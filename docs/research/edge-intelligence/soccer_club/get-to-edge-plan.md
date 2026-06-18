# SOCCER-CLUB -- get-to-edge plan (quick wins -> big bets)
_The concrete, prioritized path to a PROVEN edge for club soccer. Each step: approach + how it
is VALIDATED (calibration vs devigged close / CLV). Tags per evidence tier. Build only in safe
areas (domains/soccer, scripts/platformkit, docs/research); never edit src/kernel/api. ASCII._

## The strategy in one paragraph
Club soccer's deep TEAM history is a CALIBRATION asset, not an edge -- we keep the coherent
scoreline surface as decision-support and a CLV yardstick (odds.parquet has real closes) and STOP
hunting team $ (CUT 1). All edge effort goes to the PLAYER-PROP and TEAM-COUNT (corners/cards)
pockets, where the WC prop engine already exists and only lacks DEEP per-player CLUB data -- the
exact ingredient the WC never had. The win condition is a club prop board where 3-5 high-volume
stats clear leak-free OOS bss>=0.05 across >=2 matchdays, then accrue positive forward CLV.

## Phase 0 -- prove the team baseline matches the close (CALIBRATION, days)
WHY FIRST: establishes the honest yardstick and confirms CUT 1 on our own data before reallocating.
APPROACH: run scoreline_engine.build_engine_forecast over matches.parquet; score engine vs Poisson
baseline (dBrier ~ 0 at rho=0 expected). Then score the model's O/U-2.5 p_over against the DEVIGGED
odds.parquet close (pc_over/pc_under).
VALIDATE: Brier/ECE/BSS of model vs devigged close on 16,322 odds matches. EXPECTED outcome: BSS ~ 0
(we match, do not beat). A null here is the SUCCESS that justifies cutting team $.
TIER: CALIBRATION-PROVEN (or honest null) -- no edge claimed.

## Phase 1 -- ingest deep club per-player box (DATA, days; the unlock)
APPROACH: extend ingest_espn_box.py's keyless summary endpoint to extract the boxscore.players
block (reuse ingest_espn_players.py's WC parser), across eng.1/esp.1/ita.1/ger.1/fra.1, backfilled
over multiple seasons via scoreboard?dates walks. Output: club espn_player_stats with a TRUE
per-match per-player series (not the single-snapshot espn_club_priors aggregate).
VALIDATE: row counts per league/season; leak-guard test (player_rates._prior_rows date<as_of);
per-player n_eff distribution -- target majority of regulars at n_eff>=5 (no longer thin).
TIER: enabling (no claim). This is pure data + plumbing, no model risk.

## Phase 2 -- re-prove Saves on club data at realistic lines (CALIBRATION, days)
APPROACH: build the club Saves rate (player_rates) + opponent SOT multiplier (team_defense Saves
<-opponent shotsOnTarget); run props_eval.backtest_calibration on the club Saves series at the
DFS-realistic line (2.5/3.5), NOT the lam-nearest .5 that inflated the WC number.
VALIDATE: bss>=0.05 AND >=100 preds across >=2 independent matchdays (proof-standards #4) +
seed/N stability (#5). Compare honestly to the WC +0.337 (expect lower at realistic lines).
TIER: target CALIBRATION-PROVEN. Saves is the proven-WC head start.

## Phase 3 -- capture closing prop lines + wire CLV (PROOF PLUMBING, days)
WHY CRITICAL: deep-dive sec 5 -- prop_paper/prop_loop have NO CLV; "the single biggest gap for
ever validating any edge claim honestly."
APPROACH: add a closing snapshot to prop_line_history (re-scrape PrizePicks/Underdog near kickoff);
store taken-price vs close so prop_paper computes CLV. For pick'em (no two-way close) fall back to
DFS-LINE MOVEMENT + realized P(over) calibration (edge-theory pick'em note).
VALIDATE: CLV ledger populates; a calibration-proven stat can finally accrue forward CLV.
TIER: enabling -> unlocks CLV-PROVEN for everything downstream.

## Phase 4 -- build team corners/cards props on the 25,834-match corpus (CALIBRATION, weeks)
WHY: the deepest-N, least-attended pocket (E1 Championship = 6,072 matches, P6 low attention).
APPROACH: per-team leak-free corners-for/against + cards NB rate (like asof_features); add a
leak-free referee-cards fixed effect (ref's PRIOR matches only). Price over X.5 corners / cards.
VALIDATE: WF calibration vs posted totals on the huge corpus -- big N can actually clear
proof-standards #4/#5 (unlike the thin WC). Devig the posted total; require BSS>0 on >=2 folds.
TIER: HYPOTHESIS -> CALIBRATION-PROVEN if it holds. The most plausible club calibration edge.

## Phase 5 -- Shots/SOT/Fouls club proof + position-conditioned dispersion (CALIBRATION, weeks)
APPROACH: with deep club rates (Phase 1), re-run props_eval cache for Shots/SOT/Fouls/Fouls-Drawn;
split dispersion + position baseline by role (GK vs outfield first). Re-test opponent-adjust each
matchday (currently a null) and ship only on >=2-matchday OOS improvement.
VALIDATE: bss>=0.05 across >=2 matchdays per stat; opponent lever ships only if it improves OOS
Brier (re-running the exact null test in team_defense). HYPOTHESIS: club depth lifts Shots from
WC's +0.008 to proven.
TIER: per-stat CALIBRATION-PROVEN where it clears; honest demotion where it does not.

## Phase 6 -- minute-projection error + confirmed-XI freshness (CALIBRATION + EXECUTION, weeks)
APPROACH: re-run the backtest with PROJECTED (not realized) minutes to MEASURE live-board minute
error (deep-dive medium #5); then add a confirmed-XI scrape near kickoff to sharpen
player_minutes, flagging props where confirmed-minutes lam diverges from the line.
VALIDATE: report the projected-vs-realized-minutes calibration gap (re-tiers some stats down
honestly); for the freshness edge, forward realized ROI + DFS line movement after XI release.
TIER: HYPOTHESIS; this is the same-day freshness lever -- the one place club data plausibly beats
a lagging DFS line.

## Phase 7 -- joint/correlated SGP + club in-game (BIG BETS, only if vertical is a priority)
APPROACH: copula / shared-latent shot-volume for Shots+SOT+player-goals (P5); then re-feed
scoreline_matrix with time-scaled lambdas for live 1X2/total repricing (P2).
VALIDATE: joint over-prob calibration on the FULL stat-pair surface (not just the dominant pair --
retro full-surface lesson); live Brier + CLV vs the live close.
TIER: HYPOTHESIS; highest ceiling, most build cost.

## The bar for any real money (binding)
No stat goes to real $ without: leak-free WF + BSS>0 vs devigged reference on >=2 independent
matchdays + seed/N stability + FORWARD positive CLV (or DFS-movement proxy for pick'em). Until
then everything is paper-only / calibrated decision-support. A null at any phase is a SUCCESS that
reallocates effort. Team markets remain a standing $ REJECT (CUT 1) regardless of calibration.
