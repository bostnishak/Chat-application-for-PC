# 💬 Simple Chat Application

Bilgisayar Ağları dersi için geliştirilmiş, istemci-sunucu mimarisine dayalı gerçek zamanlı mesajlaşma uygulaması.

---

## 🗂 Proje Yapısı

```
chat_app/
├── server.py        # TCP sunucu mantığı (ağ katmanı)
├── server_gui.py    # Sunucu yönetici paneli (GUI)
├── client_gui.py    # İstemci uygulaması (GUI)
├── run_server.py    # Terminalde sunucu başlatma
└── users.json       # Kayıtlı kullanıcılar (otomatik oluşturulur)
```

---

## ✅ Özellikler

| Özellik | Açıklama |
|---|---|
| **Kullanıcı Girişi** | Kullanıcı adı + şifre ile giriş; ilk girişte otomatik kayıt |
| **Anlık Mesajlaşma** | Gerçek zamanlı grup sohbeti (TCP/IP) |
| **Özel Mesaj (DM)** | `@kullanıcıadı mesaj` formatıyla iki kullanıcı arası özel mesaj |
| **Admin Duyurusu** | Admin panelinden tüm kullanıcılara duyuru gönderme |
| **Kullanıcı Yönetimi** | Admin istediği kullanıcıyı sunucudan atabilir (kick) |
| **Mesaj Geçmişi** | Yeni bağlanan kullanıcı son 20 mesajı görür |
| **Çoklu Kullanıcı** | Aynı anda birden fazla kullanıcı desteklenir |

---

## 🚀 Çalıştırma

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
- Sunucu IP adresi: `127.0.0.1` (aynı bilgisayar) veya sunucunun IP'si
- Port: `5555`

---

## 📡 Protokol Yapısı

İstemci ile sunucu arası iletişim TCP üzerinden özel bir metin protokolü kullanır:

| Prefix | Yön | Açıklama |
|---|---|---|
| `MSG:<metin>` | Sunucu → İstemci | Grup mesajı |
| `SYSTEM:<metin>` | Sunucu → İstemci | Sistem bildirimi |
| `HISTORY:<metin>` | Sunucu → İstemci | Geçmiş mesaj |
| `USERLIST:<liste>` | Sunucu → İstemci | Çevrimiçi kullanıcı listesi |
| `DM:<metin>` | Sunucu → İstemci | Alınan özel mesaj |
| `DM_SENT:<metin>` | Sunucu → İstemci | Gönderilen özel mesaj onayı |
| `ANNOUNCE:<metin>` | Sunucu → İstemci | Admin duyurusu |
| `ERROR:USERNAME_TAKEN` | Sunucu → İstemci | Kullanıcı adı zaten bağlı |
| `ERROR:WRONG_PASS` | Sunucu → İstemci | Hatalı şifre |
| `@kullanıcı mesaj` | İstemci → Sunucu | Özel mesaj gönder |

---

## 💡 Kullanım İpuçları

- **Özel mesaj göndermek için:** sohbet kutusuna `@AliceHello!` yazın
- **Admin duyurusu:** Admin panelinde "Announcement" alanına yazıp "Send to All" butonuna tıklayın
- **Kullanıcı atmak (kick):** Admin panelinde kullanıcının üzerine tıklayıp "Kick Selected" butonuna basın

---

## 🏗 Mimari

```
[Client 1] ──┐
[Client 2] ──┤──→ [TCP Server (server.py)] ←── [Admin Panel (server_gui.py)]
[Client N] ──┘
```

- Her istemci bağlantısı ayrı bir **thread** üzerinde çalışır
- Sunucu durumu (bağlı kullanıcılar, mesaj geçmişi) `threading.Lock` ile korunur
- GUI ile sunucu mantığı tamamen ayrı katmanlarda tutulur

---

## ⚙️ Gereksinimler

- Python 3.8 veya üzeri
- Ek kütüphane gerekmez (standart kütüphane: `socket`, `threading`, `tkinter`, `json`)
