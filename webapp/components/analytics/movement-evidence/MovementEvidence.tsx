import type { AbsorptionEvidence, OverreactionEvidence } from "@/lib/analytics/movementEvidence";
import styles from "./MovementEvidence.module.css";

const count = (value: number | null): string => value === null ? "Not published" : value.toLocaleString("en-US");
const percent = (value: number | null): string => value === null ? "Not published" : `${(value * 100).toFixed(2)}%`;
const signedPoints = (value: number): string => `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)} pp`;
const window = (value: { start: string | null; end: string | null; days: number | null; files: number | null }): string =>
  value.start && value.end && value.days !== null && value.files !== null ? `${value.start} to ${value.end} (${value.days} days; ${value.files} files)` : "Not published";
const interval = (value: { median: number | null; p90: number | null; mean: number | null }): string =>
  value.median !== null && value.p90 !== null && value.mean !== null ? `median ${value.median.toFixed(3)}, p90 ${value.p90.toFixed(3)}, mean ${value.mean.toFixed(3)} min` : "Not published";

function OverreactionTable({ evidence }: { evidence: OverreactionEvidence }) {
  return <section className={styles.evidence} aria-label="Market overreaction operands">
    <p className="overline">Published operands</p><h2>Moved-to price and outcome rate</h2>
    <p className={styles.intro}>The signed difference is derived from the two preceding columns and shown beside the published field.</p>
    <div className={styles.scroll} role="region" aria-label="Market overreaction operands table" data-scroll-region><table className={styles.table}>
      <caption>Bucketed moved-to price versus outcome rate</caption><thead><tr><th>Sport</th><th className={styles.left}>Bucket</th><th>n</th><th>Moved-to price</th><th>Outcome rate</th><th>Price minus outcome</th></tr></thead>
      <tbody>{evidence.rows.map(row => <tr key={`${row.sport}-${row.bucket}`}><td>{row.sport}</td><td className={styles.left}>{row.bucket}</td><td>{count(row.n)}</td><td>{percent(row.movedToPrice)}</td><td>{percent(row.outcomeRate)}</td><td>{signedPoints(row.derivedDifference)} (published {signedPoints(row.statedDifference)})</td></tr>)}</tbody>
    </table></div>
    <p className={styles.note}>Observation dates, snapshot intervals, and independent-game counts are not published in this artifact. International soccer&apos;s 6-10pt bucket has n=21 and should be read as limited support.</p>
  </section>;
}

function AbsorptionTable({ evidence }: { evidence: AbsorptionEvidence }) {
  return <section className={styles.evidence} aria-label="Micro absorption operands">
    <p className="overline">Published operands</p><h2>Pregame movement coverage by sport</h2>
    <p className={styles.intro}>Mean movement per pair is total absolute movement divided by move pairs. Final-hour movement share is a separate fraction of total movement, not a per-pair mean.</p>
    <div className={styles.scroll} role="region" aria-label="Micro absorption operands table" data-scroll-region><table className={styles.table}>
      <caption>Sport-specific source coverage and movement quantities</caption><thead><tr><th>Sport</th><th className={styles.left}>Availability</th><th className={styles.left}>Observation window</th><th className={styles.left}>Snapshot cadence</th><th>Pregame snapshots</th><th>Move pairs</th><th>Series used</th><th>Mean movement per pair</th><th>Final-hour movement share</th><th>6h+ mean</th><th>3-6h mean</th><th>1-3h mean</th><th>0-1h mean</th></tr></thead>
      <tbody>{evidence.rows.map(row => <tr key={row.sport}><td>{row.sport}</td><td className={`${styles.left} ${row.availability === "unavailable" ? styles.unavailable : ""}`}>{row.availability === "published" ? "Published" : "Unavailable"}</td><td className={styles.left}>{window(row.observationWindow)}</td><td className={styles.left}>{interval(row.intervalMinutes)}</td><td>{count(row.nPregameSnapshots)}</td><td>{count(row.nMovePairs)}</td><td>{count(row.nSeriesUsed)}</td><td>{percent(row.meanMovementPerPair)}</td><td>{percent(row.finalHourMovementShare)}</td><td>{percent(row.movementByBucket["6h+"] ?? null)}</td><td>{percent(row.movementByBucket["3-6h"] ?? null)}</td><td>{percent(row.movementByBucket["1-3h"] ?? null)}</td><td>{percent(row.movementByBucket["0-1h"] ?? null)}</td></tr>)}</tbody>
    </table></div>
    <p className={styles.note}>Independent-game counts are not published. Series used and dense snapshots are reported separately and do not supply an independent-game count.</p>
  </section>;
}

export function MovementEvidence({ kind, evidence }: { kind: "market_overreaction" | "micro_absorption"; evidence: OverreactionEvidence | AbsorptionEvidence }) {
  return kind === "market_overreaction"
    ? <OverreactionTable evidence={evidence as OverreactionEvidence} />
    : <AbsorptionTable evidence={evidence as AbsorptionEvidence} />;
}
