
import json
import os
import socket
import struct
import threading
from datetime import datetime
from typing import Callable, Dict, Optional, Set

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
HOST: str = "0.0.0.0"
PORT: int = 5555
BUFFER: int = 65536
ENCODING: str = "utf-8"
MAX_HISTORY: int = 50
MAX_FILE_SIZE: int = 20 * 1024 * 1024  # 20 MB

USERS_FILE: str = os.path.join(os.path.dirname(__file__), "users.json")

# ─────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────
clients: Dict[str, socket.socket] = {}   # {username: socket}
chat_history: list = []                  # last MAX_HISTORY messages
# groups: {group_name: {"creator": str, "members": set}}
groups: Dict[str, dict] = {}
lock: threading.Lock = threading.Lock()
_running: bool = False

# Offline message queue: {username: [packet_str, ...]}
# Stores DMs sent to users who are currently offline.
offline_queue: Dict[str, list] = {}

# Muted users: cannot send messages but can receive.
muted_users: Set[str] = set()

# GUI callback hooks (set by server_gui.py)
on_user_join:    Optional[Callable[[str], None]] = None
on_user_leave:   Optional[Callable[[str], None]] = None
on_message:      Optional[Callable[[str], None]] = None
on_log:          Optional[Callable[[str], None]] = None
on_group_update: Optional[Callable[[], None]] = None
on_mute_update:  Optional[Callable[[], None]] = None

# ─────────────────────────────────────────────
# User Account Storage
# ─────────────────────────────────────────────
def _load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_users(users: dict) -> None:
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
    except Exception:
        pass


def _authenticate(action: str, username: str, password: str) -> str:
    users = _load_users()
    if action == "LOGIN":
        if username not in users:
            return "NOT_FOUND"
        if users[username] == password:
            return "OK"
        return "WRONG_PASS"
    elif action == "REGISTER":
        if username in users:
            return "ALREADY_EXISTS"
        users[username] = password
        _save_users(users)
        _log(f"[AUTH] New user registered: {username}")
        return "OK"
    return "UNKNOWN_ACTION"


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def _timestamp() -> str:
    return datetime.now().strftime("%H:%M")


def _log(msg: str) -> None:
    print(msg)
    try:
        if on_log is not None:
            on_log(msg)
    except Exception:
        pass


def _add_to_history(msg: str) -> None:
    with lock:
        chat_history.append(msg)
        if len(chat_history) > MAX_HISTORY:
            chat_history.pop(0)


# ─────────────────────────────────────────────
# Low-level send helpers
# ─────────────────────────────────────────────
def _send_text(sock: socket.socket, message: str) -> bool:
    """Send a length-prefixed text message."""
    try:
        encoded = message.encode(ENCODING)
        header = struct.pack("!I", len(encoded))
        sock.sendall(header + encoded)
        return True
    except Exception:
        return False


def _send_binary(sock: socket.socket, header_text: str, data: bytes) -> bool:
    """Send a binary packet: 4-byte text-len + text header + 4-byte data-len + data."""
    try:
        hdr_enc = header_text.encode(ENCODING)
        packet = struct.pack("!I", len(hdr_enc)) + hdr_enc + struct.pack("!I", len(data)) + data
        sock.sendall(packet)
        return True
    except Exception:
        return False


def _recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    """Receive exactly n bytes."""
    buf = b""
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        except Exception:
            return None
    return buf


def recv_packet(sock: socket.socket):
    """
    Receive one packet. Returns (header: str, data: bytes | None).
    For text-only packets, data is None.
    """
    raw_len = _recv_exact(sock, 4)
    if raw_len is None:
        return None, None
    msg_len = struct.unpack("!I", raw_len)[0]
    raw_msg = _recv_exact(sock, msg_len)
    if raw_msg is None:
        return None, None
    header = raw_msg.decode(ENCODING)

    # Check if a binary payload follows
    if header.startswith("FILE_DATA|"):
        raw_dlen = _recv_exact(sock, 4)
        if raw_dlen is None:
            return header, None
        dlen = struct.unpack("!I", raw_dlen)[0]
        data = _recv_exact(sock, dlen)
        return header, data

    return header, None


# ─────────────────────────────────────────────
# Core networking
# ─────────────────────────────────────────────
def broadcast_text(message: str, exclude: Optional[str] = None) -> None:
    with lock:
        targets = list(clients.items())
    for username, sock in targets:
        if username == exclude:
            continue
        try:
            _send_text(sock, message)
        except Exception:
            _remove_client(username)


# keep old name for backward compat
def broadcast(message: str, exclude: Optional[str] = None) -> None:
    broadcast_text(message, exclude)


def broadcast_admin(message: str) -> None:
    ts = _timestamp()
    full = f"ANNOUNCE|[{ts}]|Admin|{message}"
    _log(f"[ANNOUNCE] {message}")
    broadcast_text(full)


def send_user_list() -> None:
    with lock:
        usernames = list(clients.keys())
        sockets   = list(clients.values())
    msg = "USERLIST:" + ",".join(usernames)
    for sock in sockets:
        try:
            _send_text(sock, msg)
        except Exception:
            pass


def send_group_list(target_sock: Optional[socket.socket] = None) -> None:
    """Send current group list to one socket or all connected clients."""
    with lock:
        group_data = {
            name: {"creator": info["creator"], "members": list(info["members"])}
            for name, info in groups.items()
        }
        all_socks = list(clients.values()) if target_sock is None else [target_sock]

    msg = "GROUPLIST:" + json.dumps(group_data)
    for sock in all_socks:
        try:
            _send_text(sock, msg)
        except Exception:
            pass


def send_history(client_socket: socket.socket) -> None:
    with lock:
        history_copy = list(chat_history)
    for msg in history_copy:
        try:
            _send_text(client_socket, f"HISTORY|{msg}")
        except Exception:
            break


def _remove_client(username: str) -> None:
    with lock:
        sock = clients.pop(username, None)
    if sock is not None:
        try:
            sock.close()
        except Exception:
            pass


def _send_private(sender: str, recipient: str, body: str) -> None:
    ts = _timestamp()
    with lock:
        recv_sock = clients.get(recipient)
        send_sock = clients.get(sender)

    if recv_sock is None:
        # ── Recipient offline: queue the message ──────────────────
        with lock:
            offline_queue.setdefault(recipient, []).append(
                f"DM|[{ts}]|{sender}|{body}"
            )
        _log(f"  [QUEUE] DM from {sender} queued for offline user '{recipient}'")
        if send_sock:
            _send_text(
                send_sock,
                f"SYSTEM|[{ts}]|System|📨  '{recipient}' is offline. Message queued.",
            )
        if send_sock:
            _send_text(send_sock, f"DM_SENT|[{ts}]|{recipient}|{body}")
        return

    _send_text(recv_sock, f"DM|[{ts}]|{sender}|{body}")
    if send_sock:
        _send_text(send_sock, f"DM_SENT|[{ts}]|{recipient}|{body}")
    _log(f"  [DM] {sender} → {recipient}: {body}")


def _deliver_offline_queue(username: str) -> None:
    """Deliver any queued messages to a user who has just come online."""
    with lock:
        pending = offline_queue.pop(username, [])
        sock = clients.get(username)
    if not pending or sock is None:
        return
    ts = _timestamp()
    _send_text(sock, f"SYSTEM|[{ts}]|System|📬  You have {len(pending)} queued message(s):")
    for packet in pending:
        try:
            _send_text(sock, packet)
        except Exception:
            break
    _log(f"  [QUEUE] Delivered {len(pending)} queued message(s) to {username}")


def _relay_file(sender: str, recipient: str, filename: str, data: bytes, is_group: bool = False) -> None:
    """Relay a binary file to recipient(s)."""
    ts = _timestamp()
    fsize = len(data)
    header = f"FILE_DATA|[{ts}]|{sender}|{recipient}|{filename}|{fsize}"

    if is_group:
        # recipient is a group name
        with lock:
            members = set(groups.get(recipient, {}).get("members", set()))
            targets = [(u, s) for u, s in clients.items() if u in members and u != sender]
            send_sock = clients.get(sender)

        for _uname, sock in targets:
            try:
                _send_binary(sock, header, data)
            except Exception:
                pass
        # echo to sender
        if send_sock:
            sent_hdr = f"FILE_SENT|[{ts}]|{sender}|{recipient}|{filename}|{fsize}"
            try:
                _send_binary(send_sock, sent_hdr, data)
            except Exception:
                pass
    else:
        with lock:
            recv_sock = clients.get(recipient)
            send_sock = clients.get(sender)

        if recv_sock is None:
            if send_sock:
                _send_text(send_sock, f"SYSTEM|[{ts}]|System|⚠  '{recipient}' is not online.")
            return

        try:
            _send_binary(recv_sock, header, data)
        except Exception:
            pass
        if send_sock:
            sent_hdr = f"FILE_SENT|[{ts}]|{sender}|{recipient}|{filename}|{fsize}"
            try:
                _send_binary(send_sock, sent_hdr, data)
            except Exception:
                pass

    _log(f"  [FILE] {sender} → {recipient}: {filename} ({fsize} bytes)")


# ─────────────────────────────────────────────
# Group management
# ─────────────────────────────────────────────
def _create_group(creator: str, group_name: str) -> str:
    with lock:
        if group_name in groups:
            return "EXISTS"
        groups[group_name] = {"creator": creator, "members": {creator}}
    _log(f"[GROUP] {creator} created group '{group_name}'")
    ts = _timestamp()
    broadcast_text(f"SYSTEM|[{ts}]|System|📢 New group created: '{group_name}' by {creator}")
    send_group_list()
    if on_group_update:
        try:
            on_group_update()
        except Exception:
            pass
    return "OK"


def _join_group(username: str, group_name: str) -> str:
    with lock:
        if group_name not in groups:
            return "NOT_FOUND"
        groups[group_name]["members"].add(username)
    _log(f"[GROUP] {username} joined '{group_name}'")
    ts = _timestamp()
    _send_group_msg("System", group_name, f"{username} joined the group 👋", system=True)
    send_group_list()
    if on_group_update:
        try:
            on_group_update()
        except Exception:
            pass
    return "OK"


def _leave_group(username: str, group_name: str) -> None:
    with lock:
        if group_name in groups:
            groups[group_name]["members"].discard(username)
            if not groups[group_name]["members"]:
                del groups[group_name]
    send_group_list()
    if on_group_update:
        try:
            on_group_update()
        except Exception:
            pass


def _send_group_msg(sender: str, group_name: str, body: str, system: bool = False) -> None:
    ts = _timestamp()
    with lock:
        group = groups.get(group_name)
        if group is None:
            return
        members = set(group["members"])
        targets = [(u, s) for u, s in clients.items() if u in members]

    if system:
        payload = f"GROUP_MSG|[{ts}]|{group_name}|System|{body}"
    else:
        payload = f"GROUP_MSG|[{ts}]|{group_name}|{sender}|{body}"

    for uname, sock in targets:
        try:
            _send_text(sock, payload)
        except Exception:
            pass

    if not system:
        _add_to_history(payload)
        _log(f"  [GROUP:{group_name}] {sender}: {body}")
        if on_message:
            try:
                on_message(f"[{group_name}] {sender}: {body}")
            except Exception:
                pass


# ─────────────────────────────────────────────
# Admin actions
# ─────────────────────────────────────────────
def kick_user(username: str) -> bool:
    with lock:
        sock = clients.pop(username, None)
    if sock is None:
        return False
    try:
        _send_text(sock, f"SYSTEM|[{_timestamp()}]|System|You have been kicked by the admin.")
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass
    _log(f"[KICK] {username} was kicked by admin")
    broadcast_text(f"SYSTEM|[{_timestamp()}]|System|{username} was kicked by the admin.")
    send_user_list()
    if on_user_leave is not None:
        try:
            on_user_leave(username)
        except Exception:
            pass
    return True


def mute_user(username: str) -> bool:
    """Mute a user — they can receive but not send messages. Returns False if already muted."""
    if username in muted_users:
        return False
    muted_users.add(username)
    _log(f"[MUTE] {username} was muted by admin")
    ts = _timestamp()
    with lock:
        sock = clients.get(username)
    if sock:
        _send_text(sock, f"SYSTEM|[{ts}]|System|🔇  You have been muted by an admin.")
    broadcast_text(f"SYSTEM|[{ts}]|System|🔇  {username} has been muted.")
    if on_mute_update is not None:
        try:
            on_mute_update()
        except Exception:
            pass
    return True


def unmute_user(username: str) -> bool:
    """Unmute a user. Returns False if they were not muted."""
    if username not in muted_users:
        return False
    muted_users.discard(username)
    _log(f"[UNMUTE] {username} was unmuted by admin")
    ts = _timestamp()
    with lock:
        sock = clients.get(username)
    if sock:
        _send_text(sock, f"SYSTEM|[{ts}]|System|🔊  You have been unmuted by an admin.")
    if on_mute_update is not None:
        try:
            on_mute_update()
        except Exception:
            pass
    return True

# ─────────────────────────────────────────────
# Client handler
# ─────────────────────────────────────────────
def handle_client(client_socket: socket.socket, address: tuple) -> None:
    username: Optional[str] = None

    try:
        # Step 1: Receive Action (LOGIN or REGISTER)
        _, _ = None, None
        raw_len = _recv_exact(client_socket, 4)
        if not raw_len:
            client_socket.close(); return
        msg_len = struct.unpack("!I", raw_len)[0]
        raw_msg = _recv_exact(client_socket, msg_len)
        if not raw_msg:
            client_socket.close(); return
        action = raw_msg.decode(ENCODING).strip()

        # Step 2: Receive username
        raw_len = _recv_exact(client_socket, 4)
        if not raw_len:
            client_socket.close(); return
        msg_len = struct.unpack("!I", raw_len)[0]
        raw_msg = _recv_exact(client_socket, msg_len)
        if not raw_msg:
            client_socket.close(); return
        username = raw_msg.decode(ENCODING).strip()

        # Step 3: Receive password
        raw_len = _recv_exact(client_socket, 4)
        if not raw_len:
            client_socket.close(); return
        msg_len = struct.unpack("!I", raw_len)[0]
        raw_msg = _recv_exact(client_socket, msg_len)
        if not raw_msg:
            client_socket.close(); return
        password = raw_msg.decode(ENCODING).strip()

        # Step 4: Authenticate
        auth_result = _authenticate(action, username, password)
        if auth_result != "OK":
            _send_text(client_socket, f"ERROR:{auth_result}")
            client_socket.close()
            return

        # Step 5: Check duplicate
        with lock:
            if username in clients:
                _send_text(client_socket, "ERROR:USERNAME_TAKEN")
                client_socket.close()
                return
            clients[username] = client_socket

        _log(f"[+] {username} connected from {address}")
        send_history(client_socket)
        send_group_list(client_socket)

        ts = _timestamp()
        broadcast_text(f"SYSTEM|[{ts}]|System|{username} has joined the chat! 👋", exclude=username)
        _send_text(client_socket, f"SYSTEM|[{ts}]|System|Welcome to the chat, {username}! 🎉")
        send_user_list()

        # Deliver any queued offline messages
        _deliver_offline_queue(username)

        # Notify if muted
        if username in muted_users:
            _send_text(client_socket, f"SYSTEM|[{ts}]|System|🔇  You are currently muted by an admin.")

        if on_user_join is not None:
            try:
                on_user_join(username)
            except Exception:
                pass

        # Step 5: Main receive loop
        while True:
            header, data = recv_packet(client_socket)
            if header is None:
                break

            message = header.strip()
            if not message:
                continue

            # ── File transfer ──────────────────────
            if message.startswith("FILE_DATA|"):
                if username in muted_users:
                    ts_m = _timestamp()
                    _send_text(client_socket, f"SYSTEM|[{ts_m}]|System|🔇  You are muted and cannot send files.")
                    continue
                parts = message.split("|", 3)
                if len(parts) >= 3 and data is not None:
                    _, recipient, filename = parts[0], parts[1], parts[2]
                    is_group = recipient in groups
                    _relay_file(username, recipient, filename, data, is_group=is_group)
                continue

            # ── Group commands ─────────────────────
            if message.startswith("GROUP_CREATE|"):
                group_name = message.removeprefix("GROUP_CREATE|").strip()
                result = _create_group(username, group_name)
                _send_text(client_socket, f"GROUP_RESULT|CREATE|{result}|{group_name}")
                continue

            if message.startswith("GROUP_JOIN|"):
                group_name = message.removeprefix("GROUP_JOIN|").strip()
                result = _join_group(username, group_name)
                _send_text(client_socket, f"GROUP_RESULT|JOIN|{result}|{group_name}")
                continue

            if message.startswith("GROUP_LEAVE|"):
                group_name = message.removeprefix("GROUP_LEAVE|").strip()
                _leave_group(username, group_name)
                continue

            if message.startswith("GROUP_MSG|"):
                if username in muted_users:
                    ts_m = _timestamp()
                    _send_text(client_socket, f"SYSTEM|[{ts_m}]|System|🔇  You are muted and cannot send messages.")
                    continue
                parts = message.split("|", 2)
                if len(parts) == 3:
                    _, group_name, body = parts
                    _send_group_msg(username, group_name, body)
                continue

            # ── Private message ────────────────────
            if message.startswith("@"):
                if username in muted_users:
                    ts_m = _timestamp()
                    _send_text(client_socket, f"SYSTEM|[{ts_m}]|System|🔇  You are muted and cannot send messages.")
                    continue
                parts = message.removeprefix("@").split(" ", 1)
                if len(parts) == 2:
                    _send_private(username, parts[0], parts[1])
                continue

            # ── Broadcast message ──────────────────
            if username in muted_users:
                ts_m = _timestamp()
                _send_text(client_socket, f"SYSTEM|[{ts_m}]|System|🔇  You are muted and cannot send messages.")
                continue

            ts = _timestamp()
            payload = f"MSG|[{ts}]|{username}|{message}"
            formatted_log = f"[{ts}] {username}: {message}"
            _log(f"  [{address[0]}] {formatted_log}")
            _add_to_history(payload)

            if on_message is not None:
                try:
                    on_message(formatted_log)
                except Exception:
                    pass

            _send_text(client_socket, payload)
            broadcast_text(payload, exclude=username)

    except ConnectionResetError:
        pass
    except OSError:
        pass
    except Exception as e:
        _log(f"[!] Error with {username or address}: {e}")
    finally:
        if username is not None:
            with lock:
                clients.pop(username, None)
            _log(f"[-] {username} disconnected")
            ts = _timestamp()
            broadcast_text(f"SYSTEM|[{ts}]|System|{username} has left the chat.")
            send_user_list()
            if on_user_leave is not None:
                try:
                    on_user_leave(username)
                except Exception:
                    pass
        try:
            client_socket.close()
        except Exception:
            pass


# ─────────────────────────────────────────────
# Server startup / stop
# ─────────────────────────────────────────────
_server_socket: Optional[socket.socket] = None


def start(host: str = HOST, port: int = PORT) -> None:
    global _server_socket, _running

    _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        _server_socket.bind((host, port))
    except OSError as e:
        _log(f"[ERROR] Cannot bind to {host}:{port} — {e}")
        return

    _server_socket.listen(20)
    _running = True

    _log("=" * 50)
    _log("  WhatsApp-like Chat Application - SERVER")
    _log("=" * 50)
    _log(f"  Listening on  : {host}:{port}")
    _log(f"  Buffer size   : {BUFFER} bytes")
    _log(f"  Max file size : {MAX_FILE_SIZE // (1024*1024)} MB")
    _log(f"  History limit : {MAX_HISTORY} messages")
    _log("=" * 50)

    try:
        while _running:
            try:
                client_socket, address = _server_socket.accept()
            except OSError:
                break
            t = threading.Thread(target=handle_client, args=(client_socket, address), daemon=True)
            t.start()
    except KeyboardInterrupt:
        _log("\n[!] Server shutting down...")
    finally:
        _cleanup()


def stop() -> None:
    global _running
    _running = False
    if _server_socket is not None:
        try:
            _server_socket.close()
        except Exception:
            pass
    _cleanup()


def _cleanup() -> None:
    global _server_socket
    with lock:
        for sock in clients.values():
            try:
                _send_text(sock, f"SYSTEM|[{_timestamp()}]|System|Server is shutting down.")
                sock.close()
            except Exception:
                pass
        clients.clear()
    _server_socket = None


if __name__ == "__main__":
    start()
