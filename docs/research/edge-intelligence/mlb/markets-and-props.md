# MLB MARKETS + PROP LADDER -- the full surface, what we price, what is soft
_Part of the edge-intelligence corpus. The complete MLB market surface, which we already price
coherently, and which lines are lazily set. Grounds in domains/mlb/markets.py + prop_engine_mlb.py.
ASCII only._

## Team market surface (priced, coherent, EFFICIENT)
`domains/mlb/markets.full_market_surface` (`markets.py:193`) re-reads ONE NegBinom joint matrix for
every shape, anchored to the Elo win-prob (`predictor.predict` `_anchor_nb_tiesplit` preserves the
run sum). So all of these share one win-prob and are mutually coherent:

| Market | Source | Note |
|---|---|---|
| Moneyline (home/away) | tie-split Elo p_home | The single source of truth; matches close. |
| Run line +/-1.5 (margin>=2) + alts (1,2,3) | `run_line_surface` (`markets.py:98`) | From the joint margin distribution. |
| Game total O/U + alternates | marginal total dist | Any line/alt from the total marginal. |
| Team totals (3.5/4.5/5.5 + alts) | `team_total_surface` (`markets.py:143`) | Sum-coherent: home+away team total == game lambdas. |
| First-5 (F5) ML / total | `markets.py:162`, `F5_FRACTION=0.521` | **in-sample fraction** (empirical on 27,983 games, `:46`); flagged, OOS deferred. |

Verdict: this is a genuinely coherent surface Elo alone cannot emit, with FITTED over-dispersion
(`negbinom_engine.fit_dispersion_first_half`, closes the W149 hardcoded-r gap). But it is EFFICIENT --
keep as calibrated decision-support, not a $-source (cut-list CUT 1).

## Player-prop ladder (priced as machinery, UNVALIDATED, mostly stranded)
`prop_engine_mlb.prop_distribution` -> `lam = rate x exposure` -> Poisson/NB pmf (shared with soccer
via `_make_p_over`) -> `p_over(line)`; `prop_ladder` (`:166`) returns the alt-line ladder. The canonical
stats (`player_rates_mlb.MLB_CANON`):

### Batter props (exposure = PA)
| Stat | Shape soundness | Edge verdict |
|---|---|---|
| **Hits** | sound (per-PA Bernoulli success count, low counts) | PUSH-candidate; measure first |
| **Walks** | sound (per-PA Bernoulli event) | PUSH-candidate |
| **Batter Strikeouts** | sound (per-PA Bernoulli) | PUSH-candidate |
| Total Bases | ROUGH -- weighted sum (1B/2B/3B/HR), Poisson mis-fits variance/tail | CUT-as-edge; compound model needed |
| RBIs | ROUGH -- context-driven (baserunners, order); teammate-leak | CUT-as-edge |
| Runs | ROUGH -- context-driven | CUT-as-edge |
| Hits+Runs+RBIs | ROUGH -- sum of 3 correlated stats; understates tail | CUT-as-edge |
| Home Runs | very low rate, lumpy | display-only |
| Stolen Bases | very low rate, lumpy | display-only |

### Pitcher props (exposure = BF, except Outs per-start)
| Stat | Shape soundness | Edge verdict |
|---|---|---|
| **Pitcher Strikeouts** | soundest (large BF -> ~Poisson, mildly over-dispersed -> the `dispersion` r lever) | TOP PUSH-candidate |
| **Outs** (per-start, `SHRINK_K_START=3.0`) | cleanest (exposure-natural, modelled directly) | TOP PUSH-candidate |
| **Hits Allowed** | sound (per-BF success count) | PUSH-candidate |
| **Walks Allowed** | sound (per-BF Bernoulli) | PUSH-candidate |
| Earned Runs | rough (low count, sequence-dependent) | model-view |

## Which lines are soft / lazy (where the pocket is)
- **DFS pick'em (PrizePicks/Underdog)** on non-star players and per-opportunity stats (a backup
  catcher's Hits line, a 5th-starter's Outs/Ks) are set lazily off a stale model -- the P1 pocket.
  Note: DFS pick'em has no two-way close, so CLV-vs-close is undefined; prove via P(over)-vs-realized
  calibration + realized ROI at fixed payout + DFS-line MOVEMENT (per edge-theory.md).
- **Star pitcher Ks** and **liquid star props** at major books are sharp -- efficient, do not chase.
- **F5 / team-total alts** on soft books can lag SP news; minor pocket, execution-bound.

## What we price vs gaps
- We PRICE: every team market (coherently), every canonical prop MARGINAL (independently).
- GAPS: (a) NO joint/correlation model -> any same-player or same-game prop parlay is mispriced
  (limitation #7); (b) the prop `dispersion` r is never fit -> Poisson tails too tight on Ks
  (limitation #5); (c) NO park / opposing-pitcher / platoon adjustment in the prop rate
  (limitation #6) -- the rate is a coarse pooled league baseline; (d) no live delivery path
  (`prop_distribution` is stranded -- only `props_eval_mlb` reads it).
