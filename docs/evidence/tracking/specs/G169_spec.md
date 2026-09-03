GAP G169 | sport tennis | worktree a3 | log cx_g169_emitted_frame_nondeterminism
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A2, A7 and Q8; self-check
section B before reporting. Move no threshold, no bar, no verdict.

THE ANOMALY, flagged in G162's memo and deliberately left unexplained there. Two runs of what should
be the SAME source clip produced very different output:

  - **G152b**, local, on `data/videos/reference/tennis.mp4`: **28,773 decoded frames, 6,770 emitted
    rows over 2,597 distinct emitted frames.**
  - **`tennis_smoke`**, on the pod, from the same reference clip: **1,861 rows over 726 distinct
    emitted frames** (1,430 of those rows players, 586 distinct player track ids).

That is a **3.6x difference in distinct emitted frames** on nominally the same input. G162 named it
and did not chase it. It has to be chased now, because **if the tracker is nondeterministic, every
measurement in this program that compares one run against another is unsound** -- including G161's
rally normalisation, G152b's declaration and geometry rates, and any before/after claim about the
adapter. This row is a premise check on the whole measurement stack, which is why it outranks another
feature measurement.

RESOLVE IT. The candidate explanations, to be confirmed or eliminated by evidence, not by preference:
  (a) **Different input.** Is the pod's copy of the clip byte-identical to the local one? Compare
      sizes and hashes. The pod file was uploaded by the orchestrator by scp as
      `data/videos/tennis_smoke.mp4`. If they differ, that is the whole answer and the row closes.
  (b) **Different frame budget.** Does the pod path cap frames -- an adapter argument, a `--frames`
      default, an environment variable, a section cut? `scripts/platformkit/adapter_run.py` was the
      entry point on the pod. Quote what it passes.
  (c) **Different decode.** cv2 versions differ between local and pod (a landed memo records local
      cv2 4.11 against pod cv2 4.14, and warns that comparing runs across environments once invented
      a defect that did not exist). Report both versions and say whether decode counts differ.
  (d) **Genuine nondeterminism.** Only if (a)-(c) are eliminated: run the SAME clip twice in the SAME
      environment and compare distinct emitted frames. Two identical runs prove determinism for that
      environment; two differing runs prove the opposite and are the most important result available
      here.
  (e) State which explanation holds, with the evidence for it. "Different input" and "different frame
      budget" are boring answers and both are FULL SUCCESSES -- boring is the outcome to hope for.

THEN, and this is what makes the row worth running either way: **say explicitly which landed results
would be affected if the answer were nondeterminism, and which would not.** Name them by gap id. If
the answer is benign, that list is short and the row ends by REASSURING the register rather than
disturbing it. Do not quietly drop this part because the answer turned out boring.

DO NOT change the adapter, the harness, any threshold, the coordinate contract, or any verdict. Do
not re-track into the shared store; use a scratch game id you name in the memo.

ACCEPTANCE RULE:
  metric        = hash and size comparison of the two inputs; the frame budget quoted from the entry
                  point; both cv2 versions; and, only if needed, distinct emitted frames from two
                  same-environment runs
  before        = a 3.6x discrepancy in distinct emitted frames on nominally the same clip, unexplained
  bar           = NO pass bar. Success is the discrepancy explained with evidence, plus the named list
                  of results that would have been affected under the nondeterminism branch.
  n             = 2 runs minimum for branch (d); state the environment of each (CONSTRUCT)
  eye check     = replaced by REPRODUCTION (Q7): quote every command with its raw output
  must not move = the adapter, the harness, every threshold, the coordinate contract, every verdict
EVIDENCE: docs/evidence/tracking/g169_emitted_frame_nondeterminism_2026-09-03.md with the hash
comparison, the quoted frame budget, both cv2 versions, the resolution, the affected-results list,
and a NOT VERIFIED list. Commit BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: READ-ONLY and BATCHED for inspection. If you need a second tracking run, RUN IT ON THE POD under
nohup with a log and collect it in one batched ssh -- a local decode was killed by the machine's RAM
guard at 1.4 GB today. NEVER kill, restart or deploy over the running daemon or its keeper.
COMMIT: explicit pathspec only, in a3, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
