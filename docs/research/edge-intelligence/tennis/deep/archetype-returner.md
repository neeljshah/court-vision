# TENNIS ARCHETYPE -- RETURNER (break-generating, return-first, vulnerable-serve)

_Part of the edge-intelligence corpus. PLAYSTYLE / ROLE prior, NOT a person (binding graph rule).
Grounded in data/domains/tennis/match_stats.parquet (low own ace_rate, high opponent bpFaced /
break-conversion, modest 1st_win) + matches.parquet surface dist + domains/tennis/
match_engine_holds.py / asof_hold.py / markets.py. See tennis/00-edge-map.md + markets-and-props.md.
ASCII. Tiers: HYPOTHESIS / CALIBRATION-PROVEN / CLV-PROVEN._

## Who this is (style, not name)
The return specialist: elite at NEUTRALIZING serve and CONVERTING breaks, but with a relatively
VULNERABLE own serve (modest ace_rate, ordinary hold%). Wins by breaking more than being broken.
Distinct from the grinder (who defends serve by rallying) -- the returner's edge is specifically on
the RECEIVING end: high opponent-bpFaced generated, high break-conversion. Defining traits in-data:
modest own `ace_rate` / `1st_win_pct`, but high break points CREATED (opponent bpFaced) and high
break-conversion vs the field.

## Serve/return profile -> markets

| Market | Profile for this style | Soft? | Verdict + why |
|---|---|---|---|
| Aces O/U (own) | LOW-MODERATE own aces | mild UNDER | own ace count ordinary; a flat line may slightly over-rate. Secondary, not the pocket. |
| **Opponent holds / total breaks / GAMES O/U** | the SIGNATURE: this style DEPRESSES opponent holds and creates breaks => SHORTER service games for the opponent, MORE breaks | **YES (the real pocket)** | a returner facing a vulnerable-serve opponent => break-fest => GAMES can go UNDER (quick breaks end games fast) OR the match ends in straight sets quickly. The seam: lines that price the opponent's hold off the opponent's OWN serve stats ignore the returner's break pressure. Priced coherently (markets._per_side_games / _games_ou) but no line scraped. |
| Total SETS O/U 2.5 / set betting | LEANS straight-sets WHEN the returner is the favorite (breaks early, closes 2-0); LEANS 3-set when two returners trade breaks | direction depends on favorite/dog | a returner-favorite vs a weak server trends to a fast 2-0 (straight-sets OVER on set betting). Priced (1 - P(straight sets), base 0.594). |
| Match-win (pregame) | EFFICIENT | -- | CUT. ATP Elo trails Pinnacle +0.0149 (00-edge-map). Return strength is already in the Elo via results. |
| Break-points-converted / return props | high | very noisy | ingredients exist (bpFaced/Saved) but rare-event-negative-skill trap (cut-list CUT-4 analog) -> demote until leak-free per-stat BSS proves otherwise. |

## Surface sensitivity (the load-bearing axis)
- **Clay:** returner style AMPLIFIED -- slow surface lets the returner get more balls back, break
  conversion rises, opponent holds erode. The returner-vs-server mismatch is LARGEST on clay; the
  GAMES line and opponent-hold props mis-rate the server most here. (Clay n=9,164.)
- **Grass / fast hard:** returner style SUPPRESSED -- the opponent's serve plays bigger, fewer return
  points won, breaks rarer. A surface-blind line that rates the returner on clay form over-rates it
  on grass (mirror of the big-server case). (Grass n=3,228, thin.)
- The engine surfaces this via `_pick_hold` (surface-specific as-of hold preferred, match_engine_
  holds.py:42-46): a returner depresses the OPPONENT's effective hold most where the surface allows
  -- but a surface-blind scraped prop line does not.

## How the sim/engine encodes this style
- **Asymmetric holds:** `serve_probs_asof` sets per-player holds from each player's surface as-of hold
  with a bounded `margin` (match_engine_holds.py:63). A returner facing a weak server widens the hold
  GAP -> the engine produces more breaks of the opponent -> shorter opponent service games, more
  break swings in the games tally.
- **Per-side games:** `_per_side_games` resims per-side game tallies with the same holds (markets-
  and-props.md) -> the returner's break pressure flows into the opponent's LOW game count coherently.
- **Match-win is sharp:** return ability is already integrated into the calibrated Elo via match
  results -> do NOT try to add a return feature to beat the close (cut-list CUT-1: that gap is the
  market's freshness, not our missing signal).
- **No per-point model:** which specific games break is not modeled (POINT_MODEL_GAPS) -> within-set
  break-game props are not priceable; honest gap.

## Detection recipe (compute in-data)
Flag returner: `break-conversion-on-return >= 70th pct AND opponent-bpFaced-generated >= 70th pct AND
own ace_rate <= 60th pct AND own hold% <= 60th pct`. Source: match_stats per player as-of (leak-free,
prior only). For the GAMES / opponent-hold pocket: compute the returner's historical opponent-hold
depression by surface; flag matches where a scraped GAMES line is set off the opponent's solo serve
stats (ignoring break pressure), especially on clay vs a vulnerable server.

## Proof method + honest tier
Tier = HYPOTHESIS (blocked on a prop scraper -- only match-winner two-way odds exist). Proof:
CALIBRATION-PROVE the coherent GAMES O/U and per-side-games prices vs realized by surface (leak-free
WF) BEFORE trusting any returner-driven lean; then, once a GAMES line scrapes, P(over) BSS / realized
ROI. CUT pregame match-win (return strength already in Elo). Demote break-point props (rare-event
trap). Do NOT price within-set break games (no per-point model).
