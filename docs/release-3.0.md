# Sürüm 3.0

Bu sürüm, makaleyle birlikte yayımlanan sürümdür.

## Değişen varsayılan: yerel çözünürlük

Önceki sürümler her görseli 1000 × 1000 birimlik bir çalışma düzlemine yeniden
örnekliyordu; hata sınırı ve topoloji sertifikası bu yüzden yeniden örneklenmiş
ikili görsele aitti. 3.0'da varsayılan ayar görseli **yeniden örneklemez**:

- bir çalışma birimi bir kaynak pikselidir, tolerans kaynak pikseli cinsindendir;
- çalışma düzleminin kenarı `max(genişlik, yükseklik) + 2 · kenar boşluğu` pikseldir;
- eski davranış `AnalysisConfig(working_size=1000)` ya da komut satırında
  `--working-size 1000` ile seçilir;
- 2.4 şemasından önceki proje dosyaları otomatik olarak eski düzlemle açılır.

Neden: en yakın komşu yeniden örnekleme ince çizgileri koparır ve yeni temas
noktaları üretir. 4096 × 4096 piksellik sentetik bir teknik çizimde 256 bileşen
2961'e, 9 temas noktası 2157'ye çıkmıştır; 2050 ikonun 7'sinde de bileşen, delik
ya da temas sayısı değişmiştir (`examples/icon_dataset/resampling_topology`).

`mdl_v1` kod uzunluğu artık düzlemin kenarına bağlıdır: koordinat başına
`ceil(log2(64 · N))` bit (N = 1000 için 16, ikon deneylerindeki N = 1040 için 17).

## Yeni: en az parçalı doğru + yay halkası

`optimal_arcs.py`, düğüm kısıtlı doğru parçası ve çember yayı halkaları için
sınıf içinde kanıtlı en az parça sayısını bulur. Yöntem, iki düğümden geçen bir
yayın bir ara düğüme en çok τ uzakta kaldığı bulge değerlerinin kapalı biçimli
uçları olan bir aralık oluşturmasına dayanır. Seçilen her yay tam rasyonel
aritmetikle yeniden doğrulanır. Aile `linearc` adıyla hatta adaydır.

Sınırlar: halkalar ayrı ayrı çözülür, temas ve açıklık kısıtı yoktur (temas
noktalı girdilerde aday reddedilir); yaylar en çok 512 düğüm atlar; arama
yavaştır (ikon başına onlarca saniye). `smooth_joints`, yay bulge'larını geçerli
aralıkları içinde değiştirerek teğet kırılmalarını azaltır; ölçülen etkisi küçüktür.

## Yeni: dış araçların çıktısını sertifikalama

`examples/certify_svg.py` herhangi bir vektörleştiricinin SVG çıktısını aynı
denetleyiciyle sertifikalar. `examples/certify_potrace.py` bunu Potrace 1.16
için 2050 ikonda uygular.

## Ölçek

Sertifikadaki 50.000 yaprak sınırı kaldırıldı (kutu kesişimleri uzamsal dizinle
bulunur); sınır izleyicinin 400.000 kenar sınırı ve sertifikanın halka başına
500.000 örnek sınırı parametre oldu. Ortak en az kenarlı çokgen ve sertifikası
67 megapiksellik, kontur haritası benzeri sentetik bir girdide çalıştırıldı.

## Bilinen eksikler

- Ortak (temas koruyan) arama "her an geçerli çözüm" veren türden değildir:
  düğüm sınırına ulaşınca geçerli bir alt sınır döndürür, uygun bir çokgen
  döndürmez. Yoğun çizgili ve çok temaslı girdilerde (2048 × 2048 sentetik
  çizim, taranmış bir harita kesiti) optimum kanıtlanamamıştır.
- Tarama bozulması ve yayımlanmış sonuçların denetimi betikleri depoda vardır,
  ancak deneyleri tamamlanmamıştır ve makalede kullanılmamıştır.
- Derlenmiş çekirdek karşılaştırması 2.9 sürümüyle, yeniden örneklenmiş
  görsellerde alınmıştır.
- Kullanıcı çalışması yapılmamıştır.

225 test geçmektedir.
