"""Chỉ cho MỘT bản tool chạy trên máy (người dùng 11/10: "khoá cố định chỉ được mở 1 cửa sổ").

Mở tool lần nữa khi đã có bản đang chạy: KHÔNG mở bản thứ hai — đưa cửa sổ bản đang chạy lên
trước rồi thoát. Hai bản cùng chạy là hai vòng lặp đăng bài cùng lúc -> đăng trùng, hai bên giành
nhau đóng trình duyệt (đã xảy ra nhiều lần khi người dùng mở 2-3 bản).

Khoá = mutex có tên của Windows: hệ điều hành tự nhả khi tiến trình thoát (kể cả os._exit, crash)
nên không bao giờ kẹt khoá như file khoá. Bản đang chạy từ mã nguồn và bản .exe dùng CHUNG tên ->
cũng chỉ được một trong hai.
"""
import os
import time

TEN_KHOA = "Local\\LVC.ManagerProfile.MotBan"
TIEU_DE = "LVC Manager Profile"          # cửa sổ chính + cổng đăng nhập đều mở đầu bằng chuỗi này
LOI_DA_CO = 183                          # ERROR_ALREADY_EXISTS

_khoa = None                             # giữ handle tới khi tiến trình thoát


def _tao_khoa(ten):
    """Tạo mutex. Trả (handle, da_co_ban_khac)."""
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = ctypes.c_void_p
    h = k32.CreateMutexW(None, False, ten)
    da_co = k32.GetLastError() == LOI_DA_CO
    return h, da_co


def _dong(h):
    try:
        import ctypes
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(h))
    except Exception:
        pass


def cua_so_dang_chay(tieu_de=TIEU_DE):
    """Cửa sổ hiện của bản tool KHÁC (tiêu đề mở đầu bằng ``tieu_de``), không có thì None."""
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    pid_minh = os.getpid()
    tim = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def duyet(hwnd, _l):
        if not u32.IsWindowVisible(hwnd):
            return True
        n = u32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(hwnd, buf, n + 1)
        if not buf.value.startswith(tieu_de):
            return True
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != pid_minh:
            tim.append(hwnd)
            return False
        return True

    u32.EnumWindows(duyet, 0)
    return tim[0] if tim else None


def dua_len_truoc(hwnd):
    """Hiện lại (nếu đang thu nhỏ) và đưa cửa sổ lên trước."""
    try:
        import ctypes
        u32 = ctypes.windll.user32
        if u32.IsIconic(hwnd):
            u32.ShowWindow(hwnd, 9)          # SW_RESTORE
        u32.ShowWindow(hwnd, 5)              # SW_SHOW
        u32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def chiem(cho_giay=15.0, ten=TEN_KHOA, *, _tao=None, _tim=None, _dua=None, _ngu=time.sleep,
          _gio=time.monotonic):
    """Giành quyền làm bản DUY NHẤT. True = được chạy; False = đã có bản khác (đã đưa nó lên trước).

    Có bản khác mà THẤY cửa sổ của nó -> đưa lên trước, trả False NGAY. Không thấy cửa sổ (bản cũ
    đang thoát — vd vừa cập nhật xong mở lại) -> chờ tối đa ``cho_giay`` cho nó nhả khoá rồi chạy.
    Không phải Windows / lỗi API -> cho chạy (không bao giờ chặn tool vì lỗi của chính khoá)."""
    global _khoa
    if os.name != "nt" and _tao is None:
        return True
    tao = _tao or _tao_khoa
    tim = _tim or cua_so_dang_chay
    dua = _dua or dua_len_truoc
    het = _gio() + max(0.0, cho_giay)
    while True:
        try:
            h, da_co = tao(ten)
        except Exception:
            return True
        if not da_co:
            _khoa = h
            return True
        if _tao is None:
            _dong(h)                         # không giữ handle tới mutex của bản khác
        hwnd = None
        try:
            hwnd = tim()
        except Exception:
            pass
        if hwnd:
            dua(hwnd)
            return False
        if _gio() >= het:
            return False
        _ngu(0.5)


def bao_dang_chay():
    """Không tìm thấy cửa sổ bản đang chạy để đưa lên (đang ẩn/đang đóng) -> báo một câu."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, "LVC Manager Profile đang chạy rồi — mỗi máy chỉ mở được MỘT cửa sổ tool.\n"
                  "Nếu không thấy cửa sổ, chờ vài giây rồi mở lại.",
            "LVC Manager Profile", 0x40)
    except Exception:
        pass
