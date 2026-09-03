GAP G197 | sport all | worktree a7 | log g197_harness_coverage_denominator
**This corrects a CIRCULAR METRIC inside the harness. It makes coverage HARDER, which Q3 explicitly
permits. It is NOT a moved bar and must not be described as one.** No `coverage_min` or any other
threshold value may change by a single digit.

**S1 MACHINE: LOCAL is fine and preferred.** This is a scoring-function change plus per-file tests
over committed tables; no video decode, no model inference, no `run_clip.py`. **Do NOT launch the
route and do NOT run anything on the pod** -- the pod is busy and the local box has been at 95 pct
RAM twice today. If you believe you need the pod, stop and say why instead.

**S3 DEPENDENCY.** Adjudicated as step 1 in `G_ADJUDICATION_fable_review_2026-09-03.md`, ahead of any
detector work.

THE DEFECT, verified by the orchestrator by reading the file:
  - `scripts/platformkit/tracking_harness.py:234` -- `n_frames = int(df["frame"].nunique())`
  - `scripts/platformkit/tracking_harness.py:250` -- `coverage = float((per_frame >= cfg["min_players"]).sum() / n_frames)`

`df` is the EMITTED tracking table. So `n_frames` counts only frames that HAVE ROWS. **A frame where
the tracker emitted nothing is not in the denominator at all**, which means the metric is computed
after excluding the cases that would fail it. That is **B1**, the contract's own first automatic-reject
condition, sitting inside the harness that adjudicates every row. G34 measured the inflation at
**4.9x** on 2026-09-02 and flagged it "on the critical path, not a nicety"; it was never acted on.

`ball_valid_pct` divides by the same `n_frames` and inherits the same defect. `min_players`,
`jump_p95`, `jump_max`, `oob` and `median_track_len` do NOT and must not be touched.

**THIS IS NOT G179.** That row corrected a denominator on the DAEMON path
(`_with_decoded_denominator` in `track_daemon_done.py`). This is a different computation in the
harness that scores tables. Read G179 first and state in your memo how the two relate, so nobody
later thinks one superseded the other.

THE CHANGE, and B2 binds it hard:
  (a) **Do NOT rename, remove or repurpose `coverage_pct` or `ball_valid_pct`.** At least eight
      modules read them -- `baseball_calib_probe.py`, `evidence_page.py`, `ledger_report.py`,
      `metric_local_profile.py`, `teacher_student_ab.py`, `teacher_student_distill.py`, and tests.
      **A5 survey every one and report what each would see.**
  (b) Add a NEW, correctly denominated field alongside, and make the GATE use it. Name it so its
      denominator is unmistakable in the field name itself.
  (c) The correct denominator is the frames the pipeline ATTEMPTED, not the frames it emitted on.
      Decide where that count comes from and JUSTIFY it: a `decoded_frames`/`attempted` value already
      on the row if one exists, or an explicit argument. **If no honest attempted-count is available
      for a given table, the new field must be `None` -- never silently fall back to `nunique()`,
      which would reintroduce the defect under a new name.**
  (d) Record in the report which denominator each field used, so a later reader can tell them apart.

MANDATORY EVIDENCE:
  - **Before/after on real committed tables**, showing old coverage, new coverage, and the two
    denominators side by side. State how many rows change verdict. **A row flipping PASS to FAIL is
    the EXPECTED direction** and is not a regression; a row flipping FAIL to PASS would be alarming
    and must be investigated and reported, not accepted.
  - The A5 reader survey from (a).
  - A per-file test that fails without the change, plus `test_tracking_harness.py` -- paste both.
  - A `git diff` over the `SPORTS` / `CONFIG_VERSIONS` table proving **every threshold is
    byte-identical**.

ACCEPTANCE RULE:
  metric        = before/after coverage on real tables with both denominators named; verdict-change
                  count; the A5 reader list; a diff proving thresholds unchanged
  before        = coverage divides by the frames that have rows, so failures are excluded from their
                  own denominator; measured 4.9x inflation on one clip (G34)
  bar           = NO pass bar. Success is the corrected quantity added, the gate moved onto it, every
                  threshold untouched, and the before/after produced. **"No honest attempted-count
                  exists for these tables, so the new field is None everywhere" is a FULL SUCCESS**
                  and would itself be an important finding.
  n             = every committed table you can score (CONSTRUCT); name any excluded and why
  eye check     = replaced by REPRODUCTION (Q7): the before/after recomputed from committed tables
  must not move = every `coverage_min` and every other threshold, `min_players`, the eligibility
                  definition, the coordinate contract, existing field NAMES, `src/` (human-gated),
                  the pod daemon and keeper
EVIDENCE: docs/evidence/tracking/g197_harness_coverage_denominator_2026-09-03.md with the
before/after table, the A5 survey, the unchanged-threshold diff, the relationship to G179, and a NOT
VERIFIED list. Commit BEFORE reporting (A7).
TEST: your new per-file test plus `test_tracking_harness.py`, both pasted. NEVER a full pytest.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
