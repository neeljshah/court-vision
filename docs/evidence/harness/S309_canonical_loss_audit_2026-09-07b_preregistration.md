# S309 attempt-2 preregistration: canonical in-game loss audit

Attempt 1 (candidate e6384a12f) was REJECTED on B2, B9 and Q4: the CPCV loss columns
were assigned from the forward-only loss columns, neither shared evaluator was called,
the symmetric embargo was recorded but not enforced, one JSON key was renamed without an
alias, and the design comparison ran before S293 landed. This file freezes attempt 2
before any attempt-2 metric is computed. The attempt-1 preregistration
`S309_canonical_loss_audit_2026-09-07_preregistration.md` and every attempt-1 artifact
stay untouched; attempt 2 writes only new `2026-09-07b` filenames.

## Order and ancestry

- S293 must have landed on master before this comparison runs, per the spec's ORDER
  clause. The landing commit named as this attempt's ancestor is
  `4a41c436e3650cfad1517d1987a27d09d5a00122`, and this branch is rebased onto it before scoring.

## Frozen engines (SHA-256, recorded before scoring)

Two columns because this Windows worktree holds a mix of LF and CRLF checkouts after the
rebase. The LF-normalized column is the checkout-independent content identity; the raw
column is the exact bytes `pod_run` ships, and is what the summary JSON records at run
time as `shared_route_sha256`.

| file | role | sha256 (LF-normalized) | sha256 (raw worktree bytes) |
|---|---|---|---|
| scripts/platformkit/eval_gate/walkforward.py | shared forward-only evaluator | 6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9 | c8a9b5b0f0f7c84dc5fdb0c7a4a27e0f7f2040f99326ef5376cde011df27bc2e |
| scripts/platformkit/eval_gate/cpcv_engine.py | shared symmetric CPCV evaluator | 9b152531852a9fd435be82ca69584929fe718da9bd1554ad293cb4cd11717c01 | 5accfbe490031acb084a8e4375a082b00d842cf4011a76c6d27dfc2c7db614a5 |
| scripts/platformkit/cpcv.py | CPCV split generator used by the engine | 653428d8229541f66353698326e9921bf47586a799a994f9b21b12a0abcc1dc9 | 7af09eedd1a6ce3cccc5b84b18d4e64604cef81bfcef3c061f0136b168389081 |
| scripts/platformkit/eval_gate/state_key_guard.py | S301 duplicate-state-key guard, run on both arms | 6c888a1ba80524f637eebdcd0daf0f879d79cd1d45d9f7452ebf17a58454140a | 14274212a2770a6cd548c34de444cb42c9a6dca0722e2d8eee6158d814ef04dd |
| scripts/platformkit/s309_design_evaluators.py | this row's arm driver | 91c65cbdd2747ac85c1d65af03cc13986eb37b337f3a6d96d834aa164195f472 | 6b36686e31fbc173559a6a264f2b25a9904201fefad3e40d3c822d5fe6dbbb14 |

`scripts/platformkit/s309_canonical_loss_audit.py` is deliberately absent from this table:
it embeds the seal below, so its own hash cannot exist before the seal does. Its SHA-256 and
those of the three shared files are recorded again in the summary JSON at scoring time.
The three shared files are read-only inputs to this row. If any of their hashes differs
at scoring time, the run is void and is reported as such.

## Inputs

Unchanged from attempt 1: `data/cache/inplay_odds/nba_checkpoints_full.parquet`,
`data/cache/inplay_odds/nba_price_series.parquet`,
`data/domains/basketball_nba/espn_nba_game_bridge.parquet`, and the historical archives
`docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_paired_losses.csv`,
`docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_summary.json` and
`docs/evidence/harness/S280_ingame_cross_venue_disagreement_2026-09-04_ticks.csv`.
Each is recorded with absolute path, byte size and SHA-256 in the summary JSON.

## Census, retained unchanged

All 465,249 checkpoint ticks in 1,593 game clusters are scored. The terminal-like table
is `period >= 4 and game_clock_s == 0`; its status stays UNKNOWN because receipt and
final timestamps do not exist in these stores. No outcome-based exclusion is permitted.

## Canonical source construction, retained unchanged

Every moneyline source row is retained in the accounting artifact with all original
columns plus aliases, and carries exactly one accounting reason. The canonical key is
(game_id, venue, event_key, timestamp) with one home-side probability per key:
Polymarket `home` directly; Kalshi `side == parsed home`, else the complement of the
parsed away side. A duplicate canonical key is an error and stops the run.

## Design comparison (the absorbed S299 arm) -- the attempt-2 correction

- ONE frozen calibrator is scored under BOTH designs on the same ticks: the S272
  incumbent is the logistic recalibration and the S272 candidate is the low/high tail
  isotonic recalibration.
- The forward-only arm calls `scripts.platformkit.eval_gate.walkforward.walk_forward`.
  The robustness arm calls `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate`.
  The loss series of each arm is derived ONLY from that arm's own out-of-fold
  predictions. Aliasing one arm's losses onto the other is the attempt-1 defect and is
  prohibited.
- FOLD DESIGN. CPCV uses 8 groups and 2 test groups, giving 28 paths, so every game is a
  test row on exactly 7 paths and its CPCV probability is the mean over those 7 paths.
  The forward arm is the shared expanding window: one fit per distinct train set.
- EMBARGO. CPCV is run with `embargo_days=1`, the engine's SYMMETRIC calendar-day
  window applied on BOTH sides of each test block, plus the shared 3-day same-matchup
  embargo. The forward arm carries the shared forward-only embargo only, and is labelled
  as such; the symmetric embargo is a property of the CPCV arm.
- PURGE SCOPE. Both arms use the shared purge unchanged: same-team games within
  `PURGE_HOURS = 48` and same-matchup games within `EMBARGO_DAYS = 3` are dropped from
  the train set of every test row, symmetrically in the CPCV arm. The forward arm
  additionally drops any train game not SETTLED strictly before the test state's
  timestamp -- strictly tighter than the shared route's own strict-past rule.
- GRAIN, declared in advance. The shared evaluators build each test row's train set with
  a per-state loop that is quadratic in the number of states, so they are driven at
  game-cluster grain: one evaluator state per game (1,593), each emitting one out-of-fold
  probability for every tick of its test game. The scored series is one prediction per
  tick per design and `state_key` stays unique. The tick series and each evaluator's own
  returned records must agree to 1e-9 or the run stops.
- REDACTION AND STATE KEYS. Both arms run with `strict_redaction=True` and no `allow_keys`,
  so an undeclared key on a test row is a LeakError rather than a silent pass-through, and
  with S301's `guard_state_keys=True`, so a duplicate (game_id, state_ts) evaluator key
  raises inside the shared route.

## Metric, bar and bootstrap -- retained unchanged

- Primary metric: paired tick-weighted Brier improvement, defined as baseline loss minus
  candidate loss; POSITIVE means the candidate is better. The frozen comparison bar is
  +0.004 and is not changed by this attempt.
- The design delta is forward-only loss minus CPCV loss; POSITIVE means the CPCV loss is
  lower. DESIGN-SENSITIVE is declared only if the preregistered primary paired interval
  for that delta excludes zero. Tail log loss and 10-bin ECE stay NAMED SECONDARY
  diagnostics and are published without setting any label.
- Ratio bootstrap on game sums and counts, seed 901, 10,000 replicates, on all 465,249
  ticks in 1,593 game clusters. MDE is reported per table as the candidate-specific
  minimum detectable effect, `1.96 * sd(bootstrap replicates)`, and the design delta
  carries its own interval computed the same way.

## Acceptance bars -- retained unchanged, plus the attempt-2 additions

Zero unaccounted source rows; zero duplicate canonical keys; 1,593/1,593 Polymarket games
joined; probability and historical S272 Brier replay error at most 1e-12; exhaustive
fit/purge provenance. Cross-venue overlap is printed and CLOSED AT LIMIT below 30 games.
ADDED for attempt 2: the pre-attempt-2 JSON key
`polymarket_probability_replay_max_abs_error` is retained as an alias with its original
Polymarket-only meaning; the two arms' loss series must not be identical; and the focused
tests must cover variable cluster sizes and future-label propagation.

## Compute and evidence

The price-series scorer exceeds 500 MB RSS, so the scored run happens exactly once as a
compute-only scratch job through `C:/Users/neelj/bin/pod_run a15` under
`/workspace/wt/a15`. The deployed tree is never written; `data/registry`,
`backtest_fwer.jsonl` and `hypotheses*.sqlite` never reach the pod. Required evidence is
the summary JSON, the canonical accounting and keys, the folds and fitted parameters, the
per-state paired losses for both arms, the artifact hashes, and one lane-authored memo
ending in an explicit NOT VERIFIED list. The route emits no memo, so no artifact can
carry a stale hash of a rewritten memo. No promotion, no feature flag, no register write,
no shared-ledger write and no source-store write is permitted. The focused test
normalizes this file from CRLF to LF and hashes the bytes above the seal line.

Seal SHA-256: cd9e157abc95c2e699228069bfa40292621fc26f6e48fa0352b3d992e5f69cad
