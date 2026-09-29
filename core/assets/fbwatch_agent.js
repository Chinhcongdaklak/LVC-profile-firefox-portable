/* Process script: TƯƠNG TÁC — xem video ở tab Reel + thả like, giả người thật.
 *
 * Chạy trong TIẾN TRÌNH NỘI DUNG (như fbchat_agent.js). Thao tác bằng sự kiện "người
 * thật" (setHandlingUserInput -> isTrusted); trình duyệt mở BÌNH THƯỜNG -> tránh chống bot.
 *
 * Bridge RIÊNG (không đụng agent khác):
 *   sendSyncMessage("qlfpw:cmd")     -> cha đọc <profile>/qlfp-watch.json
 *   sendAsyncMessage("qlfpw:report") -> cha ghi <profile>/qlfp-watch-result.json
 *
 * Lệnh: { action:"tuongtac", url:"https://www.facebook.com/reel/", so_video:N, so_phut:M,
 *         so_like:L, xem_giay_min:6, xem_giay_max:14 }
 * Bước: (1) nếu ĐANG dùng FB với tư cách PAGE -> chuyển về cá nhân; (2) vào /reel/;
 *       (3) xem từng reel, thả like tới L, chuyển reel kế; dừng khi đủ N video / hết M phút.
 * Báo state: "switched-personal" | "on-reel" | "progress" | "done" | "error" | "seen".
 */
"use strict";

if (typeof sendAsyncMessage === "function") {

  var lines = [];
  function report(obj) {
    try { obj.log = lines.slice(-25); sendAsyncMessage("qlfpw:report", obj); } catch (e) {}
  }
  function note(s) { lines.push(String(s)); }
  function getCommand() {
    try {
      var a = sendSyncMessage("qlfpw:cmd");
      var raw = a && a.length ? a[0] : "";
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function low(s) { return (s || "").toLowerCase(); }
  function txt(el) { try { return (el.textContent || "").trim(); } catch (e) { return ""; } }
  function vis(el) {
    try { var b = el.getBoundingClientRect(); return b.width > 8 && b.height > 8 && el.offsetParent !== null; }
    catch (e) { return false; }
  }
  function withUserInput(win, fn) {
    try { win.windowUtils.setHandlingUserInput(true); } catch (e) {}
    try { return fn(); } finally { try { win.windowUtils.setHandlingUserInput(false); } catch (e) {} }
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
  function pressKey(win, key, code, kc) {
    try {
      var el = win.document.activeElement || win.document.body;
      withUserInput(win, function () {
        ["keydown", "keyup"].forEach(function (t) {
          win.document.body.dispatchEvent(new win.KeyboardEvent(t, {
            bubbles: true, cancelable: true, key: key, code: code, keyCode: kc, which: kc }));
        });
      });
      return true;
    } catch (e) { return false; }
  }
  function nutTheoAria(doc, re) {
    var out = [];
    var els = doc.querySelectorAll('[aria-label],[role="button"]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var lb = (el.getAttribute("aria-label") || txt(el) || "");
      if (re.test(lb) && vis(el)) { out.push(el); }
    }
    return out;
  }

  // ------- nhận diện / chuyển về cá nhân -----------------------------------
  function dangLaPage(doc) {
    // FB hiện băng "Bạn đang dùng Facebook với tư cách <Trang>" / "You are using Facebook as"
    var body = low(doc.body ? doc.body.innerText : "");
    if (/đang dùng facebook với tư cách|using facebook as|bạn đang ở trang|switch out of/.test(body)) {
      return true;
    }
    // Nút "Chuyển" ở menu tài khoản khi đang là Page
    return nutTheoAria(doc, /chuyển ra khỏi|switch out of|thoát khỏi trang|dùng facebook với tư cách cá nhân/i).length > 0;
  }
  function veCaNhan(win, doc) {
    // Mở menu Tài khoản (avatar góc phải) rồi bấm chuyển về cá nhân.
    var mn = nutTheoAria(doc, /^(tài khoản|account|trang cá nhân của bạn|your profile)$/i);
    if (mn.length) { clickReal(win, mn[0]); }
    win.setTimeout(function () {
      var sw = nutTheoAria(doc, /chuyển ra khỏi|switch out of|dùng facebook với tư cách .*cá nhân|chuyển về trang cá nhân|xem trang cá nhân/i);
      if (sw.length) {
        clickReal(win, sw[0]);
        report({ state: "switched-personal", detail: "đã bấm chuyển về cá nhân: " + txt(sw[0]).slice(0, 40) });
      } else {
        report({ state: "seen", detail: "khong thay nut chuyen ve ca nhan | menu=" + mn.length });
      }
    }, 1500);
  }

  // ------- like + chuyển reel ---------------------------------------------
  function nutLike(doc) {
    // Reel có nút "Thích"/"Like"; đã thích thì aria có "Bỏ thích"/"Remove like" -> tránh gỡ like.
    var cand = nutTheoAria(doc, /^(thích|like)$/i);
    for (var i = 0; i < cand.length; i++) {
      var lb = low(cand[i].getAttribute("aria-label") || "");
      if (lb === "thích" || lb === "like") { return cand[i]; }
    }
    return null;
  }
  function daThich(doc) {
    return nutTheoAria(doc, /^(bỏ thích|remove like|đã thích|liked)$/i).length > 0;
  }
  function chuyenReelKe(win, doc) {
    // Reel chuyển bằng phím mũi tên xuống; dự phòng nút "Thẻ tiếp"/"Next".
    var nx = nutTheoAria(doc, /reel tiếp theo|thẻ tiếp theo|video tiếp theo|next reel|next card|^next$/i);
    if (nx.length) { clickReal(win, nx[0]); return "nut"; }
    pressKey(win, "ArrowDown", "ArrowDown", 40);
    return "phim";
  }

  // ------- vòng xem --------------------------------------------------------
  function onReel(win, doc, cmd) {
    var soVideo = Math.max(1, parseInt(cmd.so_video || 10, 10));
    var soLike = Math.max(0, parseInt(cmd.so_like || 0, 10));
    var xmin = Math.max(2, parseInt(cmd.xem_giay_min || 6, 10));
    var xmax = Math.max(xmin, parseInt(cmd.xem_giay_max || 14, 10));
    // Gioi han tuong tac 1 acc: uu tien gioi_han_giay (GIAY); khong co thi so_phut (phut).
    var hanGiay = parseInt(cmd.gioi_han_giay || 0, 10) || (Math.max(1, parseInt(cmd.so_phut || 1, 10)) * 60);
    var han = Date.now() + hanGiay * 1000;
    var st = { xem: 0, like: 0 };
    report({ state: "on-reel", detail: "bắt đầu xem: mục tiêu " + soVideo + " video, " + soLike + " like, ≤" + hanGiay + " giây" });

    function xong(vi) {
      report({ state: "done", detail: vi, xem: st.xem, like: st.like });
    }
    function motReel() {
      if (st.xem >= soVideo) { xong("đủ số video"); return; }
      if (Date.now() >= han) { xong("hết giờ"); return; }
      // Thả like nếu còn quota và reel này chưa thích.
      try {
        if (st.like < soLike && !daThich(doc)) {
          var lk = nutLike(doc);
          if (lk) { clickReal(win, lk); st.like++; note("like #" + st.like); }
        }
      } catch (e) {}
      var giay = xmin + Math.floor(Math.random() * (xmax - xmin + 1));
      win.setTimeout(function () {
        st.xem++;
        report({ state: "progress", detail: "xem " + st.xem + "/" + soVideo + ", like " + st.like + "/" + soLike + " (dừng " + giay + "s)", xem: st.xem, like: st.like });
        var cach = chuyenReelKe(win, doc);
        note("chuyen reel bang " + cach);
        win.setTimeout(motReel, 1800);      // chờ reel kế nạp
      }, giay * 1000);
    }
    win.setTimeout(motReel, 2500);
  }

  // ------- đọc THÔNG BÁO --------------------------------------------------
  var TB_URL = "https://www.facebook.com/notifications/";
  function dsThongBao(doc) {
    // Muc thong bao tren trang /notifications (best-effort, nhieu selector du phong).
    var out = [], seen = [];
    var q = '[role="main"] a[href][role="link"], [role="main"] [role="listitem"], [role="main"] [role="article"]';
    var els = doc.querySelectorAll(q);
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (!vis(el)) { continue; }
      var b = el.getBoundingClientRect();
      if (b.height < 40 || b.width < 200) { continue; }   // muc thong bao thuong cao/rong
      if (seen.indexOf(el) < 0) { seen.push(el); out.push(el); }
    }
    return out;
  }
  function docThongBao(win, doc, cmd, xong) {
    var muon = Math.max(1, parseInt(cmd.so_thong_bao || 0, 10));
    report({ state: "on-tb", detail: "đọc thông báo: mục tiêu " + muon });
    var tries = 0;
    (function tick() {
      tries += 1;
      var items = dsThongBao(doc);
      if (items.length < muon && tries < 15) {
        try { win.scrollTo(0, doc.body.scrollHeight); } catch (e) {}
        win.setTimeout(tick, 800); return;
      }
      var n = Math.min(muon, items.length);
      for (var i = 0; i < n; i++) {
        try { items[i].scrollIntoView({ block: "center" }); } catch (e) {}   // "đọc" = xem qua từng mục
      }
      report({ state: "tb-done", detail: "đã đọc " + n + "/" + muon + " thông báo", tb: n });
      xong(n);
    })();
  }

  var DA_CHAY = false, TB_XONG = false;
  function onPage(win) {
    var cmd = getCommand();
    if (!cmd || cmd.action !== "tuongtac") { return; }
    var doc = win.document, href = low(win.location.href);
    var reelUrl = cmd.url || "https://www.facebook.com/reel/";
    var soTB = parseInt(cmd.so_thong_bao || 0, 10) || 0;
    var soVideo = parseInt(cmd.so_video || 0, 10) || 0;

    if (href.indexOf("/checkpoint") !== -1) { report({ state: "error", detail: "checkpoint" }); return; }
    // Acc bi DANG XUAT giua chung -> ve trang login. Bao logged-out de cha goi mo-dun dang nhap lai.
    if (href.indexOf("/login") !== -1 || href.indexOf("login.php") !== -1) {
      report({ state: "logged-out", detail: href.slice(0, 120) }); return;
    }

    function sangReel() {
      if (soVideo > 0) {
        if (href.indexOf("/reel") === -1 && href.indexOf("/watch") === -1) {
          try { win.location.href = reelUrl; } catch (e) {}
        } else if (!DA_CHAY) {
          DA_CHAY = true;
          win.setTimeout(function () { onReel(win, doc, cmd); }, 3000);
        }
      } else {
        report({ state: "done", detail: "đã xong tương tác", tb: 0, xem: 0, like: 0 });
      }
    }
    function dieuHuongDau() {
      // Muc tieu ĐẦU: thông báo (nếu chọn) rồi mới tới reel.
      if (soTB > 0 && !TB_XONG) { try { win.location.href = TB_URL; } catch (e) {} }
      else { sangReel(); }
    }

    // Ở trang KHỞI ĐẦU (không phải reel/watch/notifications): xử lý quyền Page rồi điều hướng.
    if (href.indexOf("/reel") === -1 && href.indexOf("/watch") === -1
        && href.indexOf("/notifications") === -1) {
      win.setTimeout(function () {
        try {
          if (dangLaPage(doc)) {
            report({ state: "seen", detail: "đang là PAGE -> chuyển về cá nhân" });
            veCaNhan(win, doc);
            win.setTimeout(dieuHuongDau, 4000);
          } else {
            report({ state: "seen", detail: "đang là cá nhân" });
            dieuHuongDau();
          }
        } catch (e) { report({ state: "error", detail: "loi dieu huong: " + e }); }
      }, 2500);
      return;
    }

    // Phase THÔNG BÁO: đọc N rồi sang reel (hoặc xong nếu không xem video).
    if (soTB > 0 && !TB_XONG && href.indexOf("/notifications") !== -1) {
      win.setTimeout(function () {
        docThongBao(win, doc, cmd, function () { TB_XONG = true; sangReel(); });
      }, 2500);
      return;
    }

    // Phase REEL (xem video + like).
    sangReel();
  }

  var observer = {
    observe: function (subject, topic) {
      if (topic !== "content-document-global-created") { return; }
      var win = subject;
      try {
        if (win.top !== win) { return; }        // chỉ xử lý cửa sổ trên cùng
        try { win.navigator.__defineGetter__ && (win.navigator.webdriver = false); } catch (e) {}
        win.addEventListener("load", function onload() {
          win.removeEventListener("load", onload); onPage(win);
        }, { once: true });
      } catch (e) {}
    },
  };
  Services.obs.addObserver(observer, "content-document-global-created");
}
