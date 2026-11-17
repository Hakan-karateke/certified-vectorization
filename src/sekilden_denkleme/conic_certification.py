"""Tam çember/elips halkalarının doğrulanmış rasyonel parametre kapsaması."""

import math
from fractions import Fraction as Q
from functools import lru_cache

import numpy as np

from .curves import is_full_conic
from .intervals import Interval, _norm_upper, _rational_interval
from .models import CurvePiece


@lru_cache(maxsize=128)
def rotation_bounds(angle: float) -> tuple[Interval, Interval]:
    """Gerçek sin/cos değerlerini rasyonel Taylor ve çift açıyla kapsar.

    |angle|≤64 radyan için önce |x|≤1/2'ye tam ikiye bölme uygulanır.
    Azalan alternatif serinin 14 terimi ve bir sonraki terimi tam Fraction
    hesaplanır; binary64'e kapsayıcı dönüşümden sonra çift açı işlemleri dışa
    yuvarlanır. libm sin/cos doğruluğu kanıt varsayımı yapılmaz.
    """
    if not math.isfinite(angle) or abs(angle) > 64:
        raise ValueError("Konik sertifikasında dönme açısı |θ|≤64 radyan olmalıdır.")
    if angle == 0:
        return Interval.point(0.0), Interval.point(1.0)
    x, halves = Q(float(angle)), 0
    while abs(x) > Q(1, 2):
        x /= 2
        halves += 1
    term_s, term_c, sine, cosine = x, Q(1), Q(0), Q(0)
    for j in range(14):
        sine += term_s
        cosine += term_c
        term_s *= -x * x / ((2 * j + 2) * (2 * j + 3))
        term_c *= -x * x / ((2 * j + 1) * (2 * j + 2))
    s = _rational_interval([min(sine, sine + term_s), max(sine, sine + term_s)])
    c = _rational_interval([min(cosine, cosine + term_c), max(cosine, cosine + term_c)])
    s, c = Interval(s.lo[0], s.hi[1]), Interval(c.lo[0], c.hi[1])
    for _ in range(halves):
        s, c = Interval.point(2) * s * c, c * c - s * s
    return s, c


def _rotate_quadrants(x: Interval, y: Interval, direction: int) -> tuple[Interval, Interval]:
    """İlk çeyreğin aralıklarını dört çeyreğe tam işaret/değiş tokuşla taşır."""
    first = [x, -y, -x, y]
    second = [y, x, -y, -x]
    a = Interval(np.concatenate([v.lo for v in first]), np.concatenate([v.hi for v in first]))
    b = Interval(np.concatenate([v.lo for v in second]), np.concatenate([v.hi for v in second]))
    return a, b if direction > 0 else -b


def _mapped(piece: CurvePiece, x: Interval, y: Interval) -> Interval:
    """Birim çember kapsamını kayıtlı pozitif eksenler ve gerçek dönmeyle eşler."""
    p = piece.params
    radii = [p["radius"]] * 2 if piece.kind == "circle" else p["radii"]
    if not np.isfinite([*p["center"], *radii]).all() or min(radii) <= 0:
        raise ValueError("Konik sertifikası sonlu merkez ve pozitif eksen gerektirir.")
    sine, cosine = rotation_bounds(float(p.get("rotation", 0)))
    rx, ry = (Interval.point(v) for v in radii)
    a = Interval.point(p["center"][0]) + rx * x * cosine - ry * y * sine
    b = Interval.point(p["center"][1]) + rx * x * sine + ry * y * cosine
    return Interval(np.stack([a.lo, b.lo], axis=-1), np.stack([a.hi, b.hi], axis=-1))


def conic_geometry(piece: CurvePiece, tolerance: float) -> tuple[list, float, list]:
    """Tam halkayı kirişlere, simetrik H sınırına ve gerçek yay zarflarına çevirir.

    Her çeyrek (1-q²,2q)/(1+q²), 0≤q≤1 ile tam rasyonel parametrelenir.
    ||r''(q)||≤8 max(rx,ry) olduğundan n eşit q aralığında kiriş hatası
    max(rx,ry)/n²'yi aşmaz. Kiriş uçlarının aralık→float dönüşüm hatası
    ayrıca eklenir. Zarflar gerçek yayları ve çizim kirişlerini birlikte kapsar.
    """
    if not is_full_conic(piece):
        raise ValueError(
            "Konik sertifikası yalnızca kanonik tam halkaları destekler; yay belirsiz."
        )
    p = piece.params
    radii = [p["radius"]] * 2 if piece.kind == "circle" else p["radii"]
    radius = max(radii)
    if not np.isfinite(radius) or radius <= 0:
        raise ValueError("Konik yarıçapı geçersiz.")
    n = max(4, math.ceil(math.sqrt(radius / tolerance)) + 1)
    if 4 * n > 20000:
        raise ValueError("Konik sertifikası 20.000 kiriş sınırını aşıyor.")
    unit = [(Q(n * n - k * k, n * n + k * k), Q(2 * k * n, n * n + k * k)) for k in range(n)]
    unit_i = _rational_interval(unit)
    x, y = _rotate_quadrants(
        Interval(unit_i.lo[:, 0], unit_i.hi[:, 0]),
        Interval(unit_i.lo[:, 1], unit_i.hi[:, 1]),
        p.get("direction", 1),
    )
    points = _mapped(piece, x, y)
    approximation = points.lo + (points.hi - points.lo) / 2
    endpoint_error = float(np.max(_norm_upper(points - Interval.point(approximation))))
    interpolation = _rational_interval(Q(float(radius)) / (n * n))
    bound = float((interpolation + Interval.point(endpoint_error)).hi)
    if not np.isfinite(approximation).all() or not bound <= tolerance:
        raise ValueError("Konik kapsaması istenen düzleştirme toleransına ulaşamadı.")
    rational = [tuple(Q(float(v)) for v in point) for point in approximation]
    leaves = [[a, b] for a, b in zip(rational, rational[1:] + rational[:1], strict=True)]
    # q bağımlılıkları unutulsa bile aralık uzantısı tüm yayı kapsar.
    q = _rational_interval([Q(k, n) for k in range(n + 1)])
    q = Interval(q.lo[:-1], q.hi[1:])
    square = q * q
    denominator = Interval.point(1) + square
    x, y = _rotate_quadrants(
        (Interval.point(1) - square) / denominator,
        Interval.point(2) * q / denominator,
        p.get("direction", 1),
    )
    boxes = _mapped(piece, x, y)
    endpoints = np.stack([approximation, np.roll(approximation, -1, axis=0)], axis=1)
    lo, hi = (
        np.minimum(boxes.lo, endpoints.min(axis=1)),
        np.maximum(boxes.hi, endpoints.max(axis=1)),
    )
    envelopes = []
    for a, b in zip(lo, hi, strict=True):
        envelopes.append(
            [
                (Q(float(a[0])), Q(float(a[1]))),
                (Q(float(b[0])), Q(float(a[1]))),
                (Q(float(b[0])), Q(float(b[1]))),
                (Q(float(a[0])), Q(float(b[1]))),
            ]
        )
    return leaves, bound, envelopes
