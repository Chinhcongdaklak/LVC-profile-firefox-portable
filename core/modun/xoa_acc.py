"""Mo-dun XOÁ ACC — nhom acc (truoc day la App.delete_accounts).
tham_so: xoa_thu_muc (bool): True = xoa luon thu muc profile tren dia (manager.delete), False = chi dong
trinh duyet + bo khoi bang (manager.close). Luon store.remove(acc). UI hoi 2 lan truoc khi goi."""

from __future__ import annotations

from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "xoa_acc"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    xoa_thu_muc = bool(tham_so.get("xoa_thu_muc", False))
    for a in accs:
        nc.log(f"Đang xoá {a.id}...")
        try:
            if xoa_thu_muc:
                nc.manager.delete(a)
            else:
                nc.manager.close(a)
            nc.store.remove(a.id)
            kq.them_ok(a.id)
        except Exception as exc:  # noqa: BLE001
            kq.them_loi(a.id, str(exc)[:160])
    kq.ghi_chu = f"đã xoá {kq.so_ok} acc" + (" (kèm thư mục profile)" if xoa_thu_muc else " (giữ thư mục)")
    return kq


dang_ky(Modun(ma=MA, ten="🗑 Xoá acc", nhom="acc", chay=chay, can_profile=False,
              mo_ta="Bỏ acc khỏi bảng; tuỳ chọn xoá luôn thư mục profile."))
