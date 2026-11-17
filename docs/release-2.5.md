# Şekilden Denkleme 2.5 — üç CAD hedefi, ölçülebilir pilot ve araştırma raporu

Yerel son tam test: **176 geçti, 0 hata, 0 atlama; 198.22 saniye**.
Yeni sürümle yeniden aktarılan **27/27 CAD dosyası**, ayrı **FreeCAD 1.1.4**
uygulamasının başsız içe alma/profil/5 mm ekstrüzyon kontrollerini geçti.
**AutoCAD ve SolidWorks çalıştırılmadı; gerçek insan katılımcı sayısı sıfırdır.**
Bu iki ürün ve insan kullanılabilirliği için yazılım hazırdır; sonuç uydurulmadı.

## Tamamlanan geliştirmeler

Ana penceredeki **Araştırma · üç CAD pilotu** şu üç sekmeyi açar:

- **Pilot oturumları:** FreeCAD/AutoCAD/SolidWorks, gerçek sürüm/OS, takma
  katılımcı kodu/onay, deneyim, mevcut yöntem, şekil/fiziksel hedef, tekrar/sıra,
  görev, kalite toleransı, süre sınırı, monotonik kronometre veya elle süre,
  düzeltme sayısı/türleri, Evet/Hayır/Bilinmiyor kalite kontrolleri ve kanıt hash'i.
- **CAD uyumluluğu:** CAD/JSON eşleme hash'ini ve fiziksel hedefi gösterme;
  kullanıcı seçimiyle ayrı FreeCADCmd sürecinde gerçek ürün deneyi, iptal ve
  süre/kaynak sınırları, JSON/HTML ve yerel `.FCStd` belgeleri.
- **Araştırma karşılaştırması:** mevcut adaylar veya en çok 32 kayıtlı projede
  hata, bit maliyeti, parça/parametre/kontrol/düğüm/derece, ayrı sayısal ve
  sertifikalı üst sınır, Pareto ve ret nedenlerini yeniden uydurmadan raporlama.

Pilot çalışma JSON'u sürüm 1.0 / protokol 1.1'dir; uygulama proje şeması
2.3 ve CAD eşleme şeması 1.0 korunur. Eğitim kayıtları insan verisinden ayrıdır.
Yalnız eşleşen başarılı insan çiftleri karşılaştırılır; ürün/sürüm/OS/şekil/
görev/tolerans/süre sınırı ayrı tutulur. Eksik, başarısız, süre aşan ve uygulama
sırası belirsiz çiftler özet medyanına katılmaz. Ham veriler raporda kalır.

Çalışma yeniden açılabilir; form ve diske kayıt aşamaları ayrıdır. Eski veri
başarısız açma/yazmada korunur. Ana pencere kaydedilmemiş pilot kayıtları/form
veya yürüyen pilot işi varken sessizce kapanmaz. Analiz modeli değişmez.
Kayıtlar değiştirilemez/imzalı bir denetim günlüğü değildir; operatör beyanıdır.

[Masaüstü kullanım kılavuzu](pilot-workspace.md) · [Pilot JSON Schema](pilot.schema.json).

## Gerçek uyumluluk hatası ve düzeltmesi

2.4'teki çok bileşenli IGES, OCCT tarafından bir **402 grup** kökü ve bu gruba
bağlı yüzler olarak yazılıyordu. FreeCAD 1.1.4'ün `Import.insert` akışı bu
dosyayı geometri içermeyen belge olarak açtı. Birimi metre yerine mm yapmak
tek başına sorunu gidermedi. Sorun fiziksel ölçek olarak etiketlenmedi.

2.5 yazıcısı her ayrık yüzü ayrı IGES kökü olarak ekler; dış/iç teller ve fiziksel
ölçek korunur. Aynı kaynak model, aynı katsayılar, aynı metre birimi ve tolerans
ile **iki yüz/iki katı, sıfır delik** FreeCAD kontrolünü geçti. Eski 2.4 dosyası
son deneyde ayrıca açıldı ve beklenen boş belge hatasını yeniden verdi.
Önceki 2.4 dosyaları/ölçümleri değiştirilmedi; yeni dosyalar ayrı klasördedir.

Deney düzeni de gerçek ürün davranışına göre sınandı: FreeCAD `App::Origin`
eksen/düzlemleri ve `App::Part` sanal Shape'i içe alınan geometri sayılmaz.
Yerel `Part::Feature` geometrisi kullanılır. Bu, kullanıcı dosyasını onarma
değil, ürün belgesindeki yardımcı nesneleri doğru ayırma işlemidir.

## Hacim ve hata kapsamı

Spline STEP örneğinde FreeCAD'in varsayılan `Volume` özelliği
**14191.85109849 mm³** verdi. Kaynak referans poligonunun alanı × 5 mm
**14142.31948940 mm³**; ürünün yönlü yüz ağı üzerinden tetrahedron toplamı
**14142.48088357 mm³** oldu. İki ağ yoğunluğu arasındaki fark
**0.13765796 mm³** idi. Varsayılan hacim sonucu silinmedi; ham ölçümde saklanır.

Hacim kontrolünde FreeCAD'in kendi ekstrüzyonundan iki deflection yoğunluğunda
üçgenler alınır, yönlü tetrahedron hacimleri toplanır. İki yoğunluğun farkı
ve referans alan/hacimle uyumu denetlenir. Bu, varsayılan tek hacim sayısını
kesin doğru saymayı önler; **iki ağın yakın olması matematiksel yakınsama
ispatı değildir**. Alan ve hacim kabul payı kaynak kontrollü poligon çevresi
ve seçilmiş aktarım toleransından türetilir; sayısal tutarlılık testidir.

Eğri karşılaştırması, kaynak kontrollü poligonu ile FreeCAD'in
`Edge.discretize(Deflection)` çıktısındaki bütün sonlu kenarları iki yönde
kapsar. FreeCAD deflection hedefi doğrulanmış zarf ispatı sayılmaz; sonuç bu
örnekleme sözleşmesine bağlı bir sayısal üst tahmindir. `verified_numerical_certificate`
false kalır. Kaynak modelin aralık sertifikası ayrı kapsamda korunur.

## Çalıştırılan ürün deneyi

Dokuz kaynak proje katsayılarından açıldı; görselden yeniden uydurma yapılmadı.
Özgün mm/cm/m/in eşlemeleri ve 0.01 mm eşdeğer aktarım hedefi korundu.

| Şekil | DXF | STEP | IGES | Bileşen/delik |
|---|---|---|---|---:|
| Çember | Geçti | Geçti | Geçti | 1/0 |
| Elips | Geçti | Geçti | Geçti | 1/0 |
| Halka | Geçti | Geçti | Geçti | 1/1 |
| B-spline | Geçti | Geçti | Geçti | 1/0 |
| Köşe/eğri karışımı | Geçti | Geçti | Geçti | 1/0 |
| Yuvarlatılmış dikdörtgen | Geçti | Geçti | Geçti | 1/0 |
| Ayrık bileşenler | Geçti | Geçti | Geçti | 2/0 |
| Bézier | Geçti | Geçti | Geçti | 1/0 |
| Fourier, açıkça izinli poligon yaklaşımı | Geçti | Geçti | Geçti | 1/0 |

Geçiş koşulları: fiziksel kutu, bileşen/delik sayısı, kapanış/geçerlilik,
alan, 5 mm ekstrüzyon geçerliliği/katı sayısı, sayısal hacim/ağ tutarlılığı ve
sayısal eğri karşılaştırması. DXF için tellerden yüz oluşturma açık hazırlama
adımıdır; dosyanın zaten yüz veya native sketch getirdiği varsayılmaz.

Eğri düzenleme mikrodeneyi varsa içe alınan çember/spline **kopyasında**
yapılır. Diğer türlerde `not_applicable` yazılır. Bu mikrodeney GUI'de
parametrik sketch veya özellik geçmişi düzenlenebilirliği testi değildir.

Yalnız içe alma süreleri toplam **10.013 saniye**, medyan **0.270 saniye**,
en uzun **0.638 saniye** oldu. İçe alma dışındaki süreç açılışı, dışa aktarım,
örnekleme, hacim kontrolü, belge/rapor kaydı bu sayılara dahil değildir.
Önbellek ve eşzamanlı test yükü olan tek Windows koşusudur; başka ürünlerin
hızıyla veya insan işiyle karşılaştırılmaz.

[Gerçek ürün sonuçları](../examples/cad_product_validation/index.html) ·
[Ham JSON ve eski IGES regresyonu](../examples/cad_product_validation/results.json).

## Araştırma/eğitim örnekleri

Aynı çember rasterinde ε=1,2,3,5 için otomatik/dengeli/sıkı sertifika koşuları
gerçekten çalıştırıldı. Gömülü kaynaklı projeler, bütün adayları içeren HTML/JSON,
kabul edilmiş adayların hata/bit grafiği ve gerçek süreler ayrı saklanır.
Bu deney ideal sürekli çembere hata veya öğrenme kazanımı ölçmez.

| ε | İncelenen/kabul edilen aday | Seçim | Bit | Örnek H | Sayısal U | Sertifika U | Analiz s |
|---:|---:|---|---:|---:|---:|---:|---:|
| 1 | 21/12 | circle-1 | 392 | 0.725453 | 0.900453 | 0.887880 | 52.617 |
| 2 | 21/19 | circle-1 | 392 | 0.725453 | 1.025453 | 1.012771 | 7.652 |
| 3 | 21/19 | circle-1 | 392 | 0.725453 | 1.150453 | 1.012771 | 4.836 |
| 5 | 21/20 | circle-1 | 392 | 0.725453 | 1.275453 | 1.012771 | 3.960 |

Bu örnekte dört koşu da aynı çember katsayılarını seçti. U değerlerinin
değişmesi aynı geometrinin hatasının arttığı anlamına gelmez; ölçüm/sertifika
bölme yoğunluğu ve bütçesi ε'ye bağlıdır. Süreler tek koşudur; özellikle ilk
koşu eşzamanlı tam test ve CAD deney yüküyle çakıştı. Bu tablo hızlanma veya
toleransın süreye nedensel etkisi iddiası için kullanılmaz.

Boş pilot çalışma dosyası ve raporu insan/deneme sayısını sıfır gösterir.
Birim testlerindeki yapay insan fikstürleri ve Tk otomasyonundaki eğitim
kayıtları pilot sonuçlarına aktarılmaz.
[Örnekler](../examples/pilot_workspace/index.html).

## Test ve platform kapsamı

Son tam koşu `pytest -q -rs --basetemp=.tmp/pytest-final25b`:
**176 passed in 198.22s**, atlama yok. Önceki 144 teste ek olarak pilot
onay/kalite/süre, çift eşleme, bozuk şema, atomik kayıt, kanıt hash'i,
HTML/CSV kaçırma, referans/sertifika ayrımı, ürün ölçek/delik reddi, süreç
iptali, gerçek FreeCAD içe alma/IGES regresyonu/spline hacmi ve iki yeni
gerçek Tk kabul akışı sınandı. Dört GUI testi kendi Python/Tk süreçlerinde
gerçek olay döngüsü kullanır; alt süreçte atlama başarıya çevrilmez.

Uygulama: Windows 11 / Python **3.12.8**, sürüm **2.5.0**.
Ürün: FreeCAD **1.1.4**, kendi Python'u **3.11.14**, OCCT **7.8.1**.
Yazıcı: cadquery-ocp-novtk/proxy **7.9.3.1.1**, OCCT **7.9.3.1**;
DXF: ezdxf **1.4.4**. Ayrı uygulama ve farklı OCCT sürümleri çalıştırıldı;
**bağımsız geometri algoritması/çekirdeği doğrulaması değildir**.

FreeCAD'in [resmî 1.1.4 taşınabilir yayını](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4)
D: üzerindeki proje geçici klasöründe açıldı. İndirilen 7z SHA-256 değeri:
`4828741fc91ee37fafcdb97a1abacb18b04ba451ac4372d9ff7a7349b36f4d6d`.
Kullanıcı/veri/geçici yolları önceden oluşturulur; FreeCAD'in
[taşınabilir ortam sözleşmesi](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Start_up_and_Configuration.md)
ve çalıştırılan sürümün gerçek API'si kullanılır. `Volume` özelliğinin varsayılan
OCCT hesabı [sürüm kaynağında](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Part/App/TopoShapePyImp.cpp)
görülebilir; rapordaki hacim farkı yerel ölçümdür.

FreeCAD GUI kullanımı, AutoCAD/SolidWorks, gerçek katılımcı pilotu, temiz
makinede çift tıklamalı kurulum, Linux/macOS ve diğer Python sürümleri bu
turda doğrulanmadı. AutoCAD/SolidWorks kurulumu D: üzerinde tamamlandığında
aynı [pilot görevleri](cad-pilot.md) ve kayıt ekranı kullanılabilir.

## Yeniden üretme

```powershell
.venv/Scripts/python.exe -m pytest -q -rs
.venv/Scripts/python.exe examples/validate_cad_products.py --freecad D:/CAD/FreeCAD/bin/FreeCADCmd.exe --reexport
.venv/Scripts/python.exe examples/validate_pilot_workspace.py
```

FreeCAD yolunu gerçek kurulumunuzla değiştirin; uygulamadan da dosya seçilebilir.
FreeCAD paketi/kurulu ortam dağıtım ZIP'ine eklenmez. Ham sonuçlar kaynak ağacı
hash'ini, ürün sürümünü, CAD hash'lerini ve işlem günlüklerini taşır. Aynı
katsayılar yeniden üretilebilir; tarih damgalı CAD/FCStd byte hash'lerinin yeni
koşuda aynı olması beklenmez. Kaynak kopyası ve doğrulama kaydı örnek paketine
eşlik eder. Gerçek pilotun sıradaki ölçümü, aynı kalite hedefinde üç üründeki
düzeltme sayısı ve eşli görev süresidir.
