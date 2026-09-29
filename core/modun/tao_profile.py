"""Mo-dun TẠO PROFILE — nhom acc.

Tao thu muc Firefox Portable cho acc (manager.create) + khoi tao (initialize) + nap cookie da
luu (neu co), SONG SONG theo so_luong. Acc da co profile thi bo qua (bao trong loi de UI biet).
tham_so: khong co.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from core import cookies as cookie_module
from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "tao_profile"


def nap_cookie_da_luu(manager, account, replace: bool = True,
                      domain: str = ".facebook.com") -> int:
    """Ghi cookie da luu cua acc vao profile (truoc day la App._apply_cookie). Tra so cookie ghi."""
    parsed = cookie_module.parse(account.cookie or "", default_domain=domain)
    if not parsed:
        return 0
    return cookie_module.write_to_profile(manager.profile_dir(account), parsed, replace_all=replace)


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    can = [a for a in accs if not nc.manager.is_installed(a)]
    for a in accs:
        if a not in can:
            kq.them_loi(a.id, "đã có profile (bỏ qua)")
    if not can:
        kq.ghi_chu = "mọi acc đã có profile"
        return kq
    workers = max(1, min(int(nc.so_luong or 1), len(can)))
    lock = threading.Lock()
    dem = {"xong": 0}

    def mot(account) -> None:
        prefix = f"{account.id}: "
        report = lambda m, p=prefix: nc.log(p + m)  # noqa: E731
        try:
            nc.manager.create(account, on_status=report)
            nc.manager.initialize(account, on_status=report)
            if (account.cookie or "").strip():
                nap_cookie_da_luu(nc.manager, account, replace=True)
        except Exception as exc:  # noqa: BLE001
            with lock:
                kq.them_loi(account.id, str(exc).replace("\n", " ")[:160])
            return
        with lock:
            kq.them_ok(account.id)
            dem["xong"] += 1
            nc.log(f"[{dem['xong']}/{len(can)}] Xong {account.id}.")
        nc.post(lambda: None)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(mot, can))
    # create() co the da do ra mui gio/ngon ngu moi -> ghi lai.
    try:
        nc.store.save()
    except Exception:  # noqa: BLE001
        pass
    kq.ghi_chu = f"{workers} luồng"
    return kq


dang_ky(Modun(ma=MA, ten="🧩 Tạo profile", nhom="acc", chay=chay, can_profile=False,
              mo_ta="Tạo Firefox Portable cho acc, khởi tạo, nạp cookie đã lưu; song song theo Luồng."))
