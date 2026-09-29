"""Dang video len fanpage bang cach dieu khien business.facebook.com.

Ba manh ghep, moi manh giai quyet mot thu JavaScript hoac Python don le khong
lam duoc:

  * ``core/assets/fbupload_agent.js`` chay TRONG trang, tim o chon file va bam
    vao no, roi dien mo ta. Duoc nap bang process script -- khong dung
    ``Cu.Sandbox`` vi kieu do da lam crash tab truoc day.
  * ``core/winfile.py`` go duong dan vao hop thoai "Open" cua Windows. Trang web
    khong voi toi hop thoai cua he dieu hanh duoc, chi con cach dieu khien tu
    ngoai.
  * File nay dieu phoi: dat lenh, mo trinh duyet, cho hop thoai, doi ket qua.

Trao doi voi agent qua ba file trong thu muc profile:
    qlfp-upload.json          tool ghi   -> lenh
    qlfp-upload-result.json   agent ghi  -> tien do / ket qua
    qlfp-upload-dump.json     agent ghi  -> ban do cac nut tren trang
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

from . import procutil, winfile  # noqa: F401

CMD_NAME = "qlfp-upload.json"
RESULT_NAME = "qlfp-upload-result.json"
DUMP_NAME = "qlfp-upload-dump.json"


class BusinessError(Exception):
    """Khong dang duoc qua Business Suite."""


class BusinessStuck(BusinessError):
    """Trang mo len nhung khong tai len duoc phan tram nao -- coi nhu trang hong."""


def _path(profile_dir: str, name: str) -> str:
    return os.path.join(profile_dir, name)


def clear(profile_dir: str) -> None:
    """Xoa lenh va ket qua cu. Phai goi TRUOC khi mo trinh duyet."""
    for name in (CMD_NAME, RESULT_NAME, DUMP_NAME):
        try:
            os.remove(_path(profile_dir, name))
        except OSError:
            pass


def put_command(profile_dir: str, **command) -> None:
    os.makedirs(profile_dir, exist_ok=True)
    with open(_path(profile_dir, CMD_NAME), "w", encoding="utf-8") as fh:
        json.dump(command, fh, ensure_ascii=False)


def read_result(profile_dir: str) -> Optional[dict]:
    try:
        with open(_path(profile_dir, RESULT_NAME), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def read_dump(profile_dir: str) -> Optional[dict]:
    try:
        with open(_path(profile_dir, DUMP_NAME), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


#: Giao dien Facebook dang o thu tieng KHAC vi/en -> cac buoc dang bai do sai nut.
#: Nguoi goi bat dau hieu nay de doi ngon ngu roi dang lai (nhu reauth khi logout).
LANG_MARK = "NGÔN NGỮ LẠ"
LANG_STATE = "lang-unsupported"


#: Trinh duyet da bi dong/chet giua chung (nguoi dung tat, Not Responding, crash).
BROWSER_GONE = "browser-gone"


def app_dir_cua(manager, account) -> str:
    """Thu muc app cua acc, "" neu manager khong co (manager gia trong thuoc).

    Tra "" thi phan canh tien trinh tu tat -- khong duoc lam vo nguoi goi.
    """
    try:
        return manager.app_dir(account) or ""
    except Exception:  # noqa: BLE001
        return ""


def wait_state(profile_dir: str, states, timeout: float = 90.0,
               app_dir: str = "") -> Optional[dict]:
    """Doi agent bao mot trong cac trang thai ``states``. None neu het gio.

    Co ``app_dir`` thi con canh TIEN TRINH FIREFOX cua profile do: da thay no
    chay roi ma sau do BIEN MAT (nguoi dung tat, Not Responding bi kill, crash)
    thi tra ve ngay BROWSER_GONE -- khong ngoi cho het timeout.

    Truoc day khong canh: tat Firefox luc dang video la tool treo "dang dang"
    them 15 phut (timeout mac dinh) roi moi bao "trang khong phan hoi".
    """
    muon = set(states)
    deadline = time.time() + timeout
    da_thay_browser = False
    ke_tiep = 0.0
    while time.time() < deadline:
        ket_qua = read_result(profile_dir)
        if ket_qua and ket_qua.get("state") in muon:
            return ket_qua
        # Quet tien trinh kha nang -> 3 giay mot lan la du nhay (procutil cache 1.5s).
        if app_dir and time.time() >= ke_tiep:
            ke_tiep = time.time() + 3.0
            if firefox_pids(app_dir):
                da_thay_browser = True
            elif da_thay_browser:
                return {"state": BROWSER_GONE,
                        "detail": "trình duyệt đã đóng giữa chừng "
                                  "(bị tắt tay, Not Responding, hoặc tự thoát)"}
        time.sleep(0.4)
    return None


#: Trang thai bao "chuyen cua ACC" chu khong phai tool hong. Chu HOA co chu y:
#: autoup nhan ra qua chuoi loi de dung han thay vi thu lai vo ich.
ACC_STATES = {
    "checkpoint": "ACC BỊ CHECKPOINT — Facebook giữ acc lại để xác minh",
    "logged-out": "ACC ĐÃ BỊ ĐĂNG XUẤT — cookie không còn dùng được",
}


def _ho_so(manager, account, label: str, note_text: str) -> None:
    """Thu bang chung mot lan hong. Goi TRUOC khi dong trinh duyet.

    Facebook doi giao dien thi cai ton thoi gian nhat la mo xem trang moi trong
    ra sao -- luu san anh man hinh + ban do trang thi lan sau chi viec mo
    data/hoso-loi ra xem. Hong cung mac ke: viec phu khong duoc keo do viec chinh.
    """
    from . import evidence
    try:
        evidence.capture(manager.profile_dir(account), manager.app_dir(account),
                         label, note_text,
                         files=[CMD_NAME, RESULT_NAME, DUMP_NAME])
    except Exception:
        pass


def firefox_pids(app_dir: str) -> set:
    """Cac tien trinh Firefox cua profile nay -- de tim dung hop thoai cua no."""
    return {p.pid for p in procutil.find_under(app_dir, "firefox.exe")}


def upload(
    manager,
    account,
    page_id: str,
    video_path: str,
    caption: str = "",
    publish: bool = True,
    log: Optional[Callable[[str], None]] = None,
    timeout: float = 900.0,
    stuck_timeout: float = 60.0,
    lich: Optional[dict] = None,
) -> str:
    """Mo Business Suite cua fanpage roi nap video vao composer.

    ``lich`` = {"ngay": "25/09/2026", "gio": "20:00"} (gio theo MUI GIO PAGE):
    thay vi dang ngay, agent bat che do "Đặt lịch", dien ngay/gio roi bam.
    Khong bat duoc che do dat lich -> LOI (khong bao gio dang ngay thay the:
    dang sai gio con te hon khong dang).

    Tra ve mot chuoi mo ta ket qua. Nem BusinessError neu hong.
    """
    from . import autoup, fbupload

    noi = log or (lambda _m: None)
    if not os.path.isfile(video_path):
        raise BusinessError(f"Không thấy file: {video_path}")

    profile = manager.profile_dir(account)
    manager.close(account, wait=10.0)
    clear(profile)
    # doneTimeout: agent cho toi ngan nay giay cho Facebook nhan xong bai. Video
    # nang day len lau, cat ngan qua la tat trinh duyet giua chung.
    # mime PHAI gui kem: composer moi (Bulk upload reels, 9/2026) loc file theo
    # kieu "video/*" -- gan file kieu application/octet-stream thi trang lang
    # thinh bo qua, danh sach trong tron va phan tram dung im o 0% mai.
    put_command(profile, action="upload", path=os.path.abspath(video_path),
                caption=caption, publish=bool(publish),
                mime=fbupload.mime_of(video_path),
                lich=(dict(lich) if lich else None),
                doneTimeout=int(max(60, timeout - 120)),
                stuckTimeout=int(stuck_timeout),
                readyTimeout=int(max(120, timeout / 3)))

    noi("mở Business Suite...")
    manager.launch(account, url=autoup.business_url(page_id))

    HONG = {"no-file-input", "no-path", "bad-path", "no-such-file",
            "file-api-error", "attach-error", "file-read-error", "ask-file-error",
            "caption-failed", "no-publish-button", "publish-error",
            # Khong bat duoc che do dat lich -> HONG. Tuyet doi khong dang ngay
            # thay the: bai se len sai gio, hong ca lich cua nguoi dung.
            "schedule-failed",
            "check-timeout", "error"}
    TREO = "upload-stuck"
    XONG = {"publish-done", "publish-timeout"} if publish else {"caption-filled"}
    HONG = HONG | {LANG_STATE}

    nhan_hoso = f"fanpage-{page_id}"
    try:
        xong = wait_state(profile, XONG | HONG | {TREO} | set(ACC_STATES),
                          timeout=timeout, app_dir=app_dir_cua(manager, account))
        if xong is None:
            _ho_so(manager, account, nhan_hoso, "trang không phản hồi")
            raise BusinessError("Trang Business Suite không phản hồi.")
        state = xong.get("state")
        if state == BROWSER_GONE:
            # Dung NGAY, khong cho het timeout roi moi bao.
            raise BusinessError("Trình duyệt đã đóng giữa chừng — "
                                + (xong.get("detail") or "") + ". Bài này chưa đăng.")
        if state == LANG_STATE:
            raise BusinessError(f"{LANG_MARK}: giao diện đang là "
                                f"'{xong.get('detail') or '?'}' — phải đổi sang tiếng Anh "
                                "rồi mới đăng được.")
        if state in ACC_STATES:
            # Chuyen cua acc: khong thu ho so (khong phai giao dien doi).
            raise BusinessError(ACC_STATES[state] + " — "
                                + (xong.get("detail") or ""))
        if state == TREO:
            _ho_so(manager, account, nhan_hoso, "treo 0%: "
                   + (xong.get("detail") or ""))
            raise BusinessStuck(
                "Trang bị lỗi, không tải lên được phần trăm nào — "
                + (xong.get("detail") or ""))
        if state in HONG:
            _ho_so(manager, account, nhan_hoso,
                   f"{state}: {xong.get('detail') or ''}")
            raise BusinessError(f"{state}: {xong.get('detail') or ''}".strip(": "))
        # Chong dang trung: da bam "Dang" nhung dong ho cho khong thay xac nhan
        # -> Facebook gan nhu da nhan bai (chi cham). Nem loi se khien upload_now
        # thu lai va dang trung 2-3 lan. Coi la DA DANG.
        if state == "publish-timeout":
            _ho_so(manager, account, nhan_hoso, "publish-timeout (coi như đã đăng): "
                   + (xong.get("detail") or ""))
            noi("đã bấm Đăng (chờ xác nhận lâu) — coi như đã đăng, không đăng lại")
    finally:
        # Dong DUNG trinh duyet cua acc nay, khong dung toi acc khac: close() chi
        # ket lieu tien trinh chay tu thu muc app cua chinh acc do.
        noi("đóng trình duyệt")
        try:
            manager.close(account, wait=15.0)
        except OSError:
            pass

    if publish:
        if lich:
            noi("Facebook đã nhận lịch")
            return f"đã đặt lịch đăng {lich.get('ngay', '')} {lich.get('gio', '')}".strip()
        noi("Facebook đã nhận bài")
        return "đã đăng lên fanpage"
    noi("đã nạp video vào composer")
    return "đã nạp vào composer, chưa bấm Đăng"


def upload_group(
    manager,
    account,
    group_id: str,
    video_path: str,
    caption: str = "",
    kind: str = "video",
    publish: bool = True,
    log: Optional[Callable[[str], None]] = None,
    timeout: float = 900.0,
    medias: Optional[list] = None,
    random_bg: bool = True,
) -> str:
    """Dang video vao mot nhom Facebook bang acc da chon.

    Khac fanpage: nhom khong qua Business Suite ma dang thang tren trang nhom.
    Cac buoc do agent lam (xem core/assets/fbupload_agent.js): bam o soan bai ->
    gan video vao o chon file co san trong hop thoai -> dien mo ta -> bam Dang.

    ``medias``: danh sach duong dan (anh + video) de GOP nhieu media vao MOT bai.
    Rong -> dang mot file ``video_path`` nhu cu.
    """
    from . import autoup, fbupload

    noi = log or (lambda _m: None)
    if not os.path.isfile(video_path):
        raise BusinessError(f"Không thấy file: {video_path}")

    media_items = []
    for p in (medias or []):
        if p and os.path.isfile(p):
            media_items.append({"path": os.path.abspath(p), "mime": fbupload.mime_of(p)})

    profile = manager.profile_dir(account)
    manager.close(account, wait=10.0)
    clear(profile)
    put_command(profile, action="group", path=os.path.abspath(video_path),
                caption=caption, kind=kind,
                mime=fbupload.mime_of(video_path),
                medias=media_items if len(media_items) > 1 else None,
                randomBg=bool(random_bg) and kind == "text",
                publish=bool(publish),
                publishWait=int(max(60, timeout / 3)),
                doneTimeout=int(max(60, timeout - 180)))

    noi("mở trang nhóm...")
    manager.launch(account, url=autoup.group_url(group_id))

    HONG = {"no-composer", "no-file-input", "no-path", "bad-path", "no-such-file",
            "file-api-error", "attach-error", "file-read-error", "ask-file-error",
            "caption-failed", "no-publish-button", "publish-error",
            "video-slow", "click-error", "error", "group-join-pending"}
    XONG = {"publish-done", "publish-timeout"} if publish else {"caption-filled"}
    HONG = HONG | {LANG_STATE}

    nhan_hoso = f"nhom-{group_id}"
    try:
        xong = wait_state(profile, XONG | HONG | set(ACC_STATES), timeout=timeout,
                          app_dir=app_dir_cua(manager, account))
        if xong is None:
            _ho_so(manager, account, nhan_hoso, "trang không phản hồi")
            raise BusinessError("Trang nhóm không phản hồi.")
        state = xong.get("state")
        if state == BROWSER_GONE:
            raise BusinessError("Trình duyệt đã đóng giữa chừng — "
                                + (xong.get("detail") or "") + ". Bài này chưa đăng.")
        if state == LANG_STATE:
            raise BusinessError(f"{LANG_MARK}: giao diện đang là "
                                f"'{xong.get('detail') or '?'}' — phải đổi sang tiếng Anh "
                                "rồi mới đăng được.")
        if state in ACC_STATES:
            raise BusinessError(ACC_STATES[state] + " — "
                                + (xong.get("detail") or ""))
        if state == "group-join-pending":
            # Acc chua vao nhom -> agent da tu bam "Tham gia nhom" nhung nhom CAN DUYET.
            _ho_so(manager, account, nhan_hoso, xong.get("detail") or "")
            raise BusinessError(
                "ACC CHƯA VÀO NHÓM — đã tự bấm 'Tham gia nhóm' nhưng nhóm CẦN DUYỆT; "
                "chờ nhóm duyệt rồi tool sẽ đăng ở lượt sau.")
        if state in HONG:
            _ho_so(manager, account, nhan_hoso,
                   f"{state}: {xong.get('detail') or ''}")
            raise BusinessError(f"{state}: {xong.get('detail') or ''}".strip(": "))
        # QUAN TRONG - chong dang trung: 'publish-timeout' nghia la agent DA BAM
        # "Dang" nhung khong kip thay hop soan dong. Thuc te Facebook GAN NHU LUON
        # da dang bai (chi la dong hop cham). Neu nem loi o day thi upload_now se
        # THU LAI va dang lai -> ra 2-3 bai trung. Nen coi day la DA DANG, khong
        # nem loi, de bai duoc danh dau da dang + khong lap lai.
        if state == "publish-timeout":
            _ho_so(manager, account, nhan_hoso, "publish-timeout (coi như đã đăng): "
                   + (xong.get("detail") or ""))
            noi("đã bấm Đăng (hộp soạn đóng chậm) — coi như đã đăng, không đăng lại")
    finally:
        noi("đóng trình duyệt")
        try:
            manager.close(account, wait=15.0)
        except OSError:
            pass

    if not publish:                       # test: chi nap composer, khong bam Dang
        noi("đã nạp bài vào composer nhóm (chưa đăng)")
        return "đã nạp vào composer nhóm, chưa đăng"
    noi("đã đăng vào nhóm")
    return "đã đăng vào nhóm"


def health_check(manager, account, page_id: str, timeout: float = 150.0) -> tuple:
    """Kham composer: mo len xem cac bo phan quen thuoc con khong. KHONG dang gi.

    Tra ve ``(ok, chi_tiet)``. Chay moi sang truoc moc dang dau tien de biet
    Facebook vua doi giao dien -- truoc khi hang chuc trang cung hong.
    """
    from . import autoup

    profile = manager.profile_dir(account)
    manager.close(account, wait=10.0)
    clear(profile)
    put_command(profile, action="health")
    manager.launch(account, url=autoup.business_url(page_id))
    try:
        r = wait_state(profile, {"healthy", "unhealthy", "error"}
                       | set(ACC_STATES), timeout=timeout)
        if r is None:
            _ho_so(manager, account, f"kham-{page_id}", "khám trang: không phản hồi")
            return False, "trang không phản hồi"
        state, detail = r.get("state"), r.get("detail") or ""
        if state == "healthy":
            return True, detail
        if state in ACC_STATES:
            return False, f"{ACC_STATES[state]} — {detail}"
        _ho_so(manager, account, f"kham-{page_id}", f"{state}: {detail}")
        return False, f"{state}: {detail}"
    finally:
        try:
            manager.close(account, wait=15.0)
        except OSError:
            pass


def dump_page(manager, account, page_id: str, timeout: float = 150.0) -> dict:
    """Mo composer roi bao agent ghi ban do cac nut ra file. Dung khi do giao dien.

    Facebook doi giao dien luon; co cai nay thi lan sau xem lai duoc trang co gi
    ma khong phai doan.
    """
    from . import autoup

    profile = manager.profile_dir(account)
    manager.close(account, wait=10.0)
    clear(profile)
    put_command(profile, action="dump")
    manager.launch(account, url=autoup.business_url(page_id))
    if wait_state(profile, {"dumped", "error"}, timeout=timeout) is None:
        raise BusinessError("Agent không ghi được bản đồ trang.")
    ban_do = read_dump(profile)
    if ban_do is None:
        raise BusinessError("Không đọc được file bản đồ trang.")
    return ban_do
