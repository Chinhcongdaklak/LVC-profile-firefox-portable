"""Tự ĐĂNG NHẬP LẠI khi acc bị LOGOUT giữa lúc làm việc (tạo fanpage / đăng fanpage / đăng nhóm).

Thứ tự (theo yêu cầu người dùng): thử COOKIE trước; cookie không vào được thì đăng nhập WEB (id|pass|2fa);
đăng nhập lại được thì LÀM LẠI việc. Module thuần lõi (không UI): ``chay_lai_neu_logout`` bọc một việc dùng
trình duyệt, bắt lỗi "ĐĂNG XUẤT" rồi đăng nhập lại + chạy lại một lần.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

#: Dấu hiệu acc bị đăng xuất trong thông báo lỗi của các việc (fbcreatepage/fbbusiness).
LOGOUT_MARK = "ĐĂNG XUẤT"
FB_URL = "https://www.facebook.com/"


def dang_nhap_lai(manager, account, *, store=None, settings=None,
                  log: Optional[Callable[[str], None]] = None) -> dict:
    """Đăng nhập lại acc bằng MÔ-ĐUN ĐĂNG NHẬP (ADR-028): gọi mô-đun ``dang_nhap_cookie`` trước
    (tự có bước dự phòng đăng nhập web bên trong), không được thì mô-đun ``dang_nhap_web``.

    Trả ``{ok, cach, detail}`` với ``cach`` = "cookie" | "web" | "". Không ném. ``store``/``settings``
    truyền vào NguCanh của mô-đun (mô-đun tự chịu store=None)."""
    noi = log or (lambda _m: None)
    from core import modun
    from core.modun import tat_ca
    tat_ca.nap()                                   # bảo đảm registry đã nạp (idempotent)
    nc = modun.NguCanh(manager=manager, store=store, settings=settings, log=noi, so_luong=1)

    # 1) MÔ-ĐUN ĐĂNG NHẬP COOKIE (giữ phiên mới hơn / nạp cookie / verify / dự phòng web nội bộ).
    if (getattr(account, "cookie", "") or "").strip():
        try:
            kq = modun.chay("dang_nhap_cookie", nc, [account])
            if account.id in kq.ok:
                noi(f"[{account.id}] đăng nhập lại bằng mô-đun COOKIE — OK.")
                return {"ok": True, "cach": "cookie", "detail": kq.ghi_chu}
            noi(f"[{account.id}] mô-đun cookie chưa vào được.")
        except Exception as exc:  # noqa: BLE001
            noi(f"[{account.id}] lỗi mô-đun đăng nhập cookie: {exc}")

    # 2) MÔ-ĐUN ĐĂNG NHẬP WEB (id|pass|2fa) — cho acc không có cookie hoặc cookie đã hỏng.
    if (getattr(account, "password", "") or "").strip():
        noi(f"[{account.id}] gọi mô-đun ĐĂNG NHẬP WEB (id|pass|2fa)...")
        try:
            kq = modun.chay("dang_nhap_web", nc, [account])
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "cach": "", "detail": f"web lỗi: {exc}"}
        if account.id in kq.ok:
            noi(f"[{account.id}] đăng nhập lại bằng mô-đun WEB — OK.")
            return {"ok": True, "cach": "web", "detail": kq.ghi_chu}
        ly = dict(kq.loi).get(account.id, "")
        return {"ok": False, "cach": "", "detail": f"web: {ly}"}

    return {"ok": False, "cach": "", "detail": "acc chưa có cookie/mật khẩu để đăng nhập lại"}


def la_logout(exc: BaseException) -> bool:
    """Lỗi này có phải do acc bị ĐĂNG XUẤT không (để quyết định đăng nhập lại)."""
    return LOGOUT_MARK in str(exc)


def chay_lai_neu_logout(manager, account, chay: Callable[[], object], *,
                        store=None, settings=None,
                        log: Optional[Callable[[str], None]] = None):
    """Chạy ``chay()`` (một việc dùng trình duyệt). Nếu acc bị LOGOUT -> gọi MÔ-ĐUN ĐĂNG NHẬP
    (cookie -> web) rồi CHẠY LẠI một lần. Đăng nhập lại không được -> ném lại lỗi gốc.

    ``chay`` là callable không tham số, trả kết quả của việc / ném lỗi. ``store``/``settings`` truyền
    xuống mô-đun đăng nhập để lưu cookie tươi (App có; core gọi thì để None cũng chạy)."""
    noi = log or (lambda _m: None)
    try:
        return chay()
    except Exception as exc:  # noqa: BLE001
        if not la_logout(exc):
            raise
        noi(f"[{account.id}] acc bị ĐĂNG XUẤT khi làm việc — gọi mô-đun đăng nhập rồi làm tiếp...")
        kq = dang_nhap_lai(manager, account, store=store, settings=settings, log=log)
        if not kq.get("ok"):
            noi(f"[{account.id}] đăng nhập lại KHÔNG được ({kq.get('detail')}).")
            raise
        noi(f"[{account.id}] đã đăng nhập lại ({kq.get('cach')}) — làm lại việc.")
        return chay()
