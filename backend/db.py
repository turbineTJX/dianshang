import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import DATA_DIR


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA_DIR / 'studio.sqlite3', timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=30000')
    return conn


@contextmanager
def transaction():
    conn = connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rows(query, params=()):
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


def one(query, params=()):
    result = rows(query, params)
    return result[0] if result else None


def initialize():
    conn = connect()
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
          password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member',
          balance INTEGER NOT NULL DEFAULT 0 CHECK(balance >= 0),
          reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved >= 0 AND reserved <= balance),
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assets (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
          kind TEXT NOT NULL, category TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]',
          path TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL,
          width INTEGER, height INTEGER, source_job TEXT, deleted INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS providers (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, adapter TEXT NOT NULL,
          model TEXT NOT NULL DEFAULT '', base_url TEXT NOT NULL DEFAULT '',
          api_key TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 0,
          config TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bindings (
          capability TEXT PRIMARY KEY, provider_id TEXT REFERENCES providers(id)
        );
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), batch_id TEXT NOT NULL,
          operation TEXT NOT NULL, title TEXT NOT NULL, prompt TEXT NOT NULL, inputs TEXT NOT NULL,
          parameters TEXT NOT NULL, status TEXT NOT NULL, provider_id TEXT,
          provider_snapshot TEXT NOT NULL DEFAULT '{}', remote_id TEXT, result_ids TEXT NOT NULL DEFAULT '[]',
          cost INTEGER NOT NULL, reserved INTEGER NOT NULL DEFAULT 0,
          error TEXT NOT NULL DEFAULT '', progress INTEGER NOT NULL DEFAULT 0,
          attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ledger (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), job_id TEXT,
          action TEXT NOT NULL, delta INTEGER NOT NULL, reserved_delta INTEGER NOT NULL DEFAULT 0,
          balance INTEGER NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS products (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
          asset_ids TEXT NOT NULL DEFAULT '[]', category TEXT NOT NULL DEFAULT '', sku TEXT NOT NULL DEFAULT '',
          description TEXT NOT NULL DEFAULT '', selling_points TEXT NOT NULL DEFAULT '',
          variants TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS product_links (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), url TEXT NOT NULL,
          title TEXT NOT NULL DEFAULT '', platform TEXT NOT NULL DEFAULT '', product_id TEXT REFERENCES products(id),
          reference_text TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'unparsed',
          archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agent_sessions (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), mode TEXT NOT NULL,
          title TEXT NOT NULL, brief TEXT NOT NULL, input_ids TEXT NOT NULL DEFAULT '[]',
          product_id TEXT REFERENCES products(id), link_id TEXT REFERENCES product_links(id),
          parameters TEXT NOT NULL DEFAULT '{}', steps TEXT NOT NULL DEFAULT '[]',
          status TEXT NOT NULL DEFAULT 'draft', plan_source TEXT NOT NULL DEFAULT 'standard',
          revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agent_messages (
          id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES agent_sessions(id), role TEXT NOT NULL,
          content TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS products_owner ON products(user_id, archived, created_at);
        CREATE INDEX IF NOT EXISTS links_owner ON product_links(user_id, archived, created_at);
        CREATE INDEX IF NOT EXISTS agents_owner ON agent_sessions(user_id, created_at);
        CREATE INDEX IF NOT EXISTS assets_owner ON assets(user_id, deleted, created_at);
        CREATE INDEX IF NOT EXISTS jobs_owner ON jobs(user_id, created_at);
        CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS ledger_owner ON ledger(user_id, created_at);
        ''')
        conn.commit()
    finally:
        conn.close()


def decode(row, *fields):
    for field in fields:
        row[field] = json.loads(row[field])
    return row


def ledger(conn, user_id, action, delta, reserved_delta, note, job_id=None):
    conn.execute('UPDATE users SET balance=balance+?, reserved=reserved+? WHERE id=?',
                 (delta, reserved_delta, user_id))
    balance = conn.execute('SELECT balance FROM users WHERE id=?', (user_id,)).fetchone()[0]
    conn.execute('INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?,?)',
                 (uid(), user_id, job_id, action, delta, reserved_delta, balance, note, now()))
