import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { SpriteSvg } from "../art/Sprite";
import { RATING, fmtNum } from "../i18n";
import { usePrefs } from "../prefs";
import { money } from "../office/BudgetPlan";

type Pos = { id: number; ticker: string; shares: number; entry_price: number; currency: string | null; opened_at: string; rating: string | null;
  closed_at: string | null; price_now: number | null; value: number | null; cost: number; ret: number | null; bench: string | null;
  dividends?: number; fees?: number;
  bench_ret: number | null; alpha: number | null };
type View = { positions: Pos[]; totals: { currency: string; cost: number; value: number; ret: number | null; bench_ret: number | null; bench_price_only?: boolean }[];
  combined_usd?: { currency: string; cost: number; value: number; ret: number | null } | null; fees_set?: boolean };

const pct = (v: number | null | undefined) => (v == null ? "—" : `${v >= 0 ? "+" : "−"}${fmtNum(Math.abs(v * 100), "en", { maximumFractionDigits: 2 })}%`);

/** The virtual portfolio: the team's calls "bought" on paper at real prices, measured against each market's index. */
export function PaperPortfolio({ active = true }: { active?: boolean }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang, ar = lang === "ar";
  const [v, setV] = useState<View | null>(null);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => { if (active) api.get<View>("/api/paper").then(setV).catch(() => {}); }, [active]);
  if (!v) return null;
  const open = v.positions.filter((p) => !p.closed_at), closed = v.positions.filter((p) => p.closed_at);
  // A refusal ({ok:false, code}) arrives as an ApiError from api.ts.
  const act = (url: string, method: "post" | "del") => (method === "post" ? api.post<View>(url) : api.del<View>(url))
    .then((r) => { setNote(null); setV(r); })
    .catch((e) => setNote(e instanceof ApiError && e.code === "no_price"
      ? (ar ? "ما فيه سعر حالي للسهم، فما قفلنا المركز (ما نسجّل سعر بيع مخترع). جرّب بعد شوي." : "No current price for this stock, so the position stays open (we never book a made-up exit price). Try again shortly.")
      : (ar ? "ما تم. جرّب مرة ثانية." : "That didn't go through. Try again.")));
  return (
    <section className="card stack" style={{ gap: 12 }} aria-labelledby="paper-h">
      <div className="row" style={{ gap: 10 }}><SpriteSvg name="Bruno" px={2} />
        <div className="stack" style={{ gap: 0 }}>
          <h2 id="paper-h" style={{ fontSize: 22, margin: 0 }}>{ar ? "المحفظة الافتراضية" : "Virtual portfolio"}</h2>
          <span className="muted" style={{ fontSize: 14 }}>{ar ? "قرارات الفريق «مشتراة» على الورق بأسعار حقيقية، ونقارنها بمؤشر كل سوق. بدون فلوس حقيقية." : "The team's calls “bought” on paper at real prices, compared with each market's index. No real money."}</span>
        </div>
      </div>
      {note && <p role="status" className="muted" style={{ margin: 0 }}>{note}</p>}
      {v.positions.length === 0 ? <p className="muted" style={{ margin: 0 }}>{ar ? "فاضية للحين. بعد أي قرار «شراء» أو خطة مبلغ اضغط «أضف للمحفظة الافتراضية»." : "Empty for now. After a Buy call or a budget plan, press “Add to the virtual portfolio”."}</p> : <>
        <div className="row" style={{ gap: 10 }}>
          {v.totals.map((t) => (
            <div key={t.currency} className="paper-total">
              <span className="muted">{ar ? "القيمة الآن" : "Value now"}</span>
              <b className="ltr">{money(t.value, t.currency, lang)}</b>
              <span className={`ltr ${(t.ret ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(t.ret)}</span>
              <span className="muted" style={{ fontSize: 12 }}>{ar ? "المؤشر بنفس الفترة" : "Index, same period"}: <span className="ltr">{pct(t.bench_ret)}</span>
                {t.bench_price_only && (ar ? " (المؤشر بدون توزيعات، وعائدك يشملها؛ الفرق في الجدول بدونها)" : " (the index has no dividends and your return includes them; the table's lead leaves them out)")}</span>
            </div>
          ))}
          {v.combined_usd && <div className="paper-total" data-combined>
            <span className="muted">{ar ? "الكل بالدولار (مع حركة العملة)" : "All in US dollars (incl. currency moves)"}</span>
            <b className="ltr">{money(v.combined_usd.value, "USD", lang)}</b>
            <span className={`ltr ${(v.combined_usd.ret ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(v.combined_usd.ret)}</span>
          </div>}
        </div>
        <div className="tablewrap">
          <table className="plan-t">
            <thead><tr><th>{ar ? "السهم" : "Stock"}</th><th>{ar ? "القرار" : "Call"}</th><th>{ar ? "الأسهم" : "Shares"}</th><th>{ar ? "سعر الدخول" : "Entry"}</th>
              <th>{ar ? "الآن" : "Now"}</th><th>{ar ? "توزيعات" : "Dividends"}</th><th>{ar ? "رسوم" : "Fees"}</th><th>{ar ? "العائد" : "Return"}</th><th>{ar ? "مقابل المؤشر" : "vs index"}</th><th /></tr></thead>
            <tbody>
              {[...open, ...closed].map((p) => (
                <tr key={p.id} style={{ opacity: p.closed_at ? 0.6 : 1 }}>
                  <td><b className="pixel ltr">{p.ticker}</b></td>
                  <td>{p.rating ? <span className={`vchip ${RATING[p.rating]?.tone ?? "none"}`}>{ar ? RATING[p.rating]?.ar : RATING[p.rating]?.en}</span> : "—"}</td>
                  <td className="ltr">{fmtNum(p.shares, lang)}</td>
                  <td className="ltr">{money(p.entry_price, p.currency ?? "USD", lang)}</td>
                  <td className="ltr">{p.price_now != null ? money(p.price_now, p.currency ?? "USD", lang) : "—"}</td>
                  <td className="ltr">{p.dividends ? money(p.dividends, p.currency ?? "USD", lang) : "—"}</td>
                  <td className="ltr">{p.fees ? money(p.fees, p.currency ?? "USD", lang) : "—"}</td>
                  <td className={`ltr ${(p.ret ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(p.ret)}</td>
                  <td className={`ltr ${(p.alpha ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(p.alpha)}</td>
                  <td>{p.closed_at ? <span className="muted">{ar ? "مقفلة" : "closed"}</span>
                    : <span className="row" style={{ gap: 4 }}>
                      <button className="ghost btn mini" onClick={() => act(`/api/paper/${p.id}/close`, "post")}>{ar ? "بيع افتراضي" : "Sell (paper)"}</button>
                      <button className="linkish" onClick={() => act(`/api/paper/${p.id}`, "del")}>{ar ? "حذف" : "Remove"}</button></span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ margin: 0, fontSize: 12 }}>{ar ? `الأسعار من مصدر البيانات المختار. العائد بعد رسوم الدخول والخروج${v.fees_set ? "" : " (رسومك مو مدخلة في الإعدادات، فهي صفر هنا)"} ومع التوزيعات المستلمة. للتعلّم وليس نصيحة مالية.`
          : `Prices from the chosen data source. Returns are after entry and exit fees${v.fees_set ? "" : " (your fees aren't entered in Settings, so they're zero here)"} and include dividends received. For learning, not financial advice.`}</p>
      </>}
    </section>
  );
}

/** "Add to the virtual portfolio" for one stock or a whole plan. */
export function AddToPaper({ items, label }: { items: { ticker: string; shares: number; session_id?: string; rating?: string }[]; label?: string }) {
  const { prefs } = usePrefs();
  const ar = prefs.lang === "ar";
  const [state, setState] = useState<"idle" | "busy" | "done" | "err" | "noprice">("idle");
  const [partial, setPartial] = useState<string[]>([]);
  const valid = items.filter((i) => i.shares > 0);
  if (!valid.length) return null;
  return (
    <button className="ghost btn" disabled={state === "busy" || state === "done"} onClick={async () => {
      setState("busy");
      try { const r = await api.post<{ failed: string[] }>("/api/paper/plan", { items: valid }); setPartial(r.failed ?? []); setState("done"); }
      catch (e) { setState((e as { code?: string }).code === "no_price" ? "noprice" : "err"); }
    }}>{state === "done" ? (ar ? "✓ انضافت للمحفظة الافتراضية" : "✓ Added to the virtual portfolio") + (partial.length ? (ar ? ` (ما انضاف: ${partial.join("، ")}، سعره غير متوفر)` : ` (not added: ${partial.join(", ")}, no price)`) : "")
      : state === "noprice" ? (ar ? "سعر السهم غير متوفر الآن، جرّب بعد شوي" : "No price available right now, try again shortly")
      : state === "err" ? (ar ? "ما قدرنا نضيفها، جرّب مرة ثانية" : "Couldn't add, try again")
      : label ?? (ar ? "📒 أضف للمحفظة الافتراضية" : "📒 Add to the virtual portfolio")}</button>
  );
}
