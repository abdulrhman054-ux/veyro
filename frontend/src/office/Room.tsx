import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { AnimatedSprite, SpriteSvg, charColor } from "../art/Sprite";
import { CHAR_INFO, charName, charRole, fmtNum, fmtPct, type CharKey, type Lang } from "../i18n";
import { usePrefs } from "../prefs";
import { speakBlips } from "../audio";
import type { History } from "../api";
import type { AgentState } from "./useSession";
import { faceFor, type Mood, type MoodInfo } from "./mood";

// Seats read right-to-left in the analysis order: Ollie, Buzz, Pip, Benny on the front row,
// Leo at the head desk, the debaters and Tank in the back row.
export const SEATS: Record<Exclude<CharKey, "Albie">, [number, number]> = {
  Ollie: [825, 160], Buzz: [635, 160], Leo: [425, 160], Pip: [215, 160], Benny: [25, 160],
  Bolt: [720, 342], Bruno: [425, 342], Tank: [130, 342],
};

const REACTIONS: Record<CharKey, { ar: string[]; en: string[] }> = {
  Albie: { ar: ["يا جماعة عندي لكم لفّة على العالم!", "من فوق الغيوم شفت أخبار كثيرة!"], en: ["Fresh off the jet stream!", "I saw so much news from above the clouds!"] },
  Ollie: { ar: ["هوو؟ أنا أراقب الشارت!", "نظارتي نظيفة اليوم، هوو هوو!"], en: ["Hoo? I'm watching the chart!", "Freshly polished glasses, hoot!"] },
  Pip: { ar: ["عندك خبر؟ قلّي قلّي!", "سكوااك! لا تشدّ ريشي!"], en: ["Got news? Tell me tell me!", "Squawk! Mind the feathers!"] },
  Buzz: { ar: ["بززز! الكل يسولف اليوم!", "ودّك نرقص رقصة النحل؟"], en: ["Bzzz! Everyone's chatting today!", "Want to see my waggle dance?"] },
  Benny: { ar: ["لحظة… أحسب الأرقام، قرمش!", "القهوة والجداول، أحلى صباح!"], en: ["One sec… crunching numbers, chomp!", "Coffee and spreadsheets, perfect morning!"] },
  Bolt: { ar: ["مووو! متحمس للجلسة!", "كل نزول فرصة، صح؟"], en: ["Moo-ve! Ready to go!", "Every dip's a chance, right?"] },
  Bruno: { ar: ["غرر… خلني أركّز.", "أنا بس حذر، مو زعلان!"], en: ["Grr… let me focus.", "I'm careful, not grumpy!"] },
  Tank: { ar: ["على مهلك… بثبات.", "الخوذة للسلامة، طبعاً!"], en: ["Slow and steady.", "Hard hat for safety, of course!"] },
  Leo: { ar: ["أهلاً بك في المجلس! زئير!", "القرار يحتاج صبر، وأنا صبور."], en: ["Welcome to the council! Roar!", "Good calls need patience. I have plenty."] },
};

const PLANT = (leaf: string, pot: string) => (
  <svg width="60" height="90" viewBox="0 0 12 18" shapeRendering="crispEdges" aria-hidden="true">
    <path d="M5 0h2v2h2v2h2v4H9v2H7v1H5v-1H3V8H1V4h2V2h2z" fill={leaf} /><path d="M3 11h6v2H8v5H4v-5H3z" fill={pot} />
  </svg>
);
const CHECK = (
  <svg width="18" height="18" viewBox="0 0 9 9" shapeRendering="crispEdges" aria-hidden="true">
    <path fill="#27A05E" d="M7 1h2v2H8v1H7v1H6v1H5v1H4v1H3V7H2V6H1V5H0V4h2v1h1v1h1V5h1V4h1V3h1z" />
  </svg>
);
const STARS = [[14, 12, 0.3], [48, 40, 1.1], [92, 20, 0.7], [120, 58, 1.9], [30, 66, 1.4]];

export function Stage({ children }: { children: ReactNode }) {
  const outer = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const el = outer.current; if (!el) return;
    const ro = new ResizeObserver(() => setScale(Math.min(1.25, el.clientWidth / 1000)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div className="stage" ref={outer} style={{ height: 740 * scale }}>
      <div className="stage-inner" style={{ transform: `scale(${scale})` }}>{children}</div>
    </div>
  );
}

function nyTime(d: Date) {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "numeric", hour12: false }).formatToParts(d);
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);
  return { h: get("hour") % 24, m: get("minute") };
}

/** Wall clock shows New York market time; the ring is green while the market is open, red when closed. */
function Clock({ marketOpen, lang }: { marketOpen: boolean | null; lang: Lang }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 20_000); return () => clearInterval(t); }, []);
  const { h, m } = nyTime(now);
  const ring = marketOpen === true ? "#3CB371" : marketOpen === false ? "#D9573F" : "var(--trim)";
  const label = marketOpen === null ? "NY" : lang === "ar" ? (marketOpen ? "مفتوح" : "مقفل") : (marketOpen ? "OPEN" : "CLOSED");
  return (
    <>
      <div className={`clock${marketOpen ? " live" : ""}`} aria-hidden="true" style={{ borderColor: ring }}>
        <i style={{ transform: `rotate(${(h % 12) * 30 + m / 2}deg)` }} /><b style={{ transform: `rotate(${m * 6}deg)` }} />
      </div>
      <div className="clock-tag" aria-hidden="true" style={{ background: ring }}>{label}</div>
    </>
  );
}

function Whiteboard({ ticker, market, loaded, demo, lang, mood }: { ticker: string | null; market: History | null; loaded: boolean; demo: boolean; lang: Lang; mood: MoodInfo }) {
  const { t } = usePrefs();
  let chart: ReactNode = null;
  if (market?.closes && market.closes.length > 1) {
    const cs = market.closes.slice(-60);
    const lo = Math.min(...cs), hi = Math.max(...cs);
    const pts = cs.map((c, i) => `${(10 + (i / (cs.length - 1)) * 304).toFixed(1)},${(92 - ((c - lo) / (hi - lo || 1)) * 62).toFixed(1)}`).join(" ");
    const up = cs[cs.length - 1] >= cs[0];
    chart = (
      <>
        <svg width="324" height="106" viewBox="0 0 324 106" aria-hidden="true" style={{ position: "absolute", left: 0, top: 0 }}>
          <polyline key={market.ticker + String(cs.length)} className="ln" points={pts} fill="none" stroke={up ? "#2F9A62" : "#D9573F"} strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />
        </svg>
        <div className="pixel ltr" style={{ position: "absolute", bottom: 2, left: 10, fontSize: 11, color: "#7A6147" }}>
          {fmtNum(cs[cs.length - 1], "en", { maximumFractionDigits: 2 })} · {market.dates?.[market.dates.length - 1]} · Yahoo
        </div>
      </>
    );
  } else if (loaded && ticker) {
    chart = <div style={{ position: "absolute", inset: "34px 10px 10px", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 15, color: "#8C5A2B" }} dir={lang === "ar" ? "rtl" : "ltr"}>{t.chartUnavailable}</div>;
  }
  const shown = ticker ?? mood.ticker;
  const ch = mood.change;
  return (
    <div className="wb" role="img" aria-label={shown ? `${shown} ${fmtPct(ch, lang) ?? ""}` : "whiteboard"}>
      <div className="pixel" style={{ position: "absolute", top: 2, left: 10, fontSize: 17, fontWeight: 700 }}>{shown ?? "VEYRO"}</div>
      {ch != null && (
        <div className={`wb-move pixel ${ch >= 0 ? "up" : "down"}`}>{ch >= 0 ? "▲" : "▼"} <span className="ltr">{fmtPct(ch, "en")}</span></div>
      )}
      {demo && <div className="pixel wb-demo">DEMO</div>}
      {!ticker && !market && (
        <svg width="324" height="106" viewBox="0 0 324 106" aria-hidden="true" style={{ position: "absolute", left: 0, top: 0 }}>
          <path d="M14 84 L60 66 L96 74 L140 46 L180 54 L220 28 L262 36 L306 16" fill="none" stroke="#C9D1DC" strokeWidth="4" strokeDasharray="6 8" />
        </svg>
      )}
      {chart}
    </div>
  );
}

export function Agent({ name, state, lang, index, mood }: { name: Exclude<CharKey, "Albie">; state: AgentState; lang: Lang; index: number; mood: Mood }) {
  const [x, y] = SEATS[name];
  const [react, setReact] = useState<string | null>(null);
  const tm = useRef<number>(0);
  const onClick = () => {
    if (state === "speaking") return;
    const pool = REACTIONS[name][lang];
    const said = pool[Math.floor(Math.random() * pool.length)];
    setReact(said);
    speakBlips(name, said);
    window.clearTimeout(tm.current);
    tm.current = window.setTimeout(() => setReact(null), 2200);
  };
  useEffect(() => () => window.clearTimeout(tm.current), []);
  const face = faceFor(name, mood);
  const cls = ["agent", state, react ? "react" : "", face ? `face-${face}` : ""].join(" ");
  const emote = state === "thinking" ? "…" : CHAR_INFO[name].emote;
  const onBreak = state === "break";
  return (
    <div className={cls} style={{ left: x, top: y }}>
      <button className="hit" onClick={onClick} aria-label={`${charName(name, lang)}, ${charRole(name, lang)}`} />
      <div className="sprite" style={{ animationDelay: `-${(index * 0.37).toFixed(2)}s` }}><AnimatedSprite name={name} /></div>
      <div className="emote pixel" style={{ color: charColor(name) }}>{emote}</div>
      {face === "worry" && <div className="sweat" aria-hidden="true" style={{ animationDelay: `-${(index * 0.53).toFixed(2)}s` }} />}
      {face === "happy" && <div className="spark pixel" aria-hidden="true" style={{ animationDelay: `-${(index * 0.61).toFixed(2)}s` }}>♪</div>}
      {react && (
        <div role="status" style={{ position: "absolute", top: -58, left: "50%", transform: "translateX(-50%)", background: "#FFFFFF", color: "#5C4331", borderRadius: 16, padding: "6px 12px", fontSize: 14, fontWeight: 700, whiteSpace: "nowrap", boxShadow: "0 4px 0 #E3D5B8", zIndex: 9, direction: lang === "ar" ? "rtl" : "ltr" }}>{react}</div>
      )}
      <div className={`desk${name === "Leo" ? " gold" : ""}`}><div className="mug"><i /><i /></div><div className="lap"><b /></div><div className="note">{CHECK}</div></div>
      <div className="plate" style={{ background: charColor(name) }}>{charName(name, lang)}</div>
      <div className="rl">{onBreak ? (lang === "ar" ? "في استراحة قهوة" : "On a coffee break") : charRole(name, lang)}</div>
      {onBreak && <div className="zzz pixel" aria-hidden="true">z<span>z</span><b>z</b></div>}
    </div>
  );
}

export function RoomScene({ ticker, market, marketLoaded, demo, agents, lang, children, starting, mood, marketOpen }: {
  ticker: string | null; market: History | null; marketLoaded: boolean; demo: boolean;
  agents: Record<CharKey, AgentState>; lang: Lang; children?: ReactNode; starting?: string | null;
  mood: MoodInfo; marketOpen: boolean | null;
}) {
  const order: Exclude<CharKey, "Albie">[] = ["Ollie", "Buzz", "Pip", "Benny", "Bolt", "Bruno", "Tank", "Leo"];
  const albie = agents.Albie;
  return (
    <div className={`room mood-${mood.mood}`}>
      <div className="wall" />
      <div className="window" style={{ left: 50 }}>
        <div className="sun" /><div className="moon" />
        <div className="winfly" aria-hidden="true"><SpriteSvg name="Albie" px={2} frame="wave" /><i className="paper" /></div>

        {STARS.map(([sx, sy, d], i) => <div key={i} className="st" style={{ left: sx, top: sy, animationDelay: `-${d}s` }} />)}
        <div className="c" style={{ top: 26, width: 30 }} /><div className="c" style={{ top: 62, width: 24, animationDelay: "-7s" }} />
        {mood.mood === "slump" && <div className="rain" />}
      </div>
      <div className="window" style={{ left: 780 }}>
        <div className="winfly second" aria-hidden="true"><SpriteSvg name="Albie" px={2} frame="wave" /><i className="paper" /></div>
        {STARS.map(([sx, sy, d], i) => <div key={i} className="st" style={{ left: sx, top: sy, animationDelay: `-${d + 0.5}s` }} />)}
        <div className="c" style={{ top: 40, width: 28, animationDelay: "-3s" }} /><div className="c" style={{ top: 70, width: 22, animationDelay: "-10s" }} />
        {mood.mood === "slump" && <div className="rain" />}
      </div>
      <Clock marketOpen={marketOpen} lang={lang} />
      <Whiteboard ticker={ticker} market={market} loaded={marketLoaded} demo={demo} lang={lang} mood={mood} />
      <div className="plant" style={{ left: 12, top: 470 }}>{PLANT("#4E9E62", "#D9774E")}</div>
      <div className="plant" style={{ left: 928, top: 470, animationDelay: "-1.2s" }}>{PLANT("#6CC38E", "#E8A04A")}</div>
      <div className="plane" aria-hidden="true">
        <svg width="46" height="26" viewBox="0 0 23 13" shapeRendering="crispEdges"><path d="M0 6h1V5h4V4h4V3h4V2h4V1h4V0h2v1h-1v2h-1v2h-1v2h-1v2h-1v2h-1v2h-1v-1h-1v-1h-1v-1h-1V9h-1v1h-1v1H9V9H8V8H1V7H0z" fill="#FFFFFF" stroke="#9AA7B8" strokeWidth=".3" /></svg>
      </div>
      {order.map((n, i) => <Agent key={n} name={n} state={agents[n]} lang={lang} index={i} mood={mood.mood} />)}
      {(albie === "thinking" || albie === "speaking") && (
        <div className={`visitor ${albie}`} aria-label={lang === "ar" ? "ألبي، ناقل الأخبار العالمية" : "Albie, world news courier"} role="img">
          <div className="sprite"><AnimatedSprite name="Albie" px={4} /></div>
          <div className="plate" style={{ background: charColor("Albie"), top: 110 }}>{charName("Albie", lang)}</div>
          {albie === "thinking" && <div className="emote pixel" style={{ display: "flex", color: charColor("Albie") }}>✈</div>}
        </div>
      )}
      <div className="mood-tint" aria-hidden="true" />
      {starting && <><div className="lights" key={`l-${starting}`} /><div className="banner pixel" key={`b-${starting}`}>{starting}</div></>}
      {children}
    </div>
  );
}
