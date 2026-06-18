# PROP PUSH-PLAYBOOK -- Batter Hits (per-PA Bernoulli success count)
_Part of the edge-intelligence corpus (deep layer). Grounds in domains/mlb/player_rates_mlb.py,
exposure_mlb.py, prop_engine_mlb.py, props_eval_mlb.py, the deep-dive 05-mlb-prop-engine.md, and the
live player_gamelogs.parquet corpus. North star = CALIBRATION, never a $-edge. Tiers on every claim.
ASCII only._

## Why Hits is a SOUND count (and Total Bases / RBIs are NOT)
A batter's hits in a game is a SUM of per-plate-appearance Bernoulli successes: each PA is either a hit
(prob ~ batting-average-ish, after walks/HBP) or not. Over ~4 PA the sum of near-independent
Bernoulli(p_hit) trials is a clean low-count distribution that Poisson/NB approximates well. Crucially,
Hits counts EVENTS, not magnitudes -- a single and a homer both add exactly 1. That is what makes it a
sound count and Total Bases NOT one: Total Bases is a weighted sum (1B=1..HR=4) where one Poisson on the
weighted sum conflates frequency and magnitude and mis-fits the tail (`prop_engine_mlb.py:17` docstring;
cut-list CUT 4). RBIs/Runs are context-driven (baserunners, lineup) and carry teammate-leak. Hits is the
clean batter analog of Pitcher-Ks.

Canonical stat `Hits` (`player_rates_mlb.BATTER_CANON`, col `hits`, role batter, exposure PA).

## The per-opportunity rate model
1. **Rate** (`player_rates_mlb.batter_rate`, `:172`): per_pa = sum(hits)/sum(PA) over the batter's OWN
   rows with `date < as_of`, EB-shrunk toward the pooled league per-PA Hits baseline with SHRINK_K=30
   PA-worth. PA proxy = atBats + baseOnBalls + hitByPitch (`_pa_total`, `:118`).
2. **Exposure** (`exposure_mlb.expected_pa`, `:51`): mean PA over the last 15 prior games; falls back
   to the lineup-slot prior `_LINEUP_PA` (slot1->4.6 ... slot9->3.7, `:28`) or 4.0.
3. **Distribution**: lam = per_pa x E[PA]; Poisson (or NB with `dispersion`); p_over(line)=P(X>line).
   Typical lines are 0.5 and 1.5 (corpus batter mean hits/game ~0.81 among players with AB>0, so most
   Hits props are the 0.5 line on regulars, the 1.5 line on top-of-order bats).

## The drivers (priority of signal)
1. **The batter's own hit-per-PA rate** -- dominant; captured leak-free.
2. **Expected PA** -- exposure; lineup slot and whether they start. A slot-1 hitter gets ~4.6 PA vs ~3.7
   at slot 9 -- a real difference in the 1.5-line probability. Pinch-hit / late-sub risk is the live
   weak link (the 15-game mean assumes a full start).
3. **Opposing starting pitcher** -- the LARGEST unpriced structural lever for Hits. Facing a high-K /
   low-contact SP suppresses hit-per-PA sharply. NOT modelled (rate is opponent-blind, limitation #6).
   This is where the bulk of remaining Hits signal lives; analog of the SP lever on the team side
   (`asof_sp_form.py`).
4. **Park factor** -- batting-average parks (e.g. high-altitude) lift hit rate; the team domain has
   `asof_park.py` to multiply in leak-free; not yet wired into the prop rate.
5. **Platoon (L/R)** -- same-handed matchups suppress hit rate; not modelled.

## Dispersion note
Hits is low-count (lam often < 1.0); Poisson is a reasonable approximation and over-dispersion is mild.
The NB `r` lever matters less here than for Outs; still, fit and verify it does not HURT before adopting.
The bigger risk at the 0.5 line is the RATE being biased by an opponent-blind pool, not the tail shape.

## Data needed (have / missing)
- HAVE: hits, atBats, baseOnBalls, hitByPitch, batting_order, date, player_id per game-row in
  `player_gamelogs.parquet` (current-season slice; re-verify n).
- MISSING (the ceiling): opposing-SP identity + that SP's hit-per-BF allowed (join by game), park
  factor, platoon split, confirmed lineup slot / starting status (the live freshness gap the book sees
  first).

## Leak-free calibration plan
1. `props_eval_mlb.backtest_calibration_mlb(df, stats=["Hits"])` -- walk-forward, REALIZED PA fed as
   exposure (isolates rate/shape), .5 line nearest lam, `score_prop_predictions` -> Brier/ECE/BSS.
2. Read `per_stat["Hits"]`: CALIBRATION-PROVEN iff `bss >= 0.05` AND `n >= 100` independent batter-games
   (`prop_tiering.classify`); else INSUFFICIENT_DATA / REJECT.
3. Watch the 0.5 vs 1.5 line separately if possible -- the 1.5 line probability is far more
   exposure-sensitive (PA-dependent) and may calibrate worse than the 0.5 line. Report per-line.
4. Cite artifact: `data/domains/mlb/prop_calibration.json` ("mlb") Hits row + gate-run date. The
   deep-dive snapshot had n=0; the fresh run on the deeper corpus is the first verdict.

## The soft-line target
- **PrizePicks / Underdog Hits** on non-star, lower-in-order batters and platoon role-players are the P1
  pocket -- lazily set. Star top-of-order Hits lines are sharper (still softer than mainlines).
- No two-way DFS close -> prove via P(over)-vs-realized calibration + realized fixed-payout ROI + DFS
  line movement (edge-theory.md). CLV-vs-close undefined.
- Detection recipe: flag when engine `lam` diverges from the DFS line for a DEEP-prior batter,
  especially when the divergence is EXPLAINED by a driver the app likely ignored (e.g. a strong/weak
  opposing SP) -- but note our rate is opponent-blind, so until the SP adjustment is wired, that
  explanation is OUR hypothesis, not OUR model. Demote thin-prior divergences (heavy shrink artifact).

## Honest tier + traps
- **Tier: HYPOTHESIS.** Sound shape; no scored calibration yet on the deeper corpus.
- TRAP -- opponent-blind rate: a hot/cold hit rate may be an opponent-quality artifact. Largest single
  improvement is the opposing-SP adjustment; until then extreme divergences are suspect.
- TRAP -- exposure/lineup: the 1.5 line leans on PA; a late scratch or a drop in the order silently
  destroys it. Live calibration will trail the realized-exposure backtest.
- TRAP -- do NOT extend this playbook's "sound" verdict to Total Bases / RBIs / Runs / H+R+RBI. Those
  are mis-specified sums (CUT 4); they are NOT push candidates and belong in the multi-outcome cut, not
  here.
