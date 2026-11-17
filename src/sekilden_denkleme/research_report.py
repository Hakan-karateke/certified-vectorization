"""Aynı veya farklı projelerin hata/karmaşıklık sonuçlarını kaynaklarıyla raporlar."""

import hashlib
import html
import json
from dataclasses import asdict
from pathlib import Path

from .models import AnalysisResult
from .pilot import _table, atomic_text, html_page, utc_now
from .project import load_project


def comparison_data(results: list[AnalysisResult]) -> dict:
    """Adayların kayıtlı ölçümlerini taşır; farklı referansları sıralamaya sokmaz."""
    if not results or len(results) > 32:
        raise ValueError("Karşılaştırma için 1–32 proje seçin.")
    projects = []
    for result in results:
        reference = json.dumps(
            [asdict(b) for b in result.reference_boundaries], sort_keys=True, separators=(",", ":")
        )
        projects.append(
            {
                "reference_sha256": hashlib.sha256(reference.encode()).hexdigest(),
                "source_sha256": result.provenance.get("source_sha256"),
                "source_path": result.provenance.get("source_path"),
                "selected_id": result.selected_id,
                "config": asdict(result.config),
                "normalization": result.normalization,
                "topology": result.topology,
                "candidates": [
                    {
                        "id": c.id,
                        "family": c.family,
                        "selected": c.id == result.selected_id,
                        "accepted": c.accepted,
                        "pareto": c.pareto,
                        "complexity": c.complexity,
                        "metrics": c.metrics,
                        "reasons": c.reasons,
                    }
                    for c in result.candidates
                ],
            }
        )
    return {
        "schema_version": "1.0",
        "recorded_at": utc_now(),
        "projects": projects,
        "same_reference": len({p["reference_sha256"] for p in projects}) == 1,
        "scope": "Recorded candidate metrics in normalized working units; no ideal-object accuracy or global optimum claim. CAD costs are separate.",
    }


def export_comparison(results: list[AnalysisResult], directory: str | Path) -> list[Path]:
    """JSON ve HTML aday tablosu üretir; kabul edilmeyen adayları gizlemez."""
    directory = Path(directory)
    data = comparison_data(results)
    paths = [
        atomic_text(
            directory / "model-comparison.json",
            json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2),
        )
    ]
    body = "<p>Ölçümler çalışma koordinatlarındadır (varsayılan ayarda kaynak pikseli). Örneklenmiş H, float64 üst tahmini ve doğrulanmış sertifika U ayrı sütunlardır. İdeal nesne hatası değildir. Bit maliyeti sabit64 model kodlamasıdır; CAD dosya/kenar maliyeti farklıdır. Sonuç yalnız incelenen adaylar kapsamındadır.</p>"
    if not data["same_reference"]:
        body += "<p><strong>Referans sınırları farklı: projeler arasında en iyi model sıralaması yapılmaz.</strong></p>"
    for index, project in enumerate(data["projects"], 1):
        body += f"<h2>Proje {index} · ε={project['config']['tolerance']}</h2><p>Referans SHA-256: {project['reference_sha256']}</p>"
        rows = []
        for c in project["candidates"]:
            metrics, cost = c["metrics"], c["complexity"]
            proof = metrics.get("certification", {})
            rows.append(
                [
                    c["id"],
                    "Seçili" if c["selected"] else "",
                    "Kabul" if c["accepted"] else "Ret",
                    cost.get("piece_count"),
                    cost.get("free_parameters_upper"),
                    cost.get("control_points"),
                    cost.get("knots"),
                    cost.get("max_degree"),
                    cost.get("score_bits"),
                    metrics.get("sampled_hausdorff"),
                    metrics.get("rms"),
                    metrics.get("hausdorff_upper_bound"),
                    proof.get("hausdorff_upper_bound") if proof.get("status") == "proven" else None,
                    proof.get("status", "off"),
                    c["pareto"],
                    "; ".join(c["reasons"]),
                ]
            )
        body += _table(
            [
                "Aday",
                "Seçim",
                "Durum",
                "Parça",
                "Parametre üst sayımı",
                "Kontrol",
                "Düğüm",
                "Derece",
                "Bit",
                "Örnek H",
                "RMS",
                "Sayısal U",
                "Sertifika U",
                "Kanıt",
                "Pareto",
                "Ret nedenleri",
            ],
            rows,
        )
    body += (
        "<h2>Ayarlar ve yeniden üretim bilgileri</h2><pre>"
        + html.escape(json.dumps(data, ensure_ascii=False, indent=2))
        + "</pre>"
    )
    paths.append(
        atomic_text(
            directory / "model-comparison.html",
            html_page("Araştırma ve eğitim: model karşılaştırması", body),
        )
    )
    return paths


def compare_saved_projects(paths: list[str], directory: str | Path) -> list[Path]:
    """Kayıtlı projeleri katsayılarından açar; görselden yeniden uydurma yapmaz."""
    if not 1 <= len(paths) <= 32:
        raise ValueError("En çok 32 proje seçin.")
    return export_comparison([load_project(p) for p in paths], directory)
