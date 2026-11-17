"""Ürün deneyinin hata yakalama sözleşmesi ve varsa gerçek FreeCAD kabul testleri."""

import json
import os
from pathlib import Path
from threading import Event

import numpy as np
import pytest
from shapely.geometry import Polygon

from sekilden_denkleme.cad import export_cad
from sekilden_denkleme.cad_compatibility import evaluate_product, inspect_cad, run_freecad_check
from sekilden_denkleme.cad_geometry import CadOptions
from sekilden_denkleme.fitting import AnalysisCancelled
from sekilden_denkleme.project import load_project

ROOT = Path(__file__).parents[1]


def test_byte_changed_cad_is_rejected_before_executing_product(tmp_path):
    source = ROOT / "examples/cad_validation/circle/reconstruction.dxf"
    path = tmp_path / source.name
    path.write_bytes(source.read_bytes() + b"changed")
    path.with_name(path.name + ".cad.json").write_bytes(
        source.with_name(source.name + ".cad.json").read_bytes()
    )
    with pytest.raises(ValueError, match="hash"):
        inspect_cad(path)


def test_product_scale_holes_and_nonfinite_measurements_cannot_pass():
    data, reference = inspect_cad(ROOT / "examples/cad_validation/ring/reconstruction.step")
    points = np.vstack(list(reference.values()))
    area = Polygon(reference[0]).area - Polygon(reference[1]).area
    measured = {
        "bounding_box_mm": [*points.min(axis=0), 0, *points.max(axis=0), 0],
        "profile_area_mm2": area,
        "extrusion_volume_mm3": area * 5,
        "profile_face_count": 1,
        "profile_hole_count": 1,
        "all_wires_closed": True,
        "profile_valid": True,
        "extrusion_valid": True,
        "extrusion_solid_count": 1,
        "rings_mm": [np.column_stack((r, np.zeros(len(r)))).tolist() for r in reference.values()],
        "max_join_gap_mm": 0,
        "volume_refinement_difference_mm3": 0,
    }
    report = evaluate_product(data, reference, measured)
    assert report["status"] == "passed" and report["verified_numerical_certificate"] is False
    measured["profile_hole_count"] = 0
    assert evaluate_product(data, reference, measured)["status"] == "failed"
    measured["profile_hole_count"] = 1
    measured["bounding_box_mm"][3] += 1
    assert evaluate_product(data, reference, measured)["checks"]["dimensions_mm"] is False
    measured["profile_area_mm2"] = float("nan")
    with pytest.raises(ValueError, match="sonlu"):
        evaluate_product(data, reference, measured)


@pytest.fixture(scope="module")
def freecad_command():
    configured = os.environ.get("FREECADCMD_PATH")
    candidates = (
        [Path(configured)]
        if configured
        else sorted((ROOT / ".tmp/freecad").glob("*/bin/freecadcmd.exe"))
    )
    if not candidates or not candidates[-1].is_file():
        pytest.skip("Ayrı FreeCADCmd kurulumu yok; ürün entegrasyon testi çalıştırılmadı.")
    return candidates[-1]


@pytest.mark.parametrize("kind", ["dxf", "step", "iges"])
def test_real_freecad_product_import_holes_and_extrusion(tmp_path, freecad_command, kind):
    """Gerçek ürün süreci; uygulamanın OCP/ezdxf okuyucularından farklı adaptör."""
    result = load_project(ROOT / "examples/cad_validation/ring/model.json")
    target = export_cad(result, tmp_path / f"ring.{kind}", kind, CadOptions(scale=0.1))
    path = run_freecad_check(freecad_command, target, tmp_path / "product")
    report = json.loads(path.read_text(encoding="utf8"))
    assert report["evaluation"]["status"] == "passed", report
    assert report["measured"]["profile_hole_count"] == 1
    assert report["measured"]["gui_tested"] is False and report["measured"]["human_trial"] is False
    assert report["evaluation"]["independent_geometry_kernel"] is False
    assert (path.parent / "inspection.FCStd").is_file()
    assert report["measured"]["edit_probe"]["status"] == "passed"


@pytest.mark.parametrize("kind", ["step", "iges"])
def test_disconnected_iges_exports_root_faces_for_freecad(tmp_path, freecad_command, kind):
    """402 grup regresyonu: ayrı yüz kökleri iki bileşeni üründe kullanılabilir kılar."""
    result = load_project(ROOT / "examples/cad_validation/components/model.json")
    target = export_cad(
        result,
        tmp_path / f"components.{kind}",
        kind,
        CadOptions(unit="m", scale=0.001, tolerance=0.00001),
    )
    path = run_freecad_check(freecad_command, target, tmp_path / "product")
    report = json.loads(path.read_text(encoding="utf8"))
    assert report["evaluation"]["status"] == "passed", report
    assert report["measured"]["profile_face_count"] == 2


def test_bspline_extrusion_uses_two_mesh_refinements_and_keeps_native_volume(
    tmp_path, freecad_command
):
    result = load_project(ROOT / "examples/cad_validation/spline/model.json")
    target = export_cad(result, tmp_path / "spline.step", "step", CadOptions(scale=0.1))
    path = run_freecad_check(freecad_command, target, tmp_path / "product")
    report = json.loads(path.read_text(encoding="utf8"))
    assert report["evaluation"]["status"] == "passed", report
    measured = report["measured"]
    assert len(measured["volume_triangle_counts"]) == 2
    assert measured["volume_deflections_mm"][0] == measured["volume_deflections_mm"][1] * 2
    assert measured["extrusion_volume_native_mm3"] > 0


def test_cancellation_kills_only_its_product_process_and_does_not_publish_success(
    tmp_path, monkeypatch
):
    """Süreç taklidinde iptal yolu; gerçek ürün testleri yukarıda ayrıca çalışır."""
    executable = tmp_path / "FreeCADCmd.exe"
    executable.write_text("process-test-placeholder")
    stopped = []

    class Process:
        def poll(self):
            return None

        def kill(self):
            stopped.append("kill")

        def wait(self):
            stopped.append("wait")

    monkeypatch.setattr(
        "sekilden_denkleme.cad_compatibility.subprocess.Popen", lambda *a, **k: Process()
    )
    cancel = Event()
    cancel.set()
    with pytest.raises(AnalysisCancelled):
        run_freecad_check(
            executable,
            ROOT / "examples/cad_validation/ring/reconstruction.step",
            tmp_path / "runs",
            cancel=cancel,
        )
    assert stopped == ["kill", "wait"]
    assert not list(tmp_path.glob("runs/*/compatibility.json"))
