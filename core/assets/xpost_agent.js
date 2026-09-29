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
    if (/account\/access|\/suspended|your account is (locked|suspended)|tài khoản.*(khoá|khóa|tạm khoá)/i.test(url + " " + text)) { return "x-locked"; }
    if (/i\/flow\/login|\/i\/flow\/signup|\/login(\b|$|\?)/.test(url)) { return "x-login"; }
    if (/\/home(\b|$|\?)/.test(url)) { return "x-home"; }
    return "x";
  }
  return "";
}
/** Bai da gui chua, doan tu chu tren man (toast). THUAN. */
var XP_SENT_RE = /your post was sent|đã gửi bài đăng|da gui bai dang|bài đăng của bạn đã được gửi/i;
function xpDaGui(text) { return XP_SENT_RE.test(text || ""); }
/** X gioi han dang trong ngay (banner hong tren dong thoi gian + toast xanh sau khi bam Post).
 *  Da gap that 29/09: "You've hit the daily post limit. Subscribe to Premium for higher limits." */
var XP_LIMIT_RE = /hit the daily (post|tweet) limit|daily (post|tweet) limit|giới hạn (bài )?đăng (hằng|hàng) ngày|đã đạt giới hạn đăng/i;
function xpGioiHan(text) { return XP_LIMIT_RE.test(text || ""); }
/** Cho video tai len TOI DA 15 phut (nguoi dung chot 29/09) roi moi bo, dong trinh duyet. */
var CHO_UPLOAD_TOI_DA = 15 * 60 * 1000;
/** "…: Uploading (20%)" / "Uploaded (100%)" / "Processing (45%)" (EN/VI) -> "Uploading 20%". THUAN. */
function phanTramUpload(text) {
  var m = /(uploading|uploaded|processing|đang tải lên|đã tải lên|đang xử lý)[^%\n]{0,20}?(\d{1,3})\s*%/i.exec(text || "");
  return m ? (m[1].charAt(0).toUpperCase() + m[1].slice(1).toLowerCase() + " " + m[2] + "%") : "";
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { phanLoai: xpPhanLoai, daGui: xpDaGui, phanTram: phanTramUpload, gioiHan: xpGioiHan,
                     CHO_UPLOAD_TOI_DA: CHO_UPLOAD_TOI_DA };
}

if (typeof sendAsyncMessage === "function") {

  var lines = [];
  function report(state, detail) {
    lines.push(state + (detail ? ": " + detail : ""));
    try {
      sendAsyncMessage("qlfpxp:report", { state: state, detail: detail || "", log: lines.slice(-30) });
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
      el.dispatchEvent(me("click"));
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
    var el = q(doc, '[data-testid="tweetButtonInline"]') || q(doc, '[data-testid="tweetButton"]');
    return el && vis(el) ? el : null;
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

  // ---- luong chinh ---------------------------------------------------------------------
  function onPage(win) {
    var cmd = getCommand();
    if (!cmd || cmd.action !== "xpost") { return; }
    // Chi chay tren x.com: truoc do tool mo trang KIEM VPN (ipinfo) -- o do khong co
    // o soan, de chay thi sau 30s bao nham "no-composer".
    if (!/x\.com|twitter\.com/i.test(win.location.href)) { return; }
    var doc = win.document;
    var step = cmd.delay || 1200, waited = 0, cap = cmd.timeout || 300000;
    var buoc = "cho-composer";      // -> dien-chu -> xin-file -> cho-media -> bam-dang -> cho-xong
    var choComposer = 0, choMedia = 0, choNut = 0, choXong = 0, daBaoDump = false;
    var lanDienChu = 0;
    var thuCho = 0;
    var ptCuoi = "";
    var tbCuoi = "";
    var daDien = false, choKiem = 0;

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
                buoc = cmd.path ? "xin-file" : (cmd.dry ? "thu-doc" : "bam-dang");
              } else if (lanDienChu >= 4) {
                report("text-filled", "không xác minh được (" + dem2 + " lần) sau " + lanDienChu + " lần gõ");
                buoc = cmd.path ? "xin-file" : (cmd.dry ? "thu-doc" : "bam-dang");
              } else if (dem2 >= 2 || choKiem >= 3) {
                report("seen", (dem2 >= 2 ? "caption LẶP " + dem2 + " lần" : "chữ chưa vào") +
                  " -> xoá sạch, gõ lại (lần " + (lanDienChu + 1) + ")");
                daDien = false;
              }
            }
          } else {
            buoc = cmd.path ? "xin-file" : "bam-dang";
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
        } else if (buoc === "bam-dang") {
          var nut = nutDangBam(doc);
          if (nut && cmd.dry) {
            // CHE DO THU co video: video da tai xong (nut Post bat) -> bao lai, KHONG bam dang.
            report("dry-done", JSON.stringify({ post_bat: true, pt_cuoi: ptCuoi, giay_cho: Math.round(choNut / 1000),
              lan: demLap(oSoan(doc) || doc.body, cmd.text || ""), lan_dien: lanDienChu }));
            return;
          }
          if (nut) {
            clickReal(win, nut);
            report("post-clicked", "");
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
          if (xpDaGui(body) || (trong && !coMediaDinhKem(doc) && choXong >= step * 2)) {
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
