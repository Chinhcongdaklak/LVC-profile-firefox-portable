# -*- coding: utf-8 -*-
"""
capnhat.py  ->  LVCProfileUpdate.exe   (LVC Manager Profile — chep tu bo cap nhat Video Slide)
══════════════════════════════════════════════════════════════════════════════
BỘ CẬP NHẬT — người dùng bấm vào đây để tải bản mới nhất
──────────────────────────────────────────────────────────────────────────────
Chạy CẠNH `LVC Manager Profile.exe`. Nó hỏi GitHub xem có bản mới không, tải về, kiểm
lại rồi thay file cũ.

BỐN QUYẾT ĐỊNH, và lý do — đừng gỡ ra:

1. LẤY TỪ **GITHUB RELEASES**, KHÔNG PHẢI TỪ FILE TRONG REPO.
   Tool nặng ~51 MB và mỗi bản một file; GitHub không hợp để giữ file nhị phân
   trong repo (repo phình mãi, giới hạn 100 MB/file). Release cho tới 2 GB mỗi
   tệp, và có sẵn API "bản mới nhất" nên không phải tự dựng máy chủ.

2. BỘ CẬP NHẬT LÀ MỘT .EXE **RIÊNG**.
   Windows không cho ghi đè một file .exe ĐANG CHẠY. Nếu tool tự cập nhật chính
   nó thì phải giở trò đổi tên/đặt lịch xoá, lắt léo và dễ để lại file rác. Tách
   ra thì việc thay file chỉ là một phép đổi tên bình thường.

3. KHÔNG IMPORT GÌ CỦA DỰ ÁN, CHỈ DÙNG THƯ VIỆN CHUẨN.
   Bộ cập nhật phải chạy được ĐÚNG LÚC bản tool đang hỏng — đó là lúc người ta
   cần nó nhất. Import `core.*` là buộc số phận nó vào thứ nó phải đi sửa. Nhờ
   vậy nó cũng chỉ nặng ~10 MB thay vì ~51 MB.

4. TẢI XONG PHẢI KIỂM **SHA256 + DUNG LƯỢNG** RỒI MỚI THAY.
   Mạng đứt giữa chừng cho ra một file .exe cụt mà vẫn "tải xong". Thay bằng nó
   là người dùng mất luôn bản đang chạy được. Tải vào file tạm ở CÙNG thư mục
   (để phép đổi tên là tức thời), kiểm xong mới đổi tên, và giữ bản cũ tới khi
   chắc chắn bản mới đã nằm đúng chỗ.

Chạy tay:  python capnhat.py            (có cửa sổ)
           python capnhat.py --console  (không cửa sổ, in ra màn hình)
══════════════════════════════════════════════════════════════════════════════
"""

import hashlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

#: PHAI khop core/phien_ban.py (thuoc cn01 kiem) -- khong import de khoi keo du an vao.
KHO = "Chinhcongdaklak/congprofile"
TEN_EXE = "LVC Manager Profile.exe"
#: Ten tep dinh kem tren Release (khong dau cach — GitHub doi dau cach thanh dau cham).
TEN_TEP_PHAT_HANH = "LVC.Manager.Profile.exe"
TEN_MO_TA = "capnhat.json"
TEN_FILE_PHIEN_BAN = "phien_ban.txt"
API = "https://api.github.com/repos/%s/releases/latest" % KHO
UA = "LVCProfileUpdate"


# ══════════════════════════════════════════════════════════ tiện ích chung
def thu_muc_goc():
    """Thư mục chứa bộ cập nhật — cũng là thư mục chứa tool.

    Khi đã đóng thành .exe thì `sys.executable` mới là đường thật; `__file__`
    lúc đó trỏ vào thư mục giải nén tạm của PyInstaller và sẽ bị xoá."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def so_sanh(a, b):
    """So hai chuỗi phiên bản theo TỪNG SỐ. -1 / 0 / 1.

    So bằng chuỗi là sai: "5.10.0" < "5.9.0" nếu xếp chữ, trong khi 10 > 9."""
    def tach(s):
        ra = []
        for phan in str(s or "0").strip().lstrip("vV").split("."):
            so = ""
            for c in phan:
                if not c.isdigit():
                    break
                so += c
            ra.append(int(so) if so else 0)
        return ra
    x, y = tach(a), tach(b)
    n = max(len(x), len(y))
    x += [0] * (n - len(x))
    y += [0] * (n - len(y))
    return (x > y) - (x < y)


def phien_ban_dang_cai(goc):
    """Đọc `phien_ban.txt` cạnh .exe. Không có -> "0.0.0" (tức luôn cập nhật).

    Không có file nghĩa là bản cài quá cũ (trước khi có bộ cập nhật) hoặc người
    dùng lỡ xoá — cả hai trường hợp đều nên cho tải bản mới, chứ không nên im."""
    try:
        with open(os.path.join(goc, TEN_FILE_PHIEN_BAN), "r", encoding="utf-8") as f:
            return f.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _mo(url, nhi_phan=False, timeout=30):
    """Gọi HTTP có User-Agent (GitHub BẮT BUỘC) và chịu được máy thiếu chứng chỉ."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/vnd.github+json" if not nhi_phan else "application/octet-stream",
    })
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as e:
        # Máy thiếu/cũ kho chứng chỉ gốc -> mọi kết nối HTTPS hỏng. Thử lại một
        # lần với ngữ cảnh mặc định của hệ thống trước khi chịu thua, vì đây là
        # lỗi hay gặp trên máy Windows lâu ngày không cập nhật.
        if "CERTIFICATE" not in str(e).upper():
            raise
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)


# ══════════════════════════════════════════════════════ hỏi bản mới nhất
def hoi_ban_moi():
    """-> (phiên bản, url tải, dung lượng, sha256, ghi chú) hoặc ném RuntimeError."""
    try:
        with _mo(API) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(
                "Kho '%s' chưa có bản phát hành nào.\n"
                "Người phát hành cần bấm phát hành (phat_hanh.bat) để đẩy bản đầu tiên lên."
                % KHO)
        raise RuntimeError("GitHub trả lỗi %s khi hỏi bản mới nhất." % e.code)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("Không kết nối được GitHub: %s" % e)

    ban = str(d.get("tag_name") or "").lstrip("vV")
    ghi_chu = str(d.get("body") or "").strip()
    tep = {a.get("name"): a for a in (d.get("assets") or [])}

    # `capnhat.json` là nguồn CHÍNH cho dung lượng + sha256. Không có thì vẫn
    # chạy được (chỉ mất phép kiểm sha256), để bản phát hành làm tay cũng dùng được.
    # Tep tren Release ten KHONG dau cach; chap nhan ca ten goc (ban phat hanh lam tay).
    sha, co = "", tep.get(TEN_TEP_PHAT_HANH) or tep.get(TEN_EXE)
    if TEN_MO_TA in tep:
        try:
            with _mo(tep[TEN_MO_TA]["browser_download_url"]) as r:
                mt = json.loads(r.read().decode("utf-8"))
            sha = str(mt.get("sha256") or "")
            ban = str(mt.get("phien_ban") or ban).lstrip("vV")
        except Exception:  # noqa: BLE001
            pass        # thiếu mô tả thì thôi, không được làm hỏng cả lượt
    if co is None:
        raise RuntimeError("Bản phát hành mới nhất không có tệp '%s'." % TEN_TEP_PHAT_HANH)
    if not ban:
        raise RuntimeError("Bản phát hành không ghi số phiên bản (thẻ tag rỗng).")
    return ban, co["browser_download_url"], int(co.get("size") or 0), sha, ghi_chu


# ═══════════════════════════════════════════════════════════════ tải về
def tai_ve(url, dich, tong, bao=None, dung=None):
    """Tải vào `dich`, gọi `bao(da_tai, tong)` dọc đường. Trả sha256 đã tính.

    Tính sha256 NGAY TRONG LÚC TẢI: đọc lại file ~51 MB lần nữa chỉ để băm là
    tốn thêm một lượt đọc đĩa mà không được gì."""
    bam = hashlib.sha256()
    da = 0
    with _mo(url, nhi_phan=True, timeout=60) as r, open(dich, "wb") as f:
        if not tong:
            tong = int(r.headers.get("Content-Length") or 0)
        while True:
            if dung is not None and dung():
                raise RuntimeError("Người dùng đã dừng.")
            khoi = r.read(1024 * 256)
            if not khoi:
                break
            f.write(khoi)
            bam.update(khoi)
            da += len(khoi)
            if bao:
                bao(da, tong)
    return bam.hexdigest(), da


def dang_chay(duong_exe):
    """File .exe đang chạy không? Hỏi bằng cách THỬ ĐỔI TÊN chính nó.

    Không dùng `tasklist`: tên tiến trình có thể trùng với thứ khác, và người
    dùng có thể đổi tên file. Windows khoá file đang chạy, nên phép đổi tên là
    câu trả lời CHÍNH XÁC cho đúng câu hỏi "tôi có thay được file này không".
    Đổi được thì đổi trả lại ngay."""
    if not os.path.isfile(duong_exe):
        return False
    tam = duong_exe + ".thu"
    try:
        os.rename(duong_exe, tam)
        os.rename(tam, duong_exe)
        return False
    except OSError:
        return True


def cho_nha_file(duong_exe, giay=15.0, _ngu=time.sleep):
    """Cho toi da ``giay`` cho file .exe HET bi khoa (tool dang thoat). True = VAN dang chay.

    Nut "Cap nhat" trong tool mo bo cap nhat roi moi thoat -> vai giay dau file con khoa."""
    het = time.time() + giay
    while dang_chay(duong_exe):
        if time.time() >= het:
            return True
        _ngu(0.5)
    return False


def thay_file(goc, tep_moi, ban_moi, log=None):
    """Đưa file vừa tải vào đúng chỗ. Trả "" nếu xong, hoặc câu lỗi đọc được."""
    log = log or (lambda _m: None)
    dich = os.path.join(goc, TEN_EXE)
    cu = dich + ".cu"
    if dang_chay(dich):
        return ("%s ĐANG CHẠY nên không thay được.\n"
                "Hãy đóng tool rồi bấm lại." % TEN_EXE)
    try:
        if os.path.exists(cu):
            os.remove(cu)
        if os.path.exists(dich):
            os.rename(dich, cu)     # GIỮ bản cũ, chưa xoá vội
        os.rename(tep_moi, dich)
    except OSError as e:
        # Đưa bản cũ trở lại: thà giữ nguyên bản đang chạy được còn hơn để
        # người dùng không còn cái nào.
        try:
            if not os.path.exists(dich) and os.path.exists(cu):
                os.rename(cu, dich)
                log("↩️ Đã trả lại bản cũ.")
        except OSError:
            pass
        return "Không thay được file: %s" % e
    try:
        with open(os.path.join(goc, TEN_FILE_PHIEN_BAN), "w", encoding="utf-8") as f:
            f.write(ban_moi)
    except OSError:
        pass        # ghi hụt số phiên bản thì lần sau báo có bản mới, không hại
    try:
        if os.path.exists(cu):
            os.remove(cu)
    except OSError:
        log("ℹ️ Bản cũ còn ở %s, xoá tay lúc nào cũng được." % os.path.basename(cu))
    return ""


def kiem_tep_kem(goc):
    """Các THƯ MỤC phải nằm cạnh .exe. Chúng KHÔNG nằm trong .exe và KHÔNG được cập nhật
    tự động (dữ liệu acc, profile Firefox, bộ cài Firefox + addon)."""
    can = [("data", "danh sách acc, cookie, cài đặt"),
           ("profile", "profile Firefox của từng acc"),
           ("extension", "bộ cài Firefox Portable + addon")]
    return [(t, v) for t, v in can if not os.path.isdir(os.path.join(goc, t))]


# ══════════════════════════════════════════════════════════════ luồng việc
class BoCapNhat:
    """Phần việc thật, KHÔNG dính giao diện — để chạy được cả ở chế độ console."""

    def __init__(self, goc=None, log=None, tien_do=None):
        self.goc = goc or thu_muc_goc()
        self.log = log or (lambda m: print(m))
        self.tien_do = tien_do or (lambda da, tong: None)
        self._dung = False

    def yeu_cau_dung(self):
        self._dung = True

    def chay(self):
        """-> (có cập nhật không, câu kết luận)."""
        hien = phien_ban_dang_cai(self.goc)
        self.log("📁 Thư mục: %s" % self.goc)
        self.log("🏷️ Bản đang cài: %s" % hien)
        self.log("🌐 Đang hỏi GitHub...")
        try:
            ban, url, co_lon, sha, ghi_chu = hoi_ban_moi()
        except RuntimeError as e:
            return False, "❌ %s" % e
        self.log("🏷️ Bản mới nhất: %s" % ban)
        if so_sanh(ban, hien) <= 0:
            return False, "✅ Đang dùng bản mới nhất (%s). Không cần cập nhật." % hien
        if ghi_chu:
            self.log("📝 Có gì mới:")
            for d in ghi_chu.splitlines()[:12]:
                self.log("   " + d)

        dich = os.path.join(self.goc, TEN_EXE)
        if cho_nha_file(dich):
            return False, ("⚠️ %s ĐANG CHẠY. Hãy đóng tool rồi chạy lại bộ cập nhật."
                           % TEN_EXE)

        tam = os.path.join(self.goc, TEN_EXE + ".tai_tam")
        self.log("⬇️ Đang tải %s (%.1f MB)..." % (ban, (co_lon or 0) / 1048576.0))
        try:
            sha_that, da = tai_ve(url, tam, co_lon, bao=self.tien_do,
                                  dung=lambda: self._dung)
        except Exception as e:  # noqa: BLE001
            self._xoa(tam)
            return False, "❌ Tải hỏng: %s" % e

        if co_lon and da != co_lon:
            self._xoa(tam)
            return False, ("❌ Tải thiếu: được %d byte, đáng lẽ %d. "
                           "Mạng đứt giữa chừng — thử lại." % (da, co_lon))
        if sha and sha_that.lower() != sha.lower():
            self._xoa(tam)
            return False, ("❌ File tải về KHÔNG khớp mã kiểm tra — có thể hỏng "
                           "hoặc bị can thiệp. Đã bỏ, KHÔNG thay bản đang dùng.")
        if sha:
            self.log("🔒 Mã kiểm tra khớp.")

        loi = self.thay(tam, ban)
        if loi:
            self._xoa(tam)
            return False, "❌ %s" % loi

        thieu = kiem_tep_kem(self.goc)
        if thieu:
            self.log("⚠️ Thiếu %d thư mục cần đặt CẠNH .exe:" % len(thieu))
            for t, v in thieu:
                self.log("   • %s — thiếu thì hỏng: %s" % (t, v))
        return True, "✅ Đã cập nhật lên bản %s." % ban

    def thay(self, tam, ban):
        return thay_file(self.goc, tam, ban, log=self.log)

    def _xoa(self, p):
        try:
            os.remove(p)
        except OSError:
            pass

    def mo_tool(self):
        p = os.path.join(self.goc, TEN_EXE)
        if not os.path.isfile(p):
            return False
        try:
            subprocess.Popen([p], cwd=self.goc)
            return True
        except OSError:
            return False


# ═════════════════════════════════════════════════════════════ giao diện
def chay_console():
    bo = BoCapNhat()
    moc = [0.0]

    def tien_do(da, tong):
        if time.time() - moc[0] < 0.5 and da != tong:
            return
        moc[0] = time.time()
        pt = (100.0 * da / tong) if tong else 0
        sys.stdout.write("\r   %5.1f%%  %6.1f / %.1f MB"
                         % (pt, da / 1048576.0, (tong or 0) / 1048576.0))
        sys.stdout.flush()

    bo.tien_do = tien_do
    xong, cau = bo.chay()
    print()
    print(cau)
    return 0 if xong or cau.startswith("✅") else 1


def chay_gui():
    import tkinter as tk
    from tkinter import ttk

    cua = tk.Tk()
    cua.title("Cập nhật LVC Manager Profile")
    cua.geometry("680x420")
    khung = tk.Frame(cua, padx=12, pady=10)
    khung.pack(fill="both", expand=True)

    tk.Label(khung, text="Cập nhật tool", font=("Segoe UI", 13, "bold")).pack(anchor="w")
    nhan = tk.Label(khung, text="Sẵn sàng.", anchor="w", fg="#374151")
    nhan.pack(fill="x", pady=(2, 6))
    thanh = ttk.Progressbar(khung, maximum=100)
    thanh.pack(fill="x")
    o_log = tk.Text(khung, height=14, wrap="word")
    o_log.pack(fill="both", expand=True, pady=8)
    o_log.configure(state="disabled")

    hang = tk.Frame(khung)
    hang.pack(fill="x")
    b_chay = tk.Button(hang, text="🔄 Kiểm tra & cập nhật", width=22)
    b_chay.pack(side="left")
    b_mo = tk.Button(hang, text="▶️ Mở tool", width=14, state="disabled")
    b_mo.pack(side="left", padx=6)
    b_dong = tk.Button(hang, text="Đóng", width=10, command=cua.destroy)
    b_dong.pack(side="right")

    bo = BoCapNhat()

    def ghi(m):
        o_log.configure(state="normal")
        o_log.insert("end", str(m) + "\n")
        o_log.see("end")
        o_log.configure(state="disabled")

    moc = [0.0]

    def tien_do(da, tong):
        if time.time() - moc[0] < 0.2 and da != tong:
            return
        moc[0] = time.time()
        pt = (100.0 * da / tong) if tong else 0
        # Sửa widget từ luồng nền là hỏng ngẫu nhiên — đẩy về luồng giao diện.
        cua.after(0, lambda: (thanh.configure(value=pt),
                              nhan.configure(text="Đang tải... %.1f%%  (%.1f / %.1f MB)"
                                             % (pt, da / 1048576.0,
                                                (tong or 0) / 1048576.0))))

    bo.log = lambda m: cua.after(0, ghi, m)
    bo.tien_do = tien_do

    def xong(cau):
        nhan.configure(text=cau)
        ghi(cau)
        b_chay.configure(state="normal")
        if os.path.isfile(os.path.join(bo.goc, TEN_EXE)):
            b_mo.configure(state="normal")

    def lam():
        try:
            _, cau = bo.chay()
        except Exception as e:  # noqa: BLE001
            cau = "❌ Lỗi không lường trước: %s" % e
        cua.after(0, xong, cau)

    def bam():
        b_chay.configure(state="disabled")
        b_mo.configure(state="disabled")
        thanh.configure(value=0)
        nhan.configure(text="Đang kiểm tra...")
        threading.Thread(target=lam, daemon=True).start()

    b_chay.configure(command=bam)
    b_mo.configure(command=lambda: (bo.mo_tool(), cua.destroy()))
    ghi("Bấm '🔄 Kiểm tra & cập nhật' để bắt đầu.")
    ghi("Thư mục: %s" % bo.goc)
    cua.mainloop()
    return 0


def quyet_dinh(goc, hoi=None):
    """Kiem ban moi. -> ("cap_nhat", ban, ghi_chu) | ("mo_tool", ly_do, ""). THUAN (hoi tiem).

    Mat mang / GitHub loi / chua co ban phat hanh -> MO THANG TOOL (nguoi dung chot 29/09: khong
    co ban moi thi vao thang tool, khong bat doc loi)."""
    hien = phien_ban_dang_cai(goc)
    try:
        ban, _url, _co, _sha, ghi_chu = (hoi or hoi_ban_moi)()
    except Exception as e:  # noqa: BLE001
        return "mo_tool", "không kiểm tra được bản mới (%s)" % e, ""
    if so_sanh(ban, hien) > 0:
        return "cap_nhat", ban, ghi_chu
    return "mo_tool", "đang dùng bản mới nhất (%s)" % hien, ""


def mo_tool_neu_chua_chay(goc):
    """Mo tool; tool DA mo san thi khong mo them ban thu hai. True neu (da) co tool chay."""
    p = os.path.join(goc, TEN_EXE)
    if not os.path.isfile(p):
        return False
    if dang_chay(p):
        return True
    try:
        subprocess.Popen([p], cwd=goc)
        return True
    except OSError:
        return False


def chay_tu_dong(hoi_truoc=True):
    """BAM FILE UPDATE: tu kiem -> co ban moi thi hoi Yes/No (Yes cap nhat roi mo tool, No mo thang
    tool) -> khong co ban moi thi mo thang tool. Chi hien cua so tien do khi cap nhat."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    goc = thu_muc_goc()
    cua = tk.Tk()
    cua.title("Cập nhật LVC Manager Profile")
    cua.geometry("460x150")
    cua.resizable(False, False)
    khung = tk.Frame(cua, padx=14, pady=12)
    khung.pack(fill="both", expand=True)
    nhan = tk.Label(khung, text="Đang kiểm tra bản mới...", anchor="w", font=("Segoe UI", 10))
    nhan.pack(fill="x")
    thanh = ttk.Progressbar(khung, maximum=100, mode="indeterminate")
    thanh.pack(fill="x", pady=10)
    thanh.start(12)
    phu = tk.Label(khung, text="", anchor="w", fg="#6b7280", justify="left", wraplength=430)
    phu.pack(fill="x")
    ket = {"ma": 0}

    def ket_thuc(mo=True):
        if mo:
            mo_tool_neu_chua_chay(goc)
        cua.destroy()

    def sau_khi_kiem(kq):
        loai, a, b = kq
        if loai == "mo_tool":
            ket_thuc(True)                    # khong co ban moi / mat mang -> vao thang tool
            return
        ban, ghi_chu = a, b
        cau = "Có bản mới %s (đang dùng %s).\n" % (ban, phien_ban_dang_cai(goc))
        if ghi_chu:
            cau += "\nCó gì mới:\n" + "\n".join(ghi_chu.splitlines()[:10]) + "\n"
        cau += "\nCập nhật ngay? (Yes = tải và thay bản cũ · No = mở tool bản đang dùng)"
        # Nut vang trong tool DA hoi nguoi dung roi (--cap-nhat-ngay) -> khong hoi lai.
        if hoi_truoc and not messagebox.askyesno("Có bản mới", cau, parent=cua):
            ket_thuc(True)
            return
        thanh.stop()
        thanh.configure(mode="determinate", value=0)
        nhan.configure(text="Đang tải bản %s..." % ban)
        bo = BoCapNhat(goc)
        bo.log = lambda m: cua.after(0, lambda m=m: phu.configure(text=str(m)[:160]))

        def tien_do(da, tong):
            pt = (100.0 * da / tong) if tong else 0
            cua.after(0, lambda: (thanh.configure(value=pt), nhan.configure(
                text="Đang tải bản %s... %.0f%%  (%.1f / %.1f MB)"
                     % (ban, pt, da / 1048576.0, (tong or 0) / 1048576.0))))
        bo.tien_do = tien_do

        def lam():
            try:
                xong, cau2 = bo.chay()
            except Exception as e:  # noqa: BLE001
                xong, cau2 = False, "❌ Lỗi không lường trước: %s" % e
            cua.after(0, lambda: sau_cap_nhat(xong, cau2))
        threading.Thread(target=lam, daemon=True).start()

    def sau_cap_nhat(xong, cau2):
        if xong:
            ket_thuc(True)                    # cap nhat xong -> mo tool ban moi
            return
        ket["ma"] = 1
        messagebox.showwarning("Cập nhật", cau2 + "\n\nBản cũ vẫn nguyên. Tool sẽ mở bản đang dùng.",
                               parent=cua)
        ket_thuc(True)

    def kiem():
        kq = quyet_dinh(goc)
        cua.after(0, lambda: sau_khi_kiem(kq))

    cua.after(200, lambda: threading.Thread(target=kiem, daemon=True).start())
    cua.mainloop()
    return ket["ma"]


def bao_hop_thoai(cau):
    """Hiện một hộp thoại Windows bằng API hệ thống. True nếu hiện được.

    Cần cho ĐÚNG một tình huống, nhưng là tình huống tệ nhất: bản .exe đóng ở
    chế độ `--windowed` KHÔNG có cửa sổ console, nên `sys.stdout` là None và
    mọi lệnh in đều ném lỗi. Nếu tkinter cũng hỏng thì không còn đường nào nói
    cho người dùng biết chuyện gì — bộ cập nhật sẽ CHẾT IM LẶNG, đúng lúc người
    ta cần nó nhất. `MessageBoxW` của user32 thì luôn có trên Windows."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, str(cau), "Cập nhật LVC Manager Profile", 0x10)     # 0x10 = biểu tượng lỗi
        return True
    except Exception:  # noqa: BLE001
        return False


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    if "--console" in argv or "-c" in argv:
        if sys.stdout is None:
            bao_hop_thoai("Bản này đóng gói không có cửa sổ console nên không "
                          "chạy được chế độ --console.")
            return 1
        return chay_console()
    try:
        # Mac dinh: TU DONG (hoi Yes/No, khong co ban moi thi mo thang tool).
        # --thu-cong: cua so day du cu (nut Kiem tra & cap nhat + nhat ky).
        if "--thu-cong" in argv:
            return chay_gui()
        return chay_tu_dong(hoi_truoc="--cap-nhat-ngay" not in argv)
    except Exception as e:  # noqa: BLE001 — máy không có tkinter thì vẫn phải nói được
        cau = ("Không mở được cửa sổ cập nhật: %s\n\n"
               "Cách khác: tải tay tại\n"
               "https://github.com/%s/releases/latest" % (e, KHO))
        if sys.stdout is not None:
            print(cau)
            return chay_console()
        bao_hop_thoai(cau)
        return 1


if __name__ == "__main__":
    sys.exit(main())
