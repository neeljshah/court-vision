GAP G99 | sport all | worktree a5 | log cx_g99_corpus_sport_audit
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. A DATA INTEGRITY audit. It exists because a survey found
something nobody was looking for.
THE FINDING THAT TRIGGERED THIS. G95 set out to survey football landmark visibility across the nine
football-labelled pod clips and reported, incidentally, that **four of those nine clips are
actually soccer footage** -- 48 of its 108 sampled frames. Read
docs/evidence/tracking/g95_football_calibration_survey_2026-09-02.md first and confirm which four.
WHY THIS IS SERIOUS AND NOT A CURIOSITY. Every per-sport number in this repo is computed by
grouping on the sport label. If the label is wrong, the number is wrong, and it is wrong in a way
no amount of careful statistics inside the group can detect. Concretely at risk:
  - The G47 contract-rejection census, which reports football 30/42 and soccer 15/25. If four
    football clips are soccer, both figures are wrong and so is the "largest single block" claim
    that G95 was dispatched on.
  - Every harness verdict on a mislabelled clip, because the harness picks bounds, adapter and
    thresholds BY SPORT. A soccer pitch scored against football bounds produces an out-of-bounds
    rate that means nothing.
  - The bridge lane assignment, since lanes are disjoint by sport and a mislabelled game is pulled,
    tracked and scored by the wrong lane end to end.
THE TASK: audit the sport label of EVERY clip in the corpus, not just the football ones. The pod
holds 63 clips in data/footage_corpus across 8 sports (9 football, 12 mlb, 11 kbo, 6 npb, 6
ncaa_basketball, 5 soccer, 9 tennis, 5 wnba) and 184 distinct games in
data/tracking/track_daemon_ledger.jsonl. Do the corpus first; it is bounded and it is what future
work reads.
  (a) For each clip, sample at least 3 frames spread across the file and identify the sport BY EYE.
      One frame can be a graphic, a crowd shot or an advert. Commit a contact sheet per clip.
  (b) Report a confusion table: labelled sport versus actual sport, with counts. Name every
      mislabelled clip by its exact game_id.
  (c) For each mislabel, say WHERE the label came from -- the queue file, the bridge lane that
      pulled it, the filename prefix, or the daemon's SPORT_ADAPTER routing -- and whether the
      label was wrong at acquisition or corrupted later. That distinction decides whether the fix
      is in queue building or in the bridge.
  (d) State plainly which published numbers are invalidated and by how much, at minimum G47's
      football and soccer counts. Do NOT recompute those numbers in this row; name them and their
      exposure so a later row can redo them on a clean corpus.
DO NOT rename, move, delete or re-track any clip, and do not edit any queue file. A mislabelled
clip is evidence right now and moving it destroys the ability to check this audit. The remediation
is a separate row and it needs this census first.
BEWARE THE OBVIOUS TRAP: football and soccer are called football by different people, and the queue
expander pulls from search terms. A clip labelled football that shows a soccer pitch may be a
naming collision at the SOURCE rather than a bug in this repo. If that is what you find, say so --
it is a different and cheaper fix, and it predicts exactly which other sports are at risk.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = number of corpus clips whose eye-identified sport differs from their label, with
                  the full confusion table
  before        = 4 of 9 football clips found mislabelled by a survey that was not looking for it;
                  the other 54 clips unaudited
  bar           = there is NO pass bar. Success is all 63 clips audited by eye, the confusion table
                  reported, every mislabel named with its game_id and suspected origin, and the
                  invalidated numbers listed. Finding zero further mislabels is a fully successful
                  and reassuring outcome.
  n             = all 63 corpus clips, >= 3 frames each; state the exact clip count you found, since
                  it may have grown -- the footage bridge is live and staging new games right now
  eye check     = this row IS the eye check and nothing else substitutes. A detector deciding which
                  sport it is would be circular: the detectors are chosen BY the label.
  must not move = every clip file and its name, every queue file, every harness threshold, the
                  coordinate contract, and every existing verdict
EVIDENCE: docs/evidence/tracking/g99_corpus_sport_audit_2026-09-0X.md with the confusion table, the
per-mislabel origin, the invalidated-numbers list, the contact sheets, and a NOT VERIFIED list.
Commit sheets under docs/evidence/tracking/g99_corpus_audit/ BEFORE reporting (A7).
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the track daemon and seven footage bridge lanes are live and
new clips are landing while you work, which is why you must state the count you actually saw.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a5,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
