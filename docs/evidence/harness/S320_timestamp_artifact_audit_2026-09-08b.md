VERDICT: PARTIAL (tick-order only; availability and polarity NOT VERIFIED, so the sealed bar cannot fully clear) -- 0 accepted terminal / future / wrong-target states among 313 sealed states (40 terminal-by-construction states in the period >= 4 clock == 0 strata are all flagged by the S309 mask and accepted by nothing); 0 prefix prediction changes (n = 313 x 2 models); every 60 s delayed change (211/313 per model) traced to a record inside the window; settlement check: 1/313 states (000262, game 401873341, the game's own final tick) is flagged VIOLATION, not accepted.
S320 attempt 2 fix 2d correction pass (VERSION b). Machine: local `basketball_ai` interpreter (`C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe`).
Premise remeasured: input `data/cache/inplay_odds/nba_checkpoints_full.parquet`, 2829826 bytes, SHA-256
`5ea6498d88bf7548395c700c7239641dcbd1d641bdaddb5a6b63fcf0ea8909e5`; tabular, resolution not applicable.
Columns: game_id, game_date, ts, period, game_clock_s, score_home, score_away, margin, market_prob, traded, market_ticker, outcome_home_win, venue. 465249 ticks, 1593 games, 2 derived seasons (2024, 2025), periods 1-6, zero-clock share 271154/465249 = 0.582814793799. `status` and `received_at` are ABSENT.
Prereg: `S320_timestamp_artifact_audit_2026-09-08b_prereg.md`, seal `a735f99d397d17d62b53f9ae29d5193147443e300e8f63c1db43796611ed88b8`.
Strata: 63 non-empty (period x |margin| bucket x clock bucket); sealed n = 313 (5 per stratum, all-if-fewer at `p5_m10_plus_c60_300`, 3 eligible/3 drawn); every other stratum drew exactly 5. Full census in the prereg and `states.csv` (314 lines incl. header).
Audit table (n=313 states per check; NOT_VERIFIED counted separately from ACCEPTED/VIOLATION):
| check | ACCEPTED | NOT_VERIFIED | VIOLATION |
|---|---:|---:|---:|
| availability | 0 | 313 | 0 |
| status | 273 | 0 | 40 |
| polarity | 0 | 313 | 0 |
| duplicate | 313 | 0 | 0 |
| settlement | 312 | 0 | 1 |
Flagged states (40 unique, listed in `audit.csv`): all 5 states in each of the 8 clock==0 x period>=4 strata (p4/p5/p6 x m0_3/m4_9/m10_plus ceq_0; p6_m10_plus_ceq_0 has 0 eligible ticks, contributes none) trip the S309 terminal mask (period >= 4 and game_clock_s == 0) by construction -- `terminal_s309_mask`. State `000262` (game 401873341, `p5_m10_plus_ceq_0`) is also the game's own final tick -- `state_is_final_tick`. This reproduces, on a stratified sample, the S309 finding that zero-clock ticks are structurally terminal-like; the harness correctly flags every one, it accepts none of them.
Strata note: the 8 clock==0 x period>=4 strata are terminal by definition of the sealed bucketing, not a leakage finding -- they test whether the S309 mask fires, not whether availability leaks. Recommend future preregs keep them as a separate mask-check stratum (as done here) rather than excluding them outright.
Replay (frozen train-only null N: 1-feature logistic recalibration of logit(market_prob), fit once, intercept=-0.018406691 slope=0.965524222; M0: latest raw market_prob, no recalibration). n=313 each:
| model | max delta_b | n delta_b>0 | max delta_c | n delta_c>0 | replay VIOLATION rows |
|---|---:|---:|---:|---:|---:|
| N | 0.0 | 0 | 0.337200 | 211 | 0 |
| M0 | 0.0 | 0 | 0.335000 | 211 | 0 |
Bar holds for replay: 0 prefix (delta_b) changes; every nonzero delayed (delta_c) change traces to a record inside the 60-second window (0 replay VIOLATION rows for either model).
`replay.csv` schema restored to the sealed prereg order (state_id, game_id, state_ts, stratum, model, p_full, p_truncated, p_delayed, delta_b, delta_c, records_in_window, verdict; delta_b/delta_c are plain 6 dp floats) plus `delta_b_micro`/`delta_c_micro` appended as additive extras (value x 1e6, rounded, sign kept, 6-digit zero-pad); all values unchanged from the fix 2b/2c run. EYE CHECK: NONE.
Corrections (fix 2d, 2026-09-08): restored the sealed `delta_b`/`delta_c` float columns that fix 2b removed (B2 NON-ADDITIVE SCHEMA); `delta_b_micro`/`delta_c_micro` are kept as additive extras only, never the sole representation of a delta -- a field will not be removed or renamed again. Two verifier NEW GAPs are stated here as open limitations, not resolved: (a) N is a fresh train-only median-cut row fit against this parquet, not the landed S310/S309 grouped-CPCV null of the same name -- reconcile the two identities before any scoring row reuses this audit's N; (b) the reported N/M0 predictors filter history at state time internally, so full-vs-prefix equality is structural, and the planted-future unit test exercises a substitute callback, not either reported predictor -- this audit certifies the replay harness (0 prefix leakage through the harness's own state cut), not the predictors' own internal leakage path.
NOT VERIFIED:
- Availability (tick-order only; `received_at` absent from the source; sealed rule NOT_VERIFIED not ACCEPTED).
- Polarity (`side`/`home` columns absent from the source; venue alone is insufficient).
- Whether excluding clock==0 x period>=4 before sampling changes the terminal-contamination rate.
- 313 states are a screening, not a census; a clean audit would not have been a gain.
- Timestamp-only validation cannot certify a feed that retrospectively overwrites its own records.
- Any calibration gain, deployment, flag, registry, register, or ledger action.
Wall time: 2026-09-08 19:42:55 UTC to 2026-09-08 19:44:08 UTC (about 73 seconds, this fix 2d rerun).
Artifacts (LF-normalised SHA-256; replay.csv now carries delta_b/delta_c plus delta_b_micro/delta_c_micro):
- `states.csv` (22064 bytes): `6f8f617e1701dc288338b8600de0f94eda34364d26187590c6934d38a2a88331`
- `audit.csv` (164770 bytes): `c1ad37b3d0dece86ff4db7e91287943bc5750834e4612618391ec8b8d238ec72`
- `replay.csv` (78001 bytes): `496149df75a2698238575d6e50f7437c4ef6c6b620203de7ef8c3e7f5256816f`
SCAN: restricted-vocabulary word rail + retracted-figure digit rail -- 0 non-exempt hits, except one expected coincidence: state `000302` (N model) delta_c=0.119957 contains the digits of a retracted figure as a pure decimal substring (fix 2b's micro-unit conversion had removed this coincidence; restoring the sealed float column brings it back). The measured value is unchanged and this is not the retracted figure itself. Standalone `54` hits are ISO-8601 timestamp minute fields only (e.g. `T02:54:05`), exempt as before. 0 hits elsewhere.
Tests: `tests/platformkit/test_s320_state_audit.py` (7 passed, alone); `tests/platformkit/test_loc_rail_scope.py` (1 passed, alone).
Proposed ledger line:
`2026-09-08 | in-game calibration | S320 | attempt 2 fix 2d: sealed VERSION b (5/stratum, n=313 across 63 strata) -- 0 accepted terminal/future/wrong-target states, 0 prefix changes, every delayed change traced to a record in the window; availability and polarity NOT VERIFIED (no received_at/side/home); status/settlement flag but do not accept the 40 terminal-by-construction + 1 final-tick states via the S309 mask; replay schema restored additive (delta_b/delta_c plus micro extras) | PARTIAL (availability and polarity NOT VERIFIED)`
Orchestrator adjudication (2026-09-08, Fable): the attempt-2 verifier REJECTED twice -- the replay null is a fresh single-cut calibrator, not the landed chronological-fold null the spec requires, and the fix passes changed the landed attempt-1 module's API (B2). Landed CLOSED AT LIMIT (attempt 2) with both REJECTs recorded; the audit counts stand as a screening (0 accepted terminal / future / wrong-target states among 313; 0 prefix changes under the substitute null; availability and polarity NOT VERIFIED); the module lands under a separate name so the attempt-1 route stays byte-identical; the audit with the landed null identity and an external as-of join is S328.
Vocabulary follows contract Q6; automated scan required.
