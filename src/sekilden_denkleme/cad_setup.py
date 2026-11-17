"""CAD program yolları ve insan pilotu öncesi hazırlık; kurulum/uyumluluk ispatı değildir."""

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Event
from typing import Any

from .fitting import AnalysisCancelled
from .pilot import atomic_text, utc_now

EXECUTABLES = {"FreeCAD": "freecad.exe", "AutoCAD": "acad.exe", "SolidWorks": "sldworks.exe"}
PREFERRED_FORMATS = {"FreeCAD": "step", "AutoCAD": "dxf", "SolidWorks": "step"}


@dataclass
class ProgramLocation:
    """Operatörün program yolu/sürüm/ilk açılış beyanı; içe alma sonucu taşımaz."""

    path: str = ""
    version: str = ""
    first_launch_confirmed: bool = False


@dataclass
class ProgramSettings:
    """Çalışma klasörüne kaydedilen üç programın ayarları; kod çalıştırmaz."""

    programs: dict[str, ProgramLocation] = field(
        default_factory=lambda: {p: ProgramLocation() for p in EXECUTABLES}
    )

    def validate(self) -> None:
        """Bilinmeyen program/alanı ve yanlış yürütülebilir adını reddeder."""
        if set(self.programs) != set(EXECUTABLES):
            raise ValueError("Program ayarları FreeCAD, AutoCAD ve SolidWorks içermelidir.")
        for product, location in self.programs.items():
            if (
                not isinstance(location, ProgramLocation)
                or not isinstance(location.path, str)
                or len(location.path) > 2000
            ):
                raise ValueError("Program konumu geçersiz.")
            if (
                not isinstance(location.version, str)
                or len(location.version) > 200
                or type(location.first_launch_confirmed) is not bool
            ):
                raise ValueError("Program sürümü/ilk açılış beyanı geçersiz.")
            if location.path and Path(location.path).name.casefold() != EXECUTABLES[product]:
                raise ValueError(f"{product} için {EXECUTABLES[product]} dosyasını seçin.")
            if location.first_launch_confirmed and (
                not location.path or not location.version.strip()
            ):
                raise ValueError(
                    "İlk açılış onayı için program yolu ve gerçek sürümü yazılmalıdır."
                )


def load_programs(path: str | Path) -> ProgramSettings:
    """Taşınmış program yolunu saklar; eksik dosya hazır olarak raporlanmaz."""
    path = Path(path)
    if not path.exists():
        return ProgramSettings()
    if path.stat().st_size > 50000:
        raise ValueError("Program ayarları 50 KB sınırını aşıyor.")
    try:
        data = json.loads(path.read_text(encoding="utf8"))
        if set(data) != {"schema_version", "programs"} or data["schema_version"] != "1.0":
            raise ValueError("Program ayarları şema sürümü desteklenmiyor.")
        if any(
            set(v) != {"path", "version", "first_launch_confirmed"}
            for v in data["programs"].values()
        ):
            raise ValueError("Program ayarlarında eksik/bilinmeyen alan var.")
        settings = ProgramSettings({p: ProgramLocation(**v) for p, v in data["programs"].items()})
        settings.validate()
        return settings
    except (TypeError, KeyError, AttributeError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Geçerli program ayarları JSON'u okunamadı.") from error


def save_programs(settings: ProgramSettings, path: str | Path) -> Path:
    """Ayarları atomik kaydeder; hiçbir program başlatmaz veya kurmaz."""
    settings.validate()
    return atomic_text(
        path,
        json.dumps({"schema_version": "1.0", **asdict(settings)}, ensure_ascii=False, indent=2),
        load_programs,
    )


def default_search_roots(workspace: Path) -> list[Path]:
    """D: kurulum klasörleri, mevcut taşınabilir FreeCAD ve standart C: köklerini seçer."""
    roots = [
        workspace / ".tmp/freecad",
        Path("D:/CAD"),
        Path("D:/Program Files"),
        Path("D:/Programlar"),
        Path("D:/Apps"),
    ]
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        if value := os.environ.get(variable):
            roots.extend(
                Path(value) / name
                for name in ("Autodesk", "SOLIDWORKS Corp", "FreeCAD 1.1", "FreeCAD 1.0")
            )
    if value := os.environ.get("LOCALAPPDATA"):
        roots.append(Path(value) / "Programs")
    return [p for p in roots if p.is_dir()]


def scan_programs(
    roots: list[Path],
    *,
    cancel: Event | None = None,
    progress: Callable[[str], None] | None = None,
    max_directories: int = 1500,
) -> dict[str, list[str]]:
    """Sınırlı derinlikte salt okunur tarar; tüm D: veya ağ yollarını kendiliğinden gezmez.

    En fazla 1500 dizin ve kökten dört alt düzey; sembolik bağlara girilmez.
    Bulunan dosya lisans, ilk açılış veya format uyumluluğu kanıtı sayılmaz.
    """
    if not 1 <= max_directories <= 10000:
        raise ValueError("Tarama dizin sınırı 1–10000 olmalıdır.")
    found: dict[str, list[str]] = {p: [] for p in EXECUTABLES}
    visited = 0
    pending = [(p, 0) for p in roots if p.is_dir()]
    skipped = {
        ".git",
        "node_modules",
        "__pycache__",
        "lib",
        "libs",
        "dlls",
        "help",
        "data",
        "textures",
        "materials",
    }
    while pending and visited < max_directories:
        if cancel is not None and cancel.is_set():
            raise AnalysisCancelled("Program taraması iptal edildi; kayıtlı yollar korunuyor.")
        directory, depth = pending.pop()
        visited += 1
        if progress and visited % 100 == 0:
            progress(f"Program yolları aranıyor: {visited} dizin incelendi.")
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name.casefold())
            matches = False
            for entry in entries:
                for product, filename in EXECUTABLES.items():
                    if entry.name.casefold() == filename and entry.is_file():
                        absolute = str(entry.resolve())
                        if absolute not in found[product]:
                            found[product].append(absolute)
                        matches = True
            if depth < 4 and not matches:
                pending.extend(
                    (p, depth + 1)
                    for p in entries
                    if p.name.casefold() not in skipped and not p.is_symlink() and p.is_dir()
                )
        except OSError:
            continue
    return found


def readiness(settings: ProgramSettings) -> dict[str, Any]:
    """Gerçek dosya varlığı ile operatör onayını ayıran hazırlık raporu üretir."""
    settings.validate()
    products = {}
    for product, location in settings.programs.items():
        exists = bool(location.path and Path(location.path).is_file())
        products[product] = {
            **asdict(location),
            "file_found": exists,
            "ready_for_manual_trial": exists and location.first_launch_confirmed,
            "compatibility_tested": False,
            "next_action": "Kurulum yolunu seçin veya programı kurun."
            if not exists
            else "Programı ilk kez açın; gerçek sürümü ve ilk açılış onayını kaydedin."
            if not location.first_launch_confirmed
            else "Görev kartını seçip gerçek denemeyi yapın.",
        }
    return {
        "schema_version": "1.0",
        "recorded_at": utc_now(),
        "programs": products,
        "scope": "Local file checks and operator declarations; not license validation, CAD compatibility or human pilot results.",
    }


def freecad_command(settings: ProgramSettings) -> str:
    """GUI veya taşınabilir kök başlatıcı yanındaki FreeCADCmd'yi bulur."""
    value = settings.programs["FreeCAD"].path
    if value:
        directory = Path(value).parent
        for candidate in (directory / "freecadcmd.exe", directory / "bin/freecadcmd.exe"):
            if candidate.is_file():
                return str(candidate)
    return ""


def launch_program(product: str, path: str) -> subprocess.Popen:
    """Kullanıcının Programı aç düğmesiyle seçilen GUI'yi görünür başlatır.

    Başlatma içe alma veya lisans başarısı sayılmaz; otomatik belge/makro yüklenmez.
    """
    if (
        product not in EXECUTABLES
        or Path(path).name.casefold() != EXECUTABLES[product]
        or not Path(path).is_file()
    ):
        raise ValueError("Önce ilgili CAD programının geçerli dosya yolunu seçin.")
    return subprocess.Popen([str(Path(path).resolve())], cwd=Path(path).resolve().parent)
