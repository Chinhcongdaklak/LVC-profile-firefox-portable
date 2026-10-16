/* Process script: DANG BAI len X.com (tuong acc, composer o /home).
 *
 * Cung khuon xlogin_agent.js: chay trong tien trinh noi dung, thao tac bang
 * su kien "nguoi that" (setHandlingUserInput), trinh duyet mo BINH THUONG.
 *
 * Bridge RIENG:
 *   sendSyncMessage("qlfpxp:cmd")      -> cha doc <profile>/qlfp-xpost.json
 *   sendAsyncMessage("qlfpxp:report")  -> cha ghi <profile>/qlfp-xpost-result.json
 *   sendAsyncMessage("qlfpxp:needfile", {path}) -> cha doc file media roi
 *   broadcast "qlfpxp:file" {ok, name, bytes} ve (tien trinh noi dung bi chan doc dia).
 *
 * Lenh: { action:"xpost", text, path, name, mime, delay, timeout }
 *   text: noi dung bai (co the rong khi chi dang media)
 *   path: duong dan media tren dia ("" = bai chi chu); name/mime kem theo.
 *
 * Trang thai bao ve cha (moi cai bao 1 lan):
 *   logged-out | x-locked | no-composer | text-filled | file-error |
 *   media-attached | post-clicked | post-done | post-error | upload-stuck
 * Cha quyet dinh thanh/bai; "seen" chi la chan doan de chinh selector khi X doi giao dien.
 */
"use strict";

/* ---- phan THUAN (test bang node): nhan biet man dang o dau -------------------------- */
/** xpPhanLoai(url, text) -> "x-home" | "x-login" | "x-locked" | "x" | "". THUAN. */
function xpPhanLoai(url, text) {
  url = (url || "").toLowerCase();
  text = text || "";
  if (/x\.com|twitter\.com/.test(url)) {
    // /i/jf/onboarding: X bat acc XAC MINH/onboarding lai (do that 12/10 acc hoheeh0719) -> khong co
    // o soan; truoc day bao chung chung "no-composer". Xep vao x-locked (phai mo profile lam tay).
    if (/account\/access|\/suspended|\/i\/jf\/onboarding|your account is (locked|suspended)|tài khoản.*(khoá|khóa|tạm khoá)/i.test(url + " " + text)) { return "x-locked"; }
    if (/i\/flow\/login|\/i\/flow\/signup|\/login(\b|$|\?)/.test(url)) { return "x-login"; }
    if (/\/home(\b|$|\?)/.test(url)) { return "x-home"; }
    return "x";
  }
  return "";
}
/** Bai da gui chua, doan tu chu tren man (toast). THUAN. */
var XP_SENT_RE = /your post was sent|đã gửi bài đăng|da gui bai dang|bài đăng của bạn đã được gửi/i;
function xpDaGui(text) { return XP_SENT_RE.test(text || ""); }
/** Toast X bao DA LEN LICH (dat lich thanh cong). THUAN. */
var XP_SCHED_RE = /your post was scheduled|post scheduled|đã được lên lịch|đã lên lịch|lên lịch thành công|will be sent on/i;
function xpDaLenLich(text) { return XP_SCHED_RE.test(text || ""); }
/** X gioi han dang trong ngay (banner hong tren dong thoi gian + toast xanh sau khi bam Post).
 *  Da gap that 29/09: "You've hit the daily post limit. Subscribe to Premium for higher limits." */
var XP_LIMIT_RE = /hit the daily (post|tweet) limit|daily (post|tweet) limit|giới hạn (bài )?đăng (hằng|hàng) ngày|đã đạt giới hạn đăng/i;
function xpGioiHan(text) { return XP_LIMIT_RE.test(text || ""); }
/** Cho video tai len TOI DA 15 phut (nguoi dung chot 29/09) roi moi bo, dong trinh duyet. */
var CHO_UPLOAD_TOI_DA = 30 * 60 * 1000;   // nguoi dung chot 06/10: cho DU 30 phut moi bo cuoc
                                         // (video nang + mang yeu: 120 MB co the mat ca nua tieng)
/** "…: Uploading (20%)" / "Uploaded (100%)" / "Processing (45%)" (EN/VI) -> "Uploading 20%". THUAN. */
function phanTramUpload(text) {
  var m = /(uploading|uploaded|processing|đang tải lên|đã tải lên|đang xử lý)[^%\n]{0,20}?(\d{1,3})\s*%/i.exec(text || "");
  return m ? (m[1].charAt(0).toUpperCase() + m[1].slice(1).toLowerCase() + " " + m[2] + "%") : "";
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { phanLoai: xpPhanLoai, daGui: xpDaGui, phanTram: phanTramUpload, gioiHan: xpGioiHan,
                     daLenLich: xpDaLenLich, CHO_UPLOAD_TOI_DA: CHO_UPLOAD_TOI_DA };
}

if (typeof sendAsyncMessage === "function") {

  var lines = [];
  var DA_CHAY_LENH = "";                 // lenh dang da chay trong TIEN TRINH nay
  // Ma rieng cua BAN agent nay (moi tien trinh noi dung mot ban) -> xin giay phep chay o cha.
  var TOK = "p" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  /** Chi MOT ban agent (trong moi tien trinh noi dung) duoc chay mot lenh dang. */
  function xinQuyen() {
    try {
      var a = sendSyncMessage("qlfpxp:claim", { tok: TOK });
      var kq = a && a.length ? a[0] : null;
      return !kq || kq.ok !== false;       // cha cu (chua co claim) -> cho chay nhu truoc
    } catch (e) { return true; }
  }
  function report(state, detail) {
    lines.push(state + (detail ? ": " + detail : ""));
    try {
      sendAsyncMessage("qlfpxp:report", { state: state, detail: detail || "", log: lines.slice(-30), tok: TOK });
    } catch (e) {}
  }
  function getCommand() {
    try {
      var a = sendSyncMessage("qlfpxp:cmd");
      var raw = a && a.length ? a[0] : "";
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function vis(el) {
    try { var b = el.getBoundingClientRect(); return b.width > 12 && b.height > 8 && el.offsetParent !== null; }
    catch (e) { return false; }
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
      // DUNG MOT su kien click: click GOC (React cua X chi chac an voi .click() that). Truoc day
      // ban THEM mot click gia lap TRUOC no = HAI click -> nut Post dang HAI bai giong het
      // (nguoi dung bao 12/10: "co video thi bi trung co video thi khong").
      try { el.click(); } catch (e) {}
      return true;
    } catch (e) { report("click-error", String(e)); return false; }
    finally { if (handle) { try { handle.destruct(); } catch (e) {} } }
  }
  function q(doc, sel) { try { return doc.querySelector(sel); } catch (e) { return null; } }
  function txt(doc) { try { return doc.body ? doc.body.innerText : ""; } catch (e) { return ""; } }

  // ---- cac manh giao dien cua composer x.com (data-testid kha on dinh nhieu nam) ------
  function oSoan(doc) {
    // O soan bai dau trang /home. Composer la contenteditable (DraftJS).
    var el = q(doc, '[data-testid="tweetTextarea_0"]');
    return el && vis(el) ? el : null;
  }
  function nutDang(doc) {
    // UU TIEN tweetButton (composer TOAN TRANG /compose/post hoac modal) roi moi den
    // tweetButtonInline (composer tren /home). LOI THAT 05/10: tren /compose/post CA HAI cung ton tai;
    // ban cu lay Inline truoc -> do nut cua o soan trang chu (luon RONG -> disabled vinh vien)
    // -> tool cho mai khong bam duoc. Va neu nut dau KHONG hien thi ban cu tra null luon, khong thu nut kia.
    var ds = [q(doc, '[data-testid="tweetButton"]'), q(doc, '[data-testid="tweetButtonInline"]')];
    for (var i = 0; i < ds.length; i++) {
      if (ds[i] && vis(ds[i])) { return ds[i]; }
    }
    return null;
  }
  var CHU_LEN_LICH = /schedule|lên lịch|len lich|hẹn giờ|hen gio/i;
  function laNutLenLich(doc) {
    // Sau khi Confirm, X doi chu nut "Post" -> "Schedule". Chua doi = lich CHUA AP.
    var el = nutDang(doc);
    if (!el) { return false; }
    return CHU_LEN_LICH.test((el.innerText || "").replace(/\s+/g, " ").trim());
  }
  function nutDangBam(doc) {
    var el = nutDang(doc);
    if (!el) { return null; }
    if (el.disabled || el.getAttribute("aria-disabled") === "true") { return null; }
    return el;
  }
  function oChonFile(doc) {
    return q(doc, 'input[data-testid="fileInput"]') || q(doc, 'input[type="file"][accept]');
  }
  function coMediaDinhKem(doc) {
    return !!q(doc, '[data-testid="attachments"]');
  }
  // Chu cua cac thong bao X hien (toast / alert / dialog loi) -- de biet vi sao X tu choi media.
  function thongBaoTrang(doc) {
    var ds = Array.prototype.slice.call(doc.querySelectorAll('[data-testid="toast"],[role="alert"],[role="alertdialog"],[role="dialog"] [role="heading"]'));
    return ds.map(function (e) { return (e.innerText || "").replace(/\s+/g, " ").trim(); })
      .filter(function (t) { return t; }).join(" / ").slice(0, 300);
  }
  function dump(doc) {
    try {
      var ids = ["tweetTextarea_0", "tweetButtonInline", "tweetButton", "fileInput", "attachments", "toast"];
      var ra = ids.map(function (t) {
        var e = q(doc, '[data-testid="' + t + '"]') || (t === "fileInput" ? oChonFile(doc) : null);
        return t + "=" + (e ? (vis(e) ? "1" : "an") : "0");
      });
      return ra.join(" ");
    } catch (e) { return "(dump loi)"; }
  }

  // ---- dien chu vao composer (contenteditable, khong phai input thuong) ---------------
  // So lan caption xuat hien trong o soan (so theo doan dau, bo khac biet khoang trang/xuong dong).
  function demLap(composer, text) {
    var gon = function (x) { return (x || "").replace(/\s+/g, " ").trim(); };
    var noi = gon(composer.innerText || composer.textContent || ""), mau = gon(text).slice(0, 24);
    if (!mau) { return 0; }
    var dem = 0, vt = noi.indexOf(mau);
    while (vt >= 0) { dem++; vt = noi.indexOf(mau, vt + mau.length); }
    return dem;
  }
  function xoaOSoan(win, doc, composer) {
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try {
      composer.focus();
      doc.execCommand("selectAll", false, null);
      doc.execCommand("delete", false, null);
    } catch (e) { report("seen", "xoa o soan loi: " + e); }
    finally { if (handle) { try { handle.destruct(); } catch (e) {} } }
  }
  function dienChu(win, doc, composer, text) {
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try {
      clickReal(win, composer);
      composer.focus();
      // DraftJS nghe beforeinput/textInput -> execCommand("insertText") la duong
      // an toan nhat trong trang that (da dung o fbchat_agent).
      var ok = doc.execCommand("insertText", false, text);
      if (!ok) {
        // Duong lui: su kien paste gia co du lieu text/plain.
        var dt = new win.DataTransfer();
        dt.setData("text/plain", text);
        var ev = new win.ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: dt });
        composer.dispatchEvent(ev);
      }
      return true;
    } catch (e) { report("text-error", String(e)); return false; }
    finally { if (handle) { try { handle.destruct(); } catch (e) {} } }
  }

  // ---- dinh kem media: xin file tu cha roi gan vao input[type=file] -------------------
  var fileDangCho = null;   // {path, resolve} dang doi cha tra bytes
  try {
    addMessageListener("qlfpxp:file", function (msg) {
      var d = msg.data || {};
      if (fileDangCho) { var f = fileDangCho; fileDangCho = null; f(d); }
    });
  } catch (e) {}

  function xinFile(path, notify) {
    fileDangCho = notify;
    try { sendAsyncMessage("qlfpxp:needfile", { path: path }); }
    catch (e) { fileDangCho = null; notify({ ok: false, error: String(e) }); }
  }

  function ganFile(win, doc, data, cmd) {
    try {
      var mime = cmd.mime || "application/octet-stream";
      var file = new win.File([data.bytes], data.name || cmd.name || "media", { type: mime });
      var dt = new win.DataTransfer();
      dt.items.add(file);
      var input = oChonFile(doc);
      if (input) {
        try {
          input.files = dt.files;
          input.dispatchEvent(new win.Event("change", { bubbles: true }));
          return true;
        } catch (e) { report("seen", "input.files loi: " + String(e)); }
      }
      // Duong lui: tha file vao o soan (X nhan drop tren composer).
      var composer = oSoan(doc);
      if (!composer) { return false; }
      var over = new win.DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: dt });
      var drop = new win.DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt });
      composer.dispatchEvent(over);
      composer.dispatchEvent(drop);
      return true;
    } catch (e) { report("file-error", String(e)); return false; }
  }

  // ---- dat lich X: nut lich -> hop chon ngay/gio (cac <select>) -> Confirm -> nut Schedule -----
  var THANG_EN = ["january", "february", "march", "april", "may", "june", "july",
                  "august", "september", "october", "november", "december"];
  function nutTheoChu(doc, re) {
    var ds = Array.prototype.slice.call(doc.querySelectorAll('[role="button"],button'));
    for (var i = 0; i < ds.length; i++) {
      var t = (ds[i].innerText || "").replace(/\s+/g, " ").trim();
      if (t && re.test(t) && vis(ds[i])) { return ds[i]; }
    }
    return null;
  }
  function nutMoLich(doc) {
    // Nut lich trong thanh cong cu composer (icon dong ho). Uu tien testid, fallback aria-label/title
    // (EN "Schedule post" / VI "Lên lịch" / "Hẹn giờ") phong khi acc khac ngon ngu.
    var el = q(doc, '[data-testid="scheduleOption"]');
    if (el && vis(el)) { return el; }
    var ds = Array.prototype.slice.call(doc.querySelectorAll('[role="button"],button,[aria-label]'));
    for (var i = 0; i < ds.length; i++) {
      var lb = ((ds[i].getAttribute("aria-label") || ds[i].getAttribute("title") || "") + "").toLowerCase();
      if (/schedule|lên lịch|len lich|hẹn giờ|hen gio/.test(lb) && vis(ds[i])) { return ds[i]; }
    }
    return null;
  }
  function dumpToolbar(doc) {
    // Liet ke nut trong thanh cong cu composer de biet acc nay hien gi (testid + aria-label).
    var tb = q(doc, '[data-testid="toolBar"]');
    var goc = tb || doc;
    var ds = Array.prototype.slice.call(goc.querySelectorAll('[data-testid],[aria-label]'));
    var ra = [];
    for (var i = 0; i < ds.length && ra.length < 24; i++) {
      var e = ds[i];
      var tid = e.getAttribute("data-testid") || "";
      var al = (e.getAttribute("aria-label") || "").slice(0, 20);
      if (tid || al) { ra.push((tid ? tid : "") + (al ? "(" + al + ")" : "") + (vis(e) ? "" : "·an")); }
    }
    return (tb ? "toolBar: " : "noToolBar: ") + ra.join(" ");
  }
  function nutXacNhanLich(doc) {
    return q(doc, '[data-testid="scheduledConfirmationPrimaryAction"]')
        || nutTheoChu(doc, /^(confirm|xác nhận|xac nhan|cập nhật|cap nhat|update|done|xong)$/i);
  }
  function dumpNutLich(doc) {
    // Liet ke nut trong hop lich (testid + chu) de biet dau la Confirm that.
    var hop = q(doc, '[role="dialog"]') || q(doc, '[aria-modal="true"]') || doc;
    var ds = Array.prototype.slice.call(hop.querySelectorAll('[role="button"],button'));
    var ra = [];
    for (var i = 0; i < ds.length && ra.length < 14; i++) {
      var e = ds[i];
      var t = (e.innerText || "").replace(/\s+/g, " ").trim().slice(0, 18);
      var tid = e.getAttribute("data-testid") || "";
      var al = (e.getAttribute("aria-label") || "").slice(0, 18);
      if (t || tid || al) {
        ra.push((tid ? tid + ":" : "") + (t || al) + (vis(e) ? "" : "·an"));
      }
    }
    return (q(doc, '[role="dialog"]') ? "dlg[" : "nodlg[") + ra.join(" | ") + "]";
  }
  function selectsLich(doc) {
    // Hop lich X dung cac <select> that (Month/Day/Year/Hour/Minute/AM-PM).
    return Array.prototype.slice.call(doc.querySelectorAll('select'));
  }
  function moTaSelects(sels) {
    return sels.map(function (s) {
      var opts = Array.prototype.slice.call(s.options || []);
      var lb = s.getAttribute("aria-label") || s.getAttribute("id") || s.name || "?";
      var dau = opts[0] ? (opts[0].value + "/" + (opts[0].text || "").slice(0, 6)) : "";
      var cuoi = opts[opts.length - 1] ? opts[opts.length - 1].value : "";
      return lb.slice(0, 16) + "[" + opts.length + ":" + dau + ".." + cuoi + "]";
    }).join(" ");
  }
  function dumpLich(doc) {
    var sels = selectsLich(doc);
    return "selects=" + sels.length + " | " + moTaSelects(sels)
      + " | confirm=" + (nutXacNhanLich(doc) ? "1" : "0");
  }
  function datSelect(win, sel, val) {
    try {
      var set = Object.getOwnPropertyDescriptor(win.HTMLSelectElement.prototype, "value").set;
      set.call(sel, String(val));
    } catch (e) { try { sel.value = String(val); } catch (e2) {} }
    try { sel.dispatchEvent(new win.Event("input", { bubbles: true })); } catch (e) {}
    try { sel.dispatchEvent(new win.Event("change", { bubbles: true })); } catch (e) {}
  }
  function chonSo(win, sel, so) {
    var opts = Array.prototype.slice.call(sel.options || []);
    for (var i = 0; i < opts.length; i++) {
      var o = opts[i];
      if (String(o.value) === String(so) || parseInt(o.value, 10) === so
          || (o.text || "").trim() === String(so) || parseInt(o.text, 10) === so) {
        datSelect(win, sel, o.value); return o.value;
      }
    }
    return "";
  }
  function chonChu(win, sel, re) {
    var opts = Array.prototype.slice.call(sel.options || []);
    for (var i = 0; i < opts.length; i++) {
      if (re.test(opts[i].value) || re.test((opts[i].text || "").trim())) {
        datSelect(win, sel, opts[i].value); return opts[i].value;
      }
    }
    return "";
  }
  function loaiSelect(sel) {
    // X dung <select id="SELECTOR_1..6"> (khong nhan Month/Day/...). Moi select co 1 option TRONG
    // o dau -> so option lech +1; phan loai theo GIA TRI LON NHAT (bo qua option trong):
    //   co ten thang -> Month; 2 option (am/pm) -> AM/PM; max>=2000 -> Year; max 1..12 -> Hour
    //   (Month da loc truoc bang ten thang); max 13..31 -> Day; max 32..59 -> Minute.
    // DA DO THAT (05/10, ReginaldVevadh): Day 32 option -> truot "n<=31" cu; Hour n=13 -> lot nham
    // nhanh "ngay" cu. Nen KHONG dua vao SO LUONG option nua.
    var lb = ((sel.getAttribute("aria-label") || sel.getAttribute("id") || sel.name || "") + "").toLowerCase();
    var opts = Array.prototype.slice.call(sel.options || []);
    var maxv = 0, coTenThang = false, coAmPm = false;
    for (var k = 0; k < opts.length; k++) {
      var vv = parseInt(opts[k].value, 10); if (!isNaN(vv) && vv > maxv) { maxv = vv; }
      if (/jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|thá/i.test(opts[k].text || "")) { coTenThang = true; }
      var tv = ((opts[k].value || "") + " " + (opts[k].text || "")).toLowerCase();
      if (/\bam\b|\bpm\b|a\.m|p\.m/.test(tv)) { coAmPm = true; }
    }
    if (/month|tháng/.test(lb)) { return "thang"; }
    if (/\bday\b|ngày/.test(lb)) { return "ngay"; }
    if (/year|năm/.test(lb)) { return "nam"; }
    if (/hour|giờ/.test(lb)) { return "gio"; }
    if (/min|phút/.test(lb)) { return "phut"; }
    if (/am\s*\/?\s*pm|meridi/.test(lb)) { return "buoi"; }
    if (coTenThang) { return "thang"; }
    if (coAmPm || opts.length === 2) { return "buoi"; }
    if (maxv >= 2000) { return "nam"; }
    if (maxv >= 32) { return "phut"; }
    if (maxv >= 13) { return "ngay"; }
    if (maxv >= 1) { return "gio"; }
    return "";
  }
  function docMacDinh(sels) {
    // Gia tri X DIEN SAN (truoc khi tool ghi de) = "bay gio" theo MUI GIO cua tai khoan X.
    var ra = [];
    for (var i = 0; i < sels.length; i++) {
      var s0 = sels[i], k = loaiSelect(s0);
      var o0 = s0.options && s0.selectedIndex >= 0 ? s0.options[s0.selectedIndex] : null;
      ra.push((k || "?") + "=" + (o0 ? ((o0.text || o0.value || "").trim().slice(0, 10)) : ""));
    }
    return ra.join(" ");
  }
  function dienLich(win, doc, sels, lich) {
    var ra = [];
    for (var i = 0; i < sels.length; i++) {
      var s = sels[i], kind = loaiSelect(s), got = "";
      if (kind === "thang") {
        got = chonChu(win, s, new RegExp("^\\s*" + THANG_EN[lich.thang - 1], "i"));
        if (!got && s.options && s.options.length >= lich.thang) {   // fallback: value 0-based -> theo vi tri
          got = s.options[lich.thang - 1].value; datSelect(win, s, got);
        }
      } else if (kind === "ngay") { got = chonSo(win, s, lich.ngay); }
      else if (kind === "nam") { got = chonSo(win, s, lich.nam); }
      else if (kind === "gio") { got = chonSo(win, s, lich.gio12); }
      else if (kind === "phut") { got = chonSo(win, s, lich.phut); }
      else if (kind === "buoi") { got = chonChu(win, s, new RegExp("^" + lich.buoi + "$", "i")); }
      ra.push((kind || "?") + "=" + (got || "?"));
    }
    return ra.join(" ");
  }

  // ---- luong chinh ---------------------------------------------------------------------
  function onPage(win) {
    var cmd = getCommand();
    if (!cmd || cmd.action !== "xpost") { return; }
    // Chi chay tren x.com: truoc do tool mo trang KIEM VPN (ipinfo) -- o do khong co
    // o soan, de chay thi sau 30s bao nham "no-composer".
    if (!/x\.com|twitter\.com/i.test(win.location.href)) { return; }
    // MOT LENH DANG CHI CHAY MOT LAN: (a) trong tien trinh nay — trang x.com tai lai khong lam lai
    // tu dau; (b) giua cac tien trinh — Firefox mo them tien trinh noi dung cho x.com, ban agent
    // thu hai gan video + bam Post lan nua = BAI TRUNG. Cha giu giay phep (qlfpxp:claim).
    var khoaLenh = JSON.stringify(cmd);
    if (DA_CHAY_LENH === khoaLenh) { return; }
    if (!xinQuyen()) { return; }
    DA_CHAY_LENH = khoaLenh;
    // Trang nay bi THAY (chuyen huong / tai lai) TRUOC khi bam Post -> nha quyen cho trang moi
    // lam tiep. Da bam Post roi thi GIU (cha cam moi ban khac chay lai lenh nay -> khong dang trung).
    var daBamPost = false;
    try {
      win.addEventListener("pagehide", function () {
        if (daBamPost) { return; }
        DA_CHAY_LENH = "";
        try { sendAsyncMessage("qlfpxp:nha", { tok: TOK }); } catch (e) {}
      }, { once: true });
    } catch (eP) {}
    var doc = win.document;
    var step = cmd.delay || 1200, waited = 0, cap = cmd.timeout || 300000;
    var buoc = "cho-composer";      // -> dien-chu -> xin-file -> cho-media -> bam-dang -> cho-xong
    var choComposer = 0, choMedia = 0, choNut = 0, choXong = 0, daBaoDump = false;
    var lanDienChu = 0;
    var thuCho = 0;
    var ptCuoi = "";
    var tbCuoi = "";
    var daDien = false, choKiem = 0;
    var choLich = 0;
    var choSau = 0;
    var daDatLich = false;
    var ketLich = "";
    function tiepTheo() {
      // CO LICH -> dat lich TRUOC khi dinh video: chuyen sang man lich ca trang roi quay lai se
      // lam RUNG media da dinh (da do that 05/10). Dat lich xong, composer ve, moi dinh video.
      if (cmd.lich && !daDatLich) { return "mo-lich"; }
      if (cmd.path) { return "xin-file"; }
      if (cmd.dry) { return "thu-doc"; }
      return "bam-dang";
    }
    function sauKhiDatLich() {
      if (cmd.path) { return "xin-file"; }
      if (cmd.dry) { return "thu-doc"; }
      return "bam-dang";
    }

    win.setTimeout(function tick() {
      try {
        var url = win.location.href;
        var man = xpPhanLoai(url, txt(doc));
        if (man === "x-login") { report("logged-out", url.slice(0, 70)); return; }
        if (man === "x-locked") { report("x-locked", url.slice(0, 70)); return; }
        // GIOI HAN DANG TRONG NGAY: kiem MOI nhip (banner co san tren trang -> khong phi cong tai
        // video; hien ra sau khi bam Post -> bai KHONG len, tuyet doi khong coi la da dang).
        if (xpGioiHan(txt(doc))) { report("daily-limit", "X: You've hit the daily post limit (buoc " + buoc + ")"); return; }

        if (buoc === "cho-composer") {
          var composer = oSoan(doc);
          if (!composer) {
            choComposer += step;
            if (choComposer > 30000) {
              if (!daBaoDump) { daBaoDump = true; report("seen", man + " | " + url.slice(0, 70) + " | " + dump(doc)); }
              report("no-composer", dump(doc));
              return;
            }
          } else {
            report("seen", "composer ok | " + dump(doc));
            buoc = "dien-chu";
          }
        } else if (buoc === "dien-chu") {
          // GO MOT LAN, KIEM O NHIP SAU. LOI CU (do that 29/09, 2/2 lan): kiem NGAY sau khi go,
          // DraftJS chua ve lai -> tuong chua vao -> go lan 2 -> caption LAP. Gio: cho nhip sau
          // moi dem; 1 lan = xong; >=2 lan = xoa sach go lai; van trong sau 3 nhip = xoa roi go lai.
          var c2 = oSoan(doc);
          var nd = (cmd.text || "").trim();
          if (c2 && nd) {
            if (!daDien) {
              if (lanDienChu > 0) { xoaOSoan(win, doc, c2); }
              dienChu(win, doc, c2, cmd.text);
              lanDienChu++; daDien = true; choKiem = 0;
            } else {
              choKiem++;
              var dem2 = demLap(c2, nd);
              if (dem2 === 1) {
                report("text-filled", "lần gõ " + lanDienChu);
                buoc = tiepTheo();
              } else if (lanDienChu >= 4) {
                report("text-filled", "không xác minh được (" + dem2 + " lần) sau " + lanDienChu + " lần gõ");
                buoc = tiepTheo();
              } else if (dem2 >= 2 || choKiem >= 3) {
                report("seen", (dem2 >= 2 ? "caption LẶP " + dem2 + " lần" : "chữ chưa vào") +
                  " -> xoá sạch, gõ lại (lần " + (lanDienChu + 1) + ")");
                daDien = false;
              }
            }
          } else {
            buoc = tiepTheo();
          }
        } else if (buoc === "thu-doc") {
          // CHE DO THU (khong dang): cho DraftJS ve xong roi doc lai o soan, dem so lan chu lap.
          thuCho++;
          if (thuCho >= 3) {
            var c3 = oSoan(doc), noi = c3 ? (c3.innerText || c3.textContent || "") : "";
            var mau3 = (cmd.text || "").trim().slice(0, 20), dem = 0, vt = noi.indexOf(mau3);
            while (mau3 && vt >= 0) { dem++; vt = noi.indexOf(mau3, vt + mau3.length); }
            report("dry-done", JSON.stringify({ lan: dem, lan_dien: lanDienChu, noi_dung: noi.slice(0, 400) }));
            return;
          }
        } else if (buoc === "xin-file") {
          buoc = "cho-file";
          report("seen", "xin file: " + (cmd.path || "").slice(-60));
          xinFile(cmd.path, function (d) {
            if (!d.ok) { report("file-error", d.error || "khong doc duoc file"); return; }
            if (!ganFile(win, doc, d, cmd)) { report("file-error", "khong gan duoc file vao composer"); return; }
            buoc = "cho-media";
          });
        } else if (buoc === "cho-media") {
          if (coMediaDinhKem(doc)) {
            report("media-attached", "");
            buoc = "bam-dang";
          } else {
            choMedia += step;
            var tb = thongBaoTrang(doc);
            if (tb && tb !== tbCuoi) { tbCuoi = tb; report("seen", "cho-media thong bao: " + tb); }
            // X TU CHOI media (vd video dai hon 2:20 voi acc thuong): bao NGAY, khong ngoi cho 90s.
            if (/media failed to load|couldn.?t upload|video is too long|too long|không tải được|quá dài/i.test(tb)) {
              report("media-rejected", tb);
              return;
            }
            if (choMedia > 90000) {
              report("file-error", "media khong hien trong composer" + (tbCuoi ? " — X báo: " + tbCuoi : "") + " | " + dump(doc));
              return;
            }
          }
        } else if (buoc === "mo-lich") {
          var nutL = nutMoLich(doc);
          if (nutL) {
            clickReal(win, nutL);
            report("schedule-open", dumpLich(doc));
            buoc = "dien-lich"; choLich = 0;
          } else {
            choLich += step;
            if (choLich > 30000) { report("schedule-failed", "không thấy nút lịch | " + dumpToolbar(doc) + " | " + dump(doc)); return; }
            else if (choLich % 10000 < step) { report("seen", "chờ nút lịch " + Math.round(choLich / 1000) + "s | " + dumpToolbar(doc)); }
          }
        } else if (buoc === "dien-lich") {
          var sels = selectsLich(doc);
          if (sels.length >= 5) {
            var macDinh = docMacDinh(sels);
            var ket = dienLich(win, doc, sels, cmd.lich);
            ketLich = ket + " || X điền sẵn: " + macDinh;
            report("schedule-filled", ketLich + " || " + moTaSelects(sels));
            buoc = "xac-nhan-lich"; choLich = 0;
          } else {
            choLich += step;
            if (choLich > 15000) { report("schedule-failed", "không thấy ô chọn ngày/giờ (selects=" + sels.length + ") | " + dump(doc)); return; }
          }
        } else if (buoc === "xac-nhan-lich") {
          var xn = nutXacNhanLich(doc);
          if (xn) {
            var nutDS = dumpNutLich(doc);
            var xnMo = (xn.getAttribute("data-testid") || "") + "/" +
              (xn.innerText || "").replace(/\s+/g, " ").trim().slice(0, 18);
            clickReal(win, xn);
            var nd1 = nutDang(doc);
            report("schedule-confirmed", ketLich + " || đã bấm: " + xnMo + " || nút sau Confirm: "
              + (nd1 ? (nd1.innerText || "").replace(/\s+/g, " ").trim().slice(0, 20) : "?")
              + " || nút trong hộp: " + nutDS);
            daDatLich = true;
            buoc = cmd.dry ? "thu-lich" : "sau-lich"; choLich = 0; choSau = 0;
          } else {
            choLich += step;
            if (choLich > 12000) { report("schedule-failed", "không thấy nút Confirm hộp lịch | " + dump(doc)); return; }
          }
        } else if (buoc === "thu-lich") {
          // CHE DO THU + lich: da dien va Confirm, KHONG bam Schedule.
          var nd0 = nutDang(doc);
          report("dry-done", JSON.stringify({ lich: cmd.lich, nut: nd0 ? (nd0.innerText || "").replace(/\s+/g, " ").trim() : "" }));
          return;
        } else if (buoc === "sau-lich") {
          // Hop lich la MAN HINH CA TRANG -> sau Confirm phai CHO composer ve lai moi doc duoc
          // media/nut. Doc ngay lap tuc se thay "trong" va phan nham la mat video.
          choSau += step;
          var coSoan = !!oSoan(doc);
          if (choSau % 5000 < step) {
            report("seen", "sau đặt lịch " + Math.round(choSau / 1000) + "s | soạn=" + (coSoan ? 1 : 0)
              + " | " + dump(doc));
          }
          if (coSoan) {
            var ndSau = (cmd.text || "").trim();
            if (ndSau && demLap(oSoan(doc), ndSau) < 1) {
              // Man lich dung lai composer -> chu cung bay. Go lai roi moi dinh video.
              report("seen", "composer quay lại nhưng MẤT CHỮ — gõ lại trước khi đính video");
              daDien = false; choKiem = 0;
              buoc = "dien-chu";
            } else {
              report("seen", "composer đã quay lại sau đặt lịch — giờ mới đính video");
              buoc = sauKhiDatLich();
            }
          } else if (choSau > 25000) {
            report("schedule-failed", "sau khi đặt lịch, composer không quay lại sau 25s ("
              + dump(doc) + ")");
            return;
          }
        } else if (buoc === "bam-dang") {
          var nut = nutDangBam(doc);
          if (nut && cmd.dry) {
            // CHE DO THU co video: video da tai xong (nut Post bat) -> bao lai, KHONG bam dang.
            report("dry-done", JSON.stringify({ post_bat: true, pt_cuoi: ptCuoi, giay_cho: Math.round(choNut / 1000),
              lan: demLap(oSoan(doc) || doc.body, cmd.text || ""), lan_dien: lanDienChu }));
            return;
          }
          if (nut && cmd.lich && !laNutLenLich(doc)) {
            // Nut da BAT nhung van la "Post" -> lich chua ap. BAM = DANG NGAY (sai hoan toan) -> DUNG.
            report("schedule-failed", "nút vẫn là \"" +
              ((nutDang(doc) || {}).innerText || "").replace(/\s+/g, " ").trim().slice(0, 20) +
              "\" chứ không đổi thành Schedule — lịch chưa được áp, KHÔNG bấm để khỏi đăng ngay.");
            return;
          }
          if (nut) {
            daBamPost = true;
            try { sendSyncMessage("qlfpxp:dabam", { tok: TOK }); } catch (eB) {}
            clickReal(win, nut);
            report("post-clicked", cmd.lich ? "bấm Schedule" : "");
            buoc = "cho-xong";
          } else {
            // Nut Post CHUA BAT = video dang tai len / X dang xu ly. Mang yeu co the rat lau:
            // DOC % X hien ("Uploading (20%)") bao ve tool; CHI khi nut Post bat moi bam; khong
            // thi cho TOI DA 15 PHUT (nguoi dung chot 29/09) roi moi bo. Truoc day 4 phut la tat.
            choNut += step;
            var pt = phanTramUpload(txt(doc));
            if (pt && pt !== ptCuoi) { ptCuoi = pt; report("upload-progress", pt); }
            // X co luc HIEN video trong o soan roi moi bao loi (da gap 29/09, video 14.7 phut) ->
            // kiem ca o buoc cho nut Post, khong thi dung cho het 15 phut.
            var tb2 = thongBaoTrang(doc);
            if (/media failed to load|couldn.?t upload|video is too long|too long|không tải được|quá dài/i.test(tb2)) {
              report("media-rejected", tb2);
              return;
            }
            if (choNut % 20000 < step) {
              // Chan doan: chu quanh video + thong bao loi (vd video qua dai voi acc thuong).
              var vung = q(doc, '[data-testid="attachments"]'), bao = q(doc, '[role="alert"]');
              report("seen", "cho-post " + Math.round(choNut / 1000) + "s | " +
                ((vung && vung.innerText) || "").replace(/\s+/g, " ").slice(0, 200) + " | alert: " +
                ((bao && bao.innerText) || "").replace(/\s+/g, " ").slice(0, 200));
            }
            if (choNut > CHO_UPLOAD_TOI_DA) {
              if (cmd.lich) {
                report("schedule-failed", "nút Schedule không bật sau "
                  + Math.round(CHO_UPLOAD_TOI_DA / 60000) + " phút — thường do GIỜ HẸN không hợp lệ với "
                  + "múi giờ của tài khoản X (giờ đã qua) hoặc X chặn đặt lịch. Xem 'X điền sẵn' ở "
                  + "schedule-filled để biết giờ hiện tại theo múi giờ acc.");
                return;
              }
              report("upload-stuck", "chờ " + Math.round(CHO_UPLOAD_TOI_DA / 60000) + " phút nút Post vẫn chưa bật" +
                (ptCuoi ? " (lần cuối: " + ptCuoi + ")" : "") + " | " + dump(doc));
              return;
            }
          }
        } else if (buoc === "cho-xong") {
          choXong += step;
          var body = txt(doc);
          var composer3 = oSoan(doc);
          var trong = composer3 ? !(composer3.textContent || "").trim() : true;
          if (cmd.lich) {
            if (xpDaLenLich(body) || (trong && !coMediaDinhKem(doc) && choXong >= step * 2)) {
              report("scheduled-done", "");
              return;
            }
          } else if (xpDaGui(body) || (trong && !coMediaDinhKem(doc) && choXong >= step * 2)) {
            report("post-done", "");
            return;
          }
          if (/something went wrong|đã xảy ra lỗi|da xay ra loi|whoops/i.test(body)) {
            report("post-error", "X báo lỗi sau khi bấm Đăng");
            return;
          }
          if (choXong > 120000) { report("publish-timeout", "không thấy xác nhận sau khi bấm Đăng"); return; }
        }
      } catch (e) { report("tick-error", String(e)); }
      waited += step;
      if (waited < cap) { win.setTimeout(tick, step); }
    }, 1200);
  }

  var observer = {
    observe: function (subject, topic) {
      if (topic !== "content-document-global-created") { return; }
      var win = subject;
      try {
        if (win.top !== win) { return; }        // composer chi o cua so tren cung
        win.addEventListener("load", function onload() {
          win.removeEventListener("load", onload);
          onPage(win);
        }, { once: true });
      } catch (e) {}
    },
  };
  Services.obs.addObserver(observer, "content-document-global-created");
}
