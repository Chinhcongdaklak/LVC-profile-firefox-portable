"""TU DO BAN MOI + nut Phat hanh tren thanh tieu de (ban tkinter cua ui/nut_capnhat Video Slide).

Nut vang "🎉 Co ban moi X — Cap nhat" CHI hien khi THAT SU co ban moi. Luat (giu nhu Video Slide):
 1. Hoi o LUONG NEN, HOAN toi sau khi cua so da hien (khong lam tool mo cham).
 2. Hoan chu khong bo.
 3. Mang hong / khong co ban moi / GitHub chan tan suat -> IM, khong hop thoai loi.
 4. Dung lai capnhat.py (so_sanh, hoi_ban_moi) — KHONG chep luat so phien ban.
Bam nut: hoi xac nhan -> mo LVCProfileUpdate.exe -> dong HAN tool (Windows khong cho thay .exe
dang chay; _on_close + _thoat_han giai phong file).

Nut "🚀 Phát hành" chi hien khi chay tu MA NGUON (khong phai .exe phat cho nguoi dung):
mo phat_hanh_gui.py de chon phien ban va day len GitHub.
"""
import os
import subprocess
import sys
import threading
from tkinter import messagebox

import customtkinter as ctk

from core.phien_ban import KHO_GITHUB, PHIEN_BAN, TEN_UPDATER

#: Hoan bao lau roi moi hoi GitHub (ms).
HOAN_MS = 4000


def thu_muc_cai() -> str:
    """Thu muc chua .exe (ban dong goi) hoac goc du an (chay ma nguon)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def phien_ban_hien() -> str:
    """Ban DANG CHAY: phien_ban.txt canh .exe (bo cap nhat ghi) neu co, khong thi so trong ma."""
    try:
        import capnhat
        ban = capnhat.phien_ban_dang_cai(thu_muc_cai())
    except Exception:  # noqa: BLE001
        ban = "0.0.0"
    return PHIEN_BAN if ban == "0.0.0" else ban


def ghi_phien_ban_canh_exe(goc: str = "", frozen=None) -> bool:
    """Ban .exe tu ghi phien_ban.txt = so ban dong trong exe (neu thieu / khac). True neu da ghi.

    Bo cap nhat doc file nay de biet ban DANG DUNG; thieu no thi tuong la 0.0.0 va hoi cap nhat
    mai (nguoi moi nhan tool lan dau chi co file exe). Chay ma nguon thi khong ghi."""
    if not (getattr(sys, "frozen", False) if frozen is None else frozen):
        return False
    from core.phien_ban import TEN_FILE_PHIEN_BAN
    p = os.path.join(goc or thu_muc_cai(), TEN_FILE_PHIEN_BAN)
    try:
        with open(p, encoding="utf-8") as fh:
            if fh.read().strip() == PHIEN_BAN:
                return False
    except OSError:
        pass
    try:
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(PHIEN_BAN)
        return True
    except OSError:
        return False


def la_ma_nguon() -> bool:
    return not getattr(sys, "frozen", False)


def co_ban_moi(hoi=None, hien: str = "") -> tuple:
    """(ban, ghi_chu) neu GitHub co ban MOI HON ban dang chay; () neu khong / loi. THUAN (hoi tiem)."""
    try:
        import capnhat
        hoi = hoi or capnhat.hoi_ban_moi
        ban, _url, _co, _sha, ghi_chu = hoi()
        if capnhat.so_sanh(ban, hien or phien_ban_hien()) > 0:
            return ban, ghi_chu
    except Exception:  # noqa: BLE001  (luat 3: mang hong thi im)
        pass
    return ()


class NutCapNhat:
    """Gan 2 nut vao ``header`` cua App: cap nhat (an toi khi co ban moi) + phat hanh (ma nguon)."""

    def __init__(self, app, header):
        self.app = app
        self._ban, self._ghi_chu = "", ""
        ghi_phien_ban_canh_exe()
        self.nut = ctk.CTkButton(header, text="", width=10, fg_color="#f59e0b",
                                 hover_color="#fbbf24", text_color="#111827",
                                 font=ctk.CTkFont(weight="bold"), command=self._bam)
        self.nut_ph = None
        if la_ma_nguon():
            self.nut_ph = ctk.CTkButton(header, text="🚀 Phát hành", width=110,
                                        fg_color="#7c3aed", hover_color="#6d28d9",
                                        command=self.mo_phat_hanh)
            self.nut_ph.pack(side="right", padx=(0, 6))

    def bat_dau_do(self) -> None:
        """Hen gio hoi — goi SAU khi cua so da hien."""
        try:
            self.app.after(HOAN_MS, self._hoi)
        except Exception:  # noqa: BLE001
            pass

    def _hoi(self) -> None:
        def lam():
            kq = co_ban_moi()
            if kq:
                try:
                    self.app._post(lambda: self._hien(*kq))
                except Exception:  # noqa: BLE001
                    pass
        threading.Thread(target=lam, daemon=True).start()

    def _hien(self, ban: str, ghi_chu: str) -> None:
        self._ban, self._ghi_chu = ban, ghi_chu
        self.nut.configure(text=f"🎉 Có bản mới {ban} — Cập nhật", width=230)
        self.nut.pack(side="right", padx=(0, 8))

    def _bam(self) -> None:
        up = os.path.join(thu_muc_cai(), TEN_UPDATER)
        cau = f"Có bản mới {self._ban} (đang dùng {phien_ban_hien()})."
        if self._ghi_chu:
            cau += "\n\nCó gì mới:\n" + "\n".join(self._ghi_chu.splitlines()[:10])
        if not os.path.isfile(up):
            messagebox.showinfo("Cập nhật", cau + f"\n\nKhông thấy {TEN_UPDATER} cạnh tool.\n"
                                f"Tải tay tại:\nhttps://github.com/{KHO_GITHUB}/releases/latest",
                                parent=self.app)
            return
        if not messagebox.askyesno("Cập nhật", cau + "\n\nTool sẽ ĐÓNG LẠI để bộ cập nhật thay file "
                                   "(Windows không cho ghi đè file đang chạy).\nTiếp tục?",
                                   parent=self.app):
            return
        try:
            # Da hoi Yes o day -> bo cap nhat khong hoi lai, cap nhat luon roi mo tool ban moi.
            subprocess.Popen([up, "--cap-nhat-ngay"], cwd=os.path.dirname(up))
        except OSError as e:
            messagebox.showwarning("Cập nhật", f"Không mở được bộ cập nhật: {e}", parent=self.app)
            return
        # Dong HAN tool: _on_close dung vong lap + destroy -> run() goi _thoat_han (nha khoa .exe).
        self.app._on_close()

    def mo_phat_hanh(self) -> None:
        """Mo cua so Phat hanh (chon phien ban) — tien trinh rieng, khong chan tool."""
        goc = thu_muc_cai()
        try:
            py = sys.executable.replace("python.exe", "pythonw.exe") if sys.executable.lower().endswith(
                "python.exe") else sys.executable
            subprocess.Popen([py, os.path.join(goc, "phat_hanh_gui.py")], cwd=goc)
        except OSError as e:
            messagebox.showwarning("Phát hành", f"Không mở được cửa sổ phát hành: {e}", parent=self.app)
