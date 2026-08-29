"""Duong dan va cau hinh chung cua tool."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict, field


def _base_dir() -> str:
    """Thu muc goc de luu du lieu (data/, profile/).

    Khi chay ban .exe (PyInstaller): lay thu muc CHUA file exe, khong lay thu muc
    tam _MEIPASS -- neu khong accounts.json/settings.json se bi ghi vao temp va
    mat sau moi lan chay. Khi chay tu ma nguon: lay thu muc 'tool'.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


TOOL_DIR = _base_dir()


def _user_data_dir() -> str:
    """Thu muc rieng cua tool trong ho so nguoi dung Windows.

    Danh cho phien dang nhap va key tool. KHONG dat canh tool: cap nhat tool la
    ghi de ca thu muc, dat o do thi moi lan cap nhat lai mat dang nhap. Ngoai ra
    %LOCALAPPDATA% moi tai khoan Windows mot ban rieng, dung voi cach DPAPI ma
    hoa theo tai khoan (xem core/secret_store.py).
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "LVC Manager Profile")


USER_DATA_DIR = _user_data_dir()


def resource_path(*parts: str) -> str:
    """Duong dan toi mot file tai nguyen di kem (vd assets/logo.png).

    Chay ca khi dong goi .exe: PyInstaller giai nen tai nguyen vao _MEIPASS.
    Uu tien _MEIPASS, roi den cay ma nguon, roi thu muc chua exe.
    """
    bases = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.append(meipass)
    bases.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    bases.append(TOOL_DIR)
    for base in bases:
        candidate = os.path.join(base, *parts)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(bases[0], *parts)
# Mac dinh gom tat ca profile vao mot cho ngay trong thu muc tool.
# Nguoi dung doi duoc trong Cai dat (vi du de sang o dia khac cho rong).
DEFAULT_ROOT = os.path.join(TOOL_DIR, "profile")

# Noi de san installer Firefox va file extension da ky. Duong dan tuy may, suy ra
# tu cho dat tool (hoac cho dat file .exe khi da dong goi).
EXTENSION_DIR = os.path.join(TOOL_DIR, "extension")
DEFAULT_XPI = os.path.join(EXTENSION_DIR, "LVCdatlich extension.xpi")
DEFAULT_PAF = os.path.join(EXTENSION_DIR, "FirefoxPortable_154.0.1_English.paf.exe")

SETTINGS_PATH = os.path.join(TOOL_DIR, "data", "settings.json")
ACCOUNTS_PATH = os.path.join(TOOL_DIR, "data", "accounts.json")

APP_FOLDER_NAME = "FirefoxPortable"
LAUNCHER_NAME = "FirefoxPortable.exe"


@dataclass
class Settings:
    profiles_root: str = DEFAULT_ROOT
    paf_path: str = ""
    #: Neu tro toi mot thu muc FirefoxPortable da giai nen, tool se nhan ban
    #: thu muc do thay vi chay lai installer (nhanh hon rat nhieu).
    template_dir: str = ""
    clone_from_template: bool = False
    allow_multiple_instances: bool = True
    #: Giao dien cua tool: "light" hoac "dark".
    appearance: str = "light"
    #: File .xpi DA DUOC MOZILLA KY, tu cai vao moi profile khi tao.
    #: Chua ky thi Firefox ban release tu choi, khong cai duoc bang cach nao ca.
    extension_xpi: str = DEFAULT_XPI
    #: Thu tu cot trong bang. De trong = dung thu tu goc trong COLUMNS.
    column_order: list = field(default_factory=list)
    #: Cac cot dang an.
    column_hidden: list = field(default_factory=list)
    #: Mau cho chuc nang "Copy tuy chon dinh dang" -- nho lai lan dung truoc.
    copy_template: str = "{id}|{password}|{recovery_mail}|{twofa}|{proxy}"
    #: So trinh duyet mo cung luc khi dang nhap bang cookie.
    login_threads: int = 5
    #: So profile duoc tao cung luc. Da do: hai installer paf.exe chay song song
    #: khong dam nhau, 2 profile mat 28 giay thay vi ~50 giay khi lam lan luot.
    create_threads: int = 3
    #: Trang mo san khi bam "Mo". De trong = mo trang chu mac dinh cua Firefox.
    start_url: str = "https://www.facebook.com/"
    #: Khi mo profile, tu nap cookie da luu neu profile chua dang nhap san.
    auto_login_cookie: bool = True
    #: Gia mui gio bang cach TIEM JS vao trang. BAT mac dinh vi Firefox tren
    #: Windows chi nhan bien moi truong TZ voi dung 5 gia tri co dinh (UTC,
    #: EST5EDT, CST6CDT, MST7MDT, PST8PDT -- da do bang cach thu 40 gia tri).
    #: Khong bat thi proxy ngoai My se de lo mui gio that cua may.
    use_tz_shim: bool = True

    @classmethod
    def load(cls) -> "Settings":
        settings = cls()
        if os.path.isfile(SETTINGS_PATH):
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
                settings = cls(**known)
            except (OSError, ValueError, TypeError):
                pass
        if not settings.paf_path or not os.path.isfile(settings.paf_path):
            settings.paf_path = settings.autodetect_paf()
        if not settings.extension_xpi:
            settings.extension_xpi = DEFAULT_XPI
        settings.ensure_root()
        return settings

    def save(self) -> None:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, ensure_ascii=False, indent=2)

    def ensure_root(self) -> None:
        for folder in (self.profiles_root, EXTENSION_DIR):
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError:
                pass

    def autodetect_paf(self) -> str:
        """Tim file FirefoxPortable_*.paf.exe o nhung cho hay de nhat.

        Uu tien thu muc 'extension' canh tool -- do la cho dat mac dinh.
        """
        if os.path.isfile(DEFAULT_PAF):
            return DEFAULT_PAF
        places = [EXTENSION_DIR, TOOL_DIR, self.profiles_root, os.path.dirname(TOOL_DIR)]
        for place in places:
            try:
                names = sorted(os.listdir(place))
            except OSError:
                continue
            for name in names:
                low = name.lower()
                if low.endswith(".paf.exe") and "firefox" in low:
                    return os.path.join(place, name)
        return ""
