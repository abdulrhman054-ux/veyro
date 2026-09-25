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


# The simplest option for a beginner: a broad index fund (ETF). Shown next to the single-stock picks, needs no paid
# analysis. Symbols checked 2026-09-25: 9412 = Albilad MSCI Saudi Equity ETF (saudiexchange.sa ETF profile; the issuer
# states it follows its Sharia committee's standards), SPYM = State Street SPDR Portfolio S&P 500 ETF (renamed from
# SPLG on 31 Oct 2025, ssga.com / OCC memo 57498), VT = Vanguard Total World Stock ETF.
# (symbol, English name, Arabic name, sector, what it holds, issuer says Sharia-compliant)
ETFS = {
    "sa": [("9412.SR", "Albilad MSCI Saudi Equity ETF", "صندوق البلاد إم إس سي آي للأسهم السعودية", "index",
            {"en": "Hundreds of Sharia-compliant Saudi companies of every size, in one unit.",
             "ar": "مئات الشركات السعودية المتوافقة مع الشريعة بكل الأحجام، في وحدة وحدة."}, True)],
    "us": [("SPYM", "SPDR Portfolio S&P 500 ETF", "صندوق إس بي دي آر للمؤشر S&P 500", "index",
            {"en": "The 500 largest US companies in one low-cost unit.", "ar": "أكبر 500 شركة أمريكية في وحدة وحدة منخفضة التكلفة."}, False),
           ("VT", "Vanguard Total World Stock ETF", "صندوق فانغارد لأسهم العالم", "index",
            {"en": "Thousands of companies across the whole world in one unit.", "ar": "آلاف الشركات من كل العالم في وحدة وحدة."}, False)],
}


def index_funds(amount: float, currency: str, market_id: str) -> list[dict]:
    """The market's broad index fund(s) with real prices and how many whole units the amount buys. Free: no model."""
    from . import sharia
    out = []
    halal_on = sharia.enabled()
    for m in (["sa", "us"] if market_id == "both" else [market_id]):
        for sym, en, ar, _sector, what, issuer_sharia in ETFS.get(m, []):
            if halal_on and not issuer_sharia:
                continue   # the screen can't check a fund's holdings; only funds whose issuer states compliance are shown
            px = market.last_price(sym)
            rate = allocation.fx(currency, px["currency"]) if px else None
            unit = px["price"] / rate if px and rate else None
            n = int(amount // unit) if unit else 0
            out.append({"symbol": sym, "name_en": en, "name_ar": ar, "what": what, "issuer_sharia": issuer_sharia,
                        "price": px["price"] if px else None, "currency": px["currency"] if px else None,
                        "units": n, "cost": round(n * unit, 2) if unit else None})
    return out


# What a beginner needs to know about the market they chose. Regular hours only (holidays not included).
MARKETS = {
    "sa": {"name": {"ar": "السوق السعودي (تداول)", "en": "Saudi market (Tadawul)"}, "currency": "SAR", "tz": "Asia/Riyadh",
           "days": (6, 0, 1, 2, 3), "open": (10, 0), "close": (15, 0), "benchmark": "^TASI.SR",
           "hours": {"ar": "الأحد إلى الخميس، 10:00 الصبح إلى 3:00 العصر بتوقيت السعودية",
                     "en": "Sunday to Thursday, 10:00 to 15:00 Saudi time"},
           "tips": [
               ("Pip", "تحتاج محفظة استثمارية عند وسيط مرخّص من هيئة السوق المالية، وتقدر تفتحها من تطبيق بنكك غالباً.",
                "You need an investment account with a broker licensed by the Capital Market Authority; most Saudi banks' apps offer one."),
               ("Tank", "التداول من الأحد للخميس. الأوامر اللي تحطها بعد الإغلاق تتنفذ بجلسة اليوم الجاي.",
                "Trading runs Sunday to Thursday; orders placed after the close wait for the next session."),
               ("Benny", "أسعار تداول بالريال، فما فيه تحويل عملة ولا رسومه. انتبه لعمولة الوسيط على كل صفقة.",
                "Prices are in riyals, so no currency conversion or its fees; mind the broker's commission on each trade."),
               ("Ollie", "نقارن أداء الأسهم بمؤشر تاسي (السوق كله)، عشان تعرف هل السهم أحسن من السوق أو لا.",
                "We compare each stock with TASI (the whole market) to see whether it beat the market."),
               ("Tank", "سعر السهم في تداول ما يتحرك في اليوم أكثر من 10٪ فوق أو تحت إغلاق أمس (حد التذبذب اليومي).",
                "On Tadawul a share can't move more than 10% above or below yesterday's close in one day (the daily price limit)."),
               ("Benny", "الصفقة تتسوّى بعد يومي عمل (T+2): الأسهم والفلوس تنتقل رسمياً بعد يومين من التنفيذ.",
                "Trades settle two business days later (T+2): shares and cash formally change hands two days after the trade."),
           ]},
    "us": {"name": {"ar": "السوق الأمريكي", "en": "US market"}, "currency": "USD", "tz": "America/New_York",
           "days": (0, 1, 2, 3, 4), "open": (9, 30), "close": (16, 0), "benchmark": "SPY",
           "hours": {"ar": "الاثنين إلى الجمعة، من العصر إلى الليل بتوقيت السعودية (9:30 إلى 4:00 بتوقيت نيويورك)",
                     "en": "Monday to Friday, 9:30 to 16:00 New York time (afternoon to night in Saudi time)"},
           "tips": [
               ("Pip", "تحتاج وسيط يتيح الأسهم الأمريكية؛ كثير من الوسطاء السعوديين يوفرونها.",
                "You need a broker that offers US stocks; many Saudi brokers do."),
               ("Benny", "الأسعار بالدولار، فالوسيط يحوّل من الريال. شوف رسوم التحويل والعمولة لأنها تأثر على المبالغ الصغيرة.",
                "Prices are in dollars, so your riyals get converted; check the conversion fee and commission, they matter on small amounts."),
               ("Tank", "السوق يفتح الاثنين للجمعة ويقفل السبت والأحد، يعني يختلف عن أيام تداول.",
                "The market trades Monday to Friday and is closed on weekends, unlike Tadawul."),
               ("Ollie", "نقارن أداء الأسهم بمؤشر S&P 500 عن طريق SPY.",
                "We compare each stock with the S&P 500 (via SPY)."),
               ("Tank", "ما فيه حد يومي ثابت للسعر، لكن التداول يتوقف شوي إذا السهم تحرك بسرعة كبيرة، ويتوقف السوق كله إذا نزل مؤشر S&P 500 بنسبة 7٪ أو 13٪ أو 20٪ في يوم.",
                "There's no fixed daily price limit, but a stock pauses briefly if it moves too fast, and the whole market halts if the S&P 500 falls 7%, 13% or 20% in a day."),
               ("Benny", "الصفقة تتسوّى بعد يوم عمل واحد (T+1).", "Trades settle one business day later (T+1)."),
           ]},
}


# "How do I actually buy this?" step by step, per market. Broker-neutral; nothing here names or rates a broker.
HOW_TO_BUY = {
    "sa": [("افتح محفظة استثمارية عند وسيط مرخّص من هيئة السوق المالية (غالباً من تطبيق بنكك).",
            "Open an investment account with a broker licensed by the Capital Market Authority (often inside your bank's app)."),
           ("حوّل المبلغ من حسابك البنكي للمحفظة.", "Move the money from your bank account to the investment account."),
           ("ابحث عن الشركة بالرمز (مثل 2222) وتأكد من الاسم.", "Search the company by its symbol (e.g. 2222) and check the name."),
           ("استخدم «أمر محدد السعر» بسعر قريب من السعر الحالي، عشان ما تشتري بسعر أعلى مما توقعت.",
            "Use a limit order near the current price, so you never pay more than you expect."),
           ("شوف العمولة والضريبة في شاشة التأكيد قبل ما تضغط تنفيذ.", "Check the commission and VAT on the confirmation screen before you press buy."),
           ("الأسهم تنتقل لك رسمياً بعد يومي عمل (T+2). احتفظ بنسخة من إشعار التنفيذ.",
            "The shares are formally yours two business days later (T+2). Keep a copy of the trade confirmation.")],
    "us": [("افتح حساب عند وسيط يتيح الأسهم الأمريكية (كثير من الوسطاء السعوديين يتيحونها، وفيه وسطاء دوليين).",
            "Open an account with a broker that offers US stocks (many Saudi brokers do; there are international ones too)."),
           ("حوّل المبلغ وانتبه لرسوم تحويل العملة من الريال للدولار.", "Transfer the money and check the currency-conversion fee from your currency to dollars."),
           ("ابحث بالرمز (مثل AAPL) وتأكد من الاسم والبورصة.", "Search by symbol (e.g. AAPL) and check the name and exchange."),
           ("السوق يفتح 9:30 إلى 4:00 بتوقيت نيويورك. استخدم «أمر محدد السعر».",
            "The market is open 9:30 to 16:00 New York time. Use a limit order."),
           ("بعض الوسطاء يسمحون بجزء من السهم (كسور)، وهذا يساعد مع المبالغ الصغيرة.",
            "Some brokers let you buy part of a share (fractional shares), which helps with small amounts."),
           ("الصفقة تتسوّى بعد يوم عمل (T+1). احتفظ بنسخة من إشعار التنفيذ.", "Trades settle one business day later (T+1). Keep the trade confirmation.")],
}


def how_to_buy(market_id: str, lang: str) -> dict:
    return {m: [ar if lang == "ar" else en for ar, en in HOW_TO_BUY[m]] for m in (["sa", "us"] if market_id == "both" else [market_id])}


def market_status(market_id: str) -> dict:
    """Open/closed by regular hours in the market's own time zone (holidays not included)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    out = {}
    for m in (["sa", "us"] if market_id == "both" else [market_id]):
        info = MARKETS[m]
        now = datetime.now(ZoneInfo(info["tz"]))
        open_ = now.weekday() in info["days"] and info["open"] <= (now.hour, now.minute) < info["close"]
        out[m] = {"open": open_, "name": info["name"], "hours": info["hours"]}
    return out


def market_tips(market_id: str, lang: str) -> list[dict]:
    ms = ["sa", "us"] if market_id == "both" else [market_id]
    tips = []
    for m in ms:
        for c, ar, en in MARKETS[m]["tips"]:
            tips.append({"character": c, "tip": ar if lang == "ar" else en, "market": m})
    return tips


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
    from . import sharia
    halal = None
    if sharia.enabled():
        # Optional Sharia screen: only compliant companies are suggested. Unknown is not compliant, and the list
        # is never padded with others: if few remain, the answer says so.
        res = sharia.screen([x[0] for x in order])
        halal = {"method": sharia.settings()["method"],
                 "excluded": [{"symbol": x[0], "name_en": x[1], "name_ar": x[2], "status": res[x[0]]["status"],
                               "reasons": res[x[0]]["reasons"]} for x in order if res[x[0]]["status"] != "compliant"]}
        order = [x for x in order if res[x[0]]["status"] == "compliant"]
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
            mkt = "sa" if sym.endswith(".SR") else "us"
            if len(picks) >= count:
                break
            if any(p["symbol"] == sym for p in picks):
                continue
            cost = in_budget_ccy(sym)
            if cost is None or cost > cap:
                continue
            if cap != amount and any(p["sector"] == sector and p["market"] == mkt for p in picks):
                continue   # spread across sectors (within each market) while we still have choice
            px = prices[sym]
            picks.append({"symbol": sym, "name_en": en, "name_ar": ar, "sector": sector, "style": style, "market": mkt,
                          "price": px["price"], "currency": px["currency"], "price_in_budget": round(cost, 2)})
        if len(picks) >= count:
            break
    out = {"picks": picks, "prices_available": any(prices.values()), "source": market.SOURCE,
           "markets": market_status(market_id), "index_funds": index_funds(amount, currency, market_id)}
    if halal is not None:
        out["sharia"] = {**halal, "short": len(picks) < count, "wanted": count}
    return out


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
    "Bolt": ("الأسهم للمدى الطويل: الفلوس اللي بتحتاجها خلال سنوات قليلة (سيارة، زواج، دفعة بيت) الأفضل ما تكون في الأسهم.",
             "Stocks are for the long run: money you'll need within a few years (a car, a wedding, a home deposit) is better kept out of them."),
    "Buzz": ("صندوق مؤشرات منخفض التكلفة (ETF) يشتري لك السوق كله دفعة وحدة، وهو بداية أبسط لكثير من المبتدئين من اختيار أسهم مفردة.",
             "A low-cost index fund (ETF) buys the whole market in one go; for many beginners it's a simpler start than picking single stocks."),
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
    base = {"profile": prof, "plan": plan, "tips": tips, "stocks": [], "intro": None, "closing": None, "generated": False,
            "market_tips": market_tips(prof.get("market", "sa"), lang), "markets": market_status(prof.get("market", "sa")),
            "how_to_buy": how_to_buy(prof.get("market", "sa"), lang)}
    if scan.get("mode") == "demo" or not any(s.get("status") == "done" for s in scan["sessions"]):
        return base
    cached = db.get_setting(f"beginner_guide:{scan_id}:{lang}")
    if cached:
        return {**base, **cached, "plan": plan, "market_tips": base["market_tips"], "markets": base["markets"], "how_to_buy": base["how_to_buy"]}
    try:
        g = _mentor(scan, prof, plan, lang)
    except Exception as e:  # noqa: BLE001
        log.info("beginner lesson failed: %s", type(e).__name__)
        return base
    db.set_setting(f"beginner_guide:{scan_id}:{lang}", g)
    return {**base, **g, "plan": plan, "market_tips": base["market_tips"], "markets": base["markets"], "how_to_buy": base["how_to_buy"]}


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
        f"The chosen market: {', '.join(MARKETS[m]['name']['en'] for m in (['sa', 'us'] if prof['market'] == 'both' else [prof['market']]))}. "
        "Keep every tip relevant to that market (its currency, trading days, benchmark index); never mention another market's specifics.\n"
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
    raw = Voice(provider, quick, what="lesson")._ask(system, user)
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
