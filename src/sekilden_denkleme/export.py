"""Gerçek vektör, raster ve sayfalanmış akademik rapor; doğrulamalı dışa aktarım."""

import base64
import io
import json
import math
import os
import tempfile
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
import numpy as np
import shapely
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PIL import Image
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as ReportImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from shapely.geometry import MultiLineString

from .cad_geometry import CadOptions
from .curves import equation, flatten, is_full_conic, model_rings
from .evaluation import closed_vertices, sample_ring
from .models import AnalysisResult
from .project import save_project, source_image


@dataclass(frozen=True)
class ExportOptions:
    """Çıktı seçenekleri; boyut piksel, DPI çözünürlük metaverisi, kalite 1..100."""

    pixel_size: int = 1600
    dpi: int = 160
    quality: int = 95
    transparent: bool = False
    background: str = "white"
    grid: bool = True
    axes: bool = True
    legend: bool = True
    annotated: bool = True
    orientation: str = "portrait"
    svg_tolerance: float = 0.05
    cad: CadOptions = field(default_factory=CadOptions)

    def __post_init__(self) -> None:
        """Kaynak tüketimini ve gerçek biçim seçeneklerini doğrular."""
        if not isinstance(self.pixel_size, int) or not 128 <= self.pixel_size <= 10000:
            raise ValueError("Çıktı boyutu 128..10000 piksel olmalıdır.")
        if not isinstance(self.dpi, int) or not 36 <= self.dpi <= 1200:
            raise ValueError("DPI 36..1200 arasında olmalıdır.")
        if not 1 <= self.quality <= 100 or self.orientation not in {"portrait", "landscape"}:
            raise ValueError("JPEG kalitesi veya PDF yönü geçersiz.")
        if self.background not in {"white", "#ffffff", "#f4f6fa"}:
            raise ValueError("Desteklenmeyen çıktı arka planı.")
        if not math.isfinite(self.svg_tolerance) or not 0.0001 <= self.svg_tolerance <= 1:
            raise ValueError("SVG toleransı 0.0001..1 birim olmalıdır.")


def rendering_tolerance(result: AnalysisResult, options: ExportOptions) -> float:
    """Yaklaşık çizimi değerlendirmede kullanılan eğri toleransından sıkı tutar."""
    delta = result.selected.metrics.get("flatten_tolerance", 0) if result.selected else 0
    return min(options.svg_tolerance, delta) if delta > 0 else options.svg_tolerance


def _plane(result: AnalysisResult) -> int:
    """Çalışma düzleminin kenarı; eski kayıtlarda 1000."""
    return int((result.normalization or {}).get("canvas_size", [1000])[0])


def equation_report(result: AnalysisResult) -> str:
    """Bütün parçaları, aralıkları, ölçümleri ve kesinlik kapsamını UTF-8 sunar."""
    selected = result.selected
    lines = [
        "ŞEKİLDEN DENKLEME 2.5",
        f"Düzlem: [0,{_plane(result)}]²; x sağa, y yukarı; piksel kare kenarları.",
        "Alan sınırı modu: kalın çizginin iki yanı korunur; merkez hattı değildir.",
        f"Seçilen aday: {result.selected_id}; kullanıcı toleransı: {result.config.tolerance:g} birim.",
        "Kesin piksel sınırı ile ideal sürekli çizim farklı referanslardır.",
        "Sonlu doğru: r(t)=A+t(B-A), 0≤t≤1.",
        "Örtük doğru parçası: dy(x-ax)-dx(y-ay)=0; 0≤D·(X-A)≤D·D.",
        "G(x,y)=min_i ||X-A_i-clip(D_i·(X-A_i)/(D_i·D_i),0,1)D_i||²=0",
        "G yalnızca doğru parçalarının birleşimi içindir; tek polinom değildir.",
        "R(θ)=[[cos θ,-sin θ],[sin θ,cos θ]]. Açılar radyandır.",
        "Kübik Bézier'de a,b kaydedilmiş interval uçlarıdır; B-spline Cox-de Boor tabanıdır.",
        "Sınırlı aday araması; incelenen adaylar arasındaki seçim. Küresel optimum kanıtı yok.",
        "Analitik kanıt yalnızca sertifika status=proven koşullarında geçerlidir; diğer sonuçlar kontrollü poligon denetimidir.",
        "",
    ]
    if selected:
        for i, piece in enumerate(selected.pieces, 1):
            lines += [
                f"Parça {i} | {piece.kind} | sınır {piece.boundary_id} | bileşen {piece.component_id}",
                equation(piece),
                f"Başlangıç={piece.start}; bitiş={piece.end}",
                "Hata (kapsamıyla): " + json.dumps(piece.errors, ensure_ascii=False),
                "Sayısal toleranslar: " + json.dumps(piece.tolerances, ensure_ascii=False),
                "",
            ]
        lines += [
            "SEÇİLEN MODEL ÖLÇÜMLERİ",
            json.dumps(selected.metrics, ensure_ascii=False, indent=2),
            "KARMAŞIKLIK",
            json.dumps(selected.complexity, ensure_ascii=False, indent=2),
        ]
    if result.polynomial:
        fit = result.polynomial
        lines += [
            "",
            "YAKLAŞIK ÖRTÜK POLİNOM",
            "u=(x-500)/500; v=(y-500)/500",
            "F(u,v)=" + " ".join(f"{c:+.17g}*u^{i}*v^{j}" for i, j, c in fit.terms) + "=0",
            f"||c||₂=1; cebirsel RMS={fit.algebraic_rms}; koşul sayısı={fit.condition_number}",
            f"Gradyan mesafe tahmini RMS={fit.gradient_distance_rms}; tekil gradyanda null.",
            "Sıfır dalları yalnızca 2 birim ızgarada araştırılmıştır; model seçimine kabul edilmez.",
            json.dumps(
                {k: v for k, v in fit.diagnostics.items() if k != "zero_paths"}, ensure_ascii=False
            ),
        ]
    lines += ["", "ADAYLAR"]
    for c in result.candidates:
        lines += [
            f"{c.id}: kabul={c.accepted}, Pareto={c.pareto}, bit={c.complexity.get('score_bits')}, "
            f"üst hata={c.metrics.get('hausdorff_upper_bound')}; neden={'; '.join(c.reasons)}"
        ]
    lines += [
        "",
        "KOORDİNAT/ÖN İŞLEME",
        json.dumps(result.normalization, ensure_ascii=False, indent=2),
        "YENİDEN ÜRETİM",
        json.dumps(
            {k: v for k, v in result.provenance.items() if "base64" not in k},
            ensure_ascii=False,
            indent=2,
        ),
    ]
    return "\n".join(lines) + "\n"


def make_figure(
    result: AnalysisResult,
    *,
    a4: bool = False,
    view: str = "model",
    options: ExportOptions | None = None,
    selected_piece: int | None = None,
) -> Figure:
    """Kaydedilmiş katsayılardan model, karşılaştırma veya hata görünümü üretir."""
    options = options or ExportOptions()
    curve_delta = rendering_tolerance(result, options)
    size = (210 / 25.4, 297 / 25.4) if a4 else (7, 7)
    figure = Figure(figsize=size, dpi=120)
    FigureCanvasAgg(figure)
    ax = figure.add_subplot()
    references = result.reference_boundaries or result.boundaries
    if view in {"source", "normalized"}:
        if view == "source":
            image = source_image(result)
        else:
            encoded = result.provenance.get("normalized_png_base64")
            image = Image.open(io.BytesIO(base64.b64decode(encoded))) if encoded else None
        if image is not None:
            ax.imshow(
                image,
                origin="upper",
                extent=(0, image.width, 0, image.height),
                cmap="gray",
                vmin=0,
                vmax=255,
            )
            ax.set_title(
                "Kaynak görsel (EXIF düzeltilmiş)"
                if view == "source"
                else "Normalize eşikleme · en yakın komşu"
            )
        else:
            ax.text(
                0.5,
                0.5,
                "Kaynak görsel bulunamadı\nKayıtlı model kullanılabilir",
                ha="center",
                transform=ax.transAxes,
            )
        ax.set_axis_off()
    else:
        if view in {"reference", "overlay", "error"}:
            for i, b in enumerate(references):
                q = closed_vertices(b)
                ax.plot(
                    q[:, 0],
                    q[:, 1],
                    color="#9aa8b5",
                    lw=1.5,
                    label="Referans piksel sınırı" if i == 0 else None,
                )
        if view != "reference" and result.selected:
            for i, piece in enumerate(result.selected.pieces):
                q = flatten(piece, curve_delta)
                highlight = i == selected_piece
                ax.plot(
                    q[:, 0],
                    q[:, 1],
                    color="#e87123" if highlight else "#136c8b",
                    lw=3 if highlight else 1.2,
                    label="Matematiksel model" if i == 0 else None,
                )
        if view == "error" and result.selected:
            rings = model_rings(result.selected.pieces, curve_delta)
            geometry = MultiLineString(list(rings.values()))
            for b in references:
                q, _, _ = sample_ring(closed_vertices(b), max(1, result.config.evaluation_spacing))
                distances = shapely.distance(shapely.points(q), geometry)
                plot = ax.scatter(
                    q[:, 0],
                    q[:, 1],
                    c=distances,
                    s=4,
                    cmap="inferno",
                    vmin=0,
                    vmax=max(1e-8, result.config.tolerance),
                )
            figure.colorbar(plot, ax=ax, label="Referans → model uzaklığı (birim)", shrink=0.7)
        if result.polynomial and view == "overlay":
            for i, path in enumerate(result.polynomial.diagnostics.get("zero_paths", [])):
                q = np.asarray(path)
                ax.plot(
                    q[:, 0],
                    q[:, 1],
                    color="#c94c6c",
                    alpha=0.7,
                    lw=0.8,
                    label="Keşif: örtük polinom" if i == 0 else None,
                )
        ax.set(xlim=(0, _plane(result)), ylim=(0, _plane(result)))
        if options.axes and options.annotated:
            ax.set(xlabel="x", ylabel="y")
            ax.set_xticks(range(0, 1001, 200))
            ax.set_yticks(range(0, 1001, 200))
        else:
            ax.set_axis_off()
        if options.grid and options.annotated:
            ax.grid(color="#dce4ea", linewidth=0.5)
        if options.annotated:
            ax.set_title(
                {
                    "model": "Matematiksel model",
                    "reference": "Referans piksel sınırı",
                    "overlay": "Referans ve model karşılaştırması",
                    "error": "Hata dağılımı",
                }.get(view, view)
            )
            if options.legend and view != "error":
                ax.legend(loc="upper right", fontsize=8)
    ax.set_aspect("equal")
    figure.set_layout_engine("tight", pad=1.2 if options.annotated else 0)
    return figure


def _svg(result: AnalysisResult, options: ExportOptions, path: Path) -> None:
    side = _plane(result)
    """Doğru/Bézier/çember/elipsi yerel SVG elemanlarıyla, spline'ı kontrollü çizer."""
    curve_delta = rendering_tolerance(result, options)
    ns = "http://www.w3.org/2000/svg"
    ET.register_namespace("", ns)
    root = ET.Element(
        "svg",
        xmlns=ns,
        viewBox=f"0 0 {side} {side}",
        width=str(options.pixel_size),
        height=str(options.pixel_size),
    )
    ET.SubElement(root, "metadata").text = json.dumps(
        {
            "schema": "2.4",
            "candidate": result.selected_id,
            "axis": "x_right_y_up",
            "spline_polyline_tolerance": curve_delta,
            "rational_arc_polyline_tolerance": curve_delta,
            "approximated_families": ["bspline", "fourier", "rational_conic_arc"],
            "native_types": ["line", "circle", "ellipse", "cubic_bezier"],
            "source_to_working": result.normalization.get("source_to_working"),
        },
        ensure_ascii=False,
    )
    if not options.transparent:
        ET.SubElement(root, "rect", width=str(side), height=str(side), fill=options.background)
    if options.annotated and options.grid:
        for v in range(0, side + 1, max(1, side // 10)):
            ET.SubElement(
                root,
                "path",
                d=f"M {v} 0 V {side} M 0 {v} H {side}",
                stroke="#e0e6eb",
                fill="none",
                **{"stroke-width": "0.5"},
            )
    group = ET.SubElement(
        root,
        "g",
        transform=f"translate(0 {side}) scale(1 -1)",
        fill="none",
        stroke="#136c8b",
        **{"stroke-width": "1.2"},
    )
    for i, p in enumerate(result.selected.pieces if result.selected else []):
        params = p.params
        attrs = {"data-piece": str(i), "data-boundary": str(p.boundary_id)}
        if p.kind == "line":
            ET.SubElement(
                group,
                "line",
                x1=str(p.start[0]),
                y1=str(p.start[1]),
                x2=str(p.end[0]),
                y2=str(p.end[1]),
                **attrs,
            )
        elif p.kind == "bezier":
            c = params["controls"]
            ET.SubElement(
                group,
                "path",
                d=f"M {c[0][0]:.17g} {c[0][1]:.17g} C "
                + " ".join(f"{x:.17g} {y:.17g}" for x, y in c[1:]),
                **attrs,
            )
        elif is_full_conic(p):
            cx, cy = params["center"]
            if p.kind == "circle":
                ET.SubElement(
                    group, "circle", cx=str(cx), cy=str(cy), r=str(params["radius"]), **attrs
                )
            else:
                rx, ry = params["radii"]
                ET.SubElement(
                    group,
                    "ellipse",
                    cx=str(cx),
                    cy=str(cy),
                    rx=str(rx),
                    ry=str(ry),
                    transform=f"rotate({math.degrees(params['rotation']):.17g} {cx:.17g} {cy:.17g})",
                    **attrs,
                )
        elif p.kind in {"circle", "ellipse"} and "arc" not in params:
            rx, ry = [params["radius"]] * 2 if p.kind == "circle" else params["radii"]
            angle = math.degrees(params.get("rotation", 0))
            large = int(p.interval[1] - p.interval[0] > np.pi)
            sweep = int(params.get("direction", 1) > 0)
            ET.SubElement(
                group,
                "path",
                d=f"M {p.start[0]:.17g} {p.start[1]:.17g} A {rx:.17g} {ry:.17g} {angle:.17g} {large} {sweep} {p.end[0]:.17g} {p.end[1]:.17g}",
                **attrs,
            )
        else:
            q = flatten(p, curve_delta)
            ET.SubElement(
                group, "polyline", points=" ".join(f"{x:.17g},{y:.17g}" for x, y in q), **attrs
            )
    if options.annotated and options.axes:
        ET.SubElement(
            root,
            "path",
            d=f"M 0 {side - 1} H {side} M 1 {side} V 0",
            stroke="#617283",
            fill="none",
        )
        for v in range(0, side + 1, max(1, side // 5)):
            ET.SubElement(
                root,
                "text",
                x=str(min(side - 30, max(4, v))),
                y=str(side - 8),
                **{"font-size": "10"},
            ).text = str(v)
    if options.annotated and options.legend:
        ET.SubElement(
            root, "text", x="20", y="22", **{"font-size": "13", "fill": "#172e48"}
        ).text = f"Şekilden Denkleme | {result.selected_id} | {side} × {side}"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _pdf(result: AnalysisResult, options: ExportOptions, path: Path) -> None:
    """A4 karşılaştırma ve bütün denklemleri taşmasız, tekrarlı başlıkla sayfalar."""
    font_dir = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    if "SD" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("SD", str(font_dir / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("SD-Bold", str(font_dir / "DejaVuSans-Bold.ttf")))
    page_size = A4 if options.orientation == "portrait" else landscape(A4)
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "SDbody", fontName="SD", fontSize=8, leading=11, spaceAfter=4, wordWrap="CJK"
    )
    title = ParagraphStyle(
        "SDtitle", parent=body, fontName="SD-Bold", fontSize=21, leading=26, spaceAfter=12
    )
    heading = ParagraphStyle(
        "SDheading",
        parent=body,
        fontName="SD-Bold",
        fontSize=12,
        leading=16,
        spaceBefore=12,
        spaceAfter=6,
    )
    small = ParagraphStyle("SDsmall", parent=body, fontSize=7, leading=10)
    _ = styles
    if not options.annotated:
        figure = make_figure(result, options=options)
        # Temiz çıktı da gerçek A4 boyutundadır.
        figure.set_size_inches(page_size[0] / 72, page_size[1] / 72)
        figure.savefig(path, format="pdf", transparent=options.transparent)
        figure.clear()
        return
    story = [
        Paragraph("Şekilden Denkleme", title),
        Paragraph("Geometrik model ve yeniden üretim raporu · Sürüm 2.5", body),
        Paragraph(
            f"Seçim: {escape(result.selected_id)} | Tolerans: {result.config.tolerance:g} birim | Düzlem: {_plane(result)} × {_plane(result)}",
            body,
        ),
        Paragraph(
            "Kesinlik normalize piksel sınırına aittir. İdeal sürekli nesnenin keşfedildiği iddia edilmez. "
            "Analitik topoloji ve aralık hata kanıtı, yalnızca sertifika bölümündeki desteklenen aile ve yeter koşullar sağlanırsa geçerlidir.",
            body,
        ),
    ]
    width = page_size[0] - 80
    images = []
    for view in ("source", "reference", "overlay"):
        figure = make_figure(result, view=view, options=ExportOptions(grid=False, legend=False))
        stream = io.BytesIO()
        figure.savefig(stream, format="png", dpi=110)
        figure.clear()
        stream.seek(0)
        images.append(ReportImage(stream, width=width / 3, height=width / 3))
    proof = result.selected.metrics.get("certification", {}) if result.selected else {}
    story += [
        Paragraph("Hata ve topoloji sertifikası", heading),
        Paragraph(
            escape(
                f"Durum: {proof.get('status', 'kapalı')}; doğrulanmış sayısal kapsama: {proof.get('verified_numerical_certificate', False)}; analitik izotopi: {proof.get('analytic_isotopy_proven', False)}; sertifikalı H üst: {proof.get('hausdorff_upper_bound', 'yok')}"
            ),
            body,
        ),
        Paragraph(
            "Sertifika kayıtlı katsayılar ve raporlanan yeter koşullar içindir. Doğru/Bézier/B-spline, kanonik tam çember/elips veya doğrulanmış boş üçgen tanığı desteklenir. Tablo ayrı float64 ölçümüdür. Genel örtük/Fourier ve karma konik yayları belirsizdir.",
            body,
        ),
    ]
    story += [
        Spacer(1, 10),
        Table([images], colWidths=[width / 3] * 3),
        Paragraph("Hata ve karmaşıklık karşılaştırması", heading),
    ]
    rows = [
        [
            Paragraph(t, small)
            for t in ["Aday", "Parça", "Serbest p. üst", "Bit", "H üst", "RMS", "Kabul / Pareto"]
        ]
    ]
    for c in result.candidates:
        h = c.metrics.get("hausdorff_upper_bound")
        rms = c.metrics.get("rms")
        row = [
            c.id,
            str(len(c.pieces)),
            str(c.complexity.get("free_parameters_upper", "-")),
            str(c.complexity.get("score_bits", "-")),
            f"{h:.4g}" if h is not None else "-",
            f"{rms:.4g}" if rms is not None else "-",
            f"{'Evet' if c.accepted else 'Ret'} / {'Evet' if c.pareto else '-'}",
        ]
        rows.append([Paragraph(escape(t), small) for t in row])
    table = Table(
        rows,
        colWidths=[width * f for f in (0.20, 0.09, 0.12, 0.13, 0.13, 0.13, 0.20)],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6eef3")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd6de")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story += [
        table,
        Paragraph("Ölçüm ve kodlama sözleşmesi", heading),
        Paragraph(
            "H üst = iki yöndeki en büyük örnek uzaklığı + en büyük yay örnek aralığı/2 + eğri düzleştirme sınırı + 1e-8. "
            "Bu üst sınır Lipschitz bağıntısı ve float64 hesapla elde edilir; doğrulanmış aralık aritmetiği değildir. "
            "RMS yay uzunluğu ağırlıklı örnek ölçümüdür. Alan farkı poligonlaştırılmış modele aittir. "
            "Sadelik: 64 × saklanan gerçek sayı + 32 × tamsayı + 8 × parça bit; türetilmiş uçlar ve ortak dönüşüm tekrar sayılmaz.",
            body,
        ),
        Paragraph("Denklemler, aralıklar ve tanılar", heading),
    ]
    for line in equation_report(result).splitlines():
        # Her akış parçası kısa tutulur; uzun B-spline/polinom ifadeleri kaybolmaz.
        for chunk in textwrap.wrap(
            line, width=115, replace_whitespace=False, drop_whitespace=False
        ) or [" "]:
            story.append(Paragraph(escape(chunk), body))

    def footer(canvas, document):
        """Her A4 sayfasına sürüm ve sayfa numarası koyar."""
        canvas.setFont("SD", 7)
        canvas.setFillColor(colors.HexColor("#526476"))
        canvas.drawString(40, 22, "Şekilden Denkleme 2.5 · yerel analiz · sınırlı aday araması")
        canvas.drawRightString(page_size[0] - 40, 22, f"Sayfa {document.page}")

    SimpleDocTemplate(
        str(path),
        pagesize=page_size,
        leftMargin=40,
        rightMargin=40,
        topMargin=38,
        bottomMargin=38,
        title="Şekilden Denkleme - Model Raporu",
        author="Şekilden Denkleme",
    ).build(story, onFirstPage=footer, onLaterPages=footer)


def _validate_output(path: Path, kind: str) -> None:
    """Dosyanın gerçek biçimini tekrar açar; yanlış başarı bildirimi üretmez."""
    if not path.exists() or path.stat().st_size == 0:
        raise OSError("Çıktı dosyası boş.")
    if kind in {"png", "jpeg"}:
        with Image.open(path) as image:
            if image.format != ("PNG" if kind == "png" else "JPEG"):
                raise ValueError("Raster çıktı biçimi uyuşmuyor.")
            image.verify()
    elif kind == "svg":
        root = ET.parse(path).getroot()
        if root.tag != "{http://www.w3.org/2000/svg}svg" or any(
            e.tag.endswith("image") for e in root.iter()
        ):
            raise ValueError("SVG gerçek vektör sözleşmesini sağlamıyor.")
    elif kind == "pdf":
        reader = PdfReader(path)
        if not reader.pages or any(
            abs(float(p.mediabox.width) * float(p.mediabox.height) - A4[0] * A4[1]) > 1
            for p in reader.pages
        ):
            raise ValueError("PDF A4 sayfa doğrulaması başarısız.")


def export_file(
    result: AnalysisResult, path: str | Path, kind: str, options: ExportOptions | None = None
) -> Path:
    """Tek biçimi geçici dosyada üretip açar; başarıda hedefi atomik değiştirir."""
    options = options or ExportOptions()
    path = Path(path)
    if kind == "json":
        return save_project(result, path)
    if kind in {"dxf", "step", "iges"}:
        from .cad import export_cad

        return export_cad(result, path, kind, options.cad)
    if kind not in {"txt", "png", "jpeg", "svg", "pdf"}:
        raise ValueError("Bilinmeyen dışa aktarım biçimi.")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".export-", suffix="." + kind, dir=path.parent)
    os.close(fd)
    temp = Path(name)
    try:
        if kind == "txt":
            temp.write_text(equation_report(result), encoding="utf-8")
        elif kind == "svg":
            _svg(result, options, temp)
        elif kind == "pdf":
            _pdf(result, options, temp)
        else:
            figure = make_figure(result, options=options)
            figure.set_size_inches(
                options.pixel_size / options.dpi, options.pixel_size / options.dpi
            )
            stream = io.BytesIO()
            figure.savefig(
                stream,
                format="png",
                dpi=options.dpi,
                transparent=options.transparent,
                facecolor="none" if options.transparent else options.background,
            )
            figure.clear()
            stream.seek(0)
            with Image.open(stream) as image:
                if kind == "jpeg":
                    rgba = image.convert("RGBA")
                    image = Image.alpha_composite(
                        Image.new("RGBA", rgba.size, options.background), rgba
                    ).convert("RGB")
                    image.save(
                        temp, format="JPEG", quality=options.quality, dpi=(options.dpi, options.dpi)
                    )
                else:
                    image.save(temp, format="PNG", dpi=(options.dpi, options.dpi))
        _validate_output(temp, kind)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return path


def export_result(
    result: AnalysisResult,
    directory: str | Path,
    *,
    formats: list[str] | None = None,
    options: ExportOptions | None = None,
) -> list[Path]:
    """Seçili biçimleri kaydeder; her dosya doğrulanır, kısmi başarısızlık yükseltilir."""
    directory = Path(directory)
    names = {
        "json": "model.json",
        "txt": "equations.txt",
        "svg": "reconstruction.svg",
        "png": "reconstruction.png",
        "jpeg": "reconstruction.jpg",
        "pdf": "a4.pdf",
        "dxf": "reconstruction.dxf",
        "step": "reconstruction.step",
        "iges": "reconstruction.iges",
    }
    selected = formats if formats is not None else ["json", "txt", "svg", "png", "jpeg", "pdf"]
    if any(kind not in names for kind in selected):
        raise ValueError("Bilinmeyen dışa aktarım biçimi.")
    paths = []
    for kind in selected:
        target = export_file(result, directory / names[kind], kind, options)
        paths.append(target)
        if kind in {"dxf", "step", "iges"}:
            paths.append(target.with_name(target.name + ".cad.json"))
    return paths
