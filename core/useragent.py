"""Kho User Agent theo category, doc tu thu muc ``useragent/`` canh tool.

Moi file ``*.txt`` trong thu muc la MOT category (moi dong mot UA). Ten category
suy ra tu ten file bang tu khoa: ``ios``, ``android``, ``tv``, ``mac``, ``win``.
Hien tai chi co ``smart-tv-user-agents.txt`` (category "TV"); nguoi dung tha them
file khac vao la co ngay, khong phai sua code.

UA duoc ap vao Firefox qua ``autoconfig`` (pref ``general.useragent.override``);
o day chi lo phan DOC + CHON NGAU NHIEN, khong dung toi trinh duyet.
"""

from __future__ import annotations

import os
import random
from typing import Optional

from .config import TOOL_DIR

#: Thu muc chua cac file UA (canh tool). Nguoi dung tha them file .txt vao day.
UA_DIR = os.path.join(TOOL_DIR, "useragent")

#: Tu khoa trong TEN FILE -> ten category hien thi. Doi khop khong phan biet hoa/thuong.
#: Xet theo thu tu nay (dat "iphone/ipad" truoc "mac" vi iOS cung co the chua "mac").
_TU_KHOA: list[tuple[tuple[str, ...], str]] = [
    (("ios", "iphone", "ipad"), "iOS"),
    (("android",), "Android"),
    (("smart-tv", "smarttv", "tv"), "TV"),
    (("macos", "mac", "osx"), "Mac"),
    (("windows", "win"), "Win"),
    (("linux",), "Linux"),
]


def nhan_loai(ten_file: str) -> str:
    """Suy ten category tu ten file. Khong khop tu khoa nao -> lay ten file (bo duoi)."""
    goc = os.path.splitext(os.path.basename(ten_file))[0]
    thap = goc.lower()
    for tu_khoa, ten in _TU_KHOA:
        if any(tk in thap for tk in tu_khoa):
            return ten
    return goc


def cac_loai(ua_dir: Optional[str] = None) -> dict[str, str]:
    """Tra ve ``{ten_category: duong_dan_file}`` cho moi file .txt co UA.

    Nhieu file cung category thi lay file dau (theo thu tu ten). Thu muc khong
    ton tai / rong -> tra dict rong.
    """
    thu_muc = ua_dir or UA_DIR
    ket: dict[str, str] = {}
    try:
        ten_files = sorted(os.listdir(thu_muc))
    except OSError:
        return ket
    for ten in ten_files:
        if not ten.lower().endswith(".txt"):
            continue
        duong_dan = os.path.join(thu_muc, ten)
        if not os.path.isfile(duong_dan):
            continue
        loai = nhan_loai(ten)
        ket.setdefault(loai, duong_dan)
    return ket


def doc_loai(loai: str, ua_dir: Optional[str] = None) -> list[str]:
    """Doc danh sach UA cua mot category (moi dong mot UA, bo dong rong/ghi chu)."""
    duong_dan = cac_loai(ua_dir).get(loai)
    if not duong_dan:
        return []
    ds: list[str] = []
    try:
        with open(duong_dan, encoding="utf-8", errors="replace") as fh:
            for dong in fh:
                dong = dong.strip()
                if dong and not dong.startswith("#"):
                    ds.append(dong)
    except OSError:
        return []
    return ds


def chon_ngau_nhien(loai: str, ua_dir: Optional[str] = None,
                    rng: Optional[random.Random] = None) -> str:
    """Chon ngau nhien mot UA trong category. Category rong/khong co -> chuoi rong."""
    ds = doc_loai(loai, ua_dir)
    if not ds:
        return ""
    return (rng or random).choice(ds)


def chon_theo_cac_loai(danh_sach_loai, ua_dir: Optional[str] = None,
                       rng: Optional[random.Random] = None) -> str:
    """Gop nhieu category roi chon ngau nhien mot UA trong tap hop chung.

    Dung khi nguoi dung tich NHIEU category luc import: moi acc lay ngau nhien
    mot UA trong toan bo cac category da tich.
    """
    gop: list[str] = []
    for loai in (danh_sach_loai or []):
        gop.extend(doc_loai(loai, ua_dir))
    if not gop:
        return ""
    return (rng or random).choice(gop)
