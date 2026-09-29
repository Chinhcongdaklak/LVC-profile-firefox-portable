"""Tao / cau hinh / mo / xoa profile Firefox Portable theo tung acc.

Bo cuc thu muc:

    <profiles_root>/
        <id_acc>/
            FirefoxPortable_154.0.1_English.paf.exe   <- ban sao installer
            FirefoxPortable/
                FirefoxPortable.exe                   <- launcher tool se goi
                FirefoxPortable.ini                   <- tool ghi de mo nhieu acc
                App/Firefox64/firefox.exe
                App/Firefox64/mozilla.cfg                <- tool ghi cau hinh proxy
                Data/profile/user.js                  <- tool ghi cau hinh proxy
                Data/profile/cookies.sqlite           <- noi nap cookie
"""

from __future__ import annotations

import json
import os
import zipfile
import shutil
import sqlite3
import subprocess
import time
from typing import Callable, Optional

from . import autoconfig
from . import geoip
from . import locales
from .config import APP_FOLDER_NAME, LAUNCHER_NAME, Settings
from .paf_installer import PafInstallError, run_paf_installer
from .proxy import Proxy, build_user_js
from .proxy_relay import RelayManager
from .store import Account, Identity
from . import procutil

CREATE_NO_WINDOW = 0x08000000
INIT_TIMEOUT = 90.0

INI_TEMPLATE = """[FirefoxPortable]
FirefoxDirectory=App\\{ffdir}
ProfileDirectory=Data\\profile
SettingsDirectory=Data\\settings
PluginsDirectory=Data\\plugins
FirefoxExecutable=firefox.exe
AdditionalParameters={extra}
LocalHomepage=
DisableSplashScreen=true
AllowMultipleInstances={multi}
DisableIntelligentStart=false
SkipCompregFix=false
RunLocally=false
AlwaysUse32Bit=false
DisableOSCheck=false
"""


class ProfileError(RuntimeError):
    pass


class ProfileManager:
    def __init__(self, settings: Settings, relays: Optional[RelayManager] = None):
        self.settings = settings
        self.relays = relays or RelayManager()

    # ---- duong dan ----------------------------------------------------
    def account_dir(self, account: Account) -> str:
        return os.path.join(self.settings.profiles_root, account.folder)

    def app_dir(self, account: Account) -> str:
        return os.path.join(self.account_dir(account), APP_FOLDER_NAME)

    def launcher(self, account: Account) -> str:
        return os.path.join(self.app_dir(account), LAUNCHER_NAME)

    def firefox_exe(self, account: Account) -> str:
        app = self.app_dir(account)
        for folder in ("Firefox64", "Firefox"):
            candidate = os.path.join(app, "App", folder, "firefox.exe")
            if os.path.isfile(candidate):
                return candidate
        return ""

    def profile_dir(self, account: Account) -> str:
        return os.path.join(self.app_dir(account), "Data", "profile")

    def is_installed(self, account: Account) -> bool:
        return os.path.isfile(self.launcher(account))

    def is_initialized(self, account: Account) -> bool:
        return os.path.isfile(os.path.join(self.profile_dir(account), "cookies.sqlite"))

    def is_running(self, account: Account) -> bool:
        # use_cache: goi hang loat (moi acc mot lan) tren luong giao dien -> dung
        # chung mot anh chup tien trinh, tranh treo khi co nhieu acc.
        return bool(procutil.find_under(self.app_dir(account), "firefox.exe", use_cache=True))

    # ---- tao profile --------------------------------------------------
    def create(
        self,
        account: Account,
        on_status: Optional[Callable[[str], None]] = None,
        overwrite: bool = False,
    ) -> str:
        """Tao thu muc profile cho acc va tra ve duong dan FirefoxPortable."""
        def status(message: str) -> None:
            if on_status:
                on_status(message)

        target = self.account_dir(account)
        if not overwrite and self.adopt_existing(account, status):
            # Da co san thu muc trung ten voi id acc -> dung luon, khong cai lai.
            self.configure(account)
            self._auto_identity(account, status)
            self._auto_extension(account, status)
            self.cleanup_installer(account, status)
            return self.app_dir(account)
        if self.is_installed(account):
            shutil.rmtree(self.app_dir(account), ignore_errors=True)

        os.makedirs(target, exist_ok=True)

        template = (self.settings.template_dir or "").strip()
        if self.settings.clone_from_template and template:
            self._clone_template(template, target, status)
        else:
            self._install_from_paf(target, status)

        self.configure(account)
        self._auto_identity(account, status)
        self._auto_extension(account, status)
        self.cleanup_installer(account, status)
        return self.app_dir(account)

    # ---- extension -----------------------------------------------------
    @staticmethod
    def read_extension_info(xpi_path: str) -> tuple[str, str]:
        """Doc (id, phien ban) tu file .xpi va kiem tra da duoc ky chua.

        Firefox ban release TU CHOI addon chua ky -- khong co cach nao vong qua
        (pref xpinstall.signatures.required bi bo qua tren kenh release). Nen
        phai bao loi ngay tu day thay vi de nguoi dung tuong da cai xong.
        """
        if not os.path.isfile(xpi_path):
            raise ProfileError(f"Không thấy file: {xpi_path}")
        try:
            with zipfile.ZipFile(xpi_path) as archive:
                names = archive.namelist()
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
            raise ProfileError(f"File .xpi hỏng hoặc không đọc được: {exc}") from exc

        if not any(name.startswith("META-INF/") for name in names):
            raise ProfileError(
                "File .xpi này CHƯA được Mozilla ký.\n"
                "Firefox bản release từ chối addon chưa ký — hãy ký qua "
                "addons.mozilla.org rồi dùng file trong thư mục 'da-ky'."
            )

        gecko = (manifest.get("browser_specific_settings")
                 or manifest.get("applications") or {}).get("gecko") or {}
        addon_id = gecko.get("id")
        if not addon_id:
            raise ProfileError(
                "manifest.json thiếu browser_specific_settings.gecko.id — "
                "Firefox cần id này để nhận addon."
            )
        return addon_id, str(manifest.get("version") or "?")

    def extension_dir(self, account: Account) -> str:
        return os.path.join(self.profile_dir(account), "extensions")

    def installed_extensions(self, account: Account) -> list[str]:
        try:
            return sorted(
                n for n in os.listdir(self.extension_dir(account))
                if n.lower().endswith(".xpi")
            )
        except OSError:
            return []

    def install_extension(self, account: Account, xpi_path: str) -> str:
        """Chep addon da ky vao ``<profile>/extensions/<id>.xpi``.

        Firefox quet thu muc nay luc khoi dong, nen phai cai khi trinh duyet
        DANG DONG; dang mo thi no ghi de lai danh sach addon cua no.
        """
        if not self.is_installed(account):
            raise ProfileError(f"Chưa cài profile cho acc '{account.id}'.")
        addon_id, version = self.read_extension_info(xpi_path)

        target_dir = self.extension_dir(account)
        os.makedirs(target_dir, exist_ok=True)
        shutil.copyfile(xpi_path, os.path.join(target_dir, addon_id + ".xpi"))
        return f"{addon_id} v{version}"

    def remove_extension(self, account: Account, addon_id: str) -> bool:
        path = os.path.join(self.extension_dir(account), addon_id + ".xpi")
        try:
            os.remove(path)
            return True
        except OSError:
            return False

    def _auto_extension(self, account: Account, status: Callable[[str], None]) -> None:
        """Cai san extension khi vua tao profile, neu da chi dinh file .xpi."""
        xpi = (getattr(self.settings, "extension_xpi", "") or "").strip()
        if not xpi:
            return
        try:
            status(f"Cài extension: {self.install_extension(account, xpi)}")
        except ProfileError as exc:
            status(f"Không cài được extension: {exc}")

    def find_existing_launcher(self, account: Account) -> str:
        """Tim ``FirefoxPortable.exe`` co san trong thu muc mang ten id acc.

        Nhan ca vai bo cuc hay gap khi nguoi dung tu chep thu muc vao:
          ``<acc>/FirefoxPortable/FirefoxPortable.exe``  (chuan)
          ``<acc>/FirefoxPortable.exe``                  (chep thang noi dung ra)
          ``<acc>/<ten khac>/FirefoxPortable.exe``       (thu muc bi doi ten)
        """
        base = self.account_dir(account)
        for candidate in (
            os.path.join(base, APP_FOLDER_NAME, LAUNCHER_NAME),
            os.path.join(base, LAUNCHER_NAME),
        ):
            if os.path.isfile(candidate):
                return candidate
        try:
            names = sorted(os.listdir(base))
        except OSError:
            return ""
        for name in names:
            candidate = os.path.join(base, name, LAUNCHER_NAME)
            if os.path.isfile(candidate):
                return candidate
        return ""

    def adopt_existing(self, account: Account, status: Callable[[str], None]) -> bool:
        """Dung lai profile da co san thay vi cai moi. Tra ve True neu dung duoc.

        Bo cuc khong chuan se duoc don ve ``<acc>/FirefoxPortable/`` de moi cho
        con lai trong tool khong phai doan duong dan.
        """
        launcher = self.find_existing_launcher(account)
        if not launcher:
            return False

        base = self.account_dir(account)
        wanted = self.app_dir(account)
        source = os.path.dirname(launcher)

        if os.path.normcase(source) == os.path.normcase(wanted):
            status("Đã có sẵn profile trong thư mục, dùng luôn.")
            return True

        if os.path.normcase(source) == os.path.normcase(base):
            # FirefoxPortable.exe nam thang trong thu muc acc: gom tat ca vao mot
            # thu muc con. Phai qua thu muc tam vi khong the doi ten mot thu muc
            # thanh chinh thu muc con cua no.
            status("Thấy Firefox nằm ngay trong thư mục acc, dọn vào đúng chỗ...")
            staging = os.path.join(base, "_FirefoxPortable_tam")
            if os.path.exists(staging):
                shutil.rmtree(staging, ignore_errors=True)
            os.makedirs(staging)
            for name in os.listdir(base):
                if name == "_FirefoxPortable_tam":
                    continue
                shutil.move(os.path.join(base, name), os.path.join(staging, name))
            os.rename(staging, wanted)
        else:
            status(f"Thấy profile ở '{os.path.basename(source)}', đổi về tên chuẩn...")
            if os.path.exists(wanted):
                shutil.rmtree(wanted, ignore_errors=True)
            os.rename(source, wanted)

        return os.path.isfile(self.launcher(account))

    def _auto_identity(self, account: Account, status: Callable[[str], None]) -> None:
        """Khop mui gio/ngon ngu theo proxy ngay khi tao profile, neu chua co.

        Dò khong duoc thi thoi -- khong duoc lam hong viec tao profile.
        """
        if not account.auto_identity or account.get_identity().enabled:
            return
        if not account.get_proxy().enabled:
            return
        status("Đang dò múi giờ và ngôn ngữ theo proxy...")
        try:
            identity = self.match_identity(account)
        except Exception as exc:
            status(f"Không dò được vị trí proxy ({exc}). Giữ múi giờ mặc định.")
            return
        status(f"Múi giờ: {identity.summary()}")

    def move_to_root(
        self,
        accounts: list[Account],
        old_root: str,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> tuple[int, list[str]]:
        """Chuyen thu muc profile tu ``old_root`` sang thu muc goc dang dat.

        Tra ve ``(so_thu_muc_da_chuyen, danh_sach_loi)``. Trinh duyet dang mo se
        bi dong truoc vi Windows khong cho doi ten thu muc dang co file bi khoa.
        """
        new_root = self.settings.profiles_root
        os.makedirs(new_root, exist_ok=True)
        moved = 0
        errors: list[str] = []

        for account in accounts:
            source = os.path.join(old_root, account.folder)
            if not os.path.isdir(source):
                continue
            destination = os.path.join(new_root, account.folder)
            if os.path.exists(destination):
                errors.append(f"{account.id}: nơi mới đã có thư mục trùng tên")
                continue
            if on_status:
                on_status(f"Đang chuyển {account.id}...")
            # Duong dan trong self.* da tro sang goc moi, nen dong theo duong dan cu.
            procutil.terminate_under(source, "firefox.exe")
            self.relays.stop(account.id)
            time.sleep(0.5)
            try:
                shutil.move(source, destination)
                moved += 1
            except OSError as exc:
                errors.append(f"{account.id}: {exc}")
        return moved, errors

    # Thu muc thuan tuy la cache: xoa di Firefox tu tao lai, khong mat dang nhap.
    # KHONG dung toi cookies.sqlite, logins.json, storage/ (localStorage,
    # IndexedDB) hay sessionstore -- do la cho giu phien dang nhap.
    CACHE_DIRS = (
        "cache2",
        "startupCache",
        "shader-cache",
        "jumpListCache",
        "thumbnails",
        "OfflineCache",
    )

    def cache_paths(self, account: Account) -> list[str]:
        """Cac thu muc cache cua profile, ke ca Cache API cua tung trang web."""
        profile = self.profile_dir(account)
        found = [
            os.path.join(profile, name)
            for name in self.CACHE_DIRS
            if os.path.isdir(os.path.join(profile, name))
        ]
        # storage/default/<trang>/cache  -- Cache API, nam canh IndexedDB nen
        # phai lay dung thu muc con 'cache', khong duoc xoa ca thu muc trang.
        default = os.path.join(profile, "storage", "default")
        try:
            origins = os.listdir(default)
        except OSError:
            origins = []
        for origin in origins:
            candidate = os.path.join(default, origin, "cache")
            if os.path.isdir(candidate):
                found.append(candidate)
        return found

    @staticmethod
    def _dir_size(path: str) -> int:
        total = 0
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
        return total

    def cache_size(self, account: Account) -> int:
        return sum(self._dir_size(path) for path in self.cache_paths(account))

    def clear_cache(self, account: Account) -> int:
        """Xoa cache cua profile va tra ve so byte giai phong duoc.

        Nem ``ProfileError`` neu trinh duyet dang mo -- Windows khoa file cache
        nen xoa luc dang chay se chi xoa duoc mot nua, de lam hong profile.
        """
        if not self.is_installed(account):
            raise ProfileError(f"Chưa cài profile cho acc '{account.id}'.")
        if self.is_running(account):
            raise ProfileError(
                f"Firefox của acc '{account.id}' đang chạy. Đóng lại rồi xoá cache."
            )

        freed = 0
        for path in self.cache_paths(account):
            size = self._dir_size(path)
            shutil.rmtree(path, ignore_errors=True)
            if not os.path.isdir(path):
                freed += size
            else:
                # Con sot lai vai file bi khoa -- tinh phan da xoa duoc.
                freed += size - self._dir_size(path)
        return freed

    def installer_copies(self, account: Account) -> list[str]:
        """Cac ban sao ``*.paf.exe`` con sot lai trong thu muc cua acc."""
        target = self.account_dir(account)
        try:
            names = os.listdir(target)
        except OSError:
            return []
        return [
            os.path.join(target, name)
            for name in names
            if name.lower().endswith(".paf.exe")
        ]

    def cleanup_installer(
        self, account: Account, on_status: Optional[Callable[[str], None]] = None
    ) -> int:
        """Xoa ban sao installer sau khi da cai xong. Tra ve so byte giai phong duoc.

        Chi xoa khi profile that su da cai thanh cong -- neu khong thi con file
        de con cai lai duoc.
        """
        if not self.is_installed(account):
            return 0
        freed = 0
        for path in self.installer_copies(account):
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            for attempt in range(3):
                try:
                    os.remove(path)
                    freed += size
                    break
                except OSError:
                    # Windows co the con giu file mot nhip sau khi installer thoat.
                    if attempt == 2:
                        break
                    time.sleep(0.5)
        if freed and on_status:
            on_status(f"Đã xoá file cài đặt, giải phóng {freed / 1024 / 1024:.0f} MB.")
        return freed

    def _clone_template(self, template: str, target: str, status: Callable[[str], None]) -> None:
        if not os.path.isfile(os.path.join(template, LAUNCHER_NAME)):
            raise ProfileError(
                f"Thư mục mẫu không hợp lệ (thiếu {LAUNCHER_NAME}): {template}"
            )
        destination = os.path.join(target, APP_FOLDER_NAME)
        status("Đang nhân bản từ thư mục mẫu...")
        shutil.copytree(template, destination, dirs_exist_ok=True)
        # Profile cua acc phai sach, khong keo theo du lieu dang nhap cua ban mau.
        shutil.rmtree(os.path.join(destination, "Data"), ignore_errors=True)
        os.makedirs(os.path.join(destination, "Data"), exist_ok=True)
        status("Nhân bản xong.")

    def _install_from_paf(self, target: str, status: Callable[[str], None]) -> None:
        paf = (self.settings.paf_path or "").strip()
        if not paf or not os.path.isfile(paf):
            raise ProfileError(
                "Chưa chỉ định file FirefoxPortable_*.paf.exe. Vào Cài đặt để chọn."
            )
        local_paf = os.path.join(target, os.path.basename(paf))
        if not os.path.isfile(local_paf):
            status("Đang chép installer vào thư mục acc...")
            shutil.copy2(paf, local_paf)
        try:
            run_paf_installer(local_paf, target, on_status=status)
        except PafInstallError as exc:
            raise ProfileError(str(exc)) from exc

    # ---- cau hinh -----------------------------------------------------
    def configure(self, account: Account, extra_prefs: Optional[dict] = None) -> None:
        """Ghi FirefoxPortable.ini va user.js (bao gom proxy) cho acc."""
        if not self.is_installed(account):
            raise ProfileError(f"Chưa cài profile cho acc '{account.id}'.")

        self._write_ini(account)

        profile = self.profile_dir(account)
        self._seed_data_folder(account)
        os.makedirs(profile, exist_ok=True)

        proxy = account.get_proxy()

        # Proxy duoc bam thang vao thu muc app bang AutoConfig (mozilla.cfg):
        # pref bi khoa cung nen khong the tat nham, va user/pass duoc nap san vao
        # Password Manager nen khong bao gio hien hop thoai hoi mat khau.
        #
        # Truoc day Firefox tro vao relay noi bo tren 127.0.0.1. Cach do hong khi
        # mo trinh duyet luc tool da tat hoac vua khoi dong lai, vi relay chi song
        # trong tien trinh tool va moi lan lai nghe mot cong ngau nhien khac ->
        # user.js con tro vao cong da chet. AutoConfig khong phu thuoc tool.
        self.relays.stop(account.id)
        # Ten cua so lay theo ten thu muc chua profile, de mo nhieu acc cung luc
        # con phan biet duoc cua so nao cua acc nao.
        autoconfig.install(
            self.app_dir(account),
            proxy,
            label=account.folder,
            identity=account.get_identity(),
            use_shim=getattr(self.settings, "use_tz_shim", False),
            user_agent=(account.extra.get("user_agent") or "").strip(),
        )
        # Moi profile mot icon rieng tren thanh tac vu (khong gom chung).
        self._set_taskbar_id(account)

        # user.js chi con la ban sao du phong cho cac ban Firefox khong doc duoc
        # AutoConfig; pref bi khoa trong mozilla.cfg luon thang neu ca hai cung co.
        with open(os.path.join(profile, "user.js"), "w", encoding="utf-8") as fh:
            fh.write(build_user_js(proxy, 0, extra_prefs))

    def set_proxy(self, account: Account, proxy: Proxy) -> str:
        """Doi proxy cua acc va ap dung ngay khi co the.

        Tra ve mot trong:
          ``"live"``     - trinh duyet dang mo va da doi xong, khong can lam gi them
          ``"restart"``  - trinh duyet dang mo nhung phai mo lai moi an
          ``"saved"``    - trinh duyet dang dong, se ap dung o lan mo sau
        """
        account.set_proxy(proxy)
        if not self.is_installed(account):
            return "saved"

        running = self.is_running(account)
        self.configure(account)
        if not running:
            return "saved"
        # Pref bi khoa trong mozilla.cfg chi duoc doc luc Firefox khoi dong, nen
        # trinh duyet dang mo phai mo lai moi an proxy moi.
        return "restart"

    def match_identity(self, account: Account) -> Identity:
        """Dò quoc gia that cua proxy roi dat mui gio va ngon ngu cho khop.

        Nem ``GeoLookupError`` neu khong dò duoc. Chi ghi vao profile khi da cai.
        """
        info = geoip.lookup(account.get_proxy())
        identity = Identity(
            timezone=info.timezone,
            accept_languages=locales.accept_languages(info.country),
            country=info.country,
            city=info.city,
            ip=info.ip,
            checked_at=time.strftime("%Y-%m-%d %H:%M"),
        )
        account.set_identity(identity)
        if self.is_installed(account):
            self.configure(account)
        return identity

    def clear_identity(self, account: Account) -> None:
        """Bo khop mui gio/ngon ngu, tra profile ve mac dinh cua may."""
        account.set_identity(None)
        if self.is_installed(account):
            self.configure(account)

    def login_probe_path(self, account: Account) -> str:
        """File ket qua do chinh trinh duyet ghi ra (xem autoconfig._PROBE_JS)."""
        return os.path.join(self.profile_dir(account), autoconfig.PROBE_NAME)

    def clear_login_probe(self, account: Account) -> None:
        """Xoa ket qua cu -- phai goi TRUOC khi mo, khong la doc nham lan truoc."""
        try:
            os.remove(self.login_probe_path(account))
        except OSError:
            pass

    def read_login_probe(self, account: Account):
        """Tra ve ``(vao_duoc, da_chot)``, hoac ``None`` neu trinh duyet chua bao."""
        try:
            with open(self.login_probe_path(account), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return bool(data.get("ok")), bool(data.get("final"))

    def read_login_probe_why(self, account: Account) -> str:
        """Truong ``why`` cua ket qua tham do (vd URL checkpoint/login) -- de bao ly do cookie chet."""
        try:
            with open(self.login_probe_path(account), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return ""
        return str(data.get("why") or "") if isinstance(data, dict) else ""

    def read_probe_cookies(self, account: Account) -> str:
        """Chuoi cookie facebook do trinh duyet tu bao ra khi thay dang nhap.

        Rong neu chua co ket qua, ket qua bao "chet", hoac probe doi cu chua kem
        cookie. Dung de LAY LAI cookie sau khi nguoi dung dang nhap tay: doc kho
        cookie trong bo nho nen moi ngay, khong dinh do tre ghi cookies.sqlite.
        """
        try:
            with open(self.login_probe_path(account), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return ""
        if not isinstance(data, dict) or not data.get("ok"):
            return ""
        return str(data.get("cookies") or "")

    def verify_cookie_login(
        self,
        account: Account,
        timeout: float = 25.0,
        settle: float = 0.0,
        fallback_after: float = 12.0,
    ) -> bool:
        """Cookie vua nap co vao duoc Facebook khong -- biet cang som cang tot.

        Duong chinh: trinh duyet tu bao ra file ``qlfp-login.json`` ngay khi trang
        Facebook tai xong (doc kho cookie trong bo nho, xem autoconfig._PROBE_JS).
        Thuong co ket qua sau 2-5 giay ke tu luc mo.

        Duong du phong: profile cu chua co doan script do (hoac mo bang duong khac)
        thi quay ve cach cu -- theo doi ``cookies.sqlite``, vi Facebook XOA
        ``c_user``/``xs`` khoi profile khi phien da chet. Cach nay cham hon nhieu
        vi Firefox ghi cookie xuong dia theo dot.
        """
        database = os.path.join(self.profile_dir(account), "cookies.sqlite")
        deadline = time.time() + timeout
        if settle > 0:
            time.sleep(min(settle, timeout))
        fallback_at = time.time() + min(fallback_after, timeout)

        while True:
            probe = self.read_login_probe(account)
            if probe is not None:
                vao_duoc, da_chot = probe
                if not vao_duoc:
                    # Checkpoint MEM: agent fbskip dang bam "Bo qua" -> cho trang chuyen tiep
                    # (probe se bao lai ok). Het gio van checkpoint -> chet.
                    if "checkpoint" in self.read_login_probe_why(account).lower() and time.time() < deadline:
                        time.sleep(0.5)
                        continue
                    return False        # chac chan chet -> khoi cho them
                if da_chot:
                    return True         # da xem lai mot lan nua -> vao duoc that

            now = time.time()
            if now >= deadline:
                # Het gio: lay tam ket qua chua chot, khong co thi doc file cookie.
                return probe[0] if probe is not None else self._has_login_cookie(database)
            # Trinh duyet im lang qua lau -> nga sang cach cu de con biet duong.
            if probe is None and now >= fallback_at and not self._has_login_cookie(database):
                return False
            time.sleep(0.25)

    @staticmethod
    def _has_login_cookie(database: str) -> bool:
        """Con ``c_user`` trong cookies.sqlite khong (duong du phong, cham)."""
        if not os.path.isfile(database):
            return False
        try:
            with sqlite3.connect(database, timeout=5) as connection:
                found = connection.execute(
                    "SELECT 1 FROM moz_cookies WHERE name = 'c_user' LIMIT 1"
                ).fetchone()
            return bool(found)
        except sqlite3.Error:
            # Firefox dang ghi do -> chua ket luan duoc, coi nhu con.
            return True

    def restart(self, account: Account, wait: float = 2.0) -> None:
        """Dong roi mo lai trinh duyet cua acc de ap dung cau hinh moi."""
        self.close(account, wait=max(wait, 5.0))
        self.launch(account)

    def _set_taskbar_id(self, account: Account) -> None:
        """Gan AppUserModelID rieng cho profile nay -> Windows tach thanh icon rieng.

        Firefox doc ID nay tu HKCU\\Software\\Mozilla\\Firefox\\TaskBarIDs, khoa la
        duong dan thu muc cai (chua firefox.exe). Launcher le ra ghi CityHash rieng
        nhung plugin thieu nen moi profile roi ve cung chuoi "FirefoxPortable" ->
        bi gom chung mot icon. Tu ghi lai gia tri duy nhat de tach ra.
        """
        try:
            import winreg
        except ImportError:
            return  # khong phai Windows
        unique = "QLFP." + account.folder
        app = self.app_dir(account)
        dirs = []
        for folder in ("Firefox64", "Firefox"):
            candidate = os.path.join(app, "App", folder)
            if os.path.isfile(os.path.join(candidate, "firefox.exe")):
                dirs.append(candidate)
        if not dirs:
            return
        try:
            key = winreg.CreateKey(
                winreg.HKEY_CURRENT_USER, r"Software\Mozilla\Firefox\TaskBarIDs"
            )
            try:
                for path in dirs:
                    winreg.SetValueEx(key, path, 0, winreg.REG_SZ, unique)
            finally:
                winreg.CloseKey(key)
        except OSError:
            pass

    def firefox_dir_name(self, account: Account) -> str:
        """Ten thu muc chua firefox.exe (``Firefox64`` hoac ``Firefox``).

        Ban PAF 154 chi giai nen vao ``App/Firefox64``, con ``App/Firefox`` de
        rong -- ini tro nham vao thu muc rong se de launcher phai tu do lai.
        """
        app = self.app_dir(account)
        for folder in ("Firefox64", "Firefox"):
            if os.path.isfile(os.path.join(app, "App", folder, "firefox.exe")):
                return folder
        return "Firefox64"

    def _write_ini(self, account: Account) -> None:
        path = os.path.join(self.app_dir(account), "FirefoxPortable.ini")
        content = INI_TEMPLATE.format(
            ffdir=self.firefox_dir_name(account),
            multi="true" if self.settings.allow_multiple_instances else "false",
            extra="",
        )
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    def _seed_data_folder(self, account: Account) -> None:
        """Chep san App\\DefaultData sang Data giong viec launcher lam lan dau chay."""
        app = self.app_dir(account)
        default_data = os.path.join(app, "App", "DefaultData")
        if not os.path.isdir(default_data):
            return
        for name in os.listdir(default_data):
            source = os.path.join(default_data, name)
            destination = os.path.join(app, "Data", name)
            if os.path.isdir(source) and not os.path.isdir(destination):
                shutil.copytree(source, destination)

    # ---- khoi tao / mo / dong -----------------------------------------
    def initialize(
        self,
        account: Account,
        on_status: Optional[Callable[[str], None]] = None,
        timeout: float = INIT_TIMEOUT,
    ) -> None:
        """Chay Firefox an mot lan de profile sinh du file (nhat la cookies.sqlite).

        Bat buoc phai lam truoc khi nap cookie vao acc moi tao.
        """
        def status(message: str) -> None:
            if on_status:
                on_status(message)

        if self.is_initialized(account):
            return
        exe = self.firefox_exe(account)
        if not exe:
            raise ProfileError(f"Không tìm thấy firefox.exe trong {self.app_dir(account)}.")

        self.configure(account)
        profile = self.profile_dir(account)
        status("Đang khởi tạo profile lần đầu...")
        process = subprocess.Popen(
            [exe, "-profile", profile, "-headless", "-no-remote", "about:blank"],
            creationflags=CREATE_NO_WINDOW,
        )
        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                if self.is_initialized(account):
                    time.sleep(1.5)  # cho Firefox ghi xong schema
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.5)
        finally:
            if process.poll() is None:
                process.kill()
            procutil.terminate_under(self.app_dir(account), "firefox.exe")
        # Firefox can vai tram ms de nha khoa file sau khi bi dong.
        time.sleep(1.0)
        if not self.is_initialized(account):
            raise ProfileError("Khởi tạo profile không thành công (chưa thấy cookies.sqlite).")
        status("Khởi tạo xong.")

    def launch(self, account: Account, url: str = "",
               on_status: Optional[Callable[[str], None]] = None) -> subprocess.Popen:
        """Mo profile bang cach chay THANG firefox.exe (khong qua launcher).

        Vi sao khong qua FirefoxPortable.exe: launcher ghi de gia tri TaskBarID
        trong registry ve chung mot chuoi "FirefoxPortable" moi lan chay, nen moi
        profile bi Windows gom chung MOT icon tren thanh tac vu. Chay thang
        firefox.exe thi khong ai ghi de -> moi profile giu duoc AppUserModelID
        rieng (xem _set_taskbar_id) va tach thanh icon rieng.

        ``url`` (neu co) mo thang tab do khi khoi dong (vd vao Facebook).

        Acc CHUA co profile -> TU DONG tao roi mo (yeu cau nguoi dung 2026-09-17):
        mo profile / dang nhap cookie|web / bat chuyen nghiep / dang bai / tao
        fanpage deu tu tao profile khi thieu; da co thi chay binh thuong.
        """
        if not self.is_installed(account):
            if on_status:
                on_status(f"Acc {account.id}: chưa có profile — tự tạo trước khi mở...")
            self.create(account, on_status=on_status)

        exe = self.firefox_exe(account)
        if not exe:
            raise ProfileError(f"Không tìm thấy firefox.exe trong {self.app_dir(account)}.")

        self.configure(account)          # ghi mozilla.cfg, ini, AUMID rieng...
        self._set_taskbar_id(account)    # chac chan AUMID rieng truoc khi mo

        profile = self.profile_dir(account)
        os.makedirs(profile, exist_ok=True)
        # -no-remote + -profile: moi profile la mot phien doc lap, chay song song.
        args = [exe, "-no-remote", "-profile", profile]
        if url.strip():
            args.append(url.strip())

        # KHONG dat bien TZ: da test tren Windows, Firefox lay mui gio tu HE DIEU
        # HANH chu khong doc TZ; ep TZ chi lam Firefox bao mot mui gio tong hop
        # kieu "Etc/GMT-7" -- gia tri gan nhu khong nguoi that nao co, thanh ra
        # lai LO hon. De trong thi Firefox bao mui gio OS sach (vd Asia/Ho_Chi_Minh).
        procutil.clear_snapshot_cache()     # trang thai "▶" tuoi ngay sau khi mo
        return subprocess.Popen(args, cwd=os.path.dirname(exe))

    def launch_debug(self, account: Account, url: str, port: int,
                     on_status: Optional[Callable[[str], None]] = None) -> subprocess.Popen:
        """Mo profile kem cong WebDriver BiDi (--remote-debugging-port) de tool
        chay JS boc bai nhom. Dong phien cu truoc vi 1 profile chi chay 1 instance.

        Acc chua co profile -> tu dong tao truoc khi mo (nhu ``launch``)."""
        if not self.is_installed(account):
            if on_status:
                on_status(f"Acc {account.id}: chưa có profile — tự tạo trước khi mở...")
            self.create(account, on_status=on_status)
        exe = self.firefox_exe(account)
        if not exe:
            raise ProfileError(f"Không tìm thấy firefox.exe cho acc '{account.id}'.")
        self.close(account, wait=3.0)
        self.configure(account)
        self._set_taskbar_id(account)
        profile = self.profile_dir(account)
        args = [exe, "-no-remote", "-profile", profile,
                "--remote-debugging-port", str(port), url]
        procutil.clear_snapshot_cache()     # trang thai "▶" tuoi ngay sau khi mo
        return subprocess.Popen(args, cwd=os.path.dirname(exe))

    def close(self, account: Account, wait: float = 0.0) -> int:
        """Dong trinh duyet cua acc. ``wait`` > 0 thi cho toi khi that su dong han.

        Vi sao can cho: TerminateProcess chi RA LENH ket lieu roi tra ve ngay.
        Neu mo acc ke tiep lien thi trinh duyet cu van con tren man hinh -- chay
        5 luong ma thay 7-8 cua so chinh la vi vay.
        """
        killed = procutil.terminate_under(self.app_dir(account), "firefox.exe")
        self.relays.stop(account.id)
        if wait > 0:
            self.wait_closed(account, wait)
        procutil.clear_snapshot_cache()     # trang thai "▶" tuoi ngay sau khi dong
        return killed

    def running_count(self) -> int:
        """So tien trinh firefox.exe dang chay tu thu muc profile cua tool."""
        return len(procutil.find_under(self.settings.profiles_root, "firefox.exe"))

    def close_all(self, wait: float = 10.0) -> int:
        """Ket lieu MOI Firefox do tool mo, khong can biet cua acc nao.

        Quet theo thu muc goc chu khong duyet tung acc: nhanh hon, va don duoc ca
        profile co tren dia ma khong con trong bang.
        """
        root = self.settings.profiles_root
        killed = procutil.terminate_under(root, "firefox.exe")
        self.relays.stop_all()
        deadline = time.time() + wait
        while procutil.find_under(root, "firefox.exe"):
            if time.time() >= deadline:
                break
            procutil.terminate_under(root, "firefox.exe")   # tien trinh con moi sinh
            time.sleep(0.25)
        return killed

    def wait_closed(self, account: Account, timeout: float = 10.0) -> bool:
        """Cho toi khi khong con tien trinh nao cua acc nay chay nua.

        Firefox de lai tien trinh noi dung con; co cai vua sinh ra dung luc minh
        chup danh sach nen thoat duoc lan ket lieu dau. Ket lieu lai sau moi vong
        cho toi khi sach han.
        """
        app = self.app_dir(account)
        deadline = time.time() + timeout
        while True:
            if not procutil.find_under(app, "firefox.exe"):
                return True
            if time.time() >= deadline:
                return False
            procutil.terminate_under(app, "firefox.exe")
            time.sleep(0.25)

    def delete(self, account: Account, remove_folder: bool = True) -> None:
        self.close(account)
        if remove_folder:
            target = self.account_dir(account)
            if os.path.isdir(target):
                time.sleep(0.5)  # cho tien trinh vua bi dong nha khoa file
                shutil.rmtree(target, ignore_errors=True)

    def folder_size(self, account: Account) -> int:
        return self._dir_size(self.account_dir(account))
