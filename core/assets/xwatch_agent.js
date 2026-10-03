/* Process script: TUONG TAC tren X.com — luot newfeed (/home), dung lai doc bai,
 * tha tim, gap video thi bam xem.
 *
 * Cung khuon xpost_agent.js / fbwatch_agent.js: chay trong tien trinh noi dung, thao tac
 * bang su kien "nguoi that" (setHandlingUserInput -> isTrusted), trinh duyet mo BINH THUONG.
 *
 * Bridge RIENG (khong dung agent khac):
 *   sendSyncMessage("qlfpxw:cmd")     -> cha doc <profile>/qlfp-xwatch.json
 *   sendAsyncMessage("qlfpxw:report") -> cha ghi <profile>/qlfp-xwatch-result.json
 *
 * Lenh: { action:"xwatch", url:"https://x.com/home", so_like:L, so_video:V,
 *         gioi_han_giay:T, dung_min:5, dung_max:10 }
 *   - cuon xuong tung bai, DUNG LAI dung_min..dung_max giay (ngau nhien) de "doc";
 *   - tha tim toi khi du L bai (chon ngau nhien, bo qua bai da tim);
 *   - gap bai co VIDEO thi bam vao video (xem nhu tuong tac), toi da V video;
 *   - het T giay thi dung va bao "done".
 *
 * Trang thai: seen | on-home | progress | done | error | logged-out | x-locked.
 */
"use strict";

/* ---- phan THUAN (test bang node) ------------------------------------------------- */
/** xwPhanLoai(url, text) -> "x-home" | "x-login" | "x-locked" | "x" | "". THUAN. */
function xwPhanLoai(url, text) {
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
/** So giay dung lai o MOT bai: ngau nhien trong [min, max] (giay). THUAN. */
function xwGiayDung(min, max, rnd) {
  min = Math.max(1, parseInt(min, 10) || 5);
  max = Math.max(min, parseInt(max, 10) || 10);
  var r = typeof rnd === "number" ? rnd : Math.random();
  return min + Math.floor(r * (max - min + 1));
}
/** Co nen tha tim bai nay khong: con thieu tim va con it bai thi tim chac tay hon. THUAN.
 *  conTim = so tim con phai tha, conBai = so bai du kien con duoc xem. */
function xwNenTim(conTim, conBai, rnd) {
  if (conTim <= 0) { return false; }
  if (conBai <= conTim) { return true; }          // sap het bai -> tim ngay keo khong du
  var r = typeof rnd === "number" ? rnd : Math.random();
  return r < Math.max(0.35, conTim / Math.max(1, conBai));
}
/** Bang icon de chen sau comment (emoji pho thong, 1 ky tu hoac co bien the mau). */
var XW_ICONS = ["😀", "😁", "😂", "🤣", "😊", "😍", "🥰", "😎", "🤩", "🥳", "👍", "👏",
                "🙌", "🔥", "✨", "💯", "❤️", "🧡", "💛", "💚", "💙", "💜", "🌟", "⭐",
                "🎉", "🎊", "😉", "😇", "🤗", "😆", "🫶", "💫", "🌈", "💪", "🙏", "🚀"];
/** Chuoi NGAU NHIEN 3-5 icon. ``rnd`` la ham tra [0,1) (tiem de test). THUAN. */
function xwIcons(rnd) {
  var f = typeof rnd === "function" ? rnd : Math.random;
  var so = 3 + Math.floor(f() * 3);                     // 3, 4 hoac 5
  if (so > 5) { so = 5; }
  if (so < 3) { so = 3; }
  var out = "";
  for (var i = 0; i < so; i++) {
    out += XW_ICONS[Math.floor(f() * XW_ICONS.length) % XW_ICONS.length];
  }
  return out;
}
/** Soan noi dung comment = chu cua comment DAU TIEN + " " + icon, cat cho vua tran X. THUAN.
 *  Cat o ranh gioi TU (khong cat giua tu); rong -> "" (khong gui). */
function xwSoanComment(text, icon, toiDa) {
  toiDa = parseInt(toiDa, 10) || 260;
  icon = icon || "";
  var t = String(text || "").replace(/\s+/g, " ").trim();
  if (!t) { return ""; }
  var cho = toiDa - (icon ? icon.length + 1 : 0);
  if (cho < 10) { cho = 10; }
  if (t.length > cho) {
    var cat = t.slice(0, cho);
    var ngan = cat.replace(/\s+\S*$/, "").trim();
    t = ngan.length >= 10 ? ngan : cat.trim();
  }
  return icon ? t + " " + icon : t;
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { phanLoai: xwPhanLoai, giayDung: xwGiayDung, nenTim: xwNenTim,
                     icons: xwIcons, soanComment: xwSoanComment, ICONS: XW_ICONS };
}

if (typeof sendAsyncMessage === "function") {

  var lines = [];
  var dem = { xem: 0, like: 0, video: 0, cmt: 0 };
  function report(state, detail, extra) {
    lines.push(state + (detail ? ": " + detail : ""));
    var obj = { state: state, detail: detail || "", log: lines.slice(-30),
                xem: dem.xem, like: dem.like, video: dem.video, cmt: dem.cmt };
    if (extra) { for (var k in extra) { obj[k] = extra[k]; } }
    try { sendAsyncMessage("qlfpxw:report", obj); } catch (e) {}
  }
  function getCommand() {
    try {
      var a = sendSyncMessage("qlfpxw:cmd");
      var raw = a && a.length ? a[0] : "";
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function txt(el) { try { return (el.textContent || "").trim(); } catch (e) { return ""; } }
  function vis(el) {
    try {
      var b = el.getBoundingClientRect();
      return b.width > 8 && b.height > 8 && el.offsetParent !== null;
    } catch (e) { return false; }
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
        el.dispatchEvent(pe("pointerover")); el.dispatchEvent(me("mouseover"));
        el.dispatchEvent(pe("pointerdown")); el.dispatchEvent(me("mousedown"));
        el.dispatchEvent(pe("pointerup")); el.dispatchEvent(me("mouseup"));
        el.dispatchEvent(me("click"));
      });
      return true;
    } catch (e) { return false; }
  }

  /** Re chuot len nut, CHO X ve lai (React re-render khi hover) roi LAY LAI nut va bam.
   *  Bam thang khi vua cuon toi thi cu dau hay truot vao node da bi go -> phai hover truoc. */
  function hoverRoiBam(win, bai, testid, xong) {
    hoverRoiBamLay(win, function () { return nutTrongBai(bai, testid); }, xong);
  }
  /** Nhu hoverRoiBam nhung nut do ham ``lay()`` tra ve (dung cho link bai / nut Tra loi). */
  function hoverRoiBamLay(win, lay, xong) {
    var n = lay();
    if (!n) { xong(false); return; }
    try {
      var r = n.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      withUserInput(win, function () {
        n.dispatchEvent(new win.PointerEvent("pointerover", { bubbles: true, clientX: cx, clientY: cy, pointerType: "mouse", isPrimary: true }));
        n.dispatchEvent(new win.MouseEvent("mouseover", { bubbles: true, clientX: cx, clientY: cy }));
        n.dispatchEvent(new win.MouseEvent("mousemove", { bubbles: true, clientX: cx, clientY: cy }));
      });
    } catch (e) {}
    win.setTimeout(function () {
      var n2 = lay() || n;                          // lay LAI (co the la node moi sau khi hover)
      var ok = clickReal(win, n2);
      try { n2.click(); } catch (e) {}               // du phong: click that cua DOM
      xong(ok);
    }, 300);
  }

  /* ---- doc dong thoi gian ---------------------------------------------------- */
  function dsBai(doc) {
    var out = [];
    var els = doc.querySelectorAll('article[data-testid="tweet"], [data-testid="cellInnerDiv"] article');
    for (var i = 0; i < els.length; i++) {
      if (vis(els[i]) && out.indexOf(els[i]) < 0) { out.push(els[i]); }
    }
    return out;
  }
  function nutTrongBai(bai, testid) {
    try {
      var el = bai.querySelector('[data-testid="' + testid + '"]');
      return el && vis(el) ? el : null;
    } catch (e) { return null; }
  }
  function coVideo(bai) {
    try {
      return !!(bai.querySelector('[data-testid="videoPlayer"], [data-testid="videoComponent"], video, [data-testid="playButton"]'));
    } catch (e) { return false; }
  }
  function nutXemVideo(bai) {
    // Uu tien nut Play; khong co thi bam vao khung video.
    return nutTrongBai(bai, "playButton") || nutTrongBai(bai, "videoPlayer")
        || nutTrongBai(bai, "videoComponent");
  }
  /** Cuon tung nac nhu LAN CHUOT (khong nhay mot phat) toi khi bai nam giua man. */
  function cuonToi(win, doc, bai, xong) {
    var buoc = 0;
    (function nac() {
      buoc += 1;
      var r;
      try { r = bai.getBoundingClientRect(); } catch (e) { xong(); return; }
      var giua = win.innerHeight / 2;
      var lech = r.top + r.height / 2 - giua;
      if (Math.abs(lech) < 60 || buoc > 25) { xong(); return; }
      var di = Math.max(-260, Math.min(260, lech));      // moi nac <= 260px cho giong nguoi
      try {
        withUserInput(win, function () {
          win.scrollBy({ top: di, left: 0, behavior: "auto" });
          // Ban them su kien wheel de X biet nguoi dung dang lan chuot.
          doc.dispatchEvent(new win.WheelEvent("wheel", { bubbles: true, deltaY: di }));
        });
      } catch (e) {}
      win.setTimeout(nac, 160 + Math.floor(Math.random() * 120));
    })();
  }

  /* ---- COMMENT: vao 1 bai, lay comment DAU TIEN, dang lai + 3-5 icon --------- */
  /** Cho tới khi ``dieuKien()`` dung (hoac het ``hanMs``) roi goi ``xong(duoc)``. */
  function cho(win, dieuKien, hanMs, xong) {
    var het = Date.now() + hanMs;
    (function nhip() {
      var ok = false;
      try { ok = !!dieuKien(); } catch (e) { ok = false; }
      if (ok) { xong(true); return; }
      if (Date.now() >= het) { xong(false); return; }
      win.setTimeout(nhip, 500);
    })();
  }
  /** Link toi trang bai viet (the <time> trong bai) — bam vao day la mo bai (SPA). */
  function linkBai(bai) {
    try {
      var t = bai.querySelector('a[href*="/status/"] time');
      if (t && t.parentNode && vis(t.parentNode)) { return t.parentNode; }
      var ls = bai.querySelectorAll('a[href*="/status/"]');
      for (var i = 0; i < ls.length; i++) {
        var h = ls[i].getAttribute("href") || "";
        if (vis(ls[i]) && !/\/(photo|video|analytics|retweets|likes)\b/.test(h)) { return ls[i]; }
      }
    } catch (e) {}
    return null;
  }
  /** ID bai (so sau /status/) — dung lam dau vet "da xem" ben vung hon tham chieu DOM. */
  function idBai(bai) {
    var l = linkBai(bai);
    var m = l ? String(l.getAttribute("href") || "").match(/\/status\/(\d+)/) : null;
    return m ? m[1] : "";
  }
  /** Chu cua mot bai/comment (gop cac doan tweetText). */
  function chuBai(bai) {
    try {
      var ds = bai.querySelectorAll('[data-testid="tweetText"]');
      var out = [];
      for (var i = 0; i < ds.length; i++) {
        var t = txt(ds[i]);
        if (t) { out.push(t); }
      }
      return out.join(" ").replace(/\s+/g, " ").trim();
    } catch (e) { return ""; }
  }
  /** Tren TRANG BAI VIET: comment DAU TIEN co chu.
   *  Bai GOC khong phai luon la article thu 0: bai la mot phan cua chuoi thi X hien ca cac bai
   *  CHA o tren (loi that 2026-10-02: 2 bai khac nhau ra cung mot "comment" = bai trong chuoi).
   *  -> tim bai GOC theo id trong URL roi lay article NGAY SAU no; cua MINH thi bo qua. */
  function commentDau(doc, href) {
    var els;
    try { els = doc.querySelectorAll('article[data-testid="tweet"]'); } catch (e) { return null; }
    var ma = (String(href || "").match(/\/status\/(\d+)/) || [])[1] || "";
    var goc = -1;
    for (var i = 0; i < els.length; i++) {
      if (ma && idBai(els[i]) === ma) { goc = i; break; }
      // Bai GOC hien ngay THANG (khong phai link <time> ve chinh no) -> khong doc ra id.
      if (!idBai(els[i])) { goc = i; }
    }
    var batDau = goc >= 0 ? goc + 1 : 1;
    for (var j = batDau; j < els.length; j++) {
      if (!vis(els[j])) { continue; }
      var chu = chuBai(els[j]);
      if (chu) { return { el: els[j], chu: chu, vi_tri: j, tong: els.length, goc: goc }; }
    }
    return null;
  }
  function hopThoai(doc) {
    try {
      var ds = doc.querySelectorAll('[role="dialog"]');
      for (var i = 0; i < ds.length; i++) { if (vis(ds[i])) { return ds[i]; } }
    } catch (e) {}
    return null;
  }
  /** O soan TRA LOI dang NHAN DUOC CHU. Trang bai viet co the co NHIEU tweetTextarea_0
   *  (o inline + o trong hop thoai, co cai an) -> phai chon cai HIEN + contenteditable,
   *  uu tien cai nam trong hop thoai dang mo. */
  function oSoanReply(doc) {
    var ds;
    try { ds = doc.querySelectorAll('[data-testid="tweetTextarea_0"]'); } catch (e) { return null; }
    var dlg = hopThoai(doc);
    var ngoai = null;
    for (var i = 0; i < ds.length; i++) {
      var el = oGoDuoc(ds[i]);
      if (!el) { continue; }
      if (dlg && dlg.contains && dlg.contains(ds[i])) { return el; }
      if (!ngoai) { ngoai = el; }
    }
    return ngoai;
  }
  /** Node THUC SU go chu duoc: chinh no neu contenteditable, khong thi con chau editable. */
  function oGoDuoc(el) {
    if (!el || !vis(el)) { return null; }
    try {
      if (el.getAttribute("contenteditable") === "true" || el.isContentEditable) { return el; }
      var c = el.querySelector('[contenteditable="true"]');
      if (c && vis(c)) { return c; }
    } catch (e) {}
    return el;
  }
  function nutGuiReply(doc) {
    var dlg = hopThoai(doc);
    var ten = ['[data-testid="tweetButtonInline"]', '[data-testid="tweetButton"]'];
    var ngoai = null;
    for (var i = 0; i < ten.length; i++) {
      var ds;
      try { ds = doc.querySelectorAll(ten[i]); } catch (e) { continue; }
      for (var j = 0; j < ds.length; j++) {
        if (!vis(ds[j])) { continue; }
        if (dlg && dlg.contains && dlg.contains(ds[j])) { return ds[j]; }
        if (!ngoai) { ngoai = ds[j]; }
      }
    }
    return ngoai;
  }
  /** Chan doan o soan — in vao bao cao khi go chu that bai (de sua lan sau khong phai doan). */
  function chanDoanSoan(doc) {
    var n = 0, hien = 0, edit = 0;
    try {
      var ds = doc.querySelectorAll('[data-testid="tweetTextarea_0"]');
      n = ds.length;
      for (var i = 0; i < ds.length; i++) {
        if (vis(ds[i])) { hien += 1; }
        if (ds[i].getAttribute("contenteditable") === "true"
            || (ds[i].querySelector && ds[i].querySelector('[contenteditable="true"]'))) { edit += 1; }
      }
    } catch (e) {}
    var nut = nutGuiReply(doc);
    var ae = "";
    try {
      var a = doc.activeElement;
      ae = a ? (a.getAttribute("data-testid") || a.tagName.toLowerCase()) : "khong";
    } catch (e) { ae = "?"; }
    return "oSoan=" + n + "/hien=" + hien + "/edit=" + edit + ", dangChon=" + ae
           + ", hopThoai=" + (hopThoai(doc) ? 1 : 0)
           + ", nutGui=" + (nut ? (nut.getAttribute("data-testid") + ":"
               + (nut.getAttribute("aria-disabled") === "true" ? "khoa" : "bat")) : "khong");
  }
  /** Dat con tro VAO o soan (cuoi noi dung). execCommand("insertText") chen tai VUNG CHON —
   *  focus() mot minh co the khong dua con tro vao o -> go im lang. */
  function datConTro(win, doc, o) {
    try {
      o.focus();
      var sel = win.getSelection();
      var rg = doc.createRange();
      rg.selectNodeContents(o);
      rg.collapse(false);
      sel.removeAllRanges();
      sel.addRange(rg);
      return true;
    } catch (e) { return false; }
  }
  /** O soan dang GIU con tro go chu? (chinh no hoac con chau cua no dang duoc chon) */
  function dangGiuTro(doc, o) {
    try {
      var a = doc.activeElement;
      return !!a && (a === o || (o.contains && o.contains(a)) || (a.contains && a.contains(o)));
    } catch (e) { return false; }
  }
  /** Go chu vao o soan DraftJS — BAT DONG BO vi phai CHO focus vao o truoc khi go.
   *
   *  LOI THAT 2026-10-02: bam link mo bai xong, the <a> con GIU focus; go ngay thi
   *  execCommand("insertText") khong vao o nao ca (o soan van rong). Phai bam vao o soan,
   *  CHO ~0.5s, XAC MINH doc.activeElement la o soan roi moi go.
   *  insertText la duong DUY NHAT an tren x.com: beforeinput/paste tong hop bi DraftJS bo qua.
   *  ``lan`` >= 3 moi thu duong paste (du phong). xong(moTaDuong). */
  function goVaoOSoan(win, o, chu, lan, xong) {
    var doc = win.document;
    clickReal(win, o);
    try { o.focus(); } catch (e) {}
    win.setTimeout(function () {
      var o2 = oSoanReply(doc) || o;
      if (!dangGiuTro(doc, o2)) {            // chua vao o -> bam + focus lan nua roi cho tiep
        clickReal(win, o2);
        try { o2.focus(); } catch (e) {}
      }
      win.setTimeout(function () {
        var o3 = oSoanReply(doc) || o2;
        var giu = dangGiuTro(doc, o3);
        var tro = datConTro(win, doc, o3);
        var duong = (lan || 1) >= 3 ? "paste" : "insertText";
        try {
          if (duong === "insertText") {
            var ok = false;
            withUserInput(win, function () {
              try { ok = doc.execCommand("insertText", false, chu); } catch (e) { ok = false; }
            });
            duong += ok ? "" : "(execCommand=false)";
          } else {
            var dt = new win.DataTransfer();
            dt.setData("text/plain", chu);
            withUserInput(win, function () {
              o3.dispatchEvent(new win.ClipboardEvent("paste",
                { bubbles: true, cancelable: true, clipboardData: dt }));
            });
          }
        } catch (e) { xong(duong + "(loi " + String(e).slice(0, 40) + ")"); return; }
        xong(duong + (giu ? "" : "+o-chua-giu-con-tro") + (tro ? "" : "+khong-dat-duoc-con-tro"));
      }, 400);
    }, 500);
  }
  function xoaOSoan(win, o) {
    try {
      clickReal(win, o);
      o.focus();
      withUserInput(win, function () {
        win.document.execCommand("selectAll", false, null);
        win.document.execCommand("delete", false, null);
      });
    } catch (e) {}
  }
  /** Ve lai /home KHONG tai lai trang (tai lai = agent chay lai tu dau -> dem sai). */
  function veHome(win, doc, xong) {
    var oHome = function () { return /\/home(\b|$|\?)/.test(String(win.location.href || "")); };
    if (oHome()) { xong(true); return; }
    try { withUserInput(win, function () { win.history.back(); }); } catch (e) {}
    cho(win, oHome, 8000, function (duoc) {
      if (duoc) { xong(true); return; }
      var nav = null;
      try {
        nav = doc.querySelector('[data-testid="AppTabBar_Home_Link"], a[href="/home"]');
      } catch (e) {}
      if (nav) { clickReal(win, nav); }
      cho(win, oHome, 8000, xong);
    });
  }
  /** Vao bai ``bai``, lay comment dau tien, dang lai + 3-5 icon, roi ve /home.
   *  ``xong(ok, moTa)``. KHONG nem; moi buoc hong deu bao ro ly do. */
  function lamComment(win, doc, bai, xong, thu) {
    var truoc = String(win.location.href || "");
    // Phai doi SANG trang bai viet KHAC trang dang mo — con o trang bai cu thi se doc lai
    // dung comment cu (loi that 2026-10-02: 2 bai lien tiep ra cung mot comment).
    var oStatus = function () {
      var h = String(win.location.href || "");
      return /\/status\/\d+/.test(h) && h !== truoc;
    };
    if (!linkBai(bai)) { xong(false, "khong thay link bai de mo"); return; }
    hoverRoiBamLay(win, function () { return linkBai(bai); }, function () {
      cho(win, oStatus, 12000, function (vao) {
        if (!vao) { xong(false, "bam vao bai nhung khong mo duoc trang bai viet"); return; }
        var nay = function () { return String(win.location.href || ""); };
        cho(win, function () { return !!commentDau(doc, nay()); }, 15000, function (coCmt) {
          var c = coCmt ? commentDau(doc, nay()) : null;
          if (!c || !c.chu) {
            veHome(win, doc, function () { xong(false, "bai nay chua co comment nao de lay"); });
            return;
          }
          var icon = xwIcons();
          var noi = xwSoanComment(c.chu, icon);
          if (!noi) {
            veHome(win, doc, function () { xong(false, "comment dau tien khong co chu"); });
            return;
          }
          report("progress", "comment: bai goc o article " + (c.goc + 1) + ", comment la article "
                 + (c.vi_tri + 1) + "/" + c.tong
                 + " \"" + c.chu.slice(0, 50) + "\" | " + chanDoanSoan(doc));
          guiComment(win, doc, noi, function (ok, vi) {
            veHome(win, doc, function () {
              xong(ok, (ok ? 'da comment "' : "KHONG comment duoc \"") + noi.slice(0, 70)
                   + '"' + (vi ? " (" + vi + ")" : ""));
            });
          }, thu);
        });
      });
    });
  }
  /** Go ``noi`` vao o tra loi roi bam Gui; xac minh o soan rong tro lai. xong(ok, moTa).
   *  ``thu`` = CHE DO THU: go chu xong thi DUNG, khong bam Gui (de soi khong lam rac). */
  function guiComment(win, doc, noi, xong, thu) {
    var lanGo = 0;
    function moO(tiep) {
      var o = oSoanReply(doc);
      if (o) { tiep(o); return; }
      var nut = null;                                  // chua co o soan -> bam nut Tra loi
      try { nut = doc.querySelector('article[data-testid="tweet"] [data-testid="reply"]'); } catch (e) {}
      if (nut) { clickReal(win, nut); }
      cho(win, function () { return !!oSoanReply(doc); }, 8000, function () { tiep(oSoanReply(doc)); });
    }
    moO(function (o) {
      if (!o) { xong(false, "khong thay o soan tra loi"); return; }
      (function goVaKiem() {
        lanGo += 1;
        goVaoOSoan(win, oSoanReply(doc) || o, noi, lanGo, function (cach) {
        win.setTimeout(function () {
          var o2 = oSoanReply(doc) || o;
          var hien = txt(o2).replace(/\s+/g, " ").trim();
          var dau = noi.slice(0, 14).replace(/\s+/g, " ").trim();
          var vao = dau && hien.indexOf(dau) >= 0;
          var lap = vao && dau && hien.split(dau).length - 1 > 1;
          report("progress", "comment: go lan " + lanGo + " (" + cach + ") -> o soan \""
                 + hien.slice(0, 40) + "\"" + (vao ? (lap ? " [LAP]" : " [vao]") : " [chua vao]")
                 + " | " + chanDoanSoan(doc));
          if (!vao || lap) {
            if (lanGo >= 3) {
              xong(false, "go chu vao o soan KHONG duoc sau 3 cach (cuoi: " + (cach || "?")
                   + (lap ? " — chu bi LAP" : "") + ", o soan: \"" + hien.slice(0, 30) + "\", "
                   + chanDoanSoan(doc) + ")");
              return;
            }
            xoaOSoan(win, o2);
            win.setTimeout(goVaKiem, 600);
            return;
          }
          if (thu) { xong(false, "CHE DO THU: da go xong, KHONG bam Gui (chu: \""
                           + hien.slice(0, 60) + "\")"); return; }
          // Cho nut Gui bat len roi bam.
          cho(win, function () {
            var n = nutGuiReply(doc);
            return n && n.getAttribute("aria-disabled") !== "true" && !n.disabled;
          }, 15000, function (bat) {
            var n = nutGuiReply(doc);
            if (!bat || !n) { xong(false, "nut Tra loi khong bat len (" + chanDoanSoan(doc) + ")"); return; }
            clickReal(win, n);
            try { n.click(); } catch (e) {}
            cho(win, function () {
              var ox = oSoanReply(doc);
              return !ox || txt(ox).replace(/\s+/g, " ").trim().indexOf(noi.slice(0, 14)) < 0;
            }, 20000, function (sach) {
              if (sach) { xong(true, "go " + (cach || "?") + ", lan " + lanGo); return; }
              xong(false, "bam Tra loi roi ma chu van con trong o soan");
            });
          });
        }, 1400);
        });
      })();
    });
  }

  /* ---- vong tuong tac -------------------------------------------------------- */
  var DANG_CHAY = false;
  function chayTuongTac(win, doc, cmd) {
    var soLike = parseInt(cmd.so_like || 0, 10) || 0;
    var soVideo = parseInt(cmd.so_video || 0, 10) || 0;
    var soComment = parseInt(cmd.so_comment || 0, 10) || 0;
    var han = (parseInt(cmd.gioi_han_giay || 0, 10) || 120) * 1000;
    var dungMin = parseInt(cmd.dung_min || 5, 10) || 5;
    var dungMax = parseInt(cmd.dung_max || 10, 10) || 10;
    var batDau = Date.now();
    var daXem = [];          // node cac bai da dung lai (tranh xem lai khi DOM doi)
    var daId = {};           // id bai da xem (ben vung khi ve tu trang bai -> DOM dung moi)
    var khongThayLan = 0;

    report("on-home", "bat dau luot newfeed: " + soLike + " tim, " + soVideo + " video, "
           + soComment + " comment, " + Math.round(han / 1000) + "s, dung "
           + dungMin + "-" + dungMax + "s/bai");

    function conGiay() { return Math.max(0, Math.round((han - (Date.now() - batDau)) / 1000)); }

    function xong(vi) {
      report("done", "xong: xem " + dem.xem + " bai, tim " + dem.like + "/" + soLike
             + ", video " + dem.video + "/" + soVideo + ", comment " + dem.cmt + "/" + soComment
             + (vi ? " (" + vi + ")" : ""));
    }

    function baiKeTiep() {
      var ds = dsBai(doc);
      for (var i = 0; i < ds.length; i++) {
        if (daXem.indexOf(ds[i]) >= 0) { continue; }
        var ma = idBai(ds[i]);
        if (ma && daId[ma]) { daXem.push(ds[i]); continue; }
        return ds[i];
      }
      return null;
    }

    function motBai() {
      if (Date.now() - batDau >= han) { xong("het gio"); return; }
      // Chi quet dong thoi gian khi DANG o /home (o trang bai viet thi article cung khop
      // selector -> de doc nham). Khong ve duoc /home thi dung, bao ro.
      if (!/\/home(\b|$|\?)/.test(String(win.location.href || ""))) {
        report("progress", "khong o /home (" + String(win.location.href).slice(0, 70) + ") -> ve home");
        veHome(win, doc, function (ve) {
          if (!ve) { xong("khong ve duoc /home"); return; }
          win.setTimeout(motBai, 1200);
        });
        return;
      }
      var bai = baiKeTiep();
      if (!bai) {
        // Het bai trong DOM -> cuon xuong cho X nap them.
        khongThayLan += 1;
        if (khongThayLan > 20) { xong("khong nap them duoc bai"); return; }
        try {
          withUserInput(win, function () {
            win.scrollBy({ top: 700, left: 0, behavior: "auto" });
            doc.dispatchEvent(new win.WheelEvent("wheel", { bubbles: true, deltaY: 700 }));
          });
        } catch (e) {}
        win.setTimeout(motBai, 1200);
        return;
      }
      khongThayLan = 0;
      daXem.push(bai);
      var maBai = idBai(bai);
      if (maBai) { daId[maBai] = 1; }
      cuonToi(win, doc, bai, function () {
        var giay = xwGiayDung(dungMin, dungMax);
        dem.xem += 1;

        // Gap VIDEO -> bam xem (tinh la tuong tac).
        var viec = [];
        if (soVideo > 0 && dem.video < soVideo && coVideo(bai)) {
          var nv = nutXemVideo(bai);
          if (nv) {
            try {
              var rv = nv.getBoundingClientRect();
              withUserInput(win, function () {
                nv.dispatchEvent(new win.MouseEvent("mouseover", { bubbles: true, clientX: rv.left + rv.width / 2, clientY: rv.top + rv.height / 2 }));
              });
            } catch (e) {}
            if (clickReal(win, nv)) {
              dem.video += 1;
              var v = null;
              try { v = bai.querySelector("video"); } catch (e) {}
              viec.push(v && !v.paused ? "bam xem video (dang chay)" : "bam xem video");
              giay = Math.max(giay, dungMax);    // xem video thi nan lai lau hon chut
            }
          }
        }

        // Tha TIM: chon ngau nhien, bo qua bai da tim san. BAM roi XAC MINH o nhip SAU
        // (React doi nut like -> unlike cham) — chi dem khi that su da tim.
        var muonTim = false;
        if (dem.like < soLike) {
          var daTim = nutTrongBai(bai, "unlike");
          var nut = nutTrongBai(bai, "like");
          muonTim = !daTim && !!nut
                    && xwNenTim(soLike - dem.like, Math.max(1, Math.round(conGiay() / Math.max(1, (dungMin + dungMax) / 2))));
        }

        function ketBai() {
          // COMMENT: vao bai, lay comment dau tien dang lai + 3-5 icon (lam SAU CUNG vi roi /home).
          if (dem.cmt < soComment && Date.now() - batDau < han && linkBai(bai)) {
            report("progress", "bai " + dem.xem + ": vao bai lay comment dau tien... (comment "
                   + dem.cmt + "/" + soComment + ")");
            lamComment(win, doc, bai, function (ok, mo) {
              if (ok) { dem.cmt += 1; }
              viec.push(mo || (ok ? "comment" : "comment hong"));
              baoRoiDoi();
            }, !!cmd.thu);
            return;
          }
          baoRoiDoi();
        }
        function baoRoiDoi() {
          report("progress", "bai " + dem.xem + ": dung " + giay + "s"
                 + (viec.length ? " + " + viec.join(" + ") : "") + " — tim " + dem.like + "/" + soLike
                 + ", video " + dem.video + "/" + soVideo + ", comment " + dem.cmt + "/" + soComment
                 + ", con " + conGiay() + "s");
          win.setTimeout(motBai, giay * 1000);
        }

        if (!muonTim) { ketBai(); return; }
        // Bam tim roi XAC MINH o nhip SAU: nut phai doi thanh "unlike". Chua doi -> bam lai MOT lan.
        var lanBam = 0;
        (function bamVaKiem() {
          lanBam += 1;
          hoverRoiBam(win, bai, "like", function () {
            win.setTimeout(function () {
              if (nutTrongBai(bai, "unlike")) {
                dem.like += 1;
                viec.push(lanBam > 1 ? "tha tim (bam lai lan " + lanBam + ")" : "tha tim");
                ketBai(); return;
              }
              if (lanBam < 3) { bamVaKiem(); return; }
              viec.push("TIM KHONG AN (nut khong doi sang unlike sau " + lanBam + " lan bam)");
              ketBai();
            }, 1200);
          });
        })();
      });
    }

    win.setTimeout(motBai, 1500);
  }

  /* ---- SOI (chan doan, chi doc + thu go 1 lan) -------------------------------- */
  function moTaEl(el) {
    if (!el) { return "null"; }
    var ra = [];
    try {
      ra.push(el.tagName.toLowerCase());
      ["data-testid", "contenteditable", "role", "aria-readonly", "aria-label", "tabindex",
       "data-text", "spellcheck"].forEach(function (k) {
        var v = el.getAttribute(k);
        if (v !== null) { ra.push(k + "=" + String(v).slice(0, 40)); }
      });
      var b = el.getBoundingClientRect();
      ra.push("ô=" + Math.round(b.left) + "," + Math.round(b.top) + " " + Math.round(b.width)
              + "x" + Math.round(b.height));
    } catch (e) { ra.push("loi " + e); }
    return ra.join(" ");
  }
  function soiComment(win, doc, cmd) {
    var ghi = [];
    function bao(st) { report(st, ghi.join(" || ").slice(0, 3000)); }
    var tiep = function () {
      ghi.push("url=" + String(win.location.href));
      var els = doc.querySelectorAll('article[data-testid="tweet"]');
      ghi.push("so_article=" + els.length);
      for (var i = 0; i < els.length && i < 6; i++) {
        ghi.push("[" + i + "] id=" + (idBai(els[i]) || "-") + " chu=\""
                 + chuBai(els[i]).slice(0, 50) + "\"");
      }
      var ds = doc.querySelectorAll('[data-testid="tweetTextarea_0"]');
      ghi.push("so_oSoan=" + ds.length);
      for (var j = 0; j < ds.length; j++) {
        ghi.push("oSoan[" + j + "] " + moTaEl(ds[j]) + " | hien=" + (vis(ds[j]) ? 1 : 0)
                 + " | con_edit=" + moTaEl(ds[j].querySelector('[contenteditable="true"]')));
      }
      ghi.push("nutGui=" + moTaEl(nutGuiReply(doc)));
      ghi.push("docFocus=" + (doc.hasFocus ? doc.hasFocus() : "?"));
      var o = oSoanReply(doc);
      if (!o) { bao("seen"); return; }
      var thu = "XINCHAO123";
      clickReal(win, o);
      ghi.push("activeElement sau click=" + moTaEl(doc.activeElement));
      var tro = datConTro(win, doc, o);
      var ok = false;
      withUserInput(win, function () {
        try { ok = doc.execCommand("insertText", false, thu); } catch (e) { ghi.push("loi exec " + e); }
      });
      ghi.push("datConTro=" + tro + " execCommand=" + ok);
      win.setTimeout(function () {
        var o2 = oSoanReply(doc) || o;
        ghi.push("sau 1.5s o soan=\"" + txt(o2).slice(0, 60) + "\" nutGui="
                 + moTaEl(nutGuiReply(doc)));
        try {
          var ae = doc.activeElement;
          ghi.push("activeElement=" + moTaEl(ae));
          ghi.push("sel=" + String(win.getSelection()).slice(0, 30)
                   + " anchor=" + moTaEl(win.getSelection().anchorNode
                        && win.getSelection().anchorNode.parentNode));
        } catch (e) {}
        bao("done");
      }, 1500);
    };
    var href = String(win.location.href || "");
    if (/\/status\/\d+/.test(href)) { tiep(); return; }
    var bai = dsBai(doc)[0];
    if (!bai) { report("error", "khong thay bai nao tren /home"); return; }
    ghi.push("bam bai id=" + (idBai(bai) || "-"));
    hoverRoiBamLay(win, function () { return linkBai(bai); }, function () {
      cho(win, function () { return /\/status\/\d+/.test(String(win.location.href || "")); },
          12000, function (vao) {
        if (!vao) { report("error", "khong mo duoc trang bai viet"); return; }
        cho(win, function () { return !!oSoanReply(doc); }, 10000, function () {
          win.setTimeout(tiep, 1200);
        });
      });
    });
  }

  function onPage(win) {
    var cmd = getCommand();
    if (cmd && cmd.action === "cmtprobe") {
      var d2 = win.document;
      if (String(win.location.href || "").indexOf("x.com") < 0) { return; }
      if (DANG_CHAY) { return; }
      DANG_CHAY = true;
      win.setTimeout(function () { soiComment(win, d2, cmd); }, 2500);
      return;
    }
    if (cmd && cmd.action === "xdoc") {       // CHI DOC: dump chu cua trang (xac minh doc lap)
      if (String(win.location.href || "").indexOf("x.com") < 0) { return; }
      if (DANG_CHAY) { return; }
      DANG_CHAY = true;
      var dd = win.document;
      // Cho dong thoi gian nap du vai bai (trang /with_replies nap dan) roi moi dump.
      cho(win, function () {
        // Dong thoi gian nap DAN -> cuon xuong cho no ve them bai.
        try { win.scrollBy({ top: 500, left: 0, behavior: "auto" }); } catch (e) {}
        return dd.querySelectorAll('article[data-testid="tweet"]').length >= 5;
      }, 20000, function () {
        var ra = [];
        try {
          var els = dd.querySelectorAll('article[data-testid="tweet"]');
          for (var i = 0; i < els.length && i < 10; i++) {
            ra.push("[" + i + "] " + chuBai(els[i]).slice(0, 110));
          }
        } catch (e) { ra.push("loi " + e); }
        report("done", "url=" + String(win.location.href) + " || " + ra.join(" || "));
      });
      return;
    }
    if (!cmd || cmd.action !== "xwatch") { return; }
    var doc = win.document;
    var href = String(win.location.href || "");
    if (href.indexOf("facebook.com") !== -1) { return; }     // agent nay chi lam viec tren X
    var man = xwPhanLoai(href, doc.body ? doc.body.innerText.slice(0, 4000) : "");
    if (!man) { return; }
    if (man === "x-login") { report("logged-out", href.slice(0, 120)); return; }
    if (man === "x-locked") { report("x-locked", href.slice(0, 120)); return; }
    if (man !== "x-home") {
      report("seen", "chua o /home (" + href.slice(0, 80) + ") -> chuyen ve home");
      try { win.location.href = cmd.url || "https://x.com/home"; } catch (e) {}
      return;
    }
    if (DANG_CHAY) { return; }
    DANG_CHAY = true;
    // Cho dong thoi gian render xong roi hay luot.
    // (ten bien KHONG duoc la "cho" — se de len ham cho() o tren do var hoisting -> TypeError)
    var lanDoi = 0;
    (function doi() {
      lanDoi += 1;
      if (dsBai(doc).length > 0) { chayTuongTac(win, doc, cmd); return; }
      if (lanDoi > 30) { report("error", "khong thay bai nao tren dong thoi gian"); return; }
      win.setTimeout(doi, 1000);
    })();
  }

  // Seam de THUOC chay buoc comment tren DOM gia (node): khong anh huong luc chay that.
  if (typeof module !== "undefined" && module.exports) {
    module.exports.thu = { lamComment: lamComment, guiComment: guiComment,
                           commentDau: commentDau, linkBai: linkBai, idBai: idBai,
                           chuBai: chuBai, veHome: veHome, oSoanReply: oSoanReply,
                           nutGuiReply: nutGuiReply, dem: dem };
  }

  var observer = {
    observe: function (subject, topic) {
      if (topic !== "content-document-global-created") { return; }
      var win = subject;
      try {
        if (win.top !== win) { return; }          // chi xu ly cua so tren cung
        win.addEventListener("load", function onload() {
          win.removeEventListener("load", onload);
          onPage(win);
        }, { once: true });
      } catch (e) {}
    },
  };
  Services.obs.addObserver(observer, "content-document-global-created");
}
