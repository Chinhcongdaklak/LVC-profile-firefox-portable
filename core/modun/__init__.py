"""Registry MO-DUN (ADR-028): moi chuc nang cua tool la MOT mo-dun rieng le, tool goi theo ma.

    from core import modun
    modun.tat_ca.nap()                       # nap moi mo-dun (App lam 1 lan khi khoi dong)
    kq = modun.chay("dang_nhap_web", ngu_canh, accs)   # KetQua

Mot mo-dun = MOT file ``core/modun/<ma>.py`` tu goi ``dang_ky(Modun(...))`` khi import.
Mo-dun THUAN NGHIEP VU: nhan NguCanh (manager/store/settings/log/post/so_luong) + accs
+ tham_so, tra KetQua (ok/loi/ghi_chu/du_lieu). KHONG mo hop thoai, KHONG import
tkinter/customtkinter/ui (kc/kien_truc_modun.py chan). UI chi dich KetQua ra man hinh.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

#: Cac nhom hop le cua Modun.nhom (dung de sinh menu theo nhom).
NHOM = ("acc", "proxy", "fanpage", "dang_bai", "khac")


def _khong(_m: Any = None) -> None:
    """log/post mac dinh: khong lam gi -> mo-dun chay duoc khong can UI."""


@dataclass
class NguCanh:
    """Moi thu mo-dun can tu tool: quan ly profile, kho acc, cai dat, kenh bao tin."""
    manager: Any
    store: Any
    settings: Any = None
    log: Callable[[str], None] = _khong
    post: Callable[[Callable[[], None]], None] = _khong
    so_luong: int = 1
    #: Bo quan ly job dang bai (core.autoup.AutoUpManager) — chi mo-dun nhom dang_bai can.
    autoup: Any = None


@dataclass
class KetQua:
    """Ket qua chay mot mo-dun tren nhieu acc."""
    ok: list = field(default_factory=list)        # id acc thanh cong
    loi: list = field(default_factory=list)       # (id acc, ly do)
    ghi_chu: str = ""
    du_lieu: dict = field(default_factory=dict)

    @property
    def so_ok(self) -> int:
        return len(self.ok)

    @property
    def so_loi(self) -> int:
        return len(self.loi)

    def them_ok(self, acc_id: str) -> None:
        self.ok.append(str(acc_id))

    def them_loi(self, acc_id: str, ly_do: str) -> None:
        self.loi.append((str(acc_id), str(ly_do)))

    def tom_tat(self) -> str:
        tong = self.so_ok + self.so_loi
        s = f"xong {self.so_ok}/{tong} acc" if tong else "xong"
        if self.so_loi:
            s += f", lỗi {self.so_loi}"
        if self.ghi_chu:
            s += f" — {self.ghi_chu}"
        return s


@dataclass
class Modun:
    """Mot chuc nang cua tool. ``chay(ngu_canh, accs, tham_so) -> KetQua``."""
    ma: str
    ten: str
    nhom: str
    chay: Callable[[NguCanh, list, dict], KetQua]
    mo_ta: str = ""
    can_profile: bool = True


_REG: dict[str, Modun] = {}
_THU_TU: list[str] = []


def dang_ky(m: Modun) -> None:
    """Dang ky mo-dun. Nem ValueError neu thieu ma, trung ma, hoac nhom la."""
    ma = (m.ma or "").strip()
    if not ma:
        raise ValueError("mô-đun thiếu mã (ma)")
    if m.nhom not in NHOM:
        raise ValueError(f"mô-đun {ma}: nhóm lạ '{m.nhom}' (hợp lệ: {', '.join(NHOM)})")
    if ma in _REG:
        raise ValueError(f"mô-đun trùng mã: {ma}")
    if not callable(m.chay):
        raise ValueError(f"mô-đun {ma}: chay không gọi được")
    _REG[ma] = m
    _THU_TU.append(ma)


def lay(ma: str) -> Modun:
    try:
        return _REG[ma]
    except KeyError:
        raise KeyError(f"chưa đăng ký mô-đun: {ma}") from None


def co(ma: str) -> bool:
    return ma in _REG


def danh_sach(nhom: Optional[str] = None) -> list[Modun]:
    """Mo-dun theo thu tu dang ky; loc theo nhom neu co."""
    ds = [_REG[k] for k in _THU_TU]
    if nhom:
        ds = [m for m in ds if m.nhom == nhom]
    return ds


def chay(ma: str, ngu_canh: NguCanh, accs: list, **tham_so) -> KetQua:
    """Goi mo-dun theo ma. Loi tung acc nam trong KetQua.loi; loi he thong nem thang."""
    m = lay(ma)
    kq = m.chay(ngu_canh, list(accs or []), dict(tham_so))
    if not isinstance(kq, KetQua):
        raise TypeError(f"mô-đun {ma} phải trả KetQua, nhận {type(kq).__name__}")
    return kq


def xoa_het() -> None:
    """Chi cho thuoc: lam rong registry."""
    _REG.clear()
    _THU_TU.clear()


def ngu_canh_tu(app: Any, *, log: Optional[Callable[[str], None]] = None,
                post: Optional[Callable] = None, so_luong: Optional[int] = None) -> NguCanh:
    """Dung NguCanh tu doi tuong App (duck-typing: manager/store/settings/autoup/_post/set_status/_so_luong).

    Dung chung cho App.goi_modun va cac tab, khoi lap lai 6 lan. ``log`` mac dinh = app.set_status,
    ``post`` = app._post, ``so_luong`` = app._so_luong() (khong co thi 1). core KHONG import ui.
    """
    def lay(ten: str, mac_dinh: Any = None) -> Any:
        # object.__getattribute__: KHONG roi vao __getattr__ cua tkinter (bare App trong thuoc -> de quy).
        try:
            return object.__getattribute__(app, ten)
        except AttributeError:
            return mac_dinh

    if log is None:
        log = lay("set_status") or _khong
    if post is None:
        post = lay("_post") or _khong
    if so_luong is None:
        f = lay("_so_luong")
        try:
            so_luong = int(f()) if callable(f) else 1
        except Exception:  # noqa: BLE001
            so_luong = 1
    return NguCanh(manager=lay("manager"), store=lay("store"), settings=lay("settings"),
                   log=log, post=post, so_luong=max(1, int(so_luong)), autoup=lay("autoup"))
