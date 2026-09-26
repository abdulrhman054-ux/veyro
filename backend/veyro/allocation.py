"""Leo's budget plan: split the owner's budget across the analysed stocks the team rated positively.

Deterministic arithmetic only (no model call): the team's own ratings and conviction set the weights, real
Yahoo prices set whole-share counts. It is an illustration to help the owner think, not financial advice.
"""
from __future__ import annotations

import math

from . import db, market

WEIGHT = {"Buy": 2.0, "Overweight": 1.0}
CONVICTION = {"high": 1.25, "medium": 1.0, "low": 0.75}
MAX_SHARE = 0.4   # no single stock gets more than 40% (with 1-2 picks the rest stays in cash)
MAX_SECTOR = 0.5  # no sector gets more than 50%
VOL_CLIP = (0.5, 2.0)
CORR_WARN = 0.8


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
    from . import sharia
    halal: dict[str, dict] = {}
    if sharia.enabled():
        # Optional Sharia screen: non-compliant and unknown stocks get no money, and the plan says why.
        halal = sharia.screen([s["ticker"] for s in sessions if s.get("rating") in WEIGHT])
    for s in sessions:
        if s.get("status") != "done" or s.get("rating") not in WEIGHT or s.get("mode") != "real":
            continue
        if halal and halal.get(s["ticker"].upper(), {}).get("status") != "compliant":
            continue
        conv = ((s.get("verdict") or {}).get("conviction")) or "unstated"
        picks.append({"ticker": s["ticker"], "rating": s["rating"], "conviction": conv, "session_id": s["id"],
                      "name": name_of(s["ticker"]), "reason": _reason(s), "w": WEIGHT[s["rating"]] * CONVICTION.get(conv, 1.0)})
    chosen = {p["session_id"] for p in picks}
    skipped = [{"ticker": s["ticker"], "rating": s.get("rating"), "session_id": s["id"], "status": s.get("status"),
                "name": name_of(s["ticker"]), "reason": _reason(s),
                **({"sharia": halal[s["ticker"].upper()]} if s["ticker"].upper() in halal else {})}
               for s in sessions if s["id"] not in chosen]
    shar = {"method": sharia.settings()["method"], "excluded": [k for k, v in halal.items() if v["status"] != "compliant"]} \
        if halal else None
    if not picks:
        return {"amount": amount, "currency": currency, "rows": [], "cash_left": round(amount, 2), "skipped": skipped,
                "notes": ["no_positive"] + (["sharia_none"] if shar and shar["excluded"] else []), "sharia": shar}
    # Risk-aware weights: the team's call and conviction, scaled by inverse volatility (a calmer stock gets more,
    # a wilder one less, clipped to x0.5..x2 so the team's view still leads). No history = no adjustment.
    vols = {p["ticker"]: _vol(p["ticker"]) for p in picks}
    known = sorted(v for v in vols.values() if v)
    mid = known[len(known) // 2] if known else None
    for p in picks:
        v = vols[p["ticker"]]
        p["risk_adj"] = round(min(VOL_CLIP[1], max(VOL_CLIP[0], mid / v)), 3) if v and mid else 1.0
        p["vol"] = round(v, 4) if v else None
        p["w"] *= p["risk_adj"]
        p["sector"] = sector_of(p["ticker"])
    shares = _capped([p["w"] for p in picks], [p["sector"] for p in picks])
    fee_cfg = fees()
    rows, spent = [], 0.0
    for p, share in zip(picks, shares):
        px = market.last_price(p["ticker"])
        if not px:
            rows.append({**p, "target": round(amount * share, 2), "price": None, "shares": 0, "cost": 0.0, "fee": 0.0, "note": "no_price"})
            continue
        rate = fx(currency, px["currency"])   # budget currency -> stock currency
        if not rate:
            rows.append({**p, "target": round(amount * share, 2), "price": px["price"], "price_currency": px["currency"],
                         "shares": 0, "cost": 0.0, "fee": 0.0, "note": "no_fx"})
            continue
        target = amount * share
        pb = px["price"] / rate
        fee_of = _fee_fn(fee_cfg.get(market_of(p["ticker"])) or {}, rate)
        n = math.floor(target / pb)
        while n > 0 and n * pb + fee_of(n * pb) > target + 1e-9:
            n -= 1
        cost = n * pb + (fee_of(n * pb) if n else 0.0)
        spent += cost
        rows.append({**p, "target": round(target, 2), "price": px["price"], "price_currency": px["currency"],
                     "shares": n, "cost": round(cost, 2), "fee": round(fee_of(n * pb) if n else 0.0, 2),
                     "note": "too_small" if n == 0 else None, "_pb": pb, "_fee": fee_of})
    # Leftover cash: with 3+ picks, first give one whole share to positive picks that got none (weightiest first,
    # even if that one share is above 40% of a small amount, so the money isn't all idle), then top up the picks
    # furthest below their share, never beyond 1.5x their target, the 40% name cap or the 50% sector cap.
    # With 1-2 picks the rest simply stays in cash: one or two stocks are not a diversified portfolio.
    cash = amount - spent
    ceiling = MAX_SHARE * amount
    live = [r for r in rows if r.get("_pb")]

    def sector_total(sec):
        return sum(r["cost"] for r in live if sec and r["sector"] == sec)

    def add_cost(r):
        return (r["shares"] + 1) * r["_pb"] + r["_fee"]((r["shares"] + 1) * r["_pb"]) - r["cost"]

    while True:
        fit = [r for r in live if add_cost(r) <= cash + 1e-9]
        zero = sorted((r for r in fit if r["shares"] == 0 and len(picks) >= 3), key=lambda r: -r["w"])
        under = sorted((r for r in fit if r["shares"] > 0 and r["cost"] + add_cost(r) <= min(r["target"] * 1.5, ceiling) + 1e-9
                        and (not r["sector"] or sector_total(r["sector"]) + add_cost(r) <= MAX_SECTOR * amount + 1e-9)),
                       key=lambda r: -(r["target"] - r["cost"]))
        pick = zero[0] if zero else under[0] if under else None
        if not pick:
            break
        extra = add_cost(pick)
        pick["shares"] += 1
        pick["fee"] = round(pick["_fee"](pick["shares"] * pick["_pb"]), 2)
        pick["cost"] = round(pick["cost"] + extra, 2)
        pick["note"] = "one_share_over_cap" if pick["cost"] > ceiling + 0.01 else None
        cash -= extra
    spent = amount - cash
    for r in rows:
        r.pop("w", None)
        r.pop("_pb", None)
        r.pop("_fee", None)
    if any(r["note"] == "too_small" for r in rows):
        notes.append("too_small")
    if any(r["note"] == "one_share_over_cap" for r in rows):
        notes.append("one_share_over_cap")
    if len(picks) < 3:
        notes.append("few_picks")    # 40% cap per stock: the rest stays in cash
    # Any market in the plan without the owner's fees: say so (fees for one market don't cover the other's rows).
    missing = sorted({market_of(r["ticker"]) for r in rows if not (fee_cfg.get(market_of(r["ticker"])) or {}).get("set")})
    if missing:
        notes.append("fees_not_set")
    return {"amount": amount, "currency": currency, "rows": rows, "fees_missing": missing, "cash_left": round(amount - spent, 2),
            "skipped": skipped, "notes": notes, "source": market.SOURCE, "sharia": shar,
            "caps": {"name": MAX_SHARE, "sector": MAX_SECTOR}, "correlated": _correlated([r["ticker"] for r in rows if r["shares"] > 0]),
            "fees_total": round(sum(r.get("fee") or 0 for r in rows), 2)}


# ---------------------------------------------------------------- risk inputs (free price history)
def _returns(t: str) -> dict[str, float]:
    h = market.history(t, "6mo") or {}
    d, c = h.get("dates") or [], h.get("closes") or []
    return {d[i]: c[i] / c[i - 1] - 1 for i in range(1, len(c)) if c[i - 1]}


def _vol(t: str) -> float | None:
    """Annualised volatility of daily returns over ~6 months."""
    r = list(_returns(t).values())[-126:]
    if len(r) < 30:
        return None
    m = sum(r) / len(r)
    v = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)
    return v or None


def _correlated(tickers: list[str], limit: float = CORR_WARN) -> list[dict]:
    """Pairs whose last 60 daily returns moved together (correlation above the limit): less diversified than it looks."""
    rets = {t: _returns(t) for t in tickers}
    out = []
    for i, a in enumerate(tickers):
        for b in tickers[i + 1:]:
            days = sorted(set(rets[a]) & set(rets[b]))[-60:]
            if len(days) < 30:
                continue
            x, y = [rets[a][d] for d in days], [rets[b][d] for d in days]
            mx, my = sum(x) / len(x), sum(y) / len(y)
            sx = math.sqrt(sum((v - mx) ** 2 for v in x))
            sy = math.sqrt(sum((v - my) ** 2 for v in y))
            if sx and sy:
                c = sum((x[k] - mx) * (y[k] - my) for k in range(len(x))) / (sx * sy)
                if c > limit:
                    out.append({"a": a, "b": b, "corr": round(c, 2)})
    return out


def _capped(weights: list[float], sectors: list[str | None]) -> list[float]:
    """Shares of the amount: proportional to the weights, at most MAX_SHARE per stock and MAX_SECTOR per sector.
    Excess goes to stocks with room; what nobody can take stays in cash (so the shares may sum to less than 1)."""
    total = sum(weights) or 1
    sh = [w / total for w in weights]
    for _ in range(20):
        excess = 0.0
        for i, x in enumerate(sh):
            if x > MAX_SHARE:
                excess += x - MAX_SHARE
                sh[i] = MAX_SHARE
        for sec in {s for s in sectors if s}:
            idx = [i for i, s in enumerate(sectors) if s == sec]
            tot = sum(sh[i] for i in idx)
            if tot > MAX_SECTOR + 1e-12:
                f = MAX_SECTOR / tot
                for i in idx:
                    excess += sh[i] * (1 - f)
                    sh[i] *= f
        if excess < 1e-9:
            break
        def room(i):
            r = MAX_SHARE - sh[i]
            if sectors[i]:
                r = min(r, MAX_SECTOR - sum(sh[j] for j, s in enumerate(sectors) if s == sectors[i]))
            return max(0.0, r)
        open_ = [i for i in range(len(sh)) if room(i) > 1e-9]
        if not open_:
            break   # nobody can take more: the rest stays in cash
        ws = sum(weights[i] for i in open_) or 1
        for i in open_:
            sh[i] += min(room(i), excess * weights[i] / ws)
    return sh


# ---------------------------------------------------------------- sector and fees
def sector_of(t: str) -> str | None:
    from .beginner import UNIVERSE, ETFS
    for rows in list(UNIVERSE.values()) + list(ETFS.values()):
        for s, _en, _ar, sector, *_ in rows:
            if s == t:
                return sector
    return market.sector(t)


def market_of(t: str) -> str:
    return "sa" if t.upper().endswith(".SR") else "us"


FEE_DEFAULT = {"rate": 0.0, "min": 0.0, "vat": 0.0, "set": False}


def fees() -> dict:
    """The owner's broker fees per market (Settings). Not guessed: until entered, they are 0 and the plan says so."""
    saved = db.get_setting("broker_fees") or {}
    return {m: {**FEE_DEFAULT, **(saved.get(m) or {})} for m in ("sa", "us")}


def save_fees(m: str, rate: float, minimum: float, vat: float) -> dict:
    if m not in ("sa", "us") or not (0 <= rate <= 0.05) or not (0 <= minimum <= 1000) or not (0 <= vat <= 0.5):
        raise ValueError("bad_fees")
    saved = db.get_setting("broker_fees") or {}
    saved[m] = {"rate": float(rate), "min": float(minimum), "vat": float(vat), "set": True}
    db.set_setting("broker_fees", saved)
    return fees()


def _fee_fn(cfg: dict, rate_fx: float):
    """Fee in the budget currency for a trade worth `value` (budget currency). The minimum is in the stock's currency."""
    r, mn, vat = float(cfg.get("rate") or 0), float(cfg.get("min") or 0), float(cfg.get("vat") or 0)
    if not r and not mn:
        return lambda value: 0.0
    return lambda value: (max(mn / rate_fx, r * value) * (1 + vat)) if value > 0 else 0.0
