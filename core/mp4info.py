"""Doc THOI LUONG + MA HOA video mp4/mov/m4v ngay trong file (hop mvhd / stsd), khong can ffmpeg. THUAN.

- thoi_luong(): loc video dai hon gioi han cua X (acc thuong <= 2:20 theo quy dinh X).
- ma_hoa(): X tren trinh duyet KHONG nhan video H.265/HEVC -> "Some of your media failed to load".
  DA DO THAT 29/09 (acc bdwayne1517): 14 video 56s-1:32 ma hoa hevc + mp3/HE-AAC deu bi tu choi; moi
  video dang duoc o 7 acc khac deu h264 + aac LC. (Truoc do tuong la do DO DAI — sai: video dai
  dem thu cung la HEVC.)
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


#: Ma video (fourcc trong stsd) X tren web KHONG nhan.
MA_X_KHONG_NHAN = {"hvc1": "H.265/HEVC", "hev1": "H.265/HEVC", "av01": "AV1",
                   "vp09": "VP9", "dvh1": "Dolby Vision (HEVC)", "dvhe": "Dolby Vision (HEVC)"}


def ma_hoa(path: str) -> dict:
    """{"video": fourcc, "audio": fourcc} cua track dau moi loai (vd "avc1", "hvc1", "mp4a",
    ".mp3"). Khong doc duoc -> {}."""
    ra: dict = {}
    try:
        cuoi = os.path.getsize(path)
        with open(path, "rb") as fh:
            for kieu, dau, co in _duyet(fh, 0, cuoi):
                if kieu != b"moov":
                    continue
                for k_t, d_t, c_t in _duyet(fh, dau, dau + co):
                    if k_t != b"trak":
                        continue
                    loai, ma = _doc_trak(fh, d_t, d_t + c_t)
                    if loai and ma and loai not in ra:
                        ra[loai] = ma
    except (OSError, struct.error, IndexError):
        return {}
    return ra


def _doc_trak(fh, dau, cuoi):
    """(loai "video"/"audio", fourcc) cua mot trak: mdia/hdlr cho loai, mdia/minf/stbl/stsd cho ma."""
    loai = ma = ""
    for k, d, c in _duyet(fh, dau, cuoi):
        if k != b"mdia":
            continue
        for k2, d2, c2 in _duyet(fh, d, d + c):
            if k2 == b"hdlr":
                fh.seek(d2 + 8)
                h = fh.read(4)
                loai = {b"vide": "video", b"soun": "audio"}.get(h, "")
            elif k2 == b"minf":
                for k3, d3, c3 in _duyet(fh, d2, d2 + c2):
                    if k3 != b"stbl":
                        continue
                    for k4, d4, c4 in _duyet(fh, d3, d3 + c3):
                        if k4 == b"stsd":
                            fh.seek(d4 + 8 + 4)          # version/flags + entry_count, roi size
                            ma = fh.read(4).decode("latin-1")
    return loai, ma


def ly_do_x_khong_nhan(path: str) -> str:
    """Ly do X (web) se tu choi video nay vi MA HOA; "" = ma hoa X nhan duoc (hoac khong doc duoc)."""
    v = (ma_hoa(path) or {}).get("video", "")
    ten = MA_X_KHONG_NHAN.get(v)
    return f"video mã hoá {ten} — X không nhận, cần chuyển sang H.264" if ten else ""


def mm_ss(giay: float) -> str:
    giay = int(round(giay or 0))
    return f"{giay // 60}:{giay % 60:02d}"
