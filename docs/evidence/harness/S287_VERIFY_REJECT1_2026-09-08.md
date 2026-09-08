[provenance: recovered by the lander from C:/Users/neelj/AppData/Local/Temp/cx_verify_s287.log, the first S287 verify run (TURN_END and EXIT:0 gap=verify_S287 at 2026-09-08T03:20:01-05:00); that run wrote its memo to docs/evidence/harness/S287_VERIFY_2026-09-08.md and the second run overwrote the file, so only what the log captured survives -- the log keeps the tail of each captured output, and the two surviving copies (a plain copy at log line 740 and a git-diff copy at log line 894, identical once the leading "+" is stripped) both begin mid-word inside the second TEST line, so the lines above it are unrecoverable and the log reports no blob id for the file, the "git diff --no-index" index line having fallen outside the captured tail.]

VERDICT: REJECT

The verdict line is taken from the harness log's own markers (`cx_verify_s287.log:775`
"agent: VERDICT: REJECT" and `cx_verify_s287.log:778` "VERDICT: REJECT"); the memo's own
first line did not survive. That first run rejected on the explicit S266
restriction-reproduction condition only.

RECOVERED TAIL, verbatim; the first line below is truncated at its head, and the wider of
the two captured copies is used:

oc_rail_scope.py -q -p no:cacheprovider` -> 1 passed in 0.88s (local result).
CORRECTION: treat 0.006218804253472238 as the simulator-Brier delta, not the full metric maximum; that maximum is 0.04175347222222213 for simulator ECE. No evidence-only diff can satisfy replay; establish route repeatability and regenerate the three S287 artifacts without moving the bar.
NOT VERIFIED: cause of simulator replay drift; independent observation of pod RSS or deployed-tree contents. The candidate memo contains its own NOT VERIFIED list (`docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04.md:266`).
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | nba in-game simulator calibration | S287 | 355 games/2,130 targets: recal_null minus simulator Brier -0.105094239870, game-clustered 95 pct CI [-0.121753426766, -0.088435052973]; 30-cluster replay arm-metric max abs diff 0.041753472222 > 1e-9 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: The per-game `timestamp` field stores a state key such as `401809239:120`, and that file lacks probabilities/outcomes needed to recompute ECE by itself (`docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04/S287_per_game_paired_loss_series.csv:2`); Q9 was outside this verdict scope.
NEW GAP: The archive was staged at `/workspace/wt/a13/data/cache/eval_gate/` rather than the preregistered scratch `inputs/` location (`docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04.md:185`); no deployed-tree write is evidenced.

NOT RECOVERED: everything above the truncated line -- the memo's own verdict line, the
PREMISE / ACCEPTANCE / HEADLINE findings, the A/B/Q per-item dispositions, the LOC and
reader-survey lines and the first TEST line. The candidate answered this REJECT with fix 1b
(the route-repeatability experiment, a13 2387c0e41); the second verify run's memo, landed
alongside as S287_VERIFY_2026-09-08.md, supersedes this one at CLOSED AT LIMIT.

Vocabulary follows contract Q6; automated scan required.
