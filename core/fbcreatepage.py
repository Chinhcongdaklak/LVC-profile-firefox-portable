"""Tu dong tao fanpage Facebook bang trinh duyet cua tung acc.

Facebook khong con API tao Page cho ung dung thuong -> phai lam qua giao dien.
Cach lam giong chuc nang "Quet bai nhom": mo profile kem cong WebDriver BiDi
(``launch_debug``), roi dieu khien trang bang cac lenh BiDi (``script.evaluate``
de dien form, ``winfile`` de lai hop thoai chon file cho avatar/anh bia).

KHONG dung process-script agent (fbupload_agent.js) -- de tach hoan toan khoi
duong dang bai, va vi tao page it thao tac hon dang video.

Luong mot page:
  1. launch_debug -> mo https://www.facebook.com/pages/creation/
  2. Cho cong BiDi san sang, ket noi, tim tab Facebook.
  3. "inspect": doc cau truc form (ten/hang muc/mo ta) -- de do giao dien va
     chay thu ma KHONG tao page.
  4. "fill": dien Ten, chon Hang muc (o goi y), dien Mo ta.
  5. (tuy chon) bam Tao.
  6. (tuy chon) up avatar + anh bia qua hop thoai Windows.

Facebook doi giao dien tao page tuy ngon ngu / dot A/B -> nhan dien theo
placeholder/aria/hinh hoc, khong theo chu cung. Van co the gay khi FB doi lon;
luon co che do "inspect" de do lai.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Callable, Optional

#: Trang tao page. FB tu chuyen sang luong "New Pages" hien hanh.
CREATE_URL = "https://www.facebook.com/pages/creation/"

#: Cong debug rieng cho tao page (khac cong quet nhom 9333 de khong dam nhau).
DEBUG_PORT = 9366


class CreatePageError(Exception):
    """Loi khi tao page (khong ket noi duoc, khong thay form, FB chan...)."""


class AccountBlockedError(CreatePageError):
    """Acc khong dung duoc nua: bi checkpoint, bi dang xuat, hoac bi CAM tao page.

    Nguoi goi nen DUNG han acc nay (dung thu them ten khac cung vo ich).
    """


# --------------------------------------------------------------------------- JS
# Cac doan JS chay trong trang qua BiDi script.evaluate. Tra ve JSON string de
# ben Python doc lai (BiDi tra "value" la chuoi).

#: Doc cau truc form tao page: cac o nhap + nut, kem aria/placeholder/hinh hoc.
_INSPECT_JS = r"""
(() => {
  function box(el){ try { var b = el.getBoundingClientRect();
    return {x:Math.round(b.left), y:Math.round(b.top),
            w:Math.round(b.width), h:Math.round(b.height)}; } catch(e){ return null; } }
  function vis(el){ var b = box(el); return b && b.w > 40 && b.h > 10; }
  function desc(el){
    return { tag: el.tagName.toLowerCase(),
             type: (el.getAttribute('type')||''),
             role: (el.getAttribute('role')||''),
             aria: (el.getAttribute('aria-label')||'').slice(0,60),
             ph: (el.getAttribute('placeholder')||'').slice(0,60),
             name: (el.getAttribute('name')||'').slice(0,40),
             text: (el.innerText||el.textContent||'').trim().slice(0,50),
             box: box(el) };
  }
  var out = { url: location.href, inputs: [], areas: [], buttons: [] };
  document.querySelectorAll('input').forEach(function(el){
    if (vis(el)) out.inputs.push(desc(el)); });
  document.querySelectorAll('textarea, [contenteditable="true"]').forEach(function(el){
    if (vis(el)) out.areas.push(desc(el)); });
  document.querySelectorAll('[role="button"], button').forEach(function(el){
    if (vis(el)) out.buttons.push(desc(el)); });
  return JSON.stringify(out);
})()
"""

#: Ham JS chung: bo tat ca truy van ve vung role=main (form tao page nam trong
#: do). Thanh nav "Search Facebook" nam NGOAI main nen tu dong bi loai -- neu
#: khong, o Ten se an nham vao thanh tim kiem. Da gap that (2026-09).
_HELPERS = r"""
  function mainRoot(){ return document.querySelector('[role="main"]') || document.body; }
  function vis(el){ var b = el.getBoundingClientRect(); return b.width > 60 && b.height > 12; }
  function low(s){ return (s||'').toLowerCase(); }
  function nameInput(root){
    // O Ten page: input type=text (khong phai search/combobox) trong main.
    var xs = [].slice.call(root.querySelectorAll('input[type="text"]')).filter(vis);
    return xs[0] || null;
  }
  function catInput(root){
    // O Hang muc: combobox/search trong main, KHAC thanh nav (nav o ngoai main).
    var xs = [].slice.call(root.querySelectorAll('input[role="combobox"], input[type="search"]'))
      .filter(function(el){ return vis(el)
        && low(el.getAttribute('aria-label')).indexOf('search facebook') === -1; });
    return xs[0] || null;
  }
  function bioInput(root){
    var xs = [].slice.call(root.querySelectorAll('textarea, [contenteditable="true"]')).filter(vis);
    return xs[0] || null;
  }
  function setNative(el, val){
    try {
      var proto = el.tagName.toLowerCase() === 'textarea'
        ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
      var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      el.focus(); setter.call(el, val);
      el.dispatchEvent(new Event('input', {bubbles:true}));
      el.dispatchEvent(new Event('change', {bubbles:true}));
    } catch(e){}
  }
  function setCE(el, val){
    try { el.focus();
      document.execCommand('selectAll', false, null);
      document.execCommand('insertText', false, val);
      el.dispatchEvent(new Event('input', {bubbles:true}));
    } catch(e){}
  }
"""

#: Dien Ten + Mo ta. Nhan dien o trong vung role=main (xem _HELPERS).
_FILL_JS = r"""
(() => {
""" + _HELPERS + r"""
  var TEN = __TEN__, MOTA = __MOTA__;
  var root = mainRoot();
  var result = { ten:false, mota:false };
  var ten = nameInput(root);
  if (ten && TEN){ setNative(ten, TEN); result.ten = true; }
  if (MOTA){
    var bio = bioInput(root);
    if (bio){
      if (bio.tagName.toLowerCase() === 'textarea') setNative(bio, MOTA);
      else setCE(bio, MOTA);
      result.mota = true;
    }
  }
  return JSON.stringify(result);
})()
"""

#: Go Hang muc roi cho danh sach goi y hien -> chon dong dau (lam o _CATEGORY_PICK).
_CATEGORY_TYPE_JS = r"""
(() => {
""" + _HELPERS + r"""
  var CAT = __CAT__;
  var cat = catInput(mainRoot());
  if (!cat) return JSON.stringify({ok:false, why:'khong thay o hang muc'});
  var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  cat.focus(); setter.call(cat, CAT);
  cat.dispatchEvent(new Event('input', {bubbles:true}));
  cat.dispatchEvent(new KeyboardEvent('keydown', {bubbles:true, key:'a'}));
  return JSON.stringify({ok:true});
})()
"""

#: Doc lai gia tri cac o (de kiem chung da dien dung cho -- KHONG tao page).
_READBACK_JS = r"""
(() => {
""" + _HELPERS + r"""
  var root = mainRoot();
  function val(el){ if(!el) return null;
    if (el.tagName && el.tagName.toLowerCase() === 'div') return (el.innerText||'').trim();
    return el.value; }
  return JSON.stringify({
    ten: val(nameInput(root)),
    hangmuc: val(catInput(root)),
    mota: val(bioInput(root))
  });
})()
"""

#: Chon goi y hang muc. Uu tien option KHOP CHINH XAC voi chu da go (khong phan
#: biet hoa thuong); khong co thi lay dong dau. Bam kieu mousedown+click cho
#: chac (combobox React co the nghe mousedown). Chi lay option trong listbox de
#: khong bam nham option cua widget khac tren trang.
_CATEGORY_PICK_JS = r"""
(() => {
  var CAT = __CAT__;
  var want = (CAT||'').trim().toLowerCase();
  var opts = [].slice.call(document.querySelectorAll('[role="listbox"] [role="option"]'))
    .filter(function(el){ var b = el.getBoundingClientRect(); return b.width > 40 && b.height > 8; });
  if (!opts.length)
    opts = [].slice.call(document.querySelectorAll('[role="option"]'))
      .filter(function(el){ var b = el.getBoundingClientRect(); return b.width > 40 && b.height > 8; });
  if (!opts.length) return JSON.stringify({ok:false, why:'chua co goi y'});
  function txt(el){ return (el.innerText||el.textContent||'').trim(); }
  var el = null;
  for (var i=0;i<opts.length;i++){ if (txt(opts[i]).toLowerCase() === want){ el = opts[i]; break; } }
  if (!el) el = opts[0];
  var chose = txt(el).slice(0,50);
  el.scrollIntoView({block:'center'});
  try { el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true})); } catch(e){}
  el.click();
  try { el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true})); } catch(e){}
  return JSON.stringify({ok:true, chose:chose,
    exact: (chose.toLowerCase() === want)});
})()
"""

#: Tra TOA DO TAM cua option hang muc khop nhat (de click that qua BiDi).
_CATEGORY_COORDS_JS = r"""
(() => {
  var CAT = __CAT__;
  var want = (CAT||'').trim().toLowerCase();
  var opts = [].slice.call(document.querySelectorAll('[role="listbox"] [role="option"]'))
    .filter(function(el){ var b=el.getBoundingClientRect(); return b.width>40 && b.height>8; });
  if (!opts.length)
    opts = [].slice.call(document.querySelectorAll('[role="option"]'))
      .filter(function(el){ var b=el.getBoundingClientRect(); return b.width>40 && b.height>8; });
  if (!opts.length) return JSON.stringify({ok:false, why:'chua co goi y'});
  function txt(el){ return (el.innerText||el.textContent||'').trim(); }
  var el=null;
  for (var i=0;i<opts.length;i++){ if (txt(opts[i]).toLowerCase()===want){ el=opts[i]; break; } }
  if (!el) el=opts[0];
  el.scrollIntoView({block:'center'});
  var b = el.getBoundingClientRect();
  return JSON.stringify({ok:true, x:Math.round(b.left+b.width/2),
    y:Math.round(b.top+b.height/2), chose:txt(el).slice(0,50),
    exact:(txt(el).toLowerCase()===want)});
})()
"""

#: Tra toa do tam nut Tao (neu da BAT). Nhan dien theo HINH HOC + trang thai
#: enabled, KHONG theo mau: nut "Create Page" khi bat van co nen trong suot
#: (mau xanh nam o phan tu con) -- da gap that (2026-09). Nut Tao la nut ENABLED,
#: RONG (ca chieu ngang form), THAP NHAT trong vung main.
_CREATE_COORDS_JS = r"""
(() => {
  var root = document.querySelector('[role="main"]') || document.body;
  function enabled(el){ return el.getAttribute('aria-disabled')!=='true' && !el.disabled; }
  var btns=[].slice.call(root.querySelectorAll('[role="button"],button'))
    .filter(function(el){ var b=el.getBoundingClientRect();
      return b.width>=200 && b.height>24 && b.top>0 && b.top<innerHeight && enabled(el); });
  if (!btns.length) return JSON.stringify({found:false});
  btns.sort(function(a,b){ return b.getBoundingClientRect().top-a.getBoundingClientRect().top; });
  var el=btns[0], b=el.getBoundingClientRect();
  return JSON.stringify({found:true, x:Math.round(b.left+b.width/2),
    y:Math.round(b.top+b.height/2),
    text:(el.innerText||el.textContent||'').trim().slice(0,40)});
})()
"""

#: Tim nut "Tao Trang"/"Create Page": nut nen MAU (primary) o cuoi form, khong
#: theo chu. Tra ve co bam duoc khong (khong tu bam -- nguoi goi quyet dinh).
_FIND_CREATE_JS = r"""
(() => {
  function bright(el){
    try { var c = getComputedStyle(el).backgroundColor || '';
      var m = c.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
      if (!m) return false;
      var r=+m[1],g=+m[2],b=+m[3];
      // nut xanh FB: xanh troi dam; loai nut xam/trang
      return (b > 150 && b > r + 30) || (g > 120 && b > 150);
    } catch(e){ return false; }
  }
  function enabled(el){
    var d = el.getAttribute('aria-disabled');
    return d !== 'true' && !el.disabled;
  }
  var btns = [].slice.call(document.querySelectorAll('[role="button"], button'))
    .filter(function(el){ var b = el.getBoundingClientRect();
      return b.width > 80 && b.height > 24 && b.top < innerHeight
             && enabled(el) && bright(el); });
  btns.sort(function(a,b){ return b.getBoundingClientRect().top - a.getBoundingClientRect().top; });
  if (!btns.length) return JSON.stringify({found:false});
  var el = btns[0];
  return JSON.stringify({found:true,
    text:(el.innerText||el.textContent||'').trim().slice(0,40)});
})()
"""

#: Bam nut tao (nut nen mau thap nhat) -- goi rieng khi da chac chan tao that.
_CLICK_CREATE_JS = _FIND_CREATE_JS.replace(
    "return JSON.stringify({found:true,",
    "el.click(); return JSON.stringify({found:true, clicked:true,")


# ----------------------------------------------------------------- BiDi client
class _Bidi:
    """Mot phien BiDi mo san toi tab Facebook -- eval JS va click that bang toa do.

    Click that (input.performActions) can thiet cho combobox React: bam kieu su
    kien JS gia khong commit lua chon (nut Tao van disabled). Da gap that (2026-09).
    """

    def __init__(self, ws):
        self.ws = ws
        self.i = 0
        self.ctx = None

    async def cmd(self, method, params):
        self.i += 1
        mid = self.i
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == mid:
                return msg

    async def start(self):
        r = await self.cmd("session.new", {"capabilities": {}})
        if "error" in r:
            raise CreatePageError(f"BiDi session lỗi: {r.get('message')}")
        r = await self.cmd("browsingContext.getTree", {})
        ctxs = r.get("result", {}).get("contexts", [])
        for c in ctxs:
            if "facebook.com" in (c.get("url") or ""):
                self.ctx = c["context"]
                break
        if not self.ctx and ctxs:
            self.ctx = ctxs[0]["context"]
        if not self.ctx:
            raise CreatePageError("Không thấy tab Facebook trong trình duyệt.")

    async def eval(self, expr):
        rr = await self.cmd("script.evaluate", {
            "expression": expr, "target": {"context": self.ctx},
            "awaitPromise": True})
        rs = rr.get("result", {})
        if rs.get("type") == "exception":
            raise CreatePageError("JS lỗi: " + str(rs.get("exceptionDetails"))[:200])
        return rs.get("result", {}).get("value", "") or ""

    async def click_xy(self, x, y):
        """Bam chuot THAT tai toa do (nhu nguoi dung) -- React nhan chac chan."""
        await self.cmd("input.performActions", {
            "context": self.ctx,
            "actions": [{
                "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
                "actions": [
                    {"type": "pointerMove", "x": int(x), "y": int(y)},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pause", "duration": 60},
                    {"type": "pointerUp", "button": 0},
                ],
            }]})

    async def end(self):
        try:
            await self.cmd("session.end", {})
        except Exception:
            pass


async def _bidi_eval(port: int, expr: str) -> str:
    import websockets  # type: ignore
    url = f"ws://127.0.0.1:{port}/session"
    async with websockets.connect(url, max_size=50_000_000) as ws:
        b = _Bidi(ws)
        await b.start()
        try:
            return await b.eval(expr)
        finally:
            await b.end()


async def _bidi_type_pick(port: int, type_js: str, coords_js: str,
                          tries: int = 8) -> dict:
    """Go hang muc (type_js) roi CLICK THAT vao option khop (coords_js tra x,y).

    coords_js phai tra JSON {ok, x, y, chose, exact} -- toa do tam option can bam.
    """
    import websockets  # type: ignore
    url = f"ws://127.0.0.1:{port}/session"
    async with websockets.connect(url, max_size=50_000_000) as ws:
        b = _Bidi(ws)
        await b.start()
        try:
            await b.eval(type_js)
            for _ in range(tries):
                await asyncio.sleep(0.8)
                raw = await b.eval(coords_js)
                d = _safe_json(raw)
                if d.get("ok") and "x" in d:
                    await b.click_xy(d["x"], d["y"])
                    await asyncio.sleep(0.6)
                    return d
            return {"ok": False}
        finally:
            await b.end()


def _run_type_pick(port: int, cat: str, timeout: float = 90.0) -> dict:
    """Go hang muc roi click that vao option khop. Tra dict {ok, chose, exact}."""
    type_js = _CATEGORY_TYPE_JS.replace("__CAT__", _js_str(cat))
    coords_js = _CATEGORY_COORDS_JS.replace("__CAT__", _js_str(cat))
    try:
        return asyncio.run(asyncio.wait_for(
            _bidi_type_pick(port, type_js, coords_js), timeout=timeout))
    except CreatePageError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CreatePageError(f"BiDi lỗi khi chọn hạng mục: {exc}") from exc


def _run_click_create(port: int, timeout: float = 60.0) -> dict:
    """Tim nut Tao (da BAT) roi click that. Tra {found, clicked, text}."""
    async def go():
        import websockets  # type: ignore
        url = f"ws://127.0.0.1:{port}/session"
        async with websockets.connect(url, max_size=50_000_000) as ws:
            b = _Bidi(ws)
            await b.start()
            try:
                d = _safe_json(await b.eval(_CREATE_COORDS_JS))
                if not d.get("found"):
                    return {"found": False}
                await b.click_xy(d["x"], d["y"])
                return {"found": True, "clicked": True, "text": d.get("text", "")}
            finally:
                await b.end()
    try:
        return asyncio.run(asyncio.wait_for(go(), timeout=timeout))
    except CreatePageError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CreatePageError(f"BiDi lỗi khi bấm Tạo: {exc}") from exc


def _run_eval(port: int, expr: str, timeout: float = 60.0) -> str:
    try:
        return asyncio.run(asyncio.wait_for(_bidi_eval(port, expr), timeout=timeout))
    except CreatePageError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CreatePageError(f"Không kết nối được trình duyệt (BiDi): {exc}") from exc


def _js_str(s: str) -> str:
    """Chuoi Python -> literal JSON an toan de nhet vao JS."""
    return json.dumps(s or "", ensure_ascii=False)


import re as _re


def in_page_mode(account) -> bool:
    """Acc dang thao tac duoi danh nghia mot PAGE (che do trang)?

    FB dat cookie ``i_user`` = id page khi "dung Facebook voi tu cach Trang".
    Doc tu cookie header cua acc. Agent (fbcreate_agent.js) van tu kiem + chuyen
    ve ca nhan trong trinh duyet; ham nay chi de tool BAO TRUOC + de test duoc.
    """
    ck = getattr(account, "cookie", "") or ""
    m = _re.search(r"(?:^|;\s*)i_user=(\d+)", ck)
    return bool(m and m.group(1))


# ------------------------------------------------------------------- dieu phoi
def inspect_form(manager, account, port: int = DEBUG_PORT,
                 log: Optional[Callable[[str], None]] = None) -> dict:
    """Mo trang tao page va DOC cau truc form -- KHONG tao gi ca.

    Dung de do giao dien tao page hien tai (FB hay doi), va de chay thu an toan.
    """
    from . import fbgroup

    noi = log or (lambda _m: None)
    manager.close(account, wait=8.0)
    noi("mở trang tạo Trang...")
    manager.launch_debug(account, CREATE_URL, port)
    if not fbgroup.wait_bidi_ready(port, timeout=30):
        raise CreatePageError("Trình duyệt chưa sẵn sàng (cổng gỡ lỗi).")
    time.sleep(10)         # cho form React ve xong (form nang ~8s)
    raw = _run_eval(port, _INSPECT_JS)
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {"raw": raw}


# ------------------------------------------------------------- bridge agent
#: File lenh + ket qua, trao doi voi fbcreate_agent.js qua tien trinh cha
#: (xem autoconfig._CREATE_LOADER_JS). Ten KHAC agent dang bai de khong dam nhau.
CMD_NAME = "qlfp-create.json"
RESULT_NAME = "qlfp-create-result.json"


def clear_create(profile_dir: str) -> None:
    for n in (CMD_NAME, RESULT_NAME):
        try:
            os.remove(os.path.join(profile_dir, n))
        except OSError:
            pass


def put_create_command(profile_dir: str, **cmd) -> None:
    os.makedirs(profile_dir, exist_ok=True)
    with open(os.path.join(profile_dir, CMD_NAME), "w", encoding="utf-8") as fh:
        json.dump(cmd, fh, ensure_ascii=False)


def read_create_result(profile_dir: str) -> Optional[dict]:
    try:
        with open(os.path.join(profile_dir, RESULT_NAME), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


#: Trang thai agent bao la XONG (khong cho them).
_OK_SUBMIT = {"create-done"}
_OK_DRY = {"filled-ready"}
_BAD = {"create-blocked", "no-create-button", "no-form", "no-name-input",
        "no-category-option", "error", "checkpoint", "logged-out"}


#: Cac buoc bao "da bam Tao" -> phai xac minh bang danh sach page (agent hay bao
#: nham create-blocked vi form khong doi kieu no cho, du page DA duoc tao).
_CLICKED = {"create-clicked", "create-done", "create-blocked"}
#: Facebook hien hop "Không thể tạo Trang" (vd trung ten page da quan ly) SAU khi bam -> chac chan KHONG co page.
_CREATE_FAILED = {"create-failed"}
#: Hong TRUOC khi bam Tao -> chac chan khong co page moi.
_PRECLICK_BAD = {"no-create-button", "no-form", "no-name-input",
                 "no-category-option", "error", "checkpoint", "logged-out"}


def _managed_page_ids(account, cookie: str = ""):
    """{id} cac page acc dang quan ly, qua cookie. None neu khong doc duoc."""
    from . import fbpage
    try:
        pages, _err = fbpage.list_managed_pages(cookie or account.cookie)
        return {str(p.get("id")) for p in pages if p.get("id")}, pages
    except Exception:  # noqa: BLE001
        return None, []


def _cookie_tuoi(manager, account) -> str:
    """Cookie TUOI doc tu cookies.sqlite cua profile (goi khi Firefox DA DONG -> file mo duoc).

    Tao page xong Facebook cap cookie/phien moi; ban ``account.cookie`` cu co the chua thay page
    vua tao -> xac minh oan la "khong tao duoc". Doc tuoi + cap nhat account.cookie de xac minh dung."""
    try:
        from . import cookies as _ck
        found = _ck.read_from_profile(manager.profile_dir(account))
        if any(getattr(c, "name", "") == "c_user" for c in found):
            tuoi = _ck.to_json(found)
            account.cookie = tuoi
            return tuoi
    except Exception:  # noqa: BLE001
        pass
    return account.cookie or ""


class FormError(CreatePageError):
    """Form tao page khong nhu mong doi TRUOC khi bam Tao (khong thay o ten, nut
    Tao khong bat, agent khong phan hoi...) -- KHONG phai acc bi cam."""


class FormInputError(FormError):
    """Loi NHAP LIEU cua nguoi dung (hang muc trong / khong co goi y). Hang muc
    dung chung cho moi page nen doi acc khac cung hong y het -> dung ca dot."""


#: Trang thai agent do NGUOI DUNG nhap sai (hang muc), khong phai do acc/form.
_FORM_INPUT = {"no-category-option"}


def _raise_form_error(st, result) -> None:
    """Nem dung loai loi cho ket qua agent truoc khi bam Tao (hoac khong phan hoi).

    Da gap that (5/9): nguoi dung de TRONG hang muc -> agent bao no-create-button
    -> tab ket luan "acc co the bi CAM" -> nguoi dung tuong tool hong. Phan loai
    ro de tab bao dung cho.
    """
    detail = ((result or {}).get("detail") or "").strip()
    if st == "checkpoint":
        raise AccountBlockedError(
            "ACC BỊ CHECKPOINT — Facebook giữ acc lại để xác minh. Gỡ checkpoint "
            "bằng tay rồi thử lại.")
    if st == "logged-out":
        raise AccountBlockedError("ACC ĐÃ BỊ ĐĂNG XUẤT — đăng nhập lại acc.")
    if st in _FORM_INPUT:
        raise FormInputError(f"{st}: {detail}".strip(": "))
    if st is None:
        raise FormError("agent không phản hồi — trang tạo page không load được "
                        "(mạng/proxy chậm?) hoặc trình duyệt chưa nạp agent")
    raise FormError(f"{st}: {detail}".strip(": "))


def create_one(manager, account, name: str, category: str = "",
               description: str = "", avatar: str = "", cover: str = "",
               submit: bool = True, timeout: float = 150.0, bm_id: str = "",
               log: Optional[Callable[[str], None]] = None) -> dict:
    """Tao MOT fanpage bang agent dac quyen (trinh duyet mo BINH THUONG).

    QUAN TRONG: FB chan tao page tu acc CA NHAN, nhung cho tao tu acc da bat
    "che do chuyen nghiep" -> nguoi goi phai bat pro cho acc TRUOC (xem
    ``enable_professional``). Da do that 5/9/2026: acc pro tao page thanh cong.

    Xac minh thanh cong bang DANH SACH PAGE qua cookie, khong tin mỗi agent:
    agent hay bao "create-blocked" vi form khong doi kieu no cho, du page DA tao.

    ``submit=False`` = chi dien form roi dung (chay thu, khong tao that).
    Tra ve dict {ten, created, page_id, note}.
    """
    noi = log or (lambda _m: None)
    name = (name or "").strip()
    if not name:
        raise CreatePageError("Thiếu tên fanpage.")
    if not (category or "").strip():
        # Facebook BAT BUOC hang muc: thieu thi nut Tao khong bao gio bat. Tu choi
        # ngay, khoi mo trinh duyet roi bao nham "acc bi cam" (da gap 5/9).
        raise FormInputError(
            "Thiếu HẠNG MỤC — Facebook bắt buộc chọn hạng mục khi tạo page "
            "(VD: Nhà hàng, Cửa hàng quần áo, Nghệ sĩ). Nhập hạng mục rồi chạy lại.")

    # Chup danh sach page TRUOC khi tao -- de biet page nao la moi.
    base_ids = None
    if submit:
        base_ids, _ = _managed_page_ids(account)

    tu_bm = bool((bm_id or "").strip())

    profile = manager.profile_dir(account)
    manager.close(account, wait=8.0)
    clear_create(profile)
    put_create_command(
        profile, action="create", name=name, category=category,
        description=description, submit=bool(submit),
        tuBm=tu_bm, bm_id=str(bm_id or ""),
        delay=3000, formTimeout=35000, catTimeout=14, doneTimeout=20)
    if tu_bm:
        # Tao TU BM (business.facebook.com): mo thang trang Trang cua BM, agent bam
        # Them -> "Tao Trang Facebook moi". Khong can che do chuyen nghiep (BM so huu page).
        from . import fbbm
        url = fbbm.BM_URL.format(bm_id=str(bm_id).strip())
        noi(f"[{name}] mở BM {str(bm_id).strip()} để tạo page bằng acc {account.id}...")
    else:
        url = CREATE_URL
        if in_page_mode(account):
            noi(f"[{name}] acc đang ở CHẾ ĐỘ TRANG — sẽ tự chuyển về hồ sơ cá nhân trước khi tạo.")
        noi(f"[{name}] mở trình duyệt tạo page bằng acc {account.id}...")
    manager.launch(account, url=url)     # BINH THUONG, khong cong go loi

    # Doi agent bao xong. Voi submit: bam xong (create-clicked/done/blocked) hoac
    # hong TRUOC khi bam. Voi chay thu: filled-ready.
    stop = (_CLICKED | _PRECLICK_BAD | _CREATE_FAILED) if submit else (_OK_DRY | _BAD | _CREATE_FAILED)
    seen: set = set()
    result = None
    made = None
    deadline = time.time() + timeout
    # Canh tien trinh Firefox: bi tat/chet giua chung thi dung NGAY thay vi ngoi
    # cho het timeout (tool treo "đang tạo" hang chuc phut).
    from core.fbbusiness import app_dir_cua, firefox_pids
    _app_dir = app_dir_cua(manager, account)
    _da_thay_browser = False
    _ke_tiep_kiem = 0.0
    try:
        while time.time() < deadline:
            if _app_dir and time.time() >= _ke_tiep_kiem:
                _ke_tiep_kiem = time.time() + 3.0
                if firefox_pids(_app_dir):
                    _da_thay_browser = True
                elif _da_thay_browser:
                    noi(f"[{name}] trình duyệt đã đóng giữa chừng — dừng.")
                    raise CreatePageError(
                        "Trình duyệt đã đóng giữa chừng (bị tắt tay, Not Responding "
                        "hoặc tự thoát) — trang này chưa tạo.")
            r = read_create_result(profile)
            if r:
                st = r.get("state")
                if st and st not in seen:
                    seen.add(st)
                    noi(f"[{name}] {st}"
                        + (f": {r.get('detail')}" if r.get("detail") else ""))
                if st in stop:
                    result = r
                    break
            time.sleep(0.5)

        # QUAN TRONG: xac minh page moi trong khi TRINH DUYET CON MO. Bam Tao xong
        # Facebook can trinh duyet mo them vai giay de gui lenh tao + xu ly; dong
        # ngay la page khong kip tao (da gap: "bam Tao thi browser tat luon").
        st0 = result.get("state") if result else None
        if submit and base_ids is not None and st0 in _CLICKED:
            noi(f"[{name}] đã bấm Tạo, chờ Facebook tạo xong (giữ trình duyệt mở)...")
            for _ in range(18):
                time.sleep(2)
                # Agent van chay: FB co the hien hop "Không thể tạo Trang" VAI GIAY SAU khi bam
                # (da gap that 2026-09-15: trung ten page) -> doc tiep, thay create-failed la dung ngay.
                r2 = read_create_result(profile)
                if r2 and r2.get("state") in _CREATE_FAILED:
                    result = r2
                    noi(f"[{name}] create-failed: {r2.get('detail') or ''}")
                    made = None
                    break
                now_ids, now_pages = _managed_page_ids(account)
                if now_ids is None:
                    break
                moi = [p for p in now_pages if str(p.get("id")) not in base_ids]
                for p in moi:
                    nn = (p.get("name") or "").lower()
                    if name.lower() in nn or nn in name.lower():
                        made = p
                        break
                made = made or (moi[0] if moi else None)
                if made:
                    break
    finally:
        try:
            manager.close(account, wait=10.0)
        except OSError:
            pass

    kq = {"ten": name, "created": False, "page_id": "", "note": ""}
    st = result.get("state") if result else None

    if not submit:
        if st == "filled-ready":
            kq["note"] = "chạy thử: đã điền form, chưa bấm Tạo"
            return kq
        _raise_form_error(st, result)

    # DA BAM Tao ma xac minh trong luc browser mo chua thay page (cookie cu / FB cham) ->
    # doc cookie TUOI tu profile (gio da dong, doc duoc) roi liet ke lai managed pages, retry.
    if st in _CREATE_FAILED:
        # FB tu choi tao (hop "Không thể tạo Trang"): KHONG phai "rat co the da tao" — bao hong ro rang.
        raise CreatePageError("Facebook KHÔNG TẠO được Trang: "
                              + ((result or {}).get("detail") or "").replace(
                                  "Facebook báo không thể tạo Trang: ", ""))
    if made is None and base_ids is not None and st in _CLICKED:
        tuoi = _cookie_tuoi(manager, account)
        noi(f"[{name}] xác minh lại bằng cookie tươi sau khi đóng trình duyệt...")
        for _ in range(10):
            now_ids, now_pages = _managed_page_ids(account, cookie=tuoi)
            if now_ids is not None:
                moi = [pg for pg in now_pages if str(pg.get("id")) not in base_ids]
                for pg in moi:
                    nn = (pg.get("name") or "").lower()
                    if name.lower() in nn or nn in name.lower():
                        made = pg
                        break
                made = made or (moi[0] if moi else None)
            if made:
                break
            time.sleep(2)

    if made:
        kq["created"] = True
        kq["page_id"] = str(made.get("id") or "")
        noi(f"[{name}] ✓ ĐÃ TẠO (id {kq['page_id']}).")
        return kq

    # DA BAM Tao (create-clicked/blocked/done) nhung khong lay duoc id: Facebook rat co the DA TAO.
    # KHONG bao loi oan (nguoi dung phan anh 'tao duoc van bao loi'), KHONG de batch tao lai -> trung.
    if st in _CLICKED:
        kq["created"] = True
        kq["note"] = ("đã bấm Tạo nhưng chưa lấy được id page (Facebook chậm cập nhật) — "
                      "rất có thể ĐÃ TẠO, kiểm tra lại; sẽ không tạo trùng.")
        noi(f"[{name}] ✓ đã bấm Tạo — coi như ĐÃ TẠO (chưa lấy được id).")
        return kq
    if st in _PRECLICK_BAD or st is None:
        _raise_form_error(st, result)     # checkpoint/logged-out/form -> dung loai
    raise CreatePageError(
        "Không tạo được page. Nếu acc còn là CÁ NHÂN, Facebook sẽ chặn — "
        "phải bật 'chế độ chuyên nghiệp' cho acc trước khi tạo.")


def _safe_json(raw: str) -> dict:
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except (ValueError, TypeError):
        return {}


#: Trang thai ket thuc cua lenh tra cuu hang muc.
_CAT_BAD = {"no-form", "no-category-input", "error", "checkpoint", "logged-out"}

#: FB tim MO: het ket qua khop thi DON danh sach mac dinh nay vao duoi (da thay
#: 5/9: 'trà sữa' -> 1 khop + 6 mac dinh). Cat phan don de bang chon/cache khong rac.
_DEFAULT_TAIL = {"dịch vụ địa phương", "mua sắm & bán lẻ", "thể thao và giải trí",
                 "bất động sản", "pháp lý", "nhà hàng"}


def _strip_default_tail(names: list) -> list:
    """Bo chuoi >= 2 muc mac dinh LIEN TIEP o cuoi danh sach (phan FB don them).

    Mot muc mac dinh le o cuoi thi giu -- co the la ket qua that (vd tim 'nhà'
    ra 'Nhà hàng' o cuoi).
    """
    n = len(names)
    while n > 0 and str(names[n - 1]).strip().lower() in _DEFAULT_TAIL:
        n -= 1
    return list(names) if len(names) - n < 2 else list(names[:n])


def search_categories(manager, account, queries, timeout: float = 240.0,
                      log: Optional[Callable[[str], None]] = None) -> dict:
    """Hoi Facebook danh sach hang muc goi y cho tung chuoi trong ``queries``.

    Mo trang tao page bang acc (BINH THUONG), agent go tung chuoi vao o Hang muc
    roi doc danh sach goi y (KHONG bam Tao). Tra ve {chuoi: [ten hang muc]}.
    Chuoi rong -> danh sach mac dinh FB hien khi chua go gi. Dung cho bang
    "Chon hang muc": nguoi dung chon dung chu FB dang co thay vi go tay.
    """
    noi = log or (lambda _m: None)
    qs = [str(q or "").strip() for q in (queries or [""])] or [""]
    profile = manager.profile_dir(account)
    manager.close(account, wait=8.0)
    clear_create(profile)
    put_create_command(profile, action="catsearch", queries=qs,
                       delay=3000, formTimeout=35000)
    noi(f"[{account.id}] mở trang tạo page để hỏi hạng mục Facebook gợi ý...")
    manager.launch(account, url=CREATE_URL)
    result = None
    tien_do = None
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            r = read_create_result(profile)
            if r:
                st = r.get("state")
                if st == "cat-progress" and r.get("detail") != tien_do:
                    tien_do = r.get("detail")
                    noi(f"[{account.id}] {tien_do}")
                if st == "cat-list" or st in _CAT_BAD:
                    result = r
                    break
            time.sleep(0.5)
    finally:
        try:
            manager.close(account, wait=8.0)
        except OSError:
            pass
    st = result.get("state") if result else None
    if st != "cat-list":
        _raise_form_error(st, result)
    data = _safe_json((result or {}).get("detail") or "")
    return {q: _strip_default_tail(
                [str(x).strip() for x in (data.get(q) or []) if str(x).strip()])
            for q in qs}


# ---- kho hang muc da biet --------------------------------------------------
#: Danh sach hang muc FB (tieng Viet) di kem tool -- lay tu chinh goi y cua FB.
CATEGORY_ASSET = "hang_muc_fb.txt"
#: Cache trong data/: hang muc FB tra ve them trong luc dung (bang "Hoi Facebook").
CATEGORY_CACHE = "hang_muc_fb.json"


def _cache_path() -> str:
    import os
    from core.config import TOOL_DIR
    return os.path.join(TOOL_DIR, "data", CATEGORY_CACHE)


def _dedupe(names) -> list[str]:
    out, seen = [], set()
    for n in names:
        n = str(n or "").strip()
        k = n.lower()
        if n and k not in seen:
            seen.add(k)
            out.append(n)
    return out


def load_known_categories() -> list[str]:
    """Hang muc da biet = file di kem tool + cache. Bo trung, giu thu tu."""
    names: list[str] = []
    try:
        from core.autoconfig import _asset
        names += _asset(CATEGORY_ASSET).splitlines()
    except Exception:  # noqa: BLE001 - thieu file di kem thi van chay bang cache
        pass
    try:
        with open(_cache_path(), encoding="utf-8") as fh:
            extra = json.load(fh)
        if isinstance(extra, list):
            names += extra
    except (OSError, ValueError):
        pass
    return _dedupe(names)


def remember_categories(names) -> None:
    """Ghi them hang muc FB vua tra ve vao cache de lan sau bang chon co san."""
    import os
    names = _dedupe(names)
    if not names:
        return
    path = _cache_path()
    cu: list = []
    try:
        with open(path, encoding="utf-8") as fh:
            cu = json.load(fh)
        if not isinstance(cu, list):
            cu = []
    except (OSError, ValueError):
        cu = []
    moi = _dedupe(list(cu) + names)
    if moi == cu:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(moi, fh, ensure_ascii=False, indent=1)


#: Trang profile cua chinh acc (/me tu chuyen sang profile.php?id=...).
PROFILE_URL = "https://www.facebook.com/me"

_PRO_OK = {"promode-done", "already-pro"}
_PRO_BAD = {"no-dots", "no-pro-item", "no-confirm", "no-form", "error",
            "checkpoint", "logged-out"}


def enable_professional(manager, account, timeout: float = 120.0,
                        log: Optional[Callable[[str], None]] = None) -> dict:
    """Bat "che do chuyen nghiep" cho acc ca nhan (menu ... tren profile -> Bat).

    Dung chung agent + bridge voi tao page (launch BINH THUONG, click bang
    setHandlingUserInput). Day la thao tac cai dat thuong, khong bi FB chan nhu
    tao page. Tra ve {id, done, note}.
    """
    noi = log or (lambda _m: None)
    profile = manager.profile_dir(account)
    manager.close(account, wait=8.0)
    clear_create(profile)
    put_create_command(profile, action="promode", delay=3000, formTimeout=22000, markWait=10000)
    if in_page_mode(account):
        noi(f"[{account.id}] acc đang ở CHẾ ĐỘ TRANG — sẽ tự chuyển về hồ sơ cá nhân trước.")
    noi(f"[{account.id}] mở profile để bật chế độ chuyên nghiệp...")
    manager.launch(account, url=PROFILE_URL)

    terminal = _PRO_OK | _PRO_BAD
    seen: set = set()
    result = None
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            r = read_create_result(profile)
            if r:
                st = r.get("state")
                if st and st not in seen:
                    seen.add(st)
                    noi(f"[{account.id}] {st}"
                        + (f": {r.get('detail')}" if r.get("detail") else ""))
                if st in terminal:
                    result = r
                    break
            time.sleep(0.5)
    finally:
        try:
            manager.close(account, wait=10.0)
        except OSError:
            pass

    kq = {"id": account.id, "done": False, "note": ""}
    if result is None:
        raise CreatePageError("Agent không phản hồi (chờ hết giờ).")
    st = result.get("state")
    if st == "promode-done":
        kq["done"] = True
        noi(f"[{account.id}] ✓ ĐÃ BẬT chế độ chuyên nghiệp.")
    elif st == "already-pro":
        kq["done"] = True
        kq["note"] = "acc đã ở chế độ chuyên nghiệp từ trước"
        noi(f"[{account.id}] acc đã chuyên nghiệp sẵn.")
    elif st == "checkpoint":
        raise AccountBlockedError(
            "ACC BỊ CHECKPOINT — Facebook giữ acc lại để xác minh. Đăng nhập "
            "acc bằng tay để gỡ checkpoint rồi thử lại.")
    elif st == "logged-out":
        raise AccountBlockedError(
            "ACC ĐÃ BỊ ĐĂNG XUẤT — cookie không còn dùng được. Đăng nhập lại acc.")
    else:
        raise CreatePageError(f"{st}: {result.get('detail', '')}".strip(": "))
    if kq["done"]:
        # Ghi nho vao acc -> cot "Chuyen nghiep" o tab quan ly acc = Bật; lan tao page
        # sau bo qua buoc kiem/bat. Nguoi goi luu store + refresh bang.
        try:
            from . import store as _store
            account.pro_mode = _store.PRO_BAT
        except Exception:  # noqa: BLE001
            pass
    return kq


def expand_names(names: list[str], count: int) -> list[str]:
    """Nhan danh sach ten cho DU ``count`` page.

    Ten goc giu nguyen, thieu thi them "Ten 2", "Ten 3"... theo vong (moi ten
    goc deu duoc dung). ``count`` <= 0 -> giu nguyen; count < so ten -> lay
    ``count`` ten dau. Khong sinh ten trung.
    """
    base = parse_names("\n".join(names))
    if count <= 0 or not base:
        return base
    if count <= len(base):
        return base[:count]
    seen, ra = set(base), list(base)
    k = 2
    while len(ra) < count:
        for ten in base:
            if len(ra) >= count:
                break
            moi = f"{ten} {k}"
            if moi not in seen:
                seen.add(moi)
                ra.append(moi)
        k += 1
    return ra


def parse_names(text: str) -> list[str]:
    """Moi dong mot ten fanpage. Bo dong trong va trung (giu thu tu)."""
    seen, ra = set(), []
    for line in (text or "").splitlines():
        ten = line.strip()
        if ten and ten not in seen:
            seen.add(ten)
            ra.append(ten)
    return ra
