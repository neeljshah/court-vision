# INEFFICIENCY -- Correlated SGP mispricing (P5; the sim's STRUCTURAL advantage)
_Per-pocket detection-recipe deep file. The one thing a MARGINAL model structurally cannot do.
Grounded in the NBA possession Monte Carlo (src/sim/basketball_sim.py + fast_sim.py) and its
joint pricer src/sim/sgp_from_sim.py (deep-dive 08). ASCII only. No $-edge claims._

## MECHANISM (why the crack exists)
Books price same-game-parlay (SGP) legs by combining INDEPENDENT marginals (the product of
each leg's prob), then apply a correlation haircut that is coarse and often wrong in sign or
size. The framework CORRELATION-BLINDSPOT crack: the true joint probability of a basket of legs
in ONE game is not the product, because every player draws from a SHARED game (a shared scoring
pie, a shared total, a shared pace). A model that prices legs marginally -- our prop stack, or
the book's -- CANNOT see this; only a model that samples a coherent JOINT can.

Our edge here is structural, not a tuned parameter. In `basketball_sim.py:91-94` each possession
is used by exactly ONE of the 5 on-court players, sampled by `use_per_min ** USAGE_CONCENTRATION
(1.25)`. Because the pie is shared and sampled per possession, the correct correlations EMERGE
rather than being imposed by a fragile rho-matrix:
- TEAMMATE same-stat: slightly NEGATIVE (validated ~ -0.10; two teammates compete for the same
  pie -> independence OVER-prices "both go over"). deep-dive 08 sec 2.2 / strength bullet 1.
- SAME-PLAYER cross-stat (pts<->reb, pts<->ast): POSITIVE (a big usage game lifts several of a
  player's lines together -> independence UNDER-prices). Realized pts-reb correlation runs
  +0.2..0.35 (08:208). NOTE this is the WEAK SPOT: the chain alone under-produces it, so a
  bolt-on CV_MIN_VAR corrector patches it at board time (08:208-209, 235). The teammate
  negative-corr is the cleaner, by-construction part; the same-player positive part is patched.
- GAME-SCRIPT cross-player: a star's pts UP can co-move with a teammate's ast UP (the feeder
  network, `assist_network.parquet`) -- a joint the book rarely prices at all.

This is the asset deep-dive 08 sec 7 names as durable: "the thing a marginal prop model
structurally cannot do, and the honest basis for an SGP/derivative product."

## CONCRETE DETECTION RECIPE (exact data + query + threshold)
Engine: one `simulate_game_fast(team_a, team_b, n_sims=20000, anchor=True, defense=True)` run
(GameSimResult, basketball_sim.py:305) gives every player 15 per-sim sample arrays -- every leg
is read off the SAME N simulated games, so any SGP is coherent from one run.

Pricer: `sgp_from_sim.joint_prob(result, legs)` returns `(joint, independent, lift)` where
- `joint`  = P(all legs hit) from the coherent samples (`hits &= leg.hit(samples)`),
- `independent` = product of each leg's marginal `leg_prob`,
- `lift = joint / independent`.
A `Leg(pid, stat in {pts,reb,ast}, line, over)` hits when `samples[pid][stat] (>|<) line`.

The MISPRICING the book makes IS `lift != 1`:
1. Build candidate baskets in the three high-signal families:
   - same-player +corr: e.g. `[Leg(pid, "pts", L1), Leg(pid, "reb", L2)]` -> expect lift > 1.
   - teammate -corr: e.g. `[Leg(pidA, "pts", L1), Leg(pidB, "pts", L2)]` same team -> lift < 1.
   - game-script: star pts + teammate ast (use the feeder pair in `assist_network.parquet`).
2. Flag a candidate when `|lift - 1| >= TAU_LIFT` (start TAU_LIFT = 0.10; below that the
   correlation is inside sim noise at 20k sims and not worth a leg). Confirm with the existing
   read-only wrapper `scripts/team_system/sgp_edge_scanner.py`.
3. WHERE TO BET (once real SGP prices exist): take the SGP when the book's implied joint
   (book_combined_prob) is on the wrong side of OUR joint -- specifically when the book priced
   near the independence product but our `joint` says lift>1 (book too cheap on the over-basket)
   or lift<1 (book too generous on the both-over teammate basket; fade it / take the under-leg
   combo). `describe(result, legs)` prints joint / independent / lift / fair odds for review.

## PROOF METHOD (which leak-free check + which metric)
TWO gates, in order; the FIRST is the gating next step because no SGP PRICE data is on disk.
1. JOINT CALIBRATION (the honest claim available NOW): `sgp_from_sim.validate_joint_calibration`
   simulates each cached game, draws random 2-3 leg parlays at the sim's OWN median lines (so
   each leg ~50/50, isolating the JOINT not the marginal), and grades predicted joint prob vs
   the realized joint outcome from the actual boxscore. Metric: reliability + Brier of the
   sim-joint model MINUS the same Brier for the INDEPENDENCE model (product of identical
   marginals). The CLEAN signal is the RELATIVE sim-vs-independence delta -- if correlation
   matters, independence is worse; if they tie, there is no SGP edge to harvest. Two caveats
   baked into the docstring: (a) rates are season-anchored => a mild ~1/100-game in-sample leak,
   so the absolute Brier is a fidelity check, NOT OOS; the RELATIVE delta is the trustworthy
   part. (b) coverage is NYK/SAS-only for the deep PBP/recency layers (08:195) -- the assist
   network and feeder game-script family are a two-team artifact until the builders run on all
   30 teams (08 quick-win 1). For a genuinely OOS joint claim: build rates as-of each game date
   (exclude the graded game) per 08 quick-win 2, then re-run.
2. CLV / ROI (the real-money bar): requires REAL captured SGP prices -- NONE in the repo
   (08:206). Until a feed exists, ROI is unprovable and must not be claimed. Once captured: log
   takes, compute CLV vs the closing SGP price, settle realized ROI at the real (correlation-
   inclusive) book price -- never the independence product, never flat payout.

## MAGNITUDE (honest)
Correlation lifts that survive 20k-sim noise sit in the family ranges above: teammate same-stat
lift modestly < 1 (the ~ -0.10 corr), same-player pts-reb lift > 1 driven by the +0.2..0.35
realized corr. A 2-3 leg basket's joint can differ from the book's independence-style price by a
material fraction precisely because books apply a coarse blanket haircut -- but the exact $-gap
is UNKNOWN without real SGP prices and must stay unquantified. The honest magnitude statement:
the JOINT STRUCTURE is right by construction (teammate part) / patched (same-player part); the
PRICE gap is a hypothesis pending a feed.

## HONEST CAVEAT / FAILURE MODES
- SAME-PLAYER CORR IS PATCHED, NOT EMERGENT. The +0.2..0.35 pts-reb correlation does not fall
  out of the chain; CV_MIN_VAR bolts it on at board time (08:208). So the positive-corr family
  is only as good as that corrector. The bigger-bet fix (08 item 4) is a per-game per-player
  common form/usage factor sampled once per sim so the joint is native. Until then, trust the
  TEAMMATE-NEGATIVE family more than the same-player-positive family.
- IN-SAMPLE RATES. Joint calibration is season-anchored (mild leak); only the sim-vs-independence
  RELATIVE delta and an as-of-date rebuild are honest OOS signals.
- NYK/SAS DEPTH ONLY. assist_network / recency / pbp_player_knowledge exist for 2 teams; the
  game-script family is not real league-wide yet.
- NO PRICE FEED => NO ROI. The structural advantage is calibration-shaped; the dollar claim is
  gated on SGP price capture that does not exist. Do not let "the joint is coherent" become "we
  beat SGP books."
- TOO-TIGHT TAILS. The chain's hard clips (anchor [0.4,2.5], 4-iter OREB cap, 08:217) bias
  extreme/blowout regimes; SGP legs deep in the tail (very high lines) inherit that bias.

## TIER
HYPOTHESIS, with a clear path to CALIBRATION-PROVEN. The joint pricer + the relative-to-
independence validator EXIST and are tested (test_sgp_joint_backtest.py, test_sgp_cross_team_
sweep.py). The gating step is: run validate_joint_calibration with the as-of-date rebuild on
>=2 team-sets and confirm sim-joint beats independence on Brier OOS -> CALIBRATION-PROVEN on the
JOINT. CLV-PROVEN is blocked on real SGP price capture. This is the system's single most
defensible structural pocket -- a marginal model cannot replicate it -- so it earns priority
once the NYK/SAS-only depth is generalized league-wide.
