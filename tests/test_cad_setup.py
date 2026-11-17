"""Program dosyası, kullanıcı beyanı ve ürün uyumluluğunu ayıran yerel hazırlık testleri."""

import json
from threading import Event

import pytest

from sekilden_denkleme.cad_setup import (
    ProgramLocation,
    ProgramSettings,
    freecad_command,
    launch_program,
    load_programs,
    readiness,
    save_programs,
    scan_programs,
)
from sekilden_denkleme.fitting import AnalysisCancelled


def test_programs_roundtrip_moved_path_is_not_ready_and_invalid_save_preserves_old(tmp_path):
    """Taşınmış uygulama ve geçersiz ilk açılış kaydı yanlış başarı üretmez."""
    exe = tmp_path / "FreeCAD.exe"
    exe.write_bytes(b"not executable: path fixture only")
    command = tmp_path / "freecadcmd.exe"
    command.write_bytes(b"fixture")
    settings = ProgramSettings()
    settings.programs["FreeCAD"] = ProgramLocation(str(exe), "test-fixture", True)
    path = save_programs(settings, tmp_path / "programs.json")
    assert freecad_command(settings) == str(command)
    command.unlink()
    command = tmp_path / "bin/freecadcmd.exe"
    command.parent.mkdir()
    command.write_bytes(b"fixture")
    assert freecad_command(settings) == str(command)
    loaded = load_programs(path)
    assert loaded == settings
    state = readiness(loaded)["programs"]
    assert state["FreeCAD"]["ready_for_manual_trial"]
    assert not any(p["compatibility_tested"] for p in state.values())
    exe.unlink()
    assert not readiness(load_programs(path))["programs"]["FreeCAD"]["ready_for_manual_trial"]
    original = path.read_bytes()
    loaded.programs["SolidWorks"].first_launch_confirmed = True
    with pytest.raises(ValueError, match="İlk açılış"):
        save_programs(loaded, path)
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "data",
    [
        {},
        [],
        {"schema_version": "99", "programs": {}},
        {
            "schema_version": "1.0",
            "programs": {
                "FreeCAD": {"path": "x", "version": "1", "first_launch_confirmed": "false"}
            },
        },
    ],
)
def test_corrupt_settings_are_rejected(tmp_path, data):
    path = tmp_path / "programs.json"
    path.write_text(json.dumps(data), encoding="utf8")
    with pytest.raises(ValueError):
        load_programs(path)


def test_bounded_discovery_cancellation_and_explicit_launch(tmp_path, monkeypatch):
    """Tarama hiçbir program çalıştırmaz; yalnız açık başlatma eylemi süreç oluşturur."""
    directory = tmp_path / "CAD/AutoCAD/bin"
    directory.mkdir(parents=True)
    exe = directory / "acad.exe"
    exe.write_bytes(b"fixture not executable")
    hidden = tmp_path / "a/b/c/d/e/f"
    hidden.mkdir(parents=True)
    (hidden / "sldworks.exe").write_bytes(b"fixture")
    calls = []
    monkeypatch.setattr(
        "sekilden_denkleme.cad_setup.subprocess.Popen", lambda *a, **k: calls.append((a, k))
    )
    found = scan_programs([tmp_path])
    assert found["AutoCAD"] == [str(exe.resolve())]
    assert not found["SolidWorks"] and not calls
    launch_program("AutoCAD", str(exe))
    assert len(calls) == 1 and calls[0][0][0] == [str(exe.resolve())]
    with pytest.raises(ValueError):
        launch_program("SolidWorks", str(exe))
    cancel = Event()
    cancel.set()
    with pytest.raises(AnalysisCancelled):
        scan_programs([tmp_path], cancel=cancel)
    assert scan_programs([tmp_path], max_directories=1)["AutoCAD"] == []
