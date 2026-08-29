@echo off
REM Dong goi tool "LVC Manager Profile" thanh mot file .exe duy nhat.
REM Uu tien python trong .venv de dung dung bo thu vien da kiem thu.
REM Truyen tham so vao build.py:  build.bat --debug   (ban co console de soi loi)
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
    echo Khong thay .venv, dung python he thong.
)

echo === Cai thu vien neu chua co ===
"%PY%" -m pip install --quiet --disable-pip-version-check pyinstaller -r requirements.txt

"%PY%" build.py %*
pause
