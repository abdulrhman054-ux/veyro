import { useEffect, useState } from "react";
import { api } from "../api";
import { SpriteSvg } from "../art/Sprite";
import { fmtUsd } from "../i18n";
import { usePrefs } from "../prefs";
import { EXD } from "./execI18n";
import { ModeBadge, execErrorText, useExec, type ExecLimits, type ExecStatus } from "./ExecContext";

export function TradingSettings() {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const d = EXD[lang];
  const { status, setStatus } = useExec();
  const [msg, setMsg] = useState<string | null>(null);
  const [unlock, setUnlock] = useState(false);
  if (!status) return null;

  const call = async (fn: () => Promise<ExecStatus>) => {
    setMsg(null);
    try { setStatus(await fn()); return true; } catch (e) { setMsg(execErrorText(e, lang).text); return false; }
  };
  const setMode = (mode: string, phrase?: string) => call(() => api.post<ExecStatus>("/api/exec/mode", { mode, phrase }));

  return (
    <section className="card stack" aria-labelledby="tr-h" style={{ border: status.mode === "live" ? "4px solid #C62828" : undefined }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row"><SpriteSvg name="Tank" px={2} /><h2 id="tr-h" style={{ fontSize: 22 }}>{d.tradingTitle}</h2></div>
        <ModeBadge big />
      </div>
      <div className="label">{d.modeLabel}</div>
      <div className="segbtns" role="group" aria-label={d.modeLabel}>
        <button aria-pressed={status.mode === "off"} onClick={() => setMode("off")}>{d.off}</button>
        <button aria-pressed={status.mode === "paper"} onClick={() => setMode("paper")}>{d.paper}</button>
        <button aria-pressed={status.mode === "live"} onClick={() => (status.mode === "live" ? null : setUnlock(true))}
          style={status.mode === "live" ? { borderColor: "#C62828", background: "#FFEBEE", color: "#B71C1C" } : undefined}>🔒 {d.live}</button>
      </div>
      <p className="muted" style={{ margin: 0, lineHeight: 1.7 }}>
        {status.mode === "off" ? d.offNote : status.mode === "live" ? d.liveNote : status.broker === "mock" ? d.mockNote : d.paperNote}
      </p>
      {msg && <div className="warnstrip" role="alert">{msg}</div>}

      <div className="grid2">
        <KeysForm mode="paper" onDone={setStatus} />
        <KeysForm mode="live" onDone={setStatus} />
      </div>
      <div className="grid2">
        <LimitsForm mode="paper" limits={status.limits.paper} confirmed={status.limits_confirmed.paper} onDone={setStatus} />
        <LimitsForm mode="live" limits={status.limits.live} confirmed={status.limits_confirmed.live} onDone={setStatus} />
      </div>
      <div className="warnstrip" role="note">{d.disclaimerTicket}</div>
      {unlock && <UnlockLive status={status} onClose={() => setUnlock(false)} onUnlock={async (p) => { if (await setMode("live", p)) setUnlock(false); }} />}
    </section>
  );
}

function KeysForm({ mode, onDone }: { mode: "paper" | "live"; onDone: (s: ExecStatus) => void }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const d = EXD[lang];
  const { status } = useExec();
  const [kid, setKid] = useState("");
  const [sec, setSec] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const k = status?.keys[mode];
  const save = async () => {
    setErr(null);
    try { onDone(await api.post<ExecStatus>("/api/exec/keys", { mode, key_id: kid.trim(), secret: sec.trim() })); setKid(""); setSec(""); }
    catch (e) { setErr(execErrorText(e, lang).text); }
  };
  const remove = async () => { try { onDone(await api.del<ExecStatus>(`/api/exec/keys/${mode}`)); } catch (e) { setErr(execErrorText(e, lang).text); } };
  return (
    <div className="card cream stack" style={{ padding: 16 }}>
      <b>{mode === "paper" ? d.paperKeys : d.liveKeys}</b>
      <label className="stack" style={{ gap: 2 }}><span className="label">{d.keyId}</span>
        <input className="field ltr" autoComplete="off" spellCheck={false} value={kid} onChange={(e) => setKid(e.target.value)} /></label>
      <label className="stack" style={{ gap: 2 }}><span className="label">{d.secret}</span>
        <input className="field ltr" type="password" autoComplete="off" value={sec} onChange={(e) => setSec(e.target.value)} /></label>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span>{d.keysSaved}: <b className="pixel ltr">{k?.present ? k.masked : "—"}</b></span>
        <span className="row">
          {k?.present && <button className="ghost btn" onClick={remove}>{d.removeKeys}</button>}
          <button className="primary green btn" style={{ height: 40, fontSize: 15 }} disabled={!kid.trim() || !sec.trim()} onClick={save}>{d.saveKeys}</button>
        </span>
      </div>
      {err && <div className="warnstrip" role="alert">{err}</div>}
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>{d.keysNote}</p>
    </div>
  );
}

function LimitsForm({ mode, limits, confirmed, onDone }: { mode: "paper" | "live"; limits: ExecLimits; confirmed: boolean; onDone: (s: ExecStatus) => void }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const d = EXD[lang];
  const [v, setV] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  useEffect(() => { setV(Object.fromEntries(Object.entries(limits).map(([k, x]) => [k, String(x)]))); }, [limits]);
  const fields: [keyof ExecLimits, string][] = [["max_order_usd", d.maxOrder], ["max_symbol_exposure_usd", d.maxExposure], ["daily_loss_limit_usd", d.dailyLoss], ["max_orders_per_day", d.maxOrdersDay]];
  const save = async () => {
    setErr(null); setOk(false);
    try { onDone(await api.post<ExecStatus>("/api/exec/limits", { mode, ...Object.fromEntries(fields.map(([k]) => [k, Number(v[k])])) })); setOk(true); }
    catch (e) { setErr(execErrorText(e, lang).text); }
  };
  return (
    <div className="card cream stack" style={{ padding: 16 }}>
      <b>{d.limitsFor} {mode === "paper" ? d.paper : d.live} {confirmed ? "✓" : ""}</b>
      {fields.map(([k, label]) => (
        <label key={k} className="row" style={{ justifyContent: "space-between", flexWrap: "nowrap" }}><span style={{ fontWeight: 700, fontSize: 14 }}>{label}</span>
          <input className="field ltr pixel" style={{ width: 130, height: 40 }} type="number" min={1} value={v[k] ?? ""} onChange={(e) => setV({ ...v, [k]: e.target.value })} /></label>
      ))}
      <div className="row" style={{ justifyContent: "flex-end" }}><button className="primary btn" style={{ height: 40, fontSize: 15 }} onClick={save}>{d.saveLimits}</button></div>
      {ok && <span role="status" className="pos" style={{ fontWeight: 800 }}>✓</span>}
      {err && <div className="warnstrip" role="alert">{err}</div>}
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>{d.limitsNote} ({fmtUsd(limits.max_order_usd, lang)})</p>
    </div>
  );
}

function UnlockLive({ status, onClose, onUnlock }: { status: ExecStatus; onClose: () => void; onUnlock: (phrase: string) => void }) {
  const { prefs } = usePrefs();
  const lang = prefs.lang;
  const d = EXD[lang];
  const [phrase, setPhrase] = useState("");
  const target = status.phrases[lang];
  const steps = [
    { ok: status.live_checklist.keys, text: d.stepKeys },
    { ok: status.live_checklist.limits, text: d.stepLimits },
    { ok: phrase.trim() === target, text: `${d.stepPhrase} «${target}»` },
  ];
  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-label={d.unlockLive}>
      <div className="modal" style={{ border: "4px solid #C62828" }}>
        <div className="row"><SpriteSvg name="Tank" px={3} /><h2 style={{ fontSize: 24, color: "#B71C1C" }}>{d.unlockLive}</h2></div>
        <div className="warnstrip" style={{ background: "#FFEBEE", color: "#B71C1C", margin: "12px 0" }}>{d.liveNote} {d.disclaimerTicket}</div>
        <ol style={{ paddingInlineStart: 22, lineHeight: 2 }}>
          {steps.map((s, i) => <li key={i} style={{ fontWeight: 700, color: s.ok ? "var(--buy)" : "var(--ink)" }}>{s.ok ? "✓ " : "○ "}{s.text}</li>)}
        </ol>
        <input className="field" style={{ width: "100%" }} value={phrase} onChange={(e) => setPhrase(e.target.value)} placeholder={d.confirmTyped} aria-label={d.confirmTyped} />
        <div className="row" style={{ justifyContent: "flex-end", marginTop: 14 }}>
          <button className="ghost btn" onClick={onClose}>{d.back}</button>
          <button className="btn" disabled={!steps.every((s) => s.ok)} onClick={() => onUnlock(phrase.trim())}
            style={{ height: 46, padding: "0 22px", borderRadius: 23, border: 0, background: "#C62828", color: "#FFFFFF", fontWeight: 800, opacity: steps.every((s) => s.ok) ? 1 : 0.45 }}>{d.unlockBtn}</button>
        </div>
      </div>
    </div>
  );
}
