# DATASOURCE: The Odds API -- KEYED genuine multi-book sportsbook odds (P3 line-shopping / arb)

_Part of the edge-intelligence corpus (_scrapers/deep/). Per-source deep spec for The Odds API,
the ONLY genuine multi-book sportsbook feed in the stack. Grounded in
`scripts/platformkit/odds_shop.py`, `base.py`, `aggregate.py`, and project-deep-dive 03
(sec 5 + plan item 7) + _scrapers/data-acquisition.md B2. ASCII only._

EDGE-UNLOCK: **P3 (stale/soft-line line-shopping) + arb** -- an EXECUTION edge (a better price
than your own book), NOT a predictive edge (cut-list CUT 6: arb is fragile, not a profit
center; line-shopping IS the durable execution edge). TIER: HYPOTHESIS (execution; thin,
transient, limit-constrained). This is the ONLY source emitting genuine SPORTSBOOK multi-book
breadth, so it is the only source that makes `best_line`/`detect_arb` meaningful for BETTABLE
team markets.

---

## 1. Endpoint + auth

- Base: `https://api.the-odds-api.com/v4` (`odds_shop.py:40`).
- Call: `GET /sports/<sport_key>/odds?apiKey=<key>&regions=us&markets=h2h&oddsFormat=decimal`
  (`odds_shop.py:232-238`). Defaults: `DEFAULT_REGIONS="us"`, `DEFAULT_MARKETS="h2h"`
  (`:41-42`); `oddsFormat=decimal` is HARD-CODED (the parser assumes decimal, `:184`).
- AUTH: **KEYED**. `_api_key()` (`odds_shop.py:171-174`) reads `ODDS_API_KEY` from ENV ONLY;
  NO committed/legacy key is ever consulted (the old key is flagged for rotation in the
  security gate, `:11-13`). Absent key -> `{"status":"unavailable", "reason":"ODDS_API_KEY not
  set in env (live odds disabled)"}` (`:229-231`). This is the ONLY keyed path in the odds
  stack and is deliberately isolated from the keyless default providers.
- QUOTA: keyed + quota-limited (cost per request, region/market multipliers). The project keeps
  it as an OPTIONAL "more books" mode behind the keyless ESPN/Kalshi/Polymarket default
  (deep-dive 03 plan item 7). It is NOT in `aggregate.default_providers` (`aggregate.py:145`).
- NO caching layer here: `fetch_odds` uses a bare `_http_get_json` (`:208-211`, urllib, 20s
  timeout), not `http_cache.disk_cache_get`. Because requests cost quota, a poll-up-to-kickoff
  loop MUST add its own TTL/dedup or it will burn the quota.

## 2. What markets it covers

- `h2h` (moneyline) by default; the API also serves `spreads`, `totals`, and player-prop
  markets per book, selectable via the `markets` arg (`fetch_odds(..., markets="h2h,totals")`).
  The parser `parse_event_books` takes ONE `market_key` at a time (default `"h2h"`, `:177`).
- One event returns MANY bookmakers, each with its own markets/outcomes -- genuine multi-book
  breadth (this is the whole point vs ESPN's single republished book).
- `sport_key` is The-Odds-API's own key (e.g. `basketball_nba`, `baseball_mlb`,
  `soccer_epl`, `soccer_fifa_world_cup`, `tennis_atp_*`), NOT the internal sport name -- a
  mapping layer is required when wiring it behind the aggregate seam (see sec 4 gap).

## 3. Schema -> normalized mapping (the exact code path)

`fetch_odds` returns `{"status":"ok","events":[<raw The-Odds-API event>, ...]}` (`:248`). The
pure parser turns ONE event into the book-prices shape:

```
parse_event_books(event, market_key="h2h")    (odds_shop.py:177)
  for bm in event["bookmakers"]:               # each bookmaker = a real sportsbook
    title = bm["title"] or bm["key"]
    for mk in bm["markets"]:
      if mk["key"] != market_key: skip
      for oc in mk["outcomes"]:
        name  = oc["name"]; price = float(oc["price"])   # decimal
        if name and price > 1.0: side_prices[name] = price
      books[title] = side_prices
  -> {book_title: {outcome_name: decimal_odds}}
```

This `{book: {side: decimal}}` dict is the EXACT input to the pure value engine:
- `best_line(book_prices)` (`:48`) -> per side, the highest decimal + its book.
- `devig_twoway(a, b)` (`:73`) -> Shin no-vig fair probs (`eval_gate.shin.shin_devig_decimal`).
- `detect_arb(best_a, best_b)` (`:84`) -> arb iff `1/a + 1/b < 1`, with split stakes.
- `summarise_twoway(book_prices, side_a, side_b, model_prob_a=None)` (`:127`) bundles all three
  (+ optional `ev_vs_price`, `:114`).

NOTE: `parse_event_books` produces book-keyed prices but does NOT itself emit an `OddsEvent`.
To enter the aggregate/`odds_lookup` seam it must be wrapped in a Provider (see sec 4 gap).

## 4. How it flows into odds_shop / odds_lookup (and the WIRING GAP)

- DIRECT (today): `odds_shop.fetch_odds` + the pure functions are called directly for
  decision-support on team markets; the unit tests exercise the pure functions network-free.
- AGGREGATE SEAM (gap): The Odds API is NOT yet a `base.Provider` and is NOT in
  `default_providers`. To put its multi-book prices on the merged board it needs a thin
  `TheOddsApiProvider.fetch(sport)` that (a) maps internal sport -> `sport_key`, (b) calls
  `fetch_odds`, (c) per event runs `parse_event_books`, (d) emits an `OddsEvent` with
  `prices={book_title: {"home":dec,"away":dec,"draw":...}}` for EACH book (multi-venue),
  `venue_type="sportsbook"`, degrading to `unavailable` on missing key/failure. This is the
  sanctioned "more books" path (deep-dive 03 plan item 7) and the only way `best_line`/
  `detect_arb` become meaningful instead of degenerating to ESPN's single book.

## 5. Prediction-market-vs-sportsbook distinction (this is the GOOD side)

The Odds API is a genuine SPORTSBOOK aggregator -> `venue_type="sportsbook"`. Its books ARE
the bettable side that `best_line`/`detect_arb` should operate on, and they are the correct
"fair close" reference for devig. This is precisely the venue class that Kalshi/Polymarket must
be kept SEPARATE from: cross-book line-shopping among The-Odds-API sportsbooks is P3 (real,
execution); a The-Odds-API-vs-Kalshi gap is P4 (divergence signal). Keep the two classes in
distinct lanes.

HONEST CAVEATS (binding): a +EV vs a SOFT book here is an EXECUTION opportunity, NOT a
beat-the-sharp-close edge -- `ev_vs_price` must be evaluated against the BEST price you can
ACTUALLY bet, never against a closing line as if you could take it (`odds_shop.py:16-22,
114-124`). Arbs are RARE, vanish fast, and books limit/void winners (`:84-95`, cut-list CUT 6):
treat them as fragile, not a standing income stream.

## 6. The MISSING closing-line capture plan (The-Odds-API-specific) -- HIGHEST-VALUE for true CLV

This is the source that makes a real multi-book "fair close" computable (sharpens the
single-venue ESPN proxy in _scrapers/closing-line-and-clv.md).

1. POLL `fetch_odds(sport_key, markets="h2h")` (and `totals`/props as quota allows) on a
   cadence up to kickoff -- but ADD a TTL/dedup cache (this client has none, sec 1) so quota is
   not burned; sample densest in the final hour (lines move most then,
   closing-line-and-clv.md sec 5).
2. LOG per tick tagged `venue_type="sportsbook"`, `source="the_odds_api"`, with
   `{event_id, book_title, side, decimal, sport_key, commence_time, ts}` -- one row per
   book per side, so per-book trajectories are preserved.
3. CLOSE = last row with `ts < commence_time` per (event, book). The MULTI-BOOK fair close =
   `devig_twoway` over the consensus / sharpest book's two-way at close.
4. CLV = `clv_ledger.compute_clv(side, taken_decimal, closing_home, closing_away)` against the
   captured close -> the FORWARD CLV that gates real money (proof-standards.md). Unlike ESPN's
   single book, the multi-book close gives a true fair-close, sharpening every "would this pay?"
   claim (data-acquisition A4/B2; deep-dive 12 limitation 5).
5. COST DISCIPLINE: because it is keyed/quota-limited, capture only the markets/events actually
   on the paper board; do not poll the full sports catalog.

## 7. Honest cut / keep verdict

KEEP as the SANCTIONED "more books" + true-CLV-reference path, behind the `ODDS_API_KEY` flag.
It is the right way to get multi-book breadth WITHOUT a fragile browser scraper (the
DraftKings-class option is scoped OUT, data-acquisition D4). CUT expectations that it yields a
predictive edge: line-shopping/arb are execution-only and limit-constrained. Build the
`TheOddsApiProvider` wrapper + the TTL cache before any poll loop, and always tag
`venue_type="sportsbook"` so it joins the bettable lane, not the P4 divergence lane.
