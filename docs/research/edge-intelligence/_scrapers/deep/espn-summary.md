# DATASOURCE -- ESPN event SUMMARY (`rosters[]` block: team + per-player stats)

_Deep per-datasource spec. Part of the edge-intelligence corpus (_scrapers/deep/).
The keyless ESPN `summary?event=<id>` payload carries THREE things we consume from
ONE call: (a) `pickcenter[]` republished moneyline (see data-acquisition.md B1),
(b) the `rosters[]` per-player post-match stats block (THIS file), and (c) `keyEvents`
substitutions used to derive minutes. The rosters block is the per-player corpus
backbone for the soccer World Cup prop board. Markets are efficient; this adds DATA
DEPTH in a beatable pocket (P1 soft/DFS props), not an asserted edge. ASCII only._

STATUS: WIRED (soccer; `fifa.world` + `eng.1`). KEY: KEYLESS. EDGE-UNLOCK: P1
substrate (per-player rate priors -> prop distributions). TIER: CALIBRATION (the
rates are the model corpus; the board's calibration is suggestive at WC N, deep-dive
12 sec 5).

---

## Endpoint

```
GET https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/summary?event={event_id}
```
- `{league}`: `fifa.world` (World Cup), `eng.1` (EPL), `esp.1` (LaLiga), etc.
  Sport segment is `soccer/...`; the same SUMMARY shape exists for `basketball/nba`
  and `baseball/mlb` but the `rosters[]` per-player node is soccer-specific (NBA/MLB
  expose `boxscore.players` instead -- see mlb-statsapi.md for the MLB analogue).
- `{event_id}`: from the scoreboard. Get ids via
  `GET .../soccer/{league}/scoreboard?dates=YYYYMMDD` ->
  `events[].id` (see `ingest_espn_players.fetch_scoreboard`, line 203).
- No auth, no key. Requires a browser `User-Agent` header (urllib default UA can 406
  on some ESPN hosts; the code sets `_UA` = Chrome string, `ingest_espn_players.py:36`).
- Cost: 1 scoreboard call per (date, league) + 1 summary call per event. The odds
  provider caps `max_events` at 20 (`espn.py:82`); the player ingest has no cap (it
  iterates all scoreboard events).

## Payload schema (confirmed 2026-06-16, fifa.world event 760432)

Top-level keys we use: `rosters` (per-player), `keyEvents` (subs), `pickcenter`
(odds; separate file). The per-player block:

```
summary["rosters"]              # list, exactly 2 entries (one per team)
  block["homeAway"]             # "home" | "away"
  block["team"]["abbreviation"] # team code
  block["roster"][]             # one entry per rostered player
    p["athlete"]["id"]          # STABLE ESPN athlete id (the join key)
    p["athlete"]["displayName"]
    p["position"]["abbreviation"]   # "F","M","D","G",...
    p["starter"]  p["subbedIn"]  p["subbedOut"]   # booleans
    p["jersey"]
    p["stats"][]                # [{name, value, displayValue}], value IS numeric
summary["keyEvents"][]          # substitution + goal/card events
    ev["type"]["text"]          # contains "Substitution"
    ev["clock"]["displayValue"] # "75'" -> minute
    ev["participants"][]["athlete"]["id"]   # both sub participants share the minute;
                                            # in/out NOT labelled -> disambiguate via
                                            # roster subbedIn/subbedOut flags
```

## Per-player fields emitted (the consumed schema)

`_parse_player_summary` (`ingest_espn_players.py:144`) writes one row per rostered
player (unused subs KEPT at minutes=0.0, stats None -- a real 0-minute fact) with:

| column | source | notes |
|---|---|---|
| `event_id`, `league`, `date` | scoreboard / arg | join + as-of key |
| `team_abbr`, `home_away` | roster block | |
| `player_id` (str), `player`, `position` | athlete / position | `player_id` = stable join key |
| `starter`, `subbed_in`, `subbed_out` | roster flags | |
| `minutes`, `minutes_estimated` | `_derive_minutes` (`:117`) | exposure denominator |
| `totalShots`, `shotsOnTarget` | stats[] | the SOT prop driver |
| `foulsCommitted`, `foulsSuffered` | stats[] | |
| `yellowCards`, `redCards` | stats[] | cards prop |
| `goalAssists`, `offsides`, `totalGoals` | stats[] | |
| `saves` | stats[] | GK-only (shotsFaced also exposed) |

Stat field whitelist: `_STAT_FIELDS` (`ingest_espn_players.py:45`). ESPN stat `name`
== output column name (no rename). `_stat_value` prefers `value`, falls back to
`displayValue` (`:69`).

Minutes derivation (`_derive_minutes`, `:117`) -- the exposure unit that turns a raw
count into a per-90 rate downstream:
- starter & not subbed out -> 90.0
- starter & subbed out -> off-minute (from keyEvents)
- sub on & not off -> 90 - on-minute
- never played -> 0.0
- missing sub minute -> fallback (`_SUB_IN_FALLBACK=20.0`) + `minutes_estimated=True`

## Output artifact

`data/domains/soccer/espn_player_stats.parquet` (~1241 rows / 48 WC teams = ONE WC
tournament, deep-dive 12 sec 5). Written/merged by `ingest_range`
(`ingest_espn_players.py:228`), dedup on `(event_id, player_id)` keep last.

## Which engine consumes it

- `domains/soccer/player_rates.py` -- `_prior_rows` / `rate_prior` / `player_rate`
  (`:62`,`:96`,`player_rate` ~`:145`) read the parquet rows AS-OF (only rows with
  `date < as_of`), pool by stat, and produce empirical-Bayes-shrunk per-90 priors.
  `CANON_TO_COLS` (`player_rates.py:35`) maps canonical prop stats -> these columns.
- `domains/soccer/prop_engine.py` -- turns rate x minutes-exposure into a Poisson/
  NegBin prop distribution and prices the board.
- `domains/soccer/prop_settle.py` -- reads `espn_player_stats.parquet` for REALIZED
  outcomes to settle/grade props (post-match, not a feature).

## Refresh cadence

Post-match, idempotent. Run after a slate completes (results are final). Loop/manual
driven, not scheduled. For the prop board it is a SUBSTRATE refresh, not a live feed:
fetch a date's events once their summaries carry final stats.

## Leak rules (as-of, binding)

1. These are REALIZED post-match rows. A player's own row for match M is NEVER a
   feature for match M (`ingest_espn_players.py` docstring; enforced by `_prior_rows`
   filtering to `date < as_of_date`).
2. To price event E, use only rows with `date < kickoff(E)`. `player_rate`'s as-of
   join is the leak guard; do not bypass it.
3. `minutes_estimated=True` rows carry denominator uncertainty -- the rate is a prior
   to blend (capped weight), never a trusted probability.
4. The `pickcenter[]` block in the SAME payload, if logged in-game, is a LIVE price
   (P2) and must be timestamped separately -- never fold a live summary's odds into a
   pregame snapshot.

## Honest caveats / gaps

- THIN: one WC tournament (~1241 rows) is the binding cap on the prop vertical's
  calibration (deep-dive 12 sec 5: isotonic recal OVERFITS, opponent-adjust NULL).
  The club-prior unlock (espn-athlete-overview.md) is the primary mitigation; deeper
  per-player stats (sofascore-fotmob.md) is the secondary one.
- ESPN soccer stats are SHALLOW: shots/SOT/fouls/cards/assists/offsides/saves only.
  NO tackles, interceptions, passes, key passes, xG, touches, progressive carries --
  i.e. the stats that drive most soft DFS soccer props are MISSING here (that is the
  D1 gap, sofascore-fotmob.md).
- Substitution in/out labels are NOT in keyEvents; minutes for double-subbed players
  are estimates. Validate `minutes` against any external source before trusting a
  per-90 from a low-minute player.
