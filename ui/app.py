"""Cua so chinh cua tool quan ly profile Firefox Portable."""

from __future__ import annotations

import ipaddress
import os
import queue
import re
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

import customtkinter as ctk

from core import config
from core import cookies as cookie_module
from core import geoip
from core import licensing
from core import proxy as proxy_module
from core import totp
from core.config import Settings
from core.profiles import ProfileError, ProfileManager
from core.proxy import Proxy
from core.proxy_relay import RelayManager, test_proxy
from core.store import Account, AccountStore, STATUSES

from . import login
from .dialogs import (
    AccountDialog,
    ColumnDialog,
    AccountPickerDialog,
    BulkImportDialog,
    BulkProxyDialog,
    CookieDialog,
    CopyCustomDialog,
    FieldEditDialog,
    GroupManagerDialog,
    NoteDialog,
    ProxyDialog,
    SettingsDialog,
    SimplePromptDialog,
)

PAD = 8
DETAIL_WIDTH = 340   # be ngang bang thong tin acc ben phai

# Treeview va tk.Menu khong tu doi mau theo customtkinter, phai to tay.
THEMES = {
    "light": {
        "row_bg": "#ffffff",
        "row_fg": "#1c1c1c",
        "head_bg": "#e9e9ec",
        "head_fg": "#2b2b2b",
        "head_hover": "#dadade",
        "selected": "#1f6aa5",
        "logged_bg": "#d9ead3",   # da dang nhap bang cookie
        "running_bg": "#cfe3f7",  # trinh duyet dang mo
        "missing_fg": "#8d8d8d",
        "grid": "#c9ccd2",        # duong ke o
        "menu_bg": "#fbfbfb",
        "menu_fg": "#1c1c1c",
    },
    "dark": {
        "row_bg": "#242424",
        "row_fg": "#e6e6e6",
        "head_bg": "#1b1b1b",
        "head_fg": "#d0d0d0",
        "head_hover": "#2a2a2a",
        "selected": "#1f6aa5",
        "logged_bg": "#1d3b2a",
        "running_bg": "#1e3550",
        "missing_fg": "#9a9a9a",
        "grid": "#3d3d3d",
        "menu_bg": "#242424",
        "menu_fg": "#e6e6e6",
    },
}

COLUMNS = (
    ("stt", "#", 44, "center"),
    ("id", "ID acc", 170, "w"),
    ("password", "Mật khẩu", 120, "w"),
    ("mail", "Mail khôi phục", 190, "w"),
    ("twofa", "2FA", 90, "center"),
    ("group", "Nhóm", 110, "w"),
    ("profile", "Profile", 90, "center"),
    ("cookie", "Cookie", 80, "center"),
    ("running", "Đang chạy", 85, "center"),
    ("status", "Trạng thái", 95, "center"),
    ("proxy", "Proxy", 210, "w"),
    ("note", "Ghi chú", 220, "w"),
    ("identity", "Múi giờ / Ngôn ngữ", 200, "w"),
)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_default_color_theme("blue")

        self.title("LVC Manager Profile")
        self.geometry("1500x820")
        self.minsize(1100, 600)
        self._set_window_icon()

        # Cong dang nhap: an cua so chinh, cho dang nhap tai khoan + key tool
        # xong moi dung giao dien. An truoc chu khong dung cua so goc rieng vi
        # Tk chi nen co mot goc (xem ui/login.py).
        self.withdraw()
        self.session = login.gate(self)
        if self.session is None:
            self.destroy()
            return

        self.settings = Settings.load()
        self.settings.save()  # ghi lai duong dan paf.exe tim duoc o lan chay dau
        ctk.set_appearance_mode(self.settings.appearance)
        self.store = AccountStore()
        self.relays = RelayManager()
        self.manager = ProfileManager(self.settings, self.relays)

        self._events: queue.Queue = queue.Queue()
        self._busy = False
        self._show_secrets = tk.BooleanVar(value=True)
        self._rows: list[Account] = []
        self._menus: list[tk.Menu] = []

        self._build_header()

        self._build_toolbar(self)
        self._build_table(self)
        self._build_detail()
        self._build_statusbar()
        self._apply_theme()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_events)
        self.refresh()
        self._schedule_running_check()
        self._show_after_login()

    def _show_after_login(self) -> None:
        """Hien cua so chinh sau khi qua cong dang nhap.

        Khong chi goi deiconify() la du: customtkinter ghi nho rang withdraw()
        da duoc goi TRUOC khi cua so kip hien lan dau, va trong mainloop() no
        an cua so mot lan nua de doi mau thanh tieu de roi chi hien lai neu co
        do chua bat. De nguyen thi tool chay nhung khong co cua so nao ca.
        Xoa co di de mainloop() di dung duong binh thuong (van doi mau tieu de
        theo sang/toi). Dat trong try vi day la thuoc tinh noi bo cua thu vien,
        ban khac co the bo -- luc do rieng deiconify() van du.
        """
        try:
            self._withdraw_called_before_window_exists = False
        except Exception:
            pass
        self.deiconify()

    # ------------------------------------------------------------------
    # Dung giao dien
    # ------------------------------------------------------------------
    def _set_window_icon(self) -> None:
        """Dat icon cua so + thanh tac vu bang logo LVC.

        Uu tien file .ico vi no chua san moi co (16 -> 256), Windows tu chon cai
        vua nhat. Chi khi thieu .ico moi vien den PNG: dung song song ca hai thi
        iconphoto de len iconbitmap va Tk cap nham co (da do: icon lon con 32px
        con icon nho lai thanh 256px).
        """
        ico = config.resource_path("assets", "logo.ico")
        if os.path.isfile(ico):
            try:
                self.iconbitmap(default=ico)
                return
            except Exception:
                pass

        try:
            from PIL import Image, ImageTk

            png = config.resource_path("assets", "logo_256.png")
            if os.path.isfile(png):
                # Phai giu tham chieu, neu khong anh bi thu gom rac va icon mat.
                self._icon_photo = ImageTk.PhotoImage(Image.open(png))
                self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0, height=56)
        header.pack(fill="x")

        # Logo LVC canh tieu de.
        try:
            from PIL import Image
            logo = Image.open(config.resource_path("assets", "logo.png"))
            self._logo_img = ctk.CTkImage(light_image=logo, dark_image=logo, size=(36, 36))
            ctk.CTkLabel(header, image=self._logo_img, text="").pack(
                side="left", padx=(14, 6), pady=8
            )
        except Exception:
            pass

        ctk.CTkLabel(
            header,
            text="LVC Manager Profile",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left", padx=(0, 8), pady=10)
        self.root_label = ctk.CTkLabel(header, text="", text_color="gray60")
        self.root_label.pack(side="left", padx=6)
        ctk.CTkButton(header, text="Cài đặt", width=90, command=self.open_settings).pack(
            side="right", padx=14
        )
        ctk.CTkButton(
            header, text="Đăng xuất", width=90, fg_color="gray50",
            hover_color="gray40", command=self.sign_out,
        ).pack(side="right", padx=(0, 4))

        self.account_label = ctk.CTkLabel(header, text="", text_color="gray60")
        self.account_label.pack(side="right", padx=8)
        self._update_account_label()

    def _update_account_label(self) -> None:
        """Ghi ten dang nhap va han key len header (doi lai sau khi dang nhap lai)."""
        info = licensing.summarize(self.session)
        self.account_label.configure(
            text=f"👤 {info['username']}   •   Hạn key: {info['expiry']}")

    def _build_toolbar(self, parent) -> None:
        filters = ctk.CTkFrame(parent, fg_color="transparent")
        filters.pack(fill="x", padx=PAD, pady=(PAD, 4))

        self.search_entry = ctk.CTkEntry(filters, placeholder_text="Tìm theo ID / mail / nhóm / ghi chú", width=320)
        self.search_entry.pack(side="left")
        self.search_entry.bind("<KeyRelease>", lambda _e: self.refresh())

        self.group_filter = ctk.CTkOptionMenu(filters, values=["Tất cả nhóm"], width=150, command=lambda _v: self.refresh())
        self.group_filter.pack(side="left", padx=6)

        self.status_filter = ctk.CTkOptionMenu(
            filters, values=["Tất cả trạng thái", *STATUSES], width=160, command=lambda _v: self.refresh()
        )
        self.status_filter.pack(side="left")

        ctk.CTkCheckBox(
            filters, text="Hiện mật khẩu", variable=self._show_secrets, command=self.refresh
        ).pack(side="left", padx=12)

        ctk.CTkButton(
            filters, text="🧱 Cột hiển thị", width=130, command=self.choose_columns,
        ).pack(side="left", padx=4)

        self.count_label = ctk.CTkLabel(filters, text="", text_color="gray60")
        self.count_label.pack(side="right", padx=6)

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.pack(fill="x", padx=PAD, pady=(0, PAD))

        bold = ctk.CTkFont(weight="bold")

        def button(text, command, color=None, width=118):
            kwargs = {"fg_color": color} if color else {}
            btn = ctk.CTkButton(actions, text=text, width=width, command=command,
                                font=bold, **kwargs)
            btn.pack(side="left", padx=3)
            return btn

        button("➕ Thêm acc", self.add_account)
        button("📥 Nhập hàng loạt", self.bulk_import, width=140)
        button("✏️ Sửa", self.edit_account, width=80)
        button("🧩 Tạo profile", self.create_profiles, color="#2f7d4f", width=130)
        button("🗂 Nhóm", self.manage_groups, width=95)
        button("🗑 Xoá", self.delete_accounts, color="#a33", width=80)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        button("▶ Mở", self.open_profiles, color="#1f6aa5", width=80)
        button("⏹ Đóng", self.close_profiles, color="#7a5", width=90)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        button("🔄 Quét thư mục", self.scan_existing, width=130)

        self.login_threads_label = ctk.CTkLabel(actions, text="Luồng cookie", font=bold)
        self.login_threads_label.pack(side="left", padx=(10, 4))
        self.login_threads_box = ctk.CTkOptionMenu(
            actions, values=[str(n) for n in range(1, 9)], width=64,
            font=bold, command=self._set_login_threads,
        )
        self.login_threads_box.set(str(self.settings.login_threads or 5))
        self.login_threads_box.pack(side="left")

    def _build_table(self, parent) -> None:
        # Bang va bang chi tiet nam canh nhau. Phai dung grid chu khong pack:
        # pack cap cho theo thu tu, bang chinh co expand=True se nuot het be ngang
        # va bang chi tiet (pack sau) khong con lai mot pixel nao.
        self._table_area = ctk.CTkFrame(parent, fg_color="transparent")
        self._table_area.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self._table_area.grid_rowconfigure(0, weight=1)
        self._table_area.grid_columnconfigure(0, weight=1)

        wrapper = ctk.CTkFrame(self._table_area)
        wrapper.grid(row=0, column=0, sticky="nsew")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Accounts.Treeview", rowheight=28, borderwidth=0)
        # Treeview khong co san duong ke o -- phai tu boc them mot phan tu ve vien
        # vao bo cuc cua o. Xem _make_grid_element de biet vi sao khong dung
        # phan tu "border" san co.
        self._build_grid_layout(style)
        style.configure(
            "Accounts.Treeview.Heading",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
        )
        # Mau do _apply_theme dat, vi con doi theo giao dien sang/toi.

        self.tree = ttk.Treeview(
            wrapper,
            columns=[c[0] for c in COLUMNS],
            show="headings",
            selectmode="extended",
            style="Accounts.Treeview",
        )
        for key, title, width, anchor in COLUMNS:
            self.tree.heading(key, text=title, command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "note"))

        self._apply_columns()

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
        # Keo chuot de quet chon nhieu dong (rubber-band). Treeview khong co san.
        self._drag_anchor = None
        self.tree.bind("<Button-1>", self._drag_start)
        self.tree.bind("<B1-Motion>", self._drag_select)
        # Ctrl+A chon het. Chi gan tren bang, khong gan toan cua so -- de Ctrl+A
        # trong o tim kiem van la "chon het chu" nhu binh thuong.
        self.tree.bind("<Control-a>", self._select_all_rows)
        self.tree.bind("<Control-A>", self._select_all_rows)

        self._menu = self._make_menu(self)

        # Viec hay dung nhat len tren; "Tao profile" chi lam mot lan cho moi acc
        # nen de xuong duoi, tranh bam nham vao no khi dinh mo profile.
        self._menu.add_command(label="▶ Mở profile", command=self.open_profiles)
        self._menu.add_command(label="🔑 Đăng nhập với cookie", command=self.relogin_cookie)
        # "Nhap / sua cookie" da nam trong menu con "Sua" -> bo o day cho do trung.
        self._menu.add_command(label="⏹ Đóng profile", command=self.close_profiles)
        self._menu.add_command(label="🧩 Tạo profile", command=self.create_profiles)
        self._menu.add_separator()

        # Danh sach nhom doi theo thoi gian nen dung lai moi lan bung menu.
        self._group_menu = self._make_menu(self._menu)
        self._menu.add_cascade(label="🗂 Chuyển vào nhóm", menu=self._group_menu)
        # Gom moi thu "sua" vao mot menu con: truoc day chi co moi "Sua ghi chu"
        # nam le o day, con cac truong khac phai mo bang chi tiet ben phai.
        edit_menu = self._make_menu(self._menu)
        edit_menu.add_command(label="Sửa tất cả...", command=self.edit_account)
        edit_menu.add_separator()
        edit_menu.add_command(label="Sửa ID acc", command=self.edit_id)
        edit_menu.add_command(label="Sửa mật khẩu",
                              command=lambda: self._edit_field("password", "Mật khẩu"))
        edit_menu.add_command(label="Sửa 2FA",
                              command=lambda: self._edit_field("twofa", "Mã 2FA"))
        edit_menu.add_command(label="Sửa cookie...", command=self.edit_cookie)
        edit_menu.add_command(label="Sửa proxy...", command=self.change_proxy)
        edit_menu.add_separator()
        edit_menu.add_command(
            label="Sửa email khôi phục",
            command=lambda: self._edit_field("recovery_mail", "Email khôi phục"))
        edit_menu.add_command(
            label="Sửa pass email khôi phục",
            command=lambda: self._edit_field("recovery_mail_password", "Pass email khôi phục"))
        edit_menu.add_command(
            label="Sửa email KP của email KP",
            command=lambda: self._edit_field("recovery_mail_backup",
                                             "Email khôi phục của email khôi phục"))
        edit_menu.add_separator()
        edit_menu.add_command(label="Sửa nhóm",
                              command=lambda: self._edit_field("group", "Nhóm"))
        edit_menu.add_command(
            label="Sửa trạng thái",
            command=lambda: self._edit_field("status", "Trạng thái", options=list(STATUSES)))
        edit_menu.add_command(label="Sửa ghi chú...", command=self.edit_note)
        edit_menu.add_separator()
        edit_menu.add_command(label="Xoá cookie đã lưu", command=self.clear_cookie_field)
        self._menu.add_cascade(label="✏️ Sửa", menu=edit_menu)
        self._menu.add_separator()

        self._menu.add_command(label="🌐 Đổi proxy...", command=self.change_proxy)
        self._menu.add_command(label="📡 Test proxy", command=self.check_proxies)
        # Hai lenh khop / bo khop mui gio da an khoi menu theo yeu cau. Muc nay
        # van tu chay khi tao profile va khi doi proxy (xem ProfileManager), nen
        # bo nut di khong lam mat chuc nang -- match_identities/clear_identities
        # duoc giu lai de goi lai duoc khi can.
        self._menu.add_separator()

        # Gom cac lenh chep vao mot menu con cho menu chinh do dai.
        copy_menu = self._make_menu(self._menu)
        copy_menu.add_command(label="ID acc", command=lambda: self._copy_field("id"))
        copy_menu.add_command(label="Mật khẩu", command=lambda: self._copy_field("password"))
        copy_menu.add_command(label="Mail khôi phục", command=lambda: self._copy_field("recovery_mail"))
        copy_menu.add_command(label="Mã 2FA", command=self.copy_2fa)
        copy_menu.add_command(label="Cookie", command=lambda: self._copy_field("cookie"))
        copy_menu.add_separator()
        copy_menu.add_command(label="Ghi chú", command=lambda: self._copy_field("note"))
        copy_menu.add_separator()
        copy_menu.add_command(label="Tuỳ chọn định dạng...", command=self.copy_custom)
        self._menu.add_cascade(label="📋 Copy", menu=copy_menu)
        self._menu.add_separator()

        self._menu.add_command(label="Mở thư mục profile", command=self.open_folder)
        self._menu.add_command(label="🧩 Cài extension vào Firefox...", command=self.install_extension)
        self._menu.add_command(label="🧩 Gỡ extension", command=self.remove_extension)
        self._menu.add_command(label="🧽 Xoá cache trình duyệt", command=self.clear_cache)
        self._menu.add_command(label="🧹 Xoá file cài đặt thừa", command=self.cleanup_installers)
        self._menu.add_command(label="💾 Lưu cookie từ profile vào acc",
                               command=self.save_cookie_from_profile)
        self._menu.add_command(label="Xuất cookie từ profile", command=self.export_cookie)
        self._menu.add_separator()
        self._menu.add_command(label="Xoá acc", command=self.delete_accounts)

    # ------------------------------------------------------------------
    # Bang chi tiet ben phai
    # ------------------------------------------------------------------
    def _build_detail(self) -> None:
        """Bang thong tin acc, hien ra khi bam vao mot dong."""
        self._detail = ctk.CTkFrame(self._table_area, width=DETAIL_WIDTH)
        self._detail.grid_propagate(False)      # giu nguyen be ngang 330px
        self._detail_account: Optional[Account] = None
        self._detail_fields: dict[str, ctk.CTkBaseClass] = {}
        # Tu theo doi trang thai an/hien: winfo_ismapped() con phu thuoc ca cua so
        # cha da ve xong chua, khong dung de quyet dinh logic duoc.
        self._detail_open = False

        head = ctk.CTkFrame(self._detail, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(10, 4))
        self._detail_title = ctk.CTkLabel(
            head, text="", anchor="w", font=ctk.CTkFont(size=14, weight="bold")
        )
        self._detail_title.pack(side="left")
        ctk.CTkButton(
            head, text="✕", width=28, fg_color="#a33", hover_color="#c44",
            command=self.hide_detail,
        ).pack(side="right")

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
            if height:
                widget = ctk.CTkTextbox(body, height=height)
            else:
                widget = ctk.CTkEntry(body)
            widget.pack(fill="x")
            self._detail_fields[key] = widget
            return widget

        # Thu tu nay do nguoi dung chi dinh, moi thu mot dong tu tren xuong.
        row("ID acc", "id")
        self._detail_fields["id"].configure(state="disabled")

        row("Mật khẩu", "password")

        twofa = row("2FA (secret)", "twofa")
        self._detail_2fa = ctk.CTkLabel(body, text="", anchor="w", text_color="gray60",
                                        font=ctk.CTkFont(size=11))
        self._detail_2fa.pack(fill="x")
        twofa.bind("<KeyRelease>", lambda _e: self._tick_detail_2fa())

        # Cookie de mot dong nhu cac o khac cho gon; noi dung dai thi cuon ngang,
        # can lay ca chuoi thi bam nut chep ben canh.
        row("Cookie", "cookie")
        row("Proxy", "proxy")
        row("Email khôi phục", "recovery_mail")
        row("Pass email khôi phục", "recovery_mail_password")
        row("Email khôi phục của email khôi phục", "recovery_mail_backup")

        row("Nhóm", "group")

        ctk.CTkLabel(body, text="Trạng thái", anchor="w", text_color="gray60",
                     font=ctk.CTkFont(size=11)).pack(fill="x", pady=(6, 0))
        self._detail_status = ctk.CTkOptionMenu(body, values=list(STATUSES))
        self._detail_status.pack(fill="x")

        ctk.CTkLabel(body, text="Múi giờ / Ngôn ngữ", anchor="w", text_color="gray60",
                     font=ctk.CTkFont(size=11)).pack(fill="x", pady=(6, 0))
        self._detail_identity = ctk.CTkLabel(body, text="", anchor="w", justify="left",
                                             wraplength=280)
        self._detail_identity.pack(fill="x")

        row("Ghi chú", "note", height=60)

        # Cac truong phu tu file nhap (token, phone, user agent...). Truoc day
        # chung nam trong Account.extra ma khong hien o dau ca.
        self._detail_extra = ctk.CTkFrame(body, fg_color="transparent")
        self._detail_extra.pack(fill="x", pady=(10, 0))

        foot = ctk.CTkFrame(self._detail, fg_color="transparent")
        foot.pack(fill="x", padx=10, pady=8)
        ctk.CTkButton(foot, text="💾 Lưu", command=self.save_detail).pack(
            side="left", fill="x", expand=True
        )
        ctk.CTkButton(foot, text="▶ Mở", width=70, fg_color="#1f6aa5",
                      command=self.open_profiles).pack(side="left", padx=(6, 0))

        self._tick_detail_2fa()

    def show_detail(self, account: Account) -> None:
        """Do thong tin cua acc vao bang ben phai va hien no ra."""
        self._detail_account = account
        self._detail_title.configure(text=account.id)

        values = {
            "id": account.id,
            "password": account.password,
            "recovery_mail": account.recovery_mail,
            "recovery_mail_password": account.recovery_mail_password,
            "recovery_mail_backup": account.recovery_mail_backup,
            "twofa": account.twofa,
            "proxy": account.get_proxy().as_text(),
            "group": account.group,
            "note": account.note,
            "cookie": account.cookie,
        }
        for key, widget in self._detail_fields.items():
            text = values.get(key, "")
            if isinstance(widget, ctk.CTkTextbox):
                widget.delete("1.0", "end")
                widget.insert("1.0", text)
            else:
                # O ID bi khoa, phai mo ra moi ghi duoc roi khoa lai.
                locked = str(widget.cget("state")) == "disabled"
                if locked:
                    widget.configure(state="normal")
                widget.delete(0, "end")
                widget.insert(0, text)
                if locked:
                    widget.configure(state="disabled")

        self._fill_extra(account)
        self._detail_status.set(account.status or STATUSES[0])
        identity = account.get_identity()
        self._detail_identity.configure(
            text=identity.summary() or "chưa khớp theo proxy",
            text_color="gray75" if identity.enabled else "gray50",
        )
        self._tick_detail_2fa()

        if not self._detail_open:
            # Dat minsize cho cot moi giu duoc be ngang: grid_propagate(False)
            # mot minh khong du, khung van bi bop lai theo noi dung ben trong.
            self._table_area.grid_columnconfigure(1, minsize=DETAIL_WIDTH)
            self._detail.grid(row=0, column=1, sticky="nsew", padx=(PAD, 0))
            self._detail_open = True

    def _fill_extra(self, account: Account) -> None:
        """Liet ke cac truong phu con lai trong ``extra``, chi de xem va chep."""
        for child in self._detail_extra.winfo_children():
            child.destroy()
        items = [(k, str(v)) for k, v in sorted(account.extra.items()) if str(v).strip()]
        if not items:
            return
        ctk.CTkLabel(
            self._detail_extra, text="Trường phụ từ file nhập", anchor="w",
            text_color="gray60", font=ctk.CTkFont(size=11),
        ).pack(fill="x")
        for key, value in items:
            line = ctk.CTkFrame(self._detail_extra, fg_color="transparent")
            line.pack(fill="x", pady=(4, 0))
            ctk.CTkLabel(line, text=key, anchor="w", width=90,
                         text_color="gray60", font=ctk.CTkFont(size=11)).pack(side="left")
            entry = ctk.CTkEntry(line)
            entry.insert(0, value)
            entry.configure(state="readonly")
            entry.pack(side="left", fill="x", expand=True)
            ctk.CTkButton(
                line, text="⧉", width=26,
                fg_color="transparent", text_color="gray60", hover_color="gray30",
                command=lambda v=value: self._copy_text(v),
            ).pack(side="left")

    #: Cac o co the chen vao mau copy: (khoa, ten hien ra).
    COPY_PLACEHOLDERS = (
        ("id", "ID acc"),
        ("password", "Mật khẩu"),
        ("twofa", "2FA secret"),
        ("twofa_code", "Mã 2FA hiện tại"),
        ("cookie", "Cookie"),
        ("proxy", "Proxy"),
        ("proxy_host", "Proxy host"),
        ("proxy_port", "Proxy port"),
        ("proxy_user", "Proxy user"),
        ("proxy_pass", "Proxy pass"),
        ("recovery_mail", "Email khôi phục"),
        ("recovery_mail_password", "Pass email KP"),
        ("recovery_mail_backup", "Email KP của email KP"),
        ("group", "Nhóm"),
        ("status", "Trạng thái"),
        ("note", "Ghi chú"),
        ("timezone", "Múi giờ"),
        ("language", "Ngôn ngữ"),
        ("folder", "Tên thư mục"),
        ("path", "Đường dẫn profile"),
    )

    def _copy_values(self, account: Account) -> dict:
        """Gia tri cua mot acc dung cho mau copy."""
        proxy = account.get_proxy()
        identity = account.get_identity()
        try:
            code = totp.generate(account.twofa) if account.twofa else ""
        except Exception:
            code = ""
        values = {
            "id": account.id,
            "password": account.password,
            "twofa": account.twofa,
            "twofa_code": code,
            "cookie": account.cookie,
            "proxy": proxy.as_text(),
            "proxy_host": proxy.host,
            "proxy_port": str(proxy.port or ""),
            "proxy_user": proxy.username,
            "proxy_pass": proxy.password,
            "recovery_mail": account.recovery_mail,
            "recovery_mail_password": account.recovery_mail_password,
            "recovery_mail_backup": account.recovery_mail_backup,
            "group": account.group,
            "status": account.status,
            "note": (account.note or "").replace("\n", " "),
            "timezone": identity.timezone,
            "language": (identity.accept_languages or "").split(",")[0].strip(),
            "folder": account.folder,
            "path": self.manager.app_dir(account),
        }
        # Cac truong phu tu file nhap (token, phone...) cung dung duoc trong mau.
        for key, value in account.extra.items():
            values.setdefault(key, str(value))
        return values

    def _render_template(self, template: str, account: Account) -> str:
        """Thay cac o {..} trong mau bang gia tri cua acc.

        O khong biet ten thi de trong chu khong nem loi, de nguoi dung go dang do
        van thay xem truoc chu khong bi bao loi lien tuc.
        """
        class _Blank(dict):
            def __missing__(self, key):
                return ""

        return template.format_map(_Blank(self._copy_values(account)))

    def copy_custom(self) -> None:
        """Copy hang loat theo dinh dang nguoi dung tu dat."""
        selected = self._require_selection()
        if not selected:
            return
        template = CopyCustomDialog(
            self, selected, self.settings.copy_template,
            self._render_template, self.COPY_PLACEHOLDERS,
        ).show()
        if not template:
            return

        self.settings.copy_template = template
        self.settings.save()
        lines = [self._render_template(template, a) for a in selected]
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.set_status(f"Đã copy {len(lines)} dòng theo định dạng đã đặt.")

    def _copy_text(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.set_status("Đã copy.")

    def hide_detail(self) -> None:
        self._detail.grid_remove()
        # Tra cot ve 0, neu khong bang chinh se chua mot khoang trong 340px.
        self._table_area.grid_columnconfigure(1, minsize=0)
        self._detail_open = False
        self._detail_account = None

    def toggle_detail(self) -> None:
        if self._detail_open:
            self.hide_detail()
            return
        chosen = self._selected_accounts()
        if chosen:
            self.show_detail(chosen[0])

    def _on_row_selected(self, _event=None) -> None:
        """Bam mot dong thi do thong tin sang bang ben phai."""
        chosen = self._selected_accounts()
        if len(chosen) == 1:
            self.show_detail(chosen[0])
        elif self._detail_open:
            # Chon nhieu dong thi khong biet hien acc nao.
            self._detail_title.configure(text=f"{len(chosen)} acc đang chọn")
            self._detail_account = None

    def _copy_detail(self, key: str) -> None:
        widget = self._detail_fields.get(key)
        if widget is None:
            return
        text = (widget.get("1.0", "end") if isinstance(widget, ctk.CTkTextbox)
                else widget.get()).strip()
        if not text:
            self.set_status("Ô này đang trống.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.set_status(f"Đã copy {key}.")

    def _tick_detail_2fa(self) -> None:
        if not self.winfo_exists():
            return
        secret = self._detail_fields["twofa"].get().strip() if self._detail_fields else ""
        if secret:
            try:
                self._detail_2fa.configure(
                    text=f"Mã hiện tại: {totp.generate(secret)}  ({totp.seconds_remaining()}s)"
                )
            except Exception:
                self._detail_2fa.configure(text="secret không hợp lệ")
        else:
            self._detail_2fa.configure(text="")
        self.after(1000, self._tick_detail_2fa)

    def save_detail(self) -> None:
        """Ghi lai thay doi tu bang ben phai."""
        account = self._detail_account
        if account is None:
            messagebox.showinfo("Lưu", "Chọn đúng một acc rồi hãy lưu.", parent=self)
            return

        text = lambda k: (
            self._detail_fields[k].get("1.0", "end")
            if isinstance(self._detail_fields[k], ctk.CTkTextbox)
            else self._detail_fields[k].get()
        ).strip()

        try:
            proxy = Proxy() if not text("proxy") else proxy_module.parse(text("proxy"))
        except ValueError as exc:
            messagebox.showerror("Proxy", str(exc), parent=self)
            return

        account.password = text("password")
        account.recovery_mail = text("recovery_mail")
        account.recovery_mail_password = text("recovery_mail_password")
        account.recovery_mail_backup = text("recovery_mail_backup")
        account.twofa = text("twofa")
        account.group = text("group")
        account.note = text("note")
        account.cookie = text("cookie")
        account.status = self._detail_status.get()

        if proxy != account.get_proxy():
            # Doi proxy keo theo mui gio + ngon ngu, di duong rieng cho dung.
            self._apply_proxy_change([(account, proxy)])
        else:
            self.store.save()
            self.refresh()
        self.show_detail(account)
        self.set_status(f"Đã lưu {account.id}.")

    def _make_menu(self, parent) -> tk.Menu:
        """Tao menu chuot phai va nho lai de con to mau khi doi giao dien."""
        menu = tk.Menu(parent, tearoff=0, borderwidth=0)
        self._menus.append(menu)
        return menu

    def _apply_theme(self) -> None:
        """To mau cho Treeview va menu -- hai thu khong tu doi theo customtkinter."""
        mode = self.settings.appearance if self.settings.appearance in THEMES else "light"
        colors = THEMES[mode]
        ctk.set_appearance_mode(mode)

        style = ttk.Style()
        style.configure(
            "Accounts.Treeview",
            background=colors["row_bg"],
            fieldbackground=colors["row_bg"],
            foreground=colors["row_fg"],
        )
        style.configure(
            "Accounts.Treeview.Heading",
            background=colors["head_bg"],
            foreground=colors["head_fg"],
        )
        self._apply_grid_lines(style, colors["grid"])
        style.map("Accounts.Treeview",
                  background=[("selected", colors["selected"])],
                  foreground=[("selected", "#ffffff")])
        style.map("Accounts.Treeview.Heading", background=[("active", colors["head_hover"])])

        self.tree.tag_configure("logged", background=colors["logged_bg"])
        self.tree.tag_configure("running", background=colors["running_bg"])
        self.tree.tag_configure("missing", foreground=colors["missing_fg"])

        for menu in self._menus:
            menu.configure(
                bg=colors["menu_bg"], fg=colors["menu_fg"],
                activebackground=colors["selected"], activeforeground="#ffffff",
            )

    @staticmethod
    def _build_grid_layout(style) -> None:
        """Ke bang lien mach kieu Excel: moi ranh gioi MOT net, khong phai moi o mot khung.

        Cach hay gap la boc ca o trong phan tu "border". Nhung nhu vay moi o co
        vien rieng du bon canh: hai o canh nhau thanh hai net song song cach nhau
        mot khe ho -- nhin ra mot ro cac cai hop chu khong phai cai luoi (da do
        bang anh chup: net o x=88 va x=98, ho 8 pixel o giua).

        O day chi ve HAI canh: mot vach o day o va mot vach o ben phai o. Vach
        cua o nay dong thoi la ranh gioi voi o ben canh -> ca bang lien mach.
        Vach day phai dat TRUOC vach phai de duong ke ngang chay het chieu rong o.

        Da thu ca cach dung phan tu anh (chu dong duoc do day 1 pixel) nhung Tk ve
        anh cho tung o rat cham: bang 13 cot x 17 dong mat 6 giay moi lan ve, con
        cach nay chi 0,5 giay.
        """
        # Lay phan tu vien cua theme "alt", khong phai "clam" hay "default":
        #   clam    -- net day 4 pixel, dam qua
        #   default -- net manh 2 pixel nhung ve MAU DEN, khong nghe bordercolor
        #   alt     -- net manh 2 pixel VA to dung mau minh dat -> chon cai nay
        for name in ("qlfp.hline", "qlfp.vline"):
            try:
                style.element_create(name, "from", "alt", "border")
            except tk.TclError:
                pass          # da tao o lan truoc (chi xay ra khi mo lai cua so)
        # Hai vach nam NGOAI phan dem chu: de trong phan dem thi vach bi thut vao
        # vai pixel moi ben, duong ke ngang dut mot khuc o moi ranh cot.
        style.layout("Accounts.Treeview.Cell", [
            ("qlfp.hline", {"side": "bottom", "sticky": "ew"}),
            ("qlfp.vline", {"side": "right", "sticky": "ns"}),
            ("Treedata.padding", {"sticky": "nswe", "children": [
                ("Treeitem.text", {"sticky": "nswe"}),
            ]}),
        ])

    @staticmethod
    def _apply_grid_lines(style, color: str) -> None:
        """To mau hai vach ke theo giao dien sang/toi."""
        style.configure("Accounts.Treeview.Cell", bordercolor=color,
                        lightcolor=color, darkcolor=color,
                        borderwidth=1, relief="solid", padding=(6, 0))

    def _build_statusbar(self) -> None:
        bar = ctk.CTkFrame(self, height=30, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        self.status_label = ctk.CTkLabel(bar, text="Sẵn sàng.", anchor="w")
        self.status_label.pack(side="left", padx=12, pady=4)
        self.progress = ctk.CTkProgressBar(bar, width=180, mode="indeterminate")

    # ------------------------------------------------------------------
    # Du lieu / bang
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self.root_label.configure(text=self.settings.profiles_root)

        groups = self.store.groups()
        self.group_filter.configure(values=["Tất cả nhóm", *groups])
        if self.group_filter.get() not in ("Tất cả nhóm", *groups):
            self.group_filter.set("Tất cả nhóm")

        group = self.group_filter.get()
        status = self.status_filter.get()
        self._rows = self.store.search(
            keyword=self.search_entry.get(),
            group="" if group == "Tất cả nhóm" else group,
            status="" if status == "Tất cả trạng thái" else status,
        )

        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        for index, account in enumerate(self._rows, start=1):
            self.tree.insert("", "end", iid=account.id, values=self._row_values(index, account),
                             tags=self._row_tags(account, index))
        for item in selected:
            if self.tree.exists(item):
                self.tree.selection_add(item)

        self.count_label.configure(text=f"{len(self._rows)}/{len(self.store)} acc")

    def _row_values(self, index: int, account: Account) -> tuple:
        """Gia tri tung o, tra ra dung thu tu COLUMNS.

        Dung tu dien chu khong phai tuple viet tay: doi thu tu cot trong COLUMNS
        thi bang van dung, khong con canh o nay nhay sang cot kia.
        """
        show = self._show_secrets.get()
        proxy = account.get_proxy()
        installed = self.manager.is_installed(account)
        cookie_count = self._cookie_count(account)
        cells = {
            "stt": index,
            "id": account.id,
            "password": (account.password or "") if show
                        else ("•" * min(len(account.password), 10) or "—"),
            "mail": account.recovery_mail or "—",
            "twofa": "có" if account.twofa else "—",
            "cookie": f"{cookie_count}" if cookie_count else "—",
            "proxy": proxy.display(mask=not show) or "—",
            "identity": self._identity_cell(account),
            "group": account.group or "—",
            "status": self._status_cell(account),
            "profile": "đã tạo" if installed else "chưa tạo",
            "running": "▶" if installed and self.manager.is_running(account) else "",
            "note": (account.note or "").replace(chr(10), " ")[:120],
        }
        return tuple(cells[key] for key, *_ in COLUMNS)

    @staticmethod
    def _status_cell(account: Account) -> str:
        """Cot "Trạng thái": kết quả test proxy nếu đã test, chưa thì trạng thái acc."""
        if account.proxy_status:
            return account.proxy_status
        return account.status or "—"

    @staticmethod
    def _identity_cell(account: Account) -> str:
        identity = account.get_identity()
        if not identity.enabled:
            return "chưa khớp" if account.get_proxy().enabled else "—"
        language = (identity.accept_languages or "").split(",")[0].strip()
        return " · ".join(p for p in (identity.timezone, language) if p)

    def _row_tags(self, account: Account, index: int = 0) -> tuple:
        """Mau nen noi len trang thai dang nhap cookie.

        Xanh la = da dang nhap bang cookie thanh cong. Trang = chua chay.
        Dong dang mo trinh duyet uu tien mau xanh duong de con phan biet.
        """
        installed = self.manager.is_installed(account)
        if installed and self.manager.is_running(account):
            return ("running",)
        if account.cookie_ok:
            return ("logged",)
        return () if installed else ("missing",)

    @staticmethod
    def _cookie_count(account: Account) -> int:
        if not account.cookie.strip():
            return 0
        try:
            return len(cookie_module.parse(account.cookie, default_domain=".facebook.com"))
        except cookie_module.CookieError:
            return 0

    def _sort_by(self, key: str) -> None:
        rows = [(self.tree.set(item, key), item) for item in self.tree.get_children("")]
        reverse = getattr(self, "_sort_reverse", {}).get(key, False)
        rows.sort(key=lambda pair: pair[0].lower(), reverse=reverse)
        for position, (_value, item) in enumerate(rows):
            self.tree.move(item, "", position)
        if not hasattr(self, "_sort_reverse"):
            self._sort_reverse = {}
        self._sort_reverse[key] = not reverse

    def _selected_accounts(self) -> list[Account]:
        ids = set(self.tree.selection())
        return [account for account in self._rows if account.id in ids]

    def _require_selection(self, single: bool = False) -> list[Account]:
        selected = self._selected_accounts()
        if not selected:
            messagebox.showinfo("Chưa chọn", "Hãy chọn ít nhất một acc trong bảng.", parent=self)
            return []
        if single and len(selected) > 1:
            messagebox.showinfo("Chọn một acc", "Chức năng này chỉ áp dụng cho một acc.", parent=self)
            return []
        return selected

    #: Bit trang thai phim bo tro trong su kien chuot cua Tk.
    SHIFT_HELD = 0x0001
    CTRL_HELD = 0x0004

    def _drag_start(self, event) -> None:
        """Ghi lai dong bam xuong lam moc cho thao tac keo chon."""
        # Bam tren tieu de cot / vung thay doi do rong -> khong phai keo chon.
        if self.tree.identify_region(event.x, event.y) in ("heading", "separator"):
            self._drag_anchor = None
            return

        # Giu Ctrl/Shift thi de Treeview tu xu ly (cong don / chon khoang).
        # Khong nhuong thi chi can nhich chuot 1px la _drag_select ghi de len
        # lua chon vua cong don, coi nhu Ctrl+click khong dung duoc.
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
        # Keo toi bien tren/duoi thi cuon theo cho chon duoc dong ngoai tam nhin.
        self.tree.see(current)

    def _apply_columns(self) -> None:
        """Dat thu tu va an/hien cot theo cai dat.

        Dung displaycolumns cua Treeview: no nhan danh sach cot theo DUNG thu tu
        hien thi, nen khong phai dung lai ca bang.
        """
        keys = [key for key, *_ in COLUMNS]
        order = [k for k in (self.settings.column_order or []) if k in keys]
        order += [k for k in keys if k not in order]
        hidden = {k for k in (self.settings.column_hidden or []) if k in keys}

        shown = [k for k in order if k not in hidden]
        if not shown:                      # an het thi bang thanh vo dung
            shown = keys
        self.tree.configure(displaycolumns=shown)

    def choose_columns(self) -> None:
        """Cho nguoi dung chon cot nao hien va sap lai thu tu."""
        columns = [(key, title) for key, title, *_ in COLUMNS]
        picked = ColumnDialog(
            self, columns, self.settings.column_order, self.settings.column_hidden
        ).show()
        if picked is None:
            return
        self.settings.column_order, self.settings.column_hidden = picked
        self.settings.save()
        self._apply_columns()
        self.set_status(
            f"Đang hiện {len(self.settings.column_order) - len(self.settings.column_hidden)}"
            f"/{len(COLUMNS)} cột."
        )

    def _set_login_threads(self, value: str) -> None:
        """Doi so trinh duyet mo cung luc khi dang nhap cookie."""
        try:
            self.settings.login_threads = max(1, min(8, int(value)))
        except ValueError:
            return
        self.settings.save()
        self.set_status(
            f"Đăng nhập cookie sẽ mở {self.settings.login_threads} trình duyệt cùng lúc."
        )

    def _select_all_rows(self, _event=None) -> str:
        """Ctrl+A: chon toan bo dong dang hien (theo bo loc hien tai)."""
        items = self.tree.get_children("")
        if items:
            self.tree.selection_set(items)
            self.tree.focus(items[0])
            self.set_status(f"Đã chọn {len(items)} acc.")
        return "break"

    def _popup_menu(self, event) -> None:
        item = self.tree.identify_row(event.y)
        if item and item not in self.tree.selection():
            self.tree.selection_set(item)
        if not self.tree.selection():
            return
        self._rebuild_group_menu()
        self._menu.tk_popup(event.x_root, event.y_root)

    def _rebuild_group_menu(self) -> None:
        """Dung lai menu con 'Chuyen vao nhom' theo danh sach nhom hien tai."""
        self._group_menu.delete(0, "end")
        selected = self._selected_accounts()
        current = {a.group.strip() for a in selected}

        for name in self.store.groups():
            # Cham danh dau nhom ma toan bo acc dang chon deu thuoc ve.
            mark = "● " if current == {name} else "○ "
            self._group_menu.add_command(
                label=mark + name,
                command=lambda n=name: self.assign_group(n),
            )
        if self.store.groups():
            self._group_menu.add_separator()
        self._group_menu.add_command(
            label="➕ Nhóm mới...", command=self.assign_new_group
        )
        self._group_menu.add_command(
            label="✖ Bỏ khỏi nhóm", command=lambda: self.assign_group("")
        )

    # ------------------------------------------------------------------
    # Chay tac vu nen
    # ------------------------------------------------------------------
    def _drain_events(self) -> None:
        try:
            while True:
                callback = self._events.get_nowait()
                callback()
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _post(self, callback: Callable[[], None]) -> None:
        self._events.put(callback)

    def set_status(self, message: str) -> None:
        self._post(lambda: self.status_label.configure(text=message))

    def _run_async(self, work: Callable[[], None], done_message: str = "Xong.") -> None:
        if self._busy:
            messagebox.showinfo("Đang bận", "Một tác vụ khác đang chạy, vui lòng đợi.", parent=self)
            return
        self._busy = True
        self.progress.pack(side="right", padx=12)
        self.progress.start()

        def runner():
            try:
                work()
                self.set_status(done_message)
            except Exception as exc:  # loi cua tac vu nen phai hien ra cho nguoi dung
                message = str(exc)
                self.set_status(f"Lỗi: {message}")
                self._post(lambda: messagebox.showerror("Lỗi", message, parent=self))
            finally:
                self._post(self._finish_async)

        threading.Thread(target=runner, daemon=True).start()

    def _finish_async(self) -> None:
        self._busy = False
        self.progress.stop()
        self.progress.pack_forget()
        self.refresh()

    def _schedule_running_check(self) -> None:
        self.after(4000, self._running_check)

    def _running_check(self) -> None:
        if not self._busy:
            for index, account in enumerate(self._rows, start=1):
                if self.tree.exists(account.id):
                    self.tree.item(account.id, tags=self._row_tags(account, index))
                    self.tree.set(account.id, "running",
                                  "▶" if self.manager.is_installed(account) and self.manager.is_running(account) else "")
        self._schedule_running_check()

    # ------------------------------------------------------------------
    # Hanh dong
    # ------------------------------------------------------------------
    def add_account(self) -> None:
        account = AccountDialog(self, groups=self.store.groups()).show()
        if not account:
            return
        try:
            self.store.add(account)
        except ValueError as exc:
            messagebox.showerror("Không thêm được", str(exc), parent=self)
            return
        self.refresh()
        self.set_status(f"Đã thêm acc {account.id}.")

    def edit_account(self) -> None:
        selected = self._require_selection(single=True)
        if not selected:
            return
        original = selected[0]
        edited = AccountDialog(self, account=original, groups=self.store.groups()).show()
        if not edited:
            return
        try:
            self.store.update(original.id, edited)
        except ValueError as exc:
            messagebox.showerror("Không lưu được", str(exc), parent=self)
            return
        if edited.proxy != original.proxy:
            # Proxy doi thi di duong rieng de con ap dung duoc cho trinh duyet dang mo.
            self._apply_proxy_change([(edited, edited.get_proxy())])
        elif self.manager.is_installed(edited):
            try:
                self.manager.configure(edited)
            except ProfileError:
                pass
        self.refresh()
        self.set_status(f"Đã lưu acc {edited.id}.")

    # ---- nhom ---------------------------------------------------------
    def manage_groups(self) -> None:
        if GroupManagerDialog(self, self.store).show():
            self.refresh()
            self.set_status("Đã cập nhật danh sách nhóm.")

    def assign_group(self, name: str) -> None:
        """Chuyen cac acc dang chon sang nhom ``name``; rong = bo khoi nhom."""
        selected = self._require_selection()
        if not selected:
            return
        moved = self.store.assign_group([a.id for a in selected], name)
        self.refresh()
        if not name:
            self.set_status(f"Đã bỏ {moved} acc khỏi nhóm.")
        elif moved:
            self.set_status(f"Đã chuyển {moved} acc vào nhóm “{name}”.")
        else:
            self.set_status(f"Các acc đã chọn vốn đã ở nhóm “{name}”.")

    def assign_new_group(self) -> None:
        selected = self._require_selection()
        if not selected:
            return
        name = SimplePromptDialog(
            self,
            "Nhóm mới",
            f"Tên nhóm mới cho {len(selected)} acc đang chọn:",
        ).show()
        if name:
            self.assign_group(name)

    #: Ten hien thi cua tung truong, dung trong loi bao sau khi sua.
    FIELD_LABELS = {
        "password": "mật khẩu",
        "twofa": "mã 2FA",
        "recovery_mail": "email khôi phục",
        "recovery_mail_password": "pass email khôi phục",
        "recovery_mail_backup": "email khôi phục của email khôi phục",
        "group": "nhóm",
        "status": "trạng thái",
        "cookie": "cookie",
    }

    def _edit_field(self, key: str, label: str, multiline: bool = False,
                    options: Optional[list] = None) -> None:
        """Sua nhanh MOT truong cho cac acc dang chon.

        Chon nhieu acc thi ghi de cung mot gia tri cho tat ca -- dung khi ca lo
        cung mot mat khau, cung mot nhom, cung mot trang thai.
        """
        selected = self._require_selection()
        if not selected:
            return
        values = [str(getattr(account, key, "") or "") for account in selected]
        result = FieldEditDialog(self, selected, "Sửa " + label.lower(), label,
                                 values, multiline=multiline, options=options).show()
        if result is None:
            return                    # bam Huy; de trong van la mot thay doi hop le

        changed = 0
        for account in selected:
            if str(getattr(account, key, "") or "") != result:
                setattr(account, key, result)
                changed += 1
        self.store.save()
        self.refresh()
        ten = self.FIELD_LABELS.get(key, label.lower())
        self.set_status(
            f"Đã sửa {ten} cho {changed} acc." if changed
            else f"Không có gì thay đổi ({ten} vẫn như cũ)."
        )

    def edit_id(self) -> None:
        """Doi ID acc -- chi cho sua tung acc mot vi ID la khoa dinh danh.

        Thu muc profile duoc dat ten theo ID, nen doi ID khi da tao profile la
        acc mat lien ket voi thu muc cu. Bao truoc chu khong am tham lam.
        """
        selected = self._require_selection()
        if not selected:
            return
        if len(selected) > 1:
            messagebox.showinfo(
                "Sửa ID acc",
                "ID acc là khoá phân biệt từng acc nên chỉ sửa được một acc mỗi lần.",
                parent=self,
            )
            return
        account = selected[0]
        moi = FieldEditDialog(self, selected, "Sửa ID acc", "ID acc",
                              [account.id]).show()
        if moi is None or moi == account.id:
            return
        if not moi:
            messagebox.showerror("Sửa ID acc", "ID acc không được để trống.", parent=self)
            return
        if any(a is not account and a.id == moi for a in self.store.accounts):
            messagebox.showerror("Sửa ID acc", f"Đã có acc mang ID '{moi}'.", parent=self)
            return
        if self.manager.is_installed(account):
            if not messagebox.askyesno(
                "Sửa ID acc",
                f"Acc '{account.id}' đã có profile trong thư mục '{account.folder}'."
                + chr(10) * 2
                + f"Đổi ID thành '{moi}' thì tool sẽ tìm profile ở thư mục mới và coi như "
                  f"acc này chưa có profile. Thư mục cũ vẫn còn nguyên trên đĩa."
                + chr(10) * 2 + "Vẫn đổi?",
                parent=self,
            ):
                return
        cu = account.id
        account.id = moi
        self.store.save()
        self.refresh()
        self.set_status(f"Đã đổi ID acc {cu} thành {moi}.")

    def clear_cookie_field(self) -> None:
        """Xoa cookie da luu trong acc (khong dung toi profile tren dia)."""
        selected = self._require_selection()
        if not selected:
            return
        co = [a for a in selected if (a.cookie or "").strip()]
        if not co:
            self.set_status("Các acc đã chọn vốn không có cookie.")
            return
        if not messagebox.askyesno(
            "Xoá cookie đã lưu",
            f"Xoá cookie đã lưu của {len(co)} acc?" + chr(10) * 2
            + "Chỉ xoá cookie trong bảng, profile trên đĩa vẫn giữ nguyên phiên đăng nhập.",
            parent=self,
        ):
            return
        for account in co:
            account.cookie = ""
        self.store.save()
        self.refresh()
        self.set_status(f"Đã xoá cookie đã lưu của {len(co)} acc.")

    def edit_note(self) -> None:
        selected = self._require_selection()
        if not selected:
            return
        # Chuoi rong van la ket qua hop le (xoa ghi chu); chi None moi la huy.
        outcome = NoteDialog(self, selected).show()
        if outcome is None:
            return
        text, append = outcome

        changed = 0
        for account in selected:
            old = account.note or ""
            if append:
                new = f"{old.rstrip()}\n{text}" if old.strip() else text
            else:
                new = text
            if new != old:
                account.note = new
                changed += 1
        self.store.save()
        self.refresh()

        if len(selected) == 1:
            self.set_status(f"Đã lưu ghi chú cho {selected[0].id}.")
        elif append:
            self.set_status(f"Đã thêm ghi chú cho {changed} acc.")
        else:
            self.set_status(f"Đã cập nhật ghi chú của {changed}/{len(selected)} acc.")

    def bulk_import(self) -> None:
        result = BulkImportDialog(self, groups=self.store.groups()).show()
        if not result:
            return
        text, separator, fields, group = result
        added, errors = self.store.import_lines(text, separator, fields=fields, group=group)
        self.refresh()
        into = f" vào nhóm “{group}”" if group else ""
        summary = f"Đã thêm {added} acc{into}."
        if errors:
            summary += "\n\nBỏ qua:\n" + "\n".join(errors[:15])
            if len(errors) > 15:
                summary += f"\n... và {len(errors) - 15} dòng nữa."
        messagebox.showinfo("Nhập hàng loạt", summary, parent=self)

    def delete_accounts(self) -> None:
        selected = self._require_selection()
        if not selected:
            return
        names = ", ".join(a.id for a in selected[:5])
        if len(selected) > 5:
            names += f" ... (+{len(selected) - 5})"
        if not messagebox.askyesno(
            "Xoá acc",
            f"Xoá {len(selected)} acc khỏi danh sách?\n{names}",
            parent=self,
        ):
            return
        remove_folder = messagebox.askyesno(
            "Xoá thư mục",
            "Xoá luôn thư mục profile trên ổ đĩa?\n"
            "Chọn 'No' nếu chỉ muốn bỏ khỏi bảng.",
            parent=self,
        )

        def work():
            for account in selected:
                self.set_status(f"Đang xoá {account.id}...")
                if remove_folder:
                    self.manager.delete(account)
                else:
                    self.manager.close(account)
                self.store.remove(account.id)

        self._run_async(work, f"Đã xoá {len(selected)} acc.")

    def create_profiles(self) -> None:
        selected = self._require_selection()
        if not selected:
            return
        pending = [a for a in selected if not self.manager.is_installed(a)]
        if not pending:
            messagebox.showinfo("Tạo profile", "Các acc đã chọn đều có profile rồi.", parent=self)
            return
        workers = max(1, min(8, self.settings.create_threads or 3))
        workers = min(workers, len(pending))
        estimate = "" if self.settings.clone_from_template else " (~25 giây mỗi acc)"
        threads = f", chạy {workers} luồng cùng lúc" if workers > 1 else ""
        if not messagebox.askyesno(
            "Tạo profile",
            f"Tạo profile cho {len(pending)} acc{estimate}{threads}?",
            parent=self,
        ):
            return

        def work():
            done = 0
            errors: list[str] = []
            lock = threading.Lock()

            def build(account: Account) -> None:
                nonlocal done
                try:
                    prefix = f"{account.id}: "
                    report = lambda m, p=prefix: self.set_status(p + m)
                    self.manager.create(account, on_status=report)
                    self.manager.initialize(account, on_status=report)
                    if account.cookie.strip():
                        self._apply_cookie(account, replace=True)
                except Exception as exc:
                    with lock:
                        errors.append(f"{account.id}: {exc}".replace("\n", " ")[:160])
                    return
                with lock:
                    done += 1
                    self.set_status(f"[{done}/{len(pending)}] Xong {account.id}.")
                self._post(self.refresh)

            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(build, pending))

            # create() co the da do ra mui gio/ngon ngu moi, phai ghi lai xuong file.
            self.store.save()
            self._post(self.refresh)
            if errors:
                report = (f"Tạo được {done}/{len(pending)} profile.\n\nLỗi:\n"
                          + "\n".join(errors[:10]))
                self._post(lambda: messagebox.showwarning("Tạo profile", report, parent=self))

        self._run_async(work, f"Đã tạo xong {len(pending)} profile.")

    def open_profiles(self) -> None:
        selected = self._require_selection()
        if not selected:
            return
        missing = [a for a in selected if not self.manager.is_installed(a)]
        if missing:
            messagebox.showwarning(
                "Chưa có profile",
                "Các acc sau chưa tạo profile:\n" + "\n".join(a.id for a in missing[:10]),
                parent=self,
            )
            selected = [a for a in selected if self.manager.is_installed(a)]
            if not selected:
                return

        url = self.settings.start_url

        def work():
            for account in selected:
                seeded = self._ensure_login_cookies(account)
                note = " (đã nạp cookie)" if seeded else ""
                self.set_status(f"Đang mở {account.id}{note}...")
                self.manager.launch(account, url=url)
                self.store.mark_opened(account.id)
                time.sleep(1.2)  # tranh cac ban sao Firefox tranh nhau khi khoi dong

        self._run_async(work, f"Đã mở {len(selected)} profile.")

    def _ensure_login_cookies(self, account: Account) -> bool:
        """Nap cookie dang nhap truoc khi mo, neu can. Tra ve True neu vua nap.

        Chi nap khi: bat auto-login, acc co cookie luu san, va profile CHUA co
        cookie dang nhap (tranh ghi de len phien Firefox da tu lam moi). Cookie
        chi ghi duoc luc Firefox dong nen phai dong truoc.
        """
        if not self.settings.auto_login_cookie:
            return False
        if not account.cookie.strip() or not self.manager.is_installed(account):
            return False
        profile_dir = self.manager.profile_dir(account)
        if cookie_module.has_login_cookie(profile_dir):
            return False  # da dang nhap san
        if self.manager.is_running(account):
            self.manager.close(account)
            time.sleep(1.5)
        # Chua chay lan nao thi chua co cookies.sqlite de ghi vao -> khoi tao truoc.
        if not self.manager.is_initialized(account):
            try:
                self.manager.initialize(account)
            except ProfileError:
                return False
        try:
            written = self._apply_cookie(account, replace=True)
        except cookie_module.CookieError:
            return False
        return written > 0

    def relogin_cookie(self) -> None:
        """Nap lai cookie da luu (ke ca khi da dang nhap) roi mo thang Facebook.

        Dung khi phien Facebook het han nhung cookie ``c_user`` cu van con, luc do
        ``open_profiles`` se khong tu nap lai vi tuong da dang nhap.
        """
        selected = self._require_selection()
        if not selected:
            return
        usable = [a for a in selected if self.manager.is_installed(a) and a.cookie.strip()]
        skipped = len(selected) - len(usable)
        if not usable:
            messagebox.showinfo(
                "Đăng nhập với cookie",
                "Các acc đã chọn chưa có profile hoặc chưa lưu cookie.",
                parent=self,
            )
            return

        # Phai vao thang Facebook thi trinh duyet moi bao lai duoc ket qua
        # (xem ProfileManager.verify_cookie_login). Trang khoi dong khac thi bo qua.
        url = self.settings.start_url
        if "facebook.com" not in (url or "").lower():
            url = "https://www.facebook.com/"
        workers = max(1, min(8, self.settings.login_threads or 5))
        workers = min(workers, len(usable))

        def work():
            lock = threading.Lock()
            ok, dead, errors = [], [], []
            done = 0

            def login(account: Account) -> None:
                nonlocal done
                try:
                    if self.manager.is_running(account):
                        self.manager.close(account)
                        time.sleep(1.5)
                    if not self.manager.is_initialized(account):
                        self.manager.initialize(account)
                    self._apply_cookie(account, replace=True)

                    self.manager.clear_login_probe(account)
                    self.manager.launch(account, url=url)
                    self.store.mark_opened(account.id)
                    # Vao duoc thi dong luon de nhuong cho acc tiep theo.
                    if self.manager.verify_cookie_login(account):
                        account.cookie_ok = time.strftime("%Y-%m-%d %H:%M")
                        with lock:
                            ok.append(account.id)
                    else:
                        # Xoa dau da dang nhap: dong tro lai mau trang.
                        account.cookie_ok = ""
                        with lock:
                            dead.append(account.id)
                    self.manager.close(account)
                except (ProfileError, cookie_module.CookieError, OSError) as exc:
                    with lock:
                        errors.append(f"{account.id}: {exc}".replace(chr(10), " ")[:150])
                finally:
                    with lock:
                        done += 1
                        self.set_status(
                            f"[{done}/{len(usable)}] xong {account.id} — "
                            f"vào được {len(ok)}, cookie chết {len(dead)}"
                        )

            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(login, usable))

            self.store.save()
            self._post(self.refresh)
            tail = f" (bỏ qua {skipped} acc thiếu cookie/profile)" if skipped else ""
            self.set_status(
                f"Vào được {len(ok)}/{len(usable)} acc, cookie chết {len(dead)}{tail}."
            )
            if dead or errors:
                report = ""
                if dead:
                    report += ("Cookie đã chết (Facebook xoá phiên), cần đăng nhập tay:\n"
                               + ", ".join(dead[:15]))
                    if len(dead) > 15:
                        report += f" ... (+{len(dead) - 15})"
                if errors:
                    report += ("\n\nLỗi:\n" + "\n".join(errors[:8]))
                self._post(lambda: messagebox.showwarning(
                    "Đăng nhập với cookie", report.strip(), parent=self))

        self._run_async(work, "Đăng nhập với cookie xong.")

    def close_profiles(self) -> None:
        selected = self._require_selection()
        if not selected:
            return

        def work():
            total = 0
            for account in selected:
                total += self.manager.close(account)
            self.set_status(f"Đã đóng {total} tiến trình.")

        self._run_async(work, "Đã đóng profile đã chọn.")

    def scan_existing(self) -> None:
        """Tim cac thu muc profile co san tren o dia va them vao bang."""
        root = self.settings.profiles_root
        found = []
        try:
            names = sorted(os.listdir(root))
        except OSError as exc:
            messagebox.showerror("Quét thư mục", str(exc), parent=self)
            return
        for name in names:
            if self.store.get(name) or not os.path.isdir(os.path.join(root, name)):
                continue
            # Nhan ca thu muc bo cuc khong chuan; create() se don ve dung cho.
            if self.manager.find_existing_launcher(Account(id=name)):
                found.append(name)
        if not found:
            messagebox.showinfo(
                "Quét thư mục",
                "Không thấy profile nào chưa có trong bảng.",
                parent=self,
            )
            return
        preview = "\n".join(found[:20])
        if len(found) > 20:
            preview += f"\n... và {len(found) - 20} thư mục nữa."
        if not messagebox.askyesno(
            "Quét thư mục", f"Thêm {len(found)} profile có sẵn vào bảng?\n\n{preview}", parent=self
        ):
            return
        for name in found:
            self.store.add(Account(id=name, note="Thêm từ thư mục có sẵn"))
        self.refresh()
        self.set_status(f"Đã thêm {len(found)} acc từ thư mục có sẵn.")

    def change_proxy(self) -> None:
        """Đổi proxy cho acc đang chọn (chuột phải > Đổi proxy)."""
        selected = self._require_selection()
        if not selected:
            return
        if len(selected) > 1:
            self.bulk_proxy()
            return
        account = selected[0]
        running = self.manager.is_installed(account) and self.manager.is_running(account)
        proxy = ProxyDialog(self, account, running=running).show()
        if proxy is None:
            return
        self._apply_proxy_change([(account, proxy)])

    def bulk_proxy(self) -> None:
        selected = self._require_selection()
        if not selected:
            return
        proxies = BulkProxyDialog(self, len(selected)).show()
        if proxies is None:
            return
        if proxies and len(proxies) not in (1, len(selected)):
            if not messagebox.askyesno(
                "Số lượng lệch",
                f"Có {len(proxies)} proxy cho {len(selected)} acc.\n"
                "Proxy sẽ được dùng lặp vòng. Tiếp tục?",
                parent=self,
            ):
                return
        self._apply_proxy_change([
            (account, proxies[index % len(proxies)] if proxies else Proxy())
            for index, account in enumerate(selected)
        ])

    def match_identities(self, accounts: Optional[list[Account]] = None) -> None:
        """Dò quốc gia thật của proxy rồi đặt múi giờ + ngôn ngữ cho khớp."""
        selected = accounts if accounts is not None else self._require_selection()
        if not selected:
            return
        targets = [a for a in selected if a.get_proxy().enabled]
        skipped = len(selected) - len(targets)
        if not targets:
            messagebox.showinfo(
                "Khớp theo proxy",
                "Các acc đã chọn chưa gán proxy nên không có gì để dò.",
                parent=self,
            )
            return

        def work():
            done = 0
            errors: list[str] = []
            for number, account in enumerate(targets, start=1):
                self.set_status(f"[{number}/{len(targets)}] Đang dò vị trí {account.id}...")
                try:
                    identity = self.manager.match_identity(account)
                except (geoip.GeoLookupError, ProfileError, OSError) as exc:
                    errors.append(f"{account.id}: {exc}".replace("\n", " ")[:160])
                    continue
                done += 1
                self.set_status(f"[{number}/{len(targets)}] {account.id} → {identity.summary()}")
            self.store.save()
            if errors:
                report = f"Khớp được {done}/{len(targets)} acc.\n\nKhông dò được:\n" + "\n".join(errors[:10])
                self._post(lambda: messagebox.showwarning("Khớp theo proxy", report, parent=self))

        note = f" ({skipped} acc chưa có proxy, bỏ qua)" if skipped else ""
        self._run_async(work, f"Đã khớp múi giờ + ngôn ngữ theo proxy{note}.")

    def clear_identities(self) -> None:
        """Trả profile về múi giờ và ngôn ngữ mặc định của máy."""
        selected = self._require_selection()
        if not selected:
            return
        for account in selected:
            try:
                self.manager.clear_identity(account)
            except ProfileError:
                account.set_identity(None)
        self.store.save()
        self.refresh()
        self.set_status(f"Đã bỏ khớp múi giờ cho {len(selected)} acc.")

    def _apply_proxy_change(self, pairs: list[tuple[Account, Proxy]]) -> None:
        """Gán proxy rồi áp dụng; acc đang mở thì hỏi để khởi động lại."""
        live: list[Account] = []
        restart: list[Account] = []
        for account, proxy in pairs:
            # Proxy moi thi ket qua test cu khong con y nghia -> tra cot "Trang
            # thai" ve trang thai acc cho toi khi test lai.
            account.proxy_status = ""
            account.proxy_checked = ""
            try:
                outcome = self.manager.set_proxy(account, proxy)
            except ProfileError:
                account.set_proxy(proxy)
                outcome = "saved"
            if outcome == "live":
                live.append(account)
            elif outcome == "restart":
                restart.append(account)
        self.store.save()
        self.refresh()

        summary = f"Đã đổi proxy cho {len(pairs)} acc."
        if live:
            summary += f" {len(live)} acc đang mở đã áp dụng ngay."
        self.set_status(summary)

        # Proxy đổi thì quốc gia đổi theo, nên múi giờ + ngôn ngữ phải dò lại.
        rematch = [
            account for account, proxy in pairs
            if account.auto_identity and proxy.enabled
        ]

        if restart:
            names = ", ".join(a.id for a in restart[:5])
            if len(restart) > 5:
                names += f" ... (+{len(restart) - 5})"
            if not messagebox.askyesno(
                "Cần mở lại trình duyệt",
                f"{len(restart)} acc đang mở. Firefox chỉ đọc cấu hình proxy lúc khởi động "
                f"nên phải mở lại mới ăn proxy mới:\n{names}\n\nKhởi động lại ngay?",
                parent=self,
            ):
                restart = []

        if not rematch and not restart:
            return

        def work():
            errors: list[str] = []
            # Dò múi giờ TRƯỚC khi mở lại, để trình duyệt mở lên là đã đúng luôn.
            for number, account in enumerate(rematch, start=1):
                self.set_status(f"[{number}/{len(rematch)}] Đang dò vị trí {account.id}...")
                try:
                    identity = self.manager.match_identity(account)
                    self.set_status(f"{account.id} → {identity.summary()}")
                except (geoip.GeoLookupError, ProfileError, OSError) as exc:
                    errors.append(f"{account.id}: {exc}".replace("\n", " ")[:160])
            if rematch:
                self.store.save()

            for number, account in enumerate(restart, start=1):
                self.set_status(f"[{number}/{len(restart)}] Đang mở lại {account.id}...")
                self.manager.restart(account)

            if errors:
                report = ("Đổi proxy xong nhưng không dò được vị trí của:\n"
                          + "\n".join(errors[:10])
                          + "\n\nMúi giờ và ngôn ngữ vẫn giữ như cũ.")
                self._post(lambda: messagebox.showwarning("Khớp theo proxy", report, parent=self))

        done = []
        if rematch:
            done.append(f"khớp múi giờ cho {len(rematch)} acc")
        if restart:
            done.append(f"mở lại {len(restart)} trình duyệt")
        self._run_async(work, "Đã " + " và ".join(done) + ".")

    def check_proxies(self) -> None:
        """Test proxy cua cac acc dang chon, ghi Live/Die vao cot "Trang thai".

        Ket qua duoc luu vao acc chu khong chi hien mot lan roi mat, nen tat tool
        mo lai van con thay proxy nao da chet.
        """
        selected = self._require_selection()
        if not selected:
            return
        targets = [a for a in selected if a.get_proxy().enabled]
        if not targets:
            messagebox.showinfo("Test proxy", "Các acc đã chọn chưa gán proxy.", parent=self)
            return

        def work():
            lines = []
            ip_of: dict[str, str] = {}   # acc id -> exit IP (de tim trung dai)
            song = 0
            for number, account in enumerate(targets, start=1):
                self.set_status(f"[{number}/{len(targets)}] Đang kiểm tra proxy của {account.id}...")
                ok, detail = test_proxy(account.get_proxy())
                account.proxy_status = "Live" if ok else "Die"
                account.proxy_checked = time.strftime("%Y-%m-%d %H:%M")
                lines.append(f"{'✔' if ok else '✖'} {account.id}: {detail}")
                if ok:
                    song += 1
                    ip = _extract_exit_ip(detail)
                    if ip:
                        ip_of[account.id] = ip
                # Hien ngay tung dong xong, khong bat nguoi dung doi het ca lo.
                self._post(self.refresh)

            self.store.save()
            self._post(self.refresh)
            self.set_status(
                f"Proxy sống {song}/{len(targets)}, chết {len(targets) - song}."
            )

            warning = _duplicate_subnet_report(ip_of)
            chet = [line for line in lines if line.startswith("✖")]
            # Chi bung hop thoai khi that su co gi can doc: proxy chet hoac trung dai.
            if chet or warning:
                report = chr(10).join(chet)
                if warning:
                    report = (report + chr(10) * 2 + warning) if report else warning
                self._post(lambda: messagebox.showinfo(
                    "Kết quả test proxy", report, parent=self))

        self._run_async(work, "Kiểm tra proxy xong.")

    def edit_cookie(self) -> None:
        selected = self._require_selection(single=True)
        if not selected:
            return
        account = selected[0]
        current = 0
        if self.manager.is_installed(account):
            current = len(cookie_module.read_from_profile(self.manager.profile_dir(account)))
        result = CookieDialog(self, account, current).show()
        if not result:
            return

        account.cookie = result["text"]
        self.store.save()
        if not result["apply"]:
            self.refresh()
            self.set_status("Đã lưu cookie vào danh sách.")
            return

        if not self.manager.is_installed(account):
            messagebox.showwarning("Chưa có profile", "Hãy tạo profile cho acc này trước.", parent=self)
            return
        if self.manager.is_running(account):
            if not messagebox.askyesno(
                "Profile đang mở",
                "Firefox của acc này đang chạy nên không ghi cookie được.\nĐóng lại rồi nạp?",
                parent=self,
            ):
                return
            self.manager.close(account)
            time.sleep(1.5)

        def work():
            self.manager.initialize(account, on_status=self.set_status)
            written = self._apply_cookie(account, replace=result["replace"], domain=result["domain"])
            self.set_status(f"Đã nạp {written} cookie vào profile {account.id}.")

        self._run_async(work, "Nạp cookie xong.")

    def _apply_cookie(self, account: Account, replace: bool, domain: str = ".facebook.com") -> int:
        parsed = cookie_module.parse(account.cookie, default_domain=domain)
        if not parsed:
            return 0
        return cookie_module.write_to_profile(
            self.manager.profile_dir(account), parsed, replace_all=replace
        )

    def save_cookie_from_profile(self) -> None:
        """Lay cookie dang song trong profile ghi nguoc vao acc.

        Dung sau khi dang nhap tay: phien cu chet thi cookie da luu cung chet,
        phai chep lai cookie moi thi lan sau "Dang nhap voi cookie" moi an.
        """
        selected = self._require_selection()
        if not selected:
            return
        usable = [a for a in selected if self.manager.is_installed(a)]
        if not usable:
            messagebox.showinfo("Lưu cookie", "Các acc đã chọn chưa có profile.", parent=self)
            return

        saved, empty, running = 0, [], []
        for account in usable:
            if self.manager.is_running(account):
                # Firefox giu cookie trong bo nho, chua ghi het xuong file.
                running.append(account.id)
            found = cookie_module.read_from_profile(self.manager.profile_dir(account))
            names = {c.name for c in found}
            if "c_user" not in names:
                empty.append(account.id)
                continue
            account.cookie = cookie_module.to_json(found)
            saved += 1
        self.store.save()
        self.refresh()

        report = f"Đã lưu cookie của {saved}/{len(usable)} acc."
        if empty:
            report += ("\n\nChưa đăng nhập (không thấy c_user), bỏ qua:\n"
                       + ", ".join(empty[:10]))
        if running:
            report += ("\n\nĐang mở nên cookie có thể chưa đầy đủ — đóng trình duyệt "
                       "rồi lưu lại cho chắc:\n" + ", ".join(running[:10]))
        if empty or running:
            messagebox.showwarning("Lưu cookie", report, parent=self)
        self.set_status(report.splitlines()[0])

    def export_cookie(self) -> None:
        selected = self._require_selection(single=True)
        if not selected:
            return
        account = selected[0]
        if not self.manager.is_installed(account):
            messagebox.showinfo("Xuất cookie", "Acc này chưa có profile.", parent=self)
            return
        found = cookie_module.read_from_profile(self.manager.profile_dir(account))
        if not found:
            messagebox.showinfo("Xuất cookie", "Profile chưa có cookie nào.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".json",
            initialfile=f"{account.folder}_cookies.json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(cookie_module.to_json(found))
        self.set_status(f"Đã xuất {len(found)} cookie ra {path}.")

    def copy_2fa(self) -> None:
        selected = self._require_selection(single=True)
        if not selected:
            return
        account = selected[0]
        if not account.twofa.strip():
            messagebox.showinfo("Mã 2FA", "Acc này chưa lưu secret 2FA.", parent=self)
            return
        try:
            code = totp.generate(account.twofa)
        except Exception:
            messagebox.showerror("Mã 2FA", "Secret 2FA không hợp lệ.", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(code)
        self.set_status(f"Đã copy mã 2FA của {account.id}: {code} (còn {totp.seconds_remaining()}s)")

    def _copy_field(self, field: str) -> None:
        selected = self._selected_accounts()
        if not selected:
            return
        values = [str(getattr(account, field, "") or "") for account in selected]
        self.clipboard_clear()
        self.clipboard_append("\n".join(values))
        self.set_status(f"Đã copy {field} của {len(values)} acc.")

    def install_extension(self) -> None:
        """Cài file .xpi đã ký vào profile của các acc đã chọn."""
        selected = self._require_selection()
        if not selected:
            return
        usable = [a for a in selected if self.manager.is_installed(a)]
        if not usable:
            messagebox.showinfo("Extension", "Các acc đã chọn chưa có profile.", parent=self)
            return

        xpi = (self.settings.extension_xpi or "").strip()
        if not os.path.isfile(xpi):
            xpi = filedialog.askopenfilename(
                parent=self,
                title="Chọn file extension đã ký (.xpi)",
                filetypes=[("Firefox extension", "*.xpi")],
            )
            if not xpi:
                return

        # Kiem tra chu ky mot lan truoc khi dung toi profile nao.
        try:
            addon_id, version = self.manager.read_extension_info(xpi)
        except ProfileError as exc:
            messagebox.showerror("Extension", str(exc), parent=self)
            return

        running = [a.id for a in usable if self.manager.is_running(a)]
        question = f"Cài {addon_id} v{version} vào {len(usable)} acc?"
        if running:
            question += ("\n\nCác acc sau đang mở, sẽ được đóng trước khi cài "
                         "(Firefox chỉ quét thư mục extension lúc khởi động):\n"
                         + ", ".join(running[:8]))
        if not messagebox.askyesno("Extension", question, parent=self):
            return

        self.settings.extension_xpi = xpi
        self.settings.save()

        def work():
            done, errors = 0, []
            for number, account in enumerate(usable, start=1):
                self.set_status(f"[{number}/{len(usable)}] Cài extension cho {account.id}...")
                if self.manager.is_running(account):
                    self.manager.close(account)
                    time.sleep(1.5)
                try:
                    self.manager.install_extension(account, xpi)
                    done += 1
                except (ProfileError, OSError) as exc:
                    errors.append(f"{account.id}: {exc}")
            if errors:
                report = (f"Cài được {done}/{len(usable)}.\n\nLỗi:\n" + "\n".join(errors[:8]))
                self._post(lambda: messagebox.showwarning("Extension", report, parent=self))

        self._run_async(
            work,
            f"Đã cài {addon_id} v{version}. Mở lại trình duyệt để Firefox nhận addon.",
        )

    def remove_extension(self) -> None:
        """Gỡ extension khỏi profile của các acc đã chọn."""
        selected = self._require_selection()
        if not selected:
            return
        found = {}
        for account in selected:
            for name in self.manager.installed_extensions(account):
                found.setdefault(name[:-4], []).append(account)
        if not found:
            messagebox.showinfo(
                "Extension", "Các acc đã chọn chưa cài extension nào.", parent=self
            )
            return

        names = ", ".join(sorted(found))
        if not messagebox.askyesno(
            "Extension",
            f"Gỡ {names} khỏi {len(selected)} acc?\n\nAcc đang mở sẽ được đóng trước.",
            parent=self,
        ):
            return

        def work():
            removed = 0
            for addon_id, accounts in found.items():
                for account in accounts:
                    if self.manager.is_running(account):
                        self.manager.close(account)
                        time.sleep(1.5)
                    if self.manager.remove_extension(account, addon_id):
                        removed += 1
            self.set_status(f"Đã gỡ extension khỏi {removed} profile.")

        self._run_async(work, "Gỡ extension xong.")

    def clear_cache(self) -> None:
        """Xoá cache trình duyệt của các acc đã chọn, giữ nguyên đăng nhập."""
        selected = self._require_selection()
        if not selected:
            return
        targets = [a for a in selected if self.manager.is_installed(a)]
        if not targets:
            messagebox.showinfo(
                "Xoá cache", "Các acc đã chọn chưa tạo profile.", parent=self
            )
            return

        total = sum(self.manager.cache_size(a) for a in targets)
        if not total:
            messagebox.showinfo("Xoá cache", "Không có cache nào để xoá.", parent=self)
            return

        running = [a for a in targets if self.manager.is_running(a)]
        question = (
            f"Xoá cache của {len(targets)} acc, giải phóng {total / 1024 / 1024:.0f} MB?\n\n"
            "Cookie, đăng nhập và cài đặt được giữ nguyên — chỉ xoá file tạm."
        )
        if running:
            names = ", ".join(a.id for a in running[:5])
            if len(running) > 5:
                names += f" ... (+{len(running) - 5})"
            question += (
                f"\n\n{len(running)} acc đang mở, phải đóng trước khi xoá:\n{names}"
            )
        if not messagebox.askyesno("Xoá cache", question, parent=self):
            return

        def work():
            freed = 0
            errors: list[str] = []
            for number, account in enumerate(targets, start=1):
                self.set_status(f"[{number}/{len(targets)}] Đang xoá cache {account.id}...")
                if self.manager.is_running(account):
                    self.manager.close(account)
                    time.sleep(1.5)
                try:
                    freed += self.manager.clear_cache(account)
                except (ProfileError, OSError) as exc:
                    errors.append(f"{account.id}: {exc}")
            self._post(self.refresh)
            if errors:
                report = (f"Giải phóng {freed / 1024 / 1024:.0f} MB.\n\nKhông xoá được:\n"
                          + "\n".join(errors[:10]))
                self._post(lambda: messagebox.showwarning("Xoá cache", report, parent=self))
            else:
                self.set_status(f"Đã xoá cache, giải phóng {freed / 1024 / 1024:.0f} MB.")

        self._run_async(work, "Xoá cache xong.")

    def cleanup_installers(self) -> None:
        """Xoá bản sao *.paf.exe còn sót trong thư mục các acc đã chọn."""
        selected = self._require_selection()
        if not selected:
            return
        targets = [a for a in selected if self.manager.is_installed(a)]
        files: list[str] = []
        for account in targets:
            files.extend(self.manager.installer_copies(account))
        if not files:
            messagebox.showinfo(
                "Dọn file cài đặt",
                "Không còn file cài đặt thừa trong các acc đã chọn.",
                parent=self,
            )
            return

        total = 0
        for path in files:
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
        if not messagebox.askyesno(
            "Dọn file cài đặt",
            f"Xoá {len(files)} bản sao installer, giải phóng {total / 1024 / 1024:.0f} MB?\n\n"
            "Profile đã cài xong nên không cần các file này nữa.",
            parent=self,
        ):
            return

        freed = sum(self.manager.cleanup_installer(account) for account in targets)
        self.refresh()
        self.set_status(f"Đã giải phóng {freed / 1024 / 1024:.0f} MB.")

    def open_folder(self) -> None:
        selected = self._require_selection(single=True)
        if not selected:
            return
        target = self.manager.account_dir(selected[0])
        if not os.path.isdir(target):
            messagebox.showinfo("Thư mục", "Thư mục chưa tồn tại.", parent=self)
            return
        subprocess.Popen(["explorer", os.path.normpath(target)])

    def open_settings(self) -> None:
        old_root = self.settings.profiles_root
        if not SettingsDialog(self, self.settings).show():
            return
        self.settings.save()
        self.manager.settings = self.settings
        self._apply_theme()
        self.refresh()
        self.set_status("Đã lưu cài đặt.")

        if os.path.normcase(os.path.abspath(old_root)) != os.path.normcase(
            os.path.abspath(self.settings.profiles_root)
        ):
            self._offer_move(old_root)

    def _offer_move(self, old_root: str) -> None:
        """Thư mục gốc vừa đổi — hỏi có chuyển các profile hiện có sang không."""
        movable = [
            account for account in self.store
            if os.path.isdir(os.path.join(old_root, account.folder))
        ]
        if not movable:
            return
        if not messagebox.askyesno(
            "Chuyển profile",
            f"Thư mục lưu profile đã đổi:\n{old_root}\n→ {self.settings.profiles_root}\n\n"
            f"Chuyển {len(movable)} profile hiện có sang chỗ mới?\n"
            "Trình duyệt nào đang mở sẽ bị đóng trước khi chuyển.\n\n"
            "Chọn 'No' nếu bạn muốn tự chuyển bằng tay.",
            parent=self,
        ):
            return

        def work():
            moved, errors = self.manager.move_to_root(movable, old_root, on_status=self.set_status)
            report = f"Đã chuyển {moved}/{len(movable)} profile."
            if errors:
                report += "\n\nKhông chuyển được:\n" + "\n".join(errors[:10])
            self._post(lambda: messagebox.showinfo("Chuyển profile", report, parent=self))

        self._run_async(work, "Chuyển profile xong.")

    # ------------------------------------------------------------------
    def sign_out(self) -> None:
        """Xoa dang nhap da luu roi quay ve man dang nhap.

        Khong dong han tool: an cua so chinh roi mo lai cong dang nhap ngay
        trong tien trinh nay, dang nhap xong thi hien lai. Danh sach acc va
        profile la cua may chu khong phai cua tai khoan LVC nen khong can dung
        lai gi -- chi doi ten hien tren header.
        """
        if not messagebox.askyesno(
                "Đăng xuất",
                "Xoá tài khoản và key tool đã lưu trên máy này?\n"
                "Bạn sẽ quay lại màn hình đăng nhập.",
                parent=self):
            return
        login.sign_out()

        self.withdraw()
        session = login.gate(self)
        if session is None:      # dong luon man dang nhap = thoat tool
            self._on_close()
            return
        self.session = session
        self._update_account_label()
        self._show_after_login()

    def _on_close(self) -> None:
        # Proxy nam trong mozilla.cfg cua tung profile, khong con di qua relay cua
        # tool nua -- dong tool khong con lam trinh duyet mat mang.
        self.relays.stop_all()
        self.destroy()


_IP_RE = re.compile(r"IP ra ngoài:\s*([0-9a-fA-F:.]+)")


def _extract_exit_ip(detail: str) -> str:
    match = _IP_RE.search(detail or "")
    return match.group(1).strip() if match else ""


def _subnet_key(ip: str) -> str:
    """Khoa gom nhom: IPv6 tinh theo /64, IPv4 theo tung dia chi.

    Google dem han muc IPv6 theo ca khoi /64, nen nhieu acc chung /64 se bi coi
    la mot nguon -> de dinh CAPTCHA du dia chi day du khac nhau.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    if addr.version == 6:
        net = ipaddress.ip_network(f"{ip}/64", strict=False)
        return f"{net.network_address}/64"
    return str(addr)


def _duplicate_subnet_report(ip_of: dict) -> str:
    """Canh bao cac acc co exit IP trung dai (cung /64 IPv6 hoac cung IPv4)."""
    groups: dict[str, list[str]] = {}
    for account_id, ip in ip_of.items():
        key = _subnet_key(ip)
        if key:
            groups.setdefault(key, []).append(account_id)

    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    if not dupes:
        return ""

    lines = ["⚠ CẢNH BÁO: nhiều acc dùng chung dải IP → Google dễ bắt CAPTCHA:"]
    for key, ids in dupes.items():
        kind = "/64 (IPv6)" if "/64" in key else "IP (IPv4)"
        lines.append(f"  • {len(ids)} acc chung {kind} {key}:")
        lines.append("      " + ", ".join(ids))
    lines.append("  → Nên cho mỗi acc một dải IP khác nhau (đổi proxy/IP).")
    return "\n".join(lines)


def run() -> None:
    app = App()
    if app.session is None:   # nguoi dung dong cong dang nhap
        return
    app.mainloop()
