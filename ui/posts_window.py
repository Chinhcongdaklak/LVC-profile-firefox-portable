"""Hop thoai chon acc / link nhom / so bai de quet (ScanDialog).

Lan 4 (ADR-009): bang 'Bai viet da quet' (PostsTab) da go — tab '🔎 Quét bài'
(ui/ai_lab_tab.py) dung ScanDialog nay roi tu quet/gui sang Auto dang nhom.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk



PAD = 8


class ScanDialog(ctk.CTkToplevel):
    """Chon acc + link nhom + so bai de quet."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.result = None
        self.title("Quét nhóm mới")
        self.geometry("560x340")
        self.transient(parent)
        self.after(150, lambda: (self.lift(), self.grab_set()))

        # acc co profile (de lay cookie + proxy)
        self._accounts = [a for a in app.store if app.manager.is_installed(a)]
        labels = [f"{a.id}" for a in self._accounts] or ["(chưa có profile)"]

        frm = ctk.CTkFrame(self, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        frm.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frm, text="Dùng acc (cookie + proxy):").grid(row=0, column=0, sticky="w", pady=6)
        self.acc_box = ctk.CTkOptionMenu(frm, values=labels, width=260)
        self.acc_box.grid(row=0, column=1, sticky="ew", pady=6)

        ctk.CTkLabel(frm, text="Link nhóm:").grid(row=1, column=0, sticky="w", pady=6)
        self.url_entry = ctk.CTkEntry(frm, placeholder_text="https://www.facebook.com/groups/...")
        self.url_entry.grid(row=1, column=1, sticky="ew", pady=6)

        ctk.CTkLabel(frm, text="Số bài:").grid(row=2, column=0, sticky="w", pady=6)
        self.count_entry = ctk.CTkEntry(frm, width=100)
        self.count_entry.insert(0, "20")
        self.count_entry.grid(row=2, column=1, sticky="w", pady=6)

        self.download_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(frm, text="Tự tải ảnh + video về máy", variable=self.download_var).grid(
            row=3, column=1, sticky="w", pady=6)

        ctk.CTkLabel(frm, text="Thư mục lưu:").grid(row=4, column=0, sticky="w", pady=6)
        fold = ctk.CTkFrame(frm, fg_color="transparent")
        fold.grid(row=4, column=1, sticky="ew", pady=6)
        fold.grid_columnconfigure(0, weight=1)
        from core.posts import MEDIA_DIR
        default_dir = (app.settings.scan_save_dir or "").strip() or MEDIA_DIR
        self.dir_entry = ctk.CTkEntry(fold)
        self.dir_entry.insert(0, default_dir)
        self.dir_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(fold, text="Chọn...", width=70, command=self._pick_dir).grid(row=0, column=1, padx=(6, 0))

        ctk.CTkLabel(
            frm,
            text="Acc phải ĐÃ ĐĂNG NHẬP Facebook và là thành viên nhóm.\n"
                 "Tool mở nhóm trong trình duyệt (cookie + proxy của acc) rồi bóc bài.\n"
                 "Cuộn feed tới khi đủ Số bài hoặc hết bài trong nhóm (50 bài ≈ 1–2 phút).",
            text_color="gray60", justify="left",
        ).grid(row=5, column=1, sticky="w", pady=(8, 0))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(btns, text="Hủy", width=90, fg_color="gray35", command=self._cancel).pack(side="right")
        ctk.CTkButton(btns, text="Quét", width=90, command=self._ok).pack(side="right", padx=6)

    def _pick_dir(self):
        d = filedialog.askdirectory(parent=self, initialdir=self.dir_entry.get() or ".")
        if d:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, os.path.normpath(d))

    def _cancel(self):
        self.result = None
        self.destroy()

    def _ok(self):
        if not self._accounts:
            messagebox.showinfo("Quét nhóm", "Chưa có acc nào tạo profile.", parent=self)
            return
        acc = self._accounts[self.acc_box.cget("values").index(self.acc_box.get())] \
            if self.acc_box.get() in self.acc_box.cget("values") else self._accounts[0]
        url = self.url_entry.get().strip()
        if "/groups/" not in url:
            messagebox.showerror("Quét nhóm", "Link nhóm không hợp lệ.", parent=self)
            return
        try:
            count = max(1, min(200, int(self.count_entry.get().strip())))
        except ValueError:
            count = 20
        save_dir = self.dir_entry.get().strip()
        # nho thu muc cho lan sau
        try:
            self.app.settings.scan_save_dir = save_dir
            self.app.settings.save()
        except Exception:
            pass
        self.result = (acc, url, count, bool(self.download_var.get()), save_dir)
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result


class MultiScanDialog(ctk.CTkToplevel):
    """Quét NHIỀU acc cùng lúc: chọn nhiều acc + dán nhiều link nguồn (mỗi acc 1 link, theo thứ tự).

    ``show()`` trả ``{"pairs": [(account, url)...], "count", "download", "save_dir"}`` hoặc None.
    """

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.result = None
        self.title("Quét nhiều acc")
        self.geometry("720x560")
        self.minsize(600, 460)
        self.transient(parent)
        self.after(150, lambda: (self.lift(), self.grab_set()))
        self._accounts = [a for a in app.store if app.manager.is_installed(a)]
        self._by_id = {a.id: a for a in self._accounts}
        self._chosen: list = []

        frm = ctk.CTkFrame(self, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        dam = ctk.CTkFont(weight="bold")

        top = ctk.CTkFrame(frm, fg_color="transparent")
        top.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(top, text="Chọn nhiều acc rồi dán mỗi acc 1 link nguồn (theo THỨ TỰ hàng).",
                     anchor="w", text_color="gray60").pack(side="left")
        ctk.CTkButton(top, text="➕ Chọn acc", width=110, command=self._pick).pack(side="right")

        cols = ctk.CTkFrame(frm, fg_color="transparent")
        cols.pack(fill="both", expand=True)
        cols.grid_columnconfigure(0, weight=1, uniform="c")
        cols.grid_columnconfigure(1, weight=2, uniform="c")
        cols.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(cols, text="Acc (mỗi dòng 1 acc)", font=dam).grid(row=0, column=0, sticky="w", padx=4)
        ctk.CTkLabel(cols, text="Link nhóm nguồn (mỗi dòng 1 link, cùng hàng với acc)",
                     font=dam).grid(row=0, column=1, sticky="w", padx=4)
        self.acc_box = ctk.CTkTextbox(cols)
        self.acc_box.grid(row=1, column=0, sticky="nsew", padx=(0, 3))
        self.link_box = ctk.CTkTextbox(cols)
        self.link_box.grid(row=1, column=1, sticky="nsew", padx=(3, 0))
        self.acc_box.bind("<KeyRelease>", lambda _e: self._dem())
        self.link_box.bind("<KeyRelease>", lambda _e: self._dem())

        opt = ctk.CTkFrame(frm, fg_color="transparent")
        opt.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(opt, text="Số bài / acc:").pack(side="left", padx=(0, 4))
        self.count_entry = ctk.CTkEntry(opt, width=70)
        self.count_entry.insert(0, "20")
        self.count_entry.pack(side="left")
        self.download_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(opt, text="Tự tải ảnh + video", variable=self.download_var).pack(side="left", padx=(14, 8))
        self.pair_lbl = ctk.CTkLabel(opt, text="", text_color="gray60")
        self.pair_lbl.pack(side="right")

        fold = ctk.CTkFrame(frm, fg_color="transparent")
        fold.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(fold, text="Thư mục lưu:").pack(side="left", padx=(0, 4))
        from core.posts import MEDIA_DIR
        self.dir_entry = ctk.CTkEntry(fold)
        self.dir_entry.insert(0, (app.settings.scan_save_dir or "").strip() or MEDIA_DIR)
        self.dir_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(fold, text="Chọn...", width=70, command=self._pick_dir).pack(side="left", padx=(6, 0))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(btns, text="Hủy", width=90, fg_color="gray35", command=self._cancel).pack(side="right")
        ctk.CTkButton(btns, text="Quét tất cả", width=110, command=self._ok).pack(side="right", padx=6)
        self._dem()

    def _pick(self):
        from ui.dialogs import AccountPickerDialog
        hien = [ln.strip() for ln in self.acc_box.get("1.0", "end").splitlines() if ln.strip()]
        chon = AccountPickerDialog(self, [a for a in self._accounts], hien).show()
        if chon is None:
            return
        self.acc_box.delete("1.0", "end")
        self.acc_box.insert("1.0", "\n".join(chon))
        self._dem()

    def _cap(self) -> list:
        accs = [ln.strip() for ln in self.acc_box.get("1.0", "end").splitlines() if ln.strip()]
        links = [ln.strip() for ln in self.link_box.get("1.0", "end").splitlines() if ln.strip()]
        pairs = []
        for i, aid in enumerate(accs):
            a = self._by_id.get(aid)
            link = links[i] if i < len(links) else ""
            if a is not None and "/groups/" in link:
                pairs.append((a, link))
        return pairs

    def _dem(self):
        try:
            self.pair_lbl.configure(text=f"ghép được {len(self._cap())} cặp acc–link")
        except tk.TclError:
            pass

    def _pick_dir(self):
        d = filedialog.askdirectory(parent=self, initialdir=self.dir_entry.get() or ".")
        if d:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, os.path.normpath(d))

    def _ok(self):
        pairs = self._cap()
        if not pairs:
            messagebox.showinfo("Quét nhiều acc",
                                "Chưa ghép được acc với link nào (mỗi acc một link /groups/ cùng hàng).",
                                parent=self)
            return
        try:
            count = max(1, min(200, int(self.count_entry.get().strip())))
        except ValueError:
            count = 20
        save_dir = self.dir_entry.get().strip()
        try:
            self.app.settings.scan_save_dir = save_dir
            self.app.settings.save()
        except Exception:
            pass
        self.result = {"pairs": pairs, "count": count,
                       "download": bool(self.download_var.get()), "save_dir": save_dir}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result
