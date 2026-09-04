GAP G276b | sport wnba | worktree a5 | log g276b_unconditioned_step_endpoint_baseline
**READ `docs/evidence/tracking/specs/G276_spec.md` IN FULL AND FOLLOW IT EXACTLY. This file changes ONE
thing: it says WHERE the row runs.** Every other requirement in G276 -- the population match, the
sampling, the pooled blind order that hides the pairing, the four categories, the 2x2 joint table, the
restated comparison, the limitations, the ledger row -- **applies unchanged.**

**WHY THIS RE-ISSUE EXISTS -- MY SPEC ERROR, AND THE LANE WAS RIGHT TO STOP.**
G276 made `du -sm /workspace` and a `dd conv=fsync` probe **mandatory stop conditions**, but **never said
the row runs on the pod.** The lane ran in the local Windows worktree, where `/workspace` does not exist,
both commands failed, and **it correctly stopped without creating crops, artifacts, memo, ledger row or
commit.** That is exactly the behaviour the stop condition is for. **This is the same fault as G256** -- a
spec that names a pod path without saying it is a pod path -- and it is mine, not the lane's.

**WHERE THIS ROW RUNS -- READ THIS BEFORE ANYTHING ELSE.**
  - **The ANALYSIS is local.** G267's retained records are committed in this worktree under
    `docs/evidence/tracking/`. Reading them, building the eligible-step population, sampling, and all
    arithmetic happen **in the local worktree, with no pod involved.**
  - **The RENDER is on the pod, because the full-resolution source video is only there.** Ship and run it
    with **`~/bin/pod_run a5 --ship <the harness files you need> --fetch <the crops you want back> --
    <your command>`**, exactly as G272b and G273 did. It ships this worktree's code tree to
    `/workspace/wt/a5`, runs the command there under nohup, and fetches the listed paths back. **It never
    writes the deployed tree `/workspace/nba-ai-system`.** Per the VERIFIER_CONTRACT B5 note of
    2026-09-04 09:35, heavy compute MAY run on the pod before ACCEPT as a compute-only run in that
    per-worktree scratch directory.
  - **THE DISK GUARD APPLIES TO THE POD SIDE ONLY.** Run `du -sm /workspace` and the `dd conv=fsync` probe
    **on the pod, inside the `pod_run` command**, never in the local checkout. **If you find yourself
    running the guard locally and `/workspace` is missing, you are in the wrong place -- that is a signal
    to move the step to `pod_run`, not to stop.**
  - **STOP only if the guard fails ON THE POD.** A missing `/workspace` locally is not a disk failure.

**Everything else is G276's**, and in particular these, which decide whether the row is any good:
  - **MATCH G272b's POPULATION EXACTLY EXCEPT DROP THE 40 ft/s CONDITION.** State the eligible-step count;
    it is **NOT** G272b's 2,507, which was already speed-conditioned. **Name any other filter that
    differs.**
  - **POOL BOTH ENDPOINTS OF EVERY STEP INTO ONE RANDOMISED BLIND ORDER so the labeller never knows which
    two crops belong to the same step**, and **commit the order and verdicts before un-blinding.** If the
    pairing is visible, the measured correlation is an artifact of the presentation, not of the tracker.
    **Say in the memo how the pairing was hidden.**
  - **Do NOT re-detect or re-associate** -- the detector is non-deterministic (G241: 808 of 1,201 records
    differed on an exact re-run) and a fresh pass breaks comparability with the whole chain.
  - **Report the 2x2 joint table**, then the per-crop non-person rate, the one-or-both rate, the endpoint
    correlation, and where the observed rate falls inside
    `[per-crop rate, 1 - (1 - per-crop rate)^2]`. **Handle CANNOT JUDGE explicitly and give the figures
    both including and excluding it.**
  - **If the measured baseline reaches or exceeds 0.500, say bluntly that G272b's jump steps are NOT
    enriched in non-people and that my bracket row's conclusion was wrong.** That is a full success and I
    want it stated plainly, not softened.
  - **Assert NO causation in either direction.** **The population is detector boxes, not authenticated
    players** -- name the denominator. **A per-crop rate differing from G273's 0.208 is sampling
    variation, NOT a change in the detector.**

**HOLD RULE, unchanged: count DISTINCT lane worktrees, not python PIDs.** One lane shows two python PIDs
sharing one `cwd` (G274 verified this for `/workspace/wt/a17`). Reduce to the SET of distinct
`/workspace/wt/a*` directories and compare THAT to 2. Exclude your own process, your checker and its
parent. **Report the set you observed.**

**DISK GUARD, POD SIDE:** `df` is NON-AUTHORITATIVE. `du -sm /workspace` was about **40,069 MB at
2026-09-04 12:35**, roughly **9.7 GB free** against the 50 GB quota, and **a peer session writes under
`/workspace/wt`.** **Re-measure yourself.** **Crops are the bulk -- keep them modest and report committed
bytes.** **Do NOT delete any corpus source, and do NOT delete the two abandoned bridge partials
(`baseball__npb_05.mp4.part` 2.4 GB, `football__football_m8UWuQoflJo.mp4.part` 4.7 GB): they are resumable
acquisitions and the football one is the only football footage in the programme.** Report bytes freed.

ACCEPTANCE RULE, EVIDENCE, TEST and COMMIT: **as in G276_spec.md**, with the memo at
`docs/evidence/tracking/g276b_unconditioned_step_endpoint_baseline_2026-09-04.md` and **a statement of
where each step ran, local or pod,** added to the required evidence. **ADD A RESULTS_LEDGER.md ROW IN THE
SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7). Explicit pathspec, no push, report the sha.
Per-file tests only, never a full pytest. ASCII stdout. **NEVER PARK.**
