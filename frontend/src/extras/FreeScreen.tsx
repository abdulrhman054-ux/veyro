import { useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "../api";
import { fmtNum, type Lang } from "../i18n";
import { usePrefs } from "../prefs";
import { SpriteSvg } from "../art/Sprite";

/** Free screen without AI (backend/veyro/screening.py): financial health, quality, trend and valuation from free data,
 *  then a screening verdict with its reasons. A filter to decide where to look, never a recommendation. */

export type Verdict = "pass" | "watch" | "exclude" | "insufficient" | "not_equity";
type Reason = { code: string; value?: number | string | null; known?: number | null };
export type ScreenResult = {
  symbol: string; name?: string | null; sector?: string | null; verdict: Verdict; reasons: Reason[];
  health?: { status: string; z?: number; reason?: string; missing?: string[]; year?: string | null };
  quality?: { status: string; score?: number; known?: number; financial?: boolean; roa?: number | null; tests?: Record<string, boolean | null>; loss_making?: boolean | null };
  trend?: { status: string; price_vs_ma200?: number; momentum_12_1?: number | null; volatility?: number; max_drawdown?: number; rsi?: number | null; flags?: string[]; sessions?: number };
  value?: { pe?: number | null; peer_pe?: number | null; pe_vs?: string | null; div_yield?: number | null; value_note?: string | null };
  cautions?: string[]; year?: string | null;
};

const VERDICT: Record<Verdict, { ar: string; en: string; tone: string }> = {
  pass: { ar: "يجتاز الفرز", en: "Passes the screen", tone: "buy" },
  watch: { ar: "مراقبة", en: "Watch", tone: "hold" },
  exclude: { ar: "استبعاد", en: "Exclude", tone: "sell" },
  insufficient: { ar: "بيانات ناقصة", en: "Not enough data", tone: "none" },
  not_equity: { ar: "مو سهم شركة", en: "Not a company share", tone: "none" },
};
export const verdictText = (v: string | null | undefined, lang: Lang) => (v && VERDICT[v as Verdict] ? VERDICT[v as Verdict][lang] : "—");
export const verdictTone = (v: string | null | undefined) => (v && VERDICT[v as Verdict] ? VERDICT[v as Verdict].tone : "none");

const pc = (x: number | null | undefined, digits = 0) => (x == null ? "—" : `${(x * 100).toFixed(digits)}%`);
/** A number kept in left-to-right order inside Arabic text (so "2%" never shows as "%2"). */
const N = ({ children }: { children: ReactNode }) => <bdi dir="ltr" className="num">{children}</bdi>;

/** Left-to-right isolate for a number inside a sentence ("Z'' = -2.31" never becomes "2.31-" in Arabic). */
const iso = (x: unknown) => `\u2066${x ?? "?"}\u2069`;

export function reasonText(r: Reason, lang: Lang): string {
  const ar = lang === "ar";
  const v = iso(r.value), k = iso(r.known);
  switch (r.code) {
    case "distress": return ar ? `خطر تعثّر مالي: مؤشر ألتمان ${iso("Z''")} = ${v} (أقل من ${iso("1.10")})` : `Financial distress risk: Altman ${iso("Z''")} = ${v} (below 1.10)`;
    case "weak_quality": return ar ? `جودة نتائج ضعيفة: ${v} من ${k} في مؤشر بيوتروسكي` : `Weak results quality: Piotroski ${v} of ${k}`;
    case "loss_and_downtrend": return ar ? "الشركة خسرانة في آخر سنة والسعر في اتجاه هابط" : "Loss-making in the last year and the price is in a downtrend";
    case "no_statements": return ar ? "ما قدرنا نجيب القوائم المالية السنوية، فما نحكم" : "Couldn't get the annual statements, so no judgement";
    case "healthy": return ar ? `وضع مالي سليم: ${iso("Z''")} = ${v} (فوق ${iso("2.60")})` : `Financially healthy: ${iso("Z''")} = ${v} (above 2.60)`;
    case "financial_profitable": return ar ? "شركة مالية رابحة وربحيتها ما تتراجع (مؤشر ألتمان ما ينطبق على البنوك والتأمين)" : "A profitable financial company whose returns aren't falling (Altman doesn't apply to banks and insurers)";
    case "good_quality": return ar ? `جودة نتائج جيدة: ${v} من ${k} في مؤشر بيوتروسكي` : `Good results quality: Piotroski ${v} of ${k}`;
    case "trend_unknown": return ar ? "تاريخ السعر أقصر من 200 يوم، فالاتجاه غير معروف" : "Less than 200 days of prices, so the trend is unknown";
    case "grey_zone": return ar ? `منطقة رمادية: ${iso("Z''")} = ${v} (بين ${iso("1.10")} و${iso("2.60")})، يحتاج متابعة` : `Grey zone: ${iso("Z''")} = ${v} (between 1.10 and 2.60), needs watching`;
    case "health_unknown": return ar ? "الوضع المالي غير معروف (بنود ناقصة في الميزانية)" : "Financial health unknown (balance-sheet lines missing)";
    case "financial_weak": return ar ? "شركة مالية ربحيتها ضعيفة أو تتراجع" : "A financial company with weak or falling returns";
    case "middling_quality": return ar ? `جودة نتائج متوسطة: ${v} من ${k}` : `Middling results quality: ${v} of ${k}`;
    case "quality_incomplete": return ar ? `جودة النتائج ما اكتمل فحصها (${k} من ${iso(9)} بنود متوفرة)` : `Results quality not fully checked (${k} of 9 tests available)`;
    case "downtrend": return ar ? "السعر تحت متوسط 200 يوم والمتوسط القصير تحت الطويل (اتجاه هابط)" : "Price below its 200-day average, and the 50-day below the 200-day (downtrend)";
    case "mixed_signals": return ar ? "إشارات مختلطة" : "Mixed signals";
    case "not_equity": return ar ? `مو سهم شركة (${v})، الفرز للأسهم فقط` : `Not a company share (${v}); the screen is for stocks only`;
    default: return r.code;
  }
}

const TESTS: Record<string, [string, string]> = {
  roa_positive: ["العائد على الأصول موجب (رابحة)", "Return on assets positive (profitable)"],
  cfo_positive: ["التدفق النقدي التشغيلي موجب", "Operating cash flow positive"],
  roa_up: ["العائد على الأصول تحسّن عن السنة السابقة", "Return on assets improved"],
  cash_backed: ["النقد التشغيلي أكبر من صافي الربح (أرباح حقيقية)", "Cash flow above net income (cash-backed earnings)"],
  leverage_down: ["نسبة الديون طويلة الأجل للأصول نزلت", "Long-term debt / assets fell"],
  liquidity_up: ["نسبة التداول (السيولة) تحسّنت", "Current ratio improved"],
  no_new_shares: ["ما أصدرت أسهم جديدة", "No new shares issued"],
  margin_up: ["هامش الربح الإجمالي تحسّن", "Gross margin improved"],
  turnover_up: ["دوران الأصول تحسّن (مبيعات أكثر لكل ريال أصول)", "Asset turnover improved"],
  roa_not_falling: ["العائد على الأصول ما تراجع", "Return on assets not falling"],
};

function healthLine(r: ScreenResult, ar: boolean): ReactNode {
  const h = r.health;
  if (!h) return "—";
  if (h.status === "not_applicable") return ar ? "ما ينطبق (شركة مالية)" : "n/a (financial company)";
  if (h.status === "unknown") return ar ? "غير معروف" : "unknown";
  const zone = { safe: ar ? "سليم" : "safe", grey: ar ? "رمادي" : "grey", distress: ar ? "خطر تعثّر" : "distress" }[h.status] ?? h.status;
  return <>{zone} · <N>Z&apos;&apos; {h.z}</N></>;
}
function qualityLine(r: ScreenResult, ar: boolean): ReactNode {
  const q = r.quality;
  if (!q) return "—";
  if (q.financial) return q.status === "good" ? (ar ? "رابحة ومستقرة" : "profitable, steady") : q.status === "unknown" ? (ar ? "غير معروف" : "unknown") : (ar ? "ضعيفة" : "weak");
  if (q.known == null || q.known < 5) return ar ? "غير معروف" : "unknown";
  return <><N>{q.score}/{q.known}</N>{q.known < 9 ? (ar ? " (بنود متوفرة)" : " (tests available)") : ""}</>;
}
function trendLine(r: ScreenResult, ar: boolean): ReactNode {
  const t = r.trend;
  if (!t || t.status === "unknown") return ar ? "غير معروف" : "unknown";
  const s = { up: ar ? "صاعد" : "up", down: ar ? "هابط" : "down", mixed: ar ? "مختلط" : "mixed" }[t.status] ?? t.status;
  return <>{s} · {ar ? "تذبذب" : "vol"} <N>{pc(t.volatility)}</N> · {ar ? "أكبر هبوط" : "max drop"} <N>{pc(t.max_drawdown)}</N></>;
}
function valueCell(r: ScreenResult, ar: boolean): ReactNode {
  const v = r.value;
  if (!v || v.pe == null) return v?.value_note === "loss_making" ? (ar ? "خسرانة (ما لها مكرر ربحية)" : "loss-making (no P/E)") : "—";
  return <>{ar ? "مكرر الربحية" : "P/E"} <N>{v.pe}</N>
    {v.peer_pe ? <> · {v.pe_vs === "sector" ? (ar ? "قطاعه" : "sector") : (ar ? "السوق" : "market")} <N>{v.peer_pe}</N></> : null}
    {v.div_yield != null ? <> · {ar ? "توزيعات" : "yield"} <N>{pc(v.div_yield, 1)}</N></> : null}</>;
}

export function FreeScreenModal({ symbols, onClose, onAnalyse }: { symbols: string[]; onClose: () => void; onAnalyse?: (syms: string[]) => void }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang, ar = lang === "ar";
  const [res, setRes] = useState<Record<string, ScreenResult> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const joined = symbols.join(",");
  useEffect(() => {
    let alive = true;
    setRes(null); setErr(null);
    api.post<{ results: Record<string, ScreenResult> }>("/api/screen/free", { symbols })
      .then((r) => alive && setRes(r.results))
      .catch((e) => alive && setErr(e instanceof ApiError && e.code === "invalid_ticker" ? (ar ? "رمز غير صالح." : "Invalid symbol.") : (ar ? "ما قدرنا نجيب البيانات الحين. جرّب بعد شوي." : "Couldn't get the data right now. Try again shortly.")));
    return () => { alive = false; };
  }, [joined]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const rows = res ? symbols.map((s) => res[s]).filter(Boolean) : [];
  const passes = rows.filter((r) => r.verdict === "pass").map((r) => r.symbol);
  const counts = (["pass", "watch", "exclude", "insufficient"] as Verdict[]).map((v) => [v, rows.filter((r) => r.verdict === v).length] as const);
  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-labelledby="fs-h" onClick={onClose}>
      <div className="modal stack free-screen" style={{ gap: 12, maxWidth: 980 }} onClick={(e) => e.stopPropagation()} dir={ar ? "rtl" : "ltr"}>
        <div className="row" style={{ gap: 10, flexWrap: "nowrap" }}>
          <SpriteSvg name="Benny" px={2} />
          <div className="stack" style={{ gap: 2 }}>
            <h2 id="fs-h" style={{ fontSize: 22, margin: 0 }}>{ar ? "🧮 فرز مجاني بدون ذكاء اصطناعي" : "🧮 Free screen without AI"}</h2>
            <span className="muted" style={{ fontSize: 13, lineHeight: 1.7 }}>{ar
              ? "أربع فحوص من بيانات مجانية: السلامة المالية (ألتمان Z'')، جودة النتائج (بيوتروسكي F)، الاتجاه والمخاطرة من السعر، والتقييم مقابل القطاع. بدون أي نموذج وبدون تكلفة."
              : "Four checks from free data: financial health (Altman Z''), results quality (Piotroski F), trend and risk from prices, and valuation against the sector. No model, no cost."}</span>
          </div>
        </div>
        <div className="warnstrip" role="note" style={{ fontSize: 13, lineHeight: 1.7 }}>{ar
          ? "أداة فرز لتعرف وين المخاطر، مو توصية شراء. هذي المؤشرات لها أدلة بحثية على المدى الطويل (ألتمان يتوقع التعثّر المالي، وبيوتروسكي ارتبط بأداء أفضل لأسهم القيمة تاريخياً)، لكن أثرها في السوق ضعف مع الوقت، وما فيه دليل كافي عليها في السوق السعودي. التقييم يُعرض للسياق فقط ولا يدخل في الحكم، لأن الرخص وحده ممكن يكون فخ."
          : "A screen to see where the risks are, not a buy recommendation. These measures have long-run research behind them (Altman predicts financial distress; Piotroski was linked to better returns for value stocks historically), but their market edge has weakened over time and there is little evidence for the Saudi market. Valuation is shown for context only and never decides the verdict: cheap alone can be a trap."}</div>
        {err && <div className="warnstrip" role="alert">{err}</div>}
        {!res && !err && <p aria-busy="true" className="muted">{ar ? "بيني يقرأ القوائم المالية السنوية… (أول مرة لكل سهم تاخذ ثواني)" : "Benny is reading the annual statements… (a few seconds per stock the first time)"}</p>}
        {res && <>
          <div className="row" style={{ gap: 8 }} data-counts>
            {counts.map(([v, n]) => n > 0 && <span key={v} className={`vchip ${verdictTone(v)}`}>{verdictText(v, lang)}: {fmtNum(n, lang)}</span>)}
          </div>
          <div className="table-scroll">
            <table className="table free-screen-tbl">
              <thead><tr>
                <th>{ar ? "السهم" : "Stock"}</th><th>{ar ? "نتيجة الفرز" : "Screen"}</th><th>{ar ? "السلامة المالية" : "Financial health"}</th>
                <th>{ar ? "جودة النتائج" : "Results quality"}</th><th>{ar ? "الاتجاه والمخاطرة" : "Trend and risk"}</th><th>{ar ? "التقييم (للسياق)" : "Valuation (context)"}</th>
              </tr></thead>
              <tbody>
                {rows.map((r) => (
                  <FragmentRow key={r.symbol} r={r} ar={ar} lang={lang} open={open === r.symbol} onToggle={() => setOpen((o) => (o === r.symbol ? null : r.symbol))} />
                ))}
              </tbody>
            </table>
          </div>
          <span className="muted" style={{ fontSize: 12 }}>{ar
            ? "من القوائم السنوية وأسعار Yahoo المجانية (تتحدث أسبوعياً). البند الناقص يظهر «غير معروف» وما نفترضه. كل نتيجة تنحفظ وتنقاس بعد 20 و60 يوم تداول في «السجل ← لوحة الثقة»."
            : "From free Yahoo annual statements and prices (refreshed weekly). A missing line shows as unknown and is never assumed. Each result is saved and scored 20 and 60 trading days later in History → Trust dashboard."}</span>
        </>}
        <div className="row" style={{ gap: 10, justifyContent: "flex-end" }}>
          {onAnalyse && res && passes.length > 0 && (
            <button className="ghost btn" onClick={() => onAnalyse(passes)} data-analyse-passes>{ar ? `حلّل المجتازين فقط بالفريق (${passes.length})` : `Analyse only those that passed (${passes.length})`}</button>
          )}
          <button className="primary btn" onClick={onClose}>{ar ? "تم" : "Done"}</button>
        </div>
      </div>
    </div>
  );
}

function FragmentRow({ r, ar, lang, open, onToggle }: { r: ScreenResult; ar: boolean; lang: Lang; open: boolean; onToggle: () => void }) {
  const tests = r.quality?.tests ?? {};
  return (
    <>
      <tr data-verdict={r.verdict}>
        <td><button className="linkish" onClick={onToggle} aria-expanded={open}><b className="pixel ltr">{r.symbol}</b></button>
          {r.name && <div className="muted small">{r.name}</div>}</td>
        <td><span className={`vchip ${verdictTone(r.verdict)}`}>{verdictText(r.verdict, lang)}</span>
          {(r.cautions ?? []).includes("stretched") && <div className="muted small">⚠ {ar ? "ارتفع بسرعة" : "rose fast"} (<N>RSI {r.trend?.rsi}</N>)</div>}
          {(r.cautions ?? []).includes("oversold") && <div className="muted small">⚠ {ar ? "نزل بسرعة" : "fell fast"} (<N>RSI {r.trend?.rsi}</N>)</div>}</td>
        <td>{healthLine(r, ar)}</td>
        <td>{qualityLine(r, ar)}</td>
        <td>{trendLine(r, ar)}</td>
        <td>{valueCell(r, ar)}</td>
      </tr>
      <tr className="fs-why" hidden={!open && r.verdict !== "exclude"}>
        <td colSpan={6}>
          <ul style={{ margin: 0, paddingInlineStart: 18, lineHeight: 1.8 }}>
            {r.reasons.map((x, i) => <li key={i}>{reasonText(x, lang)}</li>)}
          </ul>
          {open && Object.keys(tests).length > 0 && (
            <div className="fs-tests" aria-label={ar ? "بنود جودة النتائج" : "Quality tests"}>
              {Object.entries(tests).map(([k, v]) => (
                <span key={k} className={`fs-test ${v === true ? "ok" : v === false ? "no" : "na"}`}>{v === true ? "✓" : v === false ? "✗" : "?"} {TESTS[k]?.[ar ? 0 : 1] ?? k}</span>
              ))}
            </div>
          )}
          {open && r.year && <div className="muted small">{ar ? `آخر سنة مالية: ${r.year}` : `Latest fiscal year: ${r.year}`}</div>}
        </td>
      </tr>
    </>
  );
}

/** Trust dashboard section: how screened stocks did against their index afterwards. */
type Track = { min_sample: number; horizons: number[]; by_verdict: Record<string, { logged: number; horizons: Record<string, { n: number; waiting: number; avg_excess: number | null; beat_index: number | null; ci_low: number | null; ci_high: number | null; enough: boolean }> }> };

export function FreeScreenTrack({ active = true }: { active?: boolean }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang, ar = lang === "ar";
  const [d, setD] = useState<Track | null>(null);
  useEffect(() => { if (active) api.get<Track>("/api/screen/free/track").then(setD).catch(() => {}); }, [active]);
  if (!d) return null;
  const total = Object.values(d.by_verdict).reduce((s, v) => s + v.logged, 0);
  if (!total) return null;
  return (
    <div className="stack" style={{ gap: 8 }} data-screen-track>
      <b>{ar ? "🧮 سجل الفرز المجاني: هل أفاد؟" : "🧮 Free screen record: was it useful?"}</b>
      <span className="muted small">{ar
        ? "عائد السهم ناقص عائد مؤشر سوقه بعد 20 و60 يوم تداول من الفرز. المهم: هل المجتازين تفوقوا على المستبعدين؟"
        : "The stock's return minus its market index 20 and 60 trading days after the screen. The question: did the stocks that passed beat those excluded?"}</span>
      <div className="table-scroll">
        <table className="table">
          <thead><tr><th>{ar ? "النتيجة" : "Verdict"}</th>
            {d.horizons.map((h) => <th key={h}>{ar ? `بعد ${h} يوم: متوسط التفوّق · نسبة التفوّق` : `After ${h} days: avg excess · beat the index`}</th>)}</tr></thead>
          <tbody>
            {(["pass", "watch", "exclude"] as const).map((v) => (
              <tr key={v}><td><span className={`vchip ${verdictTone(v)}`}>{verdictText(v, lang)}</span> <span className="muted small">({fmtNum(d.by_verdict[v]?.logged ?? 0, lang)})</span></td>
                {d.horizons.map((h) => {
                  const x = d.by_verdict[v]?.horizons[String(h)];
                  return <td key={h}>{x && x.n ? <><N>{pc(x.avg_excess, 1)}</N> · <N>{pc(x.beat_index)}</N> (<N>n={x.n}</N>)</> : "—"}
                    {x && x.waiting > 0 && <span className="muted small"> · {ar ? `${x.waiting} تنتظر` : `${x.waiting} waiting`}</span>}</td>;
                })}</tr>
            ))}
          </tbody>
        </table>
      </div>
      <span className="muted small">{ar ? `أقل من ${d.min_sample} نتيجة لكل خانة = عينة صغيرة ما يُحكم عليها.` : `Fewer than ${d.min_sample} results in a cell is too few to judge.`}</span>
    </div>
  );
}
