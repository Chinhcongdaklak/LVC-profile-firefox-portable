"""Mo-dun CHECK TƯỜNG (live/die) — nhom acc. KHONG mo trinh duyet (ADR-020).

Dung cookie RIENG tung acc (uu tien cookie TUOI trong profile) goi HTTP mbasic/me qua
core.checkwall.check_nhieu song song theo so_luong; cap nhat account.status.
tham_so: khong co. du_lieu["rows"] = ket qua tung acc.
"""

from __future__ import annotations

from core import checkwall
from core import cookies as cookie_module
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "check_tuong"


def cookie_cua_acc(manager, account) -> str:
    """Cookie de check: uu tien cookie TUOI trong profile (co c_user), khong co thi cookie da luu.
    (Truoc day la App._cookie_cua_acc.)"""
    try:
        if manager.is_installed(account):
            found = cookie_module.read_from_profile(manager.profile_dir(account))
            if any(c.name == "c_user" for c in found):
                return cookie_module.to_json(found)
    except Exception:  # noqa: BLE001
        pass
    return account.cookie or ""


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    if not accs:
        kq.ghi_chu = "chưa chọn acc"
        return kq
    items = [(a.id, cookie_cua_acc(nc.manager, a), a.get_proxy()) for a in accs]
    by_id = {a.id: a for a in accs}
    workers = max(1, min(int(nc.so_luong or 1), len(items)))
    xong = {"n": 0}

    def on_row(r: dict) -> None:
        acc = by_id.get(r["id"])
        if acc is not None:
            acc.status = r["trang_thai"]
        xong["n"] += 1
        nc.log(f"[{xong['n']}/{len(items)}] {r['id']}: {r['trang_thai']}")
        nc.post(lambda: None)

    rows = checkwall.check_nhieu(items, workers=workers, on_row=on_row)
    for r in rows:
        if r["trang_thai"] == checkwall.LIVE:
            kq.them_ok(r["id"])
        else:
            kq.them_loi(r["id"], f"{r['trang_thai']} — {r.get('chi_tiet', '')}".strip(" —"))
    try:
        nc.store.save()
    except Exception:  # noqa: BLE001
        pass
    dem: dict = {}
    for r in rows:
        dem[r["trang_thai"]] = dem.get(r["trang_thai"], 0) + 1
    kq.ghi_chu = " · ".join(f"{k}: {v}" for k, v in dem.items())
    kq.du_lieu = {"rows": rows, "dem": dem}
    return kq


dang_ky(Modun(ma=MA, ten="🧱 Check tường (live/die)", nhom="acc", chay=chay, can_profile=False,
              mo_ta="HTTP bằng cookie từng acc, không mở trình duyệt; cập nhật cột Trạng thái."))
