"""Mo-dun QUÉT BÀI NHÓM — nhom dang_bai. Boc ai_lab.quet_nhieu: nhieu acc song song, moi acc 1 link.
tham_so: pairs [(acc, link)] (bat buoc), count, lab_dir (bat buoc), workers (mac dinh so_luong), on_acc.
accs: bo qua (lay tu pairs). KetQua: ok = acc khong loi; du_lieu["kq"] = list dict quet_nhieu."""

from __future__ import annotations

from core import ai_lab
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "quet_bai"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua(du_lieu={"kq": []})
    pairs = list(tham_so.get("pairs") or [])
    lab_dir = tham_so.get("lab_dir") or ""
    if not pairs or not lab_dir:
        raise ValueError("thiếu tham số pairs / lab_dir")
    count = int(tham_so.get("count") or 0)
    workers = int(tham_so.get("workers") or nc.so_luong or 1)
    rows = ai_lab.quet_nhieu(nc.manager, pairs, count, lab_dir, workers=workers,
                             on_acc=tham_so.get("on_acc"), log=nc.log)
    kq.du_lieu["kq"] = rows
    for r in rows:
        if r.get("loi"):
            kq.them_loi(r.get("acc_id", ""), str(r["loi"])[:160])
        else:
            kq.them_ok(r.get("acc_id", ""))
    tong = sum(len(r.get("rows", [])) for r in rows)
    kq.ghi_chu = f"{tong} bài từ {len(pairs)} acc ({workers} luồng)"
    kq.du_lieu["tong"] = tong
    return kq


dang_ky(Modun(ma=MA, ten="🔎 Quét bài nhóm", nhom="dang_bai", chay=chay,
              mo_ta="Quét bài nhiều nhóm bằng nhiều acc song song (BiDi)."))
