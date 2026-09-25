"""Money-saving and follow-up features:
- reuse: an analysis already done today for the same stock and models is reopened instead of paid for again;
- prescreen: economy mode ranks a list with free price data and sends only the best few to the full team;
- paper: a virtual portfolio that follows the team's calls, measured against each market's benchmark;
- price alerts: "tell me when gold passes X", checked on every live tick and every few minutes.
"""
from __future__ import annotations

import logging
import math
import threading

from . import db, market, runner

log = logging.getLogger("veyro.extras")


# ---------------------------------------------------------------- reuse today's analysis
def reusable(ticker: str, trade_date: str | None = None) -> dict | None:
    """The latest finished real session for this stock and date, run with the models selected now."""
    provider, quick, deep = runner.settings_models()
    r = db.q1("SELECT id, created_at, rating, finished_at FROM sessions WHERE ticker=? AND trade_date=? AND mode='real' "
              "AND status='done' AND provider=? AND quick_model=? AND deep_model=? ORDER BY created_at DESC LIMIT 1",
              (ticker, trade_date or runner.ny_today(), provider, quick, deep))
    return r


def replay(sid: str) -> None:
    """Rebuild a finished session's event stream from the database (no model calls), so a scan can show it."""
    import asyncio  # noqa: F401
    s = db.get_session(sid)
    if not s or sid in runner.BUSES and runner.BUSES[sid].events:
        return
    bus = runner.BUSES.get(sid)
    if bus is None:
        return
    lang = s["lang"]
    bus.publish({"type": "session", "id": sid, "ticker": s["ticker"], "mode": s["mode"], "lang": lang, "trade_date": s["trade_date"],
                 "estimate": {"known": True, "low": 0, "high": 0, "currency": "USD", "sessions": 1}, "reused": True,
                 "on_break": (s.get("config") or {}).get("on_break", [])})
    h = market.history(s["ticker"])
    bus.publish({"type": "market", "data": h, "available": h is not None})
    for t in s["turns"]:
        text = (t["voice_ar"] if lang == "ar" else t["voice_en"]) or t["voice_en"] or t["voice_ar"] or ""
        if not text:   # the voice line had failed: show the same fallback line as the live run
            text = runner.fallback_line(t["character"], lang) if t["character"] in runner.CHARACTERS else \
                ("التحليل الكامل محفوظ في التقرير." if lang == "ar" else "The full analysis is in the report.")
        bus.publish({"type": "agent_message", "character": t["character"], "node": t["node"], "turn_id": t["id"], "text": text,
                     "lang": lang, "texts": {k: v for k, v in (("ar", t["voice_ar"]), ("en", t["voice_en"])) if v}})
        bus.publish({"type": "agent_done", "character": t["character"], "node": t["node"]})
    v = s.get("verdict")
    if v:
        bus.publish({"type": "verdict", **v, "price": {"price": s["price_at_verdict"], "spy": s["spy_at_verdict"],
                     "as_of": s["price_time"], "source": s["price_source"]}, "disclaimer": runner.DISCLAIMER.get(lang)})
    bus.publish({"type": "end", "status": "done"})


# ---------------------------------------------------------------- economy pre-screen (free, deterministic)
def prescreen(tickers: list[str]) -> list[dict]:
    """Rank by recent price behaviour only (free Yahoo data, no model): trend vs the 50-day average,
    3-month return, and a penalty for volatility. A filter to decide where to spend, not a verdict."""
    from concurrent.futures import ThreadPoolExecutor

    def one(t: str) -> dict:
        h = market.history(t, "6mo")
        cs = (h or {}).get("closes") or []
        if len(cs) < 30:
            return {"ticker": t, "score": None, "note": "no_data"}
        last = cs[-1]
        ma50 = sum(cs[-50:]) / len(cs[-50:])
        r3m = last / cs[-min(63, len(cs))] - 1
        rets = [cs[i] / cs[i - 1] - 1 for i in range(max(1, len(cs) - 63), len(cs))]
        vol = math.sqrt(sum(r * r for r in rets) / len(rets)) * math.sqrt(252)
        trend = last / ma50 - 1
        score = trend * 2 + r3m - vol * 0.3
        return {"ticker": t, "score": round(score, 4), "trend": round(trend, 4), "ret_3m": round(r3m, 4), "vol": round(vol, 4)}
    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(one, tickers))
    return sorted(rows, key=lambda r: (r["score"] is None, -(r["score"] or 0)))   # no data goes last


# ---------------------------------------------------------------- virtual portfolio
def paper_add(ticker: str, shares: float, session_id: str | None = None, rating: str | None = None) -> dict:
    px = market.last_price(ticker)
    if not px:
        raise ValueError("no_price")
    bench = runner.benchmark_for(ticker)
    b = market.last_price(bench)
    with db.tx() as c:
        c.execute("INSERT INTO paper(ticker,shares,entry_price,currency,bench,bench_entry,opened_at,session_id,rating) VALUES(?,?,?,?,?,?,?,?,?)",
                  (ticker, shares, px["price"], px.get("currency"), bench, b["price"] if b else None, db.now(), session_id, rating))
    return paper_view()


def paper_close(pid: int) -> dict:
    row = db.q1("SELECT * FROM paper WHERE id=?", (pid,))
    if row and not row["closed_at"]:
        px = market.last_price(row["ticker"])
        if not px:
            raise ValueError("no_price")   # never book an invented exit price
        b = market.last_price(row["bench"]) if row["bench"] else None
        # the index is frozen at the same moment as the stock, so a closed position's alpha stops moving
        with db.tx() as c:
            c.execute("UPDATE paper SET closed_at=?, exit_price=?, bench_exit=? WHERE id=?",
                      (db.now(), px["price"], b["price"] if b else None, pid))
    return paper_view()


def paper_remove(pid: int) -> dict:
    with db.tx() as c:
        c.execute("DELETE FROM paper WHERE id=?", (pid,))
    return paper_view()


def paper_view() -> dict:
    rows = db.q("SELECT * FROM paper ORDER BY opened_at DESC")
    totals: dict[str, dict] = {}
    for r in rows:
        now = r["exit_price"] if r["closed_at"] else ((market.last_price(r["ticker"]) or {}).get("price"))
        bnow = r.get("bench_exit") if r["closed_at"] else ((market.last_price(r["bench"]) or {}).get("price") if r["bench"] else None)
        r["price_now"] = now
        r["value"] = now * r["shares"] if now else None
        r["cost"] = r["entry_price"] * r["shares"]
        r["ret"] = now / r["entry_price"] - 1 if now else None
        r["bench_ret"] = bnow / r["bench_entry"] - 1 if bnow and r["bench_entry"] else None
        r["alpha"] = r["ret"] - r["bench_ret"] if r["ret"] is not None and r["bench_ret"] is not None else None
        cur = r["currency"] or "USD"
        t = totals.setdefault(cur, {"currency": cur, "cost": 0.0, "value": 0.0, "bench_weighted": 0.0, "bench_cost": 0.0, "known": True})
        t["cost"] += r["cost"]
        if r["value"] is None:
            t["known"] = False
        else:
            t["value"] += r["value"]
        if r["bench_ret"] is not None:
            t["bench_weighted"] += r["cost"] * r["bench_ret"]
            t["bench_cost"] += r["cost"]
    for t in totals.values():
        t["ret"] = t["value"] / t["cost"] - 1 if t["cost"] and t["known"] else None
        t["bench_ret"] = t["bench_weighted"] / t["bench_cost"] if t["bench_cost"] else None   # only rows with an index return
    return {"positions": rows, "totals": list(totals.values()), "source": market.SOURCE}


# ---------------------------------------------------------------- price alerts
_alock = threading.Lock()


def price_alerts(active_only: bool = False) -> list[dict]:
    q = "SELECT * FROM price_alerts" + (" WHERE triggered_at IS NULL" if active_only else "") + " ORDER BY id DESC"
    return db.q(q)


def add_price_alert(symbol: str, op: str, value: float) -> list[dict]:
    if op not in ("above", "below") or not value > 0:
        raise ValueError("bad_alert")
    with db.tx() as c:
        c.execute("INSERT INTO price_alerts(symbol,op,value,created_at) VALUES(?,?,?,?)", (symbol, op, float(value), db.now()))
    try:
        from . import live
        live.HUB.add_symbols({symbol})
    except Exception:  # noqa: BLE001
        pass
    return price_alerts()


def delete_price_alert(aid: int) -> list[dict]:
    with db.tx() as c:
        c.execute("DELETE FROM price_alerts WHERE id=?", (aid,))
    return price_alerts()


def check_price(symbol: str, price: float) -> None:
    """Called on every live tick and by the scheduler; fires each alert once."""
    with _alock:
        for a in db.q("SELECT * FROM price_alerts WHERE triggered_at IS NULL AND symbol=?", (symbol,)):
            hit = price >= a["value"] if a["op"] == "above" else price <= a["value"]
            if not hit:
                continue
            with db.tx() as c:
                c.execute("UPDATE price_alerts SET triggered_at=?, triggered_price=? WHERE id=?", (db.now(), price, a["id"]))
            from .assistant import add_alert
            word_ar, word_en = ("تجاوز", "rose above") if a["op"] == "above" else ("نزل تحت", "fell below")
            add_alert("price", symbol, "Pip",
                      f"تنبيه سعر! {symbol} {word_ar} {a['value']:,.2f} (الآن {price:,.2f})، سكوااك!",
                      f"Price alert! {symbol} {word_en} {a['value']:,.2f} (now {price:,.2f}), squawk!")


def check_all_prices() -> None:
    for sym in {a["symbol"] for a in price_alerts(True)}:
        px = market.last_price(sym)
        if px:
            check_price(sym, px["price"])
