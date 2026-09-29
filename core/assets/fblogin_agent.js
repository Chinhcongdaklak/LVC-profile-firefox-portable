/* Process script: DANG NHAP web bang id|pass|2fa tren facebook.com.
 *
 * Chay trong TIEN TRINH NOI DUNG (nhu fbcreate_agent.js). Muc dich: dien form
 * dang nhap + ma 2FA bang su kien "nguoi that" (setHandlingUserInput -> isTrusted),
 * trinh duyet mo BINH THUONG (khong --remote-debugging-port) -> Facebook KHONG
 * chan bang reCAPTCHA nhu khi chay qua WebDriver BiDi (da do that 2026-09-06).
 *
 * Bridge RIENG (khong dam agent tao page / dang bai):
 *   sendSyncMessage("qlfpwl:cmd")     -> cha doc <profile>/qlfp-weblogin.json
 *   sendAsyncMessage("qlfpwl:report") -> cha ghi <profile>/qlfp-weblogin-result.json
 *
 * Lenh: { action:"weblogin", email, pass, code, code_at, formTimeout, delay }
 *   code/code_at: ma 2FA (TOTP) + moc sinh; CHA lam moi dinh ky, agent doc lai moi tick.
 * Cha xac minh dang nhap thanh cong qua verify_cookie_login (qlfp-login.json), khong
 * dua vao agent doan "da vao".
 */
"use strict";

/* ---- phan THUAN (test duoc bang node): nhan dang KIEU man dang nhap ------------------ */
var QLFP_DUNG_KHAC_RE = /dùng trang cá nhân khác|dung trang ca nhan khac|use another profile|log into another account|đăng nhập bằng tài khoản khác|not you\?|switch accounts/i;
function qlfpLaDungKhac(text) { return QLFP_DUNG_KHAC_RE.test(text || ""); }
/** o = {coEmail, coPass, coTiepTuc, coDungKhac, url} -> "full" | "pass-only" | "saved-profile" | "".
 *  full = o email + pass (dien ca hai); pass-only = FB da biet acc, chi o pass; saved-profile = man
 *  "nho profile" (ten + Tiep tuc + Dung trang ca nhan khac, URL stype=lo/flo=1) -> bam Tiep tuc truoc. */
function qlfpKieuMan(o) {
  o = o || {};
  if (o.coEmail && o.coPass) { return "full"; }
  if (o.coPass) { return "pass-only"; }
  if (o.coTiepTuc && (o.coDungKhac || /[?&](stype=lo|flo=1)(&|$)/i.test(o.url || ""))) { return "saved-profile"; }
  return "";
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { kieuMan: qlfpKieuMan, laDungKhac: qlfpLaDungKhac };
}

if (typeof sendAsyncMessage === "function") {

  var lines = [];
  function report(state, detail) {
    lines.push(state + (detail ? ": " + detail : ""));
    try {
      sendAsyncMessage("qlfpwl:report", { state: state, detail: detail || "", log: lines.slice(-30) });
    } catch (e) {}
  }
  function getCommand() {
    try {
      var a = sendSyncMessage("qlfpwl:cmd");
      var raw = a && a.length ? a[0] : "";
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function low(s) { return (s || "").toLowerCase(); }
  function vis(el) {
    try { var b = el.getBoundingClientRect(); return b.width > 20 && b.height > 8 && el.offsetParent !== null; }
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
  function loginBtn(doc, win) {
    // Nut "Log in"/"Dang nhap": uu tien div[role=button] khop chu, roi button/input[name=login].
    var cands = Array.prototype.slice.call(doc.querySelectorAll('[role="button"],button,input[type="submit"]'));
    var m = cands.filter(function (b) {
      if (!vis(b)) { return false; }
      var s = low(b.getAttribute("aria-label")) + " " + low(b.textContent) + " " + low(b.value) + " " + low(b.name);
      return /log in|đăng nhập|dang nhap/.test(s);
    });
    if (m.length) { return m[m.length - 1]; }
    return q(doc, 'input[name=login],button[name=login],[data-testid=royal-login-button]');
  }
  /** Cac nut/link hien co chu khop ``re`` (aria-label uu tien, roi chu, roi value). */
  function nutTheoChu(doc, re) {
    var cands = Array.prototype.slice.call(doc.querySelectorAll('[role="button"],button,input[type=submit],a[href],[role="link"]'));
    return cands.filter(function (b) {
      if (!vis(b)) { return false; }
      var s = (b.getAttribute("aria-label") || b.textContent || b.value || "").replace(/\s+/g, " ").trim();
      return re.test(s);
    });
  }
  function moTaNut(el) {
    try {
      return el.tagName + "[role=" + (el.getAttribute("role") || "") + ",aria=" + (el.getAttribute("aria-label") || "").slice(0, 25)
        + ",href=" + (el.getAttribute("href") || "").slice(0, 30) + ",chu=" + (el.textContent || "").trim().slice(0, 20) + "]";
    } catch (e) { return "?"; }
  }
  /** Nut "Tiep tuc/Continue" tren man "nho profile": uu tien nut co aria-label "Tiep tuc <ten>" (nut that). */
  function tiepTucBtn(doc) {
    var ds = nutTheoChu(doc, /^(tiếp tục|tiep tuc|continue)(\s|$)/i);
    if (!ds.length) { return null; }
    var coTen = ds.filter(function (b) {
      var a = (b.getAttribute("aria-label") || "").trim();
      return /^(tiếp tục|tiep tuc|continue)\s+\S/i.test(a);
    });
    return (coTen.length ? coTen : ds)[0];
  }
  var lanTiepTuc = 0;    // so lan da bam "Tiep tuc" o man nho profile
  var lanInvalid = 0;    // so lan gap "Invalid request" o trang 2FA (back -> tiep tuc -> nhap mk, toi da 3)
  function codeInput(doc) {
    return q(doc, 'input[autocomplete=one-time-code],input[name=approvals_code],input#approvals_code')
      || (function () {
        var xs = Array.prototype.slice.call(doc.querySelectorAll('input[type=text],input[type=tel],input[inputmode=numeric]'))
          .filter(function (e) { return vis(e) && e.name !== "email"; });
        return xs[0] || null;
      })();
  }
  function contBtn(doc, win) {
    var cands = Array.prototype.slice.call(doc.querySelectorAll('[role="button"],button,input[type=submit]'));
    var m = cands.filter(function (b) {
      if (!vis(b)) { return false; }
      var s = low(b.getAttribute("aria-label")) + " " + low(b.textContent) + " " + low(b.value);
      return /continue|tiếp tục|tiep tuc|submit|xác nhận|xac nhan|next|đăng nhập|dang nhap|try another way|thử cách khác/.test(s)
             && !/thử cách khác|try another way/.test(s);
    });
    return m.length ? m[m.length - 1] : null;
  }
  function dump(doc) {
    var out = [];
    try {
      var xs = doc.querySelectorAll("input");
      for (var i = 0; i < xs.length && i < 10; i++) {
        var e = xs[i];
        out.push("in[name=" + (e.name || "") + ",type=" + (e.type || "") + ",ac=" + (e.autocomplete || "") + ",vis=" + (vis(e) ? 1 : 0) + "]");
      }
      var bs = doc.querySelectorAll('[role=button],button');
      var bt = [];
      for (var j = 0; j < bs.length && bt.length < 6; j++) {
        if (!vis(bs[j])) { continue; }
        bt.push((bs[j].getAttribute("aria-label") || bs[j].textContent || "").trim().slice(0, 18));
      }
      return out.join(" ") + " || btn: " + bt.join(" / ");
    } catch (e) { return "(dump loi)"; }
  }
  function errText(doc) {
    var t = low(doc.body ? doc.body.innerText : "");
    if (/wrong credentials|incorrect|sai m|password you.?ve entered|mật khẩu.*không|không chính xác/.test(t)) { return "wrong-pass"; }
    return "";
  }

  var lastCode = "";     // ma 2FA da submit -> khong submit lai cung ma

  /** Dien ma 2FA trong MOT document (top hoac iframe). Tra true neu tim thay o ma. */
  function twofaTick(win, doc, cmd) {
    var inp = codeInput(doc);
    if (!inp) { return false; }
    report("twofa-dom", dump(doc));
    var c = getCommand() || cmd;
    if (c.code && c.code !== lastCode) {
      setNative(win, inp, c.code);
      var cb = contBtn(doc, win);
      if (cb) { clickReal(win, cb); lastCode = c.code; report("twofa-filled", String(c.code_at || "")); }
      else { try { inp.form && inp.form.submit(); lastCode = c.code; report("twofa-submit-form", ""); } catch (e) {} }
    }
    return true;
  }

  function onFrame(win) {
    // IFRAME: chi lo dien 2FA (o ma 2FA cua FB nam trong iframe fbsbx). Khong dien form login.
    var cmd = getCommand();
    if (!cmd || cmd.action !== "weblogin") { return; }
    var doc = win.document, step = cmd.delay || 2000, waited = 0, cap = cmd.formTimeout || 45000;
    report("seen", "[iframe] " + win.location.href.slice(0, 60) + " | " + dump(doc));
    win.setTimeout(function tick() {
      if (twofaTick(win, doc, cmd)) {
        report("seen", "[iframe] " + win.location.href.slice(0, 60) + " | " + dump(doc));
      }
      waited += step;
      if (codeInput(doc) && waited < cap) { win.setTimeout(tick, step); }
    }, 800);
  }

  // ---- LUONG KHOI PHUC (khi login web bi "Invalid request" o trang 2FA) ------------------
  // Vao quen mat khau -> dien mail khoi phuc -> chon "nhap mat khau" -> pass -> 2FA.
  // Dinh captcha -> DUNG YEN cho nguoi dung giai; khi 2FA hien ra thi tu dien.
  function coCaptcha(doc) {
    try {
      if (doc.querySelector('iframe[src*="recaptcha"],iframe[title*="recaptcha"],iframe[src*="hcaptcha"],iframe[src*="arkoselabs"],iframe[src*="fbsbx"][title*="challenge"],iframe[title*="challenge"]')) { return true; }
      var t = low(doc.body ? doc.body.innerText : "");
      return /security check|xác nhận bạn là|i'?m not a robot|không phải người máy|hãy xác nhận|hoàn tất kiểm tra bảo mật|complete the security check|giải câu đố/.test(t);
    } catch (e) { return false; }
  }
  function identifyInput(doc) {
    return q(doc, "input[name=email]") || q(doc, "input[type=email]")
        || q(doc, "input[type=tel]") || q(doc, 'input[type=text]:not([name=pass])');
  }
  var recStep = "";     // buoc khoi phuc gan nhat da lam (tranh lap lien tuc)
  function xuLyKhoiPhuc(win, cmd) {
    var waited = 0, cap = (cmd.recoverTimeout || 130000), step = 2500;
    report("recover-page", win.location.href.slice(0, 80));
    (function tick() {
      var d = win.document, c = getCommand() || cmd;
      // 1) CAPTCHA -> dung yen, cho nguoi dung giai (bao dinh ky), khong bam gi.
      if (coCaptcha(d)) {
        report("captcha-wait", "dính captcha — chờ người dùng giải (~" + Math.round((cap - waited) / 1000) + "s)");
        waited += step; if (waited < cap) { win.setTimeout(tick, step); } return;
      }
      // 2) O ma 2FA -> tu dien ma (giong login thuong).
      if (codeInput(d)) {
        twofaTick(win, d, c);
        waited += step; if (waited < cap) { win.setTimeout(tick, step); } return;
      }
      // 3) O mat khau -> dien pass roi Tiep tuc.
      var pw = q(d, "input[name=pass]") || q(d, 'input[type="password"]');
      if (pw && vis(pw)) {
        if (recStep !== "pass") {
          recStep = "pass";
          setNative(win, pw, c.pass);
          var b = contBtn(d, win) || loginBtn(d, win);
          if (b) { clickReal(win, b); report("recover-pass", "điền mật khẩu + tiếp tục"); }
          else { try { pw.form && pw.form.submit(); report("recover-pass", "submit form"); } catch (e) {} }
        }
        waited += step; if (waited < cap) { win.setTimeout(tick, step); } return;
      }
      // 4) Man "chọn cách" (email code / password) -> chon NHAP MAT KHAU / thu cach khac.
      var chon = nutTheoChu(d, /nhập mật khẩu|enter (your )?password|dùng mật khẩu|use password|thử cách khác|try another way|cách khác/i);
      if (chon.length && recStep !== "choose") {
        recStep = "choose"; clickReal(win, chon[0]); report("recover-choose-pass", moTaNut(chon[0]));
        waited += step; if (waited < cap) { win.setTimeout(tick, step); } return;
      }
      // 5) Trang identify -> dien MAIL KHOI PHUC roi Tim kiem/Tiep tuc.
      var idin = identifyInput(d);
      if (idin && vis(idin) && !(idin.value || "").trim() && recStep !== "identify") {
        recStep = "identify";
        setNative(win, idin, c.recovery_mail || "");
        var cont = contBtn(d, win) || (nutTheoChu(d, /tìm kiếm|search|tiếp tục|continue|tìm/i)[0]);
        if (cont) { clickReal(win, cont); report("recover-identify", "điền mail khôi phục"); }
        else { try { idin.form && idin.form.submit(); report("recover-identify", "submit"); } catch (e) {} }
        waited += step; if (waited < cap) { win.setTimeout(tick, step); } return;
      }
      report("seen", "[recover] " + win.location.href.slice(0, 60) + " | " + dump(d));
      recStep = "";     // trang doi -> cho phep lam buoc moi
      waited += step; if (waited < cap) { win.setTimeout(tick, step); }
    })();
  }

  function onPage(win) {
    var cmd = getCommand();
    if (!cmd || cmd.action !== "weblogin") { return; }
    var doc = win.document, href = low(win.location.href);

    // Trang khoi phuc (quen mat khau / identify / recover) -> xu ly rieng.
    if (href.indexOf("/login/identify") !== -1 || href.indexOf("/recover") !== -1
        || href.indexOf("/recovery") !== -1) {
      return xuLyKhoiPhuc(win, cmd);
    }
    // Trang 2FA bi "Invalid request" (theo yeu cau nguoi dung 2026-09-17):
    //   QUAY LAI -> bam "Tiep tuc" de dang nhap -> bam "Nhap mat khau". Lam lai toi da 3 lan;
    //   qua 3 lan van loi -> bao "invalid-fail" (cha tat trinh duyet + bao loi dang nhap).
    try {
      var bodyLow = low(doc.body ? doc.body.innerText : "");
      if (href.indexOf("two_step_verification") !== -1
          && /invalid request|could not validate|try starting the flow|bắt đầu lại|không xác thực được/.test(bodyLow)) {
        lanInvalid++;
        if (lanInvalid > 3) {
          report("invalid-fail", "Invalid request 3 lần → tắt trình duyệt, báo lỗi đăng nhập");
          return;
        }
        report("invalid-back", "lần " + lanInvalid + ": quay lại → tiếp tục → nhập mật khẩu");
        try { win.history.back(); } catch (e) { try { win.history.go(-1); } catch (e2) {} }
        return;
      }
    } catch (e) {}

    var step = cmd.delay || 2000, waited = 0, cap = cmd.formTimeout || 40000;

    // Chan doan: bao trang vua tai (url + cau truc) — cha ghi lai moi thay doi.
    report("seen", win.location.href.slice(0, 70) + " | " + dump(doc));
    win.setTimeout(function () {
      try { report("seen", win.location.href.slice(0, 70) + " | " + dump(win.document)); } catch (e) {}
    }, 5000);

    if (href.indexOf("/checkpoint") !== -1) {
      // AN HAN 12s: fbskip_agent bam "Bo qua" neu checkpoint MEM; con ke lai -> bao checkpoint.
      win.setTimeout(function () {
        try {
          if ((win.location.href || "").indexOf("/checkpoint") !== -1) { report("checkpoint", win.location.href.slice(0, 80)); }
        } catch (e) {}
      }, 12000);
      return;
    }

    // Trang co o ma 2FA (two_step / two_factor / co o code) -> dien ma.
    win.setTimeout(function tick2fa() {
      twofaTick(win, doc, cmd);
      waited += step;
      if (codeInput(doc) && waited < cap) { win.setTimeout(tick2fa, step); }
    }, 500);

    // Form dang nhap: NHAN DANG kieu man roi lam dung viec (ADR-019):
    //   full (email+pass) -> dien ca hai; pass-only -> chi dien pass (FB da biet acc);
    //   saved-profile ("Tiep tuc" / "Dung trang ca nhan khac") -> bam Tiep tuc, tick lai ra o pass.
    win.setTimeout(function tickLogin() {
      var em = q(doc, "input[name=email]"), pw = q(doc, "input[name=pass]");
      var er = errText(doc);
      if (er) { report(er, ""); return; }
      // Sau khi "quay lai" tu trang Invalid request (lanInvalid>0): neu FB hoi cach xac minh,
      // CHON "Nhap mat khau" de ve o mat khau (khong co o pass + khong co o ma 2FA moi chon).
      if (lanInvalid > 0 && !(pw && vis(pw)) && !codeInput(doc)) {
        var np = nutTheoChu(doc, /nhập mật khẩu|nhap mat khau|enter (your )?password|dùng mật khẩu|use password|đăng nhập bằng mật khẩu/i);
        if (np.length) {
          clickReal(win, np[0]); try { np[0].click(); } catch (e) {}
          report("invalid-choose-pass", "lần " + lanInvalid + " " + moTaNut(np[0]));
          waited += step; if (waited < cap) { win.setTimeout(tickLogin, 2500); }
          return;
        }
      }
      var tt = tiepTucBtn(doc);
      var kieu = qlfpKieuMan({
        coEmail: !!(em && vis(em)), coPass: !!(pw && vis(pw)), coTiepTuc: !!tt,
        coDungKhac: qlfpLaDungKhac(doc.body ? doc.body.innerText : ""), url: win.location.href });
      if (kieu === "saved-profile") {
        lanTiepTuc++;
        var ds = nutTheoChu(doc, /^(tiếp tục|tiep tuc|continue)(\s|$)/i);
        report("seen", "nho-profile lan " + lanTiepTuc + " | " + ds.map(moTaNut).join(" ; ").slice(0, 320));
        if (lanTiepTuc <= 2) {
          // Lan 1: chuoi su kien "nguoi that"; lan 2: them .click() + href (neu la link).
          clickReal(win, tt);
          if (lanTiepTuc === 2) {
            try { tt.click(); } catch (e) {}
            try { var h = tt.getAttribute("href"); if (h && /login/i.test(h)) { win.location.href = h; } } catch (e) {}
          }
          report("saved-profile-continue", "lan " + lanTiepTuc + " " + moTaNut(tt));
        } else {
          // Van ke man nho profile -> "Dung trang ca nhan khac" ra form email+pass (agent dien duoc).
          var khac = nutTheoChu(doc, /dùng trang cá nhân khác|dung trang ca nhan khac|use another profile|log into another account|đăng nhập bằng tài khoản khác/i);
          if (khac.length) {
            clickReal(win, khac[0]);
            try { khac[0].click(); } catch (e) {}
            report("saved-profile-other", moTaNut(khac[0]));
          }
        }
        waited += step;
        if (waited < cap) { win.setTimeout(tickLogin, 3000); }
        return;
      }
      if (kieu === "full" || kieu === "pass-only") {
        if (kieu === "full") { setNative(win, em, cmd.email); }
        setNative(win, pw, cmd.pass);
        var b = loginBtn(doc, win);
        if (b) { clickReal(win, b); report("clicked-login", kieu); }
        else { try { pw.form && pw.form.submit(); report("login-submit-form", kieu); } catch (e) {} }
        // Sau khi bam: neu con o trang dang nhap (pass van hien) -> bao van ban de biet
        // sai mat khau / bi chan. Giup errText nhan dung + chan doan.
        win.setTimeout(function () {
          try {
            var p2 = win.document.querySelector("input[name=pass]");
            if (p2 && vis(p2) && !codeInput(win.document)) {
              var t = (win.document.body ? win.document.body.innerText : "").replace(/\s+/g, " ").slice(0, 200);
              report("login-result", win.location.href.slice(0, 50) + " :: " + t);
              var er = errText(win.document);
              if (er) { report(er, ""); }
            }
          } catch (e) {}
        }, 7000);
        return;
      }
      waited += step;
      if (waited < cap && !codeInput(doc)) { win.setTimeout(tickLogin, step); }
    }, step);
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
