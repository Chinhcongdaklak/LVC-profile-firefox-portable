"""Tab "Tao fanpage": chon acc, nhap nhieu ten page, hang muc, mo ta, avatar, bia.

Giao dien o day chi lo bam nut + hien ket qua. Viec tao page (dieu khien trinh
duyet qua WebDriver BiDi) nam trong ``core/fbcreatepage.py`` -- tach ra de test
duoc phan logic ma khong can mo cua so.

Cach chay (theo yeu cau nguoi dung): chia acc thanh cac DOT bang "so luong";
moi dot mo cac acc do, moi acc tao DUNG 1 page roi dong; het dot nay sang dot
ke; het luot acc cuoi cung thi nghi "cach nhau" phut roi quay lai acc dau.
Acc checkpoint/khoa -> loai ngay; acc tao hong 3 lan -> loai. Ten tao duoc thi
xoa khoi bang, ten loi thi tra ve danh sach de vong sau lay lai.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from core import acc_nghi, fbbm, fbcreatepage, page_batch
from core import modun as modun_module
from core.modun import tat_ca as _modun_tat_ca
_modun_tat_ca.nap()   # nap registry 1 lan luc import (luong chinh), tranh tre trong luong nen
from .dialogs import AccountPickerDialog

PAD = 10
#: Hang muc mac dinh khi chua chon (ten dung nhu Facebook goi y).
DEFAULT_CATEGORY = "Blogger"
#: Tran o "So page muon tao" (BUG-001): tranh nhan hang trieu ten treo UI.
MAX_SO_PAGE = 500
#: Facebook khong nhan ten page dai hon ~75 ky tu (IDEA-010): chan truoc khi mo trinh duyet.
MAX_TEN_PAGE = 75
#: Che do "Tu dong chay": chay ngay khi bat / mo tool, hoac cho 'Cach nhau' phut roi chay.
AUTO_NGAY = "Chạy ngay"
AUTO_CHO = "Chờ rồi chạy"

#: Hai chế độ tạo fanpage (phân biệt rõ trên tab).
MODE_ACC = "🧑 Tạo trên acc"
MODE_BM = "🏢 Tạo từ BM"


class CategoryPickerDialog(ctk.CTkToplevel):
    """Bảng chọn hạng mục: lọc trong danh sách đã biết + nút "Hỏi Facebook".

    "Hỏi Facebook" mở 1 acc (đã chọn ở tab), gõ chữ đang lọc vào ô Hạng mục của
    form tạo page và đọc đúng danh sách FB gợi ý (~20s, KHÔNG tạo gì). Kết quả
    lưu vào data/hang_muc_fb.json để lần sau có sẵn trong bảng.
    """

    def __init__(self, parent, app, accounts, initial: str, on_pick):
        super().__init__(parent)
        self.app = app
        self.accounts = accounts
        self.on_pick = on_pick
        self._all = fbcreatepage.load_known_categories()
        self._fb: list[str] = []          # FB vừa gợi ý -> hiện đầu danh sách (★)
        self._items: list[str] = []
        self._busy = False
        self.title("Chọn hạng mục Facebook")
        self.geometry("620x540")
        self.transient(parent)
        self._build(initial)
        self._refresh()
        self.after(200, self._grab)

    def _grab(self) -> None:
        try:
            self.grab_set()
            self.search.focus_set()
        except tk.TclError:
            pass

    def _build(self, initial: str) -> None:
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(12, 4))
        self.search = ctk.CTkEntry(
            top, placeholder_text="Gõ để lọc… (VD: nhà hàng, cửa hàng, nghệ sĩ)")
        self.search.pack(side="left", fill="x", expand=True)
        if initial:
            self.search.insert(0, initial)
        self.search.bind("<KeyRelease>", lambda _e: self._refresh())
        self.search.bind("<Return>", lambda _e: self._choose())
        self.ask_btn = ctk.CTkButton(top, text="🔍 Hỏi Facebook", width=130,
                                     command=self._ask_fb)
        self.ask_btn.pack(side="left", padx=(8, 0))

        self.status = ctk.CTkLabel(self, text="", text_color="gray60", anchor="w")
        self.status.pack(fill="x", padx=12)

        box = ctk.CTkFrame(self)
        box.pack(fill="both", expand=True, padx=12, pady=6)
        toi = ctk.get_appearance_mode() == "Dark"
        self.listbox = tk.Listbox(
            box, activestyle="none", font=("Segoe UI", 12), borderwidth=0,
            highlightthickness=0,
            bg="#2b2b2b" if toi else "#ffffff", fg="#f2f2f2" if toi else "#111111",
            selectbackground="#1f6aa5", selectforeground="#ffffff")
        sb = ctk.CTkScrollbar(box, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 4), pady=4)
        self.listbox.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        self.listbox.bind("<Double-Button-1>", lambda _e: self._choose())
        self.listbox.bind("<Return>", lambda _e: self._choose())

        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(bot, text="✔ Chọn", width=110, command=self._choose).pack(side="right")
        ctk.CTkButton(bot, text="Huỷ", width=80, fg_color="gray40",
                      command=self.destroy).pack(side="right", padx=8)
        ctk.CTkLabel(bot, text="★ = Facebook vừa gợi ý cho chữ đang gõ",
                     text_color="gray60").pack(side="left")

    @staticmethod
    def _khop(name: str, q: str) -> bool:
        n = name.lower()
        return all(w in n for w in q.lower().split())

    def _refresh(self) -> None:
        q = self.search.get().strip()
        fb = list(self._fb)
        fb_key = {x.lower() for x in fb}
        rest = [x for x in self._all
                if x.lower() not in fb_key and (not q or self._khop(x, q))]
        ql = q.lower()

        def hang(x: str):
            # Khớp đúng -> bắt đầu bằng -> chứa; cùng hạng thì theo ABC.
            xl = x.lower()
            return (0 if xl == ql else 1 if xl.startswith(ql) else 2, xl)
        rest.sort(key=hang)
        self._items = fb + rest
        self.listbox.delete(0, "end")
        for x in fb:
            self.listbox.insert("end", "★ " + x)
        for x in rest:
            self.listbox.insert("end", x)
        if self._items:
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(0)
        if not self._busy:
            self.status.configure(
                text=f"{len(self._items)} hạng mục" + (f" khớp '{q}'" if q else "")
                + (" — không thấy? bấm 🔍 Hỏi Facebook" if q and not self._items else ""))

    def _ask_fb(self) -> None:
        if self._busy:
            return
        if not self.accounts:
            messagebox.showinfo(
                "Hỏi Facebook",
                "Chọn ít nhất 1 acc (đã cài profile) ở tab Tạo fanpage rồi mới hỏi được.",
                parent=self)
            return
        q = self.search.get().strip()
        if not q:
            # FB không hiện gợi ý khi ô trống -> cần vài chữ để tìm.
            messagebox.showinfo("Hỏi Facebook",
                                "Gõ vài chữ vào ô lọc trước (VD: nhà hàng, thời trang) "
                                "rồi bấm Hỏi Facebook.", parent=self)
            return
        acc = self.accounts[0]
        self._busy = True
        self.ask_btn.configure(state="disabled")
        self.status.configure(
            text=f"Đang mở acc {acc.id} hỏi Facebook '{q or '(danh sách mặc định)'}' "
                 f"— khoảng 20 giây, không tạo gì…")

        def run():
            try:
                kq = fbcreatepage.search_categories(self.app.manager, acc, [q])
                names = kq.get(q) or []
                fbcreatepage.remember_categories(names)
                self.app._post(lambda: self._fb_done(q, names, None))
            except Exception as exc:  # noqa: BLE001
                self.app._post(lambda e=exc: self._fb_done(q, [], e))
        threading.Thread(target=run, daemon=True).start()

    def _fb_done(self, q: str, names: list, exc) -> None:
        self._busy = False
        try:
            self.ask_btn.configure(state="normal")
            if exc is not None:
                self.status.configure(text=f"Hỏi Facebook lỗi: {exc}")
                return
            self._fb = list(names)
            self._all = fbcreatepage._dedupe(list(self._all) + list(names))
            self._refresh()
            self.status.configure(
                text=f"Facebook gợi ý {len(names)} hạng mục cho "
                     f"'{q or '(mặc định)'}' — chọn ở đầu danh sách (★).")
        except tk.TclError:
            pass          # bảng đã đóng trong lúc chờ

    def _choose(self) -> None:
        sel = self.listbox.curselection()
        if not sel or not self._items:
            return
        name = self._items[sel[0]]
        try:
            self.on_pick(name)
        finally:
            self.destroy()


class AddPageBmDialog(ctk.CTkToplevel):
    """Add MỘT page CÓ SẴN của acc vào BM. Thêm bằng TÊN page (gõ link không ra gợi ý).

    'Đọc page acc' liệt kê page acc sở hữu để chọn nhanh; hoặc gõ tên page trực tiếp.
    KHÔNG tạo page mới (không bấm Tạo fanpage).
    """

    def __init__(self, app, tab, accounts, bm_id_mac_dinh: str = ""):
        super().__init__(app)
        self.app = app
        self.tab = tab
        self.accounts = list(accounts)
        self._pages: dict = {}          # ten hien thi -> {"id","name"}
        self.title("Add page có sẵn vào BM")
        self.geometry("520x340")
        self.transient(app)
        self._build(bm_id_mac_dinh)
        self.after(200, self._grab)

    def _grab(self) -> None:
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _build(self, bm_id: str) -> None:
        pad = {"padx": 12, "pady": 6}
        r1 = ctk.CTkFrame(self, fg_color="transparent"); r1.pack(fill="x", **pad)
        ctk.CTkLabel(r1, text="Acc:", width=60, anchor="w").pack(side="left")
        self.acc_menu = ctk.CTkOptionMenu(r1, width=200, values=[a.id for a in self.accounts])
        self.acc_menu.pack(side="left")
        ctk.CTkButton(r1, text="🔎 Đọc page acc", width=130,
                      command=self._doc_page).pack(side="left", padx=8)

        r2 = ctk.CTkFrame(self, fg_color="transparent"); r2.pack(fill="x", **pad)
        ctk.CTkLabel(r2, text="Page:", width=60, anchor="w").pack(side="left")
        self.page_menu = ctk.CTkOptionMenu(r2, width=280, values=["(gõ tên bên dưới)"])
        self.page_menu.pack(side="left")

        r3 = ctk.CTkFrame(self, fg_color="transparent"); r3.pack(fill="x", **pad)
        ctk.CTkLabel(r3, text="Tên page:", width=60, anchor="w").pack(side="left")
        self.ten_entry = ctk.CTkEntry(r3, width=280,
                                      placeholder_text="Gõ TÊN page (link không ra gợi ý)")
        self.ten_entry.pack(side="left")

        r4 = ctk.CTkFrame(self, fg_color="transparent"); r4.pack(fill="x", **pad)
        ctk.CTkLabel(r4, text="ID BM:", width=60, anchor="w").pack(side="left")
        self.bm_entry = ctk.CTkEntry(r4, width=280); self.bm_entry.pack(side="left")
        if bm_id:
            self.bm_entry.insert(0, bm_id)

        self.status = ctk.CTkLabel(self, text="", text_color="gray60", anchor="w")
        self.status.pack(fill="x", padx=12)

        r5 = ctk.CTkFrame(self, fg_color="transparent"); r5.pack(fill="x", padx=12, pady=12)
        ctk.CTkButton(r5, text="➕ Add vào BM", width=140, fg_color="#2f7d4f",
                      command=self._add).pack(side="right")
        ctk.CTkButton(r5, text="Đóng", width=80, fg_color="gray40",
                      command=self.destroy).pack(side="right", padx=8)

    def _acc(self):
        ma = self.acc_menu.get()
        return self.app.store.get(ma)

    def _doc_page(self) -> None:
        acc = self._acc()
        if acc is None:
            return
        self.status.configure(text=f"Đang đọc page acc {acc.id}… (~30s, không tạo gì)")

        def run():
            ds = fbbm.liet_ke_page(self.app.manager, acc,
                                   log=lambda m: self.app._post(lambda t=m: None))
            self.app._post(lambda: self._page_done(ds))
        threading.Thread(target=run, daemon=True).start()

    def _page_done(self, ds: list) -> None:
        self._pages = {}
        vals = []
        for it in ds:
            nhan = f"{it.get('name', '')} ({it.get('id')})"
            self._pages[nhan] = it
            vals.append(nhan)
        if vals:
            self.page_menu.configure(values=vals); self.page_menu.set(vals[0])
            self.status.configure(text=f"Thấy {len(vals)} page — chọn ở ô Page.")
        else:
            self.status.configure(text="Không đọc được page — gõ tên page thủ công.")

    def _add(self) -> None:
        acc = self._acc()
        if acc is None:
            return
        chon = self._pages.get(self.page_menu.get())
        page_id = str(chon.get("id")) if chon else ""
        page_ten = (chon.get("name") if chon else "") or self.ten_entry.get().strip()
        self.tab._them_page_vao_bm_nen(acc.id, page_id, page_ten, self.bm_entry.get().strip())
        self.status.configure(text="Đã gửi lệnh add — xem nhật ký ở tab.")


class CreatePageTab(ctk.CTkFrame):
    """Tab tao fanpage hang loat."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._acc_ids: list[str] = []
        self._acc_page: dict = {}        # id acc -> số page tạo được (trong lần chạy)
        self._acc_tt: dict = {}          # id acc -> trạng thái "Live"/"Checkpoint"
        self._acc_bm: dict = {}          # id acc -> ID BM riêng của acc (1 acc có thể nhiều BM)
        self._acc_nghi: dict = {}        # id acc -> {tt:'dung', den, ly_do}: acc lỗi tạo page nghỉ N ngày (ADR-027)
        self._ngay_nghi_val = acc_nghi.NGAY_NGHI   # bản chốt số ngày nghỉ (đọc widget ở luồng chính)
        self._tt_mau = None              # mẫu TƯƠNG TÁC gắn: xem reel + like TRƯỚC khi tạo page (không delay)
        self._avatar = ""
        self._cover = ""
        self._running = False
        self._stopped = False
        self._txt_path = ""
        self._restoring = False             # dang nap cau hinh -> khong ghi lai
        self._txt_lock = threading.Lock()   # 3 luong cung ghi file txt
        self._nghi_het = None               # moc het nghi (time.time()) khi dang dem nguoc
        self._nghi_vong = 0
        self._auto_timer = None             # id after() cua lich tu chay khi mo tool lai
        self._auto_het = None               # mốc (time.time) tự chạy — cho bộ đếm ngược
        self._auto_pending = False          # dang dem nguoc delay de tu chay
        self._build()
        # Khoi phuc CAU HINH GAN NHAT (acc, hang muc, mo ta, delay, luong, TXT,
        # avatar/bia, cac toggle) tu lan chay truoc.
        try:
            self._restore_cfg()
        except Exception:  # noqa: BLE001
            pass
        # Áp gợi ý + khoá ô 'bật chuyên nghiệp' theo chế độ vừa khôi phục.
        try:
            self._che_do_doi()
        except Exception:  # noqa: BLE001
            pass
        # Chua co duong dan TXT -> dat MAC DINH createpage/createpage.txt (tao san
        # thu muc). Moi page tao xong tu ghi vao day.
        try:
            if not self.txt_entry.get().strip():
                self.txt_entry.insert(0, self._default_txt())
        except Exception:  # noqa: BLE001
            pass
        # Chua co hang muc -> mac dinh "Blogger".
        try:
            if not self.category_entry.get().strip():
                self.category_entry.insert(0, DEFAULT_CATEGORY)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ dung
    def _build(self) -> None:
        dam = ctk.CTkFont(weight="bold")

        # --- Bố cục 2×2: TRÊN-TRÁI bảng acc · TRÊN-PHẢI tên fanpage
        #                 DƯỚI-TRÁI cấu hình + nút chạy · DƯỚI-PHẢI nhật ký (1/4 góc dưới phải)
        # Khung DƯỚI pack TRƯỚC (side=bottom) để luôn đủ chỗ cho cấu hình + nút Tạo ở cửa sổ thấp
        # (600px, tp06); khung TRÊN nhận phần còn lại. Cả hai expand -> cửa sổ cao thì nhật ký to lên.
        duoi = ctk.CTkFrame(self, fg_color="transparent")
        duoi.pack(side="bottom", fill="both", expand=True, padx=PAD, pady=(0, PAD))
        duoi.grid_columnconfigure(0, weight=1, uniform="duoi")
        duoi.grid_columnconfigure(1, weight=1, uniform="duoi")
        duoi.grid_rowconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(side="top", fill="both", expand=True, padx=PAD, pady=(PAD, 6))
        top.grid_columnconfigure(0, weight=1, uniform="tp")
        top.grid_columnconfigure(1, weight=1, uniform="tp")
        top.grid_rowconfigure(0, weight=1)

        # TRÊN-TRÁI: acc tạo page — bảng dọc chọn nhiều, xoá; cột id/ID BM/số page/trạng thái.
        left = ctk.CTkFrame(top)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
        lh = ctk.CTkFrame(left, fg_color="transparent")
        lh.pack(fill="x", padx=8, pady=(8, 0))
        ctk.CTkLabel(lh, text="Acc tạo page", font=dam).pack(side="left")
        ctk.CTkButton(lh, text="🔎 Quét ID BM", width=110, fg_color="#6a4fa5",
                      command=self._quet_id_bm).pack(side="left", padx=(10, 2))
        ctk.CTkLabel(lh, text="luồng").pack(side="left")
        self.bm_luong_entry = ctk.CTkEntry(lh, width=40)
        self.bm_luong_entry.insert(0, "3")
        self.bm_luong_entry.pack(side="left", padx=(2, 0))
        self.btn_tuong_tac = ctk.CTkButton(lh, text="🤝 Tương tác: Tắt", width=160,
                                           fg_color="#6a4fa5", command=self._chon_mau_tuong_tac)
        self.btn_tuong_tac.pack(side="left", padx=(10, 0))
        ctk.CTkButton(lh, text="➕ Chọn acc", width=100,
                      command=self._pick_accounts).pack(side="right")
        ctk.CTkButton(lh, text="👤 Quản lý acc", width=110, fg_color="#3b6ea5",
                      command=self._quan_ly_acc).pack(side="right", padx=(0, 6))
        ctk.CTkButton(lh, text="🗑 Xoá acc đã chọn", width=140, fg_color="#a33",
                      command=self._remove_selected_accs).pack(side="right", padx=6)
        # Acc lỗi tạo page bị DỪNG 3 ngày (cột Trạng thái '⏸ dừng đến ...'); nút này trả về CHỜ để chạy lại.
        self.reset_btn = ctk.CTkButton(lh, text="🔁 Reset trạng thái", width=130, fg_color="#b8860b",
                                       command=self._reset_trang_thai)
        self.reset_btn.pack(side="right", padx=(0, 6))
        abox = ctk.CTkFrame(left)
        abox.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        # (khoa, tieu de, rong ban dau, canh, rong TOI THIEU). CA 4 cot cung gian theo ti le
        # (stretch=True) + minwidth de cot ID BM / So page khong bao gio bi ep mat nhu truoc
        # (chi cot id gian -> no nuot het chieu rong, 3 cot kia con ~10px).
        acols = (("id", "id acc", 160, "w", 120),
                 ("bm", "ID BM (sửa được)", 170, "w", 130),
                 ("page", "Số page", 90, "center", 70),
                 ("tt", "Trạng thái", 120, "center", 90))
        self.acc_tree = ttk.Treeview(abox, columns=[c[0] for c in acols], show="headings",
                                     selectmode="extended", style="Accounts.Treeview", height=5)
        for k, t, w, a, mw in acols:
            self.acc_tree.heading(k, text=t)
            self.acc_tree.column(k, width=w, minwidth=mw, anchor=a, stretch=True)
        # Double-click o cot ID BM -> sua tay (1 acc co the nhieu BM).
        self.acc_tree.bind("<Double-1>", self._sua_bm_o_bang)
        asb = ttk.Scrollbar(abox, orient="vertical", command=self.acc_tree.yview)
        self.acc_tree.configure(yscrollcommand=asb.set)
        self.acc_tree.pack(side="left", fill="both", expand=True)
        asb.pack(side="right", fill="y")
        self._show_accounts()
        self.after(60000, self._tick_acc_nghi)

        # TRÊN-PHẢI: tên fanpage (mỗi tên 1 dòng)
        right = ctk.CTkFrame(top)
        right.grid(row=0, column=1, sticky="nsew", padx=(3, 0))
        top2 = ctk.CTkFrame(right, fg_color="transparent")
        top2.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(top2, text="Tên fanpage (mỗi tên 1 dòng)", font=dam).pack(side="left")
        self.count_label = ctk.CTkLabel(top2, text="", text_color="gray60")
        self.count_label.pack(side="left", padx=12)
        ctk.CTkLabel(top2, text="Số page", font=dam).pack(side="left", padx=(16, 4))
        self.count_entry = ctk.CTkEntry(top2, width=54, placeholder_text="= số tên")
        self.count_entry.pack(side="left")
        self.names_box = ctk.CTkTextbox(right, height=80)
        self.names_box.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.names_box.bind("<KeyRelease>", lambda _e: self._update_count())

        # DƯỚI-TRÁI: cấu hình xếp dọc (hàng ngắn để vừa nửa màn hình) + nút chạy + dòng kết quả.
        cfg = ctk.CTkFrame(duoi)
        cfg.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
        py = 2

        def hang():
            f = ctk.CTkFrame(cfg, fg_color="transparent")
            f.pack(fill="x", padx=8, pady=py)
            return f

        # Hàng ĐẦU: chọn CHẾ ĐỘ tạo — trên acc (form /pages/creation, cần bật
        # chuyên nghiệp) hay từ BM (mở BM, bấm Thêm → Tạo Trang Facebook mới).
        r_mode = hang()
        ctk.CTkLabel(r_mode, text="Chế độ", font=dam, width=96, anchor="w").pack(side="left", padx=(2, 6))
        self.che_do = ctk.CTkSegmentedButton(
            r_mode, values=[MODE_ACC, MODE_BM], command=lambda _v: self._che_do_doi())
        self.che_do.set(MODE_ACC)
        self.che_do.pack(side="left")
        self.che_do_hint = ctk.CTkLabel(r_mode, text="", text_color="gray60")
        self.che_do_hint.pack(side="left", padx=(10, 0))

        # Hàng: hạng mục
        r3 = hang()
        ctk.CTkLabel(r3, text="Hạng mục *", font=dam, width=96, anchor="w").pack(side="left", padx=(2, 6))
        self.category_entry = ctk.CTkEntry(
            r3, width=170, placeholder_text="Bấm 'Chọn hạng mục…' để lấy đúng tên FB")
        self.category_entry.pack(side="left")
        ctk.CTkButton(r3, text="📋 Chọn hạng mục…", width=140,
                      command=self._pick_category).pack(side="left", padx=6)
        # Hàng: mô tả
        r4 = hang()
        ctk.CTkLabel(r4, text="Mô tả", font=dam, width=96, anchor="w").pack(side="left", padx=(2, 6))
        self.desc_entry = ctk.CTkEntry(
            r4, placeholder_text="Mô tả ngắn cho page (dùng chung cho mọi page)")
        self.desc_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        # Hàng: ảnh đại diện + ảnh bìa
        r5 = hang()
        ctk.CTkLabel(r5, text="Ảnh đại diện", font=dam, width=96, anchor="w").pack(side="left", padx=(2, 6))
        self.avatar_label = ctk.CTkLabel(r5, text="(chưa chọn)", text_color="gray60",
                                         width=90, anchor="w")
        self.avatar_label.pack(side="left")
        ctk.CTkButton(r5, text="Chọn ảnh...", width=90,
                      command=self._pick_avatar).pack(side="left", padx=4)
        ctk.CTkButton(r5, text="Bỏ", width=40, fg_color="gray45",
                      command=lambda: self._set_photo("avatar", "")).pack(side="left")
        ctk.CTkLabel(r5, text="Ảnh bìa", font=dam, anchor="w").pack(side="left", padx=(14, 6))
        self.cover_label = ctk.CTkLabel(r5, text="(chưa chọn)", text_color="gray60",
                                        width=90, anchor="w")
        self.cover_label.pack(side="left")
        ctk.CTkButton(r5, text="Chọn ảnh...", width=90,
                      command=self._pick_cover).pack(side="left", padx=4)
        ctk.CTkButton(r5, text="Bỏ", width=40, fg_color="gray45",
                      command=lambda: self._set_photo("cover", "")).pack(side="left")
        # Hàng: cách nhau + số luồng + tự động thêm BM
        r_delay = hang()
        ctk.CTkLabel(r_delay, text="Cách nhau", font=dam, width=96, anchor="w").pack(side="left", padx=(2, 6))
        self.delay_entry = ctk.CTkEntry(r_delay, width=60)
        self.delay_entry.insert(0, "120")
        self.delay_entry.pack(side="left")
        ctk.CTkLabel(r_delay, text="phút nghỉ mỗi vòng acc",
                     text_color="gray60").pack(side="left", padx=(6, 12))
        ctk.CTkLabel(r_delay, text="Số luồng", font=dam).pack(side="left", padx=(0, 4))
        self.threads_entry = ctk.CTkEntry(r_delay, width=50)
        self.threads_entry.insert(0, "3")
        self.threads_entry.pack(side="left")
        ctk.CTkLabel(r_delay, text="acc mỗi đợt", text_color="gray60").pack(side="left", padx=(6, 12))
        # Acc tạo page LỖI -> nghỉ N ngày rồi mới thử lại (ADR-027). Người dùng chỉnh, mặc định 3.
        ctk.CTkLabel(r_delay, text="Nghỉ nếu lỗi", font=dam).pack(side="left", padx=(0, 4))
        self.ngay_nghi_entry = ctk.CTkEntry(r_delay, width=44)
        self.ngay_nghi_entry.insert(0, "3")
        self.ngay_nghi_entry.pack(side="left")
        ctk.CTkLabel(r_delay, text="ngày", text_color="gray60").pack(side="left", padx=(6, 0))
        # Tự động thêm page vừa tạo vào BM (BM lấy theo dòng acc ở bảng, cột 'ID BM').
        self.auto_add_bm_var = tk.BooleanVar(value=True)     # mặc định TÍCH (yêu cầu người dùng)
        # Bản chốt kiểu Python cho LUỒNG PHỤ (bộ chạy gọi _hien_ket_qua_ten ngoài luồng chính;
        # đọc tk var ở đó -> RuntimeError). trace chạy ở luồng chính mỗi khi ô tích đổi.
        self._auto_add_bm_chot = True
        self.auto_add_bm_var.trace_add(
            "write", lambda *_a: setattr(self, "_auto_add_bm_chot", bool(self.auto_add_bm_var.get())))
        ctk.CTkCheckBox(r_delay, text="Tự động thêm page vào BM",
                        variable=self.auto_add_bm_var).pack(side="left")
        # Hàng: file TXT (mỗi page tạo xong / add BM xong tự ghi 5 cột)
        r_txt = hang()
        ctk.CTkLabel(r_txt, text="Lưu TXT", font=dam, width=96, anchor="w").pack(side="left", padx=(2, 6))
        self.txt_entry = ctk.CTkEntry(
            r_txt, placeholder_text="File .txt — tự ghi 'id acc|link|tên|ID BM|tên BM'")
        self.txt_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r_txt, text="Chọn...", width=70,
                      command=self._pick_txt).pack(side="left", padx=4)
        ctk.CTkButton(r_txt, text="Mở", width=44, fg_color="gray45",
                      command=self._open_txt).pack(side="left")
        # Hàng: chế độ chuyên nghiệp + chạy thử + tự động chạy
        r6 = hang()
        self.ensure_pro_var = tk.BooleanVar(value=True)
        self.pro_chk = ctk.CTkCheckBox(r6, text="Tự bật chuyên nghiệp",
                                       variable=self.ensure_pro_var)
        self.pro_chk.pack(side="left", padx=(2, 8))
        ctk.CTkButton(r6, text="💼 Bật chuyên nghiệp", width=150,
                      fg_color="#6a4fa5", command=self._enable_pro_only).pack(side="left", padx=(0, 12))
        # Bỏ ô "Chạy thử (không bấm Tạo)" theo yêu cầu: luôn tạo thật. Giữ biến (ẩn, luôn False)
        # cho thước tp09_thu_that (script gated tự bật) và mã cũ đọc dry.
        self.dryrun_var = tk.BooleanVar(value=False)
        # Hàng: nút chạy (LUÔN thấy — tp06)
        r7 = hang()
        self.auto_var = tk.BooleanVar(value=False)
        self.auto_switch = ctk.CTkSwitch(r7, text="🔄 Tự động chạy", variable=self.auto_var,
                                         command=self._auto_toggled)
        self.auto_switch.pack(side="left", padx=(2, 4))
        self.auto_mode = ctk.CTkOptionMenu(r7, width=118, values=[AUTO_NGAY, AUTO_CHO],
                                           command=lambda _v: self._auto_mode_doi())
        self.auto_mode.set(AUTO_NGAY)
        self.auto_mode.pack(side="left", padx=(0, 10))
        self.create_btn = ctk.CTkButton(r7, text="🏗 Tạo fanpage", width=140,
                                        fg_color="#2f7d4f", command=self._run)
        self.create_btn.pack(side="left")
        self.stop_btn = ctk.CTkButton(r7, text="⏹ Dừng tạo", width=100, fg_color="#a33",
                                      command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ctk.CTkButton(r7, text="🔍 Dò form (1 acc)", width=130, fg_color="gray45",
                      command=self._inspect).pack(side="left")
        # Hàng: add page vào BM (page có sẵn) + xuất TXT
        r8 = hang()
        ctk.CTkLabel(r8, text="luồng").pack(side="left", padx=(2, 2))
        self.bm_add_luong = ctk.CTkEntry(r8, width=40, height=26)
        self.bm_add_luong.insert(0, "3")
        self.bm_add_luong.pack(side="left", padx=(0, 6))
        ctk.CTkButton(r8, text="🚀 Add HẾT page → BM", width=170, height=26,
                      fg_color="#2f7d4f", command=self._add_het_page_batch).pack(side="left", padx=(0, 6))
        ctk.CTkButton(r8, text="➕ Add page vào BM", width=150, height=26,
                      fg_color="#2f7d4f", command=self._mo_add_page_bm).pack(side="left", padx=(0, 6))
        ctk.CTkButton(r8, text="📤 Xuất TXT (id|link)", width=150, height=26,
                      command=self._export_txt).pack(side="left")
        # Hàng: DÒNG KẾT QUẢ (không còn bảng per-name — chỉ báo số page đã tạo được)
        r9 = hang()
        self.summary_label = ctk.CTkLabel(
            r9, text="Kết quả: chưa chạy.", anchor="w",
            font=ctk.CTkFont(size=15, weight="bold"))
        self.summary_label.pack(side="left", padx=(2, 0))
        ctk.CTkButton(r9, text="Xoá kết quả", width=100, height=26, fg_color="gray45",
                      command=self._clear_results).pack(side="right")
        # Bộ đếm ngược tới lúc TẠO fanpage: hẹn tự chạy (mở tool lại / Chờ rồi chạy) hoặc nghỉ giữa vòng.
        self.countdown_label = ctk.CTkLabel(r9, text="", anchor="e", text_color="#ffd28a",
                                            font=ctk.CTkFont(size=14, weight="bold"))
        self.countdown_label.pack(side="right", padx=(0, 10))
        self._tick_dem_nguoc()
        #: ten -> {"acc":.., "tt":.., "ok":bool, "page_id", "link"} — ket qua CUOI CUNG cua moi ten
        #: (nuoi dong tong ket + Xuat TXT; khong con bang hien thi).
        self._results: dict = {}
        self._results_order: list = []

        # DƯỚI-PHẢI: nhật ký chi tiết (console) — chiếm trọn 1/4 góc dưới phải, co giãn theo cửa sổ.
        r_log = ctk.CTkFrame(duoi)
        r_log.grid(row=0, column=1, sticky="nsew", padx=(3, 0))
        head = ctk.CTkFrame(r_log, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(head, text="Nhật ký chi tiết (console)", font=dam).pack(side="left")
        ctk.CTkButton(head, text="Xoá nhật ký", width=100, height=26, fg_color="gray45",
                      command=self._clear_log).pack(side="right")
        self.log_box = ctk.CTkTextbox(r_log, height=60)  # co gian theo cua so
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------ acc
    def _pick_accounts(self) -> None:
        chon = AccountPickerDialog(self.app, self.app.store.accounts,
                                   self._acc_ids).show()
        if chon is None:
            return
        seen, sach = set(), []
        for a in chon:
            if a and a not in seen:
                seen.add(a)
                sach.append(a)
        self._acc_ids = sach
        self._show_accounts()
        self._persist_cfg()

    # ---------------------------------------------------------------- mẫu tương tác
    def _chon_mau_tuong_tac(self) -> None:
        """Chọn 1 mẫu tương tác đã lưu (hoặc Tắt) -> chạy TRƯỚC khi tạo page (không dùng delay)."""
        from core import tuong_tac_mau as ttm
        menu = self.app._make_menu(self)
        menu.add_command(label="Tắt (không tương tác)", command=lambda: self._dat_mau_tuong_tac(None))
        menu.add_separator()
        for mau in ttm.nap():
            menu.add_command(label=mau["ten"], command=lambda x=mau: self._dat_mau_tuong_tac(x))
        try:
            menu.tk_popup(self.app.winfo_pointerx(), self.app.winfo_pointery())
        finally:
            menu.grab_release()

    def _dat_mau_tuong_tac(self, mau) -> None:
        self._tt_mau = mau
        self._cap_nhat_nut_tuong_tac()
        self._persist_cfg()

    def _cap_nhat_nut_tuong_tac(self) -> None:
        try:
            self.btn_tuong_tac.configure(text="🤝 Tương tác: " + (self._tt_mau["ten"] if self._tt_mau else "Tắt"))
        except Exception:  # noqa: BLE001
            pass

    def _show_accounts(self) -> None:
        """Vẽ lại bảng acc: id acc (kèm '(mất)' nếu chưa có profile), số page tạo được, trạng thái."""
        tree = getattr(self, "acc_tree", None)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for ma in self._acc_ids:
            con = self.app.store.get(ma) is not None
            hien_id = ma if con else f"{ma} (mất)"
            sopage = self._acc_page.get(ma, 0)
            tt = (acc_nghi.mo_ta(self._acc_nghi, ma) or self._acc_tt.get(ma, "")
                  or ("chờ chạy" if con else "mất profile"))
            bm = self._acc_bm.get(ma, "")
            tree.insert("", "end", iid=ma, values=(hien_id, bm, sopage, tt))

    def _dat_bm(self, acc_id: str, bm_id: str) -> None:
        """Điền ID BM tự quét vào ô của acc — CHỈ khi ô đang trống (giữ ô người dùng đã sửa)."""
        if not (self._acc_bm.get(acc_id) or "").strip():
            self._acc_bm[acc_id] = bm_id
            self._show_accounts()
            self._persist_cfg()

    def _quet_id_bm(self) -> None:
        """Tự quét ID BM cho các acc trong bảng (điền ô trống). 1 acc nhiều BM -> lấy cái đầu."""
        accs = self._accounts()
        if not accs:
            messagebox.showinfo("Quét ID BM", "Chưa có acc nào trong bảng.", parent=self.app)
            return
        can = [a for a in accs if not (self._acc_bm.get(a.id) or "").strip()]
        if not can:
            self.set_status("Mọi acc đã có ID BM (xoá ô rồi quét lại nếu muốn cập nhật).")
            return
        try:
            luong = max(1, int(self.bm_luong_entry.get().strip() or 3))
        except (ValueError, tk.TclError):
            luong = 3
        luong = min(luong, len(can))       # không nhiều luồng hơn số acc cần quét
        self._log(f"🔎 Quét ID BM cho {len(can)} acc, {luong} luồng (bỏ qua acc đã có)...")

        def mot(acc):
            ds = fbbm.liet_ke_bm(
                self.app.manager, acc,
                log=lambda m: self.app._post(lambda t=m: self._log(t)))
            return acc.id, ds

        def work():
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=luong) as ex:
                futs = [ex.submit(mot, a) for a in can]
                for f in as_completed(futs):
                    try:
                        acc_id, ds = f.result()
                    except Exception as exc:  # noqa: BLE001
                        self.app._post(lambda e=exc: self._log(f"quét BM lỗi: {e}"))
                        continue
                    if ds:
                        self.app._post(lambda a=acc_id, b=ds[0]["id"], n=ds[0].get("name", ""):
                                       (self._dat_bm(a, b), self._log(f"[{a}] BM {b} “{n}”")))
                    else:
                        self.app._post(lambda a=acc_id: self._log(f"[{a}] không đọc được BM."))
            self.app._post(lambda: self._log("🔎 Quét ID BM xong."))

        threading.Thread(target=work, daemon=True).start()

    def _che_do_doi(self) -> None:
        """Đổi chế độ tạo: 'trên acc' vs 'từ BM'. Cập nhật gợi ý + khoá ô 'bật
        chuyên nghiệp' khi tạo từ BM (BM sở hữu page, không cần chế độ chuyên nghiệp)."""
        bm = self.che_do.get() == MODE_BM
        self.che_do_hint.configure(
            text=("Mở BM → Thêm → “Tạo Trang Facebook mới” (dùng ID BM ở cột acc, chưa có thì tự quét)"
                  if bm else
                  "Mở form Facebook tạo page trên acc (tự bật chế độ chuyên nghiệp)"))
        try:
            self.pro_chk.configure(state="disabled" if bm else "normal")
        except Exception:  # noqa: BLE001
            pass
        if not getattr(self, "_restoring", False):
            self._persist_cfg()

    def _ngu_canh(self):
        """NguCanh cho mo-dun (ADR-028): log vao nhat ky tab qua luong chinh."""
        _modun_tat_ca.nap()          # idempotent: tab dung duoc ke ca khi App chua nap registry (thuoc)
        return modun_module.ngu_canh_tu(self.app, log=lambda m: self.app._post(lambda t=m: self._log(t)), so_luong=1)

    def _quan_ly_acc(self) -> None:
        """Cua so Quan ly acc cho cac acc tab nay dang dung (STT/UID/Name/Ghi chu/Proxy/Nhom/Tinh trang)."""
        from ui.dialogs import AccountManagerDialog
        accs = [a for a in (self.app.store.get(i) for i in self._acc_ids) if a is not None]
        if not accs:
            messagebox.showinfo("Quản lý acc", "Tab này chưa chọn acc nào.", parent=self.app)
            return
        AccountManagerDialog(self.app, accs, tieu_de="Quản lý acc — Tạo fanpage").show()

    def _bm_cua_acc(self, acc_id: str) -> str:
        """ID BM dùng cho acc = ô 'ID BM' riêng của acc đó trong bảng (không còn ô chung)."""
        return (self._acc_bm.get(acc_id, "") or "").strip()

    def _bm_hoac_quet(self, acc) -> str:
        """ID BM của acc; CHƯA có -> TỰ QUÉT (mở BM mặc định của acc) rồi điền vào bảng. Gọi ở luồng nền.

        Trả "" nếu không đọc được BM (acc không quản lý BM nào / lỗi)."""
        bm = self._bm_cua_acc(acc.id)
        if bm:
            return bm
        self.app._post(lambda a=acc.id: self._log(f"[{a}] chưa có ID BM → tự quét BM của acc..."))
        ds = fbbm.liet_ke_bm(self.app.manager, acc,
                             log=lambda m: self.app._post(lambda t=m: self._log(t)))
        if not ds:
            # Acc CHƯA có BM nào -> TỰ TẠO BM (tên = tên acc FB, email = recovery_mail) rồi dùng.
            self.app._post(lambda a=acc.id: self._log(f"[{a}] acc chưa có BM → tự tạo BM mới..."))
            r = modun_module.chay("tao_bm", self._ngu_canh(), [acc])   # mo-dun (ADR-028)
            kq = {"ok": acc.id in r.ok, **r.du_lieu["bm"].get(acc.id, {})}
            kq.setdefault("detail", r.loi[0][1] if r.loi else "")
            if kq.get("ok") and kq.get("bm_id"):
                b, n = str(kq["bm_id"]), str(kq.get("ten_bm", ""))
                self.app._post(lambda a=acc.id, bb=b, nn=n: (self._dat_bm(a, bb),
                               self._log(f"[{a}] ✅ đã tạo BM {bb} “{nn}”.")))
                return b
            self.app._post(lambda a=acc.id, e=kq.get("detail", ""):
                           self._log(f"[{a}] không tạo được BM ({e}) → không add được page."))
            return ""
        bm, ten = str(ds[0]["id"]), str(ds[0].get("name", ""))
        self.app._post(lambda a=acc.id, b=bm, n=ten: (self._dat_bm(a, b),
                                                      self._log(f"[{a}] tự quét được BM {b} “{n}”.")))
        return bm

    def _sua_bm_o_bang(self, event) -> None:
        """Double-click ô cột 'ID BM' -> sửa tay (1 acc có thể nhiều BM)."""
        tree = self.acc_tree
        row = tree.identify_row(event.y)
        col = tree.identify_column(event.x)
        if not row or col != "#2":       # #2 = cột 'bm' (id, bm, page, tt)
            return
        try:
            x, y, w, h = tree.bbox(row, col)
        except (ValueError, tk.TclError):
            return
        ent = tk.Entry(tree)
        ent.insert(0, self._acc_bm.get(row, ""))
        ent.select_range(0, "end")
        ent.focus_set()
        ent.place(x=x, y=y, width=w, height=h)

        def luu(*_a):
            self._acc_bm[row] = ent.get().strip()
            try:
                ent.destroy()
            except tk.TclError:
                pass
            self._show_accounts()
            self._persist_cfg()

        ent.bind("<Return>", luu)
        ent.bind("<FocusOut>", luu)
        ent.bind("<Escape>", lambda _e: ent.destroy())

    def _remove_selected_accs(self) -> None:
        """Xoá các acc đang chọn trong bảng khỏi danh sách acc tạo page."""
        tree = getattr(self, "acc_tree", None)
        chon = list(tree.selection()) if tree else []
        if not chon:
            self.app.set_status("Chọn acc trong bảng rồi bấm Xoá acc đã chọn.")
            return
        bo = set(chon)
        self._acc_ids = [a for a in self._acc_ids if a not in bo]
        self._show_accounts()
        self._persist_cfg()

    def _reset_trang_thai(self) -> None:
        """Nút 🔁 Reset trạng thái: acc đang chọn (không chọn -> tất cả) đang DỪNG trở về CHỜ để chạy."""
        tree = getattr(self, "acc_tree", None)
        chon = list(tree.selection()) if tree else []
        n = acc_nghi.reset(self._acc_nghi, chon or None)
        self._show_accounts()
        self._persist_cfg()
        self.app.set_status(f"Đã reset trạng thái {n} acc → chờ chạy." if n else
                            "Không có acc nào đang dừng" + (" trong số đã chọn." if chon else "."))

    def _doc_ngay_nghi(self) -> int:
        """Đọc ô 'Nghỉ nếu lỗi (ngày)' — GỌI Ở LUỒNG CHÍNH (đọc widget), lưu vào _ngay_nghi_val."""
        try:
            self._ngay_nghi_val = max(0, int(self.ngay_nghi_entry.get().strip() or acc_nghi.NGAY_NGHI))
        except (ValueError, AttributeError):
            self._ngay_nghi_val = acc_nghi.NGAY_NGHI
        return self._ngay_nghi_val

    def _so_ngay_nghi(self) -> int:
        """Số ngày acc NGHỈ khi lỗi — trả bản chốt (an toàn gọi từ luồng nền, không đọc widget)."""
        return int(getattr(self, "_ngay_nghi_val", acc_nghi.NGAY_NGHI))

    def _dung_acc_nghi(self, acc_id: str, ly_do: str) -> None:
        """Acc lỗi tạo page -> DỪNG N ngày (ADR-027; N = ô 'Số ngày nghỉ nếu lỗi'), báo, lưu."""
        ngay = self._so_ngay_nghi()
        if not acc_nghi.dang_dung(self._acc_nghi, acc_id):
            acc_nghi.danh_dau_dung(self._acc_nghi, acc_id, ly_do, ngay=ngay)
        self._log(acc_nghi.thong_bao_dung(acc_id, ly_do, ngay=ngay))
        self.app._post(lambda: (self._show_accounts(), self._persist_cfg()))

    def _cho_acc_nghi(self, acc_id: str, phut: float) -> None:
        """Acc tạo page xong -> CHỜ delay tới lần tiếp theo (cột Trạng thái '⏳ chờ đến ...')."""
        if acc_nghi.danh_dau_cho(self._acc_nghi, acc_id, phut) is not None:
            self._log(acc_nghi.thong_bao_cho(acc_id, phut))
            self.app._post(lambda: (self._show_accounts(), self._persist_cfg()))

    def _tick_acc_nghi(self) -> None:
        """Mỗi phút: acc hết hạn nghỉ tự trở về chờ (cột Trạng thái đổi), để lần chạy sau lấy lại."""
        try:
            if not self.winfo_exists():
                return
            if acc_nghi.don_het_han(self._acc_nghi):
                self._show_accounts()
                self._persist_cfg()
                # Tự động đang BẬT mà không chạy (trước đó mọi acc dừng) -> acc vừa hết hạn thì chạy luôn.
                if bool(self.auto_var.get()) and not self._running and not self._auto_pending:
                    self._log("🔄 Tự động: có acc hết hạn nghỉ — bắt đầu chạy.")
                    self._run(xac_nhan=False)
            self.after(60000, self._tick_acc_nghi)
        except tk.TclError:
            return

    def _cap_nhat_acc_run(self, acc_id: str, tao_them: bool = False, checkpoint: bool = False) -> None:
        """Cập nhật số page tạo được / trạng thái của 1 acc khi đang chạy (gọi qua app._post)."""
        if tao_them:
            self._acc_page[acc_id] = self._acc_page.get(acc_id, 0) + 1
            if self._acc_tt.get(acc_id) != "Checkpoint":
                self._acc_tt[acc_id] = "Live"
        if checkpoint:
            self._acc_tt[acc_id] = "Checkpoint"
        self._show_accounts()

    # ------------------------------------------------------------------ anh
    def _pick_category(self) -> None:
        """Mở bảng chọn hạng mục: lọc danh sách đã biết / hỏi Facebook bằng acc đã chọn."""
        accs = [a for a in self._accounts() if self.app.manager.is_installed(a)]
        CategoryPickerDialog(self.app, self.app, accs,
                             self.category_entry.get().strip(), self._set_category)

    def _set_category(self, name: str) -> None:
        self.category_entry.delete(0, "end")
        self.category_entry.insert(0, name)
        self._persist_cfg()

    def _pick_avatar(self) -> None:
        self._pick_photo("avatar")

    def _pick_cover(self) -> None:
        self._pick_photo("cover")

    def _pick_photo(self, kind: str) -> None:
        path = filedialog.askopenfilename(
            title=("Chọn ảnh đại diện" if kind == "avatar" else "Chọn ảnh bìa"),
            parent=self.app,
            filetypes=[("Ảnh", "*.jpg *.jpeg *.png *.webp *.bmp"), ("Tất cả", "*.*")])
        if path:
            self._set_photo(kind, os.path.normpath(path))

    def _set_photo(self, kind: str, path: str) -> None:
        ten = os.path.basename(path) if path else "(chưa chọn)"
        if kind == "avatar":
            self._avatar = path
            self.avatar_label.configure(text=ten,
                                        text_color="#2f7d4f" if path else "gray60")
        else:
            self._cover = path
            self.cover_label.configure(text=ten,
                                       text_color="#2f7d4f" if path else "gray60")
        self._persist_cfg()

    # ------------------------------------------------------------------ log
    def _log(self, text: str) -> None:
        self.app._post(lambda: self._append(text))

    def _append(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("1.0", f"{time.strftime('%H:%M:%S')}  {text}\n")
        self.log_box.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------ ket qua
    def set_result(self, ten: str, acc_id: str, tt: str, ok: bool,
                   page_id: str = "") -> None:
        """Ghi ket qua CUOI cua mot ten page (an toan goi tu luong khac)."""
        self.app._post(lambda: self._set_result(ten, acc_id, tt, ok, page_id))

    def _set_result(self, ten: str, acc_id: str, tt: str, ok: bool,
                    page_id: str = "") -> None:
        if ten not in self._results:
            self._results_order.append(ten)
        link = f"https://www.facebook.com/{page_id}" if page_id else ""
        cu = self._results.get(ten) or {}
        self._results[ten] = {"acc": acc_id, "tt": tt, "ok": ok,
                              "page_id": page_id or cu.get("page_id", ""),
                              "link": link or cu.get("link", "")}
        self._refresh_results()

    def _refresh_results(self) -> None:
        """Cập nhật DÒNG tổng kết (đã tạo được / không được / đang chờ). Không còn bảng per-name."""
        da = sum(1 for r in self._results.values() if r.get("ok"))
        loi = sum(1 for r in self._results.values()
                  if (not r.get("ok")) and "không được" in (r.get("tt") or ""))
        tong = len(self._results)
        cho = tong - da - loi
        parts = [f"Đã tạo được {da} page"]
        if loi:
            parts.append(f"{loi} tạo fanpage không được")
        if cho:
            parts.append(f"{cho} đang chờ")
        try:
            self.summary_label.configure(text="Kết quả: " + " · ".join(parts)
                                         + (f"  (tổng {tong})" if tong else ""))
        except tk.TclError:
            pass

    def _clear_results(self) -> None:
        self._results = {}
        self._results_order = []
        self._refresh_results()
        self.summary_label.configure(text="Kết quả: chưa chạy.")

    def _export_lines(self) -> list:
        """Cac dong 'acc_id|link_fanpage' cho page ĐÃ TẠO (co link). Test duoc."""
        out = []
        for ten in self._results_order:
            r = self._results.get(ten) or {}
            if r.get("ok") and r.get("link"):
                out.append(f"{r.get('acc', '')}|{r.get('link')}")
        return out

    def _export_txt(self) -> None:
        """Xuat file .txt moi dong 'id acc|link fanpage vua tao'."""
        lines = self._export_lines()
        if not lines:
            messagebox.showinfo("Xuất TXT",
                                "Chưa có page nào tạo được (có link) để xuất.",
                                parent=self.app)
            return
        path = filedialog.asksaveasfilename(
            parent=self.app, defaultextension=".txt",
            initialfile="fanpage_da_tao.txt", filetypes=[("Text", "*.txt")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
        except OSError as exc:
            messagebox.showerror("Xuất TXT", f"Không ghi được file: {exc}", parent=self.app)
            return
        self._log(f"Đã xuất {len(lines)} dòng (id acc|link) ra {path}")
        self.app.set_status(f"Đã xuất {len(lines)} fanpage ra TXT.")

    # ---- luu / khoi phuc CAU HINH GAN NHAT ------------------------------
    @staticmethod
    def _cfg_path() -> str:
        from core.config import TOOL_DIR
        return os.path.join(TOOL_DIR, "data", "create_page.json")

    @staticmethod
    def _default_txt() -> str:
        """Mac dinh: <tool>/createpage/createpage.txt (tao san thu muc)."""
        from core.config import TOOL_DIR
        d = os.path.join(TOOL_DIR, "createpage")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        return os.path.join(d, "createpage.txt")

    def _cfg_read(self) -> dict:
        import json
        try:
            with open(self._cfg_path(), encoding="utf-8") as fh:
                d = json.load(fh)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _persist_cfg(self) -> None:
        """Ghi cau hinh HIEN TAI cua tab ra data/create_page.json."""
        import json
        if self._restoring:
            return
        try:
            cfg = {
                "acc_ids": list(self._acc_ids),
                "names": self.names_box.get("1.0", "end").strip(),
                "category": self.category_entry.get().strip(),
                "description": self.desc_entry.get().strip(),
                "delay": self.delay_entry.get().strip(),
                "threads": self.threads_entry.get().strip(),
                "count": self.count_entry.get().strip(),
                "ngay_nghi": self.ngay_nghi_entry.get().strip(),
                "txt_path": self.txt_entry.get().strip(),
                "avatar": self._avatar,
                "cover": self._cover,
                "ensure_pro": bool(self.ensure_pro_var.get()),
                "auto_run": bool(self.auto_var.get()),
                "auto_mode": self.auto_mode.get(),
                "auto_add_bm": bool(self.auto_add_bm_var.get()),
                "che_do": self.che_do.get(),
                "tt_mau": self._tt_mau,
                "acc_bm": {k: v for k, v in self._acc_bm.items() if v},
                "acc_nghi": {k: v for k, v in self._acc_nghi.items()
                             if acc_nghi.dang_nghi(self._acc_nghi, k)},
            }
            os.makedirs(os.path.dirname(self._cfg_path()), exist_ok=True)
            with open(self._cfg_path(), "w", encoding="utf-8") as fh:
                json.dump(cfg, fh, ensure_ascii=False, indent=1)
        except (OSError, tk.TclError):
            pass

    def _restore_cfg(self) -> None:
        """Nap cau hinh lan truoc vao cac o (goi luc mo tab)."""
        c = self._cfg_read()
        if not c:
            return
        self._restoring = True
        try:
            self._restore_cfg_do(c)
        finally:
            self._restoring = False

    def _restore_cfg_do(self, c: dict) -> None:
        def put(entry, val):
            entry.delete(0, "end")
            entry.insert(0, val or "")
        self._acc_ids = [a for a in (c.get("acc_ids") or []) if a]
        self._show_accounts()
        if c.get("names"):
            self.names_box.delete("1.0", "end")
            self.names_box.insert("1.0", c["names"])
            self._update_count()
        put(self.category_entry, c.get("category"))
        put(self.desc_entry, c.get("description"))
        if c.get("delay"):
            put(self.delay_entry, c.get("delay"))
        if c.get("threads"):
            put(self.threads_entry, c.get("threads"))
        if c.get("count"):
            put(self.count_entry, c.get("count"))
        if c.get("ngay_nghi"):
            put(self.ngay_nghi_entry, c.get("ngay_nghi"))
        put(self.txt_entry, c.get("txt_path"))
        self.auto_add_bm_var.set(bool(c.get("auto_add_bm", True)))   # thiếu khoá -> mặc định tích
        if c.get("che_do") in (MODE_ACC, MODE_BM):
            self.che_do.set(c["che_do"])
        mau = c.get("tt_mau")
        self._tt_mau = mau if isinstance(mau, dict) else None
        self._cap_nhat_nut_tuong_tac()
        self._acc_bm = {str(k): str(v) for k, v in (c.get("acc_bm") or {}).items() if v}
        self._acc_nghi = {str(k): v for k, v in (c.get("acc_nghi") or {}).items() if isinstance(v, dict)}
        acc_nghi.don_het_han(self._acc_nghi)
        self._show_accounts()   # vẽ lại để cột ID BM đã lưu hiện ra sau khi tắt/mở tool
        if c.get("avatar") and os.path.isfile(c["avatar"]):
            self._set_photo("avatar", c["avatar"])
        if c.get("cover") and os.path.isfile(c["cover"]):
            self._set_photo("cover", c["cover"])
        if "ensure_pro" in c:
            self.ensure_pro_var.set(bool(c["ensure_pro"]))
        # Tu dong chay: BAT lai theo cau hinh cu; theo CHE DO da chon (chay ngay / cho delay).
        if c.get("auto_mode") in (AUTO_NGAY, AUTO_CHO):
            self.auto_mode.set(c["auto_mode"])
        if c.get("auto_run"):
            self.auto_var.set(True)
            self._auto_bat_dau()

    # ------------------------------------------------------------------ tu dong chay
    def _auto_delay_phut(self) -> int:
        try:
            return max(0, int(self.delay_entry.get().strip() or 0))
        except (ValueError, tk.TclError):
            return 120

    def _cancel_auto_timer(self) -> None:
        if self._auto_timer is not None:
            try:
                self.after_cancel(self._auto_timer)
            except Exception:  # noqa: BLE001
                pass
        self._auto_timer = None
        self._auto_pending = False
        self._auto_het = None

    def _schedule_auto_start(self) -> None:
        """Hẹn tự chạy sau 'Cách nhau' phút (dùng khi mở tool lại, auto đang bật)."""
        self._cancel_auto_timer()
        phut = self._auto_delay_phut()
        self._auto_pending = True
        self._auto_het = time.time() + phut * 60.0
        self._auto_timer = self.after(phut * 60 * 1000, self._auto_start_now)
        try:
            self._log(f"🔄 Tự động: sẽ tự chạy sau {phut} phút (mở tool lại).")
        except Exception:  # noqa: BLE001
            pass

    def _auto_mode_ngay(self) -> bool:
        """True nếu chế độ 'Chạy ngay'; False nếu 'Chờ rồi chạy'."""
        try:
            return self.auto_mode.get() == AUTO_NGAY
        except Exception:  # noqa: BLE001
            return True

    def _hen_tu_dong_lai(self, ly_do: str = "") -> bool:
        """Auto đang BẬT nhưng lần này không chạy được (mọi acc dừng/chờ, hết acc) -> HẸN chạy lại đúng lúc acc
        sớm nhất hết hạn (không có mốc thì sau 'Cách nhau' phút). Trước đây thoát luôn -> tool mở lại vẫn đứng im
        dù acc đã hết hạn (BUG 2026-09-27). Trả True nếu đã hẹn."""
        try:
            if not bool(self.auto_var.get()) or self._running:
                return False
        except tk.TclError:
            return False
        self._cancel_auto_timer()
        moc = acc_nghi.het_han_som_nhat(self._acc_nghi, self._acc_ids)
        if moc is None:
            giay = max(60, self._auto_delay_phut() * 60)
        else:
            giay = max(5, int(moc - time.time()) + 5)
        self._auto_pending = True
        self._auto_het = time.time() + giay
        self._auto_timer = self.after(int(giay * 1000), self._auto_start_now)
        try:
            self._log(f"🔄 Tự động: {ly_do + ' — ' if ly_do else ''}sẽ thử lại lúc "
                      f"{time.strftime('%d/%m %H:%M', time.localtime(self._auto_het))}.")
        except Exception:  # noqa: BLE001
            pass
        return True

    def _auto_start_now(self) -> None:
        self._auto_timer = None
        self._auto_pending = False
        self._auto_het = None
        if bool(self.auto_var.get()) and not self._running:
            try:
                self._log("🔄 Tự động: đến giờ — bắt đầu chạy.")
            except Exception:  # noqa: BLE001
                pass
            self._run(xac_nhan=False)

    def _auto_bat_dau(self) -> None:
        """Bật auto (do người bấm hoặc mở tool lại): theo CHẾ ĐỘ đã chọn."""
        self._cancel_auto_timer()
        if self._auto_mode_ngay():
            try:
                self._log("🔄 Tự động (chạy ngay) — bắt đầu.")
            except Exception:  # noqa: BLE001
                pass
            self._run(xac_nhan=False)
        else:
            self._schedule_auto_start()

    def _auto_mode_doi(self) -> None:
        """Người dùng đổi chế độ -> lưu; nếu auto đang bật thì áp dụng lại."""
        if self._restoring:
            return
        self._persist_cfg()
        if bool(self.auto_var.get()):
            self._auto_bat_dau()

    def _auto_toggled(self) -> None:
        """Người dùng gạt công tắc Tự động chạy."""
        if self._restoring:
            return
        self._persist_cfg()
        if bool(self.auto_var.get()):
            self._auto_bat_dau()
        else:
            self._cancel_auto_timer()
            try:
                self._log("🔄 Tự động: TẮT.")
            except Exception:  # noqa: BLE001
                pass

    def _pick_txt(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.app, defaultextension=".txt", initialfile="fanpage_da_tao.txt",
            filetypes=[("Text", "*.txt")], confirmoverwrite=False,
            title="Chọn file TXT để ghi kết quả (id acc|link)")
        if path:
            self.txt_entry.delete(0, "end")
            self.txt_entry.insert(0, os.path.normpath(path))
            self._persist_cfg()

    def _open_txt(self) -> None:
        path = self.txt_entry.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showinfo("Mở TXT", "File TXT chưa có (sẽ được tạo khi tạo page đầu).",
                                parent=self.app)
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            subprocess.Popen(["notepad", path])

    def _them_page_vao_bm_nen(self, acc_id: str, page_id: str, page_ten: str,
                              bm_id: str) -> None:
        """Add MỘT page CÓ SẴN vào BM ở luồng nền (không đụng luồng tạo page, không bấm Tạo)."""
        bm_id = (bm_id or "").strip()
        page_ten = (page_ten or "").strip()
        if not bm_id or not (page_id or page_ten):
            messagebox.showwarning("Add page vào BM",
                                   "Cần ID BM và tên page (thêm bằng TÊN mới ra gợi ý).",
                                   parent=self.app)
            return
        self._log(f"[{acc_id}] add page “{page_ten or page_id}” vào BM {bm_id}...")
        self._txt_path = self.txt_entry.get().strip()   # chốt ở luồng chính (work chạy nền)

        def work():
            acc = self.app.store.get(acc_id)
            if acc is None:
                self.app._post(lambda: self._log(f"[{acc_id}] không thấy acc."))
                return
            # Có tên -> đọc BM trước: page đã có thì BỎ QUA (không add trùng).
            kq = fbbm.add_page_vao_bm(
                self.app.manager, acc, bm_id, page_id, page_ten=page_ten,
                kiem_da_co=bool(page_ten),
                log=lambda m: self.app._post(lambda t=m: self._log(t)))
            self.app._post(lambda k=kq: self._log(
                f"[{acc_id}] add BM: "
                f"{'⏭ đã có trong BM, bỏ qua' if k.get('bo_qua') else ('✅ xong' if k.get('ok') else '⚠ chưa xong')} "
                f"(BM “{k.get('ten_bm', '')}”)"))
            if kq.get("ok") and not kq.get("bo_qua"):
                # Ghi file: ID acc | link fanpage | tên fanpage | ID BM | Tên BM
                self._ghi_txt_add_bm(acc_id, page_id, page_ten, bm_id, kq.get("ten_bm", ""))

        threading.Thread(target=work, daemon=True).start()

    def _mo_add_page_bm(self) -> None:
        """Dialog add page CÓ SẴN vào BM: chọn acc + tên page (đọc được danh sách) + ID BM."""
        accs = self._accounts()
        if not accs:
            messagebox.showinfo("Add page vào BM", "Chọn ít nhất một acc trước.", parent=self.app)
            return
        bm_mac_dinh = self._bm_cua_acc(accs[0].id) if accs else ""
        AddPageBmDialog(self.app, self, accs, bm_mac_dinh)

    def _accs_add_bm(self) -> list:
        """Acc để add HẾT page: acc ĐANG CHỌN trong bảng; không chọn -> HẾT acc trong bảng."""
        sel = list(self.acc_tree.selection()) if getattr(self, "acc_tree", None) else []
        ids = sel if sel else list(self._acc_ids)
        out = []
        for i in ids:
            a = self.app.store.get(i)
            if a:
                out.append(a)
        return out

    def _add_het_page_batch(self) -> None:
        """Add HẾT page của các acc (đang chọn hoặc tất cả) vào BM theo dòng acc, song song."""
        accs = self._accs_add_bm()
        if not accs:
            messagebox.showinfo("Add hết page vào BM",
                                "Chọn acc trong bảng (không chọn = tất cả acc).", parent=self.app)
            return
        thieu = [a.id for a in accs if not self._bm_cua_acc(a.id)]
        try:
            luong = max(1, int(self.bm_add_luong.get().strip() or 3))
        except (ValueError, tk.TclError):
            luong = 3
        luong = min(luong, len(accs))
        if not messagebox.askyesno(
                "Add hết page vào BM",
                f"Add HẾT page của {len(accs)} acc vào BM (theo dòng acc), {luong} luồng?\n"
                + (f"{len(thieu)} acc chưa có ID BM → sẽ TỰ QUÉT BM của acc trước.\n" if thieu else "")
                + "Page đã có trong BM sẽ bỏ qua. Không tạo page mới (không bấm Tạo fanpage).", parent=self.app):
            return
        self._log(f"🚀 Add hết page → BM cho {len(accs)} acc, {luong} luồng...")
        self._txt_path = self.txt_entry.get().strip()   # chốt ở luồng chính (work chạy nền)

        def mot(acc):
            bm = self._bm_hoac_quet(acc)          # chưa có -> tự quét, điền bảng
            if not bm:
                return acc.id, {"bm_id": "", "tong": 0, "ok": 0, "bo_qua": 0, "rows": []}
            r = modun_module.chay("add_page_bm", self._ngu_canh(), [acc], bm_id=bm)   # mo-dun (ADR-028)
            return acc.id, r.du_lieu["rows"].get(acc.id, {"bm_id": bm, "tong": 0, "ok": 0, "bo_qua": 0, "rows": []})

        def work():
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=luong) as ex:
                futs = [ex.submit(mot, a) for a in accs]
                for f in as_completed(futs):
                    try:
                        acc_id, kq = f.result()
                    except Exception as exc:  # noqa: BLE001
                        self.app._post(lambda e=exc: self._log(f"add lỗi: {e}"))
                        continue
                    self.app._post(lambda a=acc_id, k=kq: self._log(
                        f"[{a}] xong: add {k.get('ok')}/{k.get('tong')} page vào BM {k.get('bm_id')}"
                        f" (bỏ qua {k.get('bo_qua', 0)} page đã có)"))
                    for r in (kq.get("rows") or []):
                        if r.get("ok") and not r.get("bo_qua"):
                            self._ghi_txt_add_bm(acc_id, r.get("page_id", ""), r.get("page_ten", ""),
                                                 kq.get("bm_id", ""), r.get("ten_bm", ""))
            self.app._post(lambda: self._log("🚀 Add hết page → BM xong."))

        threading.Thread(target=work, daemon=True).start()

    def _add_bm_va_ghi(self, acc_id: str, pid: str, link: str, ten: str, bm_id: str,
                       tu_quet: bool = False) -> None:
        """Tạo page xong: nếu có ID BM thì add page vào BM (luồng nền) rồi ghi TXT 5 cột.

        Không có ID BM: ``tu_quet`` -> TỰ QUÉT BM của acc rồi add; không thì ghi TXT ngay (2 ô BM trống)."""
        bm_id = (bm_id or "").strip()
        if not bm_id and not tu_quet:
            self._append_txt(acc_id, link, ten)
            return
        self._log(f"[{acc_id}] add page “{ten}” vào BM {bm_id or '(tự quét)'}...")

        def work():
            acc = self.app.store.get(acc_id)
            kq = {"ok": False, "ten_bm": "", "detail": "không tìm thấy acc"}
            bm = bm_id
            if acc is not None and not bm:
                bm = self._bm_hoac_quet(acc)
                if not bm:
                    self.app._post(lambda: self._append_txt(acc_id, link, ten))
                    return
            if acc is not None:
                kq = fbbm.add_page_vao_bm(
                    self.app.manager, acc, bm, pid, page_ten=ten,
                    log=lambda m: self.app._post(lambda t=m: self._log(t)))
            self.app._post(lambda k=kq, b=bm: self._append_txt(
                acc_id, link, ten, b, k.get("ten_bm", "")))

        threading.Thread(target=work, daemon=True).start()

    def _ghi_txt_add_bm(self, acc_id: str, page_id: str, page_ten: str,
                        bm_id: str, bm_ten: str) -> None:
        """Add page CÓ SẴN vào BM xong -> ghi 1 dòng ``ID acc|link|tên|ID BM|Tên BM`` (như tạo page)."""
        pid = (page_id or "").strip()
        if not pid:
            return
        self._append_txt(acc_id, f"https://www.facebook.com/{pid}", page_ten, bm_id, bm_ten)

    def _append_txt(self, acc_id: str, link: str, ten: str = "",
                    bm_id: str = "", bm_ten: str = "") -> None:
        """Ghi THEM 1 dong 5 cot 'uid|link|ten|IDBM|nameBM' vao file TXT (an toan da luong)."""
        path = (self._txt_path or "").strip()
        if not path or not link:
            return
        dong = fbbm.dong_txt(acc_id, link, ten, bm_id, bm_ten)
        try:
            with self._txt_lock:
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(dong + "\n")
        except OSError as exc:
            self._log(f"⚠ không ghi được file TXT ({exc})")

    def _update_count(self) -> None:
        n = len(fbcreatepage.parse_names(self.names_box.get("1.0", "end")))
        self.count_label.configure(text=f"{n} tên")

    # ------------------------------------------------------------------ chay
    def _accounts(self) -> list:
        out = []
        for ma in self._acc_ids:
            acc = self.app.store.get(ma)
            if acc is not None:
                out.append(acc)
        return out

    def _inspect(self) -> None:
        accs = self._accounts()
        if not accs:
            messagebox.showinfo("Tạo fanpage", "Chọn ít nhất một acc.", parent=self.app)
            return
        acc = accs[0]
        if not self.app.manager.is_installed(acc):
            messagebox.showwarning("Tạo fanpage",
                                   f"Acc {acc.id} chưa có profile.", parent=self.app)
            return

        def work():
            try:
                info = fbcreatepage.inspect_form(self.app.manager, acc, log=self._log)
                self._log(f"Dò form xong: {len(info.get('inputs', []))} ô nhập, "
                          f"{len(info.get('areas', []))} ô mô tả, "
                          f"{len(info.get('buttons', []))} nút. (URL: "
                          f"{info.get('url', '')[:60]})")
            except Exception as exc:  # noqa: BLE001
                self._log(f"Dò form LỖI: {exc}")
            finally:
                self.app.manager.close(acc, wait=5.0)

        threading.Thread(target=work, daemon=True).start()
        self.app.set_status("Đang dò form tạo page...")

    def _run(self, xac_nhan: bool = True) -> None:
        # Chay TU DONG (xac_nhan=False, vd khoi dong lai tool voi 'Tự động chạy') thi KHONG bung hop thoai
        # kiem tra (chua chon acc / thieu ten / thieu hang muc...) — chi ghi nhat ky roi dung. Nguoi bam Tạo
        # (xac_nhan=True) van thay hop thoai nhu cu.
        def bao(chu: str, kieu: str = "info") -> None:
            if xac_nhan:
                (messagebox.showwarning if kieu == "warn" else messagebox.showinfo)(
                    "Tạo fanpage", chu, parent=self.app)
            else:
                try:
                    self._log("Tự động: bỏ qua — " + chu.replace(chr(10), " ")[:160])
                except Exception:  # noqa: BLE001
                    pass

        if self._running:
            if xac_nhan:
                bao("Đang chạy, chờ xong đã.")
            return
        accs_het = self._accounts()
        names = fbcreatepage.parse_names(self.names_box.get("1.0", "end"))
        if not accs_het:
            bao("Chọn ít nhất một acc.")
            return
        # Acc đang DỪNG (lỗi tạo page, nghỉ 3 ngày) bị bỏ khỏi lần chạy này; hết hạn tự vào lại (ADR-027).
        acc_nghi.don_het_han(self._acc_nghi)
        chay_ids, dung_ids = acc_nghi.loc_chay(self._acc_nghi, [a.id for a in accs_het])
        accs = [a for a in accs_het if a.id in set(chay_ids)]
        if dung_ids:
            self._log("Bỏ qua acc đang dừng/chờ (lỗi: hết 3 ngày; tạo xong: hết delay; hoặc bấm 🔁 Reset trạng thái): "
                      + ", ".join(f"{a} ({acc_nghi.mo_ta(self._acc_nghi, a)})" for a in dung_ids))
        if not accs:
            bao("Mọi acc trong bảng đang DỪNG (lỗi tạo page, nghỉ 3 ngày). "
                                "Chờ hết hạn hoặc chọn acc → 🔁 Reset trạng thái.")
            if not xac_nhan:
                self._hen_tu_dong_lai("mọi acc đang dừng/chờ")
            return
        if not names:
            bao("Nhập ít nhất một tên fanpage.")
            return
        # So page muon tao: nhieu hon so ten -> nhan ten kem so thu tu (2, 3...),
        # ghi lai vao o ten de xoa/lay lai ten van dung. It hon -> lay N ten dau.
        try:
            so_page = max(0, int(self.count_entry.get().strip() or 0))
        except ValueError:
            so_page = 0
        if so_page > MAX_SO_PAGE:
            bao(f"Số page muốn tạo quá lớn ({so_page}). Tối đa {MAX_SO_PAGE} page một lần "
                f"— sẽ tạo {MAX_SO_PAGE}.", "warn")
            so_page = MAX_SO_PAGE
            self.count_entry.delete(0, "end")
            self.count_entry.insert(0, str(so_page))
        if so_page and so_page != len(names):
            names = fbcreatepage.expand_names(names, so_page)
            if so_page > len(fbcreatepage.parse_names(self.names_box.get("1.0", "end"))):
                self.names_box.delete("1.0", "end")
                self.names_box.insert("1.0", "\n".join(names))
                self._update_count()
        # Ten qua dai: FB tu choi -> chan o day, khoi mo acc vo ich (IDEA-010).
        qua_dai = [n for n in names if len(n) > MAX_TEN_PAGE]
        if qua_dai:
            bao(f"{len(qua_dai)} tên dài quá {MAX_TEN_PAGE} ký tự — Facebook không nhận:\n"
                + "\n".join(f"- {n[:40]}… ({len(n)} ký tự)" for n in qua_dai[:5])
                + ("\n- …" if len(qua_dai) > 5 else "")
                + "\nRút ngắn tên rồi bấm Tạo lại.", "warn")
            return
        # Acc chua co profile KHONG con bi chan: tool tu tao profile khi mo (core launch)
        # roi tao page binh thuong (yeu cau nguoi dung 2026-09-17). Chi ghi nhat ky.
        thieu = [a.id for a in accs if not self.app.manager.is_installed(a)]
        if thieu:
            self._log("Acc chưa có profile sẽ được TỰ TẠO trước khi tạo page: " + ", ".join(thieu))

        dry = bool(self.dryrun_var.get())
        cat = self.category_entry.get().strip()
        desc = self.desc_entry.get().strip()
        if not cat:
            # Đã gặp thật (5/9): bỏ trống hạng mục -> FB không bật nút Tạo -> tool
            # đóng trình duyệt và báo nhầm "acc bị cấm". Chặn ngay từ đây.
            bao(
                "Thiếu HẠNG MỤC.\n\nFacebook bắt buộc chọn hạng mục khi tạo page — "
                "thiếu thì nút Tạo không bao giờ bật.\n"
                "Nhập hạng mục đúng ngôn ngữ giao diện acc, VD: Nhà hàng, "
                "Cửa hàng quần áo, Nghệ sĩ, Giáo dục...", "warn")
            self.category_entry.focus_set()
            return
        tu_bm = self.che_do.get() == MODE_BM
        ensure_pro = bool(self.ensure_pro_var.get()) and not tu_bm
        try:
            delay_min = max(0, int(self.delay_entry.get().strip() or 0))
        except ValueError:
            delay_min = 120
        try:
            luong = max(1, int(self.threads_entry.get().strip() or 1))
        except ValueError:
            luong = 3
        luong = min(luong, len(accs))     # không nhiều luồng hơn số acc
        tong = len(names)                 # mỗi TÊN là một page, tạo một lần
        pro_note = ("Tạo TỪ BM: mở Business Manager của acc, bấm Thêm → “Tạo Trang "
                    "Facebook mới” (acc chưa có ID BM sẽ tự quét).\n" if tu_bm else
                    ("Sẽ tự BẬT chế độ chuyên nghiệp cho mỗi acc trước khi tạo "
                     "(FB chặn acc cá nhân).\n" if ensure_pro else ""))
        if not dry and xac_nhan and not messagebox.askyesno(
                "Tạo fanpage",
                f"Tạo {tong} fanpage bằng {len(accs)} acc: mỗi đợt mở {luong} acc, "
                f"mỗi acc tạo 1 page rồi đóng; hết lượt acc thì nghỉ {delay_min} phút "
                f"rồi quay lại acc đầu.\n"
                + pro_note
                + "Tên nào đã lấy để tạo — tạo được hay LỖI — đều XOÁ khỏi ô tên, "
                "không thử lại tên đó. "
                "Acc checkpoint loại ngay, acc hỏng 3 lần bị loại. Chắc chưa?",
                parent=self.app):
            return

        pro_done: set = set()           # acc đã bật chuyên nghiệp (dùng chung cả buổi)
        self._doc_ngay_nghi()           # CHỐT số ngày nghỉ (đọc widget Ở LUỒNG CHÍNH, tránh lỗi luồng nền)
        self._acc_page = {}             # reset số page tạo được + trạng thái cho lần chạy này
        self._acc_tt = {}
        self._show_accounts()
        self._running = True
        self._stopped = False
        self.create_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        # Luu CAU HINH GAN NHAT (acc/hang muc/mo ta/delay/luong/TXT/avatar...).
        self._persist_cfg()
        # Duong dan file TXT: moi page tao xong tu ghi them "id_acc|link".
        self._txt_path = self.txt_entry.get().strip()
        if self._txt_path:
            self._log(f"Tạo xong page nào sẽ ghi thêm 'id|link' vào: {self._txt_path}")
        # Bang ket qua: khoi tao moi ten = "cho tao" de user thay day du danh sach,
        # cai nao xong / khong duoc se cap nhat dan.
        self._clear_results()
        for n in names:
            self._set_result(n, "", "⏳ chờ tạo…", False)
        self._log(f"=== Bắt đầu {'CHẠY THỬ ' if dry else 'TẠO '}{tong} fanpage "
                  f"bằng {len(accs)} acc, mỗi đợt {luong} acc"
                  + (f", hết vòng nghỉ {delay_min} phút" if not dry else "") + " ===")

        def tao(acc, ten):
            # MẪU TƯƠNG TÁC: xem reel + like TRƯỚC khi tạo page (KHÔNG dùng delay của tab).
            if self._tt_mau:
                try:
                    from core import tuong_tac_mau as _ttm
                    _ttm.chay_truoc(self.app.manager, acc, self._tt_mau, log=self._log)
                except Exception as _e:  # noqa: BLE001
                    self._log(f"[{acc.id}] tương tác trước khi tạo lỗi (bỏ qua): {_e}")
            # Nghiep vu (bat pro, tao, dong, dich loi) o core.page_batch.
            bm = ""
            if tu_bm:
                # Tao TU BM: lay ID BM cua acc (chua co -> tu quet BM cua acc).
                bm = self._bm_hoac_quet(acc) or ""
            if tu_bm and not bm:
                kq = page_batch.ket_qua(
                    False, loi=page_batch.LOI_HONG,
                    ghi_chu="Tạo từ BM nhưng acc chưa có / không quét được BM")
            else:
                pro_truoc = getattr(acc, "pro_mode", "")
                # Tool goi DUNG mo-dun theo che do (ADR-028): tao_fanpage_bm / tao_fanpage_acc.
                ma = "tao_fanpage_bm" if tu_bm else "tao_fanpage_acc"
                r = modun_module.chay(
                    ma, self._ngu_canh(), [acc], ten=ten, category=cat, description=desc,
                    avatar=self._avatar, cover=self._cover, submit=not dry,
                    ensure_pro=ensure_pro, pro_done=pro_done, bm_id=bm)
                kq = r.du_lieu["kq"][acc.id]
                # Vua bat chuyen nghiep trong luc tao -> cap nhat cot o tab quan ly acc ngay.
                if getattr(acc, "pro_mode", "") != pro_truoc:
                    self._dong_bo_pro()
            if tu_bm and not dry:
                # Tạo TỪ BM hỏng -> acc DỪNG 3 ngày + loại khỏi lần chạy (acc khác vẫn chạy).
                kq2 = acc_nghi.ket_qua_bm_loi(self._acc_nghi, acc.id, kq, ngay=self._so_ngay_nghi())
                if kq2 is not kq:
                    self._dung_acc_nghi(acc.id, kq.get("ghi_chu") or "tạo hỏng")
                elif kq.get("ok"):
                    # Tạo XONG -> acc chờ "Cách nhau" phút tới lần tiếp (thành công hay lỗi đều qua delay).
                    self._cho_acc_nghi(acc.id, delay_min)
                return kq2
            return kq

        def su_kien(loai, d):
            # UI chi DICH su kien cua bo chay thanh chu/bang (HOP-DONG: su_kien).
            if loai == "vong":
                self._log(f"=== VÒNG {d['vong']}: còn {d['con_ten']} tên, {d['so_acc']} acc, "
                          f"{d['so_dot']} đợt × {luong} acc ===")
                self.app._post(lambda v=d["vong"], n=d["con_ten"]: self._het_nghi(v, n))
            elif loai == "dot":
                self._log(f"[vòng {d['vong']}] đợt {d['dot']}/{d['so_dot']}: mở "
                          + ", ".join(d["acc"]))
            elif loai == "ten":
                self._hien_ket_qua_ten(d["acc"], d["ten"], d["kq"], dry)
            elif loai == "bo_ten":
                self._ten_bi_bo(d["acc"], d["ten"], d.get("ly_do") or "tạo hỏng")
            elif loai == "hong":
                self._log(f"[{d['acc']}] ⏸ {d['toi_da']} lần không tạo được — chờ vòng sau "
                          f"(vòng hỏng {d.get('vong_hong', d.get('lan'))}).")
            elif loai == "loai_acc":
                self._log(f"[{d['acc']}] ⛔ LOẠI acc — {d['ly_do']}")
                if not acc_nghi.dang_dung(self._acc_nghi, d["acc"]):
                    self._dung_acc_nghi(d["acc"], d.get("ly_do") or "loại acc")
                if any(k in (d.get("ly_do") or "").lower() for k in ("khoá", "khoa", "checkpoint")):
                    self.app._post(lambda a=d["acc"]: self._cap_nhat_acc_run(a, checkpoint=True))
            elif loai == "nghi":
                self._log(f"Hết vòng {d['vong']} — nghỉ {d['phut']} phút rồi quay lại acc đầu...")
                self.app._post(lambda v=d["vong"], p=d["phut"]: self._dem_nguoc(v, p))

        def chay():
            kq = page_batch.chay_theo_dot(
                accs, names, so_moi_dot=luong, nghi_phut=delay_min, tao=tao,
                mot_vong=dry, dung=lambda: self._stopped, su_kien=su_kien)
            con_lai = len(kq["con_ten"])
            vi = kq["dung_vi"]
            if vi == "nhap_lieu":
                self._log(f"DỪNG vì LỖI NHẬP LIỆU — sửa ô Hạng mục rồi bấm Tạo lại "
                          f"(đã tạo {kq['tao_duoc']}/{tong}, còn {con_lai} tên).")
            elif vi == "dung":
                self._log(f"ĐÃ DỪNG theo yêu cầu: tạo được {kq['tao_duoc']}/{tong}, "
                          f"còn {con_lai} tên.")
            elif vi == "het_acc":
                self._log(f"HẾT ACC dùng được: tạo được {kq['tao_duoc']}/{tong}, "
                          f"còn {con_lai} tên chưa tạo.")
            elif vi == "mot_vong":
                self._log(f"CHẠY THỬ xong 1 vòng: {kq['tao_duoc']}/{tong} tên điền form ok.")
            else:
                self._log(f"XONG: tạo được {kq['tao_duoc']}/{tong} fanpage"
                          f" sau {kq['so_vong']} vòng.")
            if kq["acc_loai"]:
                self._log("Acc đã loại: " + "; ".join(f"{i} ({w})" for i, w in kq["acc_loai"]))
            self.app._post(self._done)

        threading.Thread(target=chay, daemon=True).start()
        self.app.set_status(f"Đang tạo {tong} fanpage, mỗi đợt {luong} acc...")

    def _hien_ket_qua_ten(self, acc_id: str, ten: str, kq: dict, dry: bool) -> None:
        """Dịch KetQua của 1 lần thử thành nhật ký + bảng + xoá tên + ghi TXT."""
        if kq.get("ok"):
            pid = kq.get("page_id") or ""
            if dry:
                self._log(f"[{acc_id}] (chạy thử) điền form '{ten}' ok.")
                self.set_result(ten, acc_id, "✔ (chạy thử) điền form ok", True)
                return
            self._log(f"[{acc_id}] ✅ ĐÃ TẠO fanpage '{ten}'" + (f" (id {pid})" if pid else ""))
            self.set_result(ten, acc_id, "✅ Đã tạo" + (f" (id {pid})" if pid else ""), True,
                            page_id=pid)
            if pid:
                link = f"https://www.facebook.com/{pid}"
                # CHỈ tự thêm vào BM khi tích ô "Tự động thêm page vào BM"; BM theo dòng acc.
                bm = self._bm_cua_acc(acc_id) if self._auto_add_bm_chot else ""
                # Tích "Tự động thêm page vào BM" mà acc chưa có ID BM -> tự quét rồi add.
                self._add_bm_va_ghi(acc_id, pid, link, ten, bm, tu_quet=self._auto_add_bm_chot)
            self.app._post(lambda t=ten: self._remove_name(t))
            self.app._post(lambda a=acc_id: self._cap_nhat_acc_run(a, tao_them=True))
            return
        loi, ghi = kq.get("loi"), kq.get("ghi_chu") or ""
        if loi == page_batch.LOI_KHOA:
            self.app._post(lambda a=acc_id: self._cap_nhat_acc_run(a, checkpoint=True))
            tt = f"✖ acc bị khoá/checkpoint ({ghi}) — bỏ tên"
        elif loi == page_batch.LOI_NHAP_LIEU:
            self._log(f"⚠ LỖI NHẬP LIỆU — không phải do acc: {ghi}\n"
                      f"   → sửa ô Hạng mục rồi bấm Tạo lại.")
            tt = f"✖ tạo fanpage không được — lỗi hạng mục ({ghi}) — bỏ tên"
        else:
            tt = f"✖ chưa tạo được ({ghi}) — bỏ tên"
        self.set_result(ten, acc_id, tt[:110], False)

    def _ten_bi_bo(self, acc_id: str, ten: str, ly_do: str) -> None:
        """Tên đã lấy để tạo mà LỖI (bất kỳ lý do) -> BỎ tên khỏi ô tên + ghi kết quả (ADR-023).

        Runner phát "bo_ten" cho MỌI lỗi (khoá acc / hạng mục / tạo hỏng) — đây là chỗ DUY
        NHẤT xoá tên khi lỗi; _hien_ket_qua_ten chỉ ghi chữ, không xoá, kẻo xoá 2 lần."""
        self._log(f"[{acc_id}] ✖ '{ten}' tạo không được ({ly_do}) — bỏ tên này, dùng tên khác.")
        self.set_result(ten, acc_id, f"✖ bỏ (không tạo được: {ly_do[:40]})", False)
        self.app._post(lambda t=ten: self._remove_name(t))

    def _remove_name(self, ten: str) -> None:
        """Xoá dòng tên khỏi bảng khi đã tạo xong (chạy trên luồng giao diện)."""
        try:
            cur = self.names_box.get("1.0", "end").splitlines()
        except Exception:
            return
        out, bo = [], False
        for line in cur:
            if not bo and line.strip() == ten.strip():
                bo = True           # bỏ ĐÚNG một dòng khớp
                continue
            out.append(line)
        self.names_box.delete("1.0", "end")
        self.names_box.insert("1.0", "\n".join(out))
        self._update_count()

    def _enable_pro_only(self) -> None:
        """Chỉ bật 'chế độ chuyên nghiệp' cho các acc đã chọn (không tạo page)."""
        if self._running:
            messagebox.showinfo("Chế độ chuyên nghiệp", "Đang chạy, chờ xong đã.",
                                parent=self.app)
            return
        accs = self._accounts()
        if not accs:
            messagebox.showinfo("Chế độ chuyên nghiệp", "Chọn ít nhất một acc.",
                                parent=self.app)
            return
        thieu = [a.id for a in accs if not self.app.manager.is_installed(a)]
        if thieu:
            messagebox.showwarning("Chế độ chuyên nghiệp",
                                   "Acc chưa có profile: " + ", ".join(thieu),
                                   parent=self.app)
            return
        self._running = True
        self._stopped = False
        self.stop_btn.configure(state="normal")

        def work():
            ok = 0
            for acc in accs:
                if self._stopped:
                    break
                try:
                    kq = fbcreatepage.enable_professional(
                        self.app.manager, acc, log=self._log)
                    if kq.get("done"):
                        ok += 1
                except Exception as exc:  # noqa: BLE001
                    self._log(f"[{acc.id}] LỖI: {exc}")
                finally:
                    try:
                        self.app.manager.close(acc, wait=6.0)
                    except Exception:
                        pass
            self._log(f"XONG bật chuyên nghiệp: {ok}/{len(accs)} acc.")
            # Dong bo cot "Chuyen nghiep" o tab quan ly acc (pro_mode da duoc dat khi bat xong).
            self._dong_bo_pro()
            self.app._post(self._done)

        threading.Thread(target=work, daemon=True).start()
        self.app.set_status(f"Đang bật chuyên nghiệp cho {len(accs)} acc...")

    def _dong_bo_pro(self) -> None:
        """Luu store + ve lai bang acc de cot 'Chuyen nghiep' cap nhat (goi duoc tu luong nen)."""
        try:
            self.app.store.save()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.app._post(self.app.refresh)
        except Exception:  # noqa: BLE001
            pass

    def _stop(self) -> None:
        self._stopped = True
        self.stop_btn.configure(state="disabled")
        self.app.set_status("Đang dừng sau khi xong page hiện tại...")
        self._log("Đã bấm Dừng — sẽ dừng sau khi xong page đang chạy.")

    # ------------------------------------------------------- dem nguoc nghi
    # UI thuan: core chi phat su kien "nghi" (phut); dong ho o day chay bang
    # after() cua tkinter, tat khi co vong moi / dung / xong (IDEA-007).
    def dem_nguoc_text(self, now: float | None = None) -> str:
        """Chữ đếm ngược tới lúc TẠO fanpage ('' nếu không hẹn gì). Test được (now giả)."""
        t = time.time() if now is None else now
        if self._auto_het is not None and self._auto_timer is not None:
            moc, ly_do = self._auto_het, "tự chạy tạo fanpage"
        elif self._running and not self._stopped and self._nghi_het is not None:
            moc, ly_do = self._nghi_het, "tạo vòng tiếp"
        else:
            return ""
        con = max(0, int(round(moc - t)))
        gio, phut, giay = con // 3600, (con % 3600) // 60, con % 60
        chu = f"{gio:02d}:{phut:02d}:{giay:02d}" if gio else f"{phut:02d}:{giay:02d}"
        return f"⏳ Còn {chu} đến lúc {ly_do}"

    def _tick_dem_nguoc(self) -> None:
        """Mỗi giây cập nhật nhãn đếm ngược (chạy suốt đời tab, nhẹ)."""
        try:
            if not self.winfo_exists():
                return
            self.countdown_label.configure(text=self.dem_nguoc_text())
            self.after(1000, self._tick_dem_nguoc)
        except tk.TclError:
            return

    def _dem_nguoc(self, vong: int, phut: float) -> None:
        self._nghi_het = time.time() + float(phut) * 60.0
        self._nghi_vong = vong
        self._tick_nghi()

    def _tick_nghi(self) -> None:
        if not self._running or self._stopped or self._nghi_het is None:
            return
        con = int(round(self._nghi_het - time.time()))
        if con <= 0:
            self._nghi_het = None
            return
        self.app.set_status(f"Nghỉ còn {con // 60:02d}:{con % 60:02d} rồi tạo tiếp "
                            f"(vòng {self._nghi_vong + 1})...")
        self.after(1000, self._tick_nghi)

    def _het_nghi(self, vong: int, con_ten: int) -> None:
        self._nghi_het = None
        self.app.set_status(f"Vòng {vong}: đang tạo, còn {con_ten} tên...")

    def _done(self) -> None:
        self._running = False
        self._nghi_het = None
        self.stop_btn.configure(state="disabled")
        self.create_btn.configure(state="normal")
        self.app.set_status("Xong tạo fanpage.")
        # Auto đang bật, chưa bị Dừng tay, vẫn còn tên -> hẹn lượt sau (acc đang chờ delay/nghỉ sẽ hết hạn).
        try:
            con_ten = bool(fbcreatepage.parse_names(self.names_box.get("1.0", "end")))
        except tk.TclError:
            con_ten = False
        if con_ten and not self._stopped:
            self._hen_tu_dong_lai("xong lượt, còn tên")
