@echo off
REM Dong goi tool "LVC Manager Profile" thanh mot file .exe duy nhat.
REM Dat exe canh: data\, profile\, va FirefoxPortable_*.paf.exe
cd /d "%~dp0"

echo === Cai thu vien neu chua co ===
pip install --quiet pyinstaller customtkinter pillow

echo === Dang build ===
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "LVC Manager Profile" ^
  --icon "assets/logo.ico" ^
  --add-data "core/assets;core/assets" ^
  --add-data "assets;assets" ^
  --collect-data customtkinter ^
  --hidden-import customtkinter ^
  main.py

echo === Chep exe ra thu muc tool ===
copy /Y "dist\LVC Manager Profile.exe" "LVC Manager Profile.exe"

echo.
echo XONG. File: LVC Manager Profile.exe
pause
