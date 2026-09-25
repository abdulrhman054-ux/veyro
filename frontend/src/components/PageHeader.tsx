import type { ReactNode } from "react";
import type { CharKey } from "../i18n";
import { Stroller } from "./Stroller";

/** The same header on every screen: title + one friendly line, and the screen's host character
 *  strolling beside them while doing their job. */
export function PageHeader({ title, sub, host, say, side, extra }: {
  title: ReactNode; sub: ReactNode; host: CharKey; say?: string; side?: ReactNode; extra?: { name: CharKey; say?: string }[];
}) {
  return (
    <section className="card pagehead">
      <div className="pagehead-text">
        <div className="row" style={{ gap: 10 }}><h1>{title}</h1>{side}</div>
        <p className="muted">{sub}</p>
      </div>
      <div className="pagehead-lane">
        <Stroller walkers={[{ name: host, say, dur: 20 }, ...(extra ?? []).map((e, i) => ({ ...e, dur: 17, delay: 7 + i * 4 }))]} />
      </div>
    </section>
  );
}
