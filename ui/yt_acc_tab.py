"""Tab con "YouTube" trong "Quan ly acc" — bang acc Gmail/YouTube.

GIONG HET tab Facebook/X: ke thua ui/x_acc_tab.XAccTab roi doi cac HANG SO cua nen
tang (kho acc, thu muc profile, cot bang, cookie, trang mo) nen co day du bang acc,
bang thong tin ben phai, keo chuot chon nhieu, menu chuot phai, proxy, User Agent,
nhom, cache... ma khong chep lai nghin dong.

KHAC tab X hai cho (theo yeu cau nguoi dung):
  * NHAP HANG LOAT theo dinh dang cua tool "LVC video slide" (tab Quan ly Firefox):
    ``gmail | pass gmail | 2FA | proxy`` — xem core/yt_import.py;
  * DANG NHAP GMAIL WEB (core/gmaillogin.py + agent core/assets/gmail_agent.js) thay
    cho "dang nhap X bang Google".

Kho acc RIENG data/accounts_yt.json, profile RIENG <profiles_root>_yt -> khong tron
voi acc Facebook/X.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core import store as store_module
from core import yt_import

from .x_acc_tab import XAccTab
from .x_dialogs import XBulkImportDialog

YT_ACCOUNTS_PATH = os.path.join(os.path.dirname(store_module.ACCOUNTS_PATH), "accounts_yt.json")
YT_TAB_TITLE = "▶️ YouTube"
YT_START_URL = "https://www.youtube.com/"
YT_HOME_URL = "https://studio.youtube.com/"
#: Cookie Google: mien mac dinh khi dan + host tinh la "cua YouTube/Google".
YT_COOKIE_DOMAIN = ".google.com"
YT_COOKIE_HOSTS = ("google.com", "youtube.com")
#: Co cookie nay = profile da dang nhap Google.
YT_AUTH_COOKIE = "SID"

#: Cot bang acc YouTube: dinh danh la GMAIL (khong co user/pass rieng nhu X).
YT_COLUMNS = (
    ("stt", "#", 44, "center"),
    ("id", "Gmail", 230, "w"),
    ("password", "Pass Gmail", 130, "w"),
    ("gmail_2fa", "2FA", 70, "center"),
    ("gmail_kp", "Mail KP", 180, "w"),
    ("group", "Nhóm", 110, "w"),
    ("profile", "Profile", 90, "center"),
    ("cookie", "Cookie Google", 110, "center"),
    ("running", "Đang chạy", 85, "center"),
    ("status", "Trạng thái", 95, "center"),
    ("proxy", "Proxy", 210, "w"),
    ("note", "Ghi chú", 220, "w"),
)


class YtBulkImportDialog(XBulkImportDialog):
    """Nhap hang loat acc YouTube — dinh dang cua tool LVC video slide."""

    MODULE = yt_import
    FIELDS = yt_import.YT_FIELDS
    FIELD_LABEL = yt_import.YT_FIELD_LABEL
    FIELD_KEY = yt_import.YT_FIELD_KEY
    MAC_DINH = yt_import.YT_MAC_DINH
    COT_BAT_BUOC = "gmail"
    NHAN_BAT_BUOC = "Gmail"
    TIEU_DE = "Nhập hàng loạt acc YouTube (Gmail)"
    NHAN_DAN = ("Dán danh sách acc YouTube — mỗi dòng một acc, "
                "định dạng: gmail | pass gmail | 2FA | proxy")


class YtAccTab(XAccTab):
    """Bang acc YouTube: kho acc + ProfileManager rieng (hau to thu muc "_yt")."""

    ACCOUNTS_PATH = YT_ACCOUNTS_PATH
    HAU_TO_PROFILE = "_yt"
    START_URL = YT_START_URL
    HOME_URL = YT_HOME_URL
    COOKIE_DOMAIN = YT_COOKIE_DOMAIN
    COOKIE_HOSTS = YT_COOKIE_HOSTS
    AUTH_COOKIE = YT_AUTH_COOKIE
    COLUMNS = YT_COLUMNS
    THREADS_KEY = "yt_threads"
    DETAIL_ROWS = (
        ("Gmail", "id", 0),
        ("Pass Gmail", "password", 0),
        ("2FA Gmail (secret)", "gmail_2fa", 0),
        ("Mail KP", "recovery_mail_backup", 0),
        ("Cookie Google", "cookie", 0),
        ("Proxy", "proxy", 0),
        ("Nhóm", "group", 0),
    )

    # ---- nhap hang loat theo dinh dang Gmail ----------------------------
    def bulk_import(self) -> None:
        result = YtBulkImportDialog(self.winfo_toplevel(), groups=self.store.groups()).show()
        if not result:
            return
        text, sep, fields, group, ua_loai = result
        added, errors = yt_import.nhap_vao_store(self.store, text, group, sep=sep,
                                                 fields=fields, ua_loai=ua_loai)
        self.refresh()
        tin = f"Đã thêm {added} acc YouTube" + (f" vào nhóm “{group}”" if group else "") + "."
        if errors:
            tin += "\n\nBỏ qua:\n" + "\n".join(errors[:15])
            if len(errors) > 15:
                tin += f"\n... và {len(errors) - 15} dòng nữa."
        messagebox.showinfo("Nhập hàng loạt (YouTube)", tin, parent=self.winfo_toplevel())

    def row_values(self, index: int, account) -> tuple:
        """Cot "gmail_kp" cua tab nay lay tu recovery_mail_backup (mail khoi phuc)."""
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
            "gmail_2fa": "có" if (account.extra or {}).get("gmail_2fa") else "—",
            "gmail_kp": account.recovery_mail_backup or "—",
            "group": account.group or "—",
            "profile": "đã tạo" if installed else "chưa tạo",
            "cookie": "có" if (account.cookie or "").strip() else "—",
            "running": "▶" if installed and self.manager.is_running(account) else "",
            "status": account.status or "—",
            "proxy": account.get_proxy().display(mask=not show) or "—",
            "note": (account.note or "").replace(chr(10), " ")[:120],
        }
        return tuple(cells[key] for key, *_ in self.COLUMNS)

    # ---- dang nhap Gmail web -------------------------------------------
    def login_google_selected(self) -> None:
        """Đăng nhập Gmail (web) cho các acc đã chọn → lưu cookie Google.

        Mở accounts.google.com → điền Gmail/mật khẩu/2FA (agent) → xác minh bằng
        cookie thật đọc từ profile. Acc thiếu mật khẩu bị bỏ qua và nêu tên.
        """
        from core import gmaillogin
        chon = self._require_selection()
        if not chon:
            return
        du = [a for a in chon if (a.id or "").strip() and (a.password or "").strip()]
        thieu = [a.id for a in chon if a not in du]
        if not du:
            messagebox.showinfo(
                "Đăng nhập Gmail",
                "Các acc đã chọn chưa có mật khẩu Gmail.\n"
                "Nhập ở cột Pass Gmail rồi thử lại.",
                parent=self.winfo_toplevel())
            return
        workers = self._so_luong()

        def work():
            def on_xong(a, kq):
                try:
                    self.store.save()
                except Exception:  # noqa: BLE001
                    pass
                self.app._post(self.refresh)

            kq = gmaillogin.login_nhieu(
                self.manager, du, workers=workers,
                log=lambda m: self.app._post(lambda m=m: self.app.set_status(m)),
                on_xong=on_xong)
            try:
                self.store.save()
            except Exception:  # noqa: BLE001
                pass

            def bao():
                self.refresh()
                tin = (f"Đăng nhập Gmail: {len(kq['vao'])}/{kq['so']} acc vào, "
                       "đã lưu cookie Google.")
                if kq["khong"]:
                    tin += " Chưa vào: " + ", ".join(kq["khong"][:5])
                    if len(kq["khong"]) > 5:
                        tin += "..."
                if thieu:
                    tin += (f"\nBỏ qua {len(thieu)} acc thiếu mật khẩu: "
                            + ", ".join(thieu[:5]) + ("..." if len(thieu) > 5 else ""))
                messagebox.showinfo("Đăng nhập Gmail", tin, parent=self.winfo_toplevel())
            self.app._post(bao)
        self._chay_nen(work)

    # ---- menu chuot phai: doi nhan cho dung nen tang --------------------
    def _make_menu(self) -> tk.Menu:
        menu = super()._make_menu()
        self._doi_nhan_menu(menu, {
            "🟢 Đăng nhập Google (lấy cookie X)": "🟢 Đăng nhập Gmail (lấy cookie Google)",
            "Sửa Cookie X...": "Sửa Cookie Google...",
            "Cookie X": "Cookie Google",
        })
        return menu

    @staticmethod
    def _doi_nhan_menu(menu: tk.Menu, doi: dict) -> None:
        """Doi nhan cac muc menu da dung (ke ca trong cascade con)."""
        try:
            cuoi = menu.index("end")
        except tk.TclError:
            return
        for i in range(0, (cuoi or 0) + 1):
            try:
                loai = menu.type(i)
            except tk.TclError:
                continue
            if loai == "cascade":
                con = menu.entrycget(i, "menu")
                if con:
                    try:
                        YtAccTab._doi_nhan_menu(menu.nametowidget(con), doi)
                    except Exception:  # noqa: BLE001
                        pass
                continue
            if loai in ("command", "checkbutton", "radiobutton"):
                try:
                    nhan = menu.entrycget(i, "label")
                except tk.TclError:
                    continue
                if nhan in doi:
                    menu.entryconfigure(i, label=doi[nhan])
