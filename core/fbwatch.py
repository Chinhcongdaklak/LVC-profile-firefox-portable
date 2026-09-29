"""Driver TƯƠNG TÁC — điều khiển agent fbwatch_agent.js: kiểm quyền cá nhân/Page, vào /reel/,
xem N video + thả L like trong ≤ M phút. Bridge riêng: lệnh ``<profile>/qlfp-watch.json``,
agent báo ``qlfp-watch-result.json`` (khác các agent upload/create/login/chat/bm).

``tuong_tac(manager, account, *, so_video, so_phut, so_like, ...)`` -> dict {ok, state, xem, like, detail}.
Không ném (trừ thiếu profile qua manager). Bí mật: không có; log chỉ trạng thái + số đếm.
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

CMD_NAME = "qlfp-watch.json"
RESULT_NAME = "qlfp-watch-result.json"
REEL_URL = "https://www.facebook.com/reel/"


def _path(profile_dir: str, name: str) -> str:
    return os.path.join(profile_dir, name)


def _clear(profile_dir: str) -> None:
    for name in (CMD_NAME, RESULT_NAME):
        try:
            os.remove(_path(profile_dir, name))
        except OSError:
            pass


def put_command(profile_dir: str, **command) -> None:
    path = _path(profile_dir, CMD_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(command, fh, ensure_ascii=False)
    os.replace(tmp, path)


def _read_result(profile_dir: str) -> Optional[dict]:
    try:
        with open(_path(profile_dir, RESULT_NAME), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def tuong_tac(manager, account, *, so_video: int = 10, so_phut: int = 30, so_like: int = 0,
              so_thong_bao: int = 0, gioi_han_giay: int = 0, url: str = REEL_URL,
              xem_giay_min: int = 6, xem_giay_max: int = 14, timeout: Optional[float] = None,
              log: Optional[Callable[[str], None]] = None) -> dict:
    """Mở Firefox, kiểm quyền -> đọc N thông báo (nếu chọn) -> vào reel xem + like.
    Trả {ok, state, xem, like, tb, detail}.

    ``gioi_han_giay`` > 0: giới hạn tương tác 1 acc theo GIÂY (ưu tiên); =0 thì dùng ``so_phut`` (phút)."""
    noi = log or (lambda _m: None)
    profile = manager.profile_dir(account)
    han_giay = int(gioi_han_giay) if int(gioi_han_giay) > 0 else max(1, int(so_phut)) * 60
    if timeout is None:
        timeout = han_giay + 150

    try:
        manager.close(account, wait=6.0)
    except OSError:
        pass
    manager.configure(account)
    _clear(profile)
    # Mo trang KHOI DAU = facebook.com de kiem quyen + doc thong bao truoc khi vao reel.
    mo_url = "https://www.facebook.com/" if int(so_thong_bao) > 0 else url
    put_command(profile, action="tuongtac", url=url, so_video=int(so_video),
                so_phut=int(so_phut), gioi_han_giay=han_giay, so_like=int(so_like),
                so_thong_bao=int(so_thong_bao),
                xem_giay_min=int(xem_giay_min), xem_giay_max=int(xem_giay_max))
    noi(f"[{account.id}] mở Firefox tương tác: {so_video} video, {so_like} like, "
        f"{so_thong_bao} thông báo, ≤{han_giay} giây...")
    manager.launch(account, url=mo_url)

    ket = {"ok": False, "state": "", "xem": 0, "like": 0, "tb": 0, "detail": ""}
    seen = set()
    deadline = time.time() + timeout
    # Canh tien trinh Firefox: bi tat/chet giua chung thi dung NGAY, khong ngoi
    # cho het timeout roi moi bao (truoc day treo "đang chạy" ca chuc phut).
    from core.fbbusiness import app_dir_cua, firefox_pids
    app_dir = app_dir_cua(manager, account)
    da_thay_browser = False
    ke_tiep_kiem = 0.0
    try:
        while time.time() < deadline:
            if app_dir and time.time() >= ke_tiep_kiem:
                ke_tiep_kiem = time.time() + 3.0
                if firefox_pids(app_dir):
                    da_thay_browser = True
                elif da_thay_browser:
                    ket.update(ok=False, state="browser-gone",
                               detail="trình duyệt đã đóng giữa chừng")
                    break
            r = _read_result(profile)
            if r:
                st = r.get("state") or ""
                det = str(r.get("detail") or "")
                ket["xem"] = int(r.get("xem") or ket["xem"])
                ket["like"] = int(r.get("like") or ket["like"])
                ket["tb"] = int(r.get("tb") or ket["tb"])
                key = st + "|" + det
                if key not in seen:
                    seen.add(key)
                    noi(f"[{account.id}] {st}: {det[:80]}")
                if st == "done":
                    ket.update(ok=True, state="done", detail=det)
                    break
                if st == "logged-out":
                    # Acc bi dang xuat giua chung -> cha (mo-dun) se goi dang nhap lai roi thu lai.
                    ket.update(ok=False, state="logged-out", detail=det or "acc bị đăng xuất")
                    break
                if st == "error":
                    ket.update(ok=False, state="error", detail=det or "lỗi agent")
                    break
            time.sleep(2.0)
        else:
            ket.update(state="timeout", detail=f"hết giờ chờ ({int(timeout)}s)")
    finally:
        try:
            manager.close(account, wait=8.0)
        except OSError:
            pass
        _clear(profile)
    noi(f"[{account.id}] KẾT QUẢ tương tác: {ket['state']} — xem {ket['xem']}, like {ket['like']}, "
        f"thông báo {ket['tb']}")
    return ket
