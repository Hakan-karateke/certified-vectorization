"""Yeni sertifikalı ailelerde tam katsayı dönüşümü ve uçtan uca kabul testleri."""

from decimal import Decimal, localcontext
from fractions import Fraction as Q
from math import comb
from pathlib import Path

import numpy as np
import pytest

from sekilden_denkleme import AnalysisConfig, analyze
from sekilden_denkleme.certification import certify
from sekilden_denkleme.conic_certification import conic_geometry, rotation_bounds
from sekilden_denkleme.curves import equation, evaluate, new_piece
from sekilden_denkleme.fitting import spline_piece
from sekilden_denkleme.models import Boundary, Candidate
from sekilden_denkleme.project import load_project, save_project
from sekilden_denkleme.rational_splines import bezier_spans


def test_rational_spline_spans_equal_independent_cox_basis():
    """Düzensiz dyadik düğümlerde tam Cox toplamını rasyonel Bernstein ile karşılaştırır."""
    knots = [0, 0, 0, 0, 0.25, 0.75, 1, 1, 1, 1]
    controls = [
        [2**40 + x, -(2**39) + y] for x, y in [(0, 0), (4, 8), (7, -2), (11, 9), (15, 3), (20, 0)]
    ]
    piece = new_piece("bspline", {"degree": 3, "knots": knots, "controls": controls}, [0, 1], 0, 0)
    spans = bezier_spans(piece)
    k = [Q(v) for v in knots]

    def basis(i, degree, t):
        if degree == 0:
            return Q(int(k[i] <= t < k[i + 1]))
        result = Q(0)
        if k[i + degree] > k[i]:
            result += (t - k[i]) / (k[i + degree] - k[i]) * basis(i, degree - 1, t)
        if k[i + degree + 1] > k[i + 1]:
            result += (
                (k[i + degree + 1] - t)
                / (k[i + degree + 1] - k[i + 1])
                * basis(i + 1, degree - 1, t)
            )
        return result

    for c, (a, b) in zip(
        spans, [(Q(0), Q(1, 4)), (Q(1, 4), Q(3, 4)), (Q(3, 4), Q(1))], strict=True
    ):
        for u in [Q(1, 7), Q(2, 3)]:
            t = a + (b - a) * u
            for axis in (0, 1):
                exact = sum(basis(i, 3, t) * controls[i][axis] for i in range(len(controls)))
                bernstein = sum(
                    comb(3, j) * u**j * (1 - u) ** (3 - j) * c[j][axis] for j in range(4)
                )
                assert exact == bernstein


def test_periodic_spline_certificate_and_reopen_without_refit(tmp_path, monkeypatch):
    """Sıkı mod gerçek rasterde tek spline seçer; açılışta yeniden uydurma yapılmaz."""
    source = Path(__file__).parents[1] / "examples/validation/dataset/circle.png"
    result = analyze(
        source,
        AnalysisConfig(
            padding=0, family="bspline", preference="simple", tolerance=3, certificate_mode="strict"
        ),
    )
    assert len(result.selected.pieces) == 1 and result.selected.pieces[0].kind == "bspline"
    proof = result.selected.metrics["certification"]
    assert proof["status"] == "proven" and proof["hausdorff_upper_bound"] <= 3
    saved = save_project(result, tmp_path / "spline.json")
    monkeypatch.setattr(
        "sekilden_denkleme.fitting.spline_piece", lambda *a: pytest.fail("Yeniden uydurma yapıldı")
    )
    loaded = load_project(saved)
    assert loaded.selected.metrics["certification"]["status"] == "proven"
    assert np.array_equal(
        evaluate(result.selected.pieces[0], np.linspace(0, 1, 1001)),
        evaluate(loaded.selected.pieces[0], np.linspace(0, 1, 1001)),
    )


def test_spline_exact_closure_is_required_for_topology_certificate():
    """Float64'te küçük görünse de gerçek rasyonel uç açıklığı kanıtta gizlenmez."""
    boundary = Boundary([(100, 100), (100, 200), (200, 200), (200, 100)], "outer", 4)
    piece = spline_piece(boundary, 0, 0, 16)
    piece.params["controls"][-1][0] += 1e-8
    proof = certify(Candidate("open", "bspline", [piece]), [boundary], 50)
    assert proof["status"] == "undetermined"
    assert any("C0" in s for s in proof["reasons"])


@pytest.mark.parametrize("angle", [0.0, 0.73, -19.3, 63.0])
def test_rotation_intervals_enclose_independent_decimal_series(angle):
    """Aralık trigonometrisini bağımsız 90 basamaklı, aralık indirgemesiz seriyle sınar."""
    with localcontext() as context:
        context.prec = 90
        x = Decimal.from_float(angle)
        s, c, ts, tc = Decimal(0), Decimal(0), x, Decimal(1)
        for j in range(300):
            s += ts
            c += tc
            ts *= -x * x / Decimal((2 * j + 2) * (2 * j + 3))
            tc *= -x * x / Decimal((2 * j + 1) * (2 * j + 2))
        sine, cosine = rotation_bounds(angle)
        for expected, interval in [(s, sine), (c, cosine)]:
            assert (
                Decimal.from_float(float(interval.lo))
                <= expected
                <= Decimal.from_float(float(interval.hi))
            )


@pytest.mark.parametrize(
    "name,kind,pieces", [("circle", "circle", 1), ("ellipse", "ellipse", 1), ("ring", "circle", 2)]
)
def test_strict_conics_are_compact_certified_and_reopen(tmp_path, name, kind, pieces):
    """Tam konikler sıkı modda kendi ailesiyle seçilir; kanıt açılışta tekrarlanır."""
    source = Path(__file__).parents[1] / f"examples/validation/dataset/{name}.png"
    result = analyze(
        source, AnalysisConfig(padding=0, family="auto", tolerance=3, certificate_mode="strict")
    )
    assert len(result.selected.pieces) == pieces
    assert all(p.kind == kind for p in result.selected.pieces)
    proof = result.selected.metrics["certification"]
    assert proof["status"] == "proven" and proof["hausdorff_upper_bound"] < 3
    for p in result.selected.pieces:
        assert p.start == p.end
        assert "tam kapalı halka" in equation(p)
    loaded = load_project(save_project(result, tmp_path / f"{name}.json"))
    assert loaded.selected.metrics["certification"]["status"] == "proven"


def test_conic_curve_bound_and_hidden_crossing_are_not_conflated():
    """Kiriş yaklaşımı küçük olsa da gerçek koniklerin kesişimine kanıt verilmez."""
    from shapely import distance, points
    from shapely.geometry import LineString, Polygon

    piece = new_piece(
        "ellipse",
        {
            "center": [500, 500],
            "radii": [300, 60],
            "rotation": 0.73,
            "direction": -1,
            "full_turn": True,
        },
        [0, 2 * np.pi],
        0,
        0,
    )
    leaves, upper, _ = conic_geometry(piece, 0.025)
    ring = np.asarray([*[c[0] for c in leaves], leaves[-1][-1]], dtype=float)
    measured = distance(
        points(evaluate(piece, np.linspace(0, 2 * np.pi, 20001))), LineString(ring)
    ).max()
    assert measured <= upper <= 0.025
    a = new_piece(
        "circle", {"center": [150, 150], "radius": 50, "direction": -1}, [0, 2 * np.pi], 0, 0
    )
    b = new_piece(
        "circle",
        {
            "center": [150 + (100 - 0.0001) * 5 / 13, 150 + (100 - 0.0001) * 12 / 13],
            "radius": 50,
            "direction": -1,
        },
        [0, 2 * np.pi],
        1,
        1,
    )
    reference = [
        Boundary([(100, 100), (100, 200), (200, 200), (200, 100)], "outer", 4),
        Boundary([(300, 300), (300, 400), (400, 400), (400, 300)], "outer", 4),
    ]
    polygons = []
    for conic in (a, b):
        chords, _, _ = conic_geometry(conic, 0.025)
        polygons.append(Polygon(np.asarray([c[0] for c in chords], dtype=float)))
    assert polygons[0].disjoint(polygons[1])
    assert np.linalg.norm(np.asarray(a.params["center"]) - b.params["center"]) < 100
    proof = certify(Candidate("crossed", "circle", [a, b]), reference, 500)
    assert proof["verified_numerical_certificate"] and not proof["analytic_isotopy_proven"]


def test_open_arc_cannot_be_certified_as_a_full_closed_ring():
    """Tam halkaya çok yakın bir yayı sessizce kapalı çembere yükseltmez."""
    piece = new_piece("circle", {"center": [150, 150], "radius": 50}, [0, 2 * np.pi - 1e-11], 0, 0)
    boundary = Boundary([(100, 100), (100, 200), (200, 200), (200, 100)], "outer", 4)
    proof = certify(Candidate("arc", "circle", [piece]), [boundary], 50)
    assert proof["status"] == "undetermined" and not proof["verified_numerical_certificate"]
