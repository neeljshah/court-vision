import Link from "next/link";
import type { ComparisonEntity } from "@/lib/analytics/comparisonData";

type Props = { a: ComparisonEntity; b: ComparisonEntity; sourceHref: string };
type Field = { key: string; label: string; kind: "count" | "probability" | "reference" };

const fields: Field[] = [
  { key: "n", label: "Rows in card (n)", kind: "count" },
  { key: "model_ece", label: "Model ECE (0-1 scale)", kind: "probability" },
  { key: "market_ece", label: "Market ECE (0-1 scale)", kind: "probability" },
  { key: "mean_y_overall", label: "Overall mean outcome (0-1 scale)", kind: "probability" },
  { key: "band_reference", label: "Band reference probability (0-1 scale)", kind: "reference" },
  { key: "n_time_buckets_with_data", label: "Time buckets with data (count)", kind: "count" },
];

function display(value: unknown, kind: Field["kind"]): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return kind === "count" ? value.toLocaleString("en-US") : value.toFixed(4);
  }
  if (kind === "reference" && typeof value === "string" && value.trim()) return value;
  return "Not reported";
}

function bucketRows(entity: ComparisonEntity): Array<{ bucket: string; n: unknown; mean_y: unknown }> {
  const rows = entity.values.by_time_bucket;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap((row) => {
    if (!row || typeof row !== "object" || typeof row.bucket !== "string") return [];
    return [{ bucket: row.bucket, n: row.n, mean_y: row.mean_y }];
  });
}

function typeLabel(cardType?: string): string {
  if (cardType === "time_checkpoint") return "Time checkpoint";
  if (cardType === "prob_band") return "Probability band";
  return "Card type not reported";
}

function EntityCard({ entity, label }: { entity: ComparisonEntity; label: string }) {
  return <article className="compare-profile">
    <span className="compare-profile-label">{label}</span>
    <div className="compare-monogram" aria-hidden="true">{entity.name.slice(0, 1)}</div>
    <h2><Link href={`/analytics/players/calibration/${entity.slug}`}>{entity.name}</Link></h2>
    <p>{entity.sport || "Sport not reported"} | {typeLabel(entity.cardType)}</p>
    <p style={{ overflowWrap: "anywhere" }}>Source snapshot: {entity.asOf || "Not reported"}</p>
    <p style={{ overflowWrap: "anywhere" }}>Published card floor: {entity.floors || "Not reported"}</p>
  </article>;
}

function BucketTable({ entity }: { entity: ComparisonEntity }) {
  const rows = bucketRows(entity);
  if (!rows.length) return null;
  return <div className="compare-table-wrap" style={{ marginTop: 12 }}>
    <table className="compare-table" style={{ minWidth: 480 }}>
      <caption>{entity.name}: published time-bucket rows</caption>
      <thead><tr><th scope="col">Source time bucket</th><th scope="col">Rows (n)</th><th scope="col">Mean outcome (0-1 scale)</th></tr></thead>
      <tbody>{rows.map((row, index) => <tr key={`${row.bucket}-${index}`}>
        <th scope="row">{row.bucket}</th><td>{display(row.n, "count")}</td><td>{display(row.mean_y, "probability")}</td>
      </tr>)}</tbody>
    </table>
  </div>;
}

export function CalibrationComparison({ a, b, sourceHref }: Props) {
  const shownFields = fields.filter((field) => a.values[field.key] !== undefined || b.values[field.key] !== undefined);
  const hasBuckets = bucketRows(a).length > 0 || bucketRows(b).length > 0;

  return <section aria-labelledby="calibration-comparison-title">
    <div className="compare-profiles" aria-label="Selected calibration cards">
      <EntityCard entity={a} label="Card A" />
      <div className="compare-versus" aria-hidden="true">vs</div>
      <EntityCard entity={b} label="Card B" />
    </div>
    <div className="compare-ladder">
      <span className="compare-section-label">Published calibration records</span>
      <h2 id="calibration-comparison-title">Raw card values</h2>
      <p>These cards may cover different sports, populations, checkpoints, or probability bands. Their definitions and observation windows are not established by the snapshot dates. Values are displayed independently; no rank, difference, or winner is calculated.</p>
      <p>Expected calibration error (ECE) summarizes calibration on a 0-1 probability scale. The manifest does not specify its bin definitions or observation population, so these values alone do not establish model or market superiority.</p>
    </div>
    <div className="compare-table-wrap">
      <table className="compare-table" style={{ minWidth: 600 }}>
        <caption>Published calibration values</caption>
        <thead><tr><th scope="col">Published field</th><th scope="col">{a.name}</th><th scope="col">{b.name}</th></tr></thead>
        <tbody>{shownFields.map((field) => <tr key={field.key}>
          <th scope="row">{field.label}</th><td>{display(a.values[field.key], field.kind)}</td><td>{display(b.values[field.key], field.kind)}</td>
        </tr>)}</tbody>
      </table>
    </div>
    {hasBuckets ? <div className="compare-ladder">
      <h2>Published time-bucket detail</h2>
      <p>Each row below belongs only to its named card. Bucket row counts and means are separate from the card row count and from the number of populated buckets. A card floor does not imply each bucket meets that floor.</p>
      <BucketTable entity={a} /><BucketTable entity={b} />
    </div> : null}
    <p className="compare-note">The as-of timestamp marks the source snapshot, not the start or end of observations. "Not reported" means this field is absent or invalid for that card; zero is a reported value.</p>
    <p className="compare-sources">Source: <a href={sourceHref} target="_blank" rel="noreferrer">raw calibration manifest, including card records and bucket detail</a>.</p>
  </section>;
}
