GAP G33B | sport baseball | worktree a9 | log cx_g33b_baseball_scale_bins
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. MEASUREMENT ONLY. This gates G36 (day-corpus growth).
UNBLOCKED 2026-09-02 by G53: attempt 1 of this row ran on a premise that did not reproduce. G53
has now repaired it. Use the REPAIRED premise and nothing else:
  DAY   = 9 of 30 validated segments = 0.300, Wilson 95 pct [0.167, 0.479], from
          docs/evidence/tracking/baseball_scale_validation_2026-09-01/summary.json
  NIGHT = 0 of 6 = 0.000, Wilson 95 pct [0.000, 0.390], from the night_stride20/summary.json under
          that same directory. NIGHT IS CLOSED AT LIMIT under G11 (three rejected designs).
Read docs/evidence/tracking/g53_baseball_provenance_2026-09-02.md first. Do NOT re-derive or
re-combine these fractions, and do NOT report a combined 9/36 anywhere -- that number is superseded.
PREMISE (step 0, reproduce it): recompute 9/30 and 0/6 from the two named artifacts and print them.
If either does not reproduce, STOP and report that; do not proceed on a premise you cannot confirm.
LIMIT (step 1): "9 of 30 day segments validate" says nothing about WHY the other 21 fail, so it
cannot tell anyone whether growing the day corpus would help or would simply add more of the same
failure. That is precisely what G36 needs to know, and it is the only reason this row exists.
MEASURE (step 2): bin the 21 DAY failures by cause. Requirements that make the binning honest:
  (a) Define each bin BEFORE you count, list the definitions in the memo, and make them mutually
      exclusive and collectively exhaustive. Every one of the 21 lands in exactly one bin, and
      "other" is a permitted bin whose contents you then describe individually.
  (b) Bin by the FIRST stage that failed, not by the most interesting-looking property. A segment
      that fails view detection never reaches scale estimation and must not be filed under scale.
  (c) Report each bin as a count over the stated denominator of 21, with a Wilson interval. With
      n=21 those intervals are wide; report them anyway and do not describe a 3-segment bin as
      "dominant" when its interval overlaps a 6-segment bin.
  (d) EYE CHECK, MANDATORY: render and LOOK at at least 2 segments from every non-empty bin, and
      say what you saw. A bin assigned from a log string and never viewed is not a measurement.
      Commit the renders under docs/evidence/tracking/g33b_renders/.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the failure-bin distribution over the 21 day failures
  before        = no bin breakdown exists; only the 9/30 headline
  bar           = THERE IS NO PASS BAR. This row succeeds by producing a reproducible, viewed,
                  exhaustive binning. "Resolution_360p is not dominant" and "resolution_360p is
                  dominant" are equally good outcomes.
  n             = all 21 day failures, none sampled and none skipped
  eye check     = >= 2 rendered and viewed segments per non-empty bin, described in the memo
  must not move = every harness threshold, the segment definition as the 2026-09-01 run applied it,
                  the G11 night verdict, and the G53 restated fractions
GATE OUTPUT, state it explicitly at the top of the memo: G36 (day-corpus growth) proceeds ONLY IF
resolution_360p is NOT the dominant failure bin. Answer that question in one sentence, with the
number, and say whether the interval actually separates it from the next bin -- if it does not,
the honest answer is "cannot yet tell at n=21", and that is an acceptable answer.
NIGHT: do not analyse night segments. They are closed at limit and mixing them in is the exact
defect G53 just repaired.
EVIDENCE: docs/evidence/tracking/g33b_baseball_scale_bins_2026-09-0X.md with the reproduced
premise, the pre-declared bin definitions, the binning with intervals, the renders, the explicit
G36 gate answer, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: read-only if at all. No scp, no deploy, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a9,
no push. Report the sha.
SHARED MODULE: none. If you find yourself editing the harness, STOP.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
