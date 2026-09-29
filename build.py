"""Dong goi "LVC Manager Profile" thanh file .exe bang PyInstaller.

Cach dung (chay bang python cua venv cho chac):
    .venv\\Scripts\\python.exe build.py            # ban phat hanh: 1 file, khong console
    .venv\\Scripts\\python.exe build.py --debug    # ban de soi loi: thu muc + co console
    .venv\\Scripts\\python.exe build.py --no-clean # build lai nhanh, khong xoa cache

Vi sao co --debug: ban phat hanh dung --windowed nen khong co cua so console.
Exe do ma loi luc khoi dong thi tat im, khong hien gi ca, rat kho doan. Ban
--debug giu console va tach thanh thu muc de doc traceback va kiem file thieu.

Exe xuat ra duoc dat canh thu muc tool, dung cho voi data\\, profile\\ va
extension\\ nhu khi chay tu ma nguon.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "LVC Manager Profile"
ENTRY = "main.py"
ICON = os.path.join("assets", "logo.ico")

#: Tai nguyen di kem: (duong dan nguon, thu muc dich trong goi).
#: - assets: logo cho icon cua so va header.
#: - core/assets: tz_shim.js / tz_patch.js, core/autoconfig.py doc luc gia mui gio.
DATA = [
    ("assets", "assets"),
    (os.path.join("core", "assets"), os.path.join("core", "assets")),
]

#: PyInstaller do khong ra vi chung duoc nap gian tiep.
HIDDEN = [
    "customtkinter",
    # Pillow tim lop ghep anh voi Tk qua module nay; thieu no thi logo tren
    # header va icon PNG khong nap duoc.
    "PIL._tkinter_finder",
]

# Moi MO-DUN trong core/modun/ (ADR-028): dam bao PyInstaller gom du du da import tinh
# trong tat_ca.py (belt-and-suspenders — tung loi "No module named 'core.modun.*'" tren ban .exe).
try:
    from PyInstaller.utils.hooks import collect_submodules
    HIDDEN += collect_submodules("core.modun")
except Exception:  # noqa: BLE001 - khong co PyInstaller luc import build cung khong sao
    pass

#: Thu vien can chep ca file du lieu di kem, khong chi file .py.
COLLECT_DATA = [
    "customtkinter",   # theme .json + font, thieu la giao dien vo mau
    "certifi",         # bo chung chi goc cho requests, thieu la moi HTTPS deu loi
    # Windows KHONG co san kho mui gio IANA -> zoneinfo doc tu goi tzdata. Thieu la
    # lich dang (quy doi gio page <-> gio may) nem ZoneInfoNotFoundError tren ban .exe.
    "tzdata",
]

#: Thu vien nap module dong (PyInstaller do khong het) -> gom TAT CA.
#: - websockets: giao tiep WebDriver BiDi voi Firefox (quet bai, check tuong).
#: - yt_dlp: tai video FB/YouTube/TikTok; hang tram extractor nap dong.
COLLECT_ALL = [
    "websockets",
    "yt_dlp",
]


def check_deps() -> None:
    """Bao som va ro neu thieu thu vien, thay vi de PyInstaller bao loi kho hieu."""
    missing = []
    for module, package in [("PyInstaller", "pyinstaller"), ("customtkinter", "customtkinter"),
                            ("PIL", "pillow"), ("requests", "requests"),
                            ("cryptography", "cryptography")]:
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        print("Thieu thu vien: " + ", ".join(missing))
        print(f"Cai bang:  {sys.executable} -m pip install " + " ".join(missing))
        sys.exit(1)


def build(debug: bool, clean: bool) -> str:
    for source, _ in DATA:
        if not os.path.isdir(os.path.join(ROOT, source)):
            print(f"Khong tim thay thu muc tai nguyen: {source}")
            sys.exit(1)

    name = f"{APP_NAME} (debug)" if debug else APP_NAME
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--name", name]
    cmd += ["--onedir", "--console"] if debug else ["--onefile", "--windowed"]
    if clean:
        cmd.append("--clean")
    if os.path.isfile(os.path.join(ROOT, ICON)):
        cmd += ["--icon", ICON]

    # PyInstaller tren Windows ngan cach nguon/dich bang ';'.
    separator = ";" if os.name == "nt" else ":"
    for source, target in DATA:
        cmd += ["--add-data", f"{source}{separator}{target}"]
    for module in COLLECT_DATA:
        cmd += ["--collect-data", module]
    for module in COLLECT_ALL:
        cmd += ["--collect-all", module]
    for module in HIDDEN:
        cmd += ["--hidden-import", module]
    cmd.append(ENTRY)

    print("Dang build:", " ".join(cmd), "\n")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("\nBuild that bai.")
        sys.exit(result.returncode)

    if debug:
        out = os.path.join(ROOT, "dist", name)
        print(f"\nXONG. Thu muc: {out}")
        print(f"Chay {os.path.join(out, name + '.exe')} de xem loi trong console.")
        return out

    built = os.path.join(ROOT, "dist", f"{name}.exe")
    final = os.path.join(ROOT, f"{APP_NAME}.exe")
    shutil.copy2(built, final)
    size = os.path.getsize(final) / (1024 * 1024)
    print(f"\nXONG. File: {final}  ({size:.1f} MB)")
    print("Dat exe canh data\\, profile\\ va extension\\ roi chay.")
    return final


def main() -> None:
    parser = argparse.ArgumentParser(description="Dong goi LVC Manager Profile thanh .exe")
    parser.add_argument("--debug", action="store_true",
                        help="Build ban co console + tach thu muc de soi loi khoi dong")
    parser.add_argument("--no-clean", dest="clean", action="store_false",
                        help="Khong xoa cache cua PyInstaller (build lai nhanh hon)")
    args = parser.parse_args()

    check_deps()
    build(debug=args.debug, clean=args.clean)


if __name__ == "__main__":
    main()
