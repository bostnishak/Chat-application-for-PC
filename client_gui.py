"""
Chat App — Login / Register screen.
Uses only standard tkinter (no CustomTkinter dependency issues).
"""
import socket
import tkinter as tk
from tkinter import messagebox

from client_network import connect_and_login

# ── Palette ────────────────────────────────────────────────────────────────────
BG       = "#080d1a"
PANEL    = "#0d1429"
CARD     = "#111d38"
ACCENT   = "#3d7ae5"
ACCENT_H = "#4d8ef5"
ACCENT2  = "#5865f2"
TEXT     = "#dce6f5"
DIM      = "#7a8ba8"
INPUT_BG = "#080d1a"
BORDER   = "#1e3059"
RED      = "#da3633"

FONT       = ("Segoe UI", 11)
FONT_BOLD  = ("Segoe UI", 12, "bold")
FONT_TITLE = ("Segoe UI", 20, "bold")
FONT_SMALL = ("Segoe UI", 9)


def _entry(parent, show=None):
    e = tk.Entry(parent, font=FONT, bg=INPUT_BG, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT2, bd=4, show=show or "")
    return e


class LoginScreen(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chat App")
        self.configure(bg=BG)
        self.resizable(False, False)
        self._center(420, 580)
        self._build()

    def _center(self, w, h):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=PANEL, pady=24)
        hdr.pack(fill="x")
        tk.Label(hdr, text="💬", font=("Segoe UI Emoji", 36),
                 fg=ACCENT, bg=PANEL).pack()
        tk.Label(hdr, text="Chat App", font=FONT_TITLE,
                 fg=TEXT, bg=PANEL).pack()
        tk.Label(hdr, text="Connect with your team", font=FONT_SMALL,
                 fg=DIM, bg=PANEL).pack(pady=(4, 0))

        # Tab buttons
        tab_row = tk.Frame(self, bg=BG)
        tab_row.pack(fill="x", padx=40, pady=(20, 0))

        self._tab = tk.StringVar(value="login")

        self.btn_login_tab = tk.Button(
            tab_row, text="Login", font=FONT_BOLD,
            bg=ACCENT2, fg=TEXT, relief="flat", bd=0,
            cursor="hand2", padx=20, pady=8,
            command=lambda: self._switch("login")
        )
        self.btn_login_tab.pack(side="left", fill="x", expand=True)

        self.btn_reg_tab = tk.Button(
            tab_row, text="Register", font=FONT_BOLD,
            bg=CARD, fg=DIM, relief="flat", bd=0,
            cursor="hand2", padx=20, pady=8,
            command=lambda: self._switch("register")
        )
        self.btn_reg_tab.pack(side="left", fill="x", expand=True)

        # Forms
        self.form_container = tk.Frame(self, bg=BG)
        self.form_container.pack(fill="both", expand=True, padx=40, pady=20)

        self._build_login_form()
        self._build_register_form()
        self._switch("login")

    def _build_login_form(self):
        f = tk.Frame(self.form_container, bg=BG)
        self._lf = f

        tk.Label(f, text="Username", font=FONT, fg=DIM, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))
        self.log_user = _entry(f)
        self.log_user.pack(fill="x", ipady=8, pady=(0, 16))

        tk.Label(f, text="Password", font=FONT, fg=DIM, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))
        self.log_pass = _entry(f, show="●")
        self.log_pass.pack(fill="x", ipady=8, pady=(0, 24))
        self.log_pass.bind("<Return>", lambda e: self._do_login())

        btn = tk.Button(f, text="Login →", font=FONT_BOLD,
                        bg=ACCENT2, fg=TEXT, relief="flat", bd=0,
                        cursor="hand2", pady=10, command=self._do_login)
        btn.pack(fill="x")
        btn.bind("<Enter>", lambda e: btn.config(bg="#388bfd"))
        btn.bind("<Leave>", lambda e: btn.config(bg=ACCENT2))

    def _build_register_form(self):
        f = tk.Frame(self.form_container, bg=BG)
        self._rf = f

        tk.Label(f, text="Username", font=FONT, fg=DIM, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))
        self.reg_user = _entry(f)
        self.reg_user.pack(fill="x", ipady=8, pady=(0, 12))

        tk.Label(f, text="Password", font=FONT, fg=DIM, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))
        self.reg_pass = _entry(f, show="●")
        self.reg_pass.pack(fill="x", ipady=8, pady=(0, 12))

        tk.Label(f, text="Confirm Password", font=FONT, fg=DIM, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))
        self.reg_pass2 = _entry(f, show="●")
        self.reg_pass2.pack(fill="x", ipady=8, pady=(0, 24))
        self.reg_pass2.bind("<Return>", lambda e: self._do_register())

        btn = tk.Button(f, text="Create Account →", font=FONT_BOLD,
                        bg=ACCENT, fg=TEXT, relief="flat", bd=0,
                        cursor="hand2", pady=10, command=self._do_register)
        btn.pack(fill="x")
        btn.bind("<Enter>", lambda e: btn.config(bg=ACCENT_H))
        btn.bind("<Leave>", lambda e: btn.config(bg=ACCENT))

    def _switch(self, tab: str):
        self._tab.set(tab)
        if tab == "login":
            self._rf.pack_forget()
            self._lf.pack(fill="both", expand=True)
            self.btn_login_tab.config(bg=ACCENT2, fg=TEXT)
            self.btn_reg_tab.config(bg=CARD, fg=DIM)
        else:
            self._lf.pack_forget()
            self._rf.pack(fill="both", expand=True)
            self.btn_reg_tab.config(bg=ACCENT, fg=TEXT)
            self.btn_login_tab.config(bg=CARD, fg=DIM)

    def _do_login(self):
        u = self.log_user.get().strip()
        p = self.log_pass.get().strip()
        if not u or not p:
            messagebox.showerror("Error", "Please fill all fields.", parent=self)
            return
        self._connect("LOGIN", u, p)

    def _do_register(self):
        u = self.reg_user.get().strip()
        p1 = self.reg_pass.get().strip()
        p2 = self.reg_pass2.get().strip()
        if not u or not p1 or not p2:
            messagebox.showerror("Error", "Please fill all fields.", parent=self)
            return
        if p1 != p2:
            messagebox.showerror("Error", "Passwords do not match!", parent=self)
            return
        self._connect("REGISTER", u, p1)

    def _connect(self, action: str, username: str, password: str):
        try:
            sock, first_msg = connect_and_login("127.0.0.1", 5555, action, username, password)
        except PermissionError as e:
            err = str(e)
            msgs = {
                "NOT_FOUND": "User not found. Please register first.",
                "WRONG_PASS": "Incorrect password.",
                "USERNAME_TAKEN": "User is already logged in elsewhere.",
                "ALREADY_EXISTS": "Username already taken. Please login.",
            }
            messagebox.showerror("Auth Error", msgs.get(err, err), parent=self)
            return
        except Exception as e:
            messagebox.showerror("Connection Failed",
                                 f"Cannot connect to server.\n{e}", parent=self)
            return

        if action == "REGISTER":
            messagebox.showinfo("Success", f"Account created! Welcome, {username}!", parent=self)

        self.withdraw()
        from chat_window import ChatWindow
        ChatWindow(self, sock, username, first_msg)


if __name__ == "__main__":
    app = LoginScreen()
    app.mainloop()
