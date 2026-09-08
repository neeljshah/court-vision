# S297 preregistration: NBA minutes DNP mixture distribution

## Scope and machine

This preregistration executes `docs/evidence/tracking/specs/S297_spec.md` in
`C:/Users/neelj/nba-track-a19` on branch `track-a19`. It self-checks sections B
and Q1-Q9 of `docs/evidence/tracking/VERIFIER_CONTRACT.md`. The scorer is
expected to exceed 500 MB RSS and runs exactly once through
`C:/Users/neelj/bin/pod_run a19` in its per-worktree scratch directory. The
deployed tree is never written. No ledger, register, deployment, or write
under `data/` is authorized. This is an uncharged calibration comparison, so
Q2 does not apply.

## Re-measured premise and fixed inputs

Before this seal, separate PyArrow row-group reads measured 326 zero-minute
rows among 77,744 rows in
`data/domains/basketball_nba/player_boxscores.parquet` (1,118,538 bytes) and
221 zero-minute rows among 1,023 rows in
`data/cache/omni_box_refresh/nba_player_box_extension.parquet` (34,147 bytes).
DNP rows remain in every denominator. An absent roster player has no recorded
row and is never manufactured as a DNP outcome.

## Fixed OOS design and comparison

The scorer creates exactly one evaluator state per recorded player-game tick,
with stable key `game_id|player_id`; no state represents multiple ticks. It
calls the shared
`scripts/platformkit/eval_gate/cpcv_vector_distribution.py:cpcv_evaluate_vector_distributional`
with five date blocks, one test block per path, inherited team/matchup purge,
and a fixed symmetric nonzero one-day embargo. Every recorded source state is
tested exactly once. The test outcome is redacted and, inside a forecast, only
training states strictly earlier than its timestamp may supply a value.

The baseline is the strictly earlier train-fold empirical DNP rate and its
strictly earlier train-fold empirical CDF over positive minutes. It is sampled
as a mixture of a zero atom and 100 deterministic positive-minute empirical
draws. The candidate has a player-partially-pooled DNP probability:
`(n_player * p_player + 20 * p_league) / (n_player + 20)`. Its positive-minute
CDF is a deterministic 70/30 player/league empirical mixture when the player
has positive-minute history; it otherwise uses the league CDF. The candidate
uses the same 100-draw mixture resolution. Empty strictly earlier histories use
the same zero point mass in both arms and are retained, not dropped.

The primary metric is full minutes-mixture CRPS. Secondary metrics are DNP
Brier and log loss, positive-minutes q10/q50/q90 pinball, and nominal q10-q90
coverage (0.80). Quantile pinball is evaluated on all recorded outcomes, not
conditioned on positive minutes. The archive separately identifies the DNP
status and records positive-only quantiles. Improvement is baseline loss minus
candidate loss; positive means candidate calibration is better. The acceptance
bar is exactly `baseline CRPS minus candidate CRPS > 0 with CI lower > 0`;
the NBA in-game Brier threshold does not apply to CRPS. Null is valid.

The paired 95 percent CI is a deterministic game_id-cluster bootstrap with
seed 297 and 500 draws. Every forward fold with fewer than 30 held-out game
clusters is labelled `INSUFFICIENT` and is not pooled. The durable artifacts
are a re-emitted CSV carrying game_id/player_id/date/DNP/outcome/DNP probability
and quantiles, evaluator-record-derived paired losses, fold table, JSON summary,
and the required memo. The focused test reads this file, normalizes CRLF to LF,
and hashes bytes above this seal line; it never reads Git history.

SEAL_SHA256: 3dad9bc2d19a288b9938e74909f20b2b0d05059d8dc01743db775c5875b837ea
