// Animalese-style blips and tiny jingles, synthesised with WebAudio (no audio files).
let ctx: AudioContext | null = null;
let enabled = true;

export function setSound(on: boolean) { enabled = on; }

function ac(): AudioContext | null {
  try {
    if (!ctx) {
      const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === "suspended") void ctx.resume();
    return ctx;
  } catch { return null; }
}

/** Call from a user gesture so the browser allows audio later. */
export function unlockAudio() { ac(); }

function tone(freq: number, start: number, dur: number, type: OscillatorType = "square", vol = 0.035, slide = 0.7) {
  const a = ac(); if (!a) return;
  const o = a.createOscillator(); const g = a.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, a.currentTime + start);
  o.frequency.exponentialRampToValueAtTime(Math.max(40, freq * slide), a.currentTime + start + dur * 0.9);
  g.gain.setValueAtTime(0.0001, a.currentTime + start);
  g.gain.exponentialRampToValueAtTime(vol, a.currentTime + start + 0.008);
  g.gain.exponentialRampToValueAtTime(0.0001, a.currentTime + start + dur);
  o.connect(g); g.connect(a.destination);
  o.start(a.currentTime + start); o.stop(a.currentTime + start + dur + 0.02);
}

const SILENT = new Set([" ", "،", ".", ",", "…", "!", "?", "؟", "\n", "«", "»"]);

/** Each character's own Animalese-style voice: waveform, register, glide, texture and pace. */
export type Voice = {
  wave: OscillatorType; base: number; spread: number; dur: number; vol: number; slide: number;
  vibrato?: { rate: number; depth: number };   // Buzz's buzz
  harmony?: number;                            // Leo's regal fifth, Bruno's growl (sub-octave)
  hoot?: boolean;                              // Ollie's rise-and-fall
  msPerChar: number; every: number;            // typing pace, blip on every Nth character
};
export const VOICES: Record<string, Voice> = {
  Ollie: { wave: "triangle", base: 420, spread: 0.18, dur: 0.09, vol: 0.05, slide: 0.8, hoot: true, msPerChar: 32, every: 2 },
  Pip:   { wave: "square", base: 780, spread: 0.35, dur: 0.045, vol: 0.03, slide: 1.35, msPerChar: 22, every: 2 },
  Buzz:  { wave: "sawtooth", base: 900, spread: 0.2, dur: 0.07, vol: 0.022, slide: 1.0, vibrato: { rate: 38, depth: 60 }, msPerChar: 25, every: 2 },
  Benny: { wave: "square", base: 520, spread: 0.12, dur: 0.035, vol: 0.035, slide: 0.9, msPerChar: 28, every: 1 },
  Bolt:  { wave: "sawtooth", base: 230, spread: 0.25, dur: 0.08, vol: 0.035, slide: 0.65, msPerChar: 27, every: 2 },
  Bruno: { wave: "triangle", base: 170, spread: 0.15, dur: 0.11, vol: 0.06, slide: 0.75, harmony: 0.5, msPerChar: 36, every: 2 },
  Tank:  { wave: "sine", base: 300, spread: 0.08, dur: 0.14, vol: 0.07, slide: 0.95, msPerChar: 46, every: 3 },
  Leo:   { wave: "square", base: 260, spread: 0.15, dur: 0.1, vol: 0.03, slide: 0.85, harmony: 1.5, msPerChar: 34, every: 2 },
  Albie: { wave: "triangle", base: 640, spread: 0.45, dur: 0.06, vol: 0.045, slide: 1.3, msPerChar: 20, every: 2 },   // chatty glider
};

export function voiceBlip(character: string, ch: string, index: number) {
  const v = VOICES[character];
  if (!enabled || !v || SILENT.has(ch) || index % v.every !== 0) return;
  const a = ac(); if (!a) return;
  const vowel = /[aeiouاويىآأإ]/i.test(ch) ? 1.12 : 1;  // vowels a touch higher, like chatty villagers
  const f = v.base * vowel * (1 - v.spread / 2 + Math.random() * v.spread);
  const t0 = a.currentTime;
  const out = a.createGain();
  out.gain.setValueAtTime(0.0001, t0);
  out.gain.exponentialRampToValueAtTime(v.vol, t0 + 0.008);
  out.gain.exponentialRampToValueAtTime(0.0001, t0 + v.dur);
  out.connect(a.destination);
  const mk = (freq: number, gain = 1) => {
    const o = a.createOscillator(); const g = a.createGain();
    o.type = v.wave; g.gain.value = gain;
    if (v.hoot) {
      o.frequency.setValueAtTime(freq * 0.9, t0);
      o.frequency.linearRampToValueAtTime(freq * 1.08, t0 + v.dur * 0.4);
      o.frequency.linearRampToValueAtTime(freq * 0.8, t0 + v.dur);
    } else {
      o.frequency.setValueAtTime(freq, t0);
      o.frequency.exponentialRampToValueAtTime(Math.max(40, freq * v.slide), t0 + v.dur * 0.9);
    }
    if (v.vibrato) {
      const lfo = a.createOscillator(); const lg = a.createGain();
      lfo.frequency.value = v.vibrato.rate; lg.gain.value = v.vibrato.depth;
      lfo.connect(lg); lg.connect(o.frequency); lfo.start(t0); lfo.stop(t0 + v.dur + 0.02);
    }
    o.connect(g); g.connect(out); o.start(t0); o.stop(t0 + v.dur + 0.02);
  };
  mk(f);
  if (v.harmony) mk(f * v.harmony, 0.5);
}

/** Kept for simple callers: a generic blip at a given pitch. */
export function blip(pitch: number, ch: string) {
  if (!enabled || SILENT.has(ch)) return;
  tone(pitch * (0.88 + Math.random() * 0.3), 0, 0.065);
}

export function pop() { if (enabled) { tone(660, 0, 0.06, "triangle", 0.05, 1.4); } }
export function click() { if (enabled) tone(520, 0, 0.04, "triangle", 0.04, 1.2); }

export function startJingle() {
  if (!enabled) return;
  [523, 659, 784, 1047].forEach((f, i) => tone(f, i * 0.09, 0.14, "triangle", 0.05, 1));
}
export function verdictJingle(tone0: "buy" | "hold" | "sell" | "none") {
  if (!enabled) return;
  const seq = tone0 === "sell" ? [659, 587, 523, 440] : tone0 === "hold" ? [523, 659, 587, 659] : [523, 659, 784, 1047, 1319];
  seq.forEach((f, i) => tone(f, i * 0.12, 0.2, "triangle", 0.06, 1));
}
export function errorBonk() { if (enabled) { tone(220, 0, 0.16, "square", 0.05, 0.5); tone(180, 0.12, 0.2, "square", 0.04, 0.5); } }

/** A character "says" a short line in their own voice (used for click reactions). */
export function speakBlips(character: string, text: string) {
  const v = VOICES[character]; if (!v || !enabled) return;
  [...text].slice(0, 40).forEach((ch, i) => window.setTimeout(() => voiceBlip(character, ch, i), i * v.msPerChar));
}
