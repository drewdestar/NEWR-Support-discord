/**
 * Database Handler - SQLite3
 * Professional Grade Database System
 */

const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const fs = require('fs');

class Database {
    constructor(dbPath) {
        this.dbPath = dbPath;
        this.db = null;
        this.ensureDirectory();
    }

    ensureDirectory() {
        const dir = path.dirname(this.dbPath);
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
    }

    async initialize() {
        return new Promise((resolve, reject) => {
            this.db = new sqlite3.Database(this.dbPath, (err) => {
                if (err) {
                    console.error('❌ Database connection error:', err);
                    reject(err);
                    return;
                }
                console.log('✅ Database connected successfully');
                this.createTables().then(resolve).catch(reject);
            });
        });
    }

    async createTables() {
        const tables = [
            // Guild Settings
            `CREATE TABLE IF NOT EXISTS guilds (
                guild_id TEXT PRIMARY KEY,
                prefix TEXT DEFAULT '!',
                language TEXT DEFAULT 'id',
                welcome_channel TEXT,
                goodbye_channel TEXT,
                log_channel TEXT,
                mute_role TEXT,
                auto_mod_enabled INTEGER DEFAULT 1,
                anti_nuke_enabled INTEGER DEFAULT 1,
                anti_spam_enabled INTEGER DEFAULT 1,
                anti_raid_enabled INTEGER DEFAULT 1,
                anti_invite_enabled INTEGER DEFAULT 1,
                anti_link_enabled INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )`,
            
            // User Data
            `CREATE TABLE IF NOT EXISTS users (
                user_id TEXT,
                guild_id TEXT,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                coins INTEGER DEFAULT 0,
                reputation INTEGER DEFAULT 0,
                warnings INTEGER DEFAULT 0,
                strikes INTEGER DEFAULT 0,
                last_message_at DATETIME,
                total_messages INTEGER DEFAULT 0,
                voice_time INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )`,
            
            // Moderation Logs
            `CREATE TABLE IF NOT EXISTS mod_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                user_id TEXT,
                moderator_id TEXT,
                action TEXT,
                reason TEXT,
                duration INTEGER,
                points INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )`,
            
            // Warnings
            `CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                user_id TEXT,
                moderator_id TEXT,
                reason TEXT,
                points INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )`,
            
            // Mutes
            `CREATE TABLE IF NOT EXISTS mutes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                user_id TEXT,
                moderator_id TEXT,
                reason TEXT,
                expires_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )`,
            
            // Bans
            `CREATE TABLE IF NOT EXISTS bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                user_id TEXT,
                moderator_id TEXT,
                reason TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )`,
            
            // Whitelist
            `CREATE TABLE IF NOT EXISTS whitelist (
                guild_id TEXT,
                user_id TEXT,
                role_id TEXT,
                PRIMARY KEY (guild_id, user_id)
            )`,
            
            // Blacklist
            `CREATE TABLE IF NOT EXISTS blacklist (
                guild_id TEXT,
                user_id TEXT,
                reason TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )`,
            
            // Auto Roles
            `CREATE TABLE IF NOT EXISTS auto_roles (
                guild_id TEXT,
                role_id TEXT,
                PRIMARY KEY (guild_id, role_id)
            )`,
            
            // Reaction Roles
            `CREATE TABLE IF NOT EXISTS reaction_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                message_id TEXT,
                channel_id TEXT,
                emoji TEXT,
                role_id TEXT
            )`,
            
            // Custom Commands
            `CREATE TABLE IF NOT EXISTS custom_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                trigger TEXT,
                response TEXT,
                embed_data TEXT,
                created_by TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )`,
            
            // Giveaways
            `CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                channel_id TEXT,
                message_id TEXT,
                prize TEXT,
                winners INTEGER DEFAULT 1,
                duration INTEGER,
                ends_at DATETIME,
                host_id TEXT,
                participants TEXT,
                status TEXT DEFAULT 'active'
            )`,
            
            // Tickets
            `CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                channel_id TEXT,
                user_id TEXT,
                category_id TEXT,
                status TEXT DEFAULT 'open',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                closed_at DATETIME,
                closed_by TEXT
            )`,
            
            // Economy Transactions
            `CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                user_id TEXT,
                amount INTEGER,
                type TEXT,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )`,
            
            // Shop Items
            `CREATE TABLE IF NOT EXISTS shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                name TEXT,
                description TEXT,
                price INTEGER,
                item_type TEXT,
                role_id TEXT,
                stock INTEGER DEFAULT -1,
                enabled INTEGER DEFAULT 1
            )`,
            
            // Inventory
            `CREATE TABLE IF NOT EXISTS inventory (
                guild_id TEXT,
                user_id TEXT,
                item_id INTEGER,
                quantity INTEGER DEFAULT 1,
                acquired_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id, item_id)
            )`,
            
            // Leaderboard cache
            `CREATE TABLE IF NOT EXISTS leaderboard (
                guild_id TEXT,
                user_id TEXT,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                coins INTEGER DEFAULT 0,
                rank INTEGER,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )`,
            
            // Security Events Log
            `CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                event_type TEXT,
                severity TEXT,
                user_id TEXT,
                details TEXT,
                action_taken TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )`,
            
            // Backup data
            `CREATE TABLE IF NOT EXISTS backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                backup_data TEXT,
                created_by TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )`,
            
            // Snipe cache
            `CREATE TABLE IF NOT EXISTS snipe_cache (
                guild_id TEXT,
                channel_id TEXT,
                user_id TEXT,
                content TEXT,
                message_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, channel_id)
            )`,
            
            // AFK Status
            `CREATE TABLE IF NOT EXISTS afk_status (
                user_id TEXT,
                guild_id TEXT,
                reason TEXT,
                since DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, guild_id)
            )`,
            
            // Reminders
            `CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                guild_id TEXT,
                content TEXT,
                remind_at DATETIME,
                notified INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )`
        ];

        for (const table of tables) {
            await this.run(table);
        }
        
        console.log('✅ All database tables created/verified');
    }

    run(sql, params = []) {
        return new Promise((resolve, reject) => {
            this.db.run(sql, params, function(err) {
                if (err) reject(err);
                else resolve({ lastID: this.lastID, changes: this.changes });
            });
        });
    }

    get(sql, params = []) {
        return new Promise((resolve, reject) => {
            this.db.get(sql, params, (err, row) => {
                if (err) reject(err);
                else resolve(row);
            });
        });
    }

    all(sql, params = []) {
        return new Promise((resolve, reject) => {
            this.db.all(sql, params, (err, rows) => {
                if (err) reject(err);
                else resolve(rows || []);
            });
        });
    }

    async close() {
        return new Promise((resolve, reject) => {
            this.db.close(err => {
                if (err) reject(err);
                else {
                    console.log('📁 Database connection closed');
                    resolve();
                }
            });
        });
    }
}

module.exports = Database;
