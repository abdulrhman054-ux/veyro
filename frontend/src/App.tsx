import { useCallback, useEffect, useState } from "react";
import { api, type Settings } from "./api";
import { click, unlockAudio } from "./audio";
import { usePrefs } from "./prefs";
import { Office } from "./office/Office";
import { Report } from "./screens/Report";
import { HistoryScreen } from "./screens/History";
import { SettingsScreen } from "./screens/Settings";
import { ExecProvider, ModeBadge } from "./exec/ExecContext";
import { EXD } from "./exec/execI18n";
import { OrdersScreen } from "./exec/OrdersScreen";
import { ProposeButton } from "./exec/OrderTicket";
import { TradingSettings } from "./exec/TradingSettings";
import { WorldNews } from "./screens/WorldNews";
import { LiveBoard } from "./screens/LiveBoard";
import { Welcome } from "./components/Welcome";
import { AlertsBell, AssistantProvider } from "./assistant/Assistant";

type Screen = "office" | "live" | "world" | "report" | "history" | "orders" | "settings";

const LEAF = (
  <svg width="42" height="42" viewBox="0 0 12 12" shapeRendering="crispEdges" aria-hidden="true">
    <path d="M5 0h3v1h2v2h1v4h-1v2H8v1H6v2H5v-2H3V9H2V7H1V3h1V1h3z" fill="#4A3426" />
    <path d="M5 1h3v1h2v1h0v4H9v2H6v1H5V9H3V7H2V3h1V2h2z" fill="#6CC38E" /><path d="M5 3h1v6H5z" fill="#3E9A68" />
  </svg>
);
const SUN = <svg width="20" height="20" viewBox="0 0 10 10" shapeRendering="crispEdges" aria-hidden="true"><path fill="currentColor" d="M4 0h2v2H4zM4 8h2v2H4zM0 4h2v2H0zM8 4h2v2H8zM3 3h4v4H3zM1 1h1v1H1zM8 1h1v1H8zM1 8h1v1H1zM8 8h1v1H8z" /></svg>;
const MOON = <svg width="20" height="20" viewBox="0 0 10 10" shapeRendering="crispEdges" aria-hidden="true"><path fill="currentColor" d="M3 0h4v1H5v1H4v2H3v2h1v2h1v1h2v1H3V9H2V8H1V6H0V4h1V2h1V1h1z" /></svg>;
const SPEAKER = <svg width="18" height="18" viewBox="0 0 10 10" shapeRendering="crispEdges" aria-hidden="true"><path fill="currentColor" d="M0 3h2V2h1V1h1V0h1v10H4V9H3V8H2V7H0zM7 2h1v1h1v4H8v1H7V7h1V3H7z" /></svg>;

export default function App() {
  return <ExecProvider><AssistantProvider><Shell /></AssistantProvider></ExecProvider>;
}

function Shell() {
  const { t, prefs, set, night } = usePrefs();
  const [screen, setScreen] = useState<Screen>("office");
  // Every screen stays mounted after its first visit, so what you typed, searched or opened is still
  // there when you come back (screens refresh their data when shown again).
  const [seen, setSeen] = useState<Set<Screen>>(() => new Set<Screen>(["office"]));
  useEffect(() => { setSeen((v) => (v.has(screen) ? v : new Set(v).add(screen))); }, [screen]);
  const [reportId, setReportId] = useState<string | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [market, setMarket] = useState<{ open: boolean | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingStart, setPendingStart] = useState<{ ticker: string; trade_date: string; nonce: number } | null>(null);
  const [pendingScan, setPendingScan] = useState<{ id: string; nonce: number } | null>(null);
  const openMorning = () => { api.get<{ morning_scan: string | null }>("/api/alerts").then((r) => { if (r.morning_scan) setPendingScan({ id: r.morning_scan, nonce: Date.now() }); go("office"); }).catch(() => go("office")); };

  useEffect(() => { api.get<Settings>("/api/settings").then(setSettings).catch(() => {}); }, []);
  // "Run it now" in Settings (and other places) ask the shell to follow a scan in the Office.
  useEffect(() => {
    const f = (e: Event) => { const id = (e as CustomEvent<string>).detail; if (id) { setPendingScan({ id, nonce: Date.now() }); setScreen("office"); } };
    window.addEventListener("veyro:follow-scan", f);
    return () => window.removeEventListener("veyro:follow-scan", f);
  }, []);
  useEffect(() => {
    const load = () => api.get<{ open: boolean | null }>("/api/market/status").then(setMarket).catch(() => setMarket({ open: null }));
    load(); const h = setInterval(load, 60_000); return () => clearInterval(h);
  }, []);

  const go = (s: Screen) => { click(); unlockAudio(); setScreen(s); window.scrollTo(0, 0); };
  const openReport = useCallback((id: string) => { setReportId(id); setScreen("report"); }, []);
  const onBusy = useCallback((b: boolean) => setBusy(b), []);

  const mkt = market?.open === true ? ["open", t.marketOpen] : market?.open === false ? ["closed", t.marketClosed] : ["", t.marketUnknown];

  return (
    <div className="app">
      <header className="topbar">
        <button className="brand" onClick={() => go("office")} aria-label={t.brand}>
          {LEAF}
          <span style={{ textAlign: "start" }}><b>{t.brand}</b><small>{t.tagline}</small></span>
        </button>
        <nav className="nav" aria-label={t.nav}>
          {(["office", "live", "world", "report", "history", "orders", "settings"] as Screen[]).map((s) => (
            <button key={s} className="tab" aria-current={screen === s ? "page" : undefined} onClick={() => go(s)}>
              {s === "orders" ? EXD[prefs.lang].orders : s === "world" ? (prefs.lang === "ar" ? "أخبار العالم" : "World news")
                : s === "live" ? <><span className="navlive" aria-hidden="true" />{prefs.lang === "ar" ? "مباشر" : "Live"}</> : t[s]}
            </button>
          ))}
        </nav>
        <div className="tools">
          <ModeBadge />
          <AlertsBell onOpenMorning={openMorning} />
          <span className={`chip mkt ${mkt[0]}`} role="status"><i />{mkt[1]}</span>
          <button className="pill btn" onClick={() => set({ lang: prefs.lang === "ar" ? "en" : "ar" })} aria-label={t.langAria} lang={prefs.lang === "ar" ? "en" : "ar"}>{t.langBtn}</button>
          <button className="pill btn" onClick={() => set({ theme: night ? "day" : "night" })} aria-label={t.themeAria}>{night ? SUN : MOON}</button>
          <button className="pill btn" onClick={() => { unlockAudio(); set({ sound: !prefs.sound }); }} aria-label={t.soundAria} aria-pressed={prefs.sound} style={{ opacity: prefs.sound ? 1 : 0.6 }}>
            {SPEAKER}<span>{prefs.sound ? t.sound : t.muted}</span>
          </button>
        </div>
      </header>

      <main>
        {/* Office stays mounted so a running session keeps playing while you peek at other screens. */}
        <div hidden={screen !== "office"} className="stack">
          <Office settings={settings} onOpenReport={openReport} onBusy={onBusy} marketOpen={market?.open ?? null} pendingStart={pendingStart} pendingScan={pendingScan}
            renderVerdictExtra={(sid, tk, rating, demo) => <ProposeButton sessionId={sid} ticker={tk} rating={rating} demo={demo} />} />
        </div>
        {seen.has("report") && <div hidden={screen !== "report"}><Report sessionId={reportId} active={screen === "report"} /></div>}
        {seen.has("history") && <div hidden={screen !== "history"}><HistoryScreen onOpen={openReport} settings={settings} active={screen === "history"}
          onResume={(ticker, trade_date) => { setPendingStart({ ticker, trade_date, nonce: Date.now() }); go("office"); }} /></div>}
        {seen.has("world") && <div hidden={screen !== "world"}><WorldNews /></div>}
        {seen.has("live") && <div hidden={screen !== "live"}><LiveBoard active={screen === "live"}
          onAnalyze={(tk) => { window.dispatchEvent(new CustomEvent("veyro:pick-ticker", { detail: tk })); go("office"); }} /></div>}
        {seen.has("orders") && <div hidden={screen !== "orders"}><OrdersScreen onOpenSettings={() => go("settings")} active={screen === "orders"} /></div>}
        {seen.has("settings") && <div hidden={screen !== "settings"}><SettingsScreen settings={settings} onChange={setSettings} extra={<TradingSettings />} /></div>}
      </main>
      <Welcome />
      {busy && screen !== "office" && (
        <button className="toast btn" style={{ border: 0, cursor: "pointer" }} onClick={() => go("office")}>{t.running} · {t.office}</button>
      )}
    </div>
  );
}
