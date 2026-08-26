"""Doc chuoi cookie nguoi dung dan vao va nap thang vao cookies.sqlite cua profile.

Ho tro cac dinh dang hay gap:
  * JSON xuat tu Cookie-Editor / EditThisCookie  (mang cac object)
  * JSON boc trong object co khoa "cookies"
  * File Netscape cookies.txt (phan cach bang tab)
  * Chuoi ngan gon "c_user=100...; xs=abc..." (can biet domain mac dinh)
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Iterable, Optional

DEFAULT_TTL = 365 * 24 * 3600  # cookie khong ghi han dung -> cho song 1 nam

_SAME_SITE = {
    "no_restriction": 0,
    "none": 0,
    "unspecified": 0,
    "lax": 1,
    "strict": 2,
}


class CookieError(RuntimeError):
    pass


@dataclass
class Cookie:
    name: str
    value: str
    host: str
    path: str = "/"
    expiry: int = 0
    secure: bool = True
    http_only: bool = False
    same_site: int = 0

    def normalized_host(self, host_only: bool = False) -> str:
        host = self.host.strip()
        if not host:
            return ""
        if not host_only and not host.startswith("."):
            host = "." + host
        return host


def parse(text: str, default_domain: str = "") -> list[Cookie]:
    """Phan tich chuoi cookie thanh danh sach :class:`Cookie`."""
    text = (text or "").strip()
    if not text:
        return []

    if text[0] in "[{":
        return _parse_json(text)
    if "\t" in text:
        return _parse_netscape(text)
    return _parse_header(text, default_domain)


def _parse_json(text: str) -> list[Cookie]:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise CookieError(f"Cookie JSON không hợp lệ: {exc}") from exc

    if isinstance(data, dict):
        for key in ("cookies", "Cookies", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            raise CookieError("JSON không chứa danh sách cookie.")

    now = int(time.time())
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("Name") or "").strip()
        host = str(item.get("domain") or item.get("Domain") or item.get("host") or "").strip()
        if not name or not host:
            continue
        expiry = item.get("expirationDate") or item.get("expiry") or item.get("expires")
        try:
            expiry = int(float(expiry)) if expiry else now + DEFAULT_TTL
        except (TypeError, ValueError):
            expiry = now + DEFAULT_TTL
        same_site = item.get("sameSite")
        if isinstance(same_site, str):
            same_site = _SAME_SITE.get(same_site.lower().replace("-", "_"), 0)
        elif not isinstance(same_site, int):
            same_site = 0
        result.append(
            Cookie(
                name=name,
                value=str(item.get("value") or item.get("Value") or ""),
                host=host,
                path=str(item.get("path") or "/"),
                expiry=expiry,
                secure=bool(item.get("secure", True)),
                http_only=bool(item.get("httpOnly") or item.get("HttpOnly")),
                same_site=same_site,
            )
        )
    return result


def _parse_netscape(text: str) -> list[Cookie]:
    now = int(time.time())
    result = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        host, _include_sub, path, secure, expiry, name, value = parts[:7]
        try:
            expiry_ts = int(expiry)
        except ValueError:
            expiry_ts = now + DEFAULT_TTL
        result.append(
            Cookie(
                name=name,
                value=value,
                host=host,
                path=path or "/",
                expiry=expiry_ts or now + DEFAULT_TTL,
                secure=secure.upper() == "TRUE",
            )
        )
    return result


def _parse_header(text: str, default_domain: str) -> list[Cookie]:
    if not default_domain:
        raise CookieError(
            "Cookie dạng 'ten=gia_tri; ...' không kèm domain. "
            "Hãy nhập domain (ví dụ .facebook.com) hoặc dán cookie JSON."
        )
    now = int(time.time())
    result = []
    for chunk in text.replace("\n", ";").split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, _, value = chunk.partition("=")
        name = name.strip()
        if not name:
            continue
        result.append(
            Cookie(
                name=name,
                value=value.strip(),
                host=default_domain,
                expiry=now + DEFAULT_TTL,
            )
        )
    return result


def domains(cookies: Iterable[Cookie]) -> list[str]:
    seen = []
    for cookie in cookies:
        host = cookie.host.lstrip(".")
        if host and host not in seen:
            seen.append(host)
    return seen


def expiry_scale(connection: sqlite3.Connection, columns: set) -> int:
    """Bao nhieu don vi cua cot ``expiry`` ung voi mot giay.

    Firefox tung luu ``moz_cookies.expiry`` bang GIAY, tu ban 140 tro di doi sang
    MILI GIAY (cung dot them cot ``updateTime``, schema len phien ban 17). Ghi sai
    don vi thi Firefox doc ra la het han tu nam 1970 va bo het cookie -- profile
    van thay du cookie trong file nhung dang nhap khong an.
    """
    if "updateTime" in columns:
        return 1000
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        version = 0
    return 1000 if version >= 17 else 1


def write_to_profile(profile_dir: str, cookies: list[Cookie], replace_all: bool = False) -> int:
    """Ghi cookie vao ``profile_dir/cookies.sqlite``. Tra ve so cookie da ghi.

    Profile phai o trang thai dong -- Firefox giu khoa file khi dang chay.
    """
    if not cookies:
        return 0
    db_path = os.path.join(profile_dir, "cookies.sqlite")
    if not os.path.isfile(db_path):
        raise CookieError(
            "Chưa có cookies.sqlite. Hãy bấm 'Khởi tạo profile' (hoặc mở profile "
            "một lần rồi đóng lại) trước khi nạp cookie."
        )

    connection = sqlite3.connect(db_path, timeout=10)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(moz_cookies)")}
        if not columns:
            raise CookieError("cookies.sqlite không có bảng moz_cookies.")

        if replace_all:
            connection.execute("DELETE FROM moz_cookies")

        scale = expiry_scale(connection, columns)
        now_us = int(time.time() * 1_000_000)
        now = int(time.time())
        written = 0
        for cookie in cookies:
            values = {
                "originAttributes": "",
                "name": cookie.name,
                "value": cookie.value,
                "host": cookie.normalized_host(),
                "path": cookie.path or "/",
                "expiry": (cookie.expiry or now + DEFAULT_TTL) * scale,
                "lastAccessed": now_us,
                "creationTime": now_us,
                "updateTime": now_us,
                "isSecure": 1 if cookie.secure else 0,
                "isHttpOnly": 1 if cookie.http_only else 0,
                "inBrowserElement": 0,
                "sameSite": cookie.same_site,
                "rawSameSite": cookie.same_site,
                "schemeMap": 3,  # bitmask: 1=http, 2=https
                "isPartitionedAttributeSet": 0,
            }
            usable = {k: v for k, v in values.items() if k in columns}
            placeholders = ", ".join("?" for _ in usable)
            names = ", ".join(usable)
            connection.execute(
                f"INSERT OR REPLACE INTO moz_cookies ({names}) VALUES ({placeholders})",
                tuple(usable.values()),
            )
            written += 1
        connection.commit()
        return written
    finally:
        connection.close()


def has_login_cookie(profile_dir: str, names: Iterable[str] = ("c_user",)) -> bool:
    """Profile da co cookie dang nhap chua (mac dinh xet ``c_user`` cua Facebook).

    Dung de biet co can nap cookie khong: da dang nhap roi thi khong ghi de len,
    tranh lam mat phien Firefox tu lam moi sau khi dang nhap.
    """
    db_path = os.path.join(profile_dir, "cookies.sqlite")
    if not os.path.isfile(db_path):
        return False
    wanted = tuple(names)
    connection = sqlite3.connect(db_path, timeout=10)
    try:
        placeholders = ", ".join("?" for _ in wanted)
        row = connection.execute(
            f"SELECT COUNT(*) FROM moz_cookies "
            f"WHERE name IN ({placeholders}) AND value <> ''",
            wanted,
        ).fetchone()
        return bool(row and row[0])
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def read_from_profile(profile_dir: str) -> list[Cookie]:
    """Doc cookie hien co trong profile (dung cho chuc nang xuat cookie)."""
    db_path = os.path.join(profile_dir, "cookies.sqlite")
    if not os.path.isfile(db_path):
        return []
    connection = sqlite3.connect(db_path, timeout=10)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(moz_cookies)")}
        scale = expiry_scale(connection, columns)
        rows = connection.execute(
            "SELECT name, value, host, path, expiry, isSecure, isHttpOnly, sameSite "
            "FROM moz_cookies"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        connection.close()
    return [
        Cookie(
            name=row[0], value=row[1], host=row[2], path=row[3],
            # Mo hinh Cookie cua tool luon dung GIAY, doi lai cho khop.
            expiry=int(row[4] // scale), secure=bool(row[5]),
            http_only=bool(row[6]), same_site=row[7],
        )
        for row in rows
    ]


def to_json(cookies: list[Cookie]) -> str:
    """Xuat ra dinh dang Cookie-Editor de dan sang trinh duyet khac."""
    return json.dumps(
        [
            {
                "domain": cookie.host,
                "expirationDate": cookie.expiry,
                "hostOnly": not cookie.host.startswith("."),
                "httpOnly": cookie.http_only,
                "name": cookie.name,
                "path": cookie.path,
                "sameSite": "no_restriction" if cookie.same_site == 0 else "lax",
                "secure": cookie.secure,
                "session": False,
                "value": cookie.value,
            }
            for cookie in cookies
        ],
        ensure_ascii=False,
        indent=2,
    )
