"""Driver TUONG TAC X.com — dieu khien agent xwatch_agent.js luot newfeed /home.

Cung khuon core/fbwatch.py (tuong tac Facebook) va core/xpost.py (dang bai X):
  1. Dong Firefox cua acc, lam moi agent (manager.configure).
  2. Ghi lenh vao <profile>/qlfp-xwatch.json.
  3. Mo Firefox BINH THUONG qua CONG VPN (acc co NordVPN) roi toi https://x.com/home.
  4. Agent cuon newfeed, dung lai doc tung bai, tha tim, bam xem video, vao bai lay
     comment dau tien dang lai kem 3-5 icon; bao tien do
     ve qlfp-xwatch-result.json. Ham nay poll file do.
  5. Dong Firefox, tra {ok, state, xem, like, video, detail}. KHONG nem.

Trang thai agent: on-home | progress | done | error | logged-out | x-locked | seen.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Callable, Optional

from . import nordvpn

CMD_NAME = "qlfp-xwatch.json"
RESULT_NAME = "qlfp-xwatch-result.json"
X_HOME_URL = "https://x.com/home"

#: Dung lai moi bai bao nhieu giay (nguoi dung chinh duoc; mac dinh 5-10s).
DUNG_MIN = 5
DUNG_MAX = 10


def _path(profile_dir: str, name: str) -> str:
    return os.path.join(profile_dir, name)


def _clear(profile_dir: str) -> None:
    for name in (CMD_NAME, RESULT_NAME):
        try:
            os.remove(_path(profile_dir, name))
        except OSError:
            pass


def put_command(profile_dir: str, **command) -> None:
    os.makedirs(profile_dir, exist_ok=True)
    path = _path(profile_dir, CMD_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(command, fh, ensure_ascii=False)
    os.replace(tmp, path)


def _read_result(profile_dir: str) -> Optional[dict]:
    try:
        with open(_path(profile_dir, RESULT_NAME), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def tuong_tac(manager, account, *, so_like: int = 0, so_video: int = 0, so_comment: int = 0,
              so_follow: int = 0, tu_khoa=None, so_bai_tim: int = 0,
              gioi_han_giay: int = 120, dung_min: int = DUNG_MIN, dung_max: int = DUNG_MAX,
              url: str = X_HOME_URL, timeout: Optional[float] = None, thu: bool = False,
              log: Optional[Callable[[str], None]] = None) -> dict:
    """Mo Firefox vao x.com/home, luot newfeed trong ``gioi_han_giay`` giay.

    ``so_like``: so bai tha tim. ``so_video``: so video bam xem. ``so_comment``: so bai vao
    lay comment dau tien dang lai + 3-5 icon. ``dung_min/max``: so giay dung lai moi bai
    (ngau nhien). Tra {ok, state, xem, like, video, cmt, detail}.
    """
    noi = log or (lambda _m: None)
    han = max(10, int(gioi_han_giay))
    dmin = max(1, int(dung_min))
    dmax = max(dmin, int(dung_max))
    if timeout is None:
        timeout = han + 180        # + thoi gian mo trinh duyet / cong VPN / nap trang

    if not manager.is_installed(account):
        noi(f"[{account.id}] chua co profile X — tao...")
        manager.create(account)

    profile = manager.profile_dir(account)
    try:
        manager.close(account, wait=6.0)
    except OSError:
        pass
    manager.configure(account)
    _clear(profile)
    ds_tu = [str(t).strip() for t in (tu_khoa or []) if str(t).strip()]
    put_command(profile, action="xwatch", url=url, so_like=int(so_like), so_video=int(so_video),
                so_comment=int(so_comment), so_follow=int(so_follow), tu_khoa=ds_tu,
                so_bai_tim=int(so_bai_tim), gioi_han_giay=han, dung_min=dmin, dung_max=dmax,
                thu=bool(thu))

    noi(f"[{account.id}] mo Firefox → x.com/home: {so_like} tim, {so_video} video, "
        f"{so_comment} comment, ≤{han}s, dung {dmin}-{dmax}s/bai...")
    # Kiem VPN TRUOC (acc co NordVPN) — khong luot X bang IP that.
    cong = nordvpn.mo_qua_cong_vpn(manager, account, url, log=noi)
    if not cong["ok"]:
        _clear(profile)
        return {"ok": False, "state": "vpn-loi", "xem": 0, "like": 0, "video": 0, "cmt": 0,
                "follow": 0,
                "detail": f"VPN CHƯA NỐI: {cong['detail']}"}

    ket = {"ok": False, "state": "", "xem": 0, "like": 0, "video": 0, "cmt": 0,
           "follow": 0, "detail": ""}
    seen: set = set()
    # TRINH DUYET DA MO (qua cong VPN) -> tat ca phai nam trong try/finally.
    try:
        deadline = time.time() + timeout
        from core import procutil
        from core.fbbusiness import app_dir_cua
        app_dir = app_dir_cua(manager, account)
        canh_ff = procutil.CanhTrinhDuyet(app_dir)
        ke_tiep_kiem = 0.0
        while time.time() < deadline:
            if app_dir and time.time() >= ke_tiep_kiem:
                ke_tiep_kiem = time.time() + 3.0
                if canh_ff.da_dong():
                    ket.update(ok=False, state="browser-gone",
                               detail="trình duyệt đã đóng giữa chừng")
                    break
            r = _read_result(profile)
            if r:
                st = r.get("state") or ""
                det = str(r.get("detail") or "")
                ket["xem"] = int(r.get("xem") or ket["xem"])
                ket["like"] = int(r.get("like") or ket["like"])
                ket["video"] = int(r.get("video") or ket["video"])
                ket["cmt"] = int(r.get("cmt") or ket["cmt"])
                ket["follow"] = int(r.get("follow") or ket["follow"])
                key = st + "|" + det
                if key not in seen:
                    seen.add(key)
                    noi(f"[{account.id}] {st}: {det[:320]}")
                if st == "done":
                    ket.update(ok=True, state="done", detail=det)
                    break
                if st == "logged-out":
                    ket.update(ok=False, state="logged-out", detail=det or "acc chưa đăng nhập x.com")
                    break
                if st == "x-locked":
                    ket.update(ok=False, state="x-locked", detail=det or "acc bị X khoá/treo")
                    break
                if st == "error":
                    ket.update(ok=False, state="error", detail=det or "lỗi agent")
                    break
            time.sleep(2.0)
        else:
            ket.update(state="timeout", detail=f"hết giờ chờ ({int(timeout)}s)")
    finally:
        try:
            manager.close(account, wait=8.0)
        except OSError:
            pass
        _clear(profile)
    noi(f"[{account.id}] KẾT QUẢ tương tác X: {ket['state']} — xem {ket['xem']} bài, "
        f"tim {ket['like']}, video {ket['video']}, comment {ket['cmt']}, follow {ket['follow']}")
    return ket


# ---- DANG LAI TRICH DAN (Quote) ---------------------------------------------------------
#: Nguon bai de trich dan.
NGUON_KENH = "kenh"         # list kenh X nguoi dung nhap
NGUON_NEWFEED = "newfeed"   # chon ngau nhien tren newfeed /home
#: Moi buoc (gom bai / trich dan 1 bai) cho toi da bao lau.
BUOC_GOM_GIAY = 180
BUOC_QUOTE_GIAY = 150
_DUNG_HAN = ("logged-out", "x-locked", "browser-gone")


def chuan_kenh(dong: str) -> dict:
    """Mot dong nguoi dung nhap -> {"handle": ..} | {"link": ..} | {}. THUAN.

    Nhan: "@abc", "abc", "x.com/abc", "https://twitter.com/abc"; dong co /status/<id> la
    LINK BAI (trich dan dung bai do)."""
    s = str(dong or "").strip()
    if not s:
        return {}
    m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status(?:es)?/(\d{5,})", s)
    if m:
        return {"link": f"https://x.com/{m.group(1)}/status/{m.group(2)}"}
    m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})(?:[/?#]|$)", s)
    if m:
        s = m.group(1)
    s = s.lstrip("@").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", s):
        return {}
    if s.lower() in ("home", "explore", "search", "i", "messages", "notifications", "settings"):
        return {}
    return {"handle": s}


def tach_kenh(text) -> list:
    """Van ban nhieu dong / dau phay -> list muc chuan_kenh (bo trung, bo dong sai). THUAN.

    Nhan ca list DA TACH ({"handle"} / {"link"}) — giao dien tach roi moi dua xuong mo-dun, mo-dun
    tach lai lan nua (loi that 15/10: str(dict) khong khop -> "acc chua co list kenh X")."""
    if isinstance(text, (list, tuple)):
        dong = list(text)
    else:
        dong = str(text or "").replace(",", "\n").splitlines()
    ra, da = [], set()
    for d in dong:
        if isinstance(d, dict):
            k = chuan_kenh(d.get("link") or d.get("handle") or "")
        else:
            k = chuan_kenh(str(d))
        khoa = (k.get("handle") or k.get("link") or "").lower()
        if khoa and khoa not in da:
            da.add(khoa)
            ra.append(k)
    return ra


class _PhienXQuote:
    """Mot phien trinh duyet cho agent "xquote": mo QUA CONG VPN toi trang dau, chay tung BUOC
    (lenh co idx tang, cho dung ket qua cua buoc do), dong trinh duyet. Dung chung cho trich
    dan va follow kenh nguon."""

    def __init__(self, manager, account, *, thu: bool, noi, sleep):
        self.manager, self.account, self.thu, self.noi, self.sleep = manager, account, thu, noi, sleep
        self.profile = ""
        self.idx = 0
        self.app_dir = ""
        self.canh = None

    def mo(self, url_dau: str) -> dict:
        m, a = self.manager, self.account
        if not m.is_installed(a):
            self.noi(f"[{a.id}] chua co profile X — tao...")
            m.create(a)
        self.profile = m.profile_dir(a)
        try:
            m.close(a, wait=6.0)
        except OSError:
            pass
        m.configure(a)
        _clear(self.profile)
        # Lenh "cho": agent mo trang dau xong thi ngoi cho buoc that (idx 1...).
        put_command(self.profile, action="xquote", idx=0, url=url_dau, buoc="cho", thu=bool(self.thu))
        cong = nordvpn.mo_qua_cong_vpn(m, a, url_dau, log=self.noi)
        if not cong["ok"]:
            _clear(self.profile)
            return {"ok": False, "detail": f"VPN CHƯA NỐI: {cong['detail']}"}
        try:
            from core import procutil
            from core.fbbusiness import app_dir_cua
            self.app_dir = app_dir_cua(m, a)
            self.canh = procutil.CanhTrinhDuyet(self.app_dir)
        except Exception:  # noqa: BLE001
            self.app_dir, self.canh = "", None
        return {"ok": True, "detail": ""}

    def buoc(self, **cmd) -> dict:
        self.idx += 1
        try:
            os.remove(_path(self.profile, RESULT_NAME))
        except OSError:
            pass
        han_giay = cmd.pop("han_giay", None)
        put_command(self.profile, action="xquote", idx=self.idx, thu=bool(self.thu), **cmd)
        han = time.time() + (han_giay or (BUOC_QUOTE_GIAY if cmd.get("buoc") == "quote" else BUOC_GOM_GIAY))
        seen: set = set()
        ke_kiem = 0.0
        while time.time() < han:
            if self.app_dir and self.canh is not None and time.time() >= ke_kiem:
                ke_kiem = time.time() + 3.0
                if self.canh.da_dong():
                    return {"state": "browser-gone", "detail": "trình duyệt đã đóng giữa chừng"}
            r = _read_result(self.profile)
            if r and r.get("idx") == self.idx:
                st = str(r.get("state") or "")
                det = str(r.get("detail") or "")
                if st + "|" + det not in seen:
                    seen.add(st + "|" + det)
                    self.noi(f"[{self.account.id}] {st}: {det[:320]}")
                if st in ("quote-links", "quote-done", "quote-fail", "quote-follow", "quote-lich",
                          "quote-trung", "quote-node",
                          "error") + _DUNG_HAN:
                    return r
            self.sleep(1.5)
        return {"state": "timeout", "detail": f"hết giờ chờ bước {cmd.get('buoc')}"}

    def dong(self) -> None:
        try:
            self.manager.close(self.account, wait=8.0)
        except OSError:
            pass
        if self.profile:
            _clear(self.profile)


_MO_TA_DUNG = {"logged-out": "acc chưa đăng nhập x.com", "x-locked": "acc bị X khoá/treo",
               "browser-gone": "trình duyệt đã đóng giữa chừng"}


def _hang_quote(nguon: str, kenh, rnd) -> list:
    """Hang doi nguon trich dan: kenh xao ngau nhien, hoac [newfeed]."""
    if nguon == NGUON_KENH:
        hang = list(kenh or [])
        rnd.shuffle(hang)
        return hang
    return [{"newfeed": True}]


def _quote_trong_phien(ph: "_PhienXQuote", account, hang: list, *, so_bai: int, cmin: int,
                       cmax: int, thu: bool, dung, noi, lich_su, rnd, _sleep) -> dict:
    """TRICH DAN tren phien DA MO (dung chung cho dang_lai_trich_dan va chay_kich_ban).
    Tra {ok, state, quote, thu_bai, trung, rows, detail}. KHONG dong trinh duyet."""
    ket = {"ok": False, "state": "", "quote": 0, "thu_bai": 0, "trung": 0, "rows": [], "detail": ""}
    da_thu: set = set()
    # DAU VAN TAY bai goc acc DA trich dan, doc tu trang ca nhan: so lich su chi biet bai trich
    # dan TU KHI co so; bai trich dan truoc do / bang tay chi thay duoc o day (phan nhung bai goc
    # khong co link -> so bang "@kenh|dau doan chu"). Trang "Quotes" cua bai KHONG tin duoc (do
    # that 14/10: acc moi khong hien trong danh sach) va tim kiem X khong index acc moi.
    bo_ky: list = []
    if lich_su is not None and not thu:
        rl = ph.buoc(buoc="lich", url=f"https://x.com/{account.id}", handle=account.id, so=8)
        if str(rl.get("state") or "") in _DUNG_HAN:
            ket.update(state=str(rl.get("state")), detail=_MO_TA_DUNG[str(rl.get("state"))])
            return ket
        bo_ky = [str(k) for k in (rl.get("ky") or []) if str(k)]

    def thu_quote(url: str) -> Optional[str]:
        """Trich dan 1 link. Tra state lam DUNG CA LUOT (dang xuat...) hoac None."""
        if url in da_thu:
            return None
        da_thu.add(url)
        if lich_su is not None and not thu:
            duoc, vi = lich_su.xin_bai(account.id, url)
            if not duoc:
                ket["trung"] += 1
                noi(f"[{account.id}] bỏ qua {url.rsplit('/', 1)[-1]}: {vi}")
                return None
        if ket["thu_bai"] and cmax:
            nghi = rnd.randint(cmin, cmax)
            noi(f"[{account.id}] nghỉ {nghi}s trước bài kế...")
            _sleep(nghi)
        ket["thu_bai"] += 1
        r = ph.buoc(buoc="quote", url=url, bo_ky=bo_ky)
        st = str(r.get("state") or "")
        if st == "quote-trung":            # trang ca nhan cho thay acc DA trich dan bai nay
            ket["thu_bai"] -= 1
            ket["trung"] += 1
            if lich_su is not None:
                lich_su.ghi_xong(account.id, url, url)
            noi(f"[{account.id}] bỏ qua {url.rsplit('/', 1)[-1]}: acc đã trích dẫn bài này từ trước")
            return None
        ok = st == "quote-done"
        ket["rows"].append({"url": url, "ok": ok, "detail": str(r.get("detail") or st)})
        if lich_su is not None and not thu:
            if ok:
                lich_su.ghi_xong(account.id, url, url)
            else:
                lich_su.tra_bai(account.id, url)
        if ok:
            ket["quote"] += 1
        return st if st in _DUNG_HAN else None

    bo_qua = lich_su.bo_qua(account.id) if lich_su is not None else []
    dung_som = None
    for muc in hang:
        if ket["quote"] >= so_bai or dung() or dung_som:
            break
        if muc.get("link"):
            dung_som = thu_quote(muc["link"])
            continue
        con = so_bai - ket["quote"]
        if muc.get("handle"):
            gom = ph.buoc(buoc="gom", url=f"https://x.com/{muc['handle']}", handle=muc["handle"],
                          so=con * 2 + 2, bo_qua=bo_qua, bo_ky=bo_ky)
        else:
            gom = ph.buoc(buoc="gom", url=X_HOME_URL, handle="", so=con * 3 + 4, bo_qua=bo_qua,
                          bo_ky=bo_ky)
        st = str(gom.get("state") or "")
        if st in _DUNG_HAN:
            dung_som = st
            break
        links = [str(u) for u in (gom.get("links") or []) if str(u)]
        if gom.get("bo_ky_dem"):
            ket["trung"] += int(gom.get("bo_ky_dem") or 0)
        if muc.get("newfeed"):
            rnd.shuffle(links)          # newfeed: chon NGAU NHIEN trong cac bai da gom
        for u in links:
            if ket["quote"] >= so_bai or dung():
                break
            dung_som = thu_quote(u)
            if dung_som:
                break
    if dung_som:
        ket.update(ok=False, state=dung_som, detail=_MO_TA_DUNG[dung_som])
    else:
        ket.update(ok=ket["quote"] > 0 or (thu and any(r["ok"] for r in ket["rows"])),
                   state="done",
                   detail=f"trích dẫn {ket['quote']}/{so_bai} bài (thử {ket['thu_bai']} bài"
                          + (f", bỏ {ket['trung']} bài đã trích dẫn" if ket["trung"] else "") + ")")
    return ket


def dang_lai_trich_dan(manager, account, *, nguon: str = NGUON_NEWFEED, kenh=None,
                       so_bai: int = 3, cach_min: int = 20, cach_max: int = 60,
                       thu: bool = False, nen_dung: Optional[Callable[[], bool]] = None,
                       log: Optional[Callable[[str], None]] = None, lich_su=None,
                       _sleep=time.sleep, _rnd=None) -> dict:
    """Mo Firefox acc X, TRICH DAN (Quote) ``so_bai`` bai; noi dung = comment DAU TIEN cua bai,
    khong co thi CAPTION bai, + 3-5 icon.

    ``nguon`` = NGUON_KENH: bai cua cac kenh trong ``kenh`` (list chuan_kenh; muc la link bai
    thi trich dan dung bai do) — kenh xao ngau nhien, lan luot gom bai moi cua tung kenh.
    ``nguon`` = NGUON_NEWFEED: chon NGAU NHIEN tren newfeed /home.
    ``lich_su`` (core.quote_lich_su.LichSuQuote): CHONG TRUNG — bai acc nay (hoac acc khac khi
    chung) da trich dan thi bo qua; gom bai bo qua san cac ID do; xong thi ghi lai.
    ``cach_min..max`` giay nghi giua 2 bai. ``thu`` = go chu xong KHONG bam Dang, KHONG ghi lich
    su. Tra {ok, state, quote, thu_bai, trung, rows:[{url, ok, detail}], detail}. KHONG nem.
    """
    import random
    rnd = _rnd or random.Random()
    noi = log or (lambda _m: None)
    dung = nen_dung or (lambda: False)
    so_bai = max(1, int(so_bai or 1))
    cmin = max(0, int(cach_min or 0))
    cmax = max(cmin, int(cach_max or cmin))
    ket = {"ok": False, "state": "", "quote": 0, "thu_bai": 0, "trung": 0, "rows": [], "detail": ""}
    hang = _hang_quote(nguon, kenh, rnd)
    if not hang:
        ket.update(state="thieu-kenh", detail="chưa nhập kênh X nào")
        return ket
    dau = hang[0]
    url_dau = dau.get("link") or (f"https://x.com/{dau['handle']}" if dau.get("handle")
                                  else X_HOME_URL)
    noi(f"[{account.id}] trích dẫn {so_bai} bài từ "
        + (f"{len(hang)} kênh/link" if nguon == NGUON_KENH else "newfeed (ngẫu nhiên)") + "...")
    ph = _PhienXQuote(manager, account, thu=thu, noi=noi, sleep=_sleep)
    # Co so lich su -> mo TRANG CA NHAN acc truoc de doc bai da trich dan (buoc "lich").
    doc_lich = lich_su is not None and not thu
    mo = ph.mo(f"https://x.com/{account.id}" if doc_lich else url_dau)
    if not mo["ok"]:
        ket.update(state="vpn-loi", detail=mo["detail"])
        return ket
    # TRINH DUYET DA MO (qua cong VPN) -> tat ca phai nam trong try/finally.
    try:
        ket = _quote_trong_phien(ph, account, hang, so_bai=so_bai, cmin=cmin, cmax=cmax, thu=thu,
                                 dung=dung, noi=noi, lich_su=lich_su, rnd=rnd, _sleep=_sleep)
    finally:
        ph.dong()
    noi(f"[{account.id}] KẾT QUẢ trích dẫn X: {ket['state']} — {ket['detail']}")
    return ket


def follow_kenh(manager, account, kenh, *, thu: bool = False,
                nen_dung: Optional[Callable[[], bool]] = None,
                log: Optional[Callable[[str], None]] = None, _sleep=time.sleep) -> dict:
    """Vao TUNG kenh trong ``kenh`` (list chuan_kenh, chi muc co "handle"): CHUA follow thi bam
    Follow, DA follow thi BO QUA. Tra {ok, state, follow, da_follow, loi, rows, detail}. KHONG nem."""
    noi = log or (lambda _m: None)
    dung = nen_dung or (lambda: False)
    hs: list = []
    for k in kenh or []:
        h = (k or {}).get("handle")
        if h and h.lower() not in {x.lower() for x in hs}:
            hs.append(h)
    ket = {"ok": False, "state": "", "follow": 0, "da_follow": 0, "loi": 0, "rows": [], "detail": ""}
    if not hs:
        ket.update(state="thieu-kenh", detail="chưa có kênh X nào để follow")
        return ket
    noi(f"[{account.id}] follow {len(hs)} kênh nguồn (đã follow thì bỏ qua)...")
    ph = _PhienXQuote(manager, account, thu=thu, noi=noi, sleep=_sleep)
    mo = ph.mo(f"https://x.com/{hs[0]}")
    if not mo["ok"]:
        ket.update(state="vpn-loi", detail=mo["detail"])
        return ket
    try:
        dung_som = None
        for h in hs:
            if dung():
                break
            r = ph.buoc(buoc="follow", url=f"https://x.com/{h}", handle=h)
            st = str(r.get("state") or "")
            if st in _DUNG_HAN:
                dung_som = st
                break
            kq = str(r.get("kq") or "") if st == "quote-follow" else "loi"
            ket["rows"].append({"kenh": h, "kq": kq, "detail": str(r.get("detail") or st)})
            if kq == "follow":
                ket["follow"] += 1
            elif kq == "da_follow":
                ket["da_follow"] += 1
            elif kq != "thu":
                ket["loi"] += 1
            _sleep(2)
        if dung_som:
            ket.update(state=dung_som, detail=_MO_TA_DUNG[dung_som])
        else:
            ket.update(ok=ket["loi"] < len(ket["rows"]), state="done",
                       detail=f"follow mới {ket['follow']}, đã follow sẵn {ket['da_follow']}, "
                              f"lỗi {ket['loi']} / {len(hs)} kênh")
    finally:
        ph.dong()
    noi(f"[{account.id}] KẾT QUẢ follow kênh: {ket['state']} — {ket['detail']}")
    return ket


# ---- KICH BAN: chuoi node trong MOT phien trinh duyet ------------------------------------
def chay_kich_ban(manager, account, nodes, *, kenh_follow=None, kenh_quote=None, tu_khoa=None,
                  lay_lich_su: Optional[Callable[[bool], object]] = None,
                  xoa_follow: Optional[Callable[[str], None]] = None,
                  on_tien_do: Optional[Callable[[int, str, str], None]] = None,
                  thu: bool = False, nen_dung: Optional[Callable[[], bool]] = None,
                  log: Optional[Callable[[str], None]] = None,
                  _sleep=time.sleep, _rnd=None) -> dict:
    """Chay KICH BAN (list node da chuan hoa — core.kich_ban_x) cho MOT acc: qua cong VPN MOT
    lan, chay lan luot cac node BAT, dong trinh duyet.

    ``kenh_follow`` = list kenh follow RIENG cua acc (chuan_kenh); follow xong / da follow san ->
    goi ``xoa_follow(handle)`` (bo kenh khoi list cua acc). ``kenh_quote`` = list kenh trich dan
    cua acc. ``lay_lich_su(chung)`` -> so chong trung. ``on_tien_do(i, loai, mo_ta)`` bao node
    dang chay. Tra {ok, state, nodes:[{loai, ok, ...}], tong:{xem, like, video, cmt, follow,
    quote}, detail}. Node hong KHONG dung chuoi; dang xuat / acc khoa / trinh duyet dong thi dung.
    KHONG nem."""
    import random
    rnd = _rnd or random.Random()
    noi = log or (lambda _m: None)
    dung = nen_dung or (lambda: False)
    tien = on_tien_do or (lambda i, l, m: None)
    tong = {"xem": 0, "like": 0, "video": 0, "cmt": 0, "follow": 0, "quote": 0}
    ket = {"ok": False, "state": "", "nodes": [], "tong": tong, "detail": ""}
    viec = [(i, n) for i, n in enumerate(nodes or []) if n.get("bat", True)]
    if not viec:
        ket.update(state="thieu-node", detail="kịch bản không có node nào đang bật")
        return ket
    noi(f"[{account.id}] chạy kịch bản {len(viec)} node...")
    ph = _PhienXQuote(manager, account, thu=thu, noi=noi, sleep=_sleep)
    mo = ph.mo(X_HOME_URL)
    if not mo["ok"]:
        ket.update(state="vpn-loi", detail=mo["detail"])
        return ket
    # TRINH DUYET DA MO (qua cong VPN) -> tat ca phai nam trong try/finally.
    try:
        dung_som = None
        list_follow = [k for k in (kenh_follow or []) if k.get("handle")]
        for i, n in viec:
            if dung():
                ket["state"] = "dung"
                break
            loai = n.get("loai")
            ra = {"loai": loai, "ok": True, "detail": ""}
            st_node = ""                      # trang thai lam DUNG CA CHUOI (dang xuat...)
            if loai == "luot":
                gh = rnd.randint(int(n["gio_min"]), int(n["gio_max"]))
                tien(i, loai, f"lướt newfeed {gh}s")
                r = ph.buoc(buoc="luot", url=X_HOME_URL, so_like=n["so_like"], so_video=n["so_video"],
                            so_comment=n["so_comment"], gioi_han_giay=gh, dung_min=n["dung_min"],
                            dung_max=n["dung_max"], han_giay=gh + 240)
                st = str(r.get("state") or "")
                for k in ("xem", "like", "video", "cmt"):
                    ra[k] = int(r.get(k) or 0)
                    tong[k] += ra[k]
                ra.update(ok=st == "quote-node", detail=str(r.get("detail") or st))
                st_node = st
            elif loai == "follow":
                can, da = int(n["toi_da"]), 0
                ra.update(follow=0, da_follow=0, loi=0)
                st = ""
                if n.get("theo_list"):
                    for k in list_follow:
                        if da >= can or dung():
                            break
                        h = k["handle"]
                        tien(i, loai, f"follow @{h} ({da}/{can})")
                        r = ph.buoc(buoc="follow", url=f"https://x.com/{h}", handle=h)
                        st = str(r.get("state") or "")
                        if st in _DUNG_HAN:
                            break
                        kq = str(r.get("kq") or "") if st == "quote-follow" else "loi"
                        if kq == "follow":
                            da += 1
                            ra["follow"] += 1
                        elif kq == "da_follow":
                            ra["da_follow"] += 1
                        elif kq != "thu":
                            ra["loi"] += 1
                        if kq in ("follow", "da_follow") and callable(xoa_follow) and not thu:
                            xoa_follow(h)          # follow xong -> bo khoi list cua acc
                        _sleep(2)
                from core.kich_ban_x import tach_tu_khoa
                tu = tach_tu_khoa(tu_khoa if isinstance(tu_khoa, str) else "\n".join(tu_khoa or []))
                if st not in _DUNG_HAN and n.get("theo_tu_khoa") and tu and da < can and not dung():
                    tien(i, loai, f"tìm từ khoá để follow ({da}/{can})")
                    r = ph.buoc(buoc="tim", url=X_HOME_URL, tu_khoa=tu, so_bai=n["so_bai_tu_khoa"],
                                can=can - da, gioi_han_giay=900, han_giay=1100)
                    st = str(r.get("state") or "")
                    da += int(r.get("follow") or 0)
                    ra["follow"] += int(r.get("follow") or 0)
                if st not in _DUNG_HAN and n.get("goi_y") and da < can and not dung():
                    tien(i, loai, f"follow ở trang gợi ý ({da}/{can})")
                    r = ph.buoc(buoc="goiy", url=X_HOME_URL, can=can - da, gioi_han_giay=600,
                                han_giay=800)
                    st = str(r.get("state") or "")
                    da += int(r.get("follow") or 0)
                    ra["follow"] += int(r.get("follow") or 0)
                tong["follow"] += ra["follow"]
                ra["detail"] = (f"follow mới {ra['follow']}/{can}, đã follow sẵn {ra['da_follow']}"
                                + (f", lỗi {ra['loi']}" if ra["loi"] else ""))
                if st in _DUNG_HAN:
                    ra.update(ok=False, detail=_MO_TA_DUNG[st])
                st_node = st
            elif loai == "quote":
                hang = _hang_quote(NGUON_KENH if n.get("nguon") != "newfeed" else NGUON_NEWFEED,
                                   kenh_quote, rnd)
                if not hang:
                    ra.update(ok=False, detail="acc chưa có list kênh trích dẫn — bỏ qua node")
                else:
                    tien(i, loai, f"trích dẫn {n['so_bai']} bài")
                    ls = lay_lich_su(bool(n.get("khong_trung", True))) if callable(lay_lich_su) else None
                    q = _quote_trong_phien(ph, account, hang, so_bai=int(n["so_bai"]),
                                           cmin=int(n["cach_min"]), cmax=int(n["cach_max"]), thu=thu,
                                           dung=dung, noi=noi, lich_su=ls, rnd=rnd, _sleep=_sleep)
                    ra.update(ok=bool(q.get("ok")), quote=q["quote"], trung=q["trung"],
                              detail=q.get("detail") or "")
                    tong["quote"] += int(q["quote"])
                    st_node = str(q.get("state") or "")
            elif loai == "nghi":
                giay = rnd.randint(int(n["giay_min"]), int(n["giay_max"]))
                tien(i, loai, f"nghỉ {giay}s")
                noi(f"[{account.id}] nghỉ {giay}s giữa node...")
                con = float(giay)
                while con > 0 and not dung():        # nghi tung nhip -> bam Dung la thoat ngay
                    b = min(2.0, con)
                    _sleep(b)
                    con -= b
                ra["detail"] = f"nghỉ {giay}s"
            ket["nodes"].append(ra)
            noi(f"[{account.id}] node {i + 1} ({loai}): {ra['detail']}")
            if st_node in _DUNG_HAN:
                dung_som = st_node
                break
        if dung_som:
            ket.update(ok=False, state=dung_som, detail=_MO_TA_DUNG[dung_som])
        else:
            ket.update(ok=any(x.get("ok") for x in ket["nodes"]),
                       state=ket["state"] or "done",
                       detail=(f"xem {tong['xem']} · ♥ {tong['like']} · 💬 {tong['cmt']} · "
                               f"▶ {tong['video']} · follow {tong['follow']} · trích dẫn {tong['quote']}"))
    finally:
        ph.dong()
    noi(f"[{account.id}] KẾT QUẢ kịch bản: {ket['state']} — {ket['detail']}")
    return ket
