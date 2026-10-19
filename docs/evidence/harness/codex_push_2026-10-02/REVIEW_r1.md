Three branch tips need HOLD, three need fixes, and two have no defect found. This was a static, read-only review; no tests or network calls were run.

All eight diffs are nonempty. The requested reverse diffs found no master changes since the merge bases in any touched path. References below are to files at each branch tip.

**S659-2026-09-30: HOLD**

- False heartbeat proof: `scripts/platformkit/ops/recorder_adopt_rules.py:179` checks whether supervisor PID changed, but never validates that a supervisor PID exists. A fresh heartbeat containing only a new, live `child_pid` passes at `:184`, allowing pending adoption to be cleared without proof of a new supervisor.
  - Fix: before the comparison loop, reject unless `type(beat.get("pid")) is int` and `beat["pid"] > 0`. Add constructs for missing, null, boolean and nonpositive supervisor PIDs.
  - Test gap: `tests/platformkit/ops/test_recorder_adopt_rules.py:73` tests child-PID validity and unchanged PIDs, but misses invalid supervisor PIDs.
- Windows replacement: `scripts/platformkit/ops/recorder_adopt.py:75` calls `Path.replace` directly on the durable retry state.
  - Fix: import `replace_with_retry` from `scripts.platformkit.ops.atomic_replace`; replace that call with `replace_with_retry(tmp, path, durable=True)`.
- Fixture portability: `tests/platformkit/ops/recorder_adopt_fixture.py:84` uses `write_text`, which translates LF to CRLF on Windows; its git runner at `:24` does not isolate autocrlf.
  - Fix: write fixture bodies with `write_bytes(body.encode("utf-8"))`, and give the fixture git runner `-c core.autocrlf=false`. Write its shell hook as bytes too.
- Operational limitation remains: no committed relaunch script qualifies, as disclosed in `docs/evidence/harness/S659_cloud_result_2026-09-30.md:95`. Landing this implementation alone does not complete capture adoption.

**S690-2026-09-30: HOLD**

This tip contains S659, including its false-proof defect and pending-state replacement. Preserve those corrections when landing S690.

- Push confirmation has an equality race: `scripts/platformkit/ops/evidence_allowlist_push.py:181` recognizes a completed push only when the remote tip equals local HEAD. If the push lands, another commit arrives, and the original push reports a timeout, confirmation fails and `:174` undoes an already-published commit. Subsequent publication can stall on overlapping paths.
  - Exact replacement inside `_landed`, retaining its exception handler:

    ```python
    tip = fetch(root, remote, branch)
    return git(root, "merge-base", "--is-ancestor", "HEAD", tip).returncode == 0
    ```

  - Test gap: `tests/platformkit/ops/test_evidence_allowlist_push_corrections.py:119` covers landed-then-timeout, but not a remote successor arriving before confirmation.
- Windows acceptance fixture hashes different bytes from those it writes: `tests/platformkit/ops/test_recorder_adopt_evidence.py:36` hashes LF text, then `:38` writes through the CRLF-translating S659 fixture. The byte-write correction above fixes this.
- Must land after corrected S659; the dependency is explicit in `docs/evidence/harness/S690_cloud_result_2026-09-30.md:3`.

**S658-2026-09-30: LAND AFTER FIX**

- Fast successful producers can be reported as failures. `scripts/platformkit/ops/desk_posix.py:51` rejects zombie identity; `scripts/platformkit/ops/paper_desk_process.py:172` therefore observes no owner. The already-exited success path at `:175` accepts only a child without a job, so a normal POSIX job raises `child_identity_unobservable`.
  - Make these changes while preserving the Windows path:

    ```python
    pids = job.pids() if isinstance(job, PosixJob) else [child.pid]
    marker["owners"], _ = _owners(pids, process, row)
    # Replace the existing already-exited condition:
    if child.poll() is not None and (
        not job or (isinstance(job, PosixJob) and not job.pids())
    ):
    ```

- Test gap: `tests/platformkit/ops/test_paper_desk_job_posix.py:134` launches an immediate-exit child but does not force exit before identity observation. Add a deterministic delayed-observation case and a surviving-grandchild cleanup case.
- Keep adoption subject to the existing park/platform conditions in `docs/evidence/harness/S658_spec_2026-09-30.md:4`.

**S594-2026-09-30: LAND**

No additional defect found. The constructs check actual cadence, archive rows and retry behavior.

The historical comparison uses a fixed SHA, but can skip when its blob is unavailable: `tests/platformkit/ingame/s594_lane_fixture.py:174`. That limitation is disclosed at `docs/evidence/harness/S594_cloud_result_2026-09-30.md:135`; it is not a moving-ref comparison.

**S631-2026-09-30: LAND**

`scripts/platformkit/improve/prop_line_distance_calib.py:222` correctly distinguishes `None` from an empty iterable. The empty-list construct calls production logic with nonempty input at `tests/platformkit/improve/test_prop_line_distance_calib_s631.py:25`.

The existing module remains 374 lines, already covered by `tests/platformkit/test_loc_rail_scope.py:57`; this branch does not grow it.

**S641-fix-2026-09-30: HOLD**

- Unreadable undated parquet can still appear fresh. `scripts/platformkit/mcp_server/served_asof.py:105` reads only the schema; `:107` returns immediately without reading data pages when `date` is absent. A readable footer with corrupt data pages reaches the mtime fallback at `:162`.
- This violates the readable-undated requirement in `docs/evidence/harness/S641_fix_spec_2026-09-30.md:10`.
  - Fix: insert `pq.read_table(path)` immediately before the no-date return at `served_asof.py:107`.
  - Add an undated-input construct where schema reading succeeds and table reading raises; assert `input_unreadable` and unknown as-of.
- Test gap: `tests/platformkit/mcp_server/test_served_asof_s641_fix.py:100` injects only schema failure; `:105` tests a readable undated fixture.

**S653-S656-fix-2026-09-30: LAND AFTER FIX**

- Linux-only behavior tests run on Windows whenever pwsh exists. Their fixture uses a shell script and `/proc`, while teardown calls `signal.SIGKILL` at `tests/platformkit/ops/test_s653_s656_cloud_scripts.py:198`. The decorators at `:203` and `:209` check only pwsh availability.
  - Add `import sys` and this decorator to both behavior tests:

    ```python
    @pytest.mark.skipif(
        sys.platform != "linux", reason="Linux shell and /proc fixture"
    )
    ```

  - Keep the AST/proxy tests enabled on Windows.
- `.gitattributes:72` appends three LF rules. Preserve all three during cherry-pick conflict resolution. The byte assertion at `tests/platformkit/ops/test_s653_s656_cloud_scripts.py:229` targets those pinned files.

**S646-2026-09-30: LAND AFTER FIX; retain PARKED status**

- Bare replacements remain at `scripts/platformkit/execution/markout_predict_r1_io.py:276` and `scripts/platformkit/execution/markout_predict_r1_stats.py:51`.
  - At each site, import `replace_with_retry` and replace the call with `replace_with_retry(Path(tmp), path, durable=True)`.
- The new constructs exercise replay, statistical boundaries and verdict logic. No moving-ref or checkout-file CRLF byte comparison found.
- The branch bundles its S643 implementation; no separate S643 landing is required. The seal and first scored look remain reserved for the laptop lane at `docs/evidence/harness/S646_cloud_result_2026-09-30.md:73`.

No additional seal-pinned edits, registry writes, enabled production flags, schema/evidence removals, secret-like literals or prohibited claims were found.

| branch | verdict | must-land-after | top defect | fix size (S/M/L) |
|---|---|---|---|---|
| private/cloud/S659-2026-09-30 | HOLD | none | Invalid supervisor PID passes heartbeat proof | S |
| private/cloud/S690-2026-09-30 | HOLD | corrected S659 | Inherited false proof; push-confirmation race | S |
| private/cloud/S658-2026-09-30 | LAND AFTER FIX | none | Fast successful producer becomes an error | S |
| private/cloud/S594-2026-09-30 | LAND | none | None found | - |
| private/cloud/S631-2026-09-30 | LAND | none | None found | - |
| private/cloud/S641-fix-2026-09-30 | HOLD | none | Unreadable undated input appears fresh | S |
| private/cloud/S653-S656-fix-2026-09-30 | LAND AFTER FIX | none | Linux fixtures run on Windows | S |
| private/cloud/S646-2026-09-30 | LAND AFTER FIX | none | Bare atomic replacements | S |

LANDING ORDER: S631, S594, corrected S653-S656 fix, corrected S641 fix after re-verification, corrected S659 after re-verification, then corrected S690. Corrected S658 and S646 remain parked until their respective landing conditions are satisfied.