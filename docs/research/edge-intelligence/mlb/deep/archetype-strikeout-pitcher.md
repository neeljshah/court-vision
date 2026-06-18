# MLB ARCHETYPE PRIOR -- Strikeout Pitcher (ROLE, not a person)
_Part of the edge-intelligence corpus (deep/actionable layer). Describes a ROLE/PLAYSTYLE, never an
individual -- binding graph rule. Grounds in the 30,411-row player_gamelogs.parquet (data/domains/mlb/,
2026-04-01..06-17), domains/mlb/player_rates_mlb.py, domains/mlb/exposure_mlb.py, and the MLB edge map
(../00-edge-map.md). Tier: HYPOTHESIS (priors sharpening the shrink baseline + flagging soft markets, not
$-edges). ASCII only. No $-edge claims._

## Who this role is (definition by signature, not by name)
A STRIKEOUT PITCHER is a starter whose per-batter-faced strikeout rate sits in the top quartile of
starters -- a swing-and-miss arm that retires hitters via the K rather than batted-ball contact.
Classifier proxy for the profile below: starters (mean outs/appearance >= 12 AND BF >= 80), K/BF in the
top quartile. n=43 of 170 starters matched. Starters identified by mean outs/appearance >= 12 (~4+ IP).

## Typical per-BF profile (measured, leak-free corpus means)
The exposure unit for pitcher props is BATTERS FACED (BF) except Outs which is per-START
(player_rates_mlb.py:52-69). Compare K-pitcher starters vs all starters vs contact-pitcher starters:

| Per-BF stat | K-pitcher | All starters | Contact-pitcher | Note |
|---|---|---|---|---|
| **Pitcher K / BF** | **0.2774** | 0.2154 | 0.1549 | the signature: +29% vs starter mean |
| Earned Runs / BF | 0.0878 | 0.1087 | 0.1237 | LOWER ER -- misses bats, fewer balls in play |
| Hits Allowed / BF | 0.1952 | 0.2191 | 0.2405 | LOWER -- contact suppressed |
| Walks Allowed / BF | 0.0764 | 0.0812 | 0.0806 | roughly average (not a control trait) |
| K / 9 IP | **10.18** | 8.19 | 6.07 | the headline number |
| Outs / start | 16.6 | 15.9 | 15.0 | mildly DEEPER (efficient outs) |
| BF / start | 22.5 | 22.4 | 21.8 | ~same exposure as any starter |

Read: a strikeout pitcher is HIGH on Pitcher Ks, LOW on Earned Runs and Hits Allowed, average on Walks
Allowed, and goes mildly deeper (more outs/start). The K and the suppressed-contact traits travel together.

## Exposure tendencies
- Starter, so exposure is per-start: ~22.5 BF / ~16.6 outs (5.5 IP). The reliever role faces far fewer
  (~5.3 BF, corpus) -- a different archetype; this profile is starters only.
- Engine path: lam(Ks) = per_bf * E[BF] (player_rates_mlb.py:6); lam(Outs) is per-START directly
  (SHRINK_K_START=3.0, exposure-natural). For a K-pitcher lam(Ks) ~= 0.2774 * 22.5 ~= 6.2 Ks/start.
- IMPORTANT exposure mismatch: exposure_mlb.py:32 `_DEFAULT_STARTER_BF = 24.0`, but the measured starter
  mean is 22.4 BF/appearance. The 24.0 cold-start default OVERSTATES BF by ~1.6 -> inflates every per-BF
  over (most when the pitcher has no recent history and falls to the default).

## Which prop markets this role is SOFT on (where the pocket is)
- **Pitcher Strikeouts over** -- the soundest pitcher prop shape (large BF -> ~Poisson, mildly over-
  dispersed; edge map TOP PUSH-candidate). A DFS Ks line for a non-star high-K arm set off a pooled
  league K/BF (0.215) badly under-states a true 0.277 K/BF pitcher -> the over is systematically live.
  THE prop pocket for this role. CAVEAT: the prop `dispersion` r is never fit (limitation #5) so Poisson
  tails are too tight on Ks -- inflate with NB over-dispersion before trusting tail/alt-line EV.
- **Outs over** -- this role goes mildly deeper; the per-start Outs prop (cleanest, exposure-natural) is a
  secondary PUSH-candidate. Sharp at major books for star arms, but soft on back-of-rotation high-K types.
- AVOID as a bet: Earned Runs is low/sequence-dependent (edge map model-view). Selling the ER over for a
  K-pitcher is directionally right but the shape is rough -- model-view only.
- Sharp/efficient: STAR pitcher Ks at major books are explicitly sharp (edge map markets file) -- do NOT
  chase. The pocket is non-star high-K arms on lazy DFS lines.

## How this role should inform the shrink baseline + exposure model
1. **Role-conditioned K/BF baseline.** `_league_per_exposure` (player_rates_mlb.py:133) pools ONE pitcher
   K/BF across all pitchers; a thin-history K-pitcher gets shrunk toward 0.215, dragging the Ks line down.
   PROPOSED (HYPOTHESIS): cluster the per-BF baseline by pitcher role so K-pitchers shrink toward ~0.277.
   Largest expected calibration gain because the K/BF spread (0.155 vs 0.277) is the widest pitcher axis.
2. **Fix the BF default.** Recalibrate `_DEFAULT_STARTER_BF` (exposure_mlb.py:32) from 24.0 to the measured
   ~22.4 starter mean -- leak-free, affects every cold-start per-BF over. Keep the measured-mean path
   (status "ok", expected_bf lines 94-98) which already separates starters from relievers via own history.
3. **Over-dispersion is mandatory for this role.** K count for a high-K arm has the fattest tail; the unfit
   `dispersion` r is the worst here. Fit the prop NB r (limitation #5) before any K alt-line / over EV.

## Proof method before this prior is promoted past HYPOTHESIS
Per ../_framework/proof-standards.md: leak-free walk-forward; Pitcher-K Brier + BSS vs devigged close (or
P(over)-vs-realized + DFS line MOVEMENT); >=2 season-halves agree; FLAG implausible |EV| (too-tight Poisson
trap that produced the retracted +131%). Pre-commit the high-K-segment Ks-over hypothesis and test it FIRST
when the backfill lands. CALIBRATION-PROVEN only on a real props_eval_mlb segment run with BSS>0; CLV-PROVEN
only on forward paper CLV.
