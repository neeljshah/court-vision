# S808 adversarial verifier (tier 2) -- 2026-10-09 (PAPER ONLY)

## Round 1 on 451a216b6: REJECT
3 of 14 mutants survived. Dropping the KEEP entries unsettled_games, shard_absent or lag_mid_refused still passed the test.
The memo's reasoning held up. (1) history=() cannot change any kept counter: in ingame_scoreboard.run, history reaches
only `training` through _read (json_refused / input_unavailable). served_games, shard_absent, settle(), lag_mid_refused and tick_refused:*
are all computed before _models(). (2) The seal table is accurate, but unpinned helpers also sit on the import path (venue_time, coherence_scanner*,
live_board, local_capture_metrics, local_state_capture_dates). None decides tennis orientation (ALIASES['tennis'] = {} is in the pinned game_market_link.py).
(3) The PROPOSED coverage diff is safe. render and cumulative_rollup_night read named keys only, and test_coverage_receipt.py makes no key-set assertions.
The file would be about 208 lines. Caveat: a constant label outlives a reseal fix.

## Round 2 on e3c8a72dd (fix round 1): ACCEPT
14 of 14 killed. The unmutated test gives 1 passed in 0.62 s, and git status was clean afterwards.

| id | mutant | r1 | r2 |
|---|---|---|---|
| M1 | all sports in one run() | killed | killed |
| M2 | history passed through | killed | killed |
| M3 | as_of dropped | killed | killed |
| M4 | KEEP filter removed | killed | killed |
| M5 | KEEP widened to model_state_refused | killed | killed |
| M6 | sum from last sport only | killed | killed |
| M7 | schedule not date-formatted | killed | killed |
| M8 | 'settlement_' dropped | killed | killed |
| M9 | 'tick_refused:' dropped | killed | killed |
| M10 | 'served_games' dropped | killed | killed |
| M11 | 'lag_mid_refused' dropped | SURVIVED | killed |
| M12 | 'shard_absent' dropped | SURVIVED | killed |
| M13 | 'unsettled_games' dropped | SURVIVED | killed |
| M14 | schedule formatted with as_of | killed | killed |

Contract tier: ACCEPT on 451a216b6, including the V1/V2 real-data reproduction (per-sport sums equal the receipt, 11 of 11 games fail orientation).
It also gave ACCEPT on the fix-round diff, but did not re-run pytest because MemFree was 1.08 GB, below the gate.

## Addendum 2026-10-09 (dispatcher-extended OWNS): PROPOSED diff applied with the zero-tick gate
cf3411b5d plus fix round 4d4de78e3. unscoreable_by_cause = UNSCOREABLE[sport] only when no arm scored any tick of the sport that night; otherwise []. It is also [] when the scoreboard is refused.
Tests (one file per process): test_coverage_receipt_unscoreable.py 4 passed 0.50 s; test_coverage_receipt.py 47 passed 4.67 s.
Adversarial tier on cf3411b5d: ACCEPT, 9 of 11 mutants killed. M9 (per_game gate) is equivalent. M3 (arm-A-only gate) survived and was then killed by fix round 4d4de78e3 (1 failed, 3 passed under the mutant). Contract tier: PASS C1..C5.
