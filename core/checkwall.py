"""Check tường acc Facebook KHÔNG mở trình duyệt: dùng cookie riêng của từng acc gọi HTTP.

Đã probe thật (2026-09-09, xem .congcode2/NGHIEN-CUU-OUT-COOKIE.md + ADR-020): UID trần không phân
biệt được live/die; nhưng cookie RIÊNG của acc gọi ``mbasic.facebook.com/me`` thì phân biệt được —
còn phiên thì ở lại ``/me`` (Live), bị đá về ``login`` là phiên đã chết (Die), về ``/checkpoint`` là
Checkpoint. Module thuần HTTP: không import UI, ``get`` tiêm được để thước chạy không cần mạng.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from . import cookies as cookie_module

#: Trạng thái trả về (khớp cột "Trạng thái" trong bảng acc).
LIVE = "Live"
CHECKPOINT = "Checkpoint"
DIE = "Die"
COOKIE_CHET = "Cookie chết"
CHUA_RO = "Chưa rõ"

#: Endpoint nhẹ, phản hồi theo phiên: còn sống -> ở /me, chết -> đá về login, checkpoint -> /checkpoint.
ME_URL = "https://mbasic.facebook.com/me"
_UA = ("Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/124.0 Mobile Safari/537.36")


def co_c_user(cookie_text: str) -> bool:
    """Chuỗi cookie có ``c_user`` (đã đăng nhập) không. Không có -> cookie đã chết/chưa đăng nhập."""
    try:
        for c in cookie_module.parse(cookie_text or "", default_domain=".facebook.com"):
            if c.name == "c_user" and (c.value or "").strip():
                return True
    except cookie_module.CookieError:
        pass
    return False


def phan_loai(final_url: str, html: str, status_code: int) -> tuple:
    """Phân loại từ URL cuối + nội dung trang mbasic/me. Thuần, test được.

    Trả ``(trang_thai, chi_tiet)``. Ưu tiên checkpoint > login(die) > còn ở /me(live)."""
    fin = (final_url or "").lower()
    low = (html or "").lower()
    if "/checkpoint" in fin or "/checkpoint" in low[:3000]:
        return CHECKPOINT, "bị đưa tới trang xác minh (checkpoint)"
    if "login" in fin or "login.php" in fin or "/reauth" in fin or "two_step" in fin:
        return DIE, "phiên đã bị Facebook huỷ (bị đá về đăng nhập)"
    if int(status_code or 0) == 200 and ("/me" in fin or "/home" in fin or "profile.php" in fin
                                         or "đăng xuất" in low or "log out" in low or "log_out" in low):
        return LIVE, "còn phiên đăng nhập"
    if int(status_code or 0) == 200 and len(html or "") > 4000 and "login" not in low[:1500]:
        return LIVE, "còn phiên (trang cá nhân)"
    # mbasic/me trả 4xx = Facebook từ chối phiên (cookie hỏng / acc bị khoá) -> coi là Die.
    if int(status_code or 0) in (400, 401, 403):
        return DIE, f"Facebook từ chối phiên (HTTP {status_code})"
    return CHUA_RO, f"HTTP {status_code} — {fin[-50:]}"


def _get_that(url: str, cookie_text: str, proxy=None):
    """GET thật bằng requests, kèm cookie. Trả (final_url, html, status). Ném -> caller bắt."""
    import requests
    headers = {"User-Agent": _UA, "Cookie": _header(cookie_text), "Accept-Language": "vi,en;q=0.9"}
    proxies = None
    if proxy is not None and getattr(proxy, "enabled", False) and not getattr(proxy, "is_socks", False):
        auth = (f"{proxy.username}:{proxy.password}@" if getattr(proxy, "needs_auth", False) else "")
        u = f"http://{auth}{proxy.host}:{proxy.port}"
        proxies = {"http": u, "https": u}
    r = requests.get(url, headers=headers, timeout=15, allow_redirects=True, proxies=proxies)
    return r.url, r.text, r.status_code


def _header(cookie_text: str) -> str:
    """Chuỗi cookie -> 'name=value; ...' cho header (chỉ cookie facebook)."""
    parts, seen = [], set()
    try:
        for c in cookie_module.parse(cookie_text or "", default_domain=".facebook.com"):
            if c.name in seen or "facebook.com" not in (c.host or ".facebook.com"):
                continue
            seen.add(c.name)
            parts.append(f"{c.name}={c.value}")
    except cookie_module.CookieError:
        pass
    return "; ".join(parts)


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


def check_nhieu(items, *, workers: int = 5,
                on_row: Optional[Callable[[dict], None]] = None,
                get: Optional[Callable] = None) -> list:
    """Check NHIỀU acc song song. ``items`` = [(id, cookie_text) | (id, cookie_text, proxy)].

    Trả ``[{id, trang_thai, chi_tiet}]`` theo THỨ TỰ vào. ``on_row`` gọi sau mỗi acc xong (để vẽ dần).
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
        return {"id": str(acc_id), "trang_thai": tt, "chi_tiet": ct}

    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = {ex.submit(mot, it): str(it[0]) for it in items}
        for f in as_completed(futs):
            try:
                r = f.result()
            except Exception as exc:  # noqa: BLE001
                r = {"id": futs[f], "trang_thai": CHUA_RO, "chi_tiet": f"lỗi: {str(exc)[:50]}"}
            ket[r["id"]] = r
            if on_row is not None:
                on_row(r)
    return [ket.get(str(it[0]), {"id": str(it[0]), "trang_thai": CHUA_RO, "chi_tiet": ""}) for it in items]
