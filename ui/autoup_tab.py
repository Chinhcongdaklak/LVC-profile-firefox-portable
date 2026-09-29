"""Tab "Auto up video": canh gio quet thu muc roi tu dang video len fanpage.

Giao dien o day chi lo phan bam nut va hien ket qua. Toan bo viec canh gio, quet
thu muc va xoa file nam trong ``core/autoup.py``; viec goi Facebook nam trong
``core/fbupload.py`` (Graph API) va ``core/fbpage.py`` (nhan dien fanpage bang
phien dang nhap cua acc). Tach nhu vay de test duoc phan logic ma khong can mo
cua so.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
import tkinter as tk
from datetime import datetime, timezone
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from core import modun as modun_module
from core.modun import tat_ca as _modun_tat_ca
_modun_tat_ca.nap()   # nap registry 1 lan luc import (luong chinh), tranh tre trong luong nen

from core import autoup as autoup_module
from core import fbpage
from core import fbupload
from core import prompts as prompts_module
from core import spintax

from .dialogs import AccountPickerDialog, BaseDialog, SimplePromptDialog

PAD = 10

#: Kieu bai dang vao nhom.
KIEU = {"video": "Video", "image": "Ảnh", "text": "Chỉ chữ"}

#: Dang vao fanpage hay vao nhom.
NHAN_PAGE = "Fanpage"
NHAN_GROUP = "Nhóm"

#: Hai kieu dat lich.
NHAN_LIST = "Theo danh sách giờ"
NHAN_DELAY = "Cách nhau N phút"

#: Hai cach dua video len, hien trong o "Cach dang".
NHAN_BROWSER = "Mở business.facebook.com"
NHAN_API = "Graph API (cần token)"

#: Hai kich ban khi mot trang dung nhieu acc.
ROTATE_TURN = "Luân phiên mỗi bài"
ROTATE_DAY = "Mỗi acc đăng 1 ngày"


class PagePickerDialog(BaseDialog):
    """Chon mot fanpage trong so cac fanpage acc dang quan ly."""

    def __init__(self, parent, account_id: str, pages: list):
        super().__init__(parent, "Fanpage của acc " + account_id, 560, 420)
        self.minsize(440, 300)
        self.result = None
        self._pages = pages

        ctk.CTkLabel(self, justify="left", wraplength=520,
                     text=f"Acc {account_id} đang quản lý {len(pages)} fanpage. "
                          "Chọn cái muốn đăng lên:").pack(anchor="w", padx=PAD,
                                                          pady=(PAD, 6))
        khung = ctk.CTkScrollableFrame(self, fg_color="transparent")
        khung.pack(fill="both", expand=True, padx=PAD)
        for page in pages:
            ctk.CTkButton(
                khung, text=f"{page['name']}   ({page['id']})", anchor="w",
                command=lambda p=page: self._choose(p),
            ).pack(fill="x", pady=2)

        nut = ctk.CTkFrame(self, fg_color="transparent")
        nut.pack(fill="x", padx=PAD, pady=PAD)
        ctk.CTkButton(nut, text="Hủy", width=90, fg_color="gray35",
                      command=self._cancel).pack(side="right")

    def _choose(self, page: dict) -> None:
        self.result = page
        self.destroy()


class JobPanel(ctk.CTkFrame):
    """Noi dung mot tab con: mot fanpage, mot thu muc, mot lich rieng."""

    def __init__(self, parent, app, job, manager=None, acc_store=None, profiles=None):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.auto = job
        # Manager cua tab (Facebook: app.autoup · X: app.autoup_x). Mac dinh app.autoup
        # de code cu goi JobPanel(parent, app, job) van chay.
        self.manager = manager or app.autoup
        # Bang acc + profile cua tab: Facebook = app.store/app.manager (mac dinh),
        # X = store/manager cua tab Quan ly acc X -- de "chon acc" ra dung acc X.
        self.acc_store = acc_store or getattr(app, "store", None)
        self.profiles = profiles or getattr(app, "manager", None)
        # Nen tang cua job ("fb" | "x") -- quyet dinh hang "Dang len" va _missing.
        self.platform = getattr(self.manager, "platform", "fb")

        self._build()
        self._load_from_config()
        self._refresh_log()
        self._tick_ui()

    # ---------------------------------------------------------------- dung giao dien
    def _build(self) -> None:
        dam = ctk.CTkFont(weight="bold")

        # --- Thu muc video (nguon video LE co san) ---
        khung = ctk.CTkFrame(self)
        khung.pack(fill="x", padx=PAD, pady=(PAD, 6))
        ctk.CTkLabel(khung, text="Thư mục video", font=dam, width=140, anchor="w").pack(
            side="left", padx=(10, 6), pady=10)
        self.folder_entry = ctk.CTkEntry(
            khung, placeholder_text="Bỏ video LẺ vào đây, đến giờ tool tự lấy đăng")
        self.folder_entry.pack(side="left", fill="x", expand=True, pady=10)
        ctk.CTkButton(khung, text="Chọn...", width=80, command=self._pick_folder).pack(
            side="left", padx=6, pady=10)
        ctk.CTkButton(khung, text="Mở", width=60, fg_color="gray45",
                      command=self._open_folder).pack(side="left", padx=(0, 10), pady=10)

        # --- Thu muc bai cho dang (chi nhom): noi luu media hang doi, dang xong xoa ---
        if self.auto.config.is_group:
            khung_q = ctk.CTkFrame(self)
            khung_q.pack(fill="x", padx=PAD, pady=(0, 6))
            ctk.CTkLabel(khung_q, text="Thư mục bài chờ đăng", font=dam, width=140,
                         anchor="w").pack(side="left", padx=(10, 6), pady=10)
            self.queue_dir_entry = ctk.CTkEntry(
                khung_q, placeholder_text="Nơi lưu ảnh/video của bảng bài chờ đăng "
                                          "(đăng xong tự xoá)")
            self.queue_dir_entry.pack(side="left", fill="x", expand=True, pady=10)
            ctk.CTkButton(khung_q, text="Chọn...", width=80,
                          command=self._pick_queue_dir).pack(side="left", padx=6, pady=10)
            ctk.CTkButton(khung_q, text="Mở", width=60, fg_color="gray45",
                          command=self._open_queue_dir).pack(side="left", padx=(0, 10), pady=10)
        else:
            self.queue_dir_entry = None

        # --- Acc dang (co the nhieu acc, dang luan phien) ---
        khung_acc = ctk.CTkFrame(self)
        khung_acc.pack(fill="x", padx=PAD, pady=6)
        ctk.CTkLabel(khung_acc, text="Acc đăng", font=dam, width=110, anchor="w").pack(
            side="left", padx=(10, 6), pady=10)
        # Danh sach acc hien thanh cac "the" nho co nut bo. Nhoi vao khung nay.
        self.acc_chips = ctk.CTkFrame(khung_acc, fg_color="transparent")
        self.acc_chips.pack(side="left", pady=6)
        # KHONG liet ke tung acc o day (15 acc = 15 the tran hang): chi MOT nut Quan ly acc;
        # them/bo acc lam trong cua so do. Dong tom tat (so acc + so acc co van de) o _show_account.
        ctk.CTkButton(khung_acc, text="👤 Quản lý acc", width=120, fg_color="#3b6ea5",
                      command=self._quan_ly_acc).pack(side="left", padx=(6, 12), pady=10)
        # Chon kich ban -- chi hien khi co tu 2 acc tro len.
        self.rotate_row = ctk.CTkFrame(khung_acc, fg_color="transparent")
        ctk.CTkLabel(self.rotate_row, text="Kịch bản", font=dam).pack(side="left",
                                                                      padx=(0, 4))
        self.rotate_menu = ctk.CTkOptionMenu(
            self.rotate_row, width=185, values=[ROTATE_TURN, ROTATE_DAY],
            command=self._pick_rotate)
        self.rotate_menu.pack(side="left")

        # --- Noi dang (fanpage hoac nhom) ---
        khung2 = ctk.CTkFrame(self)
        khung2.pack(fill="x", padx=PAD, pady=6)
        ctk.CTkLabel(khung2, text="Đăng lên", font=dam, width=110, anchor="w").pack(
            side="left", padx=(10, 6), pady=10)

        # Hang nao hien la do LOAI CUA TAB quyet dinh, khong phai o chon trong bang.
        self.page_row = ctk.CTkFrame(khung2, fg_color="transparent")
        self.page_entry = ctk.CTkEntry(self.page_row, width=190,
                                       placeholder_text="ID hoặc dán link fanpage")
        self.page_entry.pack(side="left")
        ctk.CTkButton(self.page_row, text="📄 Fanpage của acc", width=145,
                      command=self._pick_page).pack(side="left", padx=6)
        ctk.CTkButton(self.page_row, text="🔍 Nhận diện", width=100, fg_color="gray45",
                      command=self._detect_page).pack(side="left", padx=(0, 6))
        ctk.CTkButton(self.page_row, text="🌐 Mở Business", width=125, fg_color="#1f6aa5",
                      command=self._open_business).pack(side="left")

        self.group_row = ctk.CTkFrame(khung2, fg_color="transparent")
        self.group_entry = ctk.CTkEntry(self.group_row, width=250,
                                        placeholder_text="Dán link nhóm đã tham gia sẵn")
        self.group_entry.pack(side="left")
        ctk.CTkButton(self.group_row, text="🔍 Nhận diện", width=100, fg_color="gray45",
                      command=self._detect_group).pack(side="left", padx=6)
        ctk.CTkButton(self.group_row, text="🌐 Mở nhóm", width=110, fg_color="#1f6aa5",
                      command=self._open_group).pack(side="left")
        # Khong con chon "Kieu bai": tool tu nhan dien tung file trong thu muc
        # (video -> dang video, anh -> anh + caption, .txt -> bai chi chu).
        ctk.CTkLabel(self.group_row, text="Tự nhận diện: video / ảnh / chữ",
                     text_color="gray60").pack(side="left", padx=(14, 4))

        # X: khong co ID fanpage -- bai len TUONG acc da chon. Chi mot dong chu
        # + nut mo x.com bang profile cua acc de nguoi dung kiem tra dang nhap.
        self.x_row = ctk.CTkFrame(khung2, fg_color="transparent")
        ctk.CTkLabel(self.x_row, text="Tường acc X đã chọn (bài đăng lên trang cá nhân x.com)",
                     text_color="gray60").pack(side="left")
        ctk.CTkButton(self.x_row, text="🌐 Mở x.com", width=110, fg_color="#1f6aa5",
                      command=self._open_x).pack(side="left", padx=(10, 0))

        self.page_label = ctk.CTkLabel(khung2, text="", text_color="gray60", anchor="w")
        self.page_label.pack(side="left", padx=10, pady=10, fill="x", expand=True)

        # --- Gio dang: mot dong cho gon ---
        khung3 = ctk.CTkFrame(self)
        khung3.pack(fill="x", padx=PAD, pady=6)
        ctk.CTkLabel(khung3, text="Đặt lịch", font=dam, width=110, anchor="w").pack(
            side="left", padx=(10, 6), pady=10)
        self.mode_menu = ctk.CTkOptionMenu(
            khung3, width=175, values=[NHAN_LIST, NHAN_DELAY], command=self._pick_mode)
        if not self.auto.config.is_lich:
            self.mode_menu.pack(side="left", pady=10)
        else:
            self._build_lich_row(khung3, dam)

        # Hai o nay thay phien nhau hien, tuy kieu dat lich dang chon.
        self.times_row = ctk.CTkFrame(khung3, fg_color="transparent")
        self.times_entry = ctk.CTkEntry(
            self.times_row,
            placeholder_text="7:00,9:00,11:00,... — mỗi mốc đăng 1 video, lấy video cũ nhất")
        self.times_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(self.times_row, text="Mặc định", width=90, fg_color="gray45",
                      command=self._default_times).pack(side="left", padx=(6, 0))

        self.delay_row = ctk.CTkFrame(khung3, fg_color="transparent")
        ctk.CTkLabel(self.delay_row, text="Cứ cách", anchor="w").pack(side="left")
        self.delay_entry = ctk.CTkEntry(self.delay_row, width=70)
        self.delay_entry.pack(side="left", padx=6)
        ctk.CTkLabel(self.delay_row, text="phút đăng 1 bài", anchor="w",
                     text_color="gray60").pack(side="left")

        # --- Bat / tat ---
        khung4 = ctk.CTkFrame(self)
        khung4.pack(fill="x", padx=PAD, pady=6)
        self.enabled_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(khung4, text="Bật tự động đăng", font=dam,
                      variable=self.enabled_var, command=self._toggle).pack(
            side="left", padx=10, pady=10)
        self.delete_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(khung4, text="Đăng xong xoá video", variable=self.delete_var,
                        command=lambda: self._save_from_ui(quiet=True)).pack(
            side="left", padx=10, pady=10)
        # Nhom chi dang duoc qua trinh duyet (khong co Graph API cho nhom) nen
        # o "Cach dang" chi hien o trang fanpage.
        self.method_label = ctk.CTkLabel(khung4, text="Cách đăng", anchor="w")
        self.method_menu = ctk.CTkOptionMenu(
            khung4, width=200, values=[NHAN_BROWSER, NHAN_API], command=self._pick_method)
        if not self.auto.config.is_group and self.platform != "x":
            self.method_label.pack(side="left", padx=(10, 4))
            self.method_menu.pack(side="left", pady=10)
        ctk.CTkButton(khung4, text="💾 Lưu", width=80, command=self._save_from_ui).pack(
            side="left", padx=(14, 4), pady=10)
        ctk.CTkButton(khung4, text="▶ Đăng thử 1 video", width=155,
                      fg_color="#2f7d4f", command=self._run_once).pack(
            side="left", padx=4, pady=10)
        # Gan MAU TUONG TAC: truoc khi dang, acc xem reel + like theo mau (KHONG dung delay).
        self.btn_tuong_tac = ctk.CTkButton(khung4, text="🤝 Tương tác: Tắt", width=170,
                                           fg_color="#6a4fa5", command=self._chon_mau_tuong_tac)
        self.btn_tuong_tac.pack(side="left", padx=4, pady=10)
        self.state_label = ctk.CTkLabel(khung4, text="", text_color="gray60", anchor="e")
        self.state_label.pack(side="right", padx=12)
        # Dong ho dem nguoc toi luot dang ke tiep (chi hien o kieu "cach N phut").
        self.countdown = ctk.CTkLabel(
            khung4, text="", anchor="e", text_color="#2f7d4f",
            font=ctk.CTkFont(size=22, weight="bold"))
        self.countdown.pack(side="right", padx=(0, 4))

        # --- Phan duoi ---
        # Nhom: chia doi -- trai la bang "Bai cho dang", phai la "Nhat ky".
        # Fanpage: KHONG co hang doi (hang doi chi den tu tab Quet bai nhom),
        # nen an bang di, nhat ky trai het chieu ngang.
        duoi = ctk.CTkFrame(self, fg_color="transparent")
        duoi.pack(fill="both", expand=True, padx=PAD, pady=(6, PAD))
        duoi.grid_rowconfigure(0, weight=1)
        if self.auto.config.is_lich:
            # Trang DAT LICH: chua bang khung gio (2 cua) thay cho bang hang doi.
            duoi.grid_columnconfigure(0, weight=3, uniform="col")
            duoi.grid_columnconfigure(1, weight=2, uniform="col")
            self.queue_tree = None
            self._build_lich_table(duoi, dam)
            self._build_log(duoi, dam, col=1)
        elif self.auto.config.is_group:
            duoi.grid_columnconfigure(0, weight=3, uniform="col")   # bang cho dang
            duoi.grid_columnconfigure(1, weight=2, uniform="col")   # nhat ky
            self._build_queue_table(duoi)
            self._build_log(duoi, dam, col=1)
        else:
            duoi.grid_columnconfigure(0, weight=1)
            self.queue_tree = None
            self._build_log(duoi, dam, col=0)

    # ---------------------------------------------------------------- nhat ky
    def _build_log(self, parent, dam, col: int = 1) -> None:
        khung5 = ctk.CTkFrame(parent)
        khung5.grid(row=0, column=col, sticky="nsew",
                    padx=((4, 0) if col else (0, 0)))
        self.log_frame = khung5
        dau = ctk.CTkFrame(khung5, fg_color="transparent")
        dau.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(dau, text="Nhật ký", font=dam, anchor="w").pack(side="left")
        ctk.CTkLabel(dau, text="(bấm đúp để phóng to)", text_color="gray55",
                     anchor="w").pack(side="left", padx=(6, 0))
        ctk.CTkButton(dau, text="⛶ Phóng to", width=90, height=26,
                      command=self._open_log_window).pack(side="right", padx=(6, 0))
        ctk.CTkButton(dau, text="Xoá nhật ký", width=90, height=26,
                      fg_color="gray45", command=self._clear_log).pack(side="right")
        self.tally_label = ctk.CTkLabel(khung5, text="", anchor="w", font=dam,
                                        text_color="#2f7d4f", justify="left",
                                        wraplength=360)
        self.tally_label.pack(fill="x", padx=10, pady=(2, 0))
        # Font to hon + cao toi thieu lon hon cho de doc; bam dup -> cua so lon.
        self.log_box = ctk.CTkTextbox(khung5, height=260,
                                      font=ctk.CTkFont(size=13))
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.log_box.configure(state="disabled")
        self.log_box.bind("<Double-1>", lambda _e: self._open_log_window())

    # ---------------------------------------------------------------- hang doi bai
    _QCOLS = (("source", "Nguồn (link gốc)", 220, "w"),
              ("status", "Trạng thái", 100, "center"),
              ("xao", "Xào AI", 110, "center"),
              ("caption", "Caption", 320, "w"),
              ("media", "Nơi lưu ảnh/video", 260, "w"),
              ("kind", "Kiểu", 60, "center"),
              ("download", "Tải về", 100, "center"))
    _QSTATUS = {"cho": "⏳ Chờ", "da": "✔ Đã đăng", "loi": "✖ Lỗi", "dang": "… Đang đăng"}
    _QDL = {"da": "✔ Đã tải", "cho": "⏳ Chờ tải", "loi": "✖ Tải lỗi", "": "—"}
    _QXAO = {"": "—", "cho": "⏳ Chờ xào", "dang": "… Đang xào", "da": "✔ Đã xào",
             "loi": "✖ Xào lỗi", "tat": "(tắt)"}

    # ------------------------------------------------ trang DAT LICH (2 cua)
    def _build_lich_row(self, khung3, dam) -> None:
        """Hang "Dat lich": gio bat dau + do tre + khoang an toan (mui gio o khoi duoi)."""
        ctk.CTkLabel(khung3, text="Bắt đầu chạy lúc", anchor="w").pack(side="left", pady=10)
        self.e_bat_dau = ctk.CTkEntry(khung3, width=70, placeholder_text="09:00")
        self.e_bat_dau.pack(side="left", padx=(6, 2))
        ctk.CTkLabel(khung3, text="(giờ máy)", text_color="gray60").pack(side="left", padx=(0, 14))
        ctk.CTkLabel(khung3, text="Độ trễ cho phép", anchor="w").pack(side="left", pady=10)
        self.e_tre = ctk.CTkEntry(khung3, width=55)
        self.e_tre.pack(side="left", padx=(6, 2))
        ctk.CTkLabel(khung3, text="phút", text_color="gray60").pack(side="left", padx=(0, 12))
        ctk.CTkLabel(khung3, text="Khoảng an toàn", anchor="w").pack(side="left")
        self.e_an_toan = ctk.CTkEntry(khung3, width=55)
        self.e_an_toan.pack(side="left", padx=(6, 2))
        ctk.CTkLabel(khung3, text="phút", text_color="gray60").pack(side="left")

    def _build_lich_table(self, parent, dam) -> None:
        """Khoi dat lich: gio tool chay · mui gio · gio dat lich video (+ dong quy doi mo).

        Nguoi dung go GIO THEO MUI GIO CUA PAGE o o "Giờ đặt lịch video"; tool tu quy doi
        ra gio may va hien ngay duoi bang mot dong chu mo -- khong phai tu nham tinh.
        """
        from core import lich_dang as ld
        wrap = ctk.CTkFrame(parent)
        wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        wrap.grid_columnconfigure(1, weight=1)

        def hang(r, chu):
            ctk.CTkLabel(wrap, text=chu, font=dam, anchor="w", width=210).grid(
                row=r, column=0, sticky="w", padx=(14, 8), pady=(14, 2))

        # 1) Gio TOOL CHAY -- hai kieu: danh sach moc gio, hoac cu cach N phut.
        hang(0, "Giờ tool chạy (theo khung giờ máy)")
        o_chay = ctk.CTkFrame(wrap, fg_color="transparent")
        o_chay.grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=(14, 2))
        self.lich_mode = ctk.CTkOptionMenu(o_chay, width=160, values=[NHAN_LIST, NHAN_DELAY],
                                           command=lambda _v: self._doi_kieu_chay())
        self.lich_mode.pack(side="left", padx=(0, 8))
        self.lich_chay_row = ctk.CTkFrame(o_chay, fg_color="transparent")
        self.lich_chay_row.pack(side="left", fill="x", expand=True)
        self.e_chay = ctk.CTkEntry(
            self.lich_chay_row,
            placeholder_text="07:00, 10:00, 17:00 — hoặc 25/09 07:00 nếu muốn rõ ngày")
        self.e_chay.pack(side="left", fill="x", expand=True)
        self.lich_delay_row = ctk.CTkFrame(o_chay, fg_color="transparent")
        ctk.CTkLabel(self.lich_delay_row, text="Cứ cách").pack(side="left")
        self.e_delay = ctk.CTkEntry(self.lich_delay_row, width=70)
        self.e_delay.pack(side="left", padx=6)
        ctk.CTkLabel(self.lich_delay_row, text="phút chạy 1 bài — lấy giờ đặt lịch kế tiếp",
                     text_color="gray60").pack(side="left")

        # 2) Mui gio cua PAGE.
        hang(1, "Múi giờ")
        o_tz = ctk.CTkFrame(wrap, fg_color="transparent")
        o_tz.grid(row=1, column=1, sticky="ew", padx=(0, 14), pady=(14, 2))
        self.tz_menu = ctk.CTkOptionMenu(o_tz, width=280, values=ld.danh_sach_nhan(),
                                         command=lambda _v: self._lich_nhap_doi())
        self.tz_menu.pack(side="left")
        # Gio HIEN TAI o nuoc do -- de nguoi dung biet ben do dang la ngay may.
        self.lich_bay_gio = ctk.CTkLabel(o_tz, text="", text_color="gray55", anchor="w")
        self.lich_bay_gio.pack(side="left", padx=(12, 0))

        # 3) Gio DAT LICH video -- go theo mui gio o tren.
        hang(2, "Giờ đặt lịch video")
        self.e_dang = ctk.CTkEntry(
            wrap, placeholder_text="07:00, 15:00, 20:00 — giờ ở múi giờ đã chọn")
        self.e_dang.grid(row=2, column=1, sticky="ew", padx=(0, 14), pady=(14, 2))
        # Dong chu MO: gio vua go quy doi ve gio may + ket qua hai cua.
        self.lich_quydoi = ctk.CTkLabel(wrap, text="", text_color="gray55", anchor="w",
                                        justify="left")
        self.lich_quydoi.grid(row=3, column=1, sticky="ew", padx=(0, 14), pady=(0, 6))

        self.lich_tom = ctk.CTkLabel(wrap, text="", text_color="gray55", anchor="w",
                                     justify="left")
        self.lich_tom.grid(row=4, column=0, columnspan=2, sticky="ew", padx=14, pady=(8, 12))
        wrap.grid_rowconfigure(5, weight=1)
        # Go toi dau quy doi toi do (cho 350ms cho go xong moi tinh).
        self.lich_tree = None
        self._hen_id = None
        for o in (self.e_chay, self.e_dang):
            o.bind("<KeyRelease>", lambda _e: self._hen_lich_ve())

    def _doi_kieu_chay(self) -> None:
        """Doi kieu gio chay: hien o hop voi kieu vua chon roi luu."""
        self._show_lich_chay_row()
        self._lich_nhap_doi()

    def _show_lich_chay_row(self) -> None:
        if self.lich_mode.get() == NHAN_DELAY:
            self.lich_chay_row.pack_forget()
            self.lich_delay_row.pack(side="left", fill="x", expand=True)
        else:
            self.lich_delay_row.pack_forget()
            self.lich_chay_row.pack(side="left", fill="x", expand=True)

    def _hen_lich_ve(self) -> None:
        """Go xong ~350ms moi tinh lai -- go tung ky tu ma tinh ngay thi giat."""
        if self._hen_id:
            try:
                self.after_cancel(self._hen_id)
            except Exception:  # noqa: BLE001
                pass
        self._hen_id = self.after(350, self._lich_nhap_doi)

    def _lich_nhap_doi(self) -> None:
        """O nhap doi -> luu vao cau hinh roi ve lai dong quy doi."""
        self._save_from_ui(quiet=True)
        self.auto.save()

    def _load_lich(self, cfg) -> None:
        """Cau hinh -> o nhap cua trang LICH (gio chay, mui gio, gio dang, do tre, an toan)."""
        from core import lich_dang as ld
        nhan = ld.danh_sach_nhan()
        iana = ld.iana_tu_nhan(cfg.mui_gio) if cfg.mui_gio else ""
        self.tz_menu.set(next((n for n in nhan if ld.iana_tu_nhan(n) == iana),
                              nhan[0] if nhan else ""))
        self.e_tre.delete(0, "end")
        self.e_tre.insert(0, str(cfg.tre_phut or ld.TRE_MAC_DINH))
        self.e_an_toan.delete(0, "end")
        self.e_an_toan.insert(0, str(cfg.an_toan_phut or ld.AN_TOAN_MAC_DINH))
        self.e_bat_dau.delete(0, "end")
        self.e_bat_dau.insert(0, cfg.gio_bat_dau or autoup_module.GIO_BAT_DAU_MAC_DINH)
        self.lich_mode.set(NHAN_DELAY if cfg.schedule_mode == "delay" else NHAN_LIST)
        self.e_delay.delete(0, "end")
        self.e_delay.insert(0, str(cfg.delay_minutes or autoup_module.DELAY_LICH_MAC_DINH))
        self._show_lich_chay_row()
        self.e_chay.delete(0, "end")
        # Kieu "cach N phut" thi khung khong co gio chay -> o nay de trong.
        self.e_chay.insert(0, ", ".join(c for c in (str(k.get("chay") or "")
                                                    for k in (cfg.khung_lich or [])) if c))
        self.e_dang.delete(0, "end")
        self.e_dang.insert(0, ", ".join(str(k.get("dang") or "") for k in (cfg.khung_lich or [])))
        self._lich_ve()

    @staticmethod
    def _tach_gio(text: str) -> list:
        """'07:00, 10:00' -> ['07:00', '10:00'] (nhan ca dau phay lan xuong dong).

        Go nham dau hai cham thay dau phay ("20:00:21:00") van hieu dung: chuoi chi
        gom cac cap HH:MM noi nhau thi tach ra, khong bat nguoi dung go lai.
        """
        import re
        ra = []
        for p in (text or "").replace("\n", ",").replace(";", ",").split(","):
            p = p.strip()
            if not p:
                continue
            if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{1,2}:\d{2})+", p):
                so = p.split(":")
                ra += [f"{so[i]}:{so[i + 1]}" for i in range(0, len(so) - 1, 2)]
            else:
                ra.append(p)
        return ra

    def _save_lich(self, cfg) -> None:
        """O nhap cua trang LICH -> cau hinh. So sai thi giu mac dinh, khong chan Luu."""
        from core import lich_dang as ld
        cfg.mui_gio = ld.iana_tu_nhan(self.tz_menu.get())
        cfg.gio_bat_dau = (self.e_bat_dau.get() or "").strip()
        cfg.schedule_mode = "delay" if self.lich_mode.get() == NHAN_DELAY else "list"
        for o, khoa, mac_dinh in ((self.e_tre, "tre_phut", ld.TRE_MAC_DINH),
                                  (self.e_an_toan, "an_toan_phut", ld.AN_TOAN_MAC_DINH),
                                  (self.e_delay, "delay_minutes",
                                   autoup_module.DELAY_LICH_MAC_DINH)):
            try:
                so = int((o.get() or "").strip())
            except ValueError:
                so = mac_dinh
            setattr(cfg, khoa, max(1 if khoa == "delay_minutes" else 0, so))
        dang = self._tach_gio(self.e_dang.get())
        if cfg.schedule_mode == "delay":
            # Kieu "cach N phut": KHONG co moc gio chay — dong ho delay quyet dinh
            # luc chay. Moi gio dat lich la MOT luot chay browser.
            cfg.khung_lich = [{"chay": "", "dang": d} for d in dang]
            self._lich_ve()
            return
        # Kieu danh sach: hai o ghep theo THU TU (moc chay thu i <-> gio dang thu i).
        chay = self._tach_gio(self.e_chay.get())
        cfg.khung_lich = [{"chay": c, "dang": d} for c, d in zip(chay, dang)]
        self._lich_ve(du_chay=len(chay), du_dang=len(dang))

    def _lich_ve(self, du_chay: int = -1, du_dang: int = -1) -> None:
        """Ve DONG QUY DOI (chu mo) -- chi ve lai ket qua cua core, khong tu tinh."""
        from core import lich_dang as ld
        if not getattr(self, "lich_quydoi", None):
            return
        cham = self.auto.lich_danh_gia()
        # Bay gio ben nuoc do la NGAY MAY, GIO MAY — go "20:00" nghia la 20:00 CUA NGAY DO.
        try:
            tz_page = ld.vung(self.auto.config.mui_gio or self.tz_menu.get())
            bg = ld.ra_may(datetime.now(timezone.utc), tz_page)
            ten = self.tz_menu.get().rsplit(" (", 1)[0]
            self.lich_bay_gio.configure(
                text=f"bên đó bây giờ: {bg.strftime('%d/%m %H:%M')} ({ten})")
        except Exception:  # noqa: BLE001
            self.lich_bay_gio.configure(text="")

        dau = {ld.CHAY: "✅", ld.CHO: "⏳", ld.BO_LO: "❌", ld.QUA_GAN: "❌",
               ld.DA_QUA: "❌", ld.DA_DANG: "✅"}
        dong = []
        for i, d in enumerate(cham, 1):
            if d["ly_do"] and not d["quy_doi"]:
                dong.append(f"{i}. {d['dang']} — {d['ly_do']}")
                continue
            # Khung da xong / bo lo thi hien LY DO (đã đăng lúc mấy giờ), khong hien lai nhan.
            cuoi = (d["ly_do"] if d["ket_qua"] in (ld.DA_DANG, ld.BO_LO) and d["ly_do"]
                    else ld.NHAN.get(d["ket_qua"], ""))
            dong.append(f"{i}. {d.get('dang_du') or d['dang']} bên đó"
                        f"  →  {d['quy_doi']} giờ máy   "
                        f"{dau.get(d['ket_qua'], '·')} {cuoi}")
        self.lich_quydoi.configure(
            text="\n".join(dong) if dong else "Nhập giờ đặt lịch để xem giờ quy đổi ra máy.")

        canh = []
        if du_chay >= 0 and du_chay != du_dang:
            canh.append(f"⚠ {du_chay} giờ chạy nhưng {du_dang} giờ đặt lịch — "
                        f"chỉ ghép được {min(du_chay, du_dang)} cặp theo thứ tự.")
        dem = {}
        for d in cham:
            dem[d["ket_qua"]] = dem.get(d["ket_qua"], 0) + 1
        if cham:
            canh.append(self.auto.lich_tom_tat())
        else:
            canh.append("Chưa có khung nào.")
        rao = self.manager.rao_con_giay()
        if rao:
            canh.append(f"⏸ đang chờ rào giữa các trang: còn {rao // 60}′{rao % 60:02d}″")
        self.lich_tom.configure(text="\n".join(canh))

    def _build_queue_table(self, parent) -> None:
        dam = ctk.CTkFont(weight="bold")
        wrap = ctk.CTkFrame(parent)
        wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        # Hang 1: tieu de + cac nut THEM noi dung.
        top = ctk.CTkFrame(wrap, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(top, text="Bài chờ đăng", font=dam).pack(side="left")
        ctk.CTkButton(top, text="➕ Thêm bài viết", width=125, fg_color="#2f7d4f",
                      command=self._add_post_manual).pack(side="left", padx=(12, 0))
        ctk.CTkButton(top, text="🔗 Thêm link hàng loạt", width=160, fg_color="#1f6aa5",
                      command=self._add_links_bulk).pack(side="left", padx=(6, 0))
        ctk.CTkButton(top, text="🖼 Quét ảnh thư mục", width=150, fg_color="#7a5",
                      command=self._add_images_folder).pack(side="left", padx=(6, 0))
        ctk.CTkButton(top, text="💬 Câu khơi chuyện", width=150, fg_color="#c77",
                      command=self._add_prompts).pack(side="left", padx=(6, 0))

        # Hang 2: dem + cac nut QUAN LY (chon/xoa/mo). De rieng hang cho khoi khuat.
        top2 = ctk.CTkFrame(wrap, fg_color="transparent")
        top2.pack(fill="x", padx=10, pady=(4, 0))
        self.queue_count = ctk.CTkLabel(top2, text="", text_color="gray60")
        self.queue_count.pack(side="left")
        ctk.CTkButton(top2, text="🔄 Tải lại nội dung", width=140, fg_color="#c86",
                      command=self._retry_download).pack(side="left", padx=(12, 0))
        ctk.CTkButton(top2, text="🤖 Xào lại", width=90, fg_color="#5a7",
                      command=self._xao_lai).pack(side="left", padx=(6, 0))
        ctk.CTkButton(top2, text="🔗 Xoá link trong bài", width=160, fg_color="#c77",
                      command=self._bo_link_queue).pack(side="left", padx=(6, 0))
        ctk.CTkButton(top2, text="📂 Mở nơi lưu", width=100, fg_color="gray45",
                      command=self._open_queue_media).pack(side="left", padx=(6, 0))
        # Cong tac xao AI.
        self.auto_xao_var = tk.BooleanVar(value=bool(self.auto.config.auto_xao))
        self.only_xao_var = tk.BooleanVar(value=bool(self.auto.config.only_post_xao))
        ctk.CTkCheckBox(top2, text="Tự xào AI", variable=self.auto_xao_var,
                        command=self._save_xao_flags).pack(side="left", padx=(12, 2))
        ctk.CTkCheckBox(top2, text="Chỉ đăng bài đã xào", variable=self.only_xao_var,
                        command=self._save_xao_flags).pack(side="left", padx=2)
        # Nut XOA -- ben phai, ro rang.
        ctk.CTkButton(top2, text="🗑 Xoá hết", width=90, fg_color="#7a1f1f",
                      command=lambda: self._clear_queue(False)).pack(side="right")
        ctk.CTkButton(top2, text="🗑 Xoá đã đăng", width=115, fg_color="gray45",
                      command=lambda: self._clear_queue(True)).pack(side="right", padx=(6, 0))
        ctk.CTkButton(top2, text="🗑 Xoá dòng đang chọn", width=160, fg_color="#a33",
                      command=self._delete_queue_selected).pack(side="right", padx=(6, 0))

        box = ctk.CTkFrame(wrap)
        box.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.queue_tree = ttk.Treeview(box, columns=[c[0] for c in self._QCOLS],
                                       show="headings", selectmode="extended",
                                       height=10, style="Accounts.Treeview")
        for key, title, w, anchor in self._QCOLS:
            self.queue_tree.heading(key, text=title)
            self.queue_tree.column(key, width=w, anchor=anchor,
                                   stretch=(key == "caption"), minwidth=50)
        vsb = ttk.Scrollbar(box, orient="vertical", command=self.queue_tree.yview)
        # Bang co 7 cot ma cho hep -> them thanh cuon NGANG de xem het cot.
        hsb = ttk.Scrollbar(box, orient="horizontal", command=self.queue_tree.xview)
        self.queue_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.queue_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        box.grid_rowconfigure(0, weight=1)
        box.grid_columnconfigure(0, weight=1)
        self.queue_tree.bind("<Double-1>", lambda _e: self._open_queue_media())
        self.queue_tree.bind("<Delete>", lambda _e: self._delete_queue_selected())
        self.queue_tree.bind("<Control-a>", lambda _e: self._queue_select_all())
        self.queue_tree.bind("<Control-A>", lambda _e: self._queue_select_all())
        self.queue_tree.bind("<Button-3>", self._queue_popup)
        self._build_queue_menu()
        self._refresh_queue()

    def _build_queue_menu(self):
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="🌐 Mở link gốc trên Facebook", command=self._open_queue_source)
        m.add_command(label="🔗 Chép link gốc", command=self._copy_queue_source)
        m.add_command(label="📂 Mở nơi lưu ảnh/video", command=self._open_queue_media)
        m.add_command(label="🔄 Tải lại nội dung", command=self._retry_download)
        m.add_separator()
        m.add_command(label="☑ Chọn tất cả", command=self._queue_select_all)
        m.add_separator()
        m.add_command(label="🗑 Xoá dòng đang chọn", command=self._delete_queue_selected)
        m.add_command(label="🗑 Xoá đã đăng", command=lambda: self._clear_queue(True))
        m.add_command(label="🗑 Xoá hết", command=lambda: self._clear_queue(False))
        self._queue_menu = m

    def _queue_popup(self, event):
        row = self.queue_tree.identify_row(event.y)
        if row and row not in self.queue_tree.selection():
            self.queue_tree.selection_set(row)
        try:
            self._queue_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._queue_menu.grab_release()

    def _queue_select_all(self):
        self.queue_tree.selection_set(self.queue_tree.get_children())
        return "break"

    def _refresh_queue(self) -> None:
        if getattr(self, "queue_tree", None) is None:
            return                       # fanpage khong co bang cho dang
        try:
            self.queue_tree.delete(*self.queue_tree.get_children())
        except (tk.TclError, AttributeError):
            return
        q = self.auto.queue
        kind_vn = {"image": "Ảnh", "text": "Text", "video": "Video", "link": "🔗 Link"}
        for it in q:
            cap = (it.get("caption") or "").replace("\n", " ")
            if len(cap) > 90:
                cap = cap[:90] + "…"
            kieu = it.get("kind") or self.auto.config.post_kind or ""
            # bai text/link khong co media -> khong hien trang thai tai
            dl = it.get("download", "da")
            if kieu in ("text", "link"):
                dl = ""
            self.queue_tree.insert("", "end", values=(
                it.get("source") or "",
                self._QSTATUS.get(it.get("status"), it.get("status") or ""),
                self._QXAO.get(it.get("xao", ""), "—"),
                cap or "(không có caption)",
                it.get("media") or "",
                kind_vn.get(kieu, kieu),
                self._QDL.get(dl, "—"),
            ))
        cho = sum(1 for it in q if it.get("status") == "cho")
        da = sum(1 for it in q if it.get("status") == "da")
        loi = sum(1 for it in q if it.get("status") == "loi")
        xao_da = sum(1 for it in q if it.get("xao") == "da")
        self.queue_count.configure(
            text=f"{cho} chờ · {da} đã đăng · {loi} lỗi · {xao_da} đã xào")

    def _selected_queue(self):
        sel = self.queue_tree.selection()
        if not sel:
            return None
        idx = self.queue_tree.index(sel[0])
        return self.auto.queue[idx] if 0 <= idx < len(self.auto.queue) else None

    def _selected_queue_rows(self) -> list:
        """Danh sach item hang doi dang chon (cho phep chon nhieu)."""
        out = []
        for iid in self.queue_tree.selection():
            idx = self.queue_tree.index(iid)
            if 0 <= idx < len(self.auto.queue):
                out.append(self.auto.queue[idx])
        return out

    def _bo_link_queue(self) -> None:
        """Xoá mọi link (URL) trong caption các bài trong hàng đợi (dòng đang chọn, không chọn = tất cả)."""
        from core import ai_lab
        rows = self._selected_queue_rows() or list(self.auto.queue)
        if not rows:
            self.app.set_status("Hàng đợi trống — không có bài nào để xoá link.")
            return
        doi = 0
        for it in rows:
            cu = it.get("caption") or ""
            moi = ai_lab.bo_link(cu)
            if moi != cu:
                it["caption"] = moi
                # đã xào rồi thì caption mới cũng bỏ link cho khớp khi đăng
                if it.get("caption_moi"):
                    it["caption_moi"] = ai_lab.bo_link(it["caption_moi"])
                doi += 1
        if doi:
            self.auto.save()
            self._refresh_queue()
        pham_vi = "đang chọn" if self._selected_queue_rows() else "tất cả"
        self.app.set_status(f"Đã xoá link trong {doi}/{len(rows)} bài ({pham_vi}).")

    def _delete_queue_selected(self) -> None:
        """Xoa cac dong dang chon khoi hang doi + xoa file da tai cua dong do."""
        rows = self._selected_queue_rows()
        if not rows:
            self.app.set_status("Chưa chọn dòng nào — bấm chọn dòng (Ctrl/Shift+click) trước.")
            return
        if not messagebox.askyesno(
            "Xoá dòng bài chờ đăng",
            f"Xoá {len(rows)} dòng đang chọn?\n\n"
            "Xoá luôn ảnh/video đã tải của các dòng này trong máy.",
            parent=self):
            return
        import shutil
        for it in rows:
            media = it.get("media") or ""
            # xoa file media + .txt + subfolder <base>_media (neu co)
            for f in (media, os.path.splitext(media)[0] + ".txt" if media else ""):
                if f and os.path.isfile(f):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
            if media:
                sub = os.path.splitext(media)[0] + "_media"
                if os.path.isdir(sub):
                    shutil.rmtree(sub, ignore_errors=True)
        # bo cac item da chon khoi hang doi (so khop theo danh tinh doi tuong)
        chon = set(id(it) for it in rows)
        self.auto.queue = [it for it in self.auto.queue if id(it) not in chon]
        self.auto.save()
        self._refresh_queue()
        self.app.set_status(f"Đã xoá {len(rows)} dòng khỏi bài chờ đăng.")

    def _open_queue_media(self) -> None:
        it = self._selected_queue()
        if not it:
            return
        m = it.get("media") or ""
        target = m if os.path.exists(m) else os.path.dirname(m)
        if not target or not os.path.exists(target):
            self.app.set_status("Không thấy file/nơi lưu (có thể đã đăng xong và xoá).")
            return
        try:
            os.startfile(target)  # type: ignore[attr-defined]
        except Exception:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(m)])

    def _open_queue_source(self) -> None:
        """Mo link GOC (nguon) cua cac dong dang chon bang trinh duyet mac dinh."""
        rows = self._selected_queue_rows()
        if not rows:
            self.app.set_status("Chưa chọn dòng nào.")
            return
        links = [it.get("source") for it in rows if it.get("source")]
        if not links:
            self.app.set_status("Dòng đang chọn không có link gốc.")
            return
        for link in links[:10]:              # tranh mo qua nhieu tab
            try:
                os.startfile(link)  # type: ignore[attr-defined]
            except Exception:
                subprocess.Popen(["cmd", "/c", "start", "", link], shell=False)
        self.app.set_status(f"Đã mở {min(len(links), 10)} link gốc trên Facebook.")

    def _copy_queue_source(self) -> None:
        """Chep link GOC (nguon) cua cac dong dang chon (moi link 1 dong)."""
        rows = self._selected_queue_rows()
        links = [it.get("source") for it in rows if it.get("source")]
        if not links:
            self.app.set_status("Dòng đang chọn không có link gốc.")
            return
        try:
            self.clipboard_clear()
            self.clipboard_append("\n".join(links))
            self.app.set_status(f"Đã chép {len(links)} link gốc.")
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- xào AI
    def _save_xao_flags(self):
        self.auto.config.auto_xao = bool(self.auto_xao_var.get())
        self.auto.config.only_post_xao = bool(self.only_xao_var.get())
        self.auto.save()

    def _xao_lai(self):
        rows = self._selected_queue_rows() or [
            it for it in self.auto.queue if it.get("xao") in ("loi", "cho", "")]
        rows = [it for it in rows if it.get("xao") != "dang"]
        if not rows:
            self.app.set_status("Không có bài nào để xào.")
            return
        self._xao_queue(rows)

    def _xao_pending(self):
        """Xao cac bai 'cho' -- goi sau khi them bai (neu bat Tự xào AI)."""
        if not self.auto.config.auto_xao:
            return
        from core import ai_lab
        rows = [it for it in self.auto.queue if ai_lab.can_xao(it)]   # IDEA-020
        if rows:
            self._xao_queue(rows)

    def _xao_queue(self, rows: list):
        """Xao CHU cac item hang doi qua core.ai_lab.xao_hang_doi (ADR-006/009):
        cau hinh AI = setup o tab '🔎 Quét bài' (data/ai_lab.json); anh/video giu nguyen."""
        from core import ai as ai_module, ai_lab
        cfg = ai_module.load_shared_config()
        ok, ly_do = ai_module.available(cfg)
        if not ok:
            for it in rows:
                it["xao"] = "loi"; it["xao_detail"] = ly_do
            self.auto.save(); self._refresh_queue()
            messagebox.showinfo("Xào AI", ly_do + "\n\nVào tab '🔎 Quét bài' (khối Setup AI) để "
                                "chọn nhà cung cấp + nhập API key + prompt.", parent=self)
            return
        for it in rows:
            it["xao"] = "dang"
        self.auto.save(); self._refresh_queue()

        def alog(m):
            self.after(0, lambda: self.app.set_status(m))

        def work():
            kq = ai_lab.xao_hang_doi(self.auto, rows, cfg, log=alog)
            self.after(0, self._refresh_queue)
            self.after(0, lambda: self.app.set_status(f"Xào xong {kq['da']}/{len(rows)} bài."))
        threading.Thread(target=work, daemon=True).start()

    def _retry_download(self) -> None:
        """Tai lai video/anh cho cac bai bi tai loi (download='loi') trong hang doi.

        Dung link nguon da luu (cot 'Nguon') + cookie/proxy cua acc dau cua nhom.
        Bai da chon -> chi tai lai bai do; khong chon -> tai lai TAT CA bai loi.
        """
        sel = self._selected_queue()
        if sel is not None:
            targets = [sel]
        else:
            targets = [it for it in self.auto.queue if it.get("download") == "loi"]
        targets = [it for it in targets
                   if it.get("download") == "loi" and it.get("source")
                   and it.get("kind") in ("video", "image")]
        if not targets:
            messagebox.showinfo(
                "Tải lại nội dung",
                "Không có bài nào cần tải lại (chỉ tải lại được bài Video/Ảnh có link "
                "nguồn và đang ở trạng thái ✖ Tải lỗi).", parent=self)
            return

        acc = self.account()
        if acc is None:
            messagebox.showinfo("Tải lại nội dung",
                                "Nhóm này chưa gán acc nào để lấy cookie tải.", parent=self)
            return
        folder = self.queue_folder()
        os.makedirs(folder, exist_ok=True)

        def work():
            from core import fbgroup, download as dl
            profile_dir = self.profiles.profile_dir(acc)
            proxy = acc.get_proxy()
            cookie = fbgroup.read_fb_cookies(profile_dir)
            cookiefile = fbgroup.netscape_cookiefile(profile_dir)
            opener = fbgroup._opener(proxy)
            ok = fail = manual = 0
            for it in targets:
                url = it.get("source") or ""
                base = it.get("base") or ""
                # Video link blob/stories/groups: yt-dlp chac chan khong tai duoc ->
                # dung goi cho phi thoi gian, danh dau de user mo bai thu cong.
                if it.get("kind") == "video" and not dl.is_video_link(url):
                    it["download"] = "loi"
                    manual += 1
                    continue
                self.after(0, lambda u=url: self.app.set_status(f"Đang tải lại: {u[:60]}..."))
                try:
                    if it.get("kind") == "video":
                        path = dl.download_video(url, folder, cookiefile=cookiefile, base=base)
                    else:
                        ext = ".jpg"
                        import re as _re
                        m = _re.search(r"\.(jpg|jpeg|png|webp|gif)", url, _re.IGNORECASE)
                        if m:
                            ext = "." + m.group(1).lower()
                        path = os.path.join(folder, base + ext)
                        if not fbgroup._download_one(opener, cookie, url, path):
                            raise dl.DownloadError("tải ảnh lỗi")
                    # Ghi caption sidecar CUNG LUC co file media (khong ghi truoc,
                    # neu khong thu muc chi co .txt -> poster dang nham thanh bai text).
                    cap = it.get("caption") or ""
                    if cap:
                        try:
                            with open(os.path.splitext(path)[0] + ".txt", "w",
                                      encoding="utf-8") as fh:
                                fh.write(cap)
                        except OSError:
                            pass
                    it["media"] = path
                    it["download"] = "da"
                    ok += 1
                except dl.DownloadError:
                    it["download"] = "loi"
                    fail += 1
                except Exception:  # noqa: BLE001
                    it["download"] = "loi"
                    fail += 1
            self.auto.save()
            self.after(0, self._refresh_queue)
            extra = f", {manual} link không tải được (mở bài thủ công)" if manual else ""
            self.after(0, lambda: self.app.set_status(
                f"Tải lại xong: {ok} thành công, {fail} lỗi{extra}."))

        self.app.set_status(f"Đang tải lại {len(targets)} bài...")
        threading.Thread(target=work, daemon=True).start()

    def _clear_queue(self, only_done: bool) -> None:
        n = self.auto.clear_queue(only_done=only_done)
        self._refresh_queue()
        self.app.set_status(f"Đã xoá {n} bài khỏi hàng đợi.")

    def _add_post_manual(self) -> None:
        """Nhap tay mot bai (caption + anh HOAC chi chu) -> ghi file vao thu muc
        job + them vao hang doi. Moi bai mot dong."""
        import shutil
        folder = self.queue_folder()   # bai cho dang luu o thu muc RIENG (khong phai thu muc video)
        if not folder:
            messagebox.showinfo("Thêm bài viết",
                                "Chọn 'Thư mục video' cho job này trước đã.", parent=self)
            return
        os.makedirs(folder, exist_ok=True)

        res = AddPostDialog(self).show()
        if not res:
            return
        caption, kind, images = res  # kind: "image"|"text"; images: list duong dan

        def stamp(i=0):
            return time.strftime("%Y%m%d_%H%M%S") + (f"_{i}" if i else "")

        added = 0
        if kind == "image" and images:
            for i, src in enumerate(images):
                base = "tay_" + stamp(i)
                ext = os.path.splitext(src)[1] or ".jpg"
                dest = os.path.join(folder, base + ext)
                try:
                    shutil.copy2(src, dest)
                    with open(os.path.join(folder, base + ".txt"), "w", encoding="utf-8") as fh:
                        fh.write(caption)
                    self.auto.add_to_queue(caption, dest, base, kind="image")
                    added += 1
                except OSError:
                    pass
        else:  # text
            base = "tay_" + stamp()
            dest = os.path.join(folder, base + ".txt")
            try:
                with open(dest, "w", encoding="utf-8") as fh:
                    fh.write(caption)
                self.auto.add_to_queue(caption, dest, base, kind="text")
                added += 1
            except OSError:
                pass

        self._refresh_queue()
        self.app.set_status(f"Đã thêm {added} bài vào hàng đợi.")
        self._xao_pending()          # tu dong xao neu bat "Tự xào AI"

    def _add_links_bulk(self) -> None:
        """Dan mot list link (bai/video) -> moi link thanh MOT bai share vao nhom.

        Moi link duoc ghi thanh mot file .txt (noi dung = caption + link); dang la
        bai chi chu co chua URL, Facebook tu tao preview -> chinh la share bai/video.
        """
        folder = self.queue_folder()   # bai cho dang luu o thu muc RIENG (khong phai thu muc video)
        if not folder:
            messagebox.showinfo("Thêm link",
                                "Chọn 'Thư mục video' cho job này trước đã.", parent=self)
            return
        os.makedirs(folder, exist_ok=True)

        res = LinkBulkDialog(self).show()
        if not res:
            return
        prefix, links = res  # prefix: caption them truoc moi link (co the rong)

        added = 0
        for i, link in enumerate(links):
            base = "link_" + time.strftime("%Y%m%d_%H%M%S") + f"_{i}"
            noidung = (prefix.strip() + "\n" + link).strip() if prefix.strip() else link
            dest = os.path.join(folder, base + ".txt")
            try:
                with open(dest, "w", encoding="utf-8") as fh:
                    fh.write(noidung)
                self.auto.add_to_queue(noidung, dest, base, kind="link", source=link, download="")
                added += 1
            except OSError:
                pass
        self._refresh_queue()
        self.app.set_status(f"Đã thêm {added} link vào hàng đợi.")
        self._xao_pending()

    def _add_images_folder(self) -> None:
        """Quet tat ca anh trong MOT thu muc -> moi anh mot bai, caption = TEN ANH."""
        import shutil
        folder = self.queue_folder()   # bai cho dang luu o thu muc RIENG (khong phai thu muc video)
        if not folder:
            messagebox.showinfo("Quét ảnh thư mục",
                                "Chọn 'Thư mục video' cho job này trước đã.", parent=self)
            return
        src_dir = filedialog.askdirectory(parent=self, title="Chọn thư mục chứa ảnh")
        if not src_dir:
            return
        os.makedirs(folder, exist_ok=True)
        exts = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
        try:
            names = sorted(n for n in os.listdir(src_dir) if n.lower().endswith(exts))
        except OSError as exc:
            messagebox.showerror("Quét ảnh thư mục", f"Không đọc được thư mục: {exc}", parent=self)
            return
        if not names:
            messagebox.showinfo("Quét ảnh thư mục", "Thư mục không có ảnh nào.", parent=self)
            return
        # Neu chon dung thu muc job thi khong can copy (anh da o day roi).
        same = os.path.normcase(os.path.abspath(src_dir)) == os.path.normcase(os.path.abspath(folder))
        added = 0
        for i, name in enumerate(names):
            src = os.path.join(src_dir, name)
            caption = os.path.splitext(name)[0]          # tieu de = ten anh
            base = os.path.splitext(name)[0] if same else f"anh_{time.strftime('%Y%m%d_%H%M%S')}_{i}"
            ext = os.path.splitext(name)[1] or ".jpg"
            dest = os.path.join(folder, (name if same else base + ext))
            try:
                if not same:
                    shutil.copy2(src, dest)
                with open(os.path.splitext(dest)[0] + ".txt", "w", encoding="utf-8") as fh:
                    fh.write(caption)
                self.auto.add_to_queue(caption, dest, os.path.splitext(os.path.basename(dest))[0], kind="image", download="da")
                added += 1
            except OSError:
                pass
        self._refresh_queue()
        self.app.set_status(f"Đã thêm {added} ảnh (caption = tên ảnh) vào hàng đợi.")
        self._xao_pending()

    def _add_prompts(self) -> None:
        """Them 'cau khoi chuyen' (bai text keo comment that) tu thu vien vao hang doi.

        Moi cau la mau spintax -> luc dang se spin ra ban khac nhau. Nguoi dung tich
        chon cau muon dung; luu moi cau mot bai text .txt vao thu muc job.
        """
        folder = self.queue_folder()   # bai cho dang luu o thu muc RIENG (khong phai thu muc video)
        if not folder:
            messagebox.showinfo("Câu khơi chuyện",
                                "Chọn 'Thư mục video' cho job này trước đã.", parent=self)
            return
        dlg = PromptPickDialog(self)
        self.wait_window(dlg)
        chosen = getattr(dlg, "chosen", None)
        if not chosen:
            return
        os.makedirs(folder, exist_ok=True)
        added = 0
        for i, text in enumerate(chosen):
            base = f"khoichuyen_{time.strftime('%Y%m%d_%H%M%S')}_{i}"
            dest = os.path.join(folder, base + ".txt")
            try:
                with open(dest, "w", encoding="utf-8") as fh:
                    fh.write(text)                       # luu MAU spintax; spin luc dang
                self.auto.add_to_queue(text, dest, base, kind="text", download="da")
                added += 1
            except OSError:
                pass
        self._refresh_queue()
        self.app.set_status(f"Đã thêm {added} câu khơi chuyện vào hàng đợi.")
        self._xao_pending()

    # ---------------------------------------------------------------- doc / ghi cau hinh
    def _load_from_config(self) -> None:
        cfg = self.auto.config
        self.folder_entry.delete(0, "end")
        self.folder_entry.insert(0, cfg.folder)
        if self.queue_dir_entry is not None:
            self.queue_dir_entry.delete(0, "end")
            self.queue_dir_entry.insert(0, cfg.queue_dir or "")
        self.times_entry.delete(0, "end")
        self.times_entry.insert(0, ", ".join(cfg.times))
        self.page_entry.delete(0, "end")
        self.page_entry.insert(0, cfg.page_id)
        self.group_entry.delete(0, "end")
        self.group_entry.insert(0, cfg.group_id)
        self._show_kind_row()
        self.delete_var.set(bool(cfg.delete_after))
        self.enabled_var.set(bool(cfg.enabled))
        self.method_menu.set(NHAN_API if cfg.method == "api" else NHAN_BROWSER)
        self.mode_menu.set(NHAN_DELAY if cfg.schedule_mode == "delay" else NHAN_LIST)
        self.delay_entry.delete(0, "end")
        self.delay_entry.insert(0, str(cfg.delay_minutes or 60))
        if cfg.is_lich:
            self._load_lich(cfg)
        self._show_mode_row()
        self._cap_nhat_nut_tuong_tac()
        self._show_account()

    # ---------------------------------------------------------------- mau tuong tac
    def _chon_mau_tuong_tac(self) -> None:
        """Chon 1 mau tuong tac da luu (hoac Tat) -> gan vao job (khong dung delay cua tab)."""
        from core import tuong_tac_mau as ttm
        menu = self.app._make_menu(self)
        menu.add_command(label="Tắt (không tương tác)",
                         command=lambda: self._dat_mau_tuong_tac(None))
        menu.add_separator()
        for mau in ttm.nap():
            menu.add_command(label=mau["ten"], command=lambda x=mau: self._dat_mau_tuong_tac(x))
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _dat_mau_tuong_tac(self, mau) -> None:
        self.auto.config.tuong_tac_mau = mau
        self.auto.save()
        self._cap_nhat_nut_tuong_tac()
        self.app.set_status("Tương tác trước khi đăng: " + (mau["ten"] if mau else "Tắt"))

    def _cap_nhat_nut_tuong_tac(self) -> None:
        mau = getattr(self.auto.config, "tuong_tac_mau", None)
        try:
            self.btn_tuong_tac.configure(text="🤝 Tương tác: " + (mau["ten"] if mau else "Tắt"))
        except Exception:  # noqa: BLE001
            pass
        self._show_page()

    def _save_from_ui(self, quiet: bool = False) -> bool:
        """Doc giao dien vao cau hinh. Tra ve False neu nguoi dung go gio sai."""
        cfg = self.auto.config
        cfg.folder = self.folder_entry.get().strip()
        if self.queue_dir_entry is not None:
            cfg.queue_dir = self.queue_dir_entry.get().strip()
        if cfg.is_lich:
            self._save_lich(cfg)          # tu dat schedule_mode theo o rieng cua no
        else:
            cfg.schedule_mode = "delay" if self.mode_menu.get() == NHAN_DELAY else "list"
        if cfg.schedule_mode == "delay" and not cfg.is_lich:
            try:
                phut = int(self.delay_entry.get().strip() or 0)
            except ValueError:
                phut = 0
            if phut < 1:
                messagebox.showerror("Đặt lịch",
                                     "Số phút phải là một số nguyên từ 1 trở lên.",
                                     parent=self.app)
                return False
            cfg.delay_minutes = phut
        try:
            cfg.times = autoup_module.parse_times(self.times_entry.get())
        except ValueError as exc:
            messagebox.showerror("Giờ đăng", str(exc), parent=self.app)
            return False
        # Dan ca link cung duoc; luu lai dang gon de nhin cho de.
        nhom = autoup_module.parse_group_id(self.group_entry.get())
        if nhom != cfg.group_id:
            cfg.group_id = nhom
            cfg.group_name = ""
            self.group_entry.delete(0, "end")
            self.group_entry.insert(0, nhom)
        moi = self.page_entry.get().strip()
        if moi != cfg.page_id:
            cfg.page_id = moi
            # Doi fanpage thi ten VA so da quy doi truoc do deu het dung.
            cfg.page_name = ""
            cfg.asset_id = ""
            self._show_page()
        cfg.delete_after = bool(self.delete_var.get())
        cfg.enabled = bool(self.enabled_var.get())
        cfg.method = "api" if self.method_menu.get() == NHAN_API else "browser"
        self.auto.save()
        # Go lai gio thi hien ban da chuan hoa (7:00 -> 07:00).
        self.times_entry.delete(0, "end")
        self.times_entry.insert(0, ", ".join(cfg.times))
        if not quiet:
            self.app.set_status("Đã lưu cài đặt auto up video.")
        return True

    def _default_times(self) -> None:
        self.times_entry.delete(0, "end")
        self.times_entry.insert(0, ", ".join(autoup_module.DEFAULT_TIMES))
        self._save_from_ui(quiet=True)

    # ---------------------------------------------------------------- thu muc
    def _pick_folder(self) -> None:
        chon = filedialog.askdirectory(title="Chọn thư mục chứa video", parent=self.app)
        if chon:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, os.path.normpath(chon))
            self._save_from_ui(quiet=True)

    def _open_folder(self) -> None:
        folder = self.folder_entry.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showinfo("Mở thư mục", "Chưa chọn thư mục hợp lệ.", parent=self.app)
            return
        try:
            os.startfile(folder)                                  # noqa: S606
        except OSError:
            subprocess.Popen(["explorer", folder])

    def _pick_queue_dir(self) -> None:
        if self.queue_dir_entry is None:
            return
        chon = filedialog.askdirectory(title="Chọn thư mục lưu bài chờ đăng", parent=self.app)
        if chon:
            self.queue_dir_entry.delete(0, "end")
            self.queue_dir_entry.insert(0, os.path.normpath(chon))
            self._save_from_ui(quiet=True)

    def _open_queue_dir(self) -> None:
        folder = self.queue_folder()
        if not folder or not os.path.isdir(folder):
            messagebox.showinfo("Mở thư mục", "Thư mục bài chờ đăng chưa có/không hợp lệ.",
                                parent=self.app)
            return
        try:
            os.startfile(folder)                                  # noqa: S606
        except OSError:
            subprocess.Popen(["explorer", folder])

    def queue_folder(self) -> str:
        """Thu muc luu media bai cho dang. Uu tien o nhap; chua co thi mac dinh
        data/bai_cho_dang/job-<id> ben trong tool (khong dung chung 'Thu muc video')."""
        if self.queue_dir_entry is not None:
            v = self.queue_dir_entry.get().strip()
            if v:
                return v
        if (self.auto.config.queue_dir or "").strip():
            return self.auto.config.queue_dir.strip()
        from core.config import TOOL_DIR
        return os.path.join(TOOL_DIR, "data", "bai_cho_dang", f"job-{self.auto.job_id}")

    # ---------------------------------------------------------------- acc + fanpage
    def account(self):
        """Acc dau danh sach, hoac None. (Giu cho cho cac cho con goi acc don.)"""
        ids = self.auto.accounts()
        return self.acc_store.get(ids[0]) if ids else None

    def _sync_accounts(self, ids: list) -> None:
        """Ghi danh sach acc vao cau hinh (kem account_id dau cho tuong thich)."""
        seen, sach = set(), []
        for a in ids:
            if a and a not in seen:
                seen.add(a)
                sach.append(a)
        self.auto.config.account_ids = sach
        self.auto.config.account_id = sach[0] if sach else ""
        self.auto.save()

    def _show_account(self) -> None:
        """Ve dong TOM TAT acc (khong liet ke tung acc) + nut Mo lai + hien/giau o chon kich ban."""
        for w in self.acc_chips.winfo_children():
            w.destroy()
        ids = self.auto.accounts()
        can_mo_lai = False
        n_cp = n_bo = n_loi = n_mat = n_gh = 0
        for ma in ids:
            if self.acc_store.get(ma) is None:
                n_mat += 1
            tt, loi, _nhan = self._acc_tinh_trang(ma)
            if tt != "ok" or loi:
                can_mo_lai = True
            if tt in ("checkpoint", "dang_xuat"):
                n_cp += 1
            elif tt == "bo":
                n_bo += 1
            elif tt == "gioi_han":
                n_gh += 1
            elif loi:
                n_loi += 1
        if not ids:
            chu, mau = "(chưa chọn acc)", "gray60"
        else:
            phan = [f"{len(ids)} acc"]
            if n_cp:
                phan.append(f"⛔ {n_cp} checkpoint/đăng xuất")
            if n_bo:
                phan.append(f"⏸ {n_bo} bỏ")
            if n_gh:
                phan.append(f"⏳ {n_gh} giới hạn đăng")
            if n_loi:
                phan.append(f"⚠ {n_loi} lỗi")
            if n_mat:
                phan.append(f"{n_mat} mất")
            chu = " · ".join(phan)
            mau = "#ff8a8a" if (n_cp or n_mat) else ("#ffd28a" if (n_bo or n_loi or n_gh) else ("gray10", "gray90"))
        self.acc_summary = ctk.CTkLabel(self.acc_chips, text=chu, text_color=mau)
        self.acc_summary.pack(side="left", padx=(4, 2))
        # Co acc bi dung / dem loi -> nut mo lai (dat lai trang thai ben core).
        if can_mo_lai:
            self.reopen_btn = ctk.CTkButton(self.acc_chips, text="↺ Mở lại acc", width=100,
                                            fg_color="#6a4fa5", command=self._mo_lai_acc)
            self.reopen_btn.pack(side="left", padx=(6, 0))
        else:
            self.reopen_btn = None
        # Kich ban chi co nghia khi >= 2 acc.
        if len(ids) >= 2:
            self.rotate_menu.set(ROTATE_DAY if self.auto.config.rotate == "day"
                                 else ROTATE_TURN)
            self.rotate_row.pack(side="left", padx=(8, 0), pady=10)
        else:
            self.rotate_row.pack_forget()

    def _acc_tinh_trang(self, ma: str):
        """(tt, loi, nhan hien tren the) cua mot acc — doc tu core, khong tinh gi them."""
        st = self.auto.acc_states.get(ma) or {}
        tt = str(st.get("tt") or "ok")
        loi = int(st.get("loi") or 0)
        if tt == "checkpoint":
            nhan = " ⛔ checkpoint"
        elif tt == "dang_xuat":
            nhan = " ⛔ đăng xuất"
        elif tt == "bo":
            nhan = f" ⛔ bỏ (lỗi {loi} lần)"
        elif tt == "gioi_han":
            den = str(st.get("den") or "")
            nhan = f" ⏳ giới hạn đăng — đăng lại {den[11:16]} {den[8:10]}/{den[5:7]}" if den else " ⏳ giới hạn đăng"
        elif loi:
            nhan = f" ⚠ lỗi {loi} lần"
        else:
            nhan = ""
        return tt, loi, nhan

    def _mo_lai_acc(self) -> None:
        """Nguoi dung da xu ly acc (go checkpoint / dang nhap lai) -> cho acc dang tiep."""
        n = self.auto.mo_lai_acc()
        self._show_account()
        self.app.set_status(f"Đã mở lại {n} acc." if n else "Không có acc nào đang bị dừng.")

    def _quan_ly_acc(self) -> None:
        """Cua so Quan ly acc cho job nay: xem 7 cot + Them acc (picker) + Bo acc; cot Tinh trang kem
        trang thai job (checkpoint / bo / loi). Mo duoc ca khi chua co acc (de them)."""
        from ui.dialogs import AccountManagerDialog
        lay = lambda: [self.acc_store.get(i) for i in self.auto.accounts()]  # noqa: E731
        def bo(ids):
            for i in ids:
                self._remove_account(i)
        def tinh_trang(ma):
            _tt, _loi, nhan = self._acc_tinh_trang(ma)
            return (nhan or "").strip()
        AccountManagerDialog(self.app, [a for a in lay() if a is not None],
                             tieu_de="Quản lý acc — " + self.auto.config.label(),
                             lay_accs=lay, on_them=self._pick_account, on_xoa=bo,
                             tinh_trang=tinh_trang).show()

    def _pick_account(self) -> None:
        hien = self.auto.accounts()
        chon = AccountPickerDialog(self.app, self.acc_store.accounts, hien).show()
        if chon is None:
            return
        # Picker cho chon nhieu -> them het vao danh sach acc cua trang nay.
        self._sync_accounts(list(chon))
        self._show_account()
        n = len(self.auto.accounts())
        self.app.set_status(f"Trang này dùng {n} acc."
                            + (" Chọn kịch bản luân phiên." if n >= 2 else ""))

    def _remove_account(self, ma: str) -> None:
        self._sync_accounts([a for a in self.auto.accounts() if a != ma])
        self._show_account()

    def _pick_rotate(self, label: str) -> None:
        self.auto.config.rotate = "day" if label == ROTATE_DAY else "turn"
        self.auto.save()
        self.app.set_status(f"Kịch bản: {label}.")

    def _show_page(self) -> None:
        cfg = self.auto.config
        if cfg.is_group:
            if cfg.group_name:
                self.page_label.configure(text="→ " + cfg.group_name,
                                          text_color="#2f7d4f")
            elif cfg.group_id:
                self.page_label.configure(text="chưa nhận diện", text_color="gray60")
            else:
                self.page_label.configure(text="", text_color="gray60")
            return
        if cfg.page_name:
            self.page_label.configure(text="→ " + cfg.page_name, text_color="#2f7d4f")
        elif cfg.page_id:
            self.page_label.configure(text="chưa nhận diện", text_color="gray60")
        else:
            self.page_label.configure(text="", text_color="gray60")

    def _detect_page(self) -> None:
        """Nhan dien fanpage VA quy doi ve dung so ma Business Suite dung.

        Mot fanpage co hai so khac nhau: link cong khai dung mot so, Business
        Suite dung so khac. Dan so cong khai vao thi Business Suite chi bao
        "Sorry, this content isn't available right now". O day tu doi sang so
        dung roi ghi nguoc lai vao o nhap, de bam "Mo Business" la vao duoc ngay.
        """
        if not self._save_from_ui(quiet=True):
            return
        cfg = self.auto.config
        if not cfg.page_id:
            messagebox.showinfo("Nhận diện", "Chưa nhập ID hoặc link fanpage.",
                                parent=self.app)
            return
        acc = self.account()
        if acc is None:
            messagebox.showinfo(
                "Nhận diện",
                "Chưa chọn acc — cần phiên đăng nhập của acc mới hỏi Facebook được.",
                parent=self.app)
            return
        self.page_label.configure(text="đang hỏi Facebook...", text_color="gray60")
        da_go = cfg.page_id

        def work():
            asset, ten, loi = fbpage.resolve_asset_id(da_go, acc.cookie)

            def xong():
                if not asset:
                    self.page_label.configure(text="không nhận diện được",
                                              text_color="#c44")
                    messagebox.showwarning("Nhận diện", loi, parent=self.app)
                    return
                doi = asset != fbpage.parse_page_id(da_go)
                cfg.page_id, cfg.page_name, cfg.asset_id = asset, ten, asset
                self.page_entry.delete(0, "end")
                self.page_entry.insert(0, asset)
                self.auto.save()
                self._show_page()
                self.app.set_status(
                    f"Fanpage: {ten} ({asset})"
                    + ("  — đã đổi sang ID mà Business Suite dùng" if doi else ""))
            self.app._post(xong)

        threading.Thread(target=work, daemon=True).start()

    def _open_business(self) -> None:
        """Mo Business Suite bang acc da chon, tro san vao dung fanpage."""
        if not self._save_from_ui(quiet=True):
            return
        cfg = self.auto.config
        if not cfg.page_id:
            messagebox.showinfo("Mở Business", "Chưa nhập ID fanpage.", parent=self.app)
            return
        acc = self.account()
        if acc is None:
            messagebox.showinfo("Mở Business", "Chưa chọn acc.", parent=self.app)
            return
        if not self.profiles.is_installed(acc):
            messagebox.showwarning("Mở Business",
                                   f"Acc {acc.id} chưa có profile. Tạo profile trước.",
                                   parent=self.app)
            return
        self.app.set_status("Đang kiểm tra ID fanpage...")

        def work():
            # Quy doi truoc khi mo: dan nham so cong khai thi Business Suite chi
            # hien trang loi chung, khong noi sai o dau.
            asset, ten, loi = fbpage.resolve_asset_id(cfg.page_id, acc.cookie)
            if not asset:
                self.app._post(lambda: messagebox.showwarning(
                    "Mở Business", loi, parent=self.app))
                return
            if asset != cfg.page_id or ten != cfg.page_name:
                cfg.page_id, cfg.page_name, cfg.asset_id = asset, ten, asset
                self.auto.save()
                self.app._post(self._sync_page_entry)
            url = autoup_module.business_url(asset)
            try:
                self.profiles.launch(acc, url=url)
            except Exception as exc:
                self.app._post(lambda e=exc: messagebox.showerror("Mở Business", str(e),
                                                                  parent=self.app))
                return
            self.acc_store.mark_opened(acc.id)
            self.app._post(self.app.refresh)

        threading.Thread(target=work, daemon=True).start()

    def _open_x(self) -> None:
        """Mo x.com bang profile X cua acc dau danh sach -- kiem tra dang nhap."""
        acc = self.account()
        if acc is None:
            messagebox.showinfo("Mở x.com", "Chưa chọn acc X.", parent=self.app)
            return

        def work():
            try:
                if not self.profiles.is_installed(acc):
                    self.profiles.create(acc)
                self.profiles.launch(acc, url="https://x.com/home")
            except Exception as exc:  # noqa: BLE001
                self.app._post(lambda e=exc: messagebox.showerror(
                    "Mở x.com", str(e), parent=self.app))
                return
            self.acc_store.mark_opened(acc.id)

        threading.Thread(target=work, daemon=True).start()
        self.app.set_status(f"Đang mở x.com bằng acc {acc.id}...")

    def _show_mode_row(self) -> None:
        """Hien o hop voi kieu dat lich dang chon, giau o kia di."""
        if self.auto.config.is_lich:
            # Trang DAT LICH khong dung moc gio/delay -- giau ca hai o.
            self.times_row.pack_forget()
            self.delay_row.pack_forget()
            return
        if self.mode_menu.get() == NHAN_DELAY:
            self.times_row.pack_forget()
            self.delay_row.pack(side="left", padx=(12, 10), pady=10)
        else:
            self.delay_row.pack_forget()
            self.times_row.pack(side="left", fill="x", expand=True,
                                padx=(12, 10), pady=10)

    def _pick_mode(self, _label: str) -> None:
        self._show_mode_row()
        self._save_from_ui(quiet=True)

    def _pick_page(self) -> None:
        """Lay danh sach fanpage acc dang chon quan ly, cho nguoi dung bam chon.

        Go tay ID rat de nham -- vi du go nham id trang ca nhan kieu moi cua chinh
        acc thi Business Suite chi bao "Sorry, this content isn't available right
        now", khong noi sai o dau. Lay san danh sach thi khong con nham duoc.
        """
        acc = self.account()
        if acc is None:
            messagebox.showinfo("Fanpage của acc", "Chưa chọn acc.", parent=self.app)
            return
        self.page_label.configure(text="đang lấy danh sách...", text_color="gray60")

        def work():
            pages, loi = fbpage.list_managed_pages(acc.cookie)

            def xong():
                if not pages:
                    self.page_label.configure(text="", text_color="gray60")
                    messagebox.showwarning("Fanpage của acc", loi, parent=self.app)
                    return
                self._show_page()
                chon = PagePickerDialog(self.app, acc.id, pages).show()
                if not chon:
                    return
                cfg = self.auto.config
                cfg.page_id, cfg.page_name = chon["id"], chon["name"]
                cfg.asset_id = chon["id"]     # danh sach nay von la so cua Business Suite
                self.page_entry.delete(0, "end")
                self.page_entry.insert(0, cfg.page_id)
                self.auto.save()
                self._show_page()
                self.app.set_status(f"Fanpage: {cfg.page_name} ({cfg.page_id})")
            self.app._post(xong)

        threading.Thread(target=work, daemon=True).start()

    def _sync_page_entry(self) -> None:
        """Ghi lai o ID sau khi tool tu doi sang so cua Business Suite."""
        self.page_entry.delete(0, "end")
        self.page_entry.insert(0, self.auto.config.page_id)
        self._show_page()

    def _show_kind_row(self) -> None:
        """Hien hang hop voi loai trang nay, giau hang kia di.

        Nhan ten (page_label) phai duoc pack LAI sau moi lan doi hang: pack xep
        theo thu tu goi, khong pack lai thi nhan nhay len truoc o nhap.
        """
        self.page_label.pack_forget()
        if self.platform == "x":
            self.page_row.pack_forget()
            self.group_row.pack_forget()
            self.x_row.pack(side="left", padx=(8, 0), pady=10)
        elif self.auto.config.is_group:
            self.page_row.pack_forget()
            self.group_row.pack(side="left", padx=(8, 0), pady=10)
        else:
            self.group_row.pack_forget()
            self.page_row.pack(side="left", padx=(8, 0), pady=10)
        self.page_label.pack(side="left", padx=10, pady=10, fill="x", expand=True)

    def _detect_group(self) -> None:
        """Doc ten nhom bang phien dang nhap cua acc -- cung de kiem acc co vao duoc."""
        if not self._save_from_ui(quiet=True):
            return
        cfg = self.auto.config
        if not cfg.group_id:
            messagebox.showinfo("Nhận diện", "Chưa dán link nhóm.", parent=self.app)
            return
        acc = self.account()
        if acc is None:
            messagebox.showinfo("Nhận diện", "Chưa chọn acc.", parent=self.app)
            return
        self.page_label.configure(text="đang hỏi Facebook...", text_color="gray60")

        def work():
            ten, loi = fbpage.detect_group_name(cfg.group_id, acc.cookie)

            def xong():
                if ten:
                    cfg.group_name = ten
                    self.auto.save()
                    self._show_page()
                    self.app.set_status(f"Nhóm: {ten}")
                else:
                    self.page_label.configure(text="không nhận diện được",
                                              text_color="#c44")
                    messagebox.showwarning("Nhận diện", loi, parent=self.app)
            self.app._post(xong)

        threading.Thread(target=work, daemon=True).start()

    def _open_group(self) -> None:
        """Mo trang nhom bang acc da chon, de xem da tham gia nhom do chua."""
        if not self._save_from_ui(quiet=True):
            return
        cfg = self.auto.config
        if not cfg.group_id:
            messagebox.showinfo("Mở nhóm", "Chưa dán link nhóm.", parent=self.app)
            return
        acc = self.account()
        if acc is None:
            messagebox.showinfo("Mở nhóm", "Chưa chọn acc.", parent=self.app)
            return
        # Acc chua co profile -> tool tu tao khi mo (core launch), khong chan nua.
        url = autoup_module.group_url(cfg.group_id)

        def work():
            try:
                self.profiles.launch(acc, url=url,
                                     on_status=lambda m: self.app._post(lambda t=m: self.app.set_status(t)))
            except Exception as exc:
                self.app._post(lambda e=exc: messagebox.showerror("Mở nhóm", str(e),
                                                                  parent=self.app))
                return
            self.acc_store.mark_opened(acc.id)
            self.app._post(self.app.refresh)

        threading.Thread(target=work, daemon=True).start()
        self.app.set_status(f"Đang mở nhóm {cfg.group_id} bằng acc {acc.id}...")

    def _pick_method(self, _label: str) -> None:
        self._save_from_ui(quiet=True)

    # ---------------------------------------------------------------- chay
    def _toggle(self) -> None:
        if not self._save_from_ui(quiet=True):
            self.enabled_var.set(False)
            return
        if self.enabled_var.get():
            thieu = self._missing()
            if thieu:
                self.enabled_var.set(False)
                self.auto.config.enabled = False
                self.auto.save()
                messagebox.showwarning(
                    "Chưa bật được",
                    "Còn thiếu:" + chr(10) * 2 + "- " + (chr(10) + "- ").join(thieu),
                    parent=self.app)
                return
            # Bat lai sau khi trang bi DUNG vi het acc dung duoc (checkpoint / loi 2 lan):
            # coi nhu nguoi dung da xu ly acc -> mo lai het de dang tiep.
            if self.auto.accounts() and not self.auto.accounts_usable():
                n = self.auto.mo_lai_acc()
                self._show_account()
                self.app.set_status(f"Đã mở lại {n} acc bị dừng.")
            # Vua BAT cong tac: delay -> chay NGAY (setup xong bat la dang luon);
            # list -> bo qua moc da qua, cho moc ke tiep (khong don bai cu).
            kq = self._goi_modun_job("bat")
            self.app.set_status(("Đã bật — " + kq.ghi_chu.split("— ", 1)[-1]) if kq.ok else f"Không bật được: {kq.loi}")
        else:
            kq = self._goi_modun_job("tat")
            # TAT KHONG DUOC PHEP that bai im lang: truoc day bo qua ket qua va
            # van bao "Đã tắt" -> mo-dun tu choi job (loai 'lich') ma trang van
            # chay tiep. Gio tat bang tay ngay tai cho de chac chan no dung.
            if not (kq and kq.ok):
                self.auto.config.enabled = False
                self.auto.save()
                self.auto.stop()
                self.app.set_status("Đã tắt tự động đăng (tắt trực tiếp — "
                                    f"mô-đun báo: {getattr(kq, 'loi', '') or 'không rõ'}).")
            else:
                self.app.set_status("Đã tắt tự động đăng video.")

    def _goi_modun_job(self, hanh_dong: str, **them):
        """Tool goi DUNG mo-dun dang bai theo loai job (ADR-028): page -> dang_fanpage_tu_dong,
        group -> dang_nhom_tu_dong. Tra KetQua."""
        _modun_tat_ca.nap()
        ma = "dang_nhom_tu_dong" if self.auto.config.is_group else "dang_fanpage_tu_dong"
        nc = modun_module.ngu_canh_tu(self.app, log=lambda m: self.app._post(lambda t=m: self.app.set_status(t)))
        return modun_module.chay(ma, nc, [], job=self.auto, hanh_dong=hanh_dong, **them)

    def _missing(self) -> list[str]:
        """Nhung thu con thieu de chay duoc. Rong nghia la du."""
        cfg = self.auto.config
        thieu = []
        if not cfg.folder or not os.path.isdir(cfg.folder):
            thieu.append("thư mục video (chưa chọn hoặc không tồn tại)")
        if cfg.is_lich:
            if not (cfg.khung_lich or []):
                thieu.append("khung giờ đặt lịch (chưa thêm khung nào)")
            if not cfg.mui_gio:
                thieu.append("múi giờ page")
        elif cfg.schedule_mode == "list" and not cfg.times:
            thieu.append("giờ đăng (chưa đặt mốc nào)")
        elif cfg.schedule_mode == "delay" and int(cfg.delay_minutes or 0) < 1:
            thieu.append("số phút giãn cách")
        ids = self.auto.accounts()
        mat = [a for a in ids if self.acc_store.get(a) is None]
        if cfg.is_group:
            if not cfg.group_id:
                thieu.append("link nhóm")
            if not ids:
                thieu.append("acc đăng")
            elif mat:
                thieu.append("acc không còn trong bảng: " + ", ".join(mat))
            return thieu
        if self.platform == "x":
            # X: khong co ID fanpage; bat buoc co acc X (bai len tuong acc do).
            if not ids:
                thieu.append("acc X đăng bài (chọn từ tab Quản lý acc → X.com)")
            elif mat:
                thieu.append("acc không còn trong bảng X: " + ", ".join(mat))
            return thieu
        if not cfg.page_id:
            thieu.append("ID fanpage")
        if cfg.method == "browser":
            if not ids:
                thieu.append("acc đăng (cần phiên đăng nhập để vào Business Suite)")
            elif mat:
                thieu.append("acc không còn trong bảng: " + ", ".join(mat))
        elif not cfg.token:
            thieu.append("token của fanpage (cách đăng Graph API cần token)")
        return thieu

    def _run_once(self) -> None:
        if not self._save_from_ui(quiet=True):
            return
        thieu = self._missing()
        if thieu:
            messagebox.showwarning(
                "Chưa đăng được",
                "Còn thiếu:" + chr(10) * 2 + "- " + (chr(10) + "- ").join(thieu),
                parent=self.app)
            return
        video = self.auto.next_video()
        if not video:
            messagebox.showinfo("Đăng thử", "Thư mục không có video nào sẵn sàng.",
                                parent=self.app)
            return
        if not messagebox.askyesno(
            "Đăng thử",
            f"Đăng ngay video này lên {self.auto.config.label()}?" + chr(10) * 2
            + os.path.basename(video)
            + (chr(10) * 2 + "Đăng xong sẽ XOÁ file." if self.auto.config.delete_after else ""),
            parent=self.app,
        ):
            return

        def work():
            self._goi_modun_job("dang_ngay", video=video)     # mo-dun (ADR-028)
            self.app._post(self._refresh_log)

        threading.Thread(target=work, daemon=True).start()
        self.app.set_status(f"Đang đăng {os.path.basename(video)}...")

    # ---------------------------------------------------------------- nhat ky / trang thai
    def _refresh_log(self) -> None:
        dong = [f"{d['at']}  {'OK ' if d['ok'] else 'LỖI'}  {d['text']}"
                for d in self.auto.history[-200:]]
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.insert("1.0", chr(10).join(reversed(dong)))
        self.log_box.configure(state="disabled")
        # Neu cua so nhat ky lon dang mo -> cap nhat luon.
        if getattr(self, "_log_win", None) is not None and self._log_win.winfo_exists():
            self._fill_log_window()

    def _clear_log(self) -> None:
        self.auto.history = []
        self.auto.save()
        self._refresh_log()

    def _open_log_window(self) -> None:
        """Mo nhat ky ra cua so LON, de doc va copy. Co nut lam moi + tu cap nhat."""
        win = getattr(self, "_log_win", None)
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_force()
            return
        win = ctk.CTkToplevel(self)
        self._log_win = win
        win.title(f"Nhật ký — {self.auto.config.label()}")
        win.geometry("960x640")
        win.minsize(560, 360)
        try:
            win.after(200, win.lift)
        except Exception:  # noqa: BLE001
            pass

        top = ctk.CTkFrame(win, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkLabel(top, text="Nhật ký đăng bài", anchor="w",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        self._log_win_count = ctk.CTkLabel(top, text="", text_color="gray55")
        self._log_win_count.pack(side="left", padx=10)
        ctk.CTkButton(top, text="Đóng", width=80, fg_color="gray45",
                      command=win.destroy).pack(side="right")
        ctk.CTkButton(top, text="📋 Chép hết", width=100,
                      command=self._copy_log).pack(side="right", padx=(6, 0))
        ctk.CTkButton(top, text="🔄 Làm mới", width=100,
                      command=lambda: self._fill_log_window()).pack(side="right", padx=(6, 0))

        box = ctk.CTkTextbox(win, font=ctk.CTkFont(size=14), wrap="word")
        box.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self._log_win_box = box
        self._fill_log_window()

    def _log_lines(self) -> list:
        return [f"{d['at']}  {'✔ OK ' if d['ok'] else '✖ LỖI'}  {d['text']}"
                for d in self.auto.history]

    def _fill_log_window(self) -> None:
        box = getattr(self, "_log_win_box", None)
        if box is None or not box.winfo_exists():
            return
        dong = self._log_lines()
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", chr(10).join(reversed(dong)))   # moi nhat len dau
        box.configure(state="disabled")
        cnt = getattr(self, "_log_win_count", None)
        if cnt is not None and cnt.winfo_exists():
            cnt.configure(text=f"{len(dong)} dòng")

    def _copy_log(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(chr(10).join(reversed(self._log_lines())))
            self.app.set_status("Đã chép nhật ký vào clipboard.")
        except Exception:  # noqa: BLE001
            pass

    def _tick_ui(self) -> None:
        """Moi giay cap nhat dong ho dem nguoc, dong trang thai va nhat ky."""
        try:
            self.countdown.configure(text=self._countdown_text())
            self.state_label.configure(text=self._state_text())
            # tally() QUET DIA (dem file trong thu muc) -> khong quet moi giay (treo khi
            # thu muc nhieu file). Chi quet lai ~5s/lan, con lai hien ban da cache.
            self._tally_i = getattr(self, "_tally_i", 0) + 1
            if self._tally_i % 5 == 1:
                self._tally_cache = self.auto.tally()
            self.tally_label.configure(text=getattr(self, "_tally_cache", ""))
            if len(self.auto.history) != getattr(self, "_log_len", -1):
                self._log_len = len(self.auto.history)
                self._refresh_log()
            # Trang DAT LICH: bang khung gio + dong tom tat phai TU LAM MOI. Truoc
            # day chi ve lai khi nguoi dung go -> dang xong roi ma van hien "Chờ"
            # va "đã chạy 0/5". lich_danh_gia() la ham THUAN nen 3s/lan la nhe.
            if self.auto.config.is_lich and self._tally_i % 3 == 1:
                self._lich_ve()
            # Trang thai acc (checkpoint / bo / dem loi) doi o luong dang -> ve lai the acc.
            dau_acc = tuple(sorted((a, str(st.get("tt")), int(st.get("loi") or 0))
                                   for a, st in self.auto.acc_states.items()))
            if dau_acc != getattr(self, "_acc_sig", None):
                self._acc_sig = dau_acc
                self._show_account()
            # Hang doi: lam moi khi so luong hoac trang thai doi.
            dau = (len(self.auto.queue), tuple(it.get("status") for it in self.auto.queue))
            if dau != getattr(self, "_queue_sig", None):
                self._queue_sig = dau
                self._refresh_queue()
        except tk.TclError:
            return                       # cua so da dong
        self.after(1000, self._tick_ui)

    def _countdown_text(self) -> str:
        """Dong ho dem nguoc: mm:ss toi luot dang ke tiep."""
        cfg = self.auto.config
        if not cfg.enabled or cfg.schedule_mode != "delay":
            return ""
        if self.auto.busy:
            return "đang đăng…"
        # Trang DAT LICH: het khung trong ngay thi DUNG HAN — khong duoc dem nguoc
        # nhu sap dang bai tiep (nguoi dung bao: da du 5/5 ma van dem 02:14).
        if cfg.is_lich and not self.auto.lich_con_khung():
            return ""
        con = self.auto.seconds_left()
        if con is None:
            return ""
        if con <= 0:
            return "00:00"
        return f"{con // 60:02d}:{con % 60:02d}"

    def _state_text(self) -> str:
        cfg = self.auto.config
        if not cfg.enabled:
            return "Đang tắt"
        den_gh = self.auto.gioi_han_den()
        if den_gh is not None:
            return (f"⏳ Bị GIỚI HẠN ĐĂNG — tạm dừng, sẽ đăng lại lúc "
                    f"{den_gh.strftime('%H:%M ngày %d/%m')}")
        mat = self.auto.thu_muc_mat()
        if mat:
            return f"⚠ Thư mục video KHÔNG TỒN TẠI: {mat} — chọn lại thư mục"
        if self.platform == "x":
            so_video = (len(fbupload.find_by_kind(cfg.folder, self.auto.effective_kind()))
                        if cfg.folder else 0)
            phan = [f"{so_video} bài (video/ảnh/chữ) trong thư mục"]
        else:
            so_video = len(fbupload.find_videos(cfg.folder)) if cfg.folder else 0
            phan = [f"{so_video} video trong thư mục"]
        if self.auto.busy:
            phan.append("đang đăng...")
        elif cfg.is_lich and not self.auto.lich_con_khung():
            # Het khung hom nay -> KHONG hen "bai ke tiep" nua, cho sang ngay mai.
            phan.append("xong hôm nay — chờ ngày mai")
        elif cfg.schedule_mode == "delay":
            ke_tiep = self.auto.next_run_at()
            if ke_tiep:
                phan.append(f"bài kế tiếp {ke_tiep.strftime('%H:%M:%S')}")
        else:
            sap_toi = self._next_slot()
            if sap_toi:
                phan.append(f"mốc kế tiếp {sap_toi}")
        return "  •  ".join(phan)

    def _next_slot(self) -> str:
        """Moc gio ke tiep trong hom nay. Het roi thi la moc dau cua ngay mai."""
        from datetime import datetime

        cfg = self.auto.config
        if cfg.is_lich:
            # Trang DAT LICH: "moc ke tiep" = khung dau tien con CHO.
            from core import lich_dang as ld
            cho = [d for d in self.auto.lich_danh_gia() if d["ket_qua"] == ld.CHO]
            return f"{cho[0]['chay']} (chạy)" if cho else ""
        if not cfg.times:
            return ""
        bay_gio = datetime.now().strftime("%H:%M")
        for moc in sorted(cfg.times):
            if moc > bay_gio:
                return moc
        return sorted(cfg.times)[0] + " (ngày mai)"

class AutoUpTab(ctk.CTkFrame):
    """Khung chua nhieu tab con, moi tab mot fanpage.

    Nguoi dung tu them tab, dat ten, moi tab chay doc lap. Danh sach tab va cau
    hinh tung tab nam trong data/, nen tat tool mo lai van con nguyen va tu chay
    tiep -- khong phai bat lai.
    """

    def __init__(self, parent, app, kind: str = "page", manager=None,
                 acc_store=None, profiles=None):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        # Manager rieng cho tung he: Facebook = app.autoup, X = app.autoup_x.
        # Mac dinh app.autoup de goi cu AutoUpTab(parent, app, kind) van chay.
        self.manager = manager or app.autoup
        # Bang acc + profile cua tab (X = cua tab Quan ly acc X), truyen xuong JobPanel.
        self.acc_store = acc_store
        self.profiles = profiles
        # "page" = fanpage · "group" = nhom · "lich" = fanpage DAT LICH (gio chay + gio dang + mui gio).
        self.kind = kind if kind in ("group", "lich") else "page"
        self.panel = None
        if getattr(self.manager, "platform", "fb") == "x":
            nhan_loai = "trang X đặt lịch" if self.kind == "lich" else "trang X"
        else:
            nhan_loai = {"group": "nhóm", "lich": "trang đặt lịch"}.get(self.kind, "fanpage")

        thanh = ctk.CTkFrame(self, fg_color="transparent")
        thanh.pack(fill="x", padx=PAD, pady=(PAD, 0))
        dam = ctk.CTkFont(weight="bold")
        ctk.CTkButton(thanh, text=f"➕ Thêm {nhan_loai}",
                      width=160, font=dam, command=self.add_job).pack(side="left")
        ctk.CTkButton(thanh, text="✏️ Đổi tên", width=100, fg_color="gray45",
                      command=self.rename_job).pack(side="left", padx=6)
        ctk.CTkButton(thanh, text="🗑 Xoá", width=90, fg_color="#a33",
                      command=self.remove_job).pack(side="left")
        # Cong cu nho: tao list gio dang lech dan de nhieu acc khong dang trung gio.
        ctk.CTkButton(thanh, text="🕒 Tạo giờ đăng bài", width=150, fg_color="#6a4fa5",
                      command=self.open_schedule_gen).pack(side="left", padx=6)
        ctk.CTkButton(thanh, text="📊 Thống kê", width=110, fg_color="#2f6f8f",
                      command=self.open_stats).pack(side="left")

        ctk.CTkLabel(thanh, text="Chạy cùng lúc", font=dam).pack(side="left", padx=(20, 4))
        self.parallel_box = ctk.CTkOptionMenu(
            thanh, width=70, font=dam,
            values=[str(n) for n in (1, 2, 3, 5, 8, 10, 15, 20, 25, 30)],
            command=self._set_parallel)
        self.parallel_box.set(str(self.manager.max_parallel))
        self.parallel_box.pack(side="left")
        if self.kind == "lich":
            # RAO giua cac trang: bat tool len ca chuc trang cung den han thi
            # chuc Firefox mo mot luc -> giai deu ra, moi trang cach nhau N phut.
            ctk.CTkLabel(thanh, text="Cách nhau giữa các trang", font=dam).pack(
                side="left", padx=(16, 4))
            self.e_cach_tab = ctk.CTkEntry(thanh, width=55)
            self.e_cach_tab.insert(0, str(self.manager.cach_tab_phut))
            self.e_cach_tab.bind("<KeyRelease>", lambda _e: self._set_cach_tab())
            self.e_cach_tab.bind("<FocusOut>", lambda _e: self._set_cach_tab())
            self.e_cach_tab.pack(side="left")
            ctk.CTkLabel(thanh, text="phút", text_color="gray60").pack(side="left", padx=(4, 0))
        else:
            ctk.CTkLabel(thanh, text="· cùng một acc luôn xếp hàng, không chạy chồng",
                         text_color="gray60").pack(side="left", padx=8)
        self.running_label = ctk.CTkLabel(thanh, text="", text_color="#2f7d4f", font=dam)
        self.running_label.pack(side="right", padx=10)

        # Danh sach ben trai + mot bang ben phai. KHONG dung thanh tab ngang:
        # 50-100 trang thi thanh tab tran ra ngoai man hinh, va dung mot luc ca
        # tram bang dieu khien mat 17 giay (da do) -- mo tool la dung hinh.
        than = ctk.CTkFrame(self, fg_color="transparent")
        than.pack(fill="both", expand=True, padx=PAD, pady=(6, 0))

        self.list_frame = ctk.CTkScrollableFrame(
            than, width=220,
            label_text={"group": "Nhóm", "lich": "Đặt lịch"}.get(self.kind, "Fanpage"))
        self.list_frame.pack(side="left", fill="y")
        self.body = ctk.CTkFrame(than, fg_color="transparent")
        self.body.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self.current_id = ""
        self.buttons: dict = {}
        self._rebuild()
        self._tick_running()

    # ---------------------------------------------------------------- danh sach
    @property
    def jobs(self) -> list:
        """Chi cac trang thuoc dung loai cua tab nay."""
        return self.manager.by_kind(self.kind)

    def _rebuild(self, chon: str = "") -> None:
        """Ve lai danh sach trang. Chi dung bang dieu khien cua trang dang xem."""
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.buttons = {}
        for job in self.jobs:
            nut = ctk.CTkButton(
                self.list_frame, text=self._label(job), anchor="w", height=30,
                fg_color="transparent", text_color=("gray10", "gray90"),
                hover_color=("gray80", "gray30"),
                command=lambda j=job: self.select(j.job_id),
            )
            nut.pack(fill="x", pady=1)
            self.buttons[job.job_id] = nut

        cua_tab = {j.job_id for j in self.jobs}
        muon = chon if chon in cua_tab else (self.current_id
                                             if self.current_id in cua_tab else "")
        if not muon:
            muon = self.jobs[0].job_id if self.jobs else ""
        self.current_id = ""
        for w in self.body.winfo_children():
            w.destroy()
        self.panel = None
        if muon:
            self.select(muon)
        else:
            nhan = self._nhan_loai()
            ctk.CTkLabel(
                self.body, text=f"Chưa có {nhan} nào. Bấm “Thêm {nhan}” để tạo.",
                text_color="gray60").pack(pady=40)

    def _nhan_loai(self) -> str:
        return {"group": "nhóm", "lich": "trang đặt lịch"}.get(self.kind, "fanpage")

    @staticmethod
    def _label(job) -> str:
        dau = "●" if job.config.enabled else "○"
        return f"{dau}  {job.name}"

    def select(self, job_id: str) -> None:
        """Mo mot trang. Bang dieu khien chi duoc dung luc nay, khong dung san."""
        if job_id == self.current_id:
            return
        job = self.manager.get(job_id)
        if job is None:
            return
        for w in self.body.winfo_children():
            w.destroy()
        self.current_id = job_id
        self.panel = JobPanel(self.body, self.app, job, manager=self.manager,
                              acc_store=self.acc_store, profiles=self.profiles)
        self.panel.pack(fill="both", expand=True)
        for ma, nut in self.buttons.items():
            nut.configure(fg_color=("gray75", "gray28") if ma == job_id else "transparent")

    def current(self):
        return self.manager.get(self.current_id)

    def refresh_labels(self) -> None:
        for job in self.jobs:
            nut = self.buttons.get(job.job_id)
            if nut is not None:
                nut.configure(text=self._label(job))

    def _set_parallel(self, value: str) -> None:
        so = self.manager.set_parallel(value)
        self.parallel_box.set(str(so))
        self.app.set_status(f"Chạy tối đa {so} trang cùng lúc.")

    def _set_cach_tab(self) -> None:
        """Luu rao giua cac trang dat lich (0 = tat rao)."""
        try:
            so = max(0, int((self.e_cach_tab.get() or "").strip()))
        except ValueError:
            return                       # dang gõ dở, chưa phải số -> chưa lưu
        if so == self.manager.cach_tab_phut:
            return
        self.manager.cach_tab_phut = so
        self.manager.save_index()
        self.app.set_status("Các trang đặt lịch cách nhau " + (f"{so} phút." if so
                                                               else "0 phút (tắt rào)."))

    def _tick_running(self) -> None:
        """Moi giay hien so trang dang chay -- de nhin ra co bi don ung khong."""
        try:
            dang = self.manager.running_ids
            cho = self.manager.waiting_ids
            phan = []
            if dang:
                phan.append(f"đang chạy {len(dang)}/{self.manager.max_parallel}")
            if cho:
                phan.append(f"{len(cho)} chờ tới lượt")
            self.running_label.configure(text="  ·  ".join(phan))
            self.refresh_labels()
        except tk.TclError:
            return
        self.after(1000, self._tick_running)

    def open_schedule_gen(self) -> None:
        """Mở bảng tạo list giờ đăng lệch dần (tránh trùng giờ nhiều acc).

        Truyền danh sách tab (job) cùng loại + hàm làm mới để người dùng GỬI list giờ
        thẳng vào các tab (mỗi dòng giờ -> 1 tab, theo thứ tự hoặc tự chọn từng dòng).
        """
        from ui.schedule_dialog import ScheduleGenDialog

        def ap_dung():
            # Tab dang xem co the vua nhan list gio moi -> ve lai o giờ + bang.
            if self.panel is not None:
                try:
                    self.panel._load_from_config()
                except Exception:  # noqa: BLE001
                    pass
            self._rebuild()

        ScheduleGenDialog(self.app,
                          jobs_fn=lambda: self.manager.by_kind(self.kind),
                          nhan_loai=self._nhan_loai(),
                          on_applied=ap_dung)

    def open_stats(self) -> None:
        """Bảng tổng hợp thống kê các tab cùng loại (fanpage/nhóm)."""
        from ui.stats_dialog import StatsDialog
        nhan = self._nhan_loai()
        StatsDialog(self.app, lambda: self.manager.by_kind(self.kind),
                    tieu_de=f"Thống kê Auto đăng {nhan}")

    def add_job(self) -> None:
        nhan = self._nhan_loai()
        ten = SimplePromptDialog(self.app, f"Thêm {nhan}",
                                 f"Đặt tên cho {nhan} mới:", "").show()
        if ten is None:
            return
        job = self.manager.add(ten, kind=self.kind)
        self._rebuild(chon=job.job_id)
        self.app.set_status(f"Đã thêm trang '{job.name}'.")

    def rename_job(self) -> None:
        job = self.current()
        if job is None:
            return
        ten = SimplePromptDialog(self.app, "Đổi tên trang",
                                 "Tên mới:", job.name).show()
        if not ten:
            return
        self.manager.rename(job.job_id, ten)
        self._rebuild(chon=job.job_id)
        self.app.set_status(f"Đã đổi tên thành '{job.name}'.")

    def remove_job(self) -> None:
        job = self.current()
        if job is None:
            return
        if not messagebox.askyesno(
            "Xoá trang",
            f"Xoá trang '{job.name}'?" + chr(10) * 2
            + "Cấu hình, lịch và nhật ký của trang này sẽ mất. "
              "Video trong thư mục vẫn còn nguyên.",
            parent=self.app,
        ):
            return
        self.manager.remove(job.job_id)
        self.current_id = ""
        self._rebuild()
        self.app.set_status(f"Đã xoá trang '{job.name}'.")



class AddPostDialog(BaseDialog):
    """Nhap tay mot bai dang: caption + chon anh, hoac chi chu (text)."""

    def __init__(self, parent):
        super().__init__(parent, "Thêm bài viết", 620, 560)
        self.minsize(500, 420)
        self._images: list = []

        ctk.CTkLabel(self, text="Nội dung bài (caption):").pack(
            anchor="w", padx=PAD, pady=(PAD, 2))
        self.caption_box = ctk.CTkTextbox(self, height=180)
        self.caption_box.pack(fill="both", expand=True, padx=PAD, pady=(0, 6))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=PAD, pady=4)
        ctk.CTkLabel(row, text="Thể loại:").pack(side="left")
        self.kind_var = tk.StringVar(value="image")
        ctk.CTkRadioButton(row, text="Ảnh", variable=self.kind_var, value="image",
                           command=self._toggle).pack(side="left", padx=(8, 4))
        ctk.CTkRadioButton(row, text="Chỉ chữ (text)", variable=self.kind_var,
                           value="text", command=self._toggle).pack(side="left", padx=4)

        self.img_row = ctk.CTkFrame(self, fg_color="transparent")
        self.img_row.pack(fill="x", padx=PAD, pady=2)
        ctk.CTkButton(self.img_row, text="📁 Chọn ảnh...", width=120,
                      command=self._pick_images).pack(side="left")
        self.img_label = ctk.CTkLabel(self.img_row, text="chưa chọn ảnh",
                                      text_color="gray60", anchor="w")
        self.img_label.pack(side="left", padx=10, fill="x", expand=True)

        ctk.CTkLabel(
            self, text="Chọn nhiều ảnh = mỗi ảnh thành một bài riêng (cùng caption).",
            text_color="gray60", justify="left",
        ).pack(anchor="w", padx=PAD)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=PAD, pady=(6, PAD))
        ctk.CTkButton(btns, text="Hủy", width=90, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(btns, text="Lưu vào bảng", width=130,
                      command=self._submit).pack(side="right", padx=6)
        self.after(200, lambda: self.caption_box.focus_set())

    def _toggle(self):
        if self.kind_var.get() == "image":
            self.img_row.pack(fill="x", padx=PAD, pady=2)
        else:
            self.img_row.pack_forget()

    def _pick_images(self):
        files = filedialog.askopenfilenames(
            parent=self, title="Chọn ảnh",
            filetypes=[("Ảnh", "*.jpg *.jpeg *.png *.webp *.gif"), ("Tất cả", "*.*")])
        if files:
            self._images = list(files)
            self.img_label.configure(text=f"{len(self._images)} ảnh đã chọn")

    def _submit(self):
        caption = self.caption_box.get("1.0", "end").strip()
        kind = self.kind_var.get()
        if kind == "image" and not self._images:
            messagebox.showinfo("Thêm bài viết", "Chưa chọn ảnh.", parent=self)
            return
        if kind == "text" and not caption:
            messagebox.showinfo("Thêm bài viết", "Bài chữ phải có nội dung.", parent=self)
            return
        self.result = (caption, kind, self._images)
        self.destroy()


class LinkBulkDialog(BaseDialog):
    """Dan mot list link (bai/video) -> moi link mot bai share vao nhom."""

    def __init__(self, parent):
        super().__init__(parent, "Thêm link hàng loạt", 640, 520)
        self.minsize(520, 400)

        ctk.CTkLabel(
            self, justify="left", wraplength=600,
            text="Dán danh sách LINK bài viết / video Facebook — mỗi link một dòng. "
                 "Mỗi link thành một bài share vào nhóm (Facebook tự tạo preview)."
        ).pack(anchor="w", padx=PAD, pady=(PAD, 4))

        ctk.CTkLabel(self, text="Câu mở đầu thêm trước mỗi link (không bắt buộc):").pack(
            anchor="w", padx=PAD)
        self.prefix_entry = ctk.CTkEntry(
            self, placeholder_text="vd: Mọi người xem video này nhé 👇 (để trống nếu chỉ đăng link)")
        self.prefix_entry.pack(fill="x", padx=PAD, pady=(2, 8))

        ctk.CTkLabel(self, text="Danh sách link (mỗi dòng 1 link):").pack(anchor="w", padx=PAD)
        self.links_box = ctk.CTkTextbox(self)
        self.links_box.pack(fill="both", expand=True, padx=PAD, pady=(2, 6))
        self.links_box.insert("1.0",
                              "https://www.facebook.com/...\nhttps://www.facebook.com/reel/...\n")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(btns, text="Hủy", width=90, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(btns, text="Thêm vào bảng", width=140,
                      command=self._submit).pack(side="right", padx=6)

    def _submit(self):
        raw = self.links_box.get("1.0", "end")
        links = []
        for line in raw.splitlines():
            line = line.strip()
            if line and "http" in line and line not in links:
                links.append(line)
        if not links:
            messagebox.showinfo("Thêm link", "Chưa có link hợp lệ (phải chứa http).",
                                parent=self)
            return
        self.result = (self.prefix_entry.get(), links)
        self.destroy()


class PromptPickDialog(BaseDialog):
    """Chon 'cau khoi chuyen' tu thu vien (bai text keo comment that).

    Tich chon cac cau muon dung. Moi cau la mau spintax -> dat ``self.chosen`` la
    list cac cau. Nguoi dung cung co the go them cau rieng o o duoi.
    """

    def __init__(self, parent):
        super().__init__(parent, "Câu khơi chuyện (kéo tương tác thật)", 660, 600)
        self.minsize(520, 440)
        self.chosen = None
        self._vars: list[tuple[tk.BooleanVar, str]] = []

        ctk.CTkLabel(
            self, justify="left", wraplength=620,
            text="Chọn câu để đăng vào nhóm cho thành viên tự comment (Facebook đánh giá "
                 "cao tương tác thật). Mỗi câu là mẫu {a|b} — mỗi lần đăng ra một bản khác."
        ).pack(anchor="w", padx=PAD, pady=(PAD, 6))

        khung = ctk.CTkScrollableFrame(self, fg_color="transparent")
        khung.pack(fill="both", expand=True, padx=PAD, pady=(0, 6))
        for cat in prompts_module.categories():
            ctk.CTkLabel(khung, text="▸ " + cat, font=("", 13, "bold"),
                         anchor="w").pack(fill="x", pady=(8, 2))
            for text in prompts_module.LIBRARY[cat]:
                var = tk.BooleanVar(value=False)
                n = spintax.count_variants(text)
                label = text.replace("\n", " ⏎ ")
                if len(label) > 90:
                    label = label[:90] + "…"
                ctk.CTkCheckBox(khung, text=f"{label}   ({n} biến thể)",
                                variable=var, onvalue=True, offvalue=False).pack(
                    anchor="w", padx=(12, 0), pady=1)
                self._vars.append((var, text))

        ctk.CTkLabel(self, text="Câu tự soạn thêm (mỗi dòng 1 câu, có thể dùng {a|b}):").pack(
            anchor="w", padx=PAD)
        self.custom_box = ctk.CTkTextbox(self, height=70)
        self.custom_box.pack(fill="x", padx=PAD, pady=(2, 6))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(btns, text="Hủy", width=90, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(btns, text="Thêm vào bảng", width=140,
                      command=self._submit).pack(side="right", padx=6)

    def _submit(self):
        chosen = [text for var, text in self._vars if var.get()]
        for line in self.custom_box.get("1.0", "end").splitlines():
            line = line.strip()
            if line and line not in chosen:
                chosen.append(line)
        if not chosen:
            messagebox.showinfo("Câu khơi chuyện", "Chưa chọn câu nào.", parent=self)
            return
        self.chosen = chosen
        self.destroy()
