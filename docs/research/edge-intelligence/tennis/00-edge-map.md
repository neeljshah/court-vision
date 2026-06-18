# TENNIS -- EDGE MAP (beatable vs efficient, per market)
_Part of the edge-intelligence corpus. Grounded in domains/tennis/ + scripts/platformkit/proof_tennis/
+ the real data/domains/tennis/ parquets, run 2026-06-18. Cites _framework/cut-list-no-edge.md.
ASCII. No fabricated $-edge; every claim carries a tier (HYPOTHESIS / CALIBRATION-PROVEN / CLV-PROVEN)._

## TL;DR (where to push, where to cut)
Tennis pregame is among the SHARPEST markets we model: ATP match-win Elo TRAILS the devigged
Pinnacle close by Brier +0.0149 on n=7374 held-out matches (`beat_the_close_ml.run()`, 2026-06-18:
Elo 0.2177 vs Pinnacle 0.2028, corr 0.871). That is the cleanest efficiency proof in the sport ->
CUT pregame match-win as an edge source (keep as calibrated decision-support + a CLV yardstick).
The beatable pockets are NOT pregame match-win. They are, ranked:
1. LINE-SHOPPING the moneyline across many books (EXECUTION edge, model-free). MEASURED: the `max`
   book carries a 0.33% median overround vs Pinnacle 2.52%, and `max` winner odds beat Pinnacle on
   72.2% of matches by a median +1.59%. (data/domains/tennis/odds.parquet, n~25.7k.) P3 pocket.
2. LIVE / IN-GAME LAG (the decisive calibration lever; tennis swings huge after each set). MEASURED
   sharpness: after set 1 the combined forecaster Brier is 0.151 vs pregame 0.219 (`ingame_accuracy`,
   n=8608). P2 pocket -- calibration-proven SHARPNESS, $-edge gated.
3. SOFT PROPS on games / aces / sets IF scrapeable -- HYPOTHESIS only; we do NOT yet scrape any
   tennis prop line (odds.parquet is match-winner two-way only). P1 pocket, blocked on data.
4. WTA (lower attention than ATP) -- HYPOTHESIS that WTA closes are softer; UNPROVEN and currently
   data-limited (WTA recal HONEST FAIL, ECE 0.055, surface blend optimal at 0.0).

## The market-by-market map
Legend: VERDICT = BEATABLE-pocket (push) / EFFICIENT (cut) / GATED (calib only) / BLOCKED (need data).
TIER = the evidence that earns the claim.

| Market | Verdict | Tier | Evidence / why |
|---|---|---|---|
| ATP match-win (moneyline), pregame | EFFICIENT -> CUT | CALIBRATION (trails) | Elo Brier 0.2177 vs Pinnacle 0.2028, gap +0.0149, n=7374; corr 0.871. Pinnacle integrates injury/news/form we cannot see. cut-list CUT-1 analog. |
| WTA match-win, pregame | EFFICIENT/UNCERTAIN -> CUT for now | HYPOTHESIS | `wta_recal`: best surface blend 0.0, recal ECE 0.0546 HONEST FAIL (data-limited). Lower attention => possibly softer closes, but UNPROVEN; no WTA odds parquet to test vs a close. |
| Moneyline line-shopping (max-of-N books) | BEATABLE (execution) -> PUSH | MEASURED (price fact) | `max` overround 0.33% vs Pinnacle 2.52%; max>Pinnacle 72.2%, median +1.59%. Model-free best-price edge. NOT a predictive edge; thin/limit-bound (cut-list CUT-6: shop, don't arb). |
| In-game match-win, after set 1 | GATED (sharpness real) -> PUSH | CALIBRATION-PROVEN | Brier 0.219 pregame -> 0.151 combined (n=8608); ECE 0.043 -> 0.006 (held-out leak-free recal). A live book also sees the score => calibration, NOT $. |
| In-game match-win, after set 2 @ 1-1 | GATED (marginal) | CALIBRATION (thin) | Brier pregame 0.254 -> combined 0.245 (n=2566): small lift; 1-1 is near coin-flip, little to gain. |
| Total games O/U (match) | BLOCKED -> need lines | HYPOTHESIS | We PRICE it coherently (`markets.price_all`, empirical+normal tail) but scrape NO games lines. Soft-book games lines are a candidate P1 pocket; UNTESTED vs any close. |
| Total sets O/U 2.5 (bo3) | BLOCKED -> need lines | HYPOTHESIS | Priced as 1-P(straight sets); straight_sets base rate 0.594 (postmortem.parquet). No scraped line. |
| Set handicap +/-1.5, set betting / correct set score | BLOCKED -> need lines | HYPOTHESIS | Priced coherently off the sim matrix (markets.py). No scraped line; books price these lazily on lower-tier events (candidate). |
| Aces O/U (player) | BLOCKED -> need lines + model | HYPOTHESIS | match_stats.parquet HAS aces (p1_ace mean 4.61) + svpt + 1stIn -> a per-player ace-rate model is buildable. No ace line scraped, no ace model wired. The single most promising soft prop. |
| Double faults / 1st-serve-% / break-points props | BLOCKED | HYPOTHESIS | Ingredients in match_stats (p1_df, p1_1stIn, bpFaced/Saved). No lines, no model. |
| Tie-break Y/N, within-set games, exact game score | NOT PRICEABLE (honest gap) | n/a | `markets.POINT_MODEL_GAPS`: engine resolves 6-6 as a 50/50 coin and stores only per-match game totals -> needs a per-point serve model we do not have. Do NOT fake these. |
| In-game games/points (live) | NOT BUILT | n/a | Tennis live engine is SET-level only (repricer.py race-to-N); no game/point repricer (deep-dive 11 sec 5.8). |

## Where to PUSH (concentrate effort)
- P2 IN-GAME set-conditional calibration: already CALIBRATION-PROVEN sharper after set 1; extend to
  bo5 (`ingame_bo5.py` exists) and surface it on the board. This is the strongest real result.
- P1 SOFT PROPS, gated on a scraper: ACES first (data + model both feasible), then games/sets O/U.
  These are the only place a genuine pricing edge could live, but ENTIRELY blocked on line data.
- P3 LINE-SHOPPING: surface the multi-book best price + overround on the moneyline board (the `max`
  column already exists in odds.parquet). Execution edge, model-free, honest.

## Where to CUT (stop hunting $)
- ATP pregame match-win as a $-edge: CUT. Keep the Elo as calibrated decision-support and a CLV
  yardstick only. Do not add features chasing the 0.0149 Brier gap to Pinnacle (it is the market's
  freshness/news advantage, which we structurally cannot see -- the same lesson as cut-list CUT-1/2).
- Surface-blend tuning beyond SURFACE_BLEND=0.3 (ATP) / 0.0 (WTA): the WTA proof already shows 0.0 is
  optimal there; do not over-fit per-surface weights on thin data (cut-list CUT-5).
- Momentum / "hot hand" set-streak bet drivers: do NOT build (cut-list CUT-3). Form is fine as a
  RATE input to the calibrated distribution; "ride the streak" is not an edge.
- Tie-break / within-set markets: do not price (no per-point model; honestly out of reach).

## Honesty footnotes
- ATP "BEHIND" is the HONEST and EXPECTED result (the proof's own docstring predicts BEHIND). It is a
  SUCCESS: it tells us to stop spending on pregame match-win.
- The in-game ECE 0.043->0.006 is from the SEPARATE chronological TRAIN/EVAL split in
  `ingame_calib.recalibrate_holdout` (fit on the train era, scored on held-out), NOT a build-time
  refit -- per predictor.py's own honesty note. It is a SHARPNESS claim, never a $ claim.
- No tennis CLV exists yet: data/domains/tennis/paper_book/ and the prop ledgers are essentially
  empty (deep-dive 06: 0 settled rows carry a real CLV system-wide). Every $-edge claim is therefore
  at most HYPOTHESIS until forward CLV accrues.
