# ARCHETYPE -- GOALKEEPER (#1)

_Part of the edge-intelligence corpus. PLAYSTYLE/ARCHETYPE prior, NOT a person (binding graph rule).
Per-90 rates GROUNDED in data/domains/soccer/espn_player_stats.parquet over rows with minutes>0, ESPN
position code G (n=48 starter-rows). ASCII only._

## Role definition (playstyle, not a player)
The only role that produces Saves. For prop purposes a keeper's output is almost entirely SAVES, which is
near-deterministic given shots-on-target FACED and minutes. The relevant style axis is the TEAM in front,
not the keeper: a keeper behind a weak/minnow-nation defense faces more shots -> more saves. Sub-styles
(sweeper-keeper vs line-keeper) barely move the modeled stats; ignore for priors.

## Typical per-90 profile (measured, this corpus)
| Stat (canonical) | Keeper per-90 | Note |
|---|---|---|
| Saves | 2.611 | THE keeper stat; lam ~1.5-4 depending on opponent shot volume |
| Fouls Drawn | 0.232 | low (fouled when claiming crosses) |
| Cards (Y) | 0.021 | rare (time-wasting) |
| Fouls (committed) | 0.021 | ~never |
| Shots / SOT / Goals / Assists / Offsides | 0.000 | never |

Saves are OVERDISPERSED: mean 2.58, var 4.38, var/mean 1.69, range 0-9 (n=48). This confirms NB (not
Poisson) is required (prop_edge.py:154-165); a Poisson at lam 2.6 would fabricate too-thin tails and
mis-price the over-3.5 / over-4.5 ladder.

## How it should SHIFT the prior / shrinkage baseline
- For a thin/new keeper the shrink target MUST be the keeper Saves baseline (~2.6/90), NOT a generic mean
  (~0, since no other role saves). The position_baseline() exact-string filter on "G" (player_rates.py:106)
  ALREADY isolates keepers cleanly -- the ONE role where the as-coded baseline is correct without an
  archetype map (G is a single code). This is why Saves is the cleanest-calibrated market.
- The keeper's OWN save rate is a weak driver; the dominant driver is OPPONENT shot-on-target volume. The
  prior should ideally shrink toward (keeper-minutes-share x opponent-SOT-faced), not the keeper's raw
  save count. The engine does not yet condition Saves on opponent shot volume -- the key open lever.

## Prop markets it is SOFT on
- SAVES over/under: the ONLY CALIBRATION-PROVEN soccer market (bss +0.3365, brier 0.01755, ece 0.004,
  n=662; 00-edge-map). READ SKEPTICALLY: deep-dive 04/06 flag it as partly STRUCTURAL -- saves are nearly
  a deterministic function of shots faced, so the .5-line backtest is near-trivial. The genuine edge, if
  any, is on SHOT-VOLUME PROJECTION (how many SOT the opponent generates), NOT on save finishing.
  - SOFTEST CELL (hypothesis): Saves on BACKUP/ROTATION keepers and MINNOW-NATION keepers -- proven-
    calibration stat crossed with low DFS attention (markets-and-props.md). The single most plausible
    beatable cell on the whole soccer board. HYPOTHESIS until DFS line + CLV capture exists.

## NOT soft (do not chase)
- Every other keeper stat (fouls, cards) is ~0 and noise; CUT.
- Saves as a CLAIMED $-edge: NOT proven. It is well-calibrated and "not worse than the close," but with
  ~45 keeper-rows with saves>0 and ZERO closing-line capture (prop_line_history.jsonl ~1 row), CLV is
  unproven. Calibration-proven, NOT CLV-proven.

## Engine wiring (how role should become a shrink target)
- Keeper baseline already works (single "G" code). The high-value lever is conditioning the Saves prior
  on OPPONENT expected-SOT: replace/augment the keeper's own save-per-90 with team-defense shots-faced
  (team_defense.py is plumbed but per-opponent depth ~1-3 matches -> shrinks to 1.0 today; re-test as
  data grows). Adapter-only.

## Evidence tier
CALIBRATION-PROVEN (suggestive) for Saves on the aggregate; HYPOTHESIS for the backup/minnow-keeper soft
cell and for any opponent-SOT conditioning lift. CLV-PROVEN: NONE (no closing-line capture). The honest
line: Saves is the board's only real OOS skill, it is partly structural, and it is not yet a profit
engine.
