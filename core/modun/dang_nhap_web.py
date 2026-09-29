"""Mo-dun ĐĂNG NHẬP WEB (id|pass|2fa) — nhom acc.

Boc core.fblogin.login_nhieu (process-script agent, song song theo so_luong). Chay duoc
khong can UI. tham_so: khong co.
"""

from __future__ import annotations

from core import fblogin
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "dang_nhap_web"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    dung = [a for a in accs if nc.manager.is_installed(a) and (a.password or "").strip()]
    for a in accs:
        if a not in dung:
            kq.them_loi(a.id, "chưa có profile hoặc thiếu mật khẩu")
    if not dung:
        kq.ghi_chu = "không có acc đủ điều kiện (cần profile + mật khẩu)"
        return kq
    workers = max(1, min(int(nc.so_luong or 1), len(dung)))
    xong = {"n": 0}

    def on_xong(r: dict) -> None:
        xong["n"] += 1
        nc.log(f"[{xong['n']}/{len(dung)}] {r.get('id')}: {r.get('status')}")

    r = fblogin.login_nhieu(nc.manager, dung, workers=workers, on_xong=on_xong, log=nc.log)
    for i in r.get("vao", []):
        kq.them_ok(i)
    for i, st, det in r.get("khong", []):
        kq.them_loi(i, f"{st} — {det}" if det else str(st))
    try:
        nc.store.save()
    except Exception:  # noqa: BLE001
        pass
    kq.ghi_chu = f"song song {workers} luồng"
    kq.du_lieu = {"vao": list(r.get("vao", [])), "khong": list(r.get("khong", []))}
    return kq


dang_ky(Modun(ma=MA, ten="🌐 Đăng nhập web (id|pass|2fa)", nhom="acc", chay=chay,
              mo_ta="Mở Firefox bình thường, agent điền id/pass/2FA, lưu cookie tươi."))
