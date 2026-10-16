"""Dang MOT video len YouTube (YouTube Studio) qua trinh duyet.

Cung khuon core/xpost.py (dang bai X) va core/fbbusiness.upload:
  1. Dong Firefox cua acc, lam moi agent (manager.configure).
  2. Ghi lenh vao <profile>/qlfp-ytpost.json (duong dan video + tieu de + mo ta).
  3. Mo Firefox BINH THUONG vao https://www.youtube.com/upload (Studio tu mo hop tai len).
  4. Agent core/assets/ytpost_agent.js gan file, dien tieu de, chon "khong danh cho
     tre em", bam Tiep den man Che do hien thi, chon Cong khai, bam Xuat ban;
     bao trang thai ve qlfp-ytpost-result.json. Ham nay poll file do.
  5. Dong Firefox. Thanh cong tra chuoi mo ta; hong nem fbupload.UploadError.

Loi tra ve dung cac MOC cua core/autoup de bo may thu lai / tam dung acc:
  - acc chua dang nhap Google -> chuoi chua LOGOUT_MARK ("ĐĂNG XUẤT")
  - YouTube chan tai len       -> chuoi chua GIOI_HAN_MARK
  - da bam Xuat ban ma khong ro -> coi nhu DA len (khong thu lai keo trung)
Ham THUAN (ket_luan, mime_of, tieu_de_mo_ta) tach rieng de test khong can trinh duyet.
"""
from __future__ import annotations

import json
import mimetypes
import os
import time
from typing import Callable, Optional, Tuple

from . import fbupload
from . import procutil
from .autoup import GIOI_HAN_MARK, LOGOUT_MARK, STUCK_MARK, VIDEO_TU_CHOI_MARK

CMD_NAME = "qlfp-ytpost.json"
RESULT_NAME = "qlfp-ytpost-result.json"
#: Mo trang nay la Studio tu bat hop "Tai video len" (khong can biet ID kenh).
YT_UPLOAD_URL = "https://www.youtube.com/upload"
YT_STUDIO_URL = "https://studio.youtube.com/"

#: Tieu de YouTube toi da 100 ky tu, mo ta 5000, TONG the tag 500 ky tu.
TIEU_DE_TOI_DA = 100
MO_TA_TOI_DA = 4900
TAG_TOI_DA = 480

#: Trang thai KET THUC ma agent co the bao.
XONG = ("post-done", "publish-timeout", "dry-done")
HONG = ("publish-error", "no-upload-dialog", "file-error", "upload-stuck")
ACC_LOI = ("yt-login",)

BROWSER_GONE = "browser-gone"


# --- ham THUAN --------------------------------------------------------------

def mime_of(path: str) -> str:
    mime, _ = mimetypes.guess_type(path or "")
    return mime or "video/mp4"


def cat_tieu_de(chu: str) -> str:
    """Cat mot chuoi thanh tieu de YouTube hop le (<=100 ky tu, cat o RANH GIOI TU). THUAN."""
    chu = " ".join(str(chu or "").split()).strip()
    if not chu:
        return ""
    sach = chu.replace("<", "").replace(">", "")      # YouTube tu choi "<" va ">"
    if len(sach) <= TIEU_DE_TOI_DA:
        return sach
    cat = sach[:TIEU_DE_TOI_DA]
    ngan = cat.rsplit(" ", 1)[0].strip()
    return ngan if len(ngan) >= 10 else cat.strip()


def tach_tag(text: str) -> list:
    """Noi dung ``<ten>_tag.txt`` -> danh sach the tag.

    Nhan dau phay, xuong dong, hoac dang hashtag ("#abc #def"). Bo dau "#", bo trung
    (khong ke hoa/thuong), bo tag rong. YouTube chi nhan TONG 500 ky tu the tag nen
    cat bot tag cuoi cho vua. THUAN.
    """
    tho = str(text or "").replace("\r", "\n")
    for dau in (",", ";", "\n", "\t"):
        tho = tho.replace(dau, "\n")
    if "#" in tho:
        tho = tho.replace("#", "\n")
    ra, da_co, tong = [], set(), 0
    for t in tho.split("\n"):
        t = " ".join(t.split()).strip().strip("#").strip()
        if not t or t.lower() in da_co:
            continue
        if tong + len(t) + 1 > TAG_TOI_DA:
            break
        da_co.add(t.lower())
        ra.append(t)
        tong += len(t) + 1
    return ra


def tieu_de_mo_ta(caption: str, ten_file: str = "") -> Tuple[str, str]:
    """Tra (tieu de, mo ta) cho mot video.

    BO CUC THU MUC nguoi dung chot 06/10: ``clip.mp4`` + ``clip.png`` (thumb) +
    ``clip.txt`` (MO TA) + ``clip_tag.txt`` (the tag).
    -> TIEU DE lay tu TEN FILE (cat 100 ky tu), MO TA lay tu file .txt di kem.
    ``caption`` la chuoi job dua xuong (= noi dung .txt, khong co thi la ten file):
    neu caption trung ten file thi coi nhu KHONG co mo ta. THUAN.
    """
    ten = " ".join(os.path.splitext(os.path.basename(ten_file or ""))[0].split()).strip()
    chu = " ".join(str(caption or "").split()).strip()
    tieu_de = cat_tieu_de(ten) or cat_tieu_de(chu)
    mo_ta = "" if (not chu or chu == ten) else chu[:MO_TA_TOI_DA]
    return tieu_de, mo_ta


#: Hai kieu dang: SHORTS (video doc, ngan) va VIDEO DAI (thuong).
CD_TU_DONG = "tu_dong"
CD_SHORTS = "shorts"
CD_VIDEO = "video"
NHAN_CHE_DO = {CD_TU_DONG: "Tự động (theo video)", CD_SHORTS: "Shorts", CD_VIDEO: "Video dài"}
#: YouTube xep vao Shorts khi video DOC (cao >= rong) VA khong dai hon 3 phut.
SHORT_GIAY_TOI_DA = 180


def che_do_video(path: str, che_do: str = CD_TU_DONG, *,
                 giay: Optional[float] = None, kich_thuoc=None) -> dict:
    """Video nay dang kieu SHORTS hay VIDEO DAI.

    YouTube tu quyet dinh theo CHINH FILE (doc + <= 3 phut = Short), khong co cong tac nao
    tren Studio. Nguoi dung chon kieu la de tool dien SIEU DU LIEU cho dung (Shorts khong co
    o the tag, nen tag phai thanh hashtag; video dai thi dien o the tag that) va de BAO SOM
    khi file khong khop voi kieu da chon.

    Tra {che_do, tu_dong, ly_do, canh_bao}. ``giay``/``kich_thuoc`` tiem de test. THUAN.
    """
    from . import mp4info
    if giay is None:
        giay = mp4info.thoi_luong(path)
    if kich_thuoc is None:
        kich_thuoc = mp4info.kich_thuoc(path)
    doc = None if not kich_thuoc else kich_thuoc[1] >= kich_thuoc[0]
    ngan = None if giay is None else giay <= SHORT_GIAY_TOI_DA
    kt = f"{kich_thuoc[0]}x{kich_thuoc[1]}" if kich_thuoc else "không đọc được kích thước"
    do_dai = f"{int(giay)}s" if giay is not None else "không đọc được thời lượng"
    la_short = bool(doc) and bool(ngan)

    if che_do == CD_SHORTS:
        cb = ""
        if doc is not None and ngan is not None and not la_short:
            vi = "video NGANG" if not doc else f"dài hơn {SHORT_GIAY_TOI_DA // 60} phút"
            cb = (f"bạn chọn Shorts nhưng {vi} ({kt}, {do_dai}) — YouTube sẽ KHÔNG "
                  "xếp vào Shorts, nó thành video thường.")
        return {"che_do": CD_SHORTS, "tu_dong": False, "ly_do": f"người dùng chọn Shorts ({kt}, {do_dai})",
                "canh_bao": cb}
    if che_do == CD_VIDEO:
        cb = ""
        if la_short:
            cb = (f"bạn chọn Video dài nhưng video DỌC và chỉ {do_dai} ({kt}) — YouTube VẪN "
                  "xếp vào Shorts (nó quyết định theo file, không theo tool).")
        return {"che_do": CD_VIDEO, "tu_dong": False,
                "ly_do": f"người dùng chọn Video dài ({kt}, {do_dai})", "canh_bao": cb}
    # Tu dong: doc theo chinh file.
    if doc is None or ngan is None:
        return {"che_do": CD_VIDEO, "tu_dong": True,
                "ly_do": f"không đọc được {kt} / {do_dai} → coi như video dài", "canh_bao": ""}
    return {"che_do": CD_SHORTS if la_short else CD_VIDEO, "tu_dong": True,
            "ly_do": (f"{kt}, {do_dai} → "
                      + ("dọc và ≤3 phút = Shorts" if la_short
                         else ("ngang" if not doc else "dài hơn 3 phút") + " = video dài")),
            "canh_bao": ""}


def ket_luan(states: set, het_gio: bool) -> Optional[str]:
    """Trang thai chot tu tap trang thai agent da bao. None = cho tiep. THUAN."""
    for st in ACC_LOI + HONG + XONG:
        if st in states:
            return st
    if het_gio:
        return "het-gio"
    return None


# --- dieu phoi (can trinh duyet) --------------------------------------------

def _clear(profile_dir: str) -> None:
    for n in (CMD_NAME, RESULT_NAME):
        try:
            os.remove(os.path.join(profile_dir, n))
        except OSError:
            pass


def _put_cmd(profile_dir: str, path: str, tieu_de: str, mo_ta: str, *,
             thumb: str = "", tags: Optional[list] = None, che_do: str = CD_VIDEO,
             rieng_tu: str = "PUBLIC", tre_em: bool = False, thu: bool = False) -> None:
    # Firefox (nsIFile) chi nhan duong dan Windows dau "\\".
    path = os.path.normpath(path) if path else ""
    cmd = {
        "action": "ytpost",
        "path": path,
        "name": os.path.basename(path) if path else "",
        "mime": mime_of(path) if path else "",
        "tieu_de": tieu_de or "",
        "mo_ta": mo_ta or "",
        # Anh thumb (file anh CUNG TEN video) va the tag (<ten>_tag.txt).
        "thumb": os.path.normpath(thumb) if thumb else "",
        "thumb_mime": mime_of(thumb) if thumb else "",
        "tags": list(tags or []),
        # "shorts" = khong co o the tag -> dua tag vao mo ta dang hashtag + them #Shorts.
        # "video" = thu dien O THE TAG that truoc, hong moi lui ve hashtag.
        "che_do": che_do or CD_VIDEO,
        "rieng_tu": rieng_tu or "PUBLIC",
        "tre_em": bool(tre_em),
        "dry": bool(thu),
        # Agent tu dung sau 20 phut (video tai len + YouTube xu ly).
        "timeout": 20 * 60 * 1000,
    }
    os.makedirs(profile_dir, exist_ok=True)
    with open(os.path.join(profile_dir, CMD_NAME), "w", encoding="utf-8") as fh:
        json.dump(cmd, fh, ensure_ascii=False)


def _read_result(profile_dir: str) -> Optional[dict]:
    try:
        with open(os.path.join(profile_dir, RESULT_NAME), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _app_dir(manager, account) -> str:
    try:
        return manager.app_dir(account) or ""
    except Exception:  # noqa: BLE001
        return ""


def upload(manager, account, path: str, caption: str, *,
           timeout: float = 21 * 60.0, thu: bool = False, rieng_tu: str = "PUBLIC",
           tre_em: bool = False, url: str = "", che_do: str = CD_TU_DONG,
           log: Optional[Callable[[str], None]] = None) -> str:
    """Dang MOT video len kenh YouTube cua acc. Tra chuoi mo ta; hong nem UploadError."""
    noi = log or (lambda _m: None)
    if not path or not os.path.isfile(path):
        raise fbupload.UploadError(f"Không thấy file video: {path}")
    kind = fbupload.kind_of(path)
    if kind == "text":
        raise fbupload.UploadError("YouTube chỉ đăng được VIDEO — bài chỉ chữ không đăng được.")
    tieu_de, mo_ta = tieu_de_mo_ta(caption, path)
    if not tieu_de:
        raise fbupload.UploadError("Không có tiêu đề cho video (caption rỗng, tên file rỗng).")
    # File DI KEM cung ten video: anh thumb + <ten>_tag.txt (người dùng chốt 06/10).
    thumb = fbupload.anh_thumb(path)
    f_tag = fbupload.file_tag(path)
    tags = tach_tag(fbupload.doc_chu(f_tag)) if f_tag else []
    if not mo_ta:
        # Mo ta = noi dung <ten>.txt. Job co the da dua xuong roi; khong thi doc truc tiep.
        cap = fbupload.caption_file(path)
        if os.path.isfile(cap):
            chu = fbupload.doc_chu(cap)
            mo_ta = " ".join(chu.split())[:MO_TA_TOI_DA] if chu else ""

    if not manager.is_installed(account):
        noi(f"[{account.id}] chưa có profile YouTube — tạo...")
        manager.create(account)

    profile = manager.profile_dir(account)
    manager.close(account, wait=8.0)
    manager.configure(account)          # trien khai / lam moi agent vao profile
    _clear(profile)
    kieu = che_do_video(path, che_do)
    noi(f"[{account.id}] kiểu đăng: {NHAN_CHE_DO.get(kieu['che_do'], kieu['che_do'])} "
        f"({kieu['ly_do']})")
    if kieu["canh_bao"]:
        noi(f"[{account.id}] ⚠ {kieu['canh_bao']}")
    _put_cmd(profile, path, tieu_de, mo_ta, thumb=thumb, tags=tags, che_do=kieu["che_do"],
             rieng_tu=rieng_tu, tre_em=tre_em, thu=thu)

    noi(f"[{account.id}] mở Firefox → YouTube Studio → tải lên {os.path.basename(path)} "
        f"(tiêu đề {len(tieu_de)} ký tự"
        + (f", mô tả {len(mo_ta)} ký tự" if mo_ta else ", KHÔNG có mô tả")
        + (f", {len(tags)} thẻ tag" if tags else ", không có thẻ tag")
        + (f", thumb {os.path.basename(thumb)}" if thumb else ", KHÔNG có ảnh thumb")
        + f", {rieng_tu})")
    manager.launch(account, url or YT_UPLOAD_URL)

    # TU DAY TRO DI TRINH DUYET DA MO -> moi thu trong try/finally, khong thi mot loi
    # bat ngo la bo roi Firefox mo mai (loi that 06/10 o duong X).
    chi_tiet: dict = {}
    states: set = set()
    _seen: set = set()
    log_agent: list = []
    chot = None
    try:
        canh_ff = procutil.CanhTrinhDuyet(_app_dir(manager, account))
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = _read_result(profile)
            if r:
                # Agent ghi de MOT file ket qua moi 1.2s con cha doc 0.8s -> van co the BO LO
                # bao cao. Agent gui kem "log" (30 dong gan nhat) -> nho lai de in cuoi luot
                # (bai hoc tu agent Gmail: mat bao cao la soi mu).
                if isinstance(r.get("log"), list):
                    log_agent = r["log"]
                st = r.get("state")
                det = "" if r.get("detail") is None else str(r.get("detail"))
                if st == "seen":
                    key = "seen|" + det
                    if key not in _seen:
                        _seen.add(key)
                        noi(f"[{account.id}] seen: {det[:400]}")
                elif st in ("upload-progress", "step-next"):
                    if det and det != chi_tiet.get(st):
                        chi_tiet[st] = det
                        noi(f"[{account.id}] {st}: {det}")
                elif st and st not in states:
                    states.add(st)
                    chi_tiet[st] = det
                    noi(f"[{account.id}] {st}" + (f": {det[:400]}" if det else ""))
            chot = ket_luan(states, het_gio=False)
            if chot:
                break
            if canh_ff.da_dong():
                chot = BROWSER_GONE
                break
            time.sleep(0.8)
        if chot is None:
            chot = ket_luan(states, het_gio=True)
    finally:
        try:
            manager.close(account, wait=10.0)
        except OSError:
            pass
        _clear(profile)

    for dong in log_agent:
        d = str(dong)
        if d.split(":")[0] not in states or d.startswith("seen"):
            noi(f"[{account.id}] (agent) {d[:300]}")

    ten = os.path.basename(path)
    if chot == "dry-done":
        return chi_tiet.get("dry-done", "")
    if chot == "post-done":
        return f"đã đăng {ten} lên YouTube ({account.id}) — {chi_tiet.get('post-done', '')}"
    if chot == "publish-timeout":
        # DA bam Xuat ban -> coi nhu len roi (nhu Facebook/X), thu lai la dang trung.
        return f"đã bấm Xuất bản {ten} (không thấy xác nhận — coi như đã lên)"
    if chot == "yt-login":
        raise fbupload.UploadError(
            f"{LOGOUT_MARK}: acc {account.id} chưa đăng nhập Google/YouTube — "
            "vào tab Quản lý acc > YouTube bấm Đăng nhập Google.")
    if chot == "upload-stuck":
        pt = chi_tiet.get("upload-progress", "")
        raise fbupload.UploadError(
            f"{STUCK_MARK} — YouTube tải lên / xử lý quá lâu, chưa xuất bản được"
            + (f", lần cuối {pt}" if pt else "") + f". {chi_tiet.get('upload-stuck', '')[:200]}")
    if chot == "publish-error":
        ly_do = chi_tiet.get("publish-error", "")
        if "giới hạn" in ly_do or "daily upload limit" in ly_do.lower():
            raise fbupload.UploadError(
                f"{GIOI_HAN_MARK}: acc {account.id} — YouTube báo giới hạn tải lên trong ngày.")
        if "xử lý" in ly_do or "process" in ly_do.lower():
            raise fbupload.UploadError(
                f"{VIDEO_TU_CHOI_MARK}: YouTube không xử lý được {ten} — {ly_do[:180]}")
        raise fbupload.UploadError(f"YouTube Studio báo lỗi khi đăng {ten} — {ly_do[:200]}")
    if chot == "no-upload-dialog":
        raise fbupload.UploadError(
            "Không mở được hộp 'Tải video lên' của YouTube Studio — "
            f"{chi_tiet.get('no-upload-dialog', '')[:220]}")
    if chot == "file-error":
        raise fbupload.UploadError(
            f"Không gắn được video vào Studio: {chi_tiet.get('file-error', '')[:200]}")
    if chot == BROWSER_GONE:
        raise fbupload.UploadError("Trình duyệt bị đóng giữa chừng khi đang đăng YouTube.")
    raise fbupload.UploadError(
        "Hết giờ chờ mà chưa đăng xong YouTube "
        f"(trạng thái: {', '.join(sorted(states)) or 'không có'}).")
