# Windows kurulum ve kullanım

Yerel doğrulama ortamı: Windows 11, CPython **3.12.8**, x64. Python kurulumunda Tcl/Tk ve pip bileşenleri bulunmalıdır. İlk kurulumda paket indirme için internet gerekir. Çalışma sırasında görsel analizi ağ kullanmaz.

1. Proje klasörünü yazma izniniz olan bir yere çıkarın; örnek konum `D:\Dev\Personal\sekilden-denkleme`.
2. `kur_windows.cmd` dosyasına çift tıklayın. Betik yerel `.venv` oluşturur ve `pip install -e .` çalıştırır. Hata varsa tamamlandı demez. Yönetici olarak çalıştırmak normalde gerekmez.
3. `baslat_windows.cmd` dosyasına çift tıklayın. Ortamı elle etkinleştirmek veya terminalde komut yazmak gerekmez.
4. **Görsel aç** ile `examples\square.png` seçin. Eşik 127, boşluk 20, model **Kesin piksel sınırı**, tolerans 0 ile **Modelleri hesapla**: dört doğru parçası beklenir.
5. Çember/elips denemeleri için `examples\validation\dataset` klasörünü kullanın. Bu veri kümesi 1000×1000'dir; ideal referansla aynı koordinatlar için boşluk **0**, tolerans **3**, aile **Otomatik karma model** seçin.
6. Sonucu **Projeyi kaydet** ile JSON olarak saklayın. Kaynak görsel başka yere taşınırsa model kullanılmaya devam eder; kaynak önizlemesinde eksik girdi açıklanır. Taşınabilir kaynak da gerekiyorsa analiz öncesi **Kaynak görseli projeye göm** seçin.
7. Dışa aktarımda PDF/PNG/JPEG/SVG kutularını seçin. JPEG saydam olamaz; opak arka plan açıkça seçilir. Akademik seçeneğini kaldırmak temiz çizim üretir. Çok sayıda parça varsa PDF çok sayfalıdır.

Kar tanesi denemesi: `examples\complex_inputs\png\fa_snowflake.png`, boşluk 20, tolerans 2, otomatik veya köşe farkındalıklı aile. Deterministik aramada dengeli tercih 79 parçalık örneği üretir. İsteğe bağlı **Bütçeli simüle tavlama**, bütçe 8 ve tohum 20261015 ile başka adaylar üretir. **Sertifikalı sonuç zorunlu** doğrulanmış hata ve desteklenen analitik topoloji koşullarını ister; **Kanıt** ile **Geçti** etiketleri farklıdır. [Sertifika açıklaması](certification.md).

CPU işçisi alanı 1–8'dir; birden çok sınırın uzaklık ölçümü paralel çalışır. Daha fazla işçi her girdiyi hızlandırmaz. Sertifika ve arama sürerken pencere kullanılabilir; iptal yürüyen sertifikanın bitimini bekleyebilir.

2.2 denemeleri: `examples\validation\dataset\circle.png` veya `ellipse.png` için boşluk 0, tolerans 3, otomatik aile ve **Sertifikalı sonuç zorunlu** seçin: birer tam konik beklenir. Aynı çemberi **Kübik B-spline / Daha sade** ile deneyebilirsiniz. Geyikte `examples\complex_inputs\png\mpeg7_deer.png`, boşluk 20, tolerans 2 ve otomatik/sıkı seçim 2007 parçadır. **Temasları koruyan çokgen / Daha sade** 1560 parçalık örneği seçer. Hazır projeler `examples\certified_extensions` altındadır; yeniden uydurma gerekmez.

Teknik kurulum alternatifi, PowerShell:

```powershell
Set-Location 'D:\Dev\Personal\sekilden-denkleme'
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -m sekilden_denkleme.gui
```

`python` bulunamazsa python.org kurulumundaki PATH seçeneğini kontrol edin veya `py -3.12` ile ortamı oluşturun. Tk hatasında `python -m tkinter` küçük test penceresini açmalıdır. Sanal ortam başka bilgisayardan kopyalanmamalıdır.

Boş görsel: eşiği kontrol edin; tamamen beyaz sonuç analiz edilmez. Bozuk/animasyonlu girdi: tek kareli raster kullanın. Aşırı karmaşık girdi: kaynak limitini bildiren mesajı izleyin; uygulama kendiliğinden gürültü silmez. Çok düşük tolerans: yaklaşık adayların reddi beklenebilir; kesin sınır geçerli geri dönüştür. Eski yaklaşık JSON: referans sınır olmadığı için kaynak görseli yeniden analiz edin. Yazma izni hatası: başka çıktı klasörü seçin; başarısız dosya tamamlandı diye bildirilmez.

Bu geliştirmede Python API, CLI ve gerçek Tk olay döngüsünde Windows arayüz akışı test edildi. Kurulum betiğinin ilk kez temiz bir Windows makineye çift tıklanarak kurulması ayrıca doğrulanmadı. Kod imzalı EXE veya MSI henüz üretilmedi.


2.3 karma yay denemesi: `examples\validation\dataset\corner_curve.png`
girdisinde boşluk 0, tolerans 3, **Konik yaylı karma / Daha sade /
Sertifikalı sonuç zorunlu** seçin. Çember/elips yayları aynı parça listesinde
görünür; normalize u parametresi ve aralığı denklemde saklanır.

**Karmaşık veri · 40 × 4 tolerans taraması** düğmesiyle
`examples\complex_inputs\manifest.json` dosyasını ve ayrı bir sonuç klasörünü
seçin. Manifestteki bütün girdiler ε=1,2,3,5'te otomatik/dengeli ayarla çalışır;
varsayılan seçime ek olarak aynı adaylarda sıkı seçim raporlanır. Önceki
model korunur. İptal ederseniz aynı klasörle yeniden başlatmak tamamlanan
koşuları tekrar uydurmaz. Kod veya ortam sürümü değiştiyse yeni klasör gerekir.
Sonuçlar JSON ve tek tek `cases` kayıtlarıdır; grafik ve CSV için depo içindeki
`examples/summarize_arc_stress.py` yardımcı betiği kullanılabilir.


2.4 CAD kurulumu: `kur_cad_windows.cmd` dosyasına çift tıklayın; mevcut `.venv`
içine isteğe bağlı CAD paketlerini kurar. Sonra uygulamayı yeniden açın ve
**CAD: STEP · IGES · DXF** düğmesini kullanın. Kutuda birim, 1 çalışma
koordinatının fiziksel karşılığı ve CAD aktarım toleransı seçilir. Örneğin
0.1 mm/koordinat, 1000'lik tuvali 100 mm yapar; görselden ölçülmüş boyut değildir.

Hazır `examples\cad_validation\ring\model.json` projesini açarak üç biçimde
tek delikli profili deneyin. STEP/IGES yüz; DXF eğri grubu üretir. Geometrik
parametreler aktarılır, CAD programına özel sürücü ölçüler oluşturulmaz.
Her CAD dosyasının yanında `.cad.json` vardır; bu eşleme kaydı proje yerine
açılmaz. Kayıt işlemi arka plandadır ve bitmeden başarı bildirimi verilmez.
Yeni CAD yazıcı/okuyucu ve GUI akışı bu Windows/Python ortamında test edildi;
başka CAD ürünlerindeki kullanıcı sonucu ayrı pilotta ölçülmelidir.

2.5: **Araştırma · üç CAD pilotu** yeni çalışma alanıdır. Üç ürünün oturum
kayıtları aynı formda, program/sürüm/işletim sistemi ayrı tutularak saklanır.
FreeCAD için **CAD uyumluluğu** sekmesinde `FreeCADCmd.exe` yolunu seçin;
taşınabilir veya D: üzerindeki normal kurulum kullanılabilir. CAD dosyasının
yanında `.cad.json` eşleme kaydı bulunmalıdır. Deney çıktısı olarak JSON/HTML,
işlem günlüğü ve FreeCAD `.FCStd` belgeleri kaydedilir. Terminal gerekmez.

AutoCAD ve SolidWorks'ü kendi resmî kurulumlarıyla D: üzerinde hazırladıktan
sonra aynı dosya ve görevleri kendi arayüzlerinde deneyin; **Pilot oturumları**
sekmesinde gerçek program sürümünü yazın. Bu sürüm bu iki programı otomatik
kurmaz veya arayüzlerini otomatik yönetmez. Programın lisansı/kurulum tercihi
uygulamanın pilot kaydından ayrıdır. [Adım adım kullanım](pilot-workspace.md).

2.6: **Hazırlık ve görevler** sekmesi programları bilinen C:/D: kurulum
klasörlerinde sınırlı tarar; özel konumları Dosya seç ile gösterebilirsiniz.
Gerçek sürüm ve ilk açılış onayını kaydedin. Üç örnekli görev paketi bütün
CAD biçimlerini yeniden okuyarak doğrular; görevler ölçüm formuna aktarılır.
[Kurulumda sizin yapacağınız işler ve ilk deneme](first-cad-pilot.md).
