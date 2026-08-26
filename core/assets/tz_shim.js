/* Process script: chay trong MOI tien trinh noi dung.
 *
 * Nghe su kien "content-document-global-created" -- ban ra truoc khi script cua
 * trang chay -- roi nap tz_patch.js vao mot sandbox phu len window cua trang.
 */
"use strict";

const TZ_TARGET = "__TZ_TARGET__";

const loader = Cc["@mozilla.org/moz/jssubscript-loader;1"]
  .getService(Ci.mozIJSSubScriptLoader);

const here = Services.dirsvc.get("GreD", Ci.nsIFile);
here.append("tz_patch.js");
const PATCH_URL = Services.io.newFileURI(here).spec;

/** Chi va trang that; bo qua giao dien trinh duyet va cac addon. */
function shouldPatch(win) {
  try {
    const scheme = win.location && win.location.protocol;
    return scheme === "http:" || scheme === "https:" || scheme === "file:" ||
           scheme === "data:" || scheme === "blob:";
  } catch (e) {
    return false;
  }
}

function inject(win) {
  const sandbox = Cu.Sandbox(win, {
    sandboxPrototype: win,
    wantXrays: false,
    sameZoneAs: win,
  });
  sandbox.TZ_NAME = TZ_TARGET;
  loader.loadSubScript(PATCH_URL, sandbox);
}

const observer = {
  observe(subject, topic) {
    if (topic !== "content-document-global-created") { return; }
    if (!shouldPatch(subject)) { return; }
    try {
      inject(subject);
    } catch (e) {
      dump("TZSHIM_ERR " + e + "\n");
    }
  },
};

try {
  Services.obs.addObserver(observer, "content-document-global-created");
} catch (e) {
  dump("TZSHIM_PROC_ERR " + e + "\n");
}
