"""Sürümlü projeleri katsayılardan açar; yeniden uydurma yapmadan atomik kaydeder."""

import base64
import copy
import hashlib
import io
import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from .certification import certify
from .curves import evaluate, is_full_conic, model_rings
from .evaluation import complexity, evaluate_candidate, reference_topology
from .fitting import polygon_pieces
from .models import AnalysisConfig, AnalysisResult, Boundary, Candidate, CurvePiece, PolynomialFit
from .rational_arcs import homogeneous_controls, is_rational_arc


def choose_candidate(result: AnalysisResult, candidate_id: str) -> AnalysisResult:
    """Kabul edilmiş kayıtlı adayı seçer ve önizlemeyi katsayılardan kurar."""
    selected = next((c for c in result.candidates if c.id == candidate_id), None)
    if selected is None or not selected.accepted:
        raise ValueError("Reddedilmiş veya bulunamayan model seçilemez.")
    selected = copy.deepcopy(selected)
    # Kaydedilmiş kabul bayrağı tek başına kanıt değildir; katsayılar tekrar
    # değerlendirilir. Bu işlem yeniden uydurma veya kaynak görsel okuma değildir.
    if selected.family == "exact":
        expected = [
            p
            for i, b in enumerate(result.reference_boundaries)
            for p in polygon_pieces(b, i, result.topology["rings"][i]["component_id"])
        ]
        if len(expected) != len(selected.pieces) or any(
            p.kind != "line"
            or p.boundary_id != q.boundary_id
            or not np.array_equal(p.start, q.start)
            or not np.array_equal(p.end, q.end)
            for p, q in zip(selected.pieces, expected, strict=True)
        ):
            raise ValueError("Kesin model referans piksel sınırıyla özdeş değil.")
    spacing = selected.pieces[0].tolerances.get("sample_spacing", result.config.evaluation_spacing)
    delta = selected.pieces[0].tolerances.get("flatten", result.config.flatten_tolerance)
    if not 0.0001 <= max(delta, 0.0001) <= 1 or not 0.05 <= spacing <= 10:
        raise ValueError("Kaydedilmiş ölçüm toleransları geçersiz.")
    elapsed = selected.metrics.get("elapsed_seconds")
    search_parameters = selected.metrics.get("search_parameters")
    selected.reasons = []
    evaluate_candidate(
        selected,
        result.reference_boundaries,
        result.topology,
        spacing,
        max(delta, 0.0001),
        workers=result.config.evaluation_workers,
    )
    selected.complexity = complexity(
        selected, float((result.normalization or {}).get("canvas_size", [1000])[0])
    )
    selected.metrics["elapsed_seconds"] = elapsed
    if search_parameters is not None:
        selected.metrics["search_parameters"] = search_parameters
    if selected.family == "exact":
        selected.reasons = []
        selected.metrics["topology"].update(
            preserved=True,
            scope="exact_reference_identity",
            reference_exact_identity=True,
            reasons=[],
        )
    if result.config.certificate_mode != "off":
        proof = certify(
            selected,
            result.reference_boundaries,
            result.config.tolerance,
            spacing=min(0.5, max(0.05, result.config.tolerance / 4)),
            delta=min(0.025, max(0.0001, result.config.tolerance / 32)),
        )
        selected.metrics["certification"] = proof
        selected.metrics["verified_numerical_certificate"] = proof["verified_numerical_certificate"]
        selected.metrics["topology"]["analytic_isotopy_proven"] = proof["analytic_isotopy_proven"]
        if result.config.certificate_mode == "strict" and proof["status"] != "proven":
            selected.reasons.append("Sıkı modda yeniden açılan modelin sertifikası kanıtlanamadı.")
    if (
        selected.reasons
        or selected.metrics["hausdorff_upper_bound"] > result.config.tolerance + 1e-9
    ):
        raise ValueError(
            "Kaydedilmiş aday hata/topoloji koşullarını geçemedi: " + "; ".join(selected.reasons)
        )
    rings = model_rings(selected.pieces, result.config.flatten_tolerance)
    boundaries = [
        Boundary([tuple(p) for p in rings[i][:-1]], b.kind, b.original_vertex_count)
        for i, b in enumerate(result.reference_boundaries)
    ]
    metrics = {
        **result.metrics,
        "exported_segments": len(selected.pieces),
        "exact_normalized_pixel_boundary": selected.family == "exact",
        "sampled_symmetric_distance": selected.metrics["sampled_hausdorff"],
        "distance_sample_count": selected.metrics["sample_count"],
        "selected_error_upper_bound": selected.metrics["hausdorff_upper_bound"],
    }
    return replace(
        result,
        selected_id=candidate_id,
        boundaries=boundaries,
        metrics=metrics,
        candidates=[selected if c.id == selected.id else c for c in result.candidates],
    )


def source_image(result: AnalysisResult) -> Image.Image | None:
    """Gömülü veya hash'i doğrulanan kaynak görseli beyaz zeminle açar.

    Girdi taşınmış/değişmişse None döner; model çizimi kaynaktan bağımsızdır.
    """
    provenance = result.provenance
    embedded = provenance.get("embedded_input_base64")
    path = Path(provenance.get("source_path", ""))
    data = (
        base64.b64decode(embedded, validate=True)
        if embedded
        else path.read_bytes()
        if path.is_file()
        else None
    )
    if data is None or hashlib.sha256(data).hexdigest() != provenance.get("source_sha256"):
        return None
    with Image.open(io.BytesIO(data)) as image:
        rgba = ImageOps.exif_transpose(image).convert("RGBA")
        return Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba).convert("RGB")


def _finite_tree(value: Any) -> None:
    """JSON ağaçlarında sonlu olmayan sayıları reddeder."""
    if isinstance(value, float) and not np.isfinite(value):
        raise ValueError("Projede sonlu olmayan sayı var.")
    if isinstance(value, dict):
        for item in value.values():
            _finite_tree(item)
    if isinstance(value, list):
        for item in value:
            _finite_tree(item)


def _validate_piece(piece: CurvePiece, boundary_count: int) -> None:
    """Desteklenen parametre boyutlarını ve uç/geçerlilik tutarlılığını doğrular."""
    if not 0 <= piece.boundary_id < boundary_count or piece.component_id < 0:
        raise ValueError("Parça bilinmeyen bir sınıra/bileşene başvuruyor.")
    if len(piece.interval) != 2 or piece.interval[1] <= piece.interval[0]:
        raise ValueError("Parça aralığı artan iki sonlu uç içermelidir.")
    p = piece.params
    if piece.kind == "line":
        if (
            np.asarray([p["a"], p["b"]]).shape != (2, 2)
            or np.linalg.norm(np.asarray(p["a"]) - p["b"]) <= 1e-12
        ):
            raise ValueError("Sıfır uzunluklu veya hatalı doğru parçası.")
    elif is_rational_arc(piece):
        homogeneous_controls(piece)
    elif piece.kind in {"circle", "ellipse"}:
        radii = [p["radius"]] if piece.kind == "circle" else p["radii"]
        if len(p["center"]) != 2 or min(radii) <= 0 or p.get("direction", 1) not in {-1, 1}:
            raise ValueError("Çember/elips parametreleri geçersiz.")
        if "full_turn" in p and (p["full_turn"] is not True or not is_full_conic(piece)):
            raise ValueError(
                "Tam halka bayrağı yalnızca kanonik [0,float(2π)] aralığında true olabilir."
            )
    elif piece.kind == "bezier":
        if np.asarray(p["controls"]).shape != (4, 2):
            raise ValueError("Kübik Bézier dört 2B kontrol noktası içermelidir.")
    elif piece.kind == "bspline":
        if (
            p["degree"] != 3
            or len(p["knots"]) != len(p["controls"]) + 4
            or len(p["controls"]) > 10000
        ):
            raise ValueError("Kübik B-spline boyutları geçersiz.")
        knots = np.asarray(p["knots"])
        if (
            np.any(np.diff(knots) < 0)
            or piece.interval[0] < knots[3]
            or piece.interval[1] > knots[-4]
        ):
            raise ValueError("B-spline düğüm/aralık sözleşmesi geçersiz.")
        if np.asarray(p["controls"]).shape != (len(p["controls"]), 2):
            raise ValueError("B-spline kontrol noktaları 2B olmalıdır.")
        interior = knots[(knots > piece.interval[0]) & (knots < piece.interval[1])]
        if len(np.unique(interior)) != len(interior):
            raise ValueError("Bu sürüm iç düğümleri basit olan kübik C2 spline destekler.")
    elif piece.kind == "fourier":
        order = len(p["cos"])
        if (
            not 1 <= order <= 64
            or len(p["center"]) != 2
            or np.asarray(p["cos"]).shape != (order, 2)
            or np.asarray(p["sin"]).shape != (order, 2)
        ):
            raise ValueError("Fourier katsayı boyutları geçersiz.")
    else:
        raise ValueError(f"Desteklenmeyen model türü: {piece.kind}")
    endpoints = evaluate(piece, piece.interval)
    if is_rational_arc(piece) and not np.array_equal(endpoints, [piece.start, piece.end]):
        raise ValueError("Rasyonel yay uçları asıl katsayılarla tam eşleşmelidir.")
    if (
        endpoints.shape != (2, 2)
        or not np.isfinite(endpoints).all()
        or not np.allclose(endpoints, [piece.start, piece.end], rtol=0, atol=1e-7)
    ):
        raise ValueError("Kaydedilmiş uçlar ile eğri parametreleri tutarsız.")


def result_from_dict(data: dict[str, Any]) -> AnalysisResult:
    """Şema 2.0–2.3'ü doğrular; eski kesin 1.0 projelerini bellekte yükseltir."""
    _finite_tree(data)
    if not isinstance(data, dict):
        raise ValueError("Proje kökü bir JSON nesnesi olmalıdır.")
    if (
        data.get("format") in ("dxf", "step", "iges")
        and "selected_model" in data
        and "cad_file" in data
    ):
        raise ValueError(
            "Bu dosya CAD eşleme kaydıdır. Uygulamada yeniden açmak için model.json projesini seçin."
        )
    version = data.get("schema_version")
    if version not in {"1.0", "2.0", "2.1", "2.2", "2.3", "2.4"}:
        raise ValueError(f"Desteklenmeyen proje sürümü: {version}. Uygulamayı güncelleyin.")
    try:
        # 2.4 öncesi projeler 1000 birimlik düzleme yeniden örneklenmiş görselle üretildi.
        config = AnalysisConfig(**{"working_size": 1000, **data["config"]})
        plane = float(data["normalization"].get("canvas_size", [1000])[0])
        boundaries = [Boundary(**b) for b in data["boundaries"]]
        polynomial = PolynomialFit(**data["polynomial"]) if data.get("polynomial") else None
        if polynomial is not None:
            if (
                not 2 <= polynomial.degree <= 12
                or len(polynomial.terms) > 91
                or not polynomial.terms
            ):
                raise ValueError("Örtük polinomun derece/terim sınırı geçersiz.")
            powers = set()
            for i, j, _ in polynomial.terms:
                if (
                    not isinstance(i, int)
                    or not isinstance(j, int)
                    or min(i, j) < 0
                    or i + j > polynomial.degree
                    or (i, j) in powers
                ):
                    raise ValueError("Örtük polinom terimleri geçersiz veya yinelenmiş.")
                powers.add((i, j))
            norm = np.linalg.norm([c for _, _, c in polynomial.terms])
            if not np.isclose(norm, 1, rtol=0, atol=1e-7):
                raise ValueError(
                    "Örtük polinom katsayı normu 1 olmalıdır; sıfır polinomu geçersizdir."
                )
        if version == "1.0":
            if config.tolerance != 0:
                raise ValueError(
                    "Eski yaklaşık proje kesin referans sınırını içermiyor. Görseli yeniden analiz edin."
                )
            topology = reference_topology(boundaries)
            parts = [
                p
                for i, b in enumerate(boundaries)
                for p in polygon_pieces(b, i, topology["rings"][i]["component_id"])
            ]
            candidate = Candidate("exact", "exact", parts, accepted=True, pareto=True)
            candidate.complexity = complexity(candidate, plane)
            evaluate_candidate(candidate, boundaries, topology, 1, 0.05)
            return AnalysisResult(
                config,
                data["normalization"],
                boundaries,
                polynomial,
                data["metrics"],
                boundaries,
                [candidate],
                "exact",
                topology,
                {"load_warnings": ["1.0 kesin proje yükseltildi; kaynak görsel referansı yok."]},
            )
        reference = [Boundary(**b) for b in data["reference_boundaries"]]
        if not reference or len(reference) > 512 or any(len(b.vertices) < 3 for b in reference):
            raise ValueError("Referans sınır sayısı veya köşeleri geçersiz.")
        if sum(len(b.vertices) for b in reference) > 400000:
            raise ValueError("Proje köşe sayısı sınırını aşıyor.")
        for boundary in reference:
            coords = np.asarray(boundary.vertices, dtype=float)
            if (
                coords.shape != (len(boundary.vertices), 2)
                or np.any(coords < 0)
                or np.any(coords > plane)
                or not np.array_equal(coords, np.round(coords))
            ):
                raise ValueError(
                    "Referans piksel kenarları çalışma düzlemi içinde tam sayı koordinatlı olmalıdır."
                )
            if boundary.kind not in {"outer", "hole"}:
                raise ValueError("Bilinmeyen referans sınır türü.")
            delta = np.roll(coords, -1, axis=0) - coords
            if np.any(np.count_nonzero(delta, axis=1) != 1):
                raise ValueError(
                    "Referans sınır yalnızca sıfır olmayan yatay/dikey piksel kenarları içermelidir."
                )
        candidates = []
        if len(data["candidates"]) > 256:
            raise ValueError("Projede çok fazla aday var.")
        total_pieces = 0
        for record in data["candidates"]:
            pieces = [CurvePiece(**p) for p in record["pieces"]]
            total_pieces += len(pieces)
            if total_pieces > 400000:
                raise ValueError("Proje parça sınırını aşıyor.")
            for piece in pieces:
                _validate_piece(piece, len(reference))
            candidates.append(Candidate(**{**record, "pieces": pieces}))
        if len({c.id for c in candidates}) != len(candidates):
            raise ValueError("Yinelenen aday kimliği.")
        calculated_topology = reference_topology(reference)
        if data["topology"] != calculated_topology:
            raise ValueError("Kaydedilmiş topoloji referans sınırlarla tutarsız.")
        for c in candidates:
            for piece in c.pieces:
                if (
                    piece.component_id
                    != calculated_topology["rings"][piece.boundary_id]["component_id"]
                ):
                    raise ValueError("Parça bileşen sahipliği tutarsız.")
        result = AnalysisResult(
            config,
            data["normalization"],
            boundaries,
            polynomial,
            data["metrics"],
            reference,
            candidates,
            data["selected_id"],
            data["topology"],
            data["provenance"],
        )
        result = choose_candidate(result, result.selected_id)
        if source_image(result) is None:
            result.provenance["load_warnings"] = [
                "Kaynak görsel taşınmış/değişmiş veya gömülmemiş. Model ve dışa aktarım kullanılabilir."
            ]
        return result
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError(f"Proje şeması eksik veya bozuk: {error}") from error


def load_project(path: str | Path) -> AnalysisResult:
    """UTF-8 JSON projesini boyut ve sözleşme denetimiyle açar; uydurma yapmaz."""
    path = Path(path)
    if path.stat().st_size > 150_000_000:
        raise ValueError("Proje dosyası 150 MB sınırını aşıyor.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return result_from_dict(data)
    except (json.JSONDecodeError, UnicodeError, RecursionError) as error:
        raise ValueError("Geçerli UTF-8 proje JSON'u okunamadı.") from error


def save_project(result: AnalysisResult, path: str | Path) -> Path:
    """Önce geçici dosyayı tekrar açıp doğrular, sonra hedefi atomik yeniler."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".project-", suffix=".json", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(result.to_dict(), stream, ensure_ascii=False, allow_nan=False, indent=2)
        load_project(temp)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return path
