"""Tab "Nhắn tin AI": soạn KỊCH BẢN trả lời + chọn acc + cấu hình Gemini -> tự trả
lời bạn bè trên Messenger.

Giao diện chỉ lo bấm nút + hiện bảng. Nghiệp vụ (sinh câu trả lời, điều khiển phiên
messenger, lưu/nạp kịch bản) nằm trong ``core/fbchat.py`` (HOP-DONG.md mục fbchat).
Cấu hình Gemini DÙNG CHUNG với tab Quét bài (cùng file ``data/ai_lab.json``).
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

from core import modun as modun_module
from core.modun import tat_ca as _modun_tat_ca
_modun_tat_ca.nap()

from core import ai as ai_module
from core import fbchat
from .dialogs import AccountPickerDialog

PAD = 8

COLS = (("acc", "Acc", 150, "w"),
        ("ban", "Bạn", 160, "w"),
        ("tin_den", "Tin đến", 300, "w"),
        ("tra_loi", "Trả lời (AI)", 320, "w"),
        ("trang_thai", "Trạng thái", 260, "w"))

_TT = {"da_gui": "✅ Đã gửi", "loi": "⚠ Lỗi gửi", "xao_loi": "⚠ AI lỗi",
       "dang": "… đang xử lý"}


class ChatTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.kich_bans: list[fbchat.KichBan] = fbchat.tai_kich_ban(self._cfg_path())
        self.cfg = ai_module.load_shared_config()
        self._dang_chay = False
        self._dung = False
        self._acc_ids: list[str] = []   # acc đã chọn đưa vào bảng (rỗng ban đầu)
        self._build_config()
        self._build_kich_ban()
        self._build_acc()
        self._build_table()
        self._lam_moi_chon_kb()

    # ------------------------------------------------------------------ đường dẫn
    def _cfg_path(self) -> str:
        return fbchat.default_path()

    def set_status(self, t: str) -> None:
        try:
            self.app.set_status(t)
        except Exception:  # noqa: BLE001
            pass
        self._log(t)

    # ------------------------------------------------------------------ cấu hình AI
    def _build_config(self) -> None:
        box = ctk.CTkFrame(self)
        box.pack(fill="x", padx=PAD, pady=(PAD, 4))
        r1 = ctk.CTkFrame(box, fg_color="transparent"); r1.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(r1, text="🤖 Nhà cung cấp:").pack(side="left")
        self.provider = ctk.CTkOptionMenu(r1, width=110, values=["gemini", "mock"],
                                           command=lambda _v: None)
        self.provider.set(self.cfg.provider or "mock")
        self.provider.pack(side="left", padx=6)
        ctk.CTkButton(r1, text="💾 Lưu cấu hình", width=120,
                      command=self._save_cfg).pack(side="right")
        ctk.CTkLabel(r1, text="(API key dùng chung với tab Quét bài)",
                     text_color="gray").pack(side="right", padx=8)
        rk = ctk.CTkFrame(box, fg_color="transparent"); rk.pack(fill="x", padx=6, pady=(0, 4))
        ctk.CTkLabel(rk, text="🔑 API key Gemini (mỗi dòng 1 key):").pack(anchor="w")
        self.key_box = ctk.CTkTextbox(rk, height=48); self.key_box.pack(fill="x")
        self.key_box.insert("1.0", "\n".join(self.cfg.api_keys))

    def _sync_cfg(self) -> None:
        self.cfg.provider = self.provider.get()
        self.cfg.api_keys = ai_module.parse_api_keys(self.key_box.get("1.0", "end"))

    def _save_cfg(self) -> None:
        self._sync_cfg()
        try:
            path = ai_module.shared_config_path()
            import json
            import os
            os.makedirs(os.path.dirname(path), exist_ok=True)
            raw = {}
            try:
                with open(path, encoding="utf-8") as fh:
                    raw = json.load(fh)
            except (OSError, ValueError):
                raw = {}
            raw["cfg"] = self.cfg.to_dict()
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(raw, fh, ensure_ascii=False, indent=2)
            self.set_status(f"Đã lưu cấu hình AI ({len(self.cfg.api_keys)} key).")
        except OSError as exc:
            messagebox.showerror("Lưu cấu hình", str(exc), parent=self)

    # ------------------------------------------------------------------ kịch bản
    def _build_kich_ban(self) -> None:
        box = ctk.CTkFrame(self)
        box.pack(fill="x", padx=PAD, pady=4)
        top = ctk.CTkFrame(box, fg_color="transparent"); top.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(top, text="🎭 Kịch bản:").pack(side="left")
        self.kb_chon = ctk.CTkOptionMenu(top, width=200, values=["(mới)"],
                                         command=self._ap_kich_ban)
        self.kb_chon.pack(side="left", padx=6)
        ctk.CTkButton(top, text="💾 Lưu", width=70, command=self._luu_kich_ban).pack(side="left", padx=2)
        ctk.CTkButton(top, text="➕ Mới", width=70, command=self._kb_moi).pack(side="left", padx=2)
        ctk.CTkButton(top, text="🗑 Xoá", width=70, fg_color="#a33",
                      command=self._kb_xoa).pack(side="left", padx=2)

        r1 = ctk.CTkFrame(box, fg_color="transparent"); r1.pack(fill="x", padx=6, pady=2)
        ctk.CTkLabel(r1, text="Tên:", width=70, anchor="w").pack(side="left")
        self.ten_entry = ctk.CTkEntry(r1, width=200); self.ten_entry.pack(side="left", padx=4)
        ctk.CTkLabel(r1, text="Giọng điệu:", width=90, anchor="w").pack(side="left", padx=(10, 0))
        self.giong_entry = ctk.CTkEntry(r1, width=200,
                                        placeholder_text="thân mật / trang trọng / hài hước")
        self.giong_entry.pack(side="left", padx=4)

        r2 = ctk.CTkFrame(box, fg_color="transparent"); r2.pack(fill="x", padx=6, pady=2)
        ctk.CTkLabel(r2, text="Vai / tính cách (persona):").pack(anchor="w")
        self.persona_box = ctk.CTkTextbox(r2, height=44); self.persona_box.pack(fill="x")

        r3 = ctk.CTkFrame(box, fg_color="transparent"); r3.pack(fill="x", padx=6, pady=(2, 2))
        ctk.CTkLabel(r3, text="Chỉ dẫn thêm cho AI:").pack(anchor="w")
        self.prompt_box = ctk.CTkTextbox(r3, height=44); self.prompt_box.pack(fill="x")
        # Tin MO DAU: gui cho nguoi CHUA TUNG nhan (theo ngon ngu cua ho); da noi chuyen thi AI doc 5 tin gan
        # nhat roi tra loi tin gan nhat (core.fbchat.tra_loi_ngu_canh).
        r4 = ctk.CTkFrame(box, fg_color="transparent"); r4.pack(fill="x", padx=6, pady=(2, 6))
        ctk.CTkLabel(r4, text="Tin mở đầu (gửi người chưa từng nhắn — chọn theo ngôn ngữ của họ):").pack(anchor="w")
        rv = ctk.CTkFrame(r4, fg_color="transparent"); rv.pack(fill="x")
        ctk.CTkLabel(rv, text="Tiếng Việt", width=70, anchor="w").pack(side="left")
        self.mo_dau_vi_entry = ctk.CTkEntry(rv); self.mo_dau_vi_entry.pack(side="left", fill="x", expand=True)
        re_ = ctk.CTkFrame(r4, fg_color="transparent"); re_.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(re_, text="English", width=70, anchor="w").pack(side="left")
        self.mo_dau_en_entry = ctk.CTkEntry(re_); self.mo_dau_en_entry.pack(side="left", fill="x", expand=True)

    def _kb_ten_list(self) -> list:
        return [k.ten or "(chưa đặt tên)" for k in self.kich_bans]

    def _lam_moi_chon_kb(self) -> None:
        ten = self._kb_ten_list() or ["(mới)"]
        self.kb_chon.configure(values=ten + ["(mới)"])

    def _doc_kich_ban(self) -> fbchat.KichBan:
        return fbchat.KichBan(
            ten=self.ten_entry.get().strip(),
            persona=self.persona_box.get("1.0", "end").strip(),
            giong_dieu=self.giong_entry.get().strip(),
            prompt_them=self.prompt_box.get("1.0", "end").strip(),
            bat=True,
            mo_dau_vi=self.mo_dau_vi_entry.get().strip() or fbchat.MO_DAU_VI,
            mo_dau_en=self.mo_dau_en_entry.get().strip() or fbchat.MO_DAU_EN,
        )

    def _dat_kich_ban(self, kb: fbchat.KichBan) -> None:
        self.ten_entry.delete(0, "end"); self.ten_entry.insert(0, kb.ten)
        self.giong_entry.delete(0, "end"); self.giong_entry.insert(0, kb.giong_dieu)
        self.persona_box.delete("1.0", "end"); self.persona_box.insert("1.0", kb.persona)
        self.prompt_box.delete("1.0", "end"); self.prompt_box.insert("1.0", kb.prompt_them)
        self.mo_dau_vi_entry.delete(0, "end"); self.mo_dau_vi_entry.insert(0, getattr(kb, "mo_dau_vi", "") or fbchat.MO_DAU_VI)
        self.mo_dau_en_entry.delete(0, "end"); self.mo_dau_en_entry.insert(0, getattr(kb, "mo_dau_en", "") or fbchat.MO_DAU_EN)

    def _ap_kich_ban(self, ten: str) -> None:
        if ten == "(mới)":
            self._kb_moi(); return
        kb = next((k for k in self.kich_bans if (k.ten or "(chưa đặt tên)") == ten), None)
        if kb:
            self._dat_kich_ban(kb)

    def _kb_moi(self) -> None:
        self._dat_kich_ban(fbchat.KichBan())

    def _luu_kich_ban(self) -> None:
        kb = self._doc_kich_ban()
        if not kb.ten:
            messagebox.showwarning("Kịch bản", "Chưa đặt tên kịch bản.", parent=self)
            return
        cu = next((k for k in self.kich_bans if k.ten == kb.ten), None)
        if cu:
            self.kich_bans[self.kich_bans.index(cu)] = kb
        else:
            self.kich_bans.append(kb)
        fbchat.luu_kich_ban(self.kich_bans, self._cfg_path())
        self._lam_moi_chon_kb()
        self.kb_chon.set(kb.ten)
        self.set_status(f"Đã lưu kịch bản “{kb.ten}”.")

    def _kb_xoa(self) -> None:
        ten = self.ten_entry.get().strip()
        self.kich_bans = [k for k in self.kich_bans if k.ten != ten]
        fbchat.luu_kich_ban(self.kich_bans, self._cfg_path())
        self._lam_moi_chon_kb()
        self._kb_moi()

    # ------------------------------------------------------------------ chọn acc
    def _build_acc(self) -> None:
        box = ctk.CTkFrame(self)
        box.pack(fill="x", padx=PAD, pady=4)
        bar = ctk.CTkFrame(box, fg_color="transparent"); bar.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(bar, text="Số người muốn nhắn / acc:").pack(side="left")
        self.so_nguoi = ctk.CTkEntry(bar, width=54); self.so_nguoi.insert(0, "5")
        self.so_nguoi.pack(side="left", padx=(2, 12))
        ctk.CTkLabel(bar, text="Tổng thời gian (phút):").pack(side="left")
        self.tong_phut = ctk.CTkEntry(bar, width=60); self.tong_phut.insert(0, "60")
        self.tong_phut.pack(side="left", padx=(2, 12))
        ctk.CTkLabel(bar, text="Cách nhau (phút):").pack(side="left")
        self.cach_phut = ctk.CTkEntry(bar, width=54); self.cach_phut.insert(0, "15")
        self.cach_phut.pack(side="left", padx=2)
        self.start_btn = ctk.CTkButton(bar, text="▶ Bắt đầu nhắn", width=130,
                                       fg_color="#2f7d4f", command=self._bat_dau)
        self.start_btn.pack(side="right", padx=2)
        self.stop_btn = ctk.CTkButton(bar, text="⏹ Dừng", width=80, fg_color="#a33",
                                      command=self._dung_lai)
        self.stop_btn.pack(side="right", padx=2)

        bar2 = ctk.CTkFrame(box, fg_color="transparent"); bar2.pack(fill="x", padx=6, pady=(0, 2))
        ctk.CTkLabel(bar2, text="👤 Acc nhắn tin:").pack(side="left")
        ctk.CTkButton(bar2, text="➕ Chọn acc", width=100,
                      command=self._pick_accounts).pack(side="left", padx=6)
        ctk.CTkButton(bar2, text="🗑 Xoá acc đã chọn", width=140, fg_color="#a33",
                      command=self._remove_selected_accs).pack(side="left", padx=2)

        wrap = ctk.CTkFrame(box); wrap.pack(fill="x", padx=6, pady=(0, 6))
        self.acc_tree = ttk.Treeview(wrap, columns=["id"], show="headings",
                                     selectmode="extended", height=4)
        self.acc_tree.heading("id", text="id acc")
        self.acc_tree.column("id", width=260, anchor="w")
        self.acc_tree.pack(side="left", fill="x", expand=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.acc_tree.yview)
        sb.pack(side="right", fill="y"); self.acc_tree.configure(yscrollcommand=sb.set)
        self._show_accs()

    def _pick_accounts(self) -> None:
        chon = AccountPickerDialog(self.app, self.app.store.accounts, self._acc_ids).show()
        if chon is None:
            return
        self._dat_acc(chon)

    def _dat_acc(self, ids: list) -> None:
        seen, sach = set(), []
        for a in ids:
            if a and a not in seen:
                seen.add(a); sach.append(a)
        self._acc_ids = sach
        self._show_accs()

    def _show_accs(self) -> None:
        tree = getattr(self, "acc_tree", None)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for ma in self._acc_ids:
            con = self.app.store.get(ma) is not None
            hien = ma if con else f"{ma} (mất)"
            tree.insert("", "end", iid=ma, values=(hien,))

    def _remove_selected_accs(self) -> None:
        tree = getattr(self, "acc_tree", None)
        chon = list(tree.selection()) if tree else []
        if not chon:
            self.set_status("Chọn acc trong bảng rồi bấm Xoá acc đã chọn.")
            return
        bo = set(chon)
        self._acc_ids = [a for a in self._acc_ids if a not in bo]
        self._show_accs()

    def _acc_da_chon(self) -> list:
        out = []
        for i in self._acc_ids:
            a = self.app.store.get(i)
            if a:
                out.append(a)
        return out

    # ------------------------------------------------------------------ bảng + log
    def _build_table(self) -> None:
        wrap = ctk.CTkFrame(self); wrap.pack(fill="both", expand=True, padx=PAD, pady=4)
        self.result_tree = ttk.Treeview(wrap, columns=[c[0] for c in COLS],
                                        show="headings", selectmode="browse")
        for k, t, w, anc in COLS:
            self.result_tree.heading(k, text=t)
            self.result_tree.column(k, width=w, anchor=anc)
        self.result_tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.result_tree.yview)
        sb.pack(side="right", fill="y"); self.result_tree.configure(yscrollcommand=sb.set)

        lg = ctk.CTkFrame(self); lg.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkLabel(lg, text="📜 Nhật ký:").pack(anchor="w", padx=6)
        self.log_box = ctk.CTkTextbox(lg, height=90); self.log_box.pack(fill="x", padx=6, pady=(0, 6))

    def _log(self, msg: str) -> None:
        try:
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
        except Exception:  # noqa: BLE001
            pass

    def _them_dong(self, acc_id: str, row: dict) -> None:
        tt = _TT.get(row.get("trang_thai", ""), row.get("trang_thai", ""))
        if row.get("ly_do"):
            tt = f"{tt} — {row['ly_do']}"       # ly do agent khong gui duoc (khong go duoc / khong gui duoc / e2ee)
        self.result_tree.insert("", "end", values=(
            acc_id, row.get("ban", ""), row.get("tin_den", ""),
            row.get("tra_loi", ""), tt))

    # ------------------------------------------------------------------ chạy
    def _bat_dau(self) -> None:
        if self._dang_chay:
            return
        accs = self._acc_da_chon()
        if not accs:
            messagebox.showwarning("Nhắn tin AI", "Chưa chọn acc nào.", parent=self)
            return
        kb = self._doc_kich_ban()
        if not (kb.persona or kb.prompt_them):
            messagebox.showwarning("Nhắn tin AI",
                                   "Kịch bản trống — nhập persona hoặc chỉ dẫn cho AI.",
                                   parent=self)
            return
        self._sync_cfg()
        ok, msg = ai_module.available(self.cfg)
        if not ok:
            messagebox.showwarning("Nhắn tin AI", msg, parent=self)
            return
        so_nguoi = self._so_nguyen(self.so_nguoi, 5, toi_thieu=1)
        tong_phut = self._so_nguyen(self.tong_phut, 60, toi_thieu=1)
        cach_phut = self._so_nguyen(self.cach_phut, 15, toi_thieu=0)
        self._dung = False
        self._dang_chay = True
        self.start_btn.configure(state="disabled")
        threading.Thread(target=self._chay, args=(accs, kb, so_nguoi, tong_phut, cach_phut),
                         daemon=True).start()

    @staticmethod
    def _so_nguyen(entry, mac_dinh: int, toi_thieu: int = 0) -> int:
        try:
            return max(toi_thieu, int(entry.get().strip() or str(mac_dinh)))
        except ValueError:
            return mac_dinh

    def _dung_lai(self) -> None:
        self._dung = True
        self.set_status("Đang dừng sau acc hiện tại...")

    def _chay(self, accs: list, kb: fbchat.KichBan, so_nguoi: int,
              tong_phut: int, cach_phut: int) -> None:
        def on_row(acc, rows):
            for row in rows:
                self.app._post(lambda a=acc, r=row: self._them_dong(a.id, r))
        try:
            nc = modun_module.ngu_canh_tu(self.app, log=lambda m: self.app._post(lambda t=m: self.set_status(t)))
            tong = modun_module.chay("nhan_tin_ai", nc, accs, kich_ban=kb, cfg=self.cfg,     # mo-dun (ADR-028)
                                     so_nguoi=so_nguoi, tong_phut=tong_phut, cach_phut=cach_phut,
                                     nen_dung=lambda: self._dung, on_row=on_row).du_lieu
        except Exception as exc:  # noqa: BLE001
            self.app._post(lambda e=exc: self.set_status(f"Lỗi: {e}"))
            tong = None
        self.app._post(lambda t=tong: self._xong(t))

    def _xong(self, tong=None) -> None:
        self._dang_chay = False
        self.start_btn.configure(state="normal")
        if tong:
            self.set_status(f"Xong: {tong.get('so_vong', 0)} vòng, "
                            f"{tong.get('tong_gui', 0)} tin đã gửi.")
        else:
            self.set_status("Đã dừng nhắn tin.")
