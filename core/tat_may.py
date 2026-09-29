"""Hẹn giờ TẮT MÁY (Windows ``shutdown``). Lõi thuần: tính số giây tới giờ tắt +
gọi lệnh hệ điều hành. Windows tự đếm ngược và tắt kể cả khi đã đóng tool; huỷ bằng
``shutdown /a``. Dùng ``/f`` để ÉP đóng ứng dụng đang mở -> vẫn tắt được kể cả khi có
app khác đang chạy / có thay đổi chưa lưu (theo yêu cầu người dùng: phải tắt cho bằng được).

Tách phần TÍNH (giay_sau_phut / giay_den_gio) khỏi phần GỌI (dat_lich/huy) để thước
kiểm được mà không thật sự tắt máy (tiêm ``_run``).
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from typing import Callable, Optional

from core.autoup import normalize_time

# Cho không hiện cửa sổ console đen khi gọi shutdown.exe (Windows).
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class TatMayError(ValueError):
    pass


def giay_sau_phut(phut) -> int:
    """Số giây khi hẹn 'sau N phút'. Nhỏ hơn 0 -> 0; sai kiểu -> lỗi."""
    try:
        p = int(str(phut).strip())
    except (TypeError, ValueError):
        raise TatMayError("Số phút phải là số nguyên (ví dụ: 30).") from None
    if p < 0:
        p = 0
    return p * 60


def giay_den_gio(hhmm: str, now: Optional[datetime] = None) -> int:
    """Số giây tới lần kế tiếp đạt mốc ``HH:MM`` (hôm nay nếu còn, không thì mai)."""
    now = now or datetime.now()
    try:
        canon = normalize_time(hhmm)          # "HH:MM", ném ValueError nếu sai
    except ValueError as e:
        raise TatMayError(str(e)) from None
    gio, phut = (int(x) for x in canon.split(":"))
    moc = now.replace(hour=gio, minute=phut, second=0, microsecond=0)
    if moc <= now:
        moc += timedelta(days=1)
    return int((moc - now).total_seconds())


def gio_tat(giay: int, now: Optional[datetime] = None) -> str:
    """'HH:MM' của thời điểm sẽ tắt (để hiển thị cho người dùng)."""
    now = now or datetime.now()
    return (now + timedelta(seconds=max(0, int(giay)))).strftime("%H:%M")


def dat_lich(giay: int, *, _run: Callable = subprocess.run) -> int:
    """Hẹn Windows tắt máy sau ``giay`` giây. Trả lại số giây đã đặt. Ném TatMayError nếu lệnh lỗi."""
    giay = max(0, int(giay))
    # /f = ep dong moi ung dung dang mo -> vẫn tắt được dù có app khác chạy / chưa lưu.
    r = _run(["shutdown", "/s", "/f", "/t", str(giay)],
             capture_output=True, text=True, creationflags=_NO_WINDOW)
    if getattr(r, "returncode", 0) not in (0, None):
        raise TatMayError((getattr(r, "stderr", "") or "Không đặt được lịch tắt máy.").strip())
    return giay


def huy(*, _run: Callable = subprocess.run) -> None:
    """Huỷ lịch tắt máy đang chờ (``shutdown /a``). Không lỗi nếu chưa có lịch nào."""
    _run(["shutdown", "/a"], capture_output=True, text=True, creationflags=_NO_WINDOW)
