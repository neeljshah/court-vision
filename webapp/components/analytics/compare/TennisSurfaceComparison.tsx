import { formatMetric, formatPercentile, type ComparisonEntity } from "@/lib/analytics/comparisonData";
import { tennisSurfaceComparison, type TennisSurface } from "@/lib/analytics/tennisSurfaceComparison";

const SURFACES: Array<{ key: TennisSurface; label: string }> = [
  { key: "hard", label: "Hard" }, { key: "clay", label: "Clay" }, { key: "grass", label: "Grass" },
];

type Props = {
  a: ComparisonEntity;
  b: ComparisonEntity;
  surface: TennisSurface;
  onSurfaceChange: (surface: TennisSurface) => void;
  sourceHref: string;
};

function Value({ value, percentile, field, unit }: { value: number | null; percentile: number | null; field: string; unit: "percent" | "pp" }) {
  if (value === null) return <span className="tennis-surface-unavailable">Not reported</span>;
  const displayField = unit === "pp" ? "clay_minus_hard_career" : field;
  return <><strong>{formatMetric(value, displayField)}</strong><small>{percentile !== null ? formatPercentile(percentile) : "Not ranked"}</small></>;
}

function surfaceEligibility(surface: TennisSurface): string {
  if (surface === "hard") return "Hard win rate needs 30 or more hard-court matches per window.";
  if (surface === "clay") return "Clay win rate needs 30 or more clay matches; the clay-minus-hard measure needs 25 or more clay and hard matches per window.";
  return "Grass win rate needs 30 or more grass matches; grass adaptability needs 15 or more grass matches per window.";
}

function shortDate(value: string): string {
  const iso = value.match(/^\d{4}-\d{2}-\d{2}/)?.[0];
  if (iso) return iso;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

export function TennisSurfaceComparison({ a, b, surface, onSurfaceChange, sourceHref }: Props) {
  const comparison = tennisSurfaceComparison(a, b, surface);
  const availableRows = comparison.rows.filter((row) => row.a.value !== null || row.b.value !== null);
  const aDate = comparison.entities.a.asOf;
  const bDate = comparison.entities.b.asOf;

  return <section className="tennis-surface-comparison" aria-labelledby="tennis-surface-title">
    <div className="tennis-surface-heading">
      <div><span className="compare-section-label">Tennis context</span><h2 id="tennis-surface-title">Recorded surface history</h2></div>
      <div className="tennis-surface-tabs" aria-label="Choose a tennis surface">
        {SURFACES.map((item) => <button key={item.key} type="button" aria-pressed={surface === item.key} className={surface === item.key ? "is-active" : ""} onClick={() => onSurfaceChange(item.key)}>{item.label}</button>)}
      </div>
    </div>
    <p className="tennis-surface-intro">Published {comparison.surfaceLabel.toLowerCase()} records for each profile. Raw values lead; within-pack percentiles appear only when published.</p>
    {availableRows.length ? <div className="tennis-surface-grid" role="table" aria-label={`${comparison.surfaceLabel} recorded surface history`}>
      <div className="tennis-surface-row tennis-surface-labels" role="row"><span role="columnheader">Recorded measure</span><span role="columnheader" aria-label={a.name}><span className="tennis-surface-compact-label">Profile A</span><span className="tennis-surface-full-label">{a.name}</span></span><span role="columnheader" aria-label={b.name}><span className="tennis-surface-compact-label">Profile B</span><span className="tennis-surface-full-label">{b.name}</span></span></div>
      {comparison.rows.map((row) => <div className="tennis-surface-row" role="row" key={row.key}>
        <span role="rowheader"><b>{row.label}</b><small>{row.window === "career" ? "Career record" : "Recent record"}</small></span>
        <span role="cell"><Value value={row.a.value} percentile={row.a.percentile} field={row.key} unit={row.unit} /></span>
        <span role="cell"><Value value={row.b.value} percentile={row.b.percentile} field={row.key} unit={row.unit} /></span>
      </div>)}
    </div> : <p className="compare-empty">No published {comparison.surfaceLabel.toLowerCase()} measurements are available for either selected profile.</p>}
    <div className="tennis-surface-meta">
      <p><b>Eligibility:</b> {surfaceEligibility(surface)}</p>
      <details><summary>Exact published eligibility wording</summary>{comparison.entities.a.floors === comparison.entities.b.floors ? <p>{comparison.entities.a.floors || "Not reported"}</p> : <><p><b>{a.name}:</b> {comparison.entities.a.floors || "Not reported"}</p><p><b>{b.name}:</b> {comparison.entities.b.floors || "Not reported"}</p></>}</details>
      <p><b>Published windows:</b> Career: {comparison.comparability.windows.career}. Recent: {comparison.comparability.windows.recent}.</p>
      <p>{comparison.comparability.note} The shared publication date does not mean matching player observation windows; collected history can vary with active period. {comparison.comparability.sameAsOf === false ? "The profiles have different published as-of dates." : ""}</p>
      <p>Published status: {comparison.entities.a.status || "not reported"} for {a.name}; {comparison.entities.b.status || "not reported"} for {b.name}.</p>
      <p>Source date: {aDate && bDate && aDate === bDate ? <time title={aDate}>{shortDate(aDate)}</time> : <>{aDate ? <span title={aDate}>{a.name}: {shortDate(aDate)}</span> : `${a.name}: not reported`}; {bDate ? <span title={bDate}>{b.name}: {shortDate(bDate)}</span> : `${b.name}: not reported`}</>}. <a href={sourceHref} target="_blank" rel="noreferrer">Raw tennis manifest</a></p>
    </div>
  </section>;
}
