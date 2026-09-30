"""Đổi tên (tiêu đề) hàng loạt file trong một thư mục theo CHUỖI BƯỚC biến đổi.

Các kiểu biến đổi (``LOAI``): xoá cụm từ, xoá hashtag, thêm vào đầu, thêm vào cuối,
đánh số thứ tự, xoá cụm "cùng kiểu khác số liệu" theo VÍ DỤ (vd "833K views 22K reactions"
xoá được cả "634K views 43K reactions"). Tách tầng: file này KHÔNG import UI; UI chỉ gọi
``xem_truoc`` / ``doi_ten`` / ``hoan_tac``. Mọi hàm biến đổi làm trên PHẦN TÊN (không đuôi).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from typing import Callable, Optional

#: Số liệu: 833K, 22K, 1.2M, 1,234, 15 (có thể cách chữ K/M/B một khoảng trắng).
SO_RE = r"\d[\d.,]*\s*[KkMmBb]?"
_SO = re.compile(f"({SO_RE})")
#: Hashtag = '#' + chuỗi không có khoảng trắng, đứng đầu hoặc sau khoảng trắng (không cắt giữa chữ).
_HASHTAG = re.compile(r"(?<!\S)#\S+")
_KHOANG = re.compile(r"\s+")

#: Các kiểu bước: (mã, nhãn hiển thị, có cần giá trị không).
LOAI = (
    ("xoa_cum", "Xoá cụm từ", True),
    ("xoa_hashtag", "Xoá hashtag (#...)", False),
    ("them_dau", "Thêm vào ĐẦU", True),
    ("them_cuoi", "Thêm vào CUỐI", True),
    ("danh_so", "Đánh số thứ tự", True),
    ("xoa_mau", "Xoá cụm cùng kiểu khác số liệu (theo ví dụ)", True),
)
NHAN_LOAI = {ma: nhan for ma, nhan, _ in LOAI}
MA_THEO_NHAN = {nhan: ma for ma, nhan, _ in LOAI}
#: Tên file hoàn tác nằm ngay trong thư mục vừa đổi.
UNDO_NAME = ".lvc-doi-ten-hoan-tac.json"


@dataclass
class Buoc:
    """Một bước biến đổi. ``gia_tri``: cụm từ / chuỗi thêm / ví dụ; với ``danh_so`` là định dạng
    (vd "{n}", "{n:02d}", "Tập {n}") và ``vi_tri`` = "dau" | "cuoi"."""
    loai: str
    gia_tri: str = ""
    vi_tri: str = "cuoi"

    def mo_ta(self) -> str:
        nhan = NHAN_LOAI.get(self.loai, self.loai)
        if self.loai == "xoa_hashtag":
            return nhan
        if self.loai == "danh_so":
            return f"{nhan} ({'đầu' if self.vi_tri == 'dau' else 'cuối'}, dạng “{self.gia_tri or '{n}'}”)"
        return f"{nhan}: “{self.gia_tri}”"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Buoc":
        raw = dict(raw or {})
        return cls(str(raw.get("loai") or ""), str(raw.get("gia_tri") or ""),
                   "dau" if raw.get("vi_tri") == "dau" else "cuoi")


# --------------------------------------------------------------------------
# Từng phép biến đổi (thuần, test được)
# --------------------------------------------------------------------------
def don(s: str) -> str:
    """Dọn khoảng trắng thừa sau khi xoá: gộp nhiều khoảng trắng, cắt hai đầu."""
    return _KHOANG.sub(" ", s or "").strip()


def xoa_cum(s: str, cum: str) -> str:
    """Xoá MỌI lần xuất hiện của cụm từ (không phân biệt hoa thường)."""
    cum = (cum or "").strip()
    if not cum:
        return s
    return don(re.sub(re.escape(cum), " ", s, flags=re.IGNORECASE))


def xoa_hashtag(s: str) -> str:
    """Xoá mọi hashtag (#แม่ปลาบู่, #ophaphoomchannel ...)."""
    return don(_HASHTAG.sub(" ", s))


def them_dau(s: str, x: str) -> str:
    return don(f"{x} {s}") if (x or "").strip() else s


def them_cuoi(s: str, x: str) -> str:
    return don(f"{s} {x}") if (x or "").strip() else s


def danh_so(s: str, n: int, dinh_dang: str = "{n}", vi_tri: str = "cuoi") -> str:
    """Gắn số thứ tự ``n`` theo định dạng (hỗ trợ {n:02d}); đầu hoặc cuối tên."""
    try:
        so = (dinh_dang or "{n}").format(n=n)
    except (KeyError, ValueError, IndexError):
        so = str(n)
    return don(f"{so} {s}") if vi_tri == "dau" else don(f"{s} {so}")


def mau_tu_vi_du(vi_du: str) -> Optional[re.Pattern]:
    """Từ MỘT ví dụ ("833K views 22K reactions") dựng mẫu bắt mọi cụm cùng kiểu, khác số.

    Chữ giữ nguyên (không phân biệt hoa thường), số liệu thành ``SO_RE``, khoảng trắng co giãn."""
    vi_du = don(vi_du)
    if not vi_du:
        return None
    phan = []
    for i, doan in enumerate(_SO.split(vi_du)):
        if not doan or not doan.strip():
            continue
        if i % 2 == 1:                                   # nhóm bắt = số liệu
            phan.append(SO_RE)
        else:
            tu = [re.escape(t) for t in doan.split()]
            if tu:
                phan.append(r"\s+".join(tu))
    if not phan:
        return None
    return re.compile(r"\s*".join(phan), re.IGNORECASE)


def xoa_mau(s: str, vi_du: str) -> str:
    """Xoá mọi cụm cùng kiểu với ví dụ (khác số liệu). Ví dụ rỗng/không có số -> vẫn xoá đúng chữ."""
    mau = mau_tu_vi_du(vi_du)
    if mau is None:
        return s
    return don(mau.sub(" ", s))


def ap_dung(ten: str, buocs: list, stt: int = 1) -> str:
    """Áp CHUỖI bước lên phần tên (không đuôi). ``stt`` dùng cho bước đánh số."""
    ra = ten
    for b in buocs:
        if b.loai == "xoa_cum":
            ra = xoa_cum(ra, b.gia_tri)
        elif b.loai == "xoa_hashtag":
            ra = xoa_hashtag(ra)
        elif b.loai == "them_dau":
            ra = them_dau(ra, b.gia_tri)
        elif b.loai == "them_cuoi":
            ra = them_cuoi(ra, b.gia_tri)
        elif b.loai == "danh_so":
            ra = danh_so(ra, stt, b.gia_tri or "{n}", b.vi_tri)
        elif b.loai == "xoa_mau":
            ra = xoa_mau(ra, b.gia_tri)
    return ra


# --------------------------------------------------------------------------
# Thư mục: xem trước / đổi tên / hoàn tác
# --------------------------------------------------------------------------
_CAM = set('<>:"/\\|?*')


def ten_hop_le(ten: str) -> bool:
    return bool(ten) and not any(c in _CAM for c in ten) and ten not in (".", "..")


def _khoa_sap_xep(ten: str):
    """Sắp xếp tự nhiên: 'a2' trước 'a10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", ten)]


def liet_ke(folder: str, duoi: Optional[list] = None) -> list:
    """Tên file (không thư mục con, bỏ file hoàn tác) theo thứ tự tự nhiên; lọc đuôi nếu có."""
    try:
        ten = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    except OSError:
        return []
    duoi_s = {d.lower().lstrip(".") for d in (duoi or []) if d.strip()}
    ra = []
    for f in ten:
        if f == UNDO_NAME:
            continue
        if duoi_s and os.path.splitext(f)[1].lower().lstrip(".") not in duoi_s:
            continue
        ra.append(f)
    return sorted(ra, key=_khoa_sap_xep)


def nhom_file(folder: str, duoi: Optional[list] = None, cung_goc: bool = True) -> list:
    """[(khoá, [tên file...])] theo thứ tự tự nhiên — mỗi khoá là MỘT tiêu đề.

    ``cung_goc``: các file cùng phần tên khác đuôi (.mp4 + .txt) gom chung một nhóm."""
    nhom: dict = {}
    thu_tu: list = []
    for f in liet_ke(folder, duoi):
        goc, _ = os.path.splitext(f)
        k = goc if cung_goc else f
        if k not in nhom:
            nhom[k] = []
            thu_tu.append(k)
        nhom[k].append(f)
    return [(k, nhom[k]) for k in thu_tu]


def _danh_gia(f: str, moi_goc: str) -> dict:
    """Một dòng kế hoạch cho file ``f`` với phần tên mới ``moi_goc`` (chưa xét trùng)."""
    moi = moi_goc + os.path.splitext(f)[1]
    if moi == f:
        tt = "khong_doi"
    elif not ten_hop_le(moi_goc):
        tt = "loi"
    else:
        tt = "ok"
    return {"cu": f, "moi": moi, "tt": tt}


def xem_truoc(folder: str, buocs: list, *, duoi: Optional[list] = None,
              cung_goc: bool = True) -> list:
    """Kế hoạch đổi tên: [{cu, moi, tt}] với tt = "ok" | "khong_doi" | "trung" | "loi".

    ``cung_goc``: các file cùng phần tên (khác đuôi: .mp4 + .txt) nhận CÙNG tên mới và cùng số thứ tự.
    Số thứ tự đếm theo NHÓM tên (1, 2, 3...) theo thứ tự tự nhiên trong thư mục."""
    ke_hoach = []
    for stt, (_k, files) in enumerate(nhom_file(folder, duoi, cung_goc), start=1):
        for f in files:
            ke_hoach.append(_danh_gia(f, ap_dung(os.path.splitext(f)[0], buocs, stt)))
    return _danh_dau_trung(folder, ke_hoach)


def tach_tieu_de(text: str) -> list:
    """Mỗi DÒNG trong ô nhập = MỘT tiêu đề mới (theo thứ tự trên xuống). Bỏ dòng trống."""
    ds = []
    for dong in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        d = don(dong)
        if d:
            ds.append(d)
    return ds


def lam_sach_ten(ten: str) -> str:
    """Bỏ ký tự Windows cấm đặt tên file (< > : " / \\ | ? *) khỏi tiêu đề người dùng dán vào."""
    return don("".join(" " if c in _CAM else c for c in (ten or "")))


def xem_truoc_thay_the(folder: str, tieu_des: list, *, duoi: Optional[list] = None,
                       cung_goc: bool = True, buocs: Optional[list] = None,
                       lam_sach: bool = True) -> list:
    """THAY THẾ tên: tiêu đề thứ i (từ trên xuống) gán cho nhóm file thứ i trong thư mục.

    Thiếu tiêu đề -> các file còn lại giữ nguyên tên. Thừa tiêu đề -> bỏ qua phần dư.
    ``buocs`` (nếu có) chạy TIẾP trên tiêu đề mới (vd đánh số), ``lam_sach`` bỏ ký tự cấm."""
    ke_hoach = []
    for stt, (k, files) in enumerate(nhom_file(folder, duoi, cung_goc), start=1):
        if stt <= len(tieu_des):
            goc_moi = tieu_des[stt - 1]
            if lam_sach:
                goc_moi = lam_sach_ten(goc_moi)
        else:
            goc_moi = k
        for f in files:
            moi_goc = ap_dung(goc_moi, buocs or [], stt)
            if not cung_goc:
                moi_goc = moi_goc or os.path.splitext(f)[0]
            ke_hoach.append(_danh_gia(f, moi_goc))
    return _danh_dau_trung(folder, ke_hoach)


def _danh_dau_trung(folder: str, ke_hoach: list) -> list:
    """Đánh dấu tt = "trung" cho dòng có tên mới đụng nhau / đụng file đã có sẵn."""
    # Trùng đích: hai file cùng tên mới, hoặc tên mới đã có sẵn mà file đó không bị đổi.
    dem: dict = {}
    for r in ke_hoach:
        dem[r["moi"].lower()] = dem.get(r["moi"].lower(), 0) + 1
    ten_cu = {r["cu"].lower() for r in ke_hoach}
    for r in ke_hoach:
        if r["tt"] != "ok":
            continue
        m = r["moi"].lower()
        if dem[m] > 1 or (m in ten_cu and m != r["cu"].lower()
                          and not any(x["cu"].lower() == m and x["tt"] == "ok" for x in ke_hoach)):
            r["tt"] = "trung"
        elif m not in ten_cu and os.path.exists(os.path.join(folder, r["moi"])):
            r["tt"] = "trung"
    return ke_hoach


def doi_ten(folder: str, ke_hoach: list, *,
            log: Optional[Callable[[str], None]] = None) -> dict:
    """Đổi tên theo kế hoạch (chỉ dòng tt == "ok"). Ghi file hoàn tác trong thư mục.

    Đổi qua tên TẠM trước để hoán đổi vòng (a->b, b->a) không đè nhau. Trả {ok, bo_qua, loi:[...]}."""
    noi = log or (lambda _m: None)
    can = [r for r in ke_hoach if r.get("tt") == "ok"]
    loi, xong = [], []
    tam = []
    for i, r in enumerate(can):
        src = os.path.join(folder, r["cu"])
        t = os.path.join(folder, f".lvc-tam-{i}-{os.path.basename(r['moi'])}")
        try:
            os.rename(src, t)
            tam.append((t, r))
        except OSError as exc:
            loi.append(f"{r['cu']}: {exc}")
    for t, r in tam:
        dst = os.path.join(folder, r["moi"])
        try:
            os.rename(t, dst)
            xong.append({"moi": r["moi"], "cu": r["cu"]})
            noi(f"✔ {r['cu']}  →  {r['moi']}")
        except OSError as exc:
            loi.append(f"{r['cu']}: {exc}")
            try:
                os.rename(t, os.path.join(folder, r["cu"]))    # trả lại tên cũ
            except OSError:
                pass
    if xong:
        try:
            with open(os.path.join(folder, UNDO_NAME), "w", encoding="utf-8") as fh:
                json.dump(xong, fh, ensure_ascii=False, indent=1)
        except OSError as exc:
            noi(f"⚠ không ghi được file hoàn tác: {exc}")
    return {"ok": len(xong), "bo_qua": len(ke_hoach) - len(can), "loi": loi}


def co_hoan_tac(folder: str) -> int:
    """Số file có thể hoàn tác (đọc file hoàn tác); 0 nếu không có."""
    try:
        with open(os.path.join(folder, UNDO_NAME), encoding="utf-8") as fh:
            return len(json.load(fh) or [])
    except (OSError, ValueError):
        return 0


def hoan_tac(folder: str, *, log: Optional[Callable[[str], None]] = None) -> dict:
    """Trả tên cũ cho lần đổi gần nhất (theo file hoàn tác), rồi xoá file hoàn tác."""
    noi = log or (lambda _m: None)
    path = os.path.join(folder, UNDO_NAME)
    try:
        with open(path, encoding="utf-8") as fh:
            ds = json.load(fh) or []
    except (OSError, ValueError):
        return {"ok": 0, "loi": ["không có gì để hoàn tác"]}
    ke_hoach = [{"cu": x["moi"], "moi": x["cu"], "tt": "ok"} for x in ds
                if isinstance(x, dict) and x.get("moi") and x.get("cu")]
    kq = doi_ten(folder, ke_hoach, log=noi)
    try:
        os.remove(path)
    except OSError:
        pass
    return {"ok": kq["ok"], "loi": kq["loi"]}
