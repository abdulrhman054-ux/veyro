"""SQLite storage for sessions, per-agent turns, verdicts and settings."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from .config import DATA_DIR, DB_PATH

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  ticker TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  created_at TEXT NOT NULL,
  finished_at TEXT,
  mode TEXT NOT NULL,              -- 'real' | 'demo'
  provider TEXT, quick_model TEXT, deep_model TEXT,
  lang TEXT NOT NULL,
  status TEXT NOT NULL,            -- running | done | error | cancelled
  rating TEXT,                     -- Buy/Overweight/Hold/Underweight/Sell/REVIEW
  verdict_json TEXT,
  price_at_verdict REAL, spy_at_verdict REAL, price_time TEXT, price_source TEXT,
  usage_json TEXT, cost_usd REAL,
  error TEXT,
  scan_id TEXT REFERENCES scans(id),
  config_json TEXT                 -- analysts, rounds, asset type, benchmark, framework lessons/portfolio context
);
CREATE TABLE IF NOT EXISTS turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  character TEXT NOT NULL,
  node TEXT NOT NULL,
  detail_en TEXT NOT NULL,
  voice_ar TEXT, voice_en TEXT,
  detail_ar TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_session ON turns(session_id, seq);
CREATE TABLE IF NOT EXISTS scans (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,              -- 'watchlist' | 'screener'
  screener TEXT,                   -- yfinance predefined screener id when kind='screener'
  tickers_json TEXT NOT NULL,      -- candidates exactly as fetched / entered
  source_json TEXT,                -- raw candidate rows from the screener (symbol, name, price, as-of)
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  lang TEXT NOT NULL,
  mode TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paper (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT NOT NULL, shares REAL NOT NULL, entry_price REAL NOT NULL, currency TEXT,
  bench TEXT, bench_entry REAL, opened_at TEXT NOT NULL, session_id TEXT, rating TEXT,
  closed_at TEXT, exit_price REAL, bench_exit REAL, fee_in REAL, fee_out REAL, fx_usd_entry REAL
);
CREATE TABLE IF NOT EXISTS sharia_cache (      -- optional Sharia screen: raw free fundamentals per symbol, with the fetch date
  symbol TEXT PRIMARY KEY, data_json TEXT NOT NULL, fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS valuation_cache (   -- free pre-screen "value" mode: light company facts per symbol
  symbol TEXT PRIMARY KEY, data_json TEXT NOT NULL, fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL, op TEXT NOT NULL,       -- 'above' | 'below'
  value REAL NOT NULL, created_at TEXT NOT NULL, triggered_at TEXT, triggered_price REAL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    return c


_conn: sqlite3.Connection | None = None


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = _connect()
            _conn.executescript(SCHEMA)
            cols = {r[1] for r in _conn.execute("PRAGMA table_info(sessions)")}
            if "config_json" not in cols:  # databases created before this column existed
                _conn.execute("ALTER TABLE sessions ADD COLUMN config_json TEXT")
                _conn.commit()
            pcols = {r[1] for r in _conn.execute("PRAGMA table_info(paper)")}
            if "bench_exit" not in pcols:   # virtual portfolio from an earlier build
                _conn.execute("ALTER TABLE paper ADD COLUMN bench_exit REAL")
                _conn.commit()
            for col in ("fee_in", "fee_out", "fx_usd_entry"):   # fees and currency, added in the 2026-09 review
                if col not in pcols:
                    _conn.execute(f"ALTER TABLE paper ADD COLUMN {col} REAL")
                    _conn.commit()
        return _conn


@contextmanager
def tx():
    with _lock:
        c = conn()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


def q(sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


def q1(sql: str, args: tuple = ()) -> dict[str, Any] | None:
    rows = q(sql, args)
    return rows[0] if rows else None


# ---------------------------------------------------------------- settings
def get_setting(key: str, default: Any = None) -> Any:
    r = q1("SELECT value FROM settings WHERE key=?", (key,))
    return json.loads(r["value"]) if r else default


def set_setting(key: str, value: Any) -> None:
    with tx() as c:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, json.dumps(value)))


# ---------------------------------------------------------------- sessions
def create_session(sid: str, ticker: str, trade_date: str, mode: str, provider: str | None,
                   quick: str | None, deep: str | None, lang: str, scan_id: str | None = None) -> None:
    with tx() as c:
        c.execute("INSERT INTO sessions(id,ticker,trade_date,created_at,mode,provider,quick_model,deep_model,lang,status,scan_id)"
                  " VALUES(?,?,?,?,?,?,?,?,?,'running',?)",
                  (sid, ticker, trade_date, now(), mode, provider, quick, deep, lang, scan_id))


def create_scan(scan_id: str, kind: str, screener: str | None, tickers: list[str], source: list[dict] | None,
                lang: str, mode: str) -> None:
    with tx() as c:
        c.execute("INSERT INTO scans(id,kind,screener,tickers_json,source_json,created_at,status,lang,mode)"
                  " VALUES(?,?,?,?,?,?,'running',?,?)",
                  (scan_id, kind, screener, json.dumps(tickers), json.dumps(source), now(), lang, mode))


def update_scan(scan_id: str, **fields: Any) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    with tx() as c:
        c.execute(f"UPDATE scans SET {cols} WHERE id=?", (*fields.values(), scan_id))


def get_scan(scan_id: str) -> dict | None:
    s = q1("SELECT * FROM scans WHERE id=?", (scan_id,))
    if not s:
        return None
    s["tickers"] = json.loads(s.pop("tickers_json"))
    s["source"] = json.loads(s.pop("source_json") or "null")
    s["sessions"] = list_sessions(scan_id=scan_id)
    # analyses reused from earlier today belong to this scan's results too
    extra = get_setting(f"scan_extra:{scan_id}") or []
    if extra:
        have = {x["id"] for x in s["sessions"]}
        s["sessions"] += [r for r in list_sessions(500) if r["id"] in extra and r["id"] not in have]
    return s


def list_scans(limit: int = 50) -> list[dict]:
    rows = q("SELECT * FROM scans ORDER BY created_at DESC LIMIT ?", (limit,))
    for r in rows:
        r["tickers"] = json.loads(r.pop("tickers_json"))
        r.pop("source_json", None)
    return rows


def update_session(sid: str, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with tx() as c:
        c.execute(f"UPDATE sessions SET {cols} WHERE id=?", (*fields.values(), sid))


def add_turn(sid: str, seq: int, character: str, node: str, detail_en: str,
             voice_ar: str | None, voice_en: str | None) -> int:
    with tx() as c:
        cur = c.execute("INSERT INTO turns(session_id,seq,character,node,detail_en,voice_ar,voice_en,created_at)"
                        " VALUES(?,?,?,?,?,?,?,?)", (sid, seq, character, node, detail_en, voice_ar, voice_en, now()))
        return int(cur.lastrowid)


def update_turn(tid: int, **fields: Any) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    with tx() as c:
        c.execute(f"UPDATE turns SET {cols} WHERE id=?", (*fields.values(), tid))


def get_session(sid: str) -> dict | None:
    s = q1("SELECT * FROM sessions WHERE id=?", (sid,))
    if not s:
        return None
    s["verdict"] = json.loads(s.pop("verdict_json") or "null")
    s["usage"] = json.loads(s.pop("usage_json") or "null")
    s["config"] = json.loads(s.pop("config_json") or "null")
    s["turns"] = q("SELECT * FROM turns WHERE session_id=? ORDER BY seq", (sid,))
    return s


def list_sessions(limit: int = 200, scan_id: str | None = None) -> list[dict]:
    cols = ("id,ticker,trade_date,created_at,finished_at,mode,provider,quick_model,deep_model,lang,status,rating,verdict_json,"
            "price_at_verdict,spy_at_verdict,price_time,price_source,cost_usd,scan_id,config_json")
    if scan_id:
        rows = q(f"SELECT {cols} FROM sessions WHERE scan_id=? ORDER BY created_at", (scan_id,))
    else:
        rows = q(f"SELECT {cols} FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,))
    for r in rows:
        r["verdict"] = json.loads(r.pop("verdict_json") or "null")
        r["config"] = json.loads(r.pop("config_json") or "null")
    return rows


def mark_orphans() -> None:
    """Sessions left 'running' by a previous process are marked as interrupted."""
    with tx() as c:
        c.execute("UPDATE sessions SET status='error', error='interrupted' WHERE status='running'")
        c.execute("UPDATE scans SET status='error' WHERE status='running'")
