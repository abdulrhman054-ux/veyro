import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { StarButton, useAssistant } from "../assistant/Assistant";
import { PageHeader } from "../components/PageHeader";
import { fmtNum } from "../i18n";
import { usePrefs } from "../prefs";
import { AlertButton, AlertList, type PriceAlert } from "../extras/PriceAlerts";

type Item = { symbol: string; en: string; ar: string; unit?: string; derived?: boolean };
type Catalog = { boards: Record<"us" | "sa", Item[]>; indices: Record<"us" | "sa", Item[]>; metals: Item[]; source: string;
  markets: Record<string, { open: boolean; name: { ar: string; en: string }; hours: { ar: string; en: string } }> };
type Quote = { symbol: string; price?: number; prev_close?: number; change?: number; change_pct?: number; time?: string; ts?: number;
  day_high?: number; day_low?: number; volume?: number; currency?: string; live?: boolean; derived?: boolean };

const KEY = "veyro.live.market.v1";

/** Live prices: US or Saudi board, their indices, and metals, streaming from Yahoo Finance. */
export function LiveBoard({ active, onAnalyze }: { active: boolean; onAnalyze: (ticker: string) => void }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const ar = lang === "ar";
  const { favorites } = useAssistant();
  const [market, setMarket] = useState<"us" | "sa">(() => { try { return (localStorage.getItem(KEY) as "us" | "sa") || "sa"; } catch { return "sa"; } });
  useEffect(() => { try { localStorage.setItem(KEY, market); } catch { /* ignore */ } }, [market]);
  const [cat, setCat] = useState<Catalog | null>(null);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [ticks, setTicks] = useState<Record<string, number[]>>({});   // this session's price path per symbol
  const [flash, setFlash] = useState<Record<string, { dir: "up" | "down"; k: number }>>({});
  const [conn, setConn] = useState<"connecting" | "live" | "snapshot" | "off">("connecting");
  const [, setNow] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  useEffect(() => { if (active) api.get<{ alerts: PriceAlert[] }>("/api/price_alerts").then((r) => setAlerts(r.alerts)).catch(() => {}); }, [active]);

  useEffect(() => { api.get<Catalog>("/api/live/catalog").then(setCat).catch(() => {}); }, []);
  useEffect(() => { const h = setInterval(() => setNow((n) => n + 1), 1000); return () => clearInterval(h); }, []);

  const want = useMemo(() => {
    if (!cat) return [] as string[];
    return [...new Set([...cat.boards[market], ...cat.indices[market], ...cat.metals].map((x) => x.symbol).concat(favorites))];
  }, [cat, market, favorites]);

  const wantRef = useRef<string[]>([]);
  wantRef.current = want;

  // One socket while the screen is open; it only streams what this screen shows (always the current list,
  // also after a reconnect).
  useEffect(() => {
    if (!active || !cat) return;
    let alive = true, retry = 0, timer = 0;
    const open = () => {
      if (!alive) return;
      const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/live`);
      wsRef.current = ws;
      ws.onopen = () => { retry = 0; ws.send(JSON.stringify({ want: wantRef.current })); };
      ws.onmessage = (m) => {
        let msg: { type: string; quotes?: Quote[]; stream?: boolean };
        try { msg = JSON.parse(m.data); } catch { return; }
        setConn(msg.stream ? "live" : "snapshot");
        if (!msg.quotes?.length) return;
        const qs = msg.quotes;
        setQuotes((old) => {
          const next = { ...old };
          const fl: Record<string, { dir: "up" | "down"; k: number }> = {};
          for (const q of qs) {
            const prev = old[q.symbol]?.price;
            if (prev != null && q.price != null && q.price !== prev) fl[q.symbol] = { dir: q.price > prev ? "up" : "down", k: Date.now() + Math.random() };
            next[q.symbol] = { ...old[q.symbol], ...q };
          }
          if (Object.keys(fl).length) setFlash((f) => ({ ...f, ...fl }));
          return next;
        });
        setTicks((old) => {
          const next = { ...old };
          for (const q of qs) if (q.price != null) next[q.symbol] = [...(old[q.symbol] ?? []), q.price].slice(-60);
          return next;
        });
      };
      ws.onclose = () => { if (!alive) return; setConn("off"); timer = window.setTimeout(open, Math.min(15000, 1000 * 2 ** retry++)); };
    };
    open();
    return () => { alive = false; clearTimeout(timer); wsRef.current?.close(); wsRef.current = null; };
  }, [active, cat]);   // eslint-disable-line react-hooks/exhaustive-deps

  // Switching market or favourites: tell the open socket what to stream now.
  useEffect(() => { const ws = wsRef.current; if (ws && ws.readyState === 1) ws.send(JSON.stringify({ want })); }, [want]);

  if (!cat) return <div className="card" aria-busy="true">…</div>;
  const mk = cat.markets[market];
  const favItems: Item[] = favorites.filter((f) => !cat.boards[market].some((b) => b.symbol === f)).map((f) => ({ symbol: f, en: f, ar: f }));

  return (
    <div className="stack" style={{ gap: 16 }}>
      <PageHeader host="Ollie" title={ar ? "الأسعار مباشرة" : "Live prices"}
        sub={ar ? "أسعار السوق الأمريكي والسعودي والمعادن تتحدث لحظة بلحظة من Yahoo Finance. اضغط على أي سهم عشان يحلله الفريق." : "US and Saudi stocks and metals, updating tick by tick from Yahoo Finance. Tap any stock to have the team analyse it."}
        say={ar ? "عيني على الشاشة…" : "Eyes on the tape…"} />

      <div className="row live-bar" style={{ gap: 10 }}>
        <div className="segbtns" role="group" aria-label={ar ? "السوق" : "Market"}>
          <button aria-pressed={market === "sa"} onClick={() => setMarket("sa")}>{ar ? "🇸🇦 السوق السعودي" : "🇸🇦 Saudi market"}</button>
          <button aria-pressed={market === "us"} onClick={() => setMarket("us")}>{ar ? "🇺🇸 السوق الأمريكي" : "🇺🇸 US market"}</button>
        </div>
        {mk && <span className={`chip mkt ${mk.open ? "open" : "closed"}`} style={{ height: "auto", minHeight: 30, whiteSpace: "normal" }}>
          <i />{mk.name[lang]} · {mk.open ? (ar ? "مفتوح الآن" : "open now") : (ar ? "مقفل الآن" : "closed now")}
          <span className="muted" style={{ fontSize: 12 }}>· {mk.hours[lang]}</span></span>}
        <span style={{ flex: 1 }} />
        <span className={`livebadge ${conn}`} role="status">
          <i />{conn === "live" ? (ar ? "بث مباشر" : "Streaming live") : conn === "snapshot" ? (ar ? "آخر الأسعار (البث غير متاح الآن)" : "Latest prices (stream unavailable)")
            : conn === "off" ? (ar ? "انقطع الاتصال، نعيد المحاولة…" : "Disconnected, retrying…") : (ar ? "نتصل…" : "Connecting…")}
        </span>
      </div>

      <AlertList alerts={alerts} onChange={setAlerts} />
      <section className="stack" style={{ gap: 8 }} aria-label={ar ? "المؤشرات" : "Indices"}>
        <div className="live-grid idx">
          {cat.indices[market].map((it) => <Tile key={it.symbol} it={it} q={quotes[it.symbol]} path={ticks[it.symbol]} fl={flash[it.symbol]} lang={lang} compact />)}
        </div>
      </section>

      <section className="stack" style={{ gap: 8 }}>
        <h2 style={{ fontSize: 20, margin: 0 }}>{ar ? "الأسهم" : "Stocks"}</h2>
        <div className="live-grid">
          {[...favItems, ...cat.boards[market]].map((it) => <Tile key={it.symbol} it={it} q={quotes[it.symbol]} path={ticks[it.symbol]} fl={flash[it.symbol]} lang={lang}
            onAnalyze={() => onAnalyze(it.symbol)} fav={favorites.includes(it.symbol)} onAlerts={setAlerts} />)}
        </div>
      </section>

      <section className="stack" style={{ gap: 8 }}>
        <h2 style={{ fontSize: 20, margin: 0 }}>{ar ? "المعادن" : "Metals"}</h2>
        <div className="live-grid">
          {cat.metals.map((it) => <Tile key={it.symbol} it={it} q={quotes[it.symbol]} path={ticks[it.symbol]} fl={flash[it.symbol]} lang={lang}
            onAlerts={it.derived ? undefined : setAlerts} />)}
        </div>
        <p className="muted" style={{ margin: 0, fontSize: 13, lineHeight: 1.7 }}>{ar
          ? "المعادن من العقود الآجلة في بورصة COMEX/NYMEX (دولار للأونصة، والنحاس دولار للرطل). سعر الجرام بالريال محسوب من سعر الذهب وسعر صرف الريال، وما يشمل مصنعية أو ضريبة."
          : "Metals are COMEX/NYMEX futures (USD per troy ounce; copper per pound). Gold per gram in SAR is calculated from gold and the riyal rate and excludes making charges and VAT."}</p>
      </section>

      <p className="muted" style={{ margin: 0, fontSize: 13, lineHeight: 1.7 }}>{ar
        ? "المصدر: Yahoo Finance. «مباشر» تعني أن السعر وصل من البث اللحظي؛ غيرها آخر سعر معروف مع وقته. بعض البورصات قد يطبّق عليها المصدر تأخيراً. للمعلومة وليس نصيحة مالية."
        : "Source: Yahoo Finance. “Live” means the price arrived on the real-time stream; otherwise it is the last known price with its time. The source may delay some exchanges. Information, not financial advice."}</p>
    </div>
  );
}

function ago(iso: string | undefined, lang: "ar" | "en") {
  if (!iso) return "";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return lang === "ar" ? `قبل ${s} ث` : `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return lang === "ar" ? `قبل ${m} د` : `${m}m ago`;
  return new Intl.DateTimeFormat(lang === "ar" ? "ar-SA-u-nu-latn-ca-gregory" : "en-US", { dateStyle: "short", timeStyle: "short" }).format(new Date(iso));
}

function Tile({ it, q, path, fl, lang, compact, onAnalyze, fav, onAlerts }: { it: Item; q?: Quote; path?: number[]; fl?: { dir: "up" | "down"; k: number };
  lang: "ar" | "en"; compact?: boolean; onAnalyze?: () => void; fav?: boolean; onAlerts?: (a: PriceAlert[]) => void }) {
  const ar = lang === "ar";
  const ch = q?.change_pct;
  const dir = ch == null ? "" : ch >= 0 ? "pos" : "neg";
  const fresh = !!q?.live && !!q.ts && Date.now() / 1000 - q.ts < 120;
  const cur = q?.currency === "SAR" ? (ar ? "ر.س" : "SAR") : q?.currency === "USD" ? "$" : q?.currency ?? "";
  const unit = it.unit === "oz" ? (ar ? "/أونصة" : "/oz") : it.unit === "lb" ? (ar ? "/رطل" : "/lb") : it.unit === "g" ? (ar ? "/جرام" : "/g") : "";
  const range = q?.day_high != null && q?.day_low != null && q.day_high > q.day_low && q.price != null
    ? Math.min(100, Math.max(0, ((q.price - q.day_low) / (q.day_high - q.day_low)) * 100)) : null;
  return (
    <article className={`live-tile ${dir}${compact ? " compact" : ""}`} aria-label={`${ar ? it.ar : it.en} ${q?.price ?? ""}`}>
      {fl && <span key={fl.k} className={`flash ${fl.dir}`} aria-hidden="true" />}
      <div className="row" style={{ justifyContent: "space-between", gap: 6, flexWrap: "nowrap" }}>
        <div className="stack" style={{ gap: 0, minWidth: 0 }}>
          <b className="nm">{ar ? it.ar : it.en}</b>
          <span className="pixel ltr muted sym">{it.derived ? (ar ? "محسوب" : "calculated") : it.symbol}</span>
        </div>
        <span className={`dotlive${fresh ? " on" : ""}`} title={fresh ? (ar ? "مباشر" : "live") : (ar ? "آخر سعر" : "last price")} />
      </div>
      <div className="px ltr">{q?.price != null ? <>{fmtNum(q.price, "en", { maximumFractionDigits: q.price < 10 ? 3 : 2, minimumFractionDigits: 2 })}<small> {cur}{unit}</small></> : "…"}</div>
      <div className={`chg ltr ${dir}`}>{ch != null ? `${ch >= 0 ? "▲" : "▼"} ${fmtNum(Math.abs(q!.change ?? 0), "en", { maximumFractionDigits: 2 })} (${ch >= 0 ? "+" : "−"}${fmtNum(Math.abs(ch), "en", { maximumFractionDigits: 2 })}%)` : ""}</div>
      {!compact && <Spark path={path} up={(ch ?? 0) >= 0} />}
      {!compact && range != null && (
        <div className="range" title={ar ? "مدى اليوم" : "Day range"}><i style={{ insetInlineStart: `${range}%` }} /></div>
      )}
      <div className="row" style={{ justifyContent: "space-between", gap: 6 }}>
        <span className="muted when">{ago(q?.time, lang)}</span>
        {(onAnalyze || onAlerts) && <span className="row" style={{ gap: 4 }}>
          {onAlerts && <AlertButton symbol={it.symbol} price={q?.price} onChange={onAlerts} />}
        </span>}
        {onAnalyze && <span className="row" style={{ gap: 4 }}>
          <StarButton ticker={it.symbol} />
          <button className="ghost btn mini" onClick={onAnalyze}>{ar ? "حلّله" : "Analyse"}</button>
        </span>}
        {fav && null}
      </div>
    </article>
  );
}

function Spark({ path, up }: { path?: number[]; up: boolean }) {
  if (!path || path.length < 2) return <svg className="tickspark" viewBox="0 0 100 26" aria-hidden="true" />;
  const lo = Math.min(...path), hi = Math.max(...path);
  const pts = path.map((v, i) => `${(i / (path.length - 1)) * 100},${24 - ((v - lo) / (hi - lo || 1)) * 22}`).join(" ");
  return <svg className="tickspark" viewBox="0 0 100 26" preserveAspectRatio="none" aria-hidden="true"><polyline points={pts} fill="none" stroke={up ? "var(--buy)" : "var(--sell)"} strokeWidth="2" vectorEffect="non-scaling-stroke" /></svg>;
}
