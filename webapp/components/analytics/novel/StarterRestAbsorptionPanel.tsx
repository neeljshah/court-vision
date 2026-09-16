// StarterRestAbsorptionPanel renders the committed starter-rest artifact at build time.
import { readFileSync } from "node:fs";
import { join } from "node:path";

type Pair = [number | null, number | null];
type Cell = {
  cell: string; n_starts: number; win_frequency?: number | null; ci95?: Pair;
  mean_reference_forecast?: number | null; gap_observed_minus_reference?: number | null;
  gap_ci95?: Pair; masked?: boolean; mask_reason?: string | null; gap_excludes_zero?: boolean | null;
};
type Season = { season: string; n_starts: number; cells: Cell[]; short_minus_long: number | null };
type Checks = {
  label_crosscheck_source: string; label_crosscheck_n: number; label_agreement: number;
  tied_final_scores: number; starts_dropped_missing_starter: number;
  starts_dropped_no_prior_start_in_season: number; max_rest_days_observed: number;
  games_with_starters_and_reference: number; seasons: string[];
};
export type StarterRestAbsorption = {
  verdict: string; is_honest_null: boolean;
  method: { mask_rule: string }; panels: {
    rest_buckets: { n_starts: number; cells: Cell[] };
    contrast_vs_standard: (Cell & { delta_vs_standard?: number | null; excludes_zero?: boolean | null })[];
    by_forecast_band: { n_starts: number; note?: string; cells: Cell[] };
    season_stability: Season[];
    doubleheader_nightcap: { n_games: number; note?: string; cells: Cell[] };
  }; checks: Checks;
};

const ARTIFACT = join(process.cwd(), "public", "data", "showcase", "novel_starter_rest_absorption.json");
const MASKED = "masked";

/** The committed artifact. Build-time read; the component renders values only. */
export function loadStarterRestAbsorption(): StarterRestAbsorption {
  return JSON.parse(readFileSync(ARTIFACT, "utf8")) as StarterRestAbsorption;
}

const count = (value: number) => value.toLocaleString("en-US");
const rate = (value: number | null | undefined) => value == null ? MASKED : value.toFixed(4);
const span = (interval?: Pair) => !interval || interval[0] == null || interval[1] == null
  ? MASKED : `${interval[0].toFixed(4)} to ${interval[1].toFixed(4)}`;
const maskedReason = (cell: Cell, maskRule: string) => cell.masked ? cell.mask_reason || maskRule : "no";
const excludesZero = (value: boolean | null | undefined) => value == null ? MASKED : value ? "yes" : "no";
const sign = (value: number | null) => value == null ? MASKED : value > 0 ? "positive" : value < 0 ? "negative" : "zero";
const seasonCell = (cell: Cell | undefined, maskRule: string) => cell
  ? `${count(cell.n_starts)}; ${rate(cell.win_frequency)}; ${span(cell.ci95)}${cell.masked ? `; ${maskedReason(cell, maskRule)}` : ""}`
  : MASKED;

function Grid({ caption, columns, rows, note }: { caption: string; columns: string[]; rows: string[][]; note?: string }) {
  return <figure className="ra-fig">
    <figcaption>{caption}</figcaption>
    <div className="ra-scroll" tabIndex={0} role="region" aria-label={`${caption} (scrollable table)`}>
      <table><thead><tr>{columns.map(column => <th key={column}>{column}</th>)}</tr></thead>
        <tbody>{rows.map(row => <tr key={row[0]} className={row.includes(MASKED) ? "ra-masked" : undefined}>
          {row.map((value, index) => <td key={columns[index]}>{value}</td>)}
        </tr>)}</tbody>
      </table>
    </div>
    {note ? <p className="ra-note">{note}</p> : null}
  </figure>;
}

export function StarterRestAbsorptionPanel({ artifact = loadStarterRestAbsorption() }: { artifact?: StarterRestAbsorption }) {
  const { rest_buckets, contrast_vs_standard, by_forecast_band, season_stability, doubleheader_nightcap } = artifact.panels;
  const { checks, method } = artifact;
  const standard = rest_buckets.cells.find(cell => cell.cell === "4");
  const standardRest = standard ? `${standard.cell} days` : "standard rest";
  const figure = (number: number, caption: string, n: number, unit: string) => `${number}. ${caption} -- ${count(n)} ${unit}`;
  const commonColumns = ["Rest cell", "Starts (n)", "Win frequency", "95 percent interval", "Mean reference forecast", "Observed minus reference", "95 percent interval", "Masked"];
  const commonRow = (cell: Cell) => [cell.cell, count(cell.n_starts), rate(cell.win_frequency), span(cell.ci95), rate(cell.mean_reference_forecast), rate(cell.gap_observed_minus_reference), span(cell.gap_ci95), maskedReason(cell, method.mask_rule)];

  return <section className="ra" aria-label="Starter rest absorption panels">
    <p className="overline">Published panels</p>
    <p className="ra-pop"><b>{count(rest_buckets.n_starts)} team-starts across {count(checks.seasons.length)} seasons ({checks.seasons.join(", ")}).</b></p>
    <p className="ra-pop">{count(checks.games_with_starters_and_reference)} games with recorded starters and a recorded closing reference forecast.</p>

    {artifact.is_honest_null ? <div className="ra-verdict"><p className="overline">Honest null</p><p>{artifact.verdict}</p></div> : null}

    <Grid
      caption={figure(1, "Win frequency by days of rest", rest_buckets.n_starts, "team-starts")}
      columns={commonColumns}
      rows={rest_buckets.cells.map(commonRow)}
      note="Each row reports the team-start count, observed frequency, its game-cluster interval, the mean recorded reference forecast, and observed minus reference with its interval."
    />
    <Grid
      caption={figure(2, `Contrast against standard ${standardRest} of rest`, rest_buckets.n_starts, "team-starts")}
      columns={["Rest cell", "Starts (n)", `Difference vs ${standardRest}`, "95 percent interval", "Excludes zero", "Masked"]}
      rows={contrast_vs_standard.map(cell => [cell.cell, count(cell.n_starts), rate(cell.delta_vs_standard), span(cell.ci95), excludesZero(cell.excludes_zero), maskedReason(cell, method.mask_rule)])}
      note={standard ? `Each difference is paired against the ${standard.cell}-day rest cell on the same bootstrap resample.` : undefined}
    />
    <Grid
      caption={figure(3, "Observed frequency minus reference forecast by forecast band", by_forecast_band.n_starts, "team-starts")}
      columns={commonColumns}
      rows={by_forecast_band.cells.map(commonRow)}
      note={by_forecast_band.note}
    />
    <Grid
      caption={figure(4, "Season stability of the short-rest minus long-rest gradient", rest_buckets.n_starts, "team-starts")}
      columns={["Season", "Starts (n)", "Short rest: n; frequency; interval", "Long rest: n; frequency; interval", "Gradient", "Gradient sign"]}
      rows={season_stability.map(row => [row.season, count(row.n_starts), seasonCell(row.cells[0], method.mask_rule), seasonCell(row.cells[1], method.mask_rule), rate(row.short_minus_long), sign(row.short_minus_long)])}
      note="The gradient is short rest minus long rest within each published season."
    />
    {doubleheader_nightcap.cells.length ? <Grid
      caption={figure(5, "Doubleheader nightcap against first game", doubleheader_nightcap.n_games, "games")}
      columns={["Schedule slot", "Games (n)", "Home win frequency", "95 percent interval", "Mean reference forecast", "Observed minus reference", "95 percent interval", "Masked"]}
      rows={doubleheader_nightcap.cells.map(commonRow)}
      note={doubleheader_nightcap.note}
    /> : <p className="ra-note">The doubleheader nightcap slot had no support.</p>}

    <details className="ra-checks"><summary>Checks</summary><ul>
      <li>Label cross-check: {checks.label_crosscheck_source} ({count(checks.label_crosscheck_n)} games).</li>
      <li>Label agreement: {rate(checks.label_agreement)}.</li>
      <li>Tied finals: {count(checks.tied_final_scores)}.</li>
      <li>Starts dropped for missing starter: {count(checks.starts_dropped_missing_starter)}.</li>
      <li>Starts dropped for no prior start: {count(checks.starts_dropped_no_prior_start_in_season)}.</li>
      <li>Maximum observed rest: {count(checks.max_rest_days_observed)} days.</li>
    </ul></details>

    <style>{`
      .ra{margin:22px 0;border:1px solid var(--rule);border-top:3px solid var(--signal);border-radius:var(--radius-card);background:var(--paper-raised);padding:18px 20px}
      .ra-pop{font-size:13.5px;line-height:1.6;color:var(--ink-2);margin:8px 0 0}.ra-pop b{color:var(--ink)}.ra-fig{margin:20px 0 0}.ra-fig figcaption{font-size:13px;font-weight:600;color:var(--ink);margin-bottom:7px}.ra-scroll{overflow-x:auto;border:1px solid var(--rule);border-radius:8px}.ra table{width:100%;border-collapse:collapse;font-size:12.5px}.ra th{text-align:left;white-space:nowrap;font-family:var(--font-mono);font-weight:500;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-3);padding:8px 12px;border-bottom:1px solid var(--rule-strong);background:var(--paper-tint)}.ra td{padding:7px 12px;border-bottom:1px solid var(--rule);color:var(--ink-2);font-variant-numeric:tabular-nums;vertical-align:top}.ra tbody tr:last-child td{border-bottom:0}.ra tr.ra-masked td{color:var(--ink-3);font-style:italic}.ra-note{font-size:11.5px;line-height:1.55;color:var(--ink-3);margin-top:6px}.ra-verdict{margin-top:22px;padding:14px 16px;background:var(--paper-tint);border-left:3px solid var(--signal);border-radius:0 8px 8px 0}.ra-verdict p{font-size:13.5px;line-height:1.6;color:var(--ink-2);margin-top:6px}.ra-checks{margin-top:20px;padding-top:12px;border-top:1px solid var(--rule);font-size:12px;color:var(--ink-2)}.ra-checks summary{cursor:pointer;font-family:var(--font-mono);font-size:11px;font-weight:500;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-3)}.ra-checks ul{margin:8px 0 0 18px}.ra-checks li{margin:3px 0}
    `}</style>
  </section>;
}

export default StarterRestAbsorptionPanel;
