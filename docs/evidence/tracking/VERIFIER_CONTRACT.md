# Verifier contract -- what every tracking landing must survive
Every codex spec MUST cite this file and self-check against section B (and section Q for a harness/system S-row) before reporting. Every verifier applies section A + B, plus Q on S-rows, and nothing else; rules outside the spec's ACCEPTANCE RULE are filed as new gaps, not rejections.

---

Codex self-checks section B before reporting. The verifier applies A and B and
nothing else. A rule absent from the spec's ACCEPTANCE RULE cannot be used to
reject -- if the verifier needs one, it files a new gap instead.

## A. The verifier's own work (not the lane's)
A1 Re-run the lane's single per-file test in MASTER, not the worktree.
A2 Recompute the headline metric from the artifact yourself; never quote the lane's number without reproducing it.
A3 Sample renders EVENLY over the decision set. Head slices are how G11 v1 showed 0.93 where the honest number was 0.78.
A4 Count uniqueness -- G23 reported 2,209 rows that were 2,013 unique frames.
A5 Grep every reader of any field the diff touches (G15 broke night_report).
A6 Land by `git -C <wt> archive <sha> -- <paths> | tar -x -C <repo>`, explicit pathspec commit, then append the RESULTS_LEDGER line and the register row.
A7 Confirm that every evidence path named by the memo exists at verification time; a missing path is NOT VALIDATED, never a silent pass.

## B. Automatic reject conditions (codex: check before you report)
B1  CIRCULAR METRIC -- computed after excluding the rows that would fail it, or the excluded set is unnamed. (G19)
B2  NON-ADDITIVE SCHEMA -- a column, status value or field renamed/removed without an alias, or a reader unchecked. (G15)
B3  FALL-THROUGH LOSS -- a gate quarantines on ABSENT evidence instead of passing the item on. Missing != bad. (G01)
B4  RE-CLAIM LOOP -- a failure path leaves an item claimable forever. (G15)
B5  PRE-VERIFICATION DEPLOY -- any file copied to the pod before ACCEPT. (G28)
B6  ORPHANS -- a moved/retired module leaves a test, import or -m reference behind. (G21)
B7  HEAD-SLICE EVIDENCE -- renders or rows sampled from the start of the set.
B8  SELF-FIT AS INDEPENDENT -- a residual against the same points used to fit is not evidence. (G23)
B9  DEGENERATE DENOMINATOR -- the metric's unit is recycled or trivially constant, e.g. 10 recycled track ids per game. (G25)
B10 MOVED BAR -- any harness threshold or gate value differs from master.

## Q. Quant additions (harness / signals / system rows -- the S-register)
Apply Q1-Q6 to every row in docs/evidence/HARNESS_GAPS_2026-09-03.md exactly as
B1-B10 apply to every tracking row. Codex self-checks them before reporting.
Q1 PREREG SEALED BEFORE SCORING -- a scored comparison names its prereg artifact and the SHA-256 seal embedded in it, and the seal predates the first metric. No seal, no scored claim.
Q2 LEDGER CHARGED BEFORE THE METRIC -- a charged trial appends its ledger row before computing anything and reports the K it read AT LAUNCH. K read after scoring is an automatic reject (nine unrelated trials once moved K 3 -> 12 between prereg and launch and flipped a verdict).
Q3 NO BAR OR THRESHOLD MOVED -- every bar in the artifact is byte-identical to the bar in the spec. A bar found unmeetable is reported CLOSED AT LIMIT, never lowered.
Q4 LEAK CONTRACT VIA CPCV -- anything scored OOS runs through walk_forward or cpcv_evaluate with purging and a symmetric embargo; any meta-learner consumes OOF series only, asserted to reproduce each arm's own reported metric to 1e-9.
Q5 TWO CORPORA FOR ANY AHEAD -- an AHEAD names its second corpus or corpus_unit and prints min_corpora_eff at the current K; if it cannot be satisfied the verdict is labelled SINGLE-WINDOW in the artifact AND the register row.
Q6 CALIBRATION LANGUAGE ONLY -- no dollar, ROI, profit or "edge" language in any artifact, memo, ledger line or register row; none of the retracted figures (+18.38, 0.119, +54, 78.11, 8.94, 54.57) appears outside an explicit retraction context. Accuracy is not edge; an honest REJECT, NULL or BEHIND is a success.

## Q7-Q8 (added 2026-09-03 by the roadmap audit)
Q7 SAMPLING RAIL SCOPE -- `n >= 30` binds a SAMPLED or SCORED metric. A spec that
writes `n = <k> (CONSTRUCT)` has enumerated every case and may NOT be rejected on
the rail; the verifier instead checks that the enumeration really is exhaustive.
An S-row's `eye check` is replaced by REPRODUCTION (A2 applies, A3 does not).
Q8 PREMISE FIRST ON A ROW OLDER THAN A DAY -- before any work, re-measure the one
fact the row rests on. Three premises in this program were already false when the
row was read: the "three overdue pod deploys" (done 2026-09-02 22:05, ledger
G14b), the "two unguarded default-ledger writers" (both guarded,
inplay_derivative_mlb.py:257 and mlb_deriv_settle.py:120-122), and H01's "no
games.parquet" (all four gate corpora exist). A falsified premise is a VALID
result: report FALSIFIED, write the memo, and the row closes without a fix.

## C. Verdicts
ACCEPT (land) | ACCEPT WITH CORRECTIONS (land; ledger carries the corrections)
| NOT VALIDATED (land as unused/opt-in with zero callers, honest row)
| REJECT (do not merge; queue a named fix pass) | CLOSED AT LIMIT (no retry).
Every verdict writes one RESULTS_LEDGER line and one register row.

## Q9 (added 2026-09-03 by the harness session, from S58 trial 2)
Q9 ARCHIVE THE DIFFERENTIAL -- a scored artifact stores its per-unit paired-loss series
(per game / per state: the two losses being compared, the cluster id, the timestamp) beside
the summary, and the model side of every comparison is computed from an AS-OF state that is
itself archived or reconstructible. A CI that cannot be recomputed from the artifact alone is
not a result (the NBA halftime checkpoint claim could not be re-scored because its model used
the Elo state at run time and its per-game deltas were never written -- S63).
