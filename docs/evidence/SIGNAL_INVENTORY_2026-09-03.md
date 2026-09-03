# Signal inventory -- 2026-09-03

One page for every signal, arm, model and family that has been scored, across four sports and
two surfaces. **Every number here is copied from a memo or from the S-register row that landed
it; nothing was recomputed by this lane.** Calibration language only: Brier and its confidence
interval, never a currency, return-rate or edge figure.

Sources: `docs/evidence/HARNESS_GAPS_2026-09-03.md` (S01-S120), the memos under
`docs/evidence/harness/`, `docs/evidence/RESULTS_LEDGER_SYSTEM.md`, and
`data/cache/eval_gate/backtest_fwer.jsonl` (read-only, 18 rows).

**The bar everywhere below is +0.004 Brier improvement with the confidence interval excluding
zero.** The bar has never moved. Anything that does not clear it is a null, a match, or a
behind -- and those are the outcomes this system was built to record honestly.

**Reference labels, which decide what a number means:**

| label | what the model was compared against | market-relative? |
|---|---|---|
| devigged close | the two-sided closing price, devigged (soccer, tennis) | YES |
| first in-play tick | NBA's de-facto close: the first traded tick, median 21 s after tip (S112) | YES |
| pregame venue close | the 220 genuine NBA pregame closes that overlap the corpus (S112) | YES |
| Kalshi last pre-first-pitch traded quote | MLB's close (S81 rule, S112 join) | YES |
| Elo p_base | the gate corpora's own incumbent; `p_base == p_elo` byte-identically (S98) | **NO** |
| in-play line | the market price at the tick being scored | YES |
| recalibration null | a walk-forward logistic recalibration of the line on identical rows | reference arm |

**S112 is the finding that re-labels four earlier waves:** on NBA the close beats the corpus Elo
incumbent by **+0.025606** Brier (0.211728 -> 0.186122, n 351, team-clustered CI
[+0.015252, +0.035960]) and on MLB by **+0.007269** (n 276, CI [+0.000066, +0.014473]). So every
"vs p_base" NBA/MLB pregame number in S58c, S79, S85 and S108 was measured against a reference
far behind the market, and none of them is a market-relative result.

---

## 1. PREGAME

### 1a. NBA -- pregame

| signal / model / family | reference | n units | improvement | CI | verdict | memo |
|---|---|---|---|---|---|---|
| S58c T1 screens, NBA (564 screens) | Elo p_base (NOT a close) | 564 screens over the 800-row served window | 62 of 564 ahead of Elo | per-screen | SCREEN, not market-relative | S58 register row / S58c |
| S79 combo, `nba_boxdetail` top-5 L2 logistic (best of 12 families) | Elo p_base | last 800 rows, screen side | +0.000979 | CI lower not > 0 | NULL (screen) | `S79_family_combo_2026-09-03.md` |
| S85 `nba_player_value_features` (best of 5 newly supplied families) | Elo p_base (NOT a close) | 344 T1 screens | **+0.005221** | [+0.000244, +0.010199] | SCREEN POSITIVE **vs Elo only**; NULL by multiplicity (2 of 344 CI-lowers > 0 vs 8.6 expected by chance, both the same column) | `S85_refused_families_2026-09-03.md` |
| the same S85 family, re-scored | the close, on the close-covered window | S112 re-score | **-0.000660** | -- | the +0.005221 does not survive the reference change (the window carries most of the disappearance) | `S112_nba_mlb_close_2026-09-03.md` |
| the same S85 family, under the close incumbent | first in-play tick / pregame venue close | 889 nba screen rows | **+0.000178** | -- | NULL | `S113_close_incumbent_2026-09-03.md` |
| S111 `nba_quarter_shape` (coverage 35.2 -> 100 pct) | Elo p_base (NOT a close) | 800 served rows | **+0.001527** | CI not excluding zero | NULL, and Elo-relative | `S111_coverage_acquisitions_2026-09-03.md` |
| S108 full-feature elastic net + boosted arm (178 as-of columns) | Elo p_base | 619 events | +0.001360 (best anywhere) | -- | NULL -- and it is an intercept recalibration: the inner CV zeroed **every** coefficient in 20 of 23 outer folds | `S108_pregame_full_model_2026-09-03.md` |
| S108 elastic net / HGB, re-scored | the close | S112 re-score | **-0.040888 / -0.007784** | 3 of 4 CIs entirely below zero | BEHIND | `S112_nba_mlb_close_2026-09-03.md` |
| S113 best of 11 families under the close incumbent, `nba_opp_allowed` | first in-play tick / pregame venue close | 889 rows (window 800 -> 499) | +0.000640 | [-0.003011, +0.004291] | NULL; **6 of 889** rows ahead of the close (control vs Elo: 718 of 889) | `S113_close_incumbent_2026-09-03.md` |
| S81 open-to-close move target, NBA | n/a | -- | -- | -- | **premise FALSIFIED**: `nba_checkpoints_full` has zero pre-tip rows (first tick ~21 s after tip), so there is no open | `S81_market_move_2026-09-03.md` |

Coverage note (S112): the NBA close attaches to 952 of 1,814 corpus rows = 52.48 pct (220 genuine
pregame closes + 732 first-in-play ticks); the two subsets agree (+0.025567 vs +0.025629).

### 1b. MLB -- pregame

| signal / model / family | reference | n units | improvement | CI | verdict | memo |
|---|---|---|---|---|---|---|
| S58c / S79 `mlb_inning` combo | Elo p_base, and on the WRONG market label | screen side | negative | CI excludes 0 on the wrong side | NULL; the family has no matching corpus (S73: period/total screened on the ML corpus) | `S79_family_combo_2026-09-03.md`, S73 |
| S108 full-feature elastic net (22 as-of columns) | the close, MLB | screen side | 0 of 8 arms clear +0.004 across sports | boosted arms' CIs exclude zero on the wrong side, PBO 0.62-0.65 | NULL | `S108_pregame_full_model_2026-09-03.md` |
| S108 elastic net / HGB, re-scored | Kalshi last pre-first-pitch traded quote | S112 re-score | **-0.022663 / -0.005575** | -- | BEHIND | `S112_nba_mlb_close_2026-09-03.md` |
| S113 MLB screens under the close incumbent | Kalshi devigged close | 48 mlb rows (window 800 -> 452) | -- | -- | **0 of 48** ahead of the close; `mlb_inning` loses all 20 of its promotions | `S113_close_incumbent_2026-09-03.md` |
| S81 open-to-close move target, MLB | Kalshi open vs close (935 events, median gap 71.15 h) | 257 rows over 33 days | Brier +0.008550 | [-0.007206, +0.024306] | SINGLE-WINDOW NULL -- the R^2 +0.85170 is an artifact: AR(1) c = 0.987-1.021 in every fold, the model discards the open and recovers a stale 3-day-out quote | `S81_market_move_2026-09-03.md` |
| S52 / S10 modern MLB close acquisition | -- | -- | -- | -- | licence-gated (S62 DECIDE rows) | `S10_mlb_modern_close_2026-09-03.md` |

Coverage note (S112): the MLB close attaches to 894 of 39,162 rows (8.00 pct of era_2022_2026),
one venue, 74 days -- **SINGLE-WINDOW**. The live corpora were NOT swapped.

### 1c. Soccer -- pregame

| signal / model / family | reference | n units | improvement | CI | verdict | memo |
|---|---|---|---|---|---|---|
| **S58 T2 #1** `soccer_gate` rank 1, `diff_shots_for_asof` ew10 -- the only charged pregame trial vs a close | devigged close | 8,666 (hash-disjoint verdict partition E1/I1/D1) | **-0.000057** | [-0.000831, +0.000717] | **MATCH (SINGLE-WINDOW)**; deflated_p 1.0 at K=18, family n=1, PBO 0.581, per-unit CIs all contain 0 (n_corpora 0/3, floor 2) | `S58_T2_FIRST_CHARGE_2026-09-03.md` |
| S58c T1 screens, soccer + tennis (600 screens) | devigged close | 600 | **0 of 600** beat the close by any margin | -- | SCREEN NULL | S58 register row |
| S79 combo, `soccer_gate` top-5 L2 logistic (worst of 12) | devigged close | last 800 rows, screen side | **-0.008374** | -- | NULL; combo is worse than its own k=1 in 11 of 12 families | `S79_family_combo_2026-09-03.md` |
| S85 `soccer_style_fingerprints` | devigged close | 344 T1 screens | -0.001158 | -- | NULL | `S85_refused_families_2026-09-03.md` |
| S108 full-feature elastic net (54 as-of columns) | devigged close | screen side | **-0.000033** | -- | NULL (negative) | `S108_pregame_full_model_2026-09-03.md` |
| S81 open-to-close move (ou_open_* vs ou_close_*, 16,320 events) | the move itself | 6,562 | R^2 +0.00412, sign 0.5393, Brier +0.000024 | [-0.000058, +0.000105] | **CLOSED AT LIMIT**: perfect foresight of the whole move is worth only +0.001311 Brier, so the +0.004 bar is unreachable by construction (3x short). Bar NOT lowered | `S81_market_move_2026-09-03.md` |
| S65 event-grain soccer mechanisms (11) | -- | 160 of 16,322 scored rows | -- | -- | **CLOSED AT LIMIT** on coverage: 0.0098 vs MIN_COVERAGE 0.25, 25.5x short; cause is the calendar (StatsBomb open data is 2015/16, the close starts 2019-08-02) | `S65_soccer_event_asof_2026-09-03.md` |
| S22 soccer mechanism wiring | descriptive | 15 | 0 with a trigger | -- | NOT_TESTABLE x15 | `SIGNAL_INVENTORY_REDTEAM_2026-09-03.md` |

### 1d. Tennis -- pregame

| signal / model / family | reference | n units | improvement | CI | verdict | memo |
|---|---|---|---|---|---|---|
| S58c T1 screens, tennis (part of the 600) | devigged close (ATP) | -- | 0 of 600 (with soccer) beat the close | -- | SCREEN NULL | S58 register row |
| S111 `tennis_features` (coverage 58.2 -> 99.6 pct after the WTA siblings were built) | devigged close | 797 served rows | **-0.001911** | [-0.005899, +0.002077] | NULL | `S111_coverage_acquisitions_2026-09-03.md` |
| S111 `tennis_return` | devigged close | 797 | -0.001565 | -- | NULL | same |
| S111 `tennis_meta` | devigged close | 800 | +0.000188 | -- | NULL | same |
| S108 full-feature elastic net (178 as-of columns) | devigged close | screen side | **-0.000058** | -- | NULL (negative) | `S108_pregame_full_model_2026-09-03.md` |
| `tennis_schedule_density`, `tennis_travel_scouting` | -- | -- | -- | -- | **CLOSED AT LIMIT** -- need a different builder | `S111_coverage_acquisitions_2026-09-03.md` |
| S22 tennis mechanism wiring | residual vs devig | 23 (3 scored) | -- | -- | NULL_LOCAL 3 / NOT_TESTABLE 20 | `SIGNAL_INVENTORY_REDTEAM_2026-09-03.md` |

Across S111's 678 screens over 9 newly covered families: **2 of 678 CI-lowers > 0 vs ~16.9
expected by chance.** That is fewer positives than chance produces.

### 1e. Pregame, across all four sports -- the two population-level counts

- **S58c (the honest distribution):** 3,240 distinct frozen hypotheses screened locally in 249 s
  (17,060/hour over 4 procs): **1,212 SCREEN / 673 UNCOVERED / 1,355 refused** by name or grain.
  0 of 600 soccer+tennis screens beat the close by any margin. NBA 62 of 564 beat the
  *recalibrated Elo* -- not a close. 240 candidates promoted (12 families x 20); charges 0.
- **S113 (what survives the reference correction):** **147 of the 240 Elo-relative promotions
  vanish** once the incumbent is the close (92 of the S58 list's 140). The 140 NBA/MLB S58
  promotions must never be charged as market-relative.
- **S64 (the 60 catalog classes + 86 registry signals, re-screened):** 60 testable -- 2
  SCREEN_POSITIVE at p ~0.03-0.05, 57 SCREEN_NULL, 1 SCREEN_NEGATIVE. Three of 60 crossing
  DM 0.05 is what chance produces. The 86 registry signals are **NOT_TESTABLE** (no column
  named in any corpus). Top deltas were all NBA vs p_base at ~+0.0027, n_eff 881. Nothing charged.
- **S05 per-regime isotonic recalibration, 4 sports** (1,814 / 39,162 / 25,834 / 41,886):
  FLATTENED x4 -- an honest null that buys ECE and pays resolution. The devigged close beats
  `p_base` on soccer and on both tennis units.

---

## 2. IN-GAME

Every row below is SCREEN side, walk-forward, purged by game, embargoed, with game-clustered
confidence intervals. All are **uncharged** unless the row says otherwise: the FWER ledger stood
at 18 rows before this wave and stands at 18 rows after it.

### 2a. NBA -- in-game (the 465,249-tick corpus, 1,593 games, 2024-10-22..2026-06-13)

| arm | reference | n units | improvement | CI | verdict | memo |
|---|---|---|---|---|---|---|
| S86 state-priced Elo prior at **every** tick | in-play line | 232,951 ticks / 797 screen games; informative 82,248 (35.31 pct); n_eff 3,260, ICC 0.2420 | **-0.004857** (0.081922 vs 0.077065) | [-0.007355, -0.002359] | SCREEN NEGATIVE, SINGLE-WINDOW; **16 of 27 state cells MATCH** (P4 under 6 min; P3 close > 12 min +0.003375 with a CI crossing 0) | `S86_nba_every_tick_2026-09-03.md` |
| S94 phase-conditioned shrinkage of the line toward the prior | raw in-play line | 23,561 ticks in the target cell / n_eff 876 (ICC 0.76); 192,635 ticks / 673 games overall | **-0.002807** (cell), -0.000243 (overall) | [-0.006055, +0.000440]; overall [-0.000999, +0.000513] | SCREEN NEGATIVE. The measured market miscalibration (ECE P1 close 0.055593, P2 close 0.064157) **does not survive walk-forward**; the global recalibration null is also behind the raw line | `S94_nba_early_shrinkage_2026-09-03.md` |
| S96 post-event drift arm (6 arms) | raw in-play line | 39,168 ticks / 665 games; 14,354 events / 797 games | **-0.000138** (primary) | [-0.000301, +0.000025] | **PREMISE DIRECTION FALSIFIED**: no overshoot anywhere; the line UNDER-reacts and drifts (+0.2314 / +0.2966 / +0.4768 at k = 3 / 5 / 10; 31 of 33 cells with a CI excluding zero, all positive). A placebo on non-event ticks is also positive (+0.0661 / +0.1420 / +0.2865), so a third to two thirds is generic slow mid-updating. Bar missed ~30x | `S96_nba_overreaction_2026-09-03.md` |
| S97 two-sensor Kalman fusion (market + prior) | raw in-play line | 192,635 ticks / 673 games | **+0.000003** (0.078608 vs 0.078611) | [-0.0000091, +0.0000148] | NULL by three orders of magnitude. **The in-play line is a martingale at tick resolution** -- a local-level filter has nothing to smooth. Coverage deliverable is a measured NEGATIVE: nominal 90 pct intervals cover 0.0800 (P1 0.19, P2 0.12, P3 0.22, P4 0.08, OT 0.00) | `S97_nba_sensor_fusion_2026-09-03.md` |
| S98 better as-of prior + per-cell fitted sigma | raw in-play line | 162,171 ticks / 571 games / n_eff 2,130 | fixed sigma **-0.004805** -> fitted sigma **-0.002378** | [-0.007737, -0.001873] -> **[-0.004904, +0.000148]** (includes zero) | **THE PRIOR IS NOT THE CRUDE HALF, THE FIXED SIGMA IS.** No prior on disk beats Elo p0 at the first tick; `p_base == p_elo` byte-identically. One favourable cell CI excluding zero (P4 close, 2-6 min: +0.003210 [+0.000084, +0.006336]) is still under the bar | `S98_nba_better_prior_2026-09-03.md` |
| S103 sigma grid widened to [3, 60] + a parametric sigma | raw in-play line | 673 games / 192,635 ticks (span extended to 2026-06-10, 39 post-04-12 games) | **-0.002117** (wide grid), -0.003749 (parametric) | [-0.004670, +0.000436]; parametric CI **excludes** zero on the wrong side | The bound was real and worth **+0.000261**. Low end re-pins at 3.0 -> CLOSED AT LIMIT, not widened again. Blend -0.000130, behind the market and the recal null (fourth confirmation) | `S103_nba_sigma_2026-09-03.md` |
| S101 conformal coverage on ticks | nominal 90 +/- 2 pct grouped coverage | 192,635 ticks / 673 games | grouped coverage **0.08 -> 0.936-0.980** per phase at ~10x the Gaussian width | -- | **BAR NOT REACHED in any phase** (over-covers by 2-8 points; closest 0.8800 at P2, a miss, tolerance not widened); OT prior is the hard failure at 0.6471. The ONLINE ACI arm saturates at coverage 1.000 and is **LABEL-CONSUMING** -- reported as a ceiling, never as a leak-free number. STATIC is the deliverable | `S101_aci_coverage_2026-09-03.md` |
| S102 pod sweep, 576 frozen derived-state hypotheses | recalibration null | 192,635 ticks / 673 games / 68,925 informative; 3,266.7 screens/hour | **0 of 564 clear +0.004**; best **+0.000248** (16x below the bar) | [-0.000664, +0.001160] | SCREEN NULL. Within-family BH at q = 0.05 yields 29 "discoveries", all 29x-4,000x below the bar. Top 10 reproduced locally to 6.8e-14 on a different pandas major. The walk-forward recalibration of the line is again WORSE than the raw line (0.078969 vs 0.078611) | `S102_nba_pod_sweep_2026-09-03.md` |
| S114 nested-selection ensemble (k = 1, 3, 5, 10 by distinct source column), on the pod | raw in-play line | S86 screen side | best arm k=5 **-0.000400** | [-0.000934, +0.000133] | SCREEN NULL, 10x below the bar on the wrong side; all four arms also behind the recal null. **S102's headline does not survive nested selection** (its best form is never picked in any fold; the k=1 arm is -0.000125 behind the null). S79's "combining is worse than k=1" does NOT reproduce: k=5 beats k=1 by +0.0000830 [+0.0000027, +0.0001634], p 0.0429 -- 48x below the bar. **Register cell still reads OPEN; memo landed** | `S114_ingame_ensemble_2026-09-03.md` |
| S115 non-linear residual models (HGB depth-3, small MLP, monotone HGB) with logit(market) as a true offset | raw in-play line | 192,635 held-out ticks / 673 games; n_eff 3,240 | best arm (mlp) **-0.000549** | [-0.001476, +0.000378] | NULL. 0 of 3 beat the recal null; PBO 0.071. Both HGB arms picked the strongest L2 in 5 of 5 folds -- the inner CV asked for the least capacity on offer (the same shape as S108 and S111) | `S115_ingame_models_2026-09-03.md` |
| S84 lineup-strength as-of term | `nba_mechanism_ladder` BASE incumbent | 33,713 ticks / 284 games | -0.000455 (0.153324 -> 0.153779) | [-0.003920, +0.003009], DM p 0.7960 | SCREEN NULL. Premise falsified both halves; lineup-at-tick nonetheless built from substitutions: coverage 0.00 pct -> **577 games / 68,632 priced ticks at a full 5v5** | `S84_nba_lineup_at_tick_2026-09-03.md` |
| S92 non-static lineup terms: `fatigue_min`, `fatigue_share`, `unit_onoff` | `nba_mechanism_ladder` BASE incumbent (market line and the S94 null reported beside it) | ALL corpus 79,554 ticks / 661 clusters, n_informative 72,546-72,583, n_eff 2,348-3,185 | vs incumbent **-0.000212 / -0.000098 / -0.000397**; vs market -0.004185 / -0.004071 / -0.004370; vs null -0.002768 / -0.002655 / -0.002954 | [-0.000814, +0.000390]; [-0.000828, +0.000632]; [-0.001058, +0.000263] | **SCREEN_NULL x3.** Making the lineup term non-static does not repair what S84's static PIE sum could not: no term clears +0.004, none has a CI excluding zero, none beats the recal null. Corpus widened 2.3x (577 -> 1,331 bridged games / 160,291 ticks). On S84's exact RATED 577-game split the best is `fatigue_min` +0.000475 [-0.000579, +0.001530], also NULL | `S92_nba_lineup_dynamic_2026-09-03.md` |

### 2b. MLB -- in-game (the joined tick store: 78,986 rows, 227 game_ids = **392 real games** after S106)

| arm | reference | n units | improvement | CI | verdict | memo |
|---|---|---|---|---|---|---|
| S82 in-game screen tier, 14 state features (the tier itself is the deliverable) | e4 blend recalibrated on identical rows (the NULL arm) | 15,702 ticks / 41 game_ids (13,184 NO_TRAIN recorded) | **0 of 14 clear +0.004**; best `tick_index_in_game` **+0.003332**, `leverage_proxy` +0.001148 | [-0.001971, +0.008636]; [-0.000106, +0.002403] | SCREEN NULL, SINGLE-WINDOW. Recalibration alone is +0.006540 [-0.008751, +0.021831] -- a raw-e4 comparison showed a spurious +0.006 that was recalibration, not the feature. `score_diff` re-added = -0.018 (the instrument catches the degenerate hypothesis). The null trails the in-play line by 0.005966 | `S82_ingame_screen_2026-09-03.md` |
| S119 the same 14, re-quoted on the corrected **88 real-game** clusters | same null | 15,702 ticks / 88 real games | **0 of 14 clear**; leader +0.003332 | **[-0.003705, +0.010370]** (half-width 0.007038 vs 0.005304 on game_ids) | SCREEN NULL. **PREMISE-STOP on the supply half**: only 1 of the 5 members the row names is suppliable (`mlb_pitcher_id` is non-null on 8,287 of 78,986 ticks over 53 game_ids, all 2026-07-09..07-12); 7 of 7 S82 NOT_SUPPLIED members have no source. On a calendar-clean re-cut the S82 leader loses half its point estimate. **Register cell still reads OPEN; memo landed d6efd2f36** | `S119_mlb_ingame_supply_2026-09-03.md` |
| S80 player-grain arm (pitcher as-of run-prevention residual, shrunk IP/(IP+30)) | e4 blend | 2,267 ticks / 13 games | **+0.003759** (0.248462 -> 0.244703) -- **below** the bar | [-0.0269, +0.0344], DM p 0.7937 | SCREEN NULL, SINGLE-WINDOW. Companion purge-only arm (3,717 / 23 games) is **-0.005770** | `S80_player_grain_2026-09-03.md` |
| S83 the same arm reading identity from the fixed joined store | e4 blend | 2,262 ticks | +0.003623 | -- | SCREEN NULL; the join now carries the five `mlb_*` player columns (0 -> 11,071 rows, 8,287 non-null over 53 games) | `S83_mlb_join_player_ids_2026-09-03.md` |
| S99 analytic Poisson/Skellam rest-of-game distribution vs moneyline | in-play moneyline | 52 games / 90,915 ticks | **-0.040410** (0.201034 vs 0.160624) | [-0.069640, -0.011180] | BEHIND with the CI excluding zero -- wrong sign | `S99_cross_market_2026-09-03.md` |
| S99 the same distribution vs the total | in-play total | same | **-0.020601** (0.160422 vs 0.139822) | [-0.035143, -0.006058] | BEHIND, CI excluding zero. CRPS 2.8213. Market self-consistency mean abs 0.2614 (mlb) | same |
| S100 order-book microstructure (depth imbalance, spread, trade flow) | e4 blend | as-of feature covers 1,346 ticks / 35 games = **1.70 pct**; only 18 SCREEN games < the 20-game stop rule | **no arm was run** | descriptive imbalance sign 0.5508 on n = 305 / 25 games, CI [+0.00003, +0.10161] -- one cell of eight, chance-level for eight uncorrected tests, gone at a 60 s cap | **PREMISE FALSIFIED AT TICK GRAIN**: the captures are pre-game snapshots. `spread_bp` / `book_thinness` / `stale_quote` are null on all 25,585 rows | `S100_microstructure_2026-09-03.md` |
| S93 enlarging the MLB corpus so the bar becomes resolvable | -- | 177 of 3,780 priced events reconstructable (4.68 pct); 3,426 (90.63 pct) unreachable from disk | -- | needs ~289 clusters / 1,601 scored games for a 0.002 half-width; the full on-disk enlargement reaches **43** | **CLOSED AT LIMIT.** The 12,772,159-row moneyline corpus carries a price and a timestamp and **no game state** -- the missing half is STATE, not a model series | `S93_mlb_every_tick_2026-09-03.md` |

**The MLB in-game bar is structurally unresolvable at this n.** Every MLB in-game CI half-width
sits near 0.005, wider than the +0.004 bar (S82 41 clusters, S80 13, S72 13 folds, S119 88 real
games). NULL is guaranteed regardless of the feature until the corpus grows.

### 2c. Soccer -- in-game

| arm | reference | n units | improvement | CI | verdict | memo |
|---|---|---|---|---|---|---|
| S117 the S82 tier on soccer_intl, 7 minute x score-state x prior features | the game's own first `model_prob` (labelled; the soccer gate corpus has no p_close and zero KXWC ids) | **29 usable games / 3,658 ticks**, 2026-06-28..07-12 (13 games on the iso_week SCREEN side) | **0 of 7 clear +0.004** in either arm; behind the raw line throughout (market 0.157753) | every CI straddles zero; best half-width **0.020755** on 8 clusters | SCREEN NULL, **CLOSED AT LIMIT** on corpus size: ~862 games needed for a 0.002 half-width; the store holds 29. The verbatim 1,000-tick train floor eats 87 pct of the screen side (4 of 6 folds unfittable); a labelled floor-200 sensitivity arm is reported beside it and the BAR was untouched | `S117_soccer_ingame_screen_2026-09-03.md` |
| S99 rest-of-game distribution, soccer | in-play markets | 8 games | -- | CIs span zero | NULL at this n | `S99_cross_market_2026-09-03.md` |
| S104 soccer state capture | -- | 51 files; 22 carry the bare `live` sentinel on every tick | -- | -- | Writer premise FALSIFIED (it already satisfied the bar); the 22 legacy files are CLOSED AT LIMIT -- score unrecoverable from any store on disk. **NEW MEASUREMENT: 75.26 pct of 607,224 mlb and 92.80 pct of 468,712 soccer joined ticks carry no usable state** | `S104_soccer_state_asof_2026-09-03.md` |

### 2d. Tennis -- in-game

**No scorable tennis in-game surface exists.** S82 measured 0 settled ticks in the joined tennis
store; soccer and tennis in-play have no in-play close on disk (S58 batch 2 /
`INGAME_SIGNAL_PROGRAM_2026-09-03.md`). Nothing to report and nothing claimed.

### 2e. Cross-sport in-game

| arm | reference | n units | improvement | CI | verdict | memo |
|---|---|---|---|---|---|---|
| S116 sport-blind partially pooled residual, MLB side | raw in-play line | 9,669 ticks / 63 real games / **n_eff 103** | **+0.012837** (0.215528 -> 0.202690) | **[-0.002273, +0.027948] -- CROSSING ZERO** | SCREEN NULL, bar NOT met, no prereg. vs the S94 null +0.008137 (also crossing). Fully pooled is the WORST arm (-0.007614 vs per-sport). Partial pooling cut MLB across-fold coefficient sd 0.276 -> 0.206 (-25 pct) but over **only 2 usable folds** -- a direction, not a measurement | `S116_pooled_ingame_2026-09-03.md` |
| S116, NBA side | raw in-play line | -- | -0.000343 (the residual does not help NBA) | -- | "must not hurt NBA" is closed **BY CONSTRUCTION, not tested**: the corpora are date-disjoint and ordered (NBA ends 06-10, MLB starts 06-30), so all three arms are byte-identical | same |

### 2f. In-game -- the three findings that hold across every lane

From `INGAME_WAVE_VERDICT_2026-09-03.md`:

1. **A recalibration of the line fit on the past is itself BEHIND the raw line out of sample**
   (S94, S96, S98, S102, S103 -- four independent confirmations).
2. **Blending a state price into the line never beats the line** (four confirmations).
3. **The line drifts after events** (slow mid-updating, S96) **but the drift is too small to
   convert**, and a placebo on non-event ticks carries a third to two thirds of it.

With the data on disk, the in-play line is efficient at tick resolution within the +0.004 Brier
bar in **every** direction tested: state, player grain, dynamic lineup state (fatigue and unit
on/off), phase recalibration, overreaction, sensor fusion, prior quality, distributional
consistency, a 576-form sweep, nested selection, non-linear residual models, and cross-sport
pooling.

### 2g. In-game denominators -- what S87 and S106 corrected

- **S87 (70 pct of ticks are duplicates):** on `ingame_grade_joined/mlb`, market_prob is held from
  the previous tick on 74.97 pct of rows, model_prob on 91.71 pct, both on 69.86 pct; duplicate
  (game_id, ts) rows 1,659 (2.10 pct); informative ticks 23,964 of 78,986. Three headline CIs were
  re-quoted on informative ticks: S58 trial A 47,104 -> 14,543 ticks (n_eff 566 -> 1,098) and its
  mean differential **collapses 0.000866 -> 0.000031** -- the apparent separation sat in ticks
  where neither side moved. S80 2,267 -> 1,106. **0 verdicts were re-labelled.**
- **S106 (one game_id was several real games):** 144 of 227 files span > 6 h; the capture bridged
  a Kalshi ticker to the live game by team pair with no date check, so the next day's game was
  written under the previous ticker. 227 game_ids -> **392 real games**, 122 multi, 22,768 of
  78,986 ticks (28.8 pct) reassigned. Re-quoted on corrected clusters: **every verdict unchanged,
  every CI still spans zero.** Published MLB in-game "n games" was understated ~2x. S107 fixed the
  bridge and it is deployed on the pod (pid 360964); the verification window is SINGLE.

---

## 3. The 18 charged trials, in K order

`data/cache/eval_gate/backtest_fwer.jsonl`, read-only, 18 rows. **No charge was consumed by the
S79-S119 wave: the ledger stood at 18 before it and stands at 18 after it.** Rows 1-14 predate
the S14 family partition and carry no `family` or `tier` field.

| K | family | tier | predictor | sport | window | verdict, from its memo/artifact |
|---:|---|---|---|---|---|---|
| 1 | (absent) | (absent) | `signals.foundry_run:schedule_rest` | basketball_nba | 2025-10-21..2026-04-12 | **BEHIND** vs the devigged close: 0.248549 vs 0.198130, n 1,156, dm_p 0.000000 (`FOUNDRY_RUN_2026-09-01.md`) |
| 2 | (absent) | (absent) | `signals.foundry_run:venue_altitude` | basketball_nba | same | **BEHIND**: 0.249495 vs 0.198130, n 1,156, dm_p 0.000000 (same) |
| 3-11 | (absent) | (absent) | `analytics_showcase.mechanism_foundry:trial_00` .. `trial_08` | basketball_nba | same | **BEHIND x9** -- the nine triggered NBA mechanisms, each n 1,156, model Brier 0.226091-0.249773 vs devigged close 0.198130, dm_p 0.000000 (`analytics_showcase/out/mechanism_wiring.json`: 27 mechanisms, 9 with a trigger, 18 NOT_TESTABLE) |
| 12 | (absent) | (absent) | `hedge_trial_runner:hedge_over_gap_arms` | mlb | 2026-06-28..07-12 | **BEHIND**: 0.223656 vs market 0.195387 on 158 games / 47,104 ticks; regret 2.063 inside a 66.793 bound (`hedge_trial_2026-09-01.json`) |
| 13 | (absent) | (absent) | `hedge_trial_runner:e4_promotion` | mlb | same | **market sharper** -- e4 Brier 0.207033 vs market 0.195387, gap +0.011646 [0.003485, 0.021119], 158 games / 47,104 ticks; arm verdict SHIP_TO_SHADOW (`E4_REPLICATION_RESULT_2026-09-03.md`, `e4_promotion_trial_2026-09-01.json`) |
| 14 | (absent) | (absent) | `eval_gate.stacker:mlb_stack_v1` | mlb | same | **BEHIND (SINGLE-WINDOW)**: 0.296943 vs incumbent 0.207033, deflated_p 0.000553 at K=14 (`S06_stacker_result_2026-09-03.md`) |
| 15 | `ingame_mlb_arms` (alias -> `ingame_arms_mlb`, S89) | T2 | `eval_gate.s58_e2_slice_trial:mlb_e2_slice_v1` | mlb | 2026-06-28..07-12 | **BEHIND (SINGLE-WINDOW)**: e2_regime 0.254351 vs e4 0.206079 on e2's own 6,579-tick / 157-game slice, improvement **-0.048272**, DM CI [-0.072123, -0.024422], deflated_p 0.001475, PBO 0.0, ESS n_eff 467.3. e4_blend STANDS; S06's regime cause is now a measured negative (S58 batch 1) |
| 16 | `ingame_mlb_clamp` (alias -> `ingame_arms_mlb`) | T2 | `eval_gate.s58_clamp_family_trial:mlb_clamp_family_v1` | mlb | same | **NULL (SINGLE-WINDOW)**: market-anchor clamp family, 9 configs inner-selected via CPCV, **+0.000866** vs e4_gd 0.206786 on 47,104 ticks, DM CI [-0.000364, +0.002096], deflated_p 1.0. Instrument defect: inner selection was operative on only 5 of 13 folds (S72; repaired to 12 of 13 on a dry run, RECHARGE_BLOCKED until re-prereg). On informative ticks the differential collapses to +0.000031 (S87) |
| 17 | `ingame_nba_halftime_asof` (alias -> `ingame_arms_nba`) | T2 | `eval_gate.s58_nba_halftime_asof_trial:nba_halftime_asof_v1` | nba | 2024-10-22..2026-06-13 | **BEHIND on 0 of 2 units**: as-of Elo prior 0.171360 vs the Polymarket price 0.164777 on 1,593 halftime games, **-0.006583**, DM CI [-0.011503, -0.001664], deflated_p 0.1488. The old run-time-Elo -0.0040 is NOT reproduced. Unit 2024-25 CI excludes 0; 2025-26 includes 0 (S63) |
| 18 | `soccer_gate` (in the frozen partition) | T2 | `foundry:d65df2a95aeb0f49` | soccer | 2019-08-02..2026-05-24 | **MATCH (SINGLE-WINDOW)**: `diff_shots_for_asof` ew10 vs the devigged close on the hash-disjoint verdict partition (8,666), **-0.000057**, DM CI [-0.000831, +0.000717], deflated_p 1.0 at launch K=18, family n=1, PBO 0.581, per-unit CIs all contain 0 (n_corpora 0/3, floor 2). The factory ran end to end |

**Nothing in this ledger is an AHEAD.** Fourteen BEHIND, two NULL, one market-sharper, one MATCH.

---

## 4. DO-NOT-CLAIM -- refreshed 2026-09-03

This section supplements, and does not replace, the do-not-claim table in
`docs/JOB_EVIDENCE_PACKET.md` and the retracted-figure list in
`.claude/rules/no-edge-claims.md`. The six retracted figures enumerated in that rule file remain
retracted; they are deliberately not restated here.

**New this wave -- three classes of number that must never be presented as market-relative:**

1. **Every "vs Elo" positive is NOT market-relative.** The NBA and MLB gate corpora's incumbent
   `p_base` is Elo, and S112 measured that the close beats it by **+0.025606** (NBA, n 351) and
   **+0.007269** (MLB, n 276). So:
   - **S85's `nba_player_value_features` +0.005221** [+0.000244, +0.010199] is vs Elo. Against the
     close on the same rows it is **-0.000660** (S112) and under the close incumbent it is
     **+0.000178** (S113). Never quote +0.005221 without both of those.
   - **S111's `nba_quarter_shape` +0.001527** is vs Elo, and it is a null even there.
   - **S58c's "NBA 62 of 564 screens beat"** figure is 62 screens beating a *recalibrated Elo*,
     not a close. **0 of 600** soccer + tennis screens beat the close by any margin.
   - **147 of 240** Elo-relative promotions vanish once the incumbent is the close (S113). The
     140 NBA/MLB S58 promotions must never be charged as market-relative.

2. **S116's +0.0128 is not a result.** The MLB pooled in-game arm reads +0.012837 with a
   **game-clustered CI [-0.002273, +0.027948] that crosses zero**, on n_eff 103, over **only 2
   usable folds**. The bar was not met and no prereg was written. Quote it only as "a direction,
   not a measurement", exactly as its memo does.

3. **Nothing beats the close or the in-play line at the +0.004 bar.** Not one signal, arm, family
   combination, full-feature model, ensemble, non-linear residual model, or pooled fit, in any of
   the four sports, on either surface. The single charged pregame trial against a real close
   (K=18) is a **MATCH** at -0.000057. The strongest in-game arms are all behind the line.

**Also do not claim:**

- **S102's best in-game hypothesis (+0.000248).** It was chosen after seeing all 564 out-of-sample
  results; under nested selection it is never picked in any fold and the k=1 arm is behind the
  null (S114).
- **S81's MLB R^2 +0.85170.** The AR(1) coefficient is 0.987-1.021 in every fold -- the model
  discards the open and recovers a stale 3-day-out quote. 87.1 pct of MLB first ticks sit at a
  0.500 listing placeholder.
- **Any online-ACI coverage number.** The online arm is label-consuming (the outcome is constant
  within a game, so every within-game update reads it). Only the static conformal band is
  leak-free, and it misses the 90 +/- 2 bar in every phase (S101).
- **The in-sample per-phase recalibration numbers** (S88, still OPEN): the MLB
  late-leading_big 0.3745 -> 0.2759 pools to NO_CHANGE and its winner spec was chosen in-sample;
  the NBA one is an orphan of the retracted endQ3 lineage with no CI and no market baseline --
  **unquotable**.
- **The 86 registry signals as tested signals.** All 86 are NOT_TESTABLE (no column named in any
  corpus); `coverage_pct` is null 86 of 86 (S64, S56).
- **Any single-window number as replicated.** Every result in sections 1 and 2 above is labelled
  SINGLE-WINDOW. The S08 two-corpora replication floor has been satisfied by **no** result in
  this wave.

---

## 5. Forward / paper status -- as of tonight (2026-09-03)

Read from `data/frontend/analytics/execution_status.json` (generated 2026-09-02T14:10:16Z over
`data/frontend/clv_ledger.jsonl`) and `docs/evidence/execution/PAPER_LIVE_2026-09-03.md`.

| field | value |
|---|---|
| status | **`no_data`** |
| verdict | **INSUFFICIENT** |
| n_settled | **INSUFFICIENT** (settled row class = 0) |
| n_records | 20 (18 open, 2 legacy, 0 settled, 0 maker, 0 taker) |
| n_integrity_flags | 0 |
| settled_by_day / settled_by_sport | empty |
| as_of | 2026-09-02T14:10:16Z **(no rows)** |
| PAPER_LIVE window | 2026-09-03T00:00:00Z, status `no_data`, n_settled INSUFFICIENT |

**Honest statement: there is no forward or paper result. Zero settled paper rows exist. Nothing
prospective has been measured, and no forward claim of any kind is available tonight.**

The related corpus row, **S55**, is still OPEN: the MLB in-game replication corpus (window 2, the
second corpus every AHEAD needs to satisfy Q5) does not exist -- the pod tick store holds settle
stubs only and local `ingame_grade` has 0 usable paired+settled games after 2026-07-12.

---

## 6. What still moves the number -- acquisitions and capture, not models

From `INGAME_WAVE_VERDICT_2026-09-03.md`, `INGAME_GAP_MAP_2026-09-03.md`,
`INGAME_GAP_PREMISES_2026-09-03.md`, and the S93 / S62 / S105 / S107 / S78 rows. **None of these
is a modelling row.** Thirteen modelling directions were tested this wave; all thirteen are null.

1. **MLB game STATE for the 3,780 priced events (S93 -> S62 DECIDE row 3).** The 12,772,159-row
   moneyline corpus carries a price and a timestamp and no state; 177 of 3,780 events (4.68 pct)
   are reconstructable from disk and 3,426 (90.63 pct) are unreachable. The MLB in-game interval
   needs ~289 clusters / 1,601 scored games for a 0.002 half-width and the full on-disk
   enlargement reaches 43. The route is a keyless historical backfill of
   `/api/v1.1/game/{game_pk}/feed/live` for ~3,780 games (~3,780 GETs), or ~90 days of forward
   capture plus a retention change. **This is Neel's licence decision (S62), not an engineering
   task.** Until it is decided, MLB in-game screens cannot resolve the +0.004 bar.

2. **Depth capture DURING scored games (S105, S100).** 90.09 pct of book_depth rows and 88.06 pct
   of depth_history rows are markets 1-3 days out; 227 of 231 MLB tickers stopped being captured
   before their own first pitch (median 61.1 h). Root cause found and fixed (ticker selection: the
   runner rebuilt the sticky active list empty every 30 s). The 60 s bar is UNMET and NOT LOWERED:
   `depth_history` runs at 15 ticks x 20 s = 300 s, and shortening it multiplies the paper node's
   request rate 5x -- an orchestrator/Neel call. `mlb_book_capture` already captures full ladders
   first-pitch-to-final at median 30.0 s / p90 64.8 s; it needs **reach** and a **consumer**. The
   remaining distance to microstructure is a JOIN, not a capture.

3. **In-play ticks with state for a second sport.** Soccer captures are structured from
   2026-06-28 (S104) and the tier now runs on soccer (S117), but the store holds 29 usable games
   against the ~862 needed for a 0.002 half-width.

4. **Licence decisions (S62).** The licence ledger holds 21 sources: 6 DECIDE (ESPN/Disney, NBA
   Stats API, MLB StatsAPI/GUMBO, Statcast non-bulk, FotMob, YouTube footage), 3 OK, 12 UNREAD --
   including the whole tennis spine, whose upstream repos 404. The commercial historical close
   feed purchase is the same decision. **Six of the acquisitions that would move a number are
   blocked on a human licence call, not on code.**

5. **Pregame coverage and reference acquisitions.** S111 showed the coverage acquisitions were on
   disk and produced 678 screens that had never existed -- every one null. S112 showed the NBA
   close attaches to 52.48 pct of the corpus and the MLB close to 8.00 pct over 74 days at one
   venue. **Pre-tip NBA prices** (a price series keyed on `nba_close_corpus.commence_time`) would
   reopen the open-to-close target that S81 found falsified for NBA.

6. **Capture-side correctness that was silently costing denominators.** S106/S107 (one ticker held
   up to three real games; 28.8 pct of ticks mislabelled; bridge now date-guarded and deployed),
   S105 (ticker selection), S104 (75.26 pct of MLB and 92.80 pct of soccer joined ticks carry no
   usable state), S78 (the pod bootstrap provisions none of the factory's source tables; 127 files
   / 76 MB were shipped by hand). Fixing capture does not create a signal, but every one of these
   was inflating or deflating a denominator that a verdict was quoted against.

7. **The tracking teacher (Phase M).** The one class of information no test above could reach:
   features the line cannot see. It remains untested against a market.

---

## Provenance

Every figure above is transcribed from one of: the S-register row that landed it
(`docs/evidence/HARNESS_GAPS_2026-09-03.md`), the memo named in its row, the read-only FWER ledger
`data/cache/eval_gate/backtest_fwer.jsonl`, `analytics_showcase/out/mechanism_wiring.json`,
`docs/research/organization-sprint/FOUNDRY_RUN_2026-09-01.md`,
`data/frontend/analytics/execution_status.json`, or
`docs/evidence/execution/PAPER_LIVE_2026-09-03.md`. Nothing was recomputed. Two rows (S114, S119)
have a landed memo whose register status cell still reads OPEN at the time of writing; both are
labelled as such above. S92 landed at 464f5e150 while this page was being written and its row is
current. S88, S90, S118 are OPEN with no result.

---
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Register](HARNESS_GAPS_2026-09-03.md)

---

## 7. POST-FIX COLUMN (S137, appended 2026-09-03 -- nothing above this line was edited)

Everything above was transcribed BEFORE the round-2 fixes landed. Five instruments then changed
at once: the clean NBA/MLB close (S132/S133), the corroborated real-game split 392 -> 360 (S131),
the tick-level partition (S121), the same-rows recalibration null (S126) and UTC stamp parsing
(S125, a measured no-op). This section is the post-fix column for every headline above that any
of them reaches. Source: `docs/evidence/harness/S137_rebaseline_2026-09-03.md` and
`data/cache/eval_gate/s137_rebaseline_2026-09-03.json`. Every published number was reproduced
from its own archive before its post-fix number was read (14 of 14 comparable intervals; 12 at
1e-9). Calibration language only; a screen is still a non-finding.

**Headline: 0 verdicts change. 0 AHEAD before, 0 AHEAD after. Two LABELS change.**

| row | as published above | post-fix | what moved | verdict |
|---|---|---|---|---|
| S82 / S119 / S121 (one measurement, three stages) | 15,702 ticks / 41 tickers, +0.003332, CI [-0.001971, +0.008636]; on 88 real games CI [-0.003705, +0.010370] | **15,336 ticks / 73 real games, +0.001951, CI [-0.004611, +0.008512]**, n_eff 214.83 -> 107.06; S119 alone 88 -> **76** clusters, CI [-0.003805, +0.010469] | the leader's point estimate falls **41 pct** (the tick partition, not the split); every interval still spans zero | SCREEN NULL, unchanged |
| S87 (trial A clamp re-quote) | 47,104 ticks, 315 real-game clusters, n_eff 569.67, CI [-0.000212, +0.001944] | 47,104 ticks, **284** clusters, n_eff **521.04**, CI **[-0.000262, +0.001994]** | cluster unit only; mean differential +0.000866 unchanged (no refit) | NULL, unchanged |
| S87 (the 70-pct-duplicate premise) | 78,986 ticks / 227 game_ids; held market 74.97 pct, model 91.71 pct, both 69.86 pct; dup 1,659; informative 23,964 | identical -- the counts are per (game_id, ts). Only the GAME denominator moves: 227 game_ids -> 392 -> **360** real games | nothing | unchanged |
| S106 | 227 game_ids -> **392** real games, 122 multi, 22,768 ticks (28.8 pct) reassigned | 227 -> **360**, **112** multi, **21,318** reassigned; boundary reasons {ts_gap 129, inning_decrease 4} where they were {inning_decrease 156, score_reset 6, ts_gap 3} | 32 near-instant "boundaries" (a 1-inning feed regression, gaps of 1-13 s) are refused; all 129 genuine > 5 h splits survive | "every verdict unchanged, every CI still spans zero" -- still true |
| S112 NBA | close beats Elo by **+0.025606**, n 351, CI [+0.015252, +0.035960]; close attaches to 952 of 1,814 (52.48 pct) | **+0.021819**, n **171**, CI **[+0.010468, +0.033170]**, p 4.82e-04; coverage **563 of 1,814 (31.04 pct)** | 389 of the old 952 were in-play ticks carrying a scoreboard. The clean close is measurably LESS sharp (0.186122 -> 0.191493) -- part of the old reference's sharpness was the score | close still ahead of Elo; unchanged |
| S112 MLB | close beats Elo by **+0.007269**, n 276, CI [+0.000066, +0.014473], p 0.0481; 894 closes | **+0.006709**, n **281**, CI **[-0.000198, +0.013617]**, p **0.0564**; **910** closes | **RE-LABEL:** the interval now includes zero | a marginal positive becomes an honest **NULL**. Every model arm is BEHIND the close before and after |
| S113 | **147 of 240** Elo-relative promotions vanish; best family +0.000640, CI [-0.003011, +0.004291]; 889 rows, window 800 -> 499 | **154 of 240** (64.2 pct); best **+0.002302**, CI **[-0.003129, +0.007733]**; served window nba **313**, mlb **460**; screens beating the close **10 of 945 -> 43 of 945** | a cleaner reference is a slightly easier one, and is still not beaten | NULL, unchanged. The conclusion is slightly STRONGER: 7 more Elo-relative promotions fail |
| S114 | best arm k=5 **-0.000400**, CI [-0.000934, +0.000133], n_eff 2,369; k=5 over k=1 +0.0000830 [+0.0000027, +0.0001634] p 0.0429 | **RE-RUN REQUIRED** (the same-rows null changes the FITTED arm) -- `python -m scripts.platformkit.eval_gate.s114_ingame_ensemble`, **run and landed** (S126). k=5 **-0.000243**, CI **[-0.000663, +0.000177]**, n_eff **2,674.8**; vs its OWN same-rows null **-0.000070** [-0.000286, +0.000147]; k=5 over k=1 **+0.000294** [+0.000023, +0.000565] p 0.0333; PBO over k **0.80** | the arms are finally scored on the same rows, which SHRINKS the apparent gap to the null | SCREEN NULL, unchanged. The k-over-k1 interval still excludes zero and is still **14x below the bar** |
| S116 | +0.012837, CI [-0.002273, +0.027948], **63** MLB clusters, n_eff 103.06; row cited "392 real games" | +0.012837 (no refit), CI **[-0.002376, +0.028051]**, **54** clusters, n_eff **95.09** | re-quoted here for the first time -- no other lane had done it | SCREEN NULL crossing zero, unchanged, and now correctly labelled |
| **S127** | (open row) | **DISCHARGED as a re-label.** S116's MLB side is scored on folds 3 and 4 only: fold 3 = 7,972 ticks / 52 clusters / test date 2026-07-04, fold 4 = 1,697 / 11 / 2026-07-05 | 63 S106 clusters over **2 calendar dates**, 54 after S131, against 673 NBA game-clusters over 18 months | the S116 MLB readout is **SINGLE-DATE-PAIR**. Its +0.012837 stays "a direction, not a measurement" |
| S117 | 29 usable games / 3,658 ticks; leader +0.025071 on 163 ticks / 2 clusters; 0 of 7 clear | **identical.** Both S117 archives sit inside ONE ISO week, 0 ticks dropped, every improvement and CI byte-identical on all 7 features and both arms | the tick partition is the identity here; the real-game split is inning-based and claims no soccer purge | SCREEN NULL / CLOSED AT LIMIT, unchanged |
| S86, S94, S96, S97, S98, S101, S102, S103, S115, S123 | as published | **unchanged -- no instrument reaches them.** They sit on NBA corpora with no close attach, no MLB real-game split, no in-game tier partition and no S114 null. S102 is positively confirmed: S126's GATED re-run of its top 10 is byte-identical to the landed DB over 21 columns x 10 hypotheses | nothing | unchanged |
| S85 `soccer_style_fingerprints` (section 1c above) | -0.001158 vs the devigged close | **RE-RUN, not a re-quote** (the season-grain prior changes the FITTED arm). From S128 section 4: **-0.001006**, CI [-0.005228, +0.003216], DM p 0.6865, coverage 15,646 -> **14,878** of 16,322; 112 of 112 T1 rows moved | **0 of 112 improve on the close before, 0 of 112 after** | NULL, unchanged -- and now behind the close honestly. `nba_player_value_features` did not move at all (0 of 32); its +0.005221 is still vs Elo, never vs a close |

**What this section does NOT change.** Every do-not-claim item in section 4 above still stands,
and two are now firmer: S116's +0.0128 is not a result (and is a SINGLE-DATE-PAIR readout), and
every "vs Elo" positive is still not market-relative -- though the NBA close's advantage over Elo
is **+0.021819**, not +0.025606, and on MLB it is a NULL rather than a marginal positive. Nothing
beats the close or the in-play line at the +0.004 bar on either side of any instrument change.
The FWER ledger stood at **18 rows** before this wave and stands at 18 rows after it.

---
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Register](HARNESS_GAPS_2026-09-03.md)
