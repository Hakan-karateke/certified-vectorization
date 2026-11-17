"""Doğru + yay ailesinin parametre duyarlılığı ve teğet yumuşatma deneyi.

Her girdi ve tolerans için:
    baseline: S = 512, β_max = 0,999 (hattın ayarı) ve teğet yumuşatma istatistikleri;
    span_256, span_1024: yay atlama sınırı S'nin etkisi;
    beta_0.9: bulge sınırının etkisi (yaylar en çok ≈168° yerine ≈167°... 2·4·atan β).
`clearance` alt komutu, çokgen ailesinde açıklık c ∈ {0,1; 0,25; 0,5} değerlerini
temas noktalı girdilerde ve örneklemde karşılaştırır.

Kullanım:
    python examples/line_arc_sensitivity.py arcs examples/icon_dataset/manifest.json \
        examples/icon_dataset/line_arc_sensitivity --ids-file examples/icon_dataset/sample200.json \
        --limit 80 --workers 12
    python examples/line_arc_sensitivity.py clearance examples/icon_dataset/manifest.json \
        examples/icon_dataset/clearance_sensitivity --ids-file examples/icon_dataset/sample200.json
"""

import argparse
import io
import json
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

EPSILONS = (1, 2, 3, 5)
VARIANTS = {
    "baseline": {"span": 512, "beta": 0.999},
    "span_256": {"span": 256, "beta": 0.999},
    "span_1024": {"span": 1024, "beta": 0.999},
    "beta_0.9": {"span": 512, "beta": 0.9},
}
SMOOTH = np.radians(5)
CORNER = np.radians(30)


def _load(png: str):
    from sekilden_denkleme.evaluation import reference_topology
    from sekilden_denkleme.geometry import trace_boundaries
    from sekilden_denkleme.imaging import normalize_image

    mask, _ = normalize_image(io.BytesIO(Path(png).read_bytes()), 127, 20)
    boundaries = trace_boundaries(mask)
    topology = reference_topology(boundaries)
    return boundaries, topology


def _arcs(arguments: tuple[str, str, float]) -> dict:
    identifier, png, epsilon = arguments
    from sekilden_denkleme import optimal_arcs
    from sekilden_denkleme.certification import certify
    from sekilden_denkleme.models import Candidate

    boundaries, topology = _load(png)
    components = [r["component_id"] for r in topology["rings"]]
    spacing = min(1.0, max(0.05, epsilon / 4))
    delta = min(0.05, max(0.0001, epsilon / 16))
    tolerance = epsilon - spacing / 2 - 2 * delta - 1e-6
    nodes = [optimal_arcs.dense_nodes(boundary) for boundary in boundaries]
    record = {"id": identifier, "epsilon": epsilon, "contacts": len(topology["contacts"])}
    for name, setting in VARIANTS.items():
        optimal_arcs.BETA_MAX = setting["beta"]
        started = time.perf_counter()
        rings = [
            optimal_arcs.min_piece_ring(points, tolerance, setting["span"]) for points in nodes
        ]
        seconds = time.perf_counter() - started
        entry = {
            "pieces": sum(r["piece_count"] for r in rings),
            "arcs": sum(r["arc_count"] for r in rings),
            "optimal_in_class": all(r["optimal"] for r in rings),
            "search_seconds": seconds,
        }
        if name == "baseline":
            smooth = [
                optimal_arcs.smooth_joints(points, ring, tolerance)
                for points, ring in zip(nodes, rings, strict=True)
            ]
            before = np.abs(np.concatenate([r["kinks_before"] for r in smooth]))
            after = np.abs(np.concatenate([r["kinks_after"] for r in smooth]))
            soft = before < CORNER
            pieces = [
                piece
                for index, (points, ring) in enumerate(zip(nodes, smooth, strict=True))
                for piece in optimal_arcs.line_arc_pieces(points, ring, index, components[index])
            ]
            proof = certify(
                Candidate("linearc-smooth", "linearc", pieces),
                boundaries,
                epsilon,
                spacing=min(0.5, max(0.05, epsilon / 4)),
                delta=min(0.025, max(0.0001, epsilon / 32)),
            )
            entry.update(
                joints=len(before),
                soft_joints=int(soft.sum()),
                smooth_before=int((before < SMOOTH).sum()),
                smooth_after=int((after < SMOOTH).sum()),
                mean_soft_kink_before_degrees=float(np.degrees(before[soft].mean()))
                if soft.any()
                else 0.0,
                mean_soft_kink_after_degrees=float(np.degrees(after[soft].mean()))
                if soft.any()
                else 0.0,
                changed_arcs=sum(
                    a != b
                    for ring, old in zip(smooth, rings, strict=True)
                    for a, b in zip(ring["bulges"], old["bulges"], strict=True)
                ),
                smoothed_certificate_status=proof["status"],
            )
        record[name] = entry
    optimal_arcs.BETA_MAX = 0.999
    return record


def _clearance(arguments: tuple[str, str, float]) -> dict:
    identifier, png, epsilon = arguments
    from sekilden_denkleme.optimal_polygon import min_link_boundaries

    boundaries, topology = _load(png)
    spacing = min(1.0, max(0.05, epsilon / 4))
    record = {"id": identifier, "epsilon": epsilon, "contacts": len(topology["contacts"])}
    for clearance in (0.1, 0.25, 0.5):
        started = time.perf_counter()
        _, info = min_link_boundaries(boundaries, epsilon - spacing / 2 - 1e-6, 2, clearance)
        record[f"c_{clearance:g}"] = {
            "edges": info["edge_count"],
            "optimal_in_class": info["optimal"],
            "search_seconds": time.perf_counter() - started,
        }
    return record


def _safe(job: tuple) -> dict:
    function, arguments = job
    try:
        return function(arguments)
    except Exception as error:  # noqa: BLE001 - deney kaydı her hatayı saklar
        return {"id": arguments[0], "epsilon": arguments[2], "failed": repr(error)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["arcs", "clearance"])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ids-file", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=4)
    options = parser.parse_args()
    manifest = json.loads(options.manifest.read_text(encoding="utf-8"))
    paths = {a["id"]: str(options.manifest.parent / a["png_path"]) for a in manifest["assets"]}
    ids = json.loads(options.ids_file.read_text(encoding="utf-8"))["ids"][: options.limit]
    function = _arcs if options.command == "arcs" else _clearance
    jobs = [(function, (i, paths[i], float(e))) for i in ids for e in EPSILONS]
    options.output.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(options.workers) as pool:
        records = list(pool.map(_safe, jobs))
    (options.output / "results.json").write_text(
        json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    done = [r for r in records if "failed" not in r]
    summary = []
    for epsilon in EPSILONS:
        rows = [r for r in done if r["epsilon"] == epsilon]
        if not rows:
            continue
        entry = {"epsilon": epsilon, "cases": len(rows)}
        entry["failed"] = sum(r["epsilon"] == epsilon for r in records if "failed" in r)
        keys = [k for k in rows[0] if isinstance(rows[0][k], dict)]
        for key in keys:
            size = "pieces" if options.command == "arcs" else "edges"
            entry[key] = {
                "median_size": statistics.median(r[key][size] for r in rows),
                "total_size": sum(r[key][size] for r in rows),
                "optimal_in_class": sum(r[key]["optimal_in_class"] for r in rows),
                "median_seconds": statistics.median(r[key]["search_seconds"] for r in rows),
                "total_seconds": sum(r[key]["search_seconds"] for r in rows),
            }
        if options.command == "arcs":
            base = [r["baseline"] for r in rows]
            entry["smoothing"] = {
                "joints": sum(b["joints"] for b in base),
                "soft_joints": sum(b["soft_joints"] for b in base),
                "smooth_before": sum(b["smooth_before"] for b in base),
                "smooth_after": sum(b["smooth_after"] for b in base),
                "mean_soft_kink_before_degrees": statistics.fmean(
                    b["mean_soft_kink_before_degrees"] for b in base
                ),
                "mean_soft_kink_after_degrees": statistics.fmean(
                    b["mean_soft_kink_after_degrees"] for b in base
                ),
                "changed_arcs": sum(b["changed_arcs"] for b in base),
                "proven_after_smoothing": sum(
                    b["smoothed_certificate_status"] == "proven" for b in base
                ),
            }
        else:
            entry["inputs_where_clearance_changes_edges"] = sum(
                len({r[k]["edges"] for k in keys}) > 1 for r in rows
            )
        summary.append(entry)
    (options.output / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
