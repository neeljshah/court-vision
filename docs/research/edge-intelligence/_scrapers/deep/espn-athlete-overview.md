# DATASOURCE -- ESPN ATHLETE OVERVIEW (club-season splits = the WC club-prior unlock)

_Deep per-datasource spec. Part of the edge-intelligence corpus (_scrapers/deep/).
THE highest-leverage soccer-prop unlock available keylessly: a World Cup player carries
~1 WC match of history, so their prop rate shrinks almost entirely to a position
baseline and the board produces ~0 reliable edges. This endpoint returns each athlete's
CLUB-SEASON per-stat aggregates -- the player's true recent form -- which we ingest as a
STRONG prior so a player with a real club season gets a reliable rate baseline. Real
data, not fabrication. Adds DATA DEPTH in the P1 pocket; not an asserted edge. ASCII._

STATUS: WIRED (soccer). KEY: KEYLESS. EDGE-UNLOCK: P1 substrate -- directly attacks the
binding thinness cap on the WC prop vertical. TIER: CALIBRATION (it lifts the prior; the
board's $-edge stays HYPOTHESIS).

---

## Endpoint

```
GET https://site.web.api.espn.com/apis/common/v3/sports/soccer/{league}/athletes/{athlete_id}/overview
```
- Host is `site.web.api.espn.com` (NOT `site.api.espn.com` used by summary/scoreboard).
- `{athlete_id}`: the STABLE ESPN athlete id surfaced by the SUMMARY rosters block
  (`espn-summary.md`, `p["athlete"]["id"]`). The two sources join on this id directly.
- `{league}`: the player's CLUB league slug (default `esp.1` LaLiga; pass `eng.1`,
  `ita.1`, `ger.1`, etc.). The overview returns the athlete's splits regardless, so the
  slug mainly routes the request; we filter splits by content (see below).
- CONFIRMED keyless 2026-06-17 (`ingest_espn_athlete.py:10`). NOTE: the sibling
  `/gamelog` endpoint 500s -- use OVERVIEW only.
- Browser UA required (`_UA`, `ingest_espn_athlete.py:43`).
- Cost: 1 call per athlete. Build iterates the WC player ids from
  `espn_player_stats.parquet` (`_player_ids_from_parquet`, `:253`).

## Payload schema (confirmed 2026-06-17)

```
overview["statistics"]
  ["names"]   # ordered list of stat-column names; index-aligned to each split's stats
  ["splits"][]  # one per competition/season the athlete played
    split["displayName"]  split["leagueSlug"]  split["name"]   # used to classify intl vs club
    split["leagueId"]  split["teamSlug"]  split["teamId"]
    split["stats"][]   # values index-aligned to statistics["names"]
```
Each split is a CLUB/competition SEASON AGGREGATE (season totals, not per-game). A
`starts` column appears in `names` and is the per-90 denominator surrogate.

## Per-player fields emitted (the consumed schema)

`parse_club_prior` (`ingest_espn_athlete.py:100`) SUMS each raw ESPN column + `starts`
across all CLUB splits, EXCLUDING international/friendly/WC splits (`_is_intl_split`,
`:85`, token list `_INTL_TOKENS` `:57` -- "world cup","friendl","national","euro",
"fifa",... so WC data is never double-counted against the WC board). It then maps raw
columns -> canonical prop stats via `CANON_TO_COLS` (imported from `player_rates.py`;
cards = yellowCards + redCards). Output is one parquet row per `(player_id, stat_canonical)`:

| column | meaning |
|---|---|
| `player_id` (str) | ESPN athlete id (join key to summary rosters) |
| `stat_canonical` | canonical prop stat (e.g. shots, sot, fouls, cards, assists) |
| `total` | summed club-season count of that stat |
| `starts` | summed club-season started-match count (per-90 denominator) |
| `per_start` | `total / starts` (starts==0 -> None) read downstream AS A per90 rate |
| `as_of` | build date (`dt.date.today()`) |

## The per_start -> per90 APPROXIMATION (documented, honest)

ESPN gives season totals + `starts` but NOT minutes. A started match ~= 90 minutes, so
`starts` is treated as the per-90 denominator and `per_start = total/starts` is read as
a per90 rate (`ingest_espn_athlete.py:18-23`). Because it ignores SUB appearances, the
denominator is slightly under-counted -> the per90 is a mild OVER-estimate. It is a
PRIOR to be blended (capped weight), not a trusted probability.

## Output artifact

`data/domains/soccer/espn_club_priors.parquet` (`_DEFAULT_OUT`, `:50`). Written/merged by
`build_club_priors` (`:164`), dedup on `(player_id, stat_canonical)` keep last.

## Which engine consumes it

- `domains/soccer/player_rates.py` -- `club_prior()` lookup is implemented IN the ingest
  module (`ingest_espn_athlete.py:216`) returning `{per90, starts, status}`;
  `player_rates._club_weight` (`player_rates.py:116`) converts that to (per90, weight)
  and `player_rate(..., club_prior=...)` (`:145`) blends it as a STRONG prior with
  weight = `min(starts, CLUB_WEIGHT_CAP)` (cap at `player_rates.py:27-28` so a club
  season can dominate a 1-match WC sample but never fully override it). When no usable
  club per90 exists, the result is EXACTLY the prior (WC-only) implementation.
- `domains/soccer/prop_engine.py` + `prop_recal.py` -- consume the blended rate to price
  + recalibrate the board.

## Refresh cadence

Pre-tournament / pre-slate, idempotent. Club-season aggregates change slowly; refresh
once per club-season window (e.g. start of a WC, after a domestic-season rollover). Run:
`python -m domains.soccer.ingest_espn_athlete --league esp.1` (ids auto-loaded from the
WC players parquet) or `--ids <id...>`. Not a live feed.

## Leak rules (as-of, binding)

1. A CLUB-season aggregate is the player's PRIOR FORM; using it to price a WC match is
   leak-free PROVIDED the club season concluded (or is partial) BEFORE the WC kickoff.
   The honest risk: the overview may include the CURRENT (in-progress) club season whose
   later games post-date the WC match -- for strict leak-freedom the `as_of` stamp must
   be checked against kickoff and any split spanning past kickoff trimmed. The current
   build stamps `as_of` = build date but does NOT trim mid-season splits to kickoff;
   flag this as a known as-of gap (see proof-standards.md) -- treat club priors as
   recent-form context, validate calibration with a strict pre-kickoff cut.
2. International/WC splits are EXCLUDED (`_is_intl_split`) so WC outcomes never leak back
   into the WC prior.
3. `per_start` is a denominator approximation, not a measured rate -> blend, never trust.

## Honest caveats / gaps

- This is the SINGLE highest-value soccer-prop substrate move that is already built:
  without it, WC props shrink to a position baseline (deep-dive 12 / module docstring).
  With it, players with a real club season get a reliable baseline.
- STILL SHALLOW: same shallow ESPN stat surface as the summary (shots/SOT/fouls/cards/
  assists) -- no tackles/passes/xG. The DEEPER per-player stats that drive most soft DFS
  props remain MISSING (sofascore-fotmob.md, D1).
- `starts`-as-denominator under-counts sub minutes -> mild over-estimate; CLUB_WEIGHT_CAP
  is the guard. Validate the blended per90 against the realized WC rate where N permits.
- League-slug routing is best-effort; a player whose club is outside the passed slug may
  return partial splits. Iterating per-club-league or accepting the default-slug payload
  both work because filtering is content-based, but coverage should be spot-checked.
