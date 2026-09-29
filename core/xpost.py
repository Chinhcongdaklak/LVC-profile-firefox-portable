"""Dang mot bai len X.com (tuong acc) qua trinh duyet.

Cung khuon fbbusiness.upload (agent process-script) va xlogin (dieu phoi):
  1. Dong Firefox cua acc, lam moi agent (manager.configure).
  2. Ghi lenh vao <profile>/qlfp-xpost.json (chu + duong dan media).
  3. Mo Firefox BINH THUONG vao https://x.com/home -- khong cong debug.
  4. Agent core/assets/xpost_agent.js dien chu, dinh kem media, bam Dang,
     bao trang thai ve qlfp-xpost-result.json. Ham nay poll file do.
  5. Dong Firefox. Thanh cong tra chuoi mo ta; hong nem fbupload.UploadError.

Loi tra ve dung cac MOC cua core/autoup de bo may thu lai / tam dung acc
hoat dong y het Facebook:
  - acc chua dang nhap x.com  -> chuoi chua LOGOUT_MARK ("ĐĂNG XUẤT")
  - acc bi X khoa/treo        -> chuoi chua CHECKPOINT_MARK ("CHECKPOINT")
  - da bam Dang ma khong ro   -> "publish-timeout" (autoup coi nhu DA dang,
                                 khong thu lai de khoi dang trung)
Ham THUAN (ket_luan, mime_of) tach rieng de test khong can trinh duyet.
"""
from __future__ import annotations

import json
import mimetypes
import os
import time
from typing import Callable, Optional

from . import fbupload
from . import nordvpn
from . import procutil
from .autoup import CHECKPOINT_MARK, GIOI_HAN_MARK, LOGOUT_MARK, STUCK_MARK, VIDEO_TU_CHOI_MARK

#: Loi cong VPN (acc co NordVPN ma VPN chua noi) -- khong dang bang IP that.
VPN_MARK = "VPN CHƯA NỐI"

CMD_NAME = "qlfp-xpost.json"
RESULT_NAME = "qlfp-xpost-result.json"
X_HOME_URL = "https://x.com/home"

#: Trang thai KET THUC ma agent co the bao (moi cai dung mot lan).
XONG = ("post-done", "publish-timeout", "dry-done")
HONG = ("post-error", "no-composer", "file-error", "upload-stuck", "text-error", "media-rejected")
ACC_LOI = ("logged-out", "x-locked", "daily-limit")

#: Trinh duyet bi dong giua chung (nguoi dung tat / crash) -- xem fbbusiness.
BROWSER_GONE = "browser-gone"


# --- ham THUAN --------------------------------------------------------------

def mime_of(path: str) -> str:
    """Kieu MIME cua file media, doan theo duoi ten."""
    mime, _ = mimetypes.guess_type(path or "")
    return mime or "application/octet-stream"


def ket_luan(states: set, het_gio: bool) -> Optional[str]:
    """Trang thai chot tu tap trang thai agent da bao. None = cho tiep. THUAN."""
    for st in ACC_LOI + tuple(s for s in HONG) + tuple(XONG):
        if st in states:
            return st
    if het_gio:
        return "het-gio"
    return None


# --- dieu phoi (can trinh duyet) --------------------------------------------

def _clear(profile_dir: str) -> None:
    for n in (CMD_NAME, RESULT_NAME):
        try:
            os.remove(os.path.join(profile_dir, n))
        except OSError:
            pass


def _put_cmd(profile_dir: str, text: str, path: str, thu: bool = False) -> None:
    # Firefox (nsIFile) chi nhan duong dan Windows dau "\\": "C:/a/b.mp4" -> NS_ERROR_FILE_UNRECOGNIZED_PATH.
    path = os.path.normpath(path) if path else ""
    cmd = {
        "action": "xpost",
        "text": text or "",
        "path": path or "",
        "name": os.path.basename(path) if path else "",
        "mime": mime_of(path) if path else "",
        "delay": 1200,
        # Agent tu dung sau 22 phut: 15 phut cho video tai len + mo trang + cho xac nhan dang.
        "timeout": 22 * 60 * 1000,
        # Che do THU: dien chu (+ gan video neu co, doc % tai len, cho nut Post bat), KHONG bam Dang.
        "dry": bool(thu),
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


def _app_dir(manager, account) -> str:
    try:
        return manager.app_dir(account) or ""
    except Exception:  # noqa: BLE001
        return ""


def upload(manager, account, path: str, caption: str, *,
           timeout: float = 23 * 60.0, thu: bool = False,
           log: Optional[Callable[[str], None]] = None) -> str:
    """Dang MOT bai len tuong acc X. Tra chuoi mo ta; hong nem UploadError.

    ``path`` la file media (video/anh) hoac file .txt (bai chi chu -- khi do
    ``caption`` da chua noi dung, media bo trong).
    """
    noi = log or (lambda _m: None)
    kind = fbupload.kind_of(path)
    media = "" if kind == "text" else path
    text = (caption or "").strip()
    if not media and not text:
        raise fbupload.UploadError("Bài trống: không có chữ lẫn media.")
    if media and not os.path.isfile(media):
        raise fbupload.UploadError(f"Không thấy file: {media}")

    if not manager.is_installed(account):
        noi(f"[{account.id}] chưa có profile X — tạo...")
        manager.create(account)

    profile = manager.profile_dir(account)
    manager.close(account, wait=8.0)
    manager.configure(account)          # trien khai/lam moi agent vao profile
    _clear(profile)
    _put_cmd(profile, text, media, thu=thu)

    noi(f"[{account.id}] mở Firefox → x.com → đăng bài"
        + (f" ({os.path.basename(media)})" if media else " (chỉ chữ)"))
    # Kiem VPN TRUOC (acc co NordVPN): chua noi thi KHONG dang bai bang IP that.
    cong = nordvpn.mo_qua_cong_vpn(manager, account, X_HOME_URL, log=noi)
    if not cong["ok"]:
        _clear(profile)
        raise fbupload.UploadError(f"{VPN_MARK}: {cong['detail']}")

    app_dir = _app_dir(manager, account)
    chi_tiet: dict = {}
    states: set = set()
    _seen: set = set()
    da_thay_ff = False
    deadline = time.time() + timeout
    chot = None
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
                elif st == "upload-progress":
                    # % video X dang tai len: bao MOI LAN doi (mang yeu co the mat nhieu phut).
                    if det and det != chi_tiet.get(st):
                        chi_tiet[st] = det
                        noi(f"[{account.id}] đang tải video lên X: {det}")
                elif st and st not in states:
                    states.add(st)
                    chi_tiet[st] = det
                    noi(f"[{account.id}] {st}" + (f": {det[:80]}" if det else ""))
            chot = ket_luan(states, het_gio=False)
            if chot:
                break
            # Canh trinh duyet bi dong giua chung -- khong ngoi cho het timeout.
            if app_dir:
                dang_chay = bool(procutil.find_under(app_dir, use_cache=False))
                if dang_chay:
                    da_thay_ff = True
                elif da_thay_ff:
                    chot = BROWSER_GONE
                    break
            time.sleep(0.8)
        if chot is None:
            chot = ket_luan(states, het_gio=True)
    finally:
        try:
            manager.close(account, wait=10.0)
        except OSError:
            pass
        _clear(profile)

    ten = os.path.basename(path)
    if chot == "dry-done":
        return chi_tiet.get("dry-done", "")          # che do THU: JSON {lan, lan_dien, noi_dung}
    if chot == "post-done":
        return f"đã đăng {ten} lên tường @{account.id}"
    if chot == "publish-timeout":
        # DA bam Dang -- coi nhu len roi (nhu Facebook), thu lai la dang trung.
        return f"đã bấm Đăng {ten} (không thấy xác nhận — coi như đã lên)"
    if chot == "media-rejected":
        raise fbupload.UploadError(
            f"{VIDEO_TU_CHOI_MARK}: {ten} — X báo \"{chi_tiet.get('media-rejected', '')[:120]}\" "
            "(thường do video dài hơn 2:20 với acc X thường).")
    if chot == "daily-limit":
        # KHONG duoc coi la da dang (truoc day roi vao publish-timeout = "coi nhu da len").
        # Khong dung cum "bam Dang" (PUBLISHED_MARKS) -> autoup se tam dung acc 24 gio.
        raise fbupload.UploadError(
            f"{GIOI_HAN_MARK}: acc @{account.id} — X báo \"You've hit the daily post limit\", "
            "bài CHƯA lên.")
    if chot == "logged-out":
        raise fbupload.UploadError(
            f"{LOGOUT_MARK}: acc @{account.id} chưa đăng nhập x.com — "
            "vào tab Quản lý acc X nạp cookie / đăng nhập lại.")
    if chot == "x-locked":
        raise fbupload.UploadError(
            f"{CHECKPOINT_MARK}: acc @{account.id} bị X khoá/treo.")
    if chot == "upload-stuck":
        pt = chi_tiet.get("upload-progress", "")
        raise fbupload.UploadError(
            f"{STUCK_MARK} — chờ 15 phút nút Post vẫn chưa bật (mạng yếu / video xử lý quá lâu)"
            + (f", lần cuối {pt}" if pt else "") + ".")
    if chot == BROWSER_GONE:
        raise fbupload.UploadError("Trình duyệt bị đóng giữa chừng khi đang đăng.")
    if chot in ("post-error",):
        raise fbupload.UploadError("X báo lỗi sau khi bấm Đăng — kiểm tra tường acc "
                                   "trước khi đăng lại kẻo trùng.")
    if chot in ("no-composer",):
        raise fbupload.UploadError(
            "Không thấy ô soạn bài trên x.com/home (X đổi giao diện hoặc trang "
            "chưa tải xong) — xem nhật ký 'seen' để chỉnh selector.")
    if chot in ("file-error", "text-error"):
        raise fbupload.UploadError(f"Lỗi thao tác composer: {chot} — xem nhật ký.")
    raise fbupload.UploadError("Hết giờ chờ mà chưa đăng xong "
                               f"(trạng thái: {', '.join(sorted(states)) or 'không có'}).")
