"""Gerçek taranmış belgelerden kesitlerde yöntemi kendi çözünürlüğünde çalıştırır.

Kaynaklar (üçü de ABD federal kurumu yapıtı, kamu malı; Wikimedia Commons'tan
indirilir, depoya eklenmez; `sources.json` adresleri ve SHA-256 özetlerini taşır):
    santa_cruz: USGS Santa Cruz paftası, 1902 (renkli topoğrafya haritası taraması);
    edison:     Elektrik lambası patent çizimi, NARA 595450 (kâğıt üzerinde mürekkep);
    haer:       HAER AK-30-A-108 mimari kat planı (fotoğrafla çoğaltılmış çizim).

Her kesit gri tona çevrilir ve Otsu eşiğiyle ikili yapılır. İki girdi ölçülür:
ham eşiklenmiş kesit ve lekeden arındırılmış kesit (alanı `--speck` pikselden
küçük bileşen ve delikler silinir). Leke temizliği yöntemin parçası değildir;
garanti hangi ikili görüntü verildiyse ona göredir.

Kullanım:
    python examples/real_scans.py examples/real_scans/download examples/real_scans/results
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
Image.MAX_IMAGE_PIXELS = None

SOURCES = {
    "santa_cruz": {
        "file": "santa_cruz_quadrangle_1902.png",
        "url": "https://upload.wikimedia.org/wikipedia/commons/e/ef/Santa-Cruz-Quadrangle-1902.png",
        "origin": "U.S. Geological Survey, Santa Cruz quadrangle, 1902",
        "crops": [(3000, 3600, 1024), (3000, 3600, 2048)],
    },
    "edison": {
        "file": "edison_electric_lamp_nara_595450.jpg",
        "url": "https://upload.wikimedia.org/wikipedia/commons/5/55/"
        "Drawing_for_an_Electric_Lamp_-_NARA_-_595450.jpg",
        "origin": "U.S. National Archives, identifier 595450, patent 223,898 drawing, 1880",
        "crops": [(3500, 3400, 1024), (3100, 3000, 2048)],
    },
    "haer": {
        "file": "haer_ak_30_a_108_floor_plan.tif",
        "url": "https://upload.wikimedia.org/wikipedia/commons/c/c0/"
        "Back_side_technical_facilities_S.R._%28scanning_radar%29%2C_scanner_building_no._104"
        "%2C_%22first_floor_and_mezzanine_plan%22_-_architectural%2C_AS-BLT_AW_35-03-89"
        "%2C_sheet_1_of_40%2C_dated_HAER_AK-30-A-108.tif",
        "origin": "Historic American Engineering Record, HAER AK-30-A-108",
        "crops": [(1700, 1200, 1024), (1300, 900, 2048)],
    },
}
SEARCH_LIMIT = 300


def otsu(gray: np.ndarray) -> int:
    """Sınıflar arası varyansı en büyük yapan gri eşiği döndürür."""
    histogram = np.bincount(gray.ravel(), minlength=256).astype(float)
    total = histogram.sum()
    weight = np.cumsum(histogram)
    mean = np.cumsum(histogram * np.arange(256))
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mean[-1] * weight - mean * total) ** 2 / (weight * (total - weight))
    return int(np.nanargmax(between))


def main() -> None:
    import native_inputs
    from scan_degradation import _counts, despeckle

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("download", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--speck", type=int, default=12)
    parser.add_argument("--sizes", type=int, nargs="+", default=[1024])
    parser.add_argument(
        "--arc-edges", type=int, default=40000, help="Doğru + yay yalnızca bu kadar kenara kadar"
    )
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    native_inputs.SEARCH_LIMIT = SEARCH_LIMIT
    manifest, records = {}, []
    stored = options.output / "results.json"
    if stored.exists():
        # Önceki koşunun tamamlanan kayıtları korunur ve yeniden hesaplanmaz.
        records = json.loads(stored.read_text(encoding="utf-8"))
    finished = {(r["source"], tuple(r["crop"]), r["variant"]) for r in records}
    for name, source in SOURCES.items():
        path = options.download / source["file"]
        manifest[name] = {
            "file": source["file"],
            "url": source["url"],
            "origin": source["origin"],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        with Image.open(path) as image:
            manifest[name]["size"] = list(image.size)
            gray = np.asarray(image.convert("L"))
        for x, y, size in source["crops"]:
            if size not in options.sizes:
                continue
            crop = gray[y : y + size, x : x + size]
            threshold = otsu(crop)
            raw = crop <= threshold
            variants = {"raw": raw, "despeckled": despeckle(raw, options.speck)}
            tag = f"{name}_{size}"
            Image.fromarray(crop).save(options.output / f"{tag}_gray.png")
            for variant, mask in variants.items():
                if (name, (x, y, size), variant) in finished:
                    continue
                Image.fromarray(np.where(mask, 0, 255).astype("uint8")).save(
                    options.output / f"{tag}_{variant}.png"
                )
                counts = _counts(mask)
                families = ("polygon",)
                if variant == "despeckled" and counts["edges"] <= options.arc_edges:
                    families = ("polygon", "linearc")
                record = {
                    "source": name,
                    "crop": [x, y, size],
                    "variant": variant,
                    "threshold": threshold,
                    "counts": counts,
                }
                for epsilon in (1.0, 2.0):
                    try:
                        result, _ = native_inputs.analyse_mask(mask, epsilon, families)
                        record[f"e{epsilon:g}"] = {f: result[f] for f in families}
                    except (ValueError, MemoryError) as error:
                        record[f"e{epsilon:g}"] = {"failed": repr(error)}
                records.append(record)
                print(json.dumps(record, ensure_ascii=False), flush=True)
                (options.output / "results.json").write_text(
                    json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8"
                )
    (options.output / "sources.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
