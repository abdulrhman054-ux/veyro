"""Albie the albatross: global markets & economy news courier.

- Headlines come from leading publishers' public RSS feeds (Arabic publishers for the Arabic
  screen, English publishers for the English screen). Only title, link, time and a short
  feed description are shown, always linked to the original.
- Market tiles come from real Yahoo Finance quotes.
- Albie's briefing and his "global link" (how today's world news may relate to a stock's move)
  are written by the LLM strictly from those headlines and real price moves: no new facts.
"""
from __future__ import annotations

import html
import logging
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .lazy import yf   # loads on first use (fast startup)

from .config import CHARACTERS, STYLE

log = logging.getLogger("veyro.world")


def _gn(q: str, hl: str, gl: str) -> str:
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl={hl}&gl={gl}&ceid={gl}:{hl}"


SOURCES = {
    "en": [
        {"id": "bloomberg", "name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss"},
        {"id": "bloomberg_econ", "name": "Bloomberg Economics", "url": "https://feeds.bloomberg.com/economics/news.rss"},
        {"id": "reuters", "name": "Reuters", "url": _gn("site:reuters.com markets", "en-US", "US"), "via": "Google News"},
        {"id": "ft", "name": "Financial Times", "url": "https://www.ft.com/markets?format=rss"},
        {"id": "wsj", "name": "The Wall Street Journal", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"},
        {"id": "cnbc", "name": "CNBC", "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html"},
        {"id": "economist", "name": "The Economist", "url": "https://www.economist.com/finance-and-economics/rss.xml"},
        {"id": "bbc", "name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},
        {"id": "marketwatch", "name": "MarketWatch", "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"},
    ],
    "ar": [
        {"id": "argaam", "name": "أرقام", "url": _gn("site:argaam.com", "ar", "SA"), "via": "Google News"},
        {"id": "asharq", "name": "الشرق بلومبرغ", "url": _gn("site:asharqbusiness.com", "ar", "SA"), "via": "Google News"},
        {"id": "alarabiya", "name": "العربية أسواق", "url": _gn("site:alarabiya.net أسواق", "ar", "SA"), "via": "Google News"},
        {"id": "aleqt", "name": "الاقتصادية", "url": _gn("site:aleqt.com", "ar", "SA"), "via": "Google News"},
        {"id": "reuters_ar", "name": "رويترز عربي", "url": _gn("site:reuters.com اقتصاد", "ar", "SA"), "via": "Google News"},
        {"id": "aljazeera", "name": "الجزيرة اقتصاد", "url": "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9"},
    ],
}

MARKETS = [
    ("^GSPC", "S&P 500", "إس آند بي 500"), ("^IXIC", "Nasdaq", "ناسداك"), ("^DJI", "Dow Jones", "داو جونز"),
    ("^TASI.SR", "TASI (Saudi)", "تاسي (السعودية)"), ("^FTSE", "FTSE 100", "فوتسي 100"), ("^GDAXI", "DAX", "داكس"),
    ("^N225", "Nikkei 225", "نيكاي 225"), ("^HSI", "Hang Seng", "هانغ سنغ"), ("BZ=F", "Brent oil", "خام برنت"),
    ("GC=F", "Gold", "الذهب"), ("DX-Y.NYB", "US Dollar index", "مؤشر الدولار"), ("^TNX", "US 10Y yield", "عائد السندات الأمريكية 10 سنوات"),
    ("BTC-USD", "Bitcoin", "بيتكوين"),
]

_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


def _cached(key: str, ttl: float, fn):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    val = fn()
    lists = [v for v in val.values() if isinstance(v, list)] if isinstance(val, dict) else []
    empty = not val or (lists and not any(lists))
    with _lock:
        if len(_cache) > 400:   # searches are open-ended: keep the cache bounded
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:200]:
                _cache.pop(k, None)
        # A failed or empty fetch is retried after a minute instead of being served for the full ttl.
        _cache[key] = (time.time() - max(0.0, ttl - 60) if empty else time.time(), val)
    return val


_TAG = re.compile(r"<[^>]+>")


def _clean(s: str | None, n: int | None = None) -> str:
    s = html.unescape(_TAG.sub(" ", s or "")).replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if n and len(s) > n:
        s = s[: n - 1].rsplit(" ", 1)[0] + "…"
    return s


def _fetch(src: dict, per_source: int) -> tuple[dict, list[dict]]:
    try:
        raw = urllib.request.urlopen(urllib.request.Request(src["url"], headers={"User-Agent": "Mozilla/5.0 Veyro/1.0"}), timeout=10).read(1_500_000)
        root = ET.fromstring(raw)
        items = []
        for it in root.iter("item"):
            title = _clean(it.findtext("title"))
            link = (it.findtext("link") or "").strip()
            if not title or not link.startswith("http"):
                continue
            src_el = it.find("source")
            publisher = _clean(it.findtext("source")) or src["name"]
            domain = urllib.parse.urlparse((src_el.get("url") if src_el is not None else None) or link).netloc.replace("www.", "")
            if src.get("via") and " - " in title:
                title = title.rsplit(" - ", 1)[0].strip()  # Google News appends the publisher
            ts = None
            pd = it.findtext("pubDate")
            if pd:
                try:
                    ts = parsedate_to_datetime(pd).astimezone(timezone.utc).isoformat(timespec="minutes")
                except (TypeError, ValueError):
                    ts = None
            desc = "" if src.get("via") else _clean(it.findtext("description"), 220)
            name = publisher if src.get("search") else src["name"]
            items.append({"title": title, "link": link, "published": ts, "source": name, "source_id": src["id"],
                          "publisher": publisher, "domain": domain, "trusted": _trusted(domain, publisher) or not src.get("search"),
                          "summary": desc if desc and desc != title else ""})
            if len(items) >= per_source:
                break
        return {"id": src["id"], "name": src["name"], "ok": bool(items), "count": len(items), "via": src.get("via")}, items
    except Exception as e:  # noqa: BLE001
        log.info("feed %s unavailable: %s", src["id"], type(e).__name__)
        return {"id": src["id"], "name": src["name"], "ok": False, "count": 0, "via": src.get("via")}, []


# Publishers Albie treats as strong sources when searching the open web (ranked first).
TRUSTED = {
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "cnbc.com", "economist.com", "bbc.com", "bbc.co.uk", "apnews.com",
    "marketwatch.com", "barrons.com", "nikkei.com", "asia.nikkei.com", "nytimes.com", "theguardian.com", "forbes.com",
    "finance.yahoo.com", "investing.com", "fortune.com", "axios.com", "politico.com", "imf.org", "worldbank.org",
    "federalreserve.gov", "ecb.europa.eu", "opec.org", "iea.org", "scmp.com", "caixinglobal.com", "handelsblatt.com",
    "argaam.com", "asharqbusiness.com", "alarabiya.net", "aleqt.com", "aljazeera.net", "aawsat.com", "spa.gov.sa",
    "cnbcarabia.com", "sama.gov.sa", "saudiexchange.sa", "alkhaleej.ae", "arabnews.com", "zawya.com", "thenationalnews.com",
}
TRUSTED_NAMES = {"Reuters", "Bloomberg", "Financial Times", "The Wall Street Journal", "CNBC", "The Economist", "BBC", "AP News",
                 "Associated Press", "MarketWatch", "Barron's", "Nikkei Asia", "أرقام", "الشرق بلومبرغ", "العربية", "الاقتصادية",
                 "الجزيرة نت", "الشرق الأوسط", "CNBC عربية", "Arab News", "Zawya", "The National"}


def _trusted(domain: str, publisher: str) -> bool:
    d = (domain or "").lower()
    return any(d == t or d.endswith("." + t) for t in TRUSTED) or any(n.lower() in (publisher or "").lower() for n in TRUSTED_NAMES)


def search(query: str, lang: str, limit: int = 30) -> dict:
    """Albie searches the open web's news (Google News index) for any topic; strong sources first."""
    q = re.sub(r"[^\w\s\-\.؀-ۿ:\"']", " ", query)[:120].strip()
    if not q:
        return {"query": query, "items": [], "sources": []}
    hl, gl = ("ar", "SA") if lang == "ar" else ("en-US", "US")

    def load():
        src = {"id": "search", "name": "Google News", "url": _gn(f"{q} when:7d", hl, gl), "via": "Google News", "search": True}
        status, items = _fetch(src, 80)
        items.sort(key=lambda i: (not i["trusted"], -(datetime.fromisoformat(i["published"]).timestamp() if i["published"] else 0)))
        return {"query": q, "lang": lang, "items": items[:limit], "ok": status["ok"],
                "trusted_count": sum(1 for i in items if i["trusted"]),
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return _cached(f"search:{lang}:{q.lower()}", 600, load)


def analyze(query: str, lang: str, provider: str, model: str) -> dict:
    """Albie's analysis of a topic from what he found: what's happening, why it may matter, what to watch."""
    found = search(query, lang)
    en = search(query, "en") if lang != "en" else found
    m = markets()
    items = [i for i in found["items"] if i["trusted"]][:15] or found["items"][:15]
    extra = [i for i in en["items"] if i["trusted"]][:10] if lang != "en" else []
    if not items and not extra:
        return {"text": None, "items": [], "query": found["query"]}
    system = (
        "You are Albie, an albatross courier of global markets and economic news in a cosy pixel-art office game. "
        f"Personality: {ALBIE_STYLE[lang]}\n"
        f"Analyse the news topic \"{found['query']}\" for a non-expert investor, in 4 short parts, each 1-3 sentences, "
        "with a short heading: what is happening; why it may matter for markets; assets or sectors to watch; what to keep an eye on next.\n"
        "Hard rules: use ONLY the headlines and market moves provided; name the publication for every claim; use hedged language "
        "for impacts (may, could); add no facts, numbers or quotes that are not in the input; if sources disagree, say so; "
        "if coverage is thin, say so. This is analysis, not financial advice. "
        f"Language: {LANG[lang]} Write ONLY in this language. End with: {CATCH[lang]}"
    )
    user = (f"Headlines found (strong sources first):\n{_headline_block(items + extra, 25)}\n\n"
            f"Market moves (Yahoo Finance):\n{_tiles_block(m['tiles'])}")
    return {"text": _llm(provider, model, system, user), "items": items + extra, "query": found["query"]}


def news(lang: str, per_source: int = 6) -> dict:
    def load():
        with ThreadPoolExecutor(max_workers=8) as ex:
            res = list(ex.map(lambda s: _fetch(s, per_source), SOURCES[lang]))
        items = [i for _, its in res for i in its]
        items.sort(key=lambda i: i["published"] or "", reverse=True)
        return {"lang": lang, "sources": [s for s, _ in res], "items": items,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return _cached(f"news:{lang}", 600, load)


def markets() -> dict:
    def load():
        tiles = []
        for sym, en, ar in MARKETS:
            try:
                h = yf.Ticker(sym).history(period="1mo", auto_adjust=False)
                cs = [float(x) for x in h["Close"].dropna().tolist()]
                if len(cs) >= 2:
                    tiles.append({"symbol": sym, "en": en, "ar": ar, "last": cs[-1], "change": cs[-1] / cs[-2] - 1,
                                  "date": h.index[-1].strftime("%Y-%m-%d"), "spark": cs[-7:]})
                    continue
                # Some indices (e.g. TASI) keep only one day of history on Yahoo: use the live quote instead.
                fi = yf.Ticker(sym).fast_info
                last, prev = fi.get("lastPrice"), fi.get("previousClose")
                if last and prev:
                    tiles.append({"symbol": sym, "en": en, "ar": ar, "last": float(last), "change": float(last) / float(prev) - 1,
                                  "date": h.index[-1].strftime("%Y-%m-%d") if len(h) else None, "spark": []})
                    continue
            except Exception as e:  # noqa: BLE001
                log.info("tile %s unavailable: %s", sym, type(e).__name__)
            tiles.append({"symbol": sym, "en": en, "ar": ar, "last": None, "change": None, "date": None, "spark": []})
        return {"tiles": tiles, "source": "Yahoo Finance (yfinance)", "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return _cached("markets", 300, load)


LANG = {
    "ar": ("Arabic. Friendly, casual, Saudi-leaning Arabic, natural and human. Arabic words only; publication names in Arabic "
           "as given; Western digits."),
    "en": "English. Warm, playful, plain English.",
}
ALBIE_STYLE = {
    "ar": "لقلق مرح وسريع الكلام، يحب يقول «يا جماعة عندي لكم لفّة على العالم!» و«من فوق الغيوم شفت…»، ويذكر اسم الصحيفة مع كل خبر.",
    "en": "A chatty, globe-trotting courier who opens with 'Fresh off the jet stream!' and 'From up above the clouds I spotted…', and always names the paper.",
}
CATCH = {"ar": "ريشتي تطير بالأخبار!", "en": "feathers full of news!"}


def _headline_block(items: list[dict], n: int = 25) -> str:
    return "\n".join(f"- [{i['source']}] {i['title']}" + (f" ({i['published'][:10]})" if i.get("published") else "") for i in items[:n])


def _tiles_block(tiles: list[dict]) -> str:
    return "\n".join(f"- {t['en']}: {t['change'] * 100:+.2f}% (close {t['date']})" for t in tiles if t.get("change") is not None)


def _llm(provider: str, model: str, system: str, user: str) -> str:
    from .voice import Voice
    v = Voice(provider, model, what="albie")
    return v._ask(system, user)


def briefing(lang: str, provider: str, model: str) -> str:
    def make():
        n, m = news(lang), markets()
        system = (
            "You are Albie, an albatross news courier in a cosy pixel-art office game about the stock market. "
            f"Personality: {ALBIE_STYLE[lang]}\n"
            "Write a short spoken briefing (4-6 sentences) on today's global markets and economy.\n"
            "Hard rules: use ONLY the headlines and market moves provided; no new facts, numbers, names or predictions; "
            "name the publication for each story you mention; if the data is thin, say so. "
            f"Language: {LANG[lang]} Write ONLY in this language. End with: {CATCH[lang]}"
        )
        user = f"Headlines:\n{_headline_block(n['items'])}\n\nMarket moves (Yahoo Finance):\n{_tiles_block(m['tiles'])}"
        return _llm(provider, model, system, user)
    return _cached(f"brief:{lang}:{provider}:{model}", 1800, make)


def link(ticker: str, lang: str, provider: str, model: str, move: dict | None, context: str = "") -> str:
    """Albie connects today's world headlines to a stock's real move. Hedged, sourced, no invented causes."""
    en = news("en")
    local = news(lang) if lang != "en" else en
    m = markets()
    move_txt = (f"{ticker} last close change: {move['change'] * 100:+.2f}% (close {move['date']})" if move and move.get("change") is not None
                else f"{ticker}: latest price move unavailable")
    system = (
        "You are Albie, an albatross courier of global markets news, visiting the analyst office. "
        f"Personality: {ALBIE_STYLE[lang]}\n"
        f"Task: in 2-4 short spoken sentences, say which of today's world headlines could plausibly relate to {ticker}'s "
        "recent move, and how (e.g. rates, oil, the dollar, trade, its sector).\n"
        "Hard rules: use ONLY the headlines, market moves and analyst context provided; name the publication; "
        "use hedged language (may, could) because a headline does not prove a cause; add no new facts or numbers; "
        "if nothing clearly relates, say so honestly. "
        f"Language: {LANG[lang]} Write ONLY in this language. End with: {CATCH[lang]}"
    )
    user = (f"{move_txt}\n\nWorld market moves:\n{_tiles_block(m['tiles'])}\n\nHeadlines:\n{_headline_block(en['items'], 20)}\n"
            + (f"{_headline_block(local['items'], 10)}\n" if lang != "en" else "")
            + (f"\nAnalyst context (excerpt):\n{context[:3000]}" if context else ""))
    return _llm(provider, model, system, user)


def stock_move(ticker: str) -> dict | None:
    from . import market
    h = market.history(ticker, "1mo")
    if not h or len(h["closes"]) < 2:
        return None
    return {"change": h["closes"][-1] / h["closes"][-2] - 1, "date": h["dates"][-1], "last": h["closes"][-1]}


CHARACTERS.setdefault("Albie", {"animal": "albatross", "role": "Global markets & economy news courier",
                                 "catch_en": CATCH["en"], "catch_ar": CATCH["ar"],
                                 "persona": "a chatty globe-trotting albatross who carries world economic news"})
STYLE.setdefault("Albie", ALBIE_STYLE)
