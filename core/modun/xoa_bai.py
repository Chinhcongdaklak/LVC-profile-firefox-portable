"""Mo-dun XOA BAI VIET FANPAGE — nhom fanpage (ADR-029). Graph API chinh thuc bang token page, KHONG mo trinh duyet.

tham_so:
  dong: [{"acc_id", "page_id", "token", "tu", "den", "loai"}] — moi dong = 1 fanpage (bang cua tab);
        thieu "dong" -> moi acc trong ``accs`` lay page tu token acc (tham_so["token"][acc_id]).
  dry (True = chi quet/dem), gioi_han (bai/lan/dong, 0 = khong), cach_giay (giua 2 lan xoa), so_luong (dong song song),
  on_row(acc_id, page_id, dict), nen_dung() -> bool, txt (duong dan TXT ghi bai da xoa).
KetQua.ok/loi theo tung DONG (khoa "acc_id|page_id"); du_lieu["rows"] = {khoa: ket qua chay_xoa}.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from core import fbxoabai
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "xoa_bai"


def _khoa(d: dict) -> str:
    return f"{d.get('acc_id', '')}|{d.get('page_id', '')}"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    dry = bool(tham_so.get("dry", True))
    gioi_han = int(tham_so.get("gioi_han", 0) or 0)
    cach_giay = float(tham_so.get("cach_giay", 2) or 0)
    so_luong = max(1, int(tham_so.get("so_luong", 0) or nc.so_luong or 1))
    on_row = tham_so.get("on_row")
    nen_dung = tham_so.get("nen_dung")
    txt = (tham_so.get("txt") or "").strip()
    get = tham_so.get("get") or fbxoabai._get
    delete = tham_so.get("delete") or fbxoabai._delete
    sleep = tham_so.get("sleep")
    dong = list(tham_so.get("dong") or [])
    if not dong:
        tokens = tham_so.get("token") or {}
        for a in accs:
            tk = tokens.get(a.id, "")
            pages, loi = fbxoabai.cac_page_cua_token(tk, get=get) if tk else ([], "chưa có token")
            if loi:
                kq.them_loi(a.id, loi)
                continue
            for p in pages:
                dong.append({"acc_id": a.id, "page_id": p["id"], "token": p["access_token"] or tk,
                             "tu": tham_so.get("tu", ""), "den": tham_so.get("den", ""),
                             "loai": tham_so.get("loai", "tat_ca")})
    khoa_ghi = threading.Lock()
    rows: dict = {}

    def mot(d: dict) -> None:
        k = _khoa(d)
        if on_row:
            on_row(d.get("acc_id", ""), d.get("page_id", ""), {"tt": "đang quét…" if dry else "đang xoá…"})

        def tien_do(t: dict) -> None:
            if on_row:
                on_row(d.get("acc_id", ""), d.get("page_id", ""),
                       {"tt": f"đã xoá {t['xoa']}/{t['khop']}" + (f" · lỗi {t['loi']}" if t.get("loi") else "")})

        extra = {"sleep": sleep} if sleep else {}
        r = fbxoabai.chay_xoa(d.get("page_id", ""), d.get("token", ""), d.get("tu", ""), d.get("den", ""),
                              d.get("loai", "tat_ca"), dry=dry, gioi_han=gioi_han, cach_giay=cach_giay,
                              get=get, delete=delete, nen_dung=nen_dung, on_tien_do=tien_do, log=nc.log, **extra)
        with khoa_ghi:
            rows[k] = r
            if r["ok"]:
                kq.them_ok(k)
            else:
                kq.them_loi(k, r["loi"])
            if txt and not dry and r["xoa"]:
                try:
                    with open(txt, "a", encoding="utf-8") as fh:
                        for b in r["ds"][:r["xoa"]]:
                            fh.write(fbxoabai.dong_txt(d.get("acc_id", ""), d.get("page_id", ""), b) + "\n")
                except OSError as exc:
                    nc.log(f"không ghi được TXT: {exc}")
        if on_row:
            if r["loi"]:
                tt = "✖ " + r["loi"][:60]
            elif dry:
                tt = f"🔍 {r['khop']} bài khớp / {r['quet']} trong khoảng"
            else:
                tt = f"✓ đã xoá {r['xoa']}/{r['khop']}" + (f" · lỗi {len(r['loi_bai'])}" if r["loi_bai"] else "") \
                     + (f" · còn {r['bo_qua']}" if r["bo_qua"] else "")
            on_row(d.get("acc_id", ""), d.get("page_id", ""), {"tt": tt, "kq": r})

    if so_luong <= 1 or len(dong) <= 1:
        for d in dong:
            if nen_dung and nen_dung():
                break
            mot(d)
    else:
        with ThreadPoolExecutor(max_workers=so_luong, thread_name_prefix="xoabai") as ex:
            list(ex.map(mot, dong))
    tong_xoa = sum(r["xoa"] for r in rows.values())
    tong_khop = sum(r["khop"] for r in rows.values())
    kq.du_lieu = {"rows": rows, "tong_xoa": tong_xoa, "tong_khop": tong_khop, "dry": dry}
    kq.ghi_chu = (f"quét {len(rows)} page, {tong_khop} bài khớp" if dry
                  else f"đã xoá {tong_xoa}/{tong_khop} bài trên {len(rows)} page")
    return kq


dang_ky(Modun(
    ma=MA, ten="🗑 Xoá bài viết fanpage", nhom="fanpage", chay=chay, can_profile=False,
    mo_ta="Xoá bài đã đăng của fanpage trong khoảng ngày + thể loại (tất cả/video/ảnh) bằng Graph API "
          "với token page — không mở trình duyệt. Quét trước (đếm) rồi mới xoá thật."))
