"""Mo-dun ĐĂNG BÀI FANPAGE TỰ ĐỘNG — nhom dang_bai. Thao tac len job AutoUploader kind "page":
tham_so: job | job_id · hanh_dong ∈ {bat, tat, dang_ngay} · video (tuy chon). accs = []."""

from __future__ import annotations

from core.modun import KetQua, Modun, NguCanh, dang_ky
from core.modun._dang_bai import thao_tac_job

MA = "dang_fanpage_tu_dong"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    # "lich" = trang dat lich: cung dang len fanpage, chi khac phan gio.
    return thao_tac_job(nc, tham_so, ("page", "lich"))


dang_ky(Modun(ma=MA, ten="📤 Đăng bài fanpage tự động", nhom="dang_bai", chay=chay, can_profile=False,
              mo_ta="Bật/tắt job đăng fanpage theo lịch, hoặc đăng ngay 1 bài."))
