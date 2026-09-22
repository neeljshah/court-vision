# S365 family/week continuity ledger

PREPARED: construct-only weekly accounting; G6 remains unverified.
Vocabulary follows contract Q6; automated scan required.

Machine: local Windows worktree `C:/Users/neelj/nba-harness-h23`.
The pod is OFF. No archive, network or data directory was accessed.
Design: `docs/evidence/harness/ASTRA_ROUND12_2026-09-21.md`, section 6 row 6.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

## Binding before-condition

Before creation, `ls scripts/platformkit/execution/family_week_ledger.py`
exited 1 with this output:

```text
Cannot find path 'C:\Users\neelj\nba-harness-h23\scripts\platformkit\execution\family_week_ledger.py' because it does not exist.
```

G6 text from `docs/GO_LIVE_GATES.md`:

> At least 8 consecutive weeks of shadow maker quoting on the G3 instrumentation,
> fee-netted markout positive with a game-clustered 95 percent interval excluding
> 0, on at least 2 independent market families, with a pre-registered single-game
> and single-week concentration check; a sign flip across calendar halves is a
> reject | anything less

## Operational definition

Exactly three new files constitute this row: the module, its fixture test file,
and this memo. There are no pre-existing module edits or production callers.
The implementation uses the standard library and imports the landed
`scripts.platformkit.execution.venue_time.parse_venue_time` for zoned times.
No exception is swallowed. Invalid evidence raises instead of disappearing.

The caller supplies both paths. The family table is a JSON list; each entry has
`family`, `sport`, `market_type`, positive integer `weekly_floor`, and
`independence_rules`, a mapping from every other family id to a nonempty rule.
No numerical weekly floor is invented by this row. A canonical declaration
digest is stored in each line; reads of completed weeks reject changed declarations.
Table order does not affect that digest.

Each weekly record requires `iso_year`, `iso_week`, `family`, `sport`, all
considered `game_ids`, `qualified_game_ids`, `fill_bearing_game_ids`, integer
`qualified_games` and `fill_bearing_games`, `exclusions` mapping reason to game
ids, `capture_gap_seconds`, `source_artifact_path`, and `source_sha256`.
Every count must equal its distinct-id count. Fill-bearing ids are a subset of
qualified ids, which are a subset of all considered ids. Every unqualified id
has at least one exclusion reason; reasons may overlap and must not be summed
as a unique denominator. Missing fields never default to zero.

Capture gaps are finite nonnegative Decimal strings. No order sizes or
quantities are processed. Source paths and lowercase SHA-256 strings are
recorded without opening sources. Callers provide canonical cross-family game
identities and upstream qualification decisions. These declarations are not
independently certified by this ledger.

Weeks are UTC ISO calendar weeks. Only completed weeks are accepted, relative
to `--as-of` (a zoned venue timestamp, default UTC today). `streak(family)` ends
at the latest completed week; a missing or below-floor week stops traversal.
An old run becomes zero after a missing latest completed week. Open weeks
cannot prematurely qualify. Week arithmetic uses calendar dates across ISO
year boundaries. Historical reproduction uses the same explicit as-of time.

`independence(year, week)` reports all declared family pairs. Any shared id,
including an excluded game, yields `NOT INDEPENDENT`. An absent family record
yields `MISSING EVIDENCE`; disjoint ids yield `DECLARED INDEPENDENT`. Pair status
does not convert the separate per-family continuity counts into G6 approval.

`forecast(family, games_per_week)` prints and returns the Sunday on which eight
weeks could complete, conditional on the open week and each necessary future
week meeting the floor. Below-floor rates yield no completion date; games
cannot carry across weeks. A run already at eight returns its first completion
Sunday. This is a calendar lower bound, not a collection prediction.

Append preserves existing bytes, refuses duplicate family/week keys and fsyncs
new lines. Reads check line framing and ISO weeks, then validate completed-week
rows; partial final lines are rejected. Serialization sorts ids and object keys;
summaries sort weeks and
family pairs. Input record order does not change query results. Physical JSONL
line order necessarily records append order. One writer is required; process
serialization belongs to the caller.

## Construct verification

All synthetic input files are constructed under pytest temporary paths by
`tests/platformkit/execution/test_family_week_ledger.py`. Tests read no ignored
fixture or real archive. The synthetic source label in those rows is metadata,
not an input opened by the test. No image input exists; resolution is inapplicable.

Executed locally:

```text
python -m pytest tests/platformkit/execution/test_family_week_ledger.py -q -p no:cacheprovider
57 passed
python -m scripts.platformkit.execution.family_week_ledger --help
exit 0
```

Cases cover missing and stale weeks, a below-floor break, shared games,
excluded-game overlap, missing-family evidence, disjoint declarations, duplicate
refusal and byte preservation, ISO year boundaries, forecast arithmetic,
order invariance, malformed and missing fields, non-finite values, undeclared
exclusions, declaration changes, corrupt lines, all CLI operations, every
subcommand's help, and invalid or fraction-bearing venue timestamps.

Automated scan: all 9 checks PASS, exit 0 (vocabulary, CRLF, LOC, schema,
head-slice, spec thresholds, proposed diff, removed artifacts, row duplication).
Read-only implementation review found no blocking findings.
Reproduce the automated scan with:

```text
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/family_week_ledger.py tests/platformkit/execution/test_family_week_ledger.py docs/evidence/harness/S365_family_week_ledger_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S365_spec.md
```

Contract B self-check: all considered ids and exclusion reasons remain visible;
only new files are added; missing evidence stays explicit; no claim/retry loop,
deployment, retired module, sampled metric, fitted comparison, or gate change.
Contract Q self-check: no scored trial or comparison was performed, so scoring
seals, charges, cross-validation and corpus comparisons are inapplicable.
The eight-week target and two-family requirement remain unchanged. Construct
tests provide code evidence only.

## FIX 1b

The independent verdict identified one BLOCKING finding: historical replay
applied the append-time completed-week guard while reading stored rows.
There were no CORRECTION findings. The worktree and master specs match and
contain no AMENDMENT blocks.

Reproduced before changing the module, using constructed W37 and W38 rows
appended with as-of 2026-09-21, then reopened at W38 Monday
(`2026-09-14T00:00:00Z`). The required expected streak was 1. Actual output:

```text
E           ValueError: only completed ISO weeks may be appended
2 failed, 57 passed in 1.65s
```

Both chronological and reversed append orders reproduced the finding.
The exact fix separates invariant validation from the append-time guard:
`_validate()` checks valid ISO weeks without comparing them to query time;
`append()` alone enforces that new rows describe completed weeks; `records()`
validates every stored row, then returns only weeks before the query's current
ISO week. Historical streak, forecast and independence queries use that view.
Duplicate and corruption checks still inspect every stored row.

Regression: `test_historical_query_ignores_later_weeks` covers both append
orders, asserting streak 1, visible weeks `[37]`, conditional forecast
2026-11-01 and missing evidence for open/future week independence queries.
The existing rejection of appending an open week also still passes.

Reproduction and verification used only constructed fixtures in this worktree.
Set TEMP and TMP to `C:/Users/neelj/nba-harness-h23` and
PYTHONDONTWRITEBYTECODE to `1` before the mandated command, avoiding the
verifier's unavailable temporary-directory setup:

```text
python -m pytest tests/platformkit/execution/test_family_week_ledger.py -q -p no:cacheprovider
59 passed in 0.94s
```

All five CLI help commands (top level, append, streak, forecast, independence)
exit 0. This row defines no self-check command. Contract B/Q self-check:
only the three row-owned candidate files changed; no schema or threshold
changed; these are constructed cases without a scored comparison.
The exact contract_preflight command above passes all 9 checks over these
three files, excluding the verdict. All three files are ASCII and below
300 lines. No commit was created; files remain ready for lane_commit.

## FIX 1c

Finding 1 (BLOCKING): `records()` validated and deduplicated current/future
weeks before filtering them. Reproduced with two valid identical W38 rows,
queried at W38 Monday (`2026-09-14T00:00:00Z`), before changing the module:

```text
E                   ValueError: duplicate family week
6 failed, 59 passed in 1.44s
```

The six added cases enumerate duplicate rows, a changed declaration seal and
a missing schema field, each queried at W37 and W38 Monday. All six failed
before the fix. `records()` now minimally validates `iso_year`/`iso_week` with
`_monday()`, skips weeks >= the query's current week, and only then checks the
declaration seal, full schema and duplicate set. This supersedes FIX 1b's
statement that duplicate/schema checks inspect every stored row.

Regression `test_historical_filter_precedes_row_validation` asserts the rows
are invisible and the streak is zero before W38 completes; the same stored
rows are refused with their specific errors at W39 Monday. The original 59
cases remain unchanged. After the module fix:

```text
65 passed in 1.07s
```

Finding 2 (CORRECTION): reproduced the scratch inclusion ambiguity with
`git status --porcelain`, whose output included:

```text
?? pytest-of-neelj/
```

Per the orchestrator's ruling, the candidate is exactly these three paths:

- `scripts/platformkit/execution/family_week_ledger.py`
- `tests/platformkit/execution/test_family_week_ledger.py`
- `docs/evidence/harness/S365_family_week_ledger_2026-09-21.md`

`pytest-of-neelj/` is uncommitted scratch, excluded from the candidate by the
orchestrator's explicit pathspec. It was not deleted. No regression test was
requested for this scope correction. FIX 1c pytest runs use `--basetemp` under
`C:/Users/neelj/AppData/Local/Temp/`, outside the worktree, successfully avoiding
new in-worktree scratch. PYTHONDONTWRITEBYTECODE is `1`. Reproduction command:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$s365Temp = Join-Path $env:TEMP ('s365-fix1c-' + [guid]::NewGuid().ToString('N'))
python -m pytest tests/platformkit/execution/test_family_week_ledger.py -q -p no:cacheprovider --basetemp $s365Temp
```

Finding 3 (NOTE): no fix requested; the confirmed behaviors are unchanged.
All five help commands exit 0; the row has no self-check CLI. Contract B/Q
self-check: no schema or threshold changes, no scored comparison, constructed
fixtures only. Worktree and master specs contain no AMENDMENT blocks.
The exact three-path contract_preflight command above passes all nine checks.
NOT VERIFIED remains the final section; no production evidence is inferred.

## NOT VERIFIED

- Real source artifact contents, supplied hashes, game linkage or qualification.
- Substantive independence of declared family rules or real weekly continuity.
- Collection throughput, future instrument availability or forecast realization.
- Concurrent writers, interruption recovery or external edits to the JSONL file.
- Any measured calibration, fill or markout result, or any remaining G6 condition.
- Production integration, deployment, activation, or a lane_commit SHA.
