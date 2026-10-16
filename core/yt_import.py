"""Nhap acc YouTube (Gmail): TU NHAN DIEN cac truong trong moi dong.

Dinh dang NGUOI DUNG CHOT — lay tu tool "LVC video slide" (core/firefox_acc.py, tab
Quan ly Firefox), moi dong mot acc, ngan cach "|":

    gmail | pass gmail | 2FA | proxy

Nhan them (tuy chon, dat o dau cung): MAIL KHOI PHUC (email thu hai) va COOKIE Google
(chuoi co "SID=" / "SAPISID=" hoac JSON cookie). Thieu truong duoc.

Luat nhan dien (vi tri + hinh dang) — cung mo hinh core/x_import.py:
- Truong co "@" DAU TIEN = gmail (dinh danh acc, lam id + ten profile);
- Truong KHONG co "@" NGAY SAU gmail = pass gmail (nhan theo VI TRI truoc khi xet 2FA,
  vi pass thuan chu cai cung la base32 hop le);
- Truong co "@" THU HAI = mail khoi phuc; giong khoa TOTP = 2FA; host:port = proxy.

Luu vao Account: id = gmail, password = pass gmail, recovery_mail_backup = mail KP,
extra["gmail_2fa"] = khoa 2FA, proxy, cookie = cookie Google (neu co).
Bi mat (pass, 2FA) KHONG in ra log.

API GIONG core/x_import de dung chung hop thoai nhap hang loat: YtDong co ``loi``,
YT_FIELDS/YT_FIELD_LABEL/YT_FIELD_KEY/YT_MAC_DINH, de_xuat/tach_van_ban/nhap_vao_store.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .store import Account
from .x_import import doan_dau_phan_cach, gon_2fa, la_2fa, la_email

#: Cookie dang nhap Google (nhan ra truong cookie; cung la dau hieu da dang nhap).
GOOGLE_COOKIE_KEYS = ("SID", "SAPISID", "SSID", "HSID", "__Secure-1PSID", "LOGIN_INFO")

_PROXY = re.compile(r"^[\w.\-]+:\d{2,5}(:[^|]*){0,2}$")


def la_cookie_google(s: str) -> bool:
    s = (s or "").strip()
    if s.startswith("[") or s.startswith("{"):
        return any(k in s for k in GOOGLE_COOKIE_KEYS)
    if "=" not in s:
        return False
    return any(re.search(rf"(^|[;\s]){re.escape(k)}=", s) for k in GOOGLE_COOKIE_KEYS)


def la_proxy(s: str) -> bool:
    """host:port hoac host:port:user:pass (khong phai email, khong phai cookie)."""
    s = (s or "").strip()
    if not s or "@" in s or la_cookie_google(s):
        return False
    return bool(_PROXY.match(s))


@dataclass
class YtDong:
    """Mot dong da nhan dien. ``loi`` rong = hop le."""
    goc: str = ""
    gmail: str = ""
    pass_gmail: str = ""
    gmail_2fa: str = ""
    proxy: str = ""
    gmail_kp: str = ""
    cookie: str = ""
    thua: list = field(default_factory=list)
    loi: str = ""

    def to_account(self, group: str = "") -> Account:
        acc = Account(id=self.gmail, password=self.pass_gmail,
                      recovery_mail_backup=self.gmail_kp, cookie=self.cookie,
                      group=group)
        if self.proxy:
            # Account.proxy la DICT (khong phai chuoi) -> phai qua proxy.parse.
            from .proxy import parse as _parse_proxy
            acc.set_proxy(_parse_proxy(self.proxy))
        if self.gmail_2fa:
            acc.extra["gmail_2fa"] = gon_2fa(self.gmail_2fa)
        if self.thua:
            acc.extra["yt_thua"] = "|".join(self.thua)
        return acc


def tach_dong(line: str) -> YtDong:
    """Mot dong -> YtDong (tu nhan dien)."""
    d = YtDong(goc=line)
    s = (line or "").strip()
    if not s or s.startswith("#"):
        d.loi = "dòng trống"
        return d
    sep = "|" if "|" in s else "\t"
    phan = [p.strip() for p in s.split(sep)]
    phan = [p for p in phan if p != ""]
    if not phan:
        d.loi = "dòng trống"
        return d

    sau_gmail = False
    for p in phan:
        if la_cookie_google(p) and not d.cookie:
            d.cookie = p
            continue
        if la_email(p):
            if not d.gmail:
                d.gmail = p
                sau_gmail = True
            elif not d.gmail_kp:
                d.gmail_kp = p
            else:
                d.thua.append(p)
            continue
        if sau_gmail and not d.pass_gmail:
            # Ngay sau gmail LUON la pass (nhan theo VI TRI truoc khi xet 2FA).
            d.pass_gmail = p
            sau_gmail = False
            continue
        if la_proxy(p) and not d.proxy:
            d.proxy = p
            continue
        if la_2fa(p) and not d.gmail_2fa:
            d.gmail_2fa = gon_2fa(p)
            continue
        if not d.pass_gmail:
            d.pass_gmail = p
            continue
        d.thua.append(p)

    if not d.gmail:
        d.loi = "thiếu Gmail (dòng phải có một địa chỉ @)"
    elif not d.pass_gmail:
        d.loi = "thiếu mật khẩu Gmail"
    return d


# --- CHON DINH DANG COT (giong hop Nhap hang loat cua tab Facebook/X) -------------
#: (khoa, nhan) cac cot trai -> phai. Khoa = ten thuoc tinh YtDong.
YT_FIELDS = (
    ("", "(bỏ qua)"),
    ("gmail", "Gmail"),
    ("pass_gmail", "Pass Gmail"),
    ("gmail_2fa", "2FA Gmail"),
    ("proxy", "Proxy"),
    ("gmail_kp", "Mail KP"),
    ("cookie", "Cookie Google"),
)
YT_FIELD_LABEL = dict(YT_FIELDS)
YT_FIELD_KEY = {lbl: k for k, lbl in YT_FIELDS}
#: Thu tu tool "LVC video slide": gmail | pass gmail | 2FA | proxy.
YT_MAC_DINH = ["gmail", "pass_gmail", "gmail_2fa", "proxy"]


def tach_dong_theo(line: str, sep: str, fields: list) -> YtDong:
    """Tach theo DUNG COT nguoi dung khai (khong doan)."""
    d = YtDong(goc=line)
    s = (line or "").strip()
    if not s or s.startswith("#"):
        d.loi = "dòng trống"
        return d
    o = [p.strip() for p in s.split(sep or "|")]
    for i, khoa in enumerate(fields or []):
        if not khoa or i >= len(o) or not o[i]:
            continue
        gt = gon_2fa(o[i]) if khoa == "gmail_2fa" else o[i]
        setattr(d, khoa, gt)
    if not d.gmail:
        d.loi = "thiếu Gmail"
    elif not d.pass_gmail:
        d.loi = "thiếu mật khẩu Gmail"
    return d


def tach_van_ban(text: str, sep: str = "", fields=None) -> list:
    """Ca khoi -> [YtDong] (bo dong rong/ghi chu)."""
    ra = []
    for dong in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not dong.strip() or dong.strip().startswith("#"):
            continue
        ra.append(tach_dong_theo(dong, sep, fields) if fields else tach_dong(dong))
    return ra


def de_xuat(text: str, so_cot: int = 8) -> tuple:
    """Doan (dau phan cach, ten tung cot) tu dong dau — cho nut 'Tự đề xuất'."""
    sep = doan_dau_phan_cach(text)
    mau = ""
    for dong in (text or "").splitlines():
        if dong.strip() and not dong.strip().startswith("#"):
            mau = dong
            break
    cot = [""] * so_cot
    if not mau:
        return sep, (YT_MAC_DINH + [""] * so_cot)[:so_cot]
    d = tach_dong(mau)
    nhan = {}
    for khoa in ("gmail", "pass_gmail", "gmail_2fa", "proxy", "gmail_kp", "cookie"):
        gt = getattr(d, khoa)
        if gt:
            nhan[gt] = khoa
    o = [p.strip() for p in mau.split(sep or "|")]
    co_doan = False
    for i, gt in enumerate(o):
        if i >= so_cot:
            break
        khoa = nhan.get(gt.strip()) or nhan.get(gon_2fa(gt.strip()), "")
        cot[i] = khoa
        co_doan = co_doan or bool(khoa)
    if not co_doan:
        return sep, (YT_MAC_DINH + [""] * so_cot)[:so_cot]
    return sep, cot


def nhap_vao_store(store, text: str, group: str = "", *, sep: str = "", fields=None,
                   ua_loai=None) -> tuple:
    """Nhap vao kho acc. Tra (so acc them, [cau loi])."""
    them, loi = 0, []
    for i, d in enumerate(tach_van_ban(text, sep, fields), start=1):
        if d.loi:
            loi.append(f"dòng {i}: {d.loi}")
            continue
        if store.get(d.gmail):
            loi.append(f"dòng {i}: {d.gmail} đã có trong danh sách")
            continue
        acc = d.to_account(group)
        if ua_loai:
            from . import useragent
            ua = useragent.chon_theo_cac_loai(ua_loai)
            if ua:
                acc.extra["user_agent"] = ua
        store.add(acc)
        them += 1
    if them:
        store.save()
    return them, loi
