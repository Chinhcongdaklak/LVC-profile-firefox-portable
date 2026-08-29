"""Dang nhap tai khoan + kich hoat key tool voi may chu LVC.

Quy trinh gom hai buoc, dung nhu tool LVC Image Gen:
  1. POST /api/v1/auth/login    -> lay access_token cua tai khoan.
  2. POST /api/v1/verify/secure-verify -> xac minh key tool cho dung may nay.

Buoc 2 khong gui du lieu dang tho: payload duoc ma hoa bang ECDH (khoa cong
khai cua tool nhung o duoi) roi Fernet, va cau tra loi cua may chu phai co chu
ky ECDSA hop le moi duoc chap nhan.

Hai cho co y de "fail closed", dung sua thanh de dai:
  - Thieu chu ky hoac chu ky sai -> tu choi. Neu khong, ke dung MITM chi can
    xoa truong 'signature' la qua duoc buoc xac minh.
  - Mat mang -> tu choi, KHONG cho chay tiep offline. Neu khong, chan mang
    bang hosts/firewall la thanh mo khoa vinh vien. Muon co che do offline that
    thi phai co token do may chu ky, han su dung ro rang, kiem bang khoa cong
    khai o duoi.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
import secrets
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.fernet import Fernet

from core import config
from core import secret_store

API_URL = "https://tool.lvcmedia.vn"

#: Ma tool tren may chu -- quyet dinh key nao mo duoc tool nay.
TOOL_CODE = "lvc_firefox"
TOOL_VERSION = "1.0.0"

#: Khoa cong khai cua tool, dung de ma hoa payload (ECDH) va kiem chu ky
#: (ECDSA) cua may chu. La khoa CONG KHAI nen nam trong source la binh thuong.
TOOL_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEbPEMw/yK2v+S8hAmKtjEpRPqzekb
6KwLeFRIKxuz0AUH5UDEV/BHL7Hd1bSN/4oYo6/1DuGd76YZWyJpXHxdqw==
-----END PUBLIC KEY-----"""

_TIMEOUT = 30


class LicenseClient:
    """Noi chuyen voi may chu ban quyen."""

    def __init__(self) -> None:
        self.public_key = serialization.load_pem_public_key(
            TOOL_PUBLIC_KEY.encode(), backend=default_backend()
        )
        self.device_id = _device_id()
        self.device_info = _device_info()

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"LVCManagerProfile/{TOOL_VERSION} ({platform.system()})",
            "Accept": "application/json",
        })

        self.auth_token: Optional[str] = None
        self.user_info: Optional[dict] = None
        self.license_info: Optional[dict] = None

    # ------------------------------------------------------------------
    # Ma hoa / kiem chu ky
    # ------------------------------------------------------------------
    def _encrypt(self, data: dict) -> str:
        """Ma hoa payload bang ECDH voi khoa cong khai cua tool.

        Sinh cap khoa dung mot lan, trao doi ECDH ra khoa chung, dan khoa AES
        bang HKDF roi boc bang Fernet. Gui kem khoa cong khai tam (DER) o dau
        chuoi de may chu dan lai dung khoa do.
        """
        ephemeral = ec.generate_private_key(ec.SECP256R1(), default_backend())
        shared = ephemeral.exchange(ec.ECDH(), self.public_key)
        derived = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"license verification",  # phai khop y het voi may chu
            backend=default_backend(),
        ).derive(shared)

        token = Fernet(base64.urlsafe_b64encode(derived)).encrypt(
            json.dumps(data).encode()
        )
        pub_der = ephemeral.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return base64.b64encode(pub_der + token).decode()

    def _verify_signature(self, data: dict, signature: str) -> bool:
        """Kiem chu ky ECDSA cua may chu tren phan 'data'."""
        try:
            self.public_key.verify(
                base64.b64decode(signature),
                json.dumps(data, sort_keys=True).encode("utf-8"),
                ec.ECDSA(hashes.SHA256()),
            )
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Buoc 1: dang nhap tai khoan
    # ------------------------------------------------------------------
    def authenticate(self, username: str, password: str) -> dict:
        try:
            response = self.session.post(
                f"{API_URL}/api/v1/auth/login",
                data={"username": username, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=_TIMEOUT,
                verify=True,  # kiem chung chi TLS -- chong MITM
            )
        except requests.RequestException as exc:
            return {"success": False, "message": _network_message(exc)}

        if response.status_code != 200:
            return {"success": False,
                    "message": _server_message(response, "Sai tài khoản hoặc mật khẩu.")}

        self.auth_token = response.json().get("access_token")
        if not self.auth_token:
            return {"success": False, "message": "Máy chủ không trả về access_token."}

        self.user_info = {
            "username": username,
            "authenticated_at": datetime.now(timezone.utc).isoformat(),
        }
        return {"success": True, "user": self.user_info}

    # ------------------------------------------------------------------
    # Buoc 2: kich hoat key tool
    # ------------------------------------------------------------------
    def verify_license(self, license_key: str) -> dict:
        if not self.auth_token or not self.user_info:
            return {"success": False, "message": "Chưa đăng nhập tài khoản."}

        payload = self._encrypt({
            "license_key": license_key,
            "device_id": self.device_id,
            "device_name": platform.node(),
            "device_info": self.device_info,
            "tool_code": TOOL_CODE,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": secrets.token_hex(16),
        })
        auth_payload = self._encrypt({
            "user": self.user_info["username"],
            "user_id": _user_id_from_token(self.auth_token) or self.user_info["username"],
            "token": self.auth_token,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })

        try:
            response = self.session.post(
                f"{API_URL}/api/v1/verify/secure-verify",
                json={
                    "encrypted_payload": payload,
                    "tool_code": TOOL_CODE,
                    "auth_token": auth_payload,
                },
                timeout=_TIMEOUT,
                verify=True,
            )
        except requests.RequestException as exc:
            return {"success": False, "message": _network_message(exc)}

        if response.status_code != 200:
            return {"success": False,
                    "message": _server_message(response, "Kích hoạt thất bại.")}

        result = response.json()
        signature = result.get("signature")
        if not signature:
            return {"success": False, "message": "Máy chủ trả về dữ liệu không có chữ ký."}

        data = result.get("data", {})
        if not self._verify_signature(data, signature):
            return {"success": False, "message": "Chữ ký của máy chủ không hợp lệ."}

        if not data.get("license_valid", False):
            return {"success": False, "message": "Key tool không hợp lệ cho máy này."}

        self.license_info = data
        return {"success": True, "license": data}

    def logout(self) -> None:
        self.auth_token = None
        self.user_info = None
        self.license_info = None


# ----------------------------------------------------------------------
# Dinh danh may
# ----------------------------------------------------------------------
def _run_powershell(command: str, timeout: int = 10) -> Optional[str]:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _device_id() -> str:
    """Van tay may, on dinh giua cac lan chay tren cung mot may."""
    parts = [str(uuid.getnode()), platform.node(), platform.processor()]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _device_info() -> dict:
    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname": platform.node(),
        "tool_version": TOOL_VERSION,
    }
    if platform.system() == "Windows":
        cpu = _run_powershell(
            "Get-CimInstance -ClassName Win32_Processor | "
            "Select-Object -ExpandProperty ProcessorId"
        )
        machine = _run_powershell(
            "Get-CimInstance -ClassName Win32_ComputerSystemProduct | "
            "Select-Object -ExpandProperty UUID"
        )
        info["cpu_id"] = cpu or hashlib.md5(
            f"{uuid.getnode()}{platform.node()}".encode()).hexdigest()[:32]
        info["machine_id"] = machine or str(uuid.getnode())
    else:
        info["machine_id"] = str(uuid.getnode())
    return info


def _user_id_from_token(token: str) -> Optional[str]:
    """Doc truong 'sub' trong JWT. Chi de gan nhan, khong dung de xac thuc."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("sub")
    except Exception:
        return None


#: URL, ten mien, dia chi IP -- nhung thu khong duoc hien len giao dien.
_LEAK_RE = re.compile(
    r"(?i)\b(?:https?://|ftp://|www\.)\S+"
    r"|\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}\b"
    r"|\b\d{1,3}(?:\.\d{1,3}){3}\b"
)


def scrub(text: str) -> str:
    """Bo URL / ten mien / IP khoi thong bao truoc khi hien cho nguoi dung.

    May chu doi khi tra ve loi kem dia chi ha tang ben trong cua no. In nguyen
    van len man dang nhap la chi luon cho nguoi muon gia mao DNS biet can tro
    cai gi di dau, nen chan o day. Luu y day chi la bit lo mieng: ten mien that
    van nam trong file .exe, thu chan gia mao DNS that su la chu ky ECDSA o
    _verify_signature -- khong co khoa rieng thi khong ky gia duoc.
    """
    return _LEAK_RE.sub("…", text or "").strip()


def _network_message(exc: Exception) -> str:
    """Bao mat ket noi. Khong dung str(exc) vi chuoi cua requests co ca ten mien."""
    return ("Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại. "
            f"({type(exc).__name__})")


def _server_message(response: requests.Response, fallback: str) -> str:
    """Loi may chu tra ve, da bo dia chi, kem ma HTTP de con doi chieu voi ky thuat."""
    detail = None
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = payload.get("detail")
    except ValueError:
        pass
    if isinstance(detail, list):  # FastAPI tra loi kiem tra dau vao dang list
        detail = "; ".join(str(item.get("msg", "")) for item in detail
                           if isinstance(item, dict))

    text = scrub(str(detail)) if detail else ""
    # Boc dia chi xong ma khong con chu nao co nghia thi dung cau mac dinh.
    if len(text.replace("…", "").strip()) < 3:
        text = fallback
    return f"{text} (mã {response.status_code})"


# ----------------------------------------------------------------------
# Luu tru trong ho so nguoi dung
# ----------------------------------------------------------------------
class Vault:
    """Doc/ghi dang nhap da luu, dat trong %LOCALAPPDATA% chu khong canh tool.

    De canh tool thi moi lan cap nhat (ghi de thu muc) la mat, nen day la o
    ngoai. Noi dung deu ma hoa bang DPAPI: chep sang may khac hoac tai khoan
    Windows khac se khong doc duoc.
    """

    def __init__(self, folder: Optional[str] = None) -> None:
        self.dir = folder or config.USER_DATA_DIR
        self.credentials_path = os.path.join(self.dir, "credentials.dat")
        self.license_path = os.path.join(self.dir, "license.dat")
        self.session_path = os.path.join(self.dir, "session.dat")

    # -- tai khoan --------------------------------------------------
    def load_credentials(self) -> dict:
        data = secret_store.load_json(self.credentials_path)
        return data if isinstance(data, dict) else {}

    def save_credentials(self, username: str, password: str) -> bool:
        return secret_store.save_json(self.credentials_path, {
            "username": username,
            "password": password,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        })

    def clear_credentials(self) -> None:
        secret_store.delete(self.credentials_path)

    # -- key tool ---------------------------------------------------
    def load_license_key(self) -> str:
        data = secret_store.load_json(self.license_path)
        return data.get("license_key", "") if isinstance(data, dict) else ""

    def save_license_key(self, license_key: str) -> bool:
        return secret_store.save_json(self.license_path, {
            "license_key": license_key,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        })

    def clear_license_key(self) -> None:
        secret_store.delete(self.license_path)

    # -- phien ------------------------------------------------------
    def load_session(self) -> dict:
        data = secret_store.load_json(self.session_path)
        return data if isinstance(data, dict) else {}

    def save_session(self, session: dict) -> bool:
        return secret_store.save_json(self.session_path, session)

    def clear_session(self) -> None:
        secret_store.delete(self.session_path)

    def clear_all(self) -> None:
        self.clear_credentials()
        self.clear_license_key()
        self.clear_session()


def license_expiry_text(session: dict) -> str:
    """Mo ta han dung cua key, de hien tren thanh tieu de."""
    info = (session.get("license") or {}).get("license_info") or {}
    expires_at = info.get("expires_at")
    if not expires_at:
        return "Không giới hạn"
    try:
        text = str(expires_at).replace("Z", "+00:00")
        if "+" not in text[10:]:
            text += "+00:00"
        expiry = datetime.fromisoformat(text)
        days = (expiry - datetime.now(timezone.utc)).days
        return f"{expiry.strftime('%d/%m/%Y')} (còn {days} ngày)"
    except (ValueError, TypeError):
        return str(expires_at)


def summarize(session: dict) -> dict[str, Any]:
    """Rut gon phien thanh vai truong de hien ra giao dien."""
    info = (session.get("license") or {}).get("license_info") or {}
    return {
        "username": (session.get("user") or {}).get("username", ""),
        "key": info.get("key", ""),
        "expiry": license_expiry_text(session),
        "max_devices": info.get("max_devices", 1),
    }
