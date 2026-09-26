"""Value factors for the free pre-screen: P/E compared with the company's own sector, and dividend yield.

Free data only (Yahoo through yfinance). Choices made so the numbers mean what they say:
- P/E is Yahoo's trailing P/E (price / last 12 months' earnings per share). When Yahoo has no P/E but does have
  earnings per share in the trading currency, it is price / EPS from the latest close. EPS at or below zero means
  the company made a loss: it has no meaningful P/E and is ranked last with that reason, never guessed.
- Dividend yield is computed here from the cash dividends actually paid in the last 12 months / the latest close.
  Yahoo's own "dividendYield" field has been reported sometimes as a fraction and sometimes as a percent, so it
  is not used.
- "Cheap" only means something against similar companies: a bank at P/E 10 and a software company at 30 can
  both be fairly priced. Each stock is compared with the median P/E of its Yahoo sector among a reference group
  from its own market (Tadawul stocks against Tadawul, US against US): the candidates plus Veyro's list of
  large, well-known companies of that market. With fewer than 3 companies with a P/E in the sector, it is
  compared with the whole market's median instead, and says so.
"""
from __future__ import annotations

import json
import logging
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from . import db, market

log = logging.getLogger("veyro.valuation")

CACHE_HOURS = 24
FAIL_CACHE_MIN = 60
MIN_PEERS = 3
YIELD_CAP = 0.10        # a yield above 10% is usually a one-off or a data error: counted at most 10% and flagged
PE_MAX = 1000.0         # P/E above this is noise (earnings near zero)

def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and math.isfinite(f) else None


def _fetch(symbol: str) -> dict:
    from .lazy import yf
    info = yf.Ticker(symbol).info or {}
    if not info or (info.get("quoteType") is None and info.get("trailingPE") is None and info.get("sector") is None):
        return {"error": "unavailable"}
    return {"quote_type": info.get("quoteType"), "sector": info.get("sector"), "currency": info.get("currency"),
            "financial_currency": info.get("financialCurrency") or info.get("currency"),
            "trailing_pe": _num(info.get("trailingPE")), "trailing_eps": _num(info.get("trailingEps"))}


def info(symbol: str) -> dict:
    """Light, cached company facts for valuation (one Yahoo request per symbol per day)."""
    r = db.q1("SELECT data_json, fetched_at FROM valuation_cache WHERE symbol=?", (symbol,))
    if r:
        data = json.loads(r["data_json"])
        age = datetime.now(timezone.utc) - datetime.fromisoformat(r["fetched_at"])
        if age < (timedelta(minutes=FAIL_CACHE_MIN) if data.get("error") else timedelta(hours=CACHE_HOURS)):
            return data
    try:
        data = _fetch(symbol)
    except Exception as e:  # noqa: BLE001
        log.info("valuation data unavailable for %s: %s", symbol, type(e).__name__)
        data = {"error": "unavailable"}
    with db.tx() as c:
        c.execute("INSERT INTO valuation_cache(symbol,data_json,fetched_at) VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET "
                  "data_json=excluded.data_json, fetched_at=excluded.fetched_at", (symbol, json.dumps(data), db.now()))
    return data


def pe_of(inf: dict, price: float | None) -> tuple[float | None, str | None]:
    """(P/E, reason when there is none): 'loss_making', 'no_pe' or 'not_equity'."""
    if inf.get("error"):
        return None, "no_data"
    if inf.get("quote_type") and inf["quote_type"] != "EQUITY":
        return None, "not_equity"
    eps = inf.get("trailing_eps")
    if eps is not None and eps <= 0:
        return None, "loss_making"
    pe = inf.get("trailing_pe")
    if pe is None and eps and price and inf.get("currency") == inf.get("financial_currency"):
        pe = price / eps     # same currency only: EPS reported in another currency would give a wrong ratio
    if pe is None or not 0 < pe < PE_MAX:
        return None, "no_pe"
    return pe, None


def trailing_yield(symbol: str, price: float | None, today: date | None = None) -> tuple[float | None, bool]:
    """(dividends paid in the last 12 months / price, flagged-as-unusually-high). None when unknown."""
    if not price or price <= 0:
        return None, False
    divs = market.dividends_or_none(symbol)
    if divs is None:
        return None, False
    since = ((today or datetime.now(timezone.utc).date()) - timedelta(days=365)).isoformat()
    y = sum(v for d, v in divs if d > since) / price
    return y, y > YIELD_CAP


def reference_pool(mkt: str) -> list[str]:
    """Veyro's own list of large, well-known companies of one market (beginner universe + name aliases)."""
    from .beginner import UNIVERSE
    syms = [x[0] for x in UNIVERSE[mkt]]
    syms += [s for s, _, _ in market.ALIASES if ("-USD" not in s and not s.startswith("^")) and (s.endswith(".SR") == (mkt == "sa"))]
    return list(dict.fromkeys(syms))


def market_of(t: str) -> str:
    return "sa" if t.upper().endswith(".SR") else "us"


def score(tickers: list[str], closes: dict[str, list[float]], vols: dict[str, float | None], today: date | None = None) -> dict[str, dict]:
    """Value rows for the candidates: relative P/E, dividend yield and the combined score (higher = better value)."""
    markets = {market_of(t) for t in tickers}
    pool = {m: list(dict.fromkeys(reference_pool(m) + [t for t in tickers if market_of(t) == m])) for m in markets}
    every = sorted({s for p in pool.values() for s in p})
    with ThreadPoolExecutor(max_workers=8) as ex:
        infos = dict(zip(every, ex.map(info, every)))
    # sector and market medians of P/E, per market (candidates priced at their latest close; the rest at Yahoo's P/E)
    med_sector: dict[tuple[str, str], tuple[float, int]] = {}
    med_market: dict[str, tuple[float, int] | None] = {}
    for m, syms in pool.items():
        by_sec: dict[str, list[float]] = {}
        allpe = []
        for s in syms:
            pe, _ = pe_of(infos[s], (closes.get(s) or [None])[-1])
            if pe is None:
                continue
            allpe.append(pe)
            sec = infos[s].get("sector")
            if sec:
                by_sec.setdefault(sec, []).append(pe)
        for sec, v in by_sec.items():
            med_sector[(m, sec)] = (statistics.median(v), len(v))
        med_market[m] = (statistics.median(allpe), len(allpe)) if len(allpe) >= MIN_PEERS else None
    out = {}
    for t in tickers:
        m, inf = market_of(t), infos[t]
        cs = closes.get(t) or []
        price = cs[-1] if cs else None
        pe, why = pe_of(inf, price)
        y, high = trailing_yield(t, price, today)
        row = {"pe": round(pe, 2) if pe else None, "sector": inf.get("sector"), "div_yield": round(y, 4) if y is not None else None,
               "yield_unusual": high, "pe_vs": None, "peer_pe": None, "peers": None, "value_note": why}
        if pe is not None:
            sec = inf.get("sector")
            ref = med_sector.get((m, sec)) if sec else None
            if ref and ref[1] >= MIN_PEERS:
                row.update(pe_vs="sector", peer_pe=round(ref[0], 2), peers=ref[1])
            elif med_market.get(m):
                row.update(pe_vs="market", peer_pe=round(med_market[m][0], 2), peers=med_market[m][1])
            else:
                row["value_note"] = "no_peers"
        if row["peer_pe"]:
            rel = max(-1.0, min(1.0, math.log(row["peer_pe"] / pe)))   # > 0: cheaper than its peers
            vol = vols.get(t) or 0.0
            row["rel_value"] = round(rel, 4)
            row["score"] = round(rel + 5 * min(y or 0.0, YIELD_CAP) - 0.3 * vol, 4)
            if y is None:
                row["value_note"] = "no_dividend_data"   # scored on P/E alone, and says so
        else:
            row["score"] = None
        out[t] = row
    return out
