"""Mo-dun TẠO FANPAGE BẰNG BM — nhom fanpage.

Tao MOT fanpage TU BEN TRONG Business Manager (business.facebook.com: Them -> Tao Trang Facebook
moi -> ... -> Tao Trang). Khong can che do chuyen nghiep (BM so huu page). Boc page_batch.tao_mot_page
voi bm_id cua tung acc.
tham_so: nhu tao_fanpage_acc + bm_id (dung chung) HOAC bm_cua: dict[acc_id -> bm_id]. Acc khong co
BM -> loi "hong: chưa có BM" (khong tao nham tren acc).
"""

from __future__ import annotations

from core.modun import KetQua, Modun, NguCanh, dang_ky
from core.modun.tao_fanpage_acc import _tao

MA = "tao_fanpage_bm"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    bm_cua_dict = tham_so.get("bm_cua") or {}
    bm_chung = (tham_so.get("bm_id") or "").strip()

    def bm_cua(a):
        return (bm_cua_dict.get(a.id) or bm_chung or "").strip()

    co = [a for a in accs if bm_cua(a)]
    kq = _tao(nc, co, tham_so, bm_cua) if co else KetQua(du_lieu={"kq": {}})
    for a in accs:
        if a not in co:
            kq.them_loi(a.id, "hong: Tạo từ BM nhưng acc chưa có / không quét được BM")
            kq.du_lieu["kq"][a.id] = {"ok": False, "loi": "hong", "page_id": "",
                                      "ghi_chu": "Tạo từ BM nhưng acc chưa có / không quét được BM"}
    return kq


dang_ky(Modun(ma=MA, ten="🏢 Tạo fanpage bằng BM", nhom="fanpage", chay=chay,
              mo_ta="Tạo 1 page từ trong Business Manager của acc (không cần chuyên nghiệp)."))
