/* Process script: tao fanpage tren facebook.com/pages/creation.
 *
 * Chay trong TIEN TRINH NOI DUNG, cham thang vao document. Muc dich chinh: bam
 * nut "Create Page" bang setHandlingUserInput(true) -> su kien "user that"
 * (isTrusted), trinh duyet mo BINH THUONG (khong co cong go loi tu xa, khong
 * navigator.webdriver) -> Facebook khong chan nhu khi chay qua WebDriver BiDi.
 * Da do that: click qua BiDi bi FB chan im, con click nay giong nguoi dung.
 *
 * Bridge RIENG (khong dam agent dang bai):
 *   sendSyncMessage("qlfpc:cmd")     -> cha doc <profile>/qlfp-create.json
 *   sendAsyncMessage("qlfpc:report") -> cha ghi <profile>/qlfp-create-result.json
 *
 * Lenh: { action:"create", name, category, description, submit, delay,
 *         formTimeout, catTimeout }
 */
"use strict";

if (typeof sendAsyncMessage === "function") {

  var lines = [];

  function report(state, detail) {
    lines.push(state + (detail ? ": " + detail : ""));
    try {
      sendAsyncMessage("qlfpc:report",
        { state: state, detail: detail || "", log: lines.slice(-30) });
    } catch (e) {}
  }

  function getCommand() {
    try {
      var answer = sendSyncMessage("qlfpc:cmd");
      var raw = answer && answer.length ? answer[0] : "";
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  /* --------------------------------------------------------- nhan dien o */
  // Bo tat ca truy van ve vung role=main: thanh nav "Search Facebook" nam NGOAI
  // main -> tu dong loai, khoi go nham ten page vao thanh tim kiem.
  function mainRoot(doc) { return doc.querySelector('[role="main"]') || doc.body; }
  function vis(el) { var b = el.getBoundingClientRect(); return b.width > 60 && b.height > 12; }
  function low(s) { return (s || "").toLowerCase(); }

  function nameInput(root) {
    var xs = Array.prototype.slice.call(root.querySelectorAll('input[type="text"]'))
      .filter(vis);
    return xs[0] || null;
  }
  function catInput(root) {
    // 1) combobox/search trong main, KHAC thanh nav "Search Facebook".
    var xs = Array.prototype.slice.call(
      root.querySelectorAll('input[role="combobox"], input[type="search"]'))
      .filter(function (el) {
        return vis(el) && low(el.getAttribute("aria-label")).indexOf("search facebook") === -1;
      });
    if (xs[0]) { return xs[0]; }
    // 2) input co dau hieu "hang muc"/"category"/"loai" (aria/placeholder).
    var all = Array.prototype.slice.call(root.querySelectorAll("input")).filter(vis);
    for (var i = 0; i < all.length; i++) {
      var s = low(all[i].getAttribute("aria-label")) + " " + low(all[i].getAttribute("placeholder"));
      if (s.indexOf("hạng mục") !== -1 || s.indexOf("hang muc") !== -1
          || s.indexOf("category") !== -1 || s.indexOf("loại") !== -1
          || s.indexOf("thể loại") !== -1) { return all[i]; }
    }
    // 3) O nhap thu HAI trong main (o dau la Ten) -- loai file/hidden/nav search.
    var goc = Array.prototype.slice.call(root.querySelectorAll("input")).filter(function (el) {
      return vis(el) && el.type !== "file" && el.type !== "hidden"
             && low(el.getAttribute("aria-label")).indexOf("search facebook") === -1;
    });
    return goc[1] || null;
  }
  function bioInput(root) {
    var xs = Array.prototype.slice.call(
      root.querySelectorAll('textarea, [contenteditable="true"]')).filter(vis);
    return xs[0] || null;
  }

  function setNative(win, el, val) {
    try {
      var proto = el.tagName.toLowerCase() === "textarea"
        ? win.HTMLTextAreaElement.prototype : win.HTMLInputElement.prototype;
      var setter = Object.getOwnPropertyDescriptor(proto, "value").set;
      el.focus();
      setter.call(el, val);
      el.dispatchEvent(new win.Event("input", { bubbles: true }));
      el.dispatchEvent(new win.Event("change", { bubbles: true }));
    } catch (e) { report("set-error", String(e)); }
  }
  function setCE(win, doc, el, val) {
    try {
      el.focus();
      doc.execCommand("selectAll", false, null);
      doc.execCommand("insertText", false, val);
      el.dispatchEvent(new win.Event("input", { bubbles: true }));
    } catch (e) {}
  }

  function textOf(el) {
    try { return (el.innerText || el.textContent || "").trim(); } catch (e) { return ""; }
  }

  // Liet ke cac o nhap trong main (de soi khi khong tim/dien duoc hang muc tren
  // acc cua nguoi dung -- log se cho biet form co gi).
  function dumpInputs(root) {
    var out = [];
    try {
      var xs = root.querySelectorAll("input, textarea, [contenteditable='true']");
      for (var i = 0; i < xs.length && i < 12; i++) {
        var el = xs[i];
        if (!el.offsetParent) { continue; }
        out.push((el.tagName || "?").toLowerCase()
          + "[type=" + (el.getAttribute("type") || "") + ",role="
          + (el.getAttribute("role") || "") + ",aria="
          + (el.getAttribute("aria-label") || "").slice(0, 25) + "]");
      }
    } catch (e) {}
    return out.join(" | ") || "(không có ô nào)";
  }

  /** Bam that: setHandlingUserInput(true) -> su kien isTrusted, FB nhan la nguoi that. */
  function clickIt(win, el) {
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try { el.click(); return true; }
    catch (e) { report("click-error", String(e)); return false; }
    finally { if (handle) { try { handle.destruct(); } catch (e) {} } }
  }

  /** Bam bang CHUOI su kien day du (pointer + mouse), trong setHandlingUserInput.
   *
   * Combobox React cua FB commit lua chon o mousedown/pointer chu khong o mot su
   * kien "click" don. `el.click()` khong du -> nut Tao khong bat. Da do that
   * (2026-09): chi khi ban day du chuoi pointerdown/mousedown/mouseup/click thi
   * hang muc moi thuc su duoc chon.
   */
  function clickReal(win, el) {
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try {
      var b = el.getBoundingClientRect();
      var cx = b.left + b.width / 2, cy = b.top + b.height / 2;
      function pe(t) {
        return new win.PointerEvent(t, { bubbles: true, cancelable: true,
          clientX: cx, clientY: cy, button: 0, pointerType: "mouse", isPrimary: true });
      }
      function me(t) {
        return new win.MouseEvent(t, { bubbles: true, cancelable: true,
          clientX: cx, clientY: cy, button: 0 });
      }
      el.dispatchEvent(pe("pointerover"));
      el.dispatchEvent(me("mouseover"));
      el.dispatchEvent(pe("pointerdown"));
      el.dispatchEvent(me("mousedown"));
      try { el.focus(); } catch (e) {}
      el.dispatchEvent(pe("pointerup"));
      el.dispatchEvent(me("mouseup"));
      el.dispatchEvent(me("click"));
      return true;
    } catch (e) { report("click-error", String(e)); return false; }
    finally { if (handle) { try { handle.destruct(); } catch (e) {} } }
  }

  /** Nut "Create Page": ENABLED, RONG (ca chieu ngang form), THAP NHAT trong
   *  main. Khong theo mau (nut bat van co nen trong suot) hay chu (doi ngon ngu). */
  function createButton(root, win) {
    function enabled(el) {
      return el.getAttribute("aria-disabled") !== "true" && !el.disabled;
    }
    var btns = Array.prototype.slice.call(root.querySelectorAll('[role="button"], button'))
      .filter(function (el) {
        var b = el.getBoundingClientRect();
        return b.width >= 200 && b.height > 24 && b.top > 0
               && b.top < (win.innerHeight || 900) && enabled(el);
      });
    if (!btns.length) { return null; }
    btns.sort(function (a, b) {
      return b.getBoundingClientRect().top - a.getBoundingClientRect().top;
    });
    return btns[0];
  }

  /* ------------------------------------------------------------ cac buoc */
  function fillForm(win, doc, cmd) {
    var root = mainRoot(doc);
    var ten = nameInput(root);
    if (!ten) { report("no-name-input", "chưa thấy ô Tên (form chưa nạp xong?)"); return; }
    setNative(win, ten, cmd.name || "");
    if (cmd.description) {
      var bio = bioInput(root);
      if (bio) {
        if (bio.tagName.toLowerCase() === "textarea") setNative(win, bio, cmd.description);
        else setCE(win, doc, bio, cmd.description);
      }
    }
    report("filled", "tên + mô tả");
    if ((cmd.category || "").trim()) { typeCategory(win, doc, cmd); return; }
    // Khong co hang muc thi Facebook KHONG BAO GIO bat nut Tao -> bao thang,
    // khoi doi 8 vong roi bao mo ho "nut Tao chua bat" (da gap 5/9).
    report("no-create-button", "chưa nhập HẠNG MỤC — Facebook bắt buộc chọn hạng mục, "
           + "thiếu thì nút Tạo không bật");
  }

  function key(win, el, k, code, kc) {
    var handle = null;
    try { handle = win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try {
      ["keydown", "keyup"].forEach(function (t) {
        el.dispatchEvent(new win.KeyboardEvent(t, { bubbles: true, cancelable: true,
          key: k, code: code, keyCode: kc, which: kc }));
      });
    } catch (e) {} finally { if (handle) { try { handle.destruct(); } catch (e) {} } }
  }

  function optlist(doc) {
    var opts = Array.prototype.slice.call(
      doc.querySelectorAll('[role="listbox"] [role="option"]'))
      .filter(function (el) { var b = el.getBoundingClientRect(); return b.width > 40 && b.height > 8; });
    if (!opts.length) {
      opts = Array.prototype.slice.call(doc.querySelectorAll('[role="option"]'))
        .filter(function (el) { var b = el.getBoundingClientRect(); return b.width > 40 && b.height > 8; });
    }
    return opts;
  }

  // ---- CHIP hang muc da chon (de bo hang muc THUA) ----
  // Moi hang muc da chon hien 1 chip co nut "×" aria-label kieu "Xóa <ten>" / "Remove <ten>".
  // Bat ca tieng Viet lan tieng Anh (yeu cau nguoi dung: bao ham VI + EN).
  var RE_XOA = /^(?:xóa|xoá|remove|gỡ|bỏ|delete)\s+(.+)$/i;
  function hangMucChip(doc) {
    var out = [], root = doc.querySelector('[role="dialog"]') || mainRoot(doc);
    var btns = root.querySelectorAll('[aria-label]');
    for (var i = 0; i < btns.length; i++) {
      var b = btns[i], lb = b.getAttribute("aria-label") || "";
      var m = lb.match(RE_XOA);
      if (m && vis(b)) { out.push({ ten: m[1].trim(), xoa: b }); }
    }
    return out;
  }
  function daCoHangMuc(doc, want) {
    var cs = hangMucChip(doc);
    for (var i = 0; i < cs.length; i++) {
      var t = low(cs[i].ten);
      if (t === want || (want && t.indexOf(want) !== -1) || (want && want.indexOf(t) !== -1)) { return true; }
    }
    return false;
  }
  // Giu DUNG 1 hang muc = want; bo cac chip THUA (vd "Pháp lý" mac dinh, hoac chon nham 2 cai).
  function donHangMucThua(win, doc, want) {
    var chips = hangMucChip(doc), giuXong = false, bo = [];
    for (var i = 0; i < chips.length; i++) {
      var c = chips[i], t = low(c.ten);
      var khop = t === want || (want && t.indexOf(want) !== -1) || (want && want.indexOf(t) !== -1);
      if (khop && !giuXong) { giuXong = true; continue; }   // giu chip khop dau tien
      clickReal(win, c.xoa); bo.push(c.ten);                 // bo chip con lai (thua/nham)
    }
    return { con: chips.map(function (c) { return c.ten; }), bo: bo };
  }

  // Chon option hang muc KHOP NHAT voi chu da go. Tra ve chi so, -1 neu khong
  // khop gi. Uu tien: trung khit -> bat dau bang (ngan nhat) -> chua DU cac tu
  // -> chua. FB tim mo (fuzzy) nen goi y dau nhieu khi khong lien quan.
  function bestCatIdx(texts, want) {
    var i;
    for (i = 0; i < texts.length; i++) { if (texts[i] === want) { return i; } }
    var best = -1, bestLen = 1e9;
    for (i = 0; i < texts.length; i++) {
      if (texts[i].indexOf(want) === 0 && texts[i].length < bestLen) {
        best = i; bestLen = texts[i].length;
      }
    }
    if (best >= 0) { return best; }
    var words = want.split(/\s+/).filter(function (w) { return w.length > 1; });
    if (words.length) {
      for (i = 0; i < texts.length; i++) {
        var du = true;
        for (var w = 0; w < words.length; w++) {
          if (texts[i].indexOf(words[w]) === -1) { du = false; break; }
        }
        if (du) { return i; }
      }
    }
    for (i = 0; i < texts.length; i++) { if (texts[i].indexOf(want) !== -1) { return i; } }
    // Nguoc lai: goi y NAM TRONG chu da go ("Nhà hàng Việt" -> "Nhà hàng"), lay dai nhat.
    var rev = -1, revLen = 0;
    for (i = 0; i < texts.length; i++) {
      if (texts[i].length >= 3 && want.indexOf(texts[i]) !== -1 && texts[i].length > revLen) {
        rev = i; revLen = texts[i].length;
      }
    }
    return rev;
  }

  function typeCategory(win, doc, cmd) {
    // O Hang muc co the render CHAM hon o Ten -> doi no xuat hien (poll toi ~10s)
    // truoc khi bo cuoc. Da gap: tim hut mot lan roi bao "khong dien hang muc".
    var cwait = 0;
    (function doiCat() {
      var cat = catInput(mainRoot(doc));
      if (cat) { fillCategory(win, doc, cmd, cat); return; }
      cwait += 700;
      if (cwait < 10000) { win.setTimeout(doiCat, 700); return; }
      report("no-category-input", "chờ mãi không thấy ô Hạng mục — form có: " + dumpInputs(mainRoot(doc)));
      afterCategory(win, doc, cmd);
    })();
  }

  function fillCategory(win, doc, cmd, cat) {
    setNative(win, cat, cmd.category);
    // Goi them mot phim de FB chac chan chay tim kiem.
    try { cat.dispatchEvent(new win.KeyboardEvent("keyup", { bubbles: true, key: " " })); } catch (e) {}
    var want = low(cmd.category);
    var tries = 0, max = Math.max(8, cmd.catTimeout || 14);
    (function pick() {
      tries += 1;
      var opts = optlist(doc);
      var texts = opts.map(function (o) { return low(textOf(o)); });
      var idx = opts.length ? bestCatIdx(texts, want) : -1;
      // Trung KHIT -> chon ngay. Khop mot phan thi CHO them vai nhip cho FB tim
      // xong (goi y dau hay la mac dinh cu), roi moi lay gan nhat -- de "Nghệ sĩ"
      // khong bi chon nham "Nghệ sĩ làm móng" khi FB chua kip tra ket qua.
      var tot = idx >= 0 && texts[idx] === want;
      if (tot || (idx >= 0 && tries >= 5)) {
        // CHON 1 LAN bang click that len dung option (KHONG ArrowDown/Enter -> tranh commit 2 lan).
        opts[idx].scrollIntoView({ block: "center" });
        clickReal(win, opts[idx]);
        var chose = textOf(opts[idx]).slice(0, 40);
        report("category-picked", chose + (tot ? "" : " (gần đúng với '" + cmd.category + "')"));
        win.setTimeout(function () {
          // DON: chi giu 1 hang muc = want; bo hang muc THUA (vd "Pháp lý" mac dinh, hay chon nham 2).
          var kq = donHangMucThua(win, doc, want);
          if (kq.bo.length) { report("category-extra-removed", "giữ '" + cmd.category + "', bỏ thừa: " + kq.bo.join(", ")); }
          // Chua co chip nao khop -> click lai 1 lan (option hien tai), roi don lai.
          if (!daCoHangMuc(doc, want)) {
            var again = optlist(doc);
            var texts2 = again.map(function (o) { return low(textOf(o)); });
            var i2 = again.length ? bestCatIdx(texts2, want) : -1;
            if (i2 >= 0) { again[i2].scrollIntoView({ block: "center" }); clickReal(win, again[i2]); }
            win.setTimeout(function () { donHangMucThua(win, doc, want); afterCategory(win, doc, cmd); }, 1400);
          } else {
            afterCategory(win, doc, cmd);
          }
        }, 1400);
        return;
      }
      if (tries < max) { win.setTimeout(pick, 700); return; }
      // KHONG danh lay goi y dau khi khong khop gi: da gap (5/9) go bay "xyzqwv"
      // -> tao page hang muc "Dịch vụ địa phương" ma nguoi dung khong hay. Bao
      // loi kem danh sach FB goi y de sua; dung o day (nut Tao se khong bat).
      var goi = opts.slice(0, 8).map(function (o) { return textOf(o).slice(0, 30); }).join(" | ");
      report("no-category-option", "gõ '" + cmd.category + "' " + (opts.length
             ? "không có hạng mục nào khớp. Facebook gợi ý: " + goi
             : "không ra gợi ý nào") + " — sửa hạng mục đúng ngôn ngữ giao diện acc rồi chạy lại");
    })();
  }

  function afterCategory(win, doc, cmd) {
    if (!cmd.submit) {
      // Chay thu: cho mot nhip roi bao nut Tao da BAT chua (bat = hang muc da
      // commit thanh cong). Giup do loi "hang muc khong chon duoc".
      win.setTimeout(function () {
        var btn = createButton(mainRoot(doc), win);
        var chips = hangMucChip(doc).map(function (c) { return c.ten; });
        report("filled-ready", "chạy thử: đã điền form — hạng mục ĐANG CHỌN: ["
               + chips.join(" | ") + "]"
               + (btn ? " — nút Tạo ĐÃ BẬT" : " — nút Tạo CHƯA bật"));
      }, 2500);
      return;
    }
    // Cho mot nhip cho nut Tao bat (sau khi chon hang muc), roi bam.
    var tries = 0;
    (function waitBtn() {
      tries += 1;
      var btn = createButton(mainRoot(doc), win);
      if (btn) {
        report("create-found", textOf(btn).slice(0, 30));
        // Bam nhieu cach: click that + ban phim (Enter/Space) khi nut dang focus.
        // Nut Tao page la thu FB chan manh nhat; thu du kieu cho chac.
        clickReal(win, btn);
        try { btn.focus(); } catch (e) {}
        key(win, btn, "Enter", "Enter", 13);
        key(win, btn, " ", "Space", 32);
        report("create-clicked", "đã bấm Tạo");
        win.setTimeout(function () { waitCreated(win, doc, cmd); }, 1500);
        return;
      }
      if (tries < 8) { win.setTimeout(waitBtn, 800); return; }
      report("no-create-button", "nút Tạo chưa bật (thiếu tên/hạng mục hợp lệ). Ô: " + dumpInputs(mainRoot(doc)));
    })();
  }

  function waitCreated(win, doc, cmd) {
    var tries = 0, max = Math.max(10, cmd.doneTimeout || 25);
    (function chk() {
      tries += 1;
      var url = "";
      try { url = win.location.href || ""; } catch (e) {}
      // Tao xong: FB roi khoi trang tao (sang trang page moi / buoc them anh).
      if (url.indexOf("pages/creation") === -1) {
        report("create-done", "đã rời trang tạo: " + url.slice(0, 120));
        return;
      }
      // Hoac form da bien mat / hien buoc them anh dai dien.
      try {
        var root = mainRoot(doc);
        if (!nameInput(root)) {
          report("create-done", "form đã đóng (trang đã tạo)");
          return;
        }
      } catch (e) {}
      if (tries < max) { win.setTimeout(chk, 1000); return; }
      report("create-blocked", "chờ " + tries + "s form không đổi — Facebook có thể "
             + "vẫn chặn tạo page tự động");
    })();
  }

  /* ------------------------------------------- tra cuu hang muc FB goi y */
  // Go tung chuoi vao o Hang muc, doc danh sach FB goi y (KHONG bam Tao). Dung
  // cho bang "Chon hang muc" trong tool: nguoi dung chon dung chu FB dang co,
  // khoi go tay sai. Chuoi rong -> danh sach mac dinh FB hien khi chua go gi.
  function runCatSearch(win, doc, cmd) {
    var qs = (cmd.queries && cmd.queries.length) ? cmd.queries : [cmd.query || ""];
    var out = {}, i = 0, cwait = 0;
    (function doiCat() {
      var cat = catInput(mainRoot(doc));
      if (!cat) {
        cwait += 700;
        if (cwait < 10000) { win.setTimeout(doiCat, 700); return; }
        report("no-category-input", "không thấy ô Hạng mục — form có: " + dumpInputs(mainRoot(doc)));
        return;
      }
      (function next() {
        if (i >= qs.length) { report("cat-list", JSON.stringify(out)); return; }
        var q = String(qs[i] || "");
        setNative(win, cat, q);
        try { cat.dispatchEvent(new win.KeyboardEvent("keyup", { bubbles: true, key: " " })); } catch (e) {}
        if (!q) { clickReal(win, cat); }      // o trong: mo danh sach mac dinh
        var last = "", same = 0, polls = 0;
        (function poll() {
          polls += 1;
          var texts = optlist(doc).map(function (o) { return textOf(o); }).filter(Boolean);
          var sig = texts.join("");
          if (texts.length && sig === last) { same += 1; } else { same = 0; }
          last = sig;
          // Danh sach dung yen 2 nhip lien tiep (FB tim xong) hoac het ~5s.
          if ((texts.length && same >= 2 && polls >= 3) || polls >= 10) {
            out[q] = texts;
            i += 1;
            report("cat-progress", i + "/" + qs.length + " '" + q + "': " + texts.length + " gợi ý");
            win.setTimeout(next, 300);
            return;
          }
          win.setTimeout(poll, 500);
        })();
      })();
    })();
  }

  /* ----------------------------------------- bat che do chuyen nghiep (pro) */
  // Nut "..." o header profile: [aria-haspopup=menu] nho, aria-label ve cai dat/
  // lua chon (khong theo chu cung -- nhan ca vi lan en).
  /* Nut "..." tren header profile. Nhan theo NHAN (vi + en) truoc; khong khop nhan -> nhan theo
   * CAU TRUC: nut nho [aria-haspopup=menu] nam CUNG HANG voi nut "Chỉnh sửa trang cá nhân" /
   * "Edit profile" (giao dien tieng Anh co ban nhan la "More" — khong chua "options"). */
  var DOTS_LABELS = ["cài đặt", "cai dat", "lựa chọn", "lua chon", "xem thêm", "xem them",
                     "settings", "options", "see options", "more", "actions", "menu"];
  function smallMenuButtons(doc) {
    var out = [];
    var list = doc.querySelectorAll('[aria-haspopup="menu"], [aria-haspopup="true"]');
    for (var i = 0; i < list.length; i++) {
      var b = list[i], r = b.getBoundingClientRect();
      if (r.width < 28 || r.width > 64 || r.height < 20 || r.height > 64) { continue; }
      if (!b.offsetParent) { continue; }
      out.push(b);
    }
    return out;
  }
  function editProfileButton(doc) {
    var bs = doc.querySelectorAll('[role="button"], a[role="link"]');
    for (var i = 0; i < bs.length; i++) {
      var t = low(textOf(bs[i]));
      if (t.length > 40) { continue; }
      if (t.indexOf("chỉnh sửa trang cá nhân") !== -1 || t.indexOf("chinh sua trang ca nhan") !== -1
          || t === "edit profile" || t.indexOf("edit profile") === 0) { return bs[i]; }
    }
    return null;
  }
  function coDauHieuPro(doc) {
    var t = "";
    try { t = low((doc.querySelector('[role="main"]') || doc.body).innerText || "").slice(0, 6000); } catch (e) {}
    return t.indexOf("professional dashboard") !== -1 || t.indexOf("bảng điều khiển chuyên nghiệp") !== -1
        || t.indexOf("bang dieu khien chuyen nghiep") !== -1;
  }
  function dotsLabelsDump(doc) {
    var xs = smallMenuButtons(doc).map(function (b) {
      return JSON.stringify((b.getAttribute("aria-label") || textOf(b) || "?").slice(0, 30));
    });
    return xs.slice(0, 8).join(", ") || "(không có nút menu nhỏ nào)";
  }
  function dotsButton(doc) {
    var cands = smallMenuButtons(doc);
    var found = null;
    // 1) theo nhan (lay nut CUOI khop — header profile thuong nam sau cac menu khac)
    for (var i = 0; i < cands.length; i++) {
      var al = low(cands[i].getAttribute("aria-label")) + " " + low(textOf(cands[i]));
      for (var k = 0; k < DOTS_LABELS.length; k++) {
        if (al.indexOf(DOTS_LABELS[k]) !== -1) { found = cands[i]; break; }
      }
    }
    if (found) { return found; }
    // 2) theo cau truc: cung hang (chenh dinh <= 40px) voi nut "Edit profile"
    var ep = editProfileButton(doc);
    if (ep) {
      var er = ep.getBoundingClientRect();
      var best = null, bestDx = 1e9;
      for (var j = 0; j < cands.length; j++) {
        var cr = cands[j].getBoundingClientRect();
        if (Math.abs(cr.top - er.top) <= 40 && cr.left > er.left) {
          var dx = cr.left - er.right;
          if (dx >= -5 && dx < bestDx) { best = cands[j]; bestDx = dx; }
        }
      }
      if (best) { return best; }
    }
    return null;
  }
  function menuItemBy(doc, keys) {
    var list = doc.querySelectorAll('[role="menuitem"]');
    for (var i = 0; i < list.length; i++) {
      var t = low(textOf(list[i]));
      for (var k = 0; k < keys.length; k++) {
        if (t.indexOf(keys[k]) !== -1) { return list[i]; }
      }
    }
    return null;
  }
  function dialogConfirm(doc, keys) {
    // Uu tien trong role=dialog; khong co thi tim ca trang (nut xac nhan doi khi
    // khong nam trong role=dialog).
    var scope = doc.querySelector('[role="dialog"]') || doc;
    var btns = Array.prototype.slice.call(scope.querySelectorAll('[role="button"], button'))
      .filter(function (el) {
        var r = el.getBoundingClientRect();
        return r.width > 50 && r.height > 20 && r.top > 0 && el.offsetParent;
      });
    if (!btns.length) { return null; }
    // Nut khop chu "bật/turn on/enable..." va NGAN (khong phai ca doan van ban).
    for (var i = 0; i < btns.length; i++) {
      var t = low(textOf(btns[i]));
      if (t.length > 25) { continue; }
      for (var k = 0; k < keys.length; k++) {
        if (t === keys[k] || t.indexOf(keys[k]) !== -1) { return btns[i]; }
      }
    }
    // Khong khop chu: chi lay nut phai-nhat khi CO role=dialog (tranh bam bay ba).
    if (doc.querySelector('[role="dialog"]')) {
      btns.sort(function (a, b) {
        return b.getBoundingClientRect().left - a.getBoundingClientRect().left;
      });
      return btns[0];
    }
    return null;
  }

  var PRO_KEYS = ["chuyên nghiệp", "chuyen nghiep", "professional"];
  var CONFIRM_KEYS = ["bật", "bat", "turn on", "enable", "chuyển", "chuyen",
                      "switch", "tiếp", "tiep", "continue", "next", "xác nhận",
                      "xac nhan", "confirm", "get started", "bắt đầu", "done", "got it"];

  /** MAN GIOI THIEU "Bat che do chuyen nghiep" ma Facebook TU BAT LEN tren trang ca
   *  nhan (khong qua menu "..."): anh to + 4 gach dau dong + nut "Tìm hiểu thêm" | "Bật".
   *  Man nay CHE nut "..." -> luong cu (dots -> menu) ket, roi bao nham "already-pro".
   *  Nhan dien: trang co chu "chế độ chuyên nghiệp"/"professional mode" + nut chu
   *  DUNG "Bật"/"Turn on" (khong phai "Tìm hiểu thêm"), lay nut RONG nhat (CTA xanh). */
  function proModalButton(doc) {
    var body = "";
    try { body = low(doc.body ? doc.body.innerText : ""); } catch (e) { return null; }
    if (body.indexOf("chế độ chuyên nghiệp") === -1 && body.indexOf("che do chuyen nghiep") === -1
        && body.indexOf("professional mode") === -1) { return null; }
    var best = null, bestW = 0;
    var btns = doc.querySelectorAll('[role="button"], button');
    for (var i = 0; i < btns.length; i++) {
      var el = btns[i];
      var r = el.getBoundingClientRect();
      if (r.width < 60 || r.height < 20 || r.top <= 0 || !el.offsetParent) { continue; }
      if (el.getAttribute("aria-disabled") === "true" || el.disabled) { continue; }
      var t = low(textOf(el));
      if (t === "bật" || t === "bat" || t === "turn on" || t === "turn on now"
          || t === "bật chế độ chuyên nghiệp" || t === "turn on professional mode"
          || t === "get started" || t === "bắt đầu" || t === "continue" || t === "tiếp tục") {
        if (r.width > bestW) { best = el; bestW = r.width; }
      }
    }
    return best;
  }
  function bamProModal(win, doc, btn, ghi) {
    activateItem(win, btn);
    report("promode-confirm", "bấm '" + textOf(btn).slice(0, 20) + "' trên màn giới thiệu" + (ghi || ""));
    // Sau "Bật" FB co the hien them hop xac nhan (role=dialog) -> bam not roi moi kiem.
    win.setTimeout(function () {
      var them = null;
      try { them = doc.querySelector('[role="dialog"]') ? dialogConfirm(doc, CONFIRM_KEYS) : null; } catch (e) {}
      if (them && them !== btn) {
        activateItem(win, them);
        report("promode-confirm", "bấm thêm '" + textOf(them).slice(0, 20) + "' (hộp xác nhận sau Bật)");
        win.setTimeout(function () { verifyPro(win, doc); }, 3000);
        return;
      }
      verifyPro(win, doc);
    }, 2500);
  }

  // Bam mot muc menu: click that + Enter khi dang focus (menu item React co the
  // nghe onKeyDown). Click chuot tong hop chap chon (da do: acc thi an acc khong).
  function activateItem(win, el) {
    try { el.focus(); } catch (e) {}
    clickReal(win, el);
    key(win, el, "Enter", "Enter", 13);
  }

  function runPromode(win, doc, cmd) {
    var lan = 0;
    // Thu toi 3 lan ca chuoi: mo menu -> bam muc -> cho hop thoai -> bam Bat.
    (function attempt() {
      lan += 1;
      // Man gioi thieu tu bat len -> bam "Bật" ngay, khong can qua menu "...".
      var pm = proModalButton(doc);
      if (pm) { bamProModal(win, doc, pm); return; }
      var dots = dotsButton(doc);
      if (!dots) { report("no-dots", "không thấy nút ... trên profile (nút menu nhỏ thấy: " + dotsLabelsDump(doc) + ")"); return; }
      clickReal(win, dots);
      if (lan === 1) { report("dots-clicked", ""); }

      var t1 = 0;
      (function waitItem() {
        t1 += 1;
        var it = menuItemBy(doc, PRO_KEYS);
        if (it) {
          var chu = textOf(it).slice(0, 40);
          if (low(chu).indexOf("tắt") !== -1 || low(chu).indexOf("tat ") !== -1
              || low(chu).indexOf("turn off") !== -1) {
            report("already-pro", chu);
            return;
          }
          win.setTimeout(function () {
            activateItem(win, it);
            report("promode-item", chu + (lan > 1 ? " (lần " + lan + ")" : ""));
            waitConfirm(win, doc, cmd, lan, retry);
          }, 400);
          return;
        }
        if (t1 < 10) { win.setTimeout(waitItem, 600); return; }
        retry("no-pro-item");
      })();

      function retry(vi_sao) {
        if (lan < 3) {
          // Dong menu/hop thoai roi thu lai.
          try { doc.body.dispatchEvent(new win.KeyboardEvent("keydown",
            { bubbles: true, key: "Escape" })); } catch (e) {}
          win.setTimeout(attempt, 1200);
        } else if (vi_sao === "no-pro-item") {
          report("no-pro-item", "không thấy mục 'Bật chế độ chuyên nghiệp' trong menu");
        } else {
          report("no-confirm", "không thấy hộp thoại xác nhận sau khi bấm mục");
        }
      }
    })();
  }

  function waitConfirm(win, doc, cmd, lan, retry) {
    var t2 = 0;
    (function poll() {
      t2 += 1;
      var btn = proModalButton(doc) || dialogConfirm(doc, CONFIRM_KEYS);
      if (btn) {
        activateItem(win, btn);
        report("promode-confirm", textOf(btn).slice(0, 20));
        win.setTimeout(function () { verifyPro(win, doc); }, 3000);
        return;
      }
      if (t2 < 16) { win.setTimeout(poll, 600); return; }
      retry("no-confirm");
    })();
  }

  function verifyPro(win, doc) {
    // Xac nhan: mo lai menu xem muc da doi thanh "Tắt chế độ chuyên nghiệp" chua.
    var dots = dotsButton(doc);
    if (!dots) { report("promode-done", "đã bấm Bật (không mở lại menu kiểm được)"); return; }
    clickReal(win, dots);
    win.setTimeout(function () {
      var it = menuItemBy(doc, PRO_KEYS);
      var chu = it ? low(textOf(it)) : "";
      // dong menu lai
      try { win.document.body.dispatchEvent(new win.KeyboardEvent("keydown",
        { bubbles: true, key: "Escape" })); } catch (e) {}
      if (chu.indexOf("tắt") !== -1 || chu.indexOf("tat ") !== -1
          || chu.indexOf("turn off") !== -1) {
        report("promode-done", "ĐÃ BẬT chế độ chuyên nghiệp (menu giờ là '" + chu + "')");
      } else {
        report("promode-done", "đã bấm Bật xong (kiểm menu: '" + (chu || "?") + "')");
      }
    }, 1500);
  }

  /* ---------------------------------------- chuyen ve acc CA NHAN neu dang o
   * CHE DO TRANG. FB dat cookie i_user khi ban "dung Facebook voi tu cach
   * Trang/ho so khac"; luc do tao page bi vuong ngu canh Trang. Cach chuyen
   * gon nhat: xoa cookie i_user (doc/ghi duoc qua JS vi khong HttpOnly) roi tai
   * lai -> FB tro ve chinh chu (c_user). Neu khong xoa duoc (loi/HttpOnly) thi
   * chi bao va tao bang ngu canh hien tai, KHONG lap vo han. */
  // Hoi TIEN TRINH CHA (Services.cookies, qua bridge qlfpc:pagemode): thay ca
  // cookie HttpOnly ma doc.cookie khong thay -- i_user do FB dat thuong HttpOnly,
  // neu chi tin doc.cookie thi khong bao gio phat hien dang o che do Trang.
  function pageModeParent(clear) {
    try {
      var ans = sendSyncMessage("qlfpc:pagemode", { clear: !!clear });
      var a = ans && ans.length ? ans[0] : null;
      if (a && typeof a.inPage === "boolean") { return a; }
    } catch (e) {}
    return null;
  }
  function inPageMode(doc) {
    var p = pageModeParent(false);
    if (p) { return p.inPage; }
    try { return /(?:^|;\s*)i_user=\d/.test(doc.cookie || ""); }
    catch (e) { return false; }
  }
  function clearIUser(win, doc) {
    var p = pageModeParent(true);          // cha xoa (ke ca HttpOnly)
    if (p && p.removed) { report("page-mode-cleared", "đã xoá cookie i_user (" + p.removed + ")"); }
    var dead = "i_user=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/;";
    try {
      doc.cookie = dead;
      doc.cookie = dead + "domain=.facebook.com;";
      doc.cookie = dead + "domain=facebook.com;";
    } catch (e) {}
  }
  // Tra ve true neu can DUNG luong hien tai (dang chuyen, se reload). false =
  // da la ca nhan, cu chay tiep.
  function ensurePersonal(win, doc) {
    if (!inPageMode(doc)) { return false; }
    var tried = false;
    try { tried = win.sessionStorage.getItem("qlfpc_toperson") === "1"; } catch (e) {}
    if (tried) {
      report("page-mode-stuck",
             "vẫn ở chế độ Trang sau khi thử chuyển — tạo bằng ngữ cảnh hiện tại");
      return false;
    }
    try { win.sessionStorage.setItem("qlfpc_toperson", "1"); } catch (e) {}
    report("page-mode", "acc đang ở CHẾ ĐỘ TRANG — chuyển về hồ sơ cá nhân rồi tải lại");
    clearIUser(win, doc);
    try { win.location.reload(); } catch (e) {}
    return true;   // dang reload -> onPage se chay lai, luc do khong con i_user
  }

  /* ================================================================ TAO TU BM
   * Luong tao page TU BEN TRONG Business Manager (business.facebook.com),
   * port tu extension "add page vao BM - grok" (chrome/src/content/taopage.js):
   *   Them -> menu "Tao Trang Facebook moi" -> dien Ten + Hang muc -> Next
   *   -> tich checkbox xac nhan -> Tao Trang -> Xong.
   * Khac luong acc (/pages/creation) o cho: PHAI bam Them mo form, va co buoc
   * Next + checkbox xac nhan. Dung lai bo helper cua luong acc (nameInput/
   * catInput/optlist/bestCatIdx/key/clickReal/createButton) — chi khac GOC tim
   * (dialog cua BM) va cac nut rieng cua BM. */
  function dialogEl(doc) { return doc.querySelector('[role="dialog"]'); }
  function bmRoot(doc) { return dialogEl(doc) || doc.querySelector('[role="main"]') || doc.body; }
  function shown(el) {
    try { return !!el.offsetParent || el.getBoundingClientRect().height > 0; } catch (e) { return false; }
  }
  function enabledEl(el) {
    return !!el && el.getAttribute("aria-disabled") !== "true" && !el.disabled;
  }
  /** Nhan cua nut: aria-label, khong co thi chu (gop khoang trang). */
  function labelOf(el) {
    var s = "";
    try { s = el.getAttribute("aria-label") || ""; } catch (e) {}
    if (!s) { s = textOf(el); }
    return s.replace(/\s+/g, " ").trim();
  }
  /** Dong dau cua chu (menu BM: dong 1 = ten muc, dong 2 = mo ta dai). */
  function firstLine(el) {
    return textOf(el).split(/\n/)[0].replace(/\s+/g, " ").trim();
  }
  /** Nut/menu-item khop MOT trong cac regex: so aria-label/chu gop (<=120 ky tu) HOAC dong dau.
   *  (Truoc day bo qua phan tu chu >60 ky tu -> mat mục "Tạo Trang Facebook mới" vi no kem mo ta.) */
  function btnByText(doc, regexes, root) {
    var scope = root || doc;
    var els = scope.querySelectorAll('[role="button"], button, [role="menuitem"], a[role="button"], a[role="menuitem"]');
    for (var i = 0; i < els.length; i++) {
      if (!shown(els[i])) { continue; }
      var s = labelOf(els[i]), f = firstLine(els[i]);
      if (s.length > 120) { s = ""; }
      if (!s && !f) { continue; }
      for (var r = 0; r < regexes.length; r++) {
        if ((s && regexes[r].test(s)) || (f && f.length <= 120 && regexes[r].test(f))) { return els[i]; }
      }
    }
    return null;
  }
  /** Liet ke (toi da n) nhan nut/menu dang hien -> chan doan khi khong tim thay. */
  function listBtns(doc, n) {
    var out = [];
    try {
      var els = doc.querySelectorAll('[role="menuitem"], [role="menu"] [role="button"], [role="dialog"] [role="button"]');
      if (!els.length) { els = doc.querySelectorAll('[role="button"], button'); }
      for (var i = 0; i < els.length && out.length < (n || 12); i++) {
        if (!shown(els[i])) { continue; }
        var s = firstLine(els[i]) || labelOf(els[i]);
        if (s) { out.push(s.slice(0, 32)); }
      }
    } catch (e) {}
    return out.join(" | ");
  }
  function nutNextBm(doc, root) {
    return btnByText(doc, [/^(Next|Tiếp|Tiếp tục|Continue)$/i], root);
  }
  /** Tich moi checkbox chua tick trong r. Tra so o vua tich. */
  function tickMissing(win, r) {
    var xs = r.querySelectorAll('input[type="checkbox"], [role="checkbox"]');
    var n = 0;
    for (var i = 0; i < xs.length; i++) {
      var el = xs[i];
      if (!shown(el)) { continue; }
      var on = el.checked === true || el.getAttribute("aria-checked") === "true";
      if (!on) { var lab = el.closest && el.closest("label"); clickReal(win, lab || el); n++; }
    }
    return n;
  }
  function confirmScreen(doc) {
    var t = "";
    try { var d = dialogEl(doc); t = low(textOf(d || doc.body)).slice(0, 500); } catch (e) {}
    return /chắc chắn muốn tiếp tục|are you sure|yêu cầu của bạn|your request/i.test(t);
  }
  /** Hop "Không thể tạo Trang" / "Unable to add Facebook Page" (vd: trung ten page da quan ly) -> chu loi, hoac "". */
  function loiTaoBm(doc) {
    try {
      var d = dialogEl(doc);
      if (!d) { return ""; }
      var t = textOf(d).replace(/\s+/g, " ");
      if (/Không thể tạo Trang|Unable to (add|create) (Facebook )?Page|Không thể thêm Trang/i.test(t)) {
        var m = t.match(/(Có vẻ như[^.]*\.|It looks like[^.]*\.|Vui lòng[^.]*\.|Please[^.]*\.)/i);
        return (m ? m[0] : t.slice(0, 160)).trim();
      }
    } catch (e) {}
    return "";
  }
  function createdBm(win, doc) {
    try {
      var h = win.location.href || "";
      if (/selected_asset_id=\d{5,}/i.test(h) && /selected_asset_type=page/i.test(h)) { return true; }
    } catch (e) {}
    try {
      var d = dialogEl(doc);
      if (/Đã tạo Trang|Page created|created the Page|đã tạo trang/i.test(textOf(d || doc.body))) { return true; }
    } catch (e) {}
    return false;
  }

  function runCreateBm(win, doc, cmd) {
    var buoc = 0;
    var ten = String(cmd.name || "").trim();
    var hangMuc = String(cmd.category || "").trim();
    var daThem = false, daMenuTao = false, daForm = false;
    var daTen = false, daHm = false, daChonHm = false, lanHm = 0;
    var daNext = false, daTich = false, daTao = false, daXong = false;
    var soCheckpoint = 0, soCho = 0, soMenuMiss = 0, ketThuc = false;
    if (!hangMuc) { report("no-category-option", "BM: thiếu HẠNG MỤC (bắt buộc)"); return; }
    function xong(state, detail) { if (ketThuc) { return; } ketThuc = true; report(state, detail); }
    function sau(ms) {
      win.setTimeout(function () {
        try { buocTiep(); } catch (e) { xong("error", "BM: " + String(e)); }
      }, ms);
    }
    sau(4000);

    function buocTiep() {
      if (ketThuc) { return; }
      var href = ""; try { href = win.location.href || ""; } catch (e) {}
      if (href.indexOf("/checkpoint") !== -1) {
        if (++soCheckpoint <= 4) { return sau(3000); }
        return xong("checkpoint", href.slice(0, 140));
      }
      if (href.indexOf("facebook.com/login") !== -1) { return xong("logged-out", href.slice(0, 140)); }

      buoc++;
      if (buoc > 40) {
        return xong("no-create-button", "BM hết bước — them=" + daThem + " menu=" + daMenuTao
          + " form=" + daForm + " ten=" + daTen + " hm=" + daHm + " chonhm=" + daChonHm
          + " next=" + daNext + " tich=" + daTich + " tao=" + daTao);
      }
      var r = bmRoot(doc);
      report("bm-step", "B" + buoc + " them=" + daThem + " menu=" + daMenuTao + " form=" + daForm
        + " ten=" + daTen + " hm=" + daHm + " chonhm=" + daChonHm + " next=" + daNext
        + " tich=" + daTich + " tao=" + daTao);

      // Hop "Không thể tạo Trang" (sau Next/Tao Trang, vd trung ten page da quan ly) = LOI tao:
      // bam Xong dong hop, bao create-failed de core KHONG coi la da tao (acc se nghi 3 ngay).
      var loiTxt = daNext ? loiTaoBm(doc) : "";
      if (loiTxt) {
        var nxL = btnByText(doc, [/^Xong$/i, /^Done$/i, /^Đóng$/i, /^Close$/i]);
        if (nxL) { clickReal(win, nxL); }
        return xong("create-failed", "Facebook báo không thể tạo Trang: " + loiTxt);
      }

      // Sau khi bam Tao Trang: cho thanh cong.
      if (daTao) {
        if (createdBm(win, doc)) {
          if (!daXong) {
            var nx = btnByText(doc, [/^Xong$/i, /^Done$/i, /^Finish$/i]);
            if (nx) { clickReal(win, nx); daXong = true; return sau(2000); }
          }
          return xong("create-done", "đã tạo page từ BM: " + ten);
        }
        if (++soCho >= 12) { return xong("create-blocked", "đã bấm Tạo Trang (BM) nhưng chưa thấy tạo xong"); }
        return sau(2500);
      }

      // 1) Chua co form: BAT BUOC bam Them -> "Tao Trang Facebook moi".
      if (!daForm) {
        if (!daThem) {
          var them = btnByText(doc, [/^(\+\s*)?Thêm$/i, /^(\+\s*)?Add$/i]);
          if (them) { clickReal(win, them); daThem = true; daMenuTao = false; report("bm-them", "đã bấm Thêm"); return sau(3000); }
          if (buoc > 12) { return xong("no-form", "BM: không thấy nút Thêm trên trang Trang của BM"); }
          return sau(2500);
        }
        if (!daMenuTao) {
          var mi = btnByText(doc, [/^Tạo Trang Facebook mới/i, /^Tạo Trang mới/i,
            /^Create a new Facebook Page/i, /^Create a new Page/i, /^Create New Page/i])
            || btnByText(doc, [/^Tạo Trang\b/i, /^Create Page\b/i]);
          if (mi) { clickReal(win, mi); daMenuTao = true; report("bm-menu", "đã bấm 'Tạo Trang Facebook mới': " + firstLine(mi).slice(0, 40)); return sau(3500); }
          // Menu co the con dang ve: cho them 1 nhip truoc khi bam Thêm lai (bam lai khi menu
          // dang mo = DONG menu). Bao danh sach muc dang thay de chan doan.
          soMenuMiss++;
          report("bm-menu-miss", "lần " + soMenuMiss + " chưa thấy mục tạo — menu: " + listBtns(doc, 10));
          if (soMenuMiss % 2 === 0) { daThem = false; }
          return sau(2000);
        }
        if (nameInput(r) && catInput(r)) { daForm = true; return sau(1200); }
        if (buoc > 20) { return xong("no-form", "BM: đã bấm Thêm nhưng không mở được form tạo page"); }
        return sau(2000);
      }

      if (!daTen) {
        var iTen = nameInput(r);
        if (!iTen) { if (buoc > 14) { return xong("no-name-input", "BM: không thấy ô Tên"); } return sau(2000); }
        setNative(win, iTen, ten); daTen = true; report("bm-ten", "đã gõ tên: " + ten); return sau(1500);
      }

      if (!daHm) {
        var iHm = catInput(r);
        if (!iHm) { if (buoc > 20) { return xong("no-category-option", "BM: không thấy ô Hạng mục"); } return sau(2000); }
        setNative(win, iHm, hangMuc);
        try { iHm.dispatchEvent(new win.KeyboardEvent("keyup", { bubbles: true, key: " " })); } catch (e) {}
        daHm = true; report("bm-hangmuc", "đã gõ hạng mục: " + hangMuc); return sau(2200);
      }

      if (!daChonHm) {
        var opts = optlist(doc);
        var texts = opts.map(function (o) { return low(textOf(o)); });
        lanHm++;
        if (!opts.length && lanHm <= 3) {
          var oMo = catInput(r); if (oMo) { try { oMo.focus(); } catch (e) {} key(win, oMo, "ArrowDown", "ArrowDown", 40); }
          return sau(1200);
        }
        var idx = opts.length ? bestCatIdx(texts, low(hangMuc)) : -1;
        if (idx < 0 && opts.length && lanHm >= 4) { idx = 0; }
        var khit = idx >= 0 && texts[idx] === low(hangMuc);
        if (khit || (idx >= 0 && lanHm >= 4)) {
          // CHON 1 LAN bang click that (BO ArrowDown+Enter -> tranh commit 2 lan = chon 2 hang muc).
          opts[idx].scrollIntoView({ block: "center" }); clickReal(win, opts[idx]);
          var wantHm = low(hangMuc);
          win.setTimeout(function () {
            var don = donHangMucThua(win, doc, wantHm);   // bo hang muc THUA (chi giu 1 = want)
            if (don.bo.length) { report("bm-chon-hm", "giữ '" + hangMuc + "', bỏ thừa: " + don.bo.join(", ")); }
          }, 1200);
          daChonHm = true; report("bm-chon-hm", textOf(opts[idx] || {}).slice(0, 40)); return sau(2600);
        }
        if (nutNextBm(doc, r) || confirmScreen(doc)) { daChonHm = true; return sau(800); }
        if (lanHm > 10) { return xong("no-category-option", "BM: không chọn được hạng mục '" + hangMuc + "' — gợi ý: " + texts.slice(0, 6).join(",")); }
        return sau(1500);
      }

      if (!daNext) {
        if (confirmScreen(doc)) { daNext = true; return sau(800); }
        var nn = nutNextBm(doc, r);
        if (nn) { clickReal(win, nn); daNext = true; report("bm-next", "đã bấm Next/Tiếp"); return sau(3500); }
        if (buoc > 26 && enabledEl(btnByText(doc, [/^(Tạo Trang|Create Page)$/i], r))) { daNext = true; daTich = true; return sau(500); }
        return sau(2000);
      }

      if (!daTich) {
        var n = tickMissing(win, bmRoot(doc));
        if (n > 0) { report("bm-tich", "tích " + n + " checkbox xác nhận"); return sau(1000); }
        daTich = true; return sau(600);
      }

      // Bam nut Tao Trang (theo chu truoc, phai dang bat; roi toi hinh dang).
      var ntTxt = btnByText(doc, [/^(Tạo Trang|Create Page)$/i, /^(Tạo|Create)$/i], bmRoot(doc));
      var nt = enabledEl(ntTxt) ? ntTxt : createButton(bmRoot(doc), win);
      if (!enabledEl(nt)) { nt = null; }
      if (nt) {
        // CHAY THU (submit=false): KHONG bam Tao (acc FB khong cho tao lien tuc). Bao hang muc dang chon.
        if (!cmd.submit) {
          var chips = hangMucChip(doc).map(function (c) { return c.ten; });
          return xong("filled-ready", "chạy thử BM: nút Tạo ĐÃ BẬT — hạng mục ĐANG CHỌN: ["
                      + chips.join(" | ") + "] — KHÔNG bấm Tạo");
        }
        clickReal(win, nt); try { nt.focus(); } catch (e) {} key(win, nt, "Enter", "Enter", 13);
        daTao = true; report("create-clicked", "đã bấm Tạo Trang (BM)"); return sau(4000);
      }
      var conThieu = tickMissing(win, bmRoot(doc));
      if (conThieu > 0) { daTich = false; return sau(1000); }
      return sau(2000);
    }
  }

  /* -------------------------------------------------------------- khoi dong */
  function onPage(win) {
    var href = "";
    try { href = win.location.href || ""; } catch (e) { return; }
    var cmd = getCommand();
    if (!cmd || !cmd.action) { return; }

    // Acc bi Facebook giu lai: /me hay /pages/creation deu bi nem ve checkpoint
    // hoac trang dang nhap. Bao NGAY -- day la chuyen cua ACC, khong phai form
    // chua tai; khoi cho het gio roi bao no-form nham.
    if (href.indexOf("facebook.com/checkpoint") !== -1) {
      // AN HAN 12s: fbskip_agent bam "Bo qua" neu checkpoint MEM -> trang chuyen tiep va onPage
      // chay lai o trang moi. Con ke checkpoint sau 12s -> checkpoint CUNG -> bao.
      win.setTimeout(function () {
        try {
          if ((win.location.href || "").indexOf("/checkpoint") !== -1) {
            report("checkpoint", (win.location.href || "").slice(0, 140));
          }
        } catch (e) {}
      }, 12000);
      return;
    }
    if (href.indexOf("facebook.com/login") !== -1) {
      report("logged-out", href.slice(0, 140));
      return;
    }

    // CHE DO TRANG -> chuyen ve ca nhan TRUOC moi thao tac (tao page / bat pro /
    // tra cuu hang muc). Neu dang chuyen (reload) thi dung o day, onPage chay lai.
    try {
      if (ensurePersonal(win, win.document)) { return; }
    } catch (e) { report("page-mode-error", String(e)); }

    if (cmd.action === "promode") {
      // Chay tren profile cua chinh acc (/me -> profile.php?id=...).
      if (href.indexOf("facebook.com") === -1
          || (href.indexOf("/profile.php") === -1 && href.indexOf("/me") === -1
              && href.indexOf("facebook.com/") === -1)) { return; }
      var w0 = 0, s0 = cmd.delay || 3000;
      win.setTimeout(function tick0() {
        w0 += s0;
        var doc = win.document;
        // Man gioi thieu "Bat che do chuyen nghiep" TU BAT LEN che ca trang ->
        // bam "Bật" ngay. Phai kiem TRUOC dots va TRUOC ket luan already-pro
        // (man che nut "..." lam luong cu bao nham "da la chuyen nghiep").
        var pm0 = proModalButton(doc);
        if (pm0) {
          try { bamProModal(win, doc, pm0, " (tự bật lên)"); }
          catch (e) { report("error", String(e)); }
          return;
        }
        if (dotsButton(doc)) {
          try { runPromode(win, doc, cmd); }
          catch (e) { report("error", String(e)); }
          return;
        }
        // Trang ĐÃ tải (co role=main + du chu) ma KHONG co nut "..." ca nhan ->
        // acc da o che do chuyen nghiep (layout profile pro khac han). Bao
        // already-pro thay vi cho het gio roi bao loi.
        var daTai = false;
        try {
          daTai = !!doc.querySelector('[role="main"]')
                  && (doc.body.innerText || "").length > 500;
        } catch (e) {}
        // CHI ket luan already-pro khi trang co DAU HIEU cua profile chuyen nghiep (nut "Bảng điều
        // khiển chuyên nghiệp" / "Professional dashboard"). Khong co dau hieu ma cung khong thay
        // nut "..." (vd giao dien tieng Anh doi nhan) -> tiep tuc cho, roi bao no-form kem chan doan
        // thay vi bao nham "da la chuyen nghiep" roi dung.
        if (daTai && w0 >= (cmd.markWait || 10000) && coDauHieuPro(doc)) {
          report("already-pro", "không thấy nút bật, trang có dấu hiệu chuyên nghiệp (Professional dashboard)");
          return;
        }
        if (w0 < (cmd.formTimeout || 22000)) { win.setTimeout(tick0, s0); return; }
        report("no-form", "chờ " + Math.round(w0 / 1000) + "s không thấy nút ... trên profile (nút menu nhỏ thấy: " + dotsLabelsDump(doc) + ")");
      }, s0);
      return;
    }

    if (cmd.action === "catsearch") {
      if (href.indexOf("facebook.com/pages/creation") === -1) { return; }
      var w1 = 0, s1 = cmd.delay || 3000;
      win.setTimeout(function tick1() {
        w1 += s1;
        if (nameInput(mainRoot(win.document))) {
          try { runCatSearch(win, win.document, cmd); }
          catch (e) { report("error", String(e)); }
          return;
        }
        if (w1 < (cmd.formTimeout || 30000)) { win.setTimeout(tick1, s1); return; }
        report("no-form", "chờ " + Math.round(w1 / 1000) + "s không thấy form tạo page");
      }, s1);
      return;
    }

    // TAO TU BM: chay tren business.facebook.com (KHONG phai /pages/creation).
    if (cmd.action === "create" && cmd.tuBm) {
      if (href.indexOf("business.facebook.com") === -1) { return; }
      try { runCreateBm(win, win.document, cmd); }
      catch (e) { report("error", "BM: " + String(e)); }
      return;
    }

    if (cmd.action !== "create") { return; }
    if (href.indexOf("facebook.com/pages/creation") === -1) { return; }

    // Form React nang, ve xong sau ~8-10s. Cho ro roi doi ban than o Ten hien
    // ra (poll) truoc khi dien.
    var waited = 0, step = cmd.delay || 3000;
    win.setTimeout(function tick() {
      waited += step;
      var root = mainRoot(win.document);
      if (nameInput(root)) {
        try { fillForm(win, win.document, cmd); }
        catch (e) { report("error", String(e)); }
        return;
      }
      if (waited < (cmd.formTimeout || 30000)) { win.setTimeout(tick, step); return; }
      report("no-form", "chờ " + Math.round(waited / 1000) + "s không thấy form tạo page");
    }, step);
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
