import os
import sqlite3
import json
from datetime import datetime

DB_DIR = "/tmp/clienthunt_data" if os.environ.get("VERCEL") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "leadpulse.db")

def get_db_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Initializes tables for scalable production storage."""
    conn = get_db_connection()
    cur = conn.cursor()

    # 1. Clients Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        company TEXT,
        email TEXT UNIQUE,
        credits INTEGER DEFAULT 250,
        plan TEXT DEFAULT 'trial',
        is_paid INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        notes TEXT,
        api_key TEXT UNIQUE,
        avatar TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """)

    # 2. Payments Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY,
        trx_id TEXT UNIQUE,
        client_id TEXT,
        client_name TEXT,
        client_email TEXT,
        gateway TEXT,
        sender_number TEXT,
        amount_bdt REAL,
        credits INTEGER,
        package_id TEXT,
        status TEXT DEFAULT 'pending',
        payment_method_type TEXT DEFAULT 'manual',
        invoice_id TEXT,
        created_at TEXT,
        verified_at TEXT,
        verified_by TEXT
    )
    """)

    # 3. Credit Ledger / Transactions
    cur.execute("""
    CREATE TABLE IF NOT EXISTS credit_transactions (
        id TEXT PRIMARY KEY,
        client_id TEXT NOT NULL,
        type TEXT,
        amount INTEGER,
        balance_after INTEGER,
        description TEXT,
        created_at TEXT
    )
    """)

    # 4. Enriched Scraped Leads
    cur.execute("""
    CREATE TABLE IF NOT EXISTS enriched_leads (
        id TEXT PRIMARY KEY,
        client_id TEXT,
        company_name TEXT NOT NULL,
        category TEXT,
        location TEXT,
        address TEXT,
        phone TEXT,
        whatsapp_url TEXT,
        email TEXT,
        website TEXT,
        rating REAL,
        reviews_count INTEGER,
        contact_name TEXT,
        contact_title TEXT,
        linkedin_url TEXT,
        facebook_url TEXT,
        instagram_url TEXT,
        verification_status TEXT DEFAULT 'pending',
        verification_score INTEGER DEFAULT 0,
        buying_intent TEXT,
        created_at TEXT
    )
    """)

    # 5. Email Outreach & Open Tracking Logs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS outreach_tracking (
        id TEXT PRIMARY KEY,
        tracking_id TEXT UNIQUE,
        client_id TEXT,
        recipient_email TEXT NOT NULL,
        recipient_name TEXT,
        subject TEXT,
        status TEXT DEFAULT 'sent',
        opened INTEGER DEFAULT 0,
        opened_at TEXT,
        open_count INTEGER DEFAULT 0,
        clicked INTEGER DEFAULT 0,
        clicked_at TEXT,
        click_count INTEGER DEFAULT 0,
        sender_account TEXT,
        sent_at TEXT
    )
    """)

    conn.commit()
    conn.close()
    
    # Run one-time migration from existing JSON files
    migrate_from_json_files()

def migrate_from_json_files():
    """Migrates existing clients.json, history.json, and payments.json to SQLite seamlessly."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    conn = get_db_connection()
    cur = conn.cursor()

    # Migrate clients.json
    clients_file = os.path.join(base_dir, "clients.json")
    if os.path.exists(clients_file):
        try:
            with open(clients_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            client_list = data.get("clients", [])
            for c in client_list:
                cid = c.get("id")
                if not cid:
                    continue
                cur.execute("SELECT id FROM clients WHERE id = ?", (cid,))
                if not cur.fetchone():
                    cur.execute("""
                    INSERT INTO clients (id, name, company, email, credits, plan, is_paid, status, notes, api_key, avatar, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        cid,
                        c.get("name", "User"),
                        c.get("company", ""),
                        c.get("email", ""),
                        c.get("credits", 250),
                        c.get("plan", "trial"),
                        1 if c.get("is_paid") else 0,
                        c.get("status", "active"),
                        c.get("notes", ""),
                        c.get("api_key", ""),
                        c.get("avatar", ""),
                        c.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    ))
            conn.commit()
        except Exception as e:
            print("[DB Migration] Error migrating clients.json:", e)

    # Migrate payments.json
    payments_file = os.path.join(base_dir, "data", "payments.json")
    if os.path.exists(payments_file):
        try:
            with open(payments_file, "r", encoding="utf-8") as f:
                payments_list = json.load(f)
            for p in payments_list:
                pid = p.get("id")
                if not pid:
                    continue
                cur.execute("SELECT id FROM payments WHERE id = ?", (pid,))
                if not cur.fetchone():
                    cur.execute("""
                    INSERT OR IGNORE INTO payments (id, trx_id, client_id, client_name, client_email, gateway, sender_number, amount_bdt, credits, package_id, status, created_at, verified_at, verified_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        pid,
                        p.get("trx_id", ""),
                        p.get("client_id", ""),
                        p.get("client_name", ""),
                        p.get("client_email", ""),
                        p.get("gateway", "bkash"),
                        p.get("sender_number", ""),
                        p.get("amount_bdt", 0),
                        p.get("credits", 0),
                        p.get("package_id", ""),
                        p.get("status", "approved"),
                        p.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        p.get("verified_at", ""),
                        p.get("verified_by", "system")
                    ))
            conn.commit()
        except Exception as e:
            print("[DB Migration] Error migrating payments.json:", e)

    conn.close()

if __name__ == "__main__":
    init_database()
    print("Database initialized successfully at:", DB_PATH)
