import type { NbaFormCoverage } from "@/lib/analytics/nbaFormCoverage";
import { sourceUrl } from "@/lib/analytics/dashboardTypes";

type Props = { coverage?: NbaFormCoverage };

const count = (value: number | null) => value === null ? "Unavailable" : value.toLocaleString("en-US");
const percent = (value: number | null) => value === null ? "Unavailable" : `${(value * 100).toFixed(1)}%`;

export function NbaFormCoveragePanel({ coverage }: Props) {
  if (!coverage) return null;

  const retainedShare = coverage.consistent ? coverage.retainedShare : null;
  const eligibleShare = coverage.consistent ? coverage.eligibleShare : null;
  const excludedBeforeWindow = coverage.consistent ? coverage.excludedBeforeWindow : null;
  const excludedBeforeMover = coverage.consistent ? coverage.excludedBeforeMover : null;

  return <section className="nba-form-coverage" aria-label="NBA form cohort support">
    <header>
      <p className="cv-eyebrow">Cohort support</p>
      <h3>How many player IDs reach each form stage?</h3>
      <p>These are full-source player ID counts. Search and CSV selection do not change them.</p>
    </header>
    <div className="nba-form-coverage-cards">
      <article aria-label="Retained window coverage">
        <h4>Retained window</h4>
        <p className="nba-form-coverage-share"><strong>{percent(retainedShare)}</strong>{" "}<span>of source player IDs</span></p>
        {retainedShare !== null && <div className="nba-form-coverage-track" aria-hidden="true"><span style={{ width: `${retainedShare * 100}%` }} /></div>}
        <dl>
          <div><dt>IDs with a retained window</dt><dd>{count(coverage.retainedPlayers)}</dd></div>
          <div><dt>Source player IDs</dt><dd>{count(coverage.sourcePlayers)}</dd></div>
          <div><dt>IDs without a retained window</dt><dd>{count(excludedBeforeWindow)}</dd></div>
        </dl>
      </article>
      <article aria-label="Eligible mover coverage">
        <h4>Eligible mover</h4>
        <p className="nba-form-coverage-share"><strong>{percent(eligibleShare)}</strong>{" "}<span>of IDs with a retained window</span></p>
        {eligibleShare !== null && <div className="nba-form-coverage-track" aria-hidden="true"><span style={{ width: `${eligibleShare * 100}%` }} /></div>}
        <dl>
          <div><dt>Eligible mover IDs</dt><dd>{count(coverage.eligibleMovers)}</dd></div>
          <div><dt>IDs with a retained window</dt><dd>{count(coverage.retainedPlayers)}</dd></div>
          <div><dt>IDs not mover eligible</dt><dd>{count(excludedBeforeMover)}</dd></div>
        </dl>
      </article>
    </div>
    {!coverage.consistent && <p className="nba-form-coverage-warning">The published cohort counts are missing or do not form a consistent hierarchy. Available counts remain visible; percentages and stage differences are unavailable.</p>}
    <p className="cv-footnote">{count(coverage.pooledWindows)} pooled, overlapping {coverage.windowGames === null ? "windows (window size unavailable)" : `${coverage.windowGames}-game windows`} are not independent player or game samples. {count(coverage.publishedMoverRows)} selected mover rows are shown in the published lists, not the full eligible population.</p>
    <p className="cv-footnote">Pooled seasons: {coverage.seasons.length ? coverage.seasons.join(", ") : "Unavailable"}. Observation start and end dates are not published for this cohort. Qualification floors: {coverage.floors ?? "Unavailable"}.</p>
    <p className="cv-footnote">Form uses a frozen box-score composite, not a prediction or live streak. Raw player IDs may split names with accents upstream.</p>
    <details><summary>Calculation and source fields</summary>
      <p>Retained share = IDs with a retained window / source player IDs. Eligible share = eligible mover IDs / IDs with a retained window. Stage differences subtract the published ID counts.</p>
      <ul>
        <li><code>input_coverage.unique_players</code></li>
        <li><code>input_coverage.players_with_retained_window</code></li>
        <li><code>input_coverage.movers_eligible</code></li>
        <li><code>input_coverage.pooled_windows</code></li>
        <li><code>methodology.window_games</code></li>
        <li><code>methodology.floors</code></li>
        <li><code>methodology.seasons_pooled</code></li>
        <li><code>top_movers_risers</code> and <code>top_movers_fallers</code></li>
      </ul>
    </details>
    <a href={sourceUrl("nba_form_curves")} target="_blank" rel="noreferrer">Inspect the published NBA form source</a>
  </section>;
}
