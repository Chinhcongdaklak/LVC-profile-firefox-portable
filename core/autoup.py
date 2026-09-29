"""Canh gio quet thu muc video roi tu dang len fanpage.

Cach chay: nguoi dung dat mot danh sach moc gio theo dong ho MAY TINH (vd 08:00,
12:30, 20:00). Den moc gio nao thi quet thu muc, lay video CU NHAT, dang len
fanpage da chon, dang xong thi xoa file di.

Moi moc gio chi chay MOT LAN trong ngay. Tool tat roi mo lai giua ngay cung
khong dang lai moc da chay -- xem ``_da_chay``, no duoc ghi ra file.

Module nay khong biet gi ve giao dien lan ve cach dang. Viec dang duoc truyen
vao qua ``uploader`` nen thay Graph API bang duong trinh duyet chi la doi mot
tham so, va test khong can mang.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Callable, Optional

from . import fbupload

#: Ten file luu cau hinh + nhat ky, nam canh accounts.json.
STATE_NAME = "autoup.json"

#: Uploader nhan (duong_dan, loi_tua) va tra ve id video. Nem loi neu hong.
Uploader = Callable[[str, str], str]

#: Trang treo 0% may lan lien tiep thi tat tu dong dang, khoi chay vo ich.
STUCK_LIMIT = 3
#: Dang hong thi thu lai bao nhieu lan nua truoc khi bo cuoc.
RETRY_TIMES = 2
#: Nghi bao nhieu giay giua hai lan thu -- de trinh duyet dong han va trang nghi.
RETRY_PAUSE = 15
#: Hong du ngan nay LUOT (khung gio) lien tiep thi tam dung trang va chi nguoi
#: dung cach phan biet loi tool hay loi acc.
SLOT_FAIL_LIMIT = 3
#: Loi nao co chu nay thi coi la "trang hong", dem vao so lan treo.
STUCK_MARK = "không tải lên được phần trăm nào"
#: Loi mang chu nay la chuyen cua ACC (xem fbbusiness.ACC_STATES): khong thu
#: lai, khong dem treo -- bao thang va dung.
CHECKPOINT_MARK = "CHECKPOINT"
LOGOUT_MARK = "ĐĂNG XUẤT"
#: Loi XAY RA SAU KHI DA BAM "Dang" -> bai co the DA len roi. KHONG duoc thu lai,
#: neu khong se dang trung 2-3 lan. (publish-timeout da duoc coi la thanh cong o
#: fbbusiness; con lai publish-error va bat cu thong bao nao co "bấm Đăng".)
PUBLISHED_MARKS = ("publish-error", "publish-timeout", "bấm Đăng", "bam Dang")
#: Kham trang truoc moc dang som nhat bao nhieu phut.
CANARY_AHEAD = 20
#: Mot ACC hong du ngan nay LUOT -> bo qua acc do (chi dang bang acc con lai) cho toi khi "Mo lai acc".
ACC_FAIL_LIMIT = 2
#: Trang Auto dang X: acc loi 3 lan moi bo (nguoi dung chot 2026-09-29).
ACC_FAIL_LIMIT_X = 3
#: X bao "You've hit the daily post limit": KHONG phai loi acc/tool -- tam dung acc DUNG 24 GIO
#: roi tu dang lai (vd bao luc 08:00 29/09 -> dang lai 08:00 30/09). Bai chua len, video giu nguyen.
GIOI_HAN_MARK = "GIỚI HẠN ĐĂNG"
#: Nen tang TU CHOI chinh video nay (vd X: "Some of your media failed to load" -- video qua dai).
#: Loi cua VIDEO, khong phai acc: khong thu lai, khong dem loi acc, ghi video vao danh sach bo qua.
VIDEO_TU_CHOI_MARK = "X KHÔNG NHẬN VIDEO"
GIOI_HAN_GIO = 24
#: Cho khoa acc DU PHONG toi da bao nhieu giay (acc do co the dang ban o trang khac); het gio thi bo qua
#: acc do luot nay -- khong ngoi cho vo han (tranh deadlock 2 trang cho khoa cheo nhau).
ACC_LOCK_WAIT = 300
#: Trang thai acc trong mot cong viec: "ok" | "bo" (hong ACC_FAIL_LIMIT lan) | "checkpoint" | "dang_xuat".
ACC_TT_OK, ACC_TT_BO, ACC_TT_CHECKPOINT, ACC_TT_DANG_XUAT = "ok", "bo", "checkpoint", "dang_xuat"
#: Acc bi nen tang GIOI HAN DANG trong ngay: tam dung toi moc "den" roi TU dung lai.
ACC_TT_GIOI_HAN = "gioi_han"


#: Moc gio mac dinh khi chua cai gi -- rai deu tu sang toi khuya.
DEFAULT_TIMES = ["07:00", "09:00", "11:00", "13:00", "15:00",
                 "18:00", "19:00", "20:00", "21:00", "22:00"]

#: Mo Business Suite dung mot fanpage. ``asset_id`` la cai chon fanpage nao.
BUSINESS_URL = "https://business.facebook.com/latest/bulk_upload_composer?asset_id={page_id}"
BUSINESS_HOME = "https://business.facebook.com/latest/home?asset_id={page_id}"
#: Trang cua mot nhom. Dang bai vao nhom lam thang tren trang nay, khong qua
#: Business Suite -- Business Suite khong quan ly nhom.
GROUP_URL = "https://www.facebook.com/groups/{group_id}"


def business_url(page_id: str, home: bool = False) -> str:
    """Dia chi Business Suite da tro san vao fanpage co id nay."""
    mau = BUSINESS_HOME if home else BUSINESS_URL
    return mau.format(page_id=str(page_id).strip())


def group_url(group_id: str) -> str:
    """Dia chi trang nhom. Nhan ca id lan duong dan da dan vao."""
    return GROUP_URL.format(group_id=parse_group_id(group_id))


def parse_group_id(text: str) -> str:
    """Rut id nhom ra khoi thu nguoi dung dan vao.

    Nhan ca id tran, link ``facebook.com/groups/123456`` va link dang ten
    ``facebook.com/groups/ten-nhom``. Nhom co the dung ten thay so nen khong ep
    phai la chu so.
    """
    raw = (text or "").strip().rstrip("/")
    if not raw:
        return ""
    found = re.search(r"facebook\.com/groups/([^/?#]+)", raw)
    if found:
        return found.group(1)
    return raw.split("/")[-1].split("?")[0]


@dataclass
class AutoUpConfig:
    enabled: bool = False
    #: "Thu muc video": nguon video LE co san de dang len nhom (quet folder).
    folder: str = ""
    #: "Thu muc bai cho dang": noi luu media cua cac dong hang doi (quet ve tu
    #: group khac / them tay). Dang xong -> xoa dong + xoa file o day. TACH RIENG
    #: voi ``folder`` de hai chuc nang khong lan nhau.
    queue_dir: str = ""
    #: Cac moc gio trong ngay, dang "HH:MM".
    times: list = field(default_factory=lambda: list(DEFAULT_TIMES))
    #: Acc dung de mo Business Suite (id acc trong bang). Giu lai cho tuong
    #: thich nguoc; khi co ``account_ids`` thi day la acc dau danh sach.
    account_id: str = ""
    #: Nhieu acc dang luan phien cho MOT trang. Rong -> dung ``account_id``.
    account_ids: list = field(default_factory=list)
    #: Kich ban khi co nhieu acc:
    #:   "turn" = luan phien moi bai (acc1 dang mot moc, acc2 dang moc sau...);
    #:   "day"  = moi acc dang tron mot ngay roi doi acc.
    rotate: str = "turn"
    #: Dang vao dau: "page" (fanpage) hay "group" (nhom facebook).
    target_kind: str = "page"
    #: Kieu bai: "video", "image" (anh) hay "text" (chi co chu).
    post_kind: str = "video"
    #: Nhom se dang vao (khi target_kind = "group"). Nhan ca id lan link.
    group_id: str = ""
    #: Ten nhom do duoc (chi de nhin cho de).
    group_name: str = ""
    #: Fanpage se dang len.
    page_id: str = ""
    #: Ten fanpage do duoc (chi de hien cho de nhin).
    page_name: str = ""
    #: So ma BUSINESS SUITE dung, quy doi tu ``page_id``. Rong = chua quy doi.
    #:
    #: Phai la mot truong RIENG chu khong suy ra tu page_name: da gap truong hop
    #: page_name co roi ma page_id van la so cong khai, dan vao Business Suite thi
    #: ra trang "Sorry, this content isn't available right now".
    asset_id: str = ""
    #: Token cua fanpage -- chi can khi dang bang Graph API.
    token: str = ""
    delete_after: bool = True
    #: Video dai hon ngan nay GIAY thi BO QUA (khong mo trinh duyet). 0 = theo nen tang:
    #: X = 140s (acc thuong chi nhan <= 2:20), Facebook = khong gioi han. Acc X Premium dat so lon hon.
    video_toi_da_giay: int = 0
    #: Tu dong 'xao' (viet lai caption + anh bang AI) khi them bai vao hang doi.
    auto_xao: bool = False
    #: Khi dang: CHI dang bai da xao xong (bo qua bai chua/loi xao).
    only_post_xao: bool = False
    #: "api" hoac "browser".
    method: str = "browser"
    #: "list" = theo danh sach moc gio; "delay" = cu cach nhau bao nhieu phut.
    schedule_mode: str = "list"
    #: Khoang cach giua hai bai khi chay kieu "delay".
    delay_minutes: int = 60
    #: Mau TUONG TAC gan cho job: {ten, so_phut, so_like, so_video} hoac None. Co gan ->
    #: TRUOC khi dang bai, acc xem reel + like theo mau (KHONG dung delay cua tab).
    tuong_tac_mau: Optional[dict] = None

    # --- Chi dung khi target_kind = "lich" (dang DAT LICH, xem core/lich_dang.py) ---
    #: Mui gio cua PAGE (nhan trong lich_dang.DANH_SACH_MUI_GIO hoac ten IANA).
    mui_gio: str = ""
    #: Cac khung: [{"chay": "25/09 07:00", "dang": "25/09 07:00"}, ...]
    #: "chay" = gio MAY (tool bat dau lam); "dang" = gio theo MUI GIO PAGE.
    khung_lich: list = field(default_factory=list)
    #: CUA 1 - do tre cho phep (phut). CUA 2 - khoang an toan (phut).
    tre_phut: int = 5
    an_toan_phut: int = 30
    #: Gio SOM NHAT trang nay duoc chay trong ngay ("HH:MM", gio MAY). Rong = khong chan.
    #: Hai trang trung gio bat dau -> con bi rao "cach nhau N phut giua cac trang".
    gio_bat_dau: str = ""

    def label(self) -> str:
        if self.target_kind == "group":
            if self.group_name:
                return f"{self.group_name} ({self.group_id})"
            return self.group_id or "(chưa nhập nhóm)"
        if self.page_name:
            return f"{self.page_name} ({self.page_id})"
        return self.page_id or "(chưa nhập ID fanpage)"

    @property
    def is_group(self) -> bool:
        return self.target_kind == "group"

    @property
    def is_lich(self) -> bool:
        """Trang chay theo LICH DAT TRUOC (gio chay tool + gio dang + mui gio page)."""
        return self.target_kind == "lich"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "AutoUpConfig":
        raw = dict(raw or {})
        raw["times"] = [str(t) for t in (raw.get("times") or [])] or list(DEFAULT_TIMES)
        # File cau hinh doi cu: truoc day fanpage nam trong danh sach "targets".
        cu = raw.pop("targets", None)
        if cu and not raw.get("page_id"):
            dau = cu[0] if isinstance(cu[0], dict) else {}
            raw["page_id"] = str(dau.get("page_id") or "")
            raw["page_name"] = str(dau.get("page_name") or "")
            raw["token"] = str(dau.get("token") or "")
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def loc_nhat_ky_gan(history, so_ngay: int = 2, moc_hom_nay=None) -> list:
    """Giu cac dong nhat ky trong ``so_ngay`` ngay gan nhat (theo khoa 'at' YYYY-MM-DD ...).

    so_ngay=2 -> giu HOM NAY + HOM QUA. Dong khong doc duoc ngay bi bo (rac). Tranh
    nhat ky phinh to khi tool chay lien tuc nhieu ngay.
    """
    from datetime import date, datetime, timedelta
    hom_nay = moc_hom_nay or date.today()
    cutoff = hom_nay - timedelta(days=max(1, so_ngay) - 1)
    ra = []
    for d in history or []:
        try:
            ngay = datetime.strptime((d.get("at") or "")[:10], "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            continue
        if ngay >= cutoff:
            ra.append(d)
    return ra


def normalize_time(text: str) -> str:
    """Doi "8:5", "08.05", "0805" thanh "08:05". Sai dinh dang thi nem ValueError."""
    raw = (text or "").strip().replace(".", ":").replace("h", ":").replace(" ", "")
    if raw.isdigit() and len(raw) == 4:
        raw = raw[:2] + ":" + raw[2:]
    if ":" not in raw:
        raise ValueError(f"Giờ không hợp lệ: {text!r}. Hãy nhập dạng HH:MM.")
    gio, _, phut = raw.partition(":")
    try:
        gio_i, phut_i = int(gio), int(phut)
    except ValueError:
        raise ValueError(f"Giờ không hợp lệ: {text!r}. Hãy nhập dạng HH:MM.") from None
    if not (0 <= gio_i <= 23 and 0 <= phut_i <= 59):
        raise ValueError(f"Giờ không hợp lệ: {text!r}. Giờ 0-23, phút 0-59.")
    return f"{gio_i:02d}:{phut_i:02d}"


def parse_times(text: str) -> list[str]:
    """Doc o nhap nhieu moc gio (xuong dong / dau phay) thanh danh sach da sap xep."""
    parts = [p for p in (text or "").replace(",", "\n").replace(";", "\n").split("\n")]
    result = []
    for part in parts:
        if part.strip():
            gio = normalize_time(part)
            if gio not in result:
                result.append(gio)
    return sorted(result)


def _acc_state_sach(raw) -> dict:
    """Trang thai acc day du khoa, kieu dung (doc tu file cu/thieu khoa van ra dang chuan)."""
    raw = raw if isinstance(raw, dict) else {}
    tt = str(raw.get("tt") or ACC_TT_OK)
    if tt not in (ACC_TT_OK, ACC_TT_BO, ACC_TT_CHECKPOINT, ACC_TT_DANG_XUAT, ACC_TT_GIOI_HAN):
        tt = ACC_TT_OK
    try:
        loi = int(raw.get("loi") or 0)
    except (TypeError, ValueError):
        loi = 0
    ra = {"loi": loi, "tt": tt, "ly_do": str(raw.get("ly_do") or "")[:200],
          "at": str(raw.get("at") or "")}
    if tt == ACC_TT_GIOI_HAN:
        ra["den"] = str(raw.get("den") or "")      # "YYYY-MM-DD HH:MM:SS": luc duoc dang lai
    return ra


class AutoUploader:
    """MOT cong viec dang bai: mot fanpage, mot thu muc, mot lich rieng.

    Moi tab trong giao dien la mot cai nay. Cau hinh, nhat ky va bo dem cua tung
    cong viec nam o mot file rieng nen khong dam nhau.

    Tu no cung chay duoc mot minh (``start()``/``stop()``); khi co nhieu cong
    viec thi ``AutoUpManager`` chay chung mot vong lap cho tat ca.
    """

    def __init__(self, data_dir: str, log: Optional[Callable[[str], None]] = None,
                 job_id: str = "", name: str = "", path: Optional[str] = None,
                 platform: str = "fb"):
        self.job_id = job_id or "1"
        #: Nen tang dang bai: "fb" (Facebook, mac dinh) hay "x" (X.com).
        #: Quyet dinh kieu bai (X nhan ca anh/chu) va cach lay caption.
        self.platform = platform or "fb"
        self.name = name or "Trang 1"
        self.path = path or os.path.join(data_dir, STATE_NAME)
        self.config = AutoUpConfig()
        self.history: list = []
        self._fired: dict = {}          # "HH:MM" -> "YYYY-MM-DD" da chay
        self._lich_chay: Optional[dict] = None   # khung dat lich dang chay luot nay
        self._thieu_video_khoa: str = ""         # khung da bao "thieu video" roi
        self._chua_dang_khoa: str = ""           # khung da bao "chua dang duoc" roi
        self._last_run: str = ""        # lan dang gan nhat, cho kieu "delay"
        self._stuck: int = 0            # so lan lien tiep trang treo o 0%
        self._slot_fails: int = 0       # so LUOT (khung gio) hong lien tiep
        self._turn: int = 0             # dem luot dang, de luan phien nhieu acc
        self.ok_count: int = 0          # tong so video da dang duoc
        self.fail_count: int = 0        # tong so video dang hong
        self._posted: list = []         # dau vet video da dang, de khong dang trung
        self.queue: list = []           # hang doi bai cho dang (tu tab Quet bai)
        self._log = log or (lambda _m: None)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._busy = False
        self.uploader: Optional[Uploader] = None
        #: Manager cai vao: xin giu mot video. Tra ve True neu duoc giu.
        #: Phai lam trong MOT nhip khoa: kiem roi moi giu thi hai cong viec cung
        #: lot qua duoc (da do -- ca hai deu dang cung mot video).
        self.claim_check: Optional[Callable[[str], bool]] = None
        #: Manager cai vao: tra lai cho da giu khi hoa ra chua dung duoc.
        self.unclaim: Optional[Callable[[str], None]] = None
        #: Manager cai vao: khoa rieng cua mot acc (de acc DU PHONG cung duoc khoa khi doi acc giua luot).
        self.acc_lock: Optional[Callable[[str], threading.Lock]] = None
        #: Trang thai tung acc cua cong viec nay: acc -> {"loi", "tt", "ly_do", "at"} (xem ACC_TT_*).
        self.acc_states: dict = {}
        #: Acc DANG THU trong upload_now (ke ca acc du phong) -> pick_account tra dung acc nay
        #: de uploader/factory mo dung profile. Rong = ngoai luot dang.
        self._acc_dang: str = ""
        #: Dau vet video nen tang TU CHOI (load() ghi de neu file co).
        self._bo_video: list = []
        #: Manager cai vao: trang DAT LICH bao "that su bat dau dang" (da lay khung,
        #: sap mo trinh duyet) -> luc do moi bat rao giua cac trang.
        self.bao_bat_dau_lich: Optional[Callable[[], None]] = None
        self.load()

    # ---- luu / doc ---------------------------------------------------
    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            return
        self.config = AutoUpConfig.from_dict(raw.get("config") or {})
        self.name = str(raw.get("name") or self.name)
        self.history = loc_nhat_ky_gan(list(raw.get("history") or []))[-500:]
        self._fired = dict(raw.get("fired") or {})
        # Mo tool sang ngay moi -> so cua trang dat lich lam lai tu dau.
        self._don_so_lich()
        self._last_run = str(raw.get("last_run") or "")
        self._stuck = int(raw.get("stuck") or 0)
        self._slot_fails = int(raw.get("slot_fails") or 0)
        self._turn = int(raw.get("turn") or 0)
        self.acc_states = {str(k): _acc_state_sach(v)
                           for k, v in (raw.get("acc_states") or {}).items() if k}
        # Ban cu chi co mot acc (account_id) -> dua vao danh sach account_ids.
        if not self.config.account_ids and self.config.account_id:
            self.config.account_ids = [self.config.account_id]
        self.ok_count = int(raw.get("ok_count") or 0)
        self.fail_count = int(raw.get("fail_count") or 0)
        self._posted = [str(x) for x in (raw.get("posted") or [])][-500:]
        # Hang doi bai cho dang (dua tu tab Quet bai): moi item la mot dict
        # {caption, media, base, status: "cho"|"dang"|"loi", at}.
        self.queue = [dict(x) for x in (raw.get("queue") or []) if isinstance(x, dict)]
        #: Dau vet video nen tang TU CHOI (khong chon lai). Xoa file / doi file thi dau vet doi.
        self._bo_video = [str(x) for x in (raw.get("bo_video") or [])][-500:]

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        data = {
            "name": self.name,
            "config": self.config.to_dict(),
            "history": loc_nhat_ky_gan(self.history)[-500:],
            "fired": self._fired,
            "last_run": self._last_run,
            "stuck": self._stuck,
            "slot_fails": self._slot_fails,
            "turn": self._turn,
            "acc_states": self.acc_states,
            "ok_count": self.ok_count,
            "fail_count": self.fail_count,
            "posted": self._posted[-500:],
            "queue": self.queue[-500:],
            "bo_video": getattr(self, "_bo_video", [])[-500:],
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def note(self, text: str, ok: bool = True) -> None:
        """Ghi mot dong nhat ky, vua ra file vua len giao dien."""
        dong = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "ok": ok, "text": text}
        with self._lock:
            self.history.append(dong)
            self.history = loc_nhat_ky_gan(self.history)[-500:]
        self._log(f"{dong['at']}  {'✔' if ok else '✖'}  {text}")

    # ---- hang doi bai cho dang --------------------------------------
    def add_to_queue(self, caption: str, media: str, base: str = "",
                     kind: str = "", source: str = "", download: str = "da") -> None:
        """Them mot bai vao hang doi (goi tu tab Quet bai). Chong trung theo base.

        ``kind`` la kieu bai ("image"/"text"/"video"/"link"); de trong thi suy ra
        tu duoi file. ``source`` la link bai goc (nguon). ``download`` la trang
        thai tai media: "da" (da tai ve thu muc), "cho", "loi".
        """
        base = base or os.path.splitext(os.path.basename(media or ""))[0]
        kind = kind or fbupload.kind_of(media or "")
        for it in self.queue:
            if base and it.get("base") == base:
                it.update(caption=caption, media=media, status="cho", kind=kind,
                          source=source, download=download)
                self.save()
                return
        self.queue.append({
            "caption": caption or "", "media": media or "", "base": base,
            "kind": kind, "source": source or "", "download": download,
            "status": "cho", "at": time.strftime("%Y-%m-%d %H:%M"),
            # Bat "Tu xao AI" thi bai moi = cho xao; nut/luong UI se xao sau.
            "xao": "cho" if self.config.auto_xao else "",
            "caption_goc": caption or "",
        })
        self.save()

    def _set_queue_status(self, path: str, status: str) -> None:
        """Doi trang thai item hang doi khop voi file vua dang (theo ten file)."""
        if not path:
            return
        base = os.path.splitext(os.path.basename(path))[0]
        name = os.path.basename(path)
        changed = False
        for it in self.queue:
            m = it.get("media") or ""
            if it.get("base") == base or (m and os.path.basename(m) == name):
                it["status"] = status
                it["done_at"] = time.strftime("%Y-%m-%d %H:%M")
                changed = True
        if changed:
            self.save()

    def clear_queue(self, only_done: bool = False) -> int:
        before = len(self.queue)
        if only_done:
            self.queue = [it for it in self.queue if it.get("status") != "da"]
        else:
            self.queue = []
        self.save()
        return before - len(self.queue)

    # ---- vong lap ----------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def busy(self) -> bool:
        return self._busy

    def _loop(self) -> None:
        # Kiem moi 20 giay la du min: moc gio tinh theo phut, va lo mot nhip cung
        # khong mat luot vi ``due_times`` chi bo qua moc da chay TRONG NGAY.
        while not self._stop.wait(20):
            try:
                self.tick()
            except Exception as exc:                      # khong duoc chet ca vong lap
                self.note(f"Lỗi vòng lặp: {exc}", ok=False)

    def due_times(self, now: Optional[datetime] = None) -> list[str]:
        """Cac moc gio da toi trong hom nay ma chua chay.

        Da toi = gio hien tai >= moc gio. Tool mo luc 9h ma moc 8h chua chay thi
        van chay bu -- de tat may mot lat khong mat luot dang.
        """
        now = now or datetime.now()
        hom_nay = now.strftime("%Y-%m-%d")
        bay_gio = now.strftime("%H:%M")
        return [t for t in sorted(self.config.times)
                if t <= bay_gio and self._fired.get(t) != hom_nay]

    #: Dinh dang moc thoi gian ghi ra file (cho kieu "delay").
    STAMP = "%Y-%m-%d %H:%M:%S"

    def delay_due(self, now: Optional[datetime] = None) -> bool:
        """Kieu "delay": da du so phut ke tu lan dang truoc chua.

        Chua dang lan nao thi dang ngay -- bat len la chay, khong bat nguoi dung
        ngoi cho het mot chu ky dau tien.
        """
        if not self._last_run:
            return True
        try:
            truoc = datetime.strptime(self._last_run, self.STAMP)
        except ValueError:
            return True                      # moc hong thi coi nhu chua chay
        cach = max(1, int(self.config.delay_minutes or 1))
        return (now or datetime.now()) - truoc >= timedelta(minutes=cach)

    def next_run_at(self, now: Optional[datetime] = None) -> Optional[datetime]:
        """Kieu "delay": luc nao dang bai ke tiep. None neu dang den han roi."""
        if not self._last_run:
            return None
        try:
            truoc = datetime.strptime(self._last_run, self.STAMP)
        except ValueError:
            return None
        cach = max(1, int(self.config.delay_minutes or 1))
        ke_tiep = truoc + timedelta(minutes=cach)
        return ke_tiep if ke_tiep > (now or datetime.now()) else None

    def tick(self, now: Optional[datetime] = None) -> Optional[str]:
        """Mot nhip kiem tra. Tra ve duong dan video vua dang, hoac None."""
        if not self.config.enabled or self._busy:
            return None
        if self.config.is_lich:
            return self._tick_lich(now)
        if self.config.schedule_mode == "delay":
            return self._tick_delay(now)
        return self._tick_list(now)

    def _tick_lich(self, now: Optional[datetime]) -> Optional[str]:
        """Trang DAT LICH: khung nao qua CA HAI CUA thi upload + hen gio bai do.

        Moi nhip chi chay MOT khung (rang buoc 4: moi luc chi mot video).
        """
        # KHONG CO VIDEO THI KHONG MO TRINH DUYET, va cung KHONG tieu mat khung:
        # kiem thu muc TRUOC khi goi lich_den_luot (ham do danh dau khung "da chay").
        # Con trong cua so do tre thi tha video vao van kip dang.
        video = self.next_video()
        if not video:
            mat = self.thu_muc_mat()
            if mat:
                self._bao_thu_muc_mat(mat)
            else:
                self._bao_thieu_video(now)
            return None

        # Tuong tu: CHUA chac dang duoc thi dung tieu khung. Het acc dung duoc
        # (checkpoint / dang xuat / loi 2 lan) hoac chua cai cach dang -> bo ve,
        # khung van con nguyen de luot sau chay (khong bi ghi "bo lo" oan).
        can = self._lich_chua_dang_duoc()
        if can:
            self._bao_chua_dang_duoc(can, now)
            return None

        den_han = self.lich_den_luot(now)     # da danh dau "da chay", khong chay bu
        if not den_han:
            return None
        khung = den_han[0]
        self._lich_chay = khung
        moc = f"{khung.get('chay')} → hẹn {khung.get('dang')}"
        if self.bao_bat_dau_lich is not None:
            self.bao_bat_dau_lich()           # bat rao: trang nay SAP mo trinh duyet

        self._busy = True
        ket = None
        try:
            ket = self.upload_now(video, moc)
            return ket
        finally:
            self._busy = False
            if ket:
                # Facebook da nhan lich -> ghi moc "xong". Khong ghi thi lan sau mo
                # tool len se thay khung nay la DO DANG (bo lo), dung nhu y do.
                self.lich_ghi_xong(khung.get("khoa") or "", now)
            if self.config.schedule_mode == "delay":
                # Bam gio SAU khi xong -> dong ho "cach N phut" dem tu luc ranh.
                self._last_run = (now or datetime.now()).strftime(self.STAMP)
                self.save()

    def _tick_delay(self, now: Optional[datetime]) -> Optional[str]:
        """Cu cach nhau ``delay_minutes`` phut thi dang mot bai.

        Dong ho chi bat dau chay SAU KHI dang xong va da dong trinh duyet, chu
        khong phai tu luc bat dau dang. Dang mot video co the mat vai phut; neu
        tinh gio tu luc bat dau thi hai bai lien nhau sat hon so phut da dat, ma
        video nang con co the chong lan len nhau.
        """
        if not self.delay_due(now):
            return None
        video = self.next_video()
        if not video:
            # Khong co video: van dat lai dong ho de khong quet lai moi 20 giay.
            self._last_run = (now or datetime.now()).strftime(self.STAMP)
            self.save()
            mat = self.thu_muc_mat()
            if mat:
                self._bao_thu_muc_mat(mat)
            else:
                self.note("Đến lượt đăng nhưng thư mục không có video nào.", ok=True)
            return None

        self._busy = True
        try:
            return self.upload_now(video, f"cách {self.config.delay_minutes} phút")
        finally:
            self._busy = False
            # Bam gio o DAY: da dang xong (hoac hong) va trinh duyet da dong.
            # ``now`` chi duoc truyen vao khi chay test voi dong ho gia -- luc do
            # khong co "luc xong" that su nen dung luon moc test dua.
            self._last_run = (now or datetime.now()).strftime(self.STAMP)
            self.save()

    def _tick_list(self, now: Optional[datetime]) -> Optional[str]:
        """Theo danh sach moc gio trong ngay."""
        den_han = self.due_times(now)
        if not den_han:
            return None
        moc = den_han[0]
        hom_nay = (now or datetime.now()).strftime("%Y-%m-%d")

        video = self.next_video()
        if not video:
            # Khong co video thi coi nhu da xong moc nay, khong quet lai lien tuc.
            self._fired[moc] = hom_nay
            self.save()
            self.note(f"Mốc {moc}: thư mục không có video nào.", ok=True)
            return None

        self._busy = True
        try:
            self._fired[moc] = hom_nay      # danh dau TRUOC khi dang: hong thi
            self.save()                      # cung khong dang lai cung mot moc
            return self.upload_now(video, moc)
        finally:
            self._busy = False

    def seconds_left(self, now: Optional[datetime] = None) -> Optional[int]:
        """Con bao nhieu giay nua toi luot dang. None neu khong o kieu "delay"."""
        if self.config.schedule_mode != "delay":
            return None
        if self._busy:
            return None                      # dang dang, chua bam gio
        ke_tiep = self.next_run_at(now)
        if ke_tiep is None:
            return 0                         # den luot roi
        return max(0, int((ke_tiep - (now or datetime.now())).total_seconds()))

    @staticmethod
    def _key(path: str) -> str:
        """Dau vet mot video: ten file + kich thuoc. Du de nhan ra da dang chua."""
        try:
            return f"{os.path.basename(path)}|{os.path.getsize(path)}"
        except OSError:
            return os.path.basename(path)

    def skip_past(self, now: Optional[datetime] = None) -> list[str]:
        """Danh dau cac moc gio DA QUA hom nay la xong -- khong chay bu.

        Bat tool luc 9h05 thi moc 9:00 (va cac moc truoc do) phai duoc bo qua,
        cho moc ke tiep. Chay bu don mot loat bai cu vao mot luc vua sai y
        "moi moc mot bai" vua de bi Facebook nghi ngo. Chi ap dung kieu danh
        sach moc gio; kieu "delay" co dong ho rieng cua no.

        (Dang chay lien tuc ma lo mot nhip thi due_times van dang bu nhu cu --
        ham nay chi duoc goi luc MO TOOL va luc nguoi dung BAT cong tac.)
        """
        # Trang DAT LICH co hai cua rieng (lich_den_luot) -- khong dung moc gio ngay.
        if self.config.schedule_mode == "delay" or self.config.is_lich:
            return []
        now = now or datetime.now()
        hom_nay = now.strftime("%Y-%m-%d")
        bay_gio = now.strftime("%H:%M")
        bo = [t for t in sorted(self.config.times)
              if t <= bay_gio and self._fired.get(t) != hom_nay]
        if not bo:
            return []
        for t in bo:
            self._fired[t] = hom_nay
        self.save()
        if self.config.enabled:
            sau = [t for t in sorted(self.config.times) if t > bay_gio]
            cho = f"chờ mốc {sau[0]}" if sau else "hết mốc hôm nay, chờ ngày mai"
            self.note(f"Bật lúc {bay_gio}: bỏ qua mốc đã qua "
                      f"({', '.join(bo)}) — {cho}.")
        return bo

    def begin_delay_countdown(self, now: Optional[datetime] = None) -> None:
        """Kieu "delay": BAT DAU DEM NGUOC tu bay gio (khong dang ngay).

        Goi luc MO TOOL: dat ``_last_run`` = bay gio -> phai cho du mot chu ky
        ``delay_minutes`` moi dang bai dau. Tranh "mo tool len la dang luon".

        Trang DAT LICH thi KHONG: no co khung gio rieng, nguoi dung tat tool mo lai
        DUNG GIO thi khung toi luot phai chay ngay (loi that 28/09: mo dung gio ma
        phai cho them N phut). Khoang cach giua hai bai van giu nho ``_last_run``
        cu; nhieu trang cung toi luot thi rao ``cach_tab_phut`` giai deu.
        """
        if self.config.schedule_mode != "delay" or self.config.is_lich:
            return
        self._last_run = (now or datetime.now()).strftime(self.STAMP)
        self.save()

    def run_delay_now(self) -> None:
        """Kieu "delay": cho dang NGAY o nhip toi (xoa ``_last_run``).

        Goi luc NGUOI DUNG VUA BAT cong tac: setup xong bat len la chay luon.
        """
        if self.config.schedule_mode != "delay":
            return
        self._last_run = ""
        self.save()

    # ---- Trang DAT LICH (target_kind = "lich") -----------------------------
    def lich_danh_gia(self, now: Optional[datetime] = None) -> list:
        """Cham TUNG khung theo HAI CUA cua ``core/lich_dang``.

        Tra ``[{"khung", "chay", "dang", "quy_doi", "ket_qua", "cua1", "cua2",
        "ly_do", "da_chay"}, ...]`` -- THUAN, khong dung dia/mang, de bang UI ve
        lai dung y het cai vong lap dung khi quyet dinh.
        """
        from core import lich_dang as ld
        cfg = self.config
        now = now or datetime.now()
        may = now.astimezone().tzinfo
        try:
            tz_page = ld.vung(cfg.mui_gio) if cfg.mui_gio else may
        except ld.LichError:
            tz_page = may
        now_utc = ld.ve_utc(now.replace(tzinfo=None), may)
        # QUAN TRONG: gio dat lich go KHONG kem ngay ("20:00") phai hieu la NGAY HOM
        # NAY CUA NUOC DO, khong phai ngay hom nay cua may. Sang 24/09 08:00 o VN thi
        # Brazil moi 23/09 22:00 -- lay ngay cua may se nhay sang hom sau, tre 24 tieng.
        now_page = ld.ra_may(now_utc, tz_page)

        # Chua toi "Gio bat dau chay" cua trang nay -> moi khung deu CHO.
        chua_mo = self.chua_toi_gio_bat_dau(now)
        # Kieu "cach N phut": khong co moc gio chay: khung DAU TIEN chua chay se
        # chay o nhip ke tiep cua dong ho delay; cac khung sau doi luot.
        theo_delay = cfg.schedule_mode == "delay"
        con_giay = self.seconds_left(now) if theo_delay else None
        da_gap_khung_cho = False

        ra = []
        for k in (cfg.khung_lich or []):
            chay_txt, dang_txt = str(k.get("chay") or ""), str(k.get("dang") or "")
            dong = {"khung": k, "chay": chay_txt, "dang": dang_txt, "quy_doi": "",
                    "dang_du": "", "ket_qua": "", "cua1": "", "cua2": "", "ly_do": "",
                    "khoa": "", "trang_thai": "", "da_chay": False}
            try:
                # NGAY dat lich = NGAY CUA MAY (ngay lam viec cua so), con GIO
                # hieu theo mui gio nuoc do. Truoc day neo theo ngay BEN DO: may
                # sang 26/09 ma Chicago con 25/09 21:14 -> tool nham cac gio cua
                # ngay 25 ben do (da qua het) -> bo qua sach, ca ngay khong chay gi.
                dang_nv = ld.doc_gio(dang_txt, now)
                dang_utc, gio_may = ld.quy_doi(dang_nv, tz_page, may)
                if theo_delay:
                    # Dong ho "cach N phut" quyet dinh luc chay, khong co moc gio go tay.
                    giay = 0 if con_giay is None else int(con_giay)
                    chay_nv = now + timedelta(seconds=giay)
                    chay_utc = now_utc + timedelta(seconds=giay)
                    dong["chay"] = (f"còn {giay // 60}′" if giay
                                    else f"tới lượt (cách {cfg.delay_minutes}′)")
                else:
                    chay_nv = ld.doc_gio(chay_txt, now)
                    chay_utc = ld.ve_utc(chay_nv, may)
            except ld.LichError as e:
                dong["ly_do"] = str(e)
                ra.append(dong)
                continue

            # So theo NGAY: khoa co ngay chay -> sang ngay moi tu reset, khong ket.
            dong["khoa"] = self._lich_khoa(k, chay_nv)
            dau = self._fired.get(dong["khoa"])
            if dau:
                # CHI "xong" moi tinh la da chay. Co "bat_dau" ma chua "xong" (tool
                # tat giua chung / dat lich hong) -> VAN CHAY LAI (nguoi dung chot
                # 2026-09-25: chi khi dang hoan tat moi bo qua khung).
                da_xong = bool(isinstance(dau, dict) and dau.get("xong"))
                dong["da_chay"] = da_xong
                dong["trang_thai"] = "xong" if da_xong else "do_dang"
            dong["dang_du"] = dang_nv.strftime("%d/%m %H:%M")   # ngay/gio DAY DU o nuoc do
            dong["quy_doi"] = gio_may.strftime("%d/%m %H:%M")
            dong.update(ld.danh_gia(now_utc, chay_utc, dang_utc,
                                    tre_phut=cfg.tre_phut, an_toan_phut=cfg.an_toan_phut))

            if dong["da_chay"]:
                # DA DANG XONG -> khong dung toi nua.
                xong_luc = (dau or {}).get("xong", "")
                dong["ket_qua"] = ld.DA_DANG
                dong["ly_do"] = f"đã đăng lúc {str(xong_luc)[11:16]}".rstrip(" ")
            elif chua_mo:
                # Chua toi gio bat dau: khong duoc coi la "bo lo" (chua he mo cua).
                dong["ket_qua"] = ld.CHO
                dong["ly_do"] = f"chưa tới giờ bắt đầu {cfg.gio_bat_dau}"
            elif theo_delay:
                if da_gap_khung_cho:
                    dong["ket_qua"] = ld.CHO
                    dong["ly_do"] = f"chờ lượt (mỗi {cfg.delay_minutes}′ một bài)"
                elif dong["ket_qua"] in (ld.QUA_GAN, ld.DA_QUA):
                    # Gio dat lich nay DA QUA (hoac qua gan) o nuoc do -> BO QUA khung,
                    # khung KE TIEP thanh ung vien. Khong dung im cho het ngay.
                    pass
                else:
                    da_gap_khung_cho = True      # khung dau tien con kip = khung toi luot
            if dong["trang_thai"] == "do_dang" and dong["ket_qua"] != ld.DA_DANG:
                dong["ly_do"] = "thử lại — lần trước chưa đặt lịch xong · " + dong["ly_do"]
            ra.append(dong)
        return ra

    def chua_toi_gio_bat_dau(self, now: Optional[datetime] = None) -> bool:
        """Chua toi "Gio bat dau chay" cua trang nay trong hom nay."""
        gio = (self.config.gio_bat_dau or "").strip()
        if not gio:
            return False
        now = now or datetime.now()
        try:
            g, p = gio.split(":")
            moc = now.replace(hour=int(g), minute=int(p), second=0, microsecond=0)
        except ValueError:
            return False
        return now < moc

    @staticmethod
    def _lich_khoa(khung: dict, ngay_chay: datetime) -> str:
        """Khoa so: CO NGAY CHAY -> sang ngay moi tu reset, khung chay lai duoc.

        Khong co ngay thi khung chi chay duoc DUNG MOT LAN roi ket vinh vien --
        dat 8 khung ma ca doi chi dang duoc 8 bai.
        """
        return f"lich:{ngay_chay.strftime('%Y-%m-%d')}|{khung.get('chay')}>{khung.get('dang')}"

    def lich_toi_luot(self, now: Optional[datetime] = None) -> list:
        """Cac khung QUA CA HAI CUA va CHUA chay -- CHI NHIN, KHONG danh dau gi.

        Phai tach khoi ``lich_den_luot``: ``is_due()`` duoc vong lap goi de HOI
        "co viec khong", neu no danh dau luon thi den luc ``tick()`` chay that
        khung da bi tieu mat -> khong dang gi ca ma so lai ghi "do dang" -> bo lo.
        """
        from core import lich_dang as ld
        return [d for d in self.lich_danh_gia(now)
                if d["ket_qua"] == ld.CHAY and not d["da_chay"]]

    def lich_den_luot(self, now: Optional[datetime] = None) -> list:
        """Lay MOT khung de chay ngay bay gio va danh dau no (khong chay bu).

        Chi ghi moc ``bat_dau``. Dang xong moi ghi ``xong`` (``lich_ghi_xong``).
        Co ``bat_dau`` ma khong co ``xong`` = tool tat giua chung -> BO LO han,
        KHONG chay lai: chay lai co the hen TRUNG hai bai cung mot gio.

        MOI LUOT MOT KHUNG (rang buoc 4): truoc day danh dau het cac khung cung
        toi luot nhung chi dang mot -> may khung con lai bi ghi "do dang" oan.
        """
        bo = self.lich_toi_luot(now)[:1]
        if not bo:
            return []
        luc = (now or datetime.now()).strftime(self.STAMP)
        for d in bo:
            self._fired[d["khoa"]] = {"bat_dau": luc}
        # Nho khung DANG CHAY: luc upload phai biet hen bai vao gio nao.
        self._lich_chay = bo[0]
        self._don_so_lich(now)      # PHAI cung dong ho voi luc cham, khong don nham dau vua ghi
        self.save()
        return bo

    def _lich_chua_dang_duoc(self) -> str:
        """Ly do KHONG THE dang luc nay (rong = dang duoc). Kiem TRUOC khi tieu khung."""
        if self.uploader is None:
            return "chưa cài cách đăng (uploader)"
        if self.accounts() and not self.accounts_usable():
            return "không còn acc nào dùng được (checkpoint / đăng xuất / lỗi 2 lần)"
        return ""

    def _bao_chua_dang_duoc(self, ly_do: str, now: Optional[datetime] = None) -> None:
        """Ghi nhat ky MOT LAN cho moi khung (vong lap 20 giay mot nhip)."""
        toi_luot = self.lich_toi_luot(now)
        khoa = toi_luot[0]["khoa"] if toi_luot else "?"
        if getattr(self, "_chua_dang_khoa", "") == khoa:
            return
        self._chua_dang_khoa = khoa
        self.note(f"Tới lượt nhưng chưa đăng được — {ly_do}. Khung vẫn còn, "
                  "chưa tính là bỏ lỡ.", ok=False)

    def thu_muc_mat(self) -> str:
        """Thu muc da DAT nhung KHONG CON tren may (vd o F: da rut / doi o). Rong = on.

        ``_post_folders`` lang le bo thu muc khong ton tai -> truoc day chi thay
        "khong co video", nguoi dung khong biet la do duong dan hong.
        """
        ds = [self.config.folder]
        if self.config.is_group:
            ds.insert(0, self.config.queue_dir)
        for d in ds:
            d = (d or "").strip()
            if d and not os.path.isdir(d):
                return d
        return ""

    def _bao_thu_muc_mat(self, mat: str) -> None:
        """Bao MOT LAN moi duong dan (vong lap 20 giay mot nhip) va GHI RA FILE."""
        if getattr(self, "_thu_muc_mat_bao", "") == mat:
            return
        self._thu_muc_mat_bao = mat
        self.note(f"Thư mục video KHÔNG TỒN TẠI: {mat} — ổ đĩa đã mất hoặc thư mục "
                  "bị đổi chỗ. Chọn lại thư mục video để trang chạy tiếp.", ok=False)
        self.save()

    def _bao_thieu_video(self, now: Optional[datetime] = None) -> None:
        """Toi luot ma thu muc rong: ghi nhat ky MOT LAN cho moi khung.

        Vong lap chay 20 giay mot nhip -- khong chan thi mot khung do tre 5 phut
        de ra 15 dong nhat ky giong het nhau.
        """
        toi_luot = self.lich_toi_luot(now)
        if not toi_luot:
            return
        khoa = toi_luot[0]["khoa"]
        if getattr(self, "_thieu_video_khoa", "") == khoa:
            return
        self._thieu_video_khoa = khoa
        self.note(f"Khung {toi_luot[0]['chay']}: thư mục không có video "
                  "— không mở trình duyệt.", ok=True)

    def lich_ghi_xong(self, khoa: str, now: Optional[datetime] = None) -> None:
        """Danh dau khung da dang XONG (Facebook da nhan lich)."""
        dau = self._fired.get(khoa)
        if not isinstance(dau, dict):
            dau = {"bat_dau": (now or datetime.now()).strftime(self.STAMP)}
        dau["xong"] = (now or datetime.now()).strftime(self.STAMP)
        self._fired[khoa] = dau
        self.save()

    def _don_so_lich(self, now: Optional[datetime] = None) -> int:
        """CHI giu lich su cua DUNG HOM NAY; sang ngay moi la xoa het, lam so moi.

        Nguoi dung chot: giu so cua ngay hom do thoi. Sang ngay sau xoa di lam lai
        -> khong the dinh dau cu cua hom qua ma bo mat mot khung gio cua hom nay,
        cung khong phinh file khi chay ca nam.
        """
        hom_nay = (now or datetime.now()).strftime("%Y-%m-%d")
        bo = [k for k in self._fired
              if k.startswith("lich:") and k[5:15] != hom_nay]
        for k in bo:
            self._fired.pop(k, None)
        return len(bo)

    def lich_hom_nay(self, now: Optional[datetime] = None) -> dict:
        """Dem cua HOM NAY: {"tong", "da_dang", "bo_lo", "cho"} -- de hien mot dong."""
        from core import lich_dang as ld
        cham = self.lich_danh_gia(now)
        dem = {"tong": len(cham), "da_dang": 0, "bo_lo": 0, "cho": 0}
        for d in cham:
            if d["ket_qua"] == ld.DA_DANG:
                dem["da_dang"] += 1
            elif d["ket_qua"] in (ld.CHO, ld.CHAY):
                dem["cho"] += 1
            else:
                dem["bo_lo"] += 1
        return dem

    def lich_gio_hen(self, now: Optional[datetime] = None) -> Optional[dict]:
        """Gio can HEN cho khung dang chay: {"ngay": "dd/mm/yyyy", "gio": "HH:MM"}.

        TRA VE GIO MAY (da quy doi), KHONG phai gio cua nuoc do.

        DA DO THAT (24/09, page Riley James 3): dien gio cua nuoc do ("07:00" gio
        Mexico) vao o hen lich thi Facebook HIEU LA GIO MAY -> gio do da qua ->
        FB tu choi va giu mac dinh (~1 tieng sau) -> ca 5 bai deu bi hen sai, cach
        nhau dung mot tieng. Business Suite nhan gio theo dong ho CUA TRINH DUYET.
        """
        from core import lich_dang as ld
        if not self.config.is_lich:
            return None
        khung = getattr(self, "_lich_chay", None)
        if not khung:
            # Bam "Dang thu 1 video" (khong qua vong lap) -> hen theo khung CHO dau tien.
            khung = next((d for d in self.lich_danh_gia(now)
                          if d["ket_qua"] in (ld.CHO, ld.CHAY) and not d["da_chay"]), None)
        if not khung:
            return None
        now = now or datetime.now()
        may = now.astimezone().tzinfo
        try:
            tz_page = ld.vung(self.config.mui_gio) if self.config.mui_gio else may
            # NGAY = ngay cua MAY (xem lich_danh_gia), GIO theo mui gio nuoc do.
            ben_do = ld.doc_gio(str(khung.get("dang") or ""), now)
            # ...roi QUY DOI ra gio may -- day moi la gio dien vao o hen lich cua FB.
            _utc, gio_may = ld.quy_doi(ben_do, tz_page, may)
        except ld.LichError:
            return None
        return {"ngay": gio_may.strftime("%d/%m/%Y"), "gio": gio_may.strftime("%H:%M"),
                "ben_do": ben_do.strftime("%d/%m %H:%M"),
                "mui_gio": self.config.mui_gio or ""}

    def lich_con_khung(self, now: Optional[datetime] = None) -> bool:
        """Hom nay con khung nao chua chay khong (CHO hoac dang toi luot).

        Het khung thi phai DUNG HAN cho sang ngay mai -- khong dem nguoc, khong
        hen "bai ke tiep" nua (nguoi dung bao: du 5/5 ma dong ho van chay).
        """
        from core import lich_dang as ld
        if not self.config.is_lich:
            return True
        return any(d["ket_qua"] in (ld.CHO, ld.CHAY) for d in self.lich_danh_gia(now))

    def lich_tom_tat(self, now: Optional[datetime] = None) -> str:
        """Mot dong trang thai cho trang dat lich.

        Dang chay:  "Ngày 24/09: đã chạy 3/6 video · 1 bỏ qua — bài kế 18:00 bên đó"
        Het khung:  "Ngày 24/09: đã chạy 6/6 video — xong hôm nay, chờ 07:00 ngày mai"
        """
        from core import lich_dang as ld
        now = now or datetime.now()
        cham = self.lich_danh_gia(now)
        if not cham:
            return "Chưa có khung nào."
        hn = self.lich_hom_nay(now)
        dau = f"Ngày {now.strftime('%d/%m')}: đã chạy {hn['da_dang']}/{hn['tong']} video"
        if hn["bo_lo"]:
            dau += f" · {hn['bo_lo']} bỏ qua"
        ke = next((d for d in cham if d["ket_qua"] in (ld.CHO, ld.CHAY)), None)
        if ke:
            gio = ke.get("dang_du") or ke["dang"]
            return f"{dau} — bài kế {gio} bên đó (≈ {ke['quy_doi']} giờ máy)"
        # Het khung hom nay -> noi ro se bat dau lai luc nao NGAY MAI.
        # Phai so theo GIO, khong so theo chuoi: "10:00" < "7:00" khi so chuoi.
        def _phut(txt):
            try:
                g = ld.doc_gio(str(txt), now)
                return g.hour * 60 + g.minute
            except ld.LichError:
                return 24 * 60
        gio_list = [str(k.get("dang") or "") for k in (self.config.khung_lich or [])
                    if str(k.get("dang") or "")]
        dau_tien = min(gio_list, key=_phut) if gio_list else ""
        return f"{dau} — xong hôm nay, chờ {dau_tien} ngày mai" if dau_tien else \
               f"{dau} — xong hôm nay, chờ sang ngày mai"

    def is_due(self, now: Optional[datetime] = None) -> bool:
        """Da toi luot dang chua -- chi xem dong ho, khong dung toi dia hay mang.

        Tach rieng de vong lap loc nhanh: chay 100 cong viec ma cai nao cung quet
        thu muc thi mot vong da het vai chuc giay.
        """
        if not self.config.enabled or self._busy:
            return False
        if self.gioi_han_den(now) is not None:
            return False                      # dang tam dung vi GIOI HAN DANG -> cho toi moc
        if self.config.is_lich:
            # CHI NHIN. Danh dau la viec cua _tick_lich luc chay that.
            return bool(self.lich_toi_luot(now))
        if self.config.schedule_mode == "delay":
            return self.delay_due(now)
        return bool(self.due_times(now))

    def accounts(self) -> list:
        """Danh sach acc dang (id), da bo trung, giu thu tu.

        Uu tien ``account_ids``; ban cu chi co ``account_id`` thi dung cai do.
        """
        ids = [a for a in (self.config.account_ids or []) if a]
        if not ids and self.config.account_id:
            ids = [self.config.account_id]
        seen, ra = set(), []
        for a in ids:
            if a not in seen:
                seen.add(a)
                ra.append(a)
        return ra

    def accounts_usable(self, now: Optional[datetime] = None) -> list:
        """Acc CON DUNG DUOC = accounts() tru acc da bi bo / checkpoint / dang xuat / DANG bi gioi han.

        Acc bi gioi han dang ma da qua moc "den" -> TU mo lai (ve "ok") ngay tai day.
        """
        self._mo_acc_het_gioi_han(now)
        return [a for a in self.accounts()
                if (self.acc_states.get(a) or {}).get("tt", ACC_TT_OK) == ACC_TT_OK]

    @property
    def acc_fail_limit(self) -> int:
        """So lan loi thi bo acc: X = 3 (nguoi dung chot 29/09), Facebook = 2 (ADR-014)."""
        return ACC_FAIL_LIMIT_X if self.platform == "x" else ACC_FAIL_LIMIT

    def _mo_acc_het_gioi_han(self, now: Optional[datetime] = None) -> None:
        now = now or datetime.now()
        doi = False
        for a, st in list(self.acc_states.items()):
            if (st or {}).get("tt") != ACC_TT_GIOI_HAN:
                continue
            try:
                den = datetime.strptime(st.get("den") or "", "%Y-%m-%d %H:%M:%S")
            except ValueError:
                den = now
            if now >= den:
                self.acc_states[a] = _acc_state_sach({})
                self.note(f"acc {a} hết thời gian giới hạn đăng — đăng lại từ bây giờ.", ok=True)
                doi = True
        if doi:
            self.save()

    def gioi_han_den(self, now: Optional[datetime] = None) -> Optional[datetime]:
        """Trang DANG TAM DUNG vi gioi han dang: tra moc SOM NHAT duoc dang lai; None = khong.

        Chi khi KHONG con acc nao dung duoc va co it nhat mot acc dang bi gioi han.
        """
        if not self.accounts() or self.accounts_usable(now):
            return None
        mocs = []
        for a in self.accounts():
            st = self.acc_states.get(a) or {}
            if st.get("tt") == ACC_TT_GIOI_HAN:
                try:
                    mocs.append(datetime.strptime(st.get("den") or "", "%Y-%m-%d %H:%M:%S"))
                except ValueError:
                    pass
        return min(mocs) if mocs else None

    def mo_lai_acc(self, acc: str = "") -> int:
        """Dat lai trang thai acc (mot acc, hoac tat ca) ve "ok", loi = 0. Tra so acc da mo lai.

        Goi khi nguoi dung da go checkpoint / dang nhap lai / muon cho acc thu tiep."""
        n = 0
        for a in list(self.acc_states):
            if acc and a != acc:
                continue
            st = self.acc_states.get(a) or {}
            if st.get("tt", ACC_TT_OK) != ACC_TT_OK or int(st.get("loi") or 0):
                n += 1
            self.acc_states[a] = _acc_state_sach({})
        if n:
            self.note(f"Mở lại {n} acc (đặt lại đếm lỗi / checkpoint) — "
                      f"acc dùng được: {', '.join(self.accounts_usable()) or '(không)'}.")
            self.save()
        return n

    def pick_account(self, now: Optional[datetime] = None) -> str:
        """Acc dang bai LUOT NAY, theo kich ban luan phien, CHI trong acc con dung duoc.

        Dang o giua ``upload_now`` -> tra acc DANG THU (co the la acc du phong sau khi
        acc dau hong) de uploader mo dung profile. Ngoai luot: mot acc -> luon acc do;
        nhieu acc: "day" -> moi ngay mot acc; "turn" -> xen ke moi bai (bo dem ``_turn``,
        tang sau moi bai dang duoc). Het acc dung duoc -> "".
        """
        if self._acc_dang:
            return self._acc_dang
        ids = self.accounts_usable()
        if not ids:
            return ""
        if len(ids) == 1:
            return ids[0]
        if self.config.rotate == "day":
            dt = now or datetime.now()
            ngay = dt.date().toordinal() if hasattr(dt, "date") else dt.toordinal()
            return ids[ngay % len(ids)]
        return ids[self._turn % len(ids)]

    def effective_kind(self) -> str:
        """Kieu bai dung khi quet/dang.

        Nhom: "auto" -- tu nhan dien tung file (video/anh/text), khong bat nguoi
        dung chon. Fanpage: qua Business Suite chi dang video.
        X: composer x.com nhan ca video / anh / bai chi chu -> cung "auto".
        """
        if self.config.is_group or self.platform == "x":
            return "auto"
        return "video"

    def next_video(self) -> Optional[str]:
        """Video dau tien (theo ten) chua tung dang va khong ai khac dang giu.

        Loai hai nhom:
          * video CHINH cong viec nay da dang -- neu khong, tat "dang xong xoa
            video" la no dang di dang lai mai mot video;
          * video cong viec KHAC dang giu hoac da dang tu cung thu muc -- hai tab
            tro vao mot thu muc ma khong loai thi cung mot video len hai fanpage.

        GIU CHO TRUOC roi moi kiem file da chep xong chua: buoc kiem mat 2 giay,
        de sau thi may cong viec cung nam trong do va cung lay mot video.
        """
        da_dang = set(self._posted)
        toi_da = self.video_toi_da_giay()
        # Quet CA HAI nguon (nhom): "Thu muc bai cho dang" TRUOC (uu tien dang bai
        # quet ve), roi "Thu muc video" (video le). Fanpage chi co mot thu muc.
        for thu_muc in self._post_folders():
            for path in fbupload.find_by_kind(thu_muc, self.effective_kind()):
                key = self._key(path)
                if key in da_dang or key in getattr(self, "_bo_video", ()):
                    continue
                # Video QUA DAI voi nen tang (X thuong <= 2:20) -> bo qua, KHONG mo trinh duyet.
                if toi_da and self._qua_dai(path, key, toi_da):
                    continue
                # "Chi dang bai da xao": bai trong hang doi ma chua xao xong thi bo qua.
                if self.config.only_post_xao:
                    it = self._queue_item_for(path)
                    if it is not None and it.get("xao") != "da":
                        continue
                if self.claim_check is not None and not self.claim_check(key):
                    continue                       # cong viec khac dang giu
                if fbupload.is_ready(path):
                    return path
                if self.unclaim is not None:       # chua chep xong -> tra cho lai
                    self.unclaim(key)
        return None

    def video_toi_da_giay(self) -> int:
        """Gioi han thoi luong video (giay) cua trang nay; 0 = khong gioi han."""
        try:
            rieng = int(self.config.video_toi_da_giay or 0)
        except (TypeError, ValueError):
            rieng = 0
        if rieng > 0:
            return rieng
        return X_VIDEO_TOI_DA_GIAY if self.platform == "x" else 0

    def _qua_dai(self, path: str, key: str, toi_da: int) -> bool:
        """Video nay dai hon ``toi_da`` giay khong. Doc 1 lan/file (nho theo dau vet), bao 1 lan."""
        if fbupload.kind_of(path) != "video":
            return False
        cache = self.__dict__.setdefault("_thoi_luong", {})
        if key not in cache:
            from . import mp4info
            cache[key] = mp4info.thoi_luong(path)
        giay = cache[key]
        if not giay or giay <= toi_da:
            return False
        da_bao = self.__dict__.setdefault("_da_bao_dai", set())
        if key not in da_bao:
            da_bao.add(key)
            from .mp4info import mm_ss
            self.note(f"Bỏ qua {os.path.basename(path)}: video dài {mm_ss(giay)} — quá "
                      f"{mm_ss(toi_da)} (acc X thường chỉ đăng được video tối đa 2:20). "
                      "Cắt ngắn video hoặc dùng acc Premium.", ok=False)
            self.save()
        return True

    def _post_folders(self) -> list[str]:
        """Cac thu muc poster lay bai de dang, khong trung, chi cai co that.

        Nhom: [Thu muc bai cho dang, Thu muc video]. Fanpage: [Thu muc video].
        """
        ra = []
        if self.config.is_group and (self.config.queue_dir or "").strip():
            ra.append(self.config.queue_dir.strip())
        if (self.config.folder or "").strip():
            ra.append(self.config.folder.strip())
        seen, out = set(), []
        for d in ra:
            n = os.path.normcase(os.path.abspath(d))
            if n in seen or not os.path.isdir(d):
                continue
            seen.add(n)
            out.append(d)
        return out

    def _acc_thu_tu(self) -> list:
        """Thu tu acc se THU cho mot bai: acc luot nay truoc, roi cac acc dung duoc con lai."""
        ids = self.accounts_usable()
        if not ids:
            return []
        dau = self.pick_account()
        i = ids.index(dau) if dau in ids else 0
        return ids[i:] + ids[:i]

    def _thu_mot_acc(self, video: str, loi_tua: str, nhan: str, ten: str, acc: str,
                     so_lan: int):
        """Thu dang MOT bai bang MOT acc, toi da ``so_lan`` lan.

        Tra (video_id, loi_cuoi, ket): ket = "ok" | "published" (da bam Dang roi moi loi ->
        coi nhu da dang) | "hong" (acc nay chiu, ghi trang thai acc) | "dung" (tool dang tat)."""
        acc_chu = f"acc {acc}: " if acc else ""
        self.note(f"{nhan}{acc_chu}đang đăng {ten}...", ok=True)
        loi_cuoi = None
        for lan in range(1, so_lan + 1):
            try:
                video_id = self.uploader(video, loi_tua)
                if lan > 1:
                    self.note(f"{nhan}{acc_chu}lần {lan} đăng được {ten}.", ok=True)
                self._acc_ok(acc)
                return video_id, None, "ok"
            except Exception as exc:
                loi_cuoi = exc
                loi_chu = str(exc)
                # CHONG DANG TRUNG: loi xay ra SAU KHI da bam "Dang" -> bai co the DA len.
                # Tuyet doi khong thu lai (ke ca bang acc khac); coi nhu DA DANG.
                if any(m in loi_chu for m in PUBLISHED_MARKS):
                    self.note(f"{nhan}{acc_chu}đã bấm Đăng rồi mới lỗi ({exc}) — "
                              f"coi như ĐÃ ĐĂNG, không đăng lại. Nên kiểm tra thủ công.",
                              ok=True)
                    self._acc_ok(acc)
                    return None, exc, "published"
                # Loi cua ACC (checkpoint / dang xuat) hay trang treo 0%: thu lai cung acc vo ich.
                con_thu = (lan < so_lan and STUCK_MARK not in loi_chu
                           and CHECKPOINT_MARK not in loi_chu and LOGOUT_MARK not in loi_chu
                           and GIOI_HAN_MARK not in loi_chu and VIDEO_TU_CHOI_MARK not in loi_chu)
                if not con_thu:
                    break
                self.note(f"{nhan}{acc_chu}lần {lan} hỏng ({exc}) — nghỉ "
                          f"{RETRY_PAUSE}s rồi thử lại.", ok=False)
                if self._stop_wait(RETRY_PAUSE):
                    return None, exc, "dung"         # dang tat tool, khong thu lai nua
        if VIDEO_TU_CHOI_MARK in str(loi_cuoi):
            return None, loi_cuoi, "hong"        # loi cua VIDEO: khong dem loi acc
        self._acc_hong(acc, loi_cuoi, nhan, ten)
        return None, loi_cuoi, "hong"

    def upload_now(self, video: str, moc: str = "") -> Optional[str]:
        """Dang mot video ngay. Dung chung cho canh gio va nut "Chay thu".

        Thu TUNG acc con dung duoc theo thu tu luan phien: acc hong -> chuyen NGAY sang acc
        ke tiep dang lai cung bai (nhieu acc). Mot acc -> thu lai RETRY_TIMES lan nhu cu.
        Nhat ky moi dong deu ghi ro acc nao dang bai nao."""
        if self.uploader is None:
            self.note("Chưa cài cách đăng (uploader).", ok=False)
            return None
        ten = os.path.basename(video)
        dau_vet = self._key(video)
        # Dang NHOM: khong co caption that thi de TRONG (khong lay ten file lam mo ta) — tranh
        # bai nhom hien ra ten file "qb_r..._56928". Fanpage va X: LAY TIEU DE (ten file) lam
        # caption khi khong co file .txt di kem (yeu cau nguoi dung 2026-09-28 cho tab Auto dang X).
        loi_tua = fbupload.caption_for(
            video, fbupload.kind_of(video),
            fallback_ten=not self.config.is_group)
        nhan = f"Mốc {moc}: " if moc else ""

        ung_vien = self._acc_thu_tu()
        if self.accounts() and not ung_vien:
            den = self.gioi_han_den()
            if den is not None:
                self.note(f"{nhan}tạm dừng vì GIỚI HẠN ĐĂNG — đăng lại lúc "
                          f"{den.strftime('%H:%M %d/%m')}.", ok=False)
                return None
            self.note(f"{nhan}không còn acc nào dùng được để đăng {ten} "
                      f"(checkpoint / đăng xuất / lỗi {self.acc_fail_limit} lần).", ok=False)
            self._dung_neu_het_acc()
            return None
        if not ung_vien:
            ung_vien = [""]                  # dang qua Graph API: khong can acc
        so_lan = RETRY_TIMES + 1 if len(ung_vien) == 1 else 1
        video_id, loi_cuoi, ket, acc_dang = None, None, "hong", ""
        for i, acc in enumerate(ung_vien):
            # Nguoi dung TAT "tu dong dang" giua chung (enabled=False + stop()) -> DUNG HAN ngay,
            # khong mo them browser cho acc ke tiep (yeu cau nguoi dung 2026-09-18).
            if self._stop.is_set() or not self.config.enabled:
                self.note(f"{nhan}đã tắt tự động đăng — dừng, không đăng {ten} bằng acc tiếp theo nữa.",
                          ok=False)
                return None
            khoa = None
            if i > 0 and acc and self.acc_lock is not None:
                # Acc du phong: xin khoa rieng cua no (co the dang ban o trang khac).
                khoa = self.acc_lock(acc)
                if not khoa.acquire(timeout=ACC_LOCK_WAIT):
                    self.note(f"{nhan}acc {acc} đang bận ở trang khác — bỏ qua acc này lượt này.",
                              ok=False)
                    continue
            self._acc_dang = acc
            try:
                video_id, loi_cuoi, ket = self._thu_mot_acc(video, loi_tua, nhan, ten, acc, so_lan)
            finally:
                self._acc_dang = ""
                if khoa is not None:
                    khoa.release()
            if ket != "hong":
                acc_dang = acc
                break
            if i + 1 < len(ung_vien):
                self.note(f"{nhan}chuyển sang acc {ung_vien[i + 1]} đăng lại {ten}.", ok=False)
        if ket == "dung":
            return None
        if ket == "hong" and VIDEO_TU_CHOI_MARK in str(loi_cuoi):
            # Nen tang KHONG NHAN video nay: bo qua han (khong chon lai), acc/trang khong bi tinh loi.
            if dau_vet not in self._bo_video:
                self._bo_video.append(dau_vet)
            self.note(f"{nhan}BỎ QUA {ten}: {loi_cuoi} — chuyển sang video kế tiếp.", ok=False)
            self._set_queue_status(video, "loi")
            self.save()
            return None
        if ket == "hong" and GIOI_HAN_MARK in str(loi_cuoi):
            # Bi GIOI HAN DANG: bai CHUA len, giu video; khong dem la luot hong / trang treo.
            self._set_queue_status(video, "cho")
            return None
        if ket == "hong":
            self._sau_khi_hong(nhan, ten, loi_cuoi)
            self._set_queue_status(video, "loi")
            self._dung_neu_het_acc()
            return None

        self._stuck = 0                  # dang duoc mot bai -> quen cac lan treo
        self._slot_fails = 0             # ... va quen luon cac luot hong truoc
        self.ok_count += 1
        # Xen ke moi bai: dang xong bai nay thi luot sau sang acc ke tiep.
        if self.config.rotate == "turn" and len(self.accounts_usable()) > 1:
            self._turn += 1
        self._set_queue_status(video, "da")   # danh dau da dang trong hang doi
        # Ghi dau vet TRUOC khi xoa file: xoa hong thi lan sau van khong dang lai.
        if dau_vet not in self._posted:
            self._posted.append(dau_vet)
            self._posted = self._posted[-500:]
        bang = f" bằng acc {acc_dang}" if acc_dang else ""
        # Bai tu THU MUC BAI CHO DANG: dang xong LUON xoa dong hang doi + xoa file
        # (theo yeu cau), du "dang xong xoa" co tat hay khong.
        la_bai_cho = self._is_queue_path(video)
        if la_bai_cho:
            self._remove_queue_row(video)
            da_xoa = fbupload.remove_video(video)
            # Xoa luon subfolder media phu (album) + ban XAO (AI), neu co.
            import shutil
            for suf in ("_media", "_xao"):
                sub = os.path.splitext(video)[0] + suf
                if os.path.isdir(sub):
                    shutil.rmtree(sub, ignore_errors=True)
            thua = "" if da_xoa else " (không xoá được file)"
            self.note(f"{nhan}ĐÃ ĐĂNG {ten}{bang} — xoá khỏi bài chờ đăng{thua}. {self.tally()}")
        elif self.config.delete_after:
            da_xoa = fbupload.remove_video(video)
            thua = "" if da_xoa else " (không xoá được file)"
            self.note(f"{nhan}ĐÃ ĐĂNG {ten}{bang}{thua} — {self.tally()}")
        else:
            self.note(f"{nhan}ĐÃ ĐĂNG {ten}{bang} (giữ lại file) — {self.tally()}")
        self.save()
        return video

    def _is_queue_path(self, path: str) -> bool:
        """File nay co nam trong 'Thu muc bai cho dang' khong."""
        qd = (self.config.queue_dir or "").strip()
        if not qd or not path:
            return False
        try:
            return os.path.normcase(os.path.abspath(os.path.dirname(path))) \
                == os.path.normcase(os.path.abspath(qd))
        except OSError:
            return False

    def _queue_item_for(self, path: str):
        """Item hang doi khop voi file (theo base / ten file). None neu khong co."""
        base = os.path.splitext(os.path.basename(path))[0]
        name = os.path.basename(path)
        for it in self.queue:
            if it.get("base") == base or os.path.basename(it.get("media") or "") == name:
                return it
        return None

    def _remove_queue_row(self, path: str) -> None:
        """Xoa dong hang doi khop voi file vua dang (theo base / ten file)."""
        base = os.path.splitext(os.path.basename(path))[0]
        name = os.path.basename(path)
        truoc = len(self.queue)
        self.queue = [it for it in self.queue
                      if not (it.get("base") == base
                              or os.path.basename(it.get("media") or "") == name)]
        if len(self.queue) != truoc:
            self.save()

    def so_con_lai(self) -> int:
        """So video/bai con trong (cac) thu muc cho dang."""
        con = 0
        for d in self._post_folders():
            con += len(fbupload.find_by_kind(d, self.effective_kind()))
        return con

    def thong_ke(self) -> dict:
        """Mot dong thong ke cho bang tong hop: ten, con lai, thanh cong, loi, trang thai."""
        return {"ten": self.name, "con_lai": self.so_con_lai(),
                "thanh_cong": int(self.ok_count), "loi": int(self.fail_count),
                "trang_thai": "Đang chạy" if self.config.enabled else "Đã dừng"}

    def tally(self) -> str:
        """Dong tong ket: da dang duoc bao nhieu, hong bao nhieu, con lai bao nhieu."""
        return (f"đã đăng {self.ok_count} video, lỗi {self.fail_count}, "
                f"còn {self.so_con_lai()} bài trong thư mục")

    def _stop_wait(self, giay: float) -> bool:
        """Nghi ``giay``, tra ve True neu trong luc do tool bao dung.

        Khong dung time.sleep tran: dong tool giua chung thi phai thoat duoc ngay
        chu khong ngoi cho het gio.
        """
        return self._stop.wait(giay)

    def _bao_console(self, text: str) -> None:
        """In thang ra console: loi nang phai dap vao mat, khong chi nam nhat ky."""
        try:
            print(f"[{self.name}] {text}", flush=True)
        except Exception:
            pass

    def _acc_ok(self, acc: str) -> None:
        """Acc vua dang duoc -> quen cac lan hong truoc cua acc do."""
        if acc and int((self.acc_states.get(acc) or {}).get("loi") or 0):
            self.acc_states[acc] = _acc_state_sach({})

    def _acc_hong(self, acc: str, exc: Exception, nhan: str, ten: str) -> None:
        """MOT acc chiu, khong dang duoc bai nay. Ghi trang thai THEO ACC:

          * checkpoint / dang xuat -> dung RIENG acc do (tt), acc khac van dang;
          * loi thuong -> dem; du ACC_FAIL_LIMIT lan -> "bo" acc do (chi dang acc con lai).
        Trang co dung hay khong do _dung_neu_het_acc quyet (het acc dung duoc moi dung)."""
        loi = str(exc)
        acc_chu = f"acc {acc} " if acc else ""
        self.note(f"{nhan}{acc_chu}đăng {ten} HỎNG — {loi}", ok=False)
        if not acc:
            return
        st = _acc_state_sach(self.acc_states.get(acc) or {})
        st["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if CHECKPOINT_MARK in loi:
            st["tt"], st["ly_do"] = ACC_TT_CHECKPOINT, loi[:200]
            bao = (f"ACC {acc} BỊ CHECKPOINT — Facebook giữ acc lại để xác minh. ĐÃ DỪNG acc này; "
                   "các acc khác vẫn đăng. Đăng nhập tay gỡ checkpoint rồi bấm 'Mở lại acc'.")
        elif GIOI_HAN_MARK in loi:
            den = datetime.now() + timedelta(hours=GIOI_HAN_GIO)
            st["tt"], st["ly_do"] = ACC_TT_GIOI_HAN, loi[:200]
            st["den"] = den.strftime("%Y-%m-%d %H:%M:%S")
            bao = (f"ACC {acc} BỊ GIỚI HẠN ĐĂNG (X: \"You've hit the daily post limit\") — TẠM DỪNG "
                   f"{GIOI_HAN_GIO} giờ, sẽ đăng bài lại lúc {den.strftime('%H:%M ngày %d/%m')}. "
                   "Bài này CHƯA lên, video giữ nguyên.")
        elif LOGOUT_MARK in loi:
            st["tt"], st["ly_do"] = ACC_TT_DANG_XUAT, loi[:200]
            bao = (f"ACC {acc} ĐÃ BỊ ĐĂNG XUẤT — cookie không còn dùng được. ĐÃ DỪNG acc này; "
                   "các acc khác vẫn đăng. Đăng nhập lại rồi bấm 'Mở lại acc'.")
        else:
            st["loi"] = int(st.get("loi") or 0) + 1
            if st["loi"] >= self.acc_fail_limit:
                st["tt"], st["ly_do"] = ACC_TT_BO, loi[:200]
                bao = (f"acc {acc} lỗi {st['loi']} lần — BỎ QUA acc này, chỉ đăng bằng acc còn lại. "
                       "Bấm 'Mở lại acc' khi muốn cho acc này đăng tiếp.")
            else:
                bao = (f"acc {acc} lỗi lần {st['loi']}/{self.acc_fail_limit} — "
                       f"lỗi đủ {self.acc_fail_limit} lần sẽ bỏ qua acc này.")
        self.acc_states[acc] = st
        self.note(bao, ok=False)
        if st["tt"] != ACC_TT_OK:
            self._bao_console(bao)
        self.save()

    def _dung_neu_het_acc(self) -> bool:
        """Het acc dung duoc (tat ca checkpoint / dang xuat / bi bo) -> DUNG trang nay. Tra True neu vua dung."""
        if not self.accounts() or self.accounts_usable() or not self.config.enabled:
            return False
        if self.gioi_han_den() is not None:
            return False                      # chi TAM DUNG toi moc het gioi han, khong tat trang
        self.config.enabled = False
        tt = {(self.acc_states.get(a) or {}).get("tt") for a in self.accounts()}
        if tt <= {ACC_TT_CHECKPOINT, ACC_TT_DANG_XUAT}:
            bao = ("ĐÃ DỪNG trang này: TẤT CẢ acc đều bị checkpoint / đăng xuất. Đăng nhập tay gỡ "
                   "checkpoint rồi bật lại (bật lại sẽ tự mở lại các acc).")
        else:
            bao = (f"ĐÃ DỪNG trang này: tất cả acc đều lỗi (hỏng {self.acc_fail_limit} lần hoặc checkpoint). "
                   "Thử ĐĂNG TAY một video: tay đăng ĐƯỢC là lỗi tool (nhắn admin, kèm data/hoso-loi); "
                   "tay cũng KHÔNG được là acc bị Facebook chặn. Bật lại sẽ tự mở lại các acc.")
        self.note(bao, ok=False)
        self._bao_console(bao)
        self.save()
        return True

    def _sau_khi_hong(self, nhan: str, ten: str, exc: Exception) -> None:
        """Xu ly mot LUOT dang hong (moi acc dung duoc deu da thu).

        Loi cua tung ACC (checkpoint / dang xuat / dem hong) da ghi o _acc_hong. O day:
          * trang treo 0% -> dem rieng, du STUCK_LIMIT lan lien tiep la dung han;
          * moi luot hong -> bo qua luot nay cho luot tiep theo; hong du
            SLOT_FAIL_LIMIT luot lien tiep thi tam dung va chi nguoi dung cach
            phan biet: dang tay DUOC la loi tool (nhan admin), dang tay cung
            KHONG duoc la acc bi Facebook chan.
        """
        loi = str(exc)
        self.fail_count += 1
        self.note(f"{nhan}đăng {ten} HỎNG (mọi acc đã thử) — {loi} — {self.tally()}", ok=False)

        if STUCK_MARK in loi:
            self._stuck += 1
            self.note(
                f"Trang bị lỗi, không tải lên được phần trăm nào "
                f"(lần {self._stuck}/{STUCK_LIMIT}). Vui lòng thử up tay một video "
                "để xem trang có vào được không.", ok=False)
            if self._stuck >= STUCK_LIMIT and self.config.enabled:
                self.config.enabled = False
                self.note(
                    f"ĐÃ DỪNG tự động đăng: {STUCK_LIMIT} lần liên tiếp trang lỗi, "
                    "không upload được. Hãy thử up tay rồi bật lại.", ok=False)
        else:
            self._stuck = 0

        self._slot_fails += 1
        if self._slot_fails < SLOT_FAIL_LIMIT:
            self.note(f"Bỏ qua lượt này, chờ lượt tiếp theo "
                      f"(hỏng {self._slot_fails}/{SLOT_FAIL_LIMIT} lượt liên tiếp).",
                      ok=False)
        elif self.config.enabled:
            self.config.enabled = False
            bao = (f"TẠM DỪNG trang này: {SLOT_FAIL_LIMIT} lượt liên tiếp đăng lỗi. "
                   "Hãy thử ĐĂNG TAY một video lên trang: nếu tay đăng ĐƯỢC thì lỗi "
                   "do tool — nhắn admin để fix (kèm thư mục data/hoso-loi); nếu tay "
                   "cũng KHÔNG đăng được thì acc đã bị Facebook chặn đăng bài.")
            self.note(bao, ok=False)
            self._bao_console(bao)
        self.save()

#: File liet ke cac cong viec (tab) dang co.
INDEX_NAME = "autoup-jobs.json"
#: So trang chay cung luc mac dinh. Moi trang la mot Firefox nen dung tham qua.
DEFAULT_PARALLEL = 3
#: Rao mac dinh giua cac trang DAT LICH (phut).
CACH_TAB_MAC_DINH = 3
#: Trang dat lich moi: gio bat dau chay + so phut gian cach kieu "cach N phut".
GIO_BAT_DAU_MAC_DINH = "09:00"
DELAY_LICH_MAC_DINH = 30
#: Gio dat lich video mac dinh cua mot trang dat lich moi (gio cua NUOC DO).
GIO_DAT_LICH_MAC_DINH = ("7:00", "9:00", "12:00", "15:00",
                         "18:00", "19:00", "20:00", "21:00")
#: Acc X thuong chi nhan video <= 2 phut 20 giay. Dai hon X bao "Some of your media failed
#: to load" (do that 29/09) -> tool BO QUA video do, chon video ke tiep.
X_VIDEO_TOI_DA_GIAY = 140
#: Tran tren, de khong ai go nham 500 roi treo may.
MAX_PARALLEL = 30
#: Ma gia cua luot "kham sang" trong tap _queued (cung mo Firefox nen tinh vao tran chay cung luc).
KHAM_ID = "__kham__"


def _clamp_parallel(value) -> int:
    """Gioi han so trang chay cung luc ve khoang cho phep."""
    try:
        so = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PARALLEL
    return max(1, min(MAX_PARALLEL, so))


class AutoUpManager:
    """Nhieu cong viec dang bai cung luc -- moi tab trong giao dien la mot cai.

    Vi sao mot vong lap chung chu khong moi cong viec mot luong: cac cong viec
    deu mo trinh duyet, chay chong nhau la tranh nhau profile va tranh nhau man
    hinh. Vong lap nay chay tuan tu, cong viec nao den han thi lam, xong moi sang
    cong viec khac.

    Moi cong viec luu ra mot file rieng (``autoup-<id>.json``); file dau tien giu
    ten cu ``autoup.json`` de ban da chay tu truoc mo len khong mat gi.
    """

    def __init__(self, data_dir: str, log: Optional[Callable[[str], None]] = None,
                 platform: str = "fb"):
        self.data_dir = data_dir
        #: Nen tang cua MOI job trong manager nay ("fb" | "x").
        self.platform = platform or "fb"
        self.index_path = os.path.join(data_dir, INDEX_NAME)
        self._log = log or (lambda _m: None)
        self.jobs: list = []
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._pool = None
        self._guard = threading.Lock()
        self._queued: set = set()       # da giao cho tho, chua chac da chay
        self._running: set = set()       # dang chay THAT su
        self._acc_locks: dict = {}
        self._claimed: dict = {}        # dau vet video -> cong viec dang giu
        #: So trang chay cung luc. Nhieu qua thi may khong ganh noi tung ay Firefox.
        self.max_parallel: int = DEFAULT_PARALLEL
        #: RAO giua cac trang DAT LICH: trang nay chay xong phai cach ngan nay phut
        #: moi toi trang ke. Chong ca dan acc cung nhay vao luc mo tool (hai trang
        #: dat cung "Gio bat dau chay" thi van bi giai ra).
        self.cach_tab_phut: int = CACH_TAB_MAC_DINH
        self._lich_chay_cuoi: str = ""      # luc trang lich gan nhat THAT SU bat dau dang
        self._lich_lan_giao: dict = {}      # job_id -> luc giao gan nhat (xoay vong)
        #: App cai vao: nhan mot cong viec, tra ve ham dang cho cong viec do.
        self.make_uploader: Optional[Callable] = None
        #: App cai vao: kham composer bang acc cua mot cong viec, khong dang gi.
        #: Nhan mot cong viec, tra ve (ok, chi_tiet).
        self.canary: Optional[Callable] = None
        #: Ngay da kham gan nhat ("YYYY-MM-DD") -- moi ngay chi kham mot lan.
        self.canary_day: str = ""
        self.load()

    # ---- danh sach cong viec ----------------------------------------
    def job_file(self, job_id: str) -> str:
        # Cong viec dau tien dung dung ten file cu, de ban cu mo len van chay.
        if job_id == "1":
            return os.path.join(self.data_dir, STATE_NAME)
        return os.path.join(self.data_dir, f"autoup-{job_id}.json")

    def load(self) -> None:
        try:
            with open(self.index_path, encoding="utf-8") as fh:
                muc = json.load(fh)
        except (OSError, ValueError):
            muc = None                      # chua co file -> ban cu, se chuyen doi

        if isinstance(muc, dict):
            self.max_parallel = _clamp_parallel(muc.get("max_parallel"))
            try:
                self.cach_tab_phut = max(0, int(muc.get("cach_tab_phut",
                                                        CACH_TAB_MAC_DINH)))
            except (TypeError, ValueError):
                self.cach_tab_phut = CACH_TAB_MAC_DINH
            self.canary_day = str(muc.get("canary_day") or "")
            muc = muc.get("jobs") or []
        if muc is None:
            # Chua co file danh sach: ban cu chi co mot cong viec trong autoup.json.
            muc = [{"id": "1", "name": "Trang 1"}]

        self.jobs = []
        for item in muc:
            ma = str(item.get("id") or "")
            if not ma:
                continue
            ten = str(item.get("name") or f"Trang {ma}")
            job = AutoUploader(self.data_dir, log=self._log, job_id=ma,
                               name=ten, path=self.job_file(ma),
                               platform=self.platform)
            # load() trong AutoUploader lay ten tu file cong viec; danh sach moi
            # la cai dung, nen dat lai sau khi doc file.
            job.name = ten
            self.jobs.append(job)
        self._wire()

    def save_index(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        data = {
            "max_parallel": self.max_parallel,
            "cach_tab_phut": self.cach_tab_phut,
            "canary_day": self.canary_day,
            "jobs": [{"id": j.job_id, "name": j.name} for j in self.jobs],
        }
        tmp = self.index_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.index_path)

    def _wire(self) -> None:
        for job in self.jobs:
            job.claim_check = (lambda key, j=job: self.try_claim(j, key))
            job.unclaim = (lambda key, j=job: self.release_key(j, key))
            job.acc_lock = self._acc_lock          # acc du phong cung duoc khoa
            job.bao_bat_dau_lich = self._lich_bat_rao
        if self.make_uploader is None:
            return
        for job in self.jobs:
            job.uploader = self.make_uploader(job)

    def _same_folder(self, job) -> list:
        """Cac cong viec KHAC dung chung thu muc voi cong viec nay."""
        thu_muc = os.path.normcase(os.path.abspath(job.config.folder or ""))
        if not thu_muc:
            return []
        ra = []
        for khac in self.jobs:
            if khac is job or not khac.config.folder:
                continue
            if os.path.normcase(os.path.abspath(khac.config.folder)) == thu_muc:
                ra.append(khac)
        return ra

    def try_claim(self, job, key: str) -> bool:
        """Xin giu mot video. True neu duoc. Kiem va giu trong CUNG mot nhip khoa.

        Hai tab tro vao cung mot thu muc la chuyen binh thuong (chia video cho hai
        fanpage). Khong giu cho thi ca hai deu lay video dau danh sach -> mot video
        len hai fanpage.
        """
        with self._guard:
            chu = self._claimed.get(key)
            if chu is not None and chu != job.job_id:
                return False
            for khac in self._same_folder(job):
                if key in khac._posted:
                    return False               # cung thu muc, no dang roi
            self._claimed[key] = job.job_id
            return True

    def release_key(self, job, key: str) -> None:
        with self._guard:
            if self._claimed.get(key) == job.job_id:
                del self._claimed[key]

    def _release(self, job) -> None:
        with self._guard:
            for k in [k for k, chu in self._claimed.items() if chu == job.job_id]:
                del self._claimed[k]

    def set_parallel(self, value: int) -> int:
        """Doi so trang chay cung luc. Ap dung NGAY cho lan giao viec ke tiep.

        KHONG tao pool moi: truoc day tao pool moi trong khi pool cu con chay not viec + hang
        cho -> dat 3 ma mo 5 Firefox (loi that 29/09). Gio tran do _phat_viec dem (_queued),
        pool tao mot lan du MAX_PARALLEL cho.
        """
        self.max_parallel = _clamp_parallel(value)
        self.save_index()
        return self.max_parallel

    def _con_cho(self) -> bool:
        """Con cho giao them trang khong (goi trong self._guard). Dem CA trang dang chay lan dang
        doi khoa acc -- moi trang da giao la mot Firefox sap/dang mo."""
        return len(self._queued) < max(1, int(self.max_parallel or 1))

    def set_uploader_factory(self, factory: Callable) -> None:
        self.make_uploader = factory
        self._wire()

    def get(self, job_id: str) -> Optional[AutoUploader]:
        for job in self.jobs:
            if job.job_id == job_id:
                return job
        return None

    def by_kind(self, kind: str) -> list:
        """Cac trang thuoc mot loai: "page" (fanpage), "group" (nhom) hay "lich" (dat lich)."""
        return [j for j in self.jobs if j.config.target_kind == kind]

    def add(self, name: str = "", kind: str = "page") -> AutoUploader:
        """Them mot trang moi. Ten trong thi tu dat theo so thu tu."""
        so = 1
        dang_co = {j.job_id for j in self.jobs}
        while str(so) in dang_co:
            so += 1
        ma = str(so)
        job = AutoUploader(self.data_dir, log=self._log, job_id=ma,
                           name=(name or f"Trang {ma}"), path=self.job_file(ma),
                           platform=self.platform)
        job.config.target_kind = kind if kind in ("group", "lich") else "page"
        if job.config.is_lich:
            # Mac dinh trang dat lich: bat dau 9h, chay kieu "cach N phut" = 30 phut,
            # va dien san danh sach gio dat lich video (nguoi dung chot 2026-09-24).
            job.config.gio_bat_dau = GIO_BAT_DAU_MAC_DINH
            job.config.schedule_mode = "delay"
            job.config.delay_minutes = DELAY_LICH_MAC_DINH
            job.config.khung_lich = [{"chay": "", "dang": g}
                                     for g in GIO_DAT_LICH_MAC_DINH]
        self.jobs.append(job)
        job.save()
        self.save_index()
        self._wire()
        return job

    def remove(self, job_id: str) -> bool:
        """Bo mot trang. Xoa het cung duoc -- hai tab co danh sach rieng, ep phai
        con mot trang o tab nay la vo ly khi tab kia dang co day."""
        job = self.get(job_id)
        if job is None:
            return False
        self.jobs = [j for j in self.jobs if j.job_id != job_id]
        try:
            os.remove(job.path)
        except OSError:
            pass
        self.save_index()
        return True

    def rename(self, job_id: str, name: str) -> bool:
        job = self.get(job_id)
        if job is None or not name.strip():
            return False
        job.name = name.strip()
        job.save()
        self.save_index()
        return True

    # ---- vong lap ----------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        for job in self.jobs:
            job._stop.clear()
            # Mo tool giua ngay: cac moc da qua coi nhu xong, khong don bai cu.
            try:
                job.skip_past()
                # Kieu "delay": MO TOOL thi DEM NGUOC lai tu dau, KHONG dang ngay.
                job.begin_delay_countdown()
            except Exception:
                pass
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        # Bao cho tung cong viec biet: cai nao dang nghi giua hai lan thu lai thi
        # thoat ngay, khong ngoi cho het gio.
        for job in self.jobs:
            job._stop.set()

    @property
    def busy(self) -> bool:
        return any(j.busy for j in self.jobs)

    def _loop(self) -> None:
        """Chon cac cong viec den han roi giao cho tho lam, toi da N cai cung luc.

        Hai thu phai chan bang duoc:

        * HAI CONG VIEC DUNG CHUNG MOT ACC. Lenh dang bai nam trong thu muc
          profile cua acc (qlfp-upload.json), hai cong viec cung acc chay mot luc
          se de len lenh cua nhau -- video cua trang nay bay sang trang kia. Nen
          moi acc mot o khoa, cung acc thi phai xep hang.
        * MOT CONG VIEC bi giao hai lan. Giu danh sach dang chay va bo qua nhung
          cai da o trong do.
        """
        while not self._stop.wait(5):
            try:
                self._phat_viec()
            except Exception as exc:
                self._log(f"Lỗi vòng lặp: {exc}")

    def _phat_viec(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        if self._pool is None:
            # Du MAX_PARALLEL tho: so trang chay THAT do _con_cho() chot, khong do co pool.
            self._pool = ThreadPoolExecutor(max_workers=MAX_PARALLEL,
                                            thread_name_prefix="autoup")
        if self.canary_due():
            with self._guard:
                duoc = self._con_cho()
                if duoc:
                    self._queued.add(KHAM_ID)        # kham cung mo mot Firefox -> tinh vao tran
            if duoc:
                # Danh dau TRUOC khi chay: kham hong cung khong duoc kham lai lien tuc.
                self.canary_day = datetime.now().strftime("%Y-%m-%d")
                self.save_index()
                self._pool.submit(self._kham)
        # Trang dat lich XOAY VONG: trang vua duoc giao xep xuong cuoi. Khong thi
        # trang dung dau ma khong co viec (thu muc rong) lan nao cung duoc hoi
        # truoc, trang sau khong bao gio toi luot (loi that 28/09).
        thu_tu = sorted(self.jobs, key=lambda j: self._lich_lan_giao.get(j.job_id, "")
                        if j.config.is_lich else "")
        da_giao_lich = False
        for job in thu_tu:
            if self._stop.is_set():
                return
            with self._guard:
                if job.job_id in self._queued:
                    continue
                # TRAN CUNG "Chay cung luc": du so trang da giao thi thoi, cho luot sau.
                if not self._con_cho():
                    return
                if job.config.is_lich:
                    # Moi nhip chi giao MOT trang dat lich; RAO kiem TRUOC is_due().
                    if da_giao_lich or self._lich_bi_rao(job):
                        continue
                if not job.is_due():
                    continue
                if job.config.is_lich:
                    # KHONG bat rao o day: giao roi chua chac co viec (thu muc rong ->
                    # khong mo trinh duyet). Rao bat khi trang THAT SU bat dau dang
                    # (_lich_bat_rao) -- truoc day trang rong chiem rao, bo doi trang khac.
                    da_giao_lich = True
                    self._lich_lan_giao[job.job_id] = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S.%f")
                self._queued.add(job.job_id)
            self._pool.submit(self._lam, job)

    def _lich_bat_rao(self) -> None:
        """Mot trang dat lich vua THAT SU bat dau dang -> cac trang khac cho du rao."""
        with self._guard:
            self._lich_chay_cuoi = datetime.now().strftime(AutoUploader.STAMP)

    def _lich_bi_rao(self, job, now: Optional[datetime] = None) -> bool:
        """Trang DAT LICH nay con phai cho cho du ``cach_tab_phut`` khong.

        Muc dich: bat tool len mot phat ca chuc trang cung den han -> chuc Firefox
        mo mot luc. Rao lai thi cac trang giai deu ra, moi trang cach nhau ngan ay
        phut (ke ca khi hai trang dat cung mot "Gio bat dau chay").
        """
        if not job.config.is_lich or self.cach_tab_phut <= 0:
            return False
        if not self._lich_chay_cuoi:
            return False
        try:
            truoc = datetime.strptime(self._lich_chay_cuoi, AutoUploader.STAMP)
        except ValueError:
            return False
        return (now or datetime.now()) < truoc + timedelta(minutes=self.cach_tab_phut)

    def rao_con_giay(self, now: Optional[datetime] = None) -> int:
        """Con bao nhieu giay nua moi het rao giua cac trang (0 = chay duoc ngay)."""
        if self.cach_tab_phut <= 0 or not self._lich_chay_cuoi:
            return 0
        try:
            truoc = datetime.strptime(self._lich_chay_cuoi, AutoUploader.STAMP)
        except ValueError:
            return 0
        con = (truoc + timedelta(minutes=self.cach_tab_phut)
               - (now or datetime.now())).total_seconds()
        return max(0, int(con))

    def canary_due(self, now: Optional[datetime] = None) -> bool:
        """Hom nay da den luc kham trang buoi sang chua.

        Kham TRUOC moc dang som nhat CANARY_AHEAD phut: Facebook doi giao dien
        thi biet tu som, truoc khi hang chuc trang cung hong vao moc dau tien.
        Tool mo muon hon gio do thi kham ngay nhip dau. Moi ngay mot lan.
        """
        if self.canary is None:
            return False
        now = now or datetime.now()
        if self.canary_day == now.strftime("%Y-%m-%d"):
            return False
        bat = [j for j in self.jobs if j.config.enabled]
        if not bat:
            return False
        moc = [min(j.config.times) for j in bat
               if j.config.schedule_mode != "delay" and j.config.times]
        if not moc:
            return True                  # toan kieu "delay": kham ngay nhip dau
        try:
            gio, phut = min(moc).split(":")
            hen = now.replace(hour=int(gio), minute=int(phut), second=0,
                              microsecond=0) - timedelta(minutes=CANARY_AHEAD)
        except ValueError:
            return True
        return now >= hen

    def _kham(self) -> None:
        """Kham trang buoi sang bang MOT acc: mo composer, khong dang gi ca."""
        try:
            self._kham_that()
        finally:
            with self._guard:
                self._queued.discard(KHAM_ID)

    def _kham_that(self) -> None:
        job = next((j for j in self.jobs
                    if j.config.enabled and j.config.target_kind != "group"
                    and j.accounts()), None)
        if job is None or self.canary is None:
            return
        try:
            with self._acc_lock(job.pick_account()):
                if self._stop.is_set():
                    return
                ok, chi_tiet = self.canary(job)
        except Exception as exc:
            ok, chi_tiet = False, str(exc)
        if ok:
            job.note(f"Khám sáng: composer bình thường ({chi_tiet}).", ok=True)
        else:
            bao = ("KHÁM SÁNG THẤY KHÁC LẠ — Facebook có thể vừa đổi giao diện: "
                   f"{chi_tiet}. Các mốc đăng hôm nay có thể hỏng; xem data/hoso-loi.")
            job.note(bao, ok=False)
            job._bao_console(bao)

    def _acc_lock(self, account_id: str) -> threading.Lock:
        """O khoa rieng cho tung acc. Acc rong cung co khoa rieng cua no."""
        key = account_id or "(chưa chọn acc)"
        with self._guard:
            khoa = self._acc_locks.get(key)
            if khoa is None:
                khoa = threading.Lock()
                self._acc_locks[key] = khoa
            return khoa

    def _lam(self, job) -> None:
        """Chay mot cong viec. Cung acc thi xep hang, khac acc thi chay song song.

        Acc khoa la acc LUOT NAY (job.pick_account) chu khong phai acc dau danh
        sach -- co the la acc2 khi dang luan phien. pick_account khong doi giua
        luot nen khoa dung acc ma buoc dang sap dung.
        """
        try:
            with self._acc_lock(job.pick_account()):
                if self._stop.is_set():
                    return
                with self._guard:
                    self._running.add(job.job_id)
                try:
                    job.tick()
                finally:
                    with self._guard:
                        self._running.discard(job.job_id)
        except Exception as exc:
            try:
                job.note(f"Lỗi khi chạy: {exc}", ok=False)
            except Exception:
                pass
        finally:
            self._release(job)
            with self._guard:
                self._queued.discard(job.job_id)
                self._running.discard(job.job_id)

    @property
    def running_ids(self) -> set:
        """Cac trang dang CHAY that su -- khong tinh cai dang xep hang."""
        with self._guard:
            return set(self._running)

    @property
    def waiting_ids(self) -> set:
        """Cac trang da den han, da nhan cho, nhung con doi den luot."""
        with self._guard:
            return set(self._queued) - set(self._running) - {KHAM_ID}
