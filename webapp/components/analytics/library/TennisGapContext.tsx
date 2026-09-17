import Link from "next/link";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";
import styles from "./TennisGapContext.module.css";

const IDS = {
  clay: "tennis-clay-gap-window-shift",
  grass: "tennis-grass-gap-window-shift",
} as const;

function contextFor(id: string) {
  if (id === IDS.clay) return {
    title: "Clay versus hard-court gap",
    baseline: "Clay win rate minus hard-court win rate",
    sibling: IDS.grass,
    siblingLabel: "View grass versus overall gap",
  };
  if (id === IDS.grass) return {
    title: "Grass versus pooled overall gap",
    baseline: "Grass win rate minus pooled overall win rate",
    sibling: IDS.clay,
    siblingLabel: "View clay versus hard-court gap",
  };
  return null;
}

export function TennisGapContext({ analysis }: { analysis: ResearchAnalysis }) {
  const context = contextFor(analysis.id);
  if (!context) return null;

  return <section className={styles.context} aria-label="Tennis gap window context">
    <div className={styles.heading}>
      <p className="cv-eyebrow">Window context</p>
      <h2>{context.title}</h2>
      <p>Each row keeps its distinct baseline visible before comparing the two published windows.</p>
    </div>
    <div className={styles.grid}>
      <section className={styles.cell} aria-label="Gap definition">
        <p className={styles.label}>Gap definition</p>
        <p>{context.baseline}.</p>
        {analysis.id === IDS.grass && <p className={styles.note}>The pooled overall rate includes grass matches.</p>}
      </section>
      <section className={styles.cell} aria-label="Published windows">
        <p className={styles.label}>Published windows</p>
        <p>Source-career covers the available 2015-2025 corpus, not lifetime career.</p>
        <p className={styles.note}>Recent starts 2023-01-01 and overlaps the source corpus.</p>
      </section>
      <section className={styles.cell} aria-label="Row comparison">
        <p className={styles.label}>Row comparison</p>
        <p>Change equals recent gap minus corpus gap.</p>
        <p className={styles.note}>{analysis.rows.length} qualified {analysis.rows.length === 1 ? "player" : "players"}; exact match counts are unavailable.</p>
      </section>
    </div>
    <p className={styles.caveat}>These recorded differences do not establish a change in skill or its cause.</p>
    <Link className={styles.link} href={`/analytics/research/${context.sibling}/`}>{context.siblingLabel}</Link>
  </section>;
}
