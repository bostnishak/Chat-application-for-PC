"""
Low-level networking helpers shared by client_gui and test_chat.
Uses length-prefixed binary protocol matching server.py.
"""

import socket
import struct
import threading
from typing import Optional, Callable

ENCODING = "utf-8"


def send_text(sock: socket.socket, message: str) -> bool:
    """Send a length-prefixed text message."""
    try:
        encoded = message.encode(ENCODING)
        header = struct.pack("!I", len(encoded))
        sock.sendall(header + encoded)
        return True
    except Exception:
        return False


def send_binary(sock: socket.socket, header_text: str, data: bytes) -> bool:
    """Send binary packet: 4-byte text-len + text + 4-byte data-len + data."""
    try:
        hdr_enc = header_text.encode(ENCODING)
        packet = (struct.pack("!I", len(hdr_enc)) + hdr_enc +
                  struct.pack("!I", len(data)) + data)
        sock.sendall(packet)
        return True
    except Exception:
        return False


def recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    """Receive exactly n bytes."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def recv_packet(sock: socket.socket):
    """
    Receive one packet. Returns (header_str, binary_data_or_None).
    """
    raw_len = recv_exact(sock, 4)
    if raw_len is None:
        return None, None
    msg_len = struct.unpack("!I", raw_len)[0]
    raw_msg = recv_exact(sock, msg_len)
    if raw_msg is None:
        return None, None
    header = raw_msg.decode(ENCODING)

    if header.startswith("FILE_DATA|") or header.startswith("FILE_SENT|"):
        raw_dlen = recv_exact(sock, 4)
        if raw_dlen is None:
            return header, None
        dlen = struct.unpack("!I", raw_dlen)[0]
        data = recv_exact(sock, dlen)
        return header, data

    return header, None


def connect_and_login(host: str, port: int, action: str, username: str, password: str):
    """
    Connect to server, send action, credentials, return (socket, first_message) or raise.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))

    send_text(sock, action)
    import time; time.sleep(0.05)
    send_text(sock, username)
    time.sleep(0.05)
    send_text(sock, password)

    header, _ = recv_packet(sock)
    if header is None:
        sock.close()
        raise ConnectionError("Server did not respond.")
    if header.startswith("ERROR:USERNAME_TAKEN"):
        sock.close()
        raise PermissionError("USERNAME_TAKEN")
    if header.startswith("ERROR:WRONG_PASS"):
        sock.close()
        raise PermissionError("WRONG_PASS")
    if header.startswith("ERROR:NOT_FOUND"):
        sock.close()
        raise PermissionError("NOT_FOUND")
    if header.startswith("ERROR:ALREADY_EXISTS"):
        sock.close()
        raise PermissionError("ALREADY_EXISTS")

    return sock, header
