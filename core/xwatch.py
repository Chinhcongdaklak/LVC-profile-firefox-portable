"""Driver TUONG TAC X.com — dieu khien agent xwatch_agent.js luot newfeed /home.

Cung khuon core/fbwatch.py (tuong tac Facebook) va core/xpost.py (dang bai X):
  1. Dong Firefox cua acc, lam moi agent (manager.configure).
  2. Ghi lenh vao <profile>/qlfp-xwatch.json.
  3. Mo Firefox BINH THUONG qua CONG VPN (acc co NordVPN) roi toi https://x.com/home.
  4. Agent cuon newfeed, dung lai doc tung bai, tha tim, bam xem video, vao bai lay
     comment dau tien dang lai kem 3-5 icon; bao tien do
     ve qlfp-xwatch-result.json. Ham nay poll file do.
  5. Dong Firefox, tra {ok, state, xem, like, video, detail}. KHONG nem.

Trang thai agent: on-home | progress | done | error | logged-out | x-locked | seen.
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

from . import nordvpn

CMD_NAME = "qlfp-xwatch.json"
RESULT_NAME = "qlfp-xwatch-result.json"
X_HOME_URL = "https://x.com/home"

#: Dung lai moi bai bao nhieu giay (nguoi dung chinh duoc; mac dinh 5-10s).
DUNG_MIN = 5
DUNG_MAX = 10


def _path(profile_dir: str, name: str) -> str:
    return os.path.join(profile_dir, name)


def _clear(profile_dir: str) -> None:
    for name in (CMD_NAME, RESULT_NAME):
        try:
            os.remove(_path(profile_dir, name))
        except OSError:
            pass


def put_command(profile_dir: str, **command) -> None:
    os.makedirs(profile_dir, exist_ok=True)
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


def tuong_tac(manager, account, *, so_like: int = 0, so_video: int = 0, so_comment: int = 0,
              gioi_han_giay: int = 120, dung_min: int = DUNG_MIN, dung_max: int = DUNG_MAX,
              url: str = X_HOME_URL, timeout: Optional[float] = None, thu: bool = False,
              log: Optional[Callable[[str], None]] = None) -> dict:
    """Mo Firefox vao x.com/home, luot newfeed trong ``gioi_han_giay`` giay.

    ``so_like``: so bai tha tim. ``so_video``: so video bam xem. ``so_comment``: so bai vao
    lay comment dau tien dang lai + 3-5 icon. ``dung_min/max``: so giay dung lai moi bai
    (ngau nhien). Tra {ok, state, xem, like, video, cmt, detail}.
    """
    noi = log or (lambda _m: None)
    han = max(10, int(gioi_han_giay))
    dmin = max(1, int(dung_min))
    dmax = max(dmin, int(dung_max))
    if timeout is None:
        timeout = han + 180        # + thoi gian mo trinh duyet / cong VPN / nap trang

    if not manager.is_installed(account):
        noi(f"[{account.id}] chua co profile X — tao...")
        manager.create(account)

    profile = manager.profile_dir(account)
    try:
        manager.close(account, wait=6.0)
    except OSError:
        pass
    manager.configure(account)
    _clear(profile)
    put_command(profile, action="xwatch", url=url, so_like=int(so_like), so_video=int(so_video),
                so_comment=int(so_comment), gioi_han_giay=han, dung_min=dmin, dung_max=dmax,
                thu=bool(thu))

    noi(f"[{account.id}] mo Firefox → x.com/home: {so_like} tim, {so_video} video, "
        f"{so_comment} comment, ≤{han}s, dung {dmin}-{dmax}s/bai...")
    # Kiem VPN TRUOC (acc co NordVPN) — khong luot X bang IP that.
    cong = nordvpn.mo_qua_cong_vpn(manager, account, url, log=noi)
    if not cong["ok"]:
        _clear(profile)
        return {"ok": False, "state": "vpn-loi", "xem": 0, "like": 0, "video": 0, "cmt": 0,
                "detail": f"VPN CHƯA NỐI: {cong['detail']}"}

    ket = {"ok": False, "state": "", "xem": 0, "like": 0, "video": 0, "cmt": 0, "detail": ""}
    seen: set = set()
    deadline = time.time() + timeout
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
                ket["video"] = int(r.get("video") or ket["video"])
                ket["cmt"] = int(r.get("cmt") or ket["cmt"])
                key = st + "|" + det
                if key not in seen:
                    seen.add(key)
                    noi(f"[{account.id}] {st}: {det[:320]}")
                if st == "done":
                    ket.update(ok=True, state="done", detail=det)
                    break
                if st == "logged-out":
                    ket.update(ok=False, state="logged-out", detail=det or "acc chưa đăng nhập x.com")
                    break
                if st == "x-locked":
                    ket.update(ok=False, state="x-locked", detail=det or "acc bị X khoá/treo")
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
    noi(f"[{account.id}] KẾT QUẢ tương tác X: {ket['state']} — xem {ket['xem']} bài, "
        f"tim {ket['like']}, video {ket['video']}, comment {ket['cmt']}")
    return ket
