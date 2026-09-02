GAP G77 | sport all (summary contract) | worktree a5 | log cx_g77_scorecard_scope
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report.
THE DEFECT, found by the G72 lane's own reader audit and deliberately NOT fixed there: with the
metric_local profile landed, `tracking_brain.scorecard` would place a metric_local report into
`games_scored`, into the PASS-RATE DENOMINATOR, and into the metric summaries -- even though that
report can never enter the pass NUMERATOR, because a scoped local result always emits
`passed=false` alongside `PASS_METRIC_LOCAL`.
WHY THIS MATTERS MORE THAN IT LOOKS: it silently DEPRESSES the reported pass rate with reports that
were never eligible to pass. It is also a direct violation of condition (a) of the G69 adjudication
-- "a scoped verdict may NEVER be aggregated with court_feet passes in any headline or count" --
appearing downstream of the change rather than inside it. And baseball is the largest rejection
block of any sport (66 of 93, G47), so once baseball starts producing metric_local reports this
would move the headline number for the whole program.
FIRST, REPRODUCE IT (step 0): construct a scorecard input containing one court_feet report and one
metric_local report, run the scorecard, and SHOW the defect -- the local report appearing in
games_scored and in the pass-rate denominator while absent from the numerator. Paste the output. If
it does NOT reproduce, say so and stop; that would mean the G72 reader audit was wrong and that is
a finding worth reporting.
FIX (step 1): scope the scorecard BY COORDINATE PROFILE before it counts anything. Requirements:
  (a) A court_feet pass rate is computed over court_feet reports ONLY. Its denominator must not
      contain a report that could not have passed it.
  (b) A metric_local report is reported in its OWN scoped counts, never folded into the court_feet
      figures and never simply dropped -- dropping it would hide baseball entirely, which is the
      opposite failure and just as wrong.
  (c) Metric summaries (medians and the like) are computed per profile. A median that mixes
      court_feet coverage with metric_local coverage is not a statistic of anything.
  (d) Any headline the scorecard emits states WHICH profile it describes. An unlabelled number is
      how a scoped result gets quoted as a pass.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the court_feet pass rate and its denominator, on a mixed-profile input
  before        = a metric_local report enters games_scored and the pass-rate denominator while
                  being ineligible for the numerator, depressing the rate
  bar           = on a constructed mixed input, the court_feet pass rate and denominator are
                  IDENTICAL to what they would be with the metric_local report absent, AND the
                  metric_local report is still visible in its own scoped counts, AND every emitted
                  headline names its profile
  n             = >= 4 constructed scorecard inputs: court_feet only, metric_local only, mixed, and
                  empty. State what each produced.
  eye check     = n/a (an aggregation contract). Reproduction = the before/after scorecard output
                  for the mixed input, pasted.
  must not move = every harness threshold, every report field, the G69 adjudication's four
                  conditions, and the court_feet numbers on a court_feet-only input. If ANY
                  existing court_feet-only scorecard output changes, that is a REJECT -- report it
                  rather than adjusting the fixture.
NON-TAUTOLOGY: do not "fix" this by excluding metric_local reports from the scorecard altogether
and then reporting that the mixed case now matches the court_feet-only case. That passes the bar
while hiding baseball, which is condition (b) above and the reason it is written down.
REGRESSION GUARD: replay >= 5 existing court_feet-only scorecard inputs and show byte-identical
output. Today a lane's byte-identical replay missed a defect because its fixtures all exercised one
path -- so state explicitly which paths your replay corpus covers and which it does not.
DURABILITY (A7): commit the constructed inputs and the before/after outputs under
docs/evidence/tracking/g77_scorecard_scope/ BEFORE reporting.
EVIDENCE: docs/evidence/tracking/g77_scorecard_scope_2026-09-0X.md with the reproduced defect, the
four constructed cases, the replay result and its stated coverage, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: no deploy, no scp, never kill anything -- another session has live processes there.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a5,
no push except the token if you need it. Report the sha.
SHARED MODULE: if tracking_brain or the scorecard lives under a token-listed module, take the token
in docs/evidence/SHARED_MODULE_TOKEN.md and PUSH the release when you report.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
