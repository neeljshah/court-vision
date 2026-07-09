# NBA Answer Rules -- per claim category

Read `docs/analytics/ANSWER_RULES.md` and `docs/AI_CONSUMER_CONTRACT.md`
first. This file pins, per claim category, the single source-of-truth
artifact, exact computation, allowed phrasing, and forbidden claims for NBA
questions routed through `resolver_registry.resolve(query, "nba")`.

## 1. Player stat (category `player_stat`)

- **Source of truth:** `data/cache/profiles/nba_{player,team,lineup}_profiles.parquet`,
  `raw_value` column, resolved by `scripts/platformkit/profiles/ask.py`.
- **Computation:** fuzzy entity+attribute match -> latest (or requested)
  `window` row -> `raw_value` as stored. No re-derivation.
- **Allowed phrasing:** "X's `<attribute>` is `<raw_value>` (n=`<n>`,
  `<status>`, window `<window>`)."
- **Forbidden:** stating a bare number with no `n`/`status`/`window`;
  presenting `rating_2k` as if it were the raw stat (rule 2 below owns that).
- **Percentile pre-orientation (adjudication a):** the profiles parquet's
  `percentile` column is already orientation-normalized (higher percentile =
  better, even for "lower raw is better" attributes like `zone_def_rim_efg_allowed_on`).
  Never re-invert it; `contracts._entity_composite` does the one correct
  orientation flip via `direction`, and `ask.py`/`resolver_registry.py` never
  touch it a second time. Re-inverting an already-oriented percentile ranks
  the WORST performers top -- this is a caught regression
  (`test_directional_lower_raw_higher_oriented_pct_wins` in
  `test_answer_quality_nba.py`), not a hypothetical.

## 2. Rating / attribute (category `rating_attribute`)

- **Source of truth:** same profiles parquet, `percentile` + `rating_2k`
  columns.
- **Computation:** `rating_2k = 25 + percentile * 0.74` (25-99 band), from the
  qualified population for that attribute+window.
- **Allowed phrasing:** "X's `<attribute>` rates `<rating_2k>` (percentile
  `<percentile>`, presentation-only)."
- **Forbidden:** treating `rating_2k` as causal or predictive of anything --
  it is a rank-in-population display number, never fed into a gate/fit/claim
  (`docs/analytics/README.md`'s own rule, restated here for the answer path).
- **Min-n floor (adjudication b):** an entity below the concept/attribute's
  declared `min_n` floor is EXCLUDED from a ranking, not shown with a
  caveat. This is the 206-pitch reliever landmine: a thin-sample reliever can
  dominate a raw ranking near its own floor while an independent-proxy top-5
  overlap check shows it does not belong. `resolver_registry.py` does not
  re-implement this filter for `player_stat`/`rating_attribute` (a single-row
  fact lookup has no ranking to filter) -- it applies to `concept_rating`
  superlatives only (see below); a single-entity stat/rating answer must
  still surface `n` so the reader can judge sample size themselves.

## 3. Concept rating (category `concept_rating` -- superlative/comparison/explanation/fit)

- **Source of truth:** `domains/basketball_nba/concepts/concept_registry.py`
  (`derive_weights`) over the profiles parquet, via
  `scripts/platformkit/answers/contracts.py`.
- **Computation:** status-rank x n-shrinkage weighted composite across a
  concept's declared signals; min-n floor applied per concept
  (`_apply_min_n`) BEFORE ranking -- this is where the reliever/low-n landmine
  is actually closed for NBA (an entity below floor never appears in `top`).
- **Allowed phrasing:** always include `ingredients`/`decomposition` --
  "X ranks best at `<concept>` (composite `<c>`, confidence `<tier>`),
  driven by `<top ingredient>`."
- **Forbidden:** a bare composite score with no decomposition; treating a
  concept score as a forecast (`docs/analytics/ANSWER_RULES.md`'s core rule).

## 4. Prediction / win probability (category `prediction_winprob`)

- **Source of truth:** `domains/basketball_nba/predictor.py`, invoked ONLY via
  `scripts/platformkit/predict_matchup.py` (the `predict-matchup` skill).
  `resolver_registry.py` deliberately does not import a forecast engine --
  matches the existing guard test in `contracts.py`.
- **Computation:** pregame calibrated probability; in-game adds the realized
  score state through the validated repricer.
- **Allowed phrasing:** "calibrated win probability" / "matches the devigged
  close" -- never "our edge" or a dollar figure.
- **Forbidden:** ANY $-edge/ROI claim (see category 6).

## 5. Calibration number (category `calibration_number`)

- **Source of truth:** the pinned artifact
  `vault/_Organized/_Index/_Calibration_Scoreboard.md` (parsed by
  `resolver_registry.calibration_number`, never recomputed live in this path
  -- recomputation is `calibration-report`'s job).
- **Computation:** per-sport Brier/ECE, baseline vs. improved, from the last
  calibration-report run; `as_of` = that file's mtime.
- **Allowed phrasing:** "NBA calibration improved from Brier `<a>` to `<b>`
  (n=`<n>`) -- a calibration metric, not a market edge."
- **Forbidden:** presenting a Brier/ECE delta as profit or win-rate-over-market.

## 6. Historical result (category `historical_result`)

- **Source of truth:** `data/domains/basketball_nba/linescores.parquet`
  (`home_q1..q4`/`away_q1..q4` summed for final score).
- **Computation:** direct row read for the matched game; zero rows matched ->
  refuse (do not guess a score).
- **Allowed phrasing:** "`<away>` `<away_score>` @ `<home>` `<home_score>`,
  `<date>`."
- **Forbidden:** inferring a score from a different game/date when the exact
  match is absent.

## 7. Edge language (category `edge_language`)

- **Never answered.** Any question containing edge/ROI/beat-the-market
  language, or any of the six retracted numbers (`+18.38%`, `0.119`, `+54%`,
  `78.11`, `8.94`, `54.57`), is REFUSED by `resolver_registry.resolve()`
  before it reaches any resolver. See `.claude/rules/no-edge-claims.md` for
  the full binding list.

## Window conventions (adjudication c)

`window` values are strings like `season_2024_25` or `career_to_2024_25`.
Lexical sort puts `career_to_X` AFTER any bare year that starts with the same
digits only by coincidence of the corpus's current label set -- the correct
"latest" rule is `ask._pick_row`'s own: sort by `window` and take the last
row for that entity+attribute, never assume a specific string format encodes
recency by itself. If a new window label is added that would break lexical
ordering (e.g. `y2` sorting after `y10`), fix `_pick_row`'s sort key, not the
caller.

## Zero-row / entity-id honesty (adjudications d, e)

- Zero rows for an otherwise-plausible entity+attribute is a refusal
  (`no_data`), never a zero-filled or interpolated answer.
- NBA has one entity-id space in the profiles parquet (unlike soccer's two
  disjoint ids) -- but note the known duplicate-entity landmine: some players
  appear twice under diacritic-variant spellings (e.g. "Luka Doncic" vs the
  accented form) as distinct `entity_id`s from different source ingests. A
  bare-name lookup that hits both is correctly `ambiguous`, not silently
  picked -- narrow the query (e.g. add a team or window) rather than treating
  either row as canonical.
