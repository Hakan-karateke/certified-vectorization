@echo off
setlocal
cd /d "%~dp0"

rem Aktivasyon gerektirmeden projeye ait Python yorumlayicisi kullanilir.
if not exist ".venv\Scripts\python.exe" (
    echo Once kur_windows.cmd dosyasini calistirin.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m sekilden_denkleme.gui
if errorlevel 1 (
    echo Uygulama acilamadi. Yukaridaki hata mesajini kontrol edin.
    pause
    exit /b 1
)
exit /b 0
