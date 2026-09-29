"""Quet bai viet mot nhom Facebook qua ban mbasic (HTML thuan).

Tool tu tai HTML bang chinh COOKIE + PROXY cua profile -> dung dung phien dang
nhap va dung IP cua acc do, khong phai request "tran". Parse bai bang html.parser
cua Python (khong can trinh duyet), tai anh ve dia va tra ve danh sach Post.

Vi sao mbasic: facebook.com chinh la React ao hoa, class xao tron, parse cuc
brittle. mbasic tra HTML server-render on dinh hon nhieu.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser
from typing import Callable, Optional

from .posts import Post, classify, MEDIA_DIR
from .proxy import Proxy

MBASIC = "https://mbasic.facebook.com"
UA = ("Mozilla/5.0 (Android 12; Mobile; rv:119.0) Gecko/119.0 Firefox/119.0")

_UI_RE = re.compile(
    r"^(thích|like|bình luận|comment|chia sẻ|share|xem thêm|see more|ẩn|hide|"
    r"báo cáo|report|theo dõi|follow|gửi|send|thêm|more|·|\d+\s*(bình luận|lượt|"
    r"người|comment|share))",
    re.IGNORECASE,
)


class FbGroupError(RuntimeError):
    pass


# ----------------------------------------------------------------------
# Cookie tu profile
# ----------------------------------------------------------------------
def check_cookie(cookie_header: str, proxy: Proxy, timeout: float = 20.0) -> tuple:
    """Kiem tra cookie con dang nhap khong (qua HTTP, khong mo trinh duyet).

    Tai mbasic/home.php bang cookie + proxy. Tra ve (trang_thai, chi_tiet) voi
    trang_thai thuoc {"Live","Die","Checkpoint"}.
    """
    if not cookie_header or "c_user=" not in cookie_header:
        return ("Die", "cookie thiếu c_user")
    opener = _opener(proxy)
    try:
        html = _fetch(opener, MBASIC + "/home.php", cookie_header, timeout)
    except urllib.error.HTTPError as exc:
        return ("Die", f"HTTP {exc.code}")
    except urllib.error.URLError as exc:
        return ("Die", f"lỗi mạng: {exc.reason}")
    except Exception as exc:  # noqa: BLE001
        return ("Die", f"lỗi: {exc}")

    low = html.lower()
    head = low[:4000]
    if "checkpoint" in low or "/checkpoint/" in html:
        return ("Checkpoint", "dính checkpoint / xác minh")
    # Dau hieu DANG DANG NHAP tren mbasic: co nut dang bai / logout / bookmark menu.
    if ("/logout.php" in html or "logout.php?" in html
            or 'name="view_photo"' in html or "mbasic_logout_button" in low
            or "/composer/" in html or ">Bạn đang nghĩ gì" in html):
        return ("Live", "còn đăng nhập")
    # Dau hieu VE TRANG DANG NHAP.
    if ("login" in head and ("password" in head or "mật khẩu" in head
                              or "đăng nhập" in head)):
        return ("Die", "bị đưa về trang đăng nhập")
    # Khong chac -> coi la Live neu con thay c_user trong trang, khong thi Die.
    return ("Live", "ok") if "c_user" in html or "profile.php" in html else ("Die", "không rõ, không thấy phiên")


_WALL_JS = r"""(() => {
  var u = location.href, t = document.title || "";
  if (/\/checkpoint/i.test(u) || /checkpoint|xác nhận danh tính|xác minh/i.test(t))
    return JSON.stringify({ s: "Checkpoint", u: u, t: t });
  var hasPass = !!document.querySelector('input[type="password"],input[name="pass"]');
  if (/\/login|login\.php|\/recover|\/reg/i.test(u) || hasPass)
    return JSON.stringify({ s: "Die", u: u, t: t });
  // Con dang nhap: co thanh dieu huong / feed / nut dang bai.
  var live = document.querySelector('[role="navigation"],[role="feed"],[aria-label*="Trang chủ"],[aria-label*="Home"]');
  return JSON.stringify({ s: live ? "Live" : "Live", u: u, t: t });
})()"""


def check_wall(port: int, timeout: float = 40.0) -> tuple:
    """Kiem tra tuong acc FB dang mo trong trinh duyet (qua BiDi): Live/Checkpoint/Die."""
    import asyncio
    try:
        import websockets  # type: ignore
    except ImportError:
        return ("Chưa rõ", "thiếu websockets")

    async def run():
        async with websockets.connect(f"ws://127.0.0.1:{port}/session", max_size=20_000_000) as ws:
            i = 0
            async def cmd(m, p):
                nonlocal i
                i += 1
                await ws.send(json.dumps({"id": i, "method": m, "params": p}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get("id") == i:
                        return r
            await cmd("session.new", {"capabilities": {}})
            tr = await cmd("browsingContext.getTree", {})
            ctxs = tr.get("result", {}).get("contexts", [])
            ctx = None
            for c in ctxs:
                if "facebook.com" in (c.get("url") or ""):
                    ctx = c["context"]; break
            if not ctx and ctxs:
                ctx = ctxs[0]["context"]
            r = await cmd("script.evaluate", {"expression": _WALL_JS,
                                              "target": {"context": ctx}, "awaitPromise": True})
            try:
                await cmd("session.end", {})
            except Exception:
                pass
            return r.get("result", {}).get("result", {}).get("value", "") or ""

    try:
        raw = asyncio.run(asyncio.wait_for(run(), timeout=timeout))
        data = json.loads(raw)
        return (data.get("s") or "Chưa rõ", data.get("t") or data.get("u") or "")
    except Exception as exc:  # noqa: BLE001
        return ("Chưa rõ", f"lỗi: {exc}")


def read_fb_cookies(profile_dir: str) -> str:
    """Doc cookie facebook tu cookies.sqlite -> chuoi 'name=value; ...'.

    Doc ban sao de khong dung do Firefox dang mo (khoa WAL).
    """
    db = os.path.join(profile_dir, "cookies.sqlite")
    if not os.path.isfile(db):
        raise FbGroupError("Profile chưa có cookies.sqlite (chưa khởi tạo/đăng nhập).")
    con = sqlite3.connect(f"file:{db}?immutable=1", uri=True, timeout=10)
    try:
        rows = con.execute(
            "SELECT name, value FROM moz_cookies "
            "WHERE host LIKE '%facebook.com' AND value <> ''"
        ).fetchall()
    except sqlite3.Error as exc:
        raise FbGroupError(f"Không đọc được cookie: {exc}") from exc
    finally:
        con.close()
    seen, parts = set(), []
    for name, value in rows:
        if name in seen:
            continue
        seen.add(name)
        parts.append(f"{name}={value}")
    if "c_user" not in seen:
        raise FbGroupError("Profile chưa đăng nhập Facebook (thiếu cookie c_user).")
    return "; ".join(parts)


def _opener(proxy: Proxy) -> urllib.request.OpenerDirector:
    handlers = []
    if proxy.enabled and not proxy.is_socks:
        auth = f"{proxy.username}:{proxy.password}@" if proxy.needs_auth else ""
        url = f"http://{auth}{proxy.host}:{proxy.port}"
        handlers.append(urllib.request.ProxyHandler({"http": url, "https": url}))
    # Proxy SOCKS: urllib khong ho tro san -> di thang (hiem dung cho mbasic).
    return urllib.request.build_opener(*handlers)


def _fetch(opener, url: str, cookie: str, timeout: float = 25.0) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Cookie": cookie,
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml",
    })
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read()
    return raw.decode("utf-8", "replace")


# ----------------------------------------------------------------------
# Parser mot the <article>
# ----------------------------------------------------------------------
class _ArticleParser(HTMLParser):
    """Gom text/link/anh/abbr/tac gia trong mot khoi <article> cua mbasic."""

    SKIP_TEXT_IN = {"a", "h3", "h4", "abbr", "script", "style"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.texts = []          # text ngoai link/header -> caption
        self.links = []          # (href, text)
        self.images = []         # src
        self.abbr = ""
        self.author = ("", "")   # (name, url)
        self._cur_a = None       # (href, buffer)
        self._in_head = 0        # dang trong h3/h4
        self._in_abbr = False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        self.stack.append(tag)
        if tag == "a":
            self._cur_a = [d.get("href", ""), ""]
        elif tag == "img":
            src = d.get("src", "")
            if src:
                self.images.append(src)
        elif tag in ("h3", "h4"):
            self._in_head += 1
        elif tag == "abbr":
            self._in_abbr = True

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        if tag == "a" and self._cur_a is not None:
            href, text = self._cur_a[0], self._cur_a[1].strip()
            self.links.append((href, text))
            # tac gia: link dau tien nam trong h3/h4
            if self._in_head and not self.author[0] and text:
                self.author = (text, href)
            self._cur_a = None
        elif tag in ("h3", "h4"):
            self._in_head = max(0, self._in_head - 1)
        elif tag == "abbr":
            self._in_abbr = False

    def handle_data(self, data):
        if self._cur_a is not None:
            self._cur_a[1] += data
        if self._in_abbr:
            self.abbr += data
        inside_skip = any(t in self.SKIP_TEXT_IN for t in self.stack)
        if not inside_skip:
            t = data.strip()
            if t:
                self.texts.append(t)


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def _abs(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    return MBASIC + (href if href.startswith("/") else "/" + href)


def _parse_article(html: str, group: str) -> Optional[dict]:
    p = _ArticleParser()
    p.feed(html)

    # permalink
    permalink = ""
    for href, _t in p.links:
        if re.search(r"story\.php\?story_fbid=|/permalink/|/posts/", href):
            permalink = _abs(href)
            break
    if not permalink:
        m = re.search(r"<abbr", html)  # link boc abbr
        if m:
            am = re.search(r'href="([^"]+)"[^>]*>\s*<abbr', html)
            if am:
                permalink = _abs(am.group(1).replace("&amp;", "&"))

    # id
    post_id = ""
    ft = re.search(r'data-ft="([^"]+)"', html)
    if ft:
        blob = ft.group(1).replace("&quot;", '"')
        idm = re.search(r'"(?:top_level_post_id|tl_objid)":"?(\d+)"?', blob)
        if idm:
            post_id = idm.group(1)
    if not post_id and permalink:
        m = re.search(r"story_fbid=(\d+)|/permalink/(\d+)|/posts/(\d+)", permalink)
        if m:
            post_id = m.group(1) or m.group(2) or m.group(3)

    # anh: bo icon/emoji/static
    images = []
    for src in p.images:
        if src.startswith("data:"):
            continue
        if re.search(r"emoji|static|rsrc\.php|blank|spacer|/images/", src):
            continue
        full = _abs(src.replace("&amp;", "&"))
        if full not in images:
            images.append(full)

    # video
    videos = []
    for href, _t in p.links:
        if re.search(r"video_redirect/\?src=|/watch/\?v=|/videos/|/reel/", href):
            m = re.search(r"[?&]src=([^&]+)", href)
            v = urllib.parse.unquote(m.group(1)) if m else _abs(href)
            if v not in videos:
                videos.append(v)

    # caption: gop text ngoai link/header, bo cau UI
    body = [t for t in p.texts if not _UI_RE.match(t)]
    # bo trung, giu thu tu
    caption_parts, seen = [], set()
    for t in body:
        if t not in seen:
            seen.add(t)
            caption_parts.append(t)
    caption = _clean(" ".join(caption_parts))[:5000]

    if not (post_id or permalink or caption or images):
        return None

    return {
        "id": post_id or permalink,
        "group": group,
        "caption": caption,
        "permalink": permalink,
        "author": _clean(p.author[0]),
        "time": _clean(p.abbr),
        "images": images,
        "videos": videos,
    }


_TAG_RE = re.compile(r"<(/?)([a-zA-Z0-9]+)([^>]*)>")


def _is_story_start(tag: str, attrs: str) -> bool:
    """Mot the co phai la dau mot bai khong.

    mbasic tung boc bai trong <article>, nhung ban moi hay dung <div data-ft="..."
    chua top_level_post_id. Bat ca hai + role="article".
    """
    if tag == "article":
        return True
    if "data-ft" in attrs and ("top_level_post_id" in attrs or "tl_objid" in attrs):
        return True
    if 'role="article"' in attrs:
        return True
    return False


def _split_articles(html: str) -> list[str]:
    """Tach cac khoi bai, can bang the cung ten (chiu duoc div long nhau)."""
    stories = []
    pos = 0
    while True:
        m = _TAG_RE.search(html, pos)
        if not m:
            break
        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3)
        pos = m.end()
        if closing or not _is_story_start(tag, attrs):
            continue
        # tim the dong khop (dem the cung ten)
        depth = 1
        scan = pos
        end = -1
        while depth > 0:
            m2 = re.compile(r"<(/?)(%s)\b[^>]*>" % re.escape(tag), re.IGNORECASE).search(html, scan)
            if not m2:
                break
            if m2.group(1):
                depth -= 1
            else:
                depth += 1
            scan = m2.end()
            if depth == 0:
                end = m2.end()
        if end > 0:
            stories.append(html[m.start():end])
            pos = end
    # bo trung (mot bai co the vua co article vua co data-ft long trong)
    uniq, seen = [], set()
    for s in stories:
        key = s[:120]
        if key not in seen:
            seen.add(key)
            uniq.append(s)
    return uniq


def _find_next(html: str) -> str:
    # link "xem them bai / bai viet cu hon" o cuoi trang nhom
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
        href = m.group(1).replace("&amp;", "&")
        text = _clean(re.sub(r"<[^>]+>", "", m.group(2))).lower()
        if re.search(r"xem thêm bài|bài viết cũ|see more posts|older posts|show more", text):
            return _abs(href)
        if "/groups/" in href and re.search(r"bacr|cursor|bac=", href):
            return _abs(href)
    return ""


# ----------------------------------------------------------------------
# Tai anh
# ----------------------------------------------------------------------
def netscape_cookiefile(profile_dir: str, dest: str = "") -> str:
    """Xuat cookie facebook trong profile ra file Netscape cho yt-dlp dung.

    yt-dlp can cookiefile de tai video nhom kin / video rieng tu. Tra ve duong
    dan file, hoac "" neu khong doc duoc cookie.
    """
    db = os.path.join(profile_dir, "cookies.sqlite")
    if not os.path.isfile(db):
        return ""
    try:
        con = sqlite3.connect(f"file:{db}?immutable=1", uri=True, timeout=10)
        rows = con.execute(
            "SELECT host, path, isSecure, expiry, name, value FROM moz_cookies "
            "WHERE host LIKE '%facebook.com' OR host LIKE '%fbcdn.net'"
        ).fetchall()
        con.close()
    except sqlite3.Error:
        return ""
    if not rows:
        return ""
    dest = dest or os.path.join(profile_dir, "yt_cookies.txt")
    try:
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write("# Netscape HTTP Cookie File\n")
            for host, path, secure, expiry, name, value in rows:
                host = host or ""
                inc = "TRUE" if host.startswith(".") else "FALSE"
                sec = "TRUE" if secure else "FALSE"
                exp = int(expiry) if expiry else 0
                fh.write(f"{host}\t{inc}\t{path or '/'}\t{sec}\t{exp}\t{name}\t{value}\n")
    except OSError:
        return ""
    return dest


def _download_one(opener, cookie: str, url: str, dest: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Cookie": cookie})
        with opener.open(req, timeout=60) as resp:
            data = resp.read()
        if not data:
            return False
        with open(dest, "wb") as fh:
            fh.write(data)
        return True
    except (urllib.error.URLError, OSError):
        return False


def _download_media(opener, cookie: str, post: Post, media_dir: str,
                    max_img: int = 10, cookiefile: str = "") -> None:
    """Tai anh + video cua bai ve ``media_dir``. Ghi trang thai vao post.status.

    Anh: tai thang qua HTTP (proxy + cookie). Video: dung yt-dlp voi link bai/reel
    (FB video la luong DASH, tai tay bi cam tieng -- yt-dlp lo viec ghep hinh+tieng).
    """
    os.makedirs(media_dir, exist_ok=True)
    base = re.sub(r"[^0-9A-Za-z]", "_", str(post.id or "post"))[:40]

    img_ok = img_fail = 0
    for index, url in enumerate(post.images[:max_img]):
        m = re.search(r"\.(jpg|jpeg|png|gif|webp)", url, re.IGNORECASE)
        ext = ("." + m.group(1).lower()) if m else ".jpg"
        dest = os.path.join(media_dir, f"{base}_{index}{ext}")
        if _download_one(opener, cookie, url, dest):
            post.saved_paths.append(dest)
            img_ok += 1
        else:
            img_fail += 1

    # Video: tai bang yt-dlp. Chi thu link yt-dlp ho tro (reel/watch/videos/v=),
    # bo link rac (URL group, /stories/ -> yt-dlp khong nhan).
    vid_ok = vid_fail = vid_skip = 0
    from . import download as dl
    cand = [u for u in (post.videos or []) if u and dl.is_video_link(u)]
    if not cand and post.permalink and dl.is_video_link(post.permalink):
        cand = [post.permalink]
    had_video = bool(post.videos) or post.fmt == "Video"
    for index, url in enumerate(cand):
        try:
            path = dl.download_video(url, media_dir, cookiefile=cookiefile,
                                     base=f"{base}_v{index}")
            post.saved_videos.append(path)
            vid_ok += 1
        except dl.DownloadError:
            vid_fail += 1
    if had_video and not cand:
        vid_skip = 1   # co video nhung khong co link tai duoc

    parts = []
    if img_ok:
        parts.append(f"✔ {img_ok} ảnh")
    if vid_ok:
        parts.append(f"✔ {vid_ok} video")
    if img_fail:
        parts.append(f"✖ {img_fail} ảnh lỗi")
    if vid_fail:
        parts.append(f"✖ {vid_fail} video lỗi")
    if vid_skip:
        parts.append("🎬 video (không tải được link)")
    if not post.images and not had_video:
        parts.append("Không có media")
    post.status = ", ".join(parts) if parts else "—"


# ----------------------------------------------------------------------
# Quet
# ----------------------------------------------------------------------
def group_id_from_url(url: str) -> str:
    m = re.search(r"/groups/([0-9A-Za-z._-]+)", url or "")
    return m.group(1) if m else (url or "").strip()


def _asset(name: str) -> str:
    import sys
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(base, "assets", name),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", name)):
        if os.path.isfile(cand):
            with open(cand, encoding="utf-8") as fh:
                return fh.read()
    raise FbGroupError(f"Thiếu asset {name}.")


#: Thong tin lan quet DOM gan nhat: {"count", "rounds", "log": [...], "ms"} -- de
#: chan doan / kiem chung (HOP-DONG.md); UI khong bat buoc dung.
LAST_SCAN_INFO: dict = {}


def extract_via_bidi(port: int, count: int, group_url: str = "",
                     timeout: Optional[float] = None) -> list[dict]:
    """Ket noi WebDriver BiDi, chay bo quet DOM tren trang nhom da mo -> bai (raw).

    Firefox 154 khong con CDP -> dung BiDi. Bo quet (fbgroup_dom.js) cuon feed
    THEO TIEN DO cho toi khi du ``count`` bai hoac het feed.

    ``timeout`` None = max(200, 60 + 4*count) giay (ADR-002): 50 bai nang qua
    proxy cham co the qua 200s, ma asyncio.wait_for het gio thi mat trang. JS
    duoc bao ngan sach (timeout - 15s) de tu dung va tra phan da gom truoc.
    """
    import asyncio
    try:
        import websockets  # type: ignore
    except ImportError as exc:
        raise FbGroupError("Thiếu thư viện 'websockets' (pip install websockets).") from exc

    count = max(1, int(count))
    if timeout is None:
        timeout = max(200.0, 60.0 + 4.0 * count)
    budget_ms = int(max(30.0, timeout - 15.0) * 1000)
    # Chi nap bo quet DOM. Hai asset phat lai GraphQL (hook + truy van) van nam
    # trong core/assets cho ADR-001 "lam giau media" sau nay, nhung KHONG nap o
    # day -- truoc day nap roi bo, doc nham la co 2 duong quet (IDEA-005).
    dom_js = (_asset("fbgroup_dom.js").replace("__TARGET__", str(count))
              .replace("__BUDGET_MS__", str(budget_ms)))

    async def run():
        url = f"ws://127.0.0.1:{port}/session"
        async with websockets.connect(url, max_size=200_000_000) as ws:
            i = 0

            async def cmd(method, params):
                nonlocal i
                i += 1
                mid = i
                await ws.send(json.dumps({"id": mid, "method": method, "params": params}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == mid:
                        return msg

            r = await cmd("session.new", {"capabilities": {}})
            if "error" in r:
                raise FbGroupError(f"BiDi session lỗi: {r.get('message')}")
            r = await cmd("browsingContext.getTree", {})
            ctxs = r.get("result", {}).get("contexts", [])
            target = None
            for c in ctxs:
                if "facebook.com" in (c.get("url") or ""):
                    target = c["context"]
                    break
            if not target and ctxs:
                target = ctxs[0]["context"]
            if not target:
                await cmd("session.end", {})
                raise FbGroupError("Không thấy tab Facebook trong trình duyệt.")

            # Bo quet DOM: chay tren trang da tai (launch_debug da mo san nhom),
            # cuon tu dau feed nen lay du bai. On dinh hon phat lai GraphQL (phan
            # trang GraphQL con chap chon -- xem ADR-001 trong KIEN-TRUC.md).
            rr = await cmd("script.evaluate", {
                "expression": dom_js, "target": {"context": target}, "awaitPromise": True})
            try:
                await cmd("session.end", {})
            except Exception:
                pass
            rs = rr.get("result", {})
            if rs.get("type") == "exception":
                raise FbGroupError("JS bóc bài lỗi: " + str(rs.get("exceptionDetails"))[:200])
            return rs.get("result", {}).get("value", "") or ""

    try:
        raw = asyncio.run(asyncio.wait_for(run(), timeout=timeout))
    except FbGroupError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FbGroupError(f"Không kết nối được trình duyệt (BiDi): {exc}") from exc

    err = _scan_error(raw)
    if err:
        raise FbGroupError("Bóc bài lỗi: " + err)
    global LAST_SCAN_INFO
    try:
        d = json.loads(raw)
        LAST_SCAN_INFO = ({k: d.get(k) for k in ("count", "rounds", "log", "ms", "stop")}
                          if isinstance(d, dict) else {})
    except (ValueError, TypeError):
        LAST_SCAN_INFO = {}
    return _parse_scan(raw)


def tom_tat_quet(info: Optional[dict], count: int) -> str:
    """Cau tom tat sau khi quet, cho UI hien (ADR-004): du / het feed / het gio / tran.

    Nghiep vu dat o core de UI (cua so Quet bai, tab Thu nghiem AI) chi hien chu.
    ``info`` la ``LAST_SCAN_INFO``; rong/thieu khoa van tra cau hop ly, khong nem.
    """
    info = info or {}
    count = max(1, int(count or 1))
    n = int(info.get("count") or 0)
    ms = int(info.get("ms") or 0)
    giay = f" trong {ms // 1000}s" if ms else ""
    vong = info.get("rounds")
    vong_txt = f", {vong} vòng cuộn" if vong else ""
    stop = info.get("stop") or ""
    if n >= count or stop == "du":
        return f"Quét xong {n}/{count} bài{giay}{vong_txt}."
    if stop == "het_feed":
        return f"Quét xong {n}/{count} bài{giay}{vong_txt}: nhóm chỉ có {n} bài (hết feed)."
    if stop == "het_gio":
        return (f"Gom được {n}/{count} bài{giay}{vong_txt} — hết giờ, nhóm tải chậm: "
                "thử lại hoặc giảm số bài.")
    if stop == "tran":
        return f"Gom được {n}/{count} bài{giay}{vong_txt} (chạm trần vòng cuộn)."
    return f"Quét xong {n}/{count} bài{giay}{vong_txt}."


def _parse_scan(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(data, dict):
        return data.get("posts") or []
    return data if isinstance(data, list) else []


def _scan_error(raw: str) -> str:
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("error"):
            return str(data["error"])
    except (ValueError, TypeError):
        pass
    return ""


def _merge_scans(dom: list[dict], gq: list[dict]) -> list[dict]:
    """Gop 2 nguon: DOM lam nen (du so bai), GraphQL lam giau noi khop caption.

    Khop theo 40 ky tu dau caption. GraphQL thuong co album day du hon + video URL.
    """
    def key(p):
        return (p.get("caption") or "").strip()[:40].lower()
    gq_by = {key(p): p for p in gq if key(p)}
    out = []
    used = set()
    for p in dom:
        k = key(p)
        g = gq_by.get(k)
        if g:
            used.add(k)
            # giu caption DOM (day du do da bung "xem them"), lay media giau hon
            imgs = g.get("images") or p.get("images") or []
            vids = g.get("videos") or p.get("videos") or []
            out.append({**p, "images": imgs or p.get("images", []),
                        "videos": vids or p.get("videos", []),
                        "permalink": p.get("permalink") or g.get("permalink", "")})
        else:
            out.append(p)
    # bai chi GraphQL co (DOM bo sot)
    for k, g in gq_by.items():
        if k not in used:
            out.append(g)
    return out


def wait_bidi_ready(port: int, timeout: float = 25.0) -> bool:
    """Cho toi khi cong BiDi cua Firefox san sang (mo duoc websocket)."""
    import asyncio
    try:
        import websockets  # type: ignore
    except ImportError:
        return False

    async def probe() -> bool:
        try:
            async with websockets.connect(f"ws://127.0.0.1:{port}/session", open_timeout=3):
                return True
        except Exception:
            return False

    end = time.time() + timeout
    while time.time() < end:
        try:
            if asyncio.run(probe()):
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def download_all(posts: list[Post], profile_dir: str, proxy: Proxy,
                 media_dir: str, on_status: Optional[Callable[[str], None]] = None) -> None:
    """Tai anh + video cua cac bai ve ``media_dir`` bang cookie + proxy cua acc."""
    try:
        cookie = read_fb_cookies(profile_dir)
    except FbGroupError:
        cookie = ""
    cookiefile = netscape_cookiefile(profile_dir)   # cho yt-dlp tai video nhom
    opener = _opener(proxy)
    for i, post in enumerate(posts, start=1):
        if on_status:
            on_status(f"Đang tải media bài {i}/{len(posts)}...")
        _download_media(opener, cookie, post, media_dir, cookiefile=cookiefile)


def posts_from_raw(raw: list[dict], group_url: str) -> list[Post]:
    now = time.strftime("%Y-%m-%d %H:%M")
    group_ref = "https://www.facebook.com/groups/" + group_id_from_url(group_url)
    out = []
    for d in raw:
        images = d.get("images") or []
        videos = d.get("videos") or []
        caption = d.get("caption") or ""
        permalink = d.get("permalink") or ""
        out.append(Post(
            id=str(d.get("id") or permalink or caption[:40]),
            group=group_ref,
            caption=caption,
            fmt=d.get("fmt") or classify(images, videos, caption, permalink),
            permalink=permalink,
            author=d.get("author") or "",
            time=d.get("time") or "",
            images=images,
            videos=videos,
            scanned_at=now,
        ))
    return out


def scan_group_mbasic(
    profile_dir: str,
    proxy: Proxy,
    group_url: str,
    count: int = 20,
    download: bool = True,
    media_dir: str = MEDIA_DIR,
    on_status: Optional[Callable[[str], None]] = None,
    max_pages: int = 10,
) -> list[Post]:
    """Quet ``count`` bai moi nhat cua nhom. Tra ve danh sach Post."""
    def status(m: str) -> None:
        if on_status:
            on_status(m)

    gid = group_id_from_url(group_url)
    cookie = read_fb_cookies(profile_dir)
    opener = _opener(proxy)
    now = time.strftime("%Y-%m-%d %H:%M")
    url = f"{MBASIC}/groups/{gid}"
    group_ref = f"{MBASIC}/groups/{gid}"

    posts: list[Post] = []
    seen: set = set()
    for page in range(1, max_pages + 1):
        status(f"Đang tải trang {page} ({len(posts)}/{count} bài)...")
        try:
            html = _fetch(opener, url, cookie)
        except urllib.error.HTTPError as exc:
            raise FbGroupError(f"Facebook trả lỗi {exc.code} (cookie hết hạn?).") from exc
        except urllib.error.URLError as exc:
            raise FbGroupError(f"Không tải được trang: {exc.reason}") from exc

        if "login.php" in html[:2000] or "/login/" in html[:2000]:
            raise FbGroupError("Bị chuyển sang trang đăng nhập — cookie không hợp lệ.")

        blocks = _split_articles(html)
        # Chan doan: trang dau luon luu lai HTML + so bai tach duoc, de khi ra 0
        # bai con biet DOM that trong ra sao ma chinh selector.
        if page == 1:
            try:
                dbg = os.path.join(os.path.dirname(media_dir), "last_scan.html")
                os.makedirs(os.path.dirname(dbg), exist_ok=True)
                with open(dbg, "w", encoding="utf-8") as fh:
                    fh.write(html)
                status(f"Trang 1: tách được {len(blocks)} khối bài "
                        f"(HTML đã lưu: {dbg}).")
            except OSError:
                pass

        for block in blocks:
            data = _parse_article(block, group_ref)
            if not data or data["id"] in seen:
                continue
            seen.add(data["id"])
            post = Post(
                scanned_at=now,
                fmt=classify(data["images"], data["videos"], data["caption"], data["permalink"]),
                **data,
            )
            posts.append(post)
            if len(posts) >= count:
                break
        if len(posts) >= count:
            break
        nxt = _find_next(html)
        if not nxt:
            status("Hết bài / không thấy trang kế.")
            break
        url = nxt
        time.sleep(0.6)

    posts = posts[:count]

    if download:
        for i, post in enumerate(posts, start=1):
            status(f"Đang tải media bài {i}/{len(posts)}...")
            _download_media(opener, cookie, post, media_dir)
    else:
        for post in posts:
            n = len(post.images) + len(post.videos)
            post.status = f"{n} media (chưa tải)" if n else "Không có media"

    return posts
