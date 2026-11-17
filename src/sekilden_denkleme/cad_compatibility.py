"""Ayrı FreeCAD sürecindeki ürün deneyi ve kaynak CAD eşleme kaydı karşılaştırması."""

import hashlib
import json
import math
import os
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

import numpy as np
from shapely.geometry import Polygon

from .cad_geometry import UNIT_MM, CadOptions, nesting_signature, validate_roundtrip
from .curves import model_rings
from .fitting import AnalysisCancelled
from .models import CurvePiece
from .pilot import _table, atomic_text, html_page, utc_now


def inspect_cad(path: str | Path) -> tuple[dict[str, Any], dict[int, np.ndarray]]:
    """CAD hash'ini ve katsayılarını doğrular; beklenen geometriyi mm'ye çevirir."""
    path = Path(path).resolve()
    if path.suffix.lower() not in {".step", ".iges", ".dxf"} or path.stat().st_size > 150_000_000:
        raise ValueError("En çok 150 MB STEP/IGES/DXF seçin.")
    sidecar = path.with_name(path.name + ".cad.json")
    if sidecar.stat().st_size > 100_000_000:
        raise ValueError("CAD eşleme kaydı 100 MB sınırını aşıyor.")
    try:
        data = json.loads(sidecar.read_text(encoding="utf8"))
        if data["schema_version"] != "1.0" or data["format"] != path.suffix.lower()[1:]:
            raise ValueError("CAD eşleme sürümü/biçimi uyumsuz.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != data["cad_sha256"]:
            raise ValueError("CAD dosyası eşleme hash'iyle uyuşmuyor.")
        options = CadOptions(**data["cad_options"])
        pieces = [CurvePiece(**p) for p in data["selected_model"]["pieces"]]
        if not pieces or len(pieces) > 20000:
            raise ValueError("CAD parça sayısı kaynak sınırını aşıyor.")
        from .project import _validate_piece

        for piece in pieces:
            _validate_piece(piece, len(data["topology"]["rings"]))
        multiplier = options.scale * UNIT_MM[options.unit]
        rings = {
            k: v * multiplier
            for k, v in model_rings(pieces, options.tolerance / (8 * options.scale)).items()
        }
        if sum(len(r) for r in rings.values()) > 250000:
            raise ValueError("CAD referansı 250.000 nokta sınırını aşıyor.")
        nesting_signature(rings)
        return data, rings
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("CAD eşleme kaydı eksik veya bozuk.") from error


def evaluate_product(data: dict, reference: dict[int, np.ndarray], measured: dict) -> dict:
    """Ürün ölçümlerini boyut/topoloji/alan/hacimle karşılaştırır; formal kanıt değildir."""
    tolerance = data["cad_options"]["tolerance"] * UNIT_MM[data["cad_options"]["unit"]]
    parents = nesting_signature(reference)
    depths = {}
    for boundary in range(len(parents)):
        depth, parent = 0, parents[boundary]
        while parent is not None:
            depth += 1
            parent = parents[parent]
        depths[boundary] = depth
    area = sum((-1) ** depths[k] * Polygon(r[:-1, :2]).area for k, r in reference.items())
    perimeter = sum(Polygon(r[:-1, :2]).length for r in reference.values())
    area_allowance = perimeter * tolerance + math.pi * tolerance**2 * len(reference)
    points = np.vstack(list(reference.values()))
    bounds = np.r_[points.min(axis=0), 0.0, points.max(axis=0), 0.0]
    values = np.array(
        [
            *measured["bounding_box_mm"],
            measured["profile_area_mm2"],
            measured["extrusion_volume_mm3"],
        ],
        dtype=float,
    )
    if not np.isfinite(values).all():
        raise ValueError("CAD ürününden sonlu olmayan ölçüm geldi.")
    checks = {
        "dimensions_mm": bool(np.max(np.abs(bounds - values[:6])) <= tolerance),
        "component_count": measured["profile_face_count"] == data["topology"]["component_count"],
        "hole_count": measured["profile_hole_count"] == data["topology"]["hole_count"],
        "closed_profiles": measured["all_wires_closed"] is True,
        "valid_profiles": measured["profile_valid"] is True,
        "area_mm2": abs(measured["profile_area_mm2"] - area) <= area_allowance,
        "extrusion_valid": measured["extrusion_valid"] is True,
        "extrusion_volume_mm3": abs(measured["extrusion_volume_mm3"] - area * 5)
        <= area_allowance * 5,
        "extrusion_solid_count": measured["extrusion_solid_count"]
        == data["topology"]["component_count"],
        "volume_refinement_consistency": measured["volume_refinement_difference_mm3"]
        <= area_allowance * 5,
    }
    try:
        cover = validate_roundtrip(
            reference,
            [np.asarray(r, dtype=float) for r in measured["rings_mm"]],
            CadOptions(unit="mm", tolerance=tolerance),
            measured["max_join_gap_mm"],
        )
        cover["scope"] = (
            "Numerical cover conditional on FreeCAD deflection discretization; not a verified curve bound."
        )
        checks["numerical_curve_comparison"] = True
    except ValueError as error:
        cover = {"status": "failed", "reason": str(error)}
        checks["numerical_curve_comparison"] = False
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "expected_area_mm2_polyline": area,
        "area_allowance_mm2": area_allowance,
        "expected_bounding_box_mm_polyline": bounds.tolist(),
        "tolerance_mm": tolerance,
        "curve_comparison": cover,
        "verified_numerical_certificate": False,
        "independent_application": True,
        "independent_geometry_kernel": False,
        "scope": "FreeCAD headless product import; shared OCCT kernel; no CAD GUI or human pilot measured.",
    }


def run_freecad_check(
    executable: str | Path,
    cad_path: str | Path,
    directory: str | Path,
    *,
    cancel: Event | None = None,
    progress: Callable[[str], None] | None = None,
    timeout: float = 120,
) -> Path:
    """Kullanıcının seçtiği FreeCADCmd'yi yalıtılmış tercihlerle, iptal/süre sınırıyla çalıştırır.

    Yürütülebilir dosya otomatik indirilmez. Başka çalışan CAD süreçlerine dokunmaz.
    Süreç dışındaki ürün başarısızlığı rapora yazılır; tamamlandı bildirimi geçiş değildir.
    """
    executable, cad_path, directory = (
        Path(executable).resolve(),
        Path(cad_path).resolve(),
        Path(directory),
    )
    if not executable.is_file() or "freecadcmd" not in executable.stem.lower():
        raise ValueError("FreeCADCmd yürütülebilir dosyasını seçin.")
    if not math.isfinite(timeout) or not 1 <= timeout <= 600:
        raise ValueError("Ürün deneyi süre sınırı 1–600 saniye olmalıdır.")
    data, reference = inspect_cad(cad_path)
    directory.mkdir(parents=True, exist_ok=True)
    # Kopya çalıştırma dizini kalıcıdır: çökme/günlük/request sonradan incelenebilir.
    run_dir = Path(tempfile.mkdtemp(prefix="freecad-", dir=directory)).resolve()
    request = {
        "cad_path": str(cad_path),
        "cad_sha256": data["cad_sha256"],
        "tolerance_mm": data["cad_options"]["tolerance"] * UNIT_MM[data["cad_options"]["unit"]],
        "document_path": str(run_dir / "inspection.FCStd"),
        "response_path": str(run_dir / "response.json"),
    }
    request_path = atomic_text(run_dir / "request.json", json.dumps(request, ensure_ascii=False))
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(key, None)
    # FreeCAD mevcut olmayan çevre-yolu değerlerini yok sayar; önce oluşturulur.
    for name in ("user", "data", "temp"):
        (run_dir / name).mkdir()
    env.update(
        SD_CAD_CHECK_REQUEST=str(request_path),
        FREECAD_USER_HOME=str(run_dir / "user"),
        FREECAD_USER_DATA=str(run_dir / "data"),
        FREECAD_USER_TEMP=str(run_dir / "temp"),
    )
    worker = Path(__file__).with_name("freecad_worker.py")
    command = [
        str(executable),
        "-u",
        str(run_dir / "user.cfg"),
        "-s",
        str(run_dir / "system.cfg"),
        str(worker),
    ]
    started = time.monotonic()
    if progress:
        progress("FreeCAD gerçek içe alıcısı çalışıyor; geometri ve 5 mm ekstrüzyon denetleniyor…")
    with (run_dir / "process.log").open("wb") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            while process.poll() is None:
                if cancel is not None and cancel.is_set():
                    raise AnalysisCancelled(
                        "FreeCAD deneyi iptal edildi; pilot kayıtları korunuyor."
                    )
                if time.monotonic() - started > timeout:
                    raise TimeoutError("FreeCAD deneyi süre sınırını aştı.")
                time.sleep(0.1)
        except BaseException:
            process.kill()
            process.wait()
            raise
    raw_path = Path(request["response_path"])
    if not raw_path.is_file() or raw_path.stat().st_size > 100_000_000:
        raise ValueError(
            f"FreeCAD sonuç üretemedi (çıkış {process.returncode}). Günlük: {run_dir / 'process.log'}"
        )
    measured = json.loads(raw_path.read_text(encoding="utf8"))
    report = {
        "schema_version": "1.0",
        "recorded_at": utc_now(),
        "kind": "software_compatibility_check",
        "product": "FreeCAD",
        "executable": str(executable),
        "cad_sha256": data["cad_sha256"],
        "cad_file": str(cad_path),
        "format": data["format"],
        "source_application_version": data["application_version"],
        "process_returncode": process.returncode,
        "measured": {k: v for k, v in measured.items() if k != "rings_mm"},
    }
    if measured.get("status") == "measured" and process.returncode == 0:
        report["evaluation"] = evaluate_product(data, reference, measured)
    else:
        report["evaluation"] = {
            "status": "failed",
            "reason": measured.get("reason", "FreeCAD süreç hatası"),
        }
    report_path = atomic_text(
        run_dir / "compatibility.json",
        json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2),
    )
    body = "<p>Bu kayıt ayrı FreeCAD uygulamasının başsız içe alma deneyidir. OCCT çekirdeği ortaktır; insan pilotu veya CAD arayüz testi değildir. DXF için yerel kenarlardan yüz oluşturma adımı ayrıca yazılır. Eğri kopyasının parametre deneyi native sketch geçmişi anlamına gelmez.</p>"
    body += _table(
        ["Denetim", "Sonuç"], [[k, v] for k, v in report["evaluation"].get("checks", {}).items()]
    )
    import html

    body += "<pre>" + html.escape(json.dumps(report, ensure_ascii=False, indent=2)) + "</pre>"
    atomic_text(
        run_dir / "compatibility.html",
        html_page("FreeCAD uyumluluk: " + report["evaluation"]["status"], body),
    )
    return report_path
