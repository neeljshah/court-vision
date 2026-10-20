// CalibrationDecomposition -- T2 blocks after the reliability diagram: Brier decomposition table
// (Murphy: reliability, resolution, uncertainty; P4.2) and the sharpness histogram of forecast
// counts per bin with its table view (P4.3). Computed at build time from the published
// calibration_stability.json bins; the published Brier is printed beside the binned total.
import type { ReliabilityBin, ReliabilitySeries } from "@/lib/analytics/calibrationReliability";
import { SERIES_VAR } from "@/lib/palette";

export type Decomposition = { reliability: number; resolution: number; uncertainty: number; total: number; n: number };

/** Binned Murphy decomposition; within-bin variance is not in the bins, so total is approximate. */
export function decompose(bins: ReliabilityBin[]): Decomposition | null {
  const ok = bins.filter((b) => b.n != null && b.meanP != null && b.meanY != null) as
    (ReliabilityBin & { n: number; meanP: number; meanY: number })[];
  const n = ok.reduce((s, b) => s + b.n, 0);
  if (!n) return null;
  const ybar = ok.reduce((s, b) => s + b.n * b.meanY, 0) / n;
  const reliability = ok.reduce((s, b) => s + b.n * (b.meanP - b.meanY) ** 2, 0) / n;
  const resolution = ok.reduce((s, b) => s + b.n * (b.meanY - ybar) ** 2, 0) / n;
  const uncertainty = ybar * (1 - ybar);
  return { reliability, resolution, uncertainty, total: reliability - resolution + uncertainty, n };
}

const SPORT: Record<string, string> = { mlb: "MLB", soccer_intl: "International soccer" };
const f4 = (v: number | null | undefined) => (v == null ? "not published" : v.toFixed(4));
const pct = (v: number | null) => `${Math.round((v ?? 0) * 100)}%`;

export function CalibrationDecomposition({ series }: { series: ReliabilitySeries[] }) {
  return (
    <div className="calibration-table-wrap" role="region" aria-label="Brier decomposition" data-scroll-region tabIndex={0}>
      <table className="calibration-table">
        <caption>Brier decomposition by sport and series (lower Brier is better; uninformative baseline 0.2500)</caption>
        <thead>
          <tr><th>Sport</th><th>Series</th><th>Reliability (lower is better)</th><th>Resolution (higher is better)</th>
            <th>Uncertainty</th><th>Binned total</th><th>Published Brier (lower is better)</th><th>n ticks</th></tr>
        </thead>
        <tbody>
          {series.map((s) => {
            const d = decompose(s.bins);
            return (
              <tr key={`${s.sport}-${s.side}`}>
                <td>{SPORT[s.sport] ?? s.sport}</td><td>{s.side}</td>
                <td>{f4(d?.reliability)}</td><td>{f4(d?.resolution)}</td><td>{f4(d?.uncertainty)}</td>
                <td>{f4(d?.total)}</td><td>{f4(s.diagnostics.brier)}</td><td>{d ? d.n.toLocaleString("en-US") : "--"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Sharpness: forecast counts per probability bin, model and market side by side, one axis. */
export function CalibrationSharpness({ series, sport }: { series: ReliabilitySeries[]; sport: string }) {
  const pair = series.filter((s) => s.sport === sport);
  const bins = pair[0]?.bins ?? [];
  const max = Math.max(1, ...pair.flatMap((s) => s.bins.map((b) => b.n ?? 0)));
  const W = 620, H = 220, L = 56, B = 36, T = 12;
  const bw = (W - L - 8) / Math.max(bins.length, 1);
  const y = (n: number) => T + (H - T - B) * (1 - n / max);
  const label = SPORT[sport] ?? sport;
  return (
    <figure className="cal-hist" style={{ margin: "16px 0 0" }} data-testid={`sharpness-${sport}`}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label} sharpness: forecast counts per probability bin`}>
        <line x1={L} x2={W - 8} y1={H - B} y2={H - B} stroke="var(--rule-strong)" />
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line x1={L} x2={W - 8} y1={y(max * t)} y2={y(max * t)} stroke="var(--rule)" strokeDasharray="2 3" />
            <text x={L - 6} y={y(max * t) + 4} textAnchor="end" fill="currentColor">{Math.round(max * t).toLocaleString("en-US")}</text>
          </g>
        ))}
        {bins.map((b, i) => (
          <text key={i} x={L + i * bw + bw / 2} y={H - B + 16} textAnchor="middle" fill="currentColor">{pct(b.binLo)}</text>
        ))}
        {pair.map((s, k) =>
          s.bins.map((b, i) => {
            const n = b.n ?? 0;
            const w = (bw - 8) / 2;
            return (
              <rect key={`${s.side}-${i}`} x={L + i * bw + 3 + k * (w + 2)} y={y(n)} width={w} height={H - B - y(n)} rx={2}
                fill={s.side === "model" ? SERIES_VAR.model : SERIES_VAR.market}>
                <title>{`${label} ${s.side}: ${n.toLocaleString("en-US")} forecasts in ${pct(b.binLo)} to ${pct(b.binHi)}`}</title>
              </rect>
            );
          }),
        )}
      </svg>
      <figcaption style={{ color: "var(--ink-2)", fontSize: 13 }}>
        {label}. Legend: model = left bar of each pair, market = right bar. Counts are ticks, not games.
      </figcaption>
      <details>
        <summary>Show as table</summary>
        <table className="calibration-table">
          <thead><tr><th>Bin</th>{pair.map((s) => <th key={s.side}>{s.side} forecasts</th>)}</tr></thead>
          <tbody>{bins.map((b, i) => (
            <tr key={i}><td>{pct(b.binLo)} to {pct(b.binHi)}</td>
              {pair.map((s) => <td key={s.side}>{s.bins[i]?.n?.toLocaleString("en-US") ?? "--"}</td>)}</tr>
          ))}</tbody>
        </table>
      </details>
    </figure>
  );
}
