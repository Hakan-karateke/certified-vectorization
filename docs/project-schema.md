# Proje JSON 2.3 sözleşmesi

Makine şeması: [project.schema.json](project.schema.json), JSON Schema Draft 2020-12. Çalışma zamanı doğrulaması `project.result_from_dict` içindedir; ek geometri ve kaynak limitlerini uygular. JSON NaN/Infinity içeremez; tanımsız değerler `null` olur. Kod/pickle çalıştırılmaz.

| Alan | İçerik |
| --- | --- |
| schema_version / application_version | `2.3` / `2.4.0`; 2.0/2.1/2.2 okunabilir |
| config | Eşik, boşluk, ε, aile, tercih, ölçüm/eğri toleransları, polinom derecesi, gömme, arama/bütçe/tohum/CPU ve sertifika politikası |
| normalization | Ham ve EXIF sonrası boyut, yön kodu, eşikleme/resize yöntemi, gerçek ölçekler/ofsetler, kaynak↔çalışma matrisleri, piksel kenarı sözleşmesi |
| reference_boundaries | Kayba uğramamış normalize kapalı piksel halkaları; son köşe ilkini tekrar etmez |
| boundaries | Seçilen modelin çizim için türetilmiş poligonları; otorite katsayılardır |
| topology | Halka id, yön/kind, parent_id, component_id, closed, dört-komşuluk, temas çiftleri, bileşen/boşluk sayısı |
| candidates | Geometri parçaları, hatalar, kodlama özellikleri, kabul/ret nedenleri, Pareto durumu |
| selected_id | Kabul edilmiş adayın benzersiz id'si |
| polynomial | İstenmediyse null; aksi halde derece, `[i,j,c]` terimleri, cebirsel/gradyan/koşullanma tanıları ve keşif sıfır çizgileri |
| metrics | Seçim özeti ve toplam süre |
| provenance | Kaynak yolu/SHA-256, isteğe bağlı orijinal byte gömme, normalize PNG önizleme, algoritma ve ortam sürümleri, tohum, seçim nedeni ve kapsam |

Her parça:

```json
{
  "kind": "line",
  "params": {"a": [20,260], "b": [20,740]},
  "interval": [0,1],
  "start": [20,260],
  "end": [20,740],
  "boundary_id": 0,
  "component_id": 0,
  "transform": "normalization.source_to_working",
  "errors": {"scope":"owning_boundary", "rms":0, "hausdorff_upper_bound":0},
  "tolerances": {"flatten":0, "sample_spacing":1, "join":1e-7, "floating_margin":1e-8}
}
```

`params`: line için a,b; circle için center,radius,direction; ellipse için center,radii,rotation,direction; bezier için dört controls; bspline için controls,knots,degree=3; fourier için center, K adet 2B cos ve K adet 2B sin katsayısı. Aralık artandır; çember/elipste direction t artışının yönünü belirler. Bütün koordinatlar çalışma düzlemindedir. `transform`, kaynak eşlemesini anlatır; katsayılara yeniden uygulanmaz.

Hata alanları: `sampled_hausdorff`, yönlü maksimumlar, yay ağırlıklı `rms`, hesaplanmış `hausdorff_upper_bound`, örnek sayısı/aralığı, düzleştirme δ, alan farkı/belirsizliği, C0 uç açıklığı, G1 açı tanısı ve topoloji kapsamı. Ayrı `metrics.certification` kaydı sürüm, dyadik katsayı yorumu, aritmetik, proven/undetermined durumu, gerekçeler, doğrulanmış U, within_tolerance ve analytic_isotopy_proven içerir. Üst düzey verified bayrağı bu ayrı kaydın varlığıdır; hızlı H tablosunun aritmetiği `bound_kind` ile tanımlı kalır. Parça hatası kendi halkasına aittir; `scope=owning_boundary` açıkça saklanır.

Yeni ayarlar: `search_strategy=deterministic|annealing`, `search_budget=4..100`, `random_seed=0..2^32−1`, `evaluation_workers=1..8`, `certificate_mode=off|selected|strict`. 2.0 dosyalarında eksikler varsayılanlarla doldurulur. Grafik düğüm/kenar/yerel optimum kapsamı parça tanılarında, tavlama parametreleri aday metrics.search_parameters içinde saklanır. Aynı tohumla yeniden uydurma yalnızca aynı algoritma/bağımlılık sürümleri için beklenir; proje açmak uydurma yapmaz.

2.2: `family=topology` temas koruyan çokgendir; parçaları mevcut `line` sözleşmesindedir. Adayın `metrics.topology_witness` alanında `version=empty_triangles_v1`, global kaynak köşe indeksleriyle `removed_vertices`, kaynak/deneme sayıları, öneri toleransı ve ayrı tanık bit sayımı saklanır. Başarı için bütün silmeler yeniden oynatılır ve son katsayılar eşlenir. Tanık değiştirilirse veya katsayılarla uyuşmazsa proje reddedilir.

Tam konikte `params.full_turn=true`, yalnız `[0,float(2π)]` kanonik aralığında kabul edilir. Faz `2πt/float(2π)` ve matematiksel π kullanır; uçlar tam aynıdır. Bayraksız eski kanonik halkalar yükseltilir. Genel yaylar radyan aralığıdır; yakın bir aralık tam halka diye tahmin edilmez. Ayrı sertifika sürümü `1.3`'dir. B-spline sertifikası düğümleri ve katsayıları tam rasyonel yorumlar; çember/elips dönmesi gerçek trigonometrik fonksiyonlarla kapsanır.

Açılışta kaynak görselden yeniden uydurma yapılmaz. Parça boyutları, aralık, pozitif yarıçap, düğüm sırası, uçların katsayılarla eşitliği, kimlikler ve referans topolojisi denetlenir. Seçilen adayın hatası/topolojisi ve maliyeti yeniden hesaplanır; kaydedilmiş kabul bayrağına tek başına güvenilmez. Çizim de katsayılardan yeniden üretilir. Referans görsel taşınmış/değişmişse hash doğrulaması bunu açıklar; model ve dışa aktarım kullanılabilir. Gömülü orijinal girdi yalnızca kullanıcı analiz öncesinde seçtiyse eklenir; türetilmiş normalize önizleme her projede bulunur.

Sürüm 2.0'ın seçilmiş katsayıları korunur; yeni tercih formülüyle otomatik yeniden seçim yapılmaz. Seçilen geometri ve sertifika yeniden denetlenir; kayıtlı proof bayrağına güvenilmez. Sürüm 1.0 kesin modeller bellekte yükseltilir. Eski sadeleştirilmiş modellerde orijinal Γ eksik olduğu için açıklayıcı ret ve yeniden analiz gerekir. Bilinmeyen şema sürümü sessizce tahmin edilmez. Yazma: hedef dizinde geçici UTF-8 dosya → tekrar açma/doğrulama → atomik değiştirme.

## 2.3 rasyonel yay sözleşmesi

Çember yayı `params={"arc":{"a":[x,y],"b":[x,y],"bulge":s}}` biçimindedir.
A ve B farklı, `0<|s|<1` olmalıdır. Elips yayı
`params={"arc":{"controls":[A,P,B],"weight":w}}` biçimindedir;
`0<w<1` ve doğrusal olmayan üç kontrol gerekir. Bu iki parametre kümesi,
önceki merkez/yarıçap/açısal biçimlere alternatiftir; aynı parçada karıştırılamaz.
Artan `[a,b]` aralığı radyan değildir: `u=(t-a)/(b-a)` kullanılır.
Yön, sıralı uçlar ile bulge işareti veya orta kontrol tarafından belirlenir.
Asıl katsayılar dyadiktir; çemberin türetilmiş homojen orta ağırlığı tam
rasyoneldir ve JSON'a yaklaşık bir kopyası yazılmaz. Formüller ve kanıt
[sertifika belgesindedir](certification.md). Sertifika sürümü 1.3'tür.

2.0–2.2 açısal yayları açıldığında aynı geometri korunur; otomatik dönüşüm
ve yeniden uydurma yapılmaz. Yeni rasyonel yayların uçları tam paylaşması
sayısal yakınlıkla karıştırılmaz. SVG'deki rasyonel yay yaklaşım toleransı
`rational_arc_polyline_tolerance` alanında saklanır; asıl proje geometri
katsayılarını kayıpsız korur.


Uygulama 2.4 proje şeması 2.3'ü korur; CAD dışa aktarımı modelin analiz
ayarlarını veya geometrisini değiştirmez. CAD birim/ölçek ve nesne eşlemesi
ayrı `*.cad.json` kaydında, [CAD 1.0 şemasında](cad.schema.json) tanımlıdır.
Bu kayıt proje dosyası değildir; yanlışlıkla Proje aç ile seçilirse açıklayıcı
mesaj verilir. Pilot paketindeki `model.json` normal proje olarak yeniden açılır.

Uygulama 2.6 ana proje şemasını değiştirmez. Hazırlık ayarları ve görev
planları ayrı 1.0 sözleşmeleridir; analiz projesi veya insan çalışma kaydı
yerine açılmaz. [Alanlar, dosya sınırları ve görev kapsamı](first-cad-pilot.md).
