"""Dang nhap web bang id|pass|2fa (chuot phai -> "Dang nhap web").

Mo Firefox BINH THUONG (khong --remote-debugging-port) va dieu khien form dang nhap
bang PROCESS-SCRIPT AGENT (core/assets/fblogin_agent.js) -> su kien "nguoi that",
navigator.webdriver = false -> Facebook KHONG chan bang reCAPTCHA (khac duong BiDi,
da do that 2026-09-06). Ma 2FA sinh OFFLINE bang core.totp, CHA lam moi dinh ky.

Xac minh dang nhap thanh cong qua ProfileManager.verify/read_login_probe (qlfp-login.json),
KHONG dua vao agent doan "da vao". Bridge file: qlfp-weblogin.json / qlfp-weblogin-result.json
(xem autoconfig._LOGIN_LOADER_JS) -- KHAC qlfp-login.json cua probe.
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

from core import totp

CMD_NAME = "qlfp-weblogin.json"
RESULT_NAME = "qlfp-weblogin-result.json"
LOGIN_URL = "https://www.facebook.com/login.php"

#: Trang thai ket thuc (status) tra ve.
VAO = "vao"                 # dang nhap thanh cong (verify_cookie_login = True)
SAI_MAT_KHAU = "sai_mat_khau"
CHECKPOINT = "checkpoint"
HAI_FA_LOI = "2fa_that_bai"  # da dien 2FA nhung khong vao (ma sai / het buoc)
KHONG_VAO = "khong_vao"      # da bam dang nhap nhung khong xac minh duoc
KHONG_RO = "khong_ro"
THIEU = "thieu_thong_tin"
INVALID_LAP = "loi_invalid"  # trang 2FA bao "Invalid request" -> back/tiep tuc/nhap mk 3 lan van loi


class FbLoginError(RuntimeError):
    pass


#: Tran so acc dang nhap web SONG SONG (moi acc mo 1 Firefox that -> nang; gioi han de
#: may khong qua tai va Facebook khong nghi ngo dang nhap dong loat).
MAX_SONG_SONG = 8        # = max o "Luong" dung chung (ADR-015); tran an toan, moi acc 1 Firefox


def login_nhieu(manager, accounts, *, workers: int = 2,
                login_fn: Optional[Callable] = None,
                on_xong: Optional[Callable[[dict], None]] = None,
                dung: Optional[Callable[[], bool]] = None,
                log: Optional[Callable[[str], None]] = None) -> dict:
    """Dang nhap web NHIEU acc song song CO GIOI HAN (workers, tran MAX_SONG_SONG).

    login_fn(manager, account, log=) -> ket qua dict (mac dinh = login_web). Tra
    {"vao": [id...], "khong": [(id,status,detail)...], "so": n}. Giu tran de khong mo
    qua nhieu Firefox cung luc.
    """
    from concurrent.futures import ThreadPoolExecutor
    import threading
    login_fn = login_fn or login_web
    dung = dung or (lambda: False)
    noi = log or (lambda _m: None)
    accounts = list(accounts)
    n = max(1, min(int(workers), MAX_SONG_SONG, len(accounts) or 1))
    vao: list = []
    khong: list = []
    lock = threading.Lock()

    def one(acc):
        if dung():
            return
        try:
            kq = login_fn(manager, acc, log=log)
        except Exception as exc:  # noqa: BLE001
            kq = {"ok": False, "status": "loi", "detail": str(exc)[:150]}
        with lock:
            if kq.get("ok"):
                vao.append(acc.id)
            else:
                khong.append((acc.id, kq.get("status"), kq.get("detail", "")))
        if on_xong:
            on_xong({"id": acc.id, **kq})

    with ThreadPoolExecutor(max_workers=n) as pool:
        list(pool.map(one, accounts))
    noi(f"đăng nhập web {len(vao)}/{len(accounts)} acc (song song {n} luồng).")
    return {"vao": vao, "khong": khong, "so": len(accounts)}


def _clear(profile_dir: str) -> None:
    for n in (CMD_NAME, RESULT_NAME):
        try:
            os.remove(os.path.join(profile_dir, n))
        except OSError:
            pass


def _put_cmd(profile_dir: str, account, code: str) -> None:
    cmd = {"action": "weblogin", "email": account.id, "pass": account.password,
           "code": code or "", "code_at": time.time(), "formTimeout": 45000, "delay": 2000,
           # Luong khoi phuc (Invalid request -> quen mat khau): mail khoi phuc + thoi gian cho captcha.
           "recovery_mail": (getattr(account, "recovery_mail", "") or ""),
           "recoverTimeout": 130000}
    os.makedirs(profile_dir, exist_ok=True)
    with open(os.path.join(profile_dir, CMD_NAME), "w", encoding="utf-8") as fh:
        json.dump(cmd, fh, ensure_ascii=False)


def _read_result(profile_dir: str) -> Optional[dict]:
    try:
        with open(os.path.join(profile_dir, RESULT_NAME), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def danh_gia(states: set, vao_duoc: bool, het_gio: bool) -> Optional[str]:
    """Quyet dinh trang thai cuoi tu tap trang thai agent + probe dang nhap + het gio.

    Tra None = chua ket luan (cho tiep). Ham THUAN de test khong can trinh duyet.
    """
    if vao_duoc:
        return VAO
    if "checkpoint" in states:
        return CHECKPOINT
    if "wrong-pass" in states:
        return SAI_MAT_KHAU
    if "invalid-fail" in states:
        # Trang 2FA "Invalid request": da back -> tiep tuc -> nhap mk 3 lan van loi -> dung, bao loi.
        return INVALID_LAP
    if het_gio:
        if "twofa-filled" in states or "twofa-dom" in states:
            return HAI_FA_LOI
        if "clicked-login" in states or "login-submit-form" in states:
            return KHONG_VAO
        return KHONG_RO
    return None


def login_web(manager, account, *, timeout: float = 200.0,
              log: Optional[Callable[[str], None]] = None) -> dict:
    """Dang nhap acc bang id|pass|2fa qua trinh duyet. Tra {ok, status, detail}. Khong nem
    (tru thieu thong tin bat buoc)."""
    noi = log or (lambda _m: None)
    if not (account.password or "").strip():
        return {"ok": False, "status": THIEU, "detail": "Acc chưa có mật khẩu."}
    profile = manager.profile_dir(account)

    manager.close(account, wait=8.0)
    manager.configure(account)              # trien khai/lam moi agent dang nhap vao profile
    manager.clear_login_probe(account)
    _clear(profile)
    twofa = (account.twofa or "").strip()
    _put_cmd(profile, account, totp.generate(twofa) if twofa else "")

    noi(f"[{account.id}] mở Firefox đăng nhập id|pass" + (" |2fa" if twofa else "") + "...")
    manager.launch(account, url=LOGIN_URL)

    states: set = set()
    _seen_details: set = set()
    dom_2fa = ""
    last_code_at = 0.0
    deadline = time.time() + timeout
    status = None
    try:
        while time.time() < deadline:
            r = _read_result(profile)
            if r:
                st = r.get("state")
                det = r.get("detail")
                det = "" if det is None else str(det)
                # 'seen'/'twofa-dom': chan doan, log moi khi detail doi (khong tinh la trang thai cuoi).
                if st in ("seen", "twofa-dom"):
                    key = st + "|" + det
                    if key not in _seen_details:
                        _seen_details.add(key)
                        noi(f"[{account.id}] {st}: {det[:160]}")
                    if st == "twofa-dom":
                        dom_2fa = det
                        states.add(st)
                elif st and st not in states:
                    states.add(st)
                    noi(f"[{account.id}] {st}" + (f": {det[:60]}" if det else ""))
                # Dinh CAPTCHA: agent bao lien tuc trong luc cho -> GIA HAN deadline de nguoi dung kip giai.
                if st == "captcha-wait":
                    deadline = max(deadline, time.time() + 90.0)
            probe = manager.read_login_probe(account)
            vao = bool(probe and probe[0])
            status = danh_gia(states, vao, het_gio=False)
            if status:
                break
            # Lam moi ma 2FA moi ~5s de agent luon co ma con hieu luc khi toi buoc 2FA.
            if twofa and (time.time() - last_code_at) >= 5.0:
                _put_cmd(profile, account, totp.generate(twofa))
                last_code_at = time.time()
            time.sleep(1.0)
        if status is None:
            probe = manager.read_login_probe(account)
            status = danh_gia(states, bool(probe and probe[0]), het_gio=True) or KHONG_RO
    finally:
        # Xac minh chac chan bang phien that (giu trinh duyet mo them chut de probe kip ghi).
        try:
            if status not in (CHECKPOINT, SAI_MAT_KHAU) and manager.verify_cookie_login(account, timeout=12):
                status = VAO
        except Exception:  # noqa: BLE001
            pass
        try:
            manager.close(account, wait=10.0)
        except OSError:
            pass
        _clear(profile)     # xoa lenh de agent khong dien nham o lan mo sau

    ok = status == VAO
    if ok:
        # Luu COOKIE TUOI vao acc de dung lai (khoi dang nhap lai lan sau).
        try:
            tuoi = manager.read_probe_cookies(account)
            if tuoi and "c_user" in tuoi:
                account.cookie = tuoi
                noi(f"[{account.id}] đã lưu cookie tươi ({len(tuoi)} ký tự).")
        except Exception:  # noqa: BLE001
            pass
    detail = {VAO: "đăng nhập thành công", SAI_MAT_KHAU: "sai mật khẩu",
              CHECKPOINT: "acc bị checkpoint — cần xác minh tay",
              HAI_FA_LOI: "điền 2FA nhưng không vào được (mã sai / thêm bước)",
              KHONG_VAO: "đã bấm đăng nhập nhưng chưa vào được",
              INVALID_LAP: "trang 2FA 'Invalid request' — quay lại/nhập mật khẩu 3 lần vẫn lỗi",
              KHONG_RO: "không rõ kết quả (hết giờ)"}.get(status, status or "")
    if status == HAI_FA_LOI and dom_2fa:
        detail += f" | 2FA DOM: {dom_2fa[:120]}"
    if ok:
        account.cookie_ok = time.strftime("%Y-%m-%d %H:%M")
    noi(f"[{account.id}] KẾT QUẢ: {status} — {detail}")
    return {"ok": ok, "status": status, "detail": detail}
