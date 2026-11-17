"""Düğüm kısıtlı min-# çokgeninin kaba kuvvet ve yapısal sınamaları."""

from itertools import combinations

import numpy as np
import pytest

from sekilden_denkleme.geometry import trace_boundaries
from sekilden_denkleme.models import Boundary
from sekilden_denkleme.optimal_polygon import (
    _edge_exact,
    min_link_boundary,
    min_link_ring,
    node_sequence,
)


def _brute_force(points: np.ndarray, tolerance: float) -> int:
    """Bütün köşe alt kümelerini deneyerek en küçük geçerli çokgeni bulur."""
    m = len(points)
    for size in range(3, m + 1):
        for nodes in combinations(range(m), size):
            if all(
                _edge_exact(points, a, (b - a) % m, tolerance)
                for a, b in zip(nodes, nodes[1:] + nodes[:1], strict=True)
            ):
                return size
    raise AssertionError("Bütün köşeleri kullanan çokgen her zaman geçerlidir.")


def _disc(radius: int) -> Boundary:
    y, x = np.mgrid[-radius - 2 : radius + 3, -radius - 2 : radius + 3]
    rings = trace_boundaries(x * x + y * y <= radius * radius)
    assert len(rings) == 1
    return rings[0]


@pytest.mark.parametrize("seed", range(12))
def test_matches_brute_force_on_random_star_polygons(seed: int) -> None:
    rng = np.random.default_rng(seed)
    count = int(rng.integers(6, 12))
    angles = np.sort(rng.uniform(0, 2 * np.pi, count))
    radius = rng.uniform(4, 12, count)
    points = np.round(np.column_stack([radius * np.cos(angles), radius * np.sin(angles)]) * 2) / 2
    assert len({tuple(p) for p in points}) == count
    for tolerance in (0.75, 1.5, 3.0):
        result = min_link_ring(points, tolerance)
        assert result["optimal"]
        assert result["lower_bound"] == result["edge_count"]
        assert result["edge_count"] == _brute_force(points, tolerance)


def test_pixel_disc_optimum_shrinks_with_tolerance_and_edges_verify() -> None:
    boundary = _disc(20)
    points = node_sequence(boundary)
    previous = len(points)
    for tolerance in (0.4, 0.8, 1.6, 3.2):
        result = min_link_ring(points, tolerance)
        nodes = result["nodes"]
        assert result["optimal"] and 3 <= len(nodes) <= previous
        assert all(
            _edge_exact(points, a, (b - a) % len(points), tolerance)
            for a, b in zip(nodes, nodes[1:] + nodes[:1], strict=True)
        )
        previous = len(nodes)
    assert previous < len(points) / 4


def test_midpoints_never_hurt_and_help_on_staircase() -> None:
    boundary = _disc(30)
    plain, _ = min_link_boundary(boundary, 0.55)
    refined, record = min_link_boundary(boundary, 0.55, splits=2)
    assert record["optimal"] and record["splits"] == 2
    assert len(refined.vertices) <= len(plain.vertices)
    assert len(refined.vertices) < len(boundary.vertices)


def test_square_is_already_minimal_and_inputs_are_validated() -> None:
    square = Boundary([(0, 0), (0, 10), (10, 10), (10, 0)], "outer", 4)
    simplified, record = min_link_boundary(square, 1.0)
    assert len(simplified.vertices) == 4 and record["optimal"]
    with pytest.raises(ValueError):
        min_link_ring(np.zeros((2, 2)), 1.0)
    with pytest.raises(ValueError):
        min_link_ring(np.asarray(square.vertices, dtype=float), 0.0)
    with pytest.raises(ValueError):
        node_sequence(square, 0)


def test_boundary_tolerance_falls_back_to_exactly_verified_cycle() -> None:
    # 3-4-5 üçgenleri 0.6 uzaklığını tam üretir; float(0.6) < 3/5 olduğundan
    # üst küme grafiğinin turu tam aritmetikte reddedilir ve güvenli tura dönülür.
    points = node_sequence(_disc(30), 2)
    result = min_link_ring(points, 0.6)
    nodes = result["nodes"]
    assert result["lower_bound"] <= result["edge_count"] == len(nodes)
    assert all(
        _edge_exact(points, a, (b - a) % len(points), 0.6)
        for a, b in zip(nodes, nodes[1:] + nodes[:1], strict=True)
    )
