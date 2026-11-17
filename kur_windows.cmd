@echo off
setlocal
cd /d "%~dp0"

rem Kurulum, bu dosyanin bulundugu proje klasorundeki sanal ortama yapilir.
where python >nul 2>&1
if errorlevel 1 (
    echo Hata: Python bulunamadi. Python 3.10 veya ustunu PATH'e ekleyin.
    goto :failure
)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo Hata: Python 3.10 veya ustu gerekiyor.
    goto :failure
)

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto :failure
)

".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto :failure
echo.
echo Kurulum tamamlandi: %CD%
echo Uygulamayi acmak icin baslat_windows.cmd dosyasini calistirin.
pause
exit /b 0

:failure
echo.
echo Kurulum tamamlanamadi. Yukaridaki hata mesajini kontrol edin.
pause
exit /b 1
