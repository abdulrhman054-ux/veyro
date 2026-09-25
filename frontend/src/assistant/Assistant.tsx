import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "../api";
import { SpriteSvg, charColor } from "../art/Sprite";
import { click, pop, speakBlips } from "../audio";
import { RATING, charName, fmtDate, fmtNum, fmtPct, type CharKey, type Lang } from "../i18n";
import { usePrefs } from "../prefs";

export type Quote = { ticker: string; last: number | null; prev: number | null; change: number | null };
type Alert = { id: number; ts: string; kind: string; ticker: string | null; character: CharKey; text_ar: string; text_en: string; link: string | null; ref: string | null; read: number };
export type AssistPrefs = { morning_enabled: boolean; morning_time: string; alerts_enabled: boolean; alert_threshold: number; alerts_news: boolean; morning_count?: number };

type Ctx = { favorites: string[]; toggleFavorite: (t: string) => void; isFav: (t: string) => boolean; quotes: Quote[]; refreshQuotes: () => void };
const C = createContext<Ctx | null>(null);

export function AssistantProvider({ children }: { children: ReactNode }) {
  const { prefs } = usePrefs();
  const [favorites, setFavorites] = useState<string[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const refreshQuotes = useCallback(() => { api.get<{ quotes: Quote[] }>("/api/favorites/quotes").then((r) => setQuotes(r.quotes)).catch(() => {}); }, []);
  useEffect(() => { api.get<{ favorites: string[] }>("/api/favorites").then((r) => setFavorites(r.favorites)).catch(() => {}); refreshQuotes();
    const h = setInterval(refreshQuotes, 120_000); return () => clearInterval(h); }, [refreshQuotes]);
  // The scheduler writes alerts and morning reports in the user's current language.
  useEffect(() => { api.put("/api/assistant", { ui_lang: prefs.lang }).catch(() => {}); }, [prefs.lang]);
  const toggleFavorite = (t: string) => {
    click();
    const on = favorites.includes(t);
    (on ? api.del<{ favorites: string[] }>(`/api/favorites/${t}`) : api.post<{ favorites: string[] }>(`/api/favorites/${t}`))
      .then((r) => { setFavorites(r.favorites); refreshQuotes(); }).catch(() => {});
  };
  return <C.Provider value={{ favorites, toggleFavorite, isFav: (t) => favorites.includes(t), quotes, refreshQuotes }}>{children}</C.Provider>;
}

export function useAssistant() {
  const c = useContext(C);
  if (!c) throw new Error("AssistantProvider missing");
  return c;
}

/** ☆/★ button next to a ticker. */
export function StarButton({ ticker }: { ticker: string }) {
  const { isFav, toggleFavorite } = useAssistant();
  const { prefs } = usePrefs();
  const on = isFav(ticker);
  const label = prefs.lang === "ar" ? (on ? "إزالة من المفضلة" : "إضافة للمفضلة") : (on ? "Remove from favourites" : "Add to favourites");
  return (
    <button className="pill btn" aria-pressed={on} aria-label={label} title={label} onClick={() => ticker && toggleFavorite(ticker)}
      style={{ width: 42, padding: 0, color: on ? "#E0A020" : "var(--muted)", fontSize: 20 }}>{on ? "★" : "☆"}</button>
  );
}

/** Office strip: every favourite with today's real move; tap to analyse it. */
export function FavoritesStrip({ onPick }: { onPick: (t: string) => void }) {
  const { quotes } = useAssistant();
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  if (!quotes.length) return null;
  return (
    <div className="favstrip" role="group" aria-label={lang === "ar" ? "أسهمي المفضلة" : "My favourites"}>
      <b style={{ fontSize: 14 }}>★ {lang === "ar" ? "أسهمي المفضلة" : "My favourites"}</b>
      {quotes.map((q) => (
        <button key={q.ticker} className="chip mkt btn" style={{ cursor: "pointer", height: 34 }} onClick={() => onPick(q.ticker)}>
          <b className="pixel ltr">{q.ticker}</b>
          {q.change != null
            ? <span className={`ltr ${q.change >= 0 ? "pos" : "neg"}`}>{q.change >= 0 ? "▲" : "▼"} {fmtPct(q.change, lang)}</span>
            : <span className="muted">{lang === "ar" ? "غير متوفر" : "unavailable"}</span>}
        </button>
      ))}
      <span className="muted" style={{ fontSize: 12 }}>Yahoo Finance</span>
    </div>
  );
}

/** Header bell: alerts from Pip (big moves), Albie (big news) and Leo (morning report). Also OS notifications. */
export function AlertsBell({ onOpenMorning }: { onOpenMorning: () => void }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const [rows, setRows] = useState<Alert[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const seen = useRef<number>(-1);
  const load = useCallback(() => {
    api.get<{ alerts: Alert[]; unread: number }>("/api/alerts").then((r) => {
      setRows(r.alerts); setUnread(r.unread);
      const newest = r.alerts[0]?.id ?? 0;
      if (seen.current >= 0 && newest > seen.current) {
        r.alerts.filter((a) => a.id > seen.current).reverse().forEach((a) => {
          const text = lang === "ar" ? a.text_ar : a.text_en;
          pop(); speakBlips(a.character, text);
          try { if ("Notification" in window && Notification.permission === "granted") new Notification(charName(a.character, lang), { body: text }); } catch { /* ignore */ }
        });
      }
      seen.current = newest;
    }).catch(() => {});
  }, [lang]);
  useEffect(() => { load(); const h = setInterval(load, 30_000); return () => clearInterval(h); }, [load]);
  const toggle = () => { click(); setOpen(!open); if (!open && unread) api.post("/api/alerts/read").then(load).catch(() => {}); };
  return (
    <div style={{ position: "relative" }}>
      <button className="pill btn" onClick={toggle} aria-expanded={open} aria-label={lang === "ar" ? `التنبيهات (${unread} جديدة)` : `Alerts (${unread} new)`}>
        <svg width="18" height="18" viewBox="0 0 10 10" shapeRendering="crispEdges" aria-hidden="true"><path fill="currentColor" d="M4 0h2v1h1v1h1v4h1v1H1V6h1V2h1V1h1zM4 8h2v1H4z" /></svg>
        {unread > 0 && <span className="badge-dot">{unread}</span>}
      </button>
      {open && (
        <div className="alerts-pop" role="dialog" aria-label={lang === "ar" ? "التنبيهات" : "Alerts"}>
          <b style={{ fontSize: 17 }}>{lang === "ar" ? "التنبيهات" : "Alerts"}</b>
          {rows.length === 0 && <p className="muted" style={{ margin: 0 }}>{lang === "ar" ? "ما فيه تنبيهات للحين. أضف أسهم للمفضلة ★ وبنراقبها لك." : "No alerts yet. Star ★ some favourites and we'll watch them for you."}</p>}
          {rows.slice(0, 15).map((a) => (
            <div key={a.id} className="alert-row">
              <SpriteSvg name={a.character} px={1} />
              <div className="stack" style={{ gap: 2, minWidth: 0 }}>
                <span style={{ fontSize: 14, lineHeight: 1.6 }}>{lang === "ar" ? a.text_ar : a.text_en}</span>
                <span className="muted" style={{ fontSize: 12 }}>{fmtDate(a.ts, lang)}
                  {a.link && <> · <a href={a.link} target="_blank" rel="noopener noreferrer">{lang === "ar" ? "افتح الخبر" : "Open story"}</a></>}
                  {a.kind === "morning" && a.ref && <> · <button className="linkish" onClick={() => { setOpen(false); onOpenMorning(); }}>{lang === "ar" ? "شوف النتيجة" : "See results"}</button></>}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Settings card: morning report + alerts, in plain words. */
export function DailyAssistantSettings() {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const ar = lang === "ar";
  const { favorites } = useAssistant();
  const [p, setP] = useState<AssistPrefs | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [perm, setPerm] = useState(typeof Notification !== "undefined" ? Notification.permission : "denied");
  useEffect(() => { api.get<AssistPrefs>("/api/assistant").then(setP).catch(() => {}); }, []);
  if (!p) return null;
  const put = (x: Partial<AssistPrefs>) => api.put<AssistPrefs>("/api/assistant", x).then(setP).catch(() => {});
  const runNow = async () => {
    setMsg(null);
    try {
      const r = await api.post<{ scan_id: string }>("/api/assistant/morning/run");
      setMsg(ar ? "بدأ التقرير الصباحي! ننقلك للمكتب…" : "Morning report started! Taking you to the Office…");
      // The shell follows the scan in the Office (same path as the alert's "See results").
      window.dispatchEvent(new CustomEvent("veyro:follow-scan", { detail: r.scan_id }));
    }
    catch (e) { setMsg(e instanceof ApiError && e.code === "no_favorites" ? (ar ? "أضف أسهم للمفضلة ★ أول." : "Star ★ some favourites first.") : (ar ? "يحتاج مفتاح النموذج." : "Needs a model key.")); }
  };
  return (
    <section className="card stack" aria-labelledby="daily-h">
      <div className="row"><SpriteSvg name="Leo" px={2} /><h2 id="daily-h" style={{ fontSize: 22 }}>{ar ? "المساعد اليومي" : "Daily assistant"}</h2></div>
      <p className="muted" style={{ margin: 0 }}>{ar ? `يشتغل على أسهمك المفضلة (${favorites.length}). أضفها بزر ★ في المكتب.` : `Works on your favourites (${favorites.length}). Add them with ★ in the Office.`}</p>
      <label className="toggle"><span>{ar ? "تقرير صباحي تلقائي" : "Automatic morning report"}</span>
        <input type="checkbox" checked={p.morning_enabled} onChange={(e) => put({ morning_enabled: e.target.checked })} /></label>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <label className="row" style={{ gap: 8 }}><span className="label">{ar ? "الوقت (بتوقيت جهازك)" : "Time (your computer's time)"}</span>
          <input className="field ltr" type="time" style={{ height: 40 }} value={p.morning_time} onChange={(e) => put({ morning_time: e.target.value })} /></label>
        <button className="ghost btn" onClick={runNow}>{ar ? "شغّله الآن" : "Run it now"}</button>
      </div>
      <label className="row" style={{ justifyContent: "space-between" }}><span className="label">{ar ? "كم سهم من المفضلة يحلل كل صباح" : "How many favourites to analyse each morning"}</span>
        <input className="field ltr" type="number" min={1} max={50} step={1} style={{ width: 100, height: 40 }} value={p.morning_count ?? 5}
          onChange={(e) => { const n = Math.round(Number(e.target.value)); if (n >= 1 && n <= 50) void put({ morning_count: n }); }} /></label>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>{ar ? `كل سهم جلسة كاملة، فالتكلفة تتضاعف بعدد الأسهم (حالياً ${Math.min(favorites.length, p.morning_count ?? 5)}). أيام التداول فقط، والتطبيق لازم يكون مفتوح أو في شريط المهام.` : `Each stock is a full session, so cost multiplies by the count (currently ${Math.min(favorites.length, p.morning_count ?? 5)}). Trading days only, and the app must be open or in the tray.`}</p>
      <label className="toggle"><span>{ar ? "تنبيهات الحركة القوية (بيب)" : "Big-move alerts (Pip)"}</span>
        <input type="checkbox" checked={p.alerts_enabled} onChange={(e) => put({ alerts_enabled: e.target.checked })} /></label>
      <label className="row" style={{ justifyContent: "space-between" }}><span className="label">{ar ? "نسبة الحركة للتنبيه (%)" : "Move that triggers an alert (%)"}</span>
        <input className="field ltr" type="number" min={1} max={20} step={0.5} style={{ width: 100, height: 40 }} value={p.alert_threshold} onChange={(e) => put({ alert_threshold: Number(e.target.value) })} /></label>
      <label className="toggle"><span>{ar ? "تنبيهات الأخبار الكبيرة (ألبي)" : "Big-news alerts (Albie)"}</span>
        <input type="checkbox" checked={p.alerts_news} onChange={(e) => put({ alerts_news: e.target.checked })} /></label>
      {perm !== "granted" && typeof Notification !== "undefined" && (
        <button className="ghost btn" style={{ alignSelf: "flex-start" }} onClick={() => Notification.requestPermission().then(setPerm)}>
          {ar ? "اسمح بإشعارات ويندوز" : "Allow Windows notifications"}</button>
      )}
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>{ar ? "التنبيهات مجانية (أسعار Yahoo وعناوين الصحف القوية)، وما تستهلك النموذج." : "Alerts are free (Yahoo prices and strong-publisher headlines) and use no model tokens."}</p>
      {msg && <div className="warnstrip" role="status">{msg}</div>}
    </section>
  );
}

/** Ask the team a question about a finished session: the right character answers from its notes. */
export function AskTeam({ sessionId, onAnswer, compact = false }: { sessionId: string; onAnswer?: (c: CharKey, text: string) => void; compact?: boolean }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const ar = lang === "ar";
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<{ question: string; character: CharKey; answer: string; lang: string }[]>([]);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (!compact) api.get<{ qa: { question: string; character: CharKey; answer: string; lang: string }[] }>(`/api/sessions/${sessionId}/qa`).then((r) => setLog(r.qa)).catch(() => {}); }, [sessionId, compact]);
  const send = async () => {
    if (q.trim().length < 2) return;
    setBusy(true); setErr(null); click();
    try {
      const r = await api.post<{ character: CharKey; answer: string; question: string }>(`/api/sessions/${sessionId}/ask`, { question: q.trim(), lang });
      setLog((l) => [...l, { ...r, lang }]); setQ(""); onAnswer?.(r.character, r.answer);
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "";
      setErr(code === "demo" ? (ar ? "هذي جلسة تجريبية، ما فيها تحليل نقدر نجاوب منه." : "This is a demo session, there's no analysis to answer from.")
        : code === "no_key" ? (ar ? "يحتاج مفتاح النموذج." : "Needs a model key.") : (ar ? "ما قدرنا نجاوب الحين." : "Couldn't answer right now."));
    }
    setBusy(false);
  };
  return (
    <section className={compact ? "stack" : "card stack"} style={{ gap: 8 }}>
      {!compact && <h2 style={{ fontSize: 19 }}>{ar ? "اسأل الفريق" : "Ask the team"}</h2>}
      {!compact && log.filter((x) => x.lang === lang).map((x, i) => (
        <div key={i} className="stack" style={{ gap: 4 }}>
          <div className="muted" style={{ fontWeight: 700 }}>❓ {x.question}</div>
          <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
            <SpriteSvg name={x.character} px={2} />
            <div><span className="tagname" style={{ background: charColor(x.character), fontSize: 13 }}>{charName(x.character, lang)}</span>
              <p style={{ margin: "4px 0 0", lineHeight: 1.7 }}>{x.answer}</p></div>
          </div>
        </div>
      ))}
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input className="field" style={{ flex: 1, minWidth: 0, height: 42 }} value={q} maxLength={400} placeholder={ar ? "مثال: ليش مو شراء؟ وش أكبر خطر؟" : "e.g. Why not a buy? What's the biggest risk?"}
          onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void send(); }} aria-label={ar ? "اسأل الفريق" : "Ask the team"} />
        <button className="primary btn" style={{ height: 42, fontSize: 15 }} disabled={busy || q.trim().length < 2} onClick={send}>{busy ? "…" : (ar ? "اسأل" : "Ask")}</button>
      </div>
      {err && <div className="warnstrip" role="alert">{err}</div>}
      {!compact && <p className="muted" style={{ margin: 0, fontSize: 13 }}>{ar ? "الجواب من ملاحظات الجلسة نفسها فقط، وإذا ما فيها الجواب نقول لك." : "Answers come only from this session's notes; if they don't cover it, we say so."}</p>}
    </section>
  );
}

type Block = { sessions: number; scored: number; hits: number; by_rating: Record<string, { count: number; hits: number }>; by_ticker: Record<string, { count: number; hits: number; excess: number }> };

/** Bruno's monthly learning card: plain numbers, no sugar-coating. */
export function BrunoCard() {
  const { prefs } = usePrefs();
  const lang: Lang = prefs.lang;
  const ar = lang === "ar";
  const [d, setD] = useState<{ month: string; this_month: Block; all_time: Block; framework: { settled: number; mean_alpha: number | null } } | null>(null);
  useEffect(() => { api.get<typeof d>("/api/learning").then(setD).catch(() => {}); }, []);
  if (!d) return null;
  const m = d.this_month.scored ? d.this_month : d.all_time;
  const scope = d.this_month.scored ? (ar ? "هذا الشهر" : "this month") : (ar ? "من البداية" : "all time");
  const tick = Object.entries(m.by_ticker).sort((a, b) => b[1].excess - a[1].excess);
  const pct = m.scored ? m.hits / m.scored : null;
  return (
    <section className="card cream stack" style={{ gap: 8 }}>
      <b style={{ fontSize: 17 }}>{ar ? `بطاقة برونو (${scope})` : `Bruno's card (${scope})`}</b>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <div><div className="label">{ar ? "جلسات حقيقية" : "Real sessions"}</div><b className="pixel ltr" style={{ fontSize: 22 }}>{m.sessions}</b></div>
        <div><div className="label">{ar ? "أصاب الاتجاه" : "Direction right"}</div><b className="pixel ltr" style={{ fontSize: 22 }}>{pct == null ? "—" : `${m.hits}/${m.scored} · ${fmtPct(pct, lang)}`}</b></div>
      </div>
      {Object.entries(m.by_rating).map(([r, s]) => (
        <div key={r} className="row" style={{ justifyContent: "space-between" }}>
          <span className={`vchip ${RATING[r]?.tone ?? "none"}`}>{RATING[r] ? (ar ? RATING[r].ar : RATING[r].en) : r}</span>
          <span className="pixel ltr">{s.hits}/{s.count}</span>
        </div>
      ))}
      {tick.length > 0 && <div style={{ fontSize: 14 }}>{ar ? "أفضل سهم مقابل المؤشر:" : "Best vs benchmark:"} <b className="pixel ltr">{tick[0][0]} {fmtPct(tick[0][1].excess / tick[0][1].count, lang)}</b>
        {tick.length > 1 && <> · {ar ? "أضعف:" : "weakest:"} <b className="pixel ltr">{tick.at(-1)![0]} {fmtPct(tick.at(-1)![1].excess / tick.at(-1)![1].count, lang)}</b></>}</div>}
      <div style={{ fontSize: 14 }}>{ar ? "ذاكرة الإطار: قرارات مسوّاة" : "Framework memory: settled calls"} <b className="ltr">{fmtNum(d.framework.settled, lang)}</b>
        {d.framework.mean_alpha != null && <> · {ar ? "متوسط الألفا" : "mean alpha"} <b className={`ltr ${d.framework.mean_alpha >= 0 ? "pos" : "neg"}`}>{fmtPct(d.framework.mean_alpha, lang)}</b></>}</div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>{ar
        ? (m.scored ? "الأرقام ما تكذب. نكمّل نراقب… غرر" : "للحين ما عندي قرارات اتجاهية كافية أحكم عليها. غرر…")
        : (m.scored ? "Numbers don't lie. We keep watching… grr" : "Not enough directional calls to judge yet. grr…")}</p>
    </section>
  );
}
