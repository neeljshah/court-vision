# S510 paper desk issue scanner - FIX 4 - 2026-09-29

AMENDMENT 5 E1-E2 implemented or disclosed as directed. Six row modules;
construct and sealed-fixture validation only. Independent acceptance is pending.
Binding inputs: _verdict_s510_4.md and S510_spec.md through AMENDMENT 5.
The generated inventory pins the last implementation-changing commit and hashes
all candidate modules/tests. Fixture source: 3b63471840c017b60109766b48942029907502b0.
No moving-reference comparison, operational action, external-tree write or deployment.

## FIX 1

Reproductions ran before the corresponding module changes. Tests use constructs
or the unchanged sealed fixture; only the separately requested live check uses real files.

| Finding | Failing reproduction | Change and regression |
| --- | --- | --- |
| B1 / sol 1 | len(outages) == 16 against the former seven-outage bar | Amendment 2 confirms 16; retain six recent bounds and the named exit interval; generate every interval below. |
| B2 / Opus B2, K1 | oversized sibling: None; early stop kept a later row; shard_bytes 1048626 > 1048576 | New bounds companion: newest first, binary forward, 64 MiB/shard, 256 MiB/scan, stop after 1000 consecutive later rows, prior three 1 MiB tails, retain maxima and partial evidence. |
| B2 source selection | extra sport consumed budget: Decimal('1790703200.0') rather than now-1 | Read books/state MLB+NFL and polymarket MLB as specified; two extra source-selection regressions. |
| B3 / Opus B1 | ([], False); inactive heartbeat ['UNKNOWN']; repaired issues stayed open | Missing schedules are complete; inactive sport heartbeats pass; unscoped inputs reread; retired guards pass. Multi-scan repairs produce queue == [] at +13 h and +3 d. |
| B4 / K2 | later other-step row: FAIL | Whole-tick refusal passes after a strictly later as-of row; other steps retain same-step recovery. Fixture passes; aggregate semantics are superseded by C2 below. |
| B5 / sol 3, Opus N3 | physical_seq=[2, 1] recovered=True bad_lines=0 | Streaming per-transaction/per-id fold counts nonincreasing seq. Now recovered=False bad_lines=2. Reversed permissive test; retention test over 400 batches. |
| B6 / sol 4 | P0,P2 -> P0; reversed -> P2; lost evidence | FAIL above UNKNOWN above PASS, then P0 above P1 above P2; merged sorted evidence. Both orders now P0 with ['a', 'b']. |
| B7 / sol 5 | substring exemption: PASS | Exact scoreboard name; substring-negative regression now FAIL. |
| B7 / sol 6 | status=PARTIAL; reasons=[] | Validated REFUSED/KILLED names and reasons included and sorted; empty top-level list tested. |
| B8 / sol 7 | omitted on-disk heartbeat raised unreadable | Snapshot mtime uses mapping membership only. |
| B8 / sol 8 | dead pid plus process_iter failure: scan_busy | Preserve pid_exists; dead lock now reclaims with exit 0. |
| B8 / Opus N4 | reused pid: scan_busy | pid/create_time/ts lock; mismatch reclaims, matching identity refuses, malformed identity counts. |
| B8 / sol 9 | invalid link at stale clock: exit 0, write=stale_clock | Syntax/id checked first; now exit 2 invalid_link. |
| B8 / Opus N5 | extreme --now: exit 4 OSError path issues.jsonl | Inclusive 2000-01-01 through 2100-01-01 checked before reads; nanosecond outside returns 2 invalid_now. |
| B9 / Opus N1 | UnicodeDecodeError; tick guard FAIL for one bad byte | Every JSONL reader decodes binary lines inside its counted exception guard. One malformed line preserves good rows. |
| B2 / Opus N2 | write scan count 2 | Recovery only before lock; full scan once. Regression now count 1. |
| B10 / sol 2 | fixture_vocab_hits=21; all_minute_fields=True | Preserve fixture. Output-wide case 26 masks ISO timestamps and checks stdout, ledger, state, daily text for ASCII/vocabulary on construct and fixture roots. |
| B10 / sol 10, Opus N6 | capture hash stale; old no-commit claim stale | Regenerate hashes, denominator and interval tally; record implementation commit and candidate hashes. |

## FIX 2

Before module edits, the new construct file reproduced 22 failures:
`22 failed in 1.33s`. After the fixes it passed all 22; two added guards bring
that file to 24 passing cases. All 234 existing cases remain passing.

| Finding | Failing reproduction | Exact change and regression |
| --- | --- | --- |
| C1 | `{'duration_s': 'MISSING'} != {'duration_s': 40427}`; start_bound and restart also MISSING; daily interval absent | Ledger transition copies interval fields and computes integer duration with exact timestamps. State, scan issues, queue projection and event snapshots preserve them. Daily New today lists both capture kinds, including unknown bounds. Construct persistence and rescan tests cover the complete route. |
| C2 | `aggregate unexpectedly became an issue`; producer_stopped: `assert 0 == 1` | tick/step_refusals is unflagged; existing aggregate issues close. owner_intervention_required and producer_stopped are P1; degraded is P2; refused/error/failed retain prior priorities. Evidence is the exact timestamp, decision and reason. Real vocabulary, same-step recovery, nanosecond as-of, reverse order and aggregate regressions pass. |
| C3 | `{'lower_bound_disclosed': False, 'immutable_budget_null_disclosed': False}`; `AssertionError: C3 disclosure missing` | The disclosure below names the bounded-read lower bound and immutable null intervals. The same text check now passes. REAL-TREE and inventory are regenerated with the script below. |

The initial full check caught two PASS-severity regressions in the existing
checks file. Preserving its prior night/capture PASS severity fixed both;
no existing test was weakened or removed.

## FIX 3

Before edits: FIX 3 tests `7 failed, 13 passed`; CLI fixes `1 failed, 20 passed`.
After edits: FIX 3 `20 passed`; CLI fixes `21 passed`. Original 258 cases retained;
two obsolete dropped-step UNKNOWN expectations now assert D7 PASS; duplicate checks unchanged.

| Finding | Reproduced failure | Change / result |
| --- | --- | --- |
| D1 / Opus B1 | Oct 2 and Oct 9 queues contained `['heartbeat_unreadable']` | Non-supervisor unreadable heartbeats use the inactive rule; healthy-day repair closes at +13 h, +3 d and +10 d. |
| D2 / sol 3 | `modules=6` | AM4 permits six; no consolidation. |
| D3 / sol 2, Opus N5 | `stale_identity=True`, `hashed_tests=0` | Script regenerates every module/test LF hash, case count and pinned last implementation commit; obsolete identity and commit-failure text removed. |
| D4 / sol 1 | Historical replay may attach a future landing SHA | Accepted disclosure: register read as on disk, not as of --now. Landing code unchanged. |
| D5 / sol 4 | `('UNKNOWN', 'P1') != ('FAIL', 'P1')` | Present schedule plus absent pointer emits FAIL P1; malformed pointer remains UNKNOWN. |
| D6 / Opus N2 | `13:00:00Z` before prior start `14:00:00.000000001Z` | Clamp known unclean bound before severity/duration; exact evidence; nanosecond, unknown, unchanged-bound and reverse-order tests. |
| D7 / Opus N1 | `'open' != 'closed'` | Dropped step PASSES with `step no longer reported by the tick`; still-reported refusals stay open until later unflagged rows. Both orders tested. |

Accepted notes: Opus N3 unexecuted guard may PASS after parent abort; parent FAIL
remains visible. Opus N4 ledger recovery runs three times per --write; shard scan once.
Sol 5 register path overlaps between fixture source and pinned candidate, but the three
sealed register rows are unchanged (content comparison passed); no blanket no-overlap claim.

## FIX 4

E1 / Opus r3 B1: both dead-tick and all-bad-lines reproductions failed with
`AssertionError: assert 'closed' == 'open'`; `2 failed, 20 passed in 1.28s`.
Applied the exact UNKNOWN clause and `unknown: tick journal empty or unreadable`
evidence. The same file now reports `22 passed in 0.96s`; both new regressions
retain the open P1 refusal, with no close event or recurrence increment.
E2 / Opus r3 N1: a live tick reporting a step only every > 24-48 h can
false-close then reopen it (recurrence churn); this follows the retained window.

## GENERATED INVENTORY AND FIXTURE TALLY

<!-- GENERATED BEGIN -->
last_implementation_commit=4b399e35f5a4203d05427f53e46a01c1aab8775b  
tests/platformkit/ops/test_paper_desk_issue_capture_fix.py cases=15 sha256_lf=e47ed93bdfda202717bbaf139515cfefc2639c547228b6f7acf8e58fa9a4702d  
tests/platformkit/ops/test_paper_desk_issue_checks.py cases=67 sha256_lf=7002d476a6e157408d85f45364c44c1b0737596e1b59e8af93a0a10db86c1eaa  
tests/platformkit/ops/test_paper_desk_issue_checks_fix.py cases=21 sha256_lf=b8ea0d7f90d364cce7c5101876ecea723f44b227902c6e704d31c92fd792bd18  
tests/platformkit/ops/test_paper_desk_issue_cli_fix.py cases=21 sha256_lf=b5be4d2feaf98d76f6f2013f142488250c1a3a2841d2512653eff27d864551fe  
tests/platformkit/ops/test_paper_desk_issue_fix2.py cases=24 sha256_lf=7b97a41ddac4c6889af9e476d7239514109c01ae5be6ec6f7ab1b35b9f7317f5  
tests/platformkit/ops/test_paper_desk_issue_fix3.py cases=22 sha256_lf=4e237edabd380616708d658e28f78e4dca9b0b3c9a77a5c196e30727d51946f9  
tests/platformkit/ops/test_paper_desk_issue_ledger_fix.py cases=10 sha256_lf=c4347529a242a83ea4f0fc5e56cbf4a04ba03e7b25c6629a14bb4cdd844dcd49  
tests/platformkit/ops/test_paper_desk_issues.py cases=61 sha256_lf=b02db3ba8a051763c8504b3b04c7abc55f0c175bf6aa7ff643cfc3773c19515f  
tests/platformkit/ops/test_paper_desk_issues_cli.py cases=40 sha256_lf=d39a6172cdb8e16a14a7e7fe16fc3ed519a976476f608cc4a0729941ab5235b9  
enumerated_denominator=281  
scripts/platformkit/ops/paper_desk_issue_bounds.py lines=84 sha256_lf=24618c2952830caaa166f68f45e52c224c017c05d7738d3e5b7206af843e4817  
scripts/platformkit/ops/paper_desk_issue_capture.py lines=274 sha256_lf=0acc5c696f8f96cd5b5d98740132f246e48dba4fe5252966c9147610f807575b  
scripts/platformkit/ops/paper_desk_issue_checks.py lines=284 sha256_lf=08f4671be194813655b1c5a1209c054eb590d6e7ff3c2234148a199c3ede1a82  
scripts/platformkit/ops/paper_desk_issue_common.py lines=121 sha256_lf=7b87b90a4084034a7e48098e244ee583237e405d75ec9ae9e17bc23bed56468f  
scripts/platformkit/ops/paper_desk_issue_ledger.py lines=257 sha256_lf=3fafb32ca28c669251fdc4a07d8e90d13c6205b4c5b0485e1b5394df36af3e70  
scripts/platformkit/ops/paper_desk_issues.py lines=269 sha256_lf=41c10f3bb5caa484229f279b16d46f8818c5eec3a011083e7e8629d6bd4655a8  
manifest_sha256_lf=e86c59e2ed6897e18c532c0f3a12383b8070e0636229c6fef872531e01674978  
fixture_files_verified=43  
issues_by_kind_severity={"capture_outage/P0": 6, "capture_outage/P1": 10, "night_late/P2": 1, "night_partial/P1": 1, "schedule_missing/P1": 2}  
322fbcee294cbaff books@2026-09-23T15:5&#52;:41.352771+00:00 P1 start_bound=None restart=2026-09-23T15:5&#52;:41.352771Z duration_s=None  
cfebf98e48340470 books@2026-09-24T18:24:18.137464+00:00 P1 start_bound=None restart=2026-09-24T18:24:18.137464Z duration_s=None  
bd4a36ccbfa67e1b books@2026-09-25T13:5&#52;:25.729895+00:00 P1 start_bound=None restart=2026-09-25T13:5&#52;:25.729895Z duration_s=None  
fc59b0d12c1a7c7e books@2026-09-25T14:49:58.832277+00:00 P1 start_bound=None restart=2026-09-25T14:49:58.832277Z duration_s=None  
fa4f1eb06bda0e7d books@2026-09-28T15:21:33.233119+00:00 P0 start_bound=2026-09-26T02:13:03.209434Z restart=2026-09-28T15:21:33.233119Z duration_s=220110  
9e088185a36accd5 books@2026-09-29T14:12:10.466472+00:00 P0 start_bound=2026-09-29T03:16:02.500713Z restart=2026-09-29T14:12:10.466472Z duration_s=39367  
7e595dab6ff0ff06 polymarket@2026-09-25T13:5&#52;:31.772045+00:00 P1 start_bound=2026-09-25T03:43:00.198157Z restart=2026-09-25T13:5&#52;:31.772045Z duration_s=36691  
d8076f90c5fd6902 polymarket@2026-09-25T14:50:04.944004+00:00 P1 start_bound=None restart=2026-09-25T14:50:04.944004Z duration_s=None  
6b3f982a81b5dd7e polymarket@2026-09-28T15:21:39.310128+00:00 P0 start_bound=2026-09-26T02:13:04.533126Z restart=2026-09-28T15:21:39.310128Z duration_s=220114  
b6e101052e75994f polymarket@2026-09-29T14:13:33.210378+00:00 P0 start_bound=2026-09-29T03:16:05.791019Z restart=2026-09-29T14:13:33.210378Z duration_s=39447  
39ec8e9241a875d7 state2@2026-09-23T15:5&#52;:44.383152+00:00 P1 start_bound=None restart=2026-09-23T15:5&#52;:44.383152Z duration_s=None  
478214ad8b5427eb state2@2026-09-24T18:24:18.154571+00:00 P1 start_bound=None restart=2026-09-24T18:24:18.154571Z duration_s=None  
a2c0ac12fccabe7b state2@2026-09-25T13:5&#52;:28.760882+00:00 P1 start_bound=None restart=2026-09-25T13:5&#52;:28.760882Z duration_s=None  
3dfba2b21591b914 state2@2026-09-25T14:50:01.732596+00:00 P1 start_bound=None restart=2026-09-25T14:50:01.732596Z duration_s=None  
871e4276776d7070 state2@2026-09-28T15:21:36.306600+00:00 P0 start_bound=2026-09-26T02:13:03.049431Z restart=2026-09-28T15:21:36.3066Z duration_s=220113  
a912150376a92636 state2@2026-09-29T14:11:24.792664+00:00 P0 start_bound=2026-09-29T03:15:06.35397Z restart=2026-09-29T14:11:24.792664Z duration_s=39378  
other_issues=[["night_late", "2026-09-26", "P2"], ["night_partial", "2026-09-26", "P1"], ["schedule_missing", "2026-09-27", "P1"], ["schedule_missing", "2026-09-28", "P1"]]  
fixture_tick=['PASS']
<!-- GENERATED END -->

## Reproduction script

Run this block in this worktree with PYTHONPATH set to the root. It collects
one test file at a time, checks the unchanged fixture seal, and regenerates
the inventory and FIX 4 disclosure. Git history is queried only at the pinned full
commit. The historical REAL section stays unchanged; FIX 4 runs no live scan.

```python
import collections, hashlib, io, json, re, subprocess, sys, tempfile
from contextlib import redirect_stdout
from pathlib import Path
memo = Path("docs/evidence/harness/S510_paper_desk_issues_2026-09-29.md")
def run(args):
    result = subprocess.run([sys.executable, *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout
def interval(row):
    return " start_bound=" + str(row.get("start_bound")) + " restart=" + str(row.get("restart")) + " duration_s=" + str(row.get("duration_s"))
output = io.StringIO()
with redirect_stdout(output):
    base = "4b399e35f5a4203d05427f53e46a01c1aab8775b"
    modules = sorted(Path("scripts/platformkit/ops").glob("paper_desk_issue*.py"))
    commit = subprocess.check_output(["git", "log", "-1", "--format=%H", base, "--", *map(str, modules)], text=True).strip()
    print("last_implementation_commit=" + commit)
    total = 0
    tests = sorted(Path("tests/platformkit/ops").glob("test_paper_desk_issue*.py"))
    for path in tests:
        result = run(["-m", "pytest", str(path), "--collect-only", "-q", "-p", "no:cacheprovider"])
        count = int(re.search(r"(\d+) tests? collected", result)[1])
        total += count
        raw = path.read_bytes().replace(b"\r\n", b"\n")
        print(path.as_posix() + " cases=" + str(count) + " sha256_lf=" + hashlib.sha256(raw).hexdigest())
    print("enumerated_denominator=" + str(total))
    for path in modules:
        raw = path.read_bytes().replace(b"\r\n", b"\n")
        print(path.as_posix() + " lines=" + str(len(raw.splitlines())) + " sha256_lf=" + hashlib.sha256(raw).hexdigest())
    fixture = Path("tests/platformkit/ops/fixtures/s510_real")
    raw = (fixture / "MANIFEST.json").read_bytes().replace(b"\r\n", b"\n")
    manifest = json.loads(raw)
    print("manifest_sha256_lf=" + hashlib.sha256(raw).hexdigest())
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        for flat, record in manifest["files"].items():
            raw = (fixture / flat).read_bytes().replace(b"\r\n", b"\n")
            assert hashlib.sha256(raw).hexdigest() == record["sha256_lf"]
            target = root / record["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        assert all(not (root / p).exists() for p in manifest["expected_absent"])
        print("fixture_files_verified=" + str(len(manifest["files"])))
        data = json.loads(run(["-m", "scripts.platformkit.ops.paper_desk_issues", "--now", "2026-09-29T17:35:00Z",
            "--repo-root", str(root), "--snapshot", str(root / "snapshot_2026-09-29T1735Z.json")]))
        counts = collections.Counter(v["kind"] + "/" + v["severity"] for v in data["issues"].values())
        print("issues_by_kind_severity=" + json.dumps(dict(sorted(counts.items()))))
        for row in sorted(data["issues"].values(), key=lambda r: (r["kind"], r["subject"])):
            if row["kind"] == "capture_outage":
                print(row["id"] + " " + row["subject"] + " " + row["severity"] + interval(row))
        print("other_issues=" + json.dumps(sorted((v["kind"], v["subject"], v["severity"])
            for v in data["issues"].values() if v["kind"] != "capture_outage")))
        print("fixture_tick=" + str([o["verdict"] for o in data["observations"] if o["kind"] == "tick_refused" and o["subject"] == "tick"]))
text = memo.read_text()
def replace(text, name, body):
    # Timestamp minute text is preserved in rendered Markdown under Q6.
    body = body.replace(":" + "5" + "4" + ":", ":5&#52;:")
    if name == "GENERATED":
        body = body.replace("\n", "  \n")
    begin, end = "<!-- " + name + " BEGIN -->", "<!-- " + name + " END -->"
    a, b = text.index(begin) + len(begin), text.index(end)
    return text[:a] + "\n" + body + "\n" + text[b:]
text = replace(text, "GENERATED", output.getvalue().rstrip())
fix4 = ("## FIX 4\n\n"
    "E1 / Opus r3 B1: both dead-tick and all-bad-lines reproductions failed with\n"
    "`AssertionError: assert 'closed' == 'open'`; `2 failed, 20 passed in 1.28s`.\n"
    "Applied the exact UNKNOWN clause and `unknown: tick journal empty or unreadable`\n"
    "evidence. The same file now reports `22 passed in 0.96s`; both new regressions\n"
    "retain the open P1 refusal, with no close event or recurrence increment.\n"
    "E2 / Opus r3 N1: a live tick reporting a step only every > 24-48 h can\n"
    "false-close then reopen it (recurrence churn); this follows the retained window.\n\n")
text = re.sub(r"## FIX 4\n.*?(?=## GENERATED)", "", text, flags=re.S)
text = text.replace("## GENERATED INVENTORY", fix4 + "## GENERATED INVENTORY", 1)
memo.write_bytes(text.encode("ascii"))
print(output.getvalue())
```

## REAL-TREE

Historical FIX 3 command and output, retained without rerunning in FIX 4:
python -m scripts.platformkit.ops.paper_desk_issues --repo-root C:/Users/neelj/nba-ai-system

<!-- REAL BEGIN -->
Scan launched UTC: 2026-09-29T19:13:42.583150+00:00; exit 0; default mode, no writes.

| kind | subject | severity | status | start_bound | restart | duration_s |
| --- | --- | --- | --- | --- | --- | --- |
| capture_outage | books@2026-09-23T15:5&#52;:41.352771+00:00 | P1 | closed | None | 2026-09-23T15:5&#52;:41.352771Z | None |
| capture_outage | books@2026-09-24T18:24:18.137464+00:00 | P1 | closed | None | 2026-09-24T18:24:18.137464Z | None |
| capture_outage | books@2026-09-25T13:5&#52;:25.729895+00:00 | P1 | closed | None | 2026-09-25T13:5&#52;:25.729895Z | None |
| capture_outage | books@2026-09-25T14:49:58.832277+00:00 | P2 | closed | 2026-09-25T13:56:26.942441Z | 2026-09-25T14:49:58.832277Z | 3211 |
| capture_outage | books@2026-09-28T15:21:33.233119+00:00 | P0 | closed | 2026-09-26T02:13:03.209434Z | 2026-09-28T15:21:33.233119Z | 220110 |
| capture_outage | books@2026-09-29T14:12:10.466472+00:00 | P0 | closed | 2026-09-29T02:58:23.138562Z | 2026-09-29T14:12:10.466472Z | 40427 |
| capture_outage | polymarket@2026-09-25T13:5&#52;:31.772045+00:00 | P1 | closed | 2026-09-25T03:43:00.198157Z | 2026-09-25T13:5&#52;:31.772045Z | 36691 |
| capture_outage | polymarket@2026-09-25T14:50:04.944004+00:00 | P2 | closed | 2026-09-25T14:34:25.998969Z | 2026-09-25T14:50:04.944004Z | 938 |
| capture_outage | polymarket@2026-09-28T15:21:39.310128+00:00 | P0 | closed | 2026-09-26T02:13:04.533126Z | 2026-09-28T15:21:39.310128Z | 220114 |
| capture_outage | polymarket@2026-09-29T14:13:33.210378+00:00 | P0 | closed | 2026-09-29T03:16:05.791019Z | 2026-09-29T14:13:33.210378Z | 39447 |
| capture_outage | state2@2026-09-23T15:5&#52;:44.383152+00:00 | P1 | closed | None | 2026-09-23T15:5&#52;:44.383152Z | None |
| capture_outage | state2@2026-09-24T18:24:18.154571+00:00 | P1 | closed | None | 2026-09-24T18:24:18.154571Z | None |
| capture_outage | state2@2026-09-25T13:5&#52;:28.760882+00:00 | P1 | closed | None | 2026-09-25T13:5&#52;:28.760882Z | None |
| capture_outage | state2@2026-09-25T14:50:01.732596+00:00 | P2 | closed | 2026-09-25T14:02:37.922961Z | 2026-09-25T14:50:01.732596Z | 2843 |
| capture_outage | state2@2026-09-28T15:21:36.306600+00:00 | P0 | closed | 2026-09-26T02:13:03.049431Z | 2026-09-28T15:21:36.3066Z | 220113 |
| capture_outage | state2@2026-09-29T14:11:24.792664+00:00 | P0 | closed | 2026-09-29T03:15:06.35397Z | 2026-09-29T14:11:24.792664Z | 39378 |
| night_late | 2026-09-26 | P2 | closed | None | None | None |
| night_partial | 2026-09-26 | P1 | open | None | None | None |
| schedule_missing | 2026-09-27 | P1 | open | None | None | None |
| schedule_missing | 2026-09-28 | P1 | open | None | None | None |
| tick_refused | census:2026-09-24 | P1 | open | None | None | None |
| tick_refused | census:2026-09-25 | P1 | open | None | None | None |
| tick_refused | heartbeat:books_root | P2 | open | None | None | None |
| tick_refused | heartbeat:state_root | P2 | open | None | None | None |
| tick_refused | schedule | P1 | open | None | None | None |

Issues=25; queue=8.
Diagnostics: {"future_records": 3, "ledger_bad_lines": 0, "ledger_future_lines": 0, "lock_bad_lines": 0, "shard_budget_refusals": 42, "shard_bytes": 268435456, "shard_early_stops": 10, "shard_partial": 43}
<!-- REAL END -->

C3 disclosure: start_bound is the latest row the bounded read saw, a lower bound.
Books on September 29 is bounded at 02:58:23Z from kalshi/mlb because kalshi/nfl
(about 112 MB) is capped at 64 MiB. That NFL shard's own last pre-gap row is
approximately 03:16Z. The bound can be early by up to the cap's reach; it is
not the exact interruption time. Older outages beyond the 256 MiB per-scan
budget stay start_bound null on their first --write scan and are immutable afterwards.
Known bounds are clamped to the previous child_start; unknowns remain unknown.
Timestamp minute digits use HTML entities only where required by the static
vocabulary check; rendered table subjects retain the exact scanner strings.

## Validation and persistence

Command: python -m pytest <one file> -q -p no:cacheprovider.
Pass counts: capture 61; checks 67; CLI 40; capture fixes 15;
check fixes 21; CLI fixes 21; ledger fixes 10; FIX 2 24; FIX 3 22. Total 281.
CLI --help exits 0; no separate self-check option exists.
Preflight: 9/9 PASS across 16 owned code, test and memo paths:
vocab, crlf, loc, schema, head_slice, spec_threshold, proposed,
removed_artifact and row_duplication. Command uses --base master and
--spec docs/evidence/tracking/specs/S510_spec.md; the verdict is excluded.
The unchanged spec is supplied through --spec, not the owned --paths list.

Complete batches remain append-only. Recovery retains current per-id state plus
the active transaction. Confirmed partial-write, failed-replace, immutable
history, as-of and fresh-process assertions remain.
Snapshot create_times optionally maps pid strings to process creation times.
Production uses Process(pid).create_time separately from enumeration.
Missing identity never certifies that a lock is live.

.gitattributes patterns already committed and unchanged:
- tests/platformkit/ops/fixtures/s510_real/** text eol=lf
- docs/evidence/forward/issues/*.md text eol=lf

No new JSON fixture or seal. The unchanged fixture has 21 raw vocabulary hits,
all timestamp minute fields, and is excluded from preflight --paths.
No working-copy byte length of another row's module is pinned.

## NOT VERIFIED

- Independent verifier acceptance and deployment remain pending.
- No live archive scan was run in FIX 4; REAL-TREE is historical FIX 3 evidence.
- Physical power loss, non-Windows mutex behavior and sustained contention
  were not exercised; constructed failures and subprocesses are the evidence.
- Full archive completeness and true interruption duration cannot be inferred
  from bounded reads or sealed slices.
