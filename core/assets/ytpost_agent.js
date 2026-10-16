/* Process script: DANG VIDEO len YouTube qua YouTube Studio.
 *
 * Cung khuon xpost_agent.js (dang bai X) va gmail_agent.js (dang nhap Google):
 * chay trong tien trinh noi dung, thao tac bang su kien "nguoi that"
 * (setHandlingUserInput), trinh duyet mo BINH THUONG (khong cong debug).
 *
 * Bridge RIENG (khong dung chung voi agent khac):
 *   sendSyncMessage("qlfpyt:cmd")      -> cha doc <profile>/qlfp-ytpost.json
 *   sendAsyncMessage("qlfpyt:report")  -> cha ghi <profile>/qlfp-ytpost-result.json
 *   sendAsyncMessage("qlfpyt:needfile", {path}) -> cha mo file video roi broadcast
 *   "qlfpyt:file" {ok, name, file|bytes} ve (tien trinh noi dung bi chan doc dia).
 *
 * Lenh: { action:"ytpost"|"ytprobe", path, name, mime, tieu_de, mo_ta, rieng_tu,
 *         tre_em, dry, timeout }
 *   rieng_tu: "PUBLIC" | "UNLISTED" | "PRIVATE" (mac dinh PUBLIC)
 *   tre_em:   false = "Khong danh cho tre em" (mac dinh), true = danh cho tre em
 *   dry:      dien het nhung KHONG bam Xuat ban (de soi khong lam rac kenh)
 *
 * YouTube Studio la Polymer: HAU HET phan tu nam trong SHADOW ROOT -> moi truy van
 * phai di XUYEN shadow root (ytSau/ytSauHet). Cac #id cua Studio khong doi theo
 * ngon ngu nen do theo ID truoc, chu chi lam duong lui.
 *
 * Trang thai bao ve cha (moi cai bao mot lan):
 *   seen | yt-login | no-upload-dialog | file-attached | upload-progress |
 *   title-filled | kids-set | step-next | visibility-set | publish-clicked |
 *   post-done | dry-done | publish-error | upload-stuck | file-error
 */
"use strict";

/* ---- phan THUAN (test bang node) ---------------------------------------------------- */
/** ytPhanLoai(url, text) -> "yt-studio" | "yt-login" | "yt" | "". THUAN. */
function ytPhanLoai(url, text) {
  url = (url || "").toLowerCase();
  text = text || "";
  if (/accounts\.google\.com|\/signin|serviceLogin/i.test(url)) { return "yt-login"; }
  if (/studio\.youtube\.com|youtube\.com\/upload/.test(url)) {
    if (/\/signin|đăng nhập để tiếp tục|sign in to continue/i.test(url + " " + text)) { return "yt-login"; }
    return "yt-studio";
  }
  if (/youtube\.com/.test(url)) { return "yt"; }
  return "";
}
/** Tieu de YouTube toi da 100 KY TU; mo ta 5000. Cat o ranh gioi tu. THUAN. */
function ytTieuDe(text, toiDa) {
  toiDa = parseInt(toiDa, 10) || 100;
  var t = String(text || "").replace(/\s+/g, " ").trim();
  // YouTube KHONG nhan "<" va ">" trong tieu de (bao loi do) -> bo luon.
  t = t.replace(/[<>]/g, "");
  if (t.length <= toiDa) { return t; }
  var cat = t.slice(0, toiDa);
  var ngan = cat.replace(/\s+\S*$/, "").trim();
  return ngan.length >= 10 ? ngan : cat.trim();
}
/** "Dang tai len 45% ..." / "Uploading 45%" / "Processing 90%" -> "Uploading 45%". THUAN. */
function ytPhanTram(text) {
  var m = /(uploading|uploaded|processing|đang tải lên|đã tải lên|đang xử lý)[^%\n]{0,24}?(\d{1,3})\s*%/i.exec(text || "");
  if (m) { return m[1].charAt(0).toUpperCase() + m[1].slice(1).toLowerCase() + " " + m[2] + "%"; }
  m = /(\d{1,3})\s*%/.exec(text || "");
  return m ? m[1] + "%" : "";
}
/** Studio bao DA XUAT BAN (video/Short) — EN + VI. THUAN. */
var YT_XONG_RE = /video (published|is live)|short published|đã xuất bản|đã được xuất bản|video của bạn đã|published to/i;
function ytDaXuatBan(text) { return YT_XONG_RE.test(text || ""); }
/** Studio bao LOI xu ly / tu choi video. THUAN. */
var YT_LOI_RE = /processing (failed|abandoned)|xử lý (thất bại|lỗi)|upload (failed|aborted)|tải lên thất bại|không thể xử lý|can't process|daily upload limit|giới hạn tải lên/i;
function ytLoiTaiLen(text) { return YT_LOI_RE.test(text || ""); }
/** Cho video tai len/xu ly toi da 15 phut roi moi bo (nhu X). */
var YT_CHO_UPLOAD = 15 * 60 * 1000;

/** The tag -> hashtag dung cho MO TA (Short KHONG co o the tag: YouTube bo han o nay).
 *  "true crime" -> "#truecrime"; bo ky tu khong dung duoc trong hashtag. THUAN. */
function ytHashtag(tags, moTa) {
  var ra = [], da = {};
  // Hashtag DA CO trong mo ta thi khong them nua (khoi ra "#shorts #shorts").
  var co = String(moTa || "").toLowerCase();
  for (var i = 0; i < (tags || []).length; i++) {
    var t = String(tags[i] || "").replace(/[^0-9A-Za-zÀ-ỹà-ỹ_]/g, "");
    if (!t || da[t.toLowerCase()]) { continue; }
    if (co.indexOf("#" + t.toLowerCase()) >= 0) { continue; }
    da[t.toLowerCase()] = 1;
    ra.push("#" + t);
    if (ra.length >= 15) { break; }
  }
  return ra.join(" ");
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { phanLoai: ytPhanLoai, tieuDe: ytTieuDe, phanTram: ytPhanTram, hashtag: ytHashtag,
                     daXuatBan: ytDaXuatBan, loiTaiLen: ytLoiTaiLen, CHO_UPLOAD: YT_CHO_UPLOAD };
}

if (typeof sendAsyncMessage === "function") {

  var lines = [];
  function report(state, detail) {
    lines.push(state + (detail ? ": " + detail : ""));
    try {
      sendAsyncMessage("qlfpyt:report", { state: state, detail: detail || "", log: lines.slice(-30) });
    } catch (e) {}
  }
  function getCommand() {
    try {
      var a = sendSyncMessage("qlfpyt:cmd");
      var raw = a && a.length ? a[0] : "";
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  /* ---- truy van XUYEN SHADOW ROOT (Studio la Polymer) ---------------------------- */
  function goc_shadow(el) {
    try {
      if (el.openOrClosedShadowRoot) { return el.openOrClosedShadowRoot; }
    } catch (e) {}
    try { return el.shadowRoot || null; } catch (e) { return null; }
  }
  /** Tat ca phan tu khop ``chon``, di xuyen moi shadow root (toi da ``capToiDa`` tang). */
  function ytSauHet(goc, chon, capToiDa) {
    var ra = [];
    var capSau = capToiDa || 25;
    // BFS theo TANG: moi muc hang doi mang theo DO SAU cua no.
    // LOI THAT 06/10: truoc day tru "cap" MOI LAN POP MOT GOC (khong phai moi TANG) ->
    // Studio co hang tram custom element nen chi mo duoc ~20 shadow root dau roi dung
    // -> khong bao gio tim ra o the tag / bang video. Gio cap la DO SAU thuc su.
    var hang = [[goc, 0]];
    var vong = 0;
    while (hang.length && vong < 40000) {
      var muc = hang.shift();
      var r = muc[0], sau = muc[1];
      vong += 1;
      var ds;
      try { ds = r.querySelectorAll(chon); } catch (e) { ds = []; }
      for (var i = 0; i < ds.length; i++) { if (ra.indexOf(ds[i]) < 0) { ra.push(ds[i]); } }
      if (sau >= capSau) { continue; }
      var con;
      try { con = r.querySelectorAll("*"); } catch (e) { con = []; }
      for (var j = 0; j < con.length; j++) {
        var sh = goc_shadow(con[j]);
        if (sh) { hang.push([sh, sau + 1]); }
      }
    }
    return ra;
  }
  function ytSau(goc, chon) {
    var ds = ytSauHet(goc, chon);
    for (var i = 0; i < ds.length; i++) { if (vis(ds[i])) { return ds[i]; } }
    return ds.length ? ds[0] : null;
  }
  function ytSauHien(goc, chon) {
    var ds = ytSauHet(goc, chon), ra = [];
    for (var i = 0; i < ds.length; i++) { if (vis(ds[i])) { ra.push(ds[i]); } }
    return ra;
  }

  /** Hien thi: KHONG dung offsetParent — Studio dat nhieu khoi position:fixed nen
   *  offsetParent === null du phan tu dang nhin thay (bai hoc tu agent Gmail). */
  function vis(el) {
    try {
      var b = el.getBoundingClientRect();
      if (b.width < 2 || b.height < 2) { return false; }
      var st = el.ownerGlobal ? el.ownerGlobal.getComputedStyle(el) : null;
      if (st && (st.display === "none" || st.visibility === "hidden" || st.opacity === "0")) { return false; }
      return true;
    } catch (e) { return false; }
  }
  function chu(el) {
    try { return (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim(); }
    catch (e) { return ""; }
  }
  function chuTrang(doc) {
    try { return doc.body ? doc.body.innerText : ""; } catch (e) { return ""; }
  }
  function withUserInput(win, fn) {
    var h = null;
    try { h = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try { return fn(); } finally { if (h) { try { h.destruct(); } catch (e) {} } }
  }
  function clickReal(win, el) {
    try {
      var r = el.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      function pe(t) { return new win.PointerEvent(t, { bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0, pointerType: "mouse", isPrimary: true }); }
      function me(t) { return new win.MouseEvent(t, { bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0 }); }
      withUserInput(win, function () {
        el.dispatchEvent(pe("pointerover")); el.dispatchEvent(me("mouseover"));
        el.dispatchEvent(pe("pointerdown")); el.dispatchEvent(me("mousedown"));
        try { el.focus(); } catch (e) {}
        el.dispatchEvent(pe("pointerup")); el.dispatchEvent(me("mouseup"));
        el.dispatchEvent(me("click"));
      });
      try { el.click(); } catch (e) {}
      return true;
    } catch (e) { return false; }
  }
  function khoa(el) {
    try {
      return el.disabled === true || el.getAttribute("disabled") !== null
             || el.getAttribute("aria-disabled") === "true";
    } catch (e) { return false; }
  }

  /** Go chu vao o cua Studio (contenteditable trong ytcp-social-suggestions-textbox). */
  function goVaoO(win, doc, o, text) {
    try {
      clickReal(win, o);
      o.focus();
      var sel = win.getSelection();
      var rg = doc.createRange();
      rg.selectNodeContents(o);
      sel.removeAllRanges();
      sel.addRange(rg);
      withUserInput(win, function () {
        doc.execCommand("delete", false, null);
        doc.execCommand("insertText", false, text);
      });
      return true;
    } catch (e) { return false; }
  }

  /* ---- cac manh giao doan cua YouTube Studio -------------------------------------- */
  /** Hop chao mung "Welcome to YouTube Studio" CHE hop tai len -> phai bam Continue.
   *  Da do that 06/10: #dialog "Welcome to YouTube Stu" + #dismiss-button "Continue". */
  function donHopChao(win, doc) {
    var ds = ytSauHet(doc, "#dismiss-button, #dismissButton");
    for (var i = 0; i < ds.length; i++) {
      if (!vis(ds[i]) || khoa(ds[i])) { continue; }
      clickReal(win, ds[i]);
      return true;
    }
    return false;
  }
  function oChonFile(doc) {
    var ds = ytSauHet(doc, 'input[type="file"]');
    for (var i = 0; i < ds.length; i++) {
      // input file cua Studio bi an (display:none) nen KHONG loc theo vis.
      var ac = (ds[i].getAttribute("accept") || "").toLowerCase();
      if (/image/.test(ac)) { continue; }              // do la o chon ANH THUMB
      if (!ac || /video|\*/.test(ac)) { return ds[i]; }
    }
    return ds.length ? ds[0] : null;
  }
  /** O chon ANH THUMB (input[type=file] accept co "image"), o buoc Chi tiet. */
  function oChonAnh(doc) {
    var ds = ytSauHet(doc, 'input[type="file"]');
    for (var i = 0; i < ds.length; i++) {
      var ac = (ds[i].getAttribute("accept") || "").toLowerCase();
      if (/image|\.png|\.jpg/.test(ac)) { return ds[i]; }
    }
    return null;
  }
  /** Nut "Show more" / "Hiện thêm" mo phan cai dat chi tiet (co o THE TAG). */
  function nutHienThem(doc) {
    var el = ytSau(gocHop(doc), "#toggle-button") || ytSau(doc, "#toggle-button");
    if (el && vis(el) && /more|thêm|them/i.test(chu(el) + (el.getAttribute("aria-label") || ""))) {
      return el;
    }
    return nutTheoChu(doc, /show more|hiện thêm|hien them|xem thêm/i);
  }
  /** O nhap THE TAG (chips). Studio: #tags-container > input, aria-label co "tag"/"thẻ". */
  /** Goc tim: HOP TAI LEN neu dang mo (cay nho, tim nhanh va dung cho), khong thi ca trang. */
  function gocHop(doc) {
    // CHI nhan hop TAI LEN. Studio con co "#dialog" vo chung chung (chi chua o tim)
    // -> nhan bua la tim trong cay SAI, khong thay o nao (loi that 06/10).
    var ds = ytSauHet(doc, "ytcp-uploads-dialog");
    for (var i = 0; i < ds.length; i++) { if (vis(ds[i])) { return ds[i]; } }
    return doc;
  }
  function oTag(doc) {
    var g = gocHop(doc);
    var h = ytSau(g, "#tags-container, #tags-input, ytcp-form-input-container#tags-container")
            || ytSau(doc, "#tags-container, #tags-input");
    if (h) {
      var inp = ytSau(h, 'input,div[contenteditable="true"]');
      if (inp && vis(inp)) { return inp; }
    }
    var ds = ytSauHet(doc, "input");
    for (var i = 0; i < ds.length; i++) {
      var lb = ((ds[i].getAttribute("aria-label") || "") + " "
                + (ds[i].getAttribute("placeholder") || "")).toLowerCase();
      if (/tag|thẻ|the /.test(lb) && vis(ds[i])) { return ds[i]; }
    }
    return null;
  }
  /** Go chu vao INPUT thuong (o tag): native value setter + su kien input. */
  function goVaoInput(win, doc, o, text) {
    try {
      clickReal(win, o);
      o.focus();
      var proto = win.Object.getPrototypeOf(o);
      var d = win.Object.getOwnPropertyDescriptor(proto, "value");
      if (d && d.set) { d.set.call(o, text); } else { o.value = text; }
      withUserInput(win, function () {
        o.dispatchEvent(new win.Event("input", { bubbles: true }));
        o.dispatchEvent(new win.Event("change", { bubbles: true }));
      });
      return true;
    } catch (e) { return false; }
  }
  function nutTheoId(doc, id) {
    var el = ytSau(doc, "#" + id);
    return el && vis(el) ? el : null;
  }
  function nutTheoChu(doc, re) {
    var ds = ytSauHet(doc, 'button,[role="button"],ytcp-button,tp-yt-paper-button');
    for (var i = 0; i < ds.length; i++) {
      var t = chu(ds[i]);
      var lb = (ds[i].getAttribute("aria-label") || "") + " " + t;
      if (t.length < 60 && re.test(lb) && vis(ds[i]) && !khoa(ds[i])) { return ds[i]; }
    }
    return null;
  }
  function oTieuDe(doc) {
    var h = ytSau(doc, "#title-textarea");
    if (h) {
      var box = ytSau(h, '#textbox[contenteditable], div[contenteditable="true"]');
      if (box) { return box; }
    }
    var ds = ytSauHien(doc, 'div[contenteditable="true"],textarea');
    return ds.length ? ds[0] : null;
  }
  function oMoTa(doc) {
    var h = ytSau(doc, "#description-textarea, #description-container");
    if (h) {
      var box = ytSau(h, '#textbox[contenteditable], div[contenteditable="true"]');
      if (box) { return box; }
    }
    var ds = ytSauHien(doc, 'div[contenteditable="true"],textarea');
    return ds.length > 1 ? ds[1] : null;
  }
  /** Radio "Khong danh cho tre em" / "Danh cho tre em". */
  function radioTreEm(doc, treEm) {
    var ten = treEm ? "VIDEO_MADE_FOR_KIDS_MFK" : "VIDEO_MADE_FOR_KIDS_NOT_MFK";
    var el = ytSau(doc, 'tp-yt-paper-radio-button[name="' + ten + '"], [name="' + ten + '"]');
    if (el && vis(el)) { return el; }
    return null;
  }
  function daChon(el) {
    try {
      return el.getAttribute("aria-checked") === "true" || el.getAttribute("checked") !== null
             || (el.className || "").toString().indexOf("iron-selected") >= 0;
    } catch (e) { return false; }
  }
  function radioRiengTu(doc, muc) {
    var el = ytSau(doc, 'tp-yt-paper-radio-button[name="' + muc + '"], [name="' + muc + '"]');
    return el && vis(el) ? el : null;
  }
  /** Buoc dang o dau: 1 Chi tiet · 2 Thanh phan · 3 Kiem tra · 4 Che do hien thi. */
  function buocHienTai(doc) {
    var ds = ytSauHet(doc, '[aria-selected="true"], .step-badge-selected, #step-badge-3');
    for (var i = 0; i < ds.length; i++) {
      var id = (ds[i].id || "") + "";
      var m = /step-badge-(\d)/.exec(id);
      if (m && vis(ds[i])) { return parseInt(m[1], 10) + 1; }
    }
    if (radioRiengTu(doc, "PUBLIC")) { return 4; }
    if (oTieuDe(doc)) { return 1; }
    return 0;
  }
  function dumpStudio(doc) {
    var ra = [];
    var ds = ytSauHet(doc, "[id]");
    var dem = 0;
    for (var i = 0; i < ds.length && dem < 60; i++) {
      var id = (ds[i].id || "") + "";
      if (!id || id.length > 32) { continue; }
      if (!/button|textarea|radio|step|file|dialog|upload|progress|title|privacy|visib|tag|toggle|advanced|more/i.test(id)) { continue; }
      if (!vis(ds[i]) && !/file/i.test(id)) { continue; }
      ra.push("#" + id + (khoa(ds[i]) ? "(khoa)" : "") + (chu(ds[i]) ? ":" + chu(ds[i]).slice(0, 22) : ""));
      dem += 1;
    }
    return ra.join(" | ");
  }

  /* ---- xin file tu cha (tien trinh noi dung khong doc duoc dia) ------------------- */
  var fileDangCho = null;
  try {
    addMessageListener("qlfpyt:file", function (msg) {
      var d = msg.data || {};
      if (fileDangCho) { var f = fileDangCho; fileDangCho = null; f(d); }
    });
  } catch (e) {}
  function xinFile(path, xong) {
    fileDangCho = xong;
    try { sendAsyncMessage("qlfpyt:needfile", { path: path }); }
    catch (e) { fileDangCho = null; xong({ ok: false, error: String(e) }); }
  }
  function fileTuTin(win, data, mime) {
    // Uu tien doi tuong File cha gui thang (khong nap vao RAM); du phong la bytes.
    if (data && data.file) { return data.file; }
    if (data && data.bytes) {
      return new win.File([data.bytes], data.name || "video.mp4",
                          { type: mime || "video/mp4" });
    }
    return null;
  }
  function ganFile(win, doc, data, cmd) {
    try {
      var file = fileTuTin(win, data, cmd.mime);
      if (!file) { report("file-error", "cha khong tra duoc file"); return false; }
      var input = oChonFile(doc);
      if (!input) { return false; }
      try {
        // DataTransfer KHONG nhan File cua tien trinh cha -> uu tien mozSetFileArray.
        if (typeof input.mozSetFileArray === "function") {
          input.mozSetFileArray([file]);
        } else {
          var dt = new win.DataTransfer();
          dt.items.add(file);
          input.files = dt.files;
        }
        input.dispatchEvent(new win.Event("input", { bubbles: true }));
        input.dispatchEvent(new win.Event("change", { bubbles: true }));
        return true;
      } catch (e) { report("file-error", "gan file loi: " + String(e)); return false; }
    } catch (e) { report("file-error", String(e)); return false; }
  }

  /* ---- vong dang: may trang thai cham moi 1.2 giay ------------------------------- */
  var DANG_CHAY = false;
  function chayDang(win, doc, cmd) {
    var batDau = Date.now();
    var han = parseInt(cmd.timeout, 10) || (20 * 60 * 1000);
    var buoc = "cho-dialog";
    var daBao = {};
    var ptCuoi = "";
    var lanNext = 0;
    var lanBamNext = 0;
    var xinRoi = false;
    var moCreate = 0;
    var choThumb = 0;
    var choTag = 0;
    var daBamThem = false;
    var tienDoLuc = Date.now();

    function baoMot(st, det) {
      // Khoa theo CA trang thai LAN noi dung: truoc day khoa theo rieng trang thai nen
      // thong diep "seen" thu hai bi NUOT (mat han chan doan buoc the tag — loi that 06/10).
      var k = st + "|" + String(det || "").slice(0, 60);
      if (daBao[k]) { return; }
      daBao[k] = 1;
      report(st, det || "");
    }

    (function nhip() {
      if (Date.now() - batDau > han) {
        report("upload-stuck", "het gio (" + Math.round(han / 60000) + " phut) o buoc " + buoc
               + (ptCuoi ? ", lan cuoi " + ptCuoi : "") + " | " + dumpStudio(doc));
        return;
      }
      var tt = chuTrang(doc);
      if (ytLoiTaiLen(tt)) {
        report("publish-error", "YouTube bao loi: " + tt.replace(/\s+/g, " ").slice(0, 200));
        return;
      }
      var pt = ytPhanTram(tt);
      if (pt && pt !== ptCuoi) {
        ptCuoi = pt;
        tienDoLuc = Date.now();
        report("upload-progress", pt);
      }
      try {
        tiep(win, doc, cmd);
      } catch (e) {
        report("publish-error", "loi agent o buoc " + buoc + ": " + String(e));
        return;
      }
      win.setTimeout(nhip, 1200);
    })();

    function tiep(win, doc, cmd) {
      if (buoc === "cho-dialog") {
        if (donHopChao(win, doc)) { baoMot("seen", "da dong hop chao mung Studio"); return; }
        var input = oChonFile(doc);
        if (input) { buoc = "gan-file"; return; }
        // Chua co hop tai len -> bam CREATE roi "Tai video len".
        if (moCreate < 6) {
          moCreate += 1;
          var create = nutTheoId(doc, "create-icon") || nutTheoChu(doc, /^(create|tạo)$/i);
          if (create) { clickReal(win, create); baoMot("seen", "bam CREATE"); return; }
          var up = nutTheoChu(doc, /upload videos?|tải video lên|tải lên video/i);
          if (up) { clickReal(win, up); baoMot("seen", "bam 'Tai video len'"); return; }
        }
        if (moCreate >= 6) {
          report("no-upload-dialog", "khong thay o chon file / nut Tao | " + dumpStudio(doc));
          buoc = "dung";
        }
        return;
      }
      if (buoc === "gan-file") {
        if (xinRoi) { return; }
        xinRoi = true;
        buoc = "dang-gan";
        xinFile(cmd.path, function (data) {
          if (!data || !data.ok) {
            report("file-error", (data && data.error) || "khong doc duoc file");
            buoc = "dung";
            return;
          }
          if (ganFile(win, doc, data, cmd)) {
            baoMot("file-attached", data.name || cmd.name || "");
            buoc = "cho-chi-tiet";
            tienDoLuc = Date.now();
          } else {
            report("file-error", "khong gan duoc file vao o chon file | " + dumpStudio(doc));
            buoc = "dung";
          }
        });
        return;
      }
      if (buoc === "cho-chi-tiet") {
        donHopChao(win, doc);
        if (oTieuDe(doc)) { buoc = "dien-chi-tiet"; }
        else if (Date.now() - tienDoLuc > 120000) {
          report("no-upload-dialog", "gan file xong 2 phut ma khong ra man Chi tiet | " + dumpStudio(doc));
          buoc = "dung";
        }
        return;
      }
      if (buoc === "dien-chi-tiet") {
        var o = oTieuDe(doc);
        if (!o) { return; }
        var td = cmd.tieu_de || "";
        if (td) {
          goVaoO(win, doc, o, td);
          buoc = "kiem-tieu-de";
          return;
        }
        buoc = "tre-em";
        return;
      }
      if (buoc === "kiem-tieu-de") {
        // Kiem o NHIP SAU: Polymer cap nhat DOM bat dong bo (bai hoc DraftJS/Lexical).
        var o2 = oTieuDe(doc);
        var dang = o2 ? chu(o2) : "";
        var mong = (cmd.tieu_de || "").slice(0, 14);
        if (mong && dang.indexOf(mong) >= 0) {
          baoMot("title-filled", dang.length + " ky tu");
          buoc = "mo-ta";
          return;
        }
        lanNext += 1;
        if (lanNext > 4) {
          baoMot("seen", "KHONG go duoc tieu de (giu tieu de YouTube tu dien): \""
                 + dang.slice(0, 40) + "\"");
          buoc = "mo-ta";
          return;
        }
        if (o2) { goVaoO(win, doc, o2, cmd.tieu_de); }
        return;
      }
      if (buoc === "mo-ta") {
        // MO TA = noi dung file <ten>.txt di kem video (nguoi dung chot 06/10).
        if (cmd.mo_ta) {
          var om = oMoTa(doc);
          if (om && chu(om).indexOf(cmd.mo_ta.slice(0, 12)) < 0) {
            goVaoO(win, doc, om, cmd.mo_ta);
            baoMot("desc-filled", cmd.mo_ta.length + " ky tu");
          }
        }
        buoc = "thumb";
        return;
      }
      if (buoc === "thumb") {
        // ANH THUMB = file anh CUNG TEN video. Khong co thi bo qua.
        if (!cmd.thumb) { buoc = "tags"; return; }
        var oAnh = oChonAnh(doc);
        if (!oAnh) {
          if (choThumb < 8) { choThumb += 1; return; }     // cho o chon anh render
          baoMot("seen", "khong thay o chon anh thumb — bo qua thumb | " + dumpStudio(doc));
          buoc = "tags";
          return;
        }
        buoc = "dang-thumb";
        xinFile(cmd.thumb, function (data) {
          if (!data || !data.ok) {
            baoMot("seen", "khong doc duoc anh thumb: " + ((data && data.error) || "?"));
            buoc = "tags";
            return;
          }
          var ok = false;
          try {
            var f = fileTuTin(win, data, cmd.thumb_mime || "image/png");
            var o3 = oChonAnh(doc);
            if (f && o3) {
              if (typeof o3.mozSetFileArray === "function") { o3.mozSetFileArray([f]); }
              else {
                var dt = new win.DataTransfer();
                dt.items.add(f);
                o3.files = dt.files;
              }
              o3.dispatchEvent(new win.Event("input", { bubbles: true }));
              o3.dispatchEvent(new win.Event("change", { bubbles: true }));
              ok = true;
            }
          } catch (e) { baoMot("seen", "gan anh thumb loi: " + String(e)); }
          if (ok) { baoMot("thumb-set", data.name || ""); }
          buoc = "tags";
        });
        return;
      }
      if (buoc === "tags") {
        // THE TAG = <ten>_tag.txt. O tag nam trong phan "Show more" -> phai mo ra truoc.
        if (!cmd.tags || !cmd.tags.length) { buoc = "tre-em"; return; }
        // KIEU SHORTS: Studio KHONG co o the tag cho Short (do that 06/10) -> di thang
        // duong hashtag, khong ngoi tim "Show more" cho mat ~10 giay moi bai.
        if (cmd.che_do === "shorts") { buoc = "tag-hashtag"; return; }
        var ot = oTag(doc);
        if (!ot) {
          // Bam "Show more" DUNG MOT LAN: bam lan hai la DONG phan mo rong lai.
          if (!daBamThem) {
            var mo = nutHienThem(doc);
            if (mo) {
              clickReal(win, mo);
              daBamThem = true;
              baoMot("seen", "bam 'Show more' de mo phan the tag");
              return;
            }
          }
          choTag += 1;
          if (choTag <= 8) { return; }                   // cho phan mo rong render
          // Khong thay o the tag (voi Short thi YouTube BO HAN o nay — do that 06/10, ca
          // trang edit cung khong co) -> lui ve duong HASHTAG trong mo ta.
          baoMot("seen", "khong thay o the tag"
                 + (daBamThem ? " (da bam 'Show more')" : " va KHONG THAY nut 'Show more'")
                 + " -> dua tag vao mo ta dang hashtag");
          buoc = "tag-hashtag";
          return;
        }
        // Dau phay CUOI de Studio chot the tag cuoi thanh chip.
        goVaoInput(win, doc, ot, cmd.tags.join(",") + ",");
        baoMot("tags-set", cmd.tags.length + " the: " + cmd.tags.join(", ").slice(0, 80));
        buoc = "tre-em";
        return;
      }
      if (buoc === "tag-hashtag") {
        var ht = ytHashtag(cmd.tags, cmd.mo_ta);
        if (cmd.che_do === "shorts" && !/#shorts/i.test(String(cmd.mo_ta || "") + " " + ht)) {
          ht = (ht ? ht + " " : "") + "#Shorts";      // giup YouTube xep dung vao Shorts
        }
        var omh = oMoTa(doc);
        if (ht && omh) {
          goVaoO(win, doc, omh, (cmd.mo_ta ? cmd.mo_ta + "\n\n" : "") + ht);
          baoMot("tags-mo-ta", "da dua the tag vao mo ta dang hashtag: " + ht.slice(0, 100));
        } else if (ht) {
          baoMot("seen", "khong thay o mo ta de dat hashtag — bo qua tag");
        }
        buoc = "tre-em";
        return;
      }
      if (buoc === "tre-em") {
        var r = radioTreEm(doc, !!cmd.tre_em);
        if (r) {
          if (!daChon(r)) { clickReal(win, r); return; }
          baoMot("kids-set", cmd.tre_em ? "danh cho tre em" : "khong danh cho tre em");
          buoc = "next";
          lanBamNext = 0;
          return;
        }
        // Khong thay radio (Studio co the da nho san) -> di tiep.
        baoMot("seen", "khong thay radio 'danh cho tre em' — di tiep");
        buoc = "next";
        return;
      }
      if (buoc === "next") {
        if (radioRiengTu(doc, cmd.rieng_tu || "PUBLIC")) { buoc = "hien-thi"; return; }
        var next = nutTheoId(doc, "next-button")
                   || nutTheoChu(doc, /^(next|tiếp|tiếp theo)$/i);
        if (next && !khoa(next)) {
          clickReal(win, next);
          lanBamNext += 1;
          baoMot("step-next", "bam Tiep lan " + lanBamNext);
          // (khoa theo noi dung nen moi lan bam la mot thong diep khac -> tu bao lai)
          return;
        }
        if (lanBamNext >= 8) {
          report("publish-error", "bam Tiep 8 lan ma khong toi man Che do hien thi | " + dumpStudio(doc));
          buoc = "dung";
        }
        return;
      }
      if (buoc === "hien-thi") {
        var muc = cmd.rieng_tu || "PUBLIC";
        var rr = radioRiengTu(doc, muc);
        if (!rr) { return; }
        if (!daChon(rr)) { clickReal(win, rr); return; }
        baoMot("visibility-set", muc);
        buoc = cmd.dry ? "dry" : "xuat-ban";
        return;
      }
      if (buoc === "dry") {
        report("dry-done", "da dien xong (tieu de + tre em + " + (cmd.rieng_tu || "PUBLIC")
               + "), KHONG bam Xuat ban | " + dumpStudio(doc));
        buoc = "dung";
        return;
      }
      if (buoc === "xuat-ban") {
        var done = nutTheoId(doc, "done-button")
                   || nutTheoChu(doc, /^(publish|save|xuất bản|lưu)$/i);
        if (!done) { return; }
        if (khoa(done)) {
          // Nut bi khoa trong luc YouTube con xu ly -> cho, toi da YT_CHO_UPLOAD.
          if (Date.now() - tienDoLuc > YT_CHO_UPLOAD) {
            report("upload-stuck", "cho " + Math.round(YT_CHO_UPLOAD / 60000)
                   + " phut nut Xuat ban van khoa" + (ptCuoi ? ", lan cuoi " + ptCuoi : ""));
            buoc = "dung";
          }
          return;
        }
        clickReal(win, done);
        baoMot("publish-clicked", chu(done).slice(0, 30));
        buoc = "cho-xong";
        tienDoLuc = Date.now();
        return;
      }
      if (buoc === "cho-xong") {
        var t = chuTrang(doc);
        if (ytDaXuatBan(t)) {
          report("post-done", "YouTube bao da xuat ban");
          buoc = "dung";
          return;
        }
        // Hop chia se / hop "dang xu ly" hien ra = da nhan lenh xuat ban.
        var hop = ytSau(doc, "ytcp-video-share-dialog, #share-url, #close-button");
        if (hop && vis(hop)) {
          report("post-done", "hop chia se hien ra (video da duoc xuat ban)");
          buoc = "dung";
          return;
        }
        if (Date.now() - tienDoLuc > 6 * 60 * 1000) {
          report("publish-timeout", "da bam Xuat ban nhung khong thay xac nhan | " + dumpStudio(doc));
          buoc = "dung";
        }
        return;
      }
    }
  }

  /* ---- SOI (chi doc): dump cau truc Studio de chinh selector --------------------- */
  function soi(win, doc, cmd) {
    if (cmd.bam_het && !soi._daBam) {
      // Bam LAN LUOT moi nut "Show more" thay duoc (toi da 3) roi soi lai: chua ro nut nao
      // moi la nut mo phan chi tiet (co o THE TAG).
      soi._daBam = true;
      var bs0 = ytSauHet(doc, 'button,[role="button"],ytcp-button,tp-yt-paper-button');
      var ds0 = [];
      for (var q0 = 0; q0 < bs0.length && ds0.length < 3; q0++) {
        var c0 = chu(bs0[q0]);
        if (c0 && c0.length < 40 && vis(bs0[q0]) && /^show more|^hiện thêm|^xem thêm/i.test(c0)) {
          ds0.push(bs0[q0]);
        }
      }
      report("seen", "thay " + ds0.length + " nut 'Show more' — bam lan luot");
      (function bamTiep(i) {
        if (i >= ds0.length) {
          win.setTimeout(function () { soi(win, doc, cmd); }, 2000);
          return;
        }
        clickReal(win, ds0[i]);
        // Bam ca phan tu BEN TRONG (ytcp-button boc mot <button> that trong shadow root).
        var sh0 = goc_shadow(ds0[i]);
        var trong = sh0 ? sh0.querySelector('button,[role="button"]') : null;
        if (trong) { clickReal(win, trong); }
        win.setTimeout(function () { bamTiep(i + 1); }, 1500);
      })(0);
      return;
    }
    if (cmd.bam_them && !soi._daBam) {
      // Bam "Show more" roi SOI LAI o nhip sau: o the tag chi hien sau khi mo rong.
      soi._daBam = true;
      var mo = nutHienThem(doc);
      if (mo) {
        clickReal(win, mo);
        report("seen", "da bam 'Show more' — soi lai sau 2.5s");
        win.setTimeout(function () { soi(win, doc, cmd); }, 2500);
        return;
      }
      report("seen", "khong thay nut 'Show more'");
    }
    var ghi = [];
    ghi.push("url=" + String(win.location.href));
    var ff = ytSauHet(doc, 'input[type="file"]');
    ghi.push("so_input_file=" + ff.length);
    for (var i = 0; i < ff.length && i < 3; i++) {
      ghi.push("  input[" + i + "] id=" + (ff[i].id || "-") + " accept="
               + (ff[i].getAttribute("accept") || "-") + " multiple=" + (ff[i].multiple ? 1 : 0));
    }
    ghi.push("create-icon=" + (nutTheoId(doc, "create-icon") ? 1 : 0)
             + " hop_chao=" + (ytSauHien(doc, "#dismiss-button").length ? 1 : 0));
    ghi.push("o_tieu_de=" + (oTieuDe(doc) ? 1 : 0) + " o_mo_ta=" + (oMoTa(doc) ? 1 : 0));
    ghi.push("tieu_de_hien: \"" + (oTieuDe(doc) ? chu(oTieuDe(doc)).slice(0, 100) : "") + "\"");
    ghi.push("mo_ta_hien: \"" + (oMoTa(doc) ? chu(oMoTa(doc)).slice(0, 260) : "") + "\"");
    ghi.push("radio_tre_em=" + (radioTreEm(doc, false) ? 1 : 0)
             + " radio_PUBLIC=" + (radioRiengTu(doc, "PUBLIC") ? 1 : 0));
    ghi.push("o_chon_anh=" + (oChonAnh(doc) ? 1 : 0) + " o_tag=" + (oTag(doc) ? 1 : 0)
             + " hien_them=" + (nutHienThem(doc) ? 1 : 0));
    ghi.push("next=" + (nutTheoId(doc, "next-button") ? 1 : 0)
             + " done=" + (nutTheoId(doc, "done-button") ? 1 : 0));
    ghi.push("buoc=" + buocHienTai(doc));
    ghi.push("id: " + dumpStudio(doc));
    var ins = ytSauHet(doc, "input,textarea"), mo_ta_in = [];
    for (var z = 0; z < ins.length && mo_ta_in.length < 14; z++) {
      if (!vis(ins[z])) { continue; }
      mo_ta_in.push("#" + (ins[z].id || "-") + "[" + (ins[z].getAttribute("type") || "text") + "]"
                    + " aria=" + String(ins[z].getAttribute("aria-label") || "-").slice(0, 28)
                    + " ph=" + String(ins[z].getAttribute("placeholder") || "-").slice(0, 24));
    }
    ghi.push("input hien: " + mo_ta_in.join(" ; "));
    var tg = ytSauHet(doc, "[id]"), co_tag = [];
    for (var y = 0; y < tg.length && co_tag.length < 12; y++) {
      var idy = (tg[y].id || "") + "";
      if (/tag/i.test(idy)) {
        co_tag.push("#" + idy + "<" + tg[y].tagName.toLowerCase() + ">"
                    + (vis(tg[y]) ? "" : "(an)"));
      }
    }
    var tt0 = chuTrang(doc).replace(/\s+/g, " ");
    var vt0 = tt0.search(/tags|thẻ|the tag/i);
    ghi.push("chu co 'tag'? " + (vt0 >= 0 ? "CO o vi tri " + vt0 + ": ..." + tt0.slice(Math.max(0, vt0 - 120), vt0 + 260) : "KHONG CO trong chu trang"));
    ghi.push("id co 'tag': " + (co_tag.join(" ; ") || "KHONG CO"));
    var t9 = chuTrang(doc).replace(/\s+/g, " ");
    var v9 = t9.search(/audience|khán giả|made for kids|dành cho trẻ em/i);
    ghi.push("chu tu muc 'Khan gia': " + t9.slice(v9 >= 0 ? v9 : 0, (v9 >= 0 ? v9 : 0) + 1300));
    var nut9 = [], bs = ytSauHet(doc, 'button,[role="button"],ytcp-button,tp-yt-paper-button');
    for (var q = 0; q < bs.length && nut9.length < 16; q++) {
      var c9 = chu(bs[q]);
      if (c9 && c9.length < 40 && vis(bs[q]) && /more|thêm|them|less|ít/i.test(c9)) {
        nut9.push("\"" + c9 + "\"#" + (bs[q].id || "-"));
      }
    }
    ghi.push("nut 'more': " + (nut9.join(" ; ") || "KHONG CO"));
    report("done", ghi.join(" || "));
  }

  /** CHI DOC: liet ke video tren trang Noi dung (xac minh doc lap video da len chua). */
  function lietKe(win, doc) {
    var ra = ["url=" + String(win.location.href)];
    var ds = ytSauHet(doc, "#video-title, a#video-title");
    var dem = 0;
    for (var i = 0; i < ds.length && dem < 12; i++) {
      var t = chu(ds[i]);
      if (!t) { continue; }
      // Hang video: lay them cot che do hien thi ben canh (Public/Draft/...).
      var hang = ds[i];
      for (var k = 0; k < 6 && hang; k++) { hang = hang.parentNode; if (hang && /ROW/i.test(hang.tagName || "")) { break; } }
      var ct = hang ? chu(hang).slice(0, 160) : "";
      ra.push("[" + dem + "] " + t.slice(0, 80) + (ct ? "  ||  " + ct : ""));
      dem += 1;
    }
    ra.push("tong_tim_thay=" + ds.length);
    var ids = [], la = ytSauHet(doc, "a[href]");
    for (var z = 0; z < la.length && ids.length < 6; z++) {
      var m = /\/video\/([A-Za-z0-9_-]{6,})\//.exec(la[z].getAttribute("href") || "");
      if (m && ids.indexOf(m[1]) < 0) { ids.push(m[1]); }
    }
    ra.push("id_video=" + ids.join(","));
    // Du phong (bang Noi dung nam rat sau trong shadow root): dump CHU cua trang.
    // Chu bang chua tieu de + che do hien thi + so view -> du de xac minh video da len.
    var t = chuTrang(doc).replace(/\s+/g, " ");
    var k = t.search(/Uploads|Videos|Noi dung|Nội dung/);
    ra.push("chu_trang: " + t.slice(k > 0 ? k : 0, (k > 0 ? k : 0) + 1500));
    report("done", ra.join(" || "));
  }

  function onPage(win) {
    var cmd = getCommand();
    if (!cmd) { return; }
    if (cmd.action === "ytlist") {
      var href0 = String(win.location.href || "");
      if (!/studio\.youtube\.com/.test(href0)) { return; }
      if (DANG_CHAY) { return; }
      DANG_CHAY = true;
      var d0 = win.document;
      // Cho bang video render (Studio nap dan) roi moi dump.
      var n = 0;
      (function doi2() {
        n += 1;
        if (ytSauHet(d0, "#video-title").length > 0 || n > 25) { lietKe(win, d0); return; }
        win.setTimeout(doi2, 1000);
      })();
      return;
    }
    if (cmd.action !== "ytpost" && cmd.action !== "ytprobe") { return; }
    var href = String(win.location.href || "");
    if (!/^https?:/.test(href)) { return; }                  // bo qua about:, moz-extension:
    var doc = win.document;
    var man = ytPhanLoai(href, chuTrang(doc).slice(0, 3000));
    if (!man) { return; }
    if (man === "yt-login") {
      report("yt-login", href.slice(0, 140));
      return;
    }
    if (DANG_CHAY) { return; }
    DANG_CHAY = true;
    var cho = 0;
    (function doi() {
      cho += 1;
      // Cho Studio dung xong (co o chon file HOAC nut CREATE) roi moi lam viec.
      if (oChonFile(doc) || nutTheoId(doc, "create-icon") || cho > 40) {
        if (cmd.action === "ytprobe") { win.setTimeout(function () { soi(win, doc, cmd); }, 1500); }
        else { chayDang(win, doc, cmd); }
        return;
      }
      win.setTimeout(doi, 1000);
    })();
  }

  var observer = {
    observe: function (subject, topic) {
      if (topic !== "content-document-global-created") { return; }
      var win = subject;
      try {
        if (win.top !== win) { return; }
        win.addEventListener("load", function onload() {
          win.removeEventListener("load", onload);
          onPage(win);
        }, { once: true });
      } catch (e) {}
    },
  };
  Services.obs.addObserver(observer, "content-document-global-created");
}
