"""Mo-dun TẠO FANPAGE BẰNG ACC — nhom fanpage.

Tao MOT fanpage tren acc ca nhan (form facebook.com/pages/creation): can che do chuyen nghiep
(cot 'Chuyen nghiep' = Bật thi bo qua buoc bat, chua bat thi bat truoc). Boc page_batch.tao_mot_page
(bm_id=""). Goi cho TUNG acc trong accs voi CUNG ten (thuong 1 acc/lan; bo chay theo dot o tab).
tham_so: ten (bat buoc), category (bat buoc), description, avatar, cover, submit=True,
         ensure_pro=True, pro_done (set dung chung buoi).
KetQua: ok = acc tao duoc; loi = (acc, "<loai>: <ghi chu>"); du_lieu["kq"][acc] = dict page_batch
(ok/page_id/loi/ghi_chu) de tab dieu phoi (loai acc / doi ten / cho vong sau) nhu cu.
"""

from __future__ import annotations

from core import page_batch
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "tao_fanpage_acc"


def _tao(nc: NguCanh, accs: list, tham_so: dict, bm_cua) -> KetQua:
    kq = KetQua()
    ten = (tham_so.get("ten") or "").strip()
    category = (tham_so.get("category") or "").strip()
    if not ten or not category:
        raise ValueError("thiếu tham số ten / category")
    pro_done = tham_so.get("pro_done")
    if pro_done is None:
        pro_done = set()
    kq.du_lieu["kq"] = {}
    for a in accs:
        bm_id = bm_cua(a) if bm_cua else ""
        r = page_batch.tao_mot_page(
            nc.manager, a, ten, category=category,
            description=tham_so.get("description", "") or "",
            avatar=tham_so.get("avatar", "") or "", cover=tham_so.get("cover", "") or "",
            submit=bool(tham_so.get("submit", True)),
            ensure_pro=bool(tham_so.get("ensure_pro", True)), pro_done=pro_done,
            bm_id=bm_id or "", log=nc.log)
        kq.du_lieu["kq"][a.id] = r
        if r.get("ok"):
            kq.them_ok(a.id)
        else:
            kq.them_loi(a.id, f"{r.get('loi') or 'hong'}: {r.get('ghi_chu') or ''}".strip(": "))
    return kq


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    return _tao(nc, accs, tham_so, None)


dang_ky(Modun(ma=MA, ten="🧑 Tạo fanpage bằng acc", nhom="fanpage", chay=chay,
              mo_ta="Tạo 1 page trên acc cá nhân (/pages/creation); tự bật chuyên nghiệp nếu chưa."))
