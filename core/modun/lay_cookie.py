"""Mo-dun LAY LAI COOKIE — doc cookie dang song trong profile roi ghi nguoc vao acc.

Dung khi: acc da dang nhap san trong trinh duyet (dang nhap tay / dang nhap web) ma cookie
luu trong tool con la ban CU -> lay ban moi de lan sau "Dang nhap voi cookie" con an.

tham_so: dong_truoc (mac dinh True — dong Firefox cua acc truoc khi doc cho day du),
so_luong (so acc chay cung luc; mac dinh lay tu NguCanh).
Acc chua dang nhap (khong co c_user) -> bao loi, GIU NGUYEN cookie cu.
"""

from __future__ import annotations

from core import cookie_moi
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "lay_cookie"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    dong_truoc = bool(tham_so.get("dong_truoc", True))
    so_luong = int(tham_so.get("so_luong", 0) or nc.so_luong or 1)

    r = cookie_moi.lay_lai_nhieu(nc.manager, accs, workers=so_luong,
                                 dong_truoc=dong_truoc, log=nc.log)
    for ma in r["ok"]:
        kq.them_ok(ma)
    for ma, ly_do in r["hong"]:
        kq.them_loi(ma, ly_do)
    kq.ghi_chu = f"lấy lại cookie {len(r['ok'])}/{r['so']} acc"
    if r["hong"]:
        kq.ghi_chu += f" — {len(r['hong'])} acc chưa đăng nhập trong profile"
    kq.du_lieu = {"so_ok": len(r["ok"]), "so_hong": len(r["hong"])}
    return kq


dang_ky(Modun(ma=MA, ten="🍪 Lấy lại cookie mới", nhom="acc", chay=chay,
              mo_ta="Đọc cookie đang sống trong profile rồi ghi đè cookie cũ của acc."))
