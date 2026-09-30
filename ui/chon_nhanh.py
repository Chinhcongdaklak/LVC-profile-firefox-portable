"""Ô chọn MỘT mục trong danh sách DÀI — thay ``CTkOptionMenu`` khi danh sách quá nhiều dòng.

``CTkOptionMenu`` dựng menu của tkinter: 150 quốc gia thì menu dài quá màn hình, chỉ có hai mũi
tên tí xíu ở đầu/cuối, LĂN CHUỘT KHÔNG ĂN. Widget này thay bằng một bảng chọn thả xuống: ô tìm
nhanh + danh sách ``tk.Listbox`` (lăn chuột được) + thanh cuộn; bấm một dòng là chọn xong.

Giữ nguyên chữ ký của ``CTkOptionMenu`` (``variable`` / ``values`` / ``command`` / ``configure`` /
``get`` / ``set``) để thay tại chỗ, không phải sửa chỗ gọi.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk


class ChonNhanhCombo(ctk.CTkFrame):
    """Ô chọn nhanh: bấm -> bảng chọn có ô tìm + danh sách lăn chuột được.

    Phím: gõ chữ để lọc, ↑ ↓ di chuyển, Enter chọn, Esc đóng. Chuột: lăn để cuộn, bấm để chọn.
    """

    CAO_TOI_DA = 320          # chiều cao tối đa của bảng chọn (px)
    CAO_DONG = 20             # chiều cao một dòng, dùng để đoán chiều cao bảng
    SO_DONG_HIEN = 14         # số dòng hiện tối đa trước khi phải cuộn

    def __init__(self, master, *, variable=None, values=None, command=None,
                 width: int = 200, placeholder: str = "Gõ để tìm nhanh..."):
        super().__init__(master, fg_color="transparent", width=width, height=28)
        self._values = [str(v) for v in (values or [])]
        self._command = command
        self._placeholder = placeholder
        self._var = variable if variable is not None else tk.StringVar(master=self)
        self._state = "normal"
        self._pop = None
        self._list = None
        self._tim = None
        self._nut = ctk.CTkButton(self, textvariable=self._var, anchor="w", command=self.mo,
                                  fg_color=("gray75", "gray25"), hover_color=("gray70", "gray30"),
                                  text_color=("gray10", "gray90"))
        self._nut.pack(side="left", fill="x", expand=True)
        self._mui = ctk.CTkButton(self, text="▾", width=28, command=self.mo,
                                  fg_color=("#3a7ebf", "#1f538d"))
        self._mui.pack(side="left", padx=(2, 0))
        self.bind("<Destroy>", lambda _e: self.dong(), add="+")

    # ------------------------------------------------------- như CTkOptionMenu
    def get(self) -> str:
        return self._var.get()

    def set(self, value: str) -> None:
        self._var.set(str(value))

    def configure(self, **kwargs):
        if "values" in kwargs:
            self._values = [str(v) for v in (kwargs.pop("values") or [])]
            if self._pop is not None:
                self._loc()
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            for w in (self._nut, self._mui):
                w.configure(state=self._state)
            if self._state == "disabled":
                self.dong()
        if "variable" in kwargs:
            self._var = kwargs.pop("variable")
            self._nut.configure(textvariable=self._var)
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if kwargs:
            super().configure(**kwargs)
        return None

    def cget(self, key):
        if key == "values":
            return list(self._values)
        if key == "state":
            return self._state
        return super().cget(key)

    # ------------------------------------------------------------ bảng chọn
    def mo(self) -> None:
        """Mở bảng chọn (bấm lần nữa thì đóng)."""
        if self._state == "disabled" or not self._values:
            return
        if self._pop is not None:
            self.dong()
            return
        toi = ctk.get_appearance_mode() == "Dark"
        nen, chu = ("#2b2b2b", "#dce4ee") if toi else ("#ffffff", "#101010")

        self._pop = pop = tk.Toplevel(self)
        pop.withdraw()
        pop.overrideredirect(True)        # không khung cửa sổ: dán ngay dưới ô như menu thả xuống
        pop.configure(bg=nen, highlightthickness=1, highlightbackground="#1f6aa5")

        self._tim = ctk.CTkEntry(pop, placeholder_text=self._placeholder, height=28)
        self._tim.pack(fill="x", padx=4, pady=(4, 2))
        khung = tk.Frame(pop, bg=nen)
        khung.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self._list = lb = tk.Listbox(khung, activestyle="none", exportselection=False,
                                     highlightthickness=0, bd=0, bg=nen, fg=chu,
                                     selectbackground="#1f6aa5", selectforeground="#ffffff")
        sb = ttk.Scrollbar(khung, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._loc()
        # Listbox trên Windows tự lăn được, nhưng ô tìm và viền thì chưa -> bắt trên CẢ bảng
        # để con trỏ ở đâu trong bảng cũng cuộn được.
        for w in (pop, self._tim, khung, lb):
            w.bind("<MouseWheel>", self._lan_chuot, add="+")
        lb.bind("<ButtonRelease-1>", lambda _e: self.chon_dong())
        lb.bind("<Return>", lambda _e: self.chon_dong())
        lb.bind("<Double-Button-1>", lambda _e: self.chon_dong())
        self._tim.bind("<KeyRelease>", self._phim_o_tim)
        self._tim.bind("<Return>", lambda _e: self.chon_dong())
        for w in (pop, self._tim, lb):
            w.bind("<Escape>", lambda _e: self.dong(), add="+")
        pop.bind("<FocusOut>", lambda _e: pop.after(120, self._dong_neu_ra_ngoai), add="+")

        self._dat_cho(pop)
        pop.deiconify()
        try:
            pop.grab_set()
        except tk.TclError:
            pass
        self._tim.focus_set()

    def _dat_cho(self, pop) -> None:
        """Đặt bảng ngay dưới ô; sát đáy màn hình thì lật lên trên."""
        self.update_idletasks()
        rong = max(self.winfo_width(), 220)
        so = max(1, min(len(self._values), self.SO_DONG_HIEN))
        cao = min(self.CAO_TOI_DA, 44 + so * self.CAO_DONG)
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 2
        if y + cao > self.winfo_screenheight():
            y = max(0, self.winfo_rooty() - cao - 2)
        pop.geometry(f"{rong}x{cao}+{x}+{y}")

    def _lan_chuot(self, event):
        if self._list is not None:
            self._list.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _dong_neu_ra_ngoai(self) -> None:
        """Bấm ra ngoài bảng -> đóng. Bấm vào ô tìm cũng sinh FocusOut nên phải kiểm."""
        if self._pop is None:
            return
        try:
            if self._pop.focus_displayof() is None:
                self.dong()
        except (tk.TclError, KeyError):
            self.dong()

    # ------------------------------------------------------------- lọc / chọn
    def loc_ten(self, tu_khoa: str) -> list:
        """Các mục khớp ``tu_khoa`` — khớp ĐẦU chuỗi lên trước (gõ "sing" ra Singapore trước)."""
        tu = (tu_khoa or "").strip().lower()
        if not tu:
            return list(self._values)
        dau = [v for v in self._values if v.lower().startswith(tu)]
        giua = [v for v in self._values if tu in v.lower() and v not in dau]
        return dau + giua

    def _loc(self) -> None:
        ds = self.loc_ten(self._tim.get() if self._tim is not None else "")
        self._list.delete(0, "end")
        for v in ds:
            self._list.insert("end", v)
        if ds:
            hien = self._var.get()
            i = ds.index(hien) if hien in ds else 0
            self._list.selection_clear(0, "end")
            self._list.selection_set(i)
            self._list.activate(i)
            self._list.see(i)

    def _phim_o_tim(self, event) -> None:
        if event.keysym in ("Up", "Down"):        # ↑↓ đi trong danh sách, không sửa chữ
            self._di_chuyen(-1 if event.keysym == "Up" else 1)
            return
        self._loc()

    def _di_chuyen(self, huong: int) -> None:
        if not self._list.size():
            return
        cur = self._list.curselection()
        i = max(0, min(self._list.size() - 1, (cur[0] if cur else 0) + huong))
        self._list.selection_clear(0, "end")
        self._list.selection_set(i)
        self._list.activate(i)
        self._list.see(i)

    def chon_dong(self) -> None:
        """Chọn dòng đang sáng: đóng bảng, đặt giá trị rồi gọi ``command``."""
        cur = self._list.curselection() if self._list is not None else ()
        if not cur:
            return
        gia_tri = self._list.get(cur[0])
        self.dong()
        self._var.set(gia_tri)
        if self._command is not None:
            self._command(gia_tri)

    def dong(self) -> None:
        pop, self._pop, self._list, self._tim = self._pop, None, None, None
        if pop is None:
            return
        try:
            pop.grab_release()
        except tk.TclError:
            pass
        try:
            pop.destroy()
        except tk.TclError:
            pass
        # Trả quyền bắt sự kiện cho hộp thoại cha (BaseDialog đã grab_set).
        try:
            cha = self.winfo_toplevel()
            if isinstance(cha, ctk.CTkToplevel):
                cha.grab_set()
        except tk.TclError:
            pass
