"""Mo-dun DANG LAI TRICH DAN tren X.com (Quote) — nhom khac.

Moi acc mo Firefox (qua cong VPN) roi trich dan ``so_bai`` bai; noi dung trich dan = comment
DAU TIEN cua bai (khong co thi CAPTION bai) + 3-5 icon ngau nhien.
Nguon bai: list KENH X (MOI ACC CO LIST RIENG ``kenh_acc``; acc chua co list thi dung list chung
``kenh``; dong la link bai thi trich dan dung bai do) hoac chon NGAU NHIEN tren newfeed.
CHONG TRUNG qua core.quote_lich_su (bai acc da trich dan thi bo qua; ``khong_trung_acc`` = khong
cho 2 acc trich dan cung mot bai). Song song theo so_luong (moi acc 1 Firefox, profile X rieng).

tham_so: hanh_dong ("quote" mac dinh | "follow" = follow list kenh nguon, da follow bo qua),
nguon ("kenh"|"newfeed"), kenh (van ban/list), kenh_acc ({acc_id: van ban}), so_bai,
cach_min/cach_max (giay nghi giua 2 bai), so_luong, thu, khong_trung_acc (mac dinh True),
lich_su (LichSuQuote tiem — thuoc), on_row(callable(acc_id, dict)), nen_dung(callable()->bool).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from core import xwatch
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "dang_lai_x"

_TT_LOI = {"vpn-loi": "⛔ VPN chưa nối — KHÔNG chạy",
           "logged-out": "⛔ acc đã đăng xuất x.com",
           "x-locked": "⛔ acc bị X khoá/treo",
           "browser-gone": "⛔ trình duyệt bị đóng giữa chừng",
           "thieu-kenh": "⛔ acc chưa có list kênh X"}


def kenh_cua_acc(acc_id: str, kenh_chung, kenh_acc) -> list:
    """List kenh (chuan_kenh) cua acc: list RIENG neu co, khong thi list chung. THUAN."""
    rieng = (kenh_acc or {}).get(str(acc_id))
    ds = xwatch.tach_kenh(rieng) if rieng else []
    return ds or xwatch.tach_kenh(kenh_chung or [])


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    hanh_dong = "follow" if tham_so.get("hanh_dong") == "follow" else "quote"
    nguon = xwatch.NGUON_KENH if tham_so.get("nguon") == xwatch.NGUON_KENH else xwatch.NGUON_NEWFEED
    kenh_chung = tham_so.get("kenh") or []
    kenh_acc = tham_so.get("kenh_acc") or {}
    so_bai = max(1, int(tham_so.get("so_bai", 3) or 3))
    cach_min = max(0, int(tham_so.get("cach_min", 20) or 0))
    cach_max = max(cach_min, int(tham_so.get("cach_max", cach_min) or cach_min))
    so_luong = int(tham_so.get("so_luong", 0) or nc.so_luong or 1)
    thu = bool(tham_so.get("thu"))
    on_row = tham_so.get("on_row")
    nen_dung = tham_so.get("nen_dung")
    lich_su = tham_so.get("lich_su")
    if lich_su is None and hanh_dong == "quote":
        from core.quote_lich_su import LichSuQuote
        lich_su = LichSuQuote(chung=bool(tham_so.get("khong_trung_acc", True)))
    lock = threading.Lock()
    tong = {"quote": 0, "follow": 0, "trung": 0}

    def bao(acc_id, info) -> None:
        if callable(on_row):
            try:
                on_row(acc_id, info)
            except Exception:  # noqa: BLE001
                pass

    def _goi(a, ds_kenh):
        if hanh_dong == "follow":
            return xwatch.follow_kenh(nc.manager, a, ds_kenh, thu=thu, nen_dung=nen_dung,
                                      log=nc.log)
        return xwatch.dang_lai_trich_dan(nc.manager, a, nguon=nguon, kenh=ds_kenh, so_bai=so_bai,
                                        cach_min=cach_min, cach_max=cach_max, thu=thu,
                                        nen_dung=nen_dung, log=nc.log, lich_su=lich_su)

    def mot_acc(a) -> None:
        if callable(nen_dung) and nen_dung():
            return
        ds_kenh = kenh_cua_acc(a.id, kenh_chung, kenh_acc)
        bao(a.id, {"tt": "đang follow kênh nguồn" if hanh_dong == "follow" else "đang chạy"})
        r = _goi(a, ds_kenh)
        if r.get("state") == "logged-out":
            # Acc X bi dang xuat -> nap lai cookie X roi thu lai MOT lan.
            try:
                from core import modun as _modun
                nc.log(f"[{a.id}] bị đăng xuất — nạp lại cookie rồi thử lại...")
                dn = _modun.chay("dang_nhap_cookie", nc, [a])
                if a.id in dn.ok:
                    r = _goi(a, ds_kenh)
                else:
                    r["detail"] = "đăng xuất; nạp cookie lại KHÔNG được"
            except Exception as exc:  # noqa: BLE001
                r["detail"] = f"đăng xuất; thử đăng nhập lại lỗi: {exc}"
        st = str(r.get("state") or "")
        with lock:
            if hanh_dong == "follow":
                tong["follow"] += int(r.get("follow") or 0)
                tt = (f"follow mới {r.get('follow', 0)} · đã follow {r.get('da_follow', 0)} · "
                      f"lỗi {r.get('loi', 0)}") if st == "done" else _TT_LOI.get(st, f"lỗi: {st}")
                if r.get("ok"):
                    kq.them_ok(a.id)
                else:
                    kq.them_loi(a.id, r.get("detail") or st)
                bao(a.id, {"tt": tt})
                return
            tong["quote"] += int(r.get("quote") or 0)
            tong["trung"] += int(r.get("trung") or 0)
            loi = sum(1 for x in r.get("rows") or [] if not x.get("ok"))
            if r.get("ok"):
                kq.them_ok(a.id)
                tt = (f"xong: trích dẫn {r.get('quote')}/{so_bai}"
                      + (f" · bỏ {r.get('trung')} bài trùng" if r.get("trung") else "")
                      + (" (chạy thử)" if thu else ""))
            else:
                kq.them_loi(a.id, r.get("detail") or st or "lỗi")
                tt = _TT_LOI.get(st, f"không trích dẫn được bài nào ({r.get('detail') or st})")
        bao(a.id, {"tt": tt, "quote": r.get("quote"), "loi": loi})

    workers = max(1, min(so_luong, len(accs) or 1))
    if workers <= 1:
        for a in accs:
            if callable(nen_dung) and nen_dung():
                break
            mot_acc(a)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(mot_acc, accs))
    if hanh_dong == "follow":
        kq.ghi_chu = f"follow kênh nguồn {len(accs)} acc — follow mới tổng {tong['follow']} kênh"
    else:
        kq.ghi_chu = (f"trích dẫn X {len(accs)} acc ({workers} luồng) — tổng {tong['quote']} bài"
                      + (f", bỏ {tong['trung']} bài trùng" if tong["trung"] else "")
                      + (" từ list kênh" if nguon == xwatch.NGUON_KENH else " từ newfeed"))
    kq.du_lieu = {"tong_quote": tong["quote"], "tong_follow": tong["follow"], "tong_trung": tong["trung"]}
    return kq


dang_ky(Modun(ma=MA, ten="🔁 Đăng lại trích dẫn X (Quote)", nhom="khac", chay=chay,
              mo_ta="Trích dẫn (Quote) bài của list kênh X (mỗi acc một list) hoặc ngẫu nhiên trên "
                    "newfeed; nội dung = comment đầu tiên (không có thì caption) + 3-5 icon; "
                    "không trích dẫn trùng bài."))
