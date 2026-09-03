# G147 coverage-bar adjudication -- required reproduction stop

**Verdict: NOT VALIDATED.** This is an adjudication evidence row, not a
threshold, harness, coordinate-contract, rung-ladder, or verdict change. The
specified arithmetic that can be reproduced is below. The required per-table
decoded-frame coverage column cannot be produced honestly for every current
eligible tennis table, so the G147 stop condition applies: no options are
advanced and no re-score is made.

## Reproduced facts

The G34 retained per-sheet tally is 125 RALLY labels out of 300 sampled frames.
Recomputing the share gives `125 / 300 = 0.4166666667`; the ordinary two-sided
Wilson interval at `z = 1.959963984540054` is `[0.3622760917, 0.4731644035]`.
This reproduces G34's displayed 0.4167 and `[0.362, 0.473]` from
[`g34_view_share_and_denominator_2026-09-02.md`](g34_view_share_and_denominator_2026-09-02.md).

The untouched harness still declares tennis `coverage_min = 0.90` in
[`tracking_harness.py`](../../../scripts/platformkit/tracking_harness.py), and
sets `n_frames` from the distinct frames already present in the table. No
constant, report, prior verdict, coordinate declaration, or rung was edited.

The four retained G34 legacy tables were independently re-read on the pod.
Their exact frame bounds, numerator, stride-3 comparator, and recomputed
ratios are committed in
[`g147_coverage/g34_legacy_reproduction.csv`](g147_coverage/g34_legacy_reproduction.csv).
They reproduce the stated inflation factors: tennis_02 4.9001x, tennis_03
2.7706x, tennis_04 2.5289x, and tennis_05 2.7377x. Their current-harness
coverage versus the retained stride-3 scope is respectively 0.151205 vs
0.030858, 0.439269 vs 0.158544, 0.599894 vs 0.237216, and 0.328399 vs
0.119955. The lower right-hand value is a harder measurement, never a way to
manufacture a pass.

The persistent, append-only pod ledger at census time contains **39 tennis
rows and 0 passes** (12 tracked, 15 thin, 9 timeout, and 3 corrupt). This
reproduces the specification's daemon statement; the transient daemon log's
36 outcome lines are not substituted for that ledger.

## Required current-table census and the stop

At `2026-09-03T03:10:10Z`, the read-only canonical table census finds **8
gate-eligible tennis tables** under the existing G107 prerequisites: at least
30 frames, declared `court_feet`, required player fields, and a unique positive
modal stride. This is a fresh count; it is not the older seven-table G109
snapshot. The census was taken from
`data/tracking/*/tracking_data.csv` and each table appears once.

[`g147_coverage/eligible_tennis_source_frame_probe.csv`](g147_coverage/eligible_tennis_source_frame_probe.csv)
names every one of the eight. It intentionally does **not** claim its
`candidate_full_source_coverage` column is the required decoded-frame metric:

- Each output table has a discontiguous emitted-frame scope (9 to 121 runs at
  a gap greater than two modal strides). A min/max span would count arbitrary
  gaps; a whole-source count would count frames outside an unrecorded selected
  scope. Neither is the table's actual decoder opportunity set.
- The fast `ffprobe` `stream=nb_frames` field in the artifact is therefore
  retained only as a diagnostic candidate. It is not substituted for the
  `-count_frames` decoder-derived denominator defined by G139. Bounded
  `-count_frames` reads did not finish, and no background process was created
  or polled.
- `tennis_08` is a direct source/table mismatch: the current table reaches
  frame 59,998, the retained source metadata reports 24,055 frames, and the
  append-only ledger already records `emitted frame index outside decoded
  range: 24290`. Its candidate number cannot be promoted to a corrected
  coverage result.

Thus the required second coverage column is **NOT VERIFIED for 8/8 tables**.
The candidate column is preserved solely to show direction: every candidate is
lower than the harness value. It is not a corrected score, a revised gate
verdict, or an input to any durable quality decision.

Because this required arithmetic does not reproduce to the verifier standard,
G147's instruction to “say so and stop” controls. Sections (c) and (d) of the
specification are deliberately not executed: laying out option consequences or
cross-sport changes after an unverified denominator would be an adjudication
based on an unsupported metric. The orchestrator must obtain a source-scope
decoder manifest before reopening that decision.

## Verifier-contract self-check

### A

- **A1:** No code was added or changed, so no new per-file test exists.
- **A2:** Recomputed the rally share/Wilson interval and all four G34 legacy
  row arithmetic from the retained source tables; recomputed the persistent
  ledger tally by parsing JSON records, not the transient log.
- **A3:** No renders apply to this exhaustive table/ledger census. The G34
  rally sample's 12 sheets are evenly distributed, as recorded in G34; no new
  visual claim is made.
- **A4:** The current census has eight distinct source-table directories. The
  ledger count uses 39 physical tennis records and reports pass count
  separately.
- **A5:** Evidence only; no production field, schema, or reader changed.
- **A6:** This lane makes an explicit-path evidence commit in its worktree; it
  does not archive-land, deploy, or alter pod state. The orchestrator owns any
  later adjudication landing.
- **A7:** At this self-check, every repository evidence path named by this memo
  exists: this memo; both `g147_coverage/` CSVs; G34; G107; G109; G131; G139;
  the verifier contract; and the untouched harness source.

### B

- **B1:** Clear. All eight eligible tables are named. The unverified set is
  8/8, not a post-result exclusion.
- **B2-B6:** Clear. No schema, field, reader, gate, claim path, deployment,
  module, import, or test changed.
- **B7:** Clear. The metric census is exhaustive, and no head-slice render
  evidence is used.
- **B8:** Clear. No fitted residual is presented.
- **B9:** Clear. Units are distinct source-table directories and physical
  ledger records, not recycled IDs.
- **B10:** Clear. The tennis 0.90 coverage bar and every other threshold are
  untouched.

## NOT VERIFIED

- A decoder-derived coverage denominator for any of the eight current eligible
  tennis tables.
- A valid source/table pairing for `tennis_08`.
- The four adjudication options and their publication consequences, because the
  specification's required metric stop occurred first.
- Cross-sport denominator-inflation numbers beyond the retained G34 evidence,
  for the same reason.
- Any test suite: no code was changed; no full suite was run.
