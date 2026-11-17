"""Sınır algoritmasını küçük maskelerin tamamında bağımsız piksel kenarlarıyla sınar."""

import numpy as np
import pytest

from sekilden_denkleme.geometry import sample_boundaries, simplify_boundary, trace_boundaries


def expected_edges(mask):
    """Piksel karelerinin ortak kenarlarını iptal ederek yönsüz dış kenar kümesi üretir."""
    edges = set()
    height = mask.shape[0]
    for row, col in zip(*np.nonzero(mask), strict=True):
        x, y = int(col), int(height - row)
        points = [(x, y), (x + 1, y), (x + 1, y - 1), (x, y - 1)]
        for a, b in zip(points, points[1:] + points[:1], strict=True):
            edge = tuple(sorted((a, b)))
            if edge in edges:
                edges.remove(edge)
            else:
                edges.add(edge)
    return edges


def test_every_three_by_three_mask_preserves_all_edges_and_area():
    """512 olasılıkta iç boşluk, sınır teması ve köşegen temas geometrisini doğrular."""
    for bits in range(512):
        mask = np.array([(bits >> i) & 1 for i in range(9)], dtype=bool).reshape(3, 3)
        boundaries = trace_boundaries(mask)
        actual = []
        signed_area = 0
        for boundary in boundaries:
            assert len(boundary.vertices) >= 4
            points = boundary.vertices
            for a, b in zip(points, points[1:] + points[:1], strict=True):
                signed_area += (a[0] * b[1] - a[1] * b[0]) / 2
                delta = np.sign(np.array(b) - a).astype(int)
                length = int(np.max(np.abs(np.array(b) - a)))
                for step in range(length):
                    start = tuple(np.array(a) + step * delta)
                    end = tuple(np.array(a) + (step + 1) * delta)
                    actual.append(tuple(sorted((start, end))))
        assert len(actual) == len(set(actual)), bits
        assert set(actual) == expected_edges(mask), bits
        assert -signed_area == mask.sum(), bits


def test_diagonal_touch_and_hole_classification():
    """Dört-komşuluk ve yönlü alan işaretinin sözleşmeye uyduğunu doğrular."""
    diagonal = np.eye(3, dtype=bool)
    assert len(trace_boundaries(diagonal)) == 3
    ring = np.ones((5, 5), dtype=bool)
    ring[1:4, 1:4] = False
    assert sorted(b.kind for b in trace_boundaries(ring)) == ["hole", "outer"]


def test_simplification_is_optional_and_sampling_stays_on_square():
    """Kesin modun sınırı koruduğunu ve örneklerin kenar üzerinde kaldığını doğrular."""
    boundary = trace_boundaries(np.ones((10, 10), dtype=bool))[0]
    assert simplify_boundary(boundary, 0) is boundary
    assert len(simplify_boundary(boundary, 1).vertices) == 4
    points = sample_boundaries([boundary], 40)
    assert np.all(np.any((points == 0) | (points == 10), axis=1))
    assert len(np.unique(points, axis=0)) == 40


def test_pathological_noise_is_rejected_before_building_graph():
    """Yoğun dama deseninde belleği tüketmeden kontrollü hata döndüğünü doğrular."""
    mask = np.indices((1000, 1000)).sum(axis=0) % 2 == 0
    with pytest.raises(ValueError, match="400.000"):
        trace_boundaries(mask)
