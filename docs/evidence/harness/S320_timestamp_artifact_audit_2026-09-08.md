VERDICT: CLOSED AT LIMIT -- the sealed 100-state selection rule could not run; no audit or replay executed.

S320 finisher pass. Machine: local `basketball_ai` interpreter (`C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe`).

Premise remeasured (independent of the codex-lane prepare pass): input
`data/cache/inplay_odds/nba_checkpoints_full.parquet`, 2,829,826 bytes,
SHA-256 `5ea6498d88bf7548395c700c7239641dcbd1d641bdaddb5a6b63fcf0ea8909e5`.
Columns: game_id, game_date, ts, period, game_clock_s, score_home, score_away,
margin, market_prob, traded, market_ticker, outcome_home_win, venue. 465249
ticks, 1593 games, 2 derived seasons (2024-25, 2025-26), 6 distinct
`period` values (1-4 plus 2 overtime periods), 271154 zero-clock ticks.
`status` and `received_at` are ABSENT; the S309 terminal mask is
`period >= 4 and game_clock_s == 0`.

Selection stop (prereg-defined, not a code bug): `select_states` partitions
the full 465249-tick population by exact `period` x |margin| bucket (0-3,
4-9, 10+) x clock bucket (>300s, 60-300s, <60s, ==0s) and found 63
non-empty strata. The sealed prereg's own binding rule: "If more than 20
strata are non-empty, this binding requirement cannot produce both exactly
100 pairs and five per non-empty stratum; stop as PARTIAL and report the
non-empty-stratum count without auditing or scoring." Five-per-stratum over
63 strata needs >=315 states, more than the fixed n=100. This is the real
population (period reaches 6 from overtime), not a synthetic case. Regulation
alone has 48 non-empty strata (need 240); overtime adds 15. No (game_id,
state_ts) pair was drawn, so `audit_states`, `prefix_replay`, and the frozen
recalibrated null N were never invoked -- there is nothing to fit or replay.

Stratum census (full table, 63 rows, in `states.csv`): n_ticks per stratum
ranges 3 (`p5_m10_plus_c60_300`) to 133026 (`p4_m10_plus_ceq_0`); n_games per
stratum ranges 2 to 1584. All 63 strata are non-empty; 0 excluded.

Audit table: NOT RUN (0 rows; `audit.csv` is header-only:
game_id,state_ts,stratum,check,verdict,reason).
Replay deltas (N, M0): NOT RUN (0 rows; `replay.csv` is header-only:
game_id,state_ts,stratum,arm,p_full,p_truncated,p_delayed,delta_b,delta_c,
records_in_window,verdict). Violating states: none, because none were drawn.

EYE CHECK: NONE.

Artifacts (LF-normalised SHA-256):
- `states.csv` (6041 bytes): `436c69714f9fda8fe9aa308437861d118ba6051152845d28ca506d287b1a7ff6`
- `audit.csv` (46 bytes): `98b441c15bdf824c5f34d57be49e478c3eb0552af09acb0715f65910afc45b36`
- `replay.csv` (100 bytes): `95ec7ff875e1b763ac33950f2ce2bca2fd0ed77543a7bc305ab05bee5ab57ccc`

Wall time: 2026-09-08 18:04:13 UTC (finisher measurement pass, about 28 seconds).

Sign convention: improvement equals baseline loss minus candidate loss;
positive means candidate better. Not applicable here -- no comparison ran.

Proposed ledger line:
`2026-09-08 | in-game calibration | S320 | CLOSED AT LIMIT: 63 non-empty period x margin x clock strata (need >=315 states at 5/stratum) exceed the sealed 100-state rule's 20-stratum limit; premise 465249 ticks / 1593 games / 271154 zero-clock ticks; 0 states selected, 0 audited, 0 replayed | CLOSED AT LIMIT`

NOT VERIFIED:
- The sealed 100-state list, the audit table, and the N/M0 replay deltas -- none ran; the prereg's own stop condition fired first.
- Whether a corrected stratum design (e.g. collapsing period >= 5 into one overtime bucket) would produce <=20 strata; that would require editing the SEALED prereg, which this pass may not do.
- Timestamp-only validation cannot certify a feed that retrospectively overwrites its own records.
- 100 states are a screening, not a census; a clean audit would not have been a gain.
- Any calibration gain, deployment, flag, registry, register, or ledger action.
