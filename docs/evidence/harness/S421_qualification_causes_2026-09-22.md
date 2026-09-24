# S421 qualification causes

NOT VALIDATED. The orchestrator's build-2, fix-1b, fix-1c and fix-1d runs reproduced 146 / 529 / 575.
The fix-1c, fix-1d and fix-1e artifacts are hashed below and committed at landing. The FIX 1e AFTER-3 real re-run reproduced every per-game count with repo-relative paths (recorded below).
Machine: local, the S421 candidate worktree (<worktree>). No real archive, network, pod or production ledger was used by the fix lanes.
Authority: docs/evidence/tracking/specs/S421_spec.md including AMENDMENTS 1-6; VERIFIER_CONTRACT.md sections B and Q.
Historical sources: S390 AMENDMENT 7 as corrected by AMENDMENT 9; S410 AMENDMENT 5.

## Binding interpretation

The landed decision boolean is `converted and touch and not row.get("_refusal")`.
S421 AMENDMENT 1 corrects the original probe: to_quote_book RETURNS refusal dictionaries as well as raising.
The three served tickers' adapter refusal counts are all `inconsistent_touch`; accepted rows pass touch.
The orderbook and row prices agree; raw_market prices disagree. Source fetch ordering is not inferred.
Frozen bars are imported: COVERAGE_PERCENT 90, MIN_DECISIONS 480, BOOK_MEDIAN_S 45, BOOK_P95_S 90,
BOOK_MAX_S 120 and STATE_GAP_S 30. S421 changes no landed module or frozen bar.
Four exclusive per-decision causes sum to not_accepted: pre_adapter_refused, adapter_refused,
touch_unavailable and downstream_refusal. Precedence follows that order, including overlapping refusals.
A 10-digit timestamp fraction is a landed global unreadable-books fatal, separately represented:
native_rows drops it; load_native marks every game; gate_adapter_refused is max(not_accepted, fatal).
One cents pair unit is one disagreeing source pair on one side. A side whose raw pair disagrees,
whether or not _touch reached it, contributes six pairs when the two raw fields agree against three sources.
A row may yield 12 pairs / 2 sides, explaining TORBAL's 165 sides versus 146 refused rows.
The side distribution counts each side once at its widest pair, with plain integer-text cents keys.

## FIX 1b and FIX 1c summary

FIX 1b removed unbounded row details, retained at most three bounded examples per reason, and added
source-pair/cents totals. Its initial 10,000-row construct failed `assert 17213509 < 1000000`;
the bounded artifact regression passed after that fix. These are historical construct records.
FIX 1c retained refused books as landed replay does, counted duplicate identities, added the fourth cause,
plain cents keys and side-instance counts, and confined raw examples to undecodable rows.
Disagreement-analysis failures get their own counter; SQLite spools use temporary scratch directories.
Historical parity constructs before/after: http500 0/1 vs landed 1; size_nan 0/1 vs landed 1;
tied nonidentical 0/2 vs landed 2; identical tie 0/1 vs landed 1. The 10-digit case is global fatal, not a row.
Historical FIX 1c validation: report 61, stream 10, runtime 4, landed 13 passed; --help exit 0.
The former reserved_input_field and refused-state divergences are superseded by FIX 1d below.

### BEFORE: orchestrator build-2 real run (verbatim S421 AMENDMENT 2)

```text
--books-root data/cache/ingame_capture_view_v2/kalshi --state-root data/cache/ingame_capture_view_v2/state --schedule
docs/evidence/forward/schedules/2026-09-22_maker_forward_full_selection.json --date 2026-09-22 --as-of 2026-09-23T06:00:00Z;
wall 16:19:58Z-16:21:33Z; peak working set 2,294 MB measured by the orchestrator's watch). THE COUNTS REPRODUCE AMENDMENT 1
EXACTLY: TORBAL causes adapter_refused 146 / touch_unavailable 0 / downstream_refusal 0, adapter_reasons inconsistent_touch
146; MILPHI 529 / 0 / 0 (inconsistent_touch 529); MIACHC 575 / 0 / 0 (inconsistent_touch 575); STLPIT, CLEBOS, CINATL 0 / 0 / 0
with no book rows (the unserved capacity subset); TORBAL rows 660, qualified_decisions 0, state_profile never_live true,
longest_without_live_s 3600, statuses pre count 546 (first 2026-09-22T16:58:34.287948Z, last 2026-09-23T02:09:48.967841Z,
timestamp_field response_end_utc; the 546 exceeds AMENDMENT 1's 417 because the report also reads the 2026-09-23 shard's rows
before as_of, which is correct for the window); diagnostics future_books 4357, future_state 425, LINKAGE_INVALID 1,
conflicting_state_linkage 1, state_key_conflicted 1, missing_directional_team_evidence 30, state_rows_missing_start 0.
DEFECT, MEASURED: the artifact is 283,940,291 bytes because every game carries a "details" list with the VERBATIM RAW TEXT of
every book row, accepted rows included -- a counts-only report that re-publishes the whole shard, and the reason the peak
working set reached 2.3 GB.
```

Historical cents distributions, quoted from
`docs/evidence/harness/S421_real_shard_probe_2026-09-23.md` item 4b:
TORBAL {1: 165}; MILPHI {1: 423, 2: 293, 3: 141, 4: 64, 5: 50,
6: 32, 7: 1, 8: 1, 9: 1, 17: 4, 18: 6, 19: 22, 20: 2};
MIACHC {1: 563, 2: 331, 3: 129, 4: 60}.
These are failing-side instances (165 / 1040 / 1083), distinct from the
report's all-source-pair denominator. They are attributed BEFORE evidence,
not a result measured by this construct-only fix lane.

### AFTER: orchestrator fix-1b real run (verbatim facts; artifact read on disk)

Artifact: `s421_real_2026-09-22_fix1b.json`, 12,177 bytes, in the orchestrator's session scratchpad. Wall
16:44:30Z-16:46:04Z; peak working set 617 MB (the orchestrator's watch). The exact command line was not found on
disk. It is reconstructed from the artifact's own `inputs` list, and the schedule path is assumed to be the BEFORE
one, since the artifact does not record it:

```text
python -m scripts.platformkit.ops.qualification_cause_report --books-root data/cache/ingame_books_local/kalshi
--state-root data/cache/ingame_state_local_v2/state --schedule docs/evidence/forward/schedules/2026-09-22_maker_forward_full_selection.json
--date 2026-09-22 --as-of 2026-09-23T06:00:00Z --out <orchestrator scratchpad>/s421_real_2026-09-22_fix1b.json
inputs: books mlb/2026-09-22.jsonl 359982871 bytes, mlb/2026-09-23.jsonl 85728660 bytes;
        state mlb/2026-09-22.jsonl 8369460 bytes, mlb/2026-09-23.jsonl 8950143 bytes
TORBAL rows 660 not_accepted 146 adapter_refused 146 touch_unavailable 0 downstream_refusal 0 (inconsistent_touch 146) qualified 0 never_live true
MILPHI rows 658 not_accepted 529 adapter_refused 529 touch_unavailable 0 downstream_refusal 0 (inconsistent_touch 529) qualified 117
MIACHC rows 690 not_accepted 575 adapter_refused 575 touch_unavailable 0 downstream_refusal 0 (inconsistent_touch 575) qualified 103
STLPIT rows 4 not_accepted 0 qualified 2; CLEBOS rows 4 not_accepted 0 qualified 1; CINATL rows 4 not_accepted 0 qualified 4
diagnostics LINKAGE_INVALID 1, conflicting_state_linkage 1, future_books 7148, future_state 813,
missing_directional_team_evidence 30, state_key_conflicted 1, state_rows_missing_start 0
```

Cents-by-pair distributions (`disagreement_pairs_by_cents`, verbatim artifact keys):
TORBAL {"1": 990}; MILPHI {"1": 2538, "17": 24, "18": 36, "19": 132, "2": 1758, "2E+1": 12, "3": 846, "4": 384,
"5": 300, "6": 192, "7": 6, "8": 6, "9": 6}; MIACHC {"1": 3378, "2": 1986, "3": 774, "4": 360}.
With integer keys in order: TORBAL {1: 990}; MILPHI {1: 2538, 2: 1758, 3: 846, 4: 384, 5: 300, 6: 192, 7: 6, 8: 6,
9: 6, 17: 24, 18: 36, 19: 132, 20: 12}; MIACHC {1: 3378, 2: 1986, 3: 774, 4: 360}.
Every bucket is 6 times the probe's side-instance count (165 x 6 = 990; 423 x 6 = 2538; 22 x 6 = 132; 563 x 6 = 3378).
The artifact's per-side split gives the side counts: TORBAL yes 112 + no 53 = 165.

Reconciliation with BEFORE: the BEFORE text says the unserved three had "no book rows". That wording is wrong. A
read-only regex over the build-2 artifact (283,940,291 bytes) finds `"rows":4` with `"not_accepted":0` for each
of STLPIT / CLEBOS / CINATL, with qualified_decisions 2 / 1 / 4, the same as fix 1b. They had four in-window book
decisions each and none refused. future_books / future_state differ (4357 / 425 in BEFORE vs 7148 / 813 in fix 1b)
because the two runs read different capture roots (`ingame_capture_view_v2` vs `ingame_books_local` /
`ingame_state_local_v2`). The per-game cause counts are identical.

### AFTER: durable fix-1c artifact

The exact read-only source was
<orchestrator scratchpad>/s421_real_2026-09-22_fix1c.json.
Copied bytes: docs/evidence/forward/qualification_causes/2026-09-22_fix1c.json, 11946 bytes (JSON).
Source and copy SHA-256: 7e595b1b0b73196eaac04b547de3929c1a9586fa62c9717eb01478ef5f82ee18.
No archive was opened to copy or inspect this report artifact. Its four input records give full paths and byte sizes.
Reconstructed invocation, not an exact execution log; roots are from artifact inputs and schedule is assumed:
```text
python -m scripts.platformkit.ops.qualification_cause_report --books-root data/cache/ingame_books_local/kalshi
--state-root data/cache/ingame_state_local_v2/state --schedule docs/evidence/forward/schedules/2026-09-22_maker_forward_full_selection.json
--date 2026-09-22 --as-of 2026-09-23T06:00:00Z --out <orchestrator scratchpad>/s421_real_2026-09-22_fix1c.json
```
Exact command: UNKNOWN; wall bounds: UNKNOWN (prior memo 17:2xZ); peak working set: UNKNOWN.
The artifact contains no timing or command fields. Counts below were checked against the copied JSON.
Its 2026-09-23 input shards grew relative to FIX 1b (books 95147699 bytes, state 9359482 bytes);
2026-09-22 books/state remain 359982871 / 8369460 bytes. Equal as_of does not imply equal file bytes.

Orchestrator real re-run after FIX 1c (2026-09-23 17:2xZ, from the h75 candidate; same --as-of; input sizes recorded in the durable artifact; AMENDMENT 3 ruling (h)):
  artifact 11946 bytes; cause_precedence ["pre_adapter_refused", "adapter_refused", "touch_unavailable", "downstream_refusal"]; frozen_bars {"BOOK_MAX_S": 120, "BOOK_MEDIAN_S": 45, "BOOK_P95_S": 90, "COVERAGE_PERCENT": 90, "MIN_DECISIONS": 480, "STATE_GAP_S": 30}
  diagnostics {"LINKAGE_INVALID": 1, "conflicting_state_linkage": 1, "future_books": 12361, "future_state": 1380, "inconsistent_touch": 5121, "missing_directional_team_evidence": 30, "one_sided_book": 4857, "price_out_of_range": 4243, "state_key_conflicted": 1, "state_rows_missing_start": 0}
  KXMLBGAME-26SEP221835TORBAL: rows 660 not_accepted 146 causes {"adapter_refused": 146, "downstream_refusal": 0, "pre_adapter_refused": 0, "touch_unavailable": 0} adapter_reasons {"inconsistent_touch": 146} qualified_decisions 0 never_live True statuses {"pre": 546}
    disagreement_pairs_by_cents {"1": 990}; disagreement_sides_by_max_cents {"1": 165}
  KXMLBGAME-26SEP221840MILPHI: rows 658 not_accepted 529 causes {"adapter_refused": 529, "downstream_refusal": 0, "pre_adapter_refused": 0, "touch_unavailable": 0} adapter_reasons {"inconsistent_touch": 529} qualified_decisions 117 never_live False statuses {"final": 1, "live": 1030, "pre": 316}
    disagreement_pairs_by_cents {"1": 2538, "17": 24, "18": 36, "19": 132, "2": 1758, "20": 12, "3": 846, "4": 384, "5": 300, "6": 192, "7": 6, "8": 6, "9": 6}; disagreement_sides_by_max_cents {"1": 423, "17": 4, "18": 6, "19": 22, "2": 293, "20": 2, "3": 141, "4": 64, "5": 50, "6": 32, "7": 1, "8": 1, "9": 1}
  KXMLBGAME-26SEP221840STLPIT: rows 4 not_accepted 0 causes {"adapter_refused": 0, "downstream_refusal": 0, "pre_adapter_refused": 0, "touch_unavailable": 0} adapter_reasons {} qualified_decisions 2 never_live False statuses {"final": 1, "live": 1040, "pre": 310}
    disagreement_pairs_by_cents {}; disagreement_sides_by_max_cents {}
  KXMLBGAME-26SEP221845CLEBOS: rows 4 not_accepted 0 causes {"adapter_refused": 0, "downstream_refusal": 0, "pre_adapter_refused": 0, "touch_unavailable": 0} adapter_reasons {} qualified_decisions 1 never_live False statuses {"final": 1, "live": 1206, "pre": 314}
    disagreement_pairs_by_cents {}; disagreement_sides_by_max_cents {}
  KXMLBGAME-26SEP221915CINATL: rows 4 not_accepted 0 causes {"adapter_refused": 0, "downstream_refusal": 0, "pre_adapter_refused": 0, "touch_unavailable": 0} adapter_reasons {} qualified_decisions 4 never_live False statuses {"final": 1, "live": 1011, "pre": 352}
    disagreement_pairs_by_cents {}; disagreement_sides_by_max_cents {}
  KXMLBGAME-26SEP221940MIACHC: rows 690 not_accepted 575 causes {"adapter_refused": 575, "downstream_refusal": 0, "pre_adapter_refused": 0, "touch_unavailable": 0} adapter_reasons {"inconsistent_touch": 575} qualified_decisions 103 never_live False statuses {"live": 1020, "pre": 371}
    disagreement_pairs_by_cents {"1": 3378, "2": 1986, "3": 774, "4": 360}; disagreement_sides_by_max_cents {"1": 563, "2": 331, "3": 129, "4": 60}
  READING: the three in-window counts (146 / 529 / 575) reproduce for the third time, now under the FOUR-cause artifact with pre_adapter_refused 0 on this day and the side-instance counts equal to the probe record (TORBAL 165 sides at 1 cent; MILPHI 423 at 1 cent, 22 at 19 cents; MIACHC 563 at 1 cent).

## FIX 1d

Binding findings: tier 1 BLOCKING 1-4 and tier 2 CORRECTIONS 1-2, S421 AMENDMENT 4.
1. State parity (BLOCKING 1 / CORRECTION 1): retain all readable linkable states and preserve linkage/native
   _refusal. Landed observe() rejects malformed state/status schema itself, without an injected schema refusal.
   The regression compares qualified_decisions as well as ADAPTER_REFUSED for malformed state,
   http 500, duplicate state, state="x" and capture_sequence -1 constructs.
   BEFORE: six refused-state faults in two orders gave 12 failures: `AssertionError: ('qualified_decisions', 2, 1)`.
   AFTER: all state parity regressions passed in the landed file's 28 functional passes.
2. Captured private-looking fields (BLOCKING 2): preserve captured _raw / _s421* keys exactly.
   Move report metadata to SQLite sidecar columns; do not refuse, inject or strip captured fields.
   BEFORE: _raw / _s421 / _s421_cause each failed `AssertionError: ('qualified_decisions', 1, 2)`.
   The landed file reproduced `15 failed, 13 passed` across state and captured-field cases.
   AFTER: all captured-field parity regressions passed in those 28 functional passes.
3. Tied-group streaming (BLOCKING 3): SQL deduplicates and counts identities; yield one grouped payload at a time.
   A 10,000-row tie construct pins the bound. BEFORE: `1 failed, 10 passed`,
   `AssertionError: tied_rows_python_peak_bytes=[592832, 5781985]`. AFTER: the stream file passed 23 tests, including the 10,000-row bound and captured-field tie identities.
4. Memo (BLOCKING 4 / CORRECTION 2): BEFORE reproduction was
   `FAIL memo bytes=33363 lines=450 cap=300`; line 416 declared `29,936 bytes, 433 lines`.
   Line 4 called fix-1c outstanding while line 418 recorded it; line 437 repeated the stale claim.
   Condensed this memo below 300 ASCII lines, retained BEFORE/AFTER records, removed stale claims,
   copied the exact fix-1c artifact, and regenerated every owned-file size below.
   AFTER static memo checks: PASS on line cap, ASCII, final NOT VERIFIED and all pinned historical facts.
   The new inventory regression first gave `1 failed, 28 passed`: `assert len(inventory) == 11` (got 0).
   The inventory is now generated below.
   Its per-file rerun remains the final check.
The confirmed fatal-time path, book-refusal precedence, Decimal counts and accepted observer design are unchanged.

## FIX 1d validation

Each pytest command used one file only: `python -m pytest <file> -q -p no:cacheprovider`.
- tests/platformkit/ops/test_qualification_cause_report.py: 61 passed (10.39s).
- tests/platformkit/ops/test_qualification_cause_stream.py: 23 passed (5.84s).
- tests/platformkit/ops/test_qualification_cause_runtime.py: 4 passed (1.31s).
- tests/platformkit/ops/test_qualification_cause_landed.py: 29 passed (2.31s) at the lane; after the orchestrator's append
  the self-pinned inventory check failed (28 passed, 1 failed) -- fixed in FIX 1e.
- python -m scripts.platformkit.ops.qualification_cause_report --help: exit 0. No separate self-check command exists.
- contract_preflight --paths <11 owned files below> --base master --spec docs/evidence/tracking/specs/S421_spec.md:
  9/9 PASS over all 11 owned paths; the verdict file is excluded.
Report metadata uses SQL sidecar raw/cause columns; each event's cause comes from the SQL generator.
State rows retain landed _refusal observation; SQL GROUP BY and window counts stream tied identities.

## Owned files

The memo itself is owned too but never pins its own size (AMENDMENT 6(2)).

- `scripts/platformkit/ops/qualification_cause_report.py`: 18233 bytes, 299 lines
- `scripts/platformkit/ops/qualification_cause_stream.py`: 10241 bytes, 203 lines
- `scripts/platformkit/ops/qualification_cause_runtime.py`: 3140 bytes, 73 lines
- `tests/platformkit/ops/test_qualification_cause_report.py`: 17773 bytes, 300 lines
- `tests/platformkit/ops/test_qualification_cause_stream.py`: 10670 bytes, 214 lines
- `tests/platformkit/ops/test_qualification_cause_runtime.py`: 5568 bytes, 116 lines
- `tests/platformkit/ops/test_qualification_cause_landed.py`: 11936 bytes, 213 lines
- `tests/platformkit/ops/fixtures/s421_books.jsonl`: 3051 bytes, 8 lines
- `tests/platformkit/ops/fixtures/s421_state.jsonl`: 801 bytes, 4 lines
- `docs/evidence/forward/qualification_causes/2026-09-22_fix1c.json`: 11946 bytes, 1 lines
- `docs/evidence/forward/qualification_causes/2026-09-22_fix1d.json`: 11947 bytes, 1 lines

NEXT-ROW: were raw_market prices and the ladder fetched at different instants within the same row,
and which is fresher; or does the all-sources-must-agree rule refuse a ladder that could be priced?
These counts answer neither alternative by assertion.

Orchestrator real re-run after FIX 1d (2026-09-23 17:40:35Z-17:4xZ; same command and --as-of; AMENDMENT 4(h) / AMENDMENT 5):
  docs/evidence/forward/qualification_causes/2026-09-22_fix1c.json: 11946 bytes, sha256 7e595b1b0b73196eaac04b547de3929c1a9586fa62c9717eb01478ef5f82ee18; per game [not_accepted, qualified, causes] {"CINATL": [0, 4, "{\"adapter_refused\": 0, \"downstream_refusal\": 0, \"pre_adapter_refused\": 0, \"touch_unavailable\": 0}"], "CLEBOS": [0, 1, "{\"adapter_refused\": 0, \"downstream_refusal\": 0, \"pre_adapter_refused\": 0, \"touch_unavailable\": 0}"], "MIACHC": [575, 103, "{\"adapter_refused\": 575, \"downstream_refusal\": 0, \"pre_adapter_refused\": 0, \"touch_unavailable\": 0}"], "MILPHI": [529, 117, "{\"adapter_refused\": 529, \"downstream_refusal\": 0, \"pre_adapter_refused\": 0, \"touch_unavailable\": 0}"], "STLPIT": [0, 2, "{\"adapter_refused\": 0, \"downstream_refusal\": 0, \"pre_adapter_refused\": 0, \"touch_unavailable\": 0}"], "TORBAL": [146, 0, "{\"adapter_refused\": 146, \"downstream_refusal\": 0, \"pre_adapter_refused\": 0, \"touch_unavailable\": 0}"]}
  docs/evidence/forward/qualification_causes/2026-09-22_fix1d.json: 11947 bytes, sha256 43e6881462fa8554e8440f07d212043ef753634ffe6e56ca5078af47d36aa583; per game [not_accepted, qualified, causes] {"CINATL": [0, 4, "{\"adapter_refused\": 0, \"downstream_refusal\": 0, \"pre_adapter_refused\": 0, \"touch_unavailable\": 0}"], "CLEBOS": [0, 1, "{\"adapter_refused\": 0, \"downstream_refusal\": 0, \"pre_adapter_refused\": 0, \"touch_unavailable\": 0}"], "MIACHC": [575, 103, "{\"adapter_refused\": 575, \"downstream_refusal\": 0, \"pre_adapter_refused\": 0, \"touch_unavailable\": 0}"], "MILPHI": [529, 117, "{\"adapter_refused\": 529, \"downstream_refusal\": 0, \"pre_adapter_refused\": 0, \"touch_unavailable\": 0}"], "STLPIT": [0, 2, "{\"adapter_refused\": 0, \"downstream_refusal\": 0, \"pre_adapter_refused\": 0, \"touch_unavailable\": 0}"], "TORBAL": [146, 0, "{\"adapter_refused\": 146, \"downstream_refusal\": 0, \"pre_adapter_refused\": 0, \"touch_unavailable\": 0}"]}
  READING: every per-game count identical between fix 1c and fix 1d (the state-row mirroring changes nothing on this day, as AMENDMENT 4(1) predicted); only diagnostics future_books (12361 -> 19202) and future_state (1380 -> 2086) and the 2026-09-23 input byte sizes differ -- input growth under a fixed as_of (the 09-23 shards grew). The fix-1d artifact still carries absolute input paths -- AMENDMENT 5's BEFORE state; the AFTER-3 re-run replaces it.

## FIX 1e

Binding findings: round 3 (tier 1 CORRECTIONS 1-5; tier 2 B1-B2, C1-C4), ruled in S421 AMENDMENT 6 (items 1-6).
1. Receipt field (tier 1 #1, tier 2 B2; AMENDMENT 6(1)). report.py takes the receipt for books AND state with the
   landed expression `row.get("response_end_ts", row.get("response_end_utc"))` (forward_replay_io.py:168-169).
   The state PROFILE is stamped separately from response_end_utc in the profile loop (AMENDMENT 1(4)); a visible
   state row without a readable response_end_utc is counted per game as rows_without_response_end_utc.
   BEFORE (new constructs in test_qualification_cause_landed.py): book row with only response_end_utc
   `AssertionError: ('qualified_decisions', 1, 2)`; state row whose response_end_ts differs
   `('qualified_decisions', 2, 0)`; state row with only response_end_ts `('qualified_decisions', 0, 2)`.
   AFTER: all three pass and not_accepted / ADAPTER_REFUSED match (0 / 0). Real state rows carry both fields;
   tier 1 found them equal on a 3,000-row head slice of 2026-09-22 (not the whole set).
2. Memo self-pinned size (tier 1 #2, tier 2 B1; AMENDMENT 6(2)). BEFORE: `assert (21275, 215) == (18939, 210)`
   (memo on disk 21275 bytes / 215 lines). The memo no longer lists itself in the inventory; the test asserts that,
   pins 11 entries including 2026-09-22_fix1d.json, and checks both committed artifact hashes. The pass counts
   below were regenerated after the last edit.
3. Stale lines (tier 1 #3, tier 2 C1; AMENDMENT 6(3)): lines 3-4 and 6 updated (fix 1d listed, AMENDMENTS 1-6,
   no 'belongs to the orchestrator'); the NOT VERIFIED 'remain pending' item is removed.
4. Repo-relative paths (tier 1 #4, tier 2 C3; AMENDMENT 5 / 6(4) and the orchestrator's addendum). New flag
   `--repo-root` (default: the checkout the module lives in). Every recorded path (inputs[].path and the
   missing/unreadable shard example path) is relpath(path, repo_root) with forward slashes; a result starting
   with '..' (or on another drive) is REFUSED by name: stderr `REFUSED path_outside_repo_root`, exit 3, no artifact.
   BEFORE: fix1d.json inputs[0].path is an absolute local Windows path under the main checkout's data/ tree.
   AFTER: construct tests assert `["books/mlb/2026-09-22.jsonl", "state/mlb/2026-09-22.jsonl"]` (none absolute,
   no backslash) and the exit-3 refusal with no artifact. The memo's worktree and scratchpad paths are placeholders.
5. Wording (tier 1 #5, tier 2 C4): the fix1c / fix1d READING line says 'every per-game count identical' and names
   future_books 12361 -> 19202, future_state 1380 -> 2086 and the 09-23 input bytes as input growth under a fixed as_of.
6. SQLite sorter (tier 2 C2; AMENDMENT 6(6)). BEFORE plans: rows() `SEARCH rows USING INDEX duplicate_key |
   USE TEMP B-TREE FOR ORDER BY`; events() two `USE TEMP B-TREE FOR ORDER BY`. Process peak working set
   (psutil peak_wset, construct rows through rows() + events()): 39.4 / 62.9 / 104.1 MB at 1,000 / 10,000 / 30,000
   tied rows (97.2 MB at 30,000 untied). FIX: both queries are index-ordered with indexed EXISTS probes (a tie is
   another row, or another identity, under the same key); identical identities collapse in Python holding one group
   (SQL MIN semantics kept). No temp B-tree remains. AFTER: 34.8 / 34.9 / 34.8 MB (34.8 untied), flat.
   Regression tests: every streaming SELECT's EXPLAIN QUERY PLAN has no TEMP B-TREE; a subprocess measures the
   process peak working set at 1,000 and 10,000 tied rows (bound: under 8 MB apart). Against the old queries that
   test failed `assert (72822784 - 47554560) < 8000000`; now 41,709,568 / 41,754,624 bytes (30,000: 41,705,472).
Landed modules are unedited; repo_relative and REPO_ROOT live in qualification_cause_runtime.py.

## FIX 1e validation

Each pytest command used one file only: `python -m pytest <file> -q -p no:cacheprovider` (Python 3.10.0, box).
- tests/platformkit/ops/test_qualification_cause_report.py: 61 passed.
- tests/platformkit/ops/test_qualification_cause_stream.py: 25 passed (adds the no-temp-B-tree and working-set tests).
- tests/platformkit/ops/test_qualification_cause_runtime.py: 6 passed (adds the two repo-relative path tests).
- tests/platformkit/ops/test_qualification_cause_landed.py: 32 passed (adds three receipt constructs; inventory rewritten).
- python -m scripts.platformkit.ops.qualification_cause_report --help: exit 0 (shows --repo-root).
- contract_preflight --paths <the 9 owned code, test and fixture files plus this memo; verdict file excluded> --base master
  --spec docs/evidence/tracking/specs/S421_spec.md: 9/9 PASS over 10 paths, exit 0.

### AFTER-3: orchestrator real re-run after FIX 1e (2026-09-23 18:02:49Z-18:04:28Z, from the candidate worktree)

```text
python -m scripts.platformkit.ops.qualification_cause_report --repo-root <main checkout>
--books-root <main checkout>/data/cache/ingame_capture_view_v2/kalshi --state-root <main checkout>/data/cache/ingame_capture_view_v2/state
--schedule <main checkout>/docs/evidence/forward/schedules/2026-09-22_maker_forward_full_selection.json
--date 2026-09-22 --as-of 2026-09-23T06:00:00Z --out docs/evidence/forward/qualification_causes/2026-09-22_fix1e.json
wall: 99 s (exit 0); peak working set: not measured by the orchestrator's watch (its process lookup returned 0; the FIX 1e
construct measurement of about 41.7 MB at 1,000 / 10,000 / 30,000 rows stands as the only measurement)
artifact: docs/evidence/forward/qualification_causes/2026-09-22_fix1e.json: 12000 bytes,
sha256 7306276bdcf9b74516a104516dbd7753a1920eb07bc1edc860bb97e350c1fe50
per-game counts: EVERY per-game count identical to fix 1d (146 / 529 / 575 not_accepted on TORBAL / MILPHI / MIACHC, all
adapter_refused; qualified 0 / 117 / 103; CINATL 4, CLEBOS 1, STLPIT 2 qualified with 0 not_accepted). A leaf diff of the
fix-1d and fix-1e artifacts shows 14 differing leaves and nothing else: the four inputs[].path values now repo-relative
(data/cache/ingame_books_local/kalshi/mlb/2026-09-22.jsonl and the 09-23 books and state shards; the view root resolves to
the books_local and state_local_v2 targets), the two 09-23 input byte sizes (books 105939867 -> 115213549, state
9915086 -> 10319707: growth under the fixed as_of), diagnostics future_books 19202 -> 25774 and future_state 2086 -> 2656
(the same growth), and the new per-game state_profile.rows_without_response_end_utc = 0 on all six games (AMENDMENT 6(1)).
```

## NOT VERIFIED

- response_end_ts == response_end_utc on real state rows was checked by tier 1 on a 3,000-row head slice of 2026-09-22
  only, not the whole set or 2026-09-23; this lane did not re-check it.
- A naive (unzoned) state timestamp makes the landed path mark every game LINKAGE_INVALID (unreadable_state, a global
  fatal); this report shows it only in top-level diagnostics, with no per-game flag. A state row carrying NEITHER receipt
  field hits the same limit: refused as invalid_time before the profile (rows_without_response_end_utc stays 0), shown
  only in the top-level diagnostics and refusal_counts (round-4 tier 2, construct D).
- Exact FIX 1c command, wall-clock bounds and peak working set are absent from the supplied artifact and memo.
  The prior record gives only 2026-09-23 17:2xZ. Source file timestamps are not execution measurements.
- FIX 1b's exact command text is unavailable; its reconstruction and assumed schedule are named above.
  Its wall time/peak and build-2 measurements are quoted orchestrator records, not remeasured by this lane.
- The guarded sys._getframe observer of landed caller locals is accepted as designed in AMENDMENT 3;
  the guard fails closed with replay_observer_contract_changed. A future landed implementation change is untested.
- CountPolicy replacement of internal containers is covered only by its construct tests; concurrent patch/LOCK callers are untested.
- Per-game input_refusals use a global three-per-reason example cap, so other games can crowd a game out.
  A books invalid_json example with ticker None appears under no game although its fatal flag applies to every game.
- A SIGKILL can leave atomic_write's temporary output beside --out; the SQLite spool is in scratch. SIGKILL is untested.
- Full-day memory after FIX 1e, capture fetch timing, source freshness, adapter-rule changes and independent FIX 1e review are unverified.
