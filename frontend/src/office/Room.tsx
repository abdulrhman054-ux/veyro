import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { AnimatedSprite, SpriteSvg, charColor } from "../art/Sprite";
import { CHAR_INFO, charName, charRole, fmtNum, fmtPct, type CharKey, type Lang } from "../i18n";
import { usePrefs } from "../prefs";
import { speakBlips } from "../audio";
import type { History } from "../api";
import type { AgentState } from "./useSession";
import { faceFor, type Mood, type MoodInfo } from "./mood";
import { ALBIE_AT, BLOCKING, OFFICE, SCENE_LABEL, type SceneId } from "./scenes";
import { DONT_BUY, IDLE_QUIPS, POKED, REACTIONS, pick, quipFor, useParty } from "./fun";

// Seats read right-to-left in the analysis order: Ollie, Buzz, Pip, Benny on the front row,
// Leo at the head desk, the debaters and Tank in the back row.
export const SEATS = OFFICE;

/** What each character is busy with while thinking (shown in their thought bubble). */
const THINK: Record<CharKey, string> = { Ollie: "📈", Buzz: "💬", Pip: "📰", Benny: "🧮", Bolt: "🐂", Bruno: "🐻", Tank: "🛡️", Leo: "⚖️", Albie: "🌍" };
/** How a listener reacts while someone else speaks (the scene's supporting cast). */
const REACT_TO: Partial<Record<CharKey, Partial<Record<CharKey, string>>>> = {
  Bolt: { Bruno: "?!", Leo: "👀" },            // the bear's rebuttal when the bull talks
  Bruno: { Bolt: "!!", Leo: "👀" },            // the bull wants to jump in when the bear talks
  Tank: { Leo: "👍", Bolt: "…", Bruno: "…" },   // the risk talk: Leo approves, the debaters hold their breath
  Albie: { Leo: "!", Pip: "📰" },
  Leo: { Ollie: "👏", Buzz: "👏", Pip: "👏", Benny: "👏", Bolt: "🤞", Bruno: "🤞", Tank: "👏" },
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

function zoneTime(d: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone, hour: "numeric", minute: "numeric", hour12: false }).formatToParts(d);
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);
  return { h: get("hour") % 24, m: get("minute") };
}

/** Wall clock shows the market's own time (Riyadh for a Tadawul stock, else New York); the ring is green while
 *  that market is open, red when closed. */
function Clock({ marketOpen, lang, saudi = false, onTap }: { marketOpen: boolean | null; lang: Lang; saudi?: boolean; onTap?: () => void }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 20_000); return () => clearInterval(t); }, []);
  const { h, m } = zoneTime(now, saudi ? "Asia/Riyadh" : "America/New_York");
  const ring = marketOpen === true ? "#3CB371" : marketOpen === false ? "#D9573F" : "var(--trim)";
  const label = marketOpen === null ? (saudi ? "RUH" : "NY") : lang === "ar" ? (marketOpen ? "مفتوح" : "مقفل") : (marketOpen ? "OPEN" : "CLOSED");
  return (
    <>
      <div className={`clock${marketOpen ? " live" : ""}`} aria-hidden="true" style={{ borderColor: ring }} onClick={onTap}>
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

export function Agent({ name, state, lang, index, mood, reaction, pos, quip, quipKind }: { name: Exclude<CharKey, "Albie">; state: AgentState; lang: Lang; index: number; mood: Mood; reaction?: string | null; pos?: [number, number] | null;
  quip?: string | null; quipKind?: "warn" | "idle" | "party" }) {
  const offstage = pos === null;
  const [x, y] = pos ?? SEATS[name];
  // Walking to a new mark: show the walk for as long as the move takes.
  const [walking, setWalking] = useState(false);
  const prev = useRef<string>(`${x},${y}`);
  useEffect(() => {
    const key = `${x},${y}`;
    if (key === prev.current) return;
    prev.current = key;
    setWalking(true);
    const h = window.setTimeout(() => setWalking(false), 950);
    return () => clearTimeout(h);
  }, [x, y]);
  const [react, setReact] = useState<string | null>(null);
  const [poked, setPoked] = useState(false);
  const tm = useRef<number>(0);
  const taps = useRef<number[]>([]);
  const onClick = () => {
    if (state === "speaking") return;
    // Five taps on the same character within four seconds: they've had enough.
    const now = Date.now();
    taps.current = [...taps.current.filter((t) => now - t < 4000), now];
    const fed = taps.current.length >= 5;
    if (fed) taps.current = [];
    const said = fed ? POKED[name][lang] : pick(REACTIONS[name][lang]);
    setReact(said); setPoked(fed);
    speakBlips(name, said);
    window.clearTimeout(tm.current);
    tm.current = window.setTimeout(() => { setReact(null); setPoked(false); }, fed ? 3200 : 2200);
  };
  useEffect(() => () => window.clearTimeout(tm.current), []);
  const face = faceFor(name, mood);
  const cls = ["agent", `c-${name}`, state, react ? "react" : "", face ? `face-${face}` : "", reaction && !react && state !== "speaking" ? "listening" : "",
    walking ? "walking" : "", offstage ? "offstage" : "", poked ? "poked" : ""].join(" ");
  const emote = state === "thinking" ? THINK[name] : CHAR_INFO[name].emote;
  const onBreak = state === "break";
  return (
    <div className={cls} style={{ left: x, top: y }} aria-hidden={offstage || undefined}>
      <button className="hit" onClick={onClick} aria-label={`${charName(name, lang)}, ${charRole(name, lang)}`} tabIndex={offstage ? -1 : undefined} />
      <div className="sprite" style={{ animationDelay: `-${(index * 0.37).toFixed(2)}s` }}>
        <div className="motion" style={{ animationDelay: `-${(index * 0.71).toFixed(2)}s` }}><AnimatedSprite name={name} /></div>
      </div>
      <div className="emote pixel" style={{ color: charColor(name) }}>{emote}</div>
      {reaction && state !== "speaking" && state !== "break" && <div className="reactmark pixel" aria-hidden="true">{reaction}</div>}
      {face === "worry" && <div className="sweat" aria-hidden="true" style={{ animationDelay: `-${(index * 0.53).toFixed(2)}s` }} />}
      {face === "happy" && <div className="spark pixel" aria-hidden="true" style={{ animationDelay: `-${(index * 0.61).toFixed(2)}s` }}>♪</div>}
      {!react && quip && !offstage && (
        <div className={`quip${quipKind ? ` quip-${quipKind}` : ""}`} role="status" dir={lang === "ar" ? "rtl" : "ltr"} data-quip={quipKind}>{quip}</div>
      )}
      {react && (
        <div role="status" data-react={poked ? "poked" : "tap"} style={{ position: "absolute", top: -58, left: "50%", transform: "translateX(-50%)", background: "#FFFFFF", color: "#5C4331", borderRadius: 16, padding: "6px 12px", fontSize: 14, fontWeight: 700, whiteSpace: "nowrap", boxShadow: "0 4px 0 #E3D5B8", zIndex: 9, direction: lang === "ar" ? "rtl" : "ltr" }}>{react}</div>
      )}
      <div className={`desk${name === "Leo" ? " gold" : ""}`}><div className="mug"><i /><i /></div><div className="lap"><b /></div><div className="note">{CHECK}</div></div>
      <div className="plate" style={{ background: charColor(name) }}>{charName(name, lang)}</div>
      <div className="rl">{onBreak ? (lang === "ar" ? "في استراحة قهوة" : "On a coffee break") : charRole(name, lang)}</div>
      {onBreak && <div className="zzz pixel" aria-hidden="true">z<span>z</span><b>z</b></div>}
    </div>
  );
}

const ORDER: Exclude<CharKey, "Albie">[] = ["Ollie", "Buzz", "Pip", "Benny", "Bolt", "Bruno", "Tank", "Leo"];

export function RoomScene({ ticker, market, marketLoaded, demo, agents, lang, children, starting, mood, marketOpen, scene = "office", heat = 0, verdictTone, speakTone, warn = false }: {
  ticker: string | null; market: History | null; marketLoaded: boolean; demo: boolean;
  agents: Record<CharKey, AgentState>; lang: Lang; children?: ReactNode; starting?: string | null;
  mood: MoodInfo; marketOpen: boolean | null; scene?: SceneId; heat?: number; verdictTone?: string | null; speakTone?: string | null;
  /** the line being spoken is a clear risk warning */
  warn?: boolean;
}) {
  // Bruno pops into the risk room to back up a clear warning, and says it again at a sell call.
  const bruno = (scene === "risk" && warn) || (scene === "decision" && verdictTone === "sell");
  const blocking = scene === "risk" && warn ? { ...BLOCKING.risk, Bruno: [110, 300] as [number, number] } : BLOCKING[scene];
  const { party, partyKey, tapClock } = useParty();
  const { motionOff, prefs } = usePrefs();
  const intensity = prefs.intensity;
  // A scene card each time the set changes (not on the first, quiet office).
  const [card, setCard] = useState<{ id: SceneId; k: number } | null>(null);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; if (scene === "office") return; }
    setCard((c) => ({ id: scene, k: (c?.k ?? 0) + 1 }));
    const h = window.setTimeout(() => setCard(null), 2900);
    return () => clearTimeout(h);
  }, [scene]);
  const order = ORDER;
  const albie = agents.Albie;
  const speaker = (Object.keys(agents) as CharKey[]).find((c) => agents[c] === "speaking") ?? null;
  const spot = speaker && speaker !== "Albie" ? blocking[speaker] ?? SEATS[speaker] : speaker === "Albie" ? ALBIE_AT[scene] : null;
  const idle = order.every((c) => agents[c] === "idle" || agents[c] === "break") && albie !== "speaking" && albie !== "thinking";
  const ambient = useAmbient(idle, order);
  // Now and then the idle office chats (one in three ambient moments), chosen once per moment.
  const [idleQuip, setIdleQuip] = useState<string | null>(null);
  useEffect(() => { setIdleQuip(ambient && Math.random() < 0.34 ? quipFor(ambient, lang, IDLE_QUIPS) : null); }, [ambient, lang]);
  const quipOf = (n: CharKey): { text: string; kind: "warn" | "idle" | "party" } | null =>
    n === "Bruno" && bruno ? { text: DONT_BUY[lang], kind: "warn" }
    : party && n === "Leo" ? { text: lang === "ar" ? "حفلة فيرو! الكل يرقص 🎉" : "Veyro party! Everybody dance 🎉", kind: "party" }
    : idle && ambient === n && idleQuip ? { text: idleQuip, kind: "idle" } : null;
  const heatLevel = scene === "debate" ? Math.min(3, heat) : 0;
  const cls = ["room", `mood-${mood.mood}`, `scene-${scene}`, speaker ? `has-speaker speaker-${speaker}` : "", speaker && speakTone ? `tone-${speakTone}` : "",
    heatLevel ? `heat-${heatLevel}` : "", verdictTone ? `verdict-${verdictTone}` : "", party ? "party" : ""].join(" ");
  return (
    <div className={cls}>
      {/* The camera: pushes in slowly on whoever is speaking, like a film cut to a close-up. */}
      <div className="cam" style={spot && !motionOff ? { transform: `scale(${intensity === "lively" ? 1.08 : 1.05})`,
        transformOrigin: `${spot[0] + 75}px ${spot[1] + 90}px` } : undefined}>
      <div className="wall" />
      <SceneSet scene={scene} lang={lang} heat={heatLevel} />
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
      <Clock marketOpen={marketOpen} lang={lang} saudi={!!ticker && ticker.toUpperCase().endsWith(".SR")} onTap={tapClock} />
      <Whiteboard ticker={ticker} market={market} loaded={marketLoaded} demo={demo} lang={lang} mood={mood} />
      <div className="plant" style={{ left: 12, top: 470 }}>{PLANT("#4E9E62", "#D9774E")}</div>
      <div className="plant" style={{ left: 928, top: 470, animationDelay: "-1.2s" }}>{PLANT("#6CC38E", "#E8A04A")}</div>
      <div className="plane" aria-hidden="true">
        <svg width="46" height="26" viewBox="0 0 23 13" shapeRendering="crispEdges"><path d="M0 6h1V5h4V4h4V3h4V2h4V1h4V0h2v1h-1v2h-1v2h-1v2h-1v2h-1v2h-1v2h-1v-1h-1v-1h-1v-1h-1V9h-1v1h-1v1H9V9H8V8H1V7H0z" fill="#FFFFFF" stroke="#9AA7B8" strokeWidth=".3" /></svg>
      </div>
      {spot && <div className="spotlight" aria-hidden="true" style={{ left: spot[0] + 75, top: spot[1] + 70 }} />}
      {scene === "debate" && <div className="versus pixel" aria-hidden="true">VS</div>}
      {party && <div className="disco" key={`d-${partyKey}`} aria-hidden="true"><i className="ball" />{[0, 1, 2, 3, 4, 5].map((k) => <b key={k} className={`beam b${k}`} />)}</div>}
      {order.map((n, i) => <Agent key={n} name={n} state={agents[n]} lang={lang} index={i} mood={mood.mood} pos={blocking[n]}
        quip={quipOf(n)?.text} quipKind={quipOf(n)?.kind}
        reaction={speaker ? REACT_TO[speaker]?.[n] ?? (scene === "debate" && heatLevel >= 2 && (n === "Bolt" || n === "Bruno") ? "💢" : null)
          : ambient === n ? CHAR_INFO[n].emote : null} />)}
      {/* Albie only lands when it's his scene (the server may already be preparing him while the debate still plays). */}
      {(albie === "speaking" || ((albie === "thinking" || albie === "done") && (scene === "world" || scene === "decision" || scene === "office"))) && (
        <div className={`visitor ${albie === "done" ? "leaving" : albie}`} aria-hidden={albie === "done" || undefined}
          style={{ left: ALBIE_AT[scene][0], top: ALBIE_AT[scene][1] }} aria-label={lang === "ar" ? "ألبي، ناقل الأخبار العالمية" : "Albie, world news courier"} role="img">
          <div className="sprite"><AnimatedSprite name="Albie" px={4} /></div>
          <div className="plate" style={{ background: charColor("Albie"), top: 110 }}>{charName("Albie", lang)}</div>
          {albie === "thinking" && <div className="emote pixel" style={{ display: "flex", color: charColor("Albie") }}>✈</div>}
        </div>
      )}
      </div>
      <div className="mood-tint" aria-hidden="true" />
      {/* Film grammar: letterbox bars and an iris wipe whenever the set changes, bars stay for the verdict. */}
      <div className={`letterbox${card || scene === "decision" ? " on" : ""}`} aria-hidden="true"><i /><i /></div>
      {card && <div className="iris" key={`iris-${card.k}`} aria-hidden="true" />}
      {starting && <><div className="lights" key={`l-${starting}`} /><div className="banner pixel" key={`b-${starting}`}>{starting}</div></>}
      {party && <div className="banner pixel party-banner" key={`pb-${partyKey}`} role="status">{lang === "ar" ? "🕺 وضع الحفلة! 🎉" : "🕺 PARTY MODE! 🎉"}</div>}
      {card && <div className="scene-card" key={`p-${card.id}-${card.k}`} dir={lang === "ar" ? "rtl" : "ltr"} role="status">
        <b className="pixel">{SCENE_LABEL[card.id].n}</b><span>{SCENE_LABEL[card.id][lang]}</span></div>}
      {children}
    </div>
  );
}

/** Between sessions the office isn't frozen: every few seconds someone idles in character. */
function useAmbient(on: boolean, cast: CharKey[]) {
  const { motionOff } = usePrefs();
  const [who, setWho] = useState<CharKey | null>(null);
  useEffect(() => {
    if (!on || motionOff) { setWho(null); return; }
    let t2 = 0;
    const h = window.setInterval(() => {
      setWho(cast[Math.floor(Math.random() * cast.length)]);
      t2 = window.setTimeout(() => setWho(null), 1800);
    }, 5200);
    return () => { clearInterval(h); clearTimeout(t2); };
  }, [on, motionOff, cast]);
  return who;
}

/** The set for each scene: backdrops and props drawn in the same chunky pixel style. */
function SceneSet({ scene, lang, heat }: { scene: SceneId; lang: Lang; heat: number }) {
  const ar = lang === "ar";
  if (scene === "office") return null;
  return (
    <div className={`set set-${scene}`} aria-hidden="true">
      {scene === "debate" && <>
        <div className="curtain l" /><div className="curtain r" />
        <div className="stage-floor" />
        <div className="podium" style={{ left: 205 }}><i>{ar ? "برونو" : "BRUNO"}</i></div>
        <div className="podium bull" style={{ left: 655 }}><i>{ar ? "بولت" : "BOLT"}</i></div>
        <div className="sign pixel">{ar ? "مناظرة" : "DEBATE"}</div>
        <div className="heat" dir="ltr"><span>{ar ? "حرارة النقاش" : "HEAT"}</span>{[1, 2, 3].map((i) => <b key={i} className={i <= heat ? "on" : ""} />)}</div>
        {heat >= 2 && <div className="heat-note" dir={ar ? "rtl" : "ltr"}>{ar ? "🔥 احتدم النقاش! الباقين طلعوا وخلّوهم يتناقشون" : "🔥 It's heating up! Everyone else left the two of them to it"}</div>}
      </>}
      {scene === "plan" && <>
        <div className="panel-wall" />
        <div className="bigdesk"><i /><i /></div>
        <div className="flipchart pixel"><b>{ar ? "الخطة" : "PLAN"}</b><i /><i /><i /></div>
        <div className="frame-pic" />
      </>}
      {scene === "risk" && <>
        <div className="control-wall" />
        <div className="lamps">
          <span className="lamp red"><b /> {ar ? "جريء" : "Aggressive"}</span>
          <span className="lamp amber"><b /> {ar ? "محايد" : "Neutral"}</span>
          <span className="lamp green"><b /> {ar ? "حذر" : "Conservative"}</span>
        </div>
        <div className="shield pixel">🛡️</div>
        <div className="console" />
      </>}
      {scene === "world" && <>
        <div className="sky" /><div className="worldmap" />
        <div className="cloud c1" /><div className="cloud c2" /><div className="cloud c3" />
        <div className="papers"><i /><i /><i /></div>
        <div className="sign pixel">{ar ? "أخبار العالم" : "WORLD NEWS"}</div>
      </>}
      {scene === "charts" && <>
        <div className="chartwall">{[38, 52, 30, 64, 48, 72, 58, 84, 66, 90].map((h, i) => <i key={i} className={i % 3 === 1 ? "dn" : ""} style={{ height: h, animationDelay: `${i * 0.12}s` }} />)}</div>
        <div className="branch" /><div className="sign pixel">{ar ? "التحليل الفني" : "TECHNICALS"}</div>
        <div className="glasses pixel">🔍</div>
      </>}
      {scene === "social" && <>
        <div className="hive" />
        {["👍", "🔥", "💬", "👎", "❤️", "🤔", "📣", "💬"].map((e, i) => <span key={i} className="bubble" style={{ left: 90 + (i % 4) * 230, top: 60 + Math.floor(i / 4) * 150, animationDelay: `${i * 0.35}s` }}>{e}</span>)}
        <div className="sign pixel">{ar ? "وش يقول الناس؟" : "WHAT'S THE BUZZ?"}</div>
      </>}
      {scene === "newsdesk" && <>
        <div className="studio" /><div className="anchordesk"><b>{ar ? "أخبار السهم" : "STOCK NEWS"}</b></div>
        <div className="onair pixel">{ar ? "● على الهواء" : "● ON AIR"}</div>
        <div className="ticker-tape" dir="ltr"><span>{ar ? "عاجل عاجل · بيب يقرأ أخبار الشركة والقطاع · عاجل عاجل · " : "BREAKING · Pip reads the company and sector news · BREAKING · "}</span></div>
      </>}
      {scene === "ledger" && <>
        <div className="ledgerwall" /><div className="ledgerdesk"><i /><i /><i /></div>
        <div className="coins">{[0, 1, 2, 3, 4].map((i) => <i key={i} style={{ animationDelay: `${i * 0.2}s` }} />)}</div>
        <div className="calc pixel">🧮</div><div className="sign pixel">{ar ? "القوائم المالية" : "THE BOOKS"}</div>
      </>}
      {scene === "decision" && <>
        <div className="boardtable"><i /><i /><i /><i /><i /></div>
        <div className="gavel pixel">⚖️</div>
      </>}
    </div>
  );
}
