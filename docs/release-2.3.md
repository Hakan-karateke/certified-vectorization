# 2.3 — Rasyonel karma yaylar ve karmaşık veri taraması

## Uygulanan değişiklik

Karma yerel uydurma artık sonlu doğru, ortak uçlu rasyonel çember yayı,
rasyonel elips yayı ve kübik Bézier önerir. Çember merkezi/açısı üzerinden
hesaplanan yaklaşık uçların tam C0 kanıtına yetmemesi giderildi. Çemberde
A,B,bulge; elipste A,P,B,pozitif ağırlık asıl katsayılardır. Ayrı merkez/açı
önbelleği tutulmaz. Ağırlıkların pozitifliği ve tam rasyonel homojen alt bölme,
mevcut dışbükey zarf/Jordan denetiminin karma yaylara uygulanmasını sağlar.
[Formüller ve yeter koşul argümanı](certification.md).

Doğru/Bézier/B-spline, yeni rasyonel konik yaylar ve tam kanonik konikler aynı
model sözleşmesinde kalır. Küresel optimum, bütün ailelerde topoloji çözümü
ve koşulsuz donanım garantisi iddiası yoktur. Eski açısal projeler aynı geometriyle
okunur; açık açısal yaylara yeni kanıt etiketi verilmez. Şema 2.3, sertifika 1.3;
2.0–2.2 okunabilir. Yeni paket bağımlılığı eklenmedi.

GUI'de **Konik yaylı karma** ailesi ve **Karmaşık veri · 40 × 4 tolerans taraması**
düğmesi vardır. Tarama, normal modeli değiştirmeden arka planda çalışır;
iptal çalışan süreçleri kapatır, atomik tamamlanmış kayıtları korur. Aynı
kod/ayar/ortam parmak iziyle devam eder. Farklı sürümde ayrı sonuç klasörü gerekir.

## Deney yöntemi

15 Ekim 2026, Windows 11 / Python 3.12.8, 16 mantıksal CPU. Manifestteki 24 MPEG-7
ve 16 Font Awesome girdisi, ε=1,2,3,5 ile toplam 160 koşuda denenir. Kaynak SHA-256
her çalıştırmadan önce doğrulanır. Eşik127, boşluk20, threshold_then_nearest,
otomatik aile, dengeli tercih, deterministik arama; süreç başına bir ölçüm
ve BLAS işçisi, toplam dört analiz süreci. Süre sınırı iş başına 240 saniyedir.
Varsayılan `selected` analizinden sonra **aynı uydurulmuş adayların kopyasında**
`strict` yeniden seçim yapılır. Uydurma tekrarlanmaz; iki süre ayrı kaydedilir.

Başarı, algoritmanın sonuç üretmesidir; bütün adayların kabul edildiği anlamına
gelmez. `proven` hata ve analitik topoloji koşullarının birlikte geçtiğini
belirtir. Kesin referansa geri dönüş ayrıca sayılır. Geometrik hata raster
piksel sınırına göredir; bu 40 girdinin ideal sürekli referansı bilinmiyor.
RMS/alan örneklenmiş veya poligonlaştırılmış tanılardır. Belirsizlik ve süre
sınırı ölçümden ayıklanarak saklanmaz; ayrı durum olarak raporlanır.

Ham [manifest](../examples/complex_inputs/manifest.json), kaynak/lisans ve
atfetme kayıtları mevcut girdi klasöründe korunur. MPEG-7 kaynak sayfasında
belirli yeniden dağıtım lisansı bulunmadığı kaydı değişmez; yeni lisans iddiası
yapılmaz. Yeni görsel indirilmedi veya ön işlemede geometri temizlenmedi.

İş/analiz süreleri eşzamanlı yük altında ölçülür; tek kullanıcılı etkileşim
gecikmesi veya 2.2→2.3 hızlanması olarak yorumlanmaz. Önceki sekiz koşu farklı
zaman aralığında çalışmıştır. Karşılaştırmada aynı girdi/tolerans ve belgeli bit
maliyeti esas alınır. Küçük veri kümesinin sonucu genelleme kanıtı değildir.

## 40 × 4 taramasının gerçek sonuçları

**160/160 analiz tamamlandı; analiz hatası veya 240 saniye süre aşımı yok.**
Varsayılan seçimlerde 132 kanıtlandı, 28 belirsiz kaldı. Sıkı yeniden seçimde
160 kanıtlandı; bunların **44'ü kesin referans**, **116'sı yaklaşık model**.
Belirsiz 28 seçimin 9'u Fourier ailesinin desteklenmemesi, 19'u Bernstein/Jordan
yeter koşullarının sağlanmaması nedeniyledir. Belirsizlik yanlış geometri
kanıtı değildir; sıkı modda kabul edilmez.

| ε | Analiz | Varsayılan kanıt | Varsayılan kesin | Sıkı kanıt | Sıkı kesin | Sıkı yaklaşık | Varsayılan / sıkı medyan parça |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 40/40 | 38/40 | 24 | 40/40 | 26 | 14 | 1116.5 / 1116.5 |
| 2 | 40/40 | 34/40 | 10 | 40/40 | 12 | 28 | 76 / 103.5 |
| 3 | 40/40 | 31/40 | 2 | 40/40 | 5 | 35 | 47 / 51 |
| 5 | 40/40 | 29/40 | 0 | 40/40 | 1 | 39 | 38 / 44.5 |

ε=1'de 26/40 sıkı sonuç kesin referanstır. Bu veri kümesinde küçük toleransta
kompakt yaklaşım başarısı sınırlıdır. ε=5'te bile bir kesin dönüş vardır.
Sertifika oranını tek başına sadeleştirme başarı oranı diye kullanmak doğru olmaz.
Sıkı sonuçlarda yöntemler: 87 rasyonel Bernstein/Jordan, 11 tam konik kapsama,
18 yeniden oynatılmış boş üçgen çizge tanığı, 44 referans özdeşliğidir.

| ε | Varsayılan medyan bit | Sıkı medyan bit | Analiz p50 / p95 (s) | Ek sıkı seçim medyanı (s) |
|---:|---:|---:|---:|---:|
| 1 | 473396 | 473396 | 18.235 / 51.289 | 0.004 |
| 2 | 42328 | 57588 | 15.051 / 45.898 | 1.316 |
| 3 | 25392 | 29240 | 11.008 / 38.603 | 2.121 |
| 5 | 20804 | 24624 | 7.512 / 21.344 | 2.123 |

Analiz süreleri toplamı 2739.924 s, ek sıkı seçim toplamı
513.533 s; başlatma/kopyalama dahil iş süreleri
toplamı 3548.765 s'dir. Bu toplamlar dört eşzamanlı iş nedeniyle
geçen duvar süresi değildir. Toplam rapor dosyasındaki `invocation_wall_seconds`,
sonuçların yeniden uydurmadan ara kayıtlardan birleştirilme süresidir;
bütün deneyin çalışma süresi olarak kullanılmaz. İlk komutun ilerleme çıktısında
Windows cp1254'ün ε karakterini yazamaması bir konsol hatası oluşturdu;
tüm 160 çocuk işin atomik kayıtları tamamlandı. UTF-8 başlatıcı düzeltildi ve
aynı parmak iziyle ara kayıtlar birleştirildi; hiçbir ölçüm yeniden etiketlenmedi.

![Tolerans, parça sayısı, süre ve sertifika](../examples/arc_stress/summary.png)

## Önceki 2.2 sürümüyle eşleştirilmiş karşılaştırma

Dört girdi × ε=2,3 = sekiz gerçek eski koşu çalıştırıldı.

| Girdi | ε | Varsayılan parça 2.2→2.3 | Sıkı parça 2.2→2.3 | Sıkı bit 2.2→2.3 |
|---|---:|---:|---:|---:|
| fa_anchor | 2 | 41→41 | 41→41 | 23784→23784 |
| fa_anchor | 3 | 32→32 | 32→32 | 18432→18432 |
| fa_bicycle | 2 | 47→47 | 47→47 | 26840→26840 |
| fa_bicycle | 3 | 42→42 | 42→42 | 22416→22416 |
| fa_snowflake | 2 | 79→79 | 79→79 | 43480→43480 |
| fa_snowflake | 3 | 58→58 | 58→58 | 31504→31504 |
| mpeg7_bat | 2 | 580→579 | 1065→1065 | 451560→451560 |
| mpeg7_bat | 3 | 116→113 | 324→324 | 137376→137376 |

Bu sekiz otomatik/sıkı seçimde parça ve bit maliyeti **değişmedi**. Varsayılan
yarasada ε=2 için 580→579 ve ε=3 için 116→113 parça bulundu; bu varsayılan
seçimlerin kanıt durumu ayrıca ham kayıttadır. Sonuçlar genel veya radikal bir
sadelik kazanımı göstermiyor. Yeni yetenek, yerel karma yayların tam uçlu
sertifika kapsamıdır; yukarıdaki üç kontrollü örnek bunu ayrı ölçer.

## Sertifikalı karma örnekler

![Üç karma model](../examples/arc_stress/illustrations/comparison.png)

Aşağıdaki üç analizde aile `mixed`, ε=3, boşluk0, daha sade tercih ve sıkı
sertifika kullanıldı. U, doğrulanmış simetrik Hausdorff üstüdür; ideal şekle
uzaklık iddiası değildir. Kaydedilmiş modeller [örnek klasöründedir](../examples/arc_stress/illustrations).

| Girdi | Referans kenarı | Model parçası | Bit | Doğrulanmış U | Türler |
|---|---:|---:|---:|---:|---|
| circle | 1404 | 4 | 1952 | 1.260153 | 4 circle_arc |
| corner_curve | 576 | 15 | 7384 | 2.181546 | 1 circle_arc, 3 bezier, 10 line, 1 ellipse_arc |
| rounded_rectangle | 468 | 12 | 5344 | 1.253365 | 8 line, 4 circle_arc |

Aynı yerel `mixed-0.65` adayının 2.2 ve 2.3 karşılaştırması:

| Girdi | 2.2 parça / bit / kanıt | 2.3 parça / bit / kanıt |
|---|---|---|
| circle | 2 / 784 / undetermined | 4 / 1952 / proven |
| corner_curve | 15 / 7352 / undetermined | 15 / 7384 / proven |
| rounded_rectangle | 12 / 4960 / undetermined | 12 / 5344 / proven |

Bu tablo tüm otomatik aileler arasındaki en iyi seçimi değil, aynı yerel
karma adayını karşılaştırır. 2.2 çember yayı daha az bilgi kodlarken uçları
açısal katsayılardan yaklaşık üretir; tam birleşim sertifikası yoktur. 2.3
çemberi dört küçük yayla, aynı üç örneğin hepsini hata/topoloji kanıtıyla verir.
Yuvarlatılmış dikdörtgende sıkı `mixed-0.3` adayı 16→12 parçaya,
6400→6112 bite iner; `mixed-0.65` adayı ise aynı 12 parçada daha pahalıdır.
Bunlar koşullu yerel sonuçlardır; genel parça azalımı iddiası değildir.

## Yeniden üretim ve dosyalar

[Ham 160 koşu](../examples/arc_stress/current_2.3/results.json),
[tek tek ara kayıtlar](../examples/arc_stress/current_2.3/cases),
[CSV](../examples/arc_stress/results.csv),
[özet](../examples/arc_stress/summary.json) ve
[filtrelenebilir katalog](../examples/arc_stress/index.html).

`examples/run_complex_grid.py` ölçümleri; `examples/summarize_arc_stress.py`
CSV/özet/grafikleri; `examples/validate_arcs.py` üç örnek model ve gerçek biçim
çıktılarını üretir. Betikler depodan çalıştırılır. Önceki 2.2 kaynakları
`331284eff463edc35385b0b1c5e30a01c1d431f5` Git kaydından alınmıştır;
karşılaştırma betiğinde `--baseline-source <2.2-src-klasörü>` ile seçilir.
Yeni taramanın tam kaynak ağacı [benchmark-source.zip](../examples/arc_stress/benchmark-source.zip)
içindedir; kaynak özeti deney JSON'unda kayıtlıdır. Yeni kurulumda ZIP içindeki
src klasörünü PYTHONPATH'a koyarak aynı uygulama kodu seçilebilir; bağımlılık
sürümleri de ham provenans kaydındadır. Başka sürümde bit/süre eşitliği varsayılmaz.

### Sabit kaynak kaydı ve son sözleşme düzeltmeleri

160 koşu `5e4439342128b3847dfc4d95a1da50be0240de95a29705f1dfe501ccb1a5d643`
kaynak özetinde sabitlendi; ZIP bu kaynakları korur. Bu kayıttaki bağımsız
sertifikaların sürümü **1.3**'tür. `provenance.algorithm_settings.certificate_version`
etiketi eski **1.2** değerinde kalmıştı; ham ölçümler değiştirilmedi.
[Etiket düzeltme kaydı](../examples/arc_stress/provenance-erratum.json) bunu açıklar.
Son kaynak kopyası [final-source.zip](../examples/arc_stress/final-source.zip),
[doğrulama kaydı](../examples/arc_stress/verification.json) içindeki ayrı özete bağlıdır.
Son kod bu etiketi sertifika çekirdeğindeki tek sürüm sabitinden alır ve
`endpoint_rational_conics_certified_v5` algoritma adını kullanır.

Son hazırlıkta sonlu/artışı pozitif parametre aralığı denetimi, rasyonel yay
uç önbelleğinin katsayılarla tam eşleşmesi, tekrarlı manifest/tolerans reddi
ve doğrudan modül başlatıcısının UTF-8 çıktısı eklendi. Uydurma, geometrik hata,
maliyet ve seçim algoritmaları bu son değişikliklerde değiştirilmedi.
Dört eşleştirilmiş girdide ε=2,3 ile sekiz son sürüm koşusu ayrıca çalıştırıldı:
[son tekrar](../examples/arc_stress/final_recheck/results.json).
Seçilen id, parça/bit/parametre sayımları, örnek H, hesaplanan üst sınır,
RMS, alan farkı, sertifika durumu ve doğrulanmış U önceki taramayla **8/8 tam
eşleşti**. Süreler ve düzeltilmiş etiketler eşitlik sınamasının dışındadır.
[Denetim kaydı](../examples/arc_stress/final-recheck-validation.json).
160 koşunun tamamının son etiket düzeltmelerinden sonra yeniden uydurulduğu
iddia edilmez; sabit kaynak ve son tekrarların kapsamları ayrı saklanır.

## Gerçek testler ve sınırlar

Son tam test kümesi: **101 geçti**, **118.56 saniye**, atlanan test yok.
Önceki 97 testlik ilk koşu 196.06 saniyede geçmişti; son koşuya geçersiz
parametre aralıkları ve bir ULP uç önbelleği sapması için dört kabul testi eklendi.
Manifest kimliklerinin çıktı klasöründen kaçması da reddedilir; son bu
korumadan sonra tarama alt kümesi **3 geçti / 4.50 saniye** ile doğrulandı.
GUI'ye tarama bağlantısı eklendikten sonra gerçek Tk olay döngüsü testi ayrıca
**1 geçti / 8.99 saniye**: dosya seçimi, arka plan işi ve mevcut modelin korunması
sınandı. Taramanın gerçek çocuk süreç, hash değişikliği, devam ettirme ve süre
aşımı testleri tam kümededir. Çember kimliği tam Fraction işlemleriyle;
çember/elips sapması 30.001 gerçek eğri noktasıyla bağımsız GEOS uzaklığına
karşı; bir ULP birleşim açıklığı ve örtüşme olumsuz örnekleriyle test edilir.

Üç örnek projede JSON açma, katsayı eşitliği, sertifika tekrarı ve PNG/SVG
biçimleri doğrulanır. Köşe/eğri örneği ayrıca JPEG, TXT ve sekiz sayfalık A4 PDF
üretir. PDF Poppler ile sekiz sayfada görsel incelendi; PyMuPDF metin kutusu
incelemesinde sayfa dışına taşma bulunmadı. SVG raster gömmez; rasyonel yaylar
metaveride toleransı yazan kontrollü **vektör poligonu** olarak verilir.
Kaynak model rasyonel katsayılarla korunur; SVG yaklaşık gösterimdir.

Linux/macOS, farklı Python sürümleri, GPU ve temiz Windows kurulumu bu çalışma
kapsamında doğrulanmadı. Parametre araması sınırlı/sezgiseldir; parça/bit maliyeti
her örnekte azalmaz. Özellikle çemberde pozitif ağırlıklı küçük yay sözleşmesi
büyük yayları bölebilir. Tam çemberi otomatik ailede tek parça temsil eden önceki
aday korunur; karma aileyi zorlamak daha sade olduğunun kanıtı değildir.
