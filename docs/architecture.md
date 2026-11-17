# Mimari ve kaynak kararları

Tkinter arayüzü korundu. Yeni Qt/web katmanı veya analiz servisi eklenmedi. Gereksinim, matematiksel adayları ve doğrulamayı mevcut kesin sınır çekirdeğinin üzerine eklemekti; bu nedenle sorumluluklar küçük modüllere ayrıldı.

| Modül | Sorumluluk |
| --- | --- |
| imaging | EXIF, saydamlık, eşikleme, 1000'lik dönüşüm, kaynak/çalışma matrisleri |
| geometry | Mevcut tam piksel kenarı izleme, eşdoğrusal birleştirme, RDP, halka başına örnekleme |
| models | Tipli ayarlar, referans, parça, aday ve sonuç veri sözleşmeleri |
| curves | Sonlu parametrik değerlendirme, türev, denklem, tolerans kontrollü poligonlaştırma |
| fitting | Yerel uydurma, Fourier, deterministik/tavlama araması, Pareto ve sertifika politikası |
| adaptive | Köşe algılama, uçları sabit kübik ve sınırlı DAG'de en az bitli yol |
| evaluation | STRtree sonlu parça uzaklığı, ortak referans önbelleği, CPU halka işçileri, C0/G1, alan, sayısal topoloji ve maliyet |
| certification | Dışa yuvarlanan aralıklar, tam rasyonel de Casteljau, Bernstein zarf ayırıcıları ve Jordan içerilme denetleyicisi |
| intervals | Ortak dışa yuvarlanan binary64 işlemler ve rasyonel→aralık dönüşümü |
| rational_splines | Kayıtlı spline'ın tam de Boor/Hermite ile Bernstein aralıklarına dönüşümü |
| conic_certification | Rasyonel çeyrek-çember, Taylor dönme kapsamı, gerçek yay zarfları |
| topology_simplification | Boş üçgenle yerel köşe silme ve kaynaktan bağımsız tanık yeniden oynatma |
| polynomial | Normalize SVD ve keşif amaçlı sıfır dalı tanıları |
| pipeline | Aşamalar, iptal/ilerleme, kaynağın tek byte anlık görüntüsü, hash ve yeniden üretim bilgileri |
| project | Şema doğrulama, katsayılardan açma, adayın yeniden ölçülmesi, atomik JSON yazma |
| export | Ortak çizim, gerçek vektör SVG, PNG/JPEG, ReportLab A4 sayfalama ve biçim doğrulaması |
| gui | Türkçe durum akışı, tek işçili havuz, ana iş parçacığında widget erişimi |
| benchmark | Analitik katsayılar, piksel merkezi rasterleştirme, iki referansa ayrı deney |

Shapely/GEOS, ilk uzaklık/geçerlilik denetimi içindir; kendi başına kesin aritmetik sağlamaz. Bağımsız sertifikada GEOS yalnızca tanık kenar seçer; mesafe aralıkla, ayırıcılar/içerilme rasyonellerle denetlenir. ReportLab sayfalama, pypdf gerçek PDF doğrulaması içindir. NumPy/SciPy/Pillow/Matplotlib korunur. Yeni harici bağımlılık eklenmedi; Fraction standart kütüphanedendir. PyMuPDF yalnızca görsel QA aracıdır.

`EvaluationContext`, değişmeyen referans örneklerini/ağırlıklarını/alanını/STRtree dizinini bir kez kurar. `evaluation_workers=1..8` havuzu yalnızca bağımsız halka uzaklık işlerinde kullanılır. Referans verisi salt okunur paylaşılır. Köşe uydurması ve rasyonel sertifika bu havuzda paralelleştirilmez. Tk'nin arka plan işçisi ayrı sorumluluktur. GPU veya analiz servisi eklenmedi; küçük tek halkalarda paralellik kazancı varsayılmaz.

Analiz, açma, kayıt ve deney işlerindeki sonuçlar bir `Future` ile ana döngüye gelir. İşçi ilerlemeyi `Queue` ile bildirir; Tk değişkenlerine erişmez. İptal `Event` üzerinden kontrol noktalarında işler. Sonuç ancak başarıyla tamamlanınca yayımlanır. Matplotlib figürü araç çubuğu yok edilmeden temizlenir; Tk resim nesnelerinin döngüleri ana iş parçacığında toplanır.

Tek dışa aktarım: hedefle aynı dizinde geçici dosya, kapatma, yeniden açma/doğrulama, `os.replace`. Hatalı kayıt eski hedefi korur. Çoklu biçim kaydı bütün olarak atomik değildir. İptal disk kaydına uygulanmaz; kayıt sürerken pencere kullanılabilir, yeni iş başlatılmaz.

Kaynak korumaları: 400.000 açık birim kenar, 512 halka, halka başına 500.000 ölçüm örneği, 2048 Bézier parçası, kontrollü düzleştirme derinliği 24 / 200.000 nokta, 150 MB proje dosyası. Girdi tek kareli raster olmalıdır. Pillow büyük görsel koruması açıktır. Büyük projelerde çizim/denklem widget yenilemesi ana iş parçacığında kısa süreli gecikme yaratabilir; sınırsız etkileşimli veri ölçeği iddiası yoktur.

2.1 ek limitleri: köşe grafiği 768 düğüm ve düğüm başına 24 ileri bağlantı; Fourier serileştirme K≤64 (arama K≤32); tavlama en çok 100 öneri; proje en çok 256 aday; rasyonel düzleştirme parça başına 20.000 yaprak, topoloji kanıtı toplam 5000 yaprak. Kaynak sınırı adayı gerekçesiyle reddeder; sessizce tolerans gevşetilmez.

2.2: rasyonel spline dönüşümü en çok 2048 düğüm aralığı; konik başına en çok 20.000 kiriş ve |θ|≤64 radyan; temas araması en çok 20.000 kaynak köşe/üç tarama/8N teklif. Jordan yolu 5000 yaprak sınırındadır; boş üçgen tanığının çizge yolu ayrı 20.000 kaynak köşe sınırını kullanır. Ortak aralık çekirdeği tekrar eden sertifika aritmetiğini ayırmak için çıkarıldı; yeni paket bağımlılığı eklenmedi.

Proje açma kaynak görselden uydurma yapmaz. Katsayı/aralık/uç doğrulaması, referanstan topolojinin tekrar kurulması, seçilen eğrinin yeniden ölçülmesi ve sertifika yeniden hesabı yapılır. Taşınmış kaynak hash kontrolünü geçmezse açıklanır; model ve dışa aktarım çalışır. Şemada yürütülebilir kod, pickle veya dinamik sınıf yükleme bulunmaz.


2.3: `rational_arcs.py` çember/elipsin ortak uçlu pozitif ağırlıklı rasyonel
kuadratik gösterimini, değerlendirme ve türevini taşır. Sertifika aynı katsayıları
bağımsız tam rasyonel homojen de Casteljau ile kapsar. Bu modül merkez/açıdan
hesaplanan yaklaşık uçların tam C0 kanıtına yetmemesi nedeniyle eklendi.
Mevcut CurvePiece ve aile etiketleri korundu; bağımlılık eklenmedi.

`stress.py` manifestteki SHA-256 doğrulanmış girdilerde tolerans taramasını
ayrı Python süreçlerinde yürütür. Varsayılan dört süreç ve süreç başına bir
BLAS iş parçacığıdır; normal GUI analizindeki halka işçilerinden ayrıdır.
Her iş 240 saniyede sonlanır, hata/süre aşımı ölçüm gibi kaydedilmez. İptal
çalışan süreçleri kapatır ve tamamlanmış atomik ara dosyaları korur. Aynı
kod/ayar/ortam parmak iziyle devam eder, değişiklikte ayrı klasör ister.
Kaydedilen varsayılan ve sıkı sonuçlar aynı uydurulmuş aday kümesindendir;
sıkı yeniden seçimin süresi ayrıca ölçülür. Bu çok süreçli deney mimarisi
GPU hızlandırma veya tek analizde paralel hızlanma iddiası içermez.


2.4 CAD sınırı: `cad_geometry.py` fiziksel birim/ölçek, yerel eğri sözleşmesi,
sonlu aralık kırpması ve bütün kenarlarda iki yönlü aktarım denetimini ayırır.
`cad_dxf.py` ezdxf ile yerel nesne/XDATA/gruplar; `cad_occt.py` Open CASCADE ile
STEP/IGES düzlemsel yüz ve delik telleri üretir. `cad.py` bağımlılık sorgusu,
yeniden açma ve CAD+JSON kaydının geri alınmasını yönetir. `export.py` mevcut
tek biçim/çok biçim sözleşmesini bu adaptörlere bağlar. Büyük CAD bağımlılıkları
yalnız CAD işlemi sırasında yüklenir; var olan altı çıktı ve analiz onları gerektirmez.
Birim ayarları global olan OCCT, uygulama içinde ortak RLock ile korunur.
Süreç dışı CAD programı veya ağ analizi çağrılmaz; genel STEP/IGES metni elle
uydurulmaz. [Geometri ve hata sözleşmesi](cad.md).

2.5: `pilot.py` sürümlü insan/eğitim kayıtları, monotonik etkin süre,
göreve özgü kalite koşulları, atomik JSON ve eşli raporlamayı taşır.
`pilot_gui.py`, mevcut Tk kökünün ayrı Toplevel penceresidir; kendi tek işçisi
ile modelden bağımsız çalışır. Ana pencere pilotta kaydedilmemiş kayıt/form
veya yürüyen iş varken sessizce kapanmaz. `research_report.py` kayıtlı ölçümleri
yeniden uydurmadan raporlar; referans hash'leri farklıysa sıralama yapmaz.

`cad_compatibility.py`, kullanıcının seçtiği FreeCADCmd'yi ayrı süreçte,
izole ve önceden oluşturulmuş kullanıcı/veri/geçici dizinleriyle çalıştırır.
`freecad_worker.py` yalnız FreeCAD'in kendi Python'unda ürün modüllerini yükler;
ana ortamın OCP/ezdxf modüllerini kullanmaz. Kabuk komutu oluşturulmaz. İptal
yalnız başlatılan süreci sonlandırır; işlem ve çıktı kaynak sınırları vardır.
Bu süreç dışı deney isteğe bağlıdır; normal analiz/dışa aktarım değişmez.
FreeCAD ve uygulamanın OCCT sürümleri farklı olsa da algoritma ailesi ortak
olduğundan bağımsız geometri çekirdeği iddiası yoktur.

Windows Tcl'nin aynı süreçte ardışık kök başlatma durumu GUI kabul testlerinde
paylaşılmaz: her test kendi Python sürecinde gerçek Tk olay döngüsü kullanır.
Alt testin geçti/atlandı/hata sonucu JUnit XML'den aynen üst teste aktarılır.
Bu izolasyon ekranı olmayan platformda atlamayı başarıya dönüştürmez.

2.6: `cad_setup.py` program yolu/sürüm/ilk açılış beyanı ile sınırlı salt
okunur keşfi ayırır. Kurulum veya lisans doğrulaması yapmaz. Seçilmiş GUI
yalnız açık Programı aç eyleminde başlatılır; belge/makro enjekte edilmez.
`pilot_pack.py` kayıtlı üç modeli yeniden uydurmadan gerçek CAD okuyucu
doğrulamasına bağlar; fiziksel hedef, önerilen görev sırası ve dosya hash'leri
taşınabilir plan içinde kalır. Başarısız/iptal paket yalnız geçici klasördedir;
başarıda yeni benzersiz klasöre atomik taşınır. Önceki paket korunur.

`pilot_preparation_gui.py` mevcut pilot penceresinin işçi/iptal altyapısını
paylaşır; Tk widget'ları yalnız ana döngüden güncellenir. İptal düğmesi her
yeni işin olayını işaretler. Plan yüklemek veya kartı forma aktarmak PilotTrial
oluşturmaz. Katılımcı değişince onay; program yolu değişince sürüm ve ilk
açılış beyanı temizlenir. Kart sırası öneridir; gerçek uygulama sırası ayrı
form alanıdır. Proje şeması 2.3 ve insan pilot şeması 1.0 değişmedi.
