"""Market data sources the owner can switch between (Settings → data source).

- yahoo: Yahoo Finance via yfinance (default; US, Saudi, indices, metals, live stream).
- stooq: Stooq's free CSV service (no key). US stocks, main indices, spot metals and FX; no Tadawul.
- alpha_vantage: Alpha Vantage with the owner's key (free tier ~25 requests a day). US stocks only here.
  Choosing it also switches TradingAgents' own data vendors to Alpha Vantage for the analysis.

Anything the chosen source doesn't cover falls back to Yahoo, and every result names the source it came from.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger("veyro.datasources")
SOURCES = {
    "yahoo": {"label": "Yahoo Finance", "key": None},
    "stooq": {"label": "Stooq", "key": None},
    "alpha_vantage": {"label": "Alpha Vantage", "key": "data:alpha_vantage"},
}
UA = {"User-Agent": "Mozilla/5.0 Veyro"}


def current() -> str:
    from . import db
    s = db.get_setting("data_source", "yahoo")
    return s if s in SOURCES else "yahoo"


def _get(url: str, timeout: float = 10) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


# ---------------------------------------------------------------- Stooq
STOOQ_MAP = {"^GSPC": "^spx", "^IXIC": "^ndq", "^DJI": "^dji", "GC=F": "xauusd", "SI=F": "xagusd", "PL=F": "xptusd",
             "PA=F": "xpdusd", "SAR=X": "usdsar", "USDSAR=X": "usdsar", "SARUSD=X": "sarusd", "SPY": "spy.us"}


def stooq_symbol(t: str) -> str | None:
    if t in STOOQ_MAP:
        return STOOQ_MAP[t]
    if any(c in t for c in ".^=") or not t.isalnum():
        return None          # Tadawul (.SR) and other exchanges aren't covered: Yahoo answers those
    return f"{t.lower()}.us"


def stooq_quote(t: str) -> dict | None:
    s = stooq_symbol(t)
    if not s:
        return None
    txt = _get(f"https://stooq.com/q/l/?s={urllib.parse.quote(s)}&f=sd2t2ohlcp&h&e=csv")
    rows = list(csv.DictReader(io.StringIO(txt)))
    if not rows:
        return None
    r = {k.strip().lower(): v for k, v in rows[0].items()}
    try:
        price = float(r.get("close") or "nan")
    except ValueError:
        return None
    if price != price:
        return None
    prev = r.get("prev") or r.get("previous") or r.get("p")
    try:
        prev_f = float(prev) if prev else None
    except ValueError:
        prev_f = None
    cur = "USD"
    return {"price": price, "prev_close": prev_f, "currency": cur, "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "Stooq"}


def stooq_history(t: str, days: int) -> dict | None:
    s = stooq_symbol(t)
    if not s:
        return None
    txt = _get(f"https://stooq.com/q/d/l/?s={urllib.parse.quote(s)}&i=d")
    rows = [r for r in csv.DictReader(io.StringIO(txt)) if r.get("Close") not in (None, "", "N/D")]
    if not rows:
        return None
    rows = rows[-days:]
    return {"ticker": t, "dates": [r["Date"] for r in rows], "closes": [round(float(r["Close"]), 4) for r in rows], "source": "Stooq"}


# ---------------------------------------------------------------- Alpha Vantage
def _av_key() -> str | None:
    from .secrets_store import get_secret
    return get_secret("data:alpha_vantage")


def _av(params: dict) -> dict | None:
    key = _av_key()
    if not key:
        return None
    data = json.loads(_get("https://www.alphavantage.co/query?" + urllib.parse.urlencode({**params, "apikey": key}), timeout=15))
    if any(k in data for k in ("Note", "Information", "Error Message")):
        log.info("alpha vantage refused: %s", next(iter(data))[:20])   # rate limit or unknown symbol
        return None
    return data


def av_quote(t: str) -> dict | None:
    if any(c in t for c in ".^="):
        return None
    d = _av({"function": "GLOBAL_QUOTE", "symbol": t})
    q = (d or {}).get("Global Quote") or {}
    if not q.get("05. price"):
        return None
    return {"price": float(q["05. price"]), "prev_close": float(q.get("08. previous close") or 0) or None, "currency": "USD",
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": "Alpha Vantage"}


def av_history(t: str, days: int) -> dict | None:
    if any(c in t for c in ".^="):
        return None
    d = _av({"function": "TIME_SERIES_DAILY", "symbol": t, "outputsize": "compact" if days <= 100 else "full"})
    ts = (d or {}).get("Time Series (Daily)") or {}
    if not ts:
        return None
    dates = sorted(ts)[-days:]
    return {"ticker": t, "dates": dates, "closes": [round(float(ts[x]["4. close"]), 4) for x in dates], "source": "Alpha Vantage"}


def quote(t: str) -> dict | None:
    """From the chosen non-Yahoo source, or None (the caller then asks Yahoo)."""
    src = current()
    try:
        if src == "stooq":
            return stooq_quote(t)
        if src == "alpha_vantage":
            return av_quote(t)
    except Exception as e:  # noqa: BLE001
        log.info("%s quote failed for %s: %s", src, t, type(e).__name__)
    return None


def history(t: str, days: int) -> dict | None:
    src = current()
    try:
        if src == "stooq":
            return stooq_history(t, days)
        if src == "alpha_vantage":
            return av_history(t, days)
    except Exception as e:  # noqa: BLE001
        log.info("%s history failed for %s: %s", src, t, type(e).__name__)
    return None


def framework_vendors(vendors: dict) -> dict:
    """TradingAgents' own vendor map: Alpha Vantage when chosen and a key is saved, else unchanged (yfinance)."""
    if current() == "alpha_vantage" and _av_key():
        return {**vendors, "core_stock_apis": "alpha_vantage", "technical_indicators": "alpha_vantage",
                "fundamental_data": "alpha_vantage", "news_data": "alpha_vantage"}
    return vendors
