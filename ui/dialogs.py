"""Cac hop thoai phu: them/sua acc, nhap hang loat, nap cookie, cai dat."""

from __future__ import annotations

import os
import time
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import customtkinter as ctk

from core import cookies as cookie_module
from core import proxy as proxy_module
from core import totp
from core.config import DEFAULT_ROOT, Settings
from core.store import Account, Identity, STATUSES

PAD = 8

# Muc gia trong o chon nhom, tuong duong "khong thuoc nhom nao".
NO_GROUP = "(không nhóm)"

# Nhan hien thi <-> gia tri luu trong settings.appearance.
APPEARANCES = {"Sáng": "light", "Tối": "dark"}
APPEARANCE_LABELS = {value: label for label, value in APPEARANCES.items()}


class BaseDialog(ctk.CTkToplevel):
    """Hop thoai co ban: chan tuong tac voi cua so chinh cho toi khi dong."""

    def __init__(self, parent, title: str, width: int = 560, height: int = 640):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.minsize(460, 420)
        self.result = None
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _event: self._cancel())
        # Cho cua so hien xong roi moi grab, neu khong grab_set se loi tren Windows.
        self.after(120, self._grab)

    def _grab(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result


class AccountDialog(BaseDialog):
    """Nhap / sua thong tin mot acc."""

    def __init__(self, parent, account: Optional[Account] = None, groups: Optional[list[str]] = None):
        editing = account is not None
        super().__init__(parent, "Sửa acc" if editing else "Thêm acc", 620, 720)
        self.account = Account.from_dict(account.to_dict()) if editing else Account()
        self._groups = groups or []

        container = ctk.CTkScrollableFrame(self)
        container.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        container.grid_columnconfigure(1, weight=1)

        row = 0
        self.id_entry = self._field(container, row, "ID acc *", self.account.id)
        row += 1
        self.password_entry = self._field(container, row, "Mật khẩu", self.account.password, secret=True)
        row += 1
        self.mail_entry = self._field(container, row, "Email khôi phục", self.account.recovery_mail)
        row += 1
        self.mailpass_entry = self._field(
            container, row, "Pass email khôi phục", self.account.recovery_mail_password,
            secret=True,
        )
        row += 1
        self.mailbackup_entry = self._field(
            container, row, "Email khôi phục của email KP", self.account.recovery_mail_backup,
        )
        row += 1

        ctk.CTkLabel(container, text="Mã 2FA (secret)").grid(row=row, column=0, sticky="w", padx=PAD, pady=6)
        twofa_frame = ctk.CTkFrame(container, fg_color="transparent")
        twofa_frame.grid(row=row, column=1, sticky="ew", padx=PAD, pady=6)
        twofa_frame.grid_columnconfigure(0, weight=1)
        self.twofa_entry = ctk.CTkEntry(twofa_frame, placeholder_text="Base32 hoặc otpauth://...")
        self.twofa_entry.insert(0, self.account.twofa)
        self.twofa_entry.grid(row=0, column=0, sticky="ew")
        self.twofa_preview = ctk.CTkLabel(twofa_frame, text="------", width=90)
        self.twofa_preview.grid(row=0, column=1, padx=(6, 0))
        row += 1

        ctk.CTkLabel(container, text="Proxy").grid(row=row, column=0, sticky="w", padx=PAD, pady=6)
        proxy_frame = ctk.CTkFrame(container, fg_color="transparent")
        proxy_frame.grid(row=row, column=1, sticky="ew", padx=PAD, pady=6)
        proxy_frame.grid_columnconfigure(0, weight=1)
        self.proxy_entry = ctk.CTkEntry(
            proxy_frame, placeholder_text="ip:port  |  ip:port:user:pass  |  socks5://user:pass@ip:port"
        )
        self.proxy_entry.insert(0, self.account.get_proxy().as_text())
        self.proxy_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(proxy_frame, text="Kiểm tra", width=80, command=self._test_proxy).grid(
            row=0, column=1, padx=(6, 0)
        )
        row += 1

        ctk.CTkLabel(container, text="Múi giờ / Ngôn ngữ").grid(
            row=row, column=0, sticky="w", padx=PAD, pady=6
        )
        identity_frame = ctk.CTkFrame(container, fg_color="transparent")
        identity_frame.grid(row=row, column=1, sticky="ew", padx=PAD, pady=6)
        identity_frame.grid_columnconfigure(0, weight=1)
        self.identity_label = ctk.CTkLabel(identity_frame, text="", anchor="w", wraplength=290, justify="left")
        self.identity_label.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(identity_frame, text="Dò lại", width=70, command=self._match_identity).grid(
            row=0, column=1, padx=(6, 0)
        )
        row += 1

        self.auto_identity = tk.BooleanVar(value=self.account.auto_identity)
        ctk.CTkCheckBox(
            container,
            text="Tự dò lại múi giờ + ngôn ngữ mỗi khi đổi proxy",
            variable=self.auto_identity,
        ).grid(row=row, column=1, sticky="w", padx=PAD, pady=(0, 6))
        row += 1

        self._show_identity()

        ctk.CTkLabel(container, text="Nhóm").grid(row=row, column=0, sticky="w", padx=PAD, pady=6)
        # Chon nhom co san, hoac go thang ten nhom moi vao o nay.
        self.group_box = ctk.CTkComboBox(container, values=[NO_GROUP, *self._groups])
        self.group_box.set(self.account.group or NO_GROUP)
        self.group_box.grid(row=row, column=1, sticky="ew", padx=PAD, pady=6)
        row += 1

        ctk.CTkLabel(
            container,
            text="Chọn nhóm có sẵn hoặc gõ tên nhóm mới.",
            text_color="gray60",
            font=ctk.CTkFont(size=11),
        ).grid(row=row, column=1, sticky="w", padx=PAD, pady=(0, 4))
        row += 1

        ctk.CTkLabel(container, text="Trạng thái").grid(row=row, column=0, sticky="w", padx=PAD, pady=6)
        self.status_box = ctk.CTkOptionMenu(container, values=list(STATUSES))
        self.status_box.set(self.account.status or STATUSES[0])
        self.status_box.grid(row=row, column=1, sticky="ew", padx=PAD, pady=6)
        row += 1

        ctk.CTkLabel(container, text="Ghi chú").grid(row=row, column=0, sticky="nw", padx=PAD, pady=6)
        self.note_box = ctk.CTkTextbox(container, height=70)
        self.note_box.insert("1.0", self.account.note)
        self.note_box.grid(row=row, column=1, sticky="ew", padx=PAD, pady=6)
        row += 1

        ctk.CTkLabel(container, text="Cookie").grid(row=row, column=0, sticky="nw", padx=PAD, pady=6)
        self.cookie_box = ctk.CTkTextbox(container, height=150)
        self.cookie_box.insert("1.0", self.account.cookie)
        self.cookie_box.grid(row=row, column=1, sticky="ew", padx=PAD, pady=6)
        row += 1

        ctk.CTkLabel(
            container,
            text="Cookie nhận JSON (Cookie-Editor), cookies.txt hoặc chuỗi 'ten=gia_tri; ...'.",
            text_color="gray60",
            wraplength=380,
            justify="left",
        ).grid(row=row, column=1, sticky="w", padx=PAD)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(buttons, text="Hủy", width=100, fg_color="gray35", command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text="Lưu", width=100, command=self._save).pack(side="right", padx=6)

        self.id_entry.focus_set()
        self._tick_2fa()

    def _field(self, parent, row: int, label: str, value: str, secret: bool = False) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=PAD, pady=6)
        # Mat khau hien san cho de doi chieu; bam nut con mat de che lai.
        entry = ctk.CTkEntry(parent)
        entry.insert(0, value or "")
        entry.grid(row=row, column=1, sticky="ew", padx=PAD, pady=6)
        if secret:
            def toggle():
                entry.configure(show="•" if not entry.cget("show") else "")
            ctk.CTkButton(parent, text="👁", width=32, command=toggle).grid(row=row, column=2, padx=(0, PAD))
        return entry

    def _tick_2fa(self) -> None:
        if not self.winfo_exists():
            return
        secret = self.twofa_entry.get().strip()
        if secret:
            try:
                self.twofa_preview.configure(
                    text=f"{totp.generate(secret)} ({totp.seconds_remaining()}s)"
                )
            except Exception:
                self.twofa_preview.configure(text="sai secret")
        else:
            self.twofa_preview.configure(text="------")
        self.after(1000, self._tick_2fa)

    def _show_identity(self) -> None:
        identity = self.account.get_identity()
        if identity.enabled:
            language = (identity.accept_languages or "").split(",")[0].strip()
            text = f"{identity.timezone}  ·  {language}"
            if identity.checked_at:
                text += f"   (dò lúc {identity.checked_at})"
            self.identity_label.configure(text=text, text_color="gray75")
        else:
            self.identity_label.configure(
                text="Chưa khớp — đang dùng múi giờ của máy", text_color="gray60"
            )

    def _match_identity(self) -> None:
        """Dò quốc gia của proxy đang nhập rồi suy ra múi giờ + ngôn ngữ."""
        from core import geoip, locales

        try:
            proxy = self._read_proxy()
        except ValueError as exc:
            messagebox.showerror("Proxy", str(exc), parent=self)
            return
        if not proxy.enabled:
            messagebox.showinfo("Múi giờ", "Cần nhập proxy trước đã.", parent=self)
            return

        self.identity_label.configure(text="Đang dò...", text_color="gray60")
        self.update_idletasks()
        try:
            info = geoip.lookup(proxy)
        except (geoip.GeoLookupError, OSError) as exc:
            self._show_identity()
            messagebox.showerror("Múi giờ", str(exc), parent=self)
            return

        self.account.set_identity(
            Identity(
                timezone=info.timezone,
                accept_languages=locales.accept_languages(info.country),
                country=info.country,
                city=info.city,
                ip=info.ip,
                checked_at=time.strftime("%Y-%m-%d %H:%M"),
            )
        )
        self._show_identity()

    def _read_proxy(self) -> proxy_module.Proxy:
        text = self.proxy_entry.get().strip()
        return proxy_module.parse(text) if text else proxy_module.Proxy()

    def _test_proxy(self) -> None:
        try:
            proxy = self._read_proxy()
        except ValueError as exc:
            messagebox.showerror("Proxy", str(exc), parent=self)
            return
        if not proxy.enabled:
            messagebox.showinfo("Proxy", "Chưa nhập proxy.", parent=self)
            return
        from core.proxy_relay import test_proxy

        ok, detail = test_proxy(proxy)
        if ok:
            messagebox.showinfo("Proxy", f"Kết nối được.\n{detail}", parent=self)
        else:
            messagebox.showerror("Proxy", f"Không kết nối được.\n{detail}", parent=self)

    def _save(self) -> None:
        account_id = self.id_entry.get().strip()
        if not account_id:
            messagebox.showerror("Thiếu dữ liệu", "ID acc không được để trống.", parent=self)
            return
        try:
            proxy = self._read_proxy()
        except ValueError as exc:
            messagebox.showerror("Proxy", str(exc), parent=self)
            return

        cookie_text = self.cookie_box.get("1.0", "end").strip()
        if cookie_text:
            try:
                cookie_module.parse(cookie_text, default_domain=".facebook.com")
            except cookie_module.CookieError as exc:
                if not messagebox.askyesno("Cookie", f"{exc}\n\nVẫn lưu?", parent=self):
                    return

        self.account.id = account_id
        self.account.password = self.password_entry.get().strip()
        self.account.recovery_mail = self.mail_entry.get().strip()
        self.account.recovery_mail_password = self.mailpass_entry.get().strip()
        self.account.recovery_mail_backup = self.mailbackup_entry.get().strip()
        self.account.twofa = self.twofa_entry.get().strip()
        self.account.set_proxy(proxy)
        self.account.auto_identity = bool(self.auto_identity.get())
        group = self.group_box.get().strip()
        self.account.group = "" if group == NO_GROUP else group
        self.account.status = self.status_box.get()
        self.account.note = self.note_box.get("1.0", "end").strip()
        self.account.cookie = cookie_text
        self.result = self.account
        self.destroy()


# Cac loai truong gan cho tung cot khi nhap hang loat. (khoa, nhan hien thi)
# Khoa "x:..." la truong phu, luu vao Account.extra (khong co cot rieng).
IMPORT_FIELDS = [
    ("", "(bỏ qua)"),
    ("id", "Uid"),
    ("password", "Pass"),
    ("cookie", "Cookie"),
    ("x:token", "Token"),
    ("proxy", "Proxy / ProxySsh"),
    ("twofa", "2FA"),
    ("recovery_mail", "Email khôi phục"),
    ("recovery_mail_password", "Pass email khôi phục"),
    ("x:phone", "Phone"),
    ("x:user_agent", "UserAgent"),
    ("x:fb_name", "Facebook Name"),
    ("x:dob", "Ngày sinh"),
    ("x:gender", "Giới tính"),
    ("x:friends", "Friends"),
    ("x:fb_groups", "Groups (FB)"),
    ("note", "Ghi chú"),
    ("recovery_mail_backup", "Email khôi phục của email KP"),
    ("group", "Nhóm (trong tool)"),
]
_FIELD_LABEL = {key: label for key, label in IMPORT_FIELDS}
_FIELD_KEY = {label: key for key, label in IMPORT_FIELDS}
_DEFAULT_FIELDS = ["id", "password", "recovery_mail", "twofa", "proxy", "group"]
_IMPORT_COLUMNS = 10  # so o chon dinh dang hien ra


class BulkImportDialog(BaseDialog):
    """Nhap nhieu acc: chon dinh dang tung cot + nhom se dua vao.

    ``mode="update"`` la hop "Sua custom": van o dan + chon dinh dang + xem
    truoc y het, nhung khong THEM acc moi ma THAY gia tri cac cot da chon cho
    acc co san (khop theo Uid). Cot de "(bo qua)" va o trong thi giu nguyen.
    """

    def __init__(self, parent, groups: Optional[list[str]] = None,
                 mode: str = "import"):
        self.mode = mode
        tieu_de = "Nhập hàng loạt" if mode == "import" else "Sửa hàng loạt (custom)"
        super().__init__(parent, tieu_de, 900, 720)
        self.minsize(760, 600)
        self._groups = groups or []
        self._fmt_touched = False   # nguoi dung da tu sua dinh dang chua
        self._refresh_job = None

        # --- 1) O nhap input ---
        ctk.CTkLabel(
            self, text="Dán danh sách acc (mỗi dòng một acc):"
        ).pack(anchor="w", padx=PAD, pady=(PAD, 2))
        self.textbox = ctk.CTkTextbox(self, height=150)
        self.textbox.pack(fill="x", padx=PAD, pady=(0, 4))
        self.textbox.insert(
            "1.0", "100000000000001|matkhau123|mail@gmail.com||1.2.3.4:8080:user:pass\n"
        )
        self.textbox.bind("<KeyRelease>", lambda _e: self._schedule_refresh())
        self.textbox.bind("<<Paste>>", lambda _e: self.after(30, self._schedule_refresh))

        # --- 2) Khung chon dinh dang ---
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=PAD, pady=(2, 0))
        ctk.CTkLabel(head, text="Định dạng cột (trái → phải):").pack(side="left")
        ctk.CTkButton(
            head, text="🔍 Tự đề xuất", width=120, command=self._auto_detect
        ).pack(side="left", padx=8)
        ctk.CTkLabel(
            head, text="Cột không chắc để “(bỏ qua)” rồi tự chọn.",
            text_color="gray60",
        ).pack(side="left")

        fmt = ctk.CTkFrame(self, fg_color="transparent")
        fmt.pack(fill="x", padx=PAD, pady=(2, 4))
        labels = [lbl for _k, lbl in IMPORT_FIELDS]
        self.field_boxes: list[ctk.CTkOptionMenu] = []
        per_row = 5
        for i in range(_IMPORT_COLUMNS):
            box = ctk.CTkOptionMenu(
                fmt, values=labels, width=150, command=self._on_field_change
            )
            default_key = _DEFAULT_FIELDS[i] if i < len(_DEFAULT_FIELDS) else ""
            box.set(_FIELD_LABEL[default_key])
            box.grid(row=i // per_row, column=i % per_row, padx=2, pady=2, sticky="w")
            self.field_boxes.append(box)

        # --- dong cau hinh: dau phan cach + nhom ---
        cfg = ctk.CTkFrame(self, fg_color="transparent")
        cfg.pack(fill="x", padx=PAD, pady=(2, 2))
        ctk.CTkLabel(cfg, text="Dấu phân cách:").pack(side="left")
        self.separator = ctk.CTkOptionMenu(
            cfg, values=["|", ",", ";", "Tab", "Space"], width=90,
            command=lambda _v: self._schedule_refresh(),
        )
        self.separator.pack(side="left", padx=6)

        self.group_box = None
        self.ua_vars: dict = {}
        if self.mode == "import":
            ctk.CTkLabel(cfg, text="Đưa vào nhóm:").pack(side="left", padx=(16, 0))
            self.group_box = ctk.CTkComboBox(cfg, values=[NO_GROUP, *self._groups], width=170)
            self.group_box.set(NO_GROUP)
            self.group_box.pack(side="left", padx=6)
            ctk.CTkButton(cfg, text="➕ Nhóm mới", width=110, command=self._new_group).pack(side="left")

            # --- Tich chon category User Agent gan cho acc moi (iOS/Android/TV/Mac/Win) ---
            from core import useragent
            loai_ua = list(useragent.cac_loai().keys())
            ua_row = ctk.CTkFrame(self, fg_color="transparent")
            ua_row.pack(fill="x", padx=PAD, pady=(0, 2))
            if loai_ua:
                ctk.CTkLabel(ua_row, text="Gán User Agent (mỗi acc 1 UA ngẫu nhiên):").pack(side="left")
                for ten in loai_ua:
                    var = tk.BooleanVar(value=False)
                    ctk.CTkCheckBox(ua_row, text=ten, variable=var, width=70).pack(side="left", padx=6)
                    self.ua_vars[ten] = var
            else:
                ctk.CTkLabel(
                    ua_row, text="Chưa có file User Agent trong thư mục useragent/.",
                    text_color="gray60",
                ).pack(side="left")
        else:
            ctk.CTkLabel(
                cfg, text="Khớp theo cột Uid — chỉ THAY các cột đã chọn, ô trống giữ nguyên.",
                text_color="gray60",
            ).pack(side="left", padx=(16, 0))

        # --- 3) Bang xem truoc ---
        ctk.CTkLabel(self, text="Xem trước:").pack(anchor="w", padx=PAD, pady=(4, 0))
        preview_wrap = ctk.CTkFrame(self)
        preview_wrap.pack(fill="both", expand=True, padx=PAD, pady=(0, 4))
        self.preview = ttk.Treeview(preview_wrap, show="headings", height=6,
                                    style="Accounts.Treeview")
        pv = ttk.Scrollbar(preview_wrap, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=pv.set)
        self.preview.grid(row=0, column=0, sticky="nsew")
        pv.grid(row=0, column=1, sticky="ns")
        preview_wrap.grid_rowconfigure(0, weight=1)
        preview_wrap.grid_columnconfigure(0, weight=1)

        self.preview_count = ctk.CTkLabel(self, text="", text_color="gray60")
        self.preview_count.pack(anchor="w", padx=PAD)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(buttons, text="Hủy", width=100, fg_color="gray35", command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text=("Nhập" if self.mode == "import" else "Cập nhật"),
                      width=100, command=self._submit).pack(side="right", padx=6)

        # Doan dinh dang ngay tu du lieu mau + dung bang xem truoc.
        self.after(200, self._auto_detect)

    # ---- dinh dang / xem truoc ----------------------------------------
    def _current_separator(self) -> str:
        return {"Tab": "\t", "Space": " "}.get(self.separator.get(), self.separator.get())

    def _current_fields(self) -> list[str]:
        return [_FIELD_KEY.get(box.get(), "") for box in self.field_boxes]

    def _on_field_change(self, _value=None) -> None:
        self._fmt_touched = True   # nguoi dung tu sua -> ngung tu doan de len
        self._refresh_preview()

    def _schedule_refresh(self) -> None:
        # Go phim lien tuc thi doi mot nhip roi moi dung lai bang (do tre 300ms).
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        self._refresh_job = self.after(300, self._after_text_change)

    def _after_text_change(self) -> None:
        self._refresh_job = None
        # Neu nguoi dung chua tu dong vao dinh dang thi tu doan lai theo input moi.
        if not self._fmt_touched:
            self._detect_into_boxes()
        self._refresh_preview()

    def _auto_detect(self) -> None:
        self._detect_into_boxes()
        self._fmt_touched = False
        self._refresh_preview()

    def _detect_into_boxes(self) -> None:
        from core import importfmt
        text = self.textbox.get("1.0", "end")
        sep, fields = importfmt.detect(text, max_cols=_IMPORT_COLUMNS)
        # dat lai dau phan cach
        inv = {"\t": "Tab", " ": "Space"}.get(sep, sep)
        self.separator.set(inv if inv in ("|", ",", ";", "Tab", "Space") else "|")
        # dat lai cac o dinh dang (khong kich hoat _on_field_change)
        for box, key in zip(self.field_boxes, fields):
            box.set(_FIELD_LABEL.get(key, _FIELD_LABEL[""]))

    def _refresh_preview(self) -> None:
        from core import importfmt
        fields = self._current_fields()
        active = [(i, k) for i, k in enumerate(fields) if k]
        headers = [_FIELD_LABEL[k] for _i, k in active]

        cols = [f"c{i}" for i in range(len(active))]
        self.preview.configure(columns=cols)
        for col, title in zip(cols, headers):
            self.preview.heading(col, text=title)
            self.preview.column(col, width=max(90, min(240, len(title) * 12)), anchor="w")
        self.preview.delete(*self.preview.get_children())

        rows = importfmt.parse_rows(
            self.textbox.get("1.0", "end"), self._current_separator(), fields, limit=200
        )
        for row in rows:
            self.preview.insert("", "end", values=row)

        missing_id = "id" not in fields
        total = len(importfmt.clean_lines(self.textbox.get("1.0", "end")))
        warn = "  ⚠ chưa có cột Uid" if missing_id else ""
        self.preview_count.configure(text=f"{total} dòng{warn}")

    def _new_group(self) -> None:
        """Go ten nhom moi ngay tai day roi chon luon vao o 'Dua vao nhom'."""
        name = SimplePromptDialog(self, "Nhóm mới", "Tên nhóm mới:").show()
        if not name:
            return
        if name not in self._groups:
            self._groups.append(name)
            self.group_box.configure(values=[NO_GROUP, *self._groups])
        self.group_box.set(name)

    def _submit(self) -> None:
        fields = [_FIELD_KEY.get(box.get(), "") for box in self.field_boxes]
        if "id" not in fields:
            messagebox.showerror(
                "Định dạng nhập",
                "Phải có ít nhất một cột là “ID acc”.",
                parent=self,
            )
            return
        separator = self.separator.get()
        sep = {"Tab": "\t", "Space": " "}.get(separator, separator)
        group = self.group_box.get().strip() if self.group_box is not None else ""
        if group == NO_GROUP:
            group = ""
        ua_loai = [ten for ten, var in self.ua_vars.items() if var.get()]
        # (text, separator, fields, group, ua_loai)
        self.result = (self.textbox.get("1.0", "end"), sep, fields, group, ua_loai)
        self.destroy()


class CookieDialog(BaseDialog):
    """Xem / sua / nap cookie cho mot acc."""

    def __init__(self, parent, account: Account, current_count: int = 0):
        super().__init__(parent, f"Cookie - {account.id}", 720, 560)
        self.account = account

        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(fill="x", padx=PAD, pady=(PAD, 0))
        ctk.CTkLabel(info, text=f"Profile đang có {current_count} cookie.").pack(side="left")
        self.replace_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(info, text="Xoá cookie cũ trước khi nạp", variable=self.replace_var).pack(side="right")

        domain_row = ctk.CTkFrame(self, fg_color="transparent")
        domain_row.pack(fill="x", padx=PAD, pady=(6, 0))
        ctk.CTkLabel(domain_row, text="Domain mặc định:").pack(side="left")
        self.domain_entry = ctk.CTkEntry(domain_row, width=200)
        self.domain_entry.insert(0, ".facebook.com")
        self.domain_entry.pack(side="left", padx=6)
        ctk.CTkLabel(
            domain_row,
            text="(chỉ dùng khi cookie ở dạng 'ten=gia_tri; ...')",
            text_color="gray60",
        ).pack(side="left")

        self.textbox = ctk.CTkTextbox(self)
        self.textbox.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        self.textbox.insert("1.0", account.cookie)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(buttons, text="Hủy", width=100, fg_color="gray35", command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text="Lưu + Nạp vào profile", width=180, command=self._submit).pack(side="right", padx=6)
        ctk.CTkButton(buttons, text="Chỉ lưu", width=90, command=lambda: self._submit(False)).pack(side="right")

    def _submit(self, apply_now: bool = True) -> None:
        text = self.textbox.get("1.0", "end").strip()
        domain = self.domain_entry.get().strip()
        if text:
            try:
                parsed = cookie_module.parse(text, default_domain=domain)
            except cookie_module.CookieError as exc:
                messagebox.showerror("Cookie", str(exc), parent=self)
                return
            if apply_now and not parsed:
                messagebox.showerror("Cookie", "Không đọc được cookie nào.", parent=self)
                return
        self.result = {
            "text": text,
            "domain": domain,
            "apply": apply_now,
            "replace": bool(self.replace_var.get()),
        }
        self.destroy()


class ProxyDialog(BaseDialog):
    """Doi proxy cho mot acc, co nut kiem tra ngay tai cho."""

    def __init__(self, parent, account: Account, running: bool = False):
        super().__init__(parent, f"Đổi proxy - {account.id}", 620, 300)
        self.account = account
        current = account.get_proxy()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            body,
            text=f"Proxy hiện tại: {current.display(mask=False) or 'không có'}",
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        self.entry = ctk.CTkEntry(
            body, placeholder_text="ip:port  |  ip:port:user:pass  |  socks5://user:pass@ip:port"
        )
        self.entry.insert(0, current.as_text())
        self.entry.grid(row=1, column=0, sticky="ew")
        self.entry.bind("<Return>", lambda _event: self._save())
        ctk.CTkButton(body, text="Kiểm tra", width=90, command=self._test).grid(
            row=1, column=1, padx=(6, 0)
        )

        self.result_label = ctk.CTkLabel(body, text="", anchor="w", wraplength=560, justify="left")
        self.result_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        ctk.CTkLabel(
            body,
            text=(
                "Trình duyệt đang mở — proxy mới áp dụng ngay, không cần mở lại."
                if running
                else "Để trống rồi bấm Lưu nếu muốn bỏ proxy."
            ),
            text_color="gray60",
            anchor="w",
            wraplength=560,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(buttons, text="Hủy", width=100, fg_color="gray35", command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text="Lưu", width=100, command=self._save).pack(side="right", padx=6)

        self.entry.focus_set()

    def _read(self) -> Optional[proxy_module.Proxy]:
        text = self.entry.get().strip()
        if not text:
            return proxy_module.Proxy()
        try:
            return proxy_module.parse(text)
        except ValueError as exc:
            self.result_label.configure(text=str(exc), text_color="#e06c6c")
            return None

    def _test(self) -> None:
        proxy = self._read()
        if proxy is None:
            return
        if not proxy.enabled:
            self.result_label.configure(text="Chưa nhập proxy.", text_color="gray60")
            return
        from core.proxy_relay import test_proxy

        self.result_label.configure(text="Đang kiểm tra...", text_color="gray60")
        self.update_idletasks()
        ok, detail = test_proxy(proxy)
        self.result_label.configure(text=detail, text_color="#5fbf7f" if ok else "#e06c6c")

    def _save(self) -> None:
        proxy = self._read()
        if proxy is None:
            return
        self.result = proxy
        self.destroy()


class BulkProxyDialog(BaseDialog):
    """Gan proxy cho nhieu acc cung luc."""

    def __init__(self, parent, count: int):
        super().__init__(parent, "Gán proxy hàng loạt", 640, 460)
        ctk.CTkLabel(
            self,
            text=f"Đang chọn {count} acc.\n"
                 "• Nhập 1 dòng: tất cả acc dùng chung proxy đó.\n"
                 "• Nhập nhiều dòng: gán lần lượt theo thứ tự acc trong bảng.\n"
                 "• Để trống: xoá proxy khỏi các acc đã chọn.",
            justify="left",
        ).pack(anchor="w", padx=PAD, pady=(PAD, 4))

        self.textbox = ctk.CTkTextbox(self)
        self.textbox.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(buttons, text="Hủy", width=100, fg_color="gray35", command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text="Áp dụng", width=100, command=self._submit).pack(side="right", padx=6)

    def _submit(self) -> None:
        lines = [line.strip() for line in self.textbox.get("1.0", "end").splitlines() if line.strip()]
        proxies = []
        for number, line in enumerate(lines, start=1):
            try:
                proxies.append(proxy_module.parse(line))
            except ValueError as exc:
                messagebox.showerror("Proxy", f"Dòng {number}: {exc}", parent=self)
                return
        self.result = proxies
        self.destroy()


GHI_DE = "Ghi đè"
THEM_VAO = "Thêm vào cuối"


class NoteDialog(BaseDialog):
    """Sua ghi chu cho mot hoac nhieu acc cung luc."""

    def __init__(self, parent, accounts: list[Account]):
        many = len(accounts) > 1
        title = f"Ghi chú — {len(accounts)} acc" if many else f"Ghi chú — {accounts[0].id}"
        super().__init__(parent, title, 580, 420 if many else 340)
        self.minsize(440, 300)
        self.accounts = accounts

        # Chi mo san noi dung cu khi ca nhom dang dung chung mot ghi chu, neu
        # khong se khong biet lay ghi chu cua acc nao lam mac dinh.
        notes = {(a.note or "").strip() for a in accounts}
        shared = notes.pop() if len(notes) == 1 else None

        if many:
            names = ", ".join(a.id for a in accounts[:4])
            if len(accounts) > 4:
                names += f" … (+{len(accounts) - 4})"
            heading = f"Sửa ghi chú cho {len(accounts)} acc: {names}"
        else:
            heading = f"Ghi chú cho acc {accounts[0].id}:"
        ctk.CTkLabel(self, text=heading, justify="left", wraplength=540).pack(
            anchor="w", padx=PAD, pady=(PAD, 4)
        )

        self.mode = ctk.StringVar(value=GHI_DE)
        if many:
            ctk.CTkSegmentedButton(
                self, values=[GHI_DE, THEM_VAO], variable=self.mode
            ).pack(anchor="w", padx=PAD, pady=(2, 4))
            if shared is None:
                warning = "Các acc đang có ghi chú khác nhau — “Ghi đè” sẽ thay hết bằng nội dung dưới đây."
            else:
                warning = "Các acc đang dùng chung một ghi chú."
            ctk.CTkLabel(
                self, text=warning, text_color="gray60",
                justify="left", wraplength=540,
            ).pack(anchor="w", padx=PAD, pady=(0, 4))

        self.textbox = ctk.CTkTextbox(self)
        self.textbox.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        if shared:
            self.textbox.insert("1.0", shared)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(buttons, text="Hủy", width=100, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text="Lưu", width=100, command=self._submit).pack(
            side="right", padx=6
        )
        self.after(200, lambda: self.textbox.focus_set())

    def _submit(self) -> None:
        text = self.textbox.get("1.0", "end").strip()
        append = self.mode.get() == THEM_VAO
        if append and not text:
            messagebox.showinfo(
                "Ghi chú", "Chưa nhập gì để thêm vào.", parent=self
            )
            return
        if not append and not text and len(self.accounts) > 1:
            # De trong + ghi de = xoa sach ghi chu cua ca nhom, phai hoi lai.
            if not messagebox.askyesno(
                "Xoá ghi chú",
                f"Ô ghi chú đang để trống. Xoá ghi chú của {len(self.accounts)} acc?",
                parent=self,
            ):
                return
        # Tra ve (noi dung, co phai them vao cuoi khong); None nghia la huy.
        self.result = (text, append)
        self.destroy()


class GroupManagerDialog(BaseDialog):
    """Tao / doi ten / xoa nhom. Thao tac thang tren store roi bao co doi hay khong."""

    def __init__(self, parent, store):
        super().__init__(parent, "Quản lý nhóm", 520, 460)
        self.store = store
        self.changed = False

        ctk.CTkLabel(
            self,
            text="Nhóm giúp gom acc theo mục đích, ví dụ “Đăng nhập FB”, “Nuôi acc”.",
            text_color="gray60",
            justify="left",
        ).pack(anchor="w", padx=PAD, pady=(PAD, 6))

        creator = ctk.CTkFrame(self, fg_color="transparent")
        creator.pack(fill="x", padx=PAD)
        self.name_entry = ctk.CTkEntry(creator, placeholder_text="Tên nhóm mới")
        self.name_entry.pack(side="left", fill="x", expand=True)
        self.name_entry.bind("<Return>", lambda _e: self._create())
        ctk.CTkButton(creator, text="➕ Tạo nhóm", width=110, command=self._create).pack(
            side="left", padx=(6, 0)
        )

        # Dung Listbox cua tk vi customtkinter khong co widget danh sach chon duoc.
        self.listbox = tk.Listbox(
            self,
            bg="#242424", fg="#e6e6e6",
            selectbackground="#1f6aa5", selectforeground="#ffffff",
            highlightthickness=0, borderwidth=0, activestyle="none",
            font=("Segoe UI", 10),
        )
        self.listbox.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        self.listbox.bind("<Double-1>", lambda _e: self._rename())

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(actions, text="✏️ Đổi tên", width=110, command=self._rename).pack(side="left")
        ctk.CTkButton(actions, text="🗑 Xoá nhóm", width=110, fg_color="#a33",
                      command=self._remove).pack(side="left", padx=6)
        ctk.CTkButton(actions, text="Đóng", width=100, command=self._done).pack(side="right")

        self._reload()

    def _reload(self) -> None:
        self.listbox.delete(0, "end")
        self._names = self.store.groups()
        for name in self._names:
            count = self.store.count_in_group(name)
            self.listbox.insert("end", f"  {name}   ({count} acc)")
        if not self._names:
            self.listbox.insert("end", "  (chưa có nhóm nào)")

    def _selected(self) -> Optional[str]:
        if not self._names:
            return None
        picked = self.listbox.curselection()
        if not picked:
            messagebox.showinfo("Nhóm", "Chọn một nhóm trong danh sách đã.", parent=self)
            return None
        return self._names[picked[0]]

    def _create(self) -> None:
        try:
            name = self.store.add_group(self.name_entry.get())
        except ValueError as exc:
            messagebox.showerror("Không tạo được nhóm", str(exc), parent=self)
            return
        self.changed = True
        self.name_entry.delete(0, "end")
        self._reload()
        # Chon luon nhom vua tao cho de thay.
        if name in self._names:
            index = self._names.index(name)
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(index)
            self.listbox.see(index)

    def _rename(self) -> None:
        old = self._selected()
        if old is None:
            return
        new = SimplePromptDialog(
            self, "Đổi tên nhóm", f"Tên mới cho nhóm “{old}”:", old
        ).show()
        if not new or new.strip() == old:
            return
        try:
            moved = self.store.rename_group(old, new)
        except ValueError as exc:
            messagebox.showerror("Không đổi tên được", str(exc), parent=self)
            return
        self.changed = True
        self._reload()
        messagebox.showinfo("Nhóm", f"Đã đổi tên. {moved} acc được cập nhật.", parent=self)

    def _remove(self) -> None:
        name = self._selected()
        if name is None:
            return
        count = self.store.count_in_group(name)
        warning = f"Xoá nhóm “{name}”?"
        if count:
            warning += f"\n\n{count} acc đang ở nhóm này sẽ thành không có nhóm. Acc KHÔNG bị xoá."
        if not messagebox.askyesno("Xoá nhóm", warning, parent=self):
            return
        self.store.remove_group(name)
        self.changed = True
        self._reload()

    def _done(self) -> None:
        self.result = self.changed
        self.destroy()


class SimplePromptDialog(BaseDialog):
    """Hoi mot dong chu -- dung cho doi ten nhom, tao nhom nhanh."""

    def __init__(self, parent, title: str, prompt: str, initial: str = ""):
        super().__init__(parent, title, 460, 200)
        self.minsize(380, 170)
        ctk.CTkLabel(self, text=prompt, justify="left").pack(
            anchor="w", padx=PAD, pady=(PAD * 2, 6)
        )
        self.entry = ctk.CTkEntry(self)
        self.entry.pack(fill="x", padx=PAD)
        self.entry.insert(0, initial)
        self.entry.bind("<Return>", lambda _e: self._submit())

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=PAD, pady=PAD)
        ctk.CTkButton(buttons, text="Hủy", width=90, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text="OK", width=90, command=self._submit).pack(
            side="right", padx=6
        )
        self.after(200, lambda: (self.entry.focus_set(), self.entry.select_range(0, "end")))

    def _submit(self) -> None:
        value = self.entry.get().strip()
        if not value:
            self._cancel()
            return
        self.result = value
        self.destroy()


class FieldEditDialog(BaseDialog):
    """Sua MOT truong cua mot hoac nhieu acc cung luc.

    Khac SimplePromptDialog o hai cho quan trong:
      * de trong van la ket qua hop le (dung de XOA gia tri), chi bam Huy moi la huy;
      * chon nhieu acc thi noi ro se ghi de len tat ca, va chi mo san gia tri cu
        khi ca nhom dang dung chung mot gia tri.
    """

    def __init__(self, parent, accounts: list[Account], title: str, label: str,
                 values: list[str], multiline: bool = False,
                 options: Optional[list[str]] = None):
        many = len(accounts) > 1
        ten = f"{title} — {len(accounts)} acc" if many else f"{title} — {accounts[0].id}"
        cao = 420 if multiline else (300 if many else 250)
        super().__init__(parent, ten, 620, cao)
        self.minsize(460, 230)

        chung = set(values)
        san = chung.pop() if len(chung) == 1 else ""

        if many:
            ten_acc = ", ".join(a.id for a in accounts[:4])
            if len(accounts) > 4:
                ten_acc += f" … (+{len(accounts) - 4})"
            dau = f"Ghi đè {label.lower()} cho {len(accounts)} acc: {ten_acc}"
        else:
            dau = f"{label} của acc {accounts[0].id}:"
        ctk.CTkLabel(self, text=dau, justify="left", wraplength=580).pack(
            anchor="w", padx=PAD, pady=(PAD, 4)
        )
        if many and not san and len(chung) != 0:
            ctk.CTkLabel(self, text="Các acc đang có giá trị khác nhau — lưu là thay hết.",
                         text_color="gray60", justify="left", wraplength=580).pack(
                anchor="w", padx=PAD, pady=(0, 4))

        self.options = options
        if options:
            self.choice = ctk.CTkOptionMenu(self, values=options)
            self.choice.set(san if san in options else options[0])
            self.choice.pack(anchor="w", padx=PAD, pady=(4, 0))
        elif multiline:
            self.box = ctk.CTkTextbox(self)
            self.box.pack(fill="both", expand=True, padx=PAD, pady=(4, 0))
            if san:
                self.box.insert("1.0", san)
        else:
            self.box = ctk.CTkEntry(self)
            self.box.pack(fill="x", padx=PAD, pady=(4, 0))
            self.box.insert(0, san)
            self.box.bind("<Return>", lambda _e: self._submit())

        ctk.CTkLabel(self, text="Để trống rồi bấm Lưu là xoá giá trị này.",
                     text_color="gray60", justify="left").pack(
            anchor="w", padx=PAD, pady=(4, 0))

        nut = ctk.CTkFrame(self, fg_color="transparent")
        nut.pack(fill="x", padx=PAD, pady=PAD)
        ctk.CTkButton(nut, text="Hủy", width=90, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(nut, text="Lưu", width=90, command=self._submit).pack(
            side="right", padx=6)
        self.after(200, self._focus)

    def _focus(self) -> None:
        try:
            if self.options:
                return
            self.box.focus_set()
            if isinstance(self.box, ctk.CTkEntry):
                self.box.select_range(0, "end")
        except tk.TclError:
            pass

    def _submit(self) -> None:
        if self.options:
            self.result = self.choice.get()
        elif isinstance(self.box, ctk.CTkTextbox):
            self.result = self.box.get("1.0", "end").strip()
        else:
            self.result = self.box.get().strip()
        self.destroy()


class SettingsDialog(BaseDialog):
    """Chinh duong dan va cach tao profile."""

    def __init__(self, parent, settings: Settings):
        super().__init__(parent, "Cài đặt", 760, 700)
        self.settings = settings

        # Hang nut phai duoc pack TRUOC khung noi dung: pack cap cho theo thu tu,
        # khung co expand=True se an het chieu cao va nut bi cat mat o duoi.
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(side="bottom", fill="x", padx=PAD, pady=PAD)
        ctk.CTkButton(buttons, text="Hủy", width=110, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text="Lưu", width=110, command=self._save).pack(
            side="right", padx=8)

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        frame.grid_columnconfigure(1, weight=1)

        self.root_entry = self._path_row(
            frame, 0, "Thư mục chứa profile", settings.profiles_root, folder=True,
            default=DEFAULT_ROOT,
        )
        self.paf_entry = self._path_row(
            frame, 1, "File FirefoxPortable .paf.exe", settings.paf_path,
            folder=False, filetypes=[("Installer", "*.exe")],
        )
        self.template_entry = self._path_row(
            frame, 2, "Thư mục FirefoxPortable mẫu", settings.template_dir, folder=True
        )
        self.xpi_entry = self._path_row(
            frame, 3, "Extension .xpi (đã ký)", settings.extension_xpi,
            folder=False, filetypes=[("Firefox extension", "*.xpi")],
        )

        self.clone_var = tk.BooleanVar(value=settings.clone_from_template)
        ctk.CTkCheckBox(
            frame,
            text="Nhân bản từ thư mục mẫu thay vì chạy installer (nhanh hơn nhiều)",
            variable=self.clone_var,
        ).grid(row=4, column=1, sticky="w", padx=PAD, pady=(10, 4))

        self.multi_var = tk.BooleanVar(value=settings.allow_multiple_instances)
        ctk.CTkCheckBox(
            frame,
            text="Cho phép mở nhiều profile cùng lúc (AllowMultipleInstances)",
            variable=self.multi_var,
        ).grid(row=5, column=1, sticky="w", padx=PAD, pady=4)

        self.autologin_var = tk.BooleanVar(value=settings.auto_login_cookie)
        ctk.CTkCheckBox(
            frame,
            text="Tự nạp cookie để đăng nhập khi mở (nếu profile chưa đăng nhập)",
            variable=self.autologin_var,
        ).grid(row=6, column=1, sticky="w", padx=PAD, pady=4)

        self.tzshim_var = tk.BooleanVar(value=getattr(settings, "use_tz_shim", True))
        ctk.CTkCheckBox(
            frame,
            text="Giả múi giờ theo IP proxy (tắt thì proxy ngoài Mỹ sẽ lộ giờ máy thật)",
            variable=self.tzshim_var,
        ).grid(row=7, column=1, sticky="w", padx=PAD, pady=4)

        ctk.CTkLabel(frame, text="Giao diện").grid(
            row=8, column=0, sticky="w", padx=PAD, pady=8
        )
        self.appearance_box = ctk.CTkOptionMenu(
            frame, values=list(APPEARANCES), width=160,
        )
        self.appearance_box.set(APPEARANCE_LABELS.get(settings.appearance, "Sáng"))
        self.appearance_box.grid(row=8, column=1, sticky="w", padx=PAD, pady=8)

        # (Bo o "So luong tao profile": so luong DUNG CHUNG dat o o "Luong" tren bang acc — ADR-015.)

        ctk.CTkLabel(frame, text="Trang mở khi bấm “Mở”").grid(
            row=11, column=0, sticky="w", padx=PAD, pady=8
        )
        self.starturl_entry = ctk.CTkEntry(
            frame, placeholder_text="https://www.facebook.com/  (để trống = trang chủ mặc định)"
        )
        self.starturl_entry.insert(0, settings.start_url or "")
        self.starturl_entry.grid(row=11, column=1, sticky="ew", padx=PAD, pady=8)

        ctk.CTkLabel(
            frame,
            text="Mỗi acc là một thư mục con trong 'Thư mục chứa profile', đặt tên theo ID acc.\n"
                 "Mặc định là thư mục 'profile' ngay trong tool; đổi sang ổ khác nếu cần chỗ trống.\n"
                 "Đổi xong, tool sẽ hỏi có chuyển các profile hiện có sang chỗ mới không.\n"
                 "Chạy installer mất khoảng 25 giây mỗi acc; nhân bản thư mục mẫu nhanh hơn\n"
                 "nhưng cần chỉ định sẵn một thư mục FirefoxPortable đã giải nén.",
            text_color="gray60",
            justify="left",
        ).grid(row=12, column=0, columnspan=2, sticky="w", padx=PAD, pady=(16, 0))

    def _path_row(self, parent, row: int, label: str, value: str, folder: bool,
                  filetypes=None, default: str = ""):
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=PAD, pady=8)
        entry = ctk.CTkEntry(parent)
        entry.insert(0, value or "")
        entry.grid(row=row, column=1, sticky="ew", padx=PAD, pady=8)

        def browse():
            if folder:
                picked = filedialog.askdirectory(parent=self, initialdir=entry.get() or ".")
            else:
                picked = filedialog.askopenfilename(parent=self, filetypes=filetypes or [])
            if picked:
                entry.delete(0, "end")
                entry.insert(0, os.path.normpath(picked))

        ctk.CTkButton(parent, text="Chọn...", width=80, command=browse).grid(row=row, column=2, padx=(0, 4))

        if default:
            def reset():
                entry.delete(0, "end")
                entry.insert(0, default)

            ctk.CTkButton(parent, text="Mặc định", width=80, command=reset).grid(
                row=row, column=3, padx=(0, PAD)
            )
        return entry

    def _save(self) -> None:
        root = self.root_entry.get().strip()
        if not root:
            messagebox.showerror("Cài đặt", "Chưa chọn thư mục chứa profile.", parent=self)
            return
        if not os.path.isdir(root):
            if not messagebox.askyesno(
                "Cài đặt", f"Thư mục chưa tồn tại:\n{root}\n\nTạo mới?", parent=self
            ):
                return
            try:
                os.makedirs(root, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("Cài đặt", f"Không tạo được thư mục:\n{exc}", parent=self)
                return
        if self.clone_var.get():
            template = self.template_entry.get().strip()
            if not os.path.isfile(os.path.join(template, "FirefoxPortable.exe")):
                messagebox.showerror(
                    "Cài đặt",
                    "Thư mục mẫu phải chứa FirefoxPortable.exe.",
                    parent=self,
                )
                return
        self.settings.profiles_root = root
        self.settings.paf_path = self.paf_entry.get().strip()
        self.settings.template_dir = self.template_entry.get().strip()
        self.settings.clone_from_template = bool(self.clone_var.get())
        self.settings.allow_multiple_instances = bool(self.multi_var.get())
        self.settings.auto_login_cookie = bool(self.autologin_var.get())
        self.settings.use_tz_shim = bool(self.tzshim_var.get())
        self.settings.appearance = APPEARANCES.get(self.appearance_box.get(), "light")
        self.settings.start_url = self.starturl_entry.get().strip()
        self.result = self.settings
        self.destroy()


class CopyCustomDialog(BaseDialog):
    """Cho nguoi dung tu dat dinh dang roi copy hang loat theo mau do."""

    def __init__(self, parent, accounts, template: str, render, placeholders):
        super().__init__(parent, "Copy theo định dạng", 700, 560)
        self._accounts = accounts
        self._render = render

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        ctk.CTkLabel(
            body,
            text=f"Sẽ copy {len(accounts)} acc, mỗi acc một dòng theo mẫu bên dưới.",
            anchor="w",
        ).pack(fill="x")

        self.entry = ctk.CTkEntry(body, placeholder_text="{id}|{password}|{proxy}")
        self.entry.insert(0, template)
        self.entry.pack(fill="x", pady=(8, 4))
        self.entry.bind("<KeyRelease>", lambda _e: self._preview())

        ctk.CTkLabel(
            body, text="Bấm để chèn trường (tự ngăn cách bằng dấu |):", anchor="w",
            text_color="gray60", font=ctk.CTkFont(size=11),
        ).pack(fill="x", pady=(6, 2))

        chips = ctk.CTkScrollableFrame(body, height=150, fg_color="transparent")
        chips.pack(fill="x")
        column = 0
        line = None
        for key, label in placeholders:
            if column % 3 == 0:
                line = ctk.CTkFrame(chips, fg_color="transparent")
                line.pack(fill="x", pady=1)
            ctk.CTkButton(
                line, text=f"{label}  {{{key}}}", height=24, anchor="w",
                fg_color="gray30", hover_color="gray40",
                command=lambda k=key: self._insert(k),
            ).pack(side="left", fill="x", expand=True, padx=2)
            column += 1

        ctk.CTkLabel(
            body, text="Xem trước:", anchor="w",
            text_color="gray60", font=ctk.CTkFont(size=11),
        ).pack(fill="x", pady=(10, 2))
        self.preview = ctk.CTkTextbox(body, height=90)
        self.preview.pack(fill="x")

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(buttons, text="Hủy", width=110, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text="Copy", width=110, command=self._save).pack(
            side="right", padx=8)

        self.entry.focus_set()
        self._preview()

    def _insert(self, key: str) -> None:
        """Chèn trường vào mẫu, TỰ ngăn cách các trường bằng dấu ``|``.

        Bấm liên tiếp id, password, proxy -> ``{id}|{password}|{proxy}`` (không dính vào nhau)."""
        pos = self.entry.index("insert")
        truoc = self.entry.get()[:pos]
        sep = "|" if truoc and not truoc.endswith("|") else ""
        self.entry.insert(pos, sep + "{" + key + "}")
        self.entry.focus_set()
        self._preview()

    def _preview(self) -> None:
        template = self.entry.get()
        lines = []
        for account in self._accounts[:3]:
            try:
                lines.append(self._render(template, account))
            except Exception as exc:
                lines = [f"Mẫu sai: {exc}"]
                break
        if len(self._accounts) > 3:
            lines.append(f"... còn {len(self._accounts) - 3} dòng nữa")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", "\n".join(lines))

    def _save(self) -> None:
        template = self.entry.get().strip()
        if not template:
            messagebox.showerror("Copy", "Chưa nhập định dạng.", parent=self)
            return
        try:
            self._render(template, self._accounts[0])
        except Exception as exc:
            messagebox.showerror("Copy", f"Mẫu sai: {exc}", parent=self)
            return
        self.result = template
        self.destroy()


#: Be ngang cot trong hop thoai chon tai khoan.
ID_W = 190
GROUP_W = 170


_TACH_TU_KHOA = re.compile(r"[\s,;]+")


def tach_tu_khoa(text: str) -> list:
    """Tach o tim thanh cac tu khoa: cach nhau boi khoang trang / xuong dong / phay / cham phay.
    Bo trung, giu thu tu, ve chu thuong. Dan ca danh sach UID mot luc cung duoc."""
    ra, seen = [], set()
    for tu in _TACH_TU_KHOA.split((text or "").strip().lower()):
        if tu and tu not in seen:
            seen.add(tu)
            ra.append(tu)
    return ra


def _hay_acc(account) -> str:
    return f"{account.id} {getattr(account, 'group', '')} {getattr(account, 'note', '')}".lower()


def _khop(account, tu: str) -> bool:
    """Tu khoa toan so -> chi doi trong ID acc (dan UID); tu khoa khac -> id + nhom + ghi chu."""
    if tu.isdigit():
        return tu in str(account.id).lower()
    return tu in _hay_acc(account)


def loc_acc(accounts, text: str) -> list:
    """Acc HIEN theo o tim: khong tu khoa -> tat ca; co -> khop BAT KY tu khoa nao (OR), giu thu tu bang."""
    tus = tach_tu_khoa(text)
    if not tus:
        return list(accounts)
    return [a for a in accounts if any(_khop(a, tu) for tu in tus)]


def uid_khong_thay(accounts, text: str) -> list:
    """Cac tu khoa toan so (UID) khong khop ID acc nao — de bao nguoi dung thieu acc."""
    return [tu for tu in tach_tu_khoa(text)
            if tu.isdigit() and not any(_khop(a, tu) for a in accounts)]


TAT_CA_NHOM = "Tất cả nhóm"


class AccountPickerDialog(BaseDialog):
    """Chon tai khoan tu danh sach: o tim (nhieu UID), LOC NHOM, va KEO CHUOT chon nhieu acc."""

    def __init__(self, parent, accounts, picked_ids):
        super().__init__(parent, "Chọn tài khoản", 820, 620)
        self.minsize(640, 420)
        self._accounts = list(accounts)
        self._vars = {}
        # Trang thai keo chuot chon nhieu (dat truoc _fill).
        self._drag_active = False
        self._drag_target = True

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=PAD, pady=(PAD, 4))
        self.search = ctk.CTkEntry(
            head, placeholder_text="Tìm theo ID / nhóm / ghi chú — dán nhiều UID cách nhau bằng "
                                   "khoảng trắng hoặc dấu phẩy")
        self.search.pack(side="left", fill="x", expand=True)
        self.search.bind("<KeyRelease>", lambda _e: self._fill())

        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill="x", padx=PAD, pady=(0, 4))
        # LOC NHOM: chon 1 nhom -> chi hien acc nhom do; "Chọn tất cả" luc do = chon ca nhom.
        ctk.CTkLabel(tools, text="Nhóm:", text_color="gray60").pack(side="left")
        nhoms = sorted({(a.group or "").strip() for a in self._accounts if (a.group or "").strip()})
        self.group_filter = ctk.CTkOptionMenu(
            tools, width=190, values=[TAT_CA_NHOM] + nhoms,
            command=lambda _v=None: self._fill())
        self.group_filter.set(TAT_CA_NHOM)
        self.group_filter.pack(side="left", padx=(4, 12))
        self.count = ctk.CTkLabel(tools, text="", text_color="gray60")
        self.count.pack(side="left")
        ctk.CTkButton(tools, text="Bỏ chọn", width=90, fg_color="gray35",
                      command=lambda: self._set_all(False)).pack(side="right")
        ctk.CTkButton(tools, text="Chọn tất cả", width=100,
                      command=lambda: self._set_all(True)).pack(side="right", padx=6)

        ctk.CTkLabel(self, text="Mẹo: kéo chuột dọc theo các dòng để chọn/bỏ nhiều acc một lúc.",
                     text_color="gray50").pack(anchor="w", padx=PAD)

        # Hang tieu de cot, nam ngoai vung cuon de luon nhin thay.
        dam = ctk.CTkFont(weight="bold")
        tieu_de = ctk.CTkFrame(self, fg_color="transparent")
        tieu_de.pack(fill="x", padx=PAD)
        ctk.CTkLabel(tieu_de, text="ID acc", font=dam, width=ID_W, anchor="w").pack(
            side="left", padx=(28, 0))
        ctk.CTkLabel(tieu_de, text="Nhóm", font=dam, width=GROUP_W, anchor="w").pack(
            side="left")
        ctk.CTkLabel(tieu_de, text="Ghi chú", font=dam, anchor="w").pack(
            side="left", fill="x", expand=True)

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=PAD)

        for account in self._accounts:
            variable = tk.BooleanVar(value=account.id in picked_ids)
            variable.trace_add("write", lambda *_a: self._count())
            self._vars[account.id] = variable

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=PAD, pady=PAD)
        ctk.CTkButton(buttons, text="Hủy", width=110, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text="Xong", width=110, command=self._save).pack(
            side="right", padx=8)

        self._fill()
        self.search.focus_set()

    def _dang_hien(self) -> list:
        """Acc khop o tim (loc_acc — nhieu UID) VA thuoc nhom da chon o o loc nhom."""
        ds = loc_acc(self._accounts, self.search.get())
        nhom = self.group_filter.get()
        if nhom and nhom != TAT_CA_NHOM:
            ds = [a for a in ds if (a.group or "").strip() == nhom]
        return ds

    def _fill(self) -> None:
        """Ve lai danh sach. Moi dong la mot hang: o tick + ID, nhom, ghi chu.

        Khong nhet nhom vao chinh chu cua o tick nua: nhu vay cot khong thang
        hang, ma ghi chu thi dai ngan khac nhau nen cang loan.

        Moi hang gan ``_acc_id`` + bind chuot (Button-1/B1-Motion/ButtonRelease-1) de
        KEO CHUOT chon nhieu acc mot luc (winfo_containing tim acc duoi con tro).
        """
        for child in self.body.winfo_children():
            child.destroy()
        for account in self._dang_hien():
            hang = ctk.CTkFrame(self.body, fg_color="transparent")
            hang.pack(fill="x", pady=1)
            hang._acc_id = account.id                       # de tim acc duoi con tro khi keo
            ctk.CTkCheckBox(hang, text=account.id, width=ID_W,
                            variable=self._vars[account.id]).pack(side="left")
            lb_nhom = ctk.CTkLabel(hang, text=account.group or "—", width=GROUP_W, anchor="w",
                                   text_color="gray60")
            lb_nhom.pack(side="left")
            ghi_chu = (account.note or "").replace(chr(10), " ").strip()
            lb_ghi = ctk.CTkLabel(hang, text=ghi_chu or "—", anchor="w", justify="left",
                                  text_color="gray60")
            lb_ghi.pack(side="left", fill="x", expand=True)
            # Keo chuot tren PHAN NHAN (khong phai o tick) -> chon/bo nhieu dong lien tiep.
            for w in (hang, lb_nhom, lb_ghi):
                w.bind("<Button-1>", lambda e, a=account.id: self._drag_start(a))
                w.bind("<B1-Motion>", self._drag_move)
                w.bind("<ButtonRelease-1>", self._drag_end)
        self._count()

    def _acc_duoi_chuot(self, x_root: int, y_root: int):
        """Acc id cua hang nam duoi con tro (di len cay master tim ``_acc_id``)."""
        w = self.winfo_containing(x_root, y_root)
        while w is not None:
            aid = getattr(w, "_acc_id", None)
            if aid:
                return aid
            w = getattr(w, "master", None)
        return None

    def _drag_start(self, acc_id: str) -> None:
        var = self._vars.get(acc_id)
        if var is None:
            return
        self._drag_active = True
        self._drag_target = not var.get()      # keo tu dong dau: dao trang thai dong do
        var.set(self._drag_target)

    def _drag_move(self, event) -> None:
        if not self._drag_active:
            return
        aid = self._acc_duoi_chuot(event.x_root, event.y_root)
        if aid is not None:
            var = self._vars.get(aid)
            if var is not None and var.get() != self._drag_target:
                var.set(self._drag_target)

    def _drag_end(self, _event=None) -> None:
        self._drag_active = False

    def _count(self) -> None:
        picked = sum(1 for v in self._vars.values() if v.get())
        chu = f"đã chọn {picked}/{len(self._vars)}"
        text = self.search.get()
        if tach_tu_khoa(text):
            chu += f" · hiện {len(self._dang_hien())}"
            thieu = uid_khong_thay(self._accounts, text)
            if thieu:
                chu += f" · không thấy: {', '.join(thieu[:8])}" + (" …" if len(thieu) > 8 else "")
        self.count.configure(text=chu)

    def _set_all(self, value: bool) -> None:
        """Chi doi nhung dong dang hien -- neu khong o tim thanh vo nghia."""
        for account in self._dang_hien():
            self._vars[account.id].set(value)

    def _save(self) -> None:
        self.result = [i for i, v in self._vars.items() if v.get()]
        self.destroy()


class ColumnDialog(BaseDialog):
    """Chon cot nao hien, va keo thu tu cot."""

    def __init__(self, parent, columns, order, hidden):
        """``columns``: [(khoa, ten hien thi), ...] theo thu tu goc."""
        super().__init__(parent, "Cột hiển thị", 460, 620)
        self._labels = dict(columns)
        self._default = [key for key, _ in columns]

        # Thu tu dang dung = thu tu da luu, cong them cot moi chua co trong do.
        known = [k for k in (order or []) if k in self._labels]
        self._order = known + [k for k in self._default if k not in known]
        self._hidden = set(hidden or [])

        ctk.CTkLabel(
            self, anchor="w", justify="left", wraplength=420, text_color="gray60",
            text=("Bỏ tick để ẩn cột. Chọn một dòng rồi bấm ▲ ▼ để đổi thứ tự.\n"
                  "Ẩn cột không làm mất dữ liệu."),
        ).pack(fill="x", padx=PAD, pady=(PAD, 6))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=PAD)

        self.listbox = tk.Listbox(
            body, activestyle="none", exportselection=False, highlightthickness=0,
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<Double-1>", lambda _e: self._toggle())

        side = ctk.CTkFrame(body, fg_color="transparent")
        side.pack(side="left", fill="y", padx=(8, 0))
        ctk.CTkButton(side, text="▲", width=44, command=lambda: self._move(-1)).pack(pady=2)
        ctk.CTkButton(side, text="▼", width=44, command=lambda: self._move(1)).pack(pady=2)
        ctk.CTkButton(side, text="Ẩn/Hiện", width=80, command=self._toggle).pack(pady=(12, 2))
        ctk.CTkButton(side, text="Hiện hết", width=80, command=self._show_all).pack(pady=2)
        ctk.CTkButton(side, text="Mặc định", width=80, fg_color="gray35",
                      command=self._reset).pack(pady=2)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=PAD, pady=PAD)
        ctk.CTkButton(buttons, text="Hủy", width=110, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text="Áp dụng", width=110, command=self._save).pack(
            side="right", padx=8)

        self._fill()

    def _fill(self, keep: int = 0) -> None:
        self.listbox.delete(0, "end")
        for key in self._order:
            mark = "☐" if key in self._hidden else "☑"
            self.listbox.insert("end", f" {mark}  {self._labels[key]}")
        if self._order:
            index = max(0, min(keep, len(self._order) - 1))
            self.listbox.selection_set(index)
            self.listbox.see(index)

    def _current(self) -> int:
        picked = self.listbox.curselection()
        return picked[0] if picked else -1

    def _move(self, step: int) -> None:
        index = self._current()
        target = index + step
        if index < 0 or not 0 <= target < len(self._order):
            return
        self._order[index], self._order[target] = self._order[target], self._order[index]
        self._fill(keep=target)

    def _toggle(self) -> None:
        index = self._current()
        if index < 0:
            return
        key = self._order[index]
        if key in self._hidden:
            self._hidden.discard(key)
        elif len(self._hidden) + 1 < len(self._order):
            self._hidden.add(key)          # phai chua it nhat mot cot
        else:
            messagebox.showinfo("Cột hiển thị", "Phải chừa lại ít nhất một cột.", parent=self)
            return
        self._fill(keep=index)

    def _show_all(self) -> None:
        self._hidden.clear()
        self._fill(keep=self._current())

    def _reset(self) -> None:
        self._order = list(self._default)
        self._hidden.clear()
        self._fill()

    def _save(self) -> None:
        self.result = (list(self._order), sorted(self._hidden))
        self.destroy()


#: Cot cua cua so "Quan ly acc" (mo tu tab Auto dang / Tao fanpage): (khoa, tieu de, rong, canh).
QLACC_COLUMNS = (
    ("stt", "STT", 44, "center"),
    ("id", "UID acc", 150, "w"),
    ("name", "Name acc", 170, "w"),
    ("note", "Ghi chú", 200, "w"),
    ("proxy", "Proxy", 190, "w"),
    ("group", "Nhóm", 110, "w"),
    ("status", "Tình trạng acc", 120, "center"),
)


def qlacc_row(index: int, account) -> tuple:
    """Gia tri 1 dong cua so Quan ly acc (ham thuan, thuoc kiem duoc)."""
    try:
        proxy = account.get_proxy().display(mask=True) or "—"
    except Exception:  # noqa: BLE001
        proxy = "—"
    extra = getattr(account, "extra", None) or {}
    return (
        index,
        account.id,
        (extra.get("fb_name") or extra.get("name") or "—"),
        (getattr(account, "note", "") or "").replace(chr(10), " ")[:120] or "—",
        proxy,
        getattr(account, "group", "") or "—",
        getattr(account, "status", "") or "Chưa rõ",
    )


class AccountManagerDialog(BaseDialog):
    """Cua so QUAN LY ACC cho cac acc mot tab dang dung (Auto dang nhom/fanpage, Tao fanpage).

    Bang 7 cot: STT · UID acc · Name acc · Ghi chú · Proxy · Nhóm · Tình trạng acc.
    Double-click o Ghi chú -> sua ghi chu ngay; nut "Mo tab Quan ly acc" -> nhay sang tab chinh
    va chon dung cac acc nay de sua sau hon. ``accounts`` = list Account (thu tu giu nguyen).
    """

    def __init__(self, app, accounts: list, tieu_de: str = "Quản lý acc", *,
                 lay_accs=None, on_them=None, on_xoa=None, tinh_trang=None):
        """``lay_accs``: callable -> list Account (doc lai sau khi them/bo); ``on_them``: callable() mo
        picker them acc; ``on_xoa``: callable(list id) bo acc khoi tab; ``tinh_trang``: callable(id) -> chu
        noi them vao cot Tinh trang (vd trang thai job: checkpoint/bo/loi)."""
        super().__init__(app, f"{tieu_de} ({len(accounts)} acc)", 1000, 560)
        self.minsize(760, 380)
        self.app = app
        self.accounts = list(accounts)
        self._lay_accs = lay_accs
        self._on_them = on_them
        self._on_xoa = on_xoa
        self._tinh_trang = tinh_trang

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=PAD, pady=(PAD, 4))
        ctk.CTkLabel(top, text="Double-click ô Ghi chú để sửa · double-click dòng khác để mở acc ở tab Quản lý acc.",
                     text_color="gray60").pack(side="left")
        ctk.CTkButton(top, text="🔄 Làm mới", width=90, command=self.refresh).pack(side="right")
        ctk.CTkButton(top, text="📋 Mở tab Quản lý acc", width=170,
                      command=lambda: self._mo_tab_chinh(None)).pack(side="right", padx=6)
        if on_them is not None:
            ctk.CTkButton(top, text="➕ Thêm acc", width=100, command=self._them).pack(side="right", padx=(0, 6))
        if on_xoa is not None:
            ctk.CTkButton(top, text="🗑 Bỏ acc đã chọn", width=130, fg_color="#a33",
                          command=self._xoa).pack(side="right", padx=(0, 6))

        wrap = ctk.CTkFrame(self)
        wrap.pack(fill="both", expand=True, padx=PAD, pady=(0, 4))
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in QLACC_COLUMNS], show="headings",
                                 style="Accounts.Treeview", selectmode="extended")
        for k, t, w, a in QLACC_COLUMNS:
            self.tree.heading(k, text=t)
            self.tree.column(k, width=w, minwidth=40, anchor=a, stretch=(k != "stt"))
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self._double)

        self.count_label = ctk.CTkLabel(self, text="", text_color="gray60")
        self.count_label.pack(anchor="w", padx=PAD)
        ctk.CTkButton(self, text="Đóng", width=100, fg_color="gray35",
                      command=self._cancel).pack(side="right", padx=PAD, pady=(0, PAD))
        self.refresh()

    def refresh(self) -> None:
        if self._lay_accs is not None:
            try:
                self.accounts = [a for a in self._lay_accs() if a is not None]
            except Exception:  # noqa: BLE001
                pass
        self.tree.delete(*self.tree.get_children())
        for i, acc in enumerate(self.accounts, start=1):
            row = list(qlacc_row(i, acc))
            if self._tinh_trang is not None:
                try:
                    them = self._tinh_trang(acc.id) or ""
                except Exception:  # noqa: BLE001
                    them = ""
                if them:
                    row[6] = f"{row[6]} {them}".strip()
            self.tree.insert("", "end", iid=acc.id, values=tuple(row))
        self.count_label.configure(text=f"{len(self.accounts)} acc")
        try:
            self.title(self.title().split(" (")[0] + f" ({len(self.accounts)} acc)")
        except Exception:  # noqa: BLE001
            pass

    def _them(self) -> None:
        if self._on_them is None:
            return
        self._on_them()
        self.refresh()

    def _xoa(self) -> None:
        if self._on_xoa is None:
            return
        ids = list(self.tree.selection())
        if not ids:
            messagebox.showinfo("Bỏ acc", "Chọn acc trong bảng trước.", parent=self)
            return
        if not messagebox.askyesno("Bỏ acc", f"Bỏ {len(ids)} acc khỏi tab này? (acc vẫn còn trong Quản lý acc)", parent=self):
            return
        self._on_xoa(ids)
        self.refresh()

    def _acc(self, iid: str):
        for a in self.accounts:
            if a.id == iid:
                return a
        return None

    def _double(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        col = self.tree.identify_column(event.x)          # "#4" = Ghi chu
        if col == "#4":
            acc = self._acc(iid)
            if acc is None:
                return
            moi = SimplePromptDialog(self, "Ghi chú", f"Ghi chú cho {acc.id}:", initial=acc.note or "").show()
            if moi is None:
                return
            acc.note = moi
            try:
                self.app.store.save()
            except Exception:  # noqa: BLE001
                pass
            self.refresh()
            try:
                self.app.refresh()
            except Exception:  # noqa: BLE001
                pass
            return
        self._mo_tab_chinh([iid])

    def _mo_tab_chinh(self, ids) -> None:
        """Nhay sang tab Quan ly acc va chon cac acc (mac dinh: het acc trong cua so)."""
        ids = list(ids) if ids else [a.id for a in self.accounts]
        try:
            self.app.tabs.set("📋 Quản lý acc")
            acc_tabs = getattr(self.app, "acc_tabs", None)
            if acc_tabs is not None:
                acc_tabs.set("📘 Facebook")      # acc cua cac tab dang bai la acc Facebook
            tree = self.app.tree
            co = [i for i in ids if tree.exists(i)]
            tree.selection_set(co)
            if co:
                tree.see(co[0])
        except Exception:  # noqa: BLE001
            pass
        self._cancel()
