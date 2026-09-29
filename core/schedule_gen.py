"""Sinh danh sach GIO DANG BAI lech dan de tranh trung gio (nhieu acc dang cung luc).

Nguoi dung nhap MOT list moc gio goc (vd 7:00, 10:00, 19:00) + so phut lech + so dong
can tao. Dong i (1..N) = moi moc goc CONG offset*i phut, phut tran 60 thi nhay gio,
gio tran 24 thi quay vong. Vi du offset=3:
  dong 1: 7:03, 10:03, 19:03
  dong 2: 7:06, 10:06, 19:06
  dong 3: 7:09, 10:09, 19:09
Hien thi gio KHONG dem so 0 o hang gio (7:03), phut luon 2 chu so — khop vi du nguoi dung.
"""

from __future__ import annotations

from core.autoup import normalize_time


class ScheduleError(ValueError):
    pass


def parse_moc(text: str) -> list:
    """Doc o nhap list gio goc (xuong dong / phay / cham / chAcm phay) -> [(gio, phut)],
    GIU THU TU nhap (khong sap xep), bo trung. Nem ScheduleError neu rong / sai."""
    raw = (text or "")
    for sep in (",", ";", "\n", "\t"):
        raw = raw.replace(sep, " ")
    # Cham '.' co the la dau phan cach moc (19:00. 7:00) HOAC trong gio (19.00);
    # normalize_time doi '.' -> ':' nen tach moc theo khoang trang, moi mieng con
    # co the la "19.00" hoac "19:00".
    out, seen = [], set()
    for mieng in raw.split():
        mieng = mieng.strip().strip(".")
        if not mieng:
            continue
        try:
            canon = normalize_time(mieng)   # "07:03", nem ValueError neu sai
        except ValueError as e:
            raise ScheduleError(str(e)) from None
        if canon not in seen:
            seen.add(canon)
            gio, phut = canon.split(":")
            out.append((int(gio), int(phut)))
    if not out:
        raise ScheduleError("Chưa nhập mốc giờ nào (ví dụ: 7:00, 10:00, 19:00).")
    return out


def _fmt(gio: int, phut: int) -> str:
    """'7:03' — hang gio khong dem so 0, phut 2 chu so (khop vi du nguoi dung)."""
    return f"{gio % 24}:{phut:02d}"


def cong_phut(gio: int, phut: int, them: int) -> tuple:
    """Cong `them` phut vao (gio, phut); phut tran 60 -> nhay gio; gio tran 24 -> quay vong."""
    tong = (gio * 60 + phut + them) % (24 * 60)
    return tong // 60, tong % 60


def sinh_gio_lech(text_moc: str, offset_phut: int, so_dong: int) -> list:
    """Tra ve danh sach dong; moi dong la list chuoi gio '7:03'. Dong i = moc goc + offset*i.

    Nem ScheduleError khi: khong co moc, offset <= 0, so_dong <= 0.
    """
    moc = parse_moc(text_moc)
    if offset_phut <= 0:
        raise ScheduleError("Số phút lệch phải là số dương (ví dụ: 3).")
    if so_dong <= 0:
        raise ScheduleError("Số dòng cần tạo phải là số dương.")
    rows = []
    for i in range(1, so_dong + 1):
        them = offset_phut * i
        rows.append([_fmt(*cong_phut(g, p, them)) for (g, p) in moc])
    return rows


def dong_thanh_chuoi(row: list) -> str:
    """Mot dong -> '7:03, 10:03, 19:03'."""
    return ", ".join(row)


def bang_thanh_text(rows: list) -> str:
    """Ca bang -> nhieu dong, moi dong cach nhau xuong dong (de copy/xuat TXT)."""
    return "\n".join(dong_thanh_chuoi(r) for r in rows)
