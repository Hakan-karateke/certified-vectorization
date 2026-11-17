"""Potrace çıktısını aynı normalize piksel sınırına karşı bağımsız ölçer.

Potrace'e analizde kullanılan 1000×1000 eşiklenmiş maske verilir; böylece iki
yöntem aynı referans Γ'yı görür. SVG yolu ayrıştırılır; kübikler Wang sınırıyla
(hata ≤ 0.75·L/n²) δ=0.005 birime düzleştirilir. Hausdorff üst sınırı
d_s + h/2 + δ (h=0.25) ile, topoloji ise halka/bileşen/boşluk sayıları,
basitlik ve halkalar arası kesişimle raporlanır. Uzaklık bütün halkaların
birleşimi üzerindedir; halka eşlemesi gerektirmez ve Potrace lehine gevşektir.

Kullanım:
    python examples/compare_potrace.py examples/complex_inputs/manifest.json \
        .tmp/potrace/potrace-1.16.win64/potrace.exe examples/potrace_comparison
"""

import argparse
import io
import json
import re
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import shapely
from PIL import Image

from sekilden_denkleme.evaluation import reference_topology
from sekilden_denkleme.geometry import trace_boundaries
from sekilden_denkleme.imaging import normalize_image

CONFIGS = {
    "default": [],
    "no_despeckle": ["-t", "0"],
    "polygon_no_despeckle": ["-t", "0", "-a", "0"],
}
UNIT = 1000
DELTA = 0.005
SPACING = 0.25
EPSILONS = (1, 2, 3, 5)


def parse_paths(svg: str) -> list[list[tuple]]:
    """Potrace SVG'sindeki her kapalı alt yolu ('line'|'cubic', noktalar) listesi yapar."""
    rings = []
    for data in re.findall(r'<path d="([^"]+)"', svg):
        tokens = re.findall(r"[MmLlCcZz]|-?\d+(?:\.\d+)?", data)
        position = start = np.zeros(2)
        command, i, ring = None, 0, []
        while i < len(tokens):
            if tokens[i] in "MmLlCcZz":
                command = tokens[i]
                i += 1
                if command in "Zz":
                    if ring:
                        rings.append(ring)
                    ring, position = [], start
                continue
            count = 6 if command in "Cc" else 2
            values = np.asarray(tokens[i : i + count], dtype=float).reshape(-1, 2) / UNIT
            i += count
            if command.islower():
                values = values + position
            if command in "Mm":
                position = start = values[0]
                command = "l" if command == "m" else "L"
            elif command in "Ll":
                ring.append(("line", [position, values[0]]))
                position = values[0]
            else:
                ring.append(("cubic", [position, *values]))
                position = values[2]
    return rings


def flatten(ring: list[tuple]) -> np.ndarray:
    """Halkayı kanıtlı δ sapmalı kapalı kırık çizgiye çevirir (Wang sınırı)."""
    points = [ring[0][1][0]]
    for kind, c in ring:
        if kind == "line":
            points.append(c[1])
            continue
        c = np.asarray(c)
        bend = max(np.linalg.norm(c[0] - 2 * c[1] + c[2]), np.linalg.norm(c[1] - 2 * c[2] + c[3]))
        n = max(1, int(np.ceil(np.sqrt(0.75 * bend / DELTA))))
        t = (np.arange(1, n + 1) / n)[:, None]
        points.extend(
            (1 - t) ** 3 * c[0]
            + 3 * (1 - t) ** 2 * t * c[1]
            + 3 * (1 - t) * t**2 * c[2]
            + t**3 * c[3]
        )
    return np.asarray(points)


def sample(rings: list[np.ndarray]) -> np.ndarray:
    """Bütün köşeleri ve en çok SPACING aralıklı kenar noktalarını döndürür."""
    out = []
    for ring in rings:
        a, b = ring[:-1], ring[1:]
        counts = np.maximum(1, np.ceil(np.linalg.norm(b - a, axis=1) / SPACING).astype(int))
        index = np.repeat(np.arange(len(a)), counts)
        u = np.concatenate([np.arange(n) / n for n in counts])[:, None]
        out.append(a[index] + u * (b[index] - a[index]))
    return np.vstack(out)


def directed(points: np.ndarray, rings: list[np.ndarray]) -> float:
    """Örneklerden karşı tarafın sonlu kenarlarına en büyük uzaklık."""
    segments = np.vstack([np.stack([r[:-1], r[1:]], axis=1) for r in rings])
    segments = segments[np.any(segments[:, 0] != segments[:, 1], axis=1)]
    tree = shapely.STRtree(shapely.linestrings(segments))
    _, distance = tree.query_nearest(
        shapely.points(points), return_distance=True, all_matches=False
    )
    return float(distance.max())


def topology(rings: list[np.ndarray]) -> dict:
    """Halka basitliği, halkalar arası kesişim ve iç içe derinlikten bileşen/boşluk sayar."""
    lines = np.asarray([shapely.LinearRing(r) for r in rings], dtype=object)
    simple = [bool(x) for x in shapely.is_simple(lines)]
    polygons = [shapely.Polygon(r) for r in rings]
    tree = shapely.STRtree(lines)
    left, right = tree.query(lines, predicate="intersects")
    crossings = int(np.sum(left < right))
    components = holes = 0
    if all(simple) and not crossings:
        probes = shapely.points([r[0] for r in rings])
        for i, probe in enumerate(probes):
            depth = sum(
                bool(shapely.contains(polygons[j], probe)) for j in range(len(rings)) if j != i
            )
            if depth % 2:
                holes += 1
            else:
                components += 1
    return {
        "rings": len(rings),
        "all_rings_simple": all(simple),
        "ring_pair_intersections": crossings,
        "components": components if all(simple) and not crossings else None,
        "holes": holes if all(simple) and not crossings else None,
    }


def _measure(arguments: tuple[str, str, str]) -> list[dict]:
    """Bir girdiyi bütün Potrace ayarlarıyla izleyip bağımsız ölçer."""
    identifier, png, executable = arguments
    try:
        mask, _ = normalize_image(io.BytesIO(Path(png).read_bytes()), 127, 20)
        boundaries = trace_boundaries(mask)
        reference = reference_topology(boundaries)
        closed = [np.asarray([*b.vertices, b.vertices[0]], dtype=float) for b in boundaries]
        reference_samples = sample(closed)
        rows = []
        with tempfile.TemporaryDirectory() as temporary:
            bitmap = Path(temporary) / "input.pbm"
            Image.fromarray(np.where(mask, 0, 255).astype("uint8")).convert("1").save(bitmap)
            for name, flags in CONFIGS.items():
                target = Path(temporary) / "output.svg"
                started = time.perf_counter()
                subprocess.run(
                    [executable, "-b", "svg", "-u", str(UNIT), "-r", "72", *flags]
                    + [str(bitmap), "-o", str(target)],
                    check=True,
                    capture_output=True,
                )
                seconds = time.perf_counter() - started
                paths = parse_paths(target.read_text(encoding="utf-8"))
                rings = [flatten(r) for r in paths]
                lines = sum(kind == "line" for r in paths for kind, _ in r)
                cubics = sum(kind == "cubic" for r in paths for kind, _ in r)
                sampled = max(directed(reference_samples, rings), directed(sample(rings), closed))
                measured = topology(rings)
                same = (
                    measured["components"] == reference["component_count"]
                    and measured["holes"] == reference["hole_count"]
                )
                rows.append(
                    {
                        "id": identifier,
                        "config": name,
                        "pieces": lines + cubics,
                        "lines": lines,
                        "cubics": cubics,
                        "fixed64_bits": 424 * lines + 680 * cubics,
                        "sampled_hausdorff": sampled,
                        "hausdorff_upper_bound": sampled + SPACING / 2 + DELTA,
                        "topology": measured,
                        "reference_rings": len(boundaries),
                        "reference_components": reference["component_count"],
                        "reference_holes": reference["hole_count"],
                        "reference_contacts": len(reference["contacts"]),
                        "topology_counts_match": bool(same),
                        "process_seconds": seconds,
                    }
                )
        return rows
    except Exception as error:  # noqa: BLE001 - büyük kümede tek girdi deneyi durdurmaz
        return [{"id": identifier, "failed": str(error)}]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("potrace", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    options = parser.parse_args()
    executable = str(options.potrace.resolve())
    version = subprocess.run([executable, "--version"], capture_output=True, text=True).stdout
    manifest = json.loads(options.manifest.read_text(encoding="utf-8"))
    jobs = [
        (asset["id"], str(options.manifest.parent / asset["png_path"]), executable)
        for asset in manifest["assets"]
    ]
    with ProcessPoolExecutor(options.workers) as pool:
        records = [row for rows in pool.map(_measure, jobs, chunksize=4) for row in rows]
    failed = [r for r in records if "failed" in r]
    results = [r for r in records if "failed" not in r]
    summary = {}
    for name in CONFIGS:
        rows = [r for r in results if r["config"] == name]
        summary[name] = {
            "inputs": len(rows),
            "median_pieces": statistics.median(r["pieces"] for r in rows),
            "median_bits": statistics.median(r["fixed64_bits"] for r in rows),
            "median_hausdorff_upper": statistics.median(r["hausdorff_upper_bound"] for r in rows),
            "max_hausdorff_upper": max(r["hausdorff_upper_bound"] for r in rows),
            "topology_counts_match": sum(r["topology_counts_match"] for r in rows),
            "non_simple_or_crossing": sum(
                not r["topology"]["all_rings_simple"]
                or r["topology"]["ring_pair_intersections"] > 0
                for r in rows
            ),
            "median_process_seconds": statistics.median(r["process_seconds"] for r in rows),
            **{
                f"within_epsilon_{e}": sum(r["hausdorff_upper_bound"] <= e for r in rows)
                for e in EPSILONS
            },
            **{
                f"within_epsilon_{e}_and_topology": sum(
                    r["hausdorff_upper_bound"] <= e and r["topology_counts_match"] for r in rows
                )
                for e in EPSILONS
            },
        }
    options.output.mkdir(parents=True, exist_ok=True)
    record = {
        "potrace_version": version.splitlines()[0] if version else None,
        "flags": CONFIGS,
        "unit": UNIT,
        "flatten_delta": DELTA,
        "sample_spacing": SPACING,
        "bound": "sampled + spacing/2 + delta (float64, union of rings)",
        "summary": summary,
        "failed": failed,
        "results": results,
    }
    (options.output / "results.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
