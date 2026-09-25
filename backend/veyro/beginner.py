"""Beginner mode: "I have 1000 riyals, what should I do?"

1. suggest(): picks beginner-friendly, large, well-known companies the owner can actually afford (real Yahoo
   prices), spread across sectors, ordered by the owner's comfort with risk.
2. The picks run as a normal watchlist scan: the full TradingAgents team analyses every one.
3. guide(): Leo's whole-share plan for the amount (allocation.plan) plus a plain-language lesson where each
   character shares its expertise, grounded only in the session notes. General education, not financial advice.
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from . import allocation, db, market, runner

log = logging.getLogger("veyro.beginner")

# (symbol, English name, Arabic name, sector, style). "steady" = large, mature, dividend-paying businesses;
# "growth" = large companies whose price usually moves more. Only very large, liquid, widely held names.
UNIVERSE = {
    "sa": [
        ("2280.SR", "Almarai", "المراعي", "food", "steady"),
        ("7010.SR", "stc", "الاتصالات السعودية", "telecom", "steady"),
        ("1120.SR", "Al Rajhi Bank", "مصرف الراجحي", "banks", "steady"),
        ("2222.SR", "Saudi Aramco", "أرامكو السعودية", "energy", "steady"),
        ("5110.SR", "Saudi Electricity", "الكهرباء السعودية", "utilities", "steady"),
        ("1180.SR", "Saudi National Bank", "البنك الأهلي السعودي", "banks", "steady"),
        ("2050.SR", "Savola", "صافولا", "food", "steady"),
        ("1211.SR", "Ma'aden", "معادن", "materials", "growth"),
        ("2082.SR", "ACWA Power", "أكوا باور", "utilities", "growth"),
        ("4013.SR", "Dr. Sulaiman Al Habib", "سليمان الحبيب", "health", "growth"),
        ("4190.SR", "Jarir", "جرير", "retail", "growth"),
        ("2010.SR", "SABIC", "سابك", "materials", "growth"),
        ("1150.SR", "Alinma Bank", "مصرف الإنماء", "banks", "growth"),
    ],
    "us": [
        ("KO", "Coca-Cola", "كوكاكولا", "food", "steady"),
        ("PG", "Procter & Gamble", "بروكتر آند غامبل", "household", "steady"),
        ("JNJ", "Johnson & Johnson", "جونسون آند جونسون", "health", "steady"),
        ("WMT", "Walmart", "وولمارت", "retail", "steady"),
        ("JPM", "JPMorgan Chase", "جي بي مورغان", "banks", "steady"),
        ("PEP", "PepsiCo", "بيبسيكو", "food", "steady"),
        ("MSFT", "Microsoft", "مايكروسوفت", "tech", "steady"),
        ("AAPL", "Apple", "أبل", "tech", "growth"),
        ("GOOGL", "Alphabet (Google)", "ألفابت (جوجل)", "internet", "growth"),
        ("AMZN", "Amazon", "أمازون", "retail", "growth"),
        ("NVDA", "NVIDIA", "إنفيديا", "chips", "growth"),
        ("V", "Visa", "فيزا", "payments", "growth"),
        ("META", "Meta Platforms", "ميتا", "internet", "growth"),
    ],
}


def _ordered(market_id: str, risk: str) -> list[tuple]:
    markets = ["sa", "us"] if market_id == "both" else [market_id if market_id in UNIVERSE else "sa"]
    lists = []
    for m in markets:
        steady = [x for x in UNIVERSE[m] if x[4] == "steady"]
        growth = [x for x in UNIVERSE[m] if x[4] == "growth"]
        if risk == "cautious":
            lists.append(steady + growth)
        elif risk == "bold":
            lists.append(growth + steady)
        else:  # balanced: alternate
            mixed = []
            for i in range(max(len(steady), len(growth))):
                mixed += [x for x in (steady[i] if i < len(steady) else None, growth[i] if i < len(growth) else None) if x]
            lists.append(mixed)
    out = []
    for i in range(max(len(x) for x in lists)):   # interleave markets for "both"
        out += [lst[i] for lst in lists if i < len(lst)]
    return out


def suggest(amount: float, currency: str, market_id: str, risk: str, count: int) -> dict:
    """Up to `count` affordable picks from different sectors, with real prices."""
    order = _ordered(market_id, risk)
    with ThreadPoolExecutor(max_workers=8) as ex:
        prices = dict(zip([x[0] for x in order], ex.map(market.last_price, [x[0] for x in order])))
    rates: dict[str, float | None] = {}

    def in_budget_ccy(sym: str) -> float | None:
        px = prices.get(sym)
        if not px:
            return None
        cur = px["currency"]
        if cur not in rates:
            rates[cur] = allocation.fx(currency, cur)
        return px["price"] / rates[cur] if rates[cur] else None

    picks: list[dict] = []
    # Loosen the affordability bar step by step: first "every pick gets at least one share", then "one share fits".
    for cap in (amount / max(1, count), amount * 0.6, amount):
        for sym, en, ar, sector, style in order:
            if len(picks) >= count:
                break
            if any(p["symbol"] == sym for p in picks):
                continue
            cost = in_budget_ccy(sym)
            if cost is None or cost > cap:
                continue
            if any(p["sector"] == sector for p in picks) and cap != amount:
                continue   # spread across sectors while we still have choice
            px = prices[sym]
            picks.append({"symbol": sym, "name_en": en, "name_ar": ar, "sector": sector, "style": style,
                          "price": px["price"], "currency": px["currency"], "price_in_budget": round(cost, 2)})
        if len(picks) >= count:
            break
    return {"picks": picks, "prices_available": any(prices.values()), "source": market.SOURCE}


# ---------------------------------------------------------------- the lesson
STATIC_TIPS = {
    "Leo": ("ابدأ بمبلغ ما تحتاجه في مصاريفك، وخلّ عندك احتياطي للطوارئ قبل أي استثمار.",
            "Only invest money you won't need for bills, and keep an emergency fund first."),
    "Tank": ("لا تحط كل فلوسك في سهم واحد. التنويع بين قطاعات مختلفة يخفف الضربة لو سهم نزل.",
             "Don't put everything in one stock. Spreading across sectors softens the blow if one falls."),
    "Benny": ("قبل ما تشتري، اعرف وش تسوي الشركة وكيف تكسب فلوسها. السهم جزء من شركة حقيقية.",
              "Before you buy, know what the company does and how it makes money. A share is a piece of a real business."),
    "Ollie": ("السعر يطلع وينزل كل يوم. لا تلاحق السهم بعد ما يطير، ولا تبيع من الخوف أول نزول.",
              "Prices move every day. Don't chase a stock after it jumps, and don't panic-sell on the first dip."),
    "Bruno": ("اسأل نفسك دايم: وش ممكن يغلط؟ وحدد قبل الشراء كم تتحمل خسارة.",
              "Always ask what could go wrong, and decide before buying how much loss you can stand."),
    "Pip": ("انتبه للرسوم: عمولة الوسيط تاكل من المبالغ الصغيرة، فقلّل عدد مرات البيع والشراء.",
            "Watch the fees: broker commissions eat into small amounts, so trade less often."),
}


def _profile(scan_id: str) -> dict | None:
    return db.get_setting(f"beginner:{scan_id}")


def save_profile(scan_id: str, profile: dict) -> None:
    db.set_setting(f"beginner:{scan_id}", profile)


def guide(scan_id: str, lang: str) -> dict:
    prof = _profile(scan_id)
    scan = db.get_scan(scan_id)
    if not prof or not scan:
        return {"ok": False, "code": "not_found"}
    plan = allocation.plan(scan["sessions"], prof["amount"], prof["currency"])
    tips = [{"character": c, "tip": ar if lang == "ar" else en} for c, (ar, en) in STATIC_TIPS.items()]
    base = {"profile": prof, "plan": plan, "tips": tips, "stocks": [], "intro": None, "closing": None, "generated": False}
    if scan.get("mode") == "demo" or not any(s.get("status") == "done" for s in scan["sessions"]):
        return base
    cached = db.get_setting(f"beginner_guide:{scan_id}:{lang}")
    if cached:
        return {**base, **cached, "plan": plan}
    try:
        g = _mentor(scan, prof, plan, lang)
    except Exception as e:  # noqa: BLE001
        log.info("beginner lesson failed: %s", type(e).__name__)
        return base
    db.set_setting(f"beginner_guide:{scan_id}:{lang}", g)
    return {**base, **g, "plan": plan}


def _mentor(scan: dict, prof: dict, plan: dict, lang: str) -> dict:
    from .config import CHARACTERS, STYLE
    from .secrets_store import llm_key
    from .voice import LANG_RULES, Voice, clean_line
    provider, quick, _ = runner.settings_models()
    key, _ = llm_key(provider)
    if not key and provider != "ollama":
        raise RuntimeError("no_key")
    runner.activate_key(provider, key)
    notes = []
    for s in scan["sessions"]:
        full = db.get_session(s["id"]) or {}
        pm = next((t for t in reversed(full.get("turns", [])) if t["node"] == "Portfolio Manager"), None)
        v = s.get("verdict") or {}
        notes.append(f"### {s['ticker']} — rating {s.get('rating')} (status {s.get('status')})\n"
                     f"Leo's reason: {v.get('reason', '')}\nDecision excerpt: {(pm or {}).get('detail_en', '')[:1400]}")
    rows = "\n".join(f"- {r['ticker']}: {r['shares']} shares, about {r['cost']} {plan['currency']}" for r in plan["rows"]) or "- none (keep cash)"
    chars = ", ".join(c for c in ("Leo", "Tank", "Benny", "Ollie", "Bruno", "Pip", "Buzz", "Bolt"))
    system = (
        "You are the mentor voice of a cosy pixel-art office of animal analysts (TradingAgents). A BEGINNER investor told us "
        f"their budget ({prof['amount']} {prof['currency']}), market ({prof['market']}) and comfort with risk ({prof['risk']}). "
        "The team analysed a few beginner-friendly large companies. Explain the result to a total beginner.\n"
        "Hard rules: use ONLY the session notes and the plan below for anything about these stocks; add no new facts, numbers, "
        "prices or predictions; keep every risk the notes mention; explain any finance word in simple terms; general beginner "
        "education (diversification, time horizon, fees, emergency fund, no borrowing) is allowed. Say it is not financial advice.\n"
        f"Characters and their expertise: " + "; ".join(f"{c}: {CHARACTERS[c]['role']}" for c in CHARACTERS) + "\n"
        f"Language: {LANG_RULES[lang]} Write ONLY in this language. Friendly and encouraging, short sentences.\n"
        'Return ONLY JSON: {"intro": "<2 sentences>", "stocks": [{"ticker": "<symbol>", "simple": "<1-2 sentences: what the '
        'team concluded, in beginner words>"}], "tips": [{"character": "<one of: ' + chars + '>", "tip": "<one practical tip '
        'from that character\'s expertise, tied to these results when possible>"}], "closing": "<1-2 sentences from Leo>"}\n'
        "Give 4 to 6 tips from different characters, each in that character's voice: "
        + " | ".join(f"{c}: {STYLE[c][lang]}" for c in ("Leo", "Tank", "Benny", "Ollie", "Bruno", "Pip"))
    )
    user = f"Leo's plan for the budget:\n{rows}\nCash left: {plan['cash_left']} {plan['currency']}\n\nSession notes:\n" + "\n\n".join(notes)[:20000]
    raw = Voice(provider, quick)._ask(system, user)
    m = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(m.group(0)) if m else {}
    tips = [{"character": t.get("character") if t.get("character") in CHARACTERS else "Leo", "tip": clean_line(str(t.get("tip", "")))}
            for t in data.get("tips", []) if isinstance(t, dict) and t.get("tip")]
    stocks = [{"ticker": str(x.get("ticker", "")), "simple": clean_line(str(x.get("simple", "")))}
              for x in data.get("stocks", []) if isinstance(x, dict)]
    out = {"intro": clean_line(str(data.get("intro") or "")) or None, "closing": clean_line(str(data.get("closing") or "")) or None,
           "stocks": stocks, "generated": True}
    if tips:
        out["tips"] = tips[:6]
    return out
