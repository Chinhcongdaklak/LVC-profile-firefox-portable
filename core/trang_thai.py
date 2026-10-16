"""TRẠNG THÁI GẦN NHẤT CỦA ACC — một nguồn duy nhất cho cột "Trạng thái".

Trước đây cột này chỉ hiện ``account.status`` (Live / Checkpoint / Die / Chưa rõ do check tường
hoặc người dùng tự chọn), còn kết quả test proxy nằm ở ``proxy_status`` và chỉ hiện khi status
trống. Những việc khác — acc bị Facebook/X giới hạn đăng bài, bị chặn vì spam, bị đăng xuất giữa
chừng, đăng nhập lại được — không để lại dấu gì trên bảng.

Mô-đun này (THUẦN, không đụng giao diện) ghi việc GẦN NHẤT vào ``account.extra["tt"]``:

    {"ma": "han_che", "chu": "X: đã hết hạn mức đăng hôm nay", "nguon": "đăng bài", "luc": "..."}

``hien(account)`` dựng chuỗi cho cột: "⏳ Live · hạn chế đăng bài — 5 phút trước".
``ghi(...)`` cũng đồng bộ ``account.status`` về một trong ``store.STATUSES`` khi suy ra được, để
ô lọc "Tất cả trạng thái" và các chỗ đọc ``status`` cũ vẫn chạy như trước.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

#: Khoá trong ``account.extra`` giữ bản ghi gần nhất.
KHOA = "tt"
DINH_DANG = "%Y-%m-%d %H:%M:%S"

# --- các mã trạng thái -------------------------------------------------------
LIVE = "live"                  # acc sống, dùng bình thường
HAN_CHE = "han_che"            # acc SỐNG nhưng nền tảng đang chặn đăng (giới hạn / spam)
CHECKPOINT = "checkpoint"      # bị checkpoint, phải xác minh tay
DANG_XUAT = "dang_xuat"        # phiên hết hạn, cần đăng nhập lại
DIE = "die"                    # acc chết / bị vô hiệu hoá
COOKIE_CHET = "cookie_chet"    # cookie lưu không dùng được nữa
LOI_PROXY = "loi_proxy"        # proxy của acc không ra được mạng
LOI_VPN = "loi_vpn"            # có NordVPN nhưng chưa nối -> không làm gì được
LOI = "loi"                    # lỗi khác, có chi tiết kèm theo

#: Nhãn hiện trên bảng. Giữ ngắn — cột "Trạng thái" hẹp.
NHAN = {
    LIVE: "✅ Live",
    HAN_CHE: "⏳ Live · hạn chế đăng bài",
    CHECKPOINT: "⛔ Checkpoint",
    DANG_XUAT: "🚪 Đã đăng xuất",
    DIE: "❌ Die",
    COOKIE_CHET: "🍪 Cookie chết",
    LOI_PROXY: "🌐 Lỗi proxy",
    LOI_VPN: "🛡 VPN chưa nối",
    LOI: "⚠ Lỗi",
}

#: Suy ra ``account.status`` (ô lọc cũ chỉ có 4 giá trị) từ mã trạng thái.
#: Mã nào không nằm đây thì GIỮ NGUYÊN status cũ — ví dụ lỗi proxy không có nghĩa acc đã chết.
STATUS_CU = {
    LIVE: "Live",
    HAN_CHE: "Live",           # vẫn là acc sống, chỉ đang bị chặn đăng
    CHECKPOINT: "Checkpoint",
    DIE: "Die",
}


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now()


def ghi(account, ma: str, chu: str = "", nguon: str = "",
        now: Optional[datetime] = None) -> dict:
    """Ghi việc GẦN NHẤT của acc. Trả bản ghi vừa ghi.

    ``ma``   một trong các hằng ở trên (mã lạ vẫn ghi, hiện ra bằng chính mã đó);
    ``chu``  chi tiết đọc được của người (câu nền tảng báo, lý do proxy chết...);
    ``nguon`` việc nào ghi: "check tường", "đăng bài", "check proxy", "đăng nhập"...
    """
    ban = {"ma": str(ma or ""), "chu": str(chu or "")[:200],
           "nguon": str(nguon or ""), "luc": _now(now).strftime(DINH_DANG)}
    try:
        account.extra[KHOA] = ban
    except Exception:  # noqa: BLE001  (acc giả trong thước có thể không có extra)
        return ban
    moi = STATUS_CU.get(ban["ma"])
    if moi:
        account.status = moi
    return ban


def doc(account) -> dict:
    """Bản ghi gần nhất, {} nếu chưa có."""
    try:
        ban = account.extra.get(KHOA)
    except Exception:  # noqa: BLE001
        return {}
    return dict(ban) if isinstance(ban, dict) else {}


def nhan(ma: str) -> str:
    return NHAN.get(ma, ma or "")


def khi_nao(luc: str, now: Optional[datetime] = None) -> str:
    """Khoảng cách thời gian cho người đọc: "vừa xong" / "5 phút trước" / "hôm qua 14:05"."""
    try:
        t = datetime.strptime(luc, DINH_DANG)
    except (ValueError, TypeError):
        return ""
    giay = (_now(now) - t).total_seconds()
    if giay < 0:
        return t.strftime("%H:%M")
    if giay < 60:
        return "vừa xong"
    if giay < 3600:
        return f"{int(giay // 60)} phút trước"
    if giay < 86400 and t.date() == _now(now).date():
        return t.strftime("%H:%M")
    if (_now(now).date() - t.date()).days == 1:
        return "hôm qua " + t.strftime("%H:%M")
    return t.strftime("%d/%m %H:%M")


def hien(account, now: Optional[datetime] = None, kem_gio: bool = True) -> str:
    """Chuỗi cho cột "Trạng thái". Rỗng nếu chưa có bản ghi nào."""
    ban = doc(account)
    if not ban.get("ma"):
        return ""
    ra = nhan(ban["ma"])
    if kem_gio:
        gio = khi_nao(ban.get("luc", ""), now)
        if gio:
            ra += f" — {gio}"
    return ra


def chi_tiet(account, now: Optional[datetime] = None) -> str:
    """Câu đầy đủ cho tooltip / bảng chi tiết: nhãn + nguồn + chữ nền tảng báo + lúc nào."""
    ban = doc(account)
    if not ban.get("ma"):
        return ""
    phan = [nhan(ban["ma"])]
    if ban.get("nguon"):
        phan.append(f"({ban['nguon']})")
    if ban.get("chu"):
        phan.append("— " + ban["chu"])
    gio = khi_nao(ban.get("luc", ""), now)
    if gio:
        phan.append(f"· {gio}")
    return " ".join(phan)
