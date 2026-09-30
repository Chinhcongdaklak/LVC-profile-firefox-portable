"""Tab con "X.com" trong tab Quan ly acc.

Bang acc X rieng (cot user/pass X + chuoi Gmail), them/sua/nhap hang loat bang
hop thoai X (ui/x_dialogs, tu nhan dien dong qua core/x_import). Dung
DANH SACH ACC RIENG (data/accounts_x.json) va THU MUC PROFILE RIENG
(<profiles_root>_x) -> khong bao gio lan voi acc Facebook.
"""

from __future__ import annotations

import copy
import os
import shutil
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from core import cookies as cookie_module
from core import nordvpn
from core import proxy as proxy_module
from core import store as store_module
from core import totp
from core import useragent
from core.profiles import ProfileManager
from core.proxy import Proxy
from core.store import Account, AccountStore, STATUSES

from core import x_import

from .chon_nhanh import ChonNhanhCombo
from .dialogs import (BaseDialog, CookieDialog, FieldEditDialog, GroupManagerDialog,
                      ProxyDialog, SimplePromptDialog)
from .x_dialogs import XAccountDialog, XBulkImportDialog

PAD = 8
DETAIL_WIDTH = 340   # be ngang bang thong tin acc ben phai (nhu tab Facebook)

X_ACCOUNTS_PATH = os.path.join(os.path.dirname(store_module.ACCOUNTS_PATH), "accounts_x.json")
X_START_URL = "https://x.com/"
X_HOME_URL = "https://x.com/home"
X_TAB_TITLE = "𝕏 X.com"

#: Domain mac dinh khi cookie o dang "ten=gia_tri; ..." (khong kem domain).
X_COOKIE_DOMAIN = ".x.com"
#: Cookie cua X nam o hai domain nay (twitter.com la ten cu, van con hieu luc).
X_COOKIE_HOSTS = ("x.com", "twitter.com")
#: Cookie phien dang nhap cua X.
X_AUTH_COOKIE = "auth_token"
#: Thu muc cache cua Firefox trong profile -- xoa duoc, khong mat dang nhap.
X_CACHE_DIRS = ("cache2", "startupCache")

#: Cot rieng cho acc X.com: user/pass X + chuoi Gmail (gmail, pass, mail KP, 2FA).
X_COLUMNS = (
    ("stt", "#", 44, "center"),
    ("id", "User X", 160, "w"),
    ("password", "Pass X", 120, "w"),
    ("gmail", "Gmail", 200, "w"),
    ("gmail_pass", "Pass Gmail", 130, "w"),
    ("gmail_kp", "Mail KP Gmail", 180, "w"),
    ("gmail_2fa", "2FA Gmail", 80, "center"),
    ("group", "Nhóm", 110, "w"),
    ("profile", "Profile", 90, "center"),
    ("cookie", "Cookie X", 80, "center"),
    ("running", "Đang chạy", 85, "center"),
    ("status", "Trạng thái", 95, "center"),
    ("proxy", "Proxy", 210, "w"),
    ("note", "Ghi chú", 220, "w"),
)

TAT_CA_NHOM = "Tất cả nhóm"
TAT_CA_TT = "Tất cả trạng thái"


#: Muc dau tien trong menu bang = de NordVPN tu chon vi tri (bang rong).
BANG_MAC_DINH = "(Mặc định NordVPN)"


class NordVpnDialog(BaseDialog):
    """Hoi user + pass NordVPN (mot tai khoan dung chung) + vi tri truoc khi cai addon.

    ``.show()`` tra ``(user, pass, chi_cai, quoc_gia, bang)`` hoac ``None`` khi
    bam Huy. Pass che bang dau *, tich "Hiện" de xem. Tich "Chỉ cài addon" thi
    khong can user/pass; nguoc lai phai nhap du ca hai (bao loi tai cho, khong
    dong). ``bang`` = "" khi chon "(Mặc định NordVPN)" -> NordVPN tu chon vi tri.
    ``quoc_gia_list`` = danh sach {"name","code","bang":[...]} tu
    ``nordvpn.tai_quoc_gia()``; rong thi chi co "United States".
    """

    def __init__(self, parent, settings, quoc_gia_list=None):
        super().__init__(parent, "Cài NordVPN + đăng nhập", 520, 470)
        self.minsize(440, 430)

        self._quoc_gia_list = list(quoc_gia_list or [])
        self._ten_quoc_gia = [q.get("name", "") for q in self._quoc_gia_list if q.get("name")]
        if not self._ten_quoc_gia:
            self._ten_quoc_gia = [nordvpn.MAC_DINH_QUOC_GIA]

        ctk.CTkLabel(
            self,
            text="Tài khoản NordVPN dùng chung cho các acc đã chọn.\n"
                 "Addon lấy từ addons.mozilla.org (bản đã ký).",
            justify="left", text_color="gray60",
        ).pack(anchor="w", padx=PAD, pady=(PAD, 6))

        ctk.CTkLabel(self, text="User NordVPN (email)").pack(anchor="w", padx=PAD)
        self.user_entry = ctk.CTkEntry(self, placeholder_text="email@nordvpn")
        self.user_entry.insert(0, getattr(settings, "nordvpn_user", "") or "")
        self.user_entry.pack(fill="x", padx=PAD, pady=(2, 8))

        ctk.CTkLabel(self, text="Pass NordVPN").pack(anchor="w", padx=PAD)
        pass_row = ctk.CTkFrame(self, fg_color="transparent")
        pass_row.pack(fill="x", padx=PAD, pady=(2, 8))
        self.pass_entry = ctk.CTkEntry(pass_row, show="*")
        self.pass_entry.insert(0, getattr(settings, "nordvpn_pass", "") or "")
        self.pass_entry.pack(side="left", fill="x", expand=True)
        self._show_pass = tk.BooleanVar(master=self, value=False)
        ctk.CTkCheckBox(pass_row, text="Hiện", width=60, variable=self._show_pass,
                        command=self._toggle_pass).pack(side="left", padx=(6, 0))

        # ---- Vi tri: quoc gia + bang ----
        mac_qg = getattr(settings, "nordvpn_country", "") or nordvpn.MAC_DINH_QUOC_GIA
        if mac_qg not in self._ten_quoc_gia:
            mac_qg = self._ten_quoc_gia[0]

        ctk.CTkLabel(self, text="Quốc gia").pack(anchor="w", padx=PAD)
        self._quoc_gia_var = tk.StringVar(master=self, value=mac_qg)
        # 150 quoc gia -> CTkOptionMenu (menu tkinter) dai qua man hinh va KHONG lan chuot duoc;
        # ChonNhanhCombo co o tim + danh sach lan chuot, bam mot cai la xong.
        self.quoc_gia_menu = ChonNhanhCombo(
            self, variable=self._quoc_gia_var, values=self._ten_quoc_gia,
            command=self._doi_quoc_gia, placeholder="Gõ tên nước để tìm nhanh...")
        self.quoc_gia_menu.pack(fill="x", padx=PAD, pady=(2, 8))

        ctk.CTkLabel(self, text="Bang / Khu vực").pack(anchor="w", padx=PAD)
        self._bang_var = tk.StringVar(master=self, value=BANG_MAC_DINH)
        self.bang_menu = ChonNhanhCombo(
            self, variable=self._bang_var, values=[BANG_MAC_DINH],
            placeholder="Gõ tên bang / khu vực...")
        self.bang_menu.pack(fill="x", padx=PAD, pady=(2, 4))

        ctk.CTkLabel(
            self, text="Không chọn bang → NordVPN tự chọn vị trí trong nước.",
            text_color="gray60", anchor="w", justify="left", wraplength=480,
        ).pack(anchor="w", padx=PAD, pady=(0, 6))

        # Dung bang mac dinh tu Settings neu con hop le cho quoc gia mac dinh.
        mac_bang = getattr(settings, "nordvpn_state", "") or nordvpn.MAC_DINH_BANG
        self._doi_quoc_gia(mac_qg, bang_mong_muon=mac_bang)

        self._chi_cai = tk.BooleanVar(master=self, value=False)
        ctk.CTkCheckBox(self, text="Chỉ cài addon, không đăng nhập",
                        variable=self._chi_cai).pack(anchor="w", padx=PAD, pady=(2, 4))

        self.error_label = ctk.CTkLabel(self, text="", text_color="#e06c6c",
                                        anchor="w", justify="left", wraplength=480)
        self.error_label.pack(anchor="w", padx=PAD)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=PAD, pady=PAD, side="bottom")
        ctk.CTkButton(buttons, text="Huỷ", width=100, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text="OK", width=100,
                      command=self._submit).pack(side="right", padx=6)

        self.after(200, lambda: self.user_entry.focus_set())

    def _toggle_pass(self) -> None:
        self.pass_entry.configure(show="" if self._show_pass.get() else "*")

    def _doi_quoc_gia(self, ten_quoc_gia, *, bang_mong_muon="") -> None:
        """Dung lai menu bang theo quoc gia dang chon (goi khi doi quoc gia)."""
        bangs = nordvpn.bang_cua(self._quoc_gia_list, ten_quoc_gia)
        ten_bang = [b.get("name", "") for b in bangs if b.get("name")]
        values = [BANG_MAC_DINH] + ten_bang
        self.bang_menu.configure(values=values)
        if bang_mong_muon and bang_mong_muon in ten_bang:
            chon = bang_mong_muon
        else:
            chon = BANG_MAC_DINH
        self._bang_var.set(chon)
        # Khong co bang -> chi con "(Mặc định NordVPN)", vo hieu menu.
        self.bang_menu.configure(state="disabled" if not ten_bang else "normal")

    def _doc(self):
        """Doc gia tri hien tai (user, pass, chi_cai, quoc_gia, bang).

        ``bang`` = "" khi chon "(Mặc định NordVPN)".
        """
        bang = self._bang_var.get()
        if bang == BANG_MAC_DINH:
            bang = ""
        return (self.user_entry.get().strip(), self.pass_entry.get().strip(),
                bool(self._chi_cai.get()), self._quoc_gia_var.get(), bang)

    def _submit(self) -> None:
        user, mat_khau, chi_cai, quoc_gia, bang = self._doc()
        if not chi_cai and not (user and mat_khau):
            self.error_label.configure(
                text="Cần nhập cả User và Pass NordVPN (hoặc tích “Chỉ cài addon”).")
            return
        self.result = (user, mat_khau, chi_cai, quoc_gia, bang)
        self.destroy()


def x_settings(settings):
    """Ban sao Settings voi thu muc profile rieng cho X (goc + "_x"); ban goc giu nguyen."""
    ban = copy.copy(settings)
    ban.profiles_root = settings.profiles_root.rstrip("\\/") + "_x"
    return ban


class XAccTab(ctk.CTkFrame):
    """Bang acc X.com: store rieng + ProfileManager rieng."""

    def __init__(self, master, app, *, store_path=None):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.store = AccountStore(store_path or X_ACCOUNTS_PATH)
        self.manager = ProfileManager(x_settings(app.settings), getattr(app.manager, "relays", None))
        self._show_secrets = tk.BooleanVar(master=self, value=True)
        self._rows: list[Account] = []
        self._build_toolbar()
        self._build_table()
        self._build_detail()
        self.menu = self._make_menu()
        self.refresh()

    # ---- giao dien ----------------------------------------------------
    def _build_toolbar(self) -> None:
        filters = ctk.CTkFrame(self, fg_color="transparent")
        filters.pack(fill="x", padx=PAD, pady=(PAD, 4))

        self.search_entry = ctk.CTkEntry(filters, width=360,
                                         placeholder_text="Tìm user X / gmail / nhóm / ghi chú")
        self.search_entry.pack(side="left")
        self.search_entry.bind("<KeyRelease>", lambda _e: self.refresh())

        self.group_filter = ctk.CTkOptionMenu(filters, values=[TAT_CA_NHOM], width=150,
                                              command=lambda _v: self.refresh())
        self.group_filter.pack(side="left", padx=6)

        self.status_filter = ctk.CTkOptionMenu(filters, values=[TAT_CA_TT, *STATUSES], width=160,
                                               command=lambda _v: self.refresh())
        self.status_filter.pack(side="left")

        ctk.CTkCheckBox(filters, text="Hiện mật khẩu", variable=self._show_secrets,
                        command=self.refresh).pack(side="left", padx=12)

        self.count_label = ctk.CTkLabel(filters, text="", text_color="gray60")
        self.count_label.pack(side="right", padx=6)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=PAD, pady=(0, PAD))
        bold = ctk.CTkFont(weight="bold")

        def button(text, command, color=None, width=118):
            kwargs = {"fg_color": color} if color else {}
            ctk.CTkButton(actions, text=text, width=width, command=command,
                          font=bold, **kwargs).pack(side="left", padx=3)

        button("➕ Thêm acc", self.add_account)
        button("📥 Nhập hàng loạt", self.bulk_import, width=140)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        button("▶ Mở", self.open_profiles, width=90)
        button("🔑 Cookie", self.login_cookie, width=105)
        button("⏹ Đóng", self.close_profiles, color="#7a5", width=90)
        button("🧩 Tạo profile", self.create_profiles, width=130)
        # O "Luong" RIENG cua tab X: so acc chay cung luc (cai NordVPN, dang nhap Google,
        # tao profile, check proxy...). Mac dinh 2 (nguoi dung chot 2026-09-28).
        ctk.CTkLabel(actions, text="Luồng", font=bold).pack(side="left", padx=(10, 4))
        self.threads_box = ctk.CTkOptionMenu(actions, values=[str(i) for i in range(1, 9)],
                                             width=64, font=bold, command=self._set_threads)
        self.threads_box.set(str(self._so_luong()))
        self.threads_box.pack(side="left")

    def _build_table(self) -> None:
        # Khu vuc bang chia 2 cot grid: cot 0 = bang acc, cot 1 = bang thong tin
        # acc (an san, bam mot dong moi hien) -- bo cuc y het tab Facebook.
        self._table_area = ctk.CTkFrame(self, fg_color="transparent")
        self._table_area.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self._table_area.grid_rowconfigure(0, weight=1)
        self._table_area.grid_columnconfigure(0, weight=1)

        wrapper = ctk.CTkFrame(self._table_area)
        wrapper.grid(row=0, column=0, sticky="nsew")

        self.tree = ttk.Treeview(wrapper, columns=[c[0] for c in X_COLUMNS],
                                 show="headings", selectmode="extended",
                                 # dung chung style bang Facebook -> doi mau sang/toi theo App
                                 style="Accounts.Treeview")
        for key, title, width, anchor in X_COLUMNS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor=anchor, stretch=False)

        vertical = ttk.Scrollbar(wrapper, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(wrapper, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", lambda _e: self.open_profiles())
        self.tree.bind("<<TreeviewSelect>>", self._on_row_selected)
        self.tree.bind("<Button-3>", self._popup_menu)
        # Keo chuot de quet chon nhieu dong (giong tab Facebook). Treeview khong co san.
        self._drag_anchor = None
        self.tree.bind("<Button-1>", self._drag_start)
        self.tree.bind("<B1-Motion>", self._drag_select)
        self.tree.bind("<Control-a>", self._select_all_rows)
        self.tree.bind("<Control-A>", self._select_all_rows)

    # ------------------------------------------------------------------
    # Bang chi tiet ben phai (nhu tab Facebook, doi nhan sang truong cua acc X)
    # ------------------------------------------------------------------
    def _build_detail(self) -> None:
        """Bang thong tin acc X, hien ra khi bam vao mot dong."""
        self._detail = ctk.CTkFrame(self._table_area, width=DETAIL_WIDTH)
        self._detail.grid_propagate(False)      # giu nguyen be ngang
        self._detail_account = None
        self._detail_fields: dict = {}
        self._detail_open = False

        head = ctk.CTkFrame(self._detail, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(10, 4))
        self._detail_title = ctk.CTkLabel(
            head, text="", anchor="w", font=ctk.CTkFont(size=14, weight="bold"))
        self._detail_title.pack(side="left")
        ctk.CTkButton(head, text="✕", width=28, fg_color="#a33", hover_color="#c44",
                      command=self.hide_detail).pack(side="right")

        body = ctk.CTkScrollableFrame(self._detail, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=6, pady=0)

        def row(label: str, key: str, height: int = 0):
            line = ctk.CTkFrame(body, fg_color="transparent")
            line.pack(fill="x", pady=(6, 0))
            ctk.CTkLabel(line, text=label, anchor="w", text_color="gray60",
                         font=ctk.CTkFont(size=11)).pack(side="left")
            ctk.CTkButton(
                line, text="⧉", width=26, height=18,
                fg_color="transparent", text_color="gray60", hover_color="gray30",
                command=lambda k=key: self._copy_detail(k),
            ).pack(side="right")
            widget = ctk.CTkTextbox(body, height=height) if height else ctk.CTkEntry(body)
            widget.pack(fill="x")
            self._detail_fields[key] = widget
            return widget

        # Thu tu khop cot bang: user/pass X roi chuoi Gmail, roi cookie/proxy.
        row("User X", "id")
        self._detail_fields["id"].configure(state="disabled")
        row("Pass X", "password")
        row("Gmail", "recovery_mail")
        row("Pass Gmail", "recovery_mail_password")
        row("Mail KP Gmail", "recovery_mail_backup")

        twofa = row("2FA Gmail (secret)", "gmail_2fa")
        self._detail_2fa = ctk.CTkLabel(body, text="", anchor="w", text_color="gray60",
                                        font=ctk.CTkFont(size=11))
        self._detail_2fa.pack(fill="x")
        twofa.bind("<KeyRelease>", lambda _e: self._tick_detail_2fa())

        row("Cookie X", "cookie")
        row("Proxy", "proxy")
        row("Nhóm", "group")

        ctk.CTkLabel(body, text="Trạng thái", anchor="w", text_color="gray60",
                     font=ctk.CTkFont(size=11)).pack(fill="x", pady=(6, 0))
        self._detail_status = ctk.CTkOptionMenu(body, values=list(STATUSES))
        self._detail_status.pack(fill="x")

        row("Ghi chú", "note", height=60)

        # Truong phu (user_agent, x_thua...) chi de xem va chep.
        self._detail_extra = ctk.CTkFrame(body, fg_color="transparent")
        self._detail_extra.pack(fill="x", pady=(10, 0))

        foot = ctk.CTkFrame(self._detail, fg_color="transparent")
        foot.pack(fill="x", padx=10, pady=8)
        ctk.CTkButton(foot, text="💾 Lưu", command=self.save_detail).pack(
            side="left", fill="x", expand=True)
        ctk.CTkButton(foot, text="▶ Mở", width=70, fg_color="#1f6aa5",
                      command=self.open_profiles).pack(side="left", padx=(6, 0))

        self._tick_detail_2fa()

    def _on_row_selected(self, _event=None) -> None:
        """Bam mot dong thi do thong tin sang bang ben phai (nhu tab Facebook)."""
        chon = self.selected()
        if len(chon) == 1:
            self.show_detail(chon[0])
        elif self._detail_open:
            self._detail_title.configure(text=f"{len(chon)} acc đang chọn")
            self._detail_account = None

    def show_detail(self, account: Account) -> None:
        """Do thong tin cua acc X vao bang ben phai va hien no ra."""
        self._detail_account = account
        self._detail_title.configure(text="@" + account.id)

        values = {
            "id": account.id,
            "password": account.password,
            "recovery_mail": account.recovery_mail,
            "recovery_mail_password": account.recovery_mail_password,
            "recovery_mail_backup": account.recovery_mail_backup,
            "gmail_2fa": str((account.extra or {}).get("gmail_2fa", "") or ""),
            "cookie": account.cookie,
            "proxy": account.get_proxy().as_text(),
            "group": account.group,
            "note": account.note,
        }
        for key, widget in self._detail_fields.items():
            text = values.get(key, "")
            if isinstance(widget, ctk.CTkTextbox):
                widget.delete("1.0", "end")
                widget.insert("1.0", text)
            else:
                # O User X bi khoa, phai mo ra moi ghi duoc roi khoa lai.
                locked = str(widget.cget("state")) == "disabled"
                if locked:
                    widget.configure(state="normal")
                widget.delete(0, "end")
                widget.insert(0, text)
                if locked:
                    widget.configure(state="disabled")

        self._fill_extra(account)
        self._detail_status.set(account.status or STATUSES[0])
        self._tick_detail_2fa()

        if not self._detail_open:
            self._table_area.grid_columnconfigure(1, minsize=DETAIL_WIDTH)
            self._detail.grid(row=0, column=1, sticky="nsew", padx=(PAD, 0))
            self._detail_open = True

    def hide_detail(self) -> None:
        self._detail.grid_remove()
        self._table_area.grid_columnconfigure(1, minsize=0)
        self._detail_open = False
        self._detail_account = None

    def _fill_extra(self, account: Account) -> None:
        """Liet ke truong phu con lai trong ``extra`` (tru 2FA da co o rieng)."""
        for child in self._detail_extra.winfo_children():
            child.destroy()
        items = [(k, str(v)) for k, v in sorted((account.extra or {}).items())
                 if k != "gmail_2fa" and str(v).strip()]
        if not items:
            return
        ctk.CTkLabel(self._detail_extra, text="Trường phụ từ file nhập", anchor="w",
                     text_color="gray60", font=ctk.CTkFont(size=11)).pack(fill="x")
        for key, value in items:
            line = ctk.CTkFrame(self._detail_extra, fg_color="transparent")
            line.pack(fill="x", pady=(4, 0))
            ctk.CTkLabel(line, text=key, anchor="w", width=90,
                         text_color="gray60", font=ctk.CTkFont(size=11)).pack(side="left")
            entry = ctk.CTkEntry(line)
            entry.insert(0, value)
            entry.configure(state="readonly")
            entry.pack(side="left", fill="x", expand=True)
            ctk.CTkButton(line, text="⧉", width=26,
                          fg_color="transparent", text_color="gray60", hover_color="gray30",
                          command=lambda v=value: self._chep(v)).pack(side="left")

    def _copy_detail(self, key: str) -> None:
        widget = self._detail_fields.get(key)
        if widget is None:
            return
        text = (widget.get("1.0", "end") if isinstance(widget, ctk.CTkTextbox)
                else widget.get()).strip()
        if not text:
            self.app.set_status("Ô này đang trống.")
            return
        self._chep(text)

    def _tick_detail_2fa(self) -> None:
        """Hien ma TOTP hien tai ngay duoi o secret, lam moi moi giay."""
        if not self.winfo_exists():
            return
        secret = ""
        if self._detail_fields:
            secret = self._detail_fields["gmail_2fa"].get().strip()
        if secret:
            try:
                self._detail_2fa.configure(
                    text=f"Mã hiện tại: {totp.generate(secret)}  ({totp.seconds_remaining()}s)")
            except Exception:      # noqa: BLE001 - secret dang go do
                self._detail_2fa.configure(text="secret không hợp lệ")
        else:
            self._detail_2fa.configure(text="")
        self.after(1000, self._tick_detail_2fa)

    def save_detail(self) -> None:
        """Ghi lai thay doi tu bang ben phai vao acc X."""
        account = self._detail_account
        if account is None:
            messagebox.showinfo("Lưu", "Chọn đúng một acc rồi hãy lưu.",
                                parent=self.winfo_toplevel())
            return

        text = lambda k: (  # noqa: E731
            self._detail_fields[k].get("1.0", "end")
            if isinstance(self._detail_fields[k], ctk.CTkTextbox)
            else self._detail_fields[k].get()
        ).strip()

        try:
            proxy = Proxy() if not text("proxy") else proxy_module.parse(text("proxy"))
        except ValueError as exc:
            messagebox.showerror("Proxy", str(exc), parent=self.winfo_toplevel())
            return

        account.password = text("password")
        account.recovery_mail = text("recovery_mail")
        account.recovery_mail_password = text("recovery_mail_password")
        account.recovery_mail_backup = text("recovery_mail_backup")
        account.group = text("group")
        account.note = text("note")
        account.cookie = text("cookie")
        account.status = self._detail_status.get()

        # 2FA Gmail nam trong extra, gon lai nhu edit_gmail_2fa.
        extra = dict(account.extra or {})
        gon = x_import.gon_2fa(text("gmail_2fa")) if text("gmail_2fa") else ""
        if gon:
            extra["gmail_2fa"] = gon
        else:
            extra.pop("gmail_2fa", None)
        account.extra = extra

        doi_proxy = proxy != account.get_proxy()
        if doi_proxy:
            account.set_proxy(proxy)
        self.store.save()
        self.refresh()
        if doi_proxy and self.manager.is_installed(account):
            # Ap proxy moi vao profile o luong nen (nhu change_proxy).
            def work():
                try:
                    self.manager.configure(account)
                except Exception:      # noqa: BLE001 - profile loi thi bo qua
                    pass
            self._chay_nen(work)
        self.show_detail(account)
        self.app.set_status(f"X.com: đã lưu @{account.id}.")

    def _make_menu(self) -> tk.Menu:
        """Menu chuot phai day du cho acc X (soi theo menu tab Facebook, doi truong X)."""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="▶ Mở profile", command=self.open_profiles)
        menu.add_command(label="🔑 Đăng nhập với cookie", command=self.login_cookie)
        menu.add_command(label="🟢 Đăng nhập Google (lấy cookie X)",
                         command=self.login_google_selected)
        menu.add_command(label="🛡 Cài NordVPN + đăng nhập", command=self.cai_nordvpn)
        menu.add_command(label="⏹ Đóng profile", command=self.close_profiles)
        menu.add_command(label="🧩 Tạo profile", command=self.create_profiles)

        # Doi User Agent: mot muc con moi category (iOS/Android/TV/Mac/Win...)
        ua_menu = tk.Menu(menu, tearoff=0)
        for ten in useragent.cac_loai().keys():
            ua_menu.add_command(label=ten, command=lambda l=ten: self.change_user_agent(l))
        ua_menu.add_separator()
        ua_menu.add_command(label="Xoá User Agent (dùng mặc định)",
                            command=lambda: self.change_user_agent(""))
        menu.add_cascade(label="🕶 Đổi user agent", menu=ua_menu)
        menu.add_separator()

        # Danh sach nhom doi theo thoi gian -> dung lai moi lan bung menu.
        self._group_menu = tk.Menu(menu, tearoff=0)
        menu.add_cascade(label="🗂 Chuyển vào nhóm", menu=self._group_menu)
        menu.add_command(label="🗂 Quản lý nhóm...", command=self.manage_groups)

        edit_menu = tk.Menu(menu, tearoff=0)
        edit_menu.add_command(label="Sửa tất cả...", command=self.edit_account)
        edit_menu.add_separator()
        edit_menu.add_command(label="Sửa User X", command=self.edit_id)
        edit_menu.add_command(label="Sửa Pass X",
                              command=lambda: self._edit_field("password", "Pass X"))
        edit_menu.add_command(label="Sửa Gmail",
                              command=lambda: self._edit_field("recovery_mail", "Gmail"))
        edit_menu.add_command(
            label="Sửa Pass Gmail",
            command=lambda: self._edit_field("recovery_mail_password", "Pass Gmail"))
        edit_menu.add_command(
            label="Sửa Mail KP Gmail",
            command=lambda: self._edit_field("recovery_mail_backup", "Mail KP Gmail"))
        edit_menu.add_command(label="Sửa 2FA Gmail", command=self.edit_gmail_2fa)
        edit_menu.add_command(label="Sửa Cookie X...", command=self.edit_cookie)
        edit_menu.add_command(label="Sửa proxy...", command=self.change_proxy)
        edit_menu.add_separator()
        edit_menu.add_command(label="Sửa nhóm",
                              command=lambda: self._edit_field("group", "Nhóm"))
        edit_menu.add_command(
            label="Sửa trạng thái",
            command=lambda: self._edit_field("status", "Trạng thái", options=list(STATUSES)))
        edit_menu.add_command(label="Sửa ghi chú...",
                              command=lambda: self._edit_field("note", "Ghi chú", multiline=True))
        edit_menu.add_separator()
        edit_menu.add_command(label="Xoá cookie đã lưu", command=self.clear_cookie_field)
        menu.add_cascade(label="✏️ Sửa", menu=edit_menu)
        menu.add_separator()

        menu.add_command(label="🌐 Đổi proxy...", command=self.change_proxy)
        check_menu = tk.Menu(menu, tearoff=0)
        check_menu.add_command(label="Check proxy", command=self.check_proxies)
        check_menu.add_command(label="Check cookie", command=self.check_cookies)
        menu.add_cascade(label="🔍 Check", menu=check_menu)
        menu.add_separator()

        copy_menu = tk.Menu(menu, tearoff=0)
        copy_menu.add_command(label="User X", command=lambda: self._copy_field("id"))
        copy_menu.add_command(label="Pass X", command=lambda: self._copy_field("password"))
        copy_menu.add_command(label="Gmail", command=lambda: self._copy_field("recovery_mail"))
        copy_menu.add_command(label="Pass Gmail",
                              command=lambda: self._copy_field("recovery_mail_password"))
        copy_menu.add_command(label="Mã 2FA Gmail (hiện tại)", command=self.copy_gmail_2fa)
        copy_menu.add_command(label="Cookie X", command=lambda: self._copy_field("cookie"))
        copy_menu.add_separator()
        copy_menu.add_command(label="Ghi chú", command=lambda: self._copy_field("note"))
        menu.add_cascade(label="📋 Copy", menu=copy_menu)
        menu.add_separator()

        menu.add_command(label="Mở thư mục profile", command=self.open_folder)
        menu.add_command(label="🧽 Xoá cache trình duyệt", command=self.clear_cache)
        menu.add_command(label="💾 Lưu cookie từ profile vào acc",
                         command=self.save_cookie_from_profile)
        menu.add_command(label="Xuất cookie từ profile", command=self.export_cookie)
        menu.add_separator()
        menu.add_command(label="🗑 Xoá acc", command=self.delete_accounts)
        return menu

    def _rebuild_group_menu(self) -> None:
        """Dung lai menu con "Chuyen vao nhom" theo danh sach nhom hien tai."""
        self._group_menu.delete(0, "end")
        current = {a.group.strip() for a in self.selected()}
        self._group_menu.add_command(label="➕ Nhóm mới...", command=self.assign_new_group)
        self._group_menu.add_command(label="✖ Bỏ khỏi nhóm",
                                     command=lambda: self.assign_group(""))
        groups = self.store.groups()
        if groups:
            self._group_menu.add_separator()
        for name in groups:
            mark = "● " if current == {name} else "○ "
            self._group_menu.add_command(label=mark + name,
                                         command=lambda n=name: self.assign_group(n))

    def _popup_menu(self, event) -> None:
        item = self.tree.identify_row(event.y)
        if item and item not in self.tree.selection():
            self.tree.selection_set(item)
        self._rebuild_group_menu()
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # ---- du lieu ------------------------------------------------------
    def refresh(self) -> None:
        groups = self.store.groups()
        self.group_filter.configure(values=[TAT_CA_NHOM, *groups])
        if self.group_filter.get() not in (TAT_CA_NHOM, *groups):
            self.group_filter.set(TAT_CA_NHOM)
        group = self.group_filter.get()
        status = self.status_filter.get()
        self._rows = self.store.search(
            keyword=self.search_entry.get(),
            group="" if group == TAT_CA_NHOM else group,
            status="" if status == TAT_CA_TT else status,
        )
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        for index, account in enumerate(self._rows, start=1):
            self.tree.insert("", "end", iid=account.id, values=self.row_values(index, account))
        for item in selected:
            if self.tree.exists(item):
                self.tree.selection_add(item)
        self.count_label.configure(text=f"{len(self._rows)}/{len(self.store)} acc")

    def row_values(self, index: int, account: Account) -> tuple:
        """Gia tri tung o, dung thu tu X_COLUMNS."""
        show = self._show_secrets.get()
        installed = self.manager.is_installed(account)
        def an(value: str) -> str:
            value = value or ""
            if show:
                return value or "—"
            return "•" * min(len(value), 10) or "—"

        cells = {
            "stt": index,
            "id": account.id,
            "password": an(account.password),
            "gmail": account.recovery_mail or "—",
            "gmail_pass": an(account.recovery_mail_password),
            "gmail_kp": account.recovery_mail_backup or "—",
            "gmail_2fa": "có" if (account.extra or {}).get("gmail_2fa") else "—",
            "group": account.group or "—",
            "profile": "đã tạo" if installed else "chưa tạo",
            "cookie": "có" if (account.cookie or "").strip() else "—",
            "running": "▶" if installed and self.manager.is_running(account) else "",
            "status": account.status or "—",
            "proxy": account.get_proxy().display(mask=not show) or "—",
            "note": (account.note or "").replace(chr(10), " ")[:120],
        }
        return tuple(cells[key] for key, *_ in X_COLUMNS)

    def selected(self) -> list[Account]:
        ids = set(self.tree.selection())
        return [a for a in self._rows if a.id in ids]

    def _require_selection(self, single: bool = False) -> list[Account]:
        chon = self.selected()
        if not chon:
            messagebox.showinfo("Chưa chọn", "Hãy chọn ít nhất một acc X trong bảng.",
                                parent=self.winfo_toplevel())
            return []
        if single and len(chon) > 1:
            messagebox.showinfo("Chọn một acc", "Chức năng này chỉ áp dụng cho một acc.",
                                parent=self.winfo_toplevel())
            return []
        return chon

    def _chay_nen(self, work) -> None:
        """Chay work() o luong nen; loi -> bao qua app._post (luong chinh)."""
        def boc():
            try:
                work()
            except Exception as exc:     # noqa: BLE001 - bao loi ra thanh trang thai
                self.app._post(lambda: self.app.set_status(f"X.com: lỗi — {exc}"))
            finally:
                self.app._post(self.refresh)
        threading.Thread(target=boc, daemon=True).start()

    # ---- hanh dong ----------------------------------------------------
    def add_account(self) -> None:
        account = XAccountDialog(self.winfo_toplevel(), groups=self.store.groups()).show()
        if not account:
            return
        try:
            self.store.add(account)
        except ValueError as exc:
            messagebox.showerror("Không thêm được", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()
        self.app.set_status(f"X.com: đã thêm acc {account.id}.")

    def edit_account(self) -> None:
        chon = self._require_selection(single=True)
        if not chon:
            return
        original = chon[0]
        edited = XAccountDialog(self.winfo_toplevel(), account=original,
                                groups=self.store.groups()).show()
        if not edited:
            return
        try:
            self.store.update(original.id, edited)
        except ValueError as exc:
            messagebox.showerror("Không lưu được", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()
        self.app.set_status(f"X.com: đã lưu acc {edited.id}.")

    def bulk_import(self) -> None:
        result = XBulkImportDialog(self.winfo_toplevel(), groups=self.store.groups()).show()
        if not result:
            return
        text, sep, fields, group, ua_loai = result
        added, errors = x_import.nhap_vao_store(self.store, text, group, sep=sep,
                                                fields=fields, ua_loai=ua_loai)
        self.refresh()
        summary = f"Đã thêm {added} acc X" + (f" vào nhóm “{group}”" if group else "") + "."
        if errors:
            summary += "\n\nBỏ qua:\n" + "\n".join(errors[:15])
            if len(errors) > 15:
                summary += f"\n... và {len(errors) - 15} dòng nữa."
        messagebox.showinfo("Nhập hàng loạt (X.com)", summary, parent=self.winfo_toplevel())

    def delete_accounts(self) -> None:
        chon = self._require_selection()
        if not chon:
            return
        names = ", ".join(a.id for a in chon[:5]) + (f" ... (+{len(chon) - 5})" if len(chon) > 5 else "")
        parent = self.winfo_toplevel()
        if not messagebox.askyesno("Xoá acc X", f"Xoá {len(chon)} acc khỏi danh sách X?\n{names}",
                                   parent=parent):
            return
        xoa_thu_muc = messagebox.askyesno(
            "Xoá thư mục", "Xoá luôn thư mục profile trên ổ đĩa?\n"
            "Chọn 'No' nếu chỉ muốn bỏ khỏi bảng.", parent=parent)
        for a in chon:
            if xoa_thu_muc:
                try:
                    self.manager.close(a, wait=3.0)
                except Exception:          # noqa: BLE001 - khong chay thi thoi
                    pass
                shutil.rmtree(self.manager.account_dir(a), ignore_errors=True)
            self.store.remove(a.id)
        self.refresh()
        self.app.set_status(f"X.com: đã xoá {len(chon)} acc.")

    def create_profiles(self) -> None:
        chon = self._require_selection()
        if not chon:
            return
        pending = [a for a in chon if not self.manager.is_installed(a)]
        if not pending:
            messagebox.showinfo("Tạo profile", "Các acc đã chọn đều có profile rồi.",
                                parent=self.winfo_toplevel())
            return

        def work():
            luong = max(1, min(self._so_luong(), len(pending)))

            def mot(a):
                self.app._post(lambda a=a: self.app.set_status(
                    f"X.com: tạo profile {a.id} ({luong} luồng)..."))
                self.manager.create(a)
            with ThreadPoolExecutor(max_workers=luong) as pool:
                list(pool.map(mot, pending))
            self.app._post(lambda: self.app.set_status(f"X.com: đã tạo {len(pending)} profile."))
        self._chay_nen(work)

    def open_profiles(self) -> None:
        chon = self._require_selection()
        if not chon:
            return

        def work():
            for a in chon:
                if not self.manager.is_installed(a):
                    self.app._post(lambda a=a: self.app.set_status(f"X.com: tạo profile {a.id}..."))
                    self.manager.create(a)
                self.manager.launch(a, url=X_START_URL)
                self.store.mark_opened(a.id)
            self.app._post(lambda: self.app.set_status(f"X.com: đã mở {len(chon)} profile."))
        self._chay_nen(work)

    def close_profiles(self) -> None:
        chon = self._require_selection()
        if not chon:
            return

        def work():
            for a in chon:
                if self.manager.is_installed(a):
                    self.manager.close(a, wait=3.0)
            self.app._post(lambda: self.app.set_status(f"X.com: đã đóng {len(chon)} profile."))
        self._chay_nen(work)

    # ---- dang nhap bang cookie -----------------------------------------
    def login_cookie(self) -> None:
        """Nap cookie da luu vao profile roi mo x.com/home.

        Acc chua co cookie thi bo qua va bao ten trong tom tat. Trinh duyet dang
        chay giu khoa cookies.sqlite nen phai dong truoc khi ghi.
        """
        chon = self._require_selection()
        if not chon:
            return
        co = [a for a in chon if (a.cookie or "").strip()]
        thieu = [a.id for a in chon if not (a.cookie or "").strip()]
        if not co:
            messagebox.showinfo("Đăng nhập với cookie",
                                "Các acc đã chọn chưa lưu cookie X.",
                                parent=self.winfo_toplevel())
            return

        def work():
            vao, loi = 0, []
            khoa = threading.Lock()

            def mot(a):
                nonlocal vao
                try:
                    if not self.manager.is_installed(a):
                        self.app._post(lambda a=a: self.app.set_status(
                            f"X.com: tạo profile {a.id}..."))
                        self.manager.create(a)
                    if self.manager.is_running(a):
                        self.manager.close(a, wait=3.0)
                    ck = cookie_module.parse(a.cookie, default_domain=X_COOKIE_DOMAIN)
                    if not ck:
                        with khoa:
                            loi.append(f"{a.id}: không đọc được cookie nào")
                        return
                    cookie_module.write_to_profile(self.manager.profile_dir(a), ck)
                    self.manager.launch(a, url=X_HOME_URL)
                    with khoa:
                        self.store.mark_opened(a.id)
                        vao += 1
                except Exception as exc:          # noqa: BLE001 - acc nay loi thi lam acc khac
                    with khoa:
                        loi.append(f"{a.id}: {exc}")
            with ThreadPoolExecutor(max_workers=max(1, min(self._so_luong(), len(co)))) as pool:
                list(pool.map(mot, co))
            tin = f"X.com: nạp cookie + mở {vao}/{len(co)} acc."
            if thieu:
                tin += (f" Bỏ qua {len(thieu)} acc chưa có cookie: "
                        + ", ".join(thieu[:5]) + ("..." if len(thieu) > 5 else "") + ".")
            if loi:
                tin += " Lỗi: " + "; ".join(loi[:3])
            self.app._post(lambda: self.app.set_status(tin))
        self._chay_nen(work)

    def login_google_selected(self) -> None:
        """Đăng nhập X.com bằng Google cho các acc đã chọn → lưu cookie X mới.

        Mở x.com → bấm "Đăng nhập bằng Google" → điền Gmail/pass/2FA (agent) → về X.
        Cần Gmail + Pass Gmail; acc thiếu bị bỏ qua và nêu tên trong tóm tắt.
        """
        from core import xlogin
        chon = self._require_selection()
        if not chon:
            return
        du = [a for a in chon
              if (a.recovery_mail or "").strip() and (a.recovery_mail_password or "").strip()]
        thieu = [a.id for a in chon if a not in du]
        if not du:
            messagebox.showinfo(
                "Đăng nhập Google",
                "Các acc đã chọn chưa có Gmail hoặc Pass Gmail.\n"
                "Nhập ở cột Gmail / Pass Gmail rồi thử lại.",
                parent=self.winfo_toplevel())
            return
        workers = self._so_luong()

        def work():
            def on_xong(a, kq):
                # Luu ngay sau moi acc: cookie moi khoi mat neu dong tool giua chung.
                try:
                    self.store.save()
                except Exception:  # noqa: BLE001
                    pass
                self.app._post(self.refresh)

            kq = xlogin.login_nhieu(
                self.manager, du, workers=workers,
                log=lambda m: self.app._post(lambda m=m: self.app.set_status(m)),
                on_xong=on_xong)
            try:
                self.store.save()
            except Exception:  # noqa: BLE001
                pass

            def bao():
                self.refresh()
                tin = (f"Đăng nhập Google: {len(kq['vao'])}/{kq['so']} acc vào, "
                       f"đã lưu cookie X.")
                if kq["khong"]:
                    tin += " Chưa vào: " + ", ".join(kq["khong"][:5])
                    if len(kq["khong"]) > 5:
                        tin += "..."
                if thieu:
                    tin += (f"\nBỏ qua {len(thieu)} acc thiếu Gmail/Pass Gmail: "
                            + ", ".join(thieu[:5]) + ("..." if len(thieu) > 5 else ""))
                messagebox.showinfo("Đăng nhập Google", tin,
                                    parent=self.winfo_toplevel())
            self.app._post(bao)
        self._chay_nen(work)

    # ---- keo chuot chon nhieu dong (giong tab Facebook) -----------------
    SHIFT_HELD = 0x0001
    CTRL_HELD = 0x0004

    def _drag_start(self, event) -> None:
        """Ghi lai dong bam xuong lam moc cho thao tac keo chon."""
        if self.tree.identify_region(event.x, event.y) in ("heading", "separator"):
            self._drag_anchor = None
            return
        # Giu Ctrl/Shift -> de Treeview tu xu ly (cong don / chon khoang).
        if event.state & (self.SHIFT_HELD | self.CTRL_HELD):
            self._drag_anchor = None
            return
        self._drag_anchor = self.tree.identify_row(event.y)

    def _drag_select(self, event) -> None:
        """Keo chuot: chon tat ca dong tu moc toi dong duoi con tro."""
        if not self._drag_anchor:
            return
        current = self.tree.identify_row(event.y)
        if not current:
            return
        items = self.tree.get_children("")
        try:
            lo, hi = sorted((items.index(self._drag_anchor), items.index(current)))
        except ValueError:
            return
        self.tree.selection_set(items[lo:hi + 1])
        self.tree.see(current)          # keo toi bien thi cuon theo

    def _select_all_rows(self, _event=None):
        self.tree.selection_set(self.tree.get_children(""))
        return "break"

    # ---- NordVPN -------------------------------------------------------
    def cai_nordvpn(self) -> None:
        """Cai addon NordVPN vao profile cac acc dang chon roi dang nhap NordVPN.

        Hoi user + pass NordVPN (luu vao Settings), tai .xpi da ky tu AMO,
        cai vao tung profile (tao profile khi thieu, dong trinh duyet dang chay),
        roi dang nhap NordVPN tung acc (tru khi tich "Chỉ cài addon").
        """
        chon = self._require_selection()
        if not chon:
            return
        # Tai danh sach quoc gia (co cache sau lan dau; loi van mo hop thoai mac dinh).
        try:
            quoc_gia_list = self._nord_countries
        except AttributeError:
            try:
                quoc_gia_list = nordvpn.tai_quoc_gia()
            except Exception:                 # noqa: BLE001 - loi mang van mo hop thoai
                quoc_gia_list = []
            self._nord_countries = quoc_gia_list
        result = NordVpnDialog(self.winfo_toplevel(), self.app.settings,
                               quoc_gia_list=quoc_gia_list).show()
        if not result:
            return
        user, pw, chi_cai, quoc_gia, bang = result
        # Luu tai khoan dung chung + vi tri vao Settings.
        self.app.settings.nordvpn_user = user
        self.app.settings.nordvpn_pass = pw
        self.app.settings.nordvpn_country = quoc_gia
        self.app.settings.nordvpn_state = bang
        try:
            self.app.settings.save()
        except Exception:                     # noqa: BLE001 - luu loi thi van chay
            pass

        def work():
            noi = lambda m: self.app._post(lambda m=m: self.app.set_status(m))  # noqa: E731
            try:
                xpi, guid, ver = nordvpn.tai_xpi(log=noi)
            except RuntimeError as exc:
                self.app._post(lambda: self.app.set_status(f"X.com: {exc}"))
                self.app._post(lambda: messagebox.showerror(
                    "NordVPN", str(exc), parent=self.winfo_toplevel()))
                return

            # CHAY NHIEU ACC CUNG LUC theo o "Luong" cua tab X (moi acc 1 Firefox rieng).
            luong = max(1, min(self._so_luong(), len(chon)))
            noi(f"X.com: NordVPN {len(chon)} acc — {luong} luồng cùng lúc...")
            xong = []

            def mot_xong(kq):
                xong.append(kq)
                noi(f"X.com: NordVPN {len(xong)}/{len(chon)} xong — {kq['id']}: "
                    f"{'OK' if kq['ok'] else 'lỗi'} {kq.get('detail', '')[:60]}")

            ket = nordvpn.chay_nhieu(self.manager, chon, xpi=xpi, user=user, mat_khau=pw,
                                     quoc_gia=quoc_gia, bang=bang, quoc_gia_list=quoc_gia_list,
                                     chi_cai=chi_cai, workers=luong, log=noi, on_row=mot_xong)
            cai = sum(1 for k in ket if k["cai"])
            vao = sum(1 for k in ket if k["ok"])
            loi = [f"{k['id']}: {k['detail']}" for k in ket if not k["cai"]]
            dn_loi = [f"{k['id']}: {k['detail']}" for k in ket if k["cai"] and not k["ok"]]
            dat = [f"{k['id']}: {k['vi_tri'] or quoc_gia}" for k in ket if k["ok"] and not chi_cai]

            def bao():
                tin = f"Đã cài NordVPN cho {cai}/{len(chon)} acc (v{ver})."
                if not chi_cai:
                    vi_tri = f"{quoc_gia} / {bang}" if bang else f"{quoc_gia} / mặc định"
                    tin += (f"\nĐã nối VPN + bật Spoofing + Kill switch: {vao}/{len(chon)} acc."
                            f"\nVị trí: {vi_tri}.")
                    if dat:
                        tin += "\n" + "\n".join(dat[:8])
                if loi:
                    tin += "\n\nLỗi cài:\n" + "\n".join(loi[:5])
                    if len(loi) > 5:
                        tin += f"\n... và {len(loi) - 5} acc nữa."
                if dn_loi:
                    tin += "\n\nLỗi đăng nhập:\n" + "\n".join(dn_loi[:5])
                    if len(dn_loi) > 5:
                        tin += f"\n... và {len(dn_loi) - 5} acc nữa."
                messagebox.showinfo("NordVPN", tin, parent=self.winfo_toplevel())
                self.refresh()
            self.app._post(bao)
        self._chay_nen(work)

    # ---- user agent ----------------------------------------------------
    def change_user_agent(self, loai: str) -> None:
        """Gan UA ngau nhien theo category cho cac acc dang chon; rong = xoa UA."""
        chon = self._require_selection()
        if not chon:
            return
        if loai and not useragent.doc_loai(loai):
            messagebox.showinfo("Đổi user agent", f"Category “{loai}” chưa có UA nào.",
                                parent=self.winfo_toplevel())
            return
        doi = 0
        for a in chon:
            extra = dict(a.extra or {})
            if loai:
                ua = useragent.chon_ngau_nhien(loai)
                if not ua:
                    continue
                extra["user_agent"] = ua
            else:
                extra.pop("user_agent", None)
            a.extra = extra
            doi += 1
        self.store.save()
        self.refresh()
        can_ap = [a for a in chon if self.manager.is_installed(a)]
        nhan = f"category “{loai}”" if loai else "mặc định (đã xoá UA)"
        self.app.set_status(f"X.com: đã đổi user agent {doi} acc — {nhan}.")
        if not can_ap:
            return

        def work():
            for a in can_ap:
                try:
                    self.manager.configure(a)
                except Exception:              # noqa: BLE001 - profile loi thi bo qua acc do
                    pass
            self.app._post(lambda: self.app.set_status(
                f"X.com: đã áp user agent vào {len(can_ap)} profile "
                "(acc đang mở phải mở lại mới thấy)."))
        self._chay_nen(work)

    # ---- nhom ----------------------------------------------------------
    def assign_group(self, name: str) -> None:
        """Chuyen cac acc dang chon sang nhom ``name``; rong = bo khoi nhom."""
        chon = self._require_selection()
        if not chon:
            return
        moved = self.store.assign_group([a.id for a in chon], name)
        self.refresh()
        if not name:
            self.app.set_status(f"X.com: đã bỏ {moved} acc khỏi nhóm.")
        else:
            self.app.set_status(f"X.com: đã chuyển {moved} acc vào nhóm “{name}”.")

    def assign_new_group(self) -> None:
        chon = self._require_selection()
        if not chon:
            return
        name = SimplePromptDialog(self.winfo_toplevel(), "Nhóm mới",
                                  f"Tên nhóm cho {len(chon)} acc X đang chọn:").show()
        if not name:
            return
        try:
            name = self.store.add_group(name)
        except ValueError as exc:
            messagebox.showerror("Không tạo được nhóm", str(exc),
                                 parent=self.winfo_toplevel())
            return
        self.assign_group(name)

    def manage_groups(self) -> None:
        if GroupManagerDialog(self.winfo_toplevel(), self.store).show():
            self.refresh()
            self.app.set_status("X.com: đã cập nhật danh sách nhóm.")

    # ---- sua tung truong ------------------------------------------------
    def _edit_field(self, key: str, label: str, multiline: bool = False,
                    options=None) -> None:
        """Sua nhanh MOT truong cho cac acc dang chon (de trong = xoa gia tri)."""
        chon = self._require_selection()
        if not chon:
            return
        values = [str(getattr(a, key, "") or "") for a in chon]
        result = FieldEditDialog(self.winfo_toplevel(), chon, "Sửa " + label.lower(),
                                 label, values, multiline=multiline, options=options).show()
        if result is None:
            return                     # bam Huy; de trong van la thay doi hop le
        doi = 0
        for a in chon:
            if str(getattr(a, key, "") or "") != result:
                setattr(a, key, result)
                doi += 1
        self.store.save()
        self.refresh()
        self.app.set_status(f"X.com: đã sửa {label.lower()} cho {doi} acc."
                            if doi else f"X.com: {label.lower()} vẫn như cũ.")

    def edit_gmail_2fa(self) -> None:
        """Sua khoa 2FA Gmail (nam trong extra["gmail_2fa"]), tu gon lai khoang trang."""
        chon = self._require_selection()
        if not chon:
            return
        values = [str((a.extra or {}).get("gmail_2fa", "") or "") for a in chon]
        result = FieldEditDialog(self.winfo_toplevel(), chon, "Sửa 2FA Gmail",
                                 "Khoá 2FA Gmail", values).show()
        if result is None:
            return
        gon = x_import.gon_2fa(result) if result else ""
        doi = 0
        for a in chon:
            extra = dict(a.extra or {})
            cu = str(extra.get("gmail_2fa", "") or "")
            if gon:
                extra["gmail_2fa"] = gon
            else:
                extra.pop("gmail_2fa", None)
            if cu != gon:
                doi += 1
            a.extra = extra
        self.store.save()
        self.refresh()
        self.app.set_status(f"X.com: đã sửa 2FA Gmail cho {doi} acc.")

    def edit_id(self) -> None:
        """Doi User X (id) -- la khoa phan biet acc nen chi sua mot acc moi lan."""
        chon = self._require_selection(single=True)
        if not chon:
            return
        account = chon[0]
        parent = self.winfo_toplevel()
        moi = FieldEditDialog(parent, chon, "Sửa User X", "User X", [account.id]).show()
        if moi is None or moi == account.id:
            return
        if not moi:
            messagebox.showerror("Sửa User X", "User X không được để trống.", parent=parent)
            return
        if any(a is not account and a.id == moi for a in self.store.accounts):
            messagebox.showerror("Sửa User X", f"Đã có acc mang User X “{moi}”.", parent=parent)
            return
        cu = account.id
        account.id = moi
        self.store.save()
        self.refresh()
        self.app.set_status(f"X.com: đã đổi {cu} → {moi} "
                            "(thư mục profile cũ vẫn mang tên cũ).")

    def edit_cookie(self) -> None:
        """Xem / sua cookie X cua mot acc, co the nap luon vao profile."""
        chon = self._require_selection(single=True)
        if not chon:
            return
        account = chon[0]
        parent = self.winfo_toplevel()
        dang_co = 0
        if self.manager.is_installed(account):
            dang_co = len(cookie_module.read_from_profile(self.manager.profile_dir(account)))
        dlg = CookieDialog(parent, account, dang_co)
        # Hop thoai dung chung voi Facebook -> doi domain mac dinh sang X.
        dlg.domain_entry.delete(0, "end")
        dlg.domain_entry.insert(0, X_COOKIE_DOMAIN)
        result = dlg.show()
        if not result:
            return
        account.cookie = result["text"]
        self.store.save()
        self.refresh()
        if not result["apply"]:
            self.app.set_status(f"X.com: đã lưu cookie của {account.id}.")
            return
        domain = result["domain"] or X_COOKIE_DOMAIN
        replace = bool(result["replace"])

        def work():
            if not self.manager.is_installed(account):
                self.manager.create(account)
            if self.manager.is_running(account):
                self.manager.close(account, wait=3.0)
            ck = cookie_module.parse(account.cookie, default_domain=domain)
            so = cookie_module.write_to_profile(self.manager.profile_dir(account), ck,
                                               replace_all=replace)
            self.app._post(lambda: self.app.set_status(
                f"X.com: đã nạp {so} cookie vào profile {account.id}."))
        self._chay_nen(work)

    def clear_cookie_field(self) -> None:
        chon = self._require_selection()
        if not chon:
            return
        if not messagebox.askyesno("Xoá cookie đã lưu",
                                   f"Xoá cookie đã lưu của {len(chon)} acc X?\n"
                                   "Cookie trong profile KHÔNG bị xoá.",
                                   parent=self.winfo_toplevel()):
            return
        for a in chon:
            a.cookie = ""
        self.store.save()
        self.refresh()
        self.app.set_status(f"X.com: đã xoá cookie đã lưu của {len(chon)} acc.")

    # ---- proxy ---------------------------------------------------------
    def change_proxy(self) -> None:
        """Doi proxy cho cac acc dang chon (dung mot gia tri cho ca nhom)."""
        chon = self._require_selection()
        if not chon:
            return
        dang_mo = any(self.manager.is_installed(a) and self.manager.is_running(a)
                      for a in chon)
        proxy = ProxyDialog(self.winfo_toplevel(), chon[0], dang_mo).show()
        if proxy is None:
            return
        for a in chon:
            a.set_proxy(proxy)
        self.store.save()
        self.refresh()
        can_ap = [a for a in chon if self.manager.is_installed(a)]
        self.app.set_status(f"X.com: đã đổi proxy cho {len(chon)} acc.")
        if not can_ap:
            return

        def work():
            for a in can_ap:
                try:
                    self.manager.configure(a)
                except Exception:              # noqa: BLE001 - profile loi thi bo qua
                    pass
            self.app._post(lambda: self.app.set_status(
                f"X.com: đã áp proxy vào {len(can_ap)} profile."))
        self._chay_nen(work)

    # ---- check ---------------------------------------------------------
    def check_proxies(self) -> None:
        """Test proxy tung acc, ghi Live/Die vao acc (proxy_status/proxy_checked)."""
        chon = self._require_selection()
        if not chon:
            return
        targets = [a for a in chon if a.get_proxy().enabled]
        if not targets:
            messagebox.showinfo("Check proxy", "Các acc đã chọn chưa gán proxy.",
                                parent=self.winfo_toplevel())
            return
        luong = max(1, min(self._so_luong(), len(targets)))
        self.app.set_status(f"X.com: check proxy {len(targets)} acc ({luong} luồng)...")

        def work():
            from core.proxy_relay import test_proxy

            def mot(a):
                try:
                    ok, detail = test_proxy(a.get_proxy())
                except Exception as exc:       # noqa: BLE001 - tinh la die
                    ok, detail = False, str(exc)
                a.proxy_status = "Live" if ok else "Die"
                a.proxy_checked = time.strftime("%Y-%m-%d %H:%M")
                return ok, detail
            with ThreadPoolExecutor(max_workers=luong) as pool:
                ket = list(pool.map(mot, targets))
            song = sum(1 for ok, _ in ket if ok)
            self.store.save()
            self.app._post(lambda: self.app.set_status(
                f"X.com: proxy sống {song}/{len(targets)} acc."))
        self._chay_nen(work)

    def check_cookies(self) -> None:
        """Xem cookie da luu co du cho X khong (khong ra mang, khong doi trang thai)."""
        chon = self._require_selection()
        if not chon:
            return
        dong, du, thieu = [], 0, 0
        for a in chon:
            raw = (a.cookie or "").strip()
            if not raw:
                dong.append(f"{a.id}: chưa có cookie")
                thieu += 1
                continue
            try:
                ck = cookie_module.parse(raw, default_domain=X_COOKIE_DOMAIN)
            except Exception as exc:           # noqa: BLE001 - cookie sai dinh dang
                dong.append(f"{a.id}: không đọc được ({exc})")
                thieu += 1
                continue
            cua_x = [c for c in ck
                     if any(c.host.lstrip(".").endswith(h) for h in X_COOKIE_HOSTS)]
            co_auth = any(c.name == X_AUTH_COOKIE for c in cua_x)
            if co_auth:
                du += 1
            else:
                thieu += 1
            dong.append(f"{a.id}: {len(cua_x)} cookie x.com/twitter.com — "
                        + ("có auth_token" if co_auth else "THIẾU auth_token"))
        tin = (f"Có auth_token: {du}/{len(chon)} acc. Thiếu/không đọc được: {thieu}.\n\n"
               + "\n".join(dong[:25]))
        if len(dong) > 25:
            tin += f"\n... và {len(dong) - 25} acc nữa."
        tin += "\n\n(Chỉ đọc cookie đã lưu — không kiểm tra acc còn sống hay không.)"
        messagebox.showinfo("Check cookie X", tin, parent=self.winfo_toplevel())
        self.app.set_status(f"X.com: cookie có auth_token {du}/{len(chon)} acc.")

    # ---- copy ----------------------------------------------------------
    def _chep(self, text: str) -> None:
        top = self.winfo_toplevel()
        top.clipboard_clear()
        top.clipboard_append(text)

    def _copy_field(self, field: str) -> None:
        chon = self.selected()
        if not chon:
            self._require_selection()
            return
        self._chep("\n".join(str(getattr(a, field, "") or "") for a in chon))
        self.app.set_status(f"X.com: đã copy {field} của {len(chon)} acc.")

    def copy_gmail_2fa(self) -> None:
        """Copy ma 2FA Gmail dang co hieu luc (sinh offline tu khoa da luu)."""
        chon = self._require_selection()
        if not chon:
            return
        ma, loi = [], []
        for a in chon:
            key = str((a.extra or {}).get("gmail_2fa", "") or "").strip()
            if not key:
                loi.append(f"{a.id}: chưa lưu khoá 2FA Gmail")
                continue
            try:
                ma.append(totp.generate(key))
            except Exception:                  # noqa: BLE001 - khoa sai dinh dang
                loi.append(f"{a.id}: khoá 2FA không hợp lệ")
        parent = self.winfo_toplevel()
        if not ma:
            messagebox.showerror("Mã 2FA Gmail", "\n".join(loi) or "Không có mã nào.",
                                 parent=parent)
            return
        self._chep("\n".join(ma))
        tin = f"X.com: đã copy {len(ma)} mã 2FA Gmail (còn {totp.seconds_remaining()}s)."
        if loi:
            messagebox.showwarning("Mã 2FA Gmail",
                                   f"Đã copy {len(ma)} mã. Bỏ qua:\n" + "\n".join(loi[:10]),
                                   parent=parent)
        self.app.set_status(tin)

    # ---- thu muc / cache / cookie tu profile ---------------------------
    def open_folder(self) -> None:
        chon = self._require_selection(single=True)
        if not chon:
            return
        target = self.manager.account_dir(chon[0])
        if not os.path.isdir(target):
            messagebox.showinfo("Thư mục", "Thư mục chưa tồn tại.",
                                parent=self.winfo_toplevel())
            return
        os.startfile(os.path.normpath(target))     # noqa: S606 - mo Explorer tren Windows

    def clear_cache(self) -> None:
        """Xoa cache2/startupCache trong profile; acc dang mo thi bo qua (file bi khoa)."""
        chon = self._require_selection()
        if not chon:
            return
        co_profile = [a for a in chon if self.manager.is_installed(a)]
        if not co_profile:
            messagebox.showinfo("Xoá cache", "Các acc đã chọn chưa tạo profile.",
                                parent=self.winfo_toplevel())
            return
        dang_mo = [a.id for a in co_profile if self.manager.is_running(a)]
        lam = [a for a in co_profile if a.id not in set(dang_mo)]
        cau_hoi = f"Xoá cache trình duyệt của {len(lam)} acc?\nĐăng nhập và cookie giữ nguyên."
        if dang_mo:
            cau_hoi += (f"\n\n{len(dang_mo)} acc đang mở sẽ bị bỏ qua:\n"
                        + ", ".join(dang_mo[:8]))
        if not lam:
            messagebox.showinfo("Xoá cache", cau_hoi, parent=self.winfo_toplevel())
            return
        if not messagebox.askyesno("Xoá cache", cau_hoi, parent=self.winfo_toplevel()):
            return

        def work():
            xoa = 0
            for a in lam:
                profile = self.manager.profile_dir(a)
                for ten in X_CACHE_DIRS:
                    duong = os.path.join(profile, ten)
                    if os.path.isdir(duong):
                        shutil.rmtree(duong, ignore_errors=True)
                        if not os.path.isdir(duong):
                            xoa += 1
            tin = f"X.com: đã xoá {xoa} thư mục cache của {len(lam)} acc."
            if dang_mo:
                tin += f" Bỏ qua {len(dang_mo)} acc đang mở."
            self.app._post(lambda: self.app.set_status(tin))
        self._chay_nen(work)

    def save_cookie_from_profile(self) -> None:
        """Doc cookie song trong profile ghi nguoc vao acc (dang "ten=gia_tri; ...")."""
        chon = self._require_selection()
        if not chon:
            return
        co_profile = [a for a in chon if self.manager.is_installed(a)]
        if not co_profile:
            messagebox.showinfo("Lưu cookie", "Các acc đã chọn chưa có profile.",
                                parent=self.winfo_toplevel())
            return
        luu, rong, dang_mo = 0, [], []
        for a in co_profile:
            if self.manager.is_running(a):
                dang_mo.append(a.id)
            found = cookie_module.read_from_profile(self.manager.profile_dir(a))
            cua_x = [c for c in found
                     if c.name and any(c.host.lstrip(".").endswith(h) for h in X_COOKIE_HOSTS)]
            if not any(c.name == X_AUTH_COOKIE for c in cua_x):
                rong.append(a.id)
                continue
            a.cookie = "; ".join(f"{c.name}={c.value}" for c in cua_x)
            luu += 1
        self.store.save()
        self.refresh()
        bao = f"Đã lưu cookie của {luu}/{len(co_profile)} acc."
        if rong:
            bao += ("\n\nChưa đăng nhập (không thấy auth_token), bỏ qua:\n"
                    + ", ".join(rong[:10]))
        if dang_mo:
            bao += ("\n\nĐang mở nên cookie có thể chưa đầy đủ — đóng trình duyệt rồi "
                    "lưu lại cho chắc:\n" + ", ".join(dang_mo[:10]))
        if rong or dang_mo:
            messagebox.showwarning("Lưu cookie", bao, parent=self.winfo_toplevel())
        self.app.set_status("X.com: " + bao.splitlines()[0])

    def export_cookie(self) -> None:
        """Xuat cookie trong profile ra file JSON (dinh dang Cookie-Editor)."""
        chon = self._require_selection(single=True)
        if not chon:
            return
        account = chon[0]
        parent = self.winfo_toplevel()
        if not self.manager.is_installed(account):
            messagebox.showinfo("Xuất cookie", "Acc này chưa có profile.", parent=parent)
            return
        found = cookie_module.read_from_profile(self.manager.profile_dir(account))
        if not found:
            messagebox.showinfo("Xuất cookie", "Profile chưa có cookie nào.", parent=parent)
            return
        path = filedialog.asksaveasfilename(
            parent=parent, defaultextension=".json",
            initialfile=f"{account.folder}_x_cookies.json",
            filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(cookie_module.to_json(found))
        self.app.set_status(f"X.com: đã xuất {len(found)} cookie ra {path}.")

    # ---- tien ich ------------------------------------------------------
    def _so_luong(self) -> int:
        """So acc X chay CUNG LUC -- o "Luong" RIENG cua tab X (settings.x_threads, 1..8, mac dinh 2)."""
        try:
            return max(1, min(8, int(getattr(self.app.settings, "x_threads", 2) or 2)))
        except (TypeError, ValueError, AttributeError):
            return 2

    def _set_threads(self, value: str) -> None:
        try:
            self.app.settings.x_threads = max(1, min(8, int(value)))
            self.app.settings.save()
        except Exception:                      # noqa: BLE001 - luu loi thi van dung gia tri moi
            pass
        try:
            self.app.set_status(f"X.com: {self._so_luong()} luồng — số acc chạy cùng lúc.")
        except Exception:                      # noqa: BLE001
            pass
