"""D: kurulum yolları ve gerçek kullanıcı öncesi görev kartları için Türkçe masaüstü sekmesi."""

import json
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .cad_setup import (
    EXECUTABLES,
    ProgramLocation,
    ProgramSettings,
    default_search_roots,
    freecad_command,
    launch_program,
    load_programs,
    readiness,
    save_programs,
    scan_programs,
)
from .pilot import METHODS, TASKS
from .pilot_pack import asset_path, build_pack, load_pack, task_instructions


class PreparationPanel:
    """Arka plan işçisini paylaşır; planı insan ölçümü veya uyumluluk sonucu saymaz."""

    def __init__(self, owner: Any, tab: ttk.Frame, workspace: Path) -> None:
        """Proje içindeki ayarları okur; kendiliğinden program başlatmaz veya taramaz."""
        self.owner, self.workspace = owner, workspace
        self.settings_path = workspace / "output/cad-programs.json"
        self.plan_path: Path | None = None
        self.plan: dict | None = None
        self.paths = {p: tk.StringVar() for p in EXECUTABLES}
        self.versions = {p: tk.StringVar() for p in EXECUTABLES}
        self.confirmed = {p: tk.BooleanVar(value=False) for p in EXECUTABLES}
        self.states = {p: tk.StringVar(value="Yol seçilmedi.") for p in EXECUTABLES}
        self._loading = False
        self._saved_settings = self._snapshot()
        heading = ttk.Label(
            tab,
            text="1. Programları hazırlayın · 2. Aynı hedeflerle denemeye başlayın",
            font=("Segoe UI", 12, "bold"),
        )
        heading.pack(anchor="w")
        ttk.Label(
            tab,
            text="AutoCAD ve SolidWorks'ü kendi lisans/erişiminizle D: üzerine kurabilirsiniz. Bulunan dosya, lisans veya içe alma başarısı anlamına gelmez. Gerçek sürümü ve ilk açılışı siz doğrulayın.",
            wraplength=1050,
        ).pack(anchor="w", pady=(6, 8))
        programs = ttk.Frame(tab)
        programs.pack(fill="x")
        programs.columnconfigure(1, weight=1)
        for row, product in enumerate(EXECUTABLES):
            ttk.Label(programs, text=product, width=12).grid(row=row * 2, column=0, sticky="w")
            ttk.Entry(programs, textvariable=self.paths[product]).grid(
                row=row * 2, column=1, sticky="ew", padx=5
            )
            owner._button(programs, "Dosya seç", lambda p=product: self.pick(p)).grid(
                row=row * 2, column=2, padx=3
            )
            owner._button(programs, "Programı aç", lambda p=product: self.launch(p)).grid(
                row=row * 2, column=3, padx=3
            )
            ttk.Entry(programs, textvariable=self.versions[product], width=14).grid(
                row=row * 2, column=4, padx=3
            )
            ttk.Checkbutton(
                programs,
                text="İlk açılışı yaptım",
                variable=self.confirmed[product],
                command=self.refresh,
            ).grid(row=row * 2, column=5)
            ttk.Label(programs, textvariable=self.states[product]).grid(
                row=row * 2 + 1, column=1, columnspan=5, sticky="w", pady=(0, 7)
            )
            self.paths[product].trace_add("write", lambda *_, p=product: self._path_changed(p))
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=5)
        for label, command in [
            ("Programları bul", self.scan),
            ("Yolları ve sürümleri kaydet", self.save),
            ("Hazırlık raporu kaydet", self.export_readiness),
        ]:
            owner._button(bar, label, command).pack(side="left", padx=(0, 5))
        ttk.Label(
            tab,
            text="Sürüm kutusuna programın Hakkında ekranındaki gerçek sürümü yazın. Ayarlar: "
            + str(self.settings_path),
            wraplength=1050,
        ).pack(anchor="w", pady=(0, 6))
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=5)
        for label, command in [
            ("Üç örnekli görev paketi oluştur", self.build),
            ("Görev planı aç", self.open_plan),
            ("Paket kılavuzunu aç", self.open_guide),
            ("Görevi pilot formuna aktar", self.apply_task),
        ]:
            owner._button(bar, label, command).pack(side="left", padx=(0, 5))
        ttk.Label(
            tab,
            text="İlk aşama: 18 içe alma görevi. Profil ve düzenlemeyle 54 planlı görev. Kişi ataması veya sonuç oluşmaz; başlangıç eğitim modudur.",
            wraplength=1050,
        ).pack(anchor="w", pady=4)
        panes = ttk.Panedwindow(tab, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left, right = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(left, weight=1)
        panes.add(right, weight=1)
        self.tasks = ttk.Treeview(
            left, columns=("order", "program", "case", "task", "method"), show="headings", height=9
        )
        for key, label, width in [
            ("order", "Sıra", 40),
            ("program", "Program", 85),
            ("case", "Örnek", 90),
            ("task", "Görev", 90),
            ("method", "Yöntem", 100),
        ]:
            self.tasks.heading(key, text=label)
            self.tasks.column(key, width=width, stretch=True)
        scrollbar = ttk.Scrollbar(left, command=self.tasks.yview)
        self.tasks.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tasks.pack(fill="both", expand=True)
        self.tasks.bind("<<TreeviewSelect>>", self.describe_task)
        self.details = tk.Text(right, wrap="word", height=9)
        details_scroll = ttk.Scrollbar(right, command=self.details.yview)
        self.details.configure(yscrollcommand=details_scroll.set)
        details_scroll.pack(side="right", fill="y")
        self.details.pack(fill="both", expand=True, padx=(6, 0))
        try:
            self.set_settings(load_programs(self.settings_path))
        except (ValueError, OSError) as error:
            self.details.insert(
                "1.0",
                f"Kayıtlı program ayarları okunamadı: {error}\nDosya korunuyor. Yolları tekrar seçip açıkça kaydedebilirsiniz.",
            )

    def settings(self) -> ProgramSettings:
        """Widget değerlerini doğrulanabilir, çalıştırılabilir içerik taşımayan kayda çevirir."""
        return ProgramSettings(
            {
                p: ProgramLocation(
                    self.paths[p].get().strip(),
                    self.versions[p].get().strip(),
                    self.confirmed[p].get(),
                )
                for p in EXECUTABLES
            }
        )

    def _snapshot(self) -> tuple:
        """Kaydedilmemiş yol/sürüm beyanını doğrulama yapmadan karşılaştırır."""
        return tuple(
            (self.paths[p].get(), self.versions[p].get(), self.confirmed[p].get())
            for p in EXECUTABLES
        )

    @property
    def dirty(self) -> bool:
        """Program hazırlığı kaydedilmeden pencere kapanışında uyarılmasını sağlar."""
        return self._snapshot() != self._saved_settings

    def set_settings(self, settings: ProgramSettings) -> None:
        """Yükleme sırasında operatörün eski ilk açılış beyanını yanlışlıkla silmez."""
        self._loading = True
        for product, location in settings.programs.items():
            self.paths[product].set(location.path)
            self.versions[product].set(location.version)
            self.confirmed[product].set(location.first_launch_confirmed)
        self._loading = False
        self._saved_settings = self._snapshot()
        self.refresh()
        if settings.programs["FreeCAD"].path:
            self.owner.freecad_path.set(freecad_command(settings))

    def _path_changed(self, product: str) -> None:
        """Başka kuruluma geçildiğinde önceki sürüm/ilk açılış onayını taşımayı önler."""
        if not self._loading:
            self.confirmed[product].set(False)
            self.versions[product].set("")
            if product == "FreeCAD":
                self.owner.freecad_path.set(freecad_command(self.settings()))
            self.refresh()

    def refresh(self) -> None:
        """Yalnız dosya varlığı ve operatör onayını gösterir; uyumluluk iddiası üretmez."""
        for product in EXECUTABLES:
            path = self.paths[product].get().strip()
            exists = bool(
                path and Path(path).is_file() and Path(path).name.casefold() == EXECUTABLES[product]
            )
            text = (
                "Dosya bulundu; ilk açılış/sürüm onayı bekleniyor."
                if exists
                else "Program yolu bulunamadı; kurulum veya Dosya seç gerekli."
            )
            if exists and self.confirmed[product].get() and self.versions[product].get().strip():
                text = "Operatör açılışı onayladı; gerçek görev/uyumluluk henüz doğrulanmadı."
            self.states[product].set(text)

    def pick(self, product: str) -> None:
        """D: dahil kullanıcının kendi kurulumundaki GUI programını seçer."""
        path = filedialog.askopenfilename(
            parent=self.owner.window,
            title=f"{product}: {EXECUTABLES[product]} seçin",
            initialdir="D:/",
            filetypes=[("CAD programı", "*.exe")],
        )
        if path:
            self.paths[product].set(path)

    def scan(self) -> None:
        """Bilinen kurulum köklerini arka planda sınırlı tarar; dolu yolları değiştirmez."""

        def done(found: dict) -> None:
            for product, paths in found.items():
                if paths and not self.paths[product].get().strip():
                    self.paths[product].set(paths[-1])
            self.owner.status.set(
                "Sınırlı tarama tamamlandı. Bulunamayan kurulumları Dosya seç ile gösterebilirsiniz."
            )
            self.details.delete("1.0", "end")
            self.details.insert("1.0", json.dumps(found, ensure_ascii=False, indent=2))

        self.owner.job(
            lambda: scan_programs(
                default_search_roots(self.workspace),
                cancel=self.owner.cancel_event,
                progress=self.owner.messages.put,
            ),
            done=done,
            cancellable=True,
        )

    def save(self) -> None:
        """Yol/sürüm beyanlarını proje içindeki yerel ayar dosyasına kaydeder."""
        try:
            settings = self.settings()
            settings.validate()
            snapshot = self._snapshot()

            def done(_: Path) -> None:
                self._saved_settings = snapshot
                self.refresh()
                if self.paths["FreeCAD"].get().strip() == settings.programs["FreeCAD"].path:
                    self.owner.freecad_path.set(freecad_command(settings))

            self.owner.job(
                save_programs,
                settings,
                self.settings_path,
                done=done,
            )
        except ValueError as error:
            messagebox.showerror("Program ayarları", str(error), parent=self.owner.window)

    def export_readiness(self) -> None:
        """Gerçek yerel dosya kontrolünü başarı/insan sonucu içermeyen JSON'a yazar."""
        from .pilot import atomic_text

        try:
            data = readiness(self.settings())
            path = filedialog.asksaveasfilename(
                parent=self.owner.window, defaultextension=".json", initialfile="cad-hazirlik.json"
            )
            if path:
                self.owner.job(
                    atomic_text,
                    path,
                    json.dumps(data, ensure_ascii=False, indent=2),
                    lambda p: json.loads(p.read_text(encoding="utf8")),
                )
        except (ValueError, OSError) as error:
            messagebox.showerror("Hazırlık raporu", str(error), parent=self.owner.window)

    def launch(self, product: str) -> None:
        """Yalnız açık düğme eyleminde GUI'yi açar; belge, makro veya kurucu yüklemez."""
        try:
            launch_program(product, self.paths[product].get().strip())
            self.owner.status.set(
                f"{product} başlatma isteği gönderildi. İlk açılışı ve gerçek sürümü program içinde kontrol edin."
            )
        except (ValueError, OSError) as error:
            messagebox.showerror("Program açılamadı", str(error), parent=self.owner.window)

    def build(self) -> None:
        """Aynı üç kayıtlı örnekten gerçek dokuz CAD dosyasını arka planda üretir."""
        source = self.workspace / "examples/cad_product_validation"
        if not source.is_dir():
            selected = filedialog.askdirectory(
                parent=self.owner.window,
                title="circle, ring, mixed model.json örneklerinin klasörü",
            )
            if not selected:
                return
            source = Path(selected)
        target = filedialog.askdirectory(
            parent=self.owner.window, title="Yeni görev paketi için çıktı klasörü"
        )
        if target:
            self.owner.job(
                lambda: build_pack(
                    source, target, cancel=self.owner.cancel_event, progress=self.owner.messages.put
                ),
                done=self._built,
                cancellable=True,
            )

    def _built(self, path: Path) -> None:
        """İşçinin doğruladığı planı ana olay döngüsünde yüklemeye alır."""
        self.owner.job(load_pack, path, done=lambda data: self.set_plan(path, data))

    def open_plan(self) -> None:
        """Taşınmış paketin bağıl yollarını/hash'lerini doğrular; önceki planı korur."""
        path = filedialog.askopenfilename(
            parent=self.owner.window,
            title="plan.json görev planını açın",
            filetypes=[("Görev planı", "*.json")],
        )
        if path:
            self.owner.job(load_pack, path, done=lambda data: self.set_plan(Path(path), data))

    def set_plan(self, path: Path, plan: dict) -> None:
        """Gözlem sayısını değiştirmeden görevleri gösterir."""
        self.plan_path, self.plan = Path(path), plan
        self.tasks.delete(*self.tasks.get_children())
        for task in plan["tasks"]:
            self.tasks.insert(
                "",
                "end",
                iid=task["id"],
                values=(
                    task["order"],
                    task["product"],
                    plan["cases"][task["case"]]["label"],
                    TASKS[task["task"]],
                    METHODS[task["method"]],
                ),
            )
        self.tasks.selection_set(plan["tasks"][0]["id"])
        self.describe_task()
        self.owner.status.set(f"54 planlı görev yüklendi; insan sonucu oluşmadı. {path}")

    def selected_task(self) -> dict | None:
        """Seçili plan görevini döndürür; otomatik deneme veya başarı oluşturmaz."""
        selected = self.tasks.selection()
        return (
            next((t for t in self.plan["tasks"] if t["id"] == selected[0]), None)
            if self.plan and selected
            else None
        )

    def describe_task(self, *_: Any) -> None:
        """Denklem/katsayı dosyası ile ölçüm kapsamını seçili görevde gösterir."""
        if (task := self.selected_task()) and self.plan is not None:
            case = self.plan["cases"][task["case"]]
            self.details.delete("1.0", "end")
            self.details.insert(
                "1.0",
                task_instructions(self.plan, task)
                + "\n\nCAD dosyası: "
                + case["cad"][task["format"]]
                + "\nHedef katsayıları: "
                + case["parameters"]
                + "\nTüm denklemler, model/kaynak önizlemesi ve dosya bağlantıları Paket kılavuzunu aç düğmesindedir.",
            )

    def apply_task(self) -> None:
        """Hash'leri tekrar işçide denetleyip yalnız ardından ölçüm formunu doldurur."""
        task = self.selected_task()
        if task and self.plan_path:
            path, task_id = self.plan_path, task["id"]

            def done(plan: dict) -> None:
                selected = next(t for t in plan["tasks"] if t["id"] == task_id)
                self.owner.apply_planned_task(plan, selected, path, self.settings())

            self.owner.job(load_pack, path, done=done)

    def open_guide(self) -> None:
        """Değiştirilmiş HTML'i açmadan önce paket hash'lerini arka planda kontrol eder."""
        if self.plan_path:
            path = self.plan_path
            self.owner.job(
                load_pack,
                path,
                done=lambda _: webbrowser.open(asset_path(path, "index.html").as_uri()),
            )
