# CAD aktarım sözleşmesi — 2.4

Uygulama STEP, IGES ve DXF üretir. **CAD: STEP · IGES · DXF** düğmesi birim,
ölçek ve ayrı aktarım toleransını seçtirir. CAD desteği isteğe bağlıdır:
Windows'ta `kur_cad_windows.cmd`, teknik kurulumda `pip install -e '.[cad]'`.
Analiz ve mevcut altı çıktı için CAD bağımlılıkları gerekmez. Test edilen
çekirdek `cadquery-ocp-novtk 7.9.3.1.1` ve `ezdxf 1.4.4`'tür. VTK ve tam
CadQuery paketi kullanılmaz; yalnız gerekli CAD geometri/yazıcı işlevleri yüklenir.

## Biçimlerin anlamı

| Biçim | Oluşan geometri | Korunan bilgi |
|---|---|---|
| DXF R2013 | LINE, CIRCLE, ARC, ELLIPSE, SPLINE; izinli yaklaşımda LWPOLYLINE | Yerel nesne parametreleri, NURBS kontrol/düğüm/ağırlıkları, sınır katmanları ve gruplar, parça kimlikli XDATA |
| STEP AP214 | Z=0 düzleminde, delikleri bulunan yüzler | Sonlu CAD kenarları, kapalı dış/iç teller, yüz ve bileşen geometrisi |
| IGES | Z=0 düzleminde, delikleri bulunan kırpılmış yüzler | Konik/NURBS geometrisi ve dış/iç sınırlar; okuyucu koniği NURBS'e dönüştürebilir |

STEP'te yalnız tel aktarımı, OCCT tarafından geometrik eğri kümesine
indirgenebildiği için yüz kullanılır. Kalınlık, ekstrüzyon veya katı eklenmez.
Yüz normali +Z, dış tel saat yönünün tersinde, delikler saat yönündedir.
Kaynak modelin ilerleme yönü korunur; gerekli CAD yüz yön çevirmeleri
`entity_mapping.face_wire_reversed` alanında açıklanır.

**Parametrik DXF**, bu uygulamada düzenlenebilir geometrik parametreler ve
NURBS katsayıları demektir. AutoCAD/SolidWorks/FreeCAD'e özgü sürücü ölçüler,
teğetlik/çakışıklık kısıtları ve tasarım geçmişi oluşturulmaz. CAD okuyucusu
kendi parametre aralığına dönüştürebilir. Asıl matematiksel denklem/aralıklar
eşlik eden JSON'da saklanır; CAD programının özellik geçmişi olduğu iddia edilmez.

## Eğri aileleri

- Sonlu doğru yerel sonlu kenardır; sonsuz doğruya uzatılmaz.
- Tam çember/elips ve eski sonlu açısal yaylar yerel konik olarak verilir.
  Elipste büyük/küçük eksen sırası düzeltilirken dönme ve faz da düzeltilir.
- Yeni rasyonel çember yayı, asıl A/B/bulge katsayılarından hesaplanan CAD
  çember yayıdır. Merkez/yarıçapın binary64 dönüşüm sapması yeniden açma
  denetimine dahildir; kaynakta var olan rasyonel sertifika CAD'e etiketlenmez.
- Rasyonel elips yayı pozitif ağırlıklı derece 2 NURBS; kübik Bézier derece 3
  sıkıştırılmış NURBS olarak taşınır. Kontrol noktalarına yeniden uydurma yapılmaz.
- Tam B-spline kontrol/düğüm vektörüyle taşınır. Doğal aralığın içindeki kırpılmış
  spline, dış dalları dosyaya sokmadan tam rasyonel Bernstein alt aralıklarına
  ayrılır. Her alt parçanın özgün parametre aralığı eşleme kaydındadır.
- Fourier için doğrudan yerel CAD karşılığı yoktur. Varsayılan ret açıklayıcıdır.
  **Kontrollü doğru yaklaşımına izin ver** açıkça seçildiğinde eğri geometrik
  toleransla bölünür ve `approximated_source_pieces` alanına yazılır.

DXF spline kontrol, düğüm ve ağırlık sözleşmesi [ezdxf resmî
belgesinde](https://ezdxf.readthedocs.io/en/stable/dxfentities/spline.html)
açıklanır. IGES çevirisi [Open CASCADE
yazıcısını](https://occt3d.com/dev/doc/refman/html/class_i_g_e_s_control___writer.html)
kullanır; yerel testte kurulu 7.9.3 API'si ayrıca çalıştırılmıştır.

## Fiziksel birim ve ölçek

`mm`, `cm`, `m`, `in` seçilebilir. `scale`, bir çalışma koordinatının kaç CAD
birimi olduğudur: `X_cad=scale*X_work`, `Y_cad=scale*Y_work`, `Z_cad=0`.
Kaynak EXIF/piksel dönüşümü tekrar uygulanmaz; orijin çalışma düzlemi orijinidir.
Örneğin scale=0.1 mm/koordinat, 1000'lik tuvali 100 mm yapar. Bu **kullanıcı
eşlemesidir**; görüntüden fiziksel boyut veya kamera kalibrasyonu çıkarılmaz.

OCCT'nin dahili koordinatları mm'dir; yazıcı/okuyucu birim dönüşümleri gerçek
dosyalarda ayrıca sınanır. DXF `$INSUNITS` ve nesne koordinatları birlikte
yazılır. Kullanıcı eşiği veya görüntü ölçeği, fiziksel üretim doğruluğu kanıtı
olarak sunulmaz. Ölçek 0.001–1000 çıktı birimi/koordinat, aktarım toleransı
0.000001–10 çıktı birimi; OCCT için en az 0.000001 mm gerekir.

## İki farklı hata sözleşmesi

Kaynak modelin hata/topoloji sertifikası normalize piksel sınırına aittir.
CAD aktarım toleransı, **kaynak matematiksel model ile yeniden okunan CAD
geometrisi** arasındadır. Bunlar toplanırken birimler eşitlenir:

```text
U_tahmin,piksel→CAD = scale * U_sertifika,piksel→model + U_tahmin,model→CAD.
```

İkinci terim aşağıdaki float64 denetimidir; toplam **doğrulanmış aralık
sertifikası değildir**. Kaynak sertifika yoksa toplam alanı null'dır. Hiçbiri
ideal fiziksel nesneye uzaklık iddiası değildir. `physical_error_summary`
bu ayrımı ve birimi açıkça saklar.

## Dosya yeniden açma denetimi

Yazıcıdan sonra gerçek CAD okuyucusu çalışır: DXF için ezdxf, STEP/IGES için
OCCT. Aynı kütüphane ailesiyle yeniden açma, farklı CAD ürünlerinde doğrulama
yerine geçmez; gerçek kullanıcı protokolü ayrı tutulur.

1. Her sınır, her küçük delik ve her bileşen ayrı korunur. Kaynak/okunan eğriler
   `delta=tolerance/8` hedefiyle poligonlaştırılır. Spline'da gerçek eğriyi
   kapsayan pozitif homojen Bernstein zarfı; konikte ikinci türev sınırı kullanılır.
2. Sınırlar eksen kutularının maliyetiyle birebir eşlenir; kapanış, Z sapması,
   basitlik, sınırlar arası temas/kesişim ve iç içelik karşılaştırılır.
3. İki yönde **bütün poligon kenarları** denetlenir. Her AB için karşı tarafta
   bir sonlu CD tanığı seçilir. `dist(.,CD)` dışbükey olduğundan
   `max(dist(A,CD),dist(B,CD))` tüm AB için üst sınırdır. Tanık yetersizse
   AB ikiye bölünür; yalnız sonlu örneklerde düşük artıkla yetinilmez.
4. Eğri/poligon bütçeleri, kapanış/eklem yuvarlaması, Z farkı ve sayısal pay
   eklenir. Hedefi aşan veya kaynak sınırında belirsiz kalan aktarım reddedilir.

GEOS tanık/uzaklık hesabı ve binary64 dönüşümler kullanıldığı için
`verified_numerical_certificate=false` ve
`analytic_isotopy_proven_for_cad_file=false` kalır. `polygon_nesting_preserved`
sayısal poligon denetimidir. Kaynak modeldeki `proven` bayrağı değiştirilmez.
Eşleme belirsizliğinde farklı geçerli eşleme araştırılmadığından muhafazakâr
ret mümkündür. Bu bir bütün CAD eğrileri için cebirsel topoloji çözücüsü değildir.

İlk CAD kapsamı **basit, ayrık kapalı profiller**dir. Öz-temas, sınırlar arası
temas, eksik halka veya açık birleşim reddedilir; delik/gürültü silinmez.
Kaynak eklem açıklığı `min(1e-7*scale,tolerance/16)` sınırını aşamaz.
Kapanış etiketindeki küçük yuvarlama farkı ayrıca hata bütçesine eklenir.
En çok 20.000 model parçası, 250.000 referans köşesi; tanık denetiminde 24
bölme ve 500.000 yaprak sınırı vardır. Tolerans sessizce gevşetilmez.

## Kaydedilen dosyalar

Her `reconstruction.step`, `.iges` veya `.dxf` yanında `.cad.json` yazılır.
[CAD eşleme şeması](cad.schema.json), proje şemasından ayrıdır. İçerik:

- CAD byte SHA-256 ve yazıcı/okuyucu sürümleri.
- Özgün model türleri, katsayılar, denklemler, aralıklar, sınır/bileşen ilişkileri.
- Birim, ölçek, kaynak dönüşümü, CAD nesne/kenar eşlemesi ve yön çevirmeleri.
- Yerel CAD katsayıları ve kontrollü yaklaştırılan parçalar.
- Model bit maliyetinden ayrı CAD eğri, kontrol/poligon köşesi, okunan kenar/nesne ve dosya byte sayıları.
- Kaynak model sertifikası ile ayrı CAD aktarım denetimi ve fiziksel hata özeti.

CAD eşleme kaydı bir uygulama projesi değildir. Yeniden açmak için `model.json`
projesi kullanılır; CAD kutusundan yalnız üç CAD biçimi seçilmişse proje ayrıca
**Projeyi kaydet** ile saklanır. Hazır pilot paketinde projeler de vardır.

Geçici CAD ve JSON doğrulandıktan sonra hedefler değiştirilir. İkinci dosya
yazma hatasında ilk değişiklik geri alınır; bu durum test edilir. İki dosya
tek dosya sistemi işlemiyle atomik değildir; süreç/elektrik kesintisine karşı
iki dosyalı işlem garantisi verilmez. Çok biçimli grubun sonraki hatası daha
önce tamamlanmış diğer biçimleri geri almaz; arayüz başarı bildirmez.

## Çalıştırma

```powershell
.venv/Scripts/python.exe -m sekilden_denkleme examples/square.png --formats step iges dxf --cad-unit mm --cad-scale 0.1 --cad-tolerance 0.01 --output output/cad
.venv/Scripts/python.exe examples/validate_cad.py --embed-input
```

API: `export_file(result,path,'step',ExportOptions(cad=CadOptions(...)))` veya
`export_cad(result,path,'dxf',CadOptions(...))`. OCCT birim ayarları süreç
genelinde olduğundan uygulamadaki CAD işlemleri aynı kilit altında seri çalışır.
GUI kayıt işi arka plandadır; dosya kaydı iptal edilmez.

[Gerçek örnekler](../examples/cad_validation/index.html) ·
[Pilot ölçüm protokolü](cad-pilot.md) · [Eğitim etkinlikleri](education-cad.md).
