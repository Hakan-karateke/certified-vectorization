# 2.2: sertifikalı aileler ve temas koruyan sadeleştirme

Üç aşama sırasıyla uygulandı ve her aşama geçtikten sonra sonraki aşamaya geçildi. Önceki [2.1 sonuçları](improvements.md) değiştirilmeyen ham kayıtlarıyla korunur. Yeni ham ölçümler [JSON](../examples/certified_extensions/results.json) ve [CSV](../examples/certified_extensions/results.csv) içindedir.

## 1. B-spline sertifikası

Kaydedilmiş düğüm ve katsayılar tam dyadik rasyoneller olarak de Boor ile değerlendirilir. Her düğüm aralığının uç/değer türevleriyle tam Bernstein eşdeğeri bulunur. Mevcut de Casteljau hata ve ayrıklık denetleyicisi bu tam kontrol dizilerini kullanır. Yakın fakat eşit olmayan uçlar kapalı kabul edilmez. Düzensiz dyadik düğümlerde dönüşüm, bağımsız tam Cox taban toplamıyla sınandı.

Gerçek çember rasterinde `family=bspline`, `preference=simple`, ε=3 ve sıkı mod **tek B-spline-16** seçti; doğrulanmış H≤1.806257, 4104 bit. Bu aileden sonuç almak, otomatik aramada daha ucuz çemberin seçilmesiyle karıştırılmaz.

## 2. Tam çember/elips sertifikası

Tam halka, kanonik aralıkta sembolik tam tur fazıyla tanımlanır. Böylece dyadik `float(2π)` etiketinin sağ ucu açık bir boşluk bırakmaz. Eski kanonik projeler yükseltilir; yakın açık yaylar kapalı sayılmaz. JSON 2.2 `full_turn=true` açıklaması ve rapor denklemleri bunu görünür kılar.

Çeyrek çemberler tam rasyonel `(1−q²,2q)/(1+q²)` ile kapsanır. Dönme sin/cos değerleri tam Taylor kalan aralığı ve dışa yuvarlanan çift açıyla sınırlandırılır. Sayısal sin/cos kütüphanesinin doğru yuvarladığı varsayılmaz. Kiriş interpolasyonu ve uç dönüşüm hatası birlikte kapsanır; gerçek yay zarfları farklı halkaların ayrıklığında denetlenir. [Tam yeter koşullar ve argüman](certification.md).

Sıkı otomatik modda çember/elips birer, iç boşluklu halka iki konik parçayla seçildi. Katsayıdan proje açılışı her örnekte sertifikayı yeniden üretti. Kapalı konik sertifikası, karma modelin açık konik yaylarının da kanıtlandığı anlamına gelmez.

## 3. Temasları koruyan çokgen

Geyik girdisi 90 sınır yürüyüşü, 89 iç boşluk ve beş halkalar arası temas çifti içerir. Bir yürüyüş GEOS'un basit poligon koşulunu sağlamaz. Eski RDP ve eğri adayları bu yapıyı koruyamadığı için 4324 parçalık kesin modele dönülüyordu.

Yeni `topology` ailesi her köşe silmede süpürülen üçgenin diğer güncel kenarlardan boş olduğunu tam aritmetikle denetler. İçeride kalmış küçük bileşen de engeldir. Temas köşeleri korunur; her kiriş bütün orijinal alt zincire karşı sınanır. Tanık, silme sırasıdır. Bağımsız denetleyici bu adımları referanstan yeniden oynatır ve son katsayılarla eşler. Bu yerel düzlemsel izotopilerin bileşkesi çizgenin temas/yüz düzenini korur. Böyle bir tanık yoksa GEOS reddi aşılmaz.

Arama açgözlü ve bütçelidir; küresel minimum iddiası yoktur. Kullanıcı arayüzündeki **Temasları koruyan çokgen** ailesinden çalışır. Otomatik seçim, referansta temas veya basit olmayan yürüyüş gördüğünde bu aileyi ekler. Seçilen model, gösterim ve dışa aktarımda mevcut sonlu doğru parçalarıdır.

## Gerçek sonuçlar

Ortam Windows 11 x64 / CPython 3.12.8; NumPy 2.5.4, SciPy 1.18.1, Shapely 2.2.0, Pillow 12.3.0. Yeni bağımlılık eklenmedi. Çember/elips/halkada boşluk 0, ε=3; geyikte boşluk 20, ε=2; eşik 127, sertifika `strict`, CPU işçisi 1. Kaynak hash'leri, ayarlar ve ortam ham JSON'dadır.

| Deney | Arama / tercih | Parça | Geometri bit | Doğrulanmış H üstü, yukarı yuvarlanmış | Analiz süresi (s) |
| --- | --- | ---: | ---: | ---: | ---: |
| B-spline / çember rasteri | bspline / simple | 1 | 4104 | 1.806257 | 1.20 |
| Çember | auto / balanced | 1 | 392 | 1.012772 | 5.25 |
| Elips | auto / balanced | 1 | 520 | 1.017248 | 4.78 |
| İç boşluklu halka | auto / balanced | 2 | 784 | 0.987254 | 8.27 |
| Geyik | auto / balanced | 2007 | 850968 | 1.612941 | 29.88 |
| Geyik | topology / simple | 1560 | 661440 | 1.946202 | 8.87 |

Geyikte 4324→2007 (**%53.58**) veya daha yüksek hatayla 1560 (**%63.92**) parça elde edildi. Dengeli modelin 2317, sade modelin 2764 silme adımı yeniden doğrulandı. Bir bileşen, 89 boşluk ve beş temas çifti korunur. Tanık payload'ı sırasıyla 74144/88448 bit ayrıca raporlanır; geometri puanı yeniden çizim için gereken katsayı kodlamasıdır, bütün JSON dosyasının maliyeti değildir.

Bütün H değerleri **normalize piksel sınırına** göredir. Sentetik şekillerin ideal analitik eğrileri veri kümesinde bilinse de bu tabloda ideal eğriye hata yeniden ölçülmedi; bu sütunlara ideal hata anlamı yüklenmez. Geyik sürekli ideal referansı bilinmeyen indirilen bir rasterdir. Zamanlar tek çalıştırmadır, kaynak okuma/uydurma/seçim/sertifikayı içerir; dosya kaydı ve yeniden açmayı içermez. Aile/tercih ve iş yükleri farklıdır; süreler genel hızlanma oranı değildir.

## Kabul kontrolleri

- Tam test kümesi: **81 geçti, 147.45 saniye**, atlama yok. Önceki 65 test korundu/güncellenmiş aile davranışıyla çalıştı; 16 yeni parametrik test durumu eklendi.
- Yeni testler: tam düzensiz spline dönüşümü, açıklıklı spline'ın reddi, 90 basamaklı bağımsız Decimal trigonometrik seri, sıkı konik seçimi/kayıt-açma, gizli yakın konik kesişimi, açık yayın reddi, içeride kalmış delik, tanık/katsayı tahrifi, gerçek geyik ve iptal.
- Gerçek Tk olay döngüsünde analiz, iptal, aday seçimi, kayıt/açma ve PNG/JPEG/SVG/PDF dışa aktarım testi geçti. Yeni aile aynı Türkçe model seçicisine eklendi.
- Altı yeni 2.2 ve üç eski 2.0/2.1 proje bağımsız JSON Schema ile doğrulandı. Altı yeni proje yeniden uydurmadan açıldı ve sertifikalandı.
- SVG'lerde raster yok; native geometri sayıları seçilen modelle aynı. Çember/elips yerel vektör elemanı, spline kontrollü vektör çokgenidir. PNG/JPEG gerçek biçim ve 1200×1200 boyutla açıldı.
- Altı sayfalık A4 rapor Poppler ile rasterleştirildi; bütün sayfa mozaiği ve ilk tam sayfa incelendi. Metin kutularında kenar taşması yok; sembolik faz ve doğrulanmış U metinde mevcut. [Çıktı denetimi](../examples/certified_extensions/output-validation.json), [dosya hash'leri](../examples/certified_extensions/files.json).
- Yerel düzenlenebilir paket kurulumu ağ kullanılmadan 2.2.0'a güncellendi; temiz makine kurulumunun veya imzalı EXE dağıtımının doğrulandığı anlamına gelmez.
- Kurulum sonrası GUI/CLI/girdi-dışa aktarım alt kümesi tekrar çalıştırıldı: **17 geçti, 9.61 saniye**. Ruff denetimi ve 50 Python dosyasının biçim denetimi geçti; `git diff --check` temiz.

## Yeniden üretim ve kullanım

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe examples/validate_extensions.py
```

Masaüstünde **Proje aç** ile [hazır projelerden](../examples/certified_extensions/README.md) birini seçin. Kaynak görselden yeniden uydurma gerekmez. [Karşılaştırma](../examples/certified_extensions/comparison.png) · [Konik A4 örneği](../examples/certified_extensions/circle/a4.pdf) · [Geyik sade proje](../examples/certified_extensions/deer_simple/model.json).

Genel örtük/Fourier kanıtı, karma konik yay sertifikası, bütün topolojilere başarı ve küresel en az parça çözümü sağlanmadı. |θ|>64, çok yakın zarflar, tam kapanmayan spline ve kaynak sınırları belirsiz kalabilir. Windows dışı GUI, GPU ve farklı çözünürlüklerde genelleme bu altı örnekten çıkarılamaz.
