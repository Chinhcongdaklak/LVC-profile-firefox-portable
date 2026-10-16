"""Tien ich lam viec voi tien trinh Windows (khong can psutil).

Dung de biet mot profile dang mo hay khong: liet ke tien trinh va so sanh
duong dan file thuc thi voi thu muc cua acc.
"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from typing import Iterator, NamedTuple

kernel32 = ctypes.windll.kernel32

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_PATH_LONG = 32768


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class ProcessInfo(NamedTuple):
    pid: int
    name: str
    path: str


def _executable_path(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(MAX_PATH_LONG)
        buf = ctypes.create_unicode_buffer(MAX_PATH_LONG)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


#: So lan thu lai khi chup anh tien trinh that bai. CreateToolhelp32Snapshot co the
#: tra ve loi THOANG QUA (ERROR_BAD_LENGTH) khi danh sach tien trinh dang doi -- may
#: chay nhieu Firefox thi gap luon. Khong thu lai thi ham tra ve RONG, nguoi goi tuong
#: "khong con tien trinh nao" -> bao oan "trinh duyet bi dong giua chung" (loi that 05/10).
CHUP_THU_LAI = 3


def _chup_tien_trinh():
    """Anh chup danh sach tien trinh, thu lai vai lan khi Windows tu choi thoang qua."""
    for lan in range(CHUP_THU_LAI):
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot != INVALID_HANDLE_VALUE:
            return snapshot
        if lan + 1 < CHUP_THU_LAI:
            time.sleep(0.05)
    return None


def iter_processes(name_filter: str = "") -> Iterator[ProcessInfo]:
    """Duyet tien trinh dang chay. ``name_filter`` so sanh khong phan biet hoa thuong."""
    snapshot = _chup_tien_trinh()
    if snapshot is None:
        return
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return
        wanted = name_filter.lower()
        while True:
            name = entry.szExeFile
            if not wanted or name.lower() == wanted:
                yield ProcessInfo(entry.th32ProcessID, name, _executable_path(entry.th32ProcessID))
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)


#: Cache ngan han cho anh chup tien trinh: nhieu lan is_running() lien tiep (moi acc
#: mot lan, 1-4s/lan tren luong giao dien) khoi phai quet lai TOAN BO tien trinh +
#: mo handle tung firefox.exe -> tranh treo "Not Responding" khi co nhieu acc.
_snap_cache: dict = {}          # name_filter -> (thoi_diem, list[ProcessInfo])
_SNAP_TTL = 1.5


def _snapshot(name_filter: str, use_cache: bool) -> list:
    if use_cache:
        c = _snap_cache.get(name_filter)
        if c and (time.monotonic() - c[0]) < _SNAP_TTL:
            return c[1]
    procs = list(iter_processes(name_filter))
    if use_cache:
        _snap_cache[name_filter] = (time.monotonic(), procs)
    return procs


def clear_snapshot_cache() -> None:
    """Xoa cache anh chup tien trinh (goi khi vua mo/dong de trang thai tuoi ngay)."""
    _snap_cache.clear()


def find_under(directory: str, name_filter: str = "", use_cache: bool = False) -> list[ProcessInfo]:
    """Tra ve cac tien trinh co file thuc thi nam trong ``directory``.

    ``use_cache=True``: dung anh chup tien trinh gan nhat (<=1.5s) neu co -- danh cho
    is_running() goi hang loat tren luong giao dien. Terminate/lay pid thi de mac dinh
    False de luon tuoi.
    """
    root = os.path.normcase(os.path.abspath(directory)).rstrip("\\") + "\\"
    result = []
    for info in _snapshot(name_filter, use_cache):
        if info.path and os.path.normcase(info.path).startswith(root):
            result.append(info)
    return result


def terminate(pid: int) -> bool:
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        return bool(kernel32.TerminateProcess(handle, 0))
    finally:
        kernel32.CloseHandle(handle)


def terminate_under(directory: str, name_filter: str = "") -> int:
    """Dong moi tien trinh dang chay tu ``directory``. Tra ve so tien trinh da dong."""
    killed = 0
    for info in find_under(directory, name_filter):
        if terminate(info.pid):
            killed += 1
    return killed


#: So lan doc LIEN TIEP khong thay tien trinh nao thi moi ket luan "trinh duyet da dong".
#: MOT lan doc hut (anh chup loi thoang qua / OpenProcess bi tu choi khi may dang tai)
#: tung du de bao oan va huy ca luot dang bai.
BIEN_MAT_LAN = 3


class CanhTrinhDuyet:
    """Canh tien trinh Firefox cua MOT profile trong luc dang bai.

    Dung trong vong cho cua cac driver (dang bai, tuong tac): goi ``da_dong()``
    moi nhip. Chi tra True khi TRUOC DO da thay trinh duyet chay va sau do doc
    ``lan`` lan LIEN TIEP deu khong thay -- de khong huy luot dang vi mot lan quet hut.
    """

    def __init__(self, app_dir: str, lan: int = BIEN_MAT_LAN) -> None:
        self.app_dir = app_dir or ""
        self.lan = max(1, int(lan))
        self.da_thay = False
        self.vang = 0

    def da_dong(self) -> bool:
        if not self.app_dir:
            return False
        if find_under(self.app_dir, use_cache=False):
            self.da_thay = True
            self.vang = 0
            return False
        if not self.da_thay:
            return False
        self.vang += 1
        return self.vang >= self.lan
