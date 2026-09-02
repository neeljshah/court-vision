# Intelligence + answer-layer gap finder (lane I2, 2026-09-03)

Read-only lane. Question: what stands between the answer layer and 10/10 that is
NOT human-gated. Every number below was measured in this session with the command
beside it. Calibration language only (Q6); honest FAIL cells are the deliverable.

## 0. Incident found first (Q8 premise check) -- the working tree was not HEAD

At 11:49 local the main tree had **3,154 tracked files differing from HEAD**
(`git status --short | grep -v '^??' | wc -l`). `git hash-object` matched
`resolver_registry.py` to 725a45aab (08-31), `gate_manifest.py` to 0c3cece7a (09-01),
`compose_comparables.py` to 479998122 (07-17): the S37, S38, S45 and S57 landings were
absent from disk while present in HEAD. All rewritten files carry mtime
`2026-09-02 10:32:11 -0500` = the author date of **7e473807c** "fix: normalize OpenCV
Hough line shapes" on branch `codex/synthcal-basketball` (NOT an ancestor of HEAD).
`git archive <sha> | tar -x -C <repo>` sets mtimes to the commit date, so this was a
PATHLESS archive-extract of a stale codex branch over master (the A6 landing recipe
without its `-- <paths>`). The live import confirmed it: `python -c "import
scripts.platformkit.answers.resolver_registry as r; print(hasattr(r,'_ask_lookup_note'))"`
printed `False` at 11:52. By 12:04 the tree was back to HEAD (14 files differ, all
in-flight lanes; `_ask_lookup_note` count 2). The resident MCP server (pid 11348,
`python -m scripts.platformkit.mcp_server.server`, created 11:41:42) was started INSIDE
the reverted window; its lazily-imported resolver code is whichever version was on disk
at first call. **Restart it (human).** The 50-probe test cannot see this class of
regression: it scored 29 red / 22 green on BOTH the reverted tree and HEAD (below).

## 1. The 50-probe envelope, run twice

    python -m pytest tests/platformkit/mcp_server/test_envelope_contract.py -q -p no:cacheprovider

| tree | result | red probes |
|---|---|---|
| main tree (reverted state, 11:47) | `29 failed, 22 passed in 88.37s` | A01 A06 A09 A11 A13 S01-S03 C01-C03 M01-M03 W01-W04 R01-R05 H01 X01 X02 X04 X05 X06 |
| HEAD ba2ba129e extracted to scratchpad + data/vault junctions | `29 failed, 22 passed in 68.99s` | identical 29 |

Causes, re-read from every red's assertion text: 28 x `OK_NO_STALENESS_DAYS` (no tool
emits `staleness_days`), 1 x `OK_NO_SOURCE_ARTIFACT`+`OK_NO_AS_OF` (H01 system_health, P3);
riders: W01-W04 `OK_ASOF_IS_WALL_CLOCK` (P2), X06 `OK_ASOF_UNPARSEABLE:'...(no rows)'`.
**Correction to S27/S38:** the 28 staleness reds were filed as "P1 (human)". P1 is
"wire `mcp/gate_manifest_tool.py` + restart the server". Emitting `staleness_days` on every
`ok` envelope is a different, smaller change inside `scripts/platformkit/mcp_server/tools.py`
(a safe build area per `.claude/rules/human-gated-paths.md`); only the server restart is
human. 28 of the 29 reds are therefore FIXABLE (F1 below), not gated.

## 2. 39 real questions through `tools.handler_for` (HEAD tree, 12:00 local)

Script `scratchpad/q39.py`; envelopes archived under `scratchpad/q39_head/`. Grade =
SAT only when all three hold: (a) `source_artifact` + `as_of` + status cited; (b) the
quoted number reproduces when the artifact is opened; (c) reviewer-grade: specific,
uncertainty stated, no edge language, staleness visible. "repro" = I opened the artifact.

| id | tool / question | status | as_of | repro | grade | why |
|---|---|---|---|---|---|---|
| Q01 | ask: win prob OKC vs DEN (nba) | ok p=0.5855 | wall clock | yes (CLI re-run 0.5855) | FAIL | as_of is the call time, corpus age hidden (P2) |
| Q02 | ask: MLB Brier on the calibration scoreboard | ok n=8,395 Brier 0.24052->0.24024 | 2026-07-23 (vault mtime) | yes (scoreboard row) | FAIL | source is gitignored + 41 d old; tracked S05 `mlb_reliability_2026-09-03.json` (39,162 rows, ECE 0.005918->0.008077) never consulted; no staleness field |
| Q03 | ask: why does lefty advantage on return hold (tennis) | not_supported | -- | n/a | FAIL | mechanism EXISTS (A09 phrasing resolves); token-subset test defeated by "why/hold/or/not" |
| Q04 | scouting: Shai Gilgeous-Alexander (nba) | ok 8/8 axes | 2026-07-26 | yes (clutch_fga_per_game pct 100.0, raw 4.4667, season_2025_26) | SAT | note names snapshot + mtime |
| Q05 | scouting: Shohei Ohtani (mlb) | ok 4/6 axes | 2026-07-18 | yes | SAT | misses stated |
| Q06 | scouting: Carlos Alcaraz (tennis) | ok 2/4 axes | 2026-07-09 | yes | SAT | misses stated |
| Q07 | comparables: Jokic k=5 | ok | 2026-07-26 + corpus_staleness_days 38.07 | yes (RMS over 78 shared attrs = 26.6288 recomputed) | SAT | |
| Q08 | comparables: Sam Hauser | ok | same | yes | SAT | |
| Q09 | comparables: Aaron Judge (mlb) | ok | 2026-07-18 + 45.98 d | yes | SAT | n_attrs 6 at floor 5 -- stated |
| Q10 | matchup: OKC vs DEN | ok 6/8 blocks | wall clock | n/a | FAIL | outer as_of = `_now_iso()` (compose_matchup:155) |
| Q11 | matchup: LAD vs NYY (mlb) | ok 3/8 blocks | wall clock | n/a | FAIL | same |
| Q12 | matchup: Alcaraz vs Sinner (tennis) | ok 2/8 blocks | wall clock | n/a | FAIL | same |
| Q13 | win_probability nba pregame | ok 0.5855 | wall clock | yes | FAIL | P2 |
| Q14 | win_probability mlb bottom 7, 3-2 | ok 0.768; bucket inn_07/diff_+01 n=1,587 Brier 0.1071 | wall clock | yes (`data/cache/calibration_grid/mlb_reliability_map.json`, generated 2026-07-18) | FAIL | bucket block cites no artifact/date; P2 |
| Q15 | win_probability tennis sets 1-1 | ok 0.4313; bucket UNMAPPED_STATE | wall clock | yes | FAIL | honest bucket miss; P2 |
| Q16 | injury: Thunder | refused 47.6 d > 7 d | 2026-07-17 | n/a | SAT | source_artifact is an ABSOLUTE path (minor) |
| Q17 | injury: Dodgers | refused 48.5 d | 2026-07-16 | n/a | SAT | |
| Q18 | injury: LeBron James | no_data | -- | n/a | FAIL | tools._injury_report passes the arg as `team=` only; a player name can never match |
| Q19 | receipts claim_survival nba | ok 138 cards, 0 eligible | 2026-09-01T23:34Z | yes | SAT | survival null, said so |
| Q20 | receipts verification all | ok overall=VERIFIED | 2026-09-01T23:34Z | yes | FAIL | headline VERIFIED with n_verified 0 (10 STALE, 1 UNCHECKABLE) |
| Q21 | receipts attribution mlb | ok | 2026-09-01T23:35Z | yes (condition_match 16,187; joins 0.0) | SAT | |
| Q22 | system_health: is the fleet on | ok fleet_on=false | none | n/a | FAIL | no source_artifact/as_of (P3) |
| Q23 | system_health: freshness SLA | RED 33/49 daemons | `generated_at` = epoch float | n/a | FAIL | P3 |
| Q24 | system_health: last burst | 2026-09-02T15:21Z | none | n/a | FAIL | P3 |
| Q25 | atlas: NBA top 5 | ok OKC 1728.092 band 0.0288 | prose "latest accepted game date per sport" | yes | FAIL | as_of not a date; `generated_at` 2026-09-01T21:38Z exists but not surfaced |
| Q26 | atlas: tennis top 5 | ok | prose | yes | FAIL | same |
| Q27 | atlas: MLB tracking MAE | ok 0.046311 | prose | yes | FAIL | same |
| Q28 | mechanism_exposure (all) | ok | 2026-05-24 | yes | SAT | returns the whole 1,317-sheet artifact (heavy) |
| Q29 | mechanism_exposure game_id=2025-10-21-GSW-LAL-0 (real) | no_data | -- | sheet EXISTS | FAIL | handler reads `games`/`rows`; artifact key is `game_sheets` -> 0/1,317 addressable |
| Q30 | mechanism_exposure bogus id | no_data | -- | n/a | SAT | |
| Q31 | tracking status: passes standing | ok "0 passes" | max artifact | true today (173-game sweep, 09-02 census) | FAIL | `honest_headline` is a hard-coded string in artifact_tools.py, not derived |
| Q32 | tracking status: newest artifact | ok list + max as_of | 2026-09-02T16:53Z | yes | SAT | |
| Q33 | tracking status: latest tennis verdict | ok | -- | n/a | FAIL | md packets returned as raw `packet_text`; `latest_harness_verdicts` None |
| Q34 | harness_health: K | ok K=14 | 2026-09-02T05:42Z | NO -- ledger has 15 rows, k_cumulative 15 at 15:25Z | FAIL | artifact generated 14:10Z; refresher not re-run |
| Q35 | harness_health: golden verdicts | ok brier_model 0.2298 vs close 0.1851 (BEHIND) | 2026-06-16 | yes | SAT | honest BEHIND |
| Q36 | harness_health: null-ship | ok 200 candidates, ceiling 0.1 | 2026-09-01 | yes | SAT | |
| Q37 | execution_status: verdict | ok | -- | artifact says `status: no_data`, `verdict: INSUFFICIENT` | FAIL | tool overwrites the artifact's own status with ok |
| Q38 | execution_status: as_of | ok | `2026-09-02T14:10:16+00:00 (no rows)` | -- | FAIL | unparseable (clv_daily_readout.py:138) |
| Q39 | execution_status: ledger counts | ok n_records 20, n_open 18 | same | yes | SAT | units only |

**Satisfying: 16 / 39.** Numbers opened: 11; reproduce: 10; stale: 1 (Q34 K=14 vs 15).
Zero edge language in all 39 (`edge_claimed:false` or framing present on every ok).

## 3. Intelligence layer: 30 of 151 sampled evenly (rows 3,8,...,148 of the sorted listing)

Script `scratchpad/intel30.py` (HEAD `intelligence_producers.PRODUCERS`, manifest rows,
refresher heartbeat, `grep -rl` for consumers outside the producer/map/tests).

| artifact | rows | mtime | producer | inputs found / newer | consumers | manifest d | S57 run |
|---|---|---|---|---|---|---|---|
| active_trend_signals.json | 3 | 06-02 | build_ai_chat_corpus | 0 / no | 1 | 91.93 | -- |
| anti_correlation_parlay_candidates.parquet | 764 | 06-02 | build_daily_picks | 0 / no | 2 | 91.93 | -- |
| archetype_scheme_advantages.json | 3 | 06-02 | build_archetype_scheme_matrix | 0 / no | 1 | 91.93 | -- |
| bench_starter_split.parquet | 81 | 06-02 | build_bench_starter_split | 1 (05-24) / no | 0 | 91.93 | -- |
| c1_clean_backtest_results.json | 4 | 09-02 | test_c1_clean_backtest | 4 (05-27) / no | 0 | 0.04 | ok |
| compound_signal_hunt_v3.parquet | 36 | 06-02 | hunt_compound_signals_v3 | 0 / no | 1 | 91.93 | -- |
| cv_anomaly_v2_validation.json | 15 | 06-02 | build_cv_anomaly_v2 | 0 / no | 0 | 91.93 | -- |
| cv_fatigue_trajectories.parquet | 183 | 06-02 | build_cv_fatigue_trajectories | 0 / no | 0 | 91.93 | FAILED (300 s) |
| cv_shot_clock_features_sidecar.parquet | 318 | 06-02 | build_cv_shot_clock_features_sidecar | 0 / no | 0 | 91.93 | -- |
| cv_shot_types_per_game.parquet | 664 | 09-02 | build_cv_shot_types | 0 / no | 1 | 0.05 | ok |
| daily_slate_2025-02-28.json | 12 | 06-02 | NONE | -- | 0 | 95.90 | -- |
| ft_rate_predictions.parquet | 26,016 | 06-02 | build_ft_rate_model | 3 (05-29) / no | 0 | 91.93 | -- |
| gt_weighted_forms.parquet | 99,157 | 06-02 | build_gt_weighted_forms | 0 / no | 1 | 91.93 | -- |
| int99_v1_vs_v2_diff.parquet | 27 | 06-02 | NONE | -- | 0 | 91.93 | -- |
| matchup_grid.parquet | 4,900 | 06-02 | build_matchup_grid | 0 / no | 5 | 91.93 | -- |
| officials_player_sensitivity.parquet | **0** | 06-02 | build_officials_cv_impact | 3 (05-29) / no | 1 | 91.93 | -- |
| opp_paint_allowance.parquet | 240 | 06-02 | build_opp_paint_allowance | 1 (05-29) / no | 12 | 91.93 | -- |
| pair_signatures.json | 20 | 06-02 | build_pair_chemistry | 0 / no | 0 | 91.93 | -- |
| parlay_scores_v2_demo_with_calibration.parquet | 27 | 06-02 | score_multi_leg_v2 | 0 / no | 0 | 91.93 | -- |
| per_player_confidence.parquet | 112 | 06-02 | build_daily_slate | 0 / no | 10 | 91.93 | -- |
| player_def_archetype_sidecar.parquet | 99,498 | 06-02 | build_player_def_archetype | 0 / no | 1 | 91.93 | -- |
| player_fingerprints.parquet | 221 | 06-02 | build_player_atlas | 0 / no | 37 | 91.93 | -- |
| pos_vs_pos_signals.json | 7 | 06-02 | build_position_vs_position | 1 (05-24) / no | 0 | 91.93 | -- |
| pra_arbitrage_opportunities_2026-05-29.parquet | 23 | 06-02 | NONE | -- | 0 | 91.93 | -- |
| rest_cv_impact.parquet | 30 | 06-02 | build_rest_cv_intel | 3 (05-27) / no | 3 | 91.93 | -- |
| scheme_indicators.json | 7 | 06-02 | build_defensive_schemes | 1 (05-24) / no | 0 | 91.93 | -- |
| shot_quality_live_validation.json | 12 | 06-02 | eval_live_shot_quality | 0 / no | 0 | 91.93 | -- |
| streak_excluded_players.json | 4 | 06-02 | build_streak_signatures | 0 / no | 0 | 91.93 | -- |
| team_tempo_spacing.parquet | 210 | 06-02 | build_team_tempo_spacing | 0 / no | 6 | 91.93 | -- |
| trade_profile_shifts.parquet | 263 | 09-02 | build_trade_intel | 1 (05-29) / no | 2 | 0.04 | ok |

Totals over 30: **reproducible today (producer ran and rewrote the file): 3**; failed:
1; no producer: 3; producer present but never exercised: 23. Consumed by >= 1 non-test
module: 15; **zero readers: 15**. Stale versus its own inputs: **0 of 9** with a detected
input (inputs are May 2026, older than the June artifact -- S57's finding holds on the
sample). Registered in the manifest: 30/30 (27 at 91.93 d, 3 at <= 0.05 d). One
zero-row artifact (`officials_player_sensitivity`, the documented placeholder). Whole
layer: 129/151 at 2026-06-02 content, 22/151 rewritten 2026-09-02 (`os.stat` census).
Nothing in the MCP surface reads `data/intelligence` -- `ask`/scouting/comparables read
`data/cache/profiles/*`; so the layer's answers are served by NO tool today.

## 4. Fixable under scripts/platformkit/** (ranked by probes/answers closed)

| # | defect (measured before) | file : one-line fix | test that pins it |
|---|---|---|---|
| F1 | 0/13 tools emit `staleness_days`; 28/50 probes red for it alone | `mcp_server/tools.py` `handler_for`: wrap every handler so an `ok` envelope gains `staleness_days = (now - parse(as_of or source mtime)).days`, `as_of_source` labelled | `tests/platformkit/mcp_server/test_envelope_contract.py` (28 probes flip; H01 stays P3) |
| F2 | 0/1,317 exposure sheets addressable by game_id (Q29) | `mcp_server/artifact_tools.py` mechanism_exposure: `value.get("game_sheets", value.get("games", value.get("rows", [])))` | `tests/platformkit/mcp_server/test_artifact_tools.py` (real id -> ok, bogus -> no_data) |
| F3 | execution_status says ok over an artifact whose own status is no_data / verdict INSUFFICIENT; as_of `... (no rows)` unparseable (Q37, Q38, X06) | `artifact_tools.py` execution_status: pass the artifact's status through when it is one of the five; `pm_trading/clv_daily_readout.py:138`: `as_of = max(timestamps) or now_iso`, put "no rows" in `note` | `test_artifact_tools.py` + `tests/platformkit/test_scoreboard.py` |
| F4 | matchup_preview outer `as_of` = wall clock 3/3 (Q10-12) | `intel_query/compose_matchup.py:155`: `as_of = max(block as_of)`, add `computed_at` + `corpus_staleness_days` (the S38(d) pattern) | `scripts/platformkit/intel_query/test_compose_matchup.py` |
| F5 | mechanism phrasing: "why does X hold or not hold" -> not_supported while "what does the evidence say about X" -> ok (Q03 vs A09) | `answers/resolver_registry.py` mechanism_effect: try `_mech_tokens(n) <= q_tokens` (name contained in query) before the current `q_tokens <= _mech_tokens(n)` | `scripts/platformkit/answers/test_mechanism_effect.py` |
| F6 | calibration_number serves a gitignored 41-day-old vault file (no_data on a clone) while tracked S05 `docs/evidence/calibration/<sport>_reliability_2026-09-03.json` exists (Q02) | `resolver_registry.calibration_number`: read the newest tracked reliability json (ece_before/after, input_rows, prereg seal) first, scoreboard as fallback, cite which | `answers/test_calibration_scoreboard_regex.py` + `test_resolver_registry_routing.py` |
| F7 | analytics verification headline `overall: VERIFIED` at n_verified 0 / 10 STALE / 1 UNCHECKABLE (Q20) | `analytics_verify` sentinel producer: `overall = "STALE"` (or INSUFFICIENT) unless n_verified > 0 and n_discrepant == 0 | `scripts/platformkit/analytics_verify/test_*` |
| F8 | injury_report tool cannot answer a player (Q18): `team=tp, player=args.get("player")`, schema exposes no `player` | `mcp_server/tools.py` `_injury_report`: `player=args.get("player", tp)` after confirming OR semantics in `edge_facts_resolver`; make `source_artifact` repo-relative | `tests/platformkit/mcp_server/test_edge_refusal.py` + `answers/test_edge_facts_resolver.py` |
| F9 | strength_atlas `as_of` is prose; `generated_at` 2026-09-01T21:38Z unused (Q25-27) | `artifact_tools._as_of`: prefer `generated_at` when `as_of` does not parse; carry the prose as `as_of_note` | `test_artifact_tools.py` |
| F10 | tracking_program_status `honest_headline` is the constant "0 passes"; tennis packet verdict unreadable (Q31, Q33) | `artifact_tools.tracking_program_status`: read the headline from the newest `harness_sweep_*` JSON (`docs/evidence/tracking`), drop the constant; surface `verdict` from md front-matter or return `no_data` for the field | `test_artifact_tools.py` |
| F11 | harness_health K=14 served while the ledger holds 15 (Q34): refresher last ran 14:10Z | not a code fix: `artifact_refresh --once` before serving; the OS task is S24's human arm. F1 makes the 2.7 h age visible | `test_artifact_refresh.py` |

F1-F4 alone close 31 of the 39 FAIL cells' first causes (28 staleness + Q29 + Q37/38 + Q10-12).

## 5. Human-gated / not this lane (5)

1. **P1** wire `mcp/gate_manifest_tool.py` into `tools.TOOLS` + restart the resident MCP server.
2. **P2** `answers/winprob_dispatch.py:93` corpus `as_of` + `computed_at` + `corpus_staleness_days` (assigned to Neel by the plan; path itself is not gated). Add `source_artifact`/`generated_at` to the `bucket_calibration` block (Q14) in the same diff.
3. **P3** `_system_health` cites its three artifacts; convert `freshness_sla.generated_at` (epoch float) at the boundary.
4. **Restart pid 11348** (started 11:41:42 inside the reverted-tree window) -- section 0.
5. **Arm the S24 scheduler** (`SCHTASKS` line in artifact_refresh.py) so Q34-class staleness cannot recur; never armed by a lane.
No producer under `intel/`, `src/`, `api/`, `kernel/` or `scripts/team_system/` was needed for any finding above (S57's "0 gated producers" reproduced on the 30-sample).

## 6. Proposed register rows (ids allocated by the orchestrator only)

| area | gap (measured before) | bar |
|---|---|---|
| ops | pathless `git archive 7e473807c \| tar -x` rewrote the main tree at 10:32:11 (3,154 tracked files diverged at 11:49; S37/S38/S45/S57 absent from disk ~80 min; MCP server started inside the window). No guard on the A6 recipe | a landing helper under scripts/platformkit that refuses an archive without `-- <paths>` and diffs the extracted set against HEAD; 1 test; rail line added to VERIFIER_CONTRACT A6 |
| analytics | `staleness_days` emitted by 0/13 tools (28/50 probes) -- F1 | 28 probes flip; envelope 21 -> 49 green with no assert weakened; H01 remains the only red until P3 |
| analytics | mechanism_exposure game_id lookup 0/1,317 -- F2 | a real id returns its sheet verbatim; bogus id no_data; 1 test |
| analytics | execution_status status/as_of -- F3 | tool status == artifact status; X06 `as_of` parses; probe X06 red -> green (staleness only after F1) |
| analytics | matchup_preview as_of wall clock 3/3 -- F4 | as_of = data date on M01-M03; `computed_at` separate |
| analytics | mechanism phrasing miss (Q03) -- F5 | 3 phrasings of one registered mechanism resolve to the same rows; existing 19 tests unchanged |
| analytics | calibration_number reads a gitignored 41-d file -- F6 | answers cite the tracked S05 artifact + prereg seal on all 4 sports; no_data on a clone becomes ok |
| analytics | sentinel `overall: VERIFIED` at 0/11 verified -- F7 | headline word never VERIFIED when n_verified == 0 |
| analytics | 15/30 sampled intelligence artifacts have zero readers and 0/13 tools read the layer | either a resolver category serving the consumed subset with staleness, or a documented RETIRED list -- decision row, not a build row |

## NOT VERIFIED
- The 39 answers were run in a scratchpad copy of HEAD with junctions to `data/`, `vault/`,
  `.bot_state`; the injury `source_artifact` absolute paths in Q16-Q18 therefore name the
  scratchpad. Outcomes on the resident server (pid 11348) were not probed.
- Grades in section 2 are one reviewer's; (c) is a judgement call, (a)/(b) are mechanical.
- The intelligence consumer count is a `grep -rl` of the basename over `.py` files; a reader
  that builds the path from fragments is missed (same caveat as S57 section 7).
- The 10:32:11 attribution rests on mtime == author date of 7e473807c; the invoking
  session/command was not identified. The repair (tree back to HEAD by 12:04) was not mine.
- F8's OR-vs-AND semantics in `edge_facts_resolver.injury_report` were not read.
- Nothing was fixed; every F-row is a proposal with its before measurement.
