# MLB Answer Rules -- per claim category

Read `docs/analytics/ANSWER_RULES.md` and `docs/AI_CONSUMER_CONTRACT.md`
first. This file pins, per claim category, the single source-of-truth
artifact, exact computation, allowed phrasing, and forbidden claims for MLB
questions routed through `resolver_registry.resolve(query, "mlb")`.

## 1. Player stat (category `player_stat`)

- **Source of truth:** `data/cache/profiles/mlb_player_profiles.parquet`,
  `raw_value` column, resolved by `scripts/platformkit/profiles/ask.py`.
- **Computation:** fuzzy entity+attribute match -> latest (or requested)
  `window` row -> `raw_value` as stored (e.g. `platoon_resilience`'s on-base
  delta, `clutch_baseout`'s GB-rate delta). No re-derivation.
- **Allowed phrasing:** "X's `<attribute>` is `<raw_value>` (n=`<n>`,
  `<status>`, window `<window>`)."
- **Forbidden:** a bare number with no `n`/`status`/`window`; quoting a
  low-n pitcher stat (see min-n rule below) with the same confidence as a
  well-sampled one.
- **Min-n / independent-proxy overlap (adjudication b -- the 206-pitch
  reliever landmine):** a reliever with a thin single-season pitch count
  (e.g. ~206 pitches) can rank #1 on a raw rate stat near its own sample
  floor purely from noise. A `player_stat` single-entity lookup always
  surfaces `n` so this is visible; a RANKING question (best/top-N) must go
  through `concept_rating`, whose `min_n` floor excludes the entity outright,
  and must independently check that the top-5 overlaps a top-5 computed from
  a different, larger-sample proxy metric before being trusted.

## 2. Rating / attribute (category `rating_attribute`)

- **Source of truth:** same profiles parquet, `percentile` + `rating_2k`.
- **Computation:** `rating_2k = 25 + percentile * 0.74` from the qualified
  population for that attribute+window.
- **Allowed phrasing:** "X's `<attribute>` rates `<rating_2k>` (percentile
  `<percentile>`, presentation-only)."
- **Forbidden:** feeding `rating_2k` into a gate/fit/claim, or presenting a
  DESCRIPTIVE attribute (most of the 14 in `attribute_registry.py` -- only
  `platoon_resilience`, `clutch_baseout`, `mix_by_leverage`,`framing` carry a
  validated status; the rest, incl. `TTO_durability`, are DESCRIPTIVE **by
  design** after `above_avg_velo:tto3` FAILED_REPLICATION twice) as if it
  predicted an outcome.

## 3. Concept rating (category `concept_rating`)

- **Source of truth:** `domains/mlb/concepts/concept_registry.py`
  (`derive_weights`) over the profiles parquet, via
  `scripts/platformkit/answers/contracts.py`.
- **Computation:** status-rank x n-shrinkage weighted composite; `min_n`
  floor applied before ranking -- this is where the reliever/low-n landmine
  is actually closed (a below-floor entity never appears in `top`).
- **Allowed phrasing:** always include `ingredients`/`decomposition`.
- **Forbidden:** a bare composite score with no decomposition; treating a
  concept score as a forecast.

## 4. Prediction / win probability (category `prediction_winprob`)

- **Source of truth:** `domains/mlb/predictor.py`, invoked ONLY via
  `scripts/platformkit/predict_matchup.py` (the `predict-matchup` skill).
  `resolver_registry.py` never imports a forecast engine directly.
- **Computation:** pregame calibrated probability; in-game adds inning/
  base-out state through the validated repricer.
- **Allowed phrasing:** "calibrated win probability" / "matches the devigged
  close" -- never "our edge" or a dollar figure.
- **Forbidden:** ANY $-edge/ROI claim (see category 6).

## 5. Calibration number (category `calibration_number`)

- **Source of truth:** the pinned artifact
  `vault/_Organized/_Index/_Calibration_Scoreboard.md`, parsed (not
  recomputed) by `resolver_registry.calibration_number`.
- **Computation:** MLB row = SP-form 2-feature logistic vs. solo-Elo Platt
  baseline; `as_of` = that file's mtime.
- **Allowed phrasing:** "MLB calibration improved from Brier `<a>` to `<b>`
  (n=`<n>`) -- a calibration metric, not a market edge."
- **Forbidden:** presenting a Brier/ECE delta as profit or win-rate-over-market.

## 6. Historical result (category `historical_result`)

- **Source of truth:** `data/domains/mlb/games.parquet` (`home_runs`/
  `away_runs` columns directly -- no summing needed, unlike NBA's quarter
  columns).
- **Computation:** direct row read for the matched game (by team codes +
  date); zero rows matched -> refuse.
- **Allowed phrasing:** "`<away>` `<away_score>` @ `<home>` `<home_score>`,
  `<date>`."
- **Forbidden:** inferring a score from a different game/date/season when
  the exact match is absent -- MLB's odds corpus (2010-2021) and pitch-level
  Statcast corpus (2022-2026) are disjoint; never blend a result across that
  boundary as if it were one continuous corpus.

## 7. Edge language (category `edge_language`)

- **Never answered.** Same rule as every sport: any edge/ROI/beat-the-market
  phrasing or any of the six retracted numbers is REFUSED before reaching a
  resolver. `.claude/rules/no-edge-claims.md` is the binding list. Closed
  classes `ingame_sp_velo_fatigue` and `mlb_pregame_stack_L3` in particular
  must never be re-surfaced as a live edge.

## Window conventions (adjudication c)

Same rule as NBA: `ask._pick_row` sorts by the `window` string and takes the
last row -- `career_to_X` vs. a bare year is resolved by that sort, not by
parsing the label. If MLB ever adds a window label that breaks lexical
recency ordering, fix the sort key in `ask.py`, not the caller.

## Zero-row / entity-id honesty (adjudications d, e)

- Zero rows for a plausible entity+attribute (e.g. a rarely-used metric for
  a two-way player) is `no_data`, never zero-filled.
- MLB profiles use one entity-id space (batters and pitchers are the same
  `player_resolver_mlb.py` id space) -- unlike soccer's two disjoint corpora,
  there is no cross-join risk here, but a name shared by a batter and a
  pitcher (rare, but real in MLB history) must still resolve to exactly one
  `entity_id` per query or come back `ambiguous`, never silently pick one.
