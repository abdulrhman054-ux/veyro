"""Monthly spending cap for analyses (optional). Counts what real sessions actually cost this month
(Claude list prices; providers without a known price aren't counted, and the UI says so)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import db


def cap() -> float | None:
    v = db.get_setting("monthly_cap_usd")
    try:
        v = float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return v if v and v > 0 else None


def month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")   # created_at is stored in UTC


def spent() -> dict:
    """This month's recorded cost. A session with an unpriced model counts its priced part; stopped and failed
    sessions count what they used; spend that can't be measured (the framework's backtest) counts its reserved
    high estimate. Sessions still running are reserved at their high estimate, so starting several at once
    can't slip past the cap."""
    m = month_key()
    rows = db.q("SELECT cost_usd, usage_json, status, provider, quick_model, deep_model FROM sessions "
                "WHERE mode='real' AND substr(created_at,1,7)=?", (m,))
    known, unpriced, reserved = 0.0, 0, 0.0
    for r in rows:
        if r["cost_usd"] is not None:
            known += r["cost_usd"]
        else:
            try:
                known += float((json.loads(r["usage_json"] or "{}") or {}).get("cost_partial") or 0)
            except (TypeError, ValueError):
                pass
            if r["status"] != "running":
                unpriced += 1
        if r["status"] == "running" and not r["usage_json"]:
            reserved += _session_high(r["provider"], r["quick_model"], r["deep_model"])
    extra = sum(float(x.get("usd") or 0) for x in (db.get_setting("spend_extra") or []) if x.get("month") == m)
    return {"month": m, "spent": round(known + extra, 4), "reserved": round(reserved, 4), "sessions": len(rows),
            "unpriced_sessions": unpriced, "cap": cap()}


def _session_high(provider, quick, deep) -> float:
    from .runner import estimate
    try:
        return float(estimate(provider or "", quick or "", deep or "")["high"] or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def reserve_extra(usd: float, what: str) -> None:
    """Record spend Veyro can't measure token by token (the framework's backtest) at its high estimate."""
    rows = [x for x in (db.get_setting("spend_extra") or []) if x.get("month", "") >= month_key()[:4]]
    rows.append({"month": month_key(), "usd": round(float(usd), 4), "what": what, "at": db.now()})
    db.set_setting("spend_extra", rows)


def blocked() -> bool:
    c = cap()
    if not c:
        return False
    s = spent()
    return s["spent"] + s["reserved"] >= c
