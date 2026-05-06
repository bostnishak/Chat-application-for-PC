"""Chat Window — WhatsApp-style, pure tkinter."""
import io, json, os, struct, threading, time, tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from client_network import send_text, send_binary, recv_packet

# ── Palette (Navy / Dark-Blue theme) ─────────────────────────────────────────
BG       = "#080d1a"   # deepest navy
PANEL    = "#0d1429"   # sidebar / header
CARD     = "#111d38"   # cards, bubbles
ACCENT   = "#3d7ae5"   # primary blue
ACCENT2  = "#5865f2"   # blurple (active chat / send btn)
TEXT     = "#dce6f5"   # main text
DIM      = "#7a8ba8"   # secondary text
INPUT_BG = "#080d1a"
BORDER   = "#1e3059"   # subtle navy border
OWN_BG   = "#1e3a6e"   # OWN message bubble — dark blue
OTH_BG   = "#111d38"   # OTHER message bubble — navy
SYS_FG   = "#6a7d9e"
RED      = "#da3633"
GOLD     = "#e3b341"
PREVIEW_BG = "#0d1e40" # file/voice action bar

FONT       = ("Segoe UI", 11)
FONT_BOLD  = ("Segoe UI", 11, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_TIME  = ("Segoe UI", 8)
FONT_EMOJI = ("Segoe UI Emoji", 18)

EMOJIS = ["😀","😂","😍","🥰","😎","😊","🤔","😅","🤩","😏",
          "👍","👎","❤️","🔥","✅","🎉","😢","😡","🙄","💀",
          "🙏","💪","👏","🤝","💬","📎","🎵","🚀","⭐","💯"]


class ChatWindow:
    def __init__(self, root, sock, username: str, init_msg: str):
        self.root      = root
        self.sock      = sock
        self.username  = username
        self.running   = True
        self.users     = []
        self.groups    = []
        self.unread    = {}
        self.active    = "Global"
        self.panels    = {}
        self.sidebar_btns = {}
        self._pending_file = None       # (filename, bytes)
        self._recording    = False
        self._audio_frames = []
        self._audio_stream = None
        self._rec_seconds  = 0          # live timer counter
        self._emoji_imgs   = {}         # cache: char -> PhotoImage

        self.win = tk.Toplevel(root)
        self.win.title(f"Chat App — {username}")
        self.win.configure(bg=BG)
        self.win.protocol("WM_DELETE_WINDOW", self._close)
        self._center(1150, 720)

        self._build_ui()
        self._switch("Global")
        self._dispatch(init_msg, None)

        threading.Thread(target=self._recv_loop, daemon=True).start()

    # ── Layout ────────────────────────────────────────────────────────────────
    def _center(self, w, h):
        self.win.update_idletasks()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build_ui(self):
        self.win.grid_columnconfigure(1, weight=1)
        self.win.grid_rowconfigure(0, weight=1)

        # ── Sidebar ────────────────────────────────────────────────────────
        sb = tk.Frame(self.win, bg=PANEL, width=250)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(1, weight=1)

        # sidebar header
        hdr = tk.Frame(sb, bg=PANEL, pady=14, padx=14)
        hdr.grid(row=0, column=0, sticky="ew")
        tk.Label(hdr, text=f"👤 {self.username}", font=FONT_BOLD,
                 fg=TEXT, bg=PANEL).pack(side="left")

        # contact list
        self.sb_list = tk.Frame(sb, bg=PANEL)
        self.sb_list.grid(row=1, column=0, sticky="nsew")

        # sidebar footer (new-group / join)
        ftr = tk.Frame(sb, bg=PANEL, pady=10, padx=10)
        ftr.grid(row=2, column=0, sticky="ew")
        tk.Button(ftr, text="➕ New Group", font=FONT_SMALL, bg=ACCENT,
                  fg=TEXT, relief="flat", cursor="hand2", padx=8, pady=5,
                  command=self._new_group).pack(side="left", fill="x", expand=True, padx=(0,4))
        tk.Button(ftr, text="🔗 Join", font=FONT_SMALL, bg=ACCENT2,
                  fg=TEXT, relief="flat", cursor="hand2", padx=8, pady=5,
                  command=self._join_group).pack(side="right", fill="x", expand=True, padx=(4,0))

        # ── Right (header + chat area + input) ───────────────────────────
        right = tk.Frame(self.win, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # chat header
        self.chat_hdr = tk.Frame(right, bg=PANEL, pady=12, padx=16)
        self.chat_hdr.grid(row=0, column=0, sticky="ew")
        self.chat_title = tk.Label(self.chat_hdr, text="🌐 Global",
                                   font=FONT_BOLD, fg=TEXT, bg=PANEL)
        self.chat_title.pack(side="left")
        self.leave_btn = tk.Button(self.chat_hdr, text="🚪 Leave", font=FONT_SMALL,
                                   bg=RED, fg=TEXT, relief="flat", cursor="hand2",
                                   padx=8, pady=4, command=self._leave_group)
        # leave_btn hidden by default

        # chat container (panels stack here)
        self.chat_area = tk.Frame(right, bg=BG)
        self.chat_area.grid(row=1, column=0, sticky="nsew")

        # ── File preview bar (row=2, hidden by default) ──────────────────────
        self.preview_bar = tk.Frame(right, bg=PREVIEW_BG, pady=5, padx=10)
        # NOT gridded until a file is selected
        self.preview_thumb = tk.Label(self.preview_bar, bg=PREVIEW_BG)
        self.preview_thumb.pack(side="left", padx=(0, 8))
        self.preview_lbl = tk.Label(self.preview_bar, text="", font=FONT_SMALL,
                                    fg=TEXT, bg=PREVIEW_BG, anchor="w")
        self.preview_lbl.pack(side="left", fill="x", expand=True)
        tk.Button(self.preview_bar, text="✖", font=FONT_SMALL,
                  bg=RED, fg=TEXT, relief="flat", cursor="hand2", padx=8, pady=3,
                  command=self._cancel_file).pack(side="right", padx=(6, 0))
        tk.Button(self.preview_bar, text="  📤 Send  ", font=FONT_BOLD,
                  bg=ACCENT, fg=TEXT, relief="flat", cursor="hand2", padx=10, pady=4,
                  command=self._send_pending_file).pack(side="right")

        # ── Voice timer bar (row=2, hidden by default) ─────────────────
        self.voice_bar = tk.Frame(right, bg="#1a1040", pady=5, padx=10)
        # NOT gridded until recording starts
        tk.Label(self.voice_bar, text="🔴  Recording...", font=FONT_BOLD,
                 fg="#a090ff", bg="#1a1040").pack(side="left")
        self.voice_timer_lbl = tk.Label(self.voice_bar, text="0:00",
                                        font=FONT_BOLD, fg=TEXT, bg="#1a1040")
        self.voice_timer_lbl.pack(side="left", padx=(10, 0))
        tk.Button(self.voice_bar, text="  📤 Send  ", font=FONT_BOLD,
                  bg="#3d2a8a", fg=TEXT, relief="flat", cursor="hand2", padx=10, pady=4,
                  command=self._voice_stop_send).pack(side="right")
        tk.Button(self.voice_bar, text="✖ Cancel", font=FONT_SMALL,
                  bg="#120e2e", fg="#a090ff", relief="flat", cursor="hand2", padx=6, pady=3,
                  command=self._voice_cancel).pack(side="right", padx=(0, 6))

        # ── Input bar (row=3) ────────────────────────────────────────
        inp = tk.Frame(right, bg=PANEL, pady=8, padx=10)
        inp.grid(row=3, column=0, sticky="ew")
        inp.grid_columnconfigure(2, weight=1)

        tk.Button(inp, text="📎", font=("Segoe UI Emoji", 16),
                  bg=PANEL, fg=TEXT, relief="flat", cursor="hand2",
                  command=self._pick_file).grid(row=0, column=0, padx=(0,4))
        tk.Button(inp, text="😊", font=("Segoe UI Emoji", 16),
                  bg=PANEL, fg=TEXT, relief="flat", cursor="hand2",
                  command=self._emoji_picker).grid(row=0, column=1, padx=(0,6))

        self.input_var = tk.StringVar()
        self.input_box = tk.Entry(inp, textvariable=self.input_var,
                                  font=FONT, bg=INPUT_BG, fg=TEXT,
                                  insertbackground=TEXT, relief="flat",
                                  highlightthickness=1,
                                  highlightbackground=BORDER,
                                  highlightcolor=ACCENT2, bd=6)
        self.input_box.grid(row=0, column=2, sticky="ew", ipady=8)
        self.input_box.bind("<Return>", lambda e: self._send_msg())

        send_btn = tk.Button(inp, text="Send ▶", font=FONT_BOLD,
                             bg=ACCENT2, fg=TEXT, relief="flat",
                             cursor="hand2", padx=14, pady=6,
                             command=self._send_msg)
        send_btn.grid(row=0, column=3, padx=(6, 0))

        # Voice button — click to START, click again to STOP+send
        self.voice_btn = tk.Button(inp, text="🎤", font=("Segoe UI Emoji", 16),
                                   bg=PANEL, fg=TEXT, relief="flat",
                                   cursor="hand2", command=self._voice_toggle)
        self.voice_btn.grid(row=0, column=4, padx=(4, 0))

    # ── Sidebar helpers ───────────────────────────────────────────────────────
    def _rebuild_sidebar(self):
        for w in self.sb_list.winfo_children():
            w.destroy()
        self.sidebar_btns.clear()

        def _add(chat_id, icon):
            unread = self.unread.get(chat_id, 0)
            active = (chat_id == self.active)
            bg = ACCENT2 if active else PANEL
            fg = TEXT
            label = f"{icon} {chat_id}" + (f"  [{unread}]" if unread and not active else "")
            btn = tk.Button(self.sb_list, text=label, font=FONT,
                            bg=bg, fg=fg, relief="flat", anchor="w",
                            cursor="hand2", pady=10, padx=14,
                            command=lambda c=chat_id: self._switch(c))
            btn.pack(fill="x")
            self.sidebar_btns[chat_id] = btn

        _add("Global", "🌐")

        if self.groups:
            tk.Label(self.sb_list, text="GROUPS", font=FONT_SMALL,
                     fg=DIM, bg=PANEL, anchor="w", padx=14).pack(fill="x", pady=(10, 2))
            for g in sorted(self.groups):
                _add(g, "👥")

        others = [u for u in self.users if u != self.username]
        if others:
            tk.Label(self.sb_list, text="DIRECT MESSAGES", font=FONT_SMALL,
                     fg=DIM, bg=PANEL, anchor="w", padx=14).pack(fill="x", pady=(10, 2))
            for u in sorted(others):
                _add(u, "👤")

    # ── Chat panels ───────────────────────────────────────────────────────────
    def _get_panel(self, chat_id: str) -> tk.Frame:
        if chat_id not in self.panels:
            f = tk.Frame(self.chat_area, bg=BG)
            # inner scrollable via canvas
            canvas = tk.Canvas(f, bg=BG, highlightthickness=0)
            sb = tk.Scrollbar(f, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            inner = tk.Frame(canvas, bg=BG)
            win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

            def _resize(e, cv=canvas, wid=win_id):
                cv.itemconfig(wid, width=cv.winfo_width())
            canvas.bind("<Configure>", _resize)

            def _scroll(e, cv=canvas):
                cv.yview_moveto(1.0)
            inner.bind("<Configure>", lambda e, cv=canvas: (
                cv.configure(scrollregion=cv.bbox("all")),
                cv.yview_moveto(1.0)
            ))
            self.panels[chat_id] = (f, inner, canvas)
        return self.panels[chat_id]

    def _switch(self, chat_id: str):
        # hide current
        if self.active in self.panels:
            self.panels[self.active][0].pack_forget()

        self.active = chat_id
        self.unread[chat_id] = 0

        # update header
        icon = "🌐" if chat_id == "Global" else ("👥" if chat_id in self.groups else "👤")
        self.chat_title.config(text=f"{icon} {chat_id}")

        # show / hide leave button
        if chat_id in self.groups:
            self.leave_btn.pack(side="right")
        else:
            self.leave_btn.pack_forget()

        # show panel
        frame, inner, canvas = self._get_panel(chat_id)
        frame.pack(fill="both", expand=True)
        self.win.after(50, lambda: canvas.yview_moveto(1.0))

        self._rebuild_sidebar()

    # ── Bubble rendering ──────────────────────────────────────────────────────
    def _bubble(self, chat_id: str, ts: str, sender: str, body: str,
                own: bool = False, is_system: bool = False,
                image=None, audio_data: bytes = None,
                file_name: str = None, file_data: bytes = None):

        _, inner, canvas = self._get_panel(chat_id)

        row = tk.Frame(inner, bg=BG)
        row.pack(fill="x", padx=8, pady=4)

        if is_system:
            tk.Label(row, text=f"── {body} ──", font=FONT_SMALL,
                     fg=SYS_FG, bg=BG).pack()
            if self.active != chat_id:
                self.unread[chat_id] = self.unread.get(chat_id, 0) + 1
                self._rebuild_sidebar()
            return

        anchor = "e" if own else "w"
        bub_bg = OWN_BG if own else OTH_BG

        bubble = tk.Frame(row, bg=bub_bg, padx=10, pady=6)
        bubble.pack(anchor=anchor, padx=4)

        if not own:
            tk.Label(bubble, text=sender, font=FONT_BOLD,
                     fg=ACCENT2, bg=bub_bg).pack(anchor="w")

        if image is not None:
            tk.Label(bubble, image=image, bg=bub_bg).pack(anchor="w")
            bubble._img_ref = image  # keep ref

        elif audio_data is not None:
            af = tk.Frame(bubble, bg=bub_bg)
            af.pack(anchor="w")
            tk.Label(af, text="🎵 Voice message", font=FONT, fg=TEXT, bg=bub_bg).pack(side="left")
            captured = audio_data
            tk.Button(af, text="▶ Play", font=FONT_SMALL, bg=CARD, fg=TEXT,
                      relief="flat", cursor="hand2", padx=6,
                      command=lambda d=captured: self._play_audio(d)).pack(side="left", padx=(8,0))

        elif file_data is not None and file_name is not None:
            ff = tk.Frame(bubble, bg=bub_bg)
            ff.pack(anchor="w")
            kb = len(file_data) / 1024
            tk.Label(ff, text=f"📄 {file_name} ({kb:.1f} KB)",
                     font=FONT, fg=TEXT, bg=bub_bg).pack(side="left")
            tk.Button(ff, text="💾 Save", font=FONT_SMALL, bg=CARD, fg=TEXT,
                      relief="flat", cursor="hand2", padx=6,
                      command=lambda n=file_name, d=file_data: self._save_file(n, d)
                      ).pack(side="left", padx=(8,0))
        else:
            tk.Label(bubble, text=body, font=FONT, fg=TEXT,
                     bg=bub_bg, wraplength=500, justify="left").pack(anchor="w")

        tk.Label(bubble, text=ts, font=FONT_TIME, fg=DIM, bg=bub_bg).pack(anchor="e")

        if self.active != chat_id and not own:
            self.unread[chat_id] = self.unread.get(chat_id, 0) + 1
            self._rebuild_sidebar()
        elif self.active == chat_id:
            self.win.after(30, lambda: canvas.yview_moveto(1.0))

    # ── Network dispatch ──────────────────────────────────────────────────────
    def _recv_loop(self):
        while self.running:
            try:
                hdr, data = recv_packet(self.sock)
                if hdr is None:
                    break
                self.win.after(0, self._dispatch, hdr.strip(), data)
            except Exception:
                break
        if self.running:
            self.win.after(0, self._disconnected)

    def _dispatch(self, msg: str, data: bytes):
        if not msg:
            return
        parts = msg.split("|")
        ptype = parts[0]

        if ptype in ("MSG", "HISTORY"):
            # MSG|[ts]|sender|body
            if len(parts) < 4:
                return
            ts, sender, body = parts[1], parts[2], "|".join(parts[3:])
            own = (sender == self.username)
            self._bubble("Global", ts, sender, body, own=own)

        elif ptype == "DM":
            ts, sender, body = parts[1], parts[2], "|".join(parts[3:])
            self._bubble(sender, ts, sender, body, own=False)

        elif ptype == "DM_SENT":
            ts, recip, body = parts[1], parts[2], "|".join(parts[3:])
            self._bubble(recip, ts, "You", body, own=True)

        elif ptype == "GROUP_MSG":
            if len(parts) < 5:
                return
            ts, group, sender, body = parts[1], parts[2], parts[3], "|".join(parts[4:])
            own = (sender == self.username)
            self._bubble(group, ts, sender, body, own=own)

        elif ptype in ("SYSTEM", "ANNOUNCE"):
            ts, body = parts[1], "|".join(parts[3:])
            self._bubble("Global", ts, "System", body, is_system=True)

        elif ptype == "GROUP_INVITE":
            ts, gname, inviter = parts[1], parts[2], parts[3]
            if gname not in self.groups:
                self.groups.append(gname)
                self._rebuild_sidebar()
            self._bubble("Global", ts, "System",
                         f"You were added to group '{gname}' by {inviter}.", is_system=True)

        elif ptype == "USERLIST":
            self.users = parts[1].split(",") if len(parts) > 1 and parts[1] else []
            self._rebuild_sidebar()

        elif ptype == "GROUPLIST":
            if len(parts) > 1 and parts[1]:
                try:
                    gdata = json.loads(parts[1])
                    self.groups = [
                        g for g, d in gdata.items()
                        if self.username in d.get("members", [])
                    ]
                except Exception:
                    pass
            self._rebuild_sidebar()

        elif ptype == "GROUP_RESULT":
            action, result, gname = parts[1], parts[2], parts[3]
            if result == "OK":
                if action in ("CREATE", "JOIN") and gname not in self.groups:
                    self.groups.append(gname)
                    self._rebuild_sidebar()
                    self._switch(gname)
                elif action == "LEAVE" and gname in self.groups:
                    self.groups.remove(gname)
                    if self.active == gname:
                        self._switch("Global")
                    self._rebuild_sidebar()
            else:
                msgs = {"EXISTS": "Group already exists.", "NOT_FOUND": "Group not found."}
                messagebox.showwarning("Group", msgs.get(result, f"Error: {result}"), parent=self.win)

        elif ptype in ("FILE_DATA", "FILE_SENT"):
            # FILE_DATA|[ts]|sender|recip|filename|size  + binary
            if len(parts) < 6 or data is None:
                return
            ts, sender, recip, fname = parts[1], parts[2], parts[3], parts[4]
            is_group = recip in self.groups
            chat_id = recip if is_group else (sender if sender != self.username else recip)
            own = (sender == self.username)
            disp = "You" if own else sender
            ext = os.path.splitext(fname)[1].lower()

            if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
                try:
                    from PIL import Image, ImageTk
                    img = Image.open(io.BytesIO(data))
                    img.thumbnail((280, 280))
                    tk_img = ImageTk.PhotoImage(img)
                    self._bubble(chat_id, ts, disp, "", own=own, image=tk_img)
                except ImportError:
                    self._bubble(chat_id, ts, disp, f"[Image] {fname}", own=own)
            elif ext == ".wav":
                self._bubble(chat_id, ts, disp, "", own=own, audio_data=data)
            else:
                self._bubble(chat_id, ts, disp, "", own=own,
                             file_name=fname, file_data=data)

    # ── Send ──────────────────────────────────────────────────────────────────
    def _send_msg(self):
        text = self.input_var.get().strip()
        if not text:
            return
        self.input_var.set("")
        if self.active == "Global":
            send_text(self.sock, text)
        elif self.active in self.groups:
            send_text(self.sock, f"GROUP_MSG|{self.active}|{text}")
        else:
            send_text(self.sock, f"@{self.active} {text}")

    # ── File attachment (pick → preview → send) ───────────────────────────────
    def _pick_file(self):
        if self.active == "Global":
            messagebox.showinfo("Info", "Files cannot be sent to Global chat.", parent=self.win)
            return
        path = filedialog.askopenfilename(parent=self.win, title="Select File")
        if not path:
            return
        if os.path.getsize(path) > 20 * 1024 * 1024:
            messagebox.showerror("Error", "File exceeds 20 MB limit.", parent=self.win)
            return
        with open(path, "rb") as f:
            raw = f.read()
        fname = os.path.basename(path)
        self._pending_file = (fname, raw)
        kb = len(raw) / 1024
        ext = os.path.splitext(fname)[1].lower()

        # Show thumbnail if image
        self.preview_thumb.config(image="", text="")
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
            try:
                from PIL import Image, ImageTk
                img = Image.open(io.BytesIO(raw))
                img.thumbnail((40, 40))
                tk_img = ImageTk.PhotoImage(img)
                self.preview_thumb.config(image=tk_img)
                self.preview_thumb._img = tk_img   # prevent GC
            except Exception:
                self.preview_thumb.config(text="🖼️", font=("Segoe UI Emoji", 18))
        else:
            self.preview_thumb.config(text="📄", font=("Segoe UI Emoji", 18))

        self.preview_lbl.config(text=f"{fname}  ({kb:.1f} KB)")
        # Show preview bar at row=2 (between chat_area=1 and input=3)
        self.preview_bar.grid(row=2, column=0, sticky="ew")

    def _cancel_file(self):
        self._pending_file = None
        self.preview_thumb.config(image="", text="")
        self.preview_bar.grid_forget()

    def _send_pending_file(self):
        if not self._pending_file:
            return
        if self.active == "Global":
            messagebox.showinfo("Info", "Files cannot be sent to Global chat.", parent=self.win)
            return
        fname, raw = self._pending_file
        send_binary(self.sock, f"FILE_DATA|{self.active}|{fname}", raw)
        self._cancel_file()

    # Old alias kept for safety
    def _send_file(self):
        self._pick_file()

    # ── Voice recording — click toggle + timer bar ───────────────────────
    def _voice_toggle(self):
        """Click once to start, click again to stop+send."""
        if self.active == "Global":
            messagebox.showinfo("Info", "Voice messages cannot be sent to Global chat.",
                                parent=self.win)
            return
        if not self._recording:
            self._voice_start_rec()
        else:
            self._voice_stop_send()

    def _voice_start_rec(self):
        try:
            import sounddevice as sd
        except ImportError:
            messagebox.showerror("Error",
                "sounddevice not installed. Run: pip install sounddevice soundfile numpy",
                parent=self.win)
            return
        try:
            self._recording    = True
            self._audio_frames = []
            self._rec_seconds  = 0
            self.voice_btn.config(text="⏹️", bg=RED)   # stop icon when active
            # Show timer bar at row=2
            self.voice_bar.grid(row=2, column=0, sticky="ew")
            self._voice_tick()  # start live counter

            def _cb(indata, frames, t, status):
                if self._recording:
                    self._audio_frames.append(indata.copy())

            self._audio_stream = sd.InputStream(samplerate=44100, channels=1, callback=_cb)
            self._audio_stream.start()
        except Exception as e:
            self._recording = False
            self.voice_btn.config(text="🎤", bg=PANEL)
            self.voice_bar.grid_forget()
            messagebox.showerror("Mic Error", str(e), parent=self.win)

    def _voice_tick(self):
        """Update the recording timer every second."""
        if not self._recording:
            return
        self._rec_seconds += 1
        m, s = divmod(self._rec_seconds, 60)
        self.voice_timer_lbl.config(text=f"{m}:{s:02d}")
        self.win.after(1000, self._voice_tick)

    def _voice_cancel(self):
        """Discard recording without sending."""
        self._recording = False
        try:
            if self._audio_stream:
                self._audio_stream.stop()
                self._audio_stream.close()
        except Exception:
            pass
        self._audio_frames = []
        self.voice_btn.config(text="🎤", bg=PANEL)
        self.voice_bar.grid_forget()

    def _voice_stop_send(self):
        """Stop recording and send the audio."""
        if not self._recording:
            return
        self._recording = False
        self.voice_btn.config(text="🎤", bg=PANEL)
        self.voice_bar.grid_forget()
        try:
            if self._audio_stream:
                self._audio_stream.stop()
                self._audio_stream.close()
        except Exception:
            pass
        if not self._audio_frames:
            return
        try:
            import numpy as np
            import soundfile as sf
            audio = np.concatenate(self._audio_frames, axis=0)
            buf = io.BytesIO()
            sf.write(buf, audio, 44100, format="WAV")
            raw = buf.getvalue()
            fname = f"voice_{int(time.time())}.wav"
            send_binary(self.sock, f"FILE_DATA|{self.active}|{fname}", raw)
        except Exception as e:
            messagebox.showerror("Recording Error", str(e), parent=self.win)

    # Keep old bindings alive (no-ops now)
    def _voice_start(self, _e): pass
    def _voice_stop(self, _e):  pass

    def _play_audio(self, data: bytes):
        try:
            import sounddevice as sd
            import soundfile as sf
            import io as _io
            audio, fs = sf.read(_io.BytesIO(data))
            sd.play(audio, fs)
        except Exception as e:
            messagebox.showerror("Playback Error", str(e), parent=self.win)

    # ── Emoji picker — colored via PIL ────────────────────────────────────────
    def _make_emoji_img(self, char: str, size: int = 36):
        """Render a colored emoji via Pillow (Segoe UI Emoji font on Windows)."""
        if char in self._emoji_imgs:
            return self._emoji_imgs[char]
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageTk
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            font_path = "C:/Windows/Fonts/seguiemj.ttf"
            font = ImageFont.truetype(font_path, size - 6)
            draw.text((2, 1), char, font=font, embedded_color=True)
            tk_img = ImageTk.PhotoImage(img)
            self._emoji_imgs[char] = tk_img
            return tk_img
        except Exception:
            return None

    def _emoji_picker(self):
        top = tk.Toplevel(self.win)
        top.title("Emoji")
        top.configure(bg=CARD)
        top.resizable(False, False)
        top.attributes("-topmost", True)
        COLS = 6
        for i, em in enumerate(EMOJIS):
            r, c = divmod(i, COLS)
            img = self._make_emoji_img(em, 36)
            if img:
                btn = tk.Button(top, image=img, bg=CARD, relief="flat",
                                cursor="hand2", bd=0,
                                command=lambda e=em, w=top: (
                                    self.input_var.set(self.input_var.get() + e),
                                    w.destroy()))
                btn._img = img   # prevent GC
            else:
                btn = tk.Button(top, text=em, font=FONT_EMOJI, bg=CARD, fg=TEXT,
                                relief="flat", cursor="hand2",
                                command=lambda e=em, w=top: (
                                    self.input_var.set(self.input_var.get() + e),
                                    w.destroy()))
            btn.grid(row=r, column=c, padx=4, pady=4)

    # ── File save ─────────────────────────────────────────────────────────────
    def _save_file(self, fname: str, data: bytes):
        path = filedialog.asksaveasfilename(parent=self.win, initialfile=fname)
        if path:
            with open(path, "wb") as f:
                f.write(data)
            messagebox.showinfo("Saved", f"Saved to {path}", parent=self.win)

    # ── Groups ────────────────────────────────────────────────────────────────
    def _new_group(self):
        dlg = _InputDialog(self.win, "New Group",
                           "Group name:", "Members (comma separated):")
        if dlg.result:
            gname, raw_members = dlg.result
            members = [m.strip() for m in raw_members.split(",") if m.strip()]
            send_text(self.sock, f"GROUP_CREATE|{gname}|{','.join(members)}")

    def _join_group(self):
        dlg = _SimpleInput(self.win, "Join Group", "Enter group name:")
        if dlg.result:
            send_text(self.sock, f"GROUP_JOIN|{dlg.result.strip()}")

    def _leave_group(self):
        if self.active in self.groups:
            if messagebox.askyesno("Leave", f"Leave '{self.active}'?", parent=self.win):
                send_text(self.sock, f"GROUP_LEAVE|{self.active}")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def _disconnected(self):
        self.running = False
        messagebox.showerror("Disconnected", "Server closed the connection.", parent=self.win)
        self._close()

    def _close(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass
        self.win.destroy()
        self.root.destroy()


# ── Simple dialogs ─────────────────────────────────────────────────────────────
class _SimpleInput:
    def __init__(self, parent, title, prompt):
        self.result = None
        top = tk.Toplevel(parent)
        top.title(title)
        top.configure(bg=BG)
        top.resizable(False, False)
        top.grab_set()
        tk.Label(top, text=prompt, font=FONT, fg=TEXT, bg=BG).pack(padx=20, pady=(16, 4))
        e = tk.Entry(top, font=FONT, bg=CARD, fg=TEXT,
                     insertbackground=TEXT, relief="flat", bd=6)
        e.pack(padx=20, ipady=6, pady=(0, 12))
        e.focus()

        def _ok():
            self.result = e.get().strip() or None
            top.destroy()

        tk.Button(top, text="OK", font=FONT_BOLD, bg=ACCENT2, fg=TEXT,
                  relief="flat", cursor="hand2", padx=16, pady=6,
                  command=_ok).pack(pady=(0, 12))
        e.bind("<Return>", lambda ev: _ok())
        top.wait_window()


class _InputDialog:
    def __init__(self, parent, title, label1, label2):
        self.result = None
        top = tk.Toplevel(parent)
        top.title(title)
        top.configure(bg=BG)
        top.resizable(False, False)
        top.grab_set()

        for lbl in (label1, label2):
            tk.Label(top, text=lbl, font=FONT, fg=TEXT, bg=BG, anchor="w").pack(
                fill="x", padx=20, pady=(12, 2))
            e = tk.Entry(top, font=FONT, bg=CARD, fg=TEXT,
                         insertbackground=TEXT, relief="flat", bd=6)
            e.pack(fill="x", padx=20, ipady=6)
            if lbl == label1:
                self._e1 = e
                e.focus()
            else:
                self._e2 = e

        def _ok():
            v1 = self._e1.get().strip()
            v2 = self._e2.get().strip()
            if v1:
                self.result = (v1, v2)
            top.destroy()

        tk.Button(top, text="Create", font=FONT_BOLD, bg=ACCENT, fg=TEXT,
                  relief="flat", cursor="hand2", padx=16, pady=8,
                  command=_ok).pack(pady=16)
        self._e1.bind("<Return>", lambda ev: self._e2.focus())
        self._e2.bind("<Return>", lambda ev: _ok())
        top.wait_window()
