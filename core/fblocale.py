"""Doi ngon ngu giao dien Facebook cua tung acc.

Facebook chon ngon ngu theo cookie ``locale``: ``vi_VN`` la tieng Viet, ``en_US``
la tieng Anh. Doi cookie do la doi ngon ngu, khong phai vao Cai dat bam tay tung
acc.

Sua o HAI cho, thieu mot cho la khong an:
  * chuoi cookie luu trong bang -- de lan sau "Dang nhap voi cookie" van dung
    ngon ngu do;
  * cookies.sqlite trong profile -- de lan mo trinh duyet ke tiep an ngay.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from . import cookies as cookie_module

#: Ma ngon ngu -> ten hien cho nguoi dung.
LANGUAGES = {
    "vi_VN": "Tiếng Việt",
    "en_US": "English (US)",
}

COOKIE_NAME = "locale"
FB_HOST = ".facebook.com"
#: Cookie song mot nam; Facebook tu gia han moi lan vao.
TTL = 365 * 24 * 3600


def current(cookie_text: str) -> str:
    """Ma ngon ngu dang co trong chuoi cookie. Rong neu khong co."""
    try:
        for cookie in cookie_module.parse(cookie_text, default_domain=FB_HOST):
            if cookie.name == COOKIE_NAME:
                return cookie.value
    except cookie_module.CookieError:
        pass
    return ""


def label(code: str) -> str:
    return LANGUAGES.get(code, code or "chưa rõ")


def apply_to_text(cookie_text: str, code: str) -> str:
    """Tra ve chuoi cookie da doi ``locale``, giu nguyen dinh dang goc.

    Chuoi rong thi tra ve rong -- khong tu bia ra cookie cho acc chua co gi.
    """
    raw = (cookie_text or "").strip()
    if not raw:
        return raw
    danh_sach = cookie_module.parse(raw, default_domain=FB_HOST)
    het_han = int(time.time()) + TTL

    thay = False
    for cookie in danh_sach:
        if cookie.name == COOKIE_NAME:
            cookie.value = code
            cookie.expiry = cookie.expiry or het_han
            thay = True
    if not thay:
        danh_sach.append(cookie_module.Cookie(
            name=COOKIE_NAME, value=code, host=FB_HOST, expiry=het_han))

    if raw.startswith("["):
        return cookie_module.to_json(danh_sach)
    # Dang "ten=gia_tri; ten2=gia_tri2" -- giu nguyen kieu do.
    return "; ".join(f"{c.name}={c.value}" for c in danh_sach)


def apply_to_profile(profile_dir: str, code: str) -> bool:
    """Ghi cookie ngon ngu vao profile dang co tren dia. False neu chua co profile."""
    if not os.path.isfile(os.path.join(profile_dir, "cookies.sqlite")):
        return False
    het_han = int(time.time()) + TTL
    cookie = cookie_module.Cookie(name=COOKIE_NAME, value=code, host=FB_HOST,
                                  expiry=het_han)
    try:
        cookie_module.write_to_profile(profile_dir, [cookie], replace_all=False)
    except (cookie_module.CookieError, OSError):
        return False
    return True


def set_language(account, code: str, profile_dir: Optional[str] = None) -> tuple:
    """Doi ngon ngu cho mot acc. Tra ve ``(sua_cookie, sua_profile)``.

    Khong dong/mo trinh duyet: nguoi goi tu quyet khi nao khoi dong lai.
    """
    if code not in LANGUAGES:
        raise ValueError(f"Không hỗ trợ mã ngôn ngữ {code!r}.")
    cu = account.cookie or ""
    moi = apply_to_text(cu, code)
    sua_cookie = moi != cu
    if sua_cookie:
        account.cookie = moi
    sua_profile = apply_to_profile(profile_dir, code) if profile_dir else False
    return sua_cookie, sua_profile

#: Ngon ngu chay dang bai duoc. Chi can dung nhom dau: vi_VN, en_US, en_GB...
SUPPORTED_PREFIXES = ("vi", "en")
#: Ngon ngu doi ve khi acc dang dung thu tieng khac.
FALLBACK = "en_US"


def is_supported(code: str) -> bool:
    """Ngon ngu nay co chay dang bai duoc khong (tieng Viet hoac tieng Anh)."""
    ma = (code or "").strip().lower()
    if not ma:
        return False
    return ma.split("_")[0] in SUPPORTED_PREFIXES


def ensure_supported(account, profile_dir: Optional[str] = None) -> tuple:
    """Acc dang dung tieng khac thi doi ve tieng Anh truoc khi dang.

    Tra ve ``(ma_dang_dung, da_doi)``.

    Vi sao can: giao dien Business Suite bang thu tieng la thi cac buoc dang bai
    khong con giong nhung gi da do. Tieng Viet va tieng Anh la hai thu da chay
    that; con lai doi ve tieng Anh cho chac.

    Acc chua co cookie thi khong dung vao -- khong tu bia cookie cho acc trong.
    """
    ma = current(account.cookie or "")
    if is_supported(ma):
        return ma, False
    if not (account.cookie or "").strip():
        return ma, False
    set_language(account, FALLBACK, profile_dir)
    return FALLBACK, True



# --------------------------------------------------------------------------
# Doi ngon ngu THAT (qua giao dien) — cookie `locale` KHONG du
# --------------------------------------------------------------------------
#: Trang cai dat ngon ngu cua tai khoan.
LANG_URL = "https://www.facebook.com/settings/?tab=language"


def bo_quyen_page(profile_dir: str) -> str:
    """Dua acc VE ACC CA NHAN bang cach bo cookie ``i_user``.

    Facebook dat ``i_user`` khi acc dang "dong vai" mot Page. Dang o quyen Page
    thi trang Cai dat KHONG co muc ngon ngu ca nhan -> khong doi duoc.

    Khong bam nut "chuyen ve ca nhan" vi nut do chi do duoc theo CHU (Viet/Anh):
    acc dang o tieng la (da gap tieng Tay Ban Nha) thi khong do noi. Bo cookie la
    cach KHONG PHU THUOC NGON NGU.

    Tra ve id Page vua thoat ("" neu von da la ca nhan).
    """
    from . import cookies as cookie_module
    try:
        het = cookie_module.read_from_profile(profile_dir)
    except (cookie_module.CookieError, OSError):
        return ""
    co = [c for c in het if c.name == "i_user"]
    if not co:
        return ""
    giu = [c for c in het if c.name != "i_user"]
    try:
        cookie_module.write_to_profile(profile_dir, giu, replace_all=True)
    except (cookie_module.CookieError, OSError):
        return ""
    return co[0].value


def doi_ngon_ngu_that(manager, account, ma: str = FALLBACK, log=None,
                      timeout: float = 180.0) -> dict:
    """Doi ngon ngu THAT cua acc qua giao dien (cookie ``locale`` KHONG du).

    DA DO THAT (25/09): cookie ghi ``vi_VN`` ma giao dien that la ``es`` / ``he``.
    Facebook lay ngon ngu tu CAI DAT TAI KHOAN, khong theo cookie.

    Cac buoc (khop voi anh nguoi dung):
      1. Bo cookie ``i_user`` -> ve acc CA NHAN (dang o quyen Page thi trang Cai
         dat khong co muc ngon ngu ca nhan).
      2. Mo trang Cai dat > Ngon ngu, bam muc "Ngon ngu cua tai khoan".
      3. Go "english" vao o tim roi chon "English (US)".
      4. Tai lai trang de xac minh ``<html lang>``.

    Tra ``{ok, lang, detail, page_da_bo}``. Khong nem.
    """
    from . import fbbusiness
    noi = log or (lambda _m: None)
    profile = manager.profile_dir(account)
    try:
        manager.close(account, wait=8.0)
    except OSError:
        pass

    page = bo_quyen_page(profile)
    if page:
        noi(f"[{account.id}] đang ở quyền Page {page} — đã về acc cá nhân")

    fbbusiness.clear(profile)
    fbbusiness.put_command(profile, action="setlang", ma=ma,
                           langTimeout=int(max(45, timeout / 2)), delay=9000)
    noi(f"[{account.id}] mở cài đặt để đổi ngôn ngữ sang {label(ma)}...")
    manager.launch(account, url=LANG_URL)

    ket = fbbusiness.wait_state(profile, {"lang-done", "lang-failed"}, timeout=timeout,
                                app_dir=fbbusiness.app_dir_cua(manager, account))
    try:
        manager.close(account, wait=15.0)
    except OSError:
        pass

    if not ket:
        return {"ok": False, "lang": "", "detail": "hết giờ chờ đổi ngôn ngữ",
                "page_da_bo": page}
    ok = ket.get("state") == "lang-done"
    chi_tiet = str(ket.get("detail") or "")
    noi(f"[{account.id}] đổi ngôn ngữ: {'OK' if ok else 'HỎNG'} — {chi_tiet[:120]}")
    return {"ok": ok, "lang": ma if ok else "", "detail": chi_tiet, "page_da_bo": page}


def la_loi_ngon_ngu(exc) -> bool:
    """Loi nay co phai "giao dien dang o thu tieng la" khong."""
    from . import fbbusiness
    return fbbusiness.LANG_MARK in str(exc)


def chay_lai_neu_la_ngon_ngu(manager, account, viec, log=None):
    """Chay ``viec()``; gap loi NGON NGU LA thi doi sang tieng Anh roi lam lai MOT lan.

    Cung mo hinh voi ``reauth.chay_lai_neu_logout``.
    """
    try:
        return viec()
    except Exception as exc:  # noqa: BLE001
        if not la_loi_ngon_ngu(exc):
            raise
        kq = doi_ngon_ngu_that(manager, account, log=log)
        if not kq.get("ok"):
            raise RuntimeError(
                f"Giao diện đang ở thứ tiếng lạ và KHÔNG đổi được sang tiếng Anh "
                f"({kq.get('detail')}) — chưa đăng bài.") from exc
        return viec()
