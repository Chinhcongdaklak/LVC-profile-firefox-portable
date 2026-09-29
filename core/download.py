"""Tai video ve tu link (YouTube / Facebook / TikTok...) bang yt-dlp.

yt-dlp lo het phan kho: chon do phan giai, ghep tieng+hinh, xu ly DASH cua FB
(cai ma tai tay bi cam tieng). Tra ve duong dan file .mp4 da tai.
"""

from __future__ import annotations

import os
import re
from typing import Callable, Optional


class DownloadError(RuntimeError):
    pass


def available() -> bool:
    try:
        import yt_dlp  # noqa: F401
        return True
    except ImportError:
        return False


def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "video"


def download_video(url: str, dest_dir: str, cookiefile: str = "",
                   on_status: Optional[Callable[[str], None]] = None,
                   base: str = "") -> str:
    """Tai mot video ve ``dest_dir``. Tra ve duong dan file. Loi thi nem DownloadError.

    ``cookiefile``: file cookie Netscape (video rieng tu/nhom kin can dang nhap).
    ``base``: ten file (khong duoi); de trong thi lay theo tieu de video.
    """
    try:
        import yt_dlp
    except ImportError as exc:
        raise DownloadError("Chưa cài yt-dlp (pip install yt-dlp).") from exc

    os.makedirs(dest_dir, exist_ok=True)
    outtmpl = os.path.join(dest_dir, (_safe(base) if base else "%(title).80s_%(id)s") + ".%(ext)s")
    # File tam (.part / fragment) de trong thu muc temp CUA TOOL, khong ranh temp OS.
    try:
        from .config import TEMP_DIR
        os.makedirs(TEMP_DIR, exist_ok=True)
    except Exception:  # noqa: BLE001
        TEMP_DIR = dest_dir

    done = {"path": ""}

    def hook(d):
        if d.get("status") == "downloading" and on_status:
            pct = d.get("_percent_str", "").strip()
            on_status(f"Đang tải video {pct}...")
        elif d.get("status") == "finished":
            done["path"] = d.get("filename", "")

    opts = {
        "outtmpl": outtmpl,
        "paths": {"temp": TEMP_DIR},
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
        "retries": 3,
        "concurrent_fragment_downloads": 4,
    }
    if cookiefile and os.path.isfile(cookiefile):
        opts["cookiefile"] = cookiefile

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Duong dan CUOI (sau merge) nam o requested_downloads; prepare_filename
            # va hook co the tra ve fragment tien-merge nen chi dung lam du phong.
            path = ""
            rd = info.get("requested_downloads") or []
            if rd:
                path = rd[0].get("filepath") or rd[0].get("_filename") or ""
            if not path or not os.path.isfile(path):
                path = ydl.prepare_filename(info)
    except Exception as exc:  # noqa: BLE001
        raise DownloadError(str(exc)[:200]) from exc

    if path and not os.path.isfile(path):
        alt = os.path.splitext(path)[0] + ".mp4"
        if os.path.isfile(alt):
            path = alt
    if (not path or not os.path.isfile(path)) and done["path"] and os.path.isfile(done["path"]):
        path = done["path"]
    if not path or not os.path.isfile(path):
        raise DownloadError("tải xong nhưng không thấy file")
    return path


def is_video_link(url: str) -> bool:
    """Link co phai VIDEO tai duoc khong (de biet nen tai hay chi share link).

    Loai /watch/hashtag/ (trang hashtag, khong phai video) va cac trang khong tai
    duoc (/groups/.., /stories/..). Chi nhan dang yt-dlp thuc su ho tro.
    """
    u = url or ""
    if re.search(r"/watch/hashtag/|/groups/|/stories/", u, re.IGNORECASE):
        return False
    return bool(re.search(
        r"youtube\.com/watch|youtu\.be/|[?&]v=\d{5,}|"
        r"/videos/\S*?\d{6,}|"                 # ke ca /videos/pcb.<album>/<id>
        r"/reel/\d|/reels/\d|tiktok\.com/.+/video/|/watch/\?v=",
        u, re.IGNORECASE))


def fb_video_id(url: str) -> str:
    """Bóc video id Facebook tu cac dang URL, tra ve chuoi so hoac ''.

    Ho tro: /videos/<id>, /videos/pcb.<album>/<id>, watch/?v=<id>, /reel/<id>.
    """
    u = url or ""
    m = re.search(r"/videos/(?:pcb\.\d+/)?(\d{6,})", u) \
        or re.search(r"[?&]v=(\d{5,})", u) \
        or re.search(r"/reels?/(\d{6,})", u)
    return m.group(1) if m else ""
