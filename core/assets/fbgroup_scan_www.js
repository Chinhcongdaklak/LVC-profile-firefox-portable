/* =====================================================================
 *  Boc bai nhom tren www.facebook.com (DOM da render, React).
 *
 *  Dung de: (1) kiem tra heuristic boc bai co dung khong, (2) lay mau JSON
 *  gui lai de chinh cho khop DOM that.
 *
 *  Cach dung (profile DA DANG NHAP):
 *    1. Mo:  https://www.facebook.com/groups/<ID_HOAC_SLUG>
 *    2. Cuon xuong vai lan cho feed hien them bai.
 *    3. F12 -> Console -> dan toan bo file nay -> Enter.
 *  Ket qua: JSON in ra Console + chep vao clipboard + hien o overlay.
 *
 *  Doi so bai:  window.__FB_SCAN_COUNT = 20  (truoc khi dan). Mac dinh 15.
 * ===================================================================== */
(function () {
  "use strict";
  var TARGET = (window.__FB_SCAN_COUNT | 0) || 15;

  function clean(t) { return (t || "").replace(/\s+/g, " ").trim(); }
  function txt(el) { try { return clean(el.innerText || el.textContent); } catch (e) { return ""; } }

  // --- tim cac the bai top-level (khong phai binh luan) ---
  function articleNodes() {
    var all = Array.from(document.querySelectorAll('div[role="article"]'));
    // Bai top-level thuong CO link toi /posts/ hoac /permalink/ trong nhom.
    // Binh luan thi khong. Loc theo do + loai the long nhau (giu the ngoai cung).
    var kept = all.filter(function (a) {
      if (a.querySelector('div[role="article"]')) return false; // co article con -> la vo, bo
      return !!a.querySelector('a[href*="/posts/"],a[href*="/permalink/"],a[href*="story_fbid"],a[href*="/groups/"][href*="/permalink"]');
    });
    return kept.length ? kept : all;
  }

  function findPermalink(a) {
    var sel = 'a[href*="/posts/"],a[href*="/permalink/"],a[href*="story_fbid"]';
    var links = a.querySelectorAll(sel);
    for (var i = 0; i < links.length; i++) {
      var h = links[i].href || "";
      if (/\/posts\/|\/permalink\/|story_fbid/.test(h)) return h.split("?")[0];
    }
    return "";
  }

  function findAuthor(a) {
    var h = a.querySelector('h2 a, h3 a, h4 a, strong a, span a[href*="/user/"], a[role="link"] strong');
    if (h) return clean(h.textContent);
    var head = a.querySelector('h2, h3, h4');
    return head ? clean(head.textContent) : "";
  }

  function findCaption(a) {
    // Message thuong la khoi [dir="auto"] dai nhat, khong nam trong header/comment.
    var blocks = Array.from(a.querySelectorAll('div[dir="auto"], span[dir="auto"]'));
    var best = "";
    for (var i = 0; i < blocks.length; i++) {
      var t = txt(blocks[i]);
      // bo cac cum UI ngan
      if (/^(thích|like|bình luận|comment|chia sẻ|share|·|xem thêm|see more)$/i.test(t)) continue;
      if (t.length > best.length) best = t;
    }
    return best.slice(0, 5000);
  }

  function findImages(a) {
    var out = [];
    var imgs = a.querySelectorAll("img");
    for (var i = 0; i < imgs.length; i++) {
      var im = imgs[i], src = im.currentSrc || im.src || "";
      if (!/scontent|fbcdn/.test(src)) continue;
      var r = im.getBoundingClientRect();
      if (Math.min(r.width, r.height) < 90) continue;       // bo avatar/emoji nho
      if (out.indexOf(src) === -1) out.push(src);
    }
    return out;
  }

  function findVideos(a) {
    var out = [];
    var vs = a.querySelectorAll("video");
    for (var i = 0; i < vs.length; i++) {
      var s = vs[i].currentSrc || vs[i].src || "";
      if (s && out.indexOf(s) === -1) out.push(s);
    }
    var links = a.querySelectorAll('a[href*="/videos/"],a[href*="/watch/"],a[href*="/reel/"]');
    for (var k = 0; k < links.length; k++) {
      var h = links[k].href || "";
      if (h && out.indexOf(h) === -1) out.push(h.split("?")[0]);
    }
    return out;
  }

  var nodes = articleNodes();
  var posts = [], seen = {};
  for (var i = 0; i < nodes.length && posts.length < TARGET; i++) {
    var a = nodes[i];
    var permalink = findPermalink(a);
    var id = (permalink.match(/\/posts\/(\d+)|\/permalink\/(\d+)|story_fbid=(\d+)/) || [])
                .slice(1).find(Boolean) || permalink || ("idx" + i);
    if (seen[id]) continue; seen[id] = 1;
    var imgs = findImages(a), vids = findVideos(a), cap = findCaption(a);
    var fmt = vids.length ? "Video" : (imgs.length > 1 ? "Album" : (imgs.length ? "Ảnh" : (cap ? "Text" : "Khác")));
    posts.push({ id: id, fmt: fmt, author: findAuthor(a), caption: cap,
                 permalink: permalink, images: imgs, videos: vids });
  }

  var out = { group: location.href.split("?")[0], count: posts.length,
              scanned_at: new Date().toISOString(), posts: posts };
  var json = JSON.stringify(out, null, 2);
  try { navigator.clipboard.writeText(json); } catch (e) {}
  console.log("[quet-www] lấy được " + posts.length + " bài. JSON đã ở clipboard.");
  console.log(out);

  try {
    var box = document.getElementById("qlfp-www-box"); if (box) box.remove();
    box = document.createElement("div");
    box.id = "qlfp-www-box";
    box.style.cssText = "position:fixed;inset:8px;z-index:2147483647;background:#111;color:#eee;border:2px solid #1f6aa5;border-radius:8px;padding:10px;font:12px monospace;display:flex;flex-direction:column";
    var bar = document.createElement("div");
    bar.style.cssText = "display:flex;justify-content:space-between;margin-bottom:6px";
    bar.innerHTML = "<b>Quét www: " + posts.length + " bài — đã chép clipboard</b>";
    var btn = document.createElement("button"); btn.textContent = "Đóng";
    btn.onclick = function () { box.remove(); }; bar.appendChild(btn);
    var ta = document.createElement("textarea"); ta.value = json;
    ta.style.cssText = "flex:1;width:100%;background:#000;color:#0f0;border:none;resize:none";
    box.appendChild(bar); box.appendChild(ta); document.body.appendChild(box);
    ta.focus(); ta.select();
  } catch (e) {}
  window.__FB_SCAN_RESULT = out;
})();
