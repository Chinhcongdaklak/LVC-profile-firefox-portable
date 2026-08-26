"""Chay FirefoxPortable_*.paf.exe va tu dong bam Next cho toi khi cai xong.

Installer nay la NSIS/MUI wizard, khong ho tro /SILENT nen phai dieu khien bang
Win32 API. Bo cuc control cua wizard (da do bang EnumChildWindows):

    Top window  class '#32770'  title '... | PortableApps.com Installer'
      Button id=3     Back
      Button id=1     Next / Install / Finish
      Button id=2     Cancel
      #32770 id=0     inner page dialog
        Edit   id=1019   o trang chon thu muc cai dat
        Button id=1203   checkbox 'Run ...' o trang Finish
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from ctypes import wintypes
from typing import Callable, Optional

user32 = ctypes.windll.user32

_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
BM_CLICK = 0x00F5
BM_GETCHECK = 0x00F0
BM_SETCHECK = 0x00F1
BST_CHECKED = 1
BST_UNCHECKED = 0

ID_BACK = 3
ID_NEXT = 1
ID_CANCEL = 2
ID_DIR_EDIT = 1019
ID_FINISH_RUN_CHECKBOX = 1203

CREATE_NO_WINDOW = 0x08000000

SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
OFFSCREEN_XY = -32000


class PafInstallError(RuntimeError):
    pass


def _window_text(hwnd: int) -> str:
    length = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.SendMessageW(hwnd, WM_GETTEXT, length + 1, buf)
    return buf.value


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _pid_of(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _top_windows_of_pid(pid: int) -> list[int]:
    found: list[int] = []

    def cb(hwnd, _lparam):
        if _pid_of(hwnd) == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(_ENUM_PROC(cb), 0)
    return found


def _children(hwnd: int) -> list[int]:
    found: list[int] = []

    def cb(child, _lparam):
        found.append(child)
        return True

    user32.EnumChildWindows(hwnd, _ENUM_PROC(cb), 0)
    return found


def _inner_page(hwnd: int) -> Optional[int]:
    for child in _children(hwnd):
        if _class_name(child) == "#32770" and user32.IsWindowVisible(child):
            return child
    return None


def _find_control(parent: int, ctrl_id: int) -> Optional[int]:
    for child in _children(parent):
        if user32.GetDlgCtrlID(child) == ctrl_id and user32.IsWindowVisible(child):
            return child
    return None


def _click(hwnd: int) -> None:
    user32.SendMessageW(hwnd, BM_CLICK, 0, 0)


def _clean_label(text: str) -> str:
    return text.replace("&", "").strip().lower()


def _messagebox_text(hwnd: int) -> str:
    """Neu ``hwnd`` la mot message box (chi co nut OK), tra ve noi dung cua no."""
    next_btn = _find_control(hwnd, ID_NEXT)
    if next_btn is None or _clean_label(_window_text(next_btn)) not in ("ok", "close"):
        return ""
    for child in _children(hwnd):
        if _class_name(child) == "Static" and user32.IsWindowVisible(child):
            text = _window_text(child).strip()
            if len(text) > 3:
                return text
    return "Installer đã đóng bất thường."


def run_paf_installer(
    paf_path: str,
    destination: str,
    on_status: Optional[Callable[[str], None]] = None,
    timeout: float = 1800.0,
    hide_window: bool = True,
) -> str:
    """Giai nen paf.exe vao ``destination`` va tra ve duong dan thu muc FirefoxPortable.

    ``destination`` la thu muc CHA -- installer se tu tao thu muc con
    ``FirefoxPortable`` ben trong no.
    """
    if os.name != "nt":
        raise PafInstallError("Chi chay duoc tren Windows.")
    if not os.path.isfile(paf_path):
        raise PafInstallError(f"Khong tim thay installer: {paf_path}")

    destination = os.path.abspath(destination)
    os.makedirs(destination, exist_ok=True)

    def status(msg: str) -> None:
        if on_status:
            on_status(msg)

    status("Dang khoi dong installer...")
    proc = subprocess.Popen(
        [paf_path, f"/DESTINATION={destination}\\"],
        creationflags=CREATE_NO_WINDOW,
    )

    try:
        _drive_wizard(proc, destination, status, timeout, hide_window)
    except Exception:
        if proc.poll() is None:
            proc.kill()
        raise

    app_dir = os.path.join(destination, "FirefoxPortable")
    exe = os.path.join(app_dir, "FirefoxPortable.exe")
    if not os.path.isfile(exe):
        raise PafInstallError(
            f"Installer ket thuc nhung khong thay {exe}. Kiem tra lai duong dan."
        )
    status("Giai nen xong.")
    return app_dir


def _drive_wizard(
    proc: subprocess.Popen,
    destination: str,
    status: Callable[[str], None],
    timeout: float,
    hide_window: bool,
) -> None:
    deadline = time.time() + timeout
    dir_written = False
    last_label = ""
    installing_announced = False
    moved_offscreen = False

    while True:
        if proc.poll() is not None:
            return
        if time.time() > deadline:
            raise PafInstallError("Qua thoi gian cho installer.")

        hwnds = _top_windows_of_pid(proc.pid)
        wizard = None
        for hwnd in hwnds:
            if "PortableApps.com Installer" in _window_text(hwnd):
                wizard = hwnd
                break

        if wizard is None:
            # Chua kip hien cua so, hoac dang o hop thoai phu -> bam Yes/OK neu co.
            for hwnd in hwnds:
                btn = _find_control(hwnd, 6) or _find_control(hwnd, 1)  # IDYES / IDOK
                if btn is not None:
                    _click(btn)
            time.sleep(0.3)
            continue

        # Khong dung ShowWindow(SW_HIDE): control cua cua so an se bao
        # IsWindowVisible=False khien vong lap khong con tim thay nut nao nua.
        # Day cua so ra ngoai vung nhin thay la du de nguoi dung khong bi lam phien.
        if hide_window and not moved_offscreen:
            user32.SetWindowPos(
                wizard, 0, OFFSCREEN_XY, OFFSCREEN_XY, 0, 0,
                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
            )
            moved_offscreen = True

        page = _inner_page(wizard)
        if page is None:
            # Khong co trang con -> day la message box (vi du "installer dang chay").
            # Bam OK se lam installer thoat ma khong cai gi, nen bao loi ro rang.
            message = _messagebox_text(wizard)
            if message:
                if proc.poll() is None:
                    proc.kill()
                raise PafInstallError(f"Installer báo lỗi: {message}")

        if page is not None:
            if not dir_written:
                edit = _find_control(page, ID_DIR_EDIT)
                if edit is not None:
                    target = os.path.join(destination, "FirefoxPortable")
                    user32.SendMessageW(edit, WM_SETTEXT, 0, target)
                    dir_written = True
                    status(f"Dat thu muc cai: {target}")
            # Trang Finish co checkbox 'Run ...' -> bo tick de khong tu mo Firefox.
            run_cb = _find_control(page, ID_FINISH_RUN_CHECKBOX)
            if run_cb is not None and user32.SendMessageW(run_cb, BM_GETCHECK, 0, 0) == BST_CHECKED:
                user32.SendMessageW(run_cb, BM_SETCHECK, BST_UNCHECKED, 0)

        next_btn = _find_control(wizard, ID_NEXT)
        if next_btn is None:
            time.sleep(0.3)
            continue

        label = _clean_label(_window_text(next_btn))
        if not user32.IsWindowEnabled(next_btn):
            if not installing_announced:
                status("Dang giai nen, vui long doi...")
                installing_announced = True
            time.sleep(0.5)
            continue

        if label != last_label:
            status(f"Bam '{label or 'next'}'...")
            last_label = label

        _click(next_btn)
        time.sleep(0.45)
