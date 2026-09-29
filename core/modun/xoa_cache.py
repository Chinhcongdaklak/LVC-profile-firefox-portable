"""Mo-dun XOÁ CACHE — nhom khac (truoc day la App.clear_cache). Xoa cache trinh duyet, GIU dang nhap.
Acc dang mo duoc dong truoc. du_lieu["freed"] = byte giai phong. tham_so: khong co."""

from __future__ import annotations

import time

from core.modun import KetQua, Modun, NguCanh, dang_ky
from core.profiles import ProfileError

MA = "xoa_cache"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    dung = [a for a in accs if nc.manager.is_installed(a)]
    for a in accs:
        if a not in dung:
            kq.them_loi(a.id, "chưa tạo profile")
    freed = 0
    for i, a in enumerate(dung, start=1):
        nc.log(f"[{i}/{len(dung)}] Đang xoá cache {a.id}...")
        try:
            if nc.manager.is_running(a):
                nc.manager.close(a)
                time.sleep(1.5)
            freed += int(nc.manager.clear_cache(a) or 0)
            kq.them_ok(a.id)
        except (ProfileError, OSError) as exc:
            kq.them_loi(a.id, str(exc)[:160])
    kq.ghi_chu = f"giải phóng {freed / 1024 / 1024:.0f} MB"
    kq.du_lieu = {"freed": freed}
    return kq


dang_ky(Modun(ma=MA, ten="🧹 Xoá cache", nhom="khac", chay=chay,
              mo_ta="Xoá file tạm của Firefox, giữ cookie/đăng nhập."))
