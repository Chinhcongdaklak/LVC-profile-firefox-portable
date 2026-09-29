"""Mo-dun MỞ PROFILE — nhom acc.

CHI MỞ trình duyệt của từng acc, KHÔNG thao tác gì thêm (yêu cầu người dùng 2026-09-19):
không nạp cookie, không xoá probe, không theo dõi/ghi đè cookie. Người dùng toàn quyền thao tác
trên trình duyệt vừa mở. Tool CHỈ đóng/điều khiển trình duyệt khi chạy các mô-đun HÀNH ĐỘNG
(đăng fanpage/nhóm, tạo fanpage, bật chuyên nghiệp) — các mô-đun đó tự close() trước khi chạy.

Muốn nạp cookie đã lưu thì dùng riêng '🔑 Đăng nhập với cookie' (mô-đun dang_nhap_cookie).
tham_so: url (mac dinh settings.start_url).
"""

from __future__ import annotations

import os
import time

from core.modun import KetQua, Modun, NguCanh, dang_ky

MA = "mo_profile"

#: Lệnh cho các process-script agent (upload/create/weblogin/nhắn tin/bm). Agent ĐỌC LẠI file này
#: MỖI LẦN tải trang (không có cờ "đã chạy") -> lệnh CŨ còn sót = agent tự chạy lại (tạo page/đăng
#: bài...) khi người dùng chỉ mở profile hoặc chuyển sang trang Page -> phiên bị đảo. Mở profile phải
#: XOÁ hết lệnh này để KHÔNG agent nào thao tác (yêu cầu người dùng 2026-09-19).
LENH_AGENT = ("qlfp-upload.json", "qlfp-create.json", "qlfp-weblogin.json",
              "qlfp-msg.json", "qlfp-bm.json")


def xoa_lenh_agent(profile_dir: str) -> int:
    """Xoá các file LỆNH agent còn sót trong profile. Trả số file đã xoá. Không đụng trình duyệt."""
    da = 0
    for ten in LENH_AGENT:
        try:
            os.remove(os.path.join(profile_dir, ten))
            da += 1
        except OSError:
            pass
    return da


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    url = tham_so.get("url") or getattr(nc.settings, "start_url", "") or ""
    for a in accs:
        if not nc.manager.is_installed(a):
            kq.them_loi(a.id, "chưa có profile")
            continue
        try:
            # Xoá lệnh agent còn sót -> KHÔNG agent nào tự chạy (tạo page/đăng bài) khi chỉ mở profile.
            try:
                so = xoa_lenh_agent(nc.manager.profile_dir(a))
                if so:
                    nc.log(f"[{a.id}] dọn {so} lệnh agent cũ còn sót (để không tự chạy gì).")
            except Exception:  # noqa: BLE001
                pass
            nc.log(f"Đang mở {a.id} (chỉ mở trình duyệt, không thao tác gì)...")
            nc.manager.launch(a, url=url)          # MỞ THẲNG, giữ nguyên phiên trong profile
            try:
                nc.store.mark_opened(a.id)          # chỉ cập nhật cột ▶ (không đụng browser)
            except Exception:  # noqa: BLE001
                pass
            kq.them_ok(a.id)
            time.sleep(1.2)
        except Exception as exc:  # noqa: BLE001
            kq.them_loi(a.id, str(exc)[:160])
    return kq


dang_ky(Modun(ma=MA, ten="▶ Mở profile", nhom="acc", chay=chay,
              mo_ta="Chỉ mở trình duyệt của acc, không thao tác gì — người dùng toàn quyền."))
