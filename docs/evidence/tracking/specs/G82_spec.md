GAP G82 | sport all | worktree a8 | log cx_g82_jump_statistic_limit
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. MEASURE FIRST. Do NOT move the bar and do NOT change the gate.
THE DEFECT: `jump_p95` structurally excludes the tail it exists to catch. A 95th percentile ignores
the top 5 pct of steps by construction, and teleports are by definition in that top 5 pct. The gate
audit swept prevalence and found **40-foot teleports at up to 5 pct of ALL steps leave jump_p95
pinned at 0.60 with verdict PASS**; it only trips at 6 pct. Separately, `groupby.diff()` differences
consecutive ROWS rather than consecutive FRAMES, so a clean path and one containing ten 40-ft
teleports across a 200-frame hole both report `jump_p95 = 0.6, PASS`.
That is the G43 signature -- one number for a healthy input and a broken one -- sitting in the metric
that G38's ENTIRE diagnosis of tennis player selection rests on. Read
docs/evidence/tracking/HARNESS_GATE_AUDIT_2026-09-02.md before starting, and REPRODUCE the sweep
yourself; do not take it on trust.
MEASURE (step 1), and this is the deliverable:
  (a) On REAL tracking tables, not synthetic ones, measure what fraction of oversized steps sit
      ABOVE the p95 -- that is, how much of the real defect the current statistic cannot see. State
      the table set and the denominators. G38 measured the 10-29 ft band as the mass of the tennis
      defect; use that as the definition of oversized and say so.
  (b) Report, per table, what the current `jump_p95` says versus what a MAX, a count-over-threshold,
      and a rate-per-frame-gap would say. Four columns, same rows. The reader should be able to see
      which statistic distinguishes a healthy table from a broken one.
  (c) Quantify the row-versus-frame defect separately: how many consecutive-ROW diffs in the real
      tables span a frame gap greater than the sampling stride? A diff across a 200-frame hole is
      not a step and should never have been counted as one.
PROPOSE (step 2), and stop there: name the statistic you would replace `jump_p95` with, and state
what it would do to EVERY existing verdict -- how many tables currently PASS that would fail, and
how many currently FAIL that would pass. A proposal without that impact count cannot be adjudicated.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the fraction of real oversized steps invisible to jump_p95, and the four-statistic
                  comparison table
  before        = jump_p95 with an 8.0 ft bar; blind to 40-ft teleports below 6 pct prevalence
  bar           = THERE IS NO PASS BAR and NO THRESHOLD MOVES IN THIS ROW. Success is the measured
                  blindness fraction on real tables plus a proposal carrying its full verdict-impact
                  count. "The current statistic is adequate on real data because real prevalence is
                  above 6 pct" would be a perfectly good outcome -- check it before assuming.
  n             = every tennis table with jump rows, plus at least one other sport for contrast;
                  state counts
  eye check     = for >= 6 steps the current statistic misses, render the two frames and LOOK. Say
                  whether the step is a real teleport, a re-appearance across a gap, or a genuine
                  fast movement. A step counted without being seen is not evidence.
  must not move = the 8.0 ft bar, `jump_p95` itself, every other threshold, and every verdict. This
                  row changes NO code beyond whatever measurement script it needs.
NON-TAUTOLOGY: do not define "oversized step" using the same p95 you are testing -- that is circular
(B1). Define it physically, from the G38 finding, in feet or in ft/s, and state the definition.
DEPENDENCY worth knowing: G83 is separately fixing `sampling_interval_s`, which has never carried a
value in production, so a true ft/s statistic is not computable on historical reports yet. Work in
feet where you must and say where a speed would be better once G83 lands.
DURABILITY (A7): commit the per-table four-statistic table and the renders under
docs/evidence/tracking/g82_jump_statistic/ BEFORE reporting.
EVIDENCE: docs/evidence/tracking/g82_jump_statistic_limit_2026-09-0X.md with the reproduced sweep,
the blindness fraction on real tables, the four-statistic comparison, the row-versus-frame count,
the proposal with its verdict-impact count, the renders, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: read-only. No scp, no deploy, never kill anything -- another session has live processes there.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a8,
no push. Report the sha.
SHARED MODULE: tracking_harness.py is under the token AND another lane (G80) is editing it right
now. Do NOT touch it. If your measurement needs harness internals, import and call them read-only.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
