import type { SessionFull, Turn } from "../api";
import { SpriteSvg } from "../art/Sprite";
import { RATING, charName, fmtNum, fmtUsd, type CharKey, type Lang } from "../i18n";

/** Values the framework itself wrote in its structured outputs (never computed or invented by Veyro). */
export type FrameworkFigures = {
  rmRecommendation?: string; traderAction?: string; entryPrice?: number | null; stopLoss?: number | null;
  positionSizing?: string | null; priceTarget?: number | null; timeHorizon?: string | null;
  sentimentBand?: string; sentimentScore?: number; sentimentConfidence?: string;
};

const field = (text: string, label: string): string | null => {
  const m = new RegExp(`\\*\\*${label}\\*\\*:\\s*([^\\n]+)`, "i").exec(text);
  if (!m) return null;
  const v = m[1].replace(/\*\*/g, "").trim();
  return /^not provided$/i.test(v) ? null : v;
};
const num = (v: string | null) => {
  if (!v) return null;
  const m = /-?\d[\d,]*(\.\d+)?/.exec(v);
  return m ? Number(m[0].replace(/,/g, "")) : null;
};

export function extractFigures(turns: Turn[]): FrameworkFigures {
  const by = (node: string) => turns.filter((t) => t.node === node).at(-1)?.detail_en ?? "";
  const rm = by("Research Manager"), tr = by("Trader"), pm = by("Portfolio Manager"), se = by("Sentiment Analyst");
  const sent = /\*\*Overall Sentiment:\*\*\s*\*\*(.+?)\*\*\s*\(Score:\s*([\d.]+)\/10\)/i.exec(se);
  const conf = /\*\*Confidence:\*\*\s*(\w+)/i.exec(se);
  return {
    rmRecommendation: field(rm, "Recommendation") ?? undefined,
    traderAction: field(tr, "Action") ?? undefined,
    entryPrice: num(field(tr, "Entry Price")), stopLoss: num(field(tr, "Stop Loss")),
    positionSizing: field(tr, "Position Sizing"),
    priceTarget: num(field(pm, "Price Target")), timeHorizon: field(pm, "Time Horizon"),
    sentimentBand: sent?.[1], sentimentScore: sent ? Number(sent[2]) : undefined, sentimentConfidence: conf?.[1],
  };
}

const BAND_AR: Record<string, string> = {
  Bullish: "متفائل", "Mildly Bullish": "متفائل قليلاً", Neutral: "محايد", Mixed: "مختلط", "Mildly Bearish": "متشائم قليلاً", Bearish: "متشائم",
};
const ACTION_AR: Record<string, string> = { Buy: "شراء", Hold: "احتفاظ", Sell: "بيع" };
const CONF_AR: Record<string, string> = { Low: "منخفضة", Medium: "متوسطة", High: "عالية" };

export function KeyFigures({ s, lang }: { s: SessionFull; lang: Lang }) {
  if (s.mode === "demo") return null;
  const f = extractFigures(s.turns);
  const ar = lang === "ar";
  const na = ar ? "لم يحدده" : "not given";
  const cell = (who: "Leo" | "Buzz", label: string, value: React.ReactNode) => (
    <div className="figure">
      <div className="row" style={{ gap: 6 }}><SpriteSvg name={who} px={1} /><span className="label">{label}</span></div>
      <b className="ltr" style={{ fontSize: 17 }}>{value}</b>
    </div>
  );
  const rating = (r?: string) => (r ? (RATING[r] ? (ar ? RATING[r].ar : RATING[r].en) : r) : na);
  return (
    <section className="card stack" style={{ gap: 10 }}>
      <h2 style={{ fontSize: 19 }}>{ar ? "أرقام الفريق الرئيسية" : "The team's key figures"}</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 8 }}>
        {cell("Leo", ar ? "توصية مدير البحث" : "Research Manager", rating(f.rmRecommendation))}
        {cell("Leo", ar ? "قرار المتداول" : "Trader action", f.traderAction ? (ar ? ACTION_AR[f.traderAction] ?? f.traderAction : f.traderAction) : na)}
        {cell("Leo", ar ? "سعر الدخول المقترح" : "Proposed entry", f.entryPrice != null ? fmtUsd(f.entryPrice, lang) : na)}
        {cell("Leo", ar ? "وقف الخسارة المقترح" : "Proposed stop-loss", f.stopLoss != null ? fmtUsd(f.stopLoss, lang) : na)}
        {cell("Leo", ar ? "السعر المستهدف" : "Price target", f.priceTarget != null ? fmtUsd(f.priceTarget, lang) : na)}
        {cell("Buzz", ar ? "مؤشر المزاج (من 10)" : "Sentiment score (/10)",
          f.sentimentScore != null ? `${fmtNum(f.sentimentScore, lang, { maximumFractionDigits: 1 })} · ${ar ? BAND_AR[f.sentimentBand ?? ""] ?? f.sentimentBand : f.sentimentBand}` : na)}
        {!ar && f.timeHorizon && cell("Leo", "Time horizon", f.timeHorizon)}
        {!ar && f.positionSizing && cell("Leo", "Position sizing", f.positionSizing)}
        {f.sentimentConfidence && cell("Buzz", ar ? "ثقة محلل المزاج" : "Sentiment confidence", ar ? CONF_AR[f.sentimentConfidence] ?? f.sentimentConfidence : f.sentimentConfidence)}
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        {ar ? "هذي القيم كتبها وكلاء الإطار أنفسهم في مخرجاتهم، وهي تقديرات منهم وليست أسعار سوق." : "These values were written by the framework's agents in their own outputs. They are the agents' estimates, not market prices."}
      </p>
    </section>
  );
}

export function TeamAndMemory({ s, lang }: { s: SessionFull; lang: Lang }) {
  const c = s.config;
  if (!c) return null;
  const ar = lang === "ar";
  const onBreak = c.on_break ?? [];
  const notices: string[] = [];
  if (c.optional_data && !c.optional_data.fred) notices.push(ar ? "بيانات الاقتصاد الكلي (FRED) غير مفعّلة: تحتاج مفتاح اختياري من الإعدادات." : "Macro data (FRED) is off: it needs an optional key in Settings.");
  if (c.optional_data && c.optional_data.jev === false) notices.push(ar ? "تنقية منشورات التواصل (Jev) غير مفعّلة (اختياري)." : "Social post screening (Jev) is off (optional).");
  if (c.optional_data && !c.optional_data.alpha_vantage) notices.push(ar ? "Alpha Vantage غير مفعّل (اختياري). المصدر الأساسي Yahoo Finance شغّال." : "Alpha Vantage is off (optional). The main source, Yahoo Finance, is on.");
  return (
    <section className="card stack" style={{ gap: 8, fontSize: 15 }}>
      <h2 style={{ fontSize: 19 }}>{ar ? "إعداد الجلسة" : "Session setup"}</h2>
      <div>{ar ? "نوع الأصل" : "Asset type"}: <b>{c.asset_type === "crypto" ? (ar ? "عملة رقمية" : "Crypto") : (ar ? "سهم" : "Stock")}</b></div>
      {c.trade_date && <div>{ar ? "تاريخ التحليل" : "Analysis date"}: <b className="ltr">{c.trade_date}</b>{c.past_date && <span className="muted"> · {ar ? "تحليل بتاريخ سابق (الإطار ما يشوف اللي بعده)" : "past date (the framework sees nothing after it)"}</span>}</div>}
      {c.resumed && <div className="muted">{ar ? "هذي الجلسة كمّلت من حيث توقفت (نقطة حفظ الإطار)." : "This session resumed from the framework's checkpoint."}</div>}
      {c.reasoning && c.reasoning !== "default" && <div>{ar ? "عمق التفكير" : "Reasoning depth"}: <b>{c.reasoning}</b></div>}
      {c.export_dir && <a className="ghost btn" style={{ alignSelf: "flex-start", display: "inline-flex", alignItems: "center", textDecoration: "none", color: "inherit" }}
        href={`/api/sessions/${s.id}/export.zip`} download>{ar ? "تنزيل تقرير الإطار الكامل (ZIP)" : "Download the framework's full report (ZIP)"}</a>}
      {c.debate_rounds && <div>{ar ? "جولات نقاش بولت وبرونو" : "Bull/Bear debate rounds"}: <b className="ltr">{c.debate_rounds}</b> · {ar ? "جولات فريق المخاطر" : "Risk rounds"}: <b className="ltr">{c.risk_rounds}</b></div>}
      {onBreak.length > 0 && <div>{ar ? "في استراحة" : "On a break"}: <b>{onBreak.map((n) => charName(n as CharKey, lang)).join(ar ? "، " : ", ")}</b></div>}
      <div>{ar ? "المؤشر المرجعي للمقارنة" : "Benchmark"}: <b className="ltr">{c.benchmark ?? "SPY"}</b></div>
      {c.portfolio_context && <details><summary style={{ cursor: "pointer", fontWeight: 700 }}>{ar ? "محفظتك كما شافها ليو وقت القرار (النص الأصلي بالإنجليزي)" : "Your book, as Leo saw it"}</summary>
        <pre className="ltr" style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{c.portfolio_context}</pre></details>}
      {c.past_context && <details><summary style={{ cursor: "pointer", fontWeight: 700 }}>{ar ? "دروس من قرارات سابقة، من ذاكرة الإطار (النص الأصلي بالإنجليزي)" : "Lessons from past decisions (framework memory)"}</summary>
        <pre className="ltr" style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{c.past_context}</pre></details>}
      {notices.map((n) => <div key={n} className="muted" style={{ fontSize: 13 }}>• {n}</div>)}
    </section>
  );
}
