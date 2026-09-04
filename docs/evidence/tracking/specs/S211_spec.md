GAP S211 | sport all (in-game) | worktree a18 | log cx_s211_ingame_headline_rederive
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: SIGNAL_INVENTORY_REDTEAM_2026-09-03.md line 199, verbatim: "- The two static->conditional Brier pairs
(0.209->0.159, 0.241->0.126) were read from `docs/evidence/ingame-conditioning.md`, not re-run." They are the flagship
model-quality numbers, quoted in docs/JOB_EVIDENCE_PACKET.md and on the public page, with an attribution (~73 pct NBA
/ ~99 pct MLB of the lift to the score; prior ~0.014 / ~0.001) carrying no CI and no archived per-game differential
(Q9 unmet).
PREMISE (step 0): re-measure and print: that ingame-conditioning.md still states NBA 0.209 -> 0.159 and MLB 0.241 ->
0.126 from proof_nba/ingame_accuracy.py and proof_mlb/ingame_accuracy.py; that the attribution and the ~0.014 / ~0.001
prior shares carry no CI; and whether any per-game differential exists under docs/evidence/ (name the grep). If
already re-derived, STOP, memo, commit, FALSIFIED.
LIMIT (step 1): state per sport whether the corpus the harness reads is present and its game-path count. If absent,
report NOT REPRODUCIBLE with the reason and re-derive the other; never substitute a corpus or quote the page as if
re-run.
CHANGE (step 2): smallest additive change -- run the two EXISTING proof harnesses unmodified, archive the per-game
paired-loss series for the three arms (static prior; prior + score; prior + state), and recompute the prior share with
a game-clustered CI. No harness, arm or builder modified. Additive only, nothing renamed; helper <= 300 lines within
test_loc_rail_scope.py; never write data/; no flag on; no edits in src/ kernel/ api/ intel/ scripts/team_system/; one
store at a time, never > 300 MB; never touch register or ledger.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per sport: static Brier, conditional Brier, their difference, the score-only share of it, and the
                  model-prior share with a game-clustered 95 pct CI and n_eff; denominator = the game-path count
  before        = NBA 0.209 -> 0.159 and MLB 0.241 -> 0.126 with shares ~73 pct / ~99 pct and prior contributions
                  ~0.014 / ~0.001, all quoted with NO n, NO CI and NO archived differential
  bar           = both sports re-derived (or NOT REPRODUCIBLE with the reason), every published figure either
                  reproduced at max abs diff <= 1e-6 or reported NOT REPRODUCED with its honest value, the prior share
                  carrying a CI, and a per-game differential archived for all three arms. A CI covering zero is the
                  expected valid result, published as a retraction
  n             = game paths per sport, printed; >= 30 required for a CI to be reported at all
  eye check     = n/a (S-row); reproduction = the verifier recomputes all three arms' Brier and the prior-share CI
                  from the archived per-game series alone, without rerunning the harness
  must not move = both proof harnesses' behaviour; every landed docs/evidence page byte-identical (this row writes a
                  NEW memo and only PROPOSES a page correction); every threshold; backtest_fwer.jsonl untouched, K
                  unread
NON-TAUTOLOGY: every game path scored stays in the denominator; a pair re-derived after dropping unsettled games is
circular unless the dropped count is printed beside it -- name count and reason or REJECT.
EVIDENCE: docs/evidence/harness/S211_ingame_headline_rederive_2026-09-04.md -- three-arm table, prior-share CIs,
reproduction diffs, NOT VERIFIED list, summary JSON and per-game series (Q9).
TEST: scripts/platformkit/test_s211_headline_rederive.py -- one new per-file test; run only that file.
REPORT: both pairs, reproduction diffs, prior-share CIs, test line, SHA. Commit by pathspec, no push. NEVER PARK.
