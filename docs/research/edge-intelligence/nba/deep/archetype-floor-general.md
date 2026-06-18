# NBA ARCHETYPE -- FLOOR GENERAL (pass-first lead guard / distributor)

_Part of the edge-intelligence corpus. PLAYSTYLE / ROLE prior, NOT a person (binding graph rule).
Grounded in src/sim/basketball_sim.py (assist_net, playmaking, ast_per_min routing, p_assist) + the
role spine data/cache/team_system/player_roles.parquet (FLOOR_GENERAL n=28, LEAD_GUARD n=66,
CONNECTOR_GUARD n=14). See nba/00-edge-map.md + markets-and-props.md. ASCII.
Tiers: HYPOTHESIS / CALIBRATION-PROVEN / CLV-PROVEN._

## Who this is (role, not name)
The pass-first distributor: HIGH playmaking, MODERATE usage, MODERATE-to-LOW self_create (creates FOR
others more than self), HIGH creation (initiates offense) but scoring is SECONDARY (lower scorer_pct
than a high-usage creator). Maps to FLOOR_GENERAL / pass-first LEAD_GUARD / CONNECTOR_GUARD. The
CONTRAST with the high-usage-creator file is the axis that drives the whole AST edge: BOTH are
ball-dominant, but the floor general's value is ASSISTS, not own-points. Lazy lines that conflate
the two are the seam.

## Stat profile -> prop ladder

| Prop | Profile for this role | Soft? | Verdict + why |
|---|---|---|---|
| **AST** | the SIGNATURE stat: HIGH, the highest-assist archetype. Leaguewide R2 0.4988, calibration OFF on purpose to preserve divergence | **YES -- the P1 model edge** | THE documented ~+7% AST edge lives most strongly here (00-edge-map AST row; 07:115,189). For a TRUE floor general the model tends to project assists ABOVE a lazy line that anchors on points; lean WITH the model (OVER on a pass-first distributor whose assists the book under-rates). KEEP RAW; never playoffs. |
| PTS | MODERATE, lower than a creator (scoring secondary). R2 0.5105 | low-med | EFFICIENT main line; the soft slice is PTS-UNDER when the role defers (see pocket 2). |
| REB | LOW (guard). R2 0.4224 | low | EFFICIENT; match close. |
| 3PM | MODERATE, depends on spacing; pull-up vs spot-up varies. R2 0.3151 | medium | secondary; alt-ladder candidate only if high spacing. Not the role's pocket. |
| STL | noise (R2 0.1120) but guards gamble for steals | n/a | NON-BETTABLE; OVER tail exists (high perimeter activity) but unpredictable. Flag low-confidence. |
| BLK | ~zero floor (guard) | n/a | UNDER structurally safe; priced near it. |

## Where the SOFT pocket actually is for this role
1. **AST OVER on a true pass-first floor general** -- the strongest expression of the project's one
   durable model edge. The model separates `playmaking` (high here) from `scorer_pct` (lower here);
   lazy lines anchored on scoring under-rate the assist output. This is the SINGLE MOST ACTIONABLE
   archetype-level insight in the NBA deep set. (HYPOTHESIS -> leak-free OOS re-prove is the open
   action.) Mirror-image of the score-first creator's AST-UNDER.
2. **AST OVER absorption when a co-creator is OUT** -- the floor general inherits initiation; the sim
   re-routes playmaking to it (assist_net redistributes), the book lags (freshness, P1). Strongest
   single-game AST signal.
3. **PTS UNDER when the role fully defers** to a healthy primary scorer -- secondary scoring drops.
EFFICIENT for this role: PTS-main, REB, 3PM, STL, BLK. CUT.

## How the MC sim encodes this role
- **Feeder network -> assists:** when ANY teammate scores, the assister is drawn from the REAL PBP
  `assist_net` (basketball_sim.py:266-271): `aw = 0.7*(real_net) + 0.3*(ast_per_min floor)`. A high
  playmaking / high ast_per_min role wins this draw repeatedly -> its AST mean is HIGH and is a
  sim-native quantity, not a regression bolt-on. This is the structural source of the AST edge.
- **Self-create vs playmaking separation:** the role's OWN makes are assisted (moderate self_create
  -> moderate p_assist), so its scoring does NOT inflate its assists; the two stats are decoupled
  exactly as the AST divergence requires (line 263 vs 266).
- **Usage routing:** moderate `use_per_min ** 1.25` -> it takes possessions but distributes them; the
  USAGE_CONCENTRATION superlinearity routes the BALL to it without forcing it to SHOOT.
- **Team assist total preserved:** the (1-self_create) factor is recentered (x1.67 at the 0.4 mean,
  comment line 261-262) so only the per-shooter assist DISTRIBUTION shifts -> the floor general's
  share rises without breaking the team total.

## Detection recipe (compute in-data)
Flag: `archetype in {FLOOR_GENERAL, CONNECTOR_GUARD} OR (playmaking >= 66th pct AND creation >= 60th
pct AND scorer_pct <= 60th pct)`. Sub-key on `self_create`: low self_create + high playmaking = the
purest pass-first profile (strongest AST-over). Source: player_roles.parquet. For the AST edge:
prop_pergame RAW assist projection vs the (future) devigged AST prop close; flag |edge|>=threshold;
sign should be OVER for this role (vs UNDER for the score-first creator -- the two files are the two
poles of the same seam).

## Proof method + honest tier
Tier = HYPOTHESIS -> the AST divergence is the project's one near-durable model edge but the leak-free
OOS re-prove vs a devigged AST prop close is OPEN (00-edge-map action #2). Proof: leak-free WF P(over)
of the RAW assist projection vs the devigged AST close, BSS + cluster-robust DM, >=2 corpora;
critically test that the OVER-on-floor-general vs UNDER-on-score-creator SPLIT replicates out of
sample (the split, not just the pooled edge, is what makes it actionable). NEVER bet in the playoffs
(series-form overfit). Keep calibration OFF on AST on purpose (07:189) so the divergence survives.
NULL on PTS/REB/3PM/STL/BLK is expected.
