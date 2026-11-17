"""İşlem ayarları ve JSON ile taşınabilen sonuç sözleşmeleri."""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AnalysisConfig:
    """Analiz parametrelerini doğrular.

    Attributes:
        threshold: Bu değere eşit veya daha koyu gri pikseller siyahtır (0..254).
        padding: Çalışma düzleminin her kenarındaki en az boş piksel sayısı.
        working_size: 0 (varsayılan) görseli yeniden örneklemez; bir çalışma birimi bir
            kaynak pikselidir. Pozitif değer (örneğin 1000) eski davranıştır: şekil o
            kenarlı düzleme ölçeklenir ve garantiler yeniden örneklenmiş görsele aittir.
        tolerance: Sınır sadeleştirme toleransı, koordinat birimi; 0 kesin moddur.
        degree: İsteğe bağlı örtük polinomun toplam derecesi (2..12).
        max_fit_points: Polinom için eşit yay uzunluğuyla örneklenen nokta üst sınırı.
    """

    threshold: int = 127
    padding: int = 20
    tolerance: float = 0.0
    degree: int | None = None
    max_fit_points: int = 8000
    family: str = "polygon"
    preference: str = "balanced"
    evaluation_spacing: float = 1.0
    flatten_tolerance: float = 0.05
    embed_input: bool = False
    search_strategy: str = "deterministic"
    search_budget: int = 20
    random_seed: int = 20261015
    evaluation_workers: int = 1
    certificate_mode: str = "selected"
    working_size: int = 0

    def __post_init__(self) -> None:
        """Geçersiz ayarlarda ValueError yükseltir; dönüş değeri yoktur."""
        import math

        if not isinstance(self.working_size, int) or not (
            self.working_size == 0 or 100 <= self.working_size <= 20000
        ):
            raise ValueError("Çalışma düzlemi 0 (yerel çözünürlük) veya 100..20000 olmalıdır.")

        if not isinstance(self.threshold, int) or not 0 <= self.threshold <= 254:
            raise ValueError("Eşik 0..254 arasında bir tam sayı olmalıdır.")
        if not isinstance(self.padding, int) or not 0 <= self.padding < 500:
            raise ValueError("Kenar boşluğu 0..499 arasında bir tam sayı olmalıdır.")
        if self.working_size and 2 * self.padding >= self.working_size:
            raise ValueError("Kenar boşluğu çalışma düzlemine sığmıyor.")
        if not math.isfinite(self.tolerance) or not 0 <= self.tolerance <= 50:
            raise ValueError("Tolerans 0..50 arasında sonlu bir sayı olmalıdır.")
        if self.degree is not None and (
            not isinstance(self.degree, int) or not 2 <= self.degree <= 12
        ):
            raise ValueError("Polinom derecesi 2..12 arasında bir tam sayı olmalıdır.")
        if not isinstance(self.max_fit_points, int) or not 200 <= self.max_fit_points <= 20000:
            raise ValueError("Örnek sayısı 200..20000 arasında bir tam sayı olmalıdır.")
        if self.family not in {
            "exact",
            "polygon",
            "auto",
            "mixed",
            "circle",
            "ellipse",
            "bezier",
            "bspline",
            "fourier",
            "adaptive",
            "topology",
            "minlink",
            "linearc",
        }:
            raise ValueError("Bilinmeyen model ailesi.")
        if self.preference not in {"simple", "balanced", "accurate"}:
            raise ValueError("Tercih simple, balanced veya accurate olmalıdır.")
        if self.search_strategy not in {
            "deterministic",
            "annealing",
        } or self.certificate_mode not in {"off", "selected", "strict"}:
            raise ValueError("Arama veya sertifika modu geçersiz.")
        if not isinstance(self.search_budget, int) or not 4 <= self.search_budget <= 100:
            raise ValueError("Tavlama bütçesi 4..100 olmalıdır.")
        if not isinstance(self.random_seed, int) or not 0 <= self.random_seed < 2**32:
            raise ValueError("Rastgelelik tohumu 0..2^32-1 olmalıdır.")
        if not isinstance(self.evaluation_workers, int) or not 1 <= self.evaluation_workers <= 8:
            raise ValueError("CPU işçi sayısı 1..8 olmalıdır.")
        if not math.isfinite(self.evaluation_spacing) or not 0.05 <= self.evaluation_spacing <= 10:
            raise ValueError("Ölçüm aralığı 0.05..10 birim olmalıdır.")
        if not math.isfinite(self.flatten_tolerance) or not 0.0001 <= self.flatten_tolerance <= 1:
            raise ValueError("Eğri değerlendirme toleransı 0.0001..1 birim olmalıdır.")


@dataclass(frozen=True)
class Boundary:
    """Bir kapalı sınırı ve tam sayı piksel geometrisindeki yönünü taşır.

    Attributes:
        vertices: Kartezyen (x, y) köşeleri; son köşe ilk köşeyi tekrar etmez.
        kind: Saat yönündeki dış sınır için 'outer', ters yöndeki boşluk için 'hole'.
        original_vertex_count: Sadeleştirmeden önceki köşe sayısı.
    """

    vertices: list[tuple[float, float]]
    kind: str
    original_vertex_count: int


@dataclass(frozen=True)
class PolynomialFit:
    """Normalize koordinatlarda F(u,v)=0 yaklaşımının katsayılarını taşır.

    Attributes:
        degree: İstenen toplam derece üst sınırı.
        terms: (u üssü, v üssü, katsayı) üçlüleri; katsayı vektörünün normu 1'dir.
        algebraic_rms: Örneklerdeki F değerlerinin RMS'i; geometrik mesafe değildir.
        gradient_distance_rms: |F|/||grad F|| mesafesinin yaklaşık RMS'i, piksel birimi.
        sample_count: Uydurmada kullanılan nokta sayısı.
        condition_number: Tasarım matrisinin koşul sayısı; None sayısal tekilliği belirtir.
    """

    degree: int
    terms: list[tuple[int, int, float]]
    algebraic_rms: float
    gradient_distance_rms: float | None
    sample_count: int
    condition_number: float | None
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class CurvePiece:
    """Sonlu parametrik eğri; tüm uzunluklar çalışma düzlemi birimindedir.

    params türe özgü katsayıları, interval geçerli parametre aralığını taşır.
    start/end aynı katsayılardan türetilir. transform ortak kaynak dönüşümünü
    gösterir; boundary_id ve component_id topoloji kaydına başvurur.
    """

    kind: str
    params: dict[str, Any]
    interval: list[float]
    start: list[float]
    end: list[float]
    boundary_id: int
    component_id: int
    transform: str = "normalization.source_to_working"
    errors: dict[str, Any] = field(default_factory=dict)
    tolerances: dict[str, float] = field(default_factory=dict)


@dataclass
class Candidate:
    """İncelenen bir modelin geometri, maliyet, kabul ve ret kanıtlarını taşır."""

    id: str
    family: str
    pieces: list[CurvePiece]
    metrics: dict[str, Any] = field(default_factory=dict)
    complexity: dict[str, Any] = field(default_factory=dict)
    accepted: bool = False
    reasons: list[str] = field(default_factory=list)
    pareto: bool = False


@dataclass(frozen=True)
class AnalysisResult:
    """Girdi dönüşümü, sınırlar, yaklaşım ve ölçümleri birlikte taşır.

    Attributes:
        config: Kullanılan analiz ayarları.
        normalization: Boyut, ölçek, ofset ve koordinat dönüşüm bilgileri.
        boundaries: Dış sınırlar ve iç boşlukların kapalı poligonları.
        polynomial: İstenmişse yaklaşık örtük polinom, aksi halde None.
        metrics: Sınır sayıları ve sadeleştirme doğrulaması.
    """

    config: AnalysisConfig
    normalization: dict[str, Any]
    boundaries: list[Boundary]
    polynomial: PolynomialFit | None
    metrics: dict[str, Any]
    reference_boundaries: list[Boundary] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    selected_id: str = ""
    topology: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def selected(self) -> Candidate | None:
        """Seçilen kaydedilmiş modeli döndürür; yeniden uydurma yapmaz."""
        return next((c for c in self.candidates if c.id == self.selected_id), None)

    def to_dict(self) -> dict[str, Any]:
        """Alanları JSON uyumlu sözlüğe çevirir; yeni dict döndürür."""
        return {"schema_version": "2.4", "application_version": "3.0.0", **asdict(self)}
