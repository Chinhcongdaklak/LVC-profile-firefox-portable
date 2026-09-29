"""Bảng "Tạo giờ đăng bài" — sinh list giờ lệch dần để tránh trùng giờ đăng.

Nghiệp vụ ở core/schedule_gen.py; dialog chỉ nhập liệu + hiện bảng + copy/xuất.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core import autoup as autoup_module
from core import schedule_gen as sg

PAD = 8
KHONG_GUI = "— (không gửi)"


class ScheduleGenDialog(ctk.CTkToplevel):
    def __init__(self, parent, *, jobs_fn=None, nhan_loai: str = "tab", on_applied=None):
        """``jobs_fn`` (tuy chon): tra ve danh sach tab (job) cung loai de GUI list gio
        vao. Co jobs_fn -> hien them cot chon tab moi dong + nut "Gửi vào các tab".
        ``on_applied`` goi sau khi gui xong (lam moi panel). ``nhan_loai`` = 'fanpage'/'nhóm'.
        """
        super().__init__(parent)
        self.rows: list = []
        self.jobs_fn = jobs_fn
        self.nhan_loai = nhan_loai
        self.on_applied = on_applied
        self.row_tab_vars: list = []        # moi dong: StringVar chon tab dich
        self._tab_by_choice: dict = {}      # nhan hien thi -> job
        self._tab_choices: list = [KHONG_GUI]
        self.title("Tạo giờ đăng bài (lệch giờ tránh trùng)")
        self.geometry("620x660")
        self.transient(parent)
        self.after(150, lambda: (self.lift(), self._grab()))
        self._build()

    def _grab(self):
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _build(self):
        dam = ctk.CTkFont(weight="bold")
        ctk.CTkLabel(self, text="List mốc giờ gốc (mỗi mốc cách nhau dấu phẩy / xuống dòng):",
                     font=dam).pack(anchor="w", padx=PAD, pady=(PAD, 2))
        self.times_box = ctk.CTkTextbox(self, height=70)
        self.times_box.pack(fill="x", padx=PAD)
        self.times_box.insert("1.0", "7:00, 10:00, 19:00")

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=PAD, pady=6)
        ctk.CTkLabel(row, text="Số phút lệch:", font=dam).pack(side="left")
        self.offset_entry = ctk.CTkEntry(row, width=60)
        self.offset_entry.insert(0, "3")
        self.offset_entry.pack(side="left", padx=(4, 16))
        ctk.CTkLabel(row, text="Số dòng cần tạo:", font=dam).pack(side="left")
        self.count_entry = ctk.CTkEntry(row, width=60)
        self.count_entry.insert(0, "10")
        self.count_entry.pack(side="left", padx=4)
        ctk.CTkButton(row, text="🕒 Tạo", width=90, fg_color="#2f7d4f",
                      command=self._tao).pack(side="left", padx=(16, 0))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=PAD, pady=(0, 4))
        self.count_lbl = ctk.CTkLabel(bar, text="", text_color="gray60")
        self.count_lbl.pack(side="left")
        ctk.CTkButton(bar, text="📋 Copy hết", width=110, command=self._copy_het).pack(side="right", padx=3)
        ctk.CTkButton(bar, text="📤 Xuất TXT", width=110, fg_color="gray45",
                      command=lambda: self._xuat_txt()).pack(side="right", padx=3)

        # Hang GUI vao tab: chi hien khi mo tu tab Auto dang (co jobs_fn).
        if self.jobs_fn is not None:
            gui = ctk.CTkFrame(self, fg_color="transparent")
            gui.pack(fill="x", padx=PAD, pady=(0, 4))
            ctk.CTkLabel(gui, text=f"Gửi list giờ vào các {self.nhan_loai}:",
                         font=dam).pack(side="left")
            ctk.CTkButton(gui, text="↕ Gán theo thứ tự", width=150, fg_color="gray45",
                          command=self._gan_theo_thu_tu).pack(side="left", padx=(8, 3))
            ctk.CTkButton(gui, text="📨 Gửi vào các tab", width=150, fg_color="#2f7d4f",
                          command=self._gui_vao_tab).pack(side="left", padx=3)
            ctk.CTkLabel(gui, text="(mỗi dòng giờ → 1 tab; đổi tab ở cột phải mỗi dòng)",
                         text_color="gray60").pack(side="left", padx=6)

        self.table = ctk.CTkScrollableFrame(self, label_text="Danh sách giờ đăng")
        self.table.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))

    # ------------------------------------------------------------------ tạo
    def _tao(self):
        try:
            offset = int(self.offset_entry.get().strip() or 0)
            so_dong = int(self.count_entry.get().strip() or 0)
        except ValueError:
            messagebox.showwarning("Tạo giờ", "Số phút lệch và số dòng phải là số.", parent=self)
            return
        try:
            self.rows = sg.sinh_gio_lech(self.times_box.get("1.0", "end"), offset, so_dong)
        except sg.ScheduleError as e:
            messagebox.showwarning("Tạo giờ", str(e), parent=self)
            return
        self._render()

    def _cap_nhat_tab_choices(self):
        """Doc lai danh sach tab (job) hien co -> nhan hien thi + map nhan -> job."""
        jobs = list(self.jobs_fn() or []) if self.jobs_fn else []
        self._tab_choices = [KHONG_GUI] + [f"{i + 1}. {j.name}" for i, j in enumerate(jobs)]
        self._tab_by_choice = {f"{i + 1}. {j.name}": j for i, j in enumerate(jobs)}
        return jobs

    def _render(self):
        for w in self.table.winfo_children():
            w.destroy()
        jobs = self._cap_nhat_tab_choices() if self.jobs_fn else []
        self.row_tab_vars = []
        for i, r in enumerate(self.rows, 1):
            line = ctk.CTkFrame(self.table, fg_color="transparent")
            line.pack(fill="x", pady=1)
            ctk.CTkLabel(line, text=f"{i:>3}.", width=34, text_color="gray60").pack(side="left")
            ctk.CTkLabel(line, text=sg.dong_thanh_chuoi(r), anchor="w").pack(
                side="left", fill="x", expand=True)
            if self.jobs_fn is not None:
                # Mac dinh theo THU TU: dong k -> tab k (neu con tab); het tab -> khong gui.
                mac_dinh = self._tab_choices[i] if i < len(self._tab_choices) else KHONG_GUI
                var = tk.StringVar(value=mac_dinh)
                self.row_tab_vars.append(var)
                ctk.CTkOptionMenu(line, values=self._tab_choices, variable=var,
                                  width=150).pack(side="right", padx=(0, 6))
            ctk.CTkButton(line, text="Copy", width=60, height=24, fg_color="gray45",
                          command=lambda k=i - 1: self._copy_dong(k)).pack(side="right")
        self.count_lbl.configure(text=f"{len(self.rows)} dòng")

    # ------------------------------------------------------------------ gửi vào tab
    def _gan_theo_thu_tu(self):
        """Gán mỗi dòng vào tab theo THỨ TỰ: dòng 1 → tab 1, dòng 2 → tab 2..."""
        if not self.row_tab_vars:
            messagebox.showinfo("Gửi vào tab", "Chưa có dòng nào — bấm Tạo trước.", parent=self)
            return
        self._cap_nhat_tab_choices()
        for k, var in enumerate(self.row_tab_vars):
            var.set(self._tab_choices[k + 1] if k + 1 < len(self._tab_choices) else KHONG_GUI)
        self.count_lbl.configure(text="Đã gán theo thứ tự — bấm 'Gửi vào các tab'.")

    def _gui_vao_tab(self):
        """Áp list giờ mỗi dòng vào tab đã chọn ở dòng đó (mode 'list'). Lưu + làm mới."""
        if not self.rows:
            messagebox.showinfo("Gửi vào tab", "Chưa có dòng nào — bấm Tạo trước.", parent=self)
            return
        self._cap_nhat_tab_choices()      # tab co the vua doi
        ap = []       # (ten_tab, so_gio)
        trung = {}    # job_id -> dong cuoi cung ap (canh bao neu 2 dong cung 1 tab)
        canh_bao_trung = False
        for idx, var in enumerate(self.row_tab_vars):
            chon = var.get()
            job = self._tab_by_choice.get(chon)
            if job is None:                # KHONG_GUI hoac tab da bi xoa
                continue
            if job.job_id in trung:
                canh_bao_trung = True
            trung[job.job_id] = idx
            gio = autoup_module.parse_times(sg.dong_thanh_chuoi(self.rows[idx]))
            job.config.times = gio
            job.config.schedule_mode = "list"
            try:
                job.save()
            except Exception:  # noqa: BLE001
                pass
            ap.append((job.name, len(gio)))
        if not ap:
            messagebox.showinfo(
                "Gửi vào tab",
                "Chưa chọn tab nào để gửi.\n\nMỗi dòng chọn tab ở cột phải, hoặc bấm "
                "'↕ Gán theo thứ tự' rồi 'Gửi vào các tab'.", parent=self)
            return
        if callable(self.on_applied):
            try:
                self.on_applied()
            except Exception:  # noqa: BLE001
                pass
        tom = "\n".join(f"- {ten}: {n} giờ" for ten, n in ap[:15])
        them = f"\n... (+{len(ap) - 15})" if len(ap) > 15 else ""
        canh = ("\n\n⚠ Có tab nhận từ 2 dòng — dòng sau ghi đè dòng trước."
                if canh_bao_trung else "")
        self.count_lbl.configure(text=f"Đã gửi vào {len(ap)} tab.")
        messagebox.showinfo("Gửi vào tab",
                            f"Đã gửi list giờ vào {len(ap)} {self.nhan_loai}:\n{tom}{them}{canh}",
                            parent=self)

    # ------------------------------------------------------------------ copy / xuất
    def _dat_clipboard(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except tk.TclError:
            pass

    def _copy_dong(self, idx: int):
        if 0 <= idx < len(self.rows):
            self._dat_clipboard(sg.dong_thanh_chuoi(self.rows[idx]))
            self.count_lbl.configure(text=f"Đã copy dòng {idx + 1}")

    def _copy_het(self):
        if not self.rows:
            return
        self._dat_clipboard(sg.bang_thanh_text(self.rows))
        self.count_lbl.configure(text=f"Đã copy {len(self.rows)} dòng")

    def _xuat_txt(self, path: str = ""):
        if not self.rows:
            messagebox.showinfo("Xuất TXT", "Chưa có dòng nào — bấm Tạo trước.", parent=self)
            return
        if not path:
            path = filedialog.asksaveasfilename(parent=self, defaultextension=".txt",
                                                filetypes=[("Text", "*.txt")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(sg.bang_thanh_text(self.rows) + "\n")
        self.count_lbl.configure(text=f"Đã xuất {len(self.rows)} dòng → {os.path.basename(path)}")
