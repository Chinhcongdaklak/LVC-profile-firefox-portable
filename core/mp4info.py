"""Doc THOI LUONG video mp4/mov/m4v ngay trong file (hop 'mvhd'), khong can ffmpeg. THUAN.

Dung de loc video qua dai cho X: acc X thuong chi nhan video <= 2 phut 20 giay (140s); dai
hon X bao "Some of your media failed to load" (da do that 29/09: 14.7 phut / 31MB va 30.5 phut /
121MB deu bi tu choi, 1.5 phut / 18MB len binh thuong).
"""
from __future__ import annotations

import os
import struct
from typing import Optional

_CHUA = {b"moov", b"trak", b"mdia"}     # hop chua hop con (chi can di vao moov)


def _duyet(fh, dau: int, cuoi: int):
    """Lap cac hop (kieu, vi tri noi dung, kich thuoc noi dung) trong [dau, cuoi)."""
    vt = dau
    while vt + 8 <= cuoi:
        fh.seek(vt)
        tieu_de = fh.read(8)
        if len(tieu_de) < 8:
            return
        co, kieu = struct.unpack(">I4s", tieu_de)
        dau_noi = vt + 8
        if co == 1:                              # kich thuoc 64-bit
            lon = fh.read(8)
            if len(lon) < 8:
                return
            co = struct.unpack(">Q", lon)[0]
            dau_noi = vt + 16
        elif co == 0:                            # toi het file
            co = cuoi - vt
        if co < 8:
            return
        yield kieu, dau_noi, vt + co - dau_noi
        vt += co


def thoi_luong(path: str) -> Optional[float]:
    """So GIAY cua video, None neu khong doc duoc (khong phai mp4/mov, file hong)."""
    try:
        cuoi = os.path.getsize(path)
        with open(path, "rb") as fh:
            for kieu, dau, co in _duyet(fh, 0, cuoi):
                if kieu != b"moov":
                    continue
                for k2, d2, c2 in _duyet(fh, dau, dau + co):
                    if k2 != b"mvhd":
                        continue
                    fh.seek(d2)
                    raw = fh.read(min(c2, 32))
                    phien_ban = raw[0]
                    if phien_ban == 1:
                        ts, dur = struct.unpack(">IQ", raw[20:32])
                    else:
                        ts, dur = struct.unpack(">II", raw[12:20])
                    return dur / ts if ts else None
    except (OSError, struct.error, IndexError):
        return None
    return None


def mm_ss(giay: float) -> str:
    giay = int(round(giay or 0))
    return f"{giay // 60}:{giay % 60:02d}"
