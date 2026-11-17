"""Eğri sözleşmesi, geometrik sınır ve topoloji için bağımsız kabul testleri."""

import copy
from threading import Event

import numpy as np
import pytest
import shapely
from PIL import Image
from shapely.geometry import LineString

from sekilden_denkleme import AnalysisConfig, analyze
from sekilden_denkleme.benchmark import _rasterize, analytic_dataset
from sekilden_denkleme.curves import evaluate, flatten, new_piece
from sekilden_denkleme.evaluation import complexity, reference_topology, topology_check
from sekilden_denkleme.fitting import AnalysisCancelled, circle_arc, select_candidate, spline_piece
from sekilden_denkleme.geometry import sample_boundaries, trace_boundaries
from sekilden_denkleme.models import Boundary, Candidate


@pytest.mark.parametrize(
    "name,kind", [("square", "line"), ("circle", "circle"), ("ellipse", "ellipse")]
)
def test_automatic_selection_finds_basic_families(tmp_path, name, kind):
    """Gerçek raster girdide uygun aileyi ve tolerans kabulünü doğrular."""
    rings = analytic_dataset()[name]
    path = tmp_path / f"{name}.png"
    Image.fromarray(np.where(_rasterize(rings), 0, 255).astype("uint8")).save(path)
    result = analyze(path, AnalysisConfig(padding=0, tolerance=3, family="auto"))
    assert all(p.kind == kind for p in result.selected.pieces)
    assert result.selected.metrics["hausdorff_upper_bound"] <= 3
    assert result.selected.metrics["topology"]["preserved"]
    assert result.selected.pareto
    if kind == "circle":
        model = evaluate(result.selected.pieces[0], np.linspace(0, 2 * np.pi, 20001))
        reference = np.asarray(
            [*result.reference_boundaries[0].vertices, result.reference_boundaries[0].vertices[0]]
        )
        independently_measured = shapely.distance(
            shapely.points(model), LineString(reference)
        ).max()
        assert independently_measured <= result.selected.metrics["hausdorff_upper_bound"]
    for c in result.candidates:
        if c.accepted:
            assert c.metrics["hausdorff_upper_bound"] <= 3
            assert c.metrics["join_max_gap"] < 1e-7


@pytest.mark.parametrize("kind", ["circle", "ellipse", "bezier", "bspline"])
def test_curve_flattening_bound_against_dense_independent_evaluation(kind):
    """Kontrol noktalarını değil 30.001 gerçek eğri noktasını bağımsız ölçer."""
    if kind == "circle":
        piece = new_piece(
            kind, {"center": [300, 400], "radius": 220, "direction": -1}, [0.3, 5.8], 0, 0
        )
    elif kind == "ellipse":
        piece = new_piece(
            kind, {"center": [500, 500], "radii": [400, 50], "rotation": 0.65}, [0, 2 * np.pi], 0, 0
        )
    elif kind == "bezier":
        piece = new_piece(
            kind, {"controls": [[20, 50], [950, 990], [-100, 850], [900, 20]]}, [2, 5], 0, 0
        )
    else:
        t = np.linspace(0, 2 * np.pi, 60, endpoint=False)
        boundary = Boundary(
            np.column_stack([500 + 250 * np.cos(t), 500 - 180 * np.sin(t)]).tolist(), "outer", 60
        )
        piece = spline_piece(boundary, 0, 0, 16)
    delta = 0.025
    poly = flatten(piece, delta)
    t = np.linspace(*piece.interval, 30001)
    points = evaluate(piece, t)
    distances = shapely.distance(shapely.points(points), LineString(poly))
    assert distances.max() <= delta + 1e-8
    assert np.allclose(poly[[0, -1]], [piece.start, piece.end], atol=1e-10)
    with pytest.raises(ValueError, match="aralığının"):
        evaluate(piece, [piece.interval[1] + 1])


def test_circle_arc_has_exact_endpoints_and_finite_domain():
    """Aralıkla sınırlı çember yayının uçlarının veriyle tutarlı olduğunu sınar."""
    t = np.linspace(0.2, 2.6, 120)
    points = np.column_stack([500 + 200 * np.cos(t), 400 + 200 * np.sin(t)])
    arc = circle_arc(points, 0, 0, 0.001)
    assert arc is not None
    bulge = arc.params["arc"]["bulge"]
    radius = np.linalg.norm(points[-1] - points[0]) * (1 + bulge**2) / (4 * abs(bulge))
    assert radius == pytest.approx(200, abs=1e-5)
    assert np.array_equal([arc.start, arc.end], points[[0, -1]])
    assert arc.interval == [0, 1]


def test_small_components_are_never_lost_in_fitting_samples():
    """Çok farklı çevre uzunluklarında bile her halkadan örnek alınır."""
    large = Boundary([(0, 0), (1000, 0), (1000, 1000), (0, 1000)], "outer", 4)
    small = Boundary([(10, 10), (10.001, 10), (10.001, 10.001), (10, 10.001)], "hole", 4)
    points = sample_boundaries([large, small], 20)
    assert len(points) == 20
    assert (
        np.count_nonzero(
            (points[:, 0] >= 10)
            & (points[:, 0] <= 10.001)
            & (points[:, 1] >= 10)
            & (points[:, 1] <= 10.001)
        )
        >= 8
    )


def test_topology_rejects_crossings_lost_holes_and_new_contacts():
    """Öz-kesişim, boşluk kaybı ve bileşen teması sessizce kabul edilmez."""
    outer = Boundary([(0, 0), (0, 100), (100, 100), (100, 0)], "outer", 4)
    hole = Boundary([(25, 25), (75, 25), (75, 75), (25, 75)], "hole", 4)
    topology = reference_topology([outer, hole])
    good = {i: np.asarray([*b.vertices, b.vertices[0]], float) for i, b in enumerate([outer, hole])}
    assert topology_check(good, topology, 0)["preserved"]
    assert not topology_check({0: good[0]}, topology, 0)["preserved"]
    crossing = copy.deepcopy(good)
    crossing[0] = np.array([[0, 0], [100, 100], [0, 100], [100, 0], [0, 0]])
    assert not topology_check(crossing, topology, 0)["preserved"]
    crossing = copy.deepcopy(good)
    crossing[1] += 100
    assert not topology_check(crossing, topology, 0)["preserved"]
    near = copy.deepcopy(good)
    near[1][:, 0] -= 24.99
    assert not topology_check(near, topology, 0.02)["preserved"]


def test_complexity_and_pareto_selection_are_dimensionless_and_deterministic():
    """Bit kodlamasını ve basit/doğru tercihlerinin farklı sonuç verdiğini sınar."""
    piece = new_piece("line", {"a": [0, 0], "b": [1, 0]}, [0, 1], 0, 0)
    score = complexity(Candidate("p", "polygon", [piece]))
    assert score["score_bits"] == 6 * 64 + 32 + 8
    candidates = [
        Candidate("simple", "circle", [], {"hausdorff_upper_bound": 2}, {"score_bits": 100}, True),
        Candidate(
            "accurate", "exact", [], {"hausdorff_upper_bound": 0}, {"score_bits": 1000}, True
        ),
        Candidate(
            "dominated", "polygon", [], {"hausdorff_upper_bound": 3}, {"score_bits": 200}, True
        ),
    ]
    assert select_candidate(candidates, "simple", 3) == "simple"
    assert select_candidate(candidates, "accurate", 3) == "accurate"
    assert not candidates[2].pareto


def test_cancellation_never_publishes_a_partial_model(tmp_path):
    """Aday değerlendirme sırasında iptal normal sonuç üretmez."""
    path = tmp_path / "square.png"
    Image.new("L", (100, 100), 0).save(path)
    event = Event()

    def progress(message):
        if "exact" in message:
            event.set()

    with pytest.raises(AnalysisCancelled):
        analyze(path, AnalysisConfig(tolerance=2, family="auto"), cancel=event, progress=progress)


def test_diagonal_contact_exact_mode_retains_four_connectivity(tmp_path):
    """Kesin modelin noktasal temasları yaklaşık modele zorlamadığını doğrular."""
    image = np.full((1000, 1000), 255, dtype="uint8")
    image[400, 400] = 0
    image[401, 401] = 0
    path = tmp_path / "diagonal.png"
    Image.fromarray(image).save(path)
    result = analyze(path, AnalysisConfig(padding=0, tolerance=3, family="auto"))
    assert result.topology["component_count"] == 2
    assert result.topology["contacts"]
    assert result.selected.metrics["topology"]["preserved"]
    assert trace_boundaries(image == 0)


def test_mdl_code_length_shares_chain_endpoints_and_can_drive_selection():
    """mdl_v1 uzunluğunun kapalı zincirde uç paylaşımını ve seçim anahtarını sınar."""
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    lines = [
        new_piece("line", {"a": list(a), "b": list(b)}, [0, 1], 0, 0)
        for a, b in zip(square, square[1:] + square[:1], strict=True)
    ]
    score = complexity(Candidate("p", "polygon", lines))
    # Dört kenar: kenar başına 2 gerçek × 16 bit + 3 bit tür; halka sayacı gamma(4) = 5 bit.
    assert score["mdl_free_reals"] == 8
    assert score["mdl_bits"] == 4 * (2 * 16 + 3) + 5
    assert score["mdl_encoding"] == "mdl_v1"
    single = complexity(Candidate("p", "polygon", lines[:1]))
    assert single["mdl_bits"] == 4 * 16 + 3 + 1
    candidates = [
        Candidate(
            "a", "x", [], {"hausdorff_upper_bound": 1}, {"score_bits": 1, "mdl_bits": 9}, True
        ),
        Candidate(
            "b", "y", [], {"hausdorff_upper_bound": 1}, {"score_bits": 2, "mdl_bits": 5}, True
        ),
    ]
    assert select_candidate(candidates, "simple", 1) == "a"
    assert select_candidate(candidates, "simple", 1, "mdl_bits") == "b"
