import subprocess
import time
import sys
import os

def main():
    print("🚀 Test ortami hazirlaniyor...")
    
    # Sunucuyu yeni bir konsol penceresinde baslat
    print("-> Sunucu (Admin Paneli) baslatiliyor...")
    subprocess.Popen([sys.executable, "server_gui.py"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    # Sunucunun portu acmasi icin biraz bekle
    time.sleep(2)
    
    # Birinci Istemciyi (Client) yeni bir konsol penceresinde baslat
    print("-> 1. Istemci (Client) baslatiliyor...")
    subprocess.Popen([sys.executable, "client_gui.py"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    # Ikinci Istemciyi (Client) yeni bir konsol penceresinde baslat
    print("-> 2. Istemci (Client) baslatiliyor...")
    subprocess.Popen([sys.executable, "client_gui.py"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    print("✅ Tum pencereler basariyla acildi! Bu pencereyi kapatabilirsiniz.")

if __name__ == "__main__":
    main()
