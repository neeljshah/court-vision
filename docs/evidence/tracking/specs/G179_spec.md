GAP G179 | sport all | worktree a5 | log cx_g179_evaluated_denominator_arith
**EVERY BAR VALUE STAYS BYTE-IDENTICAL. This row corrects a DENOMINATOR, never a threshold.** Editing
any `coverage_min` or other bar is an automatic REJECT under B10/Q3.

CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read in full (A5, A7, B2, B3, B10, Q3, Q7,
Q8); self-check section B. ORCHESTRATOR-OWNED change, adjudicated 2026-09-03 over two rounds.

WHY, AND WHAT THE PREVIOUS ATTEMPT ESTABLISHED (read
`docs/evidence/tracking/g178_evaluated_denominator_blocked_2026-09-03.md` first; do not re-derive):
  - Coverage has a strided numerator over an unstrided denominator, capping it at 1/stride (G177).
  - **G178 STOPPED correctly**: the manifest route is unavailable. 21 tracked CSV jobs on the pod,
    exactly **1** `frame_manifest.csv`. Do NOT retry that mechanism.
  - The arithmetic route needs only `source_fps` and `decoded_frames`, both already on every ledger
    row: `stride = round(fps*0.1)` (`tracking_timebase.py:30-37`), `evaluated = ceil(decoded/stride)`.
    It reproduces tennis at 726/9,591 = **0.0757** against an expected 0.0756.
  - **THE BLOCKER YOU MUST SOLVE: `adapter_run.py:81` defaults `--max-frames` to 30000.**
    `tennis_ref01` decodes 28,773 (under the cap, fine). `mlb_...10893dca` decodes **39,035 (over)**,
    so its run was truncated and `ceil(decoded/stride)` OVERSTATES what was evaluated -- the implied
    ~6,109 emitting frames over a truncation-aware ~5,000 evaluated exceeds 1.0, which is impossible.

DO THIS, in order:
  (a) **Establish from QUOTED CODE exactly what `max_frames` caps** -- source frames read, evaluated
      frames, or emitted rows. Follow it into the adapter's loop. This is the whole row; get it wrong
      and every number after it is wrong. Q8: quote, do not infer.
  (b) Derive the correct evaluated count as a function of `decoded_frames`, `source_fps` and
      `max_frames`. Show the formula and its derivation. Sanity-bound it: coverage on evaluated frames
      **must lie in [0, 1]** for every row. **If any row exceeds 1.0, your formula is wrong -- do not
      clamp it, fix it.**
  (c) Cross-check against the ONE surviving `frame_manifest.csv`: does your formula reproduce that
      job's actual evaluated count? Report agreement or disagreement. Disagreement is a finding and
      must stop the landing.
  (d) Also check whether `decoded_frames` itself already reflects truncation rather than the full
      file. If it does, the arithmetic changes again. State which it is, from evidence.
  (e) ONLY when (a)-(d) hold: land the change. `_with_decoded_denominator` in `track_daemon_done.py`
      pads to `range(decoded)`; pad to the EVALUATED set instead. Persist the GATING quantity as a
      NEW ledger field (G164's open item -- the number deciding `passed` is currently discarded) and
      add a declared `stride` field so sampling cost is visible. **Do NOT rename or repurpose the
      existing `coverage_pct` field** (B2).
  (f) Before/after table for every reachable ledger row, from artefacts on the pod. **NO row is
      expected to flip FAIL to PASS** -- baseball fails at `coordinate_contract` before coverage is
      evaluated (G176), so this is NOT a baseball rescue. If a row flips, report it as a finding.

DO NOT change any bar, `min_players`, the eligibility definition, the coordinate contract, `src/`
(human-gated), or any verdict. Do not rename or remove a ledger field. Do not restart or kill the pod
daemon; the orchestrator deploys after ACCEPT (B5).

ACCEPTANCE RULE:
  metric        = the quoted `max_frames` semantics; the derived evaluated-count formula with every
                  row's coverage in [0,1]; agreement against the one real manifest; the before/after
                  table; a diff proving every bar byte-identical
  before        = coverage capped at 1/stride; the gating quantity discarded; the naive arithmetic
                  producing an impossible >1.0 on over-cap rows
  bar           = NO pass bar. "The semantics cannot be pinned down from the code, so landing this
                  would be guessing" is a FULL SUCCESS -- report it and stop, as G178 correctly did.
  n             = every reachable ledger row (CONSTRUCT, exhaustive); name any excluded and why
  eye check     = replaced by REPRODUCTION (Q7): the before/after table recomputed from artefacts
  must not move = every bar, min_players, the eligibility definition, the coordinate contract, every
                  existing ledger field name, `src/`, every verdict
EVIDENCE: docs/evidence/tracking/g179_evaluated_denominator_arith_2026-09-03.md with the quoted
semantics, the formula, the manifest cross-check, the before/after table, the unchanged-bars diff, and
a NOT VERIFIED list. **COMMIT THE MEMO BEFORE YOU REPORT (A7)** -- two lanes today produced complete
work, exited 0 and committed nothing, so an EXIT:0 is not evidence of a commit.
TEST: your new per-file test plus `test_track_daemon_done.py`, `test_track_daemon.py` and
`test_track_daemon_ledger_denominator.py`; paste all results. Running only your own file caused a
REJECT today. NEVER a full pytest.
POD: READ-ONLY and BATCHED. Never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, in a5, no push. Report the sha and the before/after table.
NEVER PARK. Never paste a credential-shaped string into a memo, even a fake fixture -- describe it.
