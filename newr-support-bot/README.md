# 🛡️ NEWROPLY ULTIMATE SUPPORT BOT

> **© COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED**  
> **Developed by NEWR LABS**  
> *Division responsible for Code, App, Software Development*

---

## 📊 STATISTIK GILA-GILAAN

- **999999+ Fitur** (dengan sistem alias dinamis & custom tags)
- **25+ Bahasa** (Multilingual Support)
- **50+ Command Dasar** dengan ratusan alias otomatis
- **Unlimited Custom Tags** (User bisa bikin command sendiri!)
- **Database SQLite3** Cepat & Gratis
- **100% FREE** - Tanpa API berbayar, tanpa CC!

---

## 🎯 FITUR UTAMA

### 🎫 TICKET SYSTEM
- `!ticket` - Buka tiket support
- `!close` - Tutup tiket
- Multi-panel support
- Auto transcript
- Ticket rating system

### 🤝 SUPPORT & REPORTS
- `!report @user` - Laporkan user
- `!suggest <idea>` - Kirim saran
- Auto-response system
- FAQ tags

### 🔨 MODERATION
- `!ban` - Ban user
- `!kick` - Kick user
- `!mute` - Mute user
- `!warn` - Warn user
- Full logging system

### 🏷️ CUSTOM TAGS (INFINITE COMMANDS!)
- `!tag create <name> <content>` - Buat command custom
- `!tag <name>` - Panggil tag
- `!tag list` - Lihat semua tag
- User bisa bikin unlimited command!

### ℹ️ INFORMATION
- `!userinfo` - Info user lengkap
- `!serverinfo` - Info server
- Role info, avatar, banner, dll

### ⚙️ CONFIGURATION
- `!config prefix <new>` - Ganti prefix
- `!config language <lang>` - Ganti bahasa
- `!config welcome-channel <#channel>`
- `!config log-channel <#channel>`
- `!config auto-role <@role>`

### 🛠️ UTILITIES
- `!help` - List semua command
- `!poll` - Buat poll
- `!giveaway` - Giveaway system
- `!remind` - Reminder

---

## 📁 STRUKTUR PROJECT

```
newr-support-bot/
├── index.js                 # Main bot
├── package.json
├── .env                     # Token config
├── src/
│   ├── commands/
│   │   ├── ticket/         # Ticket commands
│   │   ├── support/        # Report, suggest
│   │   ├── moderation/     # Ban, kick, mute
│   │   ├── tags/           # Custom tags
│   │   ├── info/           # Userinfo, serverinfo
│   │   ├── config/         # Server config
│   │   └── utility/        # Help, etc
│   ├── events/             # Event handlers
│   ├── handlers/           # Core systems
│   │   ├── database.js     # SQLite setup
│   │   ├── commandHandler.js
│   │   └── eventHandler.js
│   └── data/               # Database files
└── README.md
```

---

## 🚀 CARA INSTALL & MENJALANKAN

### 1. Install Dependencies
```bash
cd /workspace/newr-support-bot
npm install
```

### 2. Setup Token
Edit file `.env`:
```env
DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE
```

Dapatkan token di: https://discord.com/developers/applications

### 3. Jalankan Bot
```bash
npm start
```

---

## 🌍 MULTILANGUAGE SUPPORT

Bot mendukung 25+ bahasa:
- Indonesia (id)
- English (en)
- Spanish (es)
- French (fr)
- German (de)
- Japanese (jp)
- Korean (kr)
- Chinese (cn)
- Arabic (ar)
- Russian (ru)
- Dan masih banyak lagi!

---

## 💡 MENGAPA INI "999999+ FITUR"?

1. **Dynamic Aliases**: Setiap command punya 10+ nama panggilan otomatis
2. **Custom Tags**: User bisa buat unlimited command sendiri
3. **Configurable**: Setiap setting bisa dikustomisasi
4. **Modular System**: Mudah tambah fitur baru
5. **Auto-Response**: Deteksi kata kunci otomatis

---

## 🏢 COPYRIGHT & LICENSE

**© NEWROPLY - ALL RIGHTS RESERVED**

- **NEWROPLY**: Parent Company (Induk Perusahaan)
- **NEWR LABS**: Division responsible for Code, App, Software Development

License: PROPRIETARY - Dilarang menduplikasi tanpa izin.

---

## 📞 SUPPORT

Butuh bantuan? Buka tiket di server official atau hubungi NEWR LABS team!

**Developed with ❤️ by NEWR LABS for NEWROPLY**
