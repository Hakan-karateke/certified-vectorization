"""İkili piksel birleşiminin sınırlarını deterministik olarak izler."""

from collections import defaultdict

import numpy as np
from numpy.typing import NDArray

from .models import Boundary

Point = tuple[int, int]


def trace_boundaries(mask: NDArray[np.bool_], max_edges: int = 400_000) -> list[Boundary]:
    """Siyah birim karelerin dışarı bakan kenarlarını kapalı halkalara dönüştürür.

    Args:
        mask: İki boyutlu boolean dizi; True şeklin içidir.
        max_edges: İzin verilen en çok birim sınır kenarı; etkileşimli kullanımda
            gürültülü girdilere karşı korur, büyük girdi deneylerinde yükseltilir.

    Returns:
        Kartezyen koordinatlı dış ve iç sınırlar. Köşeden temas eden pikseller
        dört-komşuluk kuralıyla ayrı halkalarda kalır. Boş maskede boş liste döner.

    Raises:
        ValueError: Girdi iki boyutlu boolean dizi değilse.
    """
    if mask.ndim != 2 or mask.dtype != np.bool_:
        raise ValueError("Maske iki boyutlu boolean dizi olmalıdır.")
    height, _ = mask.shape
    padded = np.pad(mask, 1)
    exposed = (
        mask & ~padded[:-2, 1:-1],
        mask & ~padded[1:-1, 2:],
        mask & ~padded[2:, 1:-1],
        mask & ~padded[1:-1, :-2],
    )
    if sum(int(side.sum()) for side in exposed) > max_edges:
        raise ValueError(
            f"Görsel {max_edges:,}'den fazla birim sınır kenarı içeriyor. ".replace(",", ".")
            + "Gürültüyü temizleyin veya daha sade bir görsel kullanın."
        )
    adjacency: dict[Point, set[Point]] = defaultdict(set)
    # Görsel koordinatlarında saat yönü; içerideki siyah alan sağda kalır.
    offsets = ((0, 0, 1, 0), (1, 0, 1, 1), (1, 1, 0, 1), (0, 1, 0, 0))
    for exposed_side, (ax, ay, bx, by) in zip(exposed, offsets, strict=True):
        rows, cols = np.nonzero(exposed_side)
        for row, col in zip(rows.tolist(), cols.tolist(), strict=True):
            adjacency[(col + ax, row + ay)].add((col + bx, row + by))

    directions = {(1, 0): 0, (0, 1): 1, (-1, 0): 2, (0, -1): 3}
    turn_order = {1: 0, 0: 1, 3: 2, 2: 3}
    boundaries = []
    while adjacency:
        start = next(iter(adjacency))
        current = start
        previous_direction = None
        ring: list[Point] = []
        while True:
            ring.append(current)
            candidates = adjacency[current]
            if previous_direction is None:
                following = min(candidates)
            else:

                def priority(
                    point: Point, origin: Point = current, heading: int = previous_direction
                ) -> int:
                    """Aday kenarın sağa dönüş önceliğini tam sayı olarak döndürür."""
                    direction = directions[(point[0] - origin[0], point[1] - origin[1])]
                    return turn_order[(direction - heading) % 4]

                following = min(candidates, key=priority)
            candidates.remove(following)
            if not candidates:
                del adjacency[current]
            previous_direction = directions[(following[0] - current[0], following[1] - current[1])]
            current = following
            if current == start:
                break
        cartesian = np.array([(x, height - y) for x, y in ring], dtype=np.int64)
        incoming = cartesian - np.roll(cartesian, 1, axis=0)
        outgoing = np.roll(cartesian, -1, axis=0) - cartesian
        # Eşdoğrusal komşuları kaldırmak eğriyi değiştirmez.
        turns = incoming[:, 0] * outgoing[:, 1] - incoming[:, 1] * outgoing[:, 0]
        vertices = cartesian[turns != 0]
        area2 = np.sum(
            vertices[:, 0] * np.roll(vertices[:, 1], -1)
            - vertices[:, 1] * np.roll(vertices[:, 0], -1)
        )
        points = [tuple(map(int, point)) for point in vertices]
        boundaries.append(Boundary(points, "outer" if area2 < 0 else "hole", len(points)))
    return boundaries


def _rdp(points: NDArray[np.float64], tolerance: float) -> NDArray[np.float64]:
    """Açık nokta zincirini iteratif RDP ile sadeleştirip kalan noktaları döndürür."""
    keep = {0, len(points) - 1}
    pending = [(0, len(points) - 1)]
    while pending:
        first, last = pending.pop()
        if last <= first + 1:
            continue
        start, end = points[first], points[last]
        vector = end - start
        denominator = float(vector @ vector)
        middle = points[first + 1 : last]
        if denominator == 0:
            distances = np.linalg.norm(middle - start, axis=1)
        else:
            parameter = np.clip((middle - start) @ vector / denominator, 0, 1)
            distances = np.linalg.norm(middle - start - parameter[:, None] * vector, axis=1)
        index = int(np.argmax(distances))
        if distances[index] > tolerance:
            split = first + 1 + index
            keep.add(split)
            pending.extend(((first, split), (split, last)))
    return points[sorted(keep)]


def simplify_boundary(boundary: Boundary, tolerance: float) -> Boundary:
    """Kapalı sınırı verilen piksel toleransıyla sadeleştirip yeni Boundary döndürür.

    Args:
        boundary: Kesin piksel sınırı.
        tolerance: Sıfırsa aynı nesne döner; pozitifse RDP uygulanır.

    Returns:
        En az üç köşeli sınır. Pozitif toleransta topoloji korunma garantisi yoktur.
    """
    if tolerance == 0:
        return boundary
    points = np.asarray(boundary.vertices, dtype=float)
    split = int(np.argmax(np.linalg.norm(points - points[0], axis=1)))
    first = _rdp(points[: split + 1], tolerance)
    second = _rdp(np.vstack((points[split:], points[0])), tolerance)
    simplified = np.vstack((first[:-1], second[:-1]))
    if len(simplified) < 3:
        return boundary
    return Boundary(
        [tuple(map(int, point)) for point in simplified],
        boundary.kind,
        boundary.original_vertex_count,
    )


def sample_boundaries(boundaries: list[Boundary], count: int) -> NDArray[np.float64]:
    """Sınır birleşimini eşit yay uzunluğu aralıklarıyla örnekler.

    Args:
        boundaries: Örnek alınacak kapalı poligonlar.
        count: Döndürülecek toplam örnek sayısı.

    Returns:
        (N, 2) koordinat dizisi. Her halkaya en az 8 örnek ayrılır; count bu
        minimumdan küçükse N=8*halka sayısı olur. Hiçbir bileşen atlanmaz.

    Raises:
        ValueError: Sınır listesi boşsa veya count pozitif değilse.
    """
    if not boundaries or count <= 0:
        raise ValueError("Örnekleme için sınırlar ve pozitif örnek sayısı gereklidir.")
    if len(boundaries) > 1:
        perimeters = np.array(
            [
                np.linalg.norm(
                    np.roll(b.vertices, -1, axis=0) - np.asarray(b.vertices), axis=1
                ).sum()
                for b in boundaries
            ]
        )
        remaining = max(0, count - 8 * len(boundaries))
        allocation = np.floor(remaining * perimeters / perimeters.sum()).astype(int) + 8
        allocation[np.argmax(perimeters)] += max(count, 8 * len(boundaries)) - int(allocation.sum())
        return np.vstack(
            [sample_boundaries([b], int(n)) for b, n in zip(boundaries, allocation, strict=True)]
        )
    starts, ends = [], []
    for boundary in boundaries:
        vertices = np.asarray(boundary.vertices, dtype=float)
        starts.append(vertices)
        ends.append(np.roll(vertices, -1, axis=0))
    begin, end = np.vstack(starts), np.vstack(ends)
    lengths = np.linalg.norm(end - begin, axis=1)
    cumulative = np.cumsum(lengths)
    distances = np.linspace(0, cumulative[-1], count, endpoint=False)
    indices = np.searchsorted(cumulative, distances, side="right")
    previous = np.r_[0, cumulative[:-1]]
    parameter = (distances - previous[indices]) / lengths[indices]
    return begin[indices] + parameter[:, None] * (end[indices] - begin[indices])
