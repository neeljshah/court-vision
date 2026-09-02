GAP G108 | sport football soccer | worktree a5 | log cx_g108_relabel_and_recompute
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. A REMEDIATION plus the recompute of a published number that is
now known wrong. Read docs/evidence/tracking/g99_corpus_sport_audit_2026-09-02.md and
g47_contract_rejection_census_2026-09-02.md first.
WHAT G99 ESTABLISHED. All 66 live corpus clips were eye-audited at three interior frames each.
Exactly 4 are mislabelled and they are the same four G95 had already surfaced: football-labelled
clips that are association soccer. Zero further mismatches across the other seven sports. The cause
is a naming collision at the source (association football versus American football), not a repo
bug, which is why the fix is cheap and why it is worth doing properly once.
WHAT IS BROKEN BY IT, and this is the real deliverable:
  - G47's census reports football 30/42 and soccer 15/25 contract-only rejections. Four football
    clips being soccer moves games between those two groups, so BOTH numbers are wrong, and so is
    the derived claim that football is the largest single rejection block -- a claim that was used
    to dispatch G95 and shapes the calibration programme.
  - Every harness verdict computed on those four clips used FOOTBALL bounds. An oob rate for a
    soccer pitch measured against football bounds is meaningless, not merely imprecise.
DO THIS:
  1. RELABEL the four clips to soccer, in whatever the label of record is. Determine first WHERE the
     sport label actually lives for a corpus clip -- the filename prefix, the queue entry, the
     daemon ledger row, or several of these -- and say so. If the label is duplicated across
     places, they must all move or the mismatch simply reappears; if you fix only one, say which
     ones you did not fix and why.
  2. RECOMPUTE the G47 football and soccer contract-rejection counts on the corrected labels.
     Report before and after for both sports, and state plainly whether football is still the
     largest block. Do not edit the G47 memo; publish the corrected figures in your own memo and
     let the register carry the correction.
  3. RE-SCORE the four clips under soccer. Report their verdicts before (as football) and after (as
     soccer). Expect them to remain coordinate-contract rejections -- G91 and G101 established that
     soccer court_feet is unreachable from this corpus -- but MEASURE it rather than assuming, and
     if any verdict changes in a way you did not expect, that is the finding.
  4. PREVENT THE RECURRENCE, minimally. G99 says the collision is at the source, so the cheapest
     durable fix is at queue-build or acquisition time. Propose it in one paragraph and implement it
     only if it is genuinely small; if it is not small, write the proposal and stop. Do NOT build a
     sport classifier -- a detector deciding the sport would be circular, since detectors are chosen
     BY the label.
DO NOT delete or re-download any clip, do not re-track anything, do not change any harness
threshold, and do not touch the coordinate contract. Renaming is the change; retracking is not, and
the existing tracking tables stay as evidence of what the wrong label produced.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = corrected football and soccer contract-rejection counts, before and after, and the
                  four clips' verdicts before and after relabelling
  before        = football 30/42 and soccer 15/25, both computed on a corpus with 4 clips in the
                  wrong sport
  bar           = the four clips carry the soccer label in every place the label lives, the
                  corrected counts are reported with their denominators, and the four re-scored
                  verdicts are reported. "Football is still the largest block" and "it is not" are
                  equally good outcomes; report what the arithmetic gives.
  n             = the 4 mislabelled clips, and the full G47 denominators (42 football, 25 soccer)
                  restated as they become after the move
  eye check     = not needed for the relabel; G99 already did it at three frames per clip and its
                  contact sheets are committed. Cite them rather than redoing them.
  must not move = every clip file's CONTENT, every harness threshold, the coordinate contract, the
                  G99 audit labels and sheets, and the existing tracking tables
EVIDENCE: docs/evidence/tracking/g108_relabel_and_recompute_2026-09-0X.md with where the label lives,
what you changed, the corrected counts with denominators, the four before/after verdicts, the
recurrence proposal, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g108_relabel/ BEFORE reporting (A7).
CAUTION FROM TODAY: several lanes wrote evidence directly into the MAIN working tree and one dropped
two ledger rows another session had appended, which had to be restored by hand. Work inside your
worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: the four clips live on the pod. A RENAME is permitted for exactly those four files and nothing
else. Never kill anything -- the track daemon and seven footage bridge lanes are live, and the
daemon watches the stage directory, so do not move anything into data/footage_bridge.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a5,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
