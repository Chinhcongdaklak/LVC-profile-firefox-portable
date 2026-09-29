"""Mo-dun MỞ TOOL CÙNG WINDOWS — nhom khac. Ghi/xoa muc HKCU Run cho chinh tool (core.autostart).
tham_so: bat (bool). accs = []. Luu settings.mo_cung_windows. KetQua.ok = ["windows"] khi ghi duoc."""

from __future__ import annotations

from core import autostart
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "mo_cung_windows"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    bat = bool(tham_so.get("bat", True))
    if nc.settings is not None:
        try:
            nc.settings.mo_cung_windows = bat
            nc.settings.save()
        except Exception:  # noqa: BLE001
            pass
    if autostart.bat_cung_windows(bat):
        kq.them_ok("windows")
        kq.ghi_chu = "tool sẽ tự mở khi đăng nhập Windows" if bat else "đã tắt mở cùng Windows"
    else:
        kq.them_loi("windows", "không ghi được khóa Run của Windows (không phải Windows hoặc bị chặn)")
    kq.du_lieu = {"bat": bat, "lenh": autostart.lenh_khoi_dong_tool()}
    return kq


dang_ky(Modun(ma=MA, ten="🚀 Mở cùng Windows", nhom="khac", chay=chay, can_profile=False,
              mo_ta="Bật/tắt tool tự mở khi đăng nhập Windows (mặc định bật)."))
