"""Optional Sharia-compliance (halal) screening. OFF by default; when off nothing here runs.

A rule-based estimate from free public data (Yahoo Finance through yfinance): a business-activity screen from
the company's sector/industry, and financial-ratio screens from its latest balance sheet and income statement.
Thresholds and denominators follow each methodology's published rules (sources and what could and couldn't be
verified: DECISIONS.md, "Sharia screening"). It is NOT a religious ruling (fatwa).

Three outcomes, never more: "compliant", "not_compliant" (with the failing reasons) or "unknown" (data missing,
stale, or a case an automated screen can't judge). Missing data never counts as compliant.

The screen never runs inside an analysis: results are cached per symbol with the fetch date, and the screens
that show badges ask for them separately.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from . import db

log = logging.getLogger("veyro.sharia")
SOURCE = "Yahoo Finance (yfinance)"

# ---------------------------------------------------------------- methodologies
# denominator: what the debt and cash amounts are divided by.
#   market_cap      = today's market value of the shares (AAOIFI SS 21: "market capitalisation")
#   avg_market_cap  = 36-month average market value (S&P; approximated from monthly closes x current shares)
#   total_assets    = total assets from the balance sheet (MSCI)
# strict: True = the ratio must be strictly below the limit ("<"); False = at or below ("<=", "not exceed").
METHODS: dict[str, dict] = {
    "aaoifi": {"name": {"en": "AAOIFI Shari'ah Standard No. 21", "ar": "معيار أيوفي الشرعي رقم 21"},
               "denominator": "market_cap", "debt_max": 0.30, "cash_max": 0.30, "recv_max": None, "recv_with_cash": False,
               "income_max": 0.05, "strict": False, "extra": set()},
    "sp": {"name": {"en": "S&P Shariah Indices", "ar": "مؤشرات إس آند بي الشرعية"},
           "denominator": "avg_market_cap", "debt_max": 0.33, "cash_max": 0.33, "recv_max": 0.49, "recv_with_cash": False,
           "income_max": 0.05, "strict": True, "extra": {"tobacco", "media"}},
    "msci": {"name": {"en": "MSCI Islamic Index Series", "ar": "مؤشرات MSCI الإسلامية"},
             "denominator": "total_assets", "debt_max": 0.3333, "cash_max": 0.3333, "recv_max": 0.3333, "recv_with_cash": True,
             "income_max": 0.05, "strict": True, "extra": {"tobacco", "media", "weapons", "hotels"}},
}
DEFAULT_METHOD = "aaoifi"

# ---------------------------------------------------------------- business-activity screen
# Core activities every methodology excludes, plus the extra ones some add (METHODS[..]["extra"]).
CORE = ("conventional_finance", "alcohol", "gambling", "pork", "adult")

# Yahoo industry names (normalised: lower case, dashes unified) -> excluded activity.
INDUSTRY = {
    "banks-diversified": "conventional_finance", "banks-regional": "conventional_finance",
    "mortgage finance": "conventional_finance", "capital markets": "conventional_finance",
    "financial conglomerates": "conventional_finance", "asset management": "conventional_finance",
    "insurance-life": "conventional_finance", "insurance-property & casualty": "conventional_finance",
    "insurance-diversified": "conventional_finance", "insurance-specialty": "conventional_finance",
    "insurance-reinsurance": "conventional_finance", "insurance brokers": "conventional_finance",
    "beverages-brewers": "alcohol", "beverages-wineries & distilleries": "alcohol",
    "gambling": "gambling", "resorts & casinos": "gambling",
    "tobacco": "tobacco",
    "entertainment": "media", "broadcasting": "media",
    "aerospace & defense": "weapons",
    "lodging": "hotels",
}
# Industries that mix permissible and non-permissible businesses: an automated screen can't tell (e.g. card
# networks and consumer lenders share "Credit Services"). Always "unknown", never guessed.
AMBIGUOUS = {"credit services", "financial data & stock exchanges", "shell companies"}

# Where a keyword in the business description means a human should look (e.g. a meat processor that may sell pork).
KEYWORDS = {
    "pork": (r"\bpork\b|\bswine\b|\bhog(s)?\b", {"packaged foods", "farm products", "food distribution", "restaurants",
                                                 "grocery stores", "confectioners"}),
    "alcohol": (r"\bbeer\b|\bwine(s)?\b|\bspirits\b|\bliquor\b|\balcoholic beverage", {"beverages-non-alcoholic", "restaurants",
                                                                                        "packaged foods", "food distribution"}),
    "gambling": (r"\bcasino(s)?\b|\bgambling\b|\bbetting\b|\blotter(y|ies)\b|\bwagering\b",
                 {"leisure", "lodging", "entertainment", "electronic gaming & multimedia", "internet content & information"}),
    "adult": (r"adult entertainment|pornograph", {"entertainment", "internet content & information", "broadcasting"}),
}

# Islamic banks and takaful: interest-ratio screens don't apply to a bank, and their compliance is certified by
# their own Sharia boards. The screen says so ("unknown") instead of guessing either way.
ISLAMIC_FINANCE = {"1120.SR": "Al Rajhi Bank", "1150.SR": "Alinma Bank", "1140.SR": "Bank Albilad", "1020.SR": "Bank Aljazira"}

STALE_DAYS = 548          # a balance sheet older than ~18 months is too old to judge today's ratios
CACHE_DAYS = 7            # fundamentals change quarterly; refetch weekly
FAIL_CACHE_HOURS = 1      # a failed fetch is retried after an hour


def _norm_industry(s: str | None) -> str:
    s = (s or "").strip().lower().replace("—", "-").replace("–", "-")
    return re.sub(r"\s*-\s*", "-", s)


# ---------------------------------------------------------------- settings
def settings() -> dict:
    s = db.get_setting("sharia") or {}
    m = s.get("method") if s.get("method") in METHODS else DEFAULT_METHOD
    return {"enabled": bool(s.get("enabled")), "method": m, "hide": bool(s.get("hide"))}


def save_settings(enabled: bool | None = None, method: str | None = None, hide: bool | None = None) -> dict:
    s = settings()
    if enabled is not None:
        s["enabled"] = bool(enabled)
    if method is not None:
        if method not in METHODS:
            raise ValueError("bad_method")
        s["method"] = method
    if hide is not None:
        s["hide"] = bool(hide)
    db.set_setting("sharia", s)
    return s


def enabled() -> bool:
    return settings()["enabled"]


# ---------------------------------------------------------------- the rules (pure: no network, unit-tested)
def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None   # NaN -> None


def evaluate(symbol: str, raw: dict | None, method: str = DEFAULT_METHOD, today: date | None = None) -> dict:
    """Screen one company from its raw fundamentals (see fetch_raw) under one methodology."""
    m = METHODS.get(method) or METHODS[DEFAULT_METHOD]
    today = today or datetime.now(timezone.utc).date()
    out = {"symbol": symbol, "method": method if method in METHODS else DEFAULT_METHOD, "status": "unknown",
           "reasons": [], "ratios": {}, "data_date": None, "fetched_at": (raw or {}).get("fetched_at"),
           "purification": None, "source": SOURCE}
    fail: list[dict] = []
    unknown: list[dict] = []
    if not raw or raw.get("error"):
        out["reasons"] = [{"code": "no_data"}]
        return out
    if raw.get("quote_type") and raw["quote_type"] != "EQUITY":
        out["reasons"] = [{"code": "not_equity", "value": raw["quote_type"]}]   # funds, crypto, indices: not screened
        return out

    # 1) business activity
    ind = _norm_industry(raw.get("industry"))
    excluded = set(CORE) | m["extra"]
    if symbol.upper() in ISLAMIC_FINANCE:
        unknown.append({"code": "islamic_finance"})
    elif INDUSTRY.get(ind) in excluded:
        fail.append({"code": "activity", "value": INDUSTRY[ind], "industry": raw.get("industry")})
    elif ind in AMBIGUOUS:
        unknown.append({"code": "ambiguous_industry", "industry": raw.get("industry")})
    elif not ind:
        unknown.append({"code": "missing", "field": "industry"})
    else:
        text = (raw.get("summary") or "").lower()
        for act, (pat, inds) in KEYWORDS.items():
            if act in excluded and ind in inds and re.search(pat, text):
                unknown.append({"code": "activity_review", "value": act, "industry": raw.get("industry")})

    # 2) financial ratios (a bank's balance sheet is interest-based by nature: ratios don't apply to it)
    bs_date = raw.get("bs_date")
    out["data_date"] = bs_date
    stale = False
    if bs_date:
        try:
            stale = (today - date.fromisoformat(bs_date[:10])).days > STALE_DAYS
        except ValueError:
            stale = True
    fin_ok = not any(r["code"] in ("islamic_finance",) for r in unknown) and not (fail and fail[0]["value"] == "conventional_finance")
    if fin_ok:
        if not bs_date:
            unknown.append({"code": "missing", "field": "balance_sheet"})
        elif stale:
            unknown.append({"code": "stale", "value": bs_date})
        else:
            fail, unknown = _ratios(raw, m, out, fail, unknown)

    # 3) non-permissible income (only interest income is visible in free data; other haram revenue is not)
    rev, ii = _num(raw.get("revenue")), _num(raw.get("interest_income"))
    if rev and rev > 0 and ii is not None and ii >= 0:
        share = ii / rev
        out["ratios"]["income"] = round(share, 4)
        out["purification"] = round(share, 4)
        if fin_ok and not stale and _over(share, m["income_max"], m["strict"]):
            fail.append({"code": "income_ratio", "value": round(share, 4), "limit": m["income_max"]})
    elif fin_ok:
        out["ratios"]["income"] = None   # shown as "not checked": free data doesn't report it for this company

    if fail:
        out["status"] = "not_compliant"
        out["reasons"] = fail + unknown
    elif unknown:
        out["status"] = "unknown"
        out["reasons"] = unknown
    else:
        out["status"] = "compliant"
        out["reasons"] = [] if out["ratios"].get("income") is not None else [{"code": "income_not_checked"}]
    return out


def _over(x: float, limit: float, strict: bool) -> bool:
    return x >= limit if strict else x > limit


def _ratios(raw: dict, m: dict, out: dict, fail: list, unknown: list) -> tuple[list, list]:
    fx = _num(raw.get("fx", 1.0))   # balance-sheet currency -> trading currency (market-cap denominators)
    if m["denominator"] == "total_assets":
        den, den_field, fx_used = _num(raw.get("total_assets")), "total_assets", 1.0
    elif m["denominator"] == "avg_market_cap":
        den, den_field, fx_used = _num(raw.get("avg_market_cap_36m")), "avg_market_cap_36m", fx
    else:
        den, den_field, fx_used = _num(raw.get("market_cap")), "market_cap", fx
    if den is None or den <= 0:
        unknown.append({"code": "missing", "field": den_field})
        return fail, unknown
    if fx_used is None or fx_used <= 0:
        unknown.append({"code": "currency_mismatch", "value": f"{raw.get('financial_currency')}->{raw.get('currency')}"})
        return fail, unknown
    debt, cash, recv = _num(raw.get("total_debt")), _num(raw.get("cash_st")), _num(raw.get("receivables"))
    checks = [("debt_ratio", "total_debt", debt, m["debt_max"]), ("cash_ratio", "cash_st", cash, m["cash_max"])]
    if m["recv_max"] is not None:
        rv = None if recv is None or (m["recv_with_cash"] and cash is None) else recv + (cash if m["recv_with_cash"] else 0.0)
        checks.append(("receivables_ratio", "receivables", rv, m["recv_max"]))
    for code, field, val, limit in checks:
        if val is None:
            unknown.append({"code": "missing", "field": field})
            continue
        r = max(0.0, val) * fx_used / den
        out["ratios"][code.replace("_ratio", "")] = round(r, 4)
        if _over(r, limit, m["strict"]):
            fail.append({"code": code, "value": round(r, 4), "limit": limit})
    return fail, unknown


# ---------------------------------------------------------------- free data (yfinance), cached with its date
_fetch_lock = threading.Lock()
_inflight: dict[str, threading.Event] = {}


def _row(df, *names):
    """Latest value of the first row name the statement has (Yahoo's row names vary by company)."""
    if df is None or getattr(df, "empty", True):
        return None
    for n in names:
        if n in df.index:
            for v in df.loc[n].tolist():
                f = _num(v)
                if f is not None:
                    return f
    return None


def fetch_raw(symbol: str) -> dict:
    """Everything the rules need, from Yahoo. Raises on network failure."""
    from .allocation import fx as fx_rate
    from .lazy import yf
    t = yf.Ticker(symbol)
    info = t.info or {}
    bs = t.quarterly_balance_sheet
    if bs is None or bs.empty:
        bs = t.balance_sheet
    inc = t.income_stmt
    bs_date = str(bs.columns[0])[:10] if bs is not None and not bs.empty else None
    cur, fcur = info.get("currency"), info.get("financialCurrency") or info.get("currency")
    fx = 1.0 if not cur or not fcur or cur == fcur else fx_rate(fcur, cur)
    shares = _num(info.get("sharesOutstanding"))
    avg_mcap = None
    try:
        h = t.history(period="3y", interval="1mo")
        closes = [c for c in (h["Close"].tolist() if h is not None and not h.empty else []) if c == c]
        if shares and len(closes) >= 24:
            avg_mcap = sum(closes) / len(closes) * shares   # approximation: today's share count x average price
    except Exception:  # noqa: BLE001
        avg_mcap = None
    return {
        "quote_type": info.get("quoteType"), "sector": info.get("sector"), "industry": info.get("industry"),
        "summary": (info.get("longBusinessSummary") or "")[:3000], "name": info.get("shortName") or info.get("longName"),
        "currency": cur, "financial_currency": fcur, "fx": fx,
        "market_cap": _num(info.get("marketCap")), "avg_market_cap_36m": avg_mcap, "shares": shares,
        "total_debt": _row(bs, "Total Debt"),
        "cash_st": _row(bs, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"),
        "receivables": _row(bs, "Accounts Receivable", "Receivables"),
        "total_assets": _row(bs, "Total Assets"),
        "equity": _row(bs, "Stockholders Equity", "Total Equity Gross Minority Interest"),
        "revenue": _row(inc, "Total Revenue", "Operating Revenue"),
        "interest_income": _row(inc, "Interest Income", "Interest Income Non Operating"),
        "bs_date": bs_date, "inc_date": str(inc.columns[0])[:10] if inc is not None and not inc.empty else None,
        "fetched_at": db.now(),
    }


def _cached(symbol: str) -> dict | None:
    r = db.q1("SELECT data_json, fetched_at FROM sharia_cache WHERE symbol=?", (symbol,))
    if not r:
        return None
    data = json.loads(r["data_json"])
    age = datetime.now(timezone.utc) - datetime.fromisoformat(r["fetched_at"])
    ttl = timedelta(hours=FAIL_CACHE_HOURS) if data.get("error") else timedelta(days=CACHE_DAYS)
    return data if age < ttl else None


def _store(symbol: str, data: dict) -> None:
    with db.tx() as c:
        c.execute("INSERT INTO sharia_cache(symbol,data_json,fetched_at) VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET "
                  "data_json=excluded.data_json, fetched_at=excluded.fetched_at", (symbol, json.dumps(data), db.now()))


def raw_for(symbol: str) -> dict:
    """Cached raw fundamentals, fetching once if needed (concurrent callers for one symbol share the fetch)."""
    hit = _cached(symbol)
    if hit is not None:
        return hit
    with _fetch_lock:
        ev = _inflight.get(symbol)
        owner = ev is None
        if owner:
            ev = _inflight[symbol] = threading.Event()
    if not owner:
        ev.wait(30)
        return _cached(symbol) or {"error": "unavailable", "fetched_at": db.now()}
    try:
        try:
            data = fetch_raw(symbol)
        except Exception as e:  # noqa: BLE001
            log.info("sharia data unavailable for %s: %s", symbol, type(e).__name__)
            data = {"error": "unavailable", "fetched_at": db.now()}
        _store(symbol, data)
        return data
    finally:
        with _fetch_lock:
            _inflight.pop(symbol, None)
        ev.set()


def screen(symbols: list[str], method: str | None = None) -> dict[str, dict]:
    """Results for several symbols (parallel, cached). Never called from inside an analysis."""
    method = method or settings()["method"]
    syms = list(dict.fromkeys(s.strip().upper() for s in symbols if s and s.strip()))[:80]
    with ThreadPoolExecutor(max_workers=6) as ex:
        raws = dict(zip(syms, ex.map(raw_for, syms)))
    return {s: evaluate(s, raws[s], method) for s in syms}


def disclaimer(lang: str) -> str:
    return ("تقدير آلي من بيانات مالية عامة، وليس فتوى شرعية. تحقّق من هيئة شرعية معتمدة أو قائمة رسمية قبل الاستثمار."
            if lang == "ar" else
            "An automated estimate from public financial data, not a religious ruling (fatwa). "
            "Check with a recognised Sharia board or official list before investing.")
