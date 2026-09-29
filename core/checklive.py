"""Check live/die UID Facebook NHANH qua HTTP graph (khong mo trinh duyet).

Giong timuid.com: goi ``graph.facebook.com/<uid>?fields=name`` bang MOT access token
con song, chay SONG SONG nhieu UID. Token: nguoi dung dan vao (chac chan), hoac tu
lay tu acc da dang nhap (best-effort, xem ``derive_token``).

Phan loai (khi token con song):
  live       -> graph tra {id, name}
  die        -> UID khong ton tai / bi vo hieu hoa (code 803/100 subcode 33, "do not exist")
  checkpoint -> UID bi khoa/han che (code 368 / "temporarily blocked")
  loi        -> loi khac (mang, dinh dang)
Token chet (code 190) -> nem TokenChet de dung ca me, bao nguoi dung thay token.

Module KHONG import tkinter, KHONG mo trinh duyet cho viec CHECK (chi ``derive_token``
moi mo, va do la duong lay token, khong phai check).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

GRAPH = "https://graph.facebook.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

TRANG_THAI = ("live", "die", "checkpoint", "token_loi", "loi")


class CheckLiveError(RuntimeError):
    pass


class TokenChet(CheckLiveError):
    """Token het han / bi vo hieu hoa (graph code 190) -> khong check tiep duoc."""


def parse_uids(text: str) -> list:
    """Moi dong / khoang trang mot UID; chi giu chuoi so; bo trung (giu thu tu).

    Nhan ca link facebook.com/<uid> hoac profile.php?id=<uid> -> rut so ra.
    """
    seen, ra = set(), []
    for tok in re.split(r"[\s,;|]+", text or ""):
        tok = tok.strip()
        if not tok:
            continue
        m = re.search(r"(?:profile\.php\?id=|facebook\.com/)(\d{5,})", tok)
        uid = m.group(1) if m else tok
        # UID Facebook co the ngan (UID 4 = Mark) -> chap nhan chuoi so 1..25 chu so.
        if uid.isdigit() and 1 <= len(uid) <= 25 and uid not in seen:
            seen.add(uid)
            ra.append(uid)
    return ra


def _fetch_graph(url: str, timeout: float) -> tuple:
    """(http_status, json_dict). Loi mang -> (0, {'_neterr': ...})."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8", "replace") or "{}")
        except ValueError:
            body = {}
        return e.code, body
    except Exception as e:  # noqa: BLE001 - loi mang/timeout: bao len tren
        return 0, {"_neterr": f"{type(e).__name__}: {e}"[:150]}


def phan_loai(status: int, body: dict) -> tuple:
    """(trang_thai, name, detail) tu ket qua graph. Nem TokenChet neu code 190."""
    err = (body or {}).get("error") or {}
    if not err and (body or {}).get("id"):
        return "live", body.get("name") or "", ""
    code = err.get("code")
    sub = err.get("error_subcode")
    msg = (err.get("message") or "").strip()
    if body.get("_neterr"):
        return "loi", "", body["_neterr"]
    if code == 190:
        raise TokenChet(msg or "Token hết hạn / bị vô hiệu hoá.")
    low = msg.lower()
    if code == 803 or "do not exist" in low or "does not exist" in low:
        return "die", "", msg[:120]
    if code == 100 and (sub in (33, 33013) or "unsupported get request" in low or "cannot be loaded" in low):
        return "die", "", msg[:120]
    if code == 368 or sub == 1348092 or "temporarily blocked" in low or "checkpoint" in low or "misused" in low:
        return "checkpoint", "", msg[:120]
    if not err and not body:
        return "loi", "", "phản hồi rỗng"
    return "loi", "", (msg or f"code={code}")[:120]


def check_uid(uid: str, token: str, *, timeout: float = 15.0,
              fetch: Optional[Callable[[str, float], tuple]] = None) -> dict:
    """Check MOT uid. Tra {uid, status, name, detail}. Nem TokenChet khi token chet."""
    fetch = fetch or _fetch_graph
    url = f"{GRAPH}/{uid}?fields=id,name&access_token={(token or '').strip()}"
    status, body = fetch(url, timeout)
    tt, name, detail = phan_loai(status, body)
    return {"uid": uid, "status": tt, "name": name, "detail": detail}


def check_batch(uids: list, token: str, *, workers: int = 10, timeout: float = 15.0,
                fetch: Optional[Callable[[str, float], tuple]] = None,
                on_row: Optional[Callable[[dict], None]] = None,
                dung: Optional[Callable[[], bool]] = None) -> dict:
    """Check nhieu uid SONG SONG. Token chet -> dung ngay, danh dau cac uid con lai.

    Tra {"rows": [dict theo THU TU uids], "token_chet": bool, "detail": str}.
    ``on_row`` goi moi khi mot uid xong (de UI ve dan). ``dung()`` True -> dung som.
    """
    dung = dung or (lambda: False)
    uids = list(uids)
    ket: dict = {}
    token_chet = {"v": False, "msg": ""}

    def one(uid: str) -> None:
        if dung() or token_chet["v"]:
            ket[uid] = {"uid": uid, "status": "loi", "name": "", "detail": "bỏ qua"}
            return
        try:
            ket[uid] = check_uid(uid, token, timeout=timeout, fetch=fetch)
        except TokenChet as e:
            token_chet["v"] = True
            token_chet["msg"] = str(e)
            ket[uid] = {"uid": uid, "status": "token_loi", "name": "", "detail": str(e)[:120]}
        if on_row:
            on_row(ket[uid])

    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 30))) as pool:
        pool.map(one, uids)

    rows = [ket.get(u, {"uid": u, "status": "loi", "name": "", "detail": "chưa chạy"}) for u in uids]
    return {"rows": rows, "token_chet": token_chet["v"], "detail": token_chet["msg"]}


# ---------------------------------------------------------------- token
def kiem_token(token: str, *, timeout: float = 15.0,
               fetch: Optional[Callable[[str, float], tuple]] = None) -> tuple:
    """(ok, detail) — token con song khong (goi /me). Khong nem."""
    fetch = fetch or _fetch_graph
    status, body = fetch(f"{GRAPH}/me?fields=id&access_token={(token or '').strip()}", timeout)
    if (body or {}).get("id"):
        return True, body["id"]
    err = (body or {}).get("error") or {}
    return False, (err.get("message") or body.get("_neterr") or "token không dùng được")[:150]


def derive_token(manager, account, *, port: int = 9357,
                 log: Optional[Callable[[str], None]] = None) -> str:
    """Best-effort: mo acc da dang nhap, lay access token trong phien de check.

    Thu nhieu cach trong trang (bootloader/DTSG/business). CHUA chac lay duoc voi FB
    moi (xem PHAT-HIEN) -> nem CheckLiveError neu khong ra token; nguoi dung dan token thay.
    """
    from core import bidi
    noi = log or (lambda _m: None)
    grab = r"""
    (async () => {
      const found = new Set();
      const scan = s => { const m = (s||'').match(/EAA[A-Za-z0-9]{30,}/g); if (m) m.forEach(x => found.add(x)); };
      scan(document.documentElement.innerHTML);
      try { if (window.require) { const d = require("DTSGInitialData"); } } catch (e) {}
      for (const u of ["/adsmanager/manage/campaigns", "/business_locations", "/content_management", "/settings"]) {
        try { const r = await fetch(u, {credentials:'include'}); scan(await r.text()); } catch (e) {}
      }
      return JSON.stringify([...found].slice(0, 3));
    })()
    """
    try:
        manager.close(account, wait=6.0)
        manager.launch_debug(account, "https://www.facebook.com/", port)
        if not bidi.wait_ready(port, timeout=30):
            raise CheckLiveError("Trình duyệt chưa sẵn sàng để lấy token.")
        import time
        time.sleep(5)
        raw = bidi.run_js(port, grab, timeout=60)
        toks = json.loads(raw) if raw.strip().startswith("[") else []
        for t in toks:
            ok, _ = kiem_token(t)
            if ok:
                noi(f"lấy được token từ acc {account.id}")
                return t
        raise CheckLiveError(
            "Không lấy được access token từ acc này (Facebook mới không để lộ token). "
            "Hãy dán token vào ô Token.")
    finally:
        try:
            manager.close(account, wait=6.0)
        except Exception:  # noqa: BLE001
            pass
