import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtNum } from "../i18n";
import { usePrefs } from "../prefs";

export type PriceAlert = { id: number; symbol: string; op: "above" | "below"; value: number; created_at: string; triggered_at: string | null; triggered_price: number | null };

/** 🔔 on a live tile: "tell me when it goes above / below". */
export function AlertButton({ symbol, price, onChange }: { symbol: string; price?: number; onChange: (a: PriceAlert[]) => void }) {
  const { prefs } = usePrefs();
  const ar = prefs.lang === "ar";
  const [open, setOpen] = useState(false);
  const [op, setOp] = useState<"above" | "below">("above");
  const [val, setVal] = useState("");
  const [err, setErr] = useState(false);
  useEffect(() => { if (open && price != null && !val) setVal(String(+(price * (op === "above" ? 1.02 : 0.98)).toFixed(2))); }, [open]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!open) return <button className="pill btn" style={{ width: 34, height: 30, padding: 0 }} aria-label={ar ? "تنبيه سعر" : "Price alert"} title={ar ? "تنبيه سعر" : "Price alert"} onClick={() => setOpen(true)}>🔔</button>;
  const save = async () => {
    const v = Number(val);
    if (!(v > 0)) { setErr(true); return; }
    try { const r = await api.post<{ alerts: PriceAlert[] }>("/api/price_alerts", { symbol, op, value: v }); onChange(r.alerts); setOpen(false); setVal(""); }
    catch { setErr(true); }
  };
  return (
    <div className="alertform" role="group" aria-label={ar ? "تنبيه سعر" : "Price alert"}>
      <select className="field" value={op} onChange={(e) => setOp(e.target.value as "above" | "below")}>
        <option value="above">{ar ? "إذا صار فوق" : "If above"}</option><option value="below">{ar ? "إذا نزل تحت" : "If below"}</option>
      </select>
      <input className="field ltr" inputMode="decimal" value={val} aria-invalid={err} onChange={(e) => { setVal(e.target.value); setErr(false); }}
        onKeyDown={(e) => { if (e.key === "Enter") void save(); if (e.key === "Escape") setOpen(false); }} />
      <button className="primary btn mini" onClick={save}>{ar ? "نبّهني" : "Alert me"}</button>
      <button className="linkish" onClick={() => setOpen(false)}>{ar ? "إلغاء" : "Cancel"}</button>
    </div>
  );
}

export function AlertList({ alerts, onChange }: { alerts: PriceAlert[]; onChange: (a: PriceAlert[]) => void }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang, ar = lang === "ar";
  if (!alerts.length) return null;
  return (
    <section className="card stack" style={{ gap: 8, padding: 14 }}>
      <b style={{ fontSize: 17 }}>🔔 {ar ? "تنبيهات الأسعار" : "Price alerts"}</b>
      {alerts.map((a) => (
        <div key={a.id} className="row" style={{ justifyContent: "space-between", gap: 8 }}>
          <span><b className="pixel ltr">{a.symbol}</b> {a.op === "above" ? (ar ? "فوق" : "above") : (ar ? "تحت" : "below")} <span className="ltr">{fmtNum(a.value, "en", { maximumFractionDigits: 4 })}</span>
            {a.triggered_at ? <span className="pos"> · ✓ {ar ? "تحقق عند" : "hit at"} <span className="ltr">{fmtNum(a.triggered_price, "en", { maximumFractionDigits: 4 })}</span></span>
              : <span className="muted"> · {ar ? "ننتظر" : "waiting"}</span>}</span>
          <button className="linkish" onClick={() => api.del<{ alerts: PriceAlert[] }>(`/api/price_alerts/${a.id}`).then((r) => onChange(r.alerts)).catch(() => {})}>{ar ? "حذف" : "Delete"}</button>
        </div>
      ))}
      <span className="muted" style={{ fontSize: 12 }}>{ar ? "التنبيه يوصل للجرس فوق وإشعار ويندوز، ويشتغل والتطبيق مفتوح أو في شريط المهام." : "Alerts reach the bell and Windows notifications while Veyro is open or in the tray."}</span>
    </section>
  );
}
