"""Tab "🗑 Xoá bài viết" — xoá bài đã đăng của fanpage theo KHOẢNG NGÀY + THỂ LOẠI bằng Graph API (token page).

Bảng: STT · acc FB · fanpage · từ ngày · đến ngày · thể loại · trạng thái. Mỗi DÒNG = một fanpage của một acc.
Token dán theo ACC (nút 🔑 Token, che khi hiện); "🔎 Quét fanpage" gọi /me/accounts lấy page + page token;
bấm đúp ô fanpage để gõ ID tay; bấm đúp ô ngày/thể loại để sửa. "🔍 Quét trước" CHỈ ĐẾM; "🗑 Xoá thật" hỏi xác
nhận kèm số bài đã đếm rồi mới xoá. Nghiệp vụ ở core/fbxoabai + mô-đun xoa_bai (ADR-029); tab chỉ vẽ/dịch.
Token là bí mật: lưu data/xoa_bai.json (gitignore), nhật ký chỉ in dạng che.
"""

from __future__ import annotations

import json
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from core import fbxoabai as xb
from core import modun
from core.modun import tat_ca
from .dialogs import AccountPickerDialog, SimplePromptDialog

PAD = 8
TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLS = (("stt", "STT", 44, "center"), ("acc", "Acc FB", 130, "w"), ("page", "Fanpage", 200, "w"),
        ("tu", "Từ ngày", 96, "center"), ("den", "Đến ngày", 96, "center"),
        ("loai", "Thể loại", 84, "center"), ("tt", "Trạng thái", 220, "w"))
NHAN_LOAI = [n for _, n in xb.LOAI]


def _khoa(acc_id: str, page_id: str) -> str:
    return f"{acc_id}|{page_id}"


class XoaBaiTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        #: Dòng bảng: {khoa: {acc_id, page_id, page_ten, token, tu, den, loai, tt}} — giữ thứ tự.
        self._dong: dict = {}
        self._acc_token: dict = {}          # id acc -> user/page token (BÍ MẬT)
        self._running = False
        self._stopped = False
        self._restoring = False
        self._build()
        self._restore_cfg()

    # ------------------------------------------------------------------ dựng
    @staticmethod
    def _cfg_path() -> str:
        return os.path.join(TOOL_DIR, "data", "xoa_bai.json")

    def _build(self) -> None:
        dam = ctk.CTkFont(weight="bold")
        # Hàng 1: acc + token + quét page
        r1 = ctk.CTkFrame(self)
        r1.pack(fill="x", padx=PAD, pady=(PAD, 4))
        ctk.CTkButton(r1, text="👤 Chọn acc", width=110, command=self._pick_accounts).pack(side="left", padx=(8, 4), pady=6)
        ctk.CTkButton(r1, text="🔑 Token", width=90, fg_color="#6a4fa5",
                      command=self._nhap_token).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(r1, text="🔎 Quét fanpage", width=120, fg_color="#2f6f9f",
                      command=self._quet_page).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(r1, text="➕ Nhập ID page", width=120, command=self._them_page_tay).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(r1, text="🗑 Xoá dòng", width=100, fg_color="gray40",
                      command=self._xoa_dong).pack(side="left", padx=4, pady=6)
        self.lbl_token = ctk.CTkLabel(r1, text="", text_color="gray60")
        self.lbl_token.pack(side="right", padx=8)

        # Hàng 2: áp khoảng ngày + thể loại cho các dòng đang chọn (không chọn = tất cả)
        r2 = ctk.CTkFrame(self)
        r2.pack(fill="x", padx=PAD, pady=4)
        ctk.CTkLabel(r2, text="Từ ngày", font=dam).pack(side="left", padx=(8, 4))
        self.tu_entry = ctk.CTkEntry(r2, width=100, placeholder_text="dd/mm/yyyy")
        self.tu_entry.pack(side="left", pady=6)
        ctk.CTkLabel(r2, text="Đến ngày", font=dam).pack(side="left", padx=(10, 4))
        self.den_entry = ctk.CTkEntry(r2, width=100, placeholder_text="dd/mm/yyyy")
        self.den_entry.pack(side="left", pady=6)
        ctk.CTkLabel(r2, text="Thể loại", font=dam).pack(side="left", padx=(10, 4))
        self.loai_menu = ctk.CTkOptionMenu(r2, width=100, values=NHAN_LOAI)
        self.loai_menu.set(NHAN_LOAI[0])
        self.loai_menu.pack(side="left", pady=6)
        ctk.CTkButton(r2, text="✓ Áp cho dòng đã chọn", width=160, command=self._ap_dong).pack(side="left", padx=(10, 4), pady=6)
        for nhan, ngay in (("7 ngày", 7), ("30 ngày", 30), ("90 ngày", 90)):
            ctk.CTkButton(r2, text=nhan, width=64, fg_color="gray40",
                          command=lambda n=ngay: self._dat_nhanh(n)).pack(side="left", padx=2, pady=6)

        # Hàng 3: bảng
        box = ctk.CTkFrame(self)
        box.pack(fill="both", expand=True, padx=PAD, pady=4)
        self.tree = ttk.Treeview(box, columns=[c[0] for c in COLS], show="headings",
                                 selectmode="extended", style="Accounts.Treeview", height=10)
        for k, t, w, a in COLS:
            self.tree.heading(k, text=t)
            self.tree.column(k, width=w, anchor=a, stretch=(k in ("page", "tt")))
        self.tree.bind("<Double-1>", self._sua_o)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Hàng 4: chạy
        r4 = ctk.CTkFrame(self)
        r4.pack(fill="x", padx=PAD, pady=4)
        self.quet_btn = ctk.CTkButton(r4, text="🔍 Quét trước (chỉ đếm)", width=170, fg_color="#2f6f9f",
                                      command=lambda: self._run(dry=True))
        self.quet_btn.pack(side="left", padx=(8, 4), pady=6)
        self.xoa_btn = ctk.CTkButton(r4, text="🗑 Xoá thật", width=110, fg_color="#a33",
                                     command=lambda: self._run(dry=False))
        self.xoa_btn.pack(side="left", padx=4, pady=6)
        self.stop_btn = ctk.CTkButton(r4, text="⏹ Dừng", width=80, fg_color="gray40",
                                      command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=4, pady=6)
        ctk.CTkLabel(r4, text="Luồng").pack(side="left", padx=(12, 2))
        self.luong_entry = ctk.CTkEntry(r4, width=44)
        self.luong_entry.insert(0, "2")
        self.luong_entry.pack(side="left")
        ctk.CTkLabel(r4, text="Tối đa bài/lần (0=hết)").pack(side="left", padx=(12, 2))
        self.gioi_han_entry = ctk.CTkEntry(r4, width=56)
        self.gioi_han_entry.insert(0, "0")
        self.gioi_han_entry.pack(side="left")
        ctk.CTkLabel(r4, text="Cách nhau (giây)").pack(side="left", padx=(12, 2))
        self.cach_entry = ctk.CTkEntry(r4, width=50)
        self.cach_entry.insert(0, "2")
        self.cach_entry.pack(side="left")
        ctk.CTkLabel(r4, text="TXT").pack(side="left", padx=(12, 2))
        self.txt_entry = ctk.CTkEntry(r4, width=180, placeholder_text="ghi bài đã xoá")
        self.txt_entry.pack(side="left")
        ctk.CTkButton(r4, text="…", width=30, command=self._pick_txt).pack(side="left", padx=(2, 8))

        # Hàng 5: nhật ký
        self.log_box = ctk.CTkTextbox(self, height=120)
        self.log_box.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------ tiện ích
    def _log(self, text: str) -> None:
        def ghi():
            try:
                self.log_box.configure(state="normal")
                self.log_box.insert("end", time.strftime("%H:%M:%S ") + text + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
            except tk.TclError:
                pass
        self.app._post(ghi)

    def _int(self, entry, mac: int) -> int:
        try:
            return max(0, int(entry.get().strip() or mac))
        except ValueError:
            return mac

    def _chon(self) -> list:
        return [k for k in self.tree.selection() if k in self._dong]

    def _ve(self) -> None:
        tree = getattr(self, "tree", None)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for i, (k, d) in enumerate(self._dong.items(), start=1):
            page = d.get("page_ten") or d["page_id"]
            if d.get("page_ten") and d["page_ten"] != d["page_id"]:
                page = f"{d['page_ten']} ({d['page_id']})"
            tree.insert("", "end", iid=k, values=(i, d["acc_id"], page, d.get("tu", ""), d.get("den", ""),
                                                  xb.NHAN_LOAI.get(d.get("loai", "tat_ca"), "Tất cả"),
                                                  d.get("tt", "") or "chờ"))
        acc_co = sum(1 for a in self._acc_token if self._acc_token[a])
        self.lbl_token.configure(text=f"{acc_co} acc có token" if acc_co else "chưa dán token acc nào")

    def _them_dong(self, acc_id: str, page_id: str, page_ten: str = "", token: str = "") -> str:
        k = _khoa(acc_id, page_id)
        if k not in self._dong:
            self._dong[k] = {"acc_id": acc_id, "page_id": page_id, "page_ten": page_ten or "",
                             "token": token or "", "tu": self.tu_entry.get().strip(),
                             "den": self.den_entry.get().strip(),
                             "loai": xb.MA_THEO_NHAN.get(self.loai_menu.get(), "tat_ca"), "tt": ""}
        elif page_ten:
            self._dong[k]["page_ten"] = page_ten
            if token:
                self._dong[k]["token"] = token
        return k

    # ------------------------------------------------------------------ acc / token / page
    def _acc_dang_chon(self) -> list:
        ids = []
        for k in self._chon():
            a = self._dong[k]["acc_id"]
            if a not in ids:
                ids.append(a)
        return ids

    def _pick_accounts(self) -> None:
        da = sorted({d["acc_id"] for d in self._dong.values()})
        chon = AccountPickerDialog(self.app, self.app.store.accounts, da).show()
        if chon is None:
            return
        for a in chon:
            if a and not any(d["acc_id"] == a for d in self._dong.values()):
                # Chưa có page: thêm dòng "chờ quét/nhập page" để người dùng thấy acc trong bảng.
                self._them_dong(a, "", "")
        self._ve()
        self._persist_cfg()
        self.app.set_status("Bấm 🔑 Token rồi 🔎 Quét fanpage, hoặc ➕ Nhập ID page cho acc vừa chọn.")

    def _nhap_token(self) -> None:
        accs = self._acc_dang_chon() or sorted({d["acc_id"] for d in self._dong.values()})
        if not accs:
            messagebox.showinfo("Token", "Chọn acc (dòng trong bảng) trước.", parent=self.app)
            return
        nhan = ", ".join(accs[:3]) + ("…" if len(accs) > 3 else "")
        tk_moi = SimplePromptDialog(self.app, "Token Graph API",
                                    f"Dán page token hoặc user token (pages_manage_posts) cho acc: {nhan}",
                                    "").show()
        if tk_moi is None:
            return
        tk_moi = tk_moi.strip()
        for a in accs:
            self._acc_token[a] = tk_moi
            for d in self._dong.values():
                if d["acc_id"] == a and not d.get("token"):
                    d["token"] = tk_moi
        self._ve()
        self._persist_cfg()
        self._log(f"đã lưu token {xb.che_token(tk_moi)} cho {len(accs)} acc")

    def _quet_page(self) -> None:
        accs = self._acc_dang_chon() or sorted({d["acc_id"] for d in self._dong.values()})
        accs = [a for a in accs if self._acc_token.get(a)]
        if not accs:
            messagebox.showinfo("Quét fanpage", "Acc chưa có token — bấm 🔑 Token trước.", parent=self.app)
            return

        def work():
            for a in accs:
                ds, loi = xb.cac_page_cua_token(self._acc_token[a])
                if loi:
                    self._log(f"[{a}] quét fanpage lỗi: {loi}")
                    continue
                self._log(f"[{a}] {len(ds)} fanpage: " + ", ".join(p["name"] for p in ds[:6]))

                def cap_nhat(a=a, ds=ds):
                    # Bỏ dòng "chờ page" (page_id rỗng) của acc rồi thêm từng page.
                    for k in [k for k, d in self._dong.items() if d["acc_id"] == a and not d["page_id"]]:
                        self._dong.pop(k, None)
                    for p in ds:
                        self._them_dong(a, p["id"], p["name"], p.get("access_token") or self._acc_token[a])
                    self._ve()
                    self._persist_cfg()
                self.app._post(cap_nhat)
        threading.Thread(target=work, daemon=True, name="xoabai-quetpage").start()

    def _them_page_tay(self) -> None:
        accs = self._acc_dang_chon() or sorted({d["acc_id"] for d in self._dong.values()})
        if not accs:
            messagebox.showinfo("Nhập ID page", "Chọn acc trước.", parent=self.app)
            return
        pid = SimplePromptDialog(self.app, "Nhập ID fanpage", f"ID fanpage của acc {accs[0]}:", "").show()
        if not pid or not pid.strip():
            return
        pid = pid.strip()
        for k in [k for k, d in self._dong.items() if d["acc_id"] == accs[0] and not d["page_id"]]:
            self._dong.pop(k, None)
        self._them_dong(accs[0], pid, "", self._acc_token.get(accs[0], ""))
        self._ve()
        self._persist_cfg()

    def _xoa_dong(self) -> None:
        chon = self._chon()
        if not chon:
            self.app.set_status("Chọn dòng trong bảng rồi bấm Xoá dòng.")
            return
        for k in chon:
            self._dong.pop(k, None)
        self._ve()
        self._persist_cfg()

    # ------------------------------------------------------------------ ngày / thể loại
    def _ap_dong(self) -> None:
        """Áp Từ/Đến/Thể loại ở hàng 2 cho các dòng đang chọn (không chọn -> tất cả dòng)."""
        tu, den = self.tu_entry.get().strip(), self.den_entry.get().strip()
        _s, _u, loi = xb.khoang_ngay(tu, den)
        if loi:
            messagebox.showwarning("Khoảng ngày", loi, parent=self.app)
            return
        loai = xb.MA_THEO_NHAN.get(self.loai_menu.get(), "tat_ca")
        muc = self._chon() or list(self._dong)
        for k in muc:
            self._dong[k].update({"tu": tu, "den": den, "loai": loai})
        self._ve()
        self._persist_cfg()
        self.app.set_status(f"Đã áp {tu or '…'} → {den or 'hôm nay'} · {xb.NHAN_LOAI[loai]} cho {len(muc)} dòng.")

    def _dat_nhanh(self, ngay: int) -> None:
        """Đặt nhanh: từ (hôm nay - N ngày) đến hôm nay vào 2 ô."""
        hom_nay = time.time()
        self.tu_entry.delete(0, "end")
        self.tu_entry.insert(0, time.strftime("%d/%m/%Y", time.localtime(hom_nay - ngay * 86400)))
        self.den_entry.delete(0, "end")
        self.den_entry.insert(0, time.strftime("%d/%m/%Y", time.localtime(hom_nay)))

    def _sua_o(self, event) -> None:
        """Bấm đúp ô fanpage / từ ngày / đến ngày / thể loại -> sửa tay ngay trong bảng."""
        k = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not k or k not in self._dong:
            return
        idx = int(col.replace("#", "")) - 1
        key = COLS[idx][0] if 0 <= idx < len(COLS) else ""
        d = self._dong[k]
        if key == "loai":
            hien = [n for _, n in xb.LOAI]
            cur = xb.NHAN_LOAI.get(d.get("loai", "tat_ca"))
            d["loai"] = xb.LOAI[(hien.index(cur) + 1) % len(hien)][0]     # bấm đúp = xoay vòng
            self._ve()
            self._persist_cfg()
            return
        if key not in ("page", "tu", "den"):
            return
        tieu_de = {"page": "ID fanpage", "tu": "Từ ngày (dd/mm/yyyy)", "den": "Đến ngày (dd/mm/yyyy)"}[key]
        cu = d["page_id"] if key == "page" else d.get(key, "")
        moi = SimplePromptDialog(self.app, "Sửa", tieu_de + ":", cu).show()
        if moi is None:
            return
        moi = moi.strip()
        if key == "page":
            if not moi:
                return
            self._dong.pop(k, None)
            self._them_dong(d["acc_id"], moi, "", d.get("token") or self._acc_token.get(d["acc_id"], ""))
        else:
            if moi and xb.ngay_tu_chuoi(moi) is None:
                messagebox.showwarning("Ngày", "Sai định dạng dd/mm/yyyy.", parent=self.app)
                return
            d[key] = moi
        self._ve()
        self._persist_cfg()

    def _pick_txt(self) -> None:
        p = filedialog.asksaveasfilename(parent=self.app, defaultextension=".txt",
                                         filetypes=[("Text", "*.txt")], title="File ghi bài đã xoá")
        if p:
            self.txt_entry.delete(0, "end")
            self.txt_entry.insert(0, p)
            self._persist_cfg()

    # ------------------------------------------------------------------ chạy
    def _dong_chay(self) -> list:
        muc = self._chon() or list(self._dong)
        return [dict(self._dong[k]) for k in muc if self._dong[k]["page_id"]]

    def _run(self, dry: bool = True, xac_nhan: bool = True) -> None:
        if self._running:
            messagebox.showinfo("Xoá bài", "Đang chạy, chờ xong đã.", parent=self.app)
            return
        dong = self._dong_chay()
        if not dong:
            messagebox.showinfo("Xoá bài", "Chưa có dòng nào có fanpage. Quét fanpage hoặc nhập ID page.", parent=self.app)
            return
        for d in dong:
            d["token"] = d.get("token") or self._acc_token.get(d["acc_id"], "")
        thieu = [d for d in dong if not d["token"]]
        if thieu:
            messagebox.showwarning("Xoá bài", f"{len(thieu)} dòng chưa có token (acc {thieu[0]['acc_id']}…). "
                                   "Bấm 🔑 Token trước.", parent=self.app)
            return
        for d in dong:
            _s, _u, loi = xb.khoang_ngay(d.get("tu", ""), d.get("den", ""))
            if loi:
                messagebox.showwarning("Khoảng ngày", f"Dòng {d['page_id']}: {loi}", parent=self.app)
                return
        if not dry and xac_nhan:
            da_dem = sum(int((self._dong[_khoa(d['acc_id'], d['page_id'])].get("kq") or {}).get("khop") or 0)
                         for d in dong)
            goi_y = f"Lần quét trước đếm được {da_dem} bài khớp." if da_dem else "Chưa quét trước — nên bấm Quét trước."
            if not messagebox.askyesno("XOÁ THẬT", f"XOÁ bài trên {len(dong)} fanpage theo khoảng ngày + thể loại "
                                       f"từng dòng?\n{goi_y}\n\nXoá là KHÔNG hoàn tác được. Chắc chưa?",
                                       parent=self.app):
                return
        self._running, self._stopped = True, False
        self.quet_btn.configure(state="disabled")
        self.xoa_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._persist_cfg()
        tham = {"dong": dong, "dry": dry, "gioi_han": self._int(self.gioi_han_entry, 0),
                "cach_giay": float(self._int(self.cach_entry, 2)), "so_luong": max(1, self._int(self.luong_entry, 2)),
                "txt": self.txt_entry.get().strip(), "nen_dung": lambda: self._stopped,
                "on_row": self._on_row}
        self._log(f"=== {'QUÉT TRƯỚC' if dry else 'XOÁ THẬT'} {len(dong)} fanpage, luồng {tham['so_luong']} ===")

        def chay():
            try:
                tat_ca.nap()
                nc = modun.ngu_canh_tu(self.app) if hasattr(modun, "ngu_canh_tu") else modun.NguCanh(
                    manager=self.app.manager, store=self.app.store)
                nc.log = self._log
                nc.so_luong = tham["so_luong"]
                kq = modun.chay("xoa_bai", nc, [], **tham)
                self._log("XONG: " + kq.tom_tat())
                for a, ly_do in kq.loi:
                    self._log(f"  ✖ {a}: {ly_do}")
            except Exception as exc:  # noqa: BLE001
                self._log(f"LỖI: {exc}")
            finally:
                self.app._post(self._done)
        threading.Thread(target=chay, daemon=True, name="xoabai").start()

    def _on_row(self, acc_id: str, page_id: str, d: dict) -> None:
        def cap_nhat():
            k = _khoa(acc_id, page_id)
            if k in self._dong:
                self._dong[k]["tt"] = d.get("tt", "")
                if "kq" in d:
                    self._dong[k]["kq"] = {"khop": d["kq"].get("khop"), "xoa": d["kq"].get("xoa"),
                                           "quet": d["kq"].get("quet")}
                self._ve()
        self.app._post(cap_nhat)

    def _stop(self) -> None:
        self._stopped = True
        self._log("đang dừng sau bài hiện tại…")

    def _done(self) -> None:
        self._running = False
        self.quet_btn.configure(state="normal")
        self.xoa_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self._persist_cfg()

    # ------------------------------------------------------------------ lưu / khôi phục
    def _persist_cfg(self) -> None:
        if self._restoring:
            return
        data = {"dong": [{k2: v for k2, v in d.items() if k2 in ("acc_id", "page_id", "page_ten", "token", "tu", "den", "loai")}
                         for d in self._dong.values()],
                "acc_token": dict(self._acc_token),
                "tu": self.tu_entry.get().strip(), "den": self.den_entry.get().strip(),
                "loai": xb.MA_THEO_NHAN.get(self.loai_menu.get(), "tat_ca"),
                "luong": self._int(self.luong_entry, 2), "gioi_han": self._int(self.gioi_han_entry, 0),
                "cach_giay": self._int(self.cach_entry, 2), "txt": self.txt_entry.get().strip()}
        try:
            os.makedirs(os.path.dirname(self._cfg_path()), exist_ok=True)
            with open(self._cfg_path(), "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
        except (OSError, tk.TclError):
            pass

    def _restore_cfg(self) -> None:
        try:
            with open(self._cfg_path(), encoding="utf-8") as fh:
                c = json.load(fh) or {}
        except (OSError, ValueError):
            self._ve()
            return
        self._restoring = True
        try:
            self._acc_token = {str(k): str(v) for k, v in (c.get("acc_token") or {}).items() if v}
            for e, key in ((self.tu_entry, "tu"), (self.den_entry, "den"), (self.txt_entry, "txt")):
                if c.get(key):
                    e.delete(0, "end")
                    e.insert(0, str(c[key]))
            if c.get("loai") in xb.NHAN_LOAI:
                self.loai_menu.set(xb.NHAN_LOAI[c["loai"]])
            for e, key, mac in ((self.luong_entry, "luong", 2), (self.gioi_han_entry, "gioi_han", 0),
                                (self.cach_entry, "cach_giay", 2)):
                e.delete(0, "end")
                e.insert(0, str(c.get(key, mac)))
            for d in c.get("dong") or []:
                if not isinstance(d, dict) or not d.get("acc_id"):
                    continue
                k = _khoa(str(d["acc_id"]), str(d.get("page_id") or ""))
                self._dong[k] = {"acc_id": str(d["acc_id"]), "page_id": str(d.get("page_id") or ""),
                                 "page_ten": str(d.get("page_ten") or ""), "token": str(d.get("token") or ""),
                                 "tu": str(d.get("tu") or ""), "den": str(d.get("den") or ""),
                                 "loai": d.get("loai") if d.get("loai") in xb.NHAN_LOAI else "tat_ca", "tt": ""}
        finally:
            self._restoring = False
        self._ve()
