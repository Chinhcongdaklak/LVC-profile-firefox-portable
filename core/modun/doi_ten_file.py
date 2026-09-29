"""Mo-dun ĐỔI TÊN FILE — nhom khac. Boc core.rename_title: doi ten hang loat theo ke hoach (xem_truoc) hoac
hoan tac lan gan nhat. Khong lien quan acc (accs = []).
tham_so: hanh_dong ∈ {doi_ten, hoan_tac} · folder (bat buoc) · ke_hoach (list, bat buoc khi doi_ten).
KetQua: ok = ["<folder>"] khi khong loi; du_lieu = dict rename_title (ok/bo_qua/loi)."""

from __future__ import annotations

from core import rename_title
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "doi_ten_file"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    hanh_dong = (tham_so.get("hanh_dong") or "").strip()
    folder = tham_so.get("folder") or ""
    if not folder:
        raise ValueError("thiếu tham số folder")
    if hanh_dong == "doi_ten":
        ke_hoach = tham_so.get("ke_hoach")
        if ke_hoach is None:
            raise ValueError("thiếu tham số ke_hoach")
        r = rename_title.doi_ten(folder, ke_hoach, log=nc.log)
        kq.ghi_chu = f"đã đổi {r.get('ok', 0)} file, bỏ qua {r.get('bo_qua', 0)}"
    elif hanh_dong == "hoan_tac":
        r = rename_title.hoan_tac(folder, log=nc.log)
        kq.ghi_chu = f"đã hoàn tác {r.get('ok', 0)} file"
    else:
        raise ValueError("hanh_dong phải là 'doi_ten' hoặc 'hoan_tac'")
    kq.du_lieu = dict(r)
    if r.get("loi"):
        for x in r["loi"]:
            kq.them_loi(folder, str(x)[:160])
    else:
        kq.them_ok(folder)
    return kq


dang_ky(Modun(ma=MA, ten="✏️ Đổi tên file", nhom="khac", chay=chay, can_profile=False,
              mo_ta="Đổi tên hàng loạt trong thư mục theo các bước; hoàn tác được."))
