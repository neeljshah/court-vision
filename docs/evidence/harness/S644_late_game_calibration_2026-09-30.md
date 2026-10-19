# S644 constructed candidate, 2026-09-30

BUILD COMPLETE after fix rounds r1-r13 (lead) and r1b (a codex fix lane, see its section). The only archive runs are
the lead's census-only development probes; the final candidate (r11) was run twice against one immutable snapshot
copy of the MLB book and state shards 2026-09-21..09-30: the two receipts are byte-identical and are retained with
their resource sidecars under docs/evidence/harness/S644_dev_probe/run1/ and run2/ (FIX r9-r11).
Construct tests after r13: 117 passed (core/statistics 59, fix regressions 19, reader 22, preregistration 17).
No scored result is claimed.
Binding design: docs/evidence/tracking/specs/S644_spec.md, including AMENDMENT 1 and AMENDMENT 2.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md, sections B and Q.

## Before-condition

Before creating any module, the local filename census was run with:
`@(Get-ChildItem scripts,tests -Recurse -File -Filter '*late_game_calibration*').Count`.
Exact captured output: `BEFORE: late_game_calibration files = 0`.
The supplied A1 premise replaces the bulk-population premise with served FOCUS
snapshots. The user reserves the development archive probe for the lead.
The spec supplies no literal REAL ROW; the first reader test consumes the
constructed_archive fixture through schedule, adjacent shards, grid, outcome,
statistics and deterministic receipt. No fabricated archive observation is claimed.

## Files and implementation

New modules are scripts/platformkit/ingame/late_game_calibration_r2.py,
late_game_calibration_r2_io.py, late_game_calibration_r2_stats.py and
late_game_calibration_r2_prereg.py. Tests are the four corresponding owned
test_late_game_calibration_r2, _fix, _io and _prereg files under tests/platformkit/ingame/.
Only those files, this memo and the owned .gitattributes append were edited.
The appended pattern is `docs/evidence/forward/late_game/*.json text eol=lf`.
No JSON fixture or PREREG_R2.json was created; the only tracked JSON are the four retained development-probe files.

The core freezes the low side and NBA admission at the first valid entry.
Decimal prices remain Decimal through midpoint, complement, path means,
Prelec and residual arithmetic. Exact Poisson-binomial inference uses floats
only for the expressly specified probability DP. Platt uses derived logits.
Strict counts refuse booleans, floats and numeric strings. Receipt comparisons
retain fractional microseconds after validation through the shared parser.
The grid itself is integer microseconds. Future rows are filtered before
validation and duplicate classification; their count and stream identities can
change while the cohort statistics remain invariant.

Conflicting equal-receipt records are tombstones; identical records collapse.
Counters and results are independent of record order. A conflicting final still
retains its hard cutoff. Final labels are unresolved on conflicting or tied scores.
Unresolved games retain admission and receive both residual-bound calculations.
The MLB terminal text was read from pinned commit
`c8de21366a88bc26dbef9f9a2139624199e14242`; no test reads a moving repository ref.
NBA zero-clock exclusions use A6. No must-not-move file was edited.

The reader uses the landed stream/load_state byte prefilter and schema machinery
with isolated function globals for Decimal JSON decoding, resource checks and
the response_end_utc alias. It does not mutate the landed module globals.
Raw data is held for one served game at a time; compact retained observations
are spooled with a 256 MiB bound, append, flush and fsync. RSS is checked during
ingestion and fitting; the 400 MiB refusal returns exit 5 without a new receipt.
Input sizes and head/tail digests are deterministic receipt fields; RSS is separate.
The comparison median is the exact resolved-cohort ENTRY half-spread per A13.
The ninth-inning sensitivity is descriptive. The two sports are never pooled.

Confirmation verifies the seal and lead ledger charge before computing metrics.
NBA reads as of its fixed lock; MLB reads as of 72 hours after the first actual
final receipt of the lead-designated World Series last game. Every schedule day
through the cohort end is required, including explicit empty schedules.
An exclusive claim protects atomic publication of one confirmatory receipt per
sport in the output directory. Subsequent receipts are DESCRIPTIVE.
The replication helper requires two confirmatory sports with the same seal and
the same non-null directional verdict. Other combinations remain SINGLE-CORPUS.
First eligibility is the seal commit UTC date plus one day, with no backdating.
No seal exists from this lane, so actual lost MLB postseason days are unmeasured.

## Imported interfaces read before use

- exec_quality_audit_io: `load_schedule(root, day, inputs, cnt) -> list`;
  `load_state(root, sport, days, keys, inputs, cnt)`;
  `stream(path: str, label: str, keys: list, inputs: list)`;
  `Refused(Exception)` and `MemoryCap(Exception)`.
- venue_time: `parse_venue_time(value: object) -> float | None`.
- game_market_link: `alias(sport: str, abbr: Optional[str]) -> Optional[str]`;
  `team_code_from_ticker(ticker: str) -> Optional[str]`. Their defining module,
  and forward_schedule_writer's import site, were read. No D1 linker is called.
- atomic_replace: `replace_with_retry(temporary: Path, target: Path, *, durable: bool = True, on_cleanup_error: Callable[[OSError], None] | None = None, on_retry: Callable[[], None] | None = None) -> bool`.
- exec_policy_prereg: `canonical(obj: dict) -> bytes`; `dump(obj) -> bytes`;
  `PreregRefused(Exception)`.
- seal_provenance: `attest(repo_root: Any, artifact_path: str, declared_sha256: str) -> dict`.
  live_shadow_prereg was read as the write-once provenance reference.

## Construct coverage

1. Unresolved ticker orientation is counted.
2. Book age 31 seconds is excluded.
3. Spread 11 cents is excluded.
4. NBA fourth-quarter 601/600 and overtime admission are distinguished.
5. MLB seventh/eighth innings are distinguished.
6. MLB home-ahead bottom terminal state is excluded.
7. Grid instants at and after the first final are excluded.
8. Entry-band 0.20/0.21 boundaries are distinguished.
9. Missing final preserves unresolved admission and bounds.
10. NBA season type 1, missing and invalid labels are distinct exclusions.
11. The three-game primary residual is hand-computed.
12. Bootstrap seed and sorted interval indices reproduce.
13. The 29-game floor is INSUFFICIENT.
14. Valid seal and not_alone, rewritten and body_mismatch refusals use real temporary git histories.
15. State age 61 seconds is excluded.
16. Identical and conflicting duplicates, including both three-record permutations, are exercised.
17. Future invalid rows cannot alter cohort statistics.
18. A game joins across UTC midnight.
19. NBA period four, zero clock and margin two is excluded; overtime at 300 seconds stays.
20. A later live row does not erase the first-final cutoff.
21. Conflicting and tied finals are unresolved.
22. Both residual signs and the hand-computed exact three-game probability are exercised.
23. At each of 0.02, 0.10 and 0.20, 2000 seeded null replicates at n=30 satisfy the rejection ceiling; zero/all-win tails are exercised.
24. Mirror identity and separated Platt unavailability are exercised.
25. RSS ingestion/fitting refusals, immutable receipt reuse, merge/deletion/recreation seal refusals and recoverable replacement failure are exercised.
26. Late-capture flagging is exercised.

## Commands and results

Each test command was run separately with `-q -p no:cacheprovider`:
`python -m pytest tests/platformkit/ingame/test_late_game_calibration_r2.py`: 59 passed.
`python -m pytest tests/platformkit/ingame/test_late_game_calibration_r2_fix.py`: 17 passed (after r9).
`python -m pytest tests/platformkit/ingame/test_late_game_calibration_r2_io.py`: 22 passed.
`python -m pytest tests/platformkit/ingame/test_late_game_calibration_r2_prereg.py`: 17 passed.
Both IO and preregistration `python -m ... --help` commands passed.
The preregistration per-file tests exercised `--check` on a temporary sealed history.
The pure core and statistics companion expose no CLI.
Contract preflight with all fourteen candidate paths (ten row files plus the four retained probe files), `--base master` and
`--spec docs/evidence/tracking/specs/S644_spec.md`: nine PASS, zero FAIL.
Checks: vocab, crlf, loc, schema, head_slice, spec_threshold, proposed,
removed_artifact and row_duplication. The preflight command uses the user-required
base argument; the construct tests and this memo make no moving-ref comparisons.
All eight Python files are ASCII and at most 300 lines; no dependency size is pinned.
The .gitattributes diff has exactly one added line and no removed lines.

## FIX r1 (Opus lead as fixer; contract tier codex sol r1 REJECT; spec AMENDMENT 2)

- Finding 1 (season_reason missing accepted): entry now refuses `entry:season_reason_missing` when the key is absent;
  test `test_fix_r1_season_reason_key_must_be_present` (mutation removing the check makes it fail).
- Finding 2 (any conflict blocked a clean final): only a conflict tombstone that holds a final or lies at or after the
  first final receipt blocks the label, and that case is checked before the final scores are read (it was reported
  as `unreadable_final`); tests `test_fix_r1_live_conflict_before_clean_final_keeps_the_label` and
  `test_fix_r1_conflict_holding_a_final_is_unresolved` (mutation removing the check makes the latter fail).
- Finding 3 (one umbrella counter): the first-window scan stops at the final cutoff; non-live rows count as
  `window_scan_not_live`, unreadable gate fields as `window_scan_unreadable`, heuristic terminal states under their
  own reason; `window_state_unreadable_or_terminal` is no longer emitted; test `test_fix_r1_window_scan_counters_have_one_meaning`.
- Finding 5: the book refusal test now asserts the exact reason and the exact counter set per input.
- Finding 6: the `.gitattributes` line is owned by AMENDMENT 2 (C1).
- Finding 4 / development probe (AMENDMENT 2 C7), inherited lead report, not independently validated in this lane:
  reportedly run twice by the lead on MLB 2026-09-21..2026-09-29 served games
  (development days), census only: served 21, focus-covered 12, window-covered 0, band games 0; refusals include
  `window_scan_not_live` 4,538, `state_stale` 3,572, `not_live` 3,362, `book_stale` 546, `at_or_after_final` 144.
  The two receipts are byte-identical (sha256 86c8fd009dc93cbd2ead4fe5f95ac23489bb9272c00ce89d64914ef260b8f3c7);
  peak RSS 297.5 and 297.0 MiB. Window coverage 0 is the S598 first-hour focus limit (AMENDMENT 2 C6): on 09-24 game
  822842 focus snapshots span 18:33-19:35Z while innings 8+ run 20:43-21:06Z.
- Lead adversarial probe: real 09-24 focus rows (Decimal parsing through the reader's stream) driven through
  `reduce_game` with synthetic in-window states: a real mid of 0.54 is excluded `entry:outside_band`; with the book
  shifted into the band the YES and NO_proxy sides and both outcome labels come out as specified.
- Tests after the fix: core 59, fix 4, IO 22, prereg 17 passed (memory-guarded per-file runner).

## FIX r2 and r3 (Opus lead; contract sol r2 and adversarial astra r2 / r3 REJECT), condensed

- The grid span ends at the first-final cutoff and the whole-span veto is gone, so no later row (live, final or
  post-final) can revoke a frozen entry (`test_fix_r2_post_final_receipt_cannot_revoke_admission`,
  `test_fix_r3_later_rows_never_revoke_a_frozen_entry`; mutations fail both). Scan-row terminal reasons are
  `window_scan_<reason>`. The World Series lock uses the C3 conflict predicate. The confirmatory claim is an
  OS-released exclusive lock on a never-deleted claim file (`confirmatory_claim`; a no-op lock mutation fails).
  Refusal tests assert exact counters.

## FIX r1b (codex fix lane s644_fix_r1, 2026-09-30 17:12-17:18Z)

Disclosure: the lead cancelled this lane at its RAM gate at ~16:26Z and fixed r1 by hand, but the gate loop kept
running and dispatched the lane at 17:12Z; it worked on the r1 verdict concurrently with the lead's r3 edits. Its
code changes were two no-op simplifications in late_game_calibration_r2.py (season_reason read after the presence
check; the redundant second final-conflict test removed) plus extra fix regressions; the lead re-ran every file
afterwards: 59 / 13 / 22 / 17 passed. Its own notes follow.

Lane notes, condensed by the lead (every claim below was re-checked by the lead's later runs): it reproduced
each r1 finding as a mutation of the lead's already-fixed files (BEFORE outputs are mutation reproductions): missing
season_reason admitted -> now `entry:season_reason_missing`; live conflicts before a clean final blocked the label
-> now labelled (24 row permutations tested; conflicts holding or after a final stay unresolved); one pre and two
final rows produced `window_state_unreadable_or_terminal 3` -> now `window_scan_not_live 1, not_live 2,
at_or_after_final 1`; the book-refusal test asserts full counter sets. It ran no archive probe (reserved to the
lead) and kept the AMENDMENT 2 C1 .gitattributes line.

## FIX r4 and r5 (Opus lead; adversarial astra r4 / r5 REJECT), condensed

- Complete counter dictionaries in the final / duplicate / conflict tests; the grid starts at the later first
  receipt; the confirmatory marker is pinned under the repository (hardened to the Git top in FIX r7).

## FIX r6 (Opus lead; contract sol r4 REJECT), condensed

- Distinct NBA exclusions (season_type missing / invalid, season_reason missing / present, non-regular) with exact
  counters; a non-finite RSS sample fails closed (`rss_unavailable`); complete counters in the future / naive /
  conflicting-final tests; while the as-of state is stale or a row is a conflict tombstone the grid counts the
  constant instants arithmetically up to the next receipt (matched a per-instant brute-force reference on 300
  seeded random inputs; `test_fix_r4_ancient_receipts_are_skipped_arithmetically`).

## FIX r7 (Opus lead; adversarial astra r6 REJECT)

- Adversarial 1 (marker relocatable through a subdirectory --repo-root): the marker and claim path come from
  `late_game_calibration_r2_prereg.marker_path`, the canonical `git rev-parse --show-toplevel` of --repo-root; the
  IO test re-runs with `<repo>/scripts` and asserts one marker and no second tree (mutation reverting it fails).
- Adversarial 2: the duplicate-plus-conflict orders assert complete counters.
- Adversarial 3: memo opening updated.

## FIX r9 (Opus lead; contract sol r6 REJECT; adversarial astra r7 ACCEPT WITH CORRECTIONS)

- Sol 1 (cohort date): the cohort / eligibility date is `late_game_calibration_r2.local_date`, the America/New_York
  date of the served entry's `scheduled_start` (a Dec 20 evening game at 00:30Z Dec 21 is a Dec 20 game); absent or
  unparseable -> excluded `local_date_unresolved` (counted); `test_fix_r6_cohort_date_is_the_eastern_date_of_the_scheduled_start`.
  The IO fixtures now carry scheduled_start as the real schedules do.
- Sol 2: the cutoff final row itself counts as `window_scan_not_live` before the scan stops.
- Sol 3: exception tests match the exact reason text (`^invalid_price$`, `^timestamp_rejected$`, `^construct$`,
  `^spool_cap$`) and both RSS exit tests assert the exact printed `MEMORY_CAP <reason>` line.
- Sol 4 / astra NEW GAP: the development probe was re-run twice on the r9 candidate against the same immutable
  snapshot; both receipts AND both resource sidecars are retained and force-tracked at
  docs/evidence/harness/S644_dev_probe/run1/ and run2/ (receipts byte-identical, LF sha256
  f11f3fd4503d8a950975bece0c562ff789a8cfc95b599f1d82f3fb078078db86, unchanged from r8; peak RSS 298.3 / 298.2 MiB).
  The receipts are data kept byte-exact (re-encoding them to meet the 300-line code/memo rail would break the byte
  comparison).
- Sol 5 / astra 1: memo statements corrected (fix tests 17, the preflight path count, the statistics wording).
- Tests after r9: 59 / 17 / 22 / 17 passed.

## FIX r10 (Opus lead; contract sol r7 REJECT, adversarial astra r8 REJECT)

- Sol 1 (confirmatory mode accepted any seal / ledger path): `late_game_calibration_r2_prereg.require_canonical`
  resolves the canonical Git top of --repo-root and refuses `noncanonical_confirmatory_paths` unless the seal is
  `docs/evidence/forward/late_game/PREREG_R2.json` and the ledger `docs/evidence/RESULTS_LEDGER_SYSTEM.md` there
  (the IO test runs a stray ledger copy -> exit 2; a pass-through mutation fails the test).
- Astra 1 (an ET Dec 20 evening game sits in the Dec 21 UTC schedule): the NBA lock requires UTC schedule days
  through 2026-12-21 while admission stays ET date <= 2026-12-20; the IO test adds such a game and asserts it is
  not excluded `after_nba_cohort` (a UTC-date mutation fails the test).
- Astra 3: an unresolved local date is excluded `local_date_unresolved` and no later date predicate overrides it.
- Sol 3 / astra 2: every prereg refusal regex is anchored (`^...$`) and the replacement-failure tests match the exact
  OSError text.
- Sol 2 / 5, astra 4: memo opening, totals (115) and inventory corrected.
- Sol 4 (1,090-line JSON receipts over the 300-line rail): ADJUDICATED by the lead as not applicable -- the rail
  binds code and memos; spec data artifacts are exempt (human-gated-paths rule: spec DATA modules exempt), and
  re-encoding the receipts would break the byte comparison they exist to show.
- Development probe re-run twice on the r10 candidate: byte-identical, LF sha256 unchanged
  (f11f3fd4503d8a950975bece0c562ff789a8cfc95b599f1d82f3fb078078db86), peak RSS 298.7 / 297.7 MiB.

## FIX r11 (Opus lead; contract sol r8 and adversarial astra r9 REJECT)

- ET date precision: `local_date` floors exact epoch seconds (Decimal) before the time-zone conversion; a
  04:59:59.999999999Z Dec 21 start is Dec 20 ET, 05:00:00Z is Dec 21 (a float mutation fails the test).
- Canonical repository: marker, seal and ledger resolve under the Git top of THIS module's repository (`ROOT`); a
  --repo-root in another repository is refused `noncanonical_repo_root` (IO test; a pass-through mutation fails).
- Exact assertions: every remaining refusal regex anchored; the confirmatory refusals and the prereg writer assert
  the exact printed line; the Dec 21 UTC-file game asserts its exact reason (`no_state`, admitted by date).
- Development probe re-run twice: byte-identical, LF sha256 f11f3fd4503d8a950975bece0c562ff789a8cfc95b599f1d82f3fb078078db86.
- Master drift: the canonical ledger RESULTS_LEDGER_SYSTEM.md changed on master (unrelated rows); the landing adds
  only the S644 paths and never rewrites the ledger.

## FIX r12 (Opus lead; contract sol r9 REJECT on one item; adversarial astra r10 ACCEPT)

- MLB lock look-ahead: `lock_time` derives lock = first final receipt + 72 h and applies the conflict and score
  checks only to rows received at or before the lock; `test_fix_r11_ws_lock_ignores_rows_received_after_the_lock`
  (a differing final one microsecond after the lock is invisible, one exactly at the lock refuses; removing the
  as-of-lock filter fails the test). The development probe does not call lock_time (receipt unchanged).

## FIX r13 (Opus lead; contract sol r10 REJECT; adversarial astra r11 ACCEPT)

- The MLB lock reads the World Series game's state shards from its schedule day through day + 4, so a correction
  received in a later shard before the 72 h lock is seen (`test_fix_r12_ws_lock_reads_corrections_in_later_shards`;
  a two-day span mutation fails it).
- Scope: the candidate was transplanted onto current master (branch s644-land at 770d30c6b, uncommitted files
  carried over, the owned .gitattributes line re-appended); `master..HEAD` is empty before the landing commit.

## Final verdicts and NEW GAPs

Contract tier codex sol r11 ACCEPT; adversarial tier codex astra r12 ACCEPT (rounds r1-r10 / r2-r9 REJECTs folded
as FIX r1-r13). NEW GAP (recorded, not fixed): `run` reads each game's state from its schedule day and the next UTC
shard only, so a final corrected three or more days later is not seen (astra r12); the lock's five-shard horizon
misses a completion delayed past day + 4 (sol r11). Both lie outside A4's adjacent-shard scope.

## NOT VERIFIED

This fix lane exercised only constructs: no real archive, network, pod or scored run.
The inherited lead census and byte-comparison claim in FIX r1 were not independently reproduced;
the two underlying receipts were not inspected. Finding 4 remains NOT VERIFIED by this lane.
Archive-wide state counts, NBA live schema/cadence before October 20, NBA nightly
served coverage and achievable MLB postseason band-game counts remain unverified.
Archive RSS figures above are inherited lead claims, not this lane's measurements; production crash
recovery beyond the stale-claim construct and concurrent process races were not tested. Replacement failures and
RSS refusals were injected constructs. No serving caller or flag was changed.
The source MLB state has no elapsed inning clock: late_capture is unobservable
unless window_opened_utc exists; that absence is counted, never inferred from outs.
MLB scored admission requires strict schedule season_type 3 or a lead-declared
postseason date roster supplied through repeatable --postseason-day and stored
in the receipt. Archive metadata availability and lead roster correctness are
unverified; absent evidence is counted postseason_unestablished. Development
reads do not require postseason evidence.
The lead designation that a particular game is the World Series last game is an
external declaration; its actual first-final timestamp is verified from the input.
Input-order invariance applies to statistics and refusals; byte digests naturally
change if input bytes are reordered. No repository commit was created.
The window path on REAL in-window data is unexercised: no archived served game has focus snapshots inside the late
window before the S598 adoption. The descriptive Platt bootstrap costs about 1 s per fit on 10,000 observations.
