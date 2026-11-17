"""Varsayılan düğüm sınırında çözülemeyen ortak çokgen örneklerini daha yüksek sınırla yeniden koşar.

Arama belirlenimcidir ve çözülen örneklerin hiçbiri sınıra ulaşmaz; bu yüzden
yalnızca çözülemeyenler yeniden koşulur. Kayıtlar ayrı bir dosyaya yazılır,
ana sonuç dosyası değiştirilmez.

Kullanım:
    python tools/rerun_unsolved.py examples/icon_dataset/optimality_gap_3.0 1000
"""

import functools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "examples"))


def main() -> None:
    import optimality_gap

    from sekilden_denkleme import optimal_polygon

    folder, limit = Path(sys.argv[1]), int(sys.argv[2])
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))["results"]
    targets = [(r["id"], r["epsilon"]) for r in results if not r["midpoint"]["optimal_in_class"]]
    original = optimal_polygon.min_link_boundaries
    optimal_polygon.min_link_boundaries = functools.partial(original, max_search_nodes=limit)
    records = []
    for identifier, epsilon in targets:
        png = str(ROOT / "examples/icon_dataset/png" / f"{identifier}.png")
        record = optimality_gap._case((identifier, png, float(epsilon), ""))
        record["max_search_nodes"] = limit
        records.append(record)
        m = record["midpoint"]
        print(
            identifier,
            epsilon,
            m["edges"],
            m["unconstrained_edges"],
            m["optimal_in_class"],
            m["search_nodes"],
            round(m["search_seconds"], 1),
            m["certificate_status"],
            m["topology_method"],
        )
    (folder / f"unsolved_limit{limit}.json").write_text(
        json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
