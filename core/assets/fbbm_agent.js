/* Process script: ADD fanpage vao Business Manager tren business.facebook.com.
 *
 * Chay trong TIEN TRINH NOI DUNG (nhu fbcreate_agent.js). Thao tac bang su kien
 * "nguoi that" (setHandlingUserInput -> isTrusted), mo Firefox BINH THUONG.
 *
 * Bridge RIENG (khong dam 4 agent kia):
 *   sendSyncMessage("qlfpbm:cmd")     -> cha doc <profile>/qlfp-bm.json
 *   sendAsyncMessage("qlfpbm:report") -> cha ghi <profile>/qlfp-bm-result.json (tron msg.data)
 *
 * Lenh: { action:"addbm", bm_id, page_id, page_ten }  -> mo settings/pages cua BM,
 *   doc TEN BM, bam "Thêm" -> "Thêm Trang" -> chon page -> xac nhan.
 *   Bao: { state:"addbm-done", ok, ten_bm, detail }.  Lenh "probe": dump cau truc.
 */
"use strict";

if (typeof sendAsyncMessage === "function") {

  var lines = [];
  function report(obj) {
    try { obj.log = lines.slice(-25); sendAsyncMessage("qlfpbm:report", obj); } catch (e) {}
  }
  function note(s) { lines.push(String(s)); }
  function getCommand() {
    try {
      var a = sendSyncMessage("qlfpbm:cmd");
      var raw = a && a.length ? a[0] : "";
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }
  function low(s) { return (s || "").toLowerCase(); }
  function txt(el) { try { return (el.textContent || "").trim(); } catch (e) { return ""; } }
  function vis(el) {
    try { var b = el.getBoundingClientRect(); return b.width > 6 && b.height > 6 && el.offsetParent !== null; }
    catch (e) { return false; }
  }
  function withUserInput(win, fn) {
    try { win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try { return fn(); } finally { try { win.windowUtils.setHandlingUserInput(false); } catch (e) {} }
  }
  function setNative(win, el, val) {
    try {
      var proto = el.tagName === "TEXTAREA" ? win.HTMLTextAreaElement.prototype : win.HTMLInputElement.prototype;
      var setter = Object.getOwnPropertyDescriptor(proto, "value").set;
      el.focus(); setter.call(el, val);
      el.dispatchEvent(new win.Event("input", { bubbles: true }));
      el.dispatchEvent(new win.Event("change", { bubbles: true }));
      return true;
    } catch (e) { return false; }
  }
  // Go TUNG KY TU (autocomplete FB chi hien khi co keystroke that).
  function goTung(win, el, val) {
    try {
      el.focus();
      try { el.select(); } catch (e) {}
      var setter = Object.getOwnPropertyDescriptor(win.HTMLInputElement.prototype, "value").set;
      setter.call(el, "");
      el.dispatchEvent(new win.Event("input", { bubbles: true }));
      var cur = "";
      for (var i = 0; i < val.length; i++) {
        var c = val.charAt(i);
        withUserInput(win, function () {
          el.dispatchEvent(new win.KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: c }));
          el.dispatchEvent(new win.KeyboardEvent("keypress", { bubbles: true, cancelable: true, key: c }));
        });
        cur += c; setter.call(el, cur);
        el.dispatchEvent(new win.InputEvent("input", { bubbles: true, inputType: "insertText", data: c }));
        withUserInput(win, function () { el.dispatchEvent(new win.KeyboardEvent("keyup", { bubbles: true, cancelable: true, key: c })); });
      }
      el.dispatchEvent(new win.Event("change", { bubbles: true }));
      return el.value;
    } catch (e) { note("goTung loi " + e); return ""; }
  }
  function clickReal(win, el) {
    try {
      var r = el.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      function pe(t) { return new win.PointerEvent(t, { bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0, pointerType: "mouse", isPrimary: true }); }
      function me(t) { return new win.MouseEvent(t, { bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0 }); }
      withUserInput(win, function () {
        el.dispatchEvent(pe("pointerdown")); el.dispatchEvent(me("mousedown"));
        el.dispatchEvent(pe("pointerup")); el.dispatchEvent(me("mouseup")); el.dispatchEvent(me("click"));
      });
      return true;
    } catch (e) { return false; }
  }

  // ------- doc ten BM ------------------------------------------------------
  function tenBM(win) {
    var d = win.document;
    // Dong phu "Trang quan ly tai san doanh nghiep" -> ten BM la dong ngay tren.
    try {
      var all = d.querySelectorAll('span,div,h1,h2');
      for (var i = 0; i < all.length; i++) {
        if (/quản lý tài sản doanh nghiệp|business asset/i.test(txt(all[i]))) {
          var box = all[i].closest("a,div");
          if (box) {
            var sp = box.querySelectorAll('span,div,h1,h2');
            for (var j = 0; j < sp.length; j++) {
              var t = txt(sp[j]);
              if (t && !/quản lý tài sản|business asset|cài đặt/i.test(t) && t.length < 60) { return t; }
            }
          }
        }
      }
    } catch (e) {}
    // du phong: document.title bo duoi
    try { return (d.title || "").replace(/\s*[|\-–].*$/, "").trim().slice(0, 60); } catch (e) { return ""; }
  }

  // ------- tim nut theo chu -----------------------------------------------
  function nutTheoChu(win, reArr, trong) {
    // Nhe: trong dialog thi quet dialog (nho); ngoai thi GIOI HAN so phan tu (trang BM khong lo).
    var root = trong || win.document;
    var bs = root.querySelectorAll('[role="button"],button,[role="menuitem"],a[role="link"]');
    var gioi = trong ? bs.length : Math.min(bs.length, 600);
    for (var i = 0; i < gioi; i++) {
      var s = (bs[i].getAttribute("aria-label") || txt(bs[i])).replace(/\s+/g, " ").trim();
      if (!s) { continue; }
      for (var k = 0; k < reArr.length; k++) {
        if (reArr[k].test(s)) { if (vis(bs[i])) { return bs[i]; } }
      }
    }
    return null;
  }

  function dump(win) {
    var d = win.document, out = [];
    out.push("url=" + win.location.href.slice(0, 60));
    out.push("tenBM=" + tenBM(win));
    try {
      var bs = d.querySelectorAll('[role="button"],button,[role="menuitem"]'), bl = [];
      for (var i = 0; i < bs.length && bl.length < 18; i++) {
        var s = (bs[i].getAttribute("aria-label") || txt(bs[i])).replace(/\s+/g, " ").trim();
        if (s && vis(bs[i])) { bl.push(s.slice(0, 22)); }
      }
      out.push("NUT=" + JSON.stringify(bl));
      out.push("dialog=" + d.querySelectorAll('[role="dialog"]').length);
      var dlg = d.querySelector('[role="dialog"]');
      if (dlg) {
        out.push("DLG_TXT=" + ((dlg.innerText || "").replace(/\s+/g, " ").slice(0, 260)));
        out.push("DLG_CHECK=" + dlg.querySelectorAll('[role="checkbox"],input[type="checkbox"]').length);
      }
      var ins = d.querySelectorAll('input'), il = [];
      for (var m = 0; m < ins.length && il.length < 6; m++) {
        il.push((ins[m].type || "?") + ":" + (ins[m].getAttribute("aria-label") || ins[m].placeholder || "?").slice(0, 18));
      }
      out.push("INPUT=" + JSON.stringify(il));
    } catch (e) {}
    return out.join(" ; ");
  }

  // ------- luong TAO BM (tai san doanh nghiep) ----------------------------
  // Tim input trong dialog theo nhan (aria-label / placeholder / label ke ben).
  function inputTheoNhan(root, reArr) {
    var ins = root.querySelectorAll('input[type="text"],input:not([type]),input[type="email"]');
    for (var a = 0; a < ins.length; a++) {
      if (!vis(ins[a])) { continue; }
      var lbl = (ins[a].getAttribute("aria-label") || ins[a].placeholder || "");
      for (var k = 0; k < reArr.length; k++) { if (reArr[k].test(lbl)) { return ins[a]; } }
    }
    return null;
  }
  // Ten hien thi cua acc dang dang nhap (lam ten BM + tach Ten/Ho). Doc nhieu nguon.
  function tenAccFB(win) {
    var d = win.document;
    // 1) module noi bo cua FB (chac nhat neu voi toi duoc)
    try {
      var r = (win.wrappedJSObject && win.wrappedJSObject.require) || win.require;
      if (r) { var u = r("CurrentUserInitialData"); if (u && u.NAME) { return String(u.NAME).trim(); } }
    } catch (e) {}
    // 2) nut/anh dai dien co aria-label "Ảnh đại diện của <Ten>" / profile link
    try {
      var els = d.querySelectorAll('[aria-label]');
      for (var i = 0; i < els.length && i < 400; i++) {
        var m = /(?:ảnh đại diện của|profile picture of|tài khoản của)\s+(.+)/i.exec(els[i].getAttribute("aria-label") || "");
        if (m && m[1] && m[1].trim().length > 1) { return m[1].trim().slice(0, 60); }
      }
    } catch (e) {}
    return "";
  }
  function tachTen(hoTen) {
    // FB form: o "Tên" (given) va "Họ" (family). VN: ho dung dau -> Ho = tu dau, Ten = phan con lai.
    var t = (hoTen || "").replace(/\s+/g, " ").trim();
    if (!t) { return { ten: "", ho: "" }; }
    var p = t.split(" ");
    if (p.length === 1) { return { ten: p[0], ho: p[0] }; }
    return { ho: p[0], ten: p.slice(1).join(" ") };
  }

  // Luong tao BM (theo ANH thao tac tay 2026-09-10):
  //   bam switcher (goc tren trai) -> "Tạo trang quản lý tài sản doanh nghiệp" -> dialog:
  //   dien "Tên hồ sơ doanh nghiệp"(=tenAcc) + "Tên"(given) + "Họ"(family) + "Email" -> bam "Tạo".
  // Moi buoc 1 thao tac roi cho ~3s (nhe, tranh crash tab business).
  function taoBM(win, cmd, cb) {
    var buoc = 0, MAX = 26;
    var hoTen = "", tach = { ten: "", ho: "" };
    var email = (cmd.email || "").trim();
    var daSwitcher = false, daMenu = false, daDien = false, daTao = false, dangGo = false, daDump = false;
    var bmTruoc = "";
    function inputsHienTrong(dlg) {
      var out = [];
      try {
        var ins = dlg.querySelectorAll('input[type="text"],input[type="email"],input:not([type])');
        for (var i = 0; i < ins.length; i++) { if (vis(ins[i])) { out.push(ins[i]); } }
      } catch (e) {}
      return out;
    }
    function laDialogTaoBM(dlg) {
      try { return /tài sản doanh nghiệp|hồ sơ doanh nghiệp|business (portfolio|manager)|jasper/i.test(dlg.innerText || ""); }
      catch (e) { return false; }
    }
    // Dien LAN LUOT nhieu (o, chu) roi goi xong().
    function dienNhieu(win, cap, xong) {
      (function tiep(i) {
        if (i >= cap.length) { win.setTimeout(xong, 300); return; }
        var it = cap[i];
        if (!it.el || !it.val) { return tiep(i + 1); }
        try { clickReal(win, it.el); } catch (e) {}
        goCham(win, it.el, it.val, function () { win.setTimeout(function () { tiep(i + 1); }, 350); });
      })(0);
    }
    function later(ms) { win.setTimeout(function () {
      try { buocTiep(); } catch (e) { cb({ ok: false, bm_id: "", ten_bm: hoTen, detail: "LOI: " + e }); }
    }, ms); }
    later(4000);
    function bmIdHienTai() {
      var m = /business_id=(\d{6,})/.exec(win.location.href || ""); return m ? m[1] : "";
    }
    function buocTiep() {
      var d = win.document;
      if (low(win.location.href).indexOf("/checkpoint") !== -1) {
        cb({ ok: false, bm_id: "", ten_bm: hoTen, detail: "ACC BỊ CHECKPOINT" }); return;
      }
      if (dangGo) { return later(1500); }
      buoc++;
      if (buoc > MAX) { cb({ ok: daTao, bm_id: bmIdHienTai(), ten_bm: hoTen, detail: "hết bước; " + dump(win) }); return; }
      if (!hoTen) { hoTen = tenAccFB(win); tach = tachTen(hoTen); bmTruoc = bmIdHienTai(); }
      var dlg = d.querySelector('[role="dialog"]');
      var dlgBM = dlg && laDialogTaoBM(dlg);
      report({ state: "seen", detail: "B" + buoc + " ten='" + hoTen.slice(0, 24) + "' dlg=" + (dlg ? 1 : 0)
               + " dlgBM=" + (dlgBM ? 1 : 0) + " sw=" + daSwitcher + " menu=" + daMenu + " dien=" + daDien + " tao=" + daTao });
      if (dlg && !daDump) { daDump = true; report({ state: "seen", detail: "DIALOG: " + dump(win) }); }

      // Da bam Tạo va dialog dong = tao xong.
      if (daTao && !dlg) {
        var bmMoi = bmIdHienTai();
        cb({ ok: true, bm_id: bmMoi, ten_bm: hoTen, detail: "đã tạo BM" + (bmMoi ? " " + bmMoi : "") }); return;
      }

      // ---- Dialog tao BM auto hien (anh 1): dien theo THU TU o roi bam Tạo ----
      if (dlgBM) {
        if (!daDien) {
          var ins = inputsHienTrong(dlg);
          // Thu tu form: [Tên hồ sơ DN, Tên(given), Họ(family), Email]. Bo o an/khong phai text.
          if (ins.length < 1) { note("dialog BM chua co input; " + dump(win)); return later(2000); }
          if (!hoTen) { hoTen = "BM " + (cmd.acc_id || ""); tach = tachTen(hoTen); }
          var cap = [{ el: ins[0], val: hoTen }];
          if (ins.length >= 4) { cap.push({ el: ins[1], val: tach.ten }); cap.push({ el: ins[2], val: tach.ho }); cap.push({ el: ins[3], val: email }); }
          else if (ins.length === 2) { cap.push({ el: ins[1], val: email }); }        // chi ten BM + email
          else if (ins.length === 3) { cap.push({ el: ins[1], val: tach.ten }); cap.push({ el: ins[2], val: email }); }
          daDien = true; dangGo = true;
          dienNhieu(win, cap, function () { dangGo = false; note("da dien " + cap.length + " o (ten='" + hoTen.slice(0, 20) + "')"); later(2000); });
          return;
        }
        var bTao = nutTheoChu(win, [/^tạo$|^create$|^tạo hồ sơ|^done$/i], dlg);
        if (bTao) { clickReal(win, bTao); daTao = true; note("bam Tạo BM"); return later(4000); }
        note("chua thay nut Tạo trong dialog; " + dump(win));
        return later(2500);
      }

      // ---- Khong co dialog BM: mo switcher -> "Tạo trang quản lý tài sản doanh nghiệp" ----
      if (!dlg) {
        if (daTao) { return later(2500); }
        if (!daSwitcher) {
          var sw = timSwitcher(win);
          if (sw) { clickReal(win, sw); daSwitcher = true; note("bam switcher"); return later(3000); }
          return later(2500);
        }
        var mi = nutTheoChu(win, [/tạo trang quản lý tài sản doanh nghiệp|tạo tài khoản doanh nghiệp|create business|tạo doanh nghiệp mới/i]);
        if (mi) { clickReal(win, mi); daMenu = true; note("bam menu Tạo trang quản lý tài sản DN"); return later(3500); }
        daSwitcher = false;
        return later(2500);
      }
      // Dialog KHAC (tooltip onboarding "Công cụ tạo nội dung..." / lời nhắc) -> ĐÓNG nó rồi mở switcher.
      var dong = nutTheoChu(win, [/^ok$|^đóng$|^bỏ qua$|^close$|^không phải bây giờ$|^để sau$|^got it$|^đã hiểu$|^xong$/i], dlg);
      if (dong) { clickReal(win, dong); note("đóng dialog phụ: " + txt(dong).slice(0, 16)); daSwitcher = false; return later(2000); }
      // Khong thay nut dong -> thu bam nut X (aria-label Close/Đóng) hoac Escape
      var x = dlg.querySelector('[aria-label="Đóng"],[aria-label="Close"],[aria-label="Đóng​"]');
      if (x && vis(x)) { clickReal(win, x); note("bam X dong dialog phu"); return later(2000); }
      return later(2000);
    }
  }
  // Nut switcher goc tren-trai: nut dau tien co role=button gan mep tren-trai + co chevron/anh.
  function timSwitcher(win) {
    try {
      var bs = win.document.querySelectorAll('[role="button"]');
      for (var i = 0; i < bs.length && i < 60; i++) {
        var b = bs[i]; if (!vis(b)) { continue; }
        var r = b.getBoundingClientRect();
        if (r.top < 90 && r.left < 300 && r.width > 90 && r.height > 24) { return b; }
      }
    } catch (e) {}
    return null;
  }

  // ------- luong add page vao BM (wizard nhieu buoc) ----------------------
  // O ten page trong dialog: ban ghi thao tac tay = INPUT[role=combobox][type=text].
  function timTenInput(dlg) {
    var ins = dlg.querySelectorAll('input[role="combobox"], input[type="text"]');
    for (var a = 0; a < ins.length; a++) {
      if (!vis(ins[a])) { continue; }
      var lbl = (ins[a].getAttribute("aria-label") || ins[a].placeholder || "");
      if (ins[a].getAttribute("role") === "combobox" || /Tên hoặc URL|Name or URL|URL Trang/i.test(lbl)) { return ins[a]; }
    }
    return null;
  }
  // Goi y page = DIV[role=option] 'Ten pageBlogger' (ban ghi). Uu tien dong BAT DAU bang ten.
  function timGoiY(win, ten) {
    if (!ten) { return null; }
    var opts = win.document.querySelectorAll('[role="option"]');
    var duPhong = null, gioi = Math.min(opts.length, 200);
    for (var i = 0; i < gioi; i++) {
      var t = txt(opts[i]).replace(/\s+/g, " ").trim();
      if (!t || !vis(opts[i])) { continue; }
      if (t.indexOf(ten) === 0) { return opts[i]; }
      if (t.indexOf(ten) !== -1 && !duPhong) { duPhong = opts[i]; }
    }
    return duPhong;
  }
  // Go CHAM tung ky tu theo nhip (110ms), CHI su kien input, KHONG su kien phim, KHONG
  // setHandlingUserInput: giong nguoi go that, tranh sap o combobox (ban goTung dot lam crash).
  function goCham(win, el, val, xong) {
    var setter = Object.getOwnPropertyDescriptor(win.HTMLInputElement.prototype, "value").set;
    try { el.focus(); } catch (e) {}
    var i = 0;
    (function tiep() {
      if (i >= val.length) { win.setTimeout(xong, 300); return; }
      try {
        setter.call(el, val.slice(0, i + 1));
        el.dispatchEvent(new win.InputEvent("input", { bubbles: true, inputType: "insertText", data: val.charAt(i) }));
      } catch (e) { note("goCham loi " + e); }
      i++;
      win.setTimeout(tiep, 110);
    })();
  }
  function checkboxTrong(dlg) {
    var cbs = dlg.querySelectorAll('input[type="checkbox"]');
    for (var i = 0; i < cbs.length; i++) { if (vis(cbs[i]) && !cbs[i].checked) { return cbs[i]; } }
    return null;
  }
  // Luong add page (theo BAN GHI thao tac tay 2026-09-08):
  //   Thêm -> menuitem "Thêm Trang Facebook có sẵn" -> go ten vao combobox -> chon role=option
  //   -> Tiếp -> Tiếp -> tich checkbox -> "Thêm Trang" -> "Xong" -> dialog dong = xong.
  // Moi buoc 1 thao tac roi cho 2.5-3.5s (nhe, khong hammer trang).
  function addBM(win, cmd, cb) {
    var buoc = 0, MAX = 26;
    var ten = (cmd.page_ten || "").trim();
    var giaTri = ten || (cmd.page_id ? String(cmd.page_id) : "");
    var tenbmCache = "";
    function tenbmLazy() { if (!tenbmCache) { tenbmCache = tenBM(win); } return tenbmCache; }
    var daMenu = false, daType = false, dangGo = false, daChon = false, daThemTrang = false, daXong = false, soTiep = 0;
    var soCheckpoint = 0;   // an han: fbskip_agent bam "Bo qua" neu checkpoint MEM
    function later(ms) { win.setTimeout(function () {
      try { buocTiep(); } catch (e) { report({ state: "addbm-done", ok: false, ten_bm: tenbmCache, detail: "LOI: " + e }); }
    }, ms); }
    later(4000);
    function buocTiep() {
      var d = win.document;
      if (low(win.location.href).indexOf("/checkpoint") !== -1) {
        if (++soCheckpoint <= 4) { return later(3000); }     // cho fbskip bam "Bo qua" (~12s)
        cb({ ok: false, ten_bm: tenbmLazy(), detail: "ACC BỊ CHECKPOINT" }); return;
      }
      if (dangGo) { return later(1500); }
      buoc++;
      if (buoc > MAX) {
        cb({ ok: daThemTrang, ten_bm: tenbmLazy(),
             detail: "hết bước (type=" + daType + " chon=" + daChon + " tiep=" + soTiep + " themtrang=" + daThemTrang + " xong=" + daXong + ")" });
        return;
      }
      var dlg = d.querySelector('[role="dialog"]');
      report({ state: "seen", detail: "B" + buoc + " dlg=" + (dlg ? 1 : 0) + " menu=" + daMenu + " type=" + daType + " chon=" + daChon + " tiep=" + soTiep + " tt=" + daThemTrang + " xong=" + daXong });
      if ((daThemTrang || daXong) && !dlg) {
        cb({ ok: true, ten_bm: tenbmLazy(), detail: "đã thêm page “" + giaTri + "” vào BM" }); return;
      }
      if (!dlg) {
        if (daThemTrang) { return later(2000); }
        if (!daMenu) {
          var them = nutTheoChu(win, [/^(\+\s*)?Thêm$/i, /^Add$/i]);
          if (them) { clickReal(win, them); daMenu = true; note("bam Thêm"); return later(3000); }
          return later(2500);
        }
        var mi = nutTheoChu(win, [/Thêm Trang/i, /Add Page/i]);
        if (mi) { clickReal(win, mi); note("bam menu Thêm Trang co san"); return later(3500); }
        daMenu = false;               // menu dong mat -> bam Thêm lai
        return later(2500);
      }
      if (!daType) {
        var inp = timTenInput(dlg);
        if (!inp || !giaTri) { return later(2500); }
        daType = true; dangGo = true;
        try { clickReal(win, inp); } catch (e) {}
        goCham(win, inp, giaTri, function () { dangGo = false; note("da go ten: " + giaTri.slice(0, 30)); later(2500); });
        return;
      }
      if (!daChon) {
        var g = timGoiY(win, ten || giaTri);
        if (g) { clickReal(win, g); daChon = true; note("chon goi y: " + txt(g).slice(0, 30)); return later(2500); }
        return later(2000);
      }
      // sau khi chon: uu tien checkbox -> "Thêm Trang" (ket thuc) -> "Xong" -> "Tiếp"
      var ck = checkboxTrong(dlg);
      if (ck) { clickReal(win, ck); note("tich checkbox"); return later(2500); }
      var bThemTrang = nutTheoChu(win, [/^Thêm Trang$/i, /^Add Page$/i], dlg);
      if (bThemTrang && !daThemTrang) { clickReal(win, bThemTrang); daThemTrang = true; note("bam Thêm Trang (ket thuc)"); return later(3500); }
      var bXong = nutTheoChu(win, [/^(Xong|Done)$/i], dlg);
      if (bXong) { clickReal(win, bXong); daXong = true; note("bam Xong"); return later(3000); }
      var bTiep = nutTheoChu(win, [/^(Tiếp|Tiếp tục|Continue|Next)$/i], dlg);
      if (bTiep) { clickReal(win, bTiep); soTiep++; note("bam Tiếp " + soTiep); return later(3500); }
      later(2500);
    }
  }

  function onPage(win) {
    if (low(win.location.href).indexOf("facebook.com") === -1) { return; }
    var done = false;
    var waited = 0, step = 1000, cap = 100000;
    win.setTimeout(function tick() {
      var cmd = getCommand();
      if (cmd && cmd.action === "record" && !done) {
        // CHE DO QUAN SAT: KHONG bam gi. Ghi lai thao tac TAY cua nguoi dung (click/go/focus)
        // + goi y hien ra, de hoc dung luong roi lam theo.
        done = true;
        var d0 = win.document, dem = 0, sk = [];
        function moTa(el) {
          try {
            if (!el || !el.getAttribute) { return String(el && el.nodeName); }
            var t = (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 40);
            return el.tagName + (el.getAttribute("role") ? "[role=" + el.getAttribute("role") + "]" : "") +
                   (el.getAttribute("aria-label") ? "[aria=" + el.getAttribute("aria-label").slice(0, 30) + "]" : "") +
                   (el.type ? "[type=" + el.type + "]" : "") + " '" + t + "'";
          } catch (e) { return "?"; }
        }
        function ghi(loai, el, them) {
          dem++;
          var dong = "REC#" + dem + " " + loai + ": " + moTa(el) + (them ? " | " + them : "");
          sk.push(dong);
          report({ state: "seen", detail: dong, items: sk.slice(-200) });
        }
        d0.addEventListener("click", function (e) { ghi("CLICK", e.target, "cha=" + moTa(e.target.parentElement)); }, true);
        d0.addEventListener("focusin", function (e) { ghi("FOCUS", e.target); }, true);
        d0.addEventListener("input", function (e) {
          ghi("INPUT", e.target, "value=" + String(e.target.value || e.target.textContent || "").slice(0, 40));
        }, true);
        d0.addEventListener("keydown", function (e) { if (e.key === "Enter") { ghi("ENTER", e.target); } }, true);
        // moi 3s: neu co dialog, ghi cac goi y (role=option/listitem) dang hien
        var lanDlg = "";
        win.setInterval(function () {
          try {
            var dlg = d0.querySelector('[role="dialog"]');
            var opts = d0.querySelectorAll('[role="option"],[role="listitem"]');
            var mau = [];
            for (var i = 0; i < opts.length && mau.length < 5; i++) {
              var tt = (opts[i].textContent || "").replace(/\s+/g, " ").trim().slice(0, 40);
              if (tt) { mau.push(moTa(opts[i])); }
            }
            var key = (dlg ? "D" : "-") + "|" + mau.join(";");
            if (key !== lanDlg) { lanDlg = key; report({ state: "seen", detail: "REC-STATE dialog=" + (dlg ? 1 : 0) + " goiy=" + JSON.stringify(mau) }); }
          } catch (e) {}
        }, 3000);
        report({ state: "seen", detail: "REC bat dau ghi — ban thao tac tay, toi chi ghi, khong bam." });
        return;
      }
      if (cmd && cmd.action === "bmpages" && !done) {
        // XAC MINH doc lap: trang Cai dat > Trang cua BM co chua ten cac page (cmd.tens) khong.
        if (waited < 9000) { waited += step; win.setTimeout(tick, step); return; }
        done = true;
        var main = win.document.querySelector('[role="main"]') || win.document.body;
        var vanBan = "";
        try { vanBan = (main.innerText || "").replace(/\s+/g, " "); } catch (e) {}
        var co = [], thieu = [];
        var tens = cmd.tens || [];
        for (var i = 0; i < tens.length; i++) { (vanBan.indexOf(tens[i]) !== -1 ? co : thieu).push(tens[i]); }
        report({ state: "bmpages", co: co, thieu: thieu, ten_bm: tenBM(win),
                 mau: vanBan.slice(0, 300), rong: /Chưa thêm Trang nào/i.test(vanBan) });
        return;
      }
      if (cmd && cmd.action === "listbm" && !done) {
        // FB tu mo BM mac dinh -> doc business_id tu URL + ten BM. Cho URL co business_id.
        var href0 = win.location.href;
        if (href0.indexOf("business_id=") === -1 && waited < 15000) { waited += step; win.setTimeout(tick, step); return; }
        done = true;
        var items = [], seen = {};
        function themBM(id, nm) { if (id && !seen[id]) { seen[id] = 1; items.push({ id: id, name: (nm || "").slice(0, 60) }); } }
        var m0 = /business_id=(\d{6,})/.exec(href0);
        if (m0) { themBM(m0[1], tenBM(win)); }
        // neu co nhieu BM (link chua business_id khac) -> them
        try {
          var links = win.document.querySelectorAll('a[href*="business_id="]');
          for (var i = 0; i < links.length && items.length < 20; i++) {
            var mm = /business_id=(\d{6,})/.exec(links[i].getAttribute("href") || "");
            if (mm) { themBM(mm[1], (links[i].getAttribute("aria-label") || txt(links[i])).replace(/\s+/g, " ").trim()); }
          }
        } catch (e) {}
        report({ state: "bms", items: items, detail: "url=" + href0.slice(0, 80) });
        return;
      }
      if (cmd && cmd.action === "listpages" && !done) {
        if (waited < 9000) { waited += step; win.setTimeout(tick, step); return; }
        done = true;
        var d = win.document, items = [], seen = {};
        // "Trang ban quan ly": the link toi tung page (profile.php?id / /<id> / aria-label)
        var links = d.querySelectorAll('a[href*="/pages/"] , a[href*="profile.php?id="], a[role="link"][aria-label]');
        for (var i = 0; i < links.length; i++) {
          var h = links[i].getAttribute("href") || "";
          var m = /(?:profile\.php\?id=|\/)(\d{6,})/.exec(h);
          var nm = (links[i].getAttribute("aria-label") || txt(links[i])).replace(/\s+/g, " ").trim();
          if (m && nm && !seen[m[1]] && !/facebook|meta|thong bao|tim kiem/i.test(nm)) {
            seen[m[1]] = 1; items.push({ id: m[1], name: nm.slice(0, 60) });
          }
          if (items.length >= 20) break;
        }
        report({ state: "pages", items: items, detail: "dump: " + dump(win) });
        return;
      }
      if (cmd && cmd.action === "probe" && !done) {
        if (waited < 8000) { waited += step; win.setTimeout(tick, step); return; }
        done = true; report({ state: "addbm-done", ok: false, ten_bm: tenBM(win), detail: "probe: " + dump(win) }); return;
      }
      if (cmd && cmd.action === "addbm" && !done) {
        done = true;
        report({ state: "seen", detail: "mo BM: " + win.location.href.slice(0, 60) + " tenBM=" + tenBM(win) });
        addBM(win, cmd, function (kq) {
          report({ state: "addbm-done", ok: !!kq.ok, ten_bm: kq.ten_bm || "", detail: kq.detail || "" });
        });
        return;
      }
      if (cmd && cmd.action === "taobm" && !done) {
        done = true;
        report({ state: "seen", detail: "tao BM: " + win.location.href.slice(0, 60) });
        taoBM(win, cmd, function (kq) {
          report({ state: "taobm-done", ok: !!kq.ok, bm_id: kq.bm_id || "", ten_bm: kq.ten_bm || "", detail: kq.detail || "" });
        });
        return;
      }
      waited += step;
      if (waited < cap) { win.setTimeout(tick, step); }
    }, 3000);
  }

  var observer = {
    observe: function (subject, topic) {
      if (topic !== "content-document-global-created") { return; }
      var win = subject;
      try {
        if (win.top !== win) { return; }
        win.addEventListener("load", function onl() { win.removeEventListener("load", onl); onPage(win); }, { once: true });
      } catch (e) {}
    },
  };
  Services.obs.addObserver(observer, "content-document-global-created");
}
