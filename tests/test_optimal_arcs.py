"""Düğüm kısıtlı en az parçalı doğru + yay halkası testleri."""

import math

import numpy as np
import pytest

from sekilden_denkleme.curves import evaluate
from sekilden_denkleme.optimal_arcs import (
    BETA_MAX,
    _bulge_intervals,
    _fast_cycle,
    arc_exact,
    line_arc_pieces,
    min_piece_ring,
)
from sekilden_denkleme.optimal_polygon import _best_cycle, min_link_ring


def _reference_distance(p, a, b, beta):
    """Bağımsız yol: açı aralığıyla nokta–yay uzaklığı (β>0 a→b'nin sağına bombeli)."""
    a, b, p = (np.asarray(v, dtype=float) for v in (a, b, p))
    u = b - a
    h = np.hypot(*u) / 2
    right = np.array([u[1], -u[0]]) / (2 * h)
    centre = (a + b) / 2 + h * (beta * beta - 1) / (2 * beta) * right
    radius = h * (1 + beta * beta) / (2 * abs(beta))
    apex = (a + b) / 2 + beta * h * right
    half = 2 * math.atan(abs(beta))
    v, w = p - centre, apex - centre
    angle = abs(math.atan2(v[0] * w[1] - v[1] * w[0], v @ w))
    if angle <= half:
        return abs(np.hypot(*v) - radius)
    return min(np.hypot(*(p - a)), np.hypot(*(p - b)))


def _segment_distance(p, a, b):
    a, b, p = (np.asarray(v, dtype=float) for v in (a, b, p))
    u = b - a
    t = np.clip((p - a) @ u / (u @ u), 0, 1)
    return np.hypot(*(p - a - t * u))


def _brute_force(points, tolerance, betas):
    """Bulge ızgarasıyla geçerli parçaları bulur, en az parçalı turu döndürür."""
    m = len(points)
    valid = [[False] * m for _ in range(m)]
    for i in range(m):
        for d in range(1, m):
            a, b = points[i], points[(i + d) % m]
            if np.allclose(a, b):
                continue
            inner = [points[(i + k) % m] for k in range(1, d)]
            if all(_segment_distance(p, a, b) <= tolerance for p in inner):
                valid[i][d] = True
                continue
            for beta in betas:
                if all(_reference_distance(p, a, b, beta) <= tolerance for p in inner):
                    valid[i][d] = True
                    break
    best = None
    for start in range(m):
        reach = {0}
        for count in range(1, m + 1):
            reach = {
                position + d
                for position in reach
                if position < m
                for d in range(1, m - position + 1)
                if d < m and valid[(start + position) % m][d]
            }
            if count >= 3 and m in reach:
                best = count if best is None else min(best, count)
                break
    return best


def _digital_circle(radius, count):
    angles = np.linspace(0, 2 * np.pi, count, endpoint=False)
    points = np.round(2 * radius * np.column_stack((np.cos(angles), np.sin(angles)))) / 2
    keep = [points[0]]
    for point in points[1:]:
        if not np.array_equal(point, keep[-1]):
            keep.append(point)
    return np.asarray(keep)


def test_interval_matches_independent_distance():
    rng = np.random.default_rng(7)
    for _ in range(300):
        a = rng.uniform(-10, 10, 2)
        b = a + rng.uniform(-8, 8, 2)
        p = (a + b) / 2 + rng.uniform(-6, 6, 2)
        tolerance = float(rng.uniform(0.3, 2.5))
        lo, hi = _bulge_intervals(a[None], b[None], p[None, None], tolerance)
        for beta in np.linspace(-BETA_MAX, BETA_MAX, 81):
            if abs(beta) < 1e-3:
                continue
            distance = _reference_distance(p, a, b, beta)
            if distance <= tolerance - 1e-4:
                assert lo[0] <= beta <= hi[0]
            elif distance >= tolerance + 1e-4:
                assert not lo[0] + 1e-6 < beta < hi[0] - 1e-6


def test_digital_circle_needs_three_pieces():
    points = _digital_circle(40, 240)
    result = min_piece_ring(points, 0.875)
    polygon = min_link_ring(points, 0.875)
    assert result["optimal"] and result["piece_count"] == 3
    assert result["arc_count"] >= 2
    assert polygon["edge_count"] > 3 * result["piece_count"]
    nodes = result["nodes"]
    for i, j, beta in zip(nodes, nodes[1:] + nodes[:1], result["bulges"], strict=True):
        if beta:
            assert arc_exact(points, i, (j - i) % len(points) or len(points), beta, 0.875)


def test_square_stays_polygon():
    side = [(x / 2, 0.0) for x in range(40)]
    points = np.array(
        side
        + [(20.0, y / 2) for y in range(40)]
        + [(20 - x / 2, 20.0) for x in range(40)]
        + [(0.0, 20 - y / 2) for y in range(40)]
    )
    result = min_piece_ring(points, 0.4)
    assert result["piece_count"] == 4 and result["arc_count"] == 0 and result["optimal"]


@pytest.mark.parametrize(
    ("points", "tolerance"),
    [
        (_digital_circle(4, 22), 0.6),
        (_digital_circle(6, 26), 0.875),
        (
            np.array(
                [(0, 0), (2, -0.5), (4, -0.5), (6, 0), (7, 2), (7, 4), (6, 6), (4, 7)]
                + [(2, 7), (0, 6), (-1, 4), (-1, 2)],
                dtype=float,
            ),
            0.45,
        ),
        (
            np.array(
                [(0, 0), (3, 0), (6, 0), (6, 2), (5, 4), (3, 5), (1, 5), (0, 4), (-0.5, 2)],
                dtype=float,
            ),
            0.3,
        ),
    ],
)
def test_matches_brute_force(points, tolerance):
    result = min_piece_ring(points, tolerance)
    betas = [b for b in np.linspace(-BETA_MAX, BETA_MAX, 401) if abs(b) > 1e-6]
    brute = _brute_force(points, tolerance, betas)
    assert result["optimal"]
    assert result["piece_count"] <= brute
    assert result["piece_count"] >= _brute_force(points, tolerance + 2e-3, betas)


def test_pieces_follow_rational_arc_contract():
    points = _digital_circle(40, 240)
    result = min_piece_ring(points, 0.875)
    pieces = line_arc_pieces(points, result, 0, 0)
    assert len(pieces) == 3 and {p.kind for p in pieces} <= {"circle", "line"}
    for piece, following in zip(pieces, pieces[1:] + pieces[:1], strict=True):
        assert piece.end == following.start
        middle = evaluate(piece, [0.5])[0]
        if piece.kind == "circle":
            assert abs(np.hypot(*middle) - 40) < 1.0


def test_pipeline_family_is_certified_on_a_ring(tmp_path):
    """Halka görüntüsünde doğru + yay ailesi sıkı sertifikayla kanıtlanır."""
    from PIL import Image, ImageDraw

    from sekilden_denkleme import AnalysisConfig, analyze

    image = Image.new("L", (200, 200), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 20, 180, 180), fill=0)
    draw.ellipse((70, 70, 130, 130), fill=255)
    path = tmp_path / "ring.png"
    image.save(path)
    # 200 piksel 960 birime ölçeklenir; tolerans yaklaşık 1,7 kaynak pikselidir.
    result = analyze(path, AnalysisConfig(tolerance=8, family="linearc", certificate_mode="strict"))
    selected = next(c for c in result.candidates if c.id == result.selected_id)
    assert selected.family == "linearc"
    assert selected.metrics["certification"]["status"] == "proven"
    record = selected.pieces[0].errors["min_piece"]
    assert record["optimal"] and record["piece_count"] == len(selected.pieces) <= 24
    assert sum(p.kind == "circle" for p in selected.pieces) >= 4


def test_fast_cycle_matches_reference_search_on_random_graphs():
    """Alt sınırla budanan tur araması, pencere halkanın sonundan sarsa da aynı uzunluğu bulur."""
    rng = np.random.default_rng(11)
    for _ in range(400):
        m = int(rng.integers(6, 40))
        depth = int(rng.integers(2, min(m - 1, 12) + 1))
        valid = rng.random((depth, m)) < rng.uniform(0.1, 0.7)
        valid[0] = True
        valid = np.roll(valid, int(rng.integers(m)), axis=1)
        steps = [np.flatnonzero(valid[:, i]) + 1 for i in range(m)]
        expected = _best_cycle(steps, m)
        found = _fast_cycle(valid)
        assert len(found) == len(expected)
        for i, j in zip(found, found[1:] + found[:1], strict=True):
            assert valid[((j - i) % m or m) - 1, i]


def test_joint_smoothing_keeps_validity_and_reduces_kinks():
    """Teğet yumuşatma parça sayısını ve geçerliliği korur, kırılma toplamını artırmaz."""
    from sekilden_denkleme.optimal_arcs import joint_kinks, smooth_joints

    # Stadyum: iki yarım çember ve iki düz kenar, 0,5 birimlik ızgaraya yuvarlanmış.
    top = [(x / 2, 20.0) for x in range(-60, 61)]
    right = [(30 + 20 * np.sin(a), 20 * np.cos(a)) for a in np.linspace(0, np.pi, 126)[1:-1]]
    bottom = [(x / 2, -20.0) for x in range(60, -61, -1)]
    left = [(-30 - 20 * np.sin(a), -20 * np.cos(a)) for a in np.linspace(0, np.pi, 126)[1:-1]]
    points = np.round(2 * np.asarray(top + right + bottom + left)) / 2
    keep = np.r_[True, np.any(np.diff(points, axis=0) != 0, axis=1)]
    points = points[keep]
    tolerance = 0.8
    result = min_piece_ring(points, tolerance)
    smooth = smooth_joints(points, result, tolerance)
    assert smooth["nodes"] == result["nodes"] and len(smooth["bulges"]) == result["piece_count"]
    nodes = smooth["nodes"]
    for i, j, beta in zip(nodes, nodes[1:] + nodes[:1], smooth["bulges"], strict=True):
        if beta:
            assert arc_exact(points, i, (j - i) % len(points) or len(points), beta, tolerance)
    before = np.abs(np.asarray(smooth["kinks_before"]))
    after = np.abs(joint_kinks(points, nodes, smooth["bulges"]))
    assert np.allclose(after, np.abs(smooth["kinks_after"]))
    assert after.sum() <= before.sum() + 1e-12
