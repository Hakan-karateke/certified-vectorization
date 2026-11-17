"""Tarama kayıtlarından seçim, maliyet modeli ve aile ablasyonu özetini çıkarır.

Ablasyon yeniden analiz yapmaz: kayıtlı kabul edilmiş adaylardan bir aile
çıkarıldığında en düşük maliyetin ne kadar arttığını hesaplar. Bu sütunlar
ölçülmüş kabul ölçütüne dayanır; sertifikalı seçim sütunları ayrıca verilir.

Kullanım:
    python examples/summarize_sweep.py output/icons-2.7/cases examples/icon_dataset/pipeline_sweep
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

import numpy as np

SELECTIONS = ("strict_selected", "simple_strict_selected", "simple_strict_mdl_selected")
COSTS = ("score_bits", "mdl_bits")


def _median(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", type=Path)
    parser.add_argument("output", type=Path)
    options = parser.parse_args()
    records = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(options.cases.glob("*.json"))
    ]
    ok = [r for r in records if r.get("status") == "ok"]
    summary = {"cases": len(records), "ok": len(ok), "by_epsilon": []}
    rows = []
    for epsilon in sorted({r["epsilon"] for r in ok}):
        group = [r for r in ok if r["epsilon"] == epsilon]
        entry = {
            "epsilon": epsilon,
            "inputs": len(group),
            "median_reference_edges": _median([r["reference_piece_count"] for r in group]),
            "analysis_seconds_p50": float(
                np.percentile([r["analysis_seconds"] for r in group], 50)
            ),
            "analysis_seconds_p95": float(
                np.percentile([r["analysis_seconds"] for r in group], 95)
            ),
        }
        for name in SELECTIONS:
            chosen = [r[name] for r in group if name in r]
            entry[name] = {
                "median_pieces": _median([c["complexity"]["piece_count"] for c in chosen]),
                "median_score_bits": _median([c["complexity"]["score_bits"] for c in chosen]),
                "median_mdl_bits": _median([c["complexity"].get("mdl_bits") for c in chosen]),
                "median_certified_error": _median(
                    [
                        c["metrics"].get("certification", {}).get("hausdorff_upper_bound")
                        for c in chosen
                    ]
                ),
                "proven": sum(
                    c["metrics"].get("certification", {}).get("status") == "proven" for c in chosen
                ),
                "families": dict(Counter(c["family"] for c in chosen).most_common()),
            }
        both = [r for r in group if "simple_strict_mdl_selected" in r]
        entry["cost_models_agree"] = sum(
            r["simple_strict_selected"]["id"] == r["simple_strict_mdl_selected"]["id"] for r in both
        )
        entry["cost_models_same_family"] = sum(
            r["simple_strict_selected"]["family"] == r["simple_strict_mdl_selected"]["family"]
            for r in both
        )
        # Aile ablasyonu: kabul edilmiş adaylar, sertifikadan bağımsız.
        families = sorted({c["family"] for r in group for c in r["candidates"]} - {"exact"})
        ablation = {}
        for cost in COSTS:
            for family in families:
                ratios, changed = [], 0
                for r in group:
                    accepted = [
                        c for c in r["candidates"] if c["accepted"] and cost in c["complexity"]
                    ]
                    if not accepted:
                        continue
                    best = min(accepted, key=lambda c: c["complexity"][cost])
                    rest = [c for c in accepted if c["family"] != family]
                    without = min(c["complexity"][cost] for c in rest)
                    ratios.append(without / best["complexity"][cost])
                    changed += best["family"] == family
                ablation[f"{cost}/{family}"] = {
                    "best_in_cases": changed,
                    "median_cost_ratio_without": _median(ratios),
                    "mean_cost_ratio_without": float(np.mean(ratios)) if ratios else None,
                    "max_cost_ratio_without": max(ratios) if ratios else None,
                }
        entry["family_ablation"] = ablation
        summary["by_epsilon"].append(entry)
        for r in group:
            rows.append(
                {
                    "id": r["id"],
                    "epsilon": epsilon,
                    "reference_edges": r["reference_piece_count"],
                    "analysis_seconds": r["analysis_seconds"],
                    **{
                        name: {
                            "id": r[name]["id"],
                            "family": r[name]["family"],
                            "pieces": r[name]["complexity"]["piece_count"],
                            "score_bits": r[name]["complexity"]["score_bits"],
                            "mdl_bits": r[name]["complexity"].get("mdl_bits"),
                            "certificate": r[name]["metrics"]
                            .get("certification", {})
                            .get("status"),
                        }
                        for name in SELECTIONS
                        if name in r
                    },
                }
            )
    summary["not_ok"] = [
        {"id": r.get("id"), "epsilon": r.get("epsilon"), "status": r.get("status")}
        for r in records
        if r.get("status") != "ok"
    ]
    options.output.mkdir(parents=True, exist_ok=True)
    (options.output / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    (options.output / "results.json").write_text(json.dumps(rows), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
