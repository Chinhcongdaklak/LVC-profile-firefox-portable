"""Relay proxy noi bo dat giua Firefox va proxy that.

Firefox chi doc pref proxy luc khoi dong, va no cung khong cho nhung user:pass
vao pref. Nen moi profile duoc tro vao mot cong 127.0.0.1 co dinh do tool mo:

    Firefox --(HTTP proxy, khong auth)--> relay 127.0.0.1:PORT --> proxy that

Relay luon *nghe* theo giao thuc HTTP proxy, con dau ra thi dich sang bat ky
loai upstream nao (HTTP, SOCKS4/5, co hoac khong user/pass, hoac di thang).
Nho vay doi proxy chi la tro lai upstream cua relay: cong khong doi nen Firefox
dang mo van dung duoc ngay, khong can khoi dong lai.
"""

from __future__ import annotations

import base64
import socket
import socketserver
import ssl
import struct
import threading
import time
from typing import Optional

from .proxy import Proxy

BUFFER = 65536
CONNECT_TIMEOUT = 20.0


# ----------------------------------------------------------------------
# Tien ich socket
# ----------------------------------------------------------------------
def _pipe(src: socket.socket, dst: socket.socket) -> None:
    """Chuyen tiep du lieu mot chieu cho toi khi dut ket noi."""
    try:
        while True:
            chunk = src.recv(BUFFER)
            if not chunk:
                break
            dst.sendall(chunk)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _bridge(client: socket.socket, upstream: socket.socket) -> None:
    thread = threading.Thread(target=_pipe, args=(client, upstream), daemon=True)
    thread.start()
    _pipe(upstream, client)
    thread.join(timeout=1.0)


def _recv_exactly(sock: socket.socket, count: int) -> bytes:
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError("Ket noi bi dong giua chung.")
        data += chunk
    return data


def _basic_auth(proxy: Proxy) -> bytes:
    token = "{}:{}".format(proxy.username, proxy.password).encode("utf-8")
    return base64.b64encode(token)


def _split_host_port(authority: str, default_port: int) -> tuple[str, int]:
    """Tach 'host:port' ke ca dang IPv6 '[::1]:443'."""
    if authority.startswith("["):
        host, _, rest = authority.partition("]")
        host = host[1:]
        port = rest.lstrip(":")
        return host, int(port) if port.isdigit() else default_port
    host, _, port = authority.rpartition(":")
    if not host:  # khong co dau hai cham
        return authority, default_port
    return host, int(port) if port.isdigit() else default_port


def _socks_connect(sock: socket.socket, proxy: Proxy, host: str, port: int) -> None:
    """Bat tay SOCKS (kem user/pass neu co) roi yeu cau CONNECT toi host:port."""
    if proxy.scheme == "socks4":
        user = proxy.username.encode("utf-8")
        # SOCKS4a: dia chi 0.0.0.x bao hieu "hay tu phan giai ten mien nay".
        sock.sendall(
            b"\x04\x01" + struct.pack(">H", port) + b"\x00\x00\x00\x01"
            + user + b"\x00" + host.encode("idna") + b"\x00"
        )
        reply = _recv_exactly(sock, 8)
        if reply[1] != 0x5A:
            raise ConnectionError(f"SOCKS4 tu choi (ma {reply[1]}).")
        return

    sock.sendall(b"\x05\x02\x00\x02" if proxy.needs_auth else b"\x05\x01\x00")
    method = _recv_exactly(sock, 2)[1]
    if method == 0x02:
        user = proxy.username.encode("utf-8")
        password = proxy.password.encode("utf-8")
        sock.sendall(b"\x01" + bytes([len(user)]) + user + bytes([len(password)]) + password)
        if _recv_exactly(sock, 2)[1] != 0x00:
            raise ConnectionError("SOCKS5 tu choi user/pass.")
    elif method != 0x00:
        raise ConnectionError("SOCKS5 khong chap nhan phuong thuc xac thuc nao.")

    target = host.encode("idna")
    sock.sendall(b"\x05\x01\x00\x03" + bytes([len(target)]) + target + struct.pack(">H", port))
    reply = _recv_exactly(sock, 4)
    if reply[3] == 0x01:
        _recv_exactly(sock, 4)
    elif reply[3] == 0x03:
        _recv_exactly(sock, _recv_exactly(sock, 1)[0])
    elif reply[3] == 0x04:
        _recv_exactly(sock, 16)
    _recv_exactly(sock, 2)
    if reply[1] != 0x00:
        raise ConnectionError(f"SOCKS5 bao loi ma {reply[1]}.")


# ----------------------------------------------------------------------
# Relay
# ----------------------------------------------------------------------
class _HttpProxyHandler(socketserver.BaseRequestHandler):
    """Nhan yeu cau HTTP proxy tu Firefox roi day ra upstream dang hien hanh."""

    def handle(self) -> None:
        relay: "RelayServer" = self.server.relay
        client: socket.socket = self.request
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        try:
            head, leftover = self._read_head(client)
        except OSError:
            return
        if not head:
            return

        lines = head.split(b"\r\n")
        request_line = lines[0]
        headers = lines[1:]
        pieces = request_line.split()
        if len(pieces) < 3:
            return
        method, target = pieces[0], pieces[1].decode("latin-1")
        is_connect = method.upper() == b"CONNECT"

        # Upstream duoc doc mot lan cho ca ket noi nay; doi proxy se dong
        # cac ket noi cu nen lan sau Firefox mo lai bang upstream moi.
        proxy = relay.upstream
        try:
            if proxy.enabled and not proxy.is_socks:
                self._via_http_proxy(client, proxy, request_line, headers, leftover, is_connect, relay)
            else:
                self._via_socks_or_direct(client, proxy, target, headers, leftover, is_connect, relay, pieces[0])
        except (OSError, ConnectionError, ValueError, struct.error, IndexError) as exc:
            self._fail(client, is_connect, str(exc))

    # -- duong di 1: upstream la HTTP proxy -----------------------------
    def _via_http_proxy(self, client, proxy, request_line, headers, leftover, is_connect, relay):
        clean = [h for h in headers if h and not h.lower().startswith(b"proxy-authorization:")]
        if proxy.needs_auth:
            clean.append(b"Proxy-Authorization: Basic " + _basic_auth(proxy))
        if not is_connect:
            # Header auth chi gan duoc cho request dau tien, nen dong ket noi sau
            # khi xong de request ke tiep khong bi upstream tra ve 407.
            drop = (b"connection:", b"proxy-connection:")
            clean = [h for h in clean if not h.lower().startswith(drop)]
            clean.append(b"Connection: close")

        upstream = socket.create_connection((proxy.host, proxy.port), timeout=CONNECT_TIMEOUT)
        upstream.settimeout(None)
        upstream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with upstream:
            relay.track(client, upstream)
            try:
                upstream.sendall(b"\r\n".join([request_line] + clean) + b"\r\n\r\n")
                if leftover:
                    upstream.sendall(leftover)
                _bridge(client, upstream)
            finally:
                relay.untrack(client, upstream)

    # -- duong di 2: upstream la SOCKS, hoac di thang --------------------
    def _via_socks_or_direct(self, client, proxy, target, headers, leftover, is_connect, relay, method):
        if is_connect:
            host, port = _split_host_port(target, 443)
            path = ""
        else:
            host, port, path = self._parse_absolute_uri(target)

        upstream = socket.create_connection(
            (proxy.host, proxy.port) if proxy.enabled else (host, port),
            timeout=CONNECT_TIMEOUT,
        )
        upstream.settimeout(None)
        upstream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with upstream:
            relay.track(client, upstream)
            try:
                if proxy.enabled:
                    _socks_connect(upstream, proxy, host, port)

                if is_connect:
                    client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                    if leftover:
                        upstream.sendall(leftover)
                else:
                    # Doi tu dang tuyet doi ('GET http://host/x') sang dang goc
                    # ('GET /x') vi gio dang noi thang toi may chu dich.
                    drop = (b"connection:", b"proxy-connection:")
                    clean = [h for h in headers if h and not h.lower().startswith(drop)]
                    clean.append(b"Connection: close")
                    rebuilt = method + b" " + path.encode("latin-1") + b" HTTP/1.1"
                    upstream.sendall(b"\r\n".join([rebuilt] + clean) + b"\r\n\r\n")
                    if leftover:
                        upstream.sendall(leftover)

                _bridge(client, upstream)
            finally:
                relay.untrack(client, upstream)

    @staticmethod
    def _parse_absolute_uri(target: str) -> tuple[str, int, str]:
        scheme, _, rest = target.partition("://")
        if not rest:
            raise ValueError(f"Khong doc duoc dia chi: {target}")
        authority, slash, tail = rest.partition("/")
        if "@" in authority:
            authority = authority.rpartition("@")[2]
        host, port = _split_host_port(authority, 443 if scheme == "https" else 80)
        return host, port, (slash + tail) or "/"

    @staticmethod
    def _fail(client: socket.socket, is_connect: bool, detail: str) -> None:
        try:
            if is_connect:
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            else:
                body = detail.encode("utf-8", "replace")[:400]
                client.sendall(
                    b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain; charset=utf-8\r\n"
                    + b"Content-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n"
                    + body
                )
        except OSError:
            pass

    @staticmethod
    def _read_head(client: socket.socket) -> tuple[bytes, bytes]:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = client.recv(BUFFER)
            if not chunk:
                return b"", b""
            data += chunk
            if len(data) > 128 * 1024:
                return b"", b""
        head, _, leftover = data.partition(b"\r\n\r\n")
        return head, leftover


class _ThreadedServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    relay: "RelayServer"


class RelayServer:
    """Mot relay dang chay. Upstream co the doi bat cu luc nao ma cong khong doi."""

    def __init__(self, upstream: Proxy, host: str = "127.0.0.1", port: int = 0):
        self._upstream = upstream
        self._lock = threading.Lock()
        self._sockets: set[socket.socket] = set()

        self._server = _ThreadedServer((host, port), _HttpProxyHandler)
        self._server.relay = self
        self.port: int = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.3},
            daemon=True,
        )

    @property
    def upstream(self) -> Proxy:
        with self._lock:
            return self._upstream

    def retarget(self, upstream: Proxy) -> None:
        """Doi proxy that. Cac ket noi dang mo bi cat de trinh duyet noi lai ngay."""
        with self._lock:
            if self._upstream == upstream:
                return
            self._upstream = upstream
            sockets = list(self._sockets)
            self._sockets.clear()
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def track(self, *sockets: socket.socket) -> None:
        with self._lock:
            self._sockets.update(sockets)

    def untrack(self, *sockets: socket.socket) -> None:
        with self._lock:
            self._sockets.difference_update(sockets)

    def start(self) -> int:
        self._thread.start()
        return self.port

    def stop(self) -> None:
        try:
            self._server.shutdown()
            self._server.server_close()
        except OSError:
            pass


class RelayManager:
    """Quan ly relay theo tung acc, moi acc mot cong rieng va giu nguyen cong do."""

    def __init__(self) -> None:
        self._relays: dict[str, RelayServer] = {}
        self._lock = threading.Lock()

    def ensure(self, account_id: str, upstream: Proxy) -> int:
        """Bao dam co relay cho acc va tra ve cong tren 127.0.0.1.

        Neu relay da chay thi chi tro lai upstream -- cong giu nguyen de Firefox
        dang mo khong bi mat ket noi.
        """
        with self._lock:
            relay = self._relays.get(account_id)
        if relay is not None:
            relay.retarget(upstream)
            return relay.port

        relay = RelayServer(upstream)
        relay.start()
        with self._lock:
            self._relays[account_id] = relay
        return relay.port

    def get_port(self, account_id: str) -> Optional[int]:
        relay = self._relays.get(account_id)
        return relay.port if relay else None

    def stop(self, account_id: str) -> None:
        with self._lock:
            relay = self._relays.pop(account_id, None)
        if relay:
            relay.stop()

    def stop_all(self) -> None:
        with self._lock:
            relays = list(self._relays.values())
            self._relays.clear()
        for relay in relays:
            relay.stop()

    def active_ids(self) -> list[str]:
        with self._lock:
            return list(self._relays)


# ----------------------------------------------------------------------
# Goi HTTP di qua proxy (dung cho kiem tra proxy va dò vi tri IP)
# ----------------------------------------------------------------------
def open_tunnel(proxy: Proxy, host: str, port: int, timeout: float = 12.0) -> socket.socket:
    """Mo mot ket noi TCP toi ``host:port`` qua ``proxy`` (khong co proxy thi noi thang)."""
    if not proxy.enabled:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(timeout)
        return sock

    sock = socket.create_connection((proxy.host, proxy.port), timeout=timeout)
    sock.settimeout(timeout)
    try:
        if proxy.is_socks:
            _socks_connect(sock, proxy, host, port)
        else:
            request = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n"
            if proxy.needs_auth:
                request += "Proxy-Authorization: Basic " + _basic_auth(proxy).decode() + "\r\n"
            sock.sendall((request + "\r\n").encode("ascii"))
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = sock.recv(BUFFER)
                if not chunk:
                    raise ConnectionError("Proxy đóng kết nối khi đang mở tunnel.")
                head += chunk
            status = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
            if " 200 " not in status:
                raise ConnectionError(f"Proxy từ chối CONNECT: {status}")
    except Exception:
        sock.close()
        raise
    return sock


def http_request(
    proxy: Proxy,
    host: str,
    path: str,
    tls: bool = False,
    timeout: float = 12.0,
    limit: int = 65536,
) -> tuple[int, bytes]:
    """Goi GET toi ``host``/``path`` qua proxy. Tra ve ``(ma_trang_thai, than)``."""
    port = 443 if tls else 80
    direct_http_proxy = proxy.enabled and not proxy.is_socks and not tls

    if direct_http_proxy:
        # Proxy HTTP xu ly duoc request dang tuyet doi, khong can dung tunnel.
        sock = socket.create_connection((proxy.host, proxy.port), timeout=timeout)
        sock.settimeout(timeout)
        target = f"http://{host}{path}"
        headers = f"Proxy-Authorization: Basic {_basic_auth(proxy).decode()}\r\n" if proxy.needs_auth else ""
    else:
        sock = open_tunnel(proxy, host, port, timeout)
        target = path
        headers = ""

    try:
        if tls:
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)
            sock.settimeout(timeout)

        sock.sendall(
            (
                f"GET {target} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                f"{headers}"
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\r\n"
                "Accept: */*\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
        )
        response = b""
        while len(response) < limit:
            chunk = sock.recv(BUFFER)
            if not chunk:
                break
            response += chunk
    finally:
        try:
            sock.close()
        except OSError:
            pass

    head, _, body = response.partition(b"\r\n\r\n")
    first = head.split(b"\r\n", 1)[0].split()
    status = int(first[1]) if len(first) > 1 and first[1].isdigit() else 0
    if b"transfer-encoding: chunked" in head.lower():
        body = _dechunk(body)
    return status, body


def _dechunk(body: bytes) -> bytes:
    out = b""
    while True:
        line, _, rest = body.partition(b"\r\n")
        try:
            size = int(line.split(b";")[0], 16)
        except ValueError:
            return out or body
        if size == 0:
            return out
        out += rest[:size]
        body = rest[size:].lstrip(b"\r\n")


# ----------------------------------------------------------------------
# Kiem tra proxy
# ----------------------------------------------------------------------
# Phai la host CO ban ghi IPv6. Nhieu proxy chi ra Internet duoc bang IPv6, luc
# do host chi co IPv4 (api.ipify.org, checkip.amazonaws.com, ipinfo.io...) se bi
# proxy tra ve 502 Bad Gateway va bi hieu nham thanh "proxy hong".
# Thu lan luot, host nao tra loi truoc thi lay.
IP_CHECK_TARGETS = (
    ("icanhazip.com", "/"),
    ("ifconfig.co", "/ip"),
    ("wtfismyip.com", "/text"),
)


def test_proxy(proxy: Proxy, timeout: float = 12.0) -> tuple[bool, str]:
    """Thu di ra Internet qua proxy va lay ve IP that dang dung.

    Tra ve ``(thanh_cong, mo_ta)``.
    """
    if not proxy.enabled:
        return False, "Chưa nhập proxy."

    last: tuple[bool, str] = (False, "Không kiểm tra được.")
    for host, path in IP_CHECK_TARGETS:
        last = _probe(proxy, host, path, timeout)
        if last[0]:
            return last
        # 407 la sai user/pass, thu host khac cung vo ich.
        if "407" in last[1]:
            return last
    return last


def _probe(proxy: Proxy, host: str, path: str, timeout: float) -> tuple[bool, str]:
    started = time.monotonic()
    try:
        sock = socket.create_connection((proxy.host, proxy.port), timeout=timeout)
    except OSError as exc:
        return False, f"Không kết nối được tới {proxy.host}:{proxy.port} ({exc})."

    with sock:
        sock.settimeout(timeout)
        try:
            if proxy.is_socks:
                _socks_connect(sock, proxy, host, 80)
                request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
            else:
                request = f"GET http://{host}{path} HTTP/1.1\r\nHost: {host}\r\n"
                if proxy.needs_auth:
                    request += "Proxy-Authorization: Basic " + _basic_auth(proxy).decode() + "\r\n"
            request += "User-Agent: firefox-profile-manager\r\nConnection: close\r\n\r\n"
            sock.sendall(request.encode("ascii"))

            response = b""
            while len(response) < 8192:
                chunk = sock.recv(BUFFER)
                if not chunk:
                    break
                response += chunk
        except (OSError, ConnectionError, struct.error) as exc:
            return False, str(exc)

    elapsed = int((time.monotonic() - started) * 1000)
    head, _, body = response.partition(b"\r\n\r\n")
    status_line = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
    if b" 407 " in head:
        return False, f"Proxy từ chối user/pass (407). {status_line}"
    if b" 502 " in head or b" 504 " in head:
        # Proxy da nhan user/pass roi (neu khong da la 407), chi la no khong voi
        # toi duoc trang kiem tra.
        return False, (
            f"Proxy nhận user/pass OK nhưng không mở được {host} — {status_line}"
        )
    if b" 200 " not in head:
        return False, f"Proxy trả về: {status_line}"

    ip = body.strip().splitlines()[-1].decode("latin-1", "replace") if body.strip() else "?"
    return True, f"IP ra ngoài: {ip} — {elapsed} ms"
