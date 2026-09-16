import Link from "next/link";
import { formatMetric, formatPercentile, metricLabel, metricUnit, type ComparisonComparable, type ComparisonEntity } from "@/lib/analytics/comparisonData";

function displayDate(value?: string): string | undefined {
  return value && /^\d{4}-\d{2}-\d{2}[ T]\d{2}:/.test(value) ? value.slice(0, 10) : value;
}

function PairAction({ entity, comparable, pack }: { entity: ComparisonEntity; comparable: ComparisonComparable; pack: string }) {
  return <Link className="compare-pair-action" href={`/analytics/compare?pack=${pack}&a=${entity.slug}&b=${comparable.slug}`}>Compare with {entity.name}</Link>;
}

export function ProfileHeading({ entity, pack, label, comparables, antipode, hasPackComparables }: { entity: ComparisonEntity; pack: string; label: string; comparables?: ComparisonComparable[]; antipode?: ComparisonComparable; hasPackComparables: boolean }) {
  const asOf = displayDate(entity.asOf);
  return <article className="compare-profile"><span className="compare-profile-label">{label}</span><div className="compare-monogram" aria-hidden="true">{entity.name.slice(0, 1)}</div><h2><Link href={`/analytics/players/${pack}/${entity.slug}`}>{entity.name}</Link></h2><p>{asOf ? `As of ${asOf}` : "No published as-of date"}</p>{entity.floors || entity.status ? <details className="compare-profile-evidence"><summary>Published evidence</summary>{entity.floors ? <p><b>Floors:</b> {entity.floors}</p> : null}{entity.status ? <p><b>Status:</b> {entity.status}</p> : null}</details> : null}<div className="compare-comparables"><span>Closest comparables</span>{comparables?.length ? <ul>{comparables.slice(0, 5).map((item) => <li key={item.slug}><span><Link href={`/analytics/players/${pack}/${item.slug}`}>{item.name}</Link><b>{item.score.toFixed(3)}</b></span><PairAction entity={entity} comparable={item} pack={pack} /></li>)}</ul> : <p>{hasPackComparables ? "No published comparable profiles for this profile." : "This pack has no published comparable profiles."}</p>}{antipode ? <div className="compare-antipode"><span>Most distant profile</span><div><Link href={`/analytics/players/${pack}/${antipode.slug}`}>{antipode.name}</Link><b>{antipode.score.toFixed(3)}</b></div><PairAction entity={entity} comparable={antipode} pack={pack} /></div> : null}</div></article>;
}

export function MetricRow({ field, a, b, showRanks = true, nRanked }: { field: string; a: ComparisonEntity; b: ComparisonEntity; showRanks?: boolean; nRanked?: number }) {
  const unit = metricUnit(field);
  return <tr><th scope="row"><span>{metricLabel(field)}</span>{unit ? <small>{unit}</small> : null}</th><MetricCell value={a.values[field]} percentile={a.percentiles[field]} field={field} showRank={showRanks} nRanked={nRanked} /><MetricCell value={b.values[field]} percentile={b.percentiles[field]} field={field} showRank={showRanks} nRanked={nRanked} /></tr>;
}

function MetricCell({ value, percentile, field, showRank, nRanked }: { value: unknown; percentile: unknown; field: string; showRank: boolean; nRanked?: number }) {
  const raw = typeof value === "number" && Number.isFinite(value);
  const rank = typeof percentile === "number" && Number.isFinite(percentile) && percentile >= 0 && percentile <= 100 ? percentile : undefined;
  const formattedRank = formatPercentile(percentile);
  const ranked = showRank && raw && rank !== undefined && nRanked !== undefined;
  return <td><strong>{formatMetric(value, field)}</strong>{ranked ? <><span className="compare-rank">{formattedRank}</span><small className="compare-rank-context">Ranked among {nRanked} profiles</small><span className="compare-bar" role="img" aria-label={`${formattedRank} visual bar`}><i aria-hidden="true" style={{ width: `${rank}%` }} /></span></> : showRank ? <span className="compare-rank">Not ranked</span> : null}</td>;
}
