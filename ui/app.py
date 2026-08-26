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
from core import totp
from core.config import Settings
from core.profiles import ProfileError, ProfileManager
from core.proxy import Proxy
from core.proxy_relay import RelayManager, test_proxy
from core.store import Account, AccountStore, STATUSES

from .dialogs import (
    AccountDialog,
    BulkImportDialog,
    BulkProxyDialog,
    CookieDialog,
    GroupManagerDialog,
    NoteDialog,
    ProxyDialog,
    SettingsDialog,
    SimplePromptDialog,
)

PAD = 8

# Treeview va tk.Menu khong tu doi mau theo customtkinter, phai to tay.
THEMES = {
    "light": {
        "row_bg": "#ffffff",
        "row_fg": "#1c1c1c",
        "head_bg": "#e9e9ec",
        "head_fg": "#2b2b2b",
        "head_hover": "#dadade",
        "selected": "#1f6aa5",
        "running_bg": "#d5efdd",
        "missing_fg": "#8d8d8d",
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
        "running_bg": "#1d3b2a",
        "missing_fg": "#9a9a9a",
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
    ("cookie", "Cookie", 80, "center"),
    ("proxy", "Proxy", 210, "w"),
    ("identity", "Múi giờ / Ngôn ngữ", 200, "w"),
    ("group", "Nhóm", 110, "w"),
    ("status", "Trạng thái", 95, "center"),
    ("profile", "Profile", 90, "center"),
    ("running", "Đang chạy", 85, "center"),
    ("note", "Ghi chú", 220, "w"),
)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_default_color_theme("blue")

        self.title("LVC Manager Profile")
        self.geometry("1500x820")
        self.minsize(1100, 600)
        self._set_window_icon()

        self.settings = Settings.load()
        self.settings.save()  # ghi lai duong dan paf.exe tim duoc o lan chay dau
        ctk.set_appearance_mode(self.settings.appearance)
        self.store = AccountStore()
        self.relays = RelayManager()
        self.manager = ProfileManager(self.settings, self.relays)

        self._events: queue.Queue = queue.Queue()
        self._busy = False
        self._show_secrets = tk.BooleanVar(value=False)
        self._rows: list[Account] = []
        self._menus: list[tk.Menu] = []

        self._build_header()
        self._build_toolbar()
        self._build_table()
        self._build_statusbar()
        self._apply_theme()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_events)
        self.refresh()
        self._schedule_running_check()

    # ------------------------------------------------------------------
    # Dung giao dien
    # ------------------------------------------------------------------
    def _set_window_icon(self) -> None:
        """Dat icon cua so + thanh tac vu bang logo LVC."""
        try:
            ico = config.resource_path("assets", "logo.ico")
            if os.path.isfile(ico):
                self.iconbitmap(default=ico)
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

    def _build_toolbar(self) -> None:
        filters = ctk.CTkFrame(self, fg_color="transparent")
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

        self.count_label = ctk.CTkLabel(filters, text="", text_color="gray60")
        self.count_label.pack(side="right", padx=6)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=PAD, pady=(0, PAD))

        def button(text, command, color=None, width=118):
            kwargs = {"fg_color": color} if color else {}
            btn = ctk.CTkButton(actions, text=text, width=width, command=command, **kwargs)
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
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        button("🌐 Proxy hàng loạt", self.bulk_proxy, width=150)
        button("📡 Test proxy", self.check_proxies, width=120)
        button("🍪 Cookie", self.edit_cookie, width=100)
        button("🔑 Mã 2FA", self.copy_2fa, width=100)

    def _build_table(self) -> None:
        wrapper = ctk.CTkFrame(self)
        wrapper.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Accounts.Treeview", rowheight=28, borderwidth=0)
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

        vertical = ttk.Scrollbar(wrapper, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(wrapper, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)


        self.tree.bind("<Double-1>", lambda _e: self.open_profiles())
        self.tree.bind("<Button-3>", self._popup_menu)
        # Keo chuot de quet chon nhieu dong (rubber-band). Treeview khong co san.
        self._drag_anchor = None
        self.tree.bind("<Button-1>", self._drag_start)
        self.tree.bind("<B1-Motion>", self._drag_select)

        self._menu = self._make_menu(self)

        # Viec hay dung nhat len tren; "Tao profile" chi lam mot lan cho moi acc
        # nen de xuong duoi, tranh bam nham vao no khi dinh mo profile.
        self._menu.add_command(label="▶ Mở profile", command=self.open_profiles)
        self._menu.add_command(label="🔑 Đăng nhập với cookie", command=self.relogin_cookie)
        self._menu.add_command(label="⏹ Đóng profile", command=self.close_profiles)
        self._menu.add_command(label="🧩 Tạo profile", command=self.create_profiles)
        self._menu.add_separator()

        # Danh sach nhom doi theo thoi gian nen dung lai moi lan bung menu.
        self._group_menu = self._make_menu(self._menu)
        self._menu.add_cascade(label="🗂 Chuyển vào nhóm", menu=self._group_menu)
        self._menu.add_command(label="📝 Sửa ghi chú...", command=self.edit_note)
        self._menu.add_separator()

        self._menu.add_command(label="🌐 Đổi proxy...", command=self.change_proxy)
        self._menu.add_command(label="📡 Test proxy", command=self.check_proxies)
        self._menu.add_command(label="🌍 Khớp múi giờ + ngôn ngữ theo proxy",
                               command=self.match_identities)
        self._menu.add_command(label="🌍 Bỏ khớp múi giờ", command=self.clear_identities)
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
        self._menu.add_cascade(label="📋 Chép", menu=copy_menu)
        self._menu.add_separator()

        self._menu.add_command(label="Mở thư mục profile", command=self.open_folder)
        self._menu.add_command(label="🧽 Xoá cache trình duyệt", command=self.clear_cache)
        self._menu.add_command(label="🧹 Xoá file cài đặt thừa", command=self.cleanup_installers)
        self._menu.add_command(label="Xuất cookie từ profile", command=self.export_cookie)
        self._menu.add_separator()
        self._menu.add_command(label="Xoá acc", command=self.delete_accounts)

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
        style.map("Accounts.Treeview",
                  background=[("selected", colors["selected"])],
                  foreground=[("selected", "#ffffff")])
        style.map("Accounts.Treeview.Heading", background=[("active", colors["head_hover"])])

        self.tree.tag_configure("running", background=colors["running_bg"])
        self.tree.tag_configure("missing", foreground=colors["missing_fg"])

        for menu in self._menus:
            menu.configure(
                bg=colors["menu_bg"], fg=colors["menu_fg"],
                activebackground=colors["selected"], activeforeground="#ffffff",
            )

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
                             tags=self._row_tags(account))
        for item in selected:
            if self.tree.exists(item):
                self.tree.selection_add(item)

        self.count_label.configure(text=f"{len(self._rows)}/{len(self.store)} acc")

    def _row_values(self, index: int, account: Account) -> tuple:
        show = self._show_secrets.get()
        proxy = account.get_proxy()
        installed = self.manager.is_installed(account)
        cookie_count = self._cookie_count(account)
        return (
            index,
            account.id,
            (account.password or "") if show else ("•" * min(len(account.password), 10) or "—"),
            account.recovery_mail or "—",
            "có" if account.twofa else "—",
            f"{cookie_count}" if cookie_count else "—",
            proxy.display(mask=not show) or "—",
            self._identity_cell(account),
            account.group or "—",
            account.status or "—",
            "đã tạo" if installed else "chưa tạo",
            "▶" if installed and self.manager.is_running(account) else "",
            (account.note or "").replace("\n", " ")[:120],
        )

    @staticmethod
    def _identity_cell(account: Account) -> str:
        identity = account.get_identity()
        if not identity.enabled:
            return "chưa khớp" if account.get_proxy().enabled else "—"
        language = (identity.accept_languages or "").split(",")[0].strip()
        return " · ".join(p for p in (identity.timezone, language) if p)

    def _row_tags(self, account: Account) -> tuple:
        if not self.manager.is_installed(account):
            return ("missing",)
        if self.manager.is_running(account):
            return ("running",)
        return ()

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

    def _drag_start(self, event) -> None:
        """Ghi lai dong bam xuong lam moc cho thao tac keo chon."""
        # Bam tren tieu de cot / vung thay doi do rong -> khong phai keo chon.
        if self.tree.identify_region(event.x, event.y) in ("heading", "separator"):
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
            for account in self._rows:
                if self.tree.exists(account.id):
                    self.tree.item(account.id, tags=self._row_tags(account))
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

        url = self.settings.start_url

        def work():
            done = 0
            for number, account in enumerate(usable, start=1):
                self.set_status(f"[{number}/{len(usable)}] Nạp cookie cho {account.id}...")
                if self.manager.is_running(account):
                    self.manager.close(account)
                    time.sleep(1.5)
                if not self.manager.is_initialized(account):
                    try:
                        self.manager.initialize(account)
                    except ProfileError:
                        continue
                try:
                    written = self._apply_cookie(account, replace=True)
                except cookie_module.CookieError:
                    written = 0
                if written:
                    done += 1
                self.manager.launch(account, url=url)
                self.store.mark_opened(account.id)
                time.sleep(1.2)
            tail = f" (bỏ qua {skipped} acc thiếu cookie/profile)" if skipped else ""
            self.set_status(f"Đã đăng nhập bằng cookie {done}/{len(usable)} acc{tail}.")

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
            for number, account in enumerate(targets, start=1):
                self.set_status(f"[{number}/{len(targets)}] Đang kiểm tra proxy của {account.id}...")
                ok, detail = test_proxy(account.get_proxy())
                lines.append(f"{'✔' if ok else '✖'} {account.id}: {detail}")
                if ok:
                    ip = _extract_exit_ip(detail)
                    if ip:
                        ip_of[account.id] = ip

            warning = _duplicate_subnet_report(ip_of)
            report = "\n".join(lines)
            if warning:
                report += "\n\n" + warning
            self._post(lambda: messagebox.showinfo("Kết quả test proxy", report, parent=self))

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
        self.set_status(f"Đã chép mã 2FA của {account.id}: {code} (còn {totp.seconds_remaining()}s)")

    def _copy_field(self, field: str) -> None:
        selected = self._selected_accounts()
        if not selected:
            return
        values = [str(getattr(account, field, "") or "") for account in selected]
        self.clipboard_clear()
        self.clipboard_append("\n".join(values))
        self.set_status(f"Đã chép {field} của {len(values)} acc.")

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
    App().mainloop()
