"""Open CASCADE ile gerçek STEP/IGES düzlemsel tel profili aktarımı.

Çekirdek koordinatları mm'dir. Çıktı birimi yazıcının birim dönüşümüyle korunur.
Bu modül CAD işlemi sırasında yüklenir; GUI başlangıcına ağır çekirdek yüklemez.
"""

import math
from pathlib import Path

import numpy as np

from .cad_geometry import UNIT_MM, CadCurve, CadOptions, flatten_homogeneous, nesting_signature

OCCT_UNITS = {"mm": "MM", "cm": "CM", "m": "M", "in": "INCH"}


def _curve_edges(c: CadCurve, factor: float) -> list:
    """Asıl katsayılardan kenar kurar; uydurma veya otomatik şekil iyileştirmesi yapmaz."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.Geom import Geom_BSplineCurve, Geom_Circle, Geom_Ellipse
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.TColgp import TColgp_Array1OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal

    def point(q):
        return gp_Pnt(float(q[0]) * factor, float(q[1]) * factor, 0)

    p = c.params
    if c.kind == "line":
        makers = [BRepBuilderAPI_MakeEdge(point(p["a"]), point(p["b"]))]
    elif c.kind == "polyline":
        makers = [
            BRepBuilderAPI_MakeEdge(point(a), point(b))
            for a, b in zip(p["points"][:-1], p["points"][1:], strict=True)
        ]
    elif c.kind in {"circle", "arc", "ellipse"}:
        angle = p.get("rotation", 0)
        axes = gp_Ax2(
            point(p["center"]), gp_Dir(0, 0, 1), gp_Dir(math.cos(angle), math.sin(angle), 0)
        )
        curve = (
            Geom_Ellipse(axes, p["major"] * factor, p["minor"] * factor)
            if c.kind == "ellipse"
            else Geom_Circle(axes, p["radius"] * factor)
        )
        makers = (
            [BRepBuilderAPI_MakeEdge(curve)]
            if c.kind == "circle" or p.get("full")
            else [BRepBuilderAPI_MakeEdge(curve, p["start"], p["end"])]
        )
    elif c.kind == "bspline":
        poles = TColgp_Array1OfPnt(1, len(p["controls"]))
        for i, q in enumerate(p["controls"], 1):
            poles.SetValue(i, point(q))
        values, multiplicities = np.unique(p["knots"], return_counts=True)
        knots = TColStd_Array1OfReal(1, len(values))
        mult = TColStd_Array1OfInteger(1, len(values))
        for i, (k, m) in enumerate(zip(values, multiplicities, strict=True), 1):
            knots.SetValue(i, float(k))
            mult.SetValue(i, int(m))
        args = (poles, knots, mult, p["degree"], False)
        if p["weights"] is not None:
            weights = TColStd_Array1OfReal(1, len(p["weights"]))
            for i, w in enumerate(p["weights"], 1):
                weights.SetValue(i, w)
            args = (poles, weights, knots, mult, p["degree"], False)
        curve = Geom_BSplineCurve(*args)
        makers = [BRepBuilderAPI_MakeEdge(curve)]
    else:
        raise ValueError(f"Open CASCADE için bilinmeyen eğri: {c.kind}")
    edges = []
    for maker in makers:
        if not maker.IsDone():
            raise ValueError("Open CASCADE sonlu eğri kenarı kuramadı.")
        edge = maker.Edge()
        if c.reversed:
            edge.Reverse()
        edges.append(edge)
    return edges


def write_occt(
    curves: list[CadCurve], path: Path, kind: str, options: CadOptions, reference: dict
) -> list[dict]:
    """Kapalı profilleri delikli düzlemsel yüzler olarak STEP AP214/IGES'e yazar.

    STEP salt wire çevirisinde tel topolojisini geometrik eğri kümesine
    indirgediğinden düzlemsel yüz kullanılır. Katı veya kalınlık eklenmez.
    """
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.IGESControl import IGESControl_Writer
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.TopoDS import TopoDS_Compound

    factor = UNIT_MM[options.unit]
    grouped = {}
    mapping = []
    for c in curves:
        edges = _curve_edges(c, factor)
        grouped.setdefault(c.boundary_id, []).extend(edges)
        mapping.append(
            {
                "piece": c.source_piece,
                "boundary": c.boundary_id,
                "native_curve": c.kind,
                "edge_count": len(edges),
                "reversed": c.reversed,
                "interval": c.interval,
            }
        )
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    wires = {}
    parents = nesting_signature(reference)
    depths = []
    for i in range(len(parents)):
        depth = 0
        parent = parents[i]
        while parent is not None:
            depth += 1
            parent = parents[parent]
        depths.append(depth)
    for i, edges in sorted(grouped.items()):
        wire_builder = BRepBuilderAPI_MakeWire()
        for edge in edges:
            wire_builder.Add(edge)
        if not wire_builder.IsDone():
            raise ValueError("CAD kenarları kapalı tel olarak birleştirilemedi.")
        wire = wire_builder.Wire()
        if not wire.Closed() or not BRepCheck_Analyzer(wire).IsValid():
            raise ValueError("Open CASCADE tel kapanış/geçerlilik denetimi başarısız.")
        q = reference[i]
        area = float(np.sum(q[:-1, 0] * q[1:, 1] - q[:-1, 1] * q[1:, 0]))
        if (area > 0) != (depths[i] % 2 == 0):
            wire.Reverse()
            for item in mapping:
                if item["boundary"] == i:
                    item["face_wire_reversed"] = True
        else:
            for item in mapping:
                if item["boundary"] == i:
                    item["face_wire_reversed"] = False
        wires[i] = wire
    faces = []
    for i, wire in wires.items():
        if depths[i] % 2:
            continue
        face_builder = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), wire, True)
        for j, parent in enumerate(parents):
            if parent == i:
                face_builder.Add(wires[j])
        if not face_builder.IsDone() or not BRepCheck_Analyzer(face_builder.Face()).IsValid():
            raise ValueError("CAD düzlemsel yüz/delik denetimi başarısız.")
        builder.Add(compound, face_builder.Face())
        faces.append(face_builder.Face())
    if kind == "step":
        writer = STEPControl_Writer()
        Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
        if not Interface_Static.SetCVal_s("write.step.unit", OCCT_UNITS[options.unit]):
            raise ValueError("STEP yazıcısı çıktı birimini kabul etmedi.")
        Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
        if writer.Transfer(compound, STEPControl_AsIs) != IFSelect_RetDone:
            raise ValueError("STEP geometri çevirisi başarısız.")
        if writer.Write(str(path)) != IFSelect_RetDone:
            raise OSError("STEP dosyası yazılamadı.")
    else:
        writer = IGESControl_Writer(OCCT_UNITS[options.unit], 0)
        Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
        # Ayrık yüzler ayrı IGES kökleridir. Compound'un ürettiği 402 grubu
        # FreeCAD 1.1.4 XDE içe alıcısında boş belgeye dönüşebiliyor.
        for face in faces:
            if not writer.AddShape(face):
                raise ValueError("IGES geometri çevirisi başarısız.")
        writer.ComputeModel()
        if not writer.Write(str(path)):
            raise OSError("IGES dosyası yazılamadı.")
    return mapping


def _edge_points(edge, tolerance_mm: float) -> np.ndarray:
    """Okunan gerçek OCCT eğrisini sonlu aralığında kontrollü değerlendirir."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import (
        GeomAbs_BezierCurve,
        GeomAbs_BSplineCurve,
        GeomAbs_Circle,
        GeomAbs_Ellipse,
        GeomAbs_Line,
    )
    from OCP.GeomConvert import GeomConvert_BSplineCurveToBezierCurve
    from OCP.TopAbs import TopAbs_REVERSED

    adaptor = BRepAdaptor_Curve(edge)
    kind = adaptor.GetType()
    a, b = adaptor.FirstParameter(), adaptor.LastParameter()

    def point(t):
        return np.array(adaptor.Value(float(t)).Coord())

    if kind == GeomAbs_Line:
        q = np.array([point(a), point(b)])
    elif kind in {GeomAbs_Circle, GeomAbs_Ellipse}:
        radius = (
            adaptor.Circle().Radius() if kind == GeomAbs_Circle else adaptor.Ellipse().MajorRadius()
        )
        count = max(4, math.ceil((b - a) * math.sqrt(radius / (8 * tolerance_mm))))
        if count > 200000:
            raise ValueError("CAD konik okuyucusu nokta sınırını aştı.")
        q = np.array([point(t) for t in np.linspace(a, b, count + 1)])
    elif kind in {GeomAbs_BezierCurve, GeomAbs_BSplineCurve}:
        if kind == GeomAbs_BSplineCurve:
            converter = GeomConvert_BSplineCurveToBezierCurve(adaptor.BSpline(), a, b, 1e-12)
            beziers = [converter.Arc(i) for i in range(1, converter.NbArcs() + 1)]
        else:
            curve = adaptor.Bezier()
            curve.Segment(a, b)
            beziers = [curve]
        pieces = []
        for curve in beziers:
            h = np.array(
                [
                    [*(np.array(curve.Pole(i).Coord()) * curve.Weight(i)), curve.Weight(i)]
                    for i in range(1, curve.NbPoles() + 1)
                ]
            )
            pieces.append(flatten_homogeneous(h, tolerance_mm))
        q = np.vstack([*[p[:-1] for p in pieces], pieces[-1][-1]])
    else:
        raise ValueError("CAD okuyucusu desteklenmeyen eğri türü üretti.")
    return q[::-1] if edge.Orientation() == TopAbs_REVERSED else q


def read_occt(path: Path, kind: str, options: CadOptions) -> tuple[list[np.ndarray], dict]:
    """STEP/IGES dosyasını yeniden açar; her telin bütün kenarlarını geri okur."""
    import OCP
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.IGESControl import IGESControl_Reader
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    reader = STEPControl_Reader() if kind == "step" else IGESControl_Reader()
    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError(f"{kind.upper()} dosyası tekrar okunamadı.")
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull() or not BRepCheck_Analyzer(shape).IsValid():
        raise ValueError(f"{kind.upper()} yeniden açılan geometri geçersiz.")
    wires = TopExp_Explorer(shape, TopAbs_WIRE)
    rings = []
    edges = 0
    gap = 0.0
    factor = UNIT_MM[options.unit]
    while wires.More():
        explorer = BRepTools_WireExplorer(TopoDS.Wire_s(wires.Current()))
        parts = []
        while explorer.More():
            parts.append(_edge_points(explorer.Current(), options.tolerance * factor / 8) / factor)
            edges += 1
            explorer.Next()
        if not parts:
            raise ValueError("CAD okuyucusunda boş tel.")
        for a, b in zip(parts, parts[1:] + parts[:1], strict=True):
            gap = max(gap, float(np.linalg.norm(a[-1] - b[0])))
        rings.append(np.vstack([*[p[:-1] for p in parts], parts[-1][-1]]))
        wires.Next()
    if gap > options.tolerance / 8:
        raise ValueError("CAD yeniden açmada parça birleşimleri ayrıldı.")
    return rings, {
        "reader": "Open CASCADE/OCP",
        "reader_version": OCP.__version__,
        "edge_count": edges,
        "wire_count": len(rings),
        "max_join_gap": gap,
        "internal_reader_unit": "mm",
    }
