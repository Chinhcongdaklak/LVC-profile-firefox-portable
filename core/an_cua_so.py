"""AN TRINH DUYET — day cua so Firefox do tool mo ra khoi man hinh (nguoi dung chot 14/10).

Moi tab co CONG TAC rieng (Auto dang fanpage / Auto dang nhom / Auto dang X / Tuong tac),
MAC DINH TAT, luu theo lan chinh cuoi (Settings.an_trinh_duyet = {nhom: bool}).

Cach an: cua so GIU NGUYEN kich thuoc, doi sang TRAI, chi chua dai ~1 cm (mep PHAI cua so) o
canh trai man hinh chinh, nam o NUA DUOI man hinh. KHONG thu nho (thu nho thi Firefox ham
toc do, agent hay treo). Tat cong tac -> tra cua so ve DUNG vi tri truoc khi an.

Cua so nao cua tab nao: noi mo trinh duyet (factory dang bai, tab Tuong tac) goi
``danh_dau(nhom, manager, account)``; vong 4 giay cua App goi ``AnCuaSo.quet``.
Mo profile TAY (ProfileManager.mo_tay) -> ``bo_danh_dau`` (khong an trinh duyet nguoi dung mo).
"""

from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional

NHOM_FANPAGE = "fanpage"
NHOM_NHOM = "nhom"
NHOM_X = "x"
NHOM_TUONG_TAC = "tuong_tac"
NHOM = (NHOM_FANPAGE, NHOM_NHOM, NHOM_X, NHOM_TUONG_TAC)
MAC_DINH_BAT = False          # nguoi dung chot lai 14/10: mac dinh TAT an trinh duyet

#: So pixel chua lai = 1 cm theo DPI; 96 dpi -> 38px.
CM_INCH = 2.54
#: Cac cua so an chong LECH nhau theo chieu doc de dai 1 cm van dem duoc bao nhieu cai.
LECH_DOC = 26
LECH_TOI_DA = 12
#: Danh dau ma chua thay cua so sau bao lau thi bo (tac vu hong truoc khi mo trinh duyet).
CHO_CUA_SO_GIAY = 6 * 60


# ---- phan THUAN (test khong can Windows) ------------------------------------------------
def px_mot_cm(dpi: int) -> int:
    """So pixel cua 1 cm o ``dpi``. DPI sai -> 96. THUAN."""
    try:
        dpi = int(dpi)
    except (TypeError, ValueError):
        dpi = 96
    if dpi <= 0:
        dpi = 96
    return max(1, int(round(dpi / CM_INCH)))


def vi_tri_an(thu_tu: int, rong: int, vung: tuple, px_cm: int, vien: int = 0) -> tuple:
    """(x, y) cua cua so an thu ``thu_tu``. THUAN.

    ``vung`` = (trai, tren, rong, cao) vung lam viec man hinh chinh. Mep PHAI cua so nam o
    trai + px_cm (chi chua px_cm o man hinh); mep TREN o giua chieu cao + lech theo thu tu.
    ``vien`` = vien trong suot ben phai (khong nhin thay) -> cong them de phan LO RA du 1 cm."""
    trai, tren, _vr, vc = vung
    x = int(trai + px_cm + max(0, int(vien)) - max(1, int(rong)))
    y = int(tren + vc // 2 + (max(0, int(thu_tu)) % LECH_TOI_DA) * LECH_DOC)
    return x, y


def la_vi_tri_an(x: int, rong: int, vung: tuple, px_cm: int) -> bool:
    """Cua so o ``x`` rong ``rong`` co phai dang NAM O CHO AN (chi lo <= ~2 cm ben trai man
    hinh) khong. THUAN — dung de: khong dich lai cua so da mo san o cho an; va khi cong tac
    TAT / nguoi dung tu mo profile thi XOA vi tri an Firefox con nho."""
    try:
        return int(x) + int(rong) <= int(vung[0]) + 2 * max(1, int(px_cm)) + 40
    except (TypeError, ValueError, IndexError):
        return False


def vi_tri_tra_ve(rong: int, cao: int, vung: tuple) -> tuple:
    """Cho dat cua so khi TRA VE ma khong biet vi tri cu: goc trai tren vung lam viec. THUAN."""
    trai, tren, vr, vc = vung
    rong = max(400, min(int(rong or 1200), int(vr)))
    cao = max(300, min(int(cao or 800), int(vc)))
    return (int(trai) + 40, int(tren) + 40, rong, cao)


def dang_bat(cai_dat: Optional[dict], nhom: str) -> bool:
    """Cong tac cua ``nhom``: chua chinh lan nao -> MAC DINH TAT. THUAN."""
    if isinstance(cai_dat, dict) and nhom in cai_dat:
        return bool(cai_dat[nhom])
    return MAC_DINH_BAT


# ---- so danh dau: trinh duyet nao do tab nao mo ----------------------------------------
_khoa = threading.Lock()
_dau: dict = {}        # khoa thu muc -> {"nhom", "manager", "account", "luc", "thay"}


def _khoa_acc(manager, account) -> str:
    try:
        d = manager.app_dir(account)
    except Exception:  # noqa: BLE001
        d = ""
    return os.path.normcase(os.path.abspath(d)) if d else f"{id(manager)}:{getattr(account, 'id', '')}"


def danh_dau(nhom: str, manager, account) -> None:
    """Trinh duyet cua ``account`` sap mo la cua tab ``nhom``. Khong nem."""
    if manager is None or account is None or nhom not in NHOM:
        return
    with _khoa:
        _dau[_khoa_acc(manager, account)] = {"nhom": nhom, "manager": manager, "account": account,
                                            "luc": time.time(), "thay": False}


def bo_danh_dau(manager, account) -> None:
    with _khoa:
        _dau.pop(_khoa_acc(manager, account), None)


def ds_danh_dau() -> list:
    with _khoa:
        return [(k, dict(v)) for k, v in _dau.items()]


def _danh_dau_thay(khoa: str) -> None:
    with _khoa:
        if khoa in _dau:
            _dau[khoa]["thay"] = True


def _xoa(khoa: str) -> None:
    with _khoa:
        _dau.pop(khoa, None)


# ---- bo an / hien -----------------------------------------------------------------------
class AnCuaSo:
    """Nho vi tri CU cua tung cua so da an; quet() an/hien theo cong tac tung nhom.

    Cac ham Windows tiem duoc (tim/doc/dat vi tri/vung/dpi) -> thuoc chay may nao cung duoc.
    Moi cua so chi bi DAY RA MOT LAN: nguoi dung keo no vao lai thi tool khong keo ra nua."""

    def __init__(self, *, tim: Optional[Callable] = None, doc: Optional[Callable] = None,
                 dat: Optional[Callable] = None, vung: Optional[Callable] = None,
                 dpi: Optional[Callable] = None, song: Optional[Callable] = None,
                 vien: Optional[Callable] = None,
                 thu_nho: Optional[Callable] = None, hien_cho: Optional[Callable] = None,
                 now: Callable[[], float] = time.time):
        from core import cuaso
        self._tim = tim or cuaso.cua_so_cua_acc
        self._doc = doc or cuaso.vi_tri
        self._dat = dat or cuaso.dat_vi_tri
        self._vung = vung or cuaso.vung_lam_viec
        self._dpi = dpi or cuaso.dpi_he_thong
        self._song = song or cuaso.con_song
        self._vien = vien or cuaso.vien_phai_an
        self._thu_nho = thu_nho or cuaso.dang_thu_nho
        self._hien_cho = hien_cho or cuaso.hien_tai_cho
        self._now = now
        self._khoa = threading.RLock()   # vong 4 giay (luong giao dien) + luong canh nhanh
        self.da_an: dict = {}        # hwnd -> {"cu": (x, y, rong, cao), "nhom", "khoa"}

    def quet(self, cai_dat: Optional[dict]) -> dict:
        """Mot nhip: an cua so moi cua nhom dang BAT, tra cua so cua nhom da TAT.
        Tra {"an": [hwnd], "hien": [hwnd]}."""
        ra = {"an": [], "hien": []}
        for hwnd in list(self.da_an):                 # cua so da dong -> quen
            if not self._song(hwnd):
                self.da_an.pop(hwnd, None)
        for khoa, d in ds_danh_dau():
            try:
                hwnd = self._tim(d["manager"], d["account"])
            except Exception:  # noqa: BLE001
                hwnd = None
            if not hwnd:
                # Da tung thay cua so ma nay het -> trinh duyet da dong: bo danh dau (phien sau
                # nguoi dung tu mo profile thi KHONG bi an theo dau cu). Chua thay qua lau cung bo.
                if d["thay"] or self._now() - d["luc"] > CHO_CUA_SO_GIAY:
                    _xoa(khoa)
                continue
            _danh_dau_thay(khoa)
            bat = dang_bat(cai_dat, d["nhom"])
            if bat and hwnd not in self.da_an:
                if self.an_mot(hwnd, d, khoa):
                    ra["an"].append(hwnd)
            elif not bat and hwnd in self.da_an:
                if self._tra(hwnd):
                    ra["hien"].append(hwnd)
        # Cong tac TAT ma cua so khong con danh dau (vd danh dau bi ghi de) -> van tra ve.
        for hwnd, v in list(self.da_an.items()):
            if not dang_bat(cai_dat, v["nhom"]) and self._tra(hwnd):
                ra["hien"].append(hwnd)
        return ra

    def an_mot(self, hwnd, d: dict, khoa: str) -> bool:
        """Day MOT cua so sang ben (dung chung cho vong 4 giay va luong canh nhanh).

        Cua so da mo SAN o vi tri an (nho xulstore ghi truoc khi mo) -> khong dich them, chi
        ghi so; vi tri "cu" de tra ve lay tu ban xulstore truoc khi ghi (``d["cu_luu"]``)."""
        with self._khoa:
            if hwnd in self.da_an:
                return False
            vung = self._vung()
            pc = px_mot_cm(self._dpi())
            if self._thu_nho(hwnd):
                # Mo THU NHO (launch dung SW_SHOWMINNOACTIVE khi cong tac BAT) -> dat thang ra cho
                # an roi moi cho hien: KHONG bao gio hien o man hinh chinh, khong gianh ban phim.
                tra_ve = d.get("cu_luu") or vi_tri_tra_ve(1296, 860, vung)
                x, y = vi_tri_an(len(self.da_an), tra_ve[2], vung, pc, VIEN_UOC)
                if self._hien_cho(hwnd, x, y, tra_ve[2], tra_ve[3]):
                    self.da_an[hwnd] = {"cu": tuple(tra_ve), "nhom": d["nhom"], "khoa": khoa}
                    return True
                return False
            cu = self._doc(hwnd)
            if not cu:
                return False
            if la_vi_tri_an(cu[0], cu[2], vung, pc):
                tra_ve = d.get("cu_luu") or vi_tri_tra_ve(cu[2], cu[3], vung)
                self.da_an[hwnd] = {"cu": tuple(tra_ve), "nhom": d["nhom"], "khoa": khoa}
                return True
            x, y = vi_tri_an(len(self.da_an), cu[2], vung, pc, self._vien(hwnd))
            if self._dat(hwnd, x, y, cu[2], cu[3]):
                self.da_an[hwnd] = {"cu": tuple(cu), "nhom": d["nhom"], "khoa": khoa}
                return True
            return False

    def _tra(self, hwnd) -> bool:
        v = self.da_an.pop(hwnd, None)
        if not v:
            return False
        x, y, r, c = v["cu"]
        return bool(self._dat(hwnd, x, y, r, c))

    def hien_het(self) -> int:
        """Tra MOI cua so dang an ve cho cu (dong tool). Tra so cua so da tra."""
        n = 0
        for hwnd in list(self.da_an):
            if self._song(hwnd) and self._tra(hwnd):
                n += 1
            self.da_an.pop(hwnd, None)
        return n


# ---- MO LEN LA DA NAM SAN BEN CANH (nguoi dung chot 14/10) ------------------------------
# Truoc: cua so hien GIUA man hinh roi vong 4 giay moi day sang ben. Gio: ngay truoc khi Firefox
# khoi dong (ProfileManager.launch, luc Firefox DA DONG) ghi vi tri an vao xulstore.json cua
# profile -> Firefox mo THANG o cho an. Luong canh nhanh (0.1 giay/lan) la luoi an toan khi
# Firefox khong nghe vi tri do. Cong tac TAT / nguoi dung tu mo profile -> XOA vi tri an Firefox
# con nho, khong de trinh duyet ket ngoai man hinh.
XUL_URL = "chrome://browser/content/browser.xhtml"
CANH_NHANH_GIAY = 90          # luong canh: toi da ngan nay giay cho cua so hien ra
CANH_NHIP = 0.1
VIEN_UOC = 7                  # vien trong suot ben phai (Win10/11) khi chua co cua so de do

#: App gan vao: tra ``Settings.an_trinh_duyet`` hien tai. Chua gan -> coi nhu TAT het.
lay_cai_dat: Optional[Callable[[], Optional[dict]]] = None
_bo_chung = None
_khoa_bo = threading.Lock()


def bo_chung() -> "AnCuaSo":
    """MOT bo an dung chung cho vong 4 giay cua App va luong canh nhanh (so da_an chung)."""
    global _bo_chung
    with _khoa_bo:
        if _bo_chung is None:
            _bo_chung = AnCuaSo()
        return _bo_chung


def _cai_dat_hien() -> Optional[dict]:
    try:
        return lay_cai_dat() if lay_cai_dat else None
    except Exception:  # noqa: BLE001
        return None


def _xul_path(manager, account) -> str:
    try:
        return os.path.join(manager.profile_dir(account), "xulstore.json")
    except Exception:  # noqa: BLE001
        return ""


def doc_xul(path: str) -> dict:
    import json
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def ghi_xul(path: str, d: dict) -> bool:
    import json
    try:
        tam = path + ".lvc-tam"
        with open(tam, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False)
        os.replace(tam, path)
        return True
    except OSError:
        return False


def vi_tri_xul(d: dict) -> Optional[tuple]:
    """(x, y, rong, cao) cua cua so chinh Firefox nho trong xulstore, hoac None. THUAN."""
    mw = ((d or {}).get(XUL_URL) or {}).get("main-window") or {}
    try:
        return (int(mw["screenX"]), int(mw["screenY"]), int(mw.get("width") or 0),
                int(mw.get("height") or 0))
    except (KeyError, TypeError, ValueError):
        return None


def dat_xul_an(d: dict, x: int, y: int, rong: int, cao: int) -> dict:
    """Ghi vi tri AN vao cau truc xulstore (sizemode normal: phong to thi Firefox bo qua x/y). THUAN."""
    d = dict(d or {})
    trang = dict(d.get(XUL_URL) or {})
    mw = dict(trang.get("main-window") or {})
    mw.update({"screenX": str(int(x)), "screenY": str(int(y)), "width": str(int(rong)),
               "height": str(int(cao)), "sizemode": "normal"})
    trang["main-window"] = mw
    d[XUL_URL] = trang
    return d


def bo_xul_an(d: dict, vung: tuple, px_cm: int) -> tuple:
    """Vi tri Firefox nho la VI TRI AN -> doi ve cho nhin thay. Tra (d moi, da_doi). THUAN."""
    vt = vi_tri_xul(d)
    if not vt or not la_vi_tri_an(vt[0], vt[2] or 1200, vung, px_cm):
        return d, False
    x, y, r, c = vi_tri_tra_ve(vt[2], vt[3], vung)
    return dat_xul_an(d, x, y, r, c), True


def truoc_khi_mo(manager, account) -> str:
    """Goi TRONG ProfileManager.launch, ngay truoc khi chay firefox.exe (Firefox da dong).

    - Acc DANG DANH DAU (tab tu dong mo) + cong tac tab do BAT -> ghi vi tri an vao xulstore
      roi bat luong canh nhanh. Tra "an".
    - Con lai (cong tac TAT, nguoi dung tu mo profile...) ma Firefox con nho vi tri an -> xoa,
      tra "tra". Khong lam gi -> "". KHONG BAO GIO nem."""
    try:
        from core import cuaso
        path = _xul_path(manager, account)
        if not path:
            return ""
        khoa = _khoa_acc(manager, account)
        with _khoa:
            d_dau = dict(_dau.get(khoa) or {})
        vung = cuaso.vung_lam_viec()
        pc = px_mot_cm(cuaso.dpi_he_thong())
        xul = doc_xul(path)
        if d_dau and dang_bat(_cai_dat_hien(), d_dau.get("nhom", "")):
            cu = vi_tri_xul(xul)
            if cu and not la_vi_tri_an(cu[0], cu[2] or 1200, vung, pc):
                cu_luu = cu
            else:
                cu_luu = vi_tri_tra_ve(cu[2] if cu else 0, cu[3] if cu else 0, vung)
            rong = cu_luu[2] or 1200
            cao = cu_luu[3] or 800
            x, y = vi_tri_an(len(bo_chung().da_an), rong, vung, pc, VIEN_UOC)
            ghi_xul(path, dat_xul_an(xul, x, y, rong, cao))
            with _khoa:
                if khoa in _dau:
                    _dau[khoa]["cu_luu"] = tuple(cu_luu)
            _canh_nhanh(khoa)
            return "an"
        moi, doi = bo_xul_an(xul, vung, pc)
        if doi:
            ghi_xul(path, moi)
            return "tra"
    except Exception:  # noqa: BLE001
        pass
    return ""


def _canh_nhanh(khoa: str) -> None:
    """Luong canh: cua so vua hien ra (con o giua man hinh vi Firefox khong nghe xulstore)
    -> day sang ben NGAY, khong cho vong 4 giay."""
    def chay():
        het = time.time() + CANH_NHANH_GIAY
        bo = bo_chung()
        while time.time() < het:
            with _khoa:
                d = dict(_dau.get(khoa) or {})
            if not d or not dang_bat(_cai_dat_hien(), d.get("nhom", "")):
                return
            try:
                hwnd = bo._tim(d["manager"], d["account"])
            except Exception:  # noqa: BLE001
                hwnd = None
            if hwnd:
                _danh_dau_thay(khoa)
                bo.an_mot(hwnd, d, khoa)
                _giu_o_cho_an(bo, hwnd, khoa)
                return
            time.sleep(CANH_NHIP)
    threading.Thread(target=chay, name="an-trinh-duyet", daemon=True).start()


#: DO THAT 14/10: cua so hien 0.48s -> tool day sang ben 0.75s -> Firefox TU dat lai vi tri cua no
#: luc 1.17s (buoc khoi phuc cua so khi khoi dong). Giu o cho an them ngan nay giay; het han thi
#: thoi (nguoi dung tu keo cua so ra thi tool khong keo lai).
GIU_GIAY = 8.0
GIU_NHIP = 0.02           # nhip day ngan: Firefox keo ve thi chi lo ra ~vai chuc ms


def _giu_o_cho_an(bo: "AnCuaSo", hwnd, khoa: str) -> None:
    het = time.time() + GIU_GIAY
    while time.time() < het:
        time.sleep(GIU_NHIP)
        with _khoa:
            d = dict(_dau.get(khoa) or {})
        if not d or not dang_bat(_cai_dat_hien(), d.get("nhom", "")):
            return
        if not bo._song(hwnd) or hwnd not in bo.da_an:
            return
        try:
            vt = bo._doc(hwnd)
            vung = bo._vung()
            pc = px_mot_cm(bo._dpi())
            if vt and not bo._thu_nho(hwnd) and not la_vi_tri_an(vt[0], vt[2], vung, pc):
                x, y = vi_tri_an(0, vt[2], vung, pc, bo._vien(hwnd))
                bo._dat(hwnd, x, y, vt[2], vt[3])
        except Exception:  # noqa: BLE001
            return
