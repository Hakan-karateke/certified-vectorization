"""Gerçek CAD okuyucularında geometri, birim, topoloji ve güvenli kayıt kabul testleri."""

import copy
import hashlib
import json
import math
from dataclasses import asdict, replace
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest

from sekilden_denkleme import AnalysisConfig, analyze
from sekilden_denkleme.cad import available_formats, export_cad
from sekilden_denkleme.cad_geometry import UNIT_MM, CadOptions, native_curves
from sekilden_denkleme.curves import evaluate, new_piece
from sekilden_denkleme.evaluation import complexity
from sekilden_denkleme.models import Candidate
from sekilden_denkleme.project import load_project

pytestmark = pytest.mark.skipif(
    not all(available_formats().values()), reason="İsteğe bağlı CAD bağımlılıkları kurulu değil."
)
ROOT = Path(__file__).parents[1]
SOURCES = {
    "circle": "examples/certified_extensions/circle/model.json",
    "ellipse": "examples/certified_extensions/ellipse/model.json",
    "ring": "examples/certified_extensions/ring/model.json",
    "spline": "examples/certified_extensions/spline/model.json",
    "mixed": "examples/arc_stress/illustrations/corner_curve/model.json",
    "rounded": "examples/arc_stress/illustrations/rounded_rectangle/model.json",
}


@lru_cache
def source_result(name):
    """Gerçek rasterden önceden üretilmiş projeyi uydurmadan açar ve modül boyunca paylaşır."""
    return load_project(ROOT / SOURCES[name])


@pytest.mark.parametrize("name", list(SOURCES))
@pytest.mark.parametrize("kind", ["dxf", "step", "iges"])
def test_real_cad_geometry_roundtrip_and_parameter_record(tmp_path, name, kind):
    """Altı gerçek modelin üç gerçek CAD dosyasında bütün sınırlarını tekrar denetler."""
    result = source_result(name)
    before = [asdict(p) for p in result.selected.pieces]
    path = export_cad(result, tmp_path / f"{name}.{kind}", kind, CadOptions(scale=0.1))
    metadata = json.loads(path.with_name(path.name + ".cad.json").read_text(encoding="utf8"))
    import jsonschema

    schema = json.loads((ROOT / "docs/cad.schema.json").read_text(encoding="utf8"))
    jsonschema.Draft202012Validator(schema).validate(metadata)
    with pytest.raises(ValueError, match="CAD eşleme"):
        load_project(path.with_name(path.name + ".cad.json"))
    assert metadata["cad_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert metadata["selected_model"]["pieces"] == before
    assert metadata["selected_model"]["equations"] and metadata["topology"] == result.topology
    assert metadata["transfer_validation"]["transfer_upper_estimate"] <= 0.01
    assert metadata["transfer_validation"]["polygon_nesting_preserved"]
    assert not metadata["transfer_validation"]["verified_numerical_certificate"]
    assert not metadata["approximated_source_pieces"]
    assert [asdict(p) for p in result.selected.pieces] == before
    if kind == "dxf":
        import ezdxf

        doc = ezdxf.readfile(path)
        assert doc.units == 4 and len(doc.groups) == len(result.reference_boundaries)
        assert set(e.dxftype() for e in doc.modelspace()) <= {
            "LINE",
            "ARC",
            "CIRCLE",
            "ELLIPSE",
            "SPLINE",
        }
        if name == "mixed":
            assert any(
                e.dxftype() == "SPLINE" and e.dxf.degree == 2 and e.dxf.flags & 4
                for e in doc.modelspace()
            )
    elif kind == "step":
        assert path.read_bytes().lstrip().startswith(b"ISO-10303-21;")
    else:
        assert path.read_text(encoding="ascii").splitlines()[0][72] == "S"


@pytest.mark.parametrize("unit", list(UNIT_MM))
@pytest.mark.parametrize("kind", ["step", "iges"])
def test_hole_area_and_physical_units_with_independent_surface_integral(tmp_path, unit, kind):
    """CAD yüz integralinde deliğin dolmadığını ve mm/cm/m/in dönüşümünü doğrular."""
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec
    from OCP.GProp import GProp_GProps
    from OCP.IGESControl import IGESControl_Reader
    from OCP.STEPControl import STEPControl_Reader

    result = source_result("ring")
    scale = 0.02
    path = export_cad(
        result, tmp_path / f"ring-{unit}.{kind}", kind, CadOptions(unit=unit, scale=scale)
    )
    reader = STEPControl_Reader() if kind == "step" else IGESControl_Reader()
    reader.ReadFile(str(path))
    reader.TransferRoots()
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(reader.OneShape(), props)
    expected = (
        math.pi
        * sum(
            (1 if result.reference_boundaries[p.boundary_id].kind == "outer" else -1)
            * p.params["radius"] ** 2
            for p in result.selected.pieces
        )
        * (scale * UNIT_MM[unit]) ** 2
    )
    assert props.Mass() == pytest.approx(expected, rel=1e-8)
    solid = BRepPrimAPI_MakePrism(reader.OneShape(), gp_Vec(0, 0, 5)).Shape()
    assert BRepCheck_Analyzer(solid).IsValid()
    volume = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, volume)
    assert volume.Mass() == pytest.approx(expected * 5, rel=1e-8)


@pytest.mark.parametrize("unit", list(UNIT_MM))
def test_dxf_units_and_native_circle_radius(tmp_path, unit):
    """DXF birim etiketi ile yerel yarıçapın farklı şeyler olduğunu bağımsız okur."""
    import ezdxf

    from sekilden_denkleme.cad_dxf import DXF_UNITS

    result = source_result("circle")
    path = export_cad(
        result, tmp_path / f"circle-{unit}.dxf", "dxf", CadOptions(unit=unit, scale=0.2)
    )
    doc = ezdxf.readfile(path)
    circle = next(iter(doc.modelspace()))
    assert doc.units == DXF_UNITS[unit]
    assert circle.dxf.radius == pytest.approx(
        result.selected.pieces[0].params["radius"] * 0.2, abs=1e-10
    )


def test_trimmed_spline_keeps_finite_domain_and_exact_bernstein_correspondence():
    """DXF'de kırpma dışında kalan spline dalları taşınmaz; alt aralık eşlemesi korunur."""
    from scipy.interpolate import BSpline

    piece = copy.deepcopy(source_result("spline").selected.pieces[0])
    piece.interval = [0.2, 0.8]
    curves = native_curves(piece, 0, CadOptions(scale=0.125))
    assert curves[0].interval[0] == 0.2 and curves[-1].interval[1] == 0.8
    for c in curves:
        q = c.params
        u = np.linspace(0, 1, 101)
        actual = BSpline(q["knots"], q["controls"], 3)(u)
        expected = evaluate(piece, c.interval[0] + u * (c.interval[1] - c.interval[0])) * 0.125
        assert np.allclose(actual, expected, rtol=0, atol=1e-11)


@pytest.mark.parametrize("direction", [-1, 1])
def test_legacy_ellipse_arc_axis_swap_and_direction(tmp_path, direction):
    """Büyük yarı eksen y'deyken dönme/faz düzeltmesini gerçek DXF yayında sınar."""
    from sekilden_denkleme.cad_dxf import read_dxf, write_dxf
    from sekilden_denkleme.cad_geometry import validate_roundtrip
    from sekilden_denkleme.curves import model_rings

    piece = new_piece(
        "ellipse",
        {"center": [500, 500], "radii": [100, 300], "rotation": 0.4, "direction": direction},
        [1.9, 4.7],
        0,
        0,
    )
    line = new_piece("line", {"a": piece.end, "b": piece.start}, [0, 1], 0, 0)
    options = CadOptions(scale=0.1)
    curves = native_curves(piece, 0, options) + native_curves(line, 1, options)
    path = tmp_path / "arc.dxf"
    write_dxf(curves, path, options)
    rings, reader = read_dxf(path, options)
    reference = {i: q * 0.1 for i, q in model_rings([piece, line], 0.0125).items()}
    assert (
        validate_roundtrip(reference, rings, options, reader["max_join_gap"])[
            "transfer_upper_estimate"
        ]
        <= 0.01
    )


def test_atomic_pair_rollback_and_validation_failure_preserve_existing_files(tmp_path, monkeypatch):
    """İkinci dosya kaydı veya yeniden açma başarısızsa eski CAD+JSON çifti korunur."""
    result = source_result("circle")
    target = tmp_path / "circle.dxf"
    sidecar = tmp_path / "circle.dxf.cad.json"
    target.write_bytes(b"old cad")
    sidecar.write_bytes(b"old metadata")
    import os

    original = os.replace

    def fail_metadata(source, destination):
        if Path(source).name == sidecar.name:
            raise OSError("İkinci dosya yazma hatası")
        return original(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr("sekilden_denkleme.cad.os.replace", fail_metadata)
        with pytest.raises(OSError):
            export_cad(result, target, "dxf")
    assert target.read_bytes() == b"old cad" and sidecar.read_bytes() == b"old metadata"

    from sekilden_denkleme.cad_dxf import read_dxf

    def corrupted(path, options):
        rings, reader = read_dxf(path, options)
        rings[0][:, 0] += 1
        return rings, reader

    monkeypatch.setattr("sekilden_denkleme.cad_dxf.read_dxf", corrupted)
    with pytest.raises(ValueError):
        export_cad(result, target, "dxf")
    assert target.read_bytes() == b"old cad" and sidecar.read_bytes() == b"old metadata"
    assert not list(tmp_path.glob(".cad-*"))


@pytest.mark.parametrize("kind", ["dxf", "step", "iges"])
def test_fourier_requires_explicit_approximation_and_records_it(tmp_path, kind):
    """Desteklenmeyen fonksiyonun otomatik poligonlaştırılması sessiz yapılmaz."""
    result = source_result("circle")
    p = result.selected.pieces[0].params
    piece = new_piece(
        "fourier",
        {"center": p["center"], "cos": [[p["radius"], 0]], "sin": [[0, -p["radius"]]]},
        [0, 2 * np.pi],
        0,
        0,
    )
    candidate = Candidate("fourier", "fourier", [piece], accepted=True)
    candidate.complexity = complexity(candidate)
    result = replace(result, candidates=[candidate], selected_id="fourier")
    target = tmp_path / f"fourier.{kind}"
    with pytest.raises(ValueError, match="kontrollü yaklaşımı"):
        export_cad(result, target, kind)
    assert not target.exists()
    export_cad(result, target, kind, CadOptions(scale=0.1, allow_approximation=True))
    meta = json.loads(target.with_name(target.name + ".cad.json").read_text(encoding="utf8"))
    assert meta["approximated_source_pieces"] == [0]


def test_missing_dependency_and_contact_profile_give_clear_errors(tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(
            "sekilden_denkleme.cad.available_formats",
            lambda: {"dxf": False, "step": False, "iges": False},
        )
        with pytest.raises(ValueError, match="kur_cad_windows.cmd"):
            export_cad(source_result("circle"), tmp_path / "none.step", "step")
    from PIL import Image

    array = np.full((1000, 1000), 255, dtype="uint8")
    array[400, 400] = 0
    array[401, 401] = 0
    source = tmp_path / "contact.png"
    Image.fromarray(array).save(source)
    result = analyze(source, AnalysisConfig(padding=0))
    with pytest.raises(ValueError, match="temas"):
        export_cad(result, tmp_path / "contact.dxf", "dxf")
    opened = copy.deepcopy(source_result("rounded"))
    line = next(p for p in opened.selected.pieces if p.kind == "line")
    line.params["b"][0] += 0.001
    line.end = evaluate(line, [line.interval[1]])[0].tolist()
    with pytest.raises(ValueError, match="açık parça"):
        export_cad(opened, tmp_path / "open.dxf", "dxf")


def test_cli_can_export_all_three_cad_formats_without_other_outputs(tmp_path):
    """CLI gerçek analiz ve üç yazıcıyla yalnız istenen dosya çiftlerini üretir."""
    from sekilden_denkleme.cli import main

    code = main(
        [
            str(ROOT / "examples/square.png"),
            "--output",
            str(tmp_path),
            "--formats",
            "dxf",
            "step",
            "iges",
            "--cad-scale",
            "0.1",
        ]
    )
    assert code == 0
    assert {p.name for p in tmp_path.iterdir()} == {
        f"reconstruction.{k}{suffix}"
        for k in ("dxf", "step", "iges")
        for suffix in ("", ".cad.json")
    }


@pytest.mark.parametrize("kind", ["dxf", "step", "iges"])
def test_nested_island_remains_a_separate_component_inside_a_hole(tmp_path, kind):
    """Üç seviyeli gerçek rasterde ada/delik ilişkisi ve yüz alanı birlikte korunur."""
    from PIL import Image, ImageDraw

    image = Image.new("L", (1000, 1000), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 900, 900), fill=0)
    draw.rectangle((250, 250, 750, 750), fill=255)
    draw.rectangle((400, 400, 600, 600), fill=0)
    source = tmp_path / "island.png"
    image.save(source)
    result = analyze(source, AnalysisConfig(padding=0))
    assert result.topology["component_count"] == 2 and result.topology["hole_count"] == 1
    path = export_cad(result, tmp_path / f"island.{kind}", kind, CadOptions(scale=0.1))
    metadata = json.loads(path.with_name(path.name + ".cad.json").read_text(encoding="utf8"))
    assert metadata["transfer_validation"]["boundary_count"] == 3
    assert metadata["topology"] == result.topology
    if kind != "dxf":
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.IGESControl import IGESControl_Reader
        from OCP.STEPControl import STEPControl_Reader

        reader = STEPControl_Reader() if kind == "step" else IGESControl_Reader()
        reader.ReadFile(str(path))
        reader.TransferRoots()
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(reader.OneShape(), props)
        assert props.Mass() == pytest.approx(
            np.count_nonzero(np.array(image) == 0) * 0.1**2, rel=1e-10
        )
