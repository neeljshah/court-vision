# TENNIS ARCHETYPE -- BASELINE GRINDER (rally-heavy, break-heavy, low-ace attrition)

_Part of the edge-intelligence corpus. PLAYSTYLE / ROLE prior, NOT a person (binding graph rule).
Grounded in data/domains/tennis/match_stats.parquet (low ace_rate, high 2nd_win/bp_saved, deep
rallies implied by svpt) + matches.parquet surface dist + domains/tennis/match_engine_holds.py /
markets.py + postmortem.parquet (straight_sets base 0.594). See tennis/00-edge-map.md +
markets-and-props.md. ASCII. Tiers: HYPOTHESIS / CALIBRATION-PROVEN / CLV-PROVEN._

## Who this is (style, not name)
The defensive baseliner / attrition grinder: LOW ace_rate (at/below the leaguewide mean 0.0603),
MODERATE 1st-serve win%, strong 2nd-serve win% and break-point SAVE rate (defends serve by rallying,
not by ace), AND a strong RETURN game that CREATES breaks. Wins long rallies and converts more
breaks than it concedes. Defining traits in-data: `ace_rate <= 0.06`, high `2nd_win_pct` (mean 0.487)
relative to peers, high `bp_saved_pct` AND high break-creation on return.

## Serve/return profile -> markets

| Market | Profile for this style | Soft? | Verdict + why |
|---|---|---|---|
| Aces O/U (player) | LOW ace count (signature: this style does NOT ace) | YES (UNDER side) | the mirror of the big server: a SURFACE-BLIND flat ace line OVER-rates a grinder, especially on CLAY. ACE-UNDER candidate. Same blocker (no line, no model). |
| **Total GAMES O/U (match)** | DEPENDS: grinder-vs-grinder on clay => MANY long rallies but ALSO many breaks => games can land EITHER way; against a big server the grinder breaks more => OVER from break exchanges | mixed; soft on lower tiers | NOT a clean single-direction lean -- the grinder breaks AND gets broken => the match-game distribution widens; the soft pocket is the WIDE-tail alt lines, not the main. Priced coherently (markets._games_ou). |
| Total SETS O/U 2.5 / set betting | LEANS 3-set / OVER 2.5 sets | YES | break-heavy attrition => tighter sets => more deciding sets. Grinder matches trend AWAY from straight sets (vs base 0.594). SETS-OVER 2.5 candidate. |
| 1st-serve % / 2nd-serve win props | high & stable | noisy | ingredients in match_stats (1st_in, 2nd_win) but rare-event-negative-skill trap risk (cut-list CUT-4 analog) -- demote until a per-stat leak-free BSS proves otherwise. |
| Match-win (pregame) | EFFICIENT | -- | CUT (ATP Elo trails Pinnacle +0.0149). |

## Surface sensitivity (the load-bearing axis)
- **Clay:** grinder style AMPLIFIED -- long rallies, more breaks, ace rate falls leaguewide. The
  grinder's edge OVER a big server is largest on clay (the big server's holds erode). Clay is 9,164
  of ~30.6k matches (matches.parquet) -> decent sample, not thin. SETS-OVER-2.5 and ACE-UNDER are
  strongest here.
- **Grass / fast hard:** grinder style SUPPRESSED -- rallies shorten, the grinder loses its
  break-creation edge, the big server's holds dominate. A surface-blind line that rates the grinder
  on its clay form OVER-rates it on grass.
- The engine's `_pick_hold` surface preference (match_engine_holds.py:42-46) already lowers a
  grinder's hold on fast surfaces if surface-specific as-of hold is present; surface-blind props do
  not -> the mispricing seam.

## How the sim/engine encodes this style
- **Hold prior + break creation:** the grinder enters with a moderate hold but the match engine's
  break exchanges (driven by both holds being closer together) produce more service breaks -> more
  3-set outcomes, fewer straight sets. `serve_probs_asof` shaping keeps the two holds CLOSE for a
  grinder-vs-grinder match (small `margin`, match_engine_holds.py:63) -> tight, long matches.
- **Sets distribution:** markets prices SETS O/U as `1 - P(straight sets)` off the matrix; a grinder
  pairing lowers P(straight sets) below the 0.594 base -> SETS-OVER leans emerge natively.
- **No per-point model:** within-set game totals and tie-break frequency are NOT priceable
  (POINT_MODEL_GAPS) -> the grinder's long-deuce-game tendency cannot be expressed; honest gap.

## Detection recipe (compute in-data)
Flag grinder: `ace_rate <= 40th pct (<= ~0.06) AND 2nd_win_pct >= 60th pct AND break-creation-on-
return >= 60th pct AND bp_saved_pct >= median`. Source: match_stats per player as-of (leak-free). For
ACE-UNDER: same expected_aces model, flag where a flat line > model (grinder on clay). For SETS-OVER:
flag grinder-vs-grinder OR grinder-vs-big-server on clay -> P(straight sets) < 0.594 prior.

## Proof method + honest tier
Tier = HYPOTHESIS (blocked on a prop scraper). Proof: build per-surface ace model (for ACE-UNDER) and
CALIBRATION-PROVE the SETS-O/U coherent price vs realized straight-set rate by surface, leak-free WF.
Once lines scrape: P(over) BSS for SETS-O/U, realized ROI for ACE-UNDER. Beware the serve-% props
rare-event trap. CUT match-win. Do NOT price within-set games / tie-break.
