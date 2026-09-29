"""Hộp "Hẹn giờ tắt máy" — chọn tắt sau N phút hoặc lúc HH:MM, đặt/huỷ lịch.

Nghiệp vụ ở core/tat_may.py; dialog chỉ nhập liệu + xác nhận. Sau khi đặt/huỷ gọi
``on_changed(giay_hoac_None)`` để tool cập nhật nút ở thanh trạng thái.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core import tat_may

PAD = 10
CACH_PHUT = "Sau (phút)"
CACH_GIO = "Lúc giờ (HH:MM)"


class ShutdownDialog(ctk.CTkToplevel):
    def __init__(self, parent, *, dang_hen=None, on_changed=None):
        """``dang_hen`` = 'HH:MM' đang hẹn (hoặc None). ``on_changed(giay|None)`` gọi sau đặt/huỷ."""
        super().__init__(parent)
        self.on_changed = on_changed
        self.title("Hẹn giờ tắt máy")
        self.geometry("420x300")
        self.resizable(False, False)
        self.transient(parent)
        self.after(150, lambda: (self.lift(), self._grab()))
        self._build(dang_hen)

    def _grab(self):
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _build(self, dang_hen):
        dam = ctk.CTkFont(weight="bold")
        ctk.CTkLabel(self, text="⏻ Hẹn giờ tắt máy", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=PAD, pady=(PAD, 2))
        self.trang_thai = ctk.CTkLabel(
            self, text=(f"Đang hẹn tắt lúc {dang_hen}." if dang_hen else "Chưa hẹn lịch nào."),
            text_color=("#c44" if dang_hen else "gray60"))
        self.trang_thai.pack(anchor="w", padx=PAD, pady=(0, 6))

        self.cach = ctk.CTkSegmentedButton(self, values=[CACH_PHUT, CACH_GIO],
                                           command=lambda _=None: self._doi_cach())
        self.cach.set(CACH_GIO)
        self.cach.pack(fill="x", padx=PAD)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=PAD, pady=8)
        self.nhan_o = ctk.CTkLabel(row, text="Tắt lúc (HH:MM):", font=dam, width=130, anchor="w")
        self.nhan_o.pack(side="left")
        self.o_nhap = ctk.CTkEntry(row, width=120)
        self.o_nhap.insert(0, "23:00")
        self.o_nhap.pack(side="left", padx=4)
        self.o_nhap.bind("<KeyRelease>", lambda _e: self._xem_truoc())

        self.xem = ctk.CTkLabel(self, text="", text_color="gray60")
        self.xem.pack(anchor="w", padx=PAD)

        nut = ctk.CTkFrame(self, fg_color="transparent")
        nut.pack(fill="x", padx=PAD, pady=(14, PAD), side="bottom")
        ctk.CTkButton(nut, text="✅ Đặt lịch tắt máy", fg_color="#a33", hover_color="#c44",
                      font=dam, command=self._dat).pack(side="left", padx=(0, 6))
        ctk.CTkButton(nut, text="✖ Huỷ lịch", fg_color="gray45",
                      command=self._huy).pack(side="left")
        ctk.CTkButton(nut, text="Đóng", width=70, fg_color="gray30",
                      command=self.destroy).pack(side="right")
        self._xem_truoc()

    def _doi_cach(self):
        phut = self.cach.get() == CACH_PHUT
        self.nhan_o.configure(text="Sau (phút):" if phut else "Tắt lúc (HH:MM):")
        self.o_nhap.delete(0, "end")
        self.o_nhap.insert(0, "60" if phut else "23:00")
        self._xem_truoc()

    def _tinh_giay(self) -> int:
        v = self.o_nhap.get().strip()
        if self.cach.get() == CACH_PHUT:
            return tat_may.giay_sau_phut(v)
        return tat_may.giay_den_gio(v)

    def _xem_truoc(self):
        try:
            giay = self._tinh_giay()
        except tat_may.TatMayError as e:
            self.xem.configure(text=str(e), text_color="#c44")
            return
        phut = giay // 60
        self.xem.configure(
            text=f"→ Sẽ tắt lúc {tat_may.gio_tat(giay)} (còn {phut} phút {giay % 60} giây).",
            text_color="gray60")

    def _dat(self):
        try:
            giay = self._tinh_giay()
        except tat_may.TatMayError as e:
            messagebox.showwarning("Hẹn tắt máy", str(e), parent=self)
            return
        if giay <= 0:
            messagebox.showwarning("Hẹn tắt máy", "Giờ hẹn phải ở tương lai.", parent=self)
            return
        gio = tat_may.gio_tat(giay)
        if not messagebox.askyesno(
                "Hẹn tắt máy",
                f"Đặt lịch TẮT MÁY lúc {gio} (còn {giay // 60} phút nữa)?\n\n"
                "Máy sẽ tắt kể cả khi đã đóng tool và kể cả khi còn ứng dụng khác đang mở "
                "(ép đóng — hãy LƯU công việc trước).\n"
                "Có thể huỷ bằng nút 'Huỷ lịch'.", parent=self):
            return
        try:
            tat_may.dat_lich(giay)
        except tat_may.TatMayError as e:
            messagebox.showerror("Hẹn tắt máy", str(e), parent=self)
            return
        self.trang_thai.configure(text=f"Đang hẹn tắt lúc {gio}.", text_color="#c44")
        if callable(self.on_changed):
            self.on_changed(giay)
        messagebox.showinfo("Hẹn tắt máy", f"Đã hẹn tắt máy lúc {gio}.", parent=self)

    def _huy(self):
        try:
            tat_may.huy()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Hẹn tắt máy", str(e), parent=self)
            return
        self.trang_thai.configure(text="Đã huỷ lịch tắt máy.", text_color="gray60")
        if callable(self.on_changed):
            self.on_changed(None)
