"""Aralık kapsamı, analitik yeter koşullar, köşe araması ve Fourier kabul testleri."""

import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from sekilden_denkleme import AnalysisConfig, analyze
from sekilden_denkleme.certification import Interval, certify
from sekilden_denkleme.curves import evaluate, flatten, new_piece
from sekilden_denkleme.evaluation import EvaluationContext, evaluate_candidate, reference_topology
from sekilden_denkleme.export import ExportOptions, export_file
from sekilden_denkleme.fitting import polygon_pieces
from sekilden_denkleme.models import Boundary, Candidate
from sekilden_denkleme.project import load_project, save_project


def test_outward_intervals_contain_exact_rational_results():
    """500 rastgele dyadik çiftte dört temel işlemi tam Fraction ile karşılaştırır."""
    rng = np.random.default_rng(771)
    a = rng.uniform(-2, 2, 500) * np.exp2(rng.integers(-200, 200, 500))
    b = rng.uniform(0.5, 2, 500) * np.exp2(rng.integers(-200, 200, 500))
    for interval, operation in [
        (Interval.point(a) + Interval.point(b), lambda x, y: x + y),
        (Interval.point(a) - Interval.point(b), lambda x, y: x - y),
        (Interval.point(a) * Interval.point(b), lambda x, y: x * y),
        (Interval.point(a) / Interval.point(b), lambda x, y: x / y),
    ]:
        for i in range(len(a)):
            exact = operation(Fraction(float(a[i])), Fraction(float(b[i])))
            assert Fraction(float(interval.lo[i])) <= exact <= Fraction(float(interval.hi[i]))


def fixture_model(loop: bool = False) -> tuple[Candidate, list[Boundary]]:
    """Aynı Jordan halkası veya gizli geri dönüş içeren kübik aday kurar."""
    boundary = Boundary([(100, 100), (100, 200), (200, 200), (200, 100)], "outer", 4)
    controls = [[100, 100], [105, 133], [105, 166], [100, 200]]
    if loop:
        controls = [[100, 100], [100, 260], [100, 40], [100, 200]]
    pieces = [
        new_piece("bezier", {"controls": controls}, [0, 1], 0, 0),
        *polygon_pieces(boundary, 0, 0)[1:],
    ]
    return Candidate("test", "adaptive", pieces), [boundary]


def test_interval_error_and_analytic_jordan_certificate():
    """Basit kübik/doğru karışımında hata ve analitik izotopi yeter koşullarını sınar."""
    candidate, reference = fixture_model()
    proof = certify(candidate, reference, 10)
    assert proof["status"] == "proven"
    assert proof["verified_numerical_certificate"] and proof["analytic_isotopy_proven"]
    assert proof["hausdorff_upper_bound"] < 10


def test_hidden_retracing_is_not_certified_as_embedded_curve():
    """Aynı nokta kümesi üzerinde gidip gelen kübiğe izotopi kanıtı verilmez."""
    candidate, reference = fixture_model(True)
    proof = certify(candidate, reference, 10)
    assert proof["verified_numerical_certificate"]
    assert not proof["analytic_isotopy_proven"]
    assert proof["status"] == "undetermined"


def test_unsupported_family_never_gets_a_fabricated_certificate():
    """Transandantal aile desteklenmediğinde belirsizlik açıkça kalır."""
    p = new_piece(
        "fourier", {"center": [150, 150], "cos": [[50, 0]], "sin": [[0, 50]]}, [0, 2 * np.pi], 0, 0
    )
    proof = certify(Candidate("fourier", "fourier", [p]), fixture_model()[1], 5)
    assert proof["status"] == "undetermined"
    assert not proof["verified_numerical_certificate"]


@pytest.mark.parametrize("epsilon,spacing", [(-1, 0.5), (float("nan"), 0.5), (1, 0)])
def test_invalid_certificate_request_cannot_report_success(epsilon, spacing):
    """Yapısal özdeşlik dahi geçersiz ölçüm isteğine başarı bayrağı vermemelidir."""
    reference = fixture_model()[1]
    candidate = Candidate("exact", "exact", polygon_pieces(reference[0], 0, 0))
    proof = certify(candidate, reference, epsilon, spacing=spacing)
    assert proof["status"] == "undetermined" and proof["reasons"]


def test_exact_nesting_proof_handles_holes_and_rejects_moved_hole():
    """Sayısal içerilme sonucuna güvenmeden delik ağacını rasyonel olarak doğrular."""
    outer = Boundary([(100, 100), (100, 200), (200, 200), (200, 100)], "outer", 4)
    hole = Boundary([(120, 120), (180, 120), (180, 180), (120, 180)], "hole", 4)
    moved = Boundary([(105, 100), (105, 200), (200, 200), (200, 100)], "outer", 4)
    candidate = Candidate(
        "holes", "polygon", polygon_pieces(moved, 0, 0) + polygon_pieces(hole, 1, 0)
    )
    assert certify(candidate, [outer, hole], 10)["status"] == "proven"
    outside = Boundary([(250, 120), (310, 120), (310, 180), (250, 180)], "hole", 4)
    bad = Candidate(
        "lost-hole", "polygon", polygon_pieces(moved, 0, 0) + polygon_pieces(outside, 1, 0)
    )
    proof = certify(bad, [outer, hole], 200)
    assert proof["verified_numerical_certificate"]
    assert not proof["analytic_isotopy_proven"]


def test_corner_graph_reduces_snowflake_with_certified_error():
    """Gerçek kar tanesinde 469 parça gerilemesini sınırlı DAG aramasıyla yakalar."""
    path = Path(__file__).parents[1] / "examples/complex_inputs/png/fa_snowflake.png"
    if not path.exists():
        pytest.skip("İndirilen dış veri yerel ortamda bulunmuyor.")
    result = analyze(path, AnalysisConfig(family="adaptive", tolerance=2))
    assert len(result.selected.pieces) < 100
    proof = result.selected.metrics["certification"]
    assert proof["status"] == "proven" and proof["hausdorff_upper_bound"] <= 2
    assert any(p.kind == "line" for p in result.selected.pieces)
    assert any(p.kind == "bezier" for p in result.selected.pieces)


def test_parallel_segment_index_matches_single_worker():
    """İki halkada CPU paralelliği ve ortak referans dizini ölçümü değiştirmez."""
    a = fixture_model()[1][0]
    b = Boundary([(300, 100), (300, 200), (400, 200), (400, 100)], "outer", 4)
    boundaries = [a, b]
    parts = polygon_pieces(a, 0, 0) + polygon_pieces(b, 1, 1)
    context = EvaluationContext(boundaries, 0.5)
    topology = reference_topology(boundaries)
    candidates = [Candidate("a", "polygon", parts), Candidate("b", "polygon", parts)]
    for c, workers in zip(candidates, [1, 2], strict=True):
        evaluate_candidate(c, boundaries, topology, 0.5, 0.025, context=context, workers=workers)
    for key in ["rms", "sampled_hausdorff", "hausdorff_upper_bound", "area_difference"]:
        assert candidates[0].metrics[key] == candidates[1].metrics[key]


def test_fourier_evaluation_flattening_and_project_roundtrip(tmp_path):
    """Yeni aileyi katsayı, süreklilik, geometrik sınır ve serileştirme ile sınar."""
    image = Image.new("L", (1000, 1000), 255)
    ImageDraw.Draw(image).ellipse((200, 200, 799, 799), fill=0)
    path = tmp_path / "circle.png"
    image.save(path)
    result = analyze(path, AnalysisConfig(family="fourier", tolerance=3, certificate_mode="off"))
    candidate = next(c for c in result.candidates if c.family == "fourier" and c.accepted)
    p = candidate.pieces[0]
    assert np.linalg.norm(np.asarray(p.start) - p.end) < 1e-9
    from shapely import distance, points
    from shapely.geometry import LineString

    assert (
        distance(
            points(evaluate(p, np.linspace(0, 2 * np.pi, 20001))), LineString(flatten(p, 0.01))
        ).max()
        <= 0.01
    )
    from sekilden_denkleme.project import choose_candidate

    result = choose_candidate(result, candidate.id)
    loaded = load_project(save_project(result, tmp_path / "fourier.json"))
    assert loaded.selected.pieces[0].params == p.params
    svg = export_file(loaded, tmp_path / "fourier.svg", "svg", ExportOptions(svg_tolerance=0.01))
    xml = ET.parse(svg).getroot()
    ns = {"s": "http://www.w3.org/2000/svg"}
    vertices = xml.find(".//s:polyline", ns).attrib["points"]
    exported = np.array([[float(v) for v in pair.split(",")] for pair in vertices.split()])
    assert np.array_equal(exported, flatten(loaded.selected.pieces[0], 0.01))
    assert xml.find(".//s:image", ns) is None


def test_seeded_annealing_is_bounded_and_reproducible(tmp_path):
    """Tavlama aday bütçesi ve aynı tohumda aynı geometri önerileri doğrulanır."""
    image = Image.new("L", (1000, 1000), 255)
    ImageDraw.Draw(image).polygon(
        [(100, 100), (200, 800), (700, 900), (850, 300), (500, 450)], fill=0
    )
    path = tmp_path / "shape.png"
    image.save(path)
    config = AnalysisConfig(
        family="adaptive",
        tolerance=3,
        search_strategy="annealing",
        search_budget=4,
        random_seed=17,
        certificate_mode="off",
    )
    a, b = analyze(path, config), analyze(path, config)
    proposals = [[c for c in r.candidates if c.id.startswith("annealing-")] for r in (a, b)]
    assert 0 < len(proposals[0]) <= 4
    assert all("search_parameters" in c.metrics for c in proposals[0])
    assert [[p.params for p in c.pieces] for c in proposals[0]] == [
        [p.params for p in c.pieces] for c in proposals[1]
    ]


def test_strict_mode_rejects_unproven_fourier_and_preserves_certificate_on_reopen(tmp_path):
    """Sıkı mod desteklenmeyen Fourier'i seçmez; sertifika yeniden hesaplanır."""
    image = Image.new("L", (1000, 1000), 255)
    ImageDraw.Draw(image).ellipse((200, 200, 799, 799), fill=0)
    path = tmp_path / "circle.png"
    image.save(path)
    result = analyze(path, AnalysisConfig(family="fourier", tolerance=3, certificate_mode="strict"))
    assert result.selected.metrics["certification"]["status"] == "proven"
    assert all(p.kind == "line" for p in result.selected.pieces)
    project = save_project(result, tmp_path / "strict.json")
    assert load_project(project).selected.metrics["certification"]["status"] == "proven"
