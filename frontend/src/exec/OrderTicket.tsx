import { useEffect, useState } from "react";
import { api, type SessionFull } from "../api";
import { extractFigures } from "../screens/FrameworkPanels";
import { SpriteSvg } from "../art/Sprite";
import { click, pop, verdictJingle } from "../audio";
import { RATING, fmtDate, fmtNum, fmtUsd } from "../i18n";
import { usePrefs } from "../prefs";
import { EXD } from "./execI18n";
import { ModeBadge, execErrorText, useExec, type BrokerOrder, type ExecLimits } from "./ExecContext";

type Check = { id: string; ok: boolean; value: number | string | null; limit: number | null };
type Ticket = {
  id: string; ok: boolean; token: string | null; symbol: string; side: "buy" | "sell"; order_type: "market" | "limit";
  qty: number | null; notional: number | null; limit_price: number | null; est_cost: number; price: number; price_as_of: string;
  price_source: string; market_open: boolean; next_open: string | null; checks: Check[]; orders_left_today: number; limits: ExecLimits;
  broker: string; mode: string; expires_at: string;
};

export function sideForRating(r: string): "buy" | "sell" | null {
  const tone = RATING[r]?.tone;
  return tone === "buy" ? "buy" : tone === "sell" ? "sell" : null;
}

/** Button shown under Leo's verdict when execution is on. */
export function ProposeButton({ sessionId, ticker, rating, demo }: { sessionId: string; ticker: string; rating: string; demo: boolean }) {
  const { status } = useExec();
  const { prefs } = usePrefs();
  const d = EXD[prefs.lang];
  const [open, setOpen] = useState(false);
  if (!status || status.mode === "off" || demo) return null;
  const side = sideForRating(rating);
  if (!side) return <span style={{ fontSize: 13, fontWeight: 700 }}>{d.noTicketHold}</span>;
  return (
    <>
      <button className="primary btn" style={{ height: 42, fontSize: 16 }} onClick={() => { click(); setOpen(true); }}>{d.leoProposes}</button>
      {open && <OrderTicket sessionId={sessionId} ticker={ticker} side={side} onClose={() => setOpen(false)} />}
    </>
  );
}

export function OrderTicket({ sessionId, ticker, side, onClose }: { sessionId: string | null; ticker: string; side: "buy" | "sell"; onClose: () => void }) {
  const { prefs, motionOff } = usePrefs();
  const lang = prefs.lang;
  const d = EXD[lang];
  const { status, syncOrders } = useExec();
  const lim = status && status.mode !== "off" ? status.limits[status.mode] : null;
  const [type, setType] = useState<"market" | "limit">("market");
  const [amount, setAmount] = useState(() => String(Math.min(100, lim?.max_order_usd ?? 100)));
  const [qty, setQty] = useState("");
  const [limitPrice, setLimitPrice] = useState("");
  const [held, setHeld] = useState<number | null>(null);
  const [stage, setStage] = useState<"edit" | "checking" | "review" | "sending" | "done">("edit");
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [shown, setShown] = useState(0);
  const [err, setErr] = useState<{ c: string; text: string } | null>(null);
  const [closedOffer, setClosedOffer] = useState<string | null>(null);
  const [order, setOrder] = useState<BrokerOrder | null>(null);

  const [entryHint, setEntryHint] = useState<number | null>(null);
  useEffect(() => {
    const fromTrader = sessionId
      ? api.get<SessionFull>(`/api/sessions/${sessionId}`).then((s) => extractFigures(s.turns).entryPrice ?? null).catch(() => null)
      : Promise.resolve(null);
    fromTrader.then((entry) => {
      if (entry) { setEntryHint(entry); setLimitPrice(entry.toFixed(2)); return; }
      api.get<{ closes?: number[] }>(`/api/market/history/${ticker}`).then((h) => { const c = h.closes?.at(-1); if (c) setLimitPrice(c.toFixed(2)); }).catch(() => {});
    });
    if (side === "sell") api.get<{ positions?: { symbol: string; qty: number }[] }>("/api/exec/portfolio")
      .then((p) => { const q = p.positions?.find((x) => x.symbol === ticker)?.qty ?? 0; setHeld(q); setQty(q ? String(q) : ""); }).catch(() => setHeld(null));
  }, [ticker, side]);

  // Tank ticks the checks one by one (numbers are always visible, animation only reveals them).
  useEffect(() => {
    if (stage !== "checking" || !ticket) return;
    if (shown >= ticket.checks.length) { setStage("review"); return; }
    const h = setTimeout(() => { setShown((n) => n + 1); pop(); }, motionOff ? 0 : 380);
    return () => clearTimeout(h);
  }, [stage, shown, ticket, motionOff]);

  async function prepare() {
    setErr(null); setClosedOffer(null); click();
    try {
      const body = { symbol: ticker, side, order_type: type, session_id: sessionId,
        amount_usd: side === "buy" ? Number(amount) : null, qty: side === "sell" ? Number(qty) : null,
        limit_price: type === "limit" ? Number(limitPrice) : null };
      const t = await api.post<Ticket>("/api/exec/tickets", body);
      setTicket(t); setShown(0); setStage("checking");
    } catch (e) {
      const m = execErrorText(e, lang);
      if (m.text && (e as { code?: string }).code === "market_closed") setClosedOffer(m.text);
      else setErr(m);
    }
  }

  async function confirm() {
    if (!ticket?.token) return;
    setStage("sending"); click();
    try {
      const r = await api.post<{ order: BrokerOrder }>(`/api/exec/tickets/${ticket.id}/confirm`, { token: ticket.token, confirm: true });
      setOrder(r.order); setStage("done"); verdictJingle("buy"); void syncOrders();
    } catch (e) { setErr(execErrorText(e, lang)); setStage("review"); }
  }

  const checkLabel = (id: string) => (d as Record<string, string>)[`check_${id}`] ?? id;
  const money = (v: number | null | undefined) => fmtUsd(v ?? null, lang) ?? "—";

  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-label={d.ticketTitle} dir={lang === "ar" ? "rtl" : "ltr"}>
      <div className="modal" style={{ maxWidth: 720 }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div className="row"><SpriteSvg name="Leo" px={2} frame="wave" /><h2 style={{ fontSize: 24 }}>{d.ticketTitle}</h2></div>
          <ModeBadge big />
        </div>

        <div className="card cream" style={{ marginTop: 14, display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 12 }}>
          <div><div className="label">{d.symbol}</div><b className="pixel ltr" style={{ fontSize: 24 }}>{ticker}</b></div>
          <div><div className="label">{d.side}</div><span className={`vchip ${side === "buy" ? "buy" : "sell"}`} style={{ fontSize: 18 }}>{side === "buy" ? d.buy : d.sell}</span></div>
          <div><div className="label">{d.type}</div>
            <div className="segbtns" role="group" aria-label={d.type}>
              {(["market", "limit"] as const).map((k) => <button key={k} aria-pressed={type === k} disabled={stage !== "edit"} onClick={() => setType(k)}>{d[k]}</button>)}
            </div>
          </div>
        </div>

        {stage === "edit" && (
          <div className="stack" style={{ marginTop: 14 }}>
            {side === "buy" ? (
              <label className="stack" style={{ gap: 4 }}><span className="label">{d.amount}</span>
                <input className="field ltr pixel" type="number" min={1} step="1" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
            ) : (
              <label className="stack" style={{ gap: 4 }}><span className="label">{d.shares} {held != null && <>· {lang === "ar" ? "تملك" : "you own"} <span className="ltr">{fmtNum(held, lang, { maximumFractionDigits: 6 })}</span></>}</span>
                <input className="field ltr pixel" type="number" min={0} step="any" value={qty} onChange={(e) => setQty(e.target.value)} /></label>
            )}
            {type === "limit" && (
              <label className="stack" style={{ gap: 4 }}><span className="label">{d.limitPrice}</span>
                <input className="field ltr pixel" type="number" min={0.01} step="0.01" value={limitPrice} onChange={(e) => setLimitPrice(e.target.value)} />
                {entryHint != null && <span className="muted" style={{ fontSize: 13 }}>{lang === "ar" ? "مقترح من المتداول في الجلسة:" : "Suggested by the session's Trader:"} <span className="ltr">{money(entryHint)}</span></span>}</label>
            )}
            {lim && <p className="muted" style={{ margin: 0, fontSize: 14 }}>{d.limits}: {d.maxOrder} <span className="ltr">{money(lim.max_order_usd)}</span> · {d.maxOrdersDay} <span className="ltr">{lim.max_orders_per_day}</span></p>}
            {closedOffer && (
              <div className="warnstrip" role="alert">
                <div className="row"><SpriteSvg name="Leo" px={2} /><span>{closedOffer}</span></div>
                <div className="row" style={{ marginTop: 8 }}>
                  <button className="primary btn" style={{ height: 38, fontSize: 15 }} onClick={() => { setType("limit"); setClosedOffer(null); }}>{d.useLimit}</button>
                  <button className="ghost btn" onClick={onClose}>{d.cancel}</button>
                </div>
              </div>
            )}
            <div className="row" style={{ justifyContent: "flex-end" }}>
              <button className="ghost btn" onClick={onClose}>{d.cancel}</button>
              <button className="primary btn" onClick={prepare}>{d.checkWithTank}</button>
            </div>
          </div>
        )}

        {ticket && stage !== "edit" && (
          <div className="stack" style={{ marginTop: 14 }}>
            <div className="card" style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 12 }}>
              <div><div className="label">{d.currentPrice}</div><b className="pixel ltr" style={{ fontSize: 22 }}>{money(ticket.price)}</b>
                <div className="muted" style={{ fontSize: 12 }}>{d.source}: {ticket.price_source}</div></div>
              <div><div className="label">{d.estCost}</div><b className="pixel ltr" style={{ fontSize: 22 }}>{money(ticket.est_cost)}</b>
                <div className="muted ltr" style={{ fontSize: 12 }}>{ticket.qty != null ? `${fmtNum(ticket.qty, lang, { maximumFractionDigits: 6 })} × ${money(ticket.order_type === "limit" ? ticket.limit_price : ticket.price)}` : `${d.amount} ${money(ticket.notional)}`}</div></div>
              <div><div className="label">{d.ordersLeft}</div><b className="pixel ltr" style={{ fontSize: 20 }}>{ticket.orders_left_today} {d.of} {ticket.limits.max_orders_per_day}</b></div>
              <div><div className="label">{ticket.market_open ? d.marketIsOpen : d.nextOpen}</div>
                <b>{ticket.market_open ? "✓" : fmtDate(ticket.next_open, lang) ?? "—"}</b></div>
            </div>

            <div className="card cream" style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
              <div style={{ flexShrink: 0 }}><SpriteSvg name="Tank" px={3} frame={stage === "checking" ? "typeA" : "down"} /></div>
              <ul style={{ margin: 0, padding: 0, listStyle: "none", flex: 1, display: "flex", flexDirection: "column", gap: 6 }} aria-live="polite">
                {stage === "checking" && <li className="muted">{d.tankChecking}</li>}
                {ticket.checks.slice(0, stage === "checking" ? shown : undefined).map((c) => (
                  <li key={c.id} className="row" style={{ justifyContent: "space-between", padding: "6px 10px", borderRadius: 12, background: c.ok ? "var(--buybg)" : "var(--sellbg)" }}>
                    <span style={{ fontWeight: 800, color: c.ok ? "var(--buy)" : "var(--sell)" }}>{c.ok ? "✓" : "✗"} {checkLabel(c.id)}</span>
                    <span className="pixel ltr" style={{ fontSize: 14 }}>
                      {typeof c.value === "number" ? (c.id === "orders_today" || c.id === "no_short" ? fmtNum(c.value, lang) : money(c.value)) : c.value}
                      {c.limit != null && <> / {c.id === "orders_today" || c.id === "no_short" ? fmtNum(c.limit, lang) : money(c.limit)}</>}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="warnstrip" role="note">{d.disclaimerTicket}</div>
            {err && <div className="warnstrip" role="alert" style={{ background: "var(--sellbg)", color: "var(--sell)" }}>{err.text}</div>}

            {stage === "done" && order ? (
              <div className="card" style={{ textAlign: "center", position: "relative" }}>
                <div className="stamp" aria-hidden="true">{d.approved}</div>
                <SpriteSvg name="Leo" px={4} frame="wave" talk />
                <h3 style={{ fontSize: 22 }}>{d.submitted}</h3>
                <p className="pixel ltr" style={{ margin: 4 }}>{order.symbol} · {order.side} · {order.type} · {order.status}{order.mock ? " · MOCK" : ""}</p>
                {order.filled_avg_price != null && <p className="pixel ltr" style={{ margin: 0 }}>{fmtNum(order.filled_qty, lang, { maximumFractionDigits: 6 })} @ {money(order.filled_avg_price)}</p>}
                <button className="primary btn" style={{ marginTop: 10 }} onClick={onClose}>{d.back}</button>
              </div>
            ) : (
              <div className="row" style={{ justifyContent: "flex-end" }}>
                <button className="ghost btn" onClick={() => { setStage("edit"); setTicket(null); setErr(null); }}>{d.back}</button>
                <button className="primary btn" disabled={stage !== "review" || !ticket.ok} onClick={confirm}
                  style={ticket.ok ? undefined : { background: "var(--line)", boxShadow: "none" }}>{d.confirmOrder}</button>
              </div>
            )}
          </div>
        )}

        {!ticket && err && <div className="warnstrip" role="alert" style={{ marginTop: 12, background: "var(--sellbg)", color: "var(--sell)" }}>{err.text}</div>}
      </div>
    </div>
  );
}
