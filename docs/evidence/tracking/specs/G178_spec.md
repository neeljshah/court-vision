GAP G178 | sport all | worktree TBD | log cx_g178_evaluated_denominator
**EVERY BAR VALUE STAYS BYTE-IDENTICAL. This row corrects a DENOMINATOR, never a threshold.** If you
find yourself editing a number in `SPORTS[...]["coverage_min"]` or any other bar, stop -- that is an
automatic REJECT under B10/Q3 and it is the exact failure that forced a retraction in this program.

CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it in full, especially A5, A7, B2, B3,
B10 and Q3. Self-check section B before reporting. This is an ORCHESTRATOR-OWNED change, adjudicated
2026-09-03 after two rounds with Fable; it is not a lane's judgement call to widen or narrow.

WHY (all landed, do not re-derive):
  - **G177**: the daemon strides the numerator and not the denominator. `TARGET_SAMPLE_SECONDS = 0.1`
    (`tracking_timebase.py:13`), `stride = round(fps*0.1)` (`:30-37`), passed in at
    `adapter_run.py:100-101`; `adapter.py:223` evaluates only `source_frame % stride == 0` and `:242`
    marks the rest `skipped_stride`; `decode_manifest.decoded_frame_count` counts every decoded frame.
    Coverage is therefore capped at 1/stride -- 0.1667 at 59.94 fps, 0.3333 at 29.97.
  - **Twelve baseball ledger rows sit at 89.9-96.4 pct of that ceiling** (0.1499-0.1607 against
    0.1667). The tracker solves nearly every frame it is handed.
  - **CORRECTION you must carry (G176): baseball never reaches the coverage gate.** Of 18 ledger rows,
    exactly 1 has a coverage failure head (tennis); 14 fail at `coordinate_contract` first. So this row
    is NOT a 'baseball rescue' and must not be written up as one. It corrects a metric that is wrong on
    its own terms. **No row is expected to flip FAIL -> PASS. If one does, that is a finding to report,
    not a success to claim.**
  - **G164**: three quantities share the name `coverage_pct`. The gating one is computed over a
    decoded-padded frame and DISCARDED by `adjudicate`.
  - The adjudication: correct the denominator to EVALUATED frames. Evaluated is decided BEFORE
    tracking and the tracker cannot influence it; EMITTED (quantity 3, reading 0.9848 for tennis) is
    decided BY tracking and remains the trap. That is the line.

THE CHANGE, and it is deliberately small. The pieces already exist:
  (a) `decode_manifest.build_decode_manifest` already takes a `non_play` classifier slot, documented
      as a closure over frame index that is independent of emitted rows. **Skipped-stride frames are
      the cleanest `non_play` this program will ever have.** Route the manifest's per-frame
      `evaluated` boolean through that slot. Frames ABSENT from the manifest -- including any
      `max_frames` tail -- also count as not evaluated.
  (b) `_with_decoded_denominator` in `track_daemon_done.py` currently pads to `range(decoded)`. Pad to
      the EVALUATED set instead, so the gating quantity divides by attempted frames.
  (c) Persist the GATING quantity in the ledger row alongside the existing field. This is G164's open
      item: the number that decides `passed` is currently thrown away. **Do NOT rename or repurpose
      the existing `coverage_pct` field** -- B2 forbids it and readers depend on it. Add a new field.
  (d) Add a declared `stride` (or `sample_hz`) field to the row so the sampling cost is VISIBLE rather
      than laundered into coverage.

VERIFY BEFORE YOU TOUCH ANYTHING (Q8): `frame_manifest.csv` is written per job on the daemon path and
`track_daemon.py:157` already reads it, so the evaluated count should be a persisted artefact rather
than an estimate. Confirm that from the code and from a real file on the pod. If it is not persisted
for every job, say so and STOP -- the fix depends on it.

MANDATORY EVIDENCE, this is the acceptance test:
  - **A5 reader survey** over every consumer of `coverage_pct`, the verdict sidecar, the decode
    manifest and `completeness`. An id/metric scheme is read by more things than write it.
  - **Recompute the twelve baseball rows plus tennis and soccer BEFORE and AFTER**, from artefacts
    already on the pod, and show both columns side by side. Expected after-values, stated so you can
    falsify them rather than match them: baseball about 0.90-0.96, soccer about 0.24, tennis about
    0.076. **If your after-values differ materially from those, that is a finding -- report it, do
    not tune toward the expectation.**
  - A per-file test that fails without the change.
  - State explicitly in the memo that no bar value was edited, and show `git diff` over the harness
    SPORTS table proving it is unchanged.

DO NOT change any `coverage_min` or other bar, the eligibility definition, the coordinate contract,
`min_players`, or any verdict. Do not rename or remove a ledger field. Do not touch `src/`
(human-gated). Do not restart or kill the pod daemon; the orchestrator deploys after ACCEPT (B5).

ACCEPTANCE RULE:
  metric        = before/after coverage for all 14 reachable rows; the A5 reader list; a test that
                  fails without the change; a diff proving every bar value byte-identical
  before        = coverage capped at 1/stride; baseball at ~94 pct of an unreachable ceiling; the
                  gating quantity discarded
  bar           = NO pass bar for this row. Success is the denominator corrected with bars untouched
                  and the before/after table produced. "The manifest is not persisted for every job,
                  so this cannot be done safely" is a FULL SUCCESS -- report it and stop.
  n             = all 14 reachable ledger rows (CONSTRUCT, exhaustive); name any excluded and why
  eye check     = replaced by REPRODUCTION (Q7): the before/after table recomputed from artefacts
  must not move = every coverage_min and every other bar, min_players, the eligibility definition,
                  the coordinate contract, every existing ledger field name, `src/`, every verdict
EVIDENCE: docs/evidence/tracking/g178_evaluated_denominator_2026-09-03.md with the before/after table,
the A5 survey, the unchanged-bars diff, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: the new per-file test plus `test_track_daemon_done.py`, `test_track_daemon.py` and
`test_track_daemon_ledger_denominator.py` -- paste all results. Running only your own file is what
caused a REJECT earlier today. NEVER a full pytest.
POD: READ-ONLY and BATCHED. Never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, no push. Report the sha and the before/after table.
NEVER PARK.
