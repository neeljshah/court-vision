# G131: jump-statistic policy attempt 2

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including section A
(especially A7) and section B. Verdict: **NOT VALIDATED**. This is a
read-only point-in-time census. It does not modify `tracking_harness.py`, a
bar, a verdict, the coordinate contract, a pod file, or a pod process.

## Current eligible-table census and table list

At **2026-09-02T23:36:56Z to 2026-09-02T23:37:03Z**, one read-only scan of
the canonical pod glob
`/workspace/nba-ai-system/data/tracking/*/tracking_data.csv` read **203
distinct source-table directories**. The unit is one directory, not a ledger
outcome, frame, track, or artifact copy.

**8 distinct tables reach the jump statistic.** This is below G131's fixed
minimum of 10, so step 2 was not run.

| Table | Canonical pod path |
|---|---|
| `g89_tennis_09` | `/workspace/nba-ai-system/data/tracking/g89_tennis_09/tracking_data.csv` |
| `g89_tennis_10` | `/workspace/nba-ai-system/data/tracking/g89_tennis_10/tracking_data.csv` |
| `g89_tennis_nyYk2nPZAwY_720p` | `/workspace/nba-ai-system/data/tracking/g89_tennis_nyYk2nPZAwY_720p/tracking_data.csv` |
| `tennis_06` | `/workspace/nba-ai-system/data/tracking/tennis_06/tracking_data.csv` |
| `tennis_07` | `/workspace/nba-ai-system/data/tracking/tennis_07/tracking_data.csv` |
| `tennis_08` | `/workspace/nba-ai-system/data/tracking/tennis_08/tracking_data.csv` |
| `tennis_3x3eEWCZmWQ` | `/workspace/nba-ai-system/data/tracking/tennis_3x3eEWCZmWQ/tracking_data.csv` |
| `tennis_nyYk2nPZAwY` | `/workspace/nba-ai-system/data/tracking/tennis_nyYk2nPZAwY/tracking_data.csv` |

The complete per-table capture, including the deterministic exclusion reason,
row/frame counts, modal-stride inputs for eligible paths, and input SHA-256,
is [current_jump_gate_census.json](g131_policy2/current_jump_gate_census.json)
(artifact SHA-256
`98B17A218168566A35BD5B9C015B2D35ACFD67384A77BE4FA8F5471040BA27DD`).

## Step 1 result: stop below the fixed gate

G107 stopped at 6 eligible tables and G109 later counted 8 of 196. This fresh
snapshot still has **8**, now out of 203. It is therefore not permitted to
score C5 or any other policy candidate, report candidate verdict impact, or
make a recommendation. No known-defect scoring was run because that belongs
only to G131 step 2 after the denominator reaches 10.

The census applies G107's pre-registered definition before any statistic or
verdict: at least 30 distinct frames; every row declared `court_feet`; usable
player `track_id`, `frame`, `x`, and `y`; and a unique positive modal
same-track frame stride with at least one pair at that stride. The historical
`g89_tennis_*` directory naming is routed as tennis, as in G107/G109. No
displacement, candidate outcome, or present/past harness verdict participates
in eligibility.

For context only, the complete 203-table classification has 135
not-all-`court_feet`, 50 missing-required-column, 7 empty, 1 insufficient-frame,
2 unknown-sport, and 8 eligible records. Two additional distinct canonical
source-table directories would have to satisfy the unchanged pre-registered
requirements before a policy measurement can begin. That could occur through
ordinary corpus growth or a valid future upstream output; it cannot be reached
by counting one table twice or by moving a bar.

## G127 overlap settled by measurement

The five distinct current paths represented by G127's seven
`jump_gate_eligible=true` historical outcomes are `tennis_06`, `tennis_07`,
`tennis_08`, `tennis_3x3eEWCZmWQ`, and `tennis_nyYk2nPZAwY`. Each is present
in the eight-path census above. Thus G127 contributes **0 additional current
paths** to this denominator; its five paths must not be added to G109's eight.
The current eight are the three G89 tennis paths plus those five overlapping
paths.

## VERIFIER_CONTRACT self-check

### A

- **A1:** No code or test was added, so no new per-file test exists to rerun.
- **A2:** The headline was recomputed from the committed JSON: the eight
  `eligible_reaches_jump_statistic` records, eight listed paths, and eight
  unique table names agree; all 203 record classifications sum to the stated
  total.
- **A3:** Not applicable. This is an exhaustive census and G131 explicitly
  specifies no eye check or render; G96's prior decisive eye check was not
  repeated.
- **A4:** The artifact contains 203 distinct `table` names. The eligible
  denominator uses the eight distinct source-table directories, never G127's
  duplicate historical ledger outcomes.
- **A5:** Evidence only; no field, schema, or reader changed.
- **A6:** This lane makes an explicit-path evidence commit in `track-a5` only.
  It does not archive-land, append a ledger/register row, deploy, or alter the
  pod; adjudication and landing remain with the orchestrator.
- **A7:** Before commit/report, all named repository paths were checked:
  this memo; `g131_policy2/current_jump_gate_census.json`; G107; G109; G127;
  `g107_policy/G107_PREREGISTRATION.md`; and `VERIFIER_CONTRACT.md`.

### B

- **B1 CIRCULAR METRIC:** Clear. The raw eligibility prerequisites classify
  every canonical table before any displacement, candidate, or verdict result;
  every exclusion is named in the artifact.
- **B2 NON-ADDITIVE SCHEMA:** Clear. No production schema, field, status, or
  reader changed.
- **B3 FALL-THROUGH LOSS:** Clear. Empty, missing, insufficient, non-court,
  unknown, and no-stride inputs are explicit excluded categories, not bad
  quality verdicts.
- **B4 RE-CLAIM LOOP:** Clear. No claim, queue, retry, or ownership behavior
  changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. The pod received only a Python
  program over standard input which read existing CSVs and emitted standard
  output; no file was copied to it, persisted, restarted, killed, or tracked.
- **B6 ORPHANS:** Clear. No module, import, test, or command was moved or
  retired.
- **B7 HEAD-SLICE EVIDENCE:** Clear. The census is the complete one-pass
  canonical glob, not a leading slice.
- **B8 SELF-FIT AS INDEPENDENT:** Clear. No fitted model or residual is
  claimed.
- **B9 DEGENERATE DENOMINATOR:** Clear. A unit is a distinct source-table
  directory, not a recycled frame, track, or historical ledger outcome.
- **B10 MOVED BAR:** Clear. No harness threshold, coordinate contract, stored
  verdict, or policy bar was changed.

## NOT VERIFIED

- Any candidate policy's impact, recommendation, or its detection of the G96
  and G82 known-real defects: G131 step 2 is barred at 8 eligible tables.
- Whether the live corpus will later reach 10 eligible tables.
- Whether a future eligible table would be a valid production-quality output;
  this census establishes only reachability of the jump statistic.
- Any render or tennis_10 retrieval: G131 explicitly makes the eye check n/a,
  and tennis_10 was not rendered or retrieved.
- A focused test or full test suite: no code was added, and no test applies.
