import { useEffect, useState } from "react";
import { api } from "../api";
import { SpriteSvg } from "../art/Sprite";
import { RATING, fmtNum } from "../i18n";
import { usePrefs } from "../prefs";

export type PlanRow = { ticker: string; rating: string; conviction: string; session_id: string; target: number; price: number | null;
  price_currency?: string; shares: number; cost: number; note: string | null };
export type Plan = { amount: number; currency: string; rows: PlanRow[]; cash_left: number;
  skipped: { ticker: string; rating: string | null; session_id: string }[]; notes: string[]; source?: string };

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
      {plan.rows.length === 0 ? (
        <p style={{ margin: 0, lineHeight: 1.8 }}>{ar
          ? "ولا سهم من اللي حللناها طلع قراره «شراء» أو «زيادة». نصيحة الفريق: خلّ المبلغ نقد الحين وانتظر فرصة أوضح. زئير!"
          : "None of the analysed stocks came out Buy or Overweight. The team's view: keep the money in cash for now and wait for a clearer chance. roar!"}</p>
      ) : (
        <div className="tablewrap">
          <table className="plan-t">
            <thead><tr>
              <th>{ar ? "السهم" : "Stock"}</th><th>{ar ? "القرار" : "Call"}</th><th>{ar ? "النصيب" : "Share"}</th>
              <th>{ar ? "سعر السهم" : "Price"}</th><th>{ar ? "عدد الأسهم" : "Shares"}</th><th>{ar ? "التكلفة" : "Cost"}</th>
            </tr></thead>
            <tbody>
              {plan.rows.map((r) => (
                <tr key={r.ticker}>
                  <td>{onOpen ? <button className="linkish pixel ltr" onClick={() => onOpen(r.session_id)}>{r.ticker}</button> : <b className="pixel ltr">{r.ticker}</b>}</td>
                  <td><span className={`vchip ${RATING[r.rating]?.tone ?? "none"}`}>{ar ? RATING[r.rating]?.ar : RATING[r.rating]?.en}</span></td>
                  <td className="ltr">{money(r.target, cur, lang)}</td>
                  <td className="ltr">{r.price != null ? money(r.price, r.price_currency ?? cur, lang) : (ar ? "غير متوفر" : "unavailable")}</td>
                  <td className="ltr"><b>{fmtNum(r.shares, lang)}</b></td>
                  <td className="ltr">{r.note === "too_small" ? <span className="muted">{ar ? "المبلغ أقل من سهم" : "less than 1 share"}</span>
                    : r.note === "no_fx" ? <span className="muted">{ar ? "سعر الصرف غير متوفر" : "no FX rate"}</span>
                    : money(r.cost, cur, lang)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span>{ar ? "يبقى نقد" : "Left in cash"}: <b className="ltr">{money(plan.cash_left, cur, lang)}</b></span>
        {plan.skipped.length > 0 && <span className="muted" style={{ fontSize: 13 }}>{ar ? "ما دخلت الخطة: " : "Not in the plan: "}
          <span className="ltr">{plan.skipped.map((s) => `${s.ticker}${s.rating ? ` (${ar ? RATING[s.rating]?.ar ?? s.rating : RATING[s.rating]?.en ?? s.rating})` : ""}`).join("، ")}</span></span>}
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 12, lineHeight: 1.7 }}>{ar
        ? "الأوزان من قرارات الفريق (شراء ضعف الزيادة التدريجية، وقوة القناعة تعدّلها)، وبحد أقصى 40٪ للسهم الواحد، بأسهم كاملة وأسعار Yahoo الحالية. مثال للتفكير وليس نصيحة مالية، ولا تنسَ رسوم الوسيط."
        : "Weights come from the team's calls (Buy counts double Overweight, adjusted by conviction), capped at 40% per stock, in whole shares at current Yahoo prices. An illustration to think with, not financial advice; remember broker fees."}</p>
    </section>
  );
}
