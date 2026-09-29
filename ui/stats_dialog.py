"""Bảng tổng hợp thống kê các tab Auto đăng fanpage/nhóm.

Cột: Tên tab · Video còn lại · Đăng thành công · Đăng lỗi · Trạng thái (đang chạy/đã dừng).
Dữ liệu lấy từ AutoUploader.thong_ke(); tự làm mới định kỳ khi mở.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

PAD = 8
COLS = (("ten", "Tên tab", 220, "w"),
        ("con_lai", "Video còn lại", 110, "center"),
        ("thanh_cong", "Đăng thành công", 130, "center"),
        ("loi", "Đăng lỗi", 90, "center"),
        ("trang_thai", "Trạng thái", 120, "center"))


class StatsDialog(ctk.CTkToplevel):
    def __init__(self, parent, jobs_fn, tieu_de="Thống kê Auto đăng fanpage"):
        super().__init__(parent)
        # jobs_fn: gọi mỗi lần làm mới -> danh sách AutoUploader hiện tại.
        self._jobs_fn = jobs_fn
        self._auto = True
        self.title(tieu_de)
        self.geometry("760x460")
        self.transient(parent)
        self.after(150, lambda: self._grab())
        self._build()
        self.refresh()
        self._tick()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _grab(self):
        try: self.grab_set()
        except tk.TclError: pass

    def _build(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=PAD, pady=(PAD, 4))
        ctk.CTkButton(bar, text="🔄 Làm mới", width=110, command=self.refresh).pack(side="left")
        self.tong_lbl = ctk.CTkLabel(bar, text="", text_color="gray60")
        self.tong_lbl.pack(side="left", padx=12)

        wrap = ctk.CTkFrame(self); wrap.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in COLS], show="headings")
        for k, t, w, a in COLS:
            self.tree.heading(k, text=t); self.tree.column(k, width=w, anchor=a, stretch=(k == "ten"))
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); vsb.grid(row=0, column=1, sticky="ns")
        wrap.grid_rowconfigure(0, weight=1); wrap.grid_columnconfigure(0, weight=1)

    def refresh(self):
        try:
            jobs = list(self._jobs_fn() or [])
        except Exception:  # noqa: BLE001
            jobs = []
        self.tree.delete(*self.tree.get_children())
        t_con = t_ok = t_loi = t_chay = 0
        for j in jobs:
            try:
                d = j.thong_ke()
            except Exception:  # noqa: BLE001
                continue
            self.tree.insert("", "end", values=(d["ten"], d["con_lai"], d["thanh_cong"],
                                                d["loi"], d["trang_thai"]))
            t_con += d["con_lai"]; t_ok += d["thanh_cong"]; t_loi += d["loi"]
            t_chay += 1 if d["trang_thai"] == "Đang chạy" else 0
        self.tong_lbl.configure(
            text=f"{len(jobs)} tab · còn {t_con} · đăng {t_ok} · lỗi {t_loi} · đang chạy {t_chay}")

    def _tick(self):
        if not self._auto:
            return
        self.refresh()
        try:
            self.after(5000, self._tick)
        except tk.TclError:
            pass

    def _close(self):
        self._auto = False
        self.destroy()
