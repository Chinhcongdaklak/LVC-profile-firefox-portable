"""Trang thai NGHI cua acc tao fanpage (ADR-027): acc tao page loi -> DUNG 3 ngay roi tu chay lai.

Yeu cau nguoi dung (nguyen van 2026-09-15): "neu acc do tao page tren BM loi thi loai acc do ra khoi
list chay, bao nguoi dung acc loi tao fanpage dung sau 3 ngay roi tao lai cho an toan, con cac acc khac
van chay binh thuong, them nut reset trang thai ... nguoi dung co the reset trang thai dung chay de no
tro thanh trang thai cho de chay. hoac dem sau 3 ngay tu dong chay neu chay duoc tiep tuc chay, loi thi
sau 3 ngay chay lai".

Module nay KHONG biet tkinter. ``states`` la dict {acc_id: {"tt": "dung", "tu": epoch, "den": epoch,
"ly_do": str}} - luu trong data/create_page.json (khoa "acc_nghi"). Acc khong co trong dict = CHO (chay
duoc). Het han (den <= now) = tu dong CHO lai (khong can nguoi dung bam gi).
"""

from __future__ import annotations

import time
from typing import Iterable, Optional

#: So ngay nghi mac dinh sau khi tao page loi.
NGAY_NGHI = 3
TT_CHO = "cho"
TT_DUNG = "dung"            # loi tao page -> nghi NGAY_NGHI ngay
TT_CHO_DELAY = "cho_delay"  # tao XONG -> cho "Cach nhau" phut toi lan tiep (thanh cong hay loi deu qua delay)


def _now(now: Optional[float]) -> float:
    return time.time() if now is None else float(now)


def danh_dau_dung(states: dict, acc_id: str, ly_do: str = "", *, now: Optional[float] = None,
                  ngay: float = NGAY_NGHI) -> dict:
    """Danh dau acc DUNG ``ngay`` ngay ke tu ``now``. Tra ve ban ghi vua ghi."""
    t = _now(now)
    rec = {"tt": TT_DUNG, "tu": t, "den": t + float(ngay) * 86400.0, "ly_do": (ly_do or "").strip()}
    states[str(acc_id)] = rec
    return rec


def danh_dau_cho(states: dict, acc_id: str, phut: float, ly_do: str = "tạo xong", *,
                 now: Optional[float] = None) -> Optional[dict]:
    """Acc vua tao page XONG -> CHO ``phut`` phut toi lan tiep theo (phut <= 0 -> khong ghi)."""
    if float(phut) <= 0:
        return None
    t = _now(now)
    rec = {"tt": TT_CHO_DELAY, "tu": t, "den": t + float(phut) * 60.0, "ly_do": (ly_do or "").strip()}
    states[str(acc_id)] = rec
    return rec


def reset(states: dict, acc_ids: Optional[Iterable[str]] = None) -> int:
    """Xoa trang thai dung -> acc tro ve CHO. ``acc_ids`` None = reset het. Tra so acc doi."""
    if acc_ids is None:
        n = len(states)
        states.clear()
        return n
    n = 0
    for a in acc_ids:
        if states.pop(str(a), None) is not None:
            n += 1
    return n


def trang_thai(states: dict, acc_id: str, *, now: Optional[float] = None) -> str:
    """'dung' (loi, nghi 3 ngay) / 'cho_delay' (tao xong, cho toi lan tiep) khi con han; het han = 'cho'."""
    rec = states.get(str(acc_id))
    if not rec or rec.get("tt") not in (TT_DUNG, TT_CHO_DELAY):
        return TT_CHO
    try:
        den = float(rec.get("den") or 0)
    except (TypeError, ValueError):
        return TT_CHO
    return rec["tt"] if den > _now(now) else TT_CHO


def dang_dung(states: dict, acc_id: str, *, now: Optional[float] = None) -> bool:
    """Dang NGHI vi LOI (3 ngay)."""
    return trang_thai(states, acc_id, now=now) == TT_DUNG


def dang_nghi(states: dict, acc_id: str, *, now: Optional[float] = None) -> bool:
    """Khong chay duoc luc nay: dang dung (loi) HOAC dang cho delay (vua tao xong)."""
    return trang_thai(states, acc_id, now=now) != TT_CHO


def loc_chay(states: dict, acc_ids: Iterable[str], *, now: Optional[float] = None) -> tuple:
    """Chia danh sach acc thanh (chay_duoc, dang_dung) - giu thu tu."""
    chay, dung = [], []
    for a in acc_ids:
        (dung if dang_nghi(states, a, now=now) else chay).append(a)
    return chay, dung


def don_het_han(states: dict, *, now: Optional[float] = None) -> list:
    """Xoa ban ghi da het han (acc tu dong tro ve cho). Tra danh sach acc vua mo lai."""
    mo = [a for a in list(states) if not dang_nghi(states, a, now=now)]
    for a in mo:
        states.pop(a, None)
    return mo


def het_han_som_nhat(states: dict, acc_ids: Iterable[str], *, now: Optional[float] = None) -> Optional[float]:
    """Moc (epoch) acc dang nghi HET HAN SOM NHAT trong ``acc_ids``; khong acc nao nghi -> None.
    Dung de hen tu chay lai dung luc (BUG 2026-09-27: auto bat, moi acc dang dung -> khong bao gio chay lai)."""
    moc = None
    for a in acc_ids:
        if not dang_nghi(states, a, now=now):
            continue
        try:
            den = float(states[str(a)]["den"])
        except (KeyError, TypeError, ValueError):
            continue
        moc = den if moc is None else min(moc, den)
    return moc


def con_lai_giay(states: dict, acc_id: str, *, now: Optional[float] = None) -> float:
    rec = states.get(str(acc_id)) or {}
    try:
        return max(0.0, float(rec.get("den") or 0) - _now(now))
    except (TypeError, ValueError):
        return 0.0


def mo_ta(states: dict, acc_id: str, *, now: Optional[float] = None) -> str:
    """Chu ngan cho cot Trang thai: '⏸ dừng đến 18/09 13:05' (loi) / '⏳ chờ đến 15/09 14:30' (tao xong) / ''."""
    tt = trang_thai(states, acc_id, now=now)
    if tt == TT_CHO:
        return ""
    den = float(states[str(acc_id)]["den"])
    dau = "⏸ dừng đến " if tt == TT_DUNG else "⏳ chờ đến "
    return dau + time.strftime("%d/%m %H:%M", time.localtime(den))


def thong_bao_dung(acc_id: str, ly_do: str = "", ngay: float = NGAY_NGHI) -> str:
    """Cau bao nguoi dung khi acc bi dung (nhat ky)."""
    n = int(ngay) if float(ngay).is_integer() else ngay
    return (f"[{acc_id}] ⛔ acc LỖI tạo fanpage — DỪNG acc này {n} ngày rồi tạo lại cho an toàn"
            + (f" ({ly_do})" if ly_do else "") + ". Các acc khác vẫn chạy bình thường."
            " Muốn chạy lại sớm: chọn acc → 🔁 Reset trạng thái.")


def thong_bao_cho(acc_id: str, phut: float) -> str:
    return f"[{acc_id}] ✓ tạo xong — chờ {int(phut)} phút (Cách nhau) tới lần tạo tiếp theo."


def ket_qua_bm_loi(states: dict, acc_id: str, kq: dict, *, now: Optional[float] = None,
                   ngay: float = NGAY_NGHI) -> dict:
    """Tao page TU BM ma HONG -> danh dau acc dung + doi ma loi thanh 'khoa' de bo chay LOAI acc ngay
    (giu ten cho acc khac). Loi nhap lieu / da ok thi giu nguyen."""
    from core import page_batch
    if kq.get("ok") or kq.get("loi") != page_batch.LOI_HONG:
        return kq
    danh_dau_dung(states, acc_id, kq.get("ghi_chu") or "tạo hỏng", now=now, ngay=ngay)
    return page_batch.ket_qua(False, loi=page_batch.LOI_KHOA,
                              ghi_chu=f"acc lỗi tạo fanpage trên BM — dừng {int(ngay)} ngày: "
                                      + (kq.get("ghi_chu") or ""))
