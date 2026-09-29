"""Nhan dien fanpage tu ID, dung phien dang nhap cua mot acc.

Vi sao khong hoi Graph API: duong dang qua Business Suite khong co token nao ca,
chi co cookie cua acc -- ma cookie thi da nam san trong bang. Goi thang Facebook
bang cookie do roi doc ten trang ra, du de nguoi dung yen tam minh go dung ID
truoc khi mo Business Suite.

Ten trang KHONG nam o the ``<title>``: Facebook luon tra ve "Facebook" o do roi
mo ten bang JavaScript. No nam trong mot cuc JSON nhung trong trang, o khoa
``delegate_page`` -- da do voi nhieu ID khac nhau va deu dung.

Cung phai gui du bo header cua mot trinh duyet that. Thieu ``Accept`` hay
``Sec-Fetch-*`` la Facebook tra ve HTTP 400 (da do).
"""

from __future__ import annotations

import html
import json
import re
from typing import Optional

import requests

TIMEOUT = 25
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:154.0) "
      "Gecko/20100101 Firefox/154.0")

#: Facebook tu choi request khong giong trinh duyet -> gui du bo header nay.
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

PAGE_URL = "https://www.facebook.com/{page_id}"

#: Cho ten trang that su nam. Thu lan luot tu cho chac an nhat.
_PATTERNS = (
    re.compile(r'"delegate_page":\{[^{}]*"name":"((?:[^"\\]|\\.){1,120})"'),
    re.compile(r'"page":\{[^{}]*"name":"((?:[^"\\]|\\.){1,120})"'),
    re.compile(r'<meta property="og:title" content="([^"]{1,120})"'),
)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def cookies_from(raw: str) -> dict:
    """Doc chuoi cookie da luu trong bang thanh dang requests hieu duoc.

    Nhan ca hai kieu nguoi dung hay dan: ``ten=gia_tri; ten2=gia_tri2`` va JSON.
    """
    text = (raw or "").strip()
    if not text:
        return {}
    if text.startswith("["):
        try:
            return {c["name"]: c["value"] for c in json.loads(text)
                    if isinstance(c, dict) and c.get("name")}
        except (ValueError, KeyError, TypeError):
            return {}
    out = {}
    for phan in text.split(";"):
        ten, sep, gia_tri = phan.partition("=")
        if sep and ten.strip():
            out[ten.strip()] = gia_tri.strip()
    return out


def _decode(raw: str) -> str:
    """Doi chuoi trong JSON nhung (``\\u1ea1``, ``\\/``) ve chu binh thuong."""
    try:
        return json.loads('"' + raw + '"')
    except ValueError:
        return html.unescape(raw.replace("\\/", "/"))


def extract_name(page_html: str) -> Optional[str]:
    """Rut ten trang ra khoi HTML. None neu khong thay."""
    for mau in _PATTERNS:
        found = mau.search(page_html or "")
        if found:
            ten = _decode(found.group(1)).strip()
            if ten and ten.lower() != "facebook":
                return ten
            if ten:
                return ten          # trang ten dung la "Facebook" thi van nhan
    return None


def detect_name(page_id: str, cookie: str) -> tuple[Optional[str], str]:
    """Ten cua fanpage co ID nay. Tra ve ``(ten, loi)`` -- ten la None neu hong.

    Khong nem loi: ham nay chay o luong nen cua giao dien, bao loi bang chuoi de
    hien thang len man hinh.
    """
    ma = str(page_id or "").strip()
    if not ma:
        return None, "Chưa nhập ID fanpage."
    jar = cookies_from(cookie)
    if "c_user" not in jar:
        return None, "Acc chưa có cookie đăng nhập."

    try:
        answer = requests.get(PAGE_URL.format(page_id=ma), cookies=jar,
                              headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        return None, f"Không gọi được Facebook: {exc}"
    if answer.status_code >= 400:
        return None, f"Facebook trả về HTTP {answer.status_code}"

    body = answer.text or ""
    ten = extract_name(body)
    if ten:
        return ten, ""

    # Khong thay ten -> doan xem vi sao, de bao cho dung.
    found = _TITLE.search(body)
    tieu_de = html.unescape(re.sub(r"\s+", " ", found.group(1))).strip().lower() if found else ""
    if "log in" in tieu_de or "đăng nhập" in tieu_de:
        return None, "Cookie của acc đã hết hạn — đăng nhập lại rồi lưu cookie mới."
    if "content not found" in body.lower() or "nội dung không có sẵn" in body.lower():
        return None, f"Không tìm thấy trang có ID {ma}."
    return None, "Không đọc được tên trang (có thể ID không phải fanpage)."

#: Trang Business Suite -- doc ra fanpage ma acc dang quan ly.
BUSINESS_HOME = "https://business.facebook.com/latest/home"
#: Cac cho co the lo ra id fanpage trong trang Business Suite.
#:
#: Chi dung ``localScopes`` thi CHI RA DUNG PAGE DANG CHON -- da do: doi
#: page trong trinh duyet thi danh sach doi theo. Phai gom them cac cho khac
#: moi thay du cac fanpage acc quan ly.
_ID_SOURCES = (
    re.compile(r'\{"id":"(\d{10,})","type":"PAGE"\}'),
    re.compile(r'"asset_id":"?(\d{10,})'),
    re.compile(r'asset_id=(\d{10,})'),
)

#: Mot chuoi JSON: ky tu thuong hoac ky tu duoc thoat bang dau gach cheo nguoc.
_JSON_STR = r'((?:[^"\\]|\\.){1,80})'


def _name_of(page_id: str, body: str) -> str:
    """Tim ten cua mot id trong dong JSON cua trang."""
    ma = re.escape(page_id)
    for mau in ('"name":"' + _JSON_STR + '","id":"' + ma + '"',
                '"id":"' + ma + '","name":"' + _JSON_STR + '"'):
        found = re.search(mau, body)
        if found:
            return _decode(found.group(1)).strip()
    return ""


def list_managed_pages(cookie: str) -> tuple[list, str]:
    """Cac fanpage acc nay quan ly duoc trong Business Suite.

    Tra ve ``([{"id":..., "name":...}], loi)``. Danh sach rong thi doc ``loi``.

    Vi sao can: ``asset_id`` tren duong dan Business Suite phai la fanpage acc do
    THAT SU quan ly. Go nham mot id khac -- vi du id trang ca nhan kieu moi cua
    chinh acc -- thi Facebook bao "Sorry, this content isn't available right now"
    chu khong noi ro sai o dau. Lay san danh sach cho nguoi dung chon thi khong
    con go nham.
    """
    jar = cookies_from(cookie)
    if "c_user" not in jar:
        return [], "Acc chưa có cookie đăng nhập."
    try:
        answer = requests.get(BUSINESS_HOME, cookies=jar, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        return [], f"Không gọi được Facebook: {exc}"
    if answer.status_code >= 400:
        return [], f"Facebook trả về HTTP {answer.status_code}"

    body = answer.text or ""
    ids = []
    for mau in _ID_SOURCES:
        for ma in mau.findall(body):
            if ma not in ids:
                ids.append(ma)
    if not ids:
        if "login" in (answer.url or "") or "log in" in body[:4000].lower():
            return [], "Cookie của acc đã hết hạn — đăng nhập lại rồi lưu cookie mới."
        return [], "Acc này chưa quản lý fanpage nào trong Business Suite."

    # Ten nam ngay trong trang cho page dang chon; page khac thi phai hoi rieng.
    ra = []
    for ma in ids:
        ten = _name_of(ma, body)
        if not ten:
            ten = detect_name(ma, cookie)[0] or ""
        ra.append({"id": ma, "name": ten or ma})
    return ra, ""

# ---------------------------------------------------------------- quy doi ID

#: Cac cho co the chua ID trong mot duong dan da dan vao.
_ID_IN_URL = [
    re.compile(r"[?&]asset_id=(\d+)"),
    re.compile(r"[?&]page_id=(\d+)"),
    re.compile(r"profile\.php\?id=(\d+)"),
    re.compile(r"facebook\.com/(\d{5,})"),
]
#: Ten trang dang chu, vd facebook.com/ten-trang
_SLUG_IN_URL = re.compile(r"facebook\.com/([A-Za-z0-9\.\-]{3,60})")


def parse_page_id(text: str) -> str:
    """Rut ID (hoac ten trang) ra khoi thu nguoi dung dan vao.

    Nhan ca ID tran lan duong dan: link trang cong khai
    (``facebook.com/profile.php?id=...``), link Business Suite
    (``...?page_id=...&asset_id=...``), hay link dang ten
    (``facebook.com/ten-trang``).
    """
    raw = (text or "").strip()
    if not raw:
        return ""
    if raw.isdigit():
        return raw
    for mau in _ID_IN_URL:
        found = mau.search(raw)
        if found:
            return found.group(1)
    found = _SLUG_IN_URL.search(raw)
    if found:
        ten = found.group(1)
        # Bo cac duong dan khong phai trang: /latest/..., /profile.php...
        if ten.lower() not in ("latest", "profile.php", "pages", "groups", "watch"):
            return ten
    return raw


def resolve_asset_id(page_id: str, cookie: str) -> tuple[str, str, str]:
    """Doi ID cong khai cua fanpage thanh ID ma Business Suite dung.

    Tra ve ``(asset_id, ten, loi)``.

    Vi sao phai doi: MOT fanpage co HAI so khac nhau. Link cong khai dung mot so
    (vd facebook.com/profile.php?id=61593719316375), con Business Suite dung so
    khac (asset_id=1249952574873262). Dan so cong khai vao Business Suite thi chi
    nhan lai trang "Sorry, this content isn't available right now" -- da do ca hai
    so tren cung mot trang va deu ra ten "Hoang linh chi", nhung chi so cua
    Business Suite mo duoc composer.

    Cach doi: lay danh sach fanpage acc quan ly (deu la so cua Business Suite);
    neu so nguoi dung dan khong nam trong do thi doi chieu bang TEN trang.
    """
    ma = parse_page_id(page_id)
    if not ma:
        return "", "", "Chưa nhập ID hoặc link fanpage."

    pages, loi = list_managed_pages(cookie)
    if not pages:
        return "", "", loi

    for page in pages:
        if page["id"] == ma:
            return page["id"], page["name"], ""     # da dung so cua Business Suite

    ten, loi_ten = detect_name(ma, cookie)
    if ten:
        khop = [p for p in pages if p["name"].strip().lower() == ten.strip().lower()]
        if len(khop) == 1:
            return khop[0]["id"], khop[0]["name"], ""
        if len(khop) > 1:
            return "", "", (f"Acc có {len(khop)} fanpage cùng tên \"{ten}\" — "
                            "hãy bấm 'Fanpage của acc' rồi chọn đúng cái.")

    ds = ", ".join(f"{p['name']} ({p['id']})" for p in pages[:5])
    return "", "", (f"Acc này không quản lý fanpage nào khớp với {ma}."
                    + chr(10) * 2 + f"Acc đang quản lý: {ds}")

GROUP_URL = "https://www.facebook.com/groups/{group_id}"


def detect_group_name(group_id: str, cookie: str) -> tuple:
    """Ten cua mot nhom. Tra ve ``(ten, loi)`` -- ten la None neu khong doc duoc.

    Khac fanpage: ten nhom NAM O THE ``<title>`` (fanpage thi title luon la
    "Facebook", ten that nam trong cuc JSON). Da do tren nhom cong khai that.

    Title tra ve dung chu "Facebook" nghia la khong xem duoc -- nhom kin ma acc
    chua tham gia, hoac go sai dinh danh.
    """
    ma = str(group_id or "").strip()
    if not ma:
        return None, "Chưa nhập link nhóm."
    jar = cookies_from(cookie)
    if "c_user" not in jar:
        return None, "Acc chưa có cookie đăng nhập."
    try:
        answer = requests.get(GROUP_URL.format(group_id=ma), cookies=jar,
                              headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        return None, f"Không gọi được Facebook: {exc}"
    if answer.status_code >= 400:
        return None, f"Facebook trả về HTTP {answer.status_code}"

    body = answer.text or ""
    found = _TITLE.search(body)
    ten = html.unescape(re.sub(r"\s+", " ", found.group(1))).strip() if found else ""
    for duoi in (" | Facebook", " - Facebook", " – Facebook"):
        if ten.endswith(duoi):
            ten = ten[: -len(duoi)].strip()
    thap = ten.lower()
    if not ten or thap == "facebook":
        return None, ("Không đọc được tên nhóm — nhóm kín mà acc chưa tham gia, "
                      "hoặc link không đúng.")
    if "log in" in thap or "đăng nhập" in thap:
        return None, "Cookie của acc đã hết hạn."
    return ten, ""

