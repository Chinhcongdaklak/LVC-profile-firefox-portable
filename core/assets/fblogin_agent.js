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
  var lanInvalid = 0;    // so lan gap "Invalid request" o trang 2FA -> dang nhap lai tu dau (toi da INVALID_TOI_DA)
  var dangXuLyInvalid = false;   // dang dieu huong ra URL login sau "Invalid request" -> chan lam lai
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
  function kieuDieuHuong(win) {
    var ra = [];
    try {
      var e = win.performance && win.performance.getEntriesByType
              ? win.performance.getEntriesByType("navigation")[0] : null;
      ra.push("nav=" + (e && e.type ? e.type : "?"));
    } catch (e1) { ra.push("nav=?"); }
    try { ra.push("ref=" + String(win.document.referrer || "").slice(0, 60)); } catch (e2) {}
    try { ra.push(win === win.top ? "top" : "frame"); } catch (e3) {}
    return ra.join(" ");
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

  /* ---- reCAPTCHA: TU TICH "Toi khong phai la nguoi may" ------------------------------
   * Nguoi dung chot 08/10: khuc dinh captcha thi tu tich o do; neu FB/Google doi XAC MINH
   * them (chon anh) thi DUNG YEN cho nguoi dung lam, roi cho chuyen sang o nhap ma 2FA.
   * O tick nam trong IFRAME cheo nguon google.com/recaptcha/api2/anchor -> process-script
   * chay duoc trong iframe do (onFrame), con cua so chinh thi khong voi toi. */
  var daTichCaptcha = false;
  //: MOI iframe xac minh (Arkose MatchKey / FunCaptcha / reCAPTCHA / hCaptcha). Agent TUYET DOI
  //: khong duoc dung vao: cac he nay phat hien script la truy cap DOM iframe cua no la DANH Rot
  //: -> Facebook day ve dang nhap (goc loi 08/10: Chrome sach qua duoc, profile tool khong qua
  //: vi agent poll vao iframe Arkose fbsbx.com/captcha/arkose moi 0.8-2 giay).
  function laKhungXacMinh(href) {
    var h = String(href || "");
    return /fbsbx\.com\/captcha\//.test(h)              // Arkose/reCAPTCHA FB nhung trong fbsbx
        || /arkoselabs\.com|funcaptcha|arkose/.test(h)
        || /(google\.com|recaptcha\.net)\/recaptcha\//.test(h)
        || /hcaptcha\.com/.test(h);
  }
  function laKhungAnchor(href) {
    return /recaptcha\/(api2|enterprise)\/anchor/.test(String(href || ""));
  }
  function laKhungThuThach(href) {
    return /recaptcha\/(api2|enterprise)\/bframe/.test(String(href || ""));
  }
  /** O tick cua reCAPTCHA v2/enterprise trong khung anchor. */
  function oTichCaptcha(doc) {
    try {
      var el = doc.getElementById("recaptcha-anchor")
            || doc.querySelector('[role="checkbox"].recaptcha-checkbox')
            || doc.querySelector(".recaptcha-checkbox");
      return el && vis(el) ? el : null;
    } catch (e) { return null; }
  }
  function daTich(el) {
    try {
      return el.getAttribute("aria-checked") === "true"
          || (el.className || "").indexOf("recaptcha-checkbox-checked") !== -1;
    } catch (e) { return false; }
  }
  /** Trong khung anchor: tich o mot lan roi theo doi ket qua. */
  function tichCaptcha(win, cmd) {
    var doc = win.document, doi = 0, daBam = false;
    (function tick() {
      var el = oTichCaptcha(doc);
      if (!el) { if (doi++ < 20) { win.setTimeout(tick, 700); } return; }
      if (daTich(el)) {
        daTichCaptcha = true;
        report("captcha-ticked", "đã tích 'Tôi không phải là người máy' — chờ Facebook chuyển sang ô nhập mã");
        return;
      }
      if (cmd && cmd.tu_tich_captcha === false) {
        report("captcha-cho-tay", "reCAPTCHA chưa tích — chế độ KHÔNG tự tích, chờ bạn tích tay");
        if (doi++ < 200) { win.setTimeout(tick, 1500); }
        return;
      }
      // Chi bam MOT lan: bam lai khi khung dang xac minh co the huy token -> FB day ve trang chu.
      if (!daBam) {
        daBam = true;
        report("captcha-tick", "tự tích ô 'Tôi không phải là người máy' (một lần, rồi chờ)");
        clickReal(win, el);
        try { el.click(); } catch (e) {}
      }
      if (doi++ < 60) { win.setTimeout(tick, 1500); }
    })();
  }

  function onFrame(win) {
    var hrefF = "";
    try { hrefF = String(win.location.href || ""); } catch (e) { return; }
    // IFRAME XAC MINH (Arkose/FunCaptcha/reCAPTCHA/hCaptcha): KHONG dung vao GI CA — khong
    // getCommand, khong doc DOM, khong poll, khong dispatch su kien. De nguyen cho he xac minh
    // + nguoi dung lam. Dung vao la bi danh rot (nguoi dung chot 08/10: "bi gan vao trinh duyet").
    if (laKhungXacMinh(hrefF)) { return; }
    // IFRAME khac: lo dien 2FA (o ma 2FA cua FB mot so phien nam trong iframe fbsbx KHONG phai captcha).
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

  /* ---- TRANG 2FA DANG CHUYEN HUONG -------------------------------------------------
   * Nguoi dung chot 08/10 (anh man hinh): o trang two_step_verification co reCAPTCHA
   * "Toi khong phai la nguoi may" DA TICH va trang dang quay vong de chuyen sang man
   * NHAP MA. Luc nay tool phai CHO IT NHAT 10 GIAY cho no chuyen huong, TUYET DOI khong
   * duoc quay lai (history.back) ve man dang nhap. */
  var CHO_CHUYEN_2FA = 10000;
  //: Con captcha (nguoi dung dang xac minh) thi cho toi da bao lau roi moi bo cuoc.
  var CHO_CAPTCHA_TOI_DA = 300000;
  var moc2FA = 0;                 // lan dau thay trang 2FA ma chua co o nhap ma
  var mocCaptcha = 0;             // lan dau thay captcha o trang 2FA
  //: DA TUNG vao trang 2FA trong phien nay. Sau do FB hay day nguoc ve trang chu/form
  //: dang nhap vai giay (nhat la sau khi tich reCAPTCHA) -> KHONG duoc dien lai form
  //: ngay, phai CHO no tu quay ve 2FA, khong thi lap vo tan (nguoi dung bao 08/10).
  var daThay2FA = false;
  var mocVeLogin = 0;             // luc bi day ve form login sau khi da thay 2FA
  var lanDienLai = 0;             // so lan da dien lai form login sau khi thay 2FA
  var soLanDayVe = 0;             // SO LAN bi day 2FA -> login (dem TICH LUY, khong reset)
  //: Lap nhieu lan kieu 2FA<->login = SAI MAT KHAU (FB qua kiem tra bao mat nhung pass sai nen
  //: khong vao duoc) hoac acc bi chan -> dung bao, dung cho mai (nguoi dung chot 08/10).
  var CHO_VE_2FA = 60000, DIEN_LAI_TOI_DA = 1, DAY_VE_TOI_DA = 3, INVALID_TOI_DA = 4;
  /** Hop thoai "Invalid request / We could not validate your request" o trang 2FA. THUAN. */
  function laYeuCauLoi(doc) {
    try {
      var t = low(doc.body ? doc.body.innerText : "");
      return /invalid request|could not validate your request|try starting the flow from beginning|yêu cầu không hợp lệ|không xác thực được yêu cầu|bắt đầu lại.*từ đầu/.test(t);
    } catch (e) { return false; }
  }
  function la2FA(href) {
    return String(href || "").indexOf("two_step_verification") !== -1
        || String(href || "").indexOf("two_factor") !== -1
        || String(href || "").indexOf("twofactor/reauth") !== -1;
  }
  //: Trang 2FA "Dang tien hanh kiem tra bao mat / Hệ thống sẽ tự động chuyển hướng" (Arkose
  //: chay ngam, khong co iframe captcha thay duoc) -> FB TU NOI se chuyen, phai cho LAU.
  function dangKiemTraBaoMat(doc) {
    try {
      var t = low(doc.body ? doc.body.innerText : "");
      return /đang tiến hành kiểm tra bảo mật|tự động chuyển hướng|kiểm tra bảo mật|security check|checking your|verifying your login|xác minh lần đăng nhập/.test(t);
    } catch (e) { return false; }
  }
  /** Trang 2FA chua san sang (chua co o nhap ma) -> con duoc cho bao lau nua, 0 = het cho. */
  function conCho2FA(doc) {
    if (codeInput(doc)) { moc2FA = 0; mocCaptcha = 0; return 0; }
    // Dang kiem tra bao mat / co captcha / dang xac minh -> CHO TIEP, dong ho dat lai moi nhip,
    // nhung van co TRAN (CHO_CAPTCHA_TOI_DA) de khong treo mai neu FB khong bao gio chuyen.
    if (dangKiemTraBaoMat(doc) || coCaptcha(doc)) {
      if (!mocCaptcha) { mocCaptcha = Date.now(); }
      if (Date.now() - mocCaptcha >= CHO_CAPTCHA_TOI_DA) { return 0; }
      moc2FA = Date.now();
      return CHO_CHUYEN_2FA;
    }
    mocCaptcha = 0;
    if (!moc2FA) { moc2FA = Date.now(); }
    return Math.max(0, CHO_CHUYEN_2FA - (Date.now() - moc2FA));
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

  // ---- LAY TOKEN (business_locations) -----------------------------------------------------
  // Nguoi dung chi 07/10: vao business.facebook.com/business_locations/ (nhap 2FA neu bi hoi) roi
  // doc dong EAAG. Dung LAI bo may 2FA cua agent login (codeInput/contBtn/twofaTick), them quet EAAG.
  var tokenDaBao = false;
  function quetToken(doc) {
    var H = "";
    try { H = doc.documentElement.innerHTML || ""; } catch (e) { return ""; }
    var g = H.match(/EAAG[A-Za-z0-9]{20,}/g);
    if (g && g.length) { return g.sort(function (a, b) { return b.length - a.length; })[0]; }
    var e2 = H.match(/EAA[A-Za-z0-9]{20,}/g);
    return e2 && e2.length ? e2.sort(function (a, b) { return b.length - a.length; })[0] : "";
  }
  function layTokenPage(win, cmd) {
    var doc = win.document, step = cmd.delay || 2500, waited = 0, cap = cmd.formTimeout || 90000;
    report("seen", "[token] " + win.location.href.slice(0, 80) + " | " + dump(doc));
    win.setTimeout(function tick() {
      if (tokenDaBao) { return; }
      var href = low(win.location.href);
      // 1) Trang 2FA reauth / two_step -> dien ma (cha lam moi cmd.code moi 5s).
      if (href.indexOf("twofactor/reauth") !== -1 || href.indexOf("two_step") !== -1
          || codeInput(doc)) {
        twofaTick(win, doc, cmd);
      }
      // 2) Quet EAAG (tren business_locations hoac trang business bat ky).
      var tok = quetToken(doc);
      if (tok) {
        tokenDaBao = true;
        report("token-found", tok);         // cha doc, che bot khi hien/log
        return;
      }
      // 3) Chua ra token + chua o trang 2FA + dang o login -> bao de cha biet.
      if (href.indexOf("/login") !== -1 && !codeInput(doc)) {
        report("token-login", win.location.href.slice(0, 80));
      }
      waited += step;
      if (waited < cap) { win.setTimeout(tick, step); }
      else { report("token-timeout", "hết giờ chưa thấy EAAG — " + win.location.href.slice(0, 70)); }
    }, 1500);
  }

  var daVeTrangChu = false;
  /** login.php mà trang chỉ có chữ "Not Found" (Facebook trả cho phiên đã đăng nhập). THUẦN. */
  function laNotFoundLogin(href, doc) {
    if (String(href || "").indexOf("facebook.com/login") === -1) { return false; }
    var t = "";
    try { t = String((doc.body && doc.body.innerText) || "").trim().toLowerCase(); } catch (e) { t = ""; }
    return t === "not found" || t === "không tìm thấy";
  }

  function onPage(win) {
    var cmd = getCommand();
    if (cmd && cmd.action === "gettoken") { return layTokenPage(win, cmd); }
    if (!cmd || cmd.action !== "weblogin") { return; }
    var doc = win.document, href = low(win.location.href);

    if (la2FA(href)) { daThay2FA = true; mocVeLogin = 0; }

    // (0a) HOP THOAI "Invalid request" o trang 2FA (nguoi dung bao 22/10): Facebook bao
    //      "We could not validate your request, please try starting the flow from beginning".
    //      -> THOAT RA, DANG NHAP LAI TU DAU (mo lai URL login sach, chay het email+pass+2FA).
    //      Lam lai toi da INVALID_TOI_DA lan; qua so do van loi -> bao "invalid-fail".
    //      DAT NGAY DAU (truoc moi guard "cho 2FA") de khong ngoi cho vo ich khi dialog dang che o ma.
    if (laYeuCauLoi(doc) && (la2FA(href) || href.indexOf("two_step") !== -1
        || href.indexOf("/login") !== -1 || href.indexOf("/checkpoint") !== -1
        || href.indexOf("authentication") !== -1)) {
      if (dangXuLyInvalid) { return; }      // dang dieu huong -> cho document moi tai, khong lam lai
      lanInvalid++;
      if (lanInvalid > INVALID_TOI_DA) {
        report("invalid-fail", "Invalid request " + INVALID_TOI_DA + " lần vẫn lỗi → tắt trình duyệt, báo lỗi đăng nhập");
        return;
      }
      dangXuLyInvalid = true;
      // Bam "OK" dong hop thoai (neu co) cho giong nguoi that, roi dieu huong ra URL login.
      try {
        var okBtn = nutTheoChu(doc, /^(ok|đồng ý|dong y|close|đóng|dong|thử lại|thu lai|try again)$/i);
        if (okBtn.length) { clickReal(win, okBtn[0]); try { okBtn[0].click(); } catch (e2) {} }
      } catch (e) {}
      // Reset co phien -> lan dang nhap lai duoc coi la LUOT MOI, khong dinh bo dem day-ve cu.
      daThay2FA = false; mocVeLogin = 0; soLanDayVe = 0; lanDienLai = 0; lanTiepTuc = 0;
      report("invalid-restart", "lần " + lanInvalid + "/" + INVALID_TOI_DA + ": thoát ra, đăng nhập lại từ đầu");
      var urlVao = cmd.url_login || "https://www.facebook.com/login.php";
      win.setTimeout(function () {
        try { win.location.href = urlVao; } catch (e3) { try { win.location.replace(urlVao); } catch (e4) {} }
        win.setTimeout(function () { dangXuLyInvalid = false; }, 4000);
      }, 600);
      return;
    }

    // (0) Acc DA DANG NHAP SAN: Facebook tra trang trang "Not Found" cho login.php -> khong co
    //     form nao, truoc day ngoi cho het gio roi bao khong_ro (nguoi dung bao 12/10). Sang
    //     trang chu MOT LAN de probe thay phien song (cha tu ket luan "vao").
    if (laNotFoundLogin(href, doc)) {
      if (!daVeTrangChu) {
        daVeTrangChu = true;
        report("da-dang-nhap-san", "login.php báo 'Not Found' (acc đã đăng nhập sẵn) — sang facebook.com kiểm tra");
        try { win.location.href = "https://www.facebook.com/"; } catch (e) {}
      }
      return;
    }

    // (1) Dang o trang 2FA (two_step/two_factor) MA CHUA co o nhap ma -> man "Đang tiến hành
    //     kiểm tra bảo mật", dang quay vong qua reCAPTCHA/Arkose. CHO, khong dieu huong,
    //     khong bam gi, cho toi khi o nhap ma hien ra (nguoi dung chot 08/10).
    if (la2FA(href) && !codeInput(doc)) {
      var con2 = conCho2FA(doc);
      if (con2 > 0) {
        report("2fa-cho-chuyen", (coCaptcha(doc) ? "trang 2FA có reCAPTCHA/Arkose — chờ xác minh"
               : "trang 2FA 'Đang tiến hành kiểm tra bảo mật' — chờ nó tự chuyển sang ô nhập mã")
               + " (còn " + Math.ceil(con2 / 1000) + "s), KHÔNG quay lại màn đăng nhập");
        win.setTimeout(function () { onPage(win); }, 1500);
        return;                         // CHAN moi xu ly khac: khong lap tick, khong dien form
      }
    }

    // (2) DA TUNG thay trang 2FA ma GIO lai o login/home -> Facebook vua day nguoc ve (sau khi
    //     "kiểm tra bảo mật" chua xong). TUYET DOI khong dien lai form ngay: dien = bam Dang
    //     nhap lai = FB lai bat kiem tra bao mat -> quay vong vo tan (dung loi nguoi dung bao).
    //     CHO im lang cho FB tu dua tro lai 2FA; het CHO_VE_2FA moi dien lai, toi da 1 lan.
    //     Dat NGAY DAU onPage de khong co tick loop cu nao con song lot qua xuong dien form.
    if (daThay2FA && !codeInput(doc) && !la2FA(href)) {
      var coForm = q(doc, "input[name=pass]") || q(doc, "input[name=email]")
                || /facebook\.com\/?($|\?|login)/.test(href);
      if (coForm) {
        if (!mocVeLogin) { mocVeLogin = Date.now(); soLanDayVe += 1; }
        if (soLanDayVe > DAY_VE_TOI_DA) {
          report("lap-login", "bị đẩy từ 2FA về màn đăng nhập " + soLanDayVe + " lần — RẤT CÓ THỂ "
                 + "SAI MẬT KHẨU (Facebook qua kiểm tra bảo mật nhưng mật khẩu không đúng nên không "
                 + "vào được), hoặc acc bị chặn. Kiểm tra lại mật khẩu, hoặc đăng nhập TAY một lần.");
          return;
        }
        var choTiep0 = CHO_VE_2FA - (Date.now() - mocVeLogin);
        if (choTiep0 > 0) {
          report("cho-ve-2fa", "vừa ở trang 2FA, Facebook đẩy về màn đăng nhập — CHỜ "
                 + Math.ceil(choTiep0 / 1000) + "s cho nó tự quay lại ô nhập mã, KHÔNG đăng nhập lại");
          win.setTimeout(function () { onPage(win); }, 2000);
          return;                       // CHAN tat ca: khong lap tick, khong dien form
        }
        if (lanDienLai >= DIEN_LAI_TOI_DA) {
          report("lap-login", "đã chờ " + Math.round(CHO_VE_2FA / 1000) + "s + đăng nhập lại "
                 + lanDienLai + " lần mà Facebook vẫn không qua kiểm tra bảo mật — DỪNG "
                 + "(acc bị chặn ở bước xác minh Arkose, hãy đăng nhập TAY một lần)");
          return;
        }
        lanDienLai += 1; mocVeLogin = 0;
        report("dien-lai-login", "lần " + lanDienLai + "/" + DIEN_LAI_TOI_DA
               + " — chờ mãi không tự quay lại, thử đăng nhập lại một lần");
        // roi THOI: de cac tick ben duoi dien form mot lan.
      }
    }
    // Trang khoi phuc (quen mat khau / identify / recover) -> xu ly rieng.
    if (href.indexOf("/login/identify") !== -1 || href.indexOf("/recover") !== -1
        || href.indexOf("/recovery") !== -1) {
      return xuLyKhoiPhuc(win, cmd);
    }
    // ("Invalid request" o trang 2FA xu ly NGAY DAU onPage, muc (0a) — thoat ra, dang nhap lai tu dau.)

    var step = cmd.delay || 2000, waited = 0, cap = cmd.formTimeout || 40000;

    // Chan doan: bao trang vua tai (url + cau truc) — cha ghi lai moi thay doi.
    // Kem KIEU DIEU HUONG (navigate / back_forward / reload) + trang truoc do, de biet
    // "bi back" la ai lam: agent, nguoi dung, hay FB tu chuyen (08/10).
    report("seen", win.location.href.slice(0, 70) + " | " + dump(doc) + " | " + kieuDieuHuong(win));
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
      // (Viec "da thay 2FA ma gio o login -> CHO" da chuyen len DAU onPage de chan moi
      //  tick loop cu lot qua. O day khong lam gi nua.)
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
        // Iframe xac minh (captcha): KHONG dang ky gi, khong cham vao -> he xac minh thay
        // iframe SACH nhu trinh duyet thuong (goc loi 08/10).
        if (!top) {
          var hf = "";
          try { hf = String(win.location.href || ""); } catch (e0) {}
          if (laKhungXacMinh(hf)) { return; }
        }
        win.addEventListener("load", function onload() {
          win.removeEventListener("load", onload);
          // Khi load xong co the da dieu huong sang iframe captcha -> kiem lai.
          try { if (win.top !== win && laKhungXacMinh(String(win.location.href || ""))) { return; } } catch (e1) {}
          if (top) { onPage(win); } else { onFrame(win); }
        }, { once: true });
      } catch (e) {}
    },
  };
  Services.obs.addObserver(observer, "content-document-global-created");
}
