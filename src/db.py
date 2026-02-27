"""
db.py — SQLite setup and schema for Lucilease.
All tables are created on startup if they don't exist.
"""

import sqlite3
import pathlib

DB_PATH = pathlib.Path("/data/lucilease.db")


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Leads — incoming email inquiries
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT    UNIQUE NOT NULL,
            source      TEXT    NOT NULL DEFAULT 'gmail',
            from_email  TEXT    NOT NULL,
            name        TEXT,
            phone       TEXT,
            subject     TEXT,
            body_excerpt TEXT,
            budget_monthly_usd INTEGER,
            status      TEXT    NOT NULL DEFAULT 'new',
            first_seen_at TEXT  NOT NULL,
            handled_at  TEXT,
            gmail_msg_id TEXT
        )
    """)

    # Clients — contacts the agent is working with
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            email       TEXT    UNIQUE,
            phone       TEXT,
            address     TEXT,
            notes       TEXT,
            status      TEXT    NOT NULL DEFAULT 'active',
            created_at  TEXT    NOT NULL,
            updated_at  TEXT
        )
    """)

    # Properties — listings the agent is marketing
    cur.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            address     TEXT    NOT NULL,
            type        TEXT    NOT NULL DEFAULT 'rental',
            bedrooms    INTEGER,
            bathrooms   REAL,
            price_monthly INTEGER,
            price_sale  INTEGER,
            status      TEXT    NOT NULL DEFAULT 'active',
            notes       TEXT,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT
        )
    """)

    # Agent config — profile and preferences
    cur.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key         TEXT    PRIMARY KEY,
            value       TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        )
    """)

    # Draft log — track what's been drafted
    cur.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id     INTEGER REFERENCES leads(id),
            gmail_draft_id TEXT,
            subject     TEXT,
            body        TEXT,
            created_at  TEXT    NOT NULL,
            sent        INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    print("[db] Schema ready.")
