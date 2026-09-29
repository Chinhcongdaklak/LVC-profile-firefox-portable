"""Nap MOI mo-dun vao registry (App goi 1 lan khi khoi dong). Them mo-dun moi = them 1 dong import DUOI.

IMPORT TINH (khong importlib theo chuoi): PyInstaller phan tich tinh moi thay va dong goi duoc — ban .exe
tung loi "No module named 'core.modun.dang_nhap_cookie'" vi import dong khong duoc thu (2026-09-17).
Import module = tu chay dang_ky(Modun(...)) trong module do. Thu tu tuple = thu tu hien tren menu.
"""

from __future__ import annotations

import importlib

from core import modun

# nhom acc
from core.modun import dang_nhap_cookie, dang_nhap_web, tao_profile, check_tuong
from core.modun import bat_chuyen_nghiep, doi_user_agent, mo_profile, dong_profile, mo_lai_profile
# nhom proxy
from core.modun import doi_proxy, check_proxy, khop_mui_gio, bo_khop_mui_gio
# nhom fanpage
from core.modun import tao_fanpage_acc, tao_fanpage_bm, add_page_bm, tao_bm, xoa_bai
# nhom dang_bai
from core.modun import dang_fanpage_tu_dong, dang_nhom_tu_dong, quet_bai, nhan_tin_ai
# nhom khac
from core.modun import xoa_acc, extension, xoa_cache, doi_ten_file, mo_cung_windows, tuong_tac

#: Cac module mo-dun theo thu tu menu (chinh cac import o tren).
_MODULES = (
    dang_nhap_cookie, dang_nhap_web, tao_profile, check_tuong,
    bat_chuyen_nghiep, doi_user_agent, mo_profile, dong_profile, mo_lai_profile,
    doi_proxy, check_proxy, khop_mui_gio, bo_khop_mui_gio,
    tao_fanpage_acc, tao_fanpage_bm, add_page_bm, tao_bm, xoa_bai,
    dang_fanpage_tu_dong, dang_nhom_tu_dong, quet_bai, nhan_tin_ai,
    xoa_acc, extension, xoa_cache, doi_ten_file, mo_cung_windows, tuong_tac,
)

#: Ten file mo-dun (dung cho cong kien_truc_modun kiem "du trong DANH_SACH").
DANH_SACH = [m.__name__.rsplit(".", 1)[-1] for m in _MODULES]


def nap() -> list[str]:
    """Tra danh sach ma da dang ky (theo thu tu registry). Import tinh o tren da dang ky san;
    neu registry bi xoa (xoa_het trong thuoc) thi reload module de dang_ky chay lai."""
    for mod in _MODULES:
        ma = getattr(mod, "MA", mod.__name__.rsplit(".", 1)[-1])
        if not modun.co(ma):
            importlib.reload(mod)
    return [m.ma for m in modun.danh_sach()]
