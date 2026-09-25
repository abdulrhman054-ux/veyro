"""Optional trade execution (Alpaca). Off by default.

Safety model, all enforced here on the backend (the UI only mirrors it):
- Modes: off | paper | live. Live needs saved+validated live keys, confirmed risk limits and the
  typed confirmation phrase; leaving Live re-locks it.
- Every order is a two-step ticket: propose -> the user reviews -> confirm(ticket_id, token).
  submit_order is called from exactly one place: confirm(). Nothing places orders on its own.
- Risk limits are checked when the ticket is proposed AND again at confirm time.
- US equities only, market/limit only, DAY orders, no extended hours, no margin (cash only),
  no short selling (sells limited to shares held), no options/crypto/leverage.
- Every step is written to the exec_audit table.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import db, market
from ..secrets_store import delete_secret, get_secret, mask, scrub, set_secret
from .broker import AlpacaBroker, BrokerError, MockBroker, OrderReq

MODES = ("off", "paper", "live")
TICKET_TTL = timedelta(minutes=5)
SYMBOL_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")
LIVE_PHRASES = {"ar": "أفهم أن هذا مال حقيقي", "en": "I understand this is real money"}
LIQUIDATE_PHRASES = {"ar": "أؤكد بيع كل المراكز", "en": "I confirm selling all positions"}

# Conservative defaults (USD / count). The user can edit them; Live requires reviewing them first.
DEFAULT_LIMITS = {"max_order_usd": 500.0, "max_symbol_exposure_usd": 1000.0, "daily_loss_limit_usd": 200.0, "max_orders_per_day": 5}
LIMIT_BOUNDS = {"max_order_usd": (1, 1_000_000), "max_symbol_exposure_usd": (1, 5_000_000),
                "daily_loss_limit_usd": (1, 1_000_000), "max_orders_per_day": (1, 100)}

SCHEMA = """
CREATE TABLE IF NOT EXISTS exec_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL, mode TEXT NOT NULL, broker TEXT, event TEXT NOT NULL,
  ticket_id TEXT, session_id TEXT, symbol TEXT, side TEXT, order_type TEXT,
  qty REAL, notional REAL, limit_price REAL, est_cost REAL,
  limits_json TEXT, broker_order_id TEXT, broker_json TEXT, message TEXT
);
CREATE TABLE IF NOT EXISTS exec_tickets (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, mode TEXT NOT NULL, broker TEXT,
  session_id TEXT, symbol TEXT, side TEXT, order_type TEXT, qty REAL, notional REAL, limit_price REAL,
  est_cost REAL, price REAL, checks_json TEXT, token TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exec_orders (
  broker_order_id TEXT PRIMARY KEY, mode TEXT NOT NULL, broker TEXT, ticket_id TEXT, session_id TEXT,
  symbol TEXT, last_status TEXT, updated_at TEXT
);
"""
_lock = threading.RLock()


class ExecError(Exception):
    def __init__(self, code: str, character: str = "Tank", **data):
        super().__init__(code)
        self.code, self.character, self.data = code, character, data


def init() -> None:
    with db.tx() as c:
        c.executescript(SCHEMA)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ny_day() -> str:
    return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- settings
def mode() -> str:
    m = db.get_setting("exec_mode", "off")
    return m if m in MODES else "off"


def limits(m: str) -> dict:
    stored = db.get_setting(f"exec_limits:{m}") or {}
    return {**DEFAULT_LIMITS, **stored}


def limits_confirmed(m: str) -> bool:
    return bool(db.get_setting(f"exec_limits_confirmed:{m}", False))


def live_unlocked() -> bool:
    return bool(db.get_setting("exec_live_unlocked", False)) and mode() == "live"


def _keys(m: str) -> tuple[str | None, str | None]:
    # Keyring only. Live keys are never read from .env or the environment.
    return get_secret(f"alpaca:{m}:key_id"), get_secret(f"alpaca:{m}:secret")


def broker_for(m: str):
    if m == "off":
        raise ExecError("mode_off", "Leo")
    kid, sec = _keys(m)
    if m == "paper":
        return AlpacaBroker(kid, sec, paper=True) if kid and sec else MockBroker()
    if os.environ.get("VEYRO_BLOCK_LIVE") == "1":
        raise ExecError("live_blocked_in_dev", "Tank")
    if not (kid and sec):
        raise ExecError("no_live_keys", "Pip")
    return AlpacaBroker(kid, sec, paper=False)


def broker_label(m: str) -> str:
    if m == "off":
        return "none"
    kid, sec = _keys(m)
    if m == "paper" and not (kid and sec):
        return "mock"
    return "alpaca"


# ---------------------------------------------------------------- audit
def audit(event: str, *, m: str | None = None, ticket: dict | None = None, message: str = "", broker_order_id: str | None = None,
          broker_resp: dict | None = None, session_id: str | None = None) -> None:
    m = m or mode()
    t = ticket or {}
    with db.tx() as c:
        c.execute(
            "INSERT INTO exec_audit(ts,mode,broker,event,ticket_id,session_id,symbol,side,order_type,qty,notional,limit_price,est_cost,"
            "limits_json,broker_order_id,broker_json,message) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_now().isoformat(timespec="seconds"), m, t.get("broker") or broker_label(m), event, t.get("id"),
             t.get("session_id") or session_id, t.get("symbol"), t.get("side"), t.get("order_type"), t.get("qty"), t.get("notional"),
             t.get("limit_price"), t.get("est_cost"), json.dumps(limits(m)) if m != "off" else None, broker_order_id,
             scrub(json.dumps(broker_resp, default=str)) if broker_resp else None, scrub(message)[:500]))


def audit_rows(limit: int = 500) -> list[dict]:
    return db.q("SELECT * FROM exec_audit ORDER BY id DESC LIMIT ?", (limit,))


def audit_csv() -> str:
    rows = db.q("SELECT * FROM exec_audit ORDER BY id")
    buf = io.StringIO()
    cols = ["id", "ts", "mode", "broker", "event", "ticket_id", "session_id", "symbol", "side", "order_type", "qty", "notional",
            "limit_price", "est_cost", "limits_json", "broker_order_id", "broker_json", "message"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def orders_today(m: str) -> int:
    day = _ny_day()
    rows = db.q("SELECT ts FROM exec_audit WHERE mode=? AND event='submitted'", (m,))
    return sum(1 for r in rows if datetime.fromisoformat(r["ts"]).astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d") == day)


# ---------------------------------------------------------------- status / settings actions
def status() -> dict:
    m = mode()
    out = {"mode": m, "broker": broker_label(m), "live_unlocked": live_unlocked(),
           "limits": {k: limits(k) for k in ("paper", "live")},
           "limits_confirmed": {k: limits_confirmed(k) for k in ("paper", "live")},
           "keys": {}, "phrases": LIVE_PHRASES, "liquidate_phrases": LIQUIDATE_PHRASES}
    for k in ("paper", "live"):
        kid, sec = _keys(k)
        out["keys"][k] = {"present": bool(kid and sec), "masked": mask(kid)}
    out["live_checklist"] = {"keys": out["keys"]["live"]["present"] and bool(db.get_setting("exec_live_keys_valid", False)),
                             "limits": limits_confirmed("live")}
    return out


def save_keys(m: str, key_id: str, secret: str) -> dict:
    if m not in ("paper", "live"):
        raise ExecError("bad_mode")
    key_id, secret = key_id.strip(), secret.strip()
    if not (8 <= len(key_id) <= 64 and 16 <= len(secret) <= 128) or any(ch.isspace() for ch in key_id + secret):
        raise ExecError("bad_keys", "Pip")
    # Validate against the matching Alpaca environment before storing.
    if not (m == "live" and os.environ.get("VEYRO_BLOCK_LIVE") == "1"):
        try:
            AlpacaBroker(key_id, secret, paper=(m == "paper")).account()
        except BrokerError as e:
            audit("keys_rejected", m=m, message=f"{m} keys failed validation ({e.code})")
            raise ExecError("keys_invalid", "Pip") from None
    set_secret(f"alpaca:{m}:key_id", key_id)
    set_secret(f"alpaca:{m}:secret", secret)
    if m == "live":
        db.set_setting("exec_live_keys_valid", True)
    audit("keys_saved", m=m, message=f"{m} keys saved ({mask(key_id)})")
    return status()


def delete_keys(m: str) -> dict:
    delete_secret(f"alpaca:{m}:key_id")
    delete_secret(f"alpaca:{m}:secret")
    if m == "live":
        db.set_setting("exec_live_keys_valid", False)
        if mode() == "live":
            set_mode("off")
    audit("keys_deleted", m=m, message=f"{m} keys removed")
    return status()


def set_limits(m: str, new: dict) -> dict:
    if m not in ("paper", "live"):
        raise ExecError("bad_mode")
    clean = {}
    for k, (lo, hi) in LIMIT_BOUNDS.items():
        v = new.get(k, limits(m)[k])
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ExecError("bad_limit", "Tank", field=k) from None
        if not (lo <= v <= hi) or math.isnan(v):
            raise ExecError("bad_limit", "Tank", field=k)
        clean[k] = int(v) if k == "max_orders_per_day" else round(v, 2)
    db.set_setting(f"exec_limits:{m}", clean)
    db.set_setting(f"exec_limits_confirmed:{m}", True)
    audit("limits_saved", m=m, message=json.dumps(clean))
    return status()


def set_mode(new: str, phrase: str | None = None) -> dict:
    if new not in MODES:
        raise ExecError("bad_mode")
    with _lock:
        if new == "live":
            ok_keys = status()["live_checklist"]["keys"]
            if not ok_keys:
                raise ExecError("no_live_keys", "Pip")
            if not limits_confirmed("live"):
                raise ExecError("limits_not_set", "Tank")
            if (phrase or "").strip() not in LIVE_PHRASES.values():
                raise ExecError("phrase_mismatch", "Leo")
            db.set_setting("exec_live_unlocked", True)
        else:
            db.set_setting("exec_live_unlocked", False)  # leaving Live always re-locks it
        old = mode()
        db.set_setting("exec_mode", new)
        audit("mode_changed", m=new, message=f"{old} -> {new}")
    return status()


# ---------------------------------------------------------------- tickets
def _position(b, symbol: str) -> dict | None:
    return next((p for p in b.positions() if p["symbol"] == symbol), None)


def _checks(m: str, b, t: dict) -> list[dict]:
    """Risk checks. Each: {id, ok, value, limit}. Evaluated at propose and again at confirm."""
    L = limits(m)
    acct = b.account()
    checks = []
    checks.append({"id": "max_order", "ok": t["est_cost"] <= L["max_order_usd"] + 1e-9, "value": round(t["est_cost"], 2), "limit": L["max_order_usd"]})
    pos = _position(b, t["symbol"])
    pos_val = (pos or {}).get("market_value") or 0.0
    open_buys = sum((o.get("notional") or (o.get("qty") or 0) * (o.get("limit_price") or t["price"])) for o in b.orders("open")
                    if o["symbol"] == t["symbol"] and o["side"] == "buy")
    exposure = pos_val + open_buys + (t["est_cost"] if t["side"] == "buy" else 0.0)
    checks.append({"id": "symbol_exposure", "ok": t["side"] == "sell" or exposure <= L["max_symbol_exposure_usd"] + 1e-9,
                   "value": round(exposure, 2), "limit": L["max_symbol_exposure_usd"]})
    day_pl = (acct["equity"] or 0) - (acct["last_equity"] or 0)
    checks.append({"id": "daily_loss", "ok": day_pl > -L["daily_loss_limit_usd"], "value": round(day_pl, 2), "limit": -L["daily_loss_limit_usd"]})
    n = orders_today(m)
    checks.append({"id": "orders_today", "ok": n < L["max_orders_per_day"], "value": n, "limit": L["max_orders_per_day"]})
    if t["side"] == "buy":
        cash = min(x for x in (acct["cash"], acct["non_marginable_buying_power"]) if x is not None)
        checks.append({"id": "cash_only", "ok": t["est_cost"] <= cash + 1e-9, "value": round(t["est_cost"], 2), "limit": round(cash, 2)})
    else:
        held = (pos or {}).get("qty") or 0.0
        need = t["qty"] if t["qty"] is not None else (t["notional"] / t["price"])
        checks.append({"id": "no_short", "ok": held > 0 and need <= held + 1e-9, "value": round(need, 6), "limit": round(held, 6)})
    checks.append({"id": "account_ok", "ok": not acct["trading_blocked"], "value": acct["status"], "limit": None})
    return checks


def propose(*, symbol: str, side: str, order_type: str, amount_usd: float | None = None, qty: float | None = None,
            limit_price: float | None = None, session_id: str | None = None) -> dict:
    m = mode()
    if m == "off":
        raise ExecError("mode_off", "Leo")
    if m == "live" and not live_unlocked():
        raise ExecError("live_locked", "Tank")
    symbol = (symbol or "").strip().upper()
    if not SYMBOL_RE.match(symbol):
        raise ExecError("bad_symbol", "Benny")
    if side not in ("buy", "sell"):
        raise ExecError("side_not_allowed", "Tank")
    if order_type not in ("market", "limit"):
        raise ExecError("type_not_allowed", "Tank")  # market & limit only in this version
    b = broker_for(m)
    try:
        asset = b.asset(symbol)
    except BrokerError:
        raise ExecError("unknown_asset", "Benny") from None
    if asset["class"] != "us_equity" or not asset["tradable"]:
        raise ExecError("asset_not_allowed", "Tank")  # no options, crypto, or untradable assets
    px = market.last_price(symbol)
    if not px:
        raise ExecError("no_price", "Benny")
    price = px["price"]
    clock = b.clock()

    notional = None
    if order_type == "limit":
        if not limit_price or limit_price <= 0:
            raise ExecError("bad_limit_price", "Benny")
        limit_price = round(float(limit_price), 2 if limit_price >= 1 else 4)
        if qty is None:
            if not amount_usd or amount_usd <= 0:
                raise ExecError("bad_amount", "Benny")
            qty = math.floor(amount_usd / limit_price)
        qty = math.floor(qty)  # whole shares for limit orders
        if qty < 1:
            raise ExecError("too_small", "Benny")
        est = qty * limit_price
    else:
        if not clock["open"]:
            # Nothing is queued silently: market orders need an open market; offer a limit order instead.
            raise ExecError("market_closed", "Leo", next_open=clock.get("next_open"))
        if qty is not None:
            qty = float(qty)
            if qty <= 0:
                raise ExecError("bad_amount", "Benny")
            if not asset["fractionable"]:
                qty = math.floor(qty)
                if qty < 1:
                    raise ExecError("too_small", "Benny")
            est = qty * price
        else:
            if not amount_usd or amount_usd < 1:
                raise ExecError("bad_amount", "Benny")
            if asset["fractionable"]:
                notional = round(float(amount_usd), 2)
                est = notional
            else:
                qty = math.floor(amount_usd / price)
                if qty < 1:
                    raise ExecError("too_small", "Benny")
                est = qty * price
    if side == "sell" and notional is not None:
        qty, notional = round(notional / price, 6), None  # sells are sized in shares against what is held

    t = {"id": uuid.uuid4().hex[:12], "mode": m, "broker": b.label, "session_id": session_id, "symbol": symbol, "side": side,
         "order_type": order_type, "qty": qty, "notional": notional, "limit_price": limit_price, "est_cost": round(est, 2),
         "price": price, "price_as_of": px["as_of"], "price_source": px["source"], "market_open": clock["open"],
         "next_open": clock.get("next_open")}
    checks = _checks(m, b, t)
    ok = all(c["ok"] for c in checks)
    token = secrets.token_urlsafe(16)
    now = _now()
    with db.tx() as c:
        c.execute("INSERT INTO exec_tickets(id,created_at,expires_at,mode,broker,session_id,symbol,side,order_type,qty,notional,limit_price,"
                  "est_cost,price,checks_json,token,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (t["id"], now.isoformat(), (now + TICKET_TTL).isoformat(), m, b.label, session_id, symbol, side, order_type, qty,
                   notional, limit_price, t["est_cost"], price, json.dumps(checks), token, "open" if ok else "blocked"))
    audit("proposed" if ok else "rejected", m=m, ticket=t,
          message="all checks passed" if ok else "blocked by: " + ", ".join(c["id"] for c in checks if not c["ok"]))
    remaining = limits(m)["max_orders_per_day"] - orders_today(m)
    return {**t, "checks": checks, "ok": ok, "token": token if ok else None, "expires_at": (now + TICKET_TTL).isoformat(),
            "orders_left_today": max(0, remaining), "limits": limits(m)}


def confirm(ticket_id: str, token: str) -> dict:
    """The only code path that submits an order. Requires the ticket's one-time token."""
    with _lock:
        row = db.q1("SELECT * FROM exec_tickets WHERE id=?", (ticket_id,))
        if not row:
            raise ExecError("no_ticket", "Leo")
        if row["status"] != "open":
            raise ExecError("ticket_used", "Leo")
        if not secrets.compare_digest(row["token"], token or ""):
            raise ExecError("bad_token", "Tank")
        if datetime.fromisoformat(row["expires_at"]) < _now():
            with db.tx() as c:
                c.execute("UPDATE exec_tickets SET status='expired' WHERE id=?", (ticket_id,))
            raise ExecError("ticket_expired", "Leo")
        m = mode()
        if row["mode"] != m:
            raise ExecError("mode_changed", "Leo")
        if m == "live" and not live_unlocked():
            raise ExecError("live_locked", "Tank")
        b = broker_for(m)
        t = dict(row)
        t["price"] = row["price"]
        checks = _checks(m, b, t)  # limits enforced again at the moment of confirmation
        if not all(c["ok"] for c in checks):
            with db.tx() as c:
                c.execute("UPDATE exec_tickets SET status='rejected' WHERE id=?", (ticket_id,))
            audit("rejected", m=m, ticket=t, message="blocked at confirm by: " + ", ".join(c["id"] for c in checks if not c["ok"]))
            raise ExecError("limit_hit", "Tank", checks=checks)
        with db.tx() as c:
            c.execute("UPDATE exec_tickets SET status='confirmed' WHERE id=?", (ticket_id,))
        audit("confirmed", m=m, ticket=t, message="user confirmed ticket")
        req = OrderReq(t["symbol"], t["side"], t["order_type"], t["qty"], t["notional"], t["limit_price"], f"veyro-{ticket_id}")
        try:
            o = b.submit(req)
        except BrokerError as e:
            audit("failed", m=m, ticket=t, message=f"broker error: {e.code} {e.detail}")
            raise ExecError("broker_failed", "Pip") from None
        with db.tx() as c:
            c.execute("INSERT OR REPLACE INTO exec_orders(broker_order_id,mode,broker,ticket_id,session_id,symbol,last_status,updated_at)"
                      " VALUES(?,?,?,?,?,?,?,?)", (o["id"], m, b.label, ticket_id, t["session_id"], t["symbol"], o["status"], db.now()))
        audit("submitted", m=m, ticket=t, broker_order_id=o["id"], broker_resp=o, message=f"status={o['status']}")
        if o["status"] == "filled":
            audit("filled", m=m, ticket=t, broker_order_id=o["id"], broker_resp=o, message=f"filled {o['filled_qty']} @ {o['filled_avg_price']}")
            with db.tx() as c:
                c.execute("UPDATE exec_orders SET last_status='filled' WHERE broker_order_id=?", (o["id"],))
        return {"order": o, "mode": m, "broker": b.label}


# ---------------------------------------------------------------- orders / portfolio / kill switch
def sync() -> dict:
    """Pull orders from the broker, record status changes (fills, cancels, expiries) in the audit log."""
    m = mode()
    if m == "off":
        return {"mode": m, "orders": [], "events": []}
    b = broker_for(m)
    orders = b.orders("all", 100)
    known = {r["broker_order_id"]: r for r in db.q("SELECT * FROM exec_orders WHERE mode=?", (m,))}
    events = []
    for o in orders:
        k = known.get(o["id"])
        if not k or k["last_status"] == o["status"]:
            continue
        if o["status"] in ("filled", "partially_filled", "canceled", "expired", "rejected"):
            ev = {"filled": "filled", "partially_filled": "partially_filled", "canceled": "cancelled", "expired": "cancelled",
                  "rejected": "failed"}[o["status"]]
            t = {"id": k["ticket_id"], "session_id": k["session_id"], "symbol": o["symbol"], "side": o["side"], "order_type": o["type"],
                 "qty": o["qty"], "notional": o["notional"], "limit_price": o["limit_price"], "broker": k["broker"]}
            audit(ev, m=m, ticket=t, broker_order_id=o["id"], broker_resp=o, message=f"broker status {o['status']}")
            events.append({"event": ev, "order": o})
        with db.tx() as c:
            c.execute("UPDATE exec_orders SET last_status=?, updated_at=? WHERE broker_order_id=?", (o["status"], db.now(), o["id"]))
    for o in orders:
        o["veyro"] = o["id"] in known
    return {"mode": m, "broker": b.label, "orders": orders, "events": events}


def cancel(order_id: str) -> dict:
    m = mode()
    b = broker_for(m)
    k = db.q1("SELECT * FROM exec_orders WHERE broker_order_id=?", (order_id,))
    try:
        b.cancel(order_id)
    except BrokerError as e:
        audit("failed", m=m, broker_order_id=order_id, message=f"cancel failed: {e.code}")
        raise ExecError("cancel_failed", "Pip") from None
    audit("cancel_requested", m=m, broker_order_id=order_id, session_id=(k or {}).get("session_id"), message="user cancelled order")
    return sync()


def kill() -> dict:
    """Kill switch: cancel all open orders on the active account and turn execution Off. Positions are untouched."""
    m = mode()
    cancelled, err = [], None
    if m != "off":
        try:
            cancelled = broker_for(m).cancel_all()
        except (BrokerError, ExecError) as e:
            err = getattr(e, "code", "error")
    set_mode("off")
    audit("kill_switch", m=m, message=f"cancelled {len(cancelled)} open orders; execution off" + (f"; cancel error {err}" if err else ""))
    return {"cancelled": len(cancelled), "error": err, **status()}


def liquidate(phrase: str) -> dict:
    m = mode()
    if m == "off":
        raise ExecError("mode_off", "Leo")
    if (phrase or "").strip() not in LIQUIDATE_PHRASES.values():
        raise ExecError("phrase_mismatch", "Leo")
    if m == "live" and not live_unlocked():
        raise ExecError("live_locked", "Tank")
    res = broker_for(m).close_all()
    audit("liquidate", m=m, broker_resp={"result": res}, message=f"closed {len(res)} positions (user confirmed)")
    return {"closed": res}


def portfolio() -> dict:
    m = mode()
    if m == "off":
        return {"mode": m, "available": False}
    try:
        b = broker_for(m)
        acct = b.account()
        pos = b.positions()
        clock = b.clock()
    except (BrokerError, ExecError) as e:
        return {"mode": m, "available": False, "error": getattr(e, "code", "error")}
    L = limits(m)
    return {"mode": m, "broker": b.label, "available": True, "account": acct, "positions": pos, "clock": clock,
            "day_pl": round((acct["equity"] or 0) - (acct["last_equity"] or 0), 2),
            "orders_today": orders_today(m), "limits": L}


def acted_sessions() -> dict[str, dict]:
    """session_id -> {'submitted': n, 'filled': n} for History."""
    out: dict[str, dict] = {}
    for r in db.q("SELECT session_id, event FROM exec_audit WHERE session_id IS NOT NULL AND event IN ('submitted','filled')"):
        d = out.setdefault(r["session_id"], {"submitted": 0, "filled": 0})
        d[r["event"]] += 1
    return out
