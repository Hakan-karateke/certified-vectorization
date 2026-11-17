"""Kaynak taşınması, bozuk proje, gerçek biçim ve çok sayfalı PDF kabul testleri."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import jsonschema
import numpy as np
import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader

from sekilden_denkleme import AnalysisConfig, analyze
from sekilden_denkleme.curves import evaluate
from sekilden_denkleme.export import ExportOptions, export_file, make_figure
from sekilden_denkleme.project import choose_candidate, load_project, result_from_dict, save_project


def square_result(tmp_path):
    """Dört sonlu kenarı olan tekrar kullanılabilir gerçek analiz üretir."""
    path = tmp_path / "square.png"
    Image.new("L", (100, 100), 0).save(path)
    return path, analyze(path)


def test_project_roundtrip_with_moved_source_and_without_refitting(tmp_path, monkeypatch):
    """Kaynak silinse ve uydurma yasaklansa bile kayıtlı model yeniden çizilir."""
    source, result = square_result(tmp_path)
    target = save_project(result, tmp_path / "project.json")
    source.unlink()
    monkeypatch.setattr(
        "sekilden_denkleme.pipeline.fit_models", lambda *_: pytest.fail("Yeniden uydurma")
    )
    loaded = load_project(target)
    assert loaded.selected_id == result.selected_id
    assert loaded.provenance["load_warnings"]
    for a, b in zip(result.selected.pieces, loaded.selected.pieces, strict=True):
        assert a.params == b.params and a.interval == b.interval
        assert np.array_equal(
            evaluate(a, np.linspace(*a.interval, 9)), evaluate(b, np.linspace(*b.interval, 9))
        )
    fig = make_figure(loaded)
    assert fig.axes[0].lines
    fig.clear()
    export_file(loaded, tmp_path / "loaded.svg", "svg")


def test_published_json_schema_accepts_real_project_and_rejects_wrong_geometry(tmp_path):
    """Bağımsız Draft 2020-12 doğrulayıcısıyla yayımlanan şemayı gerçek veriyle sınar."""
    _, result = square_result(tmp_path)
    schema = json.loads(
        (Path(__file__).parents[1] / "docs" / "project.schema.json").read_text(encoding="utf-8")
    )
    validator = jsonschema.Draft202012Validator(schema)
    validator.check_schema(schema)
    validator.validate(json.loads(json.dumps(result.to_dict())))
    bad = result.to_dict()
    bad["candidates"][0]["pieces"][0]["params"]["a"] = [0, 1, 2]
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad)


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "endpoint",
        "zero_radius",
        "zero_polynomial",
        "nan",
        "topology",
        "false_exact",
        "root",
    ],
)
def test_corrupt_projects_are_rejected(tmp_path, mutation):
    """Yanlış sürüm/parametre/kanıt bayraklarının sessizce kullanılmasını engeller."""
    _, result = square_result(tmp_path)
    data = result.to_dict()
    if mutation == "version":
        data["schema_version"] = "99.0"
    elif mutation == "endpoint":
        data["candidates"][0]["pieces"][0]["end"][0] += 1
    elif mutation == "zero_radius":
        piece = data["candidates"][0]["pieces"][0]
        piece["kind"] = "circle"
        piece["params"] = {"center": [0, 0], "radius": 0}
    elif mutation == "nan":
        data["config"]["tolerance"] = float("nan")
    elif mutation == "zero_polynomial":
        data["polynomial"] = {
            "degree": 2,
            "terms": [[0, 0, 0]],
            "algebraic_rms": 0,
            "gradient_distance_rms": None,
            "sample_count": 100,
            "condition_number": None,
            "diagnostics": {},
        }
    elif mutation == "topology":
        data["topology"]["hole_count"] = 4
    elif mutation == "root":
        data = []
    else:
        for p in data["candidates"][0]["pieces"]:
            for key in ("a", "b"):
                p["params"][key][0] += 10
            p["start"][0] += 10
            p["end"][0] += 10
    with pytest.raises(ValueError):
        result_from_dict(data)


def test_true_raster_formats_size_dpi_and_alpha(tmp_path):
    """PNG saydamlığı, JPEG opaklığı ve çıktı boyut/DPI seçeneklerini açarak sınar."""
    _, result = square_result(tmp_path)
    options = ExportOptions(
        pixel_size=640, dpi=200, transparent=True, annotated=False, background="#f4f6fa", quality=87
    )
    for kind in ("png", "jpeg"):
        file = export_file(result, tmp_path / f"shape.{kind}", kind, options)
        with Image.open(file) as im:
            assert im.size == (640, 640)
            assert im.info["dpi"][0] == pytest.approx(200, abs=0.02)
            if kind == "png":
                assert im.getpixel((0, 0))[3] == 0
            else:
                assert (
                    im.mode == "RGB"
                    and np.max(np.abs(np.array(im.getpixel((0, 0))) - [244, 246, 250])) <= 3
                )


@pytest.mark.parametrize("family", ["circle", "ellipse", "bezier", "bspline"])
def test_curved_models_roundtrip_without_source_refit(tmp_path, family):
    """Eğri katsayıları, düğümler ve aralıklar kaynak taşınsa da aynı modeli üretir."""
    source = tmp_path / "curve.png"
    image = Image.new("L", (1000, 1000), 255)
    ImageDraw.Draw(image).ellipse((200, 200, 799, 799), fill=0)
    image.save(source)
    result = analyze(source, AnalysisConfig(padding=0, tolerance=3, family=family))
    candidate = next(c for c in result.candidates if c.family == family and c.accepted)
    result = choose_candidate(result, candidate.id)
    project = save_project(result, tmp_path / "curve.json")
    source.unlink()
    loaded = load_project(project)
    for p, q in zip(result.selected.pieces, loaded.selected.pieces, strict=True):
        assert p.params == q.params and p.interval == q.interval
        t = np.linspace(*p.interval, 101)
        assert np.array_equal(evaluate(p, t), evaluate(q, t))


def test_svg_has_native_cubic_and_circle_geometry(tmp_path):
    """SVG'ye raster yerleştirilmez; katsayılar yerel C ve circle elemanı olur."""
    source = tmp_path / "circle.png"
    image = Image.new("L", (1000, 1000), 255)
    ImageDraw.Draw(image).ellipse((200, 200, 799, 799), fill=0)
    image.save(source)
    result = analyze(source, AnalysisConfig(padding=0, tolerance=3, family="circle"))
    svg = export_file(result, tmp_path / "circle.svg", "svg")
    root = ET.parse(svg).getroot()
    ns = {"s": "http://www.w3.org/2000/svg"}
    element = root.find(".//s:circle", ns)
    assert element is not None
    assert float(element.attrib["r"]) == result.selected.pieces[0].params["radius"]
    assert root.find(".//s:image", ns) is None
    assert root.find("s:g", ns).attrib["transform"] == "translate(0 1000) scale(1 -1)"
    # Aynı kayıttaki kabul edilmiş Bézier adayı farklı analizde de yerel kalır.
    result = analyze(
        source, AnalysisConfig(padding=0, tolerance=3, family="bezier", preference="simple")
    )
    assert any(p.kind == "bezier" for p in result.selected.pieces)
    root = ET.parse(export_file(result, tmp_path / "bezier.svg", "svg")).getroot()
    paths = root.findall(".//s:g/s:path", ns)
    assert len(paths) == len(result.selected.pieces)
    assert all(" C " in p.attrib["d"] for p in paths)


def test_long_pdf_contains_last_equation_and_all_pages_are_a4(tmp_path):
    """Uzun denklem listesi son parçaya kadar sayfalanır ve gerçek PDF açılır."""
    source = tmp_path / "polygon.png"
    image = Image.new("L", (1000, 1000), 255)
    draw = ImageDraw.Draw(image)
    t = np.linspace(0, 2 * np.pi, 40, endpoint=False)
    radius = np.where(np.arange(40) % 2 == 0, 300, 200)
    draw.polygon(
        np.column_stack([500 + radius * np.cos(t), 500 + radius * np.sin(t)]).tolist(), fill=0
    )
    image.save(source)
    result = analyze(source, AnalysisConfig(padding=0, tolerance=3, family="polygon"))
    pdf = export_file(result, tmp_path / "long.pdf", "pdf", ExportOptions(orientation="landscape"))
    reader = PdfReader(pdf)
    assert len(reader.pages) > 3
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert f"Parça {len(result.selected.pieces)} |" in text
    assert "YENİDEN ÜRETİM" in text
    for i, page in enumerate(reader.pages, 1):
        assert float(page.mediabox.width) == pytest.approx(841.88976, abs=0.01)
        assert f"Sayfa {i}" in page.extract_text()


def test_failed_export_preserves_existing_target(tmp_path, monkeypatch):
    """Geçersiz üretilmiş dosya hedefe taşınmaz ve başarı bildirilmez."""
    _, result = square_result(tmp_path)
    path = tmp_path / "shape.svg"
    path.write_text("existing", encoding="utf-8")

    def broken(*args):
        args[-1].write_text("broken", encoding="utf-8")

    monkeypatch.setattr("sekilden_denkleme.export._svg", broken)
    with pytest.raises(ET.ParseError):
        export_file(result, path, "svg")
    assert path.read_text() == "existing"
    assert not list(tmp_path.glob(".export-*"))
