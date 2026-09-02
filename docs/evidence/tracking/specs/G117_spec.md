GAP G117 | sport baseball | worktree a11 | log cx_g117_kbo_studio_quarantine
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. A CORPUS CLEANUP with a measured cause. Read
docs/evidence/tracking/g113_nongame_content_share_2026-09-02.md first.
WHAT G113 MEASURED. G104 had noticed in passing that 60 of 120 sampled baseball frames were non-game
programme content. G113 checked whether that was normal by censusing >= 150 seeded frames across all
sports with a preregistered vocabulary, and the answer is NO: **non-baseball live-action share is
98/105 = 93.3 pct, Wilson 95 pct [86.9, 96.7]**, while baseball sits far below it. The deficit is
not a broadcast-wide property. It is **concentrated in KBO studio and statistics programming** --
some clips in the corpus are television shows about baseball, not baseball games.
WHY IT MATTERS: every per-frame rate computed over a whole clip is diluted by frames with nothing to
detect. A detector scored across a studio segment is being judged on frames where the correct output
is nothing. That silently deflates coverage, detections-per-frame and every derived quality number
for the whole baseball block, which is the largest rejection block in the corpus at 66/93.
DO THIS:
  (a) IDENTIFY the offending clips by name, from the G113 labelled frames plus whatever additional
      sampling you need. A clip is in scope if it is predominantly studio or statistics programming
      rather than game action. State your threshold for "predominantly" BEFORE you apply it, and
      justify it in one clause.
  (b) CONFIRM each candidate by eye at >= 5 spread frames before naming it. G99's audit used three
      interior frames per clip and answered a different question (which SPORT); this one is about
      what is happening within the clip and needs its own look. Commit contact sheets.
  (c) QUARANTINE, do not delete. data/footage_quarantine/ already exists in track_daemon.py as the
      destination for rejected material -- read how it is used and follow that convention. A
      deleted clip cannot be re-checked, and today four separate measurements died because a source
      was gone; do not add a fifth.
  (d) ASSESS THE EXISTING GATE. scripts/platformkit/footage_content_gate.py already exists. G113 was
      asked to say whether it already covers this and simply is not applied -- read its verdict,
      confirm it against the code, and say plainly whether the fix is "apply the gate we have" or
      "the gate does not detect studio content". Do not write a second gate if the first one works.
  (e) NAME THE EXPOSURE: which published baseball numbers were computed over these clips. Do NOT
      recompute them here; name them and their denominators so a later row can.
DO NOT delete any clip, re-track anything, change any threshold, or touch the coordinate contract.
Do not move anything into data/footage_bridge -- the daemon watches that directory and would pick it
up.
ACCEPTANCE RULE:
  metric        = number of corpus clips identified as predominantly non-game, confirmed by eye,
                  with their live-action share
  before        = baseball live-action share far below the 93.3 pct [86.9, 96.7] non-baseball
                  baseline, concentrated in KBO studio programming
  bar           = NO pass bar. Success is the clips named and eye-confirmed, quarantined rather than
                  deleted, the existing gate assessed, and the exposure named. "The gate already
                  covers this and was simply never applied" is the best possible outcome.
  n             = >= 5 eye-confirmed frames per candidate clip; state the clip count and your
                  predominance threshold
  eye check     = REQUIRED per clip. Commit the sheets.
  must not move = every clip's CONTENT, every threshold, the coordinate contract, every verdict, the
                  G113 labels, and anything in data/footage_bridge
EVIDENCE: docs/evidence/tracking/g117_kbo_studio_quarantine_2026-09-0X.md with the named clips, their
shares, the sheets, the gate assessment, the exposure list, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g117_studio/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you change code; run only that file. Never a full pytest.
POD: a MOVE into data/footage_quarantine/ is permitted for clips you have eye-confirmed, and nothing
else. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a11, no push. Report the sha.
SHARED MODULE: track_daemon.py is under the token; READ it for the quarantine convention, do not
change it.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
