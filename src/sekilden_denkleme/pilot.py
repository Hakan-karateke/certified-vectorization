"""Yerel CAD pilot kayıtları; insan verisi, eğitim denemesi ve eşli ölçüm ayrımı.

Süreler saniyedir. Kalite kutuları operatör beyanıdır; bağımsız geometri
sertifikası değildir. Eşli karşılaştırma aynı kişi/ürün/sürüm/işletim sistemi,
şekil, görev ve tekrar kodunda iki yöntem de kalite koşullarını sağlarsa yapılır.
"""

import csv
import hashlib
import html
import json
import math
import os
import statistics
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

TASKS = {"import": "İçe alma", "profile": "Profil ve 5 mm ekstrüzyon", "edit": "Eğri düzenleme"}
TASK_INSTRUCTIONS = {
    "import": "Dosya seçimini başlatmadan önce sayacı başlatın; doğru fiziksel ölçekte geometri göründüğünde durdurun.",
    "profile": "İçe alınmış geometriden kapalı profil oluşturun ve 5 mm ekstrüzyon yapın. Birleştirme/onarma işlemlerini sayın.",
    "edit": "Çemberde yarıçapı %10 artırın; spline'da seçilen kontrol noktasını +X yönünde 0.1 mm taşıyın. İki yöntemde aynı hedefi kullanın; sketch/kısıt kurulumunu düzeltme türüne yazın.",
}
METHODS = {"generated": "Üretilen CAD", "baseline": "Mevcut yöntem"}
CHECKS = {
    "units": "Fiziksel birim doğru",
    "dimensions": "Boyutlar hedefe uygun",
    "components": "Bileşen sayısı doğru",
    "holes": "Delik sayısı doğru",
    "closed_profile": "Kapalı profil kullanılabilir",
    "extrusion": "5 mm ekstrüzyon başarılı",
    "edit": "İstenen eğri düzenlemesi başarılı",
}
REQUIRED = {
    "import": ("units", "dimensions", "components", "holes"),
    "profile": ("units", "dimensions", "components", "holes", "closed_profile", "extrusion"),
    "edit": ("units", "dimensions", "components", "holes", "edit"),
}


def utc_now() -> str:
    """Saat dilimi açık bir UTC zaman damgası üretir."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Stopwatch:
    """Monotonik saatle etkin süreyi ölçer; bekleme/duraklama süresini eklemez."""

    clock: Callable[[], float] = time.monotonic
    accumulated: float = 0.0
    started: float | None = None

    def start(self) -> None:
        """Duran sayacı sürdürür; çalışan sayacı yeniden başlatmaz."""
        if self.started is None:
            self.started = self.clock()

    def elapsed(self) -> float:
        """Şu ana kadarki etkin süreyi saniye olarak döndürür."""
        return self.accumulated + (self.clock() - self.started if self.started is not None else 0)

    def pause(self) -> float:
        """Süreyi sabitler; art arda duraklatma ek süre yazmaz."""
        self.accumulated = self.elapsed()
        self.started = None
        return self.accumulated


@dataclass
class PilotTrial:
    """Tek kişi/görev/yöntem denemesi; gözlem ile yazılım kontrolünü karıştırmaz."""

    participant: str
    product: str
    product_version: str
    operating_system: str
    experience: str
    baseline_method: str
    case_id: str
    task: str
    method: str
    repeat: str = "1"
    order: int = 1
    kind: str = "training_demo"
    consent: bool = False
    status: str = "failed"
    seconds: float = 0.0
    timing: str = "manual"
    repairs: int = 0
    repair_types: str = ""
    checks: dict[str, bool | None] = field(default_factory=lambda: dict.fromkeys(CHECKS))
    notes: str = ""
    evidence: dict[str, str] = field(default_factory=dict)
    format: str = "step"
    target_tolerance_mm: float = 0.1
    time_limit_seconds: float = 600.0
    id: str = field(default_factory=lambda: str(uuid4()))
    recorded_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        """Sonlu süreyi, onayı ve göreve özgü başarı koşullarını doğrular."""
        for key in (
            "participant",
            "product",
            "product_version",
            "operating_system",
            "experience",
            "baseline_method",
            "case_id",
            "repeat",
            "id",
        ):
            value = getattr(self, key)
            if not isinstance(value, str) or not value.strip() or len(value) > 300:
                raise ValueError(f"Pilot alanı boş veya çok uzun: {key}.")
        for key, limit in [("notes", 5000), ("repair_types", 1000)]:
            if not isinstance(getattr(self, key), str) or len(getattr(self, key)) > limit:
                raise ValueError(f"Pilot metni geçersiz: {key}.")
        if self.task not in TASKS or self.method not in METHODS:
            raise ValueError("Pilot görev/yöntem değeri bilinmiyor.")
        if self.kind not in {"human", "training_demo"} or type(self.consent) is not bool:
            raise ValueError("Pilot veri türü/onay değeri geçersiz.")
        if self.kind == "human" and not self.consent:
            raise ValueError("İnsan pilot kaydı için katılımcı onayı kaydedilmelidir.")
        if self.status not in {"completed", "failed", "timeout"}:
            raise ValueError("Görev durumu completed, failed veya timeout olmalıdır.")
        if self.timing not in {"stopwatch", "manual"}:
            raise ValueError("Süre kaynağı kronometre veya elle ölçüm olmalıdır.")
        for key in ("target_tolerance_mm", "time_limit_seconds"):
            value = getattr(self, key)
            if (
                type(value) not in {int, float}
                or not math.isfinite(value)
                or value <= 0
                or value > 86400
            ):
                raise ValueError("Kalite toleransı ve görev süre sınırı pozitif sonlu olmalıdır.")
        if (
            type(self.seconds) not in {int, float}
            or not math.isfinite(self.seconds)
            or not 0 <= self.seconds <= 86400
        ):
            raise ValueError("Süre 0–86400 saniye arasında sonlu sayı olmalıdır.")
        if (
            type(self.repairs) is not int
            or not 0 <= self.repairs <= 10000
            or type(self.order) is not int
            or not 1 <= self.order <= 10000
        ):
            raise ValueError("Düzeltme sayısı veya uygulama sırası geçersiz.")
        if (
            not isinstance(self.checks, dict)
            or set(self.checks) != set(CHECKS)
            or any(v is not None and type(v) is not bool for v in self.checks.values())
        ):
            raise ValueError("Kalite kontrolü evet/hayır/bilinmiyor değerlerini içermelidir.")
        if self.status == "completed" and any(
            self.checks[k] is not True for k in REQUIRED[self.task]
        ):
            raise ValueError(
                "Başarılı görev için gerekli kalite kontrollerinin tümü Evet olmalıdır."
            )
        if self.status == "completed" and self.seconds > self.time_limit_seconds:
            raise ValueError("Görev süre sınırını aştı; tamamlandı olarak kaydedilemez.")
        if self.status == "completed" and self.seconds <= 0:
            raise ValueError("Başarılı görev için pozitif ölçülmüş süre gereklidir.")
        if self.format not in {"step", "iges", "dxf", "other"}:
            raise ValueError("Pilot dosya biçimi bilinmiyor.")
        if (
            not isinstance(self.evidence, dict)
            or set(self.evidence) - {"path", "sha256", "cad_sha256"}
            or any(not isinstance(v, str) or len(v) > 2000 for v in self.evidence.values())
        ):
            raise ValueError("Kanıt dosyası kaydı geçersiz.")
        for key in ("sha256", "cad_sha256"):
            if key in self.evidence and (
                len(self.evidence[key]) != 64
                or any(c not in "0123456789abcdef" for c in self.evidence[key])
            ):
                raise ValueError("Kanıt SHA-256 değeri geçersiz.")
        try:
            if datetime.fromisoformat(self.recorded_at).tzinfo is None:
                raise ValueError("Saat dilimi eksik.")
        except (TypeError, ValueError) as error:
            raise ValueError("Pilot zaman damgası geçersiz.") from error


@dataclass
class PilotStudy:
    """Sürümlü yerel çalışma; eğitim denemeleri insan sayısına dahil edilmez."""

    title: str = "Üç CAD programında ilk kullanım pilotu"
    trials: list[PilotTrial] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        """Çalışmayı ve kimlik/tekrar çakışmalarını dosya yazmadan önce denetler."""
        if not isinstance(self.title, str) or not self.title.strip() or len(self.title) > 300:
            raise ValueError("Çalışma başlığı geçersiz.")
        if len(self.trials) > 10000:
            raise ValueError("Pilot çalışma 10.000 kayıt sınırını aşıyor.")
        try:
            if datetime.fromisoformat(self.created_at).tzinfo is None:
                raise ValueError("Saat dilimi eksik.")
        except (TypeError, ValueError) as error:
            raise ValueError("Çalışma zaman damgası geçersiz.") from error
        ids, attempts = set(), set()
        for trial in self.trials:
            trial.validate()
            key = (*pair_key(trial), trial.method)
            if trial.id in ids or key in attempts:
                raise ValueError(
                    "Aynı kişi/görev/yöntem/tekrar için çift kayıt var; tekrar kodunu değiştirin."
                )
            ids.add(trial.id)
            attempts.add(key)

    def to_dict(self) -> dict[str, Any]:
        """Şema 1.0 sözleşmesini üretir; özet sayıları ham denemelerden türetilir."""
        self.validate()
        return {"schema_version": "1.0", "protocol_version": "1.1", **asdict(self)}


def pair_key(trial: PilotTrial) -> tuple[str, ...]:
    """Ürün/sürüm/OS ve tekrar farklıysa aynı eşte havuzlamayı önler."""
    return (
        trial.kind,
        trial.participant,
        trial.product,
        trial.product_version,
        trial.operating_system,
        trial.case_id,
        trial.task,
        trial.repeat,
        trial.baseline_method,
        str(float(trial.target_tolerance_mm)),
        str(float(trial.time_limit_seconds)),
    )


def study_from_dict(data: dict[str, Any]) -> PilotStudy:
    """Bilinmeyen sürümü veya bozuk alanları açıklayıcı hatayla reddeder."""
    try:
        if data["schema_version"] != "1.0" or data["protocol_version"] != "1.1":
            raise ValueError("Pilot şema/protokol sürümü desteklenmiyor.")
        if set(data) != {"schema_version", "protocol_version", "title", "trials", "created_at"}:
            raise ValueError("Pilot dosyası eksik veya bilinmeyen alan içeriyor.")
        if not isinstance(data["trials"], list) or any(
            not isinstance(t, dict) or set(t) != set(PilotTrial.__dataclass_fields__)
            for t in data["trials"]
        ):
            raise ValueError("Pilot denemesi eksik veya bilinmeyen alan içeriyor.")
        study = PilotStudy(
            data["title"], [PilotTrial(**t) for t in data["trials"]], data["created_at"]
        )
        study.validate()
        return study
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Geçerli pilot çalışma dosyası okunamadı.") from error


def load_study(path: str | Path) -> PilotStudy:
    """En çok 20 MB UTF-8 JSON okur; CAD dosyası veya program yürütmez."""
    path = Path(path)
    if path.stat().st_size > 20_000_000:
        raise ValueError("Pilot çalışma 20 MB sınırını aşıyor.")
    try:
        return study_from_dict(json.loads(path.read_text(encoding="utf8")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Pilot dosyası geçerli UTF-8 JSON değil.") from error


def atomic_text(
    path: str | Path, content: str, validator: Callable[[Path], Any] | None = None
) -> Path:
    """Aynı dizinde geçici dosya oluşturur; denetimden sonra atomik değiştirir."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".pilot-", suffix=path.suffix, dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf8", newline="") as stream:
            stream.write(content)
        if validator:
            validator(temp)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return path


def save_study(study: PilotStudy, path: str | Path) -> Path:
    """Kayıtlı denemeleri yeniden okuyup doğrular; hata eski hedefi korur."""
    return atomic_text(
        path, json.dumps(study.to_dict(), ensure_ascii=False, allow_nan=False, indent=2), load_study
    )


def evidence_file(path: str | Path) -> dict[str, str]:
    """Kullanıcının seçtiği kanıtın byte hash'ini alır; dosyayı çalıştırmaz."""
    path = Path(path)
    if path.stat().st_size > 150_000_000:
        raise ValueError("Kanıt dosyası 150 MB sınırını aşıyor.")
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def summarize(study: PilotStudy) -> dict[str, Any]:
    """Yalnız başarılı insan eşlerini karşılaştırır; sansürlü/eksik çiftleri sayar.

    Fark üretilen CAD eksi mevcut yöntemdir; negatif süre daha hızlıdır.
    Eğitim kayıtları, başarısızlık ve süre aşımı medyana başarı gibi sokulmaz.
    """
    study.validate()
    humans = [t for t in study.trials if t.kind == "human"]
    groups: dict[tuple[str, ...], dict[str, PilotTrial]] = {}
    for trial in humans:
        groups.setdefault(pair_key(trial), {})[trial.method] = trial
    pairs, excluded = [], []
    for key, methods in groups.items():
        if len(methods) != 2 or any(t.status != "completed" for t in methods.values()):
            excluded.append(
                {
                    "key": list(key),
                    "reason": "missing_pair" if len(methods) != 2 else "failed_or_timeout",
                }
            )
            continue
        generated, baseline = methods["generated"], methods["baseline"]
        if generated.order == baseline.order:
            excluded.append({"key": list(key), "reason": "ambiguous_order"})
            continue
        pairs.append(
            {
                "participant": generated.participant,
                "product": generated.product,
                "version": generated.product_version,
                "os": generated.operating_system,
                "case": generated.case_id,
                "task": generated.task,
                "repeat": generated.repeat,
                "target_tolerance_mm": generated.target_tolerance_mm,
                "time_limit_seconds": generated.time_limit_seconds,
                "generated_id": generated.id,
                "baseline_id": baseline.id,
                "seconds_delta": generated.seconds - baseline.seconds,
                "repairs_delta": generated.repairs - baseline.repairs,
            }
        )
    by_product = []
    grouping = (
        "product",
        "version",
        "os",
        "case",
        "task",
        "target_tolerance_mm",
        "time_limit_seconds",
    )
    for key in sorted({tuple(p[k] for k in grouping) for p in pairs}):
        rows = [p for p in pairs if tuple(p[k] for k in grouping) == key]
        by_product.append(
            {
                **dict(zip(grouping, key, strict=True)),
                "pairs": len(rows),
                "participants": len({p["participant"] for p in rows}),
                "median_seconds_delta": statistics.median(p["seconds_delta"] for p in rows),
                "median_repairs_delta": statistics.median(p["repairs_delta"] for p in rows),
            }
        )
    return {
        "human_participants": len({t.participant for t in humans}),
        "human_trials": len(humans),
        "training_trials": len(study.trials) - len(humans),
        "statuses": dict(Counter(t.status for t in humans)),
        "paired_results": pairs,
        "excluded_pairs": excluded,
        "by_product": by_product,
        "scope": "Operator-reported tasks; no causal/general usability or geometric certificate claim.",
    }


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    """Bütün hücreleri kaçırılmış, yerel HTML tablosu üretir."""
    return (
        '<div class="table-wrap"><table><thead><tr>'
        + "".join(f"<th>{html.escape(h)}</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>"
            for row in rows
        )
        + "</tbody></table></div>"
    )


def html_page(title: str, body: str) -> str:
    """Harici ağ veya betik içermeyen Türkçe rapor sayfası oluşturur."""
    return (
        '<!doctype html><html lang="tr"><meta charset="utf-8"><title>'
        + html.escape(title)
        + "</title><style>body{font:16px system-ui;max-width:1200px;margin:32px auto;padding:20px;color:#173142}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{border:1px solid #ccd6dd;padding:8px;text-align:left}th{background:#eef3f6}pre{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%}</style><h1>"
        + html.escape(title)
        + "</h1>"
        + body
        + "</html>"
    )


def export_study(study: PilotStudy, directory: str | Path) -> list[Path]:
    """Ham JSON, güvenli CSV ve eşli karşılaştırmalı HTML raporunu üretir."""
    import io

    directory = Path(directory)
    summary = summarize(study)
    paths = [save_study(study, directory / "pilot.json")]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    fields = list(PilotTrial.__dataclass_fields__)
    writer.writerow(fields)
    for trial in study.trials:
        row = asdict(trial)
        cells = [
            json.dumps(row[k], ensure_ascii=False) if isinstance(row[k], dict) else row[k]
            for k in fields
        ]
        writer.writerow(
            [
                "'" + c if isinstance(c, str) and c.lstrip().startswith(("=", "+", "-", "@")) else c
                for c in cells
            ]
        )
    paths.append(atomic_text(directory / "pilot.csv", "\ufeff" + stream.getvalue()))
    body = f"<p>İnsan katılımcı: {summary['human_participants']}; insan denemesi: {summary['human_trials']}; eğitim/deneme: {summary['training_trials']}.</p><p>Fark = üretilen CAD − mevcut yöntem. Negatif değer daha az süre/düzeltmedir. Yalnız iki yöntemi de kalite koşullarını sağlayan insan çiftleri karşılaştırılır. Eğitim kayıtları ve başarısız/süre aşan görevler medyana katılmaz. Ürün/sürüm/OS ayrı tutulur; bu sonuçlar genel verimlilik veya nedensellik kanıtı değildir.</p>"
    body += _table(
        [
            "Ürün",
            "Sürüm",
            "OS",
            "Şekil",
            "Görev",
            "Tolerans mm",
            "Sınır s",
            "Çift",
            "Kişi",
            "Medyan Δ saniye",
            "Medyan Δ düzeltme",
        ],
        [
            [
                r[k]
                for k in [
                    "product",
                    "version",
                    "os",
                    "case",
                    "task",
                    "target_tolerance_mm",
                    "time_limit_seconds",
                    "pairs",
                    "participants",
                    "median_seconds_delta",
                    "median_repairs_delta",
                ]
            ]
            for r in summary["by_product"]
        ],
    )
    body += "<h2>Bütün ham denemeler</h2>" + _table(
        [
            "Kod",
            "Tür",
            "Program",
            "Şekil",
            "Görev",
            "Yöntem",
            "Durum",
            "Saniye",
            "Düzeltme",
            "Gözlem",
        ],
        [
            [
                t.participant,
                t.kind,
                t.product + " " + t.product_version,
                t.case_id,
                TASKS[t.task],
                METHODS[t.method],
                t.status,
                t.seconds,
                t.repairs,
                t.notes,
            ]
            for t in study.trials
        ],
    )
    body += (
        "<h2>Eşler ve dışarıda kalan kayıtlar</h2><pre>"
        + html.escape(json.dumps(summary, ensure_ascii=False, indent=2))
        + "</pre>"
    )
    paths.append(atomic_text(directory / "pilot.html", html_page(study.title, body)))
    return paths
