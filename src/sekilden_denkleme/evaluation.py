"""İki yönlü geometrik hata, açık örnekleme sınırları ve topoloji denetimi."""

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

import numpy as np
import shapely
from shapely.geometry import Polygon

from .contact_certificate import contact_polygon_proof
from .curves import is_full_conic, model_rings, pieces_for_boundary, tangent
from .models import Boundary, Candidate
from .topology_simplification import verify_simplification


def _tree(ring: np.ndarray) -> shapely.STRtree:
    """Sonlu kenarları uzamsal dizine koyar; nokta bulutu mesafesi kullanmaz."""
    a, b = ring[:-1], ring[1:]
    valid = np.any(a != b, axis=1)
    return shapely.STRtree(shapely.linestrings(np.stack([a[valid], b[valid]], axis=1)))


def _distances(tree: shapely.STRtree, points: np.ndarray) -> np.ndarray:
    """GEOS dizininden her noktaya en yakın sonlu kenar mesafesini alır."""
    indices, distance = tree.query_nearest(
        shapely.points(points), all_matches=False, return_distance=True
    )
    result = np.full(len(points), np.nan)
    result[indices[0]] = distance
    return result


@dataclass
class EvaluationContext:
    """Aynı referans/örnekleme için değişmez hesapları adaylar arasında paylaşır."""

    boundaries: list[Boundary]
    spacing: float
    references: dict = field(init=False)

    def __post_init__(self) -> None:
        """Yay örnekleri, ağırlıklar, alan ve kenar dizinlerini bir kez hesaplar."""
        self.references = {}
        for i, b in enumerate(self.boundaries):
            ring = closed_vertices(b)
            points, weights, gap = sample_ring(ring, self.spacing)
            self.references[i] = (points, weights, gap, _tree(ring), Polygon(ring).area)


def closed_vertices(boundary: Boundary) -> np.ndarray:
    """Piksel sınırına yalnızca kapanış köşesini ekler; geometri değişmez."""
    return np.asarray([*boundary.vertices, boundary.vertices[0]], dtype=float)


def sample_ring(ring: np.ndarray, spacing: float) -> tuple[np.ndarray, np.ndarray, float]:
    """Her kenarı en çok spacing uzunluğunda böler; küçük halkaları da örnekler.

    Başlangıç örnekleri, yay uzunluğu ağırlıkları ve en büyük örnek aralığı döner.
    Her köşe örnektir; toplam 500.000 örnek kaynak koruması uygulanır.
    """
    lengths = np.linalg.norm(np.diff(ring, axis=0), axis=1)
    counts = np.maximum(1, np.ceil(lengths / spacing).astype(int))
    if counts.sum() > 500000:
        raise ValueError("Ölçüm 500.000 örneği aşıyor; ölçüm aralığını artırın.")
    indices = np.repeat(np.arange(len(lengths)), counts)
    u = np.concatenate([np.arange(n) / n for n in counts])
    points = ring[indices] + u[:, None] * (ring[indices + 1] - ring[indices])
    weights = np.repeat(lengths / counts, counts)
    return points, weights, float(np.max(lengths / counts))


def reference_topology(boundaries: list[Boundary]) -> dict[str, Any]:
    """Halka içerilme ağacını ve dört-komşu dış bileşen sahipliğini kurar.

    En küçük kapsayan halka ebeveyndir. İçteki adalar ayrı outer bileşenlerdir.
    Noktasal temaslar ilişki olarak kaydedilir; yeni temaslara izin verilmez.
    """
    rings = [Polygon(b.vertices) for b in boundaries]
    records = []
    component = 0
    for i, boundary in enumerate(boundaries):
        containers = [
            j
            for j, poly in enumerate(rings)
            if j != i and poly.area > rings[i].area and poly.covers(rings[i])
        ]
        parent = min(containers, key=lambda j: rings[j].area) if containers else None
        records.append(
            {
                "id": i,
                "kind": boundary.kind,
                "parent_id": parent,
                "component_id": component if boundary.kind == "outer" else None,
                "closed": True,
            }
        )
        component += boundary.kind == "outer"
    for rec in records:
        if rec["kind"] == "hole":
            parent = rec["parent_id"]
            rec["component_id"] = records[parent]["component_id"] if parent is not None else -1
    contacts = [
        [i, j]
        for i in range(len(rings))
        for j in range(i)
        if rings[i].boundary.intersects(rings[j].boundary)
    ]
    return {
        "rings": records,
        "component_count": component,
        "hole_count": sum(b.kind == "hole" for b in boundaries),
        "contacts": contacts,
        "connectivity": "foreground_4_neighbors",
    }


def topology_check(
    rings: dict[int, np.ndarray], topology: dict[str, Any], delta: float
) -> dict[str, Any]:
    """Poligon temsilinde geçerlilik ve aynı içerilme/temas ilişkilerini doğrular.

    Eğri düzleştirme belirsizliği için farklı halkalarda 2*delta güvenlik payı
    gerekir. Aynı halkanın düzgün eğri topolojisi yalnızca poligonla denetlenir;
    analitik izotopi ispatı yapılmaz ve bu durum sonuçta açıkça saklanır.
    """
    reasons = []
    polygons = {i: Polygon(r) for i, r in rings.items()}
    if set(rings) != {r["id"] for r in topology["rings"]}:
        return {"preserved": False, "reasons": ["Sınır kaybı."], "scope": "polygonized"}
    for rec in topology["rings"]:
        i = rec["id"]
        poly = polygons[i]
        if not poly.is_valid or poly.area <= 1e-12:
            reasons.append(f"Sınır {i}: öz-kesişim veya sıfır alan.")
        pts = rings[i]
        signed = np.sum(pts[:-1, 0] * pts[1:, 1] - pts[:-1, 1] * pts[1:, 0])
        if (signed < 0) != (rec["kind"] == "outer"):
            reasons.append(f"Sınır {i}: yön/alan işareti değişti.")
        containers = [
            j for j, p in polygons.items() if j != i and p.area > poly.area and p.covers(poly)
        ]
        parent = min(containers, key=lambda j: polygons[j].area) if containers else None
        if parent != rec["parent_id"]:
            reasons.append(f"Sınır {i}: içerilme ağacı değişti.")
    old_contacts = {tuple(pair) for pair in topology["contacts"]}
    for i, poly in polygons.items():
        for j in range(i):
            other = polygons[j]
            boundary_distance = poly.boundary.distance(other.boundary)
            contact = (i, j) in old_contacts
            if poly.boundary.crosses(other.boundary):
                reasons.append(f"Sınırlar {i},{j}: kesişim.")
            if contact != poly.boundary.intersects(other.boundary):
                reasons.append(f"Sınırlar {i},{j}: temas ilişkisi değişti.")
            if delta and boundary_distance <= 2 * delta:
                reasons.append(f"Sınırlar {i},{j}: eğri toleransı içinde topoloji belirsiz.")
    return {
        "preserved": not reasons,
        "reasons": reasons,
        "scope": "polygonized_with_inter_ring_clearance" if delta else "exact_polygon",
        "analytic_isotopy_proven": False,
        "component_count": topology["component_count"],
        "hole_count": topology["hole_count"],
    }


def evaluate_candidate(
    candidate: Candidate,
    boundaries: list[Boundary],
    topology: dict[str, Any],
    spacing: float,
    delta: float,
    *,
    context: EvaluationContext | None = None,
    workers: int = 1,
) -> None:
    """Adayın tüm halkalarını ayrı ölçer; sonuçları ve parça tanılarını doldurur.

    H <= max örnek uzaklığı + en büyük yay aralığı/2 + delta bağıntısı,
    uzaklık fonksiyonunun 1-Lipschitz oluşundan gelir. delta model eğrisinin
    poligona uzaklık üst sınırıdır. IEEE kayan nokta yuvarlaması ayrıca 1e-8
    payla hesaba katılır; doğrulanmış aralık aritmetiği kullanılmaz.
    """
    is_linear = all(p.kind == "line" for p in candidate.pieces)
    actual_delta = 0.0 if is_linear else delta
    rings = model_rings(candidate.pieces, delta)
    topology_result = topology_check(rings, topology, actual_delta)
    witness = candidate.metrics.get("topology_witness")
    if witness is not None or candidate.family == "topology":
        topology_result = {
            **verify_simplification(candidate, boundaries),
            "component_count": topology["component_count"],
            "hole_count": topology["hole_count"],
        }
    elif not topology_result["preserved"] and is_linear:
        # Nokta temaslı referansta shapely teması kesişim sayar; çokgenlerde
        # aynı düzlem gömülmesi tam rasyonel aritmetikle ayrıca sınanır.
        model_vertices: dict[int, list] = {}
        for piece in candidate.pieces:
            a = piece.params["a"]
            model_vertices.setdefault(piece.boundary_id, []).append(
                (Fraction(float(a[0])), Fraction(float(a[1])))
            )
        reference_vertices = {
            i: [(Fraction(float(x)), Fraction(float(y))) for x, y in b.vertices]
            for i, b in enumerate(boundaries)
        }
        if contact_polygon_proof(model_vertices, reference_vertices):
            topology_result = {
                "preserved": True,
                "reasons": [],
                "scope": "exact_contact_preserving_polygon_embedding",
                "analytic_isotopy_proven": True,
                "component_count": topology["component_count"],
                "hole_count": topology["hole_count"],
            }
    maximum, squared, total_weight, max_gap, count = 0.0, 0.0, 0.0, 0.0, 0
    area_ref, area_model = 0.0, 0.0
    per_boundary = {}
    reused_context = context is not None
    context = context or EvaluationContext(boundaries, spacing)

    def measure(i: int) -> tuple:
        """Tek halkayı ölçer; widget veya başka adayın durumuna erişmez."""
        model = rings[i]
        ref_points, rw, rh, ref_tree, ref_area = context.references[i]
        mod_points, mw, mh = sample_ring(model, spacing)
        forward = _distances(_tree(model), ref_points)
        backward = _distances(ref_tree, mod_points)
        if not np.isfinite(forward).all() or not np.isfinite(backward).all():
            raise ValueError("Geometrik uzaklık hesabı sonlu sonuç üretmedi.")
        return i, forward, backward, rw, mw, rh, mh, ref_area, Polygon(model).area

    if workers > 1 and len(boundaries) > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            measurements = list(executor.map(measure, range(len(boundaries))))
    else:
        measurements = list(map(measure, range(len(boundaries))))
    for i, forward, backward, rw, mw, rh, mh, ref_area, model_area in measurements:
        boundary = boundaries[i]
        measured = float(max(forward.max(), backward.max()))
        rms = float(np.sqrt((forward**2 @ rw + backward**2 @ mw) / (rw.sum() + mw.sum())))
        upper = measured + max(rh, mh) / 2 + actual_delta + 1e-8
        if candidate.family == "exact":
            measured, rms, upper = 0.0, 0.0, 0.0
        errors = {
            "sampled_hausdorff": measured,
            "rms": rms,
            "hausdorff_upper_bound": upper,
            "forward_max": float(forward.max()),
            "backward_max": float(backward.max()),
        }
        per_boundary[str(i)] = errors
        for piece in pieces_for_boundary(candidate.pieces, i):
            # Halka ölçümü her parçaya mal edilmez; kapsam açıkça belirtilir.
            piece.errors = {**piece.errors, "scope": "owning_boundary", **errors}
            piece.tolerances = {
                "flatten": actual_delta,
                "sample_spacing": spacing,
                "join": 1e-7,
                "floating_margin": 1e-8,
            }
        maximum = max(maximum, measured)
        squared += float(forward**2 @ rw + backward**2 @ mw)
        total_weight += float(rw.sum() + mw.sum())
        max_gap = max(max_gap, rh, mh)
        count += len(forward) + len(backward)
        sign = 1 if boundary.kind == "outer" else -1
        area_ref += sign * ref_area
        area_model += sign * model_area
    gaps, angles = [], []
    for i in rings:
        parts = pieces_for_boundary(candidate.pieces, i)
        for left, right in zip(parts, parts[1:] + parts[:1], strict=True):
            gaps.append(float(np.linalg.norm(np.asarray(left.end) - right.start)))
            a, b = tangent(left, True), tangent(right)
            denominator = np.linalg.norm(a) * np.linalg.norm(b)
            if denominator > 1e-14:
                angles.append(float(np.degrees(np.arccos(np.clip(a @ b / denominator, -1, 1)))))
    upper = maximum + max_gap / 2 + actual_delta + 1e-8
    if candidate.family == "exact":
        upper = 0.0
    candidate.metrics = {
        "sampled_hausdorff": maximum,
        "hausdorff_upper_bound": upper,
        "bound_kind": "Lipschitz_sampling_plus_curve_bound_float64",
        "verified_numerical_certificate": False,
        "distance_backend": "GEOS_STRtree_segments",
        "evaluation_workers": workers,
        "reference_cache_reused": reused_context,
        "rms": float(np.sqrt(squared / total_weight)),
        "area_difference": abs(area_model - area_ref),
        "area_reference": area_ref,
        "area_model_polygonized": area_model,
        "area_curve_uncertainty_bound": sum(
            2 * Polygon(r).length * actual_delta + np.pi * actual_delta**2 for r in rings.values()
        ),
        "sample_count": count,
        "max_sample_gap": max_gap,
        "flatten_tolerance": actual_delta,
        "topology": topology_result,
        "join_max_gap": max(gaps, default=0),
        "join_max_tangent_angle_degrees": max(angles, default=0),
        "tangent_continuity_required": False,
        "per_boundary": per_boundary,
    }
    if witness is not None:
        candidate.metrics["topology_witness"] = witness
    candidate.reasons.extend(topology_result["reasons"])
    if max(gaps, default=0) > 1e-7:
        candidate.reasons.append("Parça birleşimlerinde konum süreksizliği.")


# mdl_v1: kenarı N olan çalışma düzleminde 2^-6 birimlik ızgara → gerçek başına
# ceil(log2(64 N)) bit (N = 1000 için 16); yedi parça türü için 3 bitlik etiket.
MDL_GRID = 2.0**-6
MDL_REAL_BITS = math.ceil(math.log2(1000 / MDL_GRID))
MDL_KIND_BITS = 3


def mdl_real_bits(plane: float) -> int:
    """Kenarı `plane` olan düzlemde bir ızgara koordinatının bit sayısı."""
    return max(1, math.ceil(math.log2(max(plane, 1.0) / MDL_GRID)))


def _gamma_bits(value: int) -> int:
    """Pozitif tamsayının Elias-gamma kod uzunluğu."""
    return 2 * int(math.floor(math.log2(max(1, value)))) + 1


def complexity(candidate: Candidate, plane: float = 1000.0) -> dict[str, Any]:
    """Belgeli sabit uzunluklu model kodlamasının boyutsuz bit maliyetini döndürür.

    Her gerçek parametre 64 bit, tür 8 bit, sınır kimliği ve derece gibi
    tamsayılar 32 bit kodlanır. Tüm parçalarda iki aralık ucu da 64 bittir.
    Türetilmiş uçlar/ortak dönüşüm tekrar sayılmaz; bu gerçek JSON boyutu değildir.
    """
    reals, integers, degrees, controls, knots, free = 0, 0, [], 0, 0, 0
    ring_sizes: dict[int, int] = {}
    for piece in candidate.pieces:
        ring_sizes[piece.boundary_id] = ring_sizes.get(piece.boundary_id, 0) + 1
    mdl_reals, mdl_side = 0, 0
    for piece in candidate.pieces:
        p = piece.params
        n, ints, degree, freedom = 0, 1, 1, 0
        if piece.kind == "line":
            n, freedom = 4, 4
        elif piece.kind == "circle" and "arc" in p:
            n, degree, freedom = 5, 2, 5
            controls += 3
        elif piece.kind == "ellipse" and "arc" in p:
            n, degree, freedom = 7, 2, 7
            controls += 3
        elif piece.kind == "circle":
            arc_parameters = 0 if is_full_conic(piece) else 2
            n, ints, degree, freedom = 3, 2, 2, 3 + arc_parameters
        elif piece.kind == "ellipse":
            arc_parameters = 0 if is_full_conic(piece) else 2
            n, ints, degree, freedom = 5, 2, 2, 5 + arc_parameters
        elif piece.kind == "bezier":
            n, degree, freedom = 8, 3, 8
            controls += 4
        elif piece.kind == "fourier":
            order = len(p["cos"])
            n, ints, degree, freedom = 2 + 4 * order, 2, 0, 2 + 4 * order
        else:
            controls += len(p["controls"])
            knots += len(p["knots"])
            n = 2 * len(p["controls"]) + len(p["knots"])
            interior_knots = len(
                set(k for k in p["knots"] if piece.interval[0] < k < piece.interval[1])
            )
            ints, degree, freedom = 2, p["degree"], 2 * len(p["controls"]) + interior_knots
        reals += n + 2
        integers += ints
        # mdl_v1: C0 zincirinde başlangıç ucu önceki parçadan gelir, yeniden kodlanmaz.
        shared = 2 if ring_sizes[piece.boundary_id] > 1 and piece.kind != "fourier" else 0
        mdl_reals += max(freedom - shared, 1)
        mdl_side += MDL_KIND_BITS
        if piece.kind == "fourier":
            mdl_side += _gamma_bits(len(p["cos"]))
        elif piece.kind not in {"line", "circle", "ellipse", "bezier"}:
            mdl_side += _gamma_bits(len(p["controls"])) + 2
        free += freedom
        degrees.append(degree)
    return {
        "score_bits": 64 * reals + 32 * integers + 8 * len(candidate.pieces),
        "piece_count": len(candidate.pieces),
        "free_parameters_upper": free,
        "stored_real_count": reals,
        "stored_integer_count": integers,
        "control_points": controls,
        "knots": knots,
        "max_degree": max(degrees, default=0),
        "degree_note": "Çember/elips: örtük derece; Fourier: 0 polinom dışı anlamındadır, harmonik sayısı katsayılardan bilinir; diğerleri: parametrik polinom derecesi.",
        "interval_constraints": len(candidate.pieces),
        "encoding": "fixed64_v1",
        "mdl_bits": mdl_real_bits(plane) * mdl_reals
        + mdl_side
        + sum(_gamma_bits(count) for count in ring_sizes.values()),
        "mdl_free_reals": mdl_reals,
        "mdl_encoding": "mdl_v1",
        "parameter_count_note": "Paylaşılan uç/periodiklik kısıtları düşülmemiş üst sayım.",
    }
