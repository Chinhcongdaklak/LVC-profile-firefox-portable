"""Mo-dun CHECK PROXY — nhom proxy (truoc day la App.check_proxies + helper _extract_exit_ip /
_duplicate_subnet_report trong ui/app.py).

Test proxy tung acc (mang, tuan tu), ghi Live/Die + thoi diem vao acc (proxy_status/proxy_checked);
canh bao nhieu acc chung dai IP (IPv6 /64, IPv4 trung) -> Google de bat CAPTCHA. tham_so: khong co.
can_profile=False (khong dung profile) — tool khong khoa acc khi chay.
"""

from __future__ import annotations

import ipaddress
import re
import time

from core.modun import KetQua, Modun, NguCanh, dang_ky
from core.proxy_relay import test_proxy

MA = "check_proxy"
_IP_RE = re.compile(r"IP ra ngoài:\s*([0-9a-fA-F:.]+)")


def extract_exit_ip(detail: str) -> str:
    m = _IP_RE.search(detail or "")
    return m.group(1).strip() if m else ""


def subnet_key(ip: str) -> str:
    """IPv6 gom theo /64 (Google dem han muc theo ca khoi), IPv4 theo tung dia chi."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    if addr.version == 6:
        net = ipaddress.ip_network(f"{ip}/64", strict=False)
        return f"{net.network_address}/64"
    return str(addr)


def duplicate_subnet_report(ip_of: dict) -> str:
    """Canh bao cac acc co exit IP trung dai; rong neu khong trung."""
    groups: dict[str, list[str]] = {}
    for account_id, ip in ip_of.items():
        key = subnet_key(ip)
        if key:
            groups.setdefault(key, []).append(account_id)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    if not dupes:
        return ""
    lines = ["⚠ CẢNH BÁO: nhiều acc dùng chung dải IP → Google dễ bắt CAPTCHA:"]
    for key, ids in dupes.items():
        kind = "/64 (IPv6)" if "/64" in key else "IP (IPv4)"
        lines.append(f"  • {len(ids)} acc chung {kind} {key}:")
        lines.append("      " + ", ".join(ids))
    lines.append("  → Nên cho mỗi acc một dải IP khác nhau (đổi proxy/IP).")
    return "\n".join(lines)


def chay(nc: NguCanh, accs: list, tham_so: dict) -> KetQua:
    kq = KetQua()
    targets = [a for a in accs if a.get_proxy().enabled]
    for a in accs:
        if a not in targets:
            kq.them_loi(a.id, "chưa gán proxy")
    if not targets:
        kq.ghi_chu = "các acc chưa gán proxy"
        return kq
    ip_of: dict = {}
    for i, a in enumerate(targets, start=1):
        nc.log(f"[{i}/{len(targets)}] Đang kiểm tra proxy của {a.id}...")
        ok, detail = test_proxy(a.get_proxy())
        a.proxy_status = "Live" if ok else "Die"
        a.proxy_checked = time.strftime("%Y-%m-%d %H:%M")
        if ok:
            kq.them_ok(a.id)
            ip = extract_exit_ip(detail)
            if ip:
                ip_of[a.id] = ip
        else:
            kq.them_loi(a.id, detail)
        nc.post(lambda: None)
    try:
        nc.store.save()
    except Exception:  # noqa: BLE001
        pass
    canh_bao = duplicate_subnet_report(ip_of)
    kq.ghi_chu = f"sống {kq.so_ok}/{len(targets)}" + (f"\n{canh_bao}" if canh_bao else "")
    kq.du_lieu = {"ip_of": ip_of, "canh_bao": canh_bao}
    return kq


dang_ky(Modun(ma=MA, ten="🔍 Check proxy", nhom="proxy", chay=chay, can_profile=False,
              mo_ta="Test proxy từng acc, ghi Live/Die; cảnh báo trùng dải IP."))
