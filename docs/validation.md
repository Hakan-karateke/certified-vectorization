# 2.0 doğrulama ve deney kaydı

Bu sayfa **2.0 çalıştırmasının tarihsel kaydıdır**; aşağıdaki sayılar 2.1 yeniden ölçümü sayılmaz. Güncel köşe grafiği, sertifika, tavlama ve performans karşılaştırmaları [2.1 sonuçlarında](improvements.md) açıklanır.

Bu geliştirme **15 Ekim 2026**, Windows 11 x64 / **Python 3.12.8** üzerinde çalıştırıldı. Önceki sürümün Linux kaydı, bu sürümün doğrulaması olarak kullanılmadı. Aşağıdaki sayılar gerçek yerel çalıştırmalardandır.

## Testler ve dosya doğrulaması

- `pytest -q`: **52 geçti**, **57.68 saniye**, atlanan test yok. Mevcut 19 test korundu; çıktı kümesinin 6 dosyaya ve şemanın 2.0'a dönüşmesi için iki beklenti güncellendi.
- Eski 512 adet 3×3 maske kapsamı: bağımsız birim kenar kümesi, kenar tekilliği ve toplam işaretli alan eşitliği korundu.
- Gerçek raster kare/çember/elipste otomatik aile seçimi; bağımsız yoğun eğri örnekleriyle Bézier/B-spline/çember/elips düzleştirme sınırı; sonlu aralık dışı değerlendirme reddi; küçük bileşenlerin örneklenmesi sınandı.
- Kesişim, boşluk kaybı, içerilme ve belirsiz yakın temas reddi; C0 uçlar; iptal sırasında kısmi sonuç yayımlanmaması sınandı.
- EXIF yönü, ham/yönlü boyut ve iki yönlü koordinat matrisi doğrulandı.
- Kesin ve dört eğri ailesinde proje kaydet/aç sonrası katsayı/aralık değerlendirmesi aynı geometriyi üretti. Kaynak silindikten sonra çizim/dışa aktarım ve yeniden uydurma yapılmaması sınandı.
- Bozuk şema, yanlış uç, sahte kesinlik, sıfır yarıçap, sıfır polinomu, NaN, yanlış topoloji ve nesne olmayan JSON reddedildi. Gerçek proje Draft 2020-12 JSON Schema ile bağımsız doğrulandı.
- PNG/JPEG gerçek biçim, 640×640 boyut, DPI, saydamlık/opağa birleştirme; yerel SVG circle/C elemanları ve y dönüşümü; yatay A4 çok sayfalı PDF'de son parça ve bütün sayfa numaraları sınandı.
- Gerçek **Tk mainloop** içinde ön işleme, analiz, altı görünüm, parça inceleme, iptal, proje kaydet/aç ve PDF/PNG/JPEG/SVG/JSON/TXT kaydı tek kabul testinde tamamlandı. Sistem dosya iletişim kutuları testte deterministik seçimlerle değiştirildi; gerçek widget komutları ve işçi/ana döngü kullanıldı.
- `ruff check .`, `ruff format --check .`, `git diff --check`: geçti. Git'in CRLF dönüşümü uyarıları biçim hatası olarak raporlanmadı.
- CLI: kare örneği 1 sınır / 4 parça; altı dosya gerçekten üretildi ve tekrar açıldı.
- İki depolanmış örnek proje hem yayımlanan JSON Schema hem çalışma zamanı geometri denetimiyle açıldı.
- Örnek PDF'ler **5 + 9 = 14 A4 sayfasıdır**. İlk ve yoğun denklem sayfaları Poppler ile, bütün sayfalar PyMuPDF ile rasterleştirildi; görsel kontrol yapıldı. Sayfa dışına çıkan metin kutusu **0** bulundu. PyMuPDF yalnızca geliştirme QA aracıdır.
- Windows penceresinde görsel kontrol yapıldı. Sonraki bilgisayar kullanım denetimi fiziksel Escape ile durduruldu; devam eden UI otomasyonu yapılmadı. Ekrana göre başlangıç boyutu ve kaydırılabilir ayarlar düzeni yerel Tk kabul testiyle doğrulandı.

Ortam: NumPy 2.5.4; SciPy 1.18.1; Pillow 12.3.0; Matplotlib 3.11.2; Shapely 2.2.0; ReportLab 5.0.1; pypdf 6.20.1; pytest 9.1.1; Ruff 0.17.0; jsonschema 4.26.0. Tam Python/platform bilgisi deney JSON'undadır. Uzak CI ve temiz makinede kurulum betiğinin ilk çalıştırılması doğrulanmadı; Linux/macOS GUI yeniden çalıştırılmadı.

## Deney tasarımı

Komut:

```powershell
.venv/Scripts/python.exe -m sekilden_denkleme.benchmark examples/validation
```

Aynı işlem GUI'deki **Doğrulama veri kümesini çalıştır** düğmesinden yapılabilir. Girdiler `analytic_dataset` içindeki tam parametrik katsayılardan oluşturulur. Her piksel **merkezinde içerilme** ile rasterleştirilir; kaynak sürekli eğri 0.01 birim toleransla değerlendirilir. Çıktı `dataset/*.truth.json` dosyaları katsayıları, rasterleştirme sözleşmesini ve gürültü tohumunu içerir.

12 girdi: kare, çokgen, çember, dönük elips, bilinen kübik Bézier halkası, iç boşluklu halka, iki bağımsız bileşen, köşe/eğri birleşimi, ince ve kalın dairesel çizgi, serbest kübik siluet, 16 küçük tohumlu gürültü bileşeni eklenmiş çember. Gürültü tohumu **20261014**. Ana çalışmada rastgelelik yoktur.

Ayarlar: 1000×1000 kaynak; padding=0; eşik=127; ε=3; family=auto; preference=balanced; h≤0.75; δ=0.05; örtük derece=4; max_fit_points=1500. Her girdide 15 parametrik aday + 1 örtük polinom tanısı: toplam **192 kayıt**, **134 kabul edilmiş parametrik aday**. Bütün seçilen modeller kaydedilmiş topoloji denetimini geçti; eğrilerde kapsam kontrollü poligondur, analitik izotopi ispatı değildir.

Son tam deney süresi **35.88875 saniye**. Bu, veri oluşturma, analiz, karşılaştırma ve örnek dışa aktarımları içerir; bir kez ölçülmüştür. Aday `seconds` alanı o adayın uydurma + ölçüm süresidir; polinomda uydurma + ızgara tanısıdır. Referans çıkarımı ve diğer adaylar bu sayıya dahil değildir. Donanım/arka plan yükü kontrol edilmiş bir performans deneyi veya süre garantisi değildir.

## Seçilen modeller

H üst: piksel referansına göre hesaplanmış üst sınır. H ideal: sürekli analitik referansa göre **örneklenmiş** iki yönlü nokta-poligon mesafesi; her iki eğri 0.02 birim toleransla değerlendirilir, yay örnek aralığı ≤1'dir. H ideal bir sertifikalı üst sınır değildir. Bu iki sütun aynı başarı ölçütü değildir.

| Girdi | Seçilen aday | Parça | Serbest p. üst | Bit | Piksel H üst | İdeal H örnek |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Kare | exact | 4 | 16 | 1696 | 0.00000 | 0.00000 |
| Çokgen | bezier-0.3 | 36 | 288 | 24480 | 1.49935 | 1.06257 |
| Çember | circle-1 | 1 | 3 | 392 | 1.15045 | 0.04051 |
| Elips | ellipse-1 | 1 | 5 | 520 | 1.20982 | 0.05376 |
| Bézier | bezier-0.3 | 28 | 224 | 19040 | 1.42468 | 0.69831 |
| Halka | circle-1 | 2 | 6 | 784 | 1.17519 | 0.02744 |
| İki bileşen | hybrid | 5 | 19 | 2088 | 1.12912 | 0.02741 |
| Köşe/eğri | bezier-0.3 | 21 | 168 | 14280 | 1.41415 | 0.49095 |
| İnce çizgi | ellipse-1 | 2 | 10 | 1040 | 1.18700 | 0.04751 |
| Kalın çizgi | circle-1 | 2 | 6 | 784 | 1.16436 | 0.01161 |
| Serbest siluet | polygon-0.25 | 583 | 2332 | 247192 | 1.11921 | 0.70439 |
| Gürültülü çember | circle-1 | 17 | 51 | 6664 | 1.15045 | 12.98915 |

Gürültülü çemberde yüksek ideal hata beklenir: 16 küçük bileşeni silmek topolojiyi değiştirirdi. Algoritma onları tutar. Çember/elipste düşük karmaşıklık elde edilmiş olması serbest siluette de aynı başarının sağlandığını göstermez. Serbest siluette 583 parça kalması, sınırlı aday aramasının zayıf durumlarından biridir. Kaynak Bézier'in kontrol noktaları rasterden tam geri kazanılmış sayılmaz.

## Karşılaştırma ve ham kanıtlar

Çember girdisindeki aile karşılaştırması, aynı raster referans üzerinde:

| Aday | Parça | Bit | Piksel H üst | İdeal H örnek | Kabul | Aday süresi (s) |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| Kesin çokgen | 1404 | 595296 | 0 | 0.69963 | Evet | 0.17466 |
| RDP 0.25ε | 510 | 216240 | 1.11778 | 0.69963 | Evet | 0.08806 |
| Çember | 1 | 392 | 1.15045 | 0.04051 | Evet | 0.06060 |
| Bézier 0.65ε | 4 | 2720 | 1.42171 | 0.50101 | Evet | 0.07190 |
| B-spline 8 örnek | 1 | 2568 | 3.46091 | 2.38513 | Ret | 0.07990 |
| B-spline 16 örnek | 1 | 4104 | 1.97221 | 0.96699 | Evet | 0.08142 |
| Karma 0.65ε | 2 | 784 | 1.42205 | 0.49765 | Evet | 0.05801 |
| Örtük derece 4 | uygulanmaz | 992 | kanıtlanmadı | 9.58796 | Hayır | 0.13438 |

Bu örnekte kesin piksel çokgeninin ideal çembere örnek uzaklığı 0.69963 iken uydurulmuş çemberinki 0.04051'dir; piksel kesinliği ve ideal eğri tahmini farklı hedeflerdir. Tek girdideki bu fark genel başarı iddiasına dönüştürülmez.

[results.csv](../examples/validation/results.csv) ve [results.json](../examples/validation/results.json), **bütün adayların** piksel örnek H / hesaplanmış H üst / RMS, ideal örnek H, parça ve parametre sayıları, bit maliyeti, topoloji kapsamı, kabul/ret, Pareto, süre ve gerekçelerini içerir. Referanslar ve girdiler [dataset](../examples/validation/dataset) klasöründedir.

Örtük polinomda piksel metriği ızgaradan çıkan sıfır yollarının nokta bulutu yaklaşımıdır; parametrik adayların nokta-sonlu-parça metriğiyle aynı doğrulama değildir. İdeal mesafe de yalnızca çıkarılmış yollar içindir. Polinomun geometrik üst sınırı `null`, topolojisi kanıtlanmamış, seçilebilirliği `false` olur. 12 polinomun süre ve ideal örnek uzaklığı gerçekten hesaplandı; boş alanlar çalıştırılmamış bir deneyi temsil etmek için doldurulmadı.

![Gerçek model karşılaştırması](../examples/validation/comparison.png)

Çember ve köşe/eğri için JSON, bütün denklemler, PNG, JPEG, gerçek vektör SVG ve çok sayfalı PDF [örnek çıktı klasörlerinde](../examples/validation) bulunur. Bu çalışma 12 sentetik girdiye, tek çözünürlüğe, tek ε'ye ve tek gürültü tohumuna dayanır. Farklı veri dağılımlarına genelleme veya bütün platformlarda sayısal kararlılık iddiası yapılmaz.
