"""LỊCH ĐĂNG (thử nghiệm trước khi tích hợp vào tab Auto đăng fanpage) — lõi THUẦN, không UI.

Mỗi video có HAI mốc giờ:
  * ``gio_chay``  — giờ MÁY (local): lúc tool bắt đầu làm việc với video đó.
  * ``gio_dang``  — giờ theo MÚI GIỜ PAGE: tool tự quy đổi ra giờ máy/UTC.

HAI CỬA kiểm tra. Trượt cửa nào thì BỎ QUA khung đó, sang khung kế — KHÔNG chạy bù:
  Cửa 1 — giờ chạy tới chưa (có ``tre_phut`` độ trễ cho phép, mặc định 5).
  Cửa 2 — từ BÂY GIỜ tới giờ đăng còn ≥ ``an_toan_phut`` (mặc định 30) không.

Mọi so sánh đều quy về UTC (không bao giờ so trực tiếp hai múi giờ).
Kiểm tra 3 lần: lúc NHẬP lịch (``hop_le_khi_nhap``), lúc MỞ tool (quét ``danh_gia`` cả danh sách),
và NGAY TRƯỚC KHI upload (``danh_gia`` lại — cửa 2 có thể đã hết kịp).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

#: Độ trễ cho phép của CỬA 1 (phút) — máy có thể bận vài giây/phút.
TRE_MAC_DINH = 5
#: Khoảng an toàn của CỬA 2 (phút) — upload + Facebook xử lý + mức tối thiểu FB yêu cầu.
AN_TOAN_MAC_DINH = 30

# ---- Kết quả của một khung -------------------------------------------------
CHO = "cho"                       # chưa tới giờ chạy -> chờ
CHAY = "chay"                     # qua cả 2 cửa -> upload + hẹn lịch
BO_LO = "bo_lo_gio_chay"          # trượt cửa 1
QUA_GAN = "bo_qua_qua_gan"        # trượt cửa 2: giờ đăng quá gần
DA_QUA = "bo_qua_da_qua"          # trượt cửa 2: giờ đăng đã qua
OK = "ok"                         # cửa 2 đạt
DA_DANG = "da_dang"               # khung này HÔM NAY đã đăng xong rồi

NHAN = {
    CHO: "Chờ",
    CHAY: "Chạy",
    BO_LO: "Bỏ lỡ giờ chạy",
    QUA_GAN: "Bỏ qua – giờ đăng quá gần",
    DA_QUA: "Bỏ qua – giờ đăng đã qua",
    DA_DANG: "Đã đăng",
}
#: Các trạng thái BỎ QUA (video vẫn nằm lại danh sách, người dùng tự đặt khung mới).
BO_QUA = (BO_LO, QUA_GAN, DA_QUA)

#: Danh sách múi giờ theo NƯỚC, THỨ TỰ ƯU TIÊN người dùng yêu cầu:
#: Mexico → Mỹ → Brazil → Thái → Nhật → Hàn → Philippines → Đức → Pháp → Anh → châu Âu → còn lại.
#: Nhãn KHÔNG ghi cứng offset (DST đổi theo mùa) — UI tự gắn "(UTC±X)" theo giờ hiện tại.
DANH_SACH_MUI_GIO = [
    # --- ưu tiên ---
    ("Mexico – Mexico City", "America/Mexico_City"),
    ("Mexico – Cancún", "America/Cancun"),
    ("Mexico – Tijuana", "America/Tijuana"),
    ("Mỹ – New York (miền Đông)", "America/New_York"),
    ("Mỹ – Chicago (miền Trung)", "America/Chicago"),
    ("Mỹ – Denver (miền Núi)", "America/Denver"),
    ("Mỹ – Phoenix", "America/Phoenix"),
    ("Mỹ – Los Angeles (miền Tây)", "America/Los_Angeles"),
    ("Mỹ – Anchorage", "America/Anchorage"),
    ("Mỹ – Honolulu", "Pacific/Honolulu"),
    ("Brazil – São Paulo", "America/Sao_Paulo"),
    ("Brazil – Manaus", "America/Manaus"),
    ("Brazil – Fortaleza", "America/Fortaleza"),
    ("Thái Lan – Bangkok", "Asia/Bangkok"),
    ("Nhật Bản – Tokyo", "Asia/Tokyo"),
    ("Hàn Quốc – Seoul", "Asia/Seoul"),
    ("Philippines – Manila", "Asia/Manila"),
    ("Đức – Berlin", "Europe/Berlin"),
    ("Pháp – Paris", "Europe/Paris"),
    ("Anh – London", "Europe/London"),
    # --- châu Âu ---
    ("Tây Ban Nha – Madrid", "Europe/Madrid"),
    ("Bồ Đào Nha – Lisbon", "Europe/Lisbon"),
    ("Ý – Rome", "Europe/Rome"),
    ("Hà Lan – Amsterdam", "Europe/Amsterdam"),
    ("Bỉ – Brussels", "Europe/Brussels"),
    ("Thụy Sĩ – Zurich", "Europe/Zurich"),
    ("Áo – Vienna", "Europe/Vienna"),
    ("Ba Lan – Warsaw", "Europe/Warsaw"),
    ("Séc – Prague", "Europe/Prague"),
    ("Thụy Điển – Stockholm", "Europe/Stockholm"),
    ("Na Uy – Oslo", "Europe/Oslo"),
    ("Đan Mạch – Copenhagen", "Europe/Copenhagen"),
    ("Phần Lan – Helsinki", "Europe/Helsinki"),
    ("Ireland – Dublin", "Europe/Dublin"),
    ("Hy Lạp – Athens", "Europe/Athens"),
    ("Hungary – Budapest", "Europe/Budapest"),
    ("Romania – Bucharest", "Europe/Bucharest"),
    ("Ukraine – Kyiv", "Europe/Kyiv"),
    ("Nga – Moscow", "Europe/Moscow"),
    ("Thổ Nhĩ Kỳ – Istanbul", "Europe/Istanbul"),
    # --- châu Á / còn lại ---
    ("Việt Nam – Hồ Chí Minh", "Asia/Ho_Chi_Minh"),
    ("Indonesia – Jakarta", "Asia/Jakarta"),
    ("Malaysia – Kuala Lumpur", "Asia/Kuala_Lumpur"),
    ("Singapore", "Asia/Singapore"),
    ("Trung Quốc – Thượng Hải", "Asia/Shanghai"),
    ("Hồng Kông", "Asia/Hong_Kong"),
    ("Đài Loan – Đài Bắc", "Asia/Taipei"),
    ("Ấn Độ – Kolkata", "Asia/Kolkata"),
    ("Pakistan – Karachi", "Asia/Karachi"),
    ("Bangladesh – Dhaka", "Asia/Dhaka"),
    ("Campuchia – Phnom Penh", "Asia/Phnom_Penh"),
    ("Lào – Vientiane", "Asia/Vientiane"),
    ("Myanmar – Yangon", "Asia/Yangon"),
    ("UAE – Dubai", "Asia/Dubai"),
    ("Ả Rập Xê Út – Riyadh", "Asia/Riyadh"),
    ("Israel – Jerusalem", "Asia/Jerusalem"),
    # --- châu Mỹ khác / châu Phi / châu Đại Dương ---
    ("Canada – Toronto", "America/Toronto"),
    ("Canada – Vancouver", "America/Vancouver"),
    ("Argentina – Buenos Aires", "America/Argentina/Buenos_Aires"),
    ("Chile – Santiago", "America/Santiago"),
    ("Colombia – Bogotá", "America/Bogota"),
    ("Peru – Lima", "America/Lima"),
    ("Venezuela – Caracas", "America/Caracas"),
    ("Ai Cập – Cairo", "Africa/Cairo"),
    ("Nam Phi – Johannesburg", "Africa/Johannesburg"),
    ("Nigeria – Lagos", "Africa/Lagos"),
    ("Kenya – Nairobi", "Africa/Nairobi"),
    ("Morocco – Casablanca", "Africa/Casablanca"),
    ("Úc – Sydney", "Australia/Sydney"),
    ("Úc – Perth", "Australia/Perth"),
    ("New Zealand – Auckland", "Pacific/Auckland"),
    ("UTC", "UTC"),
]

#: nhãn -> IANA (giữ tên cũ MUI_GIO để chỗ khác dùng được).
MUI_GIO = {nhan: iana for nhan, iana in DANH_SACH_MUI_GIO}


def _chu_offset(iana: str, now: Optional[datetime] = None) -> str:
    """'UTC+7' / 'UTC−5:30' theo giờ HIỆN TẠI (đúng cả khi nước đó đang DST)."""
    try:
        off = (now or datetime.now(timezone.utc)).astimezone(vung(iana)).utcoffset()
    except Exception:  # noqa: BLE001
        return "UTC?"
    if off is None:
        return "UTC?"
    tong = int(off.total_seconds() // 60)
    dau = "+" if tong >= 0 else "−"
    gio, phut = divmod(abs(tong), 60)
    return f"UTC{dau}{gio}" + (f":{phut:02d}" if phut else "")


def danh_sach_nhan(now: Optional[datetime] = None) -> list:
    """Nhãn hiển thị cho ô chọn múi giờ: 'Mexico – Mexico City (UTC−6)' — giữ THỨ TỰ ưu tiên."""
    return [f"{nhan} ({_chu_offset(iana, now)})" for nhan, iana in DANH_SACH_MUI_GIO]


def iana_tu_nhan(nhan: str) -> str:
    """Nhãn (có hoặc không có hậu tố '(UTC±X)') -> tên IANA."""
    s = (nhan or "").strip()
    if s in MUI_GIO:
        return MUI_GIO[s]
    goc = s.rsplit(" (", 1)[0].strip()          # bỏ hậu tố offset
    return MUI_GIO.get(goc, s)


class LichError(ValueError):
    pass


def vung(ten: str):
    """tzinfo theo tên IANA ("America/Sao_Paulo"), nhãn trong ``MUI_GIO``, hoặc "UTC+7"/"UTC-3"."""
    ten = (ten or "").strip()
    if not ten:
        raise LichError("Chưa chọn múi giờ page.")
    ten = iana_tu_nhan(ten)     # nhãn UI (kèm '(UTC±X)') hoặc tên IANA sẵn
    t = ten.upper().replace("−", "-").replace(" ", "")
    if t.startswith("UTC") and (len(t) == 3 or t[3] in "+-"):
        if len(t) == 3:
            return timezone.utc
        try:
            dau = 1 if t[3] == "+" else -1
            phan = t[4:].split(":")
            gio = int(phan[0] or 0)
            phut = int(phan[1]) if len(phan) > 1 else 0
            return timezone(dau * timedelta(hours=gio, minutes=phut))
        except ValueError:
            raise LichError(f"Múi giờ không hiểu: {ten}") from None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(ten)
    except Exception:  # noqa: BLE001
        raise LichError(f"Không có múi giờ '{ten}' (cần tên IANA hoặc UTC+7).") from None


def ve_utc(dt_naive: datetime, tz) -> datetime:
    """Giờ 'trần' (naive) ở múi ``tz`` -> datetime UTC (aware). Đã aware thì chỉ đổi về UTC."""
    if dt_naive.tzinfo is not None:
        return dt_naive.astimezone(timezone.utc)
    return dt_naive.replace(tzinfo=tz).astimezone(timezone.utc)


def ra_may(dt_utc: datetime, tz_may=None) -> datetime:
    """UTC -> giờ MÁY (naive, để hiển thị). ``tz_may`` mặc định = múi giờ máy đang chạy."""
    local = dt_utc.astimezone(tz_may) if tz_may is not None else dt_utc.astimezone()
    return local.replace(tzinfo=None)


def quy_doi(gio_dang_naive: datetime, tz_page, tz_may=None) -> tuple:
    """Giờ đăng (giờ PAGE) -> (utc, giờ máy naive). Đây là cột 'Quy đổi' trên bảng."""
    utc = ve_utc(gio_dang_naive, tz_page)
    return utc, ra_may(utc, tz_may)


# ---- HAI CỬA ---------------------------------------------------------------
def doc_gio_sau(text: str, goc: datetime) -> datetime:
    """Như :func:`doc_gio`, nhưng giờ TRẦN ("20:00") đã qua trong ngày = NGÀY MAI.

    ``goc`` phải là giờ hiện tại Ở NƠI SẼ ĐĂNG. Bên Brazil đang 22:00 mà gõ "01:00"
    thì ý là 01:00 rạng sáng HÔM SAU (3 tiếng nữa), không phải 01:00 hôm nay (đã qua).
    Gõ kèm ngày ("23/09 22:30") thì giữ đúng ngày đó, không đẩy.
    """
    dt = doc_gio(text, goc)
    if "/" not in (text or "") and dt < goc:
        dt += timedelta(days=1)
    return dt


def cua1(now_utc: datetime, chay_utc: datetime, tre_phut: int = TRE_MAC_DINH) -> str:
    """CHO (chưa tới) | CHAY (trong khoảng cho phép) | BO_LO (quá giờ chạy + độ trễ)."""
    if now_utc < chay_utc:
        return CHO
    if now_utc <= chay_utc + timedelta(minutes=max(0, int(tre_phut))):
        return CHAY
    return BO_LO


def cua2(now_utc: datetime, dang_utc: datetime, an_toan_phut: int = AN_TOAN_MAC_DINH) -> str:
    """OK | QUA_GAN (còn < khoảng an toàn) | DA_QUA (giờ đăng đã qua)."""
    if dang_utc <= now_utc:
        return DA_QUA
    if dang_utc - now_utc < timedelta(minutes=max(0, int(an_toan_phut))):
        return QUA_GAN
    return OK


def _phut(td: timedelta) -> int:
    return int(td.total_seconds() // 60)


def danh_gia(now_utc: datetime, chay_utc: datetime, dang_utc: datetime, *,
             tre_phut: int = TRE_MAC_DINH, an_toan_phut: int = AN_TOAN_MAC_DINH,
             mien_cua1: bool = False) -> dict:
    """Quyết định cho MỘT khung. Trả {ket_qua, cua1, cua2, ly_do, con_phut}.

    ``mien_cua1=True``: khung bị trễ vì MÁY BẬN được bỏ qua cửa 1, chỉ xét cửa 2
    (tuỳ chọn ở ràng buộc 4 — mỗi lúc chỉ chạy một video)."""
    c1 = cua1(now_utc, chay_utc, tre_phut)
    if c1 == BO_LO and mien_cua1:
        c1 = CHAY                      # máy bận -> miễn cửa 1, chỉ xét cửa 2
    if c1 == BO_LO:
        tre = _phut(now_utc - chay_utc)
        return {"ket_qua": BO_LO, "cua1": BO_LO, "cua2": "",
                "ly_do": f"quá giờ chạy {tre} phút (cho phép {tre_phut})",
                "con_phut": _phut(dang_utc - now_utc)}
    # Chưa tới giờ chạy: XEM TRƯỚC cửa 2 tại thời điểm giờ chạy (để báo đỏ sớm).
    moc = now_utc if c1 == CHAY else chay_utc
    c2 = cua2(moc, dang_utc, an_toan_phut)
    con = _phut(dang_utc - moc)
    if c1 == CHO:
        return {"ket_qua": CHO, "cua1": CHO, "cua2": c2,
                "ly_do": (f"chờ tới giờ chạy (còn {_phut(chay_utc - now_utc)} phút)"
                          if c2 == OK else f"sẽ trượt cửa 2: {NHAN.get(c2, c2)}"),
                "con_phut": con}
    if c2 != OK:
        return {"ket_qua": c2, "cua1": CHAY, "cua2": c2,
                "ly_do": (f"giờ đăng đã qua {abs(con)} phút" if c2 == DA_QUA
                          else f"còn {con} phút < an toàn {an_toan_phut} phút"),
                "con_phut": con}
    return {"ket_qua": CHAY, "cua1": CHAY, "cua2": OK,
            "ly_do": f"qua cả 2 cửa — còn {con} phút tới giờ đăng", "con_phut": con}


def hop_le_khi_nhap(chay_utc: datetime, dang_utc: datetime,
                    an_toan_phut: int = AN_TOAN_MAC_DINH) -> tuple:
    """Kiểm LÚC NHẬP lịch: từ giờ chạy tới giờ đăng có đủ khoảng an toàn không.

    Trả (hop_le, ly_do) — báo đỏ ngay để người dùng sửa sớm (không đợi tới lúc chạy)."""
    c2 = cua2(chay_utc, dang_utc, an_toan_phut)
    if c2 == OK:
        return True, ""
    con = _phut(dang_utc - chay_utc)
    if c2 == DA_QUA:
        return False, "giờ đăng nằm TRƯỚC giờ chạy"
    return False, f"giờ chạy cách giờ đăng {con} phút < an toàn {an_toan_phut} phút"


def doc_gio(text: str, goc: Optional[datetime] = None) -> datetime:
    """Đọc 'dd/mm HH:MM', 'dd/mm/yyyy HH:MM' hoặc 'HH:MM' (lấy ngày của ``goc``) -> datetime naive."""
    s = (text or "").strip().replace("-", "/")
    goc = goc or datetime.now()
    for dinh in ("%d/%m/%Y %H:%M", "%d/%m %H:%M", "%H:%M"):
        try:
            d = datetime.strptime(s, dinh)
        except ValueError:
            continue
        if dinh == "%H:%M":
            return d.replace(year=goc.year, month=goc.month, day=goc.day)
        if dinh == "%d/%m %H:%M":
            return d.replace(year=goc.year)
        return d
    raise LichError(f"Giờ không hiểu: '{text}' (dùng 'HH:MM' hoặc 'dd/mm HH:MM').")
