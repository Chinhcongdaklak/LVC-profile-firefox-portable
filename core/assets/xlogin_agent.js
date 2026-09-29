/* Process script: DANG NHAP X.com bang "Dang nhap bang Google".
 *
 * Cung khuon fblogin_agent.js: chay trong tien trinh noi dung, dien form bang
 * su kien "nguoi that" (setHandlingUserInput), trinh duyet mo BINH THUONG.
 *
 * Bridge RIENG:
 *   sendSyncMessage("qlfpxl:cmd")     -> cha doc <profile>/qlfp-xlogin.json
 *   sendAsyncMessage("qlfpxl:report") -> cha ghi <profile>/qlfp-xlogin-result.json
 *
 * Lenh: { action:"xlogin", gmail, pass_gmail, gmail_kp, user_x, pass_x,
 *         code, code_at, formTimeout, delay, timeout }
 *   code/code_at: ma 2FA Gmail (TOTP) + moc; cha lam moi dinh ky, agent doc lai moi tick.
 * Cha xac minh dang nhap that su qua cookie auth_token (doc cookies.sqlite), khong
 * dua vao agent doan.
 *
 * Luong: x.com trang dang nhap -> bam "Dang nhap bang Google" -> man Google
 * (chon tai khoan / nhap gmail -> pass -> 2FA -> dong y) -> quay ve x.com da vao.
 */
"use strict";

/* ---- phan THUAN (test bang node): nhan biet man dang o dau -------------------------- */
var XL_GOOGLE_RE = /sign in with google|đăng nhập bằng google|dang nhap bang google|continue with google|tiếp tục với google|tiep tuc voi google/i;
function xlLaNutGoogle(text) { return XL_GOOGLE_RE.test(text || ""); }
/** phanLoai(url, text) -> man hinh hien tai. THUAN, khong dung DOM. */
function xlPhanLoai(url, text) {
  url = (url || "").toLowerCase();
  text = text || "";
  if (/accounts\.google\.|accounts\.youtube\./.test(url)) {
    if (/wrong password|mật khẩu.*không chính xác|mat khau.*khong chinh xac|incorrect password/i.test(text)) { return "g-wrong-pass"; }
    if (/couldn.?t sign you in|couldn.?t verify|không thể đăng nhập|khong the dang nhap|this browser or app may not be secure/i.test(text)) { return "g-rejected"; }
    return "google";
  }
  if (/x\.com|twitter\.com/.test(url)) {
    if (/\/home(\b|$|\?)/.test(url)) { return "x-home"; }
    if (/account\/access|\/suspended|your account is (locked|suspended)|tài khoản.*(khoá|khóa|tạm khoá)/i.test(url + " " + text)) { return "x-locked"; }
    if (/i\/flow\/login|\/login|\/i\/flow\/signup/.test(url)) { return "x-login"; }
    return "x";
  }
  return "";
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { laNutGoogle: xlLaNutGoogle, phanLoai: xlPhanLoai };
}

if (typeof sendAsyncMessage === "function") {

  var lines = [];
  function report(state, detail) {
    lines.push(state + (detail ? ": " + detail : ""));
    try {
      sendAsyncMessage("qlfpxl:report", { state: state, detail: detail || "", log: lines.slice(-30) });
    } catch (e) {}
  }
  function getCommand() {
    try {
      var a = sendSyncMessage("qlfpxl:cmd");
      var raw = a && a.length ? a[0] : "";
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function low(s) { return (s || "").toLowerCase(); }
  function vis(el) {
    try { var b = el.getBoundingClientRect(); return b.width > 12 && b.height > 8 && el.offsetParent !== null; }
    catch (e) { return false; }
  }
  function setNative(win, el, val) {
    try {
      var proto = el.tagName === "TEXTAREA" ? win.HTMLTextAreaElement.prototype : win.HTMLInputElement.prototype;
      var setter = Object.getOwnPropertyDescriptor(proto, "value").set;
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

  /** Cac nut/link hien co chu khop ``re`` (aria-label uu tien, roi chu). */
  function nutTheoChu(doc, re) {
    var cands = Array.prototype.slice.call(doc.querySelectorAll('[role="button"],button,input[type=submit],a[href],[role="link"],div[data-testid]'));
    return cands.filter(function (b) {
      if (!vis(b)) { return false; }
      var s = (b.getAttribute("aria-label") || b.textContent || b.value || "").replace(/\s+/g, " ").trim();
      return re.test(s);
    });
  }
  function dump(doc) {
    var out = [];
    try {
      var xs = doc.querySelectorAll("input");
      for (var i = 0; i < xs.length && i < 8; i++) {
        var e = xs[i];
        out.push("in[name=" + (e.name || "") + ",type=" + (e.type || "") + ",ac=" + (e.autocomplete || "") + ",vis=" + (vis(e) ? 1 : 0) + "]");
      }
      var bs = doc.querySelectorAll('[role=button],button');
      var bt = [];
      for (var j = 0; j < bs.length && bt.length < 6; j++) {
        if (!vis(bs[j])) { continue; }
        bt.push((bs[j].getAttribute("aria-label") || bs[j].textContent || "").trim().slice(0, 20));
      }
      return out.join(" ") + " || btn: " + bt.join(" / ");
    } catch (e) { return "(dump loi)"; }
  }

  // ---- man X.com: bam "Dang nhap bang Google" -----------------------------------------
  var lanGoogle = 0;
  function bamNutGoogle(win, doc) {
    var ds = nutTheoChu(doc, XL_GOOGLE_RE);
    if (!ds.length) { return false; }
    // Nut Google that thuong la phan tu bao ngoai (role=button / a) -> bam ban ngoai cung hien.
    var el = ds[0];
    clickReal(win, el);
    lanGoogle++;
    report("x-google-clicked", "lần " + lanGoogle);
    return true;
  }

  // ---- man Google: dien gmail -> pass -> 2FA -> dong y --------------------------------
  var passDaDien = "", codeDaDien = "";
  function oNhap(doc, kieu) {
    // kieu: "email" | "pass" | "code"
    var sel = kieu === "email" ? 'input[type=email],input#identifierId,input[name=identifier]'
      : kieu === "pass" ? 'input[type=password][name=Passwd],input[type=password]'
        : 'input[type=tel],input[name=totpPin],input[autocomplete=one-time-code],input[type=text]';
    var xs = Array.prototype.slice.call(doc.querySelectorAll(sel)).filter(vis);
    return xs[0] || null;
  }
  function nutTiepGoogle(win, doc) {
    // Google: nut "Next/Tiep theo" -> id #identifierNext/#passwordNext, hoac chu.
    var b = q(doc, "#identifierNext button, #passwordNext button, #totpNext button, #next button");
    if (b && vis(b)) { return b; }
    var ds = nutTheoChu(doc, /^(next|tiếp theo|tiep theo|tiếp|verify|xác minh|xac minh|continue|tiếp tục|tiep tuc)$/i);
    return ds.length ? ds[ds.length - 1] : null;
  }
  function nutDongY(win, doc) {
    var ds = nutTheoChu(doc, /^(continue|tiếp tục|tiep tuc|allow|cho phép|cho phep|đồng ý|dong y|i agree|accept)$/i);
    return ds.length ? ds[ds.length - 1] : null;
  }

  function xuLyGoogle(win, doc, cmd) {
    var t = low(txt(doc));
    if (/wrong password|mật khẩu.*không chính xác|mat khau.*khong chinh xac|incorrect password/.test(t)) { report("g-wrong-pass", ""); return; }
    if (/couldn.?t sign you in|không thể đăng nhập|khong the dang nhap|this browser or app may not be secure/.test(t)) { report("g-rejected", ""); return; }
    if (/verify it.?s you|xác minh danh tính|xac minh danh tinh|verify your phone|use your phone|thiết bị khác|thiet bi khac/.test(t)
        && !oNhap(doc, "code") && !oNhap(doc, "pass")) {
      // Google doi xac minh SDT/thiet bi -> khong tu lam duoc, bao de nguoi dung xu ly tay.
      report("g-verify-phone", "");
    }

    // Buoc 1: o email (neu chua chon san tai khoan).
    var oEmail = oNhap(doc, "email");
    if (oEmail && !oEmail.value) {
      if (cmd.gmail) { setNative(win, oEmail, cmd.gmail); report("g-email-filled", ""); var n1 = nutTiepGoogle(win, doc); if (n1) { clickReal(win, n1); } }
      return;
    }
    // Neu Google hien danh sach chon tai khoan co san -> bam dung email.
    var chon = nutTheoChu(doc, new RegExp(cmd.gmail ? cmd.gmail.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") : "@gmail\\.com", "i"));
    if (chon.length && !oNhap(doc, "pass")) { clickReal(win, chon[0]); report("g-account-chosen", ""); return; }

    // Buoc 2: o mat khau.
    var oPass = oNhap(doc, "pass");
    if (oPass) {
      if (cmd.pass_gmail && passDaDien !== cmd.pass_gmail) {
        setNative(win, oPass, cmd.pass_gmail); passDaDien = cmd.pass_gmail; report("g-pass-filled", "");
        var n2 = nutTiepGoogle(win, doc); if (n2) { clickReal(win, n2); }
      }
      return;
    }
    // Buoc 3: o ma 2FA (TOTP).
    var oCode = oNhap(doc, "code");
    if (oCode) {
      var c = (getCommand() || cmd).code;
      if (c && codeDaDien !== c) {
        setNative(win, oCode, c); codeDaDien = c; report("g-totp-filled", "");
        var n3 = nutTiepGoogle(win, doc); if (n3) { clickReal(win, n3); }
      }
      return;
    }
    // Buoc 4: man dong y (cho phep X truy cap).
    var dy = nutDongY(win, doc);
    if (dy) { clickReal(win, dy); report("g-consent-clicked", ""); }
  }

  // ---- man X sau khi ve: co the con hoi username/pass cua chinh X ---------------------
  function xuLyXSauGoogle(win, doc, cmd) {
    // X doi nhap username/dien thoai/email -> dien user_x; doi mat khau -> pass_x.
    var oUser = q(doc, 'input[autocomplete=username],input[name=text],input[name=session[username_or_email]]');
    if (oUser && vis(oUser) && !oUser.value && cmd.user_x) {
      setNative(win, oUser, cmd.user_x); report("x-username-needed", "");
      var nx = nutTheoChu(doc, /^(next|tiếp theo|tiep theo|log in|đăng nhập|dang nhap)$/i);
      if (nx.length) { clickReal(win, nx[nx.length - 1]); }
      return;
    }
    var oPassX = q(doc, 'input[type=password][name=password],input[name=session[password]],input[type=password]');
    if (oPassX && vis(oPassX) && !oPassX.value && cmd.pass_x) {
      setNative(win, oPassX, cmd.pass_x);
      var lg = nutTheoChu(doc, /^(log in|đăng nhập|dang nhap)$/i);
      if (lg.length) { clickReal(win, lg[lg.length - 1]); }
    }
  }

  function onPage(win) {
    var cmd = getCommand();
    if (!cmd || cmd.action !== "xlogin") { return; }
    var doc = win.document, step = cmd.delay || 1500, waited = 0, cap = cmd.timeout || 240000;
    win.setTimeout(function tick() {
      try {
        var url = win.location.href;
        var man = xlPhanLoai(url, txt(doc));
        report("seen", man + " | " + url.slice(0, 70) + " | " + dump(doc));
        if (man === "x-home") { report("x-logged-in", url.slice(0, 60)); return; }
        if (man === "x-locked") { report("x-locked", url.slice(0, 60)); return; }
        else if (man === "x-login" || man === "x") {
          // Uu tien bam nut Google; neu X dang hoi username/pass cua X thi dien.
          if (!bamNutGoogle(win, doc)) { xuLyXSauGoogle(win, doc, cmd); }
        } else if (man === "google" || man === "g-wrong-pass" || man === "g-rejected") {
          xuLyGoogle(win, doc, getCommand() || cmd);
        }
      } catch (e) { report("tick-error", String(e)); }
      waited += step;
      if (waited < cap) { win.setTimeout(tick, step); }
    }, 900);
  }

  function onFrame(win) {
    // Man Google/consent doi khi nam trong iframe -> xu ly nhu trang Google.
    var cmd = getCommand();
    if (!cmd || cmd.action !== "xlogin") { return; }
    var doc = win.document, step = cmd.delay || 1500, waited = 0, cap = cmd.timeout || 240000;
    win.setTimeout(function tick() {
      try {
        var man = xlPhanLoai(win.location.href, txt(doc));
        if (man === "google" || man === "g-wrong-pass" || man === "g-rejected") {
          report("seen", "[iframe] " + win.location.href.slice(0, 60) + " | " + dump(doc));
          xuLyGoogle(win, doc, getCommand() || cmd);
        }
      } catch (e) {}
      waited += step;
      if (waited < cap) { win.setTimeout(tick, step); }
    }, 900);
  }

  var observer = {
    observe: function (subject, topic) {
      if (topic !== "content-document-global-created") { return; }
      var win = subject;
      try {
        var top = (win.top === win);
        win.addEventListener("load", function onload() {
          win.removeEventListener("load", onload);
          if (top) { onPage(win); } else { onFrame(win); }
        }, { once: true });
      } catch (e) {}
    },
  };
  Services.obs.addObserver(observer, "content-document-global-created");
}
