"""Hop thoai chuyen may: XUAT (tich chon phan nao vao goi) va NHAP (tich chon phan nao gop
vao may nay + xem truoc + chon lai thu muc video / noi giai nen kho video).

Nghiep vu o core/chuyen_may.py. Bon phan nguoi dung tich chon (14/10): Acc · Trang tu dong ·
Profile · Kho video — tich cai nao thi lay cai do.
"""

from __future__ import annotations

import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core import chuyen_may as cm
from ui.dialogs import BaseDialog

PAD = 10


def co_dung_luong(byte: int) -> str:
    """1536 -> '1.5 KB' ... (thuan)."""
    so = float(byte or 0)
    for don_vi in ("B", "KB", "MB", "GB"):
        if so < 1024 or don_vi == "GB":
            return f"{so:.0f} {don_vi}" if don_vi == "B" else f"{so:.1f} {don_vi}"
        so /= 1024
    return f"{so:.1f} GB"


def tom_tat_ke_hoach(goi: cm.Goi, kh: dict, video_vao: str = "") -> str:
    """Chu xem truoc (thuan, thuoc kiem duoc)."""
    m = goi.manifest
    dong = [f"Gói từ máy: {m.get('may', '?')} · tạo lúc {m.get('tao_luc', '?')}", ""]
    if not kh.get("co_acc", True):
        dong.append("Acc: KHÔNG gộp — giữ nguyên toàn bộ acc của máy này.")
    if not kh.get("co_trang", True):
        dong.append("Trang tự động: KHÔNG nhập.")
    if not kh.get("co_profile", True):
        dong.append("Profile: KHÔNG đụng — giữ nguyên thư mục profile của máy này.")
    if video_vao and goi.video:
        tong = sum(int(v.get("byte") or 0) for v in goi.video)
        dong.append(f"Kho video: giải nén {len(goi.video)} thư mục ({co_dung_luong(tong)}) "
                    f"vào {video_vao}")
    elif goi.video:
        dong.append("Kho video: KHÔNG giải nén.")
    dong.append("")
    co_profile = kh.get("co_profile", True)
    for p in cm.NEN_TANG:
        moi, de = kh["acc_moi"].get(p) or [], kh["acc_ghi_de"].get(p) or []
        them, bo = kh["trang_them"].get(p) or [], kh["trang_bo_qua"].get(p) or []
        if not (moi or de or them or bo):
            continue
        co_pf = goi.profile.get(p, set()) if co_profile else set()
        dong.append(f"══ {cm.TEN_NEN_TANG[p]} ══")
        if kh.get("co_acc", True):
            dong.append(f"Acc MỚI thêm vào: {len(moi)}")
            for ma in moi:
                dong.append(f"   + {ma}" + ("   (kèm profile)" if ma in co_pf else ""))
            dong.append(f"Acc TRÙNG — GHI ĐÈ bằng bản máy cũ: {len(de)}")
            for ma in de:
                dong.append(f"   ↻ {ma}" + ("   (kèm profile)" if ma in co_pf
                                            else "   (chỉ thông tin — giữ profile máy này)"))
        if kh.get("co_trang", True):
            dong.append(f"Trang auto đăng THÊM (tắt sẵn tự động đăng): {len(them)}")
            for t in them:
                dong.append(f"   + {t['ten']}   [{t['kind']}]")
                if t.get("acc_thieu"):
                    dong.append(f"       ⚠ dùng acc máy này CHƯA có: {', '.join(t['acc_thieu'])}"
                                " — thêm acc (hoặc tích Acc) rồi mới bật đăng")
            dong.append(f"Trang BỎ QUA (trùng): {len(bo)}")
            for t in bo:
                dong.append(f"   – {t['ten']}: {t['ly_do']}")
        dong.append("")
    return "\n".join(dong)


class NhapGoiDialog(BaseDialog):
    """show() -> (ban do thu muc {cu: moi}, ke hoach, video_vao) hoac None neu huy.

    ``lap(co_acc, co_trang, co_profile) -> ke hoach``: doi o tich thi lap lai ke hoach.
    Phan nao goi KHONG co thi o tich do bi khoa.
    """

    def __init__(self, parent, goi: cm.Goi, kh: dict, lap=None, video_mac_dinh: str = ""):
        super().__init__(parent, "Nhập gói chuyển máy — chọn phần cần lấy", 1000, 800)
        self.goi, self.kh, self._lap = goi, kh, lap
        self._o: dict = {}                # duong dan cu -> (entry, nhan trang thai)

        ctk.CTkLabel(self, text="Tích phần nào thì lấy phần đó vào máy này",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=PAD,
                                                                   pady=(PAD, 4))
        hang = ctk.CTkFrame(self, fg_color="transparent")
        hang.pack(fill="x", padx=PAD)
        co = {
            "acc": any((goi.acc.get(p) or {}).get("accounts") for p in cm.NEN_TANG),
            "trang": any((goi.trang.get(p) or {}).get("jobs") for p in cm.NEN_TANG),
            "profile": any(goi.profile.get(p) for p in cm.NEN_TANG),
            "video": bool(goi.video),
        }
        tong_video = sum(int(v.get("byte") or 0) for v in goi.video)
        nhan = {
            "acc": "👤 Acc (thêm mới + GHI ĐÈ acc trùng)",
            "trang": "📄 Trang tự động",
            "profile": "🦊 Profile",
            "video": f"🎬 Kho video ({co_dung_luong(tong_video)})" if goi.video else "🎬 Kho video",
        }
        mac = {"acc": kh.get("co_acc", True), "trang": kh.get("co_trang", True),
               "profile": kh.get("co_profile", True), "video": True}
        self.chon: dict = {}
        self.o_tich: dict = {}
        for k in ("acc", "trang", "profile", "video"):
            self.chon[k] = tk.BooleanVar(value=bool(co[k] and mac[k]))
            o = ctk.CTkCheckBox(hang, text=nhan[k] + ("" if co[k] else " — gói không có"),
                                variable=self.chon[k], command=self._doi_chon,
                                state="normal" if co[k] else "disabled")
            o.pack(side="left", padx=(0, 14))
            self.o_tich[k] = o

        self.hang_video = ctk.CTkFrame(self, fg_color="transparent")
        self.hang_video.pack(fill="x", padx=PAD, pady=(6, 0))
        ctk.CTkLabel(self.hang_video, text="Giải nén kho video vào:").pack(side="left")
        self.video_vao = ctk.CTkEntry(self.hang_video, width=520)
        self.video_vao.pack(side="left", padx=4)
        self.video_vao.insert(0, video_mac_dinh)
        self.video_vao.bind("<KeyRelease>", lambda _e: self._ve_tat_ca())
        ctk.CTkButton(self.hang_video, text="Chọn…", width=64,
                      command=self._chon_video_vao).pack(side="left")
        self.nhan_video = ctk.CTkLabel(self.hang_video, text="", text_color="gray55")
        self.nhan_video.pack(side="left", padx=8)

        self.box = ctk.CTkTextbox(self, height=230, wrap="none")
        self.box.pack(fill="both", expand=False, padx=PAD, pady=(6, 0))

        ctk.CTkLabel(self, text="Thư mục video của các trang (bỏ tích Kho video thì chép video "
                                "tay rồi trỏ lại ở đây):",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=PAD, pady=(10, 2))
        goc = ctk.CTkFrame(self, fg_color="transparent")
        goc.pack(fill="x", padx=PAD)
        ctk.CTkLabel(goc, text="Thay gốc: đường dẫn bắt đầu bằng").pack(side="left")
        self.tu = ctk.CTkEntry(goc, width=250)
        self.tu.pack(side="left", padx=4)
        ctk.CTkLabel(goc, text="đổi thành").pack(side="left")
        self.thanh = ctk.CTkEntry(goc, width=250)
        self.thanh.pack(side="left", padx=4)
        ctk.CTkButton(goc, text="Chọn…", width=64,
                      command=lambda: self._chon(self.thanh)).pack(side="left")
        ctk.CTkButton(goc, text="Áp dụng", width=80, command=self._ap_goc).pack(side="left", padx=4)

        self.khung = ctk.CTkScrollableFrame(self, height=200)
        self.khung.pack(fill="both", expand=True, padx=PAD, pady=4)
        self.khung.grid_columnconfigure(1, weight=1)

        nut = ctk.CTkFrame(self, fg_color="transparent")
        nut.pack(fill="x", padx=PAD, pady=PAD)
        ctk.CTkLabel(nut, text="Trang nhập vào luôn TẮT “Bật tự động đăng” — kiểm lại rồi tự bật "
                               "(và tắt ở máy cũ để không đăng trùng).",
                     text_color="#c07000").pack(side="left")
        ctk.CTkButton(nut, text="Huỷ", width=90, fg_color="gray45",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(nut, text="📥 Nhập vào máy này", width=170, fg_color="#2f7d4f",
                      command=self._ok).pack(side="right", padx=6)
        self._ve_tat_ca(ve_bang=True)

    # ---- ve -----------------------------------------------------------
    def _video_vao(self) -> str:
        if not (self.chon["video"].get() and self.goi.video):
            return ""
        return self.video_vao.get().strip()

    def _ve_tat_ca(self, ve_bang: bool = False) -> None:
        dang_video = bool(self.chon["video"].get() and self.goi.video)
        trang = "normal" if dang_video else "disabled"
        self.video_vao.configure(state=trang)
        if dang_video:
            tong = sum(int(v.get("byte") or 0) for v in self.goi.video)
            self.nhan_video.configure(text=f"{len(self.goi.video)} thư mục · {co_dung_luong(tong)}")
        else:
            self.nhan_video.configure(text="")
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        self.box.insert("1.0", tom_tat_ke_hoach(self.goi, self.kh, self._video_vao()))
        self.box.configure(state="disabled")
        if ve_bang:
            self._ve_bang()
        else:
            self._kiem()

    def _ve_bang(self) -> None:
        for w in self.khung.winfo_children():
            w.destroy()
        self._o = {}
        thu_muc = self.kh.get("thu_muc") or []
        self.tu.delete(0, "end")
        chung = ""
        if len(thu_muc) > 1:
            try:
                chung = os.path.commonpath(thu_muc)
            except ValueError:
                chung = ""
        elif thu_muc:
            chung = os.path.dirname(thu_muc[0])
        self.tu.insert(0, chung)
        if not thu_muc:
            ctk.CTkLabel(self.khung, text="(không có trang nào cần thư mục video)",
                         text_color="gray60").grid(row=0, column=0, sticky="w")
        for i, f in enumerate(thu_muc):
            ctk.CTkLabel(self.khung, text=f, anchor="w", width=330).grid(row=i, column=0, sticky="w")
            e = ctk.CTkEntry(self.khung)
            e.grid(row=i, column=1, sticky="ew", padx=4, pady=2)
            e.insert(0, f)
            ctk.CTkButton(self.khung, text="Chọn…", width=60,
                          command=lambda e=e: self._chon(e)).grid(row=i, column=2)
            nhan = ctk.CTkLabel(self.khung, text="", width=170, anchor="w")
            nhan.grid(row=i, column=3, padx=4)
            e.bind("<KeyRelease>", lambda _e: self._kiem())
            self._o[f] = (e, nhan)
        self._kiem()

    def _giai_tu_goi(self) -> dict:
        """Thu muc cu -> noi se giai nen (chi khi dang tich Kho video)."""
        vao = self._video_vao()
        return cm.noi_giai_video(self.goi, vao) if vao else {}

    def _kiem(self) -> None:
        giai = self._giai_tu_goi()
        for cu, (e, nhan) in self._o.items():
            if cu in giai:
                e.configure(state="normal")
                e.delete(0, "end")
                e.insert(0, giai[cu])
                e.configure(state="disabled")
                nhan.configure(text="📦 giải nén từ gói", text_color="#2f6fb0")
                continue
            if e.cget("state") == "disabled":
                e.configure(state="normal")
                e.delete(0, "end")
                e.insert(0, cu)
            v = e.get().strip()
            if v and os.path.isdir(v):
                nhan.configure(text="✅ có thư mục", text_color="#2f7d4f")
            else:
                nhan.configure(text="⚠ chưa có thư mục", text_color="#c07000")

    # ---- thao tac -----------------------------------------------------
    def _doi_chon(self) -> None:
        if self._lap is not None:
            self.kh = self._lap(bool(self.chon["acc"].get()), bool(self.chon["trang"].get()),
                                bool(self.chon["profile"].get()))
        self._ve_tat_ca(ve_bang=True)

    def _chon_video_vao(self) -> None:
        d = filedialog.askdirectory(parent=self, initialdir=self.video_vao.get() or None)
        if d:
            self.video_vao.delete(0, "end")
            self.video_vao.insert(0, os.path.normpath(d))
            self._ve_tat_ca()

    def _chon(self, entry) -> None:
        d = filedialog.askdirectory(parent=self, initialdir=entry.get() or None)
        if d:
            entry.delete(0, "end")
            entry.insert(0, os.path.normpath(d))
            self._kiem()

    def _ap_goc(self) -> None:
        giai = self._giai_tu_goi()
        bd = cm.thay_goc([f for f in self._o if f not in giai],
                         self.tu.get().strip(), self.thanh.get().strip())
        for cu, moi in bd.items():
            e = self._o[cu][0]
            e.delete(0, "end")
            e.insert(0, moi)
        self._kiem()

    def ban_do(self) -> dict:
        giai = self._giai_tu_goi()
        return {cu: e.get().strip() for cu, (e, _n) in self._o.items()
                if cu not in giai and e.get().strip() and e.get().strip() != cu}

    def thieu_dung_luong(self) -> str:
        """Chu bao loi neu o dia khong du cho kho video (rong = du)."""
        vao = self._video_vao()
        if not vao:
            return ""
        can = sum(int(v.get("byte") or 0) for v in self.goi.video)
        goc = os.path.abspath(vao)
        while goc and not os.path.isdir(goc):
            cha = os.path.dirname(goc)
            if cha == goc:
                break
            goc = cha
        try:
            con = shutil.disk_usage(goc).free
        except OSError:
            return ""
        if can + 200 * 1024 * 1024 > con:
            return (f"Ổ đĩa chỉ còn {co_dung_luong(con)}, kho video cần {co_dung_luong(can)}.\n"
                    "Chọn ổ khác hoặc bỏ tích Kho video.")
        return ""

    def _ok(self) -> None:
        if not any(v.get() for v in self.chon.values()):
            messagebox.showwarning("Nhập gói", "Chưa tích phần nào để lấy.", parent=self)
            return
        if self.chon["video"].get() and self.goi.video and not self._video_vao():
            messagebox.showwarning("Nhập gói", "Chọn thư mục để giải nén kho video.", parent=self)
            return
        loi = self.thieu_dung_luong()
        if loi:
            messagebox.showerror("Nhập gói", loi, parent=self)
            return
        self.result = (self.ban_do(), self.kh, self._video_vao())
        self.destroy()


class XuatGoiDialog(BaseDialog):
    """Tich chon phan nao vao goi.

    show() -> {"co_acc","co_trang","co_profile","co_video"} hoac None.
    ``video`` = cm.uoc_luong_video(...) de hien goi nang co nao.
    """

    def __init__(self, parent, so_trang: int, so_acc: int, so_profile: int = 0,
                 video: dict | None = None):
        super().__init__(parent, "Xuất gói chuyển máy", 640, 420)
        video = video or {"thu_muc": 0, "file": 0, "byte": 0, "thieu": []}
        ctk.CTkLabel(self, text="Tích phần nào thì gói phần đó sang máy mới",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=PAD,
                                                                   pady=(PAD, 6))
        self.co_acc = tk.BooleanVar(value=True)
        self.co_trang = tk.BooleanVar(value=True)
        self.co_profile = tk.BooleanVar(value=False)
        self.co_video = tk.BooleanVar(value=False)
        chu_video = (f"🎬 Kho video — {video['thu_muc']} thư mục, {video['file']} file, "
                     f"{co_dung_luong(video['byte'])}")
        for var, chu, mo in (
                (self.co_acc, f"👤 Acc — {so_acc} acc (cookie, mật khẩu, 2FA, proxy, nhóm)", ""),
                (self.co_trang, f"📄 Trang tự động — {so_trang} trang (fanpage / nhóm / X / YouTube)",
                 "kèm lịch, tab, nhóm trang, sổ bài đã đăng"),
                (self.co_profile, f"🦊 Profile — {so_profile} profile (gói nhẹ, bỏ cache)",
                 "bỏ tích nếu tự chép thư mục profile bằng tay"),
                (self.co_video, chu_video, "rất nặng — chỉ tích khi không chép video bằng tay")):
            ctk.CTkCheckBox(self, text=chu, variable=var).pack(anchor="w", padx=PAD + 6, pady=(6, 0))
            if mo:
                ctk.CTkLabel(self, text="      " + mo, text_color="gray55").pack(anchor="w", padx=PAD + 6)
        if video.get("thieu"):
            ctk.CTkLabel(self, text=f"⚠ {len(video['thieu'])} thư mục video không tồn tại trên máy "
                                    "này — sẽ bỏ qua.", text_color="#c07000").pack(anchor="w", padx=PAD,
                                                                                  pady=(6, 0))
        nut = ctk.CTkFrame(self, fg_color="transparent")
        nut.pack(fill="x", side="bottom", padx=PAD, pady=PAD)
        ctk.CTkButton(nut, text="Huỷ", width=90, fg_color="gray45",
                      command=self._cancel).pack(side="right")
        ctk.CTkButton(nut, text="📤 Chọn nơi lưu & xuất", width=180, fg_color="#2f7d4f",
                      command=self._ok).pack(side="right", padx=6)

    def _ok(self) -> None:
        kq = {"co_acc": bool(self.co_acc.get()), "co_trang": bool(self.co_trang.get()),
              "co_profile": bool(self.co_profile.get()), "co_video": bool(self.co_video.get())}
        if not any(kq.values()):
            messagebox.showwarning("Xuất gói", "Chưa tích phần nào để gói.", parent=self)
            return
        self.result = kq
        self.destroy()
