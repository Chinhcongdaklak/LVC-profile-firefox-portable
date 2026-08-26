"""Cai proxy thang vao thu muc app cua Firefox bang co che AutoConfig.

Vi sao khong dung addon: ban Firefox Portable la kenh ``mozilla-release``, bat
buoc addon phai duoc Mozilla ky so -- addon tu viet khong cai duoc, va pref
``xpinstall.signatures.required`` bi bo qua tren kenh nay. AutoConfig la duong
duy nhat chay duoc ngay ma khong can ky.

Vi sao khong de Firefox tro vao relay noi bo: relay chi song trong tien trinh
tool va nghe tren mot cong ngau nhien, nen mo trinh duyet luc tool da tat (hoac
vua khoi dong lai) la tro vao mot cong da chet -> mat mang. AutoConfig bam thang
vao thu muc profile nen mo kieu gi cung chay.

Hai file duoc ghi vao MOI thu muc ``App/Firefox*`` co firefox.exe:

    App/<ffdir>/defaults/pref/autoconfig.js   <- kich hoat, tro toi mozilla.cfg
    App/<ffdir>/mozilla.cfg                   <- khoa pref proxy + nap user/pass

Luu y: mat khau proxy nam dang chu thuong trong mozilla.cfg. Firefox khong co
cach nao nhet mat khau proxy ma khong lo o dau do, day la danh doi bat buoc.
"""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import sys
from typing import Optional

from .proxy import Proxy
from .store import Identity

CFG_NAME = "mozilla.cfg"
PREF_NAME = "autoconfig.js"
DEFAULT_REALM = "proxy"

# Hai file cua lop va mui gio, duoc chep canh firefox.exe.
SHIM_NAME = "tz_shim.js"    # process script, chay trong tien trinh noi dung
PATCH_NAME = "tz_patch.js"  # lop va thuc su, chay trong tung trang


def _asset(name: str) -> str:
    """Doc mot file trong core/assets (chay ca khi da dong goi bang PyInstaller)."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(base, "assets", name),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", name),
    ):
        if os.path.isfile(candidate):
            with open(candidate, "r", encoding="utf-8") as fh:
                return fh.read()
    raise FileNotFoundError(f"Thiếu file {name} trong core/assets.")

# Firefox doc pref nay TRUOC khi chay mozilla.cfg.
# sandbox_enabled=false de mozilla.cfg duoc dung Services/Components.
_AUTOCONFIG_JS = """// Duoc tao tu dong boi Quan Ly Firefox Portable -- dung sua tay.
pref("general.config.filename", "mozilla.cfg");
pref("general.config.obscure_value", 0);
pref("general.config.sandbox_enabled", false);
"""

# Khoi JS nap san user/pass proxy vao Password Manager luc khoi dong.
# Ghi chu ky thuat (Firefox 154):
#   - LoginManager.findLogins() DA BI GO BO -> phai dung searchLoginsAsync().
#   - addLogin() cung da nhuong cho addLoginAsync().
#   - Phai cho Services.logins.initializationPromise, neu khong login manager
#     chua san sang o thoi diem autoconfig chay.
#   - Login proxy phai luu dung dang moz-proxy://<host>:<port> kem dung httpRealm
#     lay tu header 'Proxy-Authenticate: Basic realm="..."'. Sai realm la Firefox
#     van hien hop thoai hoi mat khau.
_SEED_JS = r"""
(function () {
  if (!PROXY_USER && !PROXY_PASS) { return; }   // proxy khong can dang nhap
  var ORIGIN = "moz-proxy://" + PROXY_HOST + ":" + PROXY_PORT;
  var LOG = [];
  function note(m) { LOG.push(m); }

  var SVC = null, CMP = null;
  try { SVC = Services; } catch (e) {}
  if (!SVC) {
    try { SVC = ChromeUtils.importESModule("resource://gre/modules/Services.sys.mjs").Services; }
    catch (e) {}
  }
  try { CMP = Components; } catch (e) {}

  function svc(contract, iface, prop) {
    if (SVC && prop && SVC[prop]) return SVC[prop];
    if (CMP) return CMP.classes[contract].getService(CMP.interfaces[iface]);
    throw new Error("khong truy cap duoc Services/Components");
  }

  function flush() {
    var text = LOG.join("\r\n") + "\r\n";
    try {
      IOUtils.writeUTF8(PathUtils.join(PathUtils.profileDir, "proxy-autoconfig.log"), text);
      return;
    } catch (e) {}
    try {
      var f = CMP.classes["@mozilla.org/file/directory_service;1"]
                 .getService(CMP.interfaces.nsIProperties)
                 .get("ProfD", CMP.interfaces.nsIFile);
      f.append("proxy-autoconfig.log");
      var os = CMP.classes["@mozilla.org/network/file-output-stream;1"]
                  .createInstance(CMP.interfaces.nsIFileOutputStream);
      os.init(f, 0x02 | 0x08 | 0x20, 420, 0);
      var cv = CMP.classes["@mozilla.org/intl/converter-output-stream;1"]
                  .createInstance(CMP.interfaces.nsIConverterOutputStream);
      cv.init(os, "UTF-8"); cv.writeString(text); cv.close();
    } catch (e) {}
  }

  function seed() {
    var lm, want;
    try {
      lm = svc("@mozilla.org/login-manager;1", "nsILoginManager", "logins");
      var LoginInfo = CMP.Constructor("@mozilla.org/login-manager/loginInfo;1",
                                      CMP.interfaces.nsILoginInfo, "init");
      // (origin, formActionOrigin, httpRealm, username, password, userField, passField)
      want = new LoginInfo(ORIGIN, null, PROXY_REALM, PROXY_USER, PROXY_PASS, "", "");
    } catch (e) { note("LOI khoi tao: " + e); flush(); return; }

    function add() {
      try {
        if (typeof lm.addLoginAsync === "function") {
          lm.addLoginAsync(want).then(
            function () { note("OK: da them login proxy cho " + ORIGIN); flush(); },
            function (e) { note("LOI them login: " + e); flush(); }
          );
        } else {
          lm.addLogin(want);
          note("OK: da them login proxy cho " + ORIGIN);
          flush();
        }
      } catch (e) { note("LOI them login: " + e); flush(); }
    }

    function review(found) {
      try {
        for (var i = 0; i < found.length; i++) {
          if (found[i].username === PROXY_USER) {
            if (found[i].password === PROXY_PASS) {
              note("OK: login da dung san, khong doi gi"); flush(); return;
            }
            lm.modifyLogin(found[i], want);
            note("OK: mat khau da doi -> da cap nhat"); flush(); return;
          }
        }
        add();
      } catch (e) { note("LOI review: " + e); flush(); }
    }

    try {
      if (typeof lm.searchLoginsAsync === "function") {
        lm.searchLoginsAsync({ origin: ORIGIN, httpRealm: PROXY_REALM })
          .then(review, function (e) { note("searchLoginsAsync loi: " + e); add(); });
      } else {
        add();
      }
    } catch (e) { note("searchLoginsAsync nem loi: " + e); add(); }
  }

  function start() {
    try {
      var lm = svc("@mozilla.org/login-manager;1", "nsILoginManager", "logins");
      if (lm.initializationPromise) { lm.initializationPromise.then(seed, seed); return; }
    } catch (e) { note("initializationPromise: " + e); }
    seed();
  }

  var started = false;
  function once() { if (started) return; started = true; start(); }

  try {
    var obs = svc("@mozilla.org/observer-service;1", "nsIObserverService", "obs");
    var L = { observe: function () { try { obs.removeObserver(L, "final-ui-startup"); } catch (e) {} once(); } };
    obs.addObserver(L, "final-ui-startup", false);
  } catch (e) { note("observer loi: " + e); once(); }

  // luoi an toan neu observer khong ban
  try {
    var t = CMP.classes["@mozilla.org/timer;1"].createInstance(CMP.interfaces.nsITimer);
    t.initWithCallback({ notify: once }, 8000, CMP.interfaces.nsITimer.TYPE_ONE_SHOT);
  } catch (e) {}
})();
"""


# Dat ten cua so trinh duyet theo thu muc profile, de mo nhieu acc cung luc con
# biet cua so nao la cua acc nao (nhin duoc ca o thanh tac vu va Alt-Tab).
#
# ``titlepreface`` la thuoc tinh Firefox dung san cho viec nay -- chinh no lam
# nen chu "Private Browsing" o cua so an danh. Dat thuoc tinh nay trong luc cua
# so dang tai la du, Firefox se ghep vao tieu de o lan cap nhat ke tiep.
_TITLE_JS = r"""
(function () {
  if (!PROFILE_LABEL) { return; }

  // (1) Ghi vao thanh tieu de HDH -> hien o thanh tac vu / Alt-Tab.
  function applyTitle(win) {
    try {
      var de = win.document.documentElement;
      var existing = de.getAttribute("titlepreface") || "";
      if (existing.indexOf(PROFILE_LABEL) === -1) {
        de.setAttribute("titlepreface", PROFILE_LABEL + " — " + existing);
        if (win.gBrowser && typeof win.gBrowser.updateTitlebar === "function") {
          win.gBrowser.updateTitlebar();
        } else if (typeof win.updateTitlebar === "function") {
          win.updateTitlebar();
        }
      }
    } catch (e) {}
  }

  // (2) Chen mot nhan mau vao thanh cong cu -> NHIN THAY NGAY tren giao dien,
  //     ke ca khi Firefox an thanh tieu de HDH (tab nam tren cung).
  function applyBadge(win) {
    try {
      var doc = win.document;
      if (doc.getElementById("qlfp-profile-badge")) { return; }
      var host = doc.getElementById("nav-bar") || doc.getElementById("TabsToolbar");
      if (!host) { return; }

      var make = doc.createXULElement
        ? function (t) { return doc.createXULElement(t); }
        : function (t) { return doc.createElement(t); };

      var badge = make("label");
      badge.id = "qlfp-profile-badge";
      badge.setAttribute("value", PROFILE_LABEL);
      badge.setAttribute("crop", "end");
      badge.setAttribute("tooltiptext", "Profile: " + PROFILE_LABEL);
      badge.style.cssText =
        "color:#fff;background:#1f6aa5;padding:2px 10px;margin:0 6px;" +
        "border-radius:8px;font-weight:700;align-self:center;max-width:280px;" +
        "-moz-user-select:none;";
      // Dat o dau nav-bar (canh nut tien/lui) cho de thay.
      host.insertBefore(badge, host.firstChild);
    } catch (e) {}
  }

  function apply(win) { applyTitle(win); applyBadge(win); }

  try {
    var listener = {
      onOpenWindow: function (xulWin) {
        var win = xulWin.docShell.domWindow;
        win.addEventListener("load", function onload() {
          win.removeEventListener("load", onload);
          if (win.location.href.indexOf("browser.xhtml") === -1) { return; }
          apply(win);
          // Thanh cong cu co the dung xong sau mot nhip -> thu lai vai lan.
          win.setTimeout(function () { apply(win); }, 1000);
          win.setTimeout(function () { apply(win); }, 3000);
        });
      },
      onCloseWindow: function () {},
      onWindowTitleChange: function () {}
    };
    Services.wm.addListener(listener);

    // Cua so dau tien co the da mo xong truoc khi listener kip dang ky.
    var e = Services.wm.getEnumerator("navigator:browser");
    while (e.hasMoreElements()) {
      var w = e.getNext();
      if (w.document && w.document.readyState === "complete") { apply(w); }
      else { apply(w); w.setTimeout(function(){ apply(w); }, 1500); }
    }
  } catch (e) {}
})();
"""


def firefox_dirs(app_dir: str) -> list[str]:
    """Cac thu muc ``App/Firefox*`` that su co firefox.exe.

    Ghi vao tat ca de du launcher chay ban 32 hay 64 bit thi proxy van an.
    """
    base = os.path.join(app_dir, "App")
    found = []
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return found
    for name in names:
        if not name.lower().startswith("firefox"):
            continue
        candidate = os.path.join(base, name)
        if os.path.isfile(os.path.join(candidate, "firefox.exe")):
            found.append(candidate)
    return found


def detect_realm(proxy: Proxy, timeout: float = 6.0) -> str:
    """Hoi proxy xem no khai bao realm gi (khong gui user/pass).

    Sai realm la Firefox se van hoi mat khau, nen phai lay dung chuoi that.
    Khong hoi duoc thi tra ve ``"proxy"`` -- gia tri 3proxy hay dung.
    """
    if not proxy.enabled or proxy.is_socks:
        return DEFAULT_REALM
    try:
        with socket.create_connection((proxy.host, proxy.port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(
                b"GET http://example.com/ HTTP/1.1\r\n"
                b"Host: example.com\r\n"
                b"Connection: close\r\n\r\n"
            )
            data = b""
            while len(data) < 4096:
                chunk = sock.recv(1024)
                if not chunk:
                    break
                data += chunk
    except OSError:
        return DEFAULT_REALM

    match = re.search(
        rb'Proxy-Authenticate:\s*\w+\s+realm="([^"]*)"', data, re.IGNORECASE
    )
    if match:
        return match.group(1).decode("latin-1", "replace")
    return DEFAULT_REALM


def _pref_lines(proxy: Proxy) -> str:
    lines = [
        'lockPref("network.proxy.type", 1);',
        'lockPref("network.proxy.no_proxies_on", "localhost, 127.0.0.1");',
        'lockPref("network.proxy.allow_hijacking_localhost", false);',
        # Proxy chet thi KHONG tu rot ve mang that (chong lo IP goc).
        'lockPref("network.proxy.failover_direct", false);',
    ]
    if proxy.is_socks:
        lines += [
            f'lockPref("network.proxy.socks", {json.dumps(proxy.host)});',
            f'lockPref("network.proxy.socks_port", {proxy.port});',
            'lockPref("network.proxy.socks_version", '
            f'{4 if proxy.scheme == "socks4" else 5});',
            # De proxy phan giai ten mien, tranh ro ri DNS.
            'lockPref("network.proxy.socks_remote_dns", true);',
        ]
    else:
        lines += [
            f'lockPref("network.proxy.http", {json.dumps(proxy.host)});',
            f'lockPref("network.proxy.http_port", {proxy.port});',
            f'lockPref("network.proxy.ssl", {json.dumps(proxy.host)});',
            f'lockPref("network.proxy.ssl_port", {proxy.port});',
            'lockPref("network.proxy.share_proxy_settings", true);',
        ]
    lines += [
        "",
        "// Chong ro ri IP that ngoai duong proxy",
        'lockPref("media.peerconnection.enabled", false);',
        'lockPref("network.dns.disablePrefetch", true);',
        'lockPref("network.predictor.enabled", false);',
        'lockPref("browser.send_pings", false);',
        "",
        "// Tu dong gui user/pass proxy da luu, khong hien hop thoai",
        'lockPref("signon.autologin.proxy", true);',
        'defaultPref("signon.rememberSignons", true);',
    ]
    return "\n".join(lines)


def _identity_prefs(identity: "Identity") -> str:
    """Pref khop ngon ngu va vi tri voi quoc gia cua IP proxy."""
    lines: list[str] = []

    if identity.accept_languages:
        lines += [
            "",
            "// Ngon ngu: doi ca header Accept-Language lan navigator.language(s)",
            f'lockPref("intl.accept_languages", {json.dumps(identity.accept_languages)});',
            # Khong lay dinh dang ngay/gio tu Windows, neu khong la lo may that.
            'lockPref("intl.regional_prefs.use_os_locales", false);',
        ]

    return "\n".join(lines)


# Nap process script cua lop va mui gio. Phai chay o tien trinh cha (mozilla.cfg)
# thi ppmm moi day duoc script sang moi tien trinh noi dung.
_SHIM_LOADER_JS = """
// Lop va mui gio: bom Date/Intl/Temporal cua tung trang ve mui gio cua proxy.
try {
  var shimFile = Services.dirsvc.get("GreD", Ci.nsIFile);
  shimFile.append("%(shim)s");
  if (shimFile.exists()) {
    Services.ppmm.loadProcessScript(Services.io.newFileURI(shimFile).spec, true);
  }
} catch (e) {
  Services.console.logStringMessage("tz shim loi: " + e);
}
"""


def render(
    proxy: Proxy,
    realm: str = DEFAULT_REALM,
    label: str = "",
    identity: Optional[Identity] = None,
    use_shim: bool = False,
) -> str:
    """Sinh noi dung mozilla.cfg cho proxy, ten cua so va danh tinh (mui gio/ngon ngu).

    ``use_shim=False`` (mac dinh): KHONG tiem JS va Date/Intl vao trang. Mui gio
    da duoc dat o muc engine bang bien moi truong TZ luc khoi dong (xem
    ProfileManager.launch), nen shim la thua va chi lam lo dau vet "trinh duyet bi
    sua" cho cac he chong bot (botguard cua Google). Chi bat khi that su can va
    (vi du mo Firefox khong qua tool).
    """
    identity = identity or Identity()
    # DONG DAU TIEN cua mozilla.cfg luon bi Firefox bo qua -> phai la comment.
    parts = [
        "// DONG DAU TIEN NAY BI FIREFOX BO QUA - KHONG DUOC XOA\n"
        "//\n"
        "// Duoc tao tu dong boi Quan Ly Firefox Portable.\n"
        "// Moi thay doi thu cong se bi ghi de o lan mo profile ke tiep.\n"
        "// Nhat ky chay: Data\\profile\\proxy-autoconfig.log\n",
        f"var PROFILE_LABEL = {json.dumps(label)};",
    ]

    if proxy.enabled:
        parts += [
            "",
            f"var PROXY_HOST  = {json.dumps(proxy.host)};",
            f"var PROXY_PORT  = {proxy.port};",
            f"var PROXY_USER  = {json.dumps(proxy.username)};",
            f"var PROXY_PASS  = {json.dumps(proxy.password)};",
            f"var PROXY_REALM = {json.dumps(realm)};",
            "",
            _pref_lines(proxy),
            "",
            _SEED_JS,
        ]

    if identity.enabled:
        # Ngon ngu (intl.accept_languages) van set qua pref, ap dung o muc engine.
        parts.append(_identity_prefs(identity))
    if identity.timezone and use_shim:
        parts.append(_SHIM_LOADER_JS % {"shim": SHIM_NAME})

    parts.append(_TITLE_JS)
    return "\n".join(parts)


def install(
    app_dir: str,
    proxy: Proxy,
    realm: Optional[str] = None,
    label: str = "",
    identity: Optional[Identity] = None,
    use_shim: bool = False,
) -> list[str]:
    """Cai AutoConfig vao thu muc app: proxy + ten cua so.

    Khong co proxy lan ten thi go han ra. Tra ve danh sach thu muc da ghi.
    """
    identity = identity or Identity()
    if not proxy.enabled and not label and not identity.enabled:
        uninstall(app_dir)
        return []

    targets = firefox_dirs(app_dir)
    if not targets:
        return []

    if realm is None:
        realm = detect_realm(proxy) if proxy.needs_auth else DEFAULT_REALM
    content = render(proxy, realm, label, identity, use_shim)

    shim = ""
    patch = ""
    if identity.timezone and use_shim:
        shim = _asset(SHIM_NAME).replace("__TZ_TARGET__", identity.timezone)
        patch = _asset(PATCH_NAME)

    written = []
    for folder in targets:
        pref_dir = os.path.join(folder, "defaults", "pref")
        os.makedirs(pref_dir, exist_ok=True)
        _write(os.path.join(pref_dir, PREF_NAME), _AUTOCONFIG_JS)
        _write(os.path.join(folder, CFG_NAME), content)
        if shim:
            _write(os.path.join(folder, SHIM_NAME), shim)
            _write(os.path.join(folder, PATCH_NAME), patch)
        else:
            _remove_shim(folder)
        written.append(folder)
    return written


def _remove_shim(folder: str) -> None:
    for name in (SHIM_NAME, PATCH_NAME):
        try:
            os.remove(os.path.join(folder, name))
        except OSError:
            pass


def uninstall(app_dir: str) -> None:
    """Go AutoConfig (dung khi bo proxy) de Firefox chay truc tiep tro lai."""
    for folder in firefox_dirs(app_dir):
        for path in (
            os.path.join(folder, CFG_NAME),
            os.path.join(folder, "defaults", "pref", PREF_NAME),
        ):
            try:
                os.remove(path)
            except OSError:
                pass
        _remove_shim(folder)


def is_installed(app_dir: str) -> bool:
    folders = firefox_dirs(app_dir)
    return bool(folders) and all(
        os.path.isfile(os.path.join(f, CFG_NAME)) for f in folders
    )


def basic_auth_header(proxy: Proxy) -> str:
    token = base64.b64encode(
        f"{proxy.username}:{proxy.password}".encode("utf-8")
    ).decode("ascii")
    return "Basic " + token


def _write(path: str, content: str) -> None:
    # Firefox doc mozilla.cfg dang UTF-8 khong BOM.
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
