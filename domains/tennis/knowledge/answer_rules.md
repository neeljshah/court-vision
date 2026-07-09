# Tennis Answer Rules -- per claim category

Read `docs/analytics/ANSWER_RULES.md` and `docs/AI_CONSUMER_CONTRACT.md`
first. This file pins, per claim category, the single source-of-truth
artifact, exact computation, allowed phrasing, and forbidden claims for
tennis questions routed through `resolver_registry.resolve(query, "tennis")`.

## 1. Player stat (category `player_stat`)

- **Source of truth:** `data/cache/profiles/tennis_player_profiles.parquet`
  (PLAYER-level only -- tennis has no team/lineup profiles, unlike NBA/MLB's
  player+team+lineup trio), `raw_value` column, resolved by
  `scripts/platformkit/profiles/ask.py`.
- **Computation:** fuzzy entity+attribute match -> latest (or requested)
  `window` row -> `raw_value` as stored. No re-derivation.
- **Allowed phrasing:** "X's `<attribute>` is `<raw_value>` (n=`<n>`,
  `<status>`, window `<window>`)."
- **Forbidden:** a bare number with no `n`/`status`/`window`.
- **Multi-source `sources` (adjudication a):** a tennis attribute can be
  built off more than one on-disk corpus at once -- e.g.
  `serve_dominance`'s `source_artifact` reads
  `"data/cache/sackmann_pbp/charting_points.parquet;
  data/domains/tennis/match_stats.parquet;data/domains/tennis/matches.parquet;
  data/domains/tennis/wta_matches.parquet"` (semicolon-joined, verified
  live, not soccer/MLB's JSON-list shape) -- a consumer citing this field
  must split on `;`, never treat it as one bare path.

## 2. Rating / attribute (category `rating_attribute`)

- **Source of truth:** same player profiles parquet, `percentile` +
  `rating_2k` columns.
- **Computation:** `rating_2k = 25 + percentile * 0.74` (25-99 band), from
  the qualified population for that attribute+window.
- **Allowed phrasing:** "X's `<attribute>` rates `<rating_2k>` (percentile
  `<percentile>`, presentation-only)."
- **Forbidden:** treating `rating_2k` as causal or predictive of anything.

## 3. Concept rating (category `concept_rating` -- superlative/comparison/explanation/fit)

- **Source of truth:** `domains/tennis/concepts/concept_registry.py`
  (`CONCEPTS`: `pressure_resilience`, `return_game`, `serve_weapon`,
  `stamina`) over the player profiles parquet, via
  `scripts/platformkit/answers/contracts.py`.
- **Computation:** status-rank x n-shrinkage weighted composite; `min_n`
  floor applied before ranking; a comparison additionally carries
  `what_would_flip_it` (smallest single-signal percentile move, other
  signals fixed, that flips the ranking -- verified live on Federer-vs-
  Nadal `serve_weapon`).
- **Allowed phrasing:** always include `ingredients`/`decomposition`.
- **Forbidden:** a bare composite with no decomposition; treating a concept
  score as a forecast.

## 4. Prediction / win probability (category `prediction_winprob`)

- **Source of truth:** `domains/tennis/predictor.py`, invoked ONLY via
  `scripts/platformkit/predict_matchup.py` (the `predict-matchup` skill).
  `resolver_registry.py` never imports a forecast engine directly.
- **Computation:** pregame calibrated probability; in-game adds the realized
  point/game/set state through the validated repricer.
- **Allowed phrasing:** "calibrated win probability" / "matches the devigged
  close" -- never "our edge" or a dollar figure.
- **Forbidden:** ANY $-edge/ROI claim (see category 7).

## 5. Calibration number (category `calibration_number`)

- **Source of truth:** the pinned artifact
  `vault/_Organized/_Index/_Calibration_Scoreboard.md` (parsed by
  `resolver_registry.calibration_number`, never recomputed live in this path).
- **Computation:** walk-forward Platt recalibration (blend=0.3), from the
  last calibration-report run; `as_of` = that file's mtime.
- **Allowed phrasing:** "tennis calibration improved from Brier `<a>` to
  `<b>` (n=`<n>`) -- a calibration metric, not a market edge."
- **Forbidden:** presenting a Brier/ECE delta as profit or win-rate-over-market.

## 6. Historical result (category `historical_result`)

- **Status: NOT WIRED for tennis.** `resolver_registry._HIST_PATHS` only
  registers `nba`/`mlb` -- a "final score"/"result of" tennis query returns
  `not_supported` with `"historical_result not wired for sport 'tennis'"`
  (verified live against the running registry). Never hand-roll a direct
  read of `matches.parquet`/`wta_matches.parquet` to answer this outside
  the registry.
- **Score-string WINNER-FIRST landmine (why this needs care if ever
  wired):** the `score` column in the match corpus is written from the
  MATCH WINNER's perspective in every set token, NOT a fixed "player 1"
  perspective -- verified empirically in the ledger (mechanisms.md item 14):
  the front-listed side wins the aggregate set count in 98.9% of matches,
  vs only 51.2% under a naive "player 1 always listed first" read. Any
  future historical-result wiring for tennis must resolve winner identity
  from the `winner`/`w_name` column, never by parsing set-token order.
- **`matches_2026` is results-only:** the in-season `matches_2026`-style
  ingest carries completed results, not a fixture/schedule feed -- a
  "final score" query for an in-progress or future match will legitimately
  come back with no row, and that is `no_data`, not a bug.

## 7. Mechanism effect (category `mechanism_effect`)

- **Source of truth:** `domains/tennis/knowledge/validation_ledger.jsonl`
  (23 distinct hypotheses, zero `UNTESTED` remaining as of this session's
  mechanism re-validation pass), resolved by
  `resolver_registry.mechanism_effect("tennis", <mechanism>)`.
- **Computation:** verbatim lookup of the matched hypothesis row(s) --
  verdict/effect/n/p/corpus/note, exactly as written by the mechanism
  validator; never recomputed, never improvised for an unregistered
  mechanism. Some hypotheses (e.g. `lefty_advantage_on_return`) have
  MULTIPLE ledger rows (re-appended across validation runs) -- `findings`
  returns all of them together verbatim; quote the first, never assume
  there is exactly one.
- **ATP-only ceiling (adjudication b):** `height_x_surface_interaction` is
  ATP-only because `players.parquet` height is ATP-only -- WTA rows are
  naturally excluded by the same NaN-height-join pattern used by
  `lefty_advantage_on_return`. Never present an ATP-only finding as if it
  covered WTA too.
- **Allowed phrasing:** "the local evidence for `<hypothesis>` is
  `<verdict>` (effect `<effect_local>`, n=`<n>`, p=`<p>`) -- a LOCAL
  single-corpus finding, not a market-beating or causal claim."
- **Anti-folklore receipts (quote verbatim from the ledger, never
  re-derive):**
  - `lefty_advantage_on_return` -- CONFIRMED, but REVERSED vs the popular
    "lefty advantage" folklore: right-handers win MORE often against
    lefties in a rank-controlled sample (effect +0.035, right-handed
    win-rate 0.5350, p=5.85e-06, n=4,189, `atp_wta_matches_2015_2025`).
  - `upset_rate_by_round` -- CONFIRMED that upset rate varies by round, but
    REVERSED vs the seeded claim: upset rate RISES into later rounds (SF
    highest at 0.388, RR lowest at 0.312), not falls (chi2 p=2.0e-9,
    n=40,794, `matches_atp_wta_2015_2025`).
- **Forbidden:** presenting a `NOT_TESTABLE` row (e.g.
  `tiebreak_skill_persistence_split_half`, `rally_length_distribution_by_round`)
  as a tested null -- these are honest data-gap admissions (no cross-match
  player id, or no `round` column, on the point-level corpus), not failed
  tests.

## 8. Edge language (category `edge_language`)

- **Never answered.** Any question containing edge/ROI/beat-the-market
  language, or any of the six retracted numbers, is REFUSED by
  `resolver_registry.resolve()` before it reaches any resolver. See
  `.claude/rules/no-edge-claims.md` for the full binding list.

## Window conventions (adjudication c)

Same rule as NBA/MLB: `ask._pick_row` sorts by the `window` string and
takes the last row.

## Zero-row / entity-id honesty (adjudications d, e)

- Zero rows for a plausible entity+attribute is `no_data`, never zero-filled.
- Tennis has one entity-id space in `players.parquet` (unlike soccer's two
  disjoint corpora) -- but `slam_points.parquet` (the point-level corpus)
  carries NO player-name/id column at all, only within-match server-slot
  (1/2) identity (mechanisms.md item 15, `tiebreak_skill_persistence_
  split_half`'s blocker). Any cross-match per-player question routed at
  point-level granularity must come back `not_supported`/`NOT_TESTABLE`,
  never silently fall back to match-level identity as if it were the same
  join key.
- **Sackmann repos 404 (operational landmine):** the upstream Sackmann
  GitHub repos this corpus was originally sourced from now 404 on fresh
  fetch attempts -- `matches.parquet`/`wta_matches.parquet`/
  `slam_points.parquet` are LOCAL CACHED snapshots only; do not assume a
  live re-fetch will succeed, and do not treat a 404 there as evidence the
  local cache is stale or wrong.
