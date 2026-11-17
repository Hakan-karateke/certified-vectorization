"""Türkçe Tkinter çalışma alanı; analiz ve kayıt işlerini arka planda yürütür."""

import gc
import json
import queue
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from tkinter import filedialog, messagebox, ttk
from typing import Any

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from PIL import Image, ImageOps

from .cad_geometry import CadOptions
from .curves import equation
from .export import ExportOptions, equation_report, export_result, make_figure
from .fitting import AnalysisCancelled
from .imaging import normalize_image
from .models import AnalysisConfig, AnalysisResult
from .pipeline import analyze
from .project import choose_candidate, load_project, save_project

FAMILIES = {
    "Otomatik karma model": "auto",
    "Kesin piksel sınırı": "exact",
    "Çokgen sadeleştirme": "polygon",
    "Çember": "circle",
    "Elips": "ellipse",
    "Kübik Bézier": "bezier",
    "Kübik B-spline": "bspline",
    "Konik yaylı karma": "mixed",
    "Köşe farkındalıklı karma": "adaptive",
    "Kapalı Fourier serisi": "fourier",
    "Temasları koruyan çokgen": "topology",
    "En az kenarlı çokgen (kanıtlı)": "minlink",
    "En az parçalı doğru + yay (kanıtlı)": "linearc",
}
SEARCHES = {"Deterministik aday grafiği": "deterministic", "Bütçeli simüle tavlama": "annealing"}
CERTIFICATES = {
    "Seçili modeli kanıtlamayı dene": "selected",
    "Sertifikalı sonuç zorunlu": "strict",
    "Yalnızca sayısal ölçüm": "off",
}
PREFERENCES = {"Dengeli": "balanced", "Daha sade": "simple", "Daha yüksek doğruluk": "accurate"}
VIEWS = {
    "Üst üste karşılaştırma": "overlay",
    "Kaynak görsel": "source",
    "Normalize görsel": "normalized",
    "Referans sınır": "reference",
    "Matematiksel model": "model",
    "Hata dağılımı": "error",
}


class AnalysisWindow:
    """Tek işçili, iptal edilebilir masaüstü analiz ve yeniden açma akışını yönetir.

    Widget erişimi yalnızca ana iş parçacığındadır. İşçi sonuçları poll üzerinden
    atomik yayımlanır; iptal/başarısızlık son başarılı projeyi değiştirmez.
    """

    def __init__(self, root: tk.Tk) -> None:
        """Pencereyi ve başlangıç durumunu oluşturur; yerel analiz başlatmaz."""
        self.root = root
        self.result: AnalysisResult | None = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future: Future | None = None
        self.operation = ""
        self.cancel_event = Event()
        self.messages: queue.Queue[str] = queue.Queue()
        self.canvas: FigureCanvasTkAgg | None = None
        self.toolbar: NavigationToolbar2Tk | None = None
        self.closed = False
        self.image = tk.StringVar()
        self.threshold = tk.StringVar(value="127")
        self.padding = tk.StringVar(value="20")
        self.tolerance = tk.StringVar(value="2")
        self.family = tk.StringVar(value="Otomatik karma model")
        self.preference = tk.StringVar(value="Dengeli")
        self.degree = tk.StringVar(value="Kapalı")
        self.spacing = tk.StringVar(value="1")
        self.embed = tk.BooleanVar(value=False)
        self.search = tk.StringVar(value="Deterministik aday grafiği")
        self.certificate = tk.StringVar(value="Seçili modeli kanıtlamayı dene")
        self.search_budget = tk.StringVar(value="20")
        self.seed = tk.StringVar(value="20261015")
        self.workers = tk.StringVar(value="1")
        self.view = tk.StringVar(value="Üst üste karşılaştırma")
        self.status = tk.StringVar(value="Görsel açın, ön işlemeyi inceleyin ve modeli hesaplayın.")
        self.controls = []
        root.title("Şekilden Denkleme · Araştırma çalışma alanı")
        initial_width = min(1380, root.winfo_screenwidth() - 60)
        initial_height = min(900, root.winfo_screenheight() - 100)
        root.geometry(f"{initial_width}x{initial_height}")
        root.minsize(1000, 650)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TButton", padding=(10, 6))
        style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"), foreground="#173b52")
        style.configure("Hint.TLabel", foreground="#526476")
        style.configure("Treeview", rowheight=26)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Şekilden Denkleme", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text="Yerel geometrik analiz  /  kaynak piksel birimi  /  ölçülmüş hata ve model karmaşıklığı",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 12))
        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 12))
        ttk.Entry(top, textvariable=self.image).pack(side="left", fill="x", expand=True)
        for label, command in [
            ("Görsel aç", self.choose_image),
            ("Proje aç", self.open_project),
            ("Projeyi kaydet", self.save_project_dialog),
        ]:
            button = ttk.Button(top, text=label, command=command)
            button.pack(side="left", padx=(8, 0))
            self.controls.append(button)
        panes = ttk.Panedwindow(frame, orient="horizontal")
        panes.pack(fill="both", expand=True)
        sidehost = ttk.Frame(panes, width=310)
        sidecanvas = tk.Canvas(
            sidehost,
            width=286,
            highlightthickness=0,
            background=style.lookup("TFrame", "background"),
        )
        sidescroll = ttk.Scrollbar(sidehost, orient="vertical", command=sidecanvas.yview)
        sidecanvas.configure(yscrollcommand=sidescroll.set)
        sidescroll.pack(side="right", fill="y")
        sidecanvas.pack(side="left", fill="both", expand=True)
        sidebar = ttk.Frame(sidecanvas, padding=(0, 0, 12, 0))
        sidewindow = sidecanvas.create_window((0, 0), window=sidebar, anchor="nw")
        sidebar.bind(
            "<Configure>", lambda _: sidecanvas.configure(scrollregion=sidecanvas.bbox("all"))
        )
        sidecanvas.bind(
            "<Configure>", lambda event: sidecanvas.itemconfigure(sidewindow, width=event.width)
        )

        def scroll_sidebar(event: tk.Event) -> None:
            """Yalnızca ayarlar alanındaki fare tekerleğini kaydırmaya yönlendirir."""
            if str(event.widget).startswith(str(sidehost)):
                sidecanvas.yview_scroll(-int(event.delta / 120), "units")

        root.bind("<MouseWheel>", scroll_sidebar, add="+")
        content = ttk.Frame(panes)
        panes.add(sidehost, weight=0)
        panes.add(content, weight=1)
        ttk.Label(sidebar, text="Analiz ayarları", font=("Segoe UI", 12, "bold")).pack(
            anchor="w", pady=(0, 8)
        )
        for label, var, values in [
            ("Siyah eşiği (0..254)", self.threshold, None),
            ("Kenar boşluğu (birim)", self.padding, None),
            ("Geometrik hata toleransı ε (birim)", self.tolerance, None),
            ("Model ailesi", self.family, list(FAMILIES)),
            ("Sadelik / doğruluk tercihi", self.preference, list(PREFERENCES)),
            ("En büyük ölçüm aralığı (birim)", self.spacing, None),
            ("Keşif: örtük polinom derecesi", self.degree, ["Kapalı", *map(str, range(2, 13))]),
            ("Arama stratejisi", self.search, list(SEARCHES)),
            ("Tavlama aday bütçesi (4..100)", self.search_budget, None),
            ("Rastgelelik tohumu", self.seed, None),
            ("CPU değerlendirme işçileri", self.workers, ["1", "2", "4", "8"]),
            ("Hata ve topoloji sertifikası", self.certificate, list(CERTIFICATES)),
        ]:
            ttk.Label(sidebar, text=label).pack(anchor="w", pady=(5, 2))
            widget = (
                ttk.Combobox(sidebar, textvariable=var, values=values, state="readonly")
                if values
                else ttk.Entry(sidebar, textvariable=var)
            )
            widget.pack(fill="x")
        ttk.Checkbutton(sidebar, text="Kaynak görseli projeye göm", variable=self.embed).pack(
            anchor="w", pady=9
        )
        self.preview_button = ttk.Button(
            sidebar, text="Ön işleme önizlemesi", command=self.preview_preprocessing
        )
        self.preview_button.pack(fill="x", pady=3)
        self.run_button = ttk.Button(sidebar, text="Modelleri hesapla", command=self.run)
        self.run_button.pack(fill="x", pady=3)
        self.cancel_button = ttk.Button(
            sidebar, text="İptal", command=self.cancel, state="disabled"
        )
        self.cancel_button.pack(fill="x", pady=3)
        self.save_button = ttk.Button(
            sidebar, text="PDF · PNG · JPEG · SVG dışa aktar", command=self.save, state="disabled"
        )
        self.save_button.pack(fill="x", pady=3)
        self.cad_button = ttk.Button(
            sidebar, text="CAD: STEP · IGES · DXF", command=self.save_cad, state="disabled"
        )
        self.cad_button.pack(fill="x", pady=3)
        pilot_button = ttk.Button(
            sidebar, text="Araştırma · üç CAD pilotu", command=self.open_pilot
        )
        pilot_button.pack(fill="x", pady=3)
        self.controls.append(pilot_button)
        ttk.Button(
            sidebar, text="Doğrulama veri kümesini çalıştır", command=self.run_benchmark
        ).pack(fill="x", pady=3)
        ttk.Button(
            sidebar, text="Karmaşık veri · 40 × 4 tolerans taraması", command=self.run_stress
        ).pack(fill="x", pady=3)
        ttk.Label(
            sidebar,
            text="ε=0: kesin piksel sınırı.\n\nYaklaşık model, ölçülen mesafe ve hesaplanan üst sınırla değerlendirilir. Eğri topolojisi kontrollü poligonda denetlenir.\n\nKalın çizginin alan sınırı çıkarılır. Merkez hattı ve isteğe bağlı morfoloji bu sürümde yoktur.",
            wraplength=280,
            style="Hint.TLabel",
        ).pack(anchor="w", pady=14)
        self.notebook = ttk.Notebook(content)
        self.notebook.pack(fill="both", expand=True)
        chart = ttk.Frame(self.notebook)
        candidates_tab = ttk.Frame(self.notebook, padding=8)
        parts_tab = ttk.Frame(self.notebook, padding=8)
        report_tab = ttk.Frame(self.notebook)
        self.notebook.add(chart, text="Görsel çalışma alanı")
        self.notebook.add(candidates_tab, text="Aday karşılaştırması")
        self.notebook.add(parts_tab, text="Parçalar ve denklemler")
        self.notebook.add(report_tab, text="Akademik rapor")
        viewbar = ttk.Frame(chart, padding=6)
        viewbar.pack(fill="x")
        ttk.Label(viewbar, text="Görünüm").pack(side="left", padx=(0, 8))
        combo = ttk.Combobox(
            viewbar, textvariable=self.view, values=list(VIEWS), state="readonly", width=30
        )
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _: self.draw())
        self.preview = ttk.Frame(chart)
        self.preview.pack(fill="both", expand=True)
        self.candidate_tree = ttk.Treeview(
            candidates_tab,
            columns=("id", "pieces", "bits", "upper", "rms", "topology", "pareto", "accept"),
            show="headings",
            height=13,
        )
        for key, label, width in [
            ("id", "Aday", 130),
            ("pieces", "Parça", 60),
            ("bits", "Bit", 80),
            ("upper", "H üst sınır", 90),
            ("rms", "RMS", 80),
            ("topology", "Topoloji*", 85),
            ("pareto", "Pareto", 65),
            ("accept", "Durum", 65),
        ]:
            self.candidate_tree.heading(key, text=label)
            self.candidate_tree.column(key, width=width, stretch=True)
        self.candidate_tree.pack(fill="both", expand=True)
        self.candidate_tree.bind("<<TreeviewSelect>>", self.inspect_candidate)
        self.candidate_tree.bind("<Double-1>", lambda _: self.use_candidate())
        ttk.Button(
            candidates_tab, text="Seçili kabul edilmiş modeli kullan", command=self.use_candidate
        ).pack(anchor="w", pady=8)
        self.candidate_detail = tk.Text(
            candidates_tab, height=10, wrap="word", font=("Consolas", 10)
        )
        self.candidate_detail.pack(fill="x")
        ttk.Label(
            candidates_tab,
            text="* Geçti: kontrollü poligon. Kanıt: analitik topoloji yeter koşulları sağlandı. Hata sertifikası ayrı raporlanır.",
            wraplength=850,
            style="Hint.TLabel",
        ).pack(anchor="w", pady=4)
        self.piece_tree = ttk.Treeview(
            parts_tab,
            columns=("index", "kind", "boundary", "interval", "error"),
            show="headings",
            height=8,
        )
        for key, label in [
            ("index", "Parça"),
            ("kind", "Tür"),
            ("boundary", "Sınır / bileşen"),
            ("interval", "Parametre aralığı"),
            ("error", "Halka H üst"),
        ]:
            self.piece_tree.heading(key, text=label)
            self.piece_tree.column(key, width=130)
        scrollbar = ttk.Scrollbar(parts_tab, command=self.piece_tree.yview)
        self.piece_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.piece_tree.pack(fill="both", expand=True)
        self.piece_tree.bind("<<TreeviewSelect>>", self.inspect_piece)
        self.piece_detail = tk.Text(parts_tab, height=13, wrap="word", font=("Consolas", 10))
        self.piece_detail.pack(fill="x", pady=8)
        self.text = tk.Text(report_tab, wrap="word", font=("Consolas", 10))
        scroll = ttk.Scrollbar(report_tab, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(10, 4))
        ttk.Label(frame, textvariable=self.status, wraplength=1250).pack(anchor="w")

    def config(self) -> AnalysisConfig:
        """Widget değerlerinin tek bir doğrulanmış analiz anlık görüntüsünü alır."""
        return AnalysisConfig(
            threshold=int(self.threshold.get()),
            padding=int(self.padding.get()),
            tolerance=float(self.tolerance.get()),
            degree=None if self.degree.get() == "Kapalı" else int(self.degree.get()),
            family=FAMILIES[self.family.get()],
            preference=PREFERENCES[self.preference.get()],
            evaluation_spacing=float(self.spacing.get()),
            embed_input=self.embed.get(),
            search_strategy=SEARCHES[self.search.get()],
            search_budget=int(self.search_budget.get()),
            random_seed=int(self.seed.get()),
            evaluation_workers=int(self.workers.get()),
            certificate_mode=CERTIFICATES[self.certificate.get()],
        )

    def choose_image(self) -> None:
        """Yerel raster dosyasını seçer; kaynak yolu proje modelinden bağımsızdır."""
        path = filedialog.askopenfilename(
            filetypes=[
                ("Raster görseller", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"),
                ("Tüm dosyalar", "*"),
            ]
        )
        if path:
            self.image.set(path)
            self.preview_preprocessing()

    def start_job(self, operation: str, function: Any, *args: Any, **kwargs: Any) -> None:
        """Tek iş gönderir; widget ve sonuç değişikliklerini ana döngüye bırakır."""
        if self.future is not None:
            return
        self.operation = operation
        self.cancel_event = Event()
        self.future = self.executor.submit(function, *args, **kwargs)
        self.run_button.configure(state="disabled")
        self.preview_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.cad_button.configure(state="disabled")
        for button in self.controls:
            button.configure(state="disabled")
        self.cancel_button.configure(
            state="normal" if operation in {"analyze", "benchmark", "select"} else "disabled"
        )
        self.progress.start(12)
        self.status.set("İşlem sürüyor…")
        self.root.after(80, self.poll)

    def run(self) -> None:
        """Analizi başlatır; uzun hesaplama Tk iş parçacığını kilitlemez."""
        if self.future is not None:
            return
        try:
            config = self.config()
            if not self.image.get().strip():
                raise ValueError("Önce bir görsel açın.")
            # start_job kendi olayını kurar; işçiye aynı olay aktarılmalıdır.
            self.start_job("analyze", self._analyze_job, Path(self.image.get()), config)
        except ValueError as error:
            messagebox.showerror("Geçersiz ayar", str(error))

    def _analyze_job(self, path: Path, config: AnalysisConfig) -> AnalysisResult:
        """İşçiden yalnızca kuyruk ile ilerleme bildirir; widget'a erişmez."""
        return analyze(path, config, cancel=self.cancel_event, progress=self.messages.put)

    def preview_preprocessing(self) -> None:
        """Kaynak ve normalize eşikleme görüntüsünü yan yana, analizden önce sunar."""
        if self.future is not None or not self.image.get():
            return
        try:
            config = self.config()
        except ValueError as error:
            messagebox.showerror("Geçersiz ayar", str(error))
            return
        path = self.image.get()

        def work():
            """Dosya okuma ve ön işlemeyi arka planda tamamlar."""
            mask, metadata = normalize_image(
                path, config.threshold, config.padding, config.working_size or None
            )
            with Image.open(path) as source:
                rgba = ImageOps.exif_transpose(source).convert("RGBA")
                image = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba).convert(
                    "RGB"
                )
            return image, mask, metadata

        self.start_job("preview", work)

    def open_project(self) -> None:
        """Kaydedilmiş modeli yeniden uydurmadan açar; taşınmış kaynak açıklanır."""
        if self.future is not None:
            return
        path = filedialog.askopenfilename(filetypes=[("Şekilden Denkleme projesi", "*.json")])
        if path:
            self.start_job("load", load_project, path)

    def save_project_dialog(self) -> None:
        """Kullanıcının seçtiği JSON hedefine doğrulamalı proje kaydeder."""
        if self.result is None or self.future is not None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("Proje JSON", "*.json")]
        )
        if path:
            self.start_job("project_save", save_project, self.result, path)

    def cancel(self) -> None:
        """İptal olayını işaretler; son başarılı sonuç korunur."""
        self.cancel_event.set()
        self.status.set("İptal isteniyor; yürüyen sayısal adımın bitmesi bekleniyor…")

    def poll(self) -> None:
        """İşçi kuyruğunu okur; tamamlanan sonucu tek seferde yayımlar."""
        if self.closed or self.future is None:
            return
        while True:
            try:
                self.status.set(self.messages.get_nowait())
            except queue.Empty:
                break
        if not self.future.done():
            self.root.after(80, self.poll)
            return
        future, self.future = self.future, None
        self.progress.stop()
        self.run_button.configure(state="normal")
        self.preview_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        for button in self.controls:
            button.configure(state="normal")
        try:
            value = future.result()
            if self.cancel_event.is_set() and self.operation in {"analyze", "benchmark"}:
                raise AnalysisCancelled("İşlem iptal edildi; önceki model korunuyor.")
            if self.operation in {"analyze", "load", "select"}:
                self.set_result(value)
            elif self.operation == "preview":
                image, mask, metadata = value
                fig = Figure(figsize=(10, 5), dpi=110, layout="tight")
                a, b = fig.subplots(1, 2)
                a.imshow(image)
                a.set_title("Kaynak · EXIF düzeltilmiş")
                a.set_axis_off()
                b.imshow(np.where(mask, 0, 255), cmap="gray", vmin=0, vmax=255)
                b.set_title("Normalize · eşikleme + nearest")
                b.set_axis_off()
                self.show_figure(fig)
                self.notebook.select(0)
                self.status.set(
                    f"Ön izleme: {metadata['foreground_pixels']} siyah piksel. Geometriyi değiştiren morfoloji uygulanmadı."
                )
            else:
                self.status.set(f"Dosyalar üretildi ve yeniden açılarak doğrulandı: {value}")
        except AnalysisCancelled as error:
            self.status.set(str(error))
        except Exception as error:
            self.status.set("İşlem başarısız; önceki sonuç kullanılabilir.")
            messagebox.showerror("İşlem tamamlanamadı", str(error))
        self.save_button.configure(state="normal" if self.result else "disabled")
        self.cad_button.configure(state="normal" if self.result else "disabled")

    def set_result(self, result: AnalysisResult) -> None:
        """Başarılı projeyi, adayları ve parça listesini ekranda yeniler."""
        self.result = result
        self.save_button.configure(state="normal")
        self.cad_button.configure(state="normal")
        cfg = result.config
        self.threshold.set(str(cfg.threshold))
        self.padding.set(str(cfg.padding))
        self.tolerance.set(str(cfg.tolerance))
        self.family.set(next(k for k, v in FAMILIES.items() if v == cfg.family))
        self.preference.set(next(k for k, v in PREFERENCES.items() if v == cfg.preference))
        self.spacing.set(str(cfg.evaluation_spacing))
        self.degree.set(str(cfg.degree) if cfg.degree else "Kapalı")
        self.embed.set(cfg.embed_input)
        self.search.set(next(k for k, v in SEARCHES.items() if v == cfg.search_strategy))
        self.certificate.set(next(k for k, v in CERTIFICATES.items() if v == cfg.certificate_mode))
        self.search_budget.set(str(cfg.search_budget))
        self.seed.set(str(cfg.random_seed))
        self.workers.set(str(cfg.evaluation_workers))
        self.image.set(result.provenance.get("source_path", ""))
        self.candidate_tree.delete(*self.candidate_tree.get_children())
        for c in result.candidates:
            upper = c.metrics.get("hausdorff_upper_bound")
            rms = c.metrics.get("rms")
            topology = c.metrics.get("topology", {}).get("preserved", False)
            self.candidate_tree.insert(
                "",
                "end",
                iid=c.id,
                values=(
                    c.id,
                    len(c.pieces),
                    c.complexity.get("score_bits", "-"),
                    f"{upper:.5g}" if upper is not None else "-",
                    f"{rms:.5g}" if rms is not None else "-",
                    "Kanıt"
                    if c.metrics.get("topology", {}).get("analytic_isotopy_proven")
                    else "Geçti*"
                    if topology or c.family == "exact"
                    else "Ret",
                    "Evet" if c.pareto else "-",
                    "Kabul" if c.accepted else "Ret",
                ),
            )
        self.candidate_tree.selection_set(result.selected_id)
        self.refresh_model()
        warnings = result.provenance.get("load_warnings", [])
        self.status.set(
            f"{result.selected_id} · {len(result.selected.pieces)} parça · H üst={result.selected.metrics['hausdorff_upper_bound']:.5g} · "
            f"{result.metrics['outer_count']} bileşen / {result.metrics['hole_count']} boşluk. "
            f"Sertifika: {result.selected.metrics.get('certification', {}).get('status', 'kapalı')}. "
            + " ".join(warnings)
        )

    def refresh_model(self) -> None:
        """Aynı projedeki seçilen adayın denklem ve çizimini yeniler."""
        if self.result is None:
            return
        self.text.delete("1.0", "end")
        self.text.insert("1.0", equation_report(self.result))
        self.piece_tree.delete(*self.piece_tree.get_children())
        for i, p in enumerate(self.result.selected.pieces):
            self.piece_tree.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    i + 1,
                    p.kind,
                    f"{p.boundary_id} / {p.component_id}",
                    f"[{p.interval[0]:.6g}, {p.interval[1]:.6g}]",
                    f"{p.errors.get('hausdorff_upper_bound', 0):.5g}",
                ),
            )
        self.draw()

    def show_figure(self, figure: Figure) -> None:
        """Eski tuval kaynaklarını bırakıp yeni figürü Tk alanına yerleştirir."""
        if self.canvas:
            # Figure.clear araç çubuğuna güncelleme bildirir; düğmeler hâlâ
            # mevcutken temizlemek Tk'da geçersiz widget başvurusunu önler.
            self.canvas.figure.clear()
        if self.toolbar:
            self.toolbar.destroy()
        if self.canvas:
            self.canvas.get_tk_widget().destroy()
        self.canvas = FigureCanvasTkAgg(figure, master=self.preview)
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.preview, pack_toolbar=False)
        self.toolbar.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.draw()
        # Tk PhotoImage döngülerini sonraki sayısal işçinin çöp toplayıcısına
        # bırakmamak, görüntü kaynaklarının ana iş parçacığında kapanmasını sağlar.
        gc.collect()

    def draw(self, selected_piece: int | None = None) -> None:
        """Kaydedilmiş katsayıları seçilen görünümde çizer; uydurma yapmaz."""
        if self.result:
            self.show_figure(
                make_figure(self.result, view=VIEWS[self.view.get()], selected_piece=selected_piece)
            )

    def inspect_candidate(self, _event: Any = None) -> None:
        """Adayın kabul/ret gerekçesi ve bütün ölçümlerini gösterir."""
        if not self.result or not self.candidate_tree.selection():
            return
        c = next(c for c in self.result.candidates if c.id == self.candidate_tree.selection()[0])
        self.candidate_detail.delete("1.0", "end")
        self.candidate_detail.insert(
            "1.0",
            json.dumps(
                {
                    "id": c.id,
                    "ret_nedenleri": c.reasons,
                    "karmaşıklık": c.complexity,
                    "ölçümler": c.metrics,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    def use_candidate(self) -> None:
        """Kayıtlı adayı arka planda yeniden ölçer; sertifika arayüzü kilitlemez."""
        if not self.result or not self.candidate_tree.selection() or self.future is not None:
            return
        candidate_id = self.candidate_tree.selection()[0]
        candidate = next(c for c in self.result.candidates if c.id == candidate_id)
        if not candidate.accepted:
            messagebox.showinfo("Aday seçilemedi", "Reddedilmiş model seçilemez.")
            return
        result = self.result

        def work() -> AnalysisResult:
            """Önceki başarılı sonuç ve widget'ları değiştirmeden seçimi doğrular."""
            updated = choose_candidate(result, candidate_id)
            return replace(
                updated,
                provenance={
                    **updated.provenance,
                    "selection_reason": "Kullanıcı kabul edilmiş adayı karşılaştırma tablosundan seçti.",
                },
            )

        self.start_job("select", work)

    def inspect_piece(self, _event: Any = None) -> None:
        """Parça denklemi/aralığını gösterir ve şekil üzerinde turuncu vurgular."""
        if not self.result or not self.piece_tree.selection():
            return
        index = int(self.piece_tree.selection()[0])
        p = self.result.selected.pieces[index]
        self.piece_detail.delete("1.0", "end")
        self.piece_detail.insert(
            "1.0", equation(p) + "\n\n" + json.dumps(p.__dict__, ensure_ascii=False, indent=2)
        )
        self.draw(index)

    def save(self) -> None:
        """Dört gerçek çıktı biçimi ve proje için seçenek iletişim kutusu açar."""
        if self.result is None or self.future is not None:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Dışa aktarım seçenekleri")
        dialog.geometry("510x660")
        dialog.transient(self.root)
        box = ttk.Frame(dialog, padding=20)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="Biçimler ve çizim", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        formats = {
            k: tk.BooleanVar(value=True) for k in ("pdf", "png", "jpeg", "svg", "json", "txt")
        }
        row = ttk.Frame(box)
        row.pack(fill="x", pady=12)
        for k, v in formats.items():
            ttk.Checkbutton(row, text=k.upper(), variable=v).pack(side="left")
        size = tk.StringVar(value="1600")
        dpi = tk.StringVar(value="160")
        quality = tk.StringVar(value="95")
        orient = tk.StringVar(value="Dikey")
        background = tk.StringVar(value="white")
        for label, var in [
            ("Kare çıktı kenarı (piksel)", size),
            ("DPI", dpi),
            ("JPEG kalitesi (1..100)", quality),
        ]:
            ttk.Label(box, text=label).pack(anchor="w", pady=(7, 2))
            ttk.Entry(box, textvariable=var).pack(fill="x")
        ttk.Label(box, text="A4 yönü").pack(anchor="w", pady=(7, 2))
        ttk.Combobox(box, textvariable=orient, values=["Dikey", "Yatay"], state="readonly").pack(
            fill="x"
        )
        ttk.Label(box, text="Arka plan (JPEG her zaman opaktır)").pack(anchor="w", pady=(7, 2))
        ttk.Combobox(
            box, textvariable=background, values=["white", "#f4f6fa"], state="readonly"
        ).pack(fill="x")
        flags = {
            "annotated": tk.BooleanVar(value=True),
            "transparent": tk.BooleanVar(value=False),
            "grid": tk.BooleanVar(value=True),
            "axes": tk.BooleanVar(value=True),
            "legend": tk.BooleanVar(value=True),
        }
        for k, label in [
            ("annotated", "Açıklamalı akademik çıktı (kapalı: temiz şekil)"),
            ("transparent", "PNG/SVG saydam arka plan"),
            ("grid", "Izgara"),
            ("axes", "Eksenler"),
            ("legend", "Açıklamalar"),
        ]:
            ttk.Checkbutton(box, text=label, variable=flags[k]).pack(anchor="w", pady=2)

        def confirm():
            """Seçimleri doğrular, hedef klasörü alır ve kayıt işini başlatır."""
            try:
                options = ExportOptions(
                    pixel_size=int(size.get()),
                    dpi=int(dpi.get()),
                    quality=int(quality.get()),
                    background=background.get(),
                    orientation="portrait" if orient.get() == "Dikey" else "landscape",
                    **{k: v.get() for k, v in flags.items()},
                )
                selected = [k for k, v in formats.items() if v.get()]
                if not selected:
                    raise ValueError("En az bir biçim seçin.")
                directory = filedialog.askdirectory(parent=dialog, title="Çıktı klasörü")
                if not directory:
                    return
                names = {
                    "pdf": "a4.pdf",
                    "png": "reconstruction.png",
                    "jpeg": "reconstruction.jpg",
                    "svg": "reconstruction.svg",
                    "json": "model.json",
                    "txt": "equations.txt",
                }
                if any(
                    (Path(directory) / names[k]).exists() for k in selected
                ) and not messagebox.askyesno(
                    "Dosyalar yenilenecek",
                    "Aynı adlı seçilmiş dosyalar yenilensin mi?",
                    parent=dialog,
                ):
                    return
                dialog.destroy()
                self.start_job(
                    "export",
                    export_result,
                    self.result,
                    directory,
                    formats=selected,
                    options=options,
                )
            except ValueError as error:
                messagebox.showerror("Geçersiz çıktı ayarı", str(error), parent=dialog)

        ttk.Button(box, text="Seçilen çıktıları kaydet", command=confirm).pack(fill="x", pady=15)

    def save_cad(self) -> None:
        """CAD birimi/ölçeği ve üç biçimi masaüstünden seçip arka planda dışa aktarır."""
        if self.result is None or self.future is not None:
            return
        from .cad import available_formats

        support = available_formats()
        defaults = getattr(self, "cad_defaults", CadOptions())
        dialog = tk.Toplevel(self.root)
        dialog.title("CAD aktarımı · STEP / IGES / DXF")
        dialog.geometry("610x650")
        dialog.transient(self.root)
        box = ttk.Frame(dialog, padding=20)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="Düzenlenebilir CAD geometrisi", font=("Segoe UI", 14, "bold")).pack(
            anchor="w"
        )
        variables = {}
        for kind, label in [
            ("step", "STEP · delikli düzlemsel yüzler"),
            ("iges", "IGES · delikli düzlemsel yüzler"),
            ("dxf", "DXF · yerel doğru, konik ve parametrik spline"),
        ]:
            variables[kind] = tk.BooleanVar(value=support[kind])
            ttk.Checkbutton(
                box,
                text=label,
                variable=variables[kind],
                state="normal" if support[kind] else "disabled",
            ).pack(anchor="w", pady=4)
        if not all(support.values()):
            ttk.Label(
                box,
                text="Eksik CAD desteği için kur_cad_windows.cmd dosyasını çalıştırın.",
                wraplength=560,
            ).pack(anchor="w", pady=5)
        unit = tk.StringVar(value=defaults.unit)
        scale = tk.StringVar(value=str(defaults.scale))
        tolerance = tk.StringVar(value=str(defaults.tolerance))
        approximate = tk.BooleanVar(value=defaults.allow_approximation)
        ttk.Label(box, text="Fiziksel çıktı birimi").pack(anchor="w", pady=(12, 3))
        ttk.Combobox(box, textvariable=unit, values=["mm", "cm", "m", "in"], state="readonly").pack(
            fill="x"
        )
        for label, var in [
            ("1 çalışma koordinatı = kaç çıktı birimi?", scale),
            ("CAD aktarım toleransı (seçilen çıktı biriminde)", tolerance),
        ]:
            ttk.Label(box, text=label).pack(anchor="w", pady=(10, 3))
            ttk.Entry(box, textvariable=var).pack(fill="x")
        extent = tk.StringVar()

        def update_extent(*_):
            """Ölçek eşlemesinin fiziksel anlamını hesaplamadan önce görünür tutar."""
            try:
                extent.set(
                    f"1 çalışma birimi = {float(scale.get()):g} {unit.get()}. Ölçek kullanıcı eşlemesidir; görselden fiziksel kalibrasyon çıkarılmaz."
                )
            except ValueError:
                extent.set("Geçerli bir CAD ölçeği girin.")

        scale.trace_add("write", update_extent)
        unit.trace_add("write", update_extent)
        update_extent()
        ttk.Label(box, textvariable=extent, wraplength=560).pack(anchor="w", pady=12)
        ttk.Checkbutton(
            box,
            text="Fourier gibi eğriler için kontrollü doğru yaklaşımına izin ver",
            variable=approximate,
        ).pack(anchor="w", pady=6)
        ttk.Label(
            box,
            text="Her CAD dosyasıyla denklem, katsayı/aralık, topoloji ve aktarım denetimini içeren .cad.json kaydı yazılır. Geometri parametreleri taşınır; CAD programına özgü ölçü/kısıt geçmişi oluşturulmaz.",
            wraplength=560,
        ).pack(anchor="w", pady=8)

        def confirm():
            """Somut CAD ayarlarını doğrular; mevcut dosyalar için çakışma onayı alır."""
            try:
                options = CadOptions(
                    unit.get(), float(scale.get()), float(tolerance.get()), approximate.get()
                )
                formats = [k for k, var in variables.items() if var.get()]
                if not formats:
                    raise ValueError("En az bir kurulu CAD biçimi seçin.")
                directory = filedialog.askdirectory(parent=dialog, title="CAD çıktıları klasörü")
                if not directory:
                    return
                targets = [
                    Path(directory) / f"reconstruction.{k}{suffix}"
                    for k in formats
                    for suffix in ("", ".cad.json")
                ]
                if any(p.exists() for p in targets) and not messagebox.askyesno(
                    "CAD dosyaları yenilenecek",
                    "Seçili CAD dosyaları ve eşleme kayıtları yenilensin mi?",
                    parent=dialog,
                ):
                    return
                self.cad_defaults = options
                dialog.destroy()
                self.start_job(
                    "export",
                    export_result,
                    self.result,
                    directory,
                    formats=formats,
                    options=ExportOptions(cad=options),
                )
            except ValueError as error:
                messagebox.showerror("Geçersiz CAD ayarı", str(error), parent=dialog)

        ttk.Button(box, text="Seçilen CAD biçimlerini kaydet", command=confirm).pack(
            fill="x", pady=12
        )

    def open_pilot(self) -> None:
        """Ayrı araştırma/pilot çalışma alanını mevcut model anlık görüntüsüyle açar."""
        if self.future is not None:
            return
        from .pilot_gui import PilotWindow

        current = getattr(self, "pilot_window", None)
        if current is not None and not current.closed:
            current.window.lift()
            return
        self.pilot_window = PilotWindow(self.root, self.result)

    def run_benchmark(self) -> None:
        """Analitik veri kümesini ve gerçek karşılaştırmaları terminal gerektirmeden üretir."""
        if self.future is not None:
            return
        directory = filedialog.askdirectory(title="Doğrulama veri/sonuç klasörü")
        if directory:
            from .benchmark import run_benchmark

            self.start_job(
                "benchmark",
                lambda: run_benchmark(
                    directory, cancel=self.cancel_event, progress=self.messages.put
                ),
            )

    def run_stress(self) -> None:
        """Seçilen manifesti ε=1,2,3,5'te tarar; arka plan ve iptal sözleşmesini korur."""
        if self.future is not None:
            return
        manifest = filedialog.askopenfilename(
            title="Karmaşık veri manifesti", filetypes=[("JSON manifest", "*.json")]
        )
        if not manifest:
            return
        directory = filedialog.askdirectory(title="Tarama sonuçları için ayrı klasör")
        if directory:
            from .stress import run_grid

            self.start_job(
                "benchmark",
                lambda: run_grid(
                    manifest, directory, cancel=self.cancel_event, progress=self.messages.put
                ),
            )

    def close(self) -> None:
        """İptal isteği gönderip bekleyen işleri bırakır ve Tk penceresini kapatır."""
        pilot = getattr(self, "pilot_window", None)
        if pilot is not None and not pilot.closed:
            if (
                pilot.dirty
                or pilot.form_dirty
                or pilot.preparation.dirty
                or pilot.future is not None
            ):
                pilot.window.lift()
                self.status.set("Önce pilot çalışmasını kaydedip pilot penceresini kapatın.")
                return
            pilot.close(force=True)
        self.closed = True
        self.cancel_event.set()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main() -> None:
    """Türkçe çevrimdışı masaüstü uygulamasını açar."""
    root = tk.Tk()
    AnalysisWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
