"""Real market data via yfinance (the same default vendor TradingAgents uses).

Every function returns None / raises MarketDataUnavailable instead of inventing
numbers; callers show "unavailable" in the UI.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

import yfinance as yf

log = logging.getLogger("veyro.market")
SOURCE = "Yahoo Finance (yfinance)"

SCREENERS = {  # ids from yfinance PREDEFINED_SCREENER_QUERIES (equities only)
    "most_actives": {"ar": "الأكثر تداولاً اليوم", "en": "Most active today"},
    "day_gainers": {"ar": "الأكثر ارتفاعاً اليوم", "en": "Top gainers today"},
    "day_losers": {"ar": "الأكثر انخفاضاً اليوم", "en": "Top losers today"},
    "undervalued_large_caps": {"ar": "شركات كبيرة بتقييم منخفض", "en": "Undervalued large caps"},
    "undervalued_growth_stocks": {"ar": "أسهم نمو بتقييم منخفض", "en": "Undervalued growth stocks"},
    "growth_technology_stocks": {"ar": "أسهم تقنية نامية", "en": "Growing tech stocks"},
}


class MarketDataUnavailable(Exception):
    pass


_cache: dict[str, tuple[float, Any]] = {}
_clock = threading.Lock()


def _cached(key: str, ttl: float, fn):
    with _clock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    val = fn()
    with _clock:
        _cache[key] = (time.time(), val)
    return val


def last_price(ticker: str) -> dict | None:
    """{'price', 'currency', 'as_of', 'source'} or None."""
    def fetch():
        try:
            fi = yf.Ticker(ticker).fast_info
            p = fi["lastPrice"]
            if p is None or p != p or p <= 0:
                return None
            return {"price": float(p), "currency": fi.get("currency") or "USD",
                    "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": SOURCE}
        except Exception as e:  # noqa: BLE001
            log.info("price unavailable for %s: %s", ticker, type(e).__name__)
            return None
    return _cached(f"px:{ticker}", 60, fetch)


def history(ticker: str, period: str = "3mo") -> dict | None:
    def fetch():
        try:
            h = yf.Ticker(ticker).history(period=period, auto_adjust=False)
            if h is None or h.empty:
                return None
            closes = [round(float(v), 4) for v in h["Close"].tolist()]
            dates = [d.strftime("%Y-%m-%d") for d in h.index]
            return {"ticker": ticker, "dates": dates, "closes": closes, "source": SOURCE}
        except Exception as e:  # noqa: BLE001
            log.info("history unavailable for %s: %s", ticker, type(e).__name__)
            return None
    return _cached(f"hist:{ticker}:{period}", 600, fetch)


def close_on_or_before(ticker: str, date_iso: str) -> float | None:
    """Closing price on the given date or the last trading day before it."""
    h = history(ticker, "2y")
    if not h:
        return None
    best = None
    for d, c in zip(h["dates"], h["closes"]):
        if d <= date_iso[:10]:
            best = c
    return best


def market_status() -> dict | None:
    def fetch():
        try:
            s = yf.Market("US").status
            return {"open": s.get("status") == "open", "status": s.get("status"),
                    "next_open": s["open"].isoformat() if s.get("open") else None,
                    "next_close": s["close"].isoformat() if s.get("close") else None,
                    "source": SOURCE}
        except Exception as e:  # noqa: BLE001
            log.info("market status unavailable: %s", type(e).__name__)
            return None
    return _cached("mkt", 60, fetch)


def screen(screener: str, count: int) -> list[dict]:
    if screener not in SCREENERS:
        raise ValueError("unknown screener")
    try:
        r = yf.screen(screener, count=max(count * 3, 10))
    except Exception as e:  # noqa: BLE001
        raise MarketDataUnavailable(type(e).__name__) from e
    out = []
    as_of = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for qt in r.get("quotes", []):
        sym = qt.get("symbol")
        if not sym or qt.get("quoteType") != "EQUITY" or "." in sym:
            continue  # US common stock only
        out.append({"symbol": sym, "name": qt.get("shortName") or qt.get("longName"),
                    "price": qt.get("regularMarketPrice"), "change_pct": qt.get("regularMarketChangePercent"),
                    "volume": qt.get("regularMarketVolume"), "as_of": as_of, "source": SOURCE})
        if len(out) >= count:
            break
    if not out:
        raise MarketDataUnavailable("empty")
    return out
