# Üç programda ilk CAD denemesi — 2.6

Bu aşamada kullanıcıdan gereken iş, AutoCAD ve SolidWorks kurulumlarını kendi
lisans/erişimiyle tamamlamak ve gerçek program arayüzlerinde görevleri yapmaktır.
Yerel taşınabilir FreeCAD mevcuttur; AutoCAD ve SolidWorks bilinen kurulum
klasörleri/Windows kayıtlarında bulunamadı. Bu kontrol tüm disklerin eksiksiz
envanteri değildir. Üç programdaki insan denemesi henüz yapılmadı.

## Kullanıcının yapacağı hazırlık

1. AutoCAD ve SolidWorks kurucularında ana program konumunu örneğin
   `D:\CAD\AutoCAD` ve `D:\CAD\SolidWorks` seçin. Gerçek ürün sürümünüzün
   kurulum seçenekleri geçerlidir. Autodesk Custom Install ile konum
   değiştirilebilir; bazı ortak/sistem bileşenleri C: üzerinde kalabilir.
   [Autodesk kurulum yolu](https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/How-do-I-install-on-a-different-drive-than-C.html),
   [ortak bileşen konumu](https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Autodesk-products-install-something-on-C-despite-you-have-selected-a-secondary-drive-where-to-install-the-software.html),
   [SOLIDWORKS kurulum konumu](https://help.solidworks.com/2020/English/Installation/install_guide/r_HID_STATE_INSTALL_LOC.htm).
2. Her programı bir kez açın; kendi hesabınız/lisansınız için gereken ilk
   açılışı tamamlayın. Hakkında ekranından gerçek sürümü öğrenin. FreeCAD için
   proje içindeki `.tmp\freecad\FreeCAD_1.1.4-Windows-x86_64-py311\bin\FreeCAD.exe`
   kullanılabilir. Bu taşınabilir test kurulumu taşınır/silinirse yeni yolu seçin.
3. `baslat_windows.cmd` → **Araştırma · üç CAD pilotu** → **Hazırlık ve görevler**.
   **Programları bul** ile bilinen kökleri tarayın. Bulunmazsa **Dosya seç**
   kullanın: FreeCAD.exe, acad.exe, SLDWORKS.exe. Özel D: klasörünü elle
   gösterebilirsiniz. Sürümü yazın, gerçekten yaptıysanız ilk açılışı onaylayın.
4. **Yolları ve sürümleri kaydet** seçin. Ayarlar proje içindeki
   `output/cad-programs.json` dosyasında kalır. Program yolu değişince sürüm
   ve ilk açılış beyanı sıfırlanır. Silinmiş/taşınmış program hazır sayılmaz.
   **Programı aç** yalnız seçilen programı açar; belge/makro yüklemez.

Kurulumlar tamamlanmadan örnek paketleri ve eğitim kayıt ekranını inceleyebilirsiniz.
Program bulunması ve operatörün ilk açılış beyanı, CAD uyumluluk deneyi değildir.
**Hazırlık raporu kaydet** bu ayrımı JSON olarak korur.

## Görev paketini açma veya yeniden üretme

**Üç örnekli görev paketi oluştur**, kayıtlı `circle`, `ring`, `mixed`
projelerini kaynak görüntüden yeniden uydurmadan açar. Her biri için STEP,
IGES ve DXF üretir; dosyalar gerçek CAD okuyucularında tekrar açılarak denetlenir.
İşlem arka plandadır. Çıktı her seferinde yeni `ilk-cad-denemesi-*` klasörüne
yayımlanır; eski paketlerin üzerine yazılmaz. İptal/başarısızlıkta yarım paket
yayımlanmaz. Çalışan sayısal çekirdek işleminin bitmesi beklenebilir.

**Görev planı aç** ile paketin `plan.json` dosyasını seçin. Klasör bütün olarak
taşınabilir. Göreli dosya yolları, boyutlar, SHA-256 ve CAD hedef tutarlılığı
kontrol edilir; değişmiş dosya sessizce kabul edilmez. Hash kontrolü dijital
imza/otantik kaynak garantisi değildir. Eski plan başarısız açılışta korunur.

**Paket kılavuzunu aç**, yerel HTML'de kaynak raster, model önizlemesi, üç CAD
dosyası, yeniden açılabilir proje, denklemler ve mm cinsinden katsayıları gösterir.
Kaynak görsel ideal nesnenin kesin ölçüsü değildir. `target-mm.json` ve
`.cad.json` hedefleri **kayıtlı modelin** fiziksel eşlemesidir.

| İlk rota | Tercih | Diğer seçenekler |
|---|---|---|
| FreeCAD | STEP | IGES, DXF |
| AutoCAD | DXF | STEP/IGES desteği gerçek ürün/sürüme göre kontrol edilmeli |
| SolidWorks | STEP | IGES, DXF; DXF içe alma sihirbazında sketch/yeni parça seçimi gerekebilir |

Bu tercihler uyumluluk kanıtı değildir. Autodesk bazı formatların her AutoCAD
ürününde bulunmadığını belirtir. SOLIDWORKS DXF/DWG için sketch veya çizim
seçeneklerini açıklar. [AutoCAD biçimleri](https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-Core/files/GUID-F5CEE149-E2CA-481A-97DE-EB85FE62697D.htm),
[SOLIDWORKS DXF içe alma](https://help.solidworks.com/2025/english/SolidWorks/slddxf/t_importingdxfdwg.htm?format=P&value=),
[SOLIDWORKS STEP/IGES](https://help.solidworks.com/2025/english/SolidWorks/sldworks/t_reading_step_iges_acis_sw.htm?id=18.17.8).

STEP/IGES düzlemsel yüz, DXF yerel eğri nesneleridir. Dosyalar sürücü ölçü/kısıt
geçmişi veya tamamlanmış bir katı içermez. Sketch, birleştirme ve düzeltme işi
gerekiyorsa ölçün. AutoCAD/SolidWorks GUI otomasyonu bu sürümde yoktur.

## İlk oturum

1. Önce **18 içe alma kartını** tamamlayın: 3 program × 3 şekil × 2 yöntem.
   Programlar ayrı gün/oturumda denenebilir. Sonra profil/5 mm ekstrüzyon ve
   eğri düzenleme kartlarıyla **54 planlı göreve** genişletin. Kartlar kişi,
   gözlem, süre veya başarı verisi içermez; katılımcı ataması elle yapılır.
2. Bir kart seçip **Görevi pilot formuna aktar** kullanın. Program/hedef/görev
   alanları dolar; süre sıfır, bütün kalite kutuları Bilinmiyor olur. Varsayılan
   eğitim modudur. Gerçek kişi için takma kod, CAD deneyimi, mevcut yöntem
   açıklaması, gerçek sürüm ve onayı siz girin. Başka kişiye geçiş onayı temizler.
3. İki yöntemde aynı hedef, tekrar kodu, 0.1 mm kalite toleransı ve 600 s etkin
   süre sınırını kullanın. Paket fiziksel ölçeği 0.1 mm/çalışma birimi,
   CAD aktarım toleransı 0.01 mm'dir. Bunlar aynı tolerans değildir.
4. İçe alma karşılaştırmasında **iki dosya da önceden hazır olmalıdır**.
   Üretilen CAD için paket dosyasını, mevcut yöntem için aynı hedefe göre
   kendi iş akışınızda hazırladığınız dosyayı kullanın. Sayacı dosya seçmeden
   önce başlatın; doğru ölçekte geometri göründüğünde durdurun. Dosya hazırlama
   ve görselden model üretme süreleri bu dar aktarım denemesine dahil değildir.
   Bu veriden bütün iş akışı için hızlanma çıkarılamaz. Geniş kapsamlı hazırlama
   karşılaştırması ayrı bir deney ve açık başlangıç/bitiş tanımı gerektirir.
5. Diğer görevlerde yeni/düzenlenmemiş içe alınmış geometriyle başlayın.
   Profil kartı +Z yönünde 5 mm ekstrüzyondur. Çember/halka kartı belirtilen
   çemberin merkezini koruyarak yarıçap +%10; karma kartı belirtilen spline'ın
   sıfırdan sayılan kontrol 1'ini +X 0.1 mm taşımaktır. Tam eski/yeni değerler
   kartta yazılıdır. İçe alıcı spline'ı yeniden parametrize ederse aynı
   katsayıları kurma işini düzeltme sayın; farklı bir hedefe sessizce geçmeyin.
6. Kaliteyi program içinde ölçün; kutular operatör beyanıdır. Başarısızlık ve
   süre aşımını da kaydedin. Yerel CAD çıktısını kanıt olarak seçebilirsiniz;
   girdi dosyası otomatik olarak insan sonucu kanıtı atanmaz.
7. **Denemeyi kayda ekle / güncelle**, ardından **Çalışmayı kaydet** kullanın.
   Kartın sırası öneridir; forma aktarılan uygulama sırası mevcut kayıtlardan
   devam eder ve gerçek oturuma göre düzeltilebilir. Katılımcılar arasında
   yöntem sırasını değiştirmek operatörün sorumluluğundadır; paket nüfus için
   randomizasyon/denge garantisi vermez. Tekrar oturumunda tekrar kodunu artırın.

Bir biçimi değiştirmek isterseniz aynı fiziksel hedefin alternatif dosyasını
CAD uyumluluğu sekmesinde seçin; pilot formunda biçimi ve geçiş nedenini yazın.
Seçilen kart görev protokolünü korur. Ürün/sürüm/görev/kalite farklıysa sonuçlar
birlikte değerlendirilmez. [Eşli kayıt kuralları](pilot-workspace.md).

## Kayıt sözleşmeleri

`cad-programs.json`: [şema 1.0](cad-programs.schema.json); tam üç program için `path`, `version`,
`first_launch_confirmed`. Kayıt program çalıştırmaz. Eksik yol korunabilir;
hazırlık raporu yeniden dosya kontrolü yapar. `compatibility_tested=false`,
bu raporun yalnız hazırlık kapsamını ifade eder; ayrı FreeCAD raporunu silmez.

`plan.json`: [şema 1.0](cad-pilot-plan.schema.json), tür `cad_pilot_plan`, `observation_count=0`, uygulama
sürümü, UTC oluşturulma zamanı, üç `cases` kaydı, `tasks`, dosya/hash/boyut
envanteri `assets` ve kapsam açıklaması. Her örnek kapalı geometri/topoloji,
kontrollü poligondan boyutlar, düzenleme hedefi ve kaynak/CAD hata ayrımını
taşır. Boyutlar analitik ekstremum sertifikası değildir. Her kart ürün,
örnek/hedef kodu, görev/yöntem, biçim, tekrar, önerilen sıra ve kalite/süre
eşiklerini taşır. Sürüm 1.0 kartlar bu sabit protokole göre doğrulanır;
başka protokol yeni şema veya ayrı manuel pilot gerektirir. İnsan gözlemleri
bu dosyaya yazılmaz; [pilot çalışma şeması](pilot.schema.json) ayrıdır.

Kaynak modelin piksel sınırı sertifikası ile CAD aktarımının float64 üst
tahmini ayrı kalır. CAD dosyası için doğrulanmış sayısal sertifika veya
AutoCAD/SolidWorks başarı iddiası eklenmez. Linux/macOS bu aşamada doğrulanmadı.
