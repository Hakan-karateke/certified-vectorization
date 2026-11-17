"""Yerel görsel analizini iptal edilebilir ve yeniden üretilebilir adımlarla yürütür."""

import base64
import hashlib
import io
import platform
import sys
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event

import numpy as np
import PIL
import scipy
import shapely
from PIL import Image

from .certification import CERTIFICATE_VERSION
from .curves import model_rings
from .evaluation import reference_topology
from .fitting import checkpoint, fit_models
from .geometry import sample_boundaries, trace_boundaries
from .imaging import normalize_image
from .models import AnalysisConfig, AnalysisResult, Boundary
from .polynomial import fit_polynomial, polynomial_diagnostics


def analyze(
    path: str | Path,
    config: AnalysisConfig | None = None,
    *,
    cancel: Event | None = None,
    progress: Callable[[str], None] | None = None,
) -> AnalysisResult:
    """Görselden referans sınır, ölçülmüş adaylar ve seçilen modeli üretir.

    path tek kareli raster görseldir; tolerans çalışma birimindedir (varsayılan
    ayarda bir birim bir kaynak pikseli).
    İptal AnalysisCancelled üretir; çağıranın önceki sonucu değiştirilmez.
    Kaynak okuma/GEOS/SVD çağrıları tamamlanınca iptal kontrol edilir.
    """
    started = time.perf_counter()
    config = config or AnalysisConfig()
    checkpoint(cancel)
    if progress:
        progress("Görsel normalize ediliyor…")
    image_bytes = Path(path).read_bytes()
    mask, metadata = normalize_image(
        io.BytesIO(image_bytes), config.threshold, config.padding, config.working_size or None
    )
    plane = float(mask.shape[0])
    original = trace_boundaries(mask)
    if len(original) > 512:
        raise ValueError(
            "512'den fazla sınır var; topoloji karşılaştırması için daha sade bir girdi kullanın."
        )
    checkpoint(cancel)
    if progress:
        progress("Sınır ilişkileri ve aday modeller hesaplanıyor…")
    topology = reference_topology(original)
    candidates, selected_id = fit_models(original, topology, config, cancel, progress, plane)
    selected = next(c for c in candidates if c.id == selected_id)
    rings = model_rings(selected.pieces, config.flatten_tolerance)
    boundaries = [
        Boundary([tuple(map(float, p)) for p in rings[i][:-1]], b.kind, b.original_vertex_count)
        for i, b in enumerate(original)
    ]
    fit = None
    if config.degree is not None:
        checkpoint(cancel)
        if progress:
            progress("Keşif amaçlı örtük polinom ve sıfır dalları inceleniyor…")
        polynomial_started = time.perf_counter()
        fit = fit_polynomial(
            sample_boundaries(original, config.max_fit_points), config.degree, plane
        )
        fit.diagnostics.update(polynomial_diagnostics(fit, original))
        fit.diagnostics["elapsed_seconds"] = time.perf_counter() - polynomial_started
    checkpoint(cancel)
    preview = io.BytesIO()
    Image.fromarray(np.where(mask, 0, 255).astype("uint8")).save(preview, format="PNG")
    provenance = {
        "source_path": str(Path(path).resolve()),
        "source_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "embedded_input_base64": base64.b64encode(image_bytes).decode()
        if config.embed_input
        else None,
        "normalized_png_base64": base64.b64encode(preview.getvalue()).decode(),
        "algorithm": "endpoint_rational_conics_certified_v5",
        "random_seed": config.random_seed if config.search_strategy == "annealing" else None,
        "algorithm_settings": {
            "search_strategy": config.search_strategy,
            "search_budget": config.search_budget,
            "evaluation_workers": config.evaluation_workers,
            "certificate_mode": config.certificate_mode,
            "fourier_orders": [4, 8, 16, 32],
            "corner_graph_targets": [0.72, 0.84],
            "topology_targets": [0.7, 0.85],
            "topology_auto_scope": "reference contacts or non-Jordan walks",
            "certificate_version": CERTIFICATE_VERSION,
            "circle_arc_bulge_cap": 0.9,
            "ellipse_arc_weight_bounds": [0.15, 0.98],
        },
        "python": sys.version,
        "platform": platform.platform(),
        "versions": {
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "pillow": PIL.__version__,
            "shapely": shapely.__version__,
        },
        "selection_reason": f"İncelenen kabul edilmiş adayların Pareto kümesi; tercih={config.preference}.",
        "optimality": "Sınırlı aile/ölçek araması; küresel optimum iddiası yok.",
        "topology_scope": "Analitik kanıt durumu selected.metrics.certification içinde; kanıtlanamayan aday sertifikalı sayılmaz.",
    }
    metrics = {
        "boundary_count": len(original),
        "outer_count": topology["component_count"],
        "hole_count": topology["hole_count"],
        "original_segments": sum(len(b.vertices) for b in original),
        "exported_segments": len(selected.pieces),
        "exact_normalized_pixel_boundary": selected.family == "exact",
        "sampled_symmetric_distance": selected.metrics["sampled_hausdorff"],
        "distance_sample_count": selected.metrics["sample_count"],
        "elapsed_seconds": time.perf_counter() - started,
        "selected_error_upper_bound": selected.metrics["hausdorff_upper_bound"],
    }
    return AnalysisResult(
        config,
        metadata,
        boundaries,
        fit,
        metrics,
        original,
        candidates,
        selected_id,
        topology,
        provenance,
    )
