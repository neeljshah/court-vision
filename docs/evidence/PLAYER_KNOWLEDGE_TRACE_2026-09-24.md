# Player knowledge trace -- 2026-09-24 (player level; team level is in KNOWLEDGE_CONSUMPTION_MAP_2026-09-24.md)

Read-only investigation, master d0c6f114e. Calibration language only. Labels: OBS = observed in source or on
disk this session; EST = a model estimate quoted from a landed artifact; HYP = hypothesis, untested.
Status vocabulary: EXISTS (code/artifact present), CONNECTED (reaches the next stage on the served path),
INFLUENTIAL (measured to move the output), INDEPENDENTLY USEFUL (measured better than a baseline),
BROKEN (present but wired wrongly), ABSENT.

## 0. Headline (OBS)

There are FOUR player-prediction paths and none of them carries the accumulated player knowledge end to end:
- P1 NBA served point path: `src/prediction/player_props.py:2235 predict_props` -> prefers the per-game models
  `src/prediction/prop_pergame.py:5344 predict_player_pergame` (real per-game features, point q50/blend only),
  falls back to the season-grain SYNTHETIC trainer (`player_props.py:2587-2591` labels that `season_avg_fallback`).
- P2 NBA exceedance pricer: `domains/basketball_nba/player_props.py:76 price_prop` (recency-weighted Gaussian,
  sigma floors at :31-32). Its only wrapper `scripts/platformkit/prop_edge_nba.py:99` has NO non-test caller;
  the board config makes NBA raise `NotImplementedError` (`scripts/platformkit/prop_edge_config.py:187-191`).
- P3 MLB exceedance pricer (the only live player path): `scripts/platformkit/prop_edge_mlb.py:52` ->
  `domains/mlb/prop_engine_mlb.py:111 prop_distribution` = own rate x own exposure -> Poisson P(over).
- P4 research distributions (S296 / S297 / S332 / S271): measured, landed, consumed by NO served path
  (grep of api/, src/prediction/, prop_edge*.py for full_boxscore_oof / s297 / prop_game_model: only
  research callers `scripts/platformkit/proof_nba/gate_b_*.py`).

## 1. Trace table (stage x prop family)

| Stage | NBA pts/reb/ast/fg3m/stl/blk/tov (P1) | NBA P(over) (P2) | MLB K / H / TB / BB etc. (P3) |
|---|---|---|---|
| Source observation | gamelogs + 15+ parquet joins (`prop_pergame.py:382-610`) | `player_boxscores.parquet` (`domains/basketball_nba/player_props.py:26`) | `data/domains/mlb/player_gamelogs.parquet` (`prop_edge_config.py:146-147`); OBS 321,012 rows, max date 2026-07-02 |
| Timestamped feature | EXISTS: prior-game form, opp defence, playtype (prior-season join, `prop_pergame.py:96-100`), bbref, contracts, defender-matchup (`:2366`), profile (`:2459`), officials/fouls/team-DNP (`:2556-2709`). BROKEN at serve: rest/travel replaced by neutral defaults (`:5270-5271`); `rest_days` defaults 2.0 (`:5238`, `:5350`) and `predict_props` never passes it (`player_props.py:2293`) | EXISTS: strictly-prior games only (`:78-84` docstring, `_player_history`) | EXISTS: strictly-prior rows (`exposure_mlb.py:9-10`); exposure = recent PA / BF or lineup-slot prior (`exposure_mlb.py:28,51,84`) |
| Model parameter | q50 quantile head for fg3m/stl/blk/tov/reb (`prop_pergame.py:227`), meta-blend for pts/ast (`:4859-4875`); separate model per stat | L15 weighted mean + sample sd (domains file `:97-101`) | per-PA / per-BF shrunk rate (`player_rates_mlb.py:1`) x E[exposure] = lam (`prop_engine_mlb.py:50-101`) |
| Outcome distribution | ABSENT on served path: point value only (`prop_pergame.py:5364-5369`); then hand-set scalings: minutes factor (`player_props.py:2302-2332`), DNP > 0.4 -> x(1-0.3p) (`:2365-2369`) | Gaussian, continuous, symmetric (domains file `:102`) | Poisson (NB only if `dispersion` passed; MLB config sets `supports_dispersion=False`, `prop_edge_config.py:152`) |
| Served prediction | CONNECTED: `api/predictions_router.py:285` via `prop_model_stack.stack_predict` (adds multiplicative micro-model factors + hand-weighted confidence terms, `prop_model_stack.py:585-609`); BROKEN: `api/stitch_router.py:134` calls `predict_props(player_id, season)` so the season string binds to `opp_team` | BROKEN / ABSENT (orphaned; board degrades NBA to UNAVAILABLE) | CONNECTED: prop board -> `bestbets/prop_cards.py:161` model_prob |
| Evaluation receipt | EXISTS point-only: production holdout MAE (`docs/JOB_EVIDENCE_PACKET.md:170-175`); no P(over), no quantile receipt for the served head | ABSENT for this function; S228 scored a prior-only player distribution vs the close (sec. 3) | BROKEN: `props_eval_mlb.py:146-150` feeds REALIZED exposure (tests rate only); cache `data/domains/mlb/prop_calibration.json` n = 0 (OBS); settle arm `bestbets/prop_settler.py:238-253` resolves MLB/soccer only; OBS `data/frontend/clv_ledger.jsonl` has 20 rows, 0 with market_type=prop |
| Calibration by market type | ABSENT: `analytics_showcase/out/calibration_by_market_type.json` holds mlb_moneyline, soccer_match, mlb_total only | ABSENT | ABSENT |

## 2. Player-knowledge families: does each reach the model?

| Family | Where it lives | Reaches P1 / P2 / P3? |
|---|---|---|
| Identity / archetype / fingerprints / drift | `docs/INTELLIGENCE.md:108,195-205` (data/intelligence) | none: 0 grep hits for intelligence/archetype/fingerprint in `prop_pergame.py`, `player_props.py`, `prop_model_stack.py` |
| Opponent scheme atlas | `INTELLIGENCE.md:110,219-225` | none (same grep; only a comment at `prop_pergame.py:3273`) |
| Matchup history | per-opp rolling `prop_pergame.py:272-291` | P1 disabled (REVERT, `:564-583`); defender matchup `_DMATCH_KEYS` `:2366` CONNECTED to P1; Q15c defender-matchup HOLD (`docs/evidence/props/q15c_prop_game_model_matchup_summary.json`) |
| Role / usage | bbref usg (`:2140`), adv splits usage z (`:2779-2781`), playtypes (`:90-95`) | P1 CONNECTED (season-level usage); role CHANGE detection: none (l3/momentum REVERTs `:531-601`) |
| Lineup / on-floor | lineup_chemistry, pair_chemistry (`INTELLIGENCE.md:111`) | none pregame; in-game NBA arm features are score/quarter/clock only (`ingame/baseline_four_arm_features.py:17`); S84 lineup-at-tick term NULL (`RESULTS_LEDGER_SYSTEM.md:233`) |
| Minutes projection | `minutes_aware_props.py` (hand elasticity), Bayes min (`player_props.py:2336-2344`) | P1 CONNECTED as a scalar; S297 minutes DISTRIBUTION (INDEPENDENTLY USEFUL, sec. 3) not connected |
| Injury / availability | `injury_availability.apply_availability` | P1 CONNECTED (`prop_pergame.py:5374-5388`, multiplicative, inference-only) |
| Teammate absence (vacated load) | `_VAC_LOAD_KEYS`, `_VAC_AST_KEYS` (`prop_pergame.py:153,172`) | flags default OFF (`:152,171`); team-DNP counts `:2703-2705` CONNECTED |
| Rest / schedule | trained features `is_b2b, miles_traveled, altitude_ft` (`:397`) | BROKEN at serve (neutral defaults `:5270-5271`) |
| Season phase | none found | ABSENT (per-opp REVERT notes a playoff-vs-regular failure, `:574-578`) |
| Tracking research | CV cols gated `PROP_USE_CV` (`:113-116`) | OFF; Gate B CEILING_ZERO (`docs/CAPABILITIES.md:101`); SHAP ~0 (`docs/KNOWN_LIMITATIONS.md:86`) |
| MLB batter-vs-pitcher mechanisms | `domains/mlb/matchup/pa_outcome_v2.py:1-40` (platoon x pitch-type; count-leverage) | P3: none -- `prop_engine_mlb.py` imports only rates + exposure (`:37-45`); no opponent term |
| Failed experiments | REVERT notes `prop_pergame.py:438-601` | recorded in code comments, scored on non-proper-score deltas, not CRPS or pinball |

## 3. Honest baseline (what may / may not be claimed)

MAY (EST, with artifact):
- NBA production holdout point MAE PTS 4.83 ... TOV 0.89, 20,354 rows (`JOB_EVIDENCE_PACKET.md:170-175`).
- S332 per-game quantile model AHEAD of a trailing-10 baseline (NOT a market line): pts pinball 1.5705 vs 1.6813,
  delta 0.1107 [0.1031, 0.1187], 2024-25 (`RESULTS_LEDGER_SYSTEM.md:632`); acceptance_rule_met false (3/7 stats).
- S296 strict-past player empirical beats league empirical on 16/17 box-score fields by CRPS, 78,767 player-games
  (`RESULTS_LEDGER_SYSTEM.md:544-545`). S297 minutes CRPS 9.682 -> 8.550, CI [1.091, 1.171]; inside-80 coverage
  0.642 -> 0.649 (both far below 0.80) (`docs/evidence/harness/S297_minutes_dnp_distribution_2026-09-04.md:8-16`).
- S271 q10-q90 coverage PTS/REB/AST 0.894/0.907/0.900 (`RESULTS_LEDGER_SYSTEM.md:514`).
- S228 prior-only player distribution vs the devigged prop close, 14,231 rows / 77 games: Brier on P(over close)
  0.2771 [0.2695, 0.2839] vs close 0.2491 [0.2475, 0.2506] -- TRAILS the close
  (`docs/evidence/harness/S228_pregame_prop_close_upset_2026-09-04.md:61`).
MAY NOT:
- Any claim that the season-grain trainer is a model of games: its roll / home-away / vs-opp features are the label
  times seeded noise (`player_props.py:2690-2716`) and `opp_def_rtg` is a random draw of real values
  (`:2728-2731`); absent columns are zero-filled (`:2786-2794`). Every metric from that trainer, and every served
  number tagged `season_avg_fallback`, `ensemble` or `model`, inherits this. The per-game path (P1 default) is
  real-featured; the memo claim "props are season-grain" is TRUE ONLY for the fallback (OBS `:2280-2299`).
- Any calibrated P(over) for NBA (no served pricer, no receipt) or MLB (cache n = 0; Poisson width uncalibrated by
  the engine's own note `prop_engine_mlb.py:17-22`).
- Any tracking/CV contribution to props; any matchup-feature improvement (Q15c HOLD); any comparison to the close
  other than S228's TRAILS.

## 4. Player-team coupling and distribution outputs

- Coupling (OBS): none. Each stat is predicted separately (`prop_pergame.py:5364-5369`); no constraint ties a
  player's opportunities to teammates or to the team total. The only cross-player inputs are team-DNP counts
  (`:2703`) and the OFF vac_* flags. S296 checks box-score algebra coherence, not teammate sums (register row S296).
- Distributions (OBS): served NBA = point only; MLB = Poisson P(over) + ladder (`prop_engine_mlb.py:180`);
  research quantiles exist (S271, S296, S297, S332; `src/prediction/live_quantile_bands.py:5` for in-game).
  Tail calibration: only S228's tail target (log loss 0.337 vs 0.464, S228 memo `:80`) and S297 coverage; no
  exceedance reliability at pre-declared thresholds exists for any served player number.

## 5. Two highest-value gaps buildable and scorable NOW

No NBA regular season until late October; NBA work is historical only. MLB is live; NFL has no player data on
disk (`data/domains/` has no nfl entry, OBS), so NFL is out of scope this week.

GAP A -- MLB player distribution misses the opponent and its width (P3). HYP: an opponent term (as-of opposing
lineup/team K and contact rates vs the SP; as-of opposing SP rates vs a batter, with the replicated platoon
mechanism of `pa_outcome_v2.py`) plus a dispersion fitted on the FIT corpus, plus scoring the PROJECTED exposure,
lowers CRPS and repairs tail coverage versus the served Poisson own-rate engine. Baseline = the served engine
exactly as `prop_edge_mlb.py:52` calls it (projected exposure, Poisson). Affected: every MLB prop card.
Smallest decisive experiment: SP strikeouts only (the richest line family), three arms A0 served / A1 A0+NB r fit
on 2022-23 / A2 A1+opponent-lineup K-rate multiplier fit on 2022-23. Frozen: eligibility = identified SP starts
(`props_eval_gate_mlb_dist._identify_start_opportunities`), >= MIN_PRIOR_STARTS prior starts, every eligible
start scored and every abstention (unknown status) logged with reason; split = FIT 2022-23, HOLDOUT_A 2024,
HOLDOUT_B 2025-26 to 2026-07-02 (`props_eval_gate_mlb.py:31-35`); metrics = CRPS (primary), pinball q10/q50/q90,
80 pct interval coverage, Brier + 10-bin reliability for P(K > L) at L in {3.5, 4.5, 5.5, 6.5, 7.5, 8.5} logged
for every eligible start. Accept A1 or A2 over its predecessor only if the paired CRPS difference CI (game-date
cluster bootstrap, 2,000 draws, seed 13) excludes 0 in favour on BOTH holdouts and 80 pct coverage moves toward
0.80; reject if either holdout CI excludes 0 against; else NULL. Evaluator: `cpcv_evaluate_distributional` (S268
route). Forward, descriptive only: the same arms on starts after 2026-07-02 once gamelogs are re-ingested.

GAP B -- NBA has no served player distribution, and the measured minutes/role pieces never reach one (P1/P2/P4).
HYP: a mixture exceedance P(stat > L) = sum over the S297 DNP + minutes quantile distribution of a per-minute
rate distribution (strict-past player empirical, S296), with a role-change arm conditioning minutes on as-of
vacated teammate minutes (the vac_min recipe, `prop_pergame.py:155-172`), is better calibrated in the tails than
the recency Gaussian of P2 and than the served point q50 with a residual-width band. Affected: every NBA player
number, including P(over), upside probabilities and role-change games. Smallest decisive experiment: PTS, REB,
AST; arms G = P2 Gaussian, M = minutes mixture, R = M + vacated-minutes conditioning. Frozen: eligibility =
player-games with >= 10 prior games in `player_boxscores.parquet`, DNP rows kept in the denominator; split =
fit through 2023-24, holdout 2024-25 whole season, purge + one-date embargo (S233 route); metrics = CRPS
(primary), pinball q10/q50/q90, Brier + reliability for P(stat >= own strict-past q90) and P(stat > L) at L =
own strict-past median, logged for every eligible row incl. abstentions; secondary = S228's 14,231 close rows,
Brier vs the devigged close, descriptive. Accept M over G / R over M only if the game-clustered CRPS CI excludes
0 in favour AND tail Brier at the q90 threshold is not worse (CI); R additionally needs a planted within-date
permuted-vacancy null that is not AHEAD; reject if CI excludes 0 against; else NULL. Evaluator: S268
`cpcv_evaluate_distributional`.

## 6. Draft register rows (HARNESS_GAPS format, text only -- not written to the register)

| S450 | mlb (props) | OPEN -- drafted 2026-09-24 (PLAYER_KNOWLEDGE_TRACE GAP A). MLB PROP ENGINE HAS NO OPPONENT AND AN UNCALIBRATED WIDTH: prop_edge_mlb.py:52 serves prop_engine_mlb.prop_distribution with own rate x own projected exposure under Poisson (prop_edge_config.py:152 disables dispersion); the engine imports no opponent input (prop_engine_mlb.py:37-45); props_eval_mlb.py:146-150 scores realized exposure only; prop_calibration.json n=0. SP strikeouts, arms A0 served / A1 +NB r fit on 2022-23 / A2 +as-of opposing-lineup K-rate; FIT 2022-23, HOLDOUT_A 2024, HOLDOUT_B 2025-26..2026-07-02; CRPS primary, pinball q10/50/90, 80 pct coverage, Brier + reliability at K lines 3.5..8.5 for every eligible start, abstentions logged; game-date cluster bootstrap 2,000 draws seed 13; ACCEPT only both holdouts CI in favour, REJECT any CI against, else NULL; S268 route | PLAYER_KNOWLEDGE_TRACE_2026-09-24.md sec. 1, 5 | OPEN |
| S451 | nba (props) | OPEN -- drafted 2026-09-24 (PLAYER_KNOWLEDGE_TRACE GAP B). NO SERVED NBA PLAYER DISTRIBUTION; MINUTES/ROLE PIECES DISCONNECTED: served NBA props are point values (prop_pergame.py:5364-5369); the only exceedance pricer domains/basketball_nba/player_props.py:76 is orphaned (prop_edge_config.py:187-191); S296/S297/S332 distributions have no served caller. PTS/REB/AST arms G recency Gaussian / M S297 minutes+DNP mixture x S296 per-minute rate / R M + as-of vacated-teammate minutes; >=10 prior games, DNP kept; fit through 2023-24, holdout 2024-25, purge + one-date embargo; CRPS primary, pinball, Brier + reliability at own strict-past q90 and median for every eligible row; S228 close rows descriptive; ACCEPT CRPS CI in favour and q90 tail Brier not worse (R also beats a permuted-vacancy null), REJECT CI against, else NULL; S268 route | PLAYER_KNOWLEDGE_TRACE_2026-09-24.md sec. 1, 5 | OPEN |

## 7. Also found (not ranked; for the owner)

- BROKEN (OBS by reading, not run): `api/stitch_router.py:134` passes the season as `opp_team`.
- Hand-set, unlearned adjustments on the served NBA path: DNP scaling constant 0.3 (`player_props.py:2367`),
  confidence weights 0.10/0.20/0.15 (`prop_model_stack.py:607-609`); multiplicative micro factors (`:588-594`) --
  whether those factors were fitted is NOT VERIFIED.
- `data/domains/mlb/player_gamelogs.parquet` ends 2026-07-02 while `probables.parquet` runs to 2026-09-22 (OBS):
  the live MLB engine prices September props from July history.

## 8. NOT VERIFIED

- Runtime behaviour of any endpoint (nothing was run); the stitch_router binding defect is from source only.
- Which P1 branch fires in production today (pergame vs fallback share); `data/models` contents not inspected.
- Whether `dnp_in_game` (`prop_pergame.py:2704`) and current-season bbref joins (`:5281-5284`) are as-of safe.
- Whether the micro-model factors in `prop_model_stack.py:588-594` are learned or hand-set.
- props_eval_gate_mlb / shootout2 verdicts (no landed memo found); gumbo capture carrying final box lines.
- Power for GAP A HOLDOUT_B and for S228's 77-game close set (likely UNDERPOWERED; state it, do not re-cut).
