"""Tab TƯƠNG TÁC — về acc cá nhân rồi vào Reel xem video + thả like theo số lượng/thời gian.

Nghiệp vụ ở mô-đun core/modun/tuong_tac (ADR-028) -> core/fbwatch + agent fbwatch_agent.js.
Chạy TỪNG acc tuần tự (mỗi acc 1 Firefox); hết 1 LƯỢT (tất cả acc) thì chờ ``delay`` phút rồi
chạy lượt tiếp. Đồng hồ CHECK mỗi 5 phút (không check dày làm lag), xử theo mẻ 10 acc.
"""

from __future__ import annotations

import json
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

from .dialogs import AccountPickerDialog

PAD = 8
DATA = os.path.join("data", "tuong_tac.json")
CHECK_MS = 5 * 60 * 1000     # 5 phút: nhịp kiểm tra tới lượt chưa (nhẹ máy)
BATCH = 10                   # mỗi nhịp xử tối đa 10 acc (không quét cả bảng liên tục)


class TuongTacTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._acc_ids: list[str] = []
        self._running = False
        self._stop = False
        self._in_round = False
        self._next_at: float | None = None      # thời điểm chạy lượt kế (epoch giây)
        self._acc_tt: dict[str, str] = {}
        self._acc_xem: dict[str, int] = {}
        self._acc_like: dict[str, int] = {}
        self._acc_tb: dict[str, int] = {}
        self._build()
        self._load_cfg()
        self._nap_mau_menu()
        self._show_accs()
        self.after(CHECK_MS, self._tick)

    # ------------------------------------------------------------------ mẫu tương tác
    def _nap_mau_menu(self) -> None:
        from core import tuong_tac_mau as ttm
        tens = [m["ten"] for m in ttm.nap()]
        self.mau_menu.configure(values=tens or ["(chưa có)"])
        if tens:
            self.mau_menu.set(tens[0])

    def _ap_dung_mau(self) -> None:
        """Điền cài đặt (video/like + giới hạn giây) từ mẫu đang chọn vào các ô."""
        from core import tuong_tac_mau as ttm
        m = ttm.tim(self.mau_menu.get())
        if not m:
            return
        giay = max(1, int(m.get("so_phut", 1))) * 60      # mẫu lưu phút -> đổi ra giây cho giới hạn
        for e, v in ((self.e_video, m["so_video"]), (self.e_like, m["so_like"]),
                     (self.e_gh_min, giay), (self.e_gh_max, giay)):
            e.delete(0, "end"); e.insert(0, str(v))
        self.set_status(f"Đã áp mẫu '{m['ten']}'.")

    def _luu_mau(self) -> None:
        """Lưu cài đặt hiện tại thành MỘT mẫu mới (giới hạn giây -> lưu ra phút cho mẫu dùng chung)."""
        from core import tuong_tac_mau as ttm
        from .dialogs import SimplePromptDialog
        phut = max(1, round(self._int(self.e_gh_max, 60) / 60))
        goi_y = f"{phut} phút · {self._int(self.e_like, 0)} like · {self._int(self.e_video, 1)} video"
        ten = SimplePromptDialog(self.app, "Lưu mẫu tương tác", "Tên mẫu:", goi_y).show()
        if not ten:
            return
        ten = ten.strip()
        ds = [m for m in ttm.nap() if m["ten"] != ten]
        ds.append({"ten": ten, "so_phut": phut,
                   "so_like": self._int(self.e_like, 0), "so_video": self._int(self.e_video, 1)})
        ttm.luu(ds)
        self._nap_mau_menu()
        self.mau_menu.set(ten)
        self.set_status(f"Đã lưu mẫu '{ten}'.")

    def _xoa_mau(self) -> None:
        from core import tuong_tac_mau as ttm
        ten = self.mau_menu.get()
        ds = [m for m in ttm.nap() if m["ten"] != ten]
        ttm.luu(ds)
        self._nap_mau_menu()
        self.set_status(f"Đã xoá mẫu '{ten}'.")

    # ------------------------------------------------------------------ dựng giao diện
    def _build(self) -> None:
        dam = ctk.CTkFont(weight="bold")
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=PAD, pady=(PAD, 2))
        ctk.CTkLabel(top, text="Số video muốn xem:", font=dam).pack(side="left")
        self.e_video = ctk.CTkEntry(top, width=60)
        self.e_video.insert(0, "10")
        self.e_video.pack(side="left", padx=(4, 14))
        ctk.CTkLabel(top, text="Số like:", font=dam).pack(side="left")
        self.e_like = ctk.CTkEntry(top, width=60)
        self.e_like.insert(0, "5")
        self.e_like.pack(side="left", padx=(4, 14))
        ctk.CTkLabel(top, text="Số thông báo đọc:", font=dam).pack(side="left")
        self.e_thongbao = ctk.CTkEntry(top, width=50)
        self.e_thongbao.insert(0, "0")
        self.e_thongbao.pack(side="left", padx=(4, 14))
        ctk.CTkLabel(top, text="Luồng:", font=dam).pack(side="left")
        self.e_luong = ctk.CTkEntry(top, width=50)
        self.e_luong.insert(0, "1")
        self.e_luong.pack(side="left", padx=(4, 14))
        ctk.CTkLabel(top, text="Delay 1 lượt (phút):", font=dam).pack(side="left")
        self.e_delay = ctk.CTkEntry(top, width=70)
        self.e_delay.insert(0, "600")
        self.e_delay.pack(side="left", padx=4)

        # Hàng GIỚI HẠN TƯƠNG TÁC 1 acc: NGẪU NHIÊN từ x đến y GIÂY (người dùng nhập). Hết giây đó thì dừng acc.
        hxem = ctk.CTkFrame(self, fg_color="transparent")
        hxem.pack(fill="x", padx=PAD, pady=(0, 2))
        ctk.CTkLabel(hxem, text="Giới hạn tương tác 1 acc: từ", font=dam).pack(side="left")
        self.e_gh_min = ctk.CTkEntry(hxem, width=60)
        self.e_gh_min.insert(0, "60")
        self.e_gh_min.pack(side="left", padx=4)
        ctk.CTkLabel(hxem, text="đến", font=dam).pack(side="left")
        self.e_gh_max = ctk.CTkEntry(hxem, width=60)
        self.e_gh_max.insert(0, "180")
        self.e_gh_max.pack(side="left", padx=4)
        ctk.CTkLabel(hxem, text="giây (ngẫu nhiên mỗi acc)", text_color="gray60").pack(side="left", padx=(2, 0))

        # Hàng MẪU: chọn mẫu đã lưu -> áp vào ô cài đặt; lưu/xoá mẫu (mẫu dùng chung cho các tab khác).
        hmau = ctk.CTkFrame(self, fg_color="transparent")
        hmau.pack(fill="x", padx=PAD, pady=(0, 2))
        ctk.CTkLabel(hmau, text="Mẫu tương tác:", font=dam).pack(side="left")
        self.mau_menu = ctk.CTkOptionMenu(hmau, width=210, values=["(chưa có)"])
        self.mau_menu.pack(side="left", padx=(4, 6))
        ctk.CTkButton(hmau, text="✓ Áp dụng", width=90, command=self._ap_dung_mau).pack(side="left", padx=2)
        ctk.CTkButton(hmau, text="💾 Lưu mẫu", width=100, fg_color="#2f7d4f",
                      command=self._luu_mau).pack(side="left", padx=2)
        ctk.CTkButton(hmau, text="🗑 Xoá mẫu", width=100, fg_color="gray40",
                      command=self._xoa_mau).pack(side="left", padx=2)

        thanh = ctk.CTkFrame(self, fg_color="transparent")
        thanh.pack(fill="x", padx=PAD, pady=(2, 4))
        ctk.CTkButton(thanh, text="👤 Chọn acc", width=110, command=self._pick_accounts).pack(side="left")
        ctk.CTkButton(thanh, text="🗑 Xoá acc đã chọn", width=140, fg_color="gray40",
                      command=self._remove_selected_accs).pack(side="left", padx=6)
        self.btn_start = ctk.CTkButton(thanh, text="▶ Bắt đầu", width=110, fg_color="#2f7d4f",
                                       command=self._start)
        self.btn_start.pack(side="left", padx=(16, 6))
        self.btn_stop = ctk.CTkButton(thanh, text="⏹ Dừng", width=90, fg_color="#a33",
                                      command=self._stop_run, state="disabled")
        self.btn_stop.pack(side="left")
        self.lbl_dem = ctk.CTkLabel(thanh, text="", text_color="gray60", font=dam)
        self.lbl_dem.pack(side="right", padx=8)

        than = ctk.CTkFrame(self, fg_color="transparent")
        than.pack(fill="both", expand=True, padx=PAD, pady=(2, PAD))
        # Bảng acc giống tab Tạo fanpage (Treeview, có cột Trạng thái rõ ràng).
        cols = (("id", "UID acc", 140, "w", 110),
                ("name", "Tên", 140, "w", 100),
                ("nhom", "Nhóm", 110, "w", 80),
                ("xem", "Đã xem", 70, "center", 60),
                ("like", "Đã like", 70, "center", 60),
                ("tb", "TB đọc", 70, "center", 60),
                ("tt", "Trạng thái", 160, "w", 110))
        left = ctk.CTkFrame(than, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True)
        self.acc_tree = ttk.Treeview(left, columns=[c[0] for c in cols], show="headings",
                                     selectmode="extended", style="Accounts.Treeview", height=12)
        for k, t, w, a, mw in cols:
            self.acc_tree.heading(k, text=t)
            self.acc_tree.column(k, width=w, minwidth=mw, anchor=a, stretch=True)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.acc_tree.yview)
        self.acc_tree.configure(yscrollcommand=sb.set)
        self.acc_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        right = ctk.CTkFrame(than, width=320)
        right.pack(side="left", fill="both", padx=(8, 0))
        ctk.CTkLabel(right, text="Nhật ký", font=dam).pack(anchor="w", padx=4, pady=(2, 0))
        self.log_box = ctk.CTkTextbox(right, width=320)
        self.log_box.pack(fill="both", expand=True, padx=4, pady=4)
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------ cấu hình
    def _load_cfg(self) -> None:
        try:
            with open(DATA, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            return
        for e, k, mac in ((self.e_video, "so_video", "10"),
                          (self.e_like, "so_like", "5"), (self.e_delay, "delay", "600"),
                          (self.e_thongbao, "so_thong_bao", "0"), (self.e_luong, "so_luong", "1"),
                          (self.e_gh_min, "gioi_han_min", "60"), (self.e_gh_max, "gioi_han_max", "180")):
            e.delete(0, "end")
            e.insert(0, str(d.get(k, mac)))
        self._acc_ids = [str(x) for x in (d.get("acc_ids") or [])]

    def _save_cfg(self) -> None:
        d = {"so_video": self._int(self.e_video, 10),
             "so_like": self._int(self.e_like, 5), "delay": self._int(self.e_delay, 600),
             "so_thong_bao": self._int(self.e_thongbao, 0), "so_luong": self._int(self.e_luong, 1),
             "gioi_han_min": self._int(self.e_gh_min, 60), "gioi_han_max": self._int(self.e_gh_max, 180),
             "acc_ids": self._acc_ids}
        try:
            os.makedirs(os.path.dirname(DATA), exist_ok=True)
            with open(DATA, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, indent=2)
        except OSError:
            pass

    @staticmethod
    def _int(entry, mac: int) -> int:
        try:
            return max(0, int(entry.get().strip() or mac))
        except ValueError:
            return mac

    # ------------------------------------------------------------------ acc
    def _pick_accounts(self) -> None:
        chon = AccountPickerDialog(self.app, self.app.store.accounts, self._acc_ids).show()
        if chon is None:
            return
        seen, sach = set(), []
        for a in chon:
            if a and a not in seen:
                seen.add(a); sach.append(a)
        self._acc_ids = sach
        self._show_accs()
        self._save_cfg()

    def _remove_selected_accs(self) -> None:
        chon = set(self.acc_tree.selection())
        if not chon:
            self.set_status("Chọn dòng trong bảng rồi bấm Xoá acc đã chọn.")
            return
        self._acc_ids = [a for a in self._acc_ids if a not in chon]
        self._show_accs()
        self._save_cfg()

    def _accounts(self) -> list:
        out = []
        for i in self._acc_ids:
            a = self.app.store.get(i)
            if a:
                out.append(a)
        return out

    def _show_accs(self) -> None:
        tree = self.acc_tree
        tree.delete(*tree.get_children())
        for ma in self._acc_ids:
            a = self.app.store.get(ma)
            con = a is not None
            hien = ma if con else f"{ma} (mất)"
            ten = (getattr(a, "fb_name", "") or getattr(a, "name", "") or "") if con else ""
            nhom = (getattr(a, "group", "") or "") if con else ""
            tt = self._acc_tt.get(ma, "chờ chạy" if con else "mất profile")
            tree.insert("", "end", iid=ma, values=(hien, ten, nhom,
                        self._acc_xem.get(ma, ""), self._acc_like.get(ma, ""),
                        self._acc_tb.get(ma, ""), tt))

    def _cap_nhat_dong(self, acc_id: str, info: dict) -> None:
        if "tt" in info:
            self._acc_tt[acc_id] = info["tt"]
        if info.get("xem") is not None:
            self._acc_xem[acc_id] = info["xem"]
        if info.get("like") is not None:
            self._acc_like[acc_id] = info["like"]
        if info.get("tb") is not None:
            self._acc_tb[acc_id] = info["tb"]
        if self.acc_tree.exists(acc_id):
            self.acc_tree.set(acc_id, "tt", self._acc_tt.get(acc_id, ""))
            self.acc_tree.set(acc_id, "xem", self._acc_xem.get(acc_id, ""))
            self.acc_tree.set(acc_id, "like", self._acc_like.get(acc_id, ""))
            self.acc_tree.set(acc_id, "tb", self._acc_tb.get(acc_id, ""))

    # ------------------------------------------------------------------ log / trạng thái
    def _log(self, chu: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", time.strftime("%H:%M:%S  ") + chu + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def set_status(self, chu: str) -> None:
        self.app.set_status(chu)

    # ------------------------------------------------------------------ chạy
    def _start(self) -> None:
        if self._running:
            return
        accs = self._accounts()
        if not accs:
            messagebox.showinfo("Tương tác", "Chọn ít nhất một acc.", parent=self.app)
            return
        self._save_cfg()
        self._running = True
        self._stop = False
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._log(f"=== BẮT ĐẦU tương tác {len(accs)} acc: {self._int(self.e_video, 10)} video, "
                  f"{self._int(self.e_like, 5)} like, giới hạn {self._int(self.e_gh_min, 60)}–"
                  f"{self._int(self.e_gh_max, 180)} giây/acc (ngẫu nhiên); "
                  f"hết lượt chờ {self._int(self.e_delay, 600)} phút ===")
        self._chay_luot()

    def _stop_run(self) -> None:
        self._stop = True
        self._running = False
        self._next_at = None
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.lbl_dem.configure(text="")
        self._log("Đã yêu cầu DỪNG — sẽ dừng sau acc hiện tại.")

    def _chay_luot(self) -> None:
        """Chạy MỘT lượt (tất cả acc, tuần tự) ở luồng nền; xong thì hẹn lượt kế theo delay."""
        if self._in_round or self._stop:
            return
        accs = self._accounts()
        if not accs:
            return
        self._in_round = True
        so_video = self._int(self.e_video, 10)
        so_like = self._int(self.e_like, 5)
        so_thong_bao = self._int(self.e_thongbao, 0)
        so_luong = max(1, self._int(self.e_luong, 1))
        gh_min = max(1, self._int(self.e_gh_min, 60))
        gh_max = max(gh_min, self._int(self.e_gh_max, 180))     # y >= x (giây)
        delay = self._int(self.e_delay, 600)

        def work():
            from core import modun as modun_module
            nc = modun_module.ngu_canh_tu(
                self.app, log=lambda m: self.app._post(lambda t=m: self._log(t)))
            try:
                kq = modun_module.chay(
                    "tuong_tac", nc, accs, so_video=so_video, so_like=so_like,
                    so_thong_bao=so_thong_bao, so_luong=so_luong,
                    gioi_han_min=gh_min, gioi_han_max=gh_max,
                    on_row=lambda aid, info: self.app._post(lambda a=aid, i=info: self._cap_nhat_dong(a, i)),
                    nen_dung=lambda: self._stop)
                self.app._post(lambda g=kq.ghi_chu: self._log("Lượt xong: " + g))
            except Exception as exc:  # noqa: BLE001
                self.app._post(lambda e=exc: self._log(f"Lỗi lượt: {e}"))
            finally:
                self.app._post(lambda: self._sau_luot(delay))

        threading.Thread(target=work, daemon=True, name="tuongtac").start()

    def _sau_luot(self, delay: int) -> None:
        self._in_round = False
        if self._stop or not self._running:
            self._running = False
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.lbl_dem.configure(text="")
            self._log("Đã dừng.")
            return
        self._next_at = time.time() + max(1, delay) * 60
        self._log(f"Chờ {delay} phút rồi chạy lượt tiếp.")
        self._cap_nhat_dem()

    def _cap_nhat_dem(self) -> None:
        if not (self._running and self._next_at):
            self.lbl_dem.configure(text="")
            return
        con = int(self._next_at - time.time())
        if con < 0:
            con = 0
        self.lbl_dem.configure(text=f"⏳ Lượt kế sau {con // 60}:{con % 60:02d}")

    def _tick(self) -> None:
        """Mỗi 5 phút: cập nhật đếm ngược + tới lượt thì chạy (xử theo mẻ 10 acc)."""
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            self._cap_nhat_dem()
            if (self._running and not self._in_round and self._next_at
                    and time.time() >= self._next_at):
                self._next_at = None
                self._chay_luot()
        finally:
            self.after(CHECK_MS, self._tick)
