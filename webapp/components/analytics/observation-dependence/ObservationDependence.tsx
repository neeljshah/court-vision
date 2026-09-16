import { Figure } from "@/components/analytics/charts/Figure";
import { linear } from "@/components/analytics/charts/scale";
import type { DependenceSide, DependenceSport } from "@/lib/analytics/observationDependence";

const SOURCE = "public/data/showcase/residual_autocorrelation.json";

function sportLabel(sport: string): string {
  if (sport === "mlb") return "MLB";
  if (sport === "soccer_intl") return "International soccer";
  return sport.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function percent(value: number | null): string {
  return value === null ? "Not published" : `${(value * 100).toFixed(1)}%`;
}

function skipped(side: DependenceSide): string {
  return `low rows ${side.skipped.lowN}; flat residuals ${side.skipped.flat}`;
}

function DotStrip({ sport, side }: { sport: string; side: DependenceSide }) {
  const color = side.side === "model" ? "var(--accent)" : "var(--signal)";
  const x = linear(-1, 1, 28, 292);
  return <div className="od-strip" data-side={side.side} data-series-count={side.values.length}>
    <p><span className={`od-key od-key-${side.side}`} />{side.side === "model" ? "Model" : "Market"}: {side.nGames.toLocaleString()} eligible series</p>
    <svg viewBox="0 0 320 112" role="img" aria-label={`${sportLabel(sport)} ${side.side} residual autocorrelation distribution`}>
      <line x1="28" x2="292" y1="80" y2="80" className="od-axis" />
      <line x1={x(0.9)} x2={x(0.9)} y1="12" y2="85" className="od-threshold" />
      {side.values.map((value, index) => <circle key={`${side.side}-${index}`} cx={x(value)} cy={70 - (index % 5) * 11} r="3.4" fill={color} opacity=".8" />)}
      <text x="28" y="103" textAnchor="middle">-1</text><text x={x(0.9)} y="103" textAnchor="middle">0.9</text><text x="292" y="103" textAnchor="middle">1</text>
    </svg>
    <p className="od-strip-meta">Median <span>{side.median?.toFixed(4) ?? "Not published"}</span>; above 0.9 <span>{percent(side.shareAbovePointNine)}</span></p>
  </div>;
}

export function ObservationDependence({ sports, asOf }: { sports: DependenceSport[]; asOf?: string }) {
  return <>
    {sports.map((sport) => <section className="od-sport" key={sport.sport} aria-labelledby={`od-${sport.sport}`}>
      <h2 id={`od-${sport.sport}`}>{sportLabel(sport.sport)}</h2>
      <p className="od-sport-meta">Published corpus: {sport.nRecords?.toLocaleString() ?? "Not published"} ticks across {sport.nSeries?.toLocaleString() ?? "Not published"} candidate series.</p>
      <Figure source={SOURCE} asOf={asOf || "published snapshot"} title={`${sportLabel(sport.sport)} within-game distributions`} subtitle="Each dot is one eligible game-side series. Model and market are separate populations; dots are not paired." verdict="descriptive_only">
        <div className="od-strips">{sport.sides.map((side) => <DotStrip key={side.side} sport={sport.sport} side={side} />)}</div>
      </Figure>
    </section>)}
    <section className="od-summary" aria-labelledby="od-summary-title">
      <h2 id="od-summary-title">Published-series summary</h2>
      <p>Formula: median is the middle value after sorting each side&apos;s published array; share above 0.9 = count(rho &gt; 0.9) / eligible series. Each side remains a separate population.</p>
      <div role="region" aria-label="Observation dependence summary" data-scroll-region className="od-table-wrap">
        <table><thead><tr><th scope="col">Sport</th><th scope="col">Side</th><th scope="col">Eligible series</th><th scope="col">Median autocorr</th><th scope="col">Share above 0.9</th><th scope="col">Skipped</th></tr></thead><tbody>
          {sports.flatMap((sport) => sport.sides.map((side) => <tr key={`${sport.sport}-${side.side}`}><th scope="row">{sportLabel(sport.sport)}</th><td>{side.side === "model" ? "Model" : "Market"}</td><td>{side.nGames.toLocaleString()}</td><td>{side.median?.toFixed(4) ?? "Not published"}</td><td>{percent(side.shareAbovePointNine)}</td><td>{skipped(side)}</td></tr>))}
        </tbody></table>
      </div>
    </section>
  </>;
}
