"""Tien ich lam viec voi tien trinh Windows (khong can psutil).

Dung de biet mot profile dang mo hay khong: liet ke tien trinh va so sanh
duong dan file thuc thi voi thu muc cua acc.
"""

from __future__ import annotations

import ctypes
import os
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


def iter_processes(name_filter: str = "") -> Iterator[ProcessInfo]:
    """Duyet tien trinh dang chay. ``name_filter`` so sanh khong phan biet hoa thuong."""
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
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


def find_under(directory: str, name_filter: str = "") -> list[ProcessInfo]:
    """Tra ve cac tien trinh co file thuc thi nam trong ``directory``."""
    root = os.path.normcase(os.path.abspath(directory)).rstrip("\\") + "\\"
    result = []
    for info in iter_processes(name_filter):
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
