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

| private/cloud/S658-2026-09-30 | LAND AFTER FIX | none | Fast successful producer becomes an error | S |
LANDING ORDER: S631, S594, corrected S653-S656 fix, corrected S641 fix after re-verification, corrected S659 after re-verification, then corrected S690. Corrected S658 and S646 remain parked until their respective landing conditions are satisfied.
