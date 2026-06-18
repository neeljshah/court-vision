# soccer_intl PROP PUSH-PLAYBOOK -- FOULS (committed)

_Deep/actionable layer of the edge-intelligence corpus. Sport = soccer_intl (World Cup).
The best NON-Saves graduate candidate: positive but sub-threshold (bss +0.0339, below
PROVEN_BSS=0.05). Grounded in domains/soccer/{player_rates,prop_engine,team_defense}.py,
prop_calibration.json (as_of 2026-06-18), deep-dive 04 sec5/sec7, prop_tiering.py.
ASCII. No fabricated $-edge; tier-tagged throughout._

## One-line verdict
Fouls is the cheapest market to graduate: it already measures positive OOS skill (bss +0.0339,
n=662), it is HIGH-VOLUME (lam ~1-2 so the .5-ladder is informative, unlike the rare-event
goals/cards), and role players have STABLE foul rates. It just needs more matchdays to clear
the proven bar. Tier: MARGINAL (calibration positive, sub-threshold). $-edge HYPOTHESIS.

## The model (what produces the number)
- Pipeline: identical to all WC props -- `player_rates.player_rate(stat="Fouls")` ->
  EB-shrunk per-90 foul rate (foulsCommitted column, CANON_TO_COLS player_rates.py:35),
  club-prior blended; lam = per90 * E[min]/90 * opp_mult; NB two-pass widen
  (prop_edge.py:154-165).
- Distribution shape: NB. Fouls are moderately overdispersed (sporadic clustering when a
  player is booked/under pressure); the NB widen over Poisson matters on the over-2.5 / over-3.5
  rungs. lam ~1-2 means the .5 line sits near the mode -> a genuinely informative coin, unlike
  cards/goals where lam~0.1-0.3 makes the .5 line near-pure noise (the CUT-4 family).
- Opponent multiplier: generic team_defense allowed/for ratio (team_defense.py:193); thin on
  24 matches, mostly shrinks to 1.0. Note Fouls Drawn (the sibling market) uses the cleaner
  map opponent foulsCommitted -> our foulsSuffered (team_defense.py:72-85).

## Drivers (rate-only, ARCHETYPE not people)
1. ROLE / POSITION (dominant, and the reason fouls is stable): defensive-midfield (CDM) and
   centre-back archetypes commit fouls at a structurally higher, more STABLE per-90 rate than
   forwards. The "destroyer / ball-winning DM" scheme is the canonical high-foul archetype;
   "tempo-setting deep playmaker" the low-foul one. Describe by SCHEME, never by name.
2. GAME SCRIPT: a side defending a lead / sitting in a low block commits more tactical fouls;
   a dominant side commits fewer. The team scoreline model knows the favourite/underdog split
   and does NOT feed the prop stack -- an unused conditioning signal (same gap as Saves).
3. OPPONENT DRIBBLE/PRESS PRESSURE: facing a high-dribble opponent raises foul volume. This is
   the Fouls-Drawn side of the same coin (opponent foulsCommitted attribution exists).
4. MINUTES: fouls scale roughly linearly with minutes, so projected-minutes error feeds
   directly into lam error -- a key reason the live board is noisier than the backtest.

## Data
- HAVE: foulsCommitted + foulsSuffered in `espn_player_stats.parquet`; club priors for outfield
  players (960 of 1,241 WC players have a club prior). lam ~1-2 with enough volume that the
  per-match observation is informative (unlike the rare-event stats).
- MISSING: closing lines (no CLV), projected minutes (backtest uses realized), referee
  strictness signal (a real foul-volume driver; not ingested), and a role/scheme rate-split
  finer than DF/MF/FW/GK.

## Calibration / CLV proof plan
- CALIBRATION (measured, sub-threshold): bss +0.0339, brier 0.21237, ece 0.05662, n=662
  (prop_calibration.json). Positive => the model is sharper than the base-rate reference, but
  below PROVEN_BSS=0.05 so prop_tiering.classify tags it "marginal" (prop_tiering.py:113), and
  calibration_rank_key keeps it below Saves on the board (prop_tiering.py:167). Honest.
- GRADUATE-TO-PROVEN PLAN (the cheapest win on the whole WC board, deep-dive 04 sec7):
  1. Keep ingesting matchdays; re-run `python -m scripts.platformkit.props_eval --cache` after
     each. Strict-leak-free per-player Fouls rates only START to exist once players have 2+ WC
     matches -- today every player has exactly 1 (deep-dive 04 sec5), so most of the rate rides
     the club prior. More rounds is the dominant lever; no model change needed.
  2. Require BOTH bss>=0.05 AND >=2 independent matchdays improving (proof-standards.md rule 4)
     before promoting -- a single matchday lift is a selection artifact.
  3. Re-fit position-conditioned dispersion (keepers vs outfield clearly differ; deep-dive 04
     plan #6) so the NB width is measured, not the prior.
- CLV (the real bar): same as every WC prop -- capture closing Fouls lines into
  `prop_line_history.jsonl`; accrue forward CLV via clv_ledger. Until then, MARGINAL is the
  ceiling of the claim.

## Soft-line target (the $-hypothesis cell)
Fouls / Fouls-Drawn on ROLE PLAYERS (CDM, fullbacks, ball-winning midfielders) on DFS pick'em.
These players draw low bookmaker attention, have stable foul rates we can prior off the club
season, and the fixed-payout DFS line cannot move to kill a mispriced projection
(edge-theory.md P1). HYPOTHESIS, and only actionable AFTER Fouls graduates to proven AND a
closing-line / DFS-movement signal exists. Do NOT bet it on the current marginal tier.

## Honest tier + caveat
- TIER: MARGINAL (calibration positive, sub-threshold). $-edge: HYPOTHESIS.
- CAVEAT: positive bss on n=662 POOLED predictions across ~24 correlated matches is "promising,
  thin," NOT established. The honest action is to WAIT for matchdays + re-run the cache, not to
  add features (the data, not the model, is the binding constraint). Fouls is the realistic
  second proven WC market after Saves; treat it as a graduate candidate, not a current edge.
