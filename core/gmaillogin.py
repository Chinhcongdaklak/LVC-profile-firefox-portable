"""Dang nhap GMAIL (tai khoan Google) cho acc YouTube -> luu cookie Google.

Cung khuon core/xlogin.py (da chay that): mo Firefox profile BINH THUONG (khong cong
debug), agent process-script core/assets/gmail_agent.js dien email/pass/2FA, cha (ham
nay) dieu phoi roi XAC MINH bang cookie THAT doc tu cookies.sqlite — khong tin agent doan.

Thu tu buoc lay tu tool "LVC video slide" (core/firefox_login.dien_form_google):
    accounts.google.com -> email -> Next -> mat khau -> Next -> 2FA (TOTP) -> vao.

Du lieu acc YouTube (core/yt_import): id = GMAIL, password = PASS GMAIL,
recovery_mail_backup = mail khoi phuc, extra["gmail_2fa"] = khoa TOTP.

Ham THUAN (cookie_google, danh_gia) tach rieng de test khong can trinh duyet.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from . import cookies as cookies_module
from . import totp

CMD_NAME = "qlfp-gmail.json"
RESULT_NAME = "qlfp-gmail-result.json"

#: Vao thang trang dang nhap Google cho YouTube (giong URL_DANG_NHAP cua tool slide).
GOOGLE_LOGIN_URL = "https://accounts.google.com/ServiceLogin?service=youtube"
YOUTUBE_URL = "https://www.youtube.com/"

#: Host cookie tinh la "cua Google/YouTube".
_HOSTS = ("google.com", "youtube.com", "google.com.vn")
#: Co MOT trong cac cookie nay = da dang nhap that su.
COOKIE_DANG_NHAP = ("SID", "__Secure-1PSID", "SAPISID", "__Secure-3PSID")

VAO = "vao"
SAI_PASS = "sai_pass_gmail"
SAI_2FA = "sai_2fa"
BI_CHAN = "google_chan"
CAN_XAC_MINH = "can_xac_minh"
KHOA = "acc_khoa"
THIEU = "thieu_thong_tin"
KHONG_VAO = "khong_vao"
KHONG_RO = "khong_ro"

MAX_SONG_SONG = 8


# --- ham THUAN --------------------------------------------------------------

def _thuoc_google(host: str) -> bool:
    host = (host or "").lstrip(".").lower()
    return any(host == h or host.endswith("." + h) for h in _HOSTS)


def cookie_google(cookies: list) -> str:
    """Ghep cookie Google thanh chuoi "name=value; ...".

    Tra RONG neu khong co cookie dang nhap (SID/SAPISID...) -> chua vao that su.
    """
    lay = [c for c in cookies if _thuoc_google(getattr(c, "host", ""))]
    if not any(c.name in COOKIE_DANG_NHAP and c.value for c in lay):
        return ""
    theo_ten: dict = {}
    for c in lay:
        if c.value:
            theo_ten[c.name] = c.value
    return "; ".join(f"{k}={v}" for k, v in theo_ten.items())


def danh_gia(states: set, co_cookie: bool, het_gio: bool) -> Optional[str]:
    """Ket luan tu tap trang thai agent. None = chua ket luan. THUAN."""
    if co_cookie or "gmail-in" in states:
        return VAO
    if "g-wrong-pass" in states:
        return SAI_PASS
    if "g-wrong-code" in states:
        return SAI_2FA
    if "g-disabled" in states:
        return KHOA
    if "g-rejected" in states:
        return BI_CHAN
    if "g-verify-phone" in states:
        return CAN_XAC_MINH
    if het_gio:
        if "g-email-filled" in states or "g-pass-filled" in states:
            return KHONG_VAO
        return KHONG_RO
    return None


# --- dieu phoi (can trinh duyet) --------------------------------------------

def _clear(profile_dir: str) -> None:
    for n in (CMD_NAME, RESULT_NAME):
        try:
            os.remove(os.path.join(profile_dir, n))
        except OSError:
            pass


def _put_cmd(profile_dir: str, account, code: str) -> None:
    cmd = {
        "action": "gmail",
        "gmail": (account.id or "").strip(),
        "pass_gmail": account.password or "",
        "mail_kp": (getattr(account, "recovery_mail_backup", "") or "").strip(),
        "code": code or "",
        "code_at": time.time(),
        "delay": 1500,
        "timeout": 240000,
    }
    os.makedirs(profile_dir, exist_ok=True)
    with open(os.path.join(profile_dir, CMD_NAME), "w", encoding="utf-8") as fh:
        json.dump(cmd, fh, ensure_ascii=False)


def _read_result(profile_dir: str) -> Optional[dict]:
    try:
        with open(os.path.join(profile_dir, RESULT_NAME), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _doc_cookie(manager, account) -> str:
    try:
        ck = cookies_module.read_from_profile(manager.profile_dir(account))
    except Exception:  # noqa: BLE001
        return ""
    return cookie_google(ck)


def login_gmail(manager, account, *, timeout: float = 240.0,
                log: Optional[Callable[[str], None]] = None) -> dict:
    """Dang nhap Gmail cho MOT acc. Tra {ok, status, detail, cookie}. Khong nem."""
    noi = log or (lambda _m: None)
    gmail = (account.id or "").strip()
    mat_khau = (account.password or "").strip()
    if not gmail or not mat_khau:
        return {"ok": False, "status": THIEU,
                "detail": "Thiếu Gmail hoặc mật khẩu Gmail.", "cookie": ""}

    if not manager.is_installed(account):
        noi(f"[{gmail}] chưa có profile — tạo...")
        manager.create(account)

    profile = manager.profile_dir(account)
    manager.close(account, wait=8.0)
    manager.configure(account)          # trien khai/lam moi agent vao profile
    _clear(profile)

    twofa = ((getattr(account, "extra", {}) or {}).get("gmail_2fa") or "").strip()
    _put_cmd(profile, account, totp.generate(twofa) if twofa else "")

    noi(f"[{gmail}] mở Firefox → accounts.google.com → đăng nhập...")
    manager.launch(account, url=GOOGLE_LOGIN_URL)

    states: set = set()
    _seen: set = set()
    last_code_at = 0.0
    deadline = time.time() + timeout
    status = None
    try:
        while time.time() < deadline:
            r = _read_result(profile)
            if r:
                st = r.get("state")
                det = "" if r.get("detail") is None else str(r.get("detail"))
                if st == "seen":
                    key = "seen|" + det
                    if key not in _seen:
                        _seen.add(key)
                        noi(f"[{gmail}] seen: {det[:160]}")
                elif st and st not in states:
                    states.add(st)
                    noi(f"[{gmail}] {st}" + (f": {det[:120]}" if det else ""))
                # Agent ghi DE len cung mot file; poll 1 giay/lan la BO LO trang thai
                # (da mac that 05/10: khong thay g-pass-filled du agent co dien).
                # Nhat ky kem theo giu lai moi buoc -> gom tu day cho chac.
                for dong in (r.get("log") or []):
                    ten = str(dong).split(":", 1)[0].strip()
                    if ten and ten != "seen" and ten not in states:
                        states.add(ten)
                        noi(f"[{gmail}] {ten} (nhật ký agent)")
            if "gmail-in" in states:
                break
            status = danh_gia(states, co_cookie=False, het_gio=False)
            if status:
                break
            if twofa and (time.time() - last_code_at) >= 5.0:
                _put_cmd(profile, account, totp.generate(twofa))
                last_code_at = time.time()
            time.sleep(1.0)
    finally:
        try:
            manager.close(account, wait=10.0)
        except OSError:
            pass

    cookie = _doc_cookie(manager, account)
    co_cookie = bool(cookie)
    if status is None:
        status = danh_gia(states, co_cookie, het_gio=True) or (VAO if co_cookie else KHONG_RO)
    elif co_cookie:
        status = VAO
    _clear(profile)

    ok = status == VAO and co_cookie
    if ok:
        account.cookie = cookie
        account.cookie_ok = time.strftime("%Y-%m-%d %H:%M")
        account.status = "Live"
        noi(f"[{gmail}] đã lưu cookie Google ({len(cookie)} ký tự).")

    detail = {
        VAO: "đăng nhập thành công",
        SAI_PASS: "sai mật khẩu Gmail",
        SAI_2FA: "mã 2FA sai",
        BI_CHAN: "Google chặn đăng nhập trên trình duyệt này",
        CAN_XAC_MINH: "Google đòi xác minh (SĐT/thiết bị) — làm tay 1 lần rồi chạy lại",
        KHOA: "tài khoản Google bị vô hiệu hoá",
        THIEU: "thiếu Gmail hoặc mật khẩu",
        KHONG_VAO: "đã điền nhưng chưa vào được",
        KHONG_RO: "không rõ kết quả (hết giờ)",
    }.get(status, status or "")
    noi(f"[{gmail}] KẾT QUẢ: {status} — {detail}")
    return {"ok": ok, "status": status, "detail": detail, "cookie": cookie}


def login_nhieu(manager, accounts, *, workers: int = 2,
                log: Optional[Callable[[str], None]] = None,
                on_xong: Optional[Callable[[object, dict], None]] = None) -> dict:
    """Dang nhap Gmail cho nhieu acc song song (moi acc 1 Firefox rieng)."""
    noi = log or (lambda _m: None)
    n = max(1, min(int(workers or 1), MAX_SONG_SONG))
    vao, khong = [], []

    def mot(acc):
        kq = login_gmail(manager, acc, log=noi)
        if on_xong:
            try:
                on_xong(acc, kq)
            except Exception:  # noqa: BLE001
                pass
        return acc, kq

    with ThreadPoolExecutor(max_workers=n) as ex:
        for acc, kq in ex.map(mot, list(accounts)):
            (vao if kq.get("ok") else khong).append(acc.id)
    noi(f"đăng nhập Gmail {len(vao)}/{len(accounts)} acc (song song {n} luồng).")
    return {"vao": vao, "khong": khong, "so": len(accounts)}
