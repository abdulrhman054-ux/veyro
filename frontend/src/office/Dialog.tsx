import { useEffect, useRef, useState } from "react";
import { charColor } from "../art/Sprite";
import { VOICES, errorBonk, verdictJingle, voiceBlip } from "../audio";
import { CONVICTION, RATING, charName, fmtUsd, type CharKey, type Lang } from "../i18n";
import { usePrefs } from "../prefs";
import type { Verdict } from "../api";
import type { Line } from "./useSession";
import { useLineText } from "./lineText";
import { useVerdictText } from "./verdictText";

/** Typewriter dialogue box. Click (or Enter/Space) finishes the line, click again advances. */
export function SpeechBox({ line, lang, onDone }: { line: Line; lang: Lang; onDone: () => void }) {
  const { motionOff } = usePrefs();
  const text = useLineText(line.texts, line.turnId, lang, !line.demo && line.kind !== "error") ?? "";
  const [n, setN] = useState(motionOff ? text.length : 0);
  const done = text.length > 0 && n >= text.length;
  const doneRef = useRef(onDone); doneRef.current = onDone;

  useEffect(() => {
    setN(motionOff ? text.length : 0);
  }, [line.id, text, motionOff]);
  useEffect(() => { if (line.kind === "error") errorBonk(); }, [line.id, line.kind]);

  useEffect(() => {
    if (!text) return;
    if (done) {
      const hold = Math.min(6000, 1600 + text.length * 22);
      const h = window.setTimeout(() => doneRef.current(), line.kind === "error" ? hold + 3000 : hold);
      return () => clearTimeout(h);
    }
    const h = window.setTimeout(() => {
      setN((v) => {
        const nv = Math.min(text.length, v + 1);
        voiceBlip(line.character, text[nv - 1], nv);
        return nv;
      });
    }, VOICES[line.character]?.msPerChar ?? 30);
    return () => clearTimeout(h);
  }, [n, done, text, line.kind, line.character]);

  const advance = () => (done ? onDone() : setN(text.length));
  return (
    <button className={`dlg${line.kind === "error" ? " err" : ""}`} dir={lang === "ar" ? "rtl" : "ltr"} onClick={advance}
      aria-label={`${charName(line.character, lang)}: ${text}`}>
      <span className="tag" style={{ background: charColor(line.character) }}>{charName(line.character, lang)}</span>
      <span className="dtext" aria-hidden="true" style={{ display: "block" }}>{text ? text.slice(0, n) : "…"}{!done && <span className="caret" />}</span>
      {done && <span className="next" aria-hidden="true" />}
    </button>
  );
}

export function IdleBox({ text, lang }: { text: string; lang: Lang }) {
  const { t } = usePrefs();
  return (
    <div className="dlg" dir={lang === "ar" ? "rtl" : "ltr"} style={{ cursor: "default" }}>
      <span className="tag" style={{ background: "#3E9A68" }}>{t.brand}</span>
      <span className="dtext" style={{ display: "block" }}>{text}</span>
      <span className="next" aria-hidden="true" />
    </div>
  );
}

const CONF = ["#F2A43A", "#6CC38E", "#E0453A", "#3F7FE0", "#F7CE4F", "#8A5CC7", "#FFFFFF"];

export function VerdictBox({ v, lang, onOpenReport, demo, sessionId, extra }: { v: Verdict; lang: Lang; onOpenReport: () => void; demo: boolean; sessionId: string | null; extra?: React.ReactNode }) {
  const { t, motionOff } = usePrefs();
  const r = RATING[v.rating] ?? RATING.REVIEW;
  const c = CONVICTION[v.conviction] ?? CONVICTION.unstated;
  useEffect(() => { verdictJingle(r.tone); }, [r.tone]);
  const price = v.price?.price;
  const reason = useVerdictText(sessionId, v, lang)?.reason ?? null;
  return (
    <div className="dlg verdict-box" dir={lang === "ar" ? "rtl" : "ltr"} role="region" aria-label={t.verdictTag}>
      {!motionOff && r.tone !== "none" && CONF.map((col, i) => (
        <span key={i} className="conf" style={{ left: 60 + i * 105, background: col, animationDelay: `-${(i * 0.37) % 2}s` }} />
      ))}
      <span className="tag" style={{ background: charColor("Leo") }}>{t.verdictTag}</span>
      <div className={`verdict-word tone-${r.tone}`}>{lang === "ar" ? r.ar : r.en}{demo ? ` · ${t.demo}` : ""}</div>
      {reason && <div style={{ fontSize: 18, fontWeight: 600, marginTop: 2 }}>{reason}</div>}
      <div className="row" style={{ justifyContent: "center", marginTop: 10, gap: 14 }}>
        <span style={{ fontWeight: 800 }}>{t.conviction}:</span>
        <span className="meter" aria-hidden="true">{[1, 2, 3].map((i) => <span key={i} className={i <= c.level ? "on" : ""} />)}</span>
        <span style={{ fontWeight: 700 }}>{lang === "ar" ? c.ar : c.en}</span>
        <span style={{ fontWeight: 800 }}>· {t.priceAtVerdict}:</span>
        <span className="pixel ltr">{price ? fmtUsd(price, lang) : t.unavailable}</span>
      </div>
      <div className="row" style={{ justifyContent: "center", marginTop: 10 }}>
        <button className="primary green btn" style={{ height: 42, fontSize: 16 }} onClick={onOpenReport}>{t.openReport}</button>
        {extra}
        <span style={{ fontSize: 13, fontWeight: 700, color: "#7A6147" }}>{t.disclaimer}</span>
      </div>
    </div>
  );
}

export const leoName = (l: Lang) => charName("Leo" as CharKey, l);
