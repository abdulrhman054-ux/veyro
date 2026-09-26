import type { CharKey } from "../i18n";

/** The stage: each part of a session plays on its own set, with its own blocking.
 *  A position is [left, top] inside the 1000×740 room; null means the character has stepped out. */
export type SceneId = "office" | "charts" | "social" | "newsdesk" | "ledger" | "debate" | "plan" | "risk" | "world" | "decision";
const SOLO = (who: Cast, at: [number, number] = [425, 230]): Record<Cast, Pos> =>
  ({ Ollie: null, Buzz: null, Pip: null, Benny: null, Bolt: null, Bruno: null, Tank: null, Leo: null, [who]: at });
type Cast = Exclude<CharKey, "Albie">;
type Pos = [number, number] | null;

export const OFFICE: Record<Cast, [number, number]> = {
  Ollie: [825, 160], Buzz: [635, 160], Leo: [425, 160], Pip: [215, 160], Benny: [25, 160],
  // The back row sits low enough that its heads (Bolt's horns, Bruno's ears) never cover the front row's names.
  Bolt: [720, 362], Bruno: [425, 362], Tank: [130, 362],
};

export const BLOCKING: Record<SceneId, Record<Cast, Pos>> = {
  office: OFFICE,
  // Close-ups: each analyst presents from their own corner of the building.
  charts: SOLO("Ollie", [560, 230]),
  social: SOLO("Buzz", [425, 220]),
  newsdesk: SOLO("Pip", [425, 200]),
  ledger: SOLO("Benny", [300, 220]),
  // Only the two debaters stay in the arena; Leo moderates from the back, everyone else steps out.
  debate: { Bolt: [650, 250], Bruno: [200, 250], Leo: [425, 70], Ollie: null, Buzz: null, Pip: null, Benny: null, Tank: null },
  // Leo's office: he writes the plan and the trade; the debaters are called in to hear it.
  plan: { Leo: [425, 190], Bolt: [720, 300], Bruno: [130, 300], Ollie: null, Buzz: null, Pip: null, Benny: null, Tank: null },
  // Risk control room: Tank runs the three-way risk debate, Leo watches.
  risk: { Tank: [425, 230], Leo: [760, 300], Bolt: null, Bruno: null, Ollie: null, Buzz: null, Pip: null, Benny: null },
  // Newsroom: Albie lands with the world's headlines; Pip (stock news) and Leo listen.
  world: { Pip: [720, 300], Leo: [130, 300], Ollie: null, Buzz: null, Benny: null, Bolt: null, Bruno: null, Tank: null },
  // Boardroom: everyone around the table for Leo's call.
  decision: { Leo: [425, 118], Ollie: [60, 110], Buzz: [230, 110], Pip: [620, 110], Benny: [790, 110],
              Bolt: [170, 330], Tank: [425, 340], Bruno: [680, 330] },
};

export const ALBIE_AT: Record<SceneId, [number, number]> = {
  office: [690, 4], charts: [870, 4], social: [870, 4], newsdesk: [870, 4], ledger: [870, 4], debate: [690, 4], plan: [690, 4], risk: [690, 4], world: [440, 150], decision: [870, 4],
};

export const SCENE_LABEL: Record<SceneId, { ar: string; en: string; n: number }> = {
  office: { ar: "المحللون على مكاتبهم", en: "The analysts at their desks", n: 1 },
  charts: { ar: "غرفة الشارتات مع أولي", en: "The chart room with Ollie", n: 1 },
  social: { ar: "خلية المزاج العام مع بَز", en: "The buzz hive with Buzz", n: 1 },
  newsdesk: { ar: "استوديو الأخبار مع بيب", en: "The news studio with Pip", n: 1 },
  ledger: { ar: "دفاتر الحسابات مع بيني", en: "The ledger desk with Benny", n: 1 },
  debate: { ar: "حلبة النقاش: بولت ضد برونو", en: "The debate arena: Bolt vs Bruno", n: 2 },
  plan: { ar: "مكتب ليو: الخطة والصفقة", en: "Leo's office: the plan and the trade", n: 3 },
  risk: { ar: "غرفة المخاطر مع تانك", en: "The risk room with Tank", n: 4 },
  world: { ar: "غرفة الأخبار: ألبي وصل", en: "The newsroom: Albie has landed", n: 5 },
  decision: { ar: "قاعة القرار", en: "The boardroom: the decision", n: 6 },
};

/** speaking=true: the set for a line being played (analysts get their close-up);
 *  speaking=false: where the team works while that step is still thinking. */
export function sceneOf(node: string | null | undefined, speaking = false): SceneId | null {
  switch (node) {
    case "Market Analyst": return speaking ? "charts" : "office";
    case "Sentiment Analyst": return speaking ? "social" : "office";
    case "News Analyst": return speaking ? "newsdesk" : "office";
    case "Fundamentals Analyst": return speaking ? "ledger" : "office";
    case "Bull Researcher": case "Bear Researcher": return "debate";
    case "Research Manager": case "Trader": return "plan";
    case "Risk Team": case "Aggressive Analyst": case "Conservative Analyst": case "Neutral Analyst": return "risk";
    case "Global Link": return "world";
    case "Portfolio Manager": return "decision";
    default: return null;
  }
}

/** How a line sounds, from its own words: drives the speaker's face and gestures. */
export type Tone = "pos" | "neg" | "excited" | "calm";
const POS = /(صعود|ارتفاع|قوي|قوية|فرصة|ممتاز|نمو|إيجابي|ايجابي|تفاؤل|شراء|زين|upside|bull|strong|growth|opportunit|positive|optimis|buy|beat|gain|rall)/i;
const NEG = /(هبوط|انخفاض|ضعيف|ضعف|خطر|مخاطر|حذر|سلبي|تراجع|بيع|خسار|قلق|downside|bear|weak|risk|caution|negative|sell|loss|declin|concern|volatil)/i;
export function toneScore(text: string | null | undefined): { p: number; n: number; bangs: number } {
  if (!text) return { p: 0, n: 0, bangs: 0 };
  return { p: (text.match(new RegExp(POS, "gi")) ?? []).length, n: (text.match(new RegExp(NEG, "gi")) ?? []).length,
    bangs: (text.match(/!/g) ?? []).length };
}
export function toneOf(text: string | null | undefined): Tone {
  if (!text) return "calm";
  const { p, n, bangs } = toneScore(text);
  if (p > n) return bangs >= 2 ? "excited" : "pos";
  if (n > p) return "neg";
  return bangs >= 2 ? "excited" : "calm";
}
