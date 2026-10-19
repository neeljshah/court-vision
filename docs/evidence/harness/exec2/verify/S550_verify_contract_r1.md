VERDICT: ACCEPT
S550 round 1, contract-style verifier (tier 1, Opus standing in for codex sol). Candidate = uncommitted files in nba-harness-h221 (HEAD 4045f96c0). 0 BLOCKING, 7 NOTE.

Method: I read the spec plus AMENDMENT 1, S550_prebuild_opus.md, VERIFIER_CONTRACT sections A, B and Q, the three probe files, the three new modules, both test files, the generator and the memo. I diffed the core line by line against exec2_audit_probe.py, exec2_audit_measure.py and exec2_audit_cluster.py. I ran each test file on its own through run_files.py: test_s550_exec_quality_audit.py gave 36 passed, and test_s550_exec_quality_audit_real.py gave 5 passed. contract_preflight passes on all 8 files (vocabulary, CRLF, LOC, schema, head slice, threshold, removed artifacts). A grep finds no non-ASCII bytes.

## Contract items (spec 1-15; where AMENDMENT 1 or a prebuild finding supersedes the spec, it is named)
1  ESTIMAND IDS -- MET (with N9: the probe's key strings are kept and the sha test is cut). VERSION is at exec_quality_audit.py:20. DEFINITIONS are built at exec_quality_audit_pool.py:37-68. The test at _real.py:67-68 checks that all 50 emitted keys resolve in definitions.
2  TIME -- MET (with N2). Input timestamps go only through `ts` (core:18, pool:18, io:27). The grep test is at test:58-60. Day keys are validated by DAY_RE plus date arithmetic at io:35 and io:61-76. The no-zone, True and NaN cases are tested at test:50-57.
3  MARKS -- MET. mark_after [t, t+10] and mid_before age <= 10 are at core:82-94. The crossed-book and 0/100 checks are at pool:118-121. The snapshot_bulk and other-type counters are at io:152-153. Boundaries are tested at test:64-79.
4  CENSORING -- MET (with B1: the walk is the probe's). core:96-106 matches probe:175-188. The move-then-gap and exactly-10 s cases are tested at test:82-93.
5  CLOCK GRID -- MET (with B3: three seed streams, one lag draw per instant, skipped instants included). core:113-119 and core:147-165. control_lag_absent is counted. PYTHONHASHSEED 1 vs 2 byte equality is tested at _real.py:(fifty-four)-59. The paired difference is CUT per N6.
5a EVENTS -- MET (with B2). The typing, the 900 s source-clock gate, source-only lags and EV_WIN are at core:35-64. Tested at test:114-130.
6  TAPE -- MET, plus change (iv) (N3). Dedupe runs before validation (pool:131-138). Conflict and absent outcome side are at pool:151-153. receipt_before_created is kept (pool:154-156). Tested at test:133-146.
7  CENSUS AND STATUS -- MET. The status ladder, 6 h cap and no_final_row are at core:255-282. The 19/20 snapshot, 21600 vs 21600.001 and TAPE_MISSING key-exclusion cases are tested at test:180-194.
8  MARKOUTS -- MET. core:211-217 carries both weightings and excludes fees (the fee note is at pool:60). The 0.0 / -1.6 example is tested at test:197-202.
9  JOINS -- MET. In fill, prints are strictly after t and inclusive of t+T, a strict through-print fills, and depletion needs >= ahead+1 (core:185-199). An unknown ahead is counted at core:237-238. Tested at test:205-215.
10 ENGINE ARM -- MET (with N5: time since the last event receipt). core:172-182 is a verbatim copy of the probe and imports lazily. Tested at test:218-223.
11 POOLING -- MET (with B4). pool:159-176 is the probe's pooled function, keyed on the union of keys. Game order is sorted days (io:72), then schedule-file order (io:189-190). Tested at test:226-234.
12 INPUT IDENTITY -- MET (with N7). Head and tail sha256 are at io:79-86. Paths are relative with forward slashes, and a missing shard is recorded as exists:false (io:91-93). Schedules are hashed LF-normalised (io:167-168). The limit is stated at pool:62-63 and tested at test:237-250.
13 STREAMING -- MET. The loader reads rb line by line with a bytes prefilter, reads each shard only up to its identity size, and runs `del` per (sport, day pair) (io:89-117, io:201). The sidecar holds the resource figures only (io:225-230). The two-fresh-process test is at _real.py:(fifty-four)-66.
14 RECEIPT -- MET (with B6 and N8). Output is strict JSON, ASCII and LF, written to a temp file then os.replace (io:214-222). All 11 keys are present (io:205-211). --out-dir is at io:239. Tested cases: missing schedule gives a partial run with exit 0 (test:274-279); malformed schedule and bad day give exit 2 (test:282-288); NaN leaves no file (test:267-271). Empty inputs give pools {}.
15 RISK GATE -- MET (with N1). The static AST closure (including the lazy venue_fees_decimal) equals the 10 expected project modules. No forbidden leaf is reachable, and psutil is the only non-stdlib leaf and is imported lazily (_real.py:107-154).
ORCHESTRATOR ADDITION (RSS guard) -- MET. The check runs every 10,000 lines and exits 5 with no receipt (io:99-101, io:248-250). Tested at test:291-298.

## Prebuild findings
B1-B4: MET (above).
B5: the bar is the orchestrator's bracketed run, which the brief reports as done: A == B bytes, 50 of 50 pool keys equal to the probe, 52.5 MB. I did not re-run it.
B6: MET. B7: MET; LOC is 282 / 260 / 176, and the tests are 298 / 154.
N1-N5: MET. N6 and N9: CUT, as adjudicated. N7 and N8: MET. N10: q is at core:67-70, and the sorts are stable. N11: MET; the generator is committed and the variant3 oracle is pinned.

## VERIFIER_CONTRACT
A1-A7: this was a worktree run, not a master run (per the override). The real-row oracle reproduces for me: tests pass.
B1-B10: none triggered. The only pre-existing file edited is .gitattributes (+3 lines, which the spec allows). The MUST-NOT-MOVE files are untouched on disk, and the git diff since base shows no overlap.
Q1-Q2: not applicable (not a scored trial). Q3: no bar moved. Q6: the preflight vocabulary check is clean; `yes_price_dollars` is an opaque input identifier, which the S223 ruling exempts. Q7: the construct enumeration covers items 2-15. Q9: per-game stats are persisted.

## NOTES (none blocking)
N-a  .gitattributes: master (2de35db5f) appended 3 s516 lines at the same place after the base. Landing will hit a textual conflict; keep both blocks. Per the MEMO SHA RULE, the memo's base 4045f96c0 is stale only on non-owned paths. The only overlap is .gitattributes, and no imported module has changed since base.
N-b  The schedule fixture is not verbatim: the lane removed `selected_at`, a field no reader uses. The memo discloses this at line 84, and the spec EVIDENCE said verbatim. Books and state are untouched.
N-c  There are extra fail-closed refusals the spec does not list. Duplicate ticker or game_key in a schedule gives exit 2 (io:177-178). A malformed ladder (for example p=1.2) refuses the whole snapshot (pool:90-104); I probed this: `snapshot_unparsed` 1. Trade price outside (0, 100) or count <= 0 is also refused. I found no duplicates or malformed entries across every schedule file in docs/evidence/forward/schedules, and the bracketed run was equal, so no pooled effect.
N-d  Float counts and prices are deliberate for exact equality with the probe. This is safe: inputs are fixed-point strings of 2-4 dp, values are validated finite before any arithmetic, and output is rounded to 4 dp.
N-e  Results depend on input order only at exact-time ties (stable sort keeps file order), the same as the probe. The memo discloses this at lines 70-71 and 184.
N-f  The memo says depletion and state_change are "exercised on the renamed 3-game variant". That is confirmed: variant3 through_share is 0.92 and there is one state_change (s550_expected.json).
N-g  If psutil is missing, the RSS guard or the sidecar raises an uncaught ImportError. The sidecar is written after the receipt, so the receipt survives. Acceptable.

## NOT VERIFIED
- The bracketed real-week run and the 52.5 MB peak (taken from the orchestrator's report; I did not re-run them, and I did not read the archive).
- Behaviour on Python 3.12.
- The per-file tests on master (A1): I ran them in the worktree only.
- The fixture's byte-verbatim relation to the source shards: I did not read the archive.
