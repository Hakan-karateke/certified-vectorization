# Araştırma ve üç CAD pilotu — kullanım

Ana pencereden **Araştırma · üç CAD pilotu** seçin. Analiz sonucu olmadan
pilot dosyası açılabilir. Mevcut proje raporu için önce ana alanda projeyi açın;
pilot penceresi açılıştaki modelin anlık görüntüsünü kullanır. Analiz katsayıları
pilot kaydından etkilenmez. Kayıtlı projelerden karşılaştırma her zaman yapılabilir.

## Hazırlık ve görevler (2.6)

D: veya başka konumdaki FreeCAD.exe, acad.exe, SLDWORKS.exe yollarını seçip
gerçek sürüm ve ilk açılış beyanını kaydedin. Programları bul işlemi sınırlı
salt okunur aramadır; lisans/uyumluluk kontrolü değildir. Yol değişince sürüm
ve ilk açılış onayı temizlenir; kaydedilmemiş ayarlar kapanışta korunur.

Üç örnekli paket oluşturma gerçek STEP/IGES/DXF dosyalarını yeniden okuyarak
doğrular. Plan açma dosya/hash/ortak hedef denetimi yapar; tek klasörle taşınır.
18 içe alma, profil/düzenleme ile 54 planlı görev vardır; sonuç oluşturmaz.
Seçilen kartı pilot formuna aktarın; kalite/süre alanlarını gerçekten ölçün.
Tam katsayı, düzenleme hedefi ve görseller Paket kılavuzunu aç düğmesindedir.
[Kullanıcının yapacağı kurulum ve görev kapsamı](first-cad-pilot.md).

## Pilot oturumları

1. Veri türünü seçin. Varsayılan **Eğitim / deneme** insan sonucu sayılmaz.
   Gerçek kişi için takma kod, deneyim ve açıkça alınmış onayı kaydedin.
2. FreeCAD, AutoCAD veya SolidWorks'ü seçin. Gerçek sürümü ve OS'yi yazın;
   henüz kurulu olmayan ürünü test edilmiş gibi doldurmayın.
3. İki yöntemde aynı şekil/fiziksel hedef kodunu, kalite toleransını (mm), süre
   sınırını, mevcut yöntem açıklamasını ve tekrar kodunu kullanın. Üretilen CAD
   ve mevcut yöntem için farklı uygulama sırası yazın; sırayı katılımcılar
   arasında değiştirin. İlgili ürün ve sürüm aynı olmalıdır.
4. İçe alma, profil/5 mm ekstrüzyon veya düzenleme görevini seçin. Görev
   açıklaması ve gerekli kalite kontrolleri formda görünür. Çember düzenlemesi
   yarıçap +%10; spline denemesi seçilen kontrol noktasında +X 0.1 mm'dir.
5. **Başlat / sürdür**, **Duraklat** ile etkin süreyi ölçün. Kronometre monotonik
   saate dayanır, duraklamayı eklemez. **Elle ölçüm** seçilirse saniyeyi kendiniz
   girin; süre kaynağı dosyada ayrıdır. Pencereyi kapatıp geçen süreyi otomatik
   ölçülmüş gibi sürdürmez. Formda süre sınırının aşılması otomatik başarı yapmaz.
6. Düzeltme sayısını ve türlerini kaydedin: ölçek, uç birleştirme, delik onarma,
   yeniden çizme, sketch/kısıt oluşturma gibi. Ek sürücü ölçü kurulumu ayrı
   iş olarak yazılmalıdır; dosyanın zaten özellik geçmişi getirdiği varsayılmaz.
7. Kontroller Evet/Hayır/Bilinmiyor'dur. **Tamamlandı**, görevin bütün gerekli
   kontrolleri Evet, süre pozitif ve süre sınırı içinde ise kaydedilebilir.
   Diğer durumlarda Başarısız veya Süre aşıldı kullanın; açıklama yazın.
8. İsteğe bağlı kanıt dosyasını seçin; byte SHA-256'sı kaydedilir. Dosya
   çalıştırılmaz veya otomatik paylaşılmaz. **Denemeyi kayda ekle / güncelle**
   ile tabloya alın, sonra **Çalışmayı kaydet** ile diske yazın. Form verisi
   ile tablo/disk kaydı farklı aşamalardır. Kaydı seçerek güncelleyebilirsiniz.

Form kaydırılabilir. Yeni deneme ölçüm/kontrol/kanıt alanlarını temizler;
kişi ve şekil bilgileri kalır. Ekleme sonrası sıra artar, yöntem diğer yönteme
geçer. Aynı kişi/görev/yöntem/tekrar iki kez eklenemez; yeni tekrar kodu kullanın.
Kaydedilmemiş çalışma veya form kapanışta sessizce silinmez.

**Çalışma aç** sürümlü JSON'u doğrular. Başarısız açma önceki çalışmayı korur.
**JSON · CSV · HTML raporu**, ham kayıtları ve eşli sonuçları üretir. Her dosya
ayrı atomik yazılır; grup tek atomik işlem değildir. Başarısız çoklu kayıt
tamamlandı olarak bildirilmez; önceki tamamlanan dosyalar kalabilir.

## Eşli karşılaştırmanın anlamı

Fark `üretilen CAD − mevcut yöntem`dir. Negatif saniye veya düzeltme daha az
süre/işlem demektir. Yalnız iki yöntemi de başarılı olan gerçek insan çiftleri
karşılaştırılır. Eğitim kayıtları, eksik çiftler, farklı sürüm/hedefler,
başarısızlık/süre aşımı ve aynı uygulama sırası ayrı tutulur. Özetler ürün,
sürüm, OS, şekil, görev, kalite toleransı ve süre sınırı bazındadır.

Ham kayıtlar ve dışarıda kalan çiftler görünürdür. İlk küçük örneklemde
medyanlar genel verimlilik/öğrenme veya nedensellik kanıtı değildir. Kalite
kutuları operatör beyanıdır; CAD sertifikası yerine geçmez. Kayıt güncellemeleri
yerel dosyada değişir; bu sürüm imzalı/değiştirilemez denetim günlüğü sağlamaz.
[JSON Schema 1.0](pilot.schema.json), protokol 1.1 alanlarını tanımlar. Önceki
2.4 boş alan listesi şablonu uygulama çalışma dosyası değildir; tarihsel tutulur.

## CAD uyumluluğu

CAD dosyasını seçin; yanındaki `.cad.json` hash'le eşleşmelidir. Beklenen
fiziksel XY boyutları, bileşen ve delik sayısı gösterilir. Bu hedef kodunu
iki insan yönteminde aynı fiziksel geometri için kullanın.

FreeCADCmd yolunu seçin. Kurulumu D: üzerinde yapabilirsiniz; normal veya
taşınabilir paket çalışır. Deney programı kendi Python ortamında çalıştırır,
kullanıcı tercihlerini ayrı klasöre koyar ve mevcut FreeCAD oturumuna dokunmaz.
İçe alma, kapalı profil, alan, fiziksel boyut, delik/bileşen, 5 mm ekstrüzyon
ve sayısal hacim kontrol edilir. Varsayılan süre sınırı 120 saniyedir. İptal
yalnız bu süreci durdurur; önceki pilot kayıtları ve model korunur.

STEP/IGES yerel yüzleri kullanır. DXF için içe alınan yerel tellerden yüz
oluşturma ayrıca açık bir hazırlama adımı olarak raporlanır; ilk içe almanın
zaten bir sketch/yüz getirdiği iddia edilmez. Eğri parametre deneyi içe alınan
geometrinin **kopyasında** yapılır; yerel sketch geçmişi veya GUI düzenlemesi
değildir. `imported.FCStd`, `inspection.FCStd`, `process.log`, request/response,
`compatibility.json/html` deney klasöründe saklanır. Geometri boş veya geçersizse
rapor **failed** olur; dosya üretilmesi geçti sayılmaz.

AutoCAD ve SolidWorks için otomatik ürün adaptörü bu sürümde yoktur.
Kurulumlardan sonra aynı dosyaları kendi arayüzlerinde açın, görevleri
yapın ve Pilot oturumları sekmesine kaydedin. Otomatik FreeCAD kayıtları
insan tablosuna aktarılmaz. [Gerçek kullanıcı görev protokolü](cad-pilot.md).

## Araştırma karşılaştırması

Mevcut projenin bütün adaylarını veya en çok 32 kayıtlı projeyi seçin. Görselden
yeniden uydurma yapılmaz; proje açılış doğrulaması/yeniden ölçümü uygulanır.
HTML/JSON raporunda parça, parametre üst sayımı, kontrol/düğüm/derece, bit,
örneklenmiş H, RMS, sayısal U, ayrı sertifika U, Pareto ve ret nedenleri vardır.
Farklı referans hash'lerinde projeler arası en iyi model sıralaması yapılmaz.
Piksel sınırına hata, ideal nesne hatası veya CAD aktarım hatasıyla karıştırılmaz.

[Gerçek ürün deneyleri](../examples/cad_product_validation/index.html) ·
[Örnek araştırma ve boş pilot çıktıları](../examples/pilot_workspace/index.html).
