@echo off
echo Olası bir hata varsa görmek icin bu bat dosyasini kullaniyoruz.
echo Sunucu baslatiliyor...
start "Sunucu" cmd /k "python server_gui.py"

timeout /t 2 /nobreak >nul

echo 1. Istemci baslatiliyor...
start "Client 1" cmd /k "python client_gui.py"

echo 2. Istemci baslatiliyor...
start "Client 2" cmd /k "python client_gui.py"

echo Bitti.
exit
