"""Potrace çıktısını bu projenin bağımsız denetleyicisiyle sertifikalar.

compare_potrace.py Potrace'i kayan noktalı örneklemeyle ölçer. Burada aynı SVG
yolu doğru ve kübik Bézier parçalarına çevrilir, halkalar referans halkalarla
eşlenir ve certify() çağrılır: hata üst sınırı aralık aritmetiğiyle, topoloji
rasyonel yeter koşullarla kanıtlanır. Denetleyicinin kendi araması yoktur; yani
sertifika, hızlı bir dış aracın çıktısına sonradan takılabilir.

Halka sayısı referansla aynı değilse eşleme yapılamaz ve girdi sertifikasız kalır.

Kullanım:
    python examples/certify_potrace.py examples/icon_dataset/manifest.json \
        .tmp/potrace/potrace-1.16.win64/potrace.exe examples/icon_dataset/potrace_certified
"""

import argparse
import io
import json
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from compare_potrace import UNIT, flatten, parse_paths  # noqa: E402

SPACING = 0.25
DELTA = 0.005
LIMITS = (1, 2, 3, 5)


def _dense(ring: np.ndarray, spacing: float = 1.0) -> np.ndarray:
    closed = np.vstack([ring, ring[:1]])
    parts = []
    for a, b in zip(closed, closed[1:], strict=False):
        count = max(1, int(np.ceil(np.hypot(*(b - a)) / spacing)))
        parts.append(a + (b - a) * (np.arange(count) / count)[:, None])
    return np.concatenate(parts)


def _area(ring: np.ndarray) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return float(x @ np.roll(y, -1) - y @ np.roll(x, -1)) / 2


def _case(arguments: tuple[str, str, str]) -> dict:
    identifier, png, executable = arguments
    from sekilden_denkleme.certification import certify
    from sekilden_denkleme.curves import new_piece
    from sekilden_denkleme.evaluation import reference_topology
    from sekilden_denkleme.geometry import trace_boundaries
    from sekilden_denkleme.imaging import normalize_image
    from sekilden_denkleme.models import Candidate

    mask, _ = normalize_image(io.BytesIO(Path(png).read_bytes()), 127, 20)
    boundaries = trace_boundaries(mask)
    topology = reference_topology(boundaries)
    components = [r["component_id"] for r in topology["rings"]]
    with tempfile.TemporaryDirectory() as temporary:
        bitmap = Path(temporary) / "input.pbm"
        target = Path(temporary) / "output.svg"
        Image.fromarray(np.where(mask, 0, 255).astype("uint8")).convert("1").save(bitmap)
        started = time.perf_counter()
        subprocess.run(
            [executable, "-b", "svg", "-u", str(UNIT), "-r", "72", str(bitmap), "-o", str(target)],
            check=True,
            capture_output=True,
        )
        trace_seconds = time.perf_counter() - started
        paths = parse_paths(target.read_text(encoding="utf-8"))
    record = {
        "id": identifier,
        "reference_rings": len(boundaries),
        "potrace_rings": len(paths),
        "contacts": len(topology["contacts"]),
        "pieces": sum(len(ring) for ring in paths),
        "potrace_seconds": trace_seconds,
    }
    if len(paths) != len(boundaries):
        return {**record, "status": "ring_count_mismatch"}
    # Halka eşlemesi: düzleştirilmiş Potrace halkası ile referans halka arasındaki
    # iki yönlü örnek uzaklığının en küçük toplamı.
    flat = [_dense(flatten(ring)) for ring in paths]
    reference = [_dense(np.asarray(b.vertices, dtype=float)) for b in boundaries]
    trees = [cKDTree(points) for points in reference]
    cost = np.empty((len(flat), len(reference)))
    for i, points in enumerate(flat):
        own = cKDTree(points)
        for j, tree in enumerate(trees):
            cost[i, j] = max(tree.query(points)[0].max(), own.query(reference[j])[0].max())
    rows, columns = linear_sum_assignment(cost)
    pieces = []
    for i, j in zip(rows.tolist(), columns.tolist(), strict=True):
        ring = paths[i]
        # Yön referans halkayla aynı olmalıdır; değilse parçalar ve kontroller çevrilir.
        if _area(flatten(ring)) * _area(np.asarray(boundaries[j].vertices, dtype=float)) < 0:
            ring = [(kind, points[::-1]) for kind, points in ring[::-1]]
        first = np.asarray(ring[0][1][0], dtype=float)
        position = first
        for index, (kind, points) in enumerate(ring):
            points = [np.asarray(p, dtype=float) for p in points]
            # C0 kapanış tam olmalıdır: her parça öncekinin bittiği sayıda başlar,
            # son parça halkanın ilk noktasında biter (göreli komut yuvarlaması giderilir).
            points[0] = position
            if index == len(ring) - 1:
                if np.hypot(*(points[-1] - first)) > 1e-6:
                    raise ValueError("Potrace halkası kapanmıyor.")
                points[-1] = first
            position = points[-1]
            if kind == "line":
                if np.array_equal(points[0], points[1]):
                    continue
                params = {"a": points[0].tolist(), "b": points[1].tolist()}
                pieces.append(new_piece("line", params, [0.0, 1.0], j, components[j]))
            else:
                params = {"controls": [p.tolist() for p in points]}
                pieces.append(new_piece("bezier", params, [0.0, 1.0], j, components[j]))
    pieces.sort(key=lambda piece: piece.boundary_id)
    started = time.perf_counter()
    proof = certify(Candidate("potrace", "bezier", pieces), boundaries, 1000.0, SPACING, DELTA)
    return {
        **record,
        "status": "certified",
        "matching_cost": float(cost[rows, columns].max()),
        "certify_seconds": time.perf_counter() - started,
        "certified_upper_bound": proof.get("hausdorff_upper_bound"),
        "topology_proven": bool(proof.get("analytic_isotopy_proven")),
        "topology_method": proof.get("topology_method"),
        "certificate_reasons": proof["reasons"],
    }


def _safe(arguments: tuple[str, str, str]) -> dict:
    try:
        return _case(arguments)
    except Exception as error:  # noqa: BLE001 - deney kaydı her hatayı saklar
        return {"id": arguments[0], "status": "failed", "error": repr(error)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("potrace", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=4)
    options = parser.parse_args()
    manifest = json.loads(options.manifest.read_text(encoding="utf-8"))
    executable = str(options.potrace.resolve())
    jobs = [
        (asset["id"], str(options.manifest.parent / asset["png_path"]), executable)
        for asset in manifest["assets"][: options.limit]
    ]
    options.output.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(options.workers) as pool:
        records = list(pool.map(_safe, jobs, chunksize=4))
    (options.output / "results.json").write_text(
        json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    done = [r for r in records if r["status"] == "certified"]
    bounds = [r["certified_upper_bound"] for r in done if r["certified_upper_bound"] is not None]
    proven = [r for r in done if r["topology_proven"]]
    summary = {
        "inputs": len(records),
        "failed": sum(r["status"] == "failed" for r in records),
        "ring_count_mismatch": sum(r["status"] == "ring_count_mismatch" for r in records),
        "error_bound_certified": len(bounds),
        "median_certified_upper_bound": statistics.median(bounds) if bounds else None,
        "max_certified_upper_bound": max(bounds) if bounds else None,
        "topology_proven": len(proven),
        "topology_undetermined_with_contacts": sum(
            not r["topology_proven"] and r["contacts"] > 0 for r in done
        ),
        "median_certify_seconds": statistics.median(r["certify_seconds"] for r in done)
        if done
        else None,
        "median_potrace_seconds": statistics.median(
            r["potrace_seconds"] for r in records if "potrace_seconds" in r
        ),
        **{
            f"proven_within_{limit}": sum(
                r["topology_proven"]
                and r["certified_upper_bound"] is not None
                and r["certified_upper_bound"] <= limit
                for r in done
            )
            for limit in LIMITS
        },
    }
    (options.output / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
