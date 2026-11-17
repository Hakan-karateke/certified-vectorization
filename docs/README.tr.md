> **Not (3.0):** Bu belge 2.6 sürümünün Türkçe kullanım kılavuzudur ve geliştirme
> deposundaki örnek klasörlerine bağlantılar içerir; o klasörler bu yayında yoktur.
> Güncel değişiklikler için [release-3.0.md](release-3.0.md) dosyasına bakın. 3.0'dan
> itibaren görsel varsayılan olarak yeniden örneklenmez.

# Şekilden Denkleme 2.6

Siyah çizimlerin **alan sınırını**, oranını koruyarak **1000 × 1000** çalışma düzlemine taşıyan yerel Python masaüstü uygulaması. Türkçe arayüz, ölçülmüş geometrik hata, sınırlı model araması, hata-karmaşıklık Pareto karşılaştırması ve tekrar açılabilen projeler sunar. LLM, bulut analizi veya harici analiz API'si kullanmaz.

![Sertifikalı B-spline, çember/elips ve temas koruyan çokgenler](examples/certified_extensions/comparison.png)

**2.6:** **Hazırlık ve görevler** sekmesi D: dahil CAD program yollarını,
gerçek sürüm/ilk açılış beyanını ve taşınabilir üç örnekli görev paketini yönetir.
STEP/IGES/DXF dosyaları yeniden açılarak doğrulanır; 18 başlangıç / 54 toplam
planlı görev pilot formuna aktarılır. Planlar insan sonucu değildir.
İptal düğmesi ardışık işlerde düzeltildi; kişi değişince onay temizlenir.
[Kullanıcının yapacağı hazırlık ve ilk oturum](docs/first-cad-pilot.md).
AutoCAD/SolidWorks kurulumu, ilk açılış ve gerçek insan görevleri kullanıcıyı bekliyor.
**187 test geçti; 9/9 yeni dosya ayrı FreeCAD kontrolünü geçti.**
[Gerçek 2.6 sonuçları](docs/release-2.6.md) · [Görev paketi ve raporlar](examples/first_cad_pilot/index.html).

**2.5 (tarihsel doğrulama):** **Araştırma · üç CAD pilotu** çalışma alanı eklendi. FreeCAD,
AutoCAD ve SolidWorks için görev, kronometre/elle süre, düzeltme ve kalite
kayıtları saklanır; eğitim denemeleri insan sonuçlarından ayrılır. FreeCADCmd
ayrı süreçte gerçek içe alma/profil/5 mm ekstrüzyon deneyi yapar. Araştırma
sekmesi kayıtlı aday ve tolerans projelerini HTML/JSON olarak karşılaştırır.
Çok bileşenli IGES'in FreeCAD'de boş açılması ayrı yüz kökleriyle giderildi.
**176 test geçti; 27/27 yeni CAD dosyası ayrı FreeCAD ürün kontrolünü geçti.**
[Kullanım](docs/pilot-workspace.md) · [Gerçek 2.5 sonuçları ve sınırlar](docs/release-2.5.md).
AutoCAD/SolidWorks ve gerçek insan pilotu henüz çalıştırılmadı.

**2.4:** STEP, IGES ve DXF aktarımı eklendi. **CAD: STEP · IGES · DXF**
ile mm/cm/m/in, fiziksel ölçek ve aktarım toleransı seçilir. STEP/IGES delikli
düzlemsel yüzler, DXF yerel geometrik nesneler ve parametrik NURBS üretir.
Denklem/özgün katsayılar `.cad.json` eşleme kaydıyla birlikte saklanır.
CAD programına özgü ölçü/kısıt geçmişi oluşturulmaz. **144 test geçti**;
27 gerçek CAD dosyası yeniden açılarak denetlendi.
[CAD kullanım ve sınırlar](docs/cad.md) · [Örnekler](examples/cad_validation/index.html) ·
[Eğitim etkinlikleri](docs/education-cad.md) · [Gerçek kullanıcı pilot protokolü](docs/cad-pilot.md).
CAD desteği için `kur_cad_windows.cmd` dosyasını çalıştırın; mevcut analiz kurulumu korunur.

**2.3:** Karma modellerde ortak uçlu rasyonel çember/elips yayları, bağımsız
hata/topoloji sertifikası ve masaüstünden devam ettirilebilir tolerans taraması
eklendi. [Yöntem, gerçek tarama ve karşılaştırmalar](docs/release-2.3.md).
**101 test geçti; 40 görsel × 4 tolerans = 160 analiz tamamlandı.** Sıkı
seçimde 116 yaklaşık model, 44 kesin geri dönüş sertifikalandı.
Yeni yaylar eski açısal yayların yerini uydurma aşamasında alır; kayıtlı eski
geometriler sessizce değiştirilmez.

**2.2:** B-spline, tam çember/elips ve temas koruyan çokgenler için hata/topoloji sertifikası eklendi. Sıkı modda çember/elips birer parça seçilir. Geyikte ε=2 ile 4324→2007 parça (dengeli), 1560 parça (daha sade) elde edildi. [Yeni deneyler ve kapsam](docs/release-2.2.md). Önceki kar tanesi 469→79 sonucu ve 2.1 ham deneyleri [tarihsel kayıtta](docs/improvements.md) korunur.

**Kesin mod**, normalize edilmiş siyah piksel karelerinin sınırını sonlu doğru parçalarıyla kayıpsız temsil eder. **Yaklaşık mod**, bu referansa göre ölçülen hata ve topoloji koşullarını sağlayan adayları karşılaştırır. İdeal sürekli nesne ile raster sınır aynı şey değildir. Sonuç, **incelenen adaylar arasındaki seçimdir**; küresel optimum iddiası yoktur.

## Windows'ta başlatma

Python **3.12.8** ile yerel doğrulama yapılmıştır. Proje klasöründeki `kur_windows.cmd` dosyasını ilk kurulumda, ardından `baslat_windows.cmd` dosyasını çift tıklayın. Kurulum internet gerektirir; analiz yerel çalışır. Gerekli ortam `.venv` klasöründe tutulur. Bağımsız EXE dağıtımı henüz yoktur.

Elle kurulum:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -m sekilden_denkleme.gui
```

Python 3.10 ve üstü paket sözleşmesinde desteklenir; bu geliştirmede gerçek çalıştırma Windows / Python 3.12.8 üzerindedir. Linux/macOS ve diğer Python sürümleri yeniden doğrulanmadı. [Windows kılavuzu](docs/windows.md).

## Terminal gerektirmeyen çalışma akışı

1. **Görsel aç**: PNG/JPEG/BMP/TIFF/WebP gibi tek kareli raster dosyayı seçin. Kaynak ve eşiklenmiş normalize görüntü yan yana gösterilir.
2. Eşik, boşluk, geometrik tolerans ve model ailesini ayarlayın. **ε=0** her ailede kesin piksel sınırına döner. Varsayılan masaüstü seçimi otomatik, ε=2 birimdir; API/CLI varsayılanı kesin moddur.
3. **Modelleri hesapla**: ilerleme durumunu izleyin; **İptal** önceki başarılı sonucu korur. İptal yürüyen GEOS/SVD/okuma adımının bitmesini bekleyebilir.
4. Kaynak, normalize görüntü, referans sınır, model, üst üste karşılaştırma ve hata dağılımı arasında geçin. Izgara koordinatları x sağa, y yukarıdır.
5. **Aday karşılaştırması** sekmesinde parça, bit maliyeti, RMS, hesaplanan Hausdorff üst sınırı, topoloji denetimi, kabul/ret ve Pareto durumunu inceleyin. Reddedilmiş adayın gerekçesi görünür; seçilemez. Kabul edilmiş adayı çift tıklayarak seçebilirsiniz.
6. **Parçalar ve denklemler** sekmesinden parça seçin: katsayıları, geçerlilik aralığı, uçları ve halka kapsamındaki hata ölçümü gösterilir; çizimde turuncu vurgulanır. Çizimi görmek için görsel çalışma alanına geçebilirsiniz.
7. **Projeyi kaydet** ile JSON kaydedin; **Proje aç** ile kaynak görsel olmadan da aynı katsayıları tekrar çizin. Kaynağı gömmek isterseniz analiz öncesinde ilgili kutuyu işaretleyin.
8. **PDF · PNG · JPEG · SVG dışa aktar** iletişim kutusunda biçimleri, boyut/DPI, JPEG kalitesi, arka plan, A4 yönü, ızgara/eksen/açıklamalar ve temiz şekil/akademik çıktı seçeneklerini belirleyin.
9. **Doğrulama veri kümesini çalıştır** düğmesi, analitik referansları ve gerçek deney tablolarını seçilen klasörde üretir.
10. **CAD: STEP · IGES · DXF** ile üç biçim, fiziksel birim/ölçek ve ayrı aktarım toleransı seçin. Her dosya yeniden açılır, geometri denetlenir ve eşlik eden `.cad.json` yazılır.
11. **Karmaşık veri · 40 × 4 tolerans taraması** düğmesiyle yerel manifesti ve ayrı sonuç klasörünü seçin. ε=1,2,3,5 taraması arka planda çalışır; tamamlanan koşular korunur. Aynı kod/ayarlarla aynı klasörden devam edilebilir.
12. **Araştırma · üç CAD pilotu** → **Hazırlık ve görevler** ile program yollarını kaydedin; görev paketi üretin/açın ve seçili kartı ölçüm formuna aktarın. Pilot kayıtlarını kaydedin, ayrı FreeCAD ürün deneyini çalıştırın veya aynı kaynaklı tolerans projelerini karşılaştırın. Gerçek kişi kaydı için onay ve göreve özgü kalite kontrolleri gerekir.

Arama alanında deterministik yöntem veya **Bütçeli simüle tavlama**, öneri bütçesi ve tohum seçilebilir. Tavlama yalnızca otomatik/köşe ailesini genişletir; küresel optimum kanıtlamaz. CPU işçisi 1–8, halkaların uzaklık değerlendirmesini paralelleştirir. **Seçili modeli kanıtlamayı dene** varsayılandır; **Sertifikalı sonuç zorunlu** kanıtlanamayan seçimleri reddeder. Aday tablosundaki **Kanıt**, analitik topoloji yeter koşullarını; **Geçti**, sayısal poligon denetimini belirtir. Hata sertifikasının sonucu ayrıca gösterilir.

Hesaplama ve disk kayıtları arka plandadır. Her dosya geçici konumda oluşturulur, gerçek biçimi tekrar açılarak doğrulanır ve ardından hedef atomik değiştirilir. Çoklu dışa aktarımın tamamı tek bir işlem değildir: sonraki biçim başarısız olursa daha önce tamamlanan dosyalar kalabilir; arayüz başarı bildirmez.

## Matematiksel yöntem

Uygulanan problem `min C(M)`, koşulları `E(Γ,M) ≤ ε` ve kaydedilmiş topoloji denetiminin geçmesidir. Aday aileleri:

| Aile | Uydurma / temsil | Kapsam |
| --- | --- | --- |
| Kesin çokgen | Piksel karelerinin açık kenarları; eşdoğrusal birleştirme | Kayba uğramamış normalize sınır |
| Sadeleştirilmiş çokgen | Üç RDP toleransı, ardından bağımsız ölçüm | Sonlu doğru parçaları |
| Çember / elips | Normalize koordinatlarda sayısal uydurma | Tam halkalar; elipste başlangıç artığı geometrik mesafe değildir |
| Kübik Bézier | Uçları sabit en küçük kareler ve uyarlamalı bölme | C0 birleşim; C1 zorlanmaz |
| Kübik B-spline | 8/16/32/64 örnekle periyodik interpolasyon | Basit iç düğümler, kayıtlı katsayı/düğümler |
| Karma | Doğru/rasyonel çember-elips yayı/Bézier yerel seçimi ve halka bazında aile birleştirme | Birleştirme tekrar doğrulanır |
| Köşe farkındalıklı karma | Çok ölçekli köşeler, doğru/Bézier kenar grafiği, bit maliyetli en kısa yol | Optimum yalnızca kurulan sınırlı grafiktedir |
| Kapalı Fourier | 4/8/16/32 harmonikli parametrik seri | Kapalı düzgün halka; hata/topoloji testi zorunlu |
| Temasları koruyan çokgen | Tam boş üçgen tanıklı yerel köşe silme | Temaslı düzlemsel çizge korunur; sınırlı açgözlü arama |
| Örtük polinom | Derece 2–12; normalize SVD, birim katsayı normu | Keşif amaçlı; sıfır dallarının tamlığı kanıtlanmadığından otomatik seçilmez |

Karma yerel arama sabit uçlu rasyonel çember ve elips yaylarını da inceler. Parabol/hiperbol uydurma, merkez hattı ve morfolojik temizleme eklenmedi.

**Sadelik**, sabit uzunluklu model kodlamasının bit maliyetidir. Parça, serbest parametre üst sayımı, kontrol/düğüm, derece ve aralık sayıları ayrıca gösterilir. Dengeli tercih `log2(1+C/Cmin)+(H/ε)²` kullanır. Hızlı H tablosu float64 hesabıdır. **Ayrı sertifika**, rasyonel B-spline→Bézier dönüşümü, Bernstein zarfları, tam konik rasyonel parametre kapsaması veya yeniden oynatılan boş üçgen tanığı kullanır. Pozitif ağırlıklı rasyonel karma yaylar da sertifika kapsamındadır; Fourier ve eski açısal yaylar kanıtlanmaz. [Sertifika kapsamı ve argümanı](docs/certification.md).

[Problem ve ölçüm tanımları](docs/mathematics.md) · [Aileler ve seçim](docs/model-selection.md) · [Sınırlamalar](docs/limitations.md).

## Çıktılar ve proje

Varsayılan çıktı kümesi: `model.json`, `equations.txt`, `reconstruction.png`, `reconstruction.jpg`, `reconstruction.svg`, `a4.pdf`.

- PDF: gerçek A4, dikey/yatay; kaynak/referans/model karşılaştırması, aday tablosu, bütün denklemler, aralıklar, parametreler, hata, ön işleme ve ortam bilgileri; uzun içerik çok sayfalıdır.
- PNG: 128–10000 piksel, 36–1200 DPI, beyaz/açık arka plan veya saydamlık.
- JPEG: aynı çizim seçenekleri; 1–100 kalite; seçilmiş opak arka plan.
- SVG: gerçek `line`, `circle`, `ellipse`, `path C`, `path A` elemanları; B-spline/Fourier/rasyonel konik yaylar kontrollü vektör poligonuyla verilir. Raster gömme yoktur. Yaklaşım toleransı metaveriye yazılır ve değerlendirme toleransını aşmaz.
- STEP / IGES / DXF: isteğe bağlı CAD eklentisi; kapalı profiller, fiziksel birim ve kaynak modelden ayrı aktarım denetimi. Varsayılan altı çıktı değişmez; CAD kutusundan ayrıca seçilir.
- JSON 2.3: kesin referans, topoloji ağacı, bütün aday katsayıları/aralıkları, hata/maliyetler, sertifika ve varsa silme tanığı, arama ayarları/tohum, seçilme nedeni, kaynak hash'i ve isteğe bağlı gömülü kaynak. Açılışta geometri, tanık ve sertifika tekrar denetlenir; uydurma yapılmaz. 2.0/2.1/2.2 okunabilir.

[Şema belgesi](docs/project-schema.md) · [Makine tarafından okunabilir JSON Schema](docs/project.schema.json).

## CLI ve Python API

```powershell
.venv/Scripts/python.exe -m sekilden_denkleme examples/square.png --output output/square
.venv/Scripts/python.exe -m sekilden_denkleme examples/ring.png --family auto --tolerance 3 --preference balanced --output output/ring
.venv/Scripts/python.exe -m sekilden_denkleme examples/rabbit.png --tolerance 2 --degree 6 --output output/rabbit
.venv/Scripts/python.exe -m sekilden_denkleme examples/complex_inputs/png/fa_snowflake.png --family adaptive --tolerance 2 --search annealing --search-budget 8 --seed 20261015 --workers 2 --certificate strict --output output/snowflake
```

```python
from sekilden_denkleme import AnalysisConfig, analyze
from sekilden_denkleme.project import save_project, load_project
from sekilden_denkleme.export import export_result

result = analyze("examples/ring.png", AnalysisConfig(family="auto", tolerance=3))
save_project(result, "output/project.json")
reopened = load_project("output/project.json")  # yeniden uydurma yok
export_result(reopened, "output/reopened")
```

CLI mevcut aynı adlı dosyaları yeniler. GUI çakışma onayı ister. Sürüm 1.0 kesin projeler açılabilir; eski yaklaşık projeler kesin referansı içermediği için yeniden analiz istenir.

## Doğrulama ve geliştirme

```powershell
.venv/Scripts/python.exe -m pip install -e '.[dev]'
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m sekilden_denkleme.benchmark examples/validation
```

Analitik veri kümesi kare, çokgen, çember, elips, bilinen Bézier, halka, birden fazla bileşen, köşe/eğri birleşimi, iki çizgi kalınlığı, serbest siluet ve tohumlu gürültü içerir. İdeal sürekli referans ve piksel sınırı ayrı ölçülür. 2.0 deneyinin ham sonuçları [CSV](examples/validation/results.csv) ve [JSON](examples/validation/results.json) olarak korunmuştur. [Eski deney kaydı](docs/validation.md) · [2.1 gerçek karşılaştırmaları](docs/improvements.md).

İnternetten indirilen 40 ek test şekli için [karmaşık girdi kataloğunu](examples/complex_inputs/README.md) kullanın. Uygulamada `examples/complex_inputs/png` klasöründeki PNG'leri açabilirsiniz. Kaynaklar, lisans kayıtları, dönüşümler ve gerçek analiz denemeleri aynı klasördedir.

Bağımlılıklar: NumPy/SciPy (sayısal işlem), Pillow (görsel), Shapely/GEOS (geometrik uzaklık ve topoloji), Matplotlib (çizim), ReportLab (sayfalama), pypdf (gerçek PDF doğrulaması), Tkinter (mevcut masaüstü kütüphanesi). Arayüz kütüphanesi değiştirilmedi. [Mimari](docs/architecture.md).

2.3 deneylerini yeniden üretmek için:

```powershell
.venv/Scripts/python.exe examples/validate_arcs.py --baseline-source .tmp/baseline-2.2/src
.venv/Scripts/python.exe examples/run_complex_grid.py examples/complex_inputs/manifest.json output/complex-grid --workers 4 --timeout 240
```

İlk betikte karşılaştırma için 2.2 kaynak ağacı gerekir; eski kaynak referansı
ve yeni taramanın tam kaynak kopyası [2.3 deney kaydında](docs/release-2.3.md)
açıklanır. Yeni sürüm/ortamla yeni sonuç klasörü kullanın. Hazır tablo ve
grafikler [tarama kataloğunda](examples/arc_stress/index.html), ham ölçümler
[JSON](examples/arc_stress/current_2.3/results.json) ve
[CSV](examples/arc_stress/results.csv) dosyalarındadır.

CAD eklentisinin teknik kurulumu ve doğrudan kullanım:

```powershell
.venv/Scripts/python.exe -m pip install -e '.[cad]'
.venv/Scripts/python.exe -m sekilden_denkleme examples/square.png --formats step iges dxf --cad-unit mm --cad-scale 0.1 --output output/cad
```

27 dosyalık okuyucu denemesi gerçek CAD kullanıcılarında zaman/düzeltme
kazanımı ölçümü değildir. İlk insan pilotu için boş kayıt ve görev protokolü
hazırdır; henüz katılımcı verisi yoktur. [2.4 sonuçları](docs/release-2.4.md).
