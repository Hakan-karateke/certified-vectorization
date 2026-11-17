@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 goto :failure
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto :failure
)
".venv\Scripts\python.exe" -m pip install -e ".[cad]"
if errorlevel 1 goto :failure
echo.
echo CAD destegi kuruldu: STEP, IGES, DXF.
echo baslat_windows.cmd ile uygulamayi acin.
pause
exit /b 0
:failure
echo.
echo CAD kurulumu tamamlanamadi. Yukaridaki hatayi kontrol edin.
echo Python 3.12.8 ile dogrulanmistir; internet baglantisi gerekir.
pause
exit /b 1
