import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "../api";
import { SpriteSvg } from "../art/Sprite";
import { pop } from "../audio";
import { fmtNum, fmtUsd } from "../i18n";
import { usePrefs } from "../prefs";
import { EXD, EXEC_ERR } from "./execI18n";

export type ExecLimits = { max_order_usd: number; max_symbol_exposure_usd: number; daily_loss_limit_usd: number; max_orders_per_day: number };
export type ExecStatus = {
  mode: "off" | "paper" | "live"; broker: "none" | "mock" | "alpaca"; live_unlocked: boolean;
  limits: Record<"paper" | "live", ExecLimits>; limits_confirmed: Record<"paper" | "live", boolean>;
  keys: Record<"paper" | "live", { present: boolean; masked: string | null }>;
  live_checklist: { keys: boolean; limits: boolean };
  phrases: Record<"ar" | "en", string>; liquidate_phrases: Record<"ar" | "en", string>;
};
export type BrokerOrder = {
  id: string; symbol: string; side: string; type: string; status: string; qty: number | null; notional: number | null;
  filled_qty: number; filled_avg_price: number | null; limit_price: number | null; submitted_at: string | null; filled_at: string | null; veyro?: boolean; mock?: boolean;
};

type Ctx = { status: ExecStatus | null; refresh: () => Promise<void>; setStatus: (s: ExecStatus) => void; orders: BrokerOrder[]; syncOrders: () => Promise<void> };
const C = createContext<Ctx | null>(null);

/** Error from an /api/exec call -> in-character message in the current language. */
export function execErrorText(e: unknown, lang: "ar" | "en") {
  const code = e instanceof ApiError ? e.code : "error";
  const m = EXEC_ERR[code];
  return m ? { c: m.c, text: m[lang] } : { c: "Leo" as const, text: lang === "ar" ? "صار خطأ غير متوقع." : "Something unexpected went wrong." };
}

export function ExecProvider({ children }: { children: ReactNode }) {
  const { prefs } = usePrefs();
  const [status, setStatus] = useState<ExecStatus | null>(null);
  const [orders, setOrders] = useState<BrokerOrder[]>([]);
  const [toast, setToast] = useState<{ id: number; text: string } | null>(null);
  const langRef = useRef(prefs.lang); langRef.current = prefs.lang;

  const refresh = useCallback(async () => { try { setStatus(await api.get<ExecStatus>("/api/exec/status")); } catch { /* backend down */ } }, []);
  const syncOrders = useCallback(async () => {
    try {
      const r = await api.get<{ orders: BrokerOrder[]; events: { event: string; order: BrokerOrder }[] }>("/api/exec/orders");
      setOrders(r.orders ?? []);
      // Pip announces fills; every number spelled out, nothing hidden behind animation.
      for (const ev of r.events ?? []) {
        const d = EXD[langRef.current]; const o = ev.order; const L = langRef.current;
        if (ev.event === "filled" || ev.event === "partially_filled") {
          setToast({ id: Date.now(), text: `${d.pipFilled}: ${o.side === "buy" ? d.buy : d.sell} ${o.symbol} · ${fmtNum(o.filled_qty, L, { maximumFractionDigits: 6 })} @ ${fmtUsd(o.filled_avg_price, L)}` });
          pop();
        } else if (ev.event === "cancelled") {
          setToast({ id: Date.now(), text: `${d.pipCancelled}: ${o.symbol}` });
        }
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!status || status.mode === "off") { setOrders([]); return; }
    void syncOrders();
    const h = setInterval(syncOrders, 5000);
    return () => clearInterval(h);
  }, [status?.mode, syncOrders]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (toast) { const h = setTimeout(() => setToast(null), 7000); return () => clearTimeout(h); } }, [toast]);

  return (
    <C.Provider value={{ status, refresh, setStatus, orders, syncOrders }}>
      {children}
      {toast && (
        <div className="toast" role="status" style={{ display: "flex", alignItems: "center", gap: 10, background: "var(--card)", color: "var(--ink)", border: "3px solid #E0453A" }}>
          <SpriteSvg name="Pip" px={2} talk frame="wave" /><b>{toast.text}</b>
        </div>
      )}
    </C.Provider>
  );
}

export function useExec() {
  const c = useContext(C);
  if (!c) throw new Error("ExecProvider missing");
  return c;
}

export function ModeBadge({ big = false }: { big?: boolean }) {
  const { status } = useExec();
  const { prefs } = usePrefs();
  const d = EXD[prefs.lang];
  if (!status || status.mode === "off") return null;
  const live = status.mode === "live";
  const mock = status.broker === "mock";
  const style = live
    ? { background: "#C62828", color: "#FFFFFF", boxShadow: "0 0 0 3px #FFCDD2" }
    : mock ? { background: "#FFE680", color: "#5A4200" } : { background: "#D6E6FF", color: "#123C7A" };
  return (
    <span className="chip pixel" role="status" aria-live="polite" style={{ ...style, height: big ? 36 : 30, fontSize: big ? 16 : 14 }}>
      {live ? d.liveBadge : mock ? d.mockBadge : d.paperBadge}
    </span>
  );
}
