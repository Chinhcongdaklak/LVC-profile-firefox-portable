"""XOA BAI VIET FANPAGE bang Graph API CHINH THUC (ADR-029). Module THUAN: khong tkinter, khong mo trinh duyet.

Yeu cau nguoi dung (2026-09-26): tab "Xoa bai viet" — bang acc: STT · acc FB · fanpage (tu quet / chon / nhap id)
· thoi gian bat dau · thoi gian cuoi · the loai (tat ca / video / anh); tool chon bai trong khoang do de xoa.
Nguoi dung chot: "Graph API chinh thuc bang token page cach nay cung duoc".

CO CHE (tai lieu Meta):
  - Token: page access token (hoac user token co pages_manage_posts + pages_read_engagement; tool tu doi ra
    page token qua /me/accounts). Token la BI MAT: khong ghi nhat ky, chi luu data/ (gitignore).
  - Liet ke:  GET {GRAPH}/{page_id}/published_posts?fields=...&since=&until=&limit=100 (theo trang paging.next).
  - Xoa:      DELETE {GRAPH}/{post_id}?access_token=  -> {"success": true}. MOI BAI MOT GOI, khong co bulk.
  - Han muc:  header X-Page-Usage / X-App-Usage (json call_count/total_time/total_cputime, %): >=80 cham lai,
              >=95 hoac ma loi 4/17/32/613 -> nghi (5, 5, 10, 15 phut) roi thu lai.
  - Khong xoa duoc: anh dai dien / anh bia / story highlight (API tu choi -> ghi loi, di tiep).

Moi goi mang di qua ``get``/``delete`` tiem vao (mac dinh requests) de thuoc do chay offline.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

GRAPH = "https://graph.facebook.com/v21.0"
TIMEOUT = 30

#: The loai xoa: ma -> nhan hien thi.
LOAI = (("tat_ca", "Tất cả"), ("video", "Video"), ("anh", "Ảnh"))
NHAN_LOAI = dict(LOAI)
MA_THEO_NHAN = {v: k for k, v in LOAI}

#: Ma loi Graph API = het han muc / bi tiet luu -> nghi roi thu lai.
MA_HAN_MUC = {4, 17, 32, 613}
#: Chuoi nghi (giay) khi dinh han muc: 5', 5', 10', 15'.
NGHI_HAN_MUC = (300, 300, 600, 900)
#: Nguong % han muc: cham lai / dung.
NGUONG_CHAM = 80.0
NGUONG_DUNG = 95.0

FIELDS = "id,created_time,message,permalink_url,attachments{media_type,type,subattachments{media_type,type}}"


class XoaBaiError(Exception):
    """Loi nghiep vu xoa bai (token/han muc/mang)."""


class TokenChet(XoaBaiError):
    """Token het han / khong hop le (ma 190) -> dung ca dong."""


# ------------------------------------------------------------------ mang (tiem duoc)
def _requests():
    import requests
    return requests


def _get(url: str, params: dict) -> tuple:
    r = _requests().get(url, params=params, timeout=TIMEOUT)
    return r.status_code, _json(r), dict(r.headers)


def _delete(url: str, params: dict) -> tuple:
    r = _requests().delete(url, params=params, timeout=TIMEOUT)
    return r.status_code, _json(r), dict(r.headers)


def _json(r) -> dict:
    try:
        d = r.json()
        return d if isinstance(d, dict) else {"data": d}
    except ValueError:
        return {"error": {"message": (r.text or "")[:200], "code": r.status_code}}


def che_token(token: str) -> str:
    """Token che de hien/ghi log: 'EAAB…k3Zd' (khong bao gio in het)."""
    t = (token or "").strip()
    if len(t) <= 10:
        return "•" * len(t)
    return t[:4] + "…" + t[-4:]


def ma_loi(d: dict) -> tuple:
    """(code, message) tu json loi Graph; khong loi -> (0, '')."""
    e = (d or {}).get("error") or {}
    if not e:
        return 0, ""
    try:
        code = int(e.get("code") or 0)
    except (TypeError, ValueError):
        code = 0
    return code, str(e.get("message") or e.get("error_user_msg") or "")


def han_muc_pct(headers: dict) -> float:
    """% han muc cao nhat trong X-Page-Usage / X-App-Usage / X-Business-Use-Case-Usage (0 neu khong co)."""
    cao = 0.0
    for k in ("X-Page-Usage", "x-page-usage", "X-App-Usage", "x-app-usage"):
        raw = (headers or {}).get(k)
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except (TypeError, ValueError):
            continue
        for v in d.values():
            try:
                cao = max(cao, float(v))
            except (TypeError, ValueError):
                pass
    for k in ("X-Business-Use-Case-Usage", "x-business-use-case-usage"):
        raw = (headers or {}).get(k)
        if not raw:
            continue
        try:
            d = json.loads(raw)
            for ds in d.values():
                for it in ds if isinstance(ds, list) else []:
                    for kk in ("call_count", "total_cputime", "total_time"):
                        cao = max(cao, float(it.get(kk) or 0))
        except (TypeError, ValueError, AttributeError):
            pass
    return cao


# ------------------------------------------------------------------ ngay thang
def ngay_tu_chuoi(s: str) -> Optional[datetime]:
    """'dd/mm/yyyy' (cung nhan 'd/m/yyyy', 'yyyy-mm-dd') -> datetime 00:00 gio may; sai -> None."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def khoang_ngay(tu: str, den: str) -> tuple:
    """(since_epoch, until_epoch, loi). den la NGAY CUOI (bao gom ca ngay) -> until = den + 1 ngay.
    Trong: tu trong = tu dau; den trong = toi hom nay."""
    t = ngay_tu_chuoi(tu) if (tu or "").strip() else None
    d = ngay_tu_chuoi(den) if (den or "").strip() else None
    if (tu or "").strip() and t is None:
        return 0, 0, f"Ngày bắt đầu sai định dạng (dd/mm/yyyy): {tu}"
    if (den or "").strip() and d is None:
        return 0, 0, f"Ngày cuối sai định dạng (dd/mm/yyyy): {den}"
    if d is None:
        d = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if t is not None and t > d:
        return 0, 0, "Ngày bắt đầu phải trước hoặc bằng ngày cuối."
    since = int(t.timestamp()) if t is not None else 0
    until = int((d + timedelta(days=1)).timestamp())
    return since, until, ""


def gio_bai(post: dict) -> int:
    """created_time ISO '2026-09-24T10:00:00+0000' -> epoch (0 neu khong doc duoc)."""
    s = str(post.get("created_time") or "")
    if not s:
        return 0
    s = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", s)
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


# ------------------------------------------------------------------ phan loai
def phan_loai(post: dict) -> str:
    """'video' / 'anh' / 'khac' theo attachments cua bai (album/anh -> anh; video/reel -> video)."""
    ds = ((post or {}).get("attachments") or {}).get("data") or []
    co_video = co_anh = False
    stack = list(ds)
    while stack:
        a = stack.pop()
        mt = str(a.get("media_type") or "").lower()
        ty = str(a.get("type") or "").lower()
        if mt == "video" or "video" in ty or "reel" in ty:
            co_video = True
        elif mt in ("photo", "album") or "photo" in ty or "album" in ty:
            co_anh = True
        sub = (a.get("subattachments") or {}).get("data") or []
        stack.extend(sub)
    if co_video:
        return "video"
    if co_anh:
        return "anh"
    return "khac"


def khop_loai(post: dict, loai: str) -> bool:
    loai = (loai or "tat_ca").strip()
    if loai == "tat_ca":
        return True
    return phan_loai(post) == loai


def loc_bai(posts: list, loai: str, since: int = 0, until: int = 0) -> list:
    """Loc THEO MAY (khong tin API): trong [since, until) va dung the loai."""
    ra = []
    for p in posts or []:
        g = gio_bai(p)
        if since and g and g < since:
            continue
        if until and g and g >= until:
            continue
        if khop_loai(p, loai):
            ra.append(p)
    return ra


# ------------------------------------------------------------------ token / page
def thong_tin_token(token: str, *, get: Callable = _get) -> dict:
    """GET /me -> {id, name, loi}. Token page thi me = page; token user thi me = nguoi dung."""
    st, d, _h = get(f"{GRAPH}/me", {"fields": "id,name", "access_token": token})
    code, msg = ma_loi(d)
    if code or st >= 400:
        return {"id": "", "name": "", "loi": f"token không dùng được ({code}): {msg}"}
    return {"id": str(d.get("id") or ""), "name": str(d.get("name") or ""), "loi": ""}


def cac_page_cua_token(token: str, *, get: Callable = _get) -> tuple:
    """Danh sach page token nay quan ly: [{id, name, access_token}] (theo trang). Token PAGE -> chi 1 page (me).
    Tra (ds, loi)."""
    ds, url, params = [], f"{GRAPH}/me/accounts", {"fields": "id,name,access_token", "limit": 100,
                                                     "access_token": token}
    for _ in range(50):
        st, d, _h = get(url, params)
        code, msg = ma_loi(d)
        if code == 190:
            return [], f"token hết hạn/không hợp lệ (190): {msg}"
        if code or st >= 400:
            break
        for p in d.get("data") or []:
            if p.get("id"):
                ds.append({"id": str(p["id"]), "name": str(p.get("name") or p["id"]),
                           "access_token": str(p.get("access_token") or "")})
        url = ((d.get("paging") or {}).get("next")) or ""
        if not url:
            break
        params = {}
    if ds:
        return ds, ""
    me = thong_tin_token(token, get=get)
    if me["loi"]:
        return [], me["loi"]
    # Token PAGE: /me chinh la page -> dung token nay cho page do.
    return [{"id": me["id"], "name": me["name"], "access_token": token}], ""


# ------------------------------------------------------------------ liet ke / xoa
def liet_ke_bai(page_id: str, token: str, since: int = 0, until: int = 0, *,
                get: Callable = _get, log: Optional[Callable[[str], None]] = None,
                nen_dung: Optional[Callable[[], bool]] = None, toi_da_trang: int = 200) -> list:
    """Cac bai da dang cua page trong [since, until) (API loc + may loc lai). Nem TokenChet / XoaBaiError."""
    noi = log or (lambda _m: None)
    params = {"fields": FIELDS, "limit": 100, "access_token": token}
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    url, ra = f"{GRAPH}/{page_id}/published_posts", []
    for trang in range(toi_da_trang):
        if nen_dung and nen_dung():
            break
        st, d, h = get(url, params)
        code, msg = ma_loi(d)
        if code == 190:
            raise TokenChet(f"token hết hạn/không hợp lệ (190): {msg}")
        if code in MA_HAN_MUC:
            raise XoaBaiError(f"đụng hạn mức khi liệt kê ({code}): {msg}")
        if code or st >= 400:
            raise XoaBaiError(f"không liệt kê được bài ({code or st}): {msg}")
        ds = d.get("data") or []
        ra.extend(p for p in ds if isinstance(p, dict) and p.get("id"))
        noi(f"[{page_id}] trang {trang + 1}: +{len(ds)} bài (tổng {len(ra)})")
        url = ((d.get("paging") or {}).get("next")) or ""
        if not url or not ds:
            break
        params = {}
        pct = han_muc_pct(h)
        if pct >= NGUONG_CHAM:
            noi(f"[{page_id}] hạn mức {pct:.0f}% — chậm lại")
    return loc_bai(ra, "tat_ca", since, until)


def xoa_mot_bai(post_id: str, token: str, *, delete: Callable = _delete) -> tuple:
    """DELETE /{post_id} -> (ok, loi, headers). Ma 190 -> nem TokenChet; ma han muc -> nem XoaBaiError."""
    st, d, h = delete(f"{GRAPH}/{post_id}", {"access_token": token})
    code, msg = ma_loi(d)
    if code == 190:
        raise TokenChet(f"token hết hạn/không hợp lệ (190): {msg}")
    if code in MA_HAN_MUC:
        raise XoaBaiError(f"đụng hạn mức ({code}): {msg}")
    if code or st >= 400:
        return False, f"{code or st}: {msg}", h
    if d.get("success") is False:
        return False, "Facebook trả về success=false", h
    return True, "", h


def chay_xoa(page_id: str, token: str, tu: str, den: str, loai: str = "tat_ca", *,
             dry: bool = True, gioi_han: int = 0, cach_giay: float = 2.0,
             get: Callable = _get, delete: Callable = _delete, sleep: Callable = time.sleep,
             nen_dung: Optional[Callable[[], bool]] = None,
             on_tien_do: Optional[Callable[[dict], None]] = None,
             log: Optional[Callable[[str], None]] = None) -> dict:
    """Quet (dry=True: CHI DEM) hoac XOA bai cua page trong khoang ngay + the loai.

    Tra {"ok": bool, "quet": n bai trong khoang, "khop": n khop the loai, "xoa": n da xoa, "loi_bai": [(id, ly_do)],
         "bo_qua": n (qua gioi han), "loi": "" | ly do dung, "ds": [bai khop {id, created_time, loai, message}]}.
    Xoa TUNG bai, nghi ``cach_giay`` giua 2 bai; dinh han muc -> nghi theo NGHI_HAN_MUC roi thu lai bai do.
    """
    noi = log or (lambda _m: None)
    kq = {"ok": False, "quet": 0, "khop": 0, "xoa": 0, "loi_bai": [], "bo_qua": 0, "loi": "", "ds": []}
    since, until, loi = khoang_ngay(tu, den)
    if loi:
        kq["loi"] = loi
        return kq
    if not (page_id or "").strip():
        kq["loi"] = "Chưa có ID fanpage."
        return kq
    if not (token or "").strip():
        kq["loi"] = "Chưa có token."
        return kq
    try:
        bai = liet_ke_bai(page_id, token, since, until, get=get, log=noi, nen_dung=nen_dung)
    except XoaBaiError as exc:
        kq["loi"] = str(exc)
        return kq
    if nen_dung and nen_dung():
        kq["loi"] = "dừng theo yêu cầu"
        return kq
    kq["quet"] = len(bai)
    khop = loc_bai(bai, loai, since, until)
    kq["khop"] = len(khop)
    kq["ds"] = [{"id": str(p["id"]), "created_time": str(p.get("created_time") or ""),
                 "loai": phan_loai(p), "message": str(p.get("message") or "")[:80],
                 "permalink_url": str(p.get("permalink_url") or "")} for p in khop]
    noi(f"[{page_id}] {len(bai)} bài trong khoảng, {len(khop)} bài khớp thể loại '{NHAN_LOAI.get(loai, loai)}'")
    if dry:
        kq["ok"] = True
        return kq
    lan_nghi = 0
    for i, p in enumerate(khop):
        if nen_dung and nen_dung():
            kq["loi"] = "dừng theo yêu cầu"
            break
        if gioi_han and kq["xoa"] >= gioi_han:
            kq["bo_qua"] = len(khop) - i
            noi(f"[{page_id}] đã tới giới hạn {gioi_han} bài/lần — còn {kq['bo_qua']} bài để lần sau")
            break
        pid = str(p["id"])
        while True:
            try:
                ok, ly_do, h = xoa_mot_bai(pid, token, delete=delete)
            except TokenChet as exc:
                kq["loi"] = str(exc)
                return kq
            except XoaBaiError as exc:
                if lan_nghi >= len(NGHI_HAN_MUC):
                    kq["loi"] = f"{exc} — đã nghỉ {lan_nghi} lần, dừng dòng này"
                    return kq
                giay = NGHI_HAN_MUC[lan_nghi]
                lan_nghi += 1
                noi(f"[{page_id}] {exc} — nghỉ {giay // 60} phút rồi thử lại")
                sleep(giay)
                continue
            break
        if ok:
            kq["xoa"] += 1
            noi(f"[{page_id}] ✓ đã xoá {pid} ({p.get('created_time', '')[:10]}, {phan_loai(p)})")
        else:
            kq["loi_bai"].append((pid, ly_do))
            noi(f"[{page_id}] ✖ không xoá được {pid}: {ly_do}")
        if on_tien_do:
            on_tien_do({"page_id": page_id, "xoa": kq["xoa"], "khop": len(khop), "loi": len(kq["loi_bai"])})
        pct = han_muc_pct(h)
        if pct >= NGUONG_DUNG:
            noi(f"[{page_id}] hạn mức {pct:.0f}% — nghỉ 5 phút")
            sleep(NGHI_HAN_MUC[0])
        elif pct >= NGUONG_CHAM:
            sleep(max(cach_giay, 10.0))
        elif cach_giay > 0 and i + 1 < len(khop):
            sleep(cach_giay)
    kq["ok"] = not kq["loi"]
    return kq


def dong_txt(acc_id: str, page_id: str, bai: dict) -> str:
    """Dong ghi TXT sau khi xoa: acc|page|id bai|ngay dang|loai|link."""
    return "|".join([str(acc_id), str(page_id), str(bai.get("id", "")),
                     str(bai.get("created_time", ""))[:19], str(bai.get("loai", "")),
                     str(bai.get("permalink_url", ""))])
