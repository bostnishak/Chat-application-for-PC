"""
Modern ChatWindow using CustomTkinter.
Supports Image inline viewing, Voice messages, separate chat instances.
"""

import socket
import threading
import json
import time
import io
import os
import struct
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
import sounddevice as sd
import soundfile as sf
import numpy as np

from client_network import send_text, send_file, recv_packet

# ─────────────────────────────────────────────
# Colors & Styles
# ─────────────────────────────────────────────
BG_SIDEBAR = "#1f2326"
BG_MAIN = "#14171a"
BG_HEADER = "#1f2326"
BG_BUBBLE_OWN = "#2b5278"
BG_BUBBLE_OTHER = "#2b2d31"
TEXT_COLOR = "#ffffff"
TEXT_DIM = "#99aab5"
ACCENT = "#5865F2"  # Discord-like blurple

ctk.set_appearance_mode("Dark")


class ChatWindow:
    def __init__(self, root: ctk.CTk, sock: socket.socket, username: str, init_history: str):
        self.root = root
        self.sock = sock
        self.username = username
        self.running = True

        # State
        self.users = []
        self.groups = []
        self.unread = {}
        self.active_chat = "Global"

        # Chat Frames: mapping chat_id -> ctk.CTkScrollableFrame
        self.chat_frames = {}

        # Audio recording state
        self.is_recording = False
        self.audio_stream = None
        self.audio_frames = []

        # Setup main window
        self.window = ctk.CTkToplevel(self.root)
        self.window.title(f"Chat App - {self.username}")
        self.window.geometry("1100x700")
        self.window.configure(fg_color=BG_MAIN)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        # Center
        self.window.update_idletasks()
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        x = (sw - 1100) // 2
        y = (sh - 700) // 2
        self.window.geometry(f"+{x}+{y}")

        self._build_ui()
        self._create_chat_frame("Global")

        # Process initial history
        if init_history:
            for packet in init_history.split("\n"):
                if packet:
                    self._dispatch(packet, None)

        # Start recv thread
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.recv_thread.start()

    # ── UI BUILDING ──────────────────────────────────────────────
    def _build_ui(self):
        # Base grid layout: Sidebar (250px) | Main Chat Area
        self.window.grid_columnconfigure(1, weight=1)
        self.window.grid_rowconfigure(0, weight=1)

        # ── SIDEBAR ──
        self.sidebar = ctk.CTkFrame(self.window, width=260, corner_radius=0, fg_color=BG_SIDEBAR)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(2, weight=1)  # the list area expands

        # Sidebar Header (User Info)
        hdr_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        hdr_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(20, 10))
        
        ctk.CTkLabel(hdr_frame, text=f"👤 {self.username}", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")

        # Sidebar Search
        self.search_entry = ctk.CTkEntry(self.sidebar, placeholder_text="Search...", height=35, corner_radius=8)
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=15, pady=10)
        self.search_entry.bind("<KeyRelease>", self._on_search)

        # Sidebar Contact List
        self.contact_list_frame = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent")
        self.contact_list_frame.grid(row=2, column=0, sticky="nsew", padx=5)

        # Sidebar Footer (Groups)
        ftr_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        ftr_frame.grid(row=3, column=0, sticky="ew", padx=15, pady=15)
        
        btn_new_group = ctk.CTkButton(ftr_frame, text="➕ New Group", width=110, fg_color="#4CAF50", hover_color="#45a049", command=self._prompt_create_group)
        btn_new_group.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        btn_join_group = ctk.CTkButton(ftr_frame, text="🔗 Join", width=110, fg_color="#2196F3", hover_color="#1E88E5", command=self._prompt_join_group)
        btn_join_group.pack(side="right", fill="x", expand=True, padx=(5, 0))

        # ── MAIN CHAT AREA ──
        self.main_area = ctk.CTkFrame(self.window, corner_radius=0, fg_color=BG_MAIN)
        self.main_area.grid(row=0, column=1, sticky="nsew")
        self.main_area.grid_rowconfigure(1, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)

        # Chat Header
        self.chat_header = ctk.CTkFrame(self.main_area, height=60, corner_radius=0, fg_color=BG_HEADER)
        self.chat_header.grid(row=0, column=0, sticky="ew")
        self.chat_header.pack_propagate(False)

        self.chat_title_lbl = ctk.CTkLabel(self.chat_header, text="🌐 Global", font=ctk.CTkFont(size=18, weight="bold"))
        self.chat_title_lbl.pack(side="left", padx=20)
        
        self.leave_btn = ctk.CTkButton(self.chat_header, text="🚪 Leave Group", width=100, fg_color="#F44336", hover_color="#D32F2F", command=self._leave_group)
        self.leave_btn.pack(side="right", padx=20)
        self.leave_btn.pack_forget()  # Hidden initially

        # Chat History Container (where the separate scrollable frames will be placed)
        self.history_container = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.history_container.grid(row=1, column=0, sticky="nsew")

        # Input Area
        self.input_area = ctk.CTkFrame(self.main_area, height=70, corner_radius=0, fg_color=BG_HEADER)
        self.input_area.grid(row=2, column=0, sticky="ew")
        self.input_area.grid_columnconfigure(2, weight=1)

        # Attachment Button
        self.btn_attach = ctk.CTkButton(self.input_area, text="📎", width=40, height=40, font=ctk.CTkFont(size=20), fg_color="transparent", hover_color=BG_BUBBLE_OTHER, command=self._send_file)
        self.btn_attach.grid(row=0, column=0, padx=(15, 5), pady=15)

        # Emoji Button
        self.btn_emoji = ctk.CTkButton(self.input_area, text="😊", width=40, height=40, font=ctk.CTkFont(size=20), fg_color="transparent", hover_color=BG_BUBBLE_OTHER, command=self._show_emoji_picker)
        self.btn_emoji.grid(row=0, column=1, padx=5, pady=15)

        # Text Input
        self.input_entry = ctk.CTkEntry(self.input_area, placeholder_text="Type a message...", height=40, corner_radius=20, font=ctk.CTkFont(size=14))
        self.input_entry.grid(row=0, column=2, sticky="ew", padx=10, pady=15)
        self.input_entry.bind("<Return>", lambda e: self._send_text_message())

        # Voice Record Button
        self.btn_voice = ctk.CTkButton(self.input_area, text="🎤", width=40, height=40, font=ctk.CTkFont(size=20), fg_color="transparent", hover_color="#f44336")
        self.btn_voice.grid(row=0, column=3, padx=(5, 15), pady=15)
        self.btn_voice.bind("<ButtonPress-1>", self._start_voice_record)
        self.btn_voice.bind("<ButtonRelease-1>", self._stop_voice_record)

    def _create_chat_frame(self, chat_id: str):
        if chat_id not in self.chat_frames:
            frame = ctk.CTkScrollableFrame(self.history_container, fg_color="transparent")
            self.chat_frames[chat_id] = frame
        return self.chat_frames[chat_id]

    def _switch_chat(self, chat_id: str):
        # Hide current
        if self.active_chat in self.chat_frames:
            self.chat_frames[self.active_chat].pack_forget()

        self.active_chat = chat_id
        
        # Reset unread
        if chat_id in self.unread:
            self.unread[chat_id] = 0
            self._rebuild_conv_list()

        # Update Header
        prefix = "🌐" if chat_id == "Global" else "👤"
        if chat_id in self.groups:
            prefix = "👥"
            self.leave_btn.pack(side="right", padx=20)
        else:
            self.leave_btn.pack_forget()

        self.chat_title_lbl.configure(text=f"{prefix} {chat_id}")

        # Show new frame
        frame = self._create_chat_frame(chat_id)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Scroll to bottom
        frame._parent_canvas.yview_moveto(1.0)

    # ── CONTACT LIST LOGIC ──────────────────────────────────────
    def _on_search(self, event=None):
        self._rebuild_conv_list()

    def _rebuild_conv_list(self):
        query = self.search_entry.get().lower()

        # Clear existing
        for widget in self.contact_list_frame.winfo_children():
            widget.destroy()

        def add_item(name, icon):
            if query and query not in name.lower():
                return
            
            bg = ACCENT if name == self.active_chat else "transparent"
            hover = ACCENT if name == self.active_chat else BG_MAIN
            
            btn = ctk.CTkButton(self.contact_list_frame, text=f"{icon} {name}", anchor="w", fg_color=bg, hover_color=hover, font=ctk.CTkFont(size=14), command=lambda n=name: self._switch_chat(n))
            btn.pack(fill="x", pady=2, ipady=4)

            # Add unread badge if needed
            unread_count = self.unread.get(name, 0)
            if unread_count > 0 and name != self.active_chat:
                badge = ctk.CTkLabel(btn, text=str(unread_count), fg_color="#F44336", text_color="white", corner_radius=10, width=20, height=20, font=ctk.CTkFont(size=11, weight="bold"))
                badge.place(relx=0.9, rely=0.5, anchor="center")

        add_item("Global", "🌐")
        
        if self.groups:
            ctk.CTkLabel(self.contact_list_frame, text="GROUPS", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_DIM).pack(anchor="w", pady=(10, 0), padx=5)
            for g in sorted(self.groups):
                add_item(g, "👥")

        users_list = [u for u in self.users if u != self.username]
        if users_list:
            ctk.CTkLabel(self.contact_list_frame, text="DIRECT MESSAGES", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_DIM).pack(anchor="w", pady=(10, 0), padx=5)
            for u in sorted(users_list):
                add_item(u, "👤")

    # ── NETWORK RECEIVE LOOP ─────────────────────────────────────
    def _recv_loop(self):
        while self.running:
            try:
                hdr, data = recv_packet(self.sock)
                if hdr is None:
                    break
                msg = hdr.strip()
                if msg:
                    self.window.after(0, self._dispatch, msg, data)
            except Exception as e:
                print("Recv loop error:", e)
                break
        if self.running:
            self.window.after(0, self._connection_lost)

    def _connection_lost(self):
        self.running = False
        messagebox.showerror("Disconnected", "Server closed the connection.", parent=self.window)
        self.window.destroy()
        self.root.destroy()

    def _dispatch(self, message: str, binary_data: bytes = None):
        parts = message.split("|")
        ptype = parts[0]

        if ptype == "MSG":
            # MSG|[ts]|sender|body
            ts, sender, body = parts[1], parts[2], "|".join(parts[3:])
            own = (sender == self.username)
            self._handle_msg("Global", ts, sender, body, own)

        elif ptype == "DM":
            # DM|[ts]|sender|body
            ts, sender, body = parts[1], parts[2], "|".join(parts[3:])
            self._handle_msg(sender, ts, sender, body, own=False)

        elif ptype == "DM_SENT":
            ts, recip, body = parts[1], parts[2], "|".join(parts[3:])
            self._handle_msg(recip, ts, "You", body, own=True)

        elif ptype == "GROUP_MSG":
            ts, group, sender, body = parts[1], parts[2], parts[3], "|".join(parts[4:])
            own = (sender == self.username)
            display_sender = "You" if own else sender
            self._handle_msg(group, ts, display_sender, body, own=own)

        elif ptype == "FILE_DATA":
            # FILE_DATA|[ts]|sender|recip|filename|size
            ts, sender, recip, filename = parts[1], parts[2], parts[3], parts[4]
            is_group = recip in self.groups
            chat_id = recip if is_group else (sender if sender != self.username else recip)
            own = (sender == self.username)
            display_sender = "You" if own else sender
            self._handle_file(chat_id, ts, display_sender, filename, binary_data, own)

        elif ptype == "SYSTEM" or ptype == "ANNOUNCE":
            ts, sender, body = parts[1], parts[2], "|".join(parts[3:])
            self._handle_msg("Global", ts, sender, body, own=False, is_system=True)

        elif ptype == "USERLIST":
            users = parts[1].split(",") if len(parts) > 1 and parts[1] else []
            self.users = users
            self._rebuild_conv_list()

        elif ptype == "GROUPLIST":
            if len(parts) > 1 and parts[1]:
                try:
                    data = json.loads(parts[1])
                    self.groups = [g for g, d in data.items() if self.username in d.get("members", [])]
                except Exception:
                    pass
            self._rebuild_conv_list()

        elif ptype == "GROUP_RESULT":
            action, result, gname = parts[1], parts[2], parts[3]
            if result == "OK":
                if action in ["JOIN", "CREATE"] and gname not in self.groups:
                    self.groups.append(gname)
                    self._rebuild_conv_list()
                    self._switch_chat(gname)
                elif action == "LEAVE" and gname in self.groups:
                    self.groups.remove(gname)
                    if self.active_chat == gname:
                        self._switch_chat("Global")
                    self._rebuild_conv_list()
            else:
                messagebox.showerror("Group Error", f"Action failed: {result}")

    # ── MESSAGE RENDERING ────────────────────────────────────────
    def _increment_unread(self, chat_id: str):
        if self.active_chat != chat_id:
            self.unread[chat_id] = self.unread.get(chat_id, 0) + 1
            self._rebuild_conv_list()

    def _create_bubble_container(self, target_frame: ctk.CTkScrollableFrame, ts: str, sender: str, own: bool, is_system: bool):
        # Outer frame to align left/right/center
        row_frame = ctk.CTkFrame(target_frame, fg_color="transparent")
        row_frame.pack(fill="x", padx=5, pady=5)
        
        if is_system:
            bubble = ctk.CTkFrame(row_frame, fg_color="#36393e", corner_radius=8)
            bubble.pack(anchor="center", pady=2)
            lbl = ctk.CTkLabel(bubble, text=f"{ts} [System] {sender}", text_color=TEXT_DIM, font=ctk.CTkFont(size=11, slant="italic"))
            lbl.pack(padx=10, pady=5)
            return bubble

        anchor = "e" if own else "w"
        color = BG_BUBBLE_OWN if own else BG_BUBBLE_OTHER

        bubble = ctk.CTkFrame(row_frame, fg_color=color, corner_radius=15)
        bubble.pack(anchor=anchor, padx=10)

        # Header: Sender + Time
        hdr = ctk.CTkFrame(bubble, fg_color="transparent", height=15)
        hdr.pack(fill="x", padx=10, pady=(5, 0))
        
        sender_color = "#4CAF50" if own else ACCENT
        ctk.CTkLabel(hdr, text=sender, font=ctk.CTkFont(size=12, weight="bold"), text_color=sender_color).pack(side="left")
        ctk.CTkLabel(hdr, text=ts, font=ctk.CTkFont(size=10), text_color=TEXT_DIM).pack(side="right", padx=(10, 0))

        return bubble

    def _handle_msg(self, chat_id: str, ts: str, sender: str, body: str, own: bool, is_system: bool = False):
        frame = self._create_chat_frame(chat_id)
        bubble = self._create_bubble_container(frame, ts, sender, own, is_system)
        
        if not is_system:
            txt_lbl = ctk.CTkLabel(bubble, text=body, text_color=TEXT_COLOR, font=ctk.CTkFont(size=14), justify="left", wraplength=400)
            txt_lbl.pack(padx=12, pady=(2, 8), anchor="w")

        if not own:
            self._increment_unread(chat_id)
        
        if self.active_chat == chat_id:
            frame._parent_canvas.yview_moveto(1.0)

    def _handle_file(self, chat_id: str, ts: str, sender: str, filename: str, data: bytes, own: bool):
        frame = self._create_chat_frame(chat_id)
        bubble = self._create_bubble_container(frame, ts, sender, own, False)
        
        ext = os.path.splitext(filename)[1].lower()

        if ext in [".png", ".jpg", ".jpeg", ".gif"]:
            # Render Image
            try:
                img = Image.open(io.BytesIO(data))
                img.thumbnail((250, 250))
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                img_lbl = ctk.CTkLabel(bubble, image=ctk_img, text="")
                img_lbl.pack(padx=10, pady=(2, 8))
            except Exception as e:
                ctk.CTkLabel(bubble, text="[Image format not supported]", text_color="#F44336").pack(padx=10, pady=5)
        
        elif ext in [".wav"]:
            # Render Audio Player
            audio_frame = ctk.CTkFrame(bubble, fg_color="transparent")
            audio_frame.pack(padx=10, pady=(2, 8), fill="x")
            
            ctk.CTkLabel(audio_frame, text="🎵 Voice Message", font=ctk.CTkFont(size=12)).pack(side="left")
            play_btn = ctk.CTkButton(audio_frame, text="▶ Play", width=60, height=24, command=lambda d=data: self._play_audio(d))
            play_btn.pack(side="right", padx=(10, 0))

        else:
            # Generic File
            file_frame = ctk.CTkFrame(bubble, fg_color="transparent")
            file_frame.pack(padx=10, pady=(2, 8), fill="x")
            
            size_kb = len(data) / 1024
            ctk.CTkLabel(file_frame, text=f"📎 {filename} ({size_kb:.1f} KB)", font=ctk.CTkFont(size=12)).pack(side="left")
            save_btn = ctk.CTkButton(file_frame, text="💾 Save", width=60, height=24, command=lambda f=filename, d=data: self._save_file(f, d))
            save_btn.pack(side="right", padx=(10, 0))

        if not own:
            self._increment_unread(chat_id)
        if self.active_chat == chat_id:
            frame._parent_canvas.yview_moveto(1.0)

    # ── MEDIA ACTIONS ────────────────────────────────────────────
    def _play_audio(self, binary_data: bytes):
        try:
            data, fs = sf.read(io.BytesIO(binary_data))
            sd.play(data, fs)
        except Exception as e:
            messagebox.showerror("Audio Error", str(e), parent=self.window)

    def _start_voice_record(self, event):
        self.btn_voice.configure(text="🔴", text_color="#f44336")
        self.is_recording = True
        self.audio_frames = []
        try:
            self.audio_stream = sd.InputStream(samplerate=44100, channels=1, callback=self._audio_callback)
            self.audio_stream.start()
        except Exception as e:
            self.is_recording = False
            messagebox.showerror("Mic Error", str(e), parent=self.window)

    def _audio_callback(self, indata, frames, time, status):
        if self.is_recording:
            self.audio_frames.append(indata.copy())

    def _stop_voice_record(self, event):
        self.btn_voice.configure(text="🎤", text_color=TEXT_COLOR)
        if not self.is_recording:
            return
        self.is_recording = False
        try:
            self.audio_stream.stop()
            self.audio_stream.close()
            
            if not self.audio_frames: return
            audio_data = np.concatenate(self.audio_frames, axis=0)
            
            buf = io.BytesIO()
            sf.write(buf, audio_data, 44100, format='WAV')
            binary_data = buf.getvalue()
            
            filename = f"voice_{int(time.time())}.wav"
            self._send_binary_payload(filename, binary_data)
        except Exception as e:
            messagebox.showerror("Recording Error", str(e), parent=self.window)

    def _send_file(self):
        path = filedialog.askopenfilename(parent=self.window, title="Select File to Send")
        if not path:
            return
        size = os.path.getsize(path)
        if size > 20 * 1024 * 1024:
            messagebox.showerror("Error", "File exceeds 20MB limit.", parent=self.window)
            return
            
        with open(path, "rb") as f:
            data = f.read()
        filename = os.path.basename(path)
        self._send_binary_payload(filename, data)

    def _send_binary_payload(self, filename: str, data: bytes):
        target = self.active_chat
        if target == "Global":
            messagebox.showinfo("Not Supported", "Files cannot be sent to Global chat.", parent=self.window)
            return
        
        try:
            payload = f"FILE_DATA|{target}|{filename}".encode("utf-8")
            header = struct.pack("!I", len(payload))
            
            # Send framing: HeaderLen -> HeaderBytes -> DataLen -> DataBytes
            self.sock.sendall(header)
            self.sock.sendall(payload)
            self.sock.sendall(struct.pack("!I", len(data)))
            self.sock.sendall(data)
            
            # Echo it locally immediately to look responsive
            self._handle_file(target, time.strftime("[%H:%M]"), "You", filename, data, own=True)
            
        except Exception as e:
            messagebox.showerror("Send Error", str(e), parent=self.window)

    def _save_file(self, filename: str, data: bytes):
        path = filedialog.asksaveasfilename(parent=self.window, initialfile=filename)
        if path:
            try:
                with open(path, "wb") as f:
                    f.write(data)
                messagebox.showinfo("Success", f"Saved to {path}", parent=self.window)
            except Exception as e:
                messagebox.showerror("Save Error", str(e), parent=self.window)

    # ── SENDING MESSAGES ─────────────────────────────────────────
    def _send_text_message(self):
        text = self.input_entry.get().strip()
        if not text:
            return
        self.input_entry.delete(0, tk.END)

        target = self.active_chat
        if target == "Global":
            send_text(self.sock, text)
        elif target in self.groups:
            send_text(self.sock, f"GROUP_MSG|{target}|{text}")
        else:
            # DM
            send_text(self.sock, f"@{target} {text}")

    # ── GROUPS & EMOJIS ──────────────────────────────────────────
    def _prompt_create_group(self):
        dialog = ctk.CTkInputDialog(text="Enter new group name:", title="New Group")
        name = dialog.get_input()
        if name:
            send_text(self.sock, f"GROUP_CREATE|{name.strip()}")

    def _prompt_join_group(self):
        dialog = ctk.CTkInputDialog(text="Enter group name to join:", title="Join Group")
        name = dialog.get_input()
        if name:
            send_text(self.sock, f"GROUP_JOIN|{name.strip()}")

    def _leave_group(self):
        target = self.active_chat
        if target in self.groups:
            if messagebox.askyesno("Leave Group", f"Are you sure you want to leave {target}?", parent=self.window):
                send_text(self.sock, f"GROUP_LEAVE|{target}")

    def _show_emoji_picker(self):
        top = ctk.CTkToplevel(self.window)
        top.title("Emojis")
        top.geometry("300x200")
        top.resizable(False, False)
        top.attributes("-topmost", True)
        
        # Grid of popular emojis
        emojis = ["😀","😂","🤣","😊","😍","😘","🥰","😎","🤩","😏","🤔","😐","🙄",
                  "😴","😷","🥳","🤯","😱","🤬","💔","❤️","🔥","👍","👎","👏","🤝","🙌"]
                  
        frame = ctk.CTkScrollableFrame(top)
        frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        for i, emj in enumerate(emojis):
            row = i // 5
            col = i % 5
            btn = ctk.CTkButton(frame, text=emj, width=40, height=40, font=ctk.CTkFont(size=20), fg_color="transparent", hover_color=BG_BUBBLE_OTHER)
            btn.grid(row=row, column=col, padx=2, pady=2)
            btn.configure(command=lambda e=emj, w=top: self._insert_emoji(e, w))

    def _insert_emoji(self, emoji_char, window):
        self.input_entry.insert(tk.END, emoji_char)
        window.destroy()
        self.input_entry.focus()

    # ── CLEANUP ──────────────────────────────────────────────────
    def _on_close(self):
        self.running = False
        try:
            self.sock.close()
        except: pass
        self.window.destroy()
        self.root.destroy()
