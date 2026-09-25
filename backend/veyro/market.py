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

from .lazy import yf   # loads on first use (fast startup)

log = logging.getLogger("veyro.market")
SOURCE = "Yahoo Finance (yfinance)"

SCREENERS = {  # ids from yfinance PREDEFINED_SCREENER_QUERIES (equities only)
    "most_actives": {"ar": "الأكثر تداولاً اليوم", "en": "Most active today"},
    "day_gainers": {"ar": "الأكثر ارتفاعاً اليوم", "en": "Top gainers today"},
    "day_losers": {"ar": "الأكثر انخفاضاً اليوم", "en": "Top losers today"},
    "undervalued_large_caps": {"ar": "شركات كبيرة بتقييم منخفض", "en": "Undervalued large caps"},
    "undervalued_growth_stocks": {"ar": "أسهم نمو بتقييم منخفض", "en": "Undervalued growth stocks"},
    "growth_technology_stocks": {"ar": "أسهم تقنية نامية", "en": "Growing tech stocks"},
    # Saudi market (Tadawul): Yahoo's screener with region "sa" (a field value listed in yfinance's own
    # EQUITY_SCREENER_EQ_MAP). No market-cap thresholds: their currency in the screener isn't documented.
    "sa_most_actives": {"ar": "🇸🇦 الأكثر تداولاً اليوم (تداول)", "en": "🇸🇦 Most active today (Tadawul)", "market": "sa"},
    "sa_day_gainers": {"ar": "🇸🇦 الأكثر ارتفاعاً اليوم (تداول)", "en": "🇸🇦 Top gainers today (Tadawul)", "market": "sa"},
    "sa_day_losers": {"ar": "🇸🇦 الأكثر انخفاضاً اليوم (تداول)", "en": "🇸🇦 Top losers today (Tadawul)", "market": "sa"},
    "sa_low_pe": {"ar": "🇸🇦 مكرر ربحية منخفض (تداول)", "en": "🇸🇦 Low P/E (Tadawul)", "market": "sa"},
}


def screener_market(screener: str) -> str:
    return SCREENERS.get(screener, {}).get("market", "us")


def _sa_query(screener: str):
    """(query, sort field, ascending) for the Saudi screeners."""
    from yfinance import EquityQuery as Q
    region = Q("eq", ["region", "sa"])
    liquid = Q("gt", ["dayvolume", 100000])   # shares traded today: keeps out names that barely traded
    if screener == "sa_most_actives":
        return Q("and", [region, liquid]), "dayvolume", False
    if screener == "sa_day_gainers":
        return Q("and", [region, liquid, Q("gt", ["percentchange", 0])]), "percentchange", False
    if screener == "sa_day_losers":
        return Q("and", [region, liquid, Q("lt", ["percentchange", 0])]), "percentchange", True
    return Q("and", [region, Q("btwn", ["peratio.lasttwelvemonths", 0, 15])]), "eodvolume", False


def _sa_fallback(screener: str) -> list[dict]:
    """Yahoo's screener didn't answer: today's movers among Veyro's own list of large Saudi companies, from
    their quotes (price vs previous close). Only for gainers/losers; the rest needs the screener."""
    if screener not in ("sa_day_gainers", "sa_day_losers"):
        return []
    from concurrent.futures import ThreadPoolExecutor
    from .beginner import UNIVERSE
    syms = list(dict.fromkeys([x[0] for x in UNIVERSE["sa"]] + [s for s, _, _ in ALIASES if s.endswith(".SR")]))
    with ThreadPoolExecutor(max_workers=8) as ex:
        pxs = dict(zip(syms, ex.map(last_price, syms)))
    rows = []
    for s, px in pxs.items():
        if px and px.get("prev_close"):
            ch = (px["price"] / px["prev_close"] - 1) * 100
            if (ch > 0) if screener == "sa_day_gainers" else (ch < 0):
                rows.append({"symbol": s, "regularMarketPrice": px["price"], "regularMarketChangePercent": ch,
                             "quoteType": "EQUITY", "currency": px.get("currency") or "SAR", "_fallback": True})
    return sorted(rows, key=lambda r: r["regularMarketChangePercent"], reverse=screener == "sa_day_gainers")


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
        if len(_cache) > 3000:   # searches and many symbols: keep memory bounded
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:1500]:
                _cache.pop(k, None)
        _cache[key] = (time.time(), val)
    return val


def last_price(ticker: str) -> dict | None:
    """{'price', 'currency', 'as_of', 'source'[, 'prev_close']} or None. Uses the data source chosen in
    Settings; anything it doesn't cover comes from Yahoo."""
    from . import datasources
    src = datasources.current()

    def fetch():
        if src != "yahoo":
            q = datasources.quote(ticker)
            if q:
                return q
        try:
            fi = yf.Ticker(ticker).fast_info
            p = fi["lastPrice"]
            if p is None or p != p or p <= 0:
                return _free_backup_quote(ticker, src)
            pc = fi.get("previousClose")
            from .calendars import quote_time
            qt = quote_time(ticker) if not ticker.startswith("^") and "=" not in ticker and "-USD" not in ticker else \
                {"as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"), "is_close": False}
            return {"price": float(p), "currency": fi.get("currency") or "USD", "prev_close": float(pc) if pc and pc == pc else None,
                    "as_of": qt["as_of"], "is_close": qt["is_close"],   # a closed market's price is that session's close
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": SOURCE}
        except Exception as e:  # noqa: BLE001
            log.info("price unavailable for %s: %s", ticker, type(e).__name__)
        return _free_backup_quote(ticker, src)
    return _cached(f"px:{src}:{ticker}", 60, fetch)


def _free_backup_history(ticker: str, period: str, src: str) -> dict | None:
    if src == "stooq":
        return None
    from . import datasources
    try:
        return datasources.stooq_history(ticker, PERIOD_DAYS.get(period, 64))
    except Exception:  # noqa: BLE001
        return None


def _free_backup_quote(ticker: str, src: str) -> dict | None:
    """Yahoo didn't answer: try the other free source (Stooq) for what it covers. No key, no subscription."""
    if src == "stooq":
        return None
    from . import datasources
    try:
        return datasources.stooq_quote(ticker)
    except Exception:  # noqa: BLE001
        return None


PERIOD_DAYS = {"1mo": 23, "3mo": 64, "6mo": 128, "1y": 253, "2y": 505, "5y": 1260, "max": 100000}


def history(ticker: str, period: str = "3mo") -> dict | None:
    from . import datasources
    src = datasources.current()

    def fetch():
        if src != "yahoo":
            h = datasources.history(ticker, PERIOD_DAYS.get(period, 64))
            if h:
                return h
        try:
            h = yf.Ticker(ticker).history(period=period, auto_adjust=False)
            if h is not None and not h.empty:
                h = h.dropna(subset=["Close"])   # NaN would break JSON and the charts
            if h is None or h.empty:
                return _free_backup_history(ticker, period, src)
            closes = [round(float(v), 4) for v in h["Close"].tolist()]
            dates = [d.strftime("%Y-%m-%d") for d in h.index]
            return {"ticker": ticker, "dates": dates, "closes": closes, "source": SOURCE}
        except Exception as e:  # noqa: BLE001
            log.info("history unavailable for %s: %s", ticker, type(e).__name__)
            return _free_backup_history(ticker, period, src)
    return _cached(f"hist:{src}:{ticker}:{period}", 600, fetch)


def dividends_or_none(ticker: str) -> list[tuple[str, float]] | None:
    """Cash dividends per share as (ex-date, amount) from Yahoo; [] when it pays none; None when Yahoo couldn't be
    asked (so "no data" is never mistaken for "no dividends"). Cached for a day; a failure for 10 minutes."""
    key = f"div:{ticker}"
    with _clock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < (86400 if hit[1] is not None else 600):
        return hit[1]
    try:
        d = yf.Ticker(ticker).dividends
        val = [(i.strftime("%Y-%m-%d"), float(v)) for i, v in d.items() if v == v] if d is not None else []
    except Exception as e:  # noqa: BLE001
        log.info("dividends unavailable for %s: %s", ticker, type(e).__name__)
        val = None
    with _clock:
        _cache[key] = (time.time(), val)
    return val


def dividends(ticker: str) -> list[tuple[str, float]]:
    """Like dividends_or_none, with "unavailable" treated as none (the virtual portfolio shows what it received)."""
    return dividends_or_none(ticker) or []


def sector(ticker: str) -> str | None:
    """Yahoo's sector name for a company (for the plan's sector cap), cached for a day. None when unknown."""
    def fetch():
        try:
            return (yf.Ticker(ticker).info or {}).get("sector") or None
        except Exception as e:  # noqa: BLE001
            log.info("sector unavailable for %s: %s", ticker, type(e).__name__)
            return None
    return _cached(f"sector:{ticker}", 86400, fetch)


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
    """Real screener candidates. With max_price (the owner's budget, in the screener market's currency: USD for
    the US lists, SAR for the Saudi ones), only stocks where at least one whole share fits are suggested."""
    if screener not in SCREENERS:
        raise ValueError("unknown screener")
    mkt = screener_market(screener)
    size = min(250, max(count * (8 if max_price else 3), 10))
    fallback = False
    try:
        if mkt == "sa":
            q, field, asc = _sa_query(screener)
            quotes = yf.screen(q, size=size, sortField=field, sortAsc=asc).get("quotes", [])
        else:
            quotes = yf.screen(screener, count=size).get("quotes", [])
    except Exception as e:  # noqa: BLE001
        if mkt != "sa":
            raise MarketDataUnavailable(type(e).__name__) from e
        log.info("Saudi screener unavailable (%s): using Veyro's list", type(e).__name__)
        quotes = []
    if mkt == "sa" and not quotes:
        quotes, fallback = _sa_fallback(screener), True
    out = []
    as_of = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for qt in quotes:
        sym = qt.get("symbol")
        if not sym or qt.get("quoteType") != "EQUITY":
            continue
        if (mkt == "sa") != sym.endswith(".SR") or (mkt == "us" and "." in sym):
            continue  # this market's common stock only
        px = qt.get("regularMarketPrice")
        if max_price and (px is None or px > max_price):
            continue  # can't buy even one share with this budget
        out.append({"symbol": sym, "name": qt.get("shortName") or qt.get("longName") or _alias_name(sym),
                    "price": px, "currency": qt.get("currency") or ("SAR" if mkt == "sa" else "USD"),
                    "change_pct": qt.get("regularMarketChangePercent"), "volume": qt.get("regularMarketVolume"),
                    "as_of": as_of, "source": "Veyro list (Yahoo screener unavailable)" if fallback else SOURCE})
        if len(out) >= count:
            break
    if not out:
        raise MarketDataUnavailable("empty")
    return out


def _alias_name(sym: str) -> str | None:
    return next((n for s, n, _ in ALIASES if s == sym), None)


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
            return None   # not cached: the next search tries again
    # Yahoo only understands Latin text; skip the network call for purely Arabic queries.
    if any("a" <= c <= "z" or c.isdigit() for c in q):
        key = f"search:{q}"
        with _clock:
            hit = _cache.get(key)
        found = hit[1] if hit and time.time() - hit[0] < 3600 else None
        if found is None:
            found = fetch()
            if found is not None:
                with _clock:
                    _cache[key] = (time.time(), found)
        for r in found or []:
            if r["symbol"] not in seen:
                out.append(r)
                seen.add(r["symbol"])
    return out[:limit]
