"""Tuong tac bang acc phu: vao bai da dang, tha cam xuc + binh luan (spintax).

Muc dich: tao tuong tac that (reaction/comment) cho bai -> Facebook danh gia bai
va group co tuong tac tot, tang hien thi va de duoc de xuat. Chay qua trinh duyet
that (BiDi) bang chinh phien dang nhap cua acc phu.

AN TOAN: moi acc gioi han so comment/ngay, gian gio ngau nhien, comment spintax
(khong trung nhau) -- comment hang loat giong het nhau la dau hieu spam ro nhat.
"""

from __future__ import annotations

from typing import Optional

from . import bidi, spintax

# JS chay TRONG trang bai viet: tha 1 cam xuc + (tuy chon) binh luan.
# Tra ve JSON {liked, commented, detail}.
_INTERACT_JS = r"""(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = { liked: false, commented: false, detail: "" };
  const COMMENT = %(comment)s;   // chuoi da spin san (co the rong)
  const DO_LIKE = %(do_like)s;

  // cuon xuong mot chut cho bai + o binh luan hien
  window.scrollBy(0, 400); await sleep(1500);

  // ---- 1. Tha cam xuc (Like) ----
  if (DO_LIKE) {
    try {
      const btns = [...document.querySelectorAll('[role="button"][aria-label]')];
      // Nut Thich cua BAI (khong phai cua comment): aria-label dung la "Thích"/"Like".
      const like = btns.find((b) => /^(Thích|Like)$/i.test(b.getAttribute("aria-label") || ""));
      if (like) {
        like.scrollIntoView({ block: "center" });
        await sleep(500 + Math.random() * 800);
        like.click();
        out.liked = true;
      } else {
        out.detail += "khong thay nut Thich; ";
      }
    } catch (e) { out.detail += "like loi: " + e + "; "; }
  }

  // ---- 2. Binh luan ----
  if (COMMENT) {
    try {
      await sleep(1200 + Math.random() * 1500);
      // O soan binh luan: contenteditable role=textbox, aria-label co "bình luận"/"comment".
      let box = [...document.querySelectorAll('div[contenteditable="true"][role="textbox"]')]
        .find((b) => /bình luận|comment/i.test(b.getAttribute("aria-label") || "")) ||
        document.querySelector('div[contenteditable="true"][role="textbox"]');
      if (!box) {
        // Co the phai bam "Bình luận" de mo o soan.
        const cbtn = [...document.querySelectorAll('[role="button"][aria-label]')]
          .find((b) => /^(Bình luận|Comment)$/i.test(b.getAttribute("aria-label") || ""));
        if (cbtn) { cbtn.click(); await sleep(1500); }
        box = document.querySelector('div[contenteditable="true"][role="textbox"]');
      }
      if (!box) { out.detail += "khong thay o binh luan; "; return JSON.stringify(out); }

      box.scrollIntoView({ block: "center" });
      box.focus();
      await sleep(400 + Math.random() * 600);
      // Chen text kieu go tay: execCommand fire dung su kien cho editor cua FB.
      let ok = false;
      try { ok = document.execCommand("insertText", false, COMMENT); } catch (e) {}
      if (!ok) {
        // Du phong: dispatch input event.
        box.textContent = COMMENT;
        box.dispatchEvent(new InputEvent("input", { bubbles: true, data: COMMENT, inputType: "insertText" }));
      }
      await sleep(700 + Math.random() * 800);

      // Gui: uu tien nut "Đăng"/"Comment/Bình luận", khong thi Enter.
      const send = [...document.querySelectorAll('[role="button"][aria-label]')]
        .find((b) => /^(Đăng|Bình luận|Comment|Post|Gửi)$/i.test(b.getAttribute("aria-label") || ""));
      if (send && !send.getAttribute("aria-disabled")) {
        send.click();
      } else {
        box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
        box.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
      }
      await sleep(2500);
      // Xac nhan tho: o soan da rong lai (da gui) thi coi la thanh cong.
      out.commented = !((box.textContent || "").trim());
      if (!out.commented) out.detail += "go duoc nhung chua chac da gui; ";
    } catch (e) { out.detail += "comment loi: " + e + "; "; }
  }
  return JSON.stringify(out);
})()"""


def interact(port: int, comment_text: str = "", do_like: bool = True,
             timeout: float = 90.0) -> dict:
    """Tha cam xuc + (tuy chon) binh luan bai dang mo trong trinh duyet.

    ``comment_text`` co the la mau spintax -> se duoc spin thanh mot ban.
    """
    import json
    cmt = spintax.spin(comment_text or "")
    js = _INTERACT_JS % {"comment": json.dumps(cmt), "do_like": "true" if do_like else "false"}
    try:
        raw = bidi.run_js(port, js, timeout=timeout)
        data = json.loads(raw) if raw else {}
    except bidi.BidiError as exc:
        return {"liked": False, "commented": False, "detail": str(exc)}
    except ValueError:
        return {"liked": False, "commented": False, "detail": "không đọc được kết quả"}
    data["comment"] = cmt
    return data
