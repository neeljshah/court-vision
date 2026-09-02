GAP G125 | sport baseball | worktree a11 | log cx_g125_baseball_reach_recount
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This CORRECTS a published number whose denominator is now known contaminated.
Read docs/evidence/tracking/g117_kbo_studio_quarantine_2026-09-02.md and
g104_baseball_reachability_2026-09-02.md first.
WHAT HAPPENED. G104 measured baseball court_feet reachability at **1 of 120 seeded frames = 0.8
pct**, concluding it is reachable only on rare overhead whole-infield shots. That number fed the
consolidated four-sport reachability verdict. G117 has now eye-confirmed and quarantined **12 KBO
studio and statistics clips, each 0/5 live-action frames**, and reports that **G104's sample
includes 40 of its 120 frames from two of those quarantined clips**.
So a third of G104's denominator is television programming about baseball, not baseball. Frames of a
studio desk cannot show an infield, so they are guaranteed non-reachable and they drag the rate
down mechanically. The published 0.8 pct is therefore wrong in a KNOWN DIRECTION -- too low -- and
the true game-footage rate has never been measured.
BE PRECISE ABOUT WHAT IS AND IS NOT WRONG. G104 itself retained 60 of its 120 frames as non-game
programme content, so it was transparent that its sample contained such frames; what it did not do
is exclude them from the reachability denominator. This is a denominator correction, not a
fabrication, and the memo must say so plainly rather than implying G104 was careless.
DO THIS:
  (a) RECOMPUTE reachability on the G104 sample with the quarantined-clip frames EXCLUDED. Reuse the
      G104 seed, manifest and per-frame labels -- do not draw a new sample and do not relabel. State
      the excluded count and the surviving denominator exactly.
  (b) REPORT BOTH RATES, before and after, with Wilson 95 pct intervals, and say which frames moved.
      A one-in-eighty rate and a one-in-one-hundred-twenty rate are both small, and the honest
      framing is that the correction changes the number without changing the conclusion -- unless it
      does, in which case say so loudly.
  (c) DECIDE WHETHER NON-GAME FRAMES SHOULD BE EXCLUDED AS A RULE, in one paragraph. There is a real
      argument both ways: excluding them measures what the camera can do when there is a game on,
      which is what a calibration project needs; including them measures what a clip delivers end to
      end, which is what a throughput estimate needs. State which question each rate answers so
      neither is misquoted later.
  (d) CHECK THE OTHER SPORTS for the same contamination. G113 measured non-baseball live-action at
      93.3 pct [86.9, 96.7], so the effect should be small elsewhere -- but "should be" is not a
      measurement. State, for the soccer (G101), football (G106) and basketball (G111) censuses,
      how many of their sampled frames were non-game, and whether any of those verdicts is exposed.
      If a verdict IS exposed, name it and stop; recomputing it is a separate row.
DO NOT relabel anything, do not change any threshold, the coordinate contract or any verdict, and do
not un-quarantine any clip.
ACCEPTANCE RULE:
  metric        = baseball reachability rate before and after excluding quarantined-clip frames,
                  with Wilson 95 pct intervals and exact denominators
  before        = 1/120 = 0.8 pct, with 40 of the 120 frames drawn from two quarantined studio clips
  bar           = NO pass bar on the corrected rate. Success is both rates reported with their
                  denominators, the exclusion rule argued in both directions, and the other three
                  censuses checked for the same exposure.
  n             = the G104 sample; state the excluded and surviving counts exactly
  eye check     = not needed for the recount, since G104 and G117 both already looked. Cite their
                  committed frames rather than re-judging them.
  must not move = the G104 sample, seed and labels, the G117 quarantine, every threshold, the
                  coordinate contract, and the soccer, football and basketball verdicts
EVIDENCE: docs/evidence/tracking/g125_baseball_reach_recount_2026-09-0X.md with both rates and
denominators, the exclusion-rule argument, the cross-sport exposure check, and a NOT VERIFIED list.
Commit derived tables under docs/evidence/tracking/g125_recount/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a11, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
