# ARCHETYPE -- HOLDING / CENTRAL MIDFIELDER (#6 / #8 / DM)

_Part of the edge-intelligence corpus. PLAYSTYLE/ARCHETYPE prior, NOT a person (binding graph rule).
Per-90 rates GROUNDED in data/domains/soccer/espn_player_stats.parquet over rows with minutes>0, ESPN
position codes DM / CM / CM-L / CM-R / M (n=67 starter-rows). ASCII only._

## Role definition (playstyle, not a player)
The midfield engine/screen in front of the back line. Defining trait for props: a STABLE, elevated
fouls-committed rate (the tactical-foul role) with low shot/goal output. Sub-styles:
- DESTROYER / #6 (DM): foul-heaviest, card-prone, lowest attacking output.
- BOX-TO-BOX / #8 (CM): more shots/assists, mid foul rate.

## Typical per-90 profile (measured, this corpus)
| Stat (canonical) | Holding-mid per-90 | Cross-role context | Note |
|---|---|---|---|
| Fouls (committed) | 1.08 | high (defenders/CDMs lead) | the role's stable, predictable signal |
| Fouls Drawn | 0.917 | mid | turning in central traffic |
| Shots | 0.934 | low (vs AM 2.09) | mostly from distance |
| Shots On Target | 0.197 | low | poor conversion of long-range |
| Goals | 0.082 | low | rare |
| Assists | 0.098 | low-mid | |
| Cards (Y+R) | 0.131+0.016red | among highest | tactical-foul -> bookings |
| Offsides | 0.033 | lowest outfield | stays behind the line |
| Saves | 0.000 | n/a | |

## How it should SHIFT the prior / shrinkage baseline
- The role-defining shift is FOULS-COMMITTED UP (1.08) and Offsides/Shots DOWN. A new CDM shrunk toward
  a generic mean would UNDER-price fouls-committed -- the one stat where this role is most predictable.
- Foul rate is the most stable per-role rate in soccer (tactical, role-driven not form-driven), making
  it the best-behaved shrink target: thin-data shrinkage toward the holding-mid foul baseline is
  trustworthy rather than noisy.
- WIRING GOTCHA: DM/CM/CM-L/CM-R/M are five raw codes (and DM has only 2 rows alone); MUST be pooled to
  one "holding_mid" group before position_baseline() (player_rates.py:106) or the foul baseline collapses
  to near-empty per-string buckets.

## Prop markets it is SOFT on (hypothesis-tier)
- FOULS COMMITTED over/under: THE role's edge candidate. Board-wide Fouls is the best non-Saves market
  (bss +0.0339, MARGINAL, "best graduate candidate" markets-and-props.md). The CDM/holding-mid segment
  is where the rate is highest AND most stable AND least scrutinized by DFS -> the most plausible
  beatable foul cell. HYPOTHESIS, strongest non-keeper / non-AM-fouls-drawn candidate.
- CARDS: elevated for the role (0.147 combined) BUT cards are board-WORST (bss -0.1076, irreducible
  Bernoulli + ref/game-state noise, 00-edge-map CUT 4). Even role-elevated, do NOT bet. Model-view only.

## NOT soft (do not chase)
- Shots/SOT/Goals/Offsides for a CDM: all low-volume role-noise; CUT.
- Cards: tempting (role-elevated) but measured-negative skill; explicitly CUT.

## Engine wiring (how role should become a shrink target)
- Map DM/CM*/M -> "holding_mid"; pass group to player_rate(). The Fouls baseline then pools the full
  ~67-row prior. Pair with opponent fouls-drawn-allowed attribution (team_defense.py:72-85) as data
  grows. Adapter-only.

## Evidence tier
HYPOTHESIS. Fouls-committed (holding-mid segment) is the most credible counting-stat graduate after
keeper Saves -- stable role rate + positive board bss + low DFS attention. Proof = per-role Fouls bss
from props_eval --cache (>=0.05) across >=2 folds + DFS line capture for CLV.
