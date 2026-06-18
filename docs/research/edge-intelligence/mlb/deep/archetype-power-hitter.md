# MLB ARCHETYPE PRIOR -- Power Hitter (ROLE, not a person)
_Part of the edge-intelligence corpus (deep/actionable layer). Describes a ROLE/PLAYSTYLE, never an
individual -- binding graph rule. Grounds in the 30,411-row player_gamelogs.parquet
(data/domains/mlb/, 2026-04-01..06-17), domains/mlb/player_rates_mlb.py, domains/mlb/exposure_mlb.py,
and the MLB edge map (../00-edge-map.md). Tier: HYPOTHESIS (prop corpus is too thin to have cleared
calibration; these are PRIORS that sharpen the shrink baseline + flag soft markets, not $-edges).
ASCII only. No $-edge claims._

## Who this role is (definition by signature, not by name)
A POWER HITTER is a batter whose per-PA home-run rate sits in the top quartile of regulars, typically
hitting in the middle of the order (slots 3-5) and accepting elevated strikeout risk for slugging. The
classifier proxy used to derive the profile below: regulars (>=120 PA in corpus), HR/PA >= 0.0417
(the corpus 75th percentile). n=75 of 288 regulars matched.

## Typical per-PA profile (measured, leak-free corpus means)
Compare POWER vs the LEAGUE per-PA baseline that `player_rates_mlb._league_per_exposure` pools toward:

| Per-PA stat | Power role | League regular | Delta vs league | Note |
|---|---|---|---|---|
| Hits / PA | 0.2293 | 0.2214 | +0.008 | barely above avg -- power is NOT contact |
| **Total Bases / PA** | **0.4398** | 0.3635 | **+0.076** | the signature: +21% TB; extra-base driven |
| **Home Runs / PA** | **0.0535** | 0.0309 | **+0.073 rel (+73%)** | defining trait |
| Walks / PA | 0.1029 | 0.0930 | +0.010 | pitched-around -> mildly more BB |
| **Batter K / PA** | **0.2379** | 0.2160 | **+0.022** | the cost: more whiffs |
| RBIs / PA | 0.1452 | 0.1171 | +0.028 | drives in runs (middle-order + power) |
| Runs / PA | 0.1411 | 0.1207 | +0.020 | crosses the plate often (HR self-scores) |
| Stolen Bases / PA | 0.0143 | 0.0183 | -0.004 | slower; SB is NOT this role's market |

Read: relative to the league prior the engine shrinks toward, a power hitter is materially HIGH on
Total Bases, Home Runs, RBIs, Runs, and Batter Ks, roughly average on Hits, and LOW on Stolen Bases.

## Exposure tendencies
- Lineup spot: predominantly slots 3-5. Real corpus PA/game by spot (exposure_mlb path):
  spot3 = 4.04, spot4 = 3.94, spot5 = 3.75 PA/game. So a cleanup power bat gets ~3.9 PA, i.e. roughly
  ONE FEWER PA than a leadoff bat (4.23) -- this caps the over-side count on every per-PA stat.
- E[PA] is the multiplier: `prop_engine_mlb` lam = per_pa * E[PA] (player_rates_mlb.py:6 contract).
  For a cleanup power hitter lam(HR) ~= 0.0535 * 3.94 ~= 0.21 HR/game -> P(HR>=1) ~= 1-e^-0.21 ~= 19%.

## Which prop markets this role is SOFT on (where the pocket is)
- **Total Bases over** -- the role's strongest divergence (+21% per-PA). DFS pick'em TB lines on a
  middle-order power bat set off a stale pooled rate will systematically under-price the over. P1 pocket
  candidate. CAVEAT: TB is a weighted sum (1B/2B/3B/HR); Poisson on the sum mis-fits the tail
  (edge map CUT 4) -- prove the marginal calibration before betting, and never on a same-game parlay
  (no joint model, limitation #7).
- **Home Runs over 0.5** -- highest relative lift, but very low absolute rate and lumpy; display/model-
  view only until a richer (park + opposing-pitcher fly-ball) rate exists (edge map: HR display-only).
- Sharp/efficient for this role: star-power-bat HR lines at major books (liquid, sharp -- do NOT chase).

## How this role should inform the shrink baseline + exposure model
1. **Role-conditioned league baseline.** Today `_league_per_exposure` (player_rates_mlb.py:133) pools ONE
   global per-PA mean across all batters; a power hitter with thin recent PA gets shrunk toward a contact-
   diluted league mean that is too LOW on TB/HR. PROPOSED (HYPOTHESIS): compute the baseline within a role
   cluster (power / contact / balanced) so the SHRINK_K=30 PA-worth of shrinkage pulls toward 0.44 TB/PA,
   not 0.36. This reduces early-season under-pricing of the over on call-up power bats.
2. **Exposure cap is the over-killer.** Because power bats sit slot 3-5 (~3.9 PA, not 4.6), the hardcoded
   `_LINEUP_PA` defaults in exposure_mlb.py:28 (4.4/4.2/4.1 for 3/4/5) OVERSTATE real PA (corpus:
   4.04/3.94/3.75). PROPOSED: recalibrate `_LINEUP_PA` to the measured per-spot means -- this trims lam on
   every per-PA over for this role and is a pure calibration fix (no leak, fully in-sample-free to derive
   on past rows).
3. **Variance flag.** Power per-PA stats (HR, TB) are higher-variance than contact; the prop `dispersion`
   r is never fit (limitation #5) so Poisson tails are too tight. This role is the WORST case for that bug
   -- HR/TB tails need NB over-dispersion before any over EV is trusted.

## Proof method before this prior is promoted past HYPOTHESIS
Per ../_framework/proof-standards.md: leak-free walk-forward, score per-stat Brier + BSS vs the devigged
close (or for DFS pick'em, P(over)-vs-realized calibration + DFS line MOVEMENT since no two-way close),
require >=2 corpora / season-halves to agree, and demote RBIs/Runs (teammate/context leak). Promote to
CALIBRATION-PROVEN only on a real props_eval_mlb run with BSS>0 on the role segment; CLV-PROVEN only on
forward paper CLV. Until the gamelog backfill reaches 1-2 full seasons (edge map: corpus is 30k rows /
~2.5 months), all of the above is HYPOTHESIS.
