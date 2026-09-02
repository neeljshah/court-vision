GAP G113 | sport baseball | worktree a11 | log cx_g113_nongame_content_share
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. A CORPUS QUALITY census, triggered by an incidental finding. Read
docs/evidence/tracking/g104_baseball_reachability_2026-09-02.md and
g99_corpus_sport_audit_2026-09-02.md first.
THE INCIDENTAL FINDING. G104 sampled 120 seeded frames across the mlb, kbo and npb clips to measure
reachability, and had to explicitly retain **60 of those 120 as non-game programme content** --
studio segments, adverts, replays, graphics, pre-game. That is half the sampled frames of the
largest corpus block, and it was noticed in passing rather than measured on purpose. If it holds
across the corpus it silently deflates every per-frame rate anyone computes: a detector scored over
a clip that is half studio footage is being judged on frames where there is nothing to detect.
NOTE WHAT G99 DID AND DID NOT SETTLE. G99 eye-audited all 66 corpus clips at three interior frames
each and found exactly 4 sport mislabels and no others. That answers "is this the right SPORT". It
does NOT answer "is this game action", and three frames per clip cannot measure a within-clip share.
Different question, different sample.
MEASURE:
  (a) Seeded stratified sample of >= 150 frames across ALL sports, not only baseball, so the
      baseball share can be compared against a baseline. State the seed and per-sport counts.
  (b) Classify each frame by eye into a SMALL fixed vocabulary you declare up front -- for example
      live_action, replay, studio_or_desk, advert, graphic_or_scoreboard, crowd_or_filler,
      pregame_warmup. Declare it BEFORE labelling; inventing a category to fit an awkward frame is
      how a census becomes a rationalisation.
  (c) Report the live-action share per sport with Wilson 95 pct intervals, and say whether
      baseball's is an outlier against the others or whether roughly half is normal for broadcast.
      That comparison is the deliverable -- 50 pct non-game is only alarming if other sports are
      not also near 50 pct.
  (d) NAME THE EXPOSURE. Which published per-frame numbers are computed over whole clips and would
      therefore be diluted by this? Name them and quantify the dilution where you can. Do NOT
      recompute them here.
  (e) If the share is large, say in one paragraph what could be done about it -- a content gate at
      acquisition, a live-action filter before scoring, or a per-clip usable-fraction recorded in
      the ledger. Recommend, do not build. Note that scripts/platformkit/footage_content_gate.py
      already exists; read it and say whether it already covers this and simply is not applied.
DO NOT delete, re-download, re-track or re-score any clip, do not change any threshold, and do not
touch the coordinate contract.
ACCEPTANCE RULE:
  metric        = live-action share per sport with Wilson 95 pct intervals over >= 150 seeded frames
  before        = 60 of 120 baseball frames non-game, observed incidentally by a row measuring
                  something else; no cross-sport baseline
  bar           = NO pass bar. Success is the census with a preregistered vocabulary, the per-sport
                  comparison, and the exposure named. "Half non-game is normal for broadcast across
                  every sport" is a full success and it defuses the concern.
  n             = >= 150 seeded frames spanning every sport in the corpus; state the seed and the
                  per-sport counts
  eye check     = this row IS the eye check. Commit every frame you classified.
  must not move = every threshold, the coordinate contract, every verdict, every clip, and the G99
                  and G104 results
EVIDENCE: docs/evidence/tracking/g113_nongame_content_share_2026-09-0X.md with the preregistered
vocabulary stated first, the per-sport shares and intervals, the exposure list, the
footage_content_gate assessment, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g113_content/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a11, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
