VERDICT: ACCEPT

# S550 tier-2 Opus adversarial verification, round 1 (2026-09-29)

Candidate: uncommitted files in C:/Users/neelj/nba-harness-h221 (base 4045f96c0). I did not edit anything in the worktree.
Contract: VERIFIER_CONTRACT A, B and Q, plus S550 spec AMENDMENT 1 with the binding
prebuild items B1-B7 and N1-N11.

## What I ran (this session)

- Ran both test files one at a time through run_files.py. test_s550_exec_quality_audit.py gave 36 passed and
  test_s550_exec_quality_audit_real.py gave 5 passed.
- Oracle provenance: I re-ran the r2 probe (exec2_audit_measure + exec2_audit_probe) in-process on the fixture
  and on the renamed 3-game variant, using the generator's own _run/build_variant, and wrote nothing to the worktree.
  The result equals the committed s550_expected.json exactly. The pinned oracle really is the probe's output.
- Byte hygiene: all 10 candidate files (modules, tests, generator, expected file, 3 fixture files) are
  0 CR and pure ASCII. LOC: core 282, io 260, pool 176, construct tests 298, real tests 154, memo 184. All are
  300 or less.
- Vocabulary: no forbidden terms. The only hits are the capture field identifier `yes_price_dollars` (exempt as an
  opaque identifier under the Q6 NOTE) and "between" / "\d" false positives.
- CRLF schedule: I ran IO.run twice on a fixture copy, once with an LF schedule and once with a CRLF
  schedule. The whole receipts are byte-identical, because the schedule identity is `bytes_lf` +
  `sha256_lf` over LF-normalised bytes (load_schedule:167). A CRLF book shard changes only `inputs`. The pools
  stay equal.
- .gitattributes: `s550_real/**`, `s550_expected.json` and `exec_quality/*.json` resolve to text eol=lf
  (git check-attr). The generator .py is not covered, which is harmless: it is Python and never byte-hashed by a test.
- Landing drift: `git diff 4045f96c0 586ec0224` touches no file under platformkit/execution,
  ingame/quote_freshness, conftest or .gitattributes (only 16 doc/spec files changed). The pinned import
  closure and the MUST-NOT-MOVE blobs are unchanged on master.
- Mutation power (scratchpad/s550_mutate.py and s550_mutate_real.py): each mutant is a mutated COPY
  installed under the real module name, and the test functions are called directly.
  - Depletion `>= ahead + 1` changed to `>= ahead` is KILLED (test_fill_scan[1]).
  - Flipping the taker_side markout sign is KILLED (test_markout_print_and_contract_weighting, -1.6 becomes +1.6).
  - Flipping the fill side mapping (no/yes) is KILLED (test_fill_scan cases 0, 2, 4, 6).
  - Censoring a moved instant because of a later gap (the B1 violation) is KILLED (test_censoring_walk cases 2 and 5).
  - Keeping zero-weight rows in a pool (the B4 violation) is KILLED (ZeroDivisionError in 2 tests).
  - Switching off the taker_outcome_side conflict refusal is KILLED.
  - SURVIVED: drawing control lags only for non-skipped instants (B3) and bootstrap index draws[99] instead of
    draws[100]. See N1.

## BLOCKING

None. I found no reachable input on which the candidate is wrong, unsafe or silent.

## Attack results

1. Silent failures. There is no bare or swallowing except.
   - `_real` catches ValueError/OverflowError and returns None, and every caller counts it.
   - stream catches ValueError (which includes UnicodeDecodeError) and counts it in `lines_bad_json`.
   - parse_days and load_schedule turn ValueError into Refused (exit 2).
   - Every row refusal increments a named counter, and every counter name used is present in REFUSALS
     (zero counts are emitted).
   - A partial last line, or a line past the identity byte size, is counted `lines_skipped_partial` and
     reading stops there.
   - The stricter-than-probe refusals are all counted and disclosed in the memo: count <= 0, price outside
     (0, 100), negative sizes, malformed ladder. Zero of them fired on the fixture. The orchestrator's real-week
     bar (50 of 50 pool keys equal to the probe) shows they move no pooled value on the week.
2. Causality.
   - The engine arm's seconds_since_change comes from Game.since_event, which bisects the event RECEIPT
     list (ev_rec) at or before t.
   - The book src_ts is the snapshot receipt at or before t, and the join grid sits on snapshot receipt times.
   - The event estimands deliberately use the source play clock (B2), with the prior book at the play time.
     That is descriptive, as defined.
   - Tape and fill scans use created_time and are labelled replay/backfill in NOT_VERIFIED.
3. Determinism.
   - The receipt contains no set iteration: keys are sorted for the byte prefilter, and sets are used only for
     membership.
   - Floats are summed in the probe's loop order.
   - The receipt is written with sort_keys and ASCII, LF by writing bytes, and uses no hash().
   - The fresh-process test runs under PYTHONHASHSEED 1 and 2 and asserts byte equality.
   - The schedule is LF-normalised (verified above).
   - Input paths are root-relative labels.
4. Red-after-landing. No absolute paths, byte-length pins of other modules or git refs in the tests. The
   fixtures are LF-pinned. See N2 for the import-closure pin.
5. Test power: proven for 6 key rules (list above). Two rules have no construct power (N1).
6. Float vs Decimal. Counts and sizes stay binary floats, because the bar is exact numeric equality with
   the float probe (B1-B4: "the probe's exact semantics win"). See N3 for the one reachable consequence.
7. RSS guard and exit codes.
   - The RSS check runs every 10,000 lines (a global counter reset per run). Above 400 MiB, MemoryCap gives
     exit 5 with no receipt and no sidecar (tested with an injected reader).
   - A Refused gives exit 2 with no receipt, including bad day, duplicate day, a malformed or duplicate
     schedule entry, and bad JSON.
   - Any other exception propagates (exit 1) before the receipt write.
   - The strict JSON writer raises on NaN before opening the temp file (tested: the directory stays empty).
8. Vocabulary, 300 LOC and ASCII: all pass (above).

## NOTES (non-blocking; for the fix-pass queue or the ledger line)

N1. Two B3/B4 semantics have no construct-test power. The mutants "draw a control lag only for instants with a prior book" and
    "bootstrap ci90 from draws[99]" both pass all 41 tests. test_control_grid_seeds_and_lag_draws uses gap-free
    snapshots, so no instant is skipped. The 3-row pool test and variant3 have tied order statistics.
    The orchestrator's bracketed real-week equality with the probe (all 50 pool keys, including ci90) does
    guard both on the week, so this is not blocking. Suggested follow-up: add one construct case with a
    >10 s snapshot gap before a control instant, and one pool case whose draws[99] != draws[100].
N2. test_import_closure pins EXPECTED_PROJECT exactly (quote_engine's current dependency set). A future
    legitimate new pure import in quote_engine will turn this S550 test red. That is intended as a signal, but
    it is brittle. A subset check against a forbidden list would be less fragile.
N3. Float depletion accumulation can miss an exact decimal tie on reachable 2-dp fractional counts and
    sizes. Example: ahead 0.14 and at-price prints 0.01 + 1.13, where float 1.1399999999999999 < 1.1400000000000001.
    The spec's decimal rule "accumulated >= ahead + 1" would fill; the float code does not. The
    probe behaves identically, so the pooled numbers stay equal to the probe (the bar). This is a
    measure-zero misclassification of one join instant. A Decimal port belongs to a later row, with the probe
    re-baselined.
N4. write_sidecar falls back to current RSS when peak_wset is absent (non-Windows / RunPod), but still
    labels it peak_wset_mb. This is harmless on this box, where it is disclosed only by `platform`.
N5. The memo's file sha256 inventory is of working bytes. The files are LF now, but a core.autocrlf=true checkout
    of the committed .py files will materialise CRLF, so those shas will not reproduce from a fresh
    Windows checkout (the fixtures are pinned LF, so their shas will).
N6. The schedule fixture is not byte-verbatim: the `selected_at` line was removed for the preflight check. It is
    disclosed, and no reader uses the field. Also, load_schedule refuses a duplicate ticker or game_key with exit 2. That is
    not in the spec, but it is loud rather than silent and does not fire on the real week.
N7. A previous receipt in --out-dir survives an exit-2 or exit-5 run (the module does not delete it). "No receipt"
    means no new write. The orchestrator should use a fresh out-dir per bracket run.

## Landing checklist (A6/A7)

- Land exactly: the 3 modules, the 2 test files, the generator, s550_expected.json, s550_real/**, the memo,
  and the 3-line .gitattributes block. Use an explicit pathspec.
- Re-run both test files one at a time on master after landing (A1). The dependencies are unchanged on master, so
  the same 36 + 5 are expected.
