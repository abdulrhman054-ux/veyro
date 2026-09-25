import { useEffect, useState } from "react";
import { api, type SessionRow } from "../api";
import { RATING, fmtDate, fmtPct, fmtUsd } from "../i18n";
import { usePrefs } from "../prefs";
import { EXD } from "../exec/execI18n";
import { PageHeader } from "../components/PageHeader";
import { Backtest, FrameworkMemory } from "./FrameworkLab";
import { BrunoCard } from "../assistant/Assistant";
import type { Settings } from "../api";

/** Did the call beat SPY? Only directional calls are scored; Hold/Review/Demo are neutral. */
function score(r: SessionRow): "beat" | "lagged" | "neutral" | null {
  if (r.ret == null || r.spy_ret == null) return null;
  const tone = RATING[r.rating ?? ""]?.tone;
  if (r.mode === "demo" || tone === "hold" || tone === "none" || !tone) return "neutral";
  const excess = r.ret - r.spy_ret;
  if (Math.abs(excess) < 0.0005) return "neutral";  // a tie (e.g. no price move yet) is neither a win nor a loss
  return (tone === "buy" ? excess > 0 : excess < 0) ? "beat" : "lagged";
}

export function HistoryScreen({ onOpen, onResume, settings, active = true }: { onOpen: (id: string) => void; onResume?: (ticker: string, date: string) => void; settings?: Settings | null; active?: boolean }) {
  const { t, prefs } = usePrefs();
  const lang = prefs.lang;
  const [rows, setRows] = useState<SessionRow[] | null>(null);
  const [acted, setActed] = useState<Record<string, { submitted: number; filled: number }>>({});
  // Refreshed on every visit (new sessions appear) while the screen keeps its own state between visits.
  useEffect(() => { if (active) api.get<{ sessions: SessionRow[] }>("/api/sessions").then((r) => setRows(r.sessions)).catch(() => setRows((x) => x ?? [])); }, [active]);
  useEffect(() => { if (active) api.get<Record<string, { submitted: number; filled: number }>>("/api/exec/acted").then(setActed).catch(() => {}); }, [active]);
  const ed = EXD[lang];
  const excess = (r: SessionRow) => (r.ret != null && r.spy_ret != null ? r.ret - r.spy_ret : null);
  const avg = (xs: (number | null)[]) => { const v = xs.filter((x): x is number => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  const real = (rows ?? []).filter((r) => r.mode === "real" && r.status === "done");
  const actedAvg = avg(real.filter((r) => acted[r.id]?.submitted).map(excess));
  const ignoredAvg = avg(real.filter((r) => !acted[r.id]?.submitted).map(excess));

  const scored = (rows ?? []).map((r) => ({ r, s: score(r) }));
  const directional = scored.filter((x) => x.s === "beat" || x.s === "lagged");
  const beats = directional.filter((x) => x.s === "beat").length;

  return (
    <div className="stack" style={{ gap: 18 }}>
    <PageHeader host="Bruno" title={t.historyTitle} sub={t.historySub}
      say={lang === "ar" ? "بدون تجميل… غرر" : "No sugar-coating… grr"} />
    <div className="report">
      <div className="right">
        <section className="card stack">
          {rows === null ? <p aria-busy="true">…</p> : rows.length === 0 ? <p className="muted">{t.noHistory}</p> : (
            <div style={{ overflowX: "auto" }}>
              <table className="table">
                <thead><tr>
                  <th>{t.colTicker}</th><th>{t.colVerdict}</th><th>{t.colDate}</th><th>{t.colThen}</th><th>{t.colNow}</th>
                  <th>{t.colRet}</th><th>{t.colSpy}</th><th>{t.colScore}</th><th>{ed.actedOn}</th><th><span className="sr">{t.view}</span></th>
                </tr></thead>
                <tbody>
                  {scored.map(({ r, s }) => {
                    const rt = RATING[r.rating ?? ""];
                    return (
                      <tr key={r.id}>
                        <td><b className="pixel ltr" style={{ fontSize: 18 }}>{r.ticker}</b>{r.mode === "demo" && <span className="chip demo" style={{ marginInlineStart: 6, height: 22, fontSize: 12 }}>{t.demo}</span>}</td>
                        <td>{rt ? <span className={`vchip ${rt.tone}`}>{lang === "ar" ? rt.ar : rt.en}</span> : <span className="muted">{r.status}</span>}</td>
                        <td>{fmtDate(r.created_at, lang)}</td>
                        <td className="pixel ltr">{r.price_at_verdict ? fmtUsd(r.price_at_verdict, lang) : t.unavailable}</td>
                        <td className="pixel ltr">{r.price_now ? fmtUsd(r.price_now, lang) : t.unavailable}</td>
                        <td className={`pixel ltr ${r.ret != null ? (r.ret >= 0 ? "pos" : "neg") : ""}`}>{fmtPct(r.ret, lang) ?? "—"}</td>
                        <td className={`pixel ltr ${r.spy_ret != null ? (r.spy_ret >= 0 ? "pos" : "neg") : ""}`}>{r.benchmark ?? "SPY"} {fmtPct(r.spy_ret, lang) ?? "—"}</td>
                        <td style={{ fontWeight: 800 }}>{s === "beat" ? <span className="pos">{t.beat}</span> : s === "lagged" ? <span className="neg">{t.lagged}</span> : s === "neutral" ? <span className="muted">{t.neutral}</span> : "—"}</td>
                        <td>{acted[r.id]?.submitted ? <span className="vchip buy">{ed.acted}</span> : <span className="muted">{ed.ignored}</span>}</td>
                        <td>{r.mode === "real" && (r.status === "error" || r.status === "cancelled") && onResume &&
                          <button className="ghost btn" onClick={() => onResume(r.ticker, r.trade_date)}>{lang === "ar" ? "استئناف" : "Resume"}</button>}
                          {r.status === "done" && <button className="ghost btn" onClick={() => onOpen(r.id)}>{t.view}</button>}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted" style={{ margin: 0, fontSize: 14 }}>{t.source}: Yahoo Finance (yfinance). {t.disclaimer}</p>
        </section>
      </div>
      <div className="left" style={{ width: 340 }}>
        <BrunoCard />
        <section className="card cream stack" style={{ gap: 6 }}>
          <b>{lang === "ar" ? "برونو يقول:" : "Bruno says:"}</b>
          <p style={{ margin: 0, lineHeight: 1.7 }}>{lang === "ar"
            ? "أنا أشكّك بكل شي، فأنا أحسب النتائج: كم مرة القرار تفوّق على المؤشر، وكم مرة لا. غرر…"
            : "I doubt everything, so I keep score: how often the call beat its benchmark, and how often it didn't. grr…"}</p>
        </section>
        <section className="card" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div><div className="label">{t.sessions}</div><div className="pixel" style={{ fontSize: 30 }}>{rows?.length ?? "—"}</div></div>
          <div><div className="label">{t.beatSpy}</div><div className="pixel ltr" style={{ fontSize: 30 }}>{directional.length ? `${beats}/${directional.length}` : "—"}</div></div>
        </section>
        <section className="card stack" style={{ gap: 8 }}>
          <b>{ed.actedVsIgnored}</b>
          <div className="row" style={{ justifyContent: "space-between" }}><span>{ed.acted} · {ed.avgExcess}</span><b className={`pixel ltr ${(actedAvg ?? 0) >= 0 ? "pos" : "neg"}`}>{fmtPct(actedAvg, lang) ?? "—"}</b></div>
          <div className="row" style={{ justifyContent: "space-between" }}><span>{ed.ignored} · {ed.avgExcess}</span><b className={`pixel ltr ${(ignoredAvg ?? 0) >= 0 ? "pos" : "neg"}`}>{fmtPct(ignoredAvg, lang) ?? "—"}</b></div>
        </section>
      </div>
    </div>
    <FrameworkMemory />
    <Backtest settings={settings ?? null} />
    </div>
  );
}
