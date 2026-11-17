"""Tarama süreci, veri bütünlüğü, devam ettirme ve iptal sözleşmesi."""

import hashlib
import json
from threading import Event

import pytest
from PIL import Image

from sekilden_denkleme.fitting import AnalysisCancelled
from sekilden_denkleme.stress import run_grid


def dataset(tmp_path):
    """Tek analitik kare rasteriyle hash doğrulamalı küçük manifest üretir."""
    path = tmp_path / "square.png"
    Image.new("L", (100, 100), 0).save(path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "id": "square",
                        "source": "test",
                        "png_path": "square.png",
                        "sha256_png": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                ]
            }
        ),
        encoding="utf8",
    )
    return manifest


def test_real_isolated_worker_and_resume_without_refit(tmp_path, monkeypatch):
    """Çocuk Python'da gerçek analizi ölçer; aynı tarama tekrar süreç başlatmaz."""
    manifest = dataset(tmp_path)
    output = tmp_path / "results"
    result = run_grid(manifest, output, tolerances=(2,), workers=1, timeout=60)
    data = json.loads(result.read_text(encoding="utf8"))
    assert data["completed_count"] == 1 and data["status_counts"] == {"ok": 1}
    row = data["records"][0]
    assert row["strict_selected"]["metrics"]["certification"]["status"] == "proven"
    assert row["selected"]["complexity"]["piece_count"] == 4
    monkeypatch.setattr(
        "sekilden_denkleme.stress.subprocess.Popen", lambda *a, **k: pytest.fail("Yeniden analiz")
    )
    run_grid(manifest, output, tolerances=(2,), workers=1, timeout=60)
    with pytest.raises(ValueError, match="parmak izi"):
        run_grid(manifest, output, tolerances=(3,), workers=1, timeout=60)


def test_input_tampering_and_cancellation(tmp_path):
    """Değişmiş girdi reddedilir; iptal tamamlanmış gibi bildirilmez."""
    manifest = dataset(tmp_path)
    cancel = Event()
    cancel.set()
    with pytest.raises(AnalysisCancelled):
        run_grid(manifest, tmp_path / "cancel", tolerances=(2,), workers=1, cancel=cancel)
    (tmp_path / "square.png").write_bytes(b"bad")
    with pytest.raises(ValueError, match="SHA-256"):
        run_grid(manifest, tmp_path / "bad", tolerances=(2,))
    data = json.loads(manifest.read_text(encoding="utf8"))
    data["assets"][0]["id"] = "../escape"
    manifest.write_text(json.dumps(data), encoding="utf8")
    with pytest.raises(ValueError, match="girdi kimliği"):
        run_grid(manifest, tmp_path / "escape", tolerances=(2,))


def test_timeout_is_recorded_without_fabricated_measurements(tmp_path):
    """Başlatma dahil süre sınırı aşılmışsa ölçüm alanları uydurulmaz."""
    manifest = dataset(tmp_path)
    result = run_grid(manifest, tmp_path / "timeout", tolerances=(2,), workers=1, timeout=0.001)
    row = json.loads(result.read_text(encoding="utf8"))["records"][0]
    assert row["status"] == "timeout" and "selected" not in row
