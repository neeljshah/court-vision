# 03 -- Odds Aggregation + Player-Prop Scrapers + Normalization

Area owner doc for a deep project-understanding read. Scope: the OWN keyless
odds-aggregation service, the player-prop scrapers, the normalization layer, and
the value-engine pure functions that consume them.

Honesty framing (binding): markets are efficient. Nothing here claims a money edge.
The defensible win is CALIBRATION and EXECUTION-only line-shopping (a better price
than your own book), plus an honest CLV yardstick. Every "edge" surfaced is a
prob-vs-line gap or EV-vs-soft-price for DECISION SUPPORT only. All paths degrade
to an honest `unavailable` sentinel and never fabricate a price.

---

## 1. INVENTORY -- components that EXIST and are USED

Team-moneyline odds aggregation (`scripts/platformkit/odds_provider/`):

- `base.py` -- normalized team-odds schema `OddsEvent` + pure price converters
  (`american_to_decimal`, `prob_to_decimal`) + the `unavailable`/`is_unavailable`
  honest sentinel + the `Provider` Protocol.
- `http_cache.py` -- injectable `http_get_json` + TTL disk cache `disk_cache_get`
  (default TTL 60s, cache dir `~/.cache/courtvision_odds`, honest UA).
- `espn.py` -- keyless ESPN provider (`EspnProvider`): scoreboard + per-event
  `summary?event=` -> `pickcenter[]` republished sportsbook moneylines.
- `kalshi.py` -- keyless Kalshi public market-data provider (`KalshiProvider`):
  prediction-market YES asks -> two-way team-winner lines.
- `polymarket.py` -- best-effort Polymarket gamma provider (`PolymarketProvider`):
  two-outcome sports markets -> two-way lines.
- `team_resolver.py` -- `canonical(sport, name)` code<->full-name key resolver for
  NBA/MLB (the cross-source matching backbone).
- `aggregate.py` -- merges providers into one slate (`aggregate`), builds the
  `to_odds_lookup(sport)` closure that drops into `slate.build_slate`, and holds
  the load-bearing `teams_match` / `merge_events` matching logic.
- `__init__.py` -- re-exports the base schema; documents the honesty contract.

Player-prop scrapers (`scripts/platformkit/odds_provider/`):

- `prop_base.py` -- parallel prop schema `PropLine` + canonical stat vocabulary
  `canon_stat` + `PropProvider` Protocol. (Note: it is a DIFFERENT record than
  `OddsEvent` because a prop is one player+stat+line, not a two-way game.)
- `prop_underdog.py` -- keyless Underdog Fantasy provider (`UnderdogProvider`),
  `beta/v5/over_under_lines`, sport_id "FIFA" (World Cup). Emits real two-sided
  decimal odds (`payout_type="sportsbook"`) when `decimal_price` is present.
- `prop_prizepicks.py` -- keyless PrizePicks provider (`PrizePicksProvider`),
  `/leagues` + `/projections`, league resolved BY NAME ("WORLD CUP"). All rows are
  pick'em (`payout_type="dfs_pickem"`, prices None).
- `prop_fanduel.py` -- keyless FanDuel NJ sportsbook provider (`FanDuelProvider`)
  via a static public app key. Two-way American odds. BUILT but NOT yet wired into
  any consumer (see Limitations); also no props posted at the time of probe.

Value engine + normalization helpers (`scripts/platformkit/`):

- `odds_shop.py` -- pure value engine: `best_line`, `devig_twoway` (reuses the
  vetted Shin solver), `detect_arb`, `ev_vs_price`, `summarise_twoway`, plus a
  keyed-API client `fetch_odds` for The Odds API (`ODDS_API_KEY`, optional).
- `soccer_team_map.py` -- leak-free opponent-name -> FIFA `team_abbr` resolver for
  the prop board's opponent multiplier (`resolve_team_abbr`, `opponent_in_match`,
  `opp_mult_for_line`); biased to a safe no-op.
- `prop_edge.py` -- CONVERGENCE: joins scraped prop lines to the soccer per-player
  count model and emits a ranked, calibration-tiered candidate board
  (`build_prop_board`).
- `prop_line_history.py` -- closing-line capture + paper CLV for props.

Consumers (front end, `scripts/platformkit/frontend/`):

- `slate.py` -- `build_slate(sport, odds_lookup=...)` shapes the moneyline slate
  with best-line/arb/EV via `odds_shop.summarise_twoway`.
- `bet_board.py` -- per-game bet board; attaches book prices to moneyline rows.
- `serve.py` -- FastAPI surface wiring `to_odds_lookup` and `build_prop_board`.

Tests (per-file, present and used): `test_odds_provider.py`, `test_team_resolver.py`,
`test_prop_base.py`, `test_prop_underdog.py`, `test_prop_prizepicks.py`,
`test_prop_fanduel.py`, `test_odds_shop.py`, `test_soccer_team_map.py`,
`test_prop_edge.py`, `test_prop_edge_dispersion.py`, `test_prop_line_history.py`.

---

## 2. HOW IT WORKS -- data flow + key algorithms

### 2a. Normalized schemas (the two shapes)

Team odds = `OddsEvent` (`base.py:68`). The price field is shaped EXACTLY for the
value engine: `prices: {venue: {"home": dec, "away": dec, "draw": dec|None}}` where
`dec` is DECIMAL odds (>1.0). A side a venue does not quote is absent/None, never
fabricated.

Player props = `PropLine` (`prop_base.py:89`): `sport, event_id, match, player,
team, stat, line, over_price, under_price, payout_type, source, as_of`. `over_price`
/ `under_price` are decimal odds when the source quotes a true two-sided price
(`payout_type="sportsbook"`); a flat DFS pick'em sets both to None
(`payout_type="dfs_pickem"`) -- the explicit two-way vs pick-em distinction.

Price conversions (pure, unit-tested):
- `american_to_decimal(american)` (`base.py:36`): +150 -> 2.50, -175 -> 1.5714,
  0/None -> None.
- `prob_to_decimal(prob)` (`base.py:52`): implied prob in (0,1) -> 1/prob;
  out-of-range / >=1 -> None.

### 2b. Team-odds providers (sources)

ESPN (`espn.py`, keyless): `EspnProvider.fetch(sport)` (`espn.py:92`) GETs the
league scoreboard, then per event `summary?event=<id>` and runs
`parse_pickcenter(summary, home, away)` (`espn.py:49`) over `pickcenter[]`. Each
pickcenter entry is a distinct sportsbook -> venue key `espn:<provider>`. American
moneylines -> decimal; draw omitted (two-way home/away). League map
(`espn.py:31`): nba->basketball/nba, mlb->baseball/mlb, soccer->soccer/eng.1 (EPL),
soccer_intl->soccer/fifa.world. `max_events` default 20.

Kalshi (`kalshi.py`, keyless): `KalshiProvider.fetch` (`kalshi.py:135`) GETs
`/markets?limit=200&status=open`, filters by `event_ticker` prefix
(`_SERIES_HINT`, `kalshi.py:37`: nba->KXNBA, mlb->KXMLB, soccer->KXEPL,
soccer_intl->KXWC), groups markets by `event_ticker` (`group_markets`,
`kalshi.py:71`), and only emits an `OddsEvent` for an event with EXACTLY two team
markets both carrying a usable YES ask (`parse_events`, `kalshi.py:87`). YES ask in
dollars (=implied prob) via `_yes_ask_prob` (`kalshi.py:55`, falls back to
last_price then bid) -> `prob_to_decimal`. Optional `KALSHI_API_TOKEN` from ENV
only (not required for public reads). This is a PREDICTION-MARKET source: the two
YES asks are the two sides; home/away order is the market order and is fixed later
by the aggregator's name matching.

Polymarket (`polymarket.py`, best-effort): `PolymarketProvider.fetch`
(`polymarket.py:128`) GETs `/markets?active=true&closed=false&limit=200`, filters
by sport keyword in slug/question (`_SPORT_HINT`, `polymarket.py:35`), then
`parse_market` (`polymarket.py:65`) maps a two-outcome market: `outcomes` /
`outcomePrices` are JSON-STRING arrays (`_as_list`, `polymarket.py:52`),
outcome[0]->home, outcome[1]->away, each implied prob -> decimal. Non-two-way -> None.

All three NEVER raise; a scoreboard/markets failure degrades to `unavailable(...)`
and a single bad event/market is skipped.

### 2c. Aggregation + cross-source matching (the load-bearing risk)

`aggregate(sport, providers)` (`aggregate.py:156`) runs each provider, records
per-source health in `sources` (`"ok"` or the reason string), and merges whatever
is up via `merge_events` (`aggregate.py:123`). Output:
`{sport, status, as_of, sources, events: [OddsEvent.to_dict()...]}`; status is "ok"
if >=1 provider is up.

Matching is `teams_match(a, b, sport)` (`aggregate.py:65`) -- deliberately STRICT,
biased to false negatives (no odds) over false positives (WRONG game's price):
1. Code resolver path: if BOTH sides resolve to a known code/nickname for a coded
   sport (`_resolved_code_key`, `aggregate.py:30` -> `team_resolver.canonical`),
   compare canonical keys. So "BOS" links to "Boston Celtics" (nba:celtics) and
   "CIN" to "Cincinnati Reds" (mlb:reds), while CWS vs CHC and Knicks vs Nets stay
   distinct. `canonical` (`team_resolver.py:84`) collapses a code OR full name to
   `"<sport>:<nickname>"` using the static 30-team `_NBA_CODE_TO_NICK` /
   `_MLB_CODE_TO_NICK` maps plus alias maps and multi-word fixups (Red Sox ->
   redsox).
2. Name rule fallback (soccer/tennis or unknown team): exact normalized match, OR
   the last token (distinctive nickname) agrees AND token sets are subset-related
   or Jaccard >= 0.5. "Spurs" ~ "San Antonio Spurs" matches (subset); "Boston Red
   Sox" vs "Chicago White Sox" does NOT (Jaccard 0.2); "Knicks" vs "Yankees" does
   NOT. Aliases like "Man City" / "Manchester City" may MISS -> honest no-odds.

`_event_match` (`aggregate.py:101`) accepts either orientation; `_merge_into`
(`aggregate.py:111`) flips home/away sides if the orientations differ before
folding a later provider's venues in. The FIRST provider to mention a game owns its
orientation.

`to_odds_lookup(sport, providers)` (`aggregate.py:187`) aggregates ONCE up front,
then returns a closure `_lookup(s, home, away)` that re-matches each requested
matchup to a merged event, flips if needed, and returns
`{venue: {<home_name>: dec, <away_name>: dec}}` -- keyed by the CALLER's exact team
strings because `slate.summarise_twoway` is called with those names.

### 2d. Value engine (`odds_shop.py`, pure, no network)

- `best_line(book_prices)` (`odds_shop.py:48`): per side, the highest (bettor-
  favourable) decimal odds + its book. Skips prices <= 1.0.
- `devig_twoway(a, b)` (`odds_shop.py:73`): reuses `eval_gate.shin.shin_devig_decimal`
  (the vetted Shin solver, accounts for favourite-longshot bias) -> fair (p_a, p_b).
- `detect_arb(a, b)` (`odds_shop.py:84`): arb iff 1/a + 1/b < 1; returns booksum,
  margin_pct, and inverse-odds-proportional stakes summing to 1.0.
- `ev_vs_price(model_prob, decimal_odds)` (`odds_shop.py:114`): EV = p*odds - 1.
- `summarise_twoway(book_prices, side_a, side_b, model_prob_a=None)`
  (`odds_shop.py:127`): bundles best-line + devig + arb + optional model EV; missing
  sides -> None, never fabricated. THREE-WAY markets (soccer) suppress arb in the
  caller (`slate._THREE_WAY`, `slate.py:140`) because a home/away-only arb ignores
  the draw mass and reports phantom arbs.
- `fetch_odds(sport_key)` (`odds_shop.py:214`): The Odds API client, KEYED
  (`ODDS_API_KEY` from env only). Absent key or any failure -> status
  "unavailable". This is the only KEYED path in the area; it co-exists with the
  keyless `odds_provider` stack.

### 2e. Prop convergence (`prop_edge.build_prop_board`, `prop_edge.py:229`)

Flow: `_gather` (`prop_edge.py:79`) calls each prop provider's `fetch_props`,
records per-source health; default stack is `[UnderdogProvider(), PrizePicksProvider()]`
(`prop_edge.py:58`). Loads the soccer player-stats parquet
(`data/domains/soccer/espn_player_stats.parquet`, ~1241 rows, 48 teams = a single
WC corpus). For each `PropLine`, `_edge_for_line` (`prop_edge.py:137`):
1. Resolve player name to a `player_id` (`domains.soccer.player_resolver`).
2. Opponent multiplier `soccer_team_map.opp_mult_for_line` -- maps the OTHER team in
   `match` to a df `team_abbr` and pulls `team_defense.all_multipliers`; 1.0 when
   unmappable (never guesses a wrong abbr).
3. Two-pass Poisson->NegBinom: first pass learns lam, then re-distributes with the
   leak-free per-stat dispersion phi (`soccer_dispersion`) so a too-tight Poisson
   does not fabricate tail edges.
4. If a real two-sided price exists (`payout_type=="sportsbook"`): devig + EV both
   sides (`edge_basis="ev_vs_priced"`). Else pick'em: `model_gap=|p-0.5|`
   (`edge_basis="model_view"`).
5. `_ev_flag` flags `uncalibrated_thin` / `implausible` (|EV|>0.5).
Ranked by `prop_tiering.calibration_rank_key` -- CALIBRATION_PROVEN reliable edges
first; a weak-stat edge can never outrank a proven-stat one on raw EV. tier is
always "MODEL_VIEW".

---

## 3. HOW IT IS USED -- callers / consumers

- `frontend/serve.py` imports `to_odds_lookup` (`serve.py:46`) behind
  `FRONTEND_LIVE_ODDS` (ON by default; `serve.py:63`), exposed via `_odds_or_none`
  (`serve.py:94`). `/api/slate` (`serve.py:155`) passes `odds_lookup` into
  `slate.build_slate`; `/api/bet_board` style endpoint passes it to
  `game_bet_board`. Snapshot reads are preferred; a miss falls back to live compute.
- `frontend/serve.py` imports `build_prop_board` (`serve.py:58`) for the prop
  endpoint (`serve.py:203`); guarded to "unavailable" if not importable.
- `frontend/slate.py:158` -> `odds_shop.summarise_twoway`; `_book_fields`
  (`slate.py:143`) produces best_home/away_book/price, arb_pct, model_ev_best.
- `frontend/bet_board.py:32` uses `odds_shop.best_line` + `ev_vs_price`; book price
  is attached ONLY to Moneyline rows (the reliably shoppable market via the keyless
  feed); all other markets show fair odds only.
- `prop_edge.py` consumes `prop_underdog`, `prop_prizepicks`, `prop_base`,
  `odds_shop.devig_twoway`/`ev_vs_price`, and `soccer_team_map`.
- `prop_line_history.py`, `clv_ledger.py`, `pm_trading/` consume `odds_shop` /
  prop providers for paper CLV and the paper-trading loop.

---

## 4. STRENGTHS

- Genuinely KEYLESS breadth for the live board: ESPN (republished book moneylines),
  Kalshi (public market data), Polymarket (gamma), Underdog, PrizePicks, FanDuel
  (static public app key) -- no paid Odds API dependency for the default path. The
  one keyed source (`odds_shop.fetch_odds`/The Odds API) is optional and isolated.
- Disciplined honest-degrade contract everywhere: a uniform `unavailable(reason)`
  sentinel, providers NEVER raise, a single bad event/market/provider never sinks
  the slate, and NO price is ever fabricated. This is consistently enforced and
  unit-tested.
- Clean normalization: two purpose-built schemas (`OddsEvent` vs `PropLine`), pure
  network-free converters and value functions, fully injectable `http_get` so the
  whole stack tests with zero network on canned payloads.
- The two-way-vs-pick'em distinction is handled HONESTLY: pick'em sources carry no
  fabricated two-sided price (`payout_type="dfs_pickem"`, prices None), and EV is
  only computed where a real two-sided price exists.
- Cross-source matching is correctly biased to FALSE NEGATIVES. The same-city trap
  (Knicks/Yankees, White Sox/Cubs) is explicitly defended via the canonical
  code resolver and the nickname-last-token rule; this is the right risk posture.
- The value engine reuses the vetted Shin devig rather than a naive proportional
  devig, and suppresses phantom three-way arbs.
- Prop board ranking is calibration-led, not EV-led: proven-stat edges rank first,
  thin/implausible rows are flagged and demoted -- consistent with "calibration not
  edge."

---

## 5. LIMITATIONS / RISKS / GAPS / KNOWN BUGS (brutally honest)

Breadth is THIN and largely two-way moneyline only:
- ESPN `pickcenter` is a SINGLE republished book per event most of the time -- so
  "multi-book best-line / arb" usually has one venue and degenerates to that one
  line. Real arb/line-shopping needs several independent books; the keyless feed
  rarely supplies them.
- Kalshi/Polymarket are PREDICTION MARKETS, not sportsbooks. Their "price" is a YES
  ask / outcome price -> implied prob -> decimal. Treating that as a comparable
  book line is a stretch: liquidity is low, spreads wide, and the YES ask carries
  the market's own vig/skew. Mixing them into `best_line` can surface a "best"
  price that is not actually bettable at size.
- Only moneyline (h2h) for teams. No spreads/totals/team-totals from the keyless
  providers despite `bet_board` advertising ladders -- those rows are model-fair-
  odds only, never priced.

Player props are essentially a SINGLE-SPORT, SINGLE-TOURNAMENT prototype:
- All prop providers map ONLY `soccer_intl` (World Cup): Underdog sport_id "FIFA",
  PrizePicks "WORLD CUP", FanDuel "fifa-world-cup". No NBA/MLB/EPL prop scraping
  exists. `prop_edge._SUPPORTED == {"soccer_intl"}`.
- The model corpus is TINY and in-sample-adjacent: `espn_player_stats.parquet` is
  ~1241 player-rows / 48 teams = one tournament. The board's own honest_note admits
  tiering is "OUR OWN out-of-sample calibration on 24 WC matches" -- that is small-N;
  "CALIBRATION_PROVEN" on 24 matches is suggestive, NOT established, and should not
  be read as a profit/CLV claim (the note says so, correctly).
- FanDuel provider (`prop_fanduel.py`) is BUILT but STRANDED: it is in NO consumer
  (`prop_edge._default_providers` is Underdog+PrizePicks only; no non-test import).
  And per its own docstring, at probe time FanDuel had posted no WC prop markets, so
  the prop parser has never run against REAL prop data -- only against the
  moneyline/penalty market shape. It is unvalidated on its target payload.
- PrizePicks rows are ALL pick'em (no two-sided price), so every PrizePicks edge is
  `model_view` (gap from 0.5), never a priced EV. goblin/demon flex odds are
  acknowledged but not parsed.

Cross-source matching (the load-bearing correctness risk):
- The strict matcher trades recall for safety: aliases like "Man City"/"Manchester
  City", accented names, and World Cup neutral-site naming differences will MISS
  and silently show no odds. That is honest but degrades coverage exactly where the
  board needs it.
- The nickname-last-token rule is fragile for teams whose distinctive token is not
  the last word, or where two providers use different nicknames. Soccer/tennis have
  NO code resolver at all -- they ride entirely on loose name overlap.
- Kalshi home/away orientation is "market order"; correctness depends entirely on
  the aggregator's name match fixing it. If a Kalshi label is a city/abbrev the
  resolver does not know, the merge can attach a SIDE to the wrong team (flip) or
  drop it -- and prediction-market labels are not guaranteed to be full team names.
- `soccer_team_map` 3-letter-prefix fallback is a heuristic (compact name[:3]); it
  is guarded to require a unique df match, but country naming collisions are
  plausible and a wrong opponent abbr would silently distort lam (mitigated by the
  1.0 no-op default).

Robustness / quota / degrade:
- No per-source rate limiting or backoff beyond a 60s TTL disk cache
  (`http_cache.py`). ESPN does N+1 calls (1 scoreboard + 1 summary per event up to
  20) -- that is up to 21 requests per sport per cache miss. Underdog/PrizePicks/
  FanDuel providers ignore the cache entirely (`use_cache` is "reserved" and the
  default fetcher does a raw urllib GET). FanDuel does 1 page call + 1 per event.
- These are undocumented/unofficial endpoints (Underdog beta, PrizePicks api,
  FanDuel sbapi NJ, Kalshi elections host). They WILL break on schema/host/anti-bot
  changes; the honest-degrade contract means a break shows as "unavailable", not a
  crash, but also means the board silently goes empty.
- No staleness/odds-age surfaced to the consumer for the keyless team feed (the
  prop board has `as_of`; the team `OddsEvent` carries `as_of` but the slate row
  does not prominently expose it).
- The DraftKings-Playwright gap: there is NO DraftKings (or any headless-browser /
  Playwright) scraper. The `__init__` docstring explicitly scopes direct sportsbook
  scraping OUT (ToS). FanDuel is the lone real-sportsbook path and it is via a
  documented-ish public JSON app key, not a browser. So genuine sharp two-sided
  sportsbook breadth is absent.

Other:
- `summarise_twoway` mixing a prediction-market implied prob and an ESPN book
  decimal into one devig is apples-to-oranges (different vig structures); the fair
  prob is only as honest as the inputs.
- `KALSHI_API_TOKEN`/`POLYMARKET_API_TOKEN` `_token()` helpers are read but NOT
  attached to the request headers in the keyless GET path -- effectively dead code
  for now (public reads work without them, so harmless, but misleading).

---

## 6. PLAN TO GET BETTER (prioritized)

Quick wins (days):
1. Surface odds AGE on every slate/board row (`as_of` -> "X min old") and gray out
   stale lines. Cheap; directly improves trust and avoids acting on dead prices.
2. Wire `FanDuelProvider` into `prop_edge._default_providers` (and the team path
   has no FanDuel ML; consider one) behind a flag, and add a live-probe smoke test
   that records the REAL prop payload when WC props open, so the parser is finally
   validated on its target shape.
3. Tag each venue with a TYPE (`sportsbook` vs `prediction_market`) on `OddsEvent`
   and let `best_line`/the UI separate them, so a thin prediction-market "best"
   price is not presented as a bettable book line.
4. Add minimal per-source backoff + a shared cache for the prop providers (honor
   `use_cache`) to cut request volume and survive transient rate limits.
5. Expand `team_resolver` alias coverage for EPL/World Cup (Man City, Spurs, Wolves,
   national-team short names) -- a small static map closes the most common MISS
   cases without loosening the false-match guard.

Bigger bets (weeks):
6. Add a sport with a deep model (NBA props) end-to-end: an NBA prop provider
   (PrizePicks/Underdog NBA leagues already exist on the same keyless endpoints) +
   join to the existing NBA prop model surface. This is where the real
   data depth lives and where calibration claims can be properly cross-validated on
   many seasons, unlike the 24-match WC corpus.
7. A second/independent sportsbook line source for genuine multi-book best-line and
   honest arb detection (e.g. The Odds API h2h+spreads+totals via the existing
   `fetch_odds`, normalized into `OddsEvent`), clearly separated from prediction
   markets. Keeps the keyless default but adds a keyed "more books" mode.
8. Promote `prop_line_history` to run up to kickoff over a full tournament/season so
   CLV-vs-close is actually accrued and reported -- the honest yardstick currently
   has almost no data behind it.
9. Add spreads/totals to the keyless team feed where ESPN summary exposes them, so
   `bet_board` ladders carry real prices instead of fair-odds-only rows.
10. A focused, ToS-aware DraftKings (or additional book) ingest ONLY if a legitimate
    public JSON endpoint exists (mirroring the FanDuel sbapi approach); do NOT build
    a Playwright browser scraper -- it is fragile, ToS-hostile, and out of the
    stated scope.

---

## 7. HOW GOOD CAN IT GET -- honest ceiling

Realistic best: a robust, keyless, multi-sport odds-NORMALIZATION and decision-
SUPPORT layer that reliably surfaces (a) several real sportsbook moneylines per
game with correct team matching and surfaced staleness, (b) clearly-labeled
prediction-market prices kept separate, and (c) a multi-sport player-prop board
whose ranking is honestly calibration-tiered with accrued CLV. With one keyed
"more books" source it can do genuine line-shopping and occasionally flag a real
(fragile, limit-restricted) arb.

What limits the ceiling:
- It is a CONSUMER of efficient markets. Line-shopping/arb are EXECUTION edges (a
  better price than your own book), not predictive edges; both are thin, transient,
  and quickly limited in practice. No money-edge can or should be claimed.
- Keyless breadth is structurally capped: ESPN republishes ~one book, prediction
  markets are not sportsbooks, and unofficial endpoints break without notice.
  Real multi-book depth requires either paid feeds or fragile scraping.
- Prop calibration is only as good as the model corpus. The current WC corpus
  (~1241 rows / 24 matches) cannot establish more than "suggestive" calibration;
  the credible ceiling for the prop board lives in sports with deep multi-season
  data (NBA), where calibration can be cross-validated -- and even there the honest
  outcome is "match the devigged close," not beat it.
- Cross-source matching can be made high-recall with alias maps but its CORRECTNESS
  ceiling is bounded by ambiguous names; the right posture (false-negatives over
  false-positives) is already in place and should be kept.

Bottom line: this can become a genuinely solid, honest, multi-sport odds-
normalization + decision-support service with real (execution-only) line-shopping
value. It will never be, and should never be marketed as, a profit engine.
