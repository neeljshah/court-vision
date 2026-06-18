# MLB EDGE MAP -- beatable vs efficient, market by market
_Part of the edge-intelligence corpus. Grounds in docs/research/project-deep-dive/05-mlb-prop-engine.md
+ 06-eval-proving-spine.md, the _framework/ files, and the real MLB code/data. Markets are mostly
efficient; the north star is CALIBRATION vs the devigged close, not a $-edge. Every claim is tagged
HYPOTHESIS / CALIBRATION-PROVEN / CLV-PROVEN. ASCII only._

## TL;DR ground truth (read first)
- The MLB **team** model (`domains/mlb/predictor.py` -> MOV-Elo + NegBinom run surface) is real,
  leak-free, coherent, and **matches/trails the close** -- the genuine asset, but EFFICIENT as a
  $-source (cut-list CUT 1).
- The MLB **player-prop** engine (`domains/mlb/prop_engine_mlb.py`) is correct machinery on a
  **near-empty corpus**: `data/domains/mlb/prop_calibration.json` is **n=0, all metrics null**
  (re-verified 2026-06-18). There is NO MLB prop calibration number yet -- positive or negative.
- The single unlock is the **player gamelog backfill**: `player_gamelogs.parquet` is **6,558 rows,
  2026-06-01..06-17 (17 days), 220 games, 920 players, median 6 games/player** (verified). A full
  season+ via `ingest_player_stats.ingest_range` (keyless statsapi) is the prerequisite for ANY prop
  edge claim. MLB is the MOST favorable sport here for honest calibration once that lands (162-game
  season -> per-player/per-team rates converge, season priors are informative, real ECE power).
- The validated **starting-pitcher (SP) lever** (`asof_sp_form.py` + `sp_elo_offset.py`) is measured
  leak-free but **NOT wired into `MLBPredictor`** -- the biggest single-game MLB variable (who is
  pitching) is absent from the delivered win-prob. Wiring it is the top team-side action.

## Beatable-pocket map (per _framework/edge-theory.md taxonomy P1..P6)

| Market / surface | Verdict | Tier | Evidence / why |
|---|---|---|---|
| **Soft/DFS player props -- per-opportunity stats** (Pitcher Ks, Hits, Walks, Walks Allowed, Outs) | **PUSH (P1)** | HYPOTHESIS | Per-PA/per-BF Bernoulli-sum counts; ~Poisson shape is sound (`player_rates_mlb.py:38-58`); soft/lazy DFS lines. But ZERO calibration yet (n=0). Beatable IF backfill -> BSS>0. |
| **DFS player props -- multi-outcome** (Total Bases, RBIs, Runs, Hits+Runs+RBIs) | **CUT-as-edge / model-view only** | HYPOTHESIS (negative) | cut-list CUT 4. Weighted sum / context-driven; Poisson on the sum mis-specifies variance+tail (`prop_engine_mlb.py:17` docstring admits it). WC analog measured negative (Cards -0.11, Assists -0.07). Need a compound model before betting. |
| **DFS HR / Stolen Bases** | **CUT-as-edge** | HYPOTHESIS (negative) | Very low rate, lumpy; small-N rate estimates dominate error. Display-only. |
| **Live / in-game team repricing** | **PUSH (P2)** | CALIBRATION-PROVEN (NULL recal) | `repricer.py` + `predict_live`: in-game recal is a clean validated NULL (held-out ECE 0.0085, slope 0.98; identity beats a fitted Platt). The lag-vs-book edge is the decisive lever but lives in execution, not the static number. |
| **Pregame mainlines** (ML / run line / total) | **CUT (P-none)** | CALIBRATION-PROVEN (matches close) | cut-list CUT 1. Full-season WF well-calibrated, CLV~0; books see the same statsapi data, lineup, SP, weather. Keep as calibrated decision-support + CLV yardstick. |
| **First-5-innings (F5) markets** | EFFICIENT (keep as support) | HYPOTHESIS | `markets.F5_FRACTION=0.521` (empirical, in-sample on 27,983 games, `markets.py:46`) -- flagged in-sample; OOS deferred to `proof_mlb/curve_oos.py`. SP lever matters most here (full game dominated by SP). |
| **Correlated same-game props / SGP** (HR+TB, H+R+RBI components) | PUSH-LATER (P5) | HYPOTHESIS | No joint model exists -- each stat priced independently (`prop_engine_mlb` limitation #7). Books misprice correlation; we cannot price it yet either. Build after the marginal calibration lands. |
| **Prediction-market vs book divergence** (Kalshi MLB game lines) | HYPOTHESIS (P4) | HYPOTHESIS | Not yet wired for MLB; a cross-corpus divergence flag, model-free. Low effort, untested. |
| **Stale/soft-book line-shopping** | PUSH (P3) | HYPOTHESIS | Execution edge, model-free; best-price capture. Durable per cut-list KEEP. |

## Where to PUSH (concentrate effort)
1. **Backfill the gamelog corpus to 1-2 full seasons** (keyless `ingest_range`). Single highest-leverage
   step -- unblocks every prop calibration claim. Without it the prop engine is at ~0% of ceiling.
2. **Per-opportunity props** (Ks/Hits/Walks/Outs) -- the soundest shapes; measure BSS first, push the winners.
3. **Wire the SP lever into the predictor** -- the validated `sp_elo_offset` (`p = sigmoid(elo_logit +
   w*z_sp)`, w fitted leak-free via bounded scalar min, `sp_elo_offset.py:133`) is the biggest unmodeled
   game-level signal; re-score vs close to confirm no regression.
4. **In-game lag** as an execution edge (the static recal is a NULL, but books lag realized run state).

## Where to CUT (stop hunting $)
- **Pregame mainlines** -- match the close, keep as support only (CUT 1).
- **Multi-outcome props** (TB/RBIs/Runs/H+R+RBI) as bet drivers until a compound model is built+validated (CUT 4).
- **Momentum/streak** signals as bet drivers (CUT 3, cross-sport).
- **Arbitrage** as a profit center (CUT 6); keep detection only.

## Honesty flags
- No MLB prop has cleared (or failed) calibration -- the corpus is too thin to score (n=0). Everything
  prop-side is HYPOTHESIS until the backfill + a real `props_eval_mlb` run.
- The team model's MATCHES_CLOSE is the honest, defensible win; do not chase a mainline $-edge.
- F5_FRACTION and the per-inning curve are in-sample; do not over-trust F5 markets until OOS-validated.
