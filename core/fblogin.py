"""Dang nhap web bang id|pass|2fa (chuot phai -> "Dang nhap web").

Mo Firefox BINH THUONG (khong --remote-debugging-port) va dieu khien form dang nhap
bang PROCESS-SCRIPT AGENT (core/assets/fblogin_agent.js) -> su kien "nguoi that",
navigator.webdriver = false -> Facebook KHONG chan bang reCAPTCHA (khac duong BiDi,
da do that 2026-09-06). Ma 2FA sinh OFFLINE bang core.totp, CHA lam moi dinh ky.

Xac minh dang nhap thanh cong qua ProfileManager.verify/read_login_probe (qlfp-login.json),
KHONG dua vao agent doan "da vao". Bridge file: qlfp-weblogin.json / qlfp-weblogin-result.json
(xem autoconfig._LOGIN_LOADER_JS) -- KHAC qlfp-login.json cua probe.
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

from core import totp

CMD_NAME = "qlfp-weblogin.json"
RESULT_NAME = "qlfp-weblogin-result.json"
LOGIN_URL = "https://www.facebook.com/login.php"
#: Duong thay the: giao dien mobile ra man 2FA dang form don gian (thuong khong reCAPTCHA
#: Enterprise). Thu khi www cu day ve trang chu o buoc captcha (08/10).
LOGIN_URL_M = "https://m.facebook.com/login.php"
#: Cac trang thai "dang cho" (captcha / 2FA chuyen huong) duoc gia han them toi da bay nhieu
#: giay so voi timeout ban dau. Het tran la dung han, du agent con bao dang cho.
GIA_HAN_TOI_DA = 420.0

#: Trang thai ket thuc (status) tra ve.
VAO = "vao"                 # dang nhap thanh cong (verify_cookie_login = True)
SAI_MAT_KHAU = "sai_mat_khau"
CHECKPOINT = "checkpoint"
HAI_FA_LOI = "2fa_that_bai"  # da dien 2FA nhung khong vao (ma sai / het buoc)
KHONG_VAO = "khong_vao"      # da bam dang nhap nhung khong xac minh duoc
KHONG_RO = "khong_ro"
THIEU = "thieu_thong_tin"
LAP_LOGIN = "lap_login"      # bi day ve man dang nhap lien tuc (acc dang bi chan xac minh)
INVALID_LAP = "loi_invalid"
DONG_TAY = "dong_tay"        # nguoi dung TAT trinh duyet giua chung -> dung ngay, nha acc (12/10)  # trang 2FA bao "Invalid request" -> back/tiep tuc/nhap mk 3 lan van loi


class FbLoginError(RuntimeError):
    pass


#: Tran so acc dang nhap web SONG SONG (moi acc mo 1 Firefox that -> nang; gioi han de
#: may khong qua tai va Facebook khong nghi ngo dang nhap dong loat).
MAX_SONG_SONG = 8        # = max o "Luong" dung chung (ADR-015); tran an toan, moi acc 1 Firefox


def login_nhieu(manager, accounts, *, workers: int = 2,
                login_fn: Optional[Callable] = None,
                on_xong: Optional[Callable[[dict], None]] = None,
                dung: Optional[Callable[[], bool]] = None,
                log: Optional[Callable[[str], None]] = None) -> dict:
    """Dang nhap web NHIEU acc song song CO GIOI HAN (workers, tran MAX_SONG_SONG).

    login_fn(manager, account, log=) -> ket qua dict (mac dinh = login_web). Tra
    {"vao": [id...], "khong": [(id,status,detail)...], "so": n}. Giu tran de khong mo
    qua nhieu Firefox cung luc.
    """
    from concurrent.futures import ThreadPoolExecutor
    import threading
    login_fn = login_fn or login_web
    dung = dung or (lambda: False)
    noi = log or (lambda _m: None)
    accounts = list(accounts)
    n = max(1, min(int(workers), MAX_SONG_SONG, len(accounts) or 1))
    vao: list = []
    khong: list = []
    lock = threading.Lock()

    def one(acc):
        if dung():
            return
        try:
            kq = login_fn(manager, acc, log=log)
        except Exception as exc:  # noqa: BLE001
            kq = {"ok": False, "status": "loi", "detail": str(exc)[:150]}
        with lock:
            if kq.get("ok"):
                vao.append(acc.id)
            else:
                khong.append((acc.id, kq.get("status"), kq.get("detail", "")))
        if on_xong:
            on_xong({"id": acc.id, **kq})

    with ThreadPoolExecutor(max_workers=n) as pool:
        list(pool.map(one, accounts))
    noi(f"đăng nhập web {len(vao)}/{len(accounts)} acc (song song {n} luồng).")
    return {"vao": vao, "khong": khong, "so": len(accounts)}


def _clear(profile_dir: str) -> None:
    for n in (CMD_NAME, RESULT_NAME):
        try:
            os.remove(os.path.join(profile_dir, n))
        except OSError:
            pass


#: Tu tich o "Toi khong phai la nguoi may" khi dinh reCAPTCHA?
#: MAC DINH TAT (08/10, do that 3 acc): tool tich bang su kien tong hop -> Google cham la bot ->
#: Facebook day ve trang chu 3 giay sau (nav=navigate, ref=two_step_verification — chinh FB
#: chuyen, khong phai agent). Tool chi CHO: nguoi dung tich tay + lam xac minh tren cua so
#: Firefox, trang chuyen sang o nhap ma thi tool tu dien 2FA va chay tiep. Bat lai = True.
TU_TICH_CAPTCHA = False


def _put_cmd(profile_dir: str, account, code: str, *, tu_tich_captcha=None) -> None:
    cmd = {"action": "weblogin", "email": account.id, "pass": account.password,
           "code": code or "", "code_at": time.time(), "formTimeout": 45000, "delay": 2000,
           "tu_tich_captcha": TU_TICH_CAPTCHA if tu_tich_captcha is None else bool(tu_tich_captcha),
           # Luong khoi phuc (Invalid request -> quen mat khau): mail khoi phuc + thoi gian cho captcha.
           "recovery_mail": (getattr(account, "recovery_mail", "") or ""),
           "recoverTimeout": 130000}
    os.makedirs(profile_dir, exist_ok=True)
    with open(os.path.join(profile_dir, CMD_NAME), "w", encoding="utf-8") as fh:
        json.dump(cmd, fh, ensure_ascii=False)


def _read_result(profile_dir: str) -> Optional[dict]:
    try:
        with open(os.path.join(profile_dir, RESULT_NAME), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def danh_gia(states: set, vao_duoc: bool, het_gio: bool) -> Optional[str]:
    """Quyet dinh trang thai cuoi tu tap trang thai agent + probe dang nhap + het gio.

    Tra None = chua ket luan (cho tiep). Ham THUAN de test khong can trinh duyet.
    """
    if vao_duoc:
        return VAO
    if "checkpoint" in states:
        return CHECKPOINT
    if "wrong-pass" in states:
        return SAI_MAT_KHAU
    if "invalid-fail" in states:
        # Trang 2FA "Invalid request": da back -> tiep tuc -> nhap mk 3 lan van loi -> dung, bao loi.
        return INVALID_LAP
    if "lap-login" in states:
        # Tich reCAPTCHA / xac minh xong ma FB cu day ve man dang nhap -> dung han, khong
        # quay vong (nguoi dung bao 08/10: "back lai lien thi cu lap lai lien tuc").
        return LAP_LOGIN
    if het_gio:
        if "twofa-filled" in states or "twofa-dom" in states:
            return HAI_FA_LOI
        if "clicked-login" in states or "login-submit-form" in states:
            return KHONG_VAO
        return KHONG_RO
    return None


#: Trang thai dang nhap -> ma cot "Trạng thái" (xem core/trang_thai.py). Khong co trong
#: bang thi coi la loi chung (van hien ro ly do o cot chi tiet).
_MA_TT = {CHECKPOINT: "checkpoint", HAI_FA_LOI: "loi", KHONG_VAO: "loi", LAP_LOGIN: "loi",
          KHONG_RO: "loi", THIEU: "loi", INVALID_LAP: "loi", DONG_TAY: "loi"}


#: Kiểm phiên SẴN CÓ trong profile trước khi mở form đăng nhập (người dùng chốt 12/10): acc đã đăng
#: nhập rồi thì login.php trả "Not Found" -> tool treo tới hết giờ rồi báo khong_ro. Live -> báo Live,
#: Checkpoint -> báo Checkpoint, KHÔNG mở form. Thước tắt bằng cách gán False.
KIEM_PHIEN_TRUOC = True


def _phien_san_co(manager, account) -> tuple:
    """(trang_thai checkwall, chi_tiet) của phiên đang nằm trong profile — HTTP, không mở trình duyệt.
    Lỗi gì cũng trả ("", "") -> đi đường đăng nhập như cũ."""
    try:
        from core import checkwall
        from core.modun.check_tuong import cookie_cua_acc
        ck = cookie_cua_acc(manager, account)
        if not checkwall.co_c_user(ck):
            return "", ""
        return checkwall.check_mot(ck, proxy=account.get_proxy() if hasattr(account, "get_proxy") else None)
    except Exception:  # noqa: BLE001
        return "", ""


def _ket_thuc_som(manager, account, status: str, detail: str, noi) -> dict:
    """Kết thúc KHÔNG mở form: ghi trạng thái + (Live) lấy cookie mới từ profile."""
    from core import trang_thai as _tt
    ok = status == VAO
    if ok:
        account.cookie_ok = time.strftime("%Y-%m-%d %H:%M")
        try:
            from . import cookie_moi
            chuoi, _nguon = cookie_moi.doc_cookie_moi(manager, account)
            if chuoi:
                account.cookie = chuoi
        except Exception:  # noqa: BLE001
            pass
    _tt.ghi(account, _tt.LIVE if ok else _MA_TT.get(status, _tt.LOI), detail, "đăng nhập web")
    noi(f"[{account.id}] KẾT QUẢ: {status} — {detail}")
    return {"ok": ok, "status": status, "detail": detail}


def login_web(manager, account, *, timeout: float = 200.0,
              log: Optional[Callable[[str], None]] = None, tu_tich_captcha=None,
              url_login: str = "") -> dict:
    """Dang nhap acc bang id|pass|2fa qua trinh duyet. Tra {ok, status, detail}. Khong nem
    (tru thieu thong tin bat buoc)."""
    noi = log or (lambda _m: None)
    if not (account.password or "").strip():
        return {"ok": False, "status": THIEU, "detail": "Acc chưa có mật khẩu."}
    profile = manager.profile_dir(account)

    if KIEM_PHIEN_TRUOC:
        from core import checkwall
        tt_san, ct_san = _phien_san_co(manager, account)
        if tt_san == checkwall.LIVE:
            return _ket_thuc_som(manager, account, VAO,
                                 "đã đăng nhập sẵn — phiên còn sống, không cần đăng nhập lại"
                                 + (f" ({ct_san})" if ct_san else ""), noi)
        if tt_san == checkwall.CHECKPOINT:
            return _ket_thuc_som(manager, account, CHECKPOINT,
                                 "acc đang bị checkpoint — cần xác minh tay", noi)
        if tt_san:
            noi(f"[{account.id}] phiên sẵn có: {tt_san} — mở form đăng nhập.")

    manager.close(account, wait=8.0)
    manager.configure(account)              # trien khai/lam moi agent dang nhap vao profile
    manager.clear_login_probe(account)
    _clear(profile)
    twofa = (account.twofa or "").strip()
    _put_cmd(profile, account, totp.generate(twofa) if twofa else "",
             tu_tich_captcha=tu_tich_captcha)

    noi(f"[{account.id}] mở Firefox đăng nhập id|pass" + (" |2fa" if twofa else "") + "...")
    manager.launch(account, url=(url_login or LOGIN_URL))

    states: set = set()
    _seen_details: set = set()
    dom_2fa = ""
    last_code_at = 0.0
    deadline = time.time() + timeout
    # TRAN CUNG: cac trang thai "dang cho" gia han deadline moi nhip -> khong co tran thi
    # cho-ve-2fa lap mai la chay VO HAN (do that acc 4, 08/10: qua 20 phut van chua dung).
    tran_cung = time.time() + timeout + GIA_HAN_TOI_DA
    nhac_cho_at = 0.0                # lan cuoi nhac "dang cho captcha/2FA"
    status = None
    # Canh Firefox: nguoi dung TAT trinh duyet giua chung -> dung NGAY (truoc day ngoi cho het
    # timeout + gia han toi ~10 phut, acc bi khoa "đang bận" suot luc do — nguoi dung bao 12/10).
    canh_ff = None
    try:
        from core import procutil
        from core.fbbusiness import app_dir_cua
        canh_ff = procutil.CanhTrinhDuyet(app_dir_cua(manager, account))
    except Exception:  # noqa: BLE001 — khong canh duoc thi chay nhu cu
        canh_ff = None
    ke_tiep_kiem = 0.0
    try:
        while time.time() < min(deadline, tran_cung):
            if canh_ff is not None and time.time() >= ke_tiep_kiem:
                ke_tiep_kiem = time.time() + 2.0
                if canh_ff.da_dong():
                    status = DONG_TAY
                    noi(f"[{account.id}] trình duyệt đã bị đóng — dừng đăng nhập.")
                    break
            r = _read_result(profile)
            if r:
                st = r.get("state")
                det = r.get("detail")
                det = "" if det is None else str(det)
                # 'seen'/'twofa-dom': chan doan, log moi khi detail doi (khong tinh la trang thai cuoi).
                if st in ("seen", "twofa-dom"):
                    key = st + "|" + det
                    if key not in _seen_details:
                        _seen_details.add(key)
                        noi(f"[{account.id}] {st}: {det[:160]}")
                    if st == "twofa-dom":
                        dom_2fa = det
                        states.add(st)
                elif st in ("2fa-cho-chuyen", "captcha-tick", "captcha-ticked",
                            "captcha-thu-thach", "cho-ve-2fa", "captcha-cho-tay"):
                    # Trang thai CHO: agent bao lap lai moi nhip. In dong dau, roi cu ~30s
                    # nhac lai mot lan — khong thi nhat ky im lang 4 phut, tuong tool treo
                    # (chay that 08/10). Van phai gia han o duoi.
                    if st not in states or (time.time() - nhac_cho_at) >= 30.0:
                        states.add(st)
                        nhac_cho_at = time.time()
                        noi(f"[{account.id}] {st}" + (f": {det[:90]}" if det else "")
                            + ("" if st in ("captcha-tick", "captcha-ticked") else
                               " — nếu Facebook đòi chọn ảnh, hãy làm trên cửa sổ Firefox"))
                elif st and st not in states:
                    states.add(st)
                    noi(f"[{account.id}] {st}" + (f": {det[:60]}" if det else ""))
                # Dinh CAPTCHA: agent bao lien tuc trong luc cho -> GIA HAN deadline de nguoi dung kip giai.
                if st == "captcha-wait":
                    deadline = max(deadline, time.time() + 90.0)
                # Trang 2FA dang chuyen huong sang man nhap ma (reCAPTCHA vua tich xong,
                # FB quay vong vai giay): PHAI cho, khong duoc het gio giua chung roi tat
                # trinh duyet (nguoi dung chot 08/10).
                if st == "2fa-cho-chuyen":
                    deadline = max(deadline, time.time() + 60.0)
                # Dang tich / dang cho nguoi dung xac minh reCAPTCHA -> gia han.
                if st in ("captcha-tick", "captcha-ticked", "captcha-thu-thach", "captcha-cho-tay"):
                    deadline = max(deadline, time.time() + 120.0)
                # Dang cho FB tu dua tro lai trang 2FA (vua bi day ve man dang nhap).
                if st == "cho-ve-2fa":
                    deadline = max(deadline, time.time() + 40.0)
            probe = manager.read_login_probe(account)
            vao = bool(probe and probe[0])
            status = danh_gia(states, vao, het_gio=False)
            if status:
                break
            # Lam moi ma 2FA moi ~5s de agent luon co ma con hieu luc khi toi buoc 2FA.
            if twofa and (time.time() - last_code_at) >= 5.0:
                _put_cmd(profile, account, totp.generate(twofa), tu_tich_captcha=tu_tich_captcha)
                last_code_at = time.time()
            time.sleep(1.0)
        if status is None:
            probe = manager.read_login_probe(account)
            status = danh_gia(states, bool(probe and probe[0]), het_gio=True) or KHONG_RO
    finally:
        # Xac minh chac chan bang phien that (giu trinh duyet mo them chut de probe kip ghi).
        try:
            if status not in (CHECKPOINT, SAI_MAT_KHAU, DONG_TAY) and manager.verify_cookie_login(account, timeout=12):
                status = VAO
        except Exception:  # noqa: BLE001
            pass
        try:
            manager.close(account, wait=10.0)
        except OSError:
            pass
        _clear(profile)     # xoa lenh de agent khong dien nham o lan mo sau

    ok = status == VAO
    if ok:
        # LUON thay cookie cu bang COOKIE MOI khi vao duoc (yeu cau nguoi dung 05/10).
        # Truoc day chi doc PROBE: probe khong kip ghi la giu nguyen cookie cu (da chet)
        # -> gio co them duong doc thang cookies.sqlite cua profile (xem core/cookie_moi).
        try:
            from . import cookie_moi
            chuoi, nguon = cookie_moi.doc_cookie_moi(manager, account)
            if chuoi:
                account.cookie = chuoi
                noi(f"[{account.id}] đã thay cookie cũ bằng cookie mới "
                    f"({len(chuoi)} ký tự, từ {nguon}).")
            else:
                noi(f"[{account.id}] vào được nhưng chưa đọc được cookie mới — giữ cookie cũ.")
        except Exception:  # noqa: BLE001
            pass
    detail = {VAO: "đăng nhập thành công", SAI_MAT_KHAU: "sai mật khẩu",
              CHECKPOINT: "acc bị checkpoint — cần xác minh tay",
              HAI_FA_LOI: "điền 2FA nhưng không vào được (mã sai / thêm bước)",
              KHONG_VAO: "đã bấm đăng nhập nhưng chưa vào được",
              INVALID_LAP: "trang 2FA 'Invalid request' — quay lại/nhập mật khẩu 3 lần vẫn lỗi",
              LAP_LOGIN: ("Facebook qua được kiểm tra bảo mật nhưng cứ đẩy về màn đăng nhập — "
                          "RẤT CÓ THỂ SAI MẬT KHẨU, hoặc acc bị chặn. Kiểm tra lại mật khẩu, "
                          "hoặc đăng nhập TAY một lần rồi thử lại"),
              DONG_TAY: "trình duyệt bị đóng giữa chừng — đã dừng đăng nhập",
              KHONG_RO: "không rõ kết quả (hết giờ)"}.get(status, status or "")
    if status == HAI_FA_LOI and dom_2fa:
        detail += f" | 2FA DOM: {dom_2fa[:120]}"
    if ok:
        account.cookie_ok = time.strftime("%Y-%m-%d %H:%M")
    # Ghi TRANG THAI GAN NHAT ra bang Quan ly acc (cot "Trạng thái").
    from core import trang_thai as _tt
    _tt.ghi(account, _tt.LIVE if ok else _MA_TT.get(status, _tt.LOI), detail, "đăng nhập web")
    noi(f"[{account.id}] KẾT QUẢ: {status} — {detail}")
    return {"ok": ok, "status": status, "detail": detail}
