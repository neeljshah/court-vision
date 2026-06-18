# SOCCER-CLUB -- edge map (beatable vs efficient, per market)
_Part of the edge-intelligence corpus. Sport = soccer_club (top-5 European leagues + EFL
Championship). Grounded in domains/soccer/, data/domains/soccer/, and the deep-dive
04-soccer-wc-prop-engine.md. Tiers per _framework/edge-theory.md. ASCII only._

## TL;DR thesis (the one sentence)
Club soccer has DEEP team history (25,834 matches, 6 divisions, 2015-2025, with open+close
O/U odds on 16,322 of them) -> the TEAM/scoreline surface is well-calibratable but EFFICIENT
(we match the close, no $ edge, CUT per cut-list CUT 1). The genuine opportunity is the
PLAYER-PROP pocket: the exact WC prop engine (per-90 rate x E[min] -> NB count -> p_over)
re-pointed at the SAME keyless ESPN per-player box that exists for eng.1/esp.1/ita.1/ger.1/
fra.1, where DEEP multi-season per-player history (not the WC's 1-match-per-player wall)
can finally make the rate calibration real. That is P1 (soft/DFS props) and it is where club
effort should go.

## Data reality that sets every tier (cite)
- TEAM corpus: data/domains/soccer/matches.parquet = 25,834 rows, div in {E0,E1,SP1,I1,F1,D1},
  season 2015..2025, over2.5 base rate 0.5154. match_stats.parquet = 25,834 rows with shots,
  SOT, corners, fouls, yellow/red, referee. odds.parquet = 16,322 rows with ou_open_* AND
  ou_close_* + Pinnacle/B365/Max -> a real closing line for CLV on totals.
- TEAM-side calibration is plumbed: scoreline_engine.scoreline_matrix (Dixon-Coles bivariate
  Poisson) + markets.full_surface price the ENTIRE catalog off one matrix, COHERENTLY. The
  module header (markets.py:24-28, scoreline_engine.py:5-8) states plainly: "does NOT add any
  signal or edge over the base Poisson surface ... Pregame soccer markets are efficient;
  calibration only, no $ edge claimed." rho=0 engine == closed-form baseline to <1e-6.
- PLAYER per-player CLUB box: keyless ESPN summary endpoint already ingests the top-5 leagues
  (ingest_espn_box.py header: eng.1, esp.1, ita.1, ger.1, fra.1). espn_matchstats.parquet has
  185 club team-rows so far; the WC per-player table espn_player_stats.parquet (1,241 rows,
  23 cols incl. totalShots/shotsOnTarget/saves/foulsCommitted/goalAssists) PROVES the
  per-player schema. The same ingest pointed at club summaries yields per-player CLUB box ->
  deep history, the WC's missing ingredient.
- The current MEASURED prop cache (prop_calibration.json) is WC-only and thin (n=662/stat
  pooled, NOT independent): Saves bss +0.3365 (proven), everything else marginal/weak.

## Market-by-market map

### TEAM / scoreline markets -- EFFICIENT (CUT to calibrated decision-support)
| Market | Verdict | Tier | Evidence |
|---|---|---|---|
| 1X2 (h/d/a moneyline) | EFFICIENT - CUT | CALIBRATION-only | markets.one_x_two; sharp consensus integrates team strength; cut-list CUT 1 |
| O/U total goals (2.5 etc) | EFFICIENT - CUT | CALIBRATION-only | engine_over25 == baseline at rho=0; odds.parquet has the close -> use as CLV YARDSTICK, not edge |
| BTTS yes/no | EFFICIENT - CUT | CALIBRATION-only | markets.btts read-off of P; no new signal |
| Asian / European handicap | EFFICIENT - CUT | CALIBRATION-only | markets.asian_handicap; algebraic read-off |
| Double chance / DNB | EFFICIENT - CUT | CALIBRATION-only | markets.double_chance/draw_no_bet; sum of 1X2 legs |
| Correct score / winning margin | EFFICIENT - CUT | CALIBRATION-only | markets.correct_scores; thin tails, lottery market |
| Team totals / clean sheet / odd-even | EFFICIENT - CUT | CALIBRATION-only | markets.team_totals/clean_sheet/odd_even |

ACTION: keep the full_surface as a COHERENT, well-calibrated decision-support board and as a
CLV yardstick vs odds.parquet closes. Do NOT hunt a mainline $ edge here (cut-list CUT 1: the
season WF is well-calibrated but does NOT beat the close, CLV ~ 0). The deep history's value
is CALIBRATION SHARPNESS, not edge.

### PLAYER props -- the BEATABLE pocket (P1), where club effort goes
| Prop | Verdict | Tier today | Path |
|---|---|---|---|
| Saves (GK) | PUSH - most promising | CALIBRATION-PROVEN (WC: bss +0.3365, n=662) | re-prove on club data; near-deterministic in shots-faced |
| Shots (total) | PUSH - high volume | HYPOTHESIS (WC marginal +0.008) | deep club rate history should lift this most |
| Shots on Target | PENDING | HYPOTHESIS (WC +0.005) | joint with Shots; needs club data |
| Fouls / Fouls Drawn | PENDING | HYPOTHESIS (WC +0.034 / +0.026 marginal) | club fouls are stable per-player; promising |
| Tackles / Passes / Interceptions | HYPOTHESIS - NOT YET INGESTED | unmeasured | ESPN club summary has 28 fields incl passes/crosses/longballs -> richer than WC ingest uses |
| Goals / Assists / Goal+Assist | CUT (rare-event) | WEAK (WC bss -0.025 / -0.074 / -0.007) | cut-list CUT 4: near-irreducible single-match noise; model-view only |
| Cards / Offsides | CUT (rare-event) | WEAK (WC bss -0.108 / -0.016) | cut-list CUT 4: demote, do not paper-bet |

### IN-GAME (live) -- P2, the decisive combinable lever (HYPOTHESIS, not built for club)
Live 1X2/total repricing off realized score+clock lags the book; the scoreline_matrix can be
re-fed with elapsed-time-scaled lambdas. Currently NO club in-game path exists. Highest-ceiling
unbuilt lever (see _live/ cross-sport intelligence).

## Where to PUSH vs CUT (the allocation)
PUSH: (1) ingest_espn_box -> per-player CLUB box across 5 leagues, multi-season; (2) re-point
the prop engine at club rates so Saves/Shots/Fouls get DEEP (not 1-match) history; (3) capture
CLOSING prop lines for CLV (the deep-dive's #1 gap -- prop_paper has no CLV today); (4) club
in-game repricing as the eventual decisive lever.
CUT: all team/scoreline $ hunting (CUT 1); rare-event props Goals/Assists/Cards/Offsides as
bet drivers (CUT 4); any recalibration that only helps in-sample (CUT 5; isotonic already
DEFERRED). Momentum/form-as-edge (CUT 3) -- form is a RATE input only.

## Honest ceiling
A well-calibrated club prop board on 3-5 high-volume near-deterministic stats (Saves, Shots,
Fouls/Fouls-Drawn), backed by genuinely deep per-player club history (the WC's missing piece),
proven OOS by Brier/BSS and forward CLV. Team markets stay calibrated decision-support. No
mainline $ edge -- club soccer team markets are as efficient as any major market.
