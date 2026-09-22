# S377 - PREPARE candidate; counts only

The three new files implement CHANGE 1-3 of
`docs/evidence/tracking/specs/S377_spec.md`. No pre-existing module was edited.
All work ran locally in `C:/Users/neelj/nba-harness-h34` using constructed inputs.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
The shorter contract path in the request does not exist in this checkout.

## Binding before-condition

Run before implementation: `ls scripts/platformkit/ingame/nba_corpus_readiness.py`.
Exit code: 1. Output quoted from this session:

```text
ls : Cannot find path 'C:\Users\neelj\nba-harness-h34\scripts\platformkit\ingame\nba_corpus_readiness.py' because it
does not exist.
At line:2 char:1
+ ls scripts/platformkit/ingame/nba_corpus_readiness.py
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: (C:\Users\neelj\...us_readiness.py:String) [Get-ChildItem], ItemNotFound
   Exception
    + FullyQualifiedErrorId : PathNotFound,Microsoft.PowerShell.Commands.GetChildItemCommand
```

## Read dependencies and exact signature

Read `scripts/platformkit/execution/venue_time.py` before implementation.
The only imported landed callable is exactly:
`def parse_venue_time(value: object) -> float | None:`.
It validates aware ISO timestamps with up to nine fractional digits but truncates
its return value to microseconds. The census validates using that function,
parses the whole-second portion through the same function, then appends the
original fractional digits as integer nanoseconds. It never uses a rounded
fractional float for keys, maximum timestamps, future filtering, or embargoes.
No other landed callable is imported by the production module.

Read `scripts/platformkit/ingame/nba_checkpoints_to_joined.py` for the emitted
state string, JSONL format, and `{"files": {filename: sha256}}` manifest shape.
It is not imported or edited. Read the design audit named in the spec.

## Census definitions

- Files are top-level `*.jsonl` inputs, streamed one file at a time in binary.
  `census.json` and `manifest.json` are metadata, never tick data. Byte counts
  include every data-file byte. `file_bytes` and `manifest.files` share filenames.
  `manifest_sha256` hashes ASCII JSON of `{"files": mapping}`, sorted keys,
  compact separators, no trailing newline. Converter status is missing,
  invalid, differs, or agrees. Hashes necessarily change when row bytes change.
- `records` counts nonblank source records. `ticks` counts parseable, aware,
  non-future timestamps before other validation. `refused_ticks` counts each
  malformed or schema-refused row once; reason counters can overlap.
  Future rows are skipped before identity, state, probability, and duplicate
  validation. Whole-file provenance and `future_records` still record their
  existence. Numeric JSON tokens stay typed lexemes until after this filter.
- Keys use exact parsed UTC nanoseconds. Identical duplicate keys have only one
  payload fingerprint and multiple occurrences; excess counts repeated payloads,
  including repeats within conflicting keys. Conflicting keys have multiple
  fingerprints and contribute zero eligible ticks, regardless of order.
  Invalid duplicate JSON fields are counted and cannot alias clean records.
- Raw state/period, model, outcome, exposure, and post-final diagnostics include
  duplicates and refused rows wherever the relevant field can be parsed.
  Outcome consistency uses valid binary outcomes across all keyed rows; unknown
  games are separate. Per-game output includes model counts/class and the number
  of distinct valid outcomes. Model classes mean valid non-null coverage across
  all keyed rows; null or invalid values contribute no present-model tick.
  Invalid and missing fields remain visible in refusal counters.
- Eligibility collapses identical keys, excludes core-market/schema failures and
  every conflicting key, and excludes games with contradictory valid outcomes.
  Null, missing, or invalid model values do not exclude otherwise-valid keys;
  missing/invalid model fields still count refusals and absent model coverage.
  Live eligibility additionally removes quarter >= 4 with seconds_remaining == 0.
- State counts use integer lexical grammar because the converter embeds them
  in a string. Decimal or boolean count spellings are refused, never rounded.
  Defensive bounds refuse scores above 1000 and quarters outside 1-20. Regulation
  remaining time must lie within that quarter's interval; overtime allows 0-300.
  Decimal validates clocks and probabilities exactly, including finiteness;
  probabilities must lie strictly inside (0,1). There is no float conversion,
  clipping, scaling, or missing-value substitution in these checks.
- First UTC dates and maximum timestamps use every parseable keyed tick,
  including subsequently excluded rows. Each date is one whole-game fold.
  Expanding training uses only games with eligible ticks in that population
  whose maximum timestamp is strictly before test midnight minus three days.
  No future training game is admitted; the symmetric embargo's future side is
  therefore empty. Post-final exclusions never move a game's finish earlier.
  Warm-up counts nonempty test populations with no eligible training game.
  All and live populations each get training, warm-up, and post-warm-up counts.
- `close_not_max_games` counts games whose set of valid declared close times
  differs from the singleton maximum observed timestamp. Missing or unparseable
  close fields are separately refused, including when other valid closes match.
- Exposure input is a CSV file with a `game_id` header and nonempty string IDs;
  repeated exposure IDs are refused as redundant membership records and counted
  in `refused_duplicate_ids`, without multiplying exposure. Malformed configuration or I/O
  errors propagate without publishing a partial report. Exposure counts raw
  keyed games/ticks and is descriptive; it does not change eligibility.
- The output path must be outside the corpus. A temporary sibling is flushed
  and fsynced before atomic replacement. A failure preserves the prior report;
  a completed staged file remains recoverable if replacement fails.

## Construct validation

The first test consumes the REAL ROW verbatim as its fixture, flattening only
the spec's presentation newlines into a single JSONL record, through the CLI
entry point and its written JSON report. Other fixtures cover every requested
count, both file/row permutations, absent models, conflicting outcomes/keys,
post-final runs, metadata handling, UTC dates, nanosecond boundaries, malformed
state/count/probability fields, future records, and interrupted publication.

The hand-worked embargo fixture has final-only A on Jan 1, live B on Jan 2,
C on Jan 4, D on Jan 5, and two ticks for E on Jan 6. All eligibility has
3 warm-up folds and 2 post-warm-up games / 3 ticks. Live eligibility has
3 warm-up folds and 1 post-warm-up game / 2 ticks. These are constructs only.

Reproduction:
```text
python -m pytest tests/platformkit/ingame/test_nba_corpus_readiness.py -q -p no:cacheprovider
python -m scripts.platformkit.ingame.nba_corpus_readiness --help
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/nba_corpus_readiness.py tests/platformkit/ingame/test_nba_corpus_readiness.py docs/evidence/harness/S377_nba_corpus_readiness_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S377_spec.md
```

Initial validation: 43 construct tests passed; the CLI help exited 0; all 9 preflight
checks passed (vocab, crlf, loc, schema, head_slice, spec_threshold, proposed,
removed_artifact, row_duplication). The source has 300 lines and the test has
290 lines, counted with `len(text.splitlines())`; all three files are ASCII.
Git status lists only the three owned files as new; no tracked module changed.
The read-only review's duplicate-field and extreme-number findings have direct
construct coverage. Its live-finish question is resolved by the whole-game
finish rule documented above. Independent acceptance remains outstanding.

## FIX 1b

1. BLOCKING: invalid non-null model values incorrectly excluded otherwise-valid
   keys from both populations. The row module now separates core eligibility
   from model validation. Model failures retain their refusal reason and row
   refusal count and contribute absent coverage, while core failures still
   exclude the key. Explicit null remains eligible without a refusal.
   The regression test distinguishes invalid market from invalid/null model
   values, checking both populations and per-game/per-period model absence.
   It covers zero, one, NaN, both infinities, nonnumeric values, and null.

   Minimal reproduction before the module edit (constructed single-row JSONL):
   ```text
   model_prob=None -> refusals={} eligible.all=1 eligible.live=1
   model_prob=0 -> refusals={'model_prob:outside_open_unit_interval': 1} eligible.all=0 eligible.live=0
   model_prob=1 -> refusals={'model_prob:outside_open_unit_interval': 1} eligible.all=0 eligible.live=0
   ```
   Same reproduction after the edit, with eligibility/absence assertions:
   ```text
   model_prob=None -> refusals={} eligible.all=1 eligible.live=1
   model_prob=0 -> refusals={'model_prob:outside_open_unit_interval': 1} eligible.all=1 eligible.live=1
   model_prob=1 -> refusals={'model_prob:outside_open_unit_interval': 1} eligible.all=1 eligible.live=1
   Minimal reproduction: 3/3 PASS
   ```
2. NOTE: tied regulation-ending ticks remain classified by the current spec's
   exact post-final predicate. Neither the local authority nor
   `git show master:docs/evidence/tracking/specs/S377_spec.md` has an AMENDMENT.
   The verifier requires an authority amendment first; this fix does not edit
   that authority or the predicate it confirmed matches the spec.
3. NOTE: no change requested for embargo, order independence, malformed-state
   refusal, integer counts, or restricted output. Those implementations remain
   unchanged and their existing construct assertions passed again.

FIX 1b validation: 50 construct tests passed in the single owned test file;
the minimal reproduction passed 3/3; CLI `--help` exited 0. The CLI exposes no
self-check command. TEMP and TMP pointed into this worktree so test fixtures
could be written without using another worktree or an external temp directory.
The commands are the same per-file test, CLI help, and three-path preflight
listed above. No production input was read.
All 9 contract-preflight checks passed. The module/test line counts are 300/299;
all three owned files are ASCII. No tracked files changed. The synthetic
`pytest-of-neelj/` fixture directory remains untracked: automatic approval
review rejected its cleanup as blocked by policy. Exclude it from lane_commit.

## NOT VERIFIED

- No real corpus or archive was opened; no production denominator was measured.
- No network, pod, model fit, score, or calibration statistic was exercised.
- No real exposure file, source/model provenance, team purge, or new prereg was validated.
- No production-scale memory or throughput test ran; key fingerprints remain in memory.
- No hardware power-loss test ran; fsync and replacement failures were simulated.
- No independent verifier acceptance or git commit was created in this sandbox.
