"""Türkçe pilot, ayrı CAD ürünü deneyi ve araştırma raporu çalışma alanı."""

import copy
import json
import platform
import queue
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from tkinter import filedialog, messagebox, ttk
from typing import Any

import numpy as np

from .cad_compatibility import inspect_cad, run_freecad_check
from .fitting import AnalysisCancelled
from .models import AnalysisResult
from .pilot import (
    CHECKS,
    METHODS,
    REQUIRED,
    TASK_INSTRUCTIONS,
    TASKS,
    PilotStudy,
    PilotTrial,
    Stopwatch,
    evidence_file,
    export_study,
    load_study,
    save_study,
    summarize,
)
from .research_report import compare_saved_projects, export_comparison

KINDS = {"Eğitim / deneme (insan sonucu sayılmaz)": "training_demo", "Gerçek insan pilotu": "human"}
STATUSES = {"Başarısız": "failed", "Tamamlandı": "completed", "Süre aşıldı": "timeout"}
YES_NO = {"Bilinmiyor": None, "Evet": True, "Hayır": False}


class PilotWindow:
    """Modelden bağımsız yerel çalışma; uzun ürün/rapor işleri Tk'yi kilitlemez."""

    def __init__(self, parent: tk.Tk, result: AnalysisResult | None = None) -> None:
        """Boş pilot açar; katılımcı veya ölçüm oluşturmaz."""
        self.window = tk.Toplevel(parent)
        self.window.title("Araştırma ve CAD pilot çalışma alanı")
        self.window.geometry("1180x820")
        self.window.minsize(1000, 680)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.result = result
        self.study = PilotStudy()
        self.study_path: Path | None = None
        self.dirty = False
        self.form_dirty = False
        self._resetting = False
        self.editing_id: str | None = None
        self.evidence: dict[str, str] = {}
        self.timer = Stopwatch()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future: Future | None = None
        self.cancel_event = Event()
        self.messages: queue.Queue[str] = queue.Queue()
        self.closed = False
        self.on_done = None
        self.actions: list[ttk.Button] = []
        self.status = tk.StringVar(
            value="İnsan pilotu henüz başlamadı. Üç CAD ürününün kayıtları ayrı tutulur."
        )
        host = ttk.Frame(self.window, padding=12)
        host.pack(fill="both", expand=True)
        self.notebook = ttk.Notebook(host)
        self.notebook.pack(fill="both", expand=True)
        preparation_tab, trials_tab, cad_tab, research_tab = [
            ttk.Frame(self.notebook, padding=10) for _ in range(4)
        ]
        self.trials_tab = trials_tab
        for tab, label in [
            (preparation_tab, "Hazırlık ve görevler"),
            (trials_tab, "Pilot oturumları"),
            (cad_tab, "CAD uyumluluğu"),
            (research_tab, "Araştırma karşılaştırması"),
        ]:
            self.notebook.add(tab, text=label)
        self._build_trials(trials_tab)
        self._build_cad(cad_tab)
        self._build_research(research_tab)
        from .pilot_preparation_gui import PreparationPanel

        self.preparation = PreparationPanel(self, preparation_tab, Path.cwd())
        self.fields["participant"].trace_add("write", self._participant_changed)
        self.timing.trace_add("write", self._timing_changed)
        for variable in [
            *self.fields.values(),
            self.kind,
            self.method,
            self.task,
            self.task_status,
            self.format,
            self.timing,
            self.consent,
            *self.check_vars.values(),
        ]:
            variable.trace_add("write", self._mark_form)
        self.notes.bind("<<Modified>>", self._notes_changed)
        footer = ttk.Frame(host)
        footer.pack(fill="x", pady=(8, 0))
        ttk.Label(footer, textvariable=self.status, wraplength=1000).pack(
            side="left", fill="x", expand=True
        )
        self.cancel_button = ttk.Button(
            footer, text="İşlemi iptal et", command=self.cancel_job, state="disabled"
        )
        self.cancel_button.pack(side="right")
        self.window.after(200, self._tick)

    def cancel_job(self) -> None:
        """Düğme kurulduğundaki eski olay yerine yürüyen işin iptal olayını işaretler."""
        self.cancel_event.set()
        self.status.set("İptal istendi; yürüyen sayısal adımın bitmesi bekleniyor.")

    def _participant_changed(self, *_: Any) -> None:
        """Katılımcı değiştirilince önceki kişinin onayını yeni kişiye taşımaz."""
        if not self._resetting:
            self.consent.set(False)

    def apply_planned_task(self, plan: dict, task: dict, path: Path, settings: Any) -> None:
        """Planı ölçüm formuna aktarır; süre, onay, kalite veya insan sonucu üretmez."""
        from .pilot_pack import asset_path, task_instructions

        if self.form_dirty and not messagebox.askyesno(
            "Kayda eklenmemiş form",
            "Görev kartıyla mevcut formu değiştirmek istiyor musunuz?",
            parent=self.window,
        ):
            return
        case = plan["cases"][task["case"]]
        cad_path = asset_path(path, case["cad"][task["format"]])
        self.new_trial(confirm=False)
        self._resetting = True
        for key in (
            "product",
            "case_id",
            "repeat",
            "target_tolerance_mm",
            "time_limit_seconds",
        ):
            self.fields[key].set(str(task[key]))
        # Kartın önerilen sırası, gerçek uygulama sırası yerine geçmez.
        self.fields["order"].set(str(max((t.order for t in self.study.trials), default=0) + 1))
        self.fields["product_version"].set(settings.programs[task["product"]].version)
        self.method.set(METHODS[task["method"]])
        self.task.set(TASKS[task["task"]])
        self.format.set(task["format"])
        self.timing.set("Kronometre")
        self.cad_path.set(str(cad_path))
        self.notes.insert("1.0", f"Plan: {task['id']}\n{task_instructions(plan, task)}")
        self.notes.edit_modified(False)
        self._resetting = False
        self.form_dirty = True
        self.required_hint.set(
            task_instructions(plan, task)
            + "\nTamamlandı için: "
            + ", ".join(CHECKS[k] for k in REQUIRED[task["task"]])
        )
        self.notebook.select(self.trials_tab)
        self.status.set(
            "Görev hazır. Kişi/mevcut yöntem bilgisini tamamlayın; gerçekten ölçmeden başarı kaydetmeyin."
        )

    def _button(self, parent: Any, label: str, command: Any) -> ttk.Button:
        """İş sırasında pasifleştirilecek ortak eylem düğmesi oluşturur."""
        button = ttk.Button(parent, text=label, command=command)
        self.actions.append(button)
        return button

    def _build_trials(self, tab: ttk.Frame) -> None:
        """Kaydırılabilir ölçüm formu ve kayıt/özet tablosunu kurar."""
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", pady=(0, 8))
        for label, command in [
            ("Çalışma aç", self.open),
            ("Çalışmayı kaydet", self.save),
            ("JSON · CSV · HTML raporu", self.export),
            ("Yeni deneme", self.new_trial),
        ]:
            self._button(toolbar, label, command).pack(side="left", padx=(0, 6))
        panes = ttk.Panedwindow(tab, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left, right = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(left, weight=1)
        panes.add(right, weight=1)
        canvas = tk.Canvas(left, highlightthickness=0, width=500)
        scroll = ttk.Scrollbar(left, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        form = ttk.Frame(canvas, padding=(0, 0, 12, 8))
        item = canvas.create_window(0, 0, window=form, anchor="nw")
        form.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
        defaults = {
            "participant": "",
            "product": "FreeCAD",
            "product_version": "",
            "operating_system": platform.platform(),
            "experience": "",
            "baseline_method": "",
            "case_id": "",
            "repeat": "1",
            "order": "1",
            "seconds": "0",
            "repairs": "0",
            "repair_types": "",
            "target_tolerance_mm": "0.1",
            "time_limit_seconds": "600",
        }
        self.fields = {k: tk.StringVar(value=v) for k, v in defaults.items()}
        self.kind = tk.StringVar(value=next(iter(KINDS)))
        self.method = tk.StringVar(value=METHODS["generated"])
        self.task = tk.StringVar(value=TASKS["import"])
        self.task_status = tk.StringVar(value=next(iter(STATUSES)))
        self.format = tk.StringVar(value="step")
        self.timing = tk.StringVar(value="Kronometre")
        self.consent = tk.BooleanVar(value=False)
        labels = {
            "participant": "Takma katılımcı kodu",
            "product": "CAD programı",
            "product_version": "Program sürümü",
            "operating_system": "İşletim sistemi",
            "experience": "CAD deneyimi",
            "baseline_method": "Mevcut yöntem açıklaması (iki kayıtta aynı)",
            "case_id": "Aynı şekil / fiziksel hedef kodu",
            "repeat": "Eşleştirme / tekrar kodu",
            "order": "Uygulama sırası",
            "target_tolerance_mm": "İki yöntem için aynı kalite toleransı (mm)",
            "time_limit_seconds": "Görev süre sınırı (saniye)",
            "seconds": "Ölçülen etkin süre (saniye)",
            "repairs": "Düzeltme işlemi sayısı",
            "repair_types": "Düzeltme türleri",
        }
        rows = [("Veri türü", self.kind, list(KINDS))]
        rows += [
            (labels[k], v, ["FreeCAD", "AutoCAD", "SolidWorks"] if k == "product" else None)
            for k, v in self.fields.items()
            if k not in {"seconds", "repairs", "repair_types"}
        ]
        rows += [
            ("Yöntem", self.method, list(METHODS.values())),
            ("Görev", self.task, list(TASKS.values())),
            ("Dosya biçimi", self.format, ["step", "iges", "dxf", "other"]),
            ("Görev durumu", self.task_status, list(STATUSES)),
            ("Süre kaynağı", self.timing, ["Kronometre", "Elle ölçüm"]),
        ]
        for label, var, values in rows:
            ttk.Label(form, text=label).pack(anchor="w", pady=(6, 2))
            widget = (
                ttk.Combobox(form, textvariable=var, values=values, state="readonly")
                if values
                else ttk.Entry(form, textvariable=var)
            )
            widget.pack(fill="x")
        ttk.Checkbutton(form, text="Gerçek katılımcının onayı alındı", variable=self.consent).pack(
            anchor="w", pady=8
        )
        timerbar = ttk.Frame(form)
        timerbar.pack(fill="x")
        self._button(timerbar, "Başlat / sürdür", self.start_timer).pack(side="left")
        self._button(timerbar, "Duraklat", self.pause_timer).pack(side="left", padx=6)
        self.time_label = tk.StringVar(value="0.000 s · duruyor")
        ttk.Label(timerbar, textvariable=self.time_label).pack(side="left")
        for key in ["seconds", "repairs", "repair_types"]:
            ttk.Label(form, text=labels[key]).pack(anchor="w", pady=(6, 2))
            ttk.Entry(form, textvariable=self.fields[key]).pack(fill="x")
        self.required_hint = tk.StringVar()
        ttk.Label(form, textvariable=self.required_hint, wraplength=440).pack(anchor="w", pady=10)
        self.check_vars = {k: tk.StringVar(value="Bilinmiyor") for k in CHECKS}
        for key, label in CHECKS.items():
            row = ttk.Frame(form)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label).pack(side="left")
            ttk.Combobox(
                row,
                textvariable=self.check_vars[key],
                values=list(YES_NO),
                state="readonly",
                width=13,
            ).pack(side="right")
        self.task.trace_add("write", self._update_required)
        self._update_required()
        self.evidence_label = tk.StringVar(value="Kanıt dosyası seçilmedi.")
        self._button(form, "Kanıt / ekran kaydı dosyası seç", self.pick_evidence).pack(
            fill="x", pady=(10, 2)
        )
        ttk.Label(form, textvariable=self.evidence_label, wraplength=440).pack(anchor="w")
        ttk.Label(form, text="Gözlem ve başarısızlık nedeni").pack(anchor="w", pady=(10, 2))
        self.notes = tk.Text(form, height=4, wrap="word")
        self.notes.pack(fill="x")
        self._button(form, "Denemeyi kayda ekle / güncelle", self.record).pack(fill="x", pady=12)
        ttk.Label(right, text="Kaydı seçerek inceleyin veya güncelleyin.").pack(anchor="w")
        self.tree = ttk.Treeview(
            right,
            columns=("person", "product", "method", "task", "status", "seconds"),
            show="headings",
            height=13,
        )
        for key, label in [
            ("person", "Kod / tür"),
            ("product", "Program"),
            ("method", "Yöntem"),
            ("task", "Görev"),
            ("status", "Durum"),
            ("seconds", "Saniye"),
        ]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=90, stretch=True)
        self.tree.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<<TreeviewSelect>>", self.select_trial)
        self.summary = tk.Text(right, height=13, wrap="word", font=("Consolas", 9))
        self.summary.pack(fill="both", expand=True)
        self.refresh()

    def _build_cad(self, tab: ttk.Frame) -> None:
        """Üç ürünün aynı görev protokolünü ve FreeCADCmd otomasyonunu sunar."""
        ttk.Label(
            tab, text="Hedef ürünler: FreeCAD · AutoCAD · SolidWorks", font=("Segoe UI", 13, "bold")
        ).pack(anchor="w")
        ttk.Label(
            tab,
            text="Üç üründe de Pilot oturumları sekmesini kullanın. Otomatik ürün deneyi FreeCADCmd içindir. AutoCAD/SolidWorks kurulumu ve insan oturumu ayrıca yapılır. FreeCAD ayrı uygulamadır; OCCT geometri çekirdeği ortaktır.",
            wraplength=1050,
        ).pack(anchor="w", pady=10)
        self.cad_path = tk.StringVar()
        self.freecad_path = tk.StringVar()
        local = Path.cwd() / ".tmp/freecad"
        candidates = sorted(local.glob("*/bin/freecadcmd.exe")) if local.exists() else []
        if candidates:
            self.freecad_path.set(str(candidates[-1]))
        for label, var, command in [
            ("CAD dosyası (.cad.json kaydı yanında olmalı)", self.cad_path, self.pick_cad),
            (
                "FreeCADCmd yolu — D: üzerindeki kurulumu seçebilirsiniz",
                self.freecad_path,
                self.pick_freecad,
            ),
        ]:
            ttk.Label(tab, text=label).pack(anchor="w", pady=(10, 3))
            row = ttk.Frame(tab)
            row.pack(fill="x")
            ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
            self._button(row, "Seç", command).pack(side="right", padx=(8, 0))
        self._button(
            tab, "FreeCAD içe alma ve 5 mm ekstrüzyon deneyini çalıştır", self.run_compatibility
        ).pack(anchor="w", pady=12)
        self.cad_details = tk.Text(tab, wrap="word", height=20)
        self.cad_details.pack(fill="both", expand=True)

    def _build_research(self, tab: ttk.Frame) -> None:
        """Mevcut adayları veya kayıtlı tolerans projelerini yeniden uydurmadan raporlar."""
        ttk.Label(
            tab, text="Hata – karmaşıklık – kanıt karşılaştırması", font=("Segoe UI", 13, "bold")
        ).pack(anchor="w")
        ttk.Label(
            tab,
            text="Adayların örneklenmiş uzaklığı, sayısal üst tahmini, doğrulanmış sertifikası, bit maliyeti, parça/kontrol/düğüm sayıları ve ret gerekçeleri ayrı gösterilir. Farklı referanslar birbirine göre sıralanmaz. Rapor yerel HTML ve JSON olarak kaydedilir.",
            wraplength=1000,
        ).pack(anchor="w", pady=14)
        self._button(tab, "Mevcut projenin aday raporunu kaydet", self.report_current).pack(
            anchor="w", pady=5
        )
        self._button(tab, "Kayıtlı projeleri / toleransları karşılaştır", self.report_saved).pack(
            anchor="w", pady=5
        )

    def _update_required(self, *_: Any) -> None:
        """Göreve özgü geçiş koşullarını formda açıklar."""
        task = next(k for k, v in TASKS.items() if v == self.task.get())
        self.required_hint.set(
            TASK_INSTRUCTIONS[task]
            + "\n\nTamamlandı için Evet gerekenler: "
            + ", ".join(CHECKS[k] for k in REQUIRED[task])
            + ". Kutular operatör beyanıdır."
        )

    def _tick(self) -> None:
        """Kronometreyi ana döngüde yeniler; ölçüm uyku veya duvar saatine dayanmaz."""
        if self.closed:
            return
        elapsed = self.timer.elapsed()
        self.time_label.set(
            f"{elapsed:.3f} s · {'çalışıyor' if self.timer.started is not None else 'duruyor'}"
        )
        if self.timer.started is not None:
            self.fields["seconds"].set(f"{elapsed:.3f}")
        self.window.after(200, self._tick)

    def start_timer(self) -> None:
        """Yeni görevin etkin süresini başlatır; alan düzenlemesini ölçüm saymaz."""
        self.timing.set("Kronometre")
        self.timer.start()

    def _timing_changed(self, *_: Any) -> None:
        """Elle ölçüme geçildiğinde çalışan sayacın kullanıcı değerini ezmesini önler."""
        if (
            not self._resetting
            and self.timing.get() == "Elle ölçüm"
            and self.timer.started is not None
        ):
            self.pause_timer()

    def pause_timer(self) -> None:
        """Kronometre süresini saniye alanına yazar."""
        self.fields["seconds"].set(f"{self.timer.pause():.6f}")

    def _mark_form(self, *_: Any) -> None:
        """Kayda eklenmemiş form değişikliğini disk kaydından ayrı izler."""
        if not self._resetting:
            self.form_dirty = True

    def _notes_changed(self, _event: Any = None) -> None:
        """Metin widget'ının değişiklik bayrağını tek seferde tüketir."""
        if self.notes.edit_modified():
            self._mark_form()
            self.notes.edit_modified(False)

    def new_trial(self, *, confirm: bool = True) -> None:
        """Kişi/hedef bilgilerini koruyup yeni denemenin ölçüm alanlarını temizler."""
        if self.future is not None:
            return
        if (
            confirm
            and self.form_dirty
            and not messagebox.askyesno(
                "Kayda eklenmemiş form",
                "Mevcut deneme formunu temizlemek istiyor musunuz?",
                parent=self.window,
            )
        ):
            return
        self._resetting = True
        self.editing_id = None
        self.timer = Stopwatch()
        self.fields["seconds"].set("0")
        self.fields["repairs"].set("0")
        self.fields["repair_types"].set("")
        for var in self.check_vars.values():
            var.set("Bilinmiyor")
        self.task_status.set("Başarısız")
        self.notes.delete("1.0", "end")
        self.evidence = {}
        self.evidence_label.set("Kanıt dosyası seçilmedi.")
        self.tree.selection_remove(*self.tree.selection())
        self.notes.edit_modified(False)
        self._resetting = False
        self.form_dirty = False

    def record(self) -> None:
        """Doğrulanmış denemeyi belleğe tek işlemle ekler; disk kaydı ayrıca görünürdür."""
        if self.future is not None:
            return
        try:
            values = {k: v.get().strip() for k, v in self.fields.items()}
            values.update(
                seconds=self.timer.pause()
                if self.timing.get() == "Kronometre"
                else float(values["seconds"]),
                repairs=int(values["repairs"]),
                order=int(values["order"]),
                target_tolerance_mm=float(values["target_tolerance_mm"]),
                time_limit_seconds=float(values["time_limit_seconds"]),
            )
            trial = PilotTrial(
                **values,
                kind=KINDS[self.kind.get()],
                consent=self.consent.get(),
                method=next(k for k, v in METHODS.items() if v == self.method.get()),
                task=next(k for k, v in TASKS.items() if v == self.task.get()),
                status=STATUSES[self.task_status.get()],
                timing="stopwatch" if self.timing.get() == "Kronometre" else "manual",
                format=self.format.get(),
                checks={k: YES_NO[v.get()] for k, v in self.check_vars.items()},
                notes=self.notes.get("1.0", "end").strip(),
                evidence=self.evidence.copy(),
            )
            if self.editing_id:
                original = next(t for t in self.study.trials if t.id == self.editing_id)
                trial = replace(trial, id=original.id, recorded_at=original.recorded_at)
            updated = replace(
                self.study, trials=[t for t in self.study.trials if t.id != trial.id] + [trial]
            )
            updated.validate()
            self.study = updated
            self.dirty = True
            self.refresh()
            self.new_trial(confirm=False)
            self._resetting = True
            self.fields["order"].set(str(trial.order + 1))
            self.method.set(METHODS["baseline" if trial.method == "generated" else "generated"])
            self._resetting = False
            self.status.set("Deneme eklendi. Diske saklamak için Çalışmayı kaydet seçin.")
        except (ValueError, KeyError) as error:
            messagebox.showerror("Pilot kaydı eklenemedi", str(error), parent=self.window)

    def select_trial(self, _event: Any = None) -> None:
        """Kayıtlı denemeyi düzenleme formuna taşır; kaynak dosyayı çalıştırmaz."""
        if not self.tree.selection() or self.future is not None:
            return
        if self.form_dirty and not messagebox.askyesno(
            "Kayda eklenmemiş form",
            "Form değişikliklerini bırakıp seçili kaydı açmak istiyor musunuz?",
            parent=self.window,
        ):
            return
        self._resetting = True
        trial = next(t for t in self.study.trials if t.id == self.tree.selection()[0])
        self.editing_id = trial.id
        for key, var in self.fields.items():
            var.set(str(getattr(trial, key)))
        for var, mapping, value in [
            (self.kind, KINDS, trial.kind),
            (self.method, METHODS, trial.method),
            (self.task, TASKS, trial.task),
            (self.task_status, STATUSES, trial.status),
        ]:
            var.set(
                next(k for k, v in mapping.items() if v == value)
                if mapping in (KINDS, STATUSES)
                else mapping[value]
            )
        self.consent.set(trial.consent)
        self.format.set(trial.format)
        self.timing.set("Kronometre" if trial.timing == "stopwatch" else "Elle ölçüm")
        self.timer = Stopwatch(accumulated=trial.seconds)
        for key, value in trial.checks.items():
            self.check_vars[key].set(next(k for k, v in YES_NO.items() if v is value))
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", trial.notes)
        self.evidence = trial.evidence.copy()
        self.evidence_label.set(self.evidence.get("path", "Kanıt dosyası seçilmedi."))
        self.notes.edit_modified(False)
        self._resetting = False
        self.form_dirty = False

    def refresh(self) -> None:
        """Ham kayıtları ve eğitimden ayrılmış insan özetini yeniler."""
        self.tree.delete(*self.tree.get_children())
        for t in self.study.trials:
            self.tree.insert(
                "",
                "end",
                iid=t.id,
                values=(
                    t.participant + (" · eğitim" if t.kind == "training_demo" else ""),
                    t.product,
                    METHODS[t.method],
                    TASKS[t.task],
                    t.status,
                    f"{t.seconds:.3f}",
                ),
            )
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", json.dumps(summarize(self.study), ensure_ascii=False, indent=2))

    def pick_evidence(self) -> None:
        """Seçilmiş dosyanın hash'ini arka planda alır; veri içeriğini yürütmez."""
        path = filedialog.askopenfilename(parent=self.window, title="Yerel kanıt dosyası")
        if path:

            def done(value: dict) -> None:
                self.evidence = value
                self.evidence_label.set(value["path"])
                self.form_dirty = True

            self.job(evidence_file, path, done=done)

    def _discard(self) -> bool:
        """Kaydedilmemiş denemelerin kullanıcı haberi olmadan silinmesini engeller."""
        return not (self.dirty or self.form_dirty or self.preparation.dirty) or messagebox.askyesno(
            "Kaydedilmemiş pilot kayıtları",
            "Kaydedilmemiş pilot/form/program ayarı değişikliklerini bırakmak istiyor musunuz?",
            parent=self.window,
        )

    def open(self) -> None:
        """Kaydedilmiş çalışmayı doğrular; başarısız açılış mevcut kaydı korur."""
        if self.future is not None or not self._discard():
            return
        path = filedialog.askopenfilename(
            parent=self.window, filetypes=[("Pilot çalışma JSON", "*.json")]
        )
        if path:

            def done(value: PilotStudy) -> None:
                self.study, self.study_path, self.dirty = value, Path(path), False
                self.refresh()
                self.new_trial(confirm=False)

            self.job(load_study, path, done=done)

    def save(self) -> None:
        """Çalışmanın anlık kopyasını atomik kaydeder; başarısız kayıt başarı sayılmaz."""
        if self.future is not None:
            return
        if self.form_dirty:
            messagebox.showerror(
                "Form henüz kayda eklenmedi",
                "Önce Denemeyi kayda ekle / güncelle düğmesini kullanın veya Yeni deneme ile formu temizleyin.",
                parent=self.window,
            )
            return
        path = filedialog.asksaveasfilename(
            parent=self.window, defaultextension=".json", filetypes=[("Pilot çalışma", "*.json")]
        )
        if path:

            def done(value: Path) -> None:
                self.study_path, self.dirty = value, False

            self.job(save_study, copy.deepcopy(self.study), path, done=done)

    def export(self) -> None:
        """İnsan çiftleri ve dışarıda kalanları içeren yerel raporları kaydeder."""
        if self.future is not None:
            return
        path = filedialog.askdirectory(parent=self.window, title="Pilot raporu klasörü")
        if path:
            targets = [Path(path) / n for n in ["pilot.json", "pilot.csv", "pilot.html"]]
            if any(p.exists() for p in targets) and not messagebox.askyesno(
                "Raporlar yenilenecek", "Mevcut pilot raporları yenilensin mi?", parent=self.window
            ):
                return
            self.job(export_study, copy.deepcopy(self.study), path)

    def pick_freecad(self) -> None:
        """Kurulu veya taşınabilir FreeCADCmd yolunu kullanıcıdan alır."""
        path = filedialog.askopenfilename(
            parent=self.window,
            title="FreeCADCmd seçin",
            filetypes=[("FreeCADCmd", "*.exe"), ("Tüm dosyalar", "*")],
        )
        if path:
            self.freecad_path.set(path)

    def pick_cad(self) -> None:
        """Gerçek CAD dosyası/hash/ölçek hedefini okur; insan denemesi eklemez."""
        path = filedialog.askopenfilename(
            parent=self.window, filetypes=[("CAD dosyası", "*.step *.iges *.dxf")]
        )
        if path:
            self.cad_path.set(path)

            def done(value: tuple) -> None:
                data, rings = value
                points = np.vstack(list(rings.values()))
                expected = {
                    "cad_sha256": data["cad_sha256"],
                    "components": data["topology"]["component_count"],
                    "holes": data["topology"]["hole_count"],
                    "bounding_min_mm": points.min(axis=0).tolist(),
                    "bounding_max_mm": points.max(axis=0).tolist(),
                    "physical_calibration": "user_assigned",
                }
                self.cad_details.delete("1.0", "end")
                self.cad_details.insert("1.0", json.dumps(expected, ensure_ascii=False, indent=2))
                self.fields["case_id"].set(
                    f"{data['source']['sha256'][:12]}:{data['selected_model']['id']}:{data['cad_options']['unit']}:{data['cad_options']['scale']:g}"
                )
                self.format.set(data["format"])

            self.job(inspect_cad, path, done=done)

    def run_compatibility(self) -> None:
        """FreeCAD deneyini arka planda yürütür; geçti/başarısız ayrımını gösterir."""
        if self.future is not None:
            return
        directory = filedialog.askdirectory(
            parent=self.window, title="FreeCAD deney kayıtları klasörü"
        )
        if directory:
            executable, cad_path = self.freecad_path.get(), self.cad_path.get()

            def done(path: Path) -> None:
                data = json.loads(path.read_text(encoding="utf8"))
                self.cad_details.delete("1.0", "end")
                self.cad_details.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))
                self.status.set(f"FreeCAD deneyi: {data['evaluation']['status']}. Kayıt: {path}")

            self.job(
                lambda: run_freecad_check(
                    executable,
                    cad_path,
                    directory,
                    cancel=self.cancel_event,
                    progress=self.messages.put,
                ),
                done=done,
                cancellable=True,
            )

    def report_current(self) -> None:
        """Açılışta alınmış mevcut model anlık görüntüsünü adaylarıyla raporlar."""
        if self.result is None:
            messagebox.showinfo(
                "Önce proje açın",
                "Ana çalışma alanında projeyi açıp bu pencereyi yeniden açın.",
                parent=self.window,
            )
            return
        directory = filedialog.askdirectory(parent=self.window, title="Model karşılaştırma raporu")
        if directory:
            self.job(export_comparison, [self.result], directory)

    def report_saved(self) -> None:
        """Birden fazla proje dosyasını kaynak görselden uydurmadan karşılaştırır."""
        paths = filedialog.askopenfilenames(
            parent=self.window, filetypes=[("Uygulama projeleri", "*.json")]
        )
        if paths:
            directory = filedialog.askdirectory(parent=self.window, title="Karşılaştırma sonuçları")
            if directory:
                self.job(compare_saved_projects, list(paths), directory)

    def job(self, function: Any, *args: Any, done: Any = None, cancellable: bool = False) -> None:
        """İşçiye widget taşımadan tek iş gönderir; sonucu ana döngüde yayımlar."""
        if self.future is not None:
            return
        self.cancel_event = Event()
        self.on_done = done
        self.future = self.executor.submit(function, *args)
        for button in self.actions:
            button.configure(state="disabled")
        self.cancel_button.configure(state="normal" if cancellable else "disabled")
        self.status.set("İşlem sürüyor…")
        self.window.after(80, self.poll)

    def poll(self) -> None:
        """Geçti sonucunu yalnız ürün raporundan okur; dosya oluşmasını geçiş saymaz."""
        if self.closed or self.future is None:
            return
        while not self.messages.empty():
            self.status.set(self.messages.get_nowait())
        if not self.future.done():
            self.window.after(80, self.poll)
            return
        future, self.future = self.future, None
        self.cancel_button.configure(state="disabled")
        for button in self.actions:
            button.configure(state="normal")
        try:
            value = future.result()
            self.status.set(
                f"İşlem tamamlandı: {value if isinstance(value, (Path, list)) else 'doğrulandı'}"
            )
            if self.on_done:
                self.on_done(value)
        except AnalysisCancelled as error:
            self.status.set(str(error))
        except Exception as error:
            self.status.set("İşlem başarısız; önceki çalışma korunuyor.")
            messagebox.showerror("İşlem tamamlanamadı", str(error), parent=self.window)

    def close(self, *, force: bool = False) -> None:
        """Kendi ürün sürecini iptal eder; kaydedilmemiş insan kayıtlarını açıkça korur."""
        if not force and (self.future is not None or not self._discard()):
            if self.future is not None:
                self.status.set("Önce yürüyen işin bitmesini bekleyin veya deneyi iptal edin.")
            return
        self.closed = True
        self.cancel_event.set()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.window.destroy()
