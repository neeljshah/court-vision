# S383 period-stratified cell

PREPARE candidate complete; local construct checks pass. No corpus was scored.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h43, branch harness-h43.
Binding spec: docs/evidence/tracking/specs/S383_spec.md.
Vocabulary follows contract Q6; automated scan required.
The request's docs/evidence/VERIFIER_CONTRACT.md is absent; the applicable file is
docs/evidence/tracking/VERIFIER_CONTRACT.md, as directed by the harness-lane skill.

## Binding before-condition

Run before creating files: `ls scripts/platformkit/ingame/baseline_four_arm_period.py`.
Exit code: 1. Output excerpt:

```text
ls : Cannot find path 'C:\Users\neelj\nba-harness-h43\scripts\platformkit\ingame\baseline_four_arm_period.py' because
it does not exist.
```

## Source interfaces read before coding

All paths below are relative to C:/Users/neelj/nba-harness-h43. Resolution is n/a
(Python source, no media). `git diff master --` over these three files was empty,
exit 0: the inspected worktree sources match master. No pre-existing module changed.

- scripts/platformkit/ingame/baseline_four_arm.py: 13482 bytes.
  Exact signatures: `def _cell(rows: list[dict]) -> dict:` and
  `def summarize(predictions: list[dict]) -> dict:`.
  Comparison fields: `point`, `ci95`, `verdict`, `leave_one_game_out_range`,
  `largest_absolute_share`, `concentration_pass`.
  Saved rows carry `key`, `game_id`, `phase`, `warmup`, and
  `paired_losses[arm][metric]`; arms are A/B/C/D, metrics are brier/logloss.
  Warmup is a boolean; summarize excludes it before making scored populations.
- scripts/platformkit/ingame/gate_a0_ingame_vs_market.py: 12047 bytes.
  Exact signatures: `def cluster_bootstrap(df, col_a, col_b, n_boot=N_BOOT, seed=SEED):`
  and `def verdict(lo, hi, n_games, n_min=N_MIN_GAMES):`.
  The only landed import in the new module is `verdict` from this source.
  Bootstrap constants are `N_BOOT = 2000`, `SEED = 13`, `N_MIN_GAMES = 30`;
  draws use `rng.integers(0, ng, ng)` and percentiles `[2.5, 97.5]`.
  The local implementation imports no cluster bootstrap function.
- scripts/platformkit/ingame/baseline_four_arm_features.py: 6791 bytes.
  Exact signature: `def phase(features: dict, sport: str) -> str:`.
  NBA phase expression: `return f"Q{int(features['quarter'])}" if features['quarter'] <= 4 else 'OT'`.
  This module is read for schema only; it is not imported.

## Initial implementation (superseded by FIX 2a below)

- Added scripts/platformkit/ingame/baseline_four_arm_period.py and
  tests/platformkit/ingame/test_baseline_four_arm_period.py; this memo is the third owned file.
- Every arm difference is averaged across ticks within each game-period, then
  equally across the periods that game has, then equally across games.
  A missing period is not imputed. Games are sorted by game_id; tick reduction
  uses sorted keys and stable summation. Whole-game bootstrap uses the inherited stream.
- `comparisons` maps B/C/D plus metric to the inherited comparison fields;
  `game_statistics` makes each game's contribution explicit.
  `largest_absolute_share` contains `game_id`; no week statistic is fabricated.
  The inherited denominator tolerance and concentration threshold are unchanged.
  Fewer than thirty games is UNDERPOWERED; favorable intervals use SINGLE-WINDOW.
- `periods_per_game` maps game to period count. `games_by_period_count` maps
  number of available periods to number of games, using JSON string keys.
  `n_games_by_period` additionally reports period coverage. Counts are strict ints.
- Warmup and OT exclusions have named counts. Bad scored schemas/losses or
  duplicate non-warmup keys (including OT) reject the entire batch. `n_refused` counts distinct
  invalid rows, including every row involved in duplicate keys; `duplicate_keys`
  counts occurrences beyond the first. Reason counters can overlap.
  Boolean/string losses and values outside the inherited loss bounds are refused.
  Timestamp fields are not parsed: this module consumes the scorer's opaque keys
  and paired losses and exposes no as-of or recovery-time query.
- CLI writes JSON atomically after flush and fsync. Default JSON and stdout
  contain only counts, histograms and verdict labels. `--show-values` exposes
  the full report in both destinations.
  Output cannot replace the input file. JSON object key collisions are refused.

## Historical construct evidence and checks

The spec has no REAL ROW. The first test consumes the hand-worked three-game
fixture end to end through the CLI; one game lacks Q3. All fixture values and
expected arithmetic are in the test module, including its docstring.
No real paired-row file was opened. Temporary JSON inputs are constructed in tests.

- `python -m pytest tests/platformkit/ingame/test_baseline_four_arm_period.py -q -p no:cacheprovider`
  returned `66 passed in 3.76s` (exit 0) after FIX 1b.
- `python -m scripts.platformkit.ingame.baseline_four_arm_period --help` passed (exit 0).
- The draw-stream tests compare all 2000 draws for each of three game counts.
  Other tests cover opposite weighting signs, both input orders, missing periods,
  both sides of the thirty-game boundary, all six comparisons, exclusions,
  non-finite and absurd losses, strict count types, duplicate refusals, empty/single
  populations, cancellation, safe stdout, and write/fsync/replace failures.
- Independent verification rejected the initial candidate for the two findings
  recorded under FIX 1b. The final suite also tests malformed duplicates in both
  orders with identical counts.
- Python line counts via `len(text.splitlines())`: module 218; test 300.
  Both files are ASCII.
- `python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/baseline_four_arm_period.py tests/platformkit/ingame/test_baseline_four_arm_period.py docs/evidence/harness/S383_period_stratified_cell_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S383_spec.md`
  passed all nine checks (exit 0): vocab, crlf, loc, schema, head_slice,
  spec_threshold, proposed, removed_artifact, row_duplication. The threshold
  check reports no labelled threshold lines in the spec; inherited constants
  and behavior were checked directly against the source and construct tests.

Contract self-check: B1-B10 and Q1-Q8 apply. Exclusions and denominators are named;
the module is additive and opt-in; inherited thresholds are unchanged. This is
construct preparation with no sampled claim, charged trial, or deployment.

## FIX 1b

Binding verdict: `_verdict_s383_1b.md`, findings 1 and 2 (BLOCKING).
The local spec and `git show master:docs/evidence/tracking/specs/S383_spec.md`
were read; neither contains an AMENDMENT block. All work ran in this worktree.

1. Default artifact disclosed values. Before editing, a constructed g1/Q1 row
   with A=0.2 and B=0.3 for both metrics produced this failing B_brier excerpt:
   `"point": 0.09999999999999998`,
   `"ci95": [0.09999999999999998, 0.09999999999999998]`,
   `"game_statistics": {"g1": 0.09999999999999998}`.
   The CLI now selects counts, histograms and verdict labels before writing
   default JSON. Full cells require `--show-values` for both JSON and stdout.
   Reproduction after the fix: `FINDING 1 PASS` for default output, with no
   point, ci95, game_statistics or floating values; the flagged artifact equals
   the full report. `test_show_values_gate` reads the first artifact before the
   second run and asserts those absences, then verifies the full flagged report.
   The hand fixture now explicitly requests values for its existing arithmetic checks.
2. OT bypassed key validation and duplicate detection. Before editing, two
   constructed OT rows with key `dup` returned
   `{"n_ot": 2, "n_refused": 0, "n_ticks": 0}`; an OT/Q1 pair returned
   `{"n_ot": 1, "n_refused": 0, "n_ticks": 1}`.
   Every non-warmup key is now validated and registered before excluding OT.
   Reproduction after the fix: OT/OT and OT/Q1 both report
   `"refusals": {"duplicate_key": 1}` and `"n_refused": 2` in either order.
   Regression tests cover both collisions in both orders, plus missing, empty,
   whitespace and non-string OT keys. The exclusion fixture uses a unique OT key.
3. Finding 3 is a NOTE confirming calculations and other refusals. Those
   implementations were left unchanged. All 66 construct cases pass; help exits 0.
   The module provides no separate self-check command. Contract checks are above.

## FIX 2a

Amendment 1 was read with
`git show master:docs/evidence/tracking/specs/S383_spec.md`; it supersedes the
initial game-first primary. All edits are in this existing Windows worktree.
The landed module and its game-first reduction confirmed the stated premise.

- PRIMARY: m[g,p] averages tick differences within game-period; M[p] averages
  m[g,p] over games having p. The primary is the equal mean of the four M[p].
  Custom declared subsets retain equal weighting over their declared periods.
  Missing periods are not imputed: an unsupported primary is null and
  UNDERPOWERED with reason `period_support_insufficient`.
- Whole games are drawn in sorted game_id order with seed 13, 2000 draws of
  `integers(0, ng, ng)`. Every draw recomputes all period means, including
  repeated-game multiplicities. Unsupported draws are discarded and counted;
  more than 20 forces UNDERPOWERED with `period_support_insufficient`.
  Percentiles 2.5/97.5 use retained draws only; no retained draws gives null CI.
  An empty population makes no draws and reports zero retained/discarded.
- Each comparison reports `per_period` point, strict-int `n_games`, and
  `n_missing_games`. Bootstrap retained/discarded counts are strict ints.
  The complete old estimator is labelled SECONDARY in `game_first`.
- Primary `game_statistics` now contains additive contributions
  c[g] = sum over supported p of m[g,p]/n[p], divided by declared-period count.
  Contributions sum to the primary; largest share is max(abs(c[g]))/abs(primary).
  The inherited near-zero tolerance and concentration threshold are unchanged.
  The old `game_statistics` remains in `game_first`; `game_period_means` exposes
  the inputs. A local ingame source/test reader search found no other consumers.
  Leave-one-game-out recomputes every M[p]; unsupported deletions are counted in
  `n_leave_one_out_discarded`, and the range uses supported deletions only.
- The docstring works the missing-Q3 fixture by hand: primary 1/15 differs from
  SECONDARY 1/20; primary deletion range is [1/40, 11/80], largest share 3/4.
  Tests independently recompute both bootstrap intervals and discarded draws.
  Controlled streams check 19, 20, and 21 discards without changing constants;
  the existing tests check all 2000 native draws for each of three game counts.
- Existing refusals and OT key validation/exclusion remain. Both output routes
  require `--show-values` for all estimates, including per-period and SECONDARY
  values. Default output adds only bootstrap and missing-period counts.
  Every exception handler reports refusal counts or terminates with a counted
  parser error. No estimator imports the scorer's estimation functions.

Validation: the final requested per-file command returned `70 passed in 7.48s`
(exit 0). CLI `--help` exited 0. The first preflight passed eight checks but
failed LOC (test: 303); the test was compacted without removing cases.
Final preflight passed all nine checks (exit 0) on the compacted files.
Module: 270 lines; test: 300 lines; all three owned files are ASCII.
No helper module or other file was changed.

## NOT VERIFIED

- No real archive, NBA population distribution, sealed MLB output, or measured
  calibration result was examined. No cross-corpus conclusion is established.
- No live integration, network, pod, registry, or feature activation was exercised.
- Tests simulate interrupted writes; actual power loss and filesystem failure
  semantics were not exercised. Concurrent writers are not coordinated.
- The upstream scorer's key construction, training provenance, and paired-loss
  correctness are trusted inputs and are not re-audited by this module.
- No independent final acceptance or master-worktree rerun has occurred.
- No commit was created; files remain ready for lane_commit.
