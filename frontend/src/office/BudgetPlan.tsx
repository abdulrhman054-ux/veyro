import { useEffect, useState } from "react";
import { api } from "../api";
import { SpriteSvg } from "../art/Sprite";
import { RATING, fmtNum, sharesText } from "../i18n";
import { disclaimer, methodName, reasonText, type ShariaResult } from "../extras/Sharia";
import { usePrefs } from "../prefs";
import { AddToPaper } from "../extras/Paper";

type Names = { ar: string; en: string };
type Reasons = Partial<Record<"ar" | "en", string | null>>;
export type PlanRow = { ticker: string; rating: string; conviction: string; session_id: string; target: number; price: number | null;
  price_currency?: string; shares: number; cost: number; note: string | null; name?: Names; reason?: Reasons;
  fee?: number; sector?: string | null; vol?: number | null; risk_adj?: number };
export type Plan = { amount: number; currency: string; rows: PlanRow[]; cash_left: number;
  skipped: { ticker: string; rating: string | null; session_id: string; status?: string; name?: Names; reason?: Reasons; sharia?: ShariaResult }[];
  notes: string[]; source?: string; sharia?: { method: string; excluded: string[] } | null;
  correlated?: { a: string; b: string; corr: number }[]; fees_total?: number; caps?: { name: number; sector: number } };

export function money(v: number, cur: string, lang: "ar" | "en") {
  const n = fmtNum(v, lang, { maximumFractionDigits: 2, minimumFractionDigits: v % 1 ? 2 : 0 });
  return cur === "SAR" ? (lang === "ar" ? `${n} ريال` : `SAR ${n}`) : cur === "USD" ? `$${n}` : `${n} ${cur}`;
}

/** Leo's plan for the owner's budget: whole shares of the stocks the team rated Buy/Overweight, real prices. */
export function BudgetPlan({ url, budget, onOpen, plan: given }: { url?: string; budget?: { amount: number; currency: string }; onOpen?: (sid: string) => void; plan?: Plan | null }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const ar = lang === "ar";
  const [plan, setPlan] = useState<Plan | null>(given ?? null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (given !== undefined) { setPlan(given); return; }
    if (!url || !budget) return;
    let alive = true;
    api.get<Plan>(`${url}?budget=${budget.amount}&currency=${budget.currency}`)
      .then((p) => { if (alive) setPlan(p); }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [url, budget?.amount, budget?.currency, given]);   // eslint-disable-line react-hooks/exhaustive-deps

  if (failed) return <div className="card cream" style={{ padding: 14 }}>{ar ? "ما قدرنا نحسب خطة المبلغ الآن." : "Couldn't work out the budget plan right now."}</div>;
  if (!plan) return <div className="card cream" style={{ padding: 14 }} aria-busy="true">…</div>;
  const cur = plan.currency;
  return (
    <section className="card cream plan stack" style={{ gap: 10 }} aria-label={ar ? "خطة ليو للمبلغ" : "Leo's budget plan"}>
      <div className="row" style={{ gap: 10 }}>
        <SpriteSvg name="Leo" px={1} />
        <b style={{ fontSize: 18 }}>{ar ? `خطة ليو لمبلغ ${money(plan.amount, cur, lang)}` : `Leo's plan for ${money(plan.amount, cur, lang)}`}</b>
      </div>
      {plan.rows.length > 0 && (
        <div className="reco buy" role="note">
          <b className="reco-h">✅ {ar ? "الفريق ينصح بشراء:" : "The team recommends buying:"}</b>
          <ul>
            {plan.rows.filter((r) => r.shares > 0).map((r) => (
              <li key={r.ticker}>
                <b>{r.name?.[lang] ?? r.ticker}</b> <span className="pixel ltr muted">({r.ticker})</span>
                {" — "}<span>{ar ? `${sharesText(r.shares, lang)} بحوالي ${money(r.cost, cur, lang)}` : `${sharesText(r.shares, lang)}, about ${money(r.cost, cur, lang)}`}</span>
                {" · "}<span className={`vchip ${RATING[r.rating]?.tone ?? "none"}`}>{ar ? RATING[r.rating]?.ar : RATING[r.rating]?.en}</span>
                {r.reason?.[lang] && <div className="muted" style={{ fontSize: 13 }}>{ar ? "ليش: " : "Why: "}{r.reason[lang]}</div>}
              </li>
            ))}
            {plan.rows.filter((r) => r.shares === 0).map((r) => (
              <li key={r.ticker}><b>{r.name?.[lang] ?? r.ticker}</b> <span className="pixel ltr muted">({r.ticker})</span>{" — "}
                <span className="muted">{ar ? "قراره إيجابي بس نصيبه من المبلغ أقل من سعر سهم واحد" : "rated positively, but its share of the budget is less than one share"}</span></li>
            ))}
          </ul>
        </div>
      )}
      {plan.skipped.length > 0 && (
        <div className="reco skip" role="note">
          <b className="reco-h">⏸ {ar ? "ما ينصح بشرائها الآن:" : "Not recommended to buy right now:"}</b>
          <ul>
            {plan.skipped.map((s) => (
              <li key={s.session_id}><b>{s.name?.[lang] ?? s.ticker}</b> <span className="pixel ltr muted">({s.ticker})</span>{" — "}
                {s.rating ? <span className={`vchip ${RATING[s.rating]?.tone ?? "none"}`}>{ar ? RATING[s.rating]?.ar ?? s.rating : RATING[s.rating]?.en ?? s.rating}</span>
                  : <span className="muted">{ar ? "ما اكتمل تحليله" : "analysis didn't finish"}</span>}
                {s.reason?.[lang] && <div className="muted" style={{ fontSize: 13 }}>{ar ? "ليش: " : "Why: "}{s.reason[lang]}</div>}
                {s.sharia && (s.rating === "Buy" || s.rating === "Overweight") && <div style={{ fontSize: 13 }} data-sharia-excluded={s.ticker}>
                  ☪ {s.sharia.status === "unknown"
                    ? (ar ? "استبعدناه من الخطة لأن الفحص الشرعي «غير معروف» (ما نعتبره متوافق بدون بيانات): " : "Left out of the plan: the Sharia screen is Unknown (never treated as compliant without data): ")
                    : (ar ? "استبعدناه من الخطة لأنه غير متوافق شرعياً: " : "Left out of the plan: not Sharia-compliant: ")}
                  {s.sharia.reasons.map((x) => reasonText(x, lang, s.sharia!.method)).join(ar ? "؛ " : "; ")}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {plan.sharia && <p className="muted" style={{ margin: 0, fontSize: 13 }}>☪ {ar
        ? `الفحص الشرعي مفعّل (${methodName(plan.sharia.method, lang)}): الأسهم غير المتوافقة وغير المعروفة ما تاخذ من المبلغ. ${disclaimer(lang)}`
        : `Sharia screening is on (${methodName(plan.sharia.method, lang)}): non-compliant and unknown stocks get no money. ${disclaimer(lang)}`}</p>}
      {plan.rows.length === 0 ? (
        <p style={{ margin: 0, lineHeight: 1.8 }}>{ar
          ? "ولا سهم من اللي حللناها طلع قراره «شراء» أو «زيادة». نصيحة الفريق: خلّ المبلغ نقد الحين وانتظر فرصة أوضح. زئير!"
          : "None of the analysed stocks came out Buy or Overweight. The team's view: keep the money in cash for now and wait for a clearer chance. roar!"}</p>
      ) : (
        <div className="tablewrap">
          <table className="plan-t">
            <thead><tr>
              <th>{ar ? "السهم" : "Stock"}</th><th>{ar ? "القرار" : "Call"}</th><th>{ar ? "المبلغ المستهدف" : "Target"}</th>
              <th>{ar ? "سعر السهم" : "Price"}</th><th>{ar ? "عدد الأسهم" : "Shares"}</th><th>{ar ? "الرسوم" : "Fees"}</th><th>{ar ? "التكلفة" : "Cost"}</th>
            </tr></thead>
            <tbody>
              {plan.rows.map((r) => (
                <tr key={r.ticker}>
                  <td>{onOpen ? <button className="linkish pixel ltr" onClick={() => onOpen(r.session_id)}>{r.ticker}</button> : <b className="pixel ltr">{r.ticker}</b>}</td>
                  <td><span className={`vchip ${RATING[r.rating]?.tone ?? "none"}`}>{ar ? RATING[r.rating]?.ar : RATING[r.rating]?.en}</span></td>
                  <td className="ltr">{money(r.target, cur, lang)}</td>
                  <td className="ltr">{r.price != null ? money(r.price, r.price_currency ?? cur, lang) : (ar ? "غير متوفر" : "unavailable")}</td>
                  <td className="ltr"><b>{fmtNum(r.shares, lang)}</b></td>
                  <td className="ltr">{r.fee ? money(r.fee, cur, lang) : "—"}</td>
                  <td className="ltr">{r.note === "too_small" ? <span className="muted">{ar ? "المبلغ أقل من سهم" : "less than 1 share"}</span>
                    : r.note === "no_fx" ? <span className="muted">{ar ? "سعر الصرف غير متوفر" : "no FX rate"}</span>
                    : money(r.cost, cur, lang)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {plan.rows.some((r) => r.shares > 0) && (
        <AddToPaper items={plan.rows.map((r) => ({ ticker: r.ticker, shares: r.shares, session_id: r.session_id, rating: r.rating }))}
          label={ar ? "📒 نفّذ الخطة على المحفظة الافتراضية" : "📒 Run this plan on the virtual portfolio"} />
      )}
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span>{ar ? "يبقى نقد" : "Left in cash"}: <b className="ltr">{money(plan.cash_left, cur, lang)}</b></span>
        {!!plan.fees_total && <span className="muted">{ar ? "رسوم الوسيط المقدّرة" : "Estimated broker fees"}: <b className="ltr">{money(plan.fees_total, cur, lang)}</b></span>}
      </div>
      <PlanWarnings plan={plan} lang={lang} />
      <p className="muted" style={{ margin: 0, fontSize: 12, lineHeight: 1.7 }}>{ar
        ? "الأوزان من قرارات الفريق (شراء ضعف الزيادة التدريجية، وقوة القناعة تعدّلها) ومن التذبذب (السهم الأهدأ ياخذ أكثر)، وبحد أقصى 40٪ للسهم الواحد و50٪ للقطاع الواحد، والباقي يبقى نقد. بأسهم كاملة وأسعار Yahoo الحالية، والرسوم من إعداداتك. مثال للتفكير وليس نصيحة مالية."
        : "Weights come from the team's calls (Buy counts double Overweight, adjusted by conviction) and from volatility (a calmer stock gets more), with at most 40% per stock and 50% per sector; the rest stays in cash. Whole shares at current Yahoo prices, fees from your Settings. An illustration to think with, not financial advice."}</p>
    </section>
  );
}

/** Plain warnings under the plan: concentration, look-alike stocks, fees not entered. */
function PlanWarnings({ plan, lang }: { plan: Plan; lang: "ar" | "en" }) {
  const ar = lang === "ar";
  const items: string[] = [];
  if (plan.notes.includes("few_picks") && plan.rows.some((r) => r.shares > 0))
    items.push(ar ? "سهم أو سهمين مو محفظة متنوعة: حطينا 40٪ كحد أقصى لكل سهم وخلينا الباقي نقد. فكّر بصندوق مؤشرات للجزء الباقي."
      : "One or two stocks are not a diversified portfolio: each gets at most 40% and the rest stays in cash. Consider an index fund for the rest.");
  if (plan.notes.includes("one_share_over_cap"))
    items.push(ar ? "مبلغك صغير، فسهم واحد من بعض الشركات يتجاوز 40٪ من المبلغ. انتبه لتركّز المخاطرة."
      : "Your amount is small, so one share of some companies is more than 40% of it. Mind the concentration.");
  for (const c of plan.correlated ?? [])
    items.push(ar ? `${c.a} و${c.b} يتحركون مع بعض تقريباً (ارتباط ${c.corr}): التنويع بينهم أقل مما يبدو.`
      : `${c.a} and ${c.b} tend to move together (correlation ${c.corr}): less diversified than it looks.`);
  if (plan.notes.includes("fees_not_set"))
    items.push(ar ? "رسوم وسيطك مو مدخلة (الإعدادات ← رسوم الوسيط)، فالخطة ما تحسب العمولة. على المبالغ الصغيرة ممكن تفرق كثير."
      : "Your broker's fees aren't entered (Settings → Broker fees), so the plan doesn't include commission. On small amounts it can matter a lot.");
  if (!items.length) return null;
  return <ul className="plan-warn" role="note" style={{ margin: 0, paddingInlineStart: 18, fontSize: 13, lineHeight: 1.7 }}>
    {items.map((x, i) => <li key={i}>⚠ {x}</li>)}</ul>;
}
