"""Bien doi noi dung bang AI ("xao bai"): caption + anh. Video giu nguyen.

Nha cung cap:
  * "mock"   -- khong goi mang, dung THU NGHIEM luong (xao chu don gian, anh copy).
  * "gemini" -- Google Gemini qua REST. NHIEU API KEY (moi dong 1 key) + TU DONG
                XOAY MODEL. Port logic tu tool "phan tich" (video slide):
                  - ApiKeyPool: key nao het quota ngay thi bo, xoay key khac.
                  - Xoay model: hoi API danh sach model, uu tien flash-lite ->
                    flash -> pro; model bi rate-limit theo phut thi doi model khac.
                  - Phan loai loi: quota (het ngay) / rate (theo phut) / invalid.

transform_text -> chuoi moi. transform_image -> ghi file dich, tra ve True/False.
"""

from __future__ import annotations

import base64
import json
import os
import random
import re
import shutil
import threading
import time
import urllib.request
from dataclasses import dataclass, field, asdict


class AiError(RuntimeError):
    pass


DEFAULT_CAPTION_PROMPT = (
    "Viết lại nội dung sau bằng cách diễn đạt khác, GIỮ NGUYÊN ý nghĩa và thông "
    "tin, giọng tự nhiên gần gũi, có thể thêm emoji hợp lý. CHỈ trả về nội dung "
    "đã viết lại, không giải thích, không thêm dấu ngoặc."
)
DEFAULT_IMAGE_PROMPT = (
    "Đổi phần chữ trong ảnh sang cách diễn đạt khác nhưng giữ nguyên ý; giữ "
    "nguyên bố cục, màu sắc, chủ thể. Nếu có watermark hoặc tên người khác thì xoá."
)

# "gemini-2.0-flash" da bi Google go (404, 2026-09); alias *-latest tu theo model moi.
GEMINI_TEXT_MODEL = "gemini-flash-latest"
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"
_GEN = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_LIST = "https://generativelanguage.googleapis.com/v1beta/models"

# ---- phan loai loi (port tu gemini_client) ------------------------------
_429 = ("resource_exhausted", "429", "quota", "rate limit", "ratelimit",
        "exceeded", "too many requests")
_DAILY = ("per day", "perday", "per-day", "daily", "requests per day", "/day")
_INVALID = ("api key not valid", "api_key_invalid", "invalid api key",
            "permission_denied", "unauthenticated", "401", "403")
_RE_CHO = re.compile(r"retry[_-]?delay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s?", re.I)
# Model KHONG dung de xao chu (sinh anh/nhac/embedding...) -- loc khoi xoay model text.
_NOT_TEXT = ("embedding", "aqa", "imagen", "veo", "lyria", "tts", "gemma",
             "robotics", "computer-use", "live", "native-audio", "image",
             "nano-banana", "deep-research", "transcribe")


def classify_api_error(exc) -> str:
    """'quota' (het ngay) | 'rate' (theo phut) | 'invalid' (key sai) | 'error'."""
    s = str(exc).lower()
    if any(m in s for m in _INVALID) and not any(m in s for m in _429):
        return "invalid"
    if any(m in s for m in _429):
        return "quota" if any(m in s for m in _DAILY) else "rate"
    if any(m in s for m in _INVALID):
        return "invalid"
    return "error"


def retry_delay(exc) -> float:
    m = _RE_CHO.search(str(exc or ""))
    if m:
        try:
            return max(0.0, float(m.group(1)))
        except ValueError:
            pass
    return 0.0


def parse_api_keys(text: str) -> list:
    """Moi dong 1 key (bo phan '# ghi chu'), bo trung, giu thu tu."""
    out, seen = [], set()
    for line in (text or "").splitlines():
        k = line.split("#", 1)[0].strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


class ApiKeyPool:
    """Xoay nhieu API key: key nao het quota NGAY thi loai, chuyen key ke tiep."""

    def __init__(self, keys):
        seen, self._keys = set(), []
        for k in keys:
            k = (k or "").strip()
            if k and k not in seen:
                seen.add(k)
                self._keys.append(k)
        self._dead = set()
        self._i = 0
        self._lock = threading.Lock()

    def total(self):
        return len(self._keys)

    def next_key(self):
        with self._lock:
            live = [k for k in self._keys if k not in self._dead]
            if not live:
                return None
            k = live[self._i % len(live)]
            self._i += 1
            return k

    def mark_dead(self, key):
        with self._lock:
            self._dead.add(key)


@dataclass
class AiConfig:
    provider: str = "mock"          # "mock" | "gemini"
    api_keys: list = field(default_factory=list)   # NHIEU key, moi dong 1
    text_model: str = GEMINI_TEXT_MODEL
    image_model: str = GEMINI_IMAGE_MODEL
    caption_prompt: str = DEFAULT_CAPTION_PROMPT
    image_prompt: str = DEFAULT_IMAGE_PROMPT
    do_caption: bool = True
    do_image: bool = True
    auto_rotate_model: bool = True  # tu dong xoay model khi bi gioi han

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "AiConfig":
        raw = dict(raw or {})
        # tuong thich ban cu: api_key (mot key) -> api_keys (danh sach)
        if "api_keys" not in raw and raw.get("api_key"):
            raw["api_keys"] = [raw["api_key"]]
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        if not isinstance(known.get("api_keys"), list):
            known["api_keys"] = parse_api_keys(str(known.get("api_keys") or ""))
        return cls(**known)


def shared_config_path() -> str:
    """File cau hinh AI DUNG CHUNG (tab config + bang bai cho dang doc cung mot cho)."""
    from .config import TOOL_DIR
    return os.path.join(TOOL_DIR, "data", "ai_lab.json")


def load_shared_config() -> "AiConfig":
    try:
        with open(shared_config_path(), encoding="utf-8") as fh:
            return AiConfig.from_dict(json.load(fh).get("cfg") or {})
    except (OSError, ValueError):
        return AiConfig()


def available(cfg: AiConfig) -> tuple[bool, str]:
    if cfg.provider == "mock":
        return True, ""
    if cfg.provider == "gemini":
        if not [k for k in (cfg.api_keys or []) if k.strip()]:
            return False, "Chưa nhập API key Gemini (mỗi dòng 1 key)."
        return True, ""
    return False, f"Nhà cung cấp không hỗ trợ: {cfg.provider}"


# ---------------------------------------------------------------- model list
_MODEL_CACHE: dict = {}          # key -> (danh sach, thoi diem)
_MODEL_CACHE_TTL = 600.0


def list_text_models(key: str) -> list:
    """Hoi API model KEY nay dung duoc (loc loai xao chu), uu tien flash-lite/flash/pro."""
    key = (key or "").strip()
    if not key:
        return []
    cu = _MODEL_CACHE.get(key)
    if cu and (time.monotonic() - cu[1]) < _MODEL_CACHE_TTL:
        return list(cu[0])
    try:
        req = urllib.request.Request(_LIST + "?key=" + key + "&pageSize=200")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for m in data.get("models") or []:
        name = (m.get("name") or "").replace("models/", "").strip()
        if not name:
            continue
        methods = [a.lower() for a in (m.get("supportedGenerationMethods") or [])]
        if methods and not any("generatecontent" in a for a in methods):
            continue
        if any(bad in name.lower() for bad in _NOT_TEXT):
            continue
        out.append(name)

    def sort_key(n):
        mm = re.search(r"(\d+(?:\.\d+)?)", n)
        ver = float(mm.group(1)) if mm else 0.0
        tier = 0 if "pro" in n else (1 if "lite" not in n else 2)
        return (-ver, tier, n)

    ds = sorted(set(out), key=sort_key)
    # thu tu xoay: flash-lite -> flash -> pro/khac (han muc ngay cao nhat truoc)
    ds = ([m for m in ds if "flash-lite" in m.lower()]
          + [m for m in ds if "flash" in m.lower() and "lite" not in m.lower()]
          + [m for m in ds if "flash" not in m.lower()])
    if ds:
        _MODEL_CACHE[key] = (list(ds), time.monotonic())
    return ds


#: key -> model vua xao duoc trong phien nay (IDEA-011): bai sau dung ngay, khoi xoay lai.
_MODEL_TOT: dict = {}


def _text_model_candidates(cfg: AiConfig, key: str) -> list:
    chosen = (cfg.text_model or GEMINI_TEXT_MODEL).strip()
    out = []
    tot = _MODEL_TOT.get(key)
    if tot:
        out.append(tot)
    if cfg.auto_rotate_model:
        song = list_text_models(key)
        # Model nguoi dung chon (co the la ban cu da bi go, vd 2.0-flash luu trong
        # ai_lab.json) chi thu khi API con liet ke no; danh sach rong -> van thu.
        if chosen and chosen not in out and (not song or chosen in song):
            out.append(chosen)
        for m in song:
            if m not in out:
                out.append(m)
    elif chosen and chosen not in out:
        out.append(chosen)
    return out or [GEMINI_TEXT_MODEL]


# ---------------------------------------------------------------- TEXT
def transform_text(text: str, cfg: AiConfig, log=None) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if cfg.provider == "mock":
        return _mock_text(text)
    if cfg.provider == "gemini":
        return _gemini_text(text, cfg, log or (lambda *a: None))
    raise AiError(f"provider không hỗ trợ: {cfg.provider}")


def _mock_text(text: str) -> str:
    rng = random.Random(hash(text) & 0xFFFFFFFF)
    emojis = ["✨", "🔥", "👉", "💯", "🌟", "😍", "🙌"]
    lead = rng.choice(["Chia sẻ nhé: ", "Cả nhà ơi, ", "Mới cập nhật: ", ""])
    return f"{lead}{text} {rng.choice(emojis)}{rng.choice(emojis)}"


def _gemini_text(text: str, cfg: AiConfig, log) -> str:
    prompt = cfg.caption_prompt.strip() or DEFAULT_CAPTION_PROMPT
    body = {"contents": [{"parts": [{"text": prompt + "\n\n---\n" + text}]}],
            "generationConfig": {"temperature": 1.0}}
    pool = ApiKeyPool(cfg.api_keys)
    if not pool.total():
        raise AiError("Chưa có API key.")
    last = None
    for _ in range(pool.total()):                 # moi key mot luot
        key = pool.next_key()
        if not key:
            break
        for model in _text_model_candidates(cfg, key):
            try:
                data = _call(model, key, body)
                parts = data["candidates"][0]["content"]["parts"]
                out = "".join(p.get("text", "") for p in parts).strip()
                if out:
                    _MODEL_TOT[key] = model        # nho de bai sau dung ngay
                    return out
            except AiError as e:
                last = e
                kind = classify_api_error(e)
                if kind == "quota":                # key het ngay -> bo key
                    log(f"Key ...{key[-6:]} hết quota ngày → đổi key."); pool.mark_dead(key); break
                if kind == "invalid":
                    log(f"Key ...{key[-6:]} sai → bỏ."); pool.mark_dead(key); break
                if kind == "rate":                 # model bi chan theo phut -> doi model
                    log(f"Model '{model}' bị giới hạn phút → đổi model."); continue
                log(f"Model '{model}' lỗi: {str(e)[:80]} → đổi model."); continue
    raise AiError(f"Tất cả key/model đều không xào được. Lỗi cuối: {str(last)[:150]}")


# ---------------------------------------------------------------- IMAGE
def transform_image(src: str, dest: str, cfg: AiConfig, log=None) -> bool:
    if not os.path.isfile(src):
        return False
    if cfg.provider == "mock":
        return _mock_image(src, dest)
    if cfg.provider == "gemini":
        return _gemini_image(src, dest, cfg, log or (lambda *a: None))
    raise AiError(f"provider không hỗ trợ: {cfg.provider}")


def _mock_image(src: str, dest: str) -> bool:
    try:
        shutil.copy2(src, dest)
        return True
    except OSError:
        return False


def _gemini_image(src: str, dest: str, cfg: AiConfig, log) -> bool:
    prompt = cfg.image_prompt.strip() or DEFAULT_IMAGE_PROMPT
    with open(src, "rb") as fh:
        raw = fh.read()
    body = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inlineData": {"mimeType": _mime_of(src),
                            "data": base64.b64encode(raw).decode("ascii")}},
        ]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    pool = ApiKeyPool(cfg.api_keys)
    if not pool.total():
        raise AiError("Chưa có API key.")
    model = cfg.image_model or GEMINI_IMAGE_MODEL
    last = None
    for _ in range(pool.total()):
        key = pool.next_key()
        if not key:
            break
        try:
            data = _call(model, key, body)
            parts = data["candidates"][0]["content"]["parts"]
            for p in parts:
                inline = p.get("inlineData") or p.get("inline_data")
                if inline and inline.get("data"):
                    with open(dest, "wb") as fh:
                        fh.write(base64.b64decode(inline["data"]))
                    return True
            raise AiError("Gemini không trả về ảnh.")
        except AiError as e:
            last = e
            kind = classify_api_error(e)
            if kind in ("quota", "invalid"):
                log(f"Key ...{key[-6:]} {kind} → đổi key."); pool.mark_dead(key); continue
            if kind == "rate":
                log(f"Key ...{key[-6:]} bị giới hạn phút → đổi key."); continue
            log(f"Xào ảnh lỗi: {str(e)[:80]} → đổi key."); continue
    raise AiError(f"Tất cả key đều không xào ảnh được. Lỗi cuối: {str(last)[:150]}")


# ---------------------------------------------------------------- REST
def _call(model: str, key: str, body: dict, timeout: float = 120.0) -> dict:
    url = _GEN.format(model=model) + "?key=" + key.strip()
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:300]
        except Exception:  # noqa: BLE001
            pass
        raise AiError(f"HTTP {exc.code}: {detail}") from exc
    except (KeyError, IndexError) as exc:
        raise AiError(f"Kết quả không đúng định dạng: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise AiError(f"Gọi Gemini lỗi: {exc}") from exc


def _mime_of(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(
        ext, "image/jpeg")
