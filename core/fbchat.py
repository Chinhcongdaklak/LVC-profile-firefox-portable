"""Kịch bản nhắn tin + sinh câu trả lời bạn bè bằng Gemini + điều khiển phiên messenger.

Tách tầng: file này KHÔNG import UI. Gemini TÁI DÙNG ``core/ai.py`` (ApiKeyPool, xoay
model, phân loại lỗi) — ``tra_loi()`` gọi ``ai.transform_text`` với ``caption_prompt``
sinh từ một ``KichBan`` (kịch bản), nên không lặp lại logic gọi mạng.

Facebook Messenger điều khiển qua PROCESS-SCRIPT AGENT (mở Firefox bình thường như
``fblogin``/``fbcreate``, KHÔNG BiDi) — messenger cần sự kiện tin cậy và tránh chống bot.
Bridge riêng: lệnh ghi ``<profile>/qlfp-msg.json``, agent báo ``qlfp-msg-result.json``.
"""

from __future__ import annotations

import dataclasses
import json
import os
import time
from dataclasses import dataclass
from typing import Callable, Optional

from . import ai

#: URL mở hộp thư (mở bình thường, không debug port).
MESSENGER_URL = "https://www.facebook.com/messages/"
CMD_NAME = "qlfp-msg.json"            # lệnh cho agent (khác qlfp-upload/create/weblogin)
RESULT_NAME = "qlfp-msg-result.json"  # agent báo về đây


class FbChatError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Kịch bản nhắn tin
# --------------------------------------------------------------------------
MO_DAU_VI = "Xin chào, tôi muốn làm quen với bạn để nói chuyện được nhé."
MO_DAU_EN = "Hello, I'd like to get to know you so we can chat."
SO_TIN_NGU_CANH = 5


@dataclass
class KichBan:
    """Một "kịch bản" trả lời: định tính cách + giọng điệu + chỉ dẫn thêm cho AI."""

    ten: str = ""
    persona: str = ""       # AI đóng vai ai / tính cách gì
    giong_dieu: str = ""    # thân mật / trang trọng / hài hước ...
    prompt_them: str = ""   # chỉ dẫn thêm tự do
    bat: bool = True        # kịch bản đang bật dùng hay không
    #: Tin MỞ ĐẦU gửi cho người CHƯA TỪNG nhắn (theo ngôn ngữ của người đó); rỗng -> dùng mặc định.
    mo_dau_vi: str = MO_DAU_VI
    mo_dau_en: str = MO_DAU_EN

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "KichBan":
        raw = dict(raw or {})
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def dung_prompt(self) -> str:
        """Ghép kịch bản thành chỉ dẫn (system prompt) cho Gemini.

        Là ``caption_prompt`` truyền cho ``ai.transform_text``: AI nhận tin nhắn bạn
        gửi (phần "text") và trả về CHỈ câu trả lời.
        """
        dong = ["Bạn đang thay tôi trả lời tin nhắn của một người bạn trên Facebook."]
        if self.persona.strip():
            dong.append(f"Vai/tính cách: {self.persona.strip()}.")
        if self.giong_dieu.strip():
            dong.append(f"Giọng điệu: {self.giong_dieu.strip()}.")
        if self.prompt_them.strip():
            dong.append(self.prompt_them.strip())
        dong.append(
            "Hãy viết câu trả lời tự nhiên, phù hợp ngữ cảnh, bằng ĐÚNG ngôn ngữ người bạn đang dùng "
            "(tiếng Việt hoặc tiếng Anh). "
            "CHỈ trả về nội dung câu trả lời, không giải thích, không thêm dấu ngoặc."
        )
        return " ".join(dong)


def default_path() -> str:
    from .config import TOOL_DIR
    return os.path.join(TOOL_DIR, "data", "fbchat.json")


def tai_kich_ban(path: str = "") -> list["KichBan"]:
    """Nạp danh sách kịch bản từ file. Thiếu file / hỏng -> trả []."""
    path = path or default_path()
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return []
    ds = raw.get("ds") if isinstance(raw, dict) else raw
    if not isinstance(ds, list):
        return []
    return [KichBan.from_dict(x) for x in ds if isinstance(x, dict)]


def luu_kich_ban(ds: list["KichBan"], path: str = "") -> None:
    """Ghi danh sách kịch bản ra file (tạo thư mục nếu thiếu)."""
    path = path or default_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"ds": [k.to_dict() for k in ds]}, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Sinh câu trả lời (Gemini / mock)
# --------------------------------------------------------------------------
_VI_CHU = "ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
_VI_TU = (" không ", " của ", " và ", " bạn ", " mình ", " nhé", " ạ", " ơi", " được ", " với ", " là ", " có ",
          " khong ", " chao ", " minh ", " duoc ", " cua ", " nhe ", " toi ", " ban oi", " hihi", " oi ")


def ngon_ngu(text: str) -> str:
    """"vi" nếu có dấu tiếng Việt / từ tiếng Việt quen; còn lại "en". Rỗng -> "vi"."""
    t = (text or "").lower()
    if not t.strip():
        return "vi"
    if any(c in _VI_CHU for c in t):
        return "vi"
    pad = f" {t} "
    if any(tu in pad for tu in _VI_TU):
        return "vi"
    return "en"


def cau_mo_dau(kich_ban: "KichBan", ngon: str) -> str:
    """Tin mở đầu theo ngôn ngữ (kịch bản có thể sửa; rỗng -> mặc định)."""
    if ngon == "en":
        return (getattr(kich_ban, "mo_dau_en", "") or "").strip() or MO_DAU_EN
    return (getattr(kich_ban, "mo_dau_vi", "") or "").strip() or MO_DAU_VI


def ngon_ngu_cua_ban(tin_gan: list) -> str:
    """Ngôn ngữ của NGƯỜI BẠN (tin không phải của mình); không có thì xét mọi tin."""
    cua_ban = [x.get("tin", "") for x in (tin_gan or []) if not x.get("cua_minh")]
    if not cua_ban:
        cua_ban = [x.get("tin", "") for x in (tin_gan or [])]
    return ngon_ngu(" ".join(cua_ban))


def tra_loi_ngu_canh(tin_gan: list, kich_ban: "KichBan", cfg: "ai.AiConfig",
                     log: Optional[Callable[[str], None]] = None) -> str:
    """AI đọc ``tin_gan`` (tối đa SO_TIN_NGU_CANH tin, cũ -> mới, mỗi tin {tin, cua_minh}) rồi đề xuất
    câu chat TIẾP THEO trả lời tin/câu hỏi GẦN NHẤT của bạn. Rỗng -> "". mock -> câu mẫu."""
    gan = [x for x in (tin_gan or []) if (x.get("tin") or "").strip()][-SO_TIN_NGU_CANH:]
    if not gan:
        return ""
    ngon = ngon_ngu_cua_ban(gan)
    cuoi = gan[-1]
    if cfg.provider != "gemini":
        ten = (kich_ban.ten or "mock").strip()
        return (f"[{ten}] ({ngon}) tiếp theo sau “{cuoi['tin'][:50]}” — "
                + ("Nice, tell me more!" if ngon == "en" else "Hay quá, kể mình nghe thêm đi!"))
    nhan_toi = "Tôi" if ngon == "vi" else "Me"
    nhan_ban = "Bạn" if ngon == "vi" else "Friend"
    lich_su = "\n".join(f"{nhan_toi if x.get('cua_minh') else nhan_ban}: {x['tin']}" for x in gan)
    chi_dan = (
        kich_ban.dung_prompt()
        + f" Dưới đây là {len(gan)} tin nhắn gần nhất của cuộc trò chuyện (cũ -> mới). "
        + f"Hãy viết câu chat TIẾP THEO của {nhan_toi}, trả lời trực tiếp tin/câu hỏi GẦN NHẤT của {nhan_ban}, "
        + ("bằng tiếng Anh." if ngon == "en" else "bằng tiếng Việt.")
        + " CHỈ trả về câu chat."
    )
    cfg2 = dataclasses.replace(cfg, caption_prompt=chi_dan)
    return ai.transform_text(lich_su, cfg2, log)


def tra_loi(tin_nhan: str, kich_ban: "KichBan", cfg: "ai.AiConfig",
            log: Optional[Callable[[str], None]] = None) -> str:
    """Sinh câu trả lời cho MỘT tin nhắn đến theo kịch bản.

    * tin nhắn rỗng -> "" (không gọi mạng).
    * provider "mock" -> câu trả lời mẫu (thử luồng, không gọi mạng).
    * provider "gemini" -> ``ai.transform_text`` với caption_prompt = kịch bản.
      Ném ``ai.AiError`` khi lỗi thật (hết quota / key sai ...).
    """
    if not (tin_nhan or "").strip():
        return ""
    if cfg.provider == "gemini":
        cfg2 = dataclasses.replace(cfg, caption_prompt=kich_ban.dung_prompt())
        return ai.transform_text(tin_nhan, cfg2, log)
    # mock: câu trả lời mẫu, không gọi mạng
    ten = (kich_ban.ten or "mock").strip()
    return f"[{ten}] Mình đã nhận: “{tin_nhan.strip()[:60]}” — rất vui được nhắn với bạn!"


# --------------------------------------------------------------------------
# Cầu nối file cho agent messenger (bridge qlfpm:*)
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
    """Chờ agent báo về một trong các state trong ``muon`` (hoặc 'error'). Hết giờ -> None.

    Ghi lại các báo chẩn đoán 'seen' để nhật ký cho biết agent đang thấy gì."""
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
                    log(f"  · {det[:120]}")
            elif st in muon:
                return r
            elif st == "error":
                log(f"agent lỗi: {str(r.get('detail'))[:120]}")
                return r
        time.sleep(1.0)
    return None


def _quet_tin(manager, account, profile: str, so_toi_da: int, log) -> list:
    """Bảo agent quét hộp thư, trả list {id, ban, tin} các hội thoại có tin bạn CHƯA trả lời.

    Phần trình duyệt thật; thước offline (mc04) thay hàm này. Không ném — lỗi -> []."""
    _put_cmd(profile, {"action": "scan", "so_toi_da": int(so_toi_da)})
    # 150s: moi hoi thoai mo cho o soan toi 16s + 4s doc, 5 hoi thoai + 30s cho render -> 75s la qua sat (da het gio that).
    r = _cho_state(profile, {"scanned"}, timeout=150.0, log=log)
    if not r or r.get("state") != "scanned":
        log("  · agent chưa báo kết quả quét (hết giờ). Kiểm tra acc đã đăng nhập Messenger chưa.")
        return []
    # chẩn đoán: trang, số hội thoại, vì sao rỗng
    url = str(r.get("url") or "")
    tong = r.get("tong_link")
    why = str(r.get("why") or "")
    if url:
        log(f"  · trang: {url}" + (f" | {tong} hội thoại" if tong is not None else ""))
    if why:
        log(f"  · {why}")
    if r.get("mau"):
        log(f"  · mẫu dòng: {str(r.get('mau'))[:80]}")
    if r.get("dom"):
        log(f"  · DOM: {str(r.get('dom'))[:500]}")
    items = r.get("items") or []
    out = []
    for it in items[: int(so_toi_da)]:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        out.append({"id": str(it["id"]), "ban": str(it.get("ban", "")),
                    "tin": str(it.get("tin", ""))})
    return out


#: id hoi thoai -> ly do agent khong gui duoc (dien sau _gui_tra_loi; chay_mot_acc dua vao row["ly_do"]).
_LY_DO_GUI: dict = {}


def _gui_tra_loi(manager, account, profile: str, replies: list, log) -> set:
    """Bảo agent gửi các câu trả lời. Trả set id đã gửi thành công.

    HÀNH ĐỘNG RA NGOÀI (tới người thật) — chỉ chạy khi người dùng bấm Bắt đầu. Không ném."""
    if not replies:
        return set()
    _put_cmd(profile, {"action": "reply",
                       "replies": [{"id": r["id"], "ban": r.get("ban", ""),
                                    "tra_loi": r["tra_loi"]} for r in replies]})
    r = _cho_state(profile, {"reply-sent"}, timeout=90.0, log=log)
    if not r or r.get("state") != "reply-sent":
        log("  · agent không báo kết quả gửi (hết giờ 90s).")
        return set()
    sent = {str(x) for x in (r.get("sent") or [])}
    _LY_DO_GUI.clear()
    _LY_DO_GUI.update({str(k): str(v) for k, v in (r.get("ly_do") or {}).items()})
    # Ghi ro VI SAO khong gui duoc (agent note tung buoc: khong go duoc / khong gui duoc / e2ee...).
    if len(sent) < len(replies):
        if r.get("detail"):
            log(f"  · agent: {str(r['detail'])[:200]}")
        for dong in (r.get("log") or [])[-8:]:
            if any(k in str(dong) for k in ("KHONG", "khong", "e2ee", "da gui", "da go")):
                log(f"  · {str(dong)[:200]}")
    return sent


# --------------------------------------------------------------------------
# Điều khiển một acc: quét tin -> sinh trả lời -> gửi
# --------------------------------------------------------------------------
def chay_mot_acc(manager, account, kich_ban: "KichBan", cfg: "ai.AiConfig", *,
                 so_toi_da: int = 5,
                 log: Optional[Callable[[str], None]] = None) -> list:
    """Mở Messenger cho acc, đọc tối đa ``so_toi_da`` tin bạn mới, sinh câu trả lời theo
    ``kich_ban`` và gửi. Trả list ``{ban, tin_den, tra_loi, trang_thai}``. Không ném."""
    noi = log or (lambda _m: None)
    profile = manager.profile_dir(account)
    try:
        manager.close(account, wait=6.0)
    except OSError:
        pass
    manager.configure(account)
    _clear(profile)
    noi(f"[{account.id}] mở Messenger, quét tin bạn mới...")
    manager.launch(account, url=MESSENGER_URL)

    items = _quet_tin(manager, account, profile, so_toi_da, noi)
    if not items:
        noi(f"[{account.id}] không có tin bạn mới cần trả lời.")
        _dong(manager, account)
        _clear(profile)
        return []
    noi(f"[{account.id}] có {len(items)} tin cần trả lời.")

    out: list = []
    gui_duoc: list = []
    for it in items:
        trang_thai = "dang"
        tl = ""
        try:
            if it.get("chua_tung_nhan"):
                # Chưa từng nhắn với người này -> tin MỞ ĐẦU theo ngôn ngữ của họ (không gọi AI).
                ngon = ngon_ngu_cua_ban(it.get("tin_gan") or [{"tin": it.get("tin", "")}])
                tl = cau_mo_dau(kich_ban, ngon)
                it["mo_dau"] = True
                noi(f"[{account.id}] “{it['ban']}”: chưa từng nhắn -> gửi tin mở đầu ({ngon}).")
            elif it.get("tin_gan"):
                # Đã nói chuyện -> AI đọc 5 tin gần nhất, trả lời tin/câu hỏi gần nhất.
                tl = tra_loi_ngu_canh(it["tin_gan"], kich_ban, cfg, noi)
            else:
                tl = tra_loi(it["tin"], kich_ban, cfg, noi)
        except ai.AiError as exc:
            trang_thai = "xao_loi"
            noi(f"[{account.id}] AI lỗi cho “{it['ban']}”: {exc}")
        if trang_thai != "xao_loi" and tl.strip():
            gui_duoc.append({"id": it["id"], "ban": it["ban"], "tra_loi": tl})
        elif trang_thai != "xao_loi":
            trang_thai = "xao_loi"   # không sinh được câu trả lời -> coi như lỗi AI
        out.append({"id": it["id"], "ban": it["ban"], "tin_den": it["tin"],
                    "tra_loi": tl, "trang_thai": trang_thai, "mo_dau": bool(it.get("mo_dau"))})

    sent = _gui_tra_loi(manager, account, profile, gui_duoc, noi) if gui_duoc else set()
    for row in out:
        if row["trang_thai"] == "xao_loi":
            continue
        row["trang_thai"] = "da_gui" if row["id"] in sent else "loi"
        if row["trang_thai"] == "loi":
            row["ly_do"] = _LY_DO_GUI.get(str(row["id"]), "")
    _dong(manager, account)
    _clear(profile)
    dem_ok = sum(1 for r in out if r["trang_thai"] == "da_gui")
    noi(f"[{account.id}] xong: {dem_ok}/{len(out)} tin đã gửi.")
    return out


def _dong(manager, account) -> None:
    try:
        manager.close(account, wait=8.0)
    except OSError:
        pass


def mo_khoa_e2ee(manager, account, pin: str, *,
                 log: Optional[Callable[[str], None]] = None) -> dict:
    """Thiết lập/nhập mã PIN bảo mật để mở khoá chat mã hoá đầu cuối (một lần / thiết bị).

    PIN chỉ đi qua file lệnh (xoá sau, _clear), KHÔNG lưu ra đĩa/log. Trả {ok, detail}."""
    noi = log or (lambda _m: None)
    if not (pin or "").strip():
        return {"ok": False, "detail": "chưa nhập mã PIN"}
    profile = manager.profile_dir(account)
    try:
        manager.close(account, wait=6.0)
    except OSError:
        pass
    manager.configure(account)
    _clear(profile)
    noi(f"[{account.id}] mở Messenger, thiết lập mã PIN bảo mật...")
    manager.launch(account, url=MESSENGER_URL)
    # mở một hội thoại bất kỳ để gặp màn Khôi phục, rồi agent tự thao tác
    _put_cmd(profile, {"action": "setup_pin", "pin": str(pin)})
    r = _cho_state(profile, {"pin-done"}, timeout=90.0, log=noi)
    _dong(manager, account)
    _clear(profile)     # xoá lệnh chứa PIN
    if not r:
        return {"ok": False, "detail": "hết giờ, agent chưa báo kết quả"}
    ok = bool(r.get("ok"))
    detail = str(r.get("detail") or "")
    noi(f"[{account.id}] mở khoá PIN: {'THÀNH CÔNG' if ok else 'CHƯA XONG'} — {detail}")
    return {"ok": ok, "detail": detail}


# --------------------------------------------------------------------------
# Chạy nhiều vòng theo thời gian: mỗi vòng mỗi acc nhắn N người; nghỉ rồi mở lại
# --------------------------------------------------------------------------
def chay_lich(manager, accounts: list, kich_ban: "KichBan", cfg: "ai.AiConfig", *,
              so_nguoi: int = 5, tong_phut: int = 60, cach_phut: int = 15,
              nen_dung: Optional[Callable[[], bool]] = None,
              log: Optional[Callable[[str], None]] = None,
              on_row: Optional[Callable] = None,
              _now: Callable[[], float] = time.time,
              _sleep: Callable[[float], None] = time.sleep) -> dict:
    """Chạy nhiều vòng trong ``tong_phut`` phút.

    Mỗi vòng: mỗi acc gọi :func:`chay_mot_acc` nhắn tối đa ``so_nguoi`` người. Hết một
    vòng, nếu còn thời gian thì chờ ``cach_phut`` phút (kiểm tra dừng/hết giờ từng nhịp)
    rồi MỞ LẠI vòng tiếp. Dừng khi quá ``tong_phut`` hoặc ``nen_dung()`` trả True.

    ``_now``/``_sleep`` tiêm được để kiểm thử nhanh (không chờ thật). Trả tổng kết
    ``{so_vong, tong_gui, so_acc}``. Không ném.
    """
    noi = log or (lambda _m: None)
    dung = nen_dung or (lambda: False)
    het_han = _now() + max(0, int(tong_phut)) * 60
    so_vong = 0
    tong_gui = 0
    while _now() < het_han:
        if dung():
            break
        so_vong += 1
        noi(f"=== Vòng {so_vong} — nhắn {so_nguoi} người/acc ===")
        for acc in accounts:
            if dung():
                break
            try:
                rows = chay_mot_acc(manager, acc, kich_ban, cfg,
                                    so_toi_da=so_nguoi, log=noi)
            except Exception as exc:  # noqa: BLE001
                noi(f"[{getattr(acc, 'id', '?')}] lỗi: {exc}")
                rows = []
            tong_gui += sum(1 for r in rows if r.get("trang_thai") == "da_gui")
            if on_row:
                try:
                    on_row(acc, rows)
                except Exception:  # noqa: BLE001
                    pass
        if dung() or _now() >= het_han:
            break
        # còn thời gian -> chờ cách_phut phút rồi vòng tiếp (nghỉ từng nhịp để dừng kịp)
        cho_den = _now() + max(0, int(cach_phut)) * 60
        if cho_den > _now():
            noi(f"Chờ {cach_phut} phút rồi mở lại...")
        while _now() < cho_den:
            if dung() or _now() >= het_han:
                break
            _sleep(min(5.0, cho_den - _now()))
    noi(f"Kết thúc: {so_vong} vòng, {tong_gui} tin đã gửi.")
    return {"so_vong": so_vong, "tong_gui": tong_gui, "so_acc": len(accounts)}
