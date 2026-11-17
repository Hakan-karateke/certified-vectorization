# Doğrulanmış hata ve analitik topoloji sertifikası

2.3'te `certification.py`, aday üretiminden ve GEOS kabul testinden bağımsız bir denetleyicidir. **Doğru, kübik Bézier/B-spline, pozitif ağırlıklı rasyonel çember/elips yayları, kanonik tam çember/elips ve boş üçgen tanıklı çokgenler desteklenir.** Genel örtük eğri tekilliklerini çözen bir cebirsel geometri paketi değildir. Fourier ve eski açısal konik yaylar için sonuç `undetermined` olur. Sürüm 1.3 sertifikaları aşağıdaki yeter koşullara bağlıdır.

## Neyin doğruluğu kanıtlanır?

Referans Γ, kayıtlı tamsayı piksel kenarlarıdır. Modelin binary64 katsayı/düğümleri **tam dyadik rasyonellerdir**. Konikte dönme açısı dyadiktir fakat gerçek sin/cos ile yorumlanır; tam turdaki π sembolik matematik sabitidir. Sertifika `H(Γ,M) ≤ U ≤ ε` ve yeter koşullarda aynı düzlemsel topolojiyi doğrular. İdeal sürekli nesnenin keşfedildiği veya optimum katsayıların bulunduğu sonucunu vermez.

`status=proven` için hem hata hem topoloji gerekir. `verified_numerical_certificate=true` tek başına yalnızca hata kapsamasının hesaplanabildiğini belirtir; `within_tolerance` ayrıca okunmalıdır. `analytic_isotopy_proven` topoloji koşuludur. `undetermined`, şeklin yanlış olduğunu kanıtlamaz: yeter koşullar veya kaynak bütçesi sonuç vermemiş olabilir.

## Aritmetik sözleşmesi

Temel `+,-,*,/` işlemlerinin her sonucunda alt uç `nextafter(…,−∞)`, üst uç `nextafter(…,+∞)` ile genişletilir. Bölünen aralık sıfırı kapsıyorsa işlem belirsizdir. Öklid normunda kareler, toplam ve karekök dışa genişletilir. Rasyonel→binary64 dönüşümü, `Fraction` ile tam karşılaştırılarak gerekirse komşu sayıya genişletilir. Aralıkta sıfıra bölme, sonlu olmayan sonuç ve bütçe aşımı kanıt başarısı sayılmaz.

Varsayımlar: IEEE-754 binary64 temel işlemler ve karekök, olağan doğru yuvarlama, kademeli alt taşma; yürütmede bu işlemleri yeniden ilişkilendiren `fast-math` yoktur. Binary64 ve subnormal kullanılabilirliği başlangıçta denetlenir. Bu bir donanım/NumPy uygulamasının biçimsel doğrulaması değildir; desteklenmeyen donanım için koşulsuz garanti verilmez. Temel aritmetik 500 tohumlu dyadik çiftte tam rasyonel sonuçlara karşı ayrıca test edilir. Bu test teoremin yerine geçmez.

## Eğriyi kapsayan poligon

1. Kontrol noktaları `Fraction`'a çevrilir. de Casteljau, `t=1/2`'de **tam rasyonel** alt bölme yapar.
2. Her yaprağın kontrol noktalarının sonlu kirişe uzaklığı aralıklarla üstten kapsanır. Kontrol zarfı kirişin δ kapsülündeyse bütün eğri bu kapsüldedir.
3. Ters yönde, kiriş doğrultusuna sürekli izdüşüm iki uç arasında tüm değerleri alır. Böylece her kiriş noktasının eğride en çok aynı δ uzaklıkta bir karşılığı vardır: simetrik Hausdorff sınırı elde edilir.
4. Rasyonel kiriş uçlarının çizim/ölçüm için binary64'e çevrilme hatası ayrıca eklenir. Sonuç `curve_to_polygon_bound` alanıdır; yalnızca kontrol noktalarının referansa artığı değildir.

Derinlik 24 ve parça başına 20.000 yaprak limitleri aşılırsa sonuç belirsizdir.

### B-spline'ın tam Bernstein dönüşümü

`rational_splines.bezier_spans`, düğümleri ve kontrol katsayılarını Fraction'a dönüştürür. Her basit iç düğüm aralığında uç değerleri ve türevleri **tam de Boor** ile hesaplar. `[a,b]` aralığının kontrol dizisi `S(a), S(a)+(b−a)S'(a)/3, S(b)−(b−a)S'(b)/3, S(b)`'dir. Böylece kaydedilmiş spline'ın tam kübik eşdeğeri elde edilir; SciPy'nin yuvarlanmış türevleri sertifikada kullanılmaz. Önizleme mevcut float64 değerlendiriciyi kullanmaya devam eder.

Her aralık yukarıdaki rasyonel de Casteljau denetimine girer. Aralıklar ve halka kapanışı tam rasyonel eşitlik gerektirir. Float64'te küçük görünen bir uç açıklığı kanıtta sıfıra yuvarlanmaz. Üretilen 8/16/32/64 örnekli periyodik spline'ların düğümleri dyadik olduğundan kapanış tamdır; farklı kayıtlar bu koşulu sağlamazsa belirsizdir. En çok 2048 düğüm aralığı desteklenir. Düzensiz düğümlerde dönüşüm bağımsız tam Cox taban toplamıyla test edilir.

### Rasyonel konik yaylar ve tam uç birleşimi

`rational_arcs.py`, artan `[a,b]` aralığında `u=(t-a)/(b-a)` kullanır:

```text
r(u) = [(1-u)² A + 2u(1-u)V + u² B] / [(1-u)² + 2wu(1-u) + u²].
```

Çemberde asıl katsayılar A, B ve yönlü `s=bulge` değeridir. `J=(-(B_y-A_y),B_x-A_x)`, `w=(1-s²)/(1+s²)` ve `V=w(A+B)/2-sJ/(1+s²)`. `0<|s|<1` ve A≠B gerekir. Bunlar tam rasyonel işlemlerdir. Merkez `C=(A+B)/2+(1-s²)J/(4s)` ve `R²=||B-A||²(1+s²)²/(16s²)` türetilir; ikinci bir merkez/yarıçap önbelleği tutulmaz. Yerine koyma, `||r(u)-C||²=R²` kimliğini verir. Pozitif s, A→B yönünde saat yönünün tersindeki küçük yayı seçer; açısal uç tahmini gerekmez.

Elipste asıl katsayılar A,P,B ve `0<w<1`'dir; V=wP. Üç kontrol eşdoğrusal olamaz. Bu koşul eliptik konik yayı verir. Uydurma daha dar `[0.15,0.98]` ağırlık aralığı kullanır. Bu derece 2 **rasyonel** parametrik eğridir. Konik sınıflandırması için [Michigan Tech ders notu](https://pages.mtu.edu/~shene/COURSES/cs3621/NOTES/spline/NURBS/RB-conics.html).

Denetleyici `(A,1),(V,w),(B,1)` homojen kontrollerini `Fraction` ile kurar ve üç koordinatta tam de Casteljau bölmesi yapar. Ağırlıklar her bölmede pozitiftir. Öklid kontrolleri `H.xy/H.w` dışbükey zarf/kiriş kapsülü denetimine girer; sadece kontrollerin referansa artığı hata sayılmaz. [Pozitif ağırlıklı rasyonel Bézier dışbükey zarfı](https://pages.mtu.edu/~shene/COURSES/cs3621/NOTES/spline/NURBS/RB.html), kapsamanın temelidir.

Topoloji denetiminin rasyonel yapraklara uygulanması için monotonluk ayrıca gerekçelendirilir. Kiriş izdüşümleri `s_i` sıralıysa rasyonel izdüşüm `Σp_i(u)s_i`, `p_i∝binom(n,i)w_i u^i(1-u)^(n-i)` olur. İç aralıkta türev `Cov_p(s_i,i)/(u(1-u))`'dur. Sıralı s_i için kovaryans negatif değildir; farklı uçlar ve pozitif ağırlıklar nedeniyle sıkı pozitiftir. Böylece polinom yapraklardaki monotonluk, ayırıcı yarı düzlem ve komşu olmayan zarf ayrıklığı argümanı korunur. Bu yeter koşullar sağlanmazsa kanıt verilmez.

Yaylar doğru/Bézier/spline ile aynı halkada bulunabilir; her birleşim **tam rasyonel C0** gerektirir. Bir ULP uç açıklığı bile reddedilir. G1 teğet açısı raporlanır; teğet sürekliliği zorlanmaz. Eski merkez/yarıçap/açısal aralık kayıtları çizilir, sessizce dönüştürülmez; açık yaylarına tam birleşim kanıtı verilmez. Tam kanonik konikler mevcut ayrı kapsama yolunu korur.

## Bütün sınır için hata kapsaması

Γ ve kapsayan poligon P'nin **her kenarında**, tam `k/n` oranındaki örnek noktalar aralıklarla kapsanır. Her köşe örnektir; küçük bileşenler atlanmaz. Gerçekleşen yay aralıklarının dışa yuvarlanmış üstü `h⁺` saklanır.

Her örnek için STRtree bir karşı kenar **tanığı** seçer. Tanığın gerçekten en yakın olduğunun kanıtlanması gerekmez: herhangi bir karşı kenara uzaklığın aralık üstü, karşı şekle uzaklığın da üstüdür. Uzaklık GEOS'tan alınmaz; seçilmiş sonlu kenara izdüşüm ve kırpma aralık aritmetiğiyle yeniden hesaplanır. İki yönde tanık üstlerinin en büyüğü `d⁺` olsun. Son toplama da dışa yuvarlanır:

```text
H(Γ,M) ≤ d⁺ + h⁺/2 + δ⁺ = U.
```

Uzaklık fonksiyonunun 1-Lipschitz olması bu bağıntıyı bütün kenarlara taşır. RMS ve alan farkı bu sertifikadan bağımsız örneklenmiş/poligonlaştırılmış tanılardır; onlara doğrulanmış integral değeri etiketi verilmez. Halka başına 500.000 sertifika örneği limiti vardır. Varsayılan sertifika örnek aralığı en çok 0.5, düzleştirme hedefi en çok 0.025 birimdir; çok küçük ε için ayarlanır.

## Analitik izotopi için yeter koşullar

Jordan yolunda denetleyici, eğri ve referansın **basit ve birbirinden ayrık sonlu Jordan halkaları** olduğunu aşağıdaki rasyonel tanıklarla doğrular:

- Her yaprağın kiriş yönündeki türev Bernstein katsayıları negatif değildir ve uçlar farklıdır. En az bir katsayı pozitiftir; Bernstein ağırlıkları iç aralıkta pozitif olduğundan kiriş doğrultusundaki ilerleme kesin artandır. Yaprak kendi içine dönmez.
- Bitişik yaprakların ortak ucu tam rasyonel olarak aynıdır. Bu uçtan geçen bir ayırıcı doğrunun normal vektörü sayısal olarak önerilir; bütün kontrol noktalarının gerekli yarı düzlemlerde olması **tam rasyonel skaler çarpımlarla** denetlenir. Uç haricinde sıkı ayrım vardır.
- Bitişik olmayan kontrol zarfları tam rasyonel ayırıcı eksen testiyle kesin ayrı olmalıdır. Dışa yuvarlanan kutular yalnızca güvenli erken eleme içindir. Bu koşul başka halkalarla temas ve kesişimi de dışlar.

Bir yaprağın kendi kirişine doğrusal homotopisi kontrol zarfında kalır ve kiriş yönünde kesin artar. Ayırıcılar bütün homotopi boyunca komşu olmayan yayları ayrı tutar; bitişikler sadece ortak uçta buluşur. Bu nedenle eğrinin kapsayan poligona dönüşümü gömülü halkaların izotopisidir. Referans poligonu için de aynı ayrıklık kontrolleri yapılır.

Son olarak işaretli alanlar ve ışın kesişimleri tam rasyonel hesapla belirlenir; her etiketli halkanın en küçük kapsayan ebeveyni ve yönü karşılaştırılır. Basit ayrık sonlu düzlemsel Jordan halkalarının aynı içerilme ağacına sahip olması düzlemde aynı yerleşim topolojisini verir. Bu, **R²'de ortam izotopisi** kapsamıdır; referanstan modele her ara şeklin ε tüpünde kalması veya çalışma karesinin kenarının sabit tutulması iddia edilmez.

Yeter koşullar gerekli değildir. Gerçekte kesişmeyen iki eğrinin kontrol zarfları çakışabilir; bu durumda kanıt verilmez. Toplam 5000 yaprak sınırı uygulanır. Noktasal temaslı referanslar genel Jordan yoluyla sertifikalanmaz. **Kesin modelin sıralı referans kenarlarıyla yapısal özdeşliği** ise ayrı, doğrudan bir kanıttır: bütün temaslar aynen kalır, H=0'dır.

Bu, rasyonel yeter koşulları yürütmede denetleyen bir algoritmadır; Coq/Lean biçimsel doğrulaması veya bağımsız bir ispat asistanı çıktısı değildir. Proje yeniden açıldığında katsayılardan sertifika yeniden hesaplanır; JSON içindeki başarı bayraklarına güvenilmez.

## Tam çember ve elips

Kanonik aralık `[0,float(2π)]`, `full_turn=true` ile **tam tur** anlamındadır: gerçek faz `φ=2π t/float(2π)`'dir. Sağ uç π'nin dyadik yaklaşımı olarak açık bırakılmış bir yay değildir; faz etiketi olarak tam tura karşılık gelir. Sayısal değerlendirici iki ucu aynı noktaya sabitler. Eski 2.0/2.1 dosyalarının aynı kanonik aralığı bu sözleşmeye yükseltilir; yakın fakat farklı bir aralık tam tur sayılmaz. Bayrak aralıktan türeyen açıklamadır; ayrı bir serbest parametre değildir. Genel yaylar mevcut radyan aralığını korur ve bu sertifikaya girmez.

Her çeyrek birim çember **tam rasyonel** `v(q)=((1−q²)/(1+q²), 2q/(1+q²))`, `q∈[0,1]` ile kapsanır; diğer çeyrekler tam işaret/değiş tokuştur. Çember/elips pozitif eksenlerle ölçeklenir ve döndürülür. `φ'=2/(1+q²)`, `|φ''|≤4` olduğundan `||r''(q)||≤8 max(rx,ry)`. n eşit q aralığında simetrik kiriş interpolasyon hatası `max(rx,ry)/n²` ile sınırlıdır. Gerçek uçların aralıklarından float kiriş uçlarına dönüşüm hatası ayrıca eklenir.

Dönme açısında libm sin/cos'a garanti atfedilmez. |θ|≤64 radyan önce tam ikiye bölmelerle |x|≤1/2'ye indirilir; sin/cos alternatif Taylor serilerinin 14 terimi ve ilk atılan terimi Fraction ile kapsanır. Çift açı işlemleri dışa yuvarlanır. Gerçek dönmenin ortogonal olduğu matematiksel özelliği, kiriş hata bağıntısında kullanılır. Büyük açı, sıfır/negatif eksen veya 20.000 kiriş sınırı belirsizlik nedenidir.

Pozitif eksenli tam koniğin basit kapalı halka olduğu analitiktir. Bütün gerçek yaylar ve yaklaşık kirişleri, rasyonel parametrenin aralık uzantısıyla kutularda birlikte kapsanır. Başka halkaların kontrol zarfları/kutularıyla tam rasyonel ayırıcılar, **halkalar arası** ayrıklığı doğrular. Yaklaşık poligonlar ve referans için Jordan/nesting kontrolleri de yapılır. Eşzamanlı kiriş homotopisi başka halkalara değmediğinden hareketli diğer halka noktalarına göre sarım sayısı sabittir. Başlangıç/son halkalar basittir; yön ve içerilme ağacı aynı olduğunda düzlemsel izotopi sınıfı aynıdır. Aynı koniğin homotopisinin her ara anda konik olması iddia edilmez. Çakışan kapsama kutuları kanıt üretmez; çok yakın halkalar muhafazakâr biçimde belirsiz kalabilir.

## Temaslı sınırlar: boş üçgen tanığı

`topology_simplification` Jordan koşulunu sağlamayan piksel yürüyüşlerinde ayrı bir **düzlemsel çizge** yolu sağlar. Bir köşe B, komşuları A,C arasında silinmeden önce kapalı ABC üçgeni, modelin diğer bütün güncel kenarlarıyla sınanır. A/C uçları dışında kesişim, üçgen içinde kalmış küçük bir bileşen, sınır örtüşmesi veya temas varsa silme reddedilir. Tekrarlanan temas köşeleri hareket ettirilmez. Eşdoğrusal, geriye dönmeyen AB∪BC=AC özdeşliği ayrı güvenli durumdur. Her halkada en az üç köşe bırakılır.

Üçgen içinde başka çizge bulunmaması, AB+BC yolunu AC'ye diğer çizgeyi ve A/C'yi sabit tutarak taşıyan yerel düzlemsel izotopi verir. Bu adımların bileşkesi noktasal temasları, dönel kenar düzenini, yüzleri ve bileşen/boşluk ilişkilerini korur. Bu nedenle GEOS'un geçersiz saydığı kendine dokunan bir referans, yalnızca **yeniden doğrulanan böyle bir tanıkla** sadeleştirilebilir; genel geçersiz adaylar kabul edilmez.

Öneri aşaması üç tarama/en çok 8N denemeli açgözlü aramadır; küresel minimum değildir. Her yeni AC kirişi, temsil ettiği **bütün orijinal alt zincire** tam rasyonel karesel uzaklıkla sınanır; adım hataları biriktirilmez. Tanık orijinal global köşe indekslerinin silme sırasıdır. Denetleyici başlangıç referansından her boş üçgeni baştan sınar, sonuç kenarlarını kayıtlı modelle birebir karşılaştırır. Kayıt/açma veya kullanıcı seçimi tanığı yeniden oynatır. Geometrik U ayrıca aralık ölçümüyle hesaplanır; tanık tek başına hata kanıtı değildir.

Kaynak sınırı 20.000 tamsayı köşedir. Birlikte çizilen bütün halkalar denetlenir. Tanık büyüklüğü `32 × silme sayısı` bit olarak ayrıca raporlanır; geometri kodlama maliyetine katılmaz çünkü modeli yeniden çizmek için katsayılar yeterlidir. Referans ve kanıt verisini içeren bütün proje dosyası daha büyüktür.

## Masaüstü seçenekleri

- **Seçili modeli kanıtlamayı dene** (`selected`, varsayılan): normal aday seçimi yapılır, seçili model denetlenir. Kanıt bulunamazsa durum/gerekçe gösterilir; sayısal kabul ayrı kalır.
- **Sertifikalı sonuç zorunlu** (`strict`): `status=proven` olmayan seçim reddedilir, kalan Pareto adaylarından yeniden seçilir. Kesin özdeşlik güvenli geri dönüştür. Tam çember/elips, uygun B-spline ve rasyonel karma yaylar sertifikalanabilir; Fourier veya eski açısal yaylar daha uzun bir geri dönüşe yol açabilir.
- **Yalnızca sayısal ölçüm** (`off`): eski bağımsız geometrik/topolojik denetim çalışır; sertifika hesaplanmaz.

Rapor tablosundaki `hausdorff_upper_bound` hızlı float64 ölçümünden gelir. Doğrulanmış U, ayrı `metrics.certification.hausdorff_upper_bound` alanındadır; bu iki sayının eşit olması gerekmez. Hızlı tablonun `bound_kind` alanı değişmez.

[NumPy nextafter resmî belgesi](https://numpy.org/doc/stable/reference/generated/numpy.nextafter.html), kullanılan komşu binary64 işlemine kaynak sağlar. İspatın geometrik yeter koşulları yukarıda uygulamaya özel olarak verilmiştir.

[SciPy BSpline](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.BSpline.html) düğüm/katsayı ve Cox taban sözleşmesinin kaynağıdır; tam rasyonel denetleyici yereldir. [NIST DLMF 4.19](https://dlmf.nist.gov/4.19), kullanılan sin/cos serilerini verir; kalan aralık ve çift açı kapsaması yukarıdaki yöntemle uygulanır.
