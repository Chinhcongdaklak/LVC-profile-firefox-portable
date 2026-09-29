"""Mo-dun ĐÓNG PROFILE — nhom acc (truoc day la App.close_profiles). tham_so: khong co."""

from __future__ import annotations

from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "dong_profile"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    tong = 0
    for a in accs:
        try:
            tong += int(nc.manager.close(a) or 0)
            kq.them_ok(a.id)
        except Exception as exc:  # noqa: BLE001
            kq.them_loi(a.id, str(exc)[:120])
    kq.ghi_chu = f"đã đóng {tong} tiến trình"
    kq.du_lieu = {"tien_trinh": tong}
    return kq


dang_ky(Modun(ma=MA, ten="⏹ Đóng profile", nhom="acc", chay=chay, can_profile=False,
              mo_ta="Tắt Firefox của các acc đã chọn."))
