# soccer_intl -- MARKETS AND PROPS (the full surface + which lines are soft)

_Part of the edge-intelligence corpus. The complete market + prop-ladder surface for WC /
international soccer: what we price, what is soft/lazy, and where the gaps are. Grounded in
domains/soccer/prop_engine.py, player_rates.CANON_TO_COLS, scripts/platformkit/prop_edge.py,
the odds providers, and prop_calibration.json. ASCII only._

## Team markets (we do NOT bet; decision-support only)
- 1X2 (home / draw / away), Over/Under total goals (2.5 primary, ladder 1.5/3.5), Asian handicap,
  Both-Teams-To-Score, correct score, double chance.
- Priced by the SEPARATE soccer team model (scoreline_engine.py / predictor.py / markets.py) which
  does NOT feed the prop stack (deep-dive 04 scope note). All are EFFICIENT (cut-list CUT 1) -- kept
  as a calibrated yardstick, never a $-target. Devig via shin.py; CLV via clv_ledger.py.

## Player props -- the surface we actually model (the only candidate pocket)

The engine produces exactly 10 canonical stats (`player_rates.canonical_stats()`), each a per-90
rate x expected-minutes -> Poisson/NB count distribution -> p_over(line) + an alt-line ladder
(prop_engine.py:78, prop_engine.py:99). Mapping to raw ESPN columns (CANON_TO_COLS, player_rates.py:35):

| Canonical prop | Raw ESPN col(s) summed | Typical lam | Distribution shape | Measured bss (n=662) | Soft-line note |
|---|---|---|---|---|---|
| Saves | saves | ~1.5-4 (keepers) | NB (overdispersed) | **+0.3365 proven** | Books/DFS post a Saves line; near-deterministic given shots faced -> our edge is on shot-volume projection, not finishing. |
| Shots (total) | totalShots | ~1-3 | NB | +0.0076 marginal | High-volume, commonly offered on DFS; lazy lines plausible for non-stars. |
| Shots On Target | shotsOnTarget | ~0.5-1.5 | NB | +0.0049 marginal | Should be jointly modeled with Shots (gap). |
| Fouls (committed) | foulsCommitted | ~1-2 | NB | +0.0339 marginal | Defenders/DMs have stable foul rates; best graduate candidate. |
| Fouls Drawn | foulsSuffered | ~1-2 | NB | +0.026 marginal | Dribblers/forwards; opponent-fouls allowed-attribution available. |
| Goals | totalGoals | ~0.1-0.5 | Poisson/NB | -0.0252 weak | Rare-event; the .5-line is near-coin-flip noise. |
| Assists | goalAssists | ~0.1-0.3 | Poisson | -0.074 weak | Teammate-dependent leak. |
| Goal+Assist | totalGoals+goalAssists | ~0.2-0.6 | Poisson/NB | -0.0067 weak | Independent-marginal sum; correlation unmodeled. |
| Cards | yellowCards+redCards | ~0.1-0.3 | Poisson | -0.1076 weak | Worst skill; irreducible per-match noise; ref/game-state driven. |
| Offsides | offsides | ~0.1-0.4 | Poisson/NB | -0.0155 weak | Low-volume noise. |

## The alt-line ladder
`prop_distribution` exposes `p_over(line)` for any half-integer line; the board uses the .5 line
nearest lam for backtesting (props_eval.py loop) and can price the offered DFS/book line directly.
Half-integer lines never push (prop_engine.py:78). Two-pass dispersion: Poisson to learn lam, then
re-distribute with NB r = lam/(phi-1) so a too-tight Poisson can't fabricate tail edges
(prop_edge.py:154-165). This matters most on the longer lines of the ladder (over 2.5 shots, over
4.5 saves) where Poisson tails are absurdly thin.

## Which lines are SOFT / lazy (the beatable surface, hypothesis-tier)
- **DFS pick'em (PrizePicks / Underdog):** the primary soft pocket (edge-theory.md P1). Fixed-payout,
  no two-way close -> structurally CANNOT move to kill a mispriced projection. WC props for
  non-star, rotation, and lower-profile-nation players are the most likely to be lazily set off a
  generic projection. HYPOTHESIS until P(over) calibration + line-movement prove it.
- **Saves on backup/rotation keepers and minnow-nation keepers:** the proven-calibration stat
  crossed with low bookmaker attention -- the single most plausible beatable cell. HYPOTHESIS.
- **Fouls/Fouls-Drawn for role players (CDM, fullbacks, dribbling wingers):** stable rate, low
  attention, positive bss. HYPOTHESIS once it graduates to proven.

## Which lines are NOT soft (do not chase)
- Star-player Goals/SOT/Shots on major books: increasingly efficient (04 sec 7). Our measured skill
  there is ~null/negative anyway.
- Any team mainline: sharp (cut-list CUT 1).

## What we price vs the gaps
- WE PRICE: all 10 canonical props as independent NB/Poisson marginals, opponent-adjusted (mostly
  no-op), club-prior-lifted, dispersion-widened, tier-labelled.
- GAPS: (1) NO joint/correlated pricing -- Shots, SOT, G+A are independent marginals so SGP-style
  correlated props (04 sec 6 #10, edge-theory.md P5) are unpriceable today; (2) NO closing-line /
  movement capture -> no CLV, no DFS-movement proof; (3) minutes projection is the weakest link and
  is bypassed in the backtest (realized minutes fed in), so the priced number is optimistic vs what
  we score (04 sec 5).
