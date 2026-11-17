"""DXF R2013 yerel eğrileri, sınır grupları ve parametrik NURBS aktarımı.

Yalnızca CAD işlemi sırasında ezdxf yüklenir. SPLINE katsayıları, düğümler ve
pozitif rasyonel ağırlıklar korunur. Bu aktarım yerel sketch kısıt ağı üretmez.
"""

import json
import math
from pathlib import Path

import numpy as np

from .cad_geometry import CadCurve, CadOptions, flatten_bspline

DXF_UNITS = {"mm": 4, "cm": 5, "m": 6, "in": 1}
APPID = "SD_EQUATIONS"


def write_dxf(curves: list[CadCurve], path: Path, options: CadOptions) -> list[dict]:
    """Gerçek DXF dosyasını üretir; her nesneyi model parçasına XDATA ile bağlar."""
    import ezdxf

    doc = ezdxf.new("R2013")
    doc.units = DXF_UNITS[options.unit]
    doc.header["$MEASUREMENT"] = 0 if options.unit == "in" else 1
    doc.appids.add(APPID)
    msp = doc.modelspace()
    groups = {}
    mapping = []
    for c in curves:
        p = c.params
        layer = f"SD_B{c.boundary_id:04d}"
        if layer not in doc.layers:
            doc.layers.add(layer)
        attrs = {"layer": layer}
        if c.kind == "line":
            entity = msp.add_line((*p["a"], 0), (*p["b"], 0), dxfattribs=attrs)
        elif c.kind == "circle":
            entity = msp.add_circle((*p["center"], 0), p["radius"], dxfattribs=attrs)
        elif c.kind == "arc":
            entity = msp.add_arc(
                (*p["center"], 0),
                p["radius"],
                math.degrees(p["start"]),
                math.degrees(p["end"]),
                dxfattribs=attrs,
            )
        elif c.kind == "ellipse":
            major = (p["major"] * math.cos(p["rotation"]), p["major"] * math.sin(p["rotation"]), 0)
            entity = msp.add_ellipse(
                (*p["center"], 0),
                major,
                p["minor"] / p["major"],
                start_param=0 if p["full"] else p["start"],
                end_param=2 * math.pi if p["full"] else p["end"],
                dxfattribs=attrs,
            )
        elif c.kind == "bspline":
            entity = msp.add_spline(degree=p["degree"], dxfattribs=attrs)
            entity.control_points = [(*q, 0) for q in p["controls"]]
            entity.knots = p["knots"]
            entity.dxf.flags = 8
            if p["weights"] is not None:
                entity.weights = p["weights"]
                entity.dxf.flags |= 4
        elif c.kind == "polyline":
            points = p["points"]
            closed = np.array_equal(points[0], points[-1])
            entity = msp.add_lwpolyline(
                points[:-1] if closed else points, close=closed, dxfattribs=attrs
            )
        else:
            raise ValueError(f"DXF için bilinmeyen CAD türü: {c.kind}")
        tag = {
            "piece": c.source_piece,
            "boundary": c.boundary_id,
            "reversed": c.reversed,
            "interval": c.interval,
        }
        entity.set_xdata(APPID, [(1000, json.dumps(tag, separators=(",", ":")))])
        groups.setdefault(c.boundary_id, []).append(entity)
        mapping.append({**tag, "handle": entity.dxf.handle, "entity": entity.dxftype()})
    for i, entities in groups.items():
        doc.groups.new(f"SD_BOUNDARY_{i}", description=f"Sekilden Denkleme boundary {i}").set_data(
            entities
        )
    doc.saveas(path)
    return mapping


def _entity_points(entity, tolerance: float) -> np.ndarray:
    """CAD dosyasından okunan yerel geometriyi aynı fiziksel birimde kapsar."""
    kind = entity.dxftype()
    p = entity.dxf
    if kind == "LINE":
        return np.array([p.start, p.end])
    if kind == "LWPOLYLINE":
        q = np.array([(*row[:2], float(p.elevation)) for row in entity.get_points()])
        return np.vstack([q, q[0]]) if entity.closed else q
    if kind == "SPLINE":
        return flatten_bspline(
            np.array(entity.control_points),
            list(entity.knots),
            p.degree,
            list(entity.weights),
            tolerance,
        )
    if kind in {"CIRCLE", "ARC"}:
        a = math.radians(p.start_angle) if kind == "ARC" else 0
        width = math.radians((p.end_angle - p.start_angle) % 360) if kind == "ARC" else 2 * math.pi
        radius = p.radius
        major = np.array([radius, 0, 0])
        minor = np.array([0, radius, 0])
    elif kind == "ELLIPSE":
        a = p.start_param
        width = (p.end_param - a) % (2 * math.pi)
        if abs(width) < 1e-12:
            width = 2 * math.pi
        major = np.array(p.major_axis)
        minor = np.cross(np.array(p.extrusion), major) * p.ratio
        radius = np.linalg.norm(major)
    else:
        raise ValueError(f"Beklenmeyen DXF geometri türü: {kind}")
    count = max(4, math.ceil(width * math.sqrt(radius / (8 * tolerance))))
    if count > 200000:
        raise ValueError("DXF konik değerlendirmesi nokta sınırını aşıyor.")
    t = np.linspace(a, a + width, count + 1)
    return np.array(p.center) + np.cos(t[:, None]) * major + np.sin(t[:, None]) * minor


def read_dxf(path: Path, options: CadOptions) -> tuple[list[np.ndarray], dict]:
    """DXF'yi gerçek okuyucuyla tekrar açar; grup, birim ve sonlu geometriyi denetler."""
    import ezdxf

    doc = ezdxf.readfile(path)
    auditor = doc.audit()
    if auditor.has_errors:
        raise ValueError("DXF yapısal denetimi başarısız: " + str(auditor.errors[:3]))
    if doc.units != DXF_UNITS[options.unit]:
        raise ValueError("DXF fiziksel birimi korunmadı.")
    grouped = {}
    count = 0
    for e in doc.modelspace():
        if not e.has_xdata(APPID):
            raise ValueError("DXF parça eşleme bilgisi eksik.")
        tag = json.loads(e.get_xdata(APPID)[0].value)
        q = _entity_points(e, options.tolerance / 8)
        if tag["reversed"]:
            q = q[::-1]
        grouped.setdefault(tag["boundary"], []).append(q)
        count += 1
    rings = []
    gap = 0.0
    for i in sorted(grouped):
        parts = grouped[i]
        for a, b in zip(parts, parts[1:] + parts[:1], strict=True):
            gap = max(gap, float(np.linalg.norm(a[-1] - b[0])))
        if gap > options.tolerance / 8:
            raise ValueError("DXF parça birleşimleri açıldı.")
        rings.append(np.vstack([*[q[:-1] for q in parts], parts[-1][-1]]))
    return rings, {
        "reader": "ezdxf",
        "reader_version": ezdxf.__version__,
        "entity_count": count,
        "group_count": len(doc.groups),
        "dxf_version": doc.dxfversion,
        "max_join_gap": gap,
    }
