// PitchRepeatExcessPanel -- renders the novel_pitch_repeat_excess artifact, which publishes
// `panels` rather than the flat `results` list NovelStatPanel understands, so that generic
// renderer shows nothing for it. Reads the committed artifact at build time and prints the
// preregistered claims with their verdicts, the excess tables with their intervals, the
// repeat-versus-switch outcome comparison and the full dropped-pair waterfall. Every row keeps
// its n_pairs and a masked row keeps its count and says why. ASCII source only.
import { readFileSync } from "node:fs";
import { join } from "node:path";

type Pair = [number | null, number | null];
type Cell = {
  cell: string; n_pairs: number; masked?: boolean; mask_reason?: string | null; ci95?: Pair;
  repeat_rate?: number | null; expected_repeat_rate?: number | null; excess?: number | null;
  excludes_zero?: boolean | null;
};
type Diff = {
  cell?: string; n_left: number; n_right: number; rate_left?: number | null;
  rate_right?: number | null; difference?: number | null; ci95?: Pair;
  excludes_zero?: boolean | null; masked?: boolean;
};
type Pooled = { cell: string; difference: number | null; ci95?: Pair; excludes_zero?: boolean | null };
type Outcome = { cells: Diff[]; standardized: Pooled };
type Claim = {
  id: number; claim: string; quantity: string; expected_sign: string; value: number | null;
  ci95?: Pair; excludes_zero?: boolean | null; verdict: string;
};
export type PitchRepeatExcess = {
  verdict?: string;
  preregistered_claims: Claim[];
  panels: {
    overall: { n_pairs: number; cells: Cell[] };
    by_count_class: { n_pairs: number; cells: Cell[]; contrast_ahead_minus_behind: Diff };
    by_count: { n_pairs: number; note?: string; cells: Cell[] };
    by_previous_family: { n_pairs: number; cells: Cell[] };
    outcome_repeat_vs_switch: {
      n_pairs_with_outcome_code: number; n_in_play_pairs: number;
      swing_and_miss: Outcome; called_strike_plus_swing_and_miss: Outcome; weak_contact: Outcome;
    };
    outcome_within_destination_family: { n_pairs_with_outcome_code: number; cells: Diff[]; standardized: Pooled };
    per_pitcher: { n_pitchers: number; floor_pairs_per_pitcher: number; top: Cell[]; bottom: Cell[] };
    truncation_check: { cutoff_game_date: string; n_games: number; n_pairs: number; overall_excess: number | null; whiff_difference_standardized: number | null };
  };
  checks?: Record<string, unknown>;
};

const ARTIFACT = join(process.cwd(), "public", "data", "showcase", "novel_pitch_repeat_excess.json");
const MASKED = "masked";

/** The committed artifact. Build-time read; the component renders values only. */
export function loadPitchRepeatExcess(): PitchRepeatExcess {
  return JSON.parse(readFileSync(ARTIFACT, "utf8")) as PitchRepeatExcess;
}

const count = (n: number) => n.toLocaleString("en-US");
const rate = (v: number | null | undefined) => (v == null ? MASKED : v.toFixed(4));
const signed = (v: number | null | undefined) => (v == null ? MASKED : (v > 0 ? "+" : "") + v.toFixed(4));
const span = (ci?: Pair) => (!ci || ci[0] == null || ci[1] == null ? MASKED : `${ci[0].toFixed(4)} to ${ci[1].toFixed(4)}`);
const flag = (v: boolean | null | undefined) => (v == null ? MASKED : v ? "yes" : "no");
const reason = (cell: Cell) => cell.mask_reason || (cell.masked ? "below the floor" : "");
const excessRow = (cell: Cell) => [cell.cell, count(cell.n_pairs), rate(cell.repeat_rate), rate(cell.expected_repeat_rate), signed(cell.excess), span(cell.ci95), reason(cell) || flag(cell.excludes_zero)];
const diffRow = (row: Diff) => [row.cell || "", count(row.n_left), count(row.n_right), rate(row.rate_left), rate(row.rate_right), signed(row.difference), span(row.ci95), flag(row.excludes_zero)];
const EXCESS_COLUMNS = ["Cell", "Pairs (n)", "Repeat rate", "Expected by own mix", "Excess", "95 percent interval", "Excludes zero"];
const DIFF_COLUMNS = ["Cell", "Repeat (n)", "Switch (n)", "Repeat rate", "Switch rate", "Difference", "95 percent interval", "Excludes zero"];

function Grid({ caption, columns, rows, note }: { caption: string; columns: string[]; rows: string[][]; note?: string }) {
  return (
    <figure className="rp-fig">
      <figcaption>{caption}</figcaption>
      <div className="rp-scroll" tabIndex={0} role="region" aria-label={`${caption} (scrollable table)`} data-scroll-region>
        <table>
          <thead>
            <tr>{columns.map(column => <th key={column}>{column}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row[0]} className={row.includes(MASKED) ? "rp-masked" : undefined}>
                {row.map((value, index) => <td key={columns[index]}>{value}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="rp-scroll-hint">Scroll horizontally for all columns</p>
      {note ? <p className="rp-note">{note}</p> : null}
    </figure>
  );
}

export function PitchRepeatExcessPanel({ artifact = loadPitchRepeatExcess() }: { artifact?: PitchRepeatExcess }) {
  const { overall, by_count_class, by_count, by_previous_family, outcome_repeat_vs_switch, outcome_within_destination_family, per_pitcher, truncation_check } = artifact.panels;
  const checks = (artifact.checks || {}) as Record<string, number | undefined>;
  const outcomes = outcome_repeat_vs_switch;
  const population = `Measured population: ${count(overall.n_pairs)} adjacent pitch pairs over ${count(checks.n_games ?? 0)} games and ${count(checks.n_pitchers ?? 0)} pitchers. A pair is two pitches in a row inside one plate appearance thrown by the same pitcher.`;
  const waterfall = `${count(checks.pitches_in_source ?? 0)} pitches in the source table, ${count(checks.adjacent_pairs ?? 0)} adjacent pairs, ${count(checks.dropped_pitcher_changed_mid_plate_appearance ?? 0)} dropped for a pitcher change mid plate appearance, ${count(checks.dropped_unknown_or_non_pitch_type ?? 0)} dropped for a null or non-pitch type code, ${count(checks.dropped_only_pitch_at_that_count_for_that_pitcher ?? 0)} dropped for having no leave-one-out baseline, ${count(overall.n_pairs)} measured, of which ${count(checks.measured_pairs_without_outcome_code ?? 0)} carry no per-pitch outcome code and sit out the outcome tables.`;

  return (
    <section className="rp" aria-label="Repeat-pitch excess panels">
      <p className="overline">Published panels</p>
      <p className="rp-pop"><b>{population}</b> The baseline is that same pitcher&apos;s own mix at that same count with this pitch left out, so a pitch can never predict itself.</p>
      <p className="rp-pop rp-flow">Coverage: {waterfall}</p>

      <Grid
        caption="1. The three preregistered claims, decided only by whether the interval excludes zero"
        columns={["Claim", "Preregistered direction", "Measured value", "95 percent interval", "Verdict"]}
        rows={artifact.preregistered_claims.map(claim => [`${claim.id}. ${claim.claim}`, claim.expected_sign, signed(claim.value), span(claim.ci95), claim.verdict])}
        note="Written into the producer before the first number was computed. A CONTRADICTED row is published at full size; it is the result, not a failure."
      />

      <Grid
        caption={`2. Repeat-pitch excess by count class -- ${count(by_count_class.n_pairs)} pairs`}
        columns={EXCESS_COLUMNS}
        rows={[...by_count_class.cells.map(excessRow), excessRow({ ...overall.cells[0], cell: "all pairs" })]}
        note={`Pitcher-ahead minus pitcher-behind is ${signed(by_count_class.contrast_ahead_minus_behind.difference)} with interval ${span(by_count_class.contrast_ahead_minus_behind.ci95)}, taken inside the same resample, which is the second preregistered claim.`}
      />

      <Grid
        caption="3. Repeat-pitch excess by the raw pre-pitch count"
        columns={EXCESS_COLUMNS}
        rows={by_count.cells.map(excessRow)}
        note={by_count.note}
      />

      <Grid
        caption="4. Repeat-pitch excess by the family of the previous pitch"
        columns={EXCESS_COLUMNS}
        rows={by_previous_family.cells.map(excessRow)}
        note="A repeat means the same pitch_type code, not the same family; the family here labels the pitch that came first."
      />

      <Grid
        caption={`5. Swings and misses, repeat against switch at the same count -- ${count(outcomes.n_pairs_with_outcome_code)} pairs`}
        columns={DIFF_COLUMNS}
        rows={[...outcomes.swing_and_miss.cells.map(diffRow), [outcomes.swing_and_miss.standardized.cell, "", "", "", "", signed(outcomes.swing_and_miss.standardized.difference), span(outcomes.swing_and_miss.standardized.ci95), flag(outcomes.swing_and_miss.standardized.excludes_zero)]]}
        note="A swing and miss is the outcome code swinging_strike or swinging_strike_blocked. A foul tip is contact and is not counted here. The last row weights each count class by its share of pairs."
      />

      <Grid
        caption="6. Called strikes plus swings and misses, and weak contact in play"
        columns={DIFF_COLUMNS}
        rows={[...outcomes.called_strike_plus_swing_and_miss.cells.map(row => diffRow({ ...row, cell: `called plus missed -- ${row.cell}` })), ...outcomes.weak_contact.cells.map(row => diffRow({ ...row, cell: `weak contact -- ${row.cell}` }))]}
        note={`Weak contact is the share of tracked in-play pitches below 95 mph, over ${count(outcomes.n_in_play_pairs)} in-play pairs. Standardized differences: ${signed(outcomes.called_strike_plus_swing_and_miss.standardized.difference)} (${span(outcomes.called_strike_plus_swing_and_miss.standardized.ci95)}) and ${signed(outcomes.weak_contact.standardized.difference)} (${span(outcomes.weak_contact.standardized.ci95)}).`}
      />

      <Grid
        caption="7. The same swing-and-miss difference inside destination pitch family"
        columns={DIFF_COLUMNS}
        rows={outcome_within_destination_family.cells.map(diffRow)}
        note={`Holding the destination pitch family fixed, so the comparison is not a type-mix artifact. Standardized over these nine cells: ${signed(outcome_within_destination_family.standardized.difference)} (${span(outcome_within_destination_family.standardized.ci95)}).`}
      />

      <p className="rp-pop rp-flow">
        Truncation check: rebuilt on the {count(truncation_check.n_games)} games through {truncation_check.cutoff_game_date} ({count(truncation_check.n_pairs)} pairs), the overall excess is {signed(truncation_check.overall_excess)} and the standardized swing-and-miss difference is {signed(truncation_check.whiff_difference_standardized)}. Per-pitcher rows for the {count(per_pitcher.n_pitchers)} pitchers at or above {count(per_pitcher.floor_pairs_per_pitcher)} pairs are published in the artifact, top {signed(per_pitcher.top[0]?.excess)} and bottom {signed(per_pitcher.bottom[0]?.excess)}.
      </p>

      {artifact.verdict ? (
        <div className="rp-verdict">
          <p className="overline">Verdict</p>
          <p>{artifact.verdict}</p>
        </div>
      ) : null}

      <style>{`
        .rp{margin:22px 0;border:1px solid var(--rule);border-top:3px solid var(--signal);
          border-radius:var(--radius-card);background:var(--paper-raised);padding:18px 20px}
        .rp-pop{font-size:13.5px;line-height:1.6;color:var(--ink-2);margin:8px 0 0}
        .rp-pop b{color:var(--ink)}
        .rp-flow{font-family:var(--font-mono);font-size:11.5px;color:var(--ink-3)}
        .rp-fig{margin:20px 0 0}
        .rp-fig figcaption{font-size:13px;font-weight:600;color:var(--ink);margin-bottom:7px}
        .rp-scroll{overflow-x:auto;border:1px solid var(--rule);border-radius:8px}
        .rp-scroll-hint{display:none}.rp table{width:100%;min-width:720px;border-collapse:collapse;font-size:12.5px}
        .rp th{text-align:left;white-space:nowrap;font-family:var(--font-mono);font-weight:500;font-size:11px;
          letter-spacing:.05em;text-transform:uppercase;color:var(--ink-3);
          padding:8px 12px;border-bottom:1px solid var(--rule-strong);background:var(--paper-tint)}
        .rp td{padding:7px 12px;border-bottom:1px solid var(--rule);color:var(--ink-2);
          font-variant-numeric:tabular-nums;vertical-align:top}
        .rp tbody tr:last-child td{border-bottom:0}
        .rp tr.rp-masked td{color:var(--ink-3);font-style:italic}
        .rp-note{font-size:11.5px;line-height:1.55;color:var(--ink-3);margin-top:6px}
        .rp-verdict{margin-top:22px;padding:14px 16px;background:var(--paper-tint);
          border-left:3px solid var(--signal);border-radius:0 8px 8px 0}
        .rp-verdict p{font-size:13.5px;line-height:1.6;color:var(--ink-2);margin-top:6px}
        @media(max-width:720px){.rp-scroll-hint{display:block;margin:8px 0 0;font-family:var(--font-mono);font-size:12px;color:var(--ink-3)}}
      `}</style>
    </section>
  );
}

export default PitchRepeatExcessPanel;
