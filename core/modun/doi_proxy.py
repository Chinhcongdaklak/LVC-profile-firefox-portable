"""Mo-dun ĐỔI PROXY — nhom proxy (truoc day la App._apply_proxy_change).

tham_so: proxy_cua: dict[acc_id -> Proxy]  HOAC  proxy: Proxy dung chung (Proxy() trong = go proxy).
Hai PHA (chong "not responding" khi them nhieu proxy, yeu cau nguoi dung 2026-09-21):
  PHA 1 — GAN proxy vao cot cho TAT CA acc (nhanh, khong mang) roi luu + goi hook on_gan_xong
          de UI ve lai bang NGAY (nguoi dung thay proxy da vao cot).
  PHA 2 — DO VI TRI (match_identity: geoip qua mang) cho acc co auto_identity, chay SONG SONG
          theo so_luong ("Luong", mac dinh 5) -> nhe, khong nghen.
KHONG tu mo lai trinh duyet: acc dang mo can mo lai o du_lieu["can_mo_lai"] de UI hoi.
tham_so tuy chon: on_gan_xong (callable, goi sau PHA 1); bo_qua_dia=True -> bo PHA 2.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from core import geoip
from core.modun import KetQua, Modun, NguCanh, dang_ky
from core.profiles import ProfileError
from core.proxy import Proxy

MA = "doi_proxy"


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    proxy_cua = tham_so.get("proxy_cua") or {}
    chung = tham_so.get("proxy")
    if not proxy_cua and chung is None:
        raise ValueError("thiếu tham số proxy_cua hoặc proxy")
    live: list = []
    can_mo_lai: list = []
    rematch: list = []
    # ---- PHA 1: GAN proxy vao cot (nhanh, khong mang) ----
    for a in accs:
        proxy = proxy_cua.get(a.id, chung) if proxy_cua else chung
        if proxy is None:
            proxy = Proxy()
        a.proxy_status = ""
        a.proxy_checked = ""
        try:
            outcome = nc.manager.set_proxy(a, proxy)
        except ProfileError:
            a.set_proxy(proxy)
            outcome = "saved"
        if outcome == "live":
            live.append(a.id)
        elif outcome == "restart":
            can_mo_lai.append(a.id)
        if getattr(a, "auto_identity", False) and proxy.enabled:
            rematch.append(a)
        kq.them_ok(a.id)
    try:
        nc.store.save()
    except Exception:  # noqa: BLE001
        pass
    # UI ve lai bang NGAY: proxy da vao cot, chua cho do vi tri.
    hook = tham_so.get("on_gan_xong")
    if callable(hook):
        try:
            hook()
        except Exception:  # noqa: BLE001
            pass

    # ---- PHA 2: DO VI TRI song song (geoip qua mang) ----
    loi_khop: list = []
    if rematch and not tham_so.get("bo_qua_dia"):
        lock = threading.Lock()
        dem = {"n": 0}
        tong = len(rematch)

        def khop_mot(a) -> None:
            try:
                identity = nc.manager.match_identity(a)
                with lock:
                    dem["n"] += 1
                    nc.log(f"[{dem['n']}/{tong}] {a.id} → {identity.summary()}")
            except (geoip.GeoLookupError, ProfileError, OSError) as exc:
                with lock:
                    dem["n"] += 1
                    loi_khop.append((a.id, str(exc).replace("\n", " ")[:160]))
                    nc.log(f"[{dem['n']}/{tong}] {a.id}: không dò được vị trí")

        workers = max(1, min(int(nc.so_luong or 1), tong))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(khop_mot, rematch))
        try:
            nc.store.save()
        except Exception:  # noqa: BLE001
            pass
    for i, ly in loi_khop:
        kq.them_loi(i, f"đổi proxy xong nhưng không dò được vị trí: {ly} (múi giờ giữ như cũ)")
    ghi = f"đã đổi proxy cho {len(accs)} acc"
    if live:
        ghi += f", {len(live)} acc đang mở đã áp dụng ngay"
    if rematch and not tham_so.get("bo_qua_dia"):
        ghi += f", khớp múi giờ {len(rematch) - len(loi_khop)}/{len(rematch)}"
    kq.ghi_chu = ghi
    kq.du_lieu = {"live": live, "can_mo_lai": can_mo_lai, "rematch": [a.id for a in rematch]}
    return kq


dang_ky(Modun(ma=MA, ten="🌐 Đổi proxy", nhom="proxy", chay=chay, can_profile=False,
              mo_ta="Gán proxy cho acc, áp ngay nếu được, dò lại múi giờ/ngôn ngữ; báo acc cần mở lại."))
