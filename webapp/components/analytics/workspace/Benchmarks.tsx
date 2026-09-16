import { humanize, number, type DashboardData, type Sport } from "@/lib/analytics/dashboardTypes";
import { Empty, Panel } from "./Primitives";

export function WalkForward({ data }: { data: DashboardData["walkForward"] }) {
  return <Panel title="Basketball: performance across time splits" eyebrow="Published walk-forward evaluation" source="forecaster/winprob_walk_forward_results">
    <div className="cv-fold-intro"><div className="cv-coverage-stats"><div className="cv-big-number">{(data.acc_mean * 100).toFixed(1)}%<span>mean fold accuracy</span></div><div className="cv-big-number">{data.brier_mean.toFixed(3)}<span>mean fold Brier</span></div></div><p className="cv-muted">Seasons {data.seasons.join(" and ")}. Each fold trains on an earlier portion of the corpus. These are the recorded evaluation results, separate from the in-game market comparison.</p></div>
    <div className="cv-fold-grid">{data.folds.map(f => <div key={f.fold}><div className="cv-chart-label"><strong>Fold {f.fold}</strong><span>{number(f.n_val)} validation rows</span></div><div className="cv-bar-row"><span>Accuracy</span><div className="cv-track"><i className="cv-bar cv-model" style={{ width: `${f.acc * 100}%` }} /></div><b>{(f.acc * 100).toFixed(1)}%</b></div><div className="cv-fold-details"><span>Brier <b>{f.brier.toFixed(4)}</b></span><span>Training rows <b>{number(f.n_train)}</b></span></div></div>)}</div>
    <p className="cv-footnote">Accuracy bars use a 0-100% axis. Means are across the published folds. These scores do not imply equivalent accuracy for a future game or current live performance.</p>
  </Panel>;
}
export function Benchmarks({ data, sport }: { data: DashboardData; sport: Sport }) {
  const rows = data.benchmarks.filter(r => sport === "all" || r.sport === sport || r.sport.startsWith(`${sport}_`));
  return <div className="cv-benchmarks">{(sport === "all" || sport === "nba") && <WalkForward data={data.walkForward} />}
    <Panel title="The cross-sport evaluation scoreboard" eyebrow={`${rows.length} published comparison rows`} source="cross_sport_scoreboard">
      <p className="cv-muted">Compare checkpoints within the same sport and metric. The source verdict and paired delta are reproduced verbatim; Brier and CRPS have different units and must not be pooled.</p>
      {rows.length ? <div className="cv-table-scroll" tabIndex={0} role="region" aria-label="Scrollable benchmark table"><table className="cv-benchmark-table"><caption className="sr-only">Published cross-sport benchmark deltas and confidence intervals</caption><thead><tr><th>Sport / metric</th><th>Checkpoint</th><th>n</th><th>Paired delta</th><th>95% interval</th><th>Recorded verdict</th></tr></thead><tbody>{rows.map((r, i) => <tr key={i}><td><strong>{humanize(r.sport)}</strong><span>{r.market}</span></td><td>{humanize(r.checkpoint).replace(/\|/g, " / ")}</td><td>{number(r.n)}</td><td>{r.paired_delta_mean.toFixed(4)}</td><td className="cv-ci">[{r.paired_delta_95ci[0].toFixed(4)}, {r.paired_delta_95ci[1].toFixed(4)}]</td><td><span className="cv-badge">{r.verdict.replace(/_/g, " ")}</span></td></tr>)}</tbody></table></div> : <Empty>No benchmark rows for this sport in this published scoreboard.</Empty>}
      <p className="cv-footnote">July 22, 2026 snapshot. Delta direction follows the original artifact; interpret it with the recorded verdict, not color alone. For NBA Brier, the negative Q1 delta is recorded as MARKET_SHARPER_PROVISIONAL. A confidence interval excluding zero does not override a source verdict of UNDERPOWERED.</p>
    </Panel>
  </div>;
}
