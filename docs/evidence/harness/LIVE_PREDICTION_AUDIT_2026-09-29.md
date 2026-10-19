# Live prediction audit, 2026-09-29 (~17:00Z, read-only)

Orchestrator 2. Six read-only Sonnet sweeps (two passes of three: served/pregame, in-game scoreboard arms, signal registries), with the load-bearing facts re-checked by the orchestrator. Mtimes are UTC unless marked. Calibration language only; arm A is the raw venue YES mid, never "devigged" (S495).

## Bottom line

- **No surface produced a fresh, model-based, market-calibrated number in the last 24 h, for any sport.**
- What is fresh is capture: state, Kalshi books and Polymarket MLB. The three capture supervisors were relaunched about 14:11Z on 09-29, after dying about 03:16Z.
- Paper quotes anchor on the observed mid by design (`scripts/platformkit/execution/quote_engine.py:3-5`), so no model value reaches a quote.
- **The served producer is dark.** `data/frontend/predict_service/_heartbeat.json` has mtime 2026-09-01T09:43Z and `cycle_count` 0. Every `latest.json` is from 2026-07-19 to 07-27. No predict_service, supervisor, live_loop or API process is running on this box.
- **The only scoreboard receipt is 2026-09-24:** MLB, 4 games, every cell INSUFFICIENT. Arms B, C and D were `model_not_reconstructible` on all 1,991 ticks.
- **Arm E has never produced a row.** `docs/evidence/forward/registry_e/2026-09-26.json` is REFUSED with `config_not_effective`.
- **New defect found by this audit (orchestrator-verified):** every ESPN-sourced state row carries `scheduled_start_utc = null` and `date = null` (reason `missing_scheduled_time`). This covers nfl, nba, wnba, soccer, tennis and ncaaf, archive-wide, with 0 exceptions on every shard checked from 09-23 to 09-29.
  - Cause: ESPN sends minute-precision instants (`2026-09-29T00:15Z`). `local_state_capture_dates.venue_instant` returns None for that form, while `...T00:15:00Z` parses.
  - The state heartbeats show it directly: `timestamp_parse_errors` equals `rows_written` for every ESPN sport (tennis 746,496 of 746,496). MLB, which comes from statsapi, is unaffected.
  - The bridge reduces `(date, home, away, start)` per game (`forward_capture_bridge.py:53-63`), so every non-MLB game links on teams alone, with no date or start evidence.

## 1. Pregame and served surfaces

| Surface (code) | Output | Fresh <24 h? (newest file, mtime) | Last calibration vs market (artifact) | Input freshness | Exact blocker |
|---|---|---|---|---|---|
| predict_service scheduler (`predict_service/scheduler.py:116,222`; POD `python -m supervisor --profile paper`, `supervisor/stack_specs.py:259`) | `data/frontend/predict_service/<sport>/latest.json` | NO. `_heartbeat.json` 09-01T09:43Z, `cycle_count` 0, "boot-beat" | n/a | n/a | No producing process; the heartbeat write is unguarded, a crash-loop CANDIDATE (`KNOWLEDGE_CONSUMPTION_MAP_2026-09-24.md`). Relaunch is on the pod and owner-visible. |
| NBA pregame (`domains/basketball_nba/predictor.py:64`) | Win prob, totals | NO. `nba/latest.json` 07-27T20:05Z | Moneyline Brier 0.1735 vs devigged close 0.1666, n=372, MATCHES_CLOSE, underpowered (`docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`) | `espn_boxscores.parquet` max 2026-05-24 (offseason) | Producer dark; no 2026-27 ingest yet |
| MLB pregame (`domains/mlb/predictor.py:75-92,148`) | Moneyline | NO. `mlb/latest.json` 07-27T20:05Z | TRAILS_CLOSE, gap +0.0039 [+0.0028, +0.0051], n=13,992 (`DM_RECOMPUTE_2026-09-24.md`; `docs/MARKET_EFFICIENCY_PROOF.md:42`) | `data/domains/mlb/games_current.parquet` max date **2026-07-12**, mtime 07-16T13:59Z | Ratings frozen; the refresh job never ran. S448 real run and the live statsapi fetch are an OWNER decision. Producer dark. |
| Soccer pregame (`domains/soccer/predictor.py:50`) | 1X2, O/U | NO. 07-27 | O/U 2.5 TRAILS_CLOSE +0.0076 [+0.0059, +0.0092], n=7,558 (`DM_RECOMPUTE_2026-09-24.md`) | `match_stats.parquet` max 2026-05-24 | Producer dark; results not refreshed since 06-13 |
| Tennis pregame (`domains/tennis/predictor.py:44-66`) | Match win | NO. 07-27T20:06Z | ATP 0.2177 vs 0.2028, n=7,374, BEHIND (freshness) (`docs/MARKET_EFFICIENCY_PROOF.md:45`) | `matches.parquet` max match date **2025-12-17** | Results feed stopped 9 months ago; producer dark |
| WNBA pregame (`predictor_jd.py:160-167`) | Win prob | NO. `generated_at` 07-19T14:15Z | NONE vs market (only a coin baseline, `data/domains/wnba/pregame_gate_verdict.json`) | `espn_scoreboard.parquet` max 2026-07-16 | No market comparison exists; producer dark |
| NFL pregame | none | NO (no producer) | NONE | `data/nfl/schedules.parquet` 08-31 | No predictor; nfl absent from `predict_matchup._SPORTS` |
| API `/predictions/game`, `/today`, `/props/{id}` (`api/predictions_router.py:215,237,285`) | Legacy orchestrator | NO. Newest `predictions_cache_*.parquet` is 2026-06-08 | NONE | 06-08 | Legacy stack, not in the supervisor specs; no API process; the overlay returns `{}` when the parquet is missing (`api/_predictions_overlay.py:130`) |
| API `/predictions/win` (`api/models_router.py:104`) | Spatial demo | NO | NONE (the docstring accuracy figure has no artifact) | Tracking paused | Hardcoded placeholder teams; not a prediction surface |
| Live repricer (`scripts/platformkit/ingame/live_loop.py:227,243,256`; `repricer_router.py:34,52`) | Live repriced prob | NO. `data/frontend/ingame/_heartbeat.json` 07-17T04:57Z, `n_live` 0 | NBA end-Q1 MARKET_SHARPER_PROVISIONAL (`EVIDENCE.md:49`); MLB and soccer BEHIND the mid (gate A0) | n/a | Only `surfaces/nba.json` exists, so every other sport serves `_pregame_carry` of the stale prior. No live_loop process. |
| NBA props (`domains/basketball_nba/player_props.py:76`) | Point projections | NO. `data/models/prop_pergame_walk_forward.json` 06-07 | NONE vs market; `prop_close_capture_status.json` shows `captured: 0` | Season 2025-26 | No priced-prop corpus; exceedance pricer orphaned (S451) |
| MCP `win_probability` (`scripts/platformkit/mcp_server/tools.py:42`) | On-demand envelope | Callable (3 mcp_server processes) | Inherits each predictor's result above | As stale as the domain parquets | Serves MLB Elo frozen at 07-12 |
| `data/frontend/ops/calibration_scoreboard_latest.json` | "Brier" | NO. 09-03 | Its `method` field is "synthetic-method-NBA"; must not be cited | n/a | Synthetic; not evidence |
| Webapp `webapp/public/data/forward/weekly_record.json` | Forward record | 09-24T18:17Z | `completed_weeks` 0, every family `rows: []` | n/a | No completed forward week |

## 2. In-game path and scoreboard arms

| Arm or sport | Output (file:line) | Fresh <24 h? | Last calibration vs market | Data freshness | Exact blocker |
|---|---|---|---|---|---|
| A | Raw Kalshi YES mid, `(bid+ask)/2` (`ingame_scoreboard_rules.py:83`; the register still cites :71) | NO. `docs/evidence/forward/scoreboard/2026-09-24.json` (rewritten 09-28T15:13Z) | It is the comparator. Outcome Brier by phase, MLB n_games 3-4, all INSUFFICIENT | See data rows below | 30-game / 5-cluster floor (`ingame_scoreboard.py:27`); S495 naming |
| B (mid only, walk-forward) | `baseline_four_arm_features.py:297`; `ingame_scoreboard.py:219` | NO | NONE (1,991 ticks `model_not_reconstructible:B`) | n/a | No history before S474/S475; first fitted night is 2026-09-30 (`PREREG_2026-09-30.json`) |
| B_lag | Previous receipt's mid | NO | Outcome Brier by phase, INSUFFICIENT, n_games 3-4 | n/a | Control only |
| C (mid + FEATURES[sport]) | `baseline_four_arm_features.py:14-20,297` | NO | NONE (1,991 not reconstructible) | n/a | Same as B; C minus B contrast has n=0 |
| D (C on model-present rows) | `baseline_four_arm.py:118-125` | NO | NONE | n/a | Native state never carries `model_prob` (`ingame/local_state_capture.py:34`) |
| E (registry blocks, MLB) | `registry_scorer_e.py:211`; blocks declared in `scripts/platformkit/ingame/feature_registry.py` | NO. `registry_e/2026-09-26.json` 09-29T13:58Z, REFUSED `config_not_effective`, 0 rows | NONE | n/a | Effective from 09-30 (`BLOCK_CONFIG_E_2026-09-30.json`); first fit about 10-04; quadratic tape scan (S498, `microstructure_features.py:93`); no regular-season history (S487) |
| mlb in-game | `ingame/mlb_winprob_v7.py`, `mlb_live_model.py` | State 09-29 1,428 rows, all `pre`; books 09-29 3,999 rows | **Gate A0** (`docs/evidence/ingame/gate_a0_summary.md`, 09-14): model Brier 0.2377 vs Kalshi mid 0.2067, delta +0.031 CI [+0.017, +0.046], 227 games, BEHIND. Data is 06-20..07-12. | No state or books for 09-27 and 09-28 (outage) | Sample (3 served games on the 09-30 schedule); fitted arms unproven |
| soccer in-game | Standalone model; CORPUS soccer to soccer_intl | State 09-29: 292 rows, all `final` | Gate A0: 0.2279 vs 0.1427, +0.085, 51 games, BEHIND | EPL-only state | S490 (orchestrator 1); no fixtures until about 10-09; **no start/date on any state row (new defect)** |
| nfl in-game | State only | State 09-29: 17,568 rows (1,047 live, MNF) | NONE | Only one usable historical live game (09-25) | S492 (improve run) seal 10-01; `CORPUS` has no nfl (`ingame_scoreboard_rules.py:140`); **no start/date on any row** |
| tennis in-game | `ingame/tennis_point_recursion.py`, not wired | State 09-29: 868,968 rows (2,704 live), 657 MB | NONE | Sets only, no games/points/server | S493 set-state model; **no start/date on any row** |
| wnba in-game | `ingame/wnba_ingame_shadow.py` (shadow) | State 09-29: 714 rows, all `pre` | NONE | Season ending | S491; **no start/date on any row** |
| nba in-game | `ingame/nba_logistic_pricer.py` | State 09-29: 357 rows, all `pre` | NONE from the scoreboard | Offseason until 10-20 | S494 (orchestrator 1), S482; **no start/date on any row** |

Captures (one WMI check, about 17:00Z):
- Running: `capture_supervisor` (pids 28240, 22316, 23904), `local_state_capture` (20108), `local_capture_runner` (24724) and `polymarket_live_capture` (11340).
- Heartbeats were fresh at 16:53Z.
- Down from about 03:16Z to 14:11Z on 09-29.

Paper nights, 09-20 to 09-29:
- 09-24: PARTIAL, the only scoreboard receipt.
- 09-25: PARTIAL, every RAM-gated step refused (`free_ram_below_floor`).
- 09-26: PARTIAL, `free_ram_below_floor`; E REFUSED.
- 09-27 and 09-28: none.
- 09-29: runs about 06:07Z on 09-30. It will refuse `amendment_mismatch` by design.

The 2026-09-30 night is the first fitted-arm night (B, C and D for mlb; soccer has no games). It has 3 MLB games on the served schedule, so every cell will be INSUFFICIENT.

## 3. Signal registries and the intelligence layer

| Family | Count, sport | Fresh <24 h? | Last calibration vs market | Blocker |
|---|---|---|---|---|
| SPA catalog (`scripts/platformkit/eval_gate/spa_catalog_report.txt`, 09-02) | 60 classes (NBA 16, tennis 15, soccer 15, MLB 14) | NO | All NOT_EVALUABLE. The S64 uncharged rescreen found 57 NULL, 2 SCREEN_POSITIVE vs p_base only (about 0.0001 Brier), and 1 NEGATIVE vs the close (`docs/evidence/harness/S64_catalog_rescreen_2026-09-03.md:88-93`) | No per-signal losses archived; the S396 runner has no real-row run; no consumer |
| Registry parquet (`data/registry/signal_registry.parquet`, 07-15) | 86 rows: 72 folded, 14 deferred; 12 tagged `ingame` | NO | NONE; 86 of 86 NOT_TESTABLE (`RESULTS_LEDGER_SYSTEM.md:198`) | No sport or timestamp column; `coverage_pct` empty; no adapter to any scorer |
| Arm E blocks (`ingame/feature_registry.py`) | 7 blocks in the 09-30 seal, MLB only; the NBA block is sealed off (`:220-222`) | Seals 09-28; E row REFUSED | NONE | Seal window; S498; S482 for NBA |
| `data/intelligence/` | 151 files, NBA | NO (newest 09-02) | S225 scheme-fit in-game arm NULL | Zero readers on any served or scored path; as-of risk at `intel/team_pace_identity.py:152` (`<=`) |
| S423 intel prior (`ingame/intel_prior_arm.py`) | 1,430 of 1,593 r1 games | NO (09-23) | NONE (never fitted) | Unsealed prereg (S449) |
| Discovery loop (`src/loop/discovery.py`) | n/a | NO. Last logs 06-09 | NONE | Dormant |

## 4. Top 10 blockers, ranked by how directly they stop a calibrated live in-game number

1. **Sample floor versus the calendar.** The seal requires 30 games and 5 clusters (`ingame_scoreboard.py:27`), and MLB serves 3 to 4 games a night. Tennis has thousands of live rows a day but no scoreboard support (S493).
2. **Fitted arms have never scored.** B, C and D were `model_not_reconstructible` on 09-24. The first fitted night is 09-30, and it depends on that night surviving the RAM floor (S501, owned by the improve run).
3. **Every ESPN-sourced state row lacks `scheduled_start_utc` and `date`** (nfl, nba, wnba, soccer, tennis, ncaaf; minute-precision ESPN instants fail `venue_instant`). This is missing state for linkage and segmentation on every non-MLB sport. NEW row.
4. **Night reliability.** Captures died about 03:16Z on 09-29 (OS sleep). The 09-25 and 09-26 nights were refused for RAM, and 09-27 and 09-28 have no shards. S500 and S501 are owned by the improve run.
5. **The measured in-game model trails the venue mid** on MLB and soccer (gate A0). Only "market anchor + state residual" matched (Q17). No newer measurement exists.
6. **Scoreboard sport support is missing:** nfl (S492), tennis (S493), wnba (S491), nba season type (S494), soccer six-league state (S490).
7. **Arm E is unproven:** config effective 09-30, quadratic tape (S498), NBA blocks (S482), no regular-season history (S487).
8. **The served producer is dark** (`cycle_count` 0 since 09-01; pod; owner-visible relaunch). The live repricer has only an NBA surface, so live MLB serves the pregame carry.
9. **Pregame inputs are frozen:** MLB Elo at 07-12 (S448, owner decision), tennis results at 2025-12-17, soccer at 2026-05-24.
10. **Qualification can pass a sport with no own state** (S496, `forward_capture_bridge.py:113`), and seal churn from the live FEATURES dict (S469) can refuse a night.
