VERDICT: DONE
# S327 pre-start M0 table
Spec: `docs/evidence/tracking/specs/S327_spec.md`. Prereg: `docs/evidence/harness/S327_prestart_m0_prereg_2026-09-08.md`
(SEAL `a7df4a23a11f9a1c70dc0e2324c4875d5dffd8522ea26811113f1787e1e57a5e`). Interpreter:
`C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe`. Wall time: finisher pass 2026-09-08 13:38-19:02Z;
census+build step ran in <1 min, peak RSS 1048.7 MB (budget 1200 MB; free system RAM was ~2.2 GB at the time,
so the run was kept to one bounded row-group sample per large quote store -- see "why" below, not a full
13.5 M-row rescan -- rather than risk the RAM guard).
## Store census (31 rows; full table `store_census.csv`)
TARGET (5 archive types, 16 files): `nba_checkpoints_full` (465249 rows), `wnba_checkpoints_full` (18650),
`mlb_pitch_states__2022..2026` (301717 total), `soccer_states__{combo_eng_ger,combo_esp_ita,eng1,esp1,ger1,
ita1,wc_2026}` (95266 total), `tennis_states__{atp,wta}` (55075 total). **0 of the 5 archive types has any of
start_ts/start_time/commence_time/start_utc/tip_ts** -- checked against every column name in every file.
QUOTE-CANDIDATE (8, used): `gate_corpus_nba_close` (1814), `gate_corpus_mlb_close` (39162), and the
nba/wnba/mlb/soccer/soccer_intl/tennis `*_price_series.parquet` (8.40M/0.97M/13.47M/0.20M/2.26M/1.85M rows).
EXCLUDED (6, reason given): `clv_close_legs_cache.jsonl` ABSENT-IN-WORKTREE; `prop_close_lines.jsonl` (m16,
326 MB) is player-prop decimal odds, not a game moneyline; `kalshi_market_scan.json` (m17) is one live
snapshot, no per-quote timestamp series; `clv_ledger.jsonl` (m18's real sink -- `append_settlement`'s default
path; the spec-named `clv_close_legs_cache.jsonl` is ABSENT) is a 20-row paper-bet ledger whose probability
fields (`taken_decimal`, `model_prob`) match no market-probability name the builder accepts; `book_depth/
kalshi/` and `kalshi_trades/` are empty directories; `inplay_history/{sport}/2026-07-27.jsonl` is a single
in-play day (`phase=in_play` on every row) in the same Kalshi scheme as the price series already used.
## Join census (16 sport x season groups; full table `join_census.csv`)
Every group: n_pre_start = n_at_tip = n_first_inplay = 0; n_none = n_events. Totals: nba 1593/1593 NONE,
wnba 85/85, mlb 973/973 (5 seasons), soccer 5014/5014 (7 leagues), tennis 40588/40588 (atp 29572 + wta
11016) -- 48253 events censused, 0 joined anywhere. `p0_diff_gt_005` = n/a everywhere (nothing joined to
compare). Unmapped participant keys: 0 for every sport -- not clean mapping, but because none of the used
quote stores carries separable home/away fields, so the pair-match fallback (the only path that calls the
name map) never fires; `prestart_m0_unmapped.json` is `{}` per sport, honestly.
**Why (verified, not assumed):** (1) `build_table()` skips a quote whenever its matched event's `start_ts` is
None; since 0/5 archive types carry a start-time field, that per-event gate is closed for every event before
any quote can attach -- true regardless of which or how many quote rows are supplied, so a bounded first-
row-group sample of each large price series proves the same result a full rescan would. (2) independently,
three incompatible event-ID schemes coexist per sport (official league ID e.g. NBA `0022400061`; ESPN
numeric e.g. `401704627`; Kalshi slug e.g. `KXNBAGAME-26APR26BOSPHI`) with no shared home/away fields to
fall back on. One partial exception: `wnba_checkpoints_full` carries an `event_key` column in the *same*
Kalshi-slug scheme as `wnba_price_series` (5/5 sampled keys match format) -- checked as a possible real join
-- but (1) still blocks it (no start_ts), and `close_time` in the price series was checked as a start-time
proxy and measured to be the market's **close/settlement (game end)**, not the start (WNBA sample: ticks
begin ~38 h before `close_time`, 99.9% of ticks fall before it) -- so it must not be substituted for start_ts.
## PROPOSED forward capture
`docs/research/organization-sprint/S327_PROPOSED_prestart_capture.md`, PROPOSED only, no daemon edited.
SHA-256 (LF-normalised): `f1850a9b901977d0fe593ed4bc8d116bfc423a07f37c1786c6a12fbfa2fa7705`.
EYE CHECK: NONE.
NOT VERIFIED:
- Whether any un-named store outside the spec's list carries a real start-time field (out of scope here).
- AT_TIP/FIRST_INPLAY remain proxies by definition (sealed rule); moot this row, 0 rows reached them.
- Venue prices (kalshi/polymarket) are not sportsbook closes; name mapping untested at scale (0 rows
  exercised it). p0 was never read as a probability (rating-column test); confirmed, not assumed.
SHA-256 (LF-normalised): builder `b34d59b036fb8d9f292002580c894cc06b3ef39dbc0f50203acd22c353242de6`; test
`e7b7965e9571f92c0ef9716958e190fb722d34e3de4e78b551c482e5ac3017bb`; `store_census.csv`
`8e476f3c201d4344af071f6266a5aa1ed0a9e0fd86ed676b117095a13e75e092`; `join_census.csv`
`9d0447fff67a3c4aa685ef1512dff0fb8642ba2cca6ee6035b05b5a541b22948`; `prestart_m0_unmapped.json`
`177d7698ce69bf381c955afdfec8ccd510ef7b8b2400ffc0cf99245102fc9df0`; `prestart_m0_name_map.json`
`3979a6fc5f84a5ff4231f7994519e4f9c8da32604931634d80c8223c937f4319`.
Proposed ledger line:
`2026-09-08 | data | S327 | 48253 events censused across 16 sport-season groups, 0 pre-start/at-tip/first-
inplay joins anywhere (0/5 state-archive types carry a start-time field; quote stores use 3 incompatible ID
schemes) | DONE`
