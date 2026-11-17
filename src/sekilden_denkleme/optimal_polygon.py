"""Kapalı piksel sınırı için düğüm kısıtlı kesin en-az-kenar (min-#) çokgeni.

Problem (Imai–Iri min-# biçimi): sıralı kapalı nokta dizisi P ve τ>0 verilsin.
Köşeleri P'nin alt dizisi olan, her kirişi temsil ettiği alt zincirin bütün
noktalarına en çok τ uzakta kalan (kiriş kapsülü ölçütü) ve en az kenarlı
kapalı çokgen aranır. Kapsül ölçütü, alt zincir ile kiriş arasında simetrik
Hausdorff uzaklığının ≤ τ olmasına denktir (sürekli izdüşüm argümanı).

Geçerli kirişler Chan–Chin ışın kaması yöntemiyle O(n·D) işlemde bulunur:
p noktasının ab parçasına uzaklığı, a→b ve b→a ışınlarına uzaklıklarının
büyüğüdür. Kama testleri float64 ile τ'nun **üst kümesinde** yapılır; bulunan
en kısa çevrim tam rasyonel aritmetikle yeniden denetlenir. Denetim geçerse
alt sınır = üst sınır olur ve sonuç bu problem sınıfında kanıtlı optimumdur.

Bu, küresel topolojiyi veya eğri ailelerini kapsayan bir optimum değildir;
bütün şeklin topolojisi ve Hausdorff sertifikası ayrıca denetlenmelidir.
"""

from fractions import Fraction as Q

import numpy as np

from .models import Boundary

_MARGIN = 1e-6
_ANGLE_MARGIN = 1e-9


def node_sequence(boundary: Boundary, splits: int = 1) -> np.ndarray:
    """Halka köşelerini ve her kenarın splits-1 eşit aralıklı iç noktasını döndürür.

    splits=2 kenar orta noktalarını ekler. Tamsayı köşelerde bu noktalar dyadik
    değildir ancak splits ikinin kuvvetiyse binary64'te tamdır.
    """
    if splits < 1:
        raise ValueError("Bölme sayısı en az 1 olmalıdır.")
    v = np.asarray(boundary.vertices, dtype=float)
    if splits == 1:
        return v
    w = np.roll(v, -1, axis=0)
    steps = np.arange(splits) / splits
    return (v[:, None, :] + steps[None, :, None] * (w - v)[:, None, :]).reshape(-1, 2)


def _ray_valid(points: np.ndarray, tolerance: float) -> np.ndarray:
    """V[d-1, i]: p_i'den p_{i+d}'ye ışın, aradaki bütün noktalara ≤ τ⁺ uzaktadır.

    τ⁺ = τ + pay olduğundan sonuç gerçek geçerli kümenin üst kümesidir. Bütün
    kamalar boşaldığında döngü durur; dönen matrisin satır sayısı incelenen
    en büyük adımdır.
    """
    m = len(points)
    tol = tolerance + _MARGIN
    free = np.ones(m, dtype=bool)
    base = np.zeros(m)
    lo = np.full(m, -np.inf)
    hi = np.full(m, np.inf)
    rows = []
    index = np.arange(m)
    for d in range(1, m - 1):
        delta = points[(index + d) % m] - points
        radius = np.hypot(delta[:, 0], delta[:, 1])
        angle = np.arctan2(delta[:, 1], delta[:, 0])
        diff = np.where(free, 0.0, (angle - base + np.pi) % (2 * np.pi) - np.pi)
        rows.append((radius > 0) & (free | ((diff >= lo) & (diff <= hi))))
        constrained = radius > tol
        half = np.arcsin(np.minimum(1.0, tol / np.maximum(radius, tol))) + _ANGLE_MARGIN
        first = constrained & free
        base[first] = angle[first]
        lo[first], hi[first] = -half[first], half[first]
        later = constrained & ~free
        lo[later] = np.maximum(lo[later], diff[later] - half[later])
        hi[later] = np.minimum(hi[later], diff[later] + half[later])
        free &= ~constrained
        if not (free | (lo <= hi)).any():
            break
    return np.asarray(rows, dtype=bool)


def _edge_exact(points: np.ndarray, i: int, d: int, tolerance: float) -> bool:
    """Kirişin alt zincir noktalarına uzaklığını tam rasyonel aritmetikle sınar."""
    m = len(points)
    a = tuple(Q(float(x)) for x in points[i])
    b = tuple(Q(float(x)) for x in points[(i + d) % m])
    dx, dy = b[0] - a[0], b[1] - a[1]
    squared = dx * dx + dy * dy
    if not squared:
        return False
    limit = Q(float(tolerance)) ** 2
    for k in range(1, d):
        p = points[(i + k) % m]
        px, py = Q(float(p[0])) - a[0], Q(float(p[1])) - a[1]
        projection = px * dx + py * dy
        if projection <= 0:
            distance = px * px + py * py
        elif projection >= squared:
            distance = (px - dx) ** 2 + (py - dy) ** 2
        else:
            cross = px * dy - py * dx
            distance = cross * cross / squared
        if distance > limit:
            return False
    return True


def _shortest_cycle(steps: list[np.ndarray], m: int, start: int) -> list[int] | None:
    """start'tan bir tam tur atan en az kenarlı yolu (≥3 kenar) döndürür."""
    infinity = np.iinfo(np.int32).max
    distance = np.full(m + 1, infinity, dtype=np.int32)
    previous = np.full(m + 1, -1, dtype=np.int64)
    distance[0] = 0
    for p in range(m):
        if distance[p] == infinity:
            continue
        d = steps[(start + p) % m]
        target = p + d[d <= m - p]
        better = distance[target] > distance[p] + 1
        distance[target[better]] = distance[p] + 1
        previous[target[better]] = p
    if distance[m] == infinity:
        return None
    if distance[m] < 3:
        # Çok küçük halka: tam k kenarlı katmanlarla en az üç kenarlı tur aranır.
        layers = [{0: None}]
        for _ in range(8):
            following = {}
            for p in layers[-1]:
                if p == m:
                    continue
                d = steps[(start + p) % m]
                for t in (p + d[d <= m - p]).tolist():
                    following.setdefault(t, p)
            layers.append(following)
            if len(layers) > 3 and m in following:
                path, position = [], m
                for layer in layers[:0:-1]:
                    position = layer[position]
                    path.append(position)
                return [(start + p) % m for p in path[::-1]]
        return None
    path, position = [], m
    while position:
        position = int(previous[position])
        path.append(position)
    return [(start + p) % m for p in path[::-1]]


def min_link_ring(points: np.ndarray, tolerance: float, max_nodes: int = 40000) -> dict:
    """Sıralı kapalı nokta dizisinde düğüm kısıtlı en az kenarlı çokgeni bulur.

    Returns:
        nodes: seçilen düğüm indeksleri (artan çevrim sırası);
        lower_bound: τ için kanıtlı alt sınır (üst küme grafiğinin en kısa turu);
        optimal: seçilen turun bütün kirişleri tam aritmetikte geçerliyse True.
        optimal False ise nodes, τ-pay ile kurulan güvenli grafiğin turudur.
    """
    points = np.asarray(points, dtype=float)
    m = len(points)
    if m < 3 or points.shape != (m, 2) or not np.isfinite(points).all():
        raise ValueError("Min-# araması en az üç sonlu düzlem noktası gerektirir.")
    if m > max_nodes:
        raise ValueError(f"Min-# araması {max_nodes} düğüm sınırını aştı.")
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Min-# toleransı pozitif ve sonlu olmalıdır.")

    def solve(tol: float) -> list[int] | None:
        forward = _ray_valid(points, tol)
        backward = _ray_valid(points[::-1], tol)
        depth = min(len(forward), len(backward))
        index = np.arange(m)
        valid = np.empty((depth, m), dtype=bool)
        for d in range(1, depth + 1):
            valid[d - 1] = forward[d - 1] & backward[d - 1][m - 1 - (index + d) % m]
        steps = [np.flatnonzero(valid[:, i]) + 1 for i in range(m)]
        longest = np.array([s[-1] if len(s) else 0 for s in steps])
        if not longest.all():
            return None
        # Her tur, hiçbir geçerli kirişin üzerinden atlayamadığı pencereye uğrar.
        window = np.ones(m, dtype=np.int64)
        for k in range(1, int(longest.max()) + 1):
            window = np.maximum(window, 1 + np.roll(longest, k) - k)
        first = int(np.argmin(window))
        best = None
        for start in range(first, first + int(window[first])):
            cycle = _shortest_cycle(steps, m, start % m)
            if cycle is not None and (best is None or len(cycle) < len(best)):
                best = cycle
        return best

    cycle = solve(tolerance)
    if cycle is None:
        raise ValueError("Min-# grafiğinde kapalı tur bulunamadı.")
    lower = len(cycle)

    def exact(nodes: list[int]) -> bool:
        return all(
            _edge_exact(points, a, (b - a) % m or m, tolerance)
            for a, b in zip(nodes, nodes[1:] + nodes[:1], strict=True)
        )

    optimal = exact(cycle)
    if not optimal:
        safe = solve(max(tolerance - 2 * _MARGIN, tolerance / 2))
        if safe is None or not exact(safe):
            raise ValueError("Min-# sonucu tam aritmetikte doğrulanamadı.")
        cycle = safe
    return {
        "nodes": sorted(cycle),
        "edge_count": len(cycle),
        "lower_bound": lower,
        "optimal": optimal,
        "node_count": m,
        "tolerance": float(tolerance),
    }


def _shortcut_steps(points: np.ndarray, tolerance: float) -> list[np.ndarray]:
    """Her düğümden çıkan τ⁺-geçerli kiriş adımlarını (üst küme) döndürür."""
    m = len(points)
    forward = _ray_valid(points, tolerance)
    backward = _ray_valid(points[::-1], tolerance)
    depth = min(len(forward), len(backward))
    index = np.arange(m)
    valid = np.empty((depth, m), dtype=bool)
    for d in range(1, depth + 1):
        valid[d - 1] = forward[d - 1] & backward[d - 1][m - 1 - (index + d) % m]
    return [np.flatnonzero(valid[:, i]) + 1 for i in range(m)]


def _best_cycle(steps: list[np.ndarray], m: int) -> list[int] | None:
    """Verilen kiriş grafiğinde en az kenarlı kapalı turu (artan düğüm sırası) bulur."""
    longest = np.array([s[-1] if len(s) else 0 for s in steps])
    if not longest.all():
        return None
    window = np.ones(m, dtype=np.int64)
    for k in range(1, int(longest.max()) + 1):
        window = np.maximum(window, 1 + np.roll(longest, k) - k)
    first = int(np.argmin(window))
    best = None
    for start in range(first, first + int(window[first])):
        cycle = _shortest_cycle(steps, m, start % m)
        if cycle is not None and (best is None or len(cycle) < len(best)):
            best = cycle
    return sorted(best) if best is not None else None


def _rational(point: np.ndarray) -> tuple[Q, Q]:
    return Q(float(point[0])), Q(float(point[1]))


def _point_segment_squared(p: tuple, a: tuple, b: tuple) -> Q:
    dx, dy = b[0] - a[0], b[1] - a[1]
    px, py = p[0] - a[0], p[1] - a[1]
    squared = dx * dx + dy * dy
    projection = px * dx + py * dy
    if projection <= 0:
        return px * px + py * py
    if projection >= squared:
        return (px - dx) ** 2 + (py - dy) ** 2
    cross = px * dy - py * dx
    return cross * cross / squared


def _segments_squared(a: tuple, b: tuple, c: tuple, d: tuple) -> Q:
    """İki kapalı doğru parçası arasındaki uzaklığın karesi (tam rasyonel)."""

    def side(p: tuple, q: tuple, r: tuple) -> int:
        value = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (value > 0) - (value < 0)

    if side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0:
        return Q(0)
    return min(
        _point_segment_squared(a, c, d),
        _point_segment_squared(b, c, d),
        _point_segment_squared(c, a, b),
        _point_segment_squared(d, a, b),
    )


def _segments_near(
    a: np.ndarray, b: np.ndarray, p: np.ndarray, q: np.ndarray, limit: float
) -> np.ndarray:
    """a[k]b[k] parçalarından pq parçasına uzaklığı kesinlikle ≤ limit olanlar.

    binary64 ön elemedir: limit, çağıran tarafından güvenlik payı kadar
    küçültülür; sınırdaki parçalar dışarıda kalır (alt küme döner).
    """

    def clamp(w: np.ndarray, d: np.ndarray) -> np.ndarray:
        squared = np.maximum(np.sum(d * d, axis=-1), 1e-300)
        t = np.clip(np.sum(w * d, axis=-1) / squared, 0.0, 1.0)
        rest = w - t[..., None] * d
        return np.hypot(rest[..., 0], rest[..., 1])

    distance = np.minimum(
        np.minimum(clamp(p - a, b - a), clamp(q - a, b - a)),
        np.minimum(clamp(a - p, (q - p)[None, :]), clamp(b - p, (q - p)[None, :])),
    )

    def cross(u: np.ndarray, v: np.ndarray) -> np.ndarray:
        return u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]

    s1, s2 = cross(b - a, p - a), cross(b - a, q - a)
    s3, s4 = cross(q - p, a - p), cross(q - p, b - p)
    sure = np.minimum(np.minimum(abs(s1), abs(s2)), np.minimum(abs(s3), abs(s4))) > 1e-6
    crossing = sure & (s1 * s2 < 0) & (s3 * s4 < 0)
    return (distance <= limit) | crossing


def _half(v: tuple) -> int:
    return 0 if (v[1] > 0 or (v[1] == 0 and v[0] > 0)) else 1


def _angle_compare(u: tuple, v: tuple) -> int:
    if _half(u) != _half(v):
        return _half(u) - _half(v)
    cross = u[0] * v[1] - u[1] * v[0]
    return -1 if cross > 0 else (1 if cross < 0 else 0)


def _find_conflict(
    rings: list[np.ndarray],
    cycles: list[list[int]],
    clearance: float,
    contacts: frozenset = frozenset(),
    closed: bool = True,
    wedges: bool = True,
) -> tuple[tuple[int, int, int], ...] | None:
    """Kısıtları bozan ilk kenar kümesini (halka, düğüm, adım) olarak verir.

    closed=False ise her düğüm listesi açık bir yoldur (son→ilk kenarı yoktur);
    wedges=False temas noktalarındaki dönme denetimini atlar. Bu ikisi, tek bir
    yayın kendi içindeki çakışmalarını aramak için kullanılır.

    Komşu olmayan iki kenar arasındaki tam uzaklık ≤ açıklık ise çakışmadır.
    Aynı halkada ardışık iki kenar yalnızca geri katlanırsa (sıfır açı) çakışır.
    Ortak bir temas noktasında buluşan kenarlar açıklıktan muaftır; orada iki
    geçişin ışınları çakışmamalı ve çevrimsel sırada iç içe geçmemelidir.
    """
    from functools import cmp_to_key

    edges, a, b = [], [], []
    for r, (points, cycle) in enumerate(zip(rings, cycles, strict=True)):
        m, count = len(points), len(cycle) - (not closed)
        for k in range(count):
            i, j = cycle[k], cycle[(k + 1) % len(cycle)]
            edges.append((r, i, (j - i) % m or m, k, count))
            a.append(points[i])
            b.append(points[j])
    a, b = np.asarray(a), np.asarray(b)
    lo, hi = np.minimum(a, b) - clearance, np.maximum(a, b) + clearance
    limit = Q(float(clearance)) ** 2
    for i in range(len(edges)):
        near = np.flatnonzero(
            np.all(hi[i] >= lo[i + 1 :], axis=1) & np.all(hi[i + 1 :] >= lo[i], axis=1)
        )
        for j in (near + i + 1).tolist():
            r, _, _, k, count = edges[i]
            s, _, _, n, _ = edges[j]
            p, q, u, v = _rational(a[i]), _rational(b[i]), _rational(a[j]), _rational(b[j])
            if r == s and (n - k == 1 or (closed and (k - n) % count == 1)):
                # x→y→z ardışık köşeler; z, y'den x'e doğru geri katlanıyor mu?
                x, y, z = (p, q, v) if n - k == 1 else (u, v, q)
                ex, ey = y[0] - x[0], y[1] - x[1]
                fx, fy = z[0] - y[0], z[1] - y[1]
                if ex * fy - ey * fx == 0 and ex * fx + ey * fy < 0:
                    return edges[i][:3], edges[j][:3]
                continue
            if contacts and ({p, q} & {u, v} & contacts):
                continue
            if _segments_squared(p, q, u, v) <= limit:
                return edges[i][:3], edges[j][:3]
    if not contacts or not wedges:
        return None
    # Temas noktalarında dönme denetimi: her geçişin (gelen, giden) kenarı.
    passes: dict[tuple, list] = {}
    offset = 0
    for points, cycle in zip(rings, cycles, strict=True):
        count = len(cycle)
        for k, node in enumerate(cycle):
            vertex = _rational(points[node])
            if vertex in contacts:
                passes.setdefault(vertex, []).append((offset + (k - 1) % count, offset + k))
        offset += count
    for vertex, items in passes.items():
        for x in range(len(items)):
            for y in range(x):
                rays = []
                for owner, (incoming, outgoing) in ((0, items[x]), (1, items[y])):
                    for edge, far in ((incoming, a[incoming]), (outgoing, b[outgoing])):
                        other = _rational(far)
                        rays.append(((other[0] - vertex[0], other[1] - vertex[1]), owner, edge))
                rays.sort(key=cmp_to_key(lambda g, h: _angle_compare(g[0], h[0])))
                owners = [owner for _, owner, _ in rays]
                tie = any(
                    _angle_compare(g[0], h[0]) == 0
                    for g, h in zip(rays, rays[1:] + rays[:1], strict=True)
                )
                if tie or owners in ([0, 1, 0, 1], [1, 0, 1, 0]):
                    return tuple(edges[edge][:3] for _, _, edge in rays)
    return None


def constrained_min_link(
    rings: list[np.ndarray],
    tolerance: float,
    clearance: float = 0.25,
    max_search_nodes: int = 300,
    max_nodes: int = 40000,
    preserve_contacts: bool = True,
) -> dict:
    """Bütün halkalar için birlikte, açıklık kısıtlı en az kenarlı çokgenleri arar.

    Sınıf: her halkada düğüm kısıtlı, her kirişi τ-geçerli kapalı çokgen; komşu
    olmayan her kenar çifti arasında uzaklık > açıklık (dolayısıyla çokgenler
    basit ve ikişer ayrıktır). Yöntem dal-sınırdır: gevşetme, halkaların
    bağımsız en kısa turlarıdır; bir çakışan kenar çifti (e, f) bulunduğunda
    "e yasak" ve "f yasak" dalları açılır. Hiçbir uygun çözüm ikisini birlikte
    içermediğinden dallanma tamdır. Tam aritmetikte geçersiz çıkan kirişler
    dallanmadan kalıcı olarak silinir.

    Returns:
        cycles: halka başına düğüm indeksleri; edge_count; lower_bound (kanıtlı);
        optimal: arama tamamlandıysa True; feasible: açıklık koşulu sağlandı mı;
        unconstrained_edge_count, search_nodes, branchings.
    """
    import heapq

    rings = [np.asarray(points, dtype=float) for points in rings]
    if not np.isfinite(tolerance) or tolerance <= 0 or clearance < 0:
        raise ValueError("Min-# toleransı pozitif, açıklık negatif olmayan sonlu sayı olmalıdır.")
    for points in rings:
        m = len(points)
        if m < 3 or points.shape != (m, 2) or not np.isfinite(points).all():
            raise ValueError("Min-# araması en az üç sonlu düzlem noktası gerektirir.")
        if m > max_nodes:
            raise ValueError(f"Min-# araması {max_nodes} düğüm sınırını aştı.")
    base = [_shortcut_steps(points, tolerance) for points in rings]
    free = list(base)
    # Temas noktaları: birden çok kez geçen düğüm koordinatları. Bu düğümler
    # zorunlu köşedir; üzerlerinden atlayan kirişler grafikten çıkarılır.
    contacts: frozenset = frozenset()
    if preserve_contacts:
        seen, repeated = set(), set()
        for points in rings:
            for point in points:
                key = _rational(point)
                (repeated if key in seen else seen).add(key)
        contacts = frozenset(repeated)
    # Birimler: ardışık iki sabit düğüm arasındaki yay (halka, başlangıç, uzunluk,
    # ilmek mi); sabit düğümü olmayan halka tek birimdir (başlangıç None).
    # İlmek: iki ucu aynı noktada olan yay. Tek veya iki kenarlı her ilmek
    # yozdur (sıfır uzunluk ya da geri katlanma), bu yüzden en az üç kenar ister.
    units: list[tuple[int, int | None, int, bool]] = []
    unit_of: list[np.ndarray] = []
    members: list[list[int]] = []
    for r, points in enumerate(rings):
        m = len(points)
        pinned = [i for i in range(m) if _rational(points[i]) in contacts]
        owner = np.full(m, len(units), dtype=np.int64)
        members.append([])
        if not pinned:
            members[r].append(len(units))
            units.append((r, None, m, False))
        else:
            reach = np.empty(m, dtype=np.int64)
            for position, i in enumerate(pinned):
                following = pinned[(position + 1) % len(pinned)]
                span = (following - i) % m or m
                offsets = (i + np.arange(span)) % m
                reach[offsets] = span - np.arange(span)
                owner[offsets] = len(units)
                members[r].append(len(units))
                loop = _rational(points[i]) == _rational(points[following])
                units.append((r, i, span, loop))
            base[r] = [steps[steps <= reach[i]] for i, steps in enumerate(base[r])]
        unit_of.append(owner)
    invalid: list[set] = [set() for _ in rings]
    exact_cache: dict[tuple[int, int, int], bool] = {}
    relaxed_cache: dict[tuple[int, frozenset], list[int] | None] = {}
    local_cache: dict[tuple[int, frozenset], list[int] | None] = {}
    local_limit = 20 * max_search_nodes
    counts = {"local": 0, "branchings": 0}

    def shortest(u: int, removed: dict, graph: list[np.ndarray]) -> list[int] | None:
        """Birimin grafiğinde en az kenarlı tur (kapalı) ya da yol (yay)."""
        r, start, span, loop = units[u]
        m = len(rings[r])

        def out(i: int) -> np.ndarray:
            steps = graph[i]
            return steps[~np.isin(steps, removed[i])] if i in removed else steps

        if start is None:
            return _best_cycle([out(i) for i in range(m)], m)
        need = 3 if loop else 1
        infinity = np.iinfo(np.int32).max
        distance = np.full((need, span + 1), infinity, dtype=np.int32)
        previous = np.full((need, span + 1, 2), -1, dtype=np.int64)
        distance[0, 0] = 0
        best, last = infinity, None
        for o in range(span):
            steps = None
            for layer in range(need):
                value = distance[layer, o]
                if value == infinity:
                    continue
                if steps is None:
                    steps = o + out((start + o) % m)
                    steps = steps[steps <= span]
                    inner = steps[steps < span]
                    closes = len(steps) > len(inner)
                following = min(layer + 1, need - 1)
                better = inner[distance[following, inner] > value + 1]
                distance[following, better] = value + 1
                previous[following, better] = (o, layer)
                if closes and layer == need - 1 and value + 1 < best:
                    best, last = value + 1, (o, layer)
        if last is None:
            return None
        path = [span]
        while last[0] or last[1]:
            path.append(int(last[0]))
            last = tuple(previous[last[1], last[0]])
        path.append(0)
        return [(start + o) % m for o in path[::-1]]

    def edges_of(u: int, nodes: list[int]) -> list[tuple[int, int]]:
        m = len(rings[units[u][0]])
        following = nodes[1:] + nodes[:1] if units[u][1] is None else nodes[1:]
        pairs = zip(nodes, following, strict=False)
        return [(i, (j - i) % m or m) for i, j in pairs]

    def relaxed(u: int, forbidden: frozenset, graph: list[np.ndarray] | None = None):
        """Yasaklı ve tam aritmetikte geçersiz kirişler olmadan birimin en kısası."""
        key = (u, forbidden)
        if graph is None and key in relaxed_cache:
            return relaxed_cache[key]
        r = units[u][0]
        while True:
            removed: dict[int, list[int]] = {}
            for i, d in forbidden | invalid[r]:
                removed.setdefault(i, []).append(d)
            nodes = shortest(u, removed, base[r] if graph is None else graph)
            if nodes is None:
                break
            bad = False
            for i, d in edges_of(u, nodes):
                if (r, i, d) not in exact_cache:
                    exact_cache[r, i, d] = _edge_exact(rings[r], i, d, tolerance)
                if not exact_cache[r, i, d]:
                    invalid[r].add((i, d))
                    bad = True
            if not bad:
                break
        if graph is None:
            relaxed_cache[key] = nodes
        return nodes

    def local(u: int, forbidden: frozenset) -> list[int] | None:
        """Birimin kendi içinde çakışmasız en kısa çözümü (iç dal-sınır).

        Yalnız bu birimin kenarları arasındaki açıklık ve geri katlanma
        çakışmaları çözülür; uygun her aile bunları sağlamak zorundadır, bu
        yüzden sonuç geçerli bir alt sınırdır. İç bütçe biterse çakışmalı
        gevşetme döner ve dış arama aynı çakışmada dallanır.
        """
        key = (u, forbidden)
        if key in local_cache:
            return local_cache[key]
        r, start, _, _ = units[u]
        result = relaxed(u, forbidden)
        if result is not None:
            tick = 0
            heap = [(len(edges_of(u, result)), tick, forbidden)]
            visited = {forbidden}
            while heap:
                _, _, current = heapq.heappop(heap)
                result = relaxed(u, current)
                if counts["local"] >= local_limit:
                    break
                counts["local"] += 1
                conflict = _find_conflict(
                    [rings[r]], [result], clearance, contacts, start is None, False
                )
                if conflict is None:
                    break
                counts["branchings"] += 1
                result = None
                for group in branches(tuple((r, i, d) for _, i, d in conflict)):
                    child = current | {(i, d) for _, i, d in group if unit_of[r][i] == u}
                    if child in visited:
                        continue
                    visited.add(child)
                    option = relaxed(u, child)
                    if option is not None:
                        tick += 1
                        heapq.heappush(heap, (len(edges_of(u, option)), tick, child))
        local_cache[key] = result
        return result

    shortcut_cache: dict[int, tuple] = {}

    def blockers(kept: tuple[int, int, int], r: int) -> list[tuple[int, int, int]]:
        """r halkasında, kept kenarıyla aynı uygun ailede bulunamayan kirişler."""
        ring, i, d = kept
        size = len(rings[ring])
        p, q = rings[ring][i], rings[ring][(i + d) % size]
        if r not in shortcut_cache:
            m = len(rings[r])
            starts = np.repeat(np.arange(m), [len(steps) for steps in base[r]])
            steps = np.concatenate(base[r])
            shortcut_cache[r] = (starts, steps, rings[r][starts], rings[r][(starts + steps) % m])
        starts, steps, a, b = shortcut_cache[r]
        near = _segments_near(a, b, p, q, clearance - 1e-7)
        if r == ring:
            # Kenarın kendisi ve onunla ardışık olabilecek kirişler muaftır.
            near &= ~((starts == i) & (steps == d))
            near &= ((starts + steps) % size != i) & (starts != (i + d) % size)
        for point in (p, q):
            if _rational(point) in contacts:
                near &= ~(np.all(a == point, axis=1) | np.all(b == point, axis=1))
        return [(r, int(x), int(y)) for x, y in zip(starts[near], steps[near], strict=True)]

    def branches(conflict: tuple) -> list[list[tuple[int, int, int]]]:
        """Çakışmayı kapsayan dallar: her dal yasaklanacak kirişlerin listesidir.

        Açıklık çakışmasında (e, f): uygun bir aile ya f'yi içermez ya da f ile
        çakışan hiçbir kirişi içermez. Böylece bir dal tek kirişi, öbürü f'nin
        bütün engellediklerini yasaklar. Geri katlanma ve temas kamalarında
        dal başına tek kiriş yasaklanır.
        """
        if len(conflict) == 2:
            e, f = conflict
            m = len(rings[e[0]])
            folded = e[0] == f[0] and ((e[1] + e[2]) % m == f[1] or (f[1] + f[2]) % m == e[1])
            if not folded:
                against_f = set(blockers(f, e[0])) | {e}
                against_e = set(blockers(e, f[0])) | {f}
                if len(against_f) >= len(against_e):
                    return [sorted(against_f), [f]]
                return [sorted(against_e), [e]]
        return [[edge] for edge in conflict]

    def assemble(parts: list[list[int] | None]) -> list[list[int]]:
        cycles = []
        for r in range(len(rings)):
            nodes = []
            for u in members[r]:
                nodes.extend(parts[u] if units[u][1] is None else parts[u][:-1])
            first = nodes.index(min(nodes))
            cycles.append(nodes[first:] + nodes[:first])
        return cycles

    def cost(u: int, nodes: list[int]) -> int:
        return len(nodes) - (units[u][1] is not None)

    empty = tuple(frozenset() for _ in units)
    root = [local(u, empty[u]) for u in range(len(units))]
    if any(nodes is None for nodes in root):
        raise ValueError("Min-# grafiğinde kapalı tur bulunamadı.")
    # Karşılaştırma için: temas ve açıklık kısıtı olmayan halka bazlı optimum.
    ringwise = 0
    for r in range(len(rings)):
        if units[members[r][0]][1] is None:
            nodes = relaxed(members[r][0], frozenset())
        else:
            units.append((r, None, len(rings[r]), False))
            nodes = relaxed(len(units) - 1, frozenset(), free[r])
            units.pop()
        ringwise += len(nodes)
    unconstrained = sum(cost(u, nodes) for u, nodes in enumerate(root))
    counter = 0
    heap = [(unconstrained, counter, empty)]
    seen = {empty}
    incumbent, incumbent_cost = None, None
    lower, search_nodes, complete = unconstrained, 0, True
    while heap:
        bound, _, forbidden = heapq.heappop(heap)
        if incumbent_cost is not None and bound >= incumbent_cost:
            break
        if search_nodes >= max_search_nodes:
            complete = False
            lower = bound
            break
        search_nodes += 1
        parts = [local(u, forbidden[u]) for u in range(len(units))]
        cycles = assemble(parts)
        conflict = _find_conflict(rings, cycles, clearance, contacts)
        if conflict is None:
            incumbent, incumbent_cost = cycles, bound
            continue
        counts["branchings"] += 1
        for group in branches(conflict):
            added: dict[int, set] = {}
            for r, i, d in group:
                added.setdefault(int(unit_of[r][i]), set()).add((i, d))
            child = tuple(f | added[u] if u in added else f for u, f in enumerate(forbidden))
            if child in seen:
                continue
            seen.add(child)
            options = {u: local(u, child[u]) for u in added}
            if any(option is None for option in options.values()):
                continue
            value = bound + sum(cost(u, o) - cost(u, parts[u]) for u, o in options.items())
            if incumbent_cost is None or value < incumbent_cost:
                # Eşit maliyette en yeni düğüm önce: derinlemesine ilerler.
                counter -= 1
                heapq.heappush(heap, (value, counter, child))
    if incumbent is not None and complete:
        lower = incumbent_cost
    elif incumbent is None and complete:
        # Sınıf boş: gevşetilmiş çözüm döner, uygunluk iddia edilmez.
        lower = unconstrained
    feasible = incumbent is not None
    chosen = incumbent if feasible else assemble(root)
    return {
        "cycles": chosen,
        "edge_count": sum(len(cycle) for cycle in chosen),
        "lower_bound": int(lower),
        "optimal": bool(feasible and complete),
        "feasible": feasible,
        "unconstrained_edge_count": unconstrained,
        "ringwise_edge_count": ringwise,
        "search_nodes": search_nodes + counts["local"],
        "branchings": counts["branchings"],
        "node_count": sum(len(points) for points in rings),
        "tolerance": float(tolerance),
        "clearance": float(clearance),
        "contact_points": len(contacts),
        "units": len(units),
    }


def min_link_boundaries(
    boundaries: list[Boundary],
    tolerance: float,
    splits: int = 1,
    clearance: float = 0.25,
    max_search_nodes: int = 300,
) -> tuple[list[Boundary], dict]:
    """Bütün halkaların açıklık kısıtlı ortak min-# çokgenlerini döndürür."""
    points = [node_sequence(boundary, splits) for boundary in boundaries]
    result = constrained_min_link(points, tolerance, clearance, max_search_nodes)
    result["splits"] = splits
    simplified = [
        Boundary(
            [tuple(map(float, nodes[i])) for i in cycle],
            boundary.kind,
            boundary.original_vertex_count,
        )
        for boundary, nodes, cycle in zip(boundaries, points, result["cycles"], strict=True)
    ]
    return simplified, result


def min_link_boundary(
    boundary: Boundary, tolerance: float, splits: int = 1
) -> tuple[Boundary, dict]:
    """Halkanın düğüm kısıtlı min-# çokgenini ve optimallik kaydını döndürür."""
    points = node_sequence(boundary, splits)
    result = min_link_ring(points, tolerance)
    result["splits"] = splits
    vertices = [tuple(map(float, points[i])) for i in result["nodes"]]
    return Boundary(vertices, boundary.kind, boundary.original_vertex_count), result
