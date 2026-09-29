"""Tab "✏️ Đổi tên file": biến đổi tiêu đề (tên file) hàng loạt trong một thư mục.

Chọn thư mục -> dựng CHUỖI BƯỚC (xoá cụm, xoá hashtag, thêm đầu/cuối, đánh số, xoá cụm cùng kiểu
khác số liệu theo ví dụ; gõ là bảng xem trước tự cập nhật) -> ▶ Chạy đổi tên (tự gom bước đang gõ)
-> Hoàn tác được. Mọi nghiệp vụ nằm ở
core/rename_title; tab này chỉ dịch giao diện <-> core (ADR-017).
"""

from __future__ import annotations

import json
import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from core import rename_title as rt
from core import modun as modun_module
from core.modun import tat_ca as _modun_tat_ca
_modun_tat_ca.nap()

PAD = 10
TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VI_TRI_DAU, VI_TRI_CUOI = "Đầu tên", "Cuối tên"
#: Nhãn trạng thái dòng xem trước.
TT_NHAN = {"ok": "✔ sẽ đổi", "khong_doi": "— không đổi", "trung": "⚠ trùng tên (bỏ qua)",
           "loi": "✖ tên không hợp lệ (bỏ qua)"}
#: Gợi ý ô giá trị theo loại bước.
GOI_Y = {
    "xoa_cum": "Cụm từ cần xoá (không phân biệt hoa thường)",
    "xoa_hashtag": "(không cần giá trị — xoá mọi #hashtag)",
    "them_dau": "Chuỗi thêm vào ĐẦU tên",
    "them_cuoi": "Chuỗi thêm vào CUỐI tên",
    "danh_so": "Định dạng số: {n} · {n:02d} · Tập {n}",
    "xoa_mau": "VÍ DỤ một cụm, vd: 833K views 22K reactions (số khác vẫn xoá)",
}


class RenameTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._buoc: list = []
        self._ke_hoach: list = []
        self._build()
        self._restore_cfg()

    # ------------------------------------------------------------------ dựng
    @staticmethod
    def _cfg_path() -> str:
        return os.path.join(TOOL_DIR, "data", "rename.json")

    def _build(self) -> None:
        dam = ctk.CTkFont(weight="bold")
        # Hàng 1: thư mục + đuôi + cùng gốc
        r1 = ctk.CTkFrame(self)
        r1.pack(fill="x", padx=PAD, pady=(PAD, 4))
        ctk.CTkLabel(r1, text="Thư mục", font=dam, width=80, anchor="w").pack(side="left", padx=(10, 6), pady=8)
        self.folder_entry = ctk.CTkEntry(r1, placeholder_text="Thư mục chứa các file cần đổi tiêu đề")
        self.folder_entry.pack(side="left", fill="x", expand=True, pady=8)
        ctk.CTkButton(r1, text="Chọn...", width=80, command=self._pick_folder).pack(side="left", padx=6, pady=8)
        ctk.CTkButton(r1, text="Mở", width=50, fg_color="gray45", command=self._open_folder).pack(side="left", pady=8)
        ctk.CTkLabel(r1, text="Đuôi", font=dam).pack(side="left", padx=(14, 4))
        self.duoi_entry = ctk.CTkEntry(r1, width=120, placeholder_text="mp4,txt (trống=tất cả)")
        self.duoi_entry.pack(side="left", pady=8)
        self.cung_goc_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(r1, text="Đổi cả file cùng tên khác đuôi (.mp4 + .txt)",
                        variable=self.cung_goc_var).pack(side="left", padx=(12, 10), pady=8)

        # Hàng 2: thêm bước
        r2 = ctk.CTkFrame(self)
        r2.pack(fill="x", padx=PAD, pady=4)
        ctk.CTkLabel(r2, text="Bước", font=dam, width=80, anchor="w").pack(side="left", padx=(10, 6), pady=8)
        self.loai_menu = ctk.CTkOptionMenu(r2, width=300, values=[nhan for _, nhan, _ in rt.LOAI],
                                           command=lambda _v: self._loai_doi())
        self.loai_menu.set(rt.LOAI[0][1])
        self.loai_menu.pack(side="left", pady=8)
        self.gia_tri_entry = ctk.CTkEntry(r2, placeholder_text=GOI_Y["xoa_cum"])
        self.gia_tri_entry.pack(side="left", fill="x", expand=True, padx=6, pady=8)
        # Enter = xếp bước này vào chuỗi (khi muốn nhiều bước); gõ = bảng xem trước tự cập nhật.
        self.gia_tri_entry.bind("<Return>", lambda _e: self._them_buoc())
        self.gia_tri_entry.bind("<KeyRelease>", lambda _e: self._hen_xem_truoc())
        self.vi_tri_menu = ctk.CTkOptionMenu(r2, width=110, values=[VI_TRI_CUOI, VI_TRI_DAU],
                                             command=lambda _v: self._hen_xem_truoc())
        self.vi_tri_menu.set(VI_TRI_CUOI)
        self._hen_id = None
        # Huy hen xem truoc khi tab bi huy (thuoc destroy root -> after mo coi in "invalid command name").
        self.bind("<Destroy>", lambda _e: self._huy_hen(), add="+")

        # Hàng 3: trái = chuỗi bước, phải = xem trước
        giua = ctk.CTkFrame(self, fg_color="transparent")
        giua.pack(fill="both", expand=True, padx=PAD, pady=4)
        giua.grid_columnconfigure(0, weight=2, uniform="rn")
        giua.grid_columnconfigure(1, weight=5, uniform="rn")
        giua.grid_rowconfigure(0, weight=1)
        trai = ctk.CTkFrame(giua)
        trai.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
        th = ctk.CTkFrame(trai, fg_color="transparent")
        th.pack(fill="x", padx=8, pady=(8, 0))
        ctk.CTkLabel(th, text="Chuỗi bước (chạy từ trên xuống)", font=dam).pack(side="left")
        self.steps_box = tk.Listbox(trai, activestyle="none", exportselection=False, highlightthickness=0)
        self.steps_box.pack(fill="both", expand=True, padx=8, pady=(4, 4))
        self.goi_y = ctk.CTkLabel(trai, text="Chưa có bước nào. Ở hàng “Bước”: chọn kiểu → nhập giá trị → "
                                              "bấm ▶ Chạy đổi tên là chạy luôn. Muốn nhiều bước: gõ xong nhấn Enter "
                                              "để xếp vào chuỗi rồi nhập bước kế.",
                                  text_color="#ffd28a", wraplength=300, justify="left")
        self.goi_y.pack(fill="x", padx=8, pady=(0, 4))
        tb = ctk.CTkFrame(trai, fg_color="transparent")
        tb.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkButton(tb, text="▲", width=40, command=lambda: self._doi_cho(-1)).pack(side="left")
        ctk.CTkButton(tb, text="▼", width=40, command=lambda: self._doi_cho(1)).pack(side="left", padx=4)
        ctk.CTkButton(tb, text="Xoá bước", width=90, fg_color="#a33", command=self._xoa_buoc).pack(side="left")
        ctk.CTkButton(tb, text="Xoá hết", width=80, fg_color="gray45", command=self._xoa_het).pack(side="right")

        phai = ctk.CTkFrame(giua)
        phai.grid(row=0, column=1, sticky="nsew", padx=(3, 0))
        ph = ctk.CTkFrame(phai, fg_color="transparent")
        ph.pack(fill="x", padx=8, pady=(8, 0))
        ctk.CTkLabel(ph, text="Xem trước (tự cập nhật khi gõ)", font=dam).pack(side="left")
        self.tom_tat = ctk.CTkLabel(ph, text="", text_color="gray60")
        self.tom_tat.pack(side="left", padx=12)
        box = ctk.CTkFrame(phai)
        box.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        cols = (("cu", "Tên cũ", 300, "w"), ("moi", "Tên mới", 300, "w"), ("tt", "Trạng thái", 150, "w"))
        self.tree = ttk.Treeview(box, columns=[c[0] for c in cols], show="headings",
                                 style="Accounts.Treeview")
        for k, t, w, a in cols:
            self.tree.heading(k, text=t)
            self.tree.column(k, width=w, anchor=a, stretch=(k != "tt"))
        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Hàng 4: nút chạy
        r4 = ctk.CTkFrame(self)
        r4.pack(fill="x", padx=PAD, pady=(4, PAD))
        self.doi_btn = ctk.CTkButton(r4, text="▶ Chạy đổi tên", width=140, fg_color="#2f7d4f", command=self._doi_ten)
        self.doi_btn.pack(side="left", padx=(10, 0), pady=8)
        ctk.CTkButton(r4, text="↩ Hoàn tác lần đổi gần nhất", width=200, fg_color="gray45",
                      command=self._hoan_tac).pack(side="left", padx=6, pady=8)
        self.status = ctk.CTkLabel(r4, text="", anchor="w", text_color="gray60")
        self.status.pack(side="left", fill="x", expand=True, padx=8)
        self._loai_doi()

    # ------------------------------------------------------------------ bước
    def _ma_loai(self) -> str:
        return rt.MA_THEO_NHAN.get(self.loai_menu.get(), "xoa_cum")

    def _loai_doi(self) -> None:
        ma = self._ma_loai()
        self.gia_tri_entry.configure(placeholder_text=GOI_Y.get(ma, ""))
        if ma == "danh_so":
            self.vi_tri_menu.pack(side="left", padx=(0, 6), pady=8)
        else:
            self.vi_tri_menu.pack_forget()
        self._hen_xem_truoc()

    def _buoc_dang_go(self, ep: bool = False):
        """Bước đang gõ ở hàng "Bước" (chưa xếp vào chuỗi) -> rt.Buoc, hoặc None.

        Có bước khi ô giá trị có chữ. Kiểu không cần giá trị (xoá hashtag / đánh số mặc định {n}):
        Enter (ep=True) luôn xếp được; còn xem trước / bấm Chạy chỉ tự tính khi chuỗi còn trống
        (chọn kiểu rồi bấm Chạy là chạy luôn; chuỗi đã có bước thì không tự thêm chỉ vì đổi menu).
        """
        ma = self._ma_loai()
        gia_tri = self.gia_tri_entry.get().strip()
        can = next((c for m, _, c in rt.LOAI if m == ma), True)
        khong_can = (ma == "danh_so") or not can
        if not gia_tri and not (khong_can and (ep or not self._buoc)):
            return None
        if ma == "danh_so":
            gia_tri = gia_tri or "{n}"
        vi_tri = "dau" if self.vi_tri_menu.get() == VI_TRI_DAU else "cuoi"
        return rt.Buoc(ma, gia_tri, vi_tri)

    def _them_buoc(self, xem: bool = True) -> bool:
        """Xếp bước đang gõ ở hàng "Bước" vào chuỗi (Enter). Trả True nếu thêm được."""
        b = self._buoc_dang_go(ep=True)
        if b is None:
            messagebox.showwarning("Thêm bước", "Nhập giá trị cho bước này.", parent=self.app)
            return False
        self._buoc.append(b)
        self.gia_tri_entry.delete(0, "end")
        self._ve_buoc()
        self._persist_cfg()
        if xem and self._folder():
            self._xem_truoc()
        return True

    def _gom_buoc_dang_go(self) -> None:
        """Bấm Chạy khi ô giá trị còn chữ -> tự xếp bước đó vào chuỗi rồi chạy (không cần bấm gì thêm)."""
        if self._buoc_dang_go() is not None:
            self._them_buoc(xem=False)

    def _buocs(self) -> list:
        return list(self._buoc)

    def _buocs_xem(self) -> list:
        """Chuỗi bước dùng cho xem trước = chuỗi đã xếp + bước đang gõ (nếu có)."""
        ds = list(self._buoc)
        b = self._buoc_dang_go()
        if b is not None:
            ds.append(b)
        return ds

    def _huy_hen(self) -> None:
        if getattr(self, "_hen_id", None):
            try:
                self.tk.call("after", "cancel", self._hen_id)
            except tk.TclError:
                pass
            self._hen_id = None

    def _ngu_canh(self):
        return modun_module.ngu_canh_tu(self.app, log=lambda m: self.app.set_status(m))

    def _hen_xem_truoc(self, tre_ms: int = 350) -> None:
        """Gõ tới đâu, bảng xem trước cập nhật tới đó (gộp nhiều phím trong tre_ms)."""
        self._huy_hen()
        try:
            self._hen_id = self.after(tre_ms, self._xem_truoc)
        except (RuntimeError, tk.TclError):
            self._hen_id = None

    def _ve_buoc(self) -> None:
        self.steps_box.delete(0, "end")
        for i, b in enumerate(self._buoc, start=1):
            self.steps_box.insert("end", f"{i}. {b.mo_ta()}")
        try:
            if self._buoc:
                self.goi_y.pack_forget()
            else:
                self.goi_y.pack(fill="x", padx=8, pady=(0, 4))
        except AttributeError:
            pass

    def _chon_buoc(self):
        sel = self.steps_box.curselection()
        return int(sel[0]) if sel else None

    def _xoa_buoc(self) -> None:
        i = self._chon_buoc()
        if i is None:
            return
        del self._buoc[i]
        self._ve_buoc()
        self._persist_cfg()

    def _xoa_het(self) -> None:
        self._buoc = []
        self._ve_buoc()
        self._persist_cfg()

    def _doi_cho(self, huong: int) -> None:
        i = self._chon_buoc()
        if i is None:
            return
        j = i + huong
        if 0 <= j < len(self._buoc):
            self._buoc[i], self._buoc[j] = self._buoc[j], self._buoc[i]
            self._ve_buoc()
            self.steps_box.selection_set(j)
            self._persist_cfg()

    # ------------------------------------------------------------------ thư mục
    def _folder(self) -> str:
        return self.folder_entry.get().strip()

    def _duoi(self) -> list:
        return [d.strip() for d in self.duoi_entry.get().replace(";", ",").split(",") if d.strip()]

    def _pick_folder(self) -> None:
        d = filedialog.askdirectory(parent=self.app, initialdir=self._folder() or None)
        if d:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, d)
            self._persist_cfg()
            self._xem_truoc()

    def _open_folder(self) -> None:
        d = self._folder()
        if d and os.path.isdir(d):
            subprocess.Popen(["explorer", os.path.normpath(d)])

    # ------------------------------------------------------------------ xem trước / đổi / hoàn tác
    def _xem_truoc(self) -> list:
        """Vẽ bảng xem trước theo chuỗi bước + bước đang gõ (không xếp vào chuỗi)."""
        self._hen_id = None
        folder = self._folder()
        self.tree.delete(*self.tree.get_children())
        if not folder or not os.path.isdir(folder):
            self.tom_tat.configure(text="chưa chọn thư mục")
            self._ke_hoach = []
            return []
        buocs = self._buocs_xem()
        self._ke_hoach = rt.xem_truoc(folder, buocs, duoi=self._duoi(),
                                      cung_goc=bool(self.cung_goc_var.get()))
        dem = {}
        for r in self._ke_hoach:
            dem[r["tt"]] = dem.get(r["tt"], 0) + 1
            self.tree.insert("", "end", values=(r["cu"], r["moi"], TT_NHAN.get(r["tt"], r["tt"])))
        self.tom_tat.configure(
            text=f"{len(self._ke_hoach)} file · sẽ đổi {dem.get('ok', 0)} · không đổi {dem.get('khong_doi', 0)}"
                 + (f" · trùng {dem['trung']}" if dem.get("trung") else "")
                 + (f" · lỗi {dem['loi']}" if dem.get("loi") else "")
                 + ("   ← chưa có bước nào: chọn kiểu, nhập giá trị rồi bấm ▶ Chạy đổi tên"
                    if not buocs else ""))
        return self._ke_hoach

    def _doi_ten(self) -> None:
        self._gom_buoc_dang_go()
        ke_hoach = self._xem_truoc()
        n = sum(1 for r in ke_hoach if r["tt"] == "ok")
        if not n:
            messagebox.showinfo("Đổi tên", "Không có file nào cần đổi (xem cột Trạng thái).", parent=self.app)
            return
        if not messagebox.askyesno("Đổi tên", f"Đổi tên {n} file trong:\n{self._folder()}\n\n"
                                   "Có thể Hoàn tác lần đổi gần nhất.", parent=self.app):
            return
        kq = modun_module.chay("doi_ten_file", self._ngu_canh(), [], hanh_dong="doi_ten", folder=self._folder(), ke_hoach=ke_hoach).du_lieu   # mo-dun
        self._persist_cfg()
        self._xem_truoc()
        chu = f"Đã đổi {kq['ok']} file, bỏ qua {kq['bo_qua']}."
        if kq["loi"]:
            chu += f" Lỗi {len(kq['loi'])}: " + "; ".join(kq["loi"][:3])
        self.status.configure(text=chu)
        self.app.set_status(chu)

    def _hoan_tac(self) -> None:
        folder = self._folder()
        n = rt.co_hoan_tac(folder) if folder else 0
        if not n:
            messagebox.showinfo("Hoàn tác", "Thư mục này chưa có lần đổi tên nào để hoàn tác.", parent=self.app)
            return
        if not messagebox.askyesno("Hoàn tác", f"Trả tên cũ cho {n} file?", parent=self.app):
            return
        kq = modun_module.chay("doi_ten_file", self._ngu_canh(), [], hanh_dong="hoan_tac", folder=folder).du_lieu   # mo-dun
        self._xem_truoc()
        chu = f"Đã hoàn tác {kq['ok']} file." + (f" Lỗi: {'; '.join(kq['loi'][:3])}" if kq["loi"] else "")
        self.status.configure(text=chu)
        self.app.set_status(chu)

    # ------------------------------------------------------------------ lưu / khôi phục
    def _persist_cfg(self) -> None:
        data = {"folder": self._folder(), "duoi": self.duoi_entry.get().strip(),
                "cung_goc": bool(self.cung_goc_var.get()), "buoc": [b.to_dict() for b in self._buoc]}
        try:
            os.makedirs(os.path.dirname(self._cfg_path()), exist_ok=True)
            with open(self._cfg_path(), "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def _restore_cfg(self) -> None:
        try:
            with open(self._cfg_path(), encoding="utf-8") as fh:
                c = json.load(fh) or {}
        except (OSError, ValueError):
            return
        if c.get("folder"):
            self.folder_entry.insert(0, str(c["folder"]))
        if c.get("duoi"):
            self.duoi_entry.insert(0, str(c["duoi"]))
        self.cung_goc_var.set(bool(c.get("cung_goc", True)))
        self._buoc = [rt.Buoc.from_dict(x) for x in (c.get("buoc") or []) if isinstance(x, dict)]
        self._buoc = [b for b in self._buoc if b.loai in rt.NHAN_LOAI]
        self._ve_buoc()
