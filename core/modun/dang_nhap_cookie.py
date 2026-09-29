"""Mo-dun ĐĂNG NHẬP VỚI COOKIE — nhom acc (truoc day la App.relogin_cookie, ~100 dong trong UI).

Nap lai cookie da luu roi mo thang Facebook, xac minh bang phien that (verify_cookie_login).
GIU phien dang song trong profile neu no giong/moi hon cookie luu (ADR-018: ghi de = giet phien);
phien chet -> nap cookie luu thu 1 lan; van chet + co mat khau + khong checkpoint -> tu chuyen sang
dang nhap web (ADR-019). Vao duoc -> luu cookie TUOI ve bang. Song song theo so_luong.

tham_so: url (trang mo; khong phai facebook -> ep facebook.com).
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from core import cookies as cookie_module
from core import fblogin, phien
from core.modun import KetQua, Modun, NguCanh, dang_ky
from core.modun.tao_profile import nap_cookie_da_luu
from core.profiles import ProfileError

MA = "dang_nhap_cookie"
FB_URL = "https://www.facebook.com/"
CACH_SUA = "Cách sửa: chuột phải acc → 🌐 Đăng nhập web (id|pass|2fa)."


def nap_cookie(manager, account) -> int:
    """Ghi cookie da luu vao profile (thay the phien). Tach rieng de thuoc stub duoc."""
    return nap_cookie_da_luu(manager, account, replace=True)


def _url_facebook(url: str) -> str:
    url = (url or "").strip()
    return url if "facebook.com" in url.lower() else FB_URL


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    url = _url_facebook(tham_so.get("url") or getattr(nc.settings, "start_url", "") or "")
    dung = [a for a in accs if nc.manager.is_installed(a) and (a.cookie or "").strip()]
    for a in accs:
        if a not in dung:
            kq.them_loi(a.id, "chưa có profile hoặc chưa lưu cookie")
    if not dung:
        kq.ghi_chu = "không có acc đủ điều kiện (cần profile + cookie)"
        return kq
    workers = max(1, min(int(nc.so_luong or 1), len(dung)))
    lock = threading.Lock()
    ok: list = []
    dead: list = []
    errors: list = []
    dem = {"xong": 0}
    mgr = nc.manager

    def mo_va_kiem(account) -> bool:
        mgr.clear_login_probe(account)
        mgr.launch(account, url=url)
        try:
            nc.store.mark_opened(account.id)
        except Exception:  # noqa: BLE001
            pass
        return bool(mgr.verify_cookie_login(account))

    def luu_cookie_tuoi(account) -> None:
        moi = mgr.read_probe_cookies(account)
        if not moi:
            return
        m_user, m_xs = phien.dau_hieu(moi)
        s_user, s_xs = phien.dau_hieu(account.cookie)
        if m_user and m_xs and (m_user, m_xs) != (s_user, s_xs):
            account.cookie = moi
            nc.log(f"Acc {account.id}: đã lưu cookie tươi (Facebook vừa xoay phiên).")

    def login(account) -> None:
        try:
            mgr.close(account, wait=10.0)
            if not mgr.is_initialized(account):
                mgr.initialize(account)
            tt = phien.so_phien(
                cookie_module.read_from_profile(mgr.profile_dir(account)), account.cookie)
            da_nap = False
            if phien.nen_nap(tt):
                nap_cookie(mgr, account)
                da_nap = True
            else:
                nc.log(f"Acc {account.id}: profile đang giữ phiên"
                       + (" MỚI hơn cookie lưu" if tt == phien.MOI_HON else "")
                       + " — mở bằng phiên đó, không ghi đè.")
            vao = mo_va_kiem(account)
            if not vao and not da_nap:
                mgr.close(account, wait=10.0)
                nc.log(f"Acc {account.id}: phiên trong profile chết — nạp cookie lưu thử lại...")
                nap_cookie(mgr, account)
                vao = mo_va_kiem(account)
            if vao:
                luu_cookie_tuoi(account)
                account.cookie_ok = time.strftime("%Y-%m-%d %H:%M")
                with lock:
                    ok.append(account.id)
                return
            account.cookie_ok = ""
            ly_do = phien.ly_do_chet(mgr.read_login_probe_why(account), tt)
            co_pass = bool((account.password or "").strip())
            if phien.nen_dang_nhap_web(ly_do, co_pass):
                nc.log(f"Acc {account.id}: cookie chết — chuyển sang đăng nhập web (id|pass|2fa)...")
                r = fblogin.login_web(mgr, account, log=nc.log)
                if r.get("ok") or r.get("status") == fblogin.VAO:
                    with lock:
                        ok.append(account.id)
                    return
                ly_do = f"{ly_do}; đăng nhập web: {r.get('status')} — {r.get('detail', '')}"
            elif not co_pass:
                ly_do += " (acc chưa có mật khẩu nên không tự đăng nhập web được)"
            with lock:
                dead.append((account.id, ly_do))
        except (ProfileError, cookie_module.CookieError, OSError) as exc:
            with lock:
                errors.append((account.id, str(exc).replace("\n", " ")[:150]))
        finally:
            try:
                mgr.close(account, wait=10.0)
            except OSError:
                pass
            with lock:
                dem["xong"] += 1
                nc.log(f"[{dem['xong']}/{len(dung)}] xong {account.id} — "
                       f"vào được {len(ok)}, cookie chết {len(dead)}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(login, dung))
    try:
        nc.store.save()
    except Exception:  # noqa: BLE001
        pass
    for i in ok:
        kq.them_ok(i)
    for i, ly in dead:
        kq.them_loi(i, ly)
    for i, ly in errors:
        kq.them_loi(i, f"lỗi: {ly}")
    kq.ghi_chu = CACH_SUA if (dead or errors) else f"{workers} luồng"
    kq.du_lieu = {"dead": dead, "errors": errors}
    return kq


dang_ky(Modun(ma=MA, ten="🔑 Đăng nhập với cookie", nhom="acc", chay=chay,
              mo_ta="Nạp cookie đã lưu (giữ phiên mới hơn), mở FB xác minh; chết thì tự đăng nhập web."))
