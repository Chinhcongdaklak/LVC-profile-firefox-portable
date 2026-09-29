/* Process script: DANG NHAP NordVPN qua trang my.nordaccount.com.
 *
 * Cung khuon fblogin_agent.js / xlogin_agent.js: dien email + pass bang su kien
 * "nguoi that" (setHandlingUserInput), trinh duyet mo BINH THUONG.
 *
 * Bridge RIENG:
 *   sendSyncMessage("qlfpn:cmd")     -> cha doc <profile>/qlfp-nord.json
 *   sendAsyncMessage("qlfpn:report") -> cha ghi <profile>/qlfp-nord-result.json
 *
 * Lenh: { action:"nordlogin", email, pass, delay, timeout }
 * Nord Account: nhap email -> Tiep tuc -> nhap mat khau -> Dang nhap. Sau khi vao,
 * URL roi khoi /login (ve dashboard) -> "nord-logged-in".
 */
"use strict";

/* ---- phan THUAN (test node): phan loai man theo url + chu ------------------------- */
function nordPhanLoai(url, text) {
  url = (url || "").toLowerCase();
  text = text || "";
  if (!/nordaccount\.com|nordvpn\.com/.test(url)) { return ""; }
  if (/incorrect|invalid|sai|không đúng|khong dung|wrong password|couldn.?t log/i.test(text)) { return "nord-wrong"; }
  if (/\/login|\/signup|\/auth/.test(url)) { return "nord-login"; }
  return "nord-in";      // roi trang login -> coi nhu da vao
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { phanLoai: nordPhanLoai };
}

if (typeof sendAsyncMessage === "function") {

  var lines = [];
  function report(state, detail) {
    lines.push(state + (detail ? ": " + detail : ""));
    try { sendAsyncMessage("qlfpn:report", { state: state, detail: detail || "", log: lines.slice(-30) }); }
    catch (e) {}
  }
  function getCommand() {
    try { var a = sendSyncMessage("qlfpn:cmd"); var raw = a && a.length ? a[0] : ""; return raw ? JSON.parse(raw) : null; }
    catch (e) { return null; }
  }
  function low(s) { return (s || "").toLowerCase(); }
  function vis(el) {
    try { var b = el.getBoundingClientRect(); return b.width > 12 && b.height > 8 && el.offsetParent !== null; }
    catch (e) { return false; }
  }
  function setNative(win, el, val) {
    try {
      var setter = Object.getOwnPropertyDescriptor(win.HTMLInputElement.prototype, "value").set;
      el.focus(); setter.call(el, val);
      el.dispatchEvent(new win.Event("input", { bubbles: true }));
      el.dispatchEvent(new win.Event("change", { bubbles: true }));
      return true;
    } catch (e) { report("set-error", String(e)); return false; }
  }
  function clickReal(win, el) {
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try {
      var b = el.getBoundingClientRect(), cx = b.left + b.width / 2, cy = b.top + b.height / 2;
      function pe(t) { return new win.PointerEvent(t, { bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0, pointerType: "mouse", isPrimary: true }); }
      function me(t) { return new win.MouseEvent(t, { bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0 }); }
      el.dispatchEvent(pe("pointerover")); el.dispatchEvent(me("mouseover"));
      el.dispatchEvent(pe("pointerdown")); el.dispatchEvent(me("mousedown"));
      try { el.focus(); } catch (e) {}
      el.dispatchEvent(pe("pointerup")); el.dispatchEvent(me("mouseup"));
      el.dispatchEvent(me("click"));
      return true;
    } catch (e) { report("click-error", String(e)); return false; }
    finally { if (handle) { try { handle.destruct(); } catch (e) {} } }
  }
  function q(doc, sel) { try { return doc.querySelector(sel); } catch (e) { return null; } }
  function txt(doc) { try { return doc.body ? doc.body.innerText : ""; } catch (e) { return ""; } }
  function nutTheoChu(doc, re) {
    var cands = Array.prototype.slice.call(doc.querySelectorAll('[role="button"],button,input[type=submit]'));
    return cands.filter(function (b) {
      if (!vis(b)) { return false; }
      var s = (b.getAttribute("aria-label") || b.textContent || b.value || "").replace(/\s+/g, " ").trim();
      return re.test(s);
    });
  }
  function nutTiep(doc) {
    var ds = nutTheoChu(doc, /^(continue|tiếp tục|tiep tuc|next|log in|đăng nhập|dang nhap|submit)$/i);
    return ds.length ? ds[ds.length - 1] : q(doc, 'button[type=submit]');
  }

  var emailXong = false, passXong = false;
  function xuLy(win, doc, cmd) {
    var t = low(txt(doc));
    if (/incorrect|invalid password|wrong password|sai mật khẩu|không đúng/.test(t)) { report("nord-wrong", ""); return; }
    var oEmail = q(doc, 'input[type=email],input[name=email],input[autocomplete=username]');
    if (oEmail && vis(oEmail) && !oEmail.value && cmd.email) {
      setNative(win, oEmail, cmd.email); emailXong = true; report("nord-email-filled", "");
      var n1 = nutTiep(doc); if (n1) { clickReal(win, n1); }
      return;
    }
    var oPass = q(doc, 'input[type=password]');
    if (oPass && vis(oPass)) {
      if (!oPass.value && cmd.pass) {
        setNative(win, oPass, cmd.pass); passXong = true; report("nord-pass-filled", "");
        var n2 = nutTiep(doc); if (n2) { clickReal(win, n2); }
      }
      return;
    }
  }

  function dumpNhe(doc) {
    try {
      var xs = doc.querySelectorAll("input"), out = [];
      for (var i = 0; i < xs.length && i < 6; i++) {
        out.push("in[type=" + (xs[i].type || "") + ",name=" + (xs[i].name || "") + ",vis=" + (vis(xs[i]) ? 1 : 0) + "]");
      }
      return out.join(" ");
    } catch (e) { return ""; }
  }

  // ---- popup addon NordVPN (moz-extension): chon quoc gia + bang ----------------------
  var quocGiaXong = false;
  function laPopupNord(win) {
    try { return /^moz-extension:/.test(win.location.href) && /countries|country|connect to vpn|servers/i.test(txt(win.document)); }
    catch (e) { return false; }
  }
  function oTim(doc) {
    var xs = Array.prototype.slice.call(doc.querySelectorAll('input[type=text],input[type=search],input[placeholder]'))
      .filter(function (e) { return vis(e) && /countr|city|server|search|tìm|quốc gia/i.test((e.placeholder || "") + (e.getAttribute("aria-label") || "")); });
    return xs[0] || null;
  }
  function chonQuocGia(win, doc, cmd) {
    if (quocGiaXong || !cmd.country) { return; }
    var o = oTim(doc);
    if (o) {
      if (o.value !== cmd.country) { setNative(win, o, cmd.country); report("nord-country-typed", cmd.country); return; }
      // Chon dong ket qua khop ten quoc gia (hoac bang neu co).
      var muon = (cmd.state || cmd.country).toLowerCase();
      var rows = Array.prototype.slice.call(doc.querySelectorAll('[role=option],[role=button],li,button,div'))
        .filter(function (e) { return vis(e) && low(e.textContent).indexOf(muon) >= 0 && low(e.textContent).length < 60; });
      if (rows.length) { clickReal(win, rows[0]); quocGiaXong = true; report("nord-country-picked", cmd.state || cmd.country); }
    }
  }

  // ---- THAM DO popup (index.html mo trong tab): chup phan tu bam duoc + trang thai -----
  function moTa(el) {
    var t = (el.getAttribute("aria-label") || el.innerText || el.value || el.placeholder || "")
      .replace(/\s+/g, " ").trim().slice(0, 70);
    var bat = el.getAttribute("aria-checked") || el.getAttribute("aria-pressed") ||
      el.getAttribute("aria-expanded") || (el.type === "checkbox" ? String(el.checked) : "");
    return el.tagName.toLowerCase() + (el.getAttribute("role") ? "[" + el.getAttribute("role") + "]" : "") +
      (el.type ? "{" + el.type + "}" : "") + (bat ? "<" + bat + ">" : "") +
      (el.getAttribute("data-testid") ? "#" + el.getAttribute("data-testid") : "") + " " + t;
  }
  function dumpPopup(doc) {
    var xs = Array.prototype.slice.call(doc.querySelectorAll(
      'button,[role=button],[role=switch],[role=checkbox],[role=option],[role=tab],[role=menuitem],input,a,li,label'));
    var out = [];
    for (var i = 0; i < xs.length && out.length < 90; i++) {
      if (vis(xs[i]) || xs[i].type === "checkbox") { out.push(moTa(xs[i])); }
    }
    return out.join(" || ");
  }
  function bamTheoChu(win, doc, chu) {
    var re = new RegExp("^\\s*" + chu.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
    var xs = Array.prototype.slice.call(doc.querySelectorAll(
      'button,[role=button],[role=switch],[role=option],[role=tab],[role=menuitem],a,li,label,div,span'))
      .filter(function (e) { return vis(e) && re.test((e.innerText || e.getAttribute("aria-label") || "").trim()); });
    // Phan tu NHO NHAT khop (la la nut that, khong phai khung bao ngoai).
    xs.sort(function (a, b) { return (a.innerText || "").length - (b.innerText || "").length; });
    if (!xs.length) { return false; }
    clickReal(win, xs[0]);
    return true;
  }
  function thamDo(win, cmd) {
    var doc = win.document, buoc = (cmd.steps || []).slice(), lan = 0;
    win.setTimeout(function tick() {
      lan++;
      try {
        report("dump", "[" + lan + "] " + win.location.href.slice(-40) + " | " +
          (txt(doc) || "").replace(/\s+/g, " ").slice(0, 400) + " ## " + dumpPopup(doc));
        if (buoc.length && lan % 2 === 0) {
          var b = buoc.shift();
          if (b.indexOf("sw:") === 0) {
            var sw = switchTheoChu(doc, new RegExp(b.slice(3), "i"));
            if (sw) { clickReal(win, sw); }
            report("probe-click", b + " -> " + !!sw);
          } else if (b.indexOf("id:") === 0) {
            var el = q(doc, '[data-testid="' + b.slice(3) + '"]');
            if (el) { clickReal(win, el); }
            report("probe-click", b + " -> " + !!el);
          } else if (b.indexOf("type:") === 0) {
            var o = oTim(doc) || q(doc, "input");
            if (o) { setNative(win, o, b.slice(5)); report("probe-typed", b.slice(5)); }
          } else {
            report("probe-click", b + " -> " + bamTheoChu(win, doc, b));
          }
        }
      } catch (e) { report("tick-error", String(e)); }
      if (lan < (cmd.lan || 20)) { win.setTimeout(tick, 2500); }
      else { report("probe-done", ""); }
    }, 2500);
  }

  // ---- CAI DAT sau dang nhap: Spoofing BAT + Kill switch BAT + chon vi tri -----------------
  // Do theo data-testid/role (khong theo chu), da do that tren addon 5.6.5 (2026-09-28):
  //   nav: navigation-item-container-{vpn,spoofing,settings}; spoof: button[role=switch]#settings-spoofing
  //   Settings > "Connection and security" > 4 switch (Auto-connect, Kill switch, WebRTC, Warnings)
  //   VPN: input#location-card-search-input, dong vi tri div[role=button] aria-label "New York (United States)"
  function tid(doc, id) { return q(doc, '[data-testid="' + id + '"]'); }
  function batTat(el) { return el ? el.getAttribute("aria-checked") === "true" : null; }
  function switchTheoChu(doc, re) {
    // Switch nam trong the co TIEU DE khop re (khung gan nhat chua ca chu lan switch).
    var sw = Array.prototype.slice.call(doc.querySelectorAll('[role=switch]'));
    for (var i = 0; i < sw.length; i++) {
      var p = sw[i];
      for (var k = 0; k < 5 && p; k++) {
        p = p.parentElement;
        if (p && p.querySelectorAll('[role=switch]').length === 1 && re.test(p.innerText || "")) { return sw[i]; }
      }
    }
    return null;
  }
  function daDangNhapPopup(doc) { return !!tid(doc, "navigation-item-container-vpn"); }
  function trangThaiVpn(doc) {
    var t = txt(doc);
    var ip = (t.match(/IP:\s*([0-9a-f.:]+)/i) || [])[1] || "";
    var ok = /Status:\s*(Connected|Protected)/i.test(t) || (/\bSecured\b/.test(t) && !/Not secured/i.test(t));
    return { ok: ok, ip: ip };
  }
  function daNoiDung(doc, ten) {
    // "Status: Connected - New York, United States" -> da noi dung vi tri, khong bam lai.
    var m = (txt(doc) || "").match(/Status:\s*Connected\s*-\s*([^\n]+)/i);
    return !!m && m[1].toLowerCase().indexOf(ten.toLowerCase()) >= 0;
  }
  function laDongViTri(el, ten, nuoc) {
    var s = (el.getAttribute("aria-label") || el.innerText || "").replace(/\s+/g, " ").trim();
    var tenR = ten.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (nuoc) {
      var nR = nuoc.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return new RegExp("^" + tenR + "( - Virtual)?( \\(" + nR + "\\))?$", "i").test(s);
    }
    return new RegExp("^" + tenR + "$", "i").test(s);
  }
  function caiDat(win, cmd) {
    // THU TU (nguoi dung chot 2026-09-28): KET NOI vi tri TRUOC, VPN noi xong moi bat
    // Spoofing + Kill switch. Noi khong duoc -> KHONG bat hai cong tac.
    var doc = win.document, lan = 0, buoc = cmd.country ? "vitri" : "spoof", thu = 0, luc = 0;
    var kq = { spoof: null, kill: null, vi_tri: "", ip: "", ket_noi: false };
    var lanLogin = 0, soLanLogin = 0;
    function sang(b) { buoc = b; thu = 0; }
    win.setTimeout(function tick() {
      lan++; thu++;
      try {
        var dongQc = tid(doc, "close-button");
        if (dongQc && vis(dongQc)) { clickReal(win, dongQc); report("seen", "đóng hộp quảng cáo"); }
        if (!daDangNhapPopup(doc)) {
          // ADDON CHUA DANG NHAP: bam "Log in" trong popup (addon mo tab Nord Account;
          // da co phien web thi tu vao ~5s, chua co thi tab do tu dien email/pass).
          // Da do that 28/09: dang nhap my.nordaccount.com KHONG tu dang nhap addon.
          var nutLogin = tid(doc, "login-login-button");
          if (nutLogin && (lanLogin === 0 || lan - lanLogin >= 15)) {
            clickReal(win, nutLogin); lanLogin = lan; soLanLogin++;
            report("nord-addon-login-click", "lần " + soLanLogin);
          }
          if (lan > 45 || soLanLogin > 3) {
            report("nord-need-login", (txt(doc) || "").replace(/\s+/g, " ").slice(0, 120)); return;
          }
        } else if (buoc === "spoof") {
          var sp = tid(doc, "settings-spoofing");
          if (!sp) { clickReal(win, tid(doc, "navigation-item-container-spoofing")); }
          else if (batTat(sp)) { kq.spoof = true; report("nord-spoof-on", ""); sang("kill"); }
          else if (thu % 2 === 1) { clickReal(win, sp); report("seen", "bấm bật Spoofing"); }
          if (thu > 12) { report("nord-spoof-fail", ""); sang("kill"); }
        } else if (buoc === "kill") {
          var ks = switchTheoChu(doc, /kill switch/i);
          if (!ks) {
            if (!bamTheoChu(win, doc, "Connection and security")) {
              clickReal(win, tid(doc, "navigation-item-container-settings"));
            }
          } else if (batTat(ks)) { kq.kill = true; report("nord-kill-on", ""); sang("xong"); }
          else if (thu % 2 === 1) { clickReal(win, ks); report("seen", "bấm bật Kill switch"); }
          if (thu > 14) { report("nord-kill-fail", ""); sang("xong"); }
        } else if (buoc === "vitri") {
          if (!cmd.country) { sang("spoof"); }
          else if (daNoiDung(doc, cmd.city || cmd.country)) {
            kq.ket_noi = true; kq.vi_tri = cmd.city || cmd.country; kq.ip = trangThaiVpn(doc).ip;
            report("nord-connected", "đã nối sẵn " + kq.vi_tri); sang("spoof");
          }
          else {
            var o = tid(doc, "location-card-search-input");
            var tim = cmd.city || cmd.country;
            if (!o) { clickReal(win, tid(doc, "navigation-item-container-vpn")); }
            else if (o.value !== tim) { setNative(win, o, tim); }
            else {
              var dong = Array.prototype.slice.call(doc.querySelectorAll('[role=button]'))
                .filter(function (e) { return vis(e) && laDongViTri(e, tim, cmd.city ? cmd.country : ""); })[0];
              if (dong) {
                kq.vi_tri = (dong.getAttribute("aria-label") || tim);
                clickReal(win, dong); report("nord-location-picked", kq.vi_tri); luc = lan; sang("ketnoi");
              } else if (thu > 10) {
                report("nord-location-miss", tim + " | " + dumpPopup(doc).slice(0, 600)); sang("xong");
              }
            }
          }
        } else if (buoc === "ketnoi") {
          var tt = trangThaiVpn(doc);
          if (tt.ok) { kq.ip = tt.ip; kq.ket_noi = true; report("nord-connected", tt.ip); sang("spoof"); }
          else if (thu > 20) { report("nord-connect-timeout", (txt(doc) || "").replace(/\s+/g, " ").slice(0, 160)); sang("xong"); }
        }
        if (buoc === "xong") {
          report("nord-setup-done", JSON.stringify(kq));
          return;
        }
      } catch (e) { report("tick-error", String(e)); }
      if (lan < 120) { win.setTimeout(tick, cmd.delay || 1500); }
      else { report("nord-setup-done", JSON.stringify(kq)); }
    }, 2000);
  }

  function onPage(win) {
    var cmd = getCommand();
    if (cmd && cmd.action === "nordcho" && /ipinfo\.io/.test(win.location.href)) {
      // CONG VPN truoc khi vao X: hoi IP RA NGOAI toi khi KHAC IP that cua may (addon da
      // noi lai) roi moi chuyen sang trang dich. Het gio -> dung yen, bao vpn-fail.
      var batDau = Date.now(), cap = cmd.timeout || 60000, lanCho = 0;
      (function hoi() {
        lanCho++;
        win.fetch("https://ipinfo.io/json", { cache: "no-store" }).then(function (r) { return r.json(); })
          .then(function (j) {
            var ip = (j && j.ip) || "";
            if (ip && cmd.ip_may && ip !== cmd.ip_may) {
              report("vpn-ok", JSON.stringify({ ip: ip, city: j.city || "", region: j.region || "",
                country: j.country || "", lan: lanCho }));
              win.setTimeout(function () { win.location.href = cmd.next; }, 300);
              return;
            }
            report("seen", "vpn chua noi (lan " + lanCho + ", IP " + ip + ")");
            tiep();
          })
          .catch(function (e) { report("seen", "vpn hoi loi (lan " + lanCho + "): " + e); tiep(); });
        function tiep() {
          if (Date.now() - batDau < cap) { win.setTimeout(hoi, 2500); }
          else { report("vpn-fail", "sau " + Math.round(cap / 1000) + "s van la IP that " + (cmd.ip_may || "")); }
        }
      })();
      return;
    }
    if (cmd && cmd.action === "nordprobe" && /ipify|ipinfo/.test(win.location.href)) {
      // Kiem IP RA NGOAI that (trang web di qua VPN chua).
      var lanIp = 0;
      (function hoi() {
        lanIp++;
        win.fetch("https://ipinfo.io/json", { cache: "no-store" }).then(function (r) { return r.text(); })
          .then(function (t) { report("probe-ip", "[" + lanIp + "] " + t.replace(/\s+/g, " ").slice(0, 200)); })
          .catch(function (e) { report("probe-ip", "[" + lanIp + "] loi " + e); });
        if (lanIp < 8) { win.setTimeout(hoi, 4000); } else { win.setTimeout(function () { report("probe-done", ""); }, 3000); }
      })();
      return;
    }
    if (cmd && cmd.action === "nordsetup" && /nordaccount\.com|nordvpn\.com/.test(win.location.href)) {
      // Tab dang nhap addon (OAuth Nord Account) mo tu nut "Log in" cua popup: neu chua co
      // phien web thi dien email + pass o day (dung chung xuLy cua luong dang nhap web).
      var lanN = 0;
      win.setTimeout(function tickN() {
        lanN++;
        try {
          var man = nordPhanLoai(win.location.href, txt(win.document));
          report("seen", "addon-login " + man + " | " + win.location.href.slice(0, 80));
          if (man === "nord-login") { xuLy(win, win.document, getCommand() || cmd); }
          else if (man === "nord-wrong") { report("nord-wrong", ""); return; }
        } catch (e) { report("tick-error", String(e)); }
        if (lanN < 60) { win.setTimeout(tickN, 1500); }
      }, 1200);
      return;
    }
    if (cmd && cmd.action === "nordprobe" && /nordaccount\.com|nordvpn\.com/.test(win.location.href)) {
      // Tham do cac tab popup mo ra (dang nhap addon qua Nord Account).
      var lanP = 0;
      (function chup() {
        lanP++;
        report("probe-page", "[" + lanP + "] " + win.location.href.slice(0, 120) + " | " +
          (txt(win.document) || "").replace(/\s+/g, " ").slice(0, 300) + " ## " + dumpPopup(win.document).slice(0, 900));
        if (lanP < 8) { win.setTimeout(chup, 3000); }
      })();
      return;
    }
    if (cmd && /^moz-extension:.*index\.html/.test(win.location.href)) {
      if (cmd.action === "nordprobe") { thamDo(win, cmd); return; }
      if (cmd.action === "nordsetup") { caiDat(win, cmd); return; }
    }
    if (!cmd || cmd.action !== "nordlogin") { return; }
    // Chi trang web (http/https). Addon NordVPN co ~7 trang nen moz-extension, trang nao cung
    // bao "seen" moi 1.5s -> de file ket qua, nhat ky chi con trang nen, mat dau trang dang nhap.
    if (!/^https?:/.test(win.location.href)) { return; }
    var doc = win.document, step = cmd.delay || 1500, waited = 0, cap = cmd.timeout || 180000;
    win.setTimeout(function tick() {
      try {
        if (laPopupNord(win)) {
          report("seen", "popup | " + dumpNhe(doc));
          chonQuocGia(win, doc, getCommand() || cmd);
        } else {
          var man = nordPhanLoai(win.location.href, txt(doc));
          report("seen", man + " | " + win.location.href.slice(0, 70) + " | " + dumpNhe(doc));
          if (man === "nord-in" && (emailXong || passXong)) { report("nord-logged-in", win.location.href.slice(0, 60)); return; }
          if (man === "nord-wrong") { report("nord-wrong", ""); }
          else if (man === "nord-login") { xuLy(win, doc, getCommand() || cmd); }
        }
      } catch (e) { report("tick-error", String(e)); }
      waited += step;
      if (waited < cap) { win.setTimeout(tick, step); }
    }, 900);
  }

  var observer = {
    observe: function (subject, topic) {
      if (topic !== "content-document-global-created") { return; }
      var win = subject;
      try {
        if (win.top !== win) { return; }      // chi trang chinh
        win.addEventListener("load", function onload() {
          win.removeEventListener("load", onload); onPage(win);
        }, { once: true });
      } catch (e) {}
    },
  };
  Services.obs.addObserver(observer, "content-document-global-created");
}
