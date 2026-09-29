/* =====================================================================
 *  Quet bai nhom bang cach PHAT LAI truy van GraphQL that (port tu Hub care).
 *
 *  Chay TRONG TRANG facebook.com (qua WebDriver BiDi). Uu diem so voi boc DOM:
 *   - Lay du lieu JSON co cau truc (caption/anh/video/permalink), khong phu thuoc
 *     ten class roi.
 *   - Phan trang lay nhieu bai.
 *   - Lay duoc URL .mp4 THAT cua video (progressive_url HD) -> tai video ve duoc.
 *
 *  Cach lam:
 *   1. Hook fetch de BAT mot truy van feed that ma chinh Facebook gui (doc_id +
 *      NGUYEN bo tham so __csr/__hs/__rev/__spin_* + headers x-*). Cuon de FB ban
 *      truy van do.
 *   2. Phat lai truy van do, thay {count, cursor} -> phan trang.
 *   3. Di bo cay JSON nhat bai (post_id / Story co noi dung), gom media trong
 *      nhanh attachments|media|styles cua chinh bai.
 *   4. Bai co video: phat lai truy van video (bat duoc) theo video_id -> progressive_url.
 *
 *  window.__FB_SCAN_COUNT = 20  (dat truoc). Mac dinh __TARGET__.
 * ===================================================================== */
(async () => {
  "use strict";
  const TARGET = (window.__FB_SCAN_COUNT | 0) || __TARGET__;
  const GRAPHQL = "https://www.facebook.com/api/graphql/";
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ---- phan loai truy van theo tu khoa (FB doi ten theo ban dung) ----
  const isFeed = (n) =>
    !/Mutation$/i.test(n) && /Feed|Timeline|Stories/i.test(n) && /Comet|Profile|Group|Page/i.test(n);
  const isVideo = (n) =>
    /Video/i.test(n) && !/Feed|Timeline|Stories/i.test(n) && !/Mutation$/i.test(n);

  const headersOf = (h) => {
    const r = {};
    try {
      if (!h) return r;
      if (typeof h.forEach === "function") h.forEach((v, k) => (r[String(k).toLowerCase()] = v));
      else if (Array.isArray(h)) for (const [k, v] of h) r[String(k).toLowerCase()] = v;
      else for (const [k, v] of Object.entries(h)) r[String(k).toLowerCase()] = v;
    } catch (e) {}
    return r;
  };

  // ---- 1+2. Hook da duoc cai bang preload script (fbgroup_hook.js) TRUOC khi FB
  // chay. O day chi cuon de FB ban truy van feed roi doc mau da bat len window. ----
  let feedTpl = window.__lvcFeed || null;
  const videoTpls = {};
  for (let i = 0; i < 25 && !window.__lvcFeed; i++) {
    window.scrollBy(0, 1400);
    await sleep(1000);
  }
  feedTpl = window.__lvcFeed;
  Object.assign(videoTpls, window.__lvcVideos || {});
  if (!feedTpl || !feedTpl.fields || !feedTpl.variables) {
    return JSON.stringify({ error: "chưa bắt được mẫu feed", da_thay: window.__lvcNames || {} });
  }

  // ---- helper: tach JSON streamed (nhieu object noi nhau) ----
  function tachJson(text) {
    const t = String(text).replace(/^for\s*\(;;\);/, "");
    const ra = [];
    let sach = "", dau = -1, sau = 0, trongChuoi = false, thoat = false;
    for (let i = 0; i < t.length; i++) {
      const c = t[i];
      if (trongChuoi) {
        if (c < " ") { sach += "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"); thoat = false; continue; }
        sach += c;
        if (thoat) thoat = false; else if (c === "\\") thoat = true; else if (c === '"') trongChuoi = false;
        continue;
      }
      sach += c;
      if (c === '"') trongChuoi = true;
      else if (c === "{") { if (sau === 0) dau = sach.length - 1; sau++; }
      else if (c === "}") { sau--; if (sau === 0 && dau >= 0) { try { ra.push(JSON.parse(sach.slice(dau))); } catch (e) {} dau = -1; } }
    }
    return ra;
  }

  function timCursor(goc) {
    let pi = null, edge = null;
    const di = (n) => {
      if (!n || typeof n !== "object") return;
      if (Array.isArray(n)) return n.forEach(di);
      if (!pi && n.page_info && n.page_info.has_next_page && typeof n.page_info.end_cursor === "string") pi = n.page_info.end_cursor;
      if (Array.isArray(n.edges) && n.edges.length) { const c = n.edges[n.edges.length - 1] && n.edges[n.edges.length - 1].cursor; if (typeof c === "string" && c) edge = c; }
      for (const v of Object.values(n)) di(v);
    };
    di(goc);
    return pi || edge;
  }

  // ---- 3. Di bo cay JSON nhat bai ----
  const KHOA_DINH_KEM = new Set(["attachments","attachment","all_subattachments","media","styles","style_type_renderer"]);
  function chu(n) { return n && typeof n === "object" && typeof n.text === "string" ? n.text : ""; }

  function gomMedia(node) {
    const media = [], daCo = new Set();
    let coVideo = false, videoId = "";
    const them = (url, loai) => { if (typeof url === "string" && url.startsWith("http") && !daCo.has(url)) { daCo.add(url); media.push([url, loai]); } };
    const di = (n, sau, trongDK) => {
      if (!n || typeof n !== "object" || sau > 24) return;
      if (Array.isArray(n)) return n.forEach((x) => di(x, sau + 1, trongDK));
      if (trongDK && (n.__typename === "Video" || typeof n.video_id === "string" || n.is_playable === true)) {
        coVideo = true;
        for (const x of [n.video_id, n.__typename === "Video" ? n.id : null]) {
          if (!videoId && typeof x === "string" && /^[0-9]{6,}$/.test(x)) videoId = x;
        }
      }
      them(n.browser_native_hd_url, "video");
      them(n.browser_native_sd_url, "video");
      them(n.playable_url_quality_hd, "video");
      them(n.playable_url, "video");
      for (const k of ["image","photo_image","viewer_image","full_image","preferred_thumbnail"]) {
        const v = n[k]; if (v && typeof v === "object") them(v.uri || (v.image && v.image.uri), "image");
      }
      for (const [k, v] of Object.entries(n)) di(v, sau + 1, trongDK || KHOA_DINH_KEM.has(k));
    };
    di(node, 0, false);
    const video = media.filter((m) => m[1] === "video");
    return { media: video.length ? video.slice(0, 1) : media.slice(0, 10), coVideo, videoId };
  }

  function actorOf(n) {
    // Tac gia: node co actors[] hoac actor.name gan story.
    try {
      if (n.actors && n.actors[0] && n.actors[0].name) return n.actors[0].name;
      if (n.actor && n.actor.name) return n.actor.name;
      const s = n.comet_sections && n.comet_sections.context_layout;
      if (s) { const t = JSON.stringify(s).match(/"name":"([^"]{1,60})"/); if (t) return t[1]; }
    } catch (e) {}
    return "";
  }

  function nhatBai(goc, out) {
    const di = (n) => {
      if (!n || typeof n !== "object") return;
      if (Array.isArray(n)) return n.forEach(di);
      const laBai = n.post_id || n.legacy_story_hideable_id || (n.__typename === "Story" && (n.message || n.comet_sections));
      const id = laBai ? (n.post_id || n.legacy_story_hideable_id || n.id) : null;
      if (id) {
        const noi = chu(n.message) || chu(n.comet_sections && n.comet_sections.content && n.comet_sections.content.story && n.comet_sections.content.story.message) || "";
        const cu = out.get(String(id));
        if (!cu || noi.length > cu.noi_dung.length) {
          const g = gomMedia(n);
          out.set(String(id), {
            id: String(id), noi_dung: noi,
            link: n.wwwURL || n.url || n.permalink_url || (cu && cu.link) || null,
            author: actorOf(n) || (cu && cu.author) || "",
            media: g.media, co_video: g.coVideo, video_id: g.videoId,
          });
        }
      }
      for (const v of Object.values(n)) di(v);
    };
    di(goc);
  }

  // ---- goi lai mot mau GraphQL, thay variables ----
  async function goiGraphql(tpl, bien) {
    const body = new URLSearchParams();
    for (const [k, v] of Object.entries(tpl.fields || {})) body.set(k, v);
    body.set("variables", JSON.stringify(bien));
    const hd = { "content-type": "application/x-www-form-urlencoded" };
    for (const [k, v] of Object.entries(tpl.headers || {})) if (String(k).toLowerCase().startsWith("x-")) hd[String(k).toLowerCase()] = v;
    const r = await fetch(GRAPHQL, { method: "POST", credentials: "include", headers: hd, body: body.toString() });
    return { ma: r.status, tho: await r.text() };
  }

  // ---- URL video tu phan hoi truy van video ----
  function timUrlVideo(text) {
    const khoi = tachJson(text);
    const ra = [], mp4 = [];
    const di = (n) => {
      if (!n || typeof n !== "object") return;
      if (Array.isArray(n)) return n.forEach(di);
      if (typeof n.progressive_url === "string" && n.progressive_url.startsWith("http")) ra.push({ url: n.progressive_url, chat: (n.metadata && n.metadata.quality) || "" });
      for (const v of Object.values(n)) {
        if (typeof v === "string" && v.startsWith("http") && v.includes(".mp4")) mp4.push(v);
        else di(v);
      }
    };
    khoi.forEach(di);
    if (ra.length) { const chon = ra.find((x) => String(x.chat).toUpperCase() === "HD") || ra[0]; return chon.url; }
    return mp4.length ? mp4[0] : null;
  }

  const BIEN_ID_VIDEO = ["root_video_id","initial_node_id","nodeID","videoID","video_id"];
  async function xinUrlVideo(videoId) {
    for (const tpl of Object.values(videoTpls)) {
      if (!tpl || !tpl.fields || !tpl.variables) continue;
      let bien; try { bien = JSON.parse(tpl.variables); } catch (e) { continue; }
      const khoa = BIEN_ID_VIDEO.filter((k) => k in bien);
      if (!khoa.length) continue;
      const v = { ...bien }; for (const k of khoa) v[k] = String(videoId);
      try { const { tho } = await goiGraphql(tpl, v); const u = timUrlVideo(tho); if (u) return u; } catch (e) {}
    }
    return null;
  }

  // ---- 4. Phat lai feed, phan trang ----
  let bien; try { bien = JSON.parse(feedTpl.variables); } catch (e) { return JSON.stringify({ error: "mẫu feed hỏng" }); }
  const bai = new Map();
  let cursor = bien.cursor != null ? bien.cursor : null;
  const toiDaVong = Math.min(40, Math.ceil(TARGET / 2) + 8);
  let soKhoi = 0;
  const dbg = [];

  for (let vong = 0; vong < toiDaVong && bai.size < TARGET; vong++) {
    if (vong > 0) await sleep(400 + Math.random() * 600);
    const v = { ...bien, count: Math.min(TARGET, 25), cursor };
    let tho;
    try { const r = await goiGraphql(feedTpl, v); if (r.ma < 200 || r.ma >= 300) return JSON.stringify({ error: "GraphQL HTTP " + r.ma }); tho = r.tho; }
    catch (e) { return JSON.stringify({ error: "mạng lỗi: " + e }); }
    const json = tachJson(tho); soKhoi += json.length;
    const goi = json.find((k) => k && typeof k.error === "number");
    if (goi) return JSON.stringify({ error: "Facebook: " + (goi.errorSummary || goi.error) });
    const truoc = bai.size;
    for (const khoi of json) nhatBai(khoi, bai);
    const tiep = timCursor(json);
    const dem = (s) => String(tho).split(s).length - 1;
    dbg.push({ v: vong, khoi: json.length, bai_moi: bai.size - truoc, tong: bai.size,
               co_cursor: !!tiep, cursor_giong: tiep === cursor, do_dai: String(tho).length,
               post_id: dem('"post_id"'), story: dem('"__typename":"Story"'),
               legacy: dem("legacy_story_hideable_id") });
    if (!tiep || tiep === cursor) break;
    if (bai.size === truoc) break;
    cursor = tiep;
  }
  window.__lvcDbg = dbg;

  // ---- 5. Bo sung URL video cho bai co video ma chua co .mp4 ----
  const raBai = [...bai.values()].slice(0, TARGET);
  for (const b of raBai) {
    if (b.co_video && b.video_id && !b.media.some((m) => m[1] === "video")) {
      const u = await xinUrlVideo(b.video_id);
      if (u) b.media = [[u, "video"]];
    }
  }

  // ---- xuat ra dinh dang tool ----
  const posts = raBai.map((b) => {
    const images = b.media.filter((m) => m[1] === "image").map((m) => m[0]);
    let videos = b.media.filter((m) => m[1] === "video").map((m) => m[0]);
    if (!videos.length && b.co_video) videos = [b.link || ("https://www.facebook.com/watch/?v=" + (b.video_id || ""))];
    const fmt = videos.length ? "Video" : (images.length > 1 ? "Album" : (images.length ? "Ảnh" : (b.noi_dung.trim() ? "Text" : "Khác")));
    return { id: b.id, caption: b.noi_dung, author: b.author || "", permalink: b.link || "", images, videos, fmt };
  });
  return JSON.stringify({ count: posts.length, so_khoi: soKhoi, dbg, posts });
})();
