# ARCHETYPE -- FULLBACK / WING-BACK (RB / LB / RWB / LWB)

_Part of the edge-intelligence corpus. PLAYSTYLE/ARCHETYPE prior, NOT a person (binding graph rule).
Per-90 rates GROUNDED in data/domains/soccer/espn_player_stats.parquet over rows with minutes>0, ESPN
position codes RB / LB (n=80 starter-rows). ASCII only._

## Role definition (playstyle, not a player)
Wide defender who also provides width in attack. Defining prop trait: the HIGHEST fouls-committed of any
role (chases wide attackers, tactical fouls in transition) plus card exposure. Sub-styles:
- DEFENSIVE FULLBACK: foul/card-heavy, minimal attacking output.
- ATTACKING WING-BACK: more shots/assists/fouls-drawn, profile bends toward winger.

## Typical per-90 profile (measured, this corpus)
| Stat (canonical) | Fullback per-90 | Cross-role context | Note |
|---|---|---|---|
| Fouls (committed) | 1.345 | HIGHEST of all roles | chasing wingers + transition fouls |
| Fouls Drawn | 0.901 | mid | overlapping runs drawn fouls |
| Cards (Y+R) | 0.161 | HIGHEST of all roles | foul rate -> bookings |
| Shots | 0.579 | low | occasional from wide/cutback |
| Shots On Target | 0.148 | low | |
| Goals | 0.040 | very low | |
| Assists | 0.108 | mid | crossing value |
| Offsides | 0.108 | low | |
| Saves | 0.000 | n/a | |

Avg minutes 84 (subbed for fresh legs late) -- slightly more minutes-stable than the forward roles.

## How it should SHIFT the prior / shrinkage baseline
- Role-defining shift: FOULS-COMMITTED to the role MAX (1.345) and CARDS to the role MAX (0.161). A
  generic-mean shrink target badly under-prices both. The fullback foul baseline is the highest legit
  shrink target in the dataset.
- WIRING GOTCHA: RB and LB are separate raw codes (40 + 40 rows); pool RB/LB/RWB/LWB -> one "fullback"
  group before position_baseline() (player_rates.py:106) to use the full ~80-row foul prior. Without
  pooling the baseline halves into two 40-row buckets (still usable but noisier).

## Prop markets it is SOFT on (hypothesis-tier)
- FOULS COMMITTED over/under: role-MAX rate (1.345/90), stable and role-driven. Joins the holding-mid
  and AM-fouls-drawn as the trio of credible foul-family HYPOTHESIS cells. Board Fouls bss +0.0339
  (MARGINAL); the fullback segment is where the rate is highest. HYPOTHESIS.
- FOULS DRAWN: mid (0.901), attacking-wing-back sub-style only; weaker than committed.

## NOT soft (do not chase)
- CARDS: role-elevated (highest, 0.161) and tempting, BUT board-worst skill (bss -0.1076, CUT 4) --
  per-match card is irreducible Bernoulli + ref/game-state. Even at the role max, do NOT bet. Model-view.
- Shots/SOT/Goals: low-volume role-noise; CUT.

## Engine wiring (how role should become a shrink target)
- Map RB/LB/RWB/LWB -> "fullback"; pass group to player_rate() so the foul baseline pools fully. Cards,
  despite the role signal, must keep the tier-system demotion (calibration_rank_key, prop_tiering.py:167)
  so they cannot top the board. Adapter-only.

## Evidence tier
HYPOTHESIS. Fouls-committed (fullback segment, the role MAX rate) is a strong foul-family graduate
candidate alongside holding-mid. Cards are explicitly CUT despite the role-high rate -- a good example of
"role-elevated rate != edge" when the underlying stat has measured-negative skill. Proof = per-role Fouls
bss from props_eval --cache + DFS line capture for CLV.
