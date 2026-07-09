# Analytics -- Claude Playbook (start here)

Entry point for any Claude a downloader points at this repo: what the numbers
mean, where they come from, what you may and may not say about them.
Per-sport detail: [nba.md](nba.md), [mlb.md](mlb.md), [tennis.md](tennis.md),
[soccer.md](soccer.md), [wnba.md](wnba.md).

**The product, in one sentence:** a calibrated attribute + prediction layer
over five sports, where every number traces back to a real on-disk file and
every causal claim is gate-tested and, where claimed REPLICATED,
independently reproduced on a second corpus. Honest NULL and BLOCKED are
recorded successes, not failures.

## The pipeline: compute -> claim -> re-verify -> weight -> predict

1. **Compute.** A builder script reads real corpora on disk (play-by-play,
   Statcast, StatsBomb events, charted tennis points, etc.) and computes a
   number -- a rate, a split, a delta.
2. **Claim.** The number is written to a claims store
   (`data/cache/intel_claims/*.jsonl`) with its own inputs, sample size `n`,
   and a formula, so it can be independently recomputed and checked.
3. **Streaming re-verification.** A validator streams the source data again
   and recomputes each claim from scratch; a claim that does not match on
   replay is not trusted. Several families are already fully verified (e.g.
   MLB bullpen-fatigue-chains 9,060/9,060; soccer referee/foul profiles
   2,736/2,736; tennis fatigue-schedule-density 10,914/10,914).
4. **Weight gate.** `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`
   is the mechanism ledger: every preregistered hypothesis, with verdict
   `SURVIVES_PREREG` (passed once, provisional), `REPLICATED` (passed again
   on an independent corpus/season/split), `FAILED_REPLICATION`, `NULL`, or
   `BLOCKED` (no usable data existed to test it, no proxy invented). Only
   `REPLICATED` mechanisms are eligible to condition a live prediction;
   single-fold `SURVIVES_PREREG` stays PROVISIONAL, never settled.
5. **Predict.** Predictions and `VALIDATED_MECHANISM` draw only from step
   4's `REPLICATED` rows. Everything else is `DESCRIPTIVE` or
   `VALIDATED_CLAIM` and is presented as a fact, not a signal.

## The attribute engine

Each sport has a registry at `domains/<sport>/profiles/attribute_registry.py`
-- a plain Python dict, one entry per attribute, the single source of truth
for what it means and where it comes from. Nothing is mined fresh: every
entry names its real on-disk ingredient columns/files, its formula, and a
minimum sample size (`floor`) below which an entity is *omitted*, never
zero-filled. Read the registry file directly for full ingredient
provenance -- you can trace any number back to the exact column and file.

Attributes compile into long-format parquets at
`data/cache/profiles/<sport>_{player,team,lineup}_profiles.parquet`: one row
per entity+window+attribute, columns `raw_value`, `percentile`, `rating_2k`,
`n`, `ingredients` (json), `status`, `sources`. **`rating_2k` is
presentation-only** (`25 + percentile*0.74`, a 25-99 "franchise-mode
overall" band from rank in the qualified population) -- no causal or
predictive meaning, never feed it into a gate/fit/claim. `raw_value` is the
real number for anything analytical.

### Status labels

- `VALIDATED_MECHANISM` -- built on a mechanism with a `REPLICATED` verdict.
- `VALIDATED_CLAIM` -- independently re-verified by a streaming
  claims-store validator under a different claim family; arithmetic checked
  twice, not a causal mechanism.
- `DESCRIPTIVE` -- a real, honestly-sourced number, no causal or gate-tested
  backing. The default, most attributes -- a fact, not a predictive claim.
- `BLOCKED` (tennis, soccer only) -- registered but not built, exact reason
  given, so the registry documents the honest frontier.

## The ask CLI

`scripts/platformkit/profiles/ask.py` answers `<entity> <attribute>` queries
with the full row -- never a bare number -- by fuzzy-matching entity and
attribute names against the compiled profile parquets plus the registry
descriptions. No LLM; deterministic token/difflib matching.

```
python -m scripts.platformkit.profiles.ask --list --sport nba
python -m scripts.platformkit.profiles.ask "Luka Doncic gravity" --sport nba
```

```
Entity:     Luka Doncic  (nba player)
Attribute:  gravity
Window:     season_2025_26
Raw value:  0.0619
Percentile: 99.0888
n:          2282.47
Ingredients:
  teammate_efg_on = 0.5941
  teammate_efg_off = 0.5322
  min_on = 2282.47
Status:     VALIDATED_CLAIM -- claims re-verified against source data
Sources:    data/cache/team_system/lineups/gravity_proxy_2025_26.parquet
```

A second real transcript (`Manchester City counter_threat`, VALIDATED_MECHANISM)
plus one more per sport are in `nba.md`, `mlb.md`, `tennis.md`, `soccer.md`,
`wnba.md`.

## The rules for Claude (binding, verbatim)

1. **Never claim a betting edge.** This system produces calibrated
   predictions and verified analytics, not profit or win-rate-over-market
   claims. See `.claude/rules/no-edge-claims.md` for the retracted-number
   list -- never resurface those as current.
2. **DESCRIPTIVE attributes are facts, not predictors.** `status:
   DESCRIPTIVE` means the number is honestly computed and nothing more. Do
   not present a descriptive split as if it explains or forecasts an outcome.
3. **Every number you quote must carry `n`, `window`, and `status`.** A raw
   value with no sample size or provenance is not a citable claim here --
   always quote the full row, not the bare number.
4. **Honest NULL and BLOCKED are recorded successes.** A hypothesis that
   failed replication, came back NULL, or was BLOCKED is documentation of
   what does *not* work -- report it as such, never omit it.
5. **Per-file tests only.** Never run a full `pytest tests/` here -- it
   freezes the box. Scope every test invocation to the one file touched.
6. **Do not** write outside `docs/analytics/` from this lane; do not invent a
   number not backed by a file read in this session; do not treat a
   single-fold `SURVIVES_PREREG` row as `REPLICATED` -- the ledger's own
   `note` field says "PROVISIONAL -- needs independent replication" for a
   reason.
