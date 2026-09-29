"""Go duong dan vao hop thoai "Open" cua Windows.

Dung cho duong dang video qua trinh duyet: trang web mo hop thoai chon file, mot
hop thoai cua HE DIEU HANH ma JavaScript khong voi toi duoc. Chi con cach dieu
khien no tu ben ngoai.

Cach lam: tim cua so lop ``#32770`` (hop thoai chuan cua Windows) thuoc dung tien
trinh minh vua mo, ghi duong dan vao o "File name" roi bam Open. Ghi thang vao o
nhap bang WM_SETTEXT chu khong gia lap go phim -- go phim thi ky tu chay lung
tung neu nguoi dung lo bam chuot sang cua so khac.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Optional

user32 = ctypes.windll.user32

WM_SETTEXT = 0x000C
BM_CLICK = 0x00F5
#: Lop cua so cua moi hop thoai chuan Windows (Open, Save As, Print...).
DIALOG_CLASS = "#32770"
#: Id cua nut Open/Save trong hop thoai chuan.
IDOK = 1

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class FileDialogError(Exception):
    """Khong dieu khien duoc hop thoai chon file."""


def _class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _pid_of(hwnd) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def visible_dialogs() -> set:
    """Cac cua so hop thoai chuan dang hien tren man hinh (moi tien trinh)."""
    found = set()

    def visit(hwnd, _param):
        if user32.IsWindowVisible(hwnd) and _class_name(hwnd) == DIALOG_CLASS:
            found.add(hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(visit), 0)
    return found


def wait_new_dialog(before: set, timeout: float = 30.0) -> Optional[int]:
    """Doi mot hop thoai MOI hien ra so voi luc chup ``before``.

    Khong loc theo tien trinh: Firefox mo hop thoai chon file o mot tien trinh
    RIENG (da do: cua so "File Upload" mang pid khac han moi tien trinh
    firefox.exe cua profile). Cung khong loc theo tieu de vi tieu de doi theo
    ngon ngu. So sanh voi anh chup truoc luc bam la cach chac an nhat.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        moi = visible_dialogs() - before
        if moi:
            # Cai moi nhat thuong la cai vua bat ra.
            return sorted(moi)[-1]
        time.sleep(0.2)
    return None


def _find_edit(hwnd) -> Optional[int]:
    """O nhap ten file. Hop thoai moi boc no trong ComboBoxEx32 nen phai lan sau."""
    ket = []

    def visit(child, _param):
        lop = _class_name(child)
        if lop == "Edit":
            ket.append(child)
        return True

    user32.EnumChildWindows(hwnd, EnumWindowsProc(visit), 0)
    return ket[0] if ket else None


def choose_file(before: set, path: str, timeout: float = 30.0) -> None:
    """Doi hop thoai chon file hien ra roi dua ``path`` vao va bam Open.

    ``before`` la ket qua ``visible_dialogs()`` chup TRUOC khi bam, de biet cua
    so nao la moi. Nem FileDialogError neu khong thay hop thoai hoac o nhap.
    """
    hwnd = wait_new_dialog(before, timeout=timeout)
    if not hwnd:
        raise FileDialogError("Không thấy hộp thoại chọn file của trình duyệt.")
    edit = _find_edit(hwnd)
    if not edit:
        raise FileDialogError("Thấy hộp thoại nhưng không tìm được ô nhập tên file.")

    user32.SendMessageW(edit, WM_SETTEXT, 0, ctypes.c_wchar_p(path))
    time.sleep(0.4)
    ok = user32.GetDlgItem(hwnd, IDOK)
    if ok:
        user32.SendMessageW(ok, BM_CLICK, 0, 0)
    else:
        # Khong thay nut thi Enter trong o nhap cung mo duoc.
        user32.SendMessageW(edit, 0x0100, 0x0D, 0)   # WM_KEYDOWN Enter
        user32.SendMessageW(edit, 0x0101, 0x0D, 0)   # WM_KEYUP Enter
    time.sleep(0.6)
