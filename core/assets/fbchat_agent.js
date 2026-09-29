/* Process script: TRA LOI TIN NHAN ban be tren facebook.com/messages (Messenger web).
 *
 * Chay trong TIEN TRINH NOI DUNG (nhu fblogin_agent.js). Thao tac bang su kien "nguoi
 * that" (setHandlingUserInput -> isTrusted), trinh duyet mo BINH THUONG (khong
 * --remote-debugging-port) -> tranh chong bot.
 *
 * Bridge RIENG (khong dam agent khac):
 *   sendSyncMessage("qlfpm:cmd")     -> cha doc <profile>/qlfp-msg.json
 *   sendAsyncMessage("qlfpm:report") -> cha ghi <profile>/qlfp-msg-result.json (tron msg.data)
 *
 * Lenh 1: { action:"scan", so_toi_da:N } -> agent bao { state:"scanned", items:[{id,ban,tin}] }
 * Lenh 2: { action:"reply", replies:[{id,ban,tra_loi}] } -> agent gui tung cai, bao
 *         { state:"reply-sent", sent:[id,...] }
 * Messenger la SPA: mot lan mo trang xu ly ca scan lan reply (cha ghi lenh reply sau khi
 * co cau tra loi tu Gemini). Gui = go vao o soan (contenteditable) + Enter.
 */
"use strict";

if (typeof sendAsyncMessage === "function") {

  var lines = [];
  function report(obj) {
    try {
      obj.log = lines.slice(-30);
      sendAsyncMessage("qlfpm:report", obj);
    } catch (e) {}
  }
  function note(s) { lines.push(String(s)); }
  function getCommand() {
    try {
      var a = sendSyncMessage("qlfpm:cmd");
      var raw = a && a.length ? a[0] : "";
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function low(s) { return (s || "").toLowerCase(); }
  function vis(el) {
    try { var b = el.getBoundingClientRect(); return b.width > 8 && b.height > 8 && el.offsetParent !== null; }
    catch (e) { return false; }
  }
  function threadId(href) {
    // Ho tro ca /messages/t/<id>/ lan /messages/e2ee/t/<id>/ (ma hoa dau cuoi).
    var m = /\/t\/(\d+)/.exec(href || "");
    return m ? m[1] : "";
  }
  function tenSach(s) {
    // Bo cac nhan trang thai FB dinh vao sau ten trong danh sach hoi thoai.
    return (s || "")
      .replace(/Tin nhắn (chưa đọc|đang chờ|đã xem|mới)/gi, "")
      .replace(/chưa đọc|đang chờ|đã gửi|Đang hoạt động.*/gi, "")
      .replace(/\s+/g, " ").trim().slice(0, 60);
  }
  function txt(el) { try { return (el.textContent || "").trim(); } catch (e) { return ""; } }

  // ------- su kien tin cay -------------------------------------------------
  function withUserInput(win, fn) {
    var wu = win.windowUtils || (win.QueryInterface && win);
    try { win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try { return fn(); } finally {
      try { win.windowUtils.setHandlingUserInput(false); } catch (e) {}
    }
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
  /* Go vao o soan Messenger (contenteditable Lexical). execCommand("insertText") hay tra TRUE ma o van
   * TRONG (Lexical bo qua) -> phai XAC MINH chu da vao o sau moi cach; that bai thi doi cach:
   *   1) execCommand insertText  2) InputEvent beforeinput+input (Lexical nghe beforeinput)
   *   3) paste ClipboardEvent    4) go tung ky tu (keydown + beforeinput + input).
   * Tra {ok, cach}. */
  function _coChu(el, val) {
    var t = txt(el).replace(/\s+/g, " ");
    return t.indexOf(val.slice(0, 8)) !== -1;
  }
  function _focusCuoi(win, el) {
    try { el.focus(); var sel = win.getSelection(); sel.selectAllChildren(el); sel.collapseToEnd(); } catch (e) {}
  }
  function goVaoOSoan(win, el, val) {
    var doc = win.document;
    _focusCuoi(win, el);
    try { withUserInput(win, function () { doc.execCommand("insertText", false, val); }); } catch (e) {}
    if (_coChu(el, val)) { return { ok: true, cach: "execCommand" }; }
    try {
      withUserInput(win, function () {
        el.dispatchEvent(new win.InputEvent("beforeinput", { bubbles: true, cancelable: true, inputType: "insertText", data: val }));
        el.dispatchEvent(new win.InputEvent("input", { bubbles: true, inputType: "insertText", data: val }));
      });
    } catch (e) {}
    if (_coChu(el, val)) { return { ok: true, cach: "beforeinput" }; }
    try {
      var dt = new win.DataTransfer(); dt.setData("text/plain", val);
      withUserInput(win, function () {
        el.dispatchEvent(new win.ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: dt }));
      });
    } catch (e) {}
    if (_coChu(el, val)) { return { ok: true, cach: "paste" }; }
    try {
      _focusCuoi(win, el);
      withUserInput(win, function () {
        for (var i = 0; i < val.length; i++) {
          var c = val[i];
          el.dispatchEvent(new win.KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: c }));
          el.dispatchEvent(new win.InputEvent("beforeinput", { bubbles: true, cancelable: true, inputType: "insertText", data: c }));
          el.dispatchEvent(new win.InputEvent("input", { bubbles: true, inputType: "insertText", data: c }));
          el.dispatchEvent(new win.KeyboardEvent("keyup", { bubbles: true, cancelable: true, key: c }));
        }
      });
    } catch (e) {}
    if (_coChu(el, val)) { return { ok: true, cach: "tung-ky-tu" }; }
    return { ok: false, cach: "khong-cach-nao (o soan: " + JSON.stringify(txt(el).slice(0, 40)) + ")" };
  }
  function setEditable(win, el, val) { return goVaoOSoan(win, el, val).ok; }
  function nutGui(win) {
    var doc = win.document;
    var c = doc.querySelectorAll('[aria-label="Gửi"], [aria-label="Send"], [aria-label*="Nhấn Enter để gửi"], [aria-label*="Press Enter to send"], [aria-label*="Gửi tin nhắn"], [aria-label*="Send message"]');
    for (var i = 0; i < c.length; i++) { if (vis(c[i])) { return c[i]; } }
    return null;
  }
  function clickReal(win, el) {
    try {
      var r = el.getBoundingClientRect(); var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      function pe(t) { return new win.PointerEvent(t, { bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0, pointerType: "mouse", isPrimary: true }); }
      function me(t) { return new win.MouseEvent(t, { bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0 }); }
      withUserInput(win, function () {
        el.dispatchEvent(pe("pointerdown")); el.dispatchEvent(me("mousedown"));
        el.dispatchEvent(pe("pointerup")); el.dispatchEvent(me("mouseup")); el.dispatchEvent(me("click"));
      });
      return true;
    } catch (e) { return false; }
  }
  function pressEnter(win, el) {
    try {
      withUserInput(win, function () {
        ["keydown", "keypress", "keyup"].forEach(function (t) {
          el.dispatchEvent(new win.KeyboardEvent(t, { bubbles: true, cancelable: true, key: "Enter", code: "Enter", keyCode: 13, which: 13 }));
        });
      });
      return true;
    } catch (e) { return false; }
  }

  // ------- danh sach hoi thoai (rail trai) --------------------------------
  function dsHoiThoai(win) {
    var doc = win.document;
    var links = Array.prototype.slice.call(doc.querySelectorAll('a[href*="/t/"]'));
    var seen = {}, ra = [];
    for (var i = 0; i < links.length; i++) {
      var a = links[i];
      var href = a.getAttribute("href") || a.href || "";
      if (/\/(new|requests)\b/.test(href)) { continue; }
      var id = threadId(href);
      if (!id || seen[id]) { continue; }
      if (!vis(a)) { continue; }
      var row = a.closest('[role="row"]') || a.closest('[role="gridcell"]') || a.closest("li") || a;
      var whole = txt(row);
      var ban = a.getAttribute("aria-label") || "";
      if (!ban) { var sp = row.querySelector('span[dir="auto"]'); ban = sp ? txt(sp) : whole; }
      seen[id] = 1;
      ra.push({
        id: id, el: a, ban: tenSach(ban) || id,
        unread: /chưa đọc|chua doc/i.test(whole),
        pending: /đang chờ|dang cho/i.test(whole)
      });
    }
    return ra;
  }
  // Uu tien tin chua doc; loai tin nhan cho tu nguoi la (pending).
  function chonHoiThoai(win, soToiDa) {
    var ds = dsHoiThoai(win).filter(function (t) { return !t.pending; });
    var chuaDoc = ds.filter(function (t) { return t.unread; });
    var nguon = chuaDoc.length ? chuaDoc : ds;
    return nguon.slice(0, soToiDa);
  }

  function findComposer(win) {
    var doc = win.document;
    var cands = Array.prototype.slice.call(
      doc.querySelectorAll('div[contenteditable="true"][role="textbox"], div[contenteditable="true"]'));
    for (var i = 0; i < cands.length; i++) { if (vis(cands[i])) { return cands[i]; } }
    return null;
  }
  function findThreadLink(win, id) {
    var doc = win.document;
    var links = doc.querySelectorAll('a[href*="/t/' + id + '"]');
    for (var i = 0; i < links.length; i++) { if (vis(links[i])) { return links[i]; } }
    return null;
  }
  // Doc tin NHAN DEN cuoi cung trong hoi thoai dang mo. Tin den = hang khong phai
  // cua minh: Messenger danh dau tin minh gui bang aria/align phai; tin ban thi ben trai.
  function khungHoiThoai(win) {
    // Vung hoi thoai = [role=main] (khong phai rail trai danh sach).
    var d = win.document;
    return d.querySelector('[role="main"]') || d.body;
  }
  function _boBanner(t) {
    // bo banner ma hoa dau cuoi + cac dong he thong + chu cua BANG THONG TIN ben phai (khong phai tin nhan).
    if (/mã hóa đầu cuối|end-to-end encrypt|được bảo mật bằng/i.test(t)) { return true; }
    if (/^(Đang hoạt động|Hoạt động|Đã xem|Đã gửi|Bạn đã|You |Enter|Nhấn|Gửi bằng)/i.test(t)) { return true; }
    if (/^(Quyền riêng tư và hỗ trợ|Privacy (&|and) support|Thông tin về|Chat info|Tùy chỉnh đoạn chat|Customize chat|File phương tiện|Media|Tìm kiếm trong cuộc trò chuyện|Search in conversation|Chủ đề|Theme|Biểu tượng cảm xúc|Biệt danh|Nicknames|Thông báo|Notifications|Chặn|Block|Báo cáo|Report|Xem trang cá nhân|View profile|Tắt thông báo|Mute)$/i.test(t)) { return true; }
    if (/^\d+[:h ]/.test(t) && t.length < 12) { return true; }   // dau thoi gian
    return false;
  }
  /* Cac phan tu chu THUOC CUOC TRO CHUYEN: nam trong CUNG COT voi o soan (giua rail trai va bang thong tin phai),
   * va o TREN o soan. Khong co o soan -> lay trong [role=grid]/[role=row] cua main; con lai fallback ca main. */
  function _cacChuTin(win) {
    var main = khungHoiThoai(win);
    var els = Array.prototype.slice.call(main.querySelectorAll('div[dir="auto"], span[dir="auto"]'));
    var box = findComposer(win);
    if (box) {
      var br = box.getBoundingClientRect();
      if (br.width > 100) {
        var trai = br.left - 24, phai = br.right + 24;
        var trongCot = els.filter(function (el) {
          var r = el.getBoundingClientRect();
          if (r.width <= 0 || r.height <= 0) { return false; }
          var cx = r.left + r.width / 2;
          return cx >= trai && cx <= phai && r.top < br.top;
        });
        if (trongCot.length) { return trongCot; }
      }
    }
    var grid = main.querySelector('[role="grid"]');
    if (grid) {
      var g = Array.prototype.slice.call(grid.querySelectorAll('div[dir="auto"], span[dir="auto"]'));
      if (g.length) { return g; }
    }
    return els;
  }
  function _cuaMinh(win, el) {
    try {
      var row = el.closest ? el.closest('[role="row"], [role="gridcell"], li') : null;
      var nhan = row ? ((row.innerText || "") + " " + (row.getAttribute("aria-label") || "")) : "";
      if (/Bạn đã gửi|You sent|Bạn:|You:/i.test(nhan.slice(0, 80))) { return true; }
      if (/đã gửi|sent/i.test(nhan.slice(0, 40)) && !/[A-ZÀ-Ỹ][^:]{2,40} đã gửi/.test(nhan.slice(0, 60))) { /* mo ho */ }
      var r = el.getBoundingClientRect(), w = win.innerWidth || 1200;
      if (r.width > 0 && r.left > w * 0.45 && r.right > w * 0.6) { return true; }
    } catch (e) {}
    return false;
  }
  function docTinGanNhat(win, n) {
    var out = [];
    try {
      var els = _cacChuTin(win);
      for (var i = 0; i < els.length; i++) {
        var t = txt(els[i]).replace(/\s+/g, " ").trim();
        if (!t || _boBanner(t)) { continue; }
        out.push({ tin: t.slice(0, 400), cua_minh: _cuaMinh(win, els[i]) });
      }
    } catch (e) {}
    return out.slice(-(n || 5));
  }
  function docTinCuoi(win) {
    try {
      var els = _cacChuTin(win);
      var last = "";
      for (var i = 0; i < els.length; i++) {
        var t = txt(els[i]).replace(/\s+/g, " ").trim();
        if (!t || _boBanner(t)) { continue; }
        last = t;
      }
      return last.slice(0, 400);
    } catch (e) { return ""; }
  }
  function dumpHoiThoai(win) {
    var d = win.document, out = [];
    function dem(s) { try { return d.querySelectorAll(s).length; } catch (e) { return -1; } }
    // 0) man khoa e2ee? (PIN / khoi phuc) + mau chu HIEN THI (innerText, bo script)
    var body = ((d.body && d.body.innerText) || "").replace(/\s+/g, " ");
    out.push("khoa_e2ee=" + (/mã PIN|khôi phục|Khôi phục|thiết lập.*bảo mật|Restore/i.test(body) ? "CO" : "khong"));
    out.push("body_mau=" + body.slice(0, 160));
    // Tim thong bao "khong ho tro" (neu co) -> doc du cau
    try {
      var all = d.querySelectorAll('*');
      for (var z = 0; z < all.length; z++) {
        var tz = (txt(all[z]) + " " + (all[z].getAttribute && all[z].getAttribute("aria-label") || "")).replace(/\s+/g, " ").trim();
        if (/không hỗ trợ|not supported|nâng cấp trình duyệt|update your browser/i.test(tz)) { out.push("THONGBAO=" + tz.slice(0, 240)); break; }
      }
    } catch (e) {}
    out.push("win=" + win.innerWidth + "x" + win.innerHeight);
    // iframe? (Messenger e2ee co the render hoi thoai trong iframe -> agent top khong thay)
    try {
      var ifr = d.querySelectorAll("iframe"), info = [];
      for (var f = 0; f < ifr.length; f++) {
        var one = "iframe" + f + " src=" + ((ifr[f].getAttribute("src") || "").slice(0, 30));
        try {
          var idoc = ifr[f].contentDocument;
          if (idoc) {
            one += " editable=" + idoc.querySelectorAll('[contenteditable]:not([contenteditable="false"])').length +
                   " textbox=" + idoc.querySelectorAll('[role="textbox"]').length +
                   " row=" + idoc.querySelectorAll('[role="row"]').length;
          } else { one += " (khong truy cap contentDocument)"; }
        } catch (e2) { one += " (cross-origin)"; }
        info.push(one);
      }
      out.push("IFRAME(" + ifr.length + ")=" + JSON.stringify(info));
    } catch (e) {}
    out.push("textbox=" + dem('[role="textbox"]'));
    out.push("btn_khoiphuc=" + dem('[aria-label*="Khôi phục"],[aria-label*="mã PIN"]'));
    out.push("any_editable=" + dem('[contenteditable]:not([contenteditable="false"])'));
    // liet ke nut + o nhap (de biet man khoi phuc / nhap PIN co gi)
    try {
      var btns = d.querySelectorAll('[role="button"],button'), bl = [];
      for (var k = 0; k < btns.length && bl.length < 14; k++) {
        var bt = (btns[k].getAttribute("aria-label") || txt(btns[k])).replace(/\s+/g, " ").trim();
        if (bt && vis(btns[k])) { bl.push(bt.slice(0, 26)); }
      }
      out.push("NUT=" + JSON.stringify(bl));
      var ins = d.querySelectorAll("input"), il = [];
      for (var m2 = 0; m2 < ins.length && il.length < 8; m2++) {
        il.push((ins[m2].type || "?") + ":" + (ins[m2].getAttribute("aria-label") || ins[m2].placeholder || ins[m2].name || "?").slice(0, 20));
      }
      out.push("INPUT=" + JSON.stringify(il));
    } catch (e) {}
    // 1) o soan (contenteditable) + aria-label cua no
    var eds = d.querySelectorAll('div[contenteditable="true"]');
    out.push("editable=" + eds.length);
    var al = [];
    for (var i = 0; i < eds.length && i < 3; i++) { al.push(eds[i].getAttribute("aria-label") || "?"); }
    out.push("ed_aria=" + JSON.stringify(al));
    // 2) cac vung ung vien chua tin nhan
    out.push("grid:" + dem('[role="grid"]'));
    out.push("aria-Messages:" + dem('[aria-label*="Messages"],[aria-label*="tin nhắn"],[aria-label*="Tin nhắn"]'));
    out.push("aria-Conversation:" + dem('[aria-label*="Conversation"],[aria-label*="trò chuyện"],[aria-label*="Đoạn chat"]'));
    // 3) mau chu cua vung tin nhan (neu tim duoc)
    try {
      var grid = d.querySelector('[aria-label*="Messages"],[aria-label*="tin nhắn"],[aria-label*="Tin nhắn"],[role="grid"]');
      if (grid) {
        var els = grid.querySelectorAll('div[dir="auto"],span[dir="auto"]'), tail = [];
        for (var j = Math.max(0, els.length - 6); j < els.length; j++) {
          tail.push(txt(els[j]).replace(/\s+/g, " ").slice(0, 36));
        }
        out.push("grid_aria=" + (grid.getAttribute("aria-label") || "?") + " grid_cuoi=" + JSON.stringify(tail));
      } else { out.push("grid_cuoi=KHONG-TIM-THAY-GRID"); }
    } catch (e) {}
    return out.join(" ; ");
  }
  // Thiet lap/nhap ma PIN bao mat e2ee mot cach THICH UNG (nhieu buoc: Khoi phuc ->
  // Tao ma PIN -> nhap -> xac nhan). pin do CHA truyen qua lenh (khong nam trong file agent).
  function pinInputsTrong(win) {
    var ins = win.document.querySelectorAll('input'), ra = [];
    for (var i = 0; i < ins.length; i++) {
      var el = ins[i], t = (el.type || "").toLowerCase();
      if (t === "hidden" || t === "search" || t === "checkbox") { continue; }
      var lbl = (el.getAttribute("aria-label") || el.placeholder || "");
      if (/mã PIN|PIN|mật khẩu/i.test(lbl) && vis(el) && !(el.value || "").length) { ra.push(el); }
    }
    return ra;
  }
  function pinInputsTatCa(win) {
    var ins = win.document.querySelectorAll('input'), ra = [];
    for (var i = 0; i < ins.length; i++) {
      var el = ins[i], t = (el.type || "").toLowerCase();
      if (t === "hidden" || t === "search" || t === "checkbox") { continue; }
      var lbl = (el.getAttribute("aria-label") || el.placeholder || "");
      if (/mã PIN|PIN|mật khẩu/i.test(lbl) && vis(el)) { ra.push(el); }
    }
    return ra;
  }
  function nutChinh(win) {
    // Tim tren TOAN TRANG (nut submit co the ngoai dialog); loai Quay lai / Luu chon khac.
    var bs = win.document.querySelectorAll('[role="button"],button');
    for (var i = 0; i < bs.length; i++) {
      var t = (bs[i].getAttribute("aria-label") || txt(bs[i])).replace(/\s+/g, " ").trim();
      if (/^(Tạo mã PIN|Tiếp tục|Xác nhận|Lưu mã PIN|Lưu|Hoàn tất|Xong|Tiếp|Continue|Confirm|Save|Next|Done)$/i.test(t) && vis(bs[i])) {
        return bs[i];
      }
    }
    return null;
  }
  function daMoKhoa(win) {
    // Mo khoa xong khi: khong con nut "Khôi phục", khong con o nhap PIN, khong con dialog PIN.
    try {
      var d = win.document;
      if (findComposer(win)) { return true; }
      var conKhoa = d.querySelector('[aria-label*="Khôi phục"]');
      var conPin = pinInputsTatCa(win).length > 0;
      var dlgPin = false;
      var dlg = d.querySelector('[role="dialog"]');
      if (dlg && /mã PIN/i.test(dlg.innerText || "")) { dlgPin = true; }
      return !conKhoa && !conPin && !dlgPin;
    } catch (e) { return false; }
  }
  // Go TUNG KY TU nhu nguoi that (Messenger PIN tu chuyen buoc theo moi phim).
  function goTung(win, el, val) {
    try {
      el.focus();
      // xoa gia tri cu
      try { el.select(); } catch (e) {}
      setNative(win, el, "");
      var cur = "";
      for (var i = 0; i < val.length; i++) {
        var c = val.charAt(i);
        withUserInput(win, function () {
          el.dispatchEvent(new win.KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: c, keyCode: c.charCodeAt(0), which: c.charCodeAt(0) }));
          el.dispatchEvent(new win.KeyboardEvent("keypress", { bubbles: true, cancelable: true, key: c, keyCode: c.charCodeAt(0), which: c.charCodeAt(0) }));
        });
        cur += c;
        var setter = Object.getOwnPropertyDescriptor(win.HTMLInputElement.prototype, "value").set;
        setter.call(el, cur);
        el.dispatchEvent(new win.InputEvent("input", { bubbles: true, inputType: "insertText", data: c }));
        withUserInput(win, function () {
          el.dispatchEvent(new win.KeyboardEvent("keyup", { bubbles: true, cancelable: true, key: c }));
        });
      }
      el.dispatchEvent(new win.Event("change", { bubbles: true }));
      return el.value;
    } catch (e) { note("goTung loi " + e); return ""; }
  }
  function moKhoaPin(win, pin, cb) {
    var buoc = 0, MAX = 26, daDien = 0, lanBam = 0, lanEnter = 0, onDinh = 0;
    (function tick() {
      var d = win.document;
      if (findComposer(win)) { cb(true, "da mo khoa (co o soan)"); return; }
      if (daDien >= 1 && daMoKhoa(win)) {
        onDinh++;
        if (onDinh >= 2) { cb(true, "da mo khoa (man PIN da bien mat)"); return; }
      } else { onDinh = 0; }
      var empties = pinInputsTrong(win);
      var allpins = pinInputsTatCa(win);
      var kb = d.querySelector('[aria-label*="Khôi phục"]');
      var primary = nutChinh(win);
      var dlg = d.querySelector('[role="dialog"]');
      var heading = dlg ? (dlg.innerText || "").replace(/\s+/g, " ").slice(0, 40) : "(no-dlg)";
      // chan doan trang thai moi tick
      report({ state: "seen", detail: "buoc" + buoc + " dlg=" + (dlg ? 1 : 0) + " pinTrong=" + empties.length +
               " pinAll=" + allpins.length + " nutChinh=" + (primary ? "co" : "-") + " | " + heading });
      if (empties.length) {
        for (var j = 0; j < empties.length; j++) {
          var v = goTung(win, empties[j], pin);
          note("go PIN -> do dai " + (v || "").length);
        }
        daDien += empties.length;
      } else if (allpins.length) {
        // da dien roi: thu Enter roi bam nut chinh
        pressEnter(win, allpins[allpins.length - 1]); lanEnter++;
        if (primary) { clickReal(win, primary); lanBam++; }
      } else if (primary) {
        clickReal(win, primary); lanBam++;
      } else if (kb) {
        clickReal(win, kb.closest('[role="button"]') || kb);
      }
      buoc++;
      if (buoc < MAX) { win.setTimeout(tick, 1600); }
      else {
        var d2 = d.querySelector('[role="dialog"]');
        cb(!!findComposer(win) || daMoKhoa(win), "dung: dien " + daDien + " PIN, bam " + lanBam + ", Enter " + lanEnter +
           "; composer=" + (findComposer(win) ? "co" : "khong") + "; moKhoa=" + (daMoKhoa(win) ? "co" : "khong") +
           " | DLG: " + (d2 ? (d2.innerText || "").replace(/\s+/g, " ").slice(0, 200) : "(khong)"));
      }
    })();
  }

  // Hoi thoai ma hoa dau cuoi bi KHOA: hien nut "Khôi phục" / "mã PIN", khong co o soan.
  function canKhoiPhucE2EE(win) {
    try {
      return !!win.document.querySelector('[aria-label*="Khôi phục"],[aria-label*="mã PIN"]') && !findComposer(win);
    } catch (e) { return false; }
  }
  /* Hoi thoai MA HOA DAU CUOI (e2ee): URL /e2ee/, HOAC o soan/tin nam trong iframe cheo nguon fbsbx maw_proxy
   * (contentDocument khong doc duoc) -> khong the doc tin / go / gui trong phien tu dong. Khac man "Khoi phuc/PIN". */
  function laE2EE(win) {
    try {
      if (/\/e2ee\/|\/messages\/e2ee/i.test(win.location.href || "")) { return true; }
      if (findComposer(win)) { return false; }   // co o soan top -> khong phai e2ee bi khoa
      var ifr = win.document.querySelectorAll('iframe[src*="fbsbx.com/maw_proxy"], iframe[src*="maw_proxy_page"]');
      return ifr.length > 0;
    } catch (e) { return false; }
  }
  // Mo mot hoi thoai: click that (SPA) + native click de FB router chay; cho o soan render.
  function moHoiThoai(win, id, cb) {
    var link = findThreadLink(win, id);
    if (!link) { cb(false); return; }
    var target = link.closest('[role="row"]') || link.closest('[role="gridcell"]') || link;
    clickReal(win, target);
    try { link.click(); } catch (e) {}   // kich hoat dinh tuyen mac dinh cua FB
    var waited = 0, step = 800, cap = 16000;
    (function wait() {
      if (findComposer(win)) { cb(true); return; }
      waited += step;
      if (waited >= cap) { cb(!!findComposer(win)); return; }
      // thu click lai giua chung neu chua mo
      if (waited === 6400) { try { clickReal(win, target); link.click(); } catch (e) {} }
      win.setTimeout(wait, step);
    })();
  }

  // ------- gui mot cau tra loi --------------------------------------------
  function guiMot(win, rep, done) {
    var id = rep.id, val = String(rep.tra_loi || "");
    if (!val.trim()) { note("[" + id + "] cau tra loi rong -> bo"); done(false); return; }
    moHoiThoai(win, id, function (mo) {
      var box = findComposer(win);
      if (!mo || !box) {
        note("[" + id + "] khong mo duoc hoi thoai / khong thay o soan (mo=" + mo + ", e2ee=" + canKhoiPhucE2EE(win) + ")");
        done(false); return;
      }
      var go = goVaoOSoan(win, box, val);
      if (!go.ok) { note("[" + id + "] KHONG GO DUOC vao o soan: " + go.cach); done(false); return; }
      note("[" + id + "] da go (" + go.cach + ")");
      function daGui() {
        var trong = txt(findComposer(win) || box).trim() === "";
        var cuoi = docTinCuoi(win) || "";
        return trong || cuoi.indexOf(val.slice(0, 20)) !== -1;
      }
      win.setTimeout(function () {
        pressEnter(win, box);
        win.setTimeout(function () {
          if (daGui()) { note("[" + id + "] da gui (Enter)"); done(true); return; }
          var nut = nutGui(win);
          if (nut) { clickReal(win, nut); }
          win.setTimeout(function () {
            if (daGui()) { note("[" + id + "] da gui (nut Gui)"); done(true); return; }
            note("[" + id + "] GO XONG NHUNG KHONG GUI DUOC (Enter + nut Gui=" + (nut ? "co" : "khong") + "; o soan con: " + JSON.stringify(txt(box).slice(0, 40)) + ")");
            done(false);
          }, 1500);
        }, 1500);
      }, 500);
    });
  }
  var lyDoGui = {};   // id -> ly do khong gui duoc (note cuoi cua guiMot)
  function guiHet(win, replies, i, sent, finish) {
    if (i >= replies.length) { finish(sent); return; }
    var truoc = lines.length;
    guiMot(win, replies[i], function (ok) {
      if (ok) { sent.push(replies[i].id); }
      else { lyDoGui[String(replies[i].id)] = String(lines[lines.length - 1] || "").replace(/^\[[^\]]*\]\s*/, "").slice(0, 160); }
      win.setTimeout(function () { guiHet(win, replies, i + 1, sent, finish); }, 800);
    });
  }

  // ------- doc tin cuoi cua tung hoi thoai chua doc ------------------------
  function docHet(win, ds, i, acc, finish) {
    if (i >= ds.length) { finish(acc); return; }
    var t = ds[i];
    moHoiThoai(win, t.id, function (ok) {
      win.setTimeout(function () {
        if (canKhoiPhucE2EE(win) || laE2EE(win)) { acc._e2ee = true; acc._coE2EE = true; }
        var tin = ok ? docTinCuoi(win) : "";
        var gan = ok ? docTinGanNhat(win, 5) : [];
        var chuaNhan = true;
        for (var g = 0; g < gan.length; g++) { if (gan[g].cua_minh) { chuaNhan = false; } }
        if (i === 0) { acc._dbg = "[" + t.ban + "] ok=" + ok + " tin=" + tin.slice(0, 50) + " gan=" + gan.length + " chuaNhan=" + chuaNhan + " :: " + dumpHoiThoai(win); }
        if (tin && !acc._e2ee) { acc.push({ id: t.id, ban: t.ban, tin: tin, tin_gan: gan, chua_tung_nhan: chuaNhan }); }
        else { note("[" + t.ban + "] mo=" + ok + (acc._e2ee ? " nhung hoi thoai bi KHOA (can khoi phuc e2ee)" : " nhung khong doc duoc tin")); }
        win.setTimeout(function () { docHet(win, ds, i + 1, acc, finish); }, 500);
      }, 4000);   // cho tin nhan render sau khi mo
    });
  }

  // ------- chan doan trang -------------------------------------------------
  // Checkpoint MEM (co nut "Bo qua"): fbskip_agent se bam -> coi nhu dang tai, quet lai sau.
  function coNutBoQua(win) {
    try {
      var cands = win.document.querySelectorAll('[role="button"], button');
      for (var i = 0; i < Math.min(cands.length, 200); i++) {
        if (/^(bỏ qua|skip|not now|để sau)$/i.test((cands[i].textContent || "").trim())) { return true; }
      }
    } catch (e) {}
    return false;
  }
  function trangThai(win) {
    var h = low(win.location.href);
    if (h.indexOf("/checkpoint") !== -1) { return coNutBoQua(win) ? "" : "checkpoint"; }
    if (h.indexOf("/login") !== -1 || h.indexOf("login.php") !== -1) { return "chua-dang-nhap"; }
    try {
      var d = win.document;
      if (d.querySelector('input[name="email"]') && d.querySelector('input[name="pass"]')) {
        return "chua-dang-nhap";
      }
    } catch (e) {}
    return "";
  }
  function demHoiThoai(win) {
    try { return win.document.querySelectorAll('a[href*="/messages/t/"]').length; }
    catch (e) { return 0; }
  }
  function mauDong(win) {
    try {
      var a = win.document.querySelector('a[href*="/messages/t/"]');
      var row = a && (a.closest('[role="row"]') || a.closest("li") || a);
      return row ? txt(row).replace(/\s+/g, " ").slice(0, 80) : "";
    } catch (e) { return ""; }
  }
  // Chan doan sau: dem cac selector ung vien + tieu de + mau chu -> biet DOM that.
  function chanDoanDOM(win) {
    var d = win.document, out = [];
    function dem(sel) { try { return d.querySelectorAll(sel).length; } catch (e) { return -1; } }
    out.push("title=" + (d.title || "").slice(0, 40));
    out.push("a[/messages/t/]=" + dem('a[href*="/messages/t/"]'));
    out.push("a[/t/]=" + dem('a[href*="/t/"]'));
    out.push("a[/messages]=" + dem('a[href*="/messages"]'));
    out.push("role=row:" + dem('[role="row"]'));
    out.push("role=gridcell:" + dem('[role="gridcell"]'));
    out.push("role=grid:" + dem('[role="grid"]'));
    out.push("role=link:" + dem('[role="link"]'));
    out.push("aria-label-link:" + dem('a[aria-label]'));
    out.push("editable:" + dem('div[contenteditable="true"]'));
    // mau: chu cua 2 link dau co href chua chu so (thread id thuong la so)
    try {
      var as = d.querySelectorAll('a[href]'), mau = [];
      for (var i = 0; i < as.length && mau.length < 4; i++) {
        var h = as[i].getAttribute("href") || "";
        if (/\/(t|messages)\//.test(h) || /message/i.test(as[i].getAttribute("aria-label") || "")) {
          mau.push(h.slice(0, 40) + "|" + txt(as[i]).slice(0, 24));
        }
      }
      out.push("mau_link=" + JSON.stringify(mau));
    } catch (e) {}
    out.push("body=" + (txt(d.body) || "").replace(/\s+/g, " ").slice(0, 120));
    return out.join(" ; ");
  }

  // ------- vong dieu khien tren trang messages -----------------------------
  function onPage(win) {
    if (low(win.location.href).indexOf("facebook.com") === -1) { return; }
    var didScan = false, replying = false;
    var waited = 0, step = 1000, cap = 180000, choRender = 0, CHO_TOI_DA = 30000;
    report({ state: "seen", detail: "mo trang " + win.location.href.slice(0, 80) });
    win.setTimeout(function tick() {
      var cmd = getCommand();
      if (cmd && cmd.action === "scan" && !didScan) {
        var tt = trangThai(win);
        if (tt) {
          didScan = true;
          note("khong quet duoc: " + tt);
          report({ state: "scanned", items: [], why: tt, url: win.location.href.slice(0, 80) });
        } else {
          var ds = dsHoiThoai(win);
          if (ds.length === 0 && choRender < CHO_TOI_DA) {
            // Messenger nap dong: cho danh sach hoi thoai render roi hay quet
            choRender += step;
            if (choRender % 5000 === 0) { note("dang cho danh sach hoi thoai render (" + choRender + "ms)"); }
          } else {
            didScan = true;
            var chon = chonHoiThoai(win, cmd.so_toi_da || 5);
            note("thay " + ds.length + " hoi thoai, doc " + chon.length + " cai (uu tien chua doc)");
            if (!chon.length) {
              report({ state: "scanned", items: [], url: win.location.href.slice(0, 80),
                       tong_link: ds.length, why: "khong co hoi thoai chua doc phu hop", dom: chanDoanDOM(win) });
            } else {
              docHet(win, chon, 0, [], function (items) {
                note("doc xong: " + items.length + " tin can tra loi");
                var whyEmpty = items._coE2EE
                  ? "hội thoại MÃ HOÁ ĐẦU CUỐI (e2ee) — Facebook khoá đọc/gửi tự động; mở Messenger tay, thiết lập/nhập mã PIN 1 lần cho acc này rồi chạy lại"
                  : "mở hội thoại nhưng không đọc được nội dung tin";
                report({ state: "scanned", items: items, url: win.location.href.slice(0, 80),
                         tong_link: ds.length,
                         why: items.length ? "" : whyEmpty,
                         dom: items._dbg || (items.length ? "" : dumpHoiThoai(win)) });
              });
              return;
            }
          }
        }
      } else if (cmd && cmd.action === "restore_probe" && !didScan) {
        if (choRender < 16000) {
          choRender += step;
          if (choRender === 6000) {
            var kb = win.document.querySelector('[aria-label*="Khôi phục"]');
            if (kb) { clickReal(win, kb.closest('[role="button"]') || kb); note("bam Khoi phuc"); }
            else { note("khong thay Khoi phuc"); }
          }
          if (choRender === 10000) {
            var dlg0 = win.document.querySelector('[role="dialog"]');
            var tao = null;
            if (dlg0) {
              var bs = dlg0.querySelectorAll('[role="button"],button');
              for (var y = 0; y < bs.length; y++) {
                if (/Tạo mã PIN|Tiếp tục/i.test((bs[y].getAttribute("aria-label") || txt(bs[y])))) { tao = bs[y]; break; }
              }
            }
            if (tao) { clickReal(win, tao); note("bam Tao ma PIN"); }
            else { note("khong thay nut Tao ma PIN"); }
          }
        } else {
          didScan = true;
          var d = win.document, ex = [];
          ex.push("dialog=" + d.querySelectorAll('[role="dialog"]').length);
          var ins = d.querySelectorAll('input,[role="textbox"],[contenteditable]:not([contenteditable="false"])'), il = [];
          for (var q = 0; q < ins.length && il.length < 10; q++) {
            il.push((ins[q].tagName) + "/" + (ins[q].type || ins[q].getAttribute("role") || "?") + ":" +
                    (ins[q].getAttribute("aria-label") || ins[q].placeholder || "?").slice(0, 22));
          }
          ex.push("INS=" + JSON.stringify(il));
          var dlg = d.querySelector('[role="dialog"]');
          if (dlg) {
            ex.push("DLG_TXT=" + ((dlg.innerText || "").replace(/\s+/g, " ").slice(0, 160)));
            var db = dlg.querySelectorAll('[role="button"],button'), dbl = [];
            for (var w = 0; w < db.length && dbl.length < 10; w++) {
              var bt = (db[w].getAttribute("aria-label") || txt(db[w])).replace(/\s+/g, " ").trim();
              if (bt) { dbl.push(bt.slice(0, 24)); }
            }
            ex.push("DLG_NUT=" + JSON.stringify(dbl));
          }
          report({ state: "scanned", items: [], why: "restore_probe", url: win.location.href.slice(0, 90),
                   dom: ex.join(" ; ") });
        }
      } else if (cmd && cmd.action === "setup_pin" && !replying) {
        replying = true;
        note("bat dau thiet lap ma PIN bao mat e2ee");
        if (/\/t\/\d+/.test(win.location.href)) {
          // Da o thang URL hoi thoai -> man Khoi phuc hien ra o day -> dien PIN luon.
          win.setTimeout(function () {
            moKhoaPin(win, cmd.pin || "", function (ok, msg) {
              report({ state: "pin-done", ok: ok, detail: msg });
            });
          }, 4000);
        } else {
          // Dang o inbox -> tim mot hoi thoai THAT roi DIEU HUONG THANG toi no (click khong mo duoc).
          var slan = 0;
          (function choDs() {
            var ds0 = dsHoiThoai(win).filter(function (t) { return !t.pending; });
            if (!ds0.length && slan < 30) { slan++; win.setTimeout(choDs, 800); return; }
            if (!ds0.length) { report({ state: "pin-done", ok: false, detail: "khong thay hoi thoai that" }); return; }
            var href = ds0[0].el.getAttribute("href") || ds0[0].el.href || "";
            if (href.charAt(0) === "/") { href = "https://www.facebook.com" + href; }
            note("dieu huong thang toi hoi thoai [" + ds0[0].ban + "] " + href.slice(0, 60));
            win.location.assign(href);   // full nav -> onPage chay lai, lan nay o /t/ -> dien PIN
          })();
        }
        return;
      } else if (cmd && cmd.action === "compose_probe" && !didScan) {
        // Thu luong "Tin nhan moi" (soan chu dong) — xem o soan co o trang chinh khong.
        if (choRender < 11000) {
          choRender += step;
          if (choRender === 5000) {
            var d0 = win.document;
            var nm = d0.querySelector('a[href*="/messages/new"],[aria-label*="Tin nhắn mới"],[aria-label*="Soạn"],[aria-label*="New message"]');
            if (nm) { clickReal(win, nm.closest('[role="button"],a') || nm); note("bam Tin nhan moi"); }
            else { note("khong thay Tin nhan moi"); }
          }
        } else {
          didScan = true;
          var d = win.document;
          var ed = d.querySelectorAll('[contenteditable]:not([contenteditable="false"])').length;
          var tb = d.querySelectorAll('[role="textbox"]').length;
          var toF = d.querySelectorAll('input[aria-label*="Đến"],input[aria-label*="To"],input[placeholder*="Đến"],[aria-label*="Tìm kiếm người"]').length;
          report({ state: "scanned", items: [], why: "compose_probe",
                   dom: "editable=" + ed + " textbox=" + tb + " toField=" + toF +
                        " ifr=" + d.querySelectorAll("iframe").length +
                        " url=" + win.location.href.slice(0, 50) });
        }
      } else if (cmd && cmd.action === "probe" && !didScan) {
        // Chan doan: mo thang URL hoi thoai roi dump (khong click SPA).
        if (choRender < 9000) { choRender += step; }
        else {
          didScan = true;
          report({ state: "scanned", items: [], why: "probe", url: win.location.href.slice(0, 90), dom: dumpHoiThoai(win) });
        }
      } else if (cmd && cmd.action === "reply" && !replying) {
        replying = true;
        var reps = (cmd.replies || []).filter(function (r) { return r && r.id && (r.tra_loi || "").trim(); });
        note("bat dau gui " + reps.length + " tra loi");
        guiHet(win, reps, 0, [], function (sent) {
          note("da gui " + sent.length + "/" + reps.length);
          report({ state: "reply-sent", sent: sent, ly_do: lyDoGui });
        });
        return;   // guiHet tu bao ket qua
      }
      waited += step;
      if (waited < cap) { win.setTimeout(tick, step); }
    }, 3000);
  }

  // IFRAME hoi thoai ma hoa (fbsbx.com/maw_proxy...) — o soan tin + tin nhan NAM O DAY.
  function laFrameChat(win) {
    try { return /fbsbx\.com\/(maw|messaging)/i.test(win.location.href) || /maw_prox/i.test(win.location.href); }
    catch (e) { return false; }
  }
  function onFrame(win) {
    // Chan doan + xu ly hoi thoai ben trong iframe.
    var buoc = 0, MAX = 40;
    win.setTimeout(function tick() {
      var d = win.document;
      var ed = d.querySelectorAll('[contenteditable]:not([contenteditable="false"])').length;
      var tb = d.querySelectorAll('[role="textbox"]').length;
      var rows = d.querySelectorAll('[role="row"]').length;
      var cmd = getCommand();
      if (buoc % 3 === 0) {
        report({ state: "seen", detail: "[frame] editable=" + ed + " textbox=" + tb + " row=" + rows +
                 " url=" + win.location.href.slice(0, 40) });
      }
      // gui tra loi neu co lenh reply (o soan nam trong frame nay)
      if (cmd && cmd.action === "reply" && !win.__daGui) {
        var box = findComposer(win);
        if (box) {
          win.__daGui = true;
          var reps = (cmd.replies || []).filter(function (r) { return r && (r.tra_loi || "").trim(); });
          var val = reps.length ? reps[0].tra_loi : (cmd.tra_loi || "");
          if (val) {
            var go = goVaoOSoan(win, box, val);
            var rid = reps.length ? [reps[0].id] : ["1"];
            if (!go.ok) {
              report({ state: "reply-sent", sent: [], detail: "[frame] KHONG GO DUOC vao o soan: " + go.cach });
              return;
            }
            win.setTimeout(function () {
              pressEnter(win, box);
              win.setTimeout(function () {
                var trong = txt(findComposer(win) || box).trim() === "";
                if (trong) { report({ state: "reply-sent", sent: rid, detail: "[frame] go (" + go.cach + ") + Enter, o soan da trong" }); return; }
                var nut = nutGui(win);
                if (nut) { clickReal(win, nut); }
                win.setTimeout(function () {
                  var trong2 = txt(findComposer(win) || box).trim() === "";
                  report({ state: "reply-sent", sent: trong2 ? rid : [],
                           detail: "[frame] go (" + go.cach + "), Enter" + (nut ? "+nut Gui" : "") + (trong2 ? " -> da gui" : " -> KHONG GUI DUOC, o soan con: " + JSON.stringify(txt(box).slice(0, 40))) });
                }, 1500);
              }, 1500);
            }, 500);
            return;
          }
          win.__daGui = false;
        }
      }
      buoc++;
      if (buoc < MAX) { win.setTimeout(tick, 1500); }
    }, 3000);
  }
  var observer = {
    observe: function (subject, topic) {
      if (topic !== "content-document-global-created") { return; }
      var win = subject;
      try {
        try { win.navigator.__defineGetter__ && (win.navigator.webdriver = false); } catch (e) {}
        if (win.top !== win) {
          // BAO MOI iframe (chan doan tim o soan) + xu ly frame hoi thoai.
          try {
            report({ state: "seen", detail: "[frame-moi] " + (win.location.href || "?").slice(0, 60) });
          } catch (e) {}
          win.addEventListener("load", function onl() { win.removeEventListener("load", onl); onFrame(win); }, { once: true });
          onFrame(win);
          return;
        }
        win.addEventListener("load", function onload() {
          win.removeEventListener("load", onload);
          onPage(win);
        }, { once: true });
      } catch (e) {}
    },
  };
  Services.obs.addObserver(observer, "content-document-global-created");
}
