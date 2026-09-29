() => {
  // Hook nay chay TRUOC JS cua Facebook (qua BiDi addPreloadScript) de bat cac
  // truy van GraphQL that ma FB gui -> luu mau (doc_id + nguyen bo tham so +
  // headers) len window de bo quet phat lai. Tiem sau khi trang tai thi khong
  // an vi FB da giu tham chieu fetch/XHR goc tu luc tai.
  if (window.__lvcHook) return;
  window.__lvcHook = true;
  const isFeed = (n) => !/Mutation$/i.test(n) && /Feed|Timeline|Stories/i.test(n) && /Comet|Profile|Group|Page/i.test(n);
  const isVideo = (n) => /Video/i.test(n) && !/Feed|Timeline|Stories/i.test(n) && !/Mutation$/i.test(n);
  const H = (h) => {
    const r = {};
    try {
      if (!h) return r;
      if (typeof h.forEach === "function") h.forEach((v, k) => (r[String(k).toLowerCase()] = v));
      else if (Array.isArray(h)) for (const e of h) r[String(e[0]).toLowerCase()] = e[1];
      else for (const e of Object.entries(h)) r[String(e[0]).toLowerCase()] = e[1];
    } catch (e) {}
    return r;
  };
  function cap(body, headers) {
    try {
      if (typeof body !== "string" || body.indexOf("doc_id") === -1) return;
      const p = new URLSearchParams(body);
      if (!p.get("doc_id")) return;
      const name = p.get("fb_api_req_friendly_name") || "";
      window.__lvcNames = window.__lvcNames || {};
      window.__lvcNames[name] = (window.__lvcNames[name] || 0) + 1;
      const tpl = { docId: p.get("doc_id"), name, variables: p.get("variables"),
                    fields: Object.fromEntries(p.entries()), headers: headers || {} };
      if (isFeed(name)) window.__lvcFeed = tpl;
      if (isVideo(name)) { window.__lvcVideos = window.__lvcVideos || {}; window.__lvcVideos[name] = tpl; }
    } catch (e) {}
  }
  const of = window.fetch;
  window.fetch = function (input, init) {
    try {
      const url = typeof input === "string" ? input : input && input.url;
      if (url && url.indexOf("/api/graphql") !== -1 && init && typeof init.body === "string") cap(init.body, H(init.headers));
    } catch (e) {}
    return of.apply(this, arguments);
  };
  const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send, osh = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; this.__h = {}; return oo.apply(this, arguments); };
  XMLHttpRequest.prototype.setRequestHeader = function (k, v) { try { this.__h = this.__h || {}; this.__h[String(k).toLowerCase()] = v; } catch (e) {} return osh.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (body) {
    try { if (this.__u && String(this.__u).indexOf("/api/graphql") !== -1) cap(body, this.__h); } catch (e) {}
    return os.apply(this, arguments);
  };
}
