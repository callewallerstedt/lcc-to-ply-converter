@echo off
setlocal

REM Double-click runner for LCC to PLY
REM Put .zip files or extracted LCC folders inside .\input
REM Results are written to .\output\<input-name>\

cd /d "%~dp0"

if not exist input mkdir input
if not exist output mkdir output
if not exist tmp mkdir tmp

echo ==========================================
echo LCC to PLY - Batch Converter
echo ==========================================
echo Input folder : %cd%\input
echo Output folder: %cd%\output
echo.

python lcc_to_ply.py --input-dir input --out-dir output --lod 0 --include-environment --work-dir tmp
if errorlevel 1 (
  echo.
  echo [ERROR] Conversion failed. See message above.
  pause
  exit /b 1
)

echo.
echo [DONE] Conversion finished.
pause
