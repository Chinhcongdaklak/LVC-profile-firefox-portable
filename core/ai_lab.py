"""Tab "Quet bai" (ex Thu nghiem AI): quet nhom -> gui vao job Auto dang nhom -> xao CHU o hang doi.

Hop dong: HOP-DONG.md muc "core/ai_lab.py" + muc "lan 4". Quyet dinh: ADR-006 (chi xao
chu, anh/video giu nguyen), ADR-007 (bo bai trong khi quet), ADR-009 (xao o hang doi
Auto dang nhom; gui/xao xuong core; gỡ dang truc tiep tu tab).

Row = dict co du khoa (xem ``row_moi``). Module nay KHONG biet tkinter.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from typing import Callable, Optional

from core import ai, fbgroup, fbupload
from core.config import TOOL_DIR

LAB_STORE = os.path.join(TOOL_DIR, "data", "ai_lab.json")
LAB_DIR = os.path.join(TOOL_DIR, "data", "ai_lab_media")

XAO = ("cho", "dang", "da", "loi")
#: post: "" chua gui | "gui" da gui vao job nhom (lan 4). Gia tri cu (cho/dang/da/loi/bo_qua/thu)
#: cua ban lan 3 doc len van hop le.
POST = ("", "gui", "cho", "dang", "da", "loi", "bo_qua", "thu")
#: Cong BiDi rieng cho tab nay (tab quet bai cu dung 9333) de hai duong khong gianh nhau.
PORT_MAC_DINH = 9337


# ------------------------------------------------------------------ Row
def row_moi(id_: str = "", source: str = "", caption_goc: str = "", imgs: Optional[list] = None,
            video: str = "") -> dict:
    """Row chuan: xao='cho', chua gui, chua chon."""
    return {
        "id": id_ or f"r{int(time.time() * 1000)}",
        "source": source or "",
        "caption_goc": caption_goc or "", "caption_moi": "",
        "imgs_goc": list(imgs or []), "imgs_moi": [],
        "video": video or "",
        "xao": "cho", "detail": "", "post": "", "chon": False,
    }


def chuan_hoa(raw: dict) -> dict:
    """Doc Row tu file (ke ca ban cu) -> du khoa, dung kieu."""
    r = row_moi(str(raw.get("id") or ""), raw.get("source") or "",
                raw.get("caption_goc") or "", raw.get("imgs_goc") or [], raw.get("video") or "")
    r["caption_moi"] = raw.get("caption_moi") or ""
    r["imgs_moi"] = list(raw.get("imgs_moi") or [])
    r["xao"] = raw.get("xao") if raw.get("xao") in XAO else "cho"
    r["detail"] = raw.get("detail") or ""
    r["post"] = raw.get("post") if raw.get("post") in POST else ""
    r["chon"] = bool(raw.get("chon", False))
    return r


def row_tu_post(p) -> dict:
    """Post (core.posts) -> Row; video dau tien (neu co) giu nguyen de dang kem."""
    vid = p.saved_videos[0] if getattr(p, "saved_videos", None) else ""
    return row_moi(f"r{int(time.time() * 1000)}_{id(p) & 0xffff}", p.permalink or "",
                   p.caption or "", list(p.saved_paths or []), vid)


# ------------------------------------------------------------------ quet
def quet_nhom(manager, account, group_url: str, count: int, lab_dir: str, *,
              port: int = PORT_MAC_DINH, log: Optional[Callable[[str], None]] = None) -> list:
    """Mo nhom bang acc, boc `count` bai, tai anh/video ve lab_dir. LUON dong trinh duyet.

    Nem fbgroup.FbGroupError khi trinh duyet chua san sang / boc bai hong.
    """
    noi = log or (lambda _m: None)
    os.makedirs(lab_dir, exist_ok=True)
    posts = []
    try:
        noi("mở nhóm...")
        manager.launch_debug(account, group_url, port)
        if not fbgroup.wait_bidi_ready(port, timeout=30):
            raise fbgroup.FbGroupError("Trình duyệt chưa sẵn sàng (BiDi).")
        noi("đang bóc bài...")
        posts = fbgroup.posts_from_raw(
            fbgroup.extract_via_bidi(port, count, group_url=group_url), group_url)
        if posts:
            noi(f"tải ảnh/video của {len(posts)} bài...")
            fbgroup.download_all(posts, manager.profile_dir(account), account.get_proxy(),
                                 lab_dir, on_status=log)
    finally:
        try:
            manager.close(account, wait=8.0)
        except Exception:  # noqa: BLE001
            pass
    rows = [row_tu_post(p) for p in posts]
    # ADR-007: the quang cao/goi y lot vao bo quet -> khong chu, khong media -> bo.
    du = [r for r in rows if (r["caption_goc"].strip() or r["imgs_goc"] or r["video"])]
    if len(du) < len(rows):
        noi(f"bỏ {len(rows) - len(du)} bài trống (không chữ, không ảnh/video)")
    return du


_LINK_RE = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)


def bo_link(text: str) -> str:
    """Xoá mọi link (http/https/www...) khỏi caption bài viết; dọn khoảng trắng thừa từng dòng.

    Giữ nguyên xuống dòng; chỉ bỏ các token là link. Dùng cho nút 'Xoá link trong bài' ở tab đăng nhóm."""
    out = []
    for dong in (text or "").split("\n"):
        d = _LINK_RE.sub("", dong)
        d = re.sub(r"[ \t]{2,}", " ", d).strip()
        out.append(d)
    # bỏ dòng trống thừa ở hai đầu, gộp nhiều dòng trống liên tiếp thành một
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    goc = []
    for d in out:
        if d or (goc and goc[-1]):
            goc.append(d)
    return "\n".join(goc)


def quet_nhieu(manager, cap_acc_link, count: int, lab_dir: str, *,
               workers: int = 3, port_dau: int = PORT_MAC_DINH,
               on_acc: Optional[Callable[[dict], None]] = None,
               quet_fn: Optional[Callable] = None,
               log: Optional[Callable[[str], None]] = None) -> list:
    """Quét NHIỀU acc SONG SONG, mỗi acc một link nguồn riêng (ghép theo thứ tự).

    ``cap_acc_link`` = ``[(account, group_url), ...]``. Mỗi acc mở một cổng BiDi RIÊNG
    (``port_dau + i``) để không đụng nhau. Trả ``[{acc_id, url, rows, loi}]`` theo THỨ TỰ vào.
    ``on_acc(dict)`` gọi sau mỗi acc xong (vẽ dần). ``quet_fn`` tiêm cho thước (mặc định = quet_nhom)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    noi = log or (lambda _m: None)
    cap = [(a, str(u or "").strip()) for a, u in cap_acc_link if a and str(u or "").strip()]
    if not cap:
        return []
    quet = quet_fn or quet_nhom
    n = max(1, min(int(workers or 1), len(cap)))
    ket = {}

    def mot(i, account, url):
        try:
            rows = quet(manager, account, url, count, lab_dir, port=port_dau + i,
                        log=lambda m, a=account.id: noi(f"[{a}] {m}"))
            return {"acc_id": account.id, "url": url, "rows": rows, "loi": ""}
        except Exception as exc:  # noqa: BLE001
            return {"acc_id": account.id, "url": url, "rows": [], "loi": str(exc)[:150]}

    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = {ex.submit(mot, i, a, u): i for i, (a, u) in enumerate(cap)}
        for f in as_completed(futs):
            r = f.result()
            ket[futs[f]] = r
            if on_acc is not None:
                on_acc(r)
    return [ket[i] for i in range(len(cap))]


# ------------------------------------------------------------------ xao (1 Row)
def xao_bai(row: dict, cfg: ai.AiConfig, log: Optional[Callable[[str], None]] = None) -> dict:
    """CHI xao chu; anh/video giu nguyen (ADR-006). Sua tai cho, khong nem."""
    row["imgs_moi"] = list(row.get("imgs_goc") or [])
    goc = (row.get("caption_goc") or "").strip()
    try:
        if cfg.do_caption and goc:
            row["caption_moi"] = ai.transform_text(goc, cfg, log)
        else:
            row["caption_moi"] = goc
        row["xao"] = "da"
        row["detail"] = ""
    except Exception as exc:  # noqa: BLE001 - AiError hoac loi mang: ghi vao Row
        row["caption_moi"] = ""
        row["xao"] = "loi"
        row["detail"] = str(exc)[:200]
    return row


# ------------------------------------------------------------------ gui sang job nhom (lan 4)
def _base_cua(row: dict) -> str:
    raw = re.sub(r"[^0-9A-Za-z._-]", "_", str(row.get("id") or ""))[:40] or f"r{int(time.time())}"
    return f"qb_{raw}"


def _copy(src: str, dst: str) -> str:
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copy2(src, dst)
    return dst


def gui_sang_nhom(rows: list, job, *, log: Optional[Callable[[str], None]] = None) -> list:
    """Dua cac Row vao hang doi 'Bai cho dang' cua mot job Auto dang nhom.

    Dung dinh dang cua tab Auto dang nhom (nhu PostsTab.send_to_autoup cu) nhung COPY
    file de bang Quet bai van xem duoc media. Moi item duoc dat xao="cho" — gui sang
    nhom la kich ban kich hoat xao (REQ-005). Row: post="gui". Nem OSError khi khong
    tao duoc thu muc. Tra danh sach item vua them/cap nhat.
    """
    noi = log or (lambda _m: None)
    folder = (job.config.queue_dir or "").strip()
    if not folder:
        folder = os.path.join(TOOL_DIR, "data", "bai_cho_dang", f"job-{job.job_id}")
        job.config.queue_dir = folder
        job.save()
    os.makedirs(folder, exist_ok=True)

    def sidecar(base: str, text: str) -> str:
        p = os.path.join(folder, base + ".txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return p

    def extra(base: str, srcs: list) -> int:
        srcs = [s for s in srcs if s and os.path.isfile(s)]
        if not srcs:
            return 0
        sub = os.path.join(folder, base + "_media")
        os.makedirs(sub, exist_ok=True)
        for j, s in enumerate(srcs, start=1):
            _copy(s, os.path.join(sub, f"{j}{os.path.splitext(s)[1] or '.jpg'}"))
        return len(srcs)

    items = []
    for r in rows:
        base = _base_cua(r)
        caption = (r.get("caption_goc") or "").strip() or (r.get("source") or "")
        # BUG-003 / ADR-008: chi anh/video theo duoi; file la (.exe...) khong vao thu muc job.
        imgs = [p for p in (r.get("imgs_goc") or [])
                if p and os.path.isfile(p) and fbupload.is_image(p)]
        video = r.get("video") if (r.get("video") and os.path.isfile(r["video"])
                                   and fbupload.is_video(r["video"])) else ""
        if not caption and not imgs and not video:
            r["detail"] = "bỏ: không có chữ, không có ảnh/video"
            noi(f"bỏ dòng trống {r.get('id', '')}")
            continue
        try:
            if video:
                dest = _copy(video, os.path.join(folder, base + (os.path.splitext(video)[1] or ".mp4")))
                sidecar(base, caption)
                extra(base, imgs)
                kind, download = "video", "da"
            elif imgs:
                dest = _copy(imgs[0], os.path.join(folder, base + (os.path.splitext(imgs[0])[1] or ".jpg")))
                sidecar(base, caption)
                extra(base, imgs[1:])
                kind, download = "image", "da"
            else:
                dest = sidecar(base, caption)
                kind, download = "text", ""
        except OSError as exc:
            r["detail"] = f"không gửi được: {exc}"[:200]
            noi(r["detail"])
            continue
        job.add_to_queue(caption, dest, base, kind=kind, source=r.get("source") or "", download=download)
        it = next((x for x in job.queue if x.get("base") == base), None)
        if it is None:
            continue
        it["xao"] = "cho"
        it["xao_detail"] = ""
        it["caption_goc"] = caption
        items.append(it)
        r["post"] = "gui"
        r["detail"] = f"→ {job.name} — {job.config.label()}"
    job.save()
    noi(f"đã gửi {len(items)} bài vào {job.name} — {job.config.label()}")
    return items


def xao_hang_doi(job, items: list, cfg: ai.AiConfig, *,
                 log: Optional[Callable[[str], None]] = None,
                 dung: Optional[Callable[[], bool]] = None) -> dict:
    """Xao CHU tuan tu cac item hang doi cua job (ADR-006/009). Khong nem.

    cfg = ai.load_shared_config() (= cau hinh tab Quet bai) do phia goi dua vao.
    Ghi <queue_dir>/<base>_xao/caption.txt; item caption/xao/xao_detail; job.save().
    """
    dung = dung or (lambda: False)
    folder = (job.config.queue_dir or "").strip()
    da = loi = 0
    for it in items:
        if dung():
            break
        it["xao"] = "dang"
        job.save()
        try:
            base = it.get("base") or ""
            cap_goc = it.get("caption_goc") or it.get("caption") or ""
            it["caption_goc"] = cap_goc
            row = row_moi(base, it.get("source") or "", cap_goc)
            xao_bai(row, cfg, log)
            if row["xao"] != "da":
                raise ai.AiError(row["detail"] or "xào lỗi")
            cap_moi = row["caption_moi"] or cap_goc
            xao_dir = os.path.join(folder or os.path.dirname(it.get("media") or "") or ".", base + "_xao")
            os.makedirs(xao_dir, exist_ok=True)
            with open(os.path.join(xao_dir, "caption.txt"), "w", encoding="utf-8") as fh:
                fh.write(cap_moi)
            it["caption"] = cap_moi
            it["xao"] = "da"
            it["xao_detail"] = ""
            da += 1
        except Exception as exc:  # noqa: BLE001
            it["xao"] = "loi"
            it["xao_detail"] = str(exc)[:200]
            loi += 1
        job.save()
    return {"da": da, "loi": loi}


def can_xao(item: dict) -> bool:
    """Item hang doi duoc xao tu dong? CHI khi xao == "cho" (IDEA-020): item dang xao,
    da xao hay loi khong bi xao lai boi _xao_pending (tranh goi AI trung)."""
    return (item or {}).get("xao") == "cho"


# ------------------------------------------------------------------ kho
class AiLabStore:
    """data/ai_lab.json: cfg (co API key - khong in ra log) + rows + templates + ui.

    ``ui`` (lan 4): {"kich_ban": bool, "job": str} — tuy chon giao dien tab Quet bai;
    doc qua thuoc tinh ``self.ui`` sau load(); ghi qua tham so ``ui`` cua save().
    """

    def __init__(self, path: str = LAB_STORE):
        self.path = path
        self.ui: dict = {}

    def load(self) -> tuple:
        try:
            with open(self.path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            return ai.AiConfig(), [], []
        cfg = ai.AiConfig.from_dict(raw.get("cfg") or {})
        rows = [chuan_hoa(r) for r in (raw.get("rows") or []) if isinstance(r, dict)]
        tpl = [t for t in (raw.get("templates") or []) if isinstance(t, dict)]
        self.ui = dict(raw.get("ui") or {}) if isinstance(raw.get("ui"), dict) else {}
        return cfg, rows, tpl

    def save(self, cfg: ai.AiConfig, rows: list, templates: list, ui: Optional[dict] = None) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        if ui is not None:
            self.ui = dict(ui)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"cfg": cfg.to_dict(), "rows": list(rows), "templates": list(templates),
                       "ui": dict(self.ui)}, fh, ensure_ascii=False, indent=1)
