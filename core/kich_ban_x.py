"""KICH BAN TUONG TAC X — chuoi NODE chay lan luot tren moi acc (nguoi dung chot 15/10).

Node:
  "luot"   — luot newfeed: thoi gian luot x..y giay, dung moi bai, so bai tuong tac, so like /
             comment / xem video (moi so <= so bai tuong tac);
  "follow" — follow kenh, toi da ``toi_da`` kenh MOT LUOT: theo LIST KENH RIENG CUA ACC (follow
             xong -> XOA kenh khoi list cua acc do), theo TU KHOA RIENG CUA ACC (node chi co
             cong tac bat/tat; mo bai -> follow tac gia), trang goi y cua X;
  "quote"  — dang lai trich dan (nguon list kenh RIENG cua acc, hoac newfeed; chong trung);
  "nghi"   — nghi x..y giay giua hai node.
MAU = {ten: [node...]} luu data/kich_ban_x.json, cung kho voi cau hinh tab: mau gan cho tung acc,
list kenh follow / trich dan RIENG tung acc (KHONG con list chung), acc da chon, luong, lap lai.
Lan dau (chua co file) CHUYEN cau hinh hai tab cu (tuong_tac_x.json, dang_lai_x.json) vao mau
"Mặc định". Phan THUAN (chuan_node / chuan_mau / bo_kenh) test khong can giao dien.
"""

from __future__ import annotations

import copy
import json
import os
import threading

DUONG_DAN = os.path.join("data", "kich_ban_x.json")
CU_TUONG_TAC = os.path.join("data", "tuong_tac_x.json")
CU_TRICH_DAN = os.path.join("data", "dang_lai_x.json")

NODE_LUOT = "luot"
NODE_FOLLOW = "follow"
NODE_QUOTE = "quote"
NODE_NGHI = "nghi"
LOAI_NODE = (NODE_LUOT, NODE_FOLLOW, NODE_QUOTE, NODE_NGHI)
TEN_NODE = {NODE_LUOT: "📜 Lướt newfeed", NODE_FOLLOW: "➕ Follow kênh",
            NODE_QUOTE: "🔁 Đăng lại trích dẫn", NODE_NGHI: "⏸ Nghỉ"}
MAU_MAC_DINH = "Mặc định"

MAC_DINH = {
    NODE_LUOT: {"gio_min": 60, "gio_max": 180, "dung_min": 5, "dung_max": 10,
                "so_bai_tt": 8, "so_like": 5, "so_comment": 2, "so_video": 3},
    NODE_FOLLOW: {"toi_da": 5, "theo_list": True, "theo_tu_khoa": False,
                  "so_bai_tu_khoa": 2, "goi_y": False},
    NODE_QUOTE: {"nguon": "kenh", "so_bai": 3, "cach_min": 20, "cach_max": 60, "khong_trung": True},
    NODE_NGHI: {"giay_min": 30, "giay_max": 90},
}
#: Truong so nguyen cua tung node + (min, max) cho phep.
SO = {
    NODE_LUOT: {"gio_min": (10, 7200), "gio_max": (10, 7200), "dung_min": (1, 120),
                "dung_max": (1, 120), "so_bai_tt": (0, 500), "so_like": (0, 500),
                "so_comment": (0, 100), "so_video": (0, 500)},
    NODE_FOLLOW: {"toi_da": (0, 200), "so_bai_tu_khoa": (1, 50)},
    NODE_QUOTE: {"so_bai": (1, 100), "cach_min": (0, 3600), "cach_max": (0, 3600)},
    NODE_NGHI: {"giay_min": (0, 7200), "giay_max": (0, 7200)},
}
def _so(v, mac: int, lo: int, hi: int) -> int:
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        n = mac
    return max(lo, min(hi, n))


def node_moi(loai: str) -> dict:
    """Node moi voi gia tri mac dinh. THUAN."""
    n = {"loai": loai if loai in LOAI_NODE else NODE_LUOT, "bat": True}
    n.update(copy.deepcopy(MAC_DINH[n["loai"]]))
    return n


def chuan_node(node: dict) -> tuple:
    """Day du truong, ep kieu, kep gioi han. Tra (node_sach, [canh bao]). THUAN.

    Like / comment / xem video KHONG duoc vuot "so bai tuong tac"; khoang x..y dao nguoc -> doi cho."""
    canh: list = []
    loai = (node or {}).get("loai")
    if loai not in LOAI_NODE:
        loai = NODE_LUOT
    n = node_moi(loai)
    for k, v in (node or {}).items():
        if k in n or k == "loai":
            n[k] = v
    n["loai"] = loai
    n["bat"] = bool(n.get("bat", True))
    for k, (lo, hi) in SO[loai].items():
        n[k] = _so(n.get(k), MAC_DINH[loai][k], lo, hi)
    for a, b in ((("gio_min", "gio_max"), ("dung_min", "dung_max")) if loai == NODE_LUOT
                 else (("cach_min", "cach_max"),) if loai == NODE_QUOTE
                 else (("giay_min", "giay_max"),) if loai == NODE_NGHI else ()):
        if n[a] > n[b]:
            n[a], n[b] = n[b], n[a]
            canh.append(f"{a}/{b} bị ngược — đã đổi chỗ")
    if loai == NODE_LUOT:
        for k, ten in (("so_like", "like"), ("so_comment", "comment"), ("so_video", "xem video")):
            if n[k] > n["so_bai_tt"]:
                canh.append(f"Số {ten} ({n[k]}) > số bài tương tác ({n['so_bai_tt']}) — đã giảm")
                n[k] = n["so_bai_tt"]
    if loai == NODE_FOLLOW:
        for k in ("theo_list", "theo_tu_khoa", "goi_y"):
            n[k] = bool(n.get(k))
    if loai == NODE_QUOTE:
        n["nguon"] = "newfeed" if n.get("nguon") == "newfeed" else "kenh"
        n["khong_trung"] = bool(n.get("khong_trung", True))
    return n, canh


def chuan_mau(nodes) -> list:
    """List node sach (bo node hong). THUAN."""
    return [chuan_node(n)[0] for n in (nodes or []) if isinstance(n, dict)]


def mau_mac_dinh() -> list:
    return [node_moi(NODE_LUOT), node_moi(NODE_FOLLOW), node_moi(NODE_QUOTE)]


def tach_tu_khoa(text) -> list:
    """Van ban (dong / dau phay) -> list tu khoa, bo trong + bo trung (khong phan biet hoa). THUAN."""
    ra, da = [], set()
    for t in str(text or "").replace(",", "\n").splitlines():
        t = t.strip()
        if t and t.lower() not in da:
            da.add(t.lower())
            ra.append(t)
    return ra


def _tu_khoa_trong_mau(mau_raw) -> str:
    """Gom tu khoa con nam TRONG node follow cua mau (ban cu, truoc 15/10). THUAN."""
    ra: list = []
    for nodes in (mau_raw or {}).values():
        for n in nodes or []:
            if isinstance(n, dict) and n.get("loai") == NODE_FOLLOW:
                for t in tach_tu_khoa(n.get("tu_khoa")):
                    if t.lower() not in {x.lower() for x in ra}:
                        ra.append(t)
    return "\n".join(ra)


def bo_kenh(van_ban: str, handle: str) -> str:
    """Xoa MOI dong chi toi kenh ``handle`` (@ten / ten / x.com/ten) khoi list. THUAN."""
    from core import xwatch
    h = str(handle or "").lstrip("@").lower()
    giu = []
    for d in str(van_ban or "").splitlines():
        k = xwatch.chuan_kenh(d)
        if h and (k.get("handle") or "").lower() == h:
            continue
        giu.append(d)
    return "\n".join(giu).strip()


class KhoKichBan:
    """Kho cau hinh tab Kich ban X (an toan da luong: luong chay xoa kenh follow cua acc)."""

    def __init__(self, duong_dan: str = DUONG_DAN, *, cu_tuong_tac: str = CU_TUONG_TAC,
                 cu_trich_dan: str = CU_TRICH_DAN):
        self.duong_dan = duong_dan
        self._khoa = threading.RLock()
        self.mau: dict = {}
        self.acc_mau: dict = {}
        self.acc_follow: dict = {}
        self.acc_quote: dict = {}
        self.acc_tu_khoa: dict = {}         # acc -> tu khoa follow RIENG (van ban)
        self.accs: list = []
        self.luong = 1
        self.lap_phut = 0
        self.tu_dong = False       # bat tu dong chay (mo tool la tu chay kich ban)
        self.mau_mo = MAU_MAC_DINH
        if os.path.isfile(duong_dan):
            self._nap()
        else:
            self._chuyen_cu(cu_tuong_tac, cu_trich_dan)
        if not self.mau:
            self.mau = {MAU_MAC_DINH: mau_mac_dinh()}
        if self.mau_mo not in self.mau:
            self.mau_mo = next(iter(self.mau))

    # ---- nap / luu ----
    def _nap(self) -> None:
        try:
            with open(self.duong_dan, encoding="utf-8") as fh:
                d = json.load(fh) or {}
        except (OSError, ValueError):
            d = {}
        tu_mau = _tu_khoa_trong_mau(d.get("mau"))     # tu khoa cu nam TRONG node follow
        self.mau = {str(k): chuan_mau(v) for k, v in (d.get("mau") or {}).items()}
        self.acc_mau = {str(k): str(v) for k, v in (d.get("acc_mau") or {}).items()}
        self.acc_follow = {str(k): str(v) for k, v in (d.get("acc_follow") or {}).items() if str(v).strip()}
        self.acc_quote = {str(k): str(v) for k, v in (d.get("acc_quote") or {}).items() if str(v).strip()}
        self.acc_tu_khoa = {str(k): str(v) for k, v in (d.get("acc_tu_khoa") or {}).items() if str(v).strip()}
        self.accs = [str(x) for x in d.get("accs") or []]
        self._chia_list_chung(d.get("quote_chung"))
        self._chia_tu_khoa(tu_mau)
        self.luong = _so(d.get("luong"), 1, 1, 20)
        self.lap_phut = _so(d.get("lap_phut"), 0, 0, 100000)
        self.tu_dong = bool(d.get("tu_dong", False))
        self.mau_mo = str(d.get("mau_mo") or MAU_MAC_DINH)

    def _doc(self, path: str) -> dict:
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh) or {}
        except (OSError, ValueError):
            return {}

    def _chuyen_cu(self, cu_tt: str, cu_td: str) -> None:
        """Lan dau: dua cau hinh 2 tab cu (Luot tuong tac / Dang lai trich dan) vao mau Mac dinh."""
        tt, td = self._doc(cu_tt), self._doc(cu_td)
        if not tt and not td:
            return
        luot = node_moi(NODE_LUOT)
        luot.update(gio_min=tt.get("gioi_han_min", 60), gio_max=tt.get("gioi_han_max", 180),
                    dung_min=tt.get("dung_min", 5), dung_max=tt.get("dung_max", 10),
                    so_like=tt.get("so_like", 5), so_comment=tt.get("so_comment", 2),
                    so_video=tt.get("so_video", 3))
        luot["so_bai_tt"] = max(_so(luot["so_like"], 0, 0, 500), _so(luot["so_comment"], 0, 0, 100),
                                _so(luot["so_video"], 0, 0, 500), 8)
        fl = node_moi(NODE_FOLLOW)
        tu = tt.get("tu_khoa") or []
        fl.update(toi_da=tt.get("so_follow", 5) or 5, theo_tu_khoa=bool(tu and tt.get("so_bai_tim")),
                  so_bai_tu_khoa=tt.get("so_bai_tim") or 2, goi_y=bool(tt.get("so_follow")))
        qt = node_moi(NODE_QUOTE)
        qt.update(nguon=td.get("nguon", "kenh"), so_bai=td.get("so_bai", 3),
                  cach_min=td.get("cach_min", 20), cach_max=td.get("cach_max", 60),
                  khong_trung=td.get("khong_trung_acc", True))
        self.mau = {MAU_MAC_DINH: chuan_mau([luot, fl, qt])}
        self.acc_quote = {str(k): str(v) for k, v in (td.get("kenh_acc") or {}).items() if str(v).strip()}
        accs = [str(x) for x in (td.get("accs") or []) + (tt.get("acc_ids") or [])]
        self.accs = list(dict.fromkeys(accs))
        self._chia_list_chung(td.get("kenh"))
        self._chia_tu_khoa("\n".join(str(x) for x in tu))
        self.luong = _so(td.get("so_luong") or tt.get("so_luong"), 1, 1, 20)
        self.lap_phut = _so(td.get("lap_phut"), 0, 0, 100000)

    def _chia_list_chung(self, chung) -> None:
        """BO "list kenh CHUNG" (nguoi dung 15/10): moi acc chi dung list trich dan RIENG. List chung
        cu (neu co) duoc CHEP vao list rieng cua acc CHUA co list -> khong mat kenh nao."""
        chung = str(chung or "").strip()
        if not chung:
            return
        for a in self.accs:
            if not str(self.acc_quote.get(a) or "").strip():
                self.acc_quote[a] = chung

    def _chia_tu_khoa(self, tu) -> None:
        """Tu khoa follow gio la cua TUNG ACC (nguoi dung 15/10). Tu khoa cu (trong node follow cua mau
        / tab cu) duoc CHEP vao acc CHUA co tu khoa rieng -> khong mat."""
        tu = str(tu or "").strip()
        if not tu:
            return
        for a in self.accs:
            if not str(self.acc_tu_khoa.get(a) or "").strip():
                self.acc_tu_khoa[a] = tu

    def luu(self) -> None:
        with self._khoa:
            d = {"mau": self.mau, "acc_mau": self.acc_mau, "acc_follow": self.acc_follow,
                 "acc_quote": self.acc_quote, "acc_tu_khoa": self.acc_tu_khoa, "accs": self.accs,
                 "luong": self.luong, "lap_phut": self.lap_phut, "tu_dong": self.tu_dong,
                 "mau_mo": self.mau_mo}
            try:
                os.makedirs(os.path.dirname(self.duong_dan) or ".", exist_ok=True)
                tmp = f"{self.duong_dan}.{os.getpid()}.{threading.get_ident()}.tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(d, fh, ensure_ascii=False, indent=2)
                os.replace(tmp, self.duong_dan)
            except OSError:
                pass

    # ---- mau ----
    def mau_cua_acc(self, acc_id: str) -> tuple:
        """(ten mau, nodes) acc dung: mau GAN rieng (con ton tai) hoac mau dang mo."""
        with self._khoa:
            ten = self.acc_mau.get(str(acc_id))
            if ten not in self.mau:
                ten = self.mau_mo
            return ten, chuan_mau(self.mau.get(ten) or [])

    def doi_ten_mau(self, cu: str, moi: str) -> bool:
        with self._khoa:
            moi = str(moi or "").strip()
            if not moi or cu not in self.mau or (moi in self.mau and moi != cu):
                return False
            self.mau = {(moi if k == cu else k): v for k, v in self.mau.items()}
            self.acc_mau = {a: (moi if t == cu else t) for a, t in self.acc_mau.items()}
            if self.mau_mo == cu:
                self.mau_mo = moi
            return True

    def xoa_mau(self, ten: str) -> bool:
        with self._khoa:
            if ten not in self.mau or len(self.mau) <= 1:
                return False
            self.mau.pop(ten)
            self.acc_mau = {a: t for a, t in self.acc_mau.items() if t != ten}
            if self.mau_mo == ten:
                self.mau_mo = next(iter(self.mau))
            return True

    # ---- list kenh rieng acc ----
    def xoa_kenh_follow(self, acc_id: str, handle: str) -> None:
        """Follow xong (hoac da follow san) -> bo kenh khoi list follow cua acc + luu ngay."""
        with self._khoa:
            cu = self.acc_follow.get(str(acc_id), "")
            moi = bo_kenh(cu, handle)
            if moi == cu:
                return
            if moi:
                self.acc_follow[str(acc_id)] = moi
            else:
                self.acc_follow.pop(str(acc_id), None)
        self.luu()
