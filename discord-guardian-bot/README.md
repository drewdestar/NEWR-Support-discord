# Discord Guardian Bot - Bot Keamanan Server Discord Terlengkap

Bot ini dilengkapi dengan fitur keamanan lengkap untuk melindungi server Discord Anda.

## Fitur Utama

### 1. **Anti-Nuke Protection**
- Deteksi massal channel deletion
- Deteksi massal role deletion/creation
- Deteksi massal ban/kick
- Auto-backup server settings
- Auto-restore setelah serangan terdeteksi

### 2. **Anti-Spam System**
- Spam message detection
- Raid protection (mass join detection)
- Auto-mute untuk spammer
- Customizable thresholds

### 3. **Moderation Commands**
- `/ban` - Ban user dengan alasan
- `/kick` - Kick user dari server
- `/mute` - Mute user sementara
- `/unmute` - Unmute user
- `/warn` - Memberi warning ke user
- `/warnings` - Lihat warning user
- `/purge` - Hapus bulk messages
- `/lock` - Lock channel
- `/unlock` - Unlock channel

### 4. **Logging System**
- Log semua aktivitas moderator
- Log deleted messages
- Log edited messages
- Log member joins/leaves
- Log voice channel activities

### 5. **Auto-Moderation**
- Anti-link (block link tertentu)
- Anti-invite (block invite server lain)
- Anti-profanity filter
- Anti-mass mention (@everyone/@here abuse)
- Custom word blacklist

### 6. **Security Features**
- Whitelist system untuk trusted users
- Admin action logging
- Suspicious activity alerts
- Backup & restore system

## Cara Setup

### 1. Install Dependencies
```bash
npm install
```

### 2. Buat File `.env`
Buat file `.env` di root folder dan isi dengan:
```env
DISCORD_TOKEN=your_bot_token_here
CLIENT_ID=your_client_id_here
GUILD_ID=your_server_id_here
```

### 3. Dapatkan Token Bot
1. Buka [Discord Developer Portal](https://discord.com/developers/applications)
2. Buat aplikasi baru
3. Pergi ke tab "Bot"
4. Klik "Reset Token" dan salin token
5. Paste token ke file `.env`

### 4. Invite Bot ke Server
Gunakan URL berikut (ganti CLIENT_ID dengan client ID bot Anda):
```
https://discord.com/api/oauth2/authorize?client_id=CLIENT_ID&permissions=8&scope=bot%20applications.commands
```

**Permissions yang dibutuhkan:** Administrator (untuk proteksi maksimal)

### 5. Jalankan Bot
```bash
node index.js
```

## Command List

### Moderation
- `/ban <user> [reason]` - Ban user
- `/kick <user> [reason]` - Kick user
- `/mute <user> <duration> [reason]` - Mute user (contoh: 1h, 30m, 7d)
- `/unmute <user>` - Unmute user
- `/warn <user> <reason>` - Warn user
- `/warnings <user>` - Lihat warnings user
- `/purge <amount>` - Hapus messages (max 100)
- `/lock [channel]` - Lock channel
- `/unlock [channel]` - Unlock channel

### Security
- `/whitelist add <user>` - Tambah ke whitelist
- `/whitelist remove <user>` - Hapus dari whitelist
- `/whitelist list` - Lihat daftar whitelist
- `/backup create` - Buat backup server
- `/backup restore` - Restore dari backup terakhir

### Configuration
- `/config set <key> <value>` - Set konfigurasi
- `/config get <key>` - Lihat konfigurasi
- `/config reset` - Reset konfigurasi

## Konfigurasi Default

Bot sudah dikonfigurasi dengan setting keamanan optimal:
- Anti-spam threshold: 5 messages dalam 5 detik
- Raid protection: 10 joins dalam 30 detik
- Max mentions per message: 5
- Auto-delete suspicious links: Enabled

## Troubleshooting

### Bot tidak response?
- Pastikan token benar di `.env`
- Cek apakah bot online di server
- Pastikan permissions cukup

### Fitur tidak bekerja?
- Pastikan bot punya role tertinggi (atau hampir tertinggi)
- Cek channel permissions
- Lihat console log untuk error

## Support

Jika ada masalah atau request fitur, silakan buat issue di repository ini.

---
**Catatan:** Bot ini membutuhkan Node.js v16.6.0 atau lebih tinggi.
