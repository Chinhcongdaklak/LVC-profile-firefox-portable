"""Mo-dun KHỚP MÚI GIỜ + NGÔN NGỮ THEO PROXY — nhom proxy (truoc day la App.match_identities).

Do quoc gia that cua proxy (geoip) roi dat mui gio/ngon ngu cho profile khop (manager.match_identity).
tham_so: khong co. Acc chua co proxy -> loi "chưa gán proxy".
"""

from __future__ import annotations

from core import geoip
from core.modun import KetQua, Modun, NguCanh, dang_ky
from core.profiles import ProfileError

MA = "khop_mui_gio"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    targets = [a for a in accs if a.get_proxy().enabled]
    for a in accs:
        if a not in targets:
            kq.them_loi(a.id, "chưa gán proxy nên không có gì để dò")
    for i, a in enumerate(targets, start=1):
        nc.log(f"[{i}/{len(targets)}] Đang dò vị trí {a.id}...")
        try:
            identity = nc.manager.match_identity(a)
        except (geoip.GeoLookupError, ProfileError, OSError) as exc:
            kq.them_loi(a.id, str(exc).replace("\n", " ")[:160])
            continue
        kq.them_ok(a.id)
        nc.log(f"[{i}/{len(targets)}] {a.id} → {identity.summary()}")
    try:
        nc.store.save()
    except Exception:  # noqa: BLE001
        pass
    kq.ghi_chu = f"khớp {kq.so_ok}/{len(targets)} acc có proxy"
    return kq


dang_ky(Modun(ma=MA, ten="🕒 Khớp múi giờ + ngôn ngữ theo proxy", nhom="proxy", chay=chay,
              mo_ta="Dò quốc gia của proxy, đặt múi giờ/ngôn ngữ profile cho khớp."))
