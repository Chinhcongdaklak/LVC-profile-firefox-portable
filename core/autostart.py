"""Chan va don muc "Firefox tu khoi dong cung Windows".

Firefox 154 co tinh nang tu bat chinh no khi dang nhap Windows: no ghi mot muc
vao ``HKCU\\...\\CurrentVersion\\Run`` ten ``Mozilla-Firefox-<ma>`` tro toi
firefox.exe kem tham so ``-os-autostart``, roi danh dau
``browser.startup.windowsLaunchOnLogin.alreadyApplied`` trong prefs.js.

Voi tool nay thi do la tai hoa: moi acc mot ban Firefox rieng, tao 20 profile la
co 20 muc trong Run -> bat may len la 20 cua so Firefox tu mo. Da gap tren hai
may khac nhau, vi profile nao cung tu lam viec do.

Hai viec o day:
  * ``lock_pref_lines()`` -- dong pref lai trong mozilla.cfg cho profile moi
    khong lam nua (xem core/autoconfig.py);
  * ``clean()`` -- xoa nhung muc da bi ghi tu truoc.
"""

from __future__ import annotations

import os
from typing import NamedTuple, Optional

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
#: Firefox dat ten muc theo kieu nay.
PREFIX = "Mozilla-Firefox-"
#: Tham so chi co o muc tu khoi dong, khong co o loi tat binh thuong.
FLAG = "-os-autostart"


class Entry(NamedTuple):
    name: str
    command: str
    path: str          # duong dan firefox.exe rut ra tu command
    exists: bool       # file do con tren dia khong


def _exe_from(command: str) -> str:
    """Rut duong dan exe ra khoi dong lenh (co the co dau nhay)."""
    text = (command or "").strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        return text[1:end] if end > 0 else text.strip('"')
    return text.split(FLAG)[0].strip()


def list_entries() -> list[Entry]:
    """Cac muc tu khoi dong cua Firefox trong Run cua nguoi dung hien tai."""
    try:
        import winreg
    except ImportError:
        return []                                     # khong phai Windows
    found = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            index = 0
            while True:
                try:
                    name, value, _kind = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                if not name.startswith(PREFIX):
                    continue
                command = str(value)
                path = _exe_from(command)
                found.append(Entry(name, command, path, os.path.isfile(path)))
    except OSError:
        return []
    return found


def _under(path: str, folder: str) -> bool:
    if not folder:
        return False
    try:
        root = os.path.normcase(os.path.abspath(folder)).rstrip("\\") + "\\"
        return os.path.normcase(os.path.abspath(path)).startswith(root)
    except (OSError, ValueError):
        return False


def ours(entry: Entry, profiles_root: str) -> bool:
    """Muc nay co phai do tool sinh ra khong -- chi xoa nhung cai chac chan la cua minh.

    Tinh la cua minh khi: firefox.exe nam trong thu muc profile cua tool, HOAC
    file da khong con tren dia (profile da xoa, muc bo lai thanh rac).

    KHONG dung ten "co chu FirefoxPortable" lam dieu kien: nguoi dung co the co
    ban Firefox Portable rieng cho viec khac, khong phai cua tool.
    """
    return _under(entry.path, profiles_root) or not entry.exists


def remove(names: list) -> int:
    """Xoa cac muc theo ten. Tra ve so muc da xoa."""
    try:
        import winreg
    except ImportError:
        return 0
    removed = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            for name in names:
                try:
                    winreg.DeleteValue(key, name)
                    removed += 1
                except OSError:
                    pass
    except OSError:
        return 0
    return removed


def clean(profiles_root: str) -> list[Entry]:
    """Xoa cac muc chac chan cua tool. Tra ve danh sach da xoa."""
    muc = [e for e in list_entries() if ours(e, profiles_root)]
    if muc:
        remove([e.name for e in muc])
    return muc


def others(profiles_root: str) -> list[Entry]:
    """Muc tu khoi dong cua Firefox KHONG phai cua tool -- de bao chu khong tu xoa."""
    return [e for e in list_entries() if not ours(e, profiles_root)]


def lock_pref_lines() -> str:
    """Doan pref chen vao mozilla.cfg de profile moi khong tu ghi muc Run nua."""
    return (
        "\n"
        "// Khong cho Firefox tu bat cung Windows.\n"
        "// Moi acc mot ban Firefox rieng, de mac dinh la bat may len ca chuc\n"
        "// cua so tu mo. lockPref chu khong defaultPref: khong duoc phep bat lai.\n"
        'lockPref("browser.startup.windowsLaunchOnLogin.enabled", false);\n'
        'lockPref("browser.startup.windowsLaunchOnLogin.disableLaunchOnLoginPrompt", true);\n'
        "// Coi nhu da xu ly roi, de Firefox khong chay lai buoc tu bat do.\n"
        'defaultPref("browser.startup.windowsLaunchOnLogin.alreadyApplied", true);\n'
        "// Mo len la vao trang chu, khong khoi phuc lai dam tab cua phien truoc.\n"
        'defaultPref("browser.startup.page", 1);\n'
    )


# ---------------------------------------------------------------------------
# TOOL tu mo cung Windows (khac voi phan tren la CHAN Firefox tu mo).
# Ghi 1 muc HKCU\...\Run ten TOOL_RUN_NAME tro toi exe (ban dong goi) hoac
# pythonw.exe + main.py (ban dev). Bat/tat tu cong tac goc duoi trai; mac dinh BAT.
TOOL_RUN_NAME = "LVC Manager Profile"


def lenh_khoi_dong_tool() -> str:
    """Dong lenh Windows se chay luc dang nhap de mo tool."""
    import sys
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    py = sys.executable
    # ban dev: uu tien pythonw (khong hien cua so console)
    w = os.path.join(os.path.dirname(py), "pythonw.exe")
    if os.path.isfile(w):
        py = w
    return f'"{py}" "{main_py}"'


def dang_bat_cung_windows() -> bool:
    """Tool da co muc trong Run chua?"""
    try:
        import winreg
    except ImportError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, TOOL_RUN_NAME)
            return True
    except OSError:
        return False


def bat_cung_windows(bat: bool) -> bool:
    """Bat/tat tool mo cung Windows. Tra True neu ghi/xoa duoc (hoac da dung trang thai)."""
    try:
        import winreg
    except ImportError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if bat:
                winreg.SetValueEx(key, TOOL_RUN_NAME, 0, winreg.REG_SZ, lenh_khoi_dong_tool())
            else:
                try:
                    winreg.DeleteValue(key, TOOL_RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
