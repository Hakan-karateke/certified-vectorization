# İlk gerçek CAD kullanıcı denemesi — protokol 1.0

**Durum: henüz yapılmadı.** Hazır 27 CAD dosyasının okuyucu testleri insan
kullanılabilirlik testi değildir. Bu belge ilk oturumu tekrarlanabilir yapar;
katılımcı, süre veya başarı verisi uydurulmaz. Kimseye mesaj gönderilmedi.

2.5'te [masaüstü kayıt ekranı](pilot-workspace.md) hazırdır. FreeCAD,
AutoCAD ve SolidWorks aynı görevlerle ayrı ölçülecek hedeflerdir. Ayrı FreeCAD
başsız ürün deneyleri [gerçek sonuçlarda](release-2.5.md) vardır; bu, insan
pilotunun başladığı anlamına gelmez. Uygulamadaki gerçek çalışma protokolü
1.1; aşağıdaki görevler korunur, eşli kayıt ve kalite alanları kesinleştirilir.

## Araştırma sorusu

Seçilen CAD programında aynı doğruluk koşullarına ulaşırken, üretilen CAD
dosyası kullanıcının mevcut yöntemiyle kıyaslandığında düzeltme sayısını ve
tamamlama süresini azaltıyor mu? Geometri, parametrik eğri düzenleme ve yerel
ölçü/kısıt geçmişi ayrı değerlendirilir.

İlk tur için 3–5 gerçek kullanıcı önerilir. Bu sayı ürün talebi veya istatistiksel
genelleme kanıtı değildir. Program adı/sürümü, işletim sistemi, kullanıcının
deneyim düzeyi ve mevcut yöntemi kaydedilir. AutoCAD, FreeCAD veya SolidWorks
adı önceden test edildiği anlamına gelmez; katılımcının kullandığı ürün seçilir.

## Veri ve görevler

Pilot paketinden önce `circle`, `ring`, `mixed` örneklerini kullanın.
Diğer altı örnek daha sonraki kapsama turu içindir. Kullanıcı kendi programında
uygun gördüğü biçimi seçsin; diğer biçimlere geçiş varsa nedeni kaydedilsin.

1. **İçe al ve birimi kontrol et.** Orijin, düzlem, yarıçap/boyutlar ve profil
   sayısını .cad.json katsayılarıyla karşılaştırın. Yanlış birimi elle düzeltmek
   de düzeltme sayılır; otomatik içe alma başarısı olarak yazılmaz.
2. **Profili kullanılabilir yap.** Dış sınırı ve deliği kontrol edin; program
   destekliyorsa 5 mm ekstrüzyonla deliğin korunduğunu gösterin. STEP/IGES girdisi
   düzlemsel yüzdür, önceden katı olduğu varsayılmaz. DXF girdisinde gerekli
   eğri birleştirme veya sketch oluşturma işlemleri kaydedilir.
3. **Düzenle.** Çember yarıçapını %10 değiştirin; karma profilde bir eğriyi veya
   kontrol noktasını düzenleyin. Yerel parametrik sketch kısıtlarını kurma
   ihtiyacı varsa ayrı iş olarak ölçün. Dosyanın kısıt geçmişi getirdiği söylenmez.

Her görevde aynı kalite hedefiyle kullanıcının mevcut yöntemini de deneyin.
Mevcut yöntem elle çizim, başka vektörleştirici veya var olan CAD iş akışı
olabilir; yöntemi açıkça kaydedin. Sıra etkisini azaltmak için kullanıcılar
arasında yöntem/görev sırasını değiştirin. Görev başına örneğin 10 dakikalık
önceden belirlenmiş sınır uygulayın; süre aşımı başarı değildir.

## Kaydedilecek ölçümler

| Ölçüm | Tanım |
|---|---|
| İçe alma süresi | Dosya seçmeden doğru ölçekli geometriyi görmeye kadar |
| Hazırlama süresi | İlk görünümden kullanılabilir kapalı profil/yüze kadar |
| Düzeltme işlemi sayısı | Yeniden ölçekleme, uç birleştirme, yeniden çizim, delik onarma, eğri dönüştürme |
| Geometri kontrolü | Beklenen bileşen/delik, fiziksel boyut ve kabul edilmiş sapma koşulları |
| Düzenlenebilirlik | Yerel eğri parametresi değişikliği ve ek sketch kısıt işinin ayrı sonucu |
| Görev durumu | completed, failed, timeout; açıklama ve engel |
| Kullanıcı gözlemi | Zorlandığı adım ve günlük işine uygunluk; doğrudan alıntı için onay |

Doğru geometri üretmeyen hızlı görev, kullanılabilir başarı sayılmaz.
Ham oturumlar ve eşleştirilmiş kişi/görev farkları gösterilir; yalnız ortalama
verilmez. Küçük ilk pilotta medyan/aralık ve tek tek başarısızlıklar raporlanır.
Gelir, müşteri talebi veya genel verimlilik artışı sonucu çıkarılmaz.

Başlangıç kaydı: [pilot-template.json](../examples/cad_validation/pilot-template.json).
`sessions` başlangıçta boştur. Gerçek kullanıcı onayıyla kimlik yerine takma
katılımcı kodu kullanın; mühendislik dosyalarını izinsiz paylaşmayın.

## Bir sonraki karar

Önce engelleri sınıflandırın: biçim uyumu, ölçek, kapanış/delik, eğri türü,
ya da native sketch kısıtları. En sık gerçek engeli giderin ve aynı görevlerde
tekrar ölçün. Bu pilotun amacı başka denklem aileleri eklemek için varsayım
üretmek değil, günlük işte hangi düzeltmenin gerekli kaldığını belirlemektir.
