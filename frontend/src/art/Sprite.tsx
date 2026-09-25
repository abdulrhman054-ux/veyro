import data from "./sprites.json";
import type { CharKey } from "../i18n";

type Frame = "down" | "typeA" | "typeB" | "wave" | "walkA" | "walkB";
type CharData = {
  color: string; lid: string; mouth: [number, number, number]; stripes?: boolean;
  colors: Record<string, string>; head: string[]; back?: { row: number; rows: string[] };
};
const W = 24, H = 26;
const chars = data.characters as unknown as Record<CharKey, CharData>;
const bodies = data.bodies as Record<Frame, string[]>;
const palette = data.palette as Record<string, string>;

export const charColor = (c: CharKey) => chars[c].color;

const row = (r: string) => (r.length === 12 ? r + r.split("").reverse().join("").replace(/wk/g, "kw") : r);

type Expr = "blink" | "talk" | "happy" | "worry";

function grid(name: CharKey, frame: Frame, blink = false, talk = false, expr?: "happy" | "worry"): string[][] {
  const c = chars[name];
  const g = Array.from({ length: H }, () => Array<string>(W).fill("."));
  if (c.back) c.back.rows.forEach((r, i) => row(r).split("").forEach((ch, x) => { if (ch !== ".") g[c.back!.row + i][x] = ch; }));
  bodies[frame].forEach((r0, i) => {
    let r = row(r0);
    if (c.stripes && (i === 2 || i === 4)) r = r.replace(/S/g, "T");
    r.split("").forEach((ch, x) => { if (ch !== ".") g[16 + i][x] = ch; });
  });
  c.head.forEach((r, y) => row(r).split("").forEach((ch, x) => { if (ch !== ".") g[y][x] = ch; }));
  if (blink) {
    const nearK = (x: number, y: number) => [[1, 0], [-1, 0], [0, 1], [0, -1]].some(([dx, dy]) => g[y + dy]?.[x + dx] === "k");
    const eyes: [number, number][] = [];
    for (let y = 0; y < 16; y++) for (let x = 0; x < W; x++) if (g[y][x] === "k" || (g[y][x] === "w" && nearK(x, y))) eyes.push([x, y]);
    const bottom = Math.max(...eyes.map(([, y]) => y));
    eyes.forEach(([x, y]) => { g[y][x] = y === bottom ? "o" : "@lid"; });
  }
  if (talk) { const [mx, my, mw] = c.mouth; for (let x = mx; x < mx + mw; x++) g[my][x] = "@mouth"; }
  if (expr) {
    const eyes: [number, number][] = [];
    for (let y = 0; y < 16; y++) for (let x = 0; x < W; x++) if (g[y][x] === "k") eyes.push([x, y]);
    if (!eyes.length) return g;
    const top = Math.min(...eyes.map(([, y]) => y));
    const bottom = Math.max(...eyes.map(([, y]) => y));
    if (expr === "happy") {
      // closed, smiling eyes (^^) plus a stronger blush
      for (let y = 0; y < 16; y++) for (let x = 0; x < W; x++) {
        if (g[y][x] === "k" || (g[y][x] === "w" && (g[y][x - 1] === "k" || g[y][x + 1] === "k" || g[y + 1]?.[x] === "k"))) g[y][x] = y === top ? "o" : "@lid";
        if (g[y][x] === "p") g[y][x] = "@blush";
      }
    } else {
      // worried brows: inner ends raised, one pixel above each eye
      const left = eyes.filter(([x]) => x < 12), right = eyes.filter(([x]) => x >= 12);
      const lx = Math.min(...left.map(([x]) => x)), rx = Math.min(...right.map(([x]) => x));
      const put = (x: number, y: number) => { if (y >= 0 && g[y][x] !== ".") g[y][x] = "o"; };
      if (left.length) { put(lx, top - 1); put(lx + 1, top - 2); }
      if (right.length) { put(rx + 1, top - 1); put(rx, top - 2); }
      void bottom;
    }
  }
  return g;
}

function colorOf(name: CharKey, ch: string) {
  const c = chars[name];
  if (ch === "@lid") return c.lid;
  if (ch === "@mouth") return "#7A2E2E";
  if (ch === "@blush") return "#F07C8A";
  return c.colors[ch] ?? palette[ch] ?? c.colors.H;
}

function toPaths(name: CharKey, g: string[][], only?: string[][]) {
  const runs = new Map<string, string[]>();
  for (let y = 0; y < H; y++) {
    let x = 0;
    while (x < W) {
      const ch = g[y][x];
      if (ch === "." || (only && only[y][x] === ch)) { x++; continue; }
      const s = x;
      while (x < W && g[y][x] === ch && !(only && only[y][x] === ch)) x++;
      const col = colorOf(name, ch);
      if (!runs.has(col)) runs.set(col, []);
      runs.get(col)!.push(`M${s} ${y}h${x - s}v1h-${x - s}z`);
    }
  }
  return [...runs.entries()].map(([fill, d]) => ({ fill, d: d.join("") }));
}

const cache = new Map<string, { fill: string; d: string }[]>();
export function spritePaths(name: CharKey, frame: Frame = "down", blink = false, talk = false) {
  const k = `${name}|${frame}|${blink}|${talk}`;
  if (!cache.has(k)) cache.set(k, toPaths(name, grid(name, frame, blink, talk)));
  return cache.get(k)!;
}
/** Only the pixels that differ from the plain frame: eyelids, open mouth, happy or worried face. */
export function overlayPaths(name: CharKey, kind: Expr) {
  const k = `${name}|overlay|${kind}`;
  if (!cache.has(k)) {
    const base = grid(name, "down");
    const alt = grid(name, "down", kind === "blink", kind === "talk", kind === "happy" || kind === "worry" ? kind : undefined);
    cache.set(k, toPaths(name, alt, base));
  }
  return cache.get(k)!;
}

export function SpriteSvg({ name, px = 5, frame = "down", blink = false, talk = false, className, overlay }: {
  name: CharKey; px?: number; frame?: Frame; blink?: boolean; talk?: boolean; className?: string; overlay?: Expr;
}) {
  const paths = overlay ? overlayPaths(name, overlay) : spritePaths(name, frame, blink, talk);
  return (
    <svg className={className} width={W * px} height={H * px} viewBox={`0 0 ${W} ${H}`} shapeRendering="crispEdges" aria-hidden="true">
      {paths.map((p) => <path key={p.fill} fill={p.fill} d={p.d} />)}
    </svg>
  );
}

/** A character walking: alternating legs, CSS toggles the frames. */
export function WalkingSprite({ name, px = 3 }: { name: CharKey; px?: number }) {
  return (
    <>
      <SpriteSvg name={name} px={px} frame="walkA" className="fr wka" />
      <SpriteSvg name={name} px={px} frame="walkB" className="fr wkb" />
      <SpriteSvg name={name} px={px} overlay="blink" className="fr bl" />
    </>
  );
}

/** Full animated character: all frames stacked, CSS decides which one shows. */
export function AnimatedSprite({ name, px = 5 }: { name: CharKey; px?: number }) {
  return (
    <>
      <SpriteSvg name={name} px={px} frame="typeA" className="fr ta" />
      <SpriteSvg name={name} px={px} frame="typeB" className="fr tb" />
      <SpriteSvg name={name} px={px} frame="down" className="fr dn" />
      <SpriteSvg name={name} px={px} frame="wave" className="fr wv" />
      <SpriteSvg name={name} px={px} overlay="blink" className="fr bl" />
      <SpriteSvg name={name} px={px} overlay="talk" className="fr mo" />
      <SpriteSvg name={name} px={px} overlay="happy" className="fr hp" />
      <SpriteSvg name={name} px={px} overlay="worry" className="fr wr" />
    </>
  );
}
