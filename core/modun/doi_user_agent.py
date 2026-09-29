"""Mo-dun ĐỔI USER AGENT — nhom acc (truoc day la App.change_user_agent).

tham_so: loai (category trong thu muc useragent/, vd "TV"; RONG = xoa UA, dung mac dinh Firefox).
Moi acc lay MOT UA ngau nhien trong category; ap lai vao profile (mozilla.cfg) cho acc da co
profile. Acc dang mo phai mo lai moi thay (ghi trong ghi_chu). Category rong UA -> ValueError.
"""

from __future__ import annotations

from core import useragent
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "doi_user_agent"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    loai = (tham_so.get("loai") or "").strip()
    if loai and not useragent.doc_loai(loai):
        raise ValueError(f"category “{loai}” chưa có UA nào")
    for a in accs:
        if loai:
            ua = useragent.chon_ngau_nhien(loai)
            if not ua:
                kq.them_loi(a.id, "không chọn được UA")
                continue
            a.extra["user_agent"] = ua
        else:
            a.extra.pop("user_agent", None)
        kq.them_ok(a.id)
    try:
        nc.store.save()
    except Exception:  # noqa: BLE001
        pass
    ap = 0
    dang_mo: list = []
    for a in accs:
        if not nc.manager.is_installed(a):
            continue
        try:
            nc.manager.configure(a)
            ap += 1
        except Exception:  # noqa: BLE001
            pass
        try:
            if nc.manager.is_running(a):
                dang_mo.append(a.id)
        except Exception:  # noqa: BLE001
            pass
    nhan = f"“{loai}”" if loai else "mặc định"
    kq.ghi_chu = (f"UA {nhan}, {ap} profile áp dụng"
                  + (" — acc đang mở phải mở lại mới thấy" if dang_mo else ""))
    kq.du_lieu = {"ap": ap, "dang_mo": dang_mo}
    return kq


dang_ky(Modun(ma=MA, ten="🕶 Đổi user agent", nhom="acc", chay=chay, can_profile=False,
              mo_ta="Gán UA ngẫu nhiên theo category (useragent/), áp vào mozilla.cfg."))
