"""Mo-dun EXTENSION — nhom khac (truoc day la App.install_extension / remove_extension).
tham_so: hanh_dong ∈ {cai, go} · xpi (duong dan .xpi, bat buoc khi cai) · addon_ids (list, tuy chon khi go;
mac dinh go moi extension dang cai). Acc dang mo duoc dong truoc (Firefox chi quet thu muc extension luc
khoi dong). du_lieu: addon_id/version khi cai."""

from __future__ import annotations

import time

from core.modun import KetQua, Modun, NguCanh, dang_ky
from core.profiles import ProfileError

MA = "extension"


def _dong_neu_mo(nc: NguCanh, a) -> None:
    if nc.manager.is_running(a):
        nc.manager.close(a)
        time.sleep(1.5)


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    hanh_dong = (tham_so.get("hanh_dong") or "").strip()
    if hanh_dong == "cai":
        xpi = (tham_so.get("xpi") or "").strip()
        if not xpi:
            raise ValueError("thiếu tham số xpi")
        addon_id, version = nc.manager.read_extension_info(xpi)     # nem ProfileError neu file hong
        kq.du_lieu = {"addon_id": addon_id, "version": version}
        dung = [a for a in accs if nc.manager.is_installed(a)]
        for a in accs:
            if a not in dung:
                kq.them_loi(a.id, "chưa có profile")
        for i, a in enumerate(dung, start=1):
            nc.log(f"[{i}/{len(dung)}] Cài extension cho {a.id}...")
            try:
                _dong_neu_mo(nc, a)
                nc.manager.install_extension(a, xpi)
                kq.them_ok(a.id)
            except (ProfileError, OSError) as exc:
                kq.them_loi(a.id, str(exc)[:160])
        kq.ghi_chu = f"đã cài {addon_id} v{version} — mở lại trình duyệt để Firefox nhận addon"
        return kq
    if hanh_dong == "go":
        muon = tham_so.get("addon_ids")
        go_duoc = 0
        for a in accs:
            try:
                co = [n[:-4] if n.endswith(".xpi") else n for n in nc.manager.installed_extensions(a)]
            except Exception:  # noqa: BLE001
                co = []
            ds = [x for x in co if (not muon or x in muon)]
            if not ds:
                kq.them_loi(a.id, "chưa cài extension nào")
                continue
            _dong_neu_mo(nc, a)
            n_acc = 0
            for addon_id in ds:
                if nc.manager.remove_extension(a, addon_id):
                    n_acc += 1
            go_duoc += n_acc
            kq.them_ok(a.id)
        kq.ghi_chu = f"đã gỡ extension khỏi {go_duoc} profile"
        kq.du_lieu = {"go_duoc": go_duoc}
        return kq
    raise ValueError("hanh_dong phải là 'cai' hoặc 'go'")


dang_ky(Modun(ma=MA, ten="🧩 Extension (cài / gỡ)", nhom="khac", chay=chay,
              mo_ta="Cài file .xpi đã ký vào profile hoặc gỡ extension đang cài."))
