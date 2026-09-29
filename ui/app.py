"""Cua so chinh cua tool quan ly profile Firefox Portable."""

from __future__ import annotations

import inspect
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

import customtkinter as ctk

from core import config
from core import cookies as cookie_module
from core import licensing
from core import proxy as proxy_module
from core import autostart
from core import autoup as autoup_module
from core import fbbusiness
from core import fblocale
from core import fbpage
from core import fbupload
from core import store as store_module
from core import totp
from core.config import Settings
from core.profiles import ProfileError, ProfileManager
from core.proxy import Proxy
from core.proxy_relay import RelayManager, test_proxy
from core.store import Account, AccountStore, STATUSES

from . import login
from .autoup_tab import AutoUpTab
from .dialogs import (
    AccountDialog,
    ColumnDialog,
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

#: Nhan hai che do giao dien tren thanh tieu de.
SANG = "☀ Sáng"
TOI = "🌙 Tối"
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
    ("pro", "Chuyên nghiệp", 105, "center"),
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
        # Nap REGISTRY MO-DUN (ADR-028): moi chuc nang la 1 mo-dun trong core/modun,
        # tool goi theo ma qua App.goi_modun. Them mo-dun = them 1 file, khong sua App.
        try:
            from core.modun import tat_ca as _modun_tat_ca
            _modun_tat_ca.nap()
        except Exception as exc:  # noqa: BLE001 - registry hong khong duoc lam tool khong mo
            print("nap mo-dun loi:", exc)

        self._events: queue.Queue = queue.Queue()
        # Khoa theo TUNG ACC (khong con _busy toan tool): tac vu tren acc khac nhau
        # chay song song, chi chan khi trung acc dang ban. _busy_accs = id acc dang
        # co tac vu chay; _task_count = so tac vu dang chay (de an/hien thanh tien trinh).
        self._busy_accs: set = set()
        self._busy_lock = threading.Lock()
        self._task_count = 0
        self._show_secrets = tk.BooleanVar(value=True)
        self._rows: list[Account] = []
        self._menus: list[tk.Menu] = []

        # Bo canh gio tu dang video. Tao TRUOC khi dung tab vi tab doc no ra.
        self.autoup = autoup_module.AutoUpManager(
            os.path.dirname(self.store.path), log=lambda m: self._post(
                lambda: self.set_status(m[:160])))
        self._wire_uploader()

        # Auto dang X: manager RIENG (data/x_autoup) -> job X khong tron voi job Facebook.
        # platform="x": job nhan ca anh/bai chu (effective_kind "auto"), khong lay ten
        # file lam noi dung, va JobPanel hien hang "Dang len" kieu X.
        self.autoup_x = autoup_module.AutoUpManager(
            os.path.join(os.path.dirname(self.store.path), "x_autoup"),
            log=lambda m: self._post(lambda: self.set_status(m[:160])),
            platform="x")
        self._wire_uploader_x()

        # Don muc "Firefox tu khoi dong cung Windows" do cac profile tu ghi vao.
        # Khong hoi han gi: de nguyen thi bat may len la ca chuc cua so tu mo.
        self._clean_autostart(quiet=True)

        self._build_header()
        # Thanh tieu de va thanh trang thai nam ngoai tab (chung cho ca hai tab).
        self._build_statusbar()

        self.tabs = ctk.CTkTabview(self, anchor="w")
        self.tabs.pack(fill="both", expand=True, padx=PAD, pady=(0, 4))
        tab_acc = self.tabs.add("📋 Quản lý acc")
        tab_page = self.tabs.add("🎬 Auto đăng fanpage")
        tab_group = self.tabs.add("👥 Auto đăng nhóm")
        tab_x_dang = self.tabs.add("🐦 Auto đăng X")
        # Lan 4 (ADR-009): tab "Quet bai nhom" cu bo; tab Thu nghiem AI doi ten thanh
        # "Quet bai" -- quet -> gui vao Auto dang nhom -> xao o do -> dang theo lich.
        tab_ailab = self.tabs.add("🔎 Quét bài")
        tab_chat = self.tabs.add("💬 Nhắn tin AI")
        tab_create = self.tabs.add("🏗 Tạo fanpage")
        tab_tuongtac = self.tabs.add("🤝 Tương tác")
        tab_rename = self.tabs.add("✏️ Đổi tên file")
        tab_xoabai = self.tabs.add("🗑 Xoá bài viết")

        # "Quan ly acc" co HAI TAB CON: Facebook (bang acc nhu cu) va X.com (danh
        # sach acc + thu muc profile RIENG, khong tron voi acc Facebook).
        from .x_acc_tab import XAccTab, X_TAB_TITLE
        self.acc_tabs = ctk.CTkTabview(tab_acc, anchor="w")
        self.acc_tabs.pack(fill="both", expand=True)
        tab_fb = self.acc_tabs.add("📘 Facebook")
        tab_x = self.acc_tabs.add(X_TAB_TITLE)
        self._build_toolbar(tab_fb)
        self._build_table(tab_fb)
        self._build_detail()
        self.x_acc_tab = XAccTab(tab_x, self)
        self.x_acc_tab.pack(fill="both", expand=True)
        self.acc_tabs.set("📘 Facebook")
        # "Auto dang fanpage" co HAI TAB CON: Cong khai (dang ngay) va Dat lich
        # (hen gio). Cung la AutoUpTab, chi khac loai trang -> danh sach trang
        # RIENG cho tung tab con, khong tron vao nhau.
        self.fanpage_tabs = ctk.CTkTabview(tab_page, anchor="w")
        self.fanpage_tabs.pack(fill="both", expand=True)
        tab_congkhai = self.fanpage_tabs.add("🌐 Công khai")
        tab_datlich = self.fanpage_tabs.add("🕒 Đặt lịch")
        self.autoup_tab = AutoUpTab(tab_congkhai, self, kind="page")
        self.autoup_tab.pack(fill="both", expand=True)
        self.thu_lich_tab = AutoUpTab(tab_datlich, self, kind="lich")
        self.thu_lich_tab.pack(fill="both", expand=True)
        self.fanpage_tabs.set("🌐 Công khai")
        self.group_tab = AutoUpTab(tab_group, self, kind="group")
        self.group_tab.pack(fill="both", expand=True)
        # "Auto dang X" giong het "Auto dang fanpage": 2 tab con Cong khai + Dat lich.
        # Dung manager RIENG self.autoup_x -> job X khong tron voi job Facebook.
        self.x_fanpage_tabs = ctk.CTkTabview(tab_x_dang, anchor="w")
        self.x_fanpage_tabs.pack(fill="both", expand=True)
        x_congkhai = self.x_fanpage_tabs.add("🌐 Công khai")
        x_datlich = self.x_fanpage_tabs.add("🕒 Đặt lịch")
        # Chon acc tu tab Quan ly acc X (store + profile RIENG cua X, khong dinh acc FB).
        self.x_autoup_tab = AutoUpTab(x_congkhai, self, kind="page", manager=self.autoup_x,
                                      acc_store=self.x_acc_tab.store,
                                      profiles=self.x_acc_tab.manager)
        self.x_autoup_tab.pack(fill="both", expand=True)
        self.x_lich_tab = AutoUpTab(x_datlich, self, kind="lich", manager=self.autoup_x,
                                    acc_store=self.x_acc_tab.store,
                                    profiles=self.x_acc_tab.manager)
        self.x_lich_tab.pack(fill="both", expand=True)
        self.x_fanpage_tabs.set("🌐 Công khai")
        from .ai_lab_tab import AiLabTab
        self.ai_lab_tab = AiLabTab(tab_ailab, self)
        self.ai_lab_tab.pack(fill="both", expand=True)
        from .chat_tab import ChatTab
        self.chat_tab = ChatTab(tab_chat, self)
        self.chat_tab.pack(fill="both", expand=True)
        from .create_page_tab import CreatePageTab
        self.create_page_tab = CreatePageTab(tab_create, self)
        self.create_page_tab.pack(fill="both", expand=True)
        from .tuong_tac_tab import TuongTacTab
        self.tuong_tac_tab = TuongTacTab(tab_tuongtac, self)
        self.tuong_tac_tab.pack(fill="both", expand=True)
        from .rename_tab import RenameTab
        self.rename_tab = RenameTab(tab_rename, self)
        self.rename_tab.pack(fill="both", expand=True)
        from .xoa_bai_tab import XoaBaiTab
        self.xoa_bai_tab = XoaBaiTab(tab_xoabai, self)
        self.xoa_bai_tab.pack(fill="both", expand=True)
        self.autoup.start()
        self.autoup_x.start()
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

    def _clean_autostart(self, quiet: bool = False) -> None:
        """Xoa muc "Firefox tu khoi dong cung Windows" ma cac profile tu ghi vao.

        Firefox 154 tu ghi mot muc vao registry Run cho MOI profile no chay lan
        dau. Tool tao 20 acc la 20 muc -> bat may len 20 cua so Firefox cung mo.
        Da chan bang lockPref trong mozilla.cfg cho profile moi; ham nay don
        nhung cai da bi ghi tu truoc. Chay moi lan mo tool, khong hoi gi.
        """
        try:
            da_xoa = autostart.clean(self.settings.profiles_root)
        except Exception:
            return                      # registry hong thi thoi, khong chan tool
        if quiet:
            if da_xoa:
                self._post(lambda: self.set_status(
                    f"Đã bỏ {len(da_xoa)} mục Firefox tự khởi động cùng Windows."))
            return

        khac = autostart.others(self.settings.profiles_root)
        phan = [f"Đã bỏ {len(da_xoa)} mục tự khởi động của các profile trong tool."]
        if khac:
            ten = chr(10).join("  " + e.path for e in khac[:10])
            phan.append("Còn những mục này KHÔNG phải của tool nên tôi không đụng vào:"
                        + chr(10) + ten)
            phan.append("Muốn bỏ thì xoá tay trong Task Manager > Startup apps.")
        messagebox.showinfo("Dọn tự khởi động",
                            (chr(10) * 2).join(phan), parent=self)

    def _wire_uploader(self) -> None:
        """Cai cach dang cho TUNG cong viec: Graph API, hoac qua trinh duyet."""

        def factory(job):
            def dang(path: str, caption: str) -> str:
                cfg = job.config
                # Acc dang LUOT NAY -- co the la acc2 khi dang luan phien.
                acc_id = job.pick_account()
                # Gan MAU TUONG TAC -> xem reel + like TRUOC khi dang (khong dung delay cua tab).
                mau = getattr(cfg, "tuong_tac_mau", None)
                if mau and acc_id:
                    acc_tt = self.store.get(acc_id)
                    if acc_tt is not None:
                        from core import tuong_tac_mau as _ttm
                        try:
                            _ttm.chay_truoc(self.manager, acc_tt, mau,
                                            log=lambda m: self.set_status(m))
                        except Exception as exc:  # noqa: BLE001
                            self.set_status(f"Tương tác trước khi đăng lỗi (bỏ qua): {exc}")
                if cfg.is_group:
                    return self._upload_to_group(cfg, path, caption, acc_id)
                if not cfg.page_id:
                    raise fbupload.UploadError("Chưa nhập ID fanpage.")
                if cfg.is_lich:
                    # Trang ĐẶT LỊCH: không đăng ngay — hẹn bài vào giờ của khung.
                    hen = job.lich_gio_hen()
                    if not hen:
                        raise fbupload.UploadError(
                            "Trang đặt lịch nhưng không đọc được giờ hẹn của khung.")
                    return self._upload_via_browser(cfg, path, caption, acc_id, lich=hen)
                if cfg.method == "browser":
                    return self._upload_via_browser(cfg, path, caption, acc_id)
                return fbupload.upload_video(cfg.page_id, cfg.token, path,
                                             description=caption)
            return dang

        self.autoup.set_uploader_factory(factory)

        def kham(job):
            """Kham sang: mo composer cua trang nay xem giao dien con quen khong."""
            cfg = job.config
            acc_id = job.pick_account()
            acc = self.store.get(acc_id) if acc_id else None
            if acc is None:
                return False, "chưa chọn acc"
            if not self.manager.is_installed(acc):
                return False, f"acc {acc.id} chưa có profile"
            asset = self._resolve_page(cfg, acc)
            return fbbusiness.health_check(self.manager, acc, asset)

        self.autoup.canary = kham

    def _wire_uploader_x(self) -> None:
        """Cach dang cho job X: mo Firefox profile X cua acc, agent xpost dien
        composer x.com/home roi bam Dang (core/xpost.py).

        Acc lay tu tab Quan ly acc X. Ham nay chay LUC KHOI TAO, truoc khi
        x_acc_tab ton tai -> phai voi toi x_acc_tab LUOI, ben trong dang().
        """
        def factory(job):
            def dang(path: str, caption: str) -> str:
                tab = getattr(self, "x_acc_tab", None)
                if tab is None:
                    raise fbupload.UploadError("Tab Quản lý acc X chưa sẵn sàng.")
                if job.config.is_lich:
                    raise fbupload.UploadError(
                        "Tab Đặt lịch X chưa hỗ trợ — X không có Business Suite. "
                        "Dùng tab Công khai: mốc giờ / giãn cách phút chính là lịch đăng.")
                acc_id = job.pick_account()
                if not acc_id:
                    raise fbupload.UploadError("Chưa chọn acc X cho trang này.")
                acc = tab.store.get(acc_id)
                if acc is None:
                    raise fbupload.UploadError(
                        f"Acc X {acc_id} không còn trong bảng Quản lý acc X.")
                from core import xpost
                return xpost.upload(tab.manager, acc, path, caption,
                                    log=lambda m: self.set_status(m[:160]))
            return dang
        self.autoup_x.set_uploader_factory(factory)

    def _upload_to_group(self, cfg, path: str, caption: str,
                         account_id: str = "") -> str:
        """Dang video vao mot nhom Facebook bang acc da chon."""
        if not cfg.group_id:
            raise fbupload.UploadError("Chưa dán link nhóm.")
        acc_id = account_id or cfg.account_id
        acc = self.store.get(acc_id) if acc_id else None
        if acc is None:
            raise fbupload.UploadError("Chưa chọn acc đăng.")
        if not self.manager.is_installed(acc):
            raise fbupload.UploadError(f"Acc {acc.id} chưa có profile.")

        # Giao dien tieng la thi cac buoc khong con giong nhung gi da do.
        fblocale.ensure_supported(acc, self.manager.profile_dir(acc))
        self.store.save()
        # GOP nhieu media 1 bai + uu tien BAN XAO (anh da xao thay anh goc):
        # _gather_medias tra [file_chinh, ...]; [0] moi la file chinh thuc su (co
        # the la anh da xao, khong phai ``path`` goc).
        medias = self._gather_medias(path)
        primary = medias[0] if medias else path
        from core import reauth

        def _dang_nhom():
            # Acc bị logout khi đăng nhóm -> tự đăng nhập lại (cookie -> web) rồi đăng lại.
            return reauth.chay_lai_neu_logout(
                self.manager, acc,
                lambda: fbbusiness.upload_group(
                    self.manager, acc, cfg.group_id, primary, caption=caption,
                    kind=fbupload.kind_of(primary),   # tu nhan dien: video / anh / chu
                    publish=True, log=lambda m: None,
                    medias=medias if len(medias) > 1 else None),
                store=self.store, settings=self.settings,
                log=lambda m: self.set_status(f"{acc.id}: {m}"))

        try:
            # Giao dien dang o thu tieng la -> doi sang tieng Anh roi dang lai.
            return fblocale.chay_lai_neu_la_ngon_ngu(
                self.manager, acc, _dang_nhom,
                log=lambda m: self.set_status(f"{acc.id}: {m}"))
        except fbbusiness.BusinessError as exc:
            raise fbupload.UploadError(str(exc)) from exc

    @staticmethod
    def _gather_medias(path: str) -> list:
        """Danh sach media cua mot bai. [0] = file CHINH (video_path), [] = 1 file thuong.

        Uu tien BAN XAO: neu co '<base>_xao/' (AI) thi dung ANH DA XAO (video giu
        nguyen). Khong thi dung '<base>_media/' (album/anh kem video goc).
        """
        from core import fbupload
        base = os.path.splitext(path)[0]

        def files_in(folder, skip=()):
            out = []
            try:
                for name in sorted(os.listdir(folder)):
                    if name in skip:
                        continue
                    fp = os.path.join(folder, name)
                    if os.path.isfile(fp):
                        out.append(fp)
            except OSError:
                pass
            return out

        xao = base + "_xao"
        if os.path.isdir(xao):
            imgs = [f for f in files_in(xao, skip=("caption.txt",))
                    if not fbupload.is_text(f)]
            if fbupload.kind_of(path) == "video":
                return [path, *imgs] if imgs else []      # video goc + anh da xao
            return imgs if imgs else []                   # anh da xao thay anh goc

        sub = base + "_media"
        if os.path.isdir(sub):
            extras = files_in(sub)
            return [path, *extras] if extras else []
        return []

    def _upload_via_browser(self, cfg, path: str, caption: str,
                            account_id: str = "", lich=None) -> str:
        """Dang qua business.facebook.com bang chinh acc da chon.

        ``lich`` khac None -> KHONG dang ngay ma bat "Đặt lịch" + hen dung gio.
        """
        acc_id = account_id or cfg.account_id
        acc = self.store.get(acc_id) if acc_id else None
        if acc is None:
            raise fbupload.UploadError(
                "Chưa chọn acc — cách đăng qua Business Suite cần phiên đăng nhập.")
        if not self.manager.is_installed(acc):
            raise fbupload.UploadError(f"Acc {acc.id} chưa có profile.")

        # Cookie `locale` KHONG quyet dinh ngon ngu (da do that: cookie vi_VN ma
        # giao dien la es/he) -> chi sua cookie cho dong bo, con ngon ngu THAT do
        # agent kiem ngay tren trang va bao "NGÔN NGỮ LẠ" de doi qua giao dien.
        ma, da_doi = fblocale.ensure_supported(acc, self.manager.profile_dir(acc))
        if da_doi:
            self.store.save()
            self._post(self.refresh)

        asset = self._resolve_page(cfg, acc)
        from core import reauth

        def _dang():
            # Acc bị logout khi đăng fanpage -> tự đăng nhập lại (cookie -> web) rồi đăng lại.
            return reauth.chay_lai_neu_logout(
                self.manager, acc,
                lambda: fbbusiness.upload(
                    self.manager, acc, asset, path, caption=caption,
                    publish=True, log=lambda m: None, lich=lich),
                store=self.store, settings=self.settings,
                log=lambda m: self.set_status(f"{acc.id}: {m}"))

        try:
            # Giao dien dang o thu tieng la -> doi sang tieng Anh roi dang lai.
            return fblocale.chay_lai_neu_la_ngon_ngu(
                self.manager, acc, _dang,
                log=lambda m: self.set_status(f"{acc.id}: {m}"))
        except fbbusiness.BusinessError as exc:
            raise fbupload.UploadError(str(exc)) from exc

    def _resolve_page(self, cfg, acc) -> str:
        """ID fanpage ma Business Suite dung, quy doi neu can roi nho lai.

        Phai lam o DAY chu khong chi o hai nut "Nhan dien" va "Mo Business": mot
        fanpage co hai so khac nhau, dan so cong khai vao thi Business Suite chi
        hien trang "Sorry, this content isn't available right now". Da gap dung
        loi do khi bam "Dang thu 1 video" voi so chua quy doi.

        Quy doi xong thi ghi lai vao cau hinh, cac lan dang sau khoi hoi lai.
        """
        if cfg.asset_id:
            return cfg.asset_id             # da quy doi tu truoc
        asset, ten, loi = fbpage.resolve_asset_id(cfg.page_id, acc.cookie)
        if not asset:
            raise fbupload.UploadError(loi or "Không nhận diện được fanpage.")
        cfg.asset_id, cfg.page_name = asset, ten
        for job in self.autoup.jobs:
            if job.config is cfg:
                job.save()
        return asset

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
        # Doi sang/toi ngay tren thanh tieu de, khong phai vao Cai dat.
        self.theme_box = ctk.CTkSegmentedButton(
            header, values=[SANG, TOI], width=150, command=self._pick_theme)
        self.theme_box.set(TOI if self.settings.appearance == "dark" else SANG)
        self.theme_box.pack(side="right", padx=(0, 6))
        ctk.CTkButton(
            header, text="Đăng xuất", width=90, fg_color="gray50",
            hover_color="gray40", command=self.sign_out,
        ).pack(side="right", padx=(0, 4))

        self.account_label = ctk.CTkLabel(header, text="", text_color="gray60")
        self.account_label.pack(side="right", padx=8)
        self._update_account_label()

    def _pick_theme(self, value: str) -> None:
        """Doi giao dien sang/toi va nho lai cho lan mo sau."""
        self.settings.appearance = "dark" if value == TOI else "light"
        self.settings.save()
        self._apply_theme()

    def _update_account_label(self) -> None:
        """Ghi ten dang nhap va han key len header (doi lai sau khi dang nhap lai)."""
        info = licensing.summarize(self.session)
        self.account_label.configure(
            text=f"👤 {info['username']}   •   Hạn key: {info['expiry']}")

    def _build_toolbar(self, parent) -> None:
        filters = ctk.CTkFrame(parent, fg_color="transparent")
        filters.pack(fill="x", padx=PAD, pady=(PAD, 4))

        self.search_entry = ctk.CTkEntry(
            filters, width=400,
            placeholder_text="Tìm ID / mail / nhóm / ghi chú — dán nhiều UID cũng được",
        )
        self.search_entry.pack(side="left")
        self.search_entry.bind("<KeyRelease>", lambda _e: self.refresh())
        # Dan mot cot UID tu Excel se keo theo ky tu xuong dong; o mot dong khong
        # hien duoc chung. Doi thanh dau phay cho nhin ra danh sach.
        self.search_entry.bind("<<Paste>>", self._paste_search)

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

        # Bỏ các nút Sửa / Tạo profile / Nhóm / Xoá / Mở / Check / Bài viết nhóm khỏi thanh công cụ
        # (yêu cầu người dùng 2026-09-17) — các chức năng này vẫn dùng được qua menu CHUỘT PHẢI.
        button("➕ Thêm acc", self.add_account)
        button("📥 Nhập hàng loạt", self.bulk_import, width=140)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        button("⏹ Đóng", self.close_profiles, color="#7a5", width=90)
        button("🔄 Quét thư mục", self.scan_existing, width=130)

        # MOT o "Luong" dung chung cho: dang nhap cookie, tao profile, bat chuyen nghiep, dang nhap web.
        self.login_threads_label = ctk.CTkLabel(actions, text="Luồng", font=bold)
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
            # stretch=False cho MOI cot: cot nao co stretch se bi bop lai khi bang
            # hep di -- bam vao mot dong la bang thong tin ben phai chiem cho va
            # cot do teo mat. Khong co cot nao gian thi be ngang cot giu nguyen,
            # thieu cho thi da co thanh cuon ngang.
            self.tree.column(key, width=width, anchor=anchor, stretch=False)

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
        self._menu.add_command(label="🌐 Đăng nhập web (id|pass|2fa)", command=self.login_web_selected)
        # "Nhap / sua cookie" da nam trong menu con "Sua" -> bo o day cho do trung.
        self._menu.add_command(label="⏹ Đóng profile", command=self.close_profiles)
        self._menu.add_command(label="🧩 Tạo profile", command=self.create_profiles)
        self._menu.add_command(label="💼 Bật chế độ chuyên nghiệp",
                               command=self.enable_professional_selected)
        # Doi User Agent: mot muc con moi category (iOS/Android/TV/Mac/Win...)
        from core import useragent as _ua
        ua_menu = self._make_menu(self._menu)
        _loai = list(_ua.cac_loai().keys())
        if _loai:
            for _ten in _loai:
                ua_menu.add_command(label=_ten,
                                    command=lambda l=_ten: self.change_user_agent(l))
            ua_menu.add_separator()
        ua_menu.add_command(label="Xoá User Agent (dùng mặc định)",
                            command=lambda: self.change_user_agent(""))
        self._menu.add_cascade(label="🕶 Đổi user agent", menu=ua_menu)
        self._menu.add_separator()

        # Danh sach nhom doi theo thoi gian nen dung lai moi lan bung menu.
        self._group_menu = self._make_menu(self._menu)
        self._menu.add_cascade(label="🗂 Chuyển vào nhóm", menu=self._group_menu)
        # "Quan ly nhom" (doi ten / xoa nhom) truoc day o nut thanh cong cu; nut da bo -> dua vao day.
        self._menu.add_command(label="🗂 Quản lý nhóm...", command=self.manage_groups)
        # Gom moi thu "sua" vao mot menu con: truoc day chi co moi "Sua ghi chu"
        # nam le o day, con cac truong khac phai mo bang chi tiet ben phai.
        edit_menu = self._make_menu(self._menu)
        edit_menu.add_command(label="Sửa tất cả...", command=self.edit_account)
        edit_menu.add_command(label="Sửa custom (hàng loạt)...", command=self.bulk_update)
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
        pro_menu = self._make_menu(edit_menu)
        pro_menu.add_command(label="Đánh dấu ĐÃ bật",
                             command=lambda: self.set_pro_mode(store_module.PRO_BAT))
        pro_menu.add_command(label="Đánh dấu CHƯA bật",
                             command=lambda: self.set_pro_mode(store_module.PRO_CHUA))
        edit_menu.add_cascade(label="Chuyên nghiệp (cột)", menu=pro_menu)
        edit_menu.add_command(label="Sửa ghi chú...", command=self.edit_note)
        edit_menu.add_separator()
        lang_menu = self._make_menu(edit_menu)
        for ma, ten in fblocale.LANGUAGES.items():
            lang_menu.add_command(label=ten,
                                  command=lambda m=ma: self.set_fb_language(m))
        edit_menu.add_cascade(label="Ngôn ngữ Facebook", menu=lang_menu)
        edit_menu.add_separator()
        edit_menu.add_command(label="Xoá cookie đã lưu", command=self.clear_cookie_field)
        self._menu.add_cascade(label="✏️ Sửa", menu=edit_menu)
        self._menu.add_separator()

        # 🧩 MO-DUN: menu SINH TU REGISTRY (ADR-028) — cascade theo nhom, moi muc = 1 mo-dun.
        # Them mo-dun moi vao core/modun la tu hien o day, khong sua App.
        self._menu.add_cascade(label="🧩 Mô-đun", menu=self._menu_modun(self._menu))
        self._menu.add_separator()

        self._menu.add_command(label="🌐 Đổi proxy...", command=self.change_proxy)
        check_menu = self._make_menu(self._menu)
        check_menu.add_command(label="Check proxy", command=self.check_proxies)
        check_menu.add_command(label="Check cookie", command=self.check_cookies)
        check_menu.add_command(label="Check tường (live/die)", command=self.check_walls)
        self._menu.add_cascade(label="🔍 Check", menu=check_menu)
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
        self._menu.add_command(label="🚫 Dọn Firefox tự khởi động cùng Windows",
                               command=lambda: self._clean_autostart(quiet=False))
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
        bar = ctk.CTkFrame(self, height=34, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        # Nut tat het trinh duyet: de o goc duoi ben trai, luon nhin thay o ca
        # hai tab (thanh trang thai nam ngoai tab).
        # Goc duoi ben trai: cong tac "Mo cung Windows" (mac dinh BAT) — qua mo-dun mo_cung_windows.
        self.mo_cung_win_var = tk.BooleanVar(value=bool(getattr(self.settings, "mo_cung_windows", True)))
        self.mo_cung_win_switch = ctk.CTkSwitch(
            bar, text="🚀 Mở cùng Windows", variable=self.mo_cung_win_var,
            command=self._doi_mo_cung_windows, width=150)
        self.mo_cung_win_switch.pack(side="left", padx=(10, 8), pady=3)
        self.kill_button = ctk.CTkButton(
            bar, text="🛑 Tắt hết Firefox", width=150, fg_color="#a33",
            hover_color="#c44", font=ctk.CTkFont(weight="bold"),
            command=self.kill_all_browsers,
        )
        self.kill_button.pack(side="left", padx=(0, 6), pady=3)
        # Ap trang thai da luu ngay luc mo (lan dau = mac dinh bat -> dang ky khoi dong).
        self.after(300, self._ap_mo_cung_windows)
        self.status_label = ctk.CTkLabel(bar, text="Sẵn sàng.", anchor="w")
        self.status_label.pack(side="left", padx=6, pady=4)
        self.progress = ctk.CTkProgressBar(bar, width=180, mode="indeterminate")

        # GIUA thanh duoi: nut hen gio tat may (dung place de canh giua bat ke widget hai ben).
        self._shutdown_at = None        # datetime se tat (None = chua hen)
        self.shutdown_button = ctk.CTkButton(
            bar, text="⏻ Hẹn giờ tắt máy", width=170, fg_color="#7a5",
            hover_color="#8b6", font=ctk.CTkFont(weight="bold"),
            command=self.open_shutdown_dialog)
        self.shutdown_button.place(relx=0.5, rely=0.5, anchor="center")
        self._tick_shutdown()

    def _ap_mo_cung_windows(self) -> None:
        """Dong bo khoa Run cua Windows voi cai dat (goi luc mo tool, khong hoi)."""
        from core import modun as modun_module
        bat = bool(self.mo_cung_win_var.get())
        try:
            kq = modun_module.chay("mo_cung_windows", modun_module.ngu_canh_tu(self), [], bat=bat)
            if kq.loi:
                self.set_status(f"Mở cùng Windows: {kq.loi[0][1]}")
        except Exception as exc:  # noqa: BLE001
            self.set_status(f"Mở cùng Windows: lỗi {exc}")

    def _doi_mo_cung_windows(self) -> None:
        """Nguoi dung gat cong tac goc duoi trai."""
        from core import modun as modun_module
        bat = bool(self.mo_cung_win_var.get())
        kq = modun_module.chay("mo_cung_windows", modun_module.ngu_canh_tu(self), [], bat=bat)
        if kq.loi:
            self.mo_cung_win_var.set(not bat)          # khong ghi duoc -> tra cong tac ve cu
            messagebox.showwarning("Mở cùng Windows", kq.loi[0][1], parent=self)
            return
        self.set_status("🚀 " + kq.ghi_chu)

    # ------------------------------------------------------------------ hen tat may
    def open_shutdown_dialog(self) -> None:
        """Mo hop 'Hen gio tat may' (nut o GIUA thanh duoi)."""
        from ui.shutdown_dialog import ShutdownDialog
        dang = self._shutdown_at.strftime("%H:%M") if self._shutdown_at else None
        ShutdownDialog(self, dang_hen=dang, on_changed=self._shutdown_changed)

    def _shutdown_changed(self, giay) -> None:
        """Dialog bao vua dat (giay > 0) hoac vua huy (None) -> nho gio + doi nut."""
        if giay:
            from datetime import datetime, timedelta
            self._shutdown_at = datetime.now() + timedelta(seconds=int(giay))
        else:
            self._shutdown_at = None
        self._tick_shutdown()

    def _tick_shutdown(self) -> None:
        """Moi 20s: cap nhat chu tren nut theo lich con lai (het gio thi ve mac dinh)."""
        btn = getattr(self, "shutdown_button", None)
        if btn is not None:
            from datetime import datetime
            at = self._shutdown_at
            if at and at > datetime.now():
                con = int((at - datetime.now()).total_seconds()) // 60
                btn.configure(text=f"⏻ Tắt máy {at.strftime('%H:%M')} (còn {con}′)",
                              fg_color="#a33", hover_color="#c44")
            else:
                self._shutdown_at = None
                btn.configure(text="⏻ Hẹn giờ tắt máy", fg_color="#7a5", hover_color="#8b6")
        self.after(20000, self._tick_shutdown)

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

        self.count_label.configure(text=self._count_text())

    def _paste_search(self, _event=None) -> str:
        """Dan vao o tim kiem: gop nhieu dong thanh mot danh sach ngan bang dau phay."""
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return "break"
        parts = [p.strip() for p in re.split(r"[\r\n\t;,]+", text) if p.strip()]
        gop = ", ".join(parts)
        try:
            if self.search_entry.select_present():
                self.search_entry.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.search_entry.insert("insert", gop)
        self.refresh()
        return "break"          # chan Tk dan them lan nua

    def _count_text(self) -> str:
        """Chu o goc phai: bao nhieu acc dang hien, va UID nao dan vao ma khong co."""
        base = f"{len(self._rows)}/{len(self.store)} acc"
        terms = store_module.split_terms(self.search_entry.get())
        if len(terms) < 2:
            return base
        thay = set()
        for account in self._rows:
            kho = " ".join([account.id, account.recovery_mail, account.group,
                            account.note, account.get_proxy().as_text()]).lower()
            thay.update(t for t in terms if t in kho)
        thieu = len(terms) - len(thay)
        return f"{base} · tìm {len(terms)} từ khoá" + (f", {thieu} không thấy" if thieu else "")

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
            "pro": store_module.nhan_pro(account),
            "profile": "đã tạo" if installed else "chưa tạo",
            "running": "▶" if installed and self.manager.is_running(account) else "",
            "note": (account.note or "").replace(chr(10), " ")[:120],
        }
        return tuple(cells[key] for key, *_ in COLUMNS)

    @staticmethod
    def _status_cell(account: Account) -> str:
        """Cot "Trạng thái": uu tien trang thai acc FB (check cookie/tuong), roi
        den ket qua test proxy, cuoi cung la trang thai nhap tay."""
        if account.status and account.status != "Chưa rõ":
            return account.status
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

    def _so_luong(self) -> int:
        """So luong DUNG CHUNG (o "Luong" tren bang): dang nhap cookie, tao profile,
        bat chuyen nghiep, dang nhap web. Nguon duy nhat, kep 1..8 (ADR-015)."""
        try:
            return max(1, min(8, int(self.settings.login_threads or 5)))
        except (TypeError, ValueError):
            return 5

    def _set_login_threads(self, value: str) -> None:
        """Doi o "Luong" dung chung (so acc chay cung luc)."""
        try:
            self.settings.login_threads = max(1, min(8, int(value)))
        except ValueError:
            return
        self.settings.save()
        self.set_status(
            f"Luồng dùng chung = {self.settings.login_threads}: đăng nhập cookie / tạo profile / "
            "bật chuyên nghiệp / đăng nhập web sẽ chạy chừng đó acc cùng lúc."
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

        # "Nhóm mới" + "Bỏ khỏi nhóm" ĐƯA LÊN ĐẦU (yêu cầu người dùng) — hay dùng, khỏi kéo xuống cuối.
        self._group_menu.add_command(
            label="➕ Nhóm mới...", command=self.assign_new_group
        )
        self._group_menu.add_command(
            label="✖ Bỏ khỏi nhóm", command=lambda: self.assign_group("")
        )
        if self.store.groups():
            self._group_menu.add_separator()
        for name in self.store.groups():
            # Cham danh dau nhom ma toan bo acc dang chon deu thuoc ve.
            mark = "● " if current == {name} else "○ "
            self._group_menu.add_command(
                label=mark + name,
                command=lambda n=name: self.assign_group(n),
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

    def _run_async(self, work: Callable[[], None], done_message: str = "Xong.",
                   accs: Optional[list] = None) -> None:
        """Chay ``work`` o luong nen, KHOA theo tung acc.

        ``accs``: danh sach id acc (hoac Account) tac vu se dung. Chi chan khi CO
        acc dang ban trong tac vu khac -> bao ro acc nao, con lai cho chay song
        song. ``accs=None`` = tac vu khong dung profile (vd test proxy) -> luon
        chay, khong khoa acc nao.
        """
        # work co nhan tham so? work(accs) = tac vu batch -> chay tren acc RANH, bo
        # acc ban. work() = tac vu don/toan cuc -> chan khi trung bat ky acc nao.
        nhan_acc = False
        try:
            nhan_acc = len(inspect.signature(work).parameters) >= 1
        except (TypeError, ValueError):
            nhan_acc = False
        acc_objs = list(accs or [])
        ids = {getattr(a, "id", a) for a in acc_objs}

        def _ten(tap):
            xs = sorted(str(x) for x in tap)
            return ", ".join(xs[:6]) + (f" (+{len(xs) - 6})" if len(xs) > 6 else "")

        with self._busy_lock:
            ban = ids & self._busy_accs
            if ban:
                ranh = ids - ban
                if nhan_acc and ranh:
                    # Chay tren acc RANH, bo acc dang ban (bao cho nguoi dung biet).
                    run_ids = ranh
                    run_objs = [a for a in acc_objs if getattr(a, "id", a) in ranh]
                    self._post(lambda t=_ten(ban), n=len(run_ids), b=len(ban): messagebox.showinfo(
                        "Bỏ qua acc đang bận",
                        f"{b} acc đang chạy tác vụ khác nên bỏ qua: {t}.\n\n"
                        f"Vẫn chạy trên {n} acc còn lại.",
                        parent=self))
                else:
                    # Het acc ranh, hoac tac vu don/toan cuc -> chan.
                    self._post(lambda t=_ten(ban): messagebox.showinfo(
                        "Acc đang bận",
                        f"Các acc này đang chạy tác vụ khác: {t}.\n\n"
                        "Chờ xong hoặc bỏ chọn acc đó rồi thao tác acc khác — "
                        "acc không bận vẫn dùng được bình thường.",
                        parent=self))
                    return
            else:
                run_ids = ids
                run_objs = acc_objs
            self._busy_accs |= run_ids
            self._task_count += 1
            if self._task_count == 1:
                self.progress.pack(side="right", padx=12)
                self.progress.start()

        def runner():
            try:
                work(run_objs) if nhan_acc else work()
                if done_message:      # rong = giu thong bao do work tu dat (vd KetQua.tom_tat)
                    self.set_status(done_message)
            except Exception as exc:  # loi cua tac vu nen phai hien ra cho nguoi dung
                message = str(exc)
                self.set_status(f"Lỗi: {message}")
                self._post(lambda: messagebox.showerror("Lỗi", message, parent=self))
            finally:
                self._post(lambda: self._finish_async(run_ids))

        threading.Thread(target=runner, daemon=True).start()

    def _finish_async(self, ids: Optional[set] = None) -> None:
        with self._busy_lock:
            if ids:
                self._busy_accs -= ids
            self._task_count = max(0, self._task_count - 1)
            het = self._task_count == 0
        if het:
            self.progress.stop()
            self.progress.pack_forget()
        self.refresh()

    # ------------------------------------------------------------------
    # Dieu khien MO-DUN (ADR-028): tool goi dung mo-dun theo ma khi nguoi dung bam lenh
    # ------------------------------------------------------------------
    def goi_modun(self, ma: str, accs: list, *, done_message: str = "",
                  so_luong: Optional[int] = None, tieu_de: str = "", khoa: bool = True,
                  tu_tao_profile: bool = False, **tham_so) -> None:
        """Chay mo-dun ``ma`` (core/modun) tren ``accs`` o luong nen, khoa per-acc.

        Dung NguCanh tu App (manager/store/settings, log=set_status, post=_post, so_luong
        = o "Luong" tru khi truyen), goi ``modun.chay``; KetQua -> thanh trang thai, luu store,
        ve lai bang; co loi tung acc -> hop thoai tom tat. Lenh menu chi con 1 dong goi ham nay.
        ``khoa=False``: tac vu khong dung profile (vd test proxy) -> khong khoa acc, chay song song
        voi moi thu (nhung mo-dun van nhan du ``accs``).

        ``tu_tao_profile=True``: acc CHUA co profile -> tu tao (mo-dun tao_profile) TRUOC khi
        chay mo-dun chinh (yeu cau nguoi dung 2026-09-17). Danh cho cac mo-dun tu loc acc theo
        is_installed / lam viec voi profile truoc khi mo (cookie/web/pro/mo profile); tao khong
        duoc thi bao loi acc do, cac acc con lai van chay.
        """
        from core import modun as modun_module
        m = modun_module.lay(ma)
        ten = tieu_de or m.ten
        nc = modun_module.ngu_canh_tu(self, so_luong=so_luong)

        def work(accs_chay):
            if not khoa:
                accs_chay = list(accs)      # khong khoa -> _run_async khong dua acc, tu lay du
            loi_tao: list = []
            if tu_tao_profile:
                thieu = [a for a in accs_chay if not self.manager.is_installed(a)]
                if thieu:
                    self.set_status(f"{ten}: tạo profile cho {len(thieu)} acc chưa có...")
                    kq_tao = modun_module.chay("tao_profile", nc, thieu)
                    self._post(self.refresh)
                    loi_tao = list(kq_tao.loi)          # acc tao profile khong duoc
                    van_thieu = {i for i, _ in loi_tao}
                    accs_chay = [a for a in accs_chay if a.id not in van_thieu]
                    if not accs_chay:
                        self.set_status(f"{ten}: không tạo được profile nào.")
                        if loi_tao:
                            dong = [f"{i}: {ly}" for i, ly in loi_tao[:12]]
                            self._post(lambda: messagebox.showwarning(
                                ten, "Không tạo được profile cho acc:\n" + "\n".join(dong),
                                parent=self))
                        return
            kq = modun_module.chay(ma, nc, accs_chay, **tham_so)
            for i, ly in loi_tao:
                kq.them_loi(i, f"tạo profile lỗi: {ly}")
            try:
                self.store.save()
            except Exception:  # noqa: BLE001
                pass
            self._post(self.refresh)
            self.set_status(f"{ten}: {kq.tom_tat()}")
            if kq.loi:
                dong = [f"{i}: {ly}" for i, ly in kq.loi[:12]]
                them = f"\n... (+{len(kq.loi) - 12})" if len(kq.loi) > 12 else ""
                self._post(lambda: messagebox.showwarning(
                    ten,
                    f"Xong {kq.so_ok}/{kq.so_ok + kq.so_loi} acc"
                    + (f" — {kq.ghi_chu}" if kq.ghi_chu else "") + ".\n\nChưa xong / lỗi:\n"
                    + "\n".join(dong) + them,
                    parent=self))

        self._run_async(work, done_message, accs=accs if khoa else None)

    # ---- Menu Mo-dun sinh tu registry ----------------------------------------
    #: Ten nhom hien tren menu (ma nhom -> nhan).
    TEN_NHOM = {"acc": "👤 Acc", "proxy": "🌐 Proxy", "fanpage": "🏗 Fanpage",
                "dang_bai": "📤 Đăng bài", "khac": "🧰 Khác"}
    #: Mo-dun can NHAP THAM SO / co luong rieng -> uy quyen cho lenh/tab UI da co (thu thap tham so
    #: roi moi goi_modun). Khong co trong day -> chay thang tren acc dang chon (co hoi xac nhan).
    def _uy_quyen_modun(self) -> dict:
        tab = self.tabs.set
        return {
            "dang_nhap_cookie": self.relogin_cookie, "dang_nhap_web": self.login_web_selected,
            "tao_profile": self.create_profiles, "check_tuong": self.check_walls,
            "bat_chuyen_nghiep": self.enable_professional_selected,
            "mo_profile": self.open_profiles, "dong_profile": self.close_profiles,
            "xoa_acc": self.delete_accounts, "doi_proxy": self.change_proxy,
            "check_proxy": self.check_proxies, "khop_mui_gio": self.match_identities,
            "bo_khop_mui_gio": self.clear_identities, "xoa_cache": self.clear_cache,
            "extension": self.install_extension,
            "doi_user_agent": None,                         # cascade category rieng (ben duoi)
            "tao_fanpage_acc": lambda: tab("🏗 Tạo fanpage"), "tao_fanpage_bm": lambda: tab("🏗 Tạo fanpage"),
            "add_page_bm": lambda: tab("🏗 Tạo fanpage"), "tao_bm": lambda: tab("🏗 Tạo fanpage"),
            "dang_fanpage_tu_dong": lambda: self.mo_tab_fanpage("🌐 Công khai"),
            "dang_nhom_tu_dong": lambda: tab("👥 Auto đăng nhóm"),
            "quet_bai": lambda: tab("🔎 Quét bài"), "nhan_tin_ai": lambda: tab("💬 Nhắn tin AI"),
            "tuong_tac": lambda: tab("🤝 Tương tác"),
            "doi_ten_file": lambda: tab("✏️ Đổi tên file"),
            "xoa_bai": lambda: tab("🗑 Xoá bài viết"),
            "mo_cung_windows": self._gat_mo_cung_windows,   # cong tac goc duoi trai
        }

    def mo_tab_fanpage(self, con: str = "🌐 Công khai") -> None:
        """Mo tab "Auto dang fanpage" roi chon dung TAB CON (Cong khai / Dat lich)."""
        self.tabs.set("🎬 Auto đăng fanpage")
        try:
            self.fanpage_tabs.set(con)
        except Exception:  # noqa: BLE001
            pass

    def _gat_mo_cung_windows(self) -> None:
        """Muc menu Mo-dun -> dao cong tac 'Mo cung Windows' roi ap."""
        self.mo_cung_win_var.set(not self.mo_cung_win_var.get())
        self._doi_mo_cung_windows()

    def _menu_modun(self, parent) -> tk.Menu:
        """Dung menu Mo-dun TU registry: cascade theo nhom, moi mo-dun 1 muc. Khong hardcode ma."""
        from core import modun as modun_module
        from core import useragent
        root = self._make_menu(parent)
        uy = self._uy_quyen_modun()
        for nhom in modun_module.NHOM:
            ds = modun_module.danh_sach(nhom)
            if not ds:
                continue
            sub = self._make_menu(root)
            for m in ds:
                if m.ma == "doi_user_agent":
                    ua = self._make_menu(sub)
                    for ten in useragent.cac_loai():
                        ua.add_command(label=ten, command=lambda l=ten: self.change_user_agent(l))
                    ua.add_command(label="Xoá User Agent", command=lambda: self.change_user_agent(""))
                    sub.add_cascade(label=m.ten, menu=ua)
                    continue
                lenh = uy.get(m.ma, "generic")
                if lenh == "generic":
                    sub.add_command(label=m.ten, command=lambda ma=m.ma: self.chay_modun_tren_chon(ma))
                elif lenh is not None:
                    sub.add_command(label=m.ten, command=lenh)
            root.add_cascade(label=self.TEN_NHOM.get(nhom, nhom), menu=sub)
        return root

    def chay_modun_tren_chon(self, ma: str) -> None:
        """Chay mo-dun KHONG can tham so tren cac acc dang chon (hoi xac nhan truoc)."""
        from core import modun as modun_module
        selected = self._require_selection()
        if not selected:
            return
        m = modun_module.lay(ma)
        if not messagebox.askyesno(m.ten, f"{m.ten} cho {len(selected)} acc?"
                                   + (f"\n\n{m.mo_ta}" if m.mo_ta else ""), parent=self):
            return
        self.goi_modun(ma, selected, tieu_de=m.ten)

    def _schedule_running_check(self) -> None:
        self.after(4000, self._running_check)

    def _running_check(self) -> None:
        # Cap nhat cot '▶' luon luon (khong con khoa toan tool) — nhieu tac vu co
        # the dang chay tren cac acc khac nhau, van muon thay acc nao dang mo.
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

    def set_fb_language(self, code: str) -> None:
        """Doi ngon ngu giao dien Facebook cua cac acc dang chon.

        Sua ca cookie luu trong bang lan cookies.sqlite cua profile, nen lan mo
        trinh duyet ke tiep la thay ngay va lan dang nhap lai cung giu nguyen.
        """
        selected = self._require_selection()
        if not selected:
            return
        co_cookie = [a for a in selected if (a.cookie or "").strip()]
        if not co_cookie:
            messagebox.showinfo("Ngôn ngữ Facebook",
                                "Các acc đã chọn chưa lưu cookie.", parent=self)
            return

        doi, vao_profile = 0, 0
        for account in co_cookie:
            sua_cookie, sua_profile = fblocale.set_language(
                account, code, self.manager.profile_dir(account))
            doi += 1 if sua_cookie else 0
            vao_profile += 1 if sua_profile else 0
        self.store.save()
        self.refresh()

        dang_mo = [a.id for a in co_cookie
                   if self.manager.is_installed(a) and self.manager.is_running(a)]
        tin = (f"Đã đổi {doi} acc sang {fblocale.label(code)} "
               f"({vao_profile} profile áp dụng ngay).")
        if dang_mo:
            tin += " Acc đang mở phải đóng rồi mở lại mới thấy."
        self.set_status(tin)

    def change_user_agent(self, loai: str) -> None:
        """Doi User Agent cua cac acc dang chon.

        ``loai`` rong = xoa UA (dung UA mac dinh cua Firefox). Nguoc lai moi acc
        lay MOT UA ngau nhien trong category do. Sau khi gan xong ap lai vao
        profile (mozilla.cfg) o luong nen; acc dang mo phai mo lai moi thay.
        """
        from core import useragent
        selected = self._require_selection()
        if not selected:
            return
        if loai and not useragent.doc_loai(loai):
            messagebox.showinfo("Đổi user agent",
                                f"Category “{loai}” chưa có UA nào.", parent=self)
            return

        # Nghiep vu (gan UA, luu, configure lai profile) o mo-dun core/modun/doi_user_agent (ADR-028).
        self.goi_modun("doi_user_agent", selected, tieu_de="Đổi user agent", loai=loai)

    def set_pro_mode(self, gia_tri: str) -> None:
        """Danh dau tay cot 'Chuyen nghiep' (Bật / Chưa bật) cho cac acc dang chon."""
        selected = self._require_selection()
        if not selected:
            return
        for account in selected:
            account.pro_mode = gia_tri
        self.store.save()
        self.refresh()
        nhan = "ĐÃ bật" if gia_tri == store_module.PRO_BAT else "CHƯA bật"
        self.set_status(f"Đã đánh dấu {len(selected)} acc: chuyên nghiệp {nhan}.")

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
        text, separator, fields, group, ua_loai = result
        added, errors = self.store.import_lines(
            text, separator, fields=fields, group=group, ua_loai=ua_loai)
        self.refresh()
        into = f" vào nhóm “{group}”" if group else ""
        ua_note = f" (gán UA {', '.join(ua_loai)})" if ua_loai else ""
        summary = f"Đã thêm {added} acc{into}{ua_note}."
        if errors:
            summary += "\n\nBỏ qua:\n" + "\n".join(errors[:15])
            if len(errors) > 15:
                summary += f"\n... và {len(errors) - 15} dòng nữa."
        messagebox.showinfo("Nhập hàng loạt", summary, parent=self)

    def bulk_update(self) -> None:
        """Sua custom: dan danh sach, khop theo Uid, THAY cac cot da chon.

        Hop thoai y het "Nhap hang loat" (o dan + chon dinh dang + xem truoc)
        nhung khong them acc moi -- chi cap nhat acc co san trong bang.
        """
        result = BulkImportDialog(self, mode="update").show()
        if not result:
            return
        text, separator, fields, _group, _ua = result
        updated, errors = self.store.update_lines(text, separator, fields=fields)
        self.refresh()
        summary = f"Đã cập nhật {updated} acc."
        if errors:
            xuong = chr(10)
            summary += xuong * 2 + "Bỏ qua:" + xuong + xuong.join(errors[:15])
            if len(errors) > 15:
                summary += f"{xuong}... và {len(errors) - 15} dòng nữa."
        messagebox.showinfo("Sửa custom (hàng loạt)", summary, parent=self)

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

        self.goi_modun("xoa_acc", selected, done_message=f"Đã xoá {len(selected)} acc.", xoa_thu_muc=remove_folder)

    def create_profiles(self) -> None:
        selected = self._require_selection()
        if not selected:
            return
        pending = [a for a in selected if not self.manager.is_installed(a)]
        if not pending:
            messagebox.showinfo("Tạo profile", "Các acc đã chọn đều có profile rồi.", parent=self)
            return
        workers = min(self._so_luong(), len(pending))      # o "Luong" dung chung
        estimate = "" if self.settings.clone_from_template else " (~25 giây mỗi acc)"
        threads = f", chạy {workers} luồng cùng lúc" if workers > 1 else ""
        if not messagebox.askyesno(
            "Tạo profile",
            f"Tạo profile cho {len(pending)} acc{estimate}{threads}?",
            parent=self,
        ):
            return

        # Nghiep vu o mo-dun core/modun/tao_profile (ADR-028); UI chi hoi/xac nhan roi goi.
        self.goi_modun("tao_profile", pending, so_luong=workers,
                       done_message=f"Đã tạo xong {len(pending)} profile.")

    def open_profiles(self) -> None:
        selected = self._require_selection()
        if not selected:
            return
        url = self.settings.start_url
        # "Mở profile" CHỈ mở trình duyệt, KHÔNG thao tác gì (yêu cầu người dùng 2026-09-19):
        # không nạp cookie, không theo dõi/ghi đè cookie — người dùng toàn quyền. Acc chưa có
        # profile thì tự tạo (tu_tao_profile). Nghiệp vụ ở mô-đun core/modun/mo_profile (ADR-028).
        self.goi_modun("mo_profile", selected, done_message=f"Đã mở {len(selected)} profile.",
                       tu_tao_profile=True, url=url)

    def login_web_selected(self) -> None:
        """Đăng nhập web bằng id|pass|2fa (chuột phải) cho các acc đã chọn.

        Mở Firefox bình thường, điền form + mã 2FA (TOTP) qua agent, xác minh bằng
        phiên thật. Song song theo ô "Luồng" dùng chung (trần fblogin.MAX_SONG_SONG).
        """
        from core import fblogin
        selected = self._require_selection()
        if not selected:
            return
        # Acc chua co profile -> tu tao (tu_tao_profile); chi can co mat khau.
        usable = [a for a in selected if (a.password or "").strip()]
        thieu = len(selected) - len(usable)
        if not usable:
            messagebox.showinfo("Đăng nhập web",
                                "Các acc đã chọn chưa có mật khẩu.",
                                parent=self)
            return
        # Song song theo o "Luong" dung chung, khong qua tran (moi acc 1 Firefox).
        workers = min(fblogin.MAX_SONG_SONG, self._so_luong(), len(usable))
        # BO hop thoai xac nhan (yeu cau nguoi dung 2026-09-19): bam la chay luon; thieu mat khau
        # thi ghi thanh trang thai thay vi bung hop thoai.
        if thieu:
            self.set_status(f"Đăng nhập web: bỏ qua {thieu} acc thiếu mật khẩu.")

        # Acc chua co profile -> tu tao (tu_tao_profile). Nghiep vu o mo-dun dang_nhap_web (ADR-028).
        self.goi_modun("dang_nhap_web", usable, so_luong=workers, tieu_de="Đăng nhập web",
                       tu_tao_profile=True)

    def relogin_cookie(self) -> None:
        """Nap lai cookie da luu (ke ca khi da dang nhap) roi mo thang Facebook.

        Dung khi phien Facebook het han nhung cookie ``c_user`` cu van con, luc do
        ``open_profiles`` se khong tu nap lai vi tuong da dang nhap.
        """
        selected = self._require_selection()
        if not selected:
            return
        # Acc chua co profile -> tu tao (tu_tao_profile); chi can co cookie da luu.
        usable = [a for a in selected if a.cookie.strip()]
        skipped = len(selected) - len(usable)
        if not usable:
            messagebox.showinfo(
                "Đăng nhập với cookie",
                "Các acc đã chọn chưa lưu cookie.",
                parent=self,
            )
            return

        # Phai vao thang Facebook thi trinh duyet moi bao lai duoc ket qua
        # (xem ProfileManager.verify_cookie_login). Trang khoi dong khac thi bo qua.
        url = self.settings.start_url
        if "facebook.com" not in (url or "").lower():
            url = "https://www.facebook.com/"
        workers = min(self._so_luong(), len(usable))       # o "Luong" dung chung
        # Nghiep vu (giu phien moi hon, nap cookie, xac minh, fallback dang nhap web) o
        # mo-dun core/modun/dang_nhap_cookie (ADR-028) — UI chi loc acc + goi.
        tieu_de = "Đăng nhập với cookie" + (f" (bỏ qua {skipped} acc chưa lưu cookie)" if skipped else "")
        self.goi_modun("dang_nhap_cookie", usable, so_luong=workers, tieu_de=tieu_de,
                       tu_tao_profile=True, url=url)

    def kill_all_browsers(self) -> None:
        """Tat MOI trinh duyet do tool mo, khong can chon dong nao.

        Dung khi mo nhieu qua roi loan, hoac khi mot phien nao do treo. Chi dung
        toi Firefox nam trong thu muc profile cua tool -- Firefox binh thuong cua
        may khong bi anh huong.
        """
        dang_chay = self.manager.running_count()
        if not dang_chay:
            self.set_status("Không có trình duyệt nào của tool đang mở.")
            return
        if not messagebox.askyesno(
            "Tắt hết Firefox",
            f"Tắt {dang_chay} tiến trình Firefox do tool mở?" + chr(10) * 2
            + "Việc đang làm dở trên các trình duyệt đó sẽ mất.",
            parent=self,
        ):
            return

        def work():
            so = self.manager.close_all()
            self._post(self.refresh)
            self.set_status(f"Đã tắt {so} tiến trình Firefox.")

        self._run_async(work, "Đã tắt hết trình duyệt.", accs=self._rows)

    def close_profiles(self) -> None:
        selected = self._require_selection()
        if not selected:
            return

        self.goi_modun("dong_profile", selected, done_message="Đã đóng profile đã chọn.")

    def open_posts(self) -> None:
        """Chuyen sang tab Quet bai (ex Thu nghiem AI, lan 4)."""
        try:
            self.tabs.set("🔎 Quét bài")
        except Exception:
            pass

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

        note = f" ({skipped} acc chưa có proxy, bỏ qua)" if skipped else ""
        # Nghiep vu o mo-dun core/modun/khop_mui_gio (ADR-028).
        self.goi_modun("khop_mui_gio", targets, tieu_de="Khớp theo proxy",
                       done_message=f"Đã khớp múi giờ + ngôn ngữ theo proxy{note}.")

    def clear_identities(self) -> None:
        """Trả profile về múi giờ và ngôn ngữ mặc định của máy."""
        selected = self._require_selection()
        if not selected:
            return
        self.goi_modun("bo_khop_mui_gio", selected, done_message=f"Đã bỏ khớp múi giờ cho {len(selected)} acc.")

    def _apply_proxy_change(self, pairs: list[tuple[Account, Proxy]]) -> None:
        """Gán proxy rồi dò vị trí — chạy Ở LUỒNG NỀN để KHÔNG treo tool khi thêm nhiều proxy.

        Hai pha (mô-đun doi_proxy, ADR-028): (1) GÁN proxy vào cột cho tất cả acc rồi refresh bảng
        NGAY; (2) DÒ VỊ TRÍ song song theo ô "Luồng" (mặc định 5). Trước đây chạy thẳng trên luồng
        giao diện + dò tuần tự -> thêm 100 proxy là 'Not Responding' (yêu cầu người dùng 2026-09-21).
        Acc đang mở cần mở lại -> hỏi sau khi xong.
        """
        from core import modun as modun_module
        accs = [a for a, _ in pairs]
        proxy_cua = {a.id: p for a, p in pairs}
        luong = self._so_luong()
        nc = modun_module.ngu_canh_tu(self, so_luong=luong)
        self.set_status(f"Đang gán proxy cho {len(pairs)} acc vào cột, sau đó dò vị trí ({luong} luồng)...")

        def work(run_accs):
            # pha 1 (gán proxy) xong -> on_gan_xong refresh cột ngay; pha 2 (dò vị trí) chạy song song.
            kq = modun_module.chay("doi_proxy", nc, run_accs, proxy_cua=proxy_cua,
                                   on_gan_xong=lambda: self._post(self.refresh))

            def xong():
                self.refresh()
                self.set_status(kq.ghi_chu or f"Đã đổi proxy cho {len(run_accs)} acc.")
                if kq.loi:
                    messagebox.showwarning(
                        "Khớp theo proxy",
                        "Đổi proxy xong nhưng không dò được vị trí của:" + chr(10)
                        + chr(10).join(f"{i}: {ly}" for i, ly in kq.loi[:10])
                        + chr(10) * 2 + "Múi giờ và ngôn ngữ vẫn giữ như cũ.", parent=self)
                can = [a for a in run_accs if a.id in set(kq.du_lieu.get("can_mo_lai", []))]
                if not can:
                    return
                names = ", ".join(a.id for a in can[:5]) + (f" ... (+{len(can) - 5})" if len(can) > 5 else "")
                if messagebox.askyesno(
                    "Cần mở lại trình duyệt",
                    f"{len(can)} acc đang mở. Firefox chỉ đọc cấu hình proxy lúc khởi động "
                    f"nên phải mở lại mới ăn proxy mới:" + chr(10) + f"{names}" + chr(10) * 2
                    + "Khởi động lại ngay?", parent=self):
                    self.goi_modun("mo_lai_profile", can, done_message=f"Đã mở lại {len(can)} trình duyệt.")

            self._post(xong)

        # Khóa per-acc (batch): chạy trên acc rảnh, bỏ acc đang bận ở tác vụ khác. Luồng nền -> GUI mượt.
        self._run_async(work, "", accs=accs)

    def _popup_check_menu(self) -> None:
        """Bung menu Check tu nut tren thanh cong cu."""
        m = self._make_menu(self)
        m.add_command(label="Check proxy", command=self.check_proxies)
        m.add_command(label="Check cookie", command=self.check_cookies)
        m.add_command(label="Check tường (live/die)", command=self.check_walls)
        self._apply_theme()
        try:
            m.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            m.grab_release()

    def _cookie_header(self, account: Account) -> str:
        """Chuoi cookie 'name=value; ...' cua acc: uu tien cookie thuc trong profile,
        khong thi doc tu chuoi cookie da luu."""
        if self.manager.is_installed(account):
            try:
                from core import fbgroup
                return fbgroup.read_fb_cookies(self.manager.profile_dir(account))
            except Exception:
                pass
        raw = (account.cookie or "").strip()
        if not raw:
            return ""
        try:
            cookies = cookie_module.parse(raw, default_domain=".facebook.com")
            return "; ".join(f"{c.name}={c.value}" for c in cookies if c.name)
        except Exception:
            return ""

    def check_cookies(self) -> None:
        """Check cookie: acc co cookie dang nhap (c_user) hay khong.

        Kiem tra NHANH, khong ra mang: Facebook da khai tu mbasic nen khong con
        endpoint HTTP nao xac nhan cookie con song. Muc nay chi cho biet acc DA CO
        cookie dang nhap chua; muon biet chac song/die thi dung 'Check tường'.
        """
        selected = self._require_selection()
        if not selected:
            return
        co, thieu = [], []
        for account in selected:
            header = self._cookie_header(account)
            if "c_user=" in header:
                co.append(account.id)
                account.cookie_ok = account.cookie_ok or time.strftime("%Y-%m-%d %H:%M")
            else:
                thieu.append(account.id)
        self.store.save()
        self.refresh()
        self.set_status(f"Có cookie đăng nhập: {len(co)}/{len(selected)}.")
        msg = f"Có cookie đăng nhập: {len(co)} acc.\nThiếu cookie: {len(thieu)} acc."
        if thieu:
            msg += "\n\nThiếu cookie:\n" + ", ".join(thieu[:20])
        msg += "\n\n(Cookie có sẵn chưa chắc còn sống — dùng 'Check tường' để biết chắc live/die.)"
        messagebox.showinfo("Check cookie", msg, parent=self)

    def check_walls(self) -> None:
        """Check tường acc FB bằng HTTP — KHÔNG mở trình duyệt (ADR-020).

        Dùng cookie riêng của từng acc gọi mbasic/me: còn phiên -> Live, bị đá về đăng nhập -> Die,
        về checkpoint -> Checkpoint, cookie mất c_user -> Cookie chết. Chạy song song theo ô "Luồng".
        """
        selected = self._require_selection()
        if not selected:
            return
        workers = min(self._so_luong(), len(selected))
        self.set_status(f"Check tường {len(selected)} acc ({workers} luồng, không mở browser)...")
        # Nghiep vu o mo-dun core/modun/check_tuong (ADR-028): HTTP bang cookie tung acc.
        self.goi_modun("check_tuong", selected, so_luong=workers,
                       tieu_de="Kết quả check tường (không mở browser)")

    def enable_professional_selected(self) -> None:
        """Bật chế độ chuyên nghiệp cho các acc đang chọn (menu ... trên profile)."""
        from core import fbcreatepage
        selected = self._require_selection()
        if not selected:
            return
        # Acc chua co profile -> tu tao (tu_tao_profile) truoc khi bat.
        workers = min(self._so_luong(), len(selected))    # o "Luong" dung chung
        if not messagebox.askyesno(
                "Chế độ chuyên nghiệp",
                f"Bật chế độ chuyên nghiệp cho {len(selected)} acc ({workers} luồng cùng lúc)?\n"
                "Acc chưa có profile sẽ tự tạo trước. Tool mở profile từng acc rồi bấm 'Bật'.",
                parent=self):
            return

        # Nghiep vu o mo-dun core/modun/bat_chuyen_nghiep (ADR-028).
        self.goi_modun("bat_chuyen_nghiep", selected, so_luong=workers,
                       tieu_de="Chế độ chuyên nghiệp", tu_tao_profile=True)

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

        # Nghiep vu (test_proxy, Live/Die, canh bao trung dai IP) o mo-dun core/modun/check_proxy (ADR-028).
        # Mang thuan, khong dung profile -> accs=None: khong khoa acc.
        self.goi_modun("check_proxy", targets, khoa=False, tieu_de="Kết quả test proxy")

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

        self._run_async(work, "Nạp cookie xong.", accs=[account])

    def _apply_cookie(self, account: Account, replace: bool, domain: str = ".facebook.com") -> int:
        """Ghi cookie da luu vao profile — nghiep vu o core.modun.tao_profile.nap_cookie_da_luu."""
        from core.modun.tao_profile import nap_cookie_da_luu
        return nap_cookie_da_luu(self.manager, account, replace=replace, domain=domain)
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

        self.goi_modun("extension", usable, tieu_de="Extension", hanh_dong="cai", xpi=xpi,
                       done_message=f"Đã cài {addon_id} v{version}. Mở lại trình duyệt để Firefox nhận addon.")

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

        self.goi_modun("extension", selected, tieu_de="Extension", hanh_dong="go", done_message="Gỡ extension xong.")

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

        self.goi_modun("xoa_cache", targets, tieu_de="Xoá cache")

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

        self._run_async(work, "Chuyển profile xong.", accs=self._rows)

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
        self._da_dong = True            # cac bo theo doi nen tu thoi
        try:
            self.autoup.stop()
        except Exception:
            pass
        try:
            self.autoup_x.stop()
        except Exception:
            pass

        # Proxy nam trong mozilla.cfg cua tung profile, khong con di qua relay cua
        # tool nua -- dong tool khong con lam trinh duyet mat mang.
        self.relays.stop_all()
        self.destroy()


# Helper test proxy da chuyen ve core/modun/check_proxy (ADR-028); giu ten cu.
from core.modun.check_proxy import (extract_exit_ip as _extract_exit_ip,  # noqa: E402
                                    subnet_key as _subnet_key,
                                    duplicate_subnet_report as _duplicate_subnet_report)


def _thoat_han(ma: int = 0) -> None:
    """THOAT HAN tien trinh sau khi cua so da dong.

    Loi that 29/09 (may khac): dong tool roi ma khong ghi de duoc "LVC Manager Profile.exe" —
    "file is open in LVC Manager Profile.exe". Python CHO moi viec nen cua ThreadPoolExecutor
    (dang bai video toi 23 phut, tao page...) chay xong moi thoat -> tien trinh song ngam, khong
    cua so, giu khoa file exe. _on_close da dung vong lap + relay; du lieu ghi kieu file tam +
    os.replace nen cat ngang khong hong file. Firefox dang mo la tien trinh rieng, khong bi tat.
    """
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(ma)


def run() -> None:
    app = App()
    if app.session is None:   # nguoi dung dong cong dang nhap
        _thoat_han(0)
    app.mainloop()
    _thoat_han(0)
