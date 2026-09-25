import { AnimatedSprite, WalkingSprite } from "../art/Sprite";
import type { CharKey } from "../i18n";

/** A character walking back and forth doing their job on a screen (e.g. Tank patrolling the orders).
 *  Purely decorative; hidden from screen readers. Motion follows the intensity / reduced-motion setting. */
export function Stroller({ walkers, sky = false, height }: {
  walkers: { name: CharKey; say?: string; dur?: number; delay?: number; fly?: boolean }[]; sky?: boolean; height?: number;
}) {
  return (
    <div className={`stroll${sky ? " sky" : ""}`} aria-hidden="true" style={height ? { height } : undefined}>
      {walkers.map((w, i) => w.fly ? (
        <div key={i} className="flyer" style={{ ["--dur" as string]: `${w.dur ?? 22}s`, animationDelay: `-${w.delay ?? 0}s` }}>
          <div className="inner sprite" style={{ position: "absolute", left: 0, top: 0, width: 96, height: 104, animation: "none" }}><AnimatedSprite name={w.name} px={4} /></div>
        </div>
      ) : (
        <div key={i} className="walker" style={{ ["--dur" as string]: `${w.dur ?? 16}s`, animationDelay: `-${w.delay ?? 0}s` }}>
          <div className="inner"><WalkingSprite name={w.name} px={3} /></div>
          {w.say && <div className="say">{w.say}</div>}
        </div>
      ))}
    </div>
  );
}
