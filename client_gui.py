"""
Professional Chat Application - Client GUI
Entry point: LoginScreen → ChatWindow
Uses customtkinter for a modern, sleek interface.
"""

import socket
import customtkinter as ctk
from tkinter import messagebox
from client_network import connect_and_login

# ─────────────────────────────────────────────
# Theme Configuration
# ─────────────────────────────────────────────
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BG_COLOR = "#121212"
TEXT_COLOR = "#ffffff"
TEXT_DIM = "#a0a0a0"
ACCENT = "#3498db"
ACCENT_HOVER = "#2980b9"


class LoginScreen(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Chat App")
        self.geometry("400x550")
        self.resizable(False, False)
        
        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 400) // 2
        y = (self.winfo_screenheight() - 550) // 2
        self.geometry(f"+{x}+{y}")
        
        self.configure(fg_color=BG_COLOR)
        self._build_ui()

    def _build_ui(self):
        self.main_frame = ctk.CTkFrame(self, fg_color=BG_COLOR)
        self.main_frame.pack(fill="both", expand=True, padx=40, pady=30)

        # Header
        self.logo_label = ctk.CTkLabel(
            self.main_frame, text="💬", font=ctk.CTkFont(size=54)
        )
        self.logo_label.pack(pady=(0, 10))

        self.title_label = ctk.CTkLabel(
            self.main_frame, text="Welcome to Chat App", 
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=TEXT_COLOR
        )
        self.title_label.pack(pady=(0, 20))

        # Tabs for Login / Register
        self.tabview = ctk.CTkTabview(self.main_frame, width=320, height=300)
        self.tabview.pack(pady=(0, 10))
        
        self.tab_login = self.tabview.add("Login")
        self.tab_register = self.tabview.add("Register")

        self._build_login_tab()
        self._build_register_tab()

    def _build_login_tab(self):
        self.log_user = ctk.CTkEntry(
            self.tab_login, placeholder_text="Username",
            width=280, height=40, corner_radius=8
        )
        self.log_user.pack(pady=(20, 10))

        self.log_pass = ctk.CTkEntry(
            self.tab_login, placeholder_text="Password", show="●",
            width=280, height=40, corner_radius=8
        )
        self.log_pass.pack(pady=(10, 20))

        btn = ctk.CTkButton(
            self.tab_login, text="Login", width=280, height=40,
            font=ctk.CTkFont(weight="bold"), command=self._do_login
        )
        btn.pack(pady=(0, 10))

        self.log_pass.bind("<Return>", lambda e: self._do_login())

    def _build_register_tab(self):
        self.reg_user = ctk.CTkEntry(
            self.tab_register, placeholder_text="Choose Username",
            width=280, height=40, corner_radius=8
        )
        self.reg_user.pack(pady=(10, 10))

        self.reg_pass = ctk.CTkEntry(
            self.tab_register, placeholder_text="Password", show="●",
            width=280, height=40, corner_radius=8
        )
        self.reg_pass.pack(pady=10)

        self.reg_pass2 = ctk.CTkEntry(
            self.tab_register, placeholder_text="Confirm Password", show="●",
            width=280, height=40, corner_radius=8
        )
        self.reg_pass2.pack(pady=(10, 20))

        btn = ctk.CTkButton(
            self.tab_register, text="Register", width=280, height=40,
            font=ctk.CTkFont(weight="bold"), fg_color="#27ae60", hover_color="#2ecc71",
            command=self._do_register
        )
        btn.pack(pady=(0, 10))

        self.reg_pass2.bind("<Return>", lambda e: self._do_register())

    def _do_login(self):
        user = self.log_user.get().strip()
        pw = self.log_pass.get().strip()
        if not user or not pw:
            messagebox.showerror("Error", "Please fill all fields.", parent=self)
            return
        self._connect_to_server("LOGIN", user, pw)

    def _do_register(self):
        user = self.reg_user.get().strip()
        pw1 = self.reg_pass.get().strip()
        pw2 = self.reg_pass2.get().strip()
        
        if not user or not pw1 or not pw2:
            messagebox.showerror("Error", "Please fill all fields.", parent=self)
            return
        if pw1 != pw2:
            messagebox.showerror("Error", "Passwords do not match!", parent=self)
            return
            
        self._connect_to_server("REGISTER", user, pw1)

    def _connect_to_server(self, action: str, username: str, password: str):
        server_ip = "127.0.0.1"
        port = 5555

        try:
            sock, first_msg = connect_and_login(server_ip, port, action, username, password)
        except PermissionError as e:
            err = str(e)
            if "NOT_FOUND" in err:
                messagebox.showerror("Login Failed", "User not found. Please register first.", parent=self)
            elif "WRONG_PASS" in err:
                messagebox.showerror("Login Failed", "Incorrect password.", parent=self)
            elif "USERNAME_TAKEN" in err:
                messagebox.showerror("Login Failed", "User is already logged in somewhere else.", parent=self)
            elif "ALREADY_EXISTS" in err:
                messagebox.showerror("Registration Failed", "Username already exists. Please login.", parent=self)
            else:
                messagebox.showerror("Error", err, parent=self)
            return
        except Exception as e:
            messagebox.showerror("Connection Failed", f"Could not connect to server.\n{e}", parent=self)
            return

        # If success, switch to chat
        if action == "REGISTER":
            messagebox.showinfo("Success", "Registration successful! You are now logged in.", parent=self)

        self.withdraw()
        from chat_window import ChatWindow
        ChatWindow(self, sock, username, first_msg)


if __name__ == "__main__":
    app = LoginScreen()
    app.mainloop()
