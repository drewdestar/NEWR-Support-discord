/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * 
 * NEWROPLY: Parent Company
 * NEWR LABS: Division responsible for Code, App, Software Development
 * ────────────────────────────────────────────────────────
 */

const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const fs = require('fs');

const dbPath = path.join(__dirname, '../data', 'database.sqlite');
const dbDir = path.dirname(dbPath);

if (!fs.existsSync(dbDir)) {
    fs.mkdirSync(dbDir, { recursive: true });
}

const db = new sqlite3.Database(dbPath, (err) => {
    if (err) {
        console.error('[NEWR LABS] Database connection failed:', err.message);
    } else {
        console.log('[NEWR LABS] Connected to SQLite database.');
        initDatabase();
    }
});

function initDatabase() {
    // Config Table
    db.run(`CREATE TABLE IF NOT EXISTS config (
        guild_id TEXT PRIMARY KEY,
        prefix TEXT DEFAULT '!',
        language TEXT DEFAULT 'en',
        welcome_channel TEXT,
        log_channel TEXT,
        ticket_category TEXT,
        auto_role TEXT
    )`);

    // Tickets Table
    db.run(`CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT,
        channel_id TEXT UNIQUE,
        user_id TEXT,
        status TEXT DEFAULT 'open',
        category TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        closed_at DATETIME,
        closed_by TEXT
    )`);

    // Tags Table (Infinite Custom Commands)
    db.run(`CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT,
        name TEXT,
        content TEXT,
        creator TEXT,
        uses INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(guild_id, name)
    )`);

    // Warnings Table
    db.run(`CREATE TABLE IF NOT EXISTS warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT,
        user_id TEXT,
        moderator TEXT,
        reason TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )`);

    // Leveling Table
    db.run(`CREATE TABLE IF NOT EXISTS levels (
        guild_id TEXT,
        user_id TEXT,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        PRIMARY KEY (guild_id, user_id)
    )`);

    // Auto-Response Table
    db.run(`CREATE TABLE IF NOT EXISTS auto_responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT,
        trigger TEXT,
        response TEXT,
        exact_match BOOLEAN DEFAULT 0,
        UNIQUE(guild_id, trigger)
    )`);

    // Giveaways Table
    db.run(`CREATE TABLE IF NOT EXISTS giveaways (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT,
        channel_id TEXT,
        message_id TEXT,
        prize TEXT,
        winners INTEGER,
        duration INTEGER,
        end_time DATETIME,
        active BOOLEAN DEFAULT 1
    )`);

    console.log('[NEWR LABS] Database tables initialized successfully.');
}

module.exports = db;
