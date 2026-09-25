"""Leo's budget plan: split the owner's budget across the analysed stocks the team rated positively.

Deterministic arithmetic only (no model call): the team's own ratings and conviction set the weights, real
Yahoo prices set whole-share counts. It is an illustration to help the owner think, not financial advice.
"""
from __future__ import annotations

import math

from . import market

WEIGHT = {"Buy": 2.0, "Overweight": 1.0}
CONVICTION = {"high": 1.25, "medium": 1.0, "low": 0.75}
MAX_SHARE = 0.4   # no single stock gets more than 40% when there are three or more picks


def fx(src: str, dst: str) -> float | None:
    """Units of dst per 1 src, from Yahoo (e.g. USDSAR=X)."""
    if src == dst:
        return 1.0
    px = market.last_price(f"{src}{dst}=X")
    return px["price"] if px else None


def name_of(sym: str) -> dict:
    """Company name in both languages when we know it (beginner universe or the Arabic alias list)."""
    from .beginner import UNIVERSE
    for rows in UNIVERSE.values():
        for s, en, ar, *_ in rows:
            if s == sym:
                return {"en": en, "ar": ar}
    for s, en, keys in market.ALIASES:
        if s == sym:
            ar = next((k for k in keys if any("\u0600" <= ch <= "\u06ff" for ch in k)), en)
            return {"en": en, "ar": ar}
    return {"en": sym, "ar": sym}


def _reason(s: dict) -> dict:
    v = s.get("verdict") or {}
    texts = v.get("texts") or {}
    return {lg: (texts.get(lg) or {}).get("reason") for lg in ("ar", "en")} | ({v.get("lang"): v.get("reason")} if v.get("lang") else {})


def plan(sessions: list[dict], amount: float, currency: str = "USD") -> dict:
    notes: list[str] = []
    picks = []
    for s in sessions:
        if s.get("status") != "done" or s.get("rating") not in WEIGHT or s.get("mode") != "real":
            continue
        conv = ((s.get("verdict") or {}).get("conviction")) or "unstated"
        picks.append({"ticker": s["ticker"], "rating": s["rating"], "conviction": conv, "session_id": s["id"],
                      "name": name_of(s["ticker"]), "reason": _reason(s), "w": WEIGHT[s["rating"]] * CONVICTION.get(conv, 1.0)})
    chosen = {p["session_id"] for p in picks}
    skipped = [{"ticker": s["ticker"], "rating": s.get("rating"), "session_id": s["id"], "status": s.get("status"),
                "name": name_of(s["ticker"]), "reason": _reason(s)} for s in sessions if s["id"] not in chosen]
    if not picks:
        return {"amount": amount, "currency": currency, "rows": [], "cash_left": round(amount, 2), "skipped": skipped,
                "notes": ["no_positive"]}
    total = sum(p["w"] for p in picks)
    shares = [p["w"] / total for p in picks]
    if len(picks) >= 3:   # cap concentration, spread the excess over the others
        for _ in range(5):
            over = [i for i, x in enumerate(shares) if x > MAX_SHARE + 1e-9]
            if not over:
                break
            extra = sum(shares[i] - MAX_SHARE for i in over)
            for i in over:
                shares[i] = MAX_SHARE
            room = [i for i, x in enumerate(shares) if x < MAX_SHARE]
            rs = sum(shares[i] for i in room) or 1
            for i in room:
                shares[i] += extra * shares[i] / rs
    rows, spent = [], 0.0
    for p, share in zip(picks, shares):
        px = market.last_price(p["ticker"])
        if not px:
            rows.append({**p, "target": round(amount * share, 2), "price": None, "shares": 0, "cost": 0.0, "note": "no_price"})
            continue
        rate = fx(currency, px["currency"])   # budget currency -> stock currency
        if not rate:
            rows.append({**p, "target": round(amount * share, 2), "price": px["price"], "price_currency": px["currency"],
                         "shares": 0, "cost": 0.0, "note": "no_fx"})
            continue
        target = amount * share
        n = math.floor(target * rate / px["price"])
        cost = n * px["price"] / rate
        spent += cost
        rows.append({**p, "target": round(target, 2), "price": px["price"], "price_currency": px["currency"],
                     "shares": n, "cost": round(cost, 2), "note": "too_small" if n == 0 else None, "_pb": px["price"] / rate})
    # Leftover cash: first give a whole share to positive picks that got none (weightiest first), then top up
    # the picks furthest below their share, never beyond 1.5x their target, so small budgets still get spread.
    # A top-up never takes a stock past the 40% cap (only a single first share may exceed it on a small amount).
    cash = amount - spent
    ceiling = MAX_SHARE * amount if len(picks) >= 3 else float("inf")
    live = [r for r in rows if r.get("_pb")]
    while True:
        fit = [r for r in live if r["_pb"] <= cash + 1e-9]
        zero = sorted((r for r in fit if r["shares"] == 0), key=lambda r: -r["w"])
        under = sorted((r for r in fit if r["shares"] > 0 and r["cost"] + r["_pb"] <= min(r["target"] * 1.5, ceiling) + 1e-9),
                       key=lambda r: -(r["target"] - r["cost"]))
        pick = zero[0] if zero else under[0] if under else None
        if not pick:
            break
        pick["shares"] += 1
        pick["cost"] = round(pick["cost"] + pick["_pb"], 2)
        pick["note"] = None
        cash -= pick["_pb"]
    spent = amount - cash
    for r in rows:
        r.pop("w", None)
        r.pop("_pb", None)
    if any(r["note"] == "too_small" for r in rows):
        notes.append("too_small")
    return {"amount": amount, "currency": currency, "rows": rows, "cash_left": round(amount - spent, 2),
            "skipped": skipped, "notes": notes, "source": market.SOURCE}
