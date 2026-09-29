/* =====================================================================
 *  Quet bai viet mot nhom Facebook tren ban mbasic (HTML thuan).
 *
 *  Cach dung (tren profile DA DANG NHAP):
 *    1. Mo:  https://mbasic.facebook.com/groups/<ID_NHOM>
 *    2. F12 -> Console -> dan TOAN BO file nay -> Enter.
 *  Script tu FETCH cac trang mbasic ke tiep (cung origin, tu kem cookie), gom
 *  du SO_BAI trong MOT lan chay -> hien JSON + chep clipboard. Khong can chuyen
 *  trang, khong phai dan lai.
 *
 *  Doi so bai:  window.__FB_SCAN_COUNT = 30  (chay truoc khi dan)  -- mac dinh 20.
 *
 *  Vi sao mbasic: facebook.com chinh la React ao hoa, class xao tron, parse cuc
 *  brittle. mbasic tra HTML server render, on dinh hon nhieu.
 *  Luu y: selector FB co the doi -- neu thieu truong, gui lai mau HTML de chinh.
 * ===================================================================== */
(async function () {
  "use strict";

  var TARGET = (window.__FB_SCAN_COUNT | 0) || 20;
  var MAX_PAGES = 10;

  function log(m) { try { console.log("[quet-nhom] " + m); } catch (e) {} }
  function abs(href) { try { return new URL(href, location.origin).href; } catch (e) { return href || ""; } }
  function clean(t) { return (t || "").replace(/\s+/g, " ").trim(); }

  var UI_RE = /^(thích|like|bình luận|comment|chia sẻ|share|xem thêm|see more|ẩn|hide|báo cáo|report|theo dõi|follow|gửi|send|\d+ (bình luận|lượt|người|comment))/i;

  function findPermalink(art) {
    var ab = art.querySelector("abbr");
    if (ab) { var a = ab.closest("a"); if (a && a.getAttribute("href")) return abs(a.getAttribute("href")); }
    var links = art.querySelectorAll("a[href]");
    for (var i = 0; i < links.length; i++) {
      var h = links[i].getAttribute("href") || "";
      if (/story\.php\?story_fbid=|\/permalink\/|\/posts\//.test(h)) return abs(h);
    }
    return "";
  }
  function findId(art, permalink) {
    var ft = art.getAttribute("data-ft");
    if (ft) { try { var j = JSON.parse(ft); if (j.top_level_post_id) return String(j.top_level_post_id); if (j.tl_objid) return String(j.tl_objid); } catch (e) {} }
    var m = (permalink || "").match(/story_fbid=(\d+)|\/permalink\/(\d+)|\/posts\/(\d+)/);
    if (m) return m[1] || m[2] || m[3];
    return permalink || ("idx_" + Math.random().toString(36).slice(2));
  }
  function findAuthor(art) {
    var h = art.querySelector("h3 a, h4 a, header a");
    return h ? { name: clean(h.textContent), url: abs(h.getAttribute("href")) } : { name: "", url: "" };
  }
  function findTime(art) { var ab = art.querySelector("abbr"); return ab ? clean(ab.textContent) : ""; }

  function findText(art) {
    var parts = [], ps = art.querySelectorAll("p"), i, k;
    for (i = 0; i < ps.length; i++) parts.push(clean(ps[i].textContent));
    if (!parts.join("").trim()) {
      var divs = art.querySelectorAll("div");
      for (k = 0; k < divs.length && parts.length < 6; k++) {
        var d = divs[k];
        if (d.querySelector("h3,h4,abbr,form,table")) continue;
        var t = clean(d.textContent);
        if (t && t.length > 1 && !UI_RE.test(t)) parts.push(t);
      }
    }
    var text = parts.filter(function (x, idx) { return x && parts.indexOf(x) === idx; }).join("\n");
    return clean(text).slice(0, 5000);
  }

  function findMedia(art) {
    var imgs = [], videos = [], i, im = art.querySelectorAll("img[src]");
    for (i = 0; i < im.length; i++) {
      var src = im[i].getAttribute("src") || "";
      if (/^data:/.test(src) || /emoji|static|rsrc\.php|blank|spacer/i.test(src)) continue;
      var full = abs(src); if (imgs.indexOf(full) === -1) imgs.push(full);
    }
    var links = art.querySelectorAll("a[href]");
    for (i = 0; i < links.length; i++) {
      var h = links[i].getAttribute("href") || "";
      if (/video_redirect\/\?src=|\/watch\/\?v=|\/videos\/|\/reel\//.test(h)) {
        var m = h.match(/[?&]src=([^&]+)/);
        var v = m ? decodeURIComponent(m[1]) : abs(h);
        if (videos.indexOf(v) === -1) videos.push(v);
      }
    }
    return { images: imgs, videos: videos };
  }

  function findCounts(art) {
    var txt = art.textContent || "";
    var re = /(\d[\d.,]*)\s*(bình luận|comment)/i.exec(txt);
    var re2 = /(\d[\d.,]*)\s*(lượt thích|reaction|người)/i.exec(txt);
    return {
      reactions: re2 ? re2[1].replace(/[.,]/g, "") : "",
      comments: re ? re[1].replace(/[.,]/g, "") : "",
    };
  }

  function findNext(doc) {
    var links = doc.querySelectorAll("a[href]");
    for (var i = 0; i < links.length; i++) {
      var a = links[i], t = clean(a.textContent).toLowerCase(), h = a.getAttribute("href") || "";
      if (/xem thêm bài|bài viết cũ|see more posts|older posts|show more/i.test(t)) return abs(h);
      if (/\/groups\//.test(h) && /(bacr|cursor|bac=)/.test(h)) return abs(h);
    }
    return "";
  }

  function parseDoc(doc, seen, posts) {
    var arts = doc.querySelectorAll("article"), added = 0;
    for (var i = 0; i < arts.length; i++) {
      var art = arts[i], permalink = findPermalink(art), id = findId(art, permalink);
      if (seen[id]) continue;
      seen[id] = 1;
      var media = findMedia(art), author = findAuthor(art), counts = findCounts(art);
      posts.push({
        id: id, author: author.name, author_url: author.url, time: findTime(art),
        text: findText(art), permalink: permalink,
        images: media.images, videos: media.videos,
        reactions: counts.reactions, comments: counts.comments,
      });
      added++;
      if (posts.length >= TARGET) break;
    }
    return added;
  }

  function overlay(json, count) {
    try {
      var old = document.getElementById("qlfp-scan-box"); if (old) old.remove();
      var box = document.createElement("div");
      box.id = "qlfp-scan-box";
      box.style.cssText = "position:fixed;left:8px;right:8px;top:8px;bottom:8px;z-index:2147483647;background:#111;color:#eee;border:2px solid #1f6aa5;border-radius:8px;padding:10px;font:12px monospace;display:flex;flex-direction:column";
      var bar = document.createElement("div");
      bar.style.cssText = "display:flex;justify-content:space-between;margin-bottom:6px";
      bar.innerHTML = "<b>Quét nhóm: " + count + " bài — đã chép clipboard</b>";
      var btn = document.createElement("button"); btn.textContent = "Đóng";
      btn.onclick = function () { box.remove(); }; bar.appendChild(btn);
      var ta = document.createElement("textarea"); ta.value = json;
      ta.style.cssText = "flex:1;width:100%;background:#000;color:#0f0;border:none;resize:none";
      box.appendChild(bar); box.appendChild(ta); document.body.appendChild(box);
      ta.focus(); ta.select();
    } catch (e) { log("overlay loi: " + e); }
  }

  // -------- dieu phoi --------
  if (!/mbasic\.facebook\.com\/groups\//.test(location.href)) {
    alert("Hãy mở trang nhóm trên mbasic trước:\nhttps://mbasic.facebook.com/groups/<ID>");
    return;
  }

  var seen = {}, posts = [], doc = document, page = 0;
  while (posts.length < TARGET && page < MAX_PAGES) {
    page++;
    var got = parseDoc(doc, seen, posts);
    log("trang " + page + ": +" + got + " bài, tổng " + posts.length + "/" + TARGET);
    if (posts.length >= TARGET) break;
    var next = findNext(doc);
    if (!next) { log("hết trang / không thấy link 'xem thêm'."); break; }
    try {
      var res = await fetch(next, { credentials: "same-origin" });
      var html = await res.text();
      doc = new DOMParser().parseFromString(html, "text/html");
      await new Promise(function (r) { setTimeout(r, 500 + Math.random() * 600); }); // giãn nhịp
    } catch (e) { log("tải trang kế lỗi: " + e); break; }
  }

  var out = {
    group: location.href.replace(/\?.*$/, ""),
    scanned_at: new Date().toISOString(),
    count: posts.length,
    posts: posts.slice(0, TARGET),
  };
  var json = JSON.stringify(out, null, 2);
  try { await navigator.clipboard.writeText(json); } catch (e) {}
  overlay(json, out.count);
  window.__FB_SCAN_RESULT = out;
  log("XONG: " + out.count + " bài. JSON đã ở clipboard + ô trên màn hình.");
  return out;
})();
