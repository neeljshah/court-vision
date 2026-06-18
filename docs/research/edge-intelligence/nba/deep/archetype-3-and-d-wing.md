# NBA ARCHETYPE -- 3-AND-D WING (low-usage spacer + perimeter stopper)

_Part of the edge-intelligence corpus. PLAYSTYLE / ROLE prior, NOT a person (binding graph rule).
Grounded in src/sim/basketball_sim.py (zone mix, perim_d, ast suppression) + the role spine
data/cache/team_system/player_roles.parquet (THREE_D_WING is the LARGEST cluster, n=93; also
ROLE_WING n=25, CONNECTOR_WING n=46 sit nearby). See nba/00-edge-map.md + markets-and-props.md.
ASCII. Tiers: HYPOTHESIS / CALIBRATION-PROVEN / CLV-PROVEN._

## Who this is (role, not name)
The catch-and-shoot perimeter defender: LOW usage_pct, LOW self_create (shots are assisted), HIGH
spacing, HIGH perimeter_d, LOW playmaking, LOW creation. The largest archetype on disk
(THREE_D_WING n=93) -> the most common player-game you will price. Defining trait: scoring is
DERIVATIVE (spot-up 3s off others' creation) and value is on the DEFENSIVE end the box score
under-captures.

## Stat profile -> prop ladder

| Prop | Profile for this role | Soft? | Verdict + why |
|---|---|---|---|
| PTS | LOW-MODERATE, BIMODAL (3-heavy: 0 / 3 / 6 / 9). Driven by 3PM, not drives | high (binned) | The PTS distribution is lumpy (multiples of 3) -> the smooth marginal mis-states tail probs; ALT/ladder lines off a stale base are the soft pocket. Main line ~efficient. |
| REB | LOW; perimeter role. R2 0.4224 | low | EFFICIENT; match close. |
| AST | LOW (this role does NOT create). Low playmaking + low self_create | YES (under side) | Lazy lines sometimes float an AST line; this role's structural AST floor makes UNDER safe -- but the line is usually set so low the edge is thin. Lean with the model's low projection. |
| **3PM** | the SIGNATURE stat: HIGH-VOLUME catch-and-shoot, VOLATILE. R2 0.3151, q50 head | **high (the real pocket)** | the ONE atlas-positive stat AND this role's defining output. High spacing + high 3PA share => the fattest 3PM tails of any archetype. Soft books price 3PM lazily and volatility is large => alt-line ladders + main line are the best soft-prop candidate for this role. |
| STL | noise (R2 0.1120) but perimeter_d high | n/a | NON-BETTABLE as a model edge; this role gambles for steals (high perim_d) so the OVER tail exists but is unpredictable. Flag low-confidence. |
| BLK | near-zero floor | n/a | UNDER structurally safe; priced near 0.5. |

## Where the SOFT pocket actually is for this role
1. **3PM main line + alt-ladders** -- this is the archetype where the project's only atlas-positive
   stat (fg3m) and the soft-book laziness coincide. Volatility => fat tails the book under-prices on
   alt rungs (>=3, >=4 3PM). PRIMARY candidate. (HYPOTHESIS -> needs prop feed + leak-free P(over).)
2. **PTS UNDER when the offense's primary creator is OUT** -- this role's scoring is DERIVATIVE; if
   the creator who feeds it is scratched, the assisted-3 supply drops and the book lags (freshness,
   P1). The sim re-routes usage AWAY from this role, so its PTS projection drops while a lazy line
   holds. Inverse of the creator-absorption case.
EFFICIENT for this role: REB, AST main, STL, BLK. CUT.

## How the MC sim encodes this role
- **Low self_create -> assisted scoring:** `p_assist = ast_rate_on_make * clip(1.9*(1-self_create),
  0.5,1.7)` (basketball_sim.py:263). LOW self_create => HIGH assist factor => when this role scores
  it is correctly credited as assisted (a teammate gets the AST), and its OWN AST stays near-floor.
- **Spacing -> z_3 share:** the per-player zone mix routes this role's FGA to z_3 -> the 3PM-heavy,
  bimodal PTS shape emerges natively rather than being imposed.
- **Perimeter defense:** on defense `perim_d_oc = mean(perim_d over on-court)` scales the opponent's
  perimeter make via `DEF_PERIM_SLOPE` clip(0.88,1.08) (line 246-247). A high-perim_d wing on the
  floor suppresses opponent 3-point efficiency -> the role's defensive value flows into the OPPONENT
  total, not its own box score (why STL/BLK can't capture it).
- **Low usage:** `use_per_min ** 1.25` keeps possessions OFF this role -> low FGA/PTS mean.

## Detection recipe (compute in-data)
Flag: `archetype in {THREE_D_WING, ROLE_WING} OR (usage_pct <= 40th pct AND spacing >= 70th pct AND
perimeter_d >= 65th pct AND self_create <= 0.40)`. Source: player_roles.parquet. For the 3PM pocket:
compute the role's 3PA share and recent 3PM volatility; flag alt-ladder rungs where the smooth
marginal CDF diverges from the empirical multiples-of-3 histogram.

## Proof method + honest tier
Tier = HYPOTHESIS. fg3m is the single stat that cleared all-folds atlas validation (00-edge-map:
fg3m -0.003 MAE, 3/3) -> the calibration is the most trustworthy of any prop, but the SOFT-LINE edge
is unproven (no prop feed). Proof: leak-free WF P(over) of the q50 3PM head vs the devigged 3PM prop
close, BSS + DM, >=2 corpora; separately validate the alt-ladder CDF vs realized. Watch the
too-tight-distribution trap (sigma inflation already flagged leaguewide). NULL on PTS-main/REB/AST/
STL/BLK is expected -- do not chase.
