"""Mo-dun BỎ KHỚP MÚI GIỜ — nhom proxy (truoc day la App.clear_identities).
Tra profile ve mui gio + ngon ngu mac dinh cua may. tham_so: khong co."""

from __future__ import annotations

from core.modun import KetQua, Modun, NguCanh, dang_ky
from core.profiles import ProfileError

MA = "bo_khop_mui_gio"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    for a in accs:
        try:
            nc.manager.clear_identity(a)
        except ProfileError:
            a.set_identity(None)
        kq.them_ok(a.id)
    try:
        nc.store.save()
    except Exception:  # noqa: BLE001
        pass
    kq.ghi_chu = f"đã bỏ khớp múi giờ cho {len(accs)} acc"
    return kq


dang_ky(Modun(ma=MA, ten="🕒 Bỏ khớp múi giờ", nhom="proxy", chay=chay, can_profile=False,
              mo_ta="Trả profile về múi giờ/ngôn ngữ mặc định của máy."))
