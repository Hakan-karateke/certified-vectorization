"""Düğüm kısıtlı en az parçalı doğru + yay halkasının sınıf içi optimallik deneyi.

Her girdi ve tolerans için halkalar ayrı ayrı çözülür; kayıt parça sayısını,
kanıtlı alt sınırı, tam aritmetik onarımlarını, aynı düğümler ve aynı toleransla
en az kenarlı çokgeni ve bağımsız sertifikanın sonucunu içerir. Tolerans, hattın
`linearc` adayıyla aynıdır: ε - h/2 - 2δ - 1e-6.

Kullanım:
    python examples/line_arc_optimum.py examples/icon_dataset/manifest.json \
        examples/icon_dataset/line_arc_optimum --ids-file examples/icon_dataset/sample200.json \
        --workers 8
"""

import argparse
import io
import json
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

EPSILONS = (1, 2, 3, 5)


def _case(arguments: tuple[str, str, float]) -> dict:
    identifier, png, epsilon = arguments
    from sekilden_denkleme.certification import certify
    from sekilden_denkleme.evaluation import complexity, reference_topology
    from sekilden_denkleme.geometry import trace_boundaries
    from sekilden_denkleme.imaging import normalize_image
    from sekilden_denkleme.models import Candidate
    from sekilden_denkleme.optimal_arcs import dense_nodes, min_piece_boundaries
    from sekilden_denkleme.optimal_polygon import min_link_ring

    mask, _ = normalize_image(io.BytesIO(Path(png).read_bytes()), 127, 20)
    boundaries = trace_boundaries(mask)
    topology = reference_topology(boundaries)
    components = [r["component_id"] for r in topology["rings"]]
    spacing = min(1.0, max(0.05, epsilon / 4))
    delta = min(0.05, max(0.0001, epsilon / 16))
    tolerance = epsilon - spacing / 2 - 2 * delta - 1e-6
    started = time.perf_counter()
    pieces, info = min_piece_boundaries(boundaries, tolerance, components)
    seconds = time.perf_counter() - started
    polygon = sum(min_link_ring(dense_nodes(b), tolerance)["edge_count"] for b in boundaries)
    candidate = Candidate("linearc", "linearc", pieces)
    candidate.complexity = complexity(candidate, float(mask.shape[0]))
    proof = certify(
        candidate,
        boundaries,
        epsilon,
        spacing=min(0.5, max(0.05, epsilon / 4)),
        delta=min(0.025, max(0.0001, epsilon / 32)),
    )
    spans = [
        (b - a) % ring["node_count"] or ring["node_count"]
        for ring in info["rings"]
        for a, b, beta in zip(
            ring["nodes"], ring["nodes"][1:] + ring["nodes"][:1], ring["bulges"], strict=True
        )
        if beta
    ]
    return {
        "id": identifier,
        "epsilon": epsilon,
        "rings": len(boundaries),
        "contacts": len(topology["contacts"]),
        "nodes": sum(ring["node_count"] for ring in info["rings"]),
        "local_tolerance": tolerance,
        "polygon_edges": polygon,
        "pieces": info["piece_count"],
        "arcs": info["arc_count"],
        "lower_bound": info["lower_bound"],
        "optimal_in_class": info["optimal"],
        "repairs": info["repairs"],
        "pruned": info["pruned"],
        "max_arc_span": max(spans, default=0),
        "mdl_bits": candidate.complexity["mdl_bits"],
        "search_seconds": seconds,
        "certificate_status": proof["status"],
        "certified_upper_bound": proof.get("hausdorff_upper_bound"),
        "topology_method": proof.get("topology_method"),
        "certificate_reasons": proof["reasons"],
    }


def _safe(arguments: tuple[str, str, float]) -> dict:
    try:
        return _case(arguments)
    except Exception as error:  # noqa: BLE001 - deney kaydı her hatayı saklar
        return {"id": arguments[0], "epsilon": arguments[2], "failed": repr(error)}


def write(output: Path, results: list[dict], failed: list[dict]) -> None:
    """Kayıtları ve tolerans başına özeti yazar."""
    (output / "results.json").write_text(
        json.dumps({"failed": failed, "results": results}, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    summary = []
    for epsilon in EPSILONS:
        rows = [r for r in results if r["epsilon"] == epsilon]
        if not rows:
            continue
        free = [r for r in rows if not r["contacts"]]
        seconds = sorted(r["search_seconds"] for r in rows)
        summary.append(
            {
                "epsilon": epsilon,
                "cases": len(rows),
                "failed": sum(r["epsilon"] == epsilon for r in failed),
                "optimal_in_class": sum(r["optimal_in_class"] for r in rows),
                "cases_with_repairs": sum(r["repairs"] > 0 for r in rows),
                "max_gap": max(r["pieces"] - r["lower_bound"] for r in rows),
                "median_nodes": statistics.median(r["nodes"] for r in rows),
                "median_polygon_edges": statistics.median(r["polygon_edges"] for r in rows),
                "median_pieces": statistics.median(r["pieces"] for r in rows),
                "median_ratio": statistics.median(r["pieces"] / r["polygon_edges"] for r in rows),
                "min_ratio": min(r["pieces"] / r["polygon_edges"] for r in rows),
                "max_ratio": max(r["pieces"] / r["polygon_edges"] for r in rows),
                "arc_share": sum(r["arcs"] for r in rows) / sum(r["pieces"] for r in rows),
                "cases_at_span_limit": sum(r["max_arc_span"] >= 512 for r in rows),
                "proven": sum(r["certificate_status"] == "proven" for r in rows),
                "inputs_with_contacts": len(rows) - len(free),
                "proven_without_contacts": sum(r["certificate_status"] == "proven" for r in free),
                "median_search_seconds": statistics.median(seconds),
                "p95_search_seconds": seconds[int(0.95 * (len(seconds) - 1))],
                "max_search_seconds": seconds[-1],
            }
        )
    (output / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ids-file", type=Path, help="{'ids': [...]} biçiminde örneklem")
    parser.add_argument("--workers", type=int, default=4)
    options = parser.parse_args()
    manifest = json.loads(options.manifest.read_text(encoding="utf-8"))
    wanted = None
    if options.ids_file:
        wanted = set(json.loads(options.ids_file.read_text(encoding="utf-8"))["ids"])
    jobs = [
        (asset["id"], str(options.manifest.parent / asset["png_path"]), float(epsilon))
        for asset in manifest["assets"]
        if wanted is None or asset["id"] in wanted
        for epsilon in EPSILONS
    ]
    options.output.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(options.workers) as pool:
        records = list(pool.map(_safe, jobs))
    failed = [r for r in records if "failed" in r]
    results = [r for r in records if "failed" not in r]
    write(options.output, results, failed)


if __name__ == "__main__":
    main()
