# Araştırma ve teknik eğitim etkinlikleri

Bu etkinlikler çalışan uygulama ve gerçek CAD dosyalarıyla yürütülür.
Sınıf/öğrenci başarısı henüz ölçülmedi. [Örnek kataloğu](../examples/cad_validation/index.html)
ve gömülü kaynaklı `model.json` projeleri çevrimdışı kullanılabilir.

## 1 — Aynı şekil için farklı temsiller

Çember görselini otomatik, Bézier ve B-spline aileleriyle ε=1,2,3,5'te inceleyin.
Her koşuda parça, serbest parametre üst sayımı, bit maliyeti, örneklenmiş H ve
doğrulanmış U'yu ayrı kaydedin. Kesin piksel sınırı ile ideal çemberin neden
aynı referans olmadığını açıklayın. Tolerans küçülürken kesin modele dönüş
olmasını başarısızlık, doğruluk veya sadelik açısından ayrı tartışın.

Beklenen yöntem: karşılaştırma tablosunda kabul/ret nedenlerini okuyun;
tek bir ikinci derece denklemin keyfi bir silueti tam temsil edeceğini varsaymayın.
Farklı deneylerde aynı model seçilirse de bunu sonuç olarak kaydedin.

## 2 — Matematiksel aralık ve fiziksel birim

`mixed/model.json` projesini açın. Bir doğru, çember yayı, elips yayı ve kübik
seçip katsayı/aralıklarını inceleyin. Yayı sonsuz eğriye uzatmanın şekli nasıl
değiştireceğini gösterin. Parametrik u ile geometrik açı t'nin hangi temsilde
farklı olduğunu denklemlerden bulun.

CAD kutusunda 0.1 mm/koordinat ve 0.01 cm/koordinat seçin. İki dosyanın aynı
fiziksel geometriyi üretmesi gerekir; sayıların ve birim etiketinin birlikte
değiştiğini kontrol edin. İnç örneğinde de aynı dönüşümü hesaplayın.
Ölçeğin görüntüden ölçülmediğini, kullanıcı tarafından verildiğini belirtin.

Kaynak sertifikası U, ölçek s, CAD aktarım tahmini V ise `sU+V`'yi hesaplayın.
V float64 olduğu için toplamı aralık sertifikası diye etiketlemeyin. İdeal
nesnenin gerçek boyutuna ilişkin hangi bilginin hâlâ eksik olduğunu yazın.

## 3 — Topoloji ve CAD kullanımı

`ring/model.json` ile tek bileşen/tek delik örneğini, `components/model.json`
ile iki bileşeni karşılaştırın. Üç CAD biçiminde delik/bileşen sayısını kontrol
edin. Yalnız görsel benzerliğin deliğin korunmasını garanti etmediğini açıklayın.
Yeniden açma denetimindeki `polygon_nesting_preserved` ile kaynak modelin
`analytic_isotopy_proven` alanlarının hangi geometriye ait olduğunu ayırın.

Fourier örneğini açın. CAD kutusunda yaklaşım izni kapalıyken verilen ret
gerekçesini okuyun; izin açıkken .cad.json içinde hangi parçanın yaklaştırıldığını
bulun. Kontrol noktası düzenlenebilen NURBS, kontrollü poligon yaklaşımı ve
CAD programının native kısıt geçmişi arasındaki farkları kendi cümlenizle yazın.

## Değerlendirme ölçütü

Doğru yanıt tek bir güzel çizim değildir. Öğrenci referans sınırı, parametre
aralığını, birimleri, hata türünü, topoloji kapsamını ve sadelik ölçütünü doğru
etiketlemelidir. Öğretmen bu başlıklarda hataları ayrı kaydeder; henüz ölçülmeyen
öğrenme kazanımı iddiası yapılmaz.
