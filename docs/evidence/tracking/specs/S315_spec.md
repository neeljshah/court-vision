GAP S315 | sport nba | worktree aXX | log cx_s315_teach_ball_control
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: allocated 2026-09-07 from docs/research/astra_teach_feasibility_2026-09-07.md ranked experiment S-TEACH-1 (orchestrator-held; NOT a lane input) -- the highest-ranked predictive trial
  under S312 (amended 2026-09-07b). Frozen sport = NBA. Frozen target = home-win probability at the END OF Q2, one scored row per actual game; the final outcome is evaluation-only on held-out
  games. BLOCKED-ON: S314 -- do NOT dispatch before S314 lands a qualified packet; without it this row reports BLOCKED (teacher packet unqualified) and stops.
DEPENDENCY: S311 (safe pod transport) and S314. Fits and scoring run on the pod; census and arithmetic are local.
WHERE: local = committed records, arithmetic, one per-file test. pod = teacher/student fits and scoring, run with ~/bin/pod_run <aN> --ship <code> --fetch <evidence> -- <cmd>, scratch
  /workspace/wt/<aN> only, NEVER the deployed tree /workspace/nba-ai-system.
PREMISE (step 0) BINDING BEFORE-CONDITION: the census must find QUALIFIED observed ball/player/team associations and unique J/S alignment (J = league, official game_id, period, validated elapsed
  game time, ordered API event; S = J plus team_id and the half-open lineup stint), with NO inferred-ball substitution, and enough chronological games surviving the S312 rails. A PASS_NO_BALL
  corpus cannot qualify a ball signal; ball rows with inferred or default coordinates are not observations. If any item is missing, STOP and report BLOCKED naming it.
LIMIT (step 1): a qualified but undersized corpus is INSUFFICIENT; empty or degenerate folds after the frozen purge are INSUFFICIENT. Neither is a NULL.
CHANGE (step 2): teacher inputs = PREFIX visible ball-control duration and concentration summaries (episode durations; changes between verified teammates) from strictly PRIOR games. Student
  inputs = the IDENTICAL API prefixes the no-teacher arm uses. One frozen small model family and loss mixture, NO tuning on outer games. Fit the inner teacher on earlier completed games only,
  generate its OOF q_g, train the student on X_g with q_g under the same labels and budget as its ablation. Teacher fits, normalization, identity priors, reliability weights and meta-calibration
  are recomputed INSIDE chronological folds; no teacher trained on g may supervise g. At outer game k, freeze every weight and predict from X_k only.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else) -- THE FULL FOUR-ARM RULE:
  metric = paired Brier on IDENTICAL held-out games across four arms -- IDs, student, student+IDs, and a matched API-only no-distillation arm -- with equal training API data, architecture,
           labels, budget and ID prior where applicable.
  before = S04 (c7523ce63) and S31 (d48731fe3) certify CONSTRUCTS only; no real tracking-trained API-only student has ever been scored.
  bar = ALL of: Brier(IDs) - Brier(student) >= 0.004; DM lower > 0; launch-K p < 0.05; Brier(student) - Brier(student+IDs) <= 0.004; n_eff >= 30; >= 20 clusters AND >= 30 actual scored games;
        paired lower > 0 versus the matched no-teacher API arm. PLUS the S312 provenance zeros: 0 held-out-teacher dependencies, 0 held-out-outcome dependencies, 0 runtime tracking reads,
        0 unexplained join losses, every paired score replays. No benefit may be attributable solely to camera or missingness control.
  n = the frozen eligible held-out set meeting BOTH the 20-cluster floor and the >= 30 scored-game rail, printed per arm, with N_teacher_train and N_API_test published as SEPARATE counts (A3).
  eye check = n/a (S-row); reproduction = the verifier replays every paired score and one fold from the archived keyed losses.
  must not move = the +0.004 bar; the attribution bar; S04/S31 modules and artifacts; every tracking source store; data/registry/; all prior dated evidence.
LAUNCH-K (S312 A5, binding): STOP BEFORE SCORED ACCEPTANCE pending authorization of the named isolated pre-metric research charge. K = 1 is NEVER used silently. Reaching the scoring step
  unauthorized = BLOCKED (launch-K charge unauthorized), with census, qualification and fold counts published.
PURGE (S312 A4, binding): freeze and publish the team-group purge scope, the nonzero embargo and the resulting per-fold train/test counts BEFORE fitting. INFERENCE BOUNDARY (S312 A3, binding):
  held-out video establishes ELIGIBILITY ONLY -- never a teacher target, feature, fitted transform or prediction-time lookup value.
NON-TAUTOLOGY: the eligible denominator is fixed by teacher qualification and API availability BEFORE scoring, never by outcome; every dropped game is counted by reason. A measured NULL closes the real experiment and is a SUCCESS; inadequate n is INSUFFICIENT.
NO POSITIVE TEACHING CLAIM without independent replication and the common ship gates: >= 2 independent OOS corpora, all-fold improvement, null-shuffle z >= 3, isolated ablation, launch-K
  accounting and both multiplicity bars. One screened corpus cannot establish it.
TEST: exactly one new per-file test with full package imports covering: teacher summaries shuffled within training time blocks preserving missingness; the matched API-only control;
  future-teacher refusal; byte-identical inference with tracking removed. Run only that file.
BUDGET: 3,600-second wall stop; 10 min checks, 35 min fits, 15 min replay. On expiry report BUDGET LIMIT with the completed counts. EXPECTED FAILURE: the current caller has no real ball path;
  apparent possession ends at cuts; PBP duration/assist features already explain the information; the video advantage cannot be distilled into APIs.
EVIDENCE: docs/evidence/harness/S315_teach_ball_control_2026-09-07.md + summary JSON + the keyed paired-loss CSV + the census/purge count tables, with the prereg sealed FIRST as its own commit and a NOT VERIFIED list. New dated filenames only.
BAN: never write data/ or docs/research/; no gated-tree change; no flag flip; no registry write; no forced git operation; calibration language only.
REPORT: verdict first, the four-arm table with CIs, the provenance zeros, purge/fold counts, RSS, test line, SHA, NOT VERIFIED list. No push. NEVER PARK.
