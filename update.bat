@echo off
chcp 65001 >nul
REM ============================================================
REM  Lay ban moi nhat tu GitHub ve thu muc nay.
REM
REM  An toan: data\ (acc, cookie, proxy), profile\ va extension\ KHONG nam
REM  tren GitHub, nen lenh nay khong bao gio dung toi du lieu cua ban.
REM ============================================================
cd /d "%~dp0"

where git >nul 2>nul
if errorlevel 1 (
  echo Chua cai Git tren may nay.
  echo   - Tai Git: https://git-scm.com/download/win
  echo   - Hoac vao GitHub bam "Code" ^> "Download ZIP", giai nen de len thu muc nay.
  pause
  exit /b 1
)

if not exist ".git" (
  echo Thu muc nay chua noi voi GitHub. Chay mot lan lenh sau roi thoi:
  echo    git init
  echo    git remote add origin https://github.com/Chinhcongdaklak/LVC-profile-firefox-portable.git
  echo    git fetch origin ^&^& git reset --hard origin/main
  pause
  exit /b 1
)

echo === Kiem tra sua doi cua ban ===
git diff --quiet && git diff --cached --quiet
if errorlevel 1 goto co_sua_doi

REM Khong co sua doi that. Nhung Git van co the bao file "da doi" khi file chi
REM khac ky tu xuong dong (CRLF cua Windows). Kieu do lam lenh keo ve bi chan
REM giua chung -- tra ve ban goc cho sach.
git checkout -- . 2>nul
goto keo_ve

:co_sua_doi
echo.
echo Ban dang co sua doi CHUA LUU:
git status --short
echo.
echo Keo ban moi ve se de len nhung sua doi nay.
choice /c YN /m "Cat sua doi di roi lay ban moi (Y), hay dung lai (N)"
if errorlevel 2 (
  echo Da dung lai. Hay tu commit hoac sao luu truoc khi update.
  pause
  exit /b 1
)
git stash push -u -m "truoc khi update"
echo Sua doi cu da cat vao stash. Muon lay lai sau: git stash pop

:keo_ve
echo.
echo === Dang tai ban moi ===
git pull origin main
if errorlevel 1 (
  echo.
  echo Tai khong duoc. Doc loi o tren.
  pause
  exit /b 1
)

echo.
echo === Cai thu vien con thieu (neu co) ===
pip install --quiet --disable-pip-version-check -r requirements.txt

echo.
echo === Phien ban hien tai ===
git log --oneline -1
echo.
echo XONG. Mo lai tool de dung ban moi.
pause
