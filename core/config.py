"""Duong dan va cau hinh chung cua tool."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict


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
    #: So profile duoc tao cung luc. Da do: hai installer paf.exe chay song song
    #: khong dam nhau, 2 profile mat 28 giay thay vi ~50 giay khi lam lan luot.
    create_threads: int = 3
    #: Trang mo san khi bam "Mo". De trong = mo trang chu mac dinh cua Firefox.
    start_url: str = "https://www.facebook.com/"
    #: Khi mo profile, tu nap cookie da luu neu profile chua dang nhap san.
    auto_login_cookie: bool = True
    #: Gia mui gio bang cach TIEM JS vao trang. Mac dinh TAT vi de bi cac he
    #: chong bot phat hien "trinh duyet bi sua". Mui gio da duoc dat o muc engine
    #: bang bien moi truong TZ luc khoi dong nen khong can shim nay.
    use_tz_shim: bool = False

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
        settings.ensure_root()
        return settings

    def save(self) -> None:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, ensure_ascii=False, indent=2)

    def ensure_root(self) -> None:
        try:
            os.makedirs(self.profiles_root, exist_ok=True)
        except OSError:
            pass

    def autodetect_paf(self) -> str:
        """Tim file FirefoxPortable_*.paf.exe o nhung cho hay de nhat.

        Uu tien THU MUC CHUA EXE (TOOL_DIR) -- mac dinh file paf.exe se nam chung
        thu muc voi file exe cua tool.
        """
        places = [TOOL_DIR, self.profiles_root, os.path.dirname(TOOL_DIR)]
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
