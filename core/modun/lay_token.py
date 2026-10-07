"""Mo-dun LAY TOKEN Graph cua acc -> ghi vao cot "Token" (account.extra["token"]).

Cach lay (nguoi dung chi 07/10): vao business.facebook.com/business_locations/ (phien da nhap 2FA)
roi doc dong EAAG. Thu HAI duong (core.fbxoabai.token_tu_cookie):
  1) HTTP: GET business_locations kem cookie -> NHANH, khong mo trinh duyet (chi an khi cookie con
     du manh cho business.facebook.com);
  2) khong ra -> mo trinh duyet acc, vao business_locations, quet EAAG.

derive_token dung MOT cong BiDi -> PHAI tuan tu (khong song song).
tham_so: lam_moi (mac dinh False — chi lay acc CHUA co token).
Token la BI MAT: chi luu extra["token"] (data/ gitignore), log chi in ban CHE.
"""

from __future__ import annotations

from core import fbxoabai as xb
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "lay_token"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    lam_moi = bool(tham_so.get("lam_moi", False))
    can = [a for a in accs
           if lam_moi or not str((getattr(a, "extra", None) or {}).get("token") or "").strip()]
    if not can:
        kq.ghi_chu = "mọi acc đã có token (tích Làm mới để lấy lại)"
        for a in accs:
            kq.them_ok(str(a.id))
        return kq

    nc.log(f"Lấy token {len(can)} acc — vào business_locations lấy dòng EAAG (lần lượt từng acc)…")
    so_ok = 0
    for a in can:
        tok, loi = xb.token_tu_cookie(nc.manager, a, log=nc.log)
        if tok:
            if not isinstance(getattr(a, "extra", None), dict):
                a.extra = {}
            a.extra["token"] = tok
            so_ok += 1
            kq.them_ok(str(a.id))
            nc.log(f"[{a.id}] token: {xb.che_token(tok)} ✓")
        else:
            kq.them_loi(str(a.id), f"token: {loi}")
            nc.log(f"[{a.id}] không lấy được token: {loi}")

    if so_ok and nc.store is not None:
        nc.store.save()
    kq.ghi_chu = f"Lấy token {so_ok}/{len(can)} acc"
    if so_ok < len(can):
        kq.ghi_chu += " — acc còn lại dán token tay vào cột Token"
    kq.du_lieu = {"so_ok": so_ok, "so_can": len(can)}
    return kq


dang_ky(Modun(ma=MA, ten="🔑 Lấy token (business_locations)", nhom="acc", chay=chay,
              can_profile=False,
              mo_ta="Vào business_locations lấy dòng EAAG; cookie yếu thì mở trình duyệt. "
                    "Ghi vào cột Token."))
