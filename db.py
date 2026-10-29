"""SQLite persistence for NEWR Support. No secrets are stored here."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "data.db"))


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS tickets(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,
            channel_id INTEGER UNIQUE, owner_id INTEGER, status TEXT,
            reason TEXT, claimed_by INTEGER, created_at TEXT);
        CREATE TABLE IF NOT EXISTS warns(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,
            user_id INTEGER, moderator_id INTEGER, reason TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS settings(
            guild_id INTEGER, key TEXT, value TEXT,
            PRIMARY KEY (guild_id, key));
        CREATE TABLE IF NOT EXISTS notes(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,
            user_id INTEGER, author_id INTEGER, note TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS reports(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,
            reporter_id INTEGER, target_id INTEGER, reason TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS suggestions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,
            author_id INTEGER, text TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS bugs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,
            author_id INTEGER, text TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS appeals(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,
            author_id INTEGER, text TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS feedback(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,
            author_id INTEGER, rating INTEGER, comment TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS watchlist(
            guild_id INTEGER, user_id INTEGER, reason TEXT,
            PRIMARY KEY (guild_id, user_id));
        CREATE TABLE IF NOT EXISTS banned_words(
            guild_id INTEGER, word TEXT, PRIMARY KEY (guild_id, word));
        CREATE TABLE IF NOT EXISTS faqs(
            guild_id INTEGER, topic TEXT, answer TEXT,
            PRIMARY KEY (guild_id, topic));
        CREATE TABLE IF NOT EXISTS dm_requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,
            user_id INTEGER, text TEXT, status TEXT, created_at TEXT);
        """)
    # A small default FAQ set is inserted only when the table is empty.
    with _conn() as conn:
        if conn.execute("SELECT COUNT(*) FROM faqs").fetchone()[0] == 0:
            conn.executemany(
                "INSERT OR IGNORE INTO faqs VALUES (0, ?, ?)",
                [("support", "Open a ticket with /ticket_create and staff will reply there."),
                 ("rules", "Be respectful, no spam, no NSFW, and follow staff directions."),
                 ("verify", "Use /verify and click the verification button, then follow the prompt.")],
            )


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_setting(guild_id: int, key: str, value: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO settings VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, key) DO UPDATE SET value=excluded.value",
            (guild_id, key, value))


def get_setting(guild_id: int, key: str, default: str = "off") -> str:
    with _conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE guild_id=? AND key=?",
            (guild_id, key)).fetchone()
    return row["value"] if row else default


def add_row(table: str, **cols) -> int:
    keys, vals = list(cols), list(cols.values())
    with _conn() as conn:
        cur = conn.execute(
            f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?' * len(keys))})", vals)
        return cur.lastrowid


def list_rows(table: str, guild_id: int, limit: int = 20):
    with _conn() as conn:
        return conn.execute(
            f"SELECT * FROM {table} WHERE guild_id=? ORDER BY id DESC LIMIT ?",
            (guild_id, limit)).fetchall()
