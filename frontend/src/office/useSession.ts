import { useCallback, useEffect, useReducer, useRef } from "react";
import { openStream, type Estimate, type History, type Usage, type VEvent, type Verdict } from "../api";
import type { CharKey } from "../i18n";

export type AgentState = "idle" | "thinking" | "speaking" | "done" | "break";
export type Line = { id: string; character: CharKey; node: string; text: string; texts: Partial<Record<"ar" | "en", string>>; turnId?: number; kind: "speech" | "error" | "verdict"; demo: boolean };

export type SessionState = {
  id: string | null;
  ticker: string | null;
  mode: "real" | "demo" | null;
  tradeDate: string | null;
  estimate: Estimate | null;
  market: History | null;
  marketLoaded: boolean;
  agents: Record<CharKey, AgentState>;
  queue: Line[];
  current: Line | null;
  log: Line[];
  verdict: Verdict | null;
  verdictShown: boolean;
  usage: Usage | null;
  ended: boolean;
  status: string | null;
  error: { code: string; character: CharKey; text: string } | null;
  rethinking: CharKey[];   // started a new task while still speaking / queued
  assetType: string | null;
  portfolioUsed: boolean;
  portfolioBroker: string | null;
  stopping: boolean;          // Stop pressed: waiting for the backend's confirmation
  thinkingSince: number | null;  // when the current "someone is working" stretch began (for the waiting box)
  lastNode: string | null;       // the framework step most recently started (drives the stage when nobody speaks)
  debateLines: number;           // bull/bear lines played so far: the debate heats up with each exchange
};

const ALL: CharKey[] = ["Ollie", "Pip", "Buzz", "Benny", "Bolt", "Bruno", "Tank", "Leo", "Albie"];
const idleAgents = () => Object.fromEntries(ALL.map((c) => [c, "idle"])) as Record<CharKey, AgentState>;

export const initial: SessionState = {
  id: null, ticker: null, mode: null, tradeDate: null, estimate: null, market: null, marketLoaded: false,
  agents: idleAgents(), queue: [], current: null, log: [], verdict: null, verdictShown: false,
  usage: null, ended: false, status: null, error: null, rethinking: [], assetType: null, portfolioUsed: false,
  portfolioBroker: null, stopping: false, thinkingSince: null, lastNode: null, debateLines: 0,
};

type Action =
  | { type: "reset"; id: string | null }
  | { type: "event"; ev: VEvent }
  | { type: "next" }          // current line finished playing
  | { type: "showVerdict" }
  | { type: "streamClosed"; status?: string }
  | { type: "stop" }
  | { type: "say"; character: CharKey; text: string };

let lineSeq = 0;

function reducer(s: SessionState, a: Action): SessionState {
  switch (a.type) {
    case "reset":
      return { ...initial, id: a.id, agents: idleAgents() };
    case "streamClosed":
      return s.ended ? s : { ...s, ended: true, status: a.status ?? s.status ?? "disconnected",
        agents: settle(s.agents), stopping: false };
    case "stop": {
      // Stop means stop now: drop the lines still waiting to be played and put everyone back at their desk.
      // Already finished on the server (lines still playing, or a replayed result): just stop the playback.
      if (s.ended) return { ...s, queue: [], current: null, rethinking: [], agents: settle(s.agents), thinkingSince: null,
        verdictShown: !!s.verdict };
      return { ...s, stopping: true, queue: [], current: null, rethinking: [], agents: settle(s.agents), thinkingSince: null };
    }
    case "showVerdict":
      return { ...s, verdictShown: true };
    case "say": {
      const line: Line = { id: `l${++lineSeq}`, character: a.character, node: "Ask", text: a.text, texts: { ar: a.text, en: a.text }, kind: "speech", demo: false };
      return enqueue({ ...s, verdictShown: false }, line);
    }
    case "next": {
      if (!s.current) return s;
      const done = s.current;
      const agents = { ...s.agents };
      let rethinking = s.rethinking;
      if (done.kind !== "error") {
        const again = rethinking.includes(done.character) || s.queue.some((l) => l.character === done.character);
        agents[done.character] = again ? "thinking" : "done";
        rethinking = rethinking.filter((c) => c !== done.character);
      }
      const log = done.kind === "speech" || done.kind === "verdict" ? [done, ...s.log] : s.log;
      const [head, ...rest] = s.queue;
      if (head && head.kind !== "error") agents[head.character] = "speaking";
      const debateLines = s.debateLines + (done.node === "Bull Researcher" || done.node === "Bear Researcher" ? 1 : 0);
      return { ...s, agents, log, rethinking, current: head ?? null, queue: rest, debateLines };
    }
    case "event": {
      const ev = a.ev;
      switch (ev.type) {
        case "session": {
          const agents = { ...s.agents };
          (ev.on_break ?? []).forEach((c) => { agents[c as CharKey] = "break"; });
          return { ...s, agents, id: ev.id, ticker: ev.ticker, mode: ev.mode, tradeDate: ev.trade_date, estimate: ev.estimate,
            assetType: ev.asset_type ?? null, portfolioUsed: !!ev.portfolio_used, portfolioBroker: ev.portfolio_broker ?? null };
        }
        case "team": {
          const agents = { ...s.agents };
          ev.on_break.forEach((c) => { agents[c as CharKey] = "break"; });
          return { ...s, agents, assetType: ev.asset_type };
        }
        case "market":
          return { ...s, market: ev.data, marketLoaded: true };
        case "agent_started": {
          if (s.stopping) return s;
          const c = ev.character as CharKey;
          const since = s.thinkingSince ?? Date.now();
          s = { ...s, lastNode: ev.node };
          if (s.current?.character === c || s.queue.some((l) => l.character === c))
            return { ...s, rethinking: [...s.rethinking, c], thinkingSince: since };
          return { ...s, agents: { ...s.agents, [c]: "thinking" }, thinkingSince: since };
        }
        case "agent_message": {
          if (s.stopping) return s;
          const line: Line = { id: `l${++lineSeq}`, character: ev.character as CharKey, node: ev.node, text: ev.text, turnId: ev.turn_id,
            texts: ev.texts ?? { [ev.lang as "ar" | "en"]: ev.text }, demo: s.mode === "demo",
            kind: ev.node === "Portfolio Manager" ? "verdict" : "speech" };
          return enqueue({ ...s, thinkingSince: null }, line);
        }
        case "agent_done":
          return s;
        case "verdict":
          return { ...s, verdict: ev };
        case "usage":
          return { ...s, usage: ev.data };
        case "error": {
          const c = ev.character as CharKey;
          const line: Line = { id: `l${++lineSeq}`, character: c, node: "error", text: ev.text, texts: ev.texts ?? {}, kind: "error", demo: s.mode === "demo" };
          if (!ev.character) return s;   // transport-level error with nobody to voice it (handled by the stream)
          return enqueue({ ...s, agents: settle(s.agents), queue: s.stopping ? [] : s.queue, thinkingSince: null,
            error: { code: ev.code, character: c, text: ev.text } }, line);
        }
        case "end":
          return { ...s, ended: true, status: ev.status, stopping: false, thinkingSince: null,
            agents: ev.status === "done" ? s.agents : settle(s.agents) };
        default:
          return s;
      }
    }
  }
}

/** Anyone mid-task goes back to idle (coffee-break and finished characters keep their state). */
function settle(a: Record<CharKey, AgentState>): Record<CharKey, AgentState> {
  const out = { ...a };
  ALL.forEach((k) => { if (out[k] === "thinking" || out[k] === "speaking") out[k] = "idle"; });
  return out;
}

function enqueue(s: SessionState, line: Line): SessionState {
  if (!s.current) {
    const agents = { ...s.agents };
    if (line.kind !== "error") agents[line.character] = "speaking";
    return { ...s, current: line, agents };
  }
  return { ...s, queue: [...s.queue, line] };
}

export function useSession(sessionId: string | null) {
  const [state, dispatch] = useReducer(reducer, initial);
  const closeRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    closeRef.current?.();
    dispatch({ type: "reset", id: sessionId });
    if (!sessionId) return;
    // The server replays the whole session to every new connection, so after a dropped connection we
    // reconnect and skip the events we already have: nothing is lost and nothing plays twice.
    let seen = 0, tries = 0, alive = true, ended = false, timer = 0;
    const connect = () => {
      let skip = seen;
      closeRef.current = openStream(`/ws/sessions/${sessionId}`, (ev) => {
        if (ev.type === "error" && ev.code === "not_found" && !ev.character) {
          ended = true; dispatch({ type: "streamClosed", status: "lost" }); return;
        }
        if (skip > 0) { skip--; return; }
        seen++; tries = 0;
        if (ev.type === "end") ended = true;
        dispatch({ type: "event", ev });
      }, () => {
        if (!alive || ended) return;
        if (tries++ < 20) timer = window.setTimeout(connect, 1500);
        else dispatch({ type: "streamClosed" });
      });
    };
    connect();
    return () => { alive = false; clearTimeout(timer); closeRef.current?.(); };
  }, [sessionId]);

  const next = useCallback(() => dispatch({ type: "next" }), []);
  const showVerdict = useCallback(() => dispatch({ type: "showVerdict" }), []);
  const say = useCallback((character: CharKey, text: string) => dispatch({ type: "say", character, text }), []);
  const stopNow = useCallback(() => dispatch({ type: "stop" }), []);
  return { state, next, showVerdict, say, stopNow };
}
