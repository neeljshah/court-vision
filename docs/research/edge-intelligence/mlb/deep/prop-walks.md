# PROP PUSH-PLAYBOOK -- Walks (batter Walks + pitcher Walks Allowed)
_Part of the edge-intelligence corpus (deep layer). Grounds in domains/mlb/player_rates_mlb.py,
exposure_mlb.py, prop_engine_mlb.py, props_eval_mlb.py, the deep-dive 05-mlb-prop-engine.md, and the
live player_gamelogs.parquet corpus. North star = CALIBRATION, never a $-edge. Tiers on every claim.
ASCII only._

## Why Walks is a sound count -- and the caveat
A walk is a per-opportunity Bernoulli event on BOTH sides of the matchup: per-PA for the batter
(`Walks`, col `baseOnBalls`) and per-BF for the pitcher (`Walks Allowed`, col `baseOnBalls_allowed`).
The sum over the game's opportunities is a clean low-count distribution -- the same sound shape as
Pitcher-Ks and Hits. CAVEAT: walks are LOWER-rate than hits or Ks (corpus batter mean walks/game ~0.33),
so almost every batter Walks line is the 0.5 line, the per-game count is heavily zero-inflated, and the
RATE estimate is noisier per PA (fewer events -> wider EB shrinkage pulls hard toward the league mean).
Walks Allowed for a starter (~24 BF) accumulates more events per game and is the more stable of the two.

Canonical: `Walks` (batter, exposure PA) and `Walks Allowed` (pitcher, exposure BF).

## The per-opportunity rate model
- **Batter Walks** (`batter_rate`): per_pa = sum(baseOnBalls)/sum(PA) over `date < as_of` rows, EB-shrunk
  (SHRINK_K=30) toward the league per-PA walk baseline; lam = per_pa x E[PA] (`expected_pa`).
- **Walks Allowed** (`pitcher_rate`): per_bf = sum(baseOnBalls_allowed)/sum(battersFaced), EB-shrunk
  toward the league per-BF baseline; lam = per_bf x E[BF] (`expected_bf`, ~24 for starters).
- Distribution: Poisson (or NB with `dispersion`); p_over(line)=P(X>line). Lines are almost always 0.5
  (batter) or 1.5/2.5 (pitcher Walks Allowed over a full start).

## The drivers (priority of signal)
1. **Own walk rate** (batter plate discipline / pitcher command) -- dominant; captured leak-free. Walk
   rate is one of the most STABLE per-PA skills in baseball (stabilizes faster than BABIP/hits), which
   makes the shrunk own-rate genuinely informative once a batter has a few hundred PA.
2. **Exposure** -- PA (batter) / BF (pitcher). Walks Allowed depends heavily on how deep the starter
   goes (the exposure weak link, as for Ks).
3. **Opponent discipline / command** -- a patient opposing lineup lifts a pitcher's Walks Allowed; a
   wild opposing SP lifts a batter's Walks. NOT modelled (opponent-blind rate, limitation #6). For walks
   the opponent effect is real but generally SMALLER than for hits (walk rate is more pitcher/batter
   intrinsic than contact outcomes).
4. **Umpire zone** -- a tight/loose zone shifts called-ball rate; out of reach without an umpire feed.
5. **Intentional walks / game context** -- IBBs are not a skill event and pollute the count (a slugger
   walked around a base-open situation). If the feed distinguishes IBB, consider excluding it from the
   rate; the current `baseOnBalls` likely includes IBB -> a small upward bias on high-power batters.

## Dispersion note
Low-count + zero-inflated. Poisson is a defensible approximation at the 0.5 line; over-dispersion is the
least of the concerns here. The dominant error source is the NOISY rate (few events) over-shrunk to the
league mean, not the tail shape. Do not over-engineer the NB r for Walks before the rate has enough PA.

## Data needed (have / missing)
- HAVE: baseOnBalls, baseOnBalls_allowed, atBats, hitByPitch, battersFaced, date, player_id in
  `player_gamelogs.parquet` (current-season slice; re-verify n).
- MISSING (the ceiling): IBB split (to clean the batter rate), opponent command/discipline join,
  umpire zone, confirmed exposure. Season-prior BB% from statsapi splits is a strong low-variance shrink
  target (walk rate stabilizes fast -> season prior is informative).

## Leak-free calibration plan
1. `props_eval_mlb.backtest_calibration_mlb(df, stats=["Walks", "Walks Allowed"])` -- walk-forward,
   REALIZED exposure fed, .5 line nearest lam, `score_prop_predictions`.
2. CALIBRATION-PROVEN iff `bss >= 0.05` AND `n >= 100` independent player-games per stat. Expect Walks
   Allowed (pitcher, more events/game) to reach n and stabilize FASTER than batter Walks. Report both.
3. Because batter Walks is so low-count, watch for the collapse-to-base-rate failure: a model that just
   predicts the league walk rate for everyone will look "calibrated" (low ECE) but have BSS ~ 0 -- the
   sharpness pairing in `score_prop_predictions` catches this. Require BSS>0, not just low ECE.
4. Cite artifact: `prop_calibration.json` ("mlb") Walks / Walks Allowed rows + gate-run date.

## The soft-line target
- **PrizePicks / Underdog Walks / Walks Allowed** -- a NICHE, low-attention prop (most DFS volume is on
  Hits/Ks/Total Bases), which is precisely why it can be lazily set (P1 + P6 thin-attention overlap).
  Pitcher Walks Allowed on a wild-but-not-star starter is the cleanest candidate.
- No two-way DFS close -> prove via P(over)-vs-realized calibration + fixed-payout ROI + line movement.
- Detection recipe: flag when engine `lam` diverges from the DFS line for a DEEP-prior player where walk
  rate is the stable, dominant driver. Walks is the stat where the OWN-RATE is most trustworthy (skill
  stabilizes fast), so a deep-prior divergence is more credible here than for hits.

## Honest tier + traps
- **Tier: HYPOTHESIS.** Sound shape; lowest event-count of the four push candidates -> needs the most
  data to reach n and is the most shrinkage-dominated.
- TRAP -- collapse-to-base-rate: low BSS hiding behind low ECE; require BSS>0 with sharpness.
- TRAP -- IBB pollution on the batter side biases high-power batters' walk rate up; clean if the feed
  allows.
- TRAP -- over-shrinkage: with few walk events per PA, SHRINK_K=30 pulls thin-prior players almost
  entirely to the league mean -> divergence flags on thin priors are shrinkage artifacts, not edges.
