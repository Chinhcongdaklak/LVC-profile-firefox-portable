"""Ho so loi: tu thu bang chung moi lan dang bai hong.

Facebook doi giao dien vai lan mot nam, khong bao truoc. Moi lan doi, cai lam
mat thoi gian nhat khong phai sua code ma la MO XEM trang moi trong ra sao.
Nen moi lan dang hong, tool tu chup man hinh trinh duyet + giu lai ban do trang
(cac o chon file, cac nut) + loi cu the vao mot thu muc rieng. Lan sau trang
hong, mo thu muc ra la thay ngay -- khoi phai dung tay chay lai de mo.

Moi lan hong mot thu muc con ``data/hoso-loi/<ngay-gio>-<nhan>/``:
  * ``man-hinh.png``  -- cua so Firefox luc dang hong (chup bang PrintWindow,
    lay dung noi dung ke ca khi cua so bi che);
  * ``qlfp-*.json``   -- lenh da giao, trang thai cuoi cua agent, ban do trang;
  * ``ghi-chu.txt``   -- gio, nhan, va dong loi.

Chi giu ``KEEP`` bo ho so moi nhat -- khong de day dia.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from typing import Optional

from . import procutil

#: Thu muc ho so loi, nam canh data cua tool.
DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "hoso-loi")
#: Giu lai bao nhieu bo ho so moi nhat.
KEEP = 20

# PrintWindow chu khong phai chup ca man hinh: lay dung noi dung cua so Firefox
# ke ca khi no bi cua so khac de len (tool chay nen, nguoi dung dang lam viec).
_PS_CHUP = r"""
Add-Type -AssemblyName System.Drawing
$src = @'
using System;using System.Runtime.InteropServices;using System.Drawing;
public class Cp {
 [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
 [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L,T,R,B; }
 public static Bitmap G(IntPtr h){ RECT r; GetWindowRect(h, out r);
   Bitmap b=new Bitmap(Math.Max(r.R-r.L,1),Math.Max(r.B-r.T,1));
   using(Graphics g=Graphics.FromImage(b)){IntPtr d=g.GetHdc();PrintWindow(h,d,2);g.ReleaseHdc(d);}
   return b; }
}
'@
Add-Type -TypeDefinition $src -ReferencedAssemblies System.Drawing
$ids = @(__PIDS__)
foreach ($id in $ids) {
  $p = Get-Process -Id $id -ErrorAction SilentlyContinue
  if ($p -and $p.MainWindowHandle -ne 0) {
    $b = [Cp]::G($p.MainWindowHandle)
    $b.Save('__OUT__')
    Write-Output "ok"
    break
  }
}
"""


def _slug(text: str) -> str:
    """Nhan -> ten thu muc an toan."""
    ra = re.sub(r"[^0-9A-Za-z_-]+", "-", (text or "").strip())
    return (ra.strip("-") or "khong-ten")[:60]


def screenshot(app_dir: str, out_path: str) -> bool:
    """Chup cua so Firefox cua DUNG app nay (theo pid). False neu khong chup duoc."""
    try:
        pids = [p.pid for p in procutil.find_under(app_dir, "firefox.exe")]
    except Exception:
        pids = []
    if not pids:
        return False
    ps = (_PS_CHUP
          .replace("__PIDS__", ",".join(str(p) for p in pids))
          .replace("__OUT__", out_path.replace("'", "''")))
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=30)
        return "ok" in (r.stdout or "") and os.path.isfile(out_path)
    except (OSError, subprocess.SubprocessError):
        return False


def _prune(base_dir: str) -> None:
    """Chi giu KEEP bo moi nhat."""
    try:
        con = sorted(d for d in os.listdir(base_dir)
                     if os.path.isdir(os.path.join(base_dir, d)))
    except OSError:
        return
    for ten in con[:-KEEP]:
        shutil.rmtree(os.path.join(base_dir, ten), ignore_errors=True)


def capture(profile_dir: str, app_dir: str, label: str, note_text: str = "",
            files: Optional[list] = None, base_dir: str = "") -> Optional[str]:
    """Thu bang chung mot lan hong vao mot thu muc con. Tra ve duong dan thu muc.

    KHONG BAO GIO nem loi: day la viec phu, hong cung khong duoc keo do viec
    dang bai hay viec dong trinh duyet.
    """
    try:
        base = base_dir or DEFAULT_DIR
        dest = os.path.join(base, time.strftime("%Y%m%d-%H%M%S") + "-" + _slug(label))
        os.makedirs(dest, exist_ok=True)

        # Chup TRUOC khi ai do kip dong trinh duyet.
        co_anh = screenshot(app_dir, os.path.join(dest, "man-hinh.png"))

        for ten in (files or []):
            src = os.path.join(profile_dir, ten)
            if os.path.isfile(src):
                try:
                    shutil.copy2(src, os.path.join(dest, os.path.basename(ten)))
                except OSError:
                    pass

        with open(os.path.join(dest, "ghi-chu.txt"), "w", encoding="utf-8") as fh:
            fh.write(f"lúc: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            fh.write(f"nhãn: {label}\n")
            fh.write(f"ảnh màn hình: {'có' if co_anh else 'không chụp được'}\n")
            fh.write(f"lỗi: {note_text}\n")

        _prune(base)
        return dest
    except Exception:
        return None
