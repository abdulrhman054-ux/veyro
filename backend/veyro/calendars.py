"""Trading calendars for the two markets Veyro covers: Tadawul (XSAU) and the US (XNYS).

Holidays come from the free `exchange_calendars` package (Apache-2.0), loaded on first use. Tadawul's Eid holidays
follow the Hijri calendar and are announced by the exchange each year, so the package's dates for them are
estimates. Outside the package's range, or if it can't load, regular hours and weekdays are used and holidays
are not known (the callers say so where it matters).
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

log = logging.getLogger("veyro.calendars")

MARKETS = {
    "sa": {"code": "XSAU", "tz": "Asia/Riyadh", "days": (6, 0, 1, 2, 3), "open": (10, 0), "close": (15, 0)},
    "us": {"code": "XNYS", "tz": "America/New_York", "days": (0, 1, 2, 3, 4), "open": (9, 30), "close": (16, 0)},
}
_cals: dict[str, object | None] = {}
_lock = threading.Lock()


def market_of(ticker: str | None) -> str:
    return "sa" if (ticker or "").upper().endswith(".SR") else "us"


def _cal(m: str):
    with _lock:
        if m not in _cals:
            try:
                import exchange_calendars as xc
                _cals[m] = xc.get_calendar(MARKETS[m]["code"])
            except Exception as e:  # noqa: BLE001
                log.info("calendar %s unavailable: %s", m, type(e).__name__)
                _cals[m] = None
        return _cals[m]


def local_today(m: str, now: datetime | None = None) -> str:
    """Today's date where the market is (a Saudi stock on Sunday morning is Sunday's session, not New York's Saturday)."""
    now = now or datetime.now(timezone.utc)
    return now.astimezone(ZoneInfo(MARKETS[m]["tz"])).date().isoformat()


def is_session(m: str, d: date) -> bool:
    """A trading day (weekends and, where known, holidays excluded)."""
    c = _cal(m)
    if c is not None:
        try:
            if c.first_session.date() <= d <= c.last_session.date():
                return bool(c.is_session(d.isoformat()))
        except Exception:  # noqa: BLE001
            pass
    return d.weekday() in MARKETS[m]["days"]


def is_open(m: str, now: datetime | None = None) -> dict:
    """Open right now? {'open', 'holidays_known'}; regular session only (no auctions or extended hours)."""
    info = MARKETS[m]
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(info["tz"]))
    in_hours = info["open"] <= (now.hour, now.minute) < info["close"]
    c = _cal(m)
    known = c is not None and c.first_session.date() <= now.date() <= c.last_session.date()
    return {"open": in_hours and is_session(m, now.date()), "holidays_known": bool(known)}


def add_sessions(start: str, n: int, m: str) -> str:
    """The date n trading sessions after `start` in market m."""
    d = date.fromisoformat(start[:10])
    guard = 0
    while n > 0 and guard < 400:
        d += timedelta(days=1)
        guard += 1
        if is_session(m, d):
            n -= 1
    return d.isoformat()


def last_session(m: str, now: datetime | None = None) -> str:
    """The most recent trading day on or before today in market m (today itself only once its session has opened)."""
    info = MARKETS[m]
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(info["tz"]))
    d = now.date()
    if (now.hour, now.minute) < info["open"] or not is_session(m, d):
        d -= timedelta(days=1)
        while not is_session(m, d):
            d -= timedelta(days=1)
    return d.isoformat()


def quote_time(ticker: str, now: datetime | None = None) -> dict:
    """What a quote fetched now really is: live while the market is open, otherwise the last session's close."""
    m = market_of(ticker)
    now = now or datetime.now(timezone.utc)
    if is_open(m, now)["open"]:
        return {"as_of": now.isoformat(timespec="seconds"), "is_close": False}
    return {"as_of": last_session(m, now), "is_close": True}
