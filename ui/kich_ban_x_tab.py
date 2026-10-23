"""Tab TƯƠNG TÁC > 𝕏 X.com = màn "KỊCH BẢN" (người dùng chốt 15/10).

Trái: danh sách MẪU kịch bản (mới / nhân bản / đổi tên / xoá). Giữa: CHUỖI NODE của mẫu đang mở
— Lướt newfeed · Follow kênh · Đăng lại trích dẫn · Nghỉ — bật/tắt, đổi thứ tự (▲▼), thu gọn,
thêm/xoá node; sửa là TỰ LƯU vào mẫu. Dưới: bảng acc (mỗi acc GÁN mẫu riêng; list kênh follow /
trích dẫn RIÊNG từng acc), luồng, lặp lại sau N phút, chạy thử, Chạy/Dừng, nhật ký.
Mỗi acc chạy cả chuỗi trong MỘT lần mở trình duyệt (mô-đun kich_ban_x -> core.xwatch.chay_kich_ban).
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

from core import kich_ban_x as kbx

from .dialogs import AccountPickerDialog

PAD = 8
SO_TRON = "①②③④⑤⑥⑦⑧⑨⑩"
TU_LUU_MS = 600
AUTO_DELAY_MS = 20000      # mở tool mà "Tự động chạy" bật -> chờ app/VPN ổn định rồi tự chạy
MAU_NODE = {kbx.NODE_LUOT: "#2f6fb0", kbx.NODE_FOLLOW: "#2f7d4f", kbx.NODE_QUOTE: "#8a5a1c",
            kbx.NODE_NGHI: "gray40"}


class ListKenhDialog(ctk.CTkToplevel):
    """Sửa list RIÊNG của acc: kênh FOLLOW · TỪ KHOÁ follow · kênh TRÍCH DẪN.
    show() -> (follow, tu_khoa, quote) | None.

    Một acc: ô trống = xoá list. Nhiều acc: ô trống = GIỮ NGUYÊN list của từng acc."""

    def __init__(self, parent, tieu_de: str, follow: str = "", quote: str = "", nhieu: bool = False,
                 tu_khoa: str = ""):
        super().__init__(parent)
        self.title(tieu_de)
        self.geometry("860x460")
        self._kq = None
        goi_y = ("Kênh: mỗi dòng 1 kênh (@ten, ten hoặc x.com/ten). Từ khoá: mỗi dòng (hoặc dấu phẩy) 1 từ khoá."
                 + (" Nhiều acc: ô để TRỐNG = giữ nguyên list cũ của từng acc." if nhieu
                    else " Ô trống = không có list."))
        ctk.CTkLabel(self, text=goi_y, justify="left", wraplength=830).pack(anchor="w", padx=10, pady=(10, 4))
        than = ctk.CTkFrame(self, fg_color="transparent")
        than.pack(fill="both", expand=True, padx=10)
        than.grid_columnconfigure((0, 1, 2), weight=1)
        than.grid_rowconfigure(1, weight=1)
        self.o_fl, self.o_tk, self.o_qt = (ctk.CTkTextbox(than) for _ in range(3))
        for c, (nhan, o, gt) in enumerate((("➕ Kênh cần FOLLOW (follow xong tự xoá)", self.o_fl, follow),
                                           ("🔎 Từ khoá FOLLOW (node Follow · Theo từ khoá)", self.o_tk, tu_khoa),
                                           ("🔁 Kênh để TRÍCH DẪN (trống = bỏ qua node)", self.o_qt, quote))):
            ctk.CTkLabel(than, text=nhan).grid(row=0, column=c, sticky="w", padx=4)
            o.grid(row=1, column=c, sticky="nsew", padx=4)
            if gt:
                o.insert("1.0", gt)
        h = ctk.CTkFrame(self, fg_color="transparent")
        h.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(h, text="💾 Lưu", width=100, fg_color="#2f7d4f", command=self._luu).pack(side="right")
        ctk.CTkButton(h, text="Huỷ", width=80, fg_color="gray40", command=self.destroy).pack(side="right", padx=6)
        self.transient(parent)
        self.after(50, self.grab_set)

    def _luu(self) -> None:
        self._kq = tuple(o.get("1.0", "end").strip() for o in (self.o_fl, self.o_tk, self.o_qt))
        self.destroy()

    def show(self):
        self.wait_window()
        return self._kq


class MauMoiDialog(ctk.CTkToplevel):
    """Tạo MẪU MỚI: đặt tên + chọn node. Thứ tự node = THỨ TỰ TÍCH (dòng xem trước hiện chuỗi).
    show() -> (tên, [loại node...]) | None."""

    MAC_DINH = (kbx.NODE_LUOT, kbx.NODE_FOLLOW, kbx.NODE_QUOTE)

    def __init__(self, parent, ten_da_co):
        super().__init__(parent)
        self.title("Mẫu kịch bản mới")
        self.geometry("460x360")
        self.resizable(False, False)
        self._da_co = {str(t).strip().lower() for t in ten_da_co}
        self._kq = None
        self._thu_tu: list = list(self.MAC_DINH)
        ctk.CTkLabel(self, text="Tên mẫu:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(14, 2))
        self.e_ten = ctk.CTkEntry(self, placeholder_text="vd: Nuôi acc sáng")
        self.e_ten.pack(fill="x", padx=14)
        ctk.CTkLabel(self, text="Chọn node (tích theo thứ tự muốn chạy):",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(12, 2))
        self._var: dict = {}
        for loai in kbx.LOAI_NODE:
            v = ctk.BooleanVar(value=loai in self._thu_tu)
            self._var[loai] = v
            ctk.CTkCheckBox(self, text=kbx.TEN_NODE[loai], variable=v,
                            command=lambda l=loai: self._tich(l)).pack(anchor="w", padx=24, pady=2)
        self.lbl_xem = ctk.CTkLabel(self, text="", text_color="gray60", wraplength=430, justify="left")
        self.lbl_xem.pack(anchor="w", padx=14, pady=(8, 0))
        self.lbl_loi = ctk.CTkLabel(self, text="", text_color="#e06666")
        self.lbl_loi.pack(anchor="w", padx=14)
        h = ctk.CTkFrame(self, fg_color="transparent")
        h.pack(fill="x", side="bottom", padx=14, pady=12)
        ctk.CTkButton(h, text="➕ Tạo mẫu", width=110, fg_color="#2f7d4f", command=self._tao).pack(side="right")
        ctk.CTkButton(h, text="Huỷ", width=80, fg_color="gray40", command=self.destroy).pack(side="right", padx=6)
        self.e_ten.bind("<Return>", lambda _e: self._tao())
        self._xem()
        self.transient(parent)
        self.after(50, self.grab_set)
        self.after(80, self.e_ten.focus_set)

    def _tich(self, loai: str) -> None:
        if self._var[loai].get():
            if loai not in self._thu_tu:
                self._thu_tu.append(loai)        # tich SAU -> chay SAU
        elif loai in self._thu_tu:
            self._thu_tu.remove(loai)
        self._xem()

    def _xem(self) -> None:
        if self._thu_tu:
            self.lbl_xem.configure(text="Chuỗi: " + "  →  ".join(
                f"{SO_TRON[i]} {kbx.TEN_NODE[l]}" for i, l in enumerate(self._thu_tu)))
        else:
            self.lbl_xem.configure(text="Chưa chọn node nào.")

    def _tao(self) -> None:
        ten = self.e_ten.get().strip()
        if not ten:
            self.lbl_loi.configure(text="Nhập tên mẫu.")
            return
        if ten.lower() in self._da_co:
            self.lbl_loi.configure(text=f"Đã có mẫu \"{ten}\".")
            return
        if not self._thu_tu:
            self.lbl_loi.configure(text="Chọn ít nhất một node.")
            return
        self._kq = (ten, list(self._thu_tu))
        self.destroy()

    def show(self):
        self.wait_window()
        return self._kq


class KichBanXTab(ctk.CTkFrame):
    def __init__(self, parent, app, acc_store=None, profiles=None, kho: "kbx.KhoKichBan | None" = None):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.acc_store = acc_store if acc_store is not None else getattr(app, "store", None)
        self.profiles = profiles if profiles is not None else getattr(app, "manager", None)
        self.kho = kho or kbx.KhoKichBan()
        self._o: list = []                  # moi node: {"loai", key: widget/var, "_canh": label}
        self._gon: set = set()              # chi so node dang THU GON
        self._hen_luu = None
        self._running = False
        self._stop = False
        self._hen = None
        self._next_at: float | None = None
        self._dong: dict = {}               # acc -> {mau, node, tong, tt}
        try:                                # nap registry o LUONG CHINH (nap trong luong nen -> race)
            from core.modun import tat_ca
            tat_ca.nap()
        except Exception:  # noqa: BLE001
            pass
        self._auto_hen = None
        self._build()
        self._ve_mau()
        self._ve_nodes()
        self._show_accs()
        # Mo tool ma "Tự động chạy" đang bật -> tự chạy kịch bản sau một lúc cho app/VPN ổn định.
        if self.kho.tu_dong:
            self._auto_hen = self.after(AUTO_DELAY_MS, self._auto_start)

    # ================================================================ bố cục
    def _build(self) -> None:
        dam = ctk.CTkFont(weight="bold")
        tren = ctk.CTkFrame(self, fg_color="transparent")
        tren.pack(fill="both", expand=True, padx=PAD, pady=(PAD, 2))

        # --- trái: mẫu kịch bản
        trai = ctk.CTkFrame(tren, width=220)
        trai.pack(side="left", fill="y")
        trai.pack_propagate(False)
        ctk.CTkLabel(trai, text="MẪU KỊCH BẢN", font=dam).pack(anchor="w", padx=8, pady=(8, 2))
        self.lb_mau = tk.Listbox(trai, exportselection=False, activestyle="none", height=10,
                                 font=("Segoe UI", 11), borderwidth=0, highlightthickness=0)
        self.lb_mau.pack(fill="both", expand=True, padx=8, pady=4)
        self.lb_mau.bind("<<ListboxSelect>>", lambda _e: self._chon_mau())
        self.lb_mau.bind("<Double-1>", lambda _e: self._doi_ten_mau())
        g = ctk.CTkFrame(trai, fg_color="transparent")
        g.pack(fill="x", padx=8, pady=(0, 8))
        g.grid_columnconfigure((0, 1), weight=1)
        for i, (t, f, mau) in enumerate((("➕ Mới", self._mau_moi, "#2f7d4f"),
                                          ("📄 Nhân bản", self._nhan_ban, None),
                                          ("✏️ Đổi tên", self._doi_ten_mau, "gray40"),
                                          ("🗑 Xoá", self._xoa_mau, "#a33"))):
            kw = {"fg_color": mau} if mau else {}
            ctk.CTkButton(g, text=t, height=28, command=f, **kw).grid(row=i // 2, column=i % 2, sticky="ew",
                                                                      padx=2, pady=2)
        self.lbl_luu = ctk.CTkLabel(trai, text="", text_color="gray60")
        self.lbl_luu.pack(anchor="w", padx=8, pady=(0, 6))

        # --- giữa: chuỗi node
        giua = ctk.CTkFrame(tren, fg_color="transparent")
        giua.pack(side="left", fill="both", expand=True, padx=(8, 0))
        h = ctk.CTkFrame(giua, fg_color="transparent")
        h.pack(fill="x")
        self.lbl_chuoi = ctk.CTkLabel(h, text="CHUỖI NODE", font=dam)
        self.lbl_chuoi.pack(side="left")
        self.them_menu = ctk.CTkOptionMenu(h, width=190, values=[kbx.TEN_NODE[k] for k in kbx.LOAI_NODE],
                                           command=self._them_node)
        self.them_menu.set("+ Thêm node")
        self.them_menu.pack(side="right")
        ctk.CTkLabel(h, text="chạy lần lượt từ trên xuống · sửa là tự lưu",
                     text_color="gray60").pack(side="right", padx=8)
        self.khung_node = ctk.CTkScrollableFrame(giua, height=300)
        self.khung_node.pack(fill="both", expand=True, pady=(4, 0))

        # --- thanh điều khiển
        thanh = ctk.CTkFrame(self, fg_color="transparent")
        thanh.pack(fill="x", padx=PAD, pady=(4, 2))
        ctk.CTkButton(thanh, text="👤 Chọn acc", width=100, command=self._pick_accounts).pack(side="left")
        ctk.CTkButton(thanh, text="🗑 Bỏ acc", width=80, fg_color="gray40",
                      command=self._bo_acc).pack(side="left", padx=4)
        ctk.CTkButton(thanh, text="🎯 Gán mẫu đang mở", width=150,
                      command=self._gan_mau).pack(side="left", padx=4)
        ctk.CTkButton(thanh, text="📝 List kênh riêng", width=130,
                      command=self._sua_list).pack(side="left", padx=4)
        ctk.CTkLabel(thanh, text="Luồng", font=dam).pack(side="left", padx=(12, 2))
        self.e_luong = ctk.CTkEntry(thanh, width=40)
        self.e_luong.insert(0, str(self.kho.luong))
        self.e_luong.pack(side="left")
        ctk.CTkLabel(thanh, text="Lặp lại sau", font=dam).pack(side="left", padx=(10, 2))
        self.e_lap = ctk.CTkEntry(thanh, width=55)
        self.e_lap.insert(0, str(self.kho.lap_phut))
        self.e_lap.pack(side="left")
        ctk.CTkLabel(thanh, text="phút", text_color="gray60").pack(side="left", padx=(2, 8))
        self.thu_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(thanh, text="Chạy thử", variable=self.thu_var, width=90).pack(side="left")
        self.btn_start = ctk.CTkButton(thanh, text="▶ Chạy", width=90, fg_color="#2f7d4f", command=self._start)
        self.btn_start.pack(side="left", padx=(10, 4))
        self.btn_stop = ctk.CTkButton(thanh, text="⏹ Dừng", width=80, fg_color="#a33",
                                      command=self._stop_run, state="disabled")
        self.btn_stop.pack(side="left")
        # Tu dong chay: bat -> chay ngay; tat tool mo lai -> tu chay theo kich ban da luu.
        self.auto_var = ctk.BooleanVar(value=bool(self.kho.tu_dong))
        ctk.CTkSwitch(thanh, text="🔄 Tự động chạy", variable=self.auto_var,
                      command=self._auto_toggled).pack(side="left", padx=(12, 0))
        self.lbl_dem = ctk.CTkLabel(thanh, text="", text_color="gray60", font=dam)
        self.lbl_dem.pack(side="right", padx=8)

        # --- dưới: bảng acc + nhật ký
        duoi = ctk.CTkFrame(self, fg_color="transparent")
        # Bang acc CAO CO DINH (~7 dong): vung node o tren duoc phan con lai (truoc day chia doi
        # -> node trich dan bi cat mat o list kenh chung).
        duoi.pack(fill="x", padx=PAD, pady=(2, PAD))
        cols = (("id", "UID acc", 130, "w", 100), ("mau", "Mẫu", 120, "w", 80),
                ("node", "Node đang chạy", 220, "w", 120), ("luot", "Lướt (xem·♥·💬·▶)", 140, "center", 110),
                ("follow", "Follow", 60, "center", 50), ("quote", "Trích dẫn", 70, "center", 60),
                ("fl", "Kênh follow còn", 100, "center", 80), ("tk", "Từ khoá", 60, "center", 50),
                ("tt", "Trạng thái", 180, "w", 100))
        left = ctk.CTkFrame(duoi, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True)
        self.acc_tree = ttk.Treeview(left, columns=[c[0] for c in cols], show="headings",
                                     selectmode="extended", style="Accounts.Treeview", height=7)
        for k, t, w, a, mw in cols:
            self.acc_tree.heading(k, text=t)
            self.acc_tree.column(k, width=w, minwidth=mw, anchor=a, stretch=True)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.acc_tree.yview)
        self.acc_tree.configure(yscrollcommand=sb.set)
        self.acc_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.acc_tree.bind("<Double-1>", lambda _e: self._sua_list())
        self.acc_tree.bind("<Button-3>", self._menu_acc)
        right = ctk.CTkFrame(duoi, width=320)
        right.pack(side="left", fill="both", padx=(8, 0))
        ctk.CTkLabel(right, text="Nhật ký", font=dam).pack(anchor="w", padx=4, pady=(2, 0))
        self.log_box = ctk.CTkTextbox(right, width=320, height=170)
        self.log_box.pack(fill="both", expand=True, padx=4, pady=4)
        self.log_box.configure(state="disabled")
        self._mau_listbox()

    def _mau_listbox(self) -> None:
        """tk.Listbox khong tu doi mau theo giao dien sang/toi cua CustomTkinter -> to tay."""
        toi = ctk.get_appearance_mode() == "Dark"
        try:
            self.lb_mau.configure(bg="#2b2b2b" if toi else "#ffffff", fg="#dce4ee" if toi else "#1a1a1a",
                                  selectbackground="#1f538d", selectforeground="#ffffff")
        except tk.TclError:
            pass

    # ================================================================ mẫu
    def _ve_mau(self) -> None:
        self._mau_listbox()
        self.lb_mau.delete(0, "end")
        for i, ten in enumerate(self.kho.mau):
            so = sum(1 for t in self.kho.acc_mau.values() if t == ten)
            self.lb_mau.insert("end", f"{'●' if ten == self.kho.mau_mo else '○'} {ten}"
                               + (f"  ({so} acc)" if so else ""))
            if ten == self.kho.mau_mo:
                self.lb_mau.selection_set(i)
        self.lbl_chuoi.configure(text=f"CHUỖI NODE — mẫu \"{self.kho.mau_mo}\"")

    def _ten_chon(self) -> str:
        sel = self.lb_mau.curselection()
        return list(self.kho.mau)[sel[0]] if sel else self.kho.mau_mo

    def _chon_mau(self) -> None:
        ten = self._ten_chon()
        if ten == self.kho.mau_mo:
            return
        self._luu_ngay()
        self.kho.mau_mo = ten
        self._gon.clear()
        self.kho.luu()
        self._ve_mau()
        self._ve_nodes()

    def _hoi_ten(self, tieu_de: str, mac: str = ""):
        d = ctk.CTkInputDialog(title=tieu_de, text="Tên mẫu:")
        try:
            if mac:
                d._entry.insert(0, mac)
        except Exception:  # noqa: BLE001
            pass
        ten = (d.get_input() or "").strip()
        if ten and ten in self.kho.mau:
            messagebox.showinfo(tieu_de, f"Đã có mẫu \"{ten}\".", parent=self.winfo_toplevel())
            return ""
        return ten

    def _mau_moi(self) -> None:
        kq = MauMoiDialog(self.winfo_toplevel(), list(self.kho.mau)).show()
        if not kq:
            return
        ten, loai_ds = kq
        self._luu_ngay()
        self.kho.mau[ten] = [kbx.node_moi(l) for l in loai_ds]
        self._gon.clear()
        self.kho.mau_mo = ten
        self.kho.luu()
        self._ve_mau()
        self._ve_nodes()

    def _nhan_ban(self) -> None:
        self._luu_ngay()
        cu = self.kho.mau_mo
        ten = self._hoi_ten("Nhân bản mẫu", f"{cu} (2)")
        if not ten:
            return
        self.kho.mau[ten] = kbx.chuan_mau(self.kho.mau.get(cu))
        self.kho.mau_mo = ten
        self.kho.luu()
        self._ve_mau()
        self._ve_nodes()

    def _doi_ten_mau(self) -> None:
        cu = self.kho.mau_mo
        ten = self._hoi_ten("Đổi tên mẫu", cu)
        if ten and self.kho.doi_ten_mau(cu, ten):
            self.kho.luu()
            self._ve_mau()
            self._show_accs()

    def _xoa_mau(self) -> None:
        ten = self.kho.mau_mo
        if len(self.kho.mau) <= 1:
            messagebox.showinfo("Xoá mẫu", "Phải còn ít nhất một mẫu.", parent=self.winfo_toplevel())
            return
        so = sum(1 for t in self.kho.acc_mau.values() if t == ten)
        if not messagebox.askyesno("Xoá mẫu", f"Xoá mẫu \"{ten}\"?"
                                   + (f"\n{so} acc đang gán mẫu này sẽ chuyển sang mẫu đang mở." if so else ""),
                                   parent=self.winfo_toplevel()):
            return
        self.kho.xoa_mau(ten)
        self.kho.luu()
        self._ve_mau()
        self._ve_nodes()
        self._show_accs()

    # ================================================================ node
    def _nodes(self) -> list:
        return self.kho.mau.setdefault(self.kho.mau_mo, kbx.mau_mac_dinh())

    def _ve_nodes(self) -> None:
        for w in self.khung_node.winfo_children():
            w.destroy()
        self._o = []
        nodes = self._nodes()
        if not nodes:
            ctk.CTkLabel(self.khung_node, text="Mẫu chưa có node nào — bấm \"+ Thêm node\".",
                         text_color="gray60").pack(pady=20)
        for i, n in enumerate(nodes):
            self._o.append(self._ve_mot(i, n, len(nodes)))

    def _o_so(self, cha, nhan: str, gia_tri, rong: int = 55) -> ctk.CTkEntry:
        ctk.CTkLabel(cha, text=nhan).pack(side="left", padx=(8, 2))
        e = ctk.CTkEntry(cha, width=rong)
        e.insert(0, str(gia_tri))
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda _e: self._doi())
        e.bind("<FocusOut>", lambda _e: self._doi())
        return e

    def _o_check(self, cha, nhan: str, gia_tri: bool):
        v = ctk.BooleanVar(value=bool(gia_tri))
        ctk.CTkCheckBox(cha, text=nhan, variable=v, command=self._doi).pack(side="left", padx=(8, 2))
        return v

    def _ve_mot(self, i: int, n: dict, tong: int) -> dict:
        loai = n["loai"]
        o: dict = {"loai": loai}
        the = ctk.CTkFrame(self.khung_node, border_width=2, border_color=MAU_NODE[loai])
        the.pack(fill="x", padx=2, pady=4)
        dau = ctk.CTkFrame(the, fg_color="transparent")
        dau.pack(fill="x", padx=6, pady=(6, 2))
        gon = i in self._gon
        ctk.CTkButton(dau, text="▸" if gon else "▾", width=26, height=24, fg_color="transparent",
                      text_color=("gray20", "gray80"), command=lambda: self._gap(i)).pack(side="left")
        o["bat"] = ctk.BooleanVar(value=bool(n.get("bat", True)))
        ctk.CTkCheckBox(dau, text=f"{SO_TRON[i] if i < len(SO_TRON) else i + 1}  {kbx.TEN_NODE[loai]}",
                        variable=o["bat"], command=self._doi, font=ctk.CTkFont(weight="bold")
                        ).pack(side="left", padx=4)
        for t, f, ok in (("✖", lambda: self._xoa_node(i), True), ("▼", lambda: self._doi_cho(i, 1), i < tong - 1),
                         ("▲", lambda: self._doi_cho(i, -1), i > 0)):
            ctk.CTkButton(dau, text=t, width=28, height=24, fg_color="gray35" if t != "✖" else "#a33",
                          state="normal" if ok else "disabled", command=f).pack(side="right", padx=2)
        o["_canh"] = ctk.CTkLabel(dau, text="", text_color="#d08a20")
        o["_canh"].pack(side="right", padx=8)
        if gon:
            ctk.CTkLabel(dau, text=self._tom_tat(n), text_color="gray60").pack(side="left", padx=8)
            o["_gon"] = dict(n)
            return o
        than = ctk.CTkFrame(the, fg_color="transparent")
        than.pack(fill="x", padx=6, pady=(0, 8))
        if loai == kbx.NODE_LUOT:
            r1 = ctk.CTkFrame(than, fg_color="transparent"); r1.pack(fill="x")
            o["gio_min"] = self._o_so(r1, "Thời gian lướt:", n["gio_min"])
            o["gio_max"] = self._o_so(r1, "–", n["gio_max"])
            ctk.CTkLabel(r1, text="giây", text_color="gray60").pack(side="left", padx=2)
            o["dung_min"] = self._o_so(r1, "Dừng mỗi bài:", n["dung_min"], 45)
            o["dung_max"] = self._o_so(r1, "–", n["dung_max"], 45)
            ctk.CTkLabel(r1, text="giây", text_color="gray60").pack(side="left", padx=2)
            r2 = ctk.CTkFrame(than, fg_color="transparent"); r2.pack(fill="x", pady=(4, 0))
            o["so_bai_tt"] = self._o_so(r2, "Số bài tương tác:", n["so_bai_tt"], 45)
            o["so_like"] = self._o_so(r2, "├ Like:", n["so_like"], 45)
            o["so_comment"] = self._o_so(r2, "├ Comment:", n["so_comment"], 45)
            o["so_video"] = self._o_so(r2, "├ Xem video:", n["so_video"], 45)
        elif loai == kbx.NODE_FOLLOW:
            r1 = ctk.CTkFrame(than, fg_color="transparent"); r1.pack(fill="x")
            o["toi_da"] = self._o_so(r1, "Tối đa mỗi lượt:", n["toi_da"], 45)
            ctk.CTkLabel(r1, text="kênh (cộng cả 3 nguồn bên dưới)", text_color="gray60").pack(side="left", padx=4)
            r2 = ctk.CTkFrame(than, fg_color="transparent"); r2.pack(fill="x", pady=(4, 0))
            o["theo_list"] = self._o_check(r2, "Theo list kênh RIÊNG của acc", n["theo_list"])
            ctk.CTkLabel(r2, text="(📝 List kênh riêng · follow xong / đã follow → tự xoá khỏi list)",
                         text_color="gray60").pack(side="left", padx=4)
            r3 = ctk.CTkFrame(than, fg_color="transparent"); r3.pack(fill="x", pady=(4, 0))
            o["theo_tu_khoa"] = self._o_check(r3, "Theo từ khoá RIÊNG của acc", n["theo_tu_khoa"])
            o["so_bai_tu_khoa"] = self._o_so(r3, "mỗi từ khoá mở", n["so_bai_tu_khoa"], 40)
            ctk.CTkLabel(r3, text="bài → follow tác giả (từ khoá đặt ở 📝 List kênh riêng)",
                         text_color="gray60").pack(side="left", padx=4)
            r4 = ctk.CTkFrame(than, fg_color="transparent"); r4.pack(fill="x", pady=(4, 0))
            o["goi_y"] = self._o_check(r4, "Trang gợi ý của X (Who to follow)", n["goi_y"])
        elif loai == kbx.NODE_QUOTE:
            r1 = ctk.CTkFrame(than, fg_color="transparent"); r1.pack(fill="x")
            ctk.CTkLabel(r1, text="Nguồn:").pack(side="left", padx=(8, 2))
            o["nguon"] = ctk.CTkSegmentedButton(r1, values=["📺 List kênh", "🎲 Newfeed"],
                                                command=lambda _v: self._doi())
            o["nguon"].set("🎲 Newfeed" if n.get("nguon") == "newfeed" else "📺 List kênh")
            o["nguon"].pack(side="left", padx=4)
            o["so_bai"] = self._o_so(r1, "Số bài:", n["so_bai"], 45)
            o["cach_min"] = self._o_so(r1, "Nghỉ giữa 2 bài:", n["cach_min"], 45)
            o["cach_max"] = self._o_so(r1, "–", n["cach_max"], 45)
            ctk.CTkLabel(r1, text="giây", text_color="gray60").pack(side="left", padx=2)
            r2 = ctk.CTkFrame(than, fg_color="transparent"); r2.pack(fill="x", pady=(4, 0))
            o["khong_trung"] = self._o_check(r2, "Không cho 2 acc trích dẫn cùng 1 bài", n["khong_trung"])
            ctk.CTkLabel(r2, text="· nội dung = comment đầu (không có thì caption) + 3-5 icon · không bao giờ "
                                  "trích dẫn lại bài cũ", text_color="gray60").pack(side="left", padx=4)
            r3 = ctk.CTkFrame(than, fg_color="transparent"); r3.pack(fill="x", pady=(4, 0))
            ctk.CTkLabel(r3, text="Nguồn \"List kênh\" = list kênh trích dẫn RIÊNG của từng acc (📝 List kênh "
                                  "riêng) · acc chưa có list thì bỏ qua node này",
                         text_color="gray60").pack(side="left", padx=8)
        else:
            r1 = ctk.CTkFrame(than, fg_color="transparent"); r1.pack(fill="x")
            o["giay_min"] = self._o_so(r1, "Nghỉ từ", n["giay_min"])
            o["giay_max"] = self._o_so(r1, "đến", n["giay_max"])
            ctk.CTkLabel(r1, text="giây rồi sang node kế", text_color="gray60").pack(side="left", padx=4)
        return o

    @staticmethod
    def _tom_tat(n: dict) -> str:
        l = n["loai"]
        if l == kbx.NODE_LUOT:
            return (f"{n['gio_min']}–{n['gio_max']}s · ♥ {n['so_like']} · 💬 {n['so_comment']} · "
                    f"▶ {n['so_video']}")
        if l == kbx.NODE_FOLLOW:
            ng = [t for k, t in (("theo_list", "list"), ("theo_tu_khoa", "từ khoá"), ("goi_y", "gợi ý")) if n.get(k)]
            return f"tối đa {n['toi_da']} kênh · {', '.join(ng) or 'chưa chọn nguồn'}"
        if l == kbx.NODE_QUOTE:
            return f"{n['so_bai']} bài · {'newfeed' if n['nguon'] == 'newfeed' else 'list kênh'}"
        return f"nghỉ {n['giay_min']}–{n['giay_max']}s"

    def _doc_nodes(self) -> tuple:
        """Đọc lại mọi ô -> (nodes sạch, {i: cảnh báo})."""
        ra, canh = [], {}
        for i, o in enumerate(self._o):
            if "_gon" in o:
                n = dict(o["_gon"])
                n["bat"] = bool(o["bat"].get())
            else:
                n = {"loai": o["loai"], "bat": bool(o["bat"].get())}
                for k, w in o.items():
                    if k in ("loai", "bat") or k.startswith("_"):
                        continue
                    if isinstance(w, ctk.BooleanVar):
                        n[k] = bool(w.get())
                    elif isinstance(w, ctk.CTkTextbox):
                        n[k] = w.get("1.0", "end").strip()
                    elif isinstance(w, ctk.CTkSegmentedButton):
                        n[k] = "newfeed" if "Newfeed" in w.get() else "kenh"
                    else:
                        n[k] = w.get()
            sach, c = kbx.chuan_node(n)
            ra.append(sach)
            if c:
                canh[i] = c
        return ra, canh

    def _doi(self) -> None:
        """Có ô vừa đổi -> báo cảnh báo ngay, hẹn TỰ LƯU."""
        _n, canh = self._doc_nodes()
        for i, o in enumerate(self._o):
            o["_canh"].configure(text=("⚠ " + "; ".join(canh[i])) if i in canh else "")
        self.lbl_luu.configure(text="● chưa lưu…")
        if self._hen_luu is not None:
            try:
                self.after_cancel(self._hen_luu)
            except Exception:  # noqa: BLE001
                pass
        self._hen_luu = self.after(TU_LUU_MS, self._luu_ngay)

    def _luu_ngay(self) -> None:
        self._hen_luu = None
        if not self._o and not self._nodes():
            return
        nodes, _c = self._doc_nodes()
        self.kho.mau[self.kho.mau_mo] = nodes
        self.kho.luu()
        self.lbl_luu.configure(text=f"✓ đã lưu {time.strftime('%H:%M:%S')}")

    def _sua_cau_truc(self, f) -> None:
        self._luu_ngay()
        f(self._nodes())
        self.kho.luu()
        self._ve_nodes()

    def _them_node(self, ten: str) -> None:
        self.them_menu.set("+ Thêm node")
        loai = next((k for k, v in kbx.TEN_NODE.items() if v == ten), None)
        if loai:
            self._sua_cau_truc(lambda ns: ns.append(kbx.node_moi(loai)))

    def _xoa_node(self, i: int) -> None:
        if not messagebox.askyesno("Xoá node", f"Xoá node {i + 1} ({kbx.TEN_NODE[self._nodes()[i]['loai']]})?",
                                   parent=self.winfo_toplevel()):
            return
        self._gon = {g - (g > i) for g in self._gon if g != i}
        self._sua_cau_truc(lambda ns: ns.pop(i))

    def _doi_cho(self, i: int, buoc: int) -> None:
        j = i + buoc

        def f(ns):
            if 0 <= j < len(ns):
                ns[i], ns[j] = ns[j], ns[i]
        self._gon = {(j if g == i else i if g == j else g) for g in self._gon}
        self._sua_cau_truc(f)

    def _gap(self, i: int) -> None:
        self._luu_ngay()
        self._gon ^= {i}
        self._ve_nodes()

    # ================================================================ acc
    def _pick_accounts(self) -> None:
        chon = AccountPickerDialog(self.app, self.acc_store.accounts, self.kho.accs).show()
        if chon is None:
            return
        self.kho.accs = list(dict.fromkeys(a for a in chon if a))
        self.kho.luu()
        self._show_accs()

    def _chon_acc(self) -> list:
        return list(self.acc_tree.selection())

    def _bo_acc(self) -> None:
        ids = set(self._chon_acc())
        if not ids:
            self.app.set_status("Chọn acc trong bảng rồi bấm Bỏ acc.")
            return
        self.kho.accs = [a for a in self.kho.accs if a not in ids]
        self.kho.luu()
        self._show_accs()

    def _gan_mau(self) -> None:
        ids = self._chon_acc()
        if not ids:
            self.app.set_status("Chọn acc trong bảng rồi bấm 🎯 Gán mẫu đang mở.")
            return
        for a in ids:
            self.kho.acc_mau[a] = self.kho.mau_mo
        self.kho.luu()
        self._ve_mau()
        self._show_accs()
        self._log(f"Gán mẫu \"{self.kho.mau_mo}\" cho {len(ids)} acc.")

    def _sua_list(self) -> None:
        ids = self._chon_acc()
        if not ids:
            self.app.set_status("Chọn acc trong bảng (hoặc bấm đúp một dòng) để sửa list kênh riêng.")
            return
        nhieu = len(ids) > 1
        tieu_de = f"List kênh riêng — {ids[0]}" if not nhieu else f"List kênh riêng — {len(ids)} acc"
        kq = ListKenhDialog(self.winfo_toplevel(), tieu_de,
                            "" if nhieu else self.kho.acc_follow.get(ids[0], ""),
                            "" if nhieu else self.kho.acc_quote.get(ids[0], ""), nhieu=nhieu,
                            tu_khoa="" if nhieu else self.kho.acc_tu_khoa.get(ids[0], "")).show()
        if kq is None:
            return
        fl, tk, qt = kq
        for a in ids:
            for kho_list, gt in ((self.kho.acc_follow, fl), (self.kho.acc_tu_khoa, tk),
                                 (self.kho.acc_quote, qt)):
                if gt:
                    kho_list[a] = gt
                elif not nhieu:
                    kho_list.pop(a, None)
        self.kho.luu()
        self._show_accs()

    def _menu_acc(self, ev) -> None:
        """Chuột phải bảng acc: Mở profile · Copy ID acc · List kênh riêng (+ gán mẫu / bỏ acc)."""
        iid = self.acc_tree.identify_row(ev.y)
        if iid and iid not in self.acc_tree.selection():
            self.acc_tree.selection_set(iid)          # chuột phải dòng CHƯA chọn -> chọn dòng đó
        ids = self._chon_acc()
        if not ids:
            return
        so = f" ({len(ids)} acc)" if len(ids) > 1 else ""
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="▶ Mở profile" + so, command=self._mo_profile)
        m.add_command(label="📋 Copy ID acc" + so, command=self._copy_id)
        m.add_command(label="📝 List kênh riêng" + so, command=self._sua_list)
        m.add_separator()
        m.add_command(label=f"🎯 Gán mẫu \"{self.kho.mau_mo}\"" + so, command=self._gan_mau)
        m.add_command(label="🗑 Bỏ khỏi bảng" + so, command=self._bo_acc)
        try:
            m.tk_popup(ev.x_root, ev.y_root)
        finally:
            m.grab_release()

    def _copy_id(self) -> None:
        ids = self._chon_acc()
        if not ids:
            return
        self.clipboard_clear()
        self.clipboard_append(chr(10).join(ids))
        self.app.set_status(f"Đã copy {len(ids)} ID acc.")

    def _mo_profile(self) -> None:
        """Mở profile X cho người dùng thao tác TAY (mo_tay: không agent nào chạy) — luồng nền."""
        accs = [a for a in (self.acc_store.get(i) for i in self._chon_acc()) if a]
        if not accs or self.profiles is None:
            return
        try:
            from core import an_cua_so
            for a in accs:
                an_cua_so.bo_danh_dau(self.profiles, a)   # mở tay -> không bị "Ẩn trình duyệt"
        except Exception:  # noqa: BLE001
            pass

        def work():
            for a in accs:
                try:
                    mo = getattr(self.profiles, "mo_tay", None)
                    (mo or self.profiles.launch)(a, url="https://x.com/home")
                    self.app._post(lambda i=a.id: self.app.set_status(f"Đã mở profile {i}."))
                except Exception as exc:  # noqa: BLE001
                    self.app._post(lambda i=a.id, e=exc: self._log(f"[{i}] mở profile lỗi: {e}"))

        threading.Thread(target=work, daemon=True, name="mo_profile_x").start()

    def _accounts(self) -> list:
        return [a for a in (self.acc_store.get(i) for i in self.kho.accs) if a]

    def _show_accs(self) -> None:
        from core import xwatch
        tree = self.acc_tree
        chon = set(tree.selection())
        tree.delete(*tree.get_children())
        for ma in self.kho.accs:
            con = self.acc_store.get(ma) is not None
            d = self._dong.get(ma, {})
            t = d.get("tong") or {}
            ten_mau, _n = self.kho.mau_cua_acc(ma)
            gan = ma in self.kho.acc_mau and self.kho.acc_mau[ma] in self.kho.mau
            fl = len(xwatch.tach_kenh(self.kho.acc_follow.get(ma, "")))
            tk = len(kbx.tach_tu_khoa(self.kho.acc_tu_khoa.get(ma, "")))
            tree.insert("", "end", iid=ma, values=(
                ma if con else f"{ma} (mất)", ten_mau + ("" if gan else " (đang mở)"), d.get("node", ""),
                f"{t.get('xem', 0)}·{t.get('like', 0)}·{t.get('cmt', 0)}·{t.get('video', 0)}" if t else "",
                t.get("follow", "") if t else "", t.get("quote", "") if t else "", fl or "—", tk or "—",
                d.get("tt", "chờ chạy" if con else "mất acc")))
        for a in chon:
            if tree.exists(a):
                tree.selection_add(a)

    def _cap_nhat_dong(self, acc_id: str, info: dict) -> None:
        d = self._dong.setdefault(acc_id, {})
        d.update({k: v for k, v in info.items() if k in ("node", "tt", "tong", "mau")})
        if not self.acc_tree.exists(acc_id):
            return
        self.acc_tree.set(acc_id, "node", d.get("node", ""))
        self.acc_tree.set(acc_id, "tt", d.get("tt", ""))
        t = d.get("tong")
        if t:
            self.acc_tree.set(acc_id, "luot", f"{t.get('xem', 0)}·{t.get('like', 0)}·{t.get('cmt', 0)}·"
                                              f"{t.get('video', 0)}")
            self.acc_tree.set(acc_id, "follow", t.get("follow", 0))
            self.acc_tree.set(acc_id, "quote", t.get("quote", 0))

    # ================================================================ chạy
    def _log(self, chu: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", time.strftime("%H:%M:%S  ") + chu + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    @staticmethod
    def _int(entry, mac: int, lo: int = 0) -> int:
        try:
            return max(lo, int(entry.get().strip() or mac))
        except ValueError:
            return mac

    def _auto_toggled(self) -> None:
        """Gạt công tắc "Tự động chạy": lưu ngay; bật -> chạy luôn, tắt -> huỷ hẹn + dừng."""
        self.kho.tu_dong = bool(self.auto_var.get())
        self.kho.luu()
        if self._auto_hen is not None:
            try:
                self.after_cancel(self._auto_hen)
            except Exception:  # noqa: BLE001
                pass
            self._auto_hen = None
        if self.kho.tu_dong:
            if not self._running:
                self._start()
        else:
            self._log("Đã tắt tự động chạy.")
            if self._running:
                self._stop_run()

    def _auto_start(self) -> None:
        """Tới giờ tự chạy (mở tool mà tự động đang bật)."""
        self._auto_hen = None
        if self.kho.tu_dong and not self._running and self._accounts():
            self._log("🔄 Tự động chạy kịch bản (đã bật từ trước).")
            self._start(tu_dong=True)

    def _start(self, tu_dong: bool = False) -> None:
        if self._running:
            return
        self._luu_ngay()
        if not self._accounts():
            if not tu_dong:            # tự động mà chưa có acc -> im lặng, không bung hộp thoại
                messagebox.showinfo("Kịch bản X", "Chọn ít nhất một acc X.", parent=self.winfo_toplevel())
            return
        self.kho.luong = self._int(self.e_luong, 1, 1)
        self.kho.lap_phut = self._int(self.e_lap, 0)
        self.kho.luu()
        self._running = True
        self._stop = False
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._chay_vong()

    def _chay_vong(self) -> None:
        """Một vòng (mọi acc) ở luồng nền. Giá trị ô chốt ở LUỒNG CHÍNH."""
        accs = self._accounts()
        if not accs:
            self._xong()
            return
        so_luong = self.kho.luong
        lap = self.kho.lap_phut
        thu = bool(self.thu_var.get())
        for a in accs:
            self._dong[a.id] = {"tt": "chờ", "node": ""}
        self._show_accs()
        self._log(f"=== CHẠY KỊCH BẢN {len(accs)} acc, {so_luong} luồng"
                  + (" — CHẠY THỬ (không bấm Đăng, không xoá list follow)" if thu else "") + " ===")

        def work():
            from core import an_cua_so as _an
            from core import modun as modun_module
            post = lambda f: self.app._post(f)  # noqa: E731
            nc = modun_module.NguCanh(manager=self.profiles, store=self.acc_store,
                                      settings=getattr(self.app, "settings", None),
                                      log=lambda m: post(lambda t=m: self._log(t)),
                                      post=post, so_luong=so_luong)
            for _a in accs:                     # cong tac "An trinh duyet" cua tab Tuong tac
                _an.danh_dau(_an.NHOM_TUONG_TAC, self.profiles, _a)
            try:
                kq = modun_module.chay(
                    "kich_ban_x", nc, accs, kho=self.kho, so_luong=so_luong, thu=thu,
                    on_row=lambda aid, info: post(lambda a=aid, i=info: self._cap_nhat_dong(a, i)),
                    nen_dung=lambda: self._stop)
                post(lambda g=kq.ghi_chu: self._log("Xong: " + g))
            except Exception as exc:  # noqa: BLE001
                post(lambda e=exc: self._log(f"Lỗi: {e}"))
            finally:
                post(lambda: self._sau_vong(lap))

        threading.Thread(target=work, daemon=True, name="kich_ban_x").start()

    def _sau_vong(self, lap: int) -> None:
        self._show_accs()
        if self._stop or lap <= 0:
            self._xong()
            return
        self._next_at = time.time() + lap * 60
        self._log(f"Chờ {lap} phút rồi chạy vòng tiếp.")
        self._hen = self.after(lap * 60 * 1000, self._chay_vong)
        self._dem()

    def _dem(self) -> None:
        if not (self._running and self._next_at):
            self.lbl_dem.configure(text="")
            return
        con = max(0, int(self._next_at - time.time()))
        self.lbl_dem.configure(text=f"⏳ Vòng kế sau {con // 60}:{con % 60:02d}")
        self.after(1000, self._dem)

    def _stop_run(self) -> None:
        self._stop = True
        if self._hen is not None:
            try:
                self.after_cancel(self._hen)
            except Exception:  # noqa: BLE001
                pass
            self._hen = None
            self._log("Đã huỷ vòng kế.")
            self._xong()
            return
        self._log("Đã yêu cầu DỪNG — dừng sau bước đang làm.")

    def _xong(self) -> None:
        self._running = False
        self._next_at = None
        self._hen = None
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.lbl_dem.configure(text="")
