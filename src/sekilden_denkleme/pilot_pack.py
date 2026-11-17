"""Üç CAD ürünü için taşınabilir görev planı; planlar gözlem veya başarı kaydı değildir."""

import hashlib
import html
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

import numpy as np
from PIL import Image

from .cad import export_cad
from .cad_compatibility import inspect_cad
from .cad_geometry import CadOptions
from .cad_setup import PREFERRED_FORMATS
from .export import ExportOptions, export_file
from .fitting import AnalysisCancelled
from .pilot import METHODS, TASKS, html_page, utc_now
from .project import load_project, save_project, source_image

CASES = {"circle": "Çember", "ring": "Delikli halka", "mixed": "Köşe ve eğri birleşimi"}
TASK_FIELDS = {
    "id",
    "product",
    "case",
    "case_id",
    "task",
    "method",
    "format",
    "repeat",
    "order",
    "target_tolerance_mm",
    "time_limit_seconds",
}
PLAN_FIELDS = {
    "schema_version",
    "kind",
    "created_at",
    "application_version",
    "observation_count",
    "cases",
    "tasks",
    "assets",
    "scope",
}
CASE_FIELDS = {
    "label",
    "case_id",
    "project",
    "parameters",
    "source_png",
    "model_png",
    "equations",
    "cad",
    "component_count",
    "hole_count",
    "bounding_min_mm",
    "bounding_max_mm",
    "bounding_scope",
    "edit_target",
    "physical_error_summary",
}


def _check_cancel(cancel: Event | None) -> None:
    """Tamamlanmış paketi yayımlamadan önce iptal isteğini denetler."""
    if cancel is not None and cancel.is_set():
        raise AnalysisCancelled("Görev paketi iptal edildi; önceki paketler korunuyor.")


def _digest(path: Path) -> str:
    """Dosya baytlarını sınırlı bellekle SHA-256 olarak özetler."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def asset_path(plan_path: str | Path, relative: str) -> Path:
    """Paket dışına çıkan mutlak, üst dizinli veya sembolik bağlı yolu reddeder."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("Görev dosyası yolu geçersiz.")
    value = Path(relative)
    root = Path(plan_path).resolve().parent
    if value.is_absolute() or value.drive or ".." in value.parts:
        raise ValueError("Görev dosyası paket klasörünün dışında olamaz.")
    path = (root / value).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Görev dosyası bulunamadı veya paket dışında: {relative}")
    return path


def planned_tasks(cases: dict[str, Any]) -> list[dict[str, Any]]:
    """18 içe alma + 36 izleyen görevi üretir; katılımcı, süre veya sonuç atamaz.

    Yöntem sırası çiftler arasında değiştirilir. Bu küçük sabit sıra bir nüfus
    randomizasyonu değildir; tekrar/katılımcı ataması operatörün sorumluluğundadır.
    """
    tasks = []
    for task in TASKS:
        for product_index, (product, kind) in enumerate(PREFERRED_FORMATS.items()):
            for case_index, (key, case) in enumerate(cases.items()):
                methods = ["generated", "baseline"]
                if (product_index + case_index + list(TASKS).index(task)) % 2:
                    methods.reverse()
                for method in methods:
                    tasks.append(
                        {
                            "id": f"{task}-{product}-{key}-{method}",
                            "product": product,
                            "case": key,
                            "case_id": case["case_id"],
                            "task": task,
                            "method": method,
                            "format": kind,
                            "repeat": "1",
                            "order": len(tasks) + 1,
                            "target_tolerance_mm": 0.1,
                            "time_limit_seconds": 600.0,
                        }
                    )
    return tasks


def _edit_target(curves: list[dict[str, Any]]) -> dict[str, Any]:
    """İki yöntemde de uygulanacak tek ve sayısal düzenleme hedefini seçer."""
    circle = next(((i, c) for i, c in enumerate(curves) if c["kind"] == "circle"), None)
    if circle:
        index, curve = circle
        radius = curve["params"]["radius"]
        return {
            "kind": "radius",
            "native_curve_index": index,
            "source_piece": curve["source_piece"],
            "old_radius_mm": radius,
            "new_radius_mm": radius * 1.1,
            "instruction": f"Yerel eğri {index}: merkez sabitken yarıçapı {radius:.9g} mm → {radius * 1.1:.9g} mm yapın; diğer eğrileri koruyun.",
        }
    spline = next(
        (
            (i, c)
            for i, c in enumerate(curves)
            if c["kind"] == "bspline" and len(c["params"]["controls"]) >= 3
        ),
        None,
    )
    if spline:
        index, curve = spline
        point = curve["params"]["controls"][1]
        target = [point[0] + 0.1, point[1]]
        return {
            "kind": "control_point",
            "native_curve_index": index,
            "source_piece": curve["source_piece"],
            "control_index": 1,
            "old_point_mm": point,
            "new_point_mm": target,
            "instruction": f"Yerel spline {index}, sıfırdan sayılan kontrol 1: {point} mm → {target} mm; diğer kontrol/düğüm/ağırlıkları koruyun. İçe alıcı yeniden parametrize ederse aynı katsayılarla spline kurma işini düzeltme sayın.",
        }
    raise ValueError("Örnekte tanımlı çember/spline düzenleme hedefi yok.")


def task_instructions(plan: dict[str, Any], task: dict[str, Any]) -> str:
    """CAD aktarım hedefini ideal raster nesne doğruluğundan ayıran görev kartı verir."""
    case = plan["cases"][task["case"]]
    prefix = (
        f"{case['label']} · {task['product']} · {TASKS[task['task']]} · {METHODS[task['method']]}\n"
    )
    common = (
        f"Hedef: mm, {case['component_count']} bileşen, {case['hole_count']} delik; kalite toleransı ±0.1 mm, etkin süre sınırı 600 s.\n"
        "Fiziksel hedef, kayıtlı matematiksel modeldir; kaynak raster yalnızca görsel referanstır. Ölçek 0.1 mm/çalışma birimi kullanıcı atamasıdır.\n"
    )
    if task["task"] == "import":
        instruction = (
            "Her iki yöntemde de dosya önceden hazırlanmış olmalı. Dosya seçimini başlatmadan sayacı başlatın; doğru ölçekte geometri görününce durdurun. "
            "Üretilen CAD için paketteki dosyayı, mevcut yöntem için kendi iş akışınızda aynı hedefe göre hazırladığınız dosyayı kullanın. Hazırlama süresi bu aktarım deneyine dahil değildir; toplam iş akışı hızlanması çıkarılamaz."
        )
    elif task["task"] == "profile":
        instruction = "Yeni, düzenlenmemiş içe alınmış geometriden başlayın. Sayacı profil oluşturma öncesinde başlatın; +Z yönünde 5 mm ekstrüzyon tamamlandığında durdurun. Delikleri koruyun. Birleştirme/onarma ve sketch hazırlığını düzeltme olarak sayın."
    else:
        instruction = (
            "Yeni, düzenlenmemiş içe alınmış geometriden başlayın. Sayacı düzenleme öncesinde başlatın, hedefi doğrulayınca durdurun. "
            + case["edit_target"]["instruction"]
        )
    return (
        prefix
        + common
        + instruction
        + "\nÖlçüleri CAD içinde doğrulayın; bilinmeyen kalite kutularını başarıya çevirmeyin. Çıktı dosyasını kanıt olarak kaydedin."
    )


def _guide(plan: dict[str, Any]) -> str:
    """Görevleri ve hedef katsayılarını bağlantılı, çevrimdışı HTML kılavuzunda sunar."""
    parts = [
        "<p>Bu dosya bir görev planıdır. Gerçek kullanıcı veya AutoCAD/SolidWorks sonucu içermez. İlk aşama 18 içe alma görevidir; profil ve düzenleme ile toplam 54 planlı görev bulunur. Her programı ayrı oturumda deneyebilirsiniz.</p>",
        "<p>FreeCAD: STEP, AutoCAD: DXF, SolidWorks: STEP ilk deneme rotasıdır; alternatif üç biçim her örnekte bulunur. Gerçek ürün/sürüm desteğini ayrıca kontrol edin. STEP/IGES düzlemsel yüz, DXF eğri nesneleridir; ölçü/kısıt geçmişi beklenmez.</p>",
        "<p>Şekilden Denkleme → Araştırma · üç CAD pilotu → Hazırlık ve görevler → Görev planı aç. Görevi seçip pilot formuna aktarın. Gerçek sürüm, katılımcı kodu, mevcut yöntem ve onayı operatör girer. Varsayılan eğitim modudur. Başarısızlıkları da kaydedin.</p>",
    ]
    for case in plan["cases"].values():
        esc = html.escape
        parts.append(
            f"<h2>{esc(case['label'])}</h2><img alt='Kaynak raster' src='{case['source_png']}' width='260'> <img alt='Kayıtlı model' src='{case['model_png']}' width='320'>"
        )
        parts.append(
            f"<p><a href='{case['parameters']}'>Fiziksel hedef katsayıları, aralıklar ve ölçüm kapsamı</a> · <a href='{case['equations']}'>Denklemler (çalışma birimi)</a> · <a href='{case['project']}'>Yeniden uydurmasız proje</a></p>"
        )
        parts.append(
            "<p>"
            + " · ".join(
                f"<a href='{path}'>{kind.upper()}</a>" for kind, path in case["cad"].items()
            )
            + "</p>"
        )
        parts.append(
            "<pre>"
            + esc(
                json.dumps(
                    {
                        k: case[k]
                        for k in [
                            "component_count",
                            "hole_count",
                            "bounding_min_mm",
                            "bounding_max_mm",
                            "edit_target",
                            "physical_error_summary",
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            + "</pre>"
        )
    for task in plan["tasks"]:
        parts.append(
            f"<h3>{task['order']}. {html.escape(task['id'])}</h3><pre>{html.escape(task_instructions(plan, task))}</pre>"
        )
    return html_page("Üç CAD programında ilk deneme", "\n".join(parts))


def build_pack(
    projects: str | Path,
    output: str | Path,
    *,
    cancel: Event | None = None,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """Kayıtlı üç örneği yeniden uydurmadan aktarır, doğrular ve yeni klasörde yayımlar.

    Native CAD okuyucuları her dosyayı tekrar açar. İşlem ara adımlarda iptal
    edilebilir; çalışan çekirdek işlemi kesilmez. Başarısız/iptal paket yayımlanmaz.
    Önceki paketler ve insan pilot kayıtları değiştirilmez.
    """
    projects, output = Path(projects), Path(output)
    for key in CASES:
        if not (projects / key / "model.json").is_file():
            raise ValueError(
                f"Örnek projesi eksik: {key}/model.json. cad_product_validation klasörünü seçin."
            )
    output.mkdir(parents=True, exist_ok=True)
    target = output / ("ilk-cad-denemesi-" + uuid4().hex[:12])
    options = CadOptions(unit="mm", scale=0.1, tolerance=0.01)
    with tempfile.TemporaryDirectory(prefix=".pilot-pack-", dir=output) as temp:
        root = Path(temp) / "package"
        root.mkdir()
        plan = {
            "schema_version": "1.0",
            "kind": "cad_pilot_plan",
            "created_at": utc_now(),
            "application_version": "",
            "observation_count": 0,
            "cases": {},
            "tasks": [],
            "assets": {},
            "scope": "Planned manual CAD handoff tasks, not executed observations. Baseline preparation and source fitting time excluded; no total workflow speed claim.",
        }
        for key, label in CASES.items():
            _check_cancel(cancel)
            if progress:
                progress(
                    f"Görev paketi: {label}; kayıtlı model ve üç gerçek CAD dosyası hazırlanıyor."
                )
            result = load_project(projects / key / "model.json")
            directory = root / key
            directory.mkdir()
            save_project(result, directory / "model.json")
            image = source_image(result)
            if image is None:
                raise ValueError(
                    f"{label}: gömülü veya hash'i doğrulanan kaynak görsel bulunamadı."
                )
            image.save(directory / "source.png")
            with Image.open(directory / "source.png") as check:
                check.verify()
            export_file(result, directory / "model.png", "png", ExportOptions(pixel_size=800))
            export_file(result, directory / "equations.txt", "txt")
            cad_paths = {}
            for kind in ("step", "iges", "dxf"):
                _check_cancel(cancel)
                path = export_cad(result, directory / f"reconstruction.{kind}", kind, options)
                cad_paths[kind] = path.relative_to(root).as_posix()
            data, rings = inspect_cad(directory / "reconstruction.step")
            points = np.vstack(list(rings.values()))
            parameters = {
                "unit": "mm",
                "scale": 0.1,
                "native_curves": data["native_curves"],
                "coordinate_contract": data["coordinate_contract"],
                "physical_error_summary": data["physical_error_summary"],
                "bounding_scope": "Controlled float64 polygon envelope extrema; not an analytic extrema certificate or ideal object dimensions.",
            }
            (directory / "target-mm.json").write_text(
                json.dumps(parameters, ensure_ascii=False, allow_nan=False, indent=2),
                encoding="utf8",
            )
            plan["application_version"] = data["application_version"]
            plan["cases"][key] = {
                "label": label,
                "case_id": f"{data['source']['sha256'][:12]}:{data['selected_model']['id']}:mm:0.1",
                "project": f"{key}/model.json",
                "parameters": f"{key}/target-mm.json",
                "source_png": f"{key}/source.png",
                "model_png": f"{key}/model.png",
                "equations": f"{key}/equations.txt",
                "cad": cad_paths,
                "component_count": data["topology"]["component_count"],
                "hole_count": data["topology"]["hole_count"],
                "bounding_min_mm": points.min(axis=0).tolist(),
                "bounding_max_mm": points.max(axis=0).tolist(),
                "bounding_scope": parameters["bounding_scope"],
                "edit_target": _edit_target(data["native_curves"]),
                "physical_error_summary": data["physical_error_summary"],
            }
        plan["tasks"] = planned_tasks(plan["cases"])
        (root / "index.html").write_text(_guide(plan), encoding="utf8")
        plan["assets"] = {
            p.relative_to(root).as_posix(): {"sha256": _digest(p), "bytes": p.stat().st_size}
            for p in sorted(root.rglob("*"))
            if p.is_file()
        }
        plan_path = root / "plan.json"
        plan_path.write_text(
            json.dumps(plan, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf8"
        )
        load_pack(plan_path)
        _check_cancel(cancel)
        os.replace(root, target)
    return target / "plan.json"


def load_pack(path: str | Path) -> dict[str, Any]:
    """Şema, dosya kapsamı ve hash'leri denetler; taşınan paket kaynak görsel aramaz."""
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise ValueError("Görev planı 2 MB sınırını aşıyor.")
    try:
        plan = json.loads(path.read_text(encoding="utf8"))
        if (
            set(plan) != PLAN_FIELDS
            or type(plan["observation_count"]) is not int
            or not isinstance(plan["application_version"], str)
            or len(plan["application_version"]) > 100
            or not isinstance(plan["created_at"], str)
            or not isinstance(plan["scope"], str)
            or plan["schema_version"] != "1.0"
            or plan["kind"] != "cad_pilot_plan"
            or plan["observation_count"] != 0
        ):
            raise ValueError("Desteklenen boş gözlemli görev planı değil.")
        if (
            set(plan["cases"]) != set(CASES)
            or not 1 <= len(plan["assets"]) <= 256
            or "index.html" not in plan["assets"]
        ):
            raise ValueError("Görev planının örnek/dosya kapsamı geçersiz.")
        total = 0
        for relative, expected in plan["assets"].items():
            asset = asset_path(path, relative)
            if (
                set(expected) != {"sha256", "bytes"}
                or type(expected["bytes"]) is not int
                or not isinstance(expected["sha256"], str)
                or len(expected["sha256"]) != 64
                or not 0 < expected["bytes"] <= 80_000_000
                or asset.stat().st_size != expected["bytes"]
                or _digest(asset) != expected["sha256"]
            ):
                raise ValueError(f"Görev dosyası değişmiş veya eksik: {relative}")
            total += expected["bytes"]
            if total > 250_000_000:
                raise ValueError("Görev dosyaları toplam 250 MB sınırını aşıyor.")
        for case in plan["cases"].values():
            if set(case) != CASE_FIELDS:
                raise ValueError("Görev örneğinde eksik/bilinmeyen alan var.")
            referenced = [
                case[k] for k in ("project", "parameters", "source_png", "model_png", "equations")
            ]
            if set(case["cad"]) != {"step", "iges", "dxf"}:
                raise ValueError("Üç CAD biçimi görev planında bulunmalıdır.")
            referenced += list(case["cad"].values()) + [
                v + ".cad.json" for v in case["cad"].values()
            ]
            if any(v not in plan["assets"] for v in referenced):
                raise ValueError("Görev dosyası hash envanterinde bulunamadı.")
            data, rings = inspect_cad(asset_path(path, case["cad"]["step"]))
            points = np.vstack(list(rings.values()))
            if (
                case["case_id"]
                != f"{data['source']['sha256'][:12]}:{data['selected_model']['id']}:mm:0.1"
                or case["component_count"] != data["topology"]["component_count"]
                or case["hole_count"] != data["topology"]["hole_count"]
                or case["bounding_min_mm"] != points.min(axis=0).tolist()
                or case["bounding_max_mm"] != points.max(axis=0).tolist()
                or case["edit_target"] != _edit_target(data["native_curves"])
                or case["physical_error_summary"] != data["physical_error_summary"]
                or not isinstance(case["label"], str)
                or not 1 <= len(case["label"]) <= 100
            ):
                raise ValueError("Görev hedefi CAD eşleme kaydıyla uyuşmuyor.")
            parameters = json.loads(asset_path(path, case["parameters"]).read_text(encoding="utf8"))
            if (
                parameters["unit"] != "mm"
                or parameters["scale"] != 0.1
                or parameters["native_curves"] != data["native_curves"]
            ):
                raise ValueError("Fiziksel hedef katsayıları CAD geometrisiyle uyuşmuyor.")
            for kind, relative in case["cad"].items():
                other, _ = inspect_cad(asset_path(path, relative))
                if (
                    other["format"] != kind
                    or other["cad_options"]
                    != {"unit": "mm", "scale": 0.1, "tolerance": 0.01, "allow_approximation": False}
                    or other["native_curves"] != data["native_curves"]
                    or other["selected_model"] != data["selected_model"]
                ):
                    raise ValueError("Üç CAD biçimi aynı matematiksel hedefi taşımıyor.")
        expected = planned_tasks(plan["cases"])
        if plan["tasks"] != expected or any(set(t) != TASK_FIELDS for t in plan["tasks"]):
            raise ValueError("Görev sırası veya ortak hedefler şema 1.0 ile uyuşmuyor.")
        return plan
    except (
        KeyError,
        TypeError,
        AttributeError,
        UnicodeError,
        RecursionError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError("Görev planı JSON'u eksik veya bozuk.") from error
