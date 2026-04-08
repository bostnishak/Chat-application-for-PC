

import json
import os
import socket
import threading
from datetime import datetime
from typing import Callable, Dict, Optional

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
HOST: str = "0.0.0.0"
PORT: int = 5555
BUFFER: int = 4096
ENCODING: str = "utf-8"
MAX_HISTORY: int = 20

# File where registered accounts are stored (JSON)
USERS_FILE: str = os.path.join(os.path.dirname(__file__), "users.json")

# ─────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────
clients: Dict[str, socket.socket] = {}   # {username: socket}
chat_history: list = []                  # last MAX_HISTORY messages
lock: threading.Lock = threading.Lock()
_running: bool = False

# GUI callback hooks (set by server_gui.py)
on_user_join:  Optional[Callable[[str], None]] = None
on_user_leave: Optional[Callable[[str], None]] = None
on_message:    Optional[Callable[[str], None]] = None
on_log:        Optional[Callable[[str], None]] = None

# ─────────────────────────────────────────────
# User Account Storage
# ─────────────────────────────────────────────
def _load_users() -> dict:
    """Load the username→password mapping from disk."""
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_users(users: dict) -> None:
    """Persist the username→password mapping to disk."""
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
    except Exception:
        pass


def _authenticate(username: str, password: str) -> str:
    """
    Validate or register a user.

    Returns
    -------
    "OK"          – Credentials accepted (new or returning user).
    "WRONG_PASS"  – Username exists but password is wrong.
    """
    users = _load_users()
    if username in users:
        if users[username] == password:
            return "OK"
        return "WRONG_PASS"
    # First time → register automatically
    users[username] = password
    _save_users(users)
    _log(f"[AUTH] New user registered: {username}")
    return "OK"


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def _timestamp() -> str:
    return datetime.now().strftime("%H:%M")


def _log(msg: str) -> None:
    """Print to console and notify the GUI (if connected)."""
    print(msg)
    try:
        if on_log is not None:
            on_log(msg)
    except Exception:
        pass  # Never crash the server thread because of a GUI error


def _add_to_history(msg: str) -> None:
    with lock:
        chat_history.append(msg)
        if len(chat_history) > MAX_HISTORY:
            chat_history.pop(0)


# ─────────────────────────────────────────────
# Core networking
# ─────────────────────────────────────────────
def broadcast(message: str, exclude: Optional[str] = None) -> None:
    """Send *message* to every connected client except the excluded username."""
    encoded = message.encode(ENCODING)
    with lock:
        targets = list(clients.items())

    for username, sock in targets:
        if username == exclude:
            continue
        try:
            sock.send(encoded)
        except Exception:
            _remove_client(username)


def broadcast_admin(message: str) -> None:
    """
    Send an admin announcement to every connected client.
    Message format on client side: ANNOUNCE:<text>
    Safe to call from any thread (e.g. the GUI thread).
    """
    ts = _timestamp()
    full = f"ANNOUNCE|[{ts}]|Admin|{message}"
    _log(f"[ANNOUNCE] {message}")
    broadcast(full)


def send_user_list() -> None:
    """Push the current online-user list to every connected client."""
    with lock:
        usernames = list(clients.keys())
        sockets   = list(clients.values())

    msg = ("USERLIST:" + ",".join(usernames)).encode(ENCODING)
    for sock in sockets:
        try:
            sock.send(msg)
        except Exception:
            pass


def send_history(client_socket: socket.socket) -> None:
    """Send the buffered chat history to a newly-connected client."""
    with lock:
        history_copy = list(chat_history)

    for msg in history_copy:
        try:
            client_socket.send((f"HISTORY|{msg}").encode(ENCODING))
        except Exception:
            break


def _remove_client(username: str) -> None:
    """Close and remove a client socket — must NOT be called while holding *lock*."""
    with lock:
        sock = clients.pop(username, None)
    if sock is not None:
        try:
            sock.close()
        except Exception:
            pass


def _send_private(sender: str, recipient: str, body: str) -> None:
    """
    Route a private (DM) message from *sender* to *recipient*.
    Both sender and recipient receive a prefixed message so they
    know it is private.
    """
    ts = _timestamp()
    with lock:
        recv_sock = clients.get(recipient)
        send_sock = clients.get(sender)

    if recv_sock is None:
        # Tell sender the recipient is offline
        if send_sock:
            try:
                send_sock.send(
                    f"SYSTEM|[{ts}]|System|⚠  '{recipient}' is not online.".encode(ENCODING)
                )
            except Exception:
                pass
        return

    dm_to_recipient = f"DM|[{ts}]|{sender}|{body}"
    dm_to_sender    = f"DM_SENT|[{ts}]|{recipient}|{body}"

    try:
        recv_sock.send(dm_to_recipient.encode(ENCODING))
    except Exception:
        pass
    if send_sock:
        try:
            send_sock.send(dm_to_sender.encode(ENCODING))
        except Exception:
            pass

    _log(f"  [DM] {sender} → {recipient}: {body}")


def kick_user(username: str) -> bool:
    """
    Kick *username* from the server.

    Returns True if the user was found and removed, False otherwise.
    This function is safe to call from the GUI thread.
    """
    with lock:
        sock = clients.pop(username, None)

    if sock is None:
        return False  # user already gone

    # Send the kick notice before closing
    try:
        sock.send(f"SYSTEM|[{_timestamp()}]|System|You have been kicked by the admin.".encode(ENCODING))
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass

    _log(f"[KICK] {username} was kicked by admin")
    broadcast(f"SYSTEM|[{_timestamp()}]|System|{username} was kicked by the admin.")
    send_user_list()

    if on_user_leave is not None:
        try:
            on_user_leave(username)
        except Exception:
            pass

    return True


# ─────────────────────────────────────────────
# Client handler
# ─────────────────────────────────────────────
def handle_client(client_socket: socket.socket, address: tuple) -> None:
    """Handle all I/O for a single connected client (runs in its own thread)."""
    username: Optional[str] = None

    try:
        # ── Step 1: Receive username ──────────────
        raw = client_socket.recv(BUFFER)
        if not raw:
            client_socket.close()
            return
        username = raw.decode(ENCODING).strip()

        # ── Step 2: Receive password ──────────────
        raw = client_socket.recv(BUFFER)
        if not raw:
            client_socket.close()
            return
        password = raw.decode(ENCODING).strip()

        # ── Step 3: Authenticate ──────────────────
        auth_result = _authenticate(username, password)
        if auth_result == "WRONG_PASS":
            client_socket.send("ERROR:WRONG_PASS".encode(ENCODING))
            client_socket.close()
            _log(f"[!] Wrong password for '{username}' from {address}")
            return

        # ── Step 4: Check for duplicate login ─────
        with lock:
            if username in clients:
                client_socket.send("ERROR:USERNAME_TAKEN".encode(ENCODING))
                client_socket.close()
                _log(f"[!] Rejected duplicate login: {username}")
                return
            clients[username] = client_socket

        _log(f"[+] {username} connected from {address}")

        send_history(client_socket)

        ts = _timestamp()
        broadcast(f"SYSTEM|[{ts}]|System|{username} has joined the chat! 👋", exclude=username)
        client_socket.send(
            f"SYSTEM|[{ts}]|System|Welcome to the chat, {username}!".encode(ENCODING)
        )
        send_user_list()

        if on_user_join is not None:
            try:
                on_user_join(username)
            except Exception:
                pass

        # ── Step 5: Main receive loop ─────────────
        while True:
            raw = client_socket.recv(BUFFER)
            if not raw:
                break  # client disconnected cleanly

            message: str = raw.decode(ENCODING).strip()
            if not message:
                continue

            # ── Private message (@recipient body) ──
            if message.startswith("@"):
                parts = message.removeprefix("@").split(" ", 1)
                if len(parts) == 2:
                    _send_private(username, parts[0], parts[1])
                    continue
                # malformed DM – fall through to broadcast

            ts = _timestamp()
            formatted_log = f"[{ts}] {username}: {message}"
            payload = f"MSG|[{ts}]|{username}|{message}"
            _log(f"  [{address[0]}] {formatted_log}")
            _add_to_history(payload)

            if on_message is not None:
                try:
                    on_message(formatted_log)
                except Exception:
                    pass

            # Echo back to sender + broadcast to others
            try:
                client_socket.send(payload.encode(ENCODING))
            except Exception:
                break
            broadcast(payload, exclude=username)

    except ConnectionResetError:
        pass  # client disconnected abruptly — normal on Windows
    except OSError:
        pass  # socket closed externally (e.g. server stopped)
    except Exception as e:
        _log(f"[!] Error with {username or address}: {e}")
    finally:
        if username is not None:
            # Remove from dict only if we are still in it
            # (kick_user may have already removed us)
            with lock:
                clients.pop(username, None)

            _log(f"[-] {username} disconnected")
            ts = _timestamp()
            broadcast(f"SYSTEM|[{ts}]|System|{username} has left the chat.")
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
    """Start the chat server (blocking call — run in a background thread)."""
    global _server_socket, _running

    _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        _server_socket.bind((host, port))
    except OSError as e:
        _log(f"[ERROR] Cannot bind to {host}:{port} — {e}")
        return

    _server_socket.listen(10)
    _running = True

    _log("=" * 50)
    _log("  Simple Chat Application - SERVER")
    _log("=" * 50)
    _log(f"  Listening on  : {host}:{port}")
    _log(f"  Buffer size   : {BUFFER} bytes")
    _log(f"  History limit : {MAX_HISTORY} messages")
    _log(f"  Users file    : {USERS_FILE}")
    _log("  Press Ctrl+C to stop the server.")
    _log("=" * 50)

    try:
        while _running:
            try:
                client_socket, address = _server_socket.accept()
            except OSError:
                break  # socket was closed by stop()

            t = threading.Thread(
                target=handle_client,
                args=(client_socket, address),
                daemon=True,
            )
            t.start()
            _log(f"[*] Active connections: {threading.active_count() - 1}")

    except KeyboardInterrupt:
        _log("\n[!] Server shutting down (Ctrl+C)...")
    finally:
        _cleanup()


def stop() -> None:
    """Stop the server gracefully (safe to call from any thread)."""
    global _running
    _running = False

    if _server_socket is not None:
        try:
            _server_socket.close()
        except Exception:
            pass

    _cleanup()


def _cleanup() -> None:
    """Disconnect all clients and clear state."""
    global _server_socket
    with lock:
        for sock in clients.values():
            try:
                sock.send(f"SYSTEM|[{_timestamp()}]|System|Server is shutting down.".encode(ENCODING))
                sock.close()
            except Exception:
                pass
        clients.clear()

    _server_socket = None


if __name__ == "__main__":
    start()
