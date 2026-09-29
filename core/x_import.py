"""Nhap acc X.com: TU NHAN DIEN cac truong trong moi dong.

Dinh dang nguoi dung dua (ngan cach "|", thu tu co the thieu truong):
    user X | pass X | gmail | pass gmail | mail khoi phuc cua gmail | 2FA cua gmail
    user X | pass X | gmail | pass gmail | 2FA
Them: truong cookie X (chua "auth_token=" / "ct0=" hoac JSON cookie) nam o dau cung duoc.

Luat nhan dien (vi tri + hinh dang):
- 2 truong dau LUON la user X + pass X (user bo "@" dau neu co).
- Truong co "@" dau tien = gmail; truong KHONG co "@" ngay sau no = pass gmail;
  truong co "@" thu hai = mail khoi phuc cua gmail.
- Truong giong khoa TOTP (base32, bo khoang trang) = 2FA cua gmail. Pass thuan chu cai
  cung la base32 hop le -> chi coi la 2FA khi co nhom 4 ky tu cach nhau, hoac co so 2-7
  va do dai >= 16. Pass gmail da nhan theo VI TRI truoc nen khong bi nham.

Luu vao Account: id=user, password=pass X, recovery_mail=gmail,
recovery_mail_password=pass gmail, recovery_mail_backup=mail KP cua gmail,
extra["gmail_2fa"]=2FA cua gmail, cookie=cookie X.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .store import Account

_EMAIL = re.compile(r"^[^@\s|]+@[^@\s|]+\.[^@\s|]+$")
_B32 = re.compile(r"^[A-Z2-7]+=*$")
_COOKIE_KEYS = ("auth_token", "ct0", "twid", "guest_id")


def la_email(s: str) -> bool:
    return bool(_EMAIL.match(s.strip()))


def la_2fa(s: str) -> bool:
    """Khoa TOTP: base32 >= 16 ky tu; co nhom 4 ky tu cach nhau HOAC co so 2-7."""
    s = s.strip()
    gon = s.replace(" ", "").upper()
    if len(gon) < 16 or not _B32.match(gon):
        return False
    nhom = s.split()
    if len(nhom) >= 4 and all(len(n) == 4 for n in nhom[:-1]):
        return True
    return bool(re.search(r"[2-7]", gon))


def la_cookie(s: str) -> bool:
    s = s.strip()
    if s.startswith("[") or s.startswith("{"):
        return any(k in s for k in _COOKIE_KEYS)
    return "=" in s and any(re.search(rf"(^|[;\s]){k}=", s) for k in _COOKIE_KEYS)


def gon_2fa(s: str) -> str:
    return s.replace(" ", "").upper()


@dataclass
class XDong:
    """Mot dong da nhan dien. ``loi`` rong = hop le."""
    goc: str = ""
    user: str = ""
    pass_x: str = ""
    gmail: str = ""
    pass_gmail: str = ""
    gmail_kp: str = ""
    gmail_2fa: str = ""
    cookie: str = ""
    thua: list = field(default_factory=list)   # truong khong nhan ra
    loi: str = ""

    def to_account(self, group: str = "") -> Account:
        acc = Account(id=self.user, password=self.pass_x, recovery_mail=self.gmail,
                      recovery_mail_password=self.pass_gmail,
                      recovery_mail_backup=self.gmail_kp, cookie=self.cookie,
                      group=group)
        if self.gmail_2fa:
            acc.extra["gmail_2fa"] = self.gmail_2fa
        if self.thua:
            acc.extra["x_thua"] = "|".join(self.thua)
        return acc


def tach_dong(line: str) -> XDong:
    d = XDong(goc=line)
    sep = "|" if "|" in line else "\t"
    parts = [p.strip() for p in line.split(sep)]
    parts = [p for p in parts if p != ""]
    if not parts:
        d.loi = "dòng trống"
        return d
    d.user = parts[0].lstrip("@")
    if not d.user or la_email(parts[0]) or " " in d.user:
        d.loi = "trường đầu phải là user X"
        return d
    rest = parts[1:]
    if rest and not la_email(rest[0]) and not la_cookie(rest[0]):
        d.pass_x = rest.pop(0)
    so_email = 0
    i = 0
    while i < len(rest):
        p = rest[i]
        if la_cookie(p) and not d.cookie:
            d.cookie = p
        elif la_email(p):
            so_email += 1
            if not d.gmail:
                d.gmail = p
                # truong ngay sau gmail (khong phai email/cookie) = pass gmail, theo VI TRI
                if i + 1 < len(rest) and not la_email(rest[i + 1]) and not la_cookie(rest[i + 1]):
                    d.pass_gmail = rest[i + 1]
                    i += 1
            elif not d.gmail_kp:
                d.gmail_kp = p
            else:
                d.thua.append(p)
        elif la_2fa(p) and not d.gmail_2fa:
            d.gmail_2fa = gon_2fa(p)
        else:
            d.thua.append(p)
        i += 1
    if not d.pass_x:
        d.loi = "thiếu pass X"
    return d


# --- CHON DINH DANG COT (giong hop Nhap hang loat cua tab Facebook) ---------------
#: (khoa, nhan) cac cot nguoi dung chon trai -> phai. Khoa = ten thuoc tinh XDong.
X_FIELDS = (
    ("", "(bỏ qua)"),
    ("user", "User X"),
    ("pass_x", "Pass X"),
    ("gmail", "Gmail"),
    ("pass_gmail", "Pass Gmail"),
    ("gmail_kp", "Mail KP Gmail"),
    ("gmail_2fa", "2FA Gmail"),
    ("cookie", "Cookie X"),
)
X_FIELD_LABEL = dict(X_FIELDS)
X_FIELD_KEY = {lbl: k for k, lbl in X_FIELDS}
X_MAC_DINH = ["user", "pass_x", "gmail", "pass_gmail", "gmail_kp", "gmail_2fa"]
_SEPS = ("|", "\t", ";", ",")


def _dong_that(text: str) -> list[str]:
    return [r.strip() for r in (text or "").splitlines()
            if r.strip() and not r.strip().startswith("#")]


def doan_dau_phan_cach(text: str) -> str:
    """Dau phan cach xuat hien nhieu nhat o cac dong dau (mac dinh "|")."""
    dong = _dong_that(text)[:20]
    if not dong:
        return "|"
    diem = {s: sum(line.count(s) for line in dong) for s in _SEPS}
    tot = max(_SEPS, key=lambda s: diem[s])
    return tot if diem[tot] else "|"


def de_xuat(text: str, so_cot: int = 8) -> tuple[str, list[str]]:
    """TU DE XUAT dinh dang cot: (dau phan cach, [khoa tung cot]). THUAN.

    Lay dong dau hop le, nhan dien bang tach_dong (theo hinh dang) roi doi chieu tung
    o ve truong tuong ung. Khong co dong nao -> dinh dang mac dinh.
    """
    sep = doan_dau_phan_cach(text)
    fields = [""] * so_cot
    for line in _dong_that(text)[:20]:
        d = tach_dong(line.replace(sep, "|") if sep != "|" else line)
        if d.loi:
            continue
        parts = [p.strip() for p in line.split(sep)]
        gia_tri = {"user": d.user, "pass_x": d.pass_x, "gmail": d.gmail,
                   "pass_gmail": d.pass_gmail, "gmail_kp": d.gmail_kp, "cookie": d.cookie}
        for i, p in enumerate(parts[:so_cot]):
            if not p:
                continue
            for k, v in gia_tri.items():
                if v and (p == v or p.lstrip("@") == v) and k not in fields:
                    fields[i] = k
                    break
            else:
                if d.gmail_2fa and gon_2fa(p) == d.gmail_2fa and "gmail_2fa" not in fields:
                    fields[i] = "gmail_2fa"
        return sep, fields
    return sep, (X_MAC_DINH + [""] * so_cot)[:so_cot]


def tach_dong_theo(line: str, sep: str, fields: list) -> XDong:
    """Tach mot dong THEO DINH DANG COT nguoi dung chon (khong doan). THUAN."""
    d = XDong(goc=line)
    parts = [p.strip() for p in line.split(sep)]
    for i, k in enumerate(fields):
        if not k or i >= len(parts) or not parts[i]:
            continue
        v = parts[i]
        if k == "user":
            v = v.lstrip("@")
        elif k == "gmail_2fa":
            v = gon_2fa(v)
        setattr(d, k, v)
    d.thua = [p for i, p in enumerate(parts) if p and (i >= len(fields) or not fields[i])]
    if not d.user or " " in d.user or la_email(d.user):
        d.loi = "thiếu / sai cột User X"
    elif not d.pass_x:
        d.loi = "thiếu pass X"
    return d


def tach_van_ban(text: str, sep: str = "", fields=None) -> list[XDong]:
    """Moi dong khong trong -> XDong (bo dong bat dau bang '#').

    Co ``fields`` -> tach THEO DINH DANG COT; khong -> tu nhan dien tung dong.
    """
    out = []
    for line in _dong_that(text):
        out.append(tach_dong_theo(line, sep or "|", fields) if fields else tach_dong(line))
    return out


def nhap_vao_store(store, text: str, group: str = "", *, sep: str = "", fields=None,
                   ua_loai=None) -> tuple[int, list[str]]:
    """Them acc moi vao store (bo qua trung ID / dong loi). Tra (so them, danh sach loi).

    ``ua_loai``: category User Agent da tich -> moi acc MOI gan 1 UA ngau nhien (nhu Facebook).
    """
    added, errors = 0, []
    co = {a.id.lower() for a in store.accounts}
    ua_loai = [x for x in (ua_loai or []) if x]
    for d in tach_van_ban(text, sep, fields):
        if d.loi:
            errors.append(f"{d.goc[:40]} — {d.loi}")
            continue
        if d.user.lower() in co:
            errors.append(f"{d.user} — đã có trong danh sách")
            continue
        acc = d.to_account(group)
        if ua_loai:
            from . import useragent
            ua = useragent.chon_theo_cac_loai(ua_loai)
            if ua:
                acc.extra["user_agent"] = ua
        acc.created_at = __import__("time").strftime("%Y-%m-%d %H:%M")
        store.accounts.append(acc)
        co.add(d.user.lower())
        added += 1
    if group and group not in store.group_names:
        store.group_names.append(group)
    if added or group:
        store.save()
    return added, errors
