"""Tai AVATAR acc Facebook ve thu muc ``avatar/`` (nguoi dung 23/10).

Khi mo profile acc Facebook -> tu tai anh dai dien, ten file = <id acc>.<duoi>.
Dung cookie cua acc (uu tien cookie tuoi trong profile) goi graph.facebook.com/{id}/picture;
co cookie thi ra AVATAR THAT, khong co van ra anh mac dinh. KHONG mo trinh duyet.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

#: Thu muc luu avatar (canh thu muc lam viec cua tool, giong ``data/``).
TEN_THU_MUC = "avatar"
#: Anh nho hon nguong nay (byte) coi la rong/hong -> khong luu de.
TOI_THIEU_BYTE = 500


def thu_muc() -> str:
    """Duong dan tuyet doi thu muc avatar; TU TAO neu chua co."""
    d = os.path.abspath(TEN_THU_MUC)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def _duoi_tu_kieu(content_type: str, data: bytes) -> str:
    ct = (content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "gif" in ct:
        return ".gif"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def duong_dan_co_san(acc_id: str) -> str:
    """File avatar da ton tai cua acc (bat ky duoi nao), rong neu chua co. THUAN."""
    base = thu_muc()
    for duoi in (".jpg", ".png", ".webp", ".gif", ".jpeg"):
        p = os.path.join(base, f"{acc_id}{duoi}")
        if os.path.isfile(p):
            return p
    return ""


def url_avatar(acc_id: str, *, size: int = 720) -> str:
    return (f"https://graph.facebook.com/{acc_id}/picture"
            f"?width={size}&height={size}&redirect=true")


def _tai_anh(url: str, cookie_text: str, proxy=None):
    """GET anh nhi phan. Tra (status, data_bytes, content_type, final_url)."""
    import requests

    from core import fbthongtin
    headers = dict(fbthongtin.HEADERS)
    headers["Cookie"] = fbthongtin.header_cookie(cookie_text)
    headers["Accept"] = "image/avif,image/webp,image/png,image/*,*/*;q=0.8"
    proxies = fbthongtin._proxies(proxy)
    r = requests.get(url, headers=headers, timeout=20, allow_redirects=True, proxies=proxies)
    return r.status_code, r.content, r.headers.get("Content-Type", ""), r.url


def tai_mot(manager, account, *, force: bool = False,
            get: Optional[Callable] = None,
            log: Optional[Callable[[str], None]] = None) -> dict:
    """Tai avatar cho MOT acc Facebook. Tra {ok, path, detail}. KHONG nem.

    Da co file (va khong ``force``) -> bo qua. ``get`` tiem cho thuoc (status, data, ct, url)."""
    noi = log or (lambda _m: None)
    acc_id = str(getattr(account, "id", "") or "")
    if not acc_id:
        return {"ok": False, "path": "", "detail": "acc không có id"}
    san = duong_dan_co_san(acc_id)
    if san and not force:
        return {"ok": True, "path": san, "detail": "đã có avatar"}
    try:
        from core.modun.check_tuong import cookie_cua_acc
        cookie = cookie_cua_acc(manager, account)
    except Exception:  # noqa: BLE001
        cookie = getattr(account, "cookie", "") or ""
    proxy = account.get_proxy() if hasattr(account, "get_proxy") else None
    tai = get or _tai_anh
    try:
        status, data, ct, _final = tai(url_avatar(acc_id), cookie, proxy)
    except Exception as exc:  # noqa: BLE001
        noi(f"[{acc_id}] tải avatar lỗi: {str(exc)[:60]}")
        return {"ok": False, "path": "", "detail": f"lỗi mạng: {str(exc)[:60]}"}
    if status != 200 or not data or len(data) < TOI_THIEU_BYTE:
        return {"ok": False, "path": "",
                "detail": f"không tải được avatar (HTTP {status}, {len(data or b'')} byte)"}
    path = os.path.join(thu_muc(), f"{acc_id}{_duoi_tu_kieu(ct, data)}")
    try:
        if san and os.path.abspath(san) != os.path.abspath(path):
            os.remove(san)                       # doi duoi -> xoa ban cu
    except OSError:
        pass
    try:
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError as exc:
        return {"ok": False, "path": "", "detail": f"ghi file lỗi: {exc}"}
    noi(f"[{acc_id}] đã tải avatar ({len(data)//1024 or 1} KB) -> {os.path.basename(path)}")
    return {"ok": True, "path": path, "detail": "đã tải avatar"}


def tai_nhieu(manager, accounts, *, force: bool = False, workers: int = 4,
              get: Optional[Callable] = None,
              log: Optional[Callable[[str], None]] = None) -> dict:
    """Tai avatar NHIEU acc (song song). Tra {ok: so tai duoc, tong}."""
    from concurrent.futures import ThreadPoolExecutor
    accs = [a for a in accounts if getattr(a, "id", "")]
    if not accs:
        return {"ok": 0, "tong": 0}
    n = max(1, min(int(workers or 1), len(accs)))
    dem = {"ok": 0}
    with ThreadPoolExecutor(max_workers=n) as ex:
        for r in ex.map(lambda a: tai_mot(manager, a, force=force, get=get, log=log), accs):
            if r.get("ok"):
                dem["ok"] += 1
    return {"ok": dem["ok"], "tong": len(accs)}
