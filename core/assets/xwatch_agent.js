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
/* ---- NHIP COMMENT (nguoi dung chot 06/10) ------------------------------------
 * Khong duoc comment don dap mot cho: luot ~30% thoi gian roi moi comment lan dau;
 * giua hai comment phai luot 3-4 bai (co tha tim / xem video xen vao); moi comment
 * mot BAI KHAC NHAU va khong gui lai noi dung da gui. */
var CMT_BAT_DAU_TI_LE = 0.30;    // comment dau tien: sau khi da luot 30% thoi gian
var CMT_CACH_BAI_MIN = 3;        // giua hai comment: it nhat 3 bai
var CMT_CACH_BAI_MAX = 4;        // ... toi da 4 bai
var CMT_XEM_VIDEO_GIAY = 5;      // bai co video thi xem ~5 giay roi moi vao comment
var CMT_MOI_CAI_GIAY = 45;       // uoc moi comment ton ~45s (de biet khi nao "sap het gio")

/** Giua hai comment thi phai luot bao nhieu bai (3-4, ngau nhien). THUAN. */
function xwCachBai(rnd) {
  return xwGiayDung(CMT_CACH_BAI_MIN, CMT_CACH_BAI_MAX, rnd);
}

/** Co nen COMMENT o bai nay khong. THUAN (de thuoc chay bang node).
 *  st = {daCmt, soComment, troiMs, hanMs, baiTuCmt, cachBai, daCmtBai}
 *    daCmt     so comment da gui          soComment  tong so can gui
 *    troiMs    da luot bao lau            hanMs      tong thoi gian cua luot
 *    baiTuCmt  so bai da luot ke tu comment gan nhat
 *    cachBai   lan nay can cach bao nhieu bai (xwCachBai)
 *    daCmtBai  bai nay da comment roi (true/false)
 */
function xwNenComment(st) {
  var can = (st.soComment || 0) - (st.daCmt || 0);
  if (can <= 0) { return false; }
  if (st.daCmtBai) { return false; }                       // moi bai chi comment MOT lan
  var con = Math.max(0, (st.hanMs || 0) - (st.troiMs || 0));
  if (con <= can * CMT_MOI_CAI_GIAY * 1000) { return true; }   // sap het gio -> thoi rai
  if (!st.daCmt) {                                          // comment DAU TIEN
    return st.troiMs >= st.hanMs * CMT_BAT_DAU_TI_LE;
  }
  return (st.baiTuCmt || 0) >= (st.cachBai || CMT_CACH_BAI_MIN);
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
/** ID bai (so sau /status/) trong mot link x.com / twitter.com; khong co -> "". THUAN. */
function xwIdStatus(url) {
  var m = String(url || "").match(/\/status(?:es)?\/(\d{5,})/);
  return m ? m[1] : "";
}
/** Muc "Trich dan" (Quote) trong menu nut Dang lai: chu Quote/Trich dan hoac link /compose/post.
 *  THUAN (nhan chu + href) de thuoc chay bang node. */
function xwLaMucQuote(chu, href) {
  return /compose\/post/.test(String(href || ""))
      || /^\s*(quote|trích dẫn|trich dan)\b/i.test(String(chu || ""));
}
/** Chu dung de trich dan: comment DAU TIEN neu co, khong thi CAPTION bai. THUAN.
 *  -> {nguon: "comment"|"caption"|"icon", chu}. */
/** DAU VAN TAY mot bai: "@kenh|60 ky tu dau cua chu" (thuong, gop khoang trang). Bai khong co
 *  chu -> "" (khong du de so). Dung so bai UNG VIEN voi bai GOC nhung trong cac bai trich dan
 *  tren trang ca nhan acc (phan nhung KHONG co link toi bai goc -> khong lay duoc ID). THUAN. */
function xwKyBai(handle, text) {
  var h = String(handle || "").replace(/^@/, "").trim().toLowerCase();
  var t = String(text || "").replace(/\s+/g, " ").trim().toLowerCase().slice(0, 60);
  return h && t.length >= 8 ? h + "|" + t : "";
}
function xwChonChuQuote(cmt, caption) {
  var c = String(cmt || "").replace(/\s+/g, " ").trim();
  if (c) { return { nguon: "comment", chu: c }; }
  var t = String(caption || "").replace(/\s+/g, " ").trim();
  if (t) { return { nguon: "caption", chu: t }; }
  return { nguon: "icon", chu: "" };
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { phanLoai: xwPhanLoai, chonChuQuote: xwChonChuQuote, giayDung: xwGiayDung, nenTim: xwNenTim,
                     idStatus: xwIdStatus, laMucQuote: xwLaMucQuote, kyBai: xwKyBai,
                     icons: xwIcons, soanComment: xwSoanComment, ICONS: XW_ICONS,
                     nenComment: xwNenComment, cachBai: xwCachBai,
                     CMT: { BAT_DAU_TI_LE: CMT_BAT_DAU_TI_LE, CACH_BAI_MIN: CMT_CACH_BAI_MIN,
                            CACH_BAI_MAX: CMT_CACH_BAI_MAX, XEM_VIDEO_GIAY: CMT_XEM_VIDEO_GIAY } };
}

if (typeof sendAsyncMessage === "function") {

  var lines = [];
  var dem = { xem: 0, like: 0, video: 0, cmt: 0, follow: 0, quote: 0 };
  // Ma rieng cua BAN agent nay (moi tien trinh noi dung mot ban) -> xin giay phep chay o cha.
  var TOK = "t" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  /** Xin quyen chay lenh: chi MOT ban agent (trong moi tien trinh noi dung) duoc chay. */
  function xinQuyen() {
    try {
      var a = sendSyncMessage("qlfpxw:claim", { tok: TOK });
      var kq = a && a.length ? a[0] : null;
      return !kq || kq.ok !== false;       // cha cu (chua co claim) -> cho chay nhu truoc
    } catch (e) { return true; }
  }
  function report(state, detail, extra) {
    lines.push(state + (detail ? ": " + detail : ""));
    var obj = { state: state, detail: detail || "", log: lines.slice(-30), tok: TOK,
                xem: dem.xem, like: dem.like, video: dem.video, cmt: dem.cmt,
                follow: dem.follow, quote: dem.quote };
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
      // MOT click duy nhat (clickReal da ban su kien click). Truoc day them n2.click() "du phong"
      // = HAI click: nut cong tac (Follow/tim/xem video) bat roi tat lai, nut Tra loi gui HAI lan
      // (nguoi dung bao 10/10: comment trung cach 1 giay, follow 2 lan thanh mat follow).
      xong(clickReal(win, n2));
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
    // Trang soan rieng /compose/post: nut Dang la tweetButton (Inline la cua composer khac).
    var ten = !dlg && laTrangSoan(doc)
      ? ['[data-testid="tweetButton"]', '[data-testid="tweetButtonInline"]']
      : ['[data-testid="tweetButtonInline"]', '[data-testid="tweetButton"]'];
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
  function lamComment(win, doc, bai, xong, thu, daChu) {
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
          // KHONG gui lai noi dung da gui o bai truoc (nguoi dung 06/10: "lay 1 comment
          // dang lai 5 lan"). So theo PHAN CHU, bo icon (icon moi lan mot khac).
          var khoaChu = String(c.chu).replace(/\s+/g, " ").trim().toLowerCase().slice(0, 80);
          if (daChu && khoaChu && daChu[khoaChu]) {
            veHome(win, doc, function () {
              xong(false, "bo qua: comment nay da dang o bai truoc (\"" + khoaChu.slice(0, 40) + "\")");
            });
            return;
          }
          if (daChu && khoaChu) { daChu[khoaChu] = 1; }
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
            // BAM MOT LAN. Truoc day clickReal + n.click() = HAI click -> comment gui HAI lan
            // cach nhau 1 giay (anh nguoi dung 10/10).
            var conChu = function () {
              var ox = oSoanReply(doc);
              return !!ox && txt(ox).replace(/\s+/g, " ").trim().indexOf(noi.slice(0, 14)) >= 0;
            };
            // Nut Tra loi CHI nhan click GOC cua trinh duyet (do that 10/10: click gia lap
            // clickReal khong gui, 5/5 lan) -> bam bang n.click() MOT lan.
            withUserInput(win, function () { try { n.click(); } catch (e) {} });
            cho(win, function () { return !conChu(); }, 6000, function (sach1) {
              if (sach1) { xong(true, "go " + (cach || "?") + ", lan " + lanGo); return; }
              // 6 giay ma o soan VAN NGUYEN CHU = cu bam dau CHAC CHAN khong an (X xoa o soan
              // ngay khi gui) -> bam bu MOT lan bang cach khac.
              var n2 = nutGuiReply(doc);
              report("progress", "comment: cu bam dau khong an (nut " + (n2 ? (n2.getAttribute("aria-disabled") === "true" ? "khoa" : "bat") : "mat")
                     + ") — bam bu 1 lan");
              if (n2 && conChu()) { clickReal(win, n2); }
              cho(win, function () { return !conChu(); }, 14000, function (sach) {
                if (sach) { xong(true, "go " + (cach || "?") + ", lan " + lanGo + " (bam bu)"); return; }
                xong(false, "bam Tra loi roi ma chu van con trong o soan");
              });
            });
          });
        }, 1400);
        });
      })();
    });
  }

  /* ---- di chuyen trong SPA (KHONG dat location.href: se huy agent) ------------- */
  /** Bam the <a href="..."> trong trang (X router xu ly -> KHONG tai lai tai lieu). */
  function bamLink(win, doc, href) {
    var ds = Array.prototype.slice.call(doc.querySelectorAll('a[href="' + href + '"]'));
    for (var i = 0; i < ds.length; i++) {
      if (vis(ds[i])) { clickReal(win, ds[i]); return true; }
    }
    return false;
  }

  function oTimKiem(doc) {
    var o = doc.querySelector('input[data-testid="SearchBox_Search_Input"]')
         || doc.querySelector('input[enterkeyhint="search"]')
         || doc.querySelector('input[type="text"][role="combobox"]');
    return o && vis(o) ? o : null;
  }

  /** Go tu khoa vao o tim kiem roi MO ket qua. Tra ve qua ``xong(ok)``.
   *  TUYET DOI khong ban su kien PHIM vao o nay: o tim cua X la role="combobox", ban don
   *  keydown/keypress/keyup lam CHET TAB (da do that 06/10 — "Gah. Your tab just crashed.").
   *  Thay vao do: go bang native setter + input, roi BAM goi y <a href="/search?q=..."> (SPA). */
  function goTimKiem(win, doc, tu, xong) {
    var o = oTimKiem(doc);
    if (!o) { xong(false); return; }
    withUserInput(win, function () {
      try {
        o.focus();
        var set = Object.getOwnPropertyDescriptor(win.HTMLInputElement.prototype, "value").set;
        set.call(o, tu);
        o.dispatchEvent(new win.Event("input", { bubbles: true }));
      } catch (e) {}
    });
    // Cho X do goi y roi bam dong "/search?q=..." (hoac submit form) — KHONG dung phim.
    cho(win, function () { return !!doc.querySelector('a[href^="/search?q="]'); }, 6000,
        function (coGoiY) {
          if (coGoiY) {
            var a = doc.querySelector('a[href^="/search?q="]');
            if (a && vis(a)) { clickReal(win, a); xong(true); return; }
          }
          var form = o.closest ? o.closest("form") : null;
          if (form && form.requestSubmit) {
            withUserInput(win, function () { try { form.requestSubmit(); } catch (e) {} });
            xong(true);
            return;
          }
          xong(false);
        });
  }

  /* ---- FOLLOW kenh + TIM KIEM theo tu khoa ------------------------------------ */
  //: Nut Follow that cua X mang data-testid "<id>-follow"; follow xong doi thanh "<id>-unfollow"
  //: -> do bang testid moi CHAC, khong do theo chu (acc doi ngon ngu la hong).
  var FOLLOW_CHU = /^(follow|theo dõi|theo doi)$/i;

  function nutFollow(goc) {
    var ds = Array.prototype.slice.call(goc.querySelectorAll('[data-testid$="-follow"]'));
    for (var i = 0; i < ds.length; i++) {
      if (vis(ds[i]) && FOLLOW_CHU.test(txt(ds[i]))) { return ds[i]; }
    }
    return null;
  }

  function daFollowRoi(goc, tid) {
    try {
      if (goc.querySelector('[data-testid="' + tid.replace(/-follow$/, "-unfollow") + '"]')) { return true; }
      // Mot so cho X khong doi testid ma chi doi CHU ("Following"/"Dang theo doi") -> nut
      // "-follow" bien mat hoac khong con chu Follow cung la DA FOLLOW.
      var n = goc.querySelector('[data-testid="' + tid + '"]');
      return !n || !FOLLOW_CHU.test(txt(n));
    } catch (e) { return false; }
  }

  /** Ten tai khoan TAC GIA cua trang bai dang mo: x.com/<handle>/status/<id>. */
  function tacGiaBai(win) {
    var m = /^\/([^\/?#]+)\/status\//.exec(String((win.location && win.location.pathname) || ""));
    return m ? m[1].toLowerCase() : "";
  }

  /** Trang thai follow cua TAC GIA bai (trong khung "Relevant people"/UserCell co link toi
   *  /<handle>): {nut: nut Follow neu CHUA follow, da: true neu DA follow (nut "-unfollow" /
   *  chu Following), thay: co tim ra o cua tac gia khong}. KHONG lay "nut Follow dau tien" tren
   *  trang nua — co the la nguoi khac o muc goi y. */
  function followTacGia(doc, handle) {
    var kq = { nut: null, da: false, thay: false };
    if (!handle) { return kq; }
    var o = [];
    try { o = Array.prototype.slice.call(doc.querySelectorAll('[data-testid="UserCell"]')); } catch (e) {}
    for (var i = 0; i < o.length; i++) {
      var links = o[i].querySelectorAll('a[href]'), cua = false;
      for (var j = 0; j < links.length; j++) {
        var h = String(links[j].getAttribute("href") || "").toLowerCase();
        if (h === "/" + handle) { cua = true; break; }
      }
      if (!cua) { continue; }
      kq.thay = true;
      if (o[i].querySelector('[data-testid$="-unfollow"]')) { kq.da = true; return kq; }
      var f = o[i].querySelector('[data-testid$="-follow"]');
      if (f && FOLLOW_CHU.test(txt(f))) { kq.nut = f; return kq; }
      if (f) { kq.da = true; return kq; }               // nut con nhung chu khac Follow = da follow
    }
    return kq;
  }

  /** Link ten TAC GIA trong bai goc (vung User-Name) -> bam de sang trang ca nhan. */
  function linkTacGia(doc, handle) {
    if (!handle) { return null; }
    var ds = [];
    try { ds = doc.querySelectorAll('article[data-testid="tweet"] [data-testid="User-Name"] a[href]'); } catch (e) {}
    for (var i = 0; i < ds.length; i++) {
      if (String(ds[i].getAttribute("href") || "").toLowerCase() === "/" + handle && vis(ds[i])) { return ds[i]; }
    }
    return null;
  }

  /** Trang thai follow tren TRANG CA NHAN: nut chinh nam trong [data-testid="placementTracking"]
   *  (KHONG lay nut "-follow" cua muc goi y ben canh). Cung dang {nut, da, thay} nhu followTacGia. */
  function followTrenProfile(doc) {
    var kq = { nut: null, da: false, thay: false, goc: null };
    var goc = null;
    try { goc = doc.querySelector('[data-testid="placementTracking"]'); } catch (e) {}
    if (!goc) { return kq; }
    kq.goc = goc;
    if (goc.querySelector('[data-testid$="-unfollow"]')) { kq.thay = true; kq.da = true; return kq; }
    var f = goc.querySelector('[data-testid$="-follow"]');
    if (f) {
      kq.thay = true;
      if (FOLLOW_CHU.test(txt(f))) { kq.nut = f; } else { kq.da = true; }
    }
    return kq;
  }

  /** Bam nut Follow ``nut`` (hoac nut Follow dau tien trong ``goc``) MOT LAN; XAC MINH doi sang
   *  "-unfollow". Truoc khi bam / bam bu deu KIEM LAI: da follow roi thi KHONG bam (bam nua la
   *  BO FOLLOW — loi nguoi dung bao 10/10). */
  function bamFollow(win, goc, xong, nutChon) {
    var nut = nutChon || nutFollow(goc);
    if (!nut) { xong(false, "khong thay nut Follow"); return; }
    var tid = nut.getAttribute("data-testid") || "";
    if (daFollowRoi(goc, tid)) { xong(false, "da follow tu truoc — bo qua"); return; }
    // GHIM theo dung testid: hoverRoiBamLay co lay lai phan tu, ma sau cu bam dau "nut Follow
    // dau tien" co the da la nut CUA NGUOI KHAC -> xac minh truot (do that 06/10).
    var lay = function () {
      try { return goc.querySelector('[data-testid="' + tid + '"]'); } catch (e) { return null; }
    };
    // CUON nut vao tam nhin truoc: nut Follow o thanh ben phai co the nam ngoai man hinh ->
    // bam tong hop khong an (do that 06/10: bam o trang bai truot, cung acc do follow duoc o trang goi y).
    try { withUserInput(win, function () { nut.scrollIntoView({ block: "center" }); }); } catch (e) {}
    hoverRoiBamLay(win, lay, function (ok) {
      if (!ok) { xong(false, "bam Follow khong an"); return; }
      cho(win, function () { return daFollowRoi(goc, tid); }, 6000, function (doi) {
        if (doi) { dem.follow += 1; xong(true, "da follow " + tid.replace(/-follow$/, "")); return; }
        // 6 giay chua doi: CHI bam bu khi nut VAN la "Follow" (chua follow that) — kiem lai ngay
        // truoc khi bam, khong thi bam la thanh bo follow.
        var n2 = lay();
        if (!n2 || !FOLLOW_CHU.test(txt(n2)) || daFollowRoi(goc, tid)) {
          var da = daFollowRoi(goc, tid);
          if (da) { dem.follow += 1; }
          xong(da, (da ? "da follow (doi cham) " : "nut Follow bien mat, khong ro: ") + tid.replace(/-follow$/, ""));
          return;
        }
        report("progress", "follow: cu bam dau khong an — bam bu 1 lan");
        clickReal(win, n2);
        cho(win, function () { return daFollowRoi(goc, tid); }, 8000, function (doi2) {
          if (doi2) { dem.follow += 1; }
          xong(!!doi2, (doi2 ? "da follow (bam bu) " : "bam roi nhung chua doi sang Following: ")
               + tid.replace(/-follow$/, ""));
        });
      });
    });
  }

  /** Follow ``can`` kenh o trang goi y (x.com/i/connect_people). */
  function chayFollow(win, doc, can, hetGio, xong) {
    if (can <= 0) { xong(); return; }
    report("progress", "sang trang goi y de follow " + can + " kenh");
    if (!bamLink(win, doc, "/i/connect_people")) {
      report("progress", "khong thay muc 'Follow' o thanh ben — bo qua pha follow");
      xong(); return;
    }
    cho(win, function () { return !!nutFollow(doc); }, 15000, function (co) {
      if (!co) { report("progress", "trang goi y khong co nut Follow nao"); xong(); return; }
      (function ke() {
        if (dem.follow >= can || hetGio()) { xong(); return; }
        if (!nutFollow(doc)) {
          try { withUserInput(win, function () { win.scrollBy({ top: 600, left: 0, behavior: "auto" }); }); }
          catch (e) {}
          win.setTimeout(function () { nutFollow(doc) ? ke() : xong(); }, 1500);
          return;
        }
        bamFollow(win, doc, function (ok, mo) {
          report("progress", "follow " + dem.follow + "/" + can + " — " + mo);
          win.setTimeout(ke, ok ? 1500 : 800);
        });
      })();
    });
  }

  /** Tim kiem tung tu khoa -> mo ``soBai`` bai -> follow kenh cua bai do -> quay lai. */
  function chayTimKiem(win, doc, dsTu, soBai, hetGio, xong) {
    if (!dsTu.length || soBai <= 0) { xong(); return; }
    var k = 0;
    (function tuKe() {
      if (k >= dsTu.length || hetGio()) { xong(); return; }
      var tu = dsTu[k++];
      report("progress", "tim kiem: " + tu);
      // Phai go vao O TIM (SPA). Chua thay o tim -> sang /explore truoc.
      (function moOTim(lan) {
        if (oTimKiem(doc)) { goRoiCho(); return; }
        if (lan > 2) { report("progress", "khong thay o tim kiem"); win.setTimeout(tuKe, 800); return; }
        bamLink(win, doc, "/explore");
        cho(win, function () { return !!oTimKiem(doc); }, 8000, function () {
          win.setTimeout(function () { moOTim(lan + 1); }, 600);
        });
      })(0);

      function goRoiCho() {
      goTimKiem(win, doc, tu, function (goOk) {
      if (!goOk) { report("progress", "khong go duoc tu khoa"); win.setTimeout(tuKe, 800); return; }
      cho(win, function () { return /\/search\b/.test(String(win.location.href || ""))
                                    && dsBai(doc).length > 0; }, 15000, function (co) {
        if (!co) { report("progress", "tim '" + tu + "' khong ra bai nao"); win.setTimeout(tuKe, 800); return; }
        var daMo = 0, daLink = {};
        (function baiKe() {
          if (daMo >= soBai || hetGio()) { win.setTimeout(tuKe, 600); return; }
          // Dang o trang KET QUA thi moi chon bai; o trang bai thi quay ve truoc.
          if (!/\/search\b/.test(String(win.location.href || ""))) {
            try { win.history.back(); } catch (e) {}
            // Tu trang ca nhan phai lui HAI buoc (ca nhan -> bai -> ket qua): cho ngan roi lui tiep.
            cho(win, function () { return /\/search\b/.test(String(win.location.href || "")); },
                4000, function () { win.setTimeout(baiKe, 700); });
            return;
          }
          var ds = dsBai(doc), lk = null;
          for (var i = 0; i < ds.length; i++) {
            var a = linkBai(ds[i]);
            if (a && !daLink[a.getAttribute("href") || ""]) { lk = a; break; }
          }
          if (!lk) {
            try { withUserInput(win, function () { win.scrollBy({ top: 700, left: 0, behavior: "auto" }); }); }
            catch (e) {}
            win.setTimeout(function () { daMo += 0.0001; baiKe(); }, 1200);   // cuon roi thu lai
            return;
          }
          daLink[lk.getAttribute("href") || ""] = 1;
          var truoc = String(win.location.href || "");
          clickReal(win, lk);
          cho(win, function () { return String(win.location.href || "") !== truoc; }, 9000, function (doi) {
            if (!doi) { win.setTimeout(baiKe, 800); return; }
            daMo += 1;
            report("progress", "mo bai " + Math.floor(daMo) + "/" + soBai + " cua '" + tu + "'");
            // CHO khung "Relevant people" dung xong moi bam: bam ngay sau khi chuyen trang SPA
            // thi nut chua hydrate -> bam truot / khong thay nut (do that 06/10, 2 lan).
            // Xac dinh dung TAC GIA bai roi moi xet: DA follow -> bo qua, sang bai ke;
            // CHUA follow -> bam MOT lan. Cho o cua tac gia hien (khung hydrate muon).
            var tg = tacGiaBai(win);
            function xuLy(tt, noi) {
              if (tt.da) {
                report("progress", "@" + tg + " DA follow tu truoc (" + noi + ") — bo qua, sang bai ke");
                win.setTimeout(baiKe, 1000);
                return;
              }
              if (!tt.nut) {
                report("progress", "khong thay nut Follow cua tac gia @" + (tg || "?") + " (" + noi + ") — sang bai ke");
                win.setTimeout(baiKe, 1000);
                return;
              }
              // Xac minh theo MA NUT (<id>-follow, duy nhat) tren CA TRANG: khung nut co the bi X ve
              // lai sau khi bam -> tham chieu khung cu mo coi, doc sai trang thai.
              bamFollow(win, doc, function (ok, mo) {
                report("progress", "follow @" + tg + " (" + noi + "): " + mo);
                win.setTimeout(baiKe, 1200);
              }, tt.nut);
            }
            cho(win, function () { return followTacGia(doc, tg).thay; }, 5000, function (coKhung) {
              if (coKhung) { xuLy(followTacGia(doc, tg), "khung Relevant people"); return; }
              // Cua so HEP (xep 3 cot) -> X AN khung "Relevant people" -> sang TRANG CA NHAN tac gia.
              var lt = linkTacGia(doc, tg);
              if (!lt) { xuLy({ nut: null, da: false }, "khong co link tac gia"); return; }
              clickReal(win, lt);
              cho(win, function () {
                return String((win.location && win.location.pathname) || "").toLowerCase() === "/" + tg
                       && followTrenProfile(doc).thay;
              }, 10000, function () {
                var tp = followTrenProfile(doc);
                xuLy(tp, "trang ca nhan");
              });
            });
          });
        })();
      });
      });
      }
    })();
  }

  /* ---- vong tuong tac -------------------------------------------------------- */
  var DANG_CHAY = false;
  function chayTuongTac(win, doc, cmd, xongCb) {
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
    // Nhip COMMENT: moi bai chi comment mot lan, khong gui trung noi dung, va phai
    // luot xen ke (xem muc CMT_* o dau file).
    var daCmtBai = {};       // id bai DA comment
    var daCmtChu = {};       // noi dung comment DA gui (chuan hoa) -> khong gui lai
    var baiTuCmt = 0;        // so bai da luot ke tu comment gan nhat
    var cachBai = xwCachBai();

    var soFollow = parseInt(cmd.so_follow || 0, 10) || 0;
    var soBaiTim = parseInt(cmd.so_bai_tim || 0, 10) || 0;
    var dsTuKhoa = [];
    try {
      dsTuKhoa = (cmd.tu_khoa || []).map(function (t) { return String(t || "").trim(); })
                                    .filter(function (t) { return t; });
    } catch (e) { dsTuKhoa = []; }

    report("on-home", "bat dau: " + soLike + " tim, " + soVideo + " video, "
           + soComment + " comment, " + soFollow + " follow, "
           + dsTuKhoa.length + " tu khoa x " + soBaiTim + " bai, "
           + Math.round(han / 1000) + "s, dung " + dungMin + "-" + dungMax + "s/bai");

    function conGiay() { return Math.max(0, Math.round((han - (Date.now() - batDau)) / 1000)); }

    function xong(vi) {
      var moTa = "xong: xem " + dem.xem + " bai, tim " + dem.like + "/" + soLike
             + ", video " + dem.video + "/" + soVideo + ", comment " + dem.cmt + "/" + soComment
             + ", follow " + dem.follow + "/" + soFollow
             + (vi ? " (" + vi + ")" : "");
      if (typeof xongCb === "function") { xongCb(moTa); return; }   // chay trong KICH BAN (buoc "luot")
      report("done", moTa);
    }
    function hetGio() { return Date.now() - batDau >= han; }

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
          // Nhip do xwNenComment quyet dinh: luot ~30% thoi gian moi comment lan dau, giua hai
          // lan phai luot 3-4 bai, moi bai mot lan. Truoc day chi kiem "con thieu comment" nen
          // bai nao cung comment lien tay -> nguoi dung thay "lay 1 comment dang lai 5 lan".
          var nen = Date.now() - batDau < han && !!linkBai(bai) && xwNenComment({
            daCmt: dem.cmt, soComment: soComment, troiMs: Date.now() - batDau, hanMs: han,
            baiTuCmt: baiTuCmt, cachBai: cachBai, daCmtBai: !!(maBai && daCmtBai[maBai])
          });
          if (!nen) { baiTuCmt += 1; baoRoiDoi(); return; }

          function vaoComment() {
            report("progress", "bai " + dem.xem + ": vao bai lay comment dau tien... (comment "
                   + dem.cmt + "/" + soComment + ", da luot " + baiTuCmt + " bai tu lan truoc)");
            if (maBai) { daCmtBai[maBai] = 1; }   // danh dau TRUOC: hong cung khong lam lai bai nay
            lamComment(win, doc, bai, function (ok, mo) {
              if (ok) { dem.cmt += 1; }
              baiTuCmt = 0;
              cachBai = xwCachBai();              // lan sau cach 3-4 bai (ngau nhien lai)
              viec.push(mo || (ok ? "comment" : "comment hong"));
              baoRoiDoi();
            }, !!cmd.thu, daCmtChu);
          }

          // Bai co VIDEO -> bam xem ~5 giay roi moi vao comment (nguoi that xem roi moi binh luan).
          var nvc = coVideo(bai) ? nutXemVideo(bai) : null;
          if (!nvc) { vaoComment(); return; }
          if (clickReal(win, nvc)) {
            viec.push("xem video " + CMT_XEM_VIDEO_GIAY + "s truoc khi comment");
          }
          win.setTimeout(vaoComment, CMT_XEM_VIDEO_GIAY * 1000);
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

    // THU TU: tim kiem theo tu khoa (mo bai + follow kenh cua bai) -> follow them o trang goi y
    // -> con gio thi luot /home nhu cu. Moi pha deu bi chan boi gioi han giay.
    win.setTimeout(function () {
      chayTimKiem(win, doc, dsTuKhoa, soBaiTim, hetGio, function () {
        chayFollow(win, doc, soFollow, hetGio, function () {
          if (hetGio()) { xong("het gio sau follow/tim kiem"); return; }
          veHome(win, doc, function () { win.setTimeout(motBai, 1200); });
        });
      });
    }, 1500);
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

  /* ---- DANG LAI TRICH DAN (Quote) — lenh action "xquote" ---------------------
   * Driver (core/xwatch.dang_lai_trich_dan) dieu khien tung BUOC qua lenh co "idx" tang dan:
   *   buoc "gom"   : url = trang kenh (https://x.com/<handle>) hoac /home -> gom toi da ``so``
   *                  link bai -> report "quote-links" {idx, links}.
   *   buoc "quote" : url = link bai -> lay comment DAU TIEN + 3-5 icon -> bam Dang lai >
   *                  Trich dan -> go chu -> Dang -> report "quote-done" / "quote-fail" {idx}.
   * Xong moi buoc agent NGOI CHO lenh moi (idx khac) roi tu chuyen trang toi url cua lenh do
   * (doi trang = tai lai tai lieu -> agent moi chay lai onPage voi lenh moi). */
  var QUOTE_LAM = {};       // "idx|url" da lam trong tien trinh nay (chong chay lai)
  var QUOTE_DI = {};        // idx -> luc da dieu huong (chong dieu huong lap)
  function laQuangCao(bai) {
    var t = "";
    try { t = bai.innerText || ""; } catch (e) { t = ""; }
    return /(^|\n)\s*(Ad|Promoted|Quảng cáo)\s*(\n|$)/.test(t);
  }
  function coNguCanh(bai) {       // "Pinned" / "X reposted" -> khong phai bai goc cua kenh
    try { return !!bai.querySelector('[data-testid="socialContext"]'); } catch (e) { return false; }
  }
  function hrefBai(bai) {
    var l = linkBai(bai);
    return l ? String(l.getAttribute("href") || "").split("?")[0] : "";
  }
  function baiGoc(doc, href) {
    var els;
    try { els = doc.querySelectorAll('article[data-testid="tweet"]'); } catch (e) { return null; }
    var ma = xwIdStatus(href), khongId = null;
    for (var i = 0; i < els.length; i++) {
      if (ma && idBai(els[i]) === ma) { return els[i]; }
      if (!idBai(els[i]) && !khongId) { khongId = els[i]; }   // bai goc hien ngay thang
    }
    return khongId || null;
  }
  function nutDangLai(bai) {
    return bai ? (nutTrongBai(bai, "retweet") || nutTrongBai(bai, "unretweet")) : null;
  }
  function mucQuote(doc) {
    var ds;
    try { ds = doc.querySelectorAll('[role="menuitem"]'); } catch (e) { return null; }
    for (var i = 0; i < ds.length; i++) {
      if (vis(ds[i]) && xwLaMucQuote(txt(ds[i]), ds[i].getAttribute("href"))) { return ds[i]; }
    }
    return null;
  }
  /** Dang o TRANG SOAN rieng x.com/compose/post (khong co hop thoai). */
  function laTrangSoan(doc) {
    try { return /\/compose\/post/.test(String(doc.location.href || "")); } catch (e) { return false; }
  }
  /** Khung soan trich dan. Cua so RONG: X mo HOP THOAI noi tren trang bai. Cua so HEP (xep 3
   *  cot): X mo TRANG RIENG x.com/compose/post, KHONG co role=dialog (nguoi dung bao 14/10:
   *  dung o trang do rat lau roi tu chuyen trang, khong bam Post). */
  function hopQuote(doc) {
    var d = hopThoai(doc);
    try {
      if (d && d.querySelector('[data-testid="tweetTextarea_0"]')) { return d; }
      if (laTrangSoan(doc) && oSoanReply(doc)) { return doc.body; }
    } catch (e) {}
    return null;
  }
  /** Xong mot buoc: ngoi cho lenh MOI (idx khac) roi chuyen trang toi url cua no. */
  function theoDoiLenh(win, cmd) {
    var het = Date.now() + 20 * 60 * 1000;
    (function nhip() {
      if (Date.now() > het) { return; }
      var c2 = getCommand();
      if (c2 && c2.action === "xquote" && c2.idx !== cmd.idx && c2.url) {
        QUOTE_DI[c2.idx] = Date.now();
        try { win.location.href = c2.url; } catch (e) {}
        return;
      }
      win.setTimeout(nhip, 1500);
    })();
  }
  /** Che do thu: dong hop trich dan (Close -> Discard) de chuyen trang khong bi hoi. */
  function dongHopQuote(win, doc, xong) {
    var n = null;
    try {
      n = doc.querySelector('[role="dialog"] [data-testid="app-bar-close"]')
          || doc.querySelector('[data-testid="app-bar-close"], [data-testid="app-bar-back"]');
    } catch (e) {}
    if (n) { clickReal(win, n); }
    cho(win, function () { return !!doc.querySelector('[data-testid="confirmationSheetConfirm"]'); },
        3000, function (co) {
          if (co) { clickReal(win, doc.querySelector('[data-testid="confirmationSheetConfirm"]')); }
          win.setTimeout(xong, 800);
        });
  }
  /** Buoc "gom": cuon trang kenh / newfeed, gom link bai (bo quang cao; trang kenh bo bai
   *  ghim / bai dang lai cua nguoi khac — chi lay bai GOC cua kenh). */
  function gomBai(win, doc, cmd) {
    var can = Math.max(1, parseInt(cmd.so, 10) || 1);
    var handle = String(cmd.handle || "").replace(/^@/, "").toLowerCase();
    var ds = [], dsKy = [], da = {}, boKy = {}, lanCuon = 0, batDau = Date.now(), boKyDem = 0;
    (cmd.bo_qua || []).forEach(function (id) { da[String(id)] = 1; });
    (cmd.bo_ky || []).forEach(function (k) { if (k) { boKy[String(k)] = 1; } });
    cho(win, function () { return dsBai(doc).length > 0; }, 20000, function (co) {
      if (!co) {
        report("quote-links", "khong thay bai nao o " + String(win.location.href).slice(0, 90)
               + (handle ? " (kenh khong ton tai / bi khoa / chua co bai?)" : ""),
               { idx: cmd.idx, links: [] });
        theoDoiLenh(win, cmd);
        return;
      }
      (function quet() {
        var els = dsBai(doc);
        for (var i = 0; i < els.length; i++) {
          var b = els[i], h = hrefBai(b), id = xwIdStatus(h);
          if (!id || da[id] || laQuangCao(b)) { continue; }
          if (handle) {
            if (coNguCanh(b)) { continue; }
            if (h.toLowerCase().indexOf("/" + handle + "/status/") !== 0) { continue; }
          }
          da[id] = 1;
          var ky = xwKyBai(h.split("/")[1], chuChinh(b));
          if (ky && boKy[ky]) { boKyDem += 1; continue; }   // acc DA trich dan bai nay (tren trang ca nhan)
          ds.push("https://x.com" + h);
          dsKy.push(ky);
        }
        if (ds.length >= can || lanCuon >= 25 || Date.now() - batDau > 120000) {
          report("quote-links", "gom " + Math.min(ds.length, can) + "/" + can + " bai sau " + lanCuon + " lan cuon"
                 + (boKyDem ? " (bo " + boKyDem + " bai acc da trich dan)" : ""),
                 { idx: cmd.idx, links: ds.slice(0, can), ky: dsKy.slice(0, can), bo_ky_dem: boKyDem });
          theoDoiLenh(win, cmd);
          return;
        }
        lanCuon += 1;
        try {
          withUserInput(win, function () {
            win.scrollBy({ top: 650, left: 0, behavior: "auto" });
            doc.dispatchEvent(new win.WheelEvent("wheel", { bubbles: true, deltaY: 650 }));
          });
        } catch (e) {}
        win.setTimeout(quet, 1400 + Math.floor(Math.random() * 1200));
      })();
    });
  }
  /** Buoc "quote": tren trang bai viet — comment dau tien + icon -> Dang lai > Trich dan. */
  function lamQuote(win, doc, cmd) {
    var href = String(win.location.href || "");
    function ket(ok, vi) {
      if (ok && !cmd.thu) { dem.quote += 1; }
      report(ok ? "quote-done" : "quote-fail", vi, { idx: cmd.idx, ok: !!ok });
      theoDoiLenh(win, cmd);
    }
    cho(win, function () { return !!baiGoc(doc, href); }, 20000, function (coBai) {
      if (!coBai) { ket(false, "khong mo duoc bai (bai bi xoa / an?)"); return; }
      // Acc DA trich dan bai nay (dau van tay khop trang ca nhan) -> KHONG trich dan lai.
      var kyGoc = xwKyBai(tacGiaBai(win), chuChinh(baiGoc(doc, href)));
      if (kyGoc && (cmd.bo_ky || []).indexOf(kyGoc) >= 0) {
        report("quote-trung", "acc DA trich dan bai nay (thay tren trang ca nhan) — bo qua",
               { idx: cmd.idx, ok: false });
        theoDoiLenh(win, cmd);
        return;
      }
      cho(win, function () { return !!commentDau(doc, href); }, 8000, function (co) {
        if (!co) {
          try { withUserInput(win, function () { win.scrollBy({ top: 600, left: 0, behavior: "auto" }); }); } catch (e) {}
        }
        cho(win, function () { return !!commentDau(doc, href); }, co ? 1 : 5000, function () {
          // Nguoi dung 14/10: CO comment -> lay comment DAU TIEN; KHONG co -> lay CAPTION bai;
          // bai khong co chu (chi video/anh) -> chi 3-5 icon.
          var c = commentDau(doc, href);
          var chon = xwChonChuQuote(c ? c.chu : "", chuBai(baiGoc(doc, href)));
          var icon = xwIcons();
          var noi = chon.chu ? xwSoanComment(chon.chu, icon) : icon;
          c = { chu: (chon.nguon === "comment" ? "comment dau: " : chon.nguon === "caption"
                      ? "caption bai: " : "chi icon") + chon.chu };
          try { withUserInput(win, function () { win.scrollTo({ top: 0, left: 0, behavior: "auto" }); }); } catch (e) {}
          win.setTimeout(function () {
            if (!nutDangLai(baiGoc(doc, href))) { ket(false, "khong thay nut Dang lai cua bai"); return; }
            hoverRoiBamLay(win, function () { return nutDangLai(baiGoc(doc, href)); }, function () {
              cho(win, function () { return !!mucQuote(doc); }, 4000, function (coMenu) {
                if (!coMenu) {          // click gia lap khong mo menu -> click GOC mot lan
                  var n = nutDangLai(baiGoc(doc, href));
                  if (n) { withUserInput(win, function () { try { n.click(); } catch (e) {} }); }
                }
                cho(win, function () { return !!mucQuote(doc); }, coMenu ? 1 : 4000, function () {
                  var muc = mucQuote(doc);
                  if (!muc) { ket(false, "menu Dang lai khong co muc Trich dan (Quote)"); return; }
                  clickReal(win, muc);
                  cho(win, function () { return !!hopQuote(doc); }, 8000, function (coHop) {
                    if (!coHop) {
                      var m2 = mucQuote(doc);
                      if (m2) { withUserInput(win, function () { try { m2.click(); } catch (e) {} }); }
                    }
                    cho(win, function () { return !!hopQuote(doc); }, coHop ? 1 : 8000, function (co2) {
                      if (!co2) { ket(false, "bam Trich dan nhung khong mo duoc hop soan"); return; }
                      report("progress", "trich dan [" + (hopThoai(doc) ? "hop thoai" : "trang /compose/post") + "]: " + c.chu.slice(0, 70),
                             { idx: cmd.idx });
                      guiComment(win, doc, noi, function (ok, vi) {
                        var laThu = cmd.thu && /CHE DO THU/.test(vi || "");
                        var moTa = (ok ? 'da trich dan "' : laThu ? 'CHAY THU (khong bam Dang) "'
                                    : 'KHONG trich dan duoc "') + noi.slice(0, 70)
                                   + '"' + (vi ? " (" + vi + ")" : "");
                        if (cmd.thu) {
                          dongHopQuote(win, doc, function () { ket(/CHE DO THU/.test(vi || ""), moTa); });
                          return;
                        }
                        ket(ok, moTa);
                      }, cmd.thu);
                    });
                  });
                });
              });
            });
          }, 900);
        });
      });
    });
  }
  /** Buoc "follow": dang o trang kenh -> chua follow thi bam Follow (bamFollow xac minh doi sang
   *  Following), DA follow thi BO QUA (bam nua la BO follow). report "quote-follow" {kq}. */
  function lamFollowKenh(win, doc, cmd) {
    function ket(kq, vi) {
      report("quote-follow", vi, { idx: cmd.idx, kq: kq, ok: kq !== "loi" });
      theoDoiLenh(win, cmd);
    }
    cho(win, function () { return followTrenProfile(doc).thay; }, 15000, function (co) {
      var f = followTrenProfile(doc);
      if (!co || !f.thay) { ket("loi", "khong thay nut Follow cua kenh @" + cmd.handle + " (kenh khong ton tai / bi khoa?)"); return; }
      if (f.da) { ket("da_follow", "@" + cmd.handle + ": DA follow tu truoc — bo qua"); return; }
      if (cmd.thu) { ket("thu", "@" + cmd.handle + ": CHUA follow (che do thu, khong bam)"); return; }
      bamFollow(win, f.goc, function (ok, mo) {
        if (ok) { ket("follow", "@" + cmd.handle + ": " + mo); return; }
        ket(/da follow tu truoc/.test(mo || "") ? "da_follow" : "loi", "@" + cmd.handle + ": " + mo);
      }, f.nut);
    });
  }
  /** Chu CHINH cua bai: doan tweetText dau tien KHONG nam trong phan nhung bai khac. */
  function chuChinh(bai) {
    try {
      var ds = bai.querySelectorAll('[data-testid="tweetText"]');
      for (var i = 0; i < ds.length; i++) {
        if (!ds[i].closest('div[role="link"]')) { return txt(ds[i]); }
      }
    } catch (e) {}
    return "";
  }
  /** Phan NHUNG bai goc trong mot bai trich dan -> {handle, text} | null. */
  function baiNhung(bai) {
    try {
      var ls = bai.querySelectorAll('div[role="link"]');
      for (var i = 0; i < ls.length; i++) {
        var un = ls[i].querySelector('[data-testid="User-Name"]');
        if (!un) { continue; }
        var m = txt(un).match(/@([A-Za-z0-9_]{1,15})/);
        var t = ls[i].querySelector('[data-testid="tweetText"]');
        if (m) { return { handle: m[1], text: t ? txt(t) : "" }; }
      }
    } catch (e) {}
    return null;
  }
  /** Buoc "lich": trang CA NHAN cua acc -> dau van tay (xwKyBai) cac bai GOC acc da trich dan
   *  (phan nhung khong co link nen khong lay duoc ID). Bat ca bai trich dan tu TRUOC khi co so
   *  lich su va bai trich dan tay. Cuon ``cmd.so`` lan. report "quote-lich" {ky}. */
  function docLichSu(win, doc, cmd) {
    var h = "/" + String(cmd.handle || "").replace(/^@/, "").toLowerCase();
    var ky = {}, lan = 0, toiDa = Math.max(1, parseInt(cmd.so, 10) || 8);
    function quetMot() {
      var els = dsBai(doc);
      for (var i = 0; i < els.length; i++) {
        var cua = String(hrefBai(els[i]) || "").toLowerCase().indexOf(h + "/status/") === 0;
        if (!cua) { continue; }                     // bai cua nguoi khac (dang lai) -> bo
        var n = baiNhung(els[i]);
        var k = n ? xwKyBai(n.handle, n.text) : "";
        if (k) { ky[k] = 1; }
      }
    }
    cho(win, function () { return dsBai(doc).length > 0; }, 15000, function (co) {
      (function quet() {
        quetMot();
        if (!co || lan >= toiDa) {
          var ds = Object.keys(ky);
          report("quote-lich", "trang ca nhan: " + ds.length + " bai goc da trich dan (doc " + lan + " lan cuon)",
                 { idx: cmd.idx, ky: ds });
          theoDoiLenh(win, cmd);
          return;
        }
        lan += 1;
        try { withUserInput(win, function () { win.scrollBy({ top: 900, left: 0, behavior: "auto" }); }); } catch (e) {}
        win.setTimeout(quet, 1300);
      })();
    });
  }
  /** KICH BAN: ba node chay tu /home trong CUNG phien trinh duyet (driver xwatch.chay_kich_ban).
   *   "luot" — luot newfeed (chayTuongTac: dung moi bai, tim, xem video, comment; het gio_han giay);
   *   "tim"  — tim theo tu khoa, mo ``so_bai`` bai moi tu khoa, follow TAC GIA; dung khi du ``can``;
   *   "goiy" — follow o trang goi y toi khi du ``can``.
   *  report "quote-node" {node, xem, like, video, cmt, follow} roi ngoi cho lenh ke. */
  function lamNodeHome(win, doc, cmd) {
    var han = (parseInt(cmd.gioi_han_giay, 10) || 120) * 1000, batDau = Date.now();
    var can = parseInt(cmd.can, 10) || 0;
    function ket(vi) {
      report("quote-node", vi, { idx: cmd.idx, node: cmd.buoc });
      theoDoiLenh(win, cmd);
    }
    var hetGio = function () {
      return Date.now() - batDau >= han || (cmd.buoc !== "luot" && can > 0 && dem.follow >= can);
    };
    cho(win, function () { return dsBai(doc).length > 0; }, 20000, function (co) {
      if (!co) { ket("khong thay bai nao tren /home"); return; }
      if (cmd.buoc === "luot") {
        var c = {};
        for (var k in cmd) { c[k] = cmd[k]; }
        c.so_follow = 0; c.tu_khoa = []; c.so_bai_tim = 0;     // follow la node RIENG
        chayTuongTac(win, doc, c, ket);
        return;
      }
      var tu = (cmd.tu_khoa || []).map(function (t) { return String(t || "").trim(); })
                                  .filter(function (t) { return t; });
      if (cmd.buoc === "tim") {
        chayTimKiem(win, doc, tu, parseInt(cmd.so_bai, 10) || 1, hetGio, function () {
          ket("tim tu khoa: follow " + dem.follow + "/" + can);
        });
        return;
      }
      chayFollow(win, doc, can, hetGio, function () { ket("trang goi y: follow " + dem.follow + "/" + can); });
    });
  }
  function chayQuote(win, cmd) {
    var doc = win.document;
    var href = String(win.location.href || "");
    if (!/^https:\/\/(x|twitter)\.com\//.test(href)) { return; }
    var man = xwPhanLoai(href, doc.body ? doc.body.innerText.slice(0, 4000) : "");
    if (man === "x-login") { report("logged-out", href.slice(0, 120), { idx: cmd.idx }); return; }
    if (man === "x-locked") { report("x-locked", href.slice(0, 120), { idx: cmd.idx }); return; }
    var khoa = cmd.idx + "|" + cmd.url;
    if (QUOTE_LAM[khoa]) { return; }
    if (cmd.buoc === "cho") {             // trang dau vua mo: ngoi cho buoc that tu driver
      QUOTE_LAM[khoa] = 1;
      theoDoiLenh(win, cmd);
      return;
    }
    var path = href.replace(/^https:\/\/[^/]+/, "").split("?")[0].toLowerCase();
    var dung;
    if (cmd.buoc === "quote") {
      dung = !!xwIdStatus(href) && xwIdStatus(href) === xwIdStatus(cmd.url) && !/\/quotes\b/.test(path);
    } else if (cmd.handle) {
      var h = "/" + String(cmd.handle).replace(/^@/, "").toLowerCase();
      dung = path === h || path === h + "/";
    } else {
      dung = /^\/home\/?$/.test(path);
    }
    if (!dung) {
      if (Date.now() - (QUOTE_DI[cmd.idx] || 0) < 20000) { return; }
      QUOTE_DI[cmd.idx] = Date.now();
      report("seen", "chuyen toi " + String(cmd.url).slice(0, 100), { idx: cmd.idx });
      try { win.location.href = cmd.url; } catch (e) {}
      return;
    }
    if (!xinQuyen()) { return; }
    QUOTE_LAM[khoa] = 1;
    win.setTimeout(function () {
      if (cmd.buoc === "quote") { lamQuote(win, doc, cmd); }
      else if (cmd.buoc === "follow") { lamFollowKenh(win, doc, cmd); }
      else if (cmd.buoc === "lich") { docLichSu(win, doc, cmd); }
      else if (cmd.buoc === "luot" || cmd.buoc === "tim" || cmd.buoc === "goiy") { lamNodeHome(win, doc, cmd); }
      else { gomBai(win, doc, cmd); }
    }, 1500);
  }

  function onPage(win) {
    var cmd = getCommand();
    if (cmd && cmd.action === "xquote") { chayQuote(win, cmd); return; }
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
            var ids = [];
            var ls = els[i].querySelectorAll('a[href*="/status/"]');
            for (var j = 0; j < ls.length; j++) {
              var mm = String(ls[j].getAttribute("href") || "").match(/^\/([^\/]+)\/status\/(\d+)/);
              if (mm && ids.indexOf(mm[1] + ":" + mm[2]) < 0) { ids.push(mm[1] + ":" + mm[2]); }
            }
            var rl = els[i].querySelectorAll('div[role="link"]').length;
            ra.push("[" + i + "] " + chuBai(els[i]).slice(0, 80) + " {ids=" + ids.join(",")
                    + " roleLink=" + rl + "}");
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
    if (!xinQuyen()) { return; }          // ban agent khac (tien trinh khac) dang chay lenh nay
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
