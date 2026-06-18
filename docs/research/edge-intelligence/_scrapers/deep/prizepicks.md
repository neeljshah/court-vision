# PrizePicks -- DEEP scrape/acquisition spec (DFS pick'em projections)

_Deep, actionable layer of `_scrapers/data-acquisition.md` A2. Grounds in the live code
`scripts/platformkit/odds_provider/prop_prizepicks.py` + consumer `scripts/platformkit/prop_edge.py`.
ASCII only. No $-edge claims: every edge built on this source is a CANDIDATE until calibration-
then CLV-proven, and PrizePicks CLV is UNDEFINED (see "Honesty rules")._

---

## 1. Endpoints / host (KEYLESS, no auth, no cookie)

Two GETs, both keyless JSON. UA must be a browser string (default urllib UA is sometimes 403'd).

1. League enumeration -- resolve the league id BY NAME (survives season id churn):
   `GET https://api.prizepicks.com/leagues`
   (`prop_prizepicks.py:42` `_LEAGUES_URL`)
2. Projections for one league id:
   `GET https://api.prizepicks.com/projections?league_id=<id>&per_page=250&single_stat=true`
   (`prop_prizepicks.py:43-44` `_PROJ_URL`)

Auth: NONE. No API key, no static app key, no bearer, no cookie. `Accept: application/json`
+ browser UA only (`_UA`, `prop_prizepicks.py:45`). `single_stat=true` collapses combo
projections (e.g. "Pts+Reb+Ast") so each row is one stat -- KEEP IT for a clean board.

## 2. JSON shape + the EXACT join path

`/leagues` -> `data[]`, each `{id, attributes.name}`. Match `attributes.name` to the wanted
league name, normalized (lowercase + single-spaced), EXACT match so "WORLD CUP" does not
collide with "WORLD CUP 1H" / "WORLD CUP TRNY" (`find_league_id`, `prop_prizepicks.py:75-90`).

`/projections` is JSON:API shaped -- two arrays:
- `data[]` : each `{type:"projection", id, attributes{...}, relationships{...}}`
- `included[]` : the join hub. `type:"new_player"` rows + `type:"game"` rows.

Join path (player, stat, line):
```
projection.attributes.line_score                          -> line  (float)
projection.attributes.stat_type                           -> stat  (e.g. "Shots On Target")
projection.relationships.new_player.data.id               -> pid
included[type=new_player][id==pid].attributes.name        -> player
included[type=new_player][id==pid].attributes.team        -> team
projection.relationships.game.data.id                     -> gid
included[type=game][id==gid].attributes.metadata.game_info.teams.{home,away}.abbreviation
                                                          -> match "HOME v AWAY"
```
Implemented in `parse_props` (`prop_prizepicks.py:106-164`): builds `players{}`/`games{}`
dicts from `included[]` then walks `data[]`. The match title comes from `_match_title`
(`:93-103`). Drop any row missing name/stat/line (`:142`) -- never half-fabricate.

Other attributes present but NOT currently used (coverage gaps, see honesty rules):
- `attributes.odds_type` : `"standard"` | `"goblin"` | `"demon"` (the flex variants)
- `attributes.adjusted_odds` : True for goblin/demon
- `attributes.description` : often the opponent label
- `attributes.start_time` : the projection's event start (USE for leak stamping, below)

## 3. Sports / leagues carried

ALL PrizePicks DFS sports on the same endpoint -- the only thing that changes is `league_id`.
`/leagues` enumerates them live. Today wired: `_LEAGUE_NAME = {"soccer_intl": "WORLD CUP"}`
(`prop_prizepicks.py:49`). League names observed across the product (resolve by name, never
hardcode the int id): "NBA", "MLB", "NFL", "WNBA", "NHL", "CFB", "SOCCER" / competition-named
soccer leagues, "WORLD CUP", "CS2"/"LoL"/"VAL" esports, "PGA", "TENNIS". Map a new sport by
adding one entry to `_LEAGUE_NAME` -- e.g. `"nba": "NBA"`, `"mlb": "MLB"`.

## 4. Two-way vs pick'em pricing (THE structural point)

PrizePicks is PICK'EM: standard lines carry NO two-sided American/decimal price in the
payload. So EVERY row is emitted `over_price=None, under_price=None, payout_type="dfs_pickem"`
(`prop_prizepicks.py:156-158`). This is correct and must stay: we NEVER fabricate a price.

Why this matters for edge (from `_framework/edge-theory.md`): PrizePicks CANNOT move its
payout, so a genuinely mispriced projection STAYS mispriced -- the cleanest *structural*
inefficiency in the census. But there is no devig-able two-way close, so CLV-vs-close is
UNDEFINED here. The honest proof path is P(over)-calibration vs realized outcome + fixed-
payout simulated ROI + LINE-MOVEMENT (the projection itself moving), NOT CLV.

## 5. Rate-limit / robustness

- Light: 1 (`/leagues`) + 1 (`/projections`) per sport per refresh; league id is cached in
  `self._league_id_cache` (`prop_prizepicks.py:176,178-184`) so steady-state is 1 GET/refresh.
- No documented rate cap; the public board polls roughly every 30-60s. Stay >= 30s between
  pulls per sport; jittered. 12s timeout (`:61`).
- Anti-bot: occasional Cloudflare/403 on a bare UA -- the browser UA handles it today. If 403s
  appear, the robustness contract already covers it: `_default_http_get` returns `{}` on ANY
  error (`:63-65`), `fetch_props` degrades to `unavailable(...)` and NEVER raises (`:198-205`).
- This is an unofficial/undocumented endpoint (same fragility class as Underdog): treat a
  shape change as expected; the parser drops unknown rows rather than crashing.

## 6. Leak / honesty rules (binding)

1. LEAK: stamp `as_of` (already done, `_now_iso()` `:130`). A projection is only valid as a
   feature/bet if `as_of < projection.attributes.start_time` (kickoff/tip). Currently the
   code does NOT read `start_time`; ADD it to the row and gate on it before any CLV/grading
   use. Never use a line logged after first ball.
2. STRUCTURAL HONESTY: all edges off this source are `edge_basis="model_view"` in
   `prop_edge.py` (gap from 0.5, `prop_edge.py:215-217`), NEVER `ev_vs_priced`. Do not let a
   pick'em row claim an EV-vs-price number -- it has no price.
3. COVERAGE GAP (honest): goblin/demon flex lines (`odds_type`) carry a different (worse)
   effective payout and are NOT parsed today -- the highest-payout, most-likely-mispriced
   lines are invisible. Flag as a real gap; do not silently treat a goblin line as standard.
4. CALIBRATION TIER: HYPOTHESIS. The WC prop calibration is "suggestive on 24 matches"
   (deep-dive 03 sec 5), NOT established. `prop_edge` tiers each stat by OOS calibration on
   those 24 matches; "proven" there is a CALIBRATION claim, never a profit/CLV claim.

## 7. EXACT code change to wire a new sport (e.g. NBA)

Single-line map add + verify the stat vocab covers the new sport:
- `scripts/platformkit/odds_provider/prop_prizepicks.py:49`
  `_LEAGUE_NAME = {"soccer_intl": "WORLD CUP", "nba": "NBA", "mlb": "MLB"}`
- The provider then works unchanged (resolve-by-name -> projections -> parse).
- Extend the canonical stat map for NBA labels in
  `scripts/platformkit/odds_provider/prop_base.py:29-71` (`_STAT_CANON`) e.g.
  `"points":"PTS","rebounds":"REB","assists":"AST","pts+rebs+asts":"PRA","3-pt made":"FG3M"`.
  Unknown labels pass through unchanged (`canon_stat`, `:74-86`) so nothing is dropped.
- To surface the new sport on the board, add it to `prop_edge._SUPPORTED`
  (`prop_edge.py:35`, today `{"soccer_intl"}`) AND provide an NBA per-player distribution
  model (today `prop_edge` only knows the soccer `prop_engine`); for NBA route to the
  MC-sim prop ladder (`src/prediction/player_props.py`) rather than the soccer Poisson.
  Until that NBA distribution path exists, the scraper can still RECORD lines (for line
  history / CLV) without producing a board.

To add goblin/demon coverage: in `parse_props` read `attr.get("odds_type")` and
`attr.get("adjusted_odds")`, emit them on a new `PropLine` field (e.g. `flex_type`), and
keep `payout_type="dfs_pickem"` (still no two-way price) -- this only closes the COVERAGE
gap, it does not create a price.

ADD a smoke test that records the REAL payload: `scripts/platformkit/test_prop_prizepicks.py`
already unit-tests `parse_props`/`find_league_id` on canned bodies; add a network-gated live
probe (skipped in CI) that asserts the real `/leagues` returns a row whose name == the mapped
league, so a silent endpoint/shape change is caught.
