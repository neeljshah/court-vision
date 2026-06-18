# INEFFICIENCY -- Low-attention / niche market (P1 + P4 + P6; the lazy-pricing pocket)
_Per-pocket detection-recipe deep file. Cross-sport. The crack is LOW ATTENTION + a DIFFERENT
CROWD: soft/DFS apps, thin niche leagues, and prediction markets price lazily or differently
from the sharp consensus. Grounded in the keyless prop scrapers + PM providers (deep-dive 03)
and the WC/MLB prop engines (deep-dives 04, 05). ASCII only. No $-edge claims._

## MECHANISM (why the crack exists)
Three related framework cracks converge in "low-attention":
- LOW ATTENTION (P1/P6): soft books, DFS pick'em apps (PrizePicks/Underdog), and thin niche
  leagues (World Cup props, lower-tier soccer, non-marquee MLB) get little sharp money and price
  off a lazy internal model on a slow cadence. The line does not get sharpened by volume because
  the volume is recreational. This is THE primary pocket in the beatable-pocket thesis: per-
  player distributions we can model vs a line nobody is sharpening.
- STRUCTURAL (DFS pick'em): a FIXED-PAYOUT pick'em projection literally CANNOT move to kill a
  genuinely mispriced number -- there is no two-way market to converge. If our calibrated
  P(over) on a PROVEN stat diverges from the fixed projection, the misprice persists by design.
- DIFFERENT CROWD (P4): Kalshi/Polymarket (prediction markets) are a separate population from
  sportsbook bettors. The two crowds can disagree; a persistent gap between the PM-implied prob
  and the devigged sportsbook consensus is a candidate -- one crowd is wrong.

The reason this is beatable where mainlines are not: the efficiency assumption (sharp money
integrates all info) FAILS by construction in low-volume / fixed-payout / different-crowd venues.

## CONCRETE DETECTION RECIPE (exact data + query + threshold)
Sub-pocket A -- DFS / soft PROP misprice (the primary lever):
1. Pull pick'em + soft two-way props: `prop_prizepicks.py` (pick'em, prices None,
   payout_type="dfs_pickem"), `prop_underdog.py` (true two-way decimal when decimal_price
   present), `prop_fanduel.py` (built; verify it is posting props). Normalize stat names via
   `prop_base.canon_stat`.
2. Price OUR calibrated P(over) for that player+stat+line: soccer/WC via `prop_edge.build_prop_board`
   (joins scraped lines to the per-player count model, emits a calibration-TIERED board); MLB via
   its prop engine; NBA (when season returns) off the sim CDF.
3. RESTRICT TO PROVEN STATS ONLY. cut-list CUT-4 measured NEGATIVE skill on rare/teammate-
   dependent stats (WC Cards BSS -0.11, Assists -0.07, Goals -0.03, SoT ~0). Only flag candidates
   in the stats where we have leak-free positive skill (WC Saves; expected MLB Hits / Pitcher-Ks
   / Walks). Flagging a "mispriced" Card line is flagging our own model noise.
4. For pick'em: candidate when calibrated `P(over)` deviates from 0.5 by `>= TAU_PICKEM` on a
   PROVEN stat (start 0.55, i.e. a real >55% leg). For two-way soft props: `ev_vs_price(model_p,
   decimal_odds)` (odds_shop) > TAU_EV after devig.

Sub-pocket B -- PM vs sportsbook divergence (P4):
1. From the merged slate: `kalshi.py` / `polymarket.py` two-way team-winner probs vs the
   sportsbook devigged consensus (`odds_shop.devig_twoway` over ESPN-republished books).
2. Flag when `|p_PM - p_book_consensus| >= TAU_PM` (start 0.04). The take is the venue offering
   the longer price on the side the OTHER crowd favors.
3. Resolve cross-source identity with `team_resolver.canonical(sport, name)` (the matching
   backbone) so you are comparing the same event, not a mismatched fixture.

Sub-pocket C -- niche-league thin attention: same prop recipe (A) but in low-volume leagues
where the soft model is laziest. Detection is identical; the EXPECTATION of a gap is higher, the
DATA DEPTH (and thus model confidence) is lower -- so confidence/tier gating matters most here.

## PROOF METHOD (which leak-free check + which metric)
- DFS PICK'EM has NO two-way close -> CLV-vs-close is UNDEFINED (edge-theory note). Prove via:
  (a) P(over) CALIBRATION vs realized (leak-free WF Brier / BSS on the PROVEN stat), (b) realized
  ROI at the FIXED payout, (c) DFS-LINE MOVEMENT (did the projection drift toward our number by
  lock -- a soft analogue of CLV). All three, not ROI alone (small-N ROI is noise).
- SOFT TWO-WAY props: standard ladder -- leak-free WF P(over) calibration vs the devigged soft
  close (BSS>0) -> then forward CLV via prop_line_history.clv_vs_close.
- PM divergence: log the take, settle realized, and compute CLV against whichever side closed;
  require the gap to CONVERGE (one crowd moves toward the other by close) across >=2 windows --
  a persistent non-converging gap is two priced positions, not a misprice.
- OVERFIT GUARDS (proof-standards): isotonic recal on thin niche data OVERFITS (WC 24-match recal
  DEFERRED, cut-list CUT-5); too-tight count distributions invent fat tails -> absurd EVs (saw
  +131%); FLAG implausible |EV| and require NB-where-overdispersed + conformal width. Thin-data
  confidence: 1 player/match is model-view only unless a strong club/season PRIOR backs it.

## MAGNITUDE (honest)
This is the pocket with the HIGHEST realistic beatability in the thesis (P1, ranked first) --
BUT only on the narrow set of PROVEN stats. Where we have measured positive skill (WC Saves), the
calibration gap vs a lazy line is genuine; where we measured negative skill (Cards/Assists/Goals/
SoT), the apparent "edge" is our own miscalibration and is a TRAP. Net magnitude is therefore
stat-conditional and small after the cut: a handful of proven stats x a soft/fixed line that
does not sharpen. The fixed-payout structural piece is the most durable (it cannot converge), but
DFS execution caps (entry limits, account throttling) bound capacity hard.

## HONEST CAVEAT / FAILURE MODES
- THE CUT IS LOAD-BEARING. Most niche/DFS prop stats are in cut-list CUT-4 (negative measured
  skill). The single biggest failure mode is mistaking model noise on a leaky teammate-dependent
  stat for a market misprice. Stay on PROVEN stats; demote the rest to model-view-only.
- THIN-DATA OVERFIT. Niche leagues have little data -> recalibrators and flexible signals overfit
  in-sample (CUT-5). Gate every lever on leak-free OOS; re-fit only as data grows.
- TOO-TIGHT DISTRIBUTION. Under-dispersed count models on props manufacture fat tails and absurd
  EVs (+131% trap, proof-standards). Always flag implausible |EV| before trusting a flag.
- PM IS NOT A SECOND BOOK. A PM-vs-book gap can be a real informational disagreement, not a
  misprice; require convergence-by-close to confirm. PM liquidity is also thin -> tiny capacity.
- EXECUTION / CAPACITY. The lazy venues are exactly the ones that limit/ban winners fastest and
  cap entries; the edge does not scale even where real.
- IDENTITY-MATCH BUGS. Cross-source name/league resolution (team_resolver, PrizePicks league-by-
  name) can misjoin niche fixtures -> a phantom gap. Verify the match before flagging.

## TIER
HYPOTHESIS overall, with sub-pockets at different evidence levels: the WC prop engine has
leak-free POSITIVE skill on Saves (the seed of a CALIBRATION-PROVEN claim on that one stat) and
measured NEGATIVE skill on Cards/Assists/Goals/SoT (proven NON-pockets -- a success). The
scrapers, devig, EV, calibration-tiered board, and line-history all EXIST and are tested. The
gating step per stat is leak-free WF P(over)-vs-realized (BSS>0) on the PROVEN subset, then DFS
line-movement + forward CLV. Concentrate effort on the proven stats; do NOT re-mine the cut ones.
