"""Çok ölçekli köşeler ve sonlu aday grafiğinde maliyet en küçük yol araması."""

from threading import Event

import numpy as np

from .curves import evaluate, new_piece
from .geometry import simplify_boundary
from .models import Boundary, CurvePiece


def _fit_cubic(q: np.ndarray, target: float) -> tuple[np.ndarray, float] | None:
    """Sabit uçlarla kübik uydurur; monoton yeniden parametreleme uygular.

    Referansın her kenarına karşı fark kübiğinin Bernstein kontrol normları
    bütün parametre aralığı için eşleşme üst sınırı verir. Bu aday üretimindeki
    float64 sınırıdır; bağımsız ölçüm ve isteğe bağlı sertifika ayrıca yapılır.
    """
    if len(q) < 3:
        return None
    t = np.r_[0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
    if t[-1] <= 0:
        return None
    t /= t[-1]
    controls = None
    for _ in range(5):
        w1, w2 = 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t**2
        matrix = np.column_stack([w1, w2])
        rhs = q - (1 - t[:, None]) ** 3 * q[0] - t[:, None] ** 3 * q[-1]
        baseline = np.array([q[0] + (q[-1] - q[0]) / 3, q[0] + 2 * (q[-1] - q[0]) / 3])
        correction, _, rank, _ = np.linalg.lstsq(matrix, rhs - matrix @ baseline, rcond=None)
        if rank < 2:
            return None
        controls = np.vstack([q[0], baseline + correction, q[-1]])
        if np.max(np.linalg.norm(controls, axis=1)) > 1e5:
            return None
        u = t[:, None]
        values = (
            (1 - u) ** 3 * controls[0]
            + 3 * (1 - u) ** 2 * u * controls[1]
            + 3 * (1 - u) * u * u * controls[2]
            + u**3 * controls[3]
        )
        first = 3 * (
            (1 - u) ** 2 * (controls[1] - controls[0])
            + 2 * (1 - u) * u * (controls[2] - controls[1])
            + u * u * (controls[3] - controls[2])
        )
        second = 6 * (
            (1 - u) * (controls[2] - 2 * controls[1] + controls[0])
            + u * (controls[3] - 2 * controls[2] + controls[1])
        )
        denominator = np.sum(first * first + (values - q) * second, axis=1)
        change = np.divide(
            np.sum((values - q) * first, axis=1),
            denominator,
            out=np.zeros_like(t),
            where=denominator > 1e-10,
        )
        updated = np.clip(
            t - change, np.r_[0, (t[:-1] + t[1:]) / 2], np.r_[(t[:-1] + t[1:]) / 2, 1]
        )
        updated[0], updated[-1] = 0, 1
        if np.max(np.abs(updated - t)) < 1e-7:
            break
        t = updated
    piece = new_piece("bezier", {"controls": controls.tolist()}, [0.0, 1.0], 0, 0)
    r = evaluate(piece, t)
    u = t[:, None]
    derivative = 3 * (
        (1 - u) ** 2 * (controls[1] - controls[0])
        + 2 * (1 - u) * u * (controls[2] - controls[1])
        + u * u * (controls[3] - controls[2])
    )
    dt = np.diff(t)[:, None]
    ref_delta = np.diff(q, axis=0)
    differences = np.stack(
        [
            r[:-1] - q[:-1],
            r[:-1] + dt * derivative[:-1] / 3 - q[:-1] - ref_delta / 3,
            r[1:] - dt * derivative[1:] / 3 - q[:-1] - 2 * ref_delta / 3,
            r[1:] - q[1:],
        ],
        axis=1,
    )
    bound = float(np.max(np.linalg.norm(differences, axis=2)))
    return (controls, bound) if bound <= target else None


def corner_graph(
    boundary: Boundary,
    index: int,
    component: int,
    epsilon: float,
    *,
    angle_degrees: float = 45.0,
    target_factor: float = 0.72,
    cancel: Event | None = None,
) -> tuple[list[CurvePiece], dict]:
    """Köşeleri zorunlu düğüm yapıp yerel doğru/kübik grafiğinde DP çalıştırır.

    Her kenar referansın ardışık bir alt zincirini temsil eder; aralık uçları
    piksel sınırı köşeleridir. Sonuç yalnızca kurulan sonlu DAG'de en küçük
    bit maliyetli yoldur. Global topoloji sonradan bütün modelde doğrulanır.
    """
    v = np.asarray(boundary.vertices, dtype=float)
    lengths = np.linalg.norm(np.roll(v, -1, axis=0) - v, axis=1)
    s = np.r_[0, np.cumsum(lengths)]
    perimeter = s[-1]
    window = max(4.0, 4 * epsilon)
    extended_s = np.r_[s[:-1] - perimeter, s, s[1:] + perimeter]
    extended_v = np.vstack([v, v, v[0], v[1:], v[0]])
    before = np.column_stack(
        [np.interp(s[:-1] - window, extended_s, extended_v[:, k]) for k in (0, 1)]
    )
    after = np.column_stack(
        [np.interp(s[:-1] + window, extended_s, extended_v[:, k]) for k in (0, 1)]
    )
    left, right = v - before, after - v
    cosine = np.sum(left * right, axis=1) / np.maximum(
        np.linalg.norm(left, axis=1) * np.linalg.norm(right, axis=1), 1e-12
    )
    angles = np.degrees(np.arccos(np.clip(cosine, -1, 1)))
    corners = []
    for candidate in np.argsort(-angles):
        if angles[candidate] < angle_degrees:
            break
        distance = (
            np.abs(s[candidate] - s[np.asarray(corners, dtype=int)]) if corners else np.array([])
        )
        if not len(distance) or np.min(np.minimum(distance, perimeter - distance)) >= window:
            corners.append(int(candidate))
    seam = corners[0] if corners else 0
    v = np.roll(v, -seam, axis=0)
    corners = sorted((i - seam) % len(v) for i in corners)
    lengths = np.linalg.norm(np.roll(v, -1, axis=0) - v, axis=1)
    s = np.r_[0, np.cumsum(lengths)]
    guide = simplify_boundary(
        Boundary([tuple(p) for p in v], boundary.kind, len(v)),
        epsilon * min(0.68, target_factor * 0.96),
    )
    lookup = {tuple(p): i for i, p in enumerate(v)}
    nodes = sorted({0, len(v), *[lookup[tuple(p)] for p in guide.vertices]})
    # Köşe adayları güvenli RDP kılavuzundaki en yakın köşeye taşınır; yeni
    # uç eklemek kılavuzun yerel hata koşulunu bozmasın.
    corners = sorted(
        {
            min(nodes[:-1], key=lambda i: min(abs(s[i] - s[c]), s[-1] - abs(s[i] - s[c])))
            for c in corners
        }
    )
    if len(nodes) > 768:
        raise ValueError("Köşe grafiği 768 düğüm sınırını aştı.")
    q = np.vstack([v, v[0]])
    forced = set(corners + [len(v)])
    costs = [float("inf")] * len(nodes)
    costs[0] = 0
    predecessors = {}
    edge_count = 0
    target = epsilon * target_factor
    for i, start in enumerate(nodes[:-1]):
        if cancel is not None and cancel.is_set():
            from .fitting import AnalysisCancelled

            raise AnalysisCancelled("Köşe grafiği araması iptal edildi.")
        stop = next((j for j in range(i + 1, len(nodes)) if nodes[j] in forced), len(nodes) - 1)
        for j in range(i + 1, min(stop, i + 24) + 1):
            chain = q[start : nodes[j] + 1]
            a, b = chain[0], chain[-1]
            d = b - a
            denominator = float(d @ d)
            if denominator <= 1e-12:
                continue
            parameter = np.clip((chain - a) @ d / denominator, 0, 1)
            error = float(np.max(np.linalg.norm(chain - a - parameter[:, None] * d, axis=1)))
            if error <= target:
                piece = new_piece(
                    "line", {"a": a.tolist(), "b": b.tolist()}, [0.0, 1.0], index, component
                )
                weight = 424
            else:
                fitted = _fit_cubic(chain, target)
                if fitted is None:
                    continue
                controls, error = fitted
                piece = new_piece(
                    "bezier", {"controls": controls.tolist()}, [0.0, 1.0], index, component
                )
                weight = 680
            edge_count += 1
            piece.errors = {"proposal_correspondence_upper": error, "solver": "corner_graph_dp"}
            if costs[i] + weight < costs[j]:
                costs[j] = costs[i] + weight
                predecessors[j] = (i, piece)
    if len(nodes) - 1 not in predecessors:
        raise ValueError("Köşe grafiğinde toleransı sağlayan tam yol bulunamadı.")
    pieces = []
    position = len(nodes) - 1
    while position:
        position, piece = predecessors[position]
        pieces.append(piece)
    pieces.reverse()
    return pieces, {
        "nodes": len(nodes),
        "edges": edge_count,
        "forced_corners": len(corners),
        "cost_bits": costs[-1],
        "angle_degrees": angle_degrees,
        "target_factor": target_factor,
        "optimality": "Exact shortest path only in constructed locally admissible DAG; global topology checked afterwards.",
    }
