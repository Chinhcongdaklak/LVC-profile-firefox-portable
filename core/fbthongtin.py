"""Lấy TÊN và NGÀY SINH của acc Facebook để điền vào hai cột mới ở tab Quản lý acc.

Đã PROBE THẬT (2026-10-07, acc 61581139104468):

* **Tên**: ``GET https://www.facebook.com/me`` kèm cookie riêng của acc + header trình duyệt ĐẦY ĐỦ
  -> Facebook chuyển hướng tới ``/people/<Tên>/pfbid...`` và ``<title>`` chính là tên. KHÔNG cần mở
  trình duyệt. (Header tối thiểu kiểu mobile như check tường thì ăn HTTP 400 — phải đủ sec-fetch-*.)
* **Ngày sinh**: KHÔNG có trong HTML đầu của bất cứ trang nào (``mbasic`` đã bị Facebook khoá, trả
  trang "Lỗi"; ``m.``/``www.`` profile + about đều là vỏ JS, GraphQL nạp sau; token lưu trong acc đã
  chết — lỗi 190). Chỗ DUY NHẤT đọc được là ``accountscenter.facebook.com/personal_info/birthday``
  xem bằng TRÌNH DUYỆT (phiên thật): trang hiện "Ngày sinh" rồi "10 tháng 2, 1992".
  -> Ngày sinh phải mở trình duyệt, nên chạy TUẦN TỰ và chỉ cho acc còn thiếu (ngày sinh không đổi,
  lấy một lần là xong).

Phần phân tích chữ (``ten_tu_url``, ``ngay_sinh_tu_text``...) là THUẦN -> thước chạy không cần mạng;
``get`` tiêm được y như ``core.checkwall``.
"""

from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional
from urllib.parse import quote, unquote

from . import cookies as cookie_module

#: Khoá trong ``account.extra`` -- trùng tên cột nhập hàng loạt ``x:fb_name`` / ``x:dob`` có từ trước,
#: nên acc nhập sẵn tên/ngày sinh là hiện ra luôn, không phải lấy lại.
KHOA_TEN = "fb_name"
KHOA_NGAY_SINH = "dob"

#: Lấy tên: ``/me`` tự chuyển hướng về trang cá nhân, URL cuối mang tên.
ME_URL = "https://www.facebook.com/me"
#: Lấy ngày sinh: trang này mở bằng TRÌNH DUYỆT mới thấy (xem docstring đầu tệp).
NGAY_SINH_URL = "https://accountscenter.facebook.com/personal_info/birthday"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/129.0.0.0 Safari/537.36")

#: Header giả lập trình duyệt thật. Thiếu các khoá ``Sec-Fetch-*`` là Facebook trả HTTP 400 (đã đo).
HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "sec-ch-ua": '"Chromium";v="129", "Not=A?Brand";v="8"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

#: Tháng tiếng Việt ("10 tháng 2, 1992") và tiếng Anh ("February 10, 1992" / "10 Feb 1992").
#: Giao diện acc có thể là vi HOẶC en (đã gặp cả es/he) -> đọc theo cả hai, đừng chỉ chờ tiếng Việt.
_THANG_EN = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}

#: Nhãn mở đầu dòng ngày sinh trên trang Trung tâm tài khoản.
_NHAN_NGAY_SINH = ("ngày sinh", "ngay sinh", "sinh nhật", "date of birth", "birthday", "birth date")


def _bo_dau(text: str) -> str:
    """Bỏ dấu tiếng Việt + về chữ thường, để so nhãn không phụ thuộc dấu.

    NFD KHÔNG tách ``đ`` thành ``d`` (nó là chữ riêng, không phải d + dấu) nên phải đổi tay —
    thiếu bước này thì "Đăng nhập" không khớp nhãn "dang nhap" (đã sa bẫy khi viết hàm này).
    """
    tach = unicodedata.normalize("NFD", str(text or ""))
    khong_dau = "".join(c for c in tach if unicodedata.category(c) != "Mn").lower()
    return khong_dau.replace("đ", "d")


def co_c_user(cookie_text: str) -> bool:
    """Cookie có ``c_user`` (đã đăng nhập) không. Không có thì khỏi gọi mạng cho tốn."""
    try:
        for c in cookie_module.parse(cookie_text or "", default_domain=".facebook.com"):
            if c.name == "c_user" and (c.value or "").strip():
                return True
    except cookie_module.CookieError:
        pass
    return False


def header_cookie(cookie_text: str) -> str:
    """Chuỗi cookie -> ``'name=value; ...'`` cho header (chỉ cookie facebook, bỏ trùng tên)."""
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


# ---------------------------------------------------------------- tên

def ten_tu_url(final_url: str) -> str:
    """``/people/H%E1%BB%93-Loan/pfbid...`` -> ``"Hồ Loan"``. Thuần.

    Đây là nguồn CHẮC nhất: Facebook tự chuyển hướng ``/me`` về đây và tên nằm ngay trong đường dẫn.
    Dạng ``/<username>`` hoặc ``profile.php?id=`` thì không có tên -> trả rỗng (để đọc ``<title>``).
    """
    m = re.search(r"/people/([^/]+)/", str(final_url or ""))
    if not m:
        return ""
    ten = unquote(m.group(1)).replace("-", " ").replace("+", " ")
    return re.sub(r"\s+", " ", ten).strip()


def ten_tu_title(html: str) -> str:
    """Tên từ ``<title>``. Bỏ các tiêu đề KHÔNG phải tên người (trang lỗi / chưa đăng nhập)."""
    m = re.search(r"<title[^>]*>(.*?)</title>", str(html or ""), re.S | re.I)
    if not m:
        return ""
    ten = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()
    # Bỏ phần "Facebook" dính đầu/cuối tiêu đề ("Hồ Loan | Facebook", "Facebook - ...").
    ten = re.sub(r"\s*[|\-–]\s*facebook\s*$", "", ten, flags=re.I).strip()
    ten = re.sub(r"^\s*facebook\s*[|\-–]\s*", "", ten, flags=re.I).strip()
    kh = _bo_dau(ten)
    # Tiêu đề của trang KHÔNG phải trang cá nhân. So theo CỤM nằm bất cứ đâu, không so cả chuỗi:
    # trang thật trả "Facebook - Đăng nhập hoặc đăng ký" (đã đo 07/10) nên so cả chuỗi là trượt.
    xau = ("dang nhap", "dang ky", "log in", "login", "sign up", "error", "loi",
           "security check", "kiem tra bao mat", "page not found", "khong tim thay")
    if not ten or kh == "facebook" or any(x in kh for x in xau):
        return ""
    return ten[:120]


def lay_ten(cookie_text: str, *, get: Optional[Callable] = None, proxy=None) -> tuple:
    """Lấy TÊN một acc bằng cookie (KHÔNG mở trình duyệt). Trả ``(ten, loi)``; không ném.

    ``get(url, cookie_text)`` tiêm cho thước, trả ``(final_url, html, status)``.
    """
    if not co_c_user(cookie_text):
        return "", "cookie chưa đăng nhập (thiếu c_user)"
    lay = get or (lambda url, ck: _get_that(url, ck, proxy))
    try:
        final_url, html, status = lay(ME_URL, cookie_text)
    except Exception as exc:  # noqa: BLE001
        return "", f"lỗi mạng: {str(exc)[:60]}"
    if int(status or 0) != 200:
        return "", f"Facebook từ chối phiên (HTTP {status})"
    ten = ten_tu_url(final_url) or ten_tu_title(html)
    if not ten:
        return "", "không đọc được tên (phiên có thể đã chết)"
    return ten, ""


def _proxies(proxy) -> Optional[dict]:
    """Proxy -> tham số ``proxies`` của ``requests``. Thuần (trừ việc đọc thuộc tính proxy).

    PHẢI mã hoá tên/mật khẩu: mật khẩu thật của người dùng có ``#`` nên ghép thẳng vào URL là
    ``requests`` ném "Failed to parse" và acc nào có proxy cũng trượt (đã đo thật 07/10).
    """
    if proxy is None or not getattr(proxy, "enabled", False):
        return None
    if getattr(proxy, "is_socks", False):
        return None
    auth = ""
    if getattr(proxy, "needs_auth", False):
        auth = (f"{quote(str(proxy.username or ''), safe='')}:"
                f"{quote(str(proxy.password or ''), safe='')}@")
    u = f"http://{auth}{proxy.host}:{proxy.port}"
    return {"http": u, "https": u}


def _get_that(url: str, cookie_text: str, proxy=None):
    """GET thật bằng ``requests``, kèm cookie + header trình duyệt. Trả ``(final_url, html, status)``."""
    import requests
    headers = dict(HEADERS)
    headers["Cookie"] = header_cookie(cookie_text)
    proxies = _proxies(proxy)
    r = requests.get(url, headers=headers, timeout=20, allow_redirects=True, proxies=proxies)
    return r.url, r.text, r.status_code


def lay_ten_nhieu(items, *, workers: int = 5,
                  on_row: Optional[Callable[[dict], None]] = None,
                  get: Optional[Callable] = None) -> list:
    """Lấy tên NHIỀU acc song song. ``items`` = ``[(id, cookie) | (id, cookie, proxy)]``.

    Trả ``[{id, ten, loi}]`` theo thứ tự vào; ``on_row`` gọi sau mỗi acc để vẽ dần.
    """
    items = list(items)
    if not items:
        return []
    n = max(1, min(int(workers or 1), len(items)))
    ket = {}

    def mot(it):
        acc_id = str(it[0])
        cookie = it[1] if len(it) > 1 else ""
        proxy = it[2] if len(it) > 2 else None
        ten, loi = lay_ten(cookie, get=get, proxy=proxy)
        return {"id": acc_id, "ten": ten, "loi": loi}

    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = {ex.submit(mot, it): str(it[0]) for it in items}
        for f in as_completed(futs):
            try:
                r = f.result()
            except Exception as exc:  # noqa: BLE001
                r = {"id": futs[f], "ten": "", "loi": f"lỗi: {str(exc)[:50]}"}
            ket[r["id"]] = r
            if on_row is not None:
                on_row(r)
    return [ket.get(str(it[0]), {"id": str(it[0]), "ten": "", "loi": ""}) for it in items]


# ---------------------------------------------------------------- ngày sinh

def chuan_ngay(ngay: int, thang: int, nam: int) -> str:
    """``(10, 2, 1992)`` -> ``"10/02/1992"``. Rỗng nếu số vô lý (chống nhận nhầm số khác trên trang)."""
    if not (1 <= int(ngay) <= 31 and 1 <= int(thang) <= 12 and 1900 <= int(nam) <= 2100):
        return ""
    return f"{int(ngay):02d}/{int(thang):02d}/{int(nam)}"


def doc_mot_ngay(dong: str) -> str:
    """Một dòng chữ -> ``dd/mm/yyyy`` (rỗng nếu dòng không phải ngày sinh). Thuần.

    Nhận: ``10 tháng 2, 1992`` (vi) · ``February 10, 1992`` / ``10 February 1992`` / ``Feb 10 1992``
    (en) · ``10/02/1992`` · ``1992-02-10``.
    """
    s = re.sub(r"\s+", " ", str(dong or "")).strip()
    if not s:
        return ""
    # vi: "10 tháng 2, 1992"
    m = re.search(r"\b(\d{1,2})\s*th[áa]ng\s*(\d{1,2})\s*,?\s*(\d{4})\b", s, re.I)
    if m:
        return chuan_ngay(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # en: "February 10, 1992" / "Feb 10 1992"
    m = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*,?\s*(\d{4})\b", s)
    if m and m.group(1).lower() in _THANG_EN:
        return chuan_ngay(int(m.group(2)), _THANG_EN[m.group(1).lower()], int(m.group(3)))
    # en: "10 February 1992"
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?\s*,?\s*(\d{4})\b", s)
    if m and m.group(2).lower() in _THANG_EN:
        return chuan_ngay(int(m.group(1)), _THANG_EN[m.group(2).lower()], int(m.group(3)))
    # yyyy-mm-dd
    m = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", s)
    if m:
        return chuan_ngay(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    # dd/mm/yyyy
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", s)
    if m:
        return chuan_ngay(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return ""


def ngay_sinh_tu_text(text: str) -> str:
    """Đọc NGÀY SINH từ innerText trang Trung tâm tài khoản. Thuần.

    Trang thật (đã đo) xếp: dòng nhãn ``Ngày sinh`` rồi DÒNG SAU là ``10 tháng 2, 1992``. Nên tìm
    nhãn trước rồi mới soi mấy dòng kế — KHÔNG quét ngày bừa trên cả trang (trang còn nhiều số khác).
    """
    dong = [d.strip() for d in str(text or "").splitlines()]
    for i, d in enumerate(dong):
        kh = _bo_dau(d)
        if not any(_bo_dau(n) in kh for n in _NHAN_NGAY_SINH):
            continue
        # Ngày có thể nằm ngay trên cùng dòng nhãn, hoặc ở 3 dòng kế tiếp.
        for ke in [d] + dong[i + 1:i + 4]:
            ns = doc_mot_ngay(ke)
            if ns:
                return ns
    return ""


def ten_tu_text(text: str) -> str:
    """Tên từ innerText trang Trung tâm tài khoản: dòng ngay SAU nhãn "Trang cá nhân"/"Profile"."""
    dong = [d.strip() for d in str(text or "").splitlines()]
    for i, d in enumerate(dong):
        if _bo_dau(d) in ("trang ca nhan", "profile"):
            for ke in dong[i + 1:i + 3]:
                kh = _bo_dau(ke)
                if ke and kh not in ("facebook", "instagram", "meta") and not doc_mot_ngay(ke):
                    return ke[:120]
    return ""


def lay_bang_trinh_duyet(manager, account, *, timeout: int = 120,
                         log: Optional[Callable[[str], None]] = None) -> dict:
    """Mở TRÌNH DUYỆT của acc vào trang Trung tâm tài khoản rồi đọc tên + ngày sinh.

    Dùng action chỉ-đọc ``readmain`` của ``fbupload_agent`` (không bấm gì, không đăng gì).
    Trả ``{"ten", "ngay_sinh", "loi"}``. LUÔN đóng trình duyệt, kể cả khi lỗi lập trình —
    bài học 06/10: bỏ rơi Firefox thì agent trong đó vẫn chạy tiếp.
    """
    import json
    import os
    import time

    from . import fbbusiness

    noi = log or (lambda _m: None)
    profile = manager.profile_dir(account)
    manager.close(account, wait=8.0)
    fbbusiness.clear(profile)
    fbbusiness.put_command(profile, action="readmain", dumpDelay=15000, limit=6000)
    noi(f"{account.id}: mở Trung tâm tài khoản để đọc ngày sinh…")
    manager.launch(account, url=NGAY_SINH_URL)
    # TRINH DUYET DA MO -- tu day moi thu phai nam trong try/finally.
    try:
        ket = fbbusiness.wait_state(profile, {"main-text", "logged-out", "checkpoint"},
                                    timeout=timeout,
                                    app_dir=fbbusiness.app_dir_cua(manager, account))
        time.sleep(1)
        if not ket:
            try:
                ket = json.loads(open(os.path.join(profile, "qlfp-upload-result.json"),
                                      encoding="utf-8").read())
            except (OSError, ValueError):
                ket = {}
    except Exception as exc:  # noqa: BLE001
        ket = {"state": "loi", "detail": str(exc)[:200]}
    finally:
        manager.close(account, wait=15.0)

    state = str((ket or {}).get("state") or "")
    chu = str((ket or {}).get("detail") or "")
    if state == "logged-out":
        return {"ten": "", "ngay_sinh": "", "loi": "acc đã đăng xuất"}
    if state == "checkpoint":
        return {"ten": "", "ngay_sinh": "", "loi": "acc bị checkpoint"}
    if state != "main-text":
        return {"ten": "", "ngay_sinh": "", "loi": f"không đọc được trang ({state or 'hết giờ'})"}
    ns = ngay_sinh_tu_text(chu)
    return {"ten": ten_tu_text(chu), "ngay_sinh": ns,
            "loi": "" if ns else "trang không hiện ngày sinh"}


# ---------------------------------------------------------------- ghi vào acc

def ten_cua(account) -> str:
    """Tên đã lưu của acc (rỗng = chưa lấy)."""
    return str((getattr(account, "extra", None) or {}).get(KHOA_TEN) or "").strip()


def ngay_sinh_cua(account) -> str:
    """Ngày sinh đã lưu của acc (rỗng = chưa lấy)."""
    return str((getattr(account, "extra", None) or {}).get(KHOA_NGAY_SINH) or "").strip()


def dat_ten(account, ten: str) -> bool:
    """Ghi tên vào ``extra``. Trả True nếu có thay đổi (để biết còn phải lưu store hay không)."""
    ten = re.sub(r"\s+", " ", str(ten or "")).strip()[:120]
    if not ten or ten_cua(account) == ten:
        return False
    if not isinstance(getattr(account, "extra", None), dict):
        account.extra = {}
    account.extra[KHOA_TEN] = ten
    return True


def dat_ngay_sinh(account, ngay_sinh: str) -> bool:
    """Ghi ngày sinh vào ``extra`` (chỉ nhận ``dd/mm/yyyy`` hợp lệ). Trả True nếu có thay đổi."""
    ns = doc_mot_ngay(ngay_sinh) or ""
    if not ns or ngay_sinh_cua(account) == ns:
        return False
    if not isinstance(getattr(account, "extra", None), dict):
        account.extra = {}
    account.extra[KHOA_NGAY_SINH] = ns
    return True


def thieu_ten(accounts) -> list:
    """Các acc CHƯA có tên -> chỉ lấy cho mấy acc này (lấy lại hết mỗi lần mở tool là vô ích)."""
    return [a for a in accounts if not ten_cua(a)]


def thieu_ngay_sinh(accounts) -> list:
    """Các acc CHƯA có ngày sinh. Ngày sinh không đổi -> lấy một lần cho cả đời acc."""
    return [a for a in accounts if not ngay_sinh_cua(a)]
