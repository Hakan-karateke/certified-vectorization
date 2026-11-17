"""Gerçek dokuz CAD dosyası, taşınabilir görevler ve başarısız yayımın kabul testleri."""

import json
import shutil
from pathlib import Path
from threading import Event

import pytest

from sekilden_denkleme.cad import available_formats
from sekilden_denkleme.cad_compatibility import inspect_cad
from sekilden_denkleme.fitting import AnalysisCancelled
from sekilden_denkleme.pilot import PilotStudy, summarize
from sekilden_denkleme.pilot_pack import asset_path, build_pack, load_pack, task_instructions

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    """Yerel CAD ekleri yoksa gerçek aktarım testini açıkça atlar."""
    if not all(available_formats().values()):
        pytest.skip("STEP/IGES/DXF CAD ekleri kurulu değil.")
    directory = tmp_path_factory.mktemp("pilot-pack")
    return build_pack(ROOT / "examples/cad_product_validation", directory)


def test_pack_real_formats_shared_targets_and_plans_are_not_observations(pack):
    """Örnekler dosyadan yeniden açılır; her çiftin hedef/süre/kalite eşiği aynıdır."""
    plan = load_pack(pack)
    assert plan["observation_count"] == 0 and len(plan["tasks"]) == 54
    assert sum(t["task"] == "import" for t in plan["tasks"]) == 18
    assert len(plan["assets"]) == 34
    assert plan["cases"]["ring"]["hole_count"] == 1
    assert plan["cases"]["mixed"]["edit_target"]["kind"] == "control_point"
    assert summarize(PilotStudy())["human_participants"] == 0
    for case in plan["cases"].values():
        assert case["physical_error_summary"]["combined_verified_numerical_certificate"] is False
        for kind, relative in case["cad"].items():
            path = asset_path(pack, relative)
            data, _ = inspect_cad(path)
            assert data["format"] == kind
            assert path.stat().st_size > 100
            validation = data["transfer_validation"]
            assert validation["transfer_upper_estimate"] <= validation["tolerance"]
            assert validation["polygon_nesting_preserved"]
    for a, b in zip(plan["tasks"][::2], plan["tasks"][1::2], strict=True):
        assert a["case_id"] == b["case_id"] and a["product"] == b["product"]
        assert a["task"] == b["task"] and a["method"] != b["method"]
        assert a["target_tolerance_mm"] == b["target_tolerance_mm"]
        assert a["time_limit_seconds"] == b["time_limit_seconds"]
        assert "Hazırlama süresi" in task_instructions(plan, plan["tasks"][0])


def test_moved_pack_opens_and_changed_assets_or_tasks_rejected(pack, tmp_path):
    """Paket tek klasörle taşınır; değişmiş hedef ve yol taşması sessizce açılmaz."""
    moved = tmp_path / "moved"
    shutil.copytree(pack.parent, moved)
    path = moved / "plan.json"
    assert load_pack(path)["cases"]["circle"]["component_count"] == 1
    raw = path.read_bytes()
    data = json.loads(raw)
    data["tasks"][0]["target_tolerance_mm"] = 99
    path.write_text(json.dumps(data), encoding="utf8")
    with pytest.raises(ValueError, match="Görev sırası"):
        load_pack(path)
    path.write_bytes(raw)
    data = json.loads(raw)
    data["cases"]["ring"]["hole_count"] = 0
    path.write_text(json.dumps(data), encoding="utf8")
    with pytest.raises(ValueError, match="Görev hedefi"):
        load_pack(path)
    path.write_bytes(raw)
    (moved / "circle/reconstruction.dxf").write_bytes(b"changed")
    with pytest.raises(ValueError, match="değişmiş"):
        load_pack(path)
    for relative in ["../plan.json", str(pack.resolve()), "C:/outside.exe", "circle\\model.json"]:
        with pytest.raises(ValueError):
            asset_path(path, relative)


def test_cancelled_or_failed_pack_never_publishes_partial_or_overwrites_old(tmp_path, monkeypatch):
    """İptal ve çekirdek hata çıktıları yalnız geçici klasörde kalır."""
    source = ROOT / "examples/cad_product_validation"
    sentinel = tmp_path / "previous/keep.txt"
    sentinel.parent.mkdir()
    sentinel.write_text("keep", encoding="utf8")
    cancel = Event()
    cancel.set()
    with pytest.raises(AnalysisCancelled):
        build_pack(source, tmp_path, cancel=cancel)

    def failed_export(*a, **k):
        raise RuntimeError("injected CAD kernel failure")

    monkeypatch.setattr("sekilden_denkleme.pilot_pack.export_cad", failed_export)
    with pytest.raises(RuntimeError, match="kernel failure"):
        build_pack(source, tmp_path)
    assert list(tmp_path.iterdir()) == [sentinel.parent]
    assert sentinel.read_text(encoding="utf8") == "keep"
