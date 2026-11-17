"""Dışa yuvarlanan aralıklar ve rasyonel Bernstein/Jordan yeter koşul sertifikaları.

Sertifika kayıtlı binary64 katsayılarını tam dyadik sayılar olarak yorumlar.
Genel örtük eğri topolojisi çözülmez; desteklenmeyen/belirsiz durumda proven=False.
"""

from fractions import Fraction as Q

import numpy as np
import shapely

from .conic_certification import conic_geometry
from .contact_certificate import contact_polygon_proof
from .intervals import Interval, _norm_upper, _rational_interval, _segment_upper
from .models import Boundary, Candidate, CurvePiece
from .rational_arcs import homogeneous_controls, is_rational_arc
from .rational_splines import bezier_spans
from .topology_simplification import verify_simplification

CERTIFICATE_VERSION = "1.3"


# Halka başına örnek üst sınırı; büyük girdi deneylerinde yükseltilebilir.
MAX_SAMPLES = 500_000


def _split(c: list[tuple]) -> tuple[list, list]:
    """Bernstein kontrol dizisini t=1/2'de tam rasyonel olarak böler."""
    levels = [c]
    while len(levels[-1]) > 1:
        levels.append(
            [
                tuple((a[k] + b[k]) / 2 for k in range(len(a)))
                for a, b in zip(levels[-1][:-1], levels[-1][1:], strict=True)
            ]
        )
    return [row[0] for row in levels], [row[-1] for row in levels[::-1]]


def _flatten_rational(
    original: list, tolerance: float, homogeneous: bool = False
) -> tuple[list, float]:
    """Tam katsayılı polinom/rasyonel Bernstein dizisini kontrollü böler.

    Homojen kontrollerde bütün ağırlıklar pozitiftir; Öklid kontrollerinin
    dışbükey zarfı aynı kapsül ve topoloji yeter koşullarını sağlar.
    """
    pending = [(original, 0)]
    leaves = []
    maximum = 0.0
    while pending:
        raw, depth = pending.pop()
        if homogeneous:
            if any(h[2] <= 0 for h in raw):
                raise ValueError("Rasyonel yayda pozitif ağırlık koşulu sağlanmıyor.")
            c = [(h[0] / h[2], h[1] / h[2]) for h in raw]
        else:
            c = raw
        interval = _rational_interval(c)
        try:
            bound = float(
                np.max(
                    _segment_upper(interval, _rational_interval(c[0]), _rational_interval(c[-1]))
                )
            )
        except ValueError:
            bound = float("inf")
        endpoint_error = float(
            np.max(
                _norm_upper(
                    _rational_interval([c[0], c[-1]])
                    - Interval.point(np.asarray([c[0], c[-1]], dtype=float))
                )
            )
        )
        total = float((Interval.point(bound) + Interval.point(endpoint_error)).hi)
        if total <= tolerance:
            leaves.append(c)
            maximum = max(maximum, total)
        elif depth < 24 and len(leaves) + len(pending) < 20000:
            left, right = _split(raw)
            pending.extend([(right, depth + 1), (left, depth + 1)])
        else:
            raise ValueError("Rasyonel Bézier sertifikası kaynak sınırında belirsiz kaldı.")
    return leaves, maximum


def _verified_leaves(piece: CurvePiece, tolerance: float) -> tuple[list, float]:
    """Doğru/Bézier/B-spline için tam rasyonel ve aralık kontrollü yapraklar üretir."""
    if is_rational_arc(piece):
        return _flatten_rational(homogeneous_controls(piece), tolerance, homogeneous=True)
    if piece.kind == "line":
        return [[tuple(Q(float(x)) for x in piece.params[key]) for key in ("a", "b")]], 0.0
    if piece.kind == "bezier":
        spans = [[tuple(Q(float(x)) for x in point) for point in piece.params["controls"]]]
    elif piece.kind == "bspline":
        spans = bezier_spans(piece)
    else:
        raise ValueError(f"Bu sertifika {piece.kind} ailesini desteklemiyor.")
    leaves, maximum = [], 0.0
    for controls in spans:
        parts, bound = _flatten_rational(controls, tolerance)
        leaves.extend(parts)
        maximum = max(maximum, bound)
        if len(leaves) > 20000:
            raise ValueError("Rasyonel eğri 20.000 yaprak sınırını aştı.")
    return leaves, maximum


def _cover(ring: np.ndarray, spacing: float) -> tuple[Interval, float]:
    """Her kenardaki gerçek rasyonel k/n örneklerini ve yay boşluğu üstünü kapsar."""
    a, b = ring[:-1], ring[1:]
    lengths = _norm_upper(Interval.point(b) - Interval.point(a))
    counts = np.maximum(1, np.ceil(lengths / spacing).astype(int))
    if counts.sum() > MAX_SAMPLES:
        raise ValueError(f"Sertifika {MAX_SAMPLES} örnek sınırını aşıyor.")
    indices = np.repeat(np.arange(len(counts)), counts)
    numerator = np.concatenate([np.arange(n) for n in counts])
    denominator = np.repeat(counts, counts)
    u = Interval.point(numerator) / Interval.point(denominator)
    parameter = Interval(u.lo[:, None], u.hi[:, None])
    points = Interval.point(a[indices]) + parameter * (
        Interval.point(b[indices]) - Interval.point(a[indices])
    )
    gap = float(np.max((Interval.point(lengths) / Interval.point(counts)).hi))
    return points, gap


def _witness_distance(points: Interval, ring: np.ndarray) -> float:
    """GEOS yalnızca kenar tanığı seçer; uzaklık bağımsız aralık hesabıyla kapsanır."""
    a, b = ring[:-1], ring[1:]
    valid = np.any(a != b, axis=1)
    a, b = a[valid], b[valid]
    tree = shapely.STRtree(shapely.linestrings(np.stack([a, b], axis=1)))
    indices = tree.nearest(shapely.points((points.lo + points.hi) / 2))
    distances = _segment_upper(points, Interval.point(a[indices]), Interval.point(b[indices]))
    if not np.isfinite(distances).all():
        raise ValueError("Aralık sertifikası sonlu üst sınır üretemedi.")
    return float(distances.max())


def _cross(a: tuple, b: tuple, c: tuple) -> Q:
    """Üç rasyonel noktanın yönlü alanının iki katını verir."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _hull(points: list[tuple]) -> list[tuple]:
    """Rasyonel yön testleriyle kontrol noktalarının dışbükey zarfını kurar."""
    vertices = sorted(set(points))
    lower = []
    for p in vertices:
        while len(lower) > 1 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(vertices):
        while len(upper) > 1 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1] if len(vertices) > 1 else vertices


def _separated(a: list, b: list) -> bool:
    """Dışbükey zarflara tam rasyonel ayırıcı eksen tanığı arar."""
    for hull in (a, b):
        for p, q in zip(hull, hull[1:] + hull[:1], strict=True):
            d = (q[0] - p[0], q[1] - p[1])
            axes = [(-d[1], d[0])] + ([d] if len(hull) == 2 else [])
            for axis in axes:
                x = [v[0] * axis[0] + v[1] * axis[1] for v in a]
                y = [v[0] * axis[0] + v[1] * axis[1] for v in b]
                if max(x) < min(y) or max(y) < min(x):
                    return True
    return False


def _adjacent_separated(left: list, right: list) -> bool:
    if left[-1] != right[0]:
        return False
    join = left[-1]
    a = np.asarray([float(join[k] - left[0][k]) for k in (0, 1)])
    b = np.asarray([float(right[-1][k] - join[k]) for k in (0, 1)])
    norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
    if not norm_a or not norm_b:
        return False
    normal = tuple(Q(float(x)) for x in a / norm_a + b / norm_b)
    lp = [(p[0] - join[0]) * normal[0] + (p[1] - join[1]) * normal[1] for p in left]
    rp = [(p[0] - join[0]) * normal[0] + (p[1] - join[1]) * normal[1] for p in right]
    return max(lp) <= 0 and min(rp) >= 0 and lp[0] < 0 and rp[-1] > 0


def _embedded(leaves: dict[int, list]) -> bool:
    """Monoton yapraklar, bitişik ayırıcılar ve ayrık zarflarla izotopi kurar."""
    entries = []
    for boundary, parts in leaves.items():
        for index, c in enumerate(parts):
            d = (c[-1][0] - c[0][0], c[-1][1] - c[0][1])
            if d == (0, 0):
                return False
            if any(
                (b[0] - a[0]) * d[0] + (b[1] - a[1]) * d[1] < 0
                for a, b in zip(c[:-1], c[1:], strict=True)
            ):
                return False
            if not _adjacent_separated(c, parts[(index + 1) % len(parts)]):
                return False
            hull = _hull(c)
            interval = _rational_interval(hull)
            entries.append(
                (
                    boundary,
                    index,
                    len(parts),
                    hull,
                    interval.lo.min(axis=0),
                    interval.hi.max(axis=0),
                )
            )
    if len(entries) > 2_000_000:
        return False
    lo = np.asarray([entry[4] for entry in entries])
    hi = np.asarray([entry[5] for entry in entries])
    # Dışa yuvarlanmış kutuları kesişen çiftler uzamsal dizinle bulunur (dokunma dahil);
    # aday kümesi, bütün çiftleri tarayan kutu testiyle aynıdır.
    boxes = shapely.box(lo[:, 0], lo[:, 1], hi[:, 0], hi[:, 1])
    first, second = shapely.STRtree(boxes).query(boxes, predicate="intersects")
    for i, j in zip(first.tolist(), second.tolist(), strict=True):
        if j >= i:
            continue
        boundary, index, count, hull, _, _ = entries[i]
        other, position, _, other_hull, _, _ = entries[j]
        if boundary == other and (abs(index - position) == 1 or abs(index - position) == count - 1):
            continue
        if not _separated(hull, other_hull):
            return False
    return True


def _inside(point: tuple, vertices: list) -> bool:
    """Ayrıklığı önceden kanıtlanmış halkalarda tam rasyonel ışın testi yapar."""
    inside = False
    for a, b in zip(vertices, vertices[1:] + vertices[:1], strict=True):
        if (a[1] > point[1]) != (b[1] > point[1]):
            x = a[0] + (point[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if point[0] < x:
                inside = not inside
    return inside


def _signature(leaves: dict[int, list]) -> dict:
    """Basit ayrık halkaların ebeveyn ve yön imzasını rasyonel olarak çıkarır."""
    vertices = {i: [c[0] for c in parts] for i, parts in leaves.items()}
    areas = {
        i: sum(a[0] * b[1] - a[1] * b[0] for a, b in zip(v, v[1:] + v[:1], strict=True))
        for i, v in vertices.items()
    }
    result = {}
    for i, v in vertices.items():
        containers = [j for j, w in vertices.items() if j != i and _inside(v[0], w)]
        parent = min(containers, key=lambda j: abs(areas[j])) if containers else None
        result[i] = (parent, areas[i] < 0)
    return result


def _envelopes_separated(grouped: dict[int, list], envelopes: dict[int, list]) -> bool:
    """Konik bulunan halkalar arası gerçek eğri zarflarını kesin ayırır.

    Konikte zarf gerçek rasyonel parametreli yayı ve yaklaşık kirişi birlikte
    kapsar; polinomda kontrol zarfıdır. Ayrıklık, eşzamanlı kiriş homotopisi
    sırasında halkalar arası sarım/içerilme ilişkisinin değişmesini engeller.
    """
    entries = []
    for boundary, parts in grouped.items():
        for i, c in enumerate(parts):
            hull = envelopes[boundary][i] if boundary in envelopes else _hull(c)
            interval = _rational_interval(hull)
            entries.append((boundary, hull, interval.lo.min(axis=0), interval.hi.max(axis=0)))
    lo = np.asarray([e[2] for e in entries])
    hi = np.asarray([e[3] for e in entries])
    for i, (boundary, hull, _, _) in enumerate(entries):
        possible = np.flatnonzero(np.all(hi[i] >= lo[:i], axis=1) & np.all(hi[:i] >= lo[i], axis=1))
        for j in possible:
            other, other_hull, _, _ = entries[j]
            if boundary == other or (boundary not in envelopes and other not in envelopes):
                continue
            if not _separated(hull, other_hull):
                return False
    return True


def certify(
    candidate: Candidate,
    boundaries: list[Boundary],
    epsilon: float,
    spacing: float = 0.5,
    delta: float = 0.025,
) -> dict:
    """Hata kapsaması ve uygun doğru/Bézier ailelerinde analitik topoloji sertifikası.

    Desteklenen aritmetik: sonlu normal/subnormal binary64 temel +,-,*,/ ve
    sqrt; her işlem dışa bir ULP genişletilir. Katsayı uydurmasının doğruluğu
    veya kaynak ideal eğri hakkında garanti değildir. Belirsizlik kabul edilmez.
    """
    result = {
        "certificate_version": CERTIFICATE_VERSION,
        "arithmetic": "outward_binary64_intervals_and_exact_rationals",
        "coefficient_semantics": "stored binary64 values interpreted as exact dyadic rationals",
        "verified_numerical_certificate": False,
        "analytic_isotopy_proven": False,
        "status": "undetermined",
        "reasons": [],
        "spline_conversion": "exact_rational_de_Boor_Hermite",
        "rational_arc_semantics": "positive homogeneous quadratic Bernstein; exact shared dyadic endpoints",
        "full_conic_semantics": "canonical full-turn interval; exact symbolic 2*pi phase, dyadic radii and rotation angle",
    }
    if (
        not np.isfinite([epsilon, spacing, delta]).all()
        or epsilon < 0
        or spacing <= 0
        or delta <= 0
        or not boundaries
        or not candidate.pieces
    ):
        result["reasons"].append(
            "Sertifika için sonlu toleranslar ve boş olmayan geometri gerekir."
        )
        return result
    if np.finfo(float).bits != 64 or np.finfo(float).tiny / 2 == 0 or np.nextafter(0.0, 1.0) == 0:
        result["reasons"].append("IEEE-754 binary64/subnormal aritmetik koşulları sağlanmıyor.")
        return result
    if any(
        len(p.interval) != 2 or not np.isfinite(p.interval).all() or p.interval[0] >= p.interval[1]
        for p in candidate.pieces
    ):
        result["reasons"].append("Sertifika artan ve sonlu parça aralıkları gerektirir.")
        return result
    exact = True
    for i, b in enumerate(boundaries):
        parts = [p for p in candidate.pieces if p.boundary_id == i]
        pairs = list(zip(b.vertices, b.vertices[1:] + b.vertices[:1], strict=True))
        if len(parts) != len(pairs) or any(
            p.kind != "line" or p.params["a"] != list(a) or p.params["b"] != list(z)
            for p, (a, z) in zip(parts, pairs, strict=True)
        ):
            exact = False
            break
    if exact and len(candidate.pieces) == sum(len(b.vertices) for b in boundaries):
        return {
            **result,
            "verified_numerical_certificate": True,
            "analytic_isotopy_proven": True,
            "status": "proven",
            "within_tolerance": True,
            "hausdorff_upper_bound": 0.0,
            "topology_method": "exact_identity_of_ordered_reference_edges",
        }
    try:
        grouped = {}
        envelopes = {}
        maximum_delta = 0.0
        for p in candidate.pieces:
            if p.kind in {"circle", "ellipse"} and not is_rational_arc(p):
                if sum(part.boundary_id == p.boundary_id for part in candidate.pieces) != 1:
                    raise ValueError("Konik sertifikası halka başına tek tam konik gerektirir.")
                parts, bound, boxes = conic_geometry(p, delta)
                envelopes[p.boundary_id] = boxes
            else:
                parts, bound = _verified_leaves(p, delta)
            grouped.setdefault(p.boundary_id, []).extend(parts)
            maximum_delta = max(maximum_delta, bound)
        if set(grouped) != set(range(len(boundaries))):
            raise ValueError("Sertifika sınır kimlikleri eksik.")
        reference = {
            i: [
                [(Q(a[0]), Q(a[1])), (Q(b[0]), Q(b[1]))]
                for a, b in zip(
                    boundary.vertices, boundary.vertices[1:] + boundary.vertices[:1], strict=True
                )
            ]
            for i, boundary in enumerate(boundaries)
        }
        upper = 0.0
        for i, boundary in enumerate(boundaries):
            ref = np.asarray([*boundary.vertices, boundary.vertices[0]], dtype=float)
            parts = grouped[i]
            for a, b in zip(parts, parts[1:] + parts[:1], strict=True):
                if a[-1] != b[0]:
                    raise ValueError("Sertifikada tam rasyonel C0 kapanışı yok.")
            model = np.asarray([*[c[0] for c in parts], parts[-1][-1]], dtype=float)
            r, rh = _cover(ref, spacing)
            m, mh = _cover(model, spacing)
            measured = max(_witness_distance(r, model), _witness_distance(m, ref))
            bound = (
                Interval.point(measured)
                + Interval.point(max(rh, mh)) / Interval.point(2.0)
                + Interval.point(maximum_delta)
            )
            upper = max(upper, float(bound.hi))
        result.update(
            verified_numerical_certificate=True,
            hausdorff_upper_bound=upper,
            within_tolerance=upper <= epsilon,
            curve_to_polygon_bound=maximum_delta,
            sample_spacing=spacing,
        )
        if not result["within_tolerance"]:
            result["reasons"].append("Sertifikalı hata üst sınırı kullanıcı toleransını aşıyor.")
        graph_proof = None
        if "topology_witness" in candidate.metrics:
            graph_proof = verify_simplification(candidate, boundaries)
        if graph_proof:
            result["analytic_isotopy_proven"] = True
            result["topology_method"] = "replayed_exact_empty_triangle_planar_graph_isotopy"
            result["verified_removals"] = graph_proof["verified_removals"]
        elif (
            _embedded(grouped)
            and _embedded(reference)
            and _signature(grouped) == _signature(reference)
            and (not envelopes or _envelopes_separated(grouped, envelopes))
            and all(
                _signature(grouped)[p.boundary_id][1] == (p.params.get("direction", 1) < 0)
                for p in candidate.pieces
                if p.kind in {"circle", "ellipse"} and not is_rational_arc(p)
            )
        ):
            result["analytic_isotopy_proven"] = True
            result["topology_method"] = (
                "rational_Bernstein_enclosed_conics_and_exact_Jordan_nesting"
                if envelopes
                else "rational_monotone_Bernstein_hulls_and_exact_Jordan_nesting"
            )
        elif all(p.kind == "line" for p in candidate.pieces) and contact_polygon_proof(
            {i: [c[0] for c in parts] for i, parts in grouped.items()},
            {i: [c[0] for c in parts] for i, parts in reference.items()},
        ):
            result["analytic_isotopy_proven"] = True
            result["topology_method"] = "exact_contact_preserving_polygon_embedding"
        else:
            result["reasons"].append(
                "Bernstein/Jordan yeter koşulları sağlanamadı; genel topoloji sonucu çıkarılmaz."
            )
        result["status"] = (
            "proven"
            if result["within_tolerance"] and result["analytic_isotopy_proven"]
            else "undetermined"
        )
    except (ValueError, OverflowError, ZeroDivisionError) as error:
        result["reasons"].append(str(error))
    return result
