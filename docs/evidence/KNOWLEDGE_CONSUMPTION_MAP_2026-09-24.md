# Knowledge consumption map -- 2026-09-24 (investigation lane, read-only)

Question: which accumulated knowledge families actually reach the predictions the system serves, and
does any of them measurably improve untouched future forecasts? Four levels are kept separate:
EXISTS (artifact on disk) / CONNECTED (a serving or scoring code path reads it, file:line) /
INFLUENTIAL (evidence it changes a served forecast) / INDEPENDENTLY USEFUL (leak-free OOS evidence).
None implies the next. Labels: [OBS] observed in code or on disk this session; [EST] a number an
earlier artifact estimated (path given); [HYP] a hypothesis. Calibration language only.

## 0. Headline observations

- [OBS] The served prediction stack is DARK. data/frontend/predict_service/_heartbeat.json: boot beat
  2026-09-01, cycle_count 0, sports_run []; newest served file data/frontend/predict_service/mlb/latest.json
  generated_at 2026-07-27T20:05Z; data/frontend/ops/ingame_outcome_verdict.json mtime 2026-07-17.
  No model-produced prediction has been served for about two months.
- [OBS] What IS live (MLB, NFL now) is the forward capture + paper night, and its quotes are anchored
  on the observed mid BY DESIGN: scripts/platformkit/execution/quote_engine.py:3-5 ("A caller must not
  substitute a standalone model value as the default anchor"). No knowledge family can reach the
  forward paper record through the quote path.
- [OBS] The only scored in-game model path (landed four-arm) reads state + mid only:
  scripts/platformkit/ingame/baseline_four_arm_features.py:14-21 (FEATURES), :297;
  scripts/platformkit/ingame/baseline_four_arm.py:69,107,116-117 (arm D adds `model_prob`, NBA r1 only).
- [OBS] The served pregame predictors read results only: NBA = MOV-Elo + EW pace/off/def from
  espn_boxscores (domains/basketball_nba/predictor.py:68,185-197,317); MLB = MOV-Elo + run-rate state
  from games (+ games_current) (domains/mlb/predictor.py:86-92,148; domains/mlb/refresh_ratings.py:25).
  `git grep "atlas_|data/intelligence|intelligence/"` over predict_service/, both predictors,
  predict_matchup.py, predictor_jd.py, the prop board modules, live_loop.py and the four-arm files
  returns ZERO hits. The intelligence layer is EXISTS-only relative to every serving path.

## 1. Family x consumption table

Kinds: DESC descriptive / ASSOC local association / PRED predictive finding / REJ rejected /
INV invalidated or as-of unsafe / UNT untested. "none" under CONNECTED = no serving or scoring reader
on the served path (descriptive resolvers are named where they exist).

| family | sport | kind | provenance + as-of | coverage | EXISTS | CONNECTED | INFLUENTIAL | INDEPENDENTLY USEFUL |
|---|---|---|---|---|---|---|---|---|
| Team scheme atlas (defensive / offensive / rebounding / pace / paint / 3pt / transition / halfcourt / turnover / ft-foul; intel/team_*.py) | NBA | DESC | builders take as_of but `<=` admits the tip-off date (intel/team_pace_identity.py:152, quoted in the S423 memo); on-disk atlas SNAPSHOT-ONLY on 55 of 59 files, as_of 2026-05-31 season-final (docs/evidence/harness/S223_intel_pool_asof_census_2026-09-04.md) | 30 teams, one season snapshot | yes (data/cache/atlas_*, not opened) | none on served path; descriptive resolver only (scripts/platformkit/answers/atlas_resolver.py) | not measured | S225 scheme_fit in-game arm -0.000038 [-0.000278, 0.000201] vs incumbent, NULL (S225_ingame_intel_conditioning_rerun_2026-09-04.md) |
| Player behaviour / role profiles, dossiers (intel/player_*.py; 1,249 dossiers) | NBA | DESC | NBA Stats + tracking, May 2026 inputs, 91.9-97.0 d stale at S57 (S57_intelligence_freshness_2026-09-03.md) | 660-1,249 players | yes | none on served path; scouting_report / comparables resolvers (docs/AI_CONSUMER_CONTRACT.md) | not measured | docs/INTELLIGENCE.md:365 "SHAP = 0 in production" (legacy stack); not measured on the served props |
| Matchup matrix (291,625 player pairs) + lineup chemistry | NBA | DESC / REJ (in-game lineup) | tracking files, 3 seasons; as-of not certified | 291,625 pairs | yes (data/cache, not opened) | none | not measured | S84 / S92 lineup terms SCREEN_NULL (RESULTS_LEDGER_SYSTEM.md:233,306) |
| Season context: rest / b2b / travel | NBA, MLB, tennis | REJ | schedule-derived, as-of safe | full seasons | yes | legacy XGB only (src/prediction/win_probability.py:108-114); legacy :8077 app is not in supervisor/stack_specs.py; served Elo: none | not measured | schedule candidates REJECTED on 2 corpora with sign flips (docs/JOB_EVIDENCE_PACKET.md sec 2C); tennis S136 NULL (RESULTS_LEDGER_SYSTEM.md:328) |
| Injuries / availability | NBA, MLB | UNT (pregame) | MLB injuries.parquet snapshot max 2026-07-16 [OBS]; NBA injury facts via the m39 daemon (not opened) | MLB 4,427 rows | yes | none on served predictors; injury_report resolver (descriptive) | not measured | not measured; the NBA predictor docstring names injuries as the totals gap (domains/basketball_nba/predictor.py:7-14) |
| 86 registry signals | all | UNT | data/registry (not opened) | 86 | yes | none | not measured | 86 of 86 NOT_TESTABLE in the S64 re-screen (RESULTS_LEDGER_SYSTEM.md:198) |
| 60 SPA catalog classes | all | REJ / UNT | catalog by AST (scripts/platformkit/eval_gate/spa_catalog_report.txt) | 60 | yes | none (S396 audit runner landed, no real-row run: RESULTS_LEDGER_SYSTEM.md:753) | not measured | 0 shipped; S64: 57 NULL, 2 SCREEN_POSITIVE vs p_base only (+0.00009, MLB H2H Elo, era 2010-2021), 1 NEGATIVE (S64_catalog_rescreen_2026-09-03.md:91-93) |
| Family combinations | all | REJ | S58c screen DBs | 12 families | yes | none | not measured | S79: combining hurt paired Brier in 11 of 12 (S79_family_combo_2026-09-03.md:3-8) |
| Mechanism ledgers (domains/*/knowledge/validation_ledger.jsonl) | NBA, MLB, soccer, tennis | ASSOC (local) | single corpus each (e.g. savant_full 2025) | [OBS count] NBA 89 rows (38 CONFIRMED_LOCAL, 29 NULL_LOCAL); MLB 87 (28 / 37; 3 REJECT; 4 FAILED_REPLICATION); soccer 64; tennis 52 | yes | mechanism_effect resolver quotes verbatim (docs/AI_CONSUMER_CONTRACT.md); scripts/platformkit/analytics_showcase/mechanism_exposure.py | none on forecasts | S22 soccer / tennis vs close: 3 NULL_LOCAL, 35 NOT_TESTABLE (RESULTS_LEDGER_SYSTEM.md:116-117) |
| Pregame intelligence prior block (S423: last-10 off / def / pace from data/team_advanced_stats.parquet) | NBA | UNT (PREPARE) | reconstructed as-of 00:00 America/New_York strictly before the attested tip-off; no source receipt | 1,430 of 1,593 r1 games joined (89.8 pct) | yes (docs/evidence/forward/intel_prior/2026-09-23_r1_join_fix1b/) | scoring-only: scripts/platformkit/ingame/intel_prior_arm.py (arms C_intel / C_intx); CLI refuses without a sealed prereg | not measured | NO FIT RUN (docs/evidence/harness/S423_intel_prior_feature_2026-09-23.md; HARNESS_GAPS row S423) |
| In-game hot-night prior (S225, prior win rate) | NBA | REJ | earlier game dates only | 635 games / 187,203 ticks | yes | none | n/a | +0.000062 [-0.000402, 0.000526] vs incumbent, NULL (S225 memo) |
| NBA in-game state enrichment (S414: possession, fouls, bonus, timeouts, lineup presence, play code) | NBA | UNT | receipt-causal sibling block; capture NOT adopted (needs a supervised relaunch) | 0 captured rows | code only | FEATURES['nba_enriched'] declared (baseline_four_arm_features.py:37-41); corpus nba_state_enriched_r1 declared, empty | not measured | not measured |
| MLB live-feed state (S432: TTO pair count, bullpen used) | MLB | UNT | receipt-causal, flag OFF | 0 captured rows | code only | FEATURES['mlb_live'] (baseline_four_arm_features.py:22) with NO CORPORA entry (:24-31) | not measured | TTO offset gate INSUFFICIENT, one season (data/frontend/ingame/tto_offset_gate_mlb.json) |
| NFL situation state (S413) | NFL | UNT | declared fields, no zero-fill | 0 | code only | FEATURES['nfl'] with NO CORPORA entry (baseline_four_arm_features.py:19-20); NO NFL branch in scripts/platformkit/predictor_jd.py:138-180 | none | none |
| Microstructure block (S434: touch imbalance, signed flow, quote age, spread) | all captured | UNT (PREPARE) | receipt-causal; real run 1: 4,290 ticks / 3 games, signed_flow p10-p90 = 0, quote_age p50 ~28 min (HARNESS_GAPS row S434) | 3 games | yes | none (S435 report-only row is OPEN) | not measured | not measured |
| MLB starting-pitcher form | MLB | REJ | as-of EW, snapshot-before-update | 10,569 games (2026) | yes | gated OFF: domains/mlb/sp_adjust_current.py:21 (CV_MLB_SP_ADJUST unset) | none | REJECT: Brier 0.24389 vs baseline 0.24374 (data/domains/mlb/sp_adjust_verdict.json); family SP1 NULL_LOCAL, win CI [-0.0009, 0.0023] (data/domains/mlb/family_sp_gate_verdict.json) |
| MLB weather -> totals | MLB | INV (as-of unsafe) | [OBS] 11,165 of 11,166 weather rows in data/domains/mlb/probables.parquet have snapshot_date >= game_date (backfilled 2026-07-02..16) | 2,199 games with a totals close | yes | none (served totals come from run-rate state only) | none | the unsealed autogate SHIP_REVIEW (data/frontend/ops/mlb_context_autogate.json) is NOT usable: the weather is post-hoc, not as-of the close |
| MLB umpire / park / pitcher-fatigue gates | MLB | REJ | as-of within each gate | 4,561 games (umpire totals) | yes | none | none | umpire totals REJECT (planted null as large), park stack REJECT (L3 seed stability), velo-fatigue REJECT, SP in-game layer REJECT (data/domains/mlb/*_verdict.json) |
| Player-grain in-game (S80 pitcher RA9 residual) | MLB | REJ | gamelogs strictly before game date | 8,309 ticks / 53 games | yes | none | none | NULL (RESULTS_LEDGER_SYSTEM.md:230) |
| Tracking-derived research (CV program, paused) | NBA | REJ | prior-season tracking + hustle | props 2023-25 | yes | none | none | Gate B CEILING_ZERO (RESULTS_LEDGER_SYSTEM.md:636; docs/evidence/POWER_PAGE_2026-09-22.md:88) |
| Other in-game mechanisms on the mid | NBA, MLB | REJ | S86 archives | 571-1,593 games | yes | none | none | S94 shrinkage NEGATIVE, S96 overreaction falsified, S97 fusion NULL, S103 sigma bar not met, S06 stacker BEHIND, S58 clamp NULL (RESULTS_LEDGER_SYSTEM.md:53,203,245,249,252,258) |
| Pregame team rating (the one CONNECTED family) | NBA, MLB | PRED (calibration) | walk-forward, snapshot-before-update | NBA 743 closes; MLB 10,569 games | yes | served: domains/basketball_nba/predictor.py:317; domains/mlb/predictor.py:148; four-arm arm D via model_prob (baseline_four_arm.py:69,117) | yes (it IS the served number) | NBA 0.1735 vs close 0.1666, n 743, TRAILS_CLOSE (JOB_EVIDENCE_PACKET.md sec 2C); S112: close ahead of Elo by +0.0256 NBA / +0.0073 MLB (RESULTS_LEDGER_SYSTEM.md:282) |

What the failures rule out [EST, from the cited rows]: static team or player priors layered on the
in-play mid (S225, S80, S84, S92); shrinkage / fusion / overreaction corrections of the mid (S94, S96,
S97); stacking (S06, S79); SP form and umpire / park totals corrections at the tested proxies; tracking
features for props (Gate B). The open space is receipt-causal STATE the mid may lag (S414, S432, S434,
S435) and FRESHNESS / WIRING of the served prior -- not more descriptive intelligence.

## 2. Served-path trace (source -> feature -> model -> distribution -> served -> receipt)

Win probability, pregame (all sports):
source data/domains/<sport>/ box / games parquets -> features: team Elo (+ EW pace / off / def NBA;
run-rate lambdas MLB) -> model domains/<sport>/predictor.py via scripts/platformkit/predictor_jd.py:138-180
(called from predict_service/produce.py:111-115 -> scripts/platformkit/predict_matchup.py:170-220)
-> distribution: Gaussian margin / total (NBA), NegBinom runs (MLB) -> served
data/frontend/predict_service/<sport>/latest.json -> receipt: none tracked per served record; offline
proof artifacts only (own_lines_backtest_nba, docs/MARKET_EFFICIENCY_PROOF.md).
BROKEN / ABSENT [OBS]: (a) producer dark since 2026-07-27 (heartbeat cycle_count 0); (b) MLB ratings
source data/domains/mlb/games_current.parquet max date 2026-07-12 (mtime 2026-07-16) against its own
sla_minutes=1440 (domains/mlb/ingest_manifest.py:43); a refresh job exists
(scripts/platformkit/autoloop/mlb_results_refresh_job.py) but has not run; (c) no NFL branch in
predictor_jd.py; (d) predict_service/recal_pregame.py has no non-test caller (git grep), so the
walk-forward recalibrator is not on the served path; (e) no knowledge family is read anywhere on it.

Win probability, in-game:
source ESPN scoreboard -> GameState -> scripts/platformkit/ingame/live_loop.py:237 rr.reprice ->
scripts/platformkit/ingame/repricer_router.py:34,52 loads surfaces/<sport>.json -> ONLY surfaces/nba.json
exists [OBS] -> for MLB / soccer / tennis live_loop.py:243 serves `_pregame_carry` (the unchanged pregame
prior, basis pregame_carry) -> data/frontend/ingame snapshots (newest mtime 2026-09-01) -> receipts
data/frontend/ops/ingame_outcome_verdict.json (2026-07-17), ingame_clv_verdict.json (2026-09-01), stale.
BROKEN [OBS]: the always-on MLB live card never conditions on score / inning / outs, although
domains/mlb/predictor.py:237 predict_live exists; it is reached only by the on-demand CLI
(predict_matchup.py:223-247). m11 is NBA-only (scripts/platformkit/ingame/ingame_pred_tick_runner.py:126).
Research in-game path (scored, not served): capture state rows + Kalshi mid -> FEATURES -> ridge
logistic arms B / C / D (baseline_four_arm.py:107,116-117) -> sealed S347 MLB result: all 96
comparisons UNDERPOWERED (RESULTS_LEDGER_SYSTEM.md:714,718).

Props (NBA; MLB and soccer analogous):
source data/domains/basketball_nba/player_boxscores.parquet (domains/basketball_nba/player_props.py:26)
-> features: the player's own L5 / L10 / L20 hit rates + recency-weighted mean and sd, dates strictly
before -> Gaussian P(over) -> prop board (scripts/platformkit/bestbets/prop_cards.py:276 imports the
board builder; the NBA pricer is imported at scripts/platformkit/prop_edge_nba.py:99) ->
data/frontend/props_snapshot.json (m13) -> receipt: the prop settle runner (supervisor/stack_specs.py:527),
not opened here.
ABSENT [OBS]: no opponent, minutes projection, injury, pace, matchup-matrix or profile input in the NBA
pricer; the MLB board module states opponent levers are not used (scripts/platformkit/prop_edge_mlb.py:6).
docs/INTELLIGENCE.md "Dossier fields -> prop model features: Yes" describes the legacy src/prediction
stack behind api/main.py:36,382 (not in supervisor/stack_specs.py), not the served board.

## 3. The three highest-value verified gaps

GAP A -- the MLB live card ignores realized state (served in-game = pregame carry).
- Seen at: repricer_router.py:34,52 (one surface file per sport; only surfaces/nba.json on disk) and
  live_loop.py:237-243 (fallback to _pregame_carry). Affects every served MLB in-game win probability
  (and soccer / tennis) whenever the stack runs; the MLB postseason is the live window now.
- Hypothesis [HYP]: routing MLB through the existing predict_live (Elo-anchored lambdas + realized
  score / inning / half / outs -> repricer -> W156 recalibration) lowers Brier vs outcome relative to
  the carry. Prior evidence [EST]: vs a static prior, MLB conditioning 0.241 -> 0.126 (docs/INGAME_PROOF.md);
  vs the contemporaneous mid the in-game model is BEHIND (0.2377 vs 0.2067, 227 games, Gate A-0).
- Baseline: the carried pregame prior at each tick (what is served). Comparator: predict_live at the same
  tick. Reference (reported, never the acceptance bar): the Kalshi mid as-of the tick receipt.
- Smallest decisive experiment: on the landed mlb_segmented_r3 corpus (176 games, 29,887 eligible ticks;
  S347 prereg census) compute both arms per tick with the Elo as-of the day before each game; confirm on
  forward MLB nights from 2026-09-25 (untouched).
- Frozen rule: eligibility = the S347 eligible ticks; split = none (both arms are fixed functions; the
  W156 temperature is fit only on games strictly before the corpus window); metric = tick-weighted and
  equal-game Brier, paired per game; interval = gate_a0 cluster_bootstrap over games
  (scripts/platformkit/ingame/gate_a0_ingame_vs_market.py:22,70,84; 2,000 draws). ACCEPT if the paired
  (live minus carry) upper bound < 0 on the historical corpus AND the forward point < 0 on >= 30 forward
  games; REJECT if the lower bound > 0; else NULL. Fewer than 30 forward games = INSUFFICIENT, reported.
- Cost: no new model; one comparison script plus a declared MLB surface or routing change in
  scripts/platformkit/ingame (not a gated path). One K charge.

GAP B -- MLB served ratings are frozen at 2026-07-12.
- Seen at: domains/mlb/refresh_ratings.py:25 reads games_current.parquet; [OBS] max(date) 2026-07-12,
  mtime 2026-07-16; SLA 1,440 min at domains/mlb/ingest_manifest.py:43; predictor_jd.py:148 serves it.
  Affects every served MLB pregame p_home_win, run line and total, and the prior that anchors GAP A.
- Hypothesis [HYP]: an Elo updated walk-forward through the day before each game has lower Brier than
  the Elo frozen at 2026-07-12 on games from 2026-07-13. Baseline = the frozen Elo (what would be served
  today). The plausible size is small (MLB Elo moves slowly); that is what is being measured.
- Smallest decisive experiment: fetch 2026 final results once (the landed ingest_current.build_current),
  then score games 2026-07-13 .. end of the regular season with both ratings; no refit of K or HFA.
- Frozen rule: eligibility = FINAL regular-season games in the window with both teams resolved; metric
  = per-game Brier vs outcome, paired; interval = bootstrap over game DATES (one rating state per date),
  2,000 draws, seed 13. ACCEPT if the fresh-minus-frozen upper bound < 0; REJECT if the lower bound > 0;
  else NULL. Secondary (descriptive, not the bar): both vs the Kalshi pre-first-pitch mid on the games
  the forward capture holds.
- Cost: one fetch + one scoring script; the fix is operational (run the refresh job, alarm the SLA).

GAP C -- the only as-of-safe NBA intelligence block (S423) has never been fitted.
- Seen at: scripts/platformkit/ingame/intel_prior_arm.py (C_intel / C_intx on the landed folds), whose
  CLI refuses without a sealed prereg; blocks committed for 1,430 of 1,593 r1 games
  (docs/evidence/forward/intel_prior/2026-09-23_r1_join_fix1b/). Every other team-intelligence artifact
  is snapshot-only (55 of 59 atlas files, S223), so this is the ONLY family testable leak-free now.
  Affects NBA in-game win probability (arm C lineage) and, if useful, the NBA pregame prior.
- Hypothesis [HYP]: C_intel (mid + state + prior_net_diff, prior_pace_mean) has lower Brier than C
  (mid + state) on r1. Prior evidence against [EST]: S225 hot-night and scheme-fit priors NULL on 635 games.
- Smallest decisive experiment: seal the existing draft
  docs/evidence/ingame/S423_NBA_INTEL_PRIOR_PREREG_DRAFT_2026-09-23.md (after the NBA E2 seal chain,
  inside the family K budget, as the S423 row orders) and run the landed arm CLI.
- Frozen rule: eligibility = prior-eligible r1 ticks (1,430 games); split = the landed four-arm date
  folds with EMBARGO (baseline_four_arm.py:95-96); metric = C_intel minus C paired Brier and log loss,
  period-first cells via S383; interval = the landed game-clustered bootstrap. AHEAD(SINGLE-WINDOW) only
  if the upper bound < 0 AND a planted null (prior blocks permuted across games within date) is not also
  AHEAD; REJECT if the lower bound > 0; else NULL. AHEAD never promotes: it only nominates the block for
  the 2026-27 receipt-causal forward corpus.
- Cost: code landed and tested (16 tests); one K charge; runs offline on the local r1 corpus.

## 4. Draft register rows (text only -- the orchestrator pastes)

| S447 | mlb | OPEN -- allocated 2026-09-24 (knowledge-consumption map, docs/evidence/KNOWLEDGE_CONSUMPTION_MAP_2026-09-24.md GAP A). SERVED MLB IN-GAME = PREGAME CARRY: repricer_router.py:52 loads surfaces/<sport>.json and only surfaces/nba.json exists, so live_loop.py:243 serves the unchanged pregame prior on every live MLB game while domains/mlb/predictor.py:237 predict_live is reached only on demand. Measure predict_live against the carry at matching ticks on mlb_segmented_r3 (S347 eligible ticks, Elo as-of the prior day, W156 temperature fit before the window) and confirm on forward nights from 2026-09-25; paired Brier, gate_a0 cluster_bootstrap over games; ACCEPT upper < 0 historical AND forward point < 0 on >= 30 games, REJECT lower > 0, else NULL; the mid reported as reference only; one K charge; no gated path touched. Spec at dispatch. |
| S448 | mlb | OPEN -- allocated 2026-09-24 (knowledge-consumption map GAP B). MLB SERVED RATINGS FROZEN: refresh_ratings.py:25 reads games_current.parquet whose max date is 2026-07-12 (mtime 2026-07-16) against its 1,440-minute SLA (ingest_manifest.py:43); predictor_jd.py:148 serves it. Score an Elo updated walk-forward through the prior day against the frozen Elo on FINAL games 2026-07-13 .. end of the regular season (no K / HFA refit); paired per-game Brier, bootstrap over dates (2,000 draws, seed 13); ACCEPT upper < 0, REJECT lower > 0, else NULL; the Kalshi pre-first-pitch mid descriptive only. The fix is operational (refresh job + SLA alarm). Spec at dispatch. |
| S449 | nba | OPEN -- allocated 2026-09-24 (knowledge-consumption map GAP C). FIRST FIT OF THE S423 INTELLIGENCE PRIOR: the only as-of-safe NBA team-intelligence block (1,430 of 1,593 r1 games; 55 of 59 atlas files are snapshot-only per S223) has never been fitted. After the NBA E2 seal chain and inside the family K budget: seal the S423 draft and run intel_prior_arm on the landed folds; C_intel minus C paired Brier + log loss, period-first cells, game-clustered bootstrap; AHEAD(SINGLE-WINDOW) only if upper < 0 AND a within-date permuted-prior planted null is not AHEAD; REJECT lower > 0; else NULL; AHEAD nominates the block for the 2026-27 forward corpus and never promotes. Spec at dispatch. |

## 5. NOT VERIFIED (this lane did not establish these)

- Whether any supervisor process is running right now (heartbeats under data/cache were not read);
  the "dark" reading rests on data/frontend mtimes and the predict_service heartbeat only.
- Row counts and as-of columns of data/cache/atlas_*, data/intelligence/*, data/registry/* (not opened;
  counts quoted from the S57 / S223 / S64 memos).
- The in-game gap size in GAP A on the CURRENT forward nights; the cited figures are historical.
- Whether the legacy :8077 app (api/main.py; src/prediction/win_probability.py, 71 features incl. rest,
  travel, refs, stars_available) is served anywhere today. Its `home_stars_available` counts top players
  who APPEARED in the game (win_probability.py:136-139 comment): a possible outcome-time feature, unaudited.
- Props receipts (prop settle output) and any props calibration against settled outcomes.
- Whether mlb_segmented_r3 carries enough team identity to rebuild an as-of Elo for every game (GAP A).
- Whether the 2026-07-13 .. 2026-09 MLB results fetch succeeds (GAP B needs one network fetch).
- The NBA injury-facts store contents and their receipt timing.
