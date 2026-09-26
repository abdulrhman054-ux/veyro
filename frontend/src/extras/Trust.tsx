import { useEffect, useState } from "react";
import { api } from "../api";
import { SpriteSvg } from "../art/Sprite";
import { RATING, fmtNum } from "../i18n";
import { usePrefs } from "../prefs";
import { FreeScreenTrack } from "./FreeScreen";

type Agg = { n: number; hits: number; hit_rate: number | null; avg_edge: number | null; sessions?: number;
  ci_low?: number | null; ci_high?: number | null; enough?: boolean; waiting?: number };
type Trust = { overall: Agg & { sessions: number }; months: (Agg & { month: string; sessions: number })[];
  by_rating: Record<string, Agg & { sessions: number }>; by_model: (Agg & { model: string; sessions: number; avg_cost: number | null })[];
  min_sample: number; pending?: number; min_age_days?: number; horizon?: number; horizons?: Record<string, Agg>; paper: { currency: string; ret: number | null; bench_ret: number | null }[] };

const pct = (v: number | null | undefined, signed = false) => v == null ? "—"
  : `${signed ? (v >= 0 ? "+" : "−") : ""}${fmtNum(Math.abs(v * 100), "en", { maximumFractionDigits: 1 })}%`;

/** "Can I trust the team?": every finished call scored against its market index, with honest sample sizes. */
export function TrustDashboard({ active = true }: { active?: boolean }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang, ar = lang === "ar";
  const [d, setD] = useState<Trust | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => { if (active) api.get<Trust>("/api/trust").then(setD).catch(() => {}); }, [active]);
  if (!d) return null;
  const o = d.overall;
  const small = o.n < d.min_sample;
  const paper = d.paper[0];
  return (
    <section className="card stack trust" style={{ gap: 14 }} aria-labelledby="trust-h">
      <div className="row" style={{ gap: 10 }}><SpriteSvg name="Bruno" px={2} />
        <div className="stack" style={{ gap: 0 }}>
          <h2 id="trust-h" style={{ fontSize: 22, margin: 0 }}>{ar ? "لوحة الثقة: هل أصاب الفريق؟" : "Trust dashboard: was the team right?"}</h2>
          <span className="muted" style={{ fontSize: 14 }}>{ar
            ? "كل قرار حقيقي منتهي نقيسه بعد 5 أيام تداول من القرار (وبعد 20 يوم): عائد السهم ناقص عائد مؤشر سوقه بنفس الفترة بالضبط. «شراء» يصيب إذا تفوّق على المؤشر، و«بيع» إذا تأخر عنه. «احتفاظ» ما ينحسب، ونفس السهم بنفس القرار خلال 5 أيام ينحسب مرة."
            : "Every finished real call is scored 5 trading days after it (and 20): the stock's return minus its market index over exactly that window. A Buy is right if it beat the index, a Sell if it lagged. Hold isn't scored; the same stock with the same call within 5 days counts once."}</span>
        </div>
      </div>

      <div className="trust-tiles">
        <div className="stat"><span className="muted">{ar ? "قرارات محسوبة" : "Scored calls"}</span><b className="ltr">{fmtNum(o.n, lang)}</b>
          <span className="muted small">{ar ? `من ${fmtNum(o.sessions, lang)} جلسة` : `of ${fmtNum(o.sessions, lang)} sessions`}</span>
          {!!d.pending && <span className="muted small" data-waiting>{ar ? `${fmtNum(d.pending, lang)} قرار تنتظر (ما مرّ عليها ${d.min_age_days} أيام تداول)` : `${fmtNum(d.pending, lang)} calls are waiting (not yet ${d.min_age_days} trading days old)`}</span>}</div>
        <div className="stat"><span className="muted">{ar ? "نسبة الإصابة (5 أيام)" : "Hit rate (5 days)"}</span><b className="ltr">{o.n ? pct(o.hit_rate) : "—"}</b>
          {o.ci_low != null && <span className="muted small" data-ci>{ar ? "المدى المرجّح (95٪)" : "likely range (95%)"}: <span className="ltr">{pct(o.ci_low)}–{pct(o.ci_high)}</span></span>}
          <span className="muted small">{ar ? "العشوائي حوالي 50٪" : "a coin flip is about 50%"}</span></div>
        {d.horizons?.["20"] && <div className="stat"><span className="muted">{ar ? "نسبة الإصابة (20 يوم)" : "Hit rate (20 days)"}</span>
          <b className="ltr">{d.horizons["20"].n ? pct(d.horizons["20"].hit_rate) : "—"}</b>
          <span className="muted small">{ar ? `${d.horizons["20"].n} محسوبة · ${d.horizons["20"].waiting ?? 0} تنتظر` : `${d.horizons["20"].n} scored · ${d.horizons["20"].waiting ?? 0} waiting`}</span></div>}
        <div className="stat"><span className="muted">{ar ? "متوسط التفوّق" : "Average edge"}</span><b className="ltr">{pct(o.avg_edge, true)}</b>
          <span className="muted small">{ar ? "مقابل المؤشر، باتجاه القرار" : "vs the index, in the call's direction"}</span></div>
        <div className="stat"><span className="muted">{ar ? "المحفظة الافتراضية" : "Virtual portfolio"}</span><b className="ltr">{pct(paper?.ret, true)}</b>
          <span className="muted small">{ar ? "المؤشر" : "index"} <span className="ltr">{pct(paper?.bench_ret, true)}</span></span></div>
      </div>
      {small && <div className="warnstrip" role="note">{ar
        ? `العينة صغيرة (${o.n} قرار). نحتاج ${d.min_sample} على الأقل قبل ما نحكم، فلا تبني ثقتك على هالأرقام للحين. المدى المرجّح يوضح كم الرقم غير أكيد.`
        : `Small sample (${o.n} calls). We need at least ${d.min_sample} before judging, so don't lean on these numbers yet; the likely range shows how unsure the number is.`}</div>}

      {d.months.length > 0 && (
        <div className="stack" style={{ gap: 6 }}>
          <b>{ar ? "نسبة الإصابة شهرياً" : "Hit rate by month"}</b>
          <div className="mbars" role="img" aria-label={d.months.map((m) => `${m.month}: ${pct(m.hit_rate)} (${m.n})`).join(", ")} dir="ltr">
            <i className="half" aria-hidden="true"><span>50%</span></i>
            {d.months.map((m, i) => (
              <div key={m.month} className="mbar" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} tabIndex={0}>
                <div className="track"><div className="fill" style={{ height: `${(m.hit_rate ?? 0) * 100}%`, opacity: m.n ? 1 : 0.25 }} /></div>
                <span className="v">{m.n ? pct(m.hit_rate) : "—"}</span>
                <span className="m">{m.month.slice(2)}</span>
                {hover === i && <div className="tip" role="tooltip" dir={ar ? "rtl" : "ltr"}>
                  <b className="ltr">{m.month}</b><br />{ar ? "إصابة" : "Hits"} {m.hits}/{m.n} · {ar ? "تفوّق" : "edge"} <span className="ltr">{pct(m.avg_edge, true)}</span><br />
                  <span className="muted">{ar ? `${m.sessions} جلسة` : `${m.sessions} sessions`}</span></div>}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid2">
        <div className="stack" style={{ gap: 6 }}>
          <b>{ar ? "حسب القرار" : "By call"}</b>
          <table className="plan-t"><thead><tr><th>{ar ? "القرار" : "Call"}</th><th>{ar ? "محسوبة" : "Scored"}</th><th>{ar ? "إصابة" : "Hit rate"}</th><th>{ar ? "تفوّق" : "Edge"}</th></tr></thead>
            <tbody>{["Buy", "Overweight", "Hold", "Underweight", "Sell"].filter((r) => d.by_rating[r]).map((r) => (
              <tr key={r}><td><span className={`vchip ${RATING[r]?.tone ?? "none"}`}>{ar ? RATING[r].ar : RATING[r].en}</span></td>
                <td className="ltr">{r === "Hold" ? (ar ? "لا تُحسب" : "not scored") : `${d.by_rating[r].n}/${d.by_rating[r].sessions}`}</td>
                <td className="ltr">{pct(d.by_rating[r].hit_rate)}</td><td className="ltr">{pct(d.by_rating[r].avg_edge, true)}</td></tr>))}</tbody></table>
        </div>
        <div className="stack" style={{ gap: 6 }}>
          <b>{ar ? "حسب النموذج" : "By model"}</b>
          <div className="tablewrap"><table className="plan-t"><thead><tr><th>{ar ? "النماذج" : "Models"}</th><th>{ar ? "محسوبة" : "Scored"}</th><th>{ar ? "إصابة" : "Hit rate"}</th><th>{ar ? "تكلفة الجلسة" : "Cost/session"}</th></tr></thead>
            <tbody>{d.by_model.map((m) => (
              <tr key={m.model}><td className="ltr" style={{ whiteSpace: "normal", fontSize: 12 }}>{m.model}</td><td className="ltr">{m.n}/{m.sessions}</td>
                <td className="ltr">{pct(m.hit_rate)}</td><td className="ltr">{m.avg_cost != null ? `$${fmtNum(m.avg_cost, "en", { maximumFractionDigits: 2 })}` : "—"}</td></tr>))}</tbody></table></div>
        </div>
      </div>
      <FreeScreenTrack active={active} />
      <p className="muted" style={{ margin: 0, fontSize: 12 }}>{ar
        ? "أرقام محسوبة مباشرة من الأسعار بدون ذكاء اصطناعي. الأداء السابق ما يضمن المستقبل، وليست نصيحة مالية."
        : "Computed straight from prices, no AI involved. Past results don't guarantee the future; not financial advice."}</p>
    </section>
  );
}
