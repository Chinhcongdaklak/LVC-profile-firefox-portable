"""MẪU TƯƠNG TÁC — preset {ten, so_phut, so_like, so_video} lưu ở data/tuong_tac_mau.json.

Có 3 mẫu mặc định (seed nếu chưa có file). Người dùng tự thêm/sửa/xoá mẫu ở tab Tương tác. Các tab
đăng bài/tạo fanpage gắn 1 mẫu -> chạy tương tác (xem reel + like) TRƯỚC khi làm việc của tab (không
dùng delay). ``chay_truoc(manager, account, mau)`` gọi core.fbwatch.tuong_tac với đúng cài đặt của mẫu.
"""

from __future__ import annotations

import json
import os
from typing import Callable, Optional

DATA = os.path.join("data", "tuong_tac_mau.json")


def mac_dinh() -> list:
    """3 mẫu mặc định theo yêu cầu người dùng."""
    return [
        {"ten": "1 phút · 1 like · 10 video", "so_phut": 1, "so_like": 1, "so_video": 10},
        {"ten": "3 phút · 3 like · 20 video", "so_phut": 3, "so_like": 3, "so_video": 20},
        {"ten": "5 phút · 5 like · 10 video", "so_phut": 5, "so_like": 5, "so_video": 10},
    ]


def _sach(m: dict) -> dict:
    """Chuẩn hoá một mẫu (đủ khoá, kiểu số)."""
    return {
        "ten": str(m.get("ten") or "mẫu"),
        "so_phut": max(1, int(m.get("so_phut") or 1)),
        "so_like": max(0, int(m.get("so_like") or 0)),
        "so_video": max(1, int(m.get("so_video") or 1)),
    }


def nap() -> list:
    """Đọc danh sách mẫu; file trống/không có -> seed 3 mẫu mặc định (và ghi lại)."""
    try:
        with open(DATA, encoding="utf-8") as fh:
            ds = json.load(fh)
        out = [_sach(m) for m in ds if isinstance(m, dict)]
        if out:
            return out
    except (OSError, ValueError):
        pass
    ds = mac_dinh()
    luu(ds)
    return ds


def luu(ds: list) -> None:
    try:
        os.makedirs(os.path.dirname(DATA), exist_ok=True)
        with open(DATA, "w", encoding="utf-8") as fh:
            json.dump([_sach(m) for m in ds], fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def tim(ten: str, ds: Optional[list] = None) -> Optional[dict]:
    """Tìm mẫu theo tên. None nếu không có."""
    for m in (ds if ds is not None else nap()):
        if str(m.get("ten")) == str(ten):
            return _sach(m)
    return None


def chay_truoc(manager, account, mau: Optional[dict], *,
               log: Optional[Callable[[str], None]] = None) -> dict:
    """Chạy TƯƠNG TÁC (xem reel + like) theo ``mau`` TRƯỚC việc chính của tab. Mẫu KHÔNG dùng delay.

    ``mau`` None/rỗng -> không làm gì, trả {}. Trả kết quả core.fbwatch.tuong_tac."""
    if not mau:
        return {}
    from core import fbwatch
    m = _sach(mau)
    noi = log or (lambda _m: None)
    noi(f"[{account.id}] tương tác trước ({m['ten']}): xem {m['so_video']} video, "
        f"like {m['so_like']}, ≤{m['so_phut']} phút...")
    return fbwatch.tuong_tac(manager, account, so_video=m["so_video"], so_phut=m["so_phut"],
                             so_like=m["so_like"], log=log)
