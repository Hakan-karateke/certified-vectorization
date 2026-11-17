"""Nokta temaslı referanslarda çokgen modelleri için tam rasyonel topoloji sertifikası.

Referans halkalar piksel köşelerinde birbirine (veya kendine) dokunabilir; bu
durumda halkalar ayrık Jordan eğrileri değildir ve Bernstein/Jordan yeter
koşulları uygulanamaz. Burada referans Γ ve çokgen modeli M, köşeleri temas
noktaları olan düzlem çizgeleri olarak ele alınır ve şu koşullar yalnızca tam
rasyonel aritmetikle sınanır:

1. Her halkada temas noktalarının çevrimsel dizisi Γ ve M'de aynıdır.
2. Her temas noktasında, gelen/giden ışınların etiketli çevrimsel sırası
   (dönme sistemi) Γ ve M'de aynıdır ve hiçbir iki ışın çakışmaz.
3. M'nin komşu olmayan kenarları, ortak bir temas ucu dışında kesişmez; komşu
   kenarlar geri katlanmaz.
4. Temasla bağlı her halka bileşeninin sınırsız yüzü ve öbür bileşenlerin her
   birini içeren yüzü Γ ve M'de aynıdır. Yüzler, dönme sisteminden çıkarılan
   (yay, sol/sağ) sınıflarıyla adlandırılır.

Koşul 4 yalnız alan işareti ve içeren halka ile değiştirilemez: temasla halka
biçiminde dizilmiş üç diskte, ortadaki yüz ile dış yüz yer değiştirdiğinde
dönme sistemi, alan işaretleri ve içerilme aynı kalır ama düzlem gömülmesi
değişir (tests/test_constrained_polygon.py içindeki karşı örnek).

Koşullar sağlanırsa iki düzlem çizgesi aynı dönme sistemine, aynı dış yüzlere
ve aynı yüz içerilmesine sahiptir; dolayısıyla Γ'yı M'ye halka halka taşıyan,
yönü koruyan bir düzlem homeomorfizması vardır. Koşullar yeterdir; sağlanmaması topolojinin
bozulduğunu göstermez.
"""

from fractions import Fraction as Q
from functools import cmp_to_key
from itertools import product

Point = tuple[Q, Q]


def _half(v: Point) -> int:
    return 0 if (v[1] > 0 or (v[1] == 0 and v[0] > 0)) else 1


def _compare(u: Point, v: Point) -> int:
    """Yönleri [0, 2π) açısına göre tam aritmetikle karşılaştırır."""
    if _half(u) != _half(v):
        return _half(u) - _half(v)
    cross = u[0] * v[1] - u[1] * v[0]
    return -1 if cross > 0 else (1 if cross < 0 else 0)


def _rotation(rings: dict[int, list[Point]], contacts: set[Point]) -> dict | None:
    """Her temas noktasında etiketli ışınların çevrimsel sırasını çıkarır."""
    rays: dict[Point, list] = {}
    for ring, vertices in rings.items():
        count, occurrence = len(vertices), 0
        for k, vertex in enumerate(vertices):
            if vertex not in contacts:
                continue
            for label, other in (("in", vertices[k - 1]), ("out", vertices[(k + 1) % count])):
                direction = (other[0] - vertex[0], other[1] - vertex[1])
                if direction == (0, 0):
                    return None
                rays.setdefault(vertex, []).append((direction, (ring, occurrence, label)))
            occurrence += 1
    system = {}
    for vertex, items in rays.items():
        items.sort(key=cmp_to_key(lambda a, b: _compare(a[0], b[0])))
        if any(
            _compare(a[0], b[0]) == 0 for a, b in zip(items, items[1:] + items[:1], strict=True)
        ):
            return None
        labels = [label for _, label in items]
        start = labels.index(min(labels))
        system[vertex] = labels[start:] + labels[:start]
    return system


def _canonical(vertices: list[Point], contacts: set[Point]) -> list[list[Point]]:
    """Köşe listesinin, temas dizisinin en küçük dönüşüyle başlayan bütün dönüşleri.

    Temas içermeyen halka olduğu gibi kalır. Temas dizisi kendi dönüşüne eşitse
    (örneğin aynı noktadan iki kez geçen halka) birden çok aday döner; bunların
    her biri halkayı kendine taşıyan geçerli bir yeniden etiketlemedir.
    """
    positions = [k for k, v in enumerate(vertices) if v in contacts]
    if not positions:
        return [vertices]
    sequence = [vertices[k] for k in positions]
    rotations = [sequence[i:] + sequence[:i] for i in range(len(sequence))]
    best = min(rotations)
    return [
        vertices[positions[i] :] + vertices[: positions[i]]
        for i, rotation in enumerate(rotations)
        if rotation == best
    ]


def _contact_sequence(vertices: list[Point], contacts: set[Point]) -> list[Point]:
    return [v for v in vertices if v in contacts]


def _side(p: Point, q: Point, r: Point) -> int:
    value = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (value > 0) - (value < 0)


def _on_segment(p: Point, q: Point, r: Point) -> bool:
    return (
        _side(p, q, r) == 0
        and min(p[0], q[0]) <= r[0] <= max(p[0], q[0])
        and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])
    )


def _intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Kapalı doğru parçalarının ortak noktası var mı (tam rasyonel)."""
    if _side(a, b, c) * _side(a, b, d) < 0 and _side(c, d, a) * _side(c, d, b) < 0:
        return True
    return (
        _on_segment(a, b, c) or _on_segment(a, b, d) or _on_segment(c, d, a) or _on_segment(c, d, b)
    )


def _edges_embedded(rings: dict[int, list[Point]], contacts: set[Point]) -> bool:
    edges = []
    for ring, vertices in rings.items():
        count = len(vertices)
        if count < 3:
            return False
        for k in range(count):
            a, b, c = vertices[k - 1], vertices[k], vertices[(k + 1) % count]
            if a == b:
                return False
            # Ardışık kenarlar geri katlanmamalı.
            ex, ey, fx, fy = b[0] - a[0], b[1] - a[1], c[0] - b[0], c[1] - b[1]
            if ex * fy - ey * fx == 0 and ex * fx + ey * fy <= 0:
                return False
            edges.append((ring, k, count, b, c))
    boxes = [
        (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        for _, _, _, a, b in edges
    ]
    order = sorted(range(len(edges)), key=lambda i: boxes[i][0])
    for position, i in enumerate(order):
        ring, k, count, a, b = edges[i]
        for j in order[position + 1 :]:
            if boxes[j][0] > boxes[i][2]:
                break
            if boxes[j][1] > boxes[i][3] or boxes[i][1] > boxes[j][3]:
                continue
            other, n, _, c, d = edges[j]
            if ring == other and ((n - k) % count == 1 or (k - n) % count == 1):
                continue
            shared = {a, b} & {c, d}
            if shared:
                # Ortak uç yalnızca temas noktası olabilir; yön ayrılığı dönme
                # sistemi denetiminde kanıtlanmıştır, başka ortak nokta kalmaz.
                if len(shared) != 1 or not shared <= contacts:
                    return False
                continue
            if _intersect(a, b, c, d):
                return False
    return True


def _groups(rings: dict[int, list[Point]], contacts: set[Point]) -> list[list[int]]:
    """Ortak temas noktasıyla bağlı halka bileşenleri."""
    owner: dict[Point, int] = {}
    parent = {i: i for i in rings}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, vertices in rings.items():
        for vertex in vertices:
            if vertex in contacts:
                parent[find(i)] = find(owner.setdefault(vertex, i))
    groups: dict[int, list[int]] = {}
    for i in sorted(rings):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _faces(system: dict, passes: dict[int, int]):
    """Dönme sisteminden yüz sınıflarını kurar; (halka, yay, kenar) → sınıf temsilcisi.

    Yay k, halkanın k. temas geçişinden sonrakine kadar olan parçasıdır; kenar
    0 yayın solu, 1 sağıdır. Bir temas noktasında ardışık iki ışın arasındaki
    açı tek bir yüzün köşesidir: ilk ışının saat yönü tersindeki kenarı ile
    ikincinin saat yönündeki kenarı aynı yüzdedir.
    """
    parent: dict[tuple, tuple] = {}

    def find(dart: tuple) -> tuple:
        parent.setdefault(dart, dart)
        while parent[dart] != dart:
            parent[dart] = parent[parent[dart]]
            dart = parent[dart]
        return dart

    def side(label: tuple, counterclockwise: bool) -> tuple:
        ring, occurrence, kind = label
        if kind == "out":
            return (ring, occurrence, 0 if counterclockwise else 1)
        return (ring, (occurrence - 1) % passes[ring], 1 if counterclockwise else 0)

    for labels in system.values():
        for a, b in zip(labels, labels[1:] + labels[:1], strict=True):
            parent[find(side(a, True))] = find(side(b, False))
    return find


def _embedding(
    rings: dict[int, list[Point]], contacts: set[Point], groups: list[list[int]], find
) -> dict | None:
    """Her bileşenin sınırsız yüzünü ve öbür bileşenleri içeren yüzünü döndürür.

    Halka listeleri (varsa) bir temas köşesiyle başlamalıdır. Sınırsız yüz,
    bileşenin sözlük sırasıyla en küçük köşesindeki en sol (saat yönü tersine
    en uç) ışının ötesindedir. Başka bir bileşeni içeren yüz, o bileşenin bir
    kenar noktasından batıya atılan yatay ışının ilk kestiği kenarın doğu
    yanıdır; ışın yüksekliği hiçbir köşeden geçmeyecek biçimde seçilir.
    """
    arcs = {}
    for i, vertices in rings.items():
        current, numbers = -1, []
        for vertex in vertices:
            current += vertex in contacts
            numbers.append(max(current, 0))
        arcs[i] = numbers
    group_of = {i: c for c, members in enumerate(groups) for i in members}
    result = {}
    for c, members in enumerate(groups):
        low = min(v for i in members for v in rings[i])
        best = None
        for i in members:
            vertices = rings[i]
            count = len(vertices)
            for k, vertex in enumerate(vertices):
                if vertex != low:
                    continue
                for other, edge, right in (
                    (vertices[k - 1], k - 1, 1),
                    (vertices[(k + 1) % count], k, 0),
                ):
                    d = (other[0] - low[0], other[1] - low[1])
                    if best is None or best[0][0] * d[1] - best[0][1] * d[0] > 0:
                        best = (d, (i, arcs[i][edge], right))
        result[c, None] = find(best[1])
    edges = [(i, k, v[k], v[(k + 1) % len(v)]) for i, v in rings.items() for k in range(len(v))]
    if len(groups) == 1:
        return result
    for d, members in enumerate(groups):
        vertices = rings[members[0]]
        steep = [
            (a, b)
            for a, b in zip(vertices, vertices[1:] + vertices[:1], strict=True)
            if a[1] != b[1]
        ]
        if not steep:
            return None
        a, b = steep[0]
        low, high = min(a[1], b[1]), max(a[1], b[1])
        between = [
            w[1] for j, ring in rings.items() if group_of[j] != d for w in ring if low < w[1] < high
        ]
        level = (low + min(between, default=high)) / 2
        x = a[0] + (level - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
        nearest: dict[int, tuple] = {}
        for j, k, p, q in edges:
            c = group_of[j]
            if c == d or (p[1] > level) == (q[1] > level):
                continue
            hit = p[0] + (level - p[1]) * (q[0] - p[0]) / (q[1] - p[1])
            if hit == x or (c in nearest and nearest[c][0] == hit):
                return None
            if hit < x and (c not in nearest or hit > nearest[c][0]):
                nearest[c] = (hit, (j, arcs[j][k], 1 if q[1] > p[1] else 0))
        for c in range(len(groups)):
            if c != d:
                result[c, d] = find(nearest[c][1]) if c in nearest else result[c, None]
    return result


def contact_polygon_proof(model: dict[int, list[Point]], reference: dict[int, list[Point]]) -> bool:
    """Temaslı referans ile çokgen modelin aynı düzlem gömülmesine sahip olduğunu kanıtlar.

    Args:
        model, reference: halka kimliği → tam rasyonel köşe listesi (kapanış tekrarsız).

    Returns:
        Dört yeter koşulun tamamı tam aritmetikte sağlanırsa True.
    """
    if set(model) != set(reference):
        return False
    seen: set[Point] = set()
    contacts: set[Point] = set()
    for vertices in reference.values():
        for vertex in vertices:
            (contacts if vertex in seen else seen).add(vertex)
    if not contacts:
        return False
    reference = {i: _canonical(v, contacts)[0] for i, v in reference.items()}
    for i in reference:
        if _contact_sequence(_canonical(model[i], contacts)[0], contacts) != _contact_sequence(
            reference[i], contacts
        ):
            return False
        # Model köşeleri arasında temas noktası dışında tekrar olmamalı.
        plain = [v for v in model[i] if v not in contacts]
        if len(plain) != len(set(plain)):
            return False
    expected = _rotation(reference, contacts)
    if expected is None or not _edges_embedded(model, contacts):
        return False
    groups = _groups(reference, contacts)
    passes = {i: max(1, len(_contact_sequence(v, contacts))) for i, v in reference.items()}
    find = _faces(expected, passes)
    target = _embedding(reference, contacts, groups, find)
    if target is None:
        return False
    # Simetrik temas dizilerinde halkayı kendine taşıyan her etiketleme denenir.
    options = {i: _canonical(v, contacts) for i, v in model.items()}
    total = 1
    for candidates in options.values():
        total *= len(candidates)
    if total > 256:
        return False
    keys = sorted(options)
    for choice in product(*(range(len(options[i])) for i in keys)):
        relabelled = {i: options[i][c] for i, c in zip(keys, choice, strict=True)}
        if (
            _rotation(relabelled, contacts) == expected
            and _embedding(relabelled, contacts, groups, find) == target
        ):
            return True
    return False
