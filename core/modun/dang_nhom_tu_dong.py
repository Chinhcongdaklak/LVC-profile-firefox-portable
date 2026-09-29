"""Mo-dun ĐĂNG BÀI NHÓM TỰ ĐỘNG — nhom dang_bai. Thao tac len job AutoUploader kind "group":
tham_so: job | job_id · hanh_dong ∈ {bat, tat, dang_ngay} · video (tuy chon). accs = []."""

from __future__ import annotations

from core.modun import KetQua, Modun, NguCanh, dang_ky
from core.modun._dang_bai import thao_tac_job

MA = "dang_nhom_tu_dong"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    return thao_tac_job(nc, tham_so, "group")


dang_ky(Modun(ma=MA, ten="👥 Đăng bài nhóm tự động", nhom="dang_bai", chay=chay, can_profile=False,
              mo_ta="Bật/tắt job đăng nhóm theo lịch, hoặc đăng ngay 1 bài."))
