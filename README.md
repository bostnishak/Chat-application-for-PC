# 💬 WhatsApp-like Chat Application

Bilgisayar Ağları dersi için geliştirilmiş, istemci-sunucu mimarisine dayalı gerçek zamanlı mesajlaşma uygulaması.

---

## 🗂 Proje Yapısı

```
chat_app/
├── server.py          # TCP sunucu mantığı (ağ katmanı)
├── server_gui.py      # Sunucu yönetici paneli (GUI)
├── client_gui.py      # İstemci giriş ekranı (LoginScreen)
├── chat_window.py     # İstemci sohbet penceresi (ChatWindow)
├── client_network.py  # Ortak ağ yardımcıları (send/recv)
├── emoji_data.py      # Emoji listesi (picker için)
├── run_server.py      # Terminalde sunucu başlatma (GUI'siz)
└── users.json         # Kayıtlı kullanıcılar (otomatik oluşturulur)
```

---

## ✅ Özellikler

| Özellik | Açıklama |
|---|---|
| **Kullanıcı Girişi** | Kullanıcı adı + şifre ile giriş; ilk girişte otomatik kayıt |
| **Global Sohbet** | Tüm bağlı kullanıcılara gerçek zamanlı mesaj |
| **Özel Mesaj (DM)** | Soldaki listeden kullanıcı seçip birebir mesajlaşma |
| **Grup Sohbeti** | Grup oluştur, katıl, mesaj gönder, ayrıl |
| **Dosya Transferi** | 📎 butonu ile kullanıcı veya gruba dosya gönder (max 20 MB) |
| **Emoji Picker** | 😊 butonu ile 120+ emoji seçici |
| **Okunmamış Rozet** | Aktif olmayan konuşmalarda kırmızı sayaç |
| **Mesaj Geçmişi** | Yeni bağlanan kullanıcı son 50 mesajı görür |
| **Admin Duyurusu** | Admin panelinden tüm kullanıcılara duyuru |
| **Kullanıcı Kick** | Admin istediği kullanıcıyı sunucudan atabilir |
| **Çoklu Kullanıcı** | Her bağlantı ayrı thread'de çalışır |

---

## 🚀 Çalıştırma

### Gereksinimler

- Python 3.10 veya üzeri
- Ek kütüphane **gerekmez** (standart kütüphane: `socket`, `threading`, `tkinter`, `json`, `struct`)

### 1. Sunucuyu Başlatma

**Yönetici Paneli (önerilen):**
```bash
python server_gui.py
```

**Terminal (GUI'siz):**
```bash
python run_server.py
```

### 2. İstemciyi Başlatma

Her kullanıcı için ayrı bir terminal penceresi açın:
```bash
python client_gui.py
```

Giriş ekranında:
- **Kullanıcı adı** ve **şifre** girin (ilk girişte otomatik kayıt olursunuz)
- Sunucu IP: `127.0.0.1` (aynı bilgisayar) veya sunucunun IP'si
- Port: `5555`

---

## 💬 Kullanım

| İşlem | Nasıl yapılır |
|---|---|
| Global mesaj | Soldaki listeden **🌐 Global** seç → yaz → Enter |
| Özel mesaj | Soldaki listeden **👤 kullanıcı** adına tıkla → yaz → Enter |
| Grup oluştur | Sol alttaki **➕ New Group** butonuna tıkla |
| Gruba katıl | Sol alttaki **🔗 Join Group** butonuna tıkla |
| Gruptan ayrıl | Grup seçiliyken sağ üstteki **🚪 Leave** butonuna tıkla |
| Dosya gönder | **📎** butonuna tıkla (kullanıcı veya grup seçili olmalı) |
| Dosya kaydet | Dosya mesajındaki **💾 Save** butonuna tıkla |
| Emoji ekle | **😊** butonuna tıkla → emoji seç |

---

## 📡 Protokol Yapısı

İstemci-sunucu iletişimi TCP üzerinden length-prefixed binary protokol kullanır:

```
[4 byte: mesaj uzunluğu][mesaj bytes]
```

Dosyalar için:
```
[4 byte: header uzunluğu][header bytes][4 byte: data uzunluğu][data bytes]
```

### Mesaj Tipleri

| Prefix | Yön | Açıklama |
|---|---|---|
| `MSG\|[ts]\|sender\|body` | S→C | Global mesaj (sender dahil herkese) |
| `DM\|[ts]\|sender\|body` | S→C | Alınan özel mesaj |
| `DM_SENT\|[ts]\|recipient\|body` | S→C | Gönderilen özel mesaj echo'su |
| `GROUP_MSG\|[ts]\|group\|sender\|body` | S→C | Grup mesajı |
| `SYSTEM\|[ts]\|System\|body` | S→C | Sistem bildirimi |
| `ANNOUNCE\|[ts]\|Admin\|body` | S→C | Admin duyurusu |
| `HISTORY\|...` | S→C | Geçmiş mesaj (bağlantı sonrası) |
| `USERLIST:u1,u2,...` | S→C | Çevrimiçi kullanıcı listesi |
| `GROUPLIST:{json}` | S→C | Grup listesi |
| `FILE_DATA\|[ts]\|sender\|recip\|file\|size` | S→C | Gelen dosya |
| `FILE_SENT\|[ts]\|sender\|recip\|file\|size` | S→C | Gönderilen dosya echo'su |
| `GROUP_RESULT\|action\|result\|name` | S→C | Grup işlem sonucu |
| `@kullanıcı mesaj` | C→S | Özel mesaj gönder |
| `GROUP_CREATE\|name` | C→S | Grup oluştur |
| `GROUP_JOIN\|name` | C→S | Gruba katıl |
| `GROUP_LEAVE\|name` | C→S | Gruptan ayrıl |
| `GROUP_MSG\|group\|body` | C→S | Grup mesajı gönder |
| `FILE_DATA\|recipient\|filename` | C→S | Dosya gönder (binary) |

---

## 🏗 Mimari

```
[Client 1] ──┐
[Client 2] ──┤──→ [TCP Server (server.py)] ←── [Admin Panel (server_gui.py)]
[Client N] ──┘
     ↑
  LoginScreen (client_gui.py)
     ↓
  ChatWindow (chat_window.py)
```

- Her istemci bağlantısı ayrı bir **thread** üzerinde çalışır
- Sunucu durumu `threading.Lock` ile korunur
- GUI ile ağ katmanı tamamen ayrı: `client_network.py` ortak yardımcıları sağlar
- Tüm GUI güncellemeleri `after(0, ...)` ile ana thread'e gönderilir (thread-safe)
