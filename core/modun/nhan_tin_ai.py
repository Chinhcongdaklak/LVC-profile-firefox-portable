"""Mo-dun NHẮN TIN AI — nhom dang_bai. Boc fbchat.chay_lich: nhieu vong trong tong_phut phut, moi vong
moi acc tra loi tin den bang Gemini theo kich ban.
tham_so: kich_ban (KichBan, bat buoc), cfg (ai.AiConfig, bat buoc), so_nguoi, tong_phut, cach_phut,
nen_dung (callable -> bool), on_row (callable(acc, rows)). KetQua: ok = accs (chay xong), du_lieu = dict chay_lich."""

from __future__ import annotations

from core import fbchat
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "nhan_tin_ai"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    kb = tham_so.get("kich_ban")
    cfg = tham_so.get("cfg")
    if kb is None or cfg is None:
        raise ValueError("thiếu tham số kich_ban / cfg")
    tong = fbchat.chay_lich(
        nc.manager, list(accs), kb, cfg,
        so_nguoi=int(tham_so.get("so_nguoi", 5)), tong_phut=int(tham_so.get("tong_phut", 60)),
        cach_phut=int(tham_so.get("cach_phut", 15)),
        nen_dung=tham_so.get("nen_dung"), on_row=tham_so.get("on_row"), log=nc.log)
    for a in accs:
        kq.them_ok(a.id)
    kq.du_lieu = dict(tong or {})
    kq.ghi_chu = f"{kq.du_lieu.get('so_vong', 0)} vòng, gửi {kq.du_lieu.get('tong_gui', 0)} tin"
    return kq


dang_ky(Modun(ma=MA, ten="💬 Nhắn tin AI", nhom="dang_bai", chay=chay,
              mo_ta="Gemini tự trả lời tin nhắn bạn bè theo kịch bản, lặp theo thời gian."))
