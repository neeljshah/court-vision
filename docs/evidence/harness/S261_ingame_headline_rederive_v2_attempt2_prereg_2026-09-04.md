# S261 Attempt 2 In-Game Headline Re-Derivation v2 Preregistration

Scope: locally re-derive the existing NBA and MLB three-arm in-game calibration
values through the shared CPCV evaluator. This is a calibration measurement
only. It does not alter S211 artifacts, a corpus, a public page, the register,
the ledger, or a deployment target.

Machine: local Windows worktree `C:\Users\neelj\nba-track-a13`, because S211
attempt 2 commit `709e22974` completed this full route on this laptop. No pod
copy or deployment occurs.

Premise recheck before scoring: reopen the S211 paired-loss archives and
confirm NBA static/score-only/conditional values
0.21883250084408842/0.17235318274013006/0.16324678066236500 at n_eff 1313 and
MLB 0.24897282410431543/0.12822834737953837/0.12799755953257377 at n_eff
23279. Recount source exclusions before CPCV: 2458 `invalid_inning` rows have
an unparseable home or away innings field, and 2246 `tied_final_score` rows
have equal parsed final totals. Both counts are printed as named denominator
exclusions before scoring; neither is selected after loss evaluation.

The full route admits every eligible path: 1313 NBA game paths and 23279 MLB
game paths. It does not sample. For each sport, static, score-only, and
conditional quantities are calculated inside the same `cpcv_evaluate` callback
with eight timestamp groups, two test groups, a one-day symmetric calendar
embargo, 48-hour same-team purge, three-day symmetric same-matchup protection,
and strict test-view redaction. Outputs record the paired per-state losses,
cluster id, timestamp, split ids, raw checkpoint count, and CPCV path count.

The process prints RSS before and after each sport. It aborts with the exact
status `MEMORY LIMIT` if RSS exceeds 700 MB. There is no silent sample fallback.

New attempt-2 summary and paired-loss CSV filenames carry suffix `_attempt2`.
Every v1 field and meaning is retained: `checkpoint_count` is raw scored
checkpoints, `finite_resamples` is finite game-cluster bootstrap draws, and
`reproduction_abs_diff` is the absolute serialization/reaccumulation
difference for static, score-only, and conditional losses. Shares retain
`total_calibration_change` as an additive alias equal to
`static_minus_conditional`; they also contain score-only share and model-prior
contribution. The archive prints n_eff, named exclusions, exact public-value
differences, and `NOT REPRODUCED` whenever the unchanged bar is unmet.

Frozen public values are NBA static/conditional 0.209/0.159 and MLB
static/conditional 0.241/0.126. The bar remains max absolute difference <=
1e-6. Exact strings to print are NBA 0.00983250084408843/
0.00424678066236500 and MLB 0.00797282410431543/0.00199755953257377, in
static/conditional order. A game-cluster interval covering zero is reported as
the honest result without changing `NOT REPRODUCED`.

No charged trial is opened. K is unread; no ledger or register is read or
written. Evidence remains under 50 MB. Existing S211 and S261 attempt-1b
artifacts remain byte-identical.

Seal SHA-256 of the LF staged bytes above: `1DCB38B6CBB59694CD4A722AA843BE9694905ADC292B9A17ACE9F95D29E984FB`.
