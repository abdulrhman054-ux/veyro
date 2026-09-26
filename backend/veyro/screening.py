"""Free screen without AI: four independent checks per stock, then a screening verdict with its reasons.

A screen, not a recommendation. It sorts stocks into "passes the screen", "watch", "exclude" and "not enough data"
so an owner can see where the risks are before spending on a full analysis. It never says "buy".

Free data only (Yahoo through yfinance, cached a week). Missing data is reported as unknown and never assumed.

1. Financial health: Altman Z''-score (Altman 1995), the version for non-manufacturers and emerging markets
      Z'' = 6.56 X1 + 3.26 X2 + 6.72 X3 + 1.05 X4
      X1 = working capital / total assets       X2 = retained earnings / total assets
      X3 = EBIT / total assets                   X4 = book equity / total liabilities
   Zones: above 2.60 safe, 1.10 to 2.60 grey, below 1.10 distress. It predicts financial distress, not returns.
   Not applicable to banks, insurers and other financial companies, or to REITs: their balance sheets are built
   differently, so the result says "not applicable" instead of a misleading number.
2. Quality of results: Piotroski F-score (Piotroski 2000), 9 yes/no tests on the last two annual reports:
      profitability: ROA > 0, operating cash flow > 0, ROA improved, cash flow > net income (earnings are cash-backed)
      balance sheet: long-term debt / assets fell, current ratio rose, no new shares issued
      efficiency:    gross margin rose, asset turnover rose
   ROA and turnover use the assets at the start of the year when Yahoo has that year, else the year-end figure.
   Each test is pass / fail / unknown; the score counts passes out of the tests that could be checked. For
   financial companies the gross-margin, current-ratio and leverage tests don't apply; their quality check is
   profitability only (ROA positive and not falling).
3. Trend and risk (price only, last year of daily closes): price vs its 200-day average and the 50-day vs the
   200-day average (trend), 12-month return skipping the last month (momentum), yearly volatility, the deepest fall
   from a peak in the year (max drawdown), and RSI(14) as a caution flag (above 70 stretched, below 30 oversold).
4. Valuation (context only, not part of the verdict): P/E against the company's own sector in its own market and
   the dividend yield actually paid (valuation.py). Cheap alone is not quality; a cheap stock can be cheap for a
   reason (a value trap), so valuation is shown next to the verdict and never decides it.

Verdict (DECISIONS 134):
   exclude    distress zone (Z'' below 1.10), or F-score 2 or lower with at least 7 tests checked, or a loss-making
              company in a downtrend
   pass       healthy (safe zone, or not applicable for a financial) and good quality (F-score 6 or more with at
              least 7 tests checked; a financial: ROA positive and not falling) and not in a downtrend
   not enough data   neither the health nor the quality check could be made
   watch      everything else (grey zone, middling quality, a downtrend in a healthy company, ...)
"""
from __future__ import annotations

import json
import logging
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from . import db, market

log = logging.getLogger("veyro.screening")

CACHE_DAYS = 7          # annual reports change once a year; a weekly refetch is plenty
FAIL_CACHE_HOURS = 1
MAX_SYMBOLS = 25
Z_SAFE, Z_DISTRESS = 2.60, 1.10
F_STRONG, F_WEAK, F_MIN_KNOWN = 6, 2, 7
DEDUPE_DAYS = 5          # the same stock with the same verdict within 5 days is logged once
HORIZONS = (20, 60)      # trading sessions after the screen: about one and three months
FINANCIAL_SECTORS = {"financial services", "financial"}
FINANCIAL_WORDS = ("bank", "insurance", "capital markets", "credit services", "asset management", "mortgage", "reit")

def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and math.isfinite(f) else None


# ---------------------------------------------------------------- free data
ROWS = {   # our name -> Yahoo's row names (they vary by company), first found wins
    "total_assets": ("Total Assets",),
    "current_assets": ("Current Assets", "Total Current Assets"),
    "current_liabilities": ("Current Liabilities", "Total Current Liabilities"),
    "total_liabilities": ("Total Liabilities Net Minority Interest", "Total Liabilities"),
    "retained_earnings": ("Retained Earnings",),
    "equity": ("Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"),
    "long_term_debt": ("Long Term Debt", "Long Term Debt And Capital Lease Obligation"),
    "shares": ("Ordinary Shares Number", "Share Issued"),
    "revenue": ("Total Revenue", "Operating Revenue"),
    "gross_profit": ("Gross Profit",),
    "ebit": ("EBIT", "Operating Income"),
    "net_income": ("Net Income From Continuing Operation Net Minority Interest", "Net Income", "Net Income Common Stockholders"),
    "cfo": ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
}


def _years(df, names) -> list[float | None]:
    """The row's values for the latest 4 years, newest first (None where Yahoo has no value)."""
    if df is None or getattr(df, "empty", True):
        return []
    for n in names:
        if n in df.index:
            return [_num(v) for v in df.loc[n].tolist()[:4]]
    return []


def fetch(symbol: str) -> dict:
    """Annual statements from Yahoo, newest year first. Raises on network failure."""
    from .lazy import yf
    t = yf.Ticker(symbol)
    info = t.info or {}
    bs, inc, cf = t.balance_sheet, t.income_stmt, t.cashflow
    src = {"total_assets": bs, "current_assets": bs, "current_liabilities": bs, "total_liabilities": bs, "retained_earnings": bs,
           "equity": bs, "long_term_debt": bs, "shares": bs, "revenue": inc, "gross_profit": inc, "ebit": inc,
           "net_income": inc, "cfo": cf}
    lines = {k: _years(src[k], names) for k, names in ROWS.items()}
    if not any(lines.values()):
        return {"error": "unavailable", "quote_type": info.get("quoteType")}
    years = [str(c)[:10] for c in list(inc.columns)[:4]] if inc is not None and not inc.empty else []
    return {"quote_type": info.get("quoteType"), "sector": info.get("sector"), "industry": info.get("industry"),
            "name": info.get("shortName") or info.get("longName"), "financial_currency": info.get("financialCurrency"),
            "years": years, "lines": lines}


_lock = threading.Lock()


def statements(symbol: str) -> dict:
    """Cached annual statements (a week; a failed fetch is retried after an hour)."""
    r = db.q1("SELECT data_json, fetched_at FROM fundamentals_cache WHERE symbol=?", (symbol,))
    if r:
        data = json.loads(r["data_json"])
        age = datetime.now(timezone.utc) - datetime.fromisoformat(r["fetched_at"])
        if age < (timedelta(hours=FAIL_CACHE_HOURS) if data.get("error") else timedelta(days=CACHE_DAYS)):
            return data
    try:
        data = fetch(symbol)
    except Exception as e:  # noqa: BLE001
        log.info("statements unavailable for %s: %s", symbol, type(e).__name__)
        data = {"error": "unavailable"}
    with db.tx() as c:
        c.execute("INSERT INTO fundamentals_cache(symbol,data_json,fetched_at) VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET "
                  "data_json=excluded.data_json, fetched_at=excluded.fetched_at", (symbol, json.dumps(data), db.now()))
    return data


# ---------------------------------------------------------------- the four checks
def is_financial(raw: dict) -> bool:
    sec, ind = (raw.get("sector") or "").lower(), (raw.get("industry") or "").lower()
    return sec in FINANCIAL_SECTORS or any(w in ind for w in FINANCIAL_WORDS)


def _v(raw: dict, key: str, i: int) -> float | None:
    xs = (raw.get("lines") or {}).get(key) or []
    return xs[i] if i < len(xs) else None


def _div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def altman(raw: dict) -> dict:
    """Altman Z'' for the latest year: zone, score and the four ratios (None when a line is missing)."""
    if raw.get("error"):
        return {"status": "unknown", "reason": "no_data"}
    if is_financial(raw):
        return {"status": "not_applicable", "reason": "financial"}
    ta = _v(raw, "total_assets", 0)
    ca, cl = _v(raw, "current_assets", 0), _v(raw, "current_liabilities", 0)
    x1 = _div(ca - cl, ta) if ca is not None and cl is not None else None
    x2 = _div(_v(raw, "retained_earnings", 0), ta)
    x3 = _div(_v(raw, "ebit", 0), ta)
    x4 = _div(_v(raw, "equity", 0), _v(raw, "total_liabilities", 0))
    ratios = {"x1": x1, "x2": x2, "x3": x3, "x4": x4}
    missing = [k for k, v in ratios.items() if v is None]
    if missing:
        return {"status": "unknown", "reason": "missing", "missing": missing, "ratios": ratios}
    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    zone = "safe" if z > Z_SAFE else "distress" if z < Z_DISTRESS else "grey"
    return {"status": zone, "z": round(z, 2), "ratios": {k: round(v, 4) for k, v in ratios.items()}, "year": (raw.get("years") or [None])[0]}


def piotroski(raw: dict) -> dict:
    """The 9 F-score tests (True / False / None = couldn't be checked) and the score over the tests checked."""
    if raw.get("error"):
        return {"status": "unknown", "reason": "no_data", "tests": {}}
    fin = is_financial(raw)
    ta0, ta1, ta2 = _v(raw, "total_assets", 0), _v(raw, "total_assets", 1), _v(raw, "total_assets", 2)
    base0 = ta1 or ta0            # assets at the start of the latest year (else its end)
    base1 = ta2 or ta1
    ni0, ni1 = _v(raw, "net_income", 0), _v(raw, "net_income", 1)
    cfo0 = _v(raw, "cfo", 0)
    roa0, roa1 = _div(ni0, base0), _div(ni1, base1)

    def cmp(a, b, better="up"):
        if a is None or b is None:
            return None
        return a > b if better == "up" else a < b

    lev0, lev1 = _div(_v(raw, "long_term_debt", 0), ta0), _div(_v(raw, "long_term_debt", 1), ta1)
    cr0, cr1 = _div(_v(raw, "current_assets", 0), _v(raw, "current_liabilities", 0)), _div(_v(raw, "current_assets", 1), _v(raw, "current_liabilities", 1))
    gm0, gm1 = _div(_v(raw, "gross_profit", 0), _v(raw, "revenue", 0)), _div(_v(raw, "gross_profit", 1), _v(raw, "revenue", 1))
    at0, at1 = _div(_v(raw, "revenue", 0), base0), _div(_v(raw, "revenue", 1), base1)
    sh0, sh1 = _v(raw, "shares", 0), _v(raw, "shares", 1)
    tests = {
        "roa_positive": None if roa0 is None else roa0 > 0,
        "cfo_positive": None if cfo0 is None else cfo0 > 0,
        "roa_up": cmp(roa0, roa1),
        "cash_backed": None if cfo0 is None or ni0 is None else cfo0 > ni0,
        "leverage_down": None if fin else (cmp(lev0, lev1, "down") if lev0 is not None and lev1 is not None else None),
        "liquidity_up": None if fin else cmp(cr0, cr1),
        "no_new_shares": None if sh0 is None or sh1 is None else sh0 <= sh1 * 1.005,   # 0.5% slack for rounding
        "margin_up": None if fin else cmp(gm0, gm1),
        "turnover_up": None if fin else cmp(at0, at1),
    }
    if fin:
        # Banks and insurers: gross margin, current ratio and leverage don't mean the same; profitability only.
        ok = tests["roa_positive"]
        up = None if roa0 is None or roa1 is None else roa0 >= roa1
        status = "unknown" if ok is None else ("good" if ok and up is not False else "weak" if ok is False else "mixed")
        return {"status": status, "financial": True, "tests": {"roa_positive": ok, "roa_not_falling": up},
                "roa": round(roa0, 4) if roa0 is not None else None, "year": (raw.get("years") or [None])[0]}
    known = [v for v in tests.values() if v is not None]
    score = sum(1 for v in known if v)
    if len(known) < F_MIN_KNOWN:
        status = "unknown" if len(known) < 5 else "incomplete"
    else:
        status = "good" if score >= F_STRONG else "weak" if score <= F_WEAK else "mixed"
    return {"status": status, "score": score, "known": len(known), "tests": tests,
            "loss_making": None if ni0 is None else ni0 < 0, "year": (raw.get("years") or [None])[0]}


def rsi(closes: list[float], n: int = 14) -> float | None:
    """Wilder's RSI over the last n sessions."""
    if len(closes) <= n:
        return None
    gains = [max(0.0, closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    losses = [max(0.0, closes[i - 1] - closes[i]) for i in range(1, len(closes))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, lo in zip(gains[n:], losses[n:]):
        ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + lo) / n
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def trend(closes: list[float]) -> dict:
    """Trend and risk from about a year of daily closes."""
    if len(closes) < 200:
        return {"status": "unknown", "reason": "short_history", "sessions": len(closes)}
    last = closes[-1]
    ma50, ma200 = sum(closes[-50:]) / 50, sum(closes[-200:]) / 200
    above, golden = last > ma200, ma50 > ma200
    status = "up" if above and golden else "down" if not above and not golden else "mixed"
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    mean = sum(rets) / len(rets)
    vol = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) * math.sqrt(252)
    peak, dd = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        dd = max(dd, 1 - c / peak)
    r = rsi(closes)
    mom = closes[-22] / closes[0] - 1 if len(closes) > 22 else None
    flags = (["stretched"] if r is not None and r > 70 else []) + (["oversold"] if r is not None and r < 30 else [])
    return {"status": status, "price_vs_ma200": round(last / ma200 - 1, 4), "ma50_over_ma200": golden,
            "momentum_12_1": round(mom, 4) if mom is not None else None, "volatility": round(vol, 4),
            "max_drawdown": round(dd, 4), "rsi": round(r, 1) if r is not None else None, "flags": flags}


def verdict(health: dict, quality: dict, tr: dict) -> tuple[str, list[dict]]:
    """The screening verdict and every reason that led to it (codes the UI words in both languages)."""
    reasons: list[dict] = []
    h, q, t = health.get("status"), quality.get("status"), tr.get("status")
    fin = health.get("reason") == "financial"
    if h == "distress":
        reasons.append({"code": "distress", "value": health.get("z")})
    if q == "weak" and not quality.get("financial"):
        reasons.append({"code": "weak_quality", "value": quality.get("score"), "known": quality.get("known")})
    if quality.get("loss_making") and t == "down":
        reasons.append({"code": "loss_and_downtrend"})
    if reasons:
        return "exclude", reasons
    if h in ("unknown", None) and q in ("unknown", None):
        return "insufficient", [{"code": "no_statements"}]
    healthy = h == "safe" or (fin and h == "not_applicable")
    good = q == "good"
    if healthy and good and t != "down":
        out = [{"code": "healthy", "value": health.get("z")} if not fin else {"code": "financial_profitable"}]
        if not quality.get("financial"):
            out.append({"code": "good_quality", "value": quality.get("score"), "known": quality.get("known")})
        if t == "unknown":
            out.append({"code": "trend_unknown"})
        return "pass", out
    # watch: say what keeps it from passing
    if h == "grey":
        reasons.append({"code": "grey_zone", "value": health.get("z")})
    if h == "unknown":
        reasons.append({"code": "health_unknown"})
    if q in ("mixed", "weak") and quality.get("financial"):
        reasons.append({"code": "financial_weak"})
    elif q == "mixed":
        reasons.append({"code": "middling_quality", "value": quality.get("score"), "known": quality.get("known")})
    elif q in ("incomplete", "unknown"):
        reasons.append({"code": "quality_incomplete", "known": quality.get("known")})
    if t == "down":
        reasons.append({"code": "downtrend"})
    return "watch", reasons or [{"code": "mixed_signals"}]


# ---------------------------------------------------------------- one stock, many stocks
def evaluate(symbol: str, raw: dict, closes: list[float], value: dict | None = None) -> dict:
    if raw.get("quote_type") and raw["quote_type"] != "EQUITY":
        return {"symbol": symbol, "verdict": "not_equity", "reasons": [{"code": "not_equity", "value": raw["quote_type"]}]}
    health, quality, tr = altman(raw), piotroski(raw), trend(closes)
    v, reasons = verdict(health, quality, tr)
    flags = tr.get("flags") or []
    return {"symbol": symbol, "name": raw.get("name"), "sector": raw.get("sector"), "industry": raw.get("industry"),
            "verdict": v, "reasons": reasons, "health": health, "quality": quality, "trend": tr, "value": value or {},
            "cautions": flags, "price": closes[-1] if closes else None, "year": (raw.get("years") or [None])[0]}


def screen(symbols: list[str], log_results: bool = True) -> dict[str, dict]:
    """Screen up to MAX_SYMBOLS stocks (statements and prices in parallel, cached)."""
    from . import valuation
    symbols = list(dict.fromkeys(symbols))[:MAX_SYMBOLS]

    def load(s):
        h = market.history(s, "1y") or {}
        return s, statements(s), h.get("closes") or []
    with ThreadPoolExecutor(max_workers=6) as ex:
        loaded = list(ex.map(load, symbols))
    closes = {s: cs for s, _, cs in loaded}
    vols = {s: (trend(cs).get("volatility") if len(cs) >= 200 else None) for s, cs in closes.items()}
    try:
        vals = valuation.score(symbols, closes, vols)
    except Exception as e:  # noqa: BLE001 - valuation is context only; the screen still works without it
        log.info("valuation skipped: %s", type(e).__name__)
        vals = {}
    out = {s: evaluate(s, raw, cs, vals.get(s)) for s, raw, cs in loaded}
    if log_results:
        _log(out)
    return out


# ---------------------------------------------------------------- track record: were the screens useful?
def _log(results: dict[str, dict]) -> None:
    from .runner import benchmark_for
    today = datetime.now(timezone.utc).date()
    for s, r in results.items():
        if r["verdict"] not in ("pass", "watch", "exclude") or not r.get("price"):
            continue
        last = db.q1("SELECT screened_on FROM screen_log WHERE ticker=? AND verdict=? ORDER BY id DESC LIMIT 1", (s, r["verdict"]))
        if last and (today - date.fromisoformat(last["screened_on"])).days < DEDUPE_DAYS:
            continue
        bench = benchmark_for(s)
        bp = (market.last_price(bench) or {}).get("price") if bench else None
        with db.tx() as c:
            c.execute("INSERT INTO screen_log(ticker,verdict,price,bench,bench_price,screened_on,created_at) VALUES(?,?,?,?,?,?,?)",
                      (s, r["verdict"], r["price"], bench, bp, today.isoformat(), db.now()))


def track(today: date | None = None) -> dict:
    """For each verdict: the stock's return minus its index at 20 and 60 sessions after the screen.
    The question it answers: did stocks that passed do better than those excluded?"""
    from .assistant import MIN_SAMPLE, add_trading_days, wilson
    today = today or datetime.now(timezone.utc).date()
    rows = db.q("SELECT * FROM screen_log ORDER BY id")
    out: dict = {"min_sample": MIN_SAMPLE, "horizons": list(HORIZONS), "by_verdict": {}}
    for v in ("pass", "watch", "exclude"):
        per = {}
        for n in HORIZONS:
            xs, waiting = [], 0
            for r in (x for x in rows if x["verdict"] == v and x["price"] and x["bench_price"]):
                end = add_trading_days(r["screened_on"], n, r["ticker"])
                if date.fromisoformat(end) >= today:
                    waiting += 1
                    continue
                p1, b1 = market.close_on_or_before(r["ticker"], end), market.close_on_or_before(r["bench"], end)
                if not p1 or not b1:
                    continue
                p1 *= market.split_factor(r["ticker"], r["screened_on"])
                xs.append((p1 / r["price"] - 1) - (b1 / r["bench_price"] - 1))
            k = sum(1 for x in xs if x > 0)
            ci = wilson(k, len(xs))
            per[str(n)] = {"n": len(xs), "waiting": waiting, "avg_excess": (sum(xs) / len(xs)) if xs else None,
                           "beat_index": (k / len(xs)) if xs else None, "ci_low": ci[0] if ci else None,
                           "ci_high": ci[1] if ci else None, "enough": len(xs) >= MIN_SAMPLE}
        out["by_verdict"][v] = {"logged": sum(1 for x in rows if x["verdict"] == v), "horizons": per}
    return out
