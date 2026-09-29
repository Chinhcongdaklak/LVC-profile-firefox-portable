"""Dua video len fanpage bang Graph API cua Facebook.

Vi sao dung Graph API chu khong dieu khien trinh duyet: day la duong Facebook
cap san cho viec dang len page cua chinh minh -- khong phu thuoc giao dien, chay
duoc khi may dang lam viec khac, va khong dinh toi business.facebook.com (trang
tung lam crash tab trinh duyet, xem lich su du an).

Can mot ``page access token`` cho moi fanpage. Lay bang cach dan token nguoi dung
vao ``list_pages()`` -- ham do tra ve tung page kem token rieng cua no.

File nho thi day mot lan cho gon; file lon phai chia khuc, vi Facebook tu choi
mot request qua to va cung khong the bao tien do neu day mot cuc.
"""

from __future__ import annotations

import os
import re
from typing import Callable, Iterable, Optional

import requests

#: Doi phien ban o day khi Facebook khai tu ban cu.
API_VERSION = "v23.0"
GRAPH = f"https://graph.facebook.com/{API_VERSION}"
GRAPH_VIDEO = f"https://graph-video.facebook.com/{API_VERSION}"

#: Tren nguong nay thi chia khuc. Duoi thi day mot lan cho nhanh va it buoc hong.
CHUNKED_THRESHOLD = 80 * 1024 * 1024
#: Doc file theo tung mieng nay khi day, de khong nap ca video vao bo nho.
READ_BLOCK = 1024 * 1024

#: Duoi file duoc coi la video. Dung de quet thu muc.
VIDEO_SUFFIXES = (".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg")
#: Duoi file anh.
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif")
#: Bai chi co chu: moi file .txt la mot bai, noi dung file la noi dung bai.
TEXT_SUFFIXES = (".txt",)

#: Kieu MIME theo duoi file, de gan dung loai khi dua vao trinh duyet.
MIME = {
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska", ".webm": "video/webm", ".m4v": "video/x-m4v",
    ".flv": "video/x-flv", ".wmv": "video/x-ms-wmv", ".mpg": "video/mpeg",
    ".mpeg": "video/mpeg",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    ".heic": "image/heic", ".heif": "image/heif",
}


def mime_of(path: str) -> str:
    """Kieu MIME cua file, doan theo duoi. Khong biet thi tra ve kieu chung."""
    return MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


def is_image(path: str) -> bool:
    return path.lower().endswith(IMAGE_SUFFIXES)


def is_text(path: str) -> bool:
    return path.lower().endswith(TEXT_SUFFIXES)

DEFAULT_TIMEOUT = 60
UPLOAD_TIMEOUT = 600


class UploadError(Exception):
    """Khong dua duoc video len. Loi da duoc dich sang loi noi de nguoi dung doc."""


def is_video(path: str) -> bool:
    return path.lower().endswith(VIDEO_SUFFIXES)


def _explain(response: requests.Response) -> str:
    """Doi loi JSON cua Facebook thanh mot cau doc duoc.

    Facebook tra loi trong ``error.message``, doi khi kem ``error_user_msg`` de
    hien cho nguoi dung. Uu tien cai nao ro nghia hon.
    """
    try:
        error = (response.json() or {}).get("error") or {}
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:200]}"
    parts = [
        error.get("error_user_msg") or "",
        error.get("message") or "",
    ]
    text = " — ".join(p for p in parts if p) or f"HTTP {response.status_code}"
    code = error.get("code")
    return f"{text} (mã {code})" if code else text


def _post(url: str, timeout: int = DEFAULT_TIMEOUT, **kwargs) -> dict:
    try:
        response = requests.post(url, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise UploadError(f"Không gọi được Facebook: {exc}") from exc
    if response.status_code >= 400:
        raise UploadError(_explain(response))
    try:
        return response.json() or {}
    except ValueError:
        raise UploadError("Facebook trả về dữ liệu không đọc được.") from None


def _get(url: str, params: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    try:
        response = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise UploadError(f"Không gọi được Facebook: {exc}") from exc
    if response.status_code >= 400:
        raise UploadError(_explain(response))
    try:
        return response.json() or {}
    except ValueError:
        raise UploadError("Facebook trả về dữ liệu không đọc được.") from None


# ---------------------------------------------------------------- token / page

def whoami(token: str) -> dict:
    """Token nay la cua ai. Dung de kiem tra token con song khong."""
    if not (token or "").strip():
        raise UploadError("Chưa nhập token.")
    return _get(f"{GRAPH}/me", {"fields": "id,name", "access_token": token.strip()})


def list_pages(user_token: str) -> list[dict]:
    """Cac fanpage ma token nay quan ly, KEM token rieng cua tung page.

    Dan token nguoi dung vao day mot lan la lay duoc token cua moi page -- khong
    phai di lay tay tung cai. Token page lay theo duong nay song rat lau (theo
    token nguoi dung sinh ra no).
    """
    if not (user_token or "").strip():
        raise UploadError("Chưa nhập token.")
    data = _get(f"{GRAPH}/me/accounts",
                {"fields": "id,name,access_token", "limit": 200,
                 "access_token": user_token.strip()})
    pages = []
    for item in data.get("data") or []:
        if item.get("id") and item.get("access_token"):
            pages.append({
                "id": str(item["id"]),
                "name": item.get("name") or str(item["id"]),
                "token": item["access_token"],
            })
    if not pages:
        raise UploadError(
            "Token hợp lệ nhưng không quản lý fanpage nào. "
            "Kiểm tra lại token có đủ quyền pages_show_list / pages_manage_posts chưa."
        )
    return pages


# ---------------------------------------------------------------- dua video len

def upload_video(
    page_id: str,
    token: str,
    path: str,
    description: str = "",
    title: str = "",
    progress: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Dua mot video len fanpage. Tra ve id video. Hong thi nem UploadError.

    ``progress(da_gui, tong)`` duoc goi trong luc day de bao tien do.
    """
    if not (page_id or "").strip():
        raise UploadError("Chưa chọn fanpage.")
    if not (token or "").strip():
        raise UploadError("Fanpage này chưa có token.")
    if not os.path.isfile(path):
        raise UploadError(f"Không thấy file: {path}")
    size = os.path.getsize(path)
    if size <= 0:
        raise UploadError(f"File rỗng: {os.path.basename(path)}")

    if size <= CHUNKED_THRESHOLD:
        return _upload_one_shot(page_id, token, path, description, title, size, progress)
    return _upload_chunked(page_id, token, path, description, title, size, progress)


def _upload_one_shot(page_id, token, path, description, title, size, progress) -> str:
    """Day ca file trong mot request. Chi dung cho file nho."""
    data = {"access_token": token, "description": description}
    if title:
        data["title"] = title
    with open(path, "rb") as fh:
        files = {"source": (os.path.basename(path), fh, "video/mp4")}
        result = _post(f"{GRAPH_VIDEO}/{page_id}/videos", timeout=UPLOAD_TIMEOUT,
                       data=data, files=files)
    if progress:
        progress(size, size)
    video_id = result.get("id")
    if not video_id:
        raise UploadError("Facebook nhận file nhưng không trả về id video.")
    return str(video_id)


def _upload_chunked(page_id, token, path, description, title, size, progress) -> str:
    """Day theo khuc: bat dau -> gui tung khuc -> ket thuc.

    Facebook tu quyet dinh moi lan gui bao nhieu byte (start_offset/end_offset),
    minh cu bam theo con so no tra ve chu khong tu chia.
    """
    url = f"{GRAPH_VIDEO}/{page_id}/videos"
    start = _post(url, data={
        "access_token": token, "upload_phase": "start", "file_size": size,
    })
    session = start.get("upload_session_id")
    video_id = start.get("video_id")
    if not session:
        raise UploadError("Facebook không mở được phiên tải lên.")

    offset = int(start.get("start_offset") or 0)
    end = int(start.get("end_offset") or 0)
    try:
        with open(path, "rb") as fh:
            while offset < end:
                fh.seek(offset)
                chunk = fh.read(end - offset)
                if not chunk:
                    raise UploadError("File ngắn hơn kích thước đã báo với Facebook.")
                answer = _post(url, timeout=UPLOAD_TIMEOUT, data={
                    "access_token": token,
                    "upload_phase": "transfer",
                    "upload_session_id": session,
                    "start_offset": offset,
                }, files={"video_file_chunk": (os.path.basename(path), chunk)})
                offset = int(answer.get("start_offset") or 0)
                end = int(answer.get("end_offset") or offset)
                if progress:
                    progress(min(offset, size), size)
    except UploadError:
        _cancel_chunked(url, token, session)
        raise

    data = {"access_token": token, "upload_phase": "finish",
            "upload_session_id": session, "description": description}
    if title:
        data["title"] = title
    finish = _post(url, timeout=UPLOAD_TIMEOUT, data=data)
    if not finish.get("success", True):
        raise UploadError("Facebook từ chối bước kết thúc tải lên.")
    if progress:
        progress(size, size)
    return str(video_id or finish.get("video_id") or "")


def _cancel_chunked(url: str, token: str, session: str) -> None:
    """Bo phien tai do dang. Hong cung khong sao nen nuot loi."""
    try:
        requests.post(url, timeout=DEFAULT_TIMEOUT, data={
            "access_token": token, "upload_phase": "cancel",
            "upload_session_id": session,
        })
    except requests.RequestException:
        pass


# ---------------------------------------------------------------- quet thu muc

#: Tach ten file thanh doan chu va doan so, de sap xep giong Windows Explorer.
_CHUNK = re.compile(r'(\d+)')


def natural_key(name: str):
    """Khoa sap xep theo ten kieu Explorer: "Tap 2" dung truoc "Tap 10".

    So sanh tung doan: doan so thi so sanh theo GIA TRI, doan chu thi theo
    bang chu (khong phan biet hoa thuong). So sanh chuoi thuan tuy se dat
    "Tap 10" truoc "Tap 2" vi ky tu "1" nho hon "2".
    """
    parts = _CHUNK.split(name)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def find_files(folder: str, suffixes) -> list[str]:
    """Cac file co duoi trong ``suffixes``, XEP THEO TEN tu tren xuong duoi.

    Xep dung thu tu Windows Explorer hien, de nguoi dung nhin thu muc la biet cai
    nao se len truoc.
    """
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    found = []
    for name in names:
        path = os.path.join(folder, name)
        if os.path.isfile(path) and name.lower().endswith(suffixes):
            found.append(name)
    found.sort(key=natural_key)
    return [os.path.join(folder, name) for name in found]


def find_videos(folder: str) -> list[str]:
    """Cac video trong thu muc, xep theo ten."""
    return find_files(folder, VIDEO_SUFFIXES)


def find_images(folder: str) -> list[str]:
    """Cac anh trong thu muc, xep theo ten."""
    return find_files(folder, IMAGE_SUFFIXES)


def find_texts(folder: str) -> list[str]:
    """Cac file .txt trong thu muc -- moi file la mot bai chi co chu."""
    return find_files(folder, TEXT_SUFFIXES)


def find_by_kind(folder: str, kind: str) -> list[str]:
    """Danh sach file theo kieu bai: "video", "image", "text" hay "auto".

    "auto" = tu nhan dien: lay het video + anh + text, moi file dang theo dung
    loai cua no. File .txt di kem mot media cung ten la CAPTION, khong tinh la
    bai chu rieng.
    """
    if kind == "image":
        return find_images(folder)
    if kind == "text":
        return find_texts(folder)
    if kind == "auto":
        return find_all(folder)
    return find_videos(folder)


def find_all(folder: str) -> list[str]:
    """Moi file dang duoc (video, anh, text) trong thu muc, xep chung theo ten.

    Bo cac file .txt di kem media cung ten -- do la caption cho video/anh do,
    khong phai bai chi-chu rieng.
    """
    vids = find_videos(folder)
    imgs = find_images(folder)
    media_base = {os.path.splitext(p)[0].lower() for p in vids + imgs}
    texts = [t for t in find_texts(folder)
             if os.path.splitext(t)[0].lower() not in media_base]
    tat_ca = vids + imgs + texts
    tat_ca.sort(key=lambda p: natural_key(os.path.basename(p)))
    return tat_ca


def kind_of(path: str) -> str:
    """Kieu bai cua mot file, tu nhan dien theo duoi: video / image / text."""
    if is_image(path):
        return "image"
    if is_text(path):
        return "text"
    return "video"


def read_text_post(path: str) -> str:
    """Noi dung mot bai chi co chu. File rong thi tra ve rong."""
    for bang_ma in ("utf-8", "utf-8-sig", "cp1258", "latin-1"):
        try:
            with open(path, encoding=bang_ma) as fh:
                return fh.read().strip()
        except (UnicodeDecodeError, OSError):
            continue
    return ""


def is_ready(path: str, settle: float = 2.0) -> bool:
    """File da chep xong chua -- do kich thuoc hai lan cach nhau ``settle`` giay.

    Dang copy mot video 500 MB vao thu muc ma gap dung luc quet thi tool se day
    len mot file dang do. Kich thuoc con tang nghia la chua xong.
    """
    import time

    try:
        first = os.path.getsize(path)
    except OSError:
        return False
    if first <= 0:
        return False
    time.sleep(settle)
    try:
        return os.path.getsize(path) == first
    except OSError:
        return False


def caption_for(path: str, kind: str = "video", fallback_ten: bool = True) -> str:
    """Mo ta bai dang: LAY TIEU DE (ten file) lam mo ta.

    ``fallback_ten=False`` (dang NHOM): khong co caption that thi tra "" — KHONG lay ten file
    lam mo ta. Da gap: bai nhom anh khong co chu -> dang ra ten file "qb_r...._56928" (loi).

    Composer cua Business Suite khong co o "tieu de" rieng -- da do tren giao
    dien that: chi co MOT o soan chu cho ca bai. Tieu de video chinh la ten file,
    nen lay ten file lam mo ta.

    Muon mo ta khac ten file thi de mot file .txt cung ten canh video: ``clip1.mp4``
    thi doc ``clip1.txt``. Soan san bang Notepad, khong phai go lai trong tool.
    """
    from . import spintax
    base, _ = os.path.splitext(path)
    # Bai da 'xao' bang AI: caption moi nam o <base>_xao/caption.txt -> uu tien.
    xao_cap = os.path.join(base + "_xao", "caption.txt")
    if os.path.isfile(xao_cap):
        try:
            with open(xao_cap, encoding="utf-8") as fh:
                t = fh.read().strip()
            if t:
                return spintax.spin(t)
        except OSError:
            pass
    # Bai chi co chu: chinh noi dung file la noi dung bai.
    if kind == "text" or is_text(path):
        return spintax.spin(read_text_post(path))
    side = base + ".txt"
    if os.path.isfile(side):
        try:
            with open(side, encoding="utf-8") as fh:
                text = fh.read().strip()
            if text:
                # Spintax: caption co {a|b} thi moi lan dang ra mot ban khac ->
                # chong Facebook danh dau noi dung trung lap khi dang nhieu group.
                return spintax.spin(text)
        except OSError:
            pass
    # Khong tim thay caption that: dang nhom -> "" (khong lay ten file); fanpage video -> ten file (tieu de).
    if not fallback_ten:
        return ""
    return os.path.splitext(os.path.basename(path))[0]


def caption_file(path: str) -> str:
    """Duong dan file .txt di kem mot video (co the khong ton tai)."""
    base, _ = os.path.splitext(path)
    return base + ".txt"


def remove_video(path: str, with_caption: bool = True) -> list[str]:
    """Xoa file da dang xong (va file .txt di kem). Tra ve nhung gi da xoa.

    Bai chi co chu thi chinh file .txt la bai -- khong di tim file .txt "di kem"
    nua, khong thi xoa hai lan cung mot file.
    """
    removed = []
    if is_text(path):
        targets: Iterable[str] = (path,)
    else:
        targets = (path, caption_file(path)) if with_caption else (path,)
    for target in targets:
        try:
            if os.path.isfile(target):
                os.remove(target)
                removed.append(target)
        except OSError:
            pass
    return removed
