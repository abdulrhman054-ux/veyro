import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, openStream, type Candidate, type Settings } from "../api";
import { charColor } from "../art/Sprite";
import { click, startJingle, unlockAudio } from "../audio";
import { CHAR_ORDER, RATING, charName, fmtNum, fmtPct, fmtUsd, type CharKey } from "../i18n";
import { usePrefs } from "../prefs";
import { IdleBox, SpeechBox, VerdictBox } from "./Dialog";
import { RoomScene, Stage } from "./Room";
import { useSession, type Line } from "./useSession";
import { useLineText } from "./lineText";
import { AskTeam, FavoritesStrip, StarButton } from "../assistant/Assistant";
import { moodFrom } from "./mood";
import type { History } from "../api";

type Mode = "single" | "watchlist" | "scan";
type ScanView = { id: string; tickers: string[]; source: Candidate[] | null; sessions: string[]; results: Record<number, string | null>;
  ranking: { ticker: string; rating: string | null; session_id: string; status: string }[] | null; done: boolean };

const TICKER = /^[A-Z][A-Z0-9.\-]{0,9}$/;

export function Office({ settings, onOpenReport, onBusy, marketOpen, renderVerdictExtra, pendingStart, pendingScan }: { settings: Settings | null; onOpenReport: (id: string) => void; onBusy: (b: boolean) => void; marketOpen: boolean | null;
  renderVerdictExtra?: (sessionId: string, ticker: string, rating: string, demo: boolean) => React.ReactNode;
  pendingStart?: { ticker: string; trade_date: string; nonce: number } | null;
  pendingScan?: { id: string; nonce: number } | null }) {
  const { t, prefs } = usePrefs();
  const lang = prefs.lang;
  const [mode, setMode] = useState<Mode>("single");
  const [ticker, setTicker] = useState("NVDA");
  const [tradeDate, setTradeDate] = useState("");   // empty = today (the framework analyses point-in-time for past dates)
  const [list, setList] = useState("AAPL, MSFT, NVDA");
  const [screener, setScreener] = useState("most_actives");
  const [count, setCount] = useState(3);
  const [screeners, setScreeners] = useState<Record<string, { ar: string; en: string }>>({});
  const [preview, setPreview] = useState<Candidate[] | null>(null);
  const [previewState, setPreviewState] = useState<"idle" | "loading" | "none">("idle");
  const hasKey = !!settings && settings.keys[settings.provider]?.present;
  const [demo, setDemo] = useState<boolean>(false);
  useEffect(() => { if (settings && !hasKey) setDemo(true); }, [settings, hasKey]);
  const [err, setErr] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [scan, setScan] = useState<ScanView | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const { state, next, showVerdict, say } = useSession(sessionId);
  const [spy, setSpy] = useState<History | null>(null);
  useEffect(() => {
    const load = () => api.get<History>("/api/market/history/SPY").then(setSpy).catch(() => setSpy(null));
    load(); const h = setInterval(load, 5 * 60_000); return () => clearInterval(h);
  }, []);
  // The office mood follows the stock under discussion, or the whole market (SPY) between sessions.
  const mood = useMemo(() => moodFrom(state.market ?? (sessionId ? null : spy)), [state.market, spy, sessionId]);

  useEffect(() => { api.get<{ screeners: Record<string, { ar: string; en: string }> }>("/api/market/screeners").then((r) => setScreeners(r.screeners)).catch(() => {}); }, []);

  const running = !!sessionId && (!state.ended || !!state.current || state.queue.length > 0) || (!!scan && !scan.done);
  useEffect(() => { onBusy(running); }, [running, onBusy]);

  // Show Leo's verdict once every queued line has been spoken.
  useEffect(() => {
    if (state.verdict && !state.current && state.queue.length === 0 && !state.verdictShown) showVerdict();
  }, [state.verdict, state.current, state.queue.length, state.verdictShown, showVerdict]);

  // Scans: move to the next ticker only after the current one has been fully shown.
  const scanIdx = scan ? scan.sessions.indexOf(sessionId ?? "") : -1;
  useEffect(() => {
    if (!scan || scanIdx < 0) return;
    const finishedShowing = state.ended && !state.current && state.queue.length === 0 && (state.verdictShown || !state.verdict);
    const nextSid = scan.sessions[scanIdx + 1];
    if (finishedShowing && nextSid) {
      const h = window.setTimeout(() => { setSessionId(nextSid); setStarting(`${scan.tickers[scanIdx + 1]} · ${scanIdx + 2}/${scan.tickers.length}`); startJingle(); }, 4500);
      return () => clearTimeout(h);
    }
  }, [scan, scanIdx, state.ended, state.current, state.queue.length, state.verdictShown, state.verdict]);

  const firstScanSession = scan?.sessions[0];
  useEffect(() => {
    if (!scan || !firstScanSession || scan.sessions.includes(sessionId ?? "")) return;
    setSessionId(firstScanSession); setStarting(`${scan.tickers[0]} · 1/${scan.tickers.length}`); startJingle();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstScanSession]);

  const scanClose = useRef<(() => void) | null>(null);
  useEffect(() => () => scanClose.current?.(), []);

  const estimate = useMemo(() => {
    if (!settings) return null;
    if (demo) return t.free;
    const n = mode === "single" ? 1 : mode === "watchlist" ? parseList(list).length || 1 : count;
    const e = settings.estimate;
    if (!e.known || e.low === null || e.high === null) return t.estimateUnknown;
    return `${fmtUsd(e.low * n, lang)} – ${fmtUsd(e.high * n, lang)}`;
  }, [settings, demo, mode, list, count, lang, t]);

  async function start() {
    setErr(null); unlockAudio(); click();
    try {
      scanClose.current?.(); setScan(null);
      if (mode === "single") {
        const tk = ticker.trim().toUpperCase();
        if (!TICKER.test(tk)) { setErr(t.invalidTicker); return; }
        const r = await api.post<{ id: string }>("/api/sessions", { ticker: tk, lang, demo, trade_date: tradeDate || null });
        setStarting(tk); startJingle(); setSessionId(r.id);
      } else {
        const body = mode === "watchlist" ? { kind: "watchlist", tickers: parseList(list), lang, demo } : { kind: "screener", screener, count, lang, demo };
        if (mode === "watchlist" && (body.tickers as string[]).some((x) => !TICKER.test(x))) { setErr(t.invalidTicker); return; }
        const r = await api.post<{ id: string; tickers: string[]; source: Candidate[] | null }>("/api/scans", body);
        const view: ScanView = { id: r.id, tickers: r.tickers, source: r.source, sessions: [], results: {}, ranking: null, done: false };
        setScan(view);
        scanClose.current = openStream(`/ws/scans/${r.id}`, (ev) => {
          setScan((s) => {
            if (!s) return s;
            if (ev.type === "scan_session") {
              const sessions = [...s.sessions]; sessions[ev.index] = ev.session_id;
              return { ...s, sessions };
            }
            if (ev.type === "scan_result") return { ...s, results: { ...s.results, [ev.index]: ev.rating } };
            if (ev.type === "scan_ranked") return { ...s, ranking: ev.ranking };
            if (ev.type === "end") return { ...s, done: true };
            return s;
          });
        });
      }
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "error";
      setErr(code === "invalid_ticker" ? t.invalidTicker : code === "screener_unavailable" ? t.unavailable : t.error);
    }
  }

  // "Resume" from History: same ticker and date, the framework continues from its checkpoint.
  useEffect(() => {
    if (!pendingStart) return;
    setMode("single"); setTicker(pendingStart.ticker); setTradeDate(pendingStart.trade_date); setDemo(false);
    api.post<{ id: string }>("/api/sessions", { ticker: pendingStart.ticker, lang, demo: false, trade_date: pendingStart.trade_date })
      .then((r) => { setStarting(pendingStart.ticker); startJingle(); setSessionId(r.id); }).catch(() => setErr(t.error));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingStart?.nonce]);

  // A scan started outside the office (the morning report): follow it here.
  useEffect(() => {
    if (!pendingScan) return;
    scanClose.current?.();
    api.get<{ tickers: string[] }>(`/api/scans/${pendingScan.id}`).then((sc) => {
      setScan({ id: pendingScan.id, tickers: sc.tickers, source: null, sessions: [], results: {}, ranking: null, done: false });
      scanClose.current = openStream(`/ws/scans/${pendingScan.id}`, (ev) => setScan((s) => {
        if (!s) return s;
        if (ev.type === "scan_session") { const sessions = [...s.sessions]; sessions[ev.index] = ev.session_id; return { ...s, sessions }; }
        if (ev.type === "scan_result") return { ...s, results: { ...s.results, [ev.index]: ev.rating } };
        if (ev.type === "scan_ranked") return { ...s, ranking: ev.ranking };
        if (ev.type === "end") return { ...s, done: true };
        return s;
      }));
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingScan?.nonce]);

  async function stop() {
    if (scan) await api.post(`/api/scans/${scan.id}/cancel`).catch(() => {});
    if (sessionId) await api.post(`/api/sessions/${sessionId}/cancel`).catch(() => {});
  }

  async function loadPreview() {
    setPreviewState("loading");
    try {
      const r = await api.get<{ available: boolean; candidates: Candidate[] }>(`/api/market/screen/${screener}?count=${count}`);
      setPreview(r.available ? r.candidates : []); setPreviewState(r.available ? "idle" : "none");
    } catch { setPreview([]); setPreviewState("none"); }
  }
  useEffect(() => { setPreview(null); setPreviewState("idle"); }, [screener, count]);

  const isDemo = state.mode === "demo" || (!sessionId && demo);
  const verdictExtra = sessionId && state.verdict && state.ticker && renderVerdictExtra
    ? renderVerdictExtra(sessionId, state.ticker, state.verdict.rating, state.mode === "demo") : null;
  const SESSION: CharKey[] = [...CHAR_ORDER.slice(0, 7), "Albie", "Leo"];   // speaking order in a session
  const doneCount = SESSION.filter((c) => state.agents[c] === "done").length;
  const attending = SESSION.filter((c) => state.agents[c] !== "break").length;
  const scanDone = scan?.done && scan.ranking && (scanIdx === scan.sessions.length - 1) && state.verdictShown;

  return (
    <>
      <div className="startbar" role="group" aria-label={t.start}>
        <div className="seg" role="group">
          {(["single", "watchlist", "scan"] as Mode[]).map((m) => (
            <button key={m} aria-pressed={mode === m} onClick={() => { setMode(m); click(); }} disabled={running}>{t[m]}</button>
          ))}
        </div>
        {mode === "single" && (<>
          <label className="row" style={{ gap: 8 }}>
            <span style={{ fontWeight: 800 }}>{t.ticker}</span>
            <input className="field pixel ticker ltr" value={ticker} maxLength={15} onChange={(e) => setTicker(e.target.value.toUpperCase())}
              onKeyDown={(e) => { if (e.key === "Enter" && !running) void start(); }} aria-invalid={!!err} disabled={running} />
          </label>
          <StarButton ticker={ticker.trim().toUpperCase()} />
          <label className="row" style={{ gap: 6 }} title={lang === "ar" ? "اتركه فاضي لتحليل اليوم" : "Leave empty to analyse today"}>
            <span style={{ fontWeight: 700, fontSize: 14 }}>{lang === "ar" ? "بتاريخ سابق؟" : "Past date?"}</span>
            <input className="field ltr" type="date" style={{ height: 40, width: 150, fontSize: 14 }} value={tradeDate}
              max={new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date())} onChange={(e) => setTradeDate(e.target.value)} disabled={running} />
          </label>
        </>)}
        {mode === "watchlist" && (
          <label className="row" style={{ gap: 8, flex: 1, minWidth: 260 }}>
            <span style={{ fontWeight: 800 }}>{t.tickers}</span>
            <input className="field pixel ltr" style={{ flex: 1, minWidth: 180 }} value={list} onChange={(e) => setList(e.target.value.toUpperCase())} disabled={running} />
          </label>
        )}
        {mode === "scan" && (
          <>
            <label className="row" style={{ gap: 8 }}>
              <span style={{ fontWeight: 800 }}>{t.screener}</span>
              <select className="field" value={screener} onChange={(e) => setScreener(e.target.value)} disabled={running}>
                {Object.entries(screeners).map(([k, v]) => <option key={k} value={k}>{v[lang]}</option>)}
              </select>
            </label>
            <label className="row" style={{ gap: 8 }}>
              <span style={{ fontWeight: 800 }}>{t.candidates}</span>
              <select className="field" value={count} onChange={(e) => setCount(Number(e.target.value))} disabled={running}>
                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <button className="ghost btn" onClick={loadPreview} disabled={running || previewState === "loading"}>{t.preview}</button>
          </>
        )}
        <label className="check"><input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} disabled={running} />{t.demoMode}</label>
        {prefs.showCost && estimate && <span className="estimate">{t.estimate}: <b className="ltr">{estimate}</b></span>}
        <span style={{ flex: 1 }} />
        {running
          ? <button className="ghost btn" onClick={stop}>{t.stop}</button>
          : <button className="primary btn" onClick={start}>{mode === "single" ? (sessionId ? t.again : t.start) : mode === "watchlist" ? t.startList : t.startScan}</button>}
      </div>
      {err && <div className="warnstrip" role="alert">{err}</div>}
      {!running && <FavoritesStrip onPick={(tk) => { setMode("single"); setTicker(tk); click(); }} />}
      {mode === "scan" && preview && !running && (
        <div className="card cream" style={{ padding: 14 }}>
          {preview.length === 0 ? <span>{t.unavailable}</span> : (
            <div className="row" style={{ gap: 8 }}>
              <span className="label">{t.candidatesFrom} Yahoo Finance · {fmtTime(preview[0].as_of, lang)}</span>
              {preview.map((c) => (
                <span key={c.symbol} className="chip mkt" title={c.name ?? ""}>
                  <b className="pixel ltr">{c.symbol}</b>
                  <span className="ltr">{c.price != null ? fmtUsd(c.price, lang) : t.unavailable}</span>
                  {c.change_pct != null && <span className={`ltr ${c.change_pct >= 0 ? "pos" : "neg"}`}>{fmtPct(c.change_pct / 100, lang)}</span>}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="office">
        <Stage>
          <RoomScene ticker={state.ticker} market={state.market ?? (sessionId ? null : spy)} marketLoaded={state.marketLoaded}
            demo={isDemo} agents={state.agents} lang={lang} starting={starting} mood={mood} marketOpen={marketOpen}>
            {state.current ? <SpeechBox key={state.current.id} line={state.current} lang={lang} onDone={next} />
              : state.verdictShown && state.verdict ? <VerdictBox v={state.verdict} lang={lang} demo={state.mode === "demo"} sessionId={sessionId} onOpenReport={() => sessionId && onOpenReport(sessionId)} extra={verdictExtra} />
              : !sessionId ? <IdleBox lang={lang} text={demo ? `${t.welcome} ${t.welcomeDemo}` : t.welcome} />
              : null}
          </RoomScene>
        </Stage>

        <aside className="side" aria-label={t.minutes}>
          {scan && (
            <div className="card" style={{ padding: 16 }}>
              <div className="row" style={{ justifyContent: "space-between" }}><h2 style={{ fontSize: 19 }}>{t.scanProgress}</h2><span className="pixel ltr muted">{Object.keys(scan.results).length} / {scan.tickers.length}</span></div>
              <ol className="board-rank" style={{ margin: "10px 0 0", padding: 0 }}>
                {scan.tickers.map((tk, i) => {
                  const r = scan.results[i];
                  const on = scan.sessions[i] === sessionId;
                  return (
                    <li key={tk} style={{ outline: on ? "3px solid var(--orange)" : "none" }}>
                      <b className="pixel ltr" style={{ minWidth: 60 }}>{tk}</b>
                      {r ? <span className={`vchip ${RATING[r]?.tone ?? "none"}`}>{lang === "ar" ? RATING[r]?.ar : RATING[r]?.en}</span>
                        : <span className="muted">{on ? t.nowAnalyzing : "…"}</span>}
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
          <div className="minutes" style={{ maxHeight: scan ? 480 : 740 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <h2 style={{ fontSize: 21 }}>{t.minutes}</h2>
              <span className="pixel ltr muted">{doneCount} / {attending}</span>
            </div>
            <div className="dots" aria-hidden="true">
              {SESSION.map((c) => (
                <span key={c} title={charName(c, lang)} className={`dot${state.agents[c] === "thinking" || state.agents[c] === "speaking" ? " now" : ""}`}
                  style={state.agents[c] === "done" ? { background: charColor(c) } : state.agents[c] === "break" ? { opacity: 0.3 } : undefined} />
              ))}
            </div>
            {state.portfolioUsed && <div className="costrow"><span>{lang === "ar" ? "ليو يعرف محفظتك الحالية" : "Leo knows your current holdings"}</span><span>✓</span></div>}
            {state.assetType === "crypto" && <div className="costrow"><span>{lang === "ar" ? "عملة رقمية: بيني في استراحة (ما فيه قوائم مالية)" : "Crypto: Benny is on a break (no financial statements)"}</span></div>}
            {mood.change != null && (
              <div className="costrow" title={t.source + ": Yahoo Finance"}>
                <span>{sessionId ? t.moodStock : t.moodMarket}</span>
                <span className={`pixel ltr ${mood.change >= 0 ? "pos" : "neg"}`}>{mood.ticker} {fmtPct(mood.change, lang)} · {mood.date}</span>
              </div>
            )}
            {sessionId && state.verdictShown && state.mode === "real" && (
              <div className="costrow" style={{ display: "block" }}>
                <div style={{ marginBottom: 6 }}>{lang === "ar" ? "اسأل الفريق عن القرار" : "Ask the team about the call"}</div>
                <AskTeam compact sessionId={sessionId} onAnswer={(c, text) => say(c, text)} />
              </div>
            )}
            {prefs.showCost && state.usage && (
              <div className="costrow"><span>{t.actualCost}</span>
                <span className="pixel ltr">{state.mode === "demo" ? t.free : state.usage.cost_usd != null ? fmtUsd(state.usage.cost_usd, lang, 3)
                  : `${fmtNum(Object.values(state.usage.models).reduce((a, m) => a + m.input + m.output, 0), lang)} ${t.tokens} · ${t.unknownPrice}`}</span></div>
            )}
            {state.log.length === 0 && <p className="muted" style={{ margin: 0, lineHeight: 1.8 }}>{t.logEmpty}</p>}
            <div className="loglist" aria-live="polite">
              {state.log.map((l) => (
                <LogItem key={l.id} l={l} />
              ))}
            </div>
          </div>
        </aside>
      </div>

      {scanDone && scan?.ranking && <Ranking scan={scan} onOpen={onOpenReport} onClose={() => setScan({ ...scan, ranking: null })} />}
    </>
  );
}

function LogItem({ l }: { l: Line }) {
  const { prefs } = usePrefs();
  const text = useLineText(l.texts, l.turnId, prefs.lang, !l.demo);
  return (
    <div className="logitem">
      <b style={{ color: charColor(l.character as CharKey) }}>{charName(l.character, prefs.lang)}</b>
      <div style={{ fontSize: 14, lineHeight: 1.6 }}>{text ?? "…"}</div>
    </div>
  );
}

function Ranking({ scan, onOpen, onClose }: { scan: ScanView; onOpen: (id: string) => void; onClose: () => void }) {
  const { t, prefs } = usePrefs();
  const lang = prefs.lang;
  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-label={t.leaderboard}>
      <div className="modal">
        <h2 style={{ fontSize: 24, marginBottom: 6 }}>{t.leaderboard}</h2>
        <p className="muted" style={{ marginTop: 0 }}>{t.disclaimer}</p>
        <ol className="board-rank">
          {scan.ranking!.map((r, i) => (
            <li key={r.session_id}>
              <b className="pixel" style={{ fontSize: 20, width: 28 }}>{i + 1}</b>
              <b className="pixel ltr" style={{ minWidth: 70 }}>{r.ticker}</b>
              {r.rating ? <span className={`vchip ${RATING[r.rating]?.tone ?? "none"}`}>{lang === "ar" ? RATING[r.rating]?.ar : RATING[r.rating]?.en}</span> : <span className="muted">{r.status}</span>}
              <span style={{ flex: 1 }} />
              <button className="ghost btn" onClick={() => onOpen(r.session_id)}>{t.view}</button>
            </li>
          ))}
        </ol>
        <div className="row" style={{ justifyContent: "flex-end", marginTop: 14 }}><button className="primary btn" onClick={onClose}>{t.close}</button></div>
      </div>
    </div>
  );
}

function parseList(s: string) {
  return [...new Set(s.split(/[,\s،]+/).map((x) => x.trim().toUpperCase()).filter(Boolean))].slice(0, 5);
}
function fmtTime(iso: string, lang: string) {
  return new Intl.DateTimeFormat(lang === "ar" ? "ar-SA-u-nu-latn-ca-gregory" : "en-US", { timeStyle: "short" }).format(new Date(iso));
}
