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
   Q6 NOTE (orchestrator ruling 2026-09-04, S223): Q6 governs prose, claims, table labels and ledger text. OPAQUE
   IDENTIFIERS quoted verbatim -- file basenames, paths, column names, module strings -- are exempt even when they
   contain a prohibited token; a census must emit the exact path and must not rename or mask it.

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

## Contract v2 (added 2026-09-03, adjudicated by Fable review)
Proposed by the orchestrator after a day in which four specs carried unverified premises, three
worktrees were nearly freed with unlanded work in them, a lane died silently holding an uncommitted
fix, 2.94 GB of reader-required footage was deleted before the survey that named it, and three
quality rows were landed on a route nobody had checked repeats. **Five further clauses were proposed
and CUT in review** for having no incident behind them, duplicating Q9, or conflicting with Q8.
Record: `G_ADJUDICATION_fable_review_2026-09-03.md`.

A9  NAME THE EXACT SOURCE -- every artifact and memo states the full path, byte size and resolution
    of each input opened, never a game_id alone. Two different videos answer to `wnba_01`: a
    1920x1080 pod file and a 1280x720 `g130_recensus/` derivative, and the same code gives materially
    different answers on them.
A11 CODE IDENTITY -- every row measured on the pod records the SHA-256 of each route file it
    exercised, or the deploy-manifest hash. The pod is not a git checkout, so its revision cannot
    otherwise be named; G184 recorded hashes voluntarily and that is what caught the drift, while
    G187 did not and its non-reproduction could not be attributed.
B11 SINGLE-RUN CLAIM ON AN UNREPRODUCED ROUTE -- quoting n=1 through a route whose repeatability is
    unestablished, as a property of the system. Binds EYE CHECKS equally: rendered overlays come from
    one run. Determinism ships as ENVIRONMENT and seeds in the spec command line, never as a file
    copied to the pod, which would collide with B5.
S1  NAME THE MACHINE -- every spec that runs anything says where, in its own line, with the reason.
    "Pod is read-only" plus "do not wait on the daemon" reads as "work locally" unless stated.
S2  VERIFY THE PREMISE BEFORE DISPATCH -- the orchestrator checks each premise against the code or
    the live system before sending the spec. **A premise about a SET is verified by computing the
    distribution over the WHOLE set, never by reading its first rows.** G192's spec asserted "the
    decodes are 640x360" from `head -3`; that described 1 of 17 frames, and the lane correctly
    stopped. This is B11's error one level up: a sample stated as a property, in a spec instead of a
    memo. Q8 makes the LANE re-measure; S2 makes the AUTHOR
    measure first. A lane that STOPS on a false premise is correct and the author owns the cost.
S4  NAME THE LEDGER AND THE FIELD -- a spec citing a count says which ledger file and which field.
    The pod ledger carries diagnostics in `failure_heads` over 40 rows; the local one carries them in
    `failures` over 300. Two correct answers to one question came from this.
S5  ONE ROW, ONE LANE -- a gap id is dispatched to exactly one worktree. G182 was double-dispatched
    by orchestrator error; the duplicate happened to be useful, which is not a reason to repeat it.
D1  CONTENT, NOT PATHS, BEFORE FREEING A WORKTREE -- `git log master..<branch>` non-empty means
    unlanded. Never free on dispatched-vs-exited or on path existence.
D2  SURVEY READERS BEFORE DELETING ANY DATA -- run a FILE-READER survey first (this is not A5, which
    is a schema-reader rule). A durable derived artifact is not evidence its source is spent, and a
    reader that tests non-reproducibility makes its sources irreplaceable by construction. Write a
    per-file deletion manifest BEFORE deleting.
D3  A LANE THAT STOPS SPEAKING IS NOT A LANE THAT FINISHED -- trigger on log/worktree mtime PLUS a
    CPU check, never on wall-clock silence alone: G186 records a legitimate 22-minute decode at 99
    pct CPU. On a dead lane, commit its uncommitted work BEFORE any cleanup.
D4  MATCH PROCESSES BY EXECUTABLE AND ARGUMENT, NEVER BY SUBSTRING -- a substring match on a command
    line catches the tools doing the matching, including this session's own monitor.
D5  NO DEPLOY WHILE A POD MEASUREMENT LANE IS LIVE -- G188 spent a section disproving the
    orchestrator's own mid-flight deploy of 4,327 files as a cause. Timing cleared it once; the
    practice is what made it plausible.
H1  NAMED DENOMINATOR -- coverage and ball_valid divide by decoded or segmented frames, named in the
    artifact, NEVER by the count of frames that happen to have rows. `tracking_harness.py:234` sets
    `n_frames` from frames that HAVE rows and `:250` divides coverage by it, so frames the tracker
    emitted nothing on are excluded from the denominator. That is B1 inside the harness that
    adjudicates every row; G34 measured 4.9x inflation on 2026-09-02.

## A12 (added 2026-09-03, from a cross-session collision)

A12 SHARED RAILS ARE PART OF THE LANDING. `tests/platformkit/test_loc_rail_scope.py`
    carries a per-file LOC allowlist. When a verified landing GROWS an allowlisted
    file, the verifier raises that file's entry **in the same commit**, with a
    one-line reason naming the commit, and runs that rail test as part of the
    per-file test list before reporting.
    Why this exists: G197 grew `scripts/platformkit/tracking_harness.py` from 331
    to 416 lines without raising its entry. Master's rail went red and BLOCKED THE
    PEER SESSION'S LANDINGS for about 15 minutes. The peer raised it and told us.
    A green per-file test in the lane's own worktree does not prove master is green
    for everyone else -- this repo is shared, and a rail is a shared surface.
    A file pushed over the 300-line rail is also a split candidate the next time it
    is touched; note it, do not split it opportunistically inside an unrelated row.
