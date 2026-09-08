VERDICT: CLEAN -- 313 sealed states, 40 excluded by the S309 terminal mask, and 273 active states x 2 arms x 4 delays = 2184 replay rows; 0 prefix changes, 0 access violations, and 0 untraced delay changes.
S328 cites `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q. Machine: local `basketball_ai`.
Binding before-condition rerun: `scripts/platformkit/ingame/s320_state_audit_attempt2.py:152-156` passes a game frame to each predictor; the N path filters internally at `:167-170` and `:192-195`.
The landed S320 memo explicitly reserves the landed-null external as-of join for S328, so no landed row already exercised this four-delay replay: PROCEED.

Opened input: `docs/evidence/harness/S320_timestamp_artifact_audit_2026-09-08b/states.csv`, 22378 bytes.
Sealed states: 313 across 63 non-empty strata; all strata have 5 states except `p5_m10_plus_c60_300` with 3.
Preregistration: `docs/evidence/harness/S328_asof_join_falsification_2026-09-08_prereg.md`, seal `fcfe9d6b134781fdc8958fd55b69f738b05fe587b3dc15f676d051d476b5878b`.
Bootstrap seed 328 was selected after the seal because the preregistration is silent on a seed; it is therefore NOT sealed.
Arms: N is the landed S310/S309 grouped-CPCV null, never refit. For 2025-26 it uses frozen `(a, b) = (0.9374022892177405, 0.021210521231280095)`; 2024-25 is identity.
The full-precision tuple reproduces the two pinned S310 rows within 1e-9 in `tests/platformkit/test_s328_run_replay.py`; S320_SUBSTITUTE is raw latest market probability because S321 attempt 2 is not landed.

2026-09-08 fix 1b: restored the frozen system record byte-exact from the parent, retained the proposed result line only below, corrected the coefficient precision and input byte count, replaced direct survival scoring with the shared CPCV route, added runner coverage, and regenerated both CSVs.
Survival uses `scripts/platformkit/eval_gate/cpcv_engine.py:95-157` with four frozen groups, one test group, and one-day embargo; the evaluator applies symmetric purge/embargo at `:57-65` and `:141-143`.
Prepared sealed module `scripts/platformkit/ingame/s328_asof_replay.py` is byte-identical; the preregistration is unchanged. EYE CHECK: NONE.
Focused test: `test_s328_asof_replay.py` -> 4 passed in 1.70s. Runner test: `test_s328_run_replay.py` -> 2 passed in 1.49s.

Replay (n=273 active states per arm/delay; access violations=0):
| arm | delay s | n changed | max abs probability delta | n delay-window records |
|---|---:|---:|---:|---:|
| N | 0 / 30 / 60 / 120 | 0 / 206 / 211 / 243 | 0 / 0.347350 / 0.328581 / 0.343981 | 0 / 273 / 353 / 619 |
| S320_SUBSTITUTE | 0 / 30 / 60 / 120 | 0 / 206 / 211 / 243 | 0 / 0.355000 / 0.335000 / 0.360000 | 0 / 273 / 353 / 619 |

Conclusion survival is descriptive calibration scoring through CPCV: 273 evaluator records and 230 game clusters at each delay; delta is N loss minus substitute loss.
| delay s | Brier N | Brier sub | Brier delta 95pct CI | log N | log sub | sign vs delay 0 |
|---:|---:|---:|---|---:|---:|---|
| 0 | 0.175206 | 0.175745 | -0.000538 [-0.001348, +0.000221] | 0.515174 | 0.518111 | survives |
| 30 | 0.174946 | 0.175524 | -0.000578 [-0.001503, +0.000270] | 0.509577 | 0.511781 | survives |
| 60 | 0.175325 | 0.175974 | -0.000649 [-0.001517, +0.000193] | 0.507348 | 0.509234 | survives |
| 120 | 0.183590 | 0.184505 | -0.000915 [-0.001887, -0.000059] | 0.533479 | 0.535640 | survives |

2026-09-08 lander: ACCEPT (codex-sol, contract A/B/Q) on fix 1b (CPCV re-route with purge and symmetric embargo; full-precision landed-null coefficients; ledger hunk removed; runner test added); NEW GAPS in the ledger as listed by the verifier.
SCAN: TRUE -- 0 non-measured hits in the S328 changed content. The sole measured collision is `p_delay_probability` 0.54 for state 000025 at delays 30 s and 60 s.
Proposed result line: `2026-09-08 | in-game calibration | S328 | 313 sealed states (273 active) replay reproduced: 0 prefix changes, 0 access violations, 0 untraced changes; CPCV survival used purge plus symmetric embargo (n=2184) | CLEAN`.
Wall time: local module run 181 s; observed peak RSS 698499072 bytes, below the 1.2 GB cap.
LF-normalized SHA-256:
`replay.csv` `8bc686a0d641d7b5911045b28cfb8995211ad0a843ca1a80b29c6a2ae3b979d6`
`survival.csv` `21352e975a3439302377eac08ab2feba1854687c6416deff544a8f8b563435a0`
`s328_run_replay.py` `52ac9da09c5df81e2da8003049b4e1b0df0df8dd10eacec9e0fe8bd3caf6cc1f`
`s328_asof_replay.py` `23c5abc7b669c7e7a837ec483d660b5d097c3532a454fa201a60f2234f503626`

NOT VERIFIED: historical availability without `received_at`; ordering only. The 313-state screen is descriptive calibration evidence, not a deployment, flag, registry, or global conclusion.
