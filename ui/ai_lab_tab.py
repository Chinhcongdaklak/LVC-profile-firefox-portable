"""Tab "QUET BAI" (ex Thu nghiem AI, lan 4 - ADR-009): setup AI -> quet nhom -> gui vao Auto dang nhom.

Giao dien chi lo bam nut + hien bang. Nghiep vu (quet, gui sang job, xao hang doi)
nam trong ``core/ai_lab.py`` (HOP-DONG.md muc ai_lab + lan 4). Luong:
  1. Setup AI (nha cung cap, API key, prompt) o day = cau hinh DUNG CHUNG cho xao o tab
     Auto dang nhom (cung file data/ai_lab.json).
  2. Quet bai nhom / them tay -> bang (KHONG xao o day).
  3. Kich ban sau khi quet: "tu gui vao Auto dang nhom" (chon job) - hoac bam gui tay.
  4. Gui vao job -> xao CHU tu dong tren hang doi cua job (anh/video giu nguyen) ->
     job dang theo lich cua no.
"""

from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from core import modun as modun_module
from core.modun import tat_ca as _modun_tat_ca
_modun_tat_ca.nap()   # nap registry 1 lan luc import (luong chinh), tranh tre trong luong nen

from core import ai as ai_module
from core import ai_lab
from core.config import TOOL_DIR

PAD = 8
LAB_DIR = os.path.join(TOOL_DIR, "data", "ai_lab_media")
LAB_STORE = os.path.join(TOOL_DIR, "data", "ai_lab.json")
TAB_NHOM = "👥 Auto đăng nhóm"

_GUI = {"": "—", "gui": "➡ Đã gửi"}

COLS = (("stt", "#", 40, "center"),
        ("source", "Nguồn", 200, "w"),
        ("caption", "Caption gốc", 380, "w"),
        ("media", "Ảnh/Video", 90, "w"),
        ("ghi_chu", "Ghi chú", 200, "w"),
        ("post", "Gửi", 110, "center"))


class AiLabTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.rows: list[dict] = []
        self.templates: list = []
        kho = self._kho()
        self.cfg, self.rows, self.templates = kho.load()
        self._ui = dict(kho.ui)
        os.makedirs(LAB_DIR, exist_ok=True)
        self._build_config()
        self._build_input()
        self._build_table()
        self.refresh()

    # ------------------------------------------------------------------ kho
    def _kho(self) -> ai_lab.AiLabStore:
        return ai_lab.AiLabStore(LAB_STORE)

    def _persist(self):
        try:
            self._ui = {"kich_ban": bool(self.kich_ban_var.get()), "job": self._job_id_chon()}
        except (AttributeError, tk.TclError):
            pass
        try:
            self._kho().save(self.cfg, self.rows, self.templates, ui=self._ui)
        except OSError:
            pass

    # ------------------------------------------------------------------ config
    def _sync_cfg(self) -> None:
        """Doc giao dien vao self.cfg (khong luu, khong bao)."""
        self.cfg.provider = "mock" if self.provider_menu.get().startswith("Mock") else "gemini"
        self.cfg.api_keys = ai_module.parse_api_keys(self.key_box.get("1.0", "end"))
        self.cfg.caption_prompt = self.cap_prompt.get("1.0", "end").strip()
        self.cfg.do_caption = bool(self.do_cap.get())
        self.cfg.auto_rotate_model = bool(self.rotate.get())

    def _save_cfg(self) -> None:
        self._sync_cfg()
        self._persist()
        self.set_status(f"Đã lưu cấu hình AI ({len(self.cfg.api_keys)} key) — dùng cho xào ở tab {TAB_NHOM}.")

    def _build_config(self):
        dam = ctk.CTkFont(weight="bold")
        khung = ctk.CTkFrame(self)
        khung.pack(fill="x", padx=PAD, pady=(PAD, 4))
        r1 = ctk.CTkFrame(khung, fg_color="transparent"); r1.pack(fill="x", padx=8, pady=(8, 2))
        ctk.CTkLabel(r1, text="Setup AI (dùng cho xào ở tab Auto đăng nhóm) — Nhà cung cấp:", font=dam).pack(side="left")
        self.provider_menu = ctk.CTkOptionMenu(r1, width=200,
            values=["Mock (thử nghiệm - không cần key)", "Gemini (nhiều key, xoay model)"])
        self.provider_menu.set("Mock (thử nghiệm - không cần key)"
                               if self.cfg.provider == "mock" else "Gemini (nhiều key, xoay model)")
        self.provider_menu.pack(side="left", padx=(6, 12))
        self.do_cap = tk.BooleanVar(value=self.cfg.do_caption)
        self.rotate = tk.BooleanVar(value=self.cfg.auto_rotate_model)
        ctk.CTkCheckBox(r1, text="Xào caption", variable=self.do_cap).pack(side="left", padx=(0, 4))
        ctk.CTkLabel(r1, text="· Ảnh và video GIỮ NGUYÊN", text_color="gray60").pack(side="left", padx=4)
        ctk.CTkCheckBox(r1, text="Tự xoay model", variable=self.rotate).pack(side="left", padx=8)
        ctk.CTkButton(r1, text="💾 Lưu cấu hình", width=120, command=self._save_cfg).pack(side="right")

        rk = ctk.CTkFrame(khung, fg_color="transparent"); rk.pack(fill="x", padx=8, pady=(2, 2))
        ctk.CTkLabel(rk, text="API key (mỗi dòng 1 key, có thể '# ghi chú'):").pack(anchor="w")
        self.key_box = ctk.CTkTextbox(rk, height=54); self.key_box.pack(fill="x")
        self.key_box.insert("1.0", "\n".join(self.cfg.api_keys))

        rt = ctk.CTkFrame(khung, fg_color="transparent"); rt.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(rt, text="Mẫu prompt:", font=dam).pack(side="left")
        self.tpl_menu = ctk.CTkOptionMenu(rt, width=200, values=self._tpl_names(),
                                          command=self._apply_template)
        self.tpl_menu.set("(mẫu hiện tại)")
        self.tpl_menu.pack(side="left", padx=(6, 8))
        ctk.CTkButton(rt, text="💾 Lưu mẫu", width=90, command=self._save_template).pack(side="left", padx=2)
        ctk.CTkButton(rt, text="➕ Mẫu mới", width=90, command=self._new_template).pack(side="left", padx=2)
        ctk.CTkButton(rt, text="🗑 Xoá mẫu", width=90, fg_color="#a33",
                      command=self._del_template).pack(side="left", padx=2)

        r2 = ctk.CTkFrame(khung, fg_color="transparent"); r2.pack(fill="x", padx=8, pady=(2, 8))
        ctk.CTkLabel(r2, text="Prompt biến đổi CAPTION (ảnh/video giữ nguyên):").pack(anchor="w")
        self.cap_prompt = ctk.CTkTextbox(r2, height=48); self.cap_prompt.pack(fill="x")
        self.cap_prompt.insert("1.0", self.cfg.caption_prompt)

    # ---- mau prompt --------------------------------------------------------
    def _tpl_names(self) -> list:
        return ["(mẫu hiện tại)"] + [t.get("name", "?") for t in self.templates]

    def _apply_template(self, name: str):
        for t in self.templates:
            if t.get("name") == name:
                self.cap_prompt.delete("1.0", "end"); self.cap_prompt.insert("1.0", t.get("caption", ""))
                self.set_status(f"Đã áp mẫu prompt '{name}'.")
                return

    def _save_template(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("Lưu mẫu prompt", "Tên mẫu:", parent=self)
        if not name:
            return
        cap = self.cap_prompt.get("1.0", "end").strip()
        for t in self.templates:
            if t.get("name") == name:
                t["caption"] = cap
                break
        else:
            self.templates.append({"name": name, "caption": cap, "image": ""})
        self._persist()
        self.tpl_menu.configure(values=self._tpl_names()); self.tpl_menu.set(name)
        self.set_status(f"Đã lưu mẫu prompt '{name}'.")

    def _new_template(self):
        self.cap_prompt.delete("1.0", "end")
        self.tpl_menu.set("(mẫu hiện tại)")
        self.set_status("Soạn mẫu prompt mới rồi bấm 'Lưu mẫu'.")

    def _del_template(self):
        name = self.tpl_menu.get()
        if name == "(mẫu hiện tại)":
            self.set_status("Chọn một mẫu đã lưu để xoá.")
            return
        self.templates = [t for t in self.templates if t.get("name") != name]
        self._persist()
        self.tpl_menu.configure(values=self._tpl_names()); self.tpl_menu.set("(mẫu hiện tại)")
        self.set_status(f"Đã xoá mẫu '{name}'.")

    # ------------------------------------------------------------------ input + kich ban
    def _build_input(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=PAD, pady=(0, 4))
        ctk.CTkButton(bar, text="🔎 Quét bài nhóm", width=140, fg_color="#2f7d4f",
                      command=self.scan_new).pack(side="left", padx=3)
        ctk.CTkButton(bar, text="🔎🔎 Quét nhiều acc", width=150, fg_color="#2f7d4f",
                      command=self.scan_many).pack(side="left", padx=3)
        ctk.CTkButton(bar, text="✍ Thêm bài tay", width=120, fg_color="#1f6aa5",
                      command=self.add_manual).pack(side="left", padx=3)
        ctk.CTkButton(bar, text="🗑 Xoá dòng", width=100, fg_color="#a33",
                      command=self.delete_selected).pack(side="left", padx=3)
        ctk.CTkButton(bar, text="🗑 Xoá hết", width=90, fg_color="#7a1f1f",
                      command=self.delete_all).pack(side="left", padx=3)
        self.count_lbl = ctk.CTkLabel(bar, text="", text_color="gray60")
        self.count_lbl.pack(side="left", padx=(12, 0))

        kb = ctk.CTkFrame(self)
        kb.pack(fill="x", padx=PAD, pady=(0, 4))
        dam = ctk.CTkFont(weight="bold")
        ctk.CTkLabel(kb, text="Kịch bản sau khi quét:", font=dam).pack(side="left", padx=(10, 6), pady=8)
        self.kich_ban_var = tk.BooleanVar(value=bool(self._ui.get("kich_ban", True)))
        ctk.CTkCheckBox(kb, text="tự gửi vào tab Auto đăng nhóm (rồi xào ở đó)",
                        variable=self.kich_ban_var, command=self._persist).pack(side="left", padx=4, pady=8)
        ctk.CTkLabel(kb, text="Job nhóm:").pack(side="left", padx=(12, 4))
        self.job_menu = ctk.CTkOptionMenu(kb, width=300, values=self._job_labels() or ["(chưa có job nhóm)"],
                                          command=lambda _v: self._persist())
        self.job_menu.pack(side="left", pady=8)
        self._chon_job_da_luu()
        ctk.CTkButton(kb, text="🔄", width=34, fg_color="gray45",
                      command=self._lam_moi_job).pack(side="left", padx=(4, 8))
        ctk.CTkButton(kb, text="➡ Gửi vào Auto đăng nhóm", width=200, fg_color="#8a5a2b",
                      command=lambda: self.gui_sang_nhom()).pack(side="right", padx=(3, 10), pady=8)

    # ---- job nhom -----------------------------------------------------------
    def _jobs(self) -> list:
        try:
            return list(self.app.autoup.by_kind("group"))
        except Exception:  # noqa: BLE001 - app gia trong thuoc khong co autoup
            return []

    @staticmethod
    def ten_job(job) -> str:
        """Nhãn trong ô chọn: TÊN JOB (đúng tên tab con ở Auto đăng nhóm) — nhóm sẽ đăng."""
        return f"{job.name} — {job.config.label()}"

    def _job_labels(self) -> list:
        return [self.ten_job(j) for j in self._jobs()]

    def _lam_moi_job(self) -> None:
        nhan = self._job_labels()
        self.job_menu.configure(values=nhan or ["(chưa có job nhóm)"])
        if nhan and self.job_menu.get() not in nhan:
            self.job_menu.set(nhan[0])
        self.set_status(f"{len(nhan)} job nhóm.")

    def _chon_job_da_luu(self) -> None:
        muon = str(self._ui.get("job") or "")
        for j in self._jobs():
            if j.job_id == muon:
                self.job_menu.set(self.ten_job(j))
                return
        nhan = self._job_labels()
        if nhan:
            self.job_menu.set(nhan[0])

    def _job_chon(self):
        ten = self.job_menu.get()
        for j in self._jobs():
            if self.ten_job(j) == ten:
                return j
        return None

    def _job_id_chon(self) -> str:
        j = self._job_chon()
        return j.job_id if j is not None else ""

    # ------------------------------------------------------------------ bang
    def _build_table(self):
        wrap = ctk.CTkFrame(self); wrap.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        style = ttk.Style(); style.configure("AiLab.Treeview", rowheight=44)
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in COLS], show="headings",
                                 selectmode="extended", style="AiLab.Treeview")
        for k, t, w, a in COLS:
            self.tree.heading(k, text=t)
            self.tree.column(k, width=w, anchor=a, stretch=(k == "caption"))
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); vsb.grid(row=0, column=1, sticky="ns")
        wrap.grid_rowconfigure(0, weight=1); wrap.grid_columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _e: self._preview())
        st = ctk.CTkFrame(self, height=26, corner_radius=0); st.pack(fill="x", side="bottom")
        self.status = ctk.CTkLabel(st, text="", anchor="w"); self.status.pack(side="left", padx=12)

    def set_status(self, t):
        try: self.status.configure(text=t)
        except tk.TclError: pass

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rows, 1):
            cap = (r.get("caption_goc") or "").replace("\n", " ")
            if len(cap) > 90: cap = cap[:90] + "…"
            nimg = len(r.get("imgs_goc") or [])
            nvid = 1 if r.get("video") else 0
            media = (f"🖼{nimg} " if nimg else "") + (f"🎬{nvid}" if nvid else "")
            ghi = (r.get("detail") or "").replace("\n", " ")
            if len(ghi) > 60: ghi = ghi[:60] + "…"
            self.tree.insert("", "end", values=(
                i, r.get("source") or "(tay)", cap or "(trống)", media.strip() or "—", ghi,
                _GUI.get(r.get("post", ""), r.get("post") or "—")))
        gui = sum(1 for r in self.rows if r.get("post") == "gui")
        self.count_lbl.configure(text=f"{len(self.rows)} bài · {gui} đã gửi sang nhóm")
        self._persist()

    def _selected(self) -> list:
        out = []
        for iid in self.tree.selection():
            idx = self.tree.index(iid)
            if 0 <= idx < len(self.rows): out.append(self.rows[idx])
        return out

    # ------------------------------------------------------------------ quet / them
    def scan_new(self):
        from ui.posts_window import ScanDialog
        params = ScanDialog(self, self.app).show()
        if not params:
            return
        account, group_url, count, _dl, _save = params
        self._quet(account, group_url, count)

    def scan_many(self):
        """Quét NHIỀU acc song song, mỗi acc một link nguồn (nhanh hơn nhiều)."""
        from ui.posts_window import MultiScanDialog
        params = MultiScanDialog(self, self.app).show()
        if not params:
            return
        self._quet_nhieu(params["pairs"], params["count"])

    def _quet_nhieu(self, pairs: list, count: int) -> None:
        """Quét song song các cặp (acc, link) → gom bài về bảng. Số luồng theo ô 'Luồng' dùng chung."""
        try:
            workers = max(1, min(8, int(self.app.settings.login_threads or 3)))
        except (ValueError, AttributeError):
            workers = 3
        workers = min(workers, len(pairs))
        self.set_status(f"Quét {len(pairs)} acc song song ({workers} luồng)...")

        def work():
            xong = {"n": 0}

            def on_acc(r: dict) -> None:
                xong["n"] += 1
                if r["rows"]:
                    self.app._post(lambda rows=r["rows"]: self._add_rows(rows))
                self.app._post(lambda a=r["acc_id"], n=len(r["rows"]), e=r["loi"], k=xong["n"]:
                               self.set_status(f"[{k}/{len(pairs)}] {a}: "
                                               + (f"{n} bài" if not e else f"lỗi — {e[:50]}")))

            try:
                _modun_tat_ca.nap()
                nc = modun_module.ngu_canh_tu(self.app, log=lambda m: self.app._post(lambda t=m: self.set_status(t)), so_luong=workers)
                kq = modun_module.chay("quet_bai", nc, [], pairs=pairs, count=count, lab_dir=LAB_DIR,
                                       workers=workers, on_acc=on_acc).du_lieu["kq"]   # mo-dun (ADR-028)
            except Exception as exc:  # noqa: BLE001
                self.app._post(lambda e=exc: messagebox.showerror("Quét nhiều acc", str(e), parent=self))
                return
            tong = sum(len(r["rows"]) for r in kq)
            loi = [r["acc_id"] for r in kq if r["loi"]]
            self.app._post(lambda: self.set_status(
                f"Xong: {tong} bài từ {len(pairs)} acc"
                + (f" · lỗi {len(loi)} acc: {', '.join(loi[:8])}" if loi else "")))

        threading.Thread(target=work, daemon=True).start()

    def _quet(self, account, group_url: str, count: int) -> None:
        """Quét trong luồng nền → thêm dòng → (kịch bản) gửi vào job nhóm. KHÔNG xào ở đây."""
        def work():
            try:
                rows = ai_lab.quet_nhom(self.app.manager, account, group_url, count, LAB_DIR,
                                        log=lambda m: self.app._post(lambda t=m: self.set_status(t)))
            except Exception as exc:  # noqa: BLE001
                self.app._post(lambda e=exc: messagebox.showerror("Quét", str(e), parent=self))
                return
            self.app._post(lambda: self._add_rows(rows))
        self.set_status("Đang quét...")
        threading.Thread(target=work, daemon=True).start()

    def add_manual(self):
        dlg = _ManualDialog(self)
        self.wait_window(dlg)
        if not getattr(dlg, "result", None):
            return
        caption, images = dlg.result
        self._add_rows([ai_lab.row_moi(f"tay{int(time.time() * 1000)}", "", caption, list(images))])

    def _add_rows(self, new: list):
        if not new:
            self.set_status("Không có bài nào.")
            return
        self.rows.extend(new)
        self.refresh()
        if self.kich_ban_var.get():
            self.gui_sang_nhom(new)
        else:
            self.set_status(f"Đã thêm {len(new)} bài. Bấm '➡ Gửi vào Auto đăng nhóm' khi sẵn sàng.")

    # ------------------------------------------------------------------ gui sang nhom
    def gui_sang_nhom(self, rows=None) -> None:
        """Gửi dòng (đã chọn / vừa quét / mọi dòng chưa gửi) vào job nhóm rồi xào ở đó."""
        job = self._job_chon()
        if job is None:
            messagebox.showinfo("Auto đăng nhóm",
                                f"Chưa có job nhóm. Vào tab '{TAB_NHOM}' bấm 'Thêm nhóm' rồi bấm 🔄.",
                                parent=self)
            return
        if rows is None:
            rows = self._selected() or [r for r in self.rows if r.get("post") != "gui"]
        if not rows:
            self.set_status("Không có bài nào để gửi (mọi bài đã gửi).")
            return
        try:
            items = ai_lab.gui_sang_nhom(rows, job, log=self.set_status)
        except OSError as exc:
            messagebox.showerror("Auto đăng nhóm", f"Không tạo được thư mục bài chờ đăng: {exc}", parent=self)
            return
        self.refresh()
        self.set_status(f"Đã gửi {len(items)} bài vào '{self.ten_job(job)}' — đang xào ở đó...")
        self._sang_tab_nhom(job)
        cfg = ai_module.load_shared_config()          # = setup ở tab này
        ok, ly_do = ai_module.available(cfg)
        if not ok:
            for it in items:
                it["xao"] = "loi"; it["xao_detail"] = ly_do
            job.save()
            messagebox.showinfo("Xào AI", ly_do + "\n(Setup AI ở khối trên cùng của tab này.)", parent=self)
            return

        def work():
            kq = ai_lab.xao_hang_doi(job, items, cfg,
                                     log=lambda m: self.app._post(lambda t=m: self.set_status(t)))
            self.app._post(lambda: self.set_status(
                f"Xào xong ở '{self.ten_job(job)}': {kq['da']} được, {kq['loi']} lỗi."))
            self.app._post(lambda: self._lam_moi_bang_nhom(job))
        threading.Thread(target=work, daemon=True).start()

    def _sang_tab_nhom(self, job) -> None:
        # Tab nhom co hai tab con (Dang nhom / Quet bai) -> qua App.mo_tab_nhom.
        try:
            mo = getattr(self.app, "mo_tab_nhom", None)
            if mo is not None:
                mo()
            else:
                self.app.tabs.set(TAB_NHOM)
        except Exception:  # noqa: BLE001
            pass
        self._lam_moi_bang_nhom(job)

    def _lam_moi_bang_nhom(self, job) -> None:
        gt = getattr(self.app, "group_tab", None)
        if gt is None:
            return
        try:
            gt._rebuild(chon=job.job_id)
            gt.select(job.job_id)
            if gt.panel is not None:
                gt.panel._refresh_queue()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ xoá / xem
    def delete_selected(self):
        rows = self._selected()
        if not rows:
            self.set_status("Chưa chọn dòng nào.")
            return
        if not messagebox.askyesno("Xoá", f"Xoá {len(rows)} dòng?", parent=self):
            return
        ids = set(id(r) for r in rows)
        self.rows = [r for r in self.rows if id(r) not in ids]
        self.refresh()

    def delete_all(self):
        if not self.rows:
            return
        if not messagebox.askyesno("Xoá hết", f"Xoá tất cả {len(self.rows)} dòng?", parent=self):
            return
        self.rows = []
        self.refresh()

    def _preview(self):
        rows = self._selected()
        if not rows:
            return
        r = rows[0]
        msg = (f"CAPTION GỐC:\n{r.get('caption_goc') or '(trống)'}\n\n"
               f"Ảnh: {len(r.get('imgs_goc') or [])} · Video: {'có' if r.get('video') else 'không'}"
               f" · Gửi: {_GUI.get(r.get('post', ''), r.get('post') or '—')}")
        if r.get("detail"):
            msg += f"\n\nGhi chú: {r['detail']}"
        messagebox.showinfo("Xem trước", msg, parent=self)


class _ManualDialog(ctk.CTkToplevel):
    """Nhap tay mot bai: caption + chon anh."""
    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self._images = []
        self.title("Thêm bài viết tay")
        self.geometry("560x420")
        self.transient(parent)
        self.after(150, lambda: (self.lift(), self.grab_set()))
        ctk.CTkLabel(self, text="Caption:").pack(anchor="w", padx=PAD, pady=(PAD, 2))
        self.cap = ctk.CTkTextbox(self, height=160); self.cap.pack(fill="both", expand=True, padx=PAD)
        row = ctk.CTkFrame(self, fg_color="transparent"); row.pack(fill="x", padx=PAD, pady=6)
        ctk.CTkButton(row, text="Chọn ảnh...", command=self._pick).pack(side="left")
        self.img_lbl = ctk.CTkLabel(row, text="chưa chọn ảnh", text_color="gray60")
        self.img_lbl.pack(side="left", padx=8)
        btns = ctk.CTkFrame(self, fg_color="transparent"); btns.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(btns, text="Hủy", width=90, fg_color="gray35", command=self.destroy).pack(side="right")
        ctk.CTkButton(btns, text="Thêm", width=90, command=self._ok).pack(side="right", padx=6)

    def _pick(self):
        fs = filedialog.askopenfilenames(parent=self, title="Chọn ảnh",
            filetypes=[("Ảnh", "*.jpg *.jpeg *.png *.webp *.gif")])
        if fs:
            self._images = list(fs)
            self.img_lbl.configure(text=f"{len(fs)} ảnh")

    def _ok(self):
        cap = self.cap.get("1.0", "end").strip()
        if not cap and not self._images:
            messagebox.showinfo("Thêm bài", "Nhập caption hoặc chọn ảnh.", parent=self); return
        self.result = (cap, self._images)
        self.destroy()
