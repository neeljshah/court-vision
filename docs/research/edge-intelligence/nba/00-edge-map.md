# NBA EDGE MAP -- beatable vs efficient, per market, with evidence + tier

_Part of the edge-intelligence corpus. Sport = NBA. Grounded in the project deep-dives
(07-nba-prediction-models, 08-nba-montecarlo-sim-ratings, 09-intelligence-signal-atlases,
10-cv-tracking-pipeline, 11-live-ingame-layer), the framework (_framework/edge-theory.md,
cut-list-no-edge.md, proof-standards.md), and real artifacts/data on disk. ASCII only.
Tiers: HYPOTHESIS -> CALIBRATION-PROVEN (leak-free OOS BSS>0) -> CLV-PROVEN (forward paper CLV)._

## One-paragraph thesis
NBA pregame TEAM markets are EFFICIENT and at the historical-data ceiling (CUT 1 + CUT 2 of
the cut-list): ~17 feature-add reverts, 6 architectures + 4 levers REJECT on PTS/REB, recency
beats volume, season walk-forward is well-calibrated but CLV ~ 0. The DURABLE pockets are
narrow and specific: (1) AST pregame prop divergence (the one near-durable model signal,
~+7%, fragile, never playoffs), (2) SAME-DAY FRESHNESS on props (minutes/role/lineup the
historical box model cannot see -- the only unmodeled lever), (3) IN-GAME conditioning
(realized score is new info; calibration win, not $), (4) the COHERENT MC-sim JOINT for SGPs
(books price legs independently; our shared-pie sim makes correlation emerge). Everything
else: match the close, keep as calibrated decision-support, stop hunting $.

## The map

| Market / prop | Verdict | Tier | Evidence (file / data) | Action |
|---|---|---|---|---|
| Moneyline (pregame) | EFFICIENT | calib-proven (~match) | season WF CLV~0; `predictor.py` "match devigged close on ML"; win-prob 69.1% = accuracy not edge (07 sec3) | CUT 1/2: decision-support only |
| Spread (pregame) | EFFICIENT | calib-proven | same season-backtest; sim guidance "trust spread not total" (08:201) | CUT: match close |
| Game total (pregame) | EFFICIENT, gap=freshness | calib (trails) | sim over-predicts team totals ~+4.5 playoff-weighted (08:200); freshness is the unseen lever (07 sec7) | CUT $ hunt; push freshness |
| Team total | EFFICIENT | calib | derived from sim totals; same anchor bias | CUT |
| PTS prop | EFFICIENT (at ceiling) | calib-proven | holdout R2 0.5105, MAE 4.62 (`props_pergame_metrics.json`); 17 reverts; q50 OFF for pts | match close; freshness only lever |
| REB prop | EFFICIENT (at ceiling) | calib-proven | holdout R2 0.4224, MAE 1.91; +3 reb-context cols; q50 path | match close |
| **AST prop** | **BEATABLE (narrow)** | **HYPOTHESIS->calib** | the ONE documented near-durable model edge (~+7%, both directions); kept OFF q50/calibration ON PURPOSE to preserve divergence (07:115,189); `scripts/ast_edge_*` | KEEP RAW; never playoffs; re-prove leak-free OOS BSS vs devigged prop close |
| FG3M prop | EFFICIENT, marginal | calib | holdout R2 0.3151; ONLY atlas lift that clears all-folds (fg3m -0.003 MAE, 3/3) (09:168) | match close; low priority |
| STL prop | NON-BETTABLE (noise) | n/a | holdout R2 0.1120 = near base-rate (07:131,232) | flag low-confidence; DO NOT price as edge |
| BLK prop | LOW (near-noise) + CV candidate | HYPOTHESIS | R2 0.2166; sigma too tight (~x1.86); BLK has 3 CV features >=+0.15 corr (10:158) -- best CV retrain candidate but coverage-blocked (<20%) | inflate sigma; CV head gated on coverage |
| TOV prop | EFFICIENT (low) | calib | R2 0.2960 | match close |
| Player props on SOFT/DFS books (PrizePicks/Underdog) | **BEATABLE (P1 pocket)** | HYPOTHESIS | framework P1; books lazy; BUT props NOT wired to a keyless prop feed yet (top get-to-edge gap) | PRIMARY push once feed exists |
| Same-game parlay (SGP) | **BEATABLE (P5 pocket)** | HYPOTHESIS | coherent joint from `basketball_sim` shared-pie; teammate corr emerges ~-0.10; `sgp_from_sim.joint_prob` (08:174) | push; but ROI needs real SGP price capture (none on disk) |
| DD / TD / milestone ladders / alt-lines | BEATABLE-ADJACENT | HYPOTHESIS | all read off one 20k-sim run coherently (08:128); priced in `build_cv_board.py` | calibration-prove vs realized first |
| IN-GAME win-prob | calibration win (not $) | calib-proven (real corpus partial) | score-anchor RMSE Q1~12.5->Q4~4.2; NBA combined Brier ~0.159 vs ~0.209 pregame (11:417); BUT blend OOS still SYNTHETIC/PENDING (11:296) | push calibration; $ ceiling ~0 (book sees score too) |
| IN-GAME props | BEATABLE-ADJACENT (highest in-game upside) | HYPOTHESIS | routed-ensemble player MAE 1.01 vs 1.87 production, but OFF + single-corpus (11:336,429) | prove cross-corpus, RMSE+bias only |
| Momentum / hot-hand bets | DEAD | REJECTED | INT-81 z_vs_null=-1.75, momentum-aligned WORSE than random (CUT 3) | DO NOT build |
| Atlas/intel point features | DEAD FUNNEL | REJECTED | base+atlas WORSE: pts +0.174, reb +0.064, ast +0.008 MAE (09:168); unread by served model | scouting only |

## Where to PUSH (concentrate effort)
1. **Wire a keyless prop feed** (ESPN/PrizePicks/Underdog) -- unlocks P1, the primary pocket. Top blocker (see get-to-edge-plan).
2. **AST prop** -- re-prove the one model edge leak-free OOS vs the devigged prop close; keep RAW.
3. **Same-day freshness** (projected minutes / starting lineup / late scratch) wired in BOTH train + inference builders (parity) -- the only unmodeled accuracy lever; sim already has the `out_ids` hook (08:88).
4. **SGP coherence** -- the MC sim's joint is structurally unique; calibration-prove the joint vs realized, then price vs book legs.
5. **In-game calibration** -- end the SYNTHETIC PENDING flag (11 quick-win 1); real win, $-ceiling ~0.

## Where to CUT (stop hunting $)
Pregame ML/spread/total/team-total, PTS/REB/TOV props beyond calibration, STL props entirely,
momentum signals, atlas point-feature funnel. All map to cut-list-no-edge.md CUT 1/2/3 and the
DEAD FUNNEL finding (09). Keep them only as calibrated decision-support + a CLV yardstick.
