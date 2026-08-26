"""Sinh ma 2FA (TOTP - RFC 6238) bang thu vien chuan, khong can pyotp."""

from __future__ import annotations

import base64
import hmac
import re
import struct
import time
from hashlib import sha1

_CLEAN = re.compile(r"[^A-Za-z2-7=]")


def normalize_secret(secret: str) -> str:
    """Bo khoang trang / dau gach va chuan hoa ve base32 hop le."""
    if not secret:
        return ""
    secret = secret.strip()
    # Ho tro dan nguyen otpauth:// URI.
    if secret.lower().startswith("otpauth://"):
        match = re.search(r"[?&]secret=([^&]+)", secret, re.IGNORECASE)
        secret = match.group(1) if match else ""
    secret = _CLEAN.sub("", secret).upper().rstrip("=")
    padding = (-len(secret)) % 8
    return secret + "=" * padding


def generate(secret: str, at: float | None = None, digits: int = 6, period: int = 30) -> str:
    """Tra ve ma TOTP hien tai. Nem ValueError neu secret khong hop le."""
    key = base64.b32decode(normalize_secret(secret), casefold=True)
    counter = int((at if at is not None else time.time()) // period)
    digest = hmac.new(key, struct.pack(">Q", counter), sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)


def seconds_remaining(period: int = 30) -> int:
    return period - int(time.time()) % period
