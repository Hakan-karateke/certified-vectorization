# Şekilden Denkleme 2.6 — üç CAD programında gerçek denemeye hazırlık

Son tam koşu: **187 test geçti; 0 hata, 0 atlama; 207.78 saniye**
(JUnit süresi 207.739 s). **9/9 yeni teslim dosyası** ayrı **FreeCAD 1.1.4**
ürün kontrolünü geçti. **AutoCAD ve SolidWorks çalıştırılmadı; gerçek insan
gözlemi sıfırdır.** Program bulma/ilk açılış beyanı uyumluluk sonucu değildir.

## Değişiklik ve gerekçe

Mevcut Tk arayüzü ve modelleme çekirdeği korundu. Yeni **Hazırlık ve görevler**
sekmesi, gerçek oturumdan önce eksik kalan program yolu ve ortak hedef
hazırlığını tamamlar. D: dahil bilinen köklerde sınırlandırılmış salt okunur
arama, özel program yolunu seçme, gerçek sürüm/ilk açılış beyanı, yerel ayar
kaydı ve ayrı hazırlık raporu sunulur. Dosya bulunması lisans veya içe alma
başarısı sayılmaz; kurulum ve kullanıcı hesabı işlemleri operatöre aittir.
FreeCAD'in kök taşınabilir başlatıcısı ve `bin` içindeki GUI'si desteklenir;
eşleşen FreeCADCmd yolu türetilir. Yeni program yolu eski sürüm/onayı taşımaz.

Görev paketi mevcut üç kayıtlı modelin katsayılarını yeniden uydurmadan açar;
STEP/IGES/DXF dosyalarını gerçek okuyucularında yeniden açıp doğrular. Kaynak
ve model PNG'leri, denklemler, mm cinsinden katsayılar, düzenleme hedefleri ve
aynı geometriye ait proje saklanır. Bağıl yollar/hash'ler ve üç biçimdeki
katsayı/ölçek/hedef tutarlılığı plan açılışında denetlenir. İptal veya hata
yarım paket yayımlamaz; başarı yeni benzersiz klasördedir. Eski paket korunur.

18 içe alma kartı ilk aşamadır; profil/5 mm ekstrüzyon ve eğri düzenleme ile
54 planlı görev vardır. Bunlar insan kaydı değildir. Kart forma aktarılınca
süre sıfır ve kalite Bilinmiyor kalır; onay/başarı/kanıt dosyası atanmaz.
Kart önerilen sırayı taşır, gerçek uygulama sırası mevcut kayıtların ardından
devam eder. Kullanıcı başka sırada yaptıysa alanı düzeltmelidir.

Pilot iptal düğmesinin oluşturulma anındaki eski Event'e bağlı kalması
düzeltildi; ardışık iki işte gerçek Tk olay döngüsüyle sınandı. Katılımcı
değişince önceki kişinin onayı temizlenir. Kaydedilmemiş program ayarları da
pencere kapanışında sessizce kaybolmaz. Yeni sorumluluklar `cad_setup.py`,
`pilot_pack.py`, `pilot_preparation_gui.py` modüllerindedir. Geometri uydurma,
karmaşıklık veya matematiksel sertifika algoritması bu sürümde değiştirilmedi.

## Gerçek örnek koşusu

Windows 11 / Python 3.12.8; FreeCAD 1.1.4'ün kendi Python'u 3.11.14,
OCCT 7.8.1; uygulama CAD okuyucusu OCP/OCCT 7.9.3.1 ve ezdxf 1.4.4.
Kütüphane sürümleri bu yerel ortam içindir; temiz Windows kurulumu doğrulanmadı.
Kaynak modeller 2.5'te kaydedilmiş `circle`, `ring`, `mixed` projeleridir.
Katsayılar yeniden ölçülüp aynı fiziksel eşlemeyle aktarılmıştır; tekrar
görüntüden uydurma veya daha iyi geometri bulunduğu iddiası yoktur.

Ölçek 0.1 mm/çalışma birimi, CAD aktarım hedefi 0.01 mm. Plan kalite hedefi
ayrı olarak 0.1 mm, etkin süre sınırı 600 saniyedir. Bu eşleme ideal nesnenin
görüntüden ölçülmüş boyutu değildir; görev hedefi kayıtlı matematiksel modeldir.

| Örnek | Bileşen/delik | STEP | IGES | DXF | Üç okuyucu aktarımının en büyük sayısal üst tahmini (mm) |
|---|---:|---|---|---|---:|
| Çember | 1/0 | Geçti | Geçti | Geçti | 0.002500001 |
| Halka | 1/1 | Geçti | Geçti | Geçti | 0.002500001 |
| Köşe/eğri birleşimi | 1/0 | Geçti | Geçti | Geçti | 0.009715663 |

Tablodaki değerler yukarı yuvarlatılmış float64 aktarım tahminleridir;
**CAD dosyası için doğrulanmış aralık sertifikası değildir**. Kaynak modelin
piksel sınırı sertifikası ayrıca korunur. Ayrı FreeCAD kontrolü gerçek içe
alma, ölçek/topoloji, profil, 5 mm ekstrüzyon ve sayısal geometri kontrolleridir;
CAD GUI'sinde insan kullanılabilirliği değildir. Uygulama ile FreeCAD ortak
OCCT algoritma ailesindedir; bağımsız geometri çekirdeği iddiası yoktur.

Paket üretimi son koşuda **9.1215717 s** sürdü; tam testlerle eşzamanlı
çalıştı. Bu tek yerel hazırlama süresi karşılaştırmalı performans veya
kullanıcı süresi sonucu değildir. İlk ara koşu ve yeni benzersiz paketler
korunur; üst indeks son koşuyu gösterir. Son koşunun gerçek kayıtları:

- [Görseller, CAD dosyaları ve görev kılavuzu](../examples/first_cad_pilot/index.html).
- [Ortam, hash ve dokuz FreeCAD durumu](../examples/first_cad_pilot/preparation.json).
- [Son görev planı](../examples/first_cad_pilot/ilk-cad-denemesi-69f3b7993241/plan.json).
- [Kaynak/model karşılaştırma PNG](../examples/first_cad_pilot/comparison.png).
- [187 testin JUnit kaydı](../examples/first_cad_pilot/tests.xml).
- [121 çıktı dosyasının hash'i ve doğrulama kaydı](../examples/first_cad_pilot/verification.json).
- [Pilot malzemeleri ZIP](../examples/first_cad_pilot/first-cad-pilot-2.6.zip)
  ve [SHA-256](../examples/first_cad_pilot/first-cad-pilot-2.6.zip.sha256).
  Bu arşiv uygulama kurucusu değildir; kurulu uygulamanın görev malzemeleridir.

Doğrulanan uygulama kaynak hash'i:
`a56c0fdcccfe80256a0a589affccabc0382d1f10d2fa5415112c8ea431d640dd`.

## Test kapsamı ve kalan işler

Mevcut 176 test korunarak 11 anlamlı test/parametrik vaka eklendi. Yeni kapsam:
taşınmış/bozuk program ayarları, açık başlatma dışında süreç çalışmaması,
sınırlı keşif/iptal, kök/bin FreeCADCmd bulma, dokuz gerçek CAD aktarımı,
ortak hedefler, dosya/plan değişikliği, klasör taşınabilirliği, hata/iptalde
eski dosya korunması ve gerçek Tk üzerinden paket oluşturma/yeniden açma/
üç ürünün formuna aktarma. Var olan gerçek FreeCAD, geometri, proje, görüntü,
SVG ve sayfalanmış PDF testleri de tam koşuya dahildir.

`ruff check` ve biçim denetimi geçti (73 Python dosyası). İki yeni JSON Schema
gerçek program ayarı/görev planı örnekleriyle doğrulandı. Paket ZIP'i tekrar
açıldı ve CRC denetimi geçti. Büyük karşılaştırma PNG'si görsel incelendi;
CAD programlarının arayüzleri görsel incelenmedi.

Kullanıcı **AutoCAD ve SolidWorks kurulumunu D: üzerinde kendi erişimiyle**
tamamlamalı; üç programda ilk açılış/sürümü doğrulamalı ve gerçek görevleri
yapmalıdır. [Adım adım kullanıcı işleri](first-cad-pilot.md). İki yöntem de
önceden hazır dosyayla içe alma görevine başlar; dosya hazırlama/görselden model
üretme süreleri dışarıdadır. Toplam iş akışı hızlanması veya ticari değer
çıkarılamaz. Linux/macOS, yeni temiz kurulum ve gerçek CAD GUI/human pilotu
henüz doğrulanmadı. 2.5 ve önceki sürümlerin tarihsel deneyleri değiştirilmedi.
