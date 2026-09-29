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
import shutil
import socket
import sys
from typing import Optional

from . import autostart
from .proxy import Proxy
from .store import Identity

CFG_NAME = "mozilla.cfg"
PREF_NAME = "autoconfig.js"
DEFAULT_REALM = "proxy"

# Hai file cua lop va mui gio, duoc chep canh firefox.exe.
SHIM_NAME = "tz_shim.js"    # process script, chay trong tien trinh noi dung
PATCH_NAME = "tz_patch.js"  # lop va thuc su, chay trong tung trang
#: Dieu khien composer cua Business Suite de dang video.
AGENT_NAME = "fbupload_agent.js"
#: Agent tao fanpage -- bridge RIENG (qlfpc:*/qlfp-create*), khong dam agent dang bai.
CREATE_AGENT_NAME = "fbcreate_agent.js"
#: Agent dang nhap web (bridge RIENG qlfpwl:*/qlfp-weblogin*), khong dam agent khac.
LOGIN_AGENT_NAME = "fblogin_agent.js"
#: Agent nhan tin (bridge RIENG qlfpm:*/qlfp-msg*), khong dam 3 agent kia.
CHAT_AGENT_NAME = "fbchat_agent.js"
#: Agent tuong tac (xem reel + like) — bridge RIENG qlfpw:*/qlfp-watch*.
WATCH_AGENT_NAME = "fbwatch_agent.js"
#: Agent add page vao BM (bridge RIENG qlfpbm:*/qlfp-bm*), khong dam 4 agent kia.
BM_AGENT_NAME = "fbbm_agent.js"
#: Agent tu bam "Bo qua" tren checkpoint MEM (luon chay, khong can lenh).
SKIP_AGENT_NAME = "fbskip_agent.js"
SKIP_LOG = "qlfp-skip.log"
#: Agent dang nhap X.com bang Google (bridge RIENG qlfpxl:*/qlfp-xlogin*).
XLOGIN_AGENT_NAME = "xlogin_agent.js"
#: Agent dang nhap NordVPN qua my.nordaccount.com (bridge RIENG qlfpn:*/qlfp-nord*).
NORD_AGENT_NAME = "nordlogin_agent.js"
XPOST_AGENT_NAME = "xpost_agent.js"

def _asset_path(name: str) -> str:
    """Duong dan toi mot file trong core/assets (chay ca khi da dong goi)."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(base, "assets", name),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", name),
    ):
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(f"Thiếu {name} trong core/assets.")


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


# Addon chep san vao <profile>/extensions/ bi Firefox coi la "cai tu ben ngoai",
# mac dinh CAI NHUNG DE TAT va cho nguoi dung tu bat. Hai pref nay bao Firefox
# quet thu muc do va bat luon -- da do: khong co chung thi addon nam im.
_EXTENSION_PREFS = """
// Nhan addon duoc chep san vao thu muc profile
defaultPref("extensions.autoDisableScopes", 0);
defaultPref("extensions.startupScanScopes", 15);
"""


# Ten file ket qua do trinh duyet tu ghi vao thu muc profile. Tool doc file nay
# de biet cookie vao duoc Facebook hay khong ma khong phai ngoi doi.
PROBE_NAME = "qlfp-login.json"
PROBE_LOG = "qlfp-login.log"   # nhat ky de soi khi khong ra ket qua

# Bao cho tool biet NGAY khi trang Facebook tai xong la vao duoc hay khong.
#
# Vi sao khong doc cookies.sqlite: Firefox gom cac thay doi cookie roi moi ghi
# xuong dia theo dot, nen nhin vao file la thay cham vai chuc giay. O day doc
# thang kho cookie TRONG BO NHO (Services.cookies) ngay khi trang tai xong ->
# biet ket qua sau 1-2 giay thay vi 30 giay.
#
# Dau hieu: phien chet thi Facebook xoa c_user/xs va/hoac day sang trang dang
# nhap. Chay o muc chrome (khong dung toi noi dung trang) nen khong the lam
# crash tab nhu kieu tiem script vao trang.
_PROBE_JS = r"""
(function () {
  var CMP = null, SVC = null;
  try { CMP = Components; } catch (e) {}
  try { SVC = Services; } catch (e) {}
  if (!CMP || !SVC) { return; }

  var MARK = "%(mark)s";
  var LOGF = "%(log)s";
  var DEAD_URL = /facebook\.com\/(login|checkpoint|recover|two_step)/i;
  var written = "";
  var lines = [];
  var finished = false;   // chot xong roi thi thoi, dung ghi file nua

  // Ghi file: uu tien IOUtils, khong co thi dung luong file kieu cu.
  function put(name, text) {
    try {
      IOUtils.writeUTF8(PathUtils.join(PathUtils.profileDir, name), text);
      return true;
    } catch (e) {}
    try {
      var f = CMP.classes["@mozilla.org/file/directory_service;1"]
                 .getService(CMP.interfaces.nsIProperties)
                 .get("ProfD", CMP.interfaces.nsIFile);
      f.append(name);
      var os = CMP.classes["@mozilla.org/network/file-output-stream;1"]
                  .createInstance(CMP.interfaces.nsIFileOutputStream);
      os.init(f, 0x02 | 0x08 | 0x20, 420, 0);
      var cv = CMP.classes["@mozilla.org/intl/converter-output-stream;1"]
                  .createInstance(CMP.interfaces.nsIConverterOutputStream);
      cv.init(os, "UTF-8"); cv.writeString(text); cv.close();
      return true;
    } catch (e) {}
    return false;
  }

  function note(m) {
    lines.push(m);
    put(LOGF, lines.join("\r\n") + "\r\n");
  }

  // Toan bo cookie facebook trong BO NHO, dang "ten=gia_tri; ...". Trung ten
  // thi uu tien ban nam tren ".facebook.com" (ban goc, khong phai cua subdomain).
  function fbCookieHeader() {
    try {
      var list = SVC.cookies.cookies, map = {}, order = [];
      for (var i = 0; i < list.length; i++) {
        var c = list[i];
        if (!c.host || c.host.indexOf("facebook.com") === -1) { continue; }
        if (!(c.name in map)) { order.push(c.name); map[c.name] = c.value; }
        else if (c.host === ".facebook.com") { map[c.name] = c.value; }
      }
      var parts = [];
      for (var j = 0; j < order.length; j++) {
        parts.push(order[j] + "=" + map[order[j]]);
      }
      return parts.join("; ");
    } catch (e) { note("LOI gom cookie: " + e); return ""; }
  }

  function write(ok, why, done) {
    if (finished) { return; }
    // Kem luon chuoi cookie khi vao duoc: acc chet cookie ma nguoi dung dang
    // nhap tay xong thi tool doc file nay la lay lai duoc cookie moi ngay,
    // khong phai cho Firefox ghi cookies.sqlite xuong dia.
    var text = JSON.stringify({ ok: !!ok, final: !!done, why: why,
                                cookies: ok ? fbCookieHeader() : "" });
    if (text !== written) {
      written = text;
      note("bao: " + text.slice(0, 120));
      put(MARK, text);
    }
    // Chi ngung han khi da VAO DUOC va da chot. Con bao "chet" thi phai theo
    // doi tiep: nguoi dung co the dang nhap tay ngay trong phien nay, luc do
    // phai bao lai ket qua moi (kem cookie moi) de tool lay lai.
    if (done && ok) { finished = true; }
  }

  // Con giu ca c_user lan xs nghia la Facebook chua huy phien.
  function stillLoggedIn() {
    try {
      var list = SVC.cookies.cookies, user = false, xs = false;
      for (var i = 0; i < list.length; i++) {
        var c = list[i];
        if (!c.host || c.host.indexOf("facebook.com") === -1) { continue; }
        if (c.name === "c_user") { user = true; }
        else if (c.name === "xs") { xs = true; }
      }
      return user && xs;
    } catch (e) {
      note("LOI doc cookie: " + e);
      return true;    // khong doc duoc thi cho tiep, dung ket luan voi
    }
  }

  // Bi day sang /login la chac chan chet -- ket luan duoc ngay khong can cho.
  // Chi de soi trong nhat ky khi ket qua khong nhu mong doi.
  function fbCookieNames() {
    try {
      var list = SVC.cookies.cookies, names = [];
      for (var i = 0; i < list.length; i++) {
        if (list[i].host && list[i].host.indexOf("facebook.com") !== -1) {
          names.push(list[i].name);
        }
      }
      return names.length ? names.join(",") : "(khong co)";
    } catch (e) { return "LOI: " + e; }
  }

  // Checkpoint: bao "chua vao" nhung KHONG chot -- agent fbskip co the bam "Bo qua" (checkpoint
  // mem) roi trang chuyen tiep, luc do bao lai ok. Tool (verify_cookie_login) cho them khi why co "checkpoint".
  function judgeUrl(url) {
    if (!url || url.indexOf("facebook.com") === -1) { return; }
    if (/facebook\.com\/checkpoint/i.test(url)) { write(false, "checkpoint: " + url.slice(0, 120), false); return; }
    if (DEAD_URL.test(url)) { write(false, "bi day sang trang dang nhap", true); }
  }

  // CHI goi sau khi trang da tai xong. Goi som hon la doc nham: luc trang chua
  // tai, kho cookie chua duoc nap len nen c_user/xs nhin nhu da mat -> bao chet oan.
  function judgeLoaded(url, done) {
    if (!url || url.indexOf("facebook.com") === -1) { return; }
    if (/facebook\.com\/checkpoint/i.test(url)) { write(false, "checkpoint: " + url.slice(0, 120), false); return; }
    if (DEAD_URL.test(url)) { write(false, "bi day sang trang dang nhap", true); return; }
    if (!stillLoggedIn()) { write(false, "Facebook da xoa c_user/xs", true); return; }
    write(true, "vao duoc", done);
  }

  function watch(win) {
    try {
      if (win.__qlfpProbe) { return true; }
      if (!win.gBrowser || !win.gBrowser.addTabsProgressListener) { return false; }
      win.__qlfpProbe = true;
      var WPL = CMP.interfaces.nsIWebProgressListener;
      win.gBrowser.addTabsProgressListener({
        // Bi day sang /login thi biet ngay, khong doi tai xong.
        onLocationChange: function (browser, progress, request, location) {
          try { if (!finished && progress.isTopLevel) { judgeUrl(location.spec); } } catch (e) {}
        },
        onStateChange: function (browser, progress, request, flags) {
          try {
            if (finished || !progress.isTopLevel) { return; }
            if (!(flags & WPL.STATE_STOP) || !(flags & WPL.STATE_IS_NETWORK)) { return; }
            var url = browser.currentURI ? browser.currentURI.spec : "";
            note("tai xong: " + url + "  | tieu de: " + (browser.contentTitle || ""));
            note("cookie facebook: " + fbCookieNames());
            judgeLoaded(url, false);
            // Facebook co the huy phien them mot nhip sau khi trang tai xong ->
            // xem lai lan nua roi moi chot ket qua.
            win.setTimeout(function () { judgeLoaded(url, true); }, 2500);
          } catch (e) { note("LOI onStateChange: " + e); }
        },
        onProgressChange: function () {},
        onStatusChange: function () {},
        onSecurityChange: function () {},
        onRefreshAttempted: function () { return true; }
      });
      note("da gan bo theo doi vao cua so");
      return true;
    } catch (e) { note("LOI gan bo theo doi: " + e); }
    return false;
  }

  // gBrowser co the chua san sang ngay luc cua so "load" -> thu lai vai nhip.
  function watchSoon(win) {
    if (watch(win)) { return; }
    var n = 0;
    var again = function () {
      if (watch(win) || ++n > 40) { return; }
      win.setTimeout(again, 250);
    };
    win.setTimeout(again, 100);
  }

  try {
    note("bat dau theo doi dang nhap");
    SVC.wm.addListener({
      onOpenWindow: function (xulWin) {
        try {
          var win = xulWin.docShell.domWindow;
          win.addEventListener("load", function onload() {
            win.removeEventListener("load", onload);
            if (win.location.href.indexOf("browser.xhtml") === -1) { return; }
            watchSoon(win);
          });
        } catch (e) { note("LOI onOpenWindow: " + e); }
      },
      onCloseWindow: function () {},
      onWindowTitleChange: function () {}
    });
    var e = SVC.wm.getEnumerator("navigator:browser");
    while (e.hasMoreElements()) { watchSoon(e.getNext()); }
  } catch (e) { note("LOI dang ky: " + e); }
})();
""" % {"mark": PROBE_NAME, "log": PROBE_LOG}


# Tool dong trinh duyet bang cach ket lieu tien trinh, nen lan mo ke tiep Firefox
# tuong vua bi sap va hien trang "Restore Session" thay vi vao thang dia chi duoc
# giao -- da do: acc bi treo o do het thoi gian cho ma khong bao gio toi Facebook.
# Tat han phan phuc hoi phien thi mo lan nao cung vao thang trang can vao.
_STARTUP_PREFS = """
// Khong hoi phuc hoi phien sau khi bi ket lieu tien trinh
defaultPref("browser.sessionstore.resume_from_crash", false);
defaultPref("browser.sessionstore.max_resumed_crashes", 0);
defaultPref("toolkit.startup.max_resumed_crashes", -1);
// Khong chen trang gioi thieu / hoi trinh duyet mac dinh lam tre buoc dang nhap
defaultPref("browser.shell.checkDefaultBrowser", false);
defaultPref("browser.startup.homepage_override.mstone", "ignore");
defaultPref("startup.homepage_welcome_url", "");
defaultPref("startup.homepage_welcome_url.additional", "");
defaultPref("browser.aboutwelcome.enabled", false);
"""



# Cau noi cho agent dang video (core/assets/fbupload_agent.js).
#
# Agent chay trong tien trinh NOI DUNG de cham vao document cua trang, nhung tien
# trinh do bi he dieu hanh chan ghi dia -- da do: agent chay ma khong file nao
# duoc tao. Nen moi viec doc ghi file lam o day, trong tien trinh CHA, agent goi
# sang bang message manager.
_AGENT_LOADER_JS = """
(function () {
  var CMD = "qlfp-upload.json";
  var RESULT = "qlfp-upload-result.json";
  var DUMP = "qlfp-upload-dump.json";

  function profileFile(name) {
    var f = Services.dirsvc.get("ProfD", Ci.nsIFile);
    f.append(name);
    return f;
  }

  function readText(name) {
    try {
      var f = profileFile(name);
      if (!f.exists()) { return ""; }
      var stream = Cc["@mozilla.org/network/file-input-stream;1"]
        .createInstance(Ci.nsIFileInputStream);
      stream.init(f, 0x01, 0, 0);
      var conv = Cc["@mozilla.org/intl/converter-input-stream;1"]
        .createInstance(Ci.nsIConverterInputStream);
      conv.init(stream, "UTF-8", 0, 0);
      var out = "", chunk = {};
      while (conv.readString(4096, chunk) !== 0) { out += chunk.value; }
      conv.close();
      return out;
    } catch (e) { return ""; }
  }

  function writeText(name, text) {
    try {
      var f = profileFile(name);
      var out = Cc["@mozilla.org/network/file-output-stream;1"]
        .createInstance(Ci.nsIFileOutputStream);
      out.init(f, 0x02 | 0x08 | 0x20, 420, 0);
      var conv = Cc["@mozilla.org/intl/converter-output-stream;1"]
        .createInstance(Ci.nsIConverterOutputStream);
      conv.init(out, "UTF-8");
      conv.writeString(text);
      conv.close();
    } catch (e) {}
  }

  try {
    Services.ppmm.addMessageListener("qlfp:cmd", function () {
      return readText(CMD);
    });
    Services.ppmm.addMessageListener("qlfp:report", function (msg) {
      var data = msg.data || {};
      data.at = Date.now();
      writeText(RESULT, JSON.stringify(data));
    });
    Services.ppmm.addMessageListener("qlfp:dump", function (msg) {
      writeText(DUMP, JSON.stringify(msg.data || {}, null, 1));
    });

    // Doc file video ho tien trinh noi dung. Tien trinh do bi chan doc dia (da
    // do: nsIFile.exists() tra ve false ngay ca voi file co that), nen phai doc
    // o day roi gui noi dung sang.
    Services.ppmm.addMessageListener("qlfp:needfile", function (msg) {
      var path = (msg.data || {}).path || "";
      var tra = function (data) {
        try { Services.ppmm.broadcastAsyncMessage("qlfp:file", data); } catch (e) {}
      };
      try {
        var f = Cc["@mozilla.org/file/local;1"].createInstance(Ci.nsIFile);
        f.initWithPath(path);
        if (!f.exists()) { tra({ ok: false, error: "không thấy file: " + path }); return; }
        if (f.fileSize > 400 * 1024 * 1024) {
          tra({ ok: false, error: "file lớn hơn 400 MB, hãy dùng cách đăng Graph API" });
          return;
        }
        // Doc nhi phan bang luong co san. Khong dung IOUtils: hop cat cua
        // AutoConfig khong co doi tuong do (da do: "IOUtils is not defined").
        var size = f.fileSize;
        var stream = Cc["@mozilla.org/network/file-input-stream;1"]
          .createInstance(Ci.nsIFileInputStream);
        stream.init(f, 0x01, 0, 0);
        var bin = Cc["@mozilla.org/binaryinputstream;1"]
          .createInstance(Ci.nsIBinaryInputStream);
        bin.setInputStream(stream);
        // readArrayBuffer chu khong phai readByteArray: readByteArray tra ve mot
        // mang JS moi phan tu mot so, video vai chuc MB la treo may.
        var buf = new ArrayBuffer(size);
        bin.readArrayBuffer(size, buf);
        bin.close();
        stream.close();
        tra({ ok: true, name: f.leafName, bytes: new Uint8Array(buf) });
      } catch (e) {
        tra({ ok: false, error: String(e) });
      }
    });

    var agentFile = Services.dirsvc.get("GreD", Ci.nsIFile);
    agentFile.append("%(agent)s");
    if (agentFile.exists()) {
      Services.ppmm.loadProcessScript(Services.io.newFileURI(agentFile).spec, true);
    }
  } catch (e) {
    Services.console.logStringMessage("fbupload agent loi: " + e);
  }
})();
"""


# Bridge RIENG cho agent tao fanpage. Tach hoan toan khoi agent dang bai: ten
# message qlfpc:* va file qlfp-create* khac han, nen hai agent song chung khong
# dam nhau. Chi doc/ghi text (ten/hang muc/mo ta + ket qua) -- KHONG doc file
# nhi phan (avatar/anh bia lam sau, se dung kenh rieng neu can).
_CREATE_LOADER_JS = """
(function () {
  var CMD = "qlfp-create.json";
  var RESULT = "qlfp-create-result.json";

  function profileFile(name) {
    var f = Services.dirsvc.get("ProfD", Ci.nsIFile);
    f.append(name);
    return f;
  }
  function readText(name) {
    try {
      var f = profileFile(name);
      if (!f.exists()) { return ""; }
      var stream = Cc["@mozilla.org/network/file-input-stream;1"]
        .createInstance(Ci.nsIFileInputStream);
      stream.init(f, 0x01, 0, 0);
      var conv = Cc["@mozilla.org/intl/converter-input-stream;1"]
        .createInstance(Ci.nsIConverterInputStream);
      conv.init(stream, "UTF-8", 0, 0);
      var out = "", chunk = {};
      while (conv.readString(4096, chunk) !== 0) { out += chunk.value; }
      conv.close();
      return out;
    } catch (e) { return ""; }
  }
  function writeText(name, text) {
    try {
      var f = profileFile(name);
      var out = Cc["@mozilla.org/network/file-output-stream;1"]
        .createInstance(Ci.nsIFileOutputStream);
      out.init(f, 0x02 | 0x08 | 0x20, 420, 0);
      var conv = Cc["@mozilla.org/intl/converter-output-stream;1"]
        .createInstance(Ci.nsIConverterOutputStream);
      conv.init(out, "UTF-8");
      conv.writeString(text);
      conv.close();
    } catch (e) {}
  }

  try {
    Services.ppmm.addMessageListener("qlfpc:cmd", function () {
      return readText(CMD);
    });
    Services.ppmm.addMessageListener("qlfpc:report", function (msg) {
      var data = msg.data || {};
      data.at = Date.now();
      writeText(RESULT, JSON.stringify(data));
    });
    // CHE DO TRANG: cookie i_user do FB dat khi "dung Facebook voi tu cach Trang"
    // thuong la HttpOnly -> document.cookie trong trang KHONG thay/xoa duoc (da
    // thay: cookie FB tu dat nhu xs deu HttpOnly, cookie tool nap thi khong).
    // Tien trinh cha thay het qua Services.cookies: kiem tra + xoa theo yeu cau.
    Services.ppmm.addMessageListener("qlfpc:pagemode", function (msg) {
      var out = { inPage: false, removed: 0 };
      try {
        var clear = !!(msg.data && msg.data.clear);
        var all = Services.cookies.cookies;
        for (var i = 0; i < all.length; i++) {
          var c = all[i];
          if (c.name !== "i_user" || String(c.host).indexOf("facebook.com") === -1) { continue; }
          out.inPage = true;
          if (clear) {
            try {
              Services.cookies.remove(c.host, c.name, c.path, c.originAttributes);
              out.removed += 1;
            } catch (e) { out.error = String(e); }
          }
        }
      } catch (e) { out.error = String(e); }
      return out;
    });

    var agentFile = Services.dirsvc.get("GreD", Ci.nsIFile);
    agentFile.append("%(agent)s");
    if (agentFile.exists()) {
      Services.ppmm.loadProcessScript(Services.io.newFileURI(agentFile).spec, true);
    }
  } catch (e) {
    Services.console.logStringMessage("fbcreate agent loi: " + e);
  }
})();
"""


_LOGIN_LOADER_JS = """
(function () {
  var CMD = "qlfp-weblogin.json";
  var RESULT = "qlfp-weblogin-result.json";
  function profileFile(name) { var f = Services.dirsvc.get("ProfD", Ci.nsIFile); f.append(name); return f; }
  function readText(name) {
    try {
      var f = profileFile(name); if (!f.exists()) { return ""; }
      var stream = Cc["@mozilla.org/network/file-input-stream;1"].createInstance(Ci.nsIFileInputStream);
      stream.init(f, 0x01, 0, 0);
      var conv = Cc["@mozilla.org/intl/converter-input-stream;1"].createInstance(Ci.nsIConverterInputStream);
      conv.init(stream, "UTF-8", 0, 0);
      var out = "", chunk = {}; while (conv.readString(4096, chunk) !== 0) { out += chunk.value; }
      conv.close(); return out;
    } catch (e) { return ""; }
  }
  function writeText(name, text) {
    try {
      var f = profileFile(name);
      var out = Cc["@mozilla.org/network/file-output-stream;1"].createInstance(Ci.nsIFileOutputStream);
      out.init(f, 0x02 | 0x08 | 0x20, 420, 0);
      var conv = Cc["@mozilla.org/intl/converter-output-stream;1"].createInstance(Ci.nsIConverterOutputStream);
      conv.init(out, "UTF-8"); conv.writeString(text); conv.close();
    } catch (e) {}
  }
  try {
    Services.ppmm.addMessageListener("qlfpwl:cmd", function () { return readText(CMD); });
    Services.ppmm.addMessageListener("qlfpwl:report", function (msg) {
      var data = msg.data || {}; data.at = Date.now(); writeText(RESULT, JSON.stringify(data));
    });
    var agentFile = Services.dirsvc.get("GreD", Ci.nsIFile);
    agentFile.append("%(agent)s");
    if (agentFile.exists()) { Services.ppmm.loadProcessScript(Services.io.newFileURI(agentFile).spec, true); }
  } catch (e) { Services.console.logStringMessage("fblogin agent loi: " + e); }
})();
"""

# Bridge dang nhap X.com bang Google: message qlfpxl:* va file qlfp-xlogin* RIENG.
_XLOGIN_LOADER_JS = """
(function () {
  var CMD = "qlfp-xlogin.json";
  var RESULT = "qlfp-xlogin-result.json";
  function profileFile(name) { var f = Services.dirsvc.get("ProfD", Ci.nsIFile); f.append(name); return f; }
  function readText(name) {
    try {
      var f = profileFile(name); if (!f.exists()) { return ""; }
      var stream = Cc["@mozilla.org/network/file-input-stream;1"].createInstance(Ci.nsIFileInputStream);
      stream.init(f, 0x01, 0, 0);
      var conv = Cc["@mozilla.org/intl/converter-input-stream;1"].createInstance(Ci.nsIConverterInputStream);
      conv.init(stream, "UTF-8", 0, 0);
      var out = "", chunk = {}; while (conv.readString(4096, chunk) !== 0) { out += chunk.value; }
      conv.close(); return out;
    } catch (e) { return ""; }
  }
  function writeText(name, text) {
    try {
      var f = profileFile(name);
      var out = Cc["@mozilla.org/network/file-output-stream;1"].createInstance(Ci.nsIFileOutputStream);
      out.init(f, 0x02 | 0x08 | 0x20, 420, 0);
      var conv = Cc["@mozilla.org/intl/converter-output-stream;1"].createInstance(Ci.nsIConverterOutputStream);
      conv.init(out, "UTF-8"); conv.writeString(text); conv.close();
    } catch (e) {}
  }
  try {
    Services.ppmm.addMessageListener("qlfpxl:cmd", function () { return readText(CMD); });
    Services.ppmm.addMessageListener("qlfpxl:report", function (msg) {
      var data = msg.data || {}; data.at = Date.now(); writeText(RESULT, JSON.stringify(data));
    });
    var agentFile = Services.dirsvc.get("GreD", Ci.nsIFile);
    agentFile.append("%(agent)s");
    if (agentFile.exists()) { Services.ppmm.loadProcessScript(Services.io.newFileURI(agentFile).spec, true); }
  } catch (e) { Services.console.logStringMessage("xlogin agent loi: " + e); }
})();
"""

# Bridge DANG BAI len X.com: message qlfpxp:* va file qlfp-xpost* RIENG.
_XPOST_LOADER_JS = """
(function () {
  var CMD = "qlfp-xpost.json";
  var RESULT = "qlfp-xpost-result.json";
  function profileFile(name) { var f = Services.dirsvc.get("ProfD", Ci.nsIFile); f.append(name); return f; }
  function readText(name) {
    try {
      var f = profileFile(name); if (!f.exists()) { return ""; }
      var stream = Cc["@mozilla.org/network/file-input-stream;1"].createInstance(Ci.nsIFileInputStream);
      stream.init(f, 0x01, 0, 0);
      var conv = Cc["@mozilla.org/intl/converter-input-stream;1"].createInstance(Ci.nsIConverterInputStream);
      conv.init(stream, "UTF-8", 0, 0);
      var out = "", chunk = {}; while (conv.readString(4096, chunk) !== 0) { out += chunk.value; }
      conv.close(); return out;
    } catch (e) { return ""; }
  }
  function writeText(name, text) {
    try {
      var f = profileFile(name);
      var out = Cc["@mozilla.org/network/file-output-stream;1"].createInstance(Ci.nsIFileOutputStream);
      out.init(f, 0x02 | 0x08 | 0x20, 420, 0);
      var conv = Cc["@mozilla.org/intl/converter-output-stream;1"].createInstance(Ci.nsIConverterOutputStream);
      conv.init(out, "UTF-8"); conv.writeString(text); conv.close();
    } catch (e) {}
  }
  try {
    Services.ppmm.addMessageListener("qlfpxp:cmd", function () { return readText(CMD); });
    Services.ppmm.addMessageListener("qlfpxp:report", function (msg) {
      var data = msg.data || {}; data.at = Date.now(); writeText(RESULT, JSON.stringify(data));
    });
    // Doc file media ho tien trinh noi dung (bi chan doc dia) -- nhu qlfp:needfile.
    Services.ppmm.addMessageListener("qlfpxp:needfile", function (msg) {
      var path = (msg.data || {}).path || "";
      var tra = function (data) {
        try { Services.ppmm.broadcastAsyncMessage("qlfpxp:file", data); } catch (e) {}
      };
      try {
        var f = Cc["@mozilla.org/file/local;1"].createInstance(Ci.nsIFile);
        f.initWithPath(path);
        if (!f.exists()) { tra({ ok: false, error: "khong thay file: " + path }); return; }
        if (f.fileSize > 400 * 1024 * 1024) { tra({ ok: false, error: "file lon hon 400 MB" }); return; }
        var size = f.fileSize;
        var stream = Cc["@mozilla.org/network/file-input-stream;1"].createInstance(Ci.nsIFileInputStream);
        stream.init(f, 0x01, 0, 0);
        var bin = Cc["@mozilla.org/binaryinputstream;1"].createInstance(Ci.nsIBinaryInputStream);
        bin.setInputStream(stream);
        var buf = new ArrayBuffer(size);
        bin.readArrayBuffer(size, buf);
        bin.close(); stream.close();
        tra({ ok: true, name: f.leafName, bytes: new Uint8Array(buf) });
      } catch (e) { tra({ ok: false, error: String(e) }); }
    });
    var agentFile = Services.dirsvc.get("GreD", Ci.nsIFile);
    agentFile.append("%(agent)s");
    if (agentFile.exists()) { Services.ppmm.loadProcessScript(Services.io.newFileURI(agentFile).spec, true); }
  } catch (e) { Services.console.logStringMessage("xpost agent loi: " + e); }
})();
"""

# Bridge dang nhap NordVPN: message qlfpn:* va file qlfp-nord* RIENG.
_NORD_LOADER_JS = """
(function () {
  var CMD = "qlfp-nord.json";
  var RESULT = "qlfp-nord-result.json";
  function profileFile(name) { var f = Services.dirsvc.get("ProfD", Ci.nsIFile); f.append(name); return f; }
  function readText(name) {
    try {
      var f = profileFile(name); if (!f.exists()) { return ""; }
      var stream = Cc["@mozilla.org/network/file-input-stream;1"].createInstance(Ci.nsIFileInputStream);
      stream.init(f, 0x01, 0, 0);
      var conv = Cc["@mozilla.org/intl/converter-input-stream;1"].createInstance(Ci.nsIConverterInputStream);
      conv.init(stream, "UTF-8", 0, 0);
      var out = "", chunk = {}; while (conv.readString(4096, chunk) !== 0) { out += chunk.value; }
      conv.close(); return out;
    } catch (e) { return ""; }
  }
  function writeText(name, text) {
    try {
      var f = profileFile(name);
      var out = Cc["@mozilla.org/network/file-output-stream;1"].createInstance(Ci.nsIFileOutputStream);
      out.init(f, 0x02 | 0x08 | 0x20, 420, 0);
      var conv = Cc["@mozilla.org/intl/converter-output-stream;1"].createInstance(Ci.nsIConverterOutputStream);
      conv.init(out, "UTF-8"); conv.writeString(text); conv.close();
    } catch (e) {}
  }
  try {
    Services.ppmm.addMessageListener("qlfpn:cmd", function () { return readText(CMD); });
    Services.ppmm.addMessageListener("qlfpn:report", function (msg) {
      var data = msg.data || {}; data.at = Date.now(); writeText(RESULT, JSON.stringify(data));
    });
    var agentFile = Services.dirsvc.get("GreD", Ci.nsIFile);
    agentFile.append("%(agent)s");
    if (agentFile.exists()) { Services.ppmm.loadProcessScript(Services.io.newFileURI(agentFile).spec, true); }
  } catch (e) { Services.console.logStringMessage("nordlogin agent loi: " + e); }
})();
"""

# Bridge nhan tin RIENG: message qlfpm:* va file qlfp-msg* KHAC han 3 agent kia,
# nen bon agent song chung khong dam nhau.
_CHAT_LOADER_JS = """
(function () {
  var CMD = "qlfp-msg.json";
  var RESULT = "qlfp-msg-result.json";
  function profileFile(name) { var f = Services.dirsvc.get("ProfD", Ci.nsIFile); f.append(name); return f; }
  function readText(name) {
    try {
      var f = profileFile(name); if (!f.exists()) { return ""; }
      var stream = Cc["@mozilla.org/network/file-input-stream;1"].createInstance(Ci.nsIFileInputStream);
      stream.init(f, 0x01, 0, 0);
      var conv = Cc["@mozilla.org/intl/converter-input-stream;1"].createInstance(Ci.nsIConverterInputStream);
      conv.init(stream, "UTF-8", 0, 0);
      var out = "", chunk = {}; while (conv.readString(4096, chunk) !== 0) { out += chunk.value; }
      conv.close(); return out;
    } catch (e) { return ""; }
  }
  function writeText(name, text) {
    try {
      var f = profileFile(name);
      var out = Cc["@mozilla.org/network/file-output-stream;1"].createInstance(Ci.nsIFileOutputStream);
      out.init(f, 0x02 | 0x08 | 0x20, 420, 0);
      var conv = Cc["@mozilla.org/intl/converter-output-stream;1"].createInstance(Ci.nsIConverterOutputStream);
      conv.init(out, "UTF-8"); conv.writeString(text); conv.close();
    } catch (e) {}
  }
  try {
    Services.ppmm.addMessageListener("qlfpm:cmd", function () { return readText(CMD); });
    Services.ppmm.addMessageListener("qlfpm:report", function (msg) {
      var data = msg.data || {}; data.at = Date.now(); writeText(RESULT, JSON.stringify(data));
    });
    var agentFile = Services.dirsvc.get("GreD", Ci.nsIFile);
    agentFile.append("%(agent)s");
    if (agentFile.exists()) { Services.ppmm.loadProcessScript(Services.io.newFileURI(agentFile).spec, true); }
  } catch (e) { Services.console.logStringMessage("fbchat agent loi: " + e); }
})();
"""

# Bridge TUONG TAC RIENG: message qlfpw:* va file qlfp-watch* KHAC han cac agent kia.
_WATCH_LOADER_JS = """
(function () {
  var CMD = "qlfp-watch.json";
  var RESULT = "qlfp-watch-result.json";
  function profileFile(name) { var f = Services.dirsvc.get("ProfD", Ci.nsIFile); f.append(name); return f; }
  function readText(name) {
    try {
      var f = profileFile(name); if (!f.exists()) { return ""; }
      var stream = Cc["@mozilla.org/network/file-input-stream;1"].createInstance(Ci.nsIFileInputStream);
      stream.init(f, 0x01, 0, 0);
      var conv = Cc["@mozilla.org/intl/converter-input-stream;1"].createInstance(Ci.nsIConverterInputStream);
      conv.init(stream, "UTF-8", 0, 0);
      var out = "", chunk = {}; while (conv.readString(4096, chunk) !== 0) { out += chunk.value; }
      conv.close(); return out;
    } catch (e) { return ""; }
  }
  function writeText(name, text) {
    try {
      var f = profileFile(name);
      var out = Cc["@mozilla.org/network/file-output-stream;1"].createInstance(Ci.nsIFileOutputStream);
      out.init(f, 0x02 | 0x08 | 0x20, 420, 0);
      var conv = Cc["@mozilla.org/intl/converter-output-stream;1"].createInstance(Ci.nsIConverterOutputStream);
      conv.init(out, "UTF-8"); conv.writeString(text); conv.close();
    } catch (e) {}
  }
  try {
    Services.ppmm.addMessageListener("qlfpw:cmd", function () { return readText(CMD); });
    Services.ppmm.addMessageListener("qlfpw:report", function (msg) {
      var data = msg.data || {}; data.at = Date.now(); writeText(RESULT, JSON.stringify(data));
    });
    var agentFile = Services.dirsvc.get("GreD", Ci.nsIFile);
    agentFile.append("%(agent)s");
    if (agentFile.exists()) { Services.ppmm.loadProcessScript(Services.io.newFileURI(agentFile).spec, true); }
  } catch (e) { Services.console.logStringMessage("fbwatch agent loi: " + e); }
})();
"""

# Bridge add-BM RIENG: message qlfpbm:* va file qlfp-bm* KHAC han 4 agent kia.
_BM_LOADER_JS = """
(function () {
  var CMD = "qlfp-bm.json";
  var RESULT = "qlfp-bm-result.json";
  function profileFile(name) { var f = Services.dirsvc.get("ProfD", Ci.nsIFile); f.append(name); return f; }
  function readText(name) {
    try {
      var f = profileFile(name); if (!f.exists()) { return ""; }
      var stream = Cc["@mozilla.org/network/file-input-stream;1"].createInstance(Ci.nsIFileInputStream);
      stream.init(f, 0x01, 0, 0);
      var conv = Cc["@mozilla.org/intl/converter-input-stream;1"].createInstance(Ci.nsIConverterInputStream);
      conv.init(stream, "UTF-8", 0, 0);
      var out = "", chunk = {}; while (conv.readString(4096, chunk) !== 0) { out += chunk.value; }
      conv.close(); return out;
    } catch (e) { return ""; }
  }
  function writeText(name, text) {
    try {
      var f = profileFile(name);
      var out = Cc["@mozilla.org/network/file-output-stream;1"].createInstance(Ci.nsIFileOutputStream);
      out.init(f, 0x02 | 0x08 | 0x20, 420, 0);
      var conv = Cc["@mozilla.org/intl/converter-output-stream;1"].createInstance(Ci.nsIConverterOutputStream);
      conv.init(out, "UTF-8"); conv.writeString(text); conv.close();
    } catch (e) {}
  }
  try {
    Services.ppmm.addMessageListener("qlfpbm:cmd", function () { return readText(CMD); });
    Services.ppmm.addMessageListener("qlfpbm:report", function (msg) {
      var data = msg.data || {}; data.at = Date.now(); writeText(RESULT, JSON.stringify(data));
    });
    var agentFile = Services.dirsvc.get("GreD", Ci.nsIFile);
    agentFile.append("%(agent)s");
    if (agentFile.exists()) { Services.ppmm.loadProcessScript(Services.io.newFileURI(agentFile).spec, true); }
  } catch (e) { Services.console.logStringMessage("fbbm agent loi: " + e); }
})();
"""


# Agent thu 6: KHONG co lenh, chi nhan bao cao "skipped"/"cung" ghi vao qlfp-skip.log.
_SKIP_LOADER_JS = """
(function () {
  var LOGF = "%(log)s";
  function profileFile(name) { var f = Services.dirsvc.get("ProfD", Ci.nsIFile); f.append(name); return f; }
  function appendText(name, text) {
    try {
      var f = profileFile(name);
      var out = Cc["@mozilla.org/network/file-output-stream;1"].createInstance(Ci.nsIFileOutputStream);
      out.init(f, 0x02 | 0x08 | 0x10, 420, 0);
      var conv = Cc["@mozilla.org/intl/converter-output-stream;1"].createInstance(Ci.nsIConverterOutputStream);
      conv.init(out, "UTF-8"); conv.writeString(text); conv.close();
    } catch (e) {}
  }
  try {
    Services.ppmm.addMessageListener("qlfpsk:report", function (msg) {
      var d = msg.data || {};
      appendText(LOGF, new Date().toISOString() + " " + (d.state || "") + " " + (d.detail || "") + "\\r\\n");
    });
    var agentFile = Services.dirsvc.get("GreD", Ci.nsIFile);
    agentFile.append("%(agent)s");
    if (agentFile.exists()) { Services.ppmm.loadProcessScript(Services.io.newFileURI(agentFile).spec, true); }
  } catch (e) { Services.console.logStringMessage("fbskip agent loi: " + e); }
})();
"""


def render(
    proxy: Proxy,
    realm: str = DEFAULT_REALM,
    label: str = "",
    identity: Optional[Identity] = None,
    use_shim: bool = False,
    user_agent: str = "",
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
    if user_agent:
        # UA gia lap thiet bi (iOS/Android/TV/Mac/Win...): khoa cung de trang khong doi lai.
        parts += [
            "",
            "// User Agent gia lap thiet bi (chon luc import / chuot phai Doi user agent)",
            f'lockPref("general.useragent.override", {json.dumps(user_agent)});',
        ]
    if identity.timezone and use_shim:
        parts.append(_SHIM_LOADER_JS % {"shim": SHIM_NAME})

    parts.append(_STARTUP_PREFS)
    parts.append(autostart.lock_pref_lines())
    parts.append(_EXTENSION_PREFS)
    parts.append(_TITLE_JS)
    parts.append(_PROBE_JS)
    parts.append(_AGENT_LOADER_JS % {"agent": AGENT_NAME})
    parts.append(_CREATE_LOADER_JS % {"agent": CREATE_AGENT_NAME})
    parts.append(_LOGIN_LOADER_JS % {"agent": LOGIN_AGENT_NAME})
    parts.append(_CHAT_LOADER_JS % {"agent": CHAT_AGENT_NAME})
    parts.append(_WATCH_LOADER_JS % {"agent": WATCH_AGENT_NAME})
    parts.append(_BM_LOADER_JS % {"agent": BM_AGENT_NAME})
    parts.append(_SKIP_LOADER_JS % {"agent": SKIP_AGENT_NAME, "log": SKIP_LOG})
    parts.append(_XLOGIN_LOADER_JS % {"agent": XLOGIN_AGENT_NAME})
    parts.append(_NORD_LOADER_JS % {"agent": NORD_AGENT_NAME})
    parts.append(_XPOST_LOADER_JS % {"agent": XPOST_AGENT_NAME})
    return "\n".join(parts)


def install(
    app_dir: str,
    proxy: Proxy,
    realm: Optional[str] = None,
    label: str = "",
    identity: Optional[Identity] = None,
    use_shim: bool = False,
    user_agent: str = "",
) -> list[str]:
    """Cai AutoConfig vao thu muc app: proxy + ten cua so + UA gia lap.

    Khong co proxy lan ten thi go han ra. Tra ve danh sach thu muc da ghi.
    """
    identity = identity or Identity()
    if not proxy.enabled and not label and not identity.enabled and not user_agent:
        uninstall(app_dir)
        return []

    targets = firefox_dirs(app_dir)
    if not targets:
        return []

    if realm is None:
        realm = detect_realm(proxy) if proxy.needs_auth else DEFAULT_REALM
    content = render(proxy, realm, label, identity, use_shim, user_agent)

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
        # Agent dang video: chep san canh firefox.exe. No nam im cho toi khi tool
        # de mot file lenh trong thu muc profile.
        _write(os.path.join(folder, AGENT_NAME), _asset(AGENT_NAME), bom=True)
        # Agent tao fanpage: bridge rieng, nam im toi khi co qlfp-create.json.
        _write(os.path.join(folder, CREATE_AGENT_NAME),
               _asset(CREATE_AGENT_NAME), bom=True)
        # Agent dang nhap web: bridge rieng, nam im toi khi co qlfp-weblogin.json.
        _write(os.path.join(folder, LOGIN_AGENT_NAME),
               _asset(LOGIN_AGENT_NAME), bom=True)
        _write(os.path.join(folder, CHAT_AGENT_NAME),
               _asset(CHAT_AGENT_NAME), bom=True)
        _write(os.path.join(folder, WATCH_AGENT_NAME),
               _asset(WATCH_AGENT_NAME), bom=True)
        _write(os.path.join(folder, BM_AGENT_NAME),
               _asset(BM_AGENT_NAME), bom=True)
        # Agent bo qua checkpoint mem: luon chay tren moi trang /checkpoint.
        _write(os.path.join(folder, SKIP_AGENT_NAME),
               _asset(SKIP_AGENT_NAME), bom=True)
        # Agent dang nhap X.com bang Google: nam im toi khi co qlfp-xlogin.json.
        _write(os.path.join(folder, XLOGIN_AGENT_NAME),
               _asset(XLOGIN_AGENT_NAME), bom=True)
        # Agent dang bai X.com: nam im toi khi co qlfp-xpost.json.
        _write(os.path.join(folder, XPOST_AGENT_NAME),
               _asset(XPOST_AGENT_NAME), bom=True)
        # Agent dang nhap NordVPN: nam im toi khi co qlfp-nord.json.
        _write(os.path.join(folder, NORD_AGENT_NAME),
               _asset(NORD_AGENT_NAME), bom=True)

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


def _write(path: str, content: str, bom: bool = False) -> None:
    """Ghi file cho Firefox doc. ``bom=True`` khi file co chu tieng Viet.

    mozilla.cfg thi Firefox doc dung UTF-8. Nhung PROCESS SCRIPT
    (fbupload_agent.js) lai duoc nap theo Latin-1 neu file khong co dau hieu bang
    ma -- chu tieng Viet trong do hong ngay tu luc nap, nhat ky hien ra
    "há»™p soáº¡n bÃ i" thay vi "hộp soạn bài" (da gap that). Them BOM la nap dung.
    """
    with open(path, "w", encoding=("utf-8-sig" if bom else "utf-8"),
              newline="\n") as fh:
        fh.write(content)
