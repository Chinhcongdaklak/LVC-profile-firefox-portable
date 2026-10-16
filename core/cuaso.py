"""Cửa sổ Firefox: xếp theo kiểu "Xếp lớp 3 cột" (Cài đặt > Kiểu cửa sổ trình duyệt).

3 cột CỐ ĐỊNH chia ngang màn hình; trình duyệt thứ 4 trở đi XẾP LỚP chồng lên trong cùng cột
(lệch dần cho thấy cái bên dưới). Cửa sổ vẫn là cửa sổ TỰ DO -> người dùng kéo đi được; tool chỉ
đặt vị trí ĐÚNG MỘT LẦN lúc cửa sổ vừa hiện (xem core/sapxep.py).

Phần THUẦN (``o_ba_cot``) không đụng Windows -> test được mọi nơi.

(Tính năng cũ "Gom trình duyệt vào một khung cửa sổ" đã BỎ theo yêu cầu người dùng 06/10/2026 —
kèm theo đó là chế độ nhốt SetParent, sổ nhốt data/gom_nhot.json và ui/khung_gom.py.)
"""
from __future__ import annotations
import ctypes
import os
from ctypes import wintypes
from typing import Iterable, Optional
#: Viền quanh màn hình + khe giữa các ô (px) -> các ô tách rời như hình vẽ.
VIEN_MAC_DINH = 16
KHE_MAC_DINH = 12
# --- KIEU CUA SO TRINH DUYET (Cai dat) -------------------------------------
#: Khong dong vao cua so Firefox (MAC DINH — tool khong sap xep gi).
KIEU_BINH_THUONG = "binh_thuong"
#: Xep cac Firefox thanh 3 COT CO DINH; browser thu 4 tro di XEP LOP chong len trong cung cot.
KIEU_BA_COT = "ba_cot"
KIEU_CUA_SO = (
    (KIEU_BINH_THUONG, "Bình thường (không sắp xếp)"),
    (KIEU_BA_COT, "Xếp lớp 3 cột"),
)
NHAN_KIEU = dict(KIEU_CUA_SO)
MA_KIEU = {v: k for k, v in KIEU_CUA_SO}
#: So cot CO DINH cua kieu "xep lop 3 cot".
COT_CO_DINH = 3
#: Moi LOP chong len lech bao nhieu px (xuong + sang phai) cho thay cua so duoi.
LECH_MAC_DINH = 28
def o_ba_cot(i: int, man_rong: int, man_cao: int, *, cot: int = COT_CO_DINH,
             vien: int = VIEN_MAC_DINH, khe: int = KHE_MAC_DINH,
             lech: int = LECH_MAC_DINH) -> tuple:
    """Vi tri (x, y, rong, cao) cho cua so thu ``i`` theo kieu "xep lop 3 cot". THUAN.

    3 cot CO DINH chia ngang man hinh. ``i`` vuot qua so cot -> sang LOP tiep theo: VAN NAM
    trong cot cu (i % cot), CUNG kich thuoc, chi lech xuong + sang phai ``lech`` px moi lop
    de thay cua so ben duoi. Do lech bi CHAN trong be ngang mot cot -> khong tran sang cot ben.
    """
    cot = max(1, int(cot))
    vien, khe, lech = int(vien), int(khe), max(0, int(lech))
    rong = max(240, (int(man_rong) - 2 * vien - (cot - 1) * khe) // cot)
    # Chua cho mot nac lech doc de lop duoi con ho ra.
    cao = max(240, int(man_cao) - 2 * vien - lech)
    col, lop = i % cot, i // cot
    dich_x = min(lop * lech, max(0, rong // 3))      # lech TRONG cot, khong lan sang cot ben
    dich_y = min(lop * lech, max(0, int(man_cao) - cao - vien))
    x = vien + col * (rong + khe) + dich_x
    y = vien + dich_y
    # Kep lai cho NAM TRON trong man hinh (lop cuoi cot phai de tran mep phai).
    x = max(0, min(x, int(man_rong) - vien - rong))
    y = max(0, min(y, int(man_cao) - vien - cao))
    return (x, y, rong, cao)
_LA_WINDOWS = os.name == "nt"
if _LA_WINDOWS:
    user32 = ctypes.windll.user32
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    user32.SetParent.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    _ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
else:  # pragma: no cover - chỉ để import được trên máy khác khi chạy test thuần
    user32 = None
    _ENUM = None
LOP_FIREFOX = "MozillaWindowClass"
SWP_NOZORDER = 0x0004       # SetWindowPos: giu thu tu chong cua so
SWP_NOACTIVATE = 0x0010     # ... va khong cuop focus
def _kiem_windows() -> bool:
    return _LA_WINDOWS and user32 is not None
def pid_cua(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value
def _lop(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value
def tieu_de(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value
def cua_so_firefox() -> list:
    """[(hwnd, pid)] của mọi cửa sổ CHÍNH Firefox đang hiện (bỏ popup/hộp thoại)."""
    if not _kiem_windows():
        return []
    ra = []

    def cb(hwnd, _l):
        try:
            if user32.IsWindowVisible(hwnd) and _lop(hwnd) == LOP_FIREFOX:
                # Cửa sổ chính không có chủ (owner); popup/hộp thoại thì có.
                if not user32.GetWindow(hwnd, 4):        # GW_OWNER
                    ra.append((hwnd, pid_cua(hwnd)))
        except Exception:  # noqa: BLE001
            pass
        return True

    user32.EnumWindows(_ENUM(cb), 0)
    return ra
def cua_so_cua_acc(manager, account) -> Optional[int]:
    """hwnd cửa sổ chính Firefox của acc (None nếu acc không mở)."""
    if not _kiem_windows():
        return None
    from core import procutil
    try:
        pids = {p.pid for p in procutil.find_under(manager.app_dir(account), "firefox.exe",
                                                   use_cache=True)}
    except Exception:  # noqa: BLE001
        return None
    for hwnd, pid in cua_so_firefox():
        if pid in pids:
            return hwnd
    return None
def kich_thuoc_man_hinh() -> tuple:
    """(rong, cao) VUNG LAM VIEC cua man hinh chinh (da tru thanh tac vu). Khong phai Windows -> (1920, 1080)."""
    if not _kiem_windows():
        return (1920, 1080)
    try:
        class _RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
        r = _RECT()
        if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):   # SPI_GETWORKAREA
            return (max(640, r.right - r.left), max(480, r.bottom - r.top))
    except Exception:  # noqa: BLE001
        pass
    try:
        return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    except Exception:  # noqa: BLE001
        return (1920, 1080)
def con_song(hwnd: int) -> bool:
    return bool(_kiem_windows() and hwnd and user32.IsWindow(hwnd))
def dat_vi_tri(hwnd: int, x: int, y: int, rong: int, cao: int) -> bool:
    if not con_song(hwnd):
        return False
    return bool(user32.SetWindowPos(hwnd, 0, int(x), int(y), int(rong), int(cao),
                                    SWP_NOZORDER | SWP_NOACTIVATE))
class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
def vi_tri(hwnd: int) -> Optional[tuple]:
    """(x, y, rong, cao) cua cua so; khong doc duoc -> None."""
    if not con_song(hwnd):
        return None
    r = _RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)
def vung_lam_viec() -> tuple:
    """(trai, tren, rong, cao) VUNG LAM VIEC man hinh chinh (tru thanh tac vu)."""
    if _kiem_windows():
        try:
            r = _RECT()
            if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):   # SPI_GETWORKAREA
                return (r.left, r.top, max(640, r.right - r.left), max(480, r.bottom - r.top))
        except Exception:  # noqa: BLE001
            pass
    rong, cao = kich_thuoc_man_hinh()
    return (0, 0, rong, cao)
def dpi_he_thong() -> int:
    """DPI he thong theo cach tool thay toa do (tool khong DPI-aware -> 96, toa do cung la
    toa do 'logic' -> 1 cm van dung 1 cm tren man hinh)."""
    if not _kiem_windows():
        return 96
    try:
        return int(user32.GetDpiForSystem()) or 96
    except Exception:  # noqa: BLE001
        return 96
def vien_phai_an(hwnd: int) -> int:
    """Be rong VIEN TRONG SUOT ben phai cua so (Win10 ~7-8px): GetWindowRect tinh ca vien nay,
    khung NHIN THAY thi khong (DWMWA_EXTENDED_FRAME_BOUNDS). Khong doc duoc -> 0."""
    if not con_song(hwnd):
        return 0
    try:
        r, f = _RECT(), _RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return 0
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(f), ctypes.sizeof(f)) != 0:
            return 0
        return max(0, min(40, r.right - f.right))
    except Exception:  # noqa: BLE001
        return 0


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint), ("flags", ctypes.c_uint), ("showCmd", ctypes.c_uint),
                ("ptMinPosition", _POINT), ("ptMaxPosition", _POINT), ("rcNormalPosition", _RECT)]


SW_SHOWNOACTIVATE = 4
SW_SHOWMINNOACTIVE = 7


def dang_thu_nho(hwnd: int) -> bool:
    return bool(con_song(hwnd) and user32.IsIconic(hwnd))


def hien_tai_cho(hwnd: int, x: int, y: int, rong: int, cao: int) -> bool:
    """Cua so dang THU NHO -> dat vi tri 'binh thuong' = (x, y, rong, cao) roi cho HIEN ra ngay
    tai do, KHONG kich hoat (khong gianh ban phim). Dung de mo trinh duyet "an" ma khong bao gio
    hien o giua man hinh (Firefox tu keo vi tri luu trong xulstore vao trong man hinh)."""
    if not con_song(hwnd):
        return False
    wp = _WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(_WINDOWPLACEMENT)
    if not user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        return False
    wp.flags = 0
    wp.showCmd = SW_SHOWNOACTIVATE
    wp.rcNormalPosition = _RECT(int(x), int(y), int(x) + int(rong), int(y) + int(cao))
    return bool(user32.SetWindowPlacement(hwnd, ctypes.byref(wp)))
