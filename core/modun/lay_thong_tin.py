"""Mo-dun LAY TEN + NGAY SINH cua acc Facebook -> hai cot moi o tab Quan ly acc.

Hai duong khac han nhau (xem core/fbthongtin.py de biet vi sao):
  * TEN: HTTP bang cookie rieng cua acc -> NHANH, SONG SONG, khong mo trinh duyet.
  * NGAY SINH: BUOC phai mo trinh duyet (chi Trung tam tai khoan moi hien) -> TUAN TU, cham.

tham_so:
  ngay_sinh (mac dinh True)  — co lay ngay sinh khong (tat = chi lay ten, khong mo browser).
  lam_moi   (mac dinh False) — True thi lay lai ca acc DA CO; False chi lay acc con thieu.
  so_luong  — so acc lay ten cung luc (mac dinh theo o "Luong").
  toi_da_ngay_sinh (0 = khong gioi han) — tran so acc mo browser MOT luot, de luc mo tool
             khong bung hang chuc Firefox.
"""

from __future__ import annotations

from core import fbthongtin as tt
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "lay_thong_tin"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    lay_ns = bool(tham_so.get("ngay_sinh", True))
    lam_moi = bool(tham_so.get("lam_moi", False))
    so_luong = int(tham_so.get("so_luong", 0) or nc.so_luong or 1)
    tran_ns = int(tham_so.get("toi_da_ngay_sinh", 0) or 0)

    doi = False  # co gi moi thi moi luu store

    # ---- 1) TEN qua cookie (song song, khong mo trinh duyet)
    can_ten = list(accs) if lam_moi else tt.thieu_ten(accs)
    so_ten = 0
    if can_ten:
        nc.log(f"Lấy tên {len(can_ten)} acc bằng cookie (không mở trình duyệt)…")
        theo_id = {str(a.id): a for a in can_ten}
        items = [(str(a.id), a.cookie or "", a.get_proxy()) for a in can_ten]
        for r in tt.lay_ten_nhieu(items, workers=so_luong):
            acc = theo_id.get(r["id"])
            if acc is None:
                continue
            if r["ten"]:
                if tt.dat_ten(acc, r["ten"]):
                    doi = True
                so_ten += 1
                nc.log(f"{r['id']}: tên = {r['ten']}")
            else:
                kq.them_loi(r["id"], f"tên: {r['loi']}")
    else:
        nc.log("Mọi acc đã có tên — không cần lấy lại.")

    # ---- 2) NGAY SINH qua trinh duyet (tuan tu — moi acc mot Firefox)
    so_ns = 0
    bo_qua_tran = 0
    if lay_ns:
        can_ns = list(accs) if lam_moi else tt.thieu_ngay_sinh(accs)
        # Cookie chet thi mo browser cung vo ich -> bo qua cho nhanh.
        can_ns = [a for a in can_ns if tt.co_c_user(a.cookie or "")]
        if tran_ns > 0 and len(can_ns) > tran_ns:
            bo_qua_tran = len(can_ns) - tran_ns
            can_ns = can_ns[:tran_ns]
        if can_ns:
            nc.log(f"Lấy ngày sinh {len(can_ns)} acc — phải mở trình duyệt, chạy lần lượt…")
        for acc in can_ns:
            r = tt.lay_bang_trinh_duyet(nc.manager, acc, log=nc.log)
            if r["ngay_sinh"]:
                if tt.dat_ngay_sinh(acc, r["ngay_sinh"]):
                    doi = True
                so_ns += 1
                nc.log(f"{acc.id}: ngày sinh = {r['ngay_sinh']}")
            else:
                kq.them_loi(str(acc.id), f"ngày sinh: {r['loi']}")
            # Trang nay cung hien ten -> acc nao HTTP khong lay duoc thi vot o day.
            if r["ten"] and tt.dat_ten(acc, r["ten"]):
                doi = True
                so_ten += 1

    if doi and nc.store is not None:
        nc.store.save()

    for acc in accs:
        if tt.ten_cua(acc) or tt.ngay_sinh_cua(acc):
            kq.them_ok(str(acc.id))
    phan = [f"tên {so_ten}"]
    if lay_ns:
        phan.append(f"ngày sinh {so_ns}")
    kq.ghi_chu = "Đã lấy " + " · ".join(phan) + f" trên {len(accs)} acc"
    if bo_qua_tran:
        kq.ghi_chu += f" (còn {bo_qua_tran} acc để lượt sau)"
    kq.du_lieu = {"so_ten": so_ten, "so_ngay_sinh": so_ns, "con_lai": bo_qua_tran}
    return kq


dang_ky(Modun(ma=MA, ten="🪪 Lấy tên + ngày sinh", nhom="acc", chay=chay,
              mo_ta="Tên lấy bằng cookie (nhanh); ngày sinh phải mở trình duyệt đọc "
                    "Trung tâm tài khoản."))
