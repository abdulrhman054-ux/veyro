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
            used = float(r["cost_usd"])
        else:
            try:
                used = float((json.loads(r["usage_json"] or "{}") or {}).get("cost_partial") or 0)
            except (TypeError, ValueError):
                used = 0.0
            if r["status"] != "running":
                unpriced += 1
        known += used
        if r["status"] == "running":   # usage is written as it arrives: hold the rest of the run's high estimate
            reserved += max(0.0, _session_high(r["provider"], r["quick_model"], r["deep_model"]) - used)
    ex = [x for x in (db.get_setting("spend_extra") or []) if x.get("month") == m]
    extra = sum(float(x.get("usd") or 0) for x in ex)
    return {"month": m, "spent": round(known + extra, 4), "reserved": round(reserved, 4), "sessions": len(rows),
            "unpriced_sessions": unpriced, "cap": cap(), "other_usd": round(extra, 4),
            "other_calls": sum(int(x.get("calls") or 0) for x in ex), "unpriced_calls": sum(int(x.get("unpriced") or 0) for x in ex)}


def _session_high(provider, quick, deep) -> float:
    from .runner import estimate
    try:
        return float(estimate(provider or "", quick or "", deep or "")["high"] or 0)
    except Exception:  # noqa: BLE001
        return 0.0


_ledger_lock = __import__("threading").Lock()


def record_extra(usd: float | None, what: str) -> None:
    """Spend outside a session (translations, Albie, Ask the team, the beginner lesson, connection tests, backtests),
    added up per month and kind. usd=None means the model has no known price: the call is counted as unpriced."""
    with _ledger_lock:
        m = month_key()
        rows = [x for x in (db.get_setting("spend_extra") or []) if x.get("month", "") >= f"{int(m[:4]) - 1}{m[4:]}"]
        row = next((x for x in rows if x.get("month") == m and x.get("what") == what), None)
        if row is None:
            row = {"month": m, "what": what, "usd": 0.0, "calls": 0, "unpriced": 0}
            rows.append(row)
        row["calls"] = row.get("calls", 0) + 1
        if usd is None:
            row["unpriced"] = row.get("unpriced", 0) + 1
        else:
            row["usd"] = round(float(row.get("usd") or 0) + float(usd), 6)
        db.set_setting("spend_extra", rows)


def reserve_extra(usd: float, what: str) -> None:
    """Record spend Veyro can't measure token by token (the framework's backtest) at its high estimate."""
    record_extra(usd, what)


class CapReached(Exception):
    """This month's cap is reached: no new paid call starts."""


def ledger_tracker(what: str):
    """A usage callback for one-off calls: each model reply's cost goes into this month's ledger as it arrives."""
    from .runner import UsageTracker, price_for

    class Ledger(UsageTracker):
        def on_llm_end(self, response, **kwargs):  # noqa: ANN001
            for gens in response.generations:
                for g in gens:
                    msg = getattr(g, "message", None)
                    um = getattr(msg, "usage_metadata", None) or {}
                    meta = getattr(msg, "response_metadata", None) or {}
                    p = price_for(meta.get("model_name") or meta.get("model"))
                    i, o = int(um.get("input_tokens", 0) or 0), int(um.get("output_tokens", 0) or 0)
                    record_extra((i * p[0] + o * p[1]) / 1_000_000 if p else None, what)
            super().on_llm_end(response, **kwargs)
    return Ledger()


def next_run_high() -> float:
    """The high estimate of one more analysis with the current models (0 when their price isn't known)."""
    from .runner import settings_models
    return _session_high(*settings_models())


def blocked(upcoming: float = 0.0) -> bool:
    """True when this month's cap is reached, or when `upcoming` (a run about to start) would go past it."""
    c = cap()
    if not c:
        return False
    s = spent()
    used = s["spent"] + s["reserved"]
    return used + upcoming > c if upcoming > 0 else used >= c
