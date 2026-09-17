import type { Metadata } from "next";
import Link from "next/link";
import { artifactUrl } from "@/lib/analytics/artifactProvenance";
import { countWord, type CardVerdict } from "@/lib/analytics/novelCards";
import { getNovelCards } from "@/lib/analytics/novelCards.server";

export const metadata: Metadata = {
  title: "Experimental measurements",
  description: "Published experimental measurements with their results, intervals, and declared limitations.",
};

const baseName = (path: string) => path.split(/[\\/]/).pop() || path;
const verdictClass = (verdict: CardVerdict) => ({
  confirmed: "d-conf", null: "d-null", contradicted: "d-reject", descriptive: "d-desc",
}[verdict]);

const GATE = [
  ["Prior-art search", "The definition is searched against published literature and the public analytics canon before it is built. The verdict remains visible when someone reached most of the way there first."],
  ["Buildability check", "The stat must be computable from committed artifacts. No new scrape, private feed, or number that cannot be recomputed from its cited source files."],
  ["Adversarial re-derivation", "The result is rebuilt by a different route where one exists, specifically to try to break it. Disagreement between methods is printed rather than hidden."],
  ["Declared confounds", "Every stat publishes what could make it wrong: sparse tail buckets, excluded sports, absolute-move churn, or model misspecification. Confounds are part of the stat."],
  ["Descriptive scope", "These are measurements of observed structure and model behavior. Each artifact states its result and limits together."],
];

export default function NovelStatsPage() {
  const cards = getNovelCards();

  return (
    <div className="wrap nv">
      <p className="overline">Experimental measurements</p>
      <h1 className="serif nv-h1">{countWord(cards.length)} published experimental measurements</h1>
      <p className="nv-lede">
        Each measurement was searched against prior art before it was built, re-derived to try to break it,
        and published with the confounds that could change its interpretation.
      </p>
      <p className="nv-meta mono">{cards.length} stats; each number below is lifted from its committed artifact.</p>

      <div className="nv-grid">
        {cards.map((card, index) => (
          <article key={card.id} className={`nv-card is-${card.verdict}`} data-testid={`novel-card-${card.id}`}>
            <div className="nv-top">
              <span className="mono nv-n">{String(index + 1).padStart(2, "0")}</span>
              <span className="mono nv-verdict"><span className={`dot ${verdictClass(card.verdict)}`} />{card.verdict}</span>
            </div>
            <h2 className="serif nv-name">{card.title} <span className="mono nv-abbrev">{card.abbrev}</span></h2>
            <div className="nv-figure">
              <div className="nv-value tnum">{card.lead}</div>
              <div className="nv-unit">{card.leadLabel}</div>
              <p className="mono nv-denominator">{card.denominator}</p>
              {card.interval ? <p className="mono nv-interval">95 percent interval {card.interval}</p> : null}
            </div>
            <p className="nv-result">{card.result}</p>
            <p className="nv-limit"><span>Limitation</span>{card.limitation}</p>
            <div className="nv-foot">
              <div className="mono nv-src">
                {card.sourceArtifacts.map((source) => artifactUrl(source)
                  ? <a key={source} href={artifactUrl(source) || undefined} download>{baseName(source)}</a>
                  : <div key={source}>{baseName(source)} (not published)</div>)}
                <div className="nv-asof">{card.snapshot}</div>
                {card.estimatorWindows.map(([label, value]) => <div className="nv-asof" key={label}>{label}: {value}</div>)}
                {card.confoundCount ? <div className="nv-asof">{card.confoundCount} confounds declared</div> : null}
              </div>
              <Link className="nv-link" href={`/analytics/m/${card.id}`}>Formula, results table and prior art</Link>
            </div>
          </article>
        ))}
      </div>

      <section className="nv-gate">
        <p className="overline">Publication checks</p>
        <h2 className="serif nv-h2">How these measurements are published</h2>
        <ol className="nv-steps">
          {GATE.map(([title, body]) => <li key={title}><div><h3 className="nv-step-t">{title}</h3><p>{body}</p></div></li>)}
        </ol>
        <p className="nv-close">These measurements are explicit about their own limits, and every one can be recomputed from the artifacts named on its card.</p>
      </section>

      <style>{`
        .nv{padding:48px 24px 72px}.nv-h1{font-weight:500;font-size:clamp(2.1rem,4.4vw,3.1rem);line-height:1.07;letter-spacing:-.02em;margin-top:10px;max-width:19ch}
        .nv-lede{margin-top:18px;max-width:660px;font-size:17px;line-height:1.66;color:var(--ink-2)}.nv-meta{margin-top:16px;font-size:12px;color:var(--ink-3);padding-bottom:26px;border-bottom:1px solid var(--rule-strong)}
        .nv-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:26px;margin-top:34px}.nv-card{display:flex;flex-direction:column;background:var(--paper-raised);border:1px solid var(--rule);border-top:3px solid var(--signal);border-radius:var(--radius-card);padding:22px 24px 20px;box-shadow:var(--shadow-card)}.nv-card.is-null{border-top-color:var(--null)}.nv-card.is-contradicted{border-top-color:var(--reject)}
        .nv-top{display:flex;align-items:center;justify-content:space-between;gap:12px}.nv-n{font-size:12px;color:var(--ink-3)}.nv-verdict{display:inline-flex;align-items:center;gap:7px;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-2);border:1px solid var(--rule-strong);border-radius:var(--radius-chip);padding:3px 9px}
        .nv-name{font-weight:500;font-size:25px;letter-spacing:-.01em;margin-top:12px;line-height:1.2}.nv-abbrev{font-size:13px;color:var(--ink-3);letter-spacing:.06em;margin-left:6px}.nv-figure{margin-top:18px;padding-top:16px;border-top:1px solid var(--rule)}.nv-value{font-family:var(--font-display);font-weight:500;font-size:clamp(2.4rem,5.5vw,3.6rem);line-height:.98;letter-spacing:-.03em;color:var(--ink)}.nv-unit{margin-top:6px;font-size:13.5px;color:var(--ink-2)}.nv-denominator,.nv-interval{margin-top:7px;font-size:11.5px;line-height:1.5;color:var(--ink-3)}.nv-interval{color:var(--ink-2)}
        .nv-result{margin-top:16px;font-size:13.5px;line-height:1.58;color:var(--ink-2)}.nv-limit{margin-top:12px;background:var(--paper-tint);border-left:2px solid var(--rule-strong);border-radius:0 8px 8px 0;padding:10px 12px;font-size:12.5px;line-height:1.55;color:var(--ink-2)}.nv-limit span{display:block;margin-bottom:3px;font-family:var(--font-mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)}.nv-foot{margin-top:auto;padding-top:18px}.nv-src{font-size:11px;line-height:1.7;color:var(--ink-3);word-break:break-all}.nv-asof{color:var(--ink-3);opacity:.85}.nv-link{display:inline-block;margin-top:12px;font-size:13.5px;font-weight:600;color:var(--accent)}
        .nv-gate{margin-top:64px;padding-top:40px;border-top:1px solid var(--rule-strong);max-width:760px}.nv-h2{font-weight:500;font-size:clamp(1.6rem,3vw,2.1rem);letter-spacing:-.015em;margin-top:10px}.nv-steps{list-style:none;margin-top:26px}.nv-steps li{padding:18px 0;border-top:1px solid var(--rule)}.nv-step-t{font-size:15px;font-weight:700;color:var(--ink)}.nv-steps p{margin-top:5px;font-size:14.5px;line-height:1.6;color:var(--ink-2)}.nv-close{margin-top:26px;font-size:15px;line-height:1.65;color:var(--ink-2);border-left:2px solid var(--signal);padding-left:16px}@media(max-width:860px){.nv-grid{grid-template-columns:minmax(0,1fr)}}@media(max-width:600px){.nv{padding:32px 16px 48px}.nv-card{padding:18px 16px}.nv-meta{font-size:11px}}
      `}</style>
    </div>
  );
}
