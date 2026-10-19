# S694 cloud result -- seq-checked socket book adapter (2026-09-30)

Row: S694 (AUTOMATED_PAPER_DESK_ARCHITECTURE_2026-09-30.md section 2; one-off override section 3a). PAPER ONLY.
Branch: `cloud/S694-2026-09-30` (from trunk bb34a09c). Routine: desk-improve one-off, Claude cloud (Ubuntu, Python 3.11).
Pre-build check: `git ls-remote --heads origin 'cloud/S694*'` was empty before the build.

## Verdicts

| Tier | Who | Round 0 (4d753d8c) | Re-verify (fix round 1, d16e66ee) |
|---|---|---|---|
| Pre-build critic | independent Opus sub-agent | REVISE, 12 items -> spec AMENDMENT 1 (all folded) | - |
| CONTRACT (A/B/Q + spec + AMENDMENT 1) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS | ACCEPT WITH CORRECTIONS (remaining: this memo, now written; original edge-case test still merged, uncounted) |
| ADVERSARIAL (probes + mutants; drops, duplicates, reorders seq) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS | ACCEPT WITH CORRECTIONS (0 surviving non-equivalent mutants; 300 probe runs, 101,422 frames, 0 invariant counterexamples; remaining: this memo) |

Codex is not available in the cloud box: every tier was a separate Opus sub-agent (Agent tool), none of which wrote the code.

## What was built (new files only)

- `scripts/platformkit/execution/book_stream.py` (pure state machine, 268 lines) and
  `scripts/platformkit/execution/book_stream_frames.py` (pure frame parsing, 83 lines; uses kalshi_ws_frames read-only).
- `tests/platformkit/execution/test_book_stream.py` (7 tests; fails on trunk: module absent, collection error).
- `docs/evidence/harness/S694_spec_2026-09-30.md` (spec + AMENDMENT 1).
- Unchanged: `kalshi_ws_capture.py`, `kalshi_ws_frames.py` (`git diff trunk --` empty), every existing file.

Behaviour: per ticker, book seq separate from trade seq (as the S442 capture). A delta applies only on a VALID book at
seq == last + 1; a higher seq -> INVALID + BOOK_GAP carrying a `book_gap` row; while INVALID every delta is dropped but
advances the highest seq seen, and only a snapshot above it restores VALID (BOOK_RESYNC + `book_resync` row). This is
stricter than the capture (which compares to the last good seq). Duplicate and stale frames leave the ladders
unchanged. Malformed book frames (bad seq, price, size, zero delta, duplicate level, one-sided snapshot) and negative
levels invalidate. An in-sequence snapshot is compared to the rebuilt book; a mismatch emits BOOK_GAP(snapshot_mismatch).
on_reconnect clears seq state and requires a fresh snapshot. Two silence clocks: the book clock (accepted book frames
only) and the connection clock (any frame or heartbeat); BOOK_SILENT fires at exactly N; BOOK_RESUMED only on an
accepted book frame. `quote_gate(ticker, now_us)` is the book-state input for S702 and computes both ages itself.

Event contract (DEFINED HERE: S691 has no branch yet, `git ls-remote --heads origin 'cloud/S691*'` empty): dict with
kind (book | state | print), type, ticker, recv_us (int), seq, validity (VALID | INVALID), freshness (FRESH | SILENT);
prices and sizes as ASCII decimal strings; per call order BOOK_RESUMED, BOOK_GAP, BOOK_RESYNC, BOOK_SNAPSHOT | BOOK_UPDATE.
S691 and S702 should adopt it or say what they change.

## Tests (exact commands, one file per process)

| Command | Result |
|---|---|
| `python3 tools/desk_bin/run_files.py . tests/platformkit/execution/test_book_stream.py` | 7 passed |
| `python3 -m pytest tests/platformkit/execution/test_book_stream.py -q -s` | 7 passed (counts below) |
| `python3 tools/desk_bin/run_files.py . tests/platformkit/ingame/test_kalshi_ws_capture.py` | 40 passed |
| `python3 tools/desk_bin/run_files.py . tests/platformkit/ingame/test_kalshi_ws_capture_1b.py` | 9 passed |
| `python3 tools/desk_bin/run_files.py . tests/platformkit/ingame/test_kalshi_ws_capture_1c.py` | 5 passed |

The capture files need `websockets`, which trunk's setup.sh does not install (S660's branch pins 16.0); it was
pip-installed in the box to run them.

Printed counts (CONSTRUCT, every case enumerated):
- (a) injected single drop at every delta position with a successor: BOOK_GAP on the successor's own call 11/11;
  every adjacent swap 11/11; every duplicate position 13/13.
- (e) ladders identical after a stale or duplicate frame 24/24.
- (b) stub S702 gate, one quote intent after every frame: invalid-window refusals 7/7; silent-window refusals 5/5;
  positive control, VALID and fresh admitted 8/8 (including right after a resync and a resume); wrong 0.
- (c) 5 seeded shards (cents and dollars shapes): 30 embedded snapshots, 0 mismatches against the independent
  generator book (read by the test, not the module's flag); 52 level removals; min 5 deltas between snapshots;
  mutated delta detected 5/5.
- (d) BOOK_SILENT at N exactly and not at N - 1 us, on both clocks; trades and heartbeats do not reset the book clock.
- fix round 1: 20 enumerated cases.

Verifier reproductions: CONTRACT tier recomputed (a)-(e) with its own 21-frame stream and 5 shards (seeds 10-14):
drops 19/19, swaps 19/19, dups 21/21, 35 snapshots 0 mismatches, mutants 5/5. ADVERSARIAL tier: 1200 probe runs
(about 406k frames, 863k gate checks, 3 tickers): five invariants held with 0 counterexamples; 29 mutants, 22 red
in round 0 (M2 equivalent); fix round 1 turned all 8 survivors red (M15, M18, M21, M21b, M22, M25, M26, M29) and 5
re-run former reds stay red. Stricter probe check "book at the highest seq received": 52 hits, all the pre-snapshot
delta pattern (first NEW GAP below), 0 after excluding it.

Process note (contract tier): one of its first re-verify runs failed transiently while the adversarial tier was
applying mutants in the same checkout; all later runs pass and the file equals commit d16e66ee. Land from the commit.
Final verdict: ACCEPT WITH CORRECTIONS on both tiers after the single allowed fix round; no REJECT.

## NEW GAP lines from the verifiers (not fixed here; for the orchestrator)

- A delta received before the first (or post-reconnect) snapshot with a seq above that snapshot's seq is dropped
  unrecorded, so the older snapshot is admitted until the next delta shows the gap (spec-sanctioned by AMENDMENT 1(3)/(5);
  the capture opens a missing interval there).
- After on_reconnect a late pre-reconnect snapshot is accepted: nothing ties a frame to the new subscription (sid).
- The connection clock is global: a frame for an unknown ticker keeps every ticker's connection clock fresh.
- Fractional sizes: 0.5 accepted from JSON (Decimal) but refused as a Python float in a dict frame; needs a policy.
- The original edge-case test is one merged test (the fix-round test prints its own case count).

## NOT VERIFIED

- Any live socket message (S661): frame shapes come from the S442 capture's parser and its test fixtures only.
- Venue seq semantics: the venue may number seq per subscription (sid), not per ticker; this module follows the capture.
- Whether the venue omits an empty side in a snapshot (treated as malformed here, dropped by the capture).
- The ticker-channel field names (passed through, never used to validate the book).
- S691 event core and S702 risk gate wiring (neither exists); S668 shared enum (AD-1) not landed.
- Windows re-test on the recorder box; any recorded night or capture archive (no data/ in the clone).

PORTABLE: yes (pure module + fixtures; Ubuntu Python 3.11).
