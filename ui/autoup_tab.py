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
#: Nhan loai tab con trong khung "Auto dang fanpage" (dung cho hop thoai Them tab).
NHAN_TAB_LOAI = {"page": "Công khai", "lich": "Đặt lịch", "group": "Nhóm"}
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
        # Mo CHINH trang fanpage (facebook.com/<id>) de xem bai da len the nao --
        # khac nut tren (Business Suite la cho DANG bai).
        ctk.CTkButton(self.page_row, text="🔗 Mở fanpage", width=120, fg_color="#2f7d4f",
                      command=self._open_page).pack(side="left", padx=(6, 0))

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
        # Facebook chan dang vi spam -> cho acc do NGHI may ngay roi tu dang lai.
        ctk.CTkLabel(self.group_row, text="Bị chặn spam → nghỉ", font=dam).pack(
            side="left", padx=(14, 4))
        self.spam_entry = ctk.CTkEntry(self.group_row, width=45)
        self.spam_entry.pack(side="left")
        ctk.CTkLabel(self.group_row, text="ngày", text_color="gray60").pack(
            side="left", padx=(4, 0))

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

        # 0) SO NGAY DAT LICH: moi khung gio dat luon N bai cho N NGAY LIEN TIEP roi nghi
        # du N ngay -> khong bao gio hen hai bai vao cung mot gio (nguoi dung chot 02/10).
        hang(0, "Số ngày đặt lịch")
        o_ngay = ctk.CTkFrame(wrap, fg_color="transparent")
        o_ngay.grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=(14, 2))
        self.e_so_ngay = ctk.CTkEntry(o_ngay, width=55)
        self.e_so_ngay.pack(side="left")
        self.e_so_ngay.bind("<KeyRelease>", lambda _e: self._hen_lich_ve())
        ctk.CTkLabel(o_ngay, text="ngày", text_color="gray60").pack(side="left", padx=(6, 8))
        # Quen het dau cu, dang lai tu bai dau (nguoi dung TU bam, tool khong tu lam).
        ctk.CTkButton(o_ngay, text="↺ Chạy lại từ đầu", width=140, fg_color="#a33",
                      command=self.chay_lai_tu_dau).pack(side="left", padx=(0, 10))
        # Dong chu MO: dat den het ngay nao, hom nao chay dot moi.
        self.lich_songay = ctk.CTkLabel(o_ngay, text="", text_color="gray55", anchor="w",
                                        justify="left")
        self.lich_songay.pack(side="left", fill="x", expand=True)

        # 1) Gio TOOL CHAY -- hai kieu: danh sach moc gio, hoac cu cach N phut.
        hang(1, "Giờ tool chạy (theo khung giờ máy)")
        o_chay = ctk.CTkFrame(wrap, fg_color="transparent")
        o_chay.grid(row=1, column=1, sticky="ew", padx=(0, 14), pady=(14, 2))
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
        hang(2, "Múi giờ")
        o_tz = ctk.CTkFrame(wrap, fg_color="transparent")
        o_tz.grid(row=2, column=1, sticky="ew", padx=(0, 14), pady=(14, 2))
        self.tz_menu = ctk.CTkOptionMenu(o_tz, width=280, values=ld.danh_sach_nhan(),
                                         command=lambda _v: self._lich_nhap_doi())
        self.tz_menu.pack(side="left")
        # Gio HIEN TAI o nuoc do -- de nguoi dung biet ben do dang la ngay may.
        self.lich_bay_gio = ctk.CTkLabel(o_tz, text="", text_color="gray55", anchor="w")
        self.lich_bay_gio.pack(side="left", padx=(12, 0))

        # 3) Gio DAT LICH video -- go theo mui gio o tren.
        hang(3, "Giờ đặt lịch video")
        self.e_dang = ctk.CTkEntry(
            wrap, placeholder_text="07:00, 15:00, 20:00 — giờ ở múi giờ đã chọn")
        self.e_dang.grid(row=3, column=1, sticky="ew", padx=(0, 14), pady=(14, 2))
        # Dong TOM TAT nam TREN danh sach gio (nguoi dung chot 02/10: de thay ngay,
        # khong phai do xuong duoi mot rung gio).
        self.lich_tom = ctk.CTkLabel(wrap, text="", text_color="gray55", anchor="w",
                                     justify="left")
        self.lich_tom.grid(row=4, column=0, columnspan=2, sticky="ew", padx=14, pady=(10, 2))

        # Danh sach gio CUA CA DOT (N ngay) -- de trong khung CUON duoc: 3 ngay x nhieu gio
        # la vai chuc dong, khong the tran het ra man hinh.
        self.lich_cuon = ctk.CTkScrollableFrame(wrap, height=150, fg_color="transparent")
        self.lich_cuon.grid(row=5, column=0, columnspan=2, sticky="nsew",
                            padx=14, pady=(0, 10))
        self.lich_quydoi = ctk.CTkLabel(self.lich_cuon, text="", text_color="gray55",
                                        anchor="w", justify="left")
        self.lich_quydoi.pack(fill="x", anchor="w")
        wrap.grid_rowconfigure(5, weight=1)
        # Go toi dau quy doi toi do (cho 350ms cho go xong moi tinh).
        self.lich_tree = None
        self._hen_id = None
        for o in (self.e_chay, self.e_dang):
            o.bind("<KeyRelease>", lambda _e: self._hen_lich_ve())

    def chay_lai_tu_dau(self) -> None:
        """Nut "↺ Chạy lại từ đầu": xoa dau lich + con tro bai, dang lai tu bai dau."""
        job = self.auto
        if not messagebox.askyesno(
            "Chạy lại từ đầu",
            f"Cho trang “{job.name}” đăng lại TỪ BÀI ĐẦU?" + chr(10) * 2
            + "• Xoá dấu lịch của các khung giờ — khung sẽ tới lượt lại ngay." + chr(10)
            + "• Mở đợt đặt lịch mới tính từ hôm nay." + chr(10)
            + "• Con trỏ bài về bài 1, bỏ danh sách bài từng bị bỏ qua." + chr(10) * 2
            + "Các bài ĐÃ ĐĂNG vẫn được nhớ để không đăng trùng.",
                parent=self.app):
            return
        kq = job.chay_lai_tu_dau()
        self._load_from_config()
        self.app.set_status(
            f"Đã cho '{job.name}' chạy lại từ đầu (xoá {kq['lich']} dấu lịch, "
            f"bỏ {kq['bo_video']} bài từng bị bỏ qua).")

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
        self.e_so_ngay.delete(0, "end")
        self.e_so_ngay.insert(0, str(getattr(cfg, "so_ngay_dat_lich", None) or 1))
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
        # So ngay dat truoc: go bay thi ve 1 (chi dat cho hom nay), khong chan Luu.
        try:
            so_ngay = int((self.e_so_ngay.get() or "").strip())
        except ValueError:
            so_ngay = 1
        cfg.so_ngay_dat_lich = max(1, min(autoup_module.SO_NGAY_DAT_LICH_TOI_DA, so_ngay))
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
        # Cham CA DOT: dat 3 ngay thi bang gio phai hien du gio cua ca 3 ngay.
        cham = self.auto.lich_danh_gia_dot()
        # Dong chu mo canh o "So ngay dat lich": dat den het ngay nao, hom nao chay dot moi.
        # Doc THANG tu o nhap de go toi dau hien toi do (chua bam Luu cung thay).
        if getattr(self, "lich_songay", None) is not None:
            try:
                so = int((self.e_so_ngay.get() or "").strip())
            except ValueError:
                so = self.auto.so_ngay_lich()
            self.lich_songay.configure(text=autoup_module.ghi_chu_so_ngay(so))
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
        lech_cu = None
        for i, d in enumerate(cham, 1):
            # Dau moi NGAY cua dot: mot dong tieu de nho cho de doc.
            lech = int(d.get("lech") or 0)
            if lech != lech_cu:
                lech_cu = lech
                if lech:
                    dong.append(f"— ngày {lech + 1}/{self.auto.so_ngay_lich()} —")
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
        self.spam_entry.delete(0, "end")
        self.spam_entry.insert(0, str(getattr(cfg, "spam_ngay", None)
                                      or autoup_module.SPAM_NGAY_MAC_DINH))
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
        # So ngay nghi khi bi chan spam: go bay thi giu so cu (khong chan nguoi dung luu).
        try:
            so_ngay = int((self.spam_entry.get() or "").strip())
            if so_ngay > 0:
                cfg.spam_ngay = so_ngay
        except ValueError:
            pass
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

    def _open_page(self) -> None:
        """Mo CHINH trang fanpage bang acc da chon -- de xem bai da len the nao."""
        if not self._save_from_ui(quiet=True):
            return
        cfg = self.auto.config
        if not cfg.page_id:
            messagebox.showinfo("Mở fanpage", "Chưa nhập ID fanpage.", parent=self.app)
            return
        acc = self.account()
        if acc is None:
            messagebox.showinfo("Mở fanpage", "Chưa chọn acc.", parent=self.app)
            return
        url = autoup_module.page_url(cfg.page_id)

        def work():
            try:
                self.profiles.launch(
                    acc, url=url,
                    on_status=lambda m: self.app._post(lambda t=m: self.app.set_status(t)))
            except Exception as exc:
                self.app._post(lambda e=exc: messagebox.showerror("Mở fanpage", str(e),
                                                                  parent=self.app))
                return
            self.acc_store.mark_opened(acc.id)
            self.app._post(self.app.refresh)

        threading.Thread(target=work, daemon=True).start()
        ten = cfg.page_name or cfg.page_id
        self.app.set_status(f"Đang mở fanpage {ten} bằng acc {acc.id}...")

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
                 acc_store=None, profiles=None, tab_id: str = ""):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        #: Tab con dang xem (rong = tab mac dinh). Danh sach trang cua tab nay RIENG.
        self.tab_id = tab_id or ""
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
        self.xoa_btn = ctk.CTkButton(thanh, text="🗑 Xoá", width=110, fg_color="#a33",
                                     command=self.remove_job)
        self.xoa_btn.pack(side="left")
        # Gom cac trang thanh NHOM cho de quan ly. Mac dinh KHONG co nhom nao -> danh sach
        # phang nhu cu; tao nhom roi thi keo tha trang qua lai giua cac nhom.
        ctk.CTkButton(thanh, text="🗂 Nhóm mới", width=110, fg_color="#2f6f8f",
                      command=self.add_nhom).pack(side="left", padx=6)
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
        # Keo chuot tu CHO TRONG = quet chon nhieu trang (keo trung mot dong thi la
        # di chuyen trang do vao nhom -- xem _keo_bat_dau).
        self.list_frame.bind("<Button-1>", self._quet_bat_dau)
        self.list_frame.bind("<B1-Motion>", self._quet_di)
        self.list_frame.bind("<ButtonRelease-1>", self._quet_tha)
        self.body = ctk.CTkFrame(than, fg_color="transparent")
        self.body.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self.current_id = ""
        self.buttons: dict = {}
        #: Nhom nao dang mo (ten -> True/False). Mac dinh mo het.
        self._nhom_mo: dict = {}
        #: Cac trang DANG CHON (job_id). Keo vung trong / Ctrl+bam / Shift+bam de chon nhieu,
        #: roi xoa hoac chuyen nhom ca loat.
        self._chon: set = set()
        #: Dang keo vung trong de QUET CHON: (y bat dau, khung ve duong vien).
        self._quet = None
        #: Dang keo trang nao + o tha dang di qua (to mau de nguoi dung biet se tha vao dau).
        self._keo_job = ""
        self._keo_that = False
        self._o_sang = None
        self._rebuild()
        self._tick_running()

    # ---------------------------------------------------------------- danh sach
    @property
    def jobs(self) -> list:
        """Chi cac trang thuoc dung loai VA dung tab con dang xem."""
        return self.manager.by_kind(self.kind, self.tab_id)

    def _rebuild(self, chon: str = "") -> None:
        """Ve lai danh sach trang. Chi dung bang dieu khien cua trang dang xem.

        Chua tao nhom nao -> danh sach PHANG y nhu truoc. Co nhom -> moi nhom mot tieu de
        (bam de thu/mo), duoi la cac trang cua nhom, cuoi cung la "Chua phan nhom".
        """
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.buttons = {}
        self._o_sang = None

        nhoms = self.manager.cac_nhom(self.kind, self.tab_id)
        theo_nhom: dict = {ten: [] for ten in nhoms}
        chua: list = []
        for job in self.jobs:
            ten = str(getattr(job.config, "nhom", "") or "")
            (theo_nhom[ten] if ten in theo_nhom else chua).append(job)

        if not nhoms:
            for job in chua:
                self._ve_dong(self.list_frame, job)
        else:
            for ten in nhoms:
                self._ve_tieu_de_nhom(ten, len(theo_nhom[ten]))
                if self._nhom_mo.get(ten, True):
                    for job in theo_nhom[ten]:
                        self._ve_dong(self.list_frame, job, trong_nhom=True)
            self._ve_tieu_de_nhom("", len(chua))
            if self._nhom_mo.get("", True):
                for job in chua:
                    self._ve_dong(self.list_frame, job, trong_nhom=True)

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

    # ---- ve mot dong / mot tieu de nhom -------------------------------
    def _ve_tieu_de_nhom(self, ten: str, so: int) -> None:
        """Tieu de mot nhom -- cung la O THA khi keo trang vao nhom do."""
        mo = self._nhom_mo.get(ten, True)
        nhan = ten or "Chưa phân nhóm"
        khung = ctk.CTkFrame(self.list_frame, fg_color=("gray82", "gray22"), height=26)
        khung.pack(fill="x", pady=(6, 1))
        khung._nhom_dich = ten                      # o tha: keo trang vao day = vao nhom nay
        khung._mau_goc = ("gray82", "gray22")
        chu = ctk.CTkLabel(khung, text=f"{'▾' if mo else '▸'}  {nhan}  ({so})",
                           anchor="w", font=ctk.CTkFont(weight="bold"))
        chu.pack(side="left", fill="x", expand=True, padx=(6, 0), pady=2)
        for w in (khung, chu):
            w.bind("<Button-1>", lambda _e, t=ten: self._bat_tat_nhom(t))
            if ten:
                w.bind("<Button-3>", lambda e, t=ten: self._menu_nhom(e, t))

    def _ve_dong(self, cha, job, trong_nhom: bool = False) -> None:
        """Mot trang = mot dong bam duoc + KEO duoc (khong dung CTkButton de tu xu ly keo)."""
        khung = ctk.CTkFrame(cha, fg_color="transparent", height=28)
        khung.pack(fill="x", pady=1)
        khung._job_id = job.job_id
        khung._mau_goc = "transparent"
        chu = ctk.CTkLabel(khung, text=self._label(job), anchor="w",
                           text_color=("gray10", "gray90"))
        chu.pack(side="left", fill="x", expand=True, padx=(18 if trong_nhom else 6, 4), pady=2)
        khung._nhan = chu
        for w in (khung, chu):
            w.bind("<Button-1>", lambda e, j=job.job_id: self._keo_bat_dau(e, j))
            w.bind("<B1-Motion>", self._keo_di)
            w.bind("<ButtonRelease-1>", self._keo_tha)
            w.bind("<Button-3>", lambda e, j=job.job_id: self._menu_job(e, j))
            w.bind("<Control-Button-1>", lambda e, j=job.job_id: self._bam_ctrl(j))
            w.bind("<Shift-Button-1>", lambda e, j=job.job_id: self._bam_shift(j))
        self.buttons[job.job_id] = khung

    # ---- chon nhieu trang -------------------------------------------
    def _thu_tu_hien(self) -> list:
        """job_id theo DUNG thu tu dang hien tren thanh ben (de Shift chon ca doan)."""
        return [ma for ma in self.buttons]

    def _dat_chon(self, ids, mo: str = "") -> None:
        """Dat tap dang chon; ``mo`` = trang se mo bang dieu khien (rong = giu nguyen)."""
        self._chon = {m for m in ids if m in self.buttons}
        if mo:
            self.select(mo)
        self._to_mau()

    def _bam_ctrl(self, job_id: str) -> str:
        """Ctrl+bam: them/bo mot trang khoi tap dang chon."""
        if job_id in self._chon:
            self._chon.discard(job_id)
        else:
            self._chon.add(job_id)
        if job_id not in self._chon and self.current_id == job_id:
            con = next(iter(self._chon), "")
            if con:
                self.select(con)
        elif job_id in self._chon:
            self.select(job_id)
        self._to_mau()
        return "break"

    def _bam_shift(self, job_id: str) -> str:
        """Shift+bam: chon CA DOAN tu trang dang mo toi trang vua bam."""
        ds = self._thu_tu_hien()
        if self.current_id not in ds or job_id not in ds:
            return self._bam_ctrl(job_id)
        i, j = ds.index(self.current_id), ds.index(job_id)
        if i > j:
            i, j = j, i
        self._chon = set(ds[i:j + 1])
        self._to_mau()
        return "break"

    def _to_mau(self) -> None:
        """To lai mau cac dong: trang dang MO dam nhat, cac trang dang CHON xanh nhat."""
        for ma, dong in self.buttons.items():
            if ma == self.current_id:
                mau = ("gray75", "gray28")
            elif ma in self._chon:
                mau = ("#bcd7ee", "#1f4e6e")
            else:
                mau = "transparent"
            dong._mau_goc = mau
            try:
                dong.configure(fg_color=mau)
            except tk.TclError:
                pass
        self._cap_nhat_nut_chon()

    def _cap_nhat_nut_chon(self) -> None:
        """Nut Xoa doi chu theo so trang dang chon."""
        so = len(self._chon)
        try:
            self.xoa_btn.configure(text=f"🗑 Xoá ({so})" if so > 1 else "🗑 Xoá")
        except (AttributeError, tk.TclError):
            pass

    def _dang_chon(self) -> list:
        """Cac trang se chiu tac dong: tap dang chon, khong co thi la trang dang mo."""
        ds = [m for m in self._thu_tu_hien() if m in self._chon]
        if ds:
            return ds
        return [self.current_id] if self.current_id else []

    # ---- keo vung trong de QUET CHON ---------------------------------
    def _quet_bat_dau(self, event) -> None:
        self._quet = {"y": event.y_root, "vien": []}

    def _quet_di(self, event) -> None:
        if not self._quet:
            return
        tren, duoi = sorted((self._quet["y"], event.y_root))
        self._ve_vien(tren, duoi)
        chon = set()
        for ma, dong in self.buttons.items():
            try:
                d_tren = dong.winfo_rooty()
                d_duoi = d_tren + dong.winfo_height()
            except tk.TclError:
                continue
            if d_duoi >= tren and d_tren <= duoi:      # co giao nhau theo chieu doc
                chon.add(ma)
        self._chon = chon
        self._to_mau()

    def _quet_tha(self, _event=None) -> None:
        self._xoa_vien()
        self._quet = None
        if self._chon and self.current_id not in self._chon:
            dau = self._dang_chon()
            if dau:
                self.select(dau[0])          # mo bang dieu khien cua trang dau tap chon
                self._to_mau()

    def _ve_vien(self, tren: int, duoi: int) -> None:
        """Khung vien cua vung dang quet -- bon vach mong (Tk khong co nen trong suot)."""
        if not self._quet:
            return
        if not self._quet["vien"]:
            self._quet["vien"] = [tk.Frame(self.list_frame, bg="#1f6aa5", height=1)
                                  for _ in range(2)]
        goc = self.list_frame.winfo_rooty()
        rong = max(10, self.list_frame.winfo_width())
        for v, y in zip(self._quet["vien"], (tren - goc, duoi - goc)):
            try:
                v.place(x=0, y=max(0, y), width=rong, height=1)
                v.lift()
            except tk.TclError:
                pass

    def _xoa_vien(self) -> None:
        for v in (self._quet or {}).get("vien", []):
            try:
                v.destroy()
            except tk.TclError:
                pass

    def _bat_tat_nhom(self, ten: str) -> None:
        self._nhom_mo[ten] = not self._nhom_mo.get(ten, True)
        self._rebuild(chon=self.current_id)

    # ---- keo tha trang giua cac nhom ----------------------------------
    def _keo_bat_dau(self, event, job_id: str) -> None:
        self._keo_job = job_id
        self._keo_that = False
        self._keo_x, self._keo_y = event.x_root, event.y_root

    def _keo_di(self, event) -> None:
        if not self._keo_job:
            return
        if not self._keo_that:
            # Di qua 6px moi tinh la KEO -- khong thi moi cu bam chon cung thanh keo.
            if abs(event.x_root - self._keo_x) < 6 and abs(event.y_root - self._keo_y) < 6:
                return
            self._keo_that = True
        self._sang_o(self._o_tha_tai(event.x_root, event.y_root))

    def _keo_tha(self, event) -> None:
        job_id, keo = self._keo_job, self._keo_that
        self._keo_job, self._keo_that = "", False
        self._sang_o(None)
        if not job_id:
            return
        if not keo:                                  # bam thuong -> chon MOT trang
            self._chon = {job_id}
            self.select(job_id)
            self._to_mau()
            return
        o = self._o_tha_tai(event.x_root, event.y_root)
        if o is None:
            return
        ten = getattr(o, "_nhom_dich", None)
        if ten is None:
            return
        # Keo mot trang DANG NAM TRONG tap chon -> chuyen ca tap; khong thi chi trang do.
        ds = self._dang_chon() if job_id in self._chon else [job_id]
        so = sum(1 for m in ds if self.manager.dat_nhom(m, ten))
        if not so:
            return
        self._rebuild(chon=job_id)
        cho = f"nhóm '{ten}'." if ten else "mục chưa phân nhóm."
        if so > 1:
            self.app.set_status(f"Đã đưa {so} trang vào {cho}")
        else:
            self.app.set_status(f"Đã đưa '{self.manager.get(job_id).name}' vào {cho}")

    def _o_tha_tai(self, x_root: int, y_root: int):
        """O tha (tieu de nhom) nam duoi con tro, hoac None."""
        try:
            w = self.winfo_containing(x_root, y_root)
        except (tk.TclError, KeyError):
            return None
        while w is not None:
            if hasattr(w, "_nhom_dich"):
                return w
            w = getattr(w, "master", None)
        return None

    def _sang_o(self, o) -> None:
        """To sang o tha dang di qua (va tra mau cho o truoc do)."""
        if o is self._o_sang:
            return
        cu = self._o_sang
        if cu is not None:
            try:
                cu.configure(fg_color=cu._mau_goc)
            except tk.TclError:
                pass
        self._o_sang = o
        if o is not None:
            try:
                o.configure(fg_color="#2f6f8f")
            except tk.TclError:
                pass

    # ---- menu chuot phai ----------------------------------------------
    def _menu_job(self, event, job_id: str) -> None:
        """Chuot phai mot trang: doi nhom / doi tab (duong du phong cua keo tha)."""
        job = self.manager.get(job_id)
        if job is None:
            return
        if job_id not in self._chon:
            self._chon = {job_id}
        self.select(job_id)
        self._to_mau()
        ds = self._dang_chon()
        nhieu = len(ds) > 1
        duoi = f" ({len(ds)} trang)" if nhieu else ""
        menu = tk.Menu(self, tearoff=0)
        nhoms = self.manager.cac_nhom(self.kind, self.tab_id)
        m_nhom = tk.Menu(menu, tearoff=0)
        m_nhom.add_command(label="➕ Nhóm mới...", command=lambda: self.add_nhom(job_id))
        if nhoms:
            m_nhom.add_separator()
        hien = str(getattr(job.config, "nhom", "") or "")
        for ten in nhoms:
            dau = "✓ " if (not nhieu and ten == hien) else "    "
            m_nhom.add_command(label=dau + ten, command=lambda t=ten: self._dat_nhom_nhieu(t))
        if hien or nhieu:
            m_nhom.add_separator()
            m_nhom.add_command(label="✖ Bỏ khỏi nhóm",
                               command=lambda: self._dat_nhom_nhieu(""))
        menu.add_cascade(label="🗂 Chuyển vào nhóm" + duoi, menu=m_nhom)

        cac_tab = self.manager.cac_tab(self.kind)
        if len(cac_tab) > 1:
            m_tab = tk.Menu(menu, tearoff=0)
            for t in cac_tab:
                dau = "✓ " if t["id"] == self.tab_id else "    "
                m_tab.add_command(label=dau + t["ten"],
                                  command=lambda ma=t["id"]: self._dat_tab_nhieu(ma))
            menu.add_cascade(label="📑 Chuyển sang tab" + duoi, menu=m_tab)
        menu.add_separator()
        if not nhieu:
            menu.add_command(label="✏️ Đổi tên", command=self.rename_job)
        menu.add_command(label="🗑 Xoá" + duoi, command=self.remove_job)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _menu_nhom(self, event, ten: str) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="✏️ Đổi tên nhóm", command=lambda: self.rename_nhom(ten))
        menu.add_command(label="🗑 Bỏ nhóm (trang vẫn còn)",
                         command=lambda: self.remove_nhom(ten))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _dat_nhom(self, job_id: str, ten: str) -> None:
        if self.manager.dat_nhom(job_id, ten):
            self._rebuild(chon=job_id)

    def _dat_nhom_nhieu(self, ten: str) -> None:
        """Dua CA TAP dang chon vao mot nhom (ten rong = bo khoi nhom)."""
        ds = self._dang_chon()
        so = sum(1 for m in ds if self.manager.dat_nhom(m, ten))
        if not so:
            return
        self._rebuild(chon=self.current_id)
        cho = f"nhóm '{ten}'." if ten else "mục chưa phân nhóm."
        self.app.set_status(f"Đã đưa {so} trang vào {cho}" if so > 1
                            else f"Đã đưa '{self.manager.get(ds[0]).name}' vào {cho}")

    def _dat_tab(self, job_id: str, tab_id: str) -> None:
        job = self.manager.get(job_id)
        if job is None or not self.manager.dat_tab(job_id, tab_id):
            return
        ten_tab = next((t["ten"] for t in self.manager.cac_tab(self.kind)
                        if t["id"] == tab_id), tab_id)
        self.current_id = ""
        self._rebuild()
        self.app.set_status(f"Đã chuyển '{job.name}' sang tab '{ten_tab}'.")

    def _dat_tab_nhieu(self, tab_id: str) -> None:
        """Chuyen CA TAP dang chon sang tab khac."""
        ds = self._dang_chon()
        if len(ds) <= 1:
            self._dat_tab(ds[0] if ds else "", tab_id)
            return
        so = sum(1 for m in ds if self.manager.dat_tab(m, tab_id))
        ten_tab = next((t["ten"] for t in self.manager.cac_tab(self.kind)
                        if t["id"] == tab_id), tab_id)
        self._chon = set()
        self.current_id = ""
        self._rebuild()
        self.app.set_status(f"Đã chuyển {so} trang sang tab '{ten_tab}'.")

    # ---- tao / sua / bo nhom -------------------------------------------
    def add_nhom(self, job_id: str = "") -> None:
        """Tao nhom moi; co ``job_id`` thi dua luon trang do vao nhom vua tao."""
        ten = SimplePromptDialog(self.app, "Nhóm mới",
                                 "Tên nhóm (gom các trang cho dễ quản lý):", "").show()
        if not ten:
            return
        self.manager.them_nhom(self.kind, self.tab_id, ten)
        if job_id:
            self.manager.dat_nhom(job_id, ten)
        self._rebuild(chon=job_id or self.current_id)
        self.app.set_status(f"Đã tạo nhóm '{ten}'. Kéo trang vào nhóm, hoặc chuột phải trang "
                            "→ Chuyển vào nhóm.")

    def rename_nhom(self, ten: str) -> None:
        moi = SimplePromptDialog(self.app, "Đổi tên nhóm", "Tên mới:", ten).show()
        if not moi or moi == ten:
            return
        self.manager.doi_ten_nhom(self.kind, self.tab_id, ten, moi)
        self._nhom_mo[moi] = self._nhom_mo.pop(ten, True)
        self._rebuild(chon=self.current_id)

    def remove_nhom(self, ten: str) -> None:
        so = len([j for j in self.jobs
                  if str(getattr(j.config, "nhom", "") or "") == ten])
        hoi = f"Bỏ nhóm '{ten}'?"
        if so:
            hoi += chr(10) * 2 + f"{so} trang trong nhóm sẽ về mục “Chưa phân nhóm”, "
            hoi += "KHÔNG bị xoá."
        if not messagebox.askyesno("Bỏ nhóm", hoi, parent=self.app):
            return
        self.manager.xoa_nhom(self.kind, self.tab_id, ten)
        self._nhom_mo.pop(ten, None)
        self._rebuild(chon=self.current_id)
        self.app.set_status(f"Đã bỏ nhóm '{ten}'.")

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
        self._to_mau()

    def current(self):
        return self.manager.get(self.current_id)

    def refresh_labels(self) -> None:
        for job in self.jobs:
            dong = self.buttons.get(job.job_id)
            if dong is not None:
                try:
                    dong._nhan.configure(text=self._label(job))
                except (AttributeError, tk.TclError):
                    pass

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
                          jobs_fn=lambda: self.manager.by_kind(self.kind, self.tab_id),
                          nhan_loai=self._nhan_loai(),
                          on_applied=ap_dung)

    def open_stats(self) -> None:
        """Bảng tổng hợp thống kê các tab cùng loại (fanpage/nhóm)."""
        from ui.stats_dialog import StatsDialog
        nhan = self._nhan_loai()
        StatsDialog(self.app, lambda: self.manager.by_kind(self.kind, self.tab_id),
                    tieu_de=f"Thống kê Auto đăng {nhan}")

    def add_job(self) -> None:
        """Them mot trang: hoi TEN va NHOM can them (co the tao nhom moi ngay tai do)."""
        nhan = self._nhan_loai()
        kq = ThemTrangDialog(self.app, nhan,
                             self.manager.cac_nhom(self.kind, self.tab_id)).show()
        if not kq:
            return
        ten, nhom = kq
        if nhom:
            self.manager.them_nhom(self.kind, self.tab_id, nhom)
        job = self.manager.add(ten, kind=self.kind)
        job.config.tab_id = self.tab_id
        job.config.nhom = nhom
        job.save()
        self._chon = {job.job_id}
        self._rebuild(chon=job.job_id)
        self.app.set_status(f"Đã thêm {nhan} '{job.name}'"
                            + (f" vào nhóm '{nhom}'." if nhom else "."))

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
        """Xoa CAC trang dang chon (keo vung trong / Ctrl / Shift de chon nhieu)."""
        ds = [m for m in self._dang_chon() if self.manager.get(m) is not None]
        if not ds:
            return
        ten = [self.manager.get(m).name for m in ds]
        nhan = self._nhan_loai()
        if len(ds) == 1:
            hoi = f"Xoá {nhan} '{ten[0]}'?"
        else:
            liet = ", ".join(ten[:6]) + (f" và {len(ten) - 6} cái nữa" if len(ten) > 6 else "")
            hoi = f"Xoá {len(ds)} {nhan}?" + chr(10) + liet
        if not messagebox.askyesno(
            "Xoá trang",
            hoi + chr(10) * 2
            + "Cấu hình, lịch và nhật ký của các trang này sẽ mất. "
              "Video trong thư mục vẫn còn nguyên.",
            parent=self.app,
        ):
            return
        for m in ds:
            self.manager.remove(m)
        self._chon = set()
        self.current_id = ""
        self._rebuild()
        self.app.set_status(f"Đã xoá {len(ds)} {nhan}." if len(ds) > 1
                            else f"Đã xoá {nhan} '{ten[0]}'.")



class ThemTrangDialog(BaseDialog):
    """Hoi TEN trang moi + NHOM can them. ``.show()`` tra (ten, nhom) hoac None.

    ``nhom`` rong = chua phan nhom. Chon "➕ Nhóm mới..." thi hien them o go ten nhom.
    """

    CHUA = "— Chưa phân nhóm —"
    MOI = "➕ Nhóm mới..."

    def __init__(self, parent, nhan_loai: str, nhoms):
        super().__init__(parent, f"Thêm {nhan_loai}", 480, 300)
        self.minsize(420, 280)
        self._nhoms = list(nhoms or [])

        ctk.CTkLabel(self, text=f"Tên {nhan_loai}").pack(anchor="w", padx=PAD, pady=(PAD, 2))
        self.entry = ctk.CTkEntry(self, placeholder_text=f"Đặt tên cho {nhan_loai} mới")
        self.entry.pack(fill="x", padx=PAD)
        self.entry.bind("<Return>", lambda _e: self._submit())

        ctk.CTkLabel(self, text="Thêm vào nhóm").pack(anchor="w", padx=PAD, pady=(10, 2))
        self.nhom_menu = ctk.CTkOptionMenu(self, values=[self.CHUA] + self._nhoms + [self.MOI],
                                           command=lambda _v: self._doi_nhom())
        self.nhom_menu.set(self.CHUA)
        self.nhom_menu.pack(fill="x", padx=PAD)
        self.nhom_moi = ctk.CTkEntry(self, placeholder_text="Tên nhóm mới")
        self.nhom_moi.bind("<Return>", lambda _e: self._submit())

        self.loi = ctk.CTkLabel(self, text="", text_color="#e06c6c", anchor="w")
        self.loi.pack(fill="x", padx=PAD, pady=(6, 0))

        nut = ctk.CTkFrame(self, fg_color="transparent")
        nut.pack(fill="x", padx=PAD, pady=PAD, side="bottom")
        ctk.CTkButton(nut, text="Huỷ", width=90, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(nut, text="Thêm", width=100, command=self._submit).pack(side="right", padx=6)
        self.after(200, lambda: self.entry.focus_set())

    def _doi_nhom(self) -> None:
        if self.nhom_menu.get() == self.MOI:
            self.nhom_moi.pack(fill="x", padx=PAD, pady=(4, 0))
            self.nhom_moi.focus_set()
        else:
            self.nhom_moi.pack_forget()

    def _nhom(self) -> str:
        chon = self.nhom_menu.get()
        if chon == self.MOI:
            return self.nhom_moi.get().strip()
        return "" if chon == self.CHUA else chon

    def _submit(self) -> None:
        ten = self.entry.get().strip()
        if not ten:
            self.loi.configure(text="Chưa đặt tên.")
            return
        if self.nhom_menu.get() == self.MOI and not self._nhom():
            self.loi.configure(text="Chưa đặt tên nhóm mới.")
            return
        self.result = (ten, self._nhom())
        self.destroy()


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


#: Bieu tuong dau ten tab theo loai trang.
ICON_LOAI = {"page": "🌐", "lich": "🕒", "group": "👥"}


class ThemTabDialog(BaseDialog):
    """Hoi LOAI tab (Cong khai / Dat lich) + TEN tab. ``.show()`` tra (kind, ten) hoac None."""

    def __init__(self, parent, kinds=("page", "lich")):
        super().__init__(parent, "Thêm tab", 460, 250)
        self.minsize(400, 230)
        self._kinds = [k for k in kinds if k in NHAN_TAB_LOAI] or ["page"]
        ctk.CTkLabel(self, text="Tab mới tạo ra là TRỐNG — bấm “Thêm fanpage” trong tab đó để "
                                "thêm trang, hoặc chuột phải một trang → Chuyển sang tab.",
                     justify="left", text_color="gray60", wraplength=420).pack(
            anchor="w", padx=PAD, pady=(PAD, 8))
        ctk.CTkLabel(self, text="Loại tab").pack(anchor="w", padx=PAD)
        self._kind_box = ctk.CTkSegmentedButton(
            self, values=[NHAN_TAB_LOAI[k] for k in self._kinds])
        self._kind_box.set(NHAN_TAB_LOAI[self._kinds[0]])
        self._kind_box.pack(fill="x", padx=PAD, pady=(2, 10))
        ctk.CTkLabel(self, text="Tên tab").pack(anchor="w", padx=PAD)
        self.entry = ctk.CTkEntry(self, placeholder_text="vd: Kênh phim, Khách hàng A...")
        self.entry.pack(fill="x", padx=PAD, pady=(2, 6))
        self.entry.bind("<Return>", lambda _e: self._submit())
        nut = ctk.CTkFrame(self, fg_color="transparent")
        nut.pack(fill="x", padx=PAD, pady=PAD, side="bottom")
        ctk.CTkButton(nut, text="Huỷ", width=90, fg_color="gray35",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(nut, text="Tạo tab", width=100,
                      command=self._submit).pack(side="right", padx=6)
        self.after(200, lambda: self.entry.focus_set())

    def _submit(self) -> None:
        ten = self.entry.get().strip()
        if not ten:
            self.entry.configure(border_color="#e06c6c")
            return
        nhan = self._kind_box.get()
        kind = next((k for k in self._kinds if NHAN_TAB_LOAI[k] == nhan), self._kinds[0])
        self.result = (kind, ten)
        self.destroy()


#: Tab con (Cong khai / Dat lich / tab nguoi dung them): chu TO + DAM + co VIEN cho de phan biet
#: (nguoi dung yeu cau 02/10/2026 — truoc do cac tab chu nho, khong vien, nhin rat giong nhau).
TAB_CON_CO_CHU = 15
TAB_CON_CAO = 34


def nhan_manh_tab_con(tabview) -> None:
    """To + dam + ve vien cho thanh tab con cua mot CTkTabview.

    Goi SAU khi da add het tab (moi lan dung lai thanh tab phai goi lai)."""
    sb = getattr(tabview, "_segmented_button", None)
    if sb is None:
        return
    chu = ctk.CTkFont(size=TAB_CON_CO_CHU, weight="bold")
    try:
        sb.configure(font=chu, corner_radius=8, border_width=3,
                     fg_color=("gray72", "gray18"),              # khe giua cac tab = duong vien
                     unselected_color=("gray90", "gray26"),
                     unselected_hover_color=("gray84", "gray34"),
                     selected_color=("#2f6fb0", "#2f6fb0"),
                     selected_hover_color=("#3a7cc0", "#3a7cc0"),
                     text_color=("gray10", "gray95"))
    except Exception:  # noqa: BLE001
        pass
    for nut in list(getattr(sb, "_buttons_dict", {}).values()):
        try:
            nut.configure(font=chu, height=TAB_CON_CAO, corner_radius=8,
                          border_width=2, border_color=("gray45", "gray55"))
        except Exception:  # noqa: BLE001
            pass


class AutoUpTabs(ctk.CTkFrame):
    """Khung chua NHIEU tab con: Cong khai + Dat lich, nguoi dung tu them tab.

    Mac dinh dung hai tab (tab mac dinh cua moi loai) y nhu truoc. Them tab -> tab moi
    TRONG, co danh sach trang RIENG (``AutoUpConfig.tab_id``). Xoa tab -> cac trang trong
    do CHUYEN ve tab mac dinh, khong mat cau hinh (nguoi dung chot 01/10).

    Dung LUOI: chi dung ``AutoUpTab`` cua tab nguoi dung thuc su mo. Dung het mot luc thi
    moi tab mot bang dieu khien -> mo tool cham (da do: ca tram bang mat 17 giay).
    """

    def __init__(self, parent, app, *, manager=None, acc_store=None, profiles=None,
                 kinds=("page", "lich")):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.manager = manager or app.autoup
        self.acc_store = acc_store
        self.profiles = profiles
        self.kinds = tuple(kinds)
        self._khung: dict = {}          # ten hien thi -> {"kind","id","frame","tab"}
        self.tabview = None

        thanh = ctk.CTkFrame(self, fg_color="transparent")
        thanh.pack(fill="x", padx=PAD, pady=(4, 0))
        ctk.CTkButton(thanh, text="➕ Thêm tab", width=110, fg_color="#2f7d4f",
                      command=self.them_tab).pack(side="left")
        ctk.CTkButton(thanh, text="✏️ Đổi tên tab", width=120, fg_color="gray45",
                      command=self.doi_ten_tab).pack(side="left", padx=6)
        ctk.CTkButton(thanh, text="🗑 Xoá tab", width=100, fg_color="#a33",
                      command=self.xoa_tab).pack(side="left")
        ctk.CTkLabel(thanh, text="· mỗi tab có danh sách trang riêng; hai tab mặc định "
                                 "không xoá được",
                     text_color="gray60").pack(side="left", padx=10)
        self._than = ctk.CTkFrame(self, fg_color="transparent")
        self._than.pack(fill="both", expand=True)
        self._ve()

    # ---- dung lai thanh tab ------------------------------------------
    def _danh_sach(self) -> list:
        """[(ten hien thi, kind, tab_id)] theo thu tu: moi loai thi tab mac dinh truoc."""
        ra, da_co = [], set()
        for kind in self.kinds:
            for t in self.manager.cac_tab(kind):
                ten = f"{ICON_LOAI.get(kind, '')} {t['ten']}".strip()
                goc, so = ten, 2
                while ten in da_co:          # trung ten -> them so, thanh tab khong cho trung
                    ten = f"{goc} ({so})"
                    so += 1
                da_co.add(ten)
                ra.append((ten, kind, t["id"]))
        return ra

    def _ve(self, chon: str = "") -> None:
        cu = chon or (self.tabview.get() if self.tabview is not None else "")
        for w in self._than.winfo_children():
            w.destroy()
        self._khung = {}
        self.tabview = ctk.CTkTabview(self._than, anchor="w", command=self._doi_tab)
        self.tabview.pack(fill="both", expand=True)
        for ten, kind, tab_id in self._danh_sach():
            self._khung[ten] = {"kind": kind, "id": tab_id,
                                "frame": self.tabview.add(ten), "tab": None}
        nhan_manh_tab_con(self.tabview)      # chu to + dam + vien cho de phan biet tab
        if cu not in self._khung:
            cu = next(iter(self._khung), "")
        if cu:
            self.tabview.set(cu)
            self._dung(cu)

    def _doi_tab(self) -> None:
        """Nguoi dung bam sang tab khac -> dung bang cua tab do (neu chua dung)."""
        try:
            self._dung(self.tabview.get())
        except tk.TclError:
            pass

    def _dung(self, ten: str) -> None:
        o = self._khung.get(ten)
        if o is None or o["tab"] is not None:
            return
        o["tab"] = AutoUpTab(o["frame"], self.app, kind=o["kind"], manager=self.manager,
                             acc_store=self.acc_store, profiles=self.profiles,
                             tab_id=o["id"])
        o["tab"].pack(fill="both", expand=True)

    # ---- tab dang xem -------------------------------------------------
    @property
    def tab_hien(self):
        """``AutoUpTab`` cua tab dang xem (dung roi), hoac None."""
        o = self._khung.get(self.tabview.get() if self.tabview is not None else "")
        return o["tab"] if o else None

    def _o_hien(self) -> dict:
        return self._khung.get(self.tabview.get() if self.tabview is not None else "") or {}

    # ---- them / doi ten / xoa tab -------------------------------------
    def them_tab(self) -> None:
        kq = ThemTabDialog(self.app, self.kinds).show()
        if not kq:
            return
        kind, ten = kq
        tab = self.manager.them_tab(kind, ten)
        self._ve(chon=f"{ICON_LOAI.get(kind, '')} {tab['ten']}".strip())
        self.app.set_status(f"Đã thêm tab '{tab['ten']}' — tab trống, bấm “Thêm fanpage” "
                            "hoặc chuột phải một trang → Chuyển sang tab.")

    def doi_ten_tab(self) -> None:
        o = self._o_hien()
        if not o:
            return
        if not o["id"]:
            messagebox.showinfo("Đổi tên tab", "Hai tab mặc định (Công khai / Đặt lịch) "
                                               "không đổi tên được.", parent=self.app)
            return
        hien = next((t["ten"] for t in self.manager.cac_tab(o["kind"])
                     if t["id"] == o["id"]), "")
        ten = SimplePromptDialog(self.app, "Đổi tên tab", "Tên mới:", hien).show()
        if not ten or ten == hien:
            return
        self.manager.doi_ten_tab(o["id"], ten)
        self._ve(chon=f"{ICON_LOAI.get(o['kind'], '')} {ten}".strip())

    def xoa_tab(self) -> None:
        o = self._o_hien()
        if not o:
            return
        if not o["id"]:
            messagebox.showinfo("Xoá tab", "Hai tab mặc định (Công khai / Đặt lịch) "
                                           "không xoá được.", parent=self.app)
            return
        ten = next((t["ten"] for t in self.manager.cac_tab(o["kind"])
                    if t["id"] == o["id"]), "")
        so = len(self.manager.by_kind(o["kind"], o["id"]))
        hoi = f"Xoá tab '{ten}'?"
        if so:
            mac = NHAN_TAB_LOAI.get(o["kind"], "mặc định")
            hoi += (chr(10) * 2 + f"{so} trang trong tab này sẽ CHUYỂN về tab '{mac}', "
                    "giữ nguyên cấu hình, lịch và nhật ký.")
        if not messagebox.askyesno("Xoá tab", hoi, parent=self.app):
            return
        chuyen = self.manager.xoa_tab(o["id"])
        self._ve()
        self.app.set_status(f"Đã xoá tab '{ten}'." +
                            (f" Chuyển {chuyen} trang về tab mặc định." if chuyen > 0 else ""))
