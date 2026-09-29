"""Dang nhap X.com qua "Dang nhap bang Google" -> lay cookie X moi.

Cung khuon voi core/fblogin.py (ADR-011): mo Firefox profile BINH THUONG (khong
cong debug), mot agent process-script (core/assets/xlogin_agent.js) dien thong tin
Google giup, cha (ham nay) dieu phoi + xac minh + doc cookie.

Du lieu acc X (core/x_import):
  id=user X, password=pass X, recovery_mail=GMAIL, recovery_mail_password=PASS GMAIL,
  recovery_mail_backup=mail khoi phuc CUA gmail, extra["gmail_2fa"]=khoa TOTP (base32).

Ham THUAN (danh_gia, cookie_x) tach rieng de test khong can trinh duyet.
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from . import cookies as cookies_module
from . import nordvpn
from . import totp

CMD_NAME = "qlfp-xlogin.json"
RESULT_NAME = "qlfp-xlogin-result.json"
X_LOGIN_URL = "https://x.com/i/flow/login"
X_HOME_URL = "https://x.com/home"

# Cac host cookie thuoc X (X doi ten tu Twitter, con dung ca hai mien).
_X_HOSTS = (".x.com", "x.com", ".twitter.com", "twitter.com")

VAO = "vao"                         # dang nhap thanh cong (co auth_token)
SAI_PASS = "sai_pass_gmail"         # Google bao sai mat khau
SAI_2FA = "sai_2fa"                 # ma 2FA sai lap lai
BI_CHAN = "google_chan"            # Google chan trinh duyet / khong dang nhap duoc
CAN_XAC_MINH = "can_xac_minh"       # Google doi xac minh SDT/thiet bi
X_KHOA = "x_khoa"                   # X khoa/treo tai khoan
THIEU = "thieu_thong_tin"
KHONG_VAO = "khong_vao"
KHONG_RO = "khong_ro"
VPN_LOI = "vpn_chua_noi"             # co NordVPN ma VPN chua noi -> khong vao X

MAX_SONG_SONG = 8

# --- ham THUAN --------------------------------------------------------------

def cookie_x(cookies: list) -> str:
    """Ghep cookie thuoc mien X thanh chuoi header "name=value; ...".

    Tra rong neu khong co ``auth_token`` (chua dang nhap that su).
    """
    lay = [c for c in cookies if _thuoc_x(getattr(c, "host", ""))]
    if not any(c.name == "auth_token" and c.value for c in lay):
        return ""
    # Bo trung ten (giu ban cuoi), giu thu tu on dinh.
    theo_ten: dict = {}
    for c in lay:
        if c.value:
            theo_ten[c.name] = c.value
    return "; ".join(f"{k}={v}" for k, v in theo_ten.items())


def _thuoc_x(host: str) -> bool:
    host = (host or "").lstrip(".").lower()
    return host == "x.com" or host.endswith(".x.com") \
        or host == "twitter.com" or host.endswith(".twitter.com")


def danh_gia(states: set, co_auth_token: bool, het_gio: bool) -> Optional[str]:
    """Ket luan tu tap trang thai agent + co cookie auth_token chua + het gio.

    Tra None = chua ket luan (cho tiep). THUAN: test khong can trinh duyet.
    """
    if co_auth_token or "x-logged-in" in states:
        return VAO
    if "g-wrong-pass" in states:
        return SAI_PASS
    if "g-wrong-code" in states:
        return SAI_2FA
    if "g-rejected" in states:
        return BI_CHAN
    if "x-locked" in states:
        return X_KHOA
    if "g-verify-phone" in states:
        return CAN_XAC_MINH
    if het_gio:
        if "g-email-filled" in states or "g-pass-filled" in states \
                or "x-google-clicked" in states:
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
    extra = getattr(account, "extra", {}) or {}
    cmd = {
        "action": "xlogin",
        "gmail": (account.recovery_mail or "").strip(),
        "pass_gmail": account.recovery_mail_password or "",
        "gmail_kp": (account.recovery_mail_backup or "").strip(),
        "user_x": account.id or "",
        "pass_x": account.password or "",
        "code": code or "",
        "code_at": time.time(),
        "formTimeout": 45000,
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


def _doc_cookie_x(manager, account) -> str:
    """Doc cookies.sqlite cua profile -> chuoi cookie X (rong neu chua co auth_token)."""
    try:
        ck = cookies_module.read_from_profile(manager.profile_dir(account))
    except Exception:  # noqa: BLE001
        return ""
    return cookie_x(ck)


def login_google(manager, account, *, timeout: float = 240.0,
                 log: Optional[Callable[[str], None]] = None) -> dict:
    """Dang nhap X qua Google cho MOT acc. Tra {ok, status, detail, cookie}.

    Khong nem (tru khi thieu thong tin bat buoc, van tra dict THIEU).
    """
    noi = log or (lambda _m: None)
    gmail = (account.recovery_mail or "").strip()
    pass_gmail = (account.recovery_mail_password or "").strip()
    if not gmail or not pass_gmail:
        return {"ok": False, "status": THIEU,
                "detail": "Thiếu Gmail hoặc Pass Gmail.", "cookie": ""}

    # Tao profile neu chua co (giong cac luong khac: tu tao roi chay).
    if not manager.is_installed(account):
        noi(f"[{account.id}] chưa có profile — tạo...")
        manager.create(account)

    profile = manager.profile_dir(account)
    manager.close(account, wait=8.0)
    manager.configure(account)          # trien khai/lam moi agent vao profile
    try:
        manager.clear_login_probe(account)
    except Exception:  # noqa: BLE001
        pass
    _clear(profile)

    twofa = ((getattr(account, "extra", {}) or {}).get("gmail_2fa") or "").strip()
    _put_cmd(profile, account, totp.generate(twofa) if twofa else "")

    noi(f"[{account.id}] mở Firefox → x.com → đăng nhập bằng Google...")
    # Kiem VPN TRUOC (acc co NordVPN): chua noi thi KHONG vao X bang IP that.
    cong = nordvpn.mo_qua_cong_vpn(manager, account, X_LOGIN_URL, log=noi)
    if not cong["ok"]:
        _clear(profile)
        return {"ok": False, "status": VPN_LOI, "detail": cong["detail"], "cookie": ""}

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
                        noi(f"[{account.id}] seen: {det[:150]}")
                elif st and st not in states:
                    states.add(st)
                    noi(f"[{account.id}] {st}" + (f": {det[:60]}" if det else ""))
                if st == "g-captcha":
                    # Cho nguoi dung giai tay -> gia han.
                    deadline = max(deadline, time.time() + 90.0)
            # Neu agent bao da vao, xac nhan bang cookie that (auth_token).
            if "x-logged-in" in states:
                break
            status = danh_gia(states, co_auth_token=False, het_gio=False)
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

    cookie = _doc_cookie_x(manager, account)
    co_auth = bool(cookie)
    if status is None:
        status = danh_gia(states, co_auth, het_gio=True) or (VAO if co_auth else KHONG_RO)
    elif co_auth:
        status = VAO
    _clear(profile)

    ok = status == VAO and co_auth
    if ok:
        account.cookie = cookie
        account.cookie_ok = time.strftime("%Y-%m-%d %H:%M")
        account.status = "Live"
        noi(f"[{account.id}] đã lưu cookie X mới ({len(cookie)} ký tự).")

    detail = {
        VAO: "đăng nhập thành công",
        SAI_PASS: "sai mật khẩu Gmail",
        SAI_2FA: "mã 2FA Gmail sai",
        BI_CHAN: "Google chặn đăng nhập trên trình duyệt này",
        CAN_XAC_MINH: "Google đòi xác minh (SĐT/thiết bị) — làm tay 1 lần",
        X_KHOA: "tài khoản X bị khoá/treo",
        KHONG_VAO: "đã thao tác nhưng chưa vào được",
        KHONG_RO: "không rõ kết quả (hết giờ)",
    }.get(status, status or "")
    noi(f"[{account.id}] KẾT QUẢ: {status} — {detail}")
    return {"ok": ok, "status": status, "detail": detail, "cookie": cookie}


def login_nhieu(manager, accounts, *, workers: int = 3,
                log: Optional[Callable[[str], None]] = None,
                on_xong: Optional[Callable[[object, dict], None]] = None) -> dict:
    """Dang nhap Google cho nhieu acc song song (moi acc 1 Firefox rieng)."""
    noi = log or (lambda _m: None)
    n = max(1, min(int(workers or 1), MAX_SONG_SONG))
    vao, khong = [], []

    def mot(acc):
        kq = login_google(manager, acc, log=noi)
        if on_xong:
            try:
                on_xong(acc, kq)
            except Exception:  # noqa: BLE001
                pass
        return acc, kq

    with ThreadPoolExecutor(max_workers=n) as ex:
        for acc, kq in ex.map(mot, list(accounts)):
            (vao if kq.get("ok") else khong).append(acc.id)
    noi(f"đăng nhập Google {len(vao)}/{len(accounts)} acc (song song {n} luồng).")
    return {"vao": vao, "khong": khong, "so": len(accounts)}
