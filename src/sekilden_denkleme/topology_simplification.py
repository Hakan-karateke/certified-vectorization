"""Boş üçgen tanıklarıyla temaslı piksel sınırını koruyan yerel sadeleştirme."""

import heapq
from collections import Counter
from fractions import Fraction as Q
from threading import Event

import numpy as np

from .models import Boundary, Candidate


def _cross(a: tuple, b: tuple, c: tuple) -> int:
    """Tamsayı çalışma koordinatlarında yön determinantını tam hesaplar."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _intersection_allowed(a: tuple, b: tuple, c: tuple, s: tuple, t: tuple) -> bool:
    """Kapalı üçgenle kenarın kesişimi boş veya yalnız A/C ise true döner.

    Üç yarı düzlemde doğrusal parametre kırpması Fraction ile yapılır. Sınır
    boyunca örtüşme ve üçgen içinde kalan kenar da engeldir; yalnız kesişen
    doğruları saymak küçük bir deliği gözden kaçırabilirdi.
    """
    orientation = 1 if _cross(a, b, c) > 0 else -1
    low, high = Q(0), Q(1)
    for p, q in [(a, b), (b, c), (c, a)]:
        first, last = orientation * _cross(p, q, s), orientation * _cross(p, q, t)
        if first < 0 and last < 0:
            return True
        if first < 0:
            low = max(low, Q(-first, last - first))
        elif last < 0:
            high = min(high, Q(first, first - last))
        if low > high:
            return True
    if low < high:
        return False
    point = tuple(Q(x) + low * (y - x) for x, y in zip(s, t, strict=True))
    return point in {a, c}


class _State:
    """Bütün halkaların güncel kenarlarını ve değişmeyen kaynak indekslerini taşır."""

    def __init__(self, boundaries: list[Boundary]) -> None:
        self.boundaries = boundaries
        points = [p for b in boundaries for p in b.vertices]
        self.coords = np.asarray(points, dtype=np.int64)
        if (
            not points
            or len(points) > 20000
            or self.coords.shape != (len(points), 2)
            or not np.array_equal(self.coords, np.asarray(points))
            or np.any(self.coords < 0)
            or np.any(self.coords > 1_000_000)
        ):
            raise ValueError("Topoloji araması en çok 20.000 tamsayı piksel köşesini destekler.")
        self.points = [tuple(map(int, p)) for p in self.coords]
        self.active = np.ones(len(points), dtype=bool)
        self.previous = np.empty(len(points), dtype=int)
        self.following = np.empty(len(points), dtype=int)
        self.labels = np.empty(len(points), dtype=int)
        self.ranges = []
        offset = 0
        for i, boundary in enumerate(boundaries):
            n = len(boundary.vertices)
            if n < 3:
                raise ValueError("Her sınır en az üç köşe içermelidir.")
            ids = np.arange(offset, offset + n)
            self.previous[ids], self.following[ids] = np.roll(ids, 1), np.roll(ids, -1)
            self.labels[ids] = i
            self.ranges.append((offset, offset + n))
            offset += n
        self.counts = np.array([len(b.vertices) for b in boundaries])
        repetitions = Counter(self.points)
        self.protected = np.array([repetitions[p] > 1 for p in self.points])
        self.ends = self.coords[self.following].copy()
        self.low = np.minimum(self.coords, self.ends)
        self.high = np.maximum(self.coords, self.ends)

    def removable(self, vertex: int) -> bool:
        """Silmenin boş üçgen veya tam eşdoğrusal özdeşlik tanığını denetler."""
        if not 0 <= vertex < len(self.points) or not self.active[vertex]:
            return False
        label = self.labels[vertex]
        if self.counts[label] <= 3:
            return False
        left, right = int(self.previous[vertex]), int(self.following[vertex])
        a, b, c = (self.points[i] for i in (left, vertex, right))
        if a == c:
            return False
        if _cross(a, b, c) == 0:
            return all(min(x, z) <= y <= max(x, z) for x, y, z in zip(a, b, c, strict=True))
        if self.protected[vertex]:
            return False
        low, high = np.min([a, b, c], axis=0), np.max([a, b, c], axis=0)
        candidates = np.flatnonzero(
            self.active & np.all(self.high >= low, axis=1) & np.all(self.low <= high, axis=1)
        )
        for i in candidates:
            if i in {left, vertex}:
                continue
            if not _intersection_allowed(a, b, c, self.points[i], self.points[self.following[i]]):
                return False
        return True

    def remove(self, vertex: int) -> None:
        """Önceden doğrulanmış köşeyi bağlı listeden ve kenar kutularından kaldırır."""
        left, right = self.previous[vertex], self.following[vertex]
        self.following[left], self.previous[right] = right, left
        self.active[vertex] = False
        self.counts[self.labels[vertex]] -= 1
        self.ends[left] = self.coords[right]
        self.low[left] = np.minimum(self.coords[left], self.ends[left])
        self.high[left] = np.maximum(self.coords[left], self.ends[left])

    def chain(self, left: int, right: int) -> list[tuple]:
        """Yeni kirişin temsil edeceği sıralı orijinal alt zinciri döndürür."""
        start, stop = self.ranges[self.labels[left]]
        if left < right:
            return self.points[left : right + 1]
        return self.points[left:stop] + self.points[start : right + 1]

    def fits(self, vertex: int, tolerance: Q) -> bool:
        """Birikmiş silmeler dahil kaynak alt zincirin kiriş kapsamasını tam sınar."""
        left, right = self.previous[vertex], self.following[vertex]
        a, b = self.points[left], self.points[right]
        dx, dy = b[0] - a[0], b[1] - a[1]
        squared = dx * dx + dy * dy
        if not squared:
            return False
        limit = tolerance * tolerance
        for x, y in self.chain(left, right):
            px, py = x - a[0], y - a[1]
            projection = px * dx + py * dy
            if projection <= 0:
                distance = Q(px * px + py * py)
            elif projection >= squared:
                distance = Q((x - b[0]) ** 2 + (y - b[1]) ** 2)
            else:
                distance = Q((px * dy - py * dx) ** 2, squared)
            if distance > limit:
                return False
        return True

    def result(self) -> list[Boundary]:
        """Halka sırası ve kaynak dikişi korunmuş sadeleştirilmiş sınırları kurar."""
        return [
            Boundary(
                [self.points[i] for i in range(start, stop) if self.active[i]],
                b.kind,
                b.original_vertex_count,
            )
            for b, (start, stop) in zip(self.boundaries, self.ranges, strict=True)
        ]


def simplify_topology(
    boundaries: list[Boundary], tolerance: float, cancel: Event | None = None
) -> tuple[list[Boundary], dict]:
    """Temasları sabitleyip boş üçgenlerle güvenli köşe silmelerini açgözlü arar.

    tolerance çalışma birimidir. Her yeni kiriş, temsil ettiği bütün orijinal
    alt zincire karşı sınanır; tek adım hataları biriktirilmez. En çok üç
    tarama/8N teklif denenir. Sonuç küresel en az parça değildir. Silme sırası
    bağımsız olarak yeniden oynatılabilir topoloji tanığıdır.
    """
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Topoloji sadeleştirme toleransı pozitif ve sonlu olmalıdır.")
    state, removals = _State(boundaries), []
    versions = np.zeros(len(state.points), dtype=int)
    target = Q(float(tolerance))
    attempts = 0

    def priority(i: int) -> tuple:
        a, b, c = (
            state.coords[j].astype(float) for j in (state.previous[i], i, state.following[i])
        )
        d = c - a
        denominator = float(d @ d)
        u = float(np.clip((b - a) @ d / denominator, 0, 1)) if denominator else 0
        return float(np.linalg.norm(b - a - u * d)), i, int(versions[i])

    for _ in range(3):
        heap = [priority(int(i)) for i in np.flatnonzero(state.active)]
        heapq.heapify(heap)
        initial = len(removals)
        while heap and attempts < 8 * len(state.points):
            if cancel is not None and cancel.is_set():
                from .fitting import AnalysisCancelled

                raise AnalysisCancelled("Topoloji sadeleştirmesi iptal edildi.")
            error, vertex, version = heapq.heappop(heap)
            if not state.active[vertex] or versions[vertex] != version:
                continue
            attempts += 1
            if (
                error > tolerance * (1 + 1e-12)
                or not state.fits(vertex, target)
                or not state.removable(vertex)
            ):
                continue
            left, right = int(state.previous[vertex]), int(state.following[vertex])
            state.remove(vertex)
            removals.append(vertex)
            for neighbor in (left, right):
                versions[neighbor] += 1
                heapq.heappush(heap, priority(neighbor))
        if len(removals) == initial:
            break
    return state.result(), {
        "version": "empty_triangles_v1",
        "removed_vertices": removals,
        "reference_vertex_count": len(state.points),
        "proposal_tolerance": tolerance,
        "attempts": attempts,
        "protected_repeated_vertices": int(state.protected.sum()),
        "witness_payload_bits": 32 * len(removals),
    }


def verify_simplification(candidate: Candidate, boundaries: list[Boundary]) -> dict:
    """Kaynak indeksli silme tanığını baştan denetler ve son katsayılarla eşler.

    JSON başarı bayraklarına ve GEOS geçerlilik kararına güvenmez. Her boş
    üçgen kontrolü tam rasyonel, kutu elemesi sınırlı tamsayı aritmetiğidir.
    Noktasal temas ve yüz ilişkileri, sabit temas grafiğinin yerel düzlemsel
    izotopileriyle korunur. Geometrik hata ayrıca sertifikalanmalıdır.
    """
    witness = candidate.metrics.get("topology_witness", {})
    if not isinstance(witness, dict) or witness.get("version") != "empty_triangles_v1":
        raise ValueError("Topoloji sadeleştirme tanığının sürümü eksik veya geçersiz.")
    state = _State(boundaries)
    removed = witness.get("removed_vertices")
    if not isinstance(removed, list) or len(removed) > len(state.points):
        raise ValueError("Topoloji tanığının silme sayısı geçersiz.")
    for vertex in removed:
        if type(vertex) is not int or not state.removable(vertex):
            raise ValueError("Topoloji tanığında boş üçgen/temas koşulu sağlanmıyor.")
        state.remove(vertex)
    expected = []
    for i, b in enumerate(state.result()):
        expected.extend(
            (i, list(a), list(z))
            for a, z in zip(b.vertices, b.vertices[1:] + b.vertices[:1], strict=True)
        )
    if len(expected) != len(candidate.pieces) or any(
        p.kind != "line" or p.boundary_id != i or p.params["a"] != a or p.params["b"] != b
        for p, (i, a, b) in zip(candidate.pieces, expected, strict=True)
    ):
        raise ValueError("Topoloji tanığı son modelin katsayılarıyla eşleşmiyor.")
    return {
        "preserved": True,
        "reasons": [],
        "scope": "exact_planar_graph_isotopy_empty_triangles",
        "analytic_isotopy_proven": True,
        "verified_removals": len(removed),
    }
