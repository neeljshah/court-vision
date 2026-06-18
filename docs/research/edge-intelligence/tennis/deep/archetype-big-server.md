# TENNIS ARCHETYPE -- BIG SERVER (serve-dominant, hold-heavy, low break-conversion)

_Part of the edge-intelligence corpus. PLAYSTYLE / ROLE prior, NOT a person (binding graph rule).
Grounded in data/domains/tennis/match_stats.parquet (p1_ace_rate, 1st_in/1st_win, SvGms, bpFaced) +
matches.parquet surface dist + domains/tennis/match_engine_holds.py / asof_hold.py / markets.py.
See tennis/00-edge-map.md + markets-and-props.md. ASCII. Tiers: HYPOTHESIS / CALIBRATION-PROVEN /
CLV-PROVEN._

## Who this is (style, not name)
The serve-dominant player: HIGH ace_rate (well above the leaguewide mean 0.0603), HIGH 1st-serve win%
(above mean 0.681), HIGH hold%, but ORDINARY-to-LOW return / break-point conversion. Wins by holding
serve relentlessly and converting the rare break or the tie-break. Defining traits in-data:
`ace_rate >> 0.06`, `1st_win_pct >> 0.68`, `bp_saved_pct` high (mean 0.558), but few break chances
created on return.

## Serve/return profile -> markets

| Market | Profile for this style | Soft? | Verdict + why |
|---|---|---|---|
| **Aces O/U (player)** | the SIGNATURE: very high ace count (mean ~4.6, big servers double it). Buildable: aces ~ NegBinom(svpt*surface_ace_rate) | **YES -- the P1 candidate** | the single most promising soft prop in tennis. Books post a flat ace line that ignores OPPONENT return depth + SURFACE. A big server on a fast surface vs a weak returner = under-priced ace OVER. BLOCKED: no ace line scraped, no ace model wired (markets-and-props.md). |
| Total GAMES O/U (match) | LEANS OVER: two strong holders => long sets, more tie-breaks, more games | YES on lower tiers | big-server-vs-big-server is the canonical GAMES-OVER profile (few breaks => sets go deep). Soft on ATP-250/Challenger (low attention, P6). Priced coherently (markets._games_ou) but no line scraped. |
| Total SETS O/U 2.5 / set betting | LEANS straight-sets (favorite holds + steals one break) | mild | a heavy-favorite big server trends to 2-0; underdog-server with one hold-break-swing trends 2-1. Priced (1 - P(straight sets), base 0.594). |
| Tie-break YES | structurally HIGH (few breaks => 6-6 reached) | -- | NOT PRICEABLE honestly: the engine resolves 6-6 as a 50/50 coin, no per-point model (markets.POINT_MODEL_GAPS). Do NOT fake. This is the biggest honest gap for THIS style. |
| Match-win (pregame) | EFFICIENT | -- | CUT. ATP Elo trails Pinnacle by Brier +0.0149 (00-edge-map). |

## Surface sensitivity (the load-bearing axis for this style)
- **Grass / fast hard:** big-server style AMPLIFIED -- ace rate up, holds up, breaks rarer => GAMES-
  OVER and ACE-OVER both strongest here. Grass is only 3,228 of ~30.6k matches on disk (matches.
  parquet: Hard 18152, Clay 9164, Grass 3228) -> thin sample, prior-backed only.
- **Clay:** big-server style SUPPRESSED -- longer rallies, more breaks, ace rate falls, holds drop =>
  ACE-UNDER and the GAMES line is LESS over-leaning. A big server is OVERRATED by a surface-blind line
  on clay. This is the cleanest surface mispricing direction for this style.
- The engine already conditions on surface: `_pick_hold` prefers the surface-specific as-of hold over
  the overall (match_engine_holds.py:42-46, clipped 0.30-0.95). The ACE model, when built, must be
  per-surface (surface_ace_rate) or it will mis-price exactly this style on clay.

## How the sim/engine encodes this style
- **Hold prior:** `serve_probs_asof` shapes per-player hold% from each player's surface-conditioned
  as-of hold (asof_hold.py, prior-only / leak-free by construction). A big server enters with a high
  base hold -> the match engine produces few breaks, deep sets, more games.
- **Match-win bisection:** holds (ph1,ph2) are bisected to the calibrated Elo match-win (predictor.py
  _hold_levels) -> serve dominance shapes the GAMES/SETS distribution without overriding the (sharp)
  match-win.
- **No per-point serve model:** the engine stores per-match game TOTALS and coins 6-6 -> it CANNOT
  express tie-break frequency, the quantity most diagnostic of this style. Honest gap.

## Detection recipe (compute in-data)
Flag big server: `ace_rate >= 80th pct (>> 0.06) AND 1st_win_pct >= 70th pct AND hold% >= 75th pct
AND return/break-creation <= median`. Source: match_stats.parquet aggregated per player as-of (leak-
free, prior only). For the ace pocket: build `expected_aces = svpt_faced * surface_ace_rate(player,
surface)`; flag matches on fast surfaces vs weak-return opponents where a flat scraped line < model.
For GAMES-OVER: flag big-server-vs-big-server pairings (both flagged) -> long-match prior.

## Proof method + honest tier
Tier = HYPOTHESIS (entirely blocked on a prop scraper -- odds.parquet is match-winner two-way only).
Proof path: (1) build the per-surface ace-rate NegBinom model; CALIBRATION-PROVE its count coverage
OOS (leak-free WF, conformal width -- watch the too-tight Poisson trap that invents fat tails); (2)
once an ace line is scraped, P(over) BSS / realized ROI at fixed payout (PrizePicks = pick'em, edge
basis model_view; Underdog two-way = ev_vs_priced, the channel where CLV could accrue). CUT pregame
match-win for this style. Do NOT price tie-break (no per-point model).
