"""Chat Application Server - v2 Clean"""
import json, os, socket, struct, threading
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set

HOST = "0.0.0.0"
PORT = 5555
ENCODING = "utf-8"
MAX_HISTORY = 50
MAX_FILE_SIZE = 20 * 1024 * 1024
USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")

# ── State ──────────────────────────────────────────────────────────────────────
clients: Dict[str, socket.socket] = {}
chat_history: List[str] = []
groups: Dict[str, dict] = {}        # name -> {creator, members: set}
offline_queue: Dict[str, List[str]] = {}
muted_users: Set[str] = set()
lock = threading.Lock()
_running = False

# ── GUI Callbacks ──────────────────────────────────────────────────────────────
on_user_join: Optional[Callable] = None
on_user_leave: Optional[Callable] = None
on_message: Optional[Callable] = None
on_log: Optional[Callable] = None
on_mute_update: Optional[Callable] = None


# ── Users ──────────────────────────────────────────────────────────────────────
def _load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_users(users: dict) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


def _authenticate(action: str, username: str, password: str) -> str:
    users = _load_users()
    if action == "LOGIN":
        if username not in users:
            return "NOT_FOUND"
        return "OK" if users[username] == password else "WRONG_PASS"
    elif action == "REGISTER":
        if username in users:
            return "ALREADY_EXISTS"
        users[username] = password
        _save_users(users)
        _log(f"[AUTH] Registered: {username}")
        return "OK"
    return "UNKNOWN"


# ── Low-level I/O ──────────────────────────────────────────────────────────────
def _ts() -> str:
    return datetime.now().strftime("%H:%M")


def _log(msg: str) -> None:
    print(msg)
    if on_log:
        try:
            on_log(msg)
        except Exception:
            pass


def _recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def _recv_packet(sock: socket.socket):
    """Returns (header_str, binary_data_or_None)"""
    raw = _recv_exact(sock, 4)
    if not raw:
        return None, None
    raw_msg = _recv_exact(sock, struct.unpack("!I", raw)[0])
    if not raw_msg:
        return None, None
    header = raw_msg.decode(ENCODING)
    if header.startswith("FILE_DATA|"):
        raw_dlen = _recv_exact(sock, 4)
        if not raw_dlen:
            return header, None
        dlen = struct.unpack("!I", raw_dlen)[0]
        if dlen > MAX_FILE_SIZE:
            return header, None
        data = _recv_exact(sock, dlen)
        return header, data
    return header, None


def _send_text(sock: socket.socket, msg: str) -> bool:
    try:
        enc = msg.encode(ENCODING)
        sock.sendall(struct.pack("!I", len(enc)) + enc)
        return True
    except Exception:
        return False


def _send_binary(sock: socket.socket, header: str, data: bytes) -> bool:
    try:
        hdr_enc = header.encode(ENCODING)
        sock.sendall(
            struct.pack("!I", len(hdr_enc)) + hdr_enc +
            struct.pack("!I", len(data)) + data
        )
        return True
    except Exception:
        return False


def _add_history(msg: str) -> None:
    chat_history.append(msg)
    if len(chat_history) > MAX_HISTORY:
        chat_history.pop(0)


# ── Broadcasting ───────────────────────────────────────────────────────────────
def broadcast(msg: str, exclude: str = "") -> None:
    with lock:
        targets = [(u, s) for u, s in clients.items() if u != exclude]
    for _, sock in targets:
        _send_text(sock, msg)


def send_user_list() -> None:
    with lock:
        users = list(clients.keys())
        socks = list(clients.values())
    msg = "USERLIST|" + ",".join(users)
    for sock in socks:
        _send_text(sock, msg)


def send_group_list(sock: Optional[socket.socket] = None) -> None:
    with lock:
        data = {
            g: {"creator": d["creator"], "members": list(d["members"])}
            for g, d in groups.items()
        }
    msg = "GROUPLIST|" + json.dumps(data)
    if sock:
        _send_text(sock, msg)
    else:
        with lock:
            targets = list(clients.values())
        for s in targets:
            _send_text(s, msg)


def send_history(sock: socket.socket) -> None:
    for msg in list(chat_history):
        _send_text(sock, f"HISTORY|{msg}")


# ── DM ─────────────────────────────────────────────────────────────────────────
def _send_dm(sender: str, recipient: str, body: str) -> None:
    ts = _ts()
    with lock:
        recv_sock = clients.get(recipient)
        send_sock = clients.get(sender)

    if recv_sock is None:
        with lock:
            offline_queue.setdefault(recipient, []).append(
                f"DM|[{ts}]|{sender}|{body}"
            )
        _log(f"[QUEUE] DM from {sender} queued for {recipient}")
        if send_sock:
            _send_text(send_sock, f"SYSTEM|[{ts}]|System|📨 '{recipient}' is offline. Message queued.")
            _send_text(send_sock, f"DM_SENT|[{ts}]|{recipient}|{body}")
        return

    _send_text(recv_sock, f"DM|[{ts}]|{sender}|{body}")
    if send_sock:
        _send_text(send_sock, f"DM_SENT|[{ts}]|{recipient}|{body}")
    _log(f"  [DM] {sender} → {recipient}")


def _deliver_queue(username: str) -> None:
    with lock:
        pending = offline_queue.pop(username, [])
        sock = clients.get(username)
    if not pending or not sock:
        return
    ts = _ts()
    _send_text(sock, f"SYSTEM|[{ts}]|System|📬 You have {len(pending)} queued message(s):")
    for pkt in pending:
        _send_text(sock, pkt)


# ── Groups ─────────────────────────────────────────────────────────────────────
def _create_group(creator: str, name: str, members: List[str]) -> str:
    with lock:
        if name in groups:
            return "EXISTS"
        all_members = set(members) | {creator}
        groups[name] = {"creator": creator, "members": all_members}
    ts = _ts()
    with lock:
        online = {u: s for u, s in clients.items() if u in all_members}
    for uname, sock in online.items():
        _send_text(sock, f"GROUP_INVITE|[{ts}]|{name}|{creator}")
    send_group_list()
    _log(f"[GROUP] {creator} created '{name}' with {all_members}")
    return "OK"


def _join_group(username: str, name: str) -> str:
    with lock:
        if name not in groups:
            return "NOT_FOUND"
        groups[name]["members"].add(username)
        members = set(groups[name]["members"])
    ts = _ts()
    with lock:
        online = {u: s for u, s in clients.items() if u in members}
    for sock in online.values():
        _send_text(sock, f"GROUP_MSG|[{ts}]|{name}|System|{username} joined.")
    send_group_list()
    return "OK"


def _leave_group(username: str, name: str) -> None:
    with lock:
        if name not in groups:
            return
        groups[name]["members"].discard(username)
        if not groups[name]["members"]:
            del groups[name]
            send_group_list()
            return
        members = set(groups[name]["members"])
    ts = _ts()
    with lock:
        online = {u: s for u, s in clients.items() if u in members}
    for sock in online.values():
        _send_text(sock, f"GROUP_MSG|[{ts}]|{name}|System|{username} left.")
    send_group_list()


def _send_group_msg(sender: str, name: str, body: str) -> None:
    ts = _ts()
    with lock:
        if name not in groups or sender not in groups[name]["members"]:
            return
        members = set(groups[name]["members"])
        online = {u: s for u, s in clients.items() if u in members}
    payload = f"GROUP_MSG|[{ts}]|{name}|{sender}|{body}"
    for sock in online.values():
        _send_text(sock, payload)
    _add_history(payload)
    _log(f"  [GROUP:{name}] {sender}: {body}")
    if on_message:
        try:
            on_message(f"[{name}] {sender}: {body}")
        except Exception:
            pass


def _relay_file(sender: str, recipient: str, filename: str, data: bytes) -> None:
    ts = _ts()
    is_group = False
    with lock:
        if recipient in groups:
            is_group = True

    if is_group:
        with lock:
            members = set(groups.get(recipient, {}).get("members", set()))
            online = {u: s for u, s in clients.items() if u in members}
        for uname, sock in online.items():
            htype = "FILE_SENT" if uname == sender else "FILE_DATA"
            h = f"{htype}|[{ts}]|{sender}|{recipient}|{filename}|{len(data)}"
            _send_binary(sock, h, data)
    else:
        with lock:
            recv_sock = clients.get(recipient)
            send_sock = clients.get(sender)
        if recv_sock:
            _send_binary(recv_sock, f"FILE_DATA|[{ts}]|{sender}|{recipient}|{filename}|{len(data)}", data)
        if send_sock:
            _send_binary(send_sock, f"FILE_SENT|[{ts}]|{sender}|{recipient}|{filename}|{len(data)}", data)


# ── Admin ──────────────────────────────────────────────────────────────────────
def kick_user(username: str) -> bool:
    with lock:
        sock = clients.pop(username, None)
    if not sock:
        return False
    ts = _ts()
    _send_text(sock, f"SYSTEM|[{ts}]|System|You were kicked by an admin.")
    try:
        sock.close()
    except Exception:
        pass
    broadcast(f"SYSTEM|[{ts}]|System|{username} was kicked.")
    send_user_list()
    if on_user_leave:
        try:
            on_user_leave(username)
        except Exception:
            pass
    _log(f"[KICK] {username}")
    return True


def mute_user(username: str) -> bool:
    if username in muted_users:
        return False
    muted_users.add(username)
    ts = _ts()
    with lock:
        sock = clients.get(username)
    if sock:
        _send_text(sock, f"SYSTEM|[{ts}]|System|🔇 You have been muted by an admin.")
    if on_mute_update:
        try:
            on_mute_update()
        except Exception:
            pass
    _log(f"[MUTE] {username}")
    return True


def unmute_user(username: str) -> bool:
    if username not in muted_users:
        return False
    muted_users.discard(username)
    ts = _ts()
    with lock:
        sock = clients.get(username)
    if sock:
        _send_text(sock, f"SYSTEM|[{ts}]|System|🔊 You have been unmuted.")
    if on_mute_update:
        try:
            on_mute_update()
        except Exception:
            pass
    _log(f"[UNMUTE] {username}")
    return True


def broadcast_admin(text: str) -> None:
    ts = _ts()
    broadcast(f"ANNOUNCE|[{ts}]|Admin|📢 {text}")
    _log(f"[ANNOUNCE] {text}")


# ── Client Handler ─────────────────────────────────────────────────────────────
def handle_client(client_socket: socket.socket, address: tuple) -> None:
    username = None
    try:
        # 1. Action
        raw = _recv_exact(client_socket, 4)
        if not raw:
            client_socket.close(); return
        raw_msg = _recv_exact(client_socket, struct.unpack("!I", raw)[0])
        if not raw_msg:
            client_socket.close(); return
        action = raw_msg.decode(ENCODING).strip()

        # 2. Username
        raw = _recv_exact(client_socket, 4)
        if not raw:
            client_socket.close(); return
        raw_msg = _recv_exact(client_socket, struct.unpack("!I", raw)[0])
        if not raw_msg:
            client_socket.close(); return
        username = raw_msg.decode(ENCODING).strip()

        # 3. Password
        raw = _recv_exact(client_socket, 4)
        if not raw:
            client_socket.close(); return
        raw_msg = _recv_exact(client_socket, struct.unpack("!I", raw)[0])
        if not raw_msg:
            client_socket.close(); return
        password = raw_msg.decode(ENCODING).strip()

        # 4. Authenticate
        result = _authenticate(action, username, password)
        if result != "OK":
            _send_text(client_socket, f"ERROR:{result}")
            client_socket.close()
            return

        # 5. Duplicate check
        with lock:
            if username in clients:
                _send_text(client_socket, "ERROR:USERNAME_TAKEN")
                client_socket.close()
                return
            clients[username] = client_socket

        _log(f"[+] {username} connected from {address[0]}")

        # 6. Send initial data
        send_history(client_socket)
        send_group_list(client_socket)
        ts = _ts()
        broadcast(f"SYSTEM|[{ts}]|System|{username} joined 👋", exclude=username)
        _send_text(client_socket, f"SYSTEM|[{ts}]|System|Welcome, {username}! 🎉")
        send_user_list()
        _deliver_queue(username)

        if username in muted_users:
            _send_text(client_socket, f"SYSTEM|[{ts}]|System|🔇 You are currently muted.")

        if on_user_join:
            try:
                on_user_join(username)
            except Exception:
                pass

        # 7. Main receive loop
        while True:
            header, data = _recv_packet(client_socket)
            if header is None:
                break
            msg = header.strip()
            if not msg:
                continue

            # File
            if msg.startswith("FILE_DATA|"):
                if username in muted_users:
                    _send_text(client_socket, f"SYSTEM|[{_ts()}]|System|🔇 You are muted.")
                    continue
                parts = msg.split("|", 3)
                if len(parts) >= 3 and data is not None:
                    _relay_file(username, parts[1], parts[2], data)
                continue

            # Groups
            if msg.startswith("GROUP_CREATE|"):
                # FORMAT: GROUP_CREATE|name|member1,member2
                parts = msg.split("|", 2)
                gname = parts[1].strip() if len(parts) > 1 else ""
                raw_members = parts[2].strip() if len(parts) > 2 else ""
                member_list = [m.strip() for m in raw_members.split(",") if m.strip()] if raw_members else []
                r = _create_group(username, gname, member_list)
                _send_text(client_socket, f"GROUP_RESULT|CREATE|{r}|{gname}")
                continue

            if msg.startswith("GROUP_JOIN|"):
                gname = msg.split("|", 1)[1].strip()
                r = _join_group(username, gname)
                _send_text(client_socket, f"GROUP_RESULT|JOIN|{r}|{gname}")
                continue

            if msg.startswith("GROUP_LEAVE|"):
                gname = msg.split("|", 1)[1].strip()
                _leave_group(username, gname)
                _send_text(client_socket, f"GROUP_RESULT|LEAVE|OK|{gname}")
                continue

            if msg.startswith("GROUP_MSG|"):
                if username in muted_users:
                    _send_text(client_socket, f"SYSTEM|[{_ts()}]|System|🔇 You are muted.")
                    continue
                parts = msg.split("|", 2)
                if len(parts) == 3:
                    _send_group_msg(username, parts[1], parts[2])
                continue

            # DM
            if msg.startswith("@"):
                if username in muted_users:
                    _send_text(client_socket, f"SYSTEM|[{_ts()}]|System|🔇 You are muted.")
                    continue
                parts = msg[1:].split(" ", 1)
                if len(parts) == 2:
                    _send_dm(username, parts[0], parts[1])
                continue

            # Global broadcast
            if username in muted_users:
                _send_text(client_socket, f"SYSTEM|[{_ts()}]|System|🔇 You are muted.")
                continue

            ts = _ts()
            payload = f"MSG|[{ts}]|{username}|{msg}"
            _add_history(payload)
            _send_text(client_socket, payload)
            broadcast(payload, exclude=username)
            if on_message:
                try:
                    on_message(f"[{ts}] {username}: {msg}")
                except Exception:
                    pass
            _log(f"  [{address[0]}] {username}: {msg}")

    except (ConnectionResetError, OSError):
        pass
    except Exception as e:
        _log(f"[!] Error with {username or address}: {e}")
    finally:
        if username:
            with lock:
                clients.pop(username, None)
            _log(f"[-] {username} disconnected")
            ts = _ts()
            broadcast(f"SYSTEM|[{ts}]|System|{username} left.")
            send_user_list()
            if on_user_leave:
                try:
                    on_user_leave(username)
                except Exception:
                    pass
        try:
            client_socket.close()
        except Exception:
            pass


# ── Server Start/Stop ──────────────────────────────────────────────────────────
def start() -> None:
    global _running
    _running = True
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(50)
    srv.settimeout(1.0)
    _log(f"[SERVER] Listening on {HOST}:{PORT}")
    while _running:
        try:
            client_sock, addr = srv.accept()
            t = threading.Thread(target=handle_client, args=(client_sock, addr), daemon=True)
            t.start()
        except socket.timeout:
            continue
        except Exception:
            break
    srv.close()
    _log("[SERVER] Stopped.")


def stop() -> None:
    global _running
    _running = False
