"""Temas korumalı, açıklık kısıtlı min-# çokgeni ve tam temas sertifikası testleri."""

from fractions import Fraction as Q
from itertools import combinations

import numpy as np

from sekilden_denkleme.contact_certificate import contact_polygon_proof
from sekilden_denkleme.geometry import trace_boundaries
from sekilden_denkleme.optimal_polygon import (
    _edge_exact,
    _find_conflict,
    constrained_min_link,
    min_link_boundaries,
    min_link_ring,
    node_sequence,
)


def _q(points):
    return [(Q(x), Q(y)) for x, y in points]


def test_unconstrained_case_matches_independent_ring_optimum():
    """Çakışma yoksa ortak çözüm, halkaların bağımsız optimumlarının toplamıdır."""
    angles = np.linspace(0, 2 * np.pi, 80, endpoint=False)
    outer = np.round(np.c_[500 + 300 * np.cos(angles), 500 + 300 * np.sin(angles)])
    inner = np.round(np.c_[500 + 100 * np.cos(-angles), 500 + 100 * np.sin(-angles)])
    result = constrained_min_link([outer, inner], 3.0)
    separate = sum(min_link_ring(r, 3.0)["edge_count"] for r in (outer, inner))
    assert result["optimal"] and result["feasible"]
    assert result["edge_count"] == result["lower_bound"] == separate
    assert result["branchings"] == 0


def test_branch_and_bound_matches_brute_force_on_conflicting_rings():
    """İnce bir aralıkta kesişen bağımsız optimumlar için dal-sınır = kaba kuvvet."""
    # Dış halkanın çentiğinde küçük bir halka durur; çentiği kesen kiriş
    # tolerans içindedir ama iç halkaya açıklıktan fazla yaklaşır.
    left = np.array(
        [[0, 0], [20, 0], [20, 10], [11, 10], [11, 9], [9, 9], [9, 10], [0, 10]], dtype=float
    )
    right = np.array([[9.5, 9.5], [10.5, 9.5], [10, 9.9]], dtype=float)
    tolerance, clearance = 1.2, 0.25
    result = constrained_min_link([left, right], tolerance, clearance, preserve_contacts=False)

    def feasible_subsets(points):
        m = len(points)
        for size in range(3, m + 1):
            for nodes in combinations(range(m), size):
                ok = True
                for a, b in zip(nodes, nodes[1:] + nodes[:1], strict=True):
                    d = (b - a) % m or m
                    for k in range(1, d):
                        p = points[(a + k) % m]
                        u, v = points[a], points[b]
                        t = np.clip(np.dot(p - u, v - u) / np.dot(v - u, v - u), 0, 1)
                        ok &= np.linalg.norm(p - (u + t * (v - u))) <= tolerance
                if ok:
                    yield list(nodes)

    best = None
    for a in feasible_subsets(left):
        for b in feasible_subsets(right):
            if _find_conflict([left, right], [a, b], clearance) is None and (
                best is None or len(a) + len(b) < best
            ):
                best = len(a) + len(b)
    assert result["feasible"] and result["optimal"]
    assert result["edge_count"] == best
    assert result["branchings"] > 0
    assert result["edge_count"] > result["unconstrained_edge_count"]


def test_contact_point_is_pinned_and_certified_exactly():
    """Çapraz iki piksel bloğu köşede dokunur; temas köşesi korunur ve kanıtlanır."""
    mask = np.zeros((40, 40), dtype=bool)
    mask[5:20, 5:20] = True
    mask[20:35, 20:35] = True
    boundaries = trace_boundaries(mask)
    simplified, record = min_link_boundaries(boundaries, 0.8, 2)
    assert record["contact_points"] == 1 and record["optimal"]
    model = {i: _q(b.vertices) for i, b in enumerate(simplified)}
    reference = {i: _q(b.vertices) for i, b in enumerate(boundaries)}
    assert contact_polygon_proof(model, reference)
    shared = set(model[0]) & set(model[1]) if len(model) > 1 else set()
    counts = {}
    for vertices in model.values():
        for vertex in vertices:
            counts[vertex] = counts.get(vertex, 0) + 1
    assert shared or max(counts.values()) == 2


def test_loop_arc_keeps_three_edges_and_matches_brute_force():
    """Köşeden dokunan tek piksel iki kenara çökemez; sonuç kaba kuvvetle aynıdır."""
    mask = np.zeros((12, 12), dtype=bool)
    mask[2:4, 2:4] = True
    mask[4, 4] = True
    boundaries = trace_boundaries(mask)
    rings = [node_sequence(b, 2) for b in boundaries]
    tolerance, clearance = 1.2, 0.25
    result = constrained_min_link(rings, tolerance, clearance)
    assert result["optimal"] and result["contact_points"] == 1
    assert all(len(cycle) >= 3 for cycle in result["cycles"])
    assert result["edge_count"] < result["node_count"]

    seen, repeated = set(), set()
    for points in rings:
        for x, y in points:
            key = (Q(float(x)), Q(float(y)))
            (repeated if key in seen else seen).add(key)
    contacts = frozenset(repeated)

    def candidates(points):
        m = len(points)
        pins = {i for i in range(m) if (Q(float(points[i][0])), Q(float(points[i][1]))) in contacts}
        for size in range(3, m + 1):
            for nodes in combinations(range(m), size):
                if pins <= set(nodes) and all(
                    _edge_exact(points, a, (b - a) % m or m, tolerance)
                    for a, b in zip(nodes, nodes[1:] + nodes[:1], strict=True)
                ):
                    yield list(nodes)

    options = [list(candidates(points)) for points in rings]
    best = None
    for a in options[0]:
        for b in options[1]:
            total = len(a) + len(b)
            if (
                total <= result["edge_count"]
                and (best is None or total < best)
                and _find_conflict(rings, [a, b], clearance, contacts) is None
            ):
                best = total
    assert best == result["edge_count"]


def test_contact_certificate_rejects_swapped_outer_face():
    """Üç diskli halkada orta yüz ile dış yüz yer değiştirirse kanıt verilmez.

    İçi dışına çevrilmiş modelde dönme sistemi, alan işaretleri ve içerilme
    referansla aynıdır; yalnız sınırsız yüz farklıdır. Disklerin orta yüz
    çevresindeki sırası ters döndüğü için yönü koruyan düzlem homeomorfizması
    yoktur.
    """
    x, y, z = (0, 0), (4, 0), (2, 3)
    half, fifth = Q(1, 2), Q(1, 5)
    reference = {
        0: _q([x, (2, -1), y, (2, half)]),
        1: _q([y, (4 - fifth, 2), z, (3 - 2 * fifth, 1 + fifth)]),
        2: _q([z, (fifth, 2), x, (1 + 2 * fifth, 1 + fifth)]),
    }
    inside_out = {
        0: _q([x, (-1, 4), (5, 4), y, (7, 6), (-3, 6)]),
        1: _q([y, z, (2, 1)]),
        2: _q([z, x, (1 + half, 1)]),
    }
    moved = {
        0: _q([x, (2, -2), y, (2, half)]),
        1: _q([y, (4, 2), z, (3 - 2 * fifth, 1 + fifth)]),
        2: _q([z, (0, 2), x, (1 + 2 * fifth, 1 + fifth)]),
    }
    assert contact_polygon_proof(reference, reference)
    assert contact_polygon_proof(moved, reference)
    assert not contact_polygon_proof(inside_out, reference)


def test_contact_certificate_checks_face_of_separate_component():
    """Temassız bir halka, temaslı bileşenin başka bir yüzüne taşınırsa kanıt verilmez."""
    x, y, z = (0, 0), (40, 0), (20, 30)
    reference = {
        0: _q([x, (20, -10), y, (20, 5)]),
        1: _q([y, (38, 20), z, (26, 12)]),
        2: _q([z, (2, 20), x, (14, 12)]),
        3: _q([(19, 9), (21, 9), (20, 11)]),
    }
    assert contact_polygon_proof(reference, reference)
    outside = dict(reference)
    outside[3] = _q([(59, 9), (61, 9), (60, 11)])
    assert not contact_polygon_proof(outside, reference)
    shifted = dict(reference)
    shifted[3] = _q([(19, 8), (21, 8), (20, 10)])
    assert contact_polygon_proof(shifted, reference)


def test_contact_certificate_rejects_crossing_and_lost_contact():
    """Temas noktasında geçiş sırası değişirse veya temas kaybolursa kanıt verilmez."""
    reference = {
        0: _q([(0, 0), (10, 0), (10, 10), (0, 10)]),
        1: _q([(10, 10), (20, 10), (20, 20), (10, 20)]),
    }
    assert contact_polygon_proof(reference, reference)
    crossing = {0: _q([(0, 0), (10, 0), (10, 10), (0, 10)]), 1: _q([(10, 10), (5, 5), (20, 20)])}
    assert not contact_polygon_proof(crossing, reference)
    separated = {
        0: _q([(0, 0), (10, 0), (9, 9), (0, 10)]),
        1: _q([(10, 10), (20, 10), (20, 20), (10, 20)]),
    }
    assert not contact_polygon_proof(separated, reference)
    disjoint = {0: reference[0], 1: _q([(30, 30), (40, 30), (40, 40)])}
    assert not contact_polygon_proof(disjoint, {0: reference[0], 1: disjoint[1]})
