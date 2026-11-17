"""Tarama bozulmalarının ve yeniden örneklemenin etkisini ölçer.

`scan`: temiz ikon maskesi çalışma düzleminde bir tarama gibi bozulur: küçük bir
döndürme, Gauss bulanıklığı, sensör gürültüsü, yeniden eşikleme ve rastgele toz
lekeleri. Üç girdi karşılaştırılır: temiz, bozulmuş ve bozulmuş + leke temizliği
(alanı `--speck` pikselden küçük bileşen ve delikler silinir). Leke temizliği
yöntemin parçası değildir; referansı değiştiren açık bir ön işlemdir ve garanti
temizlenmiş görüntüye göredir. Bozulma sentetiktir, gerçek tarayıcı çıktısı değildir.

`resample`: uygulamanın 1000 × 1000 düzleme yeniden örneklemesinin bileşen, delik
ve temas sayılarını değiştirip değiştirmediğini sayar: ikonlarda (920 → 960,
büyütme) ve sentetik büyük girdilerde (2048, 4096 → 960, küçültme).

Kullanım:
    python examples/scan_degradation.py scan examples/icon_dataset/manifest.json \
        examples/icon_dataset/scan_degradation --ids-file examples/icon_dataset/sample200.json \
        --limit 100 --workers 12
    python examples/scan_degradation.py resample examples/icon_dataset/manifest.json \
        examples/icon_dataset/resampling_topology --workers 12
"""

import argparse
import io
import json
import statistics
import sys
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))

EPSILONS = (1.0, 2.0)
SEED = 20261116


def degrade(mask: np.ndarray, seed: int) -> np.ndarray:
    """Çalışma düzlemindeki maskeyi taranmış bir sayfa gibi bozar."""
    rng = np.random.default_rng(seed)
    gray = Image.fromarray(np.where(mask, 0, 255).astype("uint8"))
    angle = float(rng.uniform(-1.5, 1.5))
    gray = gray.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=255)
    field = ndimage.gaussian_filter(np.asarray(gray, dtype=float), 0.9)
    field += rng.normal(0.0, 22.0, field.shape)
    noisy = field <= 127
    # Toz: megapiksel başına yaklaşık 20 leke, 1–3 piksel çapında, iki renkte.
    for _ in range(int(20 * mask.size / 1e6)):
        row, col = rng.integers(8, mask.shape[0] - 8), rng.integers(8, mask.shape[1] - 8)
        size = int(rng.integers(1, 4))
        noisy[row : row + size, col : col + size] = bool(rng.integers(2))
    return noisy


def despeckle(mask: np.ndarray, area: int) -> np.ndarray:
    """Alanı `area` pikselden küçük siyah bileşenleri ve beyaz delikleri siler (4-komşuluk)."""
    cleaned = mask.copy()
    for value in (True, False):
        labels, count = ndimage.label(cleaned == value)
        sizes = ndimage.sum(np.ones_like(labels), labels, np.arange(1, count + 1))
        small = np.flatnonzero(sizes < area) + 1
        cleaned[np.isin(labels, small)] = not value
    return cleaned


def _counts(mask: np.ndarray) -> dict:
    from sekilden_denkleme.evaluation import reference_topology
    from sekilden_denkleme.geometry import trace_boundaries

    boundaries = trace_boundaries(mask, 8_000_000)
    topology = reference_topology(boundaries)
    return {
        "components": topology["component_count"],
        "holes": topology["hole_count"],
        "contacts": len(topology["contacts"]),
        "rings": len(boundaries),
        "edges": sum(len(b.vertices) for b in boundaries),
    }


def _scan(arguments: tuple[str, str, int]) -> dict:
    identifier, png, speck = arguments
    from native_inputs import analyse_mask

    from sekilden_denkleme.imaging import normalize_image

    clean, _ = normalize_image(io.BytesIO(Path(png).read_bytes()), 127, 20)
    scanned = degrade(clean, SEED + zlib.crc32(identifier.encode()))
    variants = {"clean": clean, "scanned": scanned, "despeckled": despeckle(scanned, speck)}
    record = {"id": identifier, "changed_pixels": int((clean != scanned).sum())}
    for name, mask in variants.items():
        record[name] = {"counts": _counts(mask)}
        for epsilon in EPSILONS:
            result, _ = analyse_mask(mask, epsilon, ("polygon", "linearc"))
            record[name][f"e{epsilon:g}"] = {
                family: {
                    key: result[family][key]
                    for key in (
                        "pieces",
                        "optimal_in_class",
                        "search_seconds",
                        "certify_seconds",
                        "certificate_status",
                    )
                }
                for family in ("polygon", "linearc")
            }
    return record


def _resample_icon(arguments: tuple[str, str]) -> dict:
    identifier, png = arguments
    from sekilden_denkleme.imaging import normalize_image

    with Image.open(png) as source:
        white = Image.new("RGBA", source.size, "white")
        gray = Image.alpha_composite(white, source.convert("RGBA")).convert("L")
    native = np.asarray(gray) <= 127
    canvas, metadata = normalize_image(io.BytesIO(Path(png).read_bytes()), 127, 20, 1000)
    before, after = _counts(native), _counts(canvas)
    return {
        "id": identifier,
        "scale": metadata["scale_x"],
        "native": before,
        "canvas": after,
        "topology_changed": any(before[k] != after[k] for k in ("components", "holes", "contacts")),
    }


def _resample_large(arguments: tuple[str, int]) -> dict:
    kind, size = arguments
    from native_inputs import drawing_mask, terrain_field

    from sekilden_denkleme.imaging import normalize_image

    native = terrain_field(size) >= 0.5 if kind == "terrain" else drawing_mask(size)
    buffer = io.BytesIO()
    Image.fromarray(np.where(native, 0, 255).astype("uint8")).save(buffer, format="PNG")
    buffer.seek(0)
    canvas, metadata = normalize_image(buffer, 127, 20, 1000)
    before, after = _counts(native), _counts(canvas)
    return {
        "id": f"{kind}_{size}",
        "scale": metadata["scale_x"],
        "native": before,
        "canvas": after,
        "topology_changed": any(before[k] != after[k] for k in ("components", "holes", "contacts")),
    }


def _safe(job: tuple) -> dict:
    function, arguments = job
    try:
        return function(arguments)
    except Exception as error:  # noqa: BLE001 - deney kaydı her hatayı saklar
        return {"id": arguments[0], "failed": repr(error)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["scan", "resample"])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ids-file", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--speck", type=int, default=12)
    parser.add_argument("--workers", type=int, default=4)
    options = parser.parse_args()
    manifest = json.loads(options.manifest.read_text(encoding="utf-8"))
    paths = {a["id"]: str(options.manifest.parent / a["png_path"]) for a in manifest["assets"]}
    ids = list(paths)
    if options.ids_file:
        ids = json.loads(options.ids_file.read_text(encoding="utf-8"))["ids"]
    ids = ids[: options.limit]
    if options.command == "scan":
        jobs = [(_scan, (i, paths[i], options.speck)) for i in ids]
    else:
        jobs = [(_resample_icon, (i, paths[i])) for i in ids]
        jobs += [(_resample_large, (k, s)) for k in ("terrain", "drawing") for s in (2048, 4096)]
    options.output.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(options.workers) as pool:
        records = list(pool.map(_safe, jobs))
    (options.output / "results.json").write_text(
        json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    done = [r for r in records if "failed" not in r]
    if options.command == "resample":
        icons = [r for r in done if not r["id"].startswith(("terrain_", "drawing_"))]
        summary = {
            "icons": len(icons),
            "failed": len(records) - len(done),
            "icon_scale": statistics.median(r["scale"] for r in icons) if icons else None,
            "icons_with_changed_topology": sum(r["topology_changed"] for r in icons),
            "large": [r for r in done if r["id"].startswith(("terrain_", "drawing_"))],
        }
    else:
        summary = {
            "inputs": len(done),
            "failed": len(records) - len(done),
            "speck_area": options.speck,
        }
        for name in ("clean", "scanned", "despeckled"):
            entry = {
                "median_rings": statistics.median(r[name]["counts"]["rings"] for r in done),
                "median_reference_edges": statistics.median(
                    r[name]["counts"]["edges"] for r in done
                ),
                "inputs_with_contacts": sum(r[name]["counts"]["contacts"] > 0 for r in done),
            }
            for epsilon in EPSILONS:
                for family in ("polygon", "linearc"):
                    rows = [r[name][f"e{epsilon:g}"][family] for r in done]
                    entry[f"{family}_e{epsilon:g}"] = {
                        "median_pieces": statistics.median(x["pieces"] for x in rows),
                        "optimal_in_class": sum(x["optimal_in_class"] for x in rows),
                        "proven": sum(x["certificate_status"] == "proven" for x in rows),
                        "median_search_seconds": statistics.median(
                            x["search_seconds"] for x in rows
                        ),
                    }
            summary[name] = entry
    (options.output / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1)[:6000])


if __name__ == "__main__":
    main()
