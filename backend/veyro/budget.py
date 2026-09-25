"""Monthly spending cap for analyses (optional). Counts what real sessions actually cost this month
(Claude list prices; providers without a known price aren't counted, and the UI says so)."""
from __future__ import annotations

from datetime import datetime

from . import db


def cap() -> float | None:
    v = db.get_setting("monthly_cap_usd")
    try:
        v = float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return v if v and v > 0 else None


def month_key() -> str:
    return datetime.now().strftime("%Y-%m")


def spent() -> dict:
    m = month_key()
    rows = db.q("SELECT cost_usd, provider FROM sessions WHERE mode='real' AND substr(created_at,1,7)=?", (m,))
    known = sum(r["cost_usd"] or 0 for r in rows)
    unpriced = sum(1 for r in rows if r["cost_usd"] is None)
    return {"month": m, "spent": round(known, 4), "sessions": len(rows), "unpriced_sessions": unpriced, "cap": cap()}


def blocked() -> bool:
    c = cap()
    return bool(c) and spent()["spent"] >= c
