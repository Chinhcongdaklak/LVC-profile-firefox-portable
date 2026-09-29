"""Hop thoai rieng cho acc X.com: them/sua 1 acc + nhap hang loat co xem truoc.

Dinh dang 1 dong (core/x_import tu nhan dien, co the thieu truong):
    user X | pass X | gmail | pass gmail | mail khoi phuc cua gmail | 2FA cua gmail
    user X | pass X | gmail | pass gmail | 2FA
Them cookie X (co "auth_token=") o vi tri bat ky.

Luu vao Account: id=user, password=pass X, recovery_mail=gmail,
recovery_mail_password=pass gmail, recovery_mail_backup=mail KP gmail,
extra["gmail_2fa"]=2FA gmail (gon_2fa), cookie=cookie X.
"""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import ttk
from typing import Optional

import customtkinter as ctk

from core import x_import
from core.store import Account

from .dialogs import NO_GROUP, BaseDialog

PAD = 8

DINH_DANG_GOI_Y = (
    "Định dạng mỗi dòng (tự nhận diện, có thể thiếu trường):\n"
    "  user|pass X|gmail|pass gmail|mail KP gmail|2FA gmail\n"
    "  user|pass X|gmail|pass gmail|2FA\n"
    "Cookie X (có auth_token=) đặt ở vị trí nào cũng được."
)

#: Cot bang xem truoc nhap hang loat: (khoa, tieu de, rong)
XEM_TRUOC_COT = (
    ("stt", "STT", 44),
    ("user", "User X", 140),
    ("pass_x", "Pass X", 110),
    ("gmail", "Gmail", 190),
    ("pass_gmail", "Pass Gmail", 120),
    ("gmail_kp", "Mail KP Gmail", 170),
    ("gmail_2fa", "2FA Gmail", 150),
    ("cookie", "Cookie", 64),
    ("loi", "Lỗi", 180),
)


def _nhom_tu_o(value: str) -> str:
    value = (value or "").strip()
    return "" if value == NO_GROUP else value


class XAccountDialog(BaseDialog):
    """Them / sua mot acc X.com."""

    def __init__(self, parent, account: Optional[Account] = None, groups=()):
        editing = account is not None
        super().__init__(parent, "Sửa acc X" if editing else "Thêm acc X", 640, 720)
        self._goc = copy.deepcopy(account) if editing else None
        self._groups = list(groups or [])
        acc = account or Account()

        body = ctk.CTkScrollableFrame(self)
        body.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        body.grid_columnconfigure(1, weight=1)

        row = 0
        # --- Dan 1 dong + tu nhan dien ---
        ctk.CTkLabel(body, text="Dán 1 dòng").grid(row=row, column=0, sticky="w", padx=PAD, pady=6)
        dan = ctk.CTkFrame(body, fg_color="transparent")
        dan.grid(row=row, column=1, sticky="ew", padx=PAD, pady=6)
        dan.grid_columnconfigure(0, weight=1)
        self.line_entry = ctk.CTkEntry(dan, placeholder_text="user|pass X|gmail|pass gmail|mail KP|2FA")
        self.line_entry.grid(row=0, column=0, sticky="ew")
        self.line_entry.bind("<Return>", lambda _e: self._dien_tu_dong(self.line_entry.get()))
        ctk.CTkButton(dan, text="Tự nhận diện", width=110,
                      command=lambda: self._dien_tu_dong(self.line_entry.get())).grid(
            row=0, column=1, padx=(6, 0))
        row += 1

        self.user_entry = self._field(body, row, "User X *", acc.id); row += 1
        self.passx_entry = self._field(body, row, "Pass X *", acc.password); row += 1
        self.gmail_entry = self._field(body, row, "Gmail", acc.recovery_mail); row += 1
        self.gmailpass_entry = self._field(body, row, "Pass Gmail", acc.recovery_mail_password); row += 1
        self.gmailkp_entry = self._field(body, row, "Mail khôi phục Gmail", acc.recovery_mail_backup); row += 1
        self.twofa_entry = self._field(body, row, "2FA Gmail", str((acc.extra or {}).get("gmail_2fa", ""))); row += 1

        ctk.CTkLabel(body, text="Cookie X").grid(row=row, column=0, sticky="nw", padx=PAD, pady=6)
        self.cookie_box = ctk.CTkTextbox(body, height=90)
        self.cookie_box.grid(row=row, column=1, sticky="ew", padx=PAD, pady=6)
        if acc.cookie:
            self.cookie_box.insert("1.0", acc.cookie)
        row += 1

        ctk.CTkLabel(body, text="Nhóm").grid(row=row, column=0, sticky="w", padx=PAD, pady=6)
        self.group_box = ctk.CTkComboBox(body, values=[NO_GROUP, *self._groups])
        self.group_box.set(acc.group or NO_GROUP)
        self.group_box.grid(row=row, column=1, sticky="ew", padx=PAD, pady=6)
        row += 1

        ctk.CTkLabel(body, text="Ghi chú").grid(row=row, column=0, sticky="nw", padx=PAD, pady=6)
        self.note_box = ctk.CTkTextbox(body, height=70)
        self.note_box.grid(row=row, column=1, sticky="ew", padx=PAD, pady=6)
        if acc.note:
            self.note_box.insert("1.0", acc.note)
        row += 1

        self.error_label = ctk.CTkLabel(self, text="", text_color="#e06c6c", anchor="w",
                                        justify="left", wraplength=600)
        self.error_label.pack(fill="x", padx=PAD)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(buttons, text="Huỷ", width=100, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text="Lưu", width=100, command=self._submit).pack(side="right", padx=6)

    @staticmethod
    def _field(parent, row: int, label: str, value: str = "") -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=PAD, pady=6)
        entry = ctk.CTkEntry(parent)
        if value:
            entry.insert(0, value)
        entry.grid(row=row, column=1, sticky="ew", padx=PAD, pady=6)
        return entry

    @staticmethod
    def _dat(entry: ctk.CTkEntry, value: str) -> None:
        entry.delete(0, "end")
        if value:
            entry.insert(0, value)

    def _dien_tu_dong(self, line: str) -> x_import.XDong:
        """Tach 1 dong bang x_import.tach_dong roi dien cac o (chi o co gia tri)."""
        d = x_import.tach_dong((line or "").strip())
        pairs = (
            (self.user_entry, d.user), (self.passx_entry, d.pass_x),
            (self.gmail_entry, d.gmail), (self.gmailpass_entry, d.pass_gmail),
            (self.gmailkp_entry, d.gmail_kp), (self.twofa_entry, d.gmail_2fa),
        )
        for entry, value in pairs:
            if value:
                self._dat(entry, value)
        if d.cookie:
            self.cookie_box.delete("1.0", "end")
            self.cookie_box.insert("1.0", d.cookie)
        if d.loi and (line or "").strip():
            self.error_label.configure(text=f"Nhận diện: {d.loi}")
        else:
            self.error_label.configure(text="")
        return d

    def _doc_form(self) -> Account:
        """Doc cac o -> Account. Dang sua thi giu cac truong khac cua acc goc."""
        acc = copy.deepcopy(self._goc) if self._goc is not None else Account()
        acc.extra = dict(acc.extra or {})
        acc.id = self.user_entry.get().strip().lstrip("@")
        acc.password = self.passx_entry.get().strip()
        acc.recovery_mail = self.gmail_entry.get().strip()
        acc.recovery_mail_password = self.gmailpass_entry.get().strip()
        acc.recovery_mail_backup = self.gmailkp_entry.get().strip()
        twofa = x_import.gon_2fa(self.twofa_entry.get().strip())
        if twofa:
            acc.extra["gmail_2fa"] = twofa
        else:
            acc.extra.pop("gmail_2fa", None)
        acc.cookie = self.cookie_box.get("1.0", "end").strip()
        acc.group = _nhom_tu_o(self.group_box.get())
        acc.note = self.note_box.get("1.0", "end").strip()
        return acc

    def _submit(self) -> None:
        acc = self._doc_form()
        thieu = [ten for ten, v in (("User X", acc.id), ("Pass X", acc.password)) if not v]
        if thieu:
            self.error_label.configure(text="Thiếu: " + ", ".join(thieu) + ".")
            return
        if " " in acc.id:
            self.error_label.configure(text="User X không được có khoảng trắng.")
            return
        self.result = acc
        self.destroy()


class XBulkImportDialog(BaseDialog):
    """Nhap nhieu acc X — GIONG hop Nhap hang loat cua tab Facebook.

    O dan -> "Dinh dang cot (trai -> phai)" (moi cot mot o chon + "Tu de xuat") ->
    Dau phan cach + Dua vao nhom + Nhom moi -> Gan User Agent -> Xem truoc -> Nhap/Huy.
    ``.show()`` tra ``(text, sep, fields, group, ua_loai)`` hoac ``None``.
    """

    SO_COT = 8
    SEP_NHAN = {"|": "|", "\t": "Tab", ";": ";", ",": ",", " ": "Space"}

    def __init__(self, parent, groups=()):
        super().__init__(parent, "Nhập hàng loạt acc X", 980, 720)
        self.minsize(760, 600)
        self._groups = list(groups or [])
        self._refresh_job = None
        self._fmt_touched = False     # nguoi dung da tu sua dinh dang chua
        self._dong: list[x_import.XDong] = []

        # --- 1) O dan ---
        ctk.CTkLabel(self, text="Dán danh sách acc X (mỗi dòng một acc):").pack(
            anchor="w", padx=PAD, pady=(PAD, 2))
        self.textbox = ctk.CTkTextbox(self, height=150)
        self.textbox.pack(fill="x", padx=PAD, pady=(0, 4))
        self.textbox.bind("<KeyRelease>", lambda _e: self._hen_cap_nhat())
        self.textbox.bind("<<Paste>>", lambda _e: self.after(30, self._hen_cap_nhat))

        # --- 2) Dinh dang cot ---
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=PAD, pady=(2, 0))
        ctk.CTkLabel(head, text="Định dạng cột (trái → phải):").pack(side="left")
        ctk.CTkButton(head, text="🔍 Tự đề xuất", width=120,
                      command=self._tu_de_xuat).pack(side="left", padx=8)
        ctk.CTkLabel(head, text="Cột không chắc để “(bỏ qua)” rồi tự chọn.",
                     text_color="gray60").pack(side="left")

        fmt = ctk.CTkFrame(self, fg_color="transparent")
        fmt.pack(fill="x", padx=PAD, pady=(2, 4))
        nhan = [lbl for _k, lbl in x_import.X_FIELDS]
        self.field_boxes: list = []
        for i in range(self.SO_COT):
            box = ctk.CTkOptionMenu(fmt, values=nhan, width=150, command=self._doi_cot)
            mac = x_import.X_MAC_DINH[i] if i < len(x_import.X_MAC_DINH) else ""
            box.set(x_import.X_FIELD_LABEL[mac])
            box.grid(row=i // 5, column=i % 5, padx=2, pady=2, sticky="w")
            self.field_boxes.append(box)

        # --- dau phan cach + nhom ---
        cfg = ctk.CTkFrame(self, fg_color="transparent")
        cfg.pack(fill="x", padx=PAD, pady=(2, 2))
        ctk.CTkLabel(cfg, text="Dấu phân cách:").pack(side="left")
        self.separator = ctk.CTkOptionMenu(cfg, values=["|", ",", ";", "Tab", "Space"], width=90,
                                           command=lambda _v: self._hen_cap_nhat())
        self.separator.pack(side="left", padx=6)
        ctk.CTkLabel(cfg, text="Đưa vào nhóm:").pack(side="left", padx=(16, 0))
        self.group_box = ctk.CTkComboBox(cfg, values=[NO_GROUP, *self._groups], width=170)
        self.group_box.set(NO_GROUP)
        self.group_box.pack(side="left", padx=6)
        ctk.CTkButton(cfg, text="➕ Nhóm mới", width=110, command=self._nhom_moi).pack(side="left")

        # --- Gan User Agent (moi acc 1 UA ngau nhien) ---
        from core import useragent
        self.ua_vars: dict = {}
        ua_row = ctk.CTkFrame(self, fg_color="transparent")
        ua_row.pack(fill="x", padx=PAD, pady=(0, 2))
        loai_ua = list(useragent.cac_loai().keys())
        if loai_ua:
            ctk.CTkLabel(ua_row, text="Gán User Agent (mỗi acc 1 UA ngẫu nhiên):").pack(side="left")
            for ten in loai_ua:
                var = tk.BooleanVar(master=self, value=False)
                ctk.CTkCheckBox(ua_row, text=ten, variable=var, width=70).pack(side="left", padx=6)
                self.ua_vars[ten] = var
        else:
            ctk.CTkLabel(ua_row, text="Chưa có file User Agent trong thư mục useragent/.",
                         text_color="gray60").pack(side="left")

        # --- 3) Xem truoc ---
        ctk.CTkLabel(self, text="Xem trước:").pack(anchor="w", padx=PAD, pady=(4, 0))
        wrap = ctk.CTkFrame(self)
        wrap.pack(fill="both", expand=True, padx=PAD, pady=(0, 4))
        self.preview = ttk.Treeview(wrap, show="headings", height=6, style="Accounts.Treeview")
        pv = ttk.Scrollbar(wrap, orient="vertical", command=self.preview.yview)
        ph = ttk.Scrollbar(wrap, orient="horizontal", command=self.preview.xview)
        self.preview.configure(yscrollcommand=pv.set, xscrollcommand=ph.set)
        self.preview.grid(row=0, column=0, sticky="nsew")
        pv.grid(row=0, column=1, sticky="ns")
        ph.grid(row=1, column=0, sticky="ew")
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        self.summary_label = ctk.CTkLabel(self, text="0 dòng · 0 hợp lệ · 0 lỗi", text_color="gray60")
        self.summary_label.pack(anchor="w", padx=PAD)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(buttons, text="Hủy", width=100, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(buttons, text="Nhập", width=100, command=self._submit).pack(side="right", padx=6)

        self._cap_nhat_xem_truoc()

    # ---- dinh dang / xem truoc ------------------------------------------
    def _sep(self) -> str:
        return {"Tab": "\t", "Space": " "}.get(self.separator.get(), self.separator.get())

    def _fields(self) -> list:
        return [x_import.X_FIELD_KEY.get(b.get(), "") for b in self.field_boxes]

    def _doi_cot(self, _v=None) -> None:
        self._fmt_touched = True      # nguoi dung tu sua -> ngung tu doan de len
        self._ve_bang()

    def _hen_cap_nhat(self) -> None:
        """Debounce 300ms: go lien tuc thi chi dung lai bang mot lan."""
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:           # noqa: BLE001 - thuoc khong co mainloop
                try:
                    self.tk.call("after", "cancel", self._refresh_job)
                except Exception:       # noqa: BLE001
                    pass
        self._refresh_job = self.after(300, self._cap_nhat_xem_truoc)

    def _cap_nhat_xem_truoc(self) -> None:
        self._refresh_job = None
        if not self._fmt_touched:
            self._dien_de_xuat()
        self._ve_bang()

    def _tu_de_xuat(self) -> None:
        self._dien_de_xuat()
        self._fmt_touched = False
        self._ve_bang()

    def _dien_de_xuat(self) -> None:
        text = self.textbox.get("1.0", "end")
        if not text.strip():
            return
        sep, fields = x_import.de_xuat(text, so_cot=self.SO_COT)
        self.separator.set(self.SEP_NHAN.get(sep, "|"))
        for box, k in zip(self.field_boxes, fields):
            box.set(x_import.X_FIELD_LABEL.get(k, x_import.X_FIELD_LABEL[""]))

    def _ve_bang(self) -> None:
        fields = self._fields()
        dung = [k for k in fields if k]
        cols = ["stt", *dung, "loi"]
        self.preview.configure(columns=cols)
        rong = {k: w for k, _t, w in XEM_TRUOC_COT}
        for c in cols:
            tieu_de = {"stt": "STT", "loi": "Lỗi"}.get(c) or x_import.X_FIELD_LABEL.get(c, c)
            self.preview.heading(c, text=tieu_de)
            self.preview.column(c, width=rong.get(c, 120), stretch=False,
                                anchor="center" if c == "stt" else "w")
        self.preview.delete(*self.preview.get_children())
        self._dong = x_import.tach_van_ban(self.textbox.get("1.0", "end"), self._sep(), fields)
        for i, d in enumerate(self._dong[:500], start=1):
            vals = [i] + [("có" if getattr(d, k) else "—") if k == "cookie" else getattr(d, k)
                          for k in dung] + [d.loi]
            self.preview.insert("", "end", values=vals, tags=("loi",) if d.loi else ())
        try:
            self.preview.tag_configure("loi", foreground="#e06c6c")
        except tk.TclError:
            pass
        loi = sum(1 for d in self._dong if d.loi)
        canh = "  ⚠ chưa có cột User X" if "user" not in fields else ""
        self.summary_label.configure(
            text=f"{len(self._dong)} dòng · {len(self._dong) - loi} hợp lệ · {loi} lỗi{canh}",
            text_color="gray60")

    def _nhom_moi(self) -> None:
        """Go ten nhom moi ngay tai day roi chon luon vao o 'Dua vao nhom'."""
        from .dialogs import SimplePromptDialog
        name = SimplePromptDialog(self, "Nhóm mới", "Tên nhóm mới:").show()
        if not name:
            return
        if name not in self._groups:
            self._groups.append(name)
            self.group_box.configure(values=[NO_GROUP, *self._groups])
        self.group_box.set(name)

    def _submit(self) -> None:
        text = self.textbox.get("1.0", "end")
        fields = self._fields()
        if "user" not in fields:
            self.summary_label.configure(text="Phải có một cột là “User X”.", text_color="#e06c6c")
            return
        if not x_import.tach_van_ban(text, self._sep(), fields):
            self.summary_label.configure(text="Chưa có dòng nào để nhập.", text_color="#e06c6c")
            return
        ua_loai = [ten for ten, var in self.ua_vars.items() if var.get()]
        self.result = (text, self._sep(), fields, _nhom_tu_o(self.group_box.get()), ua_loai)
        self.destroy()
