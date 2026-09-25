import { useEffect, useState } from "react";
import { api, ApiError, type Settings } from "../api";
import { SpriteSvg } from "../art/Sprite";
import { RATING, fmtPct, fmtUsd } from "../i18n";
import { usePrefs } from "../prefs";

type Decision = { date: string; ticker: string; rating: string; pending: boolean; raw: string | null; alpha: string | null; holding: string | null; reflection: string };
type Job = { id: string; tickers: string[]; dates: string[]; cells: number; status: string; done: number; error?: string;
  estimate: { known: boolean; low: number | null; high: number | null };
  summary: null | { resolved: number; pending: number; unscored: number; holding: string; by_rating: Record<string, { count: number; hit_rate: number | null; mean_alpha: number }> } };

const nyToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());
const daysAgo = (n: number) => { const d = new Date(); d.setDate(d.getDate() - n); return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(d); };

/** The framework's own memory: every decision is later settled against its regional benchmark. */
export function FrameworkMemory() {
  const { prefs } = usePrefs();
  const ar = prefs.lang === "ar";
  const [rows, setRows] = useState<Decision[] | null>(null);
  useEffect(() => { api.get<{ entries: Decision[] }>("/api/framework/decisions").then((r) => setRows(r.entries)).catch(() => setRows([])); }, []);
  return (
    <section className="card stack">
      <div className="row"><SpriteSvg name="Ollie" px={2} /><h2 style={{ fontSize: 20 }}>{ar ? "ذاكرة الإطار: كيف قيّم TradingAgents قراراته" : "Framework memory: how TradingAgents scored its own calls"}</h2></div>
      <p className="muted" style={{ margin: 0 }}>{ar
        ? "بعد كل قرار ينتظر الإطار أيام التداول المحددة، ثم يحسب العائد الفعلي والفرق عن المؤشر المرجعي (ألفا)، ويكتب درساً يستفيد منه الفريق في الجلسات القادمة."
        : "After each call the framework waits its holding period, then records the realised return and alpha against the benchmark, plus a lesson the team reads in later sessions."}</p>
      {rows === null ? <p aria-busy="true">…</p> : rows.length === 0 ? <p className="muted">{ar ? "ما فيه قرارات مسجلة في ذاكرة الإطار للحين." : "No decisions in the framework's memory yet."}</p> : (
        <div style={{ overflowX: "auto" }}>
          <table className="table">
            <thead><tr><th>{ar ? "السهم" : "Ticker"}</th><th>{ar ? "تاريخ التحليل" : "Date"}</th><th>{ar ? "القرار" : "Rating"}</th><th>{ar ? "الحالة" : "Status"}</th><th>{ar ? "العائد" : "Return"}</th><th>{ar ? "ألفا مقابل المؤشر" : "Alpha vs benchmark"}</th><th>{ar ? "المدة" : "Holding"}</th></tr></thead>
            <tbody>{rows.slice(0, 30).map((r, i) => {
              const rt = RATING[r.rating];
              return (
                <tr key={i}><td className="pixel ltr">{r.ticker}</td><td className="ltr">{r.date}</td>
                  <td>{rt ? <span className={`vchip ${rt.tone}`}>{ar ? rt.ar : rt.en}</span> : r.rating}</td>
                  <td>{r.pending ? (ar ? "بانتظار التسوية" : "Waiting to settle") : (ar ? "تمت التسوية" : "Settled")}</td>
                  <td className="ltr">{r.raw ?? "—"}</td><td className="ltr">{r.alpha ?? "—"}</td><td className="ltr">{r.holding ?? "—"}</td></tr>
              );
            })}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** The framework's backtest: the full team over a grid of past dates, scored per rating. */
export function Backtest({ settings }: { settings: Settings | null }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const ar = lang === "ar";
  const [tickers, setTickers] = useState("NVDA");
  const [start, setStart] = useState(daysAgo(60));
  const [end, setEnd] = useState(daysAgo(14));
  const [every, setEvery] = useState(14);
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const list = tickers.split(/[,\s،]+/).map((x) => x.trim().toUpperCase()).filter(Boolean).slice(0, 3);
  const cells = list.length * Math.min(12, Math.max(0, Math.floor((Date.parse(end) - Date.parse(start)) / 86400000 / every) + 1));
  const e = settings?.estimate;
  const est = e && e.known && e.low != null && e.high != null ? `${fmtUsd(e.low * cells, lang)} – ${fmtUsd(e.high * cells, lang)}` : (ar ? "غير معروفة لهذا المزوّد" : "unknown for this provider");

  useEffect(() => {
    if (!job || job.status !== "running") return;
    const h = setInterval(() => api.get<Job>(`/api/backtest/${job.id}`).then(setJob).catch(() => {}), 4000);
    return () => clearInterval(h);
  }, [job]);

  const run = async () => {
    setErr(null); setConfirming(false);
    try { setJob(await api.post<Job>("/api/backtest", { tickers: list, start, end, every_n_days: every })); }
    catch (x) { setErr(x instanceof ApiError && x.code === "no_key" ? (ar ? "يحتاج مفتاح النموذج من الإعدادات." : "Needs a model key in Settings.") : (ar ? "تأكد من الرموز والتواريخ." : "Check the tickers and dates.")); }
  };

  return (
    <section className="card stack">
      <div className="row"><SpriteSvg name="Tank" px={2} /><h2 style={{ fontSize: 20 }}>{ar ? "اختبار تاريخي (Backtest) من TradingAgents" : "Backtest (built into TradingAgents)"}</h2></div>
      <p className="muted" style={{ margin: 0 }}>{ar
        ? "الفريق كامل يحلل السهم في تواريخ سابقة (بدون ما يشوف اللي صار بعدها)، وبعدين نشوف كم مرة أصاب اتجاه كل قرار ومتوسط الألفا. كل خلية جلسة كاملة، فالتكلفة تتضاعف."
        : "The full team analyses the stock on past dates (without seeing what came after), then we score how often each rating got the direction right and its mean alpha. Every cell is a full session, so cost multiplies."}</p>
      <div className="grid2">
        <label className="stack" style={{ gap: 4 }}><span className="label">{ar ? "الرموز (حتى 3)" : "Tickers (up to 3)"}</span><input className="field pixel ltr" value={tickers} onChange={(x) => setTickers(x.target.value.toUpperCase())} /></label>
        <label className="stack" style={{ gap: 4 }}><span className="label">{ar ? "كل كم يوم" : "Every N days"}</span><input className="field ltr" type="number" min={1} max={30} value={every} onChange={(x) => setEvery(Number(x.target.value) || 7)} /></label>
        <label className="stack" style={{ gap: 4 }}><span className="label">{ar ? "من تاريخ" : "From"}</span><input className="field ltr" type="date" max={nyToday()} value={start} onChange={(x) => setStart(x.target.value)} /></label>
        <label className="stack" style={{ gap: 4 }}><span className="label">{ar ? "إلى تاريخ" : "To"}</span><input className="field ltr" type="date" max={nyToday()} value={end} onChange={(x) => setEnd(x.target.value)} /></label>
      </div>
      <div className="toggle"><span>{ar ? `عدد الخلايا: ${cells} · التكلفة التقديرية` : `Cells: ${cells} · estimated cost`}</span><b className="pixel ltr">{est}</b></div>
      {!confirming
        ? <button className="primary btn" style={{ alignSelf: "flex-start" }} disabled={cells === 0 || job?.status === "running"} onClick={() => setConfirming(true)}>{ar ? "شغّل الاختبار" : "Run backtest"}</button>
        : <div className="warnstrip row"><span>{ar ? `متأكد؟ بيشغّل ${cells} جلسة كاملة.` : `Sure? This runs ${cells} full sessions.`}</span>
            <button className="primary btn" style={{ height: 38, fontSize: 15 }} onClick={run}>{ar ? "نعم، شغّل" : "Yes, run"}</button>
            <button className="ghost btn" onClick={() => setConfirming(false)}>{ar ? "إلغاء" : "Cancel"}</button></div>}
      {err && <div className="warnstrip" role="alert">{err}</div>}
      {job && (
        <div className="stack" style={{ gap: 8 }} aria-live="polite">
          <div className="toggle"><span>{ar ? "التقدّم" : "Progress"}</span><b className="pixel ltr">{job.done} / {job.cells}{job.status === "running" ? " …" : ""}</b></div>
          {job.status === "error" && <div className="warnstrip">{ar ? "توقف الاختبار بسبب خطأ." : "The backtest stopped with an error."}</div>}
          {job.summary && (
            <table className="table">
              <thead><tr><th>{ar ? "القرار" : "Rating"}</th><th>{ar ? "العدد" : "Count"}</th><th>{ar ? "أصاب الاتجاه" : "Direction right"}</th><th>{ar ? "متوسط الألفا" : "Mean alpha"}</th></tr></thead>
              <tbody>{Object.entries(job.summary.by_rating).map(([r, s]) => (
                <tr key={r}><td>{RATING[r] ? (ar ? RATING[r].ar : RATING[r].en) : r}</td><td className="ltr">{s.count}</td>
                  <td className="ltr">{s.hit_rate == null ? (ar ? "لا يدّعي اتجاه" : "no direction") : fmtPct(s.hit_rate, lang)}</td>
                  <td className={`ltr ${s.mean_alpha >= 0 ? "pos" : "neg"}`}>{fmtPct(s.mean_alpha, lang)}</td></tr>
              ))}</tbody>
            </table>
          )}
          {job.summary && <p className="muted" style={{ margin: 0, fontSize: 13 }}>{ar
            ? `تمت تسوية ${job.summary.resolved} · بانتظار ${job.summary.pending}. النتائج إرشادية وليست مضمونة التكرار.`
            : `${job.summary.resolved} settled · ${job.summary.pending} pending. Indicative, not exactly repeatable.`}</p>}
        </div>
      )}
    </section>
  );
}
