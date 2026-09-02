# Verifier contract -- what every tracking landing must survive
Every codex spec MUST cite this file and self-check against section B before reporting. Every verifier applies section A and B only; rules outside the spec's ACCEPTANCE RULE are filed as new gaps, not rejections.

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

## C. Verdicts
ACCEPT (land) | ACCEPT WITH CORRECTIONS (land; ledger carries the corrections)
| NOT VALIDATED (land as unused/opt-in with zero callers, honest row)
| REJECT (do not merge; queue a named fix pass) | CLOSED AT LIMIT (no retry).
Every verdict writes one RESULTS_LEDGER line and one register row.
