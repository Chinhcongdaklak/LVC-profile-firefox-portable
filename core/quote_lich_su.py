"""LICH SU TRICH DAN X — chong dang trich dan TRUNG (nguoi dung 14/10).

Moi acc tu lap lai list kenh nguon -> vong sau gap lai DUNG cac bai moi nhat cua kenh ->
de trich dan lai bai cu. So nay nho ID bai (so sau /status/) da trich dan THEO TUNG ACC, luu
data/dang_lai_x_lich_su.json, ton tai qua cac lan mo tool.

Hai muc chong trung:
  * MOT acc khong trich dan lai bai no da trich dan (luon bat);
  * ``chung=True``: KHONG cho 2 acc trich dan CUNG MOT bai (nhin lich su moi acc + bai acc khac
    DANG GIU cho khi chay song song) — tranh nhieu acc cung trich dan mot bai trong nhu spam.
Giu cho (xin_bai) -> trich dan xong ghi_xong / hong tra_bai. An toan da luong.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time

DUONG_DAN = os.path.join("data", "dang_lai_x_lich_su.json")
#: Moi acc giu toi da bao nhieu bai gan nhat (cu hon thi bo — kenh nguon khong ke bai qua cu).
TOI_DA_MOI_ACC = 3000


def id_bai(url_hoac_id) -> str:
    """'https://x.com/a/status/123' | '123' -> '123'; khong co -> ''. THUAN."""
    s = str(url_hoac_id or "").strip()
    m = re.search(r"/status(?:es)?/(\d{5,})", s)
    if m:
        return m.group(1)
    return s if re.fullmatch(r"\d{5,}", s) else ""


class LichSuQuote:
    def __init__(self, duong_dan: str = DUONG_DAN, *, chung: bool = True, now=time.time):
        self.duong_dan = duong_dan
        self.chung = bool(chung)
        self._now = now
        self._khoa = threading.Lock()
        self._giu: dict = {}            # id bai -> acc dang giu (chay song song)
        self._du: dict = self._nap()     # acc -> {id: {"t": epoch, "u": url}}

    def _nap(self) -> dict:
        try:
            with open(self.duong_dan, encoding="utf-8") as fh:
                d = json.load(fh)
            return {str(k): dict(v) for k, v in (d or {}).items() if isinstance(v, dict)}
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    def _luu(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.duong_dan) or ".", exist_ok=True)
            tmp = f"{self.duong_dan}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._du, fh, ensure_ascii=False)
            os.replace(tmp, self.duong_dan)
        except OSError:
            pass

    # ---- doc ----
    def da_quote(self, acc_id: str, bai) -> bool:
        b = id_bai(bai)
        with self._khoa:
            return bool(b) and b in self._du.get(str(acc_id), {})

    def bo_qua(self, acc_id: str, toi_da: int = 400) -> list:
        """ID bai acc nay KHONG duoc trich dan (da trich dan / acc khac da hoac dang trich dan
        khi chung=True). Moi nhat truoc, toi da ``toi_da`` (gui cho agent bo qua khi gom bai)."""
        with self._khoa:
            nguon = [self._du.get(str(acc_id), {})]
            if self.chung:
                nguon = list(self._du.values())
            ds = {}
            for d in nguon:
                for b, v in d.items():
                    t = float((v or {}).get("t") or 0)
                    if t > ds.get(b, -1):
                        ds[b] = t
            if self.chung:
                for b in self._giu:
                    ds[b] = float("inf")
            return [b for b, _t in sorted(ds.items(), key=lambda x: -x[1])][:max(0, toi_da)]

    def so_bai(self, acc_id: str) -> int:
        with self._khoa:
            return len(self._du.get(str(acc_id), {}))

    # ---- giu cho / ghi ----
    def xin_bai(self, acc_id: str, bai) -> tuple:
        """Giu bai cho acc. Tra (True, "") hoac (False, ly do)."""
        b = id_bai(bai)
        if not b:
            return False, "link bai khong hop le"
        acc_id = str(acc_id)
        with self._khoa:
            if b in self._du.get(acc_id, {}):
                return False, "acc nay DA trich dan bai nay roi"
            if self.chung:
                for a, d in self._du.items():
                    if a != acc_id and b in d:
                        return False, f"acc {a} da trich dan bai nay roi"
                g = self._giu.get(b)
                if g and g != acc_id:
                    return False, f"acc {g} dang trich dan bai nay"
            self._giu[b] = acc_id
            return True, ""

    def tra_bai(self, acc_id: str, bai) -> None:
        b = id_bai(bai)
        with self._khoa:
            if self._giu.get(b) == str(acc_id):
                self._giu.pop(b, None)

    def ghi_xong(self, acc_id: str, bai, url: str = "") -> None:
        b = id_bai(bai)
        if not b:
            return
        acc_id = str(acc_id)
        with self._khoa:
            d = self._du.setdefault(acc_id, {})
            d[b] = {"t": self._now(), "u": str(url or "")[:200]}
            if len(d) > TOI_DA_MOI_ACC:
                giu = sorted(d.items(), key=lambda x: -float((x[1] or {}).get("t") or 0))
                self._du[acc_id] = dict(giu[:TOI_DA_MOI_ACC])
            if self._giu.get(b) == acc_id:
                self._giu.pop(b, None)
            self._luu()

    def xoa_acc(self, acc_id: str) -> int:
        """Xoa lich su mot acc (nguoi dung muon cho trich dan lai). Tra so bai da xoa."""
        with self._khoa:
            n = len(self._du.pop(str(acc_id), {}) or {})
            self._luu()
            return n
