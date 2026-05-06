"""Server Admin Panel — same palette as client."""
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

import server

# ── Palette (SAME as client) ───────────────────────────────────────────────────
BG       = "#080d1a"
PANEL    = "#0d1429"
CARD     = "#111d38"
ACCENT   = "#3d7ae5"
ACCENT2  = "#5865f2"
TEXT     = "#dce6f5"
DIM      = "#7a8ba8"
INPUT_BG = "#080d1a"
BORDER   = "#1e3059"
RED      = "#da3633"
GOLD     = "#e3b341"
MUTED_C  = "#da3633"
ONLINE_C = "#3d9be9"

FONT       = ("Segoe UI", 11)
FONT_BOLD  = ("Segoe UI", 11, "bold")
FONT_TITLE = ("Segoe UI", 18, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_MONO  = ("Consolas", 10)


class ServerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chat App — Admin Panel")
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._center(1050, 680)
        self._selected = ""
        self._build()
        self._hook()
        threading.Thread(target=server.start, daemon=True).start()
        self.after(600, lambda: self.status_lbl.config(
            text="🟢  Running  •  Port 5555", fg=ONLINE_C))

    def _center(self, w, h):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build(self):
        # ── Top bar ────────────────────────────────────────────────────────
        top = tk.Frame(self, bg=PANEL, pady=12, padx=16)
        top.pack(fill="x")
        tk.Label(top, text="🖥️  Chat App — Admin Panel",
                 font=FONT_TITLE, fg=ACCENT2, bg=PANEL).pack(side="left")
        self.status_lbl = tk.Label(top, text="⏳  Starting…",
                                   font=FONT_SMALL, fg=DIM, bg=PANEL)
        self.status_lbl.pack(side="right")

        # ── Stats row ──────────────────────────────────────────────────────
        stats = tk.Frame(self, bg=CARD, pady=6, padx=16)
        stats.pack(fill="x")
        self.queue_lbl = tk.Label(stats, text="📬  Queue: 0",
                                  font=FONT_SMALL, fg=DIM, bg=CARD)
        self.queue_lbl.pack(side="left")
        self.muted_lbl = tk.Label(stats, text="🔇  Muted: 0",
                                  font=FONT_SMALL, fg=DIM, bg=CARD)
        self.muted_lbl.pack(side="left", padx=(20, 0))

        # ── Main area ──────────────────────────────────────────────────────
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=10, pady=8)

        # Log (left)
        left = tk.Frame(main, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="📋  Server Log", font=FONT_BOLD,
                 fg=TEXT, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))
        self.log = scrolledtext.ScrolledText(
            left, state="disabled", bg=PANEL, fg=TEXT,
            font=FONT_MONO, relief="flat", bd=0, padx=8, pady=8,
            wrap="word", cursor="arrow")
        self.log.pack(fill="both", expand=True)
        self.log.tag_config("info",  foreground=TEXT)
        self.log.tag_config("join",  foreground=ONLINE_C)
        self.log.tag_config("leave", foreground=RED)
        self.log.tag_config("kick",  foreground=RED)
        self.log.tag_config("mute",  foreground=ACCENT2)
        self.log.tag_config("queue", foreground=GOLD)
        self.log.tag_config("msg",   foreground="#89b4fa")
        self.log.tag_config("ann",   foreground=GOLD)

        # Right panel
        right = tk.Frame(main, bg=PANEL, width=230, padx=10, pady=12)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        tk.Label(right, text="🟢  Online Users", font=FONT_BOLD,
                 fg=ONLINE_C, bg=PANEL).pack(anchor="w")
        tk.Frame(right, bg=BORDER, height=1).pack(fill="x", pady=(4, 8))

        self.user_frame = tk.Frame(right, bg=PANEL)
        self.user_frame.pack(fill="both", expand=True)

        self.user_count = tk.Label(right, text="0 online",
                                   font=FONT_SMALL, fg=DIM, bg=PANEL)
        self.user_count.pack(anchor="w", pady=(6, 10))

        tk.Frame(right, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))

        # Announcement
        tk.Label(right, text="📢  Announcement", font=FONT_BOLD,
                 fg=GOLD, bg=PANEL).pack(anchor="w", pady=(0, 4))
        self.ann_entry = tk.Entry(right, font=FONT, bg=INPUT_BG, fg=TEXT,
                                  insertbackground=TEXT, relief="flat",
                                  highlightthickness=1,
                                  highlightbackground=BORDER, bd=4)
        self.ann_entry.pack(fill="x", ipady=6, pady=(0, 6))
        self.ann_entry.bind("<Return>", lambda e: self._announce())
        tk.Button(right, text="📢 Send to All", font=FONT_BOLD,
                  bg=GOLD, fg="#0d1117", relief="flat", cursor="hand2",
                  pady=6, command=self._announce).pack(fill="x", pady=(0, 10))

        tk.Frame(right, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))

        # Mute button
        self.mute_btn = tk.Button(right, text="🔇  Mute Selected",
                                  font=FONT_BOLD, bg=ACCENT2, fg=TEXT,
                                  relief="flat", cursor="hand2", pady=8,
                                  command=self._mute)
        self.mute_btn.pack(fill="x", pady=(0, 6))

        # Kick button
        tk.Button(right, text="⚡  Kick Selected",
                  font=FONT_BOLD, bg=RED, fg=TEXT,
                  relief="flat", cursor="hand2", pady=8,
                  command=self._kick).pack(fill="x", pady=(0, 6))

        # Stop
        tk.Button(right, text="🛑  Stop Server",
                  font=FONT_BOLD, bg=CARD, fg=RED,
                  relief="flat", cursor="hand2", pady=8,
                  command=self._stop).pack(fill="x")

    # ── Hooks ─────────────────────────────────────────────────────────────────
    def _hook(self):
        server.on_log        = lambda m: self.after(0, self._log, m, "info")
        server.on_user_join  = lambda u: self.after(0, self._on_join, u)
        server.on_user_leave = lambda u: self.after(0, self._on_leave, u)
        server.on_message    = lambda m: self.after(0, self._log, f"  💬  {m}", "msg")
        server.on_mute_update = lambda: self.after(0, self._refresh_users)

    def _on_join(self, u):
        self._log(f"  ✅  {u} joined", "join")
        self._refresh_users()
        self._refresh_stats()

    def _on_leave(self, u):
        self._log(f"  ❌  {u} left", "leave")
        self._refresh_users()
        self._refresh_stats()

    def _log(self, text: str, tag: str = "info"):
        ml = text.lower()
        if "[queue]" in ml:
            tag = "queue"
        elif "[mute]" in ml or "[unmute]" in ml:
            tag = "mute"
        elif "[kick]" in ml:
            tag = "kick"
        self.log.config(state="normal")
        self.log.insert("end", text + "\n", tag)
        self.log.config(state="disabled")
        self.log.see("end")

    # ── Stats ─────────────────────────────────────────────────────────────────
    def _refresh_stats(self):
        with server.lock:
            q = sum(len(v) for v in server.offline_queue.values())
        m = len(server.muted_users)
        self.queue_lbl.config(text=f"📬  Queue: {q}", fg=GOLD if q else DIM)
        self.muted_lbl.config(text=f"🔇  Muted: {m}", fg=MUTED_C if m else DIM)

    # ── Users ─────────────────────────────────────────────────────────────────
    def _refresh_users(self):
        with server.lock:
            users = list(server.clients.keys())
        for w in self.user_frame.winfo_children():
            w.destroy()
        self._selected = ""
        self.mute_btn.config(text="🔇  Mute Selected")

        for name in users:
            muted = name in server.muted_users
            dot = "🔇" if muted else "●"
            dot_c = MUTED_C if muted else ONLINE_C
            fg_c = MUTED_C if muted else TEXT

            row = tk.Frame(self.user_frame, bg=PANEL, cursor="hand2")
            row.pack(fill="x", pady=2)

            tk.Label(row, text=dot, fg=dot_c, bg=PANEL,
                     font=FONT_SMALL).pack(side="left", padx=(4, 2))
            lbl = tk.Label(row, text=name, font=FONT, fg=fg_c,
                           bg=PANEL, anchor="w")
            lbl.pack(side="left", fill="x")

            with server.lock:
                q = len(server.offline_queue.get(name, []))
            if q:
                tk.Label(row, text=f"📬{q}", font=FONT_SMALL,
                         fg="#0d1117", bg=GOLD, padx=4).pack(side="right")

            def _sel(_e, n=name, r=row, l=lbl):
                for row2 in self.user_frame.winfo_children():
                    row2.config(bg=PANEL)
                    for c in row2.winfo_children():
                        c.config(bg=PANEL)
                r.config(bg=ACCENT2)
                l.config(bg=ACCENT2)
                self._selected = n
                self.mute_btn.config(
                    text="🔊  Unmute Selected" if n in server.muted_users
                    else "🔇  Mute Selected"
                )

            row.bind("<Button-1>", _sel)
            lbl.bind("<Button-1>", _sel)

        cnt = len(users)
        self.user_count.config(text=f"{cnt} user{'s' if cnt != 1 else ''} online")
        self._refresh_stats()

    # ── Actions ───────────────────────────────────────────────────────────────
    def _announce(self):
        text = self.ann_entry.get().strip()
        if not text:
            messagebox.showinfo("Announce", "Type a message first.", parent=self)
            return
        server.broadcast_admin(text)
        self._log(f"  📢  Announced: {text}", "ann")
        self.ann_entry.delete(0, tk.END)

    def _mute(self):
        if not self._selected:
            messagebox.showinfo("Mute", "Select a user first.", parent=self)
            return
        if self._selected in server.muted_users:
            if server.unmute_user(self._selected):
                self._log(f"  🔊  Unmuted: {self._selected}", "mute")
        else:
            if server.mute_user(self._selected):
                self._log(f"  🔇  Muted: {self._selected}", "mute")
        self._refresh_users()

    def _kick(self):
        if not self._selected:
            messagebox.showinfo("Kick", "Select a user first.", parent=self)
            return
        if messagebox.askyesno("Kick", f"Kick '{self._selected}'?", parent=self):
            if server.kick_user(self._selected):
                self._log(f"  ⚡  Kicked: {self._selected}", "kick")
            self._refresh_users()

    def _stop(self):
        if messagebox.askyesno("Stop", "Stop the server?", parent=self):
            server.stop()
            self.status_lbl.config(text="🔴  Stopped", fg=RED)
            self._log("  🛑  Server stopped.", "kick")

    def _close(self):
        server.stop()
        self.destroy()


if __name__ == "__main__":
    app = ServerGUI()
    app.mainloop()
