# METHOD: Empirical-Bayes shrinkage to a baseline (thin-data rates)
_Method library / edge-intelligence corpus. The shrink-to-baseline formula, how to choose K,
WHEN shrinkage dominates, and the failure modes. Grounded in the live per-90 rate engine.
ASCII only._

## The problem it solves
A player's own sample is THIN (1-3 World Cup matches; an early-season MLB starter; a player
returning from injury). The raw per-unit rate is dominated by noise: a striker with 1 shot in
1 match reads as 1.0 shots/90, a player with 4 reads 4.0/90, and neither is a trustworthy
prediction. Empirical Bayes pulls the noisy own-rate toward a structured BASELINE (the prior),
by an amount that depends on how much own-data exists. With lots of data it barely moves; with
almost none it becomes the baseline.

## The formula (the load-bearing line)
    shrunk = (n_eff * own_rate + K * baseline) / (n_eff + K)

- `own_rate`   = the player's leak-free rate (e.g. per-90 = 90 * stat_total / minutes_total).
- `baseline`   = the prior to shrink toward (a POSITION/ROLE-level rate, never a person).
- `n_eff`      = effective sample size, in the SAME UNITS as K (matches-worth, started-matches,
                 or innings/PA-worth). For per-90 rates, `n_eff = minutes_total / 90`.
- `K`          = shrinkage strength, in those same units. The "phantom sample" of baseline.

Interpretation: K is the number of baseline-units you treat as prior evidence. When
`n_eff = K`, the estimate is exactly halfway between own and baseline. When `n_eff >> K`, it is
essentially the own rate. When `n_eff -> 0`, it is the baseline.

## Choosing K (and what units it must be in)
- K is a regularisation strength. Larger K = trust the baseline longer (slower to believe a
  player's own deviation); smaller K = trust own data sooner (noisier, faster).
- UNITS MUST MATCH n_eff. The soccer engine uses `SHRINK_K = 3.0` matches-worth: lean on the
  position baseline until a player has ~3 full matches of minutes. Pick K by the regime: for
  international/tournament data with very few caps, K ~ 2-4 matches is sensible; for a long club
  season, you want the prior to fade faster relative to a large own-sample.
- Principled K: in conjugate Gamma-Poisson EB, K = baseline_mean / between-player variance of the
  rate (more between-player spread -> smaller K -> trust own data sooner). In practice a fixed K
  chosen by cross-validated coverage/Brier is fine; tune K by OOS calibration, never in-sample.
- DO NOT let one strong prior fully swamp own data. The engine caps a club-season prior's weight
  (`CLUB_WEIGHT_CAP = 20.0` started-matches) so even a big club sample cannot erase a player's
  own tournament matches.

## Multi-prior blend (club prior + own + baseline)
When a STRONGER prior than the position baseline exists (a player's own club season = real recent
form), blend it as a weighted average FIRST, then residually shrink the blend toward the baseline
only if still thin:

    blended = (n_wc * wc_rate + club_w * club_rate) / (n_wc + club_w)   # club_w = min(starts, CAP)
    n_eff   = n_wc + club_w
    if baseline and n_eff < K:
        shrunk = (n_eff * blended + K * baseline) / (n_eff + K)

This is the engine's "club-backed" path: a player with a solid club season is NO LONGER THIN even
on ~1 tournament match, which is exactly when raw rates are most dangerous.

## WHEN shrinkage DOMINATES (the regime where it is the biggest lever)
- Thin own-sample + a credible structured baseline: tournament props, early-season, post-injury,
  call-ups, debutants. This is the PRIMARY soft-prop pocket (PrizePicks/Underdog price these
  lazily), so getting the thin-data rate right is where the calibration edge concentrates.
- Many low-volume units pooled (per-player, per-pitcher, per-archetype rates).
- It is NOT the lever once a player has a large own-sample (n_eff >> K): then own-rate ~ raw, and
  the marginal benefit of shrinkage vanishes -- spend effort elsewhere (recency weighting, context).

## Baseline must be a ROLE/POSITION, never a person (binding graph rule)
The baseline is a POSITION/ROLE/ARCHETYPE-level pooled rate (e.g. all forwards' shots/90 before
as_of), computed minutes-weighted and leak-free. Never construct a baseline that names or keys on
an individual person as the prior identity -- archetypes/playstyles/roles only.

## Failure modes
- WRONG UNITS: n_eff in matches but K in minutes (or vice versa) silently over/under-shrinks.
  Keep both in the same unit (the engine uses matches-worth throughout).
- LEAKY BASELINE: computing the position baseline from rows on/after the event leaks the future.
  Always restrict to rows strictly before as_of (`_prior_rows`).
- SWAMPING: an uncapped strong prior erases real own-signal -> cap its weight (`CLUB_WEIGHT_CAP`).
- FALSE CONFIDENCE ON THIN DATA: a shrunk rate is still a MODEL VIEW, not actionable certainty,
  unless `n_eff` clears a confidence threshold (`CONFIDENCE_N_EFF = 5.0`). Label the tier; do not
  bet a 1-match player's number as if it were a season's worth.
- TUNING K IN-SAMPLE: choosing K to minimise error on the data you fit on overfits; tune on OOS
  coverage/Brier (proof-standards.md, walk-forward bar).
- NO BASELINE AVAILABLE: if there is no baseline to shrink toward, report the raw rate UNSHRUNK
  and flag it thin -- do not invent a baseline.

## Code pointers
- `domains/soccer/player_rates.py` -- the reference EB engine.
  - `SHRINK_K = 3.0` (line 23), `CLUB_WEIGHT_CAP = 20.0` (line 30), `CONFIDENCE_N_EFF = 5.0` (33).
  - `position_baseline()` (lines 93-113) -- leak-free minutes-weighted ROLE baseline (the prior).
  - `player_rate()` (lines 143-263) -- the full path: club-backed blend (203-224) and the legacy
    single-prior shrink `shrunk = (n_eff*raw_per90 + SHRINK_K*baseline)/(n_eff+SHRINK_K)` (255).
  - `_prior_rows()` (lines 62-71) -- the strict-before-as_of leak guard; shared by dispersion.py.
- `domains/soccer/dispersion.py` -- consumes the per-row mean lam this engine produces and falls
  back to per-stat PRIOR phi on thin data (the dispersion analogue of shrink-to-prior).

## Proof tier
The METHOD is sound by construction (leak-free, reduces variance on thin samples) and is
CALIBRATION-validated when its OOS coverage/Brier matches the target. K and the baseline choice
are CALIBRATION decisions, never $-edge claims. A shrunk rate feeding a prop EV stays HYPOTHESIS
until CLV-proven forward on paper.
