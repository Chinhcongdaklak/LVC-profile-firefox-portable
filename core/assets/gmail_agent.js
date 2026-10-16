/* Process script: DANG NHAP GMAIL (tai khoan Google) tren trinh duyet cua acc YouTube.
 *
 * Cung khuon xlogin_agent.js (da chay that cho "Dang nhap X bang Google"), nhung di
 * THANG vao accounts.google.com — khong qua x.com. Lay tu tool "LVC video slide"
 * (core/firefox_login.dien_form_google) THU TU BUOC: email -> Next -> pass -> Next -> 2FA.
 *
 * Bridge RIENG:
 *   sendSyncMessage("qlfpgm:cmd")     -> cha doc <profile>/qlfp-gmail.json
 *   sendAsyncMessage("qlfpgm:report") -> cha ghi <profile>/qlfp-gmail-result.json
 *
 * Lenh: { action:"gmail", gmail, pass_gmail, mail_kp, code, code_at, delay, timeout }
 *   code: ma TOTP 2FA (cha lam moi moi 5s, agent doc lai moi nhip).
 * Cha XAC MINH bang COOKIE Google that (SID/SAPISID trong cookies.sqlite), khong tin agent doan.
 */
"use strict";

/* ---- phan THUAN (test bang node) ---------------------------------------------------- */
/** gmPhanLoai(url, text) -> man hinh hien tai. THUAN. */
function gmPhanLoai(url, text) {
  url = (url || "").toLowerCase();
  text = text || "";
  if (/myaccount\.google\.|mail\.google\.|youtube\.com|studio\.youtube\./.test(url)) { return "g-in"; }
  if (/accounts\.google\.|accounts\.youtube\./.test(url)) {
    if (/wrong password|mật khẩu.*không chính xác|mat khau.*khong chinh xac|incorrect password/i.test(text)) { return "g-wrong-pass"; }
    if (/couldn.?t sign you in|couldn.?t verify|không thể đăng nhập|khong the dang nhap|this browser or app may not be secure|browser or app may not be secure/i.test(text)) { return "g-rejected"; }
    if (/account (has been )?disabled|tài khoản.*(bị vô hiệu|đã bị khoá)|account disabled/i.test(text)) { return "g-disabled"; }
    if (/\/signin\/v2\/challenge\/|\/challenge\//.test(url) || /verify it.?s you|xác minh danh tính|xac minh danh tinh/i.test(text)) { return "g-challenge"; }
    return "google";
  }
  return "";
}
/** Man xac minh KHONG tu lam duoc (doi dien thoai / thiet bi khac) -> de nguoi dung lam tay. */
function gmCanNguoiThat(text) {
  return /get a verification code|tap yes on your phone|chạm vào có|cham vao co|use your phone|xác minh qua điện thoại|xac minh qua dien thoai|recovery phone|số điện thoại khôi phục/i.test(text || "");
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { phanLoai: gmPhanLoai, canNguoiThat: gmCanNguoiThat };
}

if (typeof sendAsyncMessage === "function") {

  var lines = [];
  function report(state, detail) {
    lines.push(state + (detail ? ": " + detail : ""));
    try {
      sendAsyncMessage("qlfpgm:report", { state: state, detail: detail || "", log: lines.slice(-30) });
    } catch (e) {}
  }
  function getCommand() {
    try {
      var a = sendSyncMessage("qlfpgm:cmd");
      var raw = a && a.length ? a[0] : "";
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function low(s) { return (s || "").toLowerCase(); }
  function txt(doc) { try { return (doc.body ? doc.body.innerText : "") || ""; } catch (e) { return ""; } }
  function q(doc, sel) { try { return doc.querySelector(sel); } catch (e) { return null; } }
  /** O co dang hien khong.
   *
   * KHONG dung offsetParent: the dang nhap cua Google nam trong khoi position:fixed ->
   * offsetParent === null du o van hien ro -> agent tuong khong co o nao va dung im
   * (da mac dung loi nay khi chay that 05/10). Do bang kich thuoc + computed style.
   */
  function vis(el) {
    try {
      var b = el.getBoundingClientRect();
      if (b.width <= 12 || b.height <= 8) { return false; }
      var st = el.ownerDocument.defaultView.getComputedStyle(el);
      if (!st) { return true; }
      return st.visibility !== "hidden" && st.display !== "none" && st.opacity !== "0";
    } catch (e) { return false; }
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
      var r = el.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      ["pointerdown", "mousedown", "pointerup", "mouseup", "click"].forEach(function (t) {
        var E = t.indexOf("pointer") === 0 ? win.PointerEvent : win.MouseEvent;
        el.dispatchEvent(new E(t, { bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0 }));
      });
      try { el.click(); } catch (e) {}
      return true;
    } catch (e) { return false; } finally {
      if (handle) { try { handle.destruct(); } catch (e) {} }
    }
  }
  function nutTheoChu(doc, re) {
    var ra = [];
    try {
      var els = doc.querySelectorAll('button,[role=button],div[jsname],a,span');
      for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var t = (el.innerText || el.textContent || "").trim();
        if (t && t.length <= 60 && re.test(t) && vis(el)) { ra.push(el); }
      }
    } catch (e) {}
    return ra;
  }
  /** Chan doan: o nao CO tren trang, o nao agent THAY (sau loc hien), nut Tiep co khong. */
  function dump(doc) {
    try {
      var out = [];
      [["email", 'input[type=email],input#identifierId'],
       ["pass", 'input[type=password]'],
       ["code", 'input[type=tel],input[name=totpPin],input[autocomplete=one-time-code]']
      ].forEach(function (c) {
        var el = q(doc, c[1]);
        if (!el) { return; }
        out.push(c[0] + (vis(el) ? "(thấy" : "(ẨN") + (el.value ? ",có chữ)" : ")"));
      });
      var thay = ["email", "pass", "code"].filter(function (k) { return !!oNhap(doc, k); });
      var bt = nutTheoChu(doc, /.+/).slice(0, 5).map(function (b) {
        return (b.innerText || "").trim().replace(/\s+/g, " ").slice(0, 16);
      });
      return "ô: " + (out.join(" ") || "không có")
        + " | agent dùng: " + (thay.join(",") || "không")
        + " | nút tiếp: " + (nutTiep(null, doc) ? "có" : "không")
        + " || btn: " + bt.join(" / ");
    } catch (e) { return "(dump loi: " + e + ")"; }
  }

  // ---- cac o nhap cua Google ---------------------------------------------------------
  function oNhap(doc, kieu) {
    var sel = kieu === "email" ? 'input[type=email],input#identifierId,input[name=identifier]'
      : kieu === "pass" ? 'input[type=password][name=Passwd],input[type=password]'
        : 'input[type=tel],input[name=totpPin],input[autocomplete=one-time-code]';
    var xs = Array.prototype.slice.call(doc.querySelectorAll(sel)).filter(vis);
    return xs[0] || null;
  }
  function nutTiep(win, doc) {
    var b = q(doc, "#identifierNext button, #passwordNext button, #totpNext button, #next button");
    if (b && vis(b)) { return b; }
    var ds = nutTheoChu(doc, /^(next|tiếp theo|tiep theo|tiếp|verify|xác minh|xac minh|continue|tiếp tục|tiep tuc)$/i);
    return ds.length ? ds[ds.length - 1] : null;
  }
  function nutThuCach(doc) {
    // "Try another way" / "Thử cách khác" -> mo danh sach cach xac minh (chon Authenticator).
    var ds = nutTheoChu(doc, /^(try another way|thử cách khác|thu cach khac|cách khác|cach khac)$/i);
    return ds.length ? ds[0] : null;
  }
  function nutAuthenticator(doc) {
    var ds = nutTheoChu(doc, /authenticator|ứng dụng xác thực|ung dung xac thuc|get a code from/i);
    return ds.length ? ds[0] : null;
  }

  /** Bam THAT vao o roi dat con tro (o cua Google co khi chi "song" sau khi duoc bam). */
  function bamVaoO(win, el) {
    try {
      var r = el.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      var handle = null;
      try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
      try {
        ["pointerdown", "mousedown", "pointerup", "mouseup", "click"].forEach(function (t) {
          var E = t.indexOf("pointer") === 0 ? win.PointerEvent : win.MouseEvent;
          el.dispatchEvent(new E(t, { bubbles: true, cancelable: true,
                                      clientX: cx, clientY: cy, button: 0 }));
        });
      } finally { if (handle) { try { handle.destruct(); } catch (e) {} } }
      el.focus();
    } catch (e) {}
  }

  /** Go TUNG KY TU (keydown + keypress + input) — chac tay khi dat value thang khong an. */
  function goTungKyTu(win, el, val) {
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try {
      for (var i = 0; i < val.length; i++) {
        var c = val[i], ma = val.charCodeAt(i);
        el.dispatchEvent(new win.KeyboardEvent("keydown", { bubbles: true, cancelable: true,
                                                           key: c, keyCode: 229, which: 229 }));
        el.dispatchEvent(new win.KeyboardEvent("keypress", { bubbles: true, cancelable: true,
                                                            key: c, charCode: ma, keyCode: ma, which: ma }));
        el.value = (el.value || "") + c;
        el.dispatchEvent(new win.InputEvent("input", { bubbles: true, inputType: "insertText", data: c }));
        el.dispatchEvent(new win.KeyboardEvent("keyup", { bubbles: true, cancelable: true,
                                                         key: c, keyCode: ma, which: ma }));
      }
    } catch (e) { report("type-error", String(e)); } finally {
      if (handle) { try { handle.destruct(); } catch (e) {} }
    }
  }

  /** Dien MOT o cho chac: bam that -> setNative -> chua vao thi go tung ky tu. */
  function dienO(win, doc, el, val) {
    bamVaoO(win, el);
    setNative(win, el, val);
    if ((el.value || "") !== val) {
      try { el.value = ""; } catch (e) {}
      goTungKyTu(win, el, val);
    }
    return (el.value || "") === val;
  }

  var passDaDien = "", codeDaDien = "", daThuCach = false;
  var lanDienPass = 0, lanDienCode = 0, lanDienEmail = 0, lanBamEmail = 0, choEmail = 0;

  function xuLyGoogle(win, doc, cmd) {
    var t = low(txt(doc));

    // Buoc 1: o email. O CO SAN CHU (lan truoc da go) thi phai BAM TIEP, khong thi
    // trang dung mai o man nhap email (da mac dung loi nay khi chay that 05/10).
    var oEmail = oNhap(doc, "email");
    if (oEmail && cmd.gmail) {
      if ((oEmail.value || "").trim().toLowerCase() !== cmd.gmail.trim().toLowerCase()) {
        if (lanDienEmail >= 4) { report("g-email-stuck", "gõ 4 lần mà ô email vẫn sai/trống"); return; }
        lanDienEmail += 1;
        try { oEmail.value = ""; } catch (e) {}
        var okE = dienO(win, doc, oEmail, cmd.gmail);
        report("g-email-filled", "lần " + lanDienEmail + (okE ? "" : " (ô VẪN TRỐNG)"));
        return;                      // nhip sau xac minh roi moi bam Tiep
      }
      // O da dung email -> bam Tiep (thu lai moi 5 nhip neu trang khong chuyen, toi da 3 lan).
      choEmail += 1;
      if (lanBamEmail < 3 && (lanBamEmail === 0 || choEmail % 5 === 0)) {
        var n1 = nutTiep(win, doc);
        if (n1) {
          lanBamEmail += 1;
          clickReal(win, n1);
          report("g-email-submit", "lần " + lanBamEmail);
        } else {
          report("g-khong-thay-nut-tiep", "");
        }
      }
      return;
    }
    // CHI bam chip chon tai khoan khi CHUA TUNG dien pass: dien roi ma bam chip la
    // Google tai lai man mat khau, o bi xoa -> vong luan quan (da mac that 05/10).
    if (cmd.gmail && !oNhap(doc, "pass") && lanDienPass === 0) {
      var chon = nutTheoChu(doc, new RegExp(cmd.gmail.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"));
      if (chon.length) { clickReal(win, chon[0]); report("g-account-chosen", ""); return; }
    }

    // Buoc 2: mat khau — dien CHAC TAY roi XAC MINH o nhip sau moi bam Tiep.
    var oPass = oNhap(doc, "pass");
    if (oPass) {
      if (!cmd.pass_gmail) { report("g-thieu-pass", ""); return; }
      if ((oPass.value || "") === cmd.pass_gmail) {
        if (passDaDien !== cmd.pass_gmail) {
          passDaDien = cmd.pass_gmail;
          var nOk = nutTiep(win, doc);
          if (nOk) { clickReal(win, nOk); report("g-pass-submit", "lần " + lanDienPass); }
        }
        return;
      }
      if (lanDienPass >= 4) { report("g-pass-stuck", "gõ 4 lần mà ô mật khẩu vẫn trống"); return; }
      lanDienPass += 1;
      passDaDien = "";
      var vao = dienO(win, doc, oPass, cmd.pass_gmail);
      report("g-pass-filled", "lần " + lanDienPass + (vao ? " (chữ đã vào ô)" : " (ô VẪN TRỐNG)"));
      return;      // KHONG bam Tiep ngay — nhip sau xac minh o co chu roi moi bam
    }

    // Buoc 3: ma 2FA (TOTP tu khoa nguoi dung nhap).
    var oCode = oNhap(doc, "code");
    if (oCode) {
      var c = (getCommand() || cmd).code;
      if (!c) { return; }
      if ((oCode.value || "") === c) {
        if (codeDaDien !== c) {
          codeDaDien = c;
          var n3ok = nutTiep(win, doc);
          if (n3ok) { clickReal(win, n3ok); report("g-totp-submit", ""); }
        }
        return;
      }
      if (lanDienCode < 6) {
        lanDienCode += 1;
        codeDaDien = "";
        var okC = dienO(win, doc, oCode, c);
        report("g-totp-filled", "lần " + lanDienCode + (okC ? "" : " (ô VẪN TRỐNG)"));
      }
      return;
    }

    // Google doi xac minh kieu khac: thu chuyen sang Authenticator neu acc co khoa 2FA.
    if (cmd.code && !daThuCach) {
      var tc = nutThuCach(doc);
      if (tc) { daThuCach = true; clickReal(win, tc); report("g-try-another", ""); return; }
      var au = nutAuthenticator(doc);
      if (au) { clickReal(win, au); report("g-choose-authenticator", ""); return; }
    }
    if (gmCanNguoiThat(t)) { report("g-verify-phone", ""); return; }

    // Man "dong y / de sau" cuoi luong. CHI bam khi KHONG con o nhap nao — truoc day
    // bam bua lam Google tai lai man mat khau, xoa sach o (da mac that 05/10).
    if (oNhap(doc, "email") || oNhap(doc, "pass") || oNhap(doc, "code")) { return; }
    var dy = nutTheoChu(doc, /^(continue|tiếp tục|tiep tuc|not now|để sau|de sau|i agree|đồng ý|dong y|xong|done)$/i);
    if (dy.length) { clickReal(win, dy[dy.length - 1]); report("g-continue-clicked", ""); }
  }

  /** Chi lam viec tren trang WEB thuc: trang nen cua extension (moz-extension://),
   *  about:newtab... cung chay process-script va lam ngap nhat ky (da mac that 05/10). */
  function laTrangWeb(win) {
    try { return /^https?:/.test(String(win.location.href || "")); } catch (e) { return false; }
  }

  function onPage(win) {
    var cmd = getCommand();
    if (!cmd || cmd.action !== "gmail" || !laTrangWeb(win)) { return; }
    var doc = win.document, step = cmd.delay || 1500, waited = 0, cap = cmd.timeout || 240000;
    var nhip = 0;
    win.setTimeout(function tick() {
      try {
        nhip += 1;
        var url = win.location.href;
        var man = gmPhanLoai(url, txt(doc));
        // Kem so NHIP: nhat ky cua cha chi in dong KHAC nhau, co so nhip thi biet
        // agent con song hay da chet (da mu tit vi thieu cai nay khi chay that 05/10).
        report("seen", "#" + nhip + " " + man + " | " + url.slice(0, 70) + " | " + dump(doc));
        if (man === "g-in") { report("gmail-in", url.slice(0, 60)); return; }
        if (man === "g-wrong-pass") { report("g-wrong-pass", ""); return; }
        if (man === "g-rejected") { report("g-rejected", ""); return; }
        if (man === "g-disabled") { report("g-disabled", ""); return; }
        if (man === "google" || man === "g-challenge") {
          xuLyGoogle(win, doc, getCommand() || cmd);
        }
      } catch (e) { report("tick-error", String(e)); }
      waited += step;
      if (waited < cap) { win.setTimeout(tick, step); }
    }, 900);
  }

  function onFrame(win) {
    var cmd = getCommand();
    if (!cmd || cmd.action !== "gmail" || !laTrangWeb(win)) { return; }
    var doc = win.document, step = cmd.delay || 1500, waited = 0, cap = cmd.timeout || 240000;
    win.setTimeout(function tick() {
      try {
        var man = gmPhanLoai(win.location.href, txt(doc));
        if (man === "google" || man === "g-challenge") {
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
