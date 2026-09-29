"""Mo-dun TƯƠNG TÁC — nhom khac. Kiểm quyền cá nhân/Page -> về cá nhân -> vào /reel/ ->
xem N video + thả L like trong GIỚI HẠN NGẪU NHIÊN x..y GIÂY / acc. Chạy TỪNG acc (song song
theo so_luong; mỗi acc 1 Firefox). Acc bị đăng xuất giữa chừng -> gọi mô-đun đăng nhập rồi thử lại.

tham_so: so_video, so_like, so_thong_bao, gioi_han_min/gioi_han_max (GIÂY, chọn ngẫu nhiên mỗi acc),
so_luong, url, on_row(callable(acc_id, dict)), nen_dung(callable()->bool).
"""

from __future__ import annotations

import random
import threading
from concurrent.futures import ThreadPoolExecutor

from core import fbwatch
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "tuong_tac"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    so_video = int(tham_so.get("so_video", 10))
    so_like = int(tham_so.get("so_like", 0))
    so_thong_bao = int(tham_so.get("so_thong_bao", 0))
    # GIOI HAN tuong tac 1 acc: ngau nhien tu x den y GIAY (nguoi dung nhap). Fallback so_phut (phut).
    gh_min = int(tham_so.get("gioi_han_min", 0) or 0)
    gh_max = int(tham_so.get("gioi_han_max", 0) or 0)
    if gh_min <= 0 and gh_max <= 0:
        gh_min = gh_max = max(1, int(tham_so.get("so_phut", 1))) * 60
    gh_min = max(1, gh_min)
    gh_max = max(gh_min, gh_max)
    # Thoi gian xem MOI video (giay) — giu mac dinh trong (khong con o UI).
    xem_min = int(tham_so.get("xem_giay_min", 6))
    xem_max = int(tham_so.get("xem_giay_max", 14))
    # So LUONG chay song song: nguoi dung tu nhap (mac dinh 1 = tuan tu). Moi acc 1 Firefox rieng.
    so_luong = int(tham_so.get("so_luong", 0) or nc.so_luong or 1)
    url = tham_so.get("url") or fbwatch.REEL_URL
    on_row = tham_so.get("on_row")
    nen_dung = tham_so.get("nen_dung")      # callable() -> True để dừng sớm
    lock = threading.Lock()
    tong = {"xem": 0, "like": 0, "tb": 0}

    def mot_acc(a) -> None:
        if callable(nen_dung) and nen_dung():
            return
        if callable(on_row):
            try:
                on_row(a.id, {"tt": "đang chạy"})
            except Exception:  # noqa: BLE001
                pass
        gh = random.randint(gh_min, gh_max)     # giới hạn NGẪU NHIÊN cho acc này (giây)

        def _chay_1():
            return fbwatch.tuong_tac(nc.manager, a, so_video=so_video, gioi_han_giay=gh,
                                     so_like=so_like, so_thong_bao=so_thong_bao,
                                     xem_giay_min=xem_min, xem_giay_max=xem_max, url=url, log=nc.log)
        r = _chay_1()
        # Acc bi DANG XUAT giua chung -> goi MO-DUN dang nhap (cookie -> web) roi TUONG TAC LAI 1 lan.
        if r.get("state") == "logged-out":
            from core import reauth
            nc.log(f"[{a.id}] bị đăng xuất khi tương tác — gọi mô-đun đăng nhập lại...")
            dn = reauth.dang_nhap_lai(nc.manager, a, store=nc.store, settings=nc.settings, log=nc.log)
            if dn.get("ok"):
                nc.log(f"[{a.id}] đã đăng nhập lại ({dn.get('cach')}) — tương tác lại.")
                r = _chay_1()
            else:
                r["detail"] = f"đăng xuất; đăng nhập lại KHÔNG được: {dn.get('detail')}"
        with lock:
            tong["xem"] += int(r.get("xem") or 0)
            tong["like"] += int(r.get("like") or 0)
            tong["tb"] += int(r.get("tb") or 0)
            if r.get("ok"):
                kq.them_ok(a.id)
                tt = f"xong: xem {r.get('xem')}, like {r.get('like')}, tb {r.get('tb')}"
            else:
                kq.them_loi(a.id, r.get("detail") or r.get("state") or "lỗi")
                tt = f"lỗi: {r.get('state')}"
        if callable(on_row):
            try:
                on_row(a.id, {"tt": tt, "xem": r.get("xem"), "like": r.get("like"), "tb": r.get("tb")})
            except Exception:  # noqa: BLE001
                pass

    workers = max(1, min(so_luong, len(accs) or 1))
    if workers <= 1:
        for a in accs:
            if callable(nen_dung) and nen_dung():
                break
            mot_acc(a)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(mot_acc, accs))
    kq.ghi_chu = (f"tương tác {len(accs)} acc ({workers} luồng) — tổng xem {tong['xem']}, "
                  f"like {tong['like']}, thông báo {tong['tb']}")
    kq.du_lieu = {"tong_xem": tong["xem"], "tong_like": tong["like"], "tong_tb": tong["tb"]}
    return kq


dang_ky(Modun(ma=MA, ten="🤝 Tương tác (xem reel + like)", nhom="khac", chay=chay,
              mo_ta="Về acc cá nhân rồi vào Reel xem video + thả like theo số lượng/thời gian."))
