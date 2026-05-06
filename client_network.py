"""Network helpers shared by client GUI."""
import socket, struct
from typing import Optional, Tuple

ENCODING = "utf-8"


def send_text(sock: socket.socket, msg: str) -> bool:
    try:
        enc = msg.encode(ENCODING)
        sock.sendall(struct.pack("!I", len(enc)) + enc)
        return True
    except Exception:
        return False


def send_binary(sock: socket.socket, header: str, data: bytes) -> bool:
    try:
        hdr_enc = header.encode(ENCODING)
        sock.sendall(
            struct.pack("!I", len(hdr_enc)) + hdr_enc +
            struct.pack("!I", len(data)) + data
        )
        return True
    except Exception:
        return False


def recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def recv_packet(sock: socket.socket) -> Tuple[Optional[str], Optional[bytes]]:
    """Returns (header_str, binary_data_or_None)."""
    raw = recv_exact(sock, 4)
    if not raw:
        return None, None
    raw_msg = recv_exact(sock, struct.unpack("!I", raw)[0])
    if not raw_msg:
        return None, None
    header = raw_msg.decode(ENCODING)
    if header.startswith("FILE_DATA|") or header.startswith("FILE_SENT|"):
        raw_dlen = recv_exact(sock, 4)
        if not raw_dlen:
            return header, None
        dlen = struct.unpack("!I", raw_dlen)[0]
        data = recv_exact(sock, dlen)
        return header, data
    return header, None


def connect_and_login(
    host: str, port: int, action: str, username: str, password: str
) -> Tuple[socket.socket, str]:
    """Connect, authenticate, return (socket, first_packet). Raises on failure."""
    import time
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(8)
    sock.connect((host, port))
    sock.settimeout(None)

    send_text(sock, action)
    time.sleep(0.05)
    send_text(sock, username)
    time.sleep(0.05)
    send_text(sock, password)

    header, _ = recv_packet(sock)
    if header is None:
        sock.close()
        raise ConnectionError("Server did not respond.")

    err_map = {
        "ERROR:NOT_FOUND": "NOT_FOUND",
        "ERROR:WRONG_PASS": "WRONG_PASS",
        "ERROR:USERNAME_TAKEN": "USERNAME_TAKEN",
        "ERROR:ALREADY_EXISTS": "ALREADY_EXISTS",
    }
    for prefix, code in err_map.items():
        if header.startswith(prefix):
            sock.close()
            raise PermissionError(code)

    return sock, header
