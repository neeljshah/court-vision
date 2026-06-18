# 02 -- Coverage Plan: list as many real betting opportunities as possible

> Goal (north star for this doc): the board surfaces EVERY event The Odds API can
> return, with the BEST line per side across books, arbitrage flags, and -- where we
> have a predictor -- model +EV. Maximize COVERAGE first (model-free), layer model
> edge on top only where we can price it.
>
> Honesty contract (binding, unchanged): line-shopping / best-line / arbitrage are
> EXECUTION features that need NO model and claim NO predictive edge. Model +EV is
> evaluated against the BEST price we can actually bet, never a closing line. Any
> feed down -> `status="unavailable"` with an as-of timestamp, never a fabricated
> number. New code only under `scripts/platformkit/` or `domains/` (src/kernel/api
> human-gated), <=300 LOC/file, per-file test note. No edge claim on public repo.

Date: 2026-06-17. ASCII only.

---

## 0. The key insight (validate + document)

**Line-shopping, best-line, and arbitrage are MODEL-FREE.** They only need two or
more books quoting the same market on the same event. `odds_shop.py` already proves
this: `best_line`, `devig_twoway`, `detect_arb`, `summarise_twoway` are pure
functions that take a `{book: {side: decimal_odds}}` dict and need NOTHING from any
predictor. `summarise_twoway(..., model_prob_a=None)` already returns best-line +
devig + arb with the model fields left `None`.

Consequence for coverage: **we can cover EVERY sport and EVERY event The Odds API
returns** for best-line + devig-fair-prob + arbitrage, the instant we ingest its
odds -- with zero new models. Model +EV is an additive overlay applied ONLY on the
5 sports we already price (NBA, MLB, club soccer, intl soccer, tennis). The board's
opportunity count is therefore bounded by API breadth, not by model breadth.

This splits every (sport, market) into three tiers:

- **(a) PRICE + SHOP** -- we emit a model prob AND multiple books quote it. Full
  row: best-line, devig, arb, model_ev. (the 5 domains' emitted markets)
- **(b) SHOP-ONLY** -- multiple books quote it, no model. Row still has best-line,
  devig-fair-prob, arb. This is the bulk of coverage (NFL, NHL, NCAA, MMA, cricket,
  golf, all soccer leagues we do not model, every prop/period market). MODEL-FREE.
- **(c) GAP** -- would need a new model to PRICE; until then it lives as (b).

The product rule: **never gate a row on having a model.** A (b) row is a real,
shippable betting opportunity (a better price than your own book + arb alerts).

---

## 1. The Odds API full catalog (what we can pull)

Base `https://api.the-odds-api.com/v4`. Key from env `ODDS_API_KEY` ONLY.
Every response carries `x-requests-remaining` / `x-requests-used` headers --
the quota meter we must read and budget against.

### 1.1 Endpoints + credit cost (the credit model)

| Endpoint | Returns | Credit cost |
|---|---|---|
| `GET /sports` | all sport keys (live; `?all=true` incl. out-of-season) | **FREE** |
| `GET /sports/{key}/events` | event ids + teams + commence times | **FREE** |
| `GET /sports/{key}/odds` | featured markets, all books | `#markets x #regions` |
| `GET /sports/{key}/events/{id}/odds` | ANY market (props/alt/periods) | `#unique-markets-returned x #regions` |
| `GET /sports/{key}/events/{id}/markets` | which markets exist for event | 1 flat |
| `GET /sports/{key}/scores` | live + final scores | 1 (2 if `daysFrom`) |
| `GET /historical/.../odds` | snapshot featured odds | **10 x** #markets x #regions |
| `GET /historical/.../events/{id}/odds` | snapshot any market | #markets x #regions |

Cost rules that drive the whole design:
- Formula is `markets x regions`. 3 markets x 1 region = 3 credits; 1 market x 3
  regions = 3.
- **`/sports` and `/events` are FREE** -- the intended way to enumerate the entire
  board before spending a single credit. This is the lever for "100s of events
  without burning the API."
- **Empty responses are NOT charged.** Asking a per-event endpoint for markets a
  book does not offer costs nothing for the absent markets (charged by *unique
  markets returned*).
- Featured markets (`h2h`, `spreads`, `totals`, `outrights`) are on the cheap main
  `/odds` endpoint -- ONE call returns ALL events for a sport with ALL books.
- Player props / alternates / periods are ONLY on the per-event endpoint -> one
  paid call PER EVENT. This is the expensive lane; gate it behind freshness/demand.

Pricing tiers (USD/mo): free 500 cr; 20K $30; 100K $59; 5M $119; 15M $249. All
tiers include all sports/markets/books + historical. Free tier ~10 req/min.

### 1.2 Sport keys (the breadth)

- **American football:** `americanfootball_nfl`, `_nfl_preseason`, `_ncaaf`,
  `_cfl`, `_ufl`, plus futures `_nfl_super_bowl_winner`, `_ncaaf_championship_winner`
- **Basketball:** `basketball_nba` (we model), `_nba_preseason`, `_wnba`, `_ncaab`,
  `_wncaab`, `_euroleague`, `_nbl`, futures `_nba_championship_winner`
- **Baseball:** `baseball_mlb` (we model), `_mlb_preseason`, `_milb`, `_npb`,
  `_kbo`, `_ncaa`, futures `_mlb_world_series_winner`
- **Ice hockey:** `icehockey_nhl`, `_nhl_preseason`, `_ahl`, `_liiga`,
  `_sweden_hockey_league`, `_sweden_allsvenskan`, `_mestis`, futures `_nhl_championship_winner`
- **Soccer (~70 keys):** club leagues `soccer_epl`, `_efl_champ`, `_spain_la_liga`,
  `_italy_serie_a`, `_germany_bundesliga`, `_france_ligue_one`,
  `_netherlands_eredivisie`, `_portugal_primeira_liga`, `_usa_mls`,
  `_mexico_ligamx`, `_brazil_campeonato`, `_argentina_primera_division`,
  `_japan_j_league`, `_saudi_arabia_pro_league`, ... (we model several);
  **international (explicit, World Cup lane):** `soccer_fifa_world_cup`,
  `soccer_fifa_world_cup_qualifiers_europe`, `_qualifiers_south_america`,
  `soccer_fifa_world_cup_womens`, `soccer_fifa_world_cup_winner` (futures),
  `soccer_uefa_champs_league`, `_uefa_europa_league`, `_uefa_europa_conference_league`,
  `_uefa_nations_league`, `_uefa_european_championship`, `_uefa_euro_qualification`,
  `soccer_conmebol_copa_america`, `_copa_libertadores`, `_copa_sudamericana`,
  `soccer_concacaf_gold_cup`, `_leagues_cup`, `soccer_fifa_club_world_cup`,
  `soccer_africa_cup_of_nations` (we model these via `soccer_intl`)
- **Tennis (tournament-scoped, rotate seasonally -- enumerate via `/sports`):**
  ATP `tennis_atp_*` (aus_open, french_open, wimbledon, us_open, the masters/500s),
  WTA `tennis_wta_*` (we model both ATP + WTA)
- **Other (model-free shop-only coverage):** `mma_mixed_martial_arts`,
  `boxing_boxing`, `cricket_*` (ipl, big_bash, t20_world_cup, test_match, odi, ...),
  `golf_*` (winner futures), `aussierules_afl`, `rugbyleague_nrl`,
  `rugbyunion_six_nations`, `lacrosse_pll`/`_ncaa`, `handball_germany_bundesliga`,
  `politics_us_presidential_election_winner`

Always call `/sports` live to get current keys -- tennis/golf tournament keys come
and go each season.

### 1.3 Market keys

- **Featured (cheap, main endpoint):** `h2h`, `spreads`, `totals`, `outrights`
  (+ exchange `h2h_lay`, `outrights_lay`)
- **Game-level additional (per-event):** `alternate_spreads`, `alternate_totals`,
  `btts`, `draw_no_bet`, `h2h_3_way`, `team_totals`, `alternate_team_totals`
- **Periods (per-event):** quarters `*_q1..q4`, halves `*_h1/h2`, hockey periods
  `*_p1..p3`, baseball innings `*_1st_{1,3,5,7}_innings`, tennis sets `*_s1/s2`
  for h2h/spreads/totals/alt variants
- **Player props (per-event only):**
  - NBA/WNBA/NCAAB: `player_points`, `_rebounds`, `_assists`, `_threes`, `_blocks`,
    `_steals`, `_turnovers`, `_points_rebounds_assists` (+ combos), `_double_double`,
    `_triple_double`, `_first_basket`, `_fantasy_points`, `*_alternate`, `*_q1`
  - NFL: `player_pass_yds`, `_pass_tds`, `_rush_yds`, `_receptions`, `_reception_yds`,
    `_anytime_td`, `_1st_td`, kicking/defense props, `*_alternate`
  - MLB: batter `batter_home_runs`, `_hits`, `_total_bases`, `_rbis`, `_strikeouts`,
    `_runs_scored`, ...; pitcher `pitcher_strikeouts`, `_outs`, `_earned_runs`, ...
  - NHL: `player_points`, `_goals`, `_assists`, `_shots_on_goal`, `_goal_scorer_anytime`
  - Soccer: `player_goal_scorer_anytime`, `_assists`, `_shots_on_target`

### 1.4 Regions + books

`regions = us, us2, uk, eu, au` (comma-delimited; or `bookmakers=` filter where each
group of 10 books counts as 1 region for cost).
- **us:** DraftKings, FanDuel, BetMGM, Caesars, BetRivers, Bovada, BetOnline, ...
- **us2:** ESPN Bet, Hard Rock, Fanatics, Fliff, ...
- **uk:** Bet365, William Hill, Paddy Power, Betfair (exchange+sportsbook), ...
- **eu:** **Pinnacle** (sharpest reference), Betfair Exchange, 1xBet, Betsson, ...
- **au:** Sportsbet, TAB, Ladbrokes AU, Neds, Betfair Exchange, ...

Coverage lever: more regions = more books = more best-line spread = more arbs. But
cost scales linearly with regions. Default `us` + `eu` (DK/FD/MGM + Pinnacle) gives
the most arb-relevant book set for 2x cost.

---

## 2. What WE can price (the 5 domains) vs what books offer

Entrypoints: `domains/<d>/predictor.py :: <X>Predictor.predict(...)` (+ `.predict_live`).

| Domain | Odds API key(s) | Emitted markets (tier-a PRICE+SHOP) |
|---|---|---|
| basketball_nba | `basketball_nba` | h2h (p_home/away_win), spreads (margin_home), totals (5 lines), in-game |
| mlb | `baseball_mlb` | h2h, run-line -1.5 (spreads), totals (5 lines), in-game |
| soccer (club) | `soccer_epl`, `_spain_la_liga`, `_italy_serie_a`, `_germany_bundesliga`, `_france_ligue_one`, `_efl_champ` | h2h_3_way (1X2), totals 2.5, btts, correct-score, in-game |
| soccer_intl | `soccer_fifa_world_cup`, `_uefa_*`, `_conmebol_*`, `_concacaf_*`, qualifiers | h2h_3_way (1X2, neutral-site), totals 2.5, btts, correct-score |
| tennis | `tennis_atp_*`, `tennis_wta_*` | h2h (match win), totals (games), straight-sets, holds, in-game |

**Books offer FAR more than we price:** every props market, every alternate line,
every period/half/quarter market, and ~every other sport (NFL/NHL/NCAA/MMA/cricket/
golf/...). All of those are tier-(b) SHOP-ONLY today -- still real, shippable rows
via the model-free path. Tier-(c) GAPS we would model next: NBA/MLB player props
(we already have NBA prop models in `src/`, AST is the one durable edge -- a future
bridge), NFL/NHL team markets, soccer correct-score expansion.

Mapping line: club-soccer totals are O/U 2.5 only in our predictor, but books quote
many total lines + `alternate_totals` -> the 2.5 row is tier-a, other lines tier-b.

---

## 3. The coverage plan (P0 ingestion design)

### 3.1 Design: one generic multi-sport fetcher over `odds_shop.py`

`odds_shop.py` already has the pure core (best-line/devig/arb/EV) and a single-sport
`fetch_odds(sport_key, regions, markets)`. It is MISSING: `/sports` + `/events`
discovery, a commence-time window, a sport-key registry, quota accounting, and a
TTL cache. P0 adds a thin generic layer in `scripts/platformkit/` (each <=300 LOC,
each with a per-file test; do NOT touch src/kernel/api):

1. **`odds_catalog.py`** -- FREE-endpoint enumerator.
   - `list_sports()` -> calls `/sports`, returns active keys (cache 24h).
   - `list_events(sport_key, hours_ahead=48)` -> `/events` with
     `commenceTimeFrom/To`, returns event ids + teams + start times. FREE.
   - This is how we surface 100s of events for $0: enumerate every active sport,
     enumerate every event in the window, all free. The board can show the full
     fixture list before any priced odds call.

2. **`sport_registry.py`** -- static map: Odds API key <-> (our domain | None) <->
   default markets per sport-shape. h2h for everything; +spreads,totals where the
   book shape supports it (basketball/football/hockey/baseball); +h2h_3_way/btts
   for soccer. Marks each sport tier-a (has domain) or tier-b (shop-only).

3. **`odds_board.py`** -- the orchestrator that produces the opportunity rows.
   - For each active sport: `fetch_odds(key, regions, featured-markets)` (one cheap
     call returns all events x all books).
   - `parse_event_books` per event per market -> `summarise_twoway` (or 3-way for
     soccer 1X2). If sport maps to a domain, pass `model_prob_a` from the predictor
     -> tier-a row with model_ev; else `None` -> tier-b shop-only row.
   - Emits a flat list of opportunity rows: every event x every featured market x
     {best_line, devig_fair, arb_flag, model_ev|None}. This is the board feed.

4. **`quota.py`** -- read `x-requests-remaining` from response headers (extend
   `_http_get_json` to return headers), persist a daily spend ledger, and expose a
   budget guard so the per-event prop lane never blows the monthly cap. Degrade to
   `unavailable` when budget is exhausted -- never fabricate.

`build_slate` in `frontend/slate.py` already accepts injectable `matchups=`,
`market_lookup=`, `odds_lookup=` -- `odds_board.py` fills exactly those seams
(see 04_freshness_arch.md). No frontend rewrite needed.

### 3.2 What to ingest FIRST (max opportunities per credit)

Ordered by opportunities-per-credit (featured markets, 1-2 regions):

1. **Free enumeration sweep** (cost 0): `/sports` + `/events` for ALL active sports
   in a 48h window. Instantly populates the board with hundreds of real fixtures
   (NFL, NBA, MLB, NHL, all soccer leagues incl. World Cup, tennis, MMA, ...). This
   alone is a massive coverage jump and costs nothing.
2. **Featured h2h, all sports, region=us** (cost = 1/sport-call, each call returns
   ALL events x ALL us books). Adds best-line + devig + arb to every event. ~1
   credit per sport per refresh -> the whole board priced for ~30-40 credits.
3. **Add region=eu** (Pinnacle) on the same featured pull (2x cost) -> sharpest
   devig baseline + cross-region arbs (us vs eu books).
4. **Add spreads+totals** on the sports that have them (basketball/football/hockey/
   baseball): featured, cheap (markets x regions). Tier-a where we model.
5. **Soccer h2h_3_way + totals + btts** for our modelled leagues + World Cup ->
   tier-a 1X2 rows with model_ev.
6. **Per-event prop lane (expensive, gated):** only for high-demand tier-a sports
   (NBA, MLB) and only for events inside a short pre-game freshness window, and only
   the props we can or plan to model. Budget-capped via `quota.py`.

### 3.3 Quota budgeting strategy

- **Enumerate free, price cheap, prop sparingly.** `/sports`+`/events` always free;
  featured `/odds` is one call per sport (covers all its events); props are the only
  per-event spend and are demand+freshness gated.
- **Cache with TTL:** featured odds TTL ~3-5 min (matches free-tier refresh);
  `/sports` 24h; `/events` ~15 min. Serve from cache between refreshes -> no repeat
  spend. Stale-beyond-TTL -> `unavailable` + as-of timestamp, never silent.
- **Region discipline:** default `us`; add `eu` only where arbs/Pinnacle-devig pay
  for the 2x. Never blanket all 5 regions.
- **Budget guard:** daily credit cap from `quota.py`; when near the monthly cap, the
  prop lane shuts off first, then extra regions, then extra markets -- featured-h2h
  on us stays last so the board never goes dark.
- **Tier suggestion:** the $59/100K plan comfortably runs the full featured board
  (all sports, us+eu, 5-min refresh ~ a few thousand cr/day) with headroom for a
  gated prop lane. Start on free 500 to validate plumbing, then upgrade.

### 3.4 World Cup / international soccer (explicit)

`soccer_intl` predictor already supports neutral-site (`neutral=True`, World Cup
default) and emits 1X2 + O/U 2.5 + BTTS + correct-score. Map it to
`soccer_fifa_world_cup` (+ qualifiers, UEFA/CONMEBOL/CONCACAF, Euros, Copa America,
AFCON, Club World Cup). During a World Cup these are top-demand tier-a events: free
`/events` enumeration shows the full bracket; featured `h2h_3_way`+`totals` priced
cheap with model_ev; futures via `outrights` on `soccer_fifa_world_cup_winner`
(tier-b, shop-only -- we do not price tournament winner). This is a marquee
coverage win that needs no new model.

---

## 4. Summary

- **Full breadth available:** ~30+ sport families, ~70 soccer keys, ATP/WTA tennis,
  featured markets (h2h/spreads/totals/outrights) + every player-prop / alternate /
  period market, across us/us2/uk/eu/au books. `/sports` and `/events` are FREE.
- **Model-free coverage insight (validated):** best-line, devig, and arbitrage in
  `odds_shop.py` are pure functions needing only multi-book odds -- so we can cover
  EVERY event the API returns as tier-(b) shop-only rows, and add model +EV only on
  the 5 sports we already price. Coverage is bounded by API breadth, not models.
- **P0 ingestion plan:** add `odds_catalog.py` (free /sports+/events enumeration),
  `sport_registry.py` (key<->domain<->markets map), `odds_board.py` (generic
  orchestrator over the existing `odds_shop` pure core, filling `slate.build_slate`'s
  injectable seams), and `quota.py` (header-based credit ledger + budget guard). All
  under `scripts/platformkit/`, <=300 LOC each, per-file tests, src/kernel/api
  untouched. Ingest order: free enumeration sweep -> featured h2h (us) -> +eu/Pinnacle
  -> +spreads/totals -> soccer 1X2/World Cup -> gated per-event prop lane.

Files touched (proposed, P0): NEW `scripts/platformkit/odds_catalog.py`,
`sport_registry.py`, `odds_board.py`, `quota.py` (+ per-file tests). EXTEND
`scripts/platformkit/odds_shop.py::_http_get_json` to surface response headers.
WIRE via `scripts/platformkit/frontend/slate.py` existing injectable callbacks.
See `04_freshness_arch.md` for the refresh/scheduler layer this feeds.
