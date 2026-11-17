# Problem, koordinat ve geometrik hata sözleşmesi

## Ayrı referanslar

1. **Kaynak sürekli nesne**: yalnızca sentetik deneylerde analitik olarak bilinir.
2. **Normalize piksel sınırı Γ**: eşikleme ve en yakın komşu yeniden örneklemeden sonra siyah birim karelerin birleşiminin sınırıdır. Kesinlik bu nesneye aittir.
3. **Sonlu parçalı model M**: doğru, çember/elips/yay, Bézier, B-spline veya Fourier parçalarının aralıklarla sınırlandırılmış birleşimidir.
4. **Tek örtük polinom F=0**: çalışma karesindeki bütün sıfır dallarıdır; uydurma noktalarıyla sınırlı değildir. Keşif katmanıdır.

Her şekil tek bir ikinci derece denklemle ifade edilemez. Bir polinom bir doğru parçasının tamamında sıfırsa destek doğrusunun tamamında sıfırdır. Sonlu kare kenarlarını yalnızca eşitlikle tanımlamak, sonsuz doğru uzantılarını da üretir.

## Koordinat dönüşümü

Kaynak önce EXIF yönüne getirilir. Ham boyut, EXIF yön kodu, uygulanma durumu ve yönü düzeltilmiş boyut ayrı kaydedilir. Saydamlık beyazla birleştirilir. `gray ≤ threshold` siyah kabul edilir. Eşikleme kaynakta yapılır; sonra **NEAREST** ile oranı koruyan tam sayı boyuta yuvarlanır. Kaynağın tamamı yerleştirilir; otomatik kırpma yapılmaz.

`S=1000`, boşluk p, yönü düzeltilmiş boyut W,H olsun:

```text
s=(1000-2p)/max(W,H)
W'=max(1,round(Ws)); H'=max(1,round(Hs))
ox=floor((1000-W')/2); oy=floor((1000-H')/2)
sx=W'/W; sy=H'/H
x=ox+sx*xs; y=1000-oy-sy*ys
xs=(x-ox)/sx; ys=(1000-oy-y)/sy
```

Burada `xs,ys`, **EXIF sonrası kaynak kenar koordinatlarıdır**; ham EXIF öncesi koordinatlar değildir. Gerçek sx ve sy yuvarlamadan ötürü biraz farklı olabilir. İki yönlü homojen dönüşüm matrisleri kaydedilir. Görsel satır/sütunu `(r,c)` şu geometrik kareyi temsil eder:

`[c,c+1] × [999-r,1000-r]`.

Kare kenarları 0 ve 1000'e ulaşabilir; piksel merkezi kullanılmaz. Köşesel temaslarda ön plan dört-komşuluğu uygulanır. Kalın çizginin alan sınırı çıkarılır; merkez hattı problemi çözülmez.

## Kesin sonlu parça

`D=B-A`, `r(t)=A+tD`, `0≤t≤1`. Eşdeğer örtük tanım:

`dy(x-ax)-dx(y-ay)=0`, **ve** `0≤D·(X-A)≤D·D`.

Sonlu aralık zorunludur. Birleşimin tek tam ifadesi `min_i d(X,segment_i)²=0` olabilir; `clip` ve `min` içerir, polinom değildir. Ardışık eşdoğrusal kenarları birleştirmek geometrik kayıp oluşturmaz. Mevcut 512 adet 3×3 maske testi tüm birim kenarları ve işaretli alanı bağımsız olarak denetler.

## Uygulanan kısıtlı seçim

```text
incelenen adaylar içinde min C(M)
E_computed(Γ,M) ≤ ε
T_checked(M) = T_reference
```

Asıl araştırma hedefi `E=d_H` ve tam topolojik eşitliktir. İlk kabul hızlı hata/poligon denetimidir. 2.2'de doğru/Bézier/B-spline ve kanonik tam çember/elips için ayrıca aralık hata kapsaması ve topoloji yeter koşulları denetlenir. Temaslı yürüyüşlerde boş üçgen silme tanığı bağımsız olarak yeniden oynatılabilir. `strict` bu ikinci kanıtı zorunlu tutar. [Kapsam ve argüman](certification.md). Genel probleme kesin optimum bulunmuş sayılmaz; dengeli tercih hata/maliyet uzlaşmasıdır.

## İki yönlü hata

Yönlü uzaklık `h(A,B)=sup_(a∈A) inf_(b∈B)||a-b||`; Hausdorff `H=max(h(A,B),h(B,A))`.

Eğri M, H uzaklığı en çok δ olan P poligonuna dönüştürülür. Γ ve P'nin **her kenarı**, en fazla h yay aralığıyla bölünür; bütün köşeler örnektir. Her halka ayrı örneklenir. Çok küçük halka hiçbir zaman atlanmaz. Her örnekten karşı tarafın **sonlu doğru parçalarına** GEOS uzaklığı hesaplanır; en yakın örnek noktasına uzaklık kullanılmaz.

İki yöndeki en büyük örnek uzaklığı `d_s`, gerçekleşen en büyük örnek aralığı `h_max` olsun. Uzaklık fonksiyonunun 1-Lipschitz olmasından:

```text
H(Γ,P) ≤ d_s + h_max/2
H(Γ,M) ≤ d_s + h_max/2 + δ
```

Her poligon noktası, yay üzerinde en çok `h_max/2` uzaktaki bir örneğe sahiptir; üçgen eşitsizliği sonucu verir. Hızlı hesap kayan nokta payı `1e-8` ekler. Bu pay doğrulanmış aralık aritmetiği değildir; tablodaki sonuç **float64 ile hesaplanan üst sınırdır**. Ayrı `certification.hausdorff_upper_bound`, varsa, bütün bu adımların dışa yuvarlanan yeniden hesabından gelir. Üst düzey `verified_numerical_certificate`, bu ayrı sertifikanın varlığını belirtir; hızlı tablo sayısını sonradan sertifikalı yapmaz. Kesin referansla yapısal özdeşlik varsa hata sıfırdır. Düşük örnek artığı tek başına kabul nedeni değildir.

Varsayılan h=1; yaklaşımda `min(h, max(0.05, ε/4))`. Varsayılan δ=0.05; yaklaşımda `min(δ,max(0.0001,ε/16))`. Gerçekleşen aralıklar kaydedilir. Çok küçük ε, yaklaşık adayların muhafazakâr biçimde reddedilmesine yol açabilir; kesin model kalır.

RMS, her iki yönde örnek uzaklık karelerinin yay uzunluğu ağırlıklı ortalamasının kareköküdür. İntegralin örnekleme yaklaşımıdır. `sampled_hausdorff`, `forward_max`, `backward_max` ölçülmüş değerlerdir. `hausdorff_upper_bound` farklıdır. Parça kayıtlarındaki hata **sahip halka kapsamındadır**, parçaya özel hata gibi sunulmaz.

## Tolerans kontrollü eğri değerlendirme

- Doğru parçaları tamdır.
- Çember/elips: `||r''(t)|| ≤ max(rx,ry)`. Kiriş interpolasyonu için vektör hata sınırı `max(rx,ry) Δt²/8`; bölüm sayısı buna göre seçilir.
- Kübik Bézier: de Casteljau ile ikiye bölünür. Dört kontrol noktasının **sonlu kirişe** uzaklığı ≤δ ise dışbükey zarf eğriyi kirişin δ kapsülünde tutar. Sürekli izdüşüm, ters yöndeki kiriş-eğri mesafesine de aynı sınırı verir. Aksi halde alt bölme devam eder; derinlik/nokta limiti aşılırsa yakınsamama hatası üretilir. Sınır, kontrol noktalarının referans şekle mesafesi değildir.
- Kübik B-spline: her basit iç düğüm aralığı uç değerleri ve türevleriyle tam kübik Bézier'e çevrilir; aynı değerlendirme kullanılır. Dışa uzatma yoktur.
- Sertifikada B-spline dönüşümü tam rasyonel de Boor/Hermite ile yeniden yapılır. Tam koniklerde rasyonel çeyrek-çember parametresi, Taylor dönme kapsamı ve `max(rx,ry)/n²` kiriş sınırı kullanılır. Bunlar hızlı float64 önizlemesinden ayrı denetimlerdir.
- Fourier: `||r''|| ≤ Σ k²(||a_k||+||b_k||)` ve `M Δt²/8` kiriş hatası kullanılır. Bu ailenin normal değerlendiricisi float64'tür; aralık sertifikası henüz yoktur.

PNG/PDF/SVG önizlemelerinde kullanılan eğri yaklaşımı değerlendirmedeki δ'dan gevşek olamaz. B-spline ve Fourier SVG'de vektör çokgenidir; toleransı metaveridedir. Bézier, çember/elips ve yaylar yerel vektör elemanlarıdır.

## Alan ve süreklilik

Alan, dış halkaların alanı eksi iç boşlukların alanı (içteki adalar ayrı dış bileşen) olarak hesaplanır. Yaklaşık eğri için poligon alan farkı raporlanır. Ek `area_curve_uncertainty_bound`, geçerli basit halkada δ-tüp alanından gelen muhafazakâr `sum(2 L(P)δ+πδ²)` tahminidir; sayısal sertifika değildir. Öz-kesişen reddedilmiş adayın alanı geçerli şekil alanı sayılmaz.

C0: komşu parçaların uç mesafesi; `>1e-7` adayı reddeder. Teğetlerin yönlü açısı derece olarak raporlanır; sıfır türevde açı tanımsızdır. Keskin köşe geçerli olduğundan C1 zorlanmaz. Teğet açısının sıfır olması türev büyüklüklerinin eşit olduğunu kanıtlamaz; yalnızca G1 yön tanısıdır.

## Topoloji kapsamı

Referans; halka kimliği, outer/hole yönü, en küçük kapsayan ebeveyn, bileşen kimliği ve noktasal temas ilişkilerini taşır. Adayda halka kaybı, sıfır alan, yanlış yön, öz-kesişim, yeni çaprazlama/temas veya içerilme değişimi reddedilir. Farklı yaklaşık halkalar arasında mesafe `>2δ` olmalıdır; belirsiz yakınlık reddedilir. GEOS'un geçerli poligon tanımı kullanılır.

Bu ilk poligon testi, aynı halkanın δ altı eğri döngülerini tek başına dışlamaz. `scope=polygonized_with_inter_ring_clearance` bunu belirtir. Ayrı rasyonel Bernstein/Jordan sertifikası başarılı olursa `analytic_isotopy_proven=true` olur; aksi halde bu iddia yapılmaz. Kesin piksel modeli için yapısal özdeşlik topolojiyi korur; dejenere noktasal temaslar bile kaybolmaz. Bu nedenle kesin model güvenli geri dönüştür.

2.2'de `scope=exact_planar_graph_isotopy_empty_triangles`, temaslı referans için ayrı bir kanıt yoludur. GEOS geçersizliği yalnızca yeniden oynatılan yerel izotopi tanığı ile aşılabilir; genel geçersiz poligonlara izin verilmez. Bütün güncel kenarlar ve üçgen içinde kalmış bileşenler tam aritmetik ile denetlenir; temaslar ve yüzler korunur. Konik tam tur parametresi `[0,float(2π)]` etiketinde `φ=2πt/float(2π)`'dir; yakın açık yay aynı nesne değildir.

## Örtük polinomun ayrı tanıları

`u=(x-500)/500`, `v=(y-500)/500`; `F=Σ_(i+j≤d)c_ij u^i v^j`. SVD ile `min||Ac||₂`, `||c||₂=1`; sıfır polinomu engellenir. En büyük katsayı pozitif yapılarak işaret belirsizliği giderilir. Koşul sayısı raporlanır; sayısal tekillikte `null`.

`algebraic_rms`, F'nin artığıdır. `|F|/||∇F||` yalnızca birinci mertebe mesafe tahminidir; herhangi bir örnekte gradyan ≤1e-12 ise RMS `null` olur. 501×501 çalışma ızgarasında sıfır eğrisi çıkarılır; açık/kapalı dal sayıları ve iki yönlü örnek nokta bulutu uzaklığı ayrıca raporlanır. Küçük dallar 2 birim ızgarada kaçabilir. Bu tanılar tamlık/topoloji veya geometrik üst sınır sağlamadığı için polinom otomatik seçime kabul edilmez.

## Uygulamayla ilişkili doğrulanabilir kaynaklar

- [SciPy BSpline resmî başvurusu](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.BSpline.html): düğüm/katsayı/ derece sözleşmesi ve sonlu değerlendirme.
- [SciPy make_interp_spline](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.make_interp_spline.html): periyodik kübik adayların üretimi.
- [SciPy least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html): çember/elips ve uç kısıtlı yayların sayısal uydurması.
- [Shapely User Manual](https://shapely.readthedocs.io/en/stable/manual.html): sonlu geometri uzaklığı, poligon geçerliliği ve içerilme/temas işlemleri.

RDP yerel iteratif uygulamadır; küresel en az parça algoritması olarak kullanılmaz. Yukarıdaki Lipschitz ve kapsül argümanları bu uygulamanın hata sözleşmesini açıklar; kaynağın vaat etmediği bir garantiye atıf yapılmaz.
