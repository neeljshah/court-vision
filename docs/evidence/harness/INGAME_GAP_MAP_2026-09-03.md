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
