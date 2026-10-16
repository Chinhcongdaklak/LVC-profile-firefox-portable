"""Tự xếp cửa sổ Firefox của tool theo kiểu "xếp lớp 3 cột" (Cài đặt > Kiểu cửa sổ).

Ý người dùng (2026-10-06): 3 cột CỐ ĐỊNH; trình duyệt thứ 4 trở đi XẾP LỚP chồng lên trong cùng
cột (lệch dần cho thấy cái bên dưới); cửa sổ vẫn là cửa sổ TỰ DO nên kéo đi đâu cũng được.

Vì vậy mỗi cửa sổ chỉ được đặt **ĐÚNG MỘT LẦN** — lúc nó vừa xuất hiện. Sau đó tool không đụng
vào nữa (đụng lại là giật khỏi tay người đang kéo). Cửa sổ đóng thì trả ô về cho cửa sổ sau.

Phần THUẦN: ``SapXepCuaSo`` không gọi Windows trực tiếp — vị trí lấy từ ``core.cuaso.o_ba_cot``,
việc đặt cửa sổ đi qua hàm ``dat`` tiêm vào -> thước chạy được trên mọi máy.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from . import cuaso


class SapXepCuaSo:
    """Theo dõi các cửa sổ Firefox của tool, cửa sổ MỚI thì xếp vào ô trống nhỏ nhất."""

    def __init__(self, *, cot: int = cuaso.COT_CO_DINH, vien: int = cuaso.VIEN_MAC_DINH,
                 khe: int = cuaso.KHE_MAC_DINH, lech: int = cuaso.LECH_MAC_DINH,
                 man: Optional[tuple] = None,
                 dat: Optional[Callable[[int, int, int, int, int], bool]] = None):
        self.cot = max(1, int(cot))
        self.vien, self.khe, self.lech = int(vien), int(khe), int(lech)
        self._man = man                       # (rong, cao); None = hỏi màn hình thật
        self._dat = dat or cuaso.dat_vi_tri
        #: hwnd -> chỉ số ô đã cấp (cửa sổ đã xếp rồi thì KHÔNG xếp lại).
        self._o: dict = {}

    # ------------------------------------------------------------------ ô
    def man_hinh(self) -> tuple:
        return self._man if self._man else cuaso.kich_thuoc_man_hinh()

    def _o_trong(self) -> int:
        """Chỉ số ô nhỏ nhất chưa ai dùng (cửa sổ đóng thì ô của nó về lại đây)."""
        dang_dung = set(self._o.values())
        i = 0
        while i in dang_dung:
            i += 1
        return i

    def da_xep(self, hwnd: int) -> bool:
        return hwnd in self._o

    def quen(self, hwnds_con: Iterable[int]) -> int:
        """Bỏ nhớ các cửa sổ đã đóng -> trả ô về. Tra số ô vừa được trả."""
        con = set(hwnds_con)
        chet = [h for h in self._o if h not in con]
        for h in chet:
            self._o.pop(h, None)
        return len(chet)

    # ------------------------------------------------------------------ chạy
    def quet(self, hwnds: Iterable[int]) -> list:
        """Xếp các cửa sổ MỚI trong ``hwnds``. Trả ``[(hwnd, ô, (x, y, rộng, cao))]`` đã đặt.

        Cửa sổ đã xếp trước đó KHÔNG bị đụng tới (người dùng kéo đi thì cứ để yên).
        """
        hwnds = [h for h in hwnds if h]
        self.quen(hwnds)
        man_rong, man_cao = self.man_hinh()
        ra = []
        for h in hwnds:
            if h in self._o:
                continue                      # đã xếp một lần rồi -> để yên
            i = self._o_trong()
            self._o[h] = i
            vt = cuaso.o_ba_cot(i, man_rong, man_cao, cot=self.cot, vien=self.vien,
                                khe=self.khe, lech=self.lech)
            try:
                self._dat(h, *vt)
            except Exception:  # noqa: BLE001  (cửa sổ vừa đóng giữa chừng)
                self._o.pop(h, None)
                continue
            ra.append((h, i, vt))
        return ra


# ---------------------------------------------------------------- tiện ích cho App
def pid_cua_tool(roots: Iterable[str]) -> set:
    """PID của mọi firefox.exe nằm dưới các thư mục profile của tool (FB / X / YouTube).

    Lọc theo PID để KHÔNG đụng vào Firefox cá nhân người dùng đang mở.
    """
    from core import procutil
    pids = set()
    for r in roots:
        if not r:
            continue
        try:
            pids |= {p.pid for p in procutil.find_under(r, "firefox.exe", use_cache=True)}
        except Exception:  # noqa: BLE001
            pass
    return pids


def cua_so_cua_tool(roots: Iterable[str]) -> list:
    """hwnd các cửa sổ Firefox CHÍNH do tool mở (theo profile roots)."""
    pids = pid_cua_tool(roots)
    if not pids:
        return []
    return [h for h, pid in cuaso.cua_so_firefox() if pid in pids]
