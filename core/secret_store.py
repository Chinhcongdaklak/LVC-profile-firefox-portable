"""Ma hoa file bi mat bang Windows DPAPI thay vi tu quan ly key.

Vi sao DPAPI: neu tu dan key tu mot chuoi hard-code trong source thi chuoi do
nam nguyen trong file .exe va doc ra duoc bang `strings`. Ai ngoi vao may cung
dung lai duoc key do de doc mat khau dang tho. DPAPI de chinh Windows giu key,
gan theo tai khoan nguoi dung dang dang nhap, tool khong luu key o dau ca.

Chan duoc:
  - Chep file sang may khac hoac tai khoan Windows khac -> giai ma that bai.
  - Tai khoan Windows khac tren cung may doc file.
KHONG chan duoc:
  - Ma doc chay duoi chinh tai khoan do: no goi CryptUnprotectData duoc y het
    tool. Muon chan ca truong hop nay thi phai bat nhap passphrase moi lan mo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Nhan dien file do module nay ghi, de sau nay doi dinh dang con biet duong.
_MAGIC = b"LVCFFDPAPI1"

# Entropy phu: KHONG phai secret (nam trong binary, doc duoc). Tac dung duy nhat
# la blob cua tool nay khong giai ma lan voi blob DPAPI cua tool khac.
_ENTROPY = b"LVC Manager Profile / Firefox Portable / v1"

_CRYPTPROTECT_UI_FORBIDDEN = 0x01


def _dpapi():
    """(ctypes, crypt32, kernel32, DATA_BLOB) hoac None neu khong phai Windows."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        return (ctypes,
                ctypes.WinDLL("crypt32", use_last_error=True),
                ctypes.WinDLL("kernel32", use_last_error=True),
                DATA_BLOB)
    except Exception:
        return None


def available() -> bool:
    """True neu may nay dung duoc DPAPI."""
    return _dpapi() is not None


def _call(func_name: str, raw: bytes) -> bytes | None:
    api = _dpapi()
    if api is None:
        return None
    ctypes_mod, crypt32, kernel32, DATA_BLOB = api

    def blob(data: bytes):
        # Phai giu lai buffer: DATA_BLOB chi tro toi no, buffer bi thu gom rac
        # som thi con tro thanh rac.
        buf = ctypes_mod.create_string_buffer(data, len(data))
        return (DATA_BLOB(len(data),
                          ctypes_mod.cast(buf, ctypes_mod.POINTER(ctypes_mod.c_char))),
                buf)

    blob_in, _keep_in = blob(raw)
    entropy, _keep_entropy = blob(_ENTROPY)
    blob_out = DATA_BLOB()
    ok = getattr(crypt32, func_name)(
        ctypes_mod.byref(blob_in), None, ctypes_mod.byref(entropy),
        None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes_mod.byref(blob_out))
    if not ok:
        return None
    try:
        return ctypes_mod.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def protect_bytes(raw: bytes) -> bytes | None:
    """Ma hoa theo tai khoan Windows hien tai. None neu khong lam duoc."""
    return _call("CryptProtectData", raw)


def unprotect_bytes(blob: bytes) -> bytes | None:
    """Giai ma. None neu blob cua user/may khac hoac da hong."""
    return _call("CryptUnprotectData", blob)


def save_json(path, payload: Any) -> bool:
    """Ghi payload dang JSON da ma hoa DPAPI. Ghi ra file tam roi replace.

    DPAPI khong dung duoc thi KHONG ghi va tra False -- tha khong luu duoc
    "ghi nho dang nhap" con hon am tham de mat khau nam tho tren dia.
    """
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    blob = protect_bytes(raw)
    if blob is None:
        return False
    target = Path(path)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(_MAGIC + blob)
        os.replace(tmp, target)
        return True
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def load_json(path) -> Any:
    """Doc file bi mat. None neu khong co, hong, hoac cua may/tai khoan khac."""
    try:
        blob = Path(path).read_bytes()
    except OSError:
        return None
    if not blob.startswith(_MAGIC):
        return None
    raw = unprotect_bytes(blob[len(_MAGIC):])
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def delete(path) -> None:
    """Xoa file bi mat, bo qua neu khong co."""
    try:
        Path(path).unlink()
    except OSError:
        pass
