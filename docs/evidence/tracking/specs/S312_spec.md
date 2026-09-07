GAP S312 | sport all | worktree aXX | log cx_s312_teach_connection
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: allocated 2026-09-07 by the orchestrator's harness finish audit (orchestrator-held; NOT a lane input). This is THE single real harness <-> tracking
  connection row and it consumes S04 (c7523ce63, synthetic teacher gate), S31 (d48731fe3, real clustered INSUFFICIENT construct) and S26 (BLOCKED). S04 and S31
  certify CONSTRUCTS only; neither is a real tracking-trained, API-only student comparison.
DEPENDENCY: dispatch after S311 (safe pod transport). The census is local; teacher training and scoring run on the pod.
WHERE: local read-only census, arithmetic and one per-file test; training and scoring via ~/bin/pod_run <aN> --ship <code> --fetch <evidence> -- <cmd>, scratch /workspace/wt/<aN> only, never the deployed tree.
PREMISE (step 0): S04/S31 certify constructs only; S26 lacks a video-derived command_target; S193's missing worktree inputs do NOT prove that no teacher
  exists -- an absent copy is not an absent corpus. Census, printing path, rows and first 3 ids for each: the exact teacher rows available, their G-route
  tracking quality verdicts, the joinable API histories, and the outcome cutoffs. Freeze ONE target and ONE sport and publish the honest eligible denominator
  BEFORE any fit. Stop FALSIFIED only on that census, never on an absent worktree copy or an incidental date typo.
LIMIT (step 1): if no QUALIFIED real teacher corpus exists, report BLOCKED naming the missing prerequisite. A synthetic teacher is NOT a substitute and does not close this row.
CHANGE (step 2): train a teacher from tracking on strictly PRIOR games; distill it to an API-only student; score four arms on IDENTICAL held-out games -- ID
  baseline, student, student+IDs, and a matched API-only no-distillation ablation. Runtime inference reads declared API inputs only, through the isolation and
  key guards; opt-in existence is insufficient. Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above the seal line). Archive evaluator-derived
  keyed paired losses, every exclusion, the training cutoffs, frozen seeds and source hashes. Purge by actual games and teams with a nonzero embargo and
  nested OOF meta-calibration; chronological outer folds are the headline and CPCV is a labelled robustness companion. Never write data/ or docs/research/;
  never rewrite an existing artifact (new dated filenames).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric = paired Brier of student vs ID baseline, student vs student+IDs, and student vs the matched no-teacher API arm, on identical held-out games, with the provenance counts below.
  before = S04 and S31 are constructs; no real tracking-trained API-only student has ever been scored.
  bar = ALL of: 100 pct of scored rows trace to qualified teacher/train inputs AND to declared API inference inputs; 0 held-out-teacher dependencies; 0
        held-out-outcome dependencies; 0 runtime tracking reads; 0 unexplained join losses; every paired score replays. RETAINED S04 CLAUSES, UNCHANGED:
        delta Brier >= 0.004 vs IDs, DM lower > 0, launch-K p < 0.05, Brier(student) - Brier(student+IDs) <= 0.004, n_eff >= 30, and its 20-cluster floor.
        ADDED ATTRIBUTION BAR: the student beats the matched no-teacher API arm with paired lower > 0.
  sign = improvement = baseline loss minus candidate loss; positive = candidate better; the frozen +0.004 bar is unmoved.
  n = the frozen eligible held-out set, meeting BOTH the S04 20-cluster floor AND the scored-row >= 30-game rail; printed per arm.
  eye check = n/a (S-row); reproduction = verifier replays every paired score and one fold from the archived keyed losses.
  must not move = the +0.004 bar; S04/S31 modules and artifacts; every tracking source store; data/registry/; all prior dated evidence.
NON-TAUTOLOGY: the eligible denominator is fixed by teacher qualification and API availability BEFORE scoring, never by outcome; every dropped game is counted
  by reason. A measured NULL closes the real experiment and is a success.
NO POSITIVE TEACHING CLAIM without independent replication and the common ship gates: >= 2 independent OOS corpora, all-fold improvement, null-shuffle z >= 3,
  ablation, launch-K charging and both multiplicity bars. This row authorizes NO charge.
EVIDENCE: docs/evidence/harness/S312_teach_connection_2026-09-07.md + summary JSON + the keyed paired-loss CSV + the census table (Q9).
TEST: exactly one new per-file test with full package imports covering: tracking removed at inference gives BYTE-IDENTICAL predictions; a future-teacher plant
  is refused; shuffled-teacher and ID-only controls; qualified vs unqualified teacher; fold replay. Run only that file.
BAN: never write data/ or docs/research/; no gated-tree change; no flag flip; no registry write; no forced git operation; calibration language only.
REPORT: census counts, the four-arm table with CIs, the provenance zeros, RSS, test line, SHA, NOT VERIFIED list. No push. NEVER PARK.

## VERSION 2026-09-07b (astra feasibility)
AMENDMENT SOURCE: docs/research/astra_teach_feasibility_2026-09-07.md section "S312 critique + minimal amendment" items 1-5, adjudicated 2026-09-07.
SCOPE: ADDITIVE ONLY. Every bar, threshold, count and clause above stands unchanged and binding verbatim -- delta Brier >= 0.004 vs IDs, DM lower > 0,
  launch-K p < 0.05, Brier(student) - Brier(student+IDs) <= 0.004, n_eff >= 30, the 20-cluster floor, the >= 30-game scored-row rail, the added attribution
  bar (paired lower > 0 vs the matched no-teacher API arm) and every provenance zero. NOTHING BELOW RELAXES A TRACKING BAR.
A1 TEACHER_QUALIFICATION (item 1): "QUALIFIED" had no image-space definition, so a court-coordinate G-route FAIL was being read as disqualifying observed
  pixels while a self-consistency pass was being read as validating them; neither inference is licensed. Declare teacher_qualification PER SIGNAL from
  independent evidence only: (a) independent OBSERVATION evidence -- rows are observed, never inferred/default coordinates and never a PASS_NO_BALL
  placeholder; (b) independent IDENTITY evidence -- a verified NBA player_id or independently qualified team labels, never a local track_id and never a
  dominant colour; (c) independent TIME-ALIGNMENT evidence -- >= 2 clock anchors per live interval with source event order breaking identical clocks;
  (d) the ATTEMPTED-INTERVAL denominator, abstentions counted as failures. Record the G-route registration verdict and the producer/harness hash
  SEPARATELY from teacher_qualification: neither substitutes for the other, and the registration verdict is never edited by this row.
A2 CENSUS-FIRST BRANCHING (item 2): the spec assumed an available joined corpus. That assumption is replaced by a mandatory branch taken BEFORE any fit.
  If the authoritative source census establishes no qualified real teacher corpus for the frozen sport/target, report BLOCKED naming the missing
  qualification, source, join or history prerequisite. Synthetic data cannot substitute and does not close this row. If the authoritative inventory is
  itself unavailable, that is BLOCKED: census prerequisite unavailable -- it is NOT proof of corpus absence. A qualified but UNDERSIZED corpus is
  INSUFFICIENT. A measured NULL requires an actual valid four-arm comparison and nothing less.
A3 N_teacher_train VS N_API_test (item 3): "100 pct of scored rows trace to qualified teacher/train inputs" conflated training provenance with per-test-game
  tracking. Publish N_teacher_train and N_API_test as SEPARATE counts. INFERENCE DEPENDENCY BOUNDARY: held-out video may establish ELIGIBILITY ONLY --
  never a teacher target, never a feature, never a fitted transform, never a prediction-time lookup value. The frozen tracked-game evaluation population is
  preserved as written. A later scope amendment admitting API-only test games with no video is a DIFFERENT preregistered population: preregister it
  explicitly, retain every numerical bar, still publish the tracked/API/outcome intersection, and never apply it silently inside this row.
A4 PURGE SCOPE AND EMBARGO (item 4): "purge by actual games and teams" is underspecified -- removing every appearance of all held-out NBA teams can empty
  training. BEFORE fitting, freeze and publish the team-group purge scope, the nonzero embargo duration, and the resulting per-fold train/test counts.
  Empty or degenerate folds are INSUFFICIENT; they are never a NULL and never a reason to relax the purge.
A5 LAUNCH-K CONTRADICTION (item 5): launch-K p < 0.05 is required while "This row authorizes NO charge" forbids its prerequisite. RESOLUTION FOR THIS ROW:
  STOP BEFORE SCORED ACCEPTANCE pending authorization of the named isolated pre-metric research charge. K = 1 is NEVER used silently. A lane reaching the
  scoring step without that authorization reports BLOCKED (launch-K charge unauthorized), publishing its census, qualification and fold counts, and does
  not score.
A6 CONSTRUCT EVIDENCE STAYS SEPARATE (item 6): runtime-purity and future-teacher-refusal may be exercised NOW as CONSTRUCTS, but real fold replay and real
  attribution cannot be tested without real qualified inputs. Construct evidence never counts toward completion of this row.
A7 The execution BAN above (never write data/ or docs/research/) is unchanged for this lane. The feasibility memo cited here was produced under a separate
  research charge; it changes neither this spec's bars nor any prior dated evidence artifact.
BLOCKED-ON: S314 (TEACH-0 teacher packet qualification + alignment) must land before this row's CHANGE step may be dispatched. S315 (TEACH-1 visible
  ball-control duration) is the first predictive trial and is itself BLOCKED-ON S314.
