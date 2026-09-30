"""phat_hanh_gui.py — CUA SO PHAT HANH ban moi LVC Manager Profile len GitHub (kho congprofile).

Chay tren MAY NGUOI PHAT HANH (can token GitHub), KHONG phat cho nguoi dung.
Mo bang phat_hanh.bat, hoac nut "🚀 Phát hành" tren tool (chi hien khi chay tu ma nguon).

Nguoi dung CHON PHIEN BAN: goi y 3 muc (sua loi / them tinh nang / doi lon) hoac tu go;
hien cac ban DA CO tren GitHub va chan so trung / nho hon ban moi nhat (so thap hon thi
may nguoi dung khong coi la ban moi, khong bao gi duoc bao cap nhat).

Bam "Phat hanh" -> lam DUNG THU TU:
  1. ghi so ban vao core/phien_ban.py (TRUOC khi build -> exe mang dung so ban)
  2. python build.py              -> dist/LVC Manager Profile.exe
  3. python build_capnhat.py      -> dist/LVCProfileUpdate.exe (khi tich / khi chua co)
  4. python phat_hanh.py --ban X  -> day len GitHub Releases (+ capnhat.json sha256)
Buoc nao hong thi DUNG, chua day gi len; so ban da ghi thi tra lai nhu cu.
"""
import io
import os
import re
import subprocess
import sys
import threading

GOC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, GOC)

import capnhat  # noqa: E402  (chi thu vien chuan: so_sanh)
import phat_hanh  # noqa: E402

_SO = re.compile(r"^\d+\.\d+\.\d+$")


# ------------------------------------------------------------------ phan THUAN
def doc_phien_ban_code() -> str:
    """So ban dang ghi trong core/phien_ban.py (doc lai file, khong dung ban da import)."""
    s = io.open(os.path.join(GOC, "core", "phien_ban.py"), encoding="utf-8").read()
    m = re.search(r'^PHIEN_BAN = "([^"]+)"', s, re.M)
    return m.group(1) if m else "0.0.0"


def ghi_phien_ban_code(ban: str) -> str:
    """Ghi so ban vao core/phien_ban.py, tra so CU (de tra lai khi hong)."""
    p = os.path.join(GOC, "core", "phien_ban.py")
    s = io.open(p, encoding="utf-8").read()
    cu = doc_phien_ban_code()
    s2, n = re.subn(r'^PHIEN_BAN = "[^"]+"', 'PHIEN_BAN = "%s"' % ban, s, count=1, flags=re.M)
    if n != 1:
        raise RuntimeError("Không tìm thấy dòng PHIEN_BAN trong core/phien_ban.py")
    io.open(p, "w", encoding="utf-8", newline="\n").write(s2)
    return cu


def _du(muc) -> bool:
    """Ban tren GitHub da DU tep .exe chua (muc = (tag, ngay[, du])). Thieu co -> coi nhu du."""
    return bool(muc[2]) if len(muc) > 2 else True


def moi_nhat(da_co) -> str:
    """Ban MOI NHAT (chi tinh ban DA DU tep) trong danh sach tag, so theo tung so. Khong co -> ""."""
    ds = [m[0].lstrip("vV") for m in (da_co or []) if m and m[0] and _du(m)]
    ds = [x for x in ds if _SO.match(x)]
    if not ds:
        return ""
    tot = ds[0]
    for x in ds[1:]:
        if capnhat.so_sanh(x, tot) > 0:
            tot = x
    return tot


def goi_y(hien: str, da_co=()) -> list:
    """3 goi y (nhan, so): tang tu ban LON NHAT giua ban trong code va ban tren GitHub."""
    goc = hien if _SO.match(hien or "") else "0.0.0"
    mn = moi_nhat(da_co)
    if mn and capnhat.so_sanh(mn, goc) > 0:
        goc = mn
    x, y, z = (int(p) for p in goc.split("."))
    ra = [("%d.%d.%d" % (x, y, z + 1), "sửa lỗi"),
          ("%d.%d.0" % (x, y + 1), "thêm tính năng"),
          ("%d.0.0" % (x + 1), "thay đổi lớn")]
    # So trong code CHUA phat hanh va lon hon moi ban tren GitHub (vd lan dau 1.0.0) -> giu nguyen.
    if _SO.match(hien or "") and kiem_phien_ban(hien, da_co) == "":
        ra.insert(0, (hien, "giữ số hiện tại, chưa phát hành"))
    return ra


def kiem_phien_ban(ban: str, da_co=()) -> str:
    """"" = hop le; khac = cau loi doc duoc."""
    ban = (ban or "").strip().lstrip("vV")
    if not _SO.match(ban):
        return "Số bản phải dạng X.Y.Z, ví dụ 1.0.1"
    tags = {m[0].lstrip("vV") for m in (da_co or []) if _du(m)}
    if ban in tags:
        return "Bản %s ĐÃ CÓ trên GitHub — chọn số khác (phát hành đè sẽ thay file cũ)." % ban
    mn = moi_nhat(da_co)
    if mn and capnhat.so_sanh(ban, mn) <= 0:
        return ("Số %s không lớn hơn bản mới nhất %s — máy người dùng sẽ KHÔNG coi là "
                "bản mới." % (ban, mn))
    return ""


def cac_buoc(ban: str, ghi_chu: str, build_updater: bool) -> list:
    """Cac lenh chay theo thu tu: [(nhan, [lenh...])]."""
    py = sys.executable
    ra = [("Đóng gói tool", [py, os.path.join(GOC, "build.py")])]
    if build_updater:
        ra.append(("Đóng gói bộ cập nhật", [py, os.path.join(GOC, "build_capnhat.py")]))
    ra.append(("Đẩy lên GitHub", [py, os.path.join(GOC, "phat_hanh.py"), "--ban", ban,
                                  "--ghi-chu", ghi_chu or ("Bản %s" % ban)]
               + (["--du"] if build_updater else [])))
    return ra


# ------------------------------------------------------------------ giao dien
def chay_gui():
    import tkinter as tk
    from tkinter import messagebox, ttk

    from core.phien_ban import KHO_GITHUB, TEN_UPDATER

    cua = tk.Tk()
    cua.title("Phát hành bản mới — LVC Manager Profile")
    cua.geometry("760x620")
    khung = tk.Frame(cua, padx=12, pady=10)
    khung.pack(fill="both", expand=True)
    tk.Label(khung, text="🚀 Phát hành bản mới", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    tk.Label(khung, text="Kho: https://github.com/%s/releases" % KHO_GITHUB,
             fg="#2563eb").pack(anchor="w")

    hien = doc_phien_ban_code()
    token = phat_hanh.doc_token()
    tt_token = ("✅ Đã có mã truy cập GitHub" if token else
                "❌ CHƯA có mã truy cập GitHub — tạo file setup\\github_token.txt (xem HUONG-DAN-PHAT-HANH.md)")
    tk.Label(khung, text=tt_token, fg="#15803d" if token else "#b91c1c").pack(anchor="w", pady=(4, 0))

    o_ban = tk.Frame(khung)
    o_ban.pack(fill="x", pady=(10, 2))
    tk.Label(o_ban, text="Bản trong tool: %s" % hien).pack(side="left")
    nhan_da_co = tk.Label(o_ban, text="   Đang hỏi GitHub các bản đã có...", fg="#6b7280")
    nhan_da_co.pack(side="left")

    hang = tk.Frame(khung)
    hang.pack(fill="x", pady=4)
    tk.Label(hang, text="Phiên bản phát hành:", font=("Segoe UI", 10, "bold")).pack(side="left")
    bien_ban = tk.StringVar(master=cua)
    o_chon = ttk.Combobox(hang, textvariable=bien_ban, width=34)
    o_chon.pack(side="left", padx=8)
    nhan_loi = tk.Label(khung, text="", fg="#b91c1c", anchor="w")
    nhan_loi.pack(fill="x")

    da_co = []

    def dat_goi_y():
        gy = goi_y(hien, da_co)
        o_chon.configure(values=["%s   (%s)" % (so, nh) for so, nh in gy])
        if not bien_ban.get():
            bien_ban.set("%s   (%s)" % gy[0])
        kiem()

    def so_dang_chon():
        return (bien_ban.get() or "").split()[0] if (bien_ban.get() or "").split() else ""

    def kiem(*_a):
        loi = kiem_phien_ban(so_dang_chon(), da_co)
        nhan_loi.configure(text=("⚠️ " + loi) if loi else "")
        return loi

    bien_ban.trace_add("write", kiem)

    tk.Label(khung, text="Có gì mới (hiện cho người dùng khi báo cập nhật):").pack(anchor="w", pady=(8, 0))
    o_ghi_chu = tk.Text(khung, height=4, wrap="word")
    o_ghi_chu.pack(fill="x")

    bien_up = tk.BooleanVar(master=cua, value=not os.path.isfile(os.path.join(GOC, "dist", TEN_UPDATER)))
    tk.Checkbutton(khung, variable=bien_up,
                   text="Đóng gói + đẩy lại bộ cập nhật %s (chỉ cần khi sửa chính nó / lần đầu)"
                   % TEN_UPDATER).pack(anchor="w", pady=4)

    thanh = ttk.Progressbar(khung, maximum=100)
    thanh.pack(fill="x", pady=(6, 2))
    nhan_buoc = tk.Label(khung, text="Sẵn sàng.", anchor="w")
    nhan_buoc.pack(fill="x")
    o_log = tk.Text(khung, height=12, wrap="none", bg="#111827", fg="#e5e7eb")
    o_log.pack(fill="both", expand=True, pady=6)

    nut = tk.Frame(khung)
    nut.pack(fill="x")
    b_ph = tk.Button(nut, text="🚀 Phát hành", width=18, bg="#2563eb", fg="white",
                     font=("Segoe UI", 10, "bold"))
    b_ph.pack(side="left")
    tk.Button(nut, text="Đóng", width=10, command=cua.destroy).pack(side="right")

    def ghi(m):
        o_log.insert("end", str(m).rstrip("\n") + "\n")
        o_log.see("end")

    def hoi_da_co():
        ds = phat_hanh.cac_ban_da_phat_hanh(token)

        def xong():
            da_co[:] = ds
            if ds:
                nhan_da_co.configure(text="   Trên GitHub: " + ", ".join(
                    "%s (%s)" % (m[0], m[1]) if _du(m) else "%s (DỞ DANG — phát hành lại được)" % m[0]
                    for m in ds[:6]), fg="#374151")
            else:
                nhan_da_co.configure(text="   Trên GitHub: chưa có bản nào.", fg="#374151")
            dat_goi_y()
        cua.after(0, xong)

    threading.Thread(target=hoi_da_co, daemon=True).start()
    dat_goi_y()

    def lam(ban, ghi_chu, build_up):
        cu = None
        try:
            cu = ghi_phien_ban_code(ban)
            cua.after(0, ghi, "✍️ Ghi phiên bản %s vào core/phien_ban.py (cũ: %s)" % (ban, cu))
            buoc = cac_buoc(ban, ghi_chu, build_up)
            for i, (nhan, lenh) in enumerate(buoc, 1):
                cua.after(0, lambda i=i, nhan=nhan: (
                    nhan_buoc.configure(text="[%d/%d] %s..." % (i, len(buoc), nhan)),
                    thanh.configure(value=100.0 * (i - 1) / len(buoc))))
                p = subprocess.Popen(lenh, cwd=GOC, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                for dong in io.TextIOWrapper(p.stdout, encoding="utf-8", errors="replace"):
                    cua.after(0, ghi, dong)
                if p.wait() != 0:
                    raise RuntimeError("Bước '%s' hỏng (mã %s) — xem nhật ký." % (nhan, p.returncode))
            cua.after(0, lambda: (thanh.configure(value=100), nhan_buoc.configure(
                text="✅ XONG bản %s — https://github.com/%s/releases/tag/v%s" % (ban, KHO_GITHUB, ban))))
            cua.after(0, lambda: messagebox.showinfo(
                "Phát hành", "Đã phát hành bản %s.\nNgười dùng mở tool sẽ thấy nút báo cập nhật." % ban,
                parent=cua))
        except Exception as e:  # noqa: BLE001
            if cu is not None:
                try:
                    ghi_phien_ban_code(cu)          # chua phat hanh xong -> tra so cu
                except Exception:  # noqa: BLE001
                    pass
            cua.after(0, lambda e=e: (nhan_buoc.configure(text="❌ %s" % e), ghi("❌ %s" % e),
                                      ghi("Chưa đẩy xong lên GitHub; số bản trong code đã trả về %s." % cu)))
        finally:
            cua.after(0, lambda: b_ph.configure(state="normal"))

    def bam():
        if not phat_hanh.doc_token():
            messagebox.showerror("Phát hành", tt_token, parent=cua)
            return
        loi = kiem()
        if loi:
            messagebox.showwarning("Phát hành", loi, parent=cua)
            return
        ban = so_dang_chon()
        ghi_chu = o_ghi_chu.get("1.0", "end").strip()
        if not messagebox.askyesno(
                "Phát hành", "Phát hành bản %s lên GitHub?\n\nSẽ đóng gói lại tool (vài phút) rồi đẩy lên.\n"
                "Ghi chú: %s" % (ban, ghi_chu or "(trống)"), parent=cua):
            return
        b_ph.configure(state="disabled")
        o_log.delete("1.0", "end")
        threading.Thread(target=lam, args=(ban, ghi_chu, bool(bien_up.get())), daemon=True).start()

    b_ph.configure(command=bam)
    cua.mainloop()


if __name__ == "__main__":
    chay_gui()
