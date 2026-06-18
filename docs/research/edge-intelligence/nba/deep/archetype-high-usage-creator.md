# NBA ARCHETYPE -- HIGH-USAGE CREATOR (on-ball scoring engine)

_Part of the edge-intelligence corpus. PLAYSTYLE / ROLE prior, NOT a person (binding graph rule).
Grounded in src/sim/basketball_sim.py (USAGE_CONCENTRATION, _roles, _possession), the role spine
data/cache/team_system/player_roles.parquet (archetypes WING_CREATOR n=44, SCORING_GUARD n=18,
OFF_GUARD n=23, BENCH_SCORER n=21 cluster here), and nba/markets-and-props.md + 00-edge-map.md.
ASCII. Tiers: HYPOTHESIS / CALIBRATION-PROVEN / CLV-PROVEN._

## Who this is (role, not name)
The primary on-ball offensive option: high usage_pct, high self_create, moderate-to-high
playmaking, high scorer_pct. In the role spine this is the high-creation tail: creation 75th pct
~0.74, usage_pct top decile, self_create at/above the 0.50 cap. Maps to clusters WING_CREATOR,
SCORING_GUARD, OFF_GUARD, plus high-usage BENCH_SCORER (sixth-man scorer). The defining trait is
that possessions FUNNEL to this role and the role MAKES ITS OWN SHOT (low assisted-FG share).

## Stat profile -> prop ladder (which props are soft, which are efficient)

| Prop | Profile for this role | Soft? | Verdict + why |
|---|---|---|---|
| PTS | HIGH mean, HIGH variance (usage-driven). Holdout R2 0.5105 leaguewide | medium | EFFICIENT at ceiling (00-edge-map): match close. Variance => fat over/under tails; the soft-book pocket is ALT-line ladders priced off a stale base, not the main line. |
| AST | MODERATE, and the divergence depends on playmaking. A SCORING creator (low playmaking) is over-credited by lazy lines that conflate "ball-dominant" with "playmaker" | YES (the P1 edge) | BEATABLE (narrow). This is exactly the documented ~+7% AST divergence (00-edge-map row AST). KEEP RAW, never playoffs. For a SCORE-FIRST creator, lean UNDER assists; for a PLAYMAKING creator lean with the model. |
| REB | LOW-MODERATE; perimeter creators rebound little. R2 0.4224 | low | EFFICIENT; match close. |
| 3PM | HIGH-VOLUME but volatile; q50 head. R2 0.3151 | high | the ONE atlas-positive stat. Volatility + lazy soft-book lines = candidate, modest. Creators who pull-up 3 (high spacing) carry fatter 3PM tails -> alt-line ladder mispricing. |
| STL | noise (R2 0.1120) | n/a | NON-BETTABLE. Flag low-confidence; do NOT price as edge for this role. |
| BLK | near-noise for perimeter role (R2 0.2166, sigma x1.86 too tight) | n/a | guards/wings here have ~0 blk floor; UNDER is structurally safe but priced near 0.5 lines. |

## Where the SOFT pocket actually is for this role
1. **AST UNDER on a SCORE-FIRST creator** (high usage + LOW playmaking). Lazy lines treat usage as
   assists; the model separates self_create from playmaking, the book often does not. (HYPOTHESIS;
   this is the leak-free-OOS re-prove target in get-to-edge-plan.)
2. **PRA / PA combo redistribution** when a co-creator is OUT: this role absorbs vacated usage, and
   soft books lag the injured-teammate redistribution (markets-and-props.md "combos"). The sim's
   out_ids re-route (basketball_sim.py:97) prices it; the book lags = freshness pocket (P1).
3. **3PM alt-ladders** for pull-up-heavy creators (high spacing attribute).
EFFICIENT for this role: PTS main line, REB, STL, BLK. CUT $-hunt there.

## How the MC sim encodes this role
- **Usage routing:** `_possession` draws the shooter with weight `use_per_min ** USAGE_CONCENTRATION`
  (=1.25, basketball_sim.py:36,213). A high-usage role gets superlinearly MORE possessions than a
  flat per-minute split -> correctly fat PTS/FGA mean. This is the single most important encoding.
- **Self-create -> assist suppression:** when this role scores, `p_assist` is scaled by
  `clip(1.9*(1-self_create),0.5,1.7)` (line 263). High self_create => the make is LESS often
  assisted => the role's own AST is NOT inflated and teammates are not over-credited. This is the
  structural reason the sim can express "ball-dominant but not a playmaker."
- **Playmaking -> feeder network:** when teammates score, this role is picked as assister by the real
  PBP `assist_net` (line 266-271). A high-playmaking creator shows up as a feeder; a score-first
  creator does not -> the AST divergence is a sim-native quantity, not a bolt-on.
- **Spacing/rim_pressure -> zone mix:** per-player zone shot rates set 3PA vs rim share; a pull-up
  creator's `spacing` lifts z_3 frequency.

## Detection recipe (compute in-data)
Flag this role per player-game: `usage_pct >= league 80th pct AND self_create >= 0.50 AND
scorer_pct >= 75th pct`. Sub-split playmaking: `playmaking < 0.42 (median)` => SCORE-FIRST (AST-under
candidate); `>= 0.66 (75th)` => PLAYMAKING-creator (AST-with-model). Source: player_roles.parquet.
Then for AST: prop_pergame raw assist mean vs the (future) devigged prop close; flag |edge|>=threshold.

## Proof method + honest tier
Tier = HYPOTHESIS (AST divergence is documented but the leak-free OOS re-prove vs a devigged prop
close is the OPEN action in 00-edge-map). Proof: leak-free walk-forward, score the RAW assist
projection's P(over) vs the devigged prop close with BSS + cluster-robust DM; require >=2 corpora.
Blocker: no keyless prop feed wired yet (top get-to-edge gap). NULL on PTS/REB/STL/BLK is the
expected, honest result -- do not chase. Never bet this role's AST in the playoffs (series-form
overfit, 00-edge-map note).
