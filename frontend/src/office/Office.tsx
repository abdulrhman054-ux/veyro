import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, openStream, type Candidate, type SessionFull, type Settings } from "../api";
import { charColor } from "../art/Sprite";
import { click, startJingle, unlockAudio } from "../audio";
import { CHAR_ORDER, NODE_LABEL, RATING, charName, fmtNum, fmtPct, fmtUsd, type CharKey } from "../i18n";
import { Markdown } from "../components/Markdown";
import { Glossed } from "../extras/Glossary";
import { usePrefs } from "../prefs";
import { EndedBox, IdleBox, SpeechBox, VerdictBox, WaitBox } from "./Dialog";
import { BudgetPlan, money } from "./BudgetPlan";
import { BeginnerGuide } from "./BeginnerGuide";
import { AddToPaper } from "../extras/Paper";
import { RoomScene, Stage } from "./Room";
import { useSession, type Line } from "./useSession";
import { useLineText } from "./lineText";
import { AskTeam, FavoritesStrip, StarButton, useAssistant } from "../assistant/Assistant";
import { TICKER, TickerSearch } from "../components/TickerSearch";
import { moodFrom } from "./mood";
import { sceneOf, toneOf, type SceneId } from "./scenes";
import type { History } from "../api";
import { ShariaBadge, disclaimer, methodName, useShariaHidden } from "../extras/Sharia";

type Mode = "single" | "watchlist" | "scan" | "beginner";
type IndexFund = { symbol: string; name_en: string; name_ar: string; what: { ar: string; en: string }; issuer_sharia: boolean;
  price: number | null; currency: string | null; units: number; cost: number | null };
type BPick = { symbol: string; name_en: string; name_ar: string; sector: string; style: string; price: number; currency: string; price_in_budget: number };
type ScanView = { id: string; tickers: string[]; source: Candidate[] | null; sessions: string[]; results: Record<number, string | null>;
  ranking: { ticker: string; rating: string | null; session_id: string; status: string }[] | null; done: boolean; stopped?: boolean;
  budget?: Budget | null; beginner?: boolean; prescreen?: Prescreen[] | null; reused?: Record<number, boolean>; capped?: boolean };
type Prescreen = { ticker: string; score: number | null; trend?: number; ret_3m?: number; vol?: number; mode?: string; ret_12_1?: number; max_drop?: number };
export type Budget = { amount: number; currency: "USD" | "SAR" };

const FORM_KEY = "veyro.office.form.v1";
type Form = { mode: Mode; ticker: string; picked: string[]; screener: string; count: number };
function loadForm(): Form {
  const d: Form = { mode: "single", ticker: "NVDA", picked: ["AAPL", "MSFT", "NVDA"], screener: "most_actives", count: 3 };
  try { return { ...d, ...JSON.parse(localStorage.getItem(FORM_KEY) || "{}") }; } catch { return d; }
}

export function Office({ settings, onOpenReport, onBusy, marketOpen: usOpen, marketsOpen, renderVerdictExtra, pendingStart, pendingScan }: { settings: Settings | null; onOpenReport: (id: string) => void; onBusy: (b: boolean) => void; marketOpen: boolean | null;
  marketsOpen?: Record<"sa" | "us", { open: boolean }> | null;
  renderVerdictExtra?: (sessionId: string, ticker: string, rating: string, demo: boolean) => React.ReactNode;
  pendingStart?: { ticker: string; trade_date: string; nonce: number } | null;
  pendingScan?: { id: string; nonce: number } | null }) {
  const { t, prefs } = usePrefs();
  const lang = prefs.lang;
  const [form0] = useState(loadForm);   // the start bar remembers what you typed, across screens and restarts
  const [mode, setMode] = useState<Mode>(form0.mode);
  const [ticker, setTicker] = useState(form0.ticker);
  const [tradeDate, setTradeDate] = useState("");   // empty = today (the framework analyses point-in-time for past dates)
  const [picked, setPicked] = useState<string[]>(form0.picked);   // the stocks chosen for a watchlist run
  const [adding, setAdding] = useState("");
  const [screener, setScreener] = useState(form0.screener);
  const [count, setCount] = useState(form0.count);
  const [chosen, setChosen] = useState<Set<string>>(new Set());   // scan candidates ticked for analysis
  // Economy: a free price pre-screen, then the full (paid) team only on the best few.
  const [economy, setEconomy] = useState(false);
  const [econTop, setEconTop] = useState(3);
  const [econMode, setEconMode] = useState<"momentum" | "steady">("momentum");
  // Reuse: this stock was already analysed today with the same models.
  const [reuseOffer, setReuseOffer] = useState<{ id: string; ticker: string; rating: string | null; at: string } | null>(null);
  useEffect(() => {
    try { localStorage.setItem(FORM_KEY, JSON.stringify({ mode, ticker, picked, screener, count })); } catch { /* private mode */ }
  }, [mode, ticker, picked, screener, count]);
  const { favorites } = useAssistant();
  const maxBatch = settings?.limits?.batch ?? 50;
  const maxScreen = settings?.limits?.screen ?? 25;
  const addTickers = (xs: string[]) => {
    const ok = xs.map((x) => x.trim().toUpperCase()).filter((x) => TICKER.test(x));
    if (ok.length) setPicked((p) => [...new Set([...p, ...ok])].slice(0, maxBatch));
    return ok.length;
  };
  const [screeners, setScreeners] = useState<Record<string, { ar: string; en: string }>>({});
  const [preview, setPreview] = useState<Candidate[] | null>(null);
  const shHidden = useShariaHidden(preview?.map((c) => c.symbol) ?? []);   // optional Sharia screen: "hide non-compliant"
  const [previewState, setPreviewState] = useState<"idle" | "loading" | "none">("idle");
  const hasKey = !!settings && settings.keys[settings.provider]?.present;
  const [demo, setDemo] = useState<boolean>(false);
  useEffect(() => { if (settings && !hasKey) setDemo(true); }, [settings, hasKey]);
  const [err, setErr] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [scan, setScan] = useState<ScanView | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const { state, next, showVerdict, say, stopNow } = useSession(sessionId);
  const [stopReq, setStopReq] = useState(false);
  const [budgetText, setBudgetText] = useState(() => { try { return localStorage.getItem("veyro.budget.v1") ?? ""; } catch { return ""; } });
  const [budgetCur, setBudgetCur] = useState<"USD" | "SAR">(() => { try { return (localStorage.getItem("veyro.budgetcur.v1") as "USD" | "SAR") || "USD"; } catch { return "USD"; } });
  useEffect(() => { try { localStorage.setItem("veyro.budget.v1", budgetText); localStorage.setItem("veyro.budgetcur.v1", budgetCur); } catch { /* ignore */ } }, [budgetText, budgetCur]);
  const budgetNum = Number(budgetText.replace(/[,\s٬]/g, "").replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d))));
  const budget: Budget | null = budgetNum > 0 && Number.isFinite(budgetNum) ? { amount: budgetNum, currency: budgetCur } : null;
  const [sessionBudget, setSessionBudget] = useState<Budget | null>(null);   // the budget the shown session was started with
  // Beginner mode: "I have 1000 riyals" -> affordable, well-known companies -> full analysis -> plan + lessons.
  const [bMarket, setBMarket] = useState<"sa" | "us" | "both">("sa");
  const [bRisk, setBRisk] = useState<"cautious" | "balanced" | "bold">("balanced");
  const [bCount, setBCount] = useState(3);
  const [bPicks, setBPicks] = useState<BPick[] | null>(null);
  const [bChosen, setBChosen] = useState<Set<string>>(new Set());
  const [bLoading, setBLoading] = useState(false);
  const [bIndex, setBIndex] = useState<IndexFund[]>([]);
  const [bSharia, setBSharia] = useState<{ method: string; excluded: { symbol: string; status: string }[]; short: boolean; wanted: number } | null>(null);
  const [bMarkets, setBMarkets] = useState<Record<string, { open: boolean; name: { ar: string; en: string }; hours: { ar: string; en: string } }> | null>(null);
  useEffect(() => { setBPicks(null); }, [bMarket, bRisk, bCount, budgetText, budgetCur]);
  // The amount follows the chosen market's currency (both markets: keep whatever the owner picked).
  useEffect(() => { if (mode === "beginner" && bMarket !== "both") setBudgetCur(bMarket === "sa" ? "SAR" : "USD"); }, [bMarket, mode]);
  async function suggestBeginner() {
    setErr(null);
    if (!budget) { setErr(lang === "ar" ? "اكتب المبلغ اللي معك أول (مثلاً 1000)." : "Enter the amount you have first (e.g. 1000)."); return; }
    setBLoading(true);
    try {
      const r = await api.post<{ picks: BPick[]; prices_available: boolean; markets: typeof bMarkets; sharia?: typeof bSharia; index_funds?: IndexFund[] }>("/api/beginner/suggest",
        { amount: budget.amount, currency: budget.currency, market: bMarket, risk: bRisk, count: bCount });
      setBPicks(r.picks); setBChosen(new Set(r.picks.map((x) => x.symbol))); setBMarkets(r.markets); setBSharia(r.sharia ?? null); setBIndex(r.index_funds ?? []);
      if (!r.picks.length) setErr(r.prices_available
        ? (lang === "ar" ? "المبلغ ما يكفي لسهم واحد من الشركات المقترحة. جرّب مبلغ أكبر أو سوق ثاني." : "The amount doesn't cover one share of the suggested companies. Try a larger amount or another market.")
        : (lang === "ar" ? "أسعار السوق غير متوفرة الآن. جرّب بعد شوي." : "Market prices are unavailable right now. Try again shortly."));
    } catch { setErr(t.error); }
    setBLoading(false);
  }
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
  useEffect(() => { if (!running) setStopReq(false); }, [running]);
  const finishedShowing = state.ended && !state.current && state.queue.length === 0 && (state.verdictShown || !state.verdict);

  // Show Leo's verdict once every queued line has been spoken.
  useEffect(() => {
    if (state.verdict && !state.current && state.queue.length === 0 && !state.verdictShown) showVerdict();
  }, [state.verdict, state.current, state.queue.length, state.verdictShown, showVerdict]);

  // Scans: move to the next ticker only after the current one has been fully shown.
  const scanIdx = scan ? scan.sessions.indexOf(sessionId ?? "") : -1;
  useEffect(() => {
    if (!scan || scanIdx < 0 || scan.stopped) return;
    const nextSid = scan.sessions[scanIdx + 1];
    if (finishedShowing && nextSid) {
      const h = window.setTimeout(() => { setSessionId(nextSid); setStarting(`${scan.tickers[scanIdx + 1]} · ${scanIdx + 2}/${scan.tickers.length}`); startJingle(); }, 4500);
      return () => clearTimeout(h);
    }
  }, [scan, scanIdx, finishedShowing]);

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
    const n = batchSize();
    const e = settings.estimate;
    if (!e.known || e.low === null || e.high === null) return t.estimateUnknown;
    return `${fmtUsd(e.low * n, lang)} – ${fmtUsd(e.high * n, lang)}`;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings, demo, mode, picked, count, chosen, preview, bPicks, bChosen, bCount, lang, t]);

  // The analysis's own cost compared with the amount being invested (a $5 analysis on $270 is ~2%).
  const [usdPer, setUsdPer] = useState<number | null>(1);
  useEffect(() => {
    if (budgetCur === "USD") { setUsdPer(1); return; }
    let alive = true;
    api.get<{ rate: number | null }>(`/api/fx?src=${budgetCur}&dst=USD`).then((r) => alive && setUsdPer(r.rate)).catch(() => alive && setUsdPer(null));
    return () => { alive = false; };
  }, [budgetCur]);
  const costShare = useMemo(() => {
    const e = settings?.estimate;
    if (demo || !budget || !usdPer || !e?.known || e.high == null) return null;
    return (e.high * batchSize()) / (budget.amount * usdPer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings, demo, budget, usdPer, mode, picked, count, chosen, preview, bPicks, bChosen, bCount, economy, econTop]);

  function batchSize() {
    if (mode === "single") return 1;
    if (mode === "beginner") return bPicks ? bChosen.size || 1 : bCount;
    const n = mode === "watchlist" ? picked.length || 1 : preview && chosen.size ? chosen.size : count;
    return economy && n > econTop ? econTop : n;
  }

  async function openPrevious(id: string, tk: string) {
    setReuseOffer(null); scanClose.current?.(); setScan(null);
    try { await api.post(`/api/sessions/${id}/replay`); setSessionBudget(budget); setStarting(tk); startJingle(); setSessionId(id); }
    catch { setErr(t.error); }
  }

  async function start(opts?: { fresh?: boolean }) {
    setErr(null); unlockAudio(); click();
    try {
      if (mode === "beginner" && !bPicks) { await suggestBeginner(); return; }
      scanClose.current?.(); setScan(null);
      if (mode === "single") {
        const tk = ticker.trim().toUpperCase();
        if (!TICKER.test(tk)) { setErr(lang === "ar" ? "اكتب رمز السهم أو اختر الشركة من قائمة البحث." : "Type a symbol, or pick the company from the search list."); return; }
        if (!demo && !opts?.fresh) {
          const q = tradeDate ? `&trade_date=${tradeDate}` : "";
          const r0 = await api.get<{ session: { id: string; rating: string | null; created_at: string } | null }>(`/api/reusable?ticker=${encodeURIComponent(tk)}${q}`).catch(() => ({ session: null }));
          if (r0.session) { setReuseOffer({ id: r0.session.id, ticker: tk, rating: r0.session.rating, at: r0.session.created_at }); return; }
        }
        const r = await api.post<{ id: string }>("/api/sessions", { ticker: tk, lang, demo, trade_date: tradeDate || null,
          budget: budget?.amount ?? null, budget_currency: budget?.currency ?? "USD" });
        setSessionBudget(budget); setStarting(tk); startJingle(); setSessionId(r.id);
      } else {
        // Scan with ticked candidates = analyse exactly those; otherwise the screener's top N.
        const tickers = mode === "watchlist" ? picked : mode === "beginner" ? (bPicks ?? []).map((c) => c.symbol).filter((x) => bChosen.has(x))
          : preview && chosen.size ? preview.map((c) => c.symbol).filter((x) => chosen.has(x) && !shHidden(x)) : null;
        if (tickers && tickers.length === 0) { setErr(lang === "ar" ? "اختر سهم واحد على الأقل." : "Pick at least one stock."); return; }
        const n = tickers ? tickers.length : count;
        const e = settings?.estimate;
        const paid = economy && mode !== "beginner" && n > econTop ? econTop : n;
        const sp = settings?.spend;
        if (!demo && sp?.cap && e?.known && e.high != null && sp.spent + e.high * paid > sp.cap
          && !window.confirm(lang === "ar"
            ? `تنبيه الميزانية: صرفت ${"$"}${sp.spent.toFixed(2)} من ${"$"}${sp.cap} هذا الشهر، وهالتحليل ممكن يوصل ${fmtUsd(e.high * paid, lang)}. المسح يوقف تلقائياً عند السقف. نكمل؟`
            : `Budget check: $${sp.spent.toFixed(2)} of $${sp.cap} spent this month, and this run could reach ${fmtUsd(e.high * paid, lang)}. The run stops at the cap. Continue?`)) return;
        if (!demo && paid > 5 && e?.known && e.high != null
          && !window.confirm(lang === "ar"
            ? `بتحلل ${paid} أسهم، كل سهم جلسة كاملة. التكلفة التقديرية ${fmtUsd((e.low ?? 0) * paid, lang)} – ${fmtUsd(e.high * paid, lang)}. نكمل؟`
            : `You're analysing ${paid} stocks, each a full session. Estimated cost ${fmtUsd((e.low ?? 0) * paid, lang)} – ${fmtUsd(e.high * paid, lang)}. Continue?`)) return;
        const body = { ...(tickers ? { kind: "watchlist", tickers } : { kind: "screener", screener, count }), lang, demo,
          budget: budget?.amount ?? null, budget_currency: budget?.currency ?? "USD",
          economy_top: economy && mode !== "beginner" && n > econTop ? econTop : null, prescreen_mode: econMode };
        const r = mode === "beginner"
          ? await api.post<{ id: string; tickers: string[]; source: Candidate[] | null }>("/api/beginner/start",
              { amount: budget!.amount, currency: budget!.currency, market: bMarket, risk: bRisk, count: tickers!.length, tickers, lang, demo })
          : await api.post<{ id: string; tickers: string[]; source: Candidate[] | null; prescreen?: Prescreen[] | null }>("/api/scans", body);
        const view: ScanView = { id: r.id, tickers: r.tickers, source: r.source, sessions: [], results: {}, ranking: null, done: false, budget,
          beginner: mode === "beginner", prescreen: (r as { prescreen?: Prescreen[] | null }).prescreen ?? null, reused: {} };
        setScan(view);
        scanClose.current = openStream(`/ws/scans/${r.id}`, (ev) => {
          setScan((s) => {
            if (!s) return s;
            if (ev.type === "scan_session") {
              const sessions = [...s.sessions]; sessions[ev.index] = ev.session_id;
              return { ...s, sessions, reused: { ...(s.reused ?? {}), [ev.index]: !!(ev as { reused?: boolean }).reused } };
            }
            if (ev.type === "scan_result") return { ...s, results: { ...s.results, [ev.index]: ev.rating } };
            if (ev.type === "scan_ranked") return { ...s, ranking: ev.ranking };
            if (ev.type === "end") return { ...s, done: true };
            if ((ev as { type: string }).type === "scan_capped") return { ...s, capped: true };
            return s;
          });
        });
      }
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "error";
      setErr(code === "invalid_ticker" ? t.invalidTicker : code === "screener_unavailable" ? t.unavailable
        : code === "bad_budget" ? (lang === "ar" ? "المبلغ غير صالح." : "That amount isn't valid.")
        : code === "budget_cap" ? (lang === "ar" ? "وصلت سقف ميزانية التحليل لهذا الشهر. ارفعه من الإعدادات أو جرّب الوضع التجريبي." : "You've reached this month's analysis budget cap. Raise it in Settings or use demo mode.")
        : t.error);
    }
  }

  // "Resume" from History: same ticker and date, the framework continues from its checkpoint.
  useEffect(() => {
    if (!pendingStart) return;
    setMode("single"); setTicker(pendingStart.ticker); setTradeDate(pendingStart.trade_date); setDemo(false);
    scanClose.current?.(); setScan(null);
    api.post<{ id: string }>("/api/sessions", { ticker: pendingStart.ticker, lang, demo: false, trade_date: pendingStart.trade_date })
      .then((r) => { setSessionBudget(null); setStarting(pendingStart.ticker); startJingle(); setSessionId(r.id); }).catch(() => setErr(t.error));
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

  // "Analyse" on the Live screen: put that stock in the start bar, ready to go.
  useEffect(() => {
    const f = (e: Event) => { const tk = (e as CustomEvent<string>).detail; if (tk && !running) { setMode("single"); setTicker(tk); setErr(null); } };
    window.addEventListener("veyro:pick-ticker", f);
    return () => window.removeEventListener("veyro:pick-ticker", f);
  });

  // Keyboard: "/" jumps to the stock search, Space moves to the next line, Esc stops the session.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing = !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
      if (document.querySelector(".modal-bg")) return;
      const officeShown = !!document.querySelector(".office") && (document.querySelector(".office") as HTMLElement).offsetParent !== null;
      if (!officeShown) return;
      if (e.key === "/" && !typing) { e.preventDefault(); (document.querySelector(".startbar .tsearch input") as HTMLInputElement | null)?.focus(); }
      else if (e.key === " " && !typing && !(el?.tagName === "BUTTON")) { const d = document.querySelector("button.dlg") as HTMLButtonElement | null; if (d) { e.preventDefault(); d.click(); } }
      else if (e.key === "Escape" && !typing && running) { void stop(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  async function stop() {
    if (stopReq) return;
    click(); setStopReq(true);
    stopNow();   // the office goes quiet at once; Leo confirms when the server has stopped
    if (scan) {
      setScan((sc) => (sc ? { ...sc, stopped: true } : sc));
      await api.post(`/api/scans/${scan.id}/cancel`).catch(() => {});
    }
    if (sessionId) await api.post(`/api/sessions/${sessionId}/cancel`).catch(() => {});
  }

  async function loadPreview() {
    setPreviewState("loading");
    try {
      const b = budget ? `&budget=${budget.amount}&currency=${budget.currency}` : "";
      const r = await api.get<{ available: boolean; candidates: Candidate[] }>(`/api/market/screen/${screener}?count=${count}${b}`);
      setPreview(r.available ? r.candidates : []); setPreviewState(r.available ? "idle" : "none");
    } catch { setPreview([]); setPreviewState("none"); }
  }
  useEffect(() => { setPreview(null); setPreviewState("idle"); setChosen(new Set()); }, [screener, count, budget?.amount, budget?.currency]);
  useEffect(() => { if (preview) setChosen(new Set(preview.map((c) => c.symbol))); }, [preview]);

  const isDemo = state.mode === "demo" || (!sessionId && demo);
  // Which set we're on follows what is playing now (not what the server has already finished):
  // the line on screen, else the next queued line, else the step the team just started.
  const scene: SceneId = !sessionId ? "office"
    : state.verdictShown && state.verdict ? "decision"
    : sceneOf(state.current?.node, true) ?? sceneOf(state.queue[0]?.node) ?? sceneOf(state.lastNode) ?? "office";
  const heat = scene === "debate" ? state.debateLines + (state.current && sceneOf(state.current.node) === "debate" ? 1 : 0) : 0;
  const speakTone = state.current && state.current.kind !== "error" ? toneOf(state.current.texts?.[lang] ?? state.current.text) : null;
  const verdictTone = state.verdictShown && state.verdict ? (RATING[state.verdict.rating]?.tone ?? null) : null;
  const verdictExtra = sessionId && state.verdict && state.ticker && renderVerdictExtra
    ? <>{renderVerdictExtra(sessionId, state.ticker, state.verdict.rating, state.mode === "demo")}
        {state.mode === "real" && (state.verdict.rating === "Buy" || state.verdict.rating === "Overweight") && !sessionBudget && (
          <AddToPaper items={[{ ticker: state.ticker, shares: 1, session_id: sessionId, rating: state.verdict.rating }]}
            label={lang === "ar" ? "📒 سهم للمحفظة الافتراضية" : "📒 1 share to the virtual portfolio"} />)}</> : null;
  const SESSION: CharKey[] = [...CHAR_ORDER.slice(0, 7), "Albie", "Leo"];   // speaking order in a session
  const doneCount = SESSION.filter((c) => state.agents[c] === "done").length;
  const attending = SESSION.filter((c) => state.agents[c] !== "break").length;
  // The ranking shows once the scan is over and the last session shown has finished playing
  // (also when that session ended in an error or the scan was stopped).
  const scanDone = !!scan?.done && !!scan.ranking && (scan.stopped || scanIdx === scan.sessions.length - 1) && finishedShowing;

  return (
    <>
      <div className="startbar" role="group" aria-label={t.start}>
        <div className="seg" role="group">
          {(["beginner", "single", "watchlist", "scan"] as Mode[]).map((m) => (
            <button key={m} aria-pressed={mode === m} onClick={() => { setMode(m); click(); }} disabled={running}>
              {m === "beginner" ? (lang === "ar" ? "🌱 أنا مبتدئ" : "🌱 I'm new") : t[m]}</button>
          ))}
        </div>
        {mode === "single" && (<>
          <div className="row" style={{ gap: 8 }}>
            <span style={{ fontWeight: 800 }}>{t.ticker}</span>
            <TickerSearch value={ticker} onChange={setTicker} onPick={(sym) => { setTicker(sym); setErr(null); }} width={190}
              onEnter={() => { if (!running) void start(); }} invalid={!!err} disabled={running} />
          </div>
          <StarButton ticker={ticker.trim().toUpperCase()} />
          <label className="row" style={{ gap: 6 }} title={lang === "ar" ? "اتركه فاضي لتحليل اليوم" : "Leave empty to analyse today"}>
            <span style={{ fontWeight: 700, fontSize: 14 }}>{lang === "ar" ? "بتاريخ سابق؟" : "Past date?"}</span>
            <input className="field ltr" type="date" style={{ height: 40, width: 150, fontSize: 14 }} value={tradeDate}
              max={new Intl.DateTimeFormat("en-CA", { timeZone: ticker.trim().toUpperCase().endsWith(".SR") ? "Asia/Riyadh" : "America/New_York" }).format(new Date())} onChange={(e) => setTradeDate(e.target.value)} disabled={running} />
          </label>
        </>)}
        {mode === "watchlist" && (
          <div className="row" style={{ gap: 8, flex: 1, minWidth: 260 }}>
            <span style={{ fontWeight: 800 }}>{lang === "ar" ? "أضف سهم" : "Add a stock"}</span>
            <TickerSearch value={adding} onChange={setAdding} clearOnPick width={210} disabled={running || picked.length >= maxBatch}
              onPick={(sym) => { addTickers([sym]); setErr(null); }}
              onEnter={() => { if (addTickers(adding.split(/[,\s،]+/))) setAdding(""); }} />
            {favorites.length > 0 && <button className="ghost btn" disabled={running} onClick={() => { addTickers(favorites); click(); }}>★ {lang === "ar" ? "أضف المفضلة" : "Add favourites"}</button>}
          </div>
        )}
        {mode === "beginner" && (
          <>
            <label className="row" style={{ gap: 6 }}>
              <span style={{ fontWeight: 800 }}>{lang === "ar" ? "السوق" : "Market"}</span>
              <select className="field" style={{ height: 40 }} value={bMarket} onChange={(e) => setBMarket(e.target.value as "sa" | "us" | "both")} disabled={running}>
                <option value="sa">{lang === "ar" ? "السعودي" : "Saudi"}</option><option value="us">{lang === "ar" ? "الأمريكي" : "US"}</option>
                <option value="both">{lang === "ar" ? "الاثنين" : "Both"}</option>
              </select>
            </label>
            <div className="segbtns" role="group" aria-label={lang === "ar" ? "راحتك مع المخاطرة" : "Comfort with risk"}>
              {(["cautious", "balanced", "bold"] as const).map((r) => (
                <button key={r} aria-pressed={bRisk === r} disabled={running} onClick={() => setBRisk(r)}>
                  {lang === "ar" ? { cautious: "حذر", balanced: "متوازن", bold: "جريء" }[r] : { cautious: "Cautious", balanced: "Balanced", bold: "Bold" }[r]}</button>
              ))}
            </div>
            <label className="row" style={{ gap: 6 }}>
              <span style={{ fontWeight: 800 }}>{lang === "ar" ? "كم سهم" : "Stocks"}</span>
              <select className="field" style={{ height: 40 }} value={bCount} onChange={(e) => setBCount(Number(e.target.value))} disabled={running}>
                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <button className="ghost btn" onClick={suggestBeginner} disabled={running || bLoading}>{bLoading ? "…" : (lang === "ar" ? "اقترح لي" : "Suggest for me")}</button>
          </>
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
                {[1, 2, 3, 5, 10, 15, 20, 25].filter((n) => n <= maxScreen).map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <button className="ghost btn" onClick={loadPreview} disabled={running || previewState === "loading"}>{t.preview}</button>
          </>
        )}
        <label className="row budget" style={{ gap: 6 }} title={lang === "ar" ? "اختياري: المبلغ اللي تبي تستثمره. نقترح أسهم تقدر تشتريها، وليو يوزّع المبلغ بعد التحليل." : "Optional: the amount you want to invest. We suggest stocks you can afford, and Leo splits it after the analysis."}>
          <span style={{ fontWeight: 800 }}>{lang === "ar" ? "المبلغ" : "Budget"}</span>
          <input className="field ltr" inputMode="decimal" style={{ width: 110, height: 40 }} placeholder={lang === "ar" ? "اختياري" : "optional"}
            value={budgetText} onChange={(e) => setBudgetText(e.target.value)} disabled={running} aria-label={lang === "ar" ? "مبلغ الاستثمار" : "Amount to invest"} />
          <select className="field" style={{ height: 40, padding: "0 8px" }} value={budgetCur} onChange={(e) => setBudgetCur(e.target.value as "USD" | "SAR")} disabled={running} aria-label={lang === "ar" ? "العملة" : "Currency"}>
            <option value="USD">USD $</option><option value="SAR">{lang === "ar" ? "ريال" : "SAR"}</option>
          </select>
        </label>
        {(mode === "watchlist" || mode === "scan") && (
          <label className="check" title={lang === "ar" ? "فحص مجاني من بيانات الأسعار (الاتجاه، العائد، التذبذب) ثم التحليل الكامل المدفوع لأفضل الأسهم فقط" : "A free price pre-screen (trend, return, volatility), then the paid full analysis only on the best few"}>
            <input type="checkbox" checked={economy} onChange={(e) => setEconomy(e.target.checked)} disabled={running} />
            {lang === "ar" ? "💰 اقتصادي: حلّل أفضل" : "💰 Economy: analyse the best"}
            <select className="field" style={{ height: 32, padding: "0 6px", marginInlineStart: 6 }} value={econTop} disabled={running || !economy}
              onChange={(e) => setEconTop(Number(e.target.value))}>{[1, 2, 3, 5, 8, 10].map((k) => <option key={k} value={k}>{k}</option>)}</select>
            <select className="field" style={{ height: 32, padding: "0 6px", marginInlineStart: 6 }} value={econMode} disabled={running || !economy}
              aria-label={lang === "ar" ? "طريقة الفحص المجاني" : "Pre-screen method"} onChange={(e) => setEconMode(e.target.value as "momentum" | "steady")}
              title={lang === "ar" ? "زخم: اللي صعد مؤخراً. ثابت: قوة على سنة بدون آخر شهر، مع عقوبة للتذبذب والهبوط الكبير." : "Momentum: what rose lately. Steady: 12-month strength skipping the last month, penalising swings and big drops."}>
              <option value="momentum">{lang === "ar" ? "زخم" : "momentum"}</option>
              <option value="steady">{lang === "ar" ? "ثابت" : "steady"}</option>
            </select>
          </label>
        )}
        <label className="check"><input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} disabled={running} />{t.demoMode}</label>
        {prefs.showCost && estimate && <span className="estimate">{t.estimate}: <b className="ltr">{estimate}</b></span>}
        {prefs.showCost && settings?.spend?.cap && !demo && <span className={`chip mkt${settings.spend.spent >= settings.spend.cap ? " closed" : ""}`} title={lang === "ar" ? "صرف هذا الشهر من سقف الميزانية" : "This month's spend against your cap"}>
          <i />{lang === "ar" ? "الشهر" : "Month"} <span className="ltr">${settings.spend.spent.toFixed(2)} / ${settings.spend.cap}</span></span>}
        <span style={{ flex: 1 }} />
        {running
          ? <button className="ghost btn" onClick={stop} disabled={stopReq} aria-busy={stopReq}>{stopReq ? (lang === "ar" ? "نوقف…" : "Stopping…") : t.stop}</button>
          : <button className="primary btn" onClick={() => void start()} disabled={(mode === "watchlist" && picked.length === 0) || (mode === "beginner" && !!bPicks && bChosen.size === 0)}>
              {mode === "single" ? (sessionId ? t.again : t.start) : mode === "watchlist" ? `${t.startList} (${picked.length})`
                : mode === "beginner" ? (bPicks ? (lang === "ar" ? `حلّلها لي (${bChosen.size})` : `Analyse them (${bChosen.size})`) : (lang === "ar" ? "اقترح لي" : "Suggest for me"))
                : preview && chosen.size ? `${t.startScan} (${chosen.size})` : t.startScan}</button>}
      </div>
      {mode === "beginner" && !running && (
        <div className="card cream stack" style={{ padding: 14, gap: 10 }}>
          {!bPicks ? (
            <div className="row" style={{ gap: 10, flexWrap: "nowrap", alignItems: "flex-start" }}>
              <span aria-hidden="true" style={{ fontSize: 26 }}>🌱</span>
              <span style={{ lineHeight: 1.8 }}>{lang === "ar"
                ? "اكتب المبلغ اللي معك (مثلاً 1000 ريال)، اختر السوق وراحتك مع المخاطرة، واضغط «اقترح لي». الفريق يختار شركات كبيرة ومعروفة تقدر تشتري منها بمبلغك، يحللها كاملة، وبعدين ليو يقسم المبلغ وكل واحد يعطيك نصيحة من خبرته."
                : "Enter the amount you have (e.g. 1000 SAR), pick a market and your comfort with risk, then press “Suggest for me”. The team picks large, well-known companies you can afford, analyses each one fully, then Leo splits your amount and everyone shares a tip from their expertise."}</span>
            </div>
          ) : bPicks.length > 0 && (
            <div className="row" style={{ gap: 8 }}>
              <span className="label">{lang === "ar" ? "اقتراحات تناسب مبلغك (اختر اللي تبي):" : "Suggestions that fit your amount (tick the ones you want):"}</span>
              {bPicks.map((c) => (
                <label key={c.symbol} className="chip mkt pick" style={{ cursor: "pointer", height: "auto", minHeight: 34, opacity: bChosen.has(c.symbol) ? 1 : 0.55 }} title={c.sector}>
                  <input type="checkbox" checked={bChosen.has(c.symbol)} onChange={() => setBChosen((cs) => { const n = new Set(cs); if (n.has(c.symbol)) n.delete(c.symbol); else n.add(c.symbol); return n; })} />
                  <b>{lang === "ar" ? c.name_ar : c.name_en}</b><span className="pixel ltr muted">{c.symbol}</span>
                  <span className="ltr">{money(c.price, c.currency, lang)}</span>
                  <span className="muted" style={{ fontSize: 12 }}>{c.style === "steady" ? (lang === "ar" ? "مستقر" : "steady") : (lang === "ar" ? "نمو" : "growth")}</span>
                  <ShariaBadge symbol={c.symbol} />
                </label>
              ))}
              <span className="muted" style={{ fontSize: 12 }}>{lang === "ar" ? "أسعار Yahoo الحالية · للتعلّم وليس نصيحة مالية" : "Current Yahoo prices · for learning, not financial advice"}</span>
            </div>
          )}
          {bPicks && bIndex.length > 0 && (
            <div className="stack index-funds" style={{ gap: 6 }} aria-label={lang === "ar" ? "صندوق مؤشرات" : "Index fund"}>
              <b>{lang === "ar" ? "🧺 أبسط خيار: صندوق مؤشرات (بدون تحليل وبدون تكلفة تحليل)" : "🧺 The simplest option: an index fund (no analysis, no analysis cost)"}</b>
              <span className="muted" style={{ fontSize: 13, lineHeight: 1.7 }}>{lang === "ar"
                ? "بدل ما تختار شركات بنفسك، الصندوق يشتري لك السوق كله دفعة وحدة. لكثير من المبتدئين هذا يكفي كبداية."
                : "Instead of picking companies, the fund buys the whole market for you in one go. For many beginners that's enough to start."}</span>
              {bIndex.map((f) => (
                <div key={f.symbol} className="chip mkt pick" style={{ height: "auto", minHeight: 34, whiteSpace: "normal", gap: 6 }}>
                  <b>{lang === "ar" ? f.name_ar : f.name_en}</b><span className="pixel ltr muted">{f.symbol}</span>
                  <span>{f.what[lang]}</span>
                  {f.price != null && f.currency ? <span className="ltr">{money(f.price, f.currency, lang)}</span> : <span className="muted">{t.unavailable}</span>}
                  {f.price != null && <span>{lang === "ar" ? `مبلغك يشتري ${f.units} وحدة (${money(f.cost ?? 0, budgetCur, lang)})` : `your amount buys ${f.units} units (${money(f.cost ?? 0, budgetCur, lang)})`}</span>}
                  {f.issuer_sharia && <span className="muted" style={{ fontSize: 12 }}>{lang === "ar" ? "☪ المُصدر يذكر أنه متوافق مع الشريعة" : "☪ the issuer states it is Sharia-compliant"}</span>}
                  {f.units > 0 && <AddToPaper items={[{ ticker: f.symbol, shares: f.units }]} label={lang === "ar" ? "📒 للمحفظة الافتراضية" : "📒 To the virtual portfolio"} />}
                </div>
              ))}
            </div>
          )}
          {bPicks && bSharia && (
            <div className={bSharia.short ? "warnstrip" : "muted"} role="status" style={{ fontSize: 13, lineHeight: 1.7 }}>
              {lang === "ar"
                ? `☪ الفحص الشرعي مفعّل (${methodName(bSharia.method, lang)}): نقترح الشركات المتوافقة فقط، واستبعدنا ${bSharia.excluded.length} (غير متوافقة: ${bSharia.excluded.filter((x) => x.status === "not_compliant").length}، غير معروفة: ${bSharia.excluded.filter((x) => x.status === "unknown").length}).`
                : `☪ Sharia screening is on (${methodName(bSharia.method, lang)}): only compliant companies are suggested; ${bSharia.excluded.length} were left out (not compliant: ${bSharia.excluded.filter((x) => x.status === "not_compliant").length}, unknown: ${bSharia.excluded.filter((x) => x.status === "unknown").length}).`}
              {bSharia.short && (lang === "ar"
                ? ` طلبت ${bSharia.wanted} وما لقينا غير ${bPicks.length} متوافقة يكفيها مبلغك، وما نكمّل القائمة بغيرها.`
                : ` You asked for ${bSharia.wanted}; only ${bPicks.length} compliant ones fit your amount, and we won't pad the list with others.`)}
              {" "}{disclaimer(lang)}
            </div>
          )}
          {bPicks && bMarkets && (
            <div className="row" style={{ gap: 8 }}>
              {Object.entries(bMarkets).map(([k, m]) => (
                <span key={k} className={`chip mkt ${m.open ? "open" : "closed"}`} style={{ height: "auto", minHeight: 30, whiteSpace: "normal" }}>
                  <i /><b>{m.name[lang]}</b> · {m.open ? (lang === "ar" ? "مفتوح الآن" : "open now") : (lang === "ar" ? "مقفل الآن" : "closed now")}
                  <span className="muted" style={{ fontSize: 12 }}>· {m.hours[lang]}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      {mode === "watchlist" && (
        <div className="card cream picklist" role="group" aria-label={lang === "ar" ? "الأسهم المختارة" : "Chosen stocks"}>
          <span className="label">{lang === "ar" ? `الأسهم المختارة للتحليل (${picked.length} من ${maxBatch})` : `Stocks chosen for analysis (${picked.length} of ${maxBatch})`}</span>
          {picked.length === 0 && <span className="muted">{lang === "ar" ? "ابحث بالاسم أو الرمز فوق وأضف الأسهم اللي تبي تحللها." : "Search by name or symbol above and add the stocks you want analysed."}</span>}
          {picked.map((tk) => (
            <span key={tk} className="chip mkt pick">
              <b className="pixel ltr">{tk}</b>
              <ShariaBadge symbol={tk} />
              <button className="x btn" disabled={running} aria-label={(lang === "ar" ? "إزالة " : "Remove ") + tk}
                onClick={() => { setPicked((p) => p.filter((x) => x !== tk)); click(); }}>×</button>
            </span>
          ))}
          {picked.length > 1 && !running && <button className="linkish" onClick={() => setPicked([])}>{lang === "ar" ? "مسح الكل" : "Clear all"}</button>}
        </div>
      )}
      {err && <div className="warnstrip" role="alert">{err}</div>}
      {!running && costShare != null && costShare > 0.005 && (
        <div className="warnstrip" role="note" data-cost-warning>
          {lang === "ar"
            ? `⚠ هذا التحليل ممكن يكلّف حتى ${estimate?.split("–").pop()?.trim()}، يعني حوالي ${(costShare * 100).toFixed(1)}٪ من مبلغك، قبل عمولة الوسيط. هذا أكثر مما تاخذه كثير من الصناديق في سنة كاملة. جرّب نموذج أرخص (Haiku)، أو الوضع الاقتصادي، أو صندوق المؤشرات بدون تحليل.`
            : `⚠ This analysis could cost up to ${estimate?.split("–").pop()?.trim()}, about ${(costShare * 100).toFixed(1)}% of your amount, before broker fees. That's more than many funds charge in a whole year. Try a cheaper model (Haiku), economy mode, or the index fund with no analysis.`}
        </div>
      )}
      {reuseOffer && (
        <div className="card cream row" role="alertdialog" aria-label={lang === "ar" ? "تحليل سابق" : "Earlier analysis"} style={{ padding: 14, gap: 10 }}>
          <span style={{ flex: 1, minWidth: 220, lineHeight: 1.8 }}>{lang === "ar"
            ? <>حللنا <b className="pixel ltr">{reuseOffer.ticker}</b> اليوم بنفس النماذج{reuseOffer.rating ? <> وكان القرار <b>{RATING[reuseOffer.rating]?.ar ?? reuseOffer.rating}</b></> : null}. تبي تشوف النتيجة بدون تكلفة، أو تحلله من جديد؟</>
            : <>We already analysed <b className="pixel ltr">{reuseOffer.ticker}</b> today with the same models{reuseOffer.rating ? <> (call: <b>{RATING[reuseOffer.rating]?.en ?? reuseOffer.rating}</b>)</> : null}. See it again for free, or run a fresh analysis?</>}</span>
          <button className="primary green btn" onClick={() => openPrevious(reuseOffer.id, reuseOffer.ticker)}>{lang === "ar" ? "اعرض النتيجة (مجاناً)" : "Show it (free)"}</button>
          <button className="ghost btn" onClick={() => { setReuseOffer(null); void start({ fresh: true }); }}>{lang === "ar" ? "حلّل من جديد" : "Run again"}</button>
          <button className="linkish" onClick={() => setReuseOffer(null)}>{lang === "ar" ? "إلغاء" : "Cancel"}</button>
        </div>
      )}
      {!running && <FavoritesStrip onPick={(tk) => { if (mode === "watchlist") addTickers([tk]); else { setMode("single"); setTicker(tk); } click(); }} />}
      {mode === "scan" && preview && !running && (
        <div className="card cream" style={{ padding: 14 }}>
          {preview.length === 0 ? <span>{t.unavailable}</span> : (
            <div className="row" style={{ gap: 8 }}>
              <span className="label">{t.candidatesFrom} Yahoo Finance · {fmtTime(preview[0].as_of, lang)} · {lang === "ar" ? "اختر اللي تبي تحلله" : "tick the ones to analyse"}</span>
              {preview.filter((c) => !shHidden(c.symbol)).map((c) => (
                <label key={c.symbol} className="chip mkt pick" title={c.name ?? ""} style={{ cursor: "pointer", opacity: chosen.has(c.symbol) ? 1 : 0.55 }}>
                  <input type="checkbox" checked={chosen.has(c.symbol)} onChange={() => setChosen((cs) => { const n = new Set(cs); if (n.has(c.symbol)) n.delete(c.symbol); else n.add(c.symbol); return n; })} />
                  <b className="pixel ltr">{c.symbol}</b>
                  <span className="ltr">{c.price != null ? fmtUsd(c.price, lang) : t.unavailable}</span>
                  {c.change_pct != null && <span className={`ltr ${c.change_pct >= 0 ? "pos" : "neg"}`}>{fmtPct(c.change_pct / 100, lang)}</span>}
                  <ShariaBadge symbol={c.symbol} />
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="office">
        <Stage>
          <RoomScene ticker={state.ticker} market={state.market ?? (sessionId ? null : spy)} marketLoaded={state.marketLoaded}
            demo={isDemo} agents={state.agents} lang={lang} starting={starting} mood={mood}
            marketOpen={(state.ticker ?? "").toUpperCase().endsWith(".SR") ? (marketsOpen?.sa.open ?? null) : usOpen}
            scene={state.ended && !state.verdict && !state.current ? "office" : scene} heat={heat} verdictTone={verdictTone === "none" ? null : verdictTone}
            speakTone={speakTone}>
            {state.current ? <SpeechBox key={state.current.id} line={state.current} lang={lang} onDone={next} />
              : state.verdictShown && state.verdict ? <VerdictBox v={state.verdict} lang={lang} demo={state.mode === "demo"} sessionId={sessionId} ticker={state.ticker} onOpenReport={() => sessionId && onOpenReport(sessionId)} extra={verdictExtra} />
              : !sessionId ? <IdleBox lang={lang} text={demo ? `${t.welcome} ${t.welcomeDemo}` : t.welcome} />
              : !state.ended ? <WaitBox lang={lang} agents={state.agents} since={state.thinkingSince} stopping={state.stopping} loaded={state.id != null} />
              : <EndedBox lang={lang} status={state.status} />}
          </RoomScene>
        </Stage>

        <aside className="side" aria-label={t.minutes}>
          {scan && (
            <div className="card" style={{ padding: 16 }}>
              {scan.capped && <div className="warnstrip" role="alert" style={{ marginBottom: 8 }}>{lang === "ar" ? "وقفنا المسح لأن ميزانية التحليل لهذا الشهر خلصت. النتائج اللي خلصت محفوظة." : "The scan stopped: this month's analysis budget is used up. Finished results are kept."}</div>}
              <div className="row" style={{ justifyContent: "space-between" }}><h2 style={{ fontSize: 19 }}>{t.scanProgress}</h2><span className="pixel ltr muted">{Object.keys(scan.results).length} / {scan.tickers.length}</span></div>
              <ol className="board-rank" style={{ margin: "10px 0 0", padding: 0, maxHeight: 260, overflowY: "auto" }}>
                {scan.tickers.map((tk, i) => {
                  const r = scan.results[i];
                  const on = scan.sessions[i] === sessionId;
                  const reused = scan.reused?.[i];
                  return (
                    <li key={tk} style={{ outline: on ? "3px solid var(--orange)" : "none" }}>
                      <b className="pixel ltr" style={{ minWidth: 60 }}>{tk}</b>
                      {r ? <span className={`vchip ${RATING[r]?.tone ?? "none"}`}>{lang === "ar" ? RATING[r]?.ar : RATING[r]?.en}</span>
                        : <span className="muted">{on ? t.nowAnalyzing : "…"}</span>}
                      {reused && <span className="muted" style={{ fontSize: 12 }}>{lang === "ar" ? "♻ من تحليل اليوم" : "♻ from today"}</span>}
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
          {scan?.prescreen && (
            <div className="card" style={{ padding: 14 }}>
              <b>{lang === "ar" ? "💰 الفحص المجاني (قبل التحليل الكامل)" : "💰 Free pre-screen (before the full analysis)"}</b>
              <ol className="board-rank" style={{ margin: "8px 0 0", padding: 0, maxHeight: 200, overflowY: "auto" }}>
                {scan.prescreen.map((p) => (
                  <li key={p.ticker} style={{ opacity: scan.tickers.includes(p.ticker) ? 1 : 0.5 }}>
                    <b className="pixel ltr" style={{ minWidth: 60 }}>{p.ticker}</b>
                    <ShariaBadge symbol={p.ticker} />
                    <span className="ltr muted" style={{ fontSize: 12 }}>{p.score == null ? (lang === "ar" ? "بيانات غير كافية" : "not enough data")
                      : p.mode === "steady"
                        ? `${lang === "ar" ? "سنة بدون آخر شهر" : "12-1m"} ${fmtPct(p.ret_12_1 ?? 0, lang)} · ${lang === "ar" ? "أكبر هبوط" : "max drop"} ${fmtPct(-(p.max_drop ?? 0), lang)}`
                        : `${lang === "ar" ? "3 شهور" : "3m"} ${fmtPct(p.ret_3m ?? 0, lang)} · ${lang === "ar" ? "اتجاه" : "trend"} ${fmtPct(p.trend ?? 0, lang)}`}</span>
                    <span className="muted" style={{ fontSize: 12 }}>{scan.tickers.includes(p.ticker) ? (lang === "ar" ? "✓ للتحليل الكامل" : "✓ full analysis") : ""}</span>
                  </li>
                ))}
              </ol>
              <span className="muted" style={{ fontSize: 12 }}>{lang === "ar" ? "ترتيب فني من الأسعار فقط لتوفير التكلفة، مو توصية." : "A price-only ranking to save cost, not a recommendation."}</span>
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
            {state.portfolioUsed && <div className="costrow"><span>{state.portfolioBroker === "budget"
              ? (lang === "ar" ? "ليو يعرف المبلغ المتاح للاستثمار" : "Leo knows the budget you set")
              : (lang === "ar" ? "ليو يعرف محفظتك الحالية" : "Leo knows your current holdings")}</span><span>✓</span></div>}
            {sessionId && !scan && state.verdictShown && state.mode === "real" && sessionBudget && (
              <BudgetPlan url={`/api/sessions/${sessionId}/allocation`} budget={sessionBudget} onOpen={onOpenReport} />
            )}
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
                <LogItem key={l.id} l={l} sessionId={sessionId} />
              ))}
            </div>
          </div>
        </aside>
      </div>

      {scanDone && scan?.ranking && (scan.beginner
        ? <BeginnerGuide scanId={scan.id} onOpen={onOpenReport} onClose={() => setScan({ ...scan, ranking: null })} />
        : <Ranking scan={scan} onOpen={onOpenReport} onClose={() => setScan({ ...scan, ranking: null })} />)}
    </>
  );
}

function LogItem({ l, sessionId }: { l: Line; sessionId: string | null }) {
  const { prefs, t } = usePrefs();
  const lang = prefs.lang;
  const text = useLineText(l.texts, l.turnId, lang, !l.demo);
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The spoken line is a 1-3 sentence summary; the agent's complete write-up is one tap away, right here.
  useEffect(() => {
    if (!open || !sessionId || !l.turnId || l.demo) return;
    let alive = true;
    setBusy(true); setDetail(null);
    (async () => {
      const s = await api.get<SessionFull>(`/api/sessions/${sessionId}`);
      const turn = s.turns.find((x) => x.id === l.turnId);
      if (!turn) return null;
      if (lang === "en") return turn.detail_en;
      if (turn.detail_ar) return turn.detail_ar;
      const r = await api.post<{ detail_ar: string }>(`/api/turns/${turn.id}/translate`, { what: "detail_ar" }).catch(() => null);
      return r?.detail_ar ?? turn.detail_en;
    })().then((d) => { if (alive) setDetail(d); }).catch(() => { if (alive) setDetail(null); }).finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [open, sessionId, l.turnId, l.demo, lang]);
  const label = NODE_LABEL[l.node]?.[lang];
  return (
    <div className="logitem">
      <div className="row" style={{ justifyContent: "space-between", gap: 6 }}>
        <b style={{ color: charColor(l.character as CharKey) }}>{charName(l.character, lang)}{label && <span className="muted" style={{ fontSize: 12, fontWeight: 700 }}> · {label}</span>}</b>
        {l.turnId && !l.demo && sessionId && (
          <button className="linkish" style={{ fontSize: 12 }} aria-expanded={open} onClick={() => setOpen(!open)}>{open ? t.hideDetails : t.fullAnalysis}</button>
        )}
      </div>
      <div style={{ fontSize: 14, lineHeight: 1.6 }}>{text ? <Glossed text={text} /> : "…"}</div>
      {open && (
        <div className="detail" style={{ marginTop: 6, maxHeight: 420, overflowY: "auto", fontSize: 14 }}>
          {busy ? <span className="muted">{lang === "ar" ? t.translating : "…"}</span>
            : detail ? <Markdown text={detail} dir={lang === "ar" && !/^[\x00-\x7F\s]{40}/.test(detail) ? "rtl" : "ltr"} />
            : <span className="muted">{t.unavailable}</span>}
        </div>
      )}
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
        {(() => {
          const buys = scan.ranking!.filter((r) => r.rating === "Buy" || r.rating === "Overweight");
          return (
            <div className={`reco ${buys.length ? "buy" : "skip"}`} role="note" style={{ marginBottom: 10 }}>
              <b className="reco-h">{buys.length ? `✅ ${lang === "ar" ? "الفريق ينصح بشراء:" : "The team recommends buying:"} ` : `⏸ ${lang === "ar" ? "ولا سهم طلع قراره شراء هالمرة، الأفضل الانتظار." : "No stock came out as a buy this time; waiting is the call."}`}</b>
              {buys.length > 0 && <span className="pixel ltr">{buys.map((r) => r.ticker).join(" · ")}</span>}
            </div>
          );
        })()}
        <p className="muted" style={{ marginTop: 0 }}>{t.disclaimer}</p>
        <ol className="board-rank">
          {scan.ranking!.map((r, i) => (
            <li key={r.session_id}>
              <b className="pixel" style={{ fontSize: 20, width: 28 }}>{i + 1}</b>
              <b className="pixel ltr" style={{ minWidth: 70 }}>{r.ticker}</b>
              <ShariaBadge symbol={r.ticker} />
              {r.rating ? <span className={`vchip ${RATING[r.rating]?.tone ?? "none"}`}>{lang === "ar" ? RATING[r.rating]?.ar : RATING[r.rating]?.en}</span> : <span className="muted">{r.status}</span>}
              <span style={{ flex: 1 }} />
              <button className="ghost btn" onClick={() => onOpen(r.session_id)}>{t.view}</button>
            </li>
          ))}
        </ol>
        {scan.budget && <BudgetPlan url={`/api/scans/${scan.id}/allocation`} budget={scan.budget} onOpen={onOpen} />}
        <div className="row" style={{ justifyContent: "flex-end", marginTop: 14 }}><button className="primary btn" onClick={onClose}>{t.close}</button></div>
      </div>
    </div>
  );
}

function fmtTime(iso: string, lang: string) {
  return new Intl.DateTimeFormat(lang === "ar" ? "ar-SA-u-nu-latn-ca-gregory" : "en-US", { timeStyle: "short" }).format(new Date(iso));
}
