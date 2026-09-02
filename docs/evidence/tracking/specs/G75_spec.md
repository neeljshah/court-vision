GAP G75 | sport basketball | worktree a2 | log cx_g75_paint_role_assignment
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report.
GATED ON G68D. Do not start until the G68 census verdict is recorded. If G68D reports pooled
`paint_solvable_share` below the pre-registered ~0.10, or reports that solvable tiles CLUSTER into
a handful of static half-court stretches, then this row is CANCELLED and the per-frame paint route
is a limit result. Read docs/evidence/tracking/g68_paint_solvable_share_2026-09-0X.md first and
state its verdict in your first paragraph.
WHY THIS ROW: G47 established that the blocker for 4 of 8 sports is CALIBRATION, not tracking
quality. The calibration strategy (docs/evidence/tracking/CALIBRATION_STRATEGY_2026-09-02.md --
READ IT, section 1.2) found basketball's paint is a known APERIODIC rectangle -- structurally the
same problem tennis solved, on a quarter of the geometry -- and that
domains/basketball/tracking/line_calibration.py ALREADY has LSD detection, collinear-fragment
grouping (`candidate_line_groups`), both rule-set tables (`nba_wnba`, `ncaa_legacy`) and
`solve_from_lines`, which fits H from 4+ NAMED line correspondences. The module docstring states
the gap exactly: it fits "only after a caller has identified all four physical lines." **No caller
exists.** This row builds only that: ROLE ASSIGNMENT.
SCOPE -- ONE PROBLEM ONLY. Map candidate line groups to `baseline` / `free_throw` / `lane_low` /
`lane_high`. Do NOT build the independent validation landmark and do NOT build sidecar persistence
in this row; both are named as separate pieces and each gets its own row. A row that does all three
cannot be evaluated.
METHOD the strategy recommends, and you should say why you did or did not follow it: orientation
split first, then role pinning by TERMINATION STRUCTURE -- the lane lines terminate at the baseline
and the free-throw line, and the free-throw line terminates at the lane lines. A pure cross-ratio
match is WEAKER here than in tennis because typically only 2-3 lines per direction are in frame, so
extent and termination evidence must carry more of the load. State the rule you implement in plain
sentences before any code.
THE LEAGUE IS CALLER-DECLARED, never inferred: `nba_wnba` lane width is 16 ft and `ncaa_legacy` is
12 ft, and guessing between them from the image is exactly the kind of inference that would make
the solve self-confirming. Take it as an argument, as football's `field_level` does.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = role-assignment accuracy against HAND-LABELLED roles on frames where a human can
                  see all four lines
  before        = no role assignment exists at all; `solve_from_lines` has no caller
  bar           = THERE IS NO PASS BAR on the solve, because this row does not solve. The bar is
                  that role accuracy is MEASURED on held-out frames against hand labels, reported
                  per role with counts, and compared against the trivial baseline of assigning by
                  image position alone (topmost = free_throw, etc). If the termination rule does
                  not beat naive position, say so -- that is a real and useful finding.
  n             = >= 40 frames with hand-labelled roles, drawn from the G68 PAINT_SOLVABLE tiles
                  (they are already identified and labelled -- reuse them, do not re-census), split
                  into disjoint tune and held-out sets BY CLIP. State both sizes.
  eye check     = MANDATORY. Render >= 12 held-out frames with each assigned role drawn in a
                  distinct colour and LOOK. Report every case where a role is wrong and what it was
                  confused with. A swap of lane_low and lane_high is the failure that a residual
                  cannot see and only a picture can.
  must not move = every harness threshold, the coordinate contract, the daemon, and the basketball
                  producer. This row adds a caller; it does not change what gets written.
DO NOT EMIT COORDINATES. This row produces role labels for lines, not tracking rows. Nothing here
may write a court_feet row, and no homography may be persisted -- that is the persistence row, and
G42 measured a 145.7x output inflation from a stale homography carried across unsolved frames, so
that piece must be built deliberately with fail-closed semantics rather than as a side effect here.
KNOWN TRAP, from memory heldout_validation_blindspot_2026_09_01: a held-out residual on the SAME
structure cannot catch a global swap or a scale error. That is why the eye check above is
mandatory and why validation by a physically DIFFERENT feature is its own separate row.
DURABILITY (A7): commit the hand labels, the split definition, per-frame assignments and the
renders under docs/evidence/tracking/g75_role_assignment/ BEFORE reporting.
FOOTAGE: basketball footage is POD-ONLY; the G68 contact sheets already exist under
docs/evidence/tracking/g68_paint_census/contact_sheets/. Read-only frame work on the pod is fine.
EVIDENCE: docs/evidence/tracking/g75_paint_role_assignment_2026-09-0X.md with the G68D verdict
restated, the rule in plain sentences, held-out per-role accuracy against the naive-position
baseline, the renders and every confusion you saw, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: read-only. No scp, no deploy, no daemon restart, never kill anything -- another session has
live processes there.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a2,
no push. Report the sha.
SHARED MODULE: none. line_calibration.py is under domains/, not the token.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
