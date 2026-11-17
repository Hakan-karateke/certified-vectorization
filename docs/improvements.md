# 2.1 geliştirmeleri ve gerçek karşılaştırmalar

Bu sayfa 2.1'in tarihsel deney kaydıdır. B-spline/konik sertifikası ve geyikte temas koruyan sadeleştirme ile güncel sonuçlar [2.2 kaydındadır](release-2.2.md).

Önceki 2.0 raporundaki kar tanesi durumu yeniden üretildi: ε=2, boşluk=20, eşik=127, `auto/balanced`; `polygon-0.55` 469 doğru ve 198856 bit seçildi. Çemberin hesaplanan H üstü 203.097, elipsin 200.938, Bézier-0.65'in 2.0911 ve B-spline-64'ün 37.0506 idi. Küçük örnek artıkları veya daha geniş bir aile adı bu başarısızlıkları çözmez.

## Uygulanan değişiklikler

- Köşe farkındalıklı sonlu aday grafiği: çok ölçekli dönüş yönleri, zorunlu köşe düğümleri, doğru/kübik kenarlar ve bit maliyetiyle dinamik programlama. Yeni çekirdek mevcut bağımsız kabul testinden geçer.
- Bütçeli, tohumlu SciPy `dual_annealing`: köşe açısı ve yerel hata hedefini araştırır. Deterministik arama varsayılandır. Stokastik arama sonlu bütçede küresel optimum garantisi vermez.
- Dengeli tercihte maliyet aralığına göre normalizasyon yerine `log2(1+C/Cmin)+(H/ε)²`. Böylece çok pahalı kesin aday, bütün makul maliyetlerin birbirine benzer görünmesine yol açmaz. Bit maliyeti değişmedi.
- Kapalı parametrik Fourier ailesi, 4/8/16/32 harmonik. Köşeli şekli tek eğriye zorlama yoktur; aynı hata/topoloji testi uygulanır. Süperelips ve daha yüksek dereceli örtük polinomları kabul edilen ailelere eklemek yerine önce doğrulanabilir bu genişleme seçildi.
- Uzaklıklarda sonlu kenarlar için GEOS STRtree ve adaylar arasında ortak referans önbelleği. Birden fazla halka için 1–8 CPU işçisi. Tk olay döngüsü ayrı kalır. GPU bağımlılığı eklenmedi.
- Doğru/Bézier için dışa yuvarlanan aralık hata kapsaması ve rasyonel Bernstein/Jordan topoloji yeter koşulları. [Sertifika kapsamı ve argümanı](certification.md). Desteklenmeyen aileye kanıt bayrağı verilmez.
- Ayarlar, tohum, adaylar, kanıt ve sürümler JSON 2.1'e; masaüstü ve CLI denetimlerine; PDF ve denklem raporuna taşındı. 2.0 projeleri açılabilir.

## Deney sözleşmesi

Girdiler `examples/complex_inputs/png` altındadır; özgün kaynak/hash/lisans kayıtları aynı veri kümesinin manifestindedir. Bütün hatalar **normalize piksel sınırına** göredir; Font Awesome'ın ideal vektörüne göre ölçülmüş hata değildir. Varsayılan ayarlar, Windows 11 ve CPython 3.12.8 kullanıldı. Dört gerçek durum ölçüldü; 40 girdinin tamamı yeniden analiz edilmedi.

`before.json`, değişikliklerden önce aynı çalışan çalışma ağacında kaydedilmiş gerçek 2.0 sonuçlarıdır. `after.json` yeni otomatik aramanın gerçek sonuçlarıdır. Eski sürümün bir anlık görüntüsü betiğe gömülmedi; güncel kodda `before` adıyla betik çalıştırmak eski algoritmayı geri getirmez. Bu dosya etiketinin anlamı deneyin çalıştırıldığı sürümdür.

| Girdi / ε | Önce parça | Sonra parça | Sonraki seçim | Sonra hesaplanan H üstü | Aralık sertifikası |
| --- | ---: | ---: | --- | ---: | --- |
| Kar tanesi / 2 | 469 | 79 | adaptive-0.72 | 1.72550 | H ≤ 1.699942; topoloji kanıtlandı |
| Kar tanesi / 3 | 1673 | 58 | adaptive-0.72 | 2.55257 | H ≤ 2.402553; topoloji kanıtlandı |
| Bisiklet / 2 | 467 | 47 | adaptive-0.72 | 1.73965 | H ≤ 1.714102; topoloji kanıtlandı |
| MPEG-7 geyik / 2 | 4324 | 4324 | exact | 0 | Sıralı kenar özdeşliği |

Kar tanesi ε=2'de parça azalması **%83.16**, bit maliyeti 198856→43480 (**%78.13**). Model hem doğru hem Bézier içerir. Birleşimler C0'dır; keskin köşeler nedeniyle C1 zorlanmaz. Bu tek veri üzerinde önemli azalma, bütün çizimler için genelleme kanıtı değildir.

Geyik girdisinde 90 halka, noktasal temaslar ve küçük ayrıntılar vardır. Yaklaşık adaylar topoloji testini geçemedi; köşe grafiği ayrıca 768 düğüm sınırına ulaştı. Sadeleştirme başarılı diye raporlanmadı; kayıpsız kesin model korundu.

Seçim formülünün etkisi `selection-ablation.json` içinde, **aynı eski aday kayıtları** yeni dengeli tercihle seçilerek ayrılır. Kar tanesi ε2'de yalnızca tercih değişimi 469→201; yeni aileler eklenince 201→79 olur. ε3'te 1673→203→58, bisiklette 467→88→47 olur. Kazanımın tamamı eğri algoritmasına atfedilmez. Geometrik hata sütunları da değişir; daha az parça sıfır bedelle elde edilmez.

## Stokastik arama ve süreler

Kar tanesi ε=2, yalnızca `family=adaptive`, tavlama bütçesi 8, tohum 20261015 deneyi `annealing.json` içindedir. Gerçek üretilen öneriler, kabul durumları, parametreler ve süre kaydedilir. En az parça sayılı tavlama önerisi ile dengeli tercihin seçtiği öneri farklı olabilir: amaç fonksiyonları aynı değildir. Tavlama her çalışmada deterministik adaydan daha iyi sonuç vaat etmez.

Bu çalıştırma **44.87 saniye** sürdü; 8 öneri üretildi. Dengeli tercih **85 parça**, hesaplanan H üstü **1.54425**, sertifikalı H≤**1.518502** olan `annealing-6` adayını seçti. En az parçalı tavlama önerileri 71 parçaydı; deterministik `adaptive-0.84` zaten 69 parça sunuyordu. Bu deney tavlamanın parça sayısında ek kazanımını göstermedi; daha düşük hata için başka bir Pareto seçeneği üretti.

## 2.1 kabul kontrolleri

Windows 11 / CPython 3.12.8 üzerinde tam test kümesi: **65 geçti, 84.73 saniye**, atlanan test yok. `ruff check .` geçti; `ruff format --check .` 41 Python dosyasını uygun buldu. Yeni kontroller aralık işlemlerinin tam rasyonel karşılığını, gizli geri dönüşü reddetmeyi, delik içerilme ağacını, gerçek kar tanesini, CPU 1/2 eşitliğini, Fourier/SVG/proje tutarlılığını, tohumlu bütçeyi ve sıkı mod geri dönüşünü kapsar. Gerçek Tk olay döngüsünde yeni ayarların korunması, arka planda aday değiştirme, iptal, kayıt/açma ve dört görsel çıktı biçimi çalıştırıldı.

İki eski 2.0 proje ve yeni 2.1 kar tanesi projesi JSON Schema ile doğrulandı. Altı çıktı yeniden açıldı. SVG'de **40 gerçek line + 39 gerçek kübik path**, raster image yok; bütün kübik katsayılar kayıtlı modelle birebir eşit. PDF **19 A4 sayfa**, 79. parça ve sertifika değeri mevcut; bütün sayfalar Poppler ile rasterleştirildi, sayfa mozaiği ve örnek tam sayfalar incelendi, metin kutularında kenar taşması bulunmadı. [Dosya boyut/hash ve çıktı denetimi](../examples/improvements/output-validation.json). Temiz Windows kurulumu, Linux/macOS, GPU ve uzak CI bu çalıştırmayla doğrulanmış sayılmaz.

Eski/yeni dört tam analizde tek çalıştırma süreleri (saniye): kar tanesi ε2 **36.24 / 23.09**, ε3 **18.27 / 16.88**, bisiklet **11.45 / 30.28**, geyik **42.16 / 31.68**. Yeni süreler daha fazla aile ve seçili model sertifikasını içerir; eski sürümde sertifika yoktu. Arka plan yükü kontrol edilmedi, tekrar dağılımları alınmadı. Bu ölçüler her durumda hızlanma iddiasını desteklemez; bisiklet daha yavaştır.

`distance-benchmark.json`, aynı kaydırılmış sorgu noktalarıyla tek halkada beş tekrar, eski tam LineString uzaklığı ile önbellekli STRtree uzaklığını karşılaştırır. 4756 kenar ve 16528 sorguda ortanca süreler **0.35064 / 0.04805 saniye**, dizin kurma **0.00173 saniye**, ölçülen en büyük uzaklık farkı **0**. Bu dar mikrodeneyde yaklaşık 7.30 kat fark vardır; toplam uygulama hızlanması olarak sunulmaz. CPU işçi 1/2 eşitliği test edilmiştir; bütün girdilerde çok işçinin daha hızlı olduğu ölçülmemiştir.

## Yeniden üretim ve çıktılar

```powershell
.venv/Scripts/python.exe examples/compare_improvements.py after
.venv/Scripts/python.exe examples/render_improvement_examples.py
.venv/Scripts/python.exe examples/run_annealing_example.py
```

[Ham önce](../examples/improvements/before.json) · [Ham sonra](../examples/improvements/after.json) · [Karşılaştırma](../examples/improvements/comparison.png) · [Yeniden açılabilir kar tanesi projesi](../examples/improvements/snowflake/model.json) · [A4 rapor](../examples/improvements/snowflake/a4.pdf) · [Gerçek SVG](../examples/improvements/snowflake/reconstruction.svg).

Genel global optimum, genel cebirsel eğri tekillik çözümü, bütün aileler için sertifika, ideal sürekli şeklin bulunması, GPU ve farklı platform performansı tamamlandı diye sunulmaz. Sonuç, araştırma hedefinin açıkça sınırlandırılmış ve ölçülen bir uygulamasıdır.
