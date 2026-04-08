"""
Simple Chat Application - Server Admin GUI
==========================================
Author  : Chat App Project
Date    : 2026-03-10
Python  : 3.x

How to run:
    python server_gui.py

This launches a graphical admin panel that runs the chat server
in the background and lets you monitor connections, read logs,
send admin announcements, and kick users.
"""

import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext
from typing import Union

import server  # type: ignore  # Our chat server module

# ─────────────────────────────────────────────
# Color Palette (matches client dark theme)
# ─────────────────────────────────────────────
BG_DARK      = "#1e1e2e"
BG_MID       = "#2a2a3e"
BG_PANEL     = "#252535"
ACCENT       = "#7c6af7"
ACCENT_HOVER = "#9a8fff"
TEXT_MAIN    = "#cdd6f4"
TEXT_DIM     = "#6c7086"
TEXT_SYSTEM  = "#a6e3a1"
TEXT_WARN    = "#f38ba8"
TEXT_GOLD    = "#f9e2af"
BTN_FG       = "#ffffff"
BTN_RED      = "#e06c75"
BTN_RED_HOV  = "#f38ba8"
BTN_GOLD     = "#e5a50a"
BTN_GOLD_HOV = "#f9c74f"
INPUT_BG     = "#313244"
ONLINE_COLOR = "#a6e3a1"

FONT_MAIN  = ("Segoe UI", 11)
FONT_BOLD  = ("Segoe UI", 11, "bold")
FONT_TITLE = ("Segoe UI", 16, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_MONO  = ("Consolas", 10)


# ─────────────────────────────────────────────
# Tiny helper: a "not-yet-ready" log box stub
# ─────────────────────────────────────────────
class _LogBoxStub:
    """Placeholder used before the real ScrolledText widget is created."""

    def config(self, **_kw):
        pass

    def insert(self, *_a, **_kw):
        pass

    def see(self, _idx):
        pass

    def pack(self, **_kw):
        pass

    def tag_config(self, *_a, **_kw):
        pass


class ServerAdminGUI(tk.Tk):

    def __init__(self) -> None:
        super().__init__()

        self.log_box: Union[scrolledtext.ScrolledText, _LogBoxStub] = _LogBoxStub()
        self._selected_user: str = ""
        self.kick_btn: tk.Button  # declared here; assigned in _build_ui
        self.status_lbl: tk.Label
        self.users_frame: tk.Frame
        self.user_count_lbl: tk.Label
        self.announce_entry: tk.Entry
        self._server_thread: threading.Thread

        self.title("ChatApp – Server Admin Panel")
        self.configure(bg=BG_DARK)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._center(960, 660)
        self._build_ui()
        self._hook_server()
        self._start_server()

    # ── Window helpers ───────────────────────
    def _center(self, w: int, h: int) -> None:  # noqa: E741
        self.update_idletasks()
        sw: int = self.winfo_screenwidth()
        sh: int = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    # ── UI Construction ──────────────────────
    def _build_ui(self) -> None:
        # TOP BAR ──────────────────────────────
        top = tk.Frame(self, bg=BG_MID, pady=10, padx=16)
        top.pack(fill="x")

        tk.Label(
            top, text="🖥️  ChatApp – Admin Panel",
            font=FONT_TITLE, fg=ACCENT, bg=BG_MID,
        ).pack(side="left")

        self.status_lbl = tk.Label(
            top, text="⏳  Starting…",
            font=FONT_SMALL, fg=TEXT_DIM, bg=BG_MID,
        )
        self.status_lbl.pack(side="right")

        # MAIN AREA ────────────────────────────
        main = tk.Frame(self, bg=BG_DARK)
        main.pack(fill="both", expand=True, padx=12, pady=10)

        # LEFT: Log ────────────────────────────
        left = tk.Frame(main, bg=BG_DARK)
        left.pack(side="left", fill="both", expand=True)

        tk.Label(
            left, text="📋  Server Log",
            font=FONT_BOLD, fg=TEXT_MAIN, bg=BG_DARK, anchor="w",
        ).pack(fill="x", pady=(0, 4))

        # Replace the stub with the real widget
        self.log_box = scrolledtext.ScrolledText(
            left,
            state="disabled",
            bg=BG_MID, fg=TEXT_MAIN,
            font=FONT_MONO,
            relief="flat", bd=0,
            padx=8, pady=8,
            wrap="word", cursor="arrow",
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_config("info",   foreground=TEXT_MAIN)
        self.log_box.tag_config("join",   foreground=TEXT_SYSTEM)
        self.log_box.tag_config("leave",  foreground=TEXT_WARN)
        self.log_box.tag_config("kick",   foreground=TEXT_WARN,  font=("Consolas", 10, "bold"))
        self.log_box.tag_config("msg",    foreground="#89b4fa")
        self.log_box.tag_config("header", foreground=ACCENT,     font=("Consolas", 10, "bold"))
        self.log_box.tag_config("announce", foreground=TEXT_GOLD, font=("Consolas", 10, "bold"))

        # RIGHT: Users + controls ──────────────
        right = tk.Frame(main, bg=BG_PANEL, width=220, padx=10, pady=12)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)

        tk.Label(
            right, text="🟢  Online Users",
            font=FONT_BOLD, fg=TEXT_SYSTEM, bg=BG_PANEL,
        ).pack(anchor="w")

        tk.Frame(right, bg=TEXT_DIM, height=1).pack(fill="x", pady=(4, 8))

        self.users_frame = tk.Frame(right, bg=BG_PANEL)
        self.users_frame.pack(fill="both", expand=True)

        self.user_count_lbl = tk.Label(
            right, text="0 users online",
            font=FONT_SMALL, fg=TEXT_DIM, bg=BG_PANEL,
        )
        self.user_count_lbl.pack(anchor="w", pady=(6, 12))

        tk.Frame(right, bg=TEXT_DIM, height=1).pack(fill="x", pady=(0, 10))

        # ── Admin Announcement ─────────────────
        tk.Label(
            right, text="📢  Announcement",
            font=FONT_BOLD, fg=TEXT_GOLD, bg=BG_PANEL,
        ).pack(anchor="w", pady=(0, 4))

        self.announce_entry = tk.Entry(
            right,
            font=FONT_MAIN, bg=INPUT_BG, fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            relief="flat", bd=4,
        )
        self.announce_entry.pack(fill="x", ipady=5, pady=(0, 6))
        self.announce_entry.bind("<Return>", lambda e: self._send_announcement())

        announce_btn = tk.Button(
            right, text="📢  Send to All",
            font=FONT_BOLD, bg=BTN_GOLD, fg="#1e1e2e",
            activebackground=BTN_GOLD_HOV, activeforeground="#1e1e2e",
            relief="flat", cursor="hand2", pady=6,
            command=self._send_announcement,
        )
        announce_btn.pack(fill="x", pady=(0, 12))
        announce_btn.bind("<Enter>", lambda e, b=announce_btn: b.config(bg=BTN_GOLD_HOV))  # type: ignore[arg-type]
        announce_btn.bind("<Leave>", lambda e, b=announce_btn: b.config(bg=BTN_GOLD))  # type: ignore[arg-type]

        tk.Frame(right, bg=TEXT_DIM, height=1).pack(fill="x", pady=(0, 10))

        # ── Kick button ────────────────────────
        self.kick_btn = tk.Button(
            right, text="⚡  Kick Selected",
            font=FONT_BOLD, bg=BTN_RED, fg=BTN_FG,
            activebackground=BTN_RED_HOV, activeforeground=BTN_FG,
            relief="flat", cursor="hand2", pady=8,
            command=self._kick_selected,
        )
        self.kick_btn.pack(fill="x", pady=(0, 6))
        self.kick_btn.bind("<Enter>", lambda e, btn=self.kick_btn: btn.config(bg=BTN_RED_HOV))  # type: ignore[arg-type]
        self.kick_btn.bind("<Leave>", lambda e, btn=self.kick_btn: btn.config(bg=BTN_RED))  # type: ignore[arg-type]

        # ── Stop server button ─────────────────
        stop_btn = tk.Button(
            right, text="🛑  Stop Server",
            font=FONT_BOLD, bg=INPUT_BG, fg=TEXT_WARN,
            activebackground="#444466", activeforeground=TEXT_WARN,
            relief="flat", cursor="hand2", pady=8,
            command=self._stop_server,
        )
        stop_btn.pack(fill="x")

    # ── Server hooks ─────────────────────────
    def _hook_server(self) -> None:
        """Register GUI callbacks into the server module."""
        server.on_log        = self._on_log
        server.on_user_join  = self._on_user_join
        server.on_user_leave = self._on_user_leave
        server.on_message    = self._on_server_message

    def _start_server(self) -> None:
        """Start the server in a background daemon thread."""
        self._server_thread = threading.Thread(target=server.start, daemon=True)
        self._server_thread.start()
        self.after(500, self._set_running_status)  # type: ignore[arg-type]

    def _set_running_status(self) -> None:
        self.status_lbl.config(text="🟢  Running  •  Port 5555", fg=TEXT_SYSTEM)

    # ── Callbacks (server thread → main thread via after()) ──
    def _on_log(self, msg: str) -> None:
        self.after(0, lambda m=msg: self._append_log(m, "info"))

    def _on_user_join(self, username: str) -> None:
        self.after(0, lambda u=username: (
            self._append_log(f"  ✅  {u} joined", "join"),
            self._refresh_users(),
        ))

    def _on_user_leave(self, username: str) -> None:
        self.after(0, lambda u=username: (
            self._append_log(f"  ❌  {u} left", "leave"),
            self._refresh_users(),
        ))

    def _on_server_message(self, msg: str) -> None:
        self.after(0, lambda m=msg: self._append_log(f"  💬  {m}", "msg"))

    # ── Log display ───────────────────────────
    def _append_log(self, text: str, tag: str = "info") -> None:
        """Append a line to the log box."""
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n", tag)
        self.log_box.config(state="disabled")
        self.log_box.see("end")

    # ── User list ─────────────────────────────
    def _refresh_users(self) -> None:
        """Rebuild the online-user panel."""
        with server.lock:
            users = list(server.clients.keys())

        for widget in self.users_frame.winfo_children():
            widget.destroy()
        self._selected_user = ""

        for name in users:
            self._add_user_row(name)

        count = len(users)
        self.user_count_lbl.config(
            text=f"{count} user{'s' if count != 1 else ''} online"
        )

    def _add_user_row(self, name: str) -> None:
        row = tk.Frame(self.users_frame, bg=BG_PANEL, cursor="hand2")
        row.pack(fill="x", pady=2)

        dot = tk.Label(row, text="●", fg=ONLINE_COLOR, bg=BG_PANEL, font=FONT_SMALL)
        dot.pack(side="left")

        lbl = tk.Label(
            row, text=f"  {name}",
            font=FONT_MAIN, fg=TEXT_MAIN, bg=BG_PANEL, anchor="w",
        )
        lbl.pack(side="left", fill="x")

        def _select(
            _event: "tk.Event[tk.Widget]",
            _name: str = name,
            _row: tk.Frame = row,
            _lbl: tk.Label = lbl,
            _dot: tk.Label = dot,
        ) -> None:
            self._deselect_all()
            self._selected_user = _name
            _row.config(bg=ACCENT)
            _lbl.config(bg=ACCENT)
            _dot.config(bg=ACCENT)

        for widget in (row, lbl, dot):
            widget.bind("<Button-1>", _select)

    def _deselect_all(self) -> None:
        """Reset all user-row backgrounds to the default panel colour."""
        for row in self.users_frame.winfo_children():
            row.config(bg=BG_PANEL)  # type: ignore[call-arg]
            for child in row.winfo_children():
                child.config(bg=BG_PANEL)  # type: ignore[call-arg]

    # ── Admin actions ─────────────────────────
    def _send_announcement(self) -> None:
        """Broadcast an admin message to all connected clients."""
        text = self.announce_entry.get().strip()
        if not text:
            messagebox.showinfo("Announce", "Please type an announcement first.", parent=self)
            return
        server.broadcast_admin(text)
        self._append_log(f"  📢  Announcement sent: {text}", "announce")
        self.announce_entry.delete(0, tk.END)

    def _kick_selected(self) -> None:
        if not self._selected_user:
            messagebox.showinfo("Kick", "Please click on a user first.", parent=self)
            return

        target = self._selected_user
        if not messagebox.askyesno(
            "Kick User",
            f"Are you sure you want to kick '{target}'?",
            parent=self,
        ):
            return

        if server.kick_user(target):
            self._append_log(f"  🔨  Kicked: {target}", "kick")
            self._refresh_users()
        else:
            messagebox.showwarning(
                "Kick", f"'{target}' is no longer connected.", parent=self
            )

    def _stop_server(self) -> None:
        if not messagebox.askyesno(
            "Stop Server",
            "Stop the server? All clients will be disconnected.",
            parent=self,
        ):
            return
        server.stop()
        self.status_lbl.config(text="🔴  Stopped", fg=TEXT_WARN)
        self._append_log("  🛑  Server stopped by admin.", "kick")

    # ── Close ─────────────────────────────────
    def _on_close(self) -> None:
        server.stop()
        self.destroy()


if __name__ == "__main__":
    app = ServerAdminGUI()
    app.mainloop()
