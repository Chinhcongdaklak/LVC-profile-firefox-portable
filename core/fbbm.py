"""Add fanpage vào Business Manager (BM) theo ID BM + định dạng TXT 5 cột.

Tách tầng: file này KHÔNG import UI. Điều khiển business.facebook.com qua PROCESS-SCRIPT
AGENT (mở Firefox bình thường, KHÔNG BiDi) — cần sự kiện tin cậy và tránh chống bot.
Bridge riêng: lệnh ghi ``<profile>/qlfp-bm.json``, agent báo ``qlfp-bm-result.json``.
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

#: URL trang Cài đặt > Trang của một BM (điền business_id).
BM_URL = "https://business.facebook.com/latest/settings/pages?business_id={bm_id}"
CMD_NAME = "qlfp-bm.json"
RESULT_NAME = "qlfp-bm-result.json"


class FbBmError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Định dạng TXT 5 cột
# --------------------------------------------------------------------------
def dong_txt(uid: str, link: str, ten: str, bm_id: str = "", bm_ten: str = "") -> str:
    """Một dòng TXT: ``uid acc | link fanpage | tên fanpage | ID BM | name ID BM``.

    Các ô trống vẫn giữ chỗ để cột luôn thẳng hàng. Dấu ``|`` trong dữ liệu -> khoảng trắng."""
    def sach(x: str) -> str:
        return str(x or "").replace("|", " ").replace("\n", " ").strip()
    return "|".join([sach(uid), sach(link), sach(ten), sach(bm_id), sach(bm_ten)])


# --------------------------------------------------------------------------
# Cầu nối file cho agent business.facebook.com (bridge qlfpbm:*)
# --------------------------------------------------------------------------
def _clear(profile_dir: str) -> None:
    for name in (CMD_NAME, RESULT_NAME):
        try:
            os.remove(os.path.join(profile_dir, name))
        except OSError:
            pass


def _put_cmd(profile_dir: str, cmd: dict) -> None:
    path = os.path.join(profile_dir, CMD_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cmd, fh, ensure_ascii=False)
    os.replace(tmp, path)


def _read_result(profile_dir: str) -> Optional[dict]:
    try:
        with open(os.path.join(profile_dir, RESULT_NAME), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _cho_state(profile_dir: str, muon: set, timeout: float, log) -> Optional[dict]:
    deadline = time.time() + timeout
    seen_last = ""
    while time.time() < deadline:
        r = _read_result(profile_dir)
        if r:
            st = r.get("state")
            if st == "seen":
                det = str(r.get("detail") or "")
                if det and det != seen_last:
                    seen_last = det
                    log(f"  · {det[:140]}")
            elif st in muon:
                return r
        time.sleep(1.0)
    return None


#: URL trang "Trang bạn quản lý" của một acc (liệt kê page acc sở hữu).
PAGES_URL = "https://www.facebook.com/pages/?category=your_pages"


#: Trang "Trang bạn quản lý" gắn tên page sau nhãn ảnh đại diện -> phải bỏ đi mới ra TÊN thật
#: (bản ghi tay: người dùng gõ "Avery Rose", không phải "Ảnh đại diện của Avery Rose").
_TIEN_TO_TEN = ("Ảnh đại diện của ", "Profile picture of ", "Ảnh bìa của ")


def ten_page_sach(name: str) -> str:
    """Tên page thật: bỏ tiền tố nhãn ảnh đại diện/ảnh bìa mà FB gắn trong aria-label."""
    s = (name or "").strip()
    for p in _TIEN_TO_TEN:
        if s.startswith(p):
            s = s[len(p):].strip()
    return s


def _listpages_agent(manager, account, profile: str, log) -> list:
    """Bảo agent mở trang Pages của acc, đọc danh sách page sở hữu. Khớp nối (thước thay)."""
    manager.launch(account, url=PAGES_URL)
    _put_cmd(profile, {"action": "listpages"})
    r = _cho_state(profile, {"pages"}, timeout=60.0, log=log)
    if not r or r.get("state") != "pages":
        return []
    out = []
    for it in (r.get("items") or []):
        if isinstance(it, dict) and it.get("id"):
            out.append({"id": str(it["id"]), "name": ten_page_sach(str(it.get("name", "")))})
    return out


def liet_ke_page(manager, account, *,
                 log: Optional[Callable[[str], None]] = None) -> list:
    """Liệt kê page acc SỞ HỮU (để chọn page có sẵn add vào BM). Không ném -> [] khi lỗi."""
    noi = log or (lambda _m: None)
    profile = manager.profile_dir(account)
    try:
        manager.close(account, wait=6.0)
    except OSError:
        pass
    manager.configure(account)
    _clear(profile)
    noi(f"[{account.id}] đọc danh sách page acc sở hữu...")
    ds = _listpages_agent(manager, account, profile, noi)
    if not ds:
        # Đã gặp thật: trang your_pages thỉnh thoảng chưa kịp render -> 0 page (flake). Thử lại 1 lần.
        noi(f"[{account.id}] 0 page — thử lại một lần...")
        try:
            manager.close(account, wait=6.0)
        except OSError:
            pass
        _clear(profile)
        ds = _listpages_agent(manager, account, profile, noi)
    try:
        manager.close(account, wait=6.0)
    except OSError:
        pass
    _clear(profile)
    # Chuẩn hoá tên ở đây nữa (idempotent) để dù khớp nối bị thay vẫn ra TÊN thật.
    ds = [{"id": str(x.get("id", "")), "name": ten_page_sach(str(x.get("name", "")))}
          for x in ds if isinstance(x, dict) and x.get("id")]
    noi(f"[{account.id}] thấy {len(ds)} page.")
    return ds


#: URL Cài đặt > Trang KHÔNG kèm business_id -> FB tự mở BM mặc định của acc (đọc id từ URL).
BM_DEFAULT_URL = "https://business.facebook.com/latest/settings/pages"


def _listbm_agent(manager, account, profile: str, log) -> list:
    """Bảo agent mở Cài đặt BM (không business_id), đọc business_id + tên BM. Khớp nối (thước thay)."""
    manager.launch(account, url=BM_DEFAULT_URL)
    _put_cmd(profile, {"action": "listbm"})
    r = _cho_state(profile, {"bms"}, timeout=60.0, log=log)
    if not r or r.get("state") != "bms":
        return []
    out = []
    for it in (r.get("items") or []):
        if isinstance(it, dict) and it.get("id"):
            out.append({"id": str(it["id"]), "name": str(it.get("name", ""))})
    return out


def liet_ke_bm(manager, account, *,
               log: Optional[Callable[[str], None]] = None) -> list:
    """Liệt kê BM acc QUẢN LÝ (id + tên) để tự điền ID BM. 1 acc có thể nhiều BM.

    Không ném -> [] khi lỗi. Ưu tiên BM mặc định (cái đầu)."""
    noi = log or (lambda _m: None)
    profile = manager.profile_dir(account)
    try:
        manager.close(account, wait=6.0)
    except OSError:
        pass
    manager.configure(account)
    _clear(profile)
    noi(f"[{account.id}] quét ID BM acc quản lý...")
    ds = _listbm_agent(manager, account, profile, noi)
    try:
        manager.close(account, wait=6.0)
    except OSError:
        pass
    _clear(profile)
    noi(f"[{account.id}] thấy {len(ds)} BM.")
    return ds


def _bmpages_agent(manager, account, profile: str, bm_id: str, tens: list, log) -> Optional[dict]:
    """Bảo agent mở Cài đặt > Trang của BM, đọc tên page nào (trong ``tens``) ĐÃ có. Khớp nối (thước thay).

    Trả dict agent ``{co:[], thieu:[], ten_bm, rong}`` hoặc None khi hết giờ."""
    manager.launch(account, url=BM_URL.format(bm_id=bm_id))
    _put_cmd(profile, {"action": "bmpages", "tens": list(tens)})
    r = _cho_state(profile, {"bmpages"}, timeout=60.0, log=log)
    return r if r and r.get("state") == "bmpages" else None


def page_da_co_trong_bm(manager, account, bm_id: str, tens: list, *,
                        log: Optional[Callable[[str], None]] = None) -> dict:
    """Đọc BM xem page nào (theo TÊN) ĐÃ nằm trong BM để BỎ QUA, chỉ add page khác.

    Trả ``{biet, co:set, ten_bm}``; ``biet=False`` khi không đọc được (coi như chưa có gì)."""
    noi = log or (lambda _m: None)
    bm_id = (bm_id or "").strip()
    tens = [ten_page_sach(str(t)) for t in (tens or []) if str(t or "").strip()]
    if not bm_id or not tens:
        return {"biet": False, "co": set(), "ten_bm": ""}
    profile = manager.profile_dir(account)
    try:
        manager.close(account, wait=6.0)
    except OSError:
        pass
    manager.configure(account)
    _clear(profile)
    noi(f"[{account.id}] đọc BM {bm_id}: page nào đã có sẵn...")
    r = _bmpages_agent(manager, account, profile, bm_id, tens, noi)
    try:
        manager.close(account, wait=6.0)
    except OSError:
        pass
    _clear(profile)
    if r is None:
        noi(f"[{account.id}] không đọc được danh sách page của BM — coi như chưa có, add hết.")
        return {"biet": False, "co": set(), "ten_bm": ""}
    co = {ten_page_sach(str(t)) for t in (r.get("co") or [])}
    noi(f"[{account.id}] BM “{r.get('ten_bm', '')}” đã có {len(co)}/{len(tens)} page"
        + (": " + ", ".join(sorted(co)) if co else ""))
    return {"biet": True, "co": co, "ten_bm": str(r.get("ten_bm") or "")}


#: Trang Home cua Business Suite — noi co nut switcher de "Tao trang quan ly tai san doanh nghiep".
BM_HOME_URL = "https://business.facebook.com/latest/home"


def _taobm_agent(manager, account, profile: str, email: str, log) -> dict:
    """Bao agent mo Business Home, tao BM (dien ten acc + Ten/Ho + email). Tra dict cua agent. Khong nem."""
    manager.launch(account, url=BM_HOME_URL)
    _put_cmd(profile, {"action": "taobm", "email": str(email or ""), "acc_id": str(account.id)})
    r = _cho_state(profile, {"taobm-done"}, timeout=120.0, log=log)
    return r or {"state": "taobm-done", "ok": False, "bm_id": "", "detail": "hết giờ, agent chưa báo"}


def tao_bm(manager, account, *, email: str = "",
           log: Optional[Callable[[str], None]] = None) -> dict:
    """Tao MOT BM (tai san doanh nghiep) cho acc: ten BM = ten acc FB (agent doc), Email = ``email``
    (recovery_mail), Ten/Ho tach tu ten FB. Tra ``{ok, bm_id, ten_bm, detail}``. Khong nem."""
    noi = log or (lambda _m: None)
    profile = manager.profile_dir(account)
    try:
        manager.close(account, wait=6.0)
    except OSError:
        pass
    manager.configure(account)
    _clear(profile)
    noi(f"[{account.id}] tạo BM mới (email {email or '—'})...")
    r = _taobm_agent(manager, account, profile, email, noi)
    try:
        manager.close(account, wait=8.0)
    except OSError:
        pass
    _clear(profile)
    ok = bool(r.get("ok")) and r.get("state") == "taobm-done"
    bm_id = str(r.get("bm_id") or "")
    ten_bm = str(r.get("ten_bm") or "")
    detail = str(r.get("detail") or "")
    noi(f"[{account.id}] tạo BM: {'THÀNH CÔNG BM ' + bm_id if ok and bm_id else 'CHƯA XONG'} — {detail}")
    return {"ok": ok and bool(bm_id), "bm_id": bm_id, "ten_bm": ten_bm, "detail": detail}


def _addbm_agent(manager, account, profile: str, bm_id: str, page_id: str,
                 page_ten: str, log) -> dict:
    """Bảo agent mở BM settings, đọc tên BM, thêm page. Trả dict kết quả của agent.

    Phần trình duyệt thật; thước offline (bm02) thay hàm này. Không ném."""
    _put_cmd(profile, {"action": "addbm", "bm_id": str(bm_id),
                       "page_id": str(page_id), "page_ten": str(page_ten or "")})
    r = _cho_state(profile, {"addbm-done"}, timeout=90.0, log=log)
    return r or {"state": "addbm-done", "ok": False, "detail": "hết giờ, agent chưa báo"}


# --------------------------------------------------------------------------
# Add page vào BM
# --------------------------------------------------------------------------
def add_page_vao_bm(manager, account, bm_id: str, page_id: str, *,
                    page_ten: str = "", kiem_da_co: bool = False,
                    log: Optional[Callable[[str], None]] = None) -> dict:
    """Mở Business Manager ``bm_id`` bằng acc, thêm page ``page_id`` vào, đọc tên BM.

    Trả ``{ok, ten_bm, detail, bo_qua}``. Không ném. ``bm_id``/``page_id`` trống -> ok=False.
    ``kiem_da_co=True`` (cần ``page_ten``): đọc BM trước, page đã có -> BỎ QUA (ok=True, bo_qua=True)."""
    noi = log or (lambda _m: None)
    bm_id = (bm_id or "").strip()
    page_id = (page_id or "").strip()
    if not bm_id or not page_id:
        return {"ok": False, "ten_bm": "", "detail": "thiếu ID BM hoặc page_id", "bo_qua": False}
    if kiem_da_co and (page_ten or "").strip():
        dc = page_da_co_trong_bm(manager, account, bm_id, [page_ten], log=noi)
        if ten_page_sach(page_ten) in dc["co"]:
            noi(f"[{account.id}] page “{page_ten}” ĐÃ có trong BM “{dc['ten_bm']}” -> bỏ qua.")
            return {"ok": True, "ten_bm": dc["ten_bm"], "detail": "đã có trong BM, bỏ qua", "bo_qua": True}
    profile = manager.profile_dir(account)
    try:
        manager.close(account, wait=6.0)
    except OSError:
        pass
    manager.configure(account)
    _clear(profile)
    noi(f"[{account.id}] mở BM {bm_id}, thêm page {page_id}...")
    manager.launch(account, url=BM_URL.format(bm_id=bm_id))

    r = _addbm_agent(manager, account, profile, bm_id, page_id, page_ten, noi)
    try:
        manager.close(account, wait=8.0)
    except OSError:
        pass
    _clear(profile)

    ten_bm = str(r.get("ten_bm") or "")
    st = r.get("state")
    ok = bool(r.get("ok")) and st == "addbm-done"
    detail = str(r.get("detail") or "")
    noi(f"[{account.id}] add BM: {'THÀNH CÔNG' if ok else 'CHƯA XONG'} "
        f"(BM “{ten_bm}”) — {detail}")
    return {"ok": ok, "ten_bm": ten_bm, "detail": detail, "bo_qua": False}


def add_het_page_vao_bm(manager, account, bm_id: str, *,
                        log: Optional[Callable[[str], None]] = None) -> dict:
    """Add TẤT CẢ page acc sở hữu vào BM ``bm_id`` (thêm bằng TÊN từng page).

    ĐIỀU KIỆN: page ĐÃ có trong BM (đọc BM trước, so TÊN) -> BỎ QUA, chỉ add page khác.
    Trả ``{bm_id, tong, ok, bo_qua, rows:[{page_id, page_ten, ok, bo_qua, ten_bm}]}``. Không ném.
    ``bm_id`` trống -> không làm gì (ok=0). ``ok`` chỉ đếm page THỰC SỰ add."""
    noi = log or (lambda _m: None)
    bm_id = (bm_id or "").strip()
    if not bm_id:
        noi(f"[{account.id}] chưa có ID BM -> bỏ qua.")
        return {"bm_id": "", "tong": 0, "ok": 0, "bo_qua": 0, "rows": []}
    pages = liet_ke_page(manager, account, log=noi)
    da_co = page_da_co_trong_bm(manager, account, bm_id,
                                [p.get("name", "") for p in pages], log=noi)
    con = [p for p in pages if ten_page_sach(p.get("name", "")) not in da_co["co"]]
    noi(f"[{account.id}] có {len(pages)} page, đã có trong BM {len(pages) - len(con)}, "
        f"add {len(con)} page vào BM {bm_id}...")
    rows, ok, bo_qua = [], 0, 0
    for pg in pages:
        ten = pg.get("name", "")
        if ten_page_sach(ten) in da_co["co"]:
            bo_qua += 1
            noi(f"[{account.id}] page “{ten}” đã có trong BM -> bỏ qua.")
            rows.append({"page_id": pg["id"], "page_ten": ten, "ok": True, "bo_qua": True,
                         "ten_bm": da_co["ten_bm"]})
            continue
        kq = add_page_vao_bm(manager, account, bm_id, pg["id"], page_ten=ten, log=noi)
        r = {"page_id": pg["id"], "page_ten": ten, "ok": bool(kq.get("ok")),
             "bo_qua": False, "ten_bm": kq.get("ten_bm", "")}
        rows.append(r)
        if r["ok"]:
            ok += 1
    noi(f"[{account.id}] add {ok}/{len(con)} page vào BM {bm_id} (bỏ qua {bo_qua} page đã có).")
    return {"bm_id": bm_id, "tong": len(pages), "ok": ok, "bo_qua": bo_qua, "rows": rows}
