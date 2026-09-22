# S363 capture watchdog and daily coverage

PREPARED: synthetic construct checks only; no archive run or deployment.
Vocabulary follows contract Q6; automated scan required.

Binding before-condition rerun before construction:

```text
ls scripts/platformkit/ingame/capture_watchdog.py
ls : Cannot find path 'C:\Users\neelj\nba-harness-h21\scripts\platformkit\ingame\capture_watchdog.py' because it does
not exist.
```

The command exited 1. The named game_market_link.py was also absent.
All five deliverables are new files in this worktree; existing modules remain
unchanged. The landed venue timestamp parser and winner-series classifier are
imported. All implementation dependencies are standard library or landed code.

The watchdog reads heartbeat objects and at most 65,537 bytes at each current
UTC shard's end, including one byte to identify a partial leading record.
Heartbeat file modification time is used when no explicit heartbeat timestamp
exists. Paired observation checks totals, nested failures and lock progress.
All reasons are retained; status precedence is SILENT, STALE, DEGRADED, OK.
Unknown counters and unknown live-state evidence remain explicit. Optional JSON
output must be outside the read-only archive root.

Coverage streams synthetic daily shards, counts distinct identities per UTC date
and sport, and reports distinct-time snapshot cadence per live winner ticker.
Median and nearest-rank p95 use adjacent sorted timestamps. Touch availability
requires both finite, nonnegative, non-null size fields; its denominator is all
snapshot rows. Bulk metadata alone does not establish a book. Gap counts include
unknown intervals; one unknown interval makes the total duration null, with a
separate known-duration subtotal. Fixtures use gap_start_ts/gap_end_ts or
start_ts/end_ts; no landed trade_gap producer schema was found.

Only an absent linker selects explicit ticker-level counts. In that mode game
totals and the >= 30 games-per-sport threshold result are null. An importable
linker resolves state games against captured ticker metadata through its public
matching API. Import, adapter and matching failures are counted and reported.
No game ID is guessed from a ticker.

Construct reproduction (one file at a time):

```text
python -m pytest tests/platformkit/ingame/test_capture_watchdog.py -q -p no:cacheprovider
python -m pytest tests/platformkit/ingame/test_capture_coverage_daily.py -q -p no:cacheprovider
```

Initial preparation results: watchdog 43 passed; coverage 35 passed.
Both CLI --help commands passed in that preparation.
Fixtures cover every status, named failure growth, rate thresholds, missing and
invalid fields, finite-number refusal, fractional timestamps, order invariance,
exit codes, read-only roots, bounded tail reads and forbidden price-field access.
No test depends on a gitignored fixture. Contract B/Q review: no existing schema,
threshold or production caller changed; this is an exhaustive construct check,
not a scored comparison. Automated preflight passed all nine checks over these
five files, including vocabulary and the 300-line cap. Git status showed exactly
these five untracked deliverables and no changes to pre-existing files.

Two finisher commands, documented only and NOT RUN in this preparation:

```text
python -m scripts.platformkit.ingame.capture_watchdog --root data/cache/ingame_books_local --max-age-s 300 --watch-s 60
python -m scripts.platformkit.ingame.capture_coverage_daily --root data/cache/ingame_books_local
```

## FIX 1b

Both row-owned modules were edited in this worktree. Coverage now defines a
resolver protocol: a state game metadata row plus captured ticker metadata rows
returns (matched game identity, matched tickers, None), or (None, (), reason).
The lazy import adapter calls index_kalshi_events and link_game, forwarding the
scheduled start when supported. Those public signatures were read from the S358
candidate at C:/Users/neelj/nba-harness-h16/scripts/platformkit/ingame/game_market_link.py;
that file was neither copied nor edited. Only metadata allowlisted by LINK_FIELDS
reaches the linker. Daily source sets are joined after collecting the day's rows,
so state-before-market ordering is supported. Repeated games count once.

Only ModuleNotFoundError naming the linker itself selects ticker fallback.
A missing dependency, unsupported adapter or raised matching error instead
produces named error counts, linkage=linker_error and a nonzero CLI exit.
Unmatched results retain their reason and increment unlinked_state_rows.

The watchdog uses one timestamp helper for tail rows, heartbeat timestamps and
last_write_ts. It normalizes finite Decimal/int/float epochs, passes strings to
the shared venue parser and refuses nonfinite values. JSON decoding still
preserves fixed-point numbers as Decimal.

FIX 1b results: watchdog 45 passed; coverage 39 passed. The fractional-epoch
regression exercises JSON-decoded heartbeat, last-write and tail timestamps for
both sources. Fake-importable-linker fixtures verify two NBA games and one NFL
game, all per-source totals, running totals and counted matching failures.
Import/dependency failures, unsupported APIs and unmatched reasons are covered.
The existing bounded-tail and forbidden-price-access checks still pass.
Both CLI --help commands exited 0. All five edited files are ASCII and below
the 300-line cap. No archive command or deployment was run.

Contract reproduction:

```text
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/capture_watchdog.py scripts/platformkit/ingame/capture_coverage_daily.py tests/platformkit/ingame/test_capture_watchdog.py tests/platformkit/ingame/test_capture_coverage_daily.py docs/evidence/harness/S363_capture_watchdog_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S363_spec.md
```

## FIX 1c

Local construct-only repair in C:/Users/neelj/nba-harness-h21. The worktree spec
and `git show master:docs/evidence/tracking/specs/S363_spec.md` were both read;
neither contained an AMENDMENT block. No other worktree was written.

Finding 1 (BLOCKING): reproduced both count defects before changing the module.
The minimal fixture used fresh source() objects from test_capture_watchdog.py,
set both written totals to 2**53 in the previous heartbeat and 2**53 + 1 in the
current heartbeat, then called assess(current, previous, NOW, 300). The second
fixture set the live counts, written totals, HTTP failure count and failure
counter to Decimal("0.5"), requests to Decimal("100.5"), and assessed once.
Exact failing output:

```text
INPUT before=9007199254740992, after=9007199254740993
NORMALIZED [9007199254740992.0, 9007199254740992.0]
OUTPUT status=SILENT, reasons=['counter_flat:rows_written_total', 'counter_flat:trades_written_total', 'trades_flat_while_live_winner_markets']
FRACTIONAL status=OK, reasons=[]
```

capture_watchdog.py now has a separate nonnegative integral_count parser.
Only finite integral int/Decimal values are accepted and returned as int;
booleans, all floats, fractional values and missing values are rejected.
Live counts, requests, HTTP failure counts, written totals and nested failure
counters use it. HTTP count ratios use exact integer cross-multiplication at
the unchanged one-percent boundary. Rates and timestamp handling are unchanged.
Only whitespace was compacted to retain the per-file line cap.

The same fixtures now produce:

```text
NORMALIZED [9007199254740992, 9007199254740993]
OUTPUT status=OK, reasons=[]
FRACTIONAL status=DEGRADED, reasons=['invalid_error_counter:error_counters.max_pages_exceeded', 'invalid_http_counts:429', 'invalid_live_count:n_games_live', 'invalid_live_count:n_live_winner_markets', 'missing_or_invalid_counter:rows_written_total', 'missing_or_invalid_counter:trades_written_total']
```

Added 45 regression cases covering parser acceptance/refusal, exact large
written-total increments, exact failure-counter growth, every count category,
and the strict HTTP count-rate boundary. Before the module repair, the per-file
run reported `35 failed, 55 passed`. After repair it reported `90 passed`.
All original test bodies are retained.

Finding 2 (NOTE): reran both unchanged per-file command forms listed above in
this sandbox; temporary fixture storage worked. Watchdog: 90 passed. Coverage:
39 passed. This includes the dynamic bounded-tail regression and guarded-price
fixtures. The coverage module and its tests were not edited in FIX 1c.

Finding 3 (NOTE): no requested correction. Preserved the confirmed linker,
silent-detection and epoch handling. Both CLI --help commands exited 0.
Neither CLI exposes a self-check command; the construct tests are its checks.
Contract preflight uses the five row deliverables in the command above and
excludes the verifier verdict file. All nine checks passed. The five row files
are ASCII and at most 300 lines each. No commit was created in this sandbox.

## FIX 1d

Read _verdict_s363_1d.md first. The local spec and master spec have no
AMENDMENT blocks. This repair changes only the row's watchdog module, its
tests and this memo, in C:/Users/neelj/nba-harness-h21.

Finding 1 (BLOCKING): reproduced the verifier's serialized integral-float
payload before editing the module. Start with source() from
tests/platformkit/ingame/test_capture_watchdog.py, decode the JSON below with
watchdog.decode(payload, Counter()), update its heartbeat, then call
assess(item, None, NOW, 300). All eight decoded counter values are Decimal.

```json
{"n_games_live":1.0,"n_live_winner_markets":1.0,"rows_written_total":20.0,"trades_written_total":4.0,"n_requests_10min":100.0,"n_429_10min":1.0,"n_403_10min":0.0,"error_counters":{"max_pages_exceeded":0.0}}
```

Exact failing output (assert status == 'DEGRADED'):

```text
NORMALIZED [1, 1, 20, 4, 100, 1, 0, 0]
OUTPUT {'status': 'OK', 'reasons': [], 'errors': {}}
AssertionError: {'status': 'OK', 'reasons': [], 'errors': {}}
```

integral_count now accepts only `type(value) is int and value >= 0`, returning
the original integer. Integral Decimal acceptance was removed, including the
obsolete accepted test cases. Exact integer progress around 2**53 remains
covered. Existing timestamp, rate, size, linker and coverage behavior is retained.

The same reproduction now exits 0 with this exact output:

```text
NORMALIZED [None, None, None, None, None, None, None, None]
OUTPUT {'status': 'DEGRADED', 'reasons': ['invalid_error_counter:error_counters.max_pages_exceeded', 'invalid_http_counts:403', 'invalid_http_counts:429', 'invalid_live_count:n_games_live', 'invalid_live_count:n_live_winner_markets', 'missing_or_invalid_counter:rows_written_total', 'missing_or_invalid_counter:trades_written_total'], 'errors': {}}
```

The category regression now decodes serialized JSON `1.0` and `1e0` for each
of the eight counter fields above: n = 16 (CONSTRUCT). Each case requires
DEGRADED and its category-specific invalid-counter reason. Direct parser
regressions also reject Decimal("1.0") and Decimal(2**53 + 1).
Before the module fix, the prescribed watchdog test command produced
`18 failed, 87 passed`; after the fix it produced `105 passed`.

Finding 2 (NOTE): reran both prescribed per-file commands with TEMP and TMP
set to C:/Users/neelj/nba-harness-h21/.tmp_s363_1d and
PYTHONDONTWRITEBYTECODE=1. Writable fixture storage worked: watchdog 105 passed;
coverage 39 passed. Coverage source and tests were not edited in FIX 1d.
Both CLI --help commands exited 0. Neither exposes a self-check option;
the per-file construct tests supply those checks.

The contract reproduction command above covers all five row deliverables,
excluding the verdict. All nine checks passed. Every row file is ASCII and
at most 300 lines. No real archives, network, pod or measured results were used.
Files remain on disk for lane_commit; no commit was created.

NOT VERIFIED:
- Real archive contents, source health, daily totals or cadence.
- Runtime state-capture heartbeat schema and trade_gap producer interval fields.
- Integration with the real S358 module after landing, or game-count readiness.
- Live observation over wall-clock time, scheduling or alert delivery.
- Any measured calibration, fill or markout result.
- Pod execution or deployment; the pod remains OFF.
