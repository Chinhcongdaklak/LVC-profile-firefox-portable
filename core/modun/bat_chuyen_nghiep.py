"""Mo-dun BẬT CHẾ ĐỘ CHUYÊN NGHIỆP — nhom acc (truoc day la App.enable_professional_selected).

Mo profile tung acc, agent bam "Bật" (fbcreatepage.enable_professional; nhan dien ca man gioi thieu
tu bat len), song song theo so_luong. Bat xong core tu dat account.pro_mode=bat -> cot "Chuyen nghiep".
tham_so: khong co.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from core import fbcreatepage
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "bat_chuyen_nghiep"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    dung = [a for a in accs if nc.manager.is_installed(a)]
    for a in accs:
        if a not in dung:
            kq.them_loi(a.id, "chưa có profile")
    if not dung:
        kq.ghi_chu = "các acc chưa có profile"
        return kq
    workers = max(1, min(int(nc.so_luong or 1), len(dung)))
    lock = threading.Lock()
    dem = {"xong": 0}

    def mot(acc) -> None:
        try:
            r = fbcreatepage.enable_professional(
                nc.manager, acc, log=lambda m, a=acc: nc.log(f"{a.id}: {m}"))
            with lock:
                if r.get("done"):
                    kq.them_ok(acc.id)
                else:
                    kq.them_loi(acc.id, r.get("note") or "chưa bật được")
        except Exception as exc:  # noqa: BLE001
            with lock:
                kq.them_loi(acc.id, str(exc)[:160])
        finally:
            try:
                nc.manager.close(acc, wait=6.0)
            except Exception:  # noqa: BLE001
                pass
            with lock:
                dem["xong"] += 1
                nc.log(f"[{dem['xong']}/{len(dung)}] {acc.id}: bật chuyên nghiệp xong.")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(mot, dung))
    try:
        nc.store.save()          # pro_mode=bat da duoc core dat -> luu de cot cap nhat
    except Exception:  # noqa: BLE001
        pass
    kq.ghi_chu = f"{workers} luồng"
    return kq


dang_ky(Modun(ma=MA, ten="💼 Bật chế độ chuyên nghiệp", nhom="acc", chay=chay,
              mo_ta="Mở profile, bấm Bật (kể cả màn giới thiệu tự bật lên); cập nhật cột Chuyên nghiệp."))
