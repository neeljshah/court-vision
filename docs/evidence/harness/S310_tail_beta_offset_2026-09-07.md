CLOSED AT LIMIT -- the tail beta-offset does not improve calibration: combined-tail log-loss improvement -0.004157383, 95 pct CI [-0.010714071, +0.001495545], lower bound not above 0, so the preregistered bar is not met; the global Brier guard passes at -0.000023269, CI [-0.000049503, +0.000003889], above -0.0005.

# S310 tail beta-offset calibration screen (NBA)

Sign convention: improvement = baseline loss minus candidate loss; positive = candidate better. Every improvement is negative (candidate slightly worse) and every interval straddles zero. Calibration only.

Prereg `S310_tail_beta_offset_2026-09-07_prereg.md` seal `0b7ed9caa1bdb0e08b34fbf81fd19a7266cd00c2f6f86f1cdca4b5ba8cefafbd`;
supplement `..._prereg_supplement.md` seal `4f9898cf09f46f91253286ba2ccd8047813b46fbd920bf6ad81b4740dc10a904`;
corrected supplement `..._prereg_supplement_corrected.md` seal `aaecd6956b75c305118a24b0156510e79cd483c1875e42ebd1afff704c5f0e00`.

| population | baseline log loss | candidate log loss | log-loss improvement 95 pct CI | Brier improvement 95 pct CI | clusters |
|---|---:|---:|---|---|---:|
| low 0.01-0.05 | 0.099290493 | 0.103380344 | -0.004089851 [-0.018882212, +0.005967350] | -0.000170521 [-0.000772329, +0.000262794] | 557 |
| high 0.95-0.99 | 0.123486240 | 0.127690441 | -0.004204200 [-0.007379012, +0.001553461] | -0.000335411 [-0.000565462, +0.000072711] | 718 |
| tail combined | 0.113579822 | 0.117737205 | -0.004157383 [-0.010714071, +0.001495545] | -0.000267901 [-0.000569351, +0.000048318] | 1267 |
| global | 0.458163609 | 0.458524706 | -0.000361098 [-0.000917634, +0.000123317] | -0.000023269 [-0.000049503, +0.000003889] | 1593 |

Bootstrap: 10000 game-cluster resamples, seed 905, each keeping its full tick denominator. The frozen 0.004 global bar is untouched and is not an input. Low and high bins are descriptive, so Holm has no claimed-bin family; the S272 trainable-tail oracle cap 0.002534 stays a precision limit.

## What was fit, and on what grain

Two frozen season groups, one test group, shared purge, symmetric one-day embargo. Fold 0 (test 2024-25)
has no strict-past training rows, so both arms return the raw market probability, exactly as the prereg
declares for that case; fold 1 (test 2025-26) trains on 48349 ticks and fits beta = [-0.555847, 0.105395,
-0.042477]. The screen rests on one fitted fold. Grain, sealed before any amended result existed: one
state per (game_id, period, floor(game_clock_s / 30)), lowest source row index per cell -- 465249 source
rows become 117964 states over all 1593 clusters, and the raw 0.01-0.05 band holds 4420 states, 570
clusters and 26 positive-outcome clusters (tick grain: 9226, 649, 29).

## A defect this run found and fixed

`ts` is int64 epoch seconds and `_states` read it with `pd.Timestamp(row.ts)`, which treats a bare integer
as nanoseconds. Every state landed on 1970-01-01, the calendar-day embargo blocked all 117964 states on
every path, both folds trained on 0 rows, and every improvement was exactly +0.000000000 with a zero-width
interval. The first pod job was on course to spend eight hours returning that vacuous null. Full account
in the triage memo `docs/evidence/harness/S310_pod_job_triage_2026-09-07.md`.

## Reproduction, cost, artifacts

Pod job `20260907225013_484703_26766`, rc 0, RSS 723 MB, route SHA-256
`0fc0f84e9fa21776105e469d9220d10c970159a1d54d8e448be60371696d821a`, matching the committed harness.
Identical numbers in three runs: local (201.1 s) and two pod jobs. The per-file suite
`test_s310_tail_beta_offset.py` reports 10 passed. Time: the abandoned first job burned 4 h 46 m for no
artifact; triage, re-plan and two pod runs took about 3 h more. All six artifacts are under 50 MB and
committed; none held back on the pod.

    dc37acef16daee162b53347e058643f026f473cfc7b51ca1771eea23387d9167  clips.json (94 B)
    a582b707adcd365fb50666008bfea69c4bf39ef6815f696fb348b66a453f4185  memo.md (3504 B)
    ed57a1c02aa3bdad7808bd4433b8963aab8c7c3c5d21cc889d487e0aa8b6c137  paired_losses.csv (22023927 B)
    9066dab054e86d81b18c1e25fba7623a24656bab661d4dcd2650d30a3a5a3f18  probabilities.csv (10495595 B)
    ef75ee8c26a9f512f64cf554db5c204fcb907ac7401720e71126f2ffdfc23f9a  summary.json (3481 B)
    45122ae6b10a77281a41b4a1f2a52cc060f36e9618e8208753f6dcc6509d9a81  train_keys.json (1762580 B)

Re-attested at landing: `memo.md` and `summary.json` carry the verifier's input-metadata correction
(117964 evaluator states -> 465249 source rows), so their SHA-256 and byte size above are the corrected
values. The pre-correction values were memo.md 31dd4d10... (2646 B) and summary.json 688c7c8b... (3481 B).
The other four artifact hashes are unchanged. See memo.md "Corrections applied at landing".

## NOT VERIFIED

- The grain change: not comparable tick-for-tick with the all-tick design, the global guard denominator no longer holds the settled terminal snapshots that were 58 pct of source rows, and the discard of 0.66 near-duplicate rows per in-play cell was not quantified per bin.
- One fitted fold: fold 0 is an identity passthrough, so the fitted evidence is one season.
- Independent-corpus replication: none attempted.
- Any deployment, flag, registry, ledger, or global calibration claim.
