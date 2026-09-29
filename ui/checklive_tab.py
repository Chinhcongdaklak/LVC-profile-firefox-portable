"""Tab "Check live UID" (lan 5): dan token / lay tu acc -> check hang loat UID qua HTTP -> bang live/die.

Giao dien chi lo bam nut + hien bang. Nghiep vu o ``core/checklive.py`` (HOP-DONG muc checklive,
ADR-010). KHONG mo trinh duyet de check (chi derive_token moi mo, khi o token bo trong).
"""

from __future__ import annotations

import os
import threading
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from core import checklive

PAD = 8
_TT = {"live": "🟢 Live", "die": "🔴 Die", "checkpoint": "🟠 Checkpoint",
       "token_loi": "⚠ Token lỗi", "loi": "⚠ Lỗi"}
COLS = (("uid", "UID", 200, "w"),
        ("status", "Trạng thái", 130, "center"),
        ("name", "Tên", 260, "w"),
        ("detail", "Ghi chú", 360, "w"))


class CheckLiveTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._dung = False
        self._rows: list = []
        self._build()

    # ------------------------------------------------------------------ dựng
    def _build(self):
        dam = ctk.CTkFont(weight="bold")
        r1 = ctk.CTkFrame(self); r1.pack(fill="x", padx=PAD, pady=(PAD, 4))
        ctk.CTkLabel(r1, text="Access token", font=dam, width=100, anchor="w").pack(side="left", padx=(10, 6), pady=8)
        self.token_entry = ctk.CTkEntry(r1, placeholder_text="Dán app token (APP_ID|APP_SECRET) hoặc access token — để trống thì tự lấy từ acc bên phải")
        self.token_entry.pack(side="left", fill="x", expand=True, pady=8)
        ctk.CTkLabel(r1, text="hoặc lấy từ acc:").pack(side="left", padx=(10, 4))
        self.acc_entry = ctk.CTkEntry(r1, width=150, placeholder_text="id acc đã đăng nhập")
        self.acc_entry.pack(side="left", padx=(0, 10), pady=8)

        r2 = ctk.CTkFrame(self); r2.pack(fill="both", expand=True, padx=PAD, pady=4)
        top = ctk.CTkFrame(r2, fg_color="transparent"); top.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(top, text="Danh sách UID (mỗi dòng 1 UID, nhận cả link facebook.com/<uid>)", font=dam).pack(side="left")
        ctk.CTkLabel(top, text="Số luồng").pack(side="left", padx=(16, 4))
        self.workers_entry = ctk.CTkEntry(top, width=54); self.workers_entry.insert(0, "10")
        self.workers_entry.pack(side="left")
        self.uids_box = ctk.CTkTextbox(r2, height=120)
        self.uids_box.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        r3 = ctk.CTkFrame(self, fg_color="transparent"); r3.pack(fill="x", padx=PAD, pady=(0, 4))
        self.check_btn = ctk.CTkButton(r3, text="✅ Check live", width=140, fg_color="#2f7d4f", command=self._check)
        self.check_btn.pack(side="left", padx=3)
        self.stop_btn = ctk.CTkButton(r3, text="⏹ Dừng", width=90, fg_color="#a33", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=3)
        self.count_lbl = ctk.CTkLabel(r3, text="", text_color="gray60"); self.count_lbl.pack(side="left", padx=12)
        ctk.CTkButton(r3, text="📤 Xuất TXT", width=110, fg_color="gray45", command=lambda: self._xuat_txt()).pack(side="right", padx=3)
        ctk.CTkButton(r3, text="🗑 Xoá", width=80, fg_color="gray45", command=self._xoa).pack(side="right", padx=3)

        r4 = ctk.CTkFrame(self); r4.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self.tree = ttk.Treeview(r4, columns=[c[0] for c in COLS], show="headings", selectmode="extended")
        for k, t, w, a in COLS:
            self.tree.heading(k, text=t); self.tree.column(k, width=w, anchor=a, stretch=(k == "detail"))
        vsb = ttk.Scrollbar(r4, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); vsb.grid(row=0, column=1, sticky="ns")
        r4.grid_rowconfigure(0, weight=1); r4.grid_columnconfigure(0, weight=1)

    def set_status(self, t):
        try:
            self.app.set_status(t)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ check
    def _stop(self):
        self._dung = True
        self.stop_btn.configure(state="disabled")
        self.set_status("Đang dừng...")

    def _check(self):
        uids = checklive.parse_uids(self.uids_box.get("1.0", "end"))
        if not uids:
            messagebox.showinfo("Check live", "Chưa nhập UID nào.", parent=self); return
        token = self.token_entry.get().strip()
        acc_id = self.acc_entry.get().strip()
        try:
            workers = max(1, min(30, int(self.workers_entry.get().strip() or 10)))
        except ValueError:
            workers = 10
        self._dung = False
        self._rows = []
        self.tree.delete(*self.tree.get_children())
        self.check_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.count_lbl.configure(text=f"0/{len(uids)}...")

        def ve(row):
            self.app._post(lambda r=row: self._them_dong(r, len(uids)))

        def work():
            tok = token
            if not tok:
                if not acc_id:
                    self.app._post(lambda: self._xong_loi("Chưa có token: dán token hoặc nhập id acc để tự lấy."))
                    return
                acc = self.app.store.get(acc_id)
                if acc is None:
                    self.app._post(lambda: self._xong_loi(f"Không thấy acc '{acc_id}'."))
                    return
                try:
                    self.app._post(lambda: self.set_status(f"Đang lấy token từ acc {acc_id}..."))
                    tok = checklive.derive_token(self.app.manager, acc,
                                                 log=lambda m: self.app._post(lambda t=m: self.set_status(t)))
                except Exception as exc:  # noqa: BLE001
                    self.app._post(lambda e=exc: self._xong_loi(str(e)))
                    return
            kq = checklive.check_batch(uids, tok, workers=workers, on_row=ve, dung=lambda: self._dung)
            self.app._post(lambda: self._xong(kq))

        threading.Thread(target=work, daemon=True).start()

    def _them_dong(self, row: dict, tong: int):
        self._rows.append(row)
        self.tree.insert("", "end", values=(row["uid"], _TT.get(row["status"], row["status"]),
                                            row.get("name", ""), row.get("detail", "")))
        self._dem(tong)

    def _dem(self, tong: int):
        live = sum(1 for r in self._rows if r["status"] == "live")
        die = sum(1 for r in self._rows if r["status"] == "die")
        cp = sum(1 for r in self._rows if r["status"] == "checkpoint")
        self.count_lbl.configure(text=f"{len(self._rows)}/{tong} · {live} live · {die} die · {cp} checkpoint")

    def _xong(self, kq: dict):
        self.check_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if kq.get("token_chet"):
            messagebox.showwarning("Check live", "Token đã hết hạn/bị vô hiệu — dán token còn sống.\n"
                                   + (kq.get("detail") or ""), parent=self)
        self.set_status(f"Check xong {len(self._rows)} UID.")

    def _xong_loi(self, msg: str):
        self.check_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        messagebox.showwarning("Check live", msg, parent=self)
        self.set_status(msg)

    def _xoa(self):
        self._rows = []
        self.tree.delete(*self.tree.get_children())
        self.count_lbl.configure(text="")

    def _xuat_txt(self, path: str = ""):
        if not self._rows:
            messagebox.showinfo("Xuất TXT", "Chưa có kết quả.", parent=self); return
        if not path:
            path = filedialog.asksaveasfilename(parent=self, defaultextension=".txt",
                                                filetypes=[("Text", "*.txt")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            for r in self._rows:
                fh.write(f"{r['uid']}|{r['status']}|{r.get('name', '')}\n")
        self.set_status(f"Đã xuất {len(self._rows)} dòng ra {os.path.basename(path)}.")
