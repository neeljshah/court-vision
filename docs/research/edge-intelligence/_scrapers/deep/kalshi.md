# DATASOURCE: Kalshi -- keyless prediction-market team-winner lines (P4 divergence, NOT bettable book)

_Part of the edge-intelligence corpus (_scrapers/deep/). Per-source deep spec for the Kalshi
public market-data feed. Grounded in `scripts/platformkit/odds_provider/kalshi.py`,
`base.py`, `aggregate.py`, `odds_shop.py`, and project-deep-dive 03 (sec 5 "Other") + the
_scrapers/data-acquisition.md B3 entry. ASCII only._

EDGE-UNLOCK: **P4 (prediction-market vs sportsbook divergence)** -- a DIFFERENT crowd than a
sportsbook. TIER: HYPOTHESIS (divergence-as-signal is unmeasured here). It is NOT a sportsbook;
its YES ask is NOT a bettable book line and MUST stay tagged as venue-type prediction-market.

---

## 1. Endpoint + auth

- Base: `https://api.elections.kalshi.com/trade-api/v2` (`kalshi.py:32`; also reachable as
  `external-api.kalshi.com`).
- Call: `GET /markets?limit=200&status=open` (`kalshi.py:140-141`, `urlencode({"limit":
  page_limit, "status":"open"})`). Single paginated list across ALL categories; the provider
  filters client-side.
- AUTH: KEYLESS for public reads. `_token()` (`kalshi.py:49-52`) reads `KALSHI_API_TOKEN` from
  ENV only, but it is **NEVER attached to any request header** in the keyless path -- it is
  effectively dead code (deep-dive 03 sec 5 "Other"). Only TRADING needs auth; market data
  does not. Do not add the token to reads; it buys nothing and risks a secret-in-transit.
- Caching: `disk_cache_get` via `http_cache.py` (`~/.cache/courtvision_odds`, 60s TTL) when
  `use_cache=True` (default).
- Prices are quoted in DOLLARS in [0,1] in the `*_dollars` fields = the implied probability of
  the YES side (`kalshi.py` module docstring + `_yes_ask_prob`).

## 2. What markets it covers

- TEAM GAME-WINNER only. A Kalshi sports game is an EVENT (`event_ticker`) holding exactly two
  team-winner MARKETS, one per team, each a YES/NO "<team> wins" contract.
- Sport filter by `event_ticker` prefix `_SERIES_HINT` (`kalshi.py:37-42`):
  `nba->KXNBA`, `mlb->KXMLB`, `soccer->KXEPL`, `soccer_intl->KXWC`. Any sport not in this map
  -> `unavailable("kalshi: unsupported sport ...")` (`kalshi.py:138-139`).
- NO player props, NO totals/spreads, NO draw (soccer 3-way is NOT represented -- `draw` is
  hard-coded `None` at `kalshi.py:113`). This is a moneyline-shaped two-way feed only.
- A market that cannot be confidently mapped to a two-team game is SKIPPED, never guessed
  (`parse_events` requires exactly 2 legs each with a usable YES ask, `:99-104`).

## 3. Schema -> OddsEvent mapping (the exact code path)

`/markets` body -> `body["markets"]` (list) -> filter by prefix (`kalshi.py:150-151`) ->
`parse_events(relevant, sport)` (`:87`):

```
group_markets(markets)            # group by event_ticker -> {ev_ticker: [leg, leg, ...]}  (:71)
  for ev_ticker, legs:
    if len(legs) != 2: skip       # one-sided / >2-leg event -> never guessed  (:100)
    p_a = _yes_ask_prob(leg_a)    # yes_ask_dollars -> last_price_dollars -> yes_bid_dollars  (:55-68)
    p_b = _yes_ask_prob(leg_b)    # must each be in (0,1); else skip
    dec_a = prob_to_decimal(p_a)  # base.py:52 -> 1/prob  (out-of-range -> None -> skip)
    dec_b = prob_to_decimal(p_b)
    home  = _team_label(leg_a)    # yes_sub_title or title tail  (:82)
    away  = _team_label(leg_b)
    OddsEvent(event_id=ev_ticker, sport, home, away,
              commence_time=leg_a["close_time"],
              prices={"kalshi": {"home": dec_a, "away": dec_b, "draw": None}},
              source="kalshi", as_of=now_iso())
```

The `OddsEvent.prices` shape `{venue: {"home": dec, "away": dec, "draw": None}}` is EXACTLY
what `odds_shop.summarise_twoway` / `best_line` consume (`base.py:68-84` docstring). The venue
key is the literal string `"kalshi"`.

## 4. How it flows into the odds_shop / odds_lookup seam

- `aggregate.default_providers` (`aggregate.py:145-153`) includes `KalshiProvider` alongside
  ESPN + Polymarket. `aggregate(sport)` (`:156`) calls each `.fetch`, records per-source
  status, and `merge_events` (`:123`) folds Kalshi's `{"kalshi": {...}}` venue dict into the
  per-game OddsEvent (flipping home/away via `teams_match` if orientation differs, `:111-120`).
- `to_odds_lookup(sport)` (`:187`) builds the `odds_lookup(sport, home, away)` closure that
  `slate.build_slate` calls; the returned dict is keyed by venue then by the CALLER's team-name
  strings (`:218-226`), then `odds_shop.summarise_twoway(book_prices, home, away)` runs
  `best_line` + `devig_twoway` + `detect_arb` across every venue including `"kalshi"`.

## 5. THE PREDICTION-MARKET-vs-SPORTSBOOK DISTINCTION (binding -- must be tagged, not mixed)

Kalshi is a PREDICTION MARKET, not a sportsbook. The current code carries the venue label
`"kalshi"` in `prices`, which keeps it nominally distinguishable -- but `best_line` /
`detect_arb` / `summarise_twoway` (`odds_shop.py:48,84,127`) treat EVERY venue as an
interchangeable "book" and the Kalshi YES-ask decimal can be the highest, so it can WIN
`best_line` and surface as the bettable "best" price. THAT IS THE BUG TO PREVENT.

Why mixing it into `best_line` as bettable is wrong (deep-dive 03 sec 5; data-acquisition B3):
- The YES ask carries its OWN vig/skew (favourite-longshot, different from a book's hold).
- Liquidity is LOW and spreads WIDE -- a "best" Kalshi price is often not fillable at size, so
  a `detect_arb` hit against it can be a phantom arb you cannot actually execute.
- Orientation depends ENTIRELY on `_team_label` name-matching; a label the resolver doesn't
  know can flip a side and produce a wrong-side price.

REQUIRED DISCIPLINE (deep-dive 03 plan item 3 = "tag venue type"):
- Carry an explicit `venue_type` on each venue: `prediction_market` for kalshi/polymarket vs
  `sportsbook` for espn/the-odds-api/fanduel. (Today this is implicit in the venue name only.)
- `best_line` / `detect_arb` for the BETTABLE board must consider only `sportsbook` venues.
  Kalshi feeds a SEPARATE, labelled **P4 divergence signal** = (devigged Kalshi prob) minus
  (devigged sportsbook prob), NOT a candidate for `best_a_price`.
- The fair-prob from Kalshi must be devigged on its OWN two-way (YES_a vs YES_b via
  `odds_shop.devig_twoway` / Shin) before any cross-venue comparison -- never compared raw.
- HONEST framing: P4 is a HYPOTHESIS-tier signal. A Kalshi/book gap is a candidate, not an
  edge, until calibration- then CLV-proven on the SPORTSBOOK side you can actually bet.

## 6. The MISSING closing-line capture plan (Kalshi-specific)

Kalshi exposes a real two-way YES/YES with a timestamp (`close_time` -> `commence_time`), so it
CAN feed a closing-line trajectory -- but as a P4 DIVERGENCE close, never as the bettable close.

1. POLL on the same `refresh_daemon` 60s tick up to `close_time` (see
   _scrapers/closing-line-and-clv.md sec 1). Reuse the board already aggregated; no new fetch.
2. LOG per tick a row tagged `venue_type="prediction_market"`, `source="kalshi"`, with
   `{event_ticker, home_yes_dec, away_yes_dec, yes_ask_dollars (raw), close_time, ts}`. Keep
   raw `*_dollars` so the devig is reproducible.
3. CLOSE = last row with `ts < close_time` (the event's Kalshi close). Quarantine any row at or
   after `close_time` (it is post-event / settling).
4. The CLV metric here is **divergence CLV, not bettable CLV**: did the SPORTSBOOK number we
   actually took beat the Kalshi-implied fair prob at close? That measures whether the
   prediction-market crowd was sharper than the book on this event. It does NOT substitute for
   `clv_ledger.compute_clv` against the bettable sportsbook close -- that remains the only tier
   that gates real money (proof-standards.md).
5. STORAGE: a separate `kalshi_snapshots.jsonl` (or a `venue_type` column in the existing
   per-domain `odds_snapshots/snapshots.jsonl`), NEVER folded into `prop_line_history.jsonl`
   (which is for priced sportsbook props).

GAP TODAY: nothing logs Kalshi at all (the snapshots logs are ESPN-only single-venue;
data-acquisition A4). First step = include the `"kalshi"` venue dict in the per-tick snapshot
with its `venue_type` tag.

## 7. Honest cut / keep verdict

KEEP as a labelled P4 divergence input only. CUT any treatment of Kalshi as a bettable book in
`best_line`/`detect_arb`. Do NOT attach `KALSHI_API_TOKEN` to reads. Do NOT loosen the
2-leg/both-YES-ask requirement -- the strictness (skip rather than guess) is the right risk
posture, identical to the team-matcher bias toward false negatives.
