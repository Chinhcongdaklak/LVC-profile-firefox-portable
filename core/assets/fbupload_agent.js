/* Process script: dieu khien trang business.facebook.com de dang video.
 *
 * Chay trong TIEN TRINH NOI DUNG, cham thang vao document cua trang. KHONG dung
 * Cu.Sandbox: kieu do da lam crash tab hai lan truoc day khi gan doi tuong co
 * dac quyen vao sandbox mang nguyen tac cua trang.
 *
 * File nay KHONG doc ghi file. Tien trinh noi dung bi ho dieu hanh chan ghi dia
 * (da do: agent chay nhung khong file nao duoc tao). Moi viec doc ghi deu nho
 * tien trinh cha lam ho, noi chuyen qua message manager:
 *
 *   sendSyncMessage("qlfp:cmd")        -> cha doc <profile>/qlfp-upload.json
 *   sendAsyncMessage("qlfp:report")    -> cha ghi <profile>/qlfp-upload-result.json
 *   sendAsyncMessage("qlfp:dump")      -> cha ghi <profile>/qlfp-upload-dump.json
 *
 * Buoc chon file khong lam o day duoc: trang web mo hop thoai cua he dieu hanh,
 * JavaScript khong voi toi. Agent chi bam cho hop thoai hien ra roi bao cho tool
 * biet; tool go duong dan vao (xem core/winfile.py).
 */
"use strict";

// Trong tien trinh cha khong co ham nay -> khong lam gi ca.
if (typeof sendAsyncMessage === "function") {

  var lines = [];

  function report(state, detail) {
    lines.push(state + (detail ? ": " + detail : ""));
    try {
      sendAsyncMessage("qlfp:report", {
        state: state,
        detail: detail || "",
        log: lines.slice(-40),
      });
    } catch (e) {}
  }

  function getCommand() {
    try {
      var answer = sendSyncMessage("qlfp:cmd");
      var raw = answer && answer.length ? answer[0] : "";
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  /* ------------------------------------------------------- doc trang co gi */

  function textOf(el) {
    var t = "";
    try { t = (el.innerText || el.textContent || "").trim(); } catch (e) {}
    return t.replace(/\s+/g, " ").slice(0, 60);
  }

  function describe(el) {
    function attr(n) {
      try { return el.getAttribute(n) || ""; } catch (e) { return ""; }
    }
    return {
      tag: el.tagName ? el.tagName.toLowerCase() : "?",
      type: attr("type"),
      role: attr("role"),
      aria: attr("aria-label").slice(0, 80),
      accept: attr("accept").slice(0, 60),
      placeholder: attr("placeholder").slice(0, 60),
      value: (function () { try { return (el.value || "").slice(0, 60); } catch (e) { return ""; } })(),
      editable: attr("contenteditable"),
      text: textOf(el),
      shown: !!el.offsetParent,
    };
  }

  /** Do KY: moi thuoc tinh cua tung nut, de tim dau hieu khong phu thuoc ngon ngu. */
  function dumpButtons(doc) {
    var list = [];
    try {
      list = Array.prototype.slice.call(doc.querySelectorAll('[role="button"], button'));
    } catch (e) {}
    var ra = [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (!el.offsetParent) { continue; }
      var attrs = {};
      try {
        for (var j = 0; j < el.attributes.length; j++) {
          var a = el.attributes[j];
          attrs[a.name] = String(a.value).slice(0, 90);
        }
      } catch (e) {}
      var to = [];
      try {
        var p = el.parentElement, n = 0;
        while (p && n < 14) {
          var pa = {};
          if (p.getAttribute("role")) { pa.role = p.getAttribute("role"); }
          if (p.getAttribute("data-testid")) { pa.testid = p.getAttribute("data-testid"); }
          if (p.getAttribute("aria-label")) { pa.aria = p.getAttribute("aria-label").slice(0, 50); }
          to.push(pa);
          p = p.parentElement; n += 1;
        }
      } catch (e) {}
      var r = { text: textOf(el), attrs: attrs, cha: to };
      try {
        var box = el.getBoundingClientRect();
        r.box = [Math.round(box.left), Math.round(box.top),
                 Math.round(box.width), Math.round(box.height)];
        var st = el.ownerDocument.defaultView.getComputedStyle(el);
        r.bg = st.backgroundColor;
      } catch (e) {}
      ra.push(r);
    }
    var files = [];
    try {
      var fi = doc.querySelectorAll('input[type="file"]');
      for (var k = 0; k < fi.length; k++) {
        files.push({ accept: fi[k].getAttribute("accept") || "",
                     multiple: fi[k].hasAttribute("multiple") });
      }
    } catch (e) {}
    try {
      sendAsyncMessage("qlfp:dump",
                       { url: doc.location.href, buttons: ra, files: files });
    } catch (e) {}
    report("dumped", ra.length + " nút, " + files.length + " ô chọn file");
  }

  function dumpPage(doc, im) {
    var out = { url: doc.location ? doc.location.href : "", found: {} };
    var groups = {
      fileInputs: 'input[type="file"]',
      buttons: '[role="button"], button',
      editables: '[contenteditable="true"], textarea',
      texts: 'input[type="text"], input:not([type])',
    };
    for (var key in groups) {
      var list = [];
      try {
        list = Array.prototype.slice.call(doc.querySelectorAll(groups[key]));
      } catch (e) {}
      out.found[key] = list.slice(0, 150).map(describe);
    }
    try { sendAsyncMessage("qlfp:dump", out); } catch (e) {}
    if (im) { return; }              // dump kem theo loi: khong de len trang thai
    report("dumped", out.found.fileInputs.length + " ô chọn file, "
      + out.found.buttons.length + " nút");
  }

  /* ------------------------------------------------------------- dang video */

  function findFileInput(doc) {
    var list = [];
    try {
      list = Array.prototype.slice.call(doc.querySelectorAll('input[type="file"]'));
    } catch (e) { return null; }
    for (var i = 0; i < list.length; i++) {
      var accept = (list[i].getAttribute("accept") || "").toLowerCase();
      if (accept.indexOf("video") !== -1) { return list[i]; }
    }
    return list[0] || null;
  }

  /** Nhet video vao o chon file, khong qua hop thoai he dieu hanh.
   *
   * Da thu duong "bam nut roi go duong dan vao hop thoai Open cua Windows":
   * bap benh -- hop thoai luc hien luc khong, nam o mot tien trinh rieng, va
   * WM_SETTEXT vao o nhap thi hop thoai khong ghi nhan.
   *
   * Duong nay chac chan hon: nho tien trinh CHA doc file (tien trinh noi dung bi
   * chan doc dia) roi dung mozSetFileArray gan vao o chon -- trang thay y het
   * nhu nguoi dung tu chon file. Day cung la cach WebDriver cua Firefox nap file.
   */
  /** Dung File do cha gui sang thanh File dung duoc cho o chon file.
   *
   * Cha co the gui MOT TRONG HAI:
   *   * ``data.file`` -- File tao tu DUONG DAN (do dia do, khong gioi han dung luong);
   *   * ``data.bytes`` -- noi dung nhi phan (duong du phong, toi da 400 MB).
   */
  function fileTuTin(win, data, mime) {
    if (data.file) { return data.file; }
    var bytes = Cu.cloneInto(data.bytes, win);
    return new win.File([bytes], data.name || "file",
                        { type: mime || "application/octet-stream" });
  }

  /** Gan danh sach File vao o chon. mozSetFileArray nhan File cua tien trinh cha;
   *  DataTransfer thi khong, nen uu tien mozSetFileArray.
   */
  function ganFile(win, input, files) {
    if (typeof input.mozSetFileArray === "function") {
      input.mozSetFileArray(files);
    } else {
      var dt = new win.DataTransfer();
      files.forEach(function (f) { dt.items.add(f); });
      input.files = dt.files;
    }
    input.dispatchEvent(new win.Event("input", { bubbles: true }));
    input.dispatchEvent(new win.Event("change", { bubbles: true }));
  }

  function attachFile(win, input, path, done, cmd_mime) {
    var xong = false;

    function nhan(msg) {
      if (xong) { return; }
      xong = true;
      try { removeMessageListener("qlfp:file", nhan); } catch (e) {}
      var data = msg.data || {};
      if (!data.ok) {
        report("file-read-error", data.error || "không đọc được file");
        done(false);
        return;
      }
      try {
        var file = fileTuTin(win, data, cmd_mime);
        ganFile(win, input, [file]);
        report("file-attached", file.name + " (" + file.size + " byte, "
               + (data.cach || "?") + ")");
        try {
          done(true, file);          // dua File ra: duong du phong keo-tha can no
        } catch (e2) {
          report("after-attach-error", String(e2));
        }
      } catch (e) {
        report("attach-error", String(e));
        done(false);
      }
    }

    try {
      addMessageListener("qlfp:file", nhan);
      sendAsyncMessage("qlfp:needfile", { path: path });
    } catch (e) {
      report("ask-file-error", String(e));
      done(false);
    }
  }

  /** Dinh NHIEU file (anh + video) vao mot o chon: doc tuan tu tung file (kenh
   * qlfp:file khong co id nen khong the doc song song), gom lai roi mozSetFileArray
   * mot lan -> thu FB co nhan anh + video chung mot bai khong. ``items`` la mang
   * {path, mime}. done(ok, soFile).
   */
  function attachMany(win, input, items, done) {
    var files = [], k = 0;
    function next() {
      if (k >= items.length) {
        if (!files.length) { done(false, 0); return; }
        try {
          ganFile(win, input, files);
          report("files-attached", files.length + " file");
          done(true, files.length);
        } catch (e) { report("attach-error", String(e)); done(false, 0); }
        return;
      }
      var it = items[k++];
      var got = false;
      function nhan(msg) {
        if (got) { return; } got = true;
        try { removeMessageListener("qlfp:file", nhan); } catch (e) {}
        var data = msg.data || {};
        if (data.ok) {
          try {
            files.push(fileTuTin(win, data, it.mime));
          } catch (e) { report("attach-error", String(e)); }
        } else {
          report("file-read-error", data.error || ("không đọc được " + it.path));
        }
        next();
      }
      try { addMessageListener("qlfp:file", nhan); sendAsyncMessage("qlfp:needfile", { path: it.path }); }
      catch (e) { report("ask-file-error", String(e)); next(); }
    }
    next();
  }

  /** O soan chu cua BAI VIET.
   *
   * Truyen ``hop`` (the hop thoai) thi chi lay o nam TRONG khung hop thoai. Bat
   * buoc phai loc nhu vay tren trang nhom: trang tin cua nhom day o binh luan
   * cung la contenteditable, lay o dau tien la go vao o binh luan cua mot bai
   * nguoi khac -- da do that: chu vao dung o binh luan, bai dang len trong khong.
   */
  function captionBox(doc, win, hop) {
    var list = [];
    try {
      list = Array.prototype.slice.call(
        doc.querySelectorAll('[contenteditable="true"], textarea'));
    } catch (e) { return null; }

    var khung = null;
    if (hop) {
      try { khung = hop.getBoundingClientRect(); } catch (e) {}
    }

    var ung = [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (!el.offsetParent) { continue; }
      var box = null;
      try { box = el.getBoundingClientRect(); } catch (e) { continue; }
      if (khung) {
        if (box.left < khung.left - 4 || box.right > khung.right + 4) { continue; }
        if (box.top < khung.top - 4 || box.bottom > khung.bottom + 4) { continue; }
      }
      ung.push({ el: el, top: box.top, left: box.left,
                 trong: boxText(el).trim() === "" });
    }
    if (!ung.length) { return null; }
    if (khung) {
      ung.sort(function (a, b) { return a.top - b.top; });   // tren cung truoc
      return ung[0].el;
    }
    // Fanpage (bulk composer): ban moi (9/2026, giao tung dot A/B) co them cot
    // "Tieu de" TRUOC cot "Mo ta" -- lay o dau tien la go nham vao Tieu de,
    // Mo ta trong tron (da gap tren acc giao dien tieng Viet). Chon o con
    // TRONG (Tieu de thi Facebook dien san ten file), trong so do lay o nam
    // PHAI nhat vi cot Mo ta dung sau cot Tieu de. Ban cu chi co mot o -> van
    // ra dung o do.
    var trong = ung.filter(function (x) { return x.trong; });
    var chon = (trong.length ? trong : ung);
    chon.sort(function (a, b) { return b.left - a.left; });
    return chon[0].el;
  }

  /** DANH SACH o soan ung vien, xep hang: o kha nang la "Mo ta" dung TRUOC.
   *
   * Truoc day chi lay DUNG MOT o -> page nao bay composer khac (cot Tieu de/Mo ta doi cho,
   * o chua kich hoat) la go vao o chet roi bao caption-failed du video da len
   * (nguoi dung bao 02/10). Gio go hong o nay thi sang o KE TIEP.
   */
  function captionUngVien(doc, win, hop) {
    var list = [];
    try {
      list = Array.prototype.slice.call(
        doc.querySelectorAll('[contenteditable="true"], textarea'));
    } catch (e) { return []; }
    var khung = null;
    if (hop) { try { khung = hop.getBoundingClientRect(); } catch (e) {} }

    var ung = [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i], box = null;
      if (!el.offsetParent) { continue; }
      try { box = el.getBoundingClientRect(); } catch (e) { continue; }
      if (box.width < 40 || box.height < 12) { continue; }
      if (khung) {
        if (box.left < khung.left - 4 || box.right > khung.right + 4) { continue; }
        if (box.top < khung.top - 4 || box.bottom > khung.bottom + 4) { continue; }
      }
      ung.push({ el: el, top: box.top, left: box.left, rong: box.width, cao: box.height,
                 trong: boxText(el).trim() === "" });
    }
    // BO UNG VIEN LONG NHAU: o ngoai chua o trong thi go vao o ngoai chu cung roi vao o
    // trong -> tinh la HAI o, go hai lan, mo ta bi LAP (nguoi dung bao 03/10). Giu o TRONG CUNG.
    ung = ung.filter(function (a) {
        for (var j = 0; j < ung.length; j++) {
          if (ung[j].el === a.el) { continue; }
          try {
            if (a.el.contains(ung[j].el)) { return false; }
          } catch (e) {}
        }
        return true;
      });
    // O TRONG truoc (o "Tieu de" thuong da co san ten file), trong do o PHAI nhat truoc
    // (cot Mo ta dung sau cot Tieu de); con lai xep sau de con duong thu tiep.
    ung.sort(function (a, b) {
      if (a.trong !== b.trong) { return a.trong ? -1 : 1; }
      return b.left - a.left;
    });
    return ung;
  }

  /** Mo ta mot o soan de ghi vao nhat ky (chan doan khi go nham o). */
  function taOSoan(x) {
    var el = x.el;
    var nhan = "";
    try {
      nhan = el.getAttribute("aria-label") || el.getAttribute("placeholder")
          || el.getAttribute("data-testid") || "";
    } catch (e) {}
    return (el.tagName || "?").toLowerCase() + (nhan ? "[" + nhan.slice(0, 30) + "]" : "")
        + " " + Math.round(x.rong) + "x" + Math.round(x.cao)
        + " @" + Math.round(x.left) + "," + Math.round(x.top)
        + (x.trong ? " (trống)" : " (có sẵn chữ)");
  }

  function boxText(box) {
    try {
      if (box.tagName.toLowerCase() === "textarea") { return box.value || ""; }
      return (box.innerText || box.textContent || "");
    } catch (e) { return ""; }
  }

  /** O soan co phai DraftJS (composer CU cua Facebook) khong.
   *  Dau hieu: div[data-contents="true"] / [data-editor] / class _5rpu ben trong. */
  function laDraft(box) {
    try {
      return !!(box.querySelector('[data-contents="true"], [data-block="true"]')
                || (box.className || "").indexOf("_5rpu") !== -1
                || box.getAttribute("data-editor"));
    } catch (e) { return false; }
  }

  /** Cho caret vao dung cho trong o soan DraftJS.
   *
   * Cau truc THAT (nguoi dung gui 02/10, o dang RONG):
   *   div[contenteditable] > div[data-contents] > div[data-block] > div._1mf
   *     > span[data-offset-key] > <br data-text="true">
   * Dat caret o cuoi div GOC, hay "sau" the <br>, thi DraftJS bo qua -> phai nam TRONG
   * span[data-offset-key]: co chu thi cuoi text node, rong (chi co <br>) thi offset 0 cua span.
   */
  function diemCaret(box) {
    var span = null;
    try {
      var ds = box.querySelectorAll('span[data-offset-key]');
      span = ds.length ? ds[ds.length - 1] : null;
    } catch (e) {}
    var goc = span || box;
    var n = goc;
    for (var b = 0; b < 12; b++) {
      if (!n || !n.lastChild) { break; }
      if (n.lastChild.nodeType === 1 && (n.lastChild.tagName || "").toLowerCase() === "br") {
        return { node: n, offset: 0 };          // o RONG: caret nam TRONG span, truoc <br>
      }
      n = n.lastChild;
    }
    if (n && n.nodeType === 3) { return { node: n, offset: n.length }; }
    return { node: goc, offset: (goc.childNodes ? goc.childNodes.length : 0) };
  }

  /** Dat con tro vao cuoi o soan. execCommand chi an khi vung chon nam trong o. */
  function focusEnd(win, doc, box) {
    try {
      box.focus();
      if (box.tagName.toLowerCase() === "textarea") {
        box.setSelectionRange(box.value.length, box.value.length);
        return;
      }
      var range = doc.createRange();
      try {
        var d = diemCaret(box);
        range.setStart(d.node, d.offset);
        range.setEnd(d.node, d.offset);
      } catch (e) {
        range.selectNodeContents(box);
        range.collapse(false);
      }
      var sel = win.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    } catch (e) {}
  }

  /** XOA SACH o soan truoc khi go.
   *
   * Business Suite TU DIEN san o "Mô tả" = TEN FILE. Truoc day agent dat con tro o CUOI
   * roi chen them caption (cung la ten file) -> mo ta thanh HAI LAN -> Facebook bao
   * "Một bài viết của bạn có tiêu đề quá dài" va khoa nut Dang, trong khi KEO TAY cung
   * video do thi dang binh thuong (nguoi dung bao 01/10).
   */
  /** CLICK THAT vao o soan roi dat con tro: o Lexical cua Facebook co khi chi "song"
   *  sau khi duoc BAM — focus() suong thi go vao khong an (page bay composer khac, 02/10). */
  function bamVaoO(win, box) {
    try {
      var r = box.getBoundingClientRect();
      var cx = r.left + Math.min(40, r.width / 2), cy = r.top + r.height / 2;
      var handle = null;
      try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
      try {
        ["pointerdown", "mousedown", "pointerup", "mouseup", "click"].forEach(function (t) {
          var E = (t.indexOf("pointer") === 0) ? win.PointerEvent : win.MouseEvent;
          box.dispatchEvent(new E(t, { bubbles: true, cancelable: true,
                                       clientX: cx, clientY: cy, button: 0 }));
        });
      } finally {
        if (handle) { try { handle.destruct(); } catch (e) {} }
      }
      box.focus();
    } catch (e) {}
  }

  /** O THAT se nhan chu: su kien dispatch tren o boc se NOI LEN editor that (DraftJS /
   *  Lexical mount o phan tu khac). Lay ``activeElement`` neu no soan duoc, khong thi lay o boc.
   */
  function oThat(win, doc, box) {
    try {
      var a = doc.activeElement;
      if (a && a !== box && a.offsetParent) {
        var the = (a.tagName || "").toLowerCase();
        if (the === "textarea" || the === "input"
            || a.getAttribute("contenteditable") === "true") {
          return a;
        }
      }
    } catch (e) {}
    return box;
  }

  function xoaOSoan(win, doc, box) {
    var the = (box.tagName || "").toLowerCase();
    try {
      box.focus();
      if (the === "textarea" || the === "input") {
        box.value = "";
        box.dispatchEvent(new win.Event("input", { bubbles: true }));
        return;
      }
      var range = doc.createRange();
      range.selectNodeContents(box);
      var sel = win.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      try { doc.execCommand("delete", false, null); } catch (e) {}
      if (boxText(box).trim()) {
        // O soan Lexical bo qua execCommand -> ban su kien xoa that.
        box.dispatchEvent(new win.InputEvent("beforeinput", {
          bubbles: true, cancelable: true, inputType: "deleteContentBackward" }));
        box.dispatchEvent(new win.InputEvent("input", {
          bubbles: true, inputType: "deleteContentBackward" }));
      }
    } catch (e) {}
  }

  /** Xoa SACH moi o ung vien VA o that dang nhan chu -- goi truoc khi go lai / doi o,
   *  khong thi chu cu con nam lai va mo ta bi LAP.
   */
  function xoaHetOSoan(win, doc, ds) {
    for (var i = 0; i < (ds || []).length; i++) {
      try { xoaOSoan(win, doc, ds[i].el); } catch (e) {}
    }
    try {
      var that = oThat(win, doc, null);
      if (that) { xoaOSoan(win, doc, that); }
    } catch (e) {}
  }

  /** ``moc`` xuat hien may lan trong CA KHUNG (hop thoai, khong co thi ca trang).
   *
   * Phai dem o khung chu khong chi trong mot o: chu co the da roi sang o khac (o long
   * nhau / Facebook soi guong) ma dem trong o nay van thay 1 lan.
   */
  function demLapKhung(doc, hop, moc) {
    var goc = hop || (doc && doc.body);
    var chu = "";
    try { chu = (goc && goc.innerText) || ""; } catch (e) { return 0; }
    chu = chu.replace(/\s+/g, " ").trim();
    if (!moc) { return 0; }
    var so = 0, i = chu.indexOf(moc);
    while (i !== -1) { so += 1; i = chu.indexOf(moc, i + moc.length); }
    return so;
  }

  /** Doan ``moc`` xuat hien may lan trong o -- 2 lan tro len la mo ta bi LAP. */
  function demLap(box, moc) {
    var chu = boxText(box).replace(/\s+/g, " ").trim();
    if (!moc) { return 0; }
    var so = 0, i = chu.indexOf(moc);
    while (i !== -1) { so += 1; i = chu.indexOf(moc, i + moc.length); }
    return so;
  }

  /** Cach 1: go tung chu qua execCommand -- o soan cua Facebook (Lexical) nhan. */
  function typeInsert(win, doc, box, caption) {
    focusEnd(win, doc, box);
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try {
      if (box.tagName.toLowerCase() === "textarea") {
        box.value = caption;
        box.dispatchEvent(new win.Event("input", { bubbles: true }));
      } else {
        doc.execCommand("insertText", false, caption);
      }
    } catch (e) {
      report("caption-error", String(e));
    } finally {
      if (handle) { try { handle.destruct(); } catch (e) {} }
    }
  }

  /** Cach 2: InputEvent beforeinput+input -- Lexical (o soan FB) NGHE beforeinput.
   * execCommand hay tra TRUE ma o van trong, cach nay moi that su lam chu vao. */
  function beforeInputInsert(win, doc, box, caption) {
    focusEnd(win, doc, box);
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try {
      box.dispatchEvent(new win.InputEvent("beforeinput", {
        bubbles: true, cancelable: true, inputType: "insertText", data: caption }));
      box.dispatchEvent(new win.InputEvent("input", {
        bubbles: true, inputType: "insertText", data: caption }));
    } catch (e) {
      report("caption-error", String(e));
    } finally {
      if (handle) { try { handle.destruct(); } catch (e) {} }
    }
  }

  /** Cach 3: gia lam thao tac dan. Dung khi cach tren khong an. */
  function pasteInsert(win, doc, box, caption) {
    focusEnd(win, doc, box);
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try {
      var dt = new win.DataTransfer();
      dt.setData("text/plain", caption);
      box.dispatchEvent(new win.ClipboardEvent("paste", {
        bubbles: true, cancelable: true, clipboardData: dt,
      }));
    } catch (e) {
      report("caption-error", String(e));
    } finally {
      if (handle) { try { handle.destruct(); } catch (e) {} }
    }
  }

  /** Cach 4: go TUNG KY TU (keydown + beforeinput + input + keyup). Cham nhung chac. */
  function perCharInsert(win, doc, box, caption) {
    focusEnd(win, doc, box);
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try {
      for (var i = 0; i < caption.length; i++) {
        var c = caption[i];
        box.dispatchEvent(new win.KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: c }));
        box.dispatchEvent(new win.InputEvent("beforeinput", { bubbles: true, cancelable: true, inputType: "insertText", data: c }));
        box.dispatchEvent(new win.InputEvent("input", { bubbles: true, inputType: "insertText", data: c }));
        box.dispatchEvent(new win.KeyboardEvent("keyup", { bubbles: true, cancelable: true, key: c }));
      }
    } catch (e) {
      report("caption-error", String(e));
    } finally {
      if (handle) { try { handle.destruct(); } catch (e) {} }
    }
  }

  /** Dien mo ta, ROI DOC LAI xem chu co that su nam trong o khong.
   *
   * Truoc day chi goi execCommand roi bao "xong": bai dang len khong co mot chu
   * nao ma nhat ky van bao dien duoc. O soan cua Facebook do Lexical dieu khien,
   * khong phai lam gi cung an, nen phai kiem lai va thu cach khac neu truot.
   */
  /** Cach 5 (DraftJS tren Firefox): go TUNG KY TU bang KEYPRESS.
   *
   * React dung cho composer cu (DraftJS) KHONG dung `beforeinput` tren Firefox — no dung
   * `keypress` (charCode) de dung ra su kien nhap. Thieu keypress thi go kieu gi o cung
   * tron tro (dung lo loi "go vao nhung o van trong" tren page bay composer cu, 02/10).
   */
  function keypressInsert(win, doc, box, caption) {
    focusEnd(win, doc, box);
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try {
      for (var i = 0; i < caption.length; i++) {
        var c = caption[i], ma = caption.charCodeAt(i);
        box.dispatchEvent(new win.KeyboardEvent("keydown", {
          bubbles: true, cancelable: true, key: c, charCode: 0, keyCode: 229, which: 229 }));
        box.dispatchEvent(new win.KeyboardEvent("keypress", {
          bubbles: true, cancelable: true, key: c, charCode: ma, keyCode: ma, which: ma }));
        box.dispatchEvent(new win.InputEvent("beforeinput", {
          bubbles: true, cancelable: true, inputType: "insertText", data: c }));
        box.dispatchEvent(new win.InputEvent("input", {
          bubbles: true, inputType: "insertText", data: c }));
        box.dispatchEvent(new win.KeyboardEvent("keyup", {
          bubbles: true, cancelable: true, key: c, charCode: 0, keyCode: ma, which: ma }));
      }
    } catch (e) {
      report("caption-error", String(e));
    } finally {
      if (handle) { try { handle.destruct(); } catch (e) {} }
    }
  }

  function fillCaption(win, doc, caption, done, hop) {
    if (!caption) { done(false, "không có mô tả"); return; }

    // 4 cach go, XAC MINH sau moi cach (o soan Lexical hay bo qua execCommand -> phai doi cach):
    // execCommand -> beforeinput -> paste -> tung ky tu (giong o soan Messenger da fix).
    // Go hong HET 4 cach o mot o -> sang O KE TIEP (page bay composer khac: cot Tieu de/Mo ta
    // doi cho, hoac o chua kich hoat -> truoc day ket o mot o roi bao caption-failed oan).
    var cach = [typeInsert, beforeInputInsert, pasteInsert, perCharInsert, keypressInsert];
    var ten = ["execCommand", "beforeinput", "paste", "tung-ky-tu", "keypress"];
    var muon = caption.replace(/\s+/g, " ").trim();
    var mocKiem = muon.slice(0, Math.min(20, muon.length));
    var vong = 0, daTaUngVien = false;

    function coChu(box) {
      if (boxText(box).replace(/\s+/g, " ").trim().indexOf(mocKiem) !== -1) { return true; }
      // Chu co the da roi vao O THAT (editor long ben trong) -> do tren CA KHUNG.
      // Khong do thi lan nao cung tuong "o van trong" -> go lai -> mo ta bi LAP.
      return demLapKhung(doc, hop, mocKiem) >= 1;
    }

    function thu() {
      var ds = captionUngVien(doc, win, hop);
      if (!ds.length && vong >= 3) { ds = captionUngVien(doc, win, null); }
      if (!ds.length) {
        if (vong < 10) { vong += 1; win.setTimeout(thu, 1000); return; }
        done(false, "không thấy ô soạn chữ");
        return;
      }
      if (!daTaUngVien) {
        daTaUngVien = true;
        report("caption-o-soan", ds.length + " ô ứng viên: "
               + ds.slice(0, 4).map(taOSoan).join(" | "));
      }

      var oi = 0;

      function moO() {
        if (oi >= ds.length) {
          vong += 1;
          if (vong < 3) { win.setTimeout(thu, 1200); return; }
          done(false, "gõ vào nhưng ô vẫn trống sau " + ds.length + " ô × 4 cách (ô cuối còn: "
               + boxText(ds[ds.length - 1].el).replace(/\s+/g, " ").slice(0, 40) + ")");
          return;
        }
        var box = ds[oi].el;
        var i = 0;
        // Sang o MOI -> xoa het cac o truoc da, khong thi chu cu con nam lai -> mo ta lap.
        if (oi > 0) { xoaHetOSoan(win, doc, ds); }
        // O DraftJS (composer CU cua Facebook): keypress la cach DUY NHAT an tren Firefox
        // -> thu NO TRUOC cho nhanh, khoi mat 4 vong go tron tro.
        if (laDraft(box)) {
          cach = [keypressInsert, perCharInsert, typeInsert, beforeInputInsert, pasteInsert];
          ten = ["keypress", "tung-ky-tu", "execCommand", "beforeinput", "paste"];
          if (oi === 0 && vong === 0) {
            report("caption-draftjs", "ô soạn là composer CŨ (DraftJS) — gõ bằng keypress trước");
          }
        }

        // Mo ta Facebook TU DIEN san (= ten file): ghi ra de chan doan va XOA truoc khi go.
        var san = boxText(box).replace(/\s+/g, " ").trim();
        if (san && vong === 0 && oi === 0) {
          report("caption-prefilled", "ô mô tả có sẵn " + san.length + " ký tự: "
                 + san.slice(0, 40) + " — sẽ xoá trước khi gõ");
        }

        function xong() {
          // KIEM LAN CUOI tren ca khung: con lap thi xoa het va go lai (toi da 2 lan).
          var lapc = demLapKhung(doc, hop, mocKiem);
          if (lapc >= 2 && vong < 3) {
            report("caption-doubled", "mô tả bị lặp " + lapc + " lần (kiểm cuối) — gõ lại");
            xoaHetOSoan(win, doc, ds);
            vong += 1;
            win.setTimeout(thu, 800);
            return;
          }
          var chu = boxText(box).replace(/\s+/g, " ").trim();
          var byte = 0;
          try { byte = unescape(encodeURIComponent(chu)).length; } catch (e) {}
          // Facebook do tieu de theo BYTE UTF-8: chu Thai moi chu 3 byte.
          done(true, ten[i] + " | ô " + (oi + 1) + "/" + ds.length + ": " + chu.length
               + " ký tự / " + byte + " byte | cần " + muon.length + " | \""
               + chu.slice(0, 160) + "\"");
        }

        (function keTiep() {
          if (i >= cach.length) { oi += 1; moO(); return; }   // o nay chiu -> sang o ke tiep
          bamVaoO(win, box);                                  // CLICK THAT: Lexical chi mount khi duoc bam
          xoaOSoan(win, doc, box);                            // XOA o boc...
          try { xoaOSoan(win, doc, oThat(win, doc, box)); } catch (eX) {}   // ...VA o that
          // CHAN DOAN: o con gi TRUOC khi go (xoa co sach khong) -- mo ta bi lap thi nhin day.
          report("caption-go", "ô " + (oi + 1) + "/" + ds.length + " cách " + ten[i]
                 + " · trước khi gõ ô còn " + boxText(box).length + " ký tự: \""
                 + boxText(box).replace(/\s+/g, " ").slice(0, 40) + "\"");
          cach[i](win, doc, box, caption);
          // KIEM HAI NHIP: Lexical ve lai bat dong bo, kiem ngay la tuong trong (bai hoc o soan X).
          win.setTimeout(function () {
            // Dem tren CA KHUNG: chu co the da roi sang o khac (o long nhau / soi guong).
            var lap = Math.max(demLap(box, mocKiem), demLapKhung(doc, hop, mocKiem));
            if (lap >= 2) {
              report("caption-doubled", "mô tả bị lặp " + lap + " lần — xoá hết rồi gõ lại");
              xoaHetOSoan(win, doc, ds);
              i += 1; keTiep(); return;
            }
            if (coChu(box)) { xong(); return; }
            win.setTimeout(function () {                      // nhip SAU moi ket luan hong
              if (coChu(box)) { xong(); return; }
              i += 1; keTiep();
            }, 900);
          }, 700);
        })();
      }

      moO();
    }

    thu();
  }

  /** Nut nay co nen mau dac khong -- dau hieu cua nut hanh dong chinh.
   *
   * KHONG nhan dien nut Dang bang chu: acc doi sang tieng Viet, tieng Philippines
   * hay tieng Tay Ban Nha la hong ngay. Da do tren giao dien that: moi nut phu
   * ("Add videos", "Publish now", "Cancel") deu nen trong suot rgba(0,0,0,0),
   * rieng nut Dang co nen xanh dac rgb(10,120,190). Mau nen khong doi theo
   * ngon ngu, nen lay lam dau hieu.
   */
  function isPrimary(win, el) {
    var mau = "";
    try { mau = win.getComputedStyle(el).backgroundColor || ""; } catch (e) { return false; }
    var m = /rgba?\(([^)]+)\)/.exec(mau);
    if (!m) { return false; }
    var p = m[1].split(",").map(function (x) { return parseFloat(x); });
    var alpha = p.length > 3 ? p[3] : 1;
    if (!(alpha > 0.05)) { return false; }          // nen trong suot -> nut phu
    var sang = (p[0] + p[1] + p[2]) / 3;
    return sang < 235;                              // bo nen trang / xam rat nhat
  }

  /** Nut hanh dong chinh o cuoi form: nen mau, nam thap nhat, ben phai nhat. */
  function findPublish(win, doc) {
    var list = [];
    try {
      list = Array.prototype.slice.call(doc.querySelectorAll('[role="button"], button'));
    } catch (e) { return null; }

    var ung = [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (!el.offsetParent) { continue; }
      try {
        if (el.getAttribute("aria-disabled") === "true") { continue; }
      } catch (e) {}
      if (!isPrimary(win, el)) { continue; }
      var box = null;
      try { box = el.getBoundingClientRect(); } catch (e) { continue; }
      if (box.width < 40 || box.height < 20) { continue; }   // bo cham tron nho
      ung.push({ el: el, top: box.top, left: box.left });
    }
    if (!ung.length) { return null; }
    ung.sort(function (a, b) {
      // Thap nhat truoc; cung hang thi lay cai ben phai nhat.
      if (Math.abs(a.top - b.top) > 8) { return b.top - a.top; }
      return b.left - a.left;
    });
    return ung[0].el;
  }

  function describePublish(win, doc) {
    var nut = findPublish(win, doc);
    if (!nut) { return null; }
    var box = { l: 0, t: 0 };
    try {
      var r = nut.getBoundingClientRect();
      box = { l: Math.round(r.left), t: Math.round(r.top),
              w: Math.round(r.width), h: Math.round(r.height) };
    } catch (e) {}
    var bg = "";
    try { bg = win.getComputedStyle(nut).backgroundColor; } catch (e) {}
    return { el: nut, text: textOf(nut), box: box, bg: bg };
  }

  function clickPublish(win, doc, cmd) {
    var tim = describePublish(win, doc);
    if (!tim) {
      // Nut "Đăng" bi khoa (aria-disabled) nen findPublish khong thay. Hay gap nhat
      // la Facebook che TIEU DE QUA DAI -> bao dung ly do thay vi "khong thay nut".
      var td0 = loiTieuDeDai(doc);
      if (td0) { report("title-too-long", td0); return; }
      try { dumpPage(doc, true); } catch (eD) {}
      report("no-publish-button", "không thấy nút hành động chính (nút nền màu)");
      return;
    }
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try {
      tim.el.click();
      report("published", tim.text + " | nền " + tim.bg);
    } catch (e) {
      report("publish-error", String(e));
      return;
    } finally {
      if (handle) { try { handle.destruct(); } catch (e) {} }
    }
    waitDone(win, doc, cmd, tim.el);
  }

  /** Nut hanh dong chinh NAM TRONG mot hop thoai (vd nut Done cua hop bao
   *  "Your bulk upload is processing!"). Van nhan dien bang nen mau, khong theo chu.
   */
  function dialogPrimary(win, doc, bo_qua) {
    var hop = [];
    try {
      hop = Array.prototype.slice.call(doc.querySelectorAll('[role="dialog"]'));
    } catch (e) { return null; }
    for (var i = hop.length - 1; i >= 0; i--) {          // hop moi nhat truoc
      if (!hop[i].offsetParent) { continue; }
      var nut = [];
      try {
        nut = Array.prototype.slice.call(
          hop[i].querySelectorAll('[role="button"], button'));
      } catch (e) { continue; }
      for (var j = nut.length - 1; j >= 0; j--) {
        if (nut[j] === bo_qua) { continue; }   // dung bam lai chinh nut vua bam
        if (nut[j].offsetParent && isPrimary(win, nut[j])) { return nut[j]; }
      }
    }
    return null;
  }

  /** Cho Facebook xac nhan da nhan bai, bam nut xac nhan, roi bao tool dong may.
   *
   * Da thay tren giao dien that: bam Dang xong Facebook hien hop "Your bulk
   * upload is processing!" kem mot nut xac nhan (Done). Composer phia sau van con
   * nguyen, nen khong the lay "composer bien mat" lam dau hieu xong duoc.
   */
  function waitDone(win, doc, cmd, vua_bam) {
    var giay = 0;
    var toi_da = Math.max(30, cmd.doneTimeout || 300);
    var timer = win.setInterval(function () {
      giay += 1;
      var nut = dialogPrimary(win, doc, vua_bam);
      if (nut) {
        win.clearInterval(timer);
        var handle = null;
        try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
        try { nut.click(); } catch (e) {}
        finally { if (handle) { try { handle.destruct(); } catch (e) {} } }
        report("publish-done", "đã bấm xác nhận sau " + giay + " giây");
        return;
      }
      // Khong thay hop xac nhan nhung composer da don sach cung coi la xong.
      if (!captionBox(doc) && !findPublish(win, doc)) {
        win.clearInterval(timer);
        report("publish-done", "composer đã đóng sau " + giay + " giây");
        return;
      }
      if (giay >= toi_da) {
        win.clearInterval(timer);
        try { dumpPage(doc, true); } catch (eD) {}
        report("publish-timeout", "chờ " + giay + " giây mà chưa thấy Facebook xác nhận");
      }
    }, 1000);
  }

  /** Do sang cua nen mot nut. -1 neu nen trong suot. */
  function bgLevel(win, el) {
    var mau = "";
    try { mau = win.getComputedStyle(el).backgroundColor || ""; } catch (e) { return -1; }
    var m = /rgba?\(([^)]+)\)/.exec(mau);
    if (!m) { return -1; }
    var p = m[1].split(",").map(function (x) { return parseFloat(x); });
    var alpha = p.length > 3 ? p[3] : 1;
    if (!(alpha > 0.05)) { return -1; }
    return (p[0] + p[1] + p[2]) / 3;
  }

  /** O "Ban viet gi di..." tren trang nhom -- bam vao day de mo hop soan bai.
   *
   * KHONG tim theo chu: nhom nao cung co the mot ngon ngu. Da do tren nhom that
   * (giao dien tieng Viet): o do la mot [role=button] NEN XAM NHAT
   * rgb(240,242,245) va RONG 600px, trong khi moi nut khac nen trong suot va hep.
   * Nut hanh dong chinh thi nen dam (do sang ~106) nen khong lan voi nhau.
   */
  function findComposerEntry(win, doc) {
    var list = [];
    try {
      list = Array.prototype.slice.call(doc.querySelectorAll('[role="button"]'));
    } catch (e) { return null; }
    var ung = [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (!el.offsetParent) { continue; }
      var sang = bgLevel(win, el);
      if (sang < 200) { continue; }              // nen dam hoac trong suot
      var box = null;
      try { box = el.getBoundingClientRect(); } catch (e) { continue; }
      if (box.width < 300 || box.height < 24 || box.height > 90) { continue; }
      ung.push({ el: el, top: box.top, w: box.width });
    }
    if (!ung.length) { return null; }
    // Cai nam tren cung: hop soan bai o dau trang tin cua nhom.
    ung.sort(function (a, b) { return a.top - b.top; });
    return ung[0].el;
  }

  function clickIt(win, el) {
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try { el.click(); return true; }
    catch (e) { report("click-error", String(e)); return false; }
    finally { if (handle) { try { handle.destruct(); } catch (e) {} } }
  }

  /** Phan tram Facebook dang bao tren trang. -1 neu khong thay cho nao bao.
   *
   * Doc theo ARIA va theo con so, KHONG theo chu: "Uploading" hay "Dang tai
   * len" doi theo ngon ngu, con aria-valuenow va "45%" thi khong.
   */
  function uploadPercent(doc) {
    var cao = -1;
    try {
      var thanh = doc.querySelectorAll('[role="progressbar"]');
      for (var i = 0; i < thanh.length; i++) {
        var v = parseFloat(thanh[i].getAttribute("aria-valuenow"));
        if (!isNaN(v) && v > cao) { cao = v; }
      }
    } catch (e) {}
    try {
      var moi = doc.querySelectorAll("div, span");
      for (var j = 0; j < moi.length && j < 4000; j++) {
        var el = moi[j];
        if (el.children.length) { continue; }            // chi lay o la
        var t = (el.textContent || "").trim();
        var m = /^(\d{1,3})\s*%$/.exec(t);
        if (m) {
          var so = parseInt(m[1], 10);
          if (so > cao) { cao = so; }
        }
      }
    } catch (e) {}
    return cao;
  }

  /** Cho phan check cua Facebook chay len 100% roi moi cho dang.
   *
   * Sau khi gan video, Facebook chay mot vong kiem tra (ban quyen) va hien phan
   * tram. Bam Dang khi chua xong thi bai khong len. Cung o day bat luon truong
   * hop trang hong: dung yen o 0% mai khong nhuc nhich.
   */
  /** Trang da NHAN video chua -- nhin nhieu tin hieu, khong chi phan tram.
   *
   * The <video> hien khi video vao danh sach; thanh role="progressbar" CO SO
   * (aria-valuenow) hien khi dang tai. Doi hoi valuenow de khong nham voi vong
   * xoay cho trang (cung role="progressbar" nhung khong co so).
   */
  function uploadAlive(doc) {
    try {
      if (doc.querySelector("video")) { return true; }
      var thanh = doc.querySelectorAll('[role="progressbar"]');
      for (var i = 0; i < thanh.length; i++) {
        var v = parseFloat(thanh[i].getAttribute("aria-valuenow"));
        if (!isNaN(v)) { return true; }
      }
    } catch (e) {}
    return false;
  }

  /** Duong du phong: gia thao tac keo-tha file vao giua trang.
   *
   * Composer co vung "keo video vao day". Khi gan vao o chon file ma trang cam
   * lang (Facebook doi cach nghe su kien -- 3/9/2026 tung gap kieu loc mime),
   * tha thang file vao vung do. DataTransfer + DragEvent la y het nhung gi
   * trinh duyet tu tao khi nguoi that keo file tha vao.
   */
  function thaVao(win, doc, file) {
    try {
      var dt = new win.DataTransfer();
      dt.items.add(file);
      var giua = doc.elementFromPoint(
        Math.floor(win.innerWidth / 2), Math.floor(win.innerHeight / 2))
        || doc.body;
      ["dragenter", "dragover", "drop"].forEach(function (loai) {
        giua.dispatchEvent(new win.DragEvent(loai, {
          bubbles: true, cancelable: true, dataTransfer: dt }));
      });
      report("attach-fallback", "ô chọn file câm lặng — đã thả file thẳng vào trang");
    } catch (e) {
      report("attach-fallback-error", String(e));
    }
  }

  // ------------------------------------------------------- TIEU DE QUA DAI
  // Facebook tu choi bai vi TIEU DE (ten video) qua dai: hien thong bao goc duoi
  // phai "Một bài viết của bạn có tiêu đề quá dài." va nut "Đăng" KHONG BAO GIO
  // sang. Doi den het gio cung vo ich -> phai nhan ra ngay de bo qua video do.
  var TIEU_DE_DAI = new RegExp(
    "(ti\u00eau \u0111\u1ec1|tieu de|title|caption)[^.\n]{0,40}"
    + "(qu\u00e1 d\u00e0i|qua dai|too long)"
    + "|(qu\u00e1 d\u00e0i|too long)[^.\n]{0,40}(ti\u00eau \u0111\u1ec1|title)", "i");

  /** Cau thong bao "tieu de qua dai" dang hien tren trang, hoac "" neu khong co. */
  function loiTieuDeDai(doc) {
    var chu = "";
    try { chu = (doc.body && doc.body.innerText) || ""; } catch (e) { return ""; }
    var m = TIEU_DE_DAI.exec(chu);
    if (!m) { return ""; }
    var dau = chu.lastIndexOf("\n", m.index);
    var cuoi = chu.indexOf("\n", m.index);
    return chu.slice(dau < 0 ? 0 : dau + 1,
                    cuoi < 0 ? chu.length : cuoi).trim().slice(0, 160);
  }

  function waitReady(win, doc, cmd, file, done) {
    report("ready-start", "bắt đầu chờ check xong");
    var giay = 0;
    var cho_treo = Math.max(20, cmd.stuckTimeout || 60);
    var cho_xong = Math.max(60, cmd.readyTimeout || 300);
    var cao_nhat = 0;
    var song = false;         // da co dau hieu nao cho biet trang NHAN video chua
    var da_tha = false;       // da thu duong du phong keo-tha chua
    var timer = win.setInterval(function () {
      try {
      giay += 1;
      var pt = uploadPercent(doc);
      if (pt > cao_nhat) { cao_nhat = pt; }
      if (!song && (cao_nhat > 0 || uploadAlive(doc))) {
        song = true;
        report("upload-alive", "trang đã nhận video (giây " + giay + ")");
      }
      // Bao nhip deu: khong co dong nay thi khi trang dung im, nhat ky trong tron
      // khong biet agent con song hay da chet (da gap: im lang suot 9 phut).
      if (giay === 1 || giay % 15 === 0 || pt > 0) {
        report("checking", cao_nhat + "% (" + giay + "s)");
      }
      // Tieu de qua dai -> nut Dang se KHONG BAO GIO sang. Dung ngay, bao de
      // tool bo qua video nay va chuyen sang video ke tiep.
      var td = loiTieuDeDai(doc);
      if (td) {
        win.clearInterval(timer);
        report("title-too-long", td);
        done(false);
        return;
      }
      if (cao_nhat >= 100) {
        win.clearInterval(timer);
        report("checked", "100%");
        done(true);
        return;
      }
      // 10 giay khong dong tinh gi -> thu duong du phong MOT lan roi cho tiep.
      if (!song && !da_tha && giay >= 10 && file) {
        da_tha = true;
        thaVao(win, doc, file);
      }
      if (!song && giay >= cho_treo) {
        win.clearInterval(timer);
        try { dumpPage(doc, true); } catch (e0) {}
        report("upload-stuck",
               "chờ " + giay + " giây mà không tải lên được phần trăm nào");
        done(false);
        return;
      }
      // Trang da nhan video nhung khong hien phan tram (co ban composer khong
      // hien %): cho mot doan roi di tiep. Khong so bam Dang som -- nut Dang
      // chi duoc bam khi no sang mau, tuc dang bam duoc that.
      if (song && cao_nhat <= 0 && giay >= Math.max(45, cho_treo)) {
        win.clearInterval(timer);
        report("checked", "không đọc được %, nhưng trang đã nhận video — đi tiếp");
        done(true);
        return;
      }
      if (giay >= cho_xong) {
        win.clearInterval(timer);
        try { dumpPage(doc, true); } catch (e1) {}
        report("check-timeout", "dừng ở " + cao_nhat + "%, chờ " + giay + " giây");
        done(false);
      }
      } catch (e) {
        win.clearInterval(timer);
        report("check-error", String(e));
        done(false);
      }
    }, 1000);
  }

  // ---------------------------------------------------------------- ĐẶT LỊCH
  // Bai khong dang ngay ma HEN GIO: bat che do "Đặt lịch" trong composer, dien
  // ngay/gio cua khung roi bam nut (luc nay nut chinh doi chu thanh "Đặt lịch").
  var LICH_CHU = /(đặt lịch|dat lich|lên lịch|len lich|hẹn giờ|hen gio|schedule)/i;
  // DA THAY THAT (Business Suite 9/2026): hop "Lựa chọn lịch đăng" co BA o roi nhau
  // — o ngay placeholder "dd/mm/yyyy", o "giờ", o "phút" — roi nut "Cập nhật".
  var LICH_NGAY = /(dd\s*\/\s*mm\s*\/\s*yyyy|mm\s*\/\s*dd\s*\/\s*yyyy|ngày|ngay|date)/i;
  var LICH_GIO = /^(giờ|gio|hour|hh)$|(thời gian|thoi gian|\btime\b)/i;
  var LICH_PHUT = /^(phút|phut|minute|mm)$/i;
  var LICH_CAP_NHAT = /^(cập nhật|cap nhat|update|xong|done|lưu|luu|save|áp dụng|ap dung|apply)$/i;
  // "Đăng ngay / Share now / Publish now" -- KHONG duoc nham la nut dat lich.
  var LICH_NGAY_LUON = /(ngay bây giờ|ngay bay gio|đăng ngay|dang ngay|now)/i;

  function nhanCua(el) {
    var s = "";
    try { s = el.getAttribute("aria-label") || el.getAttribute("placeholder") || ""; } catch (e) {}
    if (!s) { try { s = textOf(el); } catch (e2) {} }
    return (s || "").replace(/\s+/g, " ").trim();
  }

  function _datValue(win, el, v) {
    var proto = win.HTMLInputElement && win.HTMLInputElement.prototype;
    var setter = proto && Object.getOwnPropertyDescriptor(proto, "value");
    if (setter && setter.set) { setter.set.call(el, v); } else { el.value = v; }
  }

  /** Dien gia tri vao o ngay/gio cua Business Suite.
   *
   *  DA DO THAT: chi set value + ban "input" thi FB NHAN CHU NHUNG KHONG DOI STATE
   *  -> luc bam "Cập nhật" no giu gio mac dinh (~1 tieng sau). O nay la input co
   *  mat na, phai GO TUNG KY TU nhu nguoi that (keydown/keypress/input/keyup) roi
   *  blur de FB chot gia tri.
   */
  /** Mo ta mot o nhap -- de biet no la input thuong hay combobox/readonly. */
  function taO(el) {
    var p = [];
    try {
      p.push(el.tagName);
      p.push("type=" + (el.getAttribute("type") || "-"));
      p.push("role=" + (el.getAttribute("role") || "-"));
      if (el.readOnly) { p.push("READONLY"); }
      if (el.disabled) { p.push("DISABLED"); }
      p.push("maxlen=" + (el.getAttribute("maxlength") || "-"));
      p.push("aria=" + (el.getAttribute("aria-label") || el.getAttribute("placeholder") || "-"));
    } catch (e) {}
    return p.join(" ");
  }

  /** O GIO/PHUT cua Business Suite la role="spinbutton": set .value KHONG an
   *  (da do that: o van rong). Cach dung la bam MUI TEN len/xuong tung nac.
   */
  //: Phim THAT qua nsIDOMWindowUtils: su kien co isTrusted=true nen React nhan.
  //: DA DO THAT: dispatchEvent(new KeyboardEvent(...)) KHONG lam spinbutton nhuc
  //: nhich (aria-valuenow y nguyen '13' = gio mac dinh cua Facebook).
  var VK_UP = 38, VK_DOWN = 40;

  var _phimLoi = "";          // vi sao phim that khong dung duoc (de chan doan)

  function phimThat(win, ma_phim, ma_chu) {
    try {
      var u = win.windowUtils;
      if (!u) { _phimLoi = "khong co windowUtils"; return false; }
      if (!u.sendKeyEvent) { _phimLoi = "windowUtils KHONG co sendKeyEvent"; return false; }
      u.sendKeyEvent("keydown", ma_phim, ma_chu || 0, 0);
      if (ma_chu) { u.sendKeyEvent("keypress", ma_phim, ma_chu, 0); }
      u.sendKeyEvent("keyup", ma_phim, ma_chu || 0, 0);
      _phimLoi = "";
      return true;
    } catch (e) {
      _phimLoi = "sendKeyEvent ném: " + String(e).slice(0, 90);
      return false;
    }
  }

  /** Go mot SO vao o (chon het -> go tung chu so bang InputEvent tong hop). */
  function _goSoVaoO(win, el, so) {
    try {
      el.focus();
      try { el.select(); } catch (e0) {}
      try { el.setSelectionRange(0, (el.value || "").length); } catch (e1) {}
      var s = String(so);
      if (String(so).length < 2) { s = "0" + s; }      // gio/phut la 2 chu so
      _datValue(win, el, "");
      try {
        el.dispatchEvent(new win.InputEvent("input", {
          bubbles: true, cancelable: false, inputType: "deleteContentBackward" }));
      } catch (e2) {}
      for (var i = 0; i < s.length; i++) {
        _datValue(win, el, (el.value || "") + s.charAt(i));
        try {
          el.dispatchEvent(new win.InputEvent("input", {
            bubbles: true, cancelable: false,
            inputType: "insertText", data: s.charAt(i) }));
        } catch (e3) {
          el.dispatchEvent(new win.Event("input", { bubbles: true }));
        }
      }
      el.dispatchEvent(new win.Event("change", { bubbles: true }));
      return true;          // ket qua that duoc XAC MINH o nhip sau (buoc 14)
    } catch (e4) { return false; }
  }

  /** O co MAT NA tu bo so 0 ("26/9/2026" cho "26/09/2026") -> so theo TUNG SO,
   *  khong so chuoi chu so tho (2692026 != 26092026 nhung van la cung mot ngay).
   */
  function _khopSo(co, can) {
    var a = String(co || "").match(/\d+/g) || [];
    var b = String(can || "").match(/\d+/g) || [];
    if (a.length !== b.length || !b.length) { return false; }
    for (var i = 0; i < b.length; i++) {
      if (parseInt(a[i], 10) !== parseInt(b[i], 10)) { return false; }
    }
    return true;
  }

  /** Dat AM/PM cho o "meridiem". Da do that: o nay KHONG nhan chu "AM" cung
   *  khong nhan so 0/1 qua value. Thu lan luot nhieu cach, moi nhip mot cach:
   *    0: mot ky tu "a"/"p" (time-picker thuong toggle bang phim nay)
   *    1: chu day du "AM"/"PM"
   *    2: so 0 (AM) / 1 (PM)
   */
  function _datBuoi(win, el, buoi, lan) {
    var chu = String(buoi || "AM").toUpperCase();
    if (lan === 0) { return _goChuVaoO(win, el, chu.charAt(0).toLowerCase()); }
    if (lan === 1) { return _goChuVaoO(win, el, chu); }
    return _goSoVaoO(win, el, chu === "PM" ? 1 : 0);
  }

  /** Go CHU vao o (vd "AM"/"PM"). KHONG dung datNative cho o AM/PM: datNative
   *  thay role="spinbutton" thi chuyen sang datSpin, ma datSpin chi xu ly SO
   *  (parseInt("AM") = NaN -> khong lam gi, o giu nguyen PM mac dinh -> 01:00
   *  thanh 1:00pm, sai 12 tieng — da do that).
   */
  function _goChuVaoO(win, el, chu) {
    var handle = null;
    try {
      try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
      el.focus();
      try { el.select(); } catch (e0) {}
      var s = String(chu || "");
      _datValue(win, el, s);
      try {
        el.dispatchEvent(new win.InputEvent("input", {
          bubbles: true, cancelable: false, inputType: "insertReplacementText", data: s }));
      } catch (e1) {
        el.dispatchEvent(new win.Event("input", { bubbles: true }));
      }
      el.dispatchEvent(new win.Event("change", { bubbles: true }));
      return true;
    } catch (e2) {
      return false;
    } finally {
      if (handle) { try { handle.destruct(); } catch (e3) {} }
    }
  }

  function _spinNow(el) {
    var n = parseInt(el.getAttribute("aria-valuenow"), 10);
    if (isNaN(n)) { n = parseInt(el.value, 10); }
    return isNaN(n) ? null : n;
  }

  function datSpin(win, el, so) {
    var dich = parseInt(so, 10);
    if (isNaN(dich)) { return false; }
    var handle = null;
    try {
      try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
      el.focus();
      var min = parseInt(el.getAttribute("aria-valuemin"), 10);
      var max = parseInt(el.getAttribute("aria-valuemax"), 10);
      if (isNaN(min)) { min = 0; }
      if (isNaN(max)) { max = 59; }
      var vong = max - min + 1;

      // Doc gia tri MOT LAN roi bam DU SO NAC theo huong ngan nhat.
      // KHONG doc lai giua chung: React cap nhat aria-valuenow BAT DONG BO, doc
      // ngay sau phim thi van thay so cu -> tuong "khong nhuc nhich" va thoat som
      // (da do that: 13 -> 14 roi dung, dang le phai toi 19).
      var hien = _spinNow(el);
      if (hien === null) { return false; }
      if (hien === dich) { return true; }
      var len = ((dich - hien) % vong + vong) % vong;
      var phim = len <= vong - len ? VK_UP : VK_DOWN;
      var so_nac = Math.min(len, vong - len);
      var xong_phim = true;
      for (var i = 0; i < so_nac; i++) {
        if (!phimThat(win, phim, 0)) { xong_phim = false; break; }
      }
      if (xong_phim) { return true; }   // xac minh o nhip sau (buoc 14)

      // KHONG co phim that (process-script: windowUtils khong lo sendKeyEvent) ->
      // go SO thang vao o nhu o ngay: set value + InputEvent. O ngay da chung minh
      // React cua Business Suite CO nghe InputEvent tong hop.
      return _goSoVaoO(win, el, dich);
    } catch (e2) {
      return false;
    } finally {
      if (handle) { try { handle.destruct(); } catch (e3) {} }
    }
  }

  function datNative(win, el, giatri) {
    var doc = null;
    try { doc = el.ownerDocument; } catch (eD) {}
    try {
      if ((el.getAttribute("role") || "") === "spinbutton") {
        return datSpin(win, el, giatri);
      }
    } catch (eR) {}
    var handle = null;
    try {
      try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
      var s = String(giatri || "");
      el.focus();

      // CACH 1 (chinh): dat THANG ca chuoi roi ban InputEvent. React doc
      // event.target.value nen nhan nguyen gia tri moi -- khong phai xoa truoc.
      // XOA rieng roi go tung ky tu thi React HOAN NGUYEN gia tri cu giua chung
      // -> o ngay thanh '25/9/2026' + '26/09/2026' noi lien (da do that 25/09).
      _datValue(win, el, s);
      try {
        el.dispatchEvent(new win.InputEvent("input", {
          bubbles: true, cancelable: false, inputType: "insertReplacementText", data: s }));
      } catch (eA) {
        el.dispatchEvent(new win.Event("input", { bubbles: true }));
      }
      el.dispatchEvent(new win.Event("change", { bubbles: true }));

      // CACH 2 (du phong): xoa sach roi go tung ky tu.
      if (!_khopSo(el.value, s)) {
        try { el.select(); } catch (e0) {}
        try { el.setSelectionRange(0, (el.value || "").length); } catch (e1) {}
        try { doc.execCommand("delete", false, null); } catch (e1b) {}
        _datValue(win, el, "");
        try {
          el.dispatchEvent(new win.InputEvent("input", {
            bubbles: true, cancelable: false, inputType: "deleteContentBackward" }));
        } catch (e1c) {
          el.dispatchEvent(new win.Event("input", { bubbles: true }));
        }
        // GO TUNG KY TU, CHI su kien "input" -- TUYET DOI khong ban keydown/keypress/
        // keyup don dap: da lam CHET TRANG o luong add BM (xem NHO "CRASH do goTung").
        for (var i = 0; i < s.length; i++) {
          var ch = s.charAt(i);
          _datValue(win, el, (el.value || "") + ch);
          try {
            el.dispatchEvent(new win.InputEvent("input", {
              bubbles: true, cancelable: false, inputType: "insertText", data: ch }));
          } catch (e4) {
            el.dispatchEvent(new win.Event("input", { bubbles: true }));
          }
        }
        el.dispatchEvent(new win.Event("change", { bubbles: true }));
      }
      try { el.blur(); } catch (e6) {}
      return _khopSo(el.value, s);
    } catch (e) {
      return false;
    } finally {
      if (handle) { try { handle.destruct(); } catch (e7) {} }
    }
  }

  /** O nhap dau tien co nhan khop ``re``, bo qua cac o da dung (``tru``). */
  function oTheoNhan(doc, re, tru) {
    var os = [];
    try { os = Array.prototype.slice.call(doc.querySelectorAll("input")); } catch (e) { return null; }
    for (var i = 0; i < os.length; i++) {
      var o = os[i];
      if (!o.offsetParent) { continue; }
      if (tru && tru.indexOf(o) >= 0) { continue; }
      var t = "";
      try { t = (o.type || "").toLowerCase(); } catch (e2) {}
      if (t === "hidden" || t === "file" || t === "checkbox" || t === "radio") { continue; }
      if (re.test(nhanCua(o))) { return o; }
    }
    return null;
  }

  /** O NGAY trong hop lich: input co MAT NA chua "yyyy" (dd/mm/yyyy hoac
   *  mm/dd/yyyy). Do theo mat na, KHONG theo chu — giao dien tieng Anh la
   *  "mm/dd/yyyy", tieng Viet la "dd/mm/yyyy".
   */
  function _oNgay(doc) {
    var os = [];
    try { os = doc.querySelectorAll("input"); } catch (e) { return null; }
    for (var i = 0; i < os.length; i++) {
      if (!os[i].offsetParent) { continue; }
      if ((os[i].getAttribute("role") || "") === "spinbutton") { continue; }
      if (/y{2,4}/i.test(nhanCua(os[i]))) { return os[i]; }
    }
    return null;
  }

  /** Sap xep ngay theo MAT NA cua o. ``ngay`` vao luon la "dd/mm/yyyy". */
  function _ngayTheoMatNa(el, ngay) {
    var so = String(ngay || "").match(/\d+/g) || [];
    if (so.length < 3) { return String(ngay || ""); }
    var d = so[0], m = so[1], y = so[2];
    var mat_na = nhanCua(el).toLowerCase();
    // "mm/dd/yyyy" -> thang truoc; con lai coi la ngay truoc.
    if (mat_na.indexOf("mm") >= 0 && mat_na.indexOf("dd") >= 0
        && mat_na.indexOf("mm") < mat_na.indexOf("dd")) {
      return m + "/" + d + "/" + y;
    }
    return d + "/" + m + "/" + y;
  }

  /** O GIO / O PHUT: deu la role="spinbutton"; phan biet bang aria-valuemax
   *  (gio toi da 23 hoac 12, phut toi da 59) — KHONG do theo chu vi nhan doi
   *  theo ngon ngu ("giờ"/"hour"/"hh", "phút"/"minute"/"mm").
   */
  function _cacSpin(doc) {
    var ra = [];
    try {
      var ds = doc.querySelectorAll('[role="spinbutton"]');
      for (var i = 0; i < ds.length; i++) {
        if (!ds[i].offsetParent) { continue; }
        var mx = parseInt(ds[i].getAttribute("aria-valuemax"), 10);
        ra.push({ el: ds[i], max: isNaN(mx) ? -1 : mx });
      }
    } catch (e) {}
    return ra;
  }

  function _oGio(doc) {
    var sp = _cacSpin(doc);
    for (var i = 0; i < sp.length; i++) { if (sp[i].max >= 0 && sp[i].max <= 23) { return sp[i].el; } }
    return sp.length ? sp[0].el : null;      // du phong: o dau tien
  }

  function _oPhut(doc) {
    var sp = _cacSpin(doc);
    for (var i = 0; i < sp.length; i++) { if (sp[i].max >= 24) { return sp[i].el; } }
    return sp.length > 1 ? sp[1].el : null;  // du phong: o thu hai
  }

  /** Dong ho 12 GIO khong (giao dien My): o gio co aria-valuemax <= 12. */
  function _la12Gio(el) {
    try {
      var mx = parseInt(el.getAttribute("aria-valuemax"), 10);
      return !isNaN(mx) && mx <= 12;
    } catch (e) { return false; }
  }

  /** O AM/PM: spinbutton co aria-valuenow KHONG phai so, hoac phan tu chu AM/PM. */
  function _oBuoi(doc) {
    var ds = [];
    try { ds = doc.querySelectorAll('[role="spinbutton"], [role="combobox"], select, input'); }
    catch (e) { return null; }
    for (var i = 0; i < ds.length; i++) {
      if (!ds[i].offsetParent) { continue; }
      var vn = "";
      try { vn = String(ds[i].getAttribute("aria-valuenow") || ds[i].value || ""); } catch (e2) {}
      if (/^(am|pm|sa|ch)$/i.test(vn.trim())) { return ds[i]; }
      if (/\b(am\/pm|meridiem|buổi)\b/i.test(nhanCua(ds[i]))) { return ds[i]; }
    }
    return null;
  }

  /** Nut xac nhan cua hop lich ("Cập nhật"). Khong lay nut chinh cua composer. */
  function nutCapNhat(win, doc) {
    var chinh = findPublish(win, doc);
    var list = [];
    try {
      list = Array.prototype.slice.call(doc.querySelectorAll('[role="button"], button'));
    } catch (e) { return null; }
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (el === chinh || !el.offsetParent) { continue; }
      if (LICH_CAP_NHAT.test(nhanCua(el))) { return el; }
    }
    return null;
  }

  /** Cong tac / muc chon "Đặt lịch" (KHONG phai nut chinh, KHONG phai "Đăng ngay"). */
  function nutDatLich(win, doc) {
    var chinh = findPublish(win, doc);
    var list = [];
    try {
      list = Array.prototype.slice.call(doc.querySelectorAll(
        '[role="radio"], [role="menuitemradio"], [role="menuitem"], [role="switch"],'
        + ' [role="checkbox"], [role="tab"], [role="button"], button, label'));
    } catch (e) { return null; }
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (el === chinh || !el.offsetParent) { continue; }
      var nhan = nhanCua(el);
      if (!nhan || nhan.length > 60) { continue; }
      if (LICH_NGAY_LUON.test(nhan)) { continue; }
      if (LICH_CHU.test(nhan)) { return el; }
    }
    return null;
  }

  /** O CHON CHE DO DANG ("Đăng ngay") — bam vao day moi hien lua chon "Đặt lịch".
   *
   *  DA THAY THAT (Business Suite 9/2026, acc nguoi dung): composer khong he co
   *  san muc "Đặt lịch"; cac nut la: Thêm video | Thêm | Đăng ngay | Tùy chọn
   *  chỉnh sửa khác | Gỡ | Hủy | Đăng. "Đăng ngay" la o chon che do, bam vao no
   *  moi ra "Đặt lịch".
   *
   *  KHONG bao gio tra ve nut CHINH (nut "Đăng" nen mau) -> khong the bam nham
   *  thanh dang luon.
   */
  function nutCheDoDang(win, doc) {
    var chinh = findPublish(win, doc);
    var list = [];
    try {
      list = Array.prototype.slice.call(doc.querySelectorAll(
        '[role="radio"], [role="menuitemradio"], [role="switch"], [role="tab"],'
        + ' [aria-haspopup], [role="button"], button, label'));
    } catch (e) { return null; }
    var thuong = null;
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (el === chinh || !el.offsetParent) { continue; }
      if (isPrimary(win, el)) { continue; }        // nut nen mau = nut Dang that
      var nhan = nhanCua(el);
      if (!nhan || nhan.length > 40) { continue; }
      if (!LICH_NGAY_LUON.test(nhan)) { continue; }
      // Uu tien phan tu CO DAU HIEU la o chon (menu/radio/tab), roi moi den nut thuong.
      var vai = "";
      try { vai = (el.getAttribute("role") || "") + (el.getAttribute("aria-haspopup") || ""); } catch (e2) {}
      if (vai) { return el; }
      if (!thuong) { thuong = el; }
    }
    return thuong;
  }

  /** Nut mui ten canh nut Dang (che do dang nam trong menu xo xuong). */
  function nutMuiTen(win, doc) {
    var chinh = findPublish(win, doc);
    if (!chinh) { return null; }
    var hop = null;
    try { hop = chinh.getBoundingClientRect(); } catch (e) { return null; }
    var list = [];
    try {
      list = Array.prototype.slice.call(doc.querySelectorAll('[aria-haspopup], [role="button"]'));
    } catch (e2) { return null; }
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (el === chinh || !el.offsetParent) { continue; }
      var b = null;
      try { b = el.getBoundingClientRect(); } catch (e3) { continue; }
      // Cung hang voi nut Dang, nam ngay sat ben (nut nho hinh mui ten).
      if (Math.abs(b.top - hop.top) <= 12 && b.width <= 70
          && Math.abs(b.left - hop.right) <= 80) { return el; }
    }
    return null;
  }

  /** Liet ke nhan cac nut/o de chan doan khi khong tim thay phan dat lich. */
  function dumpNhanLich(win, doc) {
    var ra = [];
    try {
      var list = Array.prototype.slice.call(doc.querySelectorAll(
        '[role="radio"], [role="menuitemradio"], [role="switch"], [role="button"], button, input'));
      for (var i = 0; i < list.length && ra.length < 40; i++) {
        if (!list[i].offsetParent) { continue; }
        var n = nhanCua(list[i]);
        if (n && n.length <= 60) { ra.push(n); }
      }
    } catch (e) {}
    return ra.join(" | ");
  }

  /** Bat che do dat lich + dien ngay/gio. Goi ``xong(ok, chi_tiet)``.
   *
   *  THAT BAI THI KHONG BAM DANG: dang SAI GIO con te hon khong dang -- nguoi
   *  dung hen 20:00 ma bai len ngay bay gio la hong ca lich.
   */
  function datLich(win, doc, cmd, xong) {
    var lich = cmd.lich || {};
    var buoc = 0, giay = 0, moc = 0, daMoMenu = false;
    var can_buoi = "";        // "AM"/"PM" khi o gio la dong ho 12 tieng
    var lan_buoi = 0;         // da thu bao nhieu cach dat AM/PM
    var toi_da = Math.max(25, cmd.scheduleTimeout || 70);
    var timer = win.setInterval(function () {
      giay += 1;
      function thoi(ok, chi_tiet) {
        win.clearInterval(timer);
        xong(ok, chi_tiet);
      }
      try {
        if (buoc === 0) {
          var nut = nutDatLich(win, doc);
          if (nut) {
            report("schedule-open", "bật chế độ đặt lịch: " + nhanCua(nut));
            clickIt(win, nut);
            buoc = 1; moc = giay;
            return;
          }
          // Chua thay muc "Đặt lịch" -> bam O CHON CHE DO ("Đăng ngay") de no hien ra.
          if (!daMoMenu && giay >= 2) {
            var che_do = nutCheDoDang(win, doc);
            if (che_do) {
              daMoMenu = true;
              report("schedule-mode", "bấm ô chế độ đăng: " + nhanCua(che_do));
              clickIt(win, che_do);
              return;
            }
            var caret = nutMuiTen(win, doc);
            if (caret) {
              daMoMenu = true;
              report("schedule-menu", "mở menu cạnh nút Đăng: " + nhanCua(caret));
              clickIt(win, caret);
              return;
            }
          }
          if (giay >= Math.min(20, toi_da - 5)) {
            thoi(false, "không thấy mục 'Đặt lịch' trong composer | " + dumpNhanLich(win, doc));
          }
          return;
        }
        // Ba o dien LAN LUOT, moi buoc TIM LAI o tu DOM: dien xong mot o thi
        // Business Suite render lai hop, giu tham chieu cu la dien vao phan tu
        // MO COI (da do that: o ngay vao duoc, o gio/phut van rong).
        if (buoc === 1 || buoc === 12 || buoc === 13) {
          if (giay < moc + 1) { return; }
          var hm = String(lich.gio || "").split(":");
          var o, gtri, ten_o;
          // Do theo CAU TRUC (mat na o ngay, aria-valuemax cua spinbutton), KHONG
          // theo chu: giao dien tieng Anh la "mm/dd/yyyy"/"hour"/"minute", tieng
          // Viet la "dd/mm/yyyy"/"giờ"/"phút".
          if (buoc === 1) {
            o = _oNgay(doc);
            gtri = o ? _ngayTheoMatNa(o, lich.ngay || "") : (lich.ngay || "");
            ten_o = "ngày";
          } else if (buoc === 12) {
            o = _oGio(doc);
            var h24 = parseInt(hm[0], 10);
            if (o && _la12Gio(o) && !isNaN(h24)) {
              // Giao dien My dung dong ho 12 GIO: 20:00 -> 8 PM. Dien thang 20 thi
              // o kep lai con 2 (da do that).
              var h12 = h24 % 12; if (h12 === 0) { h12 = 12; }
              gtri = String(h12);
              can_buoi = h24 >= 12 ? "PM" : "AM";
            } else {
              gtri = hm[0] || "";
            }
            ten_o = "giờ";
          } else {
            o = _oPhut(doc); gtri = hm[1] || "00"; ten_o = "phút";
          }
          if (!o) {
            if (buoc === 13) { buoc = 14; moc = giay; return; }   // khong co o phut
            if (giay >= toi_da - 6) {
              thoi(false, "không thấy ô " + ten_o + " trong hộp đặt lịch | "
                   + dumpNhanLich(win, doc));
            }
            return;
          }
          var ok = datNative(win, o, gtri);
          var thay = "";
          try {
            thay = (o.getAttribute("role") === "spinbutton")
              ? String(o.getAttribute("aria-valuenow") || o.value || "")
              : String(o.value || "");
          } catch (e8) {}
          report("schedule-fill-" + (buoc === 1 ? "ngay" : (buoc === 12 ? "gio" : "phut")),
                 ten_o + "=" + gtri + " -> ô '" + thay + "'" + (ok ? "" : "  ⚠ chưa vào")
                 + "  [" + taO(o) + "]");
          // O KHONG NHAN gia tri -> DUNG HAN, khong bam. Bam tiep thi Facebook giu
          // gio mac dinh (~1 tieng sau) = bai len SAI GIO, te hon la khong dang.
          if (!ok) {
            thoi(false, "ô " + ten_o + " không nhận giá trị (" + gtri + " -> '" + thay
                 + "') [" + taO(o) + "]"
                 + (_phimLoi ? " | PHÍM THẬT: " + _phimLoi : " | phím thật OK")
                 + " — không bấm để tránh đăng sai giờ");
            return;
          }
          buoc = (buoc === 1) ? 12 : (buoc === 12 ? 13 : (can_buoi ? 135 : 14));
          moc = giay;
          return;
        }
        if (buoc === 135) {
          if (giay < moc + 1) { return; }
          var ob = _oBuoi(doc);
          if (!ob) {
            report("schedule-fill-buoi", "không thấy ô AM/PM — bỏ qua");
            buoc = 14; moc = giay;
            return;
          }
          // O "meridiem" cua Business Suite la SPINBUTTON dung SO: 0 = AM, 1 = PM.
          // (Bang chung: go "AM" ra o '1' va Facebook nhan 1:00PM — lech 12 tieng.)
          _datBuoi(win, ob, can_buoi, lan_buoi);
          report("schedule-fill-buoi", "buổi=" + can_buoi + " (cách " + (lan_buoi + 1)
                 + ")  [" + taO(ob) + "]");
          lan_buoi += 1;
          // KHONG doc lai ngay: React cap nhat aria-valuenow BAT DONG BO (doc ngay
          // thi van thay so cu -> bao "chua vao" oan). Buoc 14 xac minh o nhip sau.
          buoc = 14; moc = giay;
          return;
        }
        if (buoc === 14) {
          // XAC MINH gio/phut o NHIP SAU: React cap nhat aria-valuenow bat dong bo,
          // doc ngay sau phim thi van thay so cu.
          if (giay < moc + 2) { return; }
          var hm2 = String(lich.gio || "").split(":");
          var oG = _oGio(doc);
          var oP = _oPhut(doc);
          var vG = oG ? _spinNow(oG) : null;
          var vP = oP ? _spinNow(oP) : null;
          var canG = parseInt(hm2[0], 10);
          var canP = parseInt(hm2[1] || "0", 10);
          if (oG && _la12Gio(oG) && !isNaN(canG)) {
            var c12 = canG % 12; if (c12 === 0) { c12 = 12; }
            canG = c12;              // o 12 gio thi so theo gio 12
          }
          var okG2 = (vG === canG);
          var okP2 = (oP == null) || (vP === canP);
          // O 12 gio: PHAI kiem ca AM/PM, khong thi lech dung 12 tieng (da do
          // that: hen 01:00 ma Facebook nhan 1:00pm).
          var buoi_hien = "";
          if (can_buoi) {
            var ob2 = _oBuoi(doc);
            try { buoi_hien = String(ob2 && (ob2.getAttribute("aria-valuenow") || ob2.value) || ""); }
            catch (eB2) {}
            var so_can = (can_buoi === "PM") ? 1 : 0;
            var so_co = ob2 ? _spinNow(ob2) : null;
            var khop_buoi = (so_co === so_can)
                            || new RegExp("^" + can_buoi + "$", "i").test(buoi_hien.trim());
            if (!khop_buoi) { okG2 = false; }
          }
          report("schedule-check", "giờ " + vG + "/" + canG + " · phút " + vP + "/" + canP
                 + (can_buoi ? " · buổi " + (buoi_hien || "?") + "/" + can_buoi : "")
                 + (okG2 && okP2 ? "  ✓" : "  ⚠"));
          if (okG2 && okP2) { buoc = 15; moc = giay; return; }
          if (giay >= toi_da - 8) {
            thoi(false, "giờ đặt lịch không vào đúng (cần " + canG + ":" + canP
                 + ", ô đang là " + vG + ":" + vP + ") — không bấm để tránh đăng sai giờ");
            return;
          }
          // Buoi sai ma con cach chua thu -> quay lai dat buoi bang CACH KHAC.
          if (can_buoi && !okG2 && lan_buoi < 3) { buoc = 135; moc = giay; return; }
          // Chua dung -> bam bu them (huong ngan nhat tu gia tri HIEN TAI).
          if (oG && !okG2) { datSpin(win, oG, canG); }
          if (oP && !okP2) { datSpin(win, oP, canP); }
          moc = giay;
          return;
        }
        if (buoc === 15) {
          // Hop lich co nut rieng ("Cập nhật") de chot gio truoc khi ve composer.
          if (giay < moc + 1) { return; }
          var capNhat = nutCapNhat(win, doc);
          if (capNhat) {
            report("schedule-confirm", "bấm '" + nhanCua(capNhat) + "' để chốt giờ");
            clickIt(win, capNhat);
            buoc = 2; moc = giay;
            return;
          }
          if (giay >= moc + 4) { buoc = 2; moc = giay; }   // khong co nut -> di tiep
          return;
        }
        if (buoc === 2 && giay >= moc + 3) {
          // BANG CHUNG da o che do hen gio. Hai dau hieu, co mot la du:
          //   1) nut chinh doi chu thanh "Đặt lịch"/"Lên lịch"; HOAC
          //   2) o chon che do khong con la "Đăng ngay" (da chuyen sang "Lên lịch").
          // DA THAY THAT: Business Suite GIU NGUYEN nut "Đăng", chi doi chip che do
          // -> neu chi soi chu nut thi khong bao gio hen duoc.
          var tim = describePublish(win, doc);
          var chu = tim ? tim.text : "";
          var conDangNgay = !!nutCheDoDang(win, doc);
          if (tim && LICH_CHU.test(chu)) { thoi(true, "nút chính đã là '" + chu + "'"); return; }
          if (tim && !conDangNgay) {
            thoi(true, "chế độ đã chuyển khỏi 'Đăng ngay' (nút chính: '" + chu + "')");
            return;
          }
          if (giay >= toi_da) {
            thoi(false, "đã điền lịch nhưng vẫn ở chế độ 'Đăng ngay' (nút chính '" + chu
                 + "') — không bấm để tránh đăng sai giờ | " + dumpNhanLich(win, doc));
          }
          return;
        }
        if (giay >= toi_da) { thoi(false, "quá " + giay + " giây"); }
      } catch (e) {
        thoi(false, String(e));
      }
    }, 1000);
  }

  /** Doi cho trang xu ly xong video roi dien mo ta, roi (neu duoc bao) bam Dang. */
  function afterAttach(win, doc, cmd) {
    win.setTimeout(function () {
      fillCaption(win, doc, cmd.caption || "", function (ok, chi_tiet) {
        if (cmd.dumpAfter) { dumpButtons(doc); }
        if (!ok) { try { dumpPage(doc, true); } catch (eD) {} }
        report(ok ? "caption-filled" : "caption-failed", chi_tiet || "");
        tiepTuc(win, doc, cmd);
      });
    }, cmd.captionDelay || 9000);
  }

  /** Sau khi dien mo ta xong: tim nut Dang (de kiem chung) hoac bam Dang. */
  function tiepTuc(win, doc, cmd) {
    if (cmd.findAfter) {
      // Chi TIM nut Dang roi bao lai, khong bam -- dung de kiem chung ma khong
      // dang bai that len fanpage.
      win.setTimeout(function () {
        var tim = describePublish(win, doc);
        report(tim ? "publish-found" : "no-publish-button",
               tim ? (tim.text + " | nền " + tim.bg
                      + " | vị trí " + tim.box.l + "," + tim.box.t) : "");
      }, cmd.publishDelay || 6000);
    }
    if (cmd.publish) {
      // Cho them mot nhip: Facebook chi bat nut Dang khi video da xu ly xong.
      win.setTimeout(function () {
        if (!cmd.lich) { clickPublish(win, doc, cmd); return; }
        // Bai HEN GIO: bat dat lich + dien ngay/gio TRUOC, xong moi bam.
        datLich(win, doc, cmd, function (ok, chi_tiet) {
          if (!ok) { report("schedule-failed", chi_tiet || ""); return; }
          report("scheduled", chi_tiet || "");
          clickPublish(win, doc, cmd);
        });
      }, cmd.publishDelay || 6000);
    }
  }

  /** Kham trang buoi sang: composer con nhung bo phan quen thuoc khong.
   *
   * KHONG dang gi ca -- chi mo composer roi cho o chon file hien ra. Muc dich:
   * biet Facebook vua doi giao dien tu 7 gio sang, truoc khi hang chuc trang
   * cung hong vao moc dang dau tien.
   */
  function khamTrang(win, doc, cmd) {
    var giay = 0;
    var toi_da = Math.max(15, cmd.healthTimeout || 40);
    var timer = win.setInterval(function () {
      giay += 1;
      var input = null;
      try { input = findFileInput(doc); } catch (e) {}
      if (input) {
        win.clearInterval(timer);
        var accept = "";
        try { accept = input.getAttribute("accept") || ""; } catch (e2) {}
        report("healthy",
               "có ô chọn file (accept=" + accept + ") sau " + giay + " giây");
        return;
      }
      if (giay >= toi_da) {
        win.clearInterval(timer);
        try { dumpPage(doc, true); } catch (e3) {}
        report("unhealthy", "chờ " + giay
               + " giây mà không thấy ô chọn file — Facebook có thể vừa đổi giao diện");
      }
    }, 1000);
  }

  // ------------------------------------------------------- DOI NGON NGU ACC
  //: Ten ngon ngu trong danh sach cua Facebook LUON viet bang chinh no
  //: ("English (US)" van la "English (US)" du giao dien dang la tieng Tay Ban Nha)
  //: -> do theo ten nay la BEN, khong phu thuoc ngon ngu dang hien.
  function _tenNgonNgu(ma) {
    if (String(ma).indexOf("vi") === 0) { return /tiếng việt/i; }
    return /english \(us\)/i;
  }

  function _mucCoChu(doc, re, toi_da) {
    var ra = [];
    var ds = [];
    // CHI trong vung noi dung chinh: quet ca trang thi bam nham thanh dieu huong
    // (thong bao / chat / menu) — da gap that.
    var goc = doc;
    try { goc = doc.querySelector('[role="main"]') || doc; } catch (eG) {}
    try {
      // Muc trong trang Cai dat khong phai lúc nao cung la role=button -> lay ca
      // phan tu co tabindex (FB dung div[tabindex] lam muc bam duoc).
      ds = goc.querySelectorAll('[role="button"], [role="link"], [role="radio"], '
                                + '[role="menuitem"], [role="option"], [role="row"], '
                                + '[tabindex], a, button, label');
    } catch (e) { return ra; }
    for (var i = 0; i < ds.length && ra.length < (toi_da || 8); i++) {
      if (!ds[i].offsetParent) { continue; }
      var t = "";
      try { t = String(ds[i].textContent || "").trim(); } catch (e2) { continue; }
      // Muc trong Cai dat gop ca DONG MO TA dai ("Idioma de la cuenta" + "Los
      // botones, titulos...") -> cat 60 la loai mat dung muc can bam.
      if (!t || t.length > 220 || !re.test(t)) { continue; }
      var trung = false;
      for (var k = 0; k < ra.length; k++) {
        try { if (ra[k].contains(ds[i]) || ds[i].contains(ra[k])) { trung = true; break; } }
        catch (e3) {}
      }
      if (!trung) { ra.push(ds[i]); }
    }
    return ra;
  }

  /** O nhap dau tien trong hop thoai (o "Buscar idiomas" — nhan o tieng la nen
   *  KHONG do theo chu, chi lay input dau tien trong dialog).
   */
  /** Hop thoai MOI NHAT dang hien (querySelector lay cai DAU TIEN -> sai hop). */
  function _hopHien(doc) {
    var hop = [];
    try { hop = doc.querySelectorAll('[role="dialog"]'); } catch (e) { return null; }
    for (var i = hop.length - 1; i >= 0; i--) {
      if (hop[i].offsetParent) { return hop[i]; }
    }
    return null;
  }

  function _oTimTrongHop(doc) {
    var hop = [];
    try { hop = doc.querySelectorAll('[role="dialog"]'); } catch (e) { return null; }
    for (var i = hop.length - 1; i >= 0; i--) {
      if (!hop[i].offsetParent) { continue; }
      var os = [];
      try { os = hop[i].querySelectorAll("input"); } catch (e2) { continue; }
      for (var k = 0; k < os.length; k++) {
        var t = "";
        try { t = (os[k].type || "").toLowerCase(); } catch (e3) {}
        if (t === "hidden" || t === "radio" || t === "checkbox") { continue; }
        if (os[k].offsetParent) { return os[k]; }
      }
    }
    return null;
  }

  function doiNgonNgu(win, doc, cmd) {
    var ma = cmd.ma || "en_US";
    var la_vi = String(ma).indexOf("vi") === 0;
    var tu_go = la_vi ? "tieng viet" : "english";
    // UU TIEN ban dung: go "english" ra ca English (UK) lan (US) — phai lay DUNG
    // (US), khong phai "cai dau tien" trong danh sach (da chon nham UK mot lan).
    var re_chinh = la_vi ? /tiếng việt/i : /english\s*\(us\)/i;
    var re_du = la_vi ? /tiếng việt/i : /english/i;
    var giay = 0, buoc = 0, moc = 0, da_bam = 0, da_tai_lai = false;
    var toi_da = Math.max(45, cmd.langTimeout || 100);

    function xong(ok, chi_tiet) {
      win.clearInterval(t);
      report(ok ? "lang-done" : "lang-failed", chi_tiet || "");
    }
    function langHienTai() {
      try { return String(doc.documentElement.getAttribute("lang") || ""); }
      catch (e) { return ""; }
    }
    function dat(ok) { return langHienTai().indexOf(String(ma).split("_")[0]) === 0; }

    var t = win.setInterval(function () {
      giay += 1;
      try {
        if (/(?:^|;\s*)i_user=/.test(doc.cookie || "")) {
          xong(false, "vẫn đang ở QUYỀN PAGE (cookie i_user) — phải về acc cá nhân trước");
          return;
        }
        if (dat() && buoc === 0) {
          xong(true, "ngôn ngữ đã là " + langHienTai() + " — không cần đổi");
          return;
        }

        // B0: bam muc "Ngon ngu cua tai khoan" -> hop thoai co O TIM hien ra.
        if (buoc === 0) {
          if (_oTimTrongHop(doc)) { buoc = 1; moc = giay; return; }
          if (giay < moc + 2) { return; }
          var mucs = _mucCoChu(doc, /\S/, 10);
          if (da_bam < mucs.length) {
            var el = mucs[da_bam];
            da_bam += 1;
            report("lang-step", "mở mục " + da_bam + ": «"
                   + String(el.textContent || "").trim()
                       .split(String.fromCharCode(10))[0].slice(0, 40) + "»");
            clickIt(win, el);
            moc = giay;
            return;
          }
          if (giay >= toi_da - 12) {
            xong(false, "không mở được hộp chọn ngôn ngữ | " + dumpNhanLich(win, doc));
          }
          return;
        }

        // B1: go tu khoa vao O TIM (nguoi dung chi: go "english" roi chon cai dau).
        if (buoc === 1) {
          var o = _oTimTrongHop(doc);
          if (!o) { buoc = 0; moc = giay; return; }
          datNative(win, o, tu_go);
          report("lang-step", "gõ '" + tu_go + "' vào ô tìm -> ô đang là '"
                 + String(o.value || "") + "'");
          buoc = 2; moc = giay;
          return;
        }

        // B2: chon KET QUA DAU TIEN khop ten ngon ngu (ten luon viet bang chinh no).
        if (buoc === 2 && giay >= moc + 2) {
          var goc_hop = _hopHien(doc) || doc;
          var chon = _mucCoChu(goc_hop, re_chinh, 3);
          if (!chon.length && giay >= moc + 5) {
            chon = _mucCoChu(goc_hop, re_du, 3);   // khong co (US) thi lay ban Anh nao cung duoc
          }
          if (!chon.length) {
            if (giay >= moc + 9) { xong(false, "gõ xong nhưng không thấy mục ngôn ngữ nào"); }
            return;
          }
          report("lang-step", "chọn «" + String(chon[0].textContent || "").trim()
                 .split(String.fromCharCode(10))[0].slice(0, 30) + "»");
          clickIt(win, chon[0]);
          buoc = 3; moc = giay;
          return;
        }

        // B3: khong co nut Luu — chon xong la FB ap dung ngay; cho trang doi ngon ngu.
        if (buoc === 3) {
          if (dat()) { xong(true, "đã đổi sang " + langHienTai()); return; }
          // Facebook AP DUNG NGAY nhung trang DANG MO khong doi <html lang> (da do
          // that: chon xong bao 'he'/'es', mo lai trang thi da la 'en'). -> TU TAI
          // LAI TRANG mot lan; agent chay lai se thay dung ngon ngu va bao xong.
          if (!da_tai_lai && giay >= moc + 4) {
            da_tai_lai = true;
            report("lang-step", "đã chọn — tải lại trang để xác minh");
            win.clearInterval(t);
            try { win.location.reload(); } catch (eR) {}
            return;
          }
          if (giay >= toi_da) {
            xong(false, "đã chọn nhưng ngôn ngữ vẫn là '" + langHienTai() + "'");
          }
          return;
        }
        if (giay >= toi_da) { xong(false, "quá " + giay + " giây (bước " + buoc + ")"); }
      } catch (e) {
        xong(false, String(e));
      }
    }, 1000);
  }

  function runCommand(win, cmd) {
    var doc = win.document;
    if (cmd.action === "health") { khamTrang(win, doc, cmd); return; }
    if (cmd.action === "dump") { dumpPage(doc); return; }
    if (cmd.action === "dumpbuttons") { dumpButtons(doc); return; }
    if (cmd.action === "groupdump") {
      var o = findComposerEntry(win, doc);
      if (!o) { try { dumpPage(doc, true); } catch (eD) {} (function () {
        var dn2 = laTrangDangNhap(win, doc, win.location.href || "");
        if (dn2) { report("logged-out", dn2.slice(0, 160)); return; }
        report("no-composer", "không thấy ô soạn bài trên trang nhóm");
      })(); return; }
      report("composer-found", textOf(o) + " | " + Math.round(
        o.getBoundingClientRect().width) + "px");
      clickIt(win, o);
      win.setTimeout(function () { dumpButtons(doc); }, cmd.dumpDelay || 5000);
      return;
    }
    // CHAN NGON NGU LA: cac buoc dang bai do nut theo chu Viet/Anh. Giao dien dang
    // la thu tieng khac (da gap Tay Ban Nha, Hebrew) thi do sai nut -> phai doi
    // ngon ngu TRUOC, khong dang lieu.
    if (cmd.action === "upload" || cmd.action === "group") {
      var lg = "";
      try { lg = String(doc.documentElement.getAttribute("lang") || ""); } catch (eL) {}
      var goc_lg = lg.split("-")[0].toLowerCase();
      if (goc_lg && goc_lg !== "vi" && goc_lg !== "en") {
        report("lang-unsupported", lg);
        return;
      }
    }
    if (cmd.action === "setlang") {
      doiNgonNgu(win, doc, cmd);
      return;
    }
    if (cmd.action === "langscan") {
      // SOI NGON NGU: doc ngon ngu THAT dang hien (documentElement.lang) + cookie
      // locale + liet ke phan tu co ma ngon ngu (de bat giao dien trang doi ngon ngu).
      win.setTimeout(function () {
        var ra = [];
        try { ra.push("lang=" + (doc.documentElement.getAttribute("lang") || "?")); } catch (e) {}
        try { ra.push("url=" + String(doc.location.href).slice(0, 110)); } catch (e) {}
        try {
          var m = /(?:^|;\s*)locale=([^;]+)/.exec(doc.cookie || "");
          ra.push("cookie.locale=" + (m ? m[1] : "-"));
        } catch (e) {}
        try { ra.push("title=" + String(doc.title || "").slice(0, 60)); } catch (e) {}
        // c_user = acc ca nhan; i_user = DANG O QUYEN PAGE (phai ve ca nhan moi
        // doi duoc ngon ngu -- nguoi dung da chot).
        try {
          var cu_ = /(?:^|;\s*)c_user=([^;]+)/.exec(doc.cookie || "");
          var iu_ = /(?:^|;\s*)i_user=([^;]+)/.exec(doc.cookie || "");
          ra.push("c_user=" + (cu_ ? cu_[1] : "-") + " i_user=" + (iu_ ? iu_[1] : "-")
                  + (iu_ ? "  >>> DANG O QUYEN PAGE" : "  (dang la ca nhan)"));
        } catch (e) {}
        // Phan tu co dinh danh ngon ngu (href/name/value/id chua "locale" hoac "_US"/"_VN").
        var thay = [];
        try {
          var ds = doc.querySelectorAll("a, input, button, select, option, [role=radio], [role=button]");
          for (var i = 0; i < ds.length && thay.length < 30; i++) {
            var el = ds[i], mo = "";
            try {
              mo = (el.getAttribute("href") || "") + "|" + (el.getAttribute("name") || "")
                 + "|" + (el.getAttribute("value") || "") + "|" + (el.getAttribute("id") || "");
            } catch (e2) { continue; }
            if (!/locale|[a-z]{2}_[A-Z]{2}/.test(mo)) { continue; }
            thay.push(el.tagName + " " + mo.slice(0, 90)
                      + " «" + String(el.textContent || "").trim().slice(0, 28) + "»");
          }
        } catch (e3) {}
        ra.push("phan tu ngon ngu (" + thay.length + "): " + thay.join("  ///  "));
        report("lang-info", ra.join(" | ").slice(0, 3500));
      }, cmd.dumpDelay || 9000);
      return;
    }
    if (cmd.action === "readmain") {
      // Doc chu cua vung noi dung -- dung de XAC MINH gio da len lich tren FB.
      // Chi doc, khong bam gi.
      win.setTimeout(function () {
        var el = null;
        try { el = doc.querySelector('[role="main"]') || doc.body; } catch (e) {}
        var chu = "";
        try { chu = (el && el.innerText || "").replace(/\n{2,}/g, "\n"); } catch (e2) {}
        report("main-text", chu.slice(0, cmd.limit || 4000));
      }, cmd.dumpDelay || 12000);
      return;
    }
    if (cmd.action === "findpublish") {
      var tim = describePublish(win, doc);
      report(tim ? "publish-found" : "no-publish-button",
             tim ? (tim.text + " | nền " + tim.bg + " | vị trí "
                    + tim.box.l + "," + tim.box.t) : "");
      return;
    }
    if (cmd.action === "group") {
      if (!cmd.path) { report("no-path", "lệnh thiếu đường dẫn video"); return; }
      runGroup(win, doc, cmd);
      return;
    }
    if (cmd.action !== "upload") { return; }

    if (!cmd.path) {
      report("no-path", "lệnh thiếu đường dẫn video");
      return;
    }
    // Business Suite ve rat cham va tung nhip. CHO o chon file hien ra chu dung
    // bo cuoc ngay -- da gap: mo may lan thi mot lan trang chua kip ve xong.
    var cho = 0;
    var toi_da = Math.max(10, cmd.inputTimeout || 90);
    (function doiInput() {
      var input = findFileInput(doc);
      if (input) {
        report("attaching", cmd.path);
        attachFile(win, input, cmd.path, function (ok, file) {
          if (!ok) { return; }
          // Cho Facebook check xong (len 100%) roi moi dien mo ta va bam Dang.
          waitReady(win, doc, cmd, file, function (san_sang) {
            if (san_sang) { afterAttach(win, doc, cmd); }
          });
        }, cmd.mime);
        return;
      }
      cho += 1;
      if (cho >= toi_da) {
        try { dumpPage(doc, true); } catch (eD) {}
        // Het gio ma khong co o chon file: thuong la acc DA BI DANG XUAT (trang chi moi
        // dang nhap). Bao dung ly do de core goi mo-dun dang nhap roi dang lai.
        var dn1 = laTrangDangNhap(win, doc, win.location.href || "");
        if (dn1) { report("logged-out", dn1.slice(0, 160)); return; }
        report("no-file-input", "chờ " + cho + " giây mà trang chưa có ô chọn file");
        return;
      }
      win.setTimeout(doiInput, 1000);
    })();
  }

  /* ---------------------------------------------------------- dang vao nhom */

  /** Hop thoai soan bai dang mo (co nut dong hoac o chon file ben trong). */
  function openDialog(doc) {
    // Lay hop TO NHAT: trang con co cac hop nho (chu giai, menu) cung mang
    // role="dialog"; lay nham mot cai cao 60px thi loc theo khung ra rong khong
    // (da do -- nut Dang nam ngoai khung do nen tim mai khong thay).
    var hop = [];
    try { hop = Array.prototype.slice.call(doc.querySelectorAll('[role="dialog"]')); }
    catch (e) { return null; }
    var to = null, rong = 0;
    for (var i = 0; i < hop.length; i++) {
      if (!hop[i].offsetParent) { continue; }
      try {
        var r = hop[i].getBoundingClientRect();
        var dt = r.width * r.height;
        if (dt > rong) { rong = dt; to = hop[i]; }
      } catch (e) {}
    }
    return to;
  }

  /** O chon file nhan video trong hop thoai. Trang nhom co san 4 cai, khong
   *  phai bam nut "Anh/video" moi hien ra (da do tren nhom that). */
  function groupFileInput(root, kind) {
    var can = (kind === "image") ? "image" : "video";
    var list = [];
    try {
      list = Array.prototype.slice.call(root.querySelectorAll('input[type="file"]'));
    } catch (e) { return null; }
    var hop = [];
    for (var i = 0; i < list.length; i++) {
      var accept = (list[i].getAttribute("accept") || "").toLowerCase();
      if (accept.indexOf(can) !== -1) { hop.push(list[i]); }
    }
    // Uu tien o nhan nhieu file: do la o cua trinh chon anh/video cua bai viet.
    for (var j = 0; j < hop.length; j++) {
      if (hop[j].hasAttribute("multiple")) { return hop[j]; }
    }
    return hop[0] || list[0] || null;
  }

  /** Nut Dang cua hop thoai nhom.
   *
   * Khac Business Suite: luc bai con trong, nut Dang NEN TRONG SUOT (da do).
   * Co noi dung roi no moi doi mau. Nen tim theo nen mau truoc; khong thay thi
   * lay nut RONG NHAT nam thap nhat trong hop thoai -- van khong dung toi chu.
   */
  function groupPostButton(win, doc, hop) {
    var khung = null;
    try { khung = hop.getBoundingClientRect(); } catch (e) { return null; }

    var list = [];
    try {
      list = Array.prototype.slice.call(doc.querySelectorAll('[role="button"], button'));
    } catch (e) { return null; }

    var hien = [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (!el.offsetParent) { continue; }
      if (el.getAttribute("aria-disabled") === "true") { continue; }
      var box = null;
      try { box = el.getBoundingClientRect(); } catch (e) { continue; }
      if (box.width < 150 || box.height < 24 || box.height > 70) { continue; }
      // Loc theo VI TRI nam trong khung hop thoai, khong theo cay DOM: React dat
      // nhieu thu o nhanh khac nen "nam trong the hop thoai" khong dung duoc.
      if (box.left < khung.left - 4 || box.right > khung.right + 4) { continue; }
      if (box.top < khung.top - 4 || box.bottom > khung.bottom + 4) { continue; }
      hien.push({ el: el, top: box.top, mau: isPrimary(win, el) });
    }
    if (!hien.length) { return null; }
    var mau = hien.filter(function (x) { return x.mau; });
    var chon = (mau.length ? mau : hien);
    chon.sort(function (a, b) { return b.top - a.top; });     // thap nhat truoc
    return chon[0].el;
  }

  /** Nut "Tham gia nhom" tren trang nhom (acc CHUA la thanh vien). Nhieu ngon ngu. */
  function timNutThamGia(win, doc) {
    var list = [];
    try { list = Array.prototype.slice.call(doc.querySelectorAll('[role="button"],a[role="link"],button')); }
    catch (e) { return null; }
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (!el.offsetParent) { continue; }
      var t = (el.getAttribute("aria-label") || el.textContent || "").replace(/\s+/g, " ").trim();
      if (!t || t.length > 45) { continue; }
      var low = t.toLowerCase();
      // ĐÃ là thành viên / ĐÃ xin vào -> KHÔNG phải nút cần bấm.
      if (/đã tham gia|đã gia nhập|rời nhóm|rời khỏi nhóm|leave group|đã gửi|đã yêu cầu|requested|huỷ yêu cầu|hủy yêu cầu|đang chờ|cancel request/.test(low)) { continue; }
      // Nút vào nhóm: gồm cả "Yêu cầu tham gia nhóm" (nhóm cần duyệt), "Gia nhập", "Join".
      if (/tham gia|yêu cầu tham gia|gia nhập nhóm|request to join|ask to join|(^|\s)join(\s|$)|join group/.test(low)) {
        return el;
      }
    }
    return null;
  }
  /** Da bam Tham gia nhung nhom CAN DUYET -> nut doi thanh "Da gui yeu cau/Huy yeu cau/Requested". */
  function daXinVaoNhom(doc) {
    var b = "";
    try { b = (doc.body ? doc.body.innerText : "").toLowerCase(); } catch (e) {}
    return /đã gửi yêu cầu|đã yêu cầu|yêu cầu đang chờ|huỷ yêu cầu|hủy yêu cầu|đang chờ phê duyệt|requested|cancel request|request sent|pending approval|request to join/.test(b);
  }

  function runGroup(win, doc, cmd) {
    // Acc CHUA la thanh vien -> trang nhom co nut "Tham gia nhom"/"Yeu cau tham gia" (trang thanh vien
    // KHONG co). Phai kiem TRUOC findComposerEntry: nut Tham gia mau xanh, rong -> de bi nham la o soan.
    if (cmd._daThamGia !== true) {
      var nut = timNutThamGia(win, doc);
      if (nut) {
        cmd._daThamGia = true;
        report("group-joining", "acc chưa vào nhóm — bấm '" + (textOf(nut) || "Tham gia nhóm").slice(0, 30) + "' rồi mới đăng");
        clickIt(win, nut);
        // Nhom cong khai: vao ngay, o soan hien ra (khong reload) -> doi va dang.
        // Nhom can duyet: nut doi thanh "Da gui yeu cau" -> bao pending.
        var lan = 0;
        var doiVao = win.setInterval(function () {
          lan += 1;
          try {
            if (findComposerEntry(win, doc) && !timNutThamGia(win, doc)) {
              win.clearInterval(doiVao); runGroup(win, doc, cmd); return;   // da vao nhom -> dang
            }
            if (daXinVaoNhom(doc)) {
              win.clearInterval(doiVao);
              report("group-join-pending", "đã gửi yêu cầu vào nhóm — nhóm CẦN DUYỆT, chưa đăng được. Sẽ đăng khi được duyệt.");
              return;
            }
            if (lan >= 10) {   // ~20s van chua vao va chua thay yeu cau cho duyet
              win.clearInterval(doiVao);
              try { dumpPage(doc, true); } catch (eD) {}
              report("no-composer", "đã bấm Tham gia nhưng chưa vào được nhóm (chưa có ô soạn bài)");
            }
          } catch (e) { win.clearInterval(doiVao); report("error", "sau tham gia: " + e); }
        }, 2000);
        return;
      }
    }
    var o = findComposerEntry(win, doc);
    if (!o) {
      try { dumpPage(doc, true); } catch (eD) {} (function () {
        var dn2 = laTrangDangNhap(win, doc, win.location.href || "");
        if (dn2) { report("logged-out", dn2.slice(0, 160)); return; }
        report("no-composer", "không thấy ô soạn bài trên trang nhóm");
      })();
      return;
    }
    report("composer-found", textOf(o));
    if (!clickIt(win, o)) { return; }

    var giay = 0;
    var doiHop = win.setInterval(function () {
      giay += 1;
      var hop = openDialog(doc);
      // Bai chi co chu: khong gan file nao ca. Hop soan bai mo ra la dien chu
      // duoc luon -- gan file .txt vao thi bai lai co mot tep dinh kem.
      if (hop && cmd.kind === "text") {
        win.clearInterval(doiHop);
        afterGroupAttach(win, doc, cmd);
        return;
      }
      // Tim o chon file tren CA TRANG chu khong chi trong hop thoai: React dat
      // cac o do o mot nhanh khac cua cay DOM, khong nam trong the hop thoai
      // (da do: hop thoai mo roi ma tim ben trong van khong thay o nao).
      var input = hop ? groupFileInput(doc, cmd.kind) : null;
      if (input) {
        win.clearInterval(doiHop);
        // Nhieu media (anh + video gop 1 bai): cmd.medias = [{path,mime}]. Dinh het
        // vao o media (o nay accept ca image lan video).
        if (cmd.medias && cmd.medias.length) {
          report("attaching", cmd.medias.length + " media");
          attachMany(win, input, cmd.medias, function (ok) {
            if (ok) { afterGroupAttach(win, doc, cmd); }
          });
          return;
        }
        report("attaching", cmd.path);
        attachFile(win, input, cmd.path, function (ok) {
          if (ok) { afterGroupAttach(win, doc, cmd); }
        }, cmd.mime);
        return;
      }
      if (giay >= Math.max(15, cmd.inputTimeout || 60)) {
        win.clearInterval(doiHop);
        try { dumpPage(doc, true); } catch (eD) {}
        report("no-file-input", "hộp soạn bài không có ô chọn file");
      }
    }, 1000);
  }

  /** Bai CHI CHU: chon NGAU NHIEN mot mau nen (phong nen) cho noi bat.
   *
   * Swatch la DIV vuong ~32px, nen la gradient / anh / mau tuoi; xam (mac dinh /
   * khong nen) thi bo. To tien role=button la cho de click. Neu dai mau dang thu
   * gon thi bam nut "Hien thi cac tuy chon phong nen" roi quet lai.
   */
  function pickRandomBackground(win, doc, done) {
    var XAM = ["rgb(201, 204, 209)", "rgb(242, 244, 247)", "rgb(226, 229, 233)",
               "rgb(255, 255, 255)", "rgba(0, 0, 0, 0)"];
    function collect() {
      var seen = [], btns = [], els;
      try { els = doc.querySelectorAll('[role="dialog"] div'); } catch (e) { return []; }
      for (var i = 0; i < els.length; i++) {
        var el = els[i], r;
        try { r = el.getBoundingClientRect(); } catch (e) { continue; }
        if (r.width < 28 || r.width > 40 || r.height < 28 || r.height > 40) { continue; }
        var st = win.getComputedStyle(el);
        var bg = st.backgroundImage || "", bc = st.backgroundColor || "";
        var la_mau = /gradient|url\(/.test(bg) || XAM.indexOf(bc) < 0;
        if (!la_mau) { continue; }
        var anc = null;
        for (var p = el; p && p !== doc.body; p = p.parentElement) {
          if (p.getAttribute && p.getAttribute("role") === "button") { anc = p; break; }
        }
        if (anc && seen.indexOf(anc) < 0) { seen.push(anc); btns.push(anc); }
      }
      return btns;
    }
    function clickToggle() {
      try {
        var bs = doc.querySelectorAll('[role="dialog"] [role="button"][aria-label]');
        for (var j = 0; j < bs.length; j++) {
          if (/phông nền|background/i.test(bs[j].getAttribute("aria-label") || "")) {
            bs[j].click(); return true;
          }
        }
      } catch (e) {}
      return false;
    }
    function chon(btns) {
      var pick = btns[Math.floor(Math.random() * btns.length)];
      try {
        pick.scrollIntoView({ block: "center" });
        pick.click();
        report("background-picked", "có " + btns.length + " mẫu, chọn ngẫu nhiên 1");
      } catch (e) { report("background-error", String(e)); }
      win.setTimeout(done, 900);
    }
    // Dai mau thuong HIEN SAN khi co chu, nhung render tre -> POLL nhieu lan thay
    // vi thu mot lan. Chi bam nut "bung" khi mai khong thay (du phong).
    var tries = 0, toggled = false;
    (function attempt() {
      tries++;
      var btns = collect();
      if (btns.length) { chon(btns); return; }
      if (tries >= 4 && !toggled) { toggled = true; clickToggle(); }
      if (tries < 8) { win.setTimeout(attempt, 600); return; }
      report("background-none", "không thấy mẫu màu (chữ quá dài / FB đổi giao diện)");
      done();
    })();
  }

  function afterGroupAttach(win, doc, cmd) {
    // Thu tu BAT BUOC: gan video -> CHO VIDEO NAP XONG -> moi dien tieu de ->
    // roi bam Dang. Dien tieu de trong luc video con dang nap thi hop soan bai
    // ve lai, chu vua go bi mat.
    //
    // Anh va bai chi co chu thi khong co the <video> de cho -- di thang sang
    // buoc dien chu.
    var cho = (cmd.kind === "video" || !cmd.kind)
      ? waitVideoReady
      : function (w, d, c, xong) { w.setTimeout(function () { xong(true); }, 2500); };
    cho(win, doc, cmd, function () {
      win.setTimeout(function () {
        // Chan doan (khi gop nhieu media): dem preview anh + the video trong hop
        // soan -> biet FB co GIU ca anh lan video khong.
        if (cmd.medias && cmd.medias.length) {
          try {
            var hop2 = openDialog(doc) || doc;
            var nImg = 0;
            var seen = {};
            for (var im of hop2.querySelectorAll('img')) {
              var s = im.currentSrc || im.src || "";
              if (/blob:|scontent|t39\./.test(s) && im.getBoundingClientRect().width > 40 && !seen[s]) { seen[s] = 1; nImg++; }
            }
            var nVid = hop2.querySelectorAll('video').length;
            report("media-in-composer", "anh~" + nImg + " video=" + nVid);
          } catch (eM) { report("media-in-composer", "loi dem: " + eM); }
        }
        var capText = cmd.caption || "";
        var coMedia = (cmd.kind === "image" || cmd.kind === "video" || !cmd.kind
                       || (cmd.medias && cmd.medias.length));

        function sauCaption(ok, chi_tiet) {
          if (!ok) { report("caption-failed", chi_tiet || ""); return; }
          if (cmd.dumpBeforePublish) { dumpVisibleButtons(win, doc); }
          // Bai CHI CHU (khong media) + bat randomBg -> chon mau nen ngau nhien
          // cho noi bat, ROI moi bao caption-filled + dang. Bao caption-filled SAU
          // khi chon nen de che do test (publish=false) van chay buoc chon nen.
          var la_text = (cmd.kind === "text") && !(cmd.medias && cmd.medias.length);
          function xong() {
            report("caption-filled", chi_tiet || "");
            if (!cmd.publish) { return; }
            win.setTimeout(function () { groupPublish(win, doc, cmd); },
                           cmd.publishDelay || 3000);
          }
          if (la_text && cmd.randomBg) { pickRandomBackground(win, doc, xong); }
          else { xong(); }
        }

        // Bai co ANH/VIDEO nhung KHONG co mo ta -> VAN DANG (bai chi media, khong kem chu),
        // KHONG coi la loi (truoc day caption rong -> caption-failed -> ket ca hang doi, nhat la
        // file le khong co .txt di kem). Bai CHI CHU ma rong thi van la loi (khong co gi de dang).
        if (!capText) {
          if (coMedia) {
            report("caption-empty", "bài không có mô tả — đăng ảnh/video không kèm chữ");
            sauCaption(true, "(không có mô tả — đăng không kèm chữ)");
          } else {
            report("caption-failed", "bài chỉ chữ nhưng không có nội dung");
          }
        } else {
          fillCaption(win, doc, capText, sauCaption, openDialog(doc));
        }
      }, cmd.captionDelay || 3000);
    });
  }

  /** Liet ke nut trong khung hop thoai, kem trang thai khoa -- de soi khi hong. */
  /** Cac nut co the la nut Dang: dang HIEN TREN MAN HINH, rong, khong bi khoa.
   *
   * Loc theo man hinh chu khong theo cay DOM hay khung hop thoai. Da do tren
   * nhom that: nut Dang o [398,703,468x36] trong man hinh cao 851, con o soan
   * bai va nut khac deu nam ngoai man hinh (top am hoac lon hon chieu cao).
   * Khong dung toi chu nen doi ngon ngu van chay.
   */
  function dialogButtons(win, doc) {
    var list = [];
    try {
      list = Array.prototype.slice.call(doc.querySelectorAll('[role="button"], button'));
    } catch (e) { return []; }
    var cao = win.innerHeight || 900;
    var ra = [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (!el.offsetParent) { continue; }
      var box = null;
      try { box = el.getBoundingClientRect(); } catch (e) { continue; }
      if (box.width < 300 || box.height < 24 || box.height > 70) { continue; }
      if (box.top < 0 || box.top > cao) { continue; }      // ngoai man hinh
      ra.push({
        el: el, top: box.top,
        khoa: el.getAttribute("aria-disabled") === "true",
        mau: isPrimary(win, el),
        chu: textOf(el),
      });
    }
    return ra;
  }

  /** Trang thai video trong hop soan bai -- de biet Facebook nap xong chua.
   *
   * Doc thang tu the <video>: readyState 4 la du du lieu de phat, duration co so
   * la da doc duoc thong tin video. Toan so, khong dinh chu nghia nao nen doi
   * ngon ngu van chay. Da do tren nhom that: sau khi gan file thi ready=4,
   * duration=18.
   */
  function videoState(doc) {
    var ra = { so: 0, ready: -1, duration: 0, percent: -1 };
    try {
      var vs = doc.querySelectorAll("video");
      ra.so = vs.length;
      for (var i = 0; i < vs.length; i++) {
        if (vs[i].readyState > ra.ready) { ra.ready = vs[i].readyState; }
        var d = vs[i].duration;
        if (!isNaN(d) && d > ra.duration) { ra.duration = Math.round(d); }
      }
    } catch (e) {}
    ra.percent = uploadPercent(doc);
    return ra;
  }

  /** Do het cac nut dang hien -- chi dung khi can soi giao dien. */
  function dumpVisibleButtons(win, doc) {
    var list = [];
    try {
      list = Array.prototype.slice.call(doc.querySelectorAll('[role="button"], button'));
    } catch (e) {}
    var ra = [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (!el.offsetParent) { continue; }
      var box = null;
      try { box = el.getBoundingClientRect(); } catch (e) { continue; }
      if (box.width < 100) { continue; }
      ra.push({
        text: textOf(el),
        aria: (el.getAttribute("aria-label") || "").slice(0, 40),
        khoa: el.getAttribute("aria-disabled") === "true",
        mau: isPrimary(win, el),
        box: [Math.round(box.left), Math.round(box.top),
              Math.round(box.width), Math.round(box.height)],
      });
    }
    var hop = openDialog(doc);
    var khung = null;
    if (hop) {
      try {
        var r = hop.getBoundingClientRect();
        khung = [Math.round(r.left), Math.round(r.top),
                 Math.round(r.width), Math.round(r.height)];
      } catch (e) {}
    }
    // Liet ke ca cac o soan chu kem vi tri -- de biet o nao la o cua bai viet.
    var soan = [];
    try {
      var eds = doc.querySelectorAll('[contenteditable="true"], textarea');
      for (var j = 0; j < eds.length; j++) {
        var e2 = eds[j];
        if (!e2.offsetParent) { continue; }
        var b2 = e2.getBoundingClientRect();
        soan.push({
          tag: e2.tagName.toLowerCase(),
          role: e2.getAttribute("role") || "",
          aria: (e2.getAttribute("aria-label") || "").slice(0, 60),
          chu: (e2.innerText || e2.value || "").slice(0, 40),
          box: [Math.round(b2.left), Math.round(b2.top),
                Math.round(b2.width), Math.round(b2.height)],
        });
      }
    } catch (e) {}
    try {
      sendAsyncMessage("qlfp:dump", {
        url: doc.location.href, buttons: ra, dialog: khung, editables: soan,
        video: videoState(doc), viewport: [win.innerWidth, win.innerHeight],
      });
    } catch (e) {}
  }

  /** Cho Facebook nap xong video trong hop soan bai.
   *
   * Do thang tu the <video>: readyState >= 3 la da du du lieu de phat, va
   * duration > 0 la da doc duoc thong tin video. Da do tren nhom that: sau khi
   * gan file mot lat thi ready=4, duration=18. Toan so, khong dinh chu nghia nao.
   */
  function waitVideoReady(win, doc, cmd, xong) {
    var giay = 0;
    var toi_da = Math.max(20, cmd.videoWait || 180);
    var timer = win.setInterval(function () {
      giay += 1;
      var v = videoState(doc);
      if (v.so > 0 && v.ready >= 3 && v.duration > 0) {
        win.clearInterval(timer);
        report("video-ready", "ready=" + v.ready + " dài " + v.duration + "s sau "
                              + giay + " giây");
        xong(true);
        return;
      }
      if (giay % 10 === 0) {
        report("video-loading", "ready=" + v.ready + " duration=" + v.duration
                                + " (" + giay + "s)");
      }
      if (giay >= toi_da) {
        win.clearInterval(timer);
        report("video-slow", "chờ " + giay + " giây video vẫn chưa nạp xong");
        xong(false);
      }
    }, 1000);
  }

  function groupPublish(win, doc, cmd) {
    var giay = 0;
    var toi_da = Math.max(30, cmd.publishWait || 240);
    var bao = "";
    var timer = win.setInterval(function () {
      giay += 1;
      if (!openDialog(doc)) {
        win.clearInterval(timer);
        report("no-publish-button", "hộp soạn bài đã đóng trước khi kịp bấm Đăng");
        return;
      }
      var spam = canhBaoSpam(doc);
      if (spam) {
        win.clearInterval(timer);
        report("spam-limit", spam);
        return;
      }
      var nut = dialogButtons(win, doc);
      var dung = nut.filter(function (x) { return !x.khoa; });
      var mau = dung.filter(function (x) { return x.mau; });
      var chon = (mau.length ? mau : dung);
      if (chon.length) {
        chon.sort(function (a, b) { return b.top - a.top; });   // thap nhat truoc
        win.clearInterval(timer);
        if (!clickIt(win, chon[0].el)) { return; }
        report("published", chon[0].chu + (chon[0].mau ? " (nền màu)" : ""));
        waitGroupDone(win, doc, cmd);
        return;
      }
      // Chua bam duoc: bao mot lan cho biet dang cho cai gi.
      var moi = nut.map(function (x) {
        return x.chu + (x.khoa ? "[khoá]" : "");
      }).join(", ").slice(0, 90);
      if (moi !== bao) {
        bao = moi;
        report("waiting-publish", moi || "chưa có nút nào trong hộp");
      }
      if (giay >= toi_da) {
        win.clearInterval(timer);
        try { dumpPage(doc, true); } catch (eD) {}
        report("no-publish-button",
               "chờ " + giay + " giây, nút vẫn khoá: " + (moi || "không thấy nút"));
      }
    }, 1000);
  }

  // Facebook chan dang vi SPAM: hop soan bai hien dong chu do, nut Dang van bam duoc
  // nhung bai KHONG len. Bat ca tieng Viet lan tieng Anh; phai co CA "spam" lan cum
  // "gioi han tan suat" de khong nham voi chu spam o cho khac trong trang nhom.
  var SPAM_CHU = new RegExp(
    "(t\u1ea7n su\u1ea5t b\u1ea1n \u0111\u0103ng|gi\u1edbi h\u1ea1n t\u1ea7n su\u1ea5t"
    + "|limit how often|limit how frequently|limit the rate)", "i");

  /** Dong canh bao SPAM dang hien (hoac "" neu khong co). */
  function canhBaoSpam(doc) {
    var chu = "";
    try {
      var goc = openDialog(doc) || doc.body;
      chu = (goc && goc.innerText) || "";
    } catch (e) { return ""; }
    if (!/spam/i.test(chu) || !SPAM_CHU.test(chu)) { return ""; }
    var dong = chu.split("\n");
    for (var i = 0; i < dong.length; i++) {
      if (/spam/i.test(dong[i]) || SPAM_CHU.test(dong[i])) {
        return dong[i].trim().slice(0, 200);
      }
    }
    return chu.trim().slice(0, 200);
  }

  function waitGroupDone(win, doc, cmd) {
    var giay = 0;
    var timer = win.setInterval(function () {
      giay += 1;
      if (!openDialog(doc)) {
        win.clearInterval(timer);
        report("publish-done", "hộp soạn bài đã đóng sau " + giay + " giây");
        return;
      }
      var spam2 = canhBaoSpam(doc);
      if (spam2) {
        win.clearInterval(timer);
        report("spam-limit", spam2);
        return;
      }
      if (giay >= Math.max(30, cmd.doneTimeout || 300)) {
        win.clearInterval(timer);
        try { dumpPage(doc, true); } catch (eD) {}
        report("publish-timeout", "chờ " + giay + " giây mà hộp soạn bài chưa đóng");
      }
    }, 1000);
  }

  /* -------------------------------------------------------------- khoi dong */

  /** Lay document cua cua so (co the chua san sang). */
  function doc0(win) {
    try { return win.document; } catch (e) { return null; }
  }

  /** Trang dang mo CO PHAI trang dang nhap khong -> tra ly do, "" la khong.
   *
   * Khong chi do mot chuoi URL: Facebook da vang acc ra nhieu dia chi khac nhau --
   * /login, /login.php, va "/index.php?next=..." (anh nguoi dung 02/10). Chac an nhat
   * la do CHINH CAI FORM dang nhap (o email + o mat khau) dang hien tren trang.
   */
  // Business Suite KHONG dua ve /login khi het phien: no giu nguyen URL composer va hien
  // trang chao "Đăng nhập vào công cụ kinh doanh của Meta / Tiếp tục bằng Facebook"
  // (da do that 02/10). Khong co o email/mat khau nen phai do theo CHU.
  var BS_DANG_NHAP = new RegExp(
    "\u0111\u0103ng nh\u1eadp v\u00e0o c\u00f4ng c\u1ee5 kinh doanh"
    + "|ti\u1ebfp t\u1ee5c b\u1eb1ng facebook"
    + "|log in to .{0,24}business tools|continue with facebook", "i");

  function laTrangDangNhap(win, doc, href) {
    href = href || "";
    if (href.indexOf("facebook.com") === -1) { return ""; }
    if (href.indexOf("facebook.com/login") !== -1) { return href; }
    if (!doc) { return ""; }
    try {
      var email = doc.querySelector('input[name="email"], input#email');
      var pass = doc.querySelector('input[name="pass"], input#pass');
      if (email && pass && email.offsetParent && pass.offsetParent) {
        return href + " (có form đăng nhập)";
      }
    } catch (e) {}
    try {
      var chu = (doc.body && doc.body.innerText) || "";
      if (BS_DANG_NHAP.test(chu)) {
        return href + " (trang mời đăng nhập của Business Suite)";
      }
    } catch (e) {}
    return "";
  }

  function onPage(win) {
    var href = "";
    try { href = win.location.href || ""; } catch (e) { return; }
    // Acc bi Facebook giu lai: trang nao cung co the bi nem ve checkpoint hoac
    // trang dang nhap. Bao ngay de tool biet day la chuyen cua ACC chu khong
    // phai tool hong -- va khoi ngoi cho het gio vo ich.
    if (href.indexOf("facebook.com") !== -1 && href.indexOf("/checkpoint") !== -1) {
      // AN HAN 12s: agent fbskip tu bam "Bo qua" neu la checkpoint MEM -> trang chuyen tiep
      // (onPage chay lai o trang moi). Van ke checkpoint sau 12s -> checkpoint CUNG, bao.
      win.setTimeout(function () {
        try {
          if ((win.location.href || "").indexOf("/checkpoint") !== -1 && getCommand()) {
            report("checkpoint", (win.location.href || "").slice(0, 160));
          }
        } catch (e) {}
      }, 12000);
      return;
    }
    var dn = laTrangDangNhap(win, doc0(win), href);
    if (dn) {
      if (getCommand()) { report("logged-out", dn.slice(0, 160)); }
      return;
    }
    var cmd = getCommand();
    if (!cmd || !cmd.action) { return; }

    // Chay tren Business Suite (fanpage) va trang nhom. Rieng cac lenh CHI DOC
    // (soi ngon ngu) duoc chay tren MOI trang facebook/mbasic -- ngon ngu phai
    // doc o trang chu / trang cai dat, khong phai o Business Suite.
    // PHAI la trang facebook that: process-script con chay o trang nen cua
    // extension (moz-extension://...) -- cai do bao ve truoc va lam nhieu.
    var lenh_moi_noi = ((cmd.action === "langscan" || cmd.action === "readmain"
                          || cmd.action === "setlang")
                        && href.indexOf("facebook.com") !== -1);
    if (!lenh_moi_noi
        && href.indexOf("business.facebook.com") === -1
        && href.indexOf("facebook.com/groups/") === -1) { return; }

    // Trang nay dung ra rat lau sau khi "load"; cho mot nhip cho no ve xong.
    win.setTimeout(function () {
      try { runCommand(win, cmd); }
      catch (e) { report("error", String(e)); }
    }, cmd.delay || 8000);
  }

  var observer = {
    observe: function (subject, topic) {
      if (topic !== "content-document-global-created") { return; }
      var win = subject;
      try {
        if (win.top !== win) { return; }      // chi khung ngoai cung
        win.addEventListener("load", function onload() {
          win.removeEventListener("load", onload);
          onPage(win);
        }, { once: true });
      } catch (e) {}
    },
  };

  Services.obs.addObserver(observer, "content-document-global-created");
}
