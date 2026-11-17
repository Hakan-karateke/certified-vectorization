"""Temas koruyan sadeleştirmede yerel izotopi tanığı ve bağımsız olumsuz testler."""

import copy
from pathlib import Path
from threading import Event

import pytest

from sekilden_denkleme import AnalysisConfig, analyze
from sekilden_denkleme.certification import certify
from sekilden_denkleme.fitting import AnalysisCancelled, polygon_pieces
from sekilden_denkleme.models import Boundary, Candidate
from sekilden_denkleme.project import load_project, save_project
from sekilden_denkleme.topology_simplification import (
    _intersection_allowed,
    simplify_topology,
    verify_simplification,
)


def test_triangle_test_detects_contained_hole_and_allows_only_fixed_endpoints():
    """Üçgenin içindeki küçük bileşen ve sınırdaki örtüşme gözden kaçmaz."""
    a, b, c = (0, 0), (0, 10), (10, 0)
    assert not _intersection_allowed(a, b, c, (2, 2), (2, 3))
    assert not _intersection_allowed(a, b, c, (0, 2), (0, 8))
    assert not _intersection_allowed(a, b, c, (-2, 2), (2, 2))
    assert _intersection_allowed(a, b, c, (-2, 0), (0, 0))
    assert _intersection_allowed(a, b, c, (20, 20), (30, 30))


def test_replayed_witness_rejects_changed_coefficients_and_branch_deletion():
    """Kaydedilmiş başarı bayrağı, değiştirilmiş geometriye veya temas silmeye yetmez."""
    boundary = Boundary(
        [
            (100, 100),
            (100, 150),
            (100, 200),
            (150, 200),
            (200, 200),
            (200, 150),
            (200, 100),
            (150, 100),
        ],
        "outer",
        8,
    )
    output, witness = simplify_topology([boundary], 1)
    candidate = Candidate(
        "topology", "topology", polygon_pieces(output[0], 0, 0), {"topology_witness": witness}
    )
    assert verify_simplification(candidate, [boundary])["verified_removals"] == 4
    bad = copy.deepcopy(candidate)
    bad.pieces[0].params["a"][0] += 1
    with pytest.raises(ValueError, match="katsayı"):
        verify_simplification(bad, [boundary])
    contact = Boundary(
        [
            (100, 100),
            (100, 200),
            (200, 200),
            (200, 100),
            (300, 100),
            (300, 0),
            (200, 0),
            (200, 100),
        ],
        "outer",
        8,
    )
    bad = Candidate(
        "branch",
        "topology",
        [],
        {"topology_witness": {"version": "empty_triangles_v1", "removed_vertices": [3]}},
    )
    with pytest.raises(ValueError, match="üçgen"):
        verify_simplification(bad, [contact])


def test_deer_contacts_simplify_with_verified_error_and_survive_reopen(tmp_path):
    """Önceden yalnız kesin modele dönen 90 halkalı gerçek girdiyi sınar."""
    source = Path(__file__).parents[1] / "examples/complex_inputs/png/mpeg7_deer.png"
    if not source.exists():
        pytest.skip("İndirilen dış veri bulunamadı.")
    result = analyze(
        source, AnalysisConfig(family="topology", tolerance=2, certificate_mode="strict")
    )
    assert len(result.reference_boundaries) == 90 and len(result.selected.pieces) < 2100
    assert len(result.topology["contacts"]) == 5
    proof = result.selected.metrics["certification"]
    assert proof["status"] == "proven" and proof["hausdorff_upper_bound"] <= 2
    assert proof["topology_method"] == "replayed_exact_empty_triangle_planar_graph_isotopy"
    assert proof["verified_removals"] > 2000
    loaded = load_project(save_project(result, tmp_path / "deer.json"))
    assert loaded.topology == result.topology
    assert loaded.selected.metrics["certification"]["status"] == "proven"
    tampered = copy.deepcopy(result.selected)
    tampered.metrics["topology_witness"]["removed_vertices"].append(0)
    assert certify(tampered, result.reference_boundaries, 2)["status"] == "undetermined"


def test_topology_search_honors_cancellation():
    """İptal, kullanılabilir bir kısmi aday gibi dönmez."""
    event = Event()
    event.set()
    with pytest.raises(AnalysisCancelled):
        simplify_topology([Boundary([(0, 0), (0, 10), (10, 10), (10, 0)], "outer", 4)], 1, event)
