export class ApiError extends Error {
  constructor(public status: number, public code: string) { super(code); }
}

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let code = "error";
    try { const j = await r.json(); code = j.code || j.detail || j.error || code; } catch { /* ignore */ }
    throw new ApiError(r.status, typeof code === "string" ? code : "error");
  }
  const j = await r.json();
  // Expected refusals come back as 200 { ok: false, code } (see backend): surface them as errors.
  if (j && typeof j === "object" && j.ok === false && typeof j.code === "string") throw new ApiError(200, j.code);
  return j as T;
}

export const api = {
  get: <T,>(u: string) => req<T>("GET", u),
  post: <T,>(u: string, b?: unknown) => req<T>("POST", u, b ?? {}),
  put: <T,>(u: string, b: unknown) => req<T>("PUT", u, b),
  del: <T,>(u: string) => req<T>("DELETE", u),
};

export function openStream(path: string, onEvent: (ev: VEvent) => void, onClose?: () => void): () => void {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}${path}`);
  ws.onmessage = (m) => { try { onEvent(JSON.parse(m.data)); } catch { /* ignore bad frame */ } };
  ws.onclose = () => onClose?.();
  return () => { ws.onclose = null; ws.close(); };
}

// ---- shared types
export type Estimate = { known: boolean; low: number | null; high: number | null; currency: string; sessions: number };
export type KeyInfo = { present: boolean; masked: string | null; source: "app" | "env" | "none" };
export type Settings = {
  provider: string; quick_model: string | null; deep_model: string | null;
  providers: Record<string, { label: string; quick: string[]; deep: string[]; extra?: boolean; needs_key?: boolean; listable?: boolean;
    recommend?: { quick: string | null; deep: string | null; why_ar: string; why_en: string } | null }>;
  reasoning_depth: string;
  anthropic_workspace_id: string | null;
  keys: Record<string, KeyInfo>; estimate: Estimate; pricing?: Record<string, [number, number]>; limits?: { batch: number; screen: number }; data_source?: string;
  spend?: { month: string; spent: number; sessions: number; unpriced_sessions: number; cap: number | null;
    reserved?: number; other_usd?: number; other_calls?: number; unpriced_calls?: number };
  custom_prices?: Record<string, [number, number]>;
  team: { analysts: string[]; debate_rounds: number; risk_rounds: number };
  data_keys: Record<"fred" | "alpha_vantage" | "typesafe", { present: boolean; masked: string | null }>;
  sharia?: { enabled: boolean; method: string; hide: boolean; methods?: Record<string, { ar: string; en: string }> };
  broker_fees?: Record<"sa" | "us", { rate: number; min: number; vat: number; set: boolean }>;
};
export type History = { available: boolean; ticker?: string; dates?: string[]; closes?: number[]; source?: string };
export type PriceInfo = { price: number | null; spy: number | null; as_of: string | null; source: string | null };
export type Source = { tool: string; category: string | null; vendor: string; ok: boolean; calls: number };
export type Verdict = {
  rating: string; line: string; reason: string; conviction: string; lang: string; turn_id: number;
  sources: Source[]; price?: PriceInfo; disclaimer?: string; texts?: Partial<Record<"ar" | "en", { line: string; reason: string }>>;
};
export type Usage = { models: Record<string, { input: number; output: number; calls: number; cost_usd?: number }>; cost_usd: number | null; pricing_known: boolean };
export type VEvent =
  | { type: "session"; id: string; ticker: string; mode: "real" | "demo"; lang: string; trade_date: string; estimate: Estimate;
      on_break?: string[]; asset_type?: string; benchmark?: string; portfolio_used?: boolean; portfolio_broker?: string | null; debate_rounds?: number; risk_rounds?: number }
  | { type: "team"; on_break: string[]; asset_type: string }
  | { type: "market"; data: History | null; available: boolean }
  | { type: "agent_started"; character: string; node: string }
  | { type: "agent_message"; character: string; node: string; turn_id: number; text: string; lang: string; texts?: Partial<Record<"ar" | "en", string>> }
  | { type: "agent_done"; character: string; node: string }
  | ({ type: "verdict" } & Verdict)
  | { type: "usage"; data: Usage }
  | { type: "error"; code: string; character: string; text: string; texts?: Partial<Record<"ar" | "en", string>>; detail?: string }
  | { type: "end"; status: string }
  | { type: "scan"; id: string; kind: string; screener: string | null; tickers: string[]; source: Candidate[] | null }
  | { type: "scan_session"; index: number; ticker: string; session_id: string }
  | { type: "scan_result"; index: number; ticker: string; session_id: string; status: string; rating: string | null }
  | { type: "scan_ranked"; ranking: { ticker: string; rating: string | null; session_id: string; status: string }[] };

export type Candidate = { symbol: string; name: string | null; price: number | null; change_pct: number | null; volume: number | null; as_of: string; source: string };

export type Turn = {
  id: number; seq: number; character: string; node: string; detail_en: string;
  voice_ar: string | null; voice_en: string | null; detail_ar: string | null; created_at: string;
};
export type SessionRow = {
  id: string; ticker: string; trade_date: string; created_at: string; finished_at: string | null; mode: "real" | "demo";
  provider: string | null; lang: string; status: string; rating: string | null; verdict: Verdict | null;
  price_at_verdict: number | null; spy_at_verdict: number | null; price_time: string | null; price_source: string | null;
  cost_usd: number | null; scan_id: string | null;
  price_now?: number | null; spy_now?: number | null; ret?: number | null; spy_ret?: number | null;
  benchmark?: string; config?: SessionConfig | null;
};
export type SessionConfig = { analysts?: string[]; on_break?: string[]; asset_type?: string; debate_rounds?: number; risk_rounds?: number;
  benchmark?: string; past_context?: string; portfolio_context?: string; portfolio_broker?: string | null;
  trade_date?: string; past_date?: boolean; resumed?: boolean; reasoning?: string; export_dir?: string;
  optional_data?: { fred: boolean; alpha_vantage: boolean; jev?: boolean } };
export type SessionFull = SessionRow & { turns: Turn[]; usage: Usage | null; quick_model: string | null; deep_model: string | null; error: string | null; config: SessionConfig | null };
