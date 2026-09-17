// RestAsymmetryPanel -- renders the novel_rest_asymmetry artifact, which publishes
// `panels` rather than the flat `results` list NovelStatPanel understands, so that
// generic renderer shows nothing for it. Reads the committed artifact at build time
// and prints all five panels as explicit tables: every row keeps its n_games, a
// masked row keeps its count and says why, and the two populations are labelled
// apart (the four-season schedule corpus and the single-season priced subset) so a
// reader never carries a number from one into the other. ASCII source only.
import { readFileSync } from "node:fs";
import { join } from "node:path";

type Pair = [number | null, number | null];
type Cell = {
  cell: string; n_games: number; masked?: boolean; mask_reason?: string | null; ci95?: Pair;
  home_win_frequency?: number | null; delta_vs_equal?: number | null; excludes_zero?: boolean | null;
  mean_market_forecast?: number | null; gap_observed_minus_market?: number | null;
};
type Season = { season: string; n_games: number; cells: Cell[]; home_more_minus_away_more: number | null };
export type RestAsymmetry = {
  verdict?: string;
  panels: {
    rest_differential: { n_games: number; cells: Cell[] };
    contrast_vs_equal_rest: Cell[];
    symmetric_congestion: { n_games: number; note?: string; cells: Cell[] };
    season_stability: Season[];
    market_residual: { n_games: number; seasons: string[]; cells: Cell[] };
  };
  checks?: Record<string, unknown>;
};

const ARTIFACT = join(process.cwd(), "public", "data", "showcase", "novel_rest_asymmetry.json");
const MASKED = "masked";

/** The committed artifact. Build-time read; the component renders values only. */
export function loadRestAsymmetry(): RestAsymmetry {
  return JSON.parse(readFileSync(ARTIFACT, "utf8")) as RestAsymmetry;
}

const count = (n: number) => n.toLocaleString("en-US");
const rate = (v: number | null | undefined) => (v == null ? MASKED : v.toFixed(4));
const span = (ci?: Pair) => (!ci || ci[0] == null || ci[1] == null ? MASKED : `${ci[0].toFixed(4)} to ${ci[1].toFixed(4)}`);
const width = (ci?: Pair) => (!ci || ci[0] == null || ci[1] == null ? MASKED : (ci[1] - ci[0]).toFixed(4));
const reason = (cell: Cell) => cell.mask_reason || (cell.masked ? "below the floor of 30 games" : "");
const flag = (v: boolean | null | undefined) => (v == null ? MASKED : v ? "yes" : "no");
const seasonRate = (row: Season, index: number) => `${rate(row.cells[index]?.home_win_frequency)} (${count(row.cells[index]?.n_games ?? 0)})`;

function Grid({ caption, columns, rows, note }: { caption: string; columns: string[]; rows: string[][]; note?: string }) {
  return (
    <figure className="ra-fig">
      <figcaption>{caption}</figcaption>
      <div className="ra-scroll" tabIndex={0} role="region" aria-label={`${caption} (scrollable table)`} data-scroll-region>
        <table>
          <thead>
            <tr>{columns.map(column => <th key={column}>{column}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row[0]} className={row.includes(MASKED) ? "ra-masked" : undefined}>
                {row.map((value, index) => <td key={columns[index]}>{value}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="ra-scroll-hint">Scroll horizontally for all columns</p>
      {note ? <p className="ra-note">{note}</p> : null}
    </figure>
  );
}

export function RestAsymmetryPanel({ artifact = loadRestAsymmetry() }: { artifact?: RestAsymmetry }) {
  const { rest_differential, contrast_vs_equal_rest, symmetric_congestion, season_stability, market_residual } = artifact.panels;
  const checks = (artifact.checks || {}) as Record<string, number | undefined>;
  const schedule = `Schedule population: ${count(rest_differential.n_games)} games over ${count(season_stability.length)} seasons (${season_stability.map(row => row.season).join(", ")}).`;
  const priced = `Priced population: ${count(market_residual.n_games)} games, ${market_residual.seasons.join(", ")} only. It is a subset of the schedule population and is the only population with a recorded reference forecast.`;
  const waterfall = `${count(checks.games_in_source ?? 0)} games in the source table, ${count(checks.dropped_games_missing_rest ?? 0)} dropped for a missing rest day, ${count(checks.dropped_games_missing_outcome ?? 0)} dropped for a missing outcome, ${count(rest_differential.n_games)} measured, ${count(market_residual.n_games)} of those carrying a recorded pregame reference forecast without a quote timestamp.`;

  return (
    <section className="ra" aria-label="Rest asymmetry panels">
      <p className="overline">Published panels</p>
      <p className="ra-pop"><b>{schedule}</b> {priced}</p>
      <p className="ra-pop ra-flow">Coverage: {waterfall}</p>

      <Grid
        caption={`1. Home win frequency by rest differential -- ${count(rest_differential.n_games)} games`}
        columns={["Rest cell", "Games (n)", "Home win frequency", "95 percent interval", "Masked"]}
        rows={rest_differential.cells.map(cell => [cell.cell, count(cell.n_games), rate(cell.home_win_frequency), span(cell.ci95), reason(cell) || "no"])}
        note="Schedule population. A masked row keeps its count and publishes no frequency."
      />

      <Grid
        caption="2. Each rest cell against the equal-rest cell"
        columns={["Rest cell", "Games (n)", "Difference vs equal", "95 percent interval", "Excludes zero"]}
        rows={contrast_vs_equal_rest.map(cell => [cell.cell, count(cell.n_games), rate(cell.delta_vs_equal), span(cell.ci95), flag(cell.excludes_zero)])}
        note="A difference between two separate groups of games, taken inside every bootstrap replicate; a row is masked when either side of the difference is below the floor."
      />

      <Grid
        caption={`3. Symmetric congestion at an equal rest differential -- ${count(symmetric_congestion.n_games)} games`}
        columns={["Congestion state", "Games (n)", "Home win frequency", "95 percent interval", "Masked"]}
        rows={symmetric_congestion.cells.map(cell => [cell.cell, count(cell.n_games), rate(cell.home_win_frequency), span(cell.ci95), reason(cell) || "no"])}
        note={`${symmetric_congestion.note || ""} Similar observed shares here do not establish absence of fatigue.`}
      />

      <Grid
        caption="4. Season stability of the rest gradient"
        columns={["Season", "Games (n)", "Away rested more: freq (n)", "Equal: freq (n)", "Home rested more: freq (n)", "Home-more minus away-more"]}
        rows={season_stability.map(row => [row.season, count(row.n_games), seasonRate(row, 0), seasonRate(row, 1), seasonRate(row, 2), rate(row.home_more_minus_away_more)])}
        note="Schedule population, split by season. The pooled gradient is an average over these four rows."
      />

      <Grid
        caption={`5. Observed frequency minus the recorded reference forecast -- ${count(market_residual.n_games)} games, ${market_residual.seasons.join(", ")} only`}
        columns={["Rest cell", "Games (n)", "Mean reference forecast", "Home win frequency", "Gap", "95 percent interval", "Interval width"]}
        rows={market_residual.cells.map(cell => [cell.cell, count(cell.n_games), rate(cell.mean_market_forecast), rate(cell.home_win_frequency), rate(cell.gap_observed_minus_market), span(cell.ci95), width(cell.ci95)])}
        note="Priced population only. The reference forecast is the devigged recorded moneyline pair; the source table carries no quote timestamp."
      />

      {artifact.verdict ? (
        <div className="ra-verdict">
          <p className="overline">Verdict</p>
          <p>{artifact.verdict}</p>
        </div>
      ) : null}

      <style>{`
        .ra{margin:22px 0;border:1px solid var(--rule);border-top:3px solid var(--signal);
          border-radius:var(--radius-card);background:var(--paper-raised);padding:18px 20px}
        .ra-pop{font-size:13.5px;line-height:1.6;color:var(--ink-2);margin:8px 0 0}
        .ra-pop b{color:var(--ink)}
        .ra-flow{font-family:var(--font-mono);font-size:11.5px;color:var(--ink-3)}
        .ra-fig{margin:20px 0 0}
        .ra-fig figcaption{font-size:13px;font-weight:600;color:var(--ink);margin-bottom:7px}
        .ra-scroll{overflow-x:auto;border:1px solid var(--rule);border-radius:8px}
        .ra-scroll-hint{display:none}.ra table{width:100%;min-width:720px;border-collapse:collapse;font-size:12.5px}
        .ra th{text-align:left;white-space:nowrap;font-family:var(--font-mono);font-weight:500;font-size:11px;
          letter-spacing:.05em;text-transform:uppercase;color:var(--ink-3);
          padding:8px 12px;border-bottom:1px solid var(--rule-strong);background:var(--paper-tint)}
        .ra td{padding:7px 12px;border-bottom:1px solid var(--rule);color:var(--ink-2);
          font-variant-numeric:tabular-nums;vertical-align:top}
        .ra tbody tr:last-child td{border-bottom:0}
        .ra tr.ra-masked td{color:var(--ink-3);font-style:italic}
        .ra-note{font-size:11.5px;line-height:1.55;color:var(--ink-3);margin-top:6px}
        .ra-verdict{margin-top:22px;padding:14px 16px;background:var(--paper-tint);
          border-left:3px solid var(--signal);border-radius:0 8px 8px 0}
        .ra-verdict p{font-size:13.5px;line-height:1.6;color:var(--ink-2);margin-top:6px}
        @media(max-width:720px){.ra-scroll-hint{display:block;margin:8px 0 0;font-family:var(--font-mono);font-size:12px;color:var(--ink-3)}}
      `}</style>
    </section>
  );
}

export default RestAsymmetryPanel;
