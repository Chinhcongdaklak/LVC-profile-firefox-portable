"""Mo hinh proxy: parse chuoi nguoi dung nhap + sinh prefs cho Firefox."""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Optional

SCHEMES = ("http", "https", "socks5", "socks4")


@dataclass
class Proxy:
    scheme: str = "http"
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.port)

    @property
    def needs_auth(self) -> bool:
        return bool(self.username or self.password)

    @property
    def is_socks(self) -> bool:
        return self.scheme.startswith("socks")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Optional[dict]) -> "Proxy":
        if not raw:
            return cls()
        return cls(
            scheme=str(raw.get("scheme") or "http").lower(),
            host=str(raw.get("host") or ""),
            port=int(raw.get("port") or 0),
            username=str(raw.get("username") or ""),
            password=str(raw.get("password") or ""),
        )

    def display(self, mask: bool = True) -> str:
        if not self.enabled:
            return ""
        base = f"{self.scheme}://{self.host}:{self.port}"
        if self.needs_auth:
            return f"{base} ({self.username}:{'***' if mask else self.password})"
        return base

    def as_text(self) -> str:
        """Chuoi mot dong de sua lai trong o nhap."""
        if not self.enabled:
            return ""
        if self.needs_auth:
            return f"{self.scheme}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.scheme}://{self.host}:{self.port}"


_SCHEME_RE = re.compile(r"^\s*(?P<scheme>https?|socks5h?|socks4)://", re.IGNORECASE)


def parse(text: str, default_scheme: str = "http") -> Proxy:
    """Nhan nhieu dinh dang pho bien:

        host:port
        host:port:user:pass
        user:pass@host:port
        socks5://user:pass@host:port
        http://host:port
    """
    text = (text or "").strip()
    if not text:
        return Proxy()

    scheme = default_scheme
    match = _SCHEME_RE.match(text)
    if match:
        scheme = match.group("scheme").lower().replace("socks5h", "socks5")
        text = text[match.end():]

    username = password = ""
    if "@" in text:
        creds, _, text = text.rpartition("@")
        username, _, password = creds.partition(":")

    parts = [p for p in text.strip().strip("/").split(":") if p != ""]
    if len(parts) == 4 and not username:
        host, port, username, password = parts
    elif len(parts) >= 2:
        host, port = parts[0], parts[1]
    else:
        raise ValueError("Sai định dạng proxy. Ví dụ: 1.2.3.4:8080:user:pass")

    if not port.isdigit():
        raise ValueError(f"Cổng proxy không hợp lệ: {port!r}")

    if scheme not in SCHEMES:
        scheme = default_scheme
    return Proxy(scheme=scheme, host=host, port=int(port), username=username, password=password)


def build_user_js(proxy: Proxy, listen_port: int = 0, extra: Optional[dict] = None) -> str:
    """Sinh noi dung user.js dat proxy cho profile.

    ``listen_port`` > 0 nghia la dang di qua relay noi bo tren 127.0.0.1, luc do
    Firefox khong can biet user/pass -- relay tu dinh kem credential len upstream.
    """
    prefs: dict[str, object] = {
        "network.proxy.type": 0,
        # Khong dung proxy cho localhost de relay hoat dong binh thuong.
        "network.proxy.no_proxies_on": "localhost, 127.0.0.1",
        "network.proxy.allow_hijacking_localhost": False,
        "network.dns.disablePrefetch": True,
        "network.prefetch-next": False,
        # Tu dien credential proxy da luu, khong hoi lai nguoi dung.
        "signon.autologin.proxy": True,
    }

    if listen_port:
        # Di qua relay noi bo: relay luon noi chuyen kieu HTTP proxy, con loai
        # proxy that (HTTP hay SOCKS) do relay lo. Nho vay doi proxy khong phai
        # ghi lai pref nen Firefox dang mo van ap dung duoc ngay.
        prefs["network.proxy.type"] = 1
        prefs["network.proxy.http"] = "127.0.0.1"
        prefs["network.proxy.http_port"] = listen_port
        prefs["network.proxy.ssl"] = "127.0.0.1"
        prefs["network.proxy.ssl_port"] = listen_port
        prefs["network.proxy.share_proxy_settings"] = True
    elif proxy.enabled:
        prefs["network.proxy.type"] = 1
        if proxy.is_socks:
            prefs["network.proxy.socks"] = proxy.host
            prefs["network.proxy.socks_port"] = proxy.port
            prefs["network.proxy.socks_version"] = 4 if proxy.scheme == "socks4" else 5
            # Tranh ro ri DNS: de proxy phan giai ten mien thay vi may cua minh.
            prefs["network.proxy.socks_remote_dns"] = True
        else:
            prefs["network.proxy.http"] = proxy.host
            prefs["network.proxy.http_port"] = proxy.port
            prefs["network.proxy.ssl"] = proxy.host
            prefs["network.proxy.ssl_port"] = proxy.port
            prefs["network.proxy.share_proxy_settings"] = True

    if extra:
        prefs.update(extra)

    lines = [
        "// Được tạo tự động bởi Quản Lý Firefox Portable.",
        "// Mọi thay đổi thủ công sẽ bị ghi đè ở lần mở profile kế tiếp.",
    ]
    for key, value in prefs.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, (int, float)):
            rendered = str(value)
        else:
            rendered = '"{}"'.format(str(value).replace("\\", "\\\\").replace('"', '\\"'))
        lines.append(f'user_pref("{key}", {rendered});')
    return "\n".join(lines) + "\n"
