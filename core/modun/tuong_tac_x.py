"""Mo-dun TUONG TAC X.com — nhom khac. Vao x.com/home, cuon newfeed, dung lai doc tung bai
5-10s (nguoi dung chinh), tha tim N bai, gap video thi bam xem, vao N bai lay comment DAU TIEN
dang lai kem 3-5 icon ngau nhien. Chay TUNG acc (song song theo
so_luong; moi acc 1 Firefox, profile X rieng).

tham_so: so_like, so_video, so_comment, gioi_han_min/gioi_han_max (GIAY, ngau nhien moi acc),
dung_min/dung_max (GIAY dung lai moi bai), so_luong, url,
on_row(callable(acc_id, dict)), nen_dung(callable()->bool).

Acc bi dang xuat giua chung -> goi mo-dun dang nhap X (cookie) roi thu lai 1 lan.
"""

from __future__ import annotations

import random
import threading
from concurrent.futures import ThreadPoolExecutor

from core import xwatch
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "tuong_tac_x"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    so_like = int(tham_so.get("so_like", 0) or 0)
    so_video = int(tham_so.get("so_video", 0) or 0)
    so_comment = int(tham_so.get("so_comment", 0) or 0)
    gh_min = max(10, int(tham_so.get("gioi_han_min", 60) or 60))
    gh_max = max(gh_min, int(tham_so.get("gioi_han_max", gh_min) or gh_min))
    dung_min = max(1, int(tham_so.get("dung_min", xwatch.DUNG_MIN) or xwatch.DUNG_MIN))
    dung_max = max(dung_min, int(tham_so.get("dung_max", xwatch.DUNG_MAX) or xwatch.DUNG_MAX))
    so_luong = int(tham_so.get("so_luong", 0) or nc.so_luong or 1)
    url = tham_so.get("url") or xwatch.X_HOME_URL
    on_row = tham_so.get("on_row")
    nen_dung = tham_so.get("nen_dung")
    lock = threading.Lock()
    tong = {"xem": 0, "like": 0, "video": 0, "cmt": 0}

    def mot_acc(a) -> None:
        if callable(nen_dung) and nen_dung():
            return
        if callable(on_row):
            try:
                on_row(a.id, {"tt": "đang chạy"})
            except Exception:  # noqa: BLE001
                pass
        gh = random.randint(gh_min, gh_max)      # thoi gian tuong tac NGAU NHIEN cho acc nay

        def _chay_1():
            return xwatch.tuong_tac(nc.manager, a, so_like=so_like, so_video=so_video,
                                    so_comment=so_comment, gioi_han_giay=gh, dung_min=dung_min, dung_max=dung_max,
                                    url=url, log=nc.log)

        r = _chay_1()
        if r.get("state") == "logged-out":
            # Acc X bi dang xuat -> nap lai cookie X roi thu lai MOT lan.
            try:
                from core import modun as _modun
                nc.log(f"[{a.id}] bị đăng xuất khi tương tác X — nạp lại cookie rồi thử lại...")
                dn = _modun.chay("dang_nhap_cookie", nc, [a])
                if a.id in dn.ok:
                    r = _chay_1()
                else:
                    r["detail"] = "đăng xuất; nạp cookie lại KHÔNG được"
            except Exception as exc:  # noqa: BLE001
                r["detail"] = f"đăng xuất; thử đăng nhập lại lỗi: {exc}"
        with lock:
            tong["xem"] += int(r.get("xem") or 0)
            tong["like"] += int(r.get("like") or 0)
            tong["video"] += int(r.get("video") or 0)
            tong["cmt"] += int(r.get("cmt") or 0)
            if r.get("ok"):
                kq.them_ok(a.id)
                tt = (f"xong: xem {r.get('xem')} bài, tim {r.get('like')}, "
                      f"video {r.get('video')}, cmt {r.get('cmt')}")
            else:
                kq.them_loi(a.id, r.get("detail") or r.get("state") or "lỗi")
                tt = f"lỗi: {r.get('state')}"
        if callable(on_row):
            try:
                on_row(a.id, {"tt": tt, "xem": r.get("xem"), "like": r.get("like"),
                              "tb": r.get("video"), "cmt": r.get("cmt")})
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
    kq.ghi_chu = (f"tương tác X {len(accs)} acc ({workers} luồng) — tổng xem {tong['xem']} bài, "
                  f"tim {tong['like']}, video {tong['video']}, comment {tong['cmt']}")
    kq.du_lieu = {"tong_xem": tong["xem"], "tong_like": tong["like"], "tong_video": tong["video"],
                  "tong_cmt": tong["cmt"]}
    return kq


dang_ky(Modun(ma=MA, ten="🐦 Tương tác X (lướt newfeed + tim)", nhom="khac", chay=chay,
              mo_ta="Vào x.com/home, cuộn newfeed, dừng đọc từng bài, thả tim, bấm xem video, "
                    "comment lại bình luận đầu tiên kèm 3-5 icon."))
