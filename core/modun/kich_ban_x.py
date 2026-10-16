"""Mo-dun KICH BAN TUONG TAC X — nhom khac (nguoi dung chot 15/10).

Moi acc chay MAU KICH BAN cua no (chuoi node Luot newfeed -> Follow kenh -> Dang lai trich dan
-> Nghi..., core.kich_ban_x) trong MOT lan mo trinh duyet (core.xwatch.chay_kich_ban).
List kenh follow / trich dan RIENG tung acc lay tu kho; follow xong thi xoa kenh khoi list cua
acc do. Song song theo so_luong (moi acc 1 Firefox, profile X rieng). So chong trung trich dan
dung CHUNG giua cac luong.

tham_so: kho (core.kich_ban_x.KhoKichBan; khong truyen -> nap data/kich_ban_x.json), so_luong,
thu (khong bam Dang/Follow-xoa list), lay_lich_su (tiem — thuoc), on_row(callable(acc_id, dict)),
nen_dung(callable()->bool).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from core import kich_ban_x as kbx
from core import xwatch
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "kich_ban_x"

_TT_LOI = {"vpn-loi": "⛔ VPN chưa nối — KHÔNG chạy",
           "logged-out": "⛔ acc đã đăng xuất x.com",
           "x-locked": "⛔ acc bị X khoá/treo",
           "browser-gone": "⛔ trình duyệt bị đóng giữa chừng",
           "thieu-node": "⛔ mẫu không có node nào đang bật"}


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    kho = tham_so.get("kho") or kbx.KhoKichBan()
    so_luong = int(tham_so.get("so_luong", 0) or nc.so_luong or 1)
    thu = bool(tham_so.get("thu"))
    on_row = tham_so.get("on_row")
    nen_dung = tham_so.get("nen_dung")
    lay_ls = tham_so.get("lay_lich_su")
    if lay_ls is None:
        from core.quote_lich_su import LichSuQuote
        _ls: dict = {}
        _ls_khoa = threading.Lock()

        def lay_ls(chung: bool):                 # MOT so moi kieu, dung chung moi luong
            with _ls_khoa:
                if chung not in _ls:
                    _ls[chung] = LichSuQuote(chung=chung)
                return _ls[chung]
    lock = threading.Lock()
    tong = {"xem": 0, "like": 0, "video": 0, "cmt": 0, "follow": 0, "quote": 0}

    def bao(acc_id, info) -> None:
        if callable(on_row):
            try:
                on_row(acc_id, info)
            except Exception:  # noqa: BLE001
                pass

    def mot_acc(a) -> None:
        if callable(nen_dung) and nen_dung():
            return
        ten, nodes = kho.mau_cua_acc(a.id)
        bao(a.id, {"tt": "đang chạy", "mau": ten, "node": ""})

        def tien(i, loai, mo_ta):
            bao(a.id, {"node": f"{i + 1}. {kbx.TEN_NODE.get(loai, loai)} — {mo_ta}"})

        def _chay_1():
            with kho._khoa:
                kenh_fl = xwatch.tach_kenh(kho.acc_follow.get(a.id, ""))
                kenh_qt = xwatch.tach_kenh(kho.acc_quote.get(a.id, ""))
                tu = kho.acc_tu_khoa.get(a.id, "")
            return xwatch.chay_kich_ban(nc.manager, a, nodes, kenh_follow=kenh_fl, kenh_quote=kenh_qt, tu_khoa=tu,
                                        lay_lich_su=lay_ls,
                                        xoa_follow=lambda h: kho.xoa_kenh_follow(a.id, h),
                                        on_tien_do=tien, thu=thu, nen_dung=nen_dung, log=nc.log)

        r = _chay_1()
        if r.get("state") == "logged-out":
            # Acc X bi dang xuat -> nap lai cookie X roi chay lai kich ban MOT lan.
            try:
                from core import modun as _modun
                nc.log(f"[{a.id}] bị đăng xuất — nạp lại cookie rồi chạy lại kịch bản...")
                dn = _modun.chay("dang_nhap_cookie", nc, [a])
                if a.id in dn.ok:
                    r = _chay_1()
                else:
                    r["detail"] = "đăng xuất; nạp cookie lại KHÔNG được"
            except Exception as exc:  # noqa: BLE001
                r["detail"] = f"đăng xuất; thử đăng nhập lại lỗi: {exc}"
        st = str(r.get("state") or "")
        t = r.get("tong") or {}
        with lock:
            for k in tong:
                tong[k] += int(t.get(k) or 0)
            if r.get("ok"):
                kq.them_ok(a.id)
                tt = "xong" + (" (dừng giữa chừng)" if st == "dung" else "") + (" — chạy thử" if thu else "")
            else:
                kq.them_loi(a.id, r.get("detail") or st or "lỗi")
                tt = _TT_LOI.get(st, f"không làm được gì ({r.get('detail') or st})")
        bao(a.id, {"tt": tt, "node": "", "tong": dict(t), "nodes": list(r.get("nodes") or [])})

    workers = max(1, min(so_luong, len(accs) or 1))
    if workers <= 1:
        for a in accs:
            if callable(nen_dung) and nen_dung():
                break
            mot_acc(a)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(mot_acc, accs))
    kq.ghi_chu = (f"kịch bản X {len(accs)} acc ({workers} luồng) — xem {tong['xem']} · ♥ {tong['like']}"
                  f" · 💬 {tong['cmt']} · ▶ {tong['video']} · follow {tong['follow']}"
                  f" · trích dẫn {tong['quote']}")
    kq.du_lieu = {"tong": tong}
    return kq


dang_ky(Modun(ma=MA, ten="🎬 Kịch bản tương tác X", nhom="khac", chay=chay,
              mo_ta="Mỗi acc chạy mẫu kịch bản của nó: lướt newfeed → follow kênh → đăng lại "
                    "trích dẫn (một lần mở trình duyệt)."))
