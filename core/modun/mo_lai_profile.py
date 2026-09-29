"""Mo-dun MỞ LẠI PROFILE — nhom acc. Dong roi mo lai Firefox cua acc (manager.restart), dung sau khi
doi proxy/UA vi Firefox chi doc mozilla.cfg luc khoi dong. tham_so: khong co."""

from __future__ import annotations

from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "mo_lai_profile"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    for i, a in enumerate(accs, start=1):
        nc.log(f"[{i}/{len(accs)}] Đang mở lại {a.id}...")
        try:
            nc.manager.restart(a)
            kq.them_ok(a.id)
        except Exception as exc:  # noqa: BLE001
            kq.them_loi(a.id, str(exc)[:160])
    kq.ghi_chu = f"mở lại {kq.so_ok}/{len(accs)} trình duyệt"
    return kq


dang_ky(Modun(ma=MA, ten="🔄 Mở lại profile", nhom="acc", chay=chay,
              mo_ta="Đóng rồi mở lại Firefox để ăn cấu hình mới (proxy/UA)."))
