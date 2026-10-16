"""Chuyen may: GOM acc + profile + trang auto dang cua may A thanh MOT file .zip,
roi GOP THEM vao may B (nguoi dung chot 14/10).

Luat gop (nguoi dung chot):
  * Acc trung ID -> GHI DE bang ban cua may A (thong tin + profile).
  * Profile goi NHE: chi du lieu dang nhap (thu muc Data/profile, bo cache);
    may B tu cai lai Firefox (ProfileManager.create) roi dat du lieu vao.
  * Video KHONG goi: may B chon lai thu muc cho tung trang (ban_do thu muc).
  * Trang auto dang trung (cung ID fanpage / ID nhom / acc dang) voi trang may B
    dang co -> BO QUA, giu trang cua B (tranh hai trang cung dang mot fanpage).

Vi sao khong chep thang thu muc data/: file trang dat ten theo SO (autoup-2.json...),
may nao cung co autoup-2 -> chep la de mat trang cua B. O day moi trang nhap vao
duoc may B CAP SO MOI con trong (AutoUpManager.add), khong file nao cua B bi de.

Trang nhap vao LUON TAT "Bat tu dong dang": may A co the van con chay -> hai may
cung dang la trung bai. Nguoi dung tu kiem roi bat.

Module THUAN (khong tkinter): nen_tang = {"fb"|"x"|"yt": NenTang(store, profiles,
autoup, data_dir)} — App truyen doi tuong THAT dang chay, thuoc truyen doi tuong tam.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import socket
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional

from core.store import Account

PHIEN_BAN_GOI = 1
TEN_MANIFEST = "manifest.json"
NEN_TANG = ("fb", "x", "yt")
TEN_NEN_TANG = {"fb": "Facebook", "x": "X.com", "yt": "YouTube"}

#: Thu muc / file trong profile KHONG goi: cache (Firefox tu tao lai), du lieu tai
#: lai duoc (safebrowsing, plugin giai ma), khoa phien, va LENH AGENT cua tool
#: (qlfp-*): mang lenh cu sang may B la agent tu chay lai lenh do khi mo trinh duyet.
BO_THU_MUC = {
    "cache2", "startupcache", "cache", "offlinecache", "safebrowsing",
    "gmp-widevinecdm", "gmp-gmpopenh264", "gmp", "shader-cache", "thumbnails",
    "datareporting", "crashes", "minidumps", "saved-telemetry-pings",
    "security_state", "jumplistcache",
}
BO_FILE = {"parent.lock", "lock", ".parentlock"}
#: Video/anh da nen san -> luu THANG (ZIP_STORED): nen lai chi ton CPU, khong nho di.
DUOI_MEDIA = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".flv", ".wmv",
              ".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp3", ".m4a", ".aac"}


@dataclass
class NenTang:
    """Mot nen tang tren MOT may: kho acc + quan ly profile + quan ly trang auto dang."""
    store: object                    # AccountStore
    profiles: object                 # ProfileManager
    autoup: object = None            # AutoUpManager (None = khong co trang)
    data_dir: str = ""               # noi dat hang doi bai (bai_cho_dang/job-N)


def _bo_qua(rel_parts: list) -> bool:
    """Duong dan TUONG DOI trong Data/profile co bi bo khi goi khong."""
    if not rel_parts:
        return False
    if rel_parts[0].lower() in BO_THU_MUC:
        return True
    ten = rel_parts[-1].lower()
    if ten in BO_FILE or ten.startswith("qlfp-"):
        return True
    return False


def _dai(p: str) -> str:
    r"""Duong dan dang \\?\ tren Windows: profile Firefox co file sau toi >260 ky tu
    (bookmarkbackups, storage/default/https+++...) -> khong co tien to nay la mo/ghi
    hong (DA GAP khi chay that: Errno 2 o bookmarkbackups)."""
    if os.name != "nt" or not p:
        return p
    p = os.path.abspath(p)
    if p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p


def _giai_nen(z, dau: str, dich_goc: str) -> int:
    """Giai moi file trong zip co ten bat dau ``dau`` vao ``dich_goc`` (giu cay thu muc)."""
    so = 0
    for n in z.namelist():
        if not n.startswith(dau) or n.endswith("/"):
            continue
        dich = _dai(os.path.join(dich_goc, *n[len(dau):].split("/")))
        os.makedirs(os.path.dirname(dich), exist_ok=True)
        with z.open(n) as src, open(dich, "wb") as dst:
            shutil.copyfileobj(src, dst)
        so += 1
    return so


def _chuan(p: str) -> str:
    return os.path.normcase(os.path.normpath(p)) if p else ""


# ====================================================================== XUAT
def khoa_trang(cfg: dict, platform: str) -> Optional[tuple]:
    """Dau hieu "cung dang vao mot cho" de nhan trang TRUNG. None = khong xet trung.

    Facebook: fanpage (page/lich cung tinh — cung mot fanpage) theo page_id, nhom theo
    group_id. X / YouTube dang len chinh acc -> theo tap acc dang.
    """
    kind = str(cfg.get("target_kind") or "page")
    if platform in ("x", "yt"):
        ids = [str(a) for a in (cfg.get("account_ids") or []) if str(a).strip()]
        if not ids and cfg.get("account_id"):
            ids = [str(cfg.get("account_id"))]
        return ("acc", kind, tuple(sorted(ids))) if ids else None
    if kind == "group":
        g = str(cfg.get("group_id") or "").strip()
        return ("group", g) if g else None
    p = str(cfg.get("page_id") or "").strip()
    return ("page", p) if p else None


def xuat_goi(dich: str, nen_tang: dict, *, co_profile: bool = True,
             co_acc: bool = True, co_trang: bool = True, co_video: bool = False,
             tien_do: Optional[Callable[[str], None]] = None) -> dict:
    """Gom moi thu cua may nay vao file ``dich`` (.zip). Tra bao cao.

    Acc dang MO trinh duyet: van goi thong tin acc nhung KHONG goi profile (cookies.sqlite
    dang ghi do -> chep ra la hong); bao cao liet ke de nguoi dung tat roi goi lai.
    """
    bao = tien_do or (lambda _m: None)
    bc = {"acc": {}, "trang": {}, "profile": 0, "profile_bo": [], "hang_doi": 0,
          "dich": dich}
    manifest = {
        "phien_ban_goi": PHIEN_BAN_GOI,
        "tao_luc": time.strftime("%Y-%m-%d %H:%M:%S"),
        "may": socket.gethostname(),
        "co_profile": bool(co_profile),
        "co_acc": bool(co_acc),
        "co_trang": bool(co_trang),
        "co_video": bool(co_video),
        "nen_tang": {},
    }
    tam = dich + ".dang-goi"
    with zipfile.ZipFile(tam, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for p in NEN_TANG:
            nt = nen_tang.get(p)
            if nt is None:
                continue
            store = nt.store
            accs = list(store.accounts)
            if co_acc:
                z.writestr(f"acc/{p}.json", json.dumps(
                    {"groups": list(store.group_names),
                     "accounts": [a.to_dict() for a in accs]},
                    ensure_ascii=False, indent=2))
                bc["acc"][p] = len(accs)
            else:
                bc["acc"][p] = 0
            co_pf = []
            if co_profile:
                for a in accs:
                    try:
                        if not nt.profiles.is_installed(a):
                            continue
                        if nt.profiles.is_running(a):
                            bc["profile_bo"].append(f"{TEN_NEN_TANG[p]} {a.id}")
                            continue
                    except Exception:
                        continue
                    bao(f"Đang gói profile {TEN_NEN_TANG[p]} {a.id}...")
                    goc = _dai(nt.profiles.profile_dir(a))
                    for thu_muc, con, files in os.walk(goc):
                        rel = os.path.relpath(thu_muc, goc)
                        phan = [] if rel == "." else rel.split(os.sep)
                        con[:] = [c for c in con if not _bo_qua(phan + [c])]
                        for f in files:
                            if _bo_qua(phan + [f]):
                                continue
                            nguon = os.path.join(thu_muc, f)
                            ten_zip = "/".join(["profile", p, a.folder] + phan + [f])
                            try:
                                z.write(nguon, ten_zip)
                            except OSError:
                                pass            # file dang bi khoa le te -> bo
                    co_pf.append(a.id)
                    bc["profile"] += 1
            trang = []
            mgr = nt.autoup if co_trang else None
            if mgr is not None:
                for job in list(mgr.jobs):
                    try:
                        job.save()               # chot trang thai dang trong bo nho
                    except Exception:
                        pass
                    try:
                        with open(job.path, encoding="utf-8") as fh:
                            raw = json.load(fh)
                    except (OSError, ValueError):
                        continue
                    z.writestr(f"trang/{p}/job-{job.job_id}.json",
                               json.dumps(raw, ensure_ascii=False, indent=2))
                    qd = str((raw.get("config") or {}).get("queue_dir") or "").strip()
                    if qd and os.path.isdir(qd):
                        qd = _dai(qd)
                        for thu_muc, _c, files in os.walk(qd):
                            rel = os.path.relpath(thu_muc, qd)
                            phan = [] if rel == "." else rel.split(os.sep)
                            for f in files:
                                z.write(os.path.join(thu_muc, f),
                                        "/".join(["hang_doi", p, job.job_id] + phan + [f]))
                                bc["hang_doi"] += 1
                    trang.append({"id": job.job_id, "name": job.name})
                z.writestr(f"trang/{p}/index.json", json.dumps(
                    {"tabs": [dict(t) for t in mgr.tabs],
                     "nhom": {k: list(v) for k, v in mgr.nhom_ds.items()},
                     "jobs": trang}, ensure_ascii=False, indent=2))
            bc["trang"][p] = len(trang)
            manifest["nen_tang"][p] = {"acc": bc["acc"][p], "profile": co_pf,
                                       "trang": len(trang)}
        manifest["video"] = []
        bc["video"] = {"thu_muc": 0, "file": 0, "byte": 0}
        if co_video:
            for goc_v in [f for f in thu_muc_video(nen_tang) if os.path.isdir(f)]:
                so = bc["video"]["thu_muc"]
                dem, byte = 0, 0
                goc_dai = _dai(goc_v)
                for thu_muc, _c, files in os.walk(goc_dai):
                    rel = os.path.relpath(thu_muc, goc_dai)
                    phan = [] if rel == "." else rel.split(os.sep)
                    for f in files:
                        nguon = os.path.join(thu_muc, f)
                        nen = (zipfile.ZIP_STORED if os.path.splitext(f)[1].lower() in DUOI_MEDIA
                               else zipfile.ZIP_DEFLATED)
                        bao(f"Đang gói video: {f}")
                        try:
                            z.write(nguon, "/".join(["video", str(so)] + phan + [f]),
                                    compress_type=nen)
                        except OSError:
                            continue
                        dem += 1
                        byte += os.path.getsize(nguon)
                manifest["video"].append({"so": so, "goc": goc_v,
                                          "ten": os.path.basename(os.path.normpath(goc_v)),
                                          "file": dem, "byte": byte})
                bc["video"]["thu_muc"] += 1
                bc["video"]["file"] += dem
                bc["video"]["byte"] += byte
        z.writestr(TEN_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
    os.replace(tam, dich)
    return bc


def thu_muc_video(nen_tang: dict) -> list:
    """Cac thu muc video (khong trung) cua MOI trang auto dang tren may nay."""
    ra, da = [], set()
    for p in NEN_TANG:
        nt = nen_tang.get(p)
        if nt is None or nt.autoup is None:
            continue
        for job in list(nt.autoup.jobs):
            f = str(getattr(job.config, "folder", "") or "").strip()
            if f and _chuan(f) not in da:
                da.add(_chuan(f))
                ra.append(f)
    return ra


def uoc_luong_video(nen_tang: dict) -> dict:
    """{"thu_muc", "file", "byte", "thieu": [thu muc khong ton tai]} — de nguoi dung biet goi nang co nao."""
    kq = {"thu_muc": 0, "file": 0, "byte": 0, "thieu": []}
    for f in thu_muc_video(nen_tang):
        if not os.path.isdir(f):
            kq["thieu"].append(f)
            continue
        kq["thu_muc"] += 1
        for thu_muc, _c, files in os.walk(_dai(f)):
            for ten in files:
                try:
                    kq["byte"] += os.path.getsize(os.path.join(thu_muc, ten))
                    kq["file"] += 1
                except OSError:
                    pass
    return kq


# ====================================================================== DOC
@dataclass
class Goi:
    duong_dan: str
    manifest: dict
    acc: dict = field(default_factory=dict)        # p -> {"groups", "accounts"}
    trang: dict = field(default_factory=dict)      # p -> {"index": {...}, "jobs": {id: raw}}
    profile: dict = field(default_factory=dict)    # p -> set(folder) co trong goi
    hang_doi: dict = field(default_factory=dict)   # p -> set(job_id) co hang doi
    video: list = field(default_factory=list)      # [{"so","goc","ten","file","byte"}]


class GoiLoi(Exception):
    pass


def doc_goi(duong_dan: str) -> Goi:
    try:
        z = zipfile.ZipFile(duong_dan)
    except (OSError, zipfile.BadZipFile) as exc:
        raise GoiLoi(f"Không mở được gói: {exc}") from exc
    with z:
        ten = set(z.namelist())
        if TEN_MANIFEST not in ten:
            raise GoiLoi("File này không phải gói chuyển máy của LVC Manager Profile "
                         "(thiếu manifest.json).")
        manifest = json.loads(z.read(TEN_MANIFEST).decode("utf-8"))
        if int(manifest.get("phien_ban_goi") or 0) > PHIEN_BAN_GOI:
            raise GoiLoi("Gói được tạo bằng bản tool MỚI hơn — hãy cập nhật tool máy này.")
        g = Goi(duong_dan, manifest)
        g.video = [v for v in manifest.get("video") or []
                   if isinstance(v, dict) and v.get("file")]
        for p in NEN_TANG:
            if f"acc/{p}.json" in ten:
                g.acc[p] = json.loads(z.read(f"acc/{p}.json").decode("utf-8"))
            if f"trang/{p}/index.json" in ten:
                idx = json.loads(z.read(f"trang/{p}/index.json").decode("utf-8"))
                jobs = {}
                for j in idx.get("jobs") or []:
                    k = f"trang/{p}/job-{j['id']}.json"
                    if k in ten:
                        jobs[str(j["id"])] = json.loads(z.read(k).decode("utf-8"))
                g.trang[p] = {"index": idx, "jobs": jobs}
            g.profile[p] = set()
            g.hang_doi[p] = set()
        for n in ten:
            phan = n.split("/")
            if len(phan) >= 4 and phan[0] == "profile" and phan[1] in g.profile:
                g.profile[phan[1]].add(phan[2])
            if len(phan) >= 4 and phan[0] == "hang_doi" and phan[1] in g.hang_doi:
                g.hang_doi[phan[1]].add(phan[2])
        return g


# ====================================================================== KE HOACH
def lap_ke_hoach(goi: Goi, nen_tang: dict, *, co_acc: bool = True, co_trang: bool = True,
                 co_profile: bool = True) -> dict:
    """Xem truoc: acc moi / ghi de, trang them / bo qua, cac thu muc video can chon lai.

    ``co_acc=False``: CHI nhap trang auto dang, KHONG dung acc nao cua may nay (nguoi dung
    tu chep profile bang tay, acc da co san o may moi). Trang nao dung acc may nay CHUA
    co -> ghi vao ``acc_thieu`` cua trang do de canh bao.
    """
    kh = {"acc_moi": {}, "acc_ghi_de": {}, "trang_them": {}, "trang_bo_qua": {},
          "thu_muc": [], "co_acc": bool(co_acc), "co_trang": bool(co_trang),
          "co_profile": bool(co_profile)}
    thu_muc = []
    for p in NEN_TANG:
        nt = nen_tang.get(p)
        a = (goi.acc.get(p) or {}) if co_acc else {}
        se_co = {str(r.get("id")) for r in a.get("accounts") or [] if r.get("id")}
        moi, de = [], []
        for raw in a.get("accounts") or []:
            ma = str(raw.get("id") or "")
            if not ma:
                continue
            (de if nt is not None and nt.store.get(ma) is not None else moi).append(ma)
        kh["acc_moi"][p], kh["acc_ghi_de"][p] = moi, de
        them, bo = [], []
        t = (goi.trang.get(p) or {}) if co_trang else {}
        da_co = {}
        if nt is not None and nt.autoup is not None:
            for j in nt.autoup.jobs:
                k = khoa_trang(j.config.to_dict(), p)
                if k is not None:
                    da_co.setdefault(k, j.name)
        for j in (t.get("index") or {}).get("jobs") or []:
            raw = (t.get("jobs") or {}).get(str(j["id"]))
            if raw is None:
                continue
            cfg = raw.get("config") or {}
            ten = str(j.get("name") or raw.get("name") or "")
            k = khoa_trang(cfg, p)
            if nt is None or nt.autoup is None:
                bo.append({"id": str(j["id"]), "ten": ten,
                           "ly_do": "máy này không có mục auto đăng tương ứng"})
            elif k is not None and k in da_co:
                bo.append({"id": str(j["id"]), "ten": ten,
                           "ly_do": f"máy này đã có trang '{da_co[k]}' đăng vào cùng chỗ"})
            else:
                ids = [str(x) for x in (cfg.get("account_ids") or []) if str(x).strip()]
                if not ids and cfg.get("account_id"):
                    ids = [str(cfg.get("account_id"))]
                thieu = [x for x in ids if x not in se_co
                         and (nt is None or nt.store.get(x) is None)]
                them.append({"id": str(j["id"]), "ten": ten,
                             "kind": str(cfg.get("target_kind") or "page"),
                             "folder": str(cfg.get("folder") or ""),
                             "acc_thieu": thieu})
                f = str(cfg.get("folder") or "").strip()
                if f and f not in thu_muc:
                    thu_muc.append(f)
        kh["trang_them"][p], kh["trang_bo_qua"][p] = them, bo
    kh["thu_muc"] = thu_muc
    return kh


def thay_goc(thu_muc: list, tu: str, thanh: str) -> dict:
    """Ban do thu muc: duong dan bat dau bang ``tu`` (khong phan biet hoa thuong, \\ hay /)
    doi phan dau thanh ``thanh``. Duong dan khong khop -> khong co trong ket qua."""
    tu_c = _chuan(tu).rstrip("\\/")
    ra = {}
    if not tu_c:
        return ra
    for f in thu_muc:
        fc = _chuan(f)
        if fc == tu_c or fc.startswith(tu_c + os.sep):
            duoi = os.path.normpath(f)[len(tu_c):].lstrip("\\/")
            ra[f] = os.path.join(thanh, duoi) if duoi else os.path.normpath(thanh)
    return ra


# ====================================================================== AP DUNG
def acc_can_tat(goi: Goi, kh: dict, nen_tang: dict) -> list:
    """Acc may B dang MO trinh duyet ma goi se ghi de profile -> phai tat truoc."""
    ra = []
    if not kh.get("co_profile", True):
        return ra
    for p in NEN_TANG:
        nt = nen_tang.get(p)
        if nt is None:
            continue
        for ma in kh["acc_ghi_de"].get(p) or []:
            acc = nt.store.get(ma)
            if acc is None or acc.folder not in goi.profile.get(p, set()):
                continue
            try:
                if nt.profiles.is_running(acc):
                    ra.append((p, acc))
            except Exception:
                pass
    return ra


def _gop_acc(goi: Goi, p: str, nt: NenTang, bc: dict) -> list:
    """Them acc moi + ghi de acc trung (sua TAI CHO doi tuong cu: noi khac dang giu tham chieu)."""
    a = goi.acc.get(p) or {}
    store = nt.store
    xong = []
    for raw in a.get("accounts") or []:
        if not raw.get("id"):
            continue
        moi = Account.from_dict(copy.deepcopy(raw))
        cu = store.get(moi.id)
        if cu is None:
            store.accounts.append(moi)
            bc["acc_them"].append(f"{TEN_NEN_TANG[p]} {moi.id}")
            xong.append(moi)
        else:
            for ten in Account.__dataclass_fields__:
                setattr(cu, ten, getattr(moi, ten))
            bc["acc_ghi_de"].append(f"{TEN_NEN_TANG[p]} {moi.id}")
            xong.append(cu)
    for g in a.get("groups") or []:
        g = str(g).strip()
        if g and g.lower() not in {x.lower() for x in store.group_names}:
            store.group_names.append(g)
    store.save()
    return xong


def _dat_profile(goi: Goi, p: str, nt: NenTang, acc: Account, khoa_zip) -> None:
    """Dat du lieu dang nhap tu goi vao profile cua acc tren may nay.

    Chua co Firefox -> cai (create) truoc. Thay Data/profile qua thu muc tam + ban cu:
    hong giua chung thi tra lai ban cu, khong de acc mat profile.
    """
    pm = nt.profiles
    if not pm.is_installed(acc):
        # create() co the do lai mui gio theo proxy va ghi vao acc -> giu nguyen ban may A.
        giu = (copy.deepcopy(acc.identity), acc.auto_identity)
        pm.create(acc)
        acc.identity, acc.auto_identity = giu
    data = os.path.dirname(pm.profile_dir(acc))
    tam = _dai(os.path.join(data, "_np"))
    cu_bak = _dai(os.path.join(data, "_pcu"))
    shutil.rmtree(tam, ignore_errors=True)
    os.makedirs(tam, exist_ok=True)
    with khoa_zip:
        with zipfile.ZipFile(goi.duong_dan) as z:
            if not _giai_nen(z, f"profile/{p}/{acc.folder}/", tam):
                shutil.rmtree(tam, ignore_errors=True)
                raise RuntimeError("gói không có dữ liệu profile của acc này")
    that = _dai(pm.profile_dir(acc))
    shutil.rmtree(cu_bak, ignore_errors=True)
    if os.path.isdir(that):
        os.rename(that, cu_bak)
    try:
        os.rename(tam, that)
    except OSError:
        if os.path.isdir(cu_bak) and not os.path.isdir(that):
            os.rename(cu_bak, that)
        raise
    shutil.rmtree(cu_bak, ignore_errors=True)
    pm.configure(acc)                 # ghi lai user.js / mozilla.cfg theo duong dan may nay


def _remap_media(item: dict, cu: str, moi: str) -> dict:
    cu_c = _chuan(cu)

    def doi(v):
        if isinstance(v, str) and v:
            vc = _chuan(v)
            if vc == cu_c or vc.startswith(cu_c + os.sep):
                return os.path.join(moi, os.path.normpath(v)[len(cu_c):].lstrip("\\/"))
        return v
    for k, v in list(item.items()):
        if isinstance(v, list):
            item[k] = [doi(x) for x in v]
        else:
            item[k] = doi(v)
    return item


def _gop_trang(goi: Goi, p: str, nt: NenTang, kh: dict, ban_do: dict, bc: dict) -> None:
    mgr = nt.autoup
    them = kh["trang_them"].get(p) or []
    if mgr is None or not them:
        return
    t = goi.trang.get(p) or {}
    idx = t.get("index") or {}
    tab_goi = {str(x.get("id")): x for x in idx.get("tabs") or [] if x.get("id")}
    nhom_goi = idx.get("nhom") or {}
    tab_map = {"": ""}

    def tab_cho(cu_id: str, kind: str) -> str:
        if not cu_id or cu_id not in tab_goi:
            return ""
        if cu_id in tab_map:
            return tab_map[cu_id]
        ten = str(tab_goi[cu_id].get("ten") or "").strip()
        for tb in mgr.tabs:
            if tb.get("kind") == kind and str(tb.get("ten") or "").strip().lower() == ten.lower():
                tab_map[cu_id] = tb["id"]
                return tb["id"]
        tab_map[cu_id] = mgr.them_tab(kind, ten)["id"]
        return tab_map[cu_id]

    for muc in them:
        raw = copy.deepcopy((t.get("jobs") or {}).get(muc["id"]) or {})
        cfg = raw.setdefault("config", {})
        kind = str(cfg.get("target_kind") or "page")
        job = mgr.add(name=muc["ten"], kind=kind)
        cfg["enabled"] = False
        f = str(cfg.get("folder") or "")
        cfg["folder"] = ban_do.get(f, f) if f else f
        cfg["tab_id"] = tab_cho(str(cfg.get("tab_id") or ""), kind)
        nhom = str(cfg.get("nhom") or "").strip()
        if nhom:
            mgr.them_nhom(kind, cfg["tab_id"], nhom)
        qd_cu = str(cfg.get("queue_dir") or "").strip()
        if qd_cu and muc["id"] in goi.hang_doi.get(p, set()):
            qd = os.path.join(nt.data_dir, "bai_cho_dang", f"job-{job.job_id}")
            if os.path.isdir(qd) and os.listdir(qd):
                qd = qd + f"-nhap-{p}"
            with zipfile.ZipFile(goi.duong_dan) as z:
                _giai_nen(z, f"hang_doi/{p}/{muc['id']}/", qd)
            cfg["queue_dir"] = qd
            raw["queue"] = [_remap_media(dict(x), qd_cu, qd)
                            for x in raw.get("queue") or [] if isinstance(x, dict)]
        elif qd_cu:
            cfg["queue_dir"] = ""          # hang doi khong co trong goi -> khong tro bay
            raw["queue"] = []
        raw["name"] = muc["ten"]
        with open(job.path, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, ensure_ascii=False, indent=2)
        job.load()
        job.name = muc["ten"]
        job.config.enabled = False
        job.save()
        bc["trang_them"].append((TEN_NEN_TANG[p], muc["ten"], job.job_id,
                                 cfg["folder"]))
    # Nhom rong (chua co trang) cua tab mac dinh cung mang sang cho du.
    for khoa, ds in nhom_goi.items():
        kind, _, tab_cu = str(khoa).partition("|")
        if tab_cu:
            continue
        for ten in ds or []:
            mgr.them_nhom(kind, "", ten)
    mgr.save_index()
    try:
        mgr._wire()
    except Exception:
        pass


def noi_giai_video(goi: Goi, video_vao: str) -> dict:
    """Thu muc goc may A -> thu muc se giai nen tren may nay (khong trung ten, khong de len
    thu muc dang co du lieu)."""
    ra, dung = {}, set()
    for v in goi.video:
        ten = str(v.get("ten") or f"video-{v.get('so')}").strip() or f"video-{v.get('so')}"
        dich, so = os.path.join(video_vao, ten), 2
        while _chuan(dich) in dung or (os.path.isdir(dich) and os.listdir(dich)):
            dich = os.path.join(video_vao, f"{ten} ({so})")
            so += 1
        dung.add(_chuan(dich))
        ra[v["goc"]] = dich
    return ra


def ap_dung(goi: Goi, kh: dict, nen_tang: dict, ban_do: Optional[dict] = None, *,
            so_luong: int = 1, video_vao: str = "",
            tien_do: Optional[Callable[[str], None]] = None) -> dict:
    """Gop goi vao may nay theo ke hoach ``kh`` (lap_ke_hoach). Tra bao cao.

    ``video_vao`` khac rong -> GIAI NEN kho video trong goi vao do (moi thu muc may A mot
    thu muc con) va trang tro thang vao thu muc vua giai (de len ban do nguoi dung chon).
    """
    bao = tien_do or (lambda _m: None)
    ban_do = dict(ban_do or {})
    bc = {"acc_them": [], "acc_ghi_de": [], "profile_ok": [], "profile_loi": [],
          "trang_them": [], "trang_bo_qua": [], "loi": [], "video": []}
    if video_vao and goi.video:
        noi = noi_giai_video(goi, video_vao)
        with zipfile.ZipFile(goi.duong_dan) as z:
            for v in goi.video:
                dich = noi[v["goc"]]
                bao(f"Giải nén video: {v.get('ten')} ({v.get('file')} file)...")
                try:
                    so = _giai_nen(z, f"video/{v['so']}/", dich)
                    ban_do[v["goc"]] = dich
                    bc["video"].append((v["goc"], dich, so))
                except Exception as exc:          # noqa: BLE001 — bao tung thu muc
                    bc["loi"].append(f"video {v.get('ten')}: {exc}")
    viec_pf = []
    for p in NEN_TANG:
        nt = nen_tang.get(p)
        if nt is None or not goi.acc.get(p) or not kh.get("co_acc", True):
            continue
        bao(f"Gộp acc {TEN_NEN_TANG[p]}...")
        for acc in _gop_acc(goi, p, nt, bc):
            if kh.get("co_profile", True) and acc.folder in goi.profile.get(p, set()):
                viec_pf.append((p, nt, acc))
    khoa_zip = threading.Lock()

    def mot(viec):
        p, nt, acc = viec
        try:
            if nt.profiles.is_running(acc):
                raise RuntimeError("trình duyệt acc đang mở — tắt rồi nhập lại")
            bao(f"Đặt profile {TEN_NEN_TANG[p]} {acc.id}...")
            _dat_profile(goi, p, nt, acc, khoa_zip)
            return (p, acc.id, None)
        except Exception as exc:          # noqa: BLE001 — bao tung acc, khong dung ca goi
            return (p, acc.id, str(exc))

    with ThreadPoolExecutor(max_workers=max(1, min(8, int(so_luong or 1)))) as ex:
        for p, ma, loi in ex.map(mot, viec_pf):
            if loi:
                bc["profile_loi"].append((f"{TEN_NEN_TANG[p]} {ma}", loi))
            else:
                bc["profile_ok"].append(f"{TEN_NEN_TANG[p]} {ma}")
    for p in NEN_TANG:
        nt = nen_tang.get(p)
        if nt is None:
            continue
        try:
            nt.store.save()               # create() co the da doi acc -> luu ban cuoi
        except Exception:
            pass
        bao(f"Gộp trang auto đăng {TEN_NEN_TANG[p]}...")
        try:
            _gop_trang(goi, p, nt, kh, ban_do, bc)
        except Exception as exc:          # noqa: BLE001
            bc["loi"].append(f"{TEN_NEN_TANG[p]}: {exc}")
        for b in kh["trang_bo_qua"].get(p) or []:
            bc["trang_bo_qua"].append((TEN_NEN_TANG[p], b["ten"], b["ly_do"]))
    return bc
