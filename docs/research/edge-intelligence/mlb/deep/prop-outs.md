# PROP PUSH-PLAYBOOK -- Pitcher Outs Recorded (the exposure-natural target)
_Part of the edge-intelligence corpus (deep layer). Grounds in domains/mlb/player_rates_mlb.py,
exposure_mlb.py, prop_engine_mlb.py, props_eval_mlb.py, the deep-dive 05-mlb-prop-engine.md, and the
live player_gamelogs.parquet corpus. North star = CALIBRATION, never a $-edge. Tiers on every claim.
ASCII only._

## Why Outs is the CLEANEST target structurally -- and its unique risk
Outs recorded by a starting pitcher is the ONE canonical MLB stat that is EXPOSURE-NATURAL: it IS the
exposure (3 outs = 1 inning). So the engine models it DIRECTLY per START -- no rate x exposure
multiplication, no separate exposure-projection weak link. `MLB_CANON` puts Outs in `PER_START_STATS`
(`player_rates_mlb.py:69`): `pitcher_rate` returns `per_start` (mean outs/start, EB-shrunk with
SHRINK_K_START=3.0 starts-worth, `:33`), and `prop_distribution` sets `lam = per_start` directly
(`prop_engine_mlb.py:62-67`). This removes the largest source of live miscalibration that afflicts Ks /
Hits / Walks (the BF/PA projection). That makes Outs structurally the cleanest of the four.

UNIQUE RISK: Outs is the MOST over-dispersed of the four. Measured on the live corpus (starter
appearances, BF>=18): `mean outs ~= 16.4` (about 5.5 IP) but `var ~= 9.9` -- the distribution is NOT
Poisson-shaped at all. It is bimodal-ish / left-skewed: a starter either gets pulled early (a short hook
-> a cluster of low values) or cruises to ~18-21 outs. A single Poisson(16.4) would put var==mean==16.4
and badly mis-fit BOTH the early-hook tail and the cap near 21-27. The NB `r` lever is NOT optional here.

Canonical stat `Outs` (`PITCHER_CANON`, col `outs`, role pitcher, exposure = start).

## The model (exact pipeline)
1. **Rate = lam directly** (`pitcher_rate`, per-start branch, `:229`): per_start = mean(outs) over the
   pitcher's OWN starts with `date < as_of`, EB-shrunk toward the league per-start outs baseline (denom
   = count of starts) with SHRINK_K_START=3.0. A few starts settle it.
2. **No exposure step.** `_resolve_rate_and_exposure` returns `(per_start, exposure=1.0)` -- lam is the
   mean outs itself.
3. **Distribution**: Poisson(lam) default; SHOULD be NB with a fitted `r` given the heavy
   over-dispersion. p_over(line)=P(X>line). Standard DFS lines cluster around 16.5-18.5 (i.e. ~5.5-6.5
   innings); the 17.5 line (5.2/3 -> "over 5.2 IP") is the canonical one.

## The drivers (priority of signal)
1. **The pitcher's own depth / efficiency** -- dominant; how deep they are LET to go (a function of
   stuff, pitch efficiency, role). Captured leak-free by mean outs/start.
2. **The HOOK / bullpen-usage regime** -- the decisive driver of the variance and the single biggest
   unpriced lever. Modern openers, piggybacks, and quick hooks make Outs heavily regime-dependent. A
   pitcher's recent outs/start partly encodes their manager's leash, but a same-day plan (opener day,
   doubleheader, taxed bullpen) is invisible to the model and the largest live-vs-backtest gap.
3. **Game script** -- a blowout (either direction) pulls or extends a starter; not modelled.
4. **Opponent lineup / pitch efficiency** -- a high-pitch-count lineup shortens the start; opponent-blind
   rate ignores it.
5. **Injury / pitch-count return-from-IL ramp** -- a returning starter on a 75-pitch limit caps outs
   regardless of skill; invisible to the rate (looks like their healthy mean).

## Dispersion: mandatory, not optional
var/mean ~= 0.6 of the mean is misleading -- the raw `var ~= 9.9` at `mean ~= 16.4` means the count is
UNDER-dispersed relative to Poisson IF you only look at var<mean, but the SHAPE is wrong (truncated at
~27, lumpy at hook points), not the dispersion magnitude. Practically: a Poisson(16.4) over-weights the
far-over tail (>20) and under-weights the early-hook tail (<12). The honest fix is NOT a single NB r but
either (a) fit an NB/under-dispersed count that respects var<mean, or (b) model outs as innings x 3 with
an explicit short-hook hazard. Minimum viable correction: fit the per-stat dispersion from realized outs
and FLAG any far-tail line where the fitted shape and Poisson disagree materially. This is the stat where
"too-tight / wrong-shape distribution fabricates fake edges" (proof-standards.md) bites HARDEST.

## Data needed (have / missing)
- HAVE: outs (and inningsPitched, battersFaced), date, player_id, is_pitcher per pitcher row in
  `player_gamelogs.parquet` (current-season slice; re-verify n; ~1,900 starter-ish appearances).
- MISSING (the ceiling): same-day pitch-count plan / opener flag / bullpen-availability (the hook
  regime -- the dominant variance driver), game-script, IL-return pitch limits. These are the
  same-day-information freshness gap the book sees first (deep-dive ceiling = freshness, not history).

## Leak-free calibration plan
1. `props_eval_mlb.backtest_calibration_mlb(df, stats=["Outs"])` -- the per-start path feeds NO exposure
   (`_realized_exposure` returns None for per-start, `props_eval_mlb.py:81`), so this tests the
   per-start lam shape directly. .5 line nearest lam, `score_prop_predictions`.
2. CALIBRATION-PROVEN iff `bss >= 0.05` AND `n >= 100` independent starts. Because Outs is the cleanest
   STRUCTURE (no exposure step), its realized-exposure-free backtest is the truest of the four -- but it
   will EXPOSE the distribution-shape problem: expect ECE to be driven by mis-fit tails, not the mean.
3. CRITICAL: re-run with a fitted dispersion and compare tail calibration (reliability in the >19.5 and
   <13.5 buckets), not just overall Brier. Ship the dispersion fix only if it improves the TAILS without
   regressing the center, across >=2 folds.
4. Cite artifact: `prop_calibration.json` ("mlb") Outs row + gate-run date.

## The soft-line target
- **PrizePicks / Underdog Outs Recorded** (often phrased as "Pitcher Outs" or an IP line) on non-ace
  starters is a clean P1 pocket -- the line is set off a stale season mean and is slow to reflect a
  shifting leash / opener day. The OUTS line is where same-day role info (opener, piggyback) creates the
  softest pre-line numbers.
- No two-way DFS close -> prove via P(over)-vs-realized calibration + fixed-payout ROI + line movement.
- Detection recipe: flag when engine lam diverges from the DFS Outs line AND the divergence is NOT
  explained by a same-day role change the app may have priced. Because the model is blind to the hook
  regime, treat an UNDER signal (model says fewer outs than the line) more cautiously -- the model
  cannot see a planned early hook, so it may be UNDER-confident on unders, not over.

## Honest tier + traps
- **Tier: HYPOTHESIS.** Structurally the cleanest (no exposure step) but distributionally the trickiest
  (wrong-shape, not just wrong-dispersion). Net: a strong CANDIDATE only after the shape fix is
  validated.
- TRAP -- wrong distribution shape (NOT just dispersion): Poisson(16.4) mis-fits the early-hook tail and
  the ~21-27 cap. This is the most dangerous fake-edge generator of the four; the alt-line ladder is
  where it shows. Validate tail reliability buckets explicitly.
- TRAP -- hook-regime blindness: the dominant variance driver (manager leash, opener, bullpen state) is
  unmodeled and same-day; live calibration will trail the backtest most for Outs.
- TRAP -- IL-return / pitch-limit caps look like the pitcher's healthy mean -> the model over-projects a
  ramping starter's outs. Needs a same-day limit flag to fix.
