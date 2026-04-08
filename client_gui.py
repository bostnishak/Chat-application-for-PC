"""
Simple Chat Application - Graphical Client
===========================================
Author  : Chat App Project
Date    : 2026-03-10
Python  : 3.x

Features
--------
- Login with username + password (register on first use)
- Real-time group messaging
- Private messages : type  @username message
- Admin announcements shown in gold colour
- Online user list in sidebar

How to run:
    python client_gui.py
"""

import socket
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext
from typing import List

# ─────────────────────────────────────────────
# Color Palette (Dark Theme)
# ─────────────────────────────────────────────
BG_DARK       = "#1e1e2e"
BG_MID        = "#2a2a3e"
BG_PANEL      = "#252535"
ACCENT        = "#7c6af7"          # Purple accent
ACCENT_HOVER  = "#9a8fff"
TEXT_MAIN     = "#cdd6f4"
TEXT_DIM      = "#6c7086"
TEXT_SYSTEM   = "#a6e3a1"          # Green for system messages
TEXT_OWN      = "#89b4fa"          # Blue for own messages
TEXT_OTHER    = "#f38ba8"          # Pink for others
TEXT_HISTORY  = "#b4a7d6"          # Muted purple for history replay
TEXT_DM       = "#f5c2e7"          # Pale pink for DM received
TEXT_DM_SENT  = "#94e2d5"          # Teal for DM sent
TEXT_ANNOUNCE = "#f9e2af"          # Gold for admin announcements
BTN_BG        = "#7c6af7"
BTN_FG        = "#ffffff"
INPUT_BG      = "#313244"
ONLINE_COLOR  = "#a6e3a1"

FONT_MAIN     = ("Segoe UI", 11)
FONT_BOLD     = ("Segoe UI", 11, "bold")
FONT_TITLE    = ("Segoe UI", 16, "bold")
FONT_SMALL    = ("Segoe UI", 9)
FONT_MSG      = ("Segoe UI", 10)

BUFFER   = 4096
ENCODING = "utf-8"


# ════════════════════════════════════════════════
# LOGIN SCREEN
# ════════════════════════════════════════════════
class LoginScreen(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Chat App – Connect")
        self.configure(bg=BG_DARK)
        self.resizable(False, False)
        # Declare all entry attributes so the type checker knows about them
        self.username_entry: tk.Entry
        self.password_entry: tk.Entry
        self.server_entry:   tk.Entry
        self.port_entry:     tk.Entry
        self._center(420, 500)
        self._build_ui()

    def _center(self, w: int, h: int) -> None:
        self.update_idletasks()
        sw: int = self.winfo_screenwidth()
        sh: int = self.winfo_screenheight()
        x  = (sw - w) // 2
        y  = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self) -> None:
        # ── Header ──────────────────────────────
        hdr = tk.Frame(self, bg=BG_MID, pady=24)
        hdr.pack(fill="x")

        tk.Label(
            hdr, text="💬  ChatApp",
            font=FONT_TITLE, fg=ACCENT, bg=BG_MID
        ).pack()

        tk.Label(
            hdr, text="Connect to a chat server",
            font=FONT_SMALL, fg=TEXT_DIM, bg=BG_MID
        ).pack(pady=(2, 0))

        # ── Form ────────────────────────────────
        form = tk.Frame(self, bg=BG_DARK, padx=36, pady=20)
        form.pack(fill="both", expand=True)

        self.username_entry = self._field(form, "👤  Username",  "Enter your nickname")
        self._password_field(form)
        self.server_entry   = self._field(form, "🌐  Server IP", "127.0.0.1")
        self.port_entry     = self._field(form, "🔌  Port",      "5555")

        # Info label about registration
        tk.Label(
            form,
            text="ℹ  New user? You'll be registered automatically.",
            font=FONT_SMALL, fg=TEXT_DIM, bg=BG_DARK, anchor="w"
        ).pack(fill="x", pady=(10, 0))

        # ── Connect Button ──────────────────────
        btn = tk.Button(
            form, text="Connect  →",
            font=FONT_BOLD, bg=BTN_BG, fg=BTN_FG,
            activebackground=ACCENT_HOVER, activeforeground=BTN_FG,
            relief="flat", cursor="hand2", pady=10,
            command=self._connect
        )
        btn.pack(fill="x", pady=(14, 0))
        self.bind("<Return>", lambda e: self._connect())

        # Hover effect
        btn.bind("<Enter>", lambda e: btn.config(bg=ACCENT_HOVER))  # type: ignore[arg-type]
        btn.bind("<Leave>", lambda e: btn.config(bg=BTN_BG))  # type: ignore[arg-type]

        # ── Footer ──────────────────────────────
        tk.Label(
            form, text="Simple Chat Application • Educational Project",
            font=FONT_SMALL, fg=TEXT_DIM, bg=BG_DARK
        ).pack(side="bottom", pady=(10, 0))

    def _field(self, parent: tk.Frame, label_text: str, placeholder: str) -> tk.Entry:
        tk.Label(
            parent, text=label_text,
            font=FONT_MAIN, fg=TEXT_MAIN, bg=BG_DARK, anchor="w"
        ).pack(fill="x", pady=(14, 2))

        entry = tk.Entry(
            parent,
            font=FONT_MAIN, bg=INPUT_BG, fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            relief="flat", bd=6
        )
        entry.insert(0, placeholder)
        entry.pack(fill="x", ipady=6)

        def on_focus_in(e, en=entry, ph=placeholder):
            if en.get() == ph:
                en.delete(0, tk.END)
                en.config(fg=TEXT_MAIN)

        def on_focus_out(e, en=entry, ph=placeholder):
            if not en.get():
                en.insert(0, ph)
                en.config(fg=TEXT_DIM)

        entry.config(fg=TEXT_DIM)
        entry.bind("<FocusIn>",  on_focus_in)   # type: ignore[arg-type]
        entry.bind("<FocusOut>", on_focus_out)  # type: ignore[arg-type]
        return entry

    def _password_field(self, parent: tk.Frame) -> None:
        """Password field with masking."""
        tk.Label(
            parent, text="🔑  Password",
            font=FONT_MAIN, fg=TEXT_MAIN, bg=BG_DARK, anchor="w"
        ).pack(fill="x", pady=(14, 2))

        self.password_entry = tk.Entry(
            parent,
            font=FONT_MAIN, bg=INPUT_BG, fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            relief="flat", bd=6,
            show="●"
        )
        self.password_entry.pack(fill="x", ipady=6)

    def _get_entry(self, entry: tk.Entry, placeholder: str) -> str:
        val = entry.get().strip()
        return "" if val == placeholder else val

    def _connect(self) -> None:
        username = self._get_entry(self.username_entry, "Enter your nickname")
        password = self.password_entry.get().strip()
        server   = self._get_entry(self.server_entry,   "127.0.0.1") or "127.0.0.1"
        port_str = self._get_entry(self.port_entry,     "5555")      or "5555"

        if not username:
            messagebox.showerror("Error", "Please enter a username.", parent=self)
            return

        if not password:
            messagebox.showerror("Error", "Please enter a password.", parent=self)
            return

        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("Error", "Port must be a number.", parent=self)
            return

        # Try to connect
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client_socket.connect((server, port))
        except Exception as e:
            messagebox.showerror(
                "Connection Failed",
                f"Could not connect to {server}:{port}\n\n{e}",
                parent=self
            )
            return

        # ── Send username then password ──
        client_socket.send(username.encode(ENCODING))

        # Small delay to ensure packets are separate
        import time
        time.sleep(0.05)
        client_socket.send(password.encode(ENCODING))

        # Read the first server response
        try:
            raw = client_socket.recv(4096)
            first_msg = raw.decode(ENCODING).strip()
        except Exception as e:
            messagebox.showerror("Error", f"Server did not respond.\n\n{e}", parent=self)
            client_socket.close()
            return

        if first_msg.startswith("ERROR:USERNAME_TAKEN"):
            messagebox.showerror(
                "Already Connected",
                f"The username '{username}' is already logged in.\n"
                "Please choose a different name.",
                parent=self
            )
            client_socket.close()
            return

        if first_msg.startswith("ERROR:WRONG_PASS"):
            messagebox.showerror(
                "Wrong Password",
                f"Incorrect password for '{username}'.\n"
                "Please try again.",
                parent=self
            )
            client_socket.close()
            return

        # Open chat window, pass the first message so it isn't lost
        self.withdraw()
        ChatWindow(self, client_socket, username, first_msg)


# ════════════════════════════════════════════════
# MAIN CHAT WINDOW
# ════════════════════════════════════════════════
class ChatWindow(tk.Toplevel):
    def __init__(
        self,
        login_win: LoginScreen,
        client_socket: socket.socket,
        username: str,
        first_message: str = ""
    ):
        super().__init__(login_win)
        self.login_win     = login_win
        self.client_socket = client_socket
        self.username      = username
        self.running       = True

        self.title(f"ChatApp  –  {username}")
        self.configure(bg=BG_DARK)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.status_lbl:  tk.Label | None          = None   # created in _build_ui
        self.chat_box:    scrolledtext.ScrolledText          # created in _build_ui
        self.users_frame: tk.Frame                           # created in _build_ui
        self.msg_entry:   tk.Entry                           # created in _build_ui
        self._center(940, 660)
        self._build_ui()

        # Handle the first message that was already received during login
        if first_message:
            for line in first_message.split("\n"):
                line = line.strip()
                if line:
                    self._handle_incoming(line)

        # Start background receive thread
        recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
        recv_thread.start()

    def _center(self, w: int, h: int) -> None:
        self.update_idletasks()
        sw: int = self.winfo_screenwidth()
        sh: int = self.winfo_screenheight()
        x  = (sw - w) // 2
        y  = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── UI Construction ──────────────────────────
    def _build_ui(self) -> None:
        # TOP BAR
        top_bar = tk.Frame(self, bg=BG_MID, pady=10, padx=16)
        top_bar.pack(fill="x")

        tk.Label(
            top_bar, text="💬  ChatApp",
            font=FONT_TITLE, fg=ACCENT, bg=BG_MID
        ).pack(side="left")

        tk.Label(
            top_bar,
            text=f"Logged in as: {self.username}",
            font=FONT_SMALL, fg=TEXT_DIM, bg=BG_MID
        ).pack(side="left", padx=(12, 0))

        status_lbl = tk.Label(
            top_bar, text="🟢  Connected",
            font=FONT_SMALL, fg=TEXT_SYSTEM, bg=BG_MID
        )
        status_lbl.pack(side="right")
        self.status_lbl = status_lbl

        # MAIN CONTENT AREA
        main = tk.Frame(self, bg=BG_DARK)
        main.pack(fill="both", expand=True)

        # Sidebar – Online Users
        sidebar = tk.Frame(main, bg=BG_PANEL, width=190, padx=10, pady=12)
        sidebar.pack(side="right", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar, text="🟢  Online Users",
            font=FONT_BOLD, fg=TEXT_SYSTEM, bg=BG_PANEL
        ).pack(anchor="w")

        tk.Frame(sidebar, bg=TEXT_DIM, height=1).pack(fill="x", pady=(4, 8))

        self.users_frame = tk.Frame(sidebar, bg=BG_PANEL)
        self.users_frame.pack(fill="both", expand=True)

        # DM hint
        tk.Frame(sidebar, bg=TEXT_DIM, height=1).pack(fill="x", pady=(8, 4))
        tk.Label(
            sidebar,
            text="💡 DM: @user message",
            font=FONT_SMALL, fg=TEXT_DIM, bg=BG_PANEL,
            wraplength=160, justify="left"
        ).pack(anchor="w")

        # Chat area
        chat_area = tk.Frame(main, bg=BG_DARK)
        chat_area.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        # Message display
        self.chat_box = scrolledtext.ScrolledText(
            chat_area,
            state="disabled",
            bg=BG_MID, fg=TEXT_MAIN,
            font=FONT_MSG,
            relief="flat",
            bd=0,
            padx=10, pady=10,
            wrap="word",
            cursor="arrow"
        )
        self.chat_box.pack(fill="both", expand=True, pady=(0, 8))

        # Color tags
        self.chat_box.tag_config("system",   foreground=TEXT_SYSTEM,  font=("Segoe UI",  9, "italic"))
        self.chat_box.tag_config("own",      foreground=TEXT_OWN,     font=("Segoe UI", 10, "bold"))
        self.chat_box.tag_config("other",    foreground=TEXT_OTHER,   font=("Segoe UI", 10))
        self.chat_box.tag_config("history",  foreground=TEXT_HISTORY, font=("Segoe UI",  9, "italic"))
        self.chat_box.tag_config("dm",       foreground=TEXT_DM,      font=("Segoe UI", 10, "bold"))
        self.chat_box.tag_config("dm_sent",  foreground=TEXT_DM_SENT, font=("Segoe UI", 10, "bold"))
        self.chat_box.tag_config("announce", foreground=TEXT_ANNOUNCE, font=("Segoe UI", 10, "bold"))

        # Input row
        input_row = tk.Frame(chat_area, bg=BG_DARK)
        input_row.pack(fill="x")

        self.msg_entry = tk.Entry(
            input_row,
            font=FONT_MAIN, bg=INPUT_BG, fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            relief="flat", bd=6
        )
        self.msg_entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        self.msg_entry.bind("<Return>", lambda e: self._send_message())
        self.msg_entry.focus_set()

        send_btn = tk.Button(
            input_row, text="Send  ➤",
            font=FONT_BOLD, bg=BTN_BG, fg=BTN_FG,
            activebackground=ACCENT_HOVER, activeforeground=BTN_FG,
            relief="flat", cursor="hand2", padx=14, pady=8,
            command=self._send_message
        )
        send_btn.pack(side="right")
        send_btn.bind("<Enter>", lambda e: send_btn.config(bg=ACCENT_HOVER))  # type: ignore[arg-type]
        send_btn.bind("<Leave>", lambda e: send_btn.config(bg=BTN_BG))  # type: ignore[arg-type]

    # ── Chat Display ─────────────────────────────
    def _append_message(self, text: str, tag: str = "other") -> None:
        self.chat_box.config(state="normal")
        self.chat_box.insert("end", text + "\n", tag)
        self.chat_box.config(state="disabled")
        self.chat_box.see("end")

    def _append_history_header(self) -> None:
        self.chat_box.config(state="normal")
        self.chat_box.insert("end", "  ─────── Previous Messages ───────\n", "history")
        self.chat_box.config(state="disabled")

    def _append_history_footer(self) -> None:
        self.chat_box.config(state="normal")
        self.chat_box.insert("end", "  ──────────────────────────────────\n", "history")
        self.chat_box.config(state="disabled")

    def _update_user_list(self, usernames: List[str]) -> None:
        for widget in self.users_frame.winfo_children():
            widget.destroy()
        for name in usernames:
            row = tk.Frame(self.users_frame, bg=BG_PANEL)
            row.pack(fill="x", pady=2)
            dot = tk.Label(row, text="●", fg=ONLINE_COLOR, bg=BG_PANEL, font=FONT_SMALL)
            dot.pack(side="left")
            lbl = tk.Label(
                row, text=f"  {name}",
                font=FONT_MSG,
                fg=TEXT_MAIN if name != self.username else ACCENT,
                bg=BG_PANEL, anchor="w"
            )
            lbl.pack(side="left", fill="x")

    # ── Networking ───────────────────────────────
    def _receive_loop(self):
        """Run in background thread – receives messages from server."""
        while self.running:
            try:
                raw = self.client_socket.recv(BUFFER)
                if not raw:
                    break
                data = raw.decode(ENCODING)

                for line in data.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    self._handle_incoming(line)
            except Exception:
                if self.running:
                    self.after(0, self._connection_lost)  # type: ignore[arg-type]
                break

    # Track whether we're in the history section
    _history_started: bool = False

    def _handle_incoming(self, data: str) -> None:
        """Parse and dispatch server messages."""

        # ── System message ──────────────────────
        if data.startswith("SYSTEM:"):
            msg = data.removeprefix("SYSTEM:")
            if self._history_started:
                self.after(0, self._append_history_footer)  # type: ignore[arg-type]
                self._history_started = False
            self.after(0, lambda m=msg: self._append_message(f"  ℹ  {m}", "system"))

        # ── User list update ────────────────────
        elif data.startswith("USERLIST:"):
            raw_list = data.removeprefix("USERLIST:")
            users = [u.strip() for u in raw_list.split(",") if u.strip()]
            self.after(0, lambda ul=users: self._update_user_list(ul))

        # ── Chat history ────────────────────────
        elif data.startswith("HISTORY:"):
            msg = data.removeprefix("HISTORY:")
            if not self._history_started:
                self._history_started = True
                self.after(0, self._append_history_header)  # type: ignore[arg-type]
            self.after(0, lambda m=msg: self._append_message(f"  {m}", "history"))

        # ── Admin announcement ──────────────────
        elif data.startswith("ANNOUNCE:"):
            if self._history_started:
                self.after(0, self._append_history_footer)  # type: ignore[arg-type]
                self._history_started = False
            msg = data.removeprefix("ANNOUNCE:")
            self.after(0, lambda m=msg: self._append_message(f"  📢  {m}", "announce"))

        # ── Private message received ────────────
        elif data.startswith("DM:"):
            if self._history_started:
                self.after(0, self._append_history_footer)  # type: ignore[arg-type]
                self._history_started = False
            msg = data.removeprefix("DM:")
            self.after(0, lambda m=msg: self._append_message(f"  {m}", "dm"))

        # ── Private message sent (echo) ─────────
        elif data.startswith("DM_SENT:"):
            if self._history_started:
                self.after(0, self._append_history_footer)  # type: ignore[arg-type]
                self._history_started = False
            msg = data.removeprefix("DM_SENT:")
            self.after(0, lambda m=msg: self._append_message(f"  {m}", "dm_sent"))

        # ── Normal chat message ─────────────────
        elif data.startswith("MSG:"):
            if self._history_started:
                self.after(0, self._append_history_footer)  # type: ignore[arg-type]
                self._history_started = False
            msg = data.removeprefix("MSG:")
            # Format: "[HH:MM] username: message body"
            if ": " in msg:
                rest = msg
                timestamp = ""
                if rest.startswith("[") and "]" in rest:
                    parts = rest.split("]", 1)
                    timestamp = parts[0] + "] "
                    rest = parts[1].strip()

                if ": " in rest:
                    sender, _, body = rest.partition(": ")
                    sender = sender.strip()
                    body   = body.strip()
                    if sender == self.username:
                        tag    = "own"
                        prefix = "  ➤ You"
                    else:
                        tag    = "other"
                        prefix = f"  {sender}"
                    display = f"{prefix}  {timestamp}{body}"
                    self.after(0, lambda d=display, t=tag: self._append_message(d, t))
                else:
                    self.after(0, lambda m=msg: self._append_message(f"  {m}", "other"))
            else:
                self.after(0, lambda m=msg: self._append_message(f"  {m}", "other"))

    def _send_message(self) -> None:
        msg = self.msg_entry.get().strip()
        if not msg:
            return
        self.msg_entry.delete(0, tk.END)
        try:
            self.client_socket.send(msg.encode(ENCODING))
        except Exception:
            self.after(0, self._connection_lost)  # type: ignore[arg-type]

    # ── Connection Management ────────────────────
    def _connection_lost(self) -> None:
        self.running = False
        if self.status_lbl is not None and self.status_lbl.winfo_exists():  # type: ignore[union-attr]
            self.status_lbl.config(text="🔴  Disconnected", fg="#f38ba8")
        self._append_message("  ⚠  Connection to server lost.", "system")
        messagebox.showwarning("Disconnected", "Connection to server was lost.", parent=self)

    def _on_close(self) -> None:
        self.running = False
        try:
            self.client_socket.close()
        except Exception:
            pass
        self.destroy()
        self.login_win.destroy()


# ════════════════════════════════════════════════
# Entry Point
# ════════════════════════════════════════════════
if __name__ == "__main__":
    app = LoginScreen()
    app.mainloop()
