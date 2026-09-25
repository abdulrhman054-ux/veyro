import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { SpriteSvg } from "../art/Sprite";
import { errorBonk } from "../audio";
import { fmtDate, fmtNum, fmtPct, fmtUsd } from "../i18n";
import { usePrefs } from "../prefs";
import { EXD } from "./execI18n";
import { ModeBadge, execErrorText, useExec, type ExecStatus } from "./ExecContext";
import { PageHeader } from "../components/PageHeader";
import { detailText, eventLabel, modeLabel } from "./auditText";

type Portfolio = {
  mode: string; available: boolean; broker?: string; error?: string;
  account?: { cash: number | null; equity: number | null; last_equity: number | null; status: string };
  positions?: { symbol: string; qty: number; avg_entry_price: number; current_price: number | null; market_value: number | null; unrealized_pl: number | null; unrealized_plpc: number | null }[];
  clock?: { open: boolean; next_open: string | null; source: string }; day_pl?: number; orders_today?: number;
  limits?: { max_orders_per_day: number; daily_loss_limit_usd: number };
};
type AuditRow = { id: number; ts: string; mode: string; broker: string | null; event: string; symbol: string | null; side: string | null;
  order_type: string | null; qty: number | null; notional: number | null; limit_price: number | null; est_cost: number | null; message: string | null };

export function OrdersScreen({ onOpenSettings, active = true }: { onOpenSettings?: () => void; active?: boolean }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const d = EXD[lang];
  const { status, setStatus, orders, syncOrders } = useExec();
  const [pf, setPf] = useState<Portfolio | null>(null);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [phrase, setPhrase] = useState("");

  const load = useCallback(async () => {
    api.get<Portfolio>("/api/exec/portfolio").then(setPf).catch(() => setPf(null));
    api.get<{ rows: AuditRow[] }>("/api/exec/audit").then((r) => setAudit(r.rows)).catch(() => {});
  }, []);
  useEffect(() => { if (!active) return; void load(); const h = setInterval(load, 5000); return () => clearInterval(h); }, [load, active]);

  const money = (v: number | null | undefined) => fmtUsd(v ?? null, lang) ?? d.unavailable;

  async function kill() {
    errorBonk();
    try { const r = await api.post<ExecStatus & { cancelled: number }>("/api/exec/kill"); setStatus(r); setMsg(`${d.killDone} (${r.cancelled})`); void load(); }
    catch (e) { setMsg(execErrorText(e, lang).text); }
  }
  async function cancelOrder(id: string) {
    try { await api.post(`/api/exec/orders/${id}/cancel`); void syncOrders(); void load(); } catch (e) { setMsg(execErrorText(e, lang).text); }
  }
  async function liquidate() {
    try { await api.post("/api/exec/liquidate", { phrase }); setPhrase(""); void load(); void syncOrders(); } catch (e) { setMsg(execErrorText(e, lang).text); }
  }

  const off = !status || status.mode === "off";
  const open = orders.filter((o) => ["new", "accepted", "pending_new", "partially_filled", "held"].includes(o.status));
  const recent = orders.filter((o) => !open.includes(o)).slice(0, 20);
  const liqPhrase = status?.liquidate_phrases[lang];

  return (
    <div className="stack" style={{ gap: 18 }}>
      <PageHeader host="Tank" title={d.orders} side={<ModeBadge big />}
        sub={lang === "ar" ? "كل أمر هنا يحتاج تأكيدك. تانك يحرس حدود المخاطرة، وبيب يبلغك إذا تنفّذ شي." : "Every order here needs your confirmation. Tank guards the risk limits and Pip tells you when something fills."}
        say={off ? (lang === "ar" ? "التنفيذ مقفل، كل شي هادي." : "Execution is off. All quiet.") : (lang === "ar" ? "أفحص حدود المخاطرة…" : "Checking the risk limits…")}
        extra={off ? [] : [{ name: "Pip", say: lang === "ar" ? "أراقب التنفيذات!" : "Watching for fills!" }]} />
      {off && (
        <section className="card cream row" style={{ gap: 16, flexWrap: "nowrap" }}>
          <div className="stack" style={{ gap: 8 }}>
            <b style={{ fontSize: 18 }}>{lang === "ar" ? "التنفيذ مغلق، وهذا الوضع الافتراضي." : "Execution is off, which is the default."}</b>
            <span>{d.offNote} {lang === "ar" ? "إذا حاب تجرّب، فعّل «تجريبي» من الإعدادات المتقدمة. خطوة خطوة." : "If you'd like to try, turn on Paper in Advanced settings. One step at a time."}</span>
            {onOpenSettings && <button className="primary btn" style={{ alignSelf: "flex-start", height: 42, fontSize: 16 }} onClick={onOpenSettings}>{lang === "ar" ? "افتح الإعدادات" : "Open settings"}</button>}
          </div>
        </section>
      )}
      <section className="card row" style={{ justifyContent: "space-between", border: status?.mode === "live" ? "4px solid #C62828" : undefined, display: off ? "none" : undefined }}>
        <div className="row">
          {pf?.clock && <span className={`chip mkt ${pf.clock.open ? "open" : "closed"}`}><i />{pf.clock.open ? d.marketIsOpen : d.nextOpen + ": " + (fmtDate(pf.clock.next_open, lang) ?? "—")}
            {pf.clock.source.includes("dev") && <> · {d.devClock}</>}</span>}
        </div>
        <button className="btn" onClick={kill} disabled={off}
          style={{ height: 54, padding: "0 24px", borderRadius: 27, border: 0, background: "#C62828", color: "#FFFFFF", fontSize: 17, fontWeight: 800, cursor: off ? "default" : "pointer", boxShadow: "0 5px 0 #7F1D1D", opacity: off ? 0.5 : 1 }}>
          ⏻ {d.killSwitch}
        </button>
      </section>
      {msg && <div className="warnstrip" role="status">{msg}</div>}

      {!off && (
        <div className="report" style={{ alignItems: "flex-start" }}>
          <div className="left">
            <section className="card stack" aria-labelledby="pf-h">
              <h2 id="pf-h" style={{ fontSize: 21 }}>{d.portfolio}</h2>
              {!pf?.available ? <p className="muted">{d.unavailable}</p> : (
                <>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                    <div><div className="label">{d.cash}</div><b className="pixel ltr" style={{ fontSize: 20 }}>{money(pf.account?.cash)}</b></div>
                    <div><div className="label">{d.equity}</div><b className="pixel ltr" style={{ fontSize: 20 }}>{money(pf.account?.equity)}</b></div>
                    <div><div className="label">{d.dayPL}</div><b className={`pixel ltr ${(pf.day_pl ?? 0) >= 0 ? "pos" : "neg"}`} style={{ fontSize: 20 }}>{money(pf.day_pl)}</b></div>
                    <div><div className="label">{d.ordersLeft}</div><b className="pixel ltr" style={{ fontSize: 20 }}>{Math.max(0, (pf.limits?.max_orders_per_day ?? 0) - (pf.orders_today ?? 0))} {d.of} {pf.limits?.max_orders_per_day}</b></div>
                  </div>
                  <div className="label">{d.positions}</div>
                  {pf.positions?.length ? (
                    <table className="table"><thead><tr><th>{d.symbol}</th><th>{d.qty}</th><th>{d.avgPrice}</th><th>{d.marketValue}</th><th>{d.unrealized}</th></tr></thead>
                      <tbody>{pf.positions.map((p) => (
                        <tr key={p.symbol}><td className="pixel ltr">{p.symbol}</td><td className="ltr">{fmtNum(p.qty, lang, { maximumFractionDigits: 6 })}</td>
                          <td className="ltr">{money(p.avg_entry_price)}</td><td className="ltr">{money(p.market_value)}</td>
                          <td className={`ltr ${(p.unrealized_pl ?? 0) >= 0 ? "pos" : "neg"}`}>{p.unrealized_pl != null ? `${money(p.unrealized_pl)} (${fmtPct(p.unrealized_plpc, lang)})` : d.unavailable}</td></tr>
                      ))}</tbody></table>
                  ) : <p className="muted" style={{ margin: 0 }}>{d.noPositions}</p>}
                  <p className="muted" style={{ margin: 0, fontSize: 13 }}>{d.source}: {pf.broker === "mock" ? `${d.mock} (Yahoo)` : "Alpaca"}</p>
                </>
              )}
            </section>
            <section className="card stack" style={{ border: "3px dashed #C62828" }}>
              <h2 style={{ fontSize: 19 }}>{d.liquidate}</h2>
              <label className="stack" style={{ gap: 4 }}><span>{d.liquidateNote} <b>«{liqPhrase}»</b></span>
                <input className="field" value={phrase} onChange={(e) => setPhrase(e.target.value)} placeholder={d.confirmTyped} /></label>
              <button className="ghost btn" disabled={phrase.trim() !== liqPhrase} onClick={liquidate} style={{ borderColor: "#C62828", color: "#C62828" }}>{d.liquidate}</button>
            </section>
          </div>
          <div className="right">
            <section className="card stack">
              <h2 style={{ fontSize: 21 }}>{d.openOrders}</h2>
              {open.length === 0 ? <p className="muted" style={{ margin: 0 }}>{d.noOrders}</p> : (
                <table className="table"><thead><tr><th>{d.symbol}</th><th>{d.side}</th><th>{d.type}</th><th>{d.qty}</th><th>{d.limitPrice}</th><th>{d.status}</th><th /></tr></thead>
                  <tbody>{open.map((o) => (
                    <tr key={o.id}><td className="pixel ltr">{o.symbol}</td><td>{o.side === "buy" ? d.buy : d.sell}</td><td>{o.type === "limit" ? d.limit : d.market}</td>
                      <td className="ltr">{o.qty != null ? fmtNum(o.qty, lang, { maximumFractionDigits: 6 }) : money(o.notional)}</td><td className="ltr">{o.limit_price != null ? money(o.limit_price) : "—"}</td>
                      <td className="ltr">{o.status}{o.mock ? " · MOCK" : ""}</td><td><button className="ghost btn" onClick={() => cancelOrder(o.id)}>{d.cancel}</button></td></tr>
                  ))}</tbody></table>
              )}
            </section>
            <section className="card stack">
              <h2 style={{ fontSize: 21 }}>{d.recentOrders}</h2>
              {recent.length === 0 ? <p className="muted" style={{ margin: 0 }}>{d.noOrders}</p> : (
                <table className="table"><thead><tr><th>{d.symbol}</th><th>{d.side}</th><th>{d.type}</th><th>{d.qty}</th><th>{d.avgPrice}</th><th>{d.status}</th><th>{d.colTime}</th></tr></thead>
                  <tbody>{recent.map((o) => (
                    <tr key={o.id}><td className="pixel ltr">{o.symbol}</td><td>{o.side === "buy" ? d.buy : d.sell}</td><td>{o.type === "limit" ? d.limit : d.market}</td>
                      <td className="ltr">{fmtNum(o.filled_qty || o.qty, lang, { maximumFractionDigits: 6 }) ?? money(o.notional)}</td>
                      <td className="ltr">{o.filled_avg_price != null ? money(o.filled_avg_price) : "—"}</td><td className="ltr">{o.status}{o.mock ? " · MOCK" : ""}</td>
                      <td>{fmtDate(o.filled_at ?? o.submitted_at, lang)}</td></tr>
                  ))}</tbody></table>
              )}
            </section>
          </div>
        </div>
      )}

      <section className="card stack">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div className="row"><SpriteSvg name="Benny" px={2} /><h2 style={{ fontSize: 21 }}>{d.auditLog}</h2></div>
          <a className="ghost btn" href="/api/exec/audit.csv" download style={{ display: "inline-flex", alignItems: "center", textDecoration: "none", color: "inherit" }}>{d.exportCsv}</a>
        </div>
        <div style={{ overflowX: "auto", maxHeight: 420, overflowY: "auto" }}>
          <table className="table"><thead><tr><th>{d.colTime}</th><th>{d.colMode}</th><th>{d.colEvent}</th><th>{d.symbol}</th><th>{d.side}</th><th>{d.estCost}</th><th>{d.colDetails}</th></tr></thead>
            <tbody>{audit.map((a) => (
              <tr key={a.id}><td>{fmtDate(a.ts, lang)}</td><td>{modeLabel(a.mode, lang)}{a.broker === "mock" ? ` · ${d.mock}` : ""}</td><td><b>{eventLabel(a.event, lang)}</b></td>
                <td className="pixel ltr">{a.symbol ?? "—"}</td><td>{a.side ? (a.side === "buy" ? d.buy : d.sell) : "—"}</td>
                <td className="ltr">{a.est_cost != null ? money(a.est_cost) : "—"}</td><td style={{ fontSize: 13, maxWidth: 360 }}>{detailText(a.message, lang)}</td></tr>
            ))}</tbody></table>
        </div>
      </section>
    </div>
  );
}
