# Model aileleri, maliyet ve seçim

## Ortak model sözleşmesi

Her parça `kind`, `params`, artan `interval=[a,b]`, katsayılardan hesaplanmış `start/end`, `boundary_id`, `component_id`, ortak kaynak dönüşümüne başvuru, hata kapsamı ve toleranslar taşır. Bütün uzunluklar 1000'lik çalışma düzlemi birimindedir; açılar radyandır. Çember/elipste `direction=±1`, t artarken geometrik yönü belirler. Aralık dışı değerlendirme hatadır.

- Doğru: A,B uçları; `(t-a)/(b-a)` parametresi.
- Çember/elips: merkez, pozitif yarıçap(lar), elipste dönme açısı; yön ve açısal aralık. Tam halka 0..2π'dir. Yaylar ayrıca sonlu açısal aralık taşır.
- Kanonik `[0,float(2π)]` tam halka, gerçek faz `φ=2πt/float(2π)` kullanır; `full_turn=true` bunu açıklar. Bayrak aralıktan türetildiği için yeni bir serbest parametre veya geometri kodlama maliyeti değildir. Genel yaylar normal radyan aralığını korur.
- Bézier: dört 2B kontrol noktası; normalize `u=(t-a)/(b-a)`, Bernstein tabanı derece 3.
- B-spline: 2B katsayılar, kübik derece, düğüm vektörü ve geçerli aralık; bu sürümde iç düğümler basittir.
- Fourier: 2B merkez, K adet 2B kosinüs ve K adet 2B sinüs katsayısı; `r(t)=c+Σ(a_k cos(kt)+b_k sin(kt))`, `0≤t≤2π`. K tam sayıdır; bu bir polinom derecesi değildir.

Çember ve elips konik ailesinin güvenilir alt kümesidir. Parabol/hiperbol uydurma eklenmedi; açıklanmayan bir genel konik çözücüsü varmış gibi davranılmaz. Tam halkalara ek olarak karma arama rasyonel çember/elips yayları önerir; eski açısal kayıtlar da çizilebilir.

## Sınırlı aday üretimi

Kesin piksel modeli her zaman adaydır. ε>0'da RDP toleransları `0.25ε,0.55ε,0.85ε` denenir. Kapanış iki zincire ayrılır; sonuç bağımsız iki yönlü hata/topoloji denetiminden geçer. RDP toleransının doğrudan bütün modele garanti verdiği varsayılmaz.

Çember, normalize koordinatlarda radyal geometrik artıkla; elips PCA başlangıcıyla radyal ölçekli artıkla `least_squares` kullanılarak uydurulur. Elips çözümü ortogonal en küçük kareler optimumu değildir. Yakınsama, değerlendirme sayısı ve Jacobian koşul sayısı saklanır; nihai kabul bağımsız geometrik ölçüme dayanır.

Bézier: halka eşit yay örneklerinde ikiye bölünür; uçları sabit kiriş parametreli doğrusal en küçük kareler uygulanır. Kontrol noktası çözümü, doğrusal kiriş kontrol noktalarına minimum norm düzeltmedir; iki/üç noktalı az belirli küçük zincirlerde yapay döngüleri önler. Örnek artığı `0.3ε` veya `0.65ε` hedefini aşarsa zincir ortadan bölünür. Uç C0 koşulu yapısaldır. Bölme 2048 parçayla sınırlıdır; bu hedef nihai geometrik garanti değildir.

Karma yerel aday, her zincirde önce doğru, sonra iki uçtan geçen rasyonel çember yayı, sonra rasyonel elips yayı, ardından Bézier dener. Yay merkezi uçların orta dikmesi üzerindedir; tek değişkenli geometrik radyal uydurma yapılır. Açısal ilerleme monoton olmalıdır; |bulge|<0.9 koşulunu aşan büyük yaylar sonraki bölmeyle ele alınır. Elipste sabit kiriş parametreleri, [0.15,0.98] sınırlı ağırlık araması ve orta kontrol için doğrusal en küçük kareler kullanılır (40 iterasyon üstü). Bu bir geometrik optimum iddiası değildir. Tam model yine bağımsız ölçülür. Halka bazlı hybrid, o halka için hata koşulunu geçen en ucuz aileyi alır; bütün birleşim tekrar ölçülür ve topolojisi kontrol edilir. Tamamen reddedilmiş bir adayın bazı halkaları birleştirmede kullanılabilir; son birleşimin kabulünü bu durum belirlemez.

B-spline: 8/16/32/64 eşit yay örneği ve periyodik kübik interpolasyon. Düğüm sayıları sınırlı taranır. Global düğüm optimizasyonu, tüm bölümlemelerin dinamik programlaması ve bütün olası parça birleşimleri taranmaz. Kaynak limitleri/yakınsamama tanıları ret nedenidir.

## Temasları koruyan çokgen

`family=topology`, bütün halkalarda boş üçgen tanıklı köşe silme yapar. Bir köşe, komşularının kirişiyle değiştirilirken süpürülen kapalı üçgenin diğer kenarlarla yalnız sabit uçlarda buluşması gerekir. Üçgen içinde kalmış küçük delikler de engeldir. Tekrarlanan temas köşeleri sabit kalır. Yeni kiriş, bütün orijinal alt zincirine karşı tam rasyonel mesafeyle denetlenir; yerel adımların hatası toplanmaz.

Öncelik küçük yerel sapmadır; en çok üç tarama ve 8N teklif vardır. Küresel minimum garantisi yoktur. 0.70ε/0.85ε hedefleri incelenir. Otomatik mod bu aileyi yalnız referansta halka teması veya GEOS'a göre basit olmayan yürüyüş varsa ekler. En çok 20.000 kaynak köşe desteklenir. Silme sırası bağımsız yeniden oynatılır; tanık yoksa eski topoloji reddi geçerli kalır. Modelin maliyeti mevcut sonlu doğruların bit maliyetidir; `32 × silme sayısı` tanık bilgisi ayrıca raporlanır ve yeniden çizim için gerekli değildir.

## Köşe farkındalıklı aday grafiği

`adaptive.corner_graph`, yay üzerinde `max(4,4ε)` uzaklıktaki iki yönden dönüş açısını hesaplar. Açı eşiği 45°; yakın köşeler aynı yay penceresinde bastırılır. En güçlü köşe dikiştir. RDP kılavuzundaki tam referans köşeleri düğümdür; köşe adayları en yakın kılavuz düğümüne taşınır ve geçilmesi zorunlu yapılır. Dikişin bütün seçenekleri taranmaz.

Bir düğümden en çok 24 sonraki düğüme, zorunlu köşeyi atlamadan kenar önerilir. Uçları sabit doğru veya kübik Bézier referans alt zincirini temsil eder. Kübikte en çok beş monoton Newton yeniden parametreleme adımı uygulanır. Her referans kenarına karşı fark kübiğinin Bernstein katsayı normları bütün parametre aralığında eşleşme hatası üstü verir; teklif aşamasındaki bu float64 sınırı nihai sertifika değildir. Doğru uygunken daha pahalı kübik kenar saklanmaz.

Kenar maliyetleri `fixed64_v1`: doğru 424 bit, kübik 680 bit. DAG'de dinamik programlama toplam bit maliyetini en aza indirir. **Yalnızca bu kurulan yerel olarak uygun grafikte kesin en kısa yoldur.** Sürekli katsayı uzayı, bütün bölümlemeler, bütün dikişler veya topolojik olarak geçerli yolların tamamı için optimum değildir; seçilen yolun bütün şekil topolojisi sonradan denetlenir. 768 düğüm sınırı, eksik yol veya sayısal başarısızlık açık ret nedenidir. Otomatik modda `target_factor=0.72,0.84` denenir.

## Fourier ve bütçeli tavlama

Fourier, eşit yay örneklerinde doğrusal en küçük karelerle 4/8/16/32 harmonik dener; tasarım matrisi koşul sayısı saklanır. Sonlu periyodik seri kapalıdır, fakat öz-kesişimsiz olduğu varsayılmaz. Keskin köşelerde salınım yapabilir; köşe grafiğiyle aynı bağımsız kabul testine tabidir. Seriyi örtük polinom diye etiketlemeyiz.

`search_strategy=annealing`, `auto/adaptive` ailelerinde SciPy `dual_annealing` kullanır. Araştırılan değişkenler köşe eşiği `[30°,85°]` ve yerel hedef çarpanı `[0.60,0.88]`; başlangıç `(45°,0.72)`'dir. Parametreler 0.001°/0.0001 çözünürlükte önbelleklenir. Bütçe 4–100 farklı öneriyle sınırlı, yerel arama kapalıdır; varsayılan bütçe 20 ve tohum 20261015'tir. Amaç kabul edilenlerde bit maliyeti, reddedilenlerde büyük ceza değeridir. Başarısız öneri de tanısıyla aday kaydına girer. Son kullanıcı tercihi, öneriler eklendikten sonra Pareto kümesinde uygulanır.

Tavlama, sürekli sınırlı bir hiperparametre alanını stokastik araştırır; sonlu çalıştırmada küresel optimum kanıtı sağlamaz. Genetik algoritma ayrıca eklenmedi: aynı sınırlı aday üreticisine ikinci bir stokastik sürücü eklemek kanıt kapsamını artırmaz. [SciPy dual_annealing resmî belgesi](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.dual_annealing.html).

## Sadelik: fixed64_v1 kodlama maliyeti

`C(M)=64 R + 32 I + 8 P` **bit**. Bu, boyutsuz ve uygulanabilir sabit genişlikli geometri gövdesi kodlamasının tahmini maliyetidir; JSON dosyasının byte boyutu veya evrensel Kolmogorov karmaşıklığı değildir. Ortak çerçeve başlığı ve her aday için aynı olan referans/topoloji/koordinat dönüşümü dışarıda tutulur. Katsayılar float64'tür; kayıplı nicemleme yapılmaz.

| Tür | R: gerçek sayılar | I: tamsayılar | Serbest parametre üst sayımı |
| --- | --- | --- | --- |
| Doğru | 4 uç koordinatı + 2 aralık | 1 sınır kimliği | 4 |
| Rasyonel çember yayı | 4 uç koordinatı + 1 bulge + 2 aralık | 1 sınır kimliği | 5 |
| Rasyonel elips yayı | 6 kontrol koordinatı + 1 ağırlık + 2 aralık | 1 sınır kimliği | 7 |
| Tam çember / eski açısal yay | 2 merkez + 1 yarıçap + 2 aralık | sınır kimliği + yön | 3 |
| Tam elips / eski açısal yay | 2 merkez + 2 yarıçap + 1 dönme + 2 aralık | sınır kimliği + yön | 5 |
| Kübik Bézier | 8 kontrol koordinatı + 2 aralık | 1 sınır kimliği | 8 |
| Kübik B-spline | 2n kontrol koordinatı + (n+4) düğüm + 2 aralık | sınır kimliği + n | 2n + iç düğüm sayısı |
| Fourier, K harmonik | 2 merkez + 4K katsayı + 2 aralık | sınır kimliği + K | 2+4K |

P parça sayısıdır. Kübik derece ve tür sözleşmesi tür etiketinden bilinir. Parçadaki bileşen kimliği topoloji ağacından, uç koordinatları katsayılardan türetilir; tekrar kodlanmaz. Çember/elips yaylarında **açısal aralık uçları da serbesttir**; rapordaki serbest parametre sayımına tam halkada 0, yayda 2 eklenir. Paylaşılan uç eşitliği, periyodiklik ve diğer bağımlılıklar için boyut indirimi yapılmaz; bu nedenle sayı açıkça üst sayımdır. B-spline'ın serbest düğümleri de bilgi maliyetinde sayılır; rapor üst sayımı koordinat ve iç düğüm sayısını içerir.

Parça sayısı, serbest parametre üst sayımı, saklanan gerçek/tamsayı sayısı, maksimum derece, düğüm/kontrol noktaları ve aralık kısıtları ayrı raporlanır. Sayısal kararlılık koşul sayısı/yakınsama tanılarıyla görünürdür; uzunluk, derece ve koşul sayısı açıklamasız ağırlıklarla toplanmaz. Küçük maliyet tek başına kabul gerekçesi değildir.

## Pareto ve kullanıcı tercihi

Kabul edilen aday A, B'den hem C hem hesaplanan H üst sınırında daha kötü değilse ve en az birinde daha iyiyse B'yi domine eder. Domine edilmeyen bütün adaylar Pareto kümesidir; eşit geometri/maliyetli farklı aileler birlikte kalabilir.

- **Daha sade**: önce en küçük bit maliyeti; eşitlikte küçük hata.
- **Daha yüksek doğruluk**: önce küçük H üst; eşitlikte düşük maliyet. Piksel referansı kullanıldığından kesin model sıfır hatayla doğal olarak kazanabilir.
- **Dengeli**: Pareto kümesinde `log2(1+C/max(1,Cmin)) + (H_upper/max(ε,1e-12))²` en küçük olan. C ve Cmin bit cinsindendir; iki terim boyutsuzdur, ağırlıklar 1 ve 1'dir. Logaritma çok pahalı modellerin etkisini yumuşatırken, Cmin'e göre maliyet artışını korur. Bu bir kullanıcı tercihidir, min C kısıtlı probleminin kesin çözümü değildir. Eşitlik düşük bit maliyetiyle çözülür. 2.0'daki Cmax normalizasyonu, pahalı kesin model yüzünden makul maliyet farklarını bastırdığı için değiştirildi.

Manuel seçim yalnızca kabul edilmiş adaylar arasından yapılır ve seçim nedeni projeye yazılır. Yalnızca bir kabul edilmiş aday varsa üç tercih de aynı sonuca varabilir.

Seçimden sonra `selected/strict/off` sertifika politikası uygulanır. `strict`, hata ve analitik topoloji kanıtlanamazsa adayı reddedip yeniden seçer; bu durumda Pareto kümesi de güncellenir. Desteklenen aileler, koşullar ve sayısal/analitik ayrımı [sertifika belgesindedir](certification.md).

Rasyonel çember yayının maliyeti 488 bit, elips yayınınki 616 bittir.
Homojen kontroller tam olarak asıl katsayılardan türetildiği için tekrar
kodlanmaz; tanıda her rasyonel yay üç kontrol noktası sayılır. Yeni yayların
`interval` uçları birimden bağımsız parametre etiketleridir; açısal uçların
serbestliğiyle birlikte tekrar sayılmaz. Tüm katsayı sayımları yine paylaşılan
uç bağımlılıkları indirilmemiş üst sayımlardır. Bu modeller aynı parça sayısında
doğrudan 680 bitlik kübikle karşılaştırılabilir; bir parça azaltımı tek başına
kabul koşulu değildir.

## İkinci maliyet modeli: `mdl_v1` (2.7)

`fixed64_v1` her parametreyi 64 bit sayar ve paylaşılan uçları iki kez kodlar; bu
bir depolama üst sayımıdır, bir betimleme uzunluğu değildir. 2.7 ile her adayın
`complexity` kaydına iki parçalı bir kod uzunluğu eklenir:

- Gerçek sayılar 1000 birimlik çalışma düzleminde `2^-6` birimlik ızgarada
  kodlanır: gerçek başına `ceil(log2(1000·64)) = 16` bit.
- Kapalı C0 zincirinde her parçanın başlangıç ucu önceki parçanın bitiş ucudur
  ve yeniden kodlanmaz: doğru 2, çember yayı 3, eliptik yay 5, kübik Bézier 6
  gerçek. Tek parçalı halkalar (tam çember/elips, B-spline, Fourier) kendi
  serbest parametre sayılarıyla kodlanır.
- Parça türü 3 bit; halka başına parça sayısı, B-spline kontrol sayısı ve
  Fourier derecesi Elias-gamma koduyla (`2·floor(log2 n)+1` bit) yazılır.

Kontrol noktalı parçalarda (doğru, Bézier, B-spline) ızgaraya yuvarlama eğriyi en
çok `2^-6/√2 ≈ 0,011` birim oynatır (dışbükey birleşim özelliği); yani kod,
`ε + 0,011` içinde kalan bir modeli gerçekten betimler. Konik merkez/yarıçap ve
Fourier katsayıları için bu sınır iddia edilmez; orada `mdl_v1` yalnızca tutarlı
bir parametre sayımıdır. Sertifika her zaman saklanan (yuvarlanmamış)
katsayılar içindir.

Varsayılan seçim anahtarı geriye uyumluluk için `score_bits` olarak kalır;
`select_candidate(..., cost_key="mdl_bits")` ve tarama kaydındaki
`simple_strict_mdl_selected` alanı aynı adaylar üzerinde `mdl_v1` ile seçimi verir.
