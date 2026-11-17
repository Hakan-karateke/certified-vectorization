"""Sonlu eğrilerin ortak değerlendirme, denklem ve kontrollü çokgenleştirme sözleşmesi."""

import math
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.interpolate import BSpline

from .models import CurvePiece
from .rational_arcs import arc_equation, arc_evaluate, arc_flatten, is_rational_arc

Array = NDArray[np.float64]


def is_full_conic(piece: CurvePiece) -> bool:
    """Kanonik [0,float(2π)] aralığının tam halka sözleşmesini tanır.

    full_turn=False açık yaydır. Eski dosyalarda bayrak yoksa aynı kanonik
    aralık tam halka olarak yükseltilir. Tam halkada faz 2πt/float(2π)'dir;
    kayıtlı sağ uç gerçek 2π'nin sayısal parametre etiketidir.
    """
    return (
        piece.kind in {"circle", "ellipse"}
        and not is_rational_arc(piece)
        and piece.params.get("full_turn", True) is True
        and piece.interval == [0.0, float(2 * np.pi)]
    )


def evaluate(piece: CurvePiece, t: Array | list[float]) -> Array:
    """Geçerli aralıktaki t değerlerinde (N,2) çalışma koordinatlarını üretir.

    Aralık dışına uzatma yapılmaz; hatalı parametre ValueError üretir.
    """
    t = np.atleast_1d(np.asarray(t, dtype=float))
    a, b = piece.interval
    if not np.isfinite(t).all() or np.any(t < a - 1e-12) or np.any(t > b + 1e-12):
        raise ValueError("Eğri parametresi geçerlilik aralığının dışında.")
    p = piece.params
    if is_rational_arc(piece):
        return arc_evaluate(piece, t)
    if piece.kind == "line":
        return np.asarray(p["a"]) + ((t - a) / (b - a))[:, None] * (np.asarray(p["b"]) - p["a"])
    if piece.kind in {"circle", "ellipse"}:
        if is_full_conic(piece):
            t = np.where((t == a) | (t == b), 0.0, t)
        t = p.get("direction", 1) * t
        center = np.asarray(p["center"])
        rx, ry = (p["radius"], p["radius"]) if piece.kind == "circle" else p["radii"]
        angle = p.get("rotation", 0.0)
        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        return center + np.column_stack((rx * np.cos(t), ry * np.sin(t))) @ rotation.T
    if piece.kind == "bezier":
        u = (t - a) / (b - a)
        weights = np.column_stack(((1 - u) ** 3, 3 * (1 - u) ** 2 * u, 3 * (1 - u) * u**2, u**3))
        return weights @ np.asarray(p["controls"])
    if piece.kind == "bspline":
        return BSpline(p["knots"], p["controls"], p["degree"], extrapolate=False)(t)
    if piece.kind == "fourier":
        order = np.arange(1, len(p["cos"]) + 1)
        phase = t[:, None] * order
        return (
            np.asarray(p["center"])
            + np.cos(phase) @ np.asarray(p["cos"])
            + np.sin(phase) @ np.asarray(p["sin"])
        )
    raise ValueError(f"Desteklenmeyen eğri: {piece.kind}")


def new_piece(
    kind: str, params: dict[str, Any], interval: list[float], boundary_id: int, component_id: int
) -> CurvePiece:
    """Uçları katsayılardan hesaplayıp tek koordinat sözleşmesinde parça kurar."""
    piece = CurvePiece(kind, params, interval, [], [], boundary_id, component_id)
    piece.start, piece.end = evaluate(piece, interval).tolist()
    return piece


def _flatten_bezier(controls: Array, tolerance: float) -> Array:
    """De Casteljau bölmesiyle eğri-kiriş Hausdorff üst sınırını denetler.

    Kontrol çokgeninin sonlu kiriş kapsülünde bulunması, dışbükey zarf ve
    sürekli izdüşümle iki yönlü sınırı verir. Derinlik 24'te yakınsamama hatadır.
    """
    output = [controls[0]]
    stack = [(controls, 0)]
    while stack:
        c, depth = stack.pop()
        d = c[-1] - c[0]
        norm = float(d @ d)
        u = np.clip((c - c[0]) @ d / norm, 0, 1) if norm else np.zeros(4)
        bound = float(np.max(np.linalg.norm(c - c[0] - u[:, None] * d, axis=1)))
        if bound <= tolerance:
            output.append(c[-1])
            continue
        if depth >= 24 or len(output) + len(stack) > 200000:
            raise ValueError("Bézier değerlendirmesi toleransa yakınsamadı.")
        c01, c12, c23 = (c[:-1] + c[1:]) / 2
        c012, c123 = (c01 + c12) / 2, (c12 + c23) / 2
        mid = (c012 + c123) / 2
        stack.append((np.array([mid, c123, c23, c[3]]), depth + 1))
        stack.append((np.array([c[0], c01, c012, mid]), depth + 1))
    return np.asarray(output)


def flatten(piece: CurvePiece, tolerance: float) -> Array:
    """Gerçek eğriye iki yönlü uzaklığı en çok tolerance olan poligon üretir.

    Doğrular tamdır. Elips/çemberde ||r''|| Δt²/8 doğrusal ara değerleme
    sınırı; kübik spline'da her düğüm aralığının tam Bézier eşdeğeri kullanılır.
    Bunlar kayan nokta hesabıdır; aralık aritmetiği sertifikası değildir.
    """
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Değerlendirme toleransı pozitif olmalıdır.")
    if is_rational_arc(piece):
        return arc_flatten(piece, tolerance)
    if piece.kind == "line":
        return evaluate(piece, piece.interval)
    if piece.kind == "bezier":
        return _flatten_bezier(np.asarray(piece.params["controls"]), tolerance)
    a, b = piece.interval
    if piece.kind == "fourier":
        order = np.arange(1, len(piece.params["cos"]) + 1)
        bound = float(
            np.sum(
                order**2
                * (
                    np.linalg.norm(piece.params["cos"], axis=1)
                    + np.linalg.norm(piece.params["sin"], axis=1)
                )
            )
        )
        count = max(16, math.ceil((b - a) * math.sqrt(bound / (8 * tolerance))))
        if count > 200000:
            raise ValueError("Fourier değerlendirmesi nokta sınırını aşıyor.")
        return evaluate(piece, np.linspace(a, b, count + 1))
    if piece.kind in {"circle", "ellipse"}:
        radius = piece.params["radius"] if piece.kind == "circle" else max(piece.params["radii"])
        count = max(4, math.ceil(abs(b - a) * math.sqrt(radius / (8 * tolerance))))
        if count > 200000:
            raise ValueError("Eğri değerlendirme nokta sınırı aşıldı.")
        return evaluate(piece, np.linspace(a, b, count + 1))
    if piece.kind == "bspline":
        p = piece.params
        spline = BSpline(p["knots"], p["controls"], p["degree"], extrapolate=False)
        if p["degree"] != 3:
            raise ValueError("Yalnızca kübik B-spline desteklenir.")
        knots = np.unique([a, *[k for k in p["knots"] if a < k < b], b])
        parts = []
        for left, right in zip(knots[:-1], knots[1:], strict=True):
            q0, q3 = spline(left), spline(right)
            controls = np.array(
                [
                    q0,
                    q0 + (right - left) * spline(left, 1) / 3,
                    q3 - (right - left) * spline(right, 1) / 3,
                    q3,
                ]
            )
            parts.append(_flatten_bezier(controls, tolerance)[:-1])
        return np.vstack([*parts, evaluate(piece, [b])])
    raise ValueError("Bilinmeyen eğri türü.")


def model_rings(pieces: list[CurvePiece], tolerance: float) -> dict[int, Array]:
    """Sınır kimliğine göre kapalı, sıralı poligonları üretir; aralıkları korur."""
    grouped: dict[int, list[Array]] = {}
    for piece in pieces:
        grouped.setdefault(piece.boundary_id, []).append(flatten(piece, tolerance)[:-1])
    return {
        i: np.vstack([*parts, pieces_for_boundary(pieces, i)[-1].end])
        for i, parts in grouped.items()
    }


def pieces_for_boundary(pieces: list[CurvePiece], boundary_id: int) -> list[CurvePiece]:
    """Belirtilen sınırın parçalarını kayıt sırasıyla döndürür."""
    return [p for p in pieces if p.boundary_id == boundary_id]


def tangent(piece: CurvePiece, end: bool = False) -> Array:
    """Birleşim tanısı için ilerleme yönündeki birinci türevi döndürür."""
    a, b = piece.interval
    t = b if end else a
    p = piece.params
    if is_rational_arc(piece):
        return arc_evaluate(piece, np.asarray([t]), derivative=True)[0]
    if piece.kind == "line":
        return (np.asarray(p["b"]) - p["a"]) / (b - a)
    if piece.kind == "bezier":
        c = np.asarray(p["controls"])
        return 3 * (c[-1] - c[-2] if end else c[1] - c[0]) / (b - a)
    if piece.kind == "bspline":
        return BSpline(p["knots"], p["controls"], 3)(t, 1)
    if piece.kind == "fourier":
        order = np.arange(1, len(p["cos"]) + 1)
        return -(order * np.sin(order * t)) @ np.asarray(p["cos"]) + (
            order * np.cos(order * t)
        ) @ np.asarray(p["sin"])
    rx, ry = (p["radius"], p["radius"]) if piece.kind == "circle" else p["radii"]
    angle = p.get("rotation", 0)
    direction = p.get("direction", 1)
    t *= direction
    return (
        direction
        * np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        @ np.array([-rx * np.sin(t), ry * np.cos(t)])
    )


def equation(piece: CurvePiece) -> str:
    """Katsayıları 17 anlamlı basamakla ve geçerlilik aralığıyla yazdırır."""
    p = piece.params

    def fmt(values):
        return "(" + ", ".join(f"{v:.17g}" for v in values) + ")"

    a, b = piece.interval
    if is_rational_arc(piece):
        body = arc_equation(piece)
    elif piece.kind == "line":
        start, delta = np.asarray(p["a"]), np.asarray(p["b"]) - p["a"]
        body = f"r(t)={fmt(start)}+(t-({a:.17g}))/({b - a:.17g})*{fmt(delta)}"
    elif piece.kind in {"circle", "ellipse"}:
        radii = [p["radius"]] * 2 if piece.kind == "circle" else p["radii"]
        phase = "φ" if is_full_conic(piece) else "t"
        body = f"r(t)={fmt(p['center'])}+R({p.get('rotation', 0):.17g})*({radii[0]:.17g} cos({p.get('direction', 1)}{phase}), {radii[1]:.17g} sin({p.get('direction', 1)}{phase}))"
        if is_full_conic(piece):
            body += f"; φ=2πt/({b:.17g}); tam kapalı halka"
    elif piece.kind == "bezier":
        body = "r(t)=sum[k=0..3] binom(3,k)(1-u)^(3-k)u^k P_k; "
        body += "u=(t-a)/(b-a); P=" + ", ".join(fmt(c) for c in p["controls"])
    elif piece.kind == "fourier":
        body = f"r(t)={fmt(p['center'])}+sum[k=1..{len(p['cos'])}](a_k cos(kt)+b_k sin(kt)); a={p['cos']}; b={p['sin']}"
    else:
        body = f"r(t)=sum c_i N_(i,3)(t); c={p['controls']}; knots={p['knots']}"
    return body + f"; {min(a, b):.17g}<=t<={max(a, b):.17g}; yön {a:.17g} -> {b:.17g}"
