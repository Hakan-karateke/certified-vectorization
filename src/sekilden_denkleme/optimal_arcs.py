"""Kapalı piksel sınırı için düğüm kısıtlı en az parçalı doğru + çember yayı halkası.

Sınıf: halkanın düğümleri P'nin alt dizisidir; ardışık iki seçili düğüm a, b
arasındaki parça ya [a, b] doğru parçası ya da a'dan b'ye, bulge β = tan(θ/4),
0 < |β| ≤ β_max < 1 olan küçük çember yayıdır (θ yönlü merkez açısı). Bir parça,
atladığı alt zincirin **bütün düğümleri** parçaya en çok τ uzaktaysa geçerlidir.
β = 0 doğru parçasıdır; o durumda ölçüt kiriş kapsülü ölçütüyle aynıdır, yani
sınıf düğüm kısıtlı çokgenleri kapsar. Yaylar en çok max_span düğüm atlar.

Yöntem: a ve b'den geçen küçük yaylar, çapı [a, b] olan diski β'ya göre
monoton biçimde yapraklar. Bu yüzden bir p düğümü için dist(p, yay_β) ≤ τ
koşulunu sağlayan β kümesi bir aralıktır ve sonlu uçları, a ile b'den geçip
(p, τ) çemberine teğet olan iki çemberin bulge değerleridir (kapalı biçimli
ikinci derece denklem). Bir (a, b) çifti, bütün ara düğümlerin aralıkları
kesişiyorsa geçerlidir. Aralıklar float64 ile τ'nun **üst kümesinde** bulunur;
en kısa tur seçildikten sonra her parça tam rasyonel aritmetikle yeniden
denetlenir. Denetim tutmazsa parça grafikten çıkarılır ve tur yeniden aranır.
İlk turun uzunluğu kanıtlı alt sınırdır; doğrulanan tur aynı uzunluktaysa
sonuç bu sınıfta optimumdur.

Düğümler zincir boyunca en çok `spacing` aralıklı olmalıdır (dense_nodes):
ölçüt yalnızca düğümleri denetler, seyrek düğümlü uzun bir kenardan yay
serbestçe uzaklaşabilir. Sürekli Hausdorff hatası ve topoloji bağımsız
sertifikayla ayrıca kanıtlanmalıdır.
"""

from fractions import Fraction as Q

import numpy as np

from .curves import new_piece
from .models import Boundary, CurvePiece
from .optimal_polygon import _best_cycle, _edge_exact, _shortcut_steps

BETA_MAX = 0.999
_MARGIN = 1e-6
_BETA_MARGIN = 1e-9
_LINE_BETA = 1e-7


def dense_nodes(boundary: Boundary, spacing: float = 0.5) -> np.ndarray:
    """Halka köşelerini ve her kenarın en çok `spacing` aralıklı iç noktalarını döndürür."""
    if not np.isfinite(spacing) or spacing <= 0:
        raise ValueError("Düğüm aralığı pozitif ve sonlu olmalıdır.")
    vertices = np.asarray(boundary.vertices, dtype=float)
    rows = []
    for a, b in zip(vertices, np.roll(vertices, -1, axis=0), strict=True):
        parts = max(1, int(np.ceil(np.hypot(*(b - a)) / spacing - 1e-9)))
        rows.append(a + (b - a) * (np.arange(parts) / parts)[:, None])
    return np.concatenate(rows)


def _arc_distance(xi: np.ndarray, eta: np.ndarray, h: np.ndarray, beta: np.ndarray) -> np.ndarray:
    """Yerel (ξ, η) noktasının bulge β yayına uzaklığı; β'nın yönü +η'dır."""
    ends = np.hypot(np.abs(xi) - h, eta)
    straight = np.abs(beta) < _LINE_BETA
    safe = np.where(straight, 1.0, beta)
    t = h * (safe * safe - 1) / (2 * safe)
    radius = h * (1 + safe * safe) / (2 * np.abs(safe))
    rho = np.hypot(xi, eta - t)
    inside = np.sign(safe) * (eta - t) * radius >= rho * np.abs(t)
    with np.errstate(divide="ignore", invalid="ignore"):
        # Nokta çemberin merkezindeyse ve yarıçap sıfırsa 0/0 oluşur; o dal seçilmez.
        radial = np.abs(xi * xi + eta * eta - h * h - 2 * eta * t) / (rho + radius)
    curved = np.where(inside, radial, ends)
    flat = np.where(np.abs(xi) <= h, np.abs(eta), ends)
    return np.where(straight, flat, curved)


def _bulge_intervals(
    a: np.ndarray, b: np.ndarray, points: np.ndarray, tolerance: float
) -> tuple[np.ndarray, np.ndarray]:
    """Her (a_n, b_n) çifti için ara düğümlerin ortak geçerli β aralığı [lo, hi].

    a, b: (N, 2); points: (N, P, 2). lo > hi boş aralıktır. Sonuç τ + pay için
    hesaplandığından gerçek geçerli kümenin üst kümesidir.
    """
    tol = tolerance + _MARGIN
    u = b - a
    length = np.hypot(u[:, 0], u[:, 1])
    safe = np.maximum(length, 1e-300)
    along = u / safe[:, None]
    right = np.stack([along[:, 1], -along[:, 0]], axis=1)
    rel = points - ((a + b) / 2)[:, None, :]
    xi = (rel * along[:, None, :]).sum(2)
    eta = (rel * right[:, None, :]).sum(2)
    h = (length / 2)[:, None] + np.zeros_like(xi)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        big = xi * xi + eta * eta - h * h - tol * tol
        qa = big * big - 4 * tol * tol * h * h
        half = 2 * big * eta
        qc = 4 * (eta * eta - tol * tol)
        disc = half * half - qa * qc
        root = np.sqrt(np.maximum(disc, 0.0))
        q = -(half + np.where(half >= 0, root, -root))
        k1, k2 = q / qa, qc / q
        x1, x2 = k1 * h, k2 * h
        b1 = np.where(np.isinf(x1), np.sign(x1), x1 / (1 + np.sqrt(1 + x1 * x1)))
        b2 = np.where(np.isinf(x2), np.sign(x2), x2 / (1 + np.sqrt(1 + x2 * x2)))
    real = disc >= 0
    b1 = np.clip(np.where(real & np.isfinite(b1), b1, 0.0), -BETA_MAX, BETA_MAX)
    b2 = np.clip(np.where(real & np.isfinite(b2), b2, 0.0), -BETA_MAX, BETA_MAX)
    first, second = np.minimum(b1, b2), np.maximum(b1, b2)
    low = _arc_distance(xi, eta, h, (first - BETA_MAX) / 2) <= tol
    middle = _arc_distance(xi, eta, h, (first + second) / 2) <= tol
    high = _arc_distance(xi, eta, h, (second + BETA_MAX) / 2) <= tol
    lo = np.where(low, -BETA_MAX, np.where(middle, first, np.where(high, second, np.inf)))
    hi = np.where(high, BETA_MAX, np.where(middle, second, np.where(low, first, -np.inf)))
    near = np.hypot(np.abs(xi) - h, eta) <= tol
    lo = np.where(near, -BETA_MAX, lo) - _BETA_MARGIN
    hi = np.where(near, BETA_MAX, hi) + _BETA_MARGIN
    lo, hi = lo.max(1), hi.min(1)
    empty = length <= 0
    return np.where(empty, np.inf, lo), np.where(empty, -np.inf, hi)


def _arc_steps(
    points: np.ndarray,
    tolerance: float,
    max_span: int,
    lines: list[np.ndarray],
    probe: int = 12,
    refine: int = 64,
    full_below: int = 128,
) -> tuple[np.ndarray, np.ndarray]:
    """valid[d-1, i]: p_i → p_{i+d} için τ⁺-geçerli bir küçük yay olabilir (üst küme).

    Ara düğümlerin eşit aralıklı bir alt kümesi sınanır (önce `probe`, geçenlerde
    `refine` düğüm); daha az kısıt daha büyük küme verdiğinden sonuç gerçek geçerli
    kümenin üst kümesidir. En çok `full_below` düğüm atlayan çiftler burada bütün
    ara düğümlerle sınanır ve ikinci dönen matriste işaretlenir; daha uzun
    çiftlerin tam denetimi tur aranırken, yalnızca kullanıldıkları yerde yapılır.
    Doğru parçası zaten geçerli olan çiftler atlanır: β = 0 aynı aralıktadır ve
    tur uzunluğunu değiştirmez.
    """
    m = len(points)
    depth = max(0, min(max_span, m - 1))
    valid = np.zeros((depth, m), dtype=bool)
    complete = np.zeros((depth, m), dtype=bool)
    straight = np.zeros((depth + 1, m), dtype=bool)
    for i, steps in enumerate(lines):
        straight[steps[steps <= depth], i] = True
    for d in range(2, depth + 1):
        index = np.flatnonzero(~straight[d])
        if not len(index):
            continue
        target = points[(index + d) % m]
        count = min(d - 1, probe)
        offsets = np.unique(np.round(np.linspace(1, d - 1, count)).astype(int))
        lo, hi = _bulge_intervals(
            points[index], target, points[(index[:, None] + offsets[None, :]) % m], tolerance
        )
        row = np.zeros(m, dtype=bool)
        row[index] = lo <= hi
        target = points[(np.arange(m) + d) % m]
        stages = [d - 1] if d <= full_below else [refine] if refine > probe else []
        if d <= full_below and refine > probe and d - 1 > 2 * refine:
            stages = [refine, d - 1]
        for stage in stages:
            if stage <= len(offsets):
                continue
            # Seyrek ön elemeyi geçen çiftler daha sık bir alt kümeyle yeniden sınanır.
            passing = np.flatnonzero(row)
            every = np.unique(np.round(np.linspace(1, d - 1, min(d - 1, stage))).astype(int))
            offsets = every
            chunk = max(1, 40000 // len(every))
            for k in range(0, len(passing), chunk):
                part = passing[k : k + chunk]
                lo, hi = _bulge_intervals(
                    points[part],
                    target[part],
                    points[(part[:, None] + every[None, :]) % m],
                    tolerance,
                )
                row[part] = lo <= hi
        valid[d - 1] = row
        complete[d - 1] = len(offsets) == d - 1
    return valid, complete


def _layered_cycle(valid: np.ndarray, start: int, limit: int) -> list[int] | None:
    """start'tan bir tam tur atan en az parçalı yolu genişlik öncelikli arar.

    valid[d-1, i] adım matrisidir. Her konum bir kez genişletilir; `limit`
    parçadan uzun turlar aranmaz. Tur yoksa None, üç parçadan kısa bir tur varsa
    boş liste döner (o durumda çağıran tam katmanlı yola başvurur).
    """
    depth, m = valid.shape
    parent = np.full(m + 1, -1, dtype=np.int64)
    seen = np.zeros(m + 1, dtype=bool)
    seen[0] = True
    frontier = np.array([0], dtype=np.int64)
    for count in range(1, limit + 1):
        steps, source = np.nonzero(valid[:, (start + frontier) % m])
        target = frontier[source] + steps + 1
        keep = target <= m
        target, origin = target[keep], frontier[source[keep]]
        fresh = ~seen[target]
        target, origin = target[fresh], origin[fresh]
        if not len(target):
            return None
        parent[target] = origin
        fresh = np.zeros(m + 1, dtype=bool)
        fresh[target] = True
        frontier = np.flatnonzero(fresh)
        seen[frontier] = True
        if seen[m]:
            if count < 3:
                # Üç parçadan kısa tur: genişlik öncelikli arama üç parçalıyı göremez.
                return []
            path, position = [], m
            while position:
                position = int(parent[position])
                path.append(position)
            return [(start + q) % m for q in path[::-1]]
        frontier = frontier[frontier < m]
    return None


def _fast_cycle(valid: np.ndarray) -> list[int] | None:
    """Adım matrisinde en az parçalı kapalı turu (artan düğüm sırası) bulur.

    Her tur, hiçbir adımın üzerinden atlayamadığı pencerenin bir düğümüne uğrar.
    Pencerenin her düğümü için ucuz bir alt sınır hesaplanır: q ≤ p konumlarından
    tek adımda ulaşılan en uzak konumun önek maksimumuyla atlayarak bir turu
    tamamlamak için gereken adım sayısı, o düğümden geçen hiçbir turdan büyük
    değildir. Katmanlı arama alt sınırı küçük olandan başlar ve alt sınırı eldeki
    en iyi turdan küçük olmayan düğümlerde yapılmaz. Üç parçadan kısa turlu çok
    küçük halkalarda optimal_polygon'daki katmanlı yola dönülür.
    """
    depth, m = valid.shape
    reach = np.where(valid.any(0), depth - np.argmax(valid[::-1], axis=0), 0)
    if not reach.all():
        return None
    window = np.ones(m, dtype=np.int64)
    for k in range(1, int(reach.max()) + 1):
        window = np.maximum(window, 1 + np.roll(reach, k) - k)
    first = int(np.argmin(window))
    starts = (first + np.arange(int(window[first]))) % m
    unrolled = np.arange(2 * m)
    hull = np.maximum.accumulate(unrolled + reach[unrolled % m])
    position = starts.copy()
    bound = np.zeros(len(starts), dtype=np.int64)
    while True:
        active = position < starts + m
        if not active.any():
            break
        position[active] = hull[position[active]]
        bound[active] += 1
    bound = np.maximum(bound, 3)
    best = None
    short = False
    for k in np.argsort(bound, kind="stable"):
        if best is not None and bound[k] >= len(best):
            break
        limit = m if best is None else len(best) - 1
        cycle = _layered_cycle(valid, int(starts[k]) % m, limit)
        if cycle:
            best = cycle
        elif cycle is not None:
            short = True
    if best is None or short:
        exact = _best_cycle([np.flatnonzero(valid[:, i]) + 1 for i in range(m)], m)
        if best is None or (exact is not None and len(exact) < len(best)):
            return exact
    return sorted(best)


def arc_exact(points: np.ndarray, i: int, d: int, bulge: float, tolerance: float) -> bool:
    """p_i → p_{i+d} yayının bütün ara düğümlere uzaklığını tam aritmetikle sınar."""
    m = len(points)
    beta = Q(float(bulge))
    a = tuple(Q(float(x)) for x in points[i])
    b = tuple(Q(float(x)) for x in points[(i + d) % m])
    if a == b or not 0 < abs(beta) < 1:
        return False
    limit = Q(float(tolerance)) ** 2
    # Pozitif bulge sağa bombelenir, merkez soldadır: orta nokta + (1-β²)/(4β) · j,
    # j = (a_y-b_y, b_x-a_x) sol normal (boyu |ab|).
    factor = (1 - beta * beta) / (4 * beta)
    c = (
        (a[0] + b[0]) / 2 + factor * (a[1] - b[1]),
        (a[1] + b[1]) / 2 + factor * (b[0] - a[0]),
    )
    ca = (a[0] - c[0], a[1] - c[1])
    cb = (b[0] - c[0], b[1] - c[1])
    radius = ca[0] * ca[0] + ca[1] * ca[1]
    turn = ca[0] * cb[1] - ca[1] * cb[0]
    sign = 1 if turn > 0 else -1
    for k in range(1, d):
        p = tuple(Q(float(x)) for x in points[(i + k) % m])
        cp = (p[0] - c[0], p[1] - c[1])
        first = (ca[0] * cp[1] - ca[1] * cp[0]) * sign
        second = (cp[0] * cb[1] - cp[1] * cb[0]) * sign
        if first >= 0 and second >= 0:
            rho = cp[0] * cp[0] + cp[1] * cp[1]
            gap = rho + radius - limit
            if gap > 0 and gap * gap > 4 * rho * radius:
                return False
        else:
            da = (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2
            db = (p[0] - b[0]) ** 2 + (p[1] - b[1]) ** 2
            if min(da, db) > limit:
                return False
    return True


def min_piece_ring(
    points: np.ndarray,
    tolerance: float,
    max_span: int = 512,
    max_repairs: int = 200,
    radius: int = 24,
) -> dict:
    """Sıralı kapalı düğüm dizisinde en az parçalı doğru + yay halkasını bulur.

    Returns:
        nodes: seçilen düğüm indeksleri (artan); bulges: nodes[k] → nodes[k+1]
        parçasının bulge değeri (0 doğru parçası); piece_count; arc_count;
        lower_bound: τ için kanıtlı alt sınır; optimal: piece_count == lower_bound;
        pruned: bütün ara düğümlerle denetimde geçersiz çıkan (alt sınırı bozmayan)
        parça sayısı; repairs: üst kümede geçerli görünüp tam aritmetikte
        doğrulanamayan parça sayısı; alt sınır o parçaları da içeren üst küme
        grafiğinde hesaplanır.
    """
    points = np.asarray(points, dtype=float)
    m = len(points)
    if m < 3 or points.shape != (m, 2) or not np.isfinite(points).all():
        raise ValueError("Min-# araması en az üç sonlu düzlem noktası gerektirir.")
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Min-# toleransı pozitif ve sonlu olmalıdır.")
    line_steps = _shortcut_steps(points, tolerance)
    # Sıkı toleransta sahte uygun çiftler çoktur ve baştan elemek ucuzdur; gevşek
    # toleransta uzun gerçek yaylar çoktur ve yalnızca kullanılanı sınamak ucuzdur.
    # Bu seçim yalnızca süreyi etkiler: iki yol da aynı üst kümeden başlar.
    eager = tolerance < 1.5
    arcs_valid, arcs_complete = _arc_steps(
        points,
        tolerance,
        max_span,
        line_steps,
        refine=64 if eager else 0,
        full_below=256 if eager else 0,
    )
    depth = max([len(arcs_valid), *(int(steps[-1]) for steps in line_steps if len(steps))])
    lines = np.zeros((depth, m), dtype=bool)
    for i, steps in enumerate(line_steps):
        lines[steps - 1, i] = True
    arcs = np.zeros((depth, m), dtype=bool)
    arcs[: len(arcs_valid)] = arcs_valid & ~lines[: len(arcs_valid)]
    verified = np.zeros_like(arcs)
    verified[: len(arcs_valid)] = arcs_complete
    reach = len(arcs_valid)

    def verify_block(i: int, d: int) -> int:
        """(i, d) çevresindeki aday yayları bütün ara düğümlerle sınar; düşen sayısını döndürür."""
        removed = 0
        offsets = np.arange(-radius, radius + 1)
        for step in range(max(2, d - 2 * radius), min(reach, d + 2 * radius) + 1):
            # Başlangıç i+s, bitiş i+d+e: adım = d + e - s, |s|, |e| ≤ radius.
            shift = offsets[np.abs(step - d + offsets) <= radius]
            index = (i + shift) % m
            index = index[arcs[step - 1, index] & ~verified[step - 1, index]]
            if not len(index):
                continue
            inner = points[(index[:, None] + np.arange(1, step)[None, :]) % m]
            lo, hi = _bulge_intervals(points[index], points[(index + step) % m], inner, tolerance)
            verified[step - 1, index] = True
            bad = index[lo > hi]
            arcs[step - 1, bad] = False
            removed += len(bad)
        return removed

    line_ok: dict[tuple[int, int], bool] = {}
    chosen: dict[tuple[int, int], float | None] = {}
    lower = None
    repairs = pruned = 0
    rejected = np.zeros_like(arcs)
    while True:
        cycle = _fast_cycle(lines | arcs)
        if cycle is None:
            raise ValueError("Min-# grafiğinde kapalı tur bulunamadı.")
        if not repairs:
            # Yalnızca kanıtlı geçersiz parçalar çıkarıldı: grafik hâlâ üst kümedir.
            lower = len(cycle)
        failed = False
        bulges = []
        for i, j in zip(cycle, cycle[1:] + cycle[:1], strict=True):
            d = (j - i) % m or m
            key = (i, d)
            if lines[d - 1, i]:
                if key not in line_ok:
                    line_ok[key] = _edge_exact(points, i, d, tolerance)
                if line_ok[key]:
                    bulges.append(0.0)
                    continue
                lines[d - 1, i] = False
                rejected[d - 1, i] = True
                repairs += 1
                failed = True
                continue
            if not verified[d - 1, i]:
                pruned += verify_block(i, d)
            if not arcs[d - 1, i]:
                failed = True
                continue
            if key not in chosen:
                inner = points[(i + np.arange(1, d)) % m][None, :, :]
                ends = points[[i]], points[[(i + d) % m]]
                lo, hi = _bulge_intervals(*ends, inner, tolerance)
                if lo[0] > hi[0]:
                    chosen[key] = None
                else:
                    safe_lo, safe_hi = _bulge_intervals(*ends, inner, tolerance - 2 * _MARGIN)
                    if safe_lo[0] <= safe_hi[0]:
                        lo, hi = safe_lo, safe_hi
                    beta = float((lo[0] + hi[0]) / 2)
                    good = abs(beta) >= _LINE_BETA and arc_exact(points, i, d, beta, tolerance)
                    chosen[key] = beta if good else 0.0
            if chosen[key]:
                bulges.append(chosen[key])
                continue
            arcs[d - 1, i] = False
            failed = True
            if chosen[key] is None:
                pruned += 1
            else:
                rejected[d - 1, i] = True
                repairs += 1
        if not failed:
            break
        if repairs > max_repairs:
            raise ValueError("Doğru + yay turu tam aritmetikte doğrulanamadı.")
    while repairs:
        # Alt sınır, tam aritmetikte reddedilen parçaları da içeren üst küme grafiğinde
        # aranır; yalnızca bütün ara düğümlerle geçersizliği gösterilen yaylar çıkarılır.
        bound = _fast_cycle(lines | arcs | rejected)
        changed = False
        for i, j in zip(bound, bound[1:] + bound[:1], strict=True):
            d = (j - i) % m or m
            if lines[d - 1, i] or rejected[d - 1, i]:
                continue
            if not verified[d - 1, i]:
                pruned += verify_block(i, d)
            changed |= not arcs[d - 1, i]
        if not changed:
            lower = len(bound)
            break
    return {
        "nodes": cycle,
        "bulges": bulges,
        "piece_count": len(cycle),
        "arc_count": sum(1 for beta in bulges if beta),
        "lower_bound": int(lower),
        "optimal": len(cycle) == lower,
        "repairs": repairs,
        "pruned": pruned,
        "node_count": m,
        "tolerance": float(tolerance),
        "max_span": int(max_span),
    }


def line_arc_pieces(
    points: np.ndarray, result: dict, boundary_id: int, component_id: int
) -> list[CurvePiece]:
    """min_piece_ring sonucunu doğru ve rasyonel çember yayı parçalarına dönüştürür."""
    nodes = result["nodes"]
    pieces = []
    for i, j, beta in zip(nodes, nodes[1:] + nodes[:1], result["bulges"], strict=True):
        a, b = points[i].tolist(), points[j].tolist()
        if beta:
            # rational_arcs sözleşmesinde pozitif bulge a→b'nin sağına bombelenir.
            params = {"arc": {"a": a, "b": b, "bulge": float(beta)}}
            pieces.append(new_piece("circle", params, [0.0, 1.0], boundary_id, component_id))
        else:
            pieces.append(
                new_piece("line", {"a": a, "b": b}, [0.0, 1.0], boundary_id, component_id)
            )
    return pieces


def min_piece_boundaries(
    boundaries: list[Boundary],
    tolerance: float,
    components: list[int],
    spacing: float = 0.5,
    max_span: int = 512,
) -> tuple[list[CurvePiece], dict]:
    """Bütün halkaları ayrı ayrı çözer; temas ve açıklık kısıtı uygulanmaz."""
    pieces: list[CurvePiece] = []
    rings = []
    for index, boundary in enumerate(boundaries):
        points = dense_nodes(boundary, spacing)
        result = min_piece_ring(points, tolerance, max_span)
        pieces.extend(line_arc_pieces(points, result, index, components[index]))
        rings.append(result)
    return pieces, {
        "piece_count": sum(r["piece_count"] for r in rings),
        "arc_count": sum(r["arc_count"] for r in rings),
        "lower_bound": sum(r["lower_bound"] for r in rings),
        "optimal": all(r["optimal"] for r in rings),
        "repairs": sum(r["repairs"] for r in rings),
        "pruned": sum(r["pruned"] for r in rings),
        "node_spacing": spacing,
        "max_span": max_span,
        "rings": rings,
    }


def joint_kinks(points: np.ndarray, nodes: list[int], bulges: list[float]) -> np.ndarray:
    """Ardışık parçalar arasındaki teğet dönüşlerini (radyan, (-π, π]) döndürür.

    Bulge β olan yay, kirişine göre başlangıçta -α, bitişte +α döner; α = 2·atan β
    ve pozitif β sağa bombeli olduğundan açı saat yönüne doğrudur. k. değer,
    k. parçanın bitişi ile (k+1). parçanın başlangıcı arasındaki dönüştür.
    """
    ends = points[nodes]
    chord = np.roll(ends, -1, axis=0) - ends
    direction = np.arctan2(chord[:, 1], chord[:, 0])
    alpha = 2 * np.arctan(np.asarray(bulges, dtype=float))
    turn = (np.roll(direction, -1) - np.roll(alpha, -1)) - (direction + alpha)
    return (turn + np.pi) % (2 * np.pi) - np.pi


def smooth_joints(
    points: np.ndarray, result: dict, tolerance: float, corner: float = np.radians(30)
) -> dict:
    """Yay bulge'larını geçerli aralıkları içinde değiştirerek teğet kırılmalarını azaltır.

    Düğümler, parça sayısı ve doğru parçaları değişmez; yalnızca yayların β değeri,
    bütün ara düğümler için geçerli aralık [lo, hi] içinde yeniden seçilir. α = 2·atan β
    cinsinden her birleşimdeki dönüş doğrusaldır, dolayısıyla kutu kısıtlı en küçük
    kareler problemidir. `corner` değerinden büyük dönüşler gerçek köşe sayılır ve
    amaçtan çıkarılır. Her yeni yay tam aritmetikle yeniden denetlenir; denetimi
    geçemeyen yay eski değerine döner. Sonuç yeni bir kayıt olarak döndürülür.
    """
    from scipy.optimize import lsq_linear

    points = np.asarray(points, dtype=float)
    m = len(points)
    nodes = list(result["nodes"])
    bulges = [float(b) for b in result["bulges"]]
    count = len(nodes)
    before = joint_kinks(points, nodes, bulges)
    arcs = [k for k, beta in enumerate(bulges) if beta]
    if not arcs:
        return {**result, "kinks_before": before.tolist(), "kinks_after": before.tolist()}
    lower, upper = np.zeros(count), np.zeros(count)
    for k in arcs:
        i = nodes[k]
        d = (nodes[(k + 1) % count] - i) % m or m
        lo, hi = _bulge_intervals(
            points[[i]],
            points[[(i + d) % m]],
            points[(i + np.arange(1, d)) % m][None, :, :],
            tolerance - 2 * _MARGIN,
        )
        # Aralık boşsa (sınırda) yay olduğu gibi bırakılır.
        low = min(float(lo[0]), bulges[k]) if lo[0] <= hi[0] else bulges[k]
        high = max(float(hi[0]), bulges[k]) if lo[0] <= hi[0] else bulges[k]
        lower[k], upper[k] = 2 * np.arctan(low), 2 * np.arctan(high)
    ends = points[nodes]
    chord = np.roll(ends, -1, axis=0) - ends
    direction = np.arctan2(chord[:, 1], chord[:, 0])
    base = (np.roll(direction, -1) - direction + np.pi) % (2 * np.pi) - np.pi
    # dönüş_k = base_k - α_k - α_{k+1}; yalnızca köşe olmayan birleşimler amaçtadır.
    rows = np.flatnonzero(np.abs(before) < corner)
    matrix = np.zeros((len(rows), len(arcs)))
    column = {k: c for c, k in enumerate(arcs)}
    for r, k in enumerate(rows):
        for piece in (k, (k + 1) % count):
            if piece in column:
                matrix[r, column[piece]] += 1.0
    alpha = 2 * np.arctan(np.asarray(bulges))
    if len(rows):
        span = np.maximum(upper[arcs] - lower[arcs], 1e-12)
        solved = lsq_linear(matrix, base[rows], bounds=(lower[arcs] - 1e-15, lower[arcs] + span))
        alpha[arcs] = np.clip(solved.x, lower[arcs], upper[arcs])
    smoothed = list(bulges)
    for k in arcs:
        beta = float(np.tan(alpha[k] / 2))
        i = nodes[k]
        d = (nodes[(k + 1) % count] - i) % m or m
        if abs(beta) >= _LINE_BETA and arc_exact(points, i, d, beta, tolerance):
            smoothed[k] = beta
    after = joint_kinks(points, nodes, smoothed)
    if np.abs(after[rows]).sum() > np.abs(before[rows]).sum():
        smoothed, after = bulges, before
    return {
        **result,
        "bulges": smoothed,
        "kinks_before": before.tolist(),
        "kinks_after": after.tolist(),
    }
