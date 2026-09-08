# S296 preregistration: strict-prior NBA full-boxscore OOF distribution

## Scope and machine

This preregistration executes `docs/evidence/tracking/specs/S296_spec.md` in
`C:/Users/neelj/nba-track-a17` on branch `track-a17`. It self-checks sections B
and Q1-Q9 of `docs/evidence/tracking/VERIFIER_CONTRACT.md`. The score is heavy
enough to run only through `C:/Users/neelj/bin/pod_run a17` in the pod scratch
worktree; the deployed tree is never written. No ledger, register, deployment,
or write under `data/` is authorized. This is an uncharged calibration
comparison, so Q2 does not apply.

## Re-measured premise and fixed inputs

Before this seal, separate pyarrow row-group reads measured 77,744 unique
`game_id+player_id` rows in
`data/domains/basketball_nba/player_boxscores.parquet` (1,118,538 bytes) and
1,023 rows in
`data/cache/omni_box_refresh/nba_player_box_extension.parquet` (34,147 bytes),
with zero overlap. Their union is exactly 78,767 rows in 3,645 game clusters.

The four median-only inputs are read separately and retained unchanged:
`data/cache/pts_q50_oof_int95.parquet` (869,923 bytes),
`data/cache/reb_q50_oof_int95.parquet` (842,533 bytes),
`data/cache/ast_q50_oof_int95.parquet` (846,879 bytes), and
`data/cache/blk_q50_oof_int90.parquet` (800,936 bytes). Their first ids are
respectively `2544@2022-10-18`, `2544@2022-10-18`, `2544@2022-10-18`, and
`1626149@2022-10-18`.

The emitted vector is fixed to every shared numeric box-score field:
`min`, `pts`, `reb`, `oreb`, `dreb`, `ast`, `stl`, `blk`, `tov`, `fgm`, `fga`,
`fg3m`, `fg3a`, `ftm`, `fta`, `pf`, and `plus_minus`. No row is excluded:
zeros, DNPs (`min == 0`), bench players, and all fields remain in every
denominator.

## Fixed OOS design and comparison

The scorer creates exactly one evaluator state per source player-game tick,
with stable key `game_id|player_id`; no state is substituted for an entire
game. It calls the shared
`scripts/platformkit/eval_gate/cpcv_vector_distribution.py:cpcv_evaluate_vector_distributional`
with five date blocks, one test block per path, the inherited team/matchup
purge, and a fixed symmetric nonzero one-day embargo. Each source state is a
test state exactly once. Every predictor receives only evaluator-supplied,
purged training states and then uses only strictly earlier dated vectors.

The candidate is the named `strict-prior player empirical` distribution: 25
deterministic vector samples drawn from that player's supplied earlier vectors;
when none exists it uses the same strict-prior league fallback without dropping
the row. The named baseline is `strict-prior league empirical`, 25 deterministic
vector samples from all supplied earlier vectors. Source-state keys for every
sample are archived with the re-emitted table, so the forecast vectors are
reconstructible from archived observed fields and source hashes.

The fixed metrics are CRPS and q10/q50/q90 pinball for every field, 80 percent
coverage and its per-state squared coverage loss, joint energy score, and
sample-vector coherence violations. Paired 95 percent cluster bootstrap CIs
use game_id clusters and seed 296. Improvement is always baseline loss minus
candidate loss: positive means candidate better. The frozen comparison bar is
`+0.004`; it is not changed. A result is only `SINGLE-WINDOW`, never an AHEAD
promotion, because this spec has one corpus.

The scorer aborts any field with fewer than 30 held-out game clusters and labels
it `NOT SCORABLE`. It writes new dated sample, fold-date, paired-loss, and JSON
artifacts plus the required memo. The focused test reads this file, normalizes
CRLF to LF, and hashes the bytes above this seal line; it never reads Git
history.

SEAL_SHA256: 06d8bba3a5c2defb368afd74bb86a929371728b0f52651be03ff84760d312530
