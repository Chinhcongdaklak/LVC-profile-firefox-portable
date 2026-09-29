/* Process script: TU BAM "Bo qua" tren trang checkpoint MEM cua Facebook.
 *
 * Facebook doi khi chan bang man "Chung toi nghi la tai khoan cua ban co hanh vi tu dong"
 * (/checkpoint/601051028565049/...) co nut "Bo qua" -> bam la di tiep. Agent nay chay
 * TREN MOI TRANG facebook.com/checkpoint/* cua moi profile do tool mo (dang nhap cookie,
 * dang nhap web, bat chuyen nghiep, dang page/nhom, tao fanpage...) va bam nut do bang su
 * kien "nguoi that" (setHandlingUserInput). Khong co lenh; luon hoat dong.
 *
 * CHI bam nut kieu "bo qua / skip / de sau". Nut "Tiep tuc / Continue / OK / Da hieu" chi
 * bam khi trang la canh bao MEM (co chu "hanh vi tu dong" / "automated behavior"); trang
 * checkpoint CUNG (doi xac minh) thi KHONG dung vao -> cac agent khac se bao checkpoint sau
 * thoi gian an han (12s).
 *
 * Bao ve cha: sendAsyncMessage("qlfpsk:report") -> <profile>/qlfp-skip.log (de tool doc).
 */
"use strict";

/* ---- phan THUAN (test duoc bang node) ---------------------------------- */
var QLFP_SKIP_RE = /^(bỏ qua|bo qua|skip|skip for now|bỏ qua bây giờ|bỏ qua lúc này|not now|để sau|lúc khác|dismiss)$/i;
var QLFP_TIEP_RE = /^(tiếp tục|tiep tuc|continue|ok|okay|đã hiểu|da hieu|got it|hiểu rồi|đồng ý|dong y)$/i;
var QLFP_MEM_RE = /hành vi tự động|hanh vi tu dong|automated behavior|automated behaviour|nghi là tài khoản|we suspect|suspicious activity|đăng nhập bất thường/i;

function qlfpChuan(s) { return (s || "").replace(/\s+/g, " ").trim(); }
/** Trang checkpoint MEM (canh bao, co the bo qua) theo chu tren trang. */
function qlfpTrangMem(bodyText) { return QLFP_MEM_RE.test(bodyText || ""); }
/** Nut nay co phai nut "bo qua" khong. ``mem`` = trang mem -> nhan ca Tiep tuc/OK. */
function qlfpLaNutBoQua(text, mem) {
  var t = qlfpChuan(text);
  if (!t || t.length > 40) { return false; }
  if (QLFP_SKIP_RE.test(t)) { return true; }
  return !!mem && QLFP_TIEP_RE.test(t);
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = { laNutBoQua: qlfpLaNutBoQua, trangMem: qlfpTrangMem };
}

/* ---- phan chay trong Firefox ------------------------------------------- */
if (typeof sendAsyncMessage === "function") {

  function report(state, detail) {
    try { sendAsyncMessage("qlfpsk:report", { state: state, detail: detail || "" }); } catch (e) {}
  }
  function vis(el) {
    try { var b = el.getBoundingClientRect(); return b.width > 20 && b.height > 8 && el.offsetParent !== null; }
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
    } catch (e) { return false; }
    finally { try { if (handle) { handle.destruct(); } } catch (e2) {} }
  }
  function timNut(win) {
    var d = win.document, mem = false;
    try { mem = qlfpTrangMem(d.body ? d.body.innerText : ""); } catch (e) {}
    var cands = d.querySelectorAll('[role="button"], button, input[type="submit"], a[role="link"]');
    var n = Math.min(cands.length, 300);
    for (var i = 0; i < n; i++) {
      var el = cands[i];
      if (!vis(el)) { continue; }
      var text = el.getAttribute("aria-label") || el.value || el.textContent || "";
      if (qlfpLaNutBoQua(text, mem)) { return { el: el, text: qlfpChuan(text), mem: mem }; }
    }
    return null;
  }

  function onPage(win) {
    var href = "";
    try { href = win.location.href || ""; } catch (e) { return; }
    if (href.indexOf("facebook.com") === -1 || href.indexOf("/checkpoint") === -1) { return; }
    var lan = 0, bam = 0;
    (function tick() {
      try {
        if ((win.location.href || "").indexOf("/checkpoint") === -1) { return; }   // da di tiep
        var nut = timNut(win);
        if (nut) {
          bam++;
          clickReal(win, nut.el);
          report("skipped", "bam '" + nut.text + "'" + (nut.mem ? " (canh bao mem)" : "") + " | " + href.slice(0, 120));
          if (bam >= 2) { return; }                 // toi da 2 lan moi lan tai trang
          win.setTimeout(tick, 3000);
          return;
        }
        if (++lan < 20) { win.setTimeout(tick, 800); return; }   // cho toi ~16s nut hien ra
        report("cung", "khong co nut bo qua | " + href.slice(0, 120));
      } catch (e) { report("loi", String(e)); }
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
          win.setTimeout(function () { onPage(win); }, 1200);
        }, { once: true });
      } catch (e) {}
    },
  };
  Services.obs.addObserver(observer, "content-document-global-created");
}
