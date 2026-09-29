"""Spintax: bien the mot cau/caption de moi lan dang ra mot ban khac nhau.

Facebook danh dau noi dung TRUNG LAP (dang y het len nhieu group / nhieu lan) la
spam. Spintax cho phep viet mot mau roi tool tu chon ngau nhien:

    "{Chào cả nhà|Xin chào mọi người}, {xem|ngó} bài này {nhé|nha} {|😍}"

-> moi lan sinh ra mot cau khac: "Xin chào mọi người, ngó bài này nha 😍".

Ho tro long nhau: "{a|{b|c}}". Khong co dau {} thi tra lai nguyen van.
"""

from __future__ import annotations

import random
import re

_GROUP = re.compile(r"\{([^{}]*)\}")


def spin(text: str, rng: random.Random | None = None) -> str:
    """Sinh MOT ban tu mau spintax. ``rng`` de test tai lap duoc."""
    if not text or "{" not in text:
        return text or ""
    r = rng or random
    out = text
    # Lap: moi vong thay cac nhom trong cung {..|..} (khong con { ben trong),
    # nen nhom long nhau duoc giai dan tu trong ra ngoai. Chan vong lap phong loi.
    for _ in range(100):
        m = _GROUP.search(out)
        if not m:
            break
        choices = m.group(1).split("|")
        out = out[:m.start()] + r.choice(choices) + out[m.end():]
    return out


def count_variants(text: str) -> int:
    """Uoc luong so ban khac nhau mot mau co the sinh (de bao nguoi dung)."""
    if not text:
        return 0
    total = 1
    # Nhan so lua chon cua tung nhom trong cung (khong long) — uoc luong tho.
    for m in re.finditer(r"\{([^{}]*)\}", text):
        n = len(m.group(1).split("|"))
        if n > 1:
            total *= n
    return total


def preview(text: str, n: int = 5) -> list[str]:
    """Vai ban mau de nguoi dung xem thu, khong trung nhau neu du bien the."""
    seen, out = set(), []
    for _ in range(n * 8):
        s = spin(text)
        if s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= n:
            break
    return out
