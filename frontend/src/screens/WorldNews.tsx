import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { SpriteSvg, charColor } from "../art/Sprite";
import { click, voiceBlip, VOICES } from "../audio";
import { Stroller } from "../components/Stroller";
import { fmtDate, fmtNum, fmtPct } from "../i18n";
import { usePrefs } from "../prefs";

type Item = { title: string; link: string; published: string | null; source: string; summary: string; trusted?: boolean; domain?: string };
type News = { sources: { id: string; name: string; ok: boolean; count: number; via?: string }[]; items: Item[]; fetched_at: string };
type Tile = { symbol: string; en: string; ar: string; last: number | null; change: number | null; date: string | null; spark: number[] };

const TXT = {
  ar: {
    title: "ألبي · ناقل الأخبار العالمية", sub: "طائر القطرس اللي يلف العالم ويجيب لك أخبار الأسواق والاقتصاد من أقوى الصحف.",
    brief: "اطلب لفّة الأخبار من ألبي", briefing: "ألبي يجمع الأخبار…", noKey: "أحتاج مفتاح النموذج من الإعدادات عشان أحلل وأتكلم. العناوين تحت حقيقية وتقدر تقرأها الحين.",
    markets: "الأسواق العالمية الآن", source: "المصدر", headlines: "آخر العناوين", all: "الكل", unavailable: "غير متوفر",
    search: "ابحث في أخبار الإنترنت عن أي موضوع", searchPh: "مثال: الفيدرالي، أوبك، الصين، أسعار الفائدة", analyze: "ابحث وحلّل",
    analyzing: "ألبي يطير ويدوّر في أقوى المصادر…", found: "لقيت", strong: "من مصادر قوية", results: "نتيجة",
    link: "اربط الأخبار العالمية بسهم", linkPh: "رمز السهم مثل NVDA", linkBtn: "اربط", move: "آخر حركة للسهم",
    feeds: "حالة المصادر", strongTag: "مصدر قوي", disclaimer: "تحليل للمساعدة على التفكير، وليس نصيحة مالية. كل خبر مرتبط بمصدره الأصلي.",
    greet: "يا جماعة عندي لكم لفّة على العالم! اضغط الزر وأعطيك الخلاصة، أو اسألني عن أي موضوع. ريشتي تطير بالأخبار!",
  },
  en: {
    title: "Albie · World News Courier", sub: "The albatross who circles the globe and brings you markets and economy news from the strongest papers.",
    brief: "Ask Albie for a news round", briefing: "Albie is gathering the news…", noKey: "I need a model key in Settings to analyse and talk. The headlines below are real and ready to read now.",
    markets: "World markets now", source: "Source", headlines: "Latest headlines", all: "All", unavailable: "Unavailable",
    search: "Search internet news on any topic", searchPh: "e.g. the Fed, OPEC, China, interest rates", analyze: "Search & analyse",
    analyzing: "Albie is flying around the strongest sources…", found: "Found", strong: "from strong sources", results: "results",
    link: "Link world news to a stock", linkPh: "Ticker e.g. NVDA", linkBtn: "Link", move: "Stock's latest move",
    feeds: "Source status", strongTag: "strong source", disclaimer: "Analysis to help you think, not financial advice. Every story links to its original source.",
    greet: "Fresh off the jet stream! Press the button for my round-up, or ask me about any topic. feathers full of news!",
  },
};

function Speech({ text }: { text: string }) {
  const { motionOff } = usePrefs();
  const [n, setN] = useState(motionOff ? text.length : 0);
  useEffect(() => { setN(motionOff ? text.length : 0); }, [text, motionOff]);
  useEffect(() => {
    if (n >= text.length) return;
    const h = setTimeout(() => { setN((v) => { voiceBlip("Albie", text[v], v + 1); return v + 1; }); }, VOICES.Albie.msPerChar);
    return () => clearTimeout(h);
  }, [n, text]);
  return <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.8, fontSize: 17 }} onClick={() => setN(text.length)}>{text.slice(0, n)}{n < text.length && <span className="caret" />}</div>;
}

export function WorldNews() {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const t = TXT[lang];
  const [news, setNews] = useState<News | null>(null);
  const [tiles, setTiles] = useState<Tile[] | null>(null);
  const [filter, setFilter] = useState("all");
  const [say, setSay] = useState<string>(t.greet);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Item[] | null>(null);
  const [tk, setTk] = useState("");
  const [move, setMove] = useState<{ change: number; date: string } | null>(null);

  useEffect(() => { setSay(TXT[lang].greet); setFound(null); setNews(null); setFilter("all");
    api.get<News>(`/api/world/news?lang=${lang}`).then(setNews).catch(() => setNews({ sources: [], items: [], fetched_at: "" })); }, [lang]);
  useEffect(() => { api.get<{ tiles: Tile[] }>("/api/world/markets").then((r) => setTiles(r.tiles)).catch(() => setTiles([])); }, []);

  const avg = useMemo(() => { const c = (tiles ?? []).filter((x) => x.change != null && !x.symbol.includes("TNX")).map((x) => x.change!); return c.length ? c.reduce((a, b) => a + b, 0) / c.length : 0; }, [tiles]);
  const items = (news?.items ?? []).filter((i) => filter === "all" || i.source === filter);

  const talk = async (fn: () => Promise<string | null>) => {
    setBusy(true); click(); setSay(t.briefing);
    try { const r = await fn(); setSay(r ?? t.noKey); } catch (e) { setSay(e instanceof ApiError && e.code === "no_key" ? t.noKey : lang === "ar" ? "الخط مقطوع! جرّب بعدين." : "Line's down! Try again later."); }
    setBusy(false);
  };
  const brief = () => talk(async () => (await api.post<{ text: string }>("/api/world/briefing", { lang })).text);
  const analyze = () => talk(async () => {
    setFound(null);
    try {
      const r = await api.post<{ text: string | null; items: Item[] }>("/api/world/analyze", { q, lang });
      setFound(r.items); return r.text;
    } catch (e) {
      if (e instanceof ApiError && e.code === "no_key") {
        const s = await api.get<{ items: Item[] }>(`/api/world/search?q=${encodeURIComponent(q)}&lang=${lang}`); setFound(s.items);
      }
      throw e;
    }
  });
  const link = () => talk(async () => {
    const r = await api.post<{ text: string; move: { change: number; date: string } | null }>("/api/world/link", { ticker: tk.trim().toUpperCase(), lang });
    setMove(r.move); return r.text;
  });

  const mood = avg >= 0.005 ? "rally" : avg <= -0.005 ? "slump" : "flat";
  return (
    <div className="stack" style={{ gap: 18 }}>
      <section className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div className={`room mood-${mood}`} style={{ position: "relative", height: 150, borderRadius: 0, boxShadow: "none", background: "var(--sky)" }}>
          {mood === "slump" && <div className="rain" />}
          <Stroller sky height={150} walkers={[{ name: "Albie", fly: true, dur: 26 }]} />
        </div>
        <div style={{ padding: 20, display: "flex", gap: 16, alignItems: "flex-start" }}>
          <div className="portrait" style={{ width: 96, height: 104 }}><SpriteSvg name="Albie" px={4} frame="wave" talk={busy} /></div>
          <div className="stack" style={{ flex: 1, gap: 8 }}>
            <div className="row"><h1 style={{ fontSize: 24 }}>{t.title}</h1><span className="tagname" style={{ background: charColor("Albie") }}>✈</span></div>
            <p className="muted" style={{ margin: 0 }}>{t.sub}</p>
            <div className="dlg" style={{ position: "relative", left: 0, top: 0, width: "100%", minHeight: 0, padding: "22px 26px", animation: "none", cursor: "default" }} aria-live="polite">
              <Speech text={say} />
            </div>
            <div className="row">
              <button className="primary btn" disabled={busy} onClick={brief}>{t.brief}</button>
            </div>
          </div>
        </div>
      </section>

      <section className="card stack">
        <h2 style={{ fontSize: 20 }}>{t.markets}</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))", gap: 10 }}>
          {(tiles ?? []).map((x) => (
            <div key={x.symbol} className="tile">
              <span style={{ fontWeight: 800, fontSize: 14 }}>{lang === "ar" ? x.ar : x.en}</span>
              <b className="pixel ltr" style={{ fontSize: 18 }}>{x.last != null ? fmtNum(x.last, lang, { maximumFractionDigits: 2 }) : t.unavailable}</b>
              <span className={`pixel ltr ${x.change != null ? (x.change >= 0 ? "pos" : "neg") : "muted"}`}>{x.change != null ? `${x.change >= 0 ? "▲" : "▼"} ${fmtPct(x.change, lang)}` : "—"}</span>
              {x.spark.length > 1 && (() => { const lo = Math.min(...x.spark), hi = Math.max(...x.spark); return (
                <svg width="100%" height="24" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true">
                  <polyline fill="none" stroke={(x.change ?? 0) >= 0 ? "#2F9A62" : "#D9573F"} strokeWidth="2" points={x.spark.map((v, i) => `${(i / (x.spark.length - 1)) * 100},${22 - ((v - lo) / (hi - lo || 1)) * 20}`).join(" ")} />
                </svg>); })()}
            </div>
          ))}
        </div>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>{t.source}: Yahoo Finance · {tiles?.[0]?.date ?? ""}</p>
      </section>

      <div className="grid2">
        <section className="card stack">
          <h2 style={{ fontSize: 19 }}>{t.search}</h2>
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input className="field" style={{ flex: 1, minWidth: 0 }} value={q} placeholder={t.searchPh} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && q.trim().length > 1) void analyze(); }} />
            <button className="primary btn" disabled={busy || q.trim().length < 2} onClick={analyze}>{t.analyze}</button>
          </div>
          {found && <p className="muted" style={{ margin: 0 }}>{t.found} <b className="ltr">{found.length}</b> {t.results} · <b className="ltr">{found.filter((i) => i.trusted).length}</b> {t.strong}</p>}
          {found?.slice(0, 8).map((i) => <NewsRow key={i.link} i={i} lang={lang} strongTag={t.strongTag} />)}
        </section>
        <section className="card stack">
          <h2 style={{ fontSize: 19 }}>{t.link}</h2>
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input className="field pixel ltr" style={{ flex: 1, minWidth: 0 }} value={tk} placeholder={t.linkPh} onChange={(e) => setTk(e.target.value.toUpperCase())} />
            <button className="primary btn" disabled={busy || !tk.trim()} onClick={link}>{t.linkBtn}</button>
          </div>
          {move && <p style={{ margin: 0 }}>{t.move}: <b className={`pixel ltr ${move.change >= 0 ? "pos" : "neg"}`}>{fmtPct(move.change, lang)}</b> · <span className="ltr">{move.date}</span></p>}
          <Stroller walkers={[{ name: "Pip", say: lang === "ar" ? "خبر خبر!" : "News, news!", dur: 14 }]} />
        </section>
      </div>

      <section className="card stack">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ fontSize: 20 }}>{t.headlines}</h2>
          <span className="muted" style={{ fontSize: 13 }}>{news?.fetched_at ? fmtDate(news.fetched_at, lang) : ""}</span>
        </div>
        <div className="row" style={{ gap: 6 }} role="group" aria-label={t.feeds}>
          <button className="ghost btn" aria-pressed={filter === "all"} style={filter === "all" ? { borderColor: "#2F6FB0" } : undefined} onClick={() => setFilter("all")}>{t.all}</button>
          {news?.sources.map((s) => (
            <button key={s.id} className="ghost btn" disabled={!s.ok} aria-pressed={filter === s.name} onClick={() => setFilter(s.name)}
              style={filter === s.name ? { borderColor: "#2F6FB0" } : undefined} title={s.ok ? "" : t.unavailable}>
              {s.name}{!s.ok && ` · ${t.unavailable}`}
            </button>
          ))}
        </div>
        {news === null ? <p aria-busy="true">…</p> : items.length === 0 ? <p className="muted">{t.unavailable}</p> : (
          <div className="grid2">{items.slice(0, 40).map((i) => <NewsRow key={i.link} i={i} lang={lang} strongTag={t.strongTag} />)}</div>
        )}
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>{t.disclaimer}</p>
      </section>
    </div>
  );
}

function NewsRow({ i, lang, strongTag }: { i: Item; lang: "ar" | "en"; strongTag: string }) {
  return (
    <article className="news-item">
      <div className="row" style={{ gap: 6 }}>
        <span className="srcchip">{i.source}</span>
        {i.trusted && i.domain && <span className="muted" style={{ fontSize: 12 }}>✓ {strongTag}</span>}
        <span className="muted" style={{ fontSize: 12 }}>{fmtDate(i.published, lang) ?? ""}</span>
      </div>
      <a href={i.link} target="_blank" rel="noopener noreferrer">{i.title}</a>
      {i.summary && <span className="muted" style={{ fontSize: 14 }}>{i.summary}</span>}
    </article>
  );
}
