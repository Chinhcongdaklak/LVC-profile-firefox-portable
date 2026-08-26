"""Dò vi tri that cua mot proxy bang cach di ra Internet qua chinh no.

Goi API dinh vi *qua proxy* thay vi tra cuu theo dia chi IP nhap tay: nhu vay
mot request la co du IP thoat, quoc gia, thanh pho, mui gio va toa do -- va so
lieu chac chan ung voi duong ra that su cua profile.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Optional

from .proxy import Proxy
from .proxy_relay import http_request

# ipwho.is di truoc: chay HTTPS va co IPv6, nen qua duoc ca nhung proxy chi cap
# duong IPv6 ra ngoai. ip-api.com chi co IPv4 va ban mien phi chi chay HTTP, de
# bi proxy tra ve 502 -- de lam nguon du phong.
_PRIMARY_HOST = "ipwho.is"
_PRIMARY_PATH = "/"
_BACKUP_HOST = "ip-api.com"
_BACKUP_PATH = "/json/?fields=status,message,countryCode,country,city,timezone,lat,lon,query"


@dataclass
class GeoInfo:
    ip: str = ""
    country: str = ""          # ma 2 chu, vi du "DE"
    country_name: str = ""
    city: str = ""
    timezone: str = ""         # ten IANA, vi du "Europe/Berlin"
    latitude: float = 0.0
    longitude: float = 0.0
    source: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.timezone or self.country)

    def summary(self) -> str:
        bits = [b for b in (self.city, self.country_name or self.country) if b]
        where = ", ".join(bits)
        parts = [p for p in (self.ip, where, self.timezone) if p]
        return " · ".join(parts)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Optional[dict]) -> "GeoInfo":
        if not raw:
            return cls()
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**known)


class GeoLookupError(RuntimeError):
    pass


def lookup(proxy: Proxy, timeout: float = 12.0) -> GeoInfo:
    """Tra ve vi tri cua duong ra Internet khi di qua ``proxy``.

    ``proxy`` rong nghia la do chinh duong mang cua may.
    """
    errors: list[str] = []

    for host, path, tls, parse in (
        (_PRIMARY_HOST, _PRIMARY_PATH, True, _parse_ipwhois),
        (_BACKUP_HOST, _BACKUP_PATH, False, _parse_ipapi),
    ):
        try:
            status, body = http_request(proxy, host, path, tls=tls, timeout=timeout)
        except Exception as exc:  # loi mang du kieu gi cung chi la "thu nguon sau"
            errors.append(f"{host}: {exc}")
            continue
        if status != 200:
            errors.append(f"{host}: HTTP {status}")
            continue
        try:
            payload = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            errors.append(f"{host}: trả về dữ liệu không đọc được")
            continue
        info = parse(payload)
        if info is None:
            errors.append(f"{host}: {payload.get('message') or 'không tra được IP này'}")
            continue
        info.source = host
        return info

    raise GeoLookupError("Không dò được vị trí proxy.\n" + "\n".join(errors))


def _parse_ipapi(payload: dict) -> Optional[GeoInfo]:
    if payload.get("status") != "success":
        return None
    return GeoInfo(
        ip=str(payload.get("query") or ""),
        country=str(payload.get("countryCode") or "").upper(),
        country_name=str(payload.get("country") or ""),
        city=str(payload.get("city") or ""),
        timezone=str(payload.get("timezone") or ""),
        latitude=float(payload.get("lat") or 0.0),
        longitude=float(payload.get("lon") or 0.0),
    )


def _parse_ipwhois(payload: dict) -> Optional[GeoInfo]:
    if not payload.get("success", True):
        return None
    timezone = payload.get("timezone") or {}
    if isinstance(timezone, dict):
        timezone = timezone.get("id") or ""
    return GeoInfo(
        ip=str(payload.get("ip") or ""),
        country=str(payload.get("country_code") or "").upper(),
        country_name=str(payload.get("country") or ""),
        city=str(payload.get("city") or ""),
        timezone=str(timezone or ""),
        latitude=float(payload.get("latitude") or 0.0),
        longitude=float(payload.get("longitude") or 0.0),
    )
