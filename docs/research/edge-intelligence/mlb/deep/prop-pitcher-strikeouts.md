# PROP PUSH-PLAYBOOK -- Pitcher Strikeouts (the soundest MLB prop)
_Part of the edge-intelligence corpus (deep layer). Grounds in domains/mlb/player_rates_mlb.py,
exposure_mlb.py, prop_engine_mlb.py, scripts/platformkit/props_eval_mlb.py, the deep-dive
05-mlb-prop-engine.md, and the live player_gamelogs.parquet corpus. North star = CALIBRATION vs the
soft DFS line, NEVER a $-edge. Every claim carries a tier. ASCII only._

## Why this is the TOP per-opportunity candidate
A pitcher's strikeouts in a start are a SUM of per-batter-faced Bernoulli events: each batter faced
either strikes out (prob p_k) or does not. Over a large exposure (a starter faces ~24 BF; corpus mean
BF among starters confirms ~24), the sum of ~24 near-independent Bernoulli(p_k) trials is well
approximated by a Poisson/Negative-Binomial count. This is the textbook shape the engine assumes
(`prop_engine_mlb.py` lam = per_bf x E[BF]) -- and it is SOUND here, unlike Total Bases / RBIs /
Runs which are weighted or context-driven sums (see cut-list CUT 4 and prop-hits.md contrast).

This is the canonical stat `Pitcher Strikeouts` (`player_rates_mlb.PITCHER_CANON`, col
`pitch_strikeOuts`, role pitcher, exposure BF).

## The per-opportunity rate model (exact pipeline)
1. **Rate** (`player_rates_mlb.pitcher_rate`, `:206`): per_bf = sum(pitch_strikeOuts)/sum(battersFaced)
   over the pitcher's OWN rows with `date < as_of` (leak-free `_prior_rows`, `:91`), empirical-Bayes
   shrunk toward the pooled league per-BF K baseline: `(n_bf*raw + 30*baseline)/(n_bf+30)`
   (SHRINK_K=30 BF-worth, `:32`). Light for a 100+ BF regular, heavy for a call-up.
2. **Exposure** (`exposure_mlb.expected_bf`, `:80`): mean battersFaced over the last 15 prior
   appearances (self-separates starters ~24 from relievers via own history); default 24.0.
3. **Distribution** (`prop_engine_mlb.prop_distribution`): lam = per_bf x E[BF]; count dist is Poisson
   unless `dispersion` (NB size r) supplied; `p_over(line) = P(X > line)` via the sport-blind
   `_make_p_over` shared with soccer.

## The drivers (what actually moves K, in priority of signal)
1. **The pitcher's own K-per-BF rate** -- dominant; captured leak-free. The single best predictor.
2. **Expected BF / depth** -- exposure. A pitcher pulled at 4 IP cannot reach a 6.5 line regardless of
   rate. This is why the engine separates rate from exposure; it is also the largest source of variance
   in the realized count (a quick hook caps the count). The exposure projection is the weakest link
   (15-game mean ignores a same-day pitch-count plan / opener / piggyback).
3. **Opponent lineup K-propensity** -- a high-K opposing lineup lifts every per-BF K. NOT modelled (the
   league baseline is opponent-blind, limitation #6). This is the largest unpriced structural lever and
   the analog of soccer's opponent strength -- see "model-lever to add" below.
4. **Park / weather / umpire zone** -- second-order; not modelled. Umpire zone size has a small but
   real effect on called-K rate; out of reach without an umpire feed.
5. **Platoon / handedness mix** -- the opposing lineup's L/R split vs the pitcher's split; not modelled.

## Dispersion: the load-bearing correctness lever
Poisson assumes var == mean. Measured on the live corpus (starter appearances, BF>=18):
`var/mean(pitch_strikeOuts) ~= 1.1` -- mildly OVER-dispersed, exactly as the engine docstring warns
(`prop_engine_mlb.py:17`). Pure Poisson therefore makes the tails slightly too TIGHT and can FABRICATE
fake edges at the extreme alt lines (the proof-standards "too-tight distribution" trap). The fix already
exists but is UNUSED for props: fit a per-stat NB `r` from realized outcomes (method-of-moments on
residuals, mirroring `negbinom_engine.fit_dispersion_first_half` on the team side) and pass it as
`dispersion`. At var/mean~=1.1 the correction is small but nonzero; verify it does not HURT the main-line
Brier before shipping (only-improve-or-hold ratchet).

## Data needed (have / missing)
- HAVE (leak-free, in `player_gamelogs.parquet`): pitch_strikeOuts, battersFaced, date, player_id,
  is_pitcher per appearance. Corpus is now a full current-season slice (~1,031 games, 8,700 pitcher
  rows, median 19 games/player -- materially deeper than the 17-day snapshot the deep-dive recorded;
  re-verify n before any claim).
- MISSING (the ceiling): opponent-lineup K-propensity (need opposing batters' K rates joinable by
  game), confirmed same-day BF/pitch-count plan, park/umpire. Season-prior K/9 from statsapi season
  splits would be a strong low-variance shrink target (deep-dive item 9).

## Leak-free calibration plan (the proof bar)
1. Run `props_eval_mlb.backtest_calibration_mlb(df, stats=["Pitcher Strikeouts"])`. It walks games in
   date order, builds the rate from `date < as_of` ONLY, feeds the pitcher's REALIZED battersFaced as
   `exposure` (so it isolates RATE/shape calibration, not the exposure projection), picks the .5 line
   nearest lam (`_nearest_half_line`), and scores `p_over` vs `realized > line` with
   `score_prop_predictions` (Brier + ECE paired with sharpness + BSS vs base rate).
2. Read `per_stat["Pitcher Strikeouts"]`: require `n >= 100` INDEPENDENT pitcher-games and `bss >= 0.05`
   for CALIBRATION-PROVEN (`prop_tiering.classify`). Below n the gate returns INSUFFICIENT_DATA.
3. Repeat with a fitted NB `r` (`dispersion=`) to confirm the over-dispersion correction does not
   regress Brier/ECE. Ship the r ONLY if it holds across >=2 date folds (single-fold lift = artifact).
4. Cite the artifact: the `prop_calibration.json` (sport "mlb") row for this stat + the gate run date.
   As of the deep-dive snapshot this file was n=0 (all metrics null); a fresh run on the deeper corpus
   is the first honest verdict -- positive OR negative.

## The soft-line target (where the pocket is)
- **PrizePicks / Underdog MLB Pitcher-Ks** on NON-star starters (5th starters, spot starters, openers'
  bulk relievers) are the P1 pocket -- lazily set off a stale projection. STAR-pitcher K lines at major
  books are SHARP (efficient -- do not chase; markets-and-props.md).
- DFS pick'em has no two-way close -> CLV-vs-close is UNDEFINED. Prove via: (a) P(over)-vs-realized
  calibration above, (b) realized ROI at the fixed DFS payout, (c) DFS-line MOVEMENT (did our pre-line
  P(over) anticipate the app's later adjustment). Per edge-theory.md.
- Detection recipe: flag a candidate when engine `lam` diverges materially from the DFS line AND the
  pitcher has a DEEP prior (n_bf large). A large gap on a THIN-prior pitcher is more likely OUR error
  (heavy shrink to the league mean) than a soft line -- demote it.

## Honest tier + traps
- **Tier: HYPOTHESIS** (soundest shape, but no scored calibration verdict until the fresh backtest on
  the deeper corpus lands). Advances to CALIBRATION-PROVEN only on bss>=0.05, n>=100, >=2 folds.
- TRAP 1 -- exposure leakage of intent: the realized-exposure backtest tests RATE shape; live, the
  EXPOSURE projection (15-game BF mean) is the weak link. A pitcher on a strict pitch count blows up the
  count without changing the rate. Live calibration WILL be worse than the realized-exposure backtest;
  do not over-trust the backtest number as the live number.
- TRAP 2 -- opponent-blind rate: a high-K rate vs the league mean may simply reflect having faced weak
  lineups; without the opponent adjustment the rate is partly an opponent artifact. Add it before
  trusting extreme divergences.
- TRAP 3 -- too-tight Poisson tails at far alt lines (var/mean~=1.1). Fix with the NB r; FLAG any
  implausible |EV| on an alt line as mis-specification, not skill.
