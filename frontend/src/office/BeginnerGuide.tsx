import { useEffect, useState } from "react";
import { api } from "../api";
import { SpriteSvg, charColor } from "../art/Sprite";
import { charName, type CharKey } from "../i18n";
import { usePrefs } from "../prefs";
import { BudgetPlan, money, type Plan } from "./BudgetPlan";
import { Glossed } from "../extras/Glossary";

type Guide = { profile: { amount: number; currency: string; market: string; risk: string }; plan: Plan;
  intro: string | null; closing: string | null; stocks: { ticker: string; simple: string }[];
  tips: { character: CharKey; tip: string }[]; generated: boolean;
  market_tips?: { character: CharKey; tip: string; market: string }[];
  markets?: Record<string, { open: boolean; name: { ar: string; en: string }; hours: { ar: string; en: string } }> };

/** After a beginner run: Leo's whole-share plan for the amount, what the team found in plain words,
 *  and one practical tip from each character's expertise. */
export function BeginnerGuide({ scanId, onOpen, onClose }: { scanId: string; onOpen: (sid: string) => void; onClose: () => void }) {
  const { prefs, t } = usePrefs();
  const lang = prefs.lang;
  const ar = lang === "ar";
  const [g, setG] = useState<Guide | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    setG(null); setFailed(false);
    api.get<Guide>(`/api/beginner/${scanId}/guide?lang=${lang}`).then((r) => alive && setG(r)).catch(() => alive && setFailed(true));
    return () => { alive = false; };
  }, [scanId, lang]);
  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-label={ar ? "دليل المبتدئ" : "Beginner guide"}>
      <div className="modal stack" style={{ gap: 14, maxWidth: 760 }}>
        <div className="row" style={{ gap: 10 }}>
          <SpriteSvg name="Leo" px={2} />
          <div className="stack" style={{ gap: 0 }}>
            <h2 style={{ fontSize: 24, margin: 0 }}>{ar ? "دليلك كمبتدئ" : "Your beginner guide"}</h2>
            {g && <span className="muted">{ar
              ? `مبلغك ${money(g.profile.amount, g.profile.currency, lang)} · ${{ sa: "السوق السعودي", us: "السوق الأمريكي", both: "السوقين" }[g.profile.market] ?? ""} · ${{ cautious: "حذر", balanced: "متوازن", bold: "جريء" }[g.profile.risk] ?? ""}`
              : `Your ${money(g.profile.amount, g.profile.currency, lang)} · ${{ sa: "Saudi market", us: "US market", both: "both markets" }[g.profile.market] ?? ""} · ${g.profile.risk}`}</span>}
          </div>
        </div>
        {failed && <div className="warnstrip">{t.error}</div>}
        {!g && !failed && <p aria-busy="true">{ar ? "الفريق يجهّز لك الشرح…" : "The team is preparing your guide…"}</p>}
        {g && <>
          {g.intro && <p style={{ margin: 0, fontSize: 17, lineHeight: 1.9, fontWeight: 600 }}>{g.intro}</p>}
          <BudgetPlan plan={g.plan} onOpen={onOpen} />
          {g.stocks.length > 0 && (
            <section className="stack" style={{ gap: 8 }}>
              <b style={{ fontSize: 17 }}>{ar ? "وش لقى الفريق، بكلام بسيط" : "What the team found, in plain words"}</b>
              {g.stocks.map((s) => (
                <div key={s.ticker} className="logitem"><b className="pixel ltr">{s.ticker}</b><div style={{ lineHeight: 1.8 }}><Glossed text={s.simple} /></div></div>
              ))}
            </section>
          )}
          <section className="stack" style={{ gap: 8 }}>
            <b style={{ fontSize: 17 }}>{ar ? "نصايح الفريق من خبرتهم" : "Tips from the team's experience"}</b>
            {g.tips.map((tp, i) => (
              <div key={i} className="row tip" style={{ alignItems: "flex-start", flexWrap: "nowrap", gap: 10 }}>
                <SpriteSvg name={tp.character} px={1} />
                <div className="stack" style={{ gap: 2 }}>
                  <b style={{ color: charColor(tp.character) }}>{charName(tp.character, lang)}</b>
                  <span style={{ lineHeight: 1.8 }}><Glossed text={tp.tip} /></span>
                </div>
              </div>
            ))}
          </section>
          {g.markets && Object.entries(g.markets).map(([k, m]) => (
            <section key={k} className="card cream stack" style={{ gap: 8, padding: 14 }}>
              <b style={{ fontSize: 17 }}>{ar ? `قبل ما تشتري من ${m.name.ar}` : `Before you buy on the ${m.name.en}`}</b>
              <span className={`chip mkt ${m.open ? "open" : "closed"}`} style={{ alignSelf: "flex-start", height: "auto", minHeight: 30, whiteSpace: "normal" }}>
                <i />{m.open ? (ar ? "مفتوح الآن" : "Open now") : (ar ? "مقفل الآن" : "Closed now")} · {m.hours[lang]}</span>
              {(g.market_tips ?? []).filter((tp) => tp.market === k).map((tp, i) => (
                <div key={i} className="row tip" style={{ alignItems: "flex-start", flexWrap: "nowrap", gap: 10 }}>
                  <SpriteSvg name={tp.character} px={1} />
                  <div className="stack" style={{ gap: 2 }}>
                    <b style={{ color: charColor(tp.character) }}>{charName(tp.character, lang)}</b>
                    <span style={{ lineHeight: 1.8 }}><Glossed text={tp.tip} /></span>
                  </div>
                </div>
              ))}
            </section>
          ))}
          {g.closing && <p style={{ margin: 0, lineHeight: 1.8, fontWeight: 700 }}>{g.closing}</p>}
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>{t.disclaimer}</p>
        </>}
        <div className="row" style={{ justifyContent: "flex-end" }}><button className="primary btn" onClick={onClose}>{t.close}</button></div>
      </div>
    </div>
  );
}
