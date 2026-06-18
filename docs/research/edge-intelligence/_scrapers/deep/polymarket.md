# DATASOURCE: Polymarket Gamma -- best-effort keyless prediction-market lines (P4, NOT bettable book)

_Part of the edge-intelligence corpus (_scrapers/deep/). Per-source deep spec for the
Polymarket Gamma feed. Grounded in `scripts/platformkit/odds_provider/polymarket.py`,
`base.py`, `aggregate.py`, `odds_shop.py`, and project-deep-dive 03 (sec 5) +
_scrapers/data-acquisition.md B4. ASCII only._

EDGE-UNLOCK: **P4 (prediction-market vs sportsbook divergence)** -- a SECOND prediction-market
crowd (distinct from Kalshi). TIER: HYPOTHESIS. Like Kalshi, it is NOT a sportsbook and MUST be
tagged `venue_type="prediction_market"`, never mixed into a bettable `best_line`.

---

## 1. Endpoint + auth

- Base: `https://gamma-api.polymarket.com` (`polymarket.py:30`).
- Call: `GET /markets?limit=200&active=true&closed=false` (`polymarket.py:132-133`,
  `urlencode({"limit": page_limit, "active":"true", "closed":"false"})`).
- AUTH: KEYLESS for read-only market data. `_token()` (`:47-49`) reads `POLYMARKET_API_TOKEN`
  from ENV only and (like Kalshi) is NOT attached to any request -- public reads do not need
  it. Do not wire it in.
- Caching: `disk_cache_get` (60s TTL) when `use_cache=True` (default).
- There is NO clean per-league filter on gamma `/markets`; the provider pulls active markets
  and filters by a SPORT KEYWORD in the slug/question (crude but honest -- a non-match is
  skipped, `:101-104`).

## 2. What markets it covers

- TWO-OUTCOME sports markets only (e.g. `["TeamA","TeamB"]`) -> a two-way line.
- Sport keyword filter `_SPORT_HINT` (`polymarket.py:35-40`):
  `nba->["nba","basketball"]`, `mlb->["mlb","baseball"]`,
  `soccer->["epl","premier-league","soccer"]`, `soccer_intl->["world-cup","world cup","fifa"]`.
  Sport not in this map -> `unavailable` (`:130-131`).
- The keyword filter is LOOSE (substring match on `slug + question`, `:102-103`) -- it can
  admit non-game markets (futures, "will X win the title") that happen to contain the keyword,
  or MISS a game whose slug uses different wording. This is the main coverage/precision risk.
- Non-two-way markets (3-way soccer with a draw, multi-candidate futures) -> `parse_market`
  returns `None` (`:73-74`), so `draw` is always `None` (`:85`). NO props, NO totals.

## 3. Schema -> OddsEvent mapping (the exact code path)

Gamma encodes `outcomes` and `outcomePrices` as JSON-STRING arrays (sometimes already lists),
each price an implied probability in [0,1]. `_as_list` (`polymarket.py:52-62`) tolerates both.

```
body -> list (or body["data"])  (:139-142)
parse_markets(markets, sport)   (:97)
  for m:
    blob = (slug + " " + question).lower()
    if hints and no hint in blob: skip          # keyword filter  (:102-104)
    parse_market(m, sport):                      (:65)
      outcomes = _as_list(m["outcomes"])         # ["TeamA","TeamB"]
      prices   = _as_list(m["outcomePrices"])    # [p0, p1] in [0,1]
      if len(outcomes)!=2 or len(prices)!=2: None # non-two-way -> skip
      dec_home = prob_to_decimal_safe(prices[0])  # 1/p0, tolerant of str  (:89)
      dec_away = prob_to_decimal_safe(prices[1])  # 1/p1
      eid = m["id"] or m["slug"] or m["conditionId"]
      OddsEvent(event_id=eid, sport, home=outcomes[0], away=outcomes[1],
                commence_time=m["startDate"] or m["endDate"],
                prices={"polymarket": {"home": dec_home, "away": dec_away, "draw": None}},
                source="polymarket", as_of=now_iso())
```

Mapping convention: `outcome[0] -> home`, `outcome[1] -> away` (`:82`). Orientation is
therefore arbitrary (Polymarket has no home/away concept) and is fixed downstream ONLY by
`aggregate.teams_match` name-matching -- a brittle point identical to Kalshi.

## 4. How it flows into the odds_shop / odds_lookup seam

Identical path to Kalshi: `PolymarketProvider` is in `aggregate.default_providers`
(`aggregate.py:145-153`); `merge_events` folds the `{"polymarket": {...}}` venue dict into the
per-game OddsEvent; `to_odds_lookup` -> `slate.build_slate` -> `odds_shop.summarise_twoway`
runs `best_line`/`devig_twoway`/`detect_arb` over all venues including `"polymarket"`.

## 5. THE PREDICTION-MARKET-vs-SPORTSBOOK DISTINCTION (binding)

Same rule as Kalshi (see deep/kalshi.md sec 5) and it bites HARDER here:
- `outcomePrices` are mid/last prices on a continuous-double-auction; the implied prob can be
  stale, thinly-quoted, or reflect a tiny last trade -> a `prob_to_decimal` that looks like a
  great "best" price but is unfillable.
- The loose keyword filter can admit a FUTURES market (season-long) and mis-attach it to a
  single game via `teams_match`, producing a categorically wrong line. Polymarket markets must
  additionally be gated to single-GAME markets (e.g. require a `startDate`/`endDate` within the
  game window, or a slug pattern) before they are trusted even as a divergence signal.
- It is "BEST-EFFORT" by its own module docstring (`:1-15`) -- the least reliable of the four
  market sources.

REQUIRED DISCIPLINE: tag `venue_type="prediction_market"`; EXCLUDE from the bettable
`best_line`/`detect_arb`; use only as a SEPARATE P4 divergence signal = devigged-polymarket
prob (devig its own two-way first via `odds_shop.devig_twoway`) minus devigged-sportsbook prob.
Never let a Polymarket decimal populate `best_a_price`/`best_b_price` on the bettable board.
Two prediction-market sources (Kalshi + Polymarket) can also be cross-checked against EACH
OTHER -- agreement raises confidence the divergence is real and not a single-venue artifact.

## 6. The MISSING closing-line capture plan (Polymarket-specific)

1. POLL on the 60s `refresh_daemon` tick up to game start; reuse the aggregated board.
2. LOG per tick tagged `venue_type="prediction_market"`, `source="polymarket"`, with
   `{event_id/slug, home_dec, away_dec, outcomePrices (raw), startDate/endDate, ts}`. Keep raw
   prices for reproducible devig.
3. CLOSE = last row with `ts < game start`; quarantine post-start rows (live). Because
   Polymarket has no clean kickoff field, derive the cutoff from the MATCHED sportsbook
   event's `commence_time` (via the merged OddsEvent), not from the loose `startDate`.
4. METRIC = **divergence CLV only** (did the bettable sportsbook number beat the
   Polymarket-implied fair prob at close?) -- same caveat as Kalshi: NOT a substitute for
   sportsbook-close CLV, which is the only real-money gate.
5. STORAGE: `polymarket_snapshots.jsonl` or a `venue_type`-tagged row in the per-domain
   `odds_snapshots/snapshots.jsonl`. NEVER `prop_line_history.jsonl`.

GAP TODAY: nothing logs Polymarket; snapshots are ESPN-only (data-acquisition A4).

## 7. Honest cut / keep verdict

KEEP as a labelled P4 divergence input, RANKED BELOW Kalshi (looser filter, best-effort
parser, futures-contamination risk). CUT any bettable-book treatment. Before trusting even as a
signal, add (a) `venue_type` tagging, (b) a single-GAME gate to drop futures, (c) devig on its
own two-way before cross-venue comparison. Do NOT loosen the strict two-outcome/two-price
requirement at `:73-74` -- skipping is correct.
