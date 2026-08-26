"""Tu do dinh dang khi nhap hang loat: doan dau phan cach + tung cot la truong gi.

Muc tieu: dan danh sach acc vao la tool tu doan Uid / Pass / 2FA / Proxy / Email /
Cookie / Token ... Cai nao khong chac thi de trong (khoa "") cho nguoi dung chon.

Khoa tra ve khop voi IMPORT_FIELDS trong ui/dialogs.py:
  id, password, cookie, proxy, twofa, recovery_mail, note, group,
  va cac truong phu tien to "x:": x:token, x:email, x:pass_email, x:phone,
  x:user_agent, x:fb_name, x:dob, x:gender, x:friends, x:fb_groups,
  x:recovery_mail_pass
"""

from __future__ import annotations

import re

SEPARATORS = ["|", "\t", ";", ","]

_RE_DIGITS = re.compile(r"\d+")
_RE_UID = re.compile(r"^\d{13,20}$")
_RE_PHONE = re.compile(r"^\+?\d[\d\s\-]{7,13}$")
_RE_PROXY = re.compile(r"^[\w.\-]+:\d{2,5}(?::[^:]+:[^:]+)?$")
_RE_DATE = re.compile(r"^\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}$")
_RE_2FA_PLAIN = re.compile(r"^[A-Z2-7]{16}$|^[A-Z2-7]{26}$|^[A-Z2-7]{32}$")
_RE_2FA_SPACED = re.compile(r"^(?:[A-Z2-7]{4}\s){3,7}[A-Z2-7]{4}$")
# Chi nhan token gioi tinh ro rang (tieng Anh) de tranh nham voi tu tieng Viet
# thuong gap nhu "nam", "khac" -> se de nguoi dung tu chon cot gioi tinh.
_GENDERS = {"male", "female"}


def clean_lines(text: str) -> list[str]:
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def detect_separator(lines: list[str]) -> str:
    """Chon dau phan cach: uu tien cai co mat o MOI dong, roi den cai tach nhieu nhat."""
    if not lines:
        return "|"
    for sep in SEPARATORS:
        if all(sep in line for line in lines):
            return sep
    best, best_total = "|", 0
    for sep in SEPARATORS:
        total = sum(line.count(sep) for line in lines)
        if total > best_total:
            best, best_total = sep, total
    return best


def guess_value(value: str) -> str:
    """Doan mot o la truong gi. Tra ve khoa, hoac "" neu khong chac."""
    v = (value or "").strip()
    if not v:
        return ""
    low = v.lower()

    # UserAgent
    if "mozilla/" in low or "applewebkit" in low or "gecko/" in low:
        return "x:user_agent"
    # Cookie Facebook: co nhieu cap ten=gia_tri ngan cach bang ';'
    if "c_user=" in low or "xs=" in low or (v.count("=") >= 2 and ";" in v):
        return "cookie"
    # Access token Facebook
    if v.startswith(("EAA", "EAAB", "EAAG")) and len(v) > 40:
        return "x:token"
    # Email
    if "@" in v and "." in v.rsplit("@", 1)[-1]:
        return "email"  # phan biet email chinh / khoi phuc o buoc gom cot
    # Proxy host:port[:user:pass] (phan host phai co dau cham)
    if _RE_PROXY.match(v) and "." in v.split(":", 1)[0]:
        return "proxy"
    # Ngay sinh
    if _RE_DATE.match(v):
        return "x:dob"
    # Gioi tinh
    if low in _GENDERS:
        return "x:gender"
    # 2FA (base32 hoa toan, khong dau cham)
    if _RE_2FA_PLAIN.match(v) or _RE_2FA_SPACED.match(v):
        return "twofa"
    # UID Facebook: rat dai toan so
    if _RE_UID.match(v):
        return "id"
    # So dien thoai
    digits = re.sub(r"\D", "", v)
    if _RE_PHONE.match(v) and 9 <= len(digits) <= 12 and (digits.startswith("0") or v.startswith("+")):
        return "x:phone"
    return ""  # khong chac -> co the la mat khau, de nguoi dung quyet


def _column_vote(values: list[str]) -> str:
    nonempty = [v for v in values if v.strip()]
    if not nonempty:
        return ""
    votes: dict[str, int] = {}
    for value in nonempty:
        guess = guess_value(value)
        if guess:
            votes[guess] = votes.get(guess, 0) + 1
    if not votes:
        return ""
    winner = max(votes, key=lambda k: votes[k])
    # Chi nhan khi it nhat mot nua so o co du lieu deu cung loai -> tranh mot o
    # le (vi du dung chu "male") lam sai ca cot.
    if votes[winner] * 2 >= len(nonempty):
        return winner
    return ""


def detect_fields(lines: list[str], separator: str, max_cols: int) -> list[str]:
    """Doan y nghia tung cot dua tren cac dong mau."""
    rows = [[p.strip() for p in line.split(separator)] for line in lines[:50]]
    ncols = min(max(((len(r) for r in rows)), default=0), max_cols)

    fields = [""] * max_cols
    email_seen = 0
    id_col = -1
    for col in range(ncols):
        column_values = [r[col] for r in rows if col < len(r)]
        guess = _column_vote(column_values)

        if guess == "email":
            # Email dau tien la email chinh, cai sau la mail khoi phuc.
            guess = "x:email" if email_seen == 0 else "recovery_mail"
            email_seen += 1
        if guess == "id":
            id_col = col
        fields[col] = guess

    # Cot ngay sau UID ma chua doan ra thi rat co the la mat khau.
    if id_col >= 0 and id_col + 1 < ncols and not fields[id_col + 1]:
        # chi gan khi o do co du lieu ngan gon (khong phai o trong)
        sample = [r[id_col + 1] for r in rows if id_col + 1 < len(r) and r[id_col + 1]]
        if sample:
            fields[id_col + 1] = "password"

    return fields


def detect(text: str, max_cols: int = 10) -> tuple[str, list[str]]:
    """Tra ve (dau_phan_cach, danh_sach_khoa_cot)."""
    lines = clean_lines(text)
    if not lines:
        return "|", [""] * max_cols
    sep = detect_separator(lines)
    return sep, detect_fields(lines, sep, max_cols)


def parse_rows(text: str, separator: str, fields: list[str], limit: int = 300) -> list[list[str]]:
    """Cat input thanh cac dong x cot theo dung so cot dang chon (de xem truoc)."""
    active = [i for i, key in enumerate(fields) if key]
    rows = []
    for line in clean_lines(text)[:limit]:
        parts = [p.strip() for p in line.split(separator)]
        rows.append([parts[i] if i < len(parts) else "" for i in active])
    return rows
