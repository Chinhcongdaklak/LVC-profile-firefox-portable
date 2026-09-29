"""Mo-dun ADD PAGE VÀO BM — nhom fanpage. Boc fbbm.add_het_page_vao_bm (add TAT CA page acc so huu
vao BM, page da co trong BM thi bo qua), song song theo so_luong.
tham_so: bm_cua: dict[acc_id -> bm_id] HOAC bm_id dung chung. Acc khong co BM -> loi.
KetQua: ok = acc add duoc >=1 page hoac moi page da co san; du_lieu["rows"][acc] = dict fbbm.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from core import fbbm
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "add_page_bm"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua(du_lieu={"rows": {}})
    bm_cua_dict = tham_so.get("bm_cua") or {}
    bm_chung = (tham_so.get("bm_id") or "").strip()
    co = []
    for a in accs:
        bm = (bm_cua_dict.get(a.id) or bm_chung or "").strip()
        if bm:
            co.append((a, bm))
        else:
            kq.them_loi(a.id, "chưa có ID BM")
    if not co:
        return kq
    workers = max(1, min(int(nc.so_luong or 1), len(co)))
    lock = threading.Lock()

    def mot(cap):
        a, bm = cap
        try:
            r = fbbm.add_het_page_vao_bm(nc.manager, a, bm, log=nc.log)
        except Exception as exc:  # noqa: BLE001
            r = {"bm_id": bm, "tong": 0, "ok": 0, "bo_qua": 0, "rows": [], "loi": str(exc)[:160]}
        with lock:
            kq.du_lieu["rows"][a.id] = r
            if r.get("ok", 0) > 0 or (r.get("tong", 0) > 0 and r.get("bo_qua", 0) == r.get("tong", 0)):
                kq.them_ok(a.id)
            else:
                kq.them_loi(a.id, r.get("loi") or f"add 0/{r.get('tong', 0)} page")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(mot, co))
    tong_ok = sum(r.get("ok", 0) for r in kq.du_lieu["rows"].values())
    tong_bo = sum(r.get("bo_qua", 0) for r in kq.du_lieu["rows"].values())
    kq.ghi_chu = f"add {tong_ok} page, bỏ qua {tong_bo} page đã có ({workers} luồng)"
    return kq


dang_ky(Modun(ma=MA, ten="➕ Add page vào BM", nhom="fanpage", chay=chay,
              mo_ta="Add hết page của acc vào BM (page đã có thì bỏ qua)."))
