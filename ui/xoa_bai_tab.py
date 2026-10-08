"""Tab "🗑 Xoá bài viết" — xoá bài đã đăng của fanpage theo KHOẢNG NGÀY + THỂ LOẠI bằng Graph API (token page).

Bảng: STT · acc FB · fanpage · từ ngày · đến ngày · thể loại · trạng thái. Mỗi DÒNG = một fanpage của một acc.
XOÁ BẰNG COOKIE: tool TỰ LẤY token từ cookie/phiên của acc (mở trình duyệt acc 1 lần, derive_token) rồi xoá
qua Graph API đúng như source tham khảo — người dùng KHÔNG dán token. "🔎 Quét fanpage" cũng tự lấy token.
bấm đúp ô fanpage để gõ ID tay; bấm đúp ô ngày/thể loại để sửa. Hàng "Đề xuất" đặt nhanh khoảng ngày:
CẢ NĂM (chọn năm), TRƯỚC NGÀY (xoá sạch bài cũ hơn một ngày mốc), CŨ HƠN N ngày/tháng/năm, và "📊 Đếm theo năm"
đọc hết bài của page rồi báo mỗi năm còn bao nhiêu bài để người dùng biết mà chọn. "🔍 Quét trước" CHỈ ĐẾM; "🗑 Xoá thật" hỏi xác
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
COLS = (("stt", "STT", 44, "center"), ("acc", "Acc FB", 130, "w"),
        ("cookie", "Cookie", 70, "center"), ("ck_tt", "TT cookie", 104, "center"),
        ("token", "Token", 150, "w"), ("page", "Fanpage", 200, "w"),
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
        self._acc_token: dict = {}          # id acc -> token LẤY TỪ COOKIE (cache phiên, bí mật)
        self._ck_tt: dict = {}              # id acc -> trạng thái cookie lần kiểm gần nhất
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
        ctk.CTkButton(r1, text="🔎 Quét fanpage", width=120, fg_color="#2f6f9f",
                      command=self._quet_page).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(r1, text="➕ Nhập ID page", width=120, command=self._them_page_tay).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(r1, text="🗑 Xoá dòng", width=100, fg_color="gray40",
                      command=self._xoa_dong).pack(side="left", padx=4, pady=6)
        self.ck_btn = ctk.CTkButton(r1, text="🔍 Kiểm cookie", width=120, fg_color="#2f7f5f",
                                    command=self._kiem_cookie)
        self.ck_btn.pack(side="left", padx=4, pady=6)
        self.token_btn = ctk.CTkButton(r1, text="🔑 Lấy token", width=112, fg_color="#2f7f5f",
                                       command=self._lay_token_chon)
        self.token_btn.pack(side="left", padx=4, pady=6)
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
        self.loai_menu.set(xb.NHAN_LOAI["video"])   # mặc định xoá VIDEO fanpage
        self.loai_menu.pack(side="left", pady=6)
        ctk.CTkButton(r2, text="✓ Áp cho dòng đã chọn", width=160, command=self._ap_dong).pack(side="left", padx=(10, 4), pady=6)
        for nhan, ngay in (("7 ngày", 7), ("30 ngày", 30), ("90 ngày", 90)):
            ctk.CTkButton(r2, text=nhan, width=64, fg_color="gray40",
                          command=lambda n=ngay: self._dat_nhanh(n)).pack(side="left", padx=2, pady=6)

        # Hàng 2b: ĐỀ XUẤT — đặt khoảng ngày theo năm / trước ngày / cũ hơn N; mỗi nút áp luôn cho dòng.
        r2b = ctk.CTkFrame(self)
        r2b.pack(fill="x", padx=PAD, pady=4)
        ctk.CTkLabel(r2b, text="Đề xuất", font=dam).pack(side="left", padx=(8, 6))
        self.nam_menu = ctk.CTkOptionMenu(r2b, width=86, values=[str(n) for n in xb.cac_nam()])
        self.nam_menu.set(str(xb.nam_hien_tai()))
        self.nam_menu.pack(side="left", pady=6)
        ctk.CTkButton(r2b, text="📅 Cả năm", width=96, fg_color="#2f6f9f",
                      command=self._dat_nam).pack(side="left", padx=(4, 12), pady=6)

        ctk.CTkLabel(r2b, text="Trước ngày").pack(side="left", padx=(0, 4))
        self.truoc_entry = ctk.CTkEntry(r2b, width=100, placeholder_text="dd/mm/yyyy")
        self.truoc_entry.pack(side="left", pady=6)
        ctk.CTkButton(r2b, text="⏮ Bài cũ hơn ngày này", width=160, fg_color="#2f6f9f",
                      command=self._dat_truoc_ngay).pack(side="left", padx=(4, 12), pady=6)

        ctk.CTkLabel(r2b, text="Cũ hơn").pack(side="left", padx=(0, 4))
        self.cu_hon_entry = ctk.CTkEntry(r2b, width=46)
        self.cu_hon_entry.insert(0, "6")
        self.cu_hon_entry.pack(side="left", pady=6)
        self.don_vi_menu = ctk.CTkOptionMenu(r2b, width=84, values=[n for _, n in xb.DON_VI])
        self.don_vi_menu.set(xb.NHAN_DON_VI["thang"])
        self.don_vi_menu.pack(side="left", padx=(4, 0), pady=6)
        ctk.CTkButton(r2b, text="✓ Áp", width=56, fg_color="#2f6f9f",
                      command=self._dat_cu_hon).pack(side="left", padx=(4, 12), pady=6)

        self.dem_nam_btn = ctk.CTkButton(r2b, text="📊 Đếm theo năm", width=130, fg_color="#6a4fa5",
                                         command=self._dem_nam)
        self.dem_nam_btn.pack(side="left", padx=4, pady=6)


        # Hàng 3: bảng
        box = ctk.CTkFrame(self)
        box.pack(fill="both", expand=True, padx=PAD, pady=4)
        self.tree = ttk.Treeview(box, columns=[c[0] for c in COLS], show="headings",
                                 selectmode="extended", style="Accounts.Treeview", height=10)
        for k, t, w, a in COLS:
            self.tree.heading(k, text=t)
            self.tree.column(k, width=w, anchor=a, stretch=(k in ("page", "tt")))
        self.tree.bind("<Double-1>", self._sua_o)
        self.tree.bind("<Button-3>", self._menu_chuot_phai)
        self._menu = tk.Menu(self.tree, tearoff=0)
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

    def _cookie_acc(self, acc_id: str) -> str:
        """Cookie TEXT của acc — kèm mỗi request Graph.

        Lấy THẲNG cookie trong bảng Quản lý acc (người dùng chốt 07/10: "cookie lấy từ bảng
        quản lý acc có sẵn") — đó cũng là cookie hiện ở cột "Cookie" của tab này, nhìn sao
        thì chạy vậy. Ô cookie trong bảng rỗng thì mới đọc tạm cookie tươi trong profile;
        muốn cập nhật ô đó thì bấm chuột phải acc > "🍪 Lấy lại cookie mới (từ profile)".
        """
        acc = self.app.store.get(acc_id) if hasattr(self.app, "store") else None
        if acc is None:
            return ""
        ck = (getattr(acc, "cookie", "") or "").strip()
        if ck:
            return ck
        try:
            from core.modun.check_tuong import cookie_cua_acc
            return cookie_cua_acc(self.app.manager, acc)
        except Exception:  # noqa: BLE001
            return ""

    def _co_cookie(self, acc_id: str) -> bool:
        """Acc có cookie để gửi kèm request không (cookie đã lưu, hoặc có profile Firefox để lấy tươi).
        Kiểm nhẹ (không đọc sqlite mỗi lần vẽ)."""
        acc = self.app.store.get(acc_id) if hasattr(self.app, "store") else None
        if acc is None:
            return False
        if (getattr(acc, "cookie", "") or "").strip():
            return True
        try:
            return bool(self.app.manager.is_installed(acc))
        except Exception:  # noqa: BLE001
            return False

    def _o_cookie(self, acc_id: str) -> str:
        """Cot "Cookie": so cookie facebook acc dang co. Dem NHE (khong doc sqlite moi lan ve)."""
        acc = self.app.store.get(acc_id) if hasattr(self.app, "store") else None
        if acc is None:
            return "—"
        so = 0
        try:
            from core import cookies as _ck
            so = len([c for c in _ck.parse(getattr(acc, "cookie", "") or "",
                                           default_domain=".facebook.com")])
        except Exception:  # noqa: BLE001
            so = 0
        if so:
            return str(so)
        return "profile" if self._co_cookie(acc_id) else "—"

    def _o_ck_tt(self, acc_id: str) -> str:
        """Cot "TT cookie": ket qua kiem cookie gan nhat (nut 🔍 Kiểm cookie / truoc khi xoa)."""
        return self._ck_tt.get(acc_id, "chưa kiểm")

    def _token_acc(self, acc_id: str) -> str:
        """Token da luu cua acc (cot "Token" bang Quan ly acc = extra["token"]); fallback cache phien."""
        acc = self.app.store.get(acc_id) if hasattr(self.app, "store") else None
        tok = str((getattr(acc, "extra", None) or {}).get("token") or "").strip() if acc else ""
        return tok or (self._acc_token.get(acc_id) or "").strip()

    def _o_token(self, d: dict) -> str:
        """Cot "Token": token cua dong, da CHE bot + noi ro tu dau ra."""
        tok = (d.get("token") or "").strip()
        if tok:
            return f"{xb.che_token(tok)} (nhập tay)"
        tok = self._token_acc(d["acc_id"])
        if tok:
            return f"{xb.che_token(tok)} (tự lấy)"
        return "— bấm đúp để nhập"

    def _ve(self) -> None:
        tree = getattr(self, "tree", None)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for i, (k, d) in enumerate(self._dong.items(), start=1):
            page = d.get("page_ten") or d["page_id"]
            if d.get("page_ten") and d["page_ten"] != d["page_id"]:
                page = f"{d['page_ten']} ({d['page_id']})"
            o = {"stt": i, "acc": d["acc_id"], "page": page,
                 "cookie": self._o_cookie(d["acc_id"]), "ck_tt": self._o_ck_tt(d["acc_id"]),
                 "token": self._o_token(d),
                 "tu": d.get("tu", ""), "den": d.get("den", ""),
                 "loai": xb.NHAN_LOAI.get(d.get("loai", "tat_ca"), "Tất cả"),
                 "tt": d.get("tt", "") or "chờ"}
            tree.insert("", "end", iid=k, values=tuple(o[c[0]] for c in COLS))
        accs = {d["acc_id"] for d in self._dong.values()}
        ck_co = sum(1 for a in accs if self._co_cookie(a))
        self.lbl_token.configure(
            text=(f"{ck_co}/{len(accs)} acc có cookie — tự lấy token khi xoá" if accs
                  else "xoá bằng cookie (tự lấy token)"))

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
        self.app.set_status("Bấm 🔎 Quét fanpage, hoặc ➕ Nhập ID page cho acc vừa chọn (token tự lấy từ cookie).")

    def _token_cookie(self, acc_id: str) -> str:
        """Lấy token của acc (HTTP business_locations trước, cookie yếu thì mở trình duyệt).

        GHI vào cột "Token" của bảng Quản lý acc (extra["token"]) để hai tab đồng bộ. Chạy ở LUỒNG NỀN.
        """
        san = self._token_acc(acc_id)
        if san:
            self._acc_token[acc_id] = san
            return san
        acc = self.app.store.get(acc_id)
        if acc is None:
            self._log(f"[{acc_id}] không thấy acc để lấy token")
            return ""
        self._log(f"[{acc_id}] lấy token (business_locations)...")
        tok, loi = xb.token_tu_cookie(self.app.manager, acc, log=self._log)
        self._acc_token[acc_id] = tok
        if tok:
            if not isinstance(getattr(acc, "extra", None), dict):
                acc.extra = {}
            acc.extra["token"] = tok                      # ghi vao cot Token bang Quan ly acc
            try:
                self.app.store.save()
                self.app._post(self.app.refresh)
            except Exception:  # noqa: BLE001
                pass
            self._log(f"[{acc_id}] đã lấy token: {xb.che_token(tok)}")
        else:
            self._log(f"[{acc_id}] KHÔNG lấy được token: {loi}")
        return tok

    def _quet_page(self) -> None:
        accs = self._acc_dang_chon() or sorted({d["acc_id"] for d in self._dong.values()})
        if not accs:
            messagebox.showinfo("Quét fanpage", "Chọn acc trước.", parent=self.app)
            return
        self._log(f"=== QUÉT FANPAGE {len(accs)} acc (tự lấy token từ cookie) ===")

        def work():
            for a in accs:
                tok = self._token_cookie(a)                       # mở trình duyệt acc, lấy token
                if not tok:
                    self._log(f"[{a}] bỏ qua — không lấy được token từ cookie")
                    continue
                ck = self._cookie_acc(a)
                ds, loi = xb.cac_page_cua_token(tok, cookie=ck)
                if loi:
                    self._log(f"[{a}] quét fanpage lỗi: {loi}")
                    continue
                self._log(f"[{a}] {len(ds)} fanpage: " + ", ".join(p["name"] for p in ds[:6]))

                def cap_nhat(a=a, ds=ds):
                    # Bỏ dòng "chờ page" (page_id rỗng) của acc rồi thêm từng page.
                    for k in [k for k, d in self._dong.items() if d["acc_id"] == a and not d["page_id"]]:
                        self._dong.pop(k, None)
                    for p in ds:
                        self._them_dong(a, p["id"], p["name"], p.get("access_token") or "")
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
        acc_id = accs[0]
        self._them_dong(acc_id, pid, "", "")
        self._ve()
        self._persist_cfg()
        # Đọc tên page (tự lấy token từ cookie, luồng nền) nếu acc có cookie.
        if self._co_cookie(acc_id):
            self._doc_ten_page(acc_id, pid)

    def _doc_ten_page(self, acc_id: str, page_id: str) -> None:
        """Đọc tên fanpage vừa gõ ID (luồng nền) để dòng không trơ trọi một dãy số.
        Token lấy từ cookie acc."""
        def work():
            tok = self._token_cookie(acc_id)
            if not tok:
                return
            ten, loi = xb.ten_page(page_id, tok, cookie=self._cookie_acc(acc_id))
            if loi:
                self._log(f"[{page_id}] {loi}")
                return
            self._log(f"[{page_id}] tên fanpage: {ten}")

            def cap_nhat():
                k = _khoa(acc_id, page_id)
                if k in self._dong:
                    self._dong[k]["page_ten"] = ten
                    self._ve()
                    self._persist_cfg()
            self.app._post(cap_nhat)
        threading.Thread(target=work, daemon=True, name="xoabai-tenpage").start()

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
        tu, den, _loi = xb.khoang_n_ngay(ngay)
        self._dien_khoang(tu, den)

    def _dien_khoang(self, tu: str, den: str, *, ap: bool = False, nhan: str = "") -> None:
        """Đổ (tu, den) vào 2 ô Từ/Đến; ``ap`` thì áp luôn cho dòng đang chọn (không chọn = tất cả)."""
        self.tu_entry.delete(0, "end")
        if tu:
            self.tu_entry.insert(0, tu)
        self.den_entry.delete(0, "end")
        if den:
            self.den_entry.insert(0, den)
        if ap:
            self._ap_dong()
            if nhan:
                self._log(nhan)

    def _de_xuat(self, bo: tuple, nhan: str) -> None:
        """Dùng chung cho 3 nút đề xuất: (tu, den, loi) -> báo lỗi hoặc đổ vào ô + áp cho dòng."""
        tu, den, loi = bo
        if loi:
            messagebox.showwarning("Đề xuất khoảng ngày", loi, parent=self.app)
            return
        self._dien_khoang(tu, den, ap=True, nhan=nhan)

    def _dat_nam(self) -> None:
        """CẢ NĂM đang chọn: 01/01 → 31/12 của năm đó."""
        nam = self.nam_menu.get().strip()
        self._de_xuat(xb.khoang_nam(nam), f"đề xuất: cả năm {nam}")
        self._persist_cfg()

    def _dat_truoc_ngay(self) -> None:
        """Mọi bài TRƯỚC ngày mốc (không gồm chính ngày đó) — dọn bài cũ một lần."""
        ngay = self.truoc_entry.get().strip()
        if not ngay:
            messagebox.showinfo("Trước ngày", "Gõ ngày mốc (dd/mm/yyyy) đã.", parent=self.app)
            return
        self._de_xuat(xb.khoang_truoc_ngay(ngay), f"đề xuất: mọi bài trước ngày {ngay}")
        self._persist_cfg()

    def _dat_cu_hon(self) -> None:
        """Bài CŨ HƠN N ngày/tháng/năm tính từ hôm nay."""
        so = self.cu_hon_entry.get().strip()
        dv = xb.MA_DON_VI.get(self.don_vi_menu.get(), "thang")
        self._de_xuat(xb.khoang_cu_hon(so, dv), f"đề xuất: bài cũ hơn {so} {xb.NHAN_DON_VI.get(dv, dv)}")
        self._persist_cfg()

    def _dem_nam(self) -> None:
        """Đọc HẾT bài của các fanpage đang chọn rồi báo mỗi năm còn bao nhiêu bài (chỉ đọc, không xoá)."""
        dong = self._dong_chay()
        if not dong:
            messagebox.showinfo("Đếm theo năm", "Chưa có dòng nào có fanpage.", parent=self.app)
            return
        self.dem_nam_btn.configure(state="disabled")
        self._stopped = False
        self._log(f"=== ĐẾM THEO NĂM {len(dong)} fanpage (chỉ đọc) ===")

        def work():
            try:
                for d in dong:
                    if self._stopped:
                        break
                    nhan = d.get("page_ten") or d["page_id"]
                    self._on_row(d["acc_id"], d["page_id"], {"tt": "đang lấy token / đếm…"})
                    tok = self._token_cookie(d["acc_id"])
                    if not tok:
                        self._on_row(d["acc_id"], d["page_id"], {"tt": "✖ không lấy được token từ cookie"})
                        continue
                    d_nam, loi = xb.thong_ke_nam(d["page_id"], tok, cookie=self._cookie_acc(d["acc_id"]),
                                                 log=self._log, nen_dung=lambda: self._stopped)
                    if loi:
                        self._log(f"[{nhan}] lỗi: {loi}")
                        self._on_row(d["acc_id"], d["page_id"], {"tt": "✖ " + loi[:60]})
                        continue
                    tong = sum(o["tong"] for o in d_nam.values())
                    self._log(f"[{nhan}] tổng {tong} bài:")
                    for dong_chu in xb.dong_dem_nam(d_nam):
                        self._log("   " + dong_chu)
                    nam_ds = [str(n) for n in d_nam if n]
                    self._on_row(d["acc_id"], d["page_id"],
                                 {"tt": f"📊 {tong} bài · năm: " + ", ".join(nam_ds[:6])})
            except Exception as exc:  # noqa: BLE001
                self._log(f"LỖI: {exc}")
            finally:
                self.app._post(lambda: self.dem_nam_btn.configure(state="normal"))
        threading.Thread(target=work, daemon=True, name="xoabai-demnam").start()

    def _acc_cua_dong_chon(self) -> list:
        """Acc cua cac DONG dang chon trong bang; khong chon dong nao -> het acc trong bang."""
        chon = [k for k in self.tree.selection() if k in self._dong]
        ds = [self._dong[k]["acc_id"] for k in chon] or [d["acc_id"] for d in self._dong.values()]
        thay, ra = set(), []
        for a in ds:
            if a not in thay:
                thay.add(a)
                ra.append(a)
        return ra

    def _kiem_cookie(self) -> None:
        """Cot "TT cookie": goi HTTP bang cookie tung acc (core.checkwall) — KHONG mo trinh duyet.

        Cookie chet thi lay token tu cookie cung chet -> biet truoc de khoi mo browser vo ich.
        """
        accs = self._acc_cua_dong_chon()
        if not accs:
            messagebox.showinfo("Kiểm cookie", "Chưa có dòng nào trong bảng.", parent=self.app)
            return
        self._log(f"Kiểm cookie {len(accs)} acc (HTTP, không mở trình duyệt)...")
        for a in accs:
            self._ck_tt[a] = "đang kiểm…"
        self._ve()
        # CHOT o nhap + cookie ngay o LUONG CHINH: doc widget tk tu luong nen -> RuntimeError
        # "main thread is not in main loop" (da do that 07/10).
        luong = max(1, self._int(self.luong_entry, 2))
        items = [(a, self._cookie_acc(a)) for a in accs]

        def work():
            from core import checkwall

            def on_row(r):
                nhan = {checkwall.LIVE: "✅ Live", checkwall.DIE: "❌ Die",
                        checkwall.CHECKPOINT: "⛔ Checkpoint",
                        checkwall.COOKIE_CHET: "✖ chưa đăng nhập"}.get(r["trang_thai"],
                                                                        r["trang_thai"])
                self._ck_tt[r["id"]] = nhan
                self._log(f"[{r['id']}] cookie: {nhan} — {r.get('chi_tiet', '')}")
                self.app._post(self._ve)

            checkwall.check_nhieu(items, workers=luong, on_row=on_row)
            self.app._post(lambda: self._log("Kiểm cookie xong."))

        threading.Thread(target=work, daemon=True, name="xoabai-kiemcookie").start()

    def _lay_token_chon(self) -> None:
        """Nut "Lay token": tu lay token TU COOKIE cho acc cua cac dong dang chon.

        Mo trinh duyet tung acc nen hoi truoc va chay TUAN TU (derive_token dung mot cong BiDi).
        """
        accs = [a for a in self._acc_cua_dong_chon() if not self._acc_token.get(a)]
        if not accs:
            messagebox.showinfo("Lấy token",
                                "Các acc trong bảng đều đã có token rồi.", parent=self.app)
            return
        if not messagebox.askyesno(
                "Lấy token",
                f"Tool sẽ MỞ TRÌNH DUYỆT lần lượt {len(accs)} acc để lấy token từ cookie."
                + chr(10) * 2
                + "Facebook mới hay không lộ token nữa — acc nào không lấy được thì bạn dán "
                  "token tay vào cột Token (bấm đúp)."
                + chr(10) * 2 + "Tiếp tục?", parent=self.app):
            return

        def work():
            for a in accs:
                self._token_cookie(a)
                self.app._post(self._ve)
            self.app._post(lambda: self._log("Lấy token xong."))

        threading.Thread(target=work, daemon=True, name="xoabai-laytoken").start()

    def _menu_chuot_phai(self, event) -> None:
        """Chuot phai tren bang: mo profile / copy UID / lay lai cookie cho acc cua dong do."""
        k = self.tree.identify_row(event.y)
        if k and k in self._dong and k not in self.tree.selection():
            self.tree.selection_set(k)          # chuot phai vao dong chua chon -> chon dong do
        accs = self._acc_cua_dong_chon()
        if not accs:
            return
        m = self._menu
        m.delete(0, "end")
        duoi = f" ({len(accs)} acc)" if len(accs) > 1 else f" ({accs[0]})"
        m.add_command(label="▶ Mở profile" + duoi, command=lambda: self._mo_profile(accs))
        m.add_separator()
        m.add_command(label="📋 Copy UID" + duoi, command=lambda: self._copy_uid(accs))
        m.add_command(label="🍪 Copy cookie" + duoi, command=lambda: self._copy_cookie(accs))
        m.add_command(label="🔑 Copy token" + duoi, command=lambda: self._copy_token(accs))
        m.add_separator()
        m.add_command(label="🍪 Lấy lại cookie (từ profile)" + duoi,
                      command=lambda: self._lay_cookie(accs))
        m.add_separator()
        m.add_command(label="🔍 Kiểm cookie" + duoi, command=self._kiem_cookie)
        m.add_command(label="🔑 Lấy token" + duoi, command=self._lay_token_chon)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _acc_doi_tuong(self, accs: list) -> list:
        """id acc -> doi tuong Account (bo id khong con trong bang Quan ly acc)."""
        kho = getattr(self.app, "store", None)
        if kho is None:
            return []
        ra = []
        for ma in accs:
            a = kho.get(ma)
            if a is not None:
                ra.append(a)
        return ra

    def _mo_profile(self, accs: list) -> None:
        """Mo trinh duyet cua acc (mo-dun "mo_profile": CHI mo, tool khong thao tac gi)."""
        doi = self._acc_doi_tuong(accs)
        if not doi:
            messagebox.showinfo("Mở profile", "Không thấy acc trong bảng Quản lý acc.",
                                parent=self.app)
            return
        self._log(f"Mở profile: {', '.join(a.id for a in doi)}")
        self.app.goi_modun("mo_profile", doi, done_message="Đã mở profile.",
                           tieu_de="Mở profile", tu_tao_profile=True)

    def _copy_uid(self, accs: list) -> None:
        """Copy UID cac acc dang chon vao clipboard (moi dong mot UID)."""
        chu = chr(10).join(accs)
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(chu)
        except tk.TclError:
            return
        self._log(f"Đã copy {len(accs)} UID.")
        self.app.set_status(f"Đã copy {len(accs)} UID vào clipboard.")

    def _dat_clipboard(self, chu: str) -> bool:
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(chu)
            return True
        except tk.TclError:
            return False

    def _copy_cookie(self, accs: list) -> None:
        """Copy cookie THẬT (đầy đủ) của acc vào clipboard — mỗi acc một dòng.

        Khác cột "Cookie" (chỉ đếm số) — cái này copy chuỗi cookie để dán sang nơi khác.
        """
        dong = [self._cookie_acc(a) for a in accs]
        co = [c for c in dong if c]
        if not co:
            messagebox.showinfo("Copy cookie", "Các acc này chưa có cookie.", parent=self.app)
            return
        if self._dat_clipboard(chr(10).join(dong)):
            self._log(f"Đã copy cookie {len(co)}/{len(accs)} acc.")
            self.app.set_status(f"Đã copy cookie {len(co)} acc vào clipboard.")

    def _copy_token(self, accs: list) -> None:
        """Copy token THẬT (đầy đủ) của acc vào clipboard — mỗi acc một dòng.

        Lấy token đã lưu (cột Token = extra["token"]); acc chưa có token thì để trống dòng đó.
        """
        dong = [self._token_acc(a) for a in accs]
        co = [t for t in dong if t]
        if not co:
            messagebox.showinfo(
                "Copy token",
                "Các acc này chưa có token. Bấm '🔑 Lấy token' hoặc nhập tay trước.",
                parent=self.app)
            return
        if self._dat_clipboard(chr(10).join(dong)):
            self._log(f"Đã copy token {len(co)}/{len(accs)} acc.")
            self.app.set_status(f"Đã copy token {len(co)} acc vào clipboard.")

    def _lay_cookie(self, accs: list) -> None:
        """Lay lai cookie MOI tu profile roi ghi vao acc (mo-dun "lay_cookie").

        Cot "Cookie" cua tab nay doc thang account.cookie nen lay xong la cot do tuoi ngay.
        """
        doi = self._acc_doi_tuong(accs)
        if not doi:
            return
        dang_mo = [a.id for a in doi if self._dang_chay(a)]
        if dang_mo and not messagebox.askyesno(
                "Lấy lại cookie",
                f"{len(dang_mo)} acc đang mở trình duyệt. Tool sẽ ĐÓNG trình duyệt của các acc "
                "đó để lấy cookie đầy đủ." + chr(10) * 2 + "Tiếp tục?", parent=self.app):
            return
        self.app.goi_modun("lay_cookie", doi, done_message="Đã lấy lại cookie mới.",
                           tieu_de="Lấy lại cookie", tu_tao_profile=False)
        # Cookie moi -> ve lai cot Cookie; trang thai cu khong con dung nua.
        for a in doi:
            self._ck_tt.pop(a.id, None)
        self.app._post(self._ve)

    def _dang_chay(self, account) -> bool:
        try:
            return bool(self.app.manager.is_running(account))
        except Exception:  # noqa: BLE001
            return False

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
        if key == "token":
            cu = (d.get("token") or "").strip()
            moi_tok = SimplePromptDialog(
                self.app, "Token",
                f"Token cho acc {d['acc_id']} (để TRỐNG = tool tự lấy từ cookie):", cu).show()
            if moi_tok is None:
                return
            d["token"] = moi_tok.strip()
            self._ve()
            self._persist_cfg()
            return
        if key in ("acc", "cookie", "ck_tt"):
            # Ba cot nay khong sua tay -> bam dup = MO PROFILE cua acc cho nhanh.
            self._mo_profile([d["acc_id"]])
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
            self._them_dong(d["acc_id"], moi, "", d.get("token") or "")
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
                "tu": self.tu_entry.get().strip(), "den": self.den_entry.get().strip(),
                "loai": xb.MA_THEO_NHAN.get(self.loai_menu.get(), "tat_ca"),
                "luong": self._int(self.luong_entry, 2), "gioi_han": self._int(self.gioi_han_entry, 0),
                "cach_giay": self._int(self.cach_entry, 2), "txt": self.txt_entry.get().strip(),
                "nam": self.nam_menu.get().strip(), "truoc_ngay": self.truoc_entry.get().strip(),
                "cu_hon": self.cu_hon_entry.get().strip(),
                "don_vi": xb.MA_DON_VI.get(self.don_vi_menu.get(), "thang")}
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
            self._acc_token = {}   # token lấy lại từ cookie mỗi phiên, không lưu
            if c.get("nam") and str(c["nam"]) in self.nam_menu.cget("values"):
                self.nam_menu.set(str(c["nam"]))
            if c.get("don_vi") in xb.NHAN_DON_VI:
                self.don_vi_menu.set(xb.NHAN_DON_VI[c["don_vi"]])
            if c.get("cu_hon"):
                self.cu_hon_entry.delete(0, "end")
                self.cu_hon_entry.insert(0, str(c["cu_hon"]))
            for e, key in ((self.tu_entry, "tu"), (self.den_entry, "den"), (self.txt_entry, "txt"),
                           (self.truoc_entry, "truoc_ngay")):
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
