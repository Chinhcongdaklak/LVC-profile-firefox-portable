@echo off
REM ============================================================
REM  PHAT HANH BAN MOI LVC Manager Profile — BAM DOI VAO FILE NAY.
REM  Mo cua so: chon phien ban, ghi chu, bam "Phat hanh".
REM  Can: Python + file setup\github_token.txt (xem HUONG-DAN-PHAT-HANH.md).
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"
python phat_hanh_gui.py
if errorlevel 1 pause
