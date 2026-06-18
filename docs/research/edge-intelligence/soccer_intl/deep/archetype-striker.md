# ARCHETYPE -- STRIKER (central forward / #9)

_Part of the edge-intelligence corpus. PLAYSTYLE/ARCHETYPE prior, NOT a person (binding graph rule).
Describes the role profile that should shift the prop prior + shrinkage baseline. Per-90 rates are
GROUNDED in data/domains/soccer/espn_player_stats.parquet (1241 rows, 24 WC events, every player 1 WC
match) over rows with minutes>0, ESPN position codes F / CF / CF-L / CF-R / RCF (n=79 starter-rows).
ASCII only._

## Role definition (playstyle, not a player)
The central attacking reference point: leads the line, makes the most off-ball runs into the box,
takes the most shots and is offside most often. Distinguish two sub-styles that matter for priors:
- POACHER / TARGET: low shot-volume, high conversion, fewest touches outside the box.
- PRESSING / ALL-ACTION 9: higher fouls-committed (defends from the front) + fouls-drawn (holds up play).

## Typical per-90 profile (measured, this corpus)
| Stat (canonical) | Striker per-90 | Cross-role context | Note |
|---|---|---|---|
| Shots | 2.31 | highest of all outfield roles | the defining stat; lam ~2.3 -> the over-1.5 / over-2.5 ladder is live |
| Shots On Target | 0.89 | tied-highest (with AM) | ~38% of shots on target |
| Goals | 0.378 | highest by far (next: AM 0.214) | still rare-event; .5 line near coin-flip |
| Assists | 0.136 | mid | teammate-dependent leak |
| Fouls (committed) | 1.22 | mid-high | pressing/hold-up contact |
| Fouls Drawn | 1.33 | high | back-to-goal hold-up draws fouls |
| Cards (Y+R) | 0.030 | lowest outfield | strikers booked least |
| Offsides | 0.453 | highest of all roles | the signature striker stat |
| Saves | 0.000 | n/a | never |

Shot distribution is OVERDISPERSED: attacking-role shots mean 1.89, var 2.74, var/mean 1.45 (n=122) --
confirms the NB (not Poisson) shape the engine uses (prop_edge.py:154-165 two-pass dispersion).

## How it should SHIFT the prior / shrinkage baseline
position_baseline() (player_rates.py:93) pools a minutes-weighted per-90 over all rows whose raw
`position` string matches EXACTLY. WIRING GOTCHA: ESPN encodes strikers as several distinct strings
(F, CF-L, CF-R, RCF), so the baseline as-coded fragments the striker pool into thin per-string buckets
instead of one ~79-row striker prior. Mapping these codes to ONE "striker" baseline group is the single
highest-value prior fix for this role (see "engine wiring" below).
- For a thin/new striker (n_eff < SHRINK_K=3, the common WC case of 1 match), the shrink target should
  be the STRIKER baseline above (Shots ~2.3, SOT ~0.9, Offsides ~0.45), NOT a generic all-position mean
  that would badly under-price shots and offsides.
- The blend is num = n_eff*raw + SHRINK_K*baseline over (n_eff+SHRINK_K) (player_rates.py:255). With the
  correct striker baseline a 1-match striker is pulled toward ~2.3 shots, the right pocket.

## Prop markets it is SOFT on (hypothesis-tier)
- SHOTS over/under: highest-volume stat for the role; lam ~2.3 gives an informative .5-ladder. Marginal
  on the board overall (bss +0.0076) but the STRIKER cell is where shot-volume is most predictable and
  DFS lines for non-star strikers from minnow nations are most plausibly lazy. HYPOTHESIS.
- SHOTS ON TARGET: lam ~0.9; should be JOINTLY modeled with Shots (known gap, markets-and-props.md). The
  Shots->SOT conditional is a role-stable ~38% here; an unmodeled correlation pocket.
- OFFSIDES over 0.5: striker-specific signal (0.453/90, 4x a defender). Board-wide bss is negative
  (-0.0155) but that pools all roles; segmented to strikers the rate is high enough that the .5 line
  could be soft. Treat as HYPOTHESIS, validate per-role before crediting.

## NOT soft (do not chase)
- GOALS .5 line: even at the role-max 0.378/90 this is a poor discriminator; star-striker goals are
  efficient on major books (00-edge-map CUT). Model-view only.
- Assists: teammate-leak, rare; CUT.

## Engine wiring (how role should become a shrink target)
1. Add a position->archetype map keyed on the raw ESPN strings (F/CF*/RCF -> "striker") and pass the
   GROUP as the `position` arg to position_baseline() / player_rate() so the baseline pools the full
   ~79-row striker prior, not a 6-row "RCF" sliver. This is a domains/soccer adapter change, not a
   kernel change.
2. Until then the inferred-position path (player_rate, player_rates.py:189-192) takes the player's own
   modal raw code, so striker baselines stay fragmented and shots/offsides get under-shrunk.

## Evidence tier
HYPOTHESIS for every edge claim above. The only CALIBRATION-PROVEN soccer market is Saves (keeper),
which strikers never produce. Shots/SOT/Offsides for strikers are the most plausible role-segmented
graduates; proof requires per-role bss from props_eval --cache plus DFS line capture for CLV.
