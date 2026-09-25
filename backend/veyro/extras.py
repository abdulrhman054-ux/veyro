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
              (ticker, trade_date or runner.today_for(ticker), provider, quick, deep))
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
    bus.publish({"type": "end", "status": s["status"] if s["status"] in ("done", "cancelled", "error") else "done"})


# ---------------------------------------------------------------- economy pre-screen (free, deterministic)
PRESCREEN_MODES = ("momentum", "steady", "value")


def prescreen(tickers: list[str], mode: str = "momentum") -> list[dict]:
    """Rank by recent price behaviour only (free Yahoo data, no model). A filter to decide where to spend, not a verdict.
    momentum: trend vs the 50-day average x2 + 3-month return - 0.3 x volatility (favours what already ran up).
    steady:   12-month return skipping the last month - 0.5 x volatility - 0.5 x worst 6-month drop
              (favours steady long-run strength over a recent spike).
    value:    P/E against the company's own sector in its own market (log of peer median / P/E, clipped to +-1)
              + 5 x dividend yield (last 12 months, capped at 10%) - 0.3 x volatility. Loss-making companies and
              those without data go last with the reason (see valuation.py)."""
    from concurrent.futures import ThreadPoolExecutor
    mode = mode if mode in PRESCREEN_MODES else "momentum"

    def vol_of(cs):
        rets = [cs[i] / cs[i - 1] - 1 for i in range(max(1, len(cs) - 63), len(cs))]
        return math.sqrt(sum(r * r for r in rets) / len(rets)) * math.sqrt(252)

    def one(t: str) -> dict:
        h = market.history(t, "1y" if mode == "steady" else "6mo")
        cs = (h or {}).get("closes") or []
        if len(cs) < (150 if mode == "steady" else 30):
            return {"ticker": t, "score": None, "note": "no_data", "mode": mode}
        last = cs[-1]
        vol = vol_of(cs)
        if mode == "steady":
            m12_1 = cs[-22] / cs[0] - 1                       # skip the last month (short-term reversal)
            peak, dd = cs[-126], 0.0
            for c in cs[-126:]:
                peak = max(peak, c)
                dd = max(dd, 1 - c / peak)
            score = m12_1 - 0.5 * vol - 0.5 * dd
            return {"ticker": t, "score": round(score, 4), "ret_12_1": round(m12_1, 4), "vol": round(vol, 4),
                    "max_drop": round(dd, 4), "mode": mode}
        ma50 = sum(cs[-50:]) / len(cs[-50:])
        r3m = last / cs[-min(63, len(cs))] - 1
        trend = last / ma50 - 1
        score = trend * 2 + r3m - vol * 0.3
        return {"ticker": t, "score": round(score, 4), "trend": round(trend, 4), "ret_3m": round(r3m, 4), "vol": round(vol, 4), "mode": mode}
    if mode == "value":
        from . import valuation

        def prices(t):
            h = market.history(t, "6mo")
            return t, (h or {}).get("closes") or []
        with ThreadPoolExecutor(max_workers=8) as ex:
            closes = dict(ex.map(prices, tickers))
        vols = {t: (vol_of(cs) if len(cs) >= 30 else None) for t, cs in closes.items()}
        v = valuation.score(tickers, closes, vols)
        rows = [{"ticker": t, "mode": mode, "vol": round(vols[t], 4) if vols[t] is not None else None, **v[t],
                 **({"note": "no_data"} if v[t]["score"] is None and v[t]["value_note"] in (None, "no_data") else {})} for t in tickers]
        return sorted(rows, key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(one, tickers))
    return sorted(rows, key=lambda r: (r["score"] is None, -(r["score"] or 0)))   # no data goes last


# ---------------------------------------------------------------- virtual portfolio
def _fee(ticker: str, value: float) -> float:
    """The owner's broker fee (Settings) for a trade worth `value` in the stock's own currency; 0 when not entered."""
    from .allocation import _fee_fn, fees, market_of
    return round(_fee_fn(fees().get(market_of(ticker)) or {}, 1.0)(value), 4)


def _divs(ticker: str | None, start: str, end: str | None) -> float:
    """Dividends per share with an ex-date after `start` and up to `end` (or today)."""
    if not ticker:
        return 0.0
    end = (end or db.now())[:10]
    return sum(v for d, v in market.dividends(ticker) if start[:10] < d <= end)


def paper_add(ticker: str, shares: float, session_id: str | None = None, rating: str | None = None) -> dict:
    from .allocation import fx
    px = market.last_price(ticker)
    if not px:
        raise ValueError("no_price")
    bench = runner.benchmark_for(ticker)
    b = market.last_price(bench)
    cur = px.get("currency") or "USD"
    with db.tx() as c:
        c.execute("INSERT INTO paper(ticker,shares,entry_price,currency,bench,bench_entry,opened_at,session_id,rating,fee_in,fx_usd_entry) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (ticker, shares, px["price"], cur, bench, b["price"] if b else None, db.now(), session_id, rating,
                   _fee(ticker, px["price"] * shares), fx(cur, "USD")))
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
            c.execute("UPDATE paper SET closed_at=?, exit_price=?, bench_exit=?, fee_out=? WHERE id=?",
                      (db.now(), px["price"], b["price"] if b else None, _fee(row["ticker"], px["price"] * row["shares"]), pid))
    return paper_view()


def paper_remove(pid: int) -> dict:
    with db.tx() as c:
        c.execute("DELETE FROM paper WHERE id=?", (pid,))
    return paper_view()


def paper_view() -> dict:
    """Each position's result after the owner's broker fees (in and out) and with dividends received, against its
    index over the same time (index dividends included where the benchmark is a fund that pays them).
    Totals per currency, plus everything combined in US dollars at the entry and current exchange rates,
    so currency moves show up too."""
    from .allocation import fx
    rows = db.q("SELECT * FROM paper ORDER BY opened_at DESC")
    totals: dict[str, dict] = {}
    usd = {"cost": 0.0, "value": 0.0, "known": True}
    for r in rows:
        now = r["exit_price"] if r["closed_at"] else ((market.last_price(r["ticker"]) or {}).get("price"))
        bnow = r.get("bench_exit") if r["closed_at"] else ((market.last_price(r["bench"]) or {}).get("price") if r["bench"] else None)
        fee_in = r.get("fee_in") or 0.0
        fee_out = (r.get("fee_out") or 0.0) if r["closed_at"] else (_fee(r["ticker"], now * r["shares"]) if now else 0.0)
        div = _divs(r["ticker"], r["opened_at"], r["closed_at"]) * r["shares"]
        r["price_now"] = now
        r["dividends"] = round(div, 4)
        r["fees"] = round(fee_in + fee_out, 4)
        r["cost"] = r["entry_price"] * r["shares"] + fee_in
        r["value"] = now * r["shares"] - fee_out + div if now else None
        r["ret"] = r["value"] / r["cost"] - 1 if r["value"] is not None and r["cost"] else None
        bdiv = _divs(r["bench"], r["opened_at"], r["closed_at"]) if r["bench"] and not r["bench"].startswith("^") else 0.0
        r["bench_ret"] = (bnow + bdiv) / r["bench_entry"] - 1 if bnow and r["bench_entry"] else None
        r["alpha"] = r["ret"] - r["bench_ret"] if r["ret"] is not None and r["bench_ret"] is not None else None
        cur = r["currency"] or "USD"
        t = totals.setdefault(cur, {"currency": cur, "cost": 0.0, "value": 0.0, "bench_weighted": 0.0, "bench_cost": 0.0, "known": True,
                                    "fees": 0.0, "dividends": 0.0})
        t["cost"] += r["cost"]
        t["fees"] += r["fees"]
        t["dividends"] += r["dividends"]
        if r["value"] is None:
            t["known"] = False
        else:
            t["value"] += r["value"]
        if r["bench_ret"] is not None:
            t["bench_weighted"] += r["cost"] * r["bench_ret"]
            t["bench_cost"] += r["cost"]
        fx_in, fx_now = r.get("fx_usd_entry") or (1.0 if cur == "USD" else None), fx(cur, "USD")
        if fx_in and fx_now and r["value"] is not None:
            usd["cost"] += r["cost"] * fx_in
            usd["value"] += r["value"] * fx_now
        else:
            usd["known"] = False
    for t in totals.values():
        t["ret"] = t["value"] / t["cost"] - 1 if t["cost"] and t["known"] else None
        t["bench_ret"] = t["bench_weighted"] / t["bench_cost"] if t["bench_cost"] else None   # only rows with an index return
    combined = {"currency": "USD", "cost": round(usd["cost"], 2), "value": round(usd["value"], 2),
                "ret": usd["value"] / usd["cost"] - 1 if usd["known"] and usd["cost"] else None} if len(totals) > 1 else None
    return {"positions": rows, "totals": list(totals.values()), "combined_usd": combined, "source": market.SOURCE,
            "fees_set": any(v.get("set") for v in __import__("veyro.allocation", fromlist=["x"]).fees().values())}


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
    _sync_pins()
    return price_alerts()


def _sync_pins() -> None:
    """The live feed follows the symbols of active alerts only (fired or deleted alerts stop costing requests)."""
    try:
        from . import live
        live.HUB.set_pinned({a["symbol"] for a in price_alerts(True)})
    except Exception:  # noqa: BLE001
        pass


def delete_price_alert(aid: int) -> list[dict]:
    with db.tx() as c:
        c.execute("DELETE FROM price_alerts WHERE id=?", (aid,))
    _sync_pins()
    return price_alerts()


def check_price(symbol: str, price: float) -> None:
    """Called on every live tick and by the scheduler; fires each alert once."""
    fired = False
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
            fired = True
    if fired:
        _sync_pins()


def check_all_prices() -> None:
    for sym in {a["symbol"] for a in price_alerts(True)}:
        px = market.last_price(sym)
        if px:
            check_price(sym, px["price"])
