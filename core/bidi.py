"""Chay JS trong Firefox dang mo qua WebDriver BiDi (Firefox 154 bo CDP).

Dung chung cho: boc bai nhom, check tuong, tuong tac (like/comment), nuoi acc.
Chi 1 session moi luc -> luon session.end sau khi xong.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional


class BidiError(RuntimeError):
    pass


def _ws():
    try:
        import websockets  # type: ignore
        return websockets
    except ImportError as exc:
        raise BidiError("Thiếu thư viện 'websockets' (pip install websockets).") from exc


def run_js(port: int, js: str, navigate_url: str = "",
           preload: str = "", wait_after_nav: float = 6.0,
           timeout: float = 90.0, want_facebook: bool = True) -> str:
    """Chay ``js`` (bieu thuc, co the async) trong tab dang mo, tra ve gia tri chuoi.

    - ``navigate_url``: neu co, dieu huong tab toi day truoc khi chay.
    - ``preload``: functionDeclaration cai TRUOC khi trang chay (addPreloadScript).
    - ``want_facebook``: uu tien chon tab facebook.com.
    """
    websockets = _ws()

    async def run() -> str:
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
                raise BidiError(f"BiDi session lỗi: {r.get('message')}")
            tr = await cmd("browsingContext.getTree", {})
            ctxs = tr.get("result", {}).get("contexts", [])
            ctx = None
            if want_facebook:
                for c in ctxs:
                    if "facebook.com" in (c.get("url") or ""):
                        ctx = c["context"]
                        break
            if not ctx and ctxs:
                ctx = ctxs[0]["context"]
            if not ctx:
                await cmd("session.end", {})
                raise BidiError("Không thấy tab nào trong trình duyệt.")

            if preload:
                await cmd("script.addPreloadScript", {"functionDeclaration": preload})
            if navigate_url:
                await cmd("browsingContext.navigate",
                          {"context": ctx, "url": navigate_url, "wait": "complete"})
                await asyncio.sleep(wait_after_nav)

            rr = await cmd("script.evaluate", {
                "expression": js, "target": {"context": ctx}, "awaitPromise": True})
            try:
                await cmd("session.end", {})
            except Exception:
                pass
            rs = rr.get("result", {})
            if rs.get("type") == "exception":
                raise BidiError("JS lỗi: " + str(rs.get("exceptionDetails"))[:200])
            return rs.get("result", {}).get("value", "") or ""

    try:
        return asyncio.run(asyncio.wait_for(run(), timeout=timeout))
    except BidiError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise BidiError(f"Không kết nối trình duyệt (BiDi): {exc}") from exc


def wait_ready(port: int, timeout: float = 30.0) -> bool:
    """Cho cong BiDi mo duoc websocket."""
    import time
    websockets = _ws()

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
