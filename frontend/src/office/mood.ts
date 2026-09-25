import type { History } from "../api";
import type { CharKey } from "../i18n";

/** Office mood, always derived from real closing prices (latest vs previous close). */
export type Mood = "rally" | "up" | "flat" | "down" | "slump" | "none";
export type MoodInfo = { mood: Mood; change: number | null; ticker: string | null; date: string | null };

export function moodFrom(h: History | null | undefined): MoodInfo {
  const cs = h?.closes;
  if (!h?.available && !cs) return { mood: "none", change: null, ticker: null, date: null };
  if (!cs || cs.length < 2) return { mood: "none", change: null, ticker: h?.ticker ?? null, date: null };
  const change = cs[cs.length - 1] / cs[cs.length - 2] - 1;
  const mood: Mood = change >= 0.02 ? "rally" : change >= 0.003 ? "up" : change <= -0.02 ? "slump" : change <= -0.003 ? "down" : "flat";
  return { mood, change, ticker: h.ticker ?? null, date: h.dates?.[h.dates.length - 1] ?? null };
}

const positive = (m: Mood) => m === "up" || m === "rally";
const negative = (m: Mood) => m === "down" || m === "slump";

/** Each character reads the tape through their own personality. */
export function faceFor(c: CharKey, m: Mood): "happy" | "worry" | null {
  if (m === "none" || m === "flat") return null;
  if (c === "Tank") return null;                                    // slow and steady, whatever happens
  if (c === "Bruno") return negative(m) ? "happy" : m === "rally" ? "worry" : null;  // the bear enjoys red days
  if (c === "Leo") return m === "rally" ? "happy" : m === "slump" ? "worry" : null;  // composed chairman
  if (positive(m)) return "happy";
  return "worry";
}
