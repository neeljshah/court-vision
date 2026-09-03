# G157 retrack yield -- replacement-pod tennis snapshot

**Verdict: ACCEPT WITH CORRECTIONS.** This is a strictly read-only,
point-in-time census of the replacement pod while its footage bridge and
tracking daemon are live. It measures rebuild yield, not geometry validity or
a quality pass. No pod file, pod process, threshold, coordinate contract,
eligibility definition, harness, or verdict was changed.

## Observation window and scope

The exhaustive pod observation ran once from `2026-09-03T14:36:45.437832Z`
through `2026-09-03T14:36:45.458652Z`. It enumerated every immediate
`/workspace/nba-ai-system/data/tracking/*/tracking_data.csv` directory routed
to tennis, and classified each with the unchanged
[`g154_local_table_census.py`](../../../scripts/platformkit/g154_local_table_census.py)
functions (`sport_for_table` followed by `census_table`). It did not rerun
tracking or write an output file on the pod.

The **ELIGIBLE DENOMINATOR is 1 tennis source-table directory**, and every
share below uses that denominator. The sole directory is `tennis_smoke`.
This is an exhaustive construct census, not a head sample.

The ledger was read in the same window. It contained **zero tennis rows**, so
zero tennis games completed inside this observation window. This does not
contradict G153's corrected general premise that new real pod rows carry
`decoded_frames`; it records only that no tennis row existed in this bounded
read.

The same pod snapshot found `data/footage_bridge/` present with **2 published
`.mp4` files and 1 in-flight `.part` file**. A separate, one-shot local bridge
read from `2026-09-03T14:39:25.012Z` to `2026-09-03T14:39:27.159Z`, using the
unchanged `bridge_supervisor.untracked_count` with its read-only pod table
probe, found tennis bridge queue depth **60** (3 known tracking IDs across all
sports). It is a later bridge snapshot, not retroactively part of the pod
census window.

## Tennis table census

| Table | Rows | Distinct frames | `coordinate_space` | `calibration_provenance=solved` | First blocker |
|---|---:|---:|---|---:|---|
| `tennis_smoke` | 1,861 | 726 | `court_feet` | 1,558 / 1,861 = 83.7184% | reaches gate |

The required first-blocker breakdown, in G109/G154 vocabulary, is committed
in [`first_blocker_breakdown.csv`](g157_yield/first_blocker_breakdown.csv):

| First blocker | Tables / eligible denominator | Share |
|---|---:|---:|
| `unknown_sport_routing` | 0 / 1 | 0.0000% |
| `empty_or_header_only` | 0 / 1 | 0.0000% |
| `metric_local_scope` | 0 / 1 | 0.0000% |
| `coordinate_contract_rejection` | 0 / 1 | 0.0000% |
| `missing_required_coordinate_or_schema` | 0 / 1 | 0.0000% |
| `INSUFFICIENT_DATA` | 0 / 1 | 0.0000% |
| `reaches_gate` | **1 / 1** | **100.0000%** |

`court_feet` is reported as a declaration only. Per G152 it is stamped
unconditionally and is not evidence of recovered geometry; the solved-share
is reported separately and likewise is not promoted to a geometry claim.

## Ledger decoded-frame comparison

The required two-column comparison is intentionally an empty, header-only
table: [`tennis_ledger_coverage_comparison.csv`](g157_yield/tennis_ledger_coverage_comparison.csv).
There were zero tennis ledger rows, hence no named row with a missing
denominator and no row silently excluded. For each future row this table's
first coverage column is the harness `coverage_pct`; the second is qualifying
emitted frames divided by that row's `decoded_frames`. They are not
interchangeable denominators.

## Even sample and eye check

Because the decision set contains one table, the table selection is exhaustive.
Within it, five frames were selected evenly over the sorted 726 distinct frame
IDs using `round(i * (n - 1) / 4)` for `i = 0..4`: 372, 7,452, 13,800,
21,189, and 28,461. The complete selected-row audit is committed in
[`even_frame_sample.csv`](g157_yield/even_frame_sample.csv), rather than a
head slice.

The required source-frame eye check is **NOT VERIFIED**. The sole table
directory contains only `tracking_data.csv` and `tracking_capability.json`; a
read-only source probe found no tennis video in `data/footage_corpus`, no
published tennis `.mp4` in the stage, and no stored render. No proxy image,
re-track, extract, or invented geometry check was substituted for it. The five
evenly chosen exported-coordinate rows are retained only to make this absence
auditable.

## VERIFIER_CONTRACT self-check

### A

- **A1:** No code or test was added; no per-file test applies, and no full
  test suite was run.
- **A2:** The committed census independently reproduces one unique table,
  one gate-reaching table, and the 1,861-row / 726-frame values. The committed
  ledger comparison has zero physical ledger records, matching the snapshot.
- **A3:** The census is exhaustive. The conditional five-frame sample is
  evenly spaced by the declared formula, not a head slice; its source visual
  is explicitly NOT VERIFIED because no source/render exists.
- **A4:** The denominator is one distinct immediate source-table directory;
  no table name is duplicated.
- **A5:** Evidence only; no field or reader changed.
- **A6:** This worktree makes an explicit-path evidence commit only. No
  archive landing, deployment, pod copy, or pod action was attempted.
- **A7:** At final check, every repository path named in this memo exists:
  this memo; all four `g157_yield/` CSVs; the G154 script; G152; G153; and
  `VERIFIER_CONTRACT.md`.

### B

- **B1 CIRCULAR METRIC:** Clear. Every tennis directory from the one-pass
  glob is classified; every tennis ledger row in the stated window is present
  (there are zero).
- **B2 NON-ADDITIVE SCHEMA:** Clear. No schema, field, status, or reader changed.
- **B3 FALL-THROUGH LOSS:** Clear. Every G109 first-blocker category is
  retained, including zero-count categories; absent ledger rows are named as
  absent rather than treated as quality failures.
- **B4 RE-CLAIM LOOP:** Clear. No claim or queue ownership code changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. Pod interaction was read-only; no
  copy, stage, move, delete, restart, kill, or re-track occurred.
- **B6 ORPHANS:** Clear. No module or command moved or retired.
- **B7 HEAD-SLICE EVIDENCE:** Clear. The census is exhaustive and the five
  frame IDs use an even-spacing rule.
- **B8 SELF-FIT AS INDEPENDENT:** Clear. No fit or residual is claimed.
- **B9 DEGENERATE DENOMINATOR:** Clear. The denominator is the distinct
  source-table directory, not rows, frames, or track IDs.
- **B10 MOVED BAR:** Clear. The 0.90 coverage bar, 10-eligible bar,
  coordinate contract, gate definition, and every verdict remain unchanged.

## NOT VERIFIED

- Recovered tennis geometry or geometry quality; `court_feet` is declaration
  evidence only.
- Any tennis ledger-based decoded-frame coverage pair; no tennis ledger row
  existed in the observation window.
- The required five-frame source visual, because neither source footage nor a
  stored render is present for `tennis_smoke`.
- Any state after the bounded snapshots. The bridge remains live and may
  change immediately after either read.
