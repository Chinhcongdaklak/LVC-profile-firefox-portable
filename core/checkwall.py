"""Check tường acc Facebook KHÔNG mở trình duyệt: dùng cookie riêng của từng acc gọi HTTP.

ADR-020 (2026-09-09) chọn ``mbasic.facebook.com/me`` vì hồi đó nó còn server-render. ĐỔI 07/10/2026:
**Facebook đã bỏ mbasic** — mọi URL mbasic giờ trả về trang "Lỗi" (~7KB, HTTP 200). Trang đó không có
chữ "login" mà lại dài > 4000 ký tự, nên luật cũ xếp nó vào Live -> acc CHẾT cũng báo Live. Cùng lúc
``m./www.`` ăn HTTP 400 vì header tối thiểu kiểu mobile -> acc sống cũng báo Die. Nói gọn: hai nhánh
đều sai, kết quả cũ không dùng được.

Đường mới (đã probe thật, xem core/fbthongtin.py): ``www.facebook.com/me`` + cookie acc + **header
trình duyệt đầy đủ** -> còn phiên thì Facebook chuyển hướng về ``/people/<Tên>/pfbid...`` (đọc được
cả TÊN luôn), phiên chết thì đá về ``login``, acc bị khoá thì về ``/checkpoint``.

Module thuần HTTP: không import UI; ``get`` tiêm được để thước chạy không cần mạng.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from . import fbthongtin as _tt

#: Trạng thái trả về (khớp cột "Trạng thái" trong bảng acc).
LIVE = "Live"
CHECKPOINT = "Checkpoint"
DIE = "Die"
COOKIE_CHET = "Cookie chết"
CHUA_RO = "Chưa rõ"

#: Endpoint phản hồi theo phiên. Dùng chung một chỗ với fbthongtin để sau này đổi một lần là xong.
ME_URL = _tt.ME_URL

#: Dấu hiệu trong URL cuối: bị đá về đăng nhập / phải xác minh.
_DAU_DANG_NHAP = ("login.php", "/login/", "/login?", "facebook.com/login",
                  "two_step", "/reauth", "/recover", "/identify", "/checkpoint")

# Dùng lại nguyên của fbthongtin: cookie đã đăng nhập chưa, ghép header cookie.
co_c_user = _tt.co_c_user
_header = _tt.header_cookie


def phan_loai(final_url: str, html: str, status_code: int) -> tuple:
    """Phân loại từ URL cuối + nội dung trang ``www.facebook.com/me``. Thuần, test được.

    Trả ``(trang_thai, chi_tiet)``. Ưu tiên checkpoint > bị đá về đăng nhập > đọc được tên (Live).
    """
    fin = (final_url or "").lower()
    low = (html or "").lower()
    st = int(status_code or 0)

    if "/checkpoint" in fin:
        return CHECKPOINT, "bị đưa tới trang xác minh (checkpoint)"
    if any(d in fin for d in _DAU_DANG_NHAP):
        return DIE, "phiên đã bị Facebook huỷ (bị đá về đăng nhập)"
    # mbasic đã bị Facebook bỏ -> trang "Lỗi". Gặp là biết đang gọi sai chỗ, KHÔNG được coi là Live.
    if "mbasic.facebook.com" in fin:
        return CHUA_RO, "mbasic đã bị Facebook bỏ — không dùng để check nữa"
    if st == 200:
        ten = _tt.ten_tu_url(final_url) or _tt.ten_tu_title(html)
        if ten:
            return LIVE, f"còn phiên đăng nhập — {ten}"
        if "/people/" in fin or "profile.php" in fin:
            return LIVE, "còn phiên đăng nhập"
        # 200 nhưng không ra tên: thường là vỏ trang chưa đăng nhập.
        if "đăng nhập hoặc đăng ký" in low or "log in or sign up" in low:
            return DIE, "trang trả về màn đăng nhập"
        return CHUA_RO, "HTTP 200 nhưng không đọc được tên"
    # 4xx = Facebook từ chối phiên (cookie hỏng / acc bị khoá) -> coi là Die.
    if st in (400, 401, 403):
        return DIE, f"Facebook từ chối phiên (HTTP {status_code})"
    return CHUA_RO, f"HTTP {status_code} — {fin[-50:]}"


def _get_that(url: str, cookie_text: str, proxy=None):
    """GET thật kèm cookie + **header trình duyệt đầy đủ**. Trả ``(final_url, html, status)``.

    Thiếu các khoá ``Sec-Fetch-*`` là Facebook trả HTTP 400; mật khẩu proxy có ``#`` mà không mã hoá
    là ``requests`` ném "Failed to parse" (cả hai đều đã đo thật 07/10) -> dùng chung của fbthongtin.
    """
    return _tt._get_that(url, cookie_text, proxy)


def check_mot(cookie_text: str, *, get: Optional[Callable] = None, proxy=None) -> tuple:
    """Check MỘT acc theo cookie. Trả ``(trang_thai, chi_tiet)``. Không ném (lỗi -> Chưa rõ).

    ``get(url, cookie_text)`` (tiêm cho thước) trả ``(final_url, html, status)``; mặc định gọi HTTP thật."""
    if not co_c_user(cookie_text):
        return COOKIE_CHET, "chưa đăng nhập / cookie mất c_user"
    lay = get or (lambda url, ck: _get_that(url, ck, proxy))
    try:
        final_url, html, status = lay(ME_URL, cookie_text)
    except Exception as exc:  # noqa: BLE001
        return CHUA_RO, f"lỗi mạng: {str(exc)[:60]}"
    return phan_loai(final_url, html, status)


def ten_trong(chi_tiet: str) -> str:
    """Tên acc moi ra từ ``chi_tiet`` của dòng Live (``"còn phiên đăng nhập — Hồ Loan"``).

    Check tường đã gọi đúng trang mang tên, nên tiện thể điền luôn cột "Tên acc" — khỏi gọi lại.
    """
    s = str(chi_tiet or "")
    if "—" not in s:
        return ""
    return s.split("—", 1)[1].strip()[:120]


def check_nhieu(items, *, workers: int = 5,
                on_row: Optional[Callable[[dict], None]] = None,
                get: Optional[Callable] = None) -> list:
    """Check NHIỀU acc song song. ``items`` = [(id, cookie_text) | (id, cookie_text, proxy)].

    Trả ``[{id, trang_thai, chi_tiet, ten}]`` theo THỨ TỰ vào. ``on_row`` gọi sau mỗi acc xong (để vẽ dần).
    Không mở trình duyệt. ``workers`` được kẹp về [1, số acc]."""
    items = list(items)
    if not items:
        return []
    n = max(1, min(int(workers or 1), len(items)))
    ket = {}

    def mot(it):
        acc_id = it[0]
        cookie = it[1] if len(it) > 1 else ""
        proxy = it[2] if len(it) > 2 else None
        tt, ct = check_mot(cookie, get=get, proxy=proxy)
        return {"id": str(acc_id), "trang_thai": tt, "chi_tiet": ct,
                "ten": ten_trong(ct) if tt == LIVE else ""}

    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = {ex.submit(mot, it): str(it[0]) for it in items}
        for f in as_completed(futs):
            try:
                r = f.result()
            except Exception as exc:  # noqa: BLE001
                r = {"id": futs[f], "trang_thai": CHUA_RO, "chi_tiet": f"lỗi: {str(exc)[:50]}",
                     "ten": ""}
            ket[r["id"]] = r
            if on_row is not None:
                on_row(r)
    return [ket.get(str(it[0]), {"id": str(it[0]), "trang_thai": CHUA_RO, "chi_tiet": "", "ten": ""})
            for it in items]
