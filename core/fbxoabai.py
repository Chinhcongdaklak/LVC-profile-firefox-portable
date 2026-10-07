"""XOA BAI VIET FANPAGE bang Graph API CHINH THUC (ADR-029). Module THUAN: khong tkinter, khong mo trinh duyet.

Yeu cau nguoi dung (2026-09-26): tab "Xoa bai viet" — bang acc: STT · acc FB · fanpage (tu quet / chon / nhap id)
· thoi gian bat dau · thoi gian cuoi · the loai (tat ca / video / anh); tool chon bai trong khoang do de xoa.
Nguoi dung chot: "Graph API chinh thuc bang token page cach nay cung duoc".

CO CHE (tai lieu Meta):
  - Token: page access token (hoac user token co pages_manage_posts + pages_read_engagement; tool tu doi ra
    page token qua /me/accounts). Token la BI MAT: khong ghi nhat ky, chi luu data/ (gitignore).
  - Liet ke:  GET {GRAPH}/{page_id}/published_posts?fields=...&since=&until=&limit=100 (theo trang paging.next).
  - Xoa:      DELETE {GRAPH}/{post_id}?access_token=  -> {"success": true}. MOI BAI MOT GOI, khong co bulk.
  - Han muc:  header X-Page-Usage / X-App-Usage (json call_count/total_time/total_cputime, %): >=80 cham lai,
              >=95 hoac ma loi 4/17/32/613 -> nghi (5, 5, 10, 15 phut) roi thu lai.
  - Khong xoa duoc: anh dai dien / anh bia / story highlight (API tu choi -> ghi loi, di tiep).

Moi goi mang di qua ``get``/``delete`` tiem vao (mac dinh requests) de thuoc do chay offline.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

GRAPH = "https://graph.facebook.com/v21.0"
TIMEOUT = 30

#: The loai xoa: ma -> nhan hien thi.
LOAI = (("tat_ca", "Tất cả"), ("video", "Video"), ("anh", "Ảnh"))
NHAN_LOAI = dict(LOAI)
MA_THEO_NHAN = {v: k for k, v in LOAI}

#: Ma loi Graph API = het han muc / bi tiet luu -> nghi roi thu lai.
MA_HAN_MUC = {4, 17, 32, 613}
#: Chuoi nghi (giay) khi dinh han muc: 5', 5', 10', 15'.
NGHI_HAN_MUC = (300, 300, 600, 900)
#: Nguong % han muc: cham lai / dung.
NGUONG_CHAM = 80.0
NGUONG_DUNG = 95.0

FIELDS = "id,created_time,message,permalink_url,attachments{media_type,type,subattachments{media_type,type}}"

#: Canh bai cua page: thu LAN LUOT. ``published_posts`` can token page + quyen day du; page khong quan ly
#: (chi co user token) thi Facebook chi cho ``posts`` / ``feed`` (tool tham khao dung ``posts``).
CANH_BAI = ("published_posts", "posts", "feed")
#: Ma loi "canh nay khong dung duoc" -> thu canh ke tiep (100 = unknown edge/field, 200/10/3 = thieu quyen).
MA_DOI_CANH = {3, 10, 100, 200}

#: Header gia lap trinh duyet — Facebook de chan request "tran" (tool tham khao gui y het bo nay).
HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
               "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"),
    "accept-language": "en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7",
    "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"),
}


def cookie_header(cookie_text: str) -> str:
    """Chuoi cookie (JSON do read_from_profile, hoac dang header 'a=b; c=d') -> 'name=value; ...'
    de nhet vao header 'cookie'. Chi giu cookie facebook. Rong -> ''."""
    t = (cookie_text or "").strip()
    if not t:
        return ""
    if "{" not in t and "[" not in t and "\n" not in t and "\t" not in t and "=" in t:
        return t  # da la chuoi header san
    try:
        from core import cookies as _cm
        phan, seen = [], set()
        for c in _cm.parse(t, default_domain=".facebook.com"):
            if not c.name or c.name in seen or "facebook.com" not in (c.host or ".facebook.com"):
                continue
            seen.add(c.name)
            phan.append(f"{c.name}={c.value}")
        return "; ".join(phan)
    except Exception:  # noqa: BLE001
        return t


def _headers(cookie_text: str = "") -> dict:
    h = dict(HEADERS)
    ch = cookie_header(cookie_text)
    if ch:
        h["cookie"] = ch
    return h


class XoaBaiError(Exception):
    """Loi nghiep vu xoa bai (token/han muc/mang)."""


class TokenChet(XoaBaiError):
    """Token het han / khong hop le (ma 190) -> dung ca dong."""


# ------------------------------------------------------------------ mang (tiem duoc)
def _requests():
    import requests
    return requests


def _get(url: str, params: dict, cookie: str = "") -> tuple:
    r = _requests().get(url, params=params, headers=_headers(cookie), timeout=TIMEOUT)
    return r.status_code, _json(r), dict(r.headers)


def _delete(url: str, params: dict, cookie: str = "") -> tuple:
    r = _requests().delete(url, params=params, headers=_headers(cookie), timeout=TIMEOUT)
    return r.status_code, _json(r), dict(r.headers)


def _json(r) -> dict:
    try:
        d = r.json()
        return d if isinstance(d, dict) else {"data": d}
    except ValueError:
        return {"error": {"message": (r.text or "")[:200], "code": r.status_code}}


def che_token(token: str) -> str:
    """Token che de hien/ghi log: 'EAAB…k3Zd' (khong bao gio in het)."""
    t = (token or "").strip()
    if len(t) <= 10:
        return "•" * len(t)
    return t[:4] + "…" + t[-4:]


def ma_loi(d: dict) -> tuple:
    """(code, message) tu json loi Graph; khong loi -> (0, '')."""
    e = (d or {}).get("error") or {}
    if not e:
        return 0, ""
    try:
        code = int(e.get("code") or 0)
    except (TypeError, ValueError):
        code = 0
    return code, str(e.get("message") or e.get("error_user_msg") or "")


def han_muc_pct(headers: dict) -> float:
    """% han muc cao nhat trong X-Page-Usage / X-App-Usage / X-Business-Use-Case-Usage (0 neu khong co)."""
    cao = 0.0
    for k in ("X-Page-Usage", "x-page-usage", "X-App-Usage", "x-app-usage"):
        raw = (headers or {}).get(k)
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except (TypeError, ValueError):
            continue
        for v in d.values():
            try:
                cao = max(cao, float(v))
            except (TypeError, ValueError):
                pass
    for k in ("X-Business-Use-Case-Usage", "x-business-use-case-usage"):
        raw = (headers or {}).get(k)
        if not raw:
            continue
        try:
            d = json.loads(raw)
            for ds in d.values():
                for it in ds if isinstance(ds, list) else []:
                    for kk in ("call_count", "total_cputime", "total_time"):
                        cao = max(cao, float(it.get(kk) or 0))
        except (TypeError, ValueError, AttributeError):
            pass
    return cao


# ------------------------------------------------------------------ ngay thang
def ngay_tu_chuoi(s: str) -> Optional[datetime]:
    """'dd/mm/yyyy' (cung nhan 'd/m/yyyy', 'yyyy-mm-dd') -> datetime 00:00 gio may; sai -> None."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def khoang_ngay(tu: str, den: str) -> tuple:
    """(since_epoch, until_epoch, loi). den la NGAY CUOI (bao gom ca ngay) -> until = den + 1 ngay.
    Trong: tu trong = tu dau; den trong = toi hom nay."""
    t = ngay_tu_chuoi(tu) if (tu or "").strip() else None
    d = ngay_tu_chuoi(den) if (den or "").strip() else None
    if (tu or "").strip() and t is None:
        return 0, 0, f"Ngày bắt đầu sai định dạng (dd/mm/yyyy): {tu}"
    if (den or "").strip() and d is None:
        return 0, 0, f"Ngày cuối sai định dạng (dd/mm/yyyy): {den}"
    if d is None:
        d = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if t is not None and t > d:
        return 0, 0, "Ngày bắt đầu phải trước hoặc bằng ngày cuối."
    since = int(t.timestamp()) if t is not None else 0
    until = int((d + timedelta(days=1)).timestamp())
    return since, until, ""


# ------------------------------------------------------------------ de xuat khoang ngay
#: Don vi cho "cu hon N ...": ma -> nhan.
DON_VI = (("ngay", "ngày"), ("thang", "tháng"), ("nam", "năm"))
NHAN_DON_VI = dict(DON_VI)
MA_DON_VI = {v: k for k, v in DON_VI}


def _chuoi_ngay(d: datetime) -> str:
    return d.strftime("%d/%m/%Y")


def nam_hien_tai(now: Optional[datetime] = None) -> int:
    return (now or datetime.now()).year


def cac_nam(now: Optional[datetime] = None, lui: int = 8) -> list:
    """Danh sach nam de do vao o chon: [nam nay, nam truoc, ... lui nam]."""
    n = nam_hien_tai(now)
    return [n - i for i in range(max(1, lui))]


def khoang_nam(nam) -> tuple:
    """CA NAM ``nam`` -> (tu, den, loi) = ('01/01/nam', '31/12/nam', '')."""
    try:
        n = int(str(nam).strip())
    except (TypeError, ValueError):
        return "", "", f"Năm không hợp lệ: {nam}"
    if not 1990 <= n <= 2999:
        return "", "", f"Năm ngoài khoảng cho phép: {n}"
    return f"01/01/{n}", f"31/12/{n}", ""


def khoang_truoc_ngay(ngay: str) -> tuple:
    """Moi bai TRUOC ngay do (KHONG gom chinh ngay do) -> (tu rong = tu dau, den = ngay - 1 hom, loi)."""
    d = ngay_tu_chuoi(ngay)
    if d is None:
        return "", "", f"Ngày sai định dạng (dd/mm/yyyy): {ngay}"
    return "", _chuoi_ngay(d - timedelta(days=1)), ""


def _lui_thang(d: datetime, so: int) -> datetime:
    import calendar
    thang = d.month - so
    nam = d.year + (thang - 1) // 12
    thang = (thang - 1) % 12 + 1
    return d.replace(year=nam, month=thang, day=min(d.day, calendar.monthrange(nam, thang)[1]))


def khoang_cu_hon(so, don_vi: str = "thang", now: Optional[datetime] = None) -> tuple:
    """Bai CU HON ``so`` ngay/thang/nam tinh tu hom nay -> (tu rong, den, loi)."""
    try:
        n = int(str(so).strip())
    except (TypeError, ValueError):
        return "", "", f"Số không hợp lệ: {so}"
    if n <= 0:
        return "", "", "Số phải lớn hơn 0."
    don_vi = MA_DON_VI.get(don_vi, don_vi)
    goc = (now or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    if don_vi == "ngay":
        moc = goc - timedelta(days=n)
    elif don_vi == "thang":
        moc = _lui_thang(goc, n)
    elif don_vi == "nam":
        moc = _lui_thang(goc, n * 12)
    else:
        return "", "", f"Đơn vị lạ: {don_vi}"
    return "", _chuoi_ngay(moc - timedelta(days=1)), ""


def khoang_n_ngay(n: int, now: Optional[datetime] = None) -> tuple:
    """N ngay GAN DAY: (hom nay - n, hom nay, '')."""
    goc = (now or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    return _chuoi_ngay(goc - timedelta(days=max(0, int(n)))), _chuoi_ngay(goc), ""


def gio_bai(post: dict) -> int:
    """created_time ISO '2026-09-24T10:00:00+0000' -> epoch (0 neu khong doc duoc)."""
    s = str(post.get("created_time") or "")
    if not s:
        return 0
    s = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", s)
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


# ------------------------------------------------------------------ phan loai
def phan_loai(post: dict) -> str:
    """'video' / 'anh' / 'khac' theo attachments cua bai (album/anh -> anh; video/reel -> video)."""
    ds = ((post or {}).get("attachments") or {}).get("data") or []
    co_video = co_anh = False
    stack = list(ds)
    while stack:
        a = stack.pop()
        mt = str(a.get("media_type") or "").lower()
        ty = str(a.get("type") or "").lower()
        if mt == "video" or "video" in ty or "reel" in ty:
            co_video = True
        elif mt in ("photo", "album") or "photo" in ty or "album" in ty:
            co_anh = True
        sub = (a.get("subattachments") or {}).get("data") or []
        stack.extend(sub)
    if co_video:
        return "video"
    if co_anh:
        return "anh"
    return "khac"


def khop_loai(post: dict, loai: str) -> bool:
    loai = (loai or "tat_ca").strip()
    if loai == "tat_ca":
        return True
    return phan_loai(post) == loai


def loc_bai(posts: list, loai: str, since: int = 0, until: int = 0) -> list:
    """Loc THEO MAY (khong tin API): trong [since, until) va dung the loai."""
    ra = []
    for p in posts or []:
        g = gio_bai(p)
        if since and g and g < since:
            continue
        if until and g and g >= until:
            continue
        if khop_loai(p, loai):
            ra.append(p)
    return ra


def nam_cua_bai(post: dict) -> int:
    """Nam dang bai theo created_time (0 neu khong doc duoc)."""
    g = gio_bai(post)
    return datetime.fromtimestamp(g).year if g else 0


def dem_theo_nam(posts: list) -> dict:
    """{nam: {tong, video, anh, khac}} — de nguoi dung biet nam nao con bao nhieu bai ma chon xoa."""
    ra: dict = {}
    for p in posts or []:
        n = nam_cua_bai(p)
        o = ra.setdefault(n, {"tong": 0, "video": 0, "anh": 0, "khac": 0})
        o["tong"] += 1
        o[phan_loai(p)] += 1
    return dict(sorted(ra.items(), reverse=True))


def dong_dem_nam(d: dict) -> list:
    """Cac dong chu de in ra nhat ky tu ``dem_theo_nam``."""
    ra = []
    for nam, o in (d or {}).items():
        ten = str(nam) if nam else "không rõ năm"
        ra.append(f"{ten}: {o['tong']} bài (video {o['video']} · ảnh {o['anh']} · khác {o['khac']})")
    return ra


# ------------------------------------------------------------------ token / page
def thong_tin_token(token: str, *, cookie: str = "", get: Optional[Callable] = None) -> dict:
    """GET /me -> {id, name, loi}. Token page thi me = page; token user thi me = nguoi dung."""
    get = get or _get
    st, d, _h = get(f"{GRAPH}/me", {"fields": "id,name", "access_token": token}, cookie)
    code, msg = ma_loi(d)
    if code or st >= 400:
        return {"id": "", "name": "", "loi": f"token không dùng được ({code}): {msg}"}
    return {"id": str(d.get("id") or ""), "name": str(d.get("name") or ""), "loi": ""}


def cac_page_cua_token(token: str, *, cookie: str = "", get: Optional[Callable] = None) -> tuple:
    """Danh sach page token nay quan ly: [{id, name, access_token}] (theo trang). Token PAGE -> chi 1 page (me).
    Tra (ds, loi)."""
    get = get or _get
    ds, url, params = [], f"{GRAPH}/me/accounts", {"fields": "id,name,access_token", "limit": 100,
                                                     "access_token": token}
    for _ in range(50):
        st, d, _h = get(url, params, cookie)
        code, msg = ma_loi(d)
        if code == 190:
            return [], f"token hết hạn/không hợp lệ (190): {msg}"
        if code or st >= 400:
            break
        for p in d.get("data") or []:
            if p.get("id"):
                ds.append({"id": str(p["id"]), "name": str(p.get("name") or p["id"]),
                           "access_token": str(p.get("access_token") or "")})
        url = ((d.get("paging") or {}).get("next")) or ""
        if not url:
            break
        params = {}
    if ds:
        return ds, ""
    me = thong_tin_token(token, cookie=cookie, get=get)
    if me["loi"]:
        return [], me["loi"]
    # Token PAGE: /me chinh la page -> dung token nay cho page do.
    return [{"id": me["id"], "name": me["name"], "access_token": token}], ""


#: Trang Meta lộ page/app access token trong HTML phiên đã đăng nhập (cách người dùng chỉ 07/10:
#: vào trang này đã nhập 2FA rồi view-source, dòng EAAG… là token).
TOKEN_URL = "https://business.facebook.com/business_locations/"
#: Token kiểu EAAG (app token của Business Suite). Bắt cả bản escape trong JSON (EAAGà… hiếm,
#: nhưng token chuẩn chỉ gồm [A-Za-z0-9]). Ưu tiên EAAG; vẫn nhận EAA khác phòng Facebook đổi app.
_TOKEN_RE = re.compile(r"EAAG[A-Za-z0-9]{20,}")
_TOKEN_RE_RONG = re.compile(r"EAA[A-Za-z0-9]{20,}")


def token_trong_html(html: str) -> str:
    """Moi token EAAG dau tien trong HTML trang business_locations. Thuan, test duoc.

    Tra "" neu khong thay. Uu tien EAAG (token Business Suite); khong co thi lay EAA bat ky
    dai nhat (token dai hon thuong la token that, khong phai manh id ngan trung dau).
    """
    s = html or ""
    m = _TOKEN_RE.search(s)
    if m:
        return m.group(0)
    hits = _TOKEN_RE_RONG.findall(s)
    return max(hits, key=len) if hits else ""


def token_tu_business(account=None, *, cookie: str = "", proxy=None,
                      get: Optional[Callable] = None) -> tuple:
    """Lay token bang HTTP: GET business_locations kem cookie acc roi do dong EAAG. (acc, cookie).

    Theo cach nguoi dung chi (07/10): KHONG mo trinh duyet -> nhanh. ``get(url, cookie, proxy)``
    tiem cho thuoc, tra ``(final_url, html, status)``; mac dinh goi HTTP that. Tra ``(token, loi)``.
    Cookie chet / chua nhap 2FA -> FB tra trang khong co token -> ("", ly do).
    """
    ck = (cookie or "").strip()
    if not ck and account is not None:
        ck = (getattr(account, "cookie", "") or "").strip()
    if not ck:
        return "", "acc chưa có cookie"
    lay = get or (lambda url, c, px: _lay_trang(url, c, px))
    try:
        final_url, html, status = lay(TOKEN_URL, ck, proxy)
    except Exception as exc:  # noqa: BLE001
        return "", f"lỗi mạng: {str(exc)[:60]}"
    fin = (final_url or "").lower()
    if "login" in fin or "/checkpoint" in fin:
        return "", "phiên chưa đăng nhập / cần nhập 2FA trong trình duyệt trước"
    tok = token_trong_html(html)
    if not tok:
        return "", f"không thấy token trong trang (HTTP {status})"
    return tok, ""


def _lay_trang(url: str, cookie: str, proxy=None):
    """GET that (requests) kem cookie + header trinh duyet. Tra (final_url, html, status)."""
    from core import fbthongtin
    return fbthongtin._get_that(url, cookie, proxy)


#: File lệnh/kết quả dùng chung với agent đăng nhập (action "gettoken" nằm trong fblogin_agent.js).
_TOK_CMD = "qlfp-weblogin.json"
_TOK_RESULT = "qlfp-weblogin-result.json"


def _tok_put_cmd(profile_dir: str, account, code: str) -> None:
    import os
    cmd = {"action": "gettoken", "email": account.id,
           "code": code or "", "code_at": time.time(), "formTimeout": 90000, "delay": 2500}
    os.makedirs(profile_dir, exist_ok=True)
    with open(os.path.join(profile_dir, _TOK_CMD), "w", encoding="utf-8") as fh:
        json.dump(cmd, fh, ensure_ascii=False)


def token_qua_browser(manager, account, *, timeout: float = 150.0,
                      log: Optional[Callable[[str], None]] = None) -> tuple:
    """Mở Firefox THƯỜNG vào business_locations, điền 2FA nếu bị hỏi, đọc dòng EAAG. (token, loi).

    Dùng process-script agent (fblogin_agent.js action "gettoken") -> Firefox mở BÌNH THƯỜNG, không
    debug port -> KHÔNG dính reCAPTCHA (BiDi thì dính — xem NHO). Acc có 2FA secret thì tự điền mã
    (core.totp, làm mới mỗi 5s). Token KHÔNG ghi log full (chỉ bản che).
    """
    import os

    from core import totp

    noi = log or (lambda _m: None)
    profile = manager.profile_dir(account)
    twofa = (getattr(account, "twofa", "") or "").strip()
    for n in (_TOK_CMD, _TOK_RESULT):
        try:
            os.remove(os.path.join(profile, n))
        except OSError:
            pass
    _tok_put_cmd(profile, account, totp.generate(twofa) if twofa else "")
    manager.close(account, wait=6.0)
    manager.launch(account, url=TOKEN_URL)
    # TRÌNH DUYỆT ĐÃ MỞ -- mọi thứ dưới đây nằm trong try/finally để luôn đóng được.
    tok, loi = "", "hết giờ chưa lấy được token"
    try:
        deadline = time.time() + timeout
        last_code = time.time()
        while time.time() < deadline:
            r = _read_result(profile)
            if r:
                st = r.get("state") or ""
                det = str(r.get("detail") or "")
                if st == "token-found" and det.startswith("EAA"):
                    tok, loi = det, ""
                    noi(f"[{account.id}] token: {che_token(tok)} ✓")
                    break
                if st == "checkpoint":
                    loi = "acc bị checkpoint"
                    break
                if st == "token-timeout":
                    loi = "mở được trang nhưng không thấy EAAG (2FA/đăng xuất?)"
                    break
            # Làm mới mã TOTP mỗi 5s (mã đổi theo thời gian; agent đọc lại command mỗi tick).
            if twofa and time.time() - last_code >= 5:
                _tok_put_cmd(profile, account, totp.generate(twofa))
                last_code = time.time()
            time.sleep(1)
    finally:
        try:
            manager.close(account, wait=8.0)
        except Exception:  # noqa: BLE001
            pass
        for n in (_TOK_CMD, _TOK_RESULT):
            try:
                os.remove(os.path.join(profile, n))
            except OSError:
                pass
    return tok, loi


def _read_result(profile_dir: str) -> Optional[dict]:
    import os
    try:
        with open(os.path.join(profile_dir, _TOK_RESULT), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def token_tu_cookie(manager, account, *, log: Optional[Callable[[str], None]] = None,
                    get: Optional[Callable] = None) -> tuple:
    """Lấy access token TỪ COOKIE/phiên của acc. Trả ``(token, loi)``; không được -> ("", lý do).

    Thử HAI đường, theo thứ tự:
      1) HTTP: GET business_locations kèm cookie rồi đọc dòng EAAG (cách người dùng chỉ 07/10) —
         NHANH, không mở trình duyệt.
      2) Nếu không ra: mở trình duyệt acc quét token trong phiên (core.checklive.derive_token).

    Facebook mới có thể vẫn không lộ token -> khi đó dán token tay vào ô Token.
    """
    noi = log or (lambda _m: None)
    tok, loi = token_tu_business(account, get=get)
    if tok:
        noi(f"[{account.id}] lấy token qua business_locations (HTTP): {che_token(tok)}")
        return tok, ""
    noi(f"[{account.id}] HTTP không ra ({loi}); mở trình duyệt vào business_locations...")
    try:
        return token_qua_browser(manager, account, log=log)
    except Exception as exc:  # noqa: BLE001
        return "", str(exc)


def ten_page(page_id: str, token: str, *, cookie: str = "", get: Optional[Callable] = None) -> tuple:
    """GET /{page_id}?fields=name -> (ten, loi). Dung khi nguoi dung GO ID TAY (dong khoi tro tro ID)."""
    get = get or _get
    if not (page_id or "").strip() or not (token or "").strip():
        return "", "thiếu ID page hoặc token"
    st, d, _h = get(f"{GRAPH}/{page_id}", {"fields": "name", "access_token": token}, cookie)
    code, msg = ma_loi(d)
    if code or st >= 400:
        return "", f"không đọc được tên page ({code or st}): {msg}"
    return str(d.get("name") or ""), ""


# ------------------------------------------------------------------ liet ke / xoa
def _ep_limit(url: str, n: int = 100) -> str:
    """Ep limit=n vao URL phan trang. Tool tham khao vap dung day: paging.next co the mang limit nho
    (hoac khong co) -> doc thieu bai, bo sot bai cu."""
    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
    try:
        u = urlparse(url)
        q = parse_qs(u.query)
        try:
            cu = int((q.get("limit") or ["0"])[0])
        except (TypeError, ValueError):
            cu = 0
        if cu < n:
            q["limit"] = [str(n)]
        return urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(q, doseq=True), u.fragment))
    except ValueError:
        return url


def _mot_canh(page_id: str, canh: str, token: str, since: int, until: int, *,
              get: Callable, log: Callable, sleep: Callable, cookie: str = "",
              nen_dung: Optional[Callable[[], bool]], toi_da_trang: int) -> list:
    """Doc het mot canh (published_posts / posts / feed). Nem TokenChet / XoaBaiError."""
    params = {"fields": FIELDS, "limit": 100, "access_token": token}
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    url, ra, lan_nghi = f"{GRAPH}/{page_id}/{canh}", [], 0
    for trang in range(toi_da_trang):
        if nen_dung and nen_dung():
            break
        st, d, h = get(url, params, cookie)
        code, msg = ma_loi(d)
        if code == 190:
            raise TokenChet(f"token hết hạn/không hợp lệ (190): {msg}")
        if code in MA_HAN_MUC:
            # Facebook chan vi goi qua nhanh: NGHI roi doc lai dung trang nay (ban cu bo ca dong).
            if lan_nghi >= len(NGHI_HAN_MUC):
                raise XoaBaiError(f"đụng hạn mức khi liệt kê ({code}): {msg} — đã nghỉ {lan_nghi} lần")
            giay = NGHI_HAN_MUC[lan_nghi]
            lan_nghi += 1
            log(f"[{page_id}] Facebook chặn khi liệt kê ({code}) — nghỉ {giay // 60} phút rồi đọc lại")
            sleep(giay)
            continue
        if code or st >= 400:
            raise XoaBaiError(f"không liệt kê được bài ({code or st}): {msg}")
        ds = d.get("data") or []
        ra.extend(p for p in ds if isinstance(p, dict) and p.get("id"))
        log(f"[{page_id}] {canh} trang {trang + 1}: +{len(ds)} bài (tổng {len(ra)})")
        url = ((d.get("paging") or {}).get("next")) or ""
        if not url or not ds:
            break
        url = _ep_limit(url)
        params = {}
        pct = han_muc_pct(h)
        if pct >= NGUONG_CHAM:
            log(f"[{page_id}] hạn mức {pct:.0f}% — chậm lại")
            sleep(10.0)
    return ra


def liet_ke_bai(page_id: str, token: str, since: int = 0, until: int = 0, *,
                cookie: str = "", get: Optional[Callable] = None,
                log: Optional[Callable[[str], None]] = None,
                nen_dung: Optional[Callable[[], bool]] = None, toi_da_trang: int = 200,
                sleep: Callable = time.sleep) -> list:
    """Cac bai da dang cua page trong [since, until) (API loc + may loc lai). Nem TokenChet / XoaBaiError.

    Thu lan luot cac canh trong ``CANH_BAI``: ``published_posts`` truoc (dung cho page minh quan ly),
    canh nao bao "khong co quyen / khong co canh nay" thi thu canh ke (``posts``, ``feed``) — page chi co
    user token van doc duoc, giong tool tham khao.
    """
    get = get or _get
    noi = log or (lambda _m: None)
    loi_cuoi = None
    for i, canh in enumerate(CANH_BAI):
        try:
            ra = _mot_canh(page_id, canh, token, since, until, get=get, log=noi, sleep=sleep,
                           cookie=cookie, nen_dung=nen_dung, toi_da_trang=toi_da_trang)
        except TokenChet:
            raise
        except XoaBaiError as exc:
            code = 0
            m = re.search(r"\((\d+)\)", str(exc))
            if m:
                code = int(m.group(1))
            loi_cuoi = exc
            if code in MA_DOI_CANH and i + 1 < len(CANH_BAI):
                noi(f"[{page_id}] {canh} không dùng được ({code}) — thử /{CANH_BAI[i + 1]}")
                continue
            raise
        return loc_bai(ra, "tat_ca", since, until)
    raise loi_cuoi or XoaBaiError("không liệt kê được bài")


def xoa_mot_bai(post_id: str, token: str, *, cookie: str = "", delete: Optional[Callable] = None) -> tuple:
    """DELETE /{post_id} -> (ok, loi, headers). Ma 190 -> nem TokenChet; ma han muc -> nem XoaBaiError."""
    delete = delete or _delete
    st, d, h = delete(f"{GRAPH}/{post_id}", {"access_token": token}, cookie)
    code, msg = ma_loi(d)
    if code == 190:
        raise TokenChet(f"token hết hạn/không hợp lệ (190): {msg}")
    if code in MA_HAN_MUC:
        raise XoaBaiError(f"đụng hạn mức ({code}): {msg}")
    if code or st >= 400:
        return False, f"{code or st}: {msg}", h
    if d.get("success") is False:
        return False, "Facebook trả về success=false", h
    return True, "", h


def chay_xoa(page_id: str, token: str, tu: str, den: str, loai: str = "tat_ca", *,
             dry: bool = True, gioi_han: int = 0, cach_giay: float = 2.0, cookie: str = "",
             get: Optional[Callable] = None, delete: Optional[Callable] = None,
             sleep: Callable = time.sleep,
             nen_dung: Optional[Callable[[], bool]] = None,
             on_tien_do: Optional[Callable[[dict], None]] = None,
             log: Optional[Callable[[str], None]] = None) -> dict:
    """Quet (dry=True: CHI DEM) hoac XOA bai cua page trong khoang ngay + the loai.

    Tra {"ok": bool, "quet": n bai trong khoang, "khop": n khop the loai, "xoa": n da xoa, "loi_bai": [(id, ly_do)],
         "bo_qua": n (qua gioi han), "loi": "" | ly do dung, "ds": [bai khop {id, created_time, loai, message}]}.
    Xoa TUNG bai, nghi ``cach_giay`` giua 2 bai; dinh han muc -> nghi theo NGHI_HAN_MUC roi thu lai bai do.
    """
    get, delete = get or _get, delete or _delete
    noi = log or (lambda _m: None)
    kq = {"ok": False, "quet": 0, "khop": 0, "xoa": 0, "loi_bai": [], "bo_qua": 0, "loi": "", "ds": []}
    since, until, loi = khoang_ngay(tu, den)
    if loi:
        kq["loi"] = loi
        return kq
    if not (page_id or "").strip():
        kq["loi"] = "Chưa có ID fanpage."
        return kq
    if not (token or "").strip():
        kq["loi"] = "Chưa có token."
        return kq
    try:
        bai = liet_ke_bai(page_id, token, since, until, cookie=cookie, get=get, log=noi, nen_dung=nen_dung, sleep=sleep)
    except XoaBaiError as exc:
        kq["loi"] = str(exc)
        return kq
    if nen_dung and nen_dung():
        kq["loi"] = "dừng theo yêu cầu"
        return kq
    kq["quet"] = len(bai)
    khop = loc_bai(bai, loai, since, until)
    kq["khop"] = len(khop)
    kq["ds"] = [{"id": str(p["id"]), "created_time": str(p.get("created_time") or ""),
                 "loai": phan_loai(p), "message": str(p.get("message") or "")[:80],
                 "permalink_url": str(p.get("permalink_url") or "")} for p in khop]
    noi(f"[{page_id}] {len(bai)} bài trong khoảng, {len(khop)} bài khớp thể loại '{NHAN_LOAI.get(loai, loai)}'")
    if dry:
        kq["ok"] = True
        return kq
    lan_nghi = 0
    for i, p in enumerate(khop):
        if nen_dung and nen_dung():
            kq["loi"] = "dừng theo yêu cầu"
            break
        if gioi_han and kq["xoa"] >= gioi_han:
            kq["bo_qua"] = len(khop) - i
            noi(f"[{page_id}] đã tới giới hạn {gioi_han} bài/lần — còn {kq['bo_qua']} bài để lần sau")
            break
        pid = str(p["id"])
        while True:
            try:
                ok, ly_do, h = xoa_mot_bai(pid, token, cookie=cookie, delete=delete)
            except TokenChet as exc:
                kq["loi"] = str(exc)
                return kq
            except XoaBaiError as exc:
                if lan_nghi >= len(NGHI_HAN_MUC):
                    kq["loi"] = f"{exc} — đã nghỉ {lan_nghi} lần, dừng dòng này"
                    return kq
                giay = NGHI_HAN_MUC[lan_nghi]
                lan_nghi += 1
                noi(f"[{page_id}] {exc} — nghỉ {giay // 60} phút rồi thử lại")
                sleep(giay)
                continue
            break
        if ok:
            kq["xoa"] += 1
            noi(f"[{page_id}] ✓ đã xoá {pid} ({p.get('created_time', '')[:10]}, {phan_loai(p)})")
        else:
            kq["loi_bai"].append((pid, ly_do))
            noi(f"[{page_id}] ✖ không xoá được {pid}: {ly_do}")
        if on_tien_do:
            on_tien_do({"page_id": page_id, "xoa": kq["xoa"], "khop": len(khop), "loi": len(kq["loi_bai"])})
        pct = han_muc_pct(h)
        if pct >= NGUONG_DUNG:
            noi(f"[{page_id}] hạn mức {pct:.0f}% — nghỉ 5 phút")
            sleep(NGHI_HAN_MUC[0])
        elif pct >= NGUONG_CHAM:
            sleep(max(cach_giay, 10.0))
        elif cach_giay > 0 and i + 1 < len(khop):
            sleep(cach_giay)
    kq["ok"] = not kq["loi"]
    return kq


def thong_ke_nam(page_id: str, token: str, *, cookie: str = "", get: Optional[Callable] = None,
                 log: Optional[Callable[[str], None]] = None,
                 nen_dung: Optional[Callable[[], bool]] = None,
                 sleep: Callable = time.sleep) -> tuple:
    """Doc HET bai cua page roi dem theo nam -> ({nam: {...}}, loi). Dung de nguoi dung chon nam ma xoa."""
    get = get or _get
    if not (page_id or "").strip():
        return {}, "Chưa có ID fanpage."
    if not (token or "").strip():
        return {}, "Chưa có token."
    try:
        bai = liet_ke_bai(page_id, token, 0, 0, cookie=cookie, get=get, log=log, nen_dung=nen_dung, sleep=sleep)
    except XoaBaiError as exc:
        return {}, str(exc)
    return dem_theo_nam(bai), ""


def dong_txt(acc_id: str, page_id: str, bai: dict) -> str:
    """Dong ghi TXT sau khi xoa: acc|page|id bai|ngay dang|loai|link."""
    return "|".join([str(acc_id), str(page_id), str(bai.get("id", "")),
                     str(bai.get("created_time", ""))[:19], str(bai.get("loai", "")),
                     str(bai.get("permalink_url", ""))])
