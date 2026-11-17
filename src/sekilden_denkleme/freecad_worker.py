"""FreeCADCmd'nin kendi Python ortamında yürütülen dar kapsamlı içe alma deneyi.

Uygulama modüllerini veya ezdxf/OCP paketlerini içe aktarmaz. Girdi/yol sözleşmesi
SD_CAD_CHECK_REQUEST JSON'udur. Sonuç bir yazılım deneyidir; insan pilotu değildir.
"""

import hashlib
import json
import math
import os
import platform
import time
import traceback
from pathlib import Path


def run(request: dict) -> dict:
    """Ürünün gerçek içe alıcısıyla mm geometri, profil ve ekstrüzyon ölçer."""
    import FreeCAD as App
    import Import
    import Part

    path = Path(request["cad_path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != request["cad_sha256"]:
        raise ValueError("CAD dosyası denetim başlatıldıktan sonra değişmiş.")
    doc = App.newDocument("SDCompatibility")
    started = time.perf_counter()
    try:
        if path.suffix.lower() == ".dxf":
            Import.readDXF(str(path), doc.Name, False)
        else:
            Import.insert(str(path), doc.Name)
        doc.recompute()
        import_seconds = time.perf_counter() - started
        doc.saveAs(str(Path(request["document_path"]).with_name("imported.FCStd")))
        request["observations"] = {
            "objects": [
                {
                    "name": o.Name,
                    "type": o.TypeId,
                    "parents": [p.Name for p in o.InList],
                    "has_shape": hasattr(o, "Shape"),
                }
                for o in doc.Objects
            ]
        }
        # App::Part sanal Shape'i ve App::Origin eksen/düzlemleri ithal geometri değildir.
        objects = [
            o for o in doc.Objects if o.isDerivedFrom("Part::Feature") and not o.Shape.isNull()
        ]
        shapes = [o.Shape for o in objects if not any(p in objects for p in o.InList)]
        if not shapes:
            raise ValueError("FreeCAD içe alıcısı geometri oluşturmadı.")
        shape = Part.makeCompound(shapes)
        request["observations"].update(
            shape_count=len(shapes),
            face_count=len(shape.Faces),
            edge_count=len(shape.Edges),
            shape_valid=shape.isValid(),
        )
        imported_faces = len(shape.Faces)
        if imported_faces:
            profile = shape
            wires = [w for face in shape.Faces for w in face.Wires]
            preparation = "native_imported_faces"
        else:
            wires = [Part.Wire(edges) for edges in Part.sortEdges(shape.Edges)]
            if not wires or any(not w.isClosed() for w in wires):
                raise ValueError("İçe alınan kenarlar kapalı profil oluşturmuyor.")
            profile = Part.makeFace(wires, "Part::FaceMakerBullseye")
            preparation = "explicit_face_construction_from_imported_wires"
            obj = doc.addObject("Part::Feature", "ProfileProbe")
            obj.Label = "Denetim: yerel tellerden oluşturulan yüz"
            obj.Shape = profile
        points, max_gap = [], 0.0
        delta = request["tolerance_mm"] / 8
        for wire in wires:
            ring = []
            for edge in wire.OrderedEdges:
                samples = edge.discretize(Deflection=delta)
                if len(samples) < 2:
                    raise ValueError("FreeCAD kenar örneklemesi yetersiz.")
                if edge.Orientation == "Reversed":
                    samples.reverse()
                if ring and (samples[-1] - ring[-1]).Length < (samples[0] - ring[-1]).Length:
                    samples.reverse()
                if ring:
                    max_gap = max(max_gap, (samples[0] - ring[-1]).Length)
                    ring.extend(samples[1:])
                else:
                    ring.extend(samples)
                if len(ring) > 250000:
                    raise ValueError("FreeCAD örnekleme kaynak sınırı aşıldı.")
            max_gap = max(max_gap, (ring[-1] - ring[0]).Length)
            points.append([[p.x, p.y, p.z] for p in ring])
        extrusion = profile.extrude(App.Vector(0, 0, 5))
        native_volume = extrusion.Volume
        mesh_volumes = []
        triangle_counts = []
        for deflection in (delta, delta / 2):
            # Bağımsız sayısal hacim: yönlü yüz üçgenlerinden tetrahedron toplamı.
            vertices, triangles = extrusion.cleaned().tessellate(deflection)
            if len(triangles) > 1000000:
                raise ValueError("Hacim ağı 1.000.000 üçgen sınırını aşıyor.")
            center = extrusion.BoundBox.Center
            vertices = [v - center for v in vertices]
            mesh_volumes.append(
                abs(
                    math.fsum(
                        vertices[a].dot(vertices[b].cross(vertices[c])) for a, b, c in triangles
                    )
                )
                / 6
            )
            triangle_counts.append(len(triangles))
        obj = doc.addObject("Part::Feature", "ExtrusionProbe")
        obj.Label = "Denetim: 5 mm ekstrüzyon"
        obj.Shape = extrusion
        edit_probe = {
            "status": "not_applicable",
            "scope": "copy_of_imported_native_curve; not GUI/sketch history",
        }
        for edge in shape.Edges:
            curve = edge.Curve.copy()
            try:
                if isinstance(curve, Part.Circle):
                    original = curve.Radius
                    curve.Radius = original * 1.1
                    edited = curve.toShape(edge.FirstParameter, edge.LastParameter)
                    edit_probe.update(
                        status="passed", kind="circle_radius", before=original, after=curve.Radius
                    )
                elif isinstance(curve, Part.BSplineCurve):
                    pole = curve.getPole(2)
                    curve.setPole(2, pole + App.Vector(0.1, 0, 0))
                    edited = curve.toShape()
                    edit_probe.update(status="passed", kind="bspline_pole", displacement_mm=0.1)
                else:
                    continue
                if not edited.isValid():
                    raise ValueError("Düzenlenen eğri geçersiz.")
                obj = doc.addObject("Part::Feature", "EditProbe")
                obj.Label = "Denetim: içe alınan eğri kopyasının parametre değişimi"
                obj.Shape = edited
                break
            except Exception as error:
                edit_probe.update(status="failed", reason=str(error))
                break
        doc.recompute()
        doc.saveAs(request["document_path"])
        bbox = shape.optimalBoundingBox(False, False)
        return {
            "status": "measured",
            "application": "FreeCAD",
            "version": list(App.Version()),
            "python": platform.python_version(),
            "kernel": getattr(Part, "OCC_VERSION", "unknown"),
            "import_seconds": import_seconds,
            "total_seconds": time.perf_counter() - started,
            "imported_object_count": len(objects),
            "edge_count": len(shape.Edges),
            "imported_face_count": imported_faces,
            "profile_preparation": preparation,
            "profile_face_count": len(profile.Faces),
            "profile_hole_count": sum(len(f.Wires) - 1 for f in profile.Faces),
            "profile_area_mm2": profile.Area,
            "profile_valid": profile.isValid(),
            "all_wires_closed": all(w.isClosed() for w in wires),
            "extrusion_valid": extrusion.isValid(),
            "extrusion_volume_mm3": mesh_volumes[-1],
            "extrusion_volume_native_mm3": native_volume,
            "extrusion_volume_method": "oriented_triangle_tetrahedra_two_deflections; not certified",
            "volume_refinement_difference_mm3": abs(mesh_volumes[-1] - mesh_volumes[0]),
            "volume_deflections_mm": [delta, delta / 2],
            "volume_triangle_counts": triangle_counts,
            "extrusion_solid_count": len(extrusion.Solids),
            "extrusion_length_mm": 5,
            "bounding_box_mm": [bbox.XMin, bbox.YMin, bbox.ZMin, bbox.XMax, bbox.YMax, bbox.ZMax],
            "rings_mm": points,
            "max_join_gap_mm": max_gap,
            "discretization": {
                "method": "FreeCAD Edge.discretize(Deflection)",
                "target_mm": delta,
                "verified_bound": False,
            },
            "edit_probe": edit_probe,
            "document_path": request["document_path"],
            "gui_tested": False,
            "human_trial": False,
        }
    finally:
        App.closeDocument(doc.Name)


def main() -> None:
    """İstisnayı da JSON olarak kaydeder; çıkış kodu tek başına başarı sayılmaz."""
    request = json.loads(Path(os.environ["SD_CAD_CHECK_REQUEST"]).read_text(encoding="utf8"))
    try:
        result = run(request)
    except Exception as error:
        result = {
            "status": "failed",
            "reason": str(error),
            "traceback": traceback.format_exc(),
            "observations": request.get("observations", {}),
        }
    Path(request["response_path"]).write_text(
        json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf8"
    )


if __name__ == "__main__" or os.environ.get("SD_CAD_CHECK_REQUEST"):
    main()
