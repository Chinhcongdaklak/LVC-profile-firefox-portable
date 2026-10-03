"""GOM CỬA SỔ Firefox vào một khung — phần lõi (tính lưới THUẦN + thao tác cửa sổ Windows).

Hai chế độ (người dùng chọn ở Cài đặt):
  * ``luoi``: cửa sổ Firefox vẫn độc lập, tool chỉ DỜI/CO chúng theo lưới của khung
    (an toàn tuyệt đối — kéo ra lúc nào cũng được).
  * ``nhot``: SetParent cửa sổ Firefox thành CON của khung (một cửa sổ thật sự).
    Đã probe 2026-10-02: chạy được, nhưng NẾU tiến trình chủ chết khi đang nhốt thì cửa sổ
    Firefox bị huỷ theo mà tiến trình firefox.exe vẫn sống (ma). Vì vậy luôn phải
    ``tha()`` khi đóng/thoát, và lúc khởi động gọi ``don_tien_trinh_ma()``.

Phần THUẦN (vi_tri_luoi / trong_vung_nhin / tong_cao) không đụng Windows -> test được mọi nơi.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Iterable, Optional

CHE_DO_LUOI = "luoi"
CHE_DO_NHOT = "nhot"

#: Mặc định người dùng chốt: 2 cột, nhìn thấy 2 hàng, cuộn chuột để xem tiếp.
COT_MAC_DINH = 2
HANG_NHIN_MAC_DINH = 2


# --- phần THUẦN -------------------------------------------------------------

def vi_tri_luoi(so_o: int, cot: int, o_rong: int, o_cao: int) -> list:
    """Toạ độ từng ô trong NỘI DUNG lưới (gốc 0,0, chưa trừ cuộn). THUẦN."""
    cot = max(1, int(cot))
    return [((i % cot) * int(o_rong), (i // cot) * int(o_cao), int(o_rong), int(o_cao))
            for i in range(max(0, int(so_o)))]


def tong_cao(so_o: int, cot: int, o_cao: int) -> int:
    """Chiều cao toàn bộ lưới (để đặt tầm cuộn). THUẦN."""
    cot = max(1, int(cot))
    hang = (max(0, int(so_o)) + cot - 1) // cot
    return hang * int(o_cao)


def trong_vung_nhin(y: int, o_cao: int, cuon_y: int, vp_cao: int) -> bool:
    """Ô ở ``y`` có dính vùng nhìn (cuộn tới ``cuon_y``, cao ``vp_cao``) không. THUẦN."""
    return (y + int(o_cao)) > int(cuon_y) and int(y) < int(cuon_y) + int(vp_cao)


def bo_cuc(so_o: int, cot: int, o_rong: int, o_cao: int, cuon_y: int, vp_cao: int) -> list:
    """[{i, x, y, rong, cao, hien}] — x/y đã TRỪ cuộn (toạ độ trong khung). THUẦN.

    ``hien=False`` = ô nằm ngoài vùng nhìn -> người gọi thu nhỏ cửa sổ đó cho nhẹ máy.
    """
    ra = []
    for i, (x, y, w, h) in enumerate(vi_tri_luoi(so_o, cot, o_rong, o_cao)):
        ra.append({"i": i, "x": x, "y": y - int(cuon_y), "rong": w, "cao": h,
                   "hien": trong_vung_nhin(y, h, cuon_y, vp_cao)})
    return ra


def kich_thuoc_o(vp_rong: int, vp_cao: int, cot: int, hang_nhin: int) -> tuple:
    """Ô to bằng vùng nhìn chia cho (cột × hàng nhìn). THUẦN."""
    cot = max(1, int(cot))
    hang_nhin = max(1, int(hang_nhin))
    return (max(200, int(vp_rong) // cot), max(150, int(vp_cao) // hang_nhin))


# --- phần Windows -----------------------------------------------------------

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
GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SW_MINIMIZE = 6
SW_SHOWNOACTIVATE = 4
SW_RESTORE = 9

#: Style gốc của cửa sổ đã nhốt — để trả lại đúng khi thả ra.
_STYLE_GOC: dict = {}
_CHA_GOC: dict = {}


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


def con_song(hwnd: int) -> bool:
    return bool(_kiem_windows() and hwnd and user32.IsWindow(hwnd))


def dat_vi_tri(hwnd: int, x: int, y: int, rong: int, cao: int) -> bool:
    if not con_song(hwnd):
        return False
    return bool(user32.SetWindowPos(hwnd, 0, int(x), int(y), int(rong), int(cao),
                                    SWP_NOZORDER | SWP_NOACTIVATE))


def thu_nho(hwnd: int) -> bool:
    """Thu nhỏ cửa sổ ngoài vùng nhìn: Firefox ngừng vẽ -> nhẹ máy khi mở nhiều acc."""
    if not con_song(hwnd):
        return False
    if user32.IsIconic(hwnd):
        return True
    return bool(user32.ShowWindow(hwnd, SW_MINIMIZE))


def khoi_phuc(hwnd: int) -> bool:
    if not con_song(hwnd):
        return False
    if not user32.IsIconic(hwnd):
        return True
    return bool(user32.ShowWindow(hwnd, SW_RESTORE))


SW_HIDE = 0

#: Cửa sổ đang bị ẨN (chế độ nhốt, ô ngoài vùng nhìn). Cửa sổ ẩn KHÔNG còn nằm trong
#: EnumWindows nữa -> phải nhớ ở đây, kẻo rơi khỏi danh sách và không ai hiện lại.
_DA_AN: set = set()


def an(hwnd: int) -> bool:
    """Ẩn hẳn cửa sổ (ô ngoài vùng nhìn ở chế độ NHỐT — cửa sổ con thu nhỏ vẫn chiếm chỗ).
    Firefox bị ẩn cũng ngừng vẽ như khi thu nhỏ."""
    if not con_song(hwnd):
        return False
    _DA_AN.add(hwnd)
    return bool(user32.ShowWindow(hwnd, SW_HIDE))


def hien(hwnd: int) -> bool:
    _DA_AN.discard(hwnd)
    if not con_song(hwnd):
        return False
    return bool(user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE))


def dang_an() -> list:
    return [h for h in _DA_AN if con_song(h)]


def hien_het() -> int:
    """Hiện lại mọi cửa sổ đang bị ẩn (đóng khung / thoát tool PHẢI gọi)."""
    return sum(1 for h in list(_DA_AN) if hien(h))


def gom(hwnd: int, cha: int) -> bool:
    """Chế độ ``nhot``: biến cửa sổ Firefox thành CON của khung ``cha``."""
    if not con_song(hwnd) or not cha:
        return False
    if hwnd not in _STYLE_GOC:
        _STYLE_GOC[hwnd] = user32.GetWindowLongW(hwnd, GWL_STYLE)
        _CHA_GOC[hwnd] = user32.GetParent(hwnd)
    user32.SetParent(hwnd, cha)
    style = (_STYLE_GOC[hwnd] & ~WS_POPUP) | WS_CHILD
    user32.SetWindowLongW(hwnd, GWL_STYLE, style)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FRAMECHANGED | SWP_NOZORDER | SWP_NOACTIVATE
                        | 0x0001 | 0x0002)       # SWP_NOSIZE | SWP_NOMOVE
    return bool(user32.IsChild(cha, hwnd))


def tha(hwnd: int) -> bool:
    """Trả cửa sổ về desktop (PHẢI gọi khi đóng khung/thoát tool, kẻo cửa sổ chết theo)."""
    if hwnd not in _STYLE_GOC:
        return False
    style = _STYLE_GOC.pop(hwnd)
    _CHA_GOC.pop(hwnd, None)
    if not con_song(hwnd):
        return False
    user32.SetParent(hwnd, 0)
    user32.SetWindowLongW(hwnd, GWL_STYLE, style)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FRAMECHANGED | SWP_NOZORDER | SWP_NOACTIVATE
                        | 0x0001 | 0x0002)
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    return True


def tha_het() -> int:
    """Thả mọi cửa sổ đang nhốt VÀ hiện lại cửa sổ đang ẩn. Trả số cửa sổ đã thả."""
    n = sum(1 for h in list(_STYLE_GOC) if tha(h))
    hien_het()
    return n


def dang_nhot() -> list:
    return list(_STYLE_GOC)


def pid_co_cua_so() -> set:
    return {pid for _h, pid in cua_so_firefox()}


#: Sổ ghi pid ĐANG BỊ NHỐT — chỉ những pid này mới được coi là "ma" ở lần mở tool sau.
SO_NHOT = os.path.join("data", "gom_nhot.json")


def ghi_so_nhot(pids: Iterable[int], duong_dan: str = "") -> None:
    """Ghi pid các Firefox đang bị NHỐT. Tool chết giữa chừng thì lần sau biết đường dọn."""
    import json
    duong_dan = duong_dan or SO_NHOT
    try:
        os.makedirs(os.path.dirname(duong_dan), exist_ok=True)
        with open(duong_dan, "w", encoding="utf-8") as fh:
            json.dump({"pids": sorted({int(p) for p in pids})}, fh)
    except OSError:
        pass


def xoa_so_nhot(duong_dan: str = "") -> None:
    try:
        os.remove(duong_dan or SO_NHOT)
    except OSError:
        pass


def doc_so_nhot(duong_dan: str = "") -> list:
    import json
    try:
        with open(duong_dan or SO_NHOT, encoding="utf-8") as fh:
            return [int(p) for p in (json.load(fh).get("pids") or [])]
    except (OSError, ValueError, TypeError):
        return []


def tien_trinh_ma(pids: Iterable[int]) -> list:
    """Trong ``pids``: pid CÒN SỐNG nhưng KHÔNG còn cửa sổ nào -> cửa sổ đã chết theo khung.

    CHỈ xét pid lấy từ sổ nhốt. KHÔNG được quét chung mọi Firefox: trình duyệt vừa khởi động
    cũng chưa có cửa sổ, quét chung là giết nhầm (đã mắc đúng lỗi này khi chạy thật 02/10).
    """
    if not _kiem_windows():
        return []
    from core import procutil
    co_cua_so = pid_co_cua_so()
    dang_song = {p.pid for p in procutil.iter_processes("firefox.exe")}
    return [int(p) for p in pids if int(p) in dang_song and int(p) not in co_cua_so]


def don_tien_trinh_ma(duong_dan: str = "") -> int:
    """Dọn theo SỔ NHỐT (gọi lúc khởi động tool). Trả số tiến trình đã tắt; luôn xoá sổ."""
    from core import procutil
    pids = doc_so_nhot(duong_dan)
    if not pids:
        return 0
    n = sum(1 for pid in tien_trinh_ma(pids) if procutil.terminate(pid))
    xoa_so_nhot(duong_dan)
    return n
