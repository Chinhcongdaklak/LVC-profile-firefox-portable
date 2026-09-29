"""Cai addon NordVPN (proxy extension cho Firefox) + dang nhap NordVPN.

Addon lay TU addons.mozilla.org (AMO) — ban da ky, Firefox release moi nhan:
  https://addons.mozilla.org/en-US/firefox/addon/nordvpn-proxy-extension/

Luong:
  1. tai_xpi()  -> tai file .xpi da ky ve cache (extension/nordvpn/), tra (path, guid, version).
  2. cai_vao_acc(manager, acc, xpi) -> chep vao <profile>/extensions/<guid>.xpi (dung install_extension san).
  3. dang_nhap(manager, acc, user, pass) -> mo Firefox, agent dien form dang nhap NordVPN (best-effort).

User/pass NordVPN luu o Settings (nordvpn_user/nordvpn_pass) — mot tai khoan dung chung cho cac acc.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Callable, Optional

from . import config

#: Slug tren AMO + API lay ban moi nhat (da ky).
AMO_SLUG = "nordvpn-proxy-extension"
AMO_API = f"https://addons.mozilla.org/api/v5/addons/addon/{AMO_SLUG}/"
#: GUID co dinh cua addon (ten file khi cai vao profile).
GUID = "nordvpnproxy@nordvpn.com"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/128.0"


#: Vi tri mac dinh khi cai (nguoi dung van doi duoc).
MAC_DINH_QUOC_GIA = "United States"
MAC_DINH_BANG = "New York"
#: API danh sach quoc gia + bang (subdivisions) that cua NordVPN.
AMO_COUNTRIES = "https://api.nordvpn.com/v1/servers/countries"


def cache_dir() -> str:
    return os.path.join(config.EXTENSION_DIR, "nordvpn")


# --- danh sach quoc gia + bang (subdivisions) -------------------------------

def doc_quoc_gia(raw: str) -> list:
    """Tach danh sach quoc gia tu JSON NordVPN. THUAN de test.

    Tra ``[{"name","code","bang":[{"name","code"}]}]`` sap theo ten. ``bang`` la
    subdivisions (US/CA/AU/DE/UK moi co); quoc gia khac -> ``bang`` rong -> chi chon
    quoc gia, de NordVPN tu chon vi tri trong nuoc.
    """
    d = json.loads(raw)
    out = []
    for c in d:
        bang = [{"name": s.get("name", ""), "code": s.get("code", ""), "id": s.get("id")}
                for s in (c.get("subdivisions") or []) if s.get("name")]
        bang.sort(key=lambda s: s["name"].lower())
        # Addon NordVPN liet ke THANH PHO (khong theo bang); API cho biet thanh pho thuoc
        # bang nao (subdivision_id) -> chon bang thi tool chon mot thanh pho trong bang do.
        tp = [{"name": t.get("name", ""), "bang_id": t.get("subdivision_id"),
               "servers": int(t.get("serverCount") or 0)}
              for t in (c.get("cities") or []) if t.get("name")]
        out.append({"name": c.get("name", ""), "code": c.get("code", ""), "bang": bang,
                    "thanh_pho": tp})
    out.sort(key=lambda c: c["name"].lower())
    return out


def thanh_pho_cua(quoc_gia_list: list, ten_quoc_gia: str, ten_bang: str) -> list:
    """Ten cac thanh pho NordVPN co server trong mot bang (rong neu khong co). THUAN."""
    for c in quoc_gia_list:
        if c["name"] != ten_quoc_gia:
            continue
        bid = next((b.get("id") for b in c["bang"] if b["name"] == ten_bang), None)
        if bid is None:
            return []
        tp = [t for t in c.get("thanh_pho") or [] if t.get("bang_id") == bid]
        tp.sort(key=lambda t: -t.get("servers", 0))
        return [t["name"] for t in tp]
    return []


def chon_thanh_pho(quoc_gia_list: list, ten_quoc_gia: str, ten_bang: str,
                   rand=None) -> str:
    """Chon NGAU NHIEN mot thanh pho trong bang (nhieu acc cung bang thi rai IP). Rong = khong co."""
    import random
    ds = thanh_pho_cua(quoc_gia_list, ten_quoc_gia, ten_bang)
    return (rand or random).choice(ds) if ds else ""


def tai_quoc_gia(force: bool = False,
                 log: Optional[Callable[[str], None]] = None) -> list:
    """Lay danh sach quoc gia + bang. Uu tien cache; loi mang -> doc cache cu; het -> [].

    Khong nem: giao dien van mo duoc du khong co mang (it ra co US/New York mac dinh).
    """
    noi = log or (lambda _m: None)
    os.makedirs(cache_dir(), exist_ok=True)
    cache = os.path.join(cache_dir(), "countries.json")
    if not force and os.path.isfile(cache):
        try:
            with open(cache, encoding="utf-8") as fh:
                return doc_quoc_gia(fh.read())
        except (OSError, ValueError):
            pass
    try:
        noi("Tải danh sách quốc gia NordVPN...")
        req = urllib.request.Request(AMO_COUNTRIES, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
        with open(cache, "w", encoding="utf-8") as fh:
            fh.write(raw)
        return doc_quoc_gia(raw)
    except Exception as exc:  # noqa: BLE001
        noi(f"Không tải được danh sách quốc gia ({exc}) — dùng cache nếu có.")
        if os.path.isfile(cache):
            try:
                with open(cache, encoding="utf-8") as fh:
                    return doc_quoc_gia(fh.read())
            except (OSError, ValueError):
                pass
        return []


def bang_cua(quoc_gia_list: list, ten_quoc_gia: str) -> list:
    """Danh sach bang cua mot quoc gia (rong neu quoc gia do khong chia bang)."""
    for c in quoc_gia_list:
        if c["name"] == ten_quoc_gia:
            return c["bang"]
    return []


# --- THUAN: doc AMO json ----------------------------------------------------

def doc_amo(raw: str) -> dict:
    """Tach {guid, version, url} tu JSON tra ve cua AMO API. THUAN de test."""
    d = json.loads(raw)
    cur = d.get("current_version") or {}
    f = cur.get("file") or {}
    return {
        "guid": d.get("guid") or GUID,
        "version": cur.get("version") or "?",
        "url": f.get("url") or "",
    }


# --- tai + cai --------------------------------------------------------------

def _tai(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as fh:
        fh.write(r.read())


def tai_xpi(force: bool = False,
            log: Optional[Callable[[str], None]] = None) -> tuple[str, str, str]:
    """Tai .xpi NordVPN da ky ve cache. Tra (duong_dan_xpi, guid, version).

    Da co ban trong cache thi dung lai (tru khi force). Nem RuntimeError khi loi mang.
    """
    noi = log or (lambda _m: None)
    os.makedirs(cache_dir(), exist_ok=True)
    try:
        req = urllib.request.Request(AMO_API, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            info = doc_amo(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Không lấy được thông tin addon NordVPN từ AMO: {exc}")
    url, version, guid = info["url"], info["version"], info["guid"]
    if not url:
        raise RuntimeError("AMO không trả về link .xpi của NordVPN.")
    dest = os.path.join(cache_dir(), f"nordvpn-{version}.xpi")
    if force or not os.path.isfile(dest):
        noi(f"Tải NordVPN {version} từ addons.mozilla.org...")
        _tai(url, dest)
    return dest, guid, version


def cai_vao_acc(manager, account, xpi: str) -> str:
    """Cai .xpi NordVPN vao profile acc (dung install_extension san). Tra mo ta."""
    return manager.install_extension(account, xpi)


def da_cai(manager, account) -> bool:
    """Acc da co addon NordVPN trong profile chua."""
    try:
        return GUID + ".xpi" in manager.installed_extensions(account)
    except Exception:  # noqa: BLE001
        return False


# --- ghim addon len thanh cong cu -------------------------------------------
#: Widget id cua nut NordVPN tren thanh (Firefox suy tu guid: @ va . -> _).
WIDGET_ID = "nordvpnproxy_nordvpn_com-browser-action"
_UI_PREF = "browser.uiCustomization.state"


def ghim_state(state: dict) -> dict:
    """Dua widget NordVPN vao nav-bar (bo khoi menu an). THUAN de test.

    Nhan/tra dict ``browser.uiCustomization.state`` da parse. Idempotent.
    """
    pl = state.setdefault("placements", {})
    nav = pl.setdefault("nav-bar", [])
    # Bo widget khoi cac vung an truoc, tranh trung.
    for vung in ("unified-extensions-area", "widget-overflow-fixed-list"):
        if vung in pl and WIDGET_ID in pl[vung]:
            pl[vung] = [w for w in pl[vung] if w != WIDGET_ID]
    if WIDGET_ID not in nav:
        # Dat truoc nut menu extension / menu chinh cho de thay; khong thi cuoi hang.
        chen = len(nav)
        for moc in ("unified-extensions-button", "PanelUI-menu-button"):
            if moc in nav:
                chen = nav.index(moc)
                break
        nav.insert(chen, WIDGET_ID)
    return state


def ghim_nordvpn(profile_dir: str) -> bool:
    """Ghim nut NordVPN len thanh cong cu cua profile (sua browser.uiCustomization.state).

    Sua prefs.js khi Firefox DANG DONG. Neu profile chua co pref (chua chay lan nao)
    thi ghi user.js de Firefox nhan widget vao nav-bar ngay khi addon nap. Tra True neu
    da ghim (hoac da o nav-bar san).
    """
    prefs = os.path.join(profile_dir, "prefs.js")
    # 1) Co san pref trong prefs.js -> sua truc tiep.
    if os.path.isfile(prefs):
        try:
            with open(prefs, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            lines = []
        for i, line in enumerate(lines):
            if _UI_PREF in line and "user_pref(" in line:
                state = _doc_pref_json(line)
                if state is None:
                    break
                ghim_state(state)
                lines[i] = _dong_pref_json(_UI_PREF, state)
                try:
                    with open(prefs, "w", encoding="utf-8") as fh:
                        fh.writelines(lines)
                    return True
                except OSError:
                    return False
    # 2) Chua co pref -> ghi user.js voi state toi thieu (Firefox nap luc khoi dong).
    return _ghi_user_js_ghim(profile_dir)


def _doc_pref_json(line: str):
    """Lay dict JSON tu dong user_pref("...", "<json escaped>");. None neu hong."""
    try:
        dau = line.index('",', line.index(_UI_PREF)) + 2
        raw = line[dau:].strip()
        raw = raw.rstrip(");").strip()
        # raw la mot chuoi JSON (co dau nhay + escape) -> json.loads 2 lan.
        return json.loads(json.loads(raw))
    except (ValueError, IndexError):
        return None


def _dong_pref_json(pref: str, state: dict) -> str:
    inner = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    return f'user_pref("{pref}", {json.dumps(inner, ensure_ascii=False)});\n'


def _ghi_user_js_ghim(profile_dir: str) -> bool:
    """Profile chua co pref: them dong user.js dat widget vao nav-bar toi thieu."""
    state = {"placements": {"nav-bar": ["back-button", "forward-button",
             "stop-reload-button", "urlbar-container", "downloads-button",
             WIDGET_ID, "unified-extensions-button"]},
             "currentVersion": 0}
    try:
        os.makedirs(profile_dir, exist_ok=True)
        with open(os.path.join(profile_dir, "user.js"), "a", encoding="utf-8") as fh:
            fh.write(_dong_pref_json(_UI_PREF, state))
        return True
    except OSError:
        return False


# --- dang nhap NordVPN (qua trang my.nordaccount.com) -----------------------
CMD_NAME = "qlfp-nord.json"
RESULT_NAME = "qlfp-nord-result.json"
#: Mo thang trang dang nhap Nord Account (agent se dien email + pass o day).
LOGIN_URL = "https://my.nordaccount.com/login/"

VAO = "vao"
SAI = "sai_thong_tin"
KHONG_RO = "khong_ro"
THIEU = "thieu_thong_tin"


def _clear(profile_dir: str) -> None:
    for n in (CMD_NAME, RESULT_NAME):
        try:
            os.remove(os.path.join(profile_dir, n))
        except OSError:
            pass


def _put_cmd(profile_dir: str, user: str, mat_khau: str,
             quoc_gia: str = "", bang: str = "") -> None:
    os.makedirs(profile_dir, exist_ok=True)
    cmd = {"action": "nordlogin", "email": user, "pass": mat_khau,
           # Vi tri muon dat trong popup NordVPN. bang rong -> de NordVPN tu chon.
           "country": quoc_gia or "", "state": bang or "",
           "delay": 1500, "timeout": 180000}
    with open(os.path.join(profile_dir, CMD_NAME), "w", encoding="utf-8") as fh:
        json.dump(cmd, fh, ensure_ascii=False)


def _read_result(profile_dir: str) -> Optional[dict]:
    try:
        with open(os.path.join(profile_dir, RESULT_NAME), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def danh_gia(states: set, het_gio: bool) -> Optional[str]:
    """Ket luan tu tap trang thai agent. THUAN de test."""
    if "nord-logged-in" in states:
        return VAO
    if "nord-wrong" in states:
        return SAI
    if het_gio:
        return KHONG_RO
    return None


def dang_nhap(manager, account, user: str, mat_khau: str, *,
              quoc_gia: str = "", bang: str = "", timeout: float = 180.0,
              log: Optional[Callable[[str], None]] = None) -> dict:
    """Mo Firefox -> trang Nord Account -> agent dien email + pass. Tra {ok, status, detail}.

    ``quoc_gia``/``bang``: vi tri muon dat trong popup NordVPN (bang rong = NordVPN tu chon).
    Best-effort: dang nhap Nord Account tren web. Sau do addon NordVPN nhan phien
    qua OAuth. Khong nem (tru thieu thong tin).
    """
    noi = log or (lambda _m: None)
    if not user or not mat_khau:
        return {"ok": False, "status": THIEU, "detail": "Thiếu user hoặc pass NordVPN."}
    if not manager.is_installed(account):
        manager.create(account)
    profile = manager.profile_dir(account)
    manager.close(account, wait=6.0)
    manager.configure(account)
    # Ghim nut NordVPN len thanh cong cu (Firefox dang dong) -> mo len la thay ngay.
    try:
        ghim_nordvpn(profile)
    except Exception:  # noqa: BLE001
        pass
    _clear(profile)
    _put_cmd(profile, user, mat_khau, quoc_gia, bang)

    noi(f"[{account.id}] mở Firefox → đăng nhập NordVPN...")
    manager.launch(account, url=LOGIN_URL)

    states: set = set()
    _seen: set = set()
    deadline = time.time() + timeout
    status = None
    try:
        while time.time() < deadline:
            r = _read_result(profile)
            if r:
                st = r.get("state")
                det = "" if r.get("detail") is None else str(r.get("detail"))
                if st == "seen":
                    if det not in _seen:
                        _seen.add(det)
                        noi(f"[{account.id}] seen: {det[:150]}")
                elif st and st not in states:
                    states.add(st)
                    noi(f"[{account.id}] {st}" + (f": {det[:60]}" if det else ""))
            status = danh_gia(states, het_gio=False)
            if status:
                break
            time.sleep(1.0)
        if status is None:
            status = danh_gia(states, het_gio=True) or KHONG_RO
    finally:
        try:
            manager.close(account, wait=8.0)
        except OSError:
            pass
        _clear(profile)

    ok = status == VAO
    detail = {VAO: "đăng nhập NordVPN thành công", SAI: "sai user/pass NordVPN",
              KHONG_RO: "không rõ kết quả (hết giờ) — có thể cần bấm Đăng nhập trong popup addon"}.get(
        status, status or "")
    noi(f"[{account.id}] NordVPN: {status} — {detail}")
    return {"ok": ok, "status": status, "detail": detail}


# --- CONG VPN: kiem VPN da noi truoc khi vao X ----------------------------------
#: Firefox vua mo thi vai giay dau trang web di THANG bang IP that (addon chua noi lai,
#: Kill switch khong chan khoang nay -- da do that 28/09). Moi luong dang nhap / dang bai
#: X phai qua cong nay: mo ipinfo -> cho IP ra ngoai KHAC IP may -> moi sang x.com.
# /ip (chu thuan): /json bi trinh xem JSON cua Firefox thay trang -> agent khong chay.
CONG_URL = "https://ipinfo.io/ip"
CONG_TIMEOUT = 60.0
_IP_MAY: dict = {"ip": "", "at": 0.0}


def ip_may(force: bool = False) -> str:
    """IP that cua may (Python goi thang, khong qua VPN addon). Cache 5 phut. Rong = khong lay duoc."""
    if not force and _IP_MAY["ip"] and time.time() - _IP_MAY["at"] < 300:
        return _IP_MAY["ip"]
    for url in ("https://ipinfo.io/ip", "https://api.ipify.org"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                ip = r.read().decode("utf-8", "replace").strip()
            if ip and len(ip) < 64:
                _IP_MAY.update(ip=ip, at=time.time())
                return ip
        except Exception:  # noqa: BLE001
            continue
    return ""


def danh_gia_cong(states: set) -> Optional[str]:
    """Ket luan cong VPN tu trang thai agent. THUAN."""
    if "vpn-ok" in states:
        return "ok"
    if "vpn-fail" in states:
        return "fail"
    return None


def mo_qua_cong_vpn(manager, account, url_tiep: str, *, timeout: float = CONG_TIMEOUT,
                    log: Optional[Callable[[str], None]] = None) -> dict:
    """Mo Firefox QUA CONG VPN roi moi toi ``url_tiep``. Tra {ok, bo_qua, ip, noi, detail}.

    Acc KHONG cai addon NordVPN -> mo thang ``url_tiep`` (bo_qua=True, ok=True).
    Co addon: mo ipinfo, agent doi IP ra ngoai khac IP may roi tu chuyen sang ``url_tiep``.
    Het gio van IP that -> DONG trinh duyet, ok=False (khong duoc vao X bang IP that).
    Nguoi goi da close + configure profile + dat lenh agent cua minh truoc khi goi.
    """
    noi = log or (lambda _m: None)
    if not da_cai(manager, account):
        manager.launch(account, url=url_tiep)
        return {"ok": True, "bo_qua": True, "ip": "", "noi": "", "detail": "không dùng NordVPN"}
    may = ip_may()
    if not may:
        return {"ok": False, "bo_qua": False, "ip": "", "noi": "",
                "detail": "không lấy được IP thật của máy để kiểm VPN (mất mạng?)"}
    profile = manager.profile_dir(account)
    _clear(profile)
    with open(os.path.join(profile, CMD_NAME), "w", encoding="utf-8") as fh:
        json.dump({"action": "nordcho", "ip_may": may, "next": url_tiep,
                   "timeout": int(timeout * 1000)}, fh, ensure_ascii=False)
    noi(f"[{account.id}] kiểm VPN trước (IP máy {may})...")
    manager.launch(account, url=CONG_URL)
    states: set = set()
    _thay: set = set()
    chi_tiet: dict = {}
    t0 = time.time()
    try:
        while time.time() < t0 + timeout + 20:
            r = _read_result(profile)
            if r:
                st = r.get("state")
                det = str(r.get("detail") or "")
                if st == "seen" and det not in _thay:
                    _thay.add(det)
                    noi(f"[{account.id}] {det[:100]}")
                if st in ("vpn-ok", "vpn-fail") and st not in states:
                    states.add(st)
                    if st == "vpn-ok":
                        try:
                            chi_tiet = json.loads(r.get("detail") or "{}")
                        except ValueError:
                            chi_tiet = {}
            kq = danh_gia_cong(states)
            if kq:
                break
            time.sleep(0.5)
    finally:
        _clear(profile)          # xong cong -> bo lenh, tai lai ipinfo khong bi chuyen trang nua
    if danh_gia_cong(states) == "ok":
        vi_tri = ", ".join(x for x in (chi_tiet.get("city"), chi_tiet.get("region"),
                                       chi_tiet.get("country")) if x)
        noi(f"[{account.id}] VPN OK: {chi_tiet.get('ip')} ({vi_tri}) sau {time.time() - t0:.0f}s → vào trang")
        return {"ok": True, "bo_qua": False, "ip": chi_tiet.get("ip", ""), "noi": vi_tri,
                "detail": f"VPN {chi_tiet.get('ip')} {vi_tri}"}
    try:
        manager.close(account, wait=8.0)
    except OSError:
        pass
    detail = (f"VPN chưa nối sau {timeout:.0f}s (vẫn IP thật {may}) — không vào X. "
              "Chạy lại 'Cài NordVPN' để chọn vị trí / kiểm tra tài khoản NordVPN.")
    noi(f"[{account.id}] {detail}")
    return {"ok": False, "bo_qua": False, "ip": may, "noi": "", "detail": detail}


# --- cai dat sau dang nhap: Spoofing + Kill switch + vi tri --------------------
CAN_DANG_NHAP = "can_dang_nhap"
XONG = "xong"


def uuid_addon(profile_dir: str) -> str:
    """UUID moz-extension cua addon NordVPN trong profile (pref extensions.webextensions.uuids)."""
    try:
        with open(os.path.join(profile_dir, "prefs.js"), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "extensions.webextensions.uuids" in line:
                    raw = line[line.index('",') + 2:].strip().rstrip(");").strip()
                    return json.loads(json.loads(raw)).get(GUID, "")
    except (OSError, ValueError):
        pass
    return ""


def danh_gia_cai_dat(states: set) -> Optional[str]:
    """Ket luan tu tap trang thai agent nordsetup. THUAN de test."""
    if "nord-wrong" in states:
        return SAI
    if "nord-need-login" in states:
        return CAN_DANG_NHAP
    if "nord-setup-done" in states:
        return XONG
    return None


def cai_dat_vpn(manager, account, *, quoc_gia: str = "", thanh_pho: str = "",
                user: str = "", mat_khau: str = "",
                timeout: float = 240.0, log: Optional[Callable[[str], None]] = None) -> dict:
    """Mo popup addon (index.html) trong tab: NOI vi tri TRUOC, noi xong moi BAT Spoofing + Kill switch.

    ``thanh_pho`` rong -> bam thang dong quoc gia (NordVPN tu chon server trong nuoc).
    Tra {ok, status, spoof, kill, vi_tri, ip, detail}. ok = ca hai cong tac bat + (neu
    co vi tri) da ket noi. status "can_dang_nhap" = addon chua dang nhap.
    """
    noi = log or (lambda _m: None)
    if not manager.is_installed(account):
        manager.create(account)
    profile = manager.profile_dir(account)
    manager.close(account, wait=6.0)
    manager.configure(account)
    uid = uuid_addon(profile)
    if not uid:
        return {"ok": False, "status": "chua_cai", "detail": "profile chưa có addon NordVPN (hoặc chưa mở lần nào)."}
    _clear(profile)
    with open(os.path.join(profile, CMD_NAME), "w", encoding="utf-8") as fh:
        # email/pass: addon chua dang nhap -> agent bam "Log in" trong popup, tab Nord Account
        # mo ra (chua co phien web) thi agent dien o do. Lenh xoa ngay khi xong (_clear).
        json.dump({"action": "nordsetup", "country": quoc_gia or "", "city": thanh_pho or "",
                   "email": user or "", "pass": mat_khau or "", "delay": 1500},
                  fh, ensure_ascii=False)
    noi(f"[{account.id}] mở popup NordVPN → bật Spoofing + Kill switch"
        + (f" → {thanh_pho or quoc_gia}" if quoc_gia else "") + "...")
    manager.launch(account, url=f"moz-extension://{uid}/index.html")

    states: set = set()
    cuoi: dict = {}
    status = None
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            r = _read_result(profile)
            if r:
                st = r.get("state")
                det = "" if r.get("detail") is None else str(r.get("detail"))
                # Agent co the bao 2 trang thai trong CUNG mot nhip -> file bi ghi de;
                # quet ca mang log de khong sot (vd nord-connected ngay truoc setup-done).
                for dong in r.get("log") or []:
                    ten = str(dong).split(":", 1)[0]
                    if ten.startswith("nord-") and ten not in states and ten != st:
                        states.add(ten)
                        noi(f"[{account.id}] {str(dong)[:100]}")
                if st and st != "seen" and st not in states:
                    states.add(st)
                    noi(f"[{account.id}] {st}" + (f": {det[:80]}" if det else ""))
                if st == "nord-setup-done":
                    try:
                        cuoi = json.loads(det)
                    except ValueError:
                        cuoi = {}
            status = danh_gia_cai_dat(states)
            if status:
                break
            time.sleep(0.7)
    finally:
        try:
            manager.close(account, wait=8.0)
        except OSError:
            pass
        _clear(profile)

    if status == CAN_DANG_NHAP:
        return {"ok": False, "status": status, "detail": "addon NordVPN chưa đăng nhập"}
    if status == SAI:
        return {"ok": False, "status": status, "detail": "sai user/pass NordVPN"}
    if status is None:
        return {"ok": False, "status": KHONG_RO, "detail": "hết giờ, không rõ kết quả"}
    spoof, kill = bool(cuoi.get("spoof")), bool(cuoi.get("kill"))
    noi_ok = (not quoc_gia) or bool(cuoi.get("ket_noi")) or "nord-connected" in states
    if not noi_ok:
        # Thu tu chot: noi VPN TRUOC; noi khong duoc thi agent KHONG bat 2 cong tac.
        return {"ok": False, "status": status, "spoof": spoof, "kill": kill,
                "vi_tri": cuoi.get("vi_tri", ""), "ip": "",
                "detail": f"không kết nối được {thanh_pho or quoc_gia} — chưa bật Spoofing/Kill switch"}
    thieu = [ten for ten, ok in (("Spoofing", spoof), ("Kill switch", kill)) if not ok]
    detail = ("đã bật Spoofing + Kill switch" + (f", nối {cuoi.get('vi_tri')}"
                                                 if quoc_gia and noi_ok else "")
              if not thieu else "chưa xong: " + ", ".join(thieu))
    return {"ok": not thieu, "status": status, "spoof": spoof, "kill": kill,
            "vi_tri": cuoi.get("vi_tri", ""), "ip": cuoi.get("ip", ""), "detail": detail}


# --- CHAY NHIEU ACC CUNG LUC (o "Luong" cua tab X) -------------------------------
def xu_ly_mot_acc(manager, account, *, xpi: str, user: str, mat_khau: str,
                  quoc_gia: str = "", thanh_pho: str = "", chi_cai: bool = False,
                  log: Optional[Callable[[str], None]] = None) -> dict:
    """Mot acc tron goi: cai addon -> (neu can) dang nhap -> noi vi tri -> bat Spoofing + Kill switch.

    Tra {id, cai, ok, detail, vi_tri}. Khong nem: loi acc nay khong lam hong acc khac.
    """
    noi = log or (lambda _m: None)
    ra = {"id": account.id, "cai": False, "ok": False, "detail": "", "vi_tri": ""}
    try:
        if not manager.is_installed(account):
            manager.create(account)
        if manager.is_running(account):
            manager.close(account, wait=3.0)
        cai_vao_acc(manager, account, xpi)
        ra["cai"] = True
    except Exception as exc:  # noqa: BLE001
        ra["detail"] = f"lỗi cài addon: {exc}"
        return ra
    if chi_cai:
        ra.update(ok=True, detail="đã cài addon")
        return ra
    try:
        kq = cai_dat_vpn(manager, account, quoc_gia=quoc_gia, thanh_pho=thanh_pho,
                         user=user, mat_khau=mat_khau, log=noi)
        if kq.get("status") in (CAN_DANG_NHAP, "chua_cai"):
            # Addon chua dang nhap (hoac profile chua tung mo -> chua co uuid): dang nhap roi lam lai.
            dn = dang_nhap(manager, account, user, mat_khau, log=noi)
            if not dn.get("ok"):
                ra["detail"] = f"đăng nhập NordVPN: {dn.get('detail') or dn.get('status')}"
                return ra
            kq = cai_dat_vpn(manager, account, quoc_gia=quoc_gia, thanh_pho=thanh_pho,
                             user=user, mat_khau=mat_khau, log=noi)
        ra.update(ok=bool(kq.get("ok")), detail=kq.get("detail") or kq.get("status") or "",
                  vi_tri=kq.get("vi_tri") or "")
    except Exception as exc:  # noqa: BLE001
        ra["detail"] = f"lỗi: {exc}"
    return ra


def chay_nhieu(manager, accounts, *, xpi: str, user: str, mat_khau: str,
               quoc_gia: str = "", bang: str = "", quoc_gia_list=None, chi_cai: bool = False,
               workers: int = 2, log: Optional[Callable[[str], None]] = None,
               on_row: Optional[Callable[[dict], None]] = None) -> list:
    """Chay xu_ly_mot_acc cho NHIEU acc SONG SONG (toi da ``workers`` Firefox cung luc).

    Moi acc mot thanh pho NGAU NHIEN trong bang (rai IP). Tra danh sach ket qua theo
    thu tu acc. ``on_row(kq)`` goi ngay khi tung acc xong (cap nhat giao dien).
    """
    from concurrent.futures import ThreadPoolExecutor
    ds = list(accounts)
    if not ds:
        return []
    n = max(1, min(int(workers or 1), len(ds)))

    def mot(a):
        tp = chon_thanh_pho(quoc_gia_list or [], quoc_gia, bang) if bang else ""
        kq = xu_ly_mot_acc(manager, a, xpi=xpi, user=user, mat_khau=mat_khau,
                           quoc_gia=quoc_gia, thanh_pho=tp, chi_cai=chi_cai, log=log)
        if on_row:
            try:
                on_row(kq)
            except Exception:  # noqa: BLE001
                pass
        return kq

    with ThreadPoolExecutor(max_workers=n, thread_name_prefix="nordvpn") as pool:
        return list(pool.map(mot, ds))
