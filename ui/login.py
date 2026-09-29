"""Cua so dang nhap hai buoc: tai khoan -> key tool.

Dung lam "cong" truoc khi mo cua so chinh. Goi qua gate(); tra ve du lieu phien
neu qua duoc, None neu nguoi dung thoat.

Vi sao la CTkToplevel chu khong phai mot cua so goc rieng: Tk chi nen co mot
goc. Tao goc thu hai sau khi huy goc thu nhat de lai cac callback 'after' treo
cua customtkinter va no bao loi ra console. Nen cua so chinh duoc tao truoc roi
an di (withdraw), cong dang nhap chay de len tren.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from datetime import datetime, timezone
from tkinter import messagebox
from typing import Callable, Optional

import customtkinter as ctk

from core import config
from core import licensing
from core.licensing import LicenseClient, Vault

PAD = 8
#: Mat mang luc tu dang nhap bang phien da luu -> cho bay nhieu giay roi thu lai.
AUTO_LOGIN_THU_LAI_GIAY = 30


class LoginWindow(ctk.CTkToplevel):
    """Hai buoc dang nhap, dung chung mot khung."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title("LVC Manager Profile - Đăng nhập")
        self.geometry("520x560")
        self.resizable(False, False)
        self._set_icon()

        self.client = LicenseClient()
        self.vault = Vault()
        self.session: Optional[dict] = None

        # Ket qua tu luong mang khong duoc dong vao Tk truc tiep -- day qua hang
        # doi roi cua so tu lay ra, giong cach cua so chinh dang lam.
        self._events: queue.Queue = queue.Queue()
        self._busy = False
        self._closing = False
        self._drain_id = None

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._quit)
        self.bind("<Escape>", lambda _e: self._quit())
        self._drain_id = self.after(100, self._drain_events)
        self.after(120, self._grab)
        self.after(200, self._try_auto_login)

    # ------------------------------------------------------------------
    # Giao dien
    # ------------------------------------------------------------------
    def _set_icon(self) -> None:
        ico = config.resource_path("assets", "logo.ico")
        if os.path.isfile(ico):
            try:
                self.iconbitmap(ico)
            except Exception:
                pass

    def _grab(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _build(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0, height=64)
        header.pack(fill="x")
        try:
            from PIL import Image
            logo = Image.open(config.resource_path("assets", "logo.png"))
            self._logo_img = ctk.CTkImage(light_image=logo, dark_image=logo, size=(38, 38))
            ctk.CTkLabel(header, image=self._logo_img, text="").pack(
                side="left", padx=(14, 8), pady=12)
        except Exception:
            pass
        ctk.CTkLabel(
            header, text="LVC Manager Profile",
            font=ctk.CTkFont(size=19, weight="bold"),
        ).pack(side="left", pady=12)

        self.step_label = ctk.CTkLabel(header, text="", text_color="gray60")
        self.step_label.pack(side="right", padx=14)

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=18, pady=(14, 6))

        self.progress = ctk.CTkProgressBar(self, mode="indeterminate", height=6)
        self.status_label = ctk.CTkLabel(self, text="", wraplength=470, justify="center")
        self.status_label.pack(side="bottom", fill="x", padx=18, pady=(4, 12))

        self._show_account_step()

    def _clear_body(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()

    def _show_account_step(self) -> None:
        """Buoc 1: tai khoan va mat khau."""
        self._clear_body()
        self.step_label.configure(text="Bước 1/2")

        ctk.CTkLabel(
            self.body, text="Đăng nhập tài khoản",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            self.body, text="Dùng tài khoản LVC đã được cấp.",
            text_color="gray60",
        ).pack(anchor="w", pady=(0, 14))

        creds = self.vault.load_credentials()

        ctk.CTkLabel(self.body, text="Tên đăng nhập").pack(anchor="w")
        self.username_entry = ctk.CTkEntry(self.body, height=36, placeholder_text="Tên đăng nhập")
        self.username_entry.pack(fill="x", pady=(2, 10))
        self.username_entry.insert(0, creds.get("username", ""))

        ctk.CTkLabel(self.body, text="Mật khẩu").pack(anchor="w")
        password_row = ctk.CTkFrame(self.body, fg_color="transparent")
        password_row.pack(fill="x", pady=(2, 10))
        self.password_entry = ctk.CTkEntry(
            password_row, height=36, show="*", placeholder_text="Mật khẩu")
        self.password_entry.pack(side="left", fill="x", expand=True)
        self.password_entry.insert(0, creds.get("password", ""))
        self._show_password = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            password_row, text="Hiện", width=60, variable=self._show_password,
            command=lambda: self.password_entry.configure(
                show="" if self._show_password.get() else "*"),
        ).pack(side="left", padx=(8, 0))

        # Mac dinh tich san: lan dau chua co gi da luu thi bool(creds) la False,
        # tich se tat va tool khong bao gio luu duoc gi -> khong tu dang nhap lai.
        self._remember_account = tk.BooleanVar(value=True)
        # Khong ghi ra duong dan file da luu: chi lam lo cho de nguoi ta mo ra mo.
        ctk.CTkCheckBox(
            self.body, text="Ghi nhớ thông tin đăng nhập",
            variable=self._remember_account,
        ).pack(anchor="w", pady=(2, 14))

        buttons = ctk.CTkFrame(self.body, fg_color="transparent")
        buttons.pack(fill="x", side="bottom")
        self.login_button = ctk.CTkButton(
            buttons, text="Đăng nhập", height=38, command=self._on_login)
        self.login_button.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            buttons, text="Thoát", height=38, width=110, fg_color="#b3413a",
            hover_color="#98332d", command=self._quit,
        ).pack(side="left", padx=(8, 0))

        self.password_entry.bind("<Return>", lambda _e: self._on_login())
        self.username_entry.bind("<Return>", lambda _e: self.password_entry.focus_set())
        (self.password_entry if creds.get("username") else self.username_entry).focus_set()

    def _show_key_step(self) -> None:
        """Buoc 2: key tool."""
        self._clear_body()
        self.step_label.configure(text="Bước 2/2")
        username = (self.client.user_info or {}).get("username", "")

        ctk.CTkLabel(
            self.body, text="Kích hoạt key tool",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            self.body, text=f"Đang đăng nhập: {username}", text_color="gray60",
        ).pack(anchor="w", pady=(0, 14))

        ctk.CTkLabel(self.body, text="Key tool").pack(anchor="w")
        self.key_entry = ctk.CTkEntry(
            self.body, height=36, placeholder_text="Dán key tool vào đây")
        self.key_entry.pack(fill="x", pady=(2, 10))
        saved_key = self.vault.load_license_key()
        self.key_entry.insert(0, saved_key)

        self._remember_key = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            self.body, text="Ghi nhớ key tool và giữ đăng nhập lần sau",
            variable=self._remember_key,
        ).pack(anchor="w", pady=(2, 4))
        ctk.CTkLabel(
            self.body,
            text="Key gắn với máy này. Đổi máy thì cần kích hoạt lại.",
            text_color="gray55", justify="left", font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=(0, 14))

        buttons = ctk.CTkFrame(self.body, fg_color="transparent")
        buttons.pack(fill="x", side="bottom")
        self.activate_button = ctk.CTkButton(
            buttons, text="Kích hoạt", height=38, command=self._on_activate)
        self.activate_button.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            buttons, text="Quay lại", height=38, width=110, fg_color="gray50",
            hover_color="gray40", command=self._back_to_account,
        ).pack(side="left", padx=(8, 0))

        self.key_entry.bind("<Return>", lambda _e: self._on_activate())
        self.key_entry.focus_set()

    def _back_to_account(self) -> None:
        if self._busy:
            return
        self.client.logout()
        self._set_status("")
        self._show_account_step()

    # ------------------------------------------------------------------
    # Chay viec mang o luong rieng
    # ------------------------------------------------------------------
    def _drain_events(self) -> None:
        if self._closing or not self.winfo_exists():
            return
        try:
            while True:
                self._events.get_nowait()()
        except queue.Empty:
            pass
        self._drain_id = self.after(100, self._drain_events)

    def _post(self, callback: Callable[[], None]) -> None:
        self._events.put(callback)

    def _set_status(self, message: str, color: str = "gray60") -> None:
        self.status_label.configure(text=message, text_color=color)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        if busy:
            self.progress.pack(side="bottom", fill="x", padx=18, pady=(0, 2))
            self.progress.start()
            self._set_status(message)
        else:
            self.progress.stop()
            self.progress.pack_forget()
        for widget in (getattr(self, "login_button", None),
                       getattr(self, "activate_button", None)):
            if widget is not None and widget.winfo_exists():
                widget.configure(state="disabled" if busy else "normal")

    def _run_async(self, work: Callable[[], dict], done: Callable[[dict], None],
                   message: str) -> None:
        if self._busy:
            return
        self._set_busy(True, message)

        def runner() -> None:
            try:
                result = work()
            except Exception as exc:
                # Chi lay TEN loi, khong lay noi dung: chuoi loi hay kem ten
                # mien hoac duong dan file tren may, khong nen hien len.
                result = {"success": False,
                          "message": f"Lỗi không xác định ({type(exc).__name__})."}
            self._post(lambda: (self._set_busy(False), done(result)))

        threading.Thread(target=runner, daemon=True).start()

    # ------------------------------------------------------------------
    # Buoc 1
    # ------------------------------------------------------------------
    def _on_login(self) -> None:
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            self._set_status("Nhập đủ tên đăng nhập và mật khẩu.", "#d9534f")
            return

        def done(result: dict) -> None:
            if not result.get("success"):
                self._set_status(result.get("message", "Đăng nhập thất bại."), "#d9534f")
                return
            warning = ""
            if self._remember_account.get():
                if not self.vault.save_credentials(username, password):
                    # Khong ma hoa duoc thi thoi, khong ghi tho ra dia.
                    warning = ("Máy không dùng được DPAPI nên không ghi nhớ "
                               "được mật khẩu, lần sau vẫn phải gõ lại.")
            else:
                self.vault.clear_credentials()
            # Dat trang thai SAU khi doi buoc, vi buoc 2 khong xoa dong trang
            # thai -- dat truoc thi canh bao bi thong bao thanh cong de mat.
            self._show_key_step()
            if warning:
                self._set_status(warning, "#c48a1a")
            else:
                self._set_status("Đăng nhập thành công.", "#3a9d5d")

        self._run_async(
            lambda: self.client.authenticate(username, password),
            done, "Đang xác thực tài khoản...")

    # ------------------------------------------------------------------
    # Buoc 2
    # ------------------------------------------------------------------
    def _on_activate(self) -> None:
        key = self.key_entry.get().strip()
        if not key:
            self._set_status("Nhập key tool.", "#d9534f")
            return

        def done(result: dict) -> None:
            if not result.get("success"):
                self._set_status(result.get("message", "Kích hoạt thất bại."), "#d9534f")
                return
            remember = self._remember_key.get()
            if remember:
                self.vault.save_license_key(key)
            else:
                self.vault.clear_license_key()
            self._finish(result.get("license", {}), remember_session=remember)

        self._run_async(
            lambda: self.client.verify_license(key), done, "Đang kiểm tra key tool...")

    def _finish(self, license_data: dict, remember_session: bool) -> None:
        session = {
            "user": self.client.user_info,
            "license": license_data,
            "device_id": self.client.device_id,
            "authenticated_at": datetime.now(timezone.utc).isoformat(),
        }
        if remember_session:
            self.vault.save_session(session)
        else:
            self.vault.clear_session()
        self.session = session
        self._close()

    # ------------------------------------------------------------------
    # Tu dang nhap lai bang thong tin da luu
    # ------------------------------------------------------------------
    def _try_auto_login(self) -> None:
        """Co du tai khoan + key da luu thi vao thang, khong bat go lai.

        Van goi may chu de kiem: key co the da bi thu hoi hoac het han ke tu lan
        chay truoc, khong the tin moi file tren dia.
        """
        if self._closing or not self.winfo_exists():
            return
        session = self.vault.load_session()
        creds = self.vault.load_credentials()
        key = self.vault.load_license_key()
        username = creds.get("username", "")
        password = creds.get("password", "")
        if not (session and username and password and key):
            return

        def work() -> dict:
            auth = self.client.authenticate(username, password)
            if not auth.get("success"):
                return auth
            return self.client.verify_license(key)

        def done(result: dict) -> None:
            if result.get("success"):
                self._finish(result.get("license", {}), remember_session=True)
                return
            if result.get("mang"):
                # MAT MANG luc mo tool (vd mo cung Windows khi mang chua len): GIU
                # phien va TU THU LAI -- khong thi tool dung o man dang nhap mai mai,
                # trang dat lich/auto dang khong bao gio chay. Van KHONG cho chay offline.
                self._set_status(
                    f"{result.get('message', 'Mất mạng.')} Tự thử lại sau "
                    f"{AUTO_LOGIN_THU_LAI_GIAY} giây...", "#c48a1a")
                self.after(AUTO_LOGIN_THU_LAI_GIAY * 1000, self._try_auto_login)
                return
            # Phien cu khong dung nua: bo di de lan sau khong thu lai vo ich,
            # nhung giu tai khoan/key da go de nguoi dung khong phai nhap lai.
            self.vault.clear_session()
            self._set_status(
                f"Cần đăng nhập lại: {result.get('message', 'phiên đã hết hạn.')}",
                "#c48a1a")

        self._run_async(work, done, f"Đang đăng nhập lại bằng phiên đã lưu ({username})...")

    # ------------------------------------------------------------------
    def _close(self) -> None:
        self._closing = True
        if self._drain_id is not None:
            try:
                self.after_cancel(self._drain_id)
            except (tk.TclError, ValueError):
                pass
            self._drain_id = None
        self.destroy()

    def _quit(self) -> None:
        if self._busy and not messagebox.askyesno(
                "Đang xử lý", "Đang kết nối máy chủ. Thoát luôn?", parent=self):
            return
        self.session = None
        self._close()


def gate(parent) -> Optional[dict]:
    """Hien cong dang nhap, chan cho toi khi xong. None neu nguoi dung thoat."""
    window = LoginWindow(parent)
    parent.wait_window(window)
    return window.session


def sign_out() -> None:
    """Xoa toan bo dang nhap da luu trong ho so nguoi dung."""
    Vault().clear_all()


__all__ = ["LoginWindow", "gate", "sign_out", "licensing"]
