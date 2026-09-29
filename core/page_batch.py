"""Bo chay tao fanpage theo DOT / VONG (HOP-DONG.md muc core/page_batch.py, ADR-005).

Quy trinh nguoi dung (nguyen van, 2026-09-05): "chon 20 acc, so luong 3, cach nhau
300 phut -> mo 3 acc dau tao page, xong tat, mo 3 acc tiep... den acc cuoi cung
thi dem 300 phut roi bat dau tu acc dau lai. Acc tao khong duoc qua 3 lan loai;
acc checkpoint loai ra luon. Ten tao duoc thi xoa dung ten khac; tao HONG thi doi ten khac
thu lai, 2 lan/vong khong duoc thi XOA ten hong + cho vong sau (ADR-023).
Bo sung 2026-09-11: ten DA LAY de tao thi XOA luon du ket qua the nao (tao duoc / acc khoa /
loi hang muc / tao hong) — khong tra lai hang doi, khong de acc khac lay tao lai.

Module nay KHONG biet tkinter. Moi thu ben ngoai duoc tiem vao:
  tao(acc, ten) -> KetQua        (that: ``tao_mot_page``; thuoc do: ham gia)
  ngu(giay)                       (that: time.sleep)
  su_kien(loai, dict)             (UI ve nhat ky/bang; thuoc do ghi lai de cham)
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from core import fbcreatepage

#: Ma loi trong KetQua["loi"] (xem HOP-DONG.md).
LOI_KHOA = "khoa"            # acc checkpoint/khoa/cam -> loai ngay
LOI_NHAP_LIEU = "nhap_lieu"  # hang muc sai/trong -> dung ca dot (doi acc cung hong)
LOI_HONG = "hong"            # tao hong -> dem cho acc, du max_hong thi loai


def ket_qua(ok: bool, page_id: str = "", loi: str = "", ghi_chu: str = "") -> dict:
    """Tao dict KetQua dung hinh dang hop dong."""
    return {"ok": bool(ok), "page_id": page_id or "", "loi": loi or "", "ghi_chu": ghi_chu or ""}


def _dong(manager, account) -> None:
    try:
        manager.close(account, wait=6.0)
    except Exception:  # noqa: BLE001 - dong trinh duyet that bai khong lam hong ket qua
        pass


def tao_mot_page(manager, account, ten: str, *, category: str, description: str = "",
                 avatar: str = "", cover: str = "", submit: bool = True,
                 ensure_pro: bool = True, pro_done: Optional[set] = None,
                 bm_id: str = "",
                 log: Optional[Callable[[str], None]] = None) -> dict:
    """Mo 1 acc, tao DUNG 1 page (1 ten), LUON dong trinh duyet. Khong nem.

    ``pro_done``: tap id acc da bat che do chuyen nghiep (dung chung ca buoi) -
    moi acc chi bat 1 lan. ``submit=False`` = chay thu: dien form, khong bam Tao.
    ``bm_id``: khac rong -> tao page TU BEN TRONG BM do (khong can che do chuyen
    nghiep), thay vi tao tren acc ca nhan.
    """
    noi = log or (lambda _m: None)
    pro_done = pro_done if pro_done is not None else set()
    tu_bm = bool((bm_id or "").strip())
    try:
        # Tao tu BM khong can che do chuyen nghiep (BM so huu page) -> bo qua buoc pro.
        # Cot "Chuyen nghiep" = Bật (account.pro_mode) -> BO QUA buoc kiem/bat luon;
        # chua bat -> bat truoc roi moi tao (enable_professional xong tu dat pro_mode=bat).
        from . import store as _store
        if _store.da_bat_pro(account):
            pro_done.add(account.id)
        if ensure_pro and submit and not tu_bm and account.id not in pro_done:
            noi(f"[{account.id}] kiểm tra / bật chế độ chuyên nghiệp...")
            try:
                fbcreatepage.enable_professional(manager, account, log=log)
                pro_done.add(account.id)
            except fbcreatepage.AccountBlockedError as exc:
                return ket_qua(False, loi=LOI_KHOA, ghi_chu=str(exc))
            except Exception as exc:  # noqa: BLE001 - bat pro chua chac, van thu tao
                noi(f"[{account.id}] bật chuyên nghiệp chưa chắc ({exc}) — vẫn thử tạo.")
                pro_done.add(account.id)
            finally:
                _dong(manager, account)
        from . import reauth
        # Acc bị logout khi tạo fanpage -> tự đăng nhập lại (cookie -> web) rồi tạo lại.
        kq = reauth.chay_lai_neu_logout(manager, account, lambda: fbcreatepage.create_one(
            manager, account, ten, category=category, description=description,
            avatar=avatar, cover=cover, submit=submit, bm_id=bm_id, log=log), log=log)
        note = kq.get("note") or ""
        if kq.get("created"):
            return ket_qua(True, page_id=str(kq.get("page_id") or ""), ghi_chu=note)
        if not submit and "chạy thử" in note:
            return ket_qua(True, ghi_chu=note)
        return ket_qua(False, loi=LOI_HONG, ghi_chu=note or "không rõ")
    except fbcreatepage.AccountBlockedError as exc:
        return ket_qua(False, loi=LOI_KHOA, ghi_chu=str(exc))
    except fbcreatepage.FormInputError as exc:
        return ket_qua(False, loi=LOI_NHAP_LIEU, ghi_chu=str(exc))
    except Exception as exc:  # noqa: BLE001 - FormError/CreatePageError/loi khac -> hong
        return ket_qua(False, loi=LOI_HONG, ghi_chu=str(exc))
    finally:
        _dong(manager, account)


def chay_theo_dot(accs: list, names: list, *, so_moi_dot: int, nghi_phut: float,
                  tao: Callable[[object, str], dict], max_hong: int = 3,
                  thu_moi_vong: int = 2,
                  mot_vong: bool = False, dung: Callable[[], bool] = lambda: False,
                  ngu: Callable[[float], None] = time.sleep,
                  su_kien: Optional[Callable[[str, dict], None]] = None) -> dict:
    """Chay het danh sach ten bang cac acc theo dot/vong. Xem HOP-DONG.md.

    Bat bien: moi acc tao TOI DA 1 page/vong (thanh cong thi dung luot); khong qua ``so_moi_dot``
    acc mo cung luc. MOI ten da lay de tao deu roi khoi ``con_ten``: OK thi xong, LOI (bat ky ma nao)
    thi phat "bo_ten" — khong tra lai hang doi. Chi ten CHUA thu (dung giua chung) moi con trong ``con_ten``.
    """
    phat = su_kien or (lambda _loai, _d: None)
    so_moi_dot = max(1, int(so_moi_dot))
    lock = threading.Lock()
    pending: list = list(names)        # ten CHUA tao: lay o dau, loi tra ve cuoi
    active: list = list(accs)          # acc con dung duoc, giu thu tu nguoi chon
    so_hong: dict = {}                 # acc_id -> so lan tao hong (cong don)
    acc_loai: list = []                # (acc_id, ly_do)
    dem = {"ok": 0, "nhap_lieu": False}

    def lay_ten():
        with lock:
            return pending.pop(0) if pending else None

    def tra_ten(ten):
        with lock:
            if ten not in pending:
                pending.append(ten)

    def loai(acc, ly_do):
        with lock:
            if not any(a.id == acc.id for a in active):
                return
            active[:] = [a for a in active if a.id != acc.id]
            acc_loai.append((acc.id, ly_do))
        phat("loai_acc", {"acc": acc.id, "ly_do": ly_do})

    def mot_lan(acc, vong):
        """Mot acc trong mot vong: thu tao toi da ``thu_moi_vong`` ten, moi lan hong doi TEN KHAC.

        Tao duoc 1 page -> xong luot acc nay trong vong (det/vong), xoa ten do dung ten khac (yeu cau
        nguoi dung). Bam Tao khong duoc -> XOA ten do (khong giu lai), doi ten khac bam Tao lan nua.
        Du ``thu_moi_vong`` lan hong -> trinh duyet da dong (tao_mot_page dong sau moi lan), cho vong
        sau. Hong het ca ``max_hong`` vong lien -> loai acc de khoi dot chay vo ich."""
        thu = 0
        while thu < max(1, int(thu_moi_vong)):
            ten = lay_ten()
            if ten is None:
                return
            if dung():
                tra_ten(ten)
                return
            try:
                kq = tao(acc, ten)
            except Exception as exc:  # noqa: BLE001 - ham tao phai khong nem; phong ho
                kq = ket_qua(False, loi=LOI_HONG, ghi_chu=f"lỗi: {exc}")
            phat("ten", {"vong": vong, "acc": acc.id, "ten": ten, "kq": kq})
            if kq.get("ok"):
                with lock:
                    dem["ok"] += 1
                    so_hong[acc.id] = 0          # tao duoc -> quen cac vong hong truoc
                return
            ma = kq.get("loi") or LOI_HONG
            ghi = kq.get("ghi_chu") or "tạo hỏng"
            # Ten DA LAY de tao -> BO luon, du loi gi (yeu cau 2026-09-11). Truoc day
            # acc khoa / loi hang muc thi tra ten lai cho acc khac; gio khong tra nua.
            if ma == LOI_KHOA:
                phat("bo_ten", {"vong": vong, "acc": acc.id, "ten": ten, "lan": thu + 1,
                                "toi_da": max(1, int(thu_moi_vong)),
                                "ly_do": f"acc bị khoá/checkpoint: {ghi}"})
                loai(acc, kq.get("ghi_chu") or "bị khoá/checkpoint")
                return
            if ma == LOI_NHAP_LIEU:
                phat("bo_ten", {"vong": vong, "acc": acc.id, "ten": ten, "lan": thu + 1,
                                "toi_da": max(1, int(thu_moi_vong)),
                                "ly_do": f"lỗi hạng mục: {ghi}"})
                with lock:
                    dem["nhap_lieu"] = True
                return
            # LOI_HONG: XOA ten tao khong duoc (khong tra lai), doi ten khac bam Tao lan nua.
            thu += 1
            phat("bo_ten", {"vong": vong, "acc": acc.id, "ten": ten, "lan": thu,
                            "toi_da": max(1, int(thu_moi_vong)),
                            "ly_do": ghi})
        # Du so lan hong trong vong nay: cho vong sau. Hong lien max_hong vong -> loai acc.
        with lock:
            so_hong[acc.id] = so_hong.get(acc.id, 0) + 1
            n = so_hong[acc.id]
        if n >= max_hong:
            loai(acc, f"{n} vòng liền không tạo được page")
        else:
            phat("hong", {"acc": acc.id, "lan": thu, "toi_da": max(1, int(thu_moi_vong)),
                          "vong_hong": n, "ly_do": f"{max(1, int(thu_moi_vong))} lần không tạo được — chờ vòng sau"})

    def ly_do_dung():
        """Tra ma dung neu phai dung ngay, None neu chay tiep."""
        if dung():
            return "dung"
        with lock:
            if dem["nhap_lieu"]:
                return "nhap_lieu"
            if not pending:
                return "xong"
            if not active:
                return "het_acc"
        return None

    vong = 0
    dung_vi = None
    while True:
        dung_vi = ly_do_dung()
        if dung_vi:
            break
        vong += 1
        with lock:
            ds = list(active)
            con_ten = len(pending)
        so_dot = (len(ds) + so_moi_dot - 1) // so_moi_dot
        phat("vong", {"vong": vong, "con_ten": con_ten, "so_acc": len(ds), "so_dot": so_dot})
        for i in range(0, len(ds), so_moi_dot):
            if ly_do_dung():
                break
            with lock:
                con_id = {a.id for a in active}
            dot = [a for a in ds[i:i + so_moi_dot] if a.id in con_id]
            if not dot:
                continue
            phat("dot", {"vong": vong, "dot": i // so_moi_dot + 1, "so_dot": so_dot,
                         "acc": [a.id for a in dot]})
            luong = [threading.Thread(target=mot_lan, args=(a, vong), daemon=True) for a in dot]
            for t in luong:
                t.start()
            for t in luong:
                t.join()
        dung_vi = ly_do_dung()
        if dung_vi:
            break
        if mot_vong:
            dung_vi = "mot_vong"
            break
        if nghi_phut and nghi_phut > 0:
            phat("nghi", {"vong": vong, "phut": nghi_phut})
            con = float(nghi_phut) * 60.0
            while con > 0 and not dung():
                buoc = min(2.0, con)
                ngu(buoc)
                con -= buoc
    with lock:
        return {"tao_duoc": dem["ok"], "con_ten": list(pending),
                "acc_loai": list(acc_loai), "so_vong": vong, "dung_vi": dung_vi}
