# TENNIS -- GET-TO-EDGE PLAN (the prioritized path to a PROVEN edge)
_The concrete, ordered path from where we are (deep history, efficient pregame, calibration-proven
in-game sharpness, ZERO prop lines) to a PROVEN edge. Each step: approach + how it is VALIDATED
(calibration BSS and/or CLV). Grounded in the real proofs. ASCII. No fabricated $-edge._

## Where we are (honest baseline, 2026-06-18)
- Pregame ATP match-win: EFFICIENT. Elo Brier 0.2177 vs Pinnacle 0.2028 (n=7374, BEHIND +0.0149).
  -> a $-edge here is CUT; keep only as calibrated decision-support + CLV yardstick.
- In-game after set 1: CALIBRATION-PROVEN sharper (Brier 0.219 -> 0.151; ECE 0.043 -> 0.006).
- Line-shopping: MEASURED price fact (max book 0.33% overround, beats Pinnacle 72.2% / +1.59%).
- Soft props (aces/games): the only place a PREDICTIVE edge could live -- but BLOCKED (no prop lines
  scraped; no ace model). WTA: model is data-limited (HONEST FAIL).
The path is therefore: stand up the missing PLUMBING (live odds + prop scraper + CLV ledger), then
build the one NEW model with real upside (aces), and prove each thing leak-free then forward.

## QUICK WINS (days) -- plumbing + documenting what's already real

### Step 1 -- Pin the in-game calibration scoreboard (document the proven win)
APPROACH: run `proof_tennis/ingame_accuracy.py` + `ingame_bo5.py`; record the after-set-1/2 (bo3) and
bo5 Brier(conditional) vs Brier(pregame) + ECE table. No new code.
VALIDATE: leak-free Brier + ECE, held-out year>2022 (already enforced). Verdict is CALIBRATION, not $.
WHY FIRST: it converts the strongest existing result into a documented, citable claim at zero risk.

### Step 2 -- Stand up the tennis CLV channel (keyless moneyline + history capture)
APPROACH: add a tennis league map to `odds_provider/espn.py` (pickcenter -> moneyline), and run
`prop_line_history` / the pm_trading cadence over a live tournament so closing lines accrue.
VALIDATE: forward CLV on the moneyline (compute_clv sign: positive = better number than the devigged
close). This is the ONLY way any tennis $-claim ever leaves HYPOTHESIS (deep-dive 06: 0 real CLV
exists system-wide today).
WHY: every later edge claim is gated on CLV, and the channel currently does not exist.

### Step 3 -- Expose the line-shopping surface (execution edge, model-free)
APPROACH: surface per-book overround + best price on the moneyline board (odds.parquet already has
psw/maxw/avgw; for live, aggregate ESPN + optional The Odds API tennis_atp via odds_shop.best_line).
VALIDATE: by construction -- taking the best price IS positive CLV vs the close. Keep size-honest;
arbs are rare/limit-bound (cut-list CUT-6). Tier: MEASURED execution edge.

## BIG BET 1 (weeks) -- the ACES soft-prop pocket (highest predictive upside)

### Step 4 -- Build the leak-free as-of ACE-RATE feature
APPROACH: new builder under domains/tennis/ (mirror asof_hold.py exactly: snapshot-before-update,
debut=NaN, no-future-leak assert). Emit per-player trailing ace-rate (aces/svpt) overall + per
surface from match_stats.parquet (p1_ace mean 4.61, p1_svpt, p1_1stIn available).
VALIDATE: assert_no_future_leak (debut rows NaN) + chronological-only construction.

### Step 5 -- Build + gate the NegBinom ace prop model (calibration)
APPROACH: model match aces ~ NegBinom(mean = asof_ace_rate * expected_serve_points, dispersion phi
fit leak-free per surface). Price P(over line). Use NB (not Poisson) + FLAG |EV|>0.5 to avoid the
too-tight-tail trap (the discipline that demoted soccer count props, deep-dive 03/05).
VALIDATE (CALIBRATION-PROVEN bar): leak-free walk-forward BSS of P(over) vs realized aces on
match_stats, >=100 INDEPENDENT matches, >=2 era folds agree, cluster-robust DM. BSS>0 = sharper than
a base-rate ace prior. Expect: aces are serve-volume-driven and may be near-deterministic given
points (the Saves-prop analog, deep-dive 06) -> read "proven" as suggestive until N is large.

### Step 6 -- Add the keyless tennis PROP scraper + join to the ace model
APPROACH: extend `prop_prizepicks`/`prop_underdog` with tennis league resolution; lift
`prop_edge._SUPPORTED` to include tennis; join scraped ace (then games/sets) lines to the model.
VALIDATE (toward CLV-PROVEN): for Underdog two-sided lines, devig + EV + forward CLV vs the closing
prop line. For PrizePicks pick'em (no two-way close), prove via P(over) calibration vs realized +
realized ROI at the fixed payout + line MOVEMENT. Gate hard; quarantine any CUT-category rows.

## BIG BET 2 (weeks-months) -- widen the surface, only where proof warrants

### Step 7 -- Low-attention games/sets totals (P6) + WTA testability
APPROACH: tag candidates by tourney_level (ATP-250/Challenger/WTA-lower); price games/sets O/U
(markets.price_all) and join to scraped lines from Step 6. Separately, build wta_odds ingest to run
the WTA beat-the-close test (POCKET T5).
VALIDATE: per-tier leak-free calibration of games/sets price vs realized (postmortem.parquet has
n_breaks/straight_sets) THEN vs the scraped line + forward CLV. WTA: WTA Elo Brier vs devigged WTA
close. Expect MATCH on top tiers; any lift must clear the full proof bar.

### Step 8 (conditional) -- per-point serve model
APPROACH: only if Step 6 shows within-set/tie-break lines are scrapeable AND soft, build a deuce/ad
point chain to unlock POINT_MODEL_GAPS (tie-break Y/N, within-set games).
VALIDATE: calibration of the new markets vs realized, then forward CLV. Do not build speculatively.

## The success ladder (what "proven edge" means here, in order)
1. CALIBRATION-PROVEN sharpness: in-game (DONE for after-set-1) + ace prop P(over) BSS>0 leak-free.
2. EXECUTION edge: line-shopping best price (immediate, model-free, CLV-positive by construction).
3. CLV-PROVEN: forward positive CLV on a tennis prop (Underdog two-way) or moneyline best-price, at a
   meaningful sample, cluster-robust CI>0 -- the only claim that ever earns "edge".

## What would make us STOP (honest kill-criteria)
- Ace model BSS <= 0 leak-free across folds -> demote to model-view, stop (cut-list CUT-4 analog).
- Scraped prop lines turn out efficient (model MATCHES the close) -> CUT props, keep the in-game
  calibration product only.
- WTA close not measurably softer than ATP -> CUT WTA edge-hunting.
A null at any gate is a SUCCESS: it reallocates effort. The defensible north star for tennis remains
"well-calibrated, proven not-worse-than the close" pregame + a real in-game sharpness win + a thin
execution (best-price) edge -- with ACES the one genuine shot at a predictive prop edge, gated.
