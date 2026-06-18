# Underdog Fantasy -- DEEP scrape/acquisition spec (real two-way O/U props)

_Deep, actionable layer of `_scrapers/data-acquisition.md` A1. Grounds in the live code
`scripts/platformkit/odds_provider/prop_underdog.py` + consumer `scripts/platformkit/prop_edge.py`.
ASCII only. No $-edge claims. THIS IS THE TOP PROP LEVER: the only currently-wired source that
emits a real two-sided price, so it is the only one where EV-vs-priced + CLV are honest._

---

## 1. Endpoint / host (KEYLESS, no auth, no cookie)

ONE GET, keyless JSON, multi-sport in a single payload:
`GET https://api.underdogfantasy.com/beta/v5/over_under_lines`
(`prop_underdog.py:39` `_URL`)

Auth: NONE. No key, no app key, no cookie. `Accept: application/json` + browser UA
(`_UA`, `:40-41`). One call returns EVERY sport's open O/U lines; we filter client-side by
`player.sport_id`. 12s timeout (`:56`).

## 2. JSON shape + the EXACT join path

Top-level arrays in the body:
- `over_under_lines[]` : one O/U line. `stat_value` = numeric line; `options[]` = the two
  sides (`choice` in {"higher","lower"}); `over_under.appearance_stat.{appearance_id,
  display_stat}` (display_stat = the human stat label).
- `appearances[]` : `id -> {player_id, team_id, match_id}` -- the JOIN HUB.
- `players[]`     : `id -> {first_name, last_name, sport_id, team_id}`.
- `games[]`       : `id (int) -> {full_team_names_title, home_team_id, away_team_id,
  short_title, sport_id, scheduled_at}`. `appearance.match_id == game.id`.

Join path (player, stat, line, prices), `parse_props` (`prop_underdog.py:104-169`):
```
line.over_under.appearance_stat.appearance_id          -> appearance
appearance.player_id  -> players[player_id]            -> player (FILTER player.sport_id)
appearance.match_id   -> games[match_id]               -> game
line.stat_value                                        -> line  (float)
appearance_stat.display_stat                           -> stat  (canon_stat'd)
first_name + last_name                                 -> player
game.full_team_names_title | short_title               -> match  (and team via home/away id)
for opt in options:
    opt.choice=="higher" -> over_price = decimal_price
    opt.choice=="lower"  -> under_price = decimal_price
```
Team resolution: split the game title on " vs " and map `appearance.team_id` to home/away
(`_team_name`, `:84-95`). Drop rows missing line/stat/name (`:140`).

## 3. Pricing -- TWO-WAY, and the price-field trap (CRITICAL)

Each `option` carries THREE numbers that DO NOT agree:
- `american_price` (e.g. -190 / +150)
- `decimal_price` (e.g. "1.53") -- the TRUE vig-adjusted two-sided price, `line_type
  "balanced"`
- `payout_multiplier` (e.g. "0.75") -- a profit-multiple, NOT a probability

Trap: `1 + payout_multiplier (1.75) != decimal_price (1.53)`. The code correctly uses
`decimal_price` and labels `payout_type="sportsbook"` (`_dec_price` `:71-76`, `:151`). NEVER
price off `payout_multiplier`. If `decimal_price` is missing/<=1.0, fall back to
`payout_type="dfs_pickem"` with both prices None (`:151`) -- never guess.

Consequence: because Underdog gives a real two-way price, `prop_edge` runs the FULL EV path
on these rows -- `devig_twoway` + `ev_vs_price`, `edge_basis="ev_vs_priced"`
(`prop_edge.py:198-214`). This is the ONLY prop source where that path is honest today.

## 4. Sports / leagues carried

ALL Underdog sports arrive in the one payload; filter by `player.sport_id`. Today wired:
`_SPORT_ID = {"soccer_intl": "FIFA"}` (`prop_underdog.py:44`). Observed `sport_id`s on the
same endpoint: `"NBA"`, `"MLB"`, `"NFL"`, `"NHL"`, `"WNBA"`, `"CBB"`, `"CFB"`, `"FIFA"`
(World Cup), `"SOCCER"`, `"PGA"`, `"TENNIS"`, `"ESPORTS"`/title-specific. Map a new sport by
adding ONE entry (see sec 7). The SAME single GET already contains NBA/MLB rows -- adding the
id is near-zero-cost and unlocks props in the deep multi-season corpora (the highest-value
wiring per data-acquisition.md D2).

## 5. Rate-limit / robustness

- ONE GET per refresh (all sports) -- cheapest source in the census. No per-sport fan-out.
- No documented cap; >= 30s between pulls is polite; jitter. 12s timeout.
- Anti-bot: browser UA suffices today; the endpoint is unofficial (fragile). On ANY error
  `_default_http_get` returns `{}` (`:58-60`); `fetch_props` degrades to `unavailable(...)`,
  NEVER raises (`:188-197`). A shape change drops affected rows, not the board.
- `use_cache` is reserved but ignored (raw urllib). For CLV capture, the SAME single endpoint
  must be polled up-to-kickoff (it is light enough to poll every 30-60s for a whole slate).

## 6. Leak / honesty rules (binding)

1. LEAK: `game.scheduled_at` is the event time. A line is valid only if `as_of <
   scheduled_at`. `as_of` is stamped (`_now_iso()` `:123`); `scheduled_at` is NOT yet read --
   ADD it onto the row and gate on it for CLV/grading. Never use a post-kickoff line.
2. PRICE HONESTY: use `decimal_price` only; `payout_multiplier` is a multiple, not odds.
   Missing price -> `dfs_pickem` + None, never a fabricated number.
3. SOFT-LINE FRAMING: Underdog is a SOFT/DFS sportsbook, not a sharp mainline. An EV-vs-this-
   price edge is `tier="MODEL_VIEW"` (`prop_edge.py`), i.e. EV vs a soft price, NOT beat-the-
   close. CLV vs the Underdog close is computable and IS the proof bar for real money.
4. CALIBRATION TIER: HYPOTHESIS. The price-vs-model edge is unestablished; WC calibration is
   suggestive on 24 matches. CLV-PROVEN requires the closing-line loop
   (`prop_line_history.py`, see `_scrapers/closing-line-and-clv.md`) to actually accrue real
   up-to-kickoff Underdog lines -- today that history is essentially one placeholder row.

## 7. EXACT code change to wire a new sport (e.g. NBA)

- `scripts/platformkit/odds_provider/prop_underdog.py:44`
  `_SPORT_ID = {"soccer_intl": "FIFA", "nba": "NBA", "mlb": "MLB"}`
- Provider works unchanged (single GET -> filter on the new `sport_id` -> parse).
- Extend the canonical stat map for NBA labels in `prop_base.py:29-71` (`_STAT_CANON`):
  `"points":"PTS","rebounds":"REB","assists":"AST","pts + rebs + asts":"PRA",
  "3-pointers made":"FG3M","steals":"STL","blocks":"BLK","turnovers":"TOV"`. Unknown labels
  pass through (`canon_stat`).
- Board surface: add the sport to `prop_edge._SUPPORTED` (`prop_edge.py:35`) AND route to an
  NBA per-player distribution. Today `_edge_for_line` (`prop_edge.py:137-219`) is hardwired to
  the soccer `prop_engine.prop_distribution`; for NBA dispatch on `line.sport` to the MC-sim
  prop ladder (`src/prediction/player_props.py`). Until that exists, the scraper still RECORDS
  Underdog NBA two-way lines (valuable for line history / CLV even with no board).
- Add `scheduled_at` to the emitted `PropLine` (new optional field on `PropLine` in
  `prop_base.py:89-110`) and populate from `game.get("scheduled_at")` in `parse_props`.

ADD a network-gated live smoke test alongside the existing unit tests
(`scripts/platformkit/test_prop_underdog.py`) that fetches the real endpoint once and asserts
at least one row for the mapped `sport_id` -- catches a silent shape/host change.
