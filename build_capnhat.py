"""build_capnhat.py — dong capnhat.py thanh dist/LVCProfileUpdate.exe (giong Video Slide).

Tach khoi build.py vi hai ban .exe khac han nhau:
  · LVC Manager Profile.exe ~51 MB — keo theo customtkinter, PIL, requests...
  · LVCProfileUpdate.exe    ~10 MB — CHI thu vien chuan + tkinter.
Bo cap nhat KHONG duoc phu thuoc vao thu no di sua, va la thu nguoi dung tai khi mang yeu.

    python build_capnhat.py
"""
import os
import subprocess
import sys

GOC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, GOC)
from core.phien_ban import TEN_UPDATER  # noqa: E402  (module thuan, khong keo giao dien)

TEN = os.path.splitext(TEN_UPDATER)[0]


def main(argv=None):
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Chua co PyInstaller. Cai: pip install pyinstaller")
        return 1
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--name", TEN, "--onefile",
           "--windowed",                     # co cua so tkinter, khong console den
           "--distpath", os.path.join(GOC, "dist"),
           "--workpath", os.path.join(GOC, "build", "capnhat"),
           "--specpath", os.path.join(GOC, "build", "capnhat"),
           # Loai han thu nang ma bo cap nhat khong dung (co trong site-packages).
           "--exclude-module", "customtkinter",
           "--exclude-module", "PIL",
           "--exclude-module", "requests",
           "--exclude-module", "numpy",
           "--exclude-module", "cv2",
           "--exclude-module", "PyQt6",
           "--exclude-module", "google",
           "--exclude-module", "selenium"]
    icon = os.path.join(GOC, "assets", "logo.ico")
    if os.path.isfile(icon):
        cmd += ["--icon", icon]
    cmd.append(os.path.join(GOC, "capnhat.py"))
    print("[build] Lenh:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=GOC)
    ra = os.path.join(GOC, "dist", TEN + ".exe")
    if os.path.isfile(ra):
        print("=" * 62)
        print("[build] THANH CONG: %s (%.1f MB)" % (ra, os.path.getsize(ra) / 1048576.0))
        print("=" * 62)
        return 0
    print("[build] Build xong nhung khong thay .exe -> xem log ben tren.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
