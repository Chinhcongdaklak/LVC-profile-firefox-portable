"""LAY LAI COOKIE MOI tu profile Firefox roi ghi nguoc vao acc.

Dung o hai cho:
  * nguoi dung bam "🍪 Lấy lại cookie mới" trong tab Quan ly acc (chay nhieu acc song song);
  * sau khi DANG NHAP WEB thanh cong -> tu thay cookie cu bang cookie tuoi (core/fblogin).

HAI NGUON cookie, lay cai nao co:
  1. PROBE (``manager.read_probe_cookies``): trinh duyet tu bao ra khi trang Facebook mo va
     thay da dang nhap — doc tu kho cookie trong BO NHO nen moi nhat, khong dinh do tre ghi
     cookies.sqlite. Nhung probe chi co khi acc vua mo trang Facebook.
  2. cookies.sqlite trong profile (``cookies.read_from_profile``) — luon co, nhung Firefox
     dang MO thi chua ghi het xuong file -> nen dong trinh duyet truoc cho chac.

Chi nhan cookie co ``c_user`` (dinh danh acc Facebook) — khong co thi coi nhu CHUA dang nhap
va GIU NGUYEN cookie cu, khong ghi de bang chuoi rong (mat cookie cu la hong ca luong).

Ham THUAN: ``co_dang_nhap`` / ``chon_cookie``.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from . import cookies as cookies_module

#: Cookie bat buoc phai co thi moi tinh la "da dang nhap Facebook".
COOKIE_DINH_DANH = "c_user"


# --- ham THUAN --------------------------------------------------------------

def co_dang_nhap(chuoi_hoac_list) -> bool:
    """Chuoi cookie (JSON/header) hoac list Cookie co ``c_user`` khong. THUAN."""
    if not chuoi_hoac_list:
        return False
    if isinstance(chuoi_hoac_list, str):
        return COOKIE_DINH_DANH in chuoi_hoac_list
    try:
        return any(getattr(c, "name", "") == COOKIE_DINH_DANH and getattr(c, "value", "")
                   for c in chuoi_hoac_list)
    except TypeError:
        return False


def chon_cookie(probe: str, tu_file: str, probe_moi_hon: bool = False) -> str:
    """Chon ban cookie dung giua PROBE va cookies.sqlite. THUAN.

    Chi nhan ban co ``c_user``. Co ca hai -> lay ban MOI HON (nguoi goi so thoi gian file;
    probe la file do lan mo truoc de lai nen CO THE CU HON cookies.sqlite — da do that
    05/10: probe tra dung cookie cu 544 ky tu trong khi sqlite co ban moi).
    Ca hai khong co -> "" (nguoi goi GIU cookie cu, KHONG ghi de bang chuoi rong)."""
    co_probe, co_file = co_dang_nhap(probe), co_dang_nhap(tu_file)
    if co_probe and co_file:
        return probe if probe_moi_hon else tu_file
    if co_probe:
        return probe
    if co_file:
        return tu_file
    return ""


def nguon_cookie(probe: str, tu_file: str, probe_moi_hon: bool = False) -> str:
    """Ten nguon da dung (de ghi nhat ky): "probe" | "cookies.sqlite" | ""."""
    chon = chon_cookie(probe, tu_file, probe_moi_hon)
    if not chon:
        return ""
    return "probe" if chon == probe and co_dang_nhap(probe) else "cookies.sqlite"


# --- doc tu profile (can dia) -----------------------------------------------

#: Firefox cua tool (FirefoxPortable) — UA that ma cookie nay da dung.
UA_FIREFOX_TOOL = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:154.0) Gecko/20100101 Firefox/154.0"


def chuan_hoa(chuoi: str) -> str:
    """Chuoi cookie bat ky (JSON Cookie-Editor / Netscape / header) -> CHI cookie Facebook,
    dang 'c_user=...; xs=...; ...' (nguoi dung chot 08/10). Rong neu khong co gi. THUAN."""
    try:
        ds = cookies_module.parse(chuoi, default_domain=".facebook.com")
    except Exception:  # noqa: BLE001
        return ""
    return cookies_module.to_header(cookies_module.chi_facebook(ds))


def ma_hoa_ua(ua: str) -> str:
    """UA -> gia tri cho muc 'useragent=' trong chuoi cookie: base64 roi url-encode
    (vd '...Safari/537.36' -> 'TW96aWxsYS81...%3D%3D'), dung kieu cac tool FB khac. THUAN."""
    import base64
    from urllib.parse import quote
    ua = (ua or "").strip()
    if not ua:
        return ""
    return quote(base64.b64encode(ua.encode("utf-8")).decode("ascii"), safe="")


def them_useragent(chuoi: str, ua: str) -> str:
    """Gan 'useragent=<base64 UA>' vao cuoi chuoi cookie (thay neu da co). THUAN."""
    chuoi = (chuoi or "").strip().rstrip(";").strip()
    if not chuoi:
        return ""
    phan = [p.strip() for p in chuoi.split(";") if p.strip() and not p.strip().lower().startswith("useragent=")]
    ma = ma_hoa_ua(ua)
    if ma:
        phan.append("useragent=" + ma)
    return "; ".join(phan)


def ua_cua(account) -> str:
    """UA di kem cookie: UA gia lap gan cho acc (extra.user_agent) neu co, khong thi UA
    Firefox that cua tool (chinh la UA ma phien cookie nay da dung)."""
    try:
        ua = (account.extra.get("user_agent") or "").strip()
    except Exception:  # noqa: BLE001
        ua = ""
    return ua or UA_FIREFOX_TOOL


def _probe(manager, account) -> str:
    try:
        return chuan_hoa(manager.read_probe_cookies(account) or "")
    except Exception:  # noqa: BLE001
        return ""


def _tu_file(manager, account) -> str:
    # cookies.sqlite chua CA cookie google/2fa.live... -> chi lay ho Facebook (loi nguoi dung
    # bao 08/10: "lay sai cookie" = JSON lan domain khac). Xuat dang header cho dan tool khac.
    try:
        ds = cookies_module.read_from_profile(manager.profile_dir(account))
    except Exception:  # noqa: BLE001
        return ""
    if not co_dang_nhap(ds):
        return ""
    return cookies_module.to_header(cookies_module.chi_facebook(ds))


def _probe_moi_hon(manager, account) -> bool:
    """File probe co MOI HON cookies.sqlite khong (so thoi gian sua file)."""
    import os
    try:
        t_probe = os.path.getmtime(manager.login_probe_path(account))
    except (OSError, AttributeError):
        return False
    for ten in ("cookies.sqlite-wal", "cookies.sqlite"):
        try:
            return t_probe > os.path.getmtime(os.path.join(manager.profile_dir(account), ten))
        except OSError:
            continue
    return True          # khong co cookies.sqlite -> probe la nguon duy nhat


def doc_cookie_moi(manager, account) -> tuple:
    """(chuoi cookie, nguon) doc tu profile. Chuoi rong = chua dang nhap."""
    probe = _probe(manager, account)
    tu_file = _tu_file(manager, account)
    moi_hon = _probe_moi_hon(manager, account) if (probe and tu_file) else False
    return chon_cookie(probe, tu_file, moi_hon), nguon_cookie(probe, tu_file, moi_hon)


def lay_lai_mot(manager, account, *, dong_truoc: bool = True,
                log: Optional[Callable[[str], None]] = None) -> dict:
    """Lay cookie moi cua MOT acc, ghi vao account neu co. Tra {ok, nguon, so, ly_do}.

    ``dong_truoc``: dong Firefox cua acc truoc khi doc (Firefox dang mo thi cookies.sqlite
    chua ghi het). Khong nem.
    """
    noi = log or (lambda _m: None)
    if not manager.is_installed(account):
        return {"ok": False, "nguon": "", "so": 0, "ly_do": "chưa có profile"}
    if dong_truoc:
        try:
            if manager.is_running(account):
                noi(f"[{account.id}] đóng trình duyệt để lấy cookie đầy đủ...")
                manager.close(account, wait=8.0)
        except Exception:  # noqa: BLE001
            pass
    chuoi, nguon = doc_cookie_moi(manager, account)
    if not chuoi:
        return {"ok": False, "nguon": "", "so": 0,
                "ly_do": "chưa đăng nhập (không thấy c_user trong profile)"}
    cu = (account.cookie or "").strip()
    if cu and cu != chuoi:
        # Giu MOT ban cookie cu de con duong lui: cookie trong profile co the la phien
        # da chet (acc bi out) — thay vao roi moi biet, luc do con cai ma khoi phuc.
        try:
            account.extra["cookie_truoc"] = cu
        except Exception:  # noqa: BLE001
            pass
    chuoi = them_useragent(chuoi, ua_cua(account))     # 'useragent=...' nhu tool khac
    account.cookie = chuoi
    account.cookie_ok = time.strftime("%Y-%m-%d %H:%M")
    if not (account.status or "").strip() or account.status == "Chưa rõ":
        account.status = "Live"
    from core import trang_thai as _tt
    _tt.ghi(account, _tt.LIVE, f"lấy cookie mới từ {nguon}", "lấy cookie")
    noi(f"[{account.id}] đã lấy cookie mới ({len(chuoi)} ký tự, từ {nguon}).")
    return {"ok": True, "nguon": nguon, "so": len(chuoi), "ly_do": ""}


def lay_lai_nhieu(manager, accounts, *, workers: int = 3, dong_truoc: bool = True,
                  log: Optional[Callable[[str], None]] = None,
                  on_xong: Optional[Callable[[object, dict], None]] = None) -> dict:
    """Lay lai cookie cho nhieu acc (song song). Tra {ok: [id], hong: [(id, ly do)], so}."""
    ds = list(accounts)
    n = max(1, min(int(workers or 1), 8))

    def mot(acc):
        kq = lay_lai_mot(manager, acc, dong_truoc=dong_truoc, log=log)
        if on_xong:
            try:
                on_xong(acc, kq)
            except Exception:  # noqa: BLE001
                pass
        return acc, kq

    ok, hong = [], []
    if n <= 1 or len(ds) <= 1:
        for a in ds:
            _a, kq = mot(a)
            (ok.append(a.id) if kq["ok"] else hong.append((a.id, kq["ly_do"])))
    else:
        with ThreadPoolExecutor(max_workers=n) as pool:
            for a, kq in pool.map(mot, ds):
                (ok.append(a.id) if kq["ok"] else hong.append((a.id, kq["ly_do"])))
    return {"ok": ok, "hong": hong, "so": len(ds)}
