"""Kayıtlı kübik B-spline'ı tam rasyonel Bernstein aralıklarına dönüştürür."""

from fractions import Fraction as Q

from .models import CurvePiece

Point = tuple[Q, Q]


def _de_boor(knots: list[Q], controls: list[Point], degree: int, t: Q, span: int) -> Point:
    """Seçili düğüm aralığının kapalı uçlarında da tam de Boor değeri hesaplar."""
    values = list(controls[span - degree : span + 1])
    for level in range(1, degree + 1):
        for j in range(degree, level - 1, -1):
            i = span - degree + j
            denominator = knots[i + degree - level + 1] - knots[i]
            if denominator <= 0:
                raise ValueError("Rasyonel spline dönüşümünde sıfır düğüm aralığı.")
            u = (t - knots[i]) / denominator
            values[j] = tuple(
                (1 - u) * a + u * b for a, b in zip(values[j - 1], values[j], strict=True)
            )
    return values[degree]


def bezier_spans(piece: CurvePiece) -> list[list[Point]]:
    """Kübik spline'ın geçerli aralıktaki tam Bernstein kontrol dizilerini verir.

    Katsayılar ve düğümler binary64 değerlerinin tam dyadik yorumudur. Sonuç,
    uç değerleri ve türevleri rasyonel de Boor ile bulunan Hermite eşdeğeridir;
    SciPy'nin yuvarlanmış türev değerleri sertifikada kullanılmaz. Birim ve
    koordinatlar çalışma düzlemidir. Süreksiz/içte çok katlı düğüm reddedilir.
    """
    p = piece.params
    if piece.kind != "bspline" or p["degree"] != 3:
        raise ValueError("Rasyonel dönüşüm yalnızca kübik B-spline destekler.")
    knots = [Q(float(x)) for x in p["knots"]]
    controls = [tuple(Q(float(x)) for x in v) for v in p["controls"]]
    left, right = (Q(float(x)) for x in piece.interval)
    if len(knots) != len(controls) + 4 or not knots[3] <= left < right <= knots[-4]:
        raise ValueError("Rasyonel spline boyut veya geçerlilik aralığı hatalı.")
    if any(b < a for a, b in zip(knots[:-1], knots[1:], strict=True)):
        raise ValueError("Spline düğümleri artmıyor.")
    inner = [t for t in knots if left < t < right]
    if len(inner) != len(set(inner)):
        raise ValueError("Sertifikada iç spline düğümleri basit olmalıdır.")
    derivative = []
    for i, (a, b) in enumerate(zip(controls[:-1], controls[1:], strict=True)):
        width = knots[i + 4] - knots[i + 1]
        if width <= 0:
            raise ValueError("Spline türevinde sıfır düğüm aralığı.")
        derivative.append(tuple(3 * (y - x) / width for x, y in zip(a, b, strict=True)))
    spans = []
    for j in range(3, len(controls)):
        a, b = max(left, knots[j]), min(right, knots[j + 1])
        if a >= b:
            continue
        c0, c3 = (_de_boor(knots, controls, 3, t, j) for t in (a, b))
        d0, d3 = (_de_boor(knots[1:-1], derivative, 2, t, j - 1) for t in (a, b))
        spans.append(
            [
                c0,
                tuple(x + (b - a) * d / 3 for x, d in zip(c0, d0, strict=True)),
                tuple(x - (b - a) * d / 3 for x, d in zip(c3, d3, strict=True)),
                c3,
            ]
        )
        if len(spans) > 2048:
            raise ValueError("Rasyonel spline dönüşümü 2048 aralık sınırını aştı.")
    if not spans:
        raise ValueError("Spline'ın boş olmayan bir geçerli aralığı bulunamadı.")
    return spans
