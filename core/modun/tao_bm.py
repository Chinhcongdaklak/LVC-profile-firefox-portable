"""Mo-dun TẠO BM — nhom fanpage. Boc fbbm.tao_bm: tao 1 Business Manager cho acc (ten BM = ten acc
FB, email = recovery_mail cua acc tru khi truyen email). Tuan tu.
tham_so: email (dung chung, tuy chon). KetQua: ok = acc tao duoc; du_lieu["bm"][acc] = {bm_id, ten_bm}.
"""

from __future__ import annotations

from core import fbbm
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "tao_bm"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua(du_lieu={"bm": {}})
    email_chung = (tham_so.get("email") or "").strip()
    for a in accs:
        email = email_chung or (getattr(a, "recovery_mail", "") or "")
        try:
            r = fbbm.tao_bm(nc.manager, a, email=email, log=nc.log)
        except Exception as exc:  # noqa: BLE001
            r = {"ok": False, "bm_id": "", "ten_bm": "", "detail": str(exc)[:160]}
        if r.get("ok") and r.get("bm_id"):
            kq.them_ok(a.id)
            kq.du_lieu["bm"][a.id] = {"bm_id": str(r["bm_id"]), "ten_bm": str(r.get("ten_bm", ""))}
        else:
            kq.them_loi(a.id, r.get("detail") or "không tạo được BM")
    return kq


dang_ky(Modun(ma=MA, ten="🏢 Tạo BM", nhom="fanpage", chay=chay,
              mo_ta="Tạo Business Manager cho acc chưa có (tên = tên acc FB, email = mail khôi phục)."))
