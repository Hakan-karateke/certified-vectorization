"""Ortak dyadik uçlu, pozitif ağırlıklı rasyonel kuadratik konik yaylar.

Çemberde bulge=tan(yönlü merkez açısı/4); elipste üç kontrol ve orta ağırlık
asıl katsayılardır. Merkez/açı önbelleği saklanmaz. Bütün koordinatlar çalışma
düzlemindedir; artan [a,b] aralığı u=(t-a)/(b-a) ile [0,1]'e dönüştürülür.
"""

from fractions import Fraction as Q

import numpy as np

from .models import CurvePiece


def is_rational_arc(piece: CurvePiece) -> bool:
    """Tam halka ve eski açısal yaydan yeni rasyonel yay sözleşmesini ayırır."""
    return piece.kind in {"circle", "ellipse"} and "arc" in piece.params


def homogeneous_controls(piece: CurvePiece) -> list[tuple[Q, Q, Q]]:
    """Katsayıları tam rasyonel (wx,wy,w) kontrollerine dönüştürür.

    Pozitif ağırlık, sonlu/dejenere olmayan yay ve tek yetkili parametre kümesi
    zorunludur. Böylece payda [0,1]'de pozitiftir ve dışbükey zarf geçerlidir.
    """
    if not is_rational_arc(piece) or set(piece.params) != {"arc"}:
        raise ValueError("Rasyonel yay yalnızca arc parametrelerini içermelidir.")
    arc = piece.params["arc"]
    if piece.kind == "circle":
        if set(arc) != {"a", "b", "bulge"}:
            raise ValueError("Çember yayı a, b ve bulge içermelidir.")
        if np.asarray([arc["a"], arc["b"]]).shape != (2, 2):
            raise ValueError("Yay uçları iki boyutlu olmalıdır.")
        a, b = [tuple(Q(float(x)) for x in arc[k]) for k in ("a", "b")]
        s = Q(float(arc["bulge"]))
        if a == b or not 0 < abs(s) < 1:
            raise ValueError("Çember yayı farklı uçlar ve 0<|bulge|<1 gerektirir.")
        w = (1 - s * s) / (1 + s * s)
        j = (a[1] - b[1], b[0] - a[0])
        interior = tuple(w * (a[k] + b[k]) / 2 - s * j[k] / (1 + s * s) for k in (0, 1))
        return [(*a, Q(1)), (*interior, w), (*b, Q(1))]
    if set(arc) != {"controls", "weight"} or np.asarray(arc["controls"]).shape != (3, 2):
        raise ValueError("Elips yayı üç 2B kontrol ve weight içermelidir.")
    a, p, b = [tuple(Q(float(x)) for x in row) for row in arc["controls"]]
    w = Q(float(arc["weight"]))
    cross = (p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0])
    if not 0 < w < 1 or cross == 0:
        raise ValueError("Eliptik yay 0<weight<1 ve doğrusal olmayan kontroller gerektirir.")
    return [(*a, Q(1)), (w * p[0], w * p[1], w), (*b, Q(1))]


def arc_evaluate(piece: CurvePiece, t: np.ndarray, derivative: bool = False) -> np.ndarray:
    """Rasyonel Bernstein toplamını veya t'ye göre birinci türevini hesaplar."""
    h = np.asarray(homogeneous_controls(piece), dtype=float)
    a, b = piece.interval
    u = (t - a) / (b - a)
    basis = np.column_stack(((1 - u) ** 2, 2 * u * (1 - u), u**2))
    v = basis @ h
    if derivative:
        d = 2 * np.column_stack((1 - u, u)) @ np.diff(h, axis=0) / (b - a)
        return (d[:, :2] * v[:, 2:] - v[:, :2] * d[:, 2:]) / v[:, 2:] ** 2
    return v[:, :2] / v[:, 2:]


def arc_flatten(piece: CurvePiece, tolerance: float) -> np.ndarray:
    """Homojen de Casteljau ve sonlu kiriş kapsülüyle kontrollü poligon üretir.

    Bu hızlı yol float64 kullanır; bağımsız sertifika aynı bölmeyi tam rasyonel
    katsayılarla tekrarlar. Derinlik/iş sınırında sessiz kabul yapılmaz.
    """
    original = np.asarray(homogeneous_controls(piece), dtype=float)
    output = [original[0, :2] / original[0, 2]]
    pending = [(original, 0)]
    while pending:
        h, depth = pending.pop()
        c = h[:, :2] / h[:, 2:]
        d = c[-1] - c[0]
        norm = float(d @ d)
        u = np.clip((c - c[0]) @ d / norm, 0, 1) if norm else np.zeros(3)
        bound = np.linalg.norm(c - c[0] - u[:, None] * d, axis=1).max()
        if bound <= tolerance:
            output.append(c[-1])
        elif depth < 24 and len(output) + len(pending) < 200000:
            left, right = (h[:-1] + h[1:]) / 2
            mid = (left + right) / 2
            pending.extend(
                [
                    (np.array([mid, right, h[-1]]), depth + 1),
                    (np.array([h[0], left, mid]), depth + 1),
                ]
            )
        else:
            raise ValueError("Rasyonel yay değerlendirmesi kaynak sınırında yakınsamadı.")
    return np.asarray(output)


def arc_equation(piece: CurvePiece) -> str:
    """Asıl katsayıları ve türetilen rasyonel formülü kayıpsız basamaklarla açıklar."""
    arc = piece.params["arc"]
    if piece.kind == "circle":
        definition = (
            f"A={arc['a']}; B={arc['b']}; s={arc['bulge']:.17g}; "
            "J=(-(B_y-A_y),B_x-A_x); w=(1-s²)/(1+s²); "
            "V=w(A+B)/2-s*J/(1+s²)"
        )
    else:
        definition = f"A,P,B={arc['controls']}; w={arc['weight']:.17g}; V=w*P"
    return "r(t)=((1-u)² A+2u(1-u)V+u² B)/((1-u)²+2w*u(1-u)+u²); u=(t-a)/(b-a); " + definition
