"""Rasyonel konik yaylarda bağımsız kimlik, geometri ve sertifika sınamaları."""

import copy
from fractions import Fraction as Q
from math import comb
from pathlib import Path

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString

from sekilden_denkleme import AnalysisConfig, analyze
from sekilden_denkleme.certification import _verified_leaves, certify
from sekilden_denkleme.curves import equation, evaluate, flatten, new_piece, tangent
from sekilden_denkleme.evaluation import complexity
from sekilden_denkleme.models import Boundary, Candidate
from sekilden_denkleme.project import load_project, save_project
from sekilden_denkleme.rational_arcs import homogeneous_controls


def arc(kind="circle"):
    """Dyadik katsayılı, üst yarı düzlemde saat yönlü bir konik yay kurar."""
    params = (
        {"a": [100, 100], "b": [900, 100], "bulge": -0.5}
        if kind == "circle"
        else {"controls": [[100, 100], [500, 900], [900, 100]], "weight": 0.5}
    )
    return new_piece(kind, {"arc": params}, [2, 5], 0, 0)


@pytest.mark.parametrize("bulge", [-0.85, -0.5, 0.125, 0.75])
def test_circle_identity_is_exact_at_rational_parameters(bulge):
    """Değerlendirme kodundan bağımsız tam rasyonel çember kimliği doğrular."""
    p = new_piece("circle", {"arc": {"a": [30, 80], "b": [350, 240], "bulge": bulge}}, [0, 1], 0, 0)
    h = homogeneous_controls(p)
    a, b = h[0][:2], h[2][:2]
    s = Q(bulge)
    j = (a[1] - b[1], b[0] - a[0])
    center = tuple((a[k] + b[k]) / 2 + (1 - s * s) / (4 * s) * j[k] for k in (0, 1))
    r2 = sum((a[k] - center[k]) ** 2 for k in (0, 1))
    for u in [Q(0), Q(1, 17), Q(2, 3), Q(1)]:
        v = [
            sum(comb(2, i) * (1 - u) ** (2 - i) * u**i * h[i][k] for i in range(3))
            for k in range(3)
        ]
        assert sum((v[k] / v[2] - center[k]) ** 2 for k in (0, 1)) == r2
    reverse = new_piece(
        "circle", {"arc": {"a": list(b), "b": list(a), "bulge": -bulge}}, [0, 1], 0, 0
    )
    assert np.allclose(
        evaluate(p, np.linspace(0, 1, 101)), evaluate(reverse, np.linspace(1, 0, 101)), atol=1e-12
    )


@pytest.mark.parametrize("kind", ["circle", "ellipse"])
def test_entire_arc_enclosed_by_verified_flattening(kind):
    """30.001 gerçek eğri noktasını bağımsız GEOS uzaklığıyla ölçer; uç/türev sınar."""
    p = arc(kind)
    dense = evaluate(p, np.linspace(2, 5, 30001))
    assert np.array_equal(dense[[0, -1]], [p.start, p.end])
    quick = flatten(p, 0.025)
    leaves, upper = _verified_leaves(p, 0.025)
    verified = np.asarray([*[c[0] for c in leaves], leaves[-1][-1]], dtype=float)
    for polygon, limit in [(quick, 0.025), (verified, upper)]:
        assert shapely.distance(shapely.points(dense), LineString(polygon)).max() <= limit
    assert upper <= 0.025
    assert np.allclose(
        tangent(p), (evaluate(p, [2 + 1e-7])[0] - dense[0]) / 1e-7, rtol=1e-6, atol=1e-4
    )
    assert "u=(t-a)/(b-a)" in equation(p)
    assert complexity(Candidate("arc", "mixed", [p]))["score_bits"] == (
        488 if kind == "circle" else 616
    )
    with pytest.raises(ValueError, match="aralığının"):
        evaluate(p, [6])


@pytest.mark.parametrize("kind", ["circle", "ellipse"])
def test_closed_mixed_arc_certificate_and_exact_join_rejection(kind):
    """Yay/doğru halkasını kanıtlar; en küçük gerçek uç açıklığını gizlemez."""
    p = arc(kind)
    line = new_piece("line", {"a": p.end, "b": p.start}, [0, 1], 0, 0)
    ref = Boundary(flatten(p, 0.005)[:-1].tolist() + [p.end], "outer", 100)
    c = Candidate("mixed", "mixed", [p, line])
    proof = certify(c, [ref], 1)
    assert proof["status"] == "proven", proof
    assert proof["hausdorff_upper_bound"] <= 1
    assert proof["analytic_isotopy_proven"]
    c = copy.deepcopy(c)
    c.pieces[1].params["a"][0] = float(np.nextafter(900.0, 901))
    proof = certify(c, [ref], 1)
    assert proof["status"] == "undetermined"
    assert any("C0" in r for r in proof["reasons"])
    crossed = new_piece("line", {"a": [900, 100], "b": [100, 100]}, [0, 1], 0, 0)
    # İki karşı yönlü aynı yay üst üste biner: kapalı olması Jordan olmasına yetmez.
    reverse = new_piece("circle", {"arc": {"a": p.end, "b": p.start, "bulge": 0.5}}, [0, 1], 0, 0)
    if kind == "circle":
        assert (
            certify(Candidate("overlap", "mixed", [p, reverse]), [ref], 300)["status"]
            == "undetermined"
        )
    assert crossed.start == p.end


@pytest.mark.parametrize(
    "kind,params",
    [
        ("circle", {"a": [0, 0], "b": [1, 1], "bulge": 1}),
        ("circle", {"a": [0, 0], "b": [1, 1], "bulge": 0}),
        ("ellipse", {"controls": [[0, 0], [1, 2], [3, 0]], "weight": -1}),
        ("ellipse", {"controls": [[0, 0], [1, 0], [3, 0]], "weight": 0.5}),
    ],
)
def test_degenerate_or_nonpositive_weight_arcs_rejected(kind, params):
    """Payda kutbu ve dejenere konik sessizce çizilmez/kanıtlanmaz."""
    with pytest.raises(ValueError):
        new_piece(kind, {"arc": params}, [0, 1], 0, 0)


def test_mixed_raster_roundtrip_schema_and_svg(tmp_path, monkeypatch):
    """Karma aile gerçek rasterden açılır; parametreler kaynak/uydurmadan bağımsızdır."""
    import json
    import xml.etree.ElementTree as ET

    import jsonschema

    from sekilden_denkleme.export import ExportOptions, export_file

    source = Path(__file__).parents[1] / "examples/validation/dataset/circle.png"
    result = analyze(
        source,
        AnalysisConfig(
            family="mixed", tolerance=3, padding=0, certificate_mode="strict", preference="simple"
        ),
    )
    assert any("arc" in p.params for p in result.selected.pieces), result.selected_id
    assert result.selected.metrics["certification"]["status"] == "proven"
    assert result.provenance["algorithm_settings"]["certificate_version"] == "1.3"
    schema = json.loads(
        (Path(__file__).parents[1] / "docs/project.schema.json").read_text(encoding="utf8")
    )
    jsonschema.Draft202012Validator(schema).validate(json.loads(json.dumps(result.to_dict())))
    saved = save_project(result, tmp_path / "model.json")
    monkeypatch.setattr(
        "sekilden_denkleme.fitting.circle_arc", lambda *a: pytest.fail("Yeniden uydurma")
    )
    loaded = load_project(saved)
    assert loaded.selected.pieces == result.selected.pieces
    svg = export_file(loaded, tmp_path / "model.svg", "svg", ExportOptions(annotated=False))
    tree = ET.parse(svg)
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert not tree.findall(".//s:image", ns)
    polylines = tree.findall(".//s:polyline", ns)
    assert polylines
    for line in polylines:
        p = loaded.selected.pieces[int(line.attrib["data-piece"])]
        q = np.array([[float(x) for x in row.split(",")] for row in line.attrib["points"].split()])
        dense = evaluate(p, np.linspace(*p.interval, 10001))
        metadata = json.loads(tree.find("s:metadata", ns).text)
        assert (
            shapely.distance(shapely.points(dense), LineString(q)).max()
            <= metadata["rational_arc_polyline_tolerance"]
        )


@pytest.mark.parametrize("interval", [[0, 0], [1, 0], [0, float("inf")]])
def test_invalid_parameter_domain_is_never_certified(interval):
    """Nokta kümesi kapansa bile tanımsız/ters/sonsuz parametre aralığı reddedilir."""
    p = arc()
    line = new_piece("line", {"a": p.end, "b": p.start}, [0, 1], 0, 0)
    ref = Boundary(flatten(p, 0.005)[:-1].tolist() + [p.end], "outer", 100)
    p.interval = interval
    proof = certify(Candidate("invalid", "mixed", [p, line]), [ref], 1)
    assert proof["status"] == "undetermined"


def test_rational_arc_cached_endpoint_cannot_drift_by_one_ulp():
    """Yeniden çizimde kullanılan uç önbelleği asıl katsayılarla tam eşleşir."""
    from sekilden_denkleme.project import _validate_piece

    p = arc()
    p.end[0] = float(np.nextafter(p.end[0], 1000))
    with pytest.raises(ValueError, match="tam eşleş"):
        _validate_piece(p, 1)
