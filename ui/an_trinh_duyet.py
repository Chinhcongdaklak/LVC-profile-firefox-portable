"""Cong tac "🙈 Ẩn trình duyệt" — dat o tung tab (Auto dang fanpage / nhom / X, Tuong tac).

Bat: trinh duyet do tab do mo ra bi day sang trai man hinh, chi chua ~1 cm o nua duoi.
Mac dinh TAT; gat la luu ngay vao Settings.an_trinh_duyet (nho qua lan mo tool sau).
"""

from __future__ import annotations

import customtkinter as ctk

from core import an_cua_so

NHAN = "🙈 Ẩn trình duyệt"


class CongTacAn(ctk.CTkSwitch):
    def __init__(self, parent, app, nhom: str, **kw):
        self.app = app
        self.nhom = nhom
        self._var = ctk.BooleanVar(value=self.dang_bat())
        super().__init__(parent, text=NHAN, variable=self._var, command=self._gat, **kw)

    def _cai_dat(self) -> dict:
        st = getattr(self.app, "settings", None)
        d = getattr(st, "an_trinh_duyet", None)
        if st is not None and not isinstance(d, dict):
            d = {}
            st.an_trinh_duyet = d
        return d if isinstance(d, dict) else {}

    def dang_bat(self) -> bool:
        return an_cua_so.dang_bat(self._cai_dat(), self.nhom)

    def _gat(self) -> None:
        bat = bool(self._var.get())
        self._cai_dat()[self.nhom] = bat
        st = getattr(self.app, "settings", None)
        try:
            st.save()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.app.set_status("Ẩn trình duyệt: BẬT — trình duyệt của tab này sẽ bị dời sang trái, "
                                "chừa 1 cm" if bat else "Ẩn trình duyệt: TẮT — trả trình duyệt về chỗ cũ")
        except Exception:  # noqa: BLE001
            pass
        f = getattr(self.app, "_tu_an_cua_so", None)
        if callable(f):
            try:
                f()                       # ap NGAY, khong cho nhip 4 giay
            except Exception:  # noqa: BLE001
                pass
