"""Düğüm kısıtlı kesin min-# çokgeni ile mevcut seçimlerin optimallik açığı deneyi.

Her girdi × tolerans için: (a) yalnız köşeler ve (b) köşe + kenar orta noktası
düğümleriyle kanıtlı en az kenarlı çokgen hesaplanır; aynı bağımsız ölçüm ve
sertifika denetiminden geçirilir; kayıtlı 2.3 taramasındaki seçimlerle
karşılaştırılır. Yerel tolerans τ = ε − h/2 − 1e-6, hızlı ölçümün Lipschitz
örnekleme payından türetilir; ayrı ayarlanan bir sabit değildir.

Kullanım:
    python examples/optimality_gap.py examples/complex_inputs/manifest.json \
        examples/arc_stress/current_2.3/cases examples/optimality_gap --workers 6
"""

import argparse
import csv
import io
import json
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

EPSILONS = (1, 2, 3, 5)


def _case(arguments: tuple[str, str, float, str]) -> dict:
    identifier, png, epsilon, case_path = arguments
    from sekilden_denkleme.certification import certify
    from sekilden_denkleme.evaluation import (
        EvaluationContext,
        complexity,
        evaluate_candidate,
        reference_topology,
    )
    from sekilden_denkleme.fitting import polygon_pieces
    from sekilden_denkleme.geometry import simplify_boundary, trace_boundaries
    from sekilden_denkleme.imaging import normalize_image
    from sekilden_denkleme.models import Candidate
    from sekilden_denkleme.optimal_polygon import min_link_boundaries

    mask, metadata = normalize_image(io.BytesIO(Path(png).read_bytes()), 127, 20)
    boundaries = trace_boundaries(mask)
    topology = reference_topology(boundaries)
    components = [r["component_id"] for r in topology["rings"]]
    spacing = min(1.0, max(0.05, epsilon / 4))
    tau = epsilon - spacing / 2 - 1e-6
    context = EvaluationContext(boundaries, spacing)
    record = {
        "id": identifier,
        "epsilon": epsilon,
        "scale": metadata["scale_x"],
        "epsilon_source_pixels": epsilon / metadata["scale_x"],
        "rings": len(boundaries),
        "reference_edges": sum(len(b.vertices) for b in boundaries),
        "local_tolerance": tau,
    }
    for label, splits in (("vertex", 1), ("midpoint", 2)):
        started = time.perf_counter()
        try:
            # Halkalar birlikte çözülür: temas noktaları zorunlu köşe, komşu
            # olmayan kenarlar arasında açıklık kısıtı (dal-sınır).
            rings, info = min_link_boundaries(boundaries, tau, splits)
            optimal, lower = info["optimal"], info["lower_bound"]
            search_seconds = time.perf_counter() - started
            pieces = [p for i, b in enumerate(rings) for p in polygon_pieces(b, i, components[i])]
            candidate = Candidate(f"minlink-{label}", "polygon", pieces)
            candidate.complexity = complexity(candidate, float(mask.shape[0]))
            try:
                evaluate_candidate(candidate, boundaries, topology, spacing, 0.05, context=context)
                upper = candidate.metrics["hausdorff_upper_bound"]
                reasons = list(candidate.reasons)
                if upper > epsilon + 1e-9:
                    reasons.append("hata üst sınırı toleransı aşıyor")
            except Exception as error:  # noqa: BLE001 - deney kaydı her hatayı saklar
                upper, reasons = None, [str(error)]
            proof = certify(
                candidate,
                boundaries,
                epsilon,
                spacing=min(0.5, max(0.05, epsilon / 4)),
                delta=min(0.025, max(0.0001, epsilon / 32)),
            )
            record[label] = {
                "edges": len(pieces),
                "lower_bound": lower,
                "optimal_in_class": optimal,
                "bits": candidate.complexity["score_bits"],
                "hausdorff_upper_bound": upper,
                "accepted": not reasons,
                "reasons": reasons,
                "certificate_status": proof["status"],
                "certified_upper_bound": proof.get("hausdorff_upper_bound"),
                "certificate_reasons": proof["reasons"],
                "search_seconds": search_seconds,
                "unconstrained_edges": info["ringwise_edge_count"],
                "feasible": info["feasible"],
                "search_nodes": info["search_nodes"],
                "branchings": info["branchings"],
                "contact_points": info["contact_points"],
                "topology_method": proof.get("topology_method"),
            }
        except ValueError as error:
            record[label] = {"error": str(error)}
    # Sezgisel taban: önceki hattın üç RDP toleransı, aynı kabul ölçütüyle.
    accepted = []
    for factor in (0.25, 0.55, 0.85):
        rings = [simplify_boundary(b, epsilon * factor) for b in boundaries]
        pieces = [p for i, b in enumerate(rings) for p in polygon_pieces(b, i, components[i])]
        candidate = Candidate(f"polygon-{factor:g}", "polygon", pieces)
        try:
            evaluate_candidate(candidate, boundaries, topology, spacing, 0.05, context=context)
        except Exception:  # noqa: BLE001
            continue
        if not candidate.reasons and candidate.metrics["hausdorff_upper_bound"] <= epsilon + 1e-9:
            accepted.append(len(pieces))
    record["rdp_best_accepted_edges"] = min(accepted) if accepted else None
    record["sweep"] = None
    if case_path and Path(case_path).exists():
        case = json.loads(Path(case_path).read_text(encoding="utf-8"))
        polygons = [
            c["complexity"]["piece_count"]
            for c in case.get("candidates", [])
            if c.get("accepted") and c.get("family") in {"polygon", "topology"}
        ]
        record["sweep"] = {
            "best_accepted_heuristic_polygon_edges": min(polygons) if polygons else None,
            "strict_pieces": case["strict_selected"]["complexity"]["piece_count"],
            "strict_bits": case["strict_selected"]["complexity"]["score_bits"],
        }
    return record


def _safe(arguments: tuple) -> dict:
    try:
        return _case(arguments)
    except Exception as error:  # noqa: BLE001 - büyük kümede tek girdi deneyi durdurmaz
        return {"id": arguments[0], "epsilon": arguments[2], "failed": str(error)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cases", type=Path, help="İsteğe bağlı kayıtlı tarama klasörü")
    parser.add_argument("--workers", type=int, default=4)
    options = parser.parse_args()
    manifest = json.loads(options.manifest.read_text(encoding="utf-8"))
    jobs = [
        (
            asset["id"],
            str(options.manifest.parent / asset["png_path"]),
            float(epsilon),
            str(options.cases / f"{asset['id']}_e{epsilon}.json") if options.cases else "",
        )
        for asset in manifest["assets"]
        for epsilon in EPSILONS
    ]
    options.output.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(options.workers) as pool:
        records = list(pool.map(_safe, jobs, chunksize=4))
    failed = [r for r in records if "failed" in r]
    results = [r for r in records if "failed" not in r]
    (options.output / "results.json").write_text(
        json.dumps({"failed": failed, "results": results}, ensure_ascii=False), encoding="utf-8"
    )
    with (options.output / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["id", "epsilon", "epsilon_source_pixels", "reference_edges", "rdp_best"]
            + ["minlink_vertex", "minlink_midpoint", "vertex_certified", "midpoint_certified"]
        )
        for r in results:
            v, m = r["vertex"], r["midpoint"]
            writer.writerow(
                [r["id"], r["epsilon"], round(r["epsilon_source_pixels"], 4)]
                + [r["reference_edges"], r["rdp_best_accepted_edges"], v.get("edges")]
                + [m.get("edges"), v.get("certificate_status"), m.get("certificate_status")]
            )
    summary = []
    for epsilon in EPSILONS:
        rows = [r for r in results if r["epsilon"] == epsilon]
        ok = [r for r in rows if "edges" in r["vertex"] and "edges" in r["midpoint"]]
        gaps = [
            r["rdp_best_accepted_edges"] / r["vertex"]["edges"]
            for r in ok
            if r["rdp_best_accepted_edges"]
        ]

        def median(values: list) -> float | None:
            values = list(values)
            return statistics.median(values) if values else None

        summary.append(
            {
                "epsilon": epsilon,
                "cases": len(rows),
                "failed": sum(r["epsilon"] == epsilon for r in failed),
                "solved": len(ok),
                "optimal_in_class_vertex": sum(r["vertex"]["optimal_in_class"] for r in ok),
                "optimal_in_class_midpoint": sum(r["midpoint"]["optimal_in_class"] for r in ok),
                "median_reference_edges": median(r["reference_edges"] for r in rows),
                "rdp_accepted_cases": len(gaps),
                "median_rdp_edges": median(
                    r["rdp_best_accepted_edges"] for r in ok if r["rdp_best_accepted_edges"]
                ),
                "median_minlink_vertex_edges": median(r["vertex"]["edges"] for r in ok),
                "median_minlink_midpoint_edges": median(r["midpoint"]["edges"] for r in ok),
                "median_rdp_over_optimal": median(gaps),
                "p95_rdp_over_optimal": float(np.percentile(gaps, 95)) if gaps else None,
                "max_rdp_over_optimal": max(gaps) if gaps else None,
                "vertex_accepted": sum(r["vertex"]["accepted"] for r in ok),
                "vertex_proven": sum(r["vertex"]["certificate_status"] == "proven" for r in ok),
                "midpoint_accepted": sum(r["midpoint"]["accepted"] for r in ok),
                "midpoint_proven": sum(r["midpoint"]["certificate_status"] == "proven" for r in ok),
                "median_search_seconds_midpoint": median(
                    r["midpoint"]["search_seconds"] for r in ok
                ),
                "max_search_seconds_midpoint": max(
                    (r["midpoint"]["search_seconds"] for r in ok), default=None
                ),
                "inputs_with_contacts": sum(r["midpoint"]["contact_points"] > 0 for r in ok),
                "midpoint_branched": sum(r["midpoint"]["branchings"] > 0 for r in ok),
                "midpoint_extra_edges_total": sum(
                    r["midpoint"]["edges"] - r["midpoint"]["unconstrained_edges"] for r in ok
                ),
                "midpoint_max_search_nodes": max(
                    (r["midpoint"]["search_nodes"] for r in ok), default=None
                ),
                "midpoint_proven_by_contact_certificate": sum(
                    r["midpoint"]["topology_method"] == "exact_contact_preserving_polygon_embedding"
                    for r in ok
                ),
            }
        )
    (options.output / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
