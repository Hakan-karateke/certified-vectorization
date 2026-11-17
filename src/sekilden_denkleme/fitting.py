"""Sınırlı aday araması, yerel eğri uydurma ve hata-maliyet Pareto seçimi."""

import copy
import math
import time
from collections.abc import Callable
from threading import Event

import numpy as np
from scipy.interpolate import make_interp_spline
from scipy.optimize import dual_annealing, least_squares
from shapely.geometry import Polygon

from .adaptive import corner_graph
from .certification import certify
from .curves import evaluate, new_piece
from .evaluation import EvaluationContext, complexity, evaluate_candidate
from .geometry import sample_boundaries, simplify_boundary
from .models import AnalysisConfig, Boundary, Candidate, CurvePiece
from .optimal_arcs import min_piece_boundaries
from .optimal_polygon import min_link_boundaries
from .topology_simplification import simplify_topology


class AnalysisCancelled(RuntimeError):
    """Kullanıcı iptalini sayısal başarısızlıktan ayırır."""


def checkpoint(cancel: Event | None) -> None:
    """İptal isteğinde kısmi sonucu yayımlamadan işlemi sonlandırır."""
    if cancel is not None and cancel.is_set():
        raise AnalysisCancelled("İşlem kullanıcı tarafından iptal edildi.")


def polygon_pieces(boundary: Boundary, index: int, component: int) -> list[CurvePiece]:
    """Kapalı çokgeni sonlu [0,1] doğru parçalarına kayıpsız dönüştürür."""
    v = boundary.vertices
    return [
        new_piece("line", {"a": list(a), "b": list(b)}, [0.0, 1.0], index, component)
        for a, b in zip(v, v[1:] + v[:1], strict=True)
    ]


def primitive(boundary: Boundary, index: int, component: int, kind: str) -> CurvePiece:
    """Çember/elipsin tam halkasını normalize koordinatlarda uydurur.

    Çemberde radyal geometrik artık, elipste radyal ölçekli başlangıç artığı
    minimize edilir. Kabul kararı bu artığa değil bağımsız geometrik denetime
    dayanır. Elips olmayan genel konikler bu sürümde aday değildir.
    """
    points = (sample_boundaries([boundary], 512) - 500) / 500
    center = points.mean(axis=0)
    if kind == "circle":
        initial = [*center, np.mean(np.linalg.norm(points - center, axis=1))]

        def residual(p: np.ndarray) -> np.ndarray:
            """Normalize çember radyal artıklarını döndürür."""
            return np.linalg.norm(points - p[:2], axis=1) - p[2]

        fit = least_squares(
            residual,
            initial,
            bounds=([-5, -5, 1e-6], [5, 5, 10]),
            max_nfev=300,
            ftol=1e-11,
            xtol=1e-11,
            gtol=1e-11,
        )
        params = {"center": (500 + 500 * fit.x[:2]).tolist(), "radius": float(500 * fit.x[2])}
    else:
        values, vectors = np.linalg.eigh(np.cov(points.T))
        order = np.argsort(values)[::-1]
        angle = math.atan2(vectors[1, order[0]], vectors[0, order[0]])
        initial = [*center, *np.sqrt(np.maximum(2 * values[order], 1e-8)), angle]

        def residual(p: np.ndarray) -> np.ndarray:
            """Elipsin radyal ölçekli, başlangıç için kullanılan artığını verir."""
            c, s = np.cos(p[4]), np.sin(p[4])
            q = (points - p[:2]) @ np.array([[c, -s], [s, c]])
            return (np.sqrt((q[:, 0] / p[2]) ** 2 + (q[:, 1] / p[3]) ** 2) - 1) * min(p[2:4])

        fit = least_squares(
            residual,
            initial,
            bounds=([-5, -5, 1e-5, 1e-5, -20], [5, 5, 10, 10, 20]),
            max_nfev=400,
            ftol=1e-11,
            xtol=1e-11,
            gtol=1e-11,
        )
        params = {
            "center": (500 + 500 * fit.x[:2]).tolist(),
            "radii": (500 * fit.x[2:4]).tolist(),
            "rotation": float(fit.x[4]),
        }
    if not fit.success or not np.isfinite(fit.x).all():
        raise ValueError(f"{kind} uydurma yakınsamadı: {fit.message}")
    singular = np.linalg.svd(fit.jac, compute_uv=False)
    condition = float(singular[0] / singular[-1]) if singular[-1] > 1e-14 else None
    params["direction"] = -1 if boundary.kind == "outer" else 1
    params["full_turn"] = True
    piece = new_piece(kind, params, [0.0, 2 * np.pi], index, component)
    piece.errors = {
        "solver": "least_squares_trf",
        "jacobian_condition": condition,
        "nfev": fit.nfev,
        "converged": True,
    }
    return piece


def bezier_pieces(
    boundary: Boundary,
    index: int,
    component: int,
    target: float,
    mixed: bool = False,
    cancel: Event | None = None,
) -> list[CurvePiece]:
    """Kiriş parametreli kübik en küçük kareleri uyarlamalı bölmeyle uygular.

    Uçlar sabittir (C0). Maksimum örnek artığı hedefi aşarsa zincir ortadan
    bölünür; en fazla 2048 parça üretilir. C1 sürekliliği zorlanmaz; raporlanır.
    Bu yerel sezgiseldir, küresel en az parça çözümü değildir.
    """
    points = sample_boundaries([boundary], max(64, min(2048, 2 * len(boundary.vertices))))
    points = np.vstack([points, points[0]])
    middle = len(points) // 2
    stack = [points[middle:], points[: middle + 1]]
    pieces = []
    while stack:
        checkpoint(cancel)
        q = stack.pop()
        lengths = np.linalg.norm(np.diff(q, axis=0), axis=1)
        t = np.r_[0, np.cumsum(lengths)]
        if t[-1] <= 1e-12:
            continue
        t /= t[-1]
        chord = q[0] + t[:, None] * (q[-1] - q[0])
        if mixed and np.max(np.linalg.norm(q - chord, axis=1)) <= target:
            pieces.append(
                new_piece(
                    "line", {"a": q[0].tolist(), "b": q[-1].tolist()}, [0.0, 1.0], index, component
                )
            )
            continue
        if mixed and len(q) >= 5:
            arc = circle_arc(q, index, component, target)
            if arc is None:
                arc = ellipse_arc(q, index, component, target)
            if arc is not None:
                pieces.append(arc)
                continue
        w1, w2 = 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t**2
        matrix = np.column_stack([w1, w2])
        rhs = q - (1 - t[:, None]) ** 3 * q[0] - t[:, None] ** 3 * q[-1]
        baseline = np.array([q[0] + (q[-1] - q[0]) / 3, q[0] + 2 * (q[-1] - q[0]) / 3])
        correction, _, rank, singular = np.linalg.lstsq(matrix, rhs - matrix @ baseline, rcond=None)
        interior = baseline + correction
        controls = np.vstack([q[0], interior, q[-1]])
        piece = new_piece("bezier", {"controls": controls.tolist()}, [0.0, 1.0], index, component)
        piece.errors = {
            "fitting_rank": int(rank),
            "fitting_condition": float(singular[0] / singular[-1])
            if singular[-1] > 1e-14
            else None,
            "solver": "chord_parameter_linear_least_squares",
        }
        error = np.linalg.norm(evaluate(piece, t) - q, axis=1)
        if error.max() <= target or len(q) <= 4:
            pieces.append(piece)
        else:
            split = len(q) // 2
            stack.extend([q[split:], q[: split + 1]])
        if len(pieces) + len(stack) > 2048:
            raise ValueError("Bézier araması 2048 parça sınırını aştı.")
    return pieces


def circle_arc(points: np.ndarray, index: int, component: int, target: float) -> CurvePiece | None:
    """İki uçtan geçen çember merkezini orta dikme üzerinde tek değişkenle arar.

    Noktaların açısal sırası tek yönlü olmalıdır. Uç eşitliği yapısaldır;
    iç noktaların radyal artığı yalnızca aday üretiminde kullanılır.
    """
    a, b = points[0], points[-1]
    length = np.linalg.norm(b - a)
    if length < 1e-6:
        return None
    mid = (a + b) / 2
    normal = np.array([-(b - a)[1], (b - a)[0]]) / length
    q = points - mid
    rhs = np.sum(q * q, axis=1) - length**2 / 4
    column = 2 * q @ normal
    denominator = float(column @ column)
    if denominator < 1e-12:
        return None
    initial = float(column @ rhs / denominator)
    if abs(initial) > 1e6:
        return None

    along = q @ normal
    half = length / 2

    def residual(value: float) -> np.ndarray:
        """Uçlardan geçen çembere geometrik radyal uzaklığı döndürür."""
        return np.linalg.norm(q - value * normal, axis=1) - np.hypot(half, value)

    # Tek değişkenli sönümlü Gauss-Newton; türev analitiktir.
    offset, current = initial, residual(initial)
    cost = float(current @ current)
    for _ in range(30):
        radii = np.maximum(current + np.hypot(half, offset), 1e-12)
        gradient = -(along - offset) / radii - offset / np.hypot(half, offset)
        curvature = float(gradient @ gradient)
        if curvature < 1e-18:
            break
        step = -float(gradient @ current) / curvature
        while True:
            trial = residual(offset + step)
            trial_cost = float(trial @ trial)
            if trial_cost <= cost or abs(step) < 1e-10:
                break
            step /= 2
        if trial_cost > cost:
            break
        improved = cost - trial_cost
        offset, current, cost = offset + step, trial, trial_cost
        if abs(step) < 1e-9 * (1 + abs(offset)) or improved <= 1e-14 * (1 + cost):
            break
    if abs(offset) > 1e6 or np.max(np.abs(current)) > target:
        return None
    center = mid + offset * normal
    angles = np.unwrap(np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0]))
    direction = 1 if angles[-1] > angles[0] else -1
    if np.any(direction * np.diff(angles) < -1e-9) or abs(angles[-1] - angles[0]) > 2 * np.pi:
        return None
    bulge = float(np.tan((angles[-1] - angles[0]) / 4))
    # Büyük yaylar bölünür; pozitif ağırlık ve kararlı küçük yay sözleşmesi korunur.
    if not 1e-6 < abs(bulge) < 0.9:
        return None
    return new_piece(
        "circle",
        {"arc": {"a": a.tolist(), "b": b.tolist(), "bulge": bulge}},
        [0.0, 1.0],
        index,
        component,
    )


def ellipse_arc(points: np.ndarray, index: int, component: int, target: float) -> CurvePiece | None:
    """Sabit uçlu eliptik rasyonel kuadratiği sınırlı ağırlık aramasıyla önerir.

    Kiriş parametreleri sabittir; ağırlık için tek değişkenli sınırlı arama,
    orta kontrol için doğrusal en küçük kareler kullanılır. Bu geometrik optimum
    veya hata kanıtı değildir; aday ayrıca bütün sınır denetiminden geçer.
    """
    lengths = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    if lengths[-1] < 1e-6 or np.linalg.norm(points[-1] - points[0]) < 1e-6:
        return None
    u = lengths / lengths[-1]
    a, b = points[0], points[-1]

    def fit_weight(w: float) -> tuple[float, np.ndarray]:
        """Verilen pozitif ağırlıkta orta kontrolü ve kare artık toplamını verir."""
        middle = 2 * w * u * (1 - u)
        denominator = (1 - u) ** 2 + middle + u**2
        rhs = denominator[:, None] * points - (1 - u[:, None]) ** 2 * a - u[:, None] ** 2 * b
        control = middle @ rhs / (middle @ middle)
        residual = (rhs - middle[:, None] * control) / denominator[:, None]
        return float(np.sum(residual**2)), control

    # Ağırlık, üç düzeyli vektörel ızgara aramasıyla seçilir (çözünürlük ~8e-4).
    low, high = 0.15, 0.98
    base = (1 - u) * u
    for _ in range(3):
        weights = np.linspace(low, high, 17)
        middle = 2 * weights[:, None] * base
        denominator = (1 - u) ** 2 + middle + u**2
        rhs = denominator[:, :, None] * points - (1 - u[:, None]) ** 2 * a - u[:, None] ** 2 * b
        controls = np.einsum("kn,knd->kd", middle, rhs) / np.sum(middle * middle, axis=1)[:, None]
        residual = (rhs - middle[:, :, None] * controls[:, None, :]) / denominator[:, :, None]
        best = int(np.argmin(np.sum(residual**2, axis=(1, 2))))
        step = (high - low) / 16
        low, high = max(0.15, weights[best] - step), min(0.98, weights[best] + step)
    weight = float(weights[best])
    _, control = fit_weight(weight)
    try:
        piece = new_piece(
            "ellipse",
            {
                "arc": {
                    "controls": [a.tolist(), control.tolist(), b.tolist()],
                    "weight": weight,
                }
            },
            [0.0, 1.0],
            index,
            component,
        )
    except ValueError:
        return None
    if np.max(np.linalg.norm(evaluate(piece, u) - points, axis=1)) > target:
        return None
    piece.errors = {"solver": "bounded_weight_and_fixed_chord_lstsq", "converged": True}
    return piece


def spline_piece(boundary: Boundary, index: int, component: int, count: int) -> CurvePiece:
    """Eşit yay örneklerinde periyodik kübik interpolasyon adayı üretir.

    Düğüm sayısı sınırlı arama tarafından seçilir; interpolasyon tolerans
    garantisi değildir. Tüm eğri bağımsız hata/topoloji denetiminden geçer.
    """
    q = sample_boundaries([boundary], count)
    q = np.vstack([q, q[0]])
    spline = make_interp_spline(np.linspace(0, 1, len(q)), q, k=3, bc_type="periodic")
    return new_piece(
        "bspline",
        {"controls": spline.c.tolist(), "knots": spline.t.tolist(), "degree": 3},
        [0.0, 1.0],
        index,
        component,
    )


def fourier_piece(boundary: Boundary, index: int, component: int, order: int) -> CurvePiece:
    """Kapalı halkaya eşit yay parametresinde sınırlı Fourier serisi uydurur."""
    count = max(256, 8 * order)
    q = sample_boundaries([boundary], count)
    t = np.linspace(0, 2 * np.pi, count, endpoint=False)
    harmonics = np.arange(1, order + 1)
    matrix = np.column_stack(
        [np.ones(count), np.cos(t[:, None] * harmonics), np.sin(t[:, None] * harmonics)]
    )
    coefficients, _, rank, singular = np.linalg.lstsq(matrix, q, rcond=None)
    if rank != 2 * order + 1:
        raise ValueError("Fourier tasarım matrisi sayısal tekil.")
    piece = new_piece(
        "fourier",
        {
            "center": coefficients[0].tolist(),
            "cos": coefficients[1 : order + 1].tolist(),
            "sin": coefficients[order + 1 :].tolist(),
        },
        [0.0, 2 * np.pi],
        index,
        component,
    )
    piece.errors = {
        "solver": "equal_arc_fourier_lstsq",
        "design_condition": float(singular[0] / singular[-1]),
    }
    return piece


def certify_selection(
    candidates: list[Candidate],
    boundaries: list[Boundary],
    config: AnalysisConfig,
    cancel: Event | None = None,
    cost_key: str = "score_bits",
) -> str:
    """Seçimi sertifikayla açıklar; sıkı modda belirsiz adayı reddedip yeniden seçer."""
    while True:
        checkpoint(cancel)
        selected_id = select_candidate(candidates, config.preference, config.tolerance, cost_key)
        selected = next(c for c in candidates if c.id == selected_id)
        if config.certificate_mode == "off":
            return selected_id
        proof_started = time.perf_counter()
        proof = certify(
            selected,
            boundaries,
            config.tolerance,
            spacing=min(0.5, max(0.05, config.tolerance / 4)),
            delta=min(0.025, max(0.0001, config.tolerance / 32)),
        )
        proof["elapsed_seconds"] = time.perf_counter() - proof_started
        checkpoint(cancel)
        selected.metrics["certification"] = proof
        selected.metrics["verified_numerical_certificate"] = proof["verified_numerical_certificate"]
        selected.metrics["topology"]["analytic_isotopy_proven"] = proof["analytic_isotopy_proven"]
        if config.certificate_mode != "strict" or proof["status"] == "proven":
            return selected_id
        selected.accepted = False
        selected.reasons.append("Sıkı mod: hata/topoloji sertifikası kanıtlanamadı.")


def select_candidate(
    candidates: list[Candidate], preference: str, epsilon: float, cost_key: str = "score_bits"
) -> str:
    """Kabul edilmiş modellerin Pareto kümesinden belgeli tercihle seçim yapar."""
    valid = [c for c in candidates if c.accepted]
    if not valid:
        raise ValueError("Hata ve topoloji koşullarını sağlayan aday bulunamadı.")
    for c in candidates:
        c.pareto = c.accepted and not any(
            other.complexity[cost_key] <= c.complexity[cost_key]
            and other.metrics["hausdorff_upper_bound"] <= c.metrics["hausdorff_upper_bound"]
            and (
                other.complexity[cost_key] < c.complexity[cost_key]
                or other.metrics["hausdorff_upper_bound"] < c.metrics["hausdorff_upper_bound"]
            )
            for other in valid
        )
    front = [c for c in valid if c.pareto]
    if preference == "simple":

        def key(c):
            return (c.complexity[cost_key], c.metrics["hausdorff_upper_bound"])
    elif preference == "accurate":

        def key(c):
            return (c.metrics["hausdorff_upper_bound"], c.complexity[cost_key])
    else:
        cmin = min(c.complexity[cost_key] for c in front)

        def key(c):
            return (
                math.log2(1 + c.complexity[cost_key] / max(1, cmin))
                + (c.metrics["hausdorff_upper_bound"] / max(epsilon, 1e-12)) ** 2,
                c.complexity[cost_key],
            )

    return min(front, key=key).id


def fit_models(
    boundaries: list[Boundary],
    topology: dict,
    config: AnalysisConfig,
    cancel: Event | None = None,
    progress: Callable[[str], None] | None = None,
    plane: float = 1000.0,
) -> tuple[list[Candidate], str]:
    """Sınırlı aile/ölçek taramasını yürütür; kesin modeli güvenli geri dönüş tutar.

    plane çalışma düzleminin kenarıdır; yalnızca mdl_v1 kod uzunluğunu etkiler.
    """
    candidates = []
    epsilon = config.tolerance
    spacing = (
        min(config.evaluation_spacing, max(0.05, epsilon / 4))
        if epsilon
        else config.evaluation_spacing
    )
    delta = (
        min(config.flatten_tolerance, max(0.0001, epsilon / 16))
        if epsilon
        else config.flatten_tolerance
    )
    components = [r["component_id"] for r in topology["rings"]]
    context = EvaluationContext(boundaries, spacing)

    def add(
        family: str,
        pieces: list[CurvePiece],
        name: str,
        started: float,
        witness: dict | None = None,
    ) -> None:
        """Adayı ölçüp hata ve topoloji koşullarıyla kabul veya ret eder."""
        checkpoint(cancel)
        if progress:
            progress(f"Aday değerlendiriliyor: {name}")
        candidate = Candidate(name, family, pieces)
        if witness is not None:
            candidate.metrics["topology_witness"] = witness
        candidate.complexity = complexity(candidate, plane)
        try:
            evaluate_candidate(
                candidate,
                boundaries,
                topology,
                spacing,
                delta,
                context=context,
                workers=config.evaluation_workers,
            )
            if candidate.metrics["hausdorff_upper_bound"] > epsilon + 1e-9:
                candidate.reasons.append("Geometrik hata üst sınırı kullanıcı toleransını aşıyor.")
            candidate.accepted = not candidate.reasons
        except (ValueError, shapely_error()) as error:
            candidate.reasons.append(str(error))
        candidate.metrics["elapsed_seconds"] = time.perf_counter() - started
        candidates.append(candidate)

    started = time.perf_counter()
    exact = [p for i, b in enumerate(boundaries) for p in polygon_pieces(b, i, components[i])]
    add("exact", exact, "exact", started)
    # Piksel sınırlarında köşesel temas nedeniyle GEOS geçersiz halkalar olabilir.
    # Kesin model bu durumda da kayıpsızdır; yaklaşım güvenli biçimde reddedilir.
    candidates[0].accepted = True
    candidates[0].reasons = []
    candidates[0].metrics["topology"]["reference_exact_identity"] = True
    candidates[0].metrics["topology"]["reference_polygon_valid"] = candidates[0].metrics[
        "topology"
    ]["preserved"]
    candidates[0].metrics["topology"]["preserved"] = True
    candidates[0].metrics["topology"]["scope"] = "exact_reference_identity"
    candidates[0].metrics["topology"]["reasons"] = []
    if epsilon == 0 or config.family == "exact":
        candidates[0].pareto = True
        if progress:
            progress("Model seçimi ve bağımsız sertifika denetimi…")
        return candidates, certify_selection(candidates, boundaries, config, cancel)
    schedules = [("polygon", factor) for factor in (0.25, 0.55, 0.85)]
    if config.family != "polygon":
        families = (
            [
                "minlink",
                "linearc",
                "circle",
                "ellipse",
                "bezier",
                "bspline",
                "mixed",
                "adaptive",
                "fourier",
            ]
            if config.family == "auto"
            else [config.family]
        )
        if config.family == "auto" and (
            topology["contacts"] or any(not Polygon(b.vertices).is_valid for b in boundaries)
        ):
            families.append("topology")
        schedules += [
            (f, factor)
            for f in families
            for factor in (
                (0.3, 0.65)
                if f in {"bezier", "mixed"}
                else (8, 16, 32, 64)
                if f == "bspline"
                else (4, 8, 16, 32)
                if f == "fourier"
                else (0.72, 0.84)
                if f == "adaptive"
                else (0.7, 0.85)
                if f == "topology"
                else (1, 2)
                if f == "minlink"
                else (1,)
            )
        ]
    for family, factor in schedules:
        checkpoint(cancel)
        started = time.perf_counter()
        name = f"{family}-{factor:g}"
        try:
            pieces = []
            if family == "topology":
                simplified, witness = simplify_topology(boundaries, epsilon * factor, cancel)
                pieces = [
                    p for i, b in enumerate(simplified) for p in polygon_pieces(b, i, components[i])
                ]
                add(family, pieces, name, started, witness)
                continue
            if family == "minlink":
                # Yerel tolerans, hızlı ölçümün h/2 örnekleme payından türetilir;
                # halkalar birlikte, temas ve açıklık kısıtlarıyla çözülür.
                simplified, record = min_link_boundaries(
                    boundaries, epsilon - spacing / 2 - 1e-6, int(factor)
                )
                pieces = [
                    p for i, b in enumerate(simplified) for p in polygon_pieces(b, i, components[i])
                ]
                record.pop("cycles")
                pieces[0].errors["min_link"] = record
                add(family, pieces, name, started)
                continue
            if family == "linearc":
                # Düğüm ölçütü τ; yayın düzleştirme payı δ hem ölçülen uzaklığa hem
                # üst sınıra girdiği için 2δ ayrıca düşülür. Halkalar ayrı çözülür.
                pieces, record = min_piece_boundaries(
                    boundaries, epsilon - spacing / 2 - 2 * delta - 1e-6, components
                )
                for ring in record["rings"]:
                    ring.pop("nodes")
                    ring.pop("bulges")
                pieces[0].errors["min_piece"] = record
                add(family, pieces, name, started)
                continue
            for i, boundary in enumerate(boundaries):
                checkpoint(cancel)
                component = components[i]
                if family == "polygon":
                    pieces.extend(
                        polygon_pieces(simplify_boundary(boundary, epsilon * factor), i, component)
                    )
                elif family in {"circle", "ellipse"}:
                    pieces.append(primitive(boundary, i, component, family))
                elif family in {"bezier", "mixed"}:
                    pieces.extend(
                        bezier_pieces(
                            boundary, i, component, epsilon * factor, family == "mixed", cancel
                        )
                    )
                elif family == "adaptive":
                    fitted, graph = corner_graph(
                        boundary, i, component, epsilon, target_factor=factor, cancel=cancel
                    )
                    if fitted:
                        fitted[0].errors["candidate_graph"] = graph
                    pieces.extend(fitted)
                elif family == "fourier":
                    pieces.append(fourier_piece(boundary, i, component, int(factor)))
                else:
                    pieces.append(spline_piece(boundary, i, component, int(factor)))
            add(family, pieces, name, started)
        except (ValueError, np.linalg.LinAlgError) as error:
            candidates.append(
                Candidate(
                    name,
                    family,
                    [],
                    {"elapsed_seconds": time.perf_counter() - started},
                    reasons=[f"Sayısal uydurma başarısız: {error}"],
                )
            )
    if config.search_strategy == "annealing" and config.family in {"auto", "adaptive"}:
        cache = {}

        def objective(parameters: np.ndarray) -> float:
            """Sınırlı köşe/eşik alanında bütçeli stokastik öneriler üretir; optimum kanıtı değildir."""
            checkpoint(cancel)
            key = (round(float(parameters[0]), 3), round(float(parameters[1]), 4))
            if key in cache:
                return cache[key]
            if len(cache) >= config.search_budget:
                return min(cache.values())
            started = time.perf_counter()
            name = f"annealing-{len(cache) + 1}"
            try:
                pieces = []
                for i, b in enumerate(boundaries):
                    fitted, graph = corner_graph(
                        b,
                        i,
                        components[i],
                        epsilon,
                        angle_degrees=key[0],
                        target_factor=key[1],
                        cancel=cancel,
                    )
                    if fitted:
                        fitted[0].errors["candidate_graph"] = graph
                    pieces.extend(fitted)
                add("adaptive", pieces, name, started)
                c = candidates[-1]
                value = (
                    c.complexity["score_bits"]
                    if c.accepted
                    else 1e9 + c.metrics.get("hausdorff_upper_bound", 1e6)
                )
            except (ValueError, np.linalg.LinAlgError) as error:
                candidates.append(
                    Candidate(
                        name,
                        "adaptive",
                        [],
                        {"elapsed_seconds": time.perf_counter() - started},
                        reasons=[f"Tavlama önerisi üretilemedi: {error}"],
                    )
                )
                value = 1e12
            candidates[-1].metrics["search_parameters"] = {
                "corner_angle_degrees": key[0],
                "target_factor": key[1],
            }
            cache[key] = float(value)
            return float(value)

        dual_annealing(
            objective,
            [(30.0, 85.0), (0.6, 0.88)],
            maxiter=config.search_budget,
            maxfun=config.search_budget,
            no_local_search=True,
            seed=config.random_seed,
            x0=np.array([45.0, 0.72]),
        )
    if config.family == "auto":
        # Her halka için en ucuz geçerli parçalar seçilir; birleşim tekrar ölçülür.
        pieces = []
        for i in range(len(boundaries)):
            options = []
            for c in candidates:
                error = c.metrics.get("per_boundary", {}).get(str(i), {})
                if error.get("hausdorff_upper_bound", float("inf")) <= epsilon:
                    part = [p for p in c.pieces if p.boundary_id == i]
                    cost = complexity(Candidate("", "", part), plane)["score_bits"]
                    options.append((cost, part))
            pieces.extend(copy.deepcopy(min(options, key=lambda pair: pair[0])[1]))
        add("hybrid", pieces, "hybrid", time.perf_counter())
    if progress:
        progress("Pareto seçimi ve bağımsız sertifika denetimi…")
    selected = certify_selection(candidates, boundaries, config, cancel)
    return candidates, selected


def shapely_error() -> type[Exception]:
    """GEOS sayısal geometri hatasının türünü döndürür."""
    from shapely.errors import GEOSException

    return GEOSException
