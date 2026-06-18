# MLB ARCHETYPE PRIOR -- Contact Hitter (ROLE, not a person)
_Part of the edge-intelligence corpus (deep/actionable layer). Describes a ROLE/PLAYSTYLE, never an
individual -- binding graph rule. Grounds in the 30,411-row player_gamelogs.parquet
(data/domains/mlb/, 2026-04-01..06-17), domains/mlb/player_rates_mlb.py, domains/mlb/exposure_mlb.py,
and the MLB edge map (../00-edge-map.md). Tier: HYPOTHESIS (priors that sharpen the shrink baseline +
flag soft markets, not $-edges). ASCII only. No $-edge claims._

## Who this role is (definition by signature, not by name)
A CONTACT HITTER is a batter who puts the ball in play far more than league average and rarely homers --
a low-strikeout, low-power bat that trades slugging for batting average and base-hits. Classifier proxy
for the profile below: regulars (>=120 PA), K/PA <= 0.169 (corpus 25th pct) AND HR/PA <= 0.0254 (40th
pct). n=39 of 288 regulars matched.

## Typical per-PA profile (measured, leak-free corpus means)
| Per-PA stat | Contact role | League regular | Delta vs league | Note |
|---|---|---|---|---|
| **Hits / PA** | **0.2321** | 0.2214 | **+0.011** | above avg -- the value is base hits |
| **Total Bases / PA** | **0.3196** | 0.3635 | **-0.044** | LOW: hits are mostly singles |
| **Home Runs / PA** | **0.0122** | 0.0309 | **-0.019 (-60%)** | defining trait: almost no power |
| Walks / PA | 0.0829 | 0.0930 | -0.010 | aggressive, swings early -> fewer BB |
| **Batter K / PA** | **0.1321** | 0.2160 | **-0.084 (-39%)** | the signature: rarely strikes out |
| RBIs / PA | 0.0965 | 0.1171 | -0.021 | fewer XBH -> fewer RBI |
| Runs / PA | 0.1124 | 0.1207 | -0.008 | roughly average |
| Stolen Bases / PA | 0.0216 | 0.0183 | +0.003 | mildly higher (often top-of-order, speed) |

Read: a contact hitter is HIGH on Hits, very LOW on Batter Ks and Home Runs, LOW on Total Bases, and
slightly HIGH on Stolen Bases. The contact-vs-power split is almost orthogonal on the K and HR axes -- the
two roles diverge most on exactly the markets the engine prices independently.

## Exposure tendencies
- Lineup spot: skews top-of-order (slots 1-2, often 6-9 for defensive contact bats). Real corpus PA/game:
  spot1 = 4.23, spot2 = 4.16 -- the HIGHEST PA in the lineup. A leadoff contact bat gets ~4.2 PA, ~0.3 PA
  more than a cleanup power bat. This is the role MOST exposed to per-PA stats (most chances at the over).
- E[PA] multiplier: lam(Hits) for a leadoff contact bat ~= 0.2321 * 4.23 ~= 0.98 hits/game ->
  P(Hits>=1) ~= 1-e^-0.98 ~= 62%, P(Hits>=2) ~= 1-e^-0.98*(1+0.98) ~= 26%.

## Which prop markets this role is SOFT on (where the pocket is)
- **Hits over (0.5 / 1.5)** -- the cleanest soundest shape for this role: per-PA Bernoulli success count,
  low counts, ~Poisson (player_rates_mlb.py:38-58). High PA (top-of-order) + above-avg H/PA stacks the
  over. Strong P1 PUSH-candidate on lazy DFS pick'em lines for non-star contact bats. Prove BSS first.
- **Batter Strikeouts UNDER** -- the role is -39% on K/PA. A DFS "Batter Ks" line set off a pooled league
  K-rate will be too HIGH for a true contact bat -> the under is systematically live. Sound Bernoulli shape
  (edge map PUSH-candidate). This is arguably the role's single most exploitable mispricing because the K
  divergence is the LARGEST and the shape is sound.
- AVOID for this role: Total Bases over and Home Runs (role is LOW on both); selling those overs is correct
  but TB shape is rough (CUT 4) so treat as model-view, not a bet.

## How this role should inform the shrink baseline + exposure model
1. **Role-conditioned baseline fixes the K/HR pull the wrong way.** The single global `_league_per_exposure`
   (player_rates_mlb.py:133) shrinks a thin-PA contact bat's K-rate UP toward 0.216 and HR-rate UP toward
   0.031 -- both wrong-direction for this role. PROPOSED (HYPOTHESIS): cluster the baseline so contact bats
   shrink toward ~0.13 K/PA and ~0.012 HR/PA. Largest expected calibration gain of any role because the K
   axis divergence (0.084 per-PA) is the widest in the corpus.
2. **Exposure: this role benefits MOST from the lineup-spot fix.** Top-of-order means high PA; the hardcoded
   `_LINEUP_PA` defaults (4.6/4.5 for slots 1-2, exposure_mlb.py:28) OVERSTATE the measured means
   (4.23/4.16). Recalibrating to the corpus means trims lam slightly on the Hits over -- a pure calibration
   correction (leak-free to derive on past rows).
3. **Recency beats volume (cross-sport invariant).** exposure_mlb already windows _RECENT_GAMES=15; keep it
   -- a contact bat's role is stable but a slump/role-change shows in recent PA first.

## Proof method before this prior is promoted past HYPOTHESIS
Per ../_framework/proof-standards.md: leak-free walk-forward; for Hits/Batter-K, Brier + BSS vs devigged
close, or P(over)-vs-realized + line MOVEMENT for DFS pick'em; >=2 season-halves agree; flag implausible
EV. The Batter-K-under and Hits-over are the two segment hypotheses to pre-commit and test FIRST when the
backfill lands. CALIBRATION-PROVEN only on a real props_eval_mlb segment run with BSS>0; CLV-PROVEN only on
forward paper CLV.
