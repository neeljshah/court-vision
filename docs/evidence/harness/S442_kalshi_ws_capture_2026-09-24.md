# S442 Kalshi socket capture - 2026-09-24

Candidate: NOT VALIDATED pending independent verification. Local CONSTRUCT only.
Machine: C:/Users/neelj/nba-harness-h97, Windows, no socket, DNS, network or pod.
Owned files: the module (kalshi_ws_capture.py), its frame-grammar helper module
(kalshi_ws_frames.py, split out to keep the module under 300 LOC after FIX 1b),
the original test file, the FIX 1b regression test file, and this memo. No
landed module edited.

## Binding before-condition and premise

The spec contains no literal BINDING BEFORE-CONDITION command. Its absence-based
before-condition was run before coding; binding adjustments set n = 16 (CONSTRUCT).
Command: `python -c "from pathlib import Path; p=Path('scripts/platformkit/ingame/kalshi_ws_capture.py'); print('module_absent=' + str(not p.exists())); print('before=0/16 CONSTRUCT' if not p.exists() else 'before_requires_review')"`
Exact output, exit 0:
```
module_absent=True
before=0/16 CONSTRUCT
```
Independent main-lane check also printed `before = 0 / 16 (module absent)`.

Exact original commands and outputs (before edits):
`git grep -n -i "api_key|KALSHI_|Authorization|private_key" -- scripts/platformkit/ingame`
stdout empty, exit 1.
`git grep -n -i "orderbook_delta|ticker_v2|wss://" -- .`
exit 0, stdout verbatim:
```
docs/evidence/tracking/specs/S442_spec.md:11:(f) `git grep -n -i "orderbook_delta|ticker_v2|wss://" -- .` returns NOTHING repo-wide -- the venue's channel names are UNVERIFIED in this repo and are NOT fetched here; the module takes them as a required CLI/config argument with no hardcoded default, and the memo states them UNVERIFIED pending an owner confirmation from the venue's own public docs before any live run.
```
These basic-regex commands search literal pipes; they do not establish absence.
The channel result is a spec self-reference. The binding adjustment supplies the correction:
`git grep -n -E 'orderbook_delta|ticker_v2|wss://' -- scripts/stream_kalshi.py`
```
scripts/stream_kalshi.py:65:            "channels": ["orderbook_delta"],
```
This is the designated in-tree subscription evidence. The subscription message
at lines 61-68 and TEXT-to-JSON handling at lines 77-78 are ported with source comments.
That script is not imported or changed. Channels remain UNVERIFIED until owner
confirmation from venue public documentation. No documentation was fetched here.
`python -c "import websockets; print('websockets', websockets.__version__)"` printed `websockets 16.0`.
`python -c "import websocket"` failed with `ModuleNotFoundError: No module named 'websocket'`.
No dependency was added. Backoff is the landed 1-second doubling shape capped at 300 seconds.

## Read-before-code API signatures

All imported landed modules were read before coding. Exact declarations relied on:
```
book_row(market: dict, body: Any, ts_ms: int, capture_ts: str,
         enqueue_ts_ms: int | None = None, close_time: str | None = None,
         *, request_start: str, response_end: str, http_status: int, errors=None) -> dict
trade_row(market: dict, trade: dict, capture_ts: str, request_start: str,
          response_end: str, http_status: int) -> dict
parse_venue_time(value: object) -> float | None
parse_ts(value: Any, errors: Optional[Counter] = None) -> Optional[datetime]
iso(value: Optional[datetime] = None) -> str
utcnow() -> datetime
Metrics.__init__(self, utc_clock=utcnow) -> None
Metrics.drop(self, source: str, reason: str) -> None
ArchiveWriter.__init__(self, root: Path, metrics: Metrics) -> None
ArchiveWriter.__enter__(self) -> ArchiveWriter
ArchiveWriter.append(self, row: dict, source: str, quarantine: bool = False) -> Path
ArchiveWriter.sync(self) -> None
ArchiveWriter.__exit__(self, *_args: Any) -> None
encode_json(value: Any) -> str
ARCHIVE_ROOT = _ROOT / "data" / "cache" / "ingame_books_local"
```
The writer owns its sibling root's lock and recovery glob. Each unbuffered append
is immediately fsynced. A short write fails the writer and is recoverable on reopening.
Normal book/trade rows retain the REST builders' keys and values except record_type.
Continuity intervals are separate `missing_interval_ws` records with last_good_seq,
last_good_ts and resync_snapshot_ts; an unresolved interval has a null end.
Reconnect marks interruption and re-subscribes, preserving trade IDs in this process.
Numeric JSON decimals parse directly as Decimal. Original raw values remain untouched.
Quantities outside 1e-18..1e24 and prices outside 1e-18..<1 are refused, not clamped.
These are prepare-only refusal bounds, not an assertion of venue limits.
Venue grammar uses parse_venue_time; a Decimal fractional remainder retains nanoseconds
for future-record filtering before schema and sequence checks.

## Construct acceptance table

Before: 0 / 16. Bar: 16 / 16. n = 16 (CONSTRUCT). No real frame is supplied by the spec.
The first test consumes the embedded snapshot fixture through parser, row builder,
writer and byte comparison end to end. No sampled or scored comparison is made.

| Case | Named independent construct | Test |
| --- | --- | --- |
| 1 | Snapshot REST keys/values and archive bytes | test_01_snapshot_fixture_end_to_end |
| 2 | Delta changes stored depth | test_02_delta |
| 3 | Sequence gap counted and resync flagged | test_03_gap_resync |
| 4 | Duplicate frame counted without duplicate row | test_04_duplicate |
| 5 | Reconnect counter and 1-double-300 sequence | test_05_reconnect |
| 6 | Protocol ping produces pong with zero application rows (library-level: the websockets Sans-I/O Protocol answers the ping; the test exercises the library, not this module's own code) | test_06_protocol_ping |
| 7 | Malformed byte and JSON shapes counted | test_07_malformed |
| 8 | Decimal precision and bare JSON numbers | test_08_decimal |
| 9 | Missing/unreadable/literal credentials refuse before writes | test_09_credentials |
| 10 | Absent/unconfirmed/UNVERIFIED channels refuse | test_10_channels |
| 11 | Live, existing sibling and overlapping roots refuse | test_11_live_root |
| 12 | Non-ASCII input is escaped in ASCII output | test_12_ascii |
| 13 | Fixture and source paths, bytes, SHA-256 match this memo | test_13_a9_identity |
| 14 | Multiple deltas agree byte-for-byte with reconstructed REST book | test_14_reconstructed_agreement |
| 15 | Open/closed interval with both instants; no continuous interior row | test_15_missing_interval |
| 16 | Trade identity matches REST and deduplicates across reconnect | test_16_trade_dedup_reconnect |

## Reproduction and results

`python -m pytest tests/platformkit/ingame/test_kalshi_ws_capture.py -q -p no:cacheprovider`
`python -m pytest tests/platformkit/ingame/test_kalshi_ws_capture_1b.py -q -p no:cacheprovider`
`python -m scripts.platformkit.ingame.kalshi_ws_capture --help`
`python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/kalshi_ws_capture.py scripts/platformkit/ingame/kalshi_ws_frames.py tests/platformkit/ingame/test_kalshi_ws_capture.py tests/platformkit/ingame/test_kalshi_ws_capture_1b.py docs/evidence/harness/S442_kalshi_ws_capture_2026-09-24.md --base master --spec docs/evidence/tracking/specs/S442_spec.md`
Final test output: `40 passed` (original file) + `9 passed` (FIX 1b file) = 49 passed
across both files, run one file at a time (exit 0 each). Acceptance constructs: 16 / 16.
Additional adversarial checks: 24 passed, included in the 40; no exclusion.
CLI `--help`: exit 0. Contract preflight: 9 PASS, 0 FAIL (final re-run below).
Source line counts via len(text.splitlines()): kalshi_ws_capture.py 264 (down
from 284 pre-FIX-1b: the frame-value grammar moved out), kalshi_ws_frames.py 48
(new), test_kalshi_ws_capture.py 297 (one line changed, none added/removed),
test_kalshi_ws_capture_1b.py 114 (new). All four source files and this memo are ASCII.
The initial 34-test pass was followed by read-only review and regression fixes:
nonfinite raw fields, future duplicate keys, durable resync ordering, and standalone
trade reconnect handling. The 40-test run on the original file covers those fixes;
FIX 1b (AMENDMENTS 1-2, below) is the second round, covered by the 9 tests in the
_1b file plus one adapted assertion (`capture.book_seq`, was `capture.seq`) in the
original file after book/trade sequence state was split.
Self-check B1-B10/Q1-Q9: all 16 constructs retained; additive new opt-in module;
no threshold edits, moved artifact, pod work, scored comparison or deployment.
Q1/Q2/Q4/Q5/Q9 scoring requirements are not invoked by these byte constructs.
No counters, flags or production callers were changed. Protected-file hashes
below match the before-coding readings (8 / 8 must-not-move files).

## FIX 1b (AMENDMENTS 1-2)

Round 1 (codex build, 40 tests): Opus tier 2 ACCEPT WITH CORRECTIONS adopted;
sol REJECT (five blockers: four AMENDMENT 1 items not yet built, one new -- trades
held hostage by a book resync -- plus one correction). This round builds every
item exactly as amended, against base sha `d0c6f114e` (`git rev-parse --short HEAD`).

| Item | What changed | Test(s) |
| --- | --- | --- |
| A1(a) one gap, one count | Already correct in round 1 (gap record created once, inside the branch that opens it); re-verified, no code change needed | test_03_gap_resync |
| A1(b) backoff resets after >= 600s | `reconnect(now, elapsed=0.0)` gained `elapsed`; resets `self.backoff = 1` before computing the returned delay, matching capture_supervisor.py:165-166; `run()` now times the connection with `time.monotonic()` and passes `elapsed=` on every reconnect call | test_a1b_backoff_resets_after_long_connection, test_a1b_backoff_holds_progression_under_600s |
| A1(c) case 6 relabelled | Acceptance table row 6 now states library-level explicitly | test_06_protocol_ping (unchanged, relabelled in this memo only) |
| A1(d) writer OSError is not a connection error | `run()`'s `async for` loop now catches `OSError` from `capture.feed(frame)` specifically and re-raises `RuntimeError("capture_failed")`, which is outside the `except (OSError, websockets.WebSocketException)` connection-error catch and reaches `main()`'s handler unchanged | test_a1d_writer_failure_is_capture_failed_not_connection_error |
| A1(e) classify before generic malformed | `feed()` now classifies, before any exception can fire: `ack` (a `"subscribed"` frame, checked before `market_ticker` is read), `unsupported_frame` (a known ticker, unrecognized `type`, no gap opened), `out_of_order_seq` (seq strictly less than the last good seq -- distinct from `duplicate_frame`, an exact repeat), `one_sided_snapshot` (one of `yes`/`no` absent, checked before indexing `msg[key]`, never a KeyError) | test_a1e_subscribe_ack_counted_not_malformed, test_a1e_unsupported_frame_known_ticker_no_gap, test_a1e_out_of_order_seq_not_duplicate_frame, test_a1e_one_sided_snapshot_refused_with_reason |
| A1(f) credential expiry | Disclosed below (Owner preparation / NOT VERIFIED); no code change -- an owner-visible, live-connection concern. SUPERSEDED round-1 state: `auth_rejected` was not yet implemented or tested at FIX 1b time; AMENDMENT 3(c) (FIX 1c) classified it from `websockets.InvalidStatus`, and AMENDMENT 4(b) (FIX 1d, below) parameterises its regression over both 401 and 403. It has still never been exercised against a real venue response -- see NOT VERIFIED. | memo only |
| A2(a) trades not held hostage by a book resync | Book and trade sequence state are now two separate dicts (`book_seq`, `trade_seq`) per ticker; the `awaiting_snapshot` gate now only fires for `orderbook_delta`, never for `trade`; a trade succeeding while `ticker in self.gaps` never touches the book's gap/resync bookkeeping | test_a2a_trade_survives_book_awaiting_resync (case 16's reconnect -> unique trade -> snapshot ordering; trade_rows 1) |
| A2(c) memo | Case 6 relabelled (above); sequence scope (per ticker vs per subscription; whether trades share the book sequence) restated UNVERIFIED below; fixed-header expiry and the pending fresh-header path disclosed below; A9 rows and base sha regenerated from this tree (below) | memo only |

Sequence scope remains UNVERIFIED (unchanged from AMENDMENT 1(e)): this fix
isolates book and trade sequence *state* defensively regardless of the answer,
so it is correct whether the venue scopes `seq` per ticker, per subscription, or
shares one counter across trades and the book -- but which of those is real is
still not confirmed from venue documentation.

## A9 exact sources

Fixture paths below identify embedded bytes in the test source using a fragment name.
Resolution: not applicable (JSON/protocol bytes and Python/text sources).
Mutated construct inputs are deterministic transformations in the hashed test source;
no external fixture, real archive or measured dataset is opened.

Recomputed from this tree at FIX 1e time, base sha `ef7248901` (`git rev-parse --short HEAD`).
Two rows changed since FIX 1d: test_kalshi_ws_capture_1c.py (the AMENDMENT 5(a)
clock-isolation edit) and S442_spec.md (AMENDMENT 5 text landed on master since
FIX 1d); every other row is byte-identical to the FIX 1d table, reconfirmed above.

| Path | Bytes | SHA-256 |
| --- | --- | --- |
| scripts/platformkit/ingame/kalshi_ws_capture.py | 14918 | ab3e45e71576acb94acf80f356d8720d2604b1dd0a23e13561e91ca655980b35 |
| scripts/platformkit/ingame/kalshi_ws_frames.py | 2075 | a7fcc3ca42e83ac9ee193edc0fa9f1585710653119663cf55fff789e8b4ae6fd |
| tests/platformkit/ingame/test_kalshi_ws_capture.py | 13042 | 52ed1673d820a718bc58769f8adda72d47ac57c626021f6b53491adfa8827005 |
| tests/platformkit/ingame/test_kalshi_ws_capture_1b.py | 4980 | b81217303b7129b82af24ae0a094268c973896de87bda6345351aee4f76113cb |
| tests/platformkit/ingame/test_kalshi_ws_capture_1c.py | 4513 | 7c2ff07a2c272b528579dc4c01f38a010cdfc95d57d7efa0d24754b6bbde0cb1 |
| docs/evidence/tracking/specs/S442_spec.md | 15316 | 327481757cb32dfd44a3eca613bc8a7b9337c3d0db3e1b5047fc70c8d3762681 |
| scripts/stream_kalshi.py | 3571 | a003a49270b5e53b9a478c5a1312060ee1834c09c3f25fcf8d075caef4e2d021 |
| scripts/platformkit/execution/venue_time.py | 2029 | 651d80edc0ef0788ea543b2cf3e9f4ae8c1d5114e67211cf7fcd6047eade79f8 |
| scripts/platformkit/ingame/local_capture_metrics.py | 2915 | 34ecc86c519b8e55f2a7874b09b3c45721c27298f36f7473df44d2c17bb6d2e3 |
| scripts/platformkit/ingame/local_capture_runner_row.py | 6901 | 7a962ee8fc1d6dcb46941d1fef0903a4721d57b510b83dcfb8736c91c61570a1 |
| scripts/platformkit/ingame/local_capture_runner_trades.py | 5327 | 8da9256e99a11c6e11495c342459dac7faa0f284963710d10b0bf42a8d615cbc |
| scripts/platformkit/ingame/local_capture_writer.py | 7873 | a450f45e1eb8f9fe37202c488c85afef9e950f97d3c1b8f948b4128231b9279c |
| scripts/platformkit/ingame/local_capture_client.py | 6629 | 82417750843907dc8fc04308112fdc3198b285f67143b364fb5c3db70ffc5501 |
| scripts/platformkit/ingame/local_capture_time.py | 1426 | 157b5120c512291e7d9ae8388d1b4ed57e551323f044fa02d8c4b6bc6944b12c |
| scripts/platformkit/ingame/local_capture_runner.py | 17793 | c8e84178c93eeb6f3e44fa9575847c5234d0436389220014023967ff39f09452 |
| requirements-live-v2.txt | 242 | aab7322826cf0f31568d0bb20b321e9aac4813dd684dc92c77d94306ce073a3c |
| requirements-web.txt | 1662 | 5054aba618bb303980af83c353aa9ab24788f4ffedbda67b4bdf08de64efa58f |
| tests/platformkit/ingame/test_kalshi_ws_capture.py#snapshot | 107 | 141115a806a4647ab703e6f76f36c935adb9b5f8be75be73b3bcc2d807ee2fc6 |
| tests/platformkit/ingame/test_kalshi_ws_capture.py#delta | 100 | 03acceea17dad4081021935113b8e618d621e42bbab570aaee62092529d12c3f |
| tests/platformkit/ingame/test_kalshi_ws_capture.py#gap | 99 | b72f9e84c0feba4923b788fee3ea09e1e0f953f6d341119606f443fb0ad715c5 |
| tests/platformkit/ingame/test_kalshi_ws_capture.py#trade | 127 | a25b12da8a14657463d3898e5994933de640420c11ef5e05c0d3c9ddead53e62 |
| tests/platformkit/ingame/test_kalshi_ws_capture.py#decimal | 153 | 631888f9c3cf35b1e9dcb0c4cfba0d434e682fb8d664ecd52c340aa13a8d4c71 |
| tests/platformkit/ingame/test_kalshi_ws_capture.py#malformed | 8 | d356aa44394dfb9e6d62d1ee01fa0e67610ff5b42d93791e44c2731901c7df66 |
| tests/platformkit/ingame/test_kalshi_ws_capture.py#ping | 4 | ab989a7e52baaa17915cf63fdf5228b896c3bdc184dbbf817c7ba698d7290dd5 |
| tests/platformkit/ingame/test_kalshi_ws_capture.py#credentials | 103 | b84c1c0596fc5af0d387a330a74d37feee40862bffa0cfeb2dff0400f6f7ace1 |
| tests/platformkit/ingame/test_kalshi_ws_capture_1b.py#ACK | 73 | 2d91df913cb07d369053ea042ae2911d1d2f53788afb21358212b5378601e1b8 |
| tests/platformkit/ingame/test_kalshi_ws_capture_1b.py#UNSUPPORTED | 68 | 85a745438f2c0f614f10e1732cb4d4b7978b5009a6f4c9facbb4408b1aa5e3ba |
| tests/platformkit/ingame/test_kalshi_ws_capture_1b.py#ONE_SIDED | 84 | d0cc00ba8c510f0f21217f9444fe512ea823f74953d0994465e215e052f971e6 |

## Owner preparation

The owner supplies `--output-root` as a nonexistent sibling of ARCHIVE_ROOT,
`--credentials-env-var KALSHI_WS_CREDENTIALS_PATH`, `--channels`, `--confirm-channels`,
`--url` (secure socket URL), `--tickers` and `--sport`.
The named environment variable contains a file path only. That ASCII JSON file
contains exactly KALSHI-ACCESS-KEY, KALSHI-ACCESS-SIGNATURE and KALSHI-ACCESS-TIMESTAMP
header strings. Header values are never printed. The owner must generate valid,
fresh authentication headers externally; the file is re-read on every connection.
No signing library, implicit credential source, credential CLI literal or URL default
is introduced. This lane does not launch that command or open any socket.

## FIX 1c (AMENDMENT 3)

Round 2 (codex sol REJECT, five blockers) after FIX 1b. This round builds every
item exactly as amended, against base sha `c3830a16b` (`git rev-parse --short HEAD`).

| Item | What changed | Test(s) |
| --- | --- | --- |
| A3(a) one gap, one count, literally | kalshi_ws_capture.py `feed()`, the `sequence_gap` branch: the `self.metrics.drop("ws", "sequence_gap")` call moved inside `if ticker not in self.gaps:`, immediately before `self.missing(ticker, now)` -- previously it fired on every frame for which `seq != seq_state[ticker] + 1` still held, so a run of deltas after one gap over-counted (the verifier's probe measured `sequence_gap == 4` for snapshot seq 1 + deltas 4/5/6/7, wanting 1) | test_a3a_one_sequence_gap_across_four_deltas (new, tests/platformkit/ingame/test_kalshi_ws_capture_1c.py): snapshot seq 1, deltas 4/5/6/7 -> sequence_gap 1, awaiting_snapshot 4; test_03_gap_resync is unchanged and still covers exactly one delta |
| A3(b) connection duration starts at a successful handshake | kalshi_ws_capture.py `run()`: `connected_at` now starts `None` each loop iteration and is set only inside `async with websockets.connect(...) as socket:`, right after entry succeeds; the `elapsed` passed to `reconnect()` is `0.0` whenever `connected_at is None`, so the clock is never read for a failed handshake | test_a3b_failed_handshake_never_resets_backoff (new, _1c file): a stubbed connect that always raises OSError inside `__aenter__`, with injected `time.monotonic()` ticks 0.0 then 601.0 -- `reconnect()` receives `elapsed=0.0`, not 601.0 (the ticks are never consumed) |
| A3(c) auth_rejected classified | kalshi_ws_capture.py `run()`: a new `except websockets.InvalidStatus as exc:` sits before the existing `except (OSError, websockets.WebSocketException):` (InvalidStatus is itself a WebSocketException, so catch order matters); an HTTP 401/403 status counts `auth_rejected` and falls through to the same landed-backoff `reconnect()` call at the loop tail (no reconnect storm); a second consecutive rejection raises `capture_failed` and stops the run | test_a3c_auth_rejected_twice_stops_after_landed_backoff (new, _1c file): a transport-injected `websockets.InvalidStatus(Response(401, "Unauthorized", Headers()))` stub -- first rejection applies backoff (one `asyncio.sleep(1)`), second rejection exits 2 printing `capture_failed`; `auth_rejected == 2`, `connection_error == 0` |
| A3(d) A9 covers every fixture | tests/platformkit/ingame/test_kalshi_ws_capture_1b.py: `test_a9_identity_1b` now also asserts the ACK, UNSUPPORTED and ONE_SIDED fixture rows (path-fragment, byte-count, sha256) added to the A9 table above | test_a9_identity_1b (extended) |
| A3(e) the 300-line cap is per file | Clarification only, no code change: kalshi_ws_capture.py (282 lines) and kalshi_ws_frames.py (48 lines) are each independently <= 300; there is no combined-file limit across the two modules | n/a (memo text only) |

Reproduction (this round):
`python -m pytest tests/platformkit/ingame/test_kalshi_ws_capture.py -q -p no:cacheprovider` -> 40 passed
`python -m pytest tests/platformkit/ingame/test_kalshi_ws_capture_1b.py -q -p no:cacheprovider` -> 9 passed
`python -m pytest tests/platformkit/ingame/test_kalshi_ws_capture_1c.py -q -p no:cacheprovider` -> 4 passed
53 passed total across three files, run one file at a time (exit 0 each). Acceptance
constructs unchanged at 16 / 16 -- FIX 1c adds regression coverage for AMENDMENT 3,
not new constructs.
Source line counts via len(text.splitlines()): kalshi_ws_capture.py 282 (up from 264:
the `connected_at`/`InvalidStatus` restructuring in `run()` plus the one-gap-one-count
fix in `feed()`), kalshi_ws_frames.py 48 (unchanged), test_kalshi_ws_capture.py 297
(unchanged), test_kalshi_ws_capture_1b.py 117 (three assertion lines added to
`test_a9_identity_1b`), test_kalshi_ws_capture_1c.py 85 (new). All five source files
and this memo are ASCII.
The 8 must-not-move files (local_capture_runner_row.py, local_capture_runner_trades.py,
local_capture_writer.py, local_capture_client.py, local_capture_time.py,
local_capture_runner.py, requirements-live-v2.txt, requirements-web.txt) are
byte-identical to master: `git diff --stat master -- <the 8 paths>` printed nothing,
exit 0. `git status --short` in the worktree shows only the six untracked candidate
paths (the module, the frame-grammar helper, the three test files, this memo).
Self-check B1-B10/Q1-Q9: all 16 constructs retained; additive opt-in module unchanged
in shape; no threshold edit, moved artifact, pod work, scored comparison, deployment,
or network call. No counters, flags or production callers were changed.

## FIX 1d (AMENDMENT 4)

Round 3 (codex sol REJECT, one blocker, two corrections) after FIX 1c: the
implementation of AMENDMENT 3 was confirmed by the verifier's own probes; only
the _1c test file and this memo needed correction. This round builds every item
exactly as amended, against base sha `bb393cbc3` (`git rev-parse --short HEAD`).

| Item | What changed | Test(s) |
| --- | --- | --- |
| A4(a) the run-level backoff regression is real | `test_a3b_failed_handshake_never_resets_backoff` (_1c file) no longer replaces `Capture.reconnect` with a stub that raises immediately; it wraps the real, unbound `reconnect()` to record its `elapsed` argument and then calls straight through, so `backoff` actually transitions inside the run loop. The captured `Capture` instance's `backoff` is initialised to 8 (not the constructor default of 1) via the same `Capture`-construction spy the other run-level tests already use. `asyncio.sleep` is intercepted to record the delay passed to it and raise the `_Stop` sentinel, ending the `while True` loop after exactly one reconnect | test_a3b_failed_handshake_never_resets_backoff (rewritten): asserts `seen_elapsed == [0.0]` (the failed handshake never reads the injected 601s clock -- AMENDMENT 3(b) unchanged), `delays == [8]` (the pre-set backoff, unreset because elapsed < 600), and `instances[0].backoff == 16` (the real doubling ran) |
| A4(b) the auth regression covers both statuses | `test_a3c_auth_rejected_twice_stops_after_landed_backoff` (_1c file) is now `@pytest.mark.parametrize("status, reason", [(401, "Unauthorized"), (403, "Forbidden")])`; the transport-injected `websockets.InvalidStatus(Response(status, reason, Headers()))` stub is unchanged in shape, only the status is now driven both ways | test_a3c_auth_rejected_twice_stops_after_landed_backoff[401-Unauthorized] and [403-Forbidden]: each asserts `auth_rejected == 2`, `connection_error == 0`, `delays == [1]`, exit 2 printing `capture_failed` |
| A4(c) memo | The FIX 1b table's A1(f) row's stale "not implemented or tested" sentence about `auth_rejected` is labelled SUPERSEDED round-1 state (AMENDMENT 3(c)/4(b) superseded it); this "## FIX 1d (AMENDMENT 4)" section added above NOT VERIFIED; every A9 row recomputed from this tree, base sha `bb393cbc3` | memo only |

Reproduction (this round):
`python -m pytest tests/platformkit/ingame/test_kalshi_ws_capture.py -q -p no:cacheprovider` -> 40 passed
`python -m pytest tests/platformkit/ingame/test_kalshi_ws_capture_1b.py -q -p no:cacheprovider` -> 9 passed
`python -m pytest tests/platformkit/ingame/test_kalshi_ws_capture_1c.py -q -p no:cacheprovider` -> 5 passed
40 + 9 + 5 passed total across three files, run one file at a time (exit 0 each). Acceptance
constructs unchanged at 16 / 16 -- FIX 1d corrects AMENDMENT 3's regression coverage,
it adds no new construct and no code change to kalshi_ws_capture.py or kalshi_ws_frames.py.
Source line counts via len(text.splitlines()): kalshi_ws_capture.py 282 (unchanged),
kalshi_ws_frames.py 48 (unchanged), test_kalshi_ws_capture.py 297 (unchanged),
test_kalshi_ws_capture_1b.py 117 (unchanged), test_kalshi_ws_capture_1c.py 110 (up
from 85: the real-reconnect wrapper, the pre-set-backoff capture spy, and the
401/403 parametrization). All five source files and this memo are ASCII.
The 8 must-not-move files (local_capture_runner_row.py, local_capture_runner_trades.py,
local_capture_writer.py, local_capture_client.py, local_capture_time.py,
local_capture_runner.py, requirements-live-v2.txt, requirements-web.txt) are
byte-identical to master: `git diff --stat master -- <the 8 paths>` printed nothing,
exit 0. `git status --short` in the worktree shows only the six untracked candidate
paths (the module, the frame-grammar helper, the three test files, this memo).
Self-check B1-B10/Q1-Q9: all 16 constructs retained; additive opt-in module unchanged
in shape; no threshold edit, moved artifact, pod work, scored comparison, deployment,
or network call. No counters, flags or production callers were changed. No live
socket was opened at any point in this round; every regression above runs against
a stubbed `websockets.connect` and an intercepted `asyncio.sleep` / `time.monotonic`.

## FIX 1e (AMENDMENT 5)

Round 4 (codex sol REJECT, one blocker: test isolation) after FIX 1d: every
implementation item was confirmed by independent probes; only the _1c test
file and this memo needed correction. This round builds the one item exactly
as amended, against base sha `ef7248901` (`git rev-parse --short HEAD`).

| Item | What changed | Test(s) |
| --- | --- | --- |
| A5(a) the backoff regression must fail on the pre-fix code | `test_a3b_failed_handshake_never_resets_backoff` (_1c file) no longer does `monkeypatch.setattr(ws.time, "monotonic", ...)` (that patches the shared stdlib `time` module object, which asyncio's own scheduling also reads from, so asyncio consumed the staged 0.0/601.0 ticks first and the pre-fix timer placement passed the test by accident -- round 4's blocker). It now does `monkeypatch.setattr(ws, "time", types.SimpleNamespace(monotonic=<staged>, monotonic_ns=time.monotonic_ns))`, rebinding the module-level name `time` inside `kalshi_ws_capture`'s own namespace so only code in that module reads the staged clock; asyncio's internal `time.monotonic()` calls resolve through its own module's globals, untouched | test_a3b_failed_handshake_never_resets_backoff (isolation fix only; assertions unchanged: `seen_elapsed == [0.0]`, `delays == [8]`, `instances[0].backoff == 16`) |
| A5 mutant-check proof | Not a code change: a scratch copy of kalshi_ws_capture.py was built under the session scratchpad (never in this worktree) with `connected_at` moved back to the pre-fix placement (set unconditionally before the handshake attempt, inside the `while True:` body, rather than only after `websockets.connect(...)` enters successfully) and loaded as a fresh module via `importlib.util.spec_from_file_location` (never overwriting the real module in `sys.modules`). The fixed test's construct (same fake failing handshake, same staged `ws.time` namespace, same `Capture`/`reconnect`/`asyncio.sleep` spies) was replayed against that mutant module directly (no pytest, no monkeypatch fixture -- a standalone script). Result: `seen_elapsed=[601.0]`, `delays=[1]`, `backoff_after=2` -- the fixed-code assertions (`seen_elapsed == [0.0]`, `delays == [8]`, `backoff_after == 16`) raise `AssertionError` against the mutant, i.e. the corrected test (run against the real, fixed module in this worktree) FAILS on the pre-fix code and PASSES on the fixed code, proving the regression actually bites | scratch script only, not part of the test suite; module in this worktree never touched |

Reproduction (this round):
`python -m pytest tests/platformkit/ingame/test_kalshi_ws_capture.py -q -p no:cacheprovider` -> 40 passed
`python -m pytest tests/platformkit/ingame/test_kalshi_ws_capture_1b.py -q -p no:cacheprovider` -> 9 passed
`python -m pytest tests/platformkit/ingame/test_kalshi_ws_capture_1c.py -q -p no:cacheprovider` -> 5 passed
40 + 9 + 5 passed total across three files, run one file at a time (exit 0 each). Acceptance
constructs unchanged at 16 / 16 -- FIX 1e corrects test isolation only; no code change
to kalshi_ws_capture.py or kalshi_ws_frames.py, no new construct.
Source line counts via len(text.splitlines()): kalshi_ws_capture.py 282 (unchanged,
byte-identical to the FIX 1d row -- sha256 reconfirmed above), kalshi_ws_frames.py 48
(unchanged), test_kalshi_ws_capture.py 297 (unchanged), test_kalshi_ws_capture_1b.py
117 (unchanged), test_kalshi_ws_capture_1c.py 118 (up from 110: the `time`/`types`
imports and the module-attribute-rebind construct, plus its explanatory comment).
All five source files and this memo are ASCII.
The 8 must-not-move files (local_capture_runner_row.py, local_capture_runner_trades.py,
local_capture_writer.py, local_capture_client.py, local_capture_time.py,
local_capture_runner.py, requirements-live-v2.txt, requirements-web.txt) are
byte-identical to master: `git diff --stat master -- <the 8 paths>` printed nothing,
exit 0. `git status --short` in the worktree shows only the six untracked candidate
paths (the module, the frame-grammar helper, the three test files, this memo).
Self-check B1-B10/Q1-Q9: all 16 constructs retained; additive opt-in module unchanged
in shape; no threshold edit, moved artifact, pod work, scored comparison, deployment,
or network call. No counters, flags or production callers were changed. No live
socket was opened anywhere in this round, including the mutant-check script: its
fake handshake raises OSError inside `__aenter__` before any connection object exists.

## NOT VERIFIED

- The asynchronous connection loop and header refresh with an injected transport;
  protocol ping/pong is exercised with the installed Sans-I/O implementation only.
- Any real frame or real sequence behavior, channel validity, subscription response,
  sequence scope between channels, or whether a socket ever actually connects.
- Venue authentication signing, validity or expiry of externally prepared headers.
  Fixed signature/timestamp headers go stale across reconnects; the owner-provided
  path must be refreshed with fresh headers per connection (a later, real-run row).
  `auth_rejected` is implemented and classified from `websockets.InvalidStatus`
  (AMENDMENT 3(c), transport-injected test only) but has NEVER been exercised
  against a real venue response: this PREPARE-ONLY lane never produces one, so
  whether the venue actually answers a stale/rejected handshake with HTTP 401/403
  (rather than some other status or a bare connection drop) is unconfirmed.
- Whether `seq` is scoped per ticker or per subscription, and whether trades share
  the book's sequence counter or run their own: book and trade sequence state are
  isolated in code defensively (AMENDMENT 2(a)), which is correct either way, but
  which one the venue actually does is still unconfirmed from its own documentation.
- Real capture coverage, reconstructed-book agreement with any real REST receipt,
  or a paired-night census accounting for real missing intervals.
- Process-restart trade deduplication; the constructed guarantee spans reconnects
  of one Capture instance. The CLI requires a new root on each process launch.
- Concurrent-process root races, host crashes, disk-full behavior or real clock jumps.
- Adoption: pending an owner-visible launch after independent verification.
