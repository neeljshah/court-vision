# NBA ARCHETYPE -- RIM-RUNNING BIG (roll/lob finisher + interior anchor)

_Part of the edge-intelligence corpus. PLAYSTYLE / ROLE prior, NOT a person (binding graph rule).
Grounded in src/sim/basketball_sim.py (rim zone, prot_h, int_d, blk_per_min, oreb) + the role spine
data/cache/team_system/player_roles.parquet (ROLE_BIG n=62, ANCHOR_BIG n=19, TWO_WAY_BIG n=5 cluster
here; distinct from PRIMARY_BIG / STRETCH_BIG). See nba/00-edge-map.md + markets-and-props.md. ASCII.
Tiers: HYPOTHESIS / CALIBRATION-PROVEN / CLV-PROVEN._

## Who this is (role, not name)
The non-creating interior big: LOW-MODERATE usage, LOW self_create (dunks/lobs are assisted), LOW
spacing, HIGH rim_pressure, HIGH rim_protect, HIGH rebounding, tall (high height_in / size_z), LOW
playmaking. Maps to ROLE_BIG / ANCHOR_BIG / TWO_WAY_BIG. Distinguish from STRETCH_BIG (spacing) and
PRIMARY_BIG (a creator-big, which belongs with the high-usage-creator file). Defining trait: scoring
is at the RIM and ASSISTED; value is REBOUNDING + RIM PROTECTION.

## Stat profile -> prop ladder

| Prop | Profile for this role | Soft? | Verdict + why |
|---|---|---|---|
| PTS | MODERATE, EFFICIENT-volume (high FG% at rim), assisted. Lower variance than a creator | low-med | EFFICIENT; tight distribution (few 3s) => fewer alt-line cracks. Match close. |
| **REB** | the SIGNATURE stat: HIGH, driven by rebounding + height + oreb. R2 0.4224, q50 head | medium | the role's defining output. Calibration is decent; the soft pocket is matchup/pace dependent (REB OVER vs a small-ball or missing-big opponent that the book is slow to adjust) => freshness, P1. |
| AST | LOW (does not create). Low playmaking | YES (under) | structural AST floor -> UNDER safe; but the line is low, edge thin. Lean model-low. |
| 3PM | ~ZERO for a true rim-runner (low spacing). R2 0.3151 | n/a | UNDER 0.5 / >=1 is structurally safe but priced near it. NOT this role's pocket. |
| STL | noise (R2 0.1120) | n/a | NON-BETTABLE. |
| **BLK** | the SECOND signature: HIGH for rim_protect bigs. R2 0.2166 BUT sigma too tight x1.86; 3 CV features >=+0.15 corr (best CV retrain candidate) | **high (the real candidate)** | BLK is the strongest player-CV signal (10:158). For a HIGH rim_protect big, the OVER tail is under-priced because the marginal sigma is too tight (under-disperses the count). Inflate sigma / NB; this is the role where the BLK CV head matters most -- gated on CV coverage (<20%). |

## Where the SOFT pocket actually is for this role
1. **BLK OVER for a high rim_protect big**, via the too-tight-sigma fix. The leaguewide sigma x1.86
   under-dispersion (00-edge-map, prop-interval feedback) hits hardest on the bigs who actually block;
   the soft line is set near the tight-sigma median and the fat upper tail is mispriced. PRIMARY
   candidate for this role. Pair with the BLK CV head once coverage clears.
2. **REB OVER vs a depleted/small opponent** (freshness/matchup, P1): the sim's int_d/rebounding
   matchup moves the projection; the book lags the opponent's missing big.
3. **DOUBLE-DOUBLE (pts+reb)** -- this role is the natural DD profile; the count-stat recal matters
   (raw sim chain under-counts secondary milestones, 08:122, fixed via secondary_targets recal).
EFFICIENT for this role: PTS, AST, 3PM, STL. CUT.

## How the MC sim encodes this role
- **Rim zone + height -> shot quality:** rim shots face `prot_h = max(height over on-def)` and
  `rim_d_oc = max(int_d over on-def)` scaling the make via `DEF_RIM_SLOPE` clip(0.78,1.12)
  (basketball_sim.py:238,243-244). This role's tall, high-rim_pressure profile gives it efficient
  finishing AND, on defense, suppresses opponent rim makes.
- **Blocks:** `blkp = sum(blk_per_min over on-def)*0.5`, bumped by `0.004*max(0,prot_h-82)` at the
  rim (line 275-277), capped 0.22. A tall high-blk big drives the team block rate -> its own BLK mean
  rises natively. The known gap: the marginal prop sigma is too tight vs this sim/real tail.
- **Rebounding:** oreb continuation (`oreb_per_miss`, line 280) + dreb picks weighted by
  `oreb_per_min`/`dreb_per_min` -> a high-rebounding big collects the lion's share.
- **Assisted scoring:** LOW self_create => high p_assist factor => its rim makes are credited to the
  feeder (the lob passer), and its OWN AST stays near floor.

## Detection recipe (compute in-data)
Flag: `archetype in {ROLE_BIG, ANCHOR_BIG, TWO_WAY_BIG} OR (rim_protect >= 70th pct AND rebounding >=
70th pct AND spacing <= 30th pct AND self_create <= 0.40)`. Source: player_roles.parquet. For BLK:
compute the role's blk_per_min and compare the marginal sigma to the empirical count overdispersion;
flag where the line sits inside the under-dispersed median and the realized upper-tail mass exceeds
the priced tail.

## Proof method + honest tier
Tier = HYPOTHESIS. BLK calibration is currently MIScalibrated (sigma too tight) -> first prove the
sigma-inflated / NB marginal is CALIBRATION-PROVEN (coverage matches nominal OOS), THEN the soft-line
P(over) BSS vs a devigged BLK close. The CV BLK head stays gated until coverage >=20% (10:158). REB
is at the leaguewide ceiling -> only the matchup/freshness slice is a candidate; main-line REB is
EFFICIENT. NULL on PTS/AST/3PM/STL is expected.
