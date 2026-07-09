# Soccer Answer Rules -- per claim category

Read `docs/analytics/ANSWER_RULES.md` and `docs/AI_CONSUMER_CONTRACT.md`
first. This file pins, per claim category, the single source-of-truth
artifact, exact computation, allowed phrasing, and forbidden claims for
soccer questions routed through `resolver_registry.resolve(query, "soccer")`.

## 1. Player stat (category `player_stat`)

- **Source of truth:** `data/cache/profiles/soccer_team_profiles.parquet`
  (TEAM-level only -- soccer has no player-level profiles parquet, unlike
  NBA/MLB's player+team+lineup trio), `raw_value` column, resolved by
  `scripts/platformkit/profiles/ask.py`.
- **Computation:** fuzzy entity+attribute match -> latest (or requested)
  `window` row -> `raw_value` as stored. No re-derivation.
- **Allowed phrasing:** "X's `<attribute>` is `<raw_value>` (n=`<n>`,
  `<status>`, window `<window>`)."
- **Forbidden:** a bare number with no `n`/`status`/`window`; asking for a
  player-level stat this category cannot answer (no player profiles exist)
  -- that must come back `no_data`/`ambiguous`, never a team number
  substituted silently for a player question.
- **`sources` column shape (adjudication a):** soccer's `sources` field is a
  JSON-stringified list, e.g. `'["data/cache/statsbomb/events",
  "data/cache/statsbomb/matches"]'` -- the same convention MLB uses (unlike
  NBA's bare path string). A consumer must `json.loads` it before treating it
  as a single path (see MLB's `_source_paths` helper in
  `test_answer_consistency_mlb.py` for the reference pattern).

## 2. Rating / attribute (category `rating_attribute`)

- **Source of truth:** same team profiles parquet, `percentile` +
  `rating_2k` columns.
- **Computation:** `rating_2k = 25 + percentile * 0.74` (25-99 band), from
  the qualified population for that attribute+window.
- **Allowed phrasing:** "X's `<attribute>` rates `<rating_2k>` (percentile
  `<percentile>`, presentation-only)."
- **Forbidden:** treating `rating_2k` as causal or predictive of anything.

## 3. Concept rating (category `concept_rating` -- superlative/comparison/explanation/fit)

- **Source of truth:** `domains/soccer/concepts/concept_registry.py`
  (`CONCEPTS`: `solidity`, `threat`, `transition`) over the team profiles
  parquet, via `scripts/platformkit/answers/contracts.py`.
- **Computation:** status-rank x n-shrinkage weighted composite; `min_n`
  floor applied before ranking.
- **Allowed phrasing:** always include `ingredients`/`decomposition`.
- **Forbidden:** a bare composite with no decomposition; treating a concept
  score as a forecast.
- **Thin-population floor (adjudication b):** all three soccer concepts are
  built over a single 400-match two-corpus slice (EPL 2015/16 + FA WSL) --
  a superlative query can legitimately come back `ok` with an EMPTY `top`
  and the note `"no entities met the min-n floor"` (verified live: `best
  threat`/`best solidity`/`best transition` each returned zero qualifying
  entities against this corpus's current floor). An empty `top` with `ok`
  status is an honest "nobody clears the bar" answer, not a bug to route
  around -- never lower the floor ad hoc to force a result.

## 4. Prediction / win probability (category `prediction_winprob`)

- **Source of truth:** `domains/soccer/predictor.py`, invoked ONLY via
  `scripts/platformkit/predict_matchup.py` (the `predict-matchup` skill).
  `resolver_registry.py` never imports a forecast engine directly.
- **Computation:** pregame calibrated probability; in-game adds the realized
  score state through the validated repricer (see the leak rule in
  mechanisms.md item 3 -- state must be rebuilt `as-of` the target date,
  never a static snapshot replayed across a corpus).
- **Allowed phrasing:** "calibrated win probability" / "matches the devigged
  close" -- never "our edge" or a dollar figure.
- **Forbidden:** ANY $-edge/ROI claim (see category 7).

## 5. Calibration number (category `calibration_number`)

- **Source of truth:** the pinned artifact
  `vault/_Organized/_Index/_Calibration_Scoreboard.md` (parsed by
  `resolver_registry.calibration_number`, never recomputed live in this path).
- **Computation:** DC-rho x draw-prob calibration (scoreline-level, capped),
  from the last calibration-report run; `as_of` = that file's mtime.
- **Allowed phrasing:** "soccer calibration improved from Brier `<a>` to
  `<b>` (n=`<n>`) -- a calibration metric, not a market edge."
- **Forbidden:** presenting a Brier/ECE delta as profit or win-rate-over-market.

## 6. Historical result (category `historical_result`)

- **Status: NOT WIRED for soccer.** `resolver_registry._HIST_PATHS` only
  registers `nba`/`mlb` -- calling `resolver_registry.historical_result`
  (or routing a "final score of X vs Y" query) for soccer returns
  `not_supported` with `"historical_result not wired for sport 'soccer'"`
  (verified live against the running registry, not assumed from reading
  the source). A soccer historical-result question must be answered as
  `not_supported`, never guessed from `match_meta.parquet` by hand.
- **Forbidden:** improvising a direct pandas read of
  `data/cache/statsbomb/match_meta.parquet` to answer this category outside
  the registry -- if this category is wired later, it belongs in
  `resolver_registry._HIST_PATHS`, not a one-off client-side read.

## 7. Mechanism effect (category `mechanism_effect`)

- **Source of truth:** `domains/soccer/knowledge/validation_ledger.jsonl`
  (24 distinct hypotheses, zero `UNTESTED` remaining as of this session's
  mechanism re-validation pass), resolved by
  `resolver_registry.mechanism_effect("soccer", <mechanism>)`.
- **Computation:** verbatim lookup of the matched hypothesis row(s) --
  verdict/effect/n/p/corpus/note, exactly as written by the mechanism
  validator; never recomputed, never improvised for an unregistered
  mechanism.
- **Allowed phrasing:** "the local evidence for `<hypothesis>` is
  `<verdict>` (effect `<effect_local>`, n=`<n>`, p=`<p>`) -- a LOCAL
  single-corpus finding, not a market-beating or causal claim."
- **Anti-folklore receipts (quote verbatim from the ledger, never
  re-derive):**
  - `leading_team_shot_rate_suppression` -- CONFIRMED, but INVERTED vs the
    "defensive shell" folklore: a leading team takes MORE shots/min than
    while tied, not fewer (effect +0.02423, p=2.15e-37, n=3,352 team-match
    units, `statsbomb_events_full__3443_matches`).
  - `pressing_ppda_vs_turnover_rate` -- CONFIRMED, PPDA-proxy vs opponent
    turnover rate (pearson r=-0.558, p~0, n=6,886 team-match units,
    `statsbomb_events_full_cache`) -- the strongest single-effect
    CONFIRMED_LOCAL row in the soccer ledger.
- **Forbidden:** presenting a `NOT_TESTABLE` row (e.g. `weather_pitch_
  condition_effect`, `home_advantage_crowd_component`) as if it were a
  tested null -- `NOT_TESTABLE` means the ingredient does not exist locally,
  not that the mechanism was checked and failed.

## 8. Edge language (category `edge_language`)

- **Never answered.** Any question containing edge/ROI/beat-the-market
  language, or any of the six retracted numbers, is REFUSED by
  `resolver_registry.resolve()` before it reaches any resolver (verified
  live: `"what edge do we have on pressing, 18.38 percent"` -> `refused`).
  See `.claude/rules/no-edge-claims.md` for the full binding list.

## Window conventions (adjudication c)

Same rule as NBA/MLB: `ask._pick_row` sorts by the `window` string and
takes the last row.

## Zero-row / entity-id honesty (adjudications d, e -- the two-disjoint-id landmine)

- Zero rows for a plausible entity+attribute is `no_data`, never zero-filled.
- **Soccer has TWO disjoint entity-id spaces in the corpus (verified live,
  not hypothetical):** a bare-name lookup of `"Arsenal"` against the team
  profiles parquet resolves `ambiguous` against
  `['Arsenal WFC (soccer)', 'Arsenal (soccer)', 'Arsenal (soccer)']` --
  the men's Premier League club, the FA WSL women's club, and a duplicate
  men's row from a second source ingest are three distinct `entity_id`s.
  A query must disambiguate (e.g. `"Arsenal WFC"` or add a competition/
  window qualifier) rather than accept the first match.
- **`div` vs `match_meta_full` competition landmine:** StatsBomb's cached
  match metadata carries competition identity two different ways depending
  on which file is read -- do not assume the abbreviated `div`-style code
  used in one artifact lines up 1:1 with the full competition name in
  `match_meta_full`/`match_meta.parquet`; join on the sport's declared
  competition-id column, never on a raw string match across the two shapes.
- **Home/away side-mismatch landmine:** the CLOSED leak rule (mechanisms.md
  item 3) exists precisely because a static snapshot silently reused stale
  home/away state across dates it had already absorbed -- any repricer or
  historical join must rebuild state `as-of` the target date, and must
  re-verify which side is home/away for THAT date's row rather than
  assuming a fixed team-to-side mapping across a season.
- **Odds-parquet decimal landmine:** soccer's `odds.parquet` stores prices
  as decimal odds, not American/moneyline -- any consumer converting to an
  implied probability must use `1/decimal_odds`, never the American-odds
  formula (see `reference_soccer_odds_parquet_decimal_landmine_2026_07_05`
  memory note); a silent format-mismatch here misprices every question that
  touches an odds-derived number.
