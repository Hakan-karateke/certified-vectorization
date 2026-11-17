"""CAD aktarımında ortak geometri, fiziksel ölçek ve bağımsız poligon denetimi.

DXF kapalı eğri grupları, STEP/IGES bunlarla sınırlı düzlemsel yüzlerdir;
katı veya ölçü/kısıt geçmişi değildir. Sayısal aktarım denetimi, kaynak modelin aralık sertifikasından
ayrı raporlanır. Bütün bu modüldeki CAD uzunlukları seçilmiş çıktı birimindedir.
"""

import math
from dataclasses import dataclass
from fractions import Fraction as Q
from typing import Any

import numpy as np
import shapely
from scipy.interpolate import BSpline
from scipy.optimize import linear_sum_assignment
from shapely.geometry import Polygon

from .curves import evaluate, flatten, is_full_conic, model_rings, pieces_for_boundary
from .models import AnalysisResult, CurvePiece
from .rational_arcs import homogeneous_controls, is_rational_arc
from .rational_splines import bezier_spans

UNIT_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}


@dataclass(frozen=True)
class CadOptions:
    """CAD birimi, ölçek eşlemesi ve aktarım sapmasını tanımlar.

    scale: Bir çalışma koordinatının kaç çıktı birimi olduğu. Bu bir kullanıcı
        eşlemesidir; görselden fiziksel kalibrasyon çıkarıldığı anlamına gelmez.
    tolerance: CAD geometri aktarım sapması hedefi, seçilen çıktı biriminde.
    allow_approximation: Fourier gibi yerel temsili bulunmayan eğrileri kontrollü
        doğru parçalarıyla aktarmaya açıkça izin verir.
    """

    unit: str = "mm"
    scale: float = 1.0
    tolerance: float = 0.01
    allow_approximation: bool = False

    def __post_init__(self) -> None:
        """Birim ve sayısal kaynak sınırlarını kontrol eder; toleransı gevşetmez."""
        if self.unit not in UNIT_MM:
            raise ValueError("CAD birimi mm, cm, m veya in olmalıdır.")
        if not math.isfinite(self.scale) or not 0.001 <= self.scale <= 1000:
            raise ValueError("CAD ölçeği 0.001..1000 çıktı birimi/koordinat olmalıdır.")
        if not math.isfinite(self.tolerance) or not 1e-6 <= self.tolerance <= 10:
            raise ValueError("CAD aktarım toleransı 0.000001..10 çıktı birimi olmalıdır.")
        if self.tolerance * UNIT_MM[self.unit] < 1e-6:
            raise ValueError("CAD toleransı çekirdek çözünürlüğü için en az 0.000001 mm olmalıdır.")


@dataclass
class CadCurve:
    """Bir yerel CAD eğrisini asıl model parçasına ve sınırına bağlar."""

    kind: str
    params: dict[str, Any]
    source_piece: int
    boundary_id: int
    interval: list[float]
    reversed: bool = False


def _spline(
    controls: list,
    degree: int,
    knots: list,
    weights: list | None,
    piece: CurvePiece,
    index: int,
    scale: float,
) -> CadCurve:
    """Kontrol/düğüm/ağırlıkları yeniden uydurmadan CAD spline katsayılarına çevirir."""
    return CadCurve(
        "bspline",
        {
            "controls": (np.asarray(controls, float) * scale).tolist(),
            "degree": degree,
            "knots": list(knots),
            "weights": weights,
        },
        index,
        piece.boundary_id,
        list(piece.interval),
    )


def native_curves(piece: CurvePiece, index: int, options: CadOptions) -> list[CadCurve]:
    """Sonlu geometriyi yerel doğru/konik/NURBS'e çevirir; bilinmeyeni açıkça reddeder."""
    p, scale = piece.params, options.scale
    common = (index, piece.boundary_id, list(piece.interval))
    if piece.kind == "line":
        return [
            CadCurve(
                "line",
                {
                    "a": (np.array(p["a"]) * scale).tolist(),
                    "b": (np.array(p["b"]) * scale).tolist(),
                },
                *common,
            )
        ]
    if is_rational_arc(piece) and piece.kind == "circle":
        arc = p["arc"]
        a, b = [tuple(Q(float(v)) for v in arc[k]) for k in ("a", "b")]
        s = Q(float(arc["bulge"]))
        j = (a[1] - b[1], b[0] - a[0])
        exact_center = [(a[k] + b[k]) / 2 + (1 - s * s) * j[k] / (4 * s) for k in (0, 1)]
        center = np.array([float(v) for v in exact_center])
        radius = math.sqrt(float(sum((a[k] - exact_center[k]) ** 2 for k in (0, 1))))
        start = np.array(arc["a"] if s > 0 else arc["b"])
        angle = math.atan2(*(start - center)[::-1])
        return [
            CadCurve(
                "arc",
                {
                    "center": (center * scale).tolist(),
                    "radius": radius * scale,
                    "start": angle,
                    "end": angle + abs(4 * math.atan(float(s))),
                },
                *common,
                reversed=s < 0,
            )
        ]
    if is_rational_arc(piece):
        h = homogeneous_controls(piece)
        return [
            _spline(
                [[float(x / w), float(y / w)] for x, y, w in h],
                2,
                [0, 0, 0, 1, 1, 1],
                [float(row[2]) for row in h],
                piece,
                index,
                scale,
            )
        ]
    if piece.kind == "bezier":
        return [_spline(p["controls"], 3, [0, 0, 0, 0, 1, 1, 1, 1], None, piece, index, scale)]
    if piece.kind == "bspline":
        if piece.interval == [p["knots"][3], p["knots"][-4]]:
            return [_spline(p["controls"], 3, p["knots"], None, piece, index, scale)]
        # DXF SPLINE'da ayrı kırpma aralığı yoktur; sonlu alt aralıklar tam
        # Bernstein eşdeğerleriyle taşınır, dışarıdaki dallar dosyaya sızmaz.
        breaks = sorted(
            {
                piece.interval[0],
                piece.interval[1],
                *[k for k in p["knots"] if piece.interval[0] < k < piece.interval[1]],
            }
        )
        result = []
        for c, a, b in zip(bezier_spans(piece), breaks[:-1], breaks[1:], strict=True):
            curve = _spline(c, 3, [0, 0, 0, 0, 1, 1, 1, 1], None, piece, index, scale)
            curve.interval = [a, b]
            result.append(curve)
        return result
    if piece.kind in {"circle", "ellipse"}:
        direction = p.get("direction", 1)
        a, b = piece.interval
        center = (np.array(p["center"]) * scale).tolist()
        if piece.kind == "circle":
            kind = "circle" if is_full_conic(piece) else "arc"
            params = {"center": center, "radius": p["radius"] * scale}
        else:
            rx, ry = p["radii"]
            rotation = p.get("rotation", 0)
            shift = 0.0
            if ry > rx:
                rx, ry, rotation, shift = ry, rx, rotation + np.pi / 2, np.pi / 2
            params = {
                "center": center,
                "major": rx * scale,
                "minor": ry * scale,
                "rotation": rotation,
            }
            a, b = direction * a - shift, direction * b - shift
            kind = "ellipse"
        if piece.kind == "circle":
            a, b = direction * a, direction * b
        params.update(start=min(a, b), end=max(a, b), full=is_full_conic(piece))
        if params["end"] - params["start"] > 2 * np.pi + 1e-12:
            raise ValueError("CAD aktarımı bir turu aşan konik aralıklarını desteklemiyor.")
        return [CadCurve(kind, params, *common, reversed=direction < 0)]
    if not options.allow_approximation:
        raise ValueError(
            f"{piece.kind} CAD'de tam temsil edilemiyor; kontrollü yaklaşımı açıkça seçin."
        )
    q = flatten(piece, options.tolerance / (8 * scale)) * scale
    return [
        CadCurve(
            "polyline",
            {"points": q.tolist(), "approximation_tolerance": options.tolerance / 8},
            *common,
        )
    ]


def prepare_geometry(result: AnalysisResult, options: CadOptions) -> tuple[list[CadCurve], dict]:
    """Kayıtlı modeli CAD'e hazırlar; açık, temaslı veya geçersiz profili reddeder."""
    from .project import _validate_piece

    if result.selected is None or not result.selected.accepted:
        raise ValueError("CAD aktarımı kabul edilmiş seçili model gerektirir.")
    if len(result.selected.pieces) > 20000:
        raise ValueError("CAD aktarımı en çok 20.000 model parçası destekler.")
    curves = []
    for i, p in enumerate(result.selected.pieces):
        _validate_piece(p, len(result.reference_boundaries))
        curves.extend(native_curves(p, i, options))
    for i in range(len(result.reference_boundaries)):
        parts = pieces_for_boundary(result.selected.pieces, i)
        if not parts:
            raise ValueError("CAD aktarımında bir referans sınırı eksik.")
        for a, b in zip(parts, parts[1:] + parts[:1], strict=True):
            gap = (
                float(
                    np.linalg.norm(
                        evaluate(a, [a.interval[1]])[0] - evaluate(b, [b.interval[0]])[0]
                    )
                )
                * options.scale
            )
            if gap > min(1e-7 * options.scale, options.tolerance / 16):
                raise ValueError(
                    "Kaynak modelde açık parça birleşimi var; CAD profili kapatılamaz."
                )
    rings = {
        i: q * options.scale
        for i, q in model_rings(
            result.selected.pieces, options.tolerance / (8 * options.scale)
        ).items()
    }
    if sum(len(q) for q in rings.values()) > 250000:
        raise ValueError("CAD profil denetimi 250.000 köşe sınırını aştı.")
    rings = dict(sorted(rings.items()))
    nesting_signature(rings)
    return curves, rings


def flatten_homogeneous(h: np.ndarray, tolerance: float) -> np.ndarray:
    """Pozitif ağırlıklı CAD Bézier'ini sonlu kiriş kapsülüyle float64'te böler.

    Girdi (n,4) homojen 3B kontrollerdir. Denetim aralık sertifikası değildir;
    bütün gerçek eğri için dışbükey zarf yeter koşulu kullanılır.
    """
    if not np.isfinite(h).all() or np.any(h[:, -1] <= 0):
        raise ValueError("CAD okuyucusu pozitif sonlu spline ağırlıkları üretmedi.")
    pending = [(h, 0)]
    output = [h[0, :3] / h[0, 3]]
    while pending:
        c, depth = pending.pop()
        q = c[:, :3] / c[:, 3:]
        d = q[-1] - q[0]
        norm = float(d @ d)
        u = np.clip((q - q[0]) @ d / norm, 0, 1) if norm else np.zeros(len(q))
        bound = np.linalg.norm(q - q[0] - u[:, None] * d, axis=1).max()
        if bound <= tolerance:
            output.append(q[-1])
        elif depth < 24 and len(output) + len(pending) < 50000:
            levels = [c]
            while len(levels[-1]) > 1:
                levels.append((levels[-1][:-1] + levels[-1][1:]) / 2)
            pending.extend(
                [
                    (np.array([v[-1] for v in levels[::-1]]), depth + 1),
                    (np.array([v[0] for v in levels]), depth + 1),
                ]
            )
        else:
            raise ValueError("CAD spline değerlendirmesi toleransa yakınsamadı.")
    return np.array(output)


def nesting_signature(rings: dict[int, np.ndarray]) -> list[int | None]:
    """Basit ayrık poligonlarda kaynak sıra numarasıyla ebeveyn listesini hesaplar."""
    if set(rings) != set(range(len(rings))):
        raise ValueError("CAD sınır kimlikleri eksik veya sırasız.")
    # Son nokta kapanış etiketidir. Bir ULP yuvarlama farkını ayrı bir kısa
    # kenara dönüştürmek GEOS'ta sahte öz-kesişim oluşturabilir; kapanış farkı
    # validate_roundtrip içinde ayrıca ölçülüp aktarım bütçesine eklenir.
    polygons = [Polygon(rings[i][:-1, :2]) for i in range(len(rings))]
    if any(not p.is_valid or p.area == 0 for p in polygons):
        raise ValueError(
            "CAD profil aktarımı basit kapalı halkalar ister; öz-temas/kesişim giderilmelidir."
        )
    parents = []
    for i, p in enumerate(polygons):
        containers = []
        for j, other in enumerate(polygons):
            if i == j:
                continue
            if not p.exterior.disjoint(other.exterior):
                raise ValueError("CAD profil sınırları kesişiyor veya birbirine temas ediyor.")
            if other.contains(p):
                containers.append(j)
        parents.append(min(containers, key=lambda j: polygons[j].area) if containers else None)
    return parents


def flatten_bspline(
    controls: np.ndarray, knots: list, degree: int, weights: list | None, tolerance: float
) -> np.ndarray:
    """DXF NURBS'ünü homojen polinom aralıklarından kontrollü değerlendirir.

    Derece en çok üçtür. Her açık düğüm aralığında Taylor→Bernstein dönüşümü
    uygulanır; eğri yeniden uydurulmaz. Türevlerin float64 hesabı ayrıca etiketlidir.
    """
    if degree not in {1, 2, 3}:
        raise ValueError("CAD okuyucusu desteklenmeyen spline derecesi üretti.")
    w = np.ones(len(controls)) if weights is None or len(weights) == 0 else np.array(weights)
    h = np.column_stack([controls * w[:, None], w])
    spline = BSpline(knots, h, degree, extrapolate=False)
    breaks = np.unique(knots[degree:-degree])
    output = []
    for a, b in zip(breaks[:-1], breaks[1:], strict=True):
        derivatives = [
            spline.derivative(j)(a) * (b - a) ** j / math.factorial(j) for j in range(degree + 1)
        ]
        c = np.array(
            [
                sum(math.comb(k, j) / math.comb(degree, j) * derivatives[j] for j in range(k + 1))
                for k in range(degree + 1)
            ]
        )
        output.append(flatten_homogeneous(c, tolerance)[:-1])
    if not output:
        raise ValueError("CAD spline düğüm aralığı boş.")
    return np.vstack([*output, spline(breaks[-1])[:3] / spline(breaks[-1])[3]])


def _directed_cover(source: np.ndarray, target: np.ndarray, budget: float) -> tuple[float, int]:
    """Bütün doğru parçalarını tek sonlu kenar tanığının dışbükey uzaklığıyla kapsar.

    dist(.,segment) dışbükeydir; uç uzaklıklarının maksimumu bütün kirişi kapsar.
    Tanık yetersizse kiriş ikiye bölünür. GEOS tanık seçimi ve float64 uzaklıkları
    kullanılır; verified numerical certificate etiketi verilmez.
    """
    segments = np.stack([target[:-1], target[1:]], axis=1)
    segments = segments[np.any(segments[:, 0] != segments[:, 1], axis=1)]
    tree = shapely.STRtree(shapely.linestrings(segments))
    pending = np.stack([source[:-1], source[1:]], axis=1)
    maximum = 0.0
    count = 0
    for _ in range(25):
        if not len(pending):
            return maximum, count
        witnesses = tree.geometries.take(tree.nearest(shapely.points(pending.mean(axis=1))))
        bound = np.maximum(
            shapely.distance(shapely.points(pending[:, 0]), witnesses),
            shapely.distance(shapely.points(pending[:, 1]), witnesses),
        )
        good = bound <= budget
        count += int(good.sum())
        if np.any(good):
            maximum = max(maximum, float(bound[good].max()))
        remaining = pending[~good]
        if not len(remaining):
            return maximum, count
        endpoints = remaining.reshape(-1, 2)
        measured = shapely.distance(
            shapely.points(endpoints), tree.geometries.take(tree.nearest(shapely.points(endpoints)))
        )
        if measured.max() > budget:
            raise ValueError(f"CAD yeniden açma sapması toleransı aşıyor: {measured.max():.6g}.")
        mid = remaining.mean(axis=1)
        pending = np.concatenate(
            [np.stack([remaining[:, 0], mid], axis=1), np.stack([mid, remaining[:, 1]], axis=1)]
        )
        if len(pending) + count > 500000:
            break
    raise ValueError("CAD sonlu kenar uzaklık denetimi kaynak sınırında belirsiz kaldı.")


def validate_roundtrip(
    reference: dict, imported: list[np.ndarray], options: CadOptions, join_margin: float = 0.0
) -> dict:
    """Her halkayı iki yönde kapsar, Z düzlemi/kapanış ve yuvalanmayı karşılaştırır."""
    if len(imported) != len(reference):
        raise ValueError(
            f"CAD yeniden açmada sınır kaybı: {len(reference)} yerine {len(imported)}."
        )
    reference_closure = max(float(np.linalg.norm(q[0] - q[-1])) for q in reference.values())
    if reference_closure > options.tolerance / 8:
        raise ValueError("Kaynak modelin CAD referans poligonu kapanmıyor.")
    reference = {i: q.copy() for i, q in reference.items()}
    for q in reference.values():
        q[-1] = q[0]
    closure = 0.0
    zmax = 0.0
    for ring in imported:
        if not np.isfinite(ring).all() or len(ring) < 4:
            raise ValueError("CAD yeniden açmada boş/sonlu olmayan sınır.")
        closure = max(closure, float(np.linalg.norm(ring[0] - ring[-1])))
        zmax = max(zmax, float(np.max(np.abs(ring[:, 2]))))
    if max(closure, zmax) > options.tolerance / 8:
        raise ValueError("CAD sınırı kapanmıyor veya Z=0 düzleminden sapıyor.")

    def bounds(q: np.ndarray) -> np.ndarray:
        """Halka eşlemesi için fiziksel eksen kutusunu verir."""
        return np.r_[q[:, :2].min(axis=0), q[:, :2].max(axis=0)]

    cost = np.array(
        [[np.max(np.abs(bounds(q) - bounds(r))) for r in imported] for q in reference.values()]
    )
    left, right = linear_sum_assignment(cost)
    mapped = {int(i): imported[int(j)][:, :2].copy() for i, j in zip(left, right, strict=True)}
    for q in mapped.values():
        q[-1] = q[0]
    if nesting_signature(reference) != nesting_signature(mapped):
        raise ValueError("CAD yeniden açmada bileşen/boşluk yuvalanması değişti.")
    maximum = 0.0
    witnesses = 0
    numeric_margin = max(
        options.tolerance * 1e-8,
        max(float(np.max(np.abs(q))) for q in reference.values()) * np.finfo(float).eps * 128,
    )
    budget = (
        options.tolerance * 0.75 - numeric_margin - closure - zmax - join_margin - reference_closure
    )
    if budget <= 0:
        raise ValueError("CAD toleransı koordinat büyüklüğüne göre sayısal olarak çok küçük.")
    for i, q in reference.items():
        for a, b in [(q, mapped[i]), (mapped[i], q)]:
            upper, count = _directed_cover(a, b, budget)
            maximum = max(maximum, upper)
            witnesses += count
    total = (
        maximum
        + options.tolerance / 4
        + numeric_margin
        + closure
        + zmax
        + join_margin
        + reference_closure
    )
    if total > options.tolerance:
        raise ValueError("CAD aktarım hata hedefi sağlanamadı.")
    return {
        "method": "bidirectional_finite_segment_convex_witness_cover_float64",
        "transfer_upper_estimate": total,
        "tolerance": options.tolerance,
        "unit": options.unit,
        "curve_polygon_budget_each": options.tolerance / 8,
        "numeric_margin": numeric_margin,
        "witness_segments": witnesses,
        "boundary_count": len(imported),
        "polygon_nesting_preserved": True,
        "max_closure_gap": closure,
        "max_abs_z": zmax,
        "join_margin": join_margin,
        "reference_closure_roundoff": reference_closure,
        "verified_numerical_certificate": False,
        "analytic_isotopy_proven_for_cad_file": False,
        "scope": "CAD okuyucusundan tekrar alınan geometri; float64 kontrollü poligonlar. Kaynak model sertifikasından ayrıdır.",
    }
