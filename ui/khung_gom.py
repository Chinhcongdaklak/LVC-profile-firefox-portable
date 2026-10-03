"""Khung GOM CỬA SỔ — một cửa sổ chứa tất cả Firefox đang mở, cuộn chuột để xem tiếp.

Hai chế độ (Cài đặt):
  * ``luoi``  — cửa sổ Firefox vẫn độc lập, khung chỉ DỜI chúng theo lưới (an toàn).
  * ``nhot``  — SetParent: Firefox thành cửa sổ CON của khung (một cửa sổ thật sự).

Mặc định 2 cột, nhìn 2 hàng, lăn chuột xuống xem tiếp. Ô ngoài vùng nhìn -> THU NHỎ
(Firefox ngừng vẽ, nhẹ máy khi mở 20-30 acc).

AN TOÀN (probe 2026-10-02): chế độ ``nhot`` mà tiến trình tool chết thì cửa sổ Firefox bị
huỷ theo. Vì vậy khung LUÔN thả cửa sổ ra khi đóng, khi tool thoát và qua ``atexit``.
"""

from __future__ import annotations

import atexit
import tkinter as tk

import customtkinter as ctk

from core import cuaso

PAD = 8
NHIP_MS = 2500          # nhịp quét acc mới mở / cửa sổ đã đóng


class KhungGom(ctk.CTkToplevel):
    def __init__(self, app, che_do: str = cuaso.CHE_DO_LUOI, cot: int = cuaso.COT_MAC_DINH,
                 hang_nhin: int = cuaso.HANG_NHIN_MAC_DINH):
        super().__init__(app)
        self.app = app
        self.che_do = che_do if che_do in (cuaso.CHE_DO_LUOI, cuaso.CHE_DO_NHOT) else cuaso.CHE_DO_LUOI
        self.cot = max(1, int(cot))
        self.hang_nhin = max(1, int(hang_nhin))
        self._cuon_y = 0
        self._o: list = []          # [(nhan, hwnd)] theo thứ tự lưới
        self._nhan: dict = {}       # hwnd -> nhãn acc (giữ cả khi cửa sổ đã bị nhốt)
        self._dong = False

        self.title("Gom cửa sổ trình duyệt")
        self.geometry("1280x760+40+20")
        self.protocol("WM_DELETE_WINDOW", self.dong)

        thanh = ctk.CTkFrame(self, fg_color="transparent")
        thanh.pack(fill="x", padx=PAD, pady=(PAD, 2))
        ctk.CTkLabel(thanh, text="Cột:").pack(side="left")
        self.e_cot = ctk.CTkEntry(thanh, width=50)
        self.e_cot.insert(0, str(self.cot))
        self.e_cot.pack(side="left", padx=(4, 10))
        ctk.CTkLabel(thanh, text="Hàng nhìn:").pack(side="left")
        self.e_hang = ctk.CTkEntry(thanh, width=50)
        self.e_hang.insert(0, str(self.hang_nhin))
        self.e_hang.pack(side="left", padx=(4, 10))
        ctk.CTkButton(thanh, text="↻ Xếp lại", width=100, command=self.xep_lai).pack(side="left")
        self.lbl = ctk.CTkLabel(thanh, text="", text_color="gray60")
        self.lbl.pack(side="left", padx=10)
        ctk.CTkLabel(thanh, text="lăn chuột để xem tiếp", text_color="gray55").pack(side="right")

        than = ctk.CTkFrame(self, fg_color="transparent")
        than.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        self.vung = tk.Frame(than, bg="#1a1a1a", highlightthickness=0)
        self.vung.pack(side="left", fill="both", expand=True)
        self.thanh_cuon = ctk.CTkScrollbar(than, command=self._keo_cuon)
        self.thanh_cuon.pack(side="right", fill="y")

        for w in (self, self.vung):
            w.bind("<MouseWheel>", self._lan_chuot)
        self.bind("<Configure>", lambda _e: self._hen_xep())

        atexit.register(self._tha_het_an_toan)
        self.after(300, self.xep_lai)
        self.after(NHIP_MS, self._nhip)

    # ------------------------------------------------------------- thu thập
    def _cac_cua_so(self) -> list:
        """[(nhãn, hwnd)] — mọi acc (Facebook + X) đang mở Firefox.

        Cửa sổ ĐÃ NHỐT không còn là cửa sổ top-level nên không quét lại được -> phải GIỮ
        theo sổ ``cuaso.dang_nhot()``, kẻo quét nhịp sau là danh sách rỗng (lỗi 02/10).
        """
        ra, da_co = [], set()
        for nhan, store, mgr in self._nguon():
            for a in getattr(store, "accounts", []):
                h = cuaso.cua_so_cua_acc(mgr, a)
                if h:
                    ten = f"{nhan}:{a.id}"
                    self._nhan[h] = ten
                    ra.append((ten, h))
                    da_co.add(h)
        # Cửa sổ ĐANG ẨN cũng không nằm trong EnumWindows -> cùng phải giữ, kẻo bị bỏ rơi
        # ở trạng thái ẩn (người dùng tưởng mất trình duyệt — lỗi 02/10).
        for h in list(cuaso.dang_nhot()) + list(cuaso.dang_an()):
            if h not in da_co and cuaso.con_song(h):
                da_co.add(h)
                ra.append((self._nhan.get(h, f"hwnd {h}"), h))
        return ra

    def _nguon(self) -> list:
        ds = [("FB", getattr(self.app, "store", None), getattr(self.app, "manager", None))]
        xt = getattr(self.app, "x_acc_tab", None)
        if xt is not None:
            ds.append(("X", getattr(xt, "store", None), getattr(xt, "manager", None)))
        return [(n, s, m) for n, s, m in ds if s is not None and m is not None]

    # ------------------------------------------------------------- bày lưới
    def _so_nguyen(self, entry, mac: int) -> int:
        try:
            return max(1, int(entry.get().strip() or mac))
        except (ValueError, tk.TclError):
            return mac

    def xep_lai(self) -> None:
        if self._dong:
            return
        self.cot = self._so_nguyen(self.e_cot, cuaso.COT_MAC_DINH)
        self.hang_nhin = self._so_nguyen(self.e_hang, cuaso.HANG_NHIN_MAC_DINH)
        self._o = sorted(self._cac_cua_so(), key=lambda x: x[0])
        self._ve()

    def _ve(self) -> None:
        if self._dong or not self.winfo_exists():
            return
        vp_rong = max(200, self.vung.winfo_width())
        vp_cao = max(150, self.vung.winfo_height())
        o_rong, o_cao = cuaso.kich_thuoc_o(vp_rong, vp_cao, self.cot, self.hang_nhin)
        cao_het = cuaso.tong_cao(len(self._o), self.cot, o_cao)
        self._cuon_y = max(0, min(self._cuon_y, max(0, cao_het - vp_cao)))

        goc_x, goc_y = (0, 0) if self.che_do == cuaso.CHE_DO_NHOT else self._goc_man_hinh()
        hien = 0
        for o in cuaso.bo_cuc(len(self._o), self.cot, o_rong, o_cao, self._cuon_y, vp_cao):
            _nhan, hwnd = self._o[o["i"]]
            if not cuaso.con_song(hwnd):
                continue
            if not o["hien"]:
                # Ngoài vùng nhìn -> Firefox ngừng vẽ. Chế độ nhốt thì ẨN hẳn (cửa sổ con
                # thu nhỏ vẫn chiếm một ô trong khung), chế độ lưới thì thu nhỏ.
                if self.che_do == cuaso.CHE_DO_NHOT:
                    cuaso.an(hwnd)
                else:
                    cuaso.thu_nho(hwnd)
                continue
            hien += 1
            if self.che_do == cuaso.CHE_DO_NHOT:
                cuaso.hien(hwnd)
            else:
                cuaso.khoi_phuc(hwnd)
            if self.che_do == cuaso.CHE_DO_NHOT:
                if cuaso.gom(hwnd, int(self.vung.winfo_id())):
                    self._ghi_so_nhot()
            cuaso.dat_vi_tri(hwnd, goc_x + o["x"], goc_y + o["y"], o["rong"], o["cao"])

        self._cap_nhat_thanh_cuon(cao_het, vp_cao)
        self.lbl.configure(text=f"{len(self._o)} trình duyệt · đang hiện {hien} · "
                                f"ô {o_rong}×{o_cao} · chế độ "
                                + ("nhốt vào khung" if self.che_do == cuaso.CHE_DO_NHOT else "xếp lưới"))

    def _goc_man_hinh(self) -> tuple:
        """Chế độ xếp lưới: cửa sổ Firefox nằm TRÊN MÀN HÌNH, lấy gốc là vùng trống của khung."""
        try:
            return (self.vung.winfo_rootx(), self.vung.winfo_rooty())
        except tk.TclError:
            return (0, 0)

    def _cap_nhat_thanh_cuon(self, cao_het: int, vp_cao: int) -> None:
        if cao_het <= vp_cao:
            self.thanh_cuon.set(0, 1)
            return
        dau = self._cuon_y / cao_het
        self.thanh_cuon.set(dau, min(1.0, dau + vp_cao / cao_het))

    # ------------------------------------------------------------- cuộn
    def _lan_chuot(self, e) -> None:
        buoc = 120 if e.delta < 0 else -120
        self._cuon_y = max(0, self._cuon_y + buoc)
        self._ve()

    def _keo_cuon(self, *args) -> None:
        if not args:
            return
        vp_cao = max(150, self.vung.winfo_height())
        _o_rong, o_cao = cuaso.kich_thuoc_o(max(200, self.vung.winfo_width()), vp_cao,
                                            self.cot, self.hang_nhin)
        cao_het = cuaso.tong_cao(len(self._o), self.cot, o_cao)
        if args[0] == "moveto":
            self._cuon_y = int(float(args[1]) * cao_het)
        elif args[0] == "scroll":
            self._cuon_y += int(float(args[1])) * (o_cao if args[2] == "pages" else 120)
        self._ve()

    # ------------------------------------------------------------- nhịp / đóng
    def _hen_xep(self) -> None:
        if getattr(self, "_hen", None):
            try:
                self.after_cancel(self._hen)
            except tk.TclError:
                pass
        self._hen = self.after(250, self._ve)

    def _nhip(self) -> None:
        """Quét lại: acc mới mở thì thêm ô, cửa sổ đã đóng thì bỏ ô."""
        if self._dong or not self.winfo_exists():
            return
        try:
            moi = self._cac_cua_so()
            moi.sort(key=lambda x: x[0])
            if [h for _n, h in moi] != [h for _n, h in self._o]:
                self._o = moi
                self._ve()
        finally:
            self.after(NHIP_MS, self._nhip)

    def _ghi_so_nhot(self) -> None:
        """Ghi pid đang nhốt ra đĩa: tool chết giữa chừng thì lần mở sau dọn đúng tiến trình đó."""
        try:
            cuaso.ghi_so_nhot([cuaso.pid_cua(h) for h in cuaso.dang_nhot()])
        except Exception:  # noqa: BLE001
            pass

    def _tha_het_an_toan(self) -> None:
        try:
            cuaso.tha_het()
            cuaso.xoa_so_nhot()
        except Exception:  # noqa: BLE001
            pass

    def dong(self) -> None:
        """Đóng khung: THẢ + HIỆN hết cửa sổ về desktop rồi mới huỷ khung."""
        self._dong = True
        self._tha_het_an_toan()
        cuaso.hien_het()
        # Trả về desktop: RẢI SO LE cho khỏi chồng khít lên nhau (trước đó 6 cửa sổ đè 2 chỗ).
        for i, (_nhan, hwnd) in enumerate(self._o):
            cuaso.hien(hwnd)
            cuaso.khoi_phuc(hwnd)
            cuaso.dat_vi_tri(hwnd, 60 + i * 36, 40 + i * 32, 1000, 700)
        try:
            atexit.unregister(self._tha_het_an_toan)
        except Exception:  # noqa: BLE001
            pass
        self.destroy()
