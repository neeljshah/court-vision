# ARCHETYPE -- ATTACKING MIDFIELDER (#10 / advanced playmaker)

_Part of the edge-intelligence corpus. PLAYSTYLE/ARCHETYPE prior, NOT a person (binding graph rule).
Per-90 rates GROUNDED in data/domains/soccer/espn_player_stats.parquet over rows with minutes>0, ESPN
position codes AM / AM-L / AM-R (n=43 starter-rows). ASCII only._

## Role definition (playstyle, not a player)
The creative hub operating between the lines: high shot volume from the edge of the box, the most
fouls-DRAWN of any role (carries into traffic), and a prime assist source. Sub-styles:
- SHADOW-STRIKER #10: shot/goal-leaning, profile bends toward striker.
- DEEP PLAYMAKER #10: assist-leaning, fewer shots, draws fouls turning in midfield.

## Typical per-90 profile (measured, this corpus)
| Stat (canonical) | AM per-90 | Cross-role context | Note |
|---|---|---|---|
| Shots | 2.09 | 2nd only to striker (2.31) | high-volume shooter |
| Shots On Target | 0.855 | tied-highest with striker | ~41% of shots -- best on-target ratio |
| Goals | 0.214 | 2nd to striker | rare-event still |
| Assists | 0.160 | top-tier | the creative signal |
| Fouls (committed) | 0.695 | LOWEST outfield | does little defensive contact |
| Fouls Drawn | 1.63 | HIGHEST of all roles | the signature #10 stat |
| Cards (Y+R) | 0.053 | low | rarely booked |
| Offsides | 0.214 | mid | |
| Saves | 0.000 | n/a | |

Smallest archetype sample (n=43) and shortest avg minutes (78) -- treat the baseline as the noisiest of
the outfield groups; lean on club priors (club_prior path, player_rates.py:203) harder for #10s.

## How it should SHIFT the prior / shrinkage baseline
- Two role-defining shifts vs a generic mean: Fouls-Drawn UP (1.63, highest) and Fouls-Committed DOWN
  (0.695, lowest). A new #10 shrunk toward a pooled mean would be badly mis-set on BOTH foul stats.
- SOT is high relative to shots (0.855/2.09 ~41%): the Shots->SOT conditional is steepest for this role,
  the strongest argument for joint Shots+SOT modeling (currently independent marginals -- known gap).
- WIRING GOTCHA: AM/AM-L/AM-R are three raw codes; map to one "attacking_mid" group before
  position_baseline() (player_rates.py:106) or the n=43 prior splits into ~14-15-row slivers.

## Prop markets it is SOFT on (hypothesis-tier)
- FOULS DRAWN over/under: role-MAX at 1.63/90. Same logic as winger but stronger -- this is the cell
  where Fouls-Drawn (board MARGINAL+, bss +0.026) is most rate-elevated. Top role-conditioned HYPOTHESIS.
- SHOTS ON TARGET: high lam (0.855) AND high conversion; the most informative SOT cell. The unmodeled
  Shots/SOT correlation here is a concrete SGP-style pocket (edge-theory P5) once joint pricing exists.
- SHOTS: lam ~2.1; over-1.5 ladder live.

## NOT soft (do not chase)
- Fouls COMMITTED for a #10: rate is the lowest outfield (0.695) and the value is in the DEFENDER/CDM
  segment, not here -- do not bet AM fouls-committed.
- Goals/Assists .5 lines: rare-event/teammate-leak; model-view only.

## Engine wiring (how role should become a shrink target)
- Map AM* -> "attacking_mid"; pass group to player_rate(). Given the thin n=43 + short minutes, ALSO
  ensure the club_prior blend is populated for #10s (player_rates.py:203, CLUB_WEIGHT_CAP=20) so the
  prior is club-form-backed rather than 1-WC-match noise.

## Evidence tier
HYPOTHESIS. Fouls-Drawn (AM segment) is the single highest role-conditioned rate in the corpus and the
most promising graduate after keeper Saves; smallest-n role, so require multi-fold + club-prior backing
before crediting. Proof = per-role bss from props_eval --cache + DFS capture for CLV.
