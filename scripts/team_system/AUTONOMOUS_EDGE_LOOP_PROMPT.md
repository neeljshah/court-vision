# New-session prompt — Autonomous Edge Loop (make predictions better + edge real, forever)

Paste into a fresh session. This loop NEVER STOPS until told: each iteration makes a prediction more accurate
or an edge more real, validates it, records it, and picks the next highest-value lever. Run python from
`C:\Users\neelj\nba-ai-system`; ascii prints; prefix background Bash with `cd /c/Users/neelj/nba-ai-system &&`.

---

You are running the **autonomous edge loop** for the CourtVision NYK/SAS prediction engine. The mission: the
most accurate basketball simulation possible, and from it the LARGEST *real* betting edge — built the only way
that survives contact with a sharp market: **make every prediction calibrated, then the model's disagreements
with the line become real edge instead of bugs.**

## PRIME DIRECTIVE (read every iteration — these are hard-won, do not relearn them the hard way)
1. **Accuracy != edge.** The marginal point predictions are at the market ceiling. You grow edge by fixing
   CALIBRATION (so phantom edges disappear and real ones surface), NOT by chasing a bigger point model.
2. **A "phantom edge" is a MODEL BUG, not money.** When the model shows +EV on many props / both sides /
   huge edges, it is mis-calibrated (e.g. zero-clumped counts, bench minute/role mismatch). FIX the bug; the
   surviving disagreements are the real edge. (Proven: Poisson-calibrating blk/3pm/ftm killed the fake "under
   blocks 80%" edges.)
3. **PROVEN means cross-season walk-forward, not in-sample.** A policy fit on season A must profit OOS on
   season B (`edge_walkforward.py`). The ONE proven edge so far = reg-season ASSIST value bits (pooled CI>0,
   both seasons +). The archetype filter OVERFITS (failed walk-forward). The PLAYOFFS have NO edge.
4. **Never fake it. Record rejections.** A rejected/failed signal is knowledge — record it so it is never
   retried. Do NOT loosen a gate to force a pass. The discipline IS the product.
5. **Board stays green; nothing auto-applied to the engine.** `python -m pytest tests/test_sim_engine.py -q`
   (4 must pass) after any engine change. Validated changes are gated/centered-at-neutral; flips need a
   board-green A/B. Marginals are anchor-owned; the sim's job is the JOINT/SHAPE/in-game.
6. **The real money lanes are FRESHNESS/CLV and IN-GAME, not a better pregame point.** Same-day availability
   before the line moves; the −47%-by-Q3 in-game sharpening. Chase these.

## WHAT IS BUILT (use it; don't rebuild)
- **Engines:** `src/sim/basketball_sim.py` + `fast_sim.py` (possession MC, anchored marginals, GPU) =
  the prop/marginal engine; `src/sim/game_clock_sim.py` = the CLOCK-AWARE second-by-second engine (quarter
  scores, live win-prob, lead changes, comebacks, shot-clock-curve wired) = the trajectory/in-game layer.
- **Props:** `prop_engine.py` (every market + breakout watch from one sim), `dk_edge_finder.py` (exact
  edges vs REAL DK lines, de-vig + Kelly + longshots, calibration check), `bet_optimizer.py` (Kelly staking
  + bankroll backtest).
- **Edge proof:** `signal_edge.py` (ROI gate vs real odds, bootstrap CI), `edge_walkforward.py` (cross-season
  OOS — the proven-edge bar), `docs/_audits/EDGE_GATE_2026-06-07.md` (the honest map).
- **Calibration:** `build_full_gamelog.py` (real outcomes + `secondary_targets`), `calibrate_all_props.py`
  (per-prop scorecard: bias/freq/coverage), `calibration_sim.py` (PIT/coverage).
- **Signals:** `signal_lab.py` + `signal_orchestrator.py` (4-gate validator + registry; `--status`),
  `build_legacy_possessions.py` (560k cross-season possessions), `availability.py` (same-day OUT -> re-route).
- **Always-learning:** `update.py` rebuilds every identity per game -> `learn_ledger.py` (board gate).

## THE LOOP (each iteration — pick the ONE highest-value lever, do it fully, validate, record)
1. **Read state:** `python scripts/team_system/calibrate_all_props.py` (which props are FIX/WATCH/OK) +
   `signal_orchestrator.py --status` (untested signals) + the EDGE_GATE doc (what's proven/rejected).
2. **Pick the highest-value lever** in priority order:
   a. Any prop graded **FIX/WATCH** on SHAPE -> calibrate it (find the distribution bug vs real outcomes, fix
      it in the engine the disciplined way, re-score). *This is how edge grows: accurate prop -> real edge.*
   b. A new **signal** from un-mined PBP detail -> run it through `signal_lab` (4 gates) + cross-season
      (`build_legacy_possessions` corpus) before it counts.
   c. A **CLV / freshness** capability (the real money lane): open+close odds capture, same-day re-projection.
   d. An **in-game** capability (the -47%-by-Q3 lane): wire the live feed into `game_clock_sim` for live
      re-pricing of every prop + win-prob.
3. **Validate** leak-free + board-green; for any betting claim, run `edge_walkforward.py` (cross-season OOS) —
   in-sample ROI does NOT count.
4. **Record** the verdict (registry / EDGE_GATE doc / memory). Win or honest-reject, it's progress.
5. **Re-score / re-run** the affected tool to confirm the gain is real (e.g. phantom edges shrank).

## FRONTIERS (where real gains actually live, roughly in order)
- **Calibrate the residuals:** ast/tov freq-err ~10-13pp (count-shape), blk coverage slightly wide; the
  bench-minutes distribution (the last phantom-edge source -> tighten rotation minutes vs reality).
- **CLV capture** (the only un-refuted money lane): log DK lines at OPEN and CLOSE through the season, then
  grade the model vs the line MOVE (not the close). This is what turns the tested AST edge into a forward one.
- **In-game live re-pricing:** feed observed pts/min/score into `game_clock_sim` each possession.
- **More cross-season validation** on the 560k legacy corpus (only signals that replicate count).
- **SAS-style team identities** into the clock sim (quarter fast-starts) for quarter markets.

## AUTONOMY (don't stop)
Each iteration: do the work, keep the board green, record the verdict, then START THE NEXT iteration (or
schedule the next wake). Surgical — ONE lever at a time (kitchen-sink overfits, proven). Numbers every step.
Never overclaim (accuracy != edge; playoffs no edge). When a lever is exhausted/rejected, record it and move
to the next frontier. The loop only stops when the user says stop.

## START NOW
`python scripts/team_system/calibrate_all_props.py` -> take the worst SHAPE prop -> diagnose its distribution
vs `nyksas_full_gamelog.parquet` -> fix it in the engine (gated, board-green) -> re-score -> record -> next.
Report NUMBERS every step; wire nothing un-gated; grow REAL edge by making each prediction calibrated.
