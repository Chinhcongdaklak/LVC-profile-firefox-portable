"""Bảng tổng hợp thống kê các tab Auto đăng fanpage/nhóm.

Cột: Tên tab · Video còn lại · Đăng thành công · Đăng lỗi · Trạng thái (đang chạy/đã dừng).
Dữ liệu lấy từ AutoUploader.thong_ke(); tự làm mới định kỳ khi mở.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

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
        self._job_theo_dong: dict = {}        # ma dong tren bang -> AutoUploader
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
        # Dem "Dang loi" chi de nhin; don so la viec cua NGUOI DUNG, tool khong tu xoa.
        ctk.CTkButton(bar, text="↺ Reset lỗi về 0", width=150, fg_color="#a33",
                      command=self.reset_loi).pack(side="left", padx=6)
        self.tong_lbl = ctk.CTkLabel(bar, text="", text_color="gray60")
        self.tong_lbl.pack(side="left", padx=12)

        wrap = ctk.CTkFrame(self); wrap.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in COLS], show="headings",
                                 selectmode="extended")
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
        chon = set(self.tree.selection()) if self.tree.get_children() else set()
        self.tree.delete(*self.tree.get_children())
        self._job_theo_dong = {}
        t_con = t_ok = t_loi = t_chay = 0
        for i, j in enumerate(jobs):
            try:
                d = j.thong_ke()
            except Exception:  # noqa: BLE001
                continue
            # Ma dong = SO THU TU + job_id: hai trang khac manager co the trung job_id.
            ma = f"{i}:{getattr(j, 'job_id', '')}"
            self._job_theo_dong[ma] = j
            self.tree.insert("", "end", iid=ma,
                             values=(d["ten"], d["con_lai"], d["thanh_cong"],
                                     d["loi"], d["trang_thai"]))
            t_con += d["con_lai"]; t_ok += d["thanh_cong"]; t_loi += d["loi"]
            t_chay += 1 if d["trang_thai"] == "Đang chạy" else 0
        self.tong_lbl.configure(
            text=f"{len(jobs)} tab · còn {t_con} · đăng {t_ok} · lỗi {t_loi} · đang chạy {t_chay}")
        # Lam moi 5 giay/lan -> phai giu lai nhung dong nguoi dung dang chon.
        con = [m for m in chon if m in self._job_theo_dong]
        if con:
            try:
                self.tree.selection_set(con)
            except tk.TclError:
                pass

    def reset_loi(self):
        """Dat so "Đăng lỗi" ve 0: cac tab DANG CHON, khong chon dong nao thi HOI de reset HET."""
        chon = [self._job_theo_dong[m] for m in self.tree.selection()
                if m in self._job_theo_dong]
        het = not chon
        if het:
            chon = list(self._job_theo_dong.values())
        if not chon:
            return
        co_loi = [j for j in chon if int(getattr(j, "fail_count", 0) or 0)]
        if not co_loi:
            messagebox.showinfo("Reset lỗi", "Các tab này đang không có lỗi nào.", parent=self)
            return
        tong = sum(int(j.fail_count or 0) for j in co_loi)
        hoi = (f"Đặt lại số “Đăng lỗi” về 0 cho TẤT CẢ {len(chon)} tab (đang có {tong} lỗi)?"
               if het else
               f"Đặt lại số “Đăng lỗi” về 0 cho {len(chon)} tab đang chọn (đang có {tong} lỗi)?")
        if not messagebox.askyesno("Reset lỗi", hoi + chr(10) * 2
                                   + "Chỉ xoá con số đếm, không đụng tới video hay trạng thái acc.",
                                   parent=self):
            return
        xong, hong = 0, []
        for j in co_loi:
            try:
                xong += j.reset_loi()
            except Exception as exc:  # noqa: BLE001
                hong.append(f"{getattr(j, 'name', '?')}: {type(exc).__name__}: {exc}")
        self.refresh()
        if hong:
            # TUYET DOI khong im lang: truoc day nuot loi nen nguoi dung bam ma khong
            # hieu vi sao so khong ve 0.
            them = ("" if "reset_loi" not in hong[0] else chr(10) * 2
                    + "Bản tool đang chạy cũ hơn file mã nguồn — hãy ĐÓNG rồi MỞ LẠI tool.")
            messagebox.showerror(
                "Reset lỗi",
                f"Không đặt lại được {len(hong)}/{len(co_loi)} tab:" + chr(10)
                + chr(10).join(hong[:5]) + them, parent=self)
            return
        messagebox.showinfo("Reset lỗi",
                            f"Đã đặt lại {xong} lỗi về 0 trên {len(co_loi)} tab.", parent=self)

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
