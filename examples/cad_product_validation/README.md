# 2.5 — ayrı CAD ürünü deneyi

`index.html` ve `results.json` 27 yeni CAD dosyasının gerçek FreeCADCmd
sonuçlarını içerir. Her şekil klasöründe gömülü kaynaklı `model.json`, her
biçimin altında CAD/`.cad.json`, deney dizininde `imported.FCStd`,
`inspection.FCStd`, istek/yanıt ve süreç günlüğü vardır.

FreeCAD 1.1.4 başsız ürün API'si çalıştırıldı. OCCT ailesi ortaktır; bağımsız
geometri algoritması, CAD GUI kullanımı veya insan kullanılabilirliği değildir.
AutoCAD/SolidWorks çalıştırılmadı; gerçek kişi sayısı 0'dır.

`legacy-2.4-iges` eski 402 gruplu dosyanın başarısız regresyon koşusudur.
Yeni IGES yüzleri ayrı köklerle yazar. Eski başarısız kayıt geçişe katılmaz;
eski dosya ve yanındaki JSON da yeniden üretme için eklenmiştir.

Kaynaklar/testler/belgeler `source-2.5.zip`, teslim denetimi `verification.json`
içindedir. `research-pilot-2.5.zip`, bu dosyaları ve araştırma/boş pilot
örneklerini birleştirir. FreeCAD programı veya Python ortamı pakete gömülmez.
Program yolları makineye özgüdür; yeniden koşuda kendi D: kurulumunuzu seçin.
