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
            if h is not None and not h.empty:
                h = h.dropna(subset=["Close"])   # NaN would break JSON and the charts
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
    from datetime import date
    try:
        age_days = (date.today() - date.fromisoformat(date_iso[:10])).days
    except ValueError:
        return None
    h = history(ticker, "2y" if age_days < 700 else "5y" if age_days < 1800 else "max")
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


def screen(screener: str, count: int, max_price: float | None = None) -> list[dict]:
    """Real screener candidates. With max_price (the owner's budget), only stocks where at least one whole
    share fits the budget are suggested."""
    if screener not in SCREENERS:
        raise ValueError("unknown screener")
    try:
        r = yf.screen(screener, count=min(250, max(count * (8 if max_price else 3), 10)))
    except Exception as e:  # noqa: BLE001
        raise MarketDataUnavailable(type(e).__name__) from e
    out = []
    as_of = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for qt in r.get("quotes", []):
        sym = qt.get("symbol")
        if not sym or qt.get("quoteType") != "EQUITY" or "." in sym:
            continue  # US common stock only
        px = qt.get("regularMarketPrice")
        if max_price and (px is None or px > max_price):
            continue  # can't buy even one share with this budget
        out.append({"symbol": sym, "name": qt.get("shortName") or qt.get("longName"),
                    "price": qt.get("regularMarketPrice"), "change_pct": qt.get("regularMarketChangePercent"),
                    "volume": qt.get("regularMarketVolume"), "as_of": as_of, "source": SOURCE})
        if len(out) >= count:
            break
    if not out:
        raise MarketDataUnavailable("empty")
    return out


# ---------------------------------------------------------------- ticker search by name
# Common names people type in Arabic (and a few English nicknames) -> Yahoo symbol. Yahoo's own search
# doesn't understand Arabic names, so these are matched locally first. Saudi symbols use Yahoo's ".SR".
ALIASES: list[tuple[str, str, tuple[str, ...]]] = [
    ("2222.SR", "Saudi Aramco", ("ارامكو", "أرامكو", "aramco")),
    ("1120.SR", "Al Rajhi Bank", ("الراجحي", "مصرف الراجحي", "rajhi")),
    ("2010.SR", "SABIC", ("سابك", "sabic")),
    ("7010.SR", "stc (Saudi Telecom)", ("الاتصالات السعودية", "اس تي سي", "stc")),
    ("1180.SR", "Saudi National Bank", ("الأهلي", "الاهلي", "البنك الأهلي", "snb")),
    ("1211.SR", "Ma'aden", ("معادن", "maaden")),
    ("1150.SR", "Alinma Bank", ("الإنماء", "الانماء", "مصرف الإنماء", "alinma")),
    ("2280.SR", "Almarai", ("المراعي", "almarai")),
    ("1010.SR", "Riyad Bank", ("بنك الرياض", "riyad bank")),
    ("2082.SR", "ACWA Power", ("أكوا باور", "اكوا باور", "acwa")),
    ("4190.SR", "Jarir Marketing", ("جرير", "jarir")),
    ("7020.SR", "Etihad Etisalat (Mobily)", ("موبايلي", "mobily")),
    ("5110.SR", "Saudi Electricity", ("الكهرباء السعودية", "كهرباء")),
    ("4013.SR", "Dr. Sulaiman Al Habib", ("الحبيب", "سليمان الحبيب")),
    ("2050.SR", "Savola", ("صافولا", "savola")),
    ("4280.SR", "Kingdom Holding", ("المملكة القابضة",)),
    ("4300.SR", "Dar Al Arkan", ("دار الأركان", "دار الاركان")),
    ("AAPL", "Apple", ("أبل", "ابل", "آبل")),
    ("MSFT", "Microsoft", ("مايكروسوفت",)),
    ("NVDA", "NVIDIA", ("إنفيديا", "انفيديا", "نفيديا")),
    ("TSLA", "Tesla", ("تسلا",)),
    ("AMZN", "Amazon", ("أمازون", "امازون")),
    ("GOOGL", "Alphabet (Google)", ("جوجل", "قوقل", "ألفابت")),
    ("META", "Meta Platforms", ("ميتا", "فيسبوك")),
    ("NFLX", "Netflix", ("نتفليكس",)),
    ("AMD", "AMD", ("اي ام دي",)),
    ("INTC", "Intel", ("إنتل", "انتل")),
    ("BTC-USD", "Bitcoin", ("بيتكوين", "بتكوين", "bitcoin")),
    ("ETH-USD", "Ethereum", ("إيثريوم", "ايثريوم", "ethereum")),
]

_SEARCH_TYPES = {"EQUITY", "ETF", "INDEX", "CRYPTOCURRENCY"}


def _norm(s: str) -> str:
    s = s.strip().lower()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        s = s.replace(a, b)
    return s


def search(query: str, limit: int = 8) -> list[dict]:
    """Find tickers by company name or symbol. Local Arabic aliases first, then Yahoo Finance search."""
    q = _norm(query)
    out: list[dict] = []
    seen: set[str] = set()
    for sym, name, keys in ALIASES:
        if len(q) >= 2 and any(q in _norm(k) or (len(q) >= 3 and _norm(k) in q) for k in keys) or q == sym.lower():
            out.append({"symbol": sym, "name": name, "exchange": "Tadawul" if sym.endswith(".SR") else None,
                        "type": "INDEX" if sym.startswith("^") else "CRYPTOCURRENCY" if sym.endswith("-USD") else "EQUITY",
                        "source": "Veyro"})
            seen.add(sym)

    def fetch():
        try:
            s = yf.Search(query.strip(), max_results=limit, news_count=0, lists_count=0, enable_fuzzy_query=True)
            return [{"symbol": x["symbol"], "name": x.get("shortname") or x.get("longname"),
                     "exchange": x.get("exchDisp") or x.get("exchange"), "type": x.get("quoteType"), "source": SOURCE}
                    for x in s.quotes if x.get("quoteType") in _SEARCH_TYPES]
        except Exception as e:  # noqa: BLE001
            log.info("ticker search unavailable: %s", type(e).__name__)
            return []
    # Yahoo only understands Latin text; skip the network call for purely Arabic queries.
    if any("a" <= c <= "z" or c.isdigit() for c in q):
        for r in _cached(f"search:{q}", 3600, fetch):
            if r["symbol"] not in seen:
                out.append(r)
                seen.add(r["symbol"])
    return out[:limit]
