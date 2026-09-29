"""Phiên đăng nhập Facebook trong profile so với cookie đang lưu trong bảng.

Thuần (không UI, không đụng trình duyệt). Dùng để QUYẾT ĐỊNH có nạp cookie lưu vào profile hay
không: phiên đang sống trong profile là nguồn sự thật; cookie lưu chỉ là dự phòng. Ghi đè phiên
mới bằng cookie cũ là cách nhanh nhất làm acc "out" (xem .congcode2/NGHIEN-CUU-OUT-COOKIE.md).
"""

from __future__ import annotations

from typing import Iterable

from . import cookies as cookie_module

#: Trạng thái so phiên.
TRONG, KHAC_ACC, GIONG, MOI_HON = "trong", "khac_acc", "giong", "moi_hon"


def dau_hieu(cookie_text: str) -> tuple:
    """(c_user, xs) từ chuỗi cookie (``name=value; ...`` hoặc JSON). Không có -> ("", "")."""
    ra = {"c_user": "", "xs": ""}
    try:
        for c in cookie_module.parse(cookie_text or "", default_domain=".facebook.com"):
            if c.name in ra and "facebook.com" in (c.host or ".facebook.com"):
                ra[c.name] = ra[c.name] or c.value
    except cookie_module.CookieError:
        pass
    return ra["c_user"], ra["xs"]


def dau_hieu_ds(cookies: Iterable) -> tuple:
    """(c_user, xs) từ danh sách ``Cookie`` đọc ở profile (chỉ xét host facebook.com)."""
    ra = {"c_user": "", "xs": ""}
    for c in cookies or []:
        if getattr(c, "name", "") in ra and "facebook.com" in (getattr(c, "host", "") or ""):
            if getattr(c, "value", ""):
                ra[c.name] = ra[c.name] or c.value
    return ra["c_user"], ra["xs"]


def so_phien(profile_cookies: Iterable, stored_text: str) -> str:
    """So phiên trong profile với cookie lưu:

    * ``trong``    : profile không có phiên (không c_user/xs) -> nạp cookie lưu được;
    * ``khac_acc`` : profile đang là acc KHÁC -> nạp (thay);
    * ``giong``    : cùng acc, cùng xs -> không cần nạp;
    * ``moi_hon``  : cùng acc, xs KHÁC -> profile giữ phiên FB vừa xoay, MỚI hơn bản lưu -> KHÔNG được ghi đè.
    """
    p_user, p_xs = dau_hieu_ds(profile_cookies)
    s_user, s_xs = dau_hieu(stored_text)
    if not p_user or not p_xs:
        return TRONG
    if s_user and p_user != s_user:
        return KHAC_ACC
    if p_xs == s_xs:
        return GIONG
    return MOI_HON


def nen_nap(trang_thai: str) -> bool:
    """Chỉ nạp cookie lưu khi profile trống hoặc đang là acc khác."""
    return trang_thai in (TRONG, KHAC_ACC)


def nen_dang_nhap_web(ly_do: str, co_mat_khau: bool) -> bool:
    """Cookie chết -> có nên tự chuyển sang đăng nhập web (id|pass|2fa) không.

    Có mật khẩu và lý do KHÔNG phải checkpoint / khôi phục acc (những cái đó cần tay). Màn "nhớ profile",
    FB huỷ phiên, đòi 2 bước -> đăng nhập web xử lý được (agent bấm Tiếp tục / điền pass / TOTP)."""
    if not co_mat_khau:
        return False
    w = (ly_do or "").lower()
    return not any(k in w for k in ("checkpoint", "khôi phục", "recover"))


def ly_do_chet(why: str, trang_thai: str) -> str:
    """Câu báo vì sao cookie không vào được, theo ``why`` của probe + trạng thái so phiên."""
    w = (why or "").lower()
    if "checkpoint" in w:
        return ("acc bị CHECKPOINT (Facebook đòi xác minh) — cookie không dùng được; "
                "gỡ checkpoint bằng tay rồi Đăng nhập web (id|pass|2fa)")
    if "two_step" in w or "2fa" in w:
        return "Facebook đòi mã 2 bước — dùng Đăng nhập web (id|pass|2fa) để tool tự điền TOTP"
    if "recover" in w:
        return "Facebook chuyển sang trang khôi phục acc — acc bị khoá/hạn chế, cookie vô dụng"
    if trang_thai == MOI_HON:
        return ("cookie lưu CŨ hơn phiên trong profile (FB đã xoay xs) — tool đã ưu tiên phiên profile; "
                "cả hai đều chết -> Facebook đã huỷ phiên, cần Đăng nhập web")
    if trang_thai == GIONG:
        return "Facebook đã huỷ phiên này (đổi mật khẩu / đăng xuất mọi thiết bị / IP đổi) — cần Đăng nhập web"
    return "Facebook không nhận cookie này (đã bị thu hồi) — cần Đăng nhập web (id|pass|2fa)"
