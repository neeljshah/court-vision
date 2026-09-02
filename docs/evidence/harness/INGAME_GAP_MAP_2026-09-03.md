# In-game signal gap map (Fable, 2026-09-03) -- every way to close the gap to the Renaissance bar

Standing: e4 blend is the incumbent (leak-free OOF Brier 0.206786 on MLB ticks vs the in-play line);
clamp NULL (K=16, instrument repaired S72), e2 BEHIND (K=15), NBA halftime BEHIND (K=17), stacker
BEHIND (K=14). The factory has no in-game tier (S82 running). Player grain unmeasured (S80 running).
Calibration language only. Every lever below is a register row with a SCREEN-side result first
(no charge) and a prereg DRAFT only if the screen side clears +0.004 Brier vs the incumbent.

| lever | what closes the gap | premise to verify first | screen-side bar |
|---|---|---|---|
| L1 features | in-game STATE features (base-out, outs, leverage, TTO, pitch count, bullpen as-of) screened in the factory | S82: in-game families refused as same-game columns | +0.004 vs e4 on ticks |
| L2 player grain | batter/pitcher/lineup identity at the tick + pregame player as-of | S80: share of ticks carrying player state | +0.004 vs e4 |
| L3 structural prior | Markov base-out / possession chain with as-of transition rates as a model probability at EVERY state, blended with the market | ingame_baseout_mlb.py, rest_of_game_sim.py exist -- are they scored on ticks vs the line? | +0.004 vs e4 |
| L4 corpus size | backfill historical in-play prices (Kalshi intragame venue history) for the whole 2026 season so screens have thousands of games not 13 folds | venue_history/kalshi_intragame.py: what is covered, what the API exposes, granularity | n_games x10 with a joined outcome + tick line |
| L5 tick quality | duplicate ticks, held (frozen) positions, stale lines inflate n_eff and fake CIs | council defect 'dup tick store'; ESS/ICC on the tick corpus | dedup + stale flag; n_eff reported honestly |
| L6 phase recalibration | isotonic/bucket recalibration of the blend per phase (inning x run-diff x outs), max-loser-WP bins (S43) | bucket_recalibration.py, ingame_blend_recal.py exist -- OOF per phase? | +0.004 on the worst-calibrated phase without hurting the rest |
| L7 freshness / lead time | score the model vs the market's NEXT tick after an event: does the model anticipate the update; lead-time distribution vs tick latency p50 15 s | freshness_premium.py, inplay_tick_latency.py exist | measured lead-time and a screen of 'model-at-t vs market-at-t+30s' |
| L8 cross-sport ticks | NBA / soccer / tennis in-play lines captured so the in-game tier runs on 4 sports | inplay_odds, ingame_shadow_history: which sports carry a tick line | a second sport with >= 200 games of ticks + outcome |
| L9 arm registry sweep | every registered gap_* arm (blend, leadoff, offset, regime, hedge_combiner) re-scored leak-free on the SAME screen partition, one table | arm_registry.py, arm_evaluation.py | one honest table; drop arms that never beat e4 |
| L10 event-reactive model | model updates on the event stream (GUMBO poll) not on the tick cadence; probability at event time | gumbo_mlb_poller.py, aci_online.py | latency-to-event p50 < market p50 |
| L11 multiplicity for in-game | in-game family in the FWER ledger with its own BH bar and K-source discipline | family_bars.py: is there an in-game family? | families frozen before the first in-game charge |
| L12 forward | paper week window 2 (S55) settles the first prospective in-game rows | accruing | not a worry per user; report only |

Order (user: in-game first, slowly): L1 L2 (running) -> L4 L5 (corpus + quality, they gate every CI) ->
L3 L6 (structure + calibration) -> L7 L10 (freshness) -> L9 L11 (housekeeping) -> L8 (breadth).

## New territory (user 2026-09-03: "better than any quant for sports") -- levers no sports shop ships

| lever | idea | why it is new | premise to verify | screen-side bar |
|---|---|---|---|---|
| L13 sensor fusion | treat the in-play line as a NOISY SENSOR of the true state and the event-driven model as another; a Kalman / Bayesian filter with learned per-phase observation noise and the market's measured latency gives a posterior that is neither the model nor the market | sports models blend a model with a market at one weight; nobody filters the market's tick SERIES with its latency as a noise model | tick series + model series per game on disk (ingame corpus); latency p50 15 s measured | +0.004 vs e4 on ticks, and coverage of the posterior interval within 2 pts of nominal |
| L14 market-consistent sim | fit the rest-of-game score distribution JOINTLY to every in-play market on the same game (moneyline, total, run line, on Kalshi and Polymarket); a single consistent distribution is sharper than any one market | cross-market consistency is used for arbitrage, never as a calibration prior | ingame_book_depth_kalshi/poly: which secondary in-play markets were captured, n games | +0.004 vs the moneyline alone on ticks; totals scored too |
| L15 microstructure state | order-book depth imbalance, queue at the touch, last-trade direction, spread as features for the NEXT-tick move and for the outcome | sports models ignore the book; equities microstructure never met a base-out state | ingame_book_depth_* retention: rows, games, fields | next-tick sign accuracy > 50 pct with clustered CI; outcome Brier +0.004 |
| L16 overreaction residual | after a scoring event, does the market overshoot? score the market's post-event change against the eventual outcome; a mean-reversion arm on the market's own reaction | inverts the usual 'chase the event' framing; tests the market not the game | GUMBO events with timestamps joined to ticks within +/- 120 s | measured overshoot with CI; arm +0.004 if it exists, honest NULL if not |
| L17 adaptive conformal | ACI on ticks so per-tick intervals keep nominal coverage under regime drift; the metric is COVERAGE, which a Brier never shows | aci_online.py exists; never reported as a coverage series per phase | aci_online.py scored on ticks? | coverage 90 +/- 2 per phase on the screen side |
| L18 hierarchical pooling | one sport-blind in-game blend with partial pooling across sports and phases (Bayesian hierarchical logistic); low-n phases borrow strength | matches the kernel/ direction; nobody pools in-game across sports | needs a second sport with ticks (L8) | +0.004 on the low-n phases without hurting MLB |
| L19 momentum-as-null | preregister the hot-hand / momentum family as a PUBLIC null test; the market may overweight it | an honest public null is a moat: it says what we refuse to trade | momentum features in the grammar | verdict recorded either way |
| L20 rest-of-game distribution | predict the full run/point distribution per tick and score EVERY in-play market (win, total, spread) with CRPS, not just win Brier | triples the surface where calibration is verified; totals in-game are thinner | rest_of_game_sim.py; totals ticks captured? | CRPS vs market-implied distribution on the screen side |

Order after L1-L2: L4 L5 (corpus + quality) -> L13 L16 (fusion, overreaction: data on disk) -> L14 L15 L20 (need the secondary-market and book-depth captures) -> L17 L19 -> L18 (needs L8).
