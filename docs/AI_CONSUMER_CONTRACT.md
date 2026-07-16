# AI Consumer Contract -- binding, for ANY LLM client

Any AI (Claude or other) answering a sports question about this repo's data
is an INTERFACE, not the source of truth. The answer engine
(`scripts/platformkit/answers/resolver_registry.py`) is the oracle. This
contract is what makes two different models give the same answer to the same
question -- follow it exactly; do not improvise a "better" phrasing that
drops a field.

## The rules

1. **Route every sports question through the resolver, never model memory.**
   Call `resolver_registry.resolve(query, sport, **kwargs)` (or the CLI:
   `python -m scripts.platformkit.answers.contract_client "<query>" --sport <sport>`).
   Do not answer a stat, rating, prediction, calibration, or historical-result
   question from training data.
2. **Quote the resolver's numbers verbatim.** Do not re-round, re-derive, or
   "clean up" a number the resolver returned. If the resolver returns
   `raw_value=0.0453`, say `0.0453`, not "about 4.5%" unless the resolver
   itself expresses it as a percent.
3. **Cite artifact + as-of on every number.** Every answer must name the
   `source_artifact` and `as_of` fields from the envelope. An answer with a
   number and no citation is non-compliant.
4. **Apply refusal rules verbatim.** `status: "not_supported"` -> say
   NOT_SUPPORTED and stop (an unregistered question type is never
   improvised). `status: "no_data"` -> say NO_DATA and name the zero-row
   reason if given (refuse rather than answer, per the WNBA rim-case rule).
   `status: "refused"` -> the question used edge/ROI/retracted-number
   language; refuse and point at `.claude/rules/no-edge-claims.md`. Never
   soften a refusal into a hedge like "it's hard to say" that still implies a
   number exists.
5. **Never mix engine numbers with model-memory numbers in one answer.** If a
   question needs a fact the resolver does not cover (e.g. play-by-play
   trivia with no registered resolver), say NOT_SUPPORTED for that part
   rather than filling the gap from memory next to a real resolver number --
   the reader cannot tell which parts are verified.
6. **Never claim a dollar edge / ROI / beating the market.** This engine
   produces calibrated numbers and verified analytics, not a profit claim.
   See `.claude/rules/no-edge-claims.md` for the exact retracted-number list
   that must never resurface as current.

## What "the resolver" means concretely

`resolver_registry.RESOLVERS` is the registry: one resolver per question
category (`player_stat`, `rating_attribute`, `concept_rating`,
`prediction_winprob`, `calibration_number`, `historical_result`,
`mechanism_effect`, `edge_language`, `ranking`, plus the descriptive-intel
categories `injury_report`, `news_context`, `schedule_context`,
`scouting_report`, `comparables`, and `matchup_preview`), each with its declared source artifact,
computation rule, and units. `resolver_registry.classify(query)` picks the category;
`resolver_registry.resolve(query, sport)` returns the envelope described
above. Per-sport claim-category rules (what may/may not be said about a
player stat vs. a rating vs. a prediction) are in
`domains/<sport>/knowledge/answer_rules.md`.

## Mechanism / anti-folklore queries (`mechanism_effect`)

"Does mechanism X hold up locally?" / "what does the evidence say about
<mechanism>?" / a folklore claim in free text -- routes to the
`mechanism_effect` category, which reads the matching
`domains/<sport>/knowledge/validation_ledger.jsonl` row(s) verbatim (never
recomputed): `verdict` (`CONFIRMED_LOCAL`/`NULL_LOCAL`/`NOT_TESTABLE`),
`effect_local`, `n`, `p`, `corpus`, and `note`, quoted exactly as the
validator wrote them, plus `source_artifact` and `as_of`.

- A folklore claim that the ledger REJECTED or REVERSED (e.g. NBA
  `clutch_usage_compression` is CONFIRMED but in the AMPLIFYING direction,
  not the "compression" originally claimed; tennis `lefty_advantage_on_return`
  and similar rows) must be answered by citing that exact row -- `NULL_LOCAL`
  or a reversed-direction `CONFIRMED_LOCAL` is the honest answer, never
  softened toward the folklore version.
- Every `effect_local`/`n`/`p` returned by this category is a LOCAL,
  single-corpus finding. State it as such -- never as a market-beating,
  causal, or dollar-edge claim (the envelope's `framing` field says this;
  repeat it, don't drop it).
- Multiple ledger rows validate the SAME mechanism across corpora/re-runs --
  all are returned together under one `hypothesis` key.
- Multiple DIFFERENT mechanisms match a fuzzy query -> `status: "ambiguous"`
  with a `candidates` list; narrow the query, don't guess which one was meant.
- An unregistered/unknown mechanism -> `status: "not_supported"`; say
  NOT_SUPPORTED per rule 4, never improvise a mechanism that isn't in the
  ledger.

## Intel categories: injuries, news, schedule, scouting, comparables, matchup, win-prob

Six additional categories return DESCRIPTIVE context, quoted verbatim from a
source artifact under the same fail-closed envelope. Each fails closed the same
way every other category does: an absent artifact -> `no_data`, a stale/zero-row
match -> `no_data`/`refused`, never a fabricated value. None of them is an edge
or profit claim (rule 6 still binds).

- `injury_report` / `news_context` -- newest-first injury-status rows / news
  items for a team or player, read verbatim off the edge-engine fact stores.
  Absent store -> `no_data`; if the newest matched row is older than the 7-day
  staleness bound -> `refused` (injuries and news churn weekly, so a stale
  answer is worse than none). Pass `team=`/`player=` (or phrase the query
  "injury report for <team>").
- `schedule_context` -- rest days / back-to-back / games-in-last-7 for one team,
  computed directly off the public games calendar (NBA/MLB only, same corpora
  as `historical_result`). Descriptive schedule physics, not a prediction; the
  envelope's `framing` field says so -- repeat it.
- `scouting_report` -- a multi-axis descriptive VECTOR for one player (per-concept
  ratings + shooting facet + top raw-attribute percentiles). Axes are reported
  independently and NEVER collapsed into one score; a player who resolves on no
  axis -> `no_data` naming the miss.
- `comparables` -- the K nearest players by RMS Euclidean distance over shared
  attribute percentiles. "Statistically similar profile", never a projection;
  a target below the shared-attribute floor -> `refused`.
- `matchup_preview` -- fans out over the shipped resolvers (win-prob + team
  profiles + style pairing + injuries + schedule) and quotes each block's own
  envelope verbatim. A block's own `no_data`/`refused` marks it absent in
  `blocks_absent` WITHOUT failing the overall preview; read `blocks_ok` to see
  which sub-answers landed.
- `prediction_winprob` -- now resolves a live calibrated probability by running
  the buyer-facing predictor as a subprocess (it authors no new number; the
  probability is quoted verbatim). On a clone with no forecast corpus it fails
  closed to `no_data`. Pass `home=`/`away=` (or phrase "win probability
  <HOME> vs <AWAY>"). Still probability only -- never a dollar edge.

## Reference implementation

`scripts/platformkit/answers/contract_client.py` IS this contract, executable
-- it classifies, resolves, and formats per rules 2-4 above with no model
call. A real LLM client should reproduce its behavior, not deviate from it.
`scripts/platformkit/answers/test_answer_consistency_{nba,mlb,soccer,tennis,intel}.py`
prove the two paths (direct resolver call vs. this contract client) produce
identical numbers for the same question (the `intel` file covers the six
descriptive-intel categories plus the rewired `prediction_winprob`); the sibling `test_answer_quality_*.py`
files (nba, mlb, soccer, tennis, wnba) cover answer-quality checks per sport.
