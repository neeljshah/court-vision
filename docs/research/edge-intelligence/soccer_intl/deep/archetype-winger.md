# ARCHETYPE -- WINGER (wide forward / wide midfielder)

_Part of the edge-intelligence corpus. PLAYSTYLE/ARCHETYPE prior, NOT a person (binding graph rule).
Per-90 rates GROUNDED in data/domains/soccer/espn_player_stats.parquet over rows with minutes>0, ESPN
position codes RM / LM / LF / RF (n=102 starter-rows). ASCII only._

## Role definition (playstyle, not a player)
Wide attacker whose value is carrying, beating the fullback, and crossing/cutting in. Two sub-styles:
- INVERTED WINGER: cuts onto strong foot, shoots more (shifts toward striker shot profile).
- TOUCHLINE / CROSSER: stays wide, assists-leaning, lower shot volume, draws fouls on the dribble.
The corpus RM/LM bucket also catches wide MIDFIELDERS, so this prior is a blended wide-attacker rate.

## Typical per-90 profile (measured, this corpus)
| Stat (canonical) | Winger per-90 | Cross-role context | Note |
|---|---|---|---|
| Shots | 1.40 | below striker (2.31) / AM (2.09), above mids | moderate shot volume |
| Shots On Target | 0.401 | mid | ~29% of shots |
| Goals | 0.123 | mid | rare |
| Assists | 0.167 | tied-highest (with attacking creators) | crossing/cut-back value |
| Fouls (committed) | 1.13 | mid | tracking-back contact |
| Fouls Drawn | 1.23 | high (2nd to AM/striker) | the dribble draws fouls -- key role signal |
| Cards (Y+R) | 0.100 | mid | |
| Offsides | 0.134 | low-mid | far below striker 0.453 |
| Saves | 0.000 | n/a | |

## How it should SHIFT the prior / shrinkage baseline
- The winger baseline sits BETWEEN the holding-mid and striker profiles on shots (1.40) and is HIGH on
  fouls-drawn (1.23). A thin/new winger should shrink toward this, not toward a generic mean that would
  under-price fouls-drawn and over-price offsides.
- WIRING GOTCHA: like striker, wingers split across raw codes (RM, LM, and the rare LF/RF), so
  position_baseline() (player_rates.py:106 exact-string filter) fragments the ~102-row pool. Map RM/LM/
  LF/RF -> one "winger" group before calling player_rate() to recover the full prior.
- Fouls-Drawn is the role's most distinctive, stable signal and the best shrink target to get right for
  this archetype.

## Prop markets it is SOFT on (hypothesis-tier)
- FOULS DRAWN over/under: 1.23/90, role-elevated and rate-stable (dribblers get fouled). Board-wide
  Fouls-Drawn is MARGINAL+ (bss +0.026) and named a graduate candidate (00-edge-map). The winger/
  dribbler segment is exactly where this rate is highest and DFS attention lowest. HYPOTHESIS, best
  non-keeper role candidate alongside CDM fouls-committed.
- SHOTS: moderate lam (1.4); the over-0.5 / over-1.5 ladder is usable for an inverted-winger sub-style.
- ASSISTS: highest-tier rate for the role but still teammate-leaky and rare -> model-view, not a target.

## NOT soft (do not chase)
- Offsides: low for the role (0.134), noisy; CUT.
- Goals/Cards: rare-event noise; CUT.

## Engine wiring (how role should become a shrink target)
- Add RM/LM/LF/RF -> "winger" to the position->archetype map and pass the group to player_rate(); the
  Fouls-Drawn baseline then pools the full wide-attacker prior. Adapter-only (domains/soccer), no kernel
  change.

## Evidence tier
HYPOTHESIS. Fouls-Drawn (winger segment) is the most credible role-conditioned graduate behind keeper
Saves; proof = per-role Fouls-Drawn bss from props_eval --cache (>=PROVEN_BSS 0.05, prop_tiering.py:113)
across >=2 matchday folds + DFS line capture for CLV.
