# Bilinen sınırlamalar ve başarısızlık durumları

- Araştırma probleminin küresel optimumu çözülmez. Köşe DAG'sindeki en kısa yol yalnızca o grafikte optimumdur. Tavlama bütçeli stokastik aramadır; daha iyi incelenmemiş model olabilir.
- Kesinlik eşiklenmiş/yeniden örneklenmiş piksel sınırına aittir. Büyük ölçekle büyütülmüş merdiven sınırına küçük ε ile çember uydurmak reddedilebilir; ideal çembere yakınlık farklı ölçüttür.
- İlk topoloji testi δ kontrollü poligondadır. Doğru/Bézier/B-spline ve pozitif ağırlıklı rasyonel konik yaylar, kanonik tam çember/elips veya boş üçgen tanıklı çokgen için ayrıca kanıt yolu vardır. Çakışan zarflar, tanıksız temaslı referans veya kaynak sınırı belirsiz kalabilir. Genel cebirsel geometri çözücüsü ve bütün ailelere kanıt yoktur. [Kapsam](certification.md).
- Hızlı float64 H tablosu aralık sertifikası değildir. Ayrı sertifika U değeri desteklenen ailelerde IEEE-754 varsayımları altında dışa yuvarlanır. İdeal sürekli referansa hata, RMS ve alan integrali sertifikalanmaz. `selected` modunda belirsiz aday sayısal kabulünü koruyabilir; kanıt zorunluysa `strict` seçilmelidir.
- Beyaz zeminde koyu alan varsayılır. Fotoğraftan nesne ayırma, öğrenilmiş sınıflandırma, merkez hattı, metin/nesne tanıma yoktur. Morfolojik temizleme eklenmedi; kullanıcının çizimi sessizce değiştirilmez.
- Parabol/hiperbol, süperelips ve serbest genel konik uydurma yoktur. Fourier kapalı düzgün halkalar içindir; köşelerde salınım ve öz-kesişim yapabilir. Karma yerel arama sabit uçlu çember ve elips yayları önerir; eliptik ağırlık araması sınırlıdır. Karma ailelerin hiçbiri bütün bölümlemeleri taramaz.
- Bézier parçaları C0 bağlıdır; G1 teğet yönü ölçülür, C1 türev büyüklüğü zorlanmaz. B-spline periyodik kübiktir, iç düğümler basittir. Düğüm optimizasyonu yapılmaz.
- Spline sertifikası kayıtlı düğüm/katsayıların tam rasyonel kapanışını gerektirir; yalnız float64'te yakın görünen uçlar yeterli değildir. Konik kanıtı kanonik tam halkalara ve |dönme açısı|≤64 radyana aittir; Eski açısal yaylar kanıtlanmaz; yeni arc sözleşmesindeki pozitif ağırlıklı karma yaylar desteklenir. Yakın halkalarda kapsama kutularının çakışması muhafazakâr belirsizlik doğurabilir.
- Temas koruyan çokgen en çok 20.000 kaynak köşede üç tarama/8N teklifli açgözlü aramadır. Her silme tanığı baştan doğrulanır; bütün geçersiz GEOS poligonları kabul edilmiş sayılmaz. Geyikte parça sayısı azalsa da çok sayıda küçük delik hâlâ maliyetlidir. Tanık byte'ları geometri bit puanına dahil değildir; ayrı raporlanır.
- Elips başlangıç uydurması radyal ölçekli artığa dayanır; ortogonal en küçük kareler optimumu iddiası yoktur. Adayın kabulü sonradan geometrik ölçüme dayanır. İyi geometrik uyum tüm katsayıların iyi tanımlandığını kanıtlamaz; koşullanma tanılarını inceleyin.
- Örtük polinom sıfır dalları 2 birim ızgarada araştırılır; küçük/tekil dallar kaçabilir. Polinom, otomatik kabul edilen sınır modeli değildir. Cebirsel artık ve gradyan mesafe tahmini gerçek Hausdorff değildir.
- Gürültü bileşenleri topoloji gereği korunur. `noisy_circle` deneyinde ideal temiz çembere uzaklığın yüksek kalması beklenir; bu, piksel sınırını koruma hedefiyle çelişmez.
- Bit maliyeti seçilmiş sabit uzunluklu temsil kodlamasına bağlıdır. Serbest parametre üst sayımı uç/periyodiklik bağımlılıklarını indirmez; evrensel sadelik veya minimum JSON boyutu değildir.
- Girdi: tek kare raster. PDF/SVG girdi değildir. Görsel sınırı 400.000 açık kenar / 512 halka; değerlendirme ve dosya limitleri mimari belgesinde yazılıdır.
- Bazı yoğun projelerde çizim ve denklem widget yenilemesi ana iş parçacığında kısa gecikme yapabilir. İptal, devam eden bir C/Fortran sayısal çağrısını ortasında kesmez; sonraki kontrol noktasında işler. Kayıt işlemi iptal edilmez.
- Rasyonel sertifikada iptal, yürüyen denetimin bitiminde alınır; kısmi sonuç yayımlanmaz. CPU işçileri yalnızca halka uzaklıklarını hızlandırabilir; tek halkalı arama ve sertifika için GPU/hızlanma garantisi yoktur. Yeni aileler bazı girdilerde toplam süreyi artırır.
- Her dosya ayrı atomiktir; çok biçimli çıktı grubunda sonraki hata önceki dosyaları geri almaz. Eski yaklaşık şema 1.0 projeler kesin referans içermediğinden doğrudan yükseltilmez.
- 2.0/2.1 deneyleri tarihsel olarak korunur; 2.2 için altı sertifikalı analiz tarihsel klasördedir; 2.3 taraması ve örnekleri arc_stress klasörüne kaydedilir. Bir veri kümesindeki kazanım genel kararlılık kanıtı değildir. Linux/macOS GUI, GPU, temiz Windows kurulumu ve uzak CI bu çalıştırmada doğrulanmadı.

- 2.4 CAD kapsamı basit ayrık kapalı profillerdir; temaslı/açık profil sessizce onarılmaz. STEP/IGES düzlemsel yüz üretir; katı/kalınlık ve native ölçü/kısıt geçmişi oluşturulmaz. DXF'teki parametriklik eğri katsayılarına aittir.
- CAD aktarımı float64 sonlu kenar tanıklarıyla ayrıca denetlenir; kaynak aralık sertifikası CAD dosyasını sertifikalamaz. Fourier açık izinle kontrollü poligona çevrilir; modelin bit maliyeti ile CAD kenar/düğüm/dosya maliyeti farklı olabilir ve ayrıca raporlanır.
- OCCT ve ezdxf okuyucularıyla yeniden açma doğrulandı; AutoCAD/SolidWorks/FreeCAD arayüzlerinde gerçek kullanıcı pilotu henüz yapılmadı. İnsan düzeltme süresi, öğrenme kazanımı veya ticari değer ölçülmedi. Temiz Windows'ta yeni CAD kurulum betiği ayrıca doğrulanmadı.
2.5 pilot sınırı: kalite kutuları ve insan süreleri operatör beyanıdır;
bağımsız sertifika veya denetlenemez bir kayıt defteri değildir. Eğitim
kayıtları insan sayılmaz. Yalnız aynı kişi/ürün/sürüm/OS/şekil/görev/tekrar/
tolerans/süre sınırı/mevcut yöntem koşullarındaki başarılı iki yöntem
karşılaştırılır. Farklı görev/şekil hedefleri tek medyanda havuzlanmaz.
Başarısız, süre aşan, eşleşmeyen ve sıra belirsiz kayıtlar ayrıca gösterilir.

FreeCAD deneyi başsız ürün API'sini çalıştırır; FreeCAD arayüzünde insan
kullanımı değildir. Örnekleme FreeCAD deflection hedefidir; doğrulanmış hata
sınırı değildir. Hacim iki yüz ağı yoğunluğunda sayısal kontrol edilir;
iki ağın yakın olması tek başına kesin yakınsama ispatı değildir. Varsayılan
çekirdek hacmi de raporda korunur. AutoCAD/SolidWorks, gerçek insan pilotu,
temiz makinede kurulum ve Linux/macOS bu turda sınanmadı.

2.6 hazırlık/paket sınırları: program keşfi en çok 1500 dizin, dört alt düzey
ve bilinen köklerle sınırlıdır; tüm disk taraması veya kurulu yazılım ispatı
değildir. D: özel kurulumları elle seçilebilir. İlk açılış ve gerçek sürüm
operatör beyanıdır; lisans veya uyumluluk kontrolü sayılmaz.

Paket sabit üç örnek/54 kartlık ilk aktarım protokolüdür; rastgele katılımcı
ataması veya nüfus için dengeli sıra sağlamaz. İki yöntemde dosyalar önceden
hazırlanır; analiz ve dosya hazırlama süresi bu aktarım karşılaştırmasının
dışındadır. Toplam iş akışı hızlanması çıkarılamaz. Boyut hedefleri kontrollü
poligon ekstremumlarıdır; analitik ekstremum sertifikası değildir. Hash'ler
değişiklik kontrolüdür, dijital imza veya değiştirilemez günlük değildir.
Görev kartı/otomatik FreeCAD raporu insan gözlemi değildir. AutoCAD/SolidWorks
uyumluluğu ve her üç ürünün GUI kullanılabilirliği insan oturumu bekliyor.
