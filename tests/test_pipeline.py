"""Normalizasyon, polinom, çıktı sözleşmesi ve kullanıcı hatası testleri."""

import json
import re
import xml.etree.ElementTree as ET

import numpy as np
import pytest
from PIL import Image, ImageDraw

from sekilden_denkleme import AnalysisConfig, analyze
from sekilden_denkleme.cli import main
from sekilden_denkleme.export import equation_report, export_result
from sekilden_denkleme.imaging import normalize_image
from sekilden_denkleme.polynomial import evaluate_polynomial, fit_polynomial


@pytest.mark.parametrize(
    "kwargs",
    [
        {"threshold": -1},
        {"threshold": 255},
        {"padding": 500},
        {"padding": 2.5},
        {"tolerance": float("nan")},
        {"tolerance": -1},
        {"degree": 1},
        {"degree": 13},
        {"max_fit_points": 3},
    ],
)
def test_invalid_settings(kwargs):
    """Geçersiz sayısal ayarların algoritmaya ulaşmasını önler."""
    with pytest.raises(ValueError):
        AnalysisConfig(**kwargs)


def test_rectangle_normalization_and_exact_equations(tmp_path):
    """Eski 1000 birimlik düzlemde oranı, koordinat yönünü ve dört kenarı doğrular."""
    path = tmp_path / "rectangle.png"
    Image.new("L", (200, 100), 0).save(path)
    result = analyze(path, AnalysisConfig(working_size=1000))
    assert result.normalization["canvas_size"] == [1000, 1000]
    assert result.normalization["resized_size"] == [960, 480]
    assert result.normalization["foreground_pixels"] == 960 * 480
    assert set(result.boundaries[0].vertices) == {(20, 260), (980, 260), (980, 740), (20, 740)}
    assert result.metrics["exported_segments"] == 4
    assert result.metrics["exact_normalized_pixel_boundary"]
    report = equation_report(result)
    assert "0≤t≤1" in report
    assert "G(x,y)=" in report
    assert "YAKLAŞIK ÖRTÜK POLİNOM" not in report


def test_native_plane_keeps_source_pixels(tmp_path):
    """Varsayılan ayarda görsel yeniden örneklenmez; bir birim bir kaynak pikselidir."""
    path = tmp_path / "rectangle.png"
    Image.new("L", (200, 100), 0).save(path)
    result = analyze(path)
    assert result.config.working_size == 0
    assert result.normalization["canvas_size"] == [240, 240]
    assert result.normalization["resized_size"] == [200, 100]
    assert result.normalization["scale_x"] == result.normalization["scale_y"] == 1
    assert result.normalization["resampling"] == "none"
    assert result.normalization["foreground_pixels"] == 200 * 100
    assert set(result.boundaries[0].vertices) == {(20, 70), (220, 70), (220, 170), (20, 170)}


def test_native_plane_preserves_thin_features_that_resampling_destroys(tmp_path):
    """Yeniden örnekleme ince çizgileri koparır; yerel düzlem piksel topolojisini korur."""
    from sekilden_denkleme.evaluation import reference_topology
    from sekilden_denkleme.geometry import trace_boundaries

    image = Image.new("L", (3000, 3000), 255)
    for offset in range(0, 2900):
        image.putpixel((50 + offset, 50 + offset), 0)
        image.putpixel((51 + offset, 50 + offset), 0)
    path = tmp_path / "diagonal.png"
    image.save(path)
    native, _ = normalize_image(path, 127, 20)
    legacy, _ = normalize_image(path, 127, 20, 1000)
    assert native.shape == (3040, 3040) and legacy.shape == (1000, 1000)
    assert reference_topology(trace_boundaries(native))["component_count"] == 1
    assert reference_topology(trace_boundaries(legacy))["component_count"] > 1


def test_working_size_is_validated_and_old_projects_default_to_legacy_plane():
    """Düzlem ayarı doğrulanır; mdl kod uzunluğu düzlemin kenarına göre büyür."""
    from sekilden_denkleme.evaluation import mdl_real_bits

    with pytest.raises(ValueError):
        AnalysisConfig(working_size=50)
    with pytest.raises(ValueError):
        AnalysisConfig(working_size=100, padding=60)
    assert mdl_real_bits(1000) == 16
    assert mdl_real_bits(1040) == 17
    assert mdl_real_bits(8192) == 19


def test_transparency_is_white_and_threshold_is_inclusive(tmp_path):
    """Saydam zemin ve eşik sınırındaki gri tonların sınıflandırılmasını doğrular."""
    source = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
    source.putpixel((400, 600), (127, 127, 127, 255))
    source.putpixel((401, 600), (128, 128, 128, 255))
    path = tmp_path / "alpha.png"
    source.save(path)
    mask, _ = normalize_image(path, 127, 0)
    assert mask.sum() == 1
    assert mask[600, 400]
    result = analyze(path, AnalysisConfig(padding=0))
    assert set(result.boundaries[0].vertices) == {(400, 399), (401, 399), (401, 400), (400, 400)}


def test_white_image_and_missing_file_return_actionable_errors(tmp_path, capsys):
    """Boş ve eksik görselde CLI'nin sıfır olmayan çıkış kodunu doğrular."""
    path = tmp_path / "white.png"
    Image.new("L", (20, 20), 255).save(path)
    assert main([str(path)]) == 2
    assert "siyah piksel" in capsys.readouterr().err
    assert main([str(tmp_path / "missing.png")]) == 2


def test_quadratic_circle_has_nonzero_normalized_coefficients():
    """Analitik çemberin ikinci derece polinomunu ve birim katsayı normunu doğrular."""
    t = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    points = np.column_stack((500 + 300 * np.cos(t), 500 + 300 * np.sin(t)))
    fit = fit_polynomial(points, 2)
    assert np.linalg.norm([c for _, _, c in fit.terms]) == pytest.approx(1)
    assert fit.algebraic_rms < 1e-12
    assert fit.gradient_distance_rms < 1e-8
    assert np.max(np.abs(evaluate_polynomial(fit, points[:, 0], points[:, 1]))) < 1e-12
    assert abs(float(evaluate_polynomial(fit, np.array(500), np.array(500)))) > 0.1


def test_square_cannot_be_exact_quadratic():
    """İkinci derecenin genel şekilleri tam temsil ettiği iddiasını engeller."""
    t = np.linspace(200, 800, 200)
    points = np.vstack(
        (
            np.column_stack((t, np.full_like(t, 200))),
            np.column_stack((t, np.full_like(t, 800))),
            np.column_stack((np.full_like(t, 200), t)),
            np.column_stack((np.full_like(t, 800), t)),
        )
    )
    fit = fit_polynomial(points, 2)
    assert fit.algebraic_rms > 0.01


def test_exports_are_parseable_and_pdf_is_a4(tmp_path):
    """Gerçek analizden JSON, vektörel SVG ve A4 sayfa boyutlu PDF üretir."""
    image = Image.new("L", (100, 100), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse((10, 10, 89, 89), fill=0)
    draw.ellipse((35, 35, 64, 64), fill=255)
    path = tmp_path / "ring.png"
    image.save(path)
    result = analyze(
        path, AnalysisConfig(tolerance=8, degree=2, max_fit_points=1000, preference="simple")
    )
    assert result.metrics["hole_count"] == 1
    assert not result.metrics["exact_normalized_pixel_boundary"]
    assert result.metrics["exported_segments"] < result.metrics["original_segments"]
    output = tmp_path / "exports"
    files = export_result(result, output)
    assert len(files) == 6 and all(file.stat().st_size > 100 for file in files)
    model = json.loads((output / "model.json").read_text())
    assert model["schema_version"] == "2.4"
    assert model["polynomial"]["degree"] == 2
    ET.parse(output / "reconstruction.svg")
    media_box = re.search(rb"/MediaBox\s*\[([^\]]+)\]", (output / "a4.pdf").read_bytes())
    dimensions = [float(number) for number in media_box[1].split()]
    assert dimensions[2:] == pytest.approx([595.27559, 841.88976], abs=0.01)
    with Image.open(output / "reconstruction.png") as preview:
        assert preview.width == preview.height


def test_exif_and_coordinate_transform_roundtrip(tmp_path):
    """Ham/yönlü boyutları ve iki yönlü kenar koordinatı dönüşümünü doğrular."""
    image = Image.new("RGB", (120, 60), "black")
    exif = image.getexif()
    exif[274] = 6
    path = tmp_path / "oriented.jpg"
    image.save(path, exif=exif)
    _, metadata = normalize_image(path, 127, 20)
    assert metadata["raw_source_size"] == [120, 60]
    assert metadata["source_size"] == [60, 120]
    assert metadata["exif_orientation"] == 6 and metadata["exif_applied"]
    forward = np.asarray(metadata["source_to_working"])
    backward = np.asarray(metadata["working_to_source"])
    assert np.allclose(forward @ backward, np.eye(3))
    assert np.allclose(backward @ forward @ np.array([32.5, 42.5, 1]), [32.5, 42.5, 1])
