# Şekilden Denkleme 2.4 — araştırma, eğitim ve CAD aktarımı

15 Ekim 2026 tarihli yerel doğrulama: **144 test geçti**, atlanan test yok;
dokuz örnekten **27 gerçek STEP/IGES/DXF dosyası** üretildi ve yeniden açıldı.
Araştırma modelinin katsayıları, sonlu aralıkları ve kaynak sertifikası korunur;
CAD dosyasının aktarım denetimi ayrı tutulur. Gerçek CAD kullanıcılarıyla
kullanılabilirlik pilotu henüz yapılmadı.

## Tamamlanan işlevler

- Türkçe masaüstünden üç CAD biçimi, mm/cm/m/in birimi, fiziksel ölçek ve
  ayrı aktarım toleransı seçilebilir. Kayıt arka plandadır; analiz tekrarlanmaz.
- DXF R2013, yerel doğru/çember/yay/elips ve parametrik NURBS nesneleri üretir.
  STEP AP214 ve IGES, Z=0 düzleminde delikli yüzler üretir. Katı veya kalınlık
  varsayılmaz. Dış tel/delik yönleri +Z yüz normaliyle uyumludur.
- Doğru, konik, Bézier, B-spline ve rasyonel yaylar uygun yerel temsile çevrilir.
  Kırpılmış spline dış dalları taşımaz. Fourier için kontrollü poligon yaklaşımı
  ancak kullanıcı açıkça izin verirse yapılır.
- Her CAD dosyasına denklem, özgün katsayı/aralık, CAD katsayıları, birim,
  kaynak dönüşümü, parça eşlemesi, dosya hash'i ve ayrı denetim içeren
  `.cad.json` eşlik eder. Uygulama projesi `model.json` olarak ayrıca saklanır.
- Üç eğitim etkinliği ve gerçek pilot için boş oturum kaydı/protokol hazırdır.

Burada **parametrik DXF**, düzenlenebilir geometrik parametreler ve NURBS
kontrol noktaları/düğüm/ağırlıkları demektir. CAD ürününe özgü sürücü ölçüler,
teğetlik kısıtları veya özellik geçmişi oluşturulmaz. Araştırma uygulamasının
önceki altı çıktı biçimi ve JSON 2.3 proje sözleşmesi korunur.

## Matematiksel denetimin kapsamı

CAD kaydı, kaynak modelden ve gerçek okuyucuyla yeniden açılan dosyadan
tolerans kontrollü eğri poligonları oluşturur. İki yönde bütün sonlu kenarları
kapsayan dışbükey uzaklık tanıkları, eğri/poligon payları, birleşim ve Z sapması
ile bir aktarım üst tahmini hesaplar. Yalnız örnek noktalarında düşük artık
başarı sayılmaz. Her halka ayrı ele alınır; kapanış, basitlik, sınırlar arası
kesişim ve iç içelik karşılaştırılır. Uymayan aday kaydedilmez.

Bu hesap GEOS/binary64 kullanır: CAD dosyası için
`verified_numerical_certificate=false` ve
`analytic_isotopy_proven_for_cad_file=false` kalır. Kaynak modelin doğrulanmış
sertifikası varsa kendi kapsamında saklanır. Topoloji denetimi kontrollü
poligonların iç içelik denetimidir; CAD eğrilerinin analitik izotopi ispatı değildir.
[Yöntemin ayrıntısı, birimler ve başarısızlık sınırları](cad.md).

Çember STEP örneğinde, kullanıcı ölçeği 0.1 mm/koordinattır:

| Hata terimi | Gerçek değer |
|---|---:|
| Piksel sınırı → kaynak model, ölçeklenmiş sertifika üst sınırı | 0.101277145 mm |
| Kaynak model → yeniden okunan STEP, sayısal aktarım üst tahmini | 0.0025000001 mm |
| İki terimin toplamı, doğrulanmış aralık sertifikası olmayan tahmin | 0.103777145 mm |

Dolayısıyla 0.01 mm CAD aktarım toleransı, kaynak çizimin 0.01 mm doğrulukta
modellendiği anlamına gelmez. İdeal fiziksel nesneye uzaklık bilinmez;
fiziksel ölçek kullanıcı atamasıdır.

## Gerçek örnek sonuçları

Aşağıdaki tabloda tüm aktarım üst tahminleri karşılaştırılabilmesi için mm'ye
çevrilmiştir. Her kaydın hedefi 0.01 mm'dir. Ham dosyalarda özgün seçilmiş
birimler ve bütün katsayılar vardır. B/D, bağlı bileşen/delik sayısıdır.

| Örnek | Seçili model | Model parçası | B/D | DXF U (mm) | STEP U (mm) | IGES U (mm) |
|---|---|---:|---:|---:|---:|---:|
| Çember | circle-1 | 1 | 1/0 | 0.00250000 | 0.00250000 | 0.00250000 |
| Elips | ellipse-1 | 1 | 1/0 | 0.00250000 | 0.00250000 | 0.00999327 |
| İç boşluklu halka | circle-1 | 2 | 1/1 | 0.00250000 | 0.00250000 | 0.00250000 |
| Spline | bspline-16 | 1 | 1/0 | 0.00250000 | 0.00250000 | 0.00250001 |
| Köşe/eğri birleşimi | mixed-0.65 | 15 | 1/0 | 0.00971566 | 0.00971566 | 0.00971566 |
| Yuvarlatılmış dikdörtgen | mixed-0.65 | 12 | 1/0 | 0.00985934 | 0.00985934 | 0.00985934 |
| Ayrık bileşenler | hybrid | 5 | 2/0 | 0.00250000 | 0.00250000 | 0.00250029 |
| Bézier | bezier-0.65 | 4 | 1/0 | 0.00250000 | 0.00250000 | 0.00250000 |
| Fourier, açıkça izinli poligon yaklaşımı | fourier-8 | 1 | 1/0 | 0.00250000 | 0.00250000 | 0.00250000 |

İlk altı kaynak proje katsayılarından yeniden uydurma yapılmadan açıldı.
Son üç kaynak raster analizi gerçekten çalıştırıldı; süreleri ayrı kaydedildi.
Sekiz kaynak modelin sertifika durumu `proven`, Fourier'in `undetermined`'dır.
Bu sayılar CAD dosyasına doğrulanmış sertifika atamaz. Örnek projelerin kaynak
görselleri açıkça seçilen `--embed-input` ile gömüldü.

27 aktarımın yazma/gerçek okuyucuyla denetleme/kayıt süreleri toplam
**8.514 saniye**, medyan **0.223 saniye**, en uzun **1.408 saniye** oldu.
Uydurma, proje yükleme, karşılaştırma çizimi ve ZIP oluşturma bu süreye dahil
değildir. Tek yerel koşu, önbellek/ilk yükleme ve eşzamanlı test yükü içerir;
platformlar arası hız veya kullanıcı verimliliği karşılaştırması değildir.

Matematiksel sadelik ile CAD maliyeti de ayrı ölçülür. Fourier örneğinde tek
matematiksel parça **2376 bit** model maliyetine sahiptir; izinli yaklaşımı
638 poligon köşesi kullanır. DXF bir LWPOLYLINE nesnesiyle **49,915 byte**,
STEP 637 kenarla **521,639 byte**, IGES 637 kenarla **159,651 byte** tutar.
Tek denklem, küçük veya kolay düzenlenen CAD dosyası garantisi vermez.
Her eşleme kaydındaki `cad_complexity` bu farkı görünür kılar.

[Örnek kataloğu ve karşılaştırma görselleri](../examples/cad_validation/index.html) ·
[Ham JSON](../examples/cad_validation/results.json) ·
[Ham CSV](../examples/cad_validation/results.csv) ·
[27 dosyalık pilot paketi](../examples/cad_validation/cad-pilot-pack.zip).

## Çalıştırılan testler ve ortam

Son tam koşu: `pytest -q -rs --basetemp=.tmp/pytest-final-cad24`,
**144 passed in 160.82s**, sıfır hata ve sıfır atlama. Kapsam:

- Önceki analiz, kesin sınır, model seçimi, sertifikasyon, proje ve altı çıktı testleri.
- Gerçek üç biçimde konik/rasyonel yay/Bézier/spline aktarımı ve JSON Schema doğrulaması.
- mm/cm/m/in birimlerinde gerçek DXF parametreleri ve STEP/IGES yüz alanları.
- Yeniden okunan STEP/IGES halkasının 5 mm gerçek OCCT ekstrüzyonunda geçerlilik
  ve hacim; deliğin alan/hacimden düşmesi. Bu test masaüstü CAD ürünü testi değildir.
- Üç seviyeli dış sınır/delik/iç ada: üç biçimde halka/bileşen ilişkisi;
  STEP/IGES yüz alanının siyah piksel alanına uyması.
- Sonlu spline aralıkları, eksenleri yer değiştirmiş elips yayı ve ters yön.
- Fourier izni, eksik bağımlılık, temas/açık eklem reddi ve bozulan yeniden okuma.
- İkinci dosya yazma hatasında mevcut CAD/JSON çiftini geri alma.
- Gerçek Tk olay döngüsünde mevcut masaüstü akışı ve üç CAD biçiminin arka planda kaydı.

Ortam: **Windows 11 (10.0.26300), Python 3.12.8**, uygulama 2.4.0;
NumPy 2.5.4, SciPy 1.18.1, Shapely 2.2.0, ezdxf 1.4.4,
cadquery-ocp-novtk/proxy 7.9.3.1.1 (OCCT API 7.9.3.1).
VTK veya tam CadQuery eklenmedi; CAD modülleri isteğe bağlı ve geç yüklenir.

STEP/IGES yazıcı ve okuyucuları aynı OCCT ailesindendir; DXF için ezdxf
kullanıldı. Alan/hacim ve bağımsız model geometrisi kontrolleri eklenmiş olsa da
AutoCAD/FreeCAD/SolidWorks arayüzlerinde gerçek içe alma/düzenleme ölçülmedi.
Linux/macOS, başka Python sürümleri ve temiz makinede Windows kurulum betiğinin
çift tıklama akışı bu turda doğrulanmadı. Windows/Python 3.12.8 bağımlılık
kurulumu ve mevcut ortamda masaüstü olay döngüsü çalıştırıldı.

## Yeniden üretme ve sonraki ölçüm

```powershell
.venv/Scripts/python.exe -m pip install -e '.[cad,dev]'
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe examples/validate_cad.py --embed-input
```

Test edilen CAD paketleri [sabit sürüm kaydındadır](../requirements-cad-tested.txt).
Ham sonuçlar kaynak ağacı SHA-256'sını içerir; [doğrulama kaydı](../examples/cad_validation/verification.json)
ve [kaynak kopyası](../examples/cad_validation/source.zip) bu koşuya eşlik eder.
CAD başlıklarındaki zaman damgaları nedeniyle yeniden üretimde byte hash'inin
aynı olması beklenmez; katsayılar, birimler ve geometrik denetimler karşılaştırılır.

İlk gerçek kullanıcı denemesi için [pilot protokolü](cad-pilot.md),
[boş oturum şablonu](../examples/cad_validation/pilot-template.json) ve
[araştırma/teknik eğitim etkinlikleri](education-cad.md) hazırdır. Katılımcı
sayısı şu anda sıfırdır. Sonraki kanıt, aynı kalite hedefinde gerçek CAD
kullanıcılarının mevcut yöntemiyle eşleştirilmiş düzeltme sayısı ve süredir.
