VERDICT: PARTIAL -- the sealed 22-unit premise is NOT EVALUABLE (10 of 22 units irrecoverable); on the 12 recoverable units the line-family cue is ANTI-correlated and the surface cue rests on one positive; the held-out set is NOT SEALED because the prereg balance rule is unsatisfiable under the sealed thresholds.
# G360 court-presence cue -- finisher phase 1 (premise + held-out attempt)
Spec: docs/evidence/tracking/specs/G360_spec.md. Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md (A/B; Q1, Q3, Q6, Q7).
Preregistration: docs/evidence/tracking/g360_prereg_2026-09-08.md; LF seal sha256 62affa7b992fbf1b894256287cb89032b859bb5b4a4c5acb1ce394a6616386eb -- unchanged, not edited.
Machine: POD 213.181.122.2, worktree /workspace/wt/a3 (cv2 4.14, numpy 2.1.2). Scratch /workspace/g360_scratch, 580 MB, deleted after this memo.

## Premise input recovery (the binding before-condition)
The G350 sources are gone from the pod corpus (a live rotating queue) and from both staged PC corpora. Of the 15 distinct sources behind the 22 adjudicated units:
- 9 sources / 12 units RECOVERED. One (basketball__eurocup-mhi_fuXUPRE_s90) was byte-identical on the PC staging corpus, its sha256 equal to the recorded video_sha256, and was uploaded. Eight were re-fetched with the pod yt-dlp recipe (HLS rungs 270/312) on 2026-09-09. Every re-fetch reproduced the RECORDED byte size EXACTLY (bytes_match YES, 12 of 12 rows) at the recorded native 1920x1080; the container sha256 differs on the eight re-fetches (remux metadata), so identity rests on byte size plus the eye check, never on the container hash. Format id, fetch UTC, avg_frame_rate, container frame count, container start_time (0.000000 everywhere), requested section start and frame index are in source_identity.csv.
- 6 sources / 10 units IRRECOVERABLE: nba__0022500081_s357/s2436/s4812, nba__0022500592_s2700, nba__0022500621_s2100/s7200. They are named by NBA game id only; no video id is recorded in any G350 artifact, the pod holds their tracking outputs but no video, and neither staged PC corpus has them. One of the two USABLE_WIDE reference positives (nba__0022500592_s2700) is in this set. The sealed command reports the first of them as ABSENT-IN-WORKTREE and stops.
EYE CHECK (required): eyecheck_recovered_01.jpg and _02.jpg place each recovered representative frame beside its committed G350 sheet tile for all 12 units. All 12 match, scoreboard digits included. The committed sheets were NOT used as cue input: their representative tile is 360x203 from a 1920-wide source, and Canny with a minimum segment length of 8 per cent of frame width cannot see court lines about one pixel wide after that reduction.

## Premise table -- DESCRIPTIVE, 12 of 22 units, 1 positive; NOT the sealed premise
Rank AUC with USABLE_WIDE positive: line-family cue 0.090909091 ; surface cue 1.000000000.
Rule derived by choose_rule: family_floor 000001, surface_floor 0.459872685.
Top of the surface ranking (label, surface, families): USABLE_WIDE 0.459873 fam 1 | CLOSEUP 0.378585 fam 3 | CROWD_GRAPHICS 0.135226 fam 2 | CROWD_GRAPHICS 0.122808 fam 3 | CLOSEUP 0.121314 fam 1 | CROWD_GRAPHICS 0.105610 fam 5.
Why this does not establish the premise:
1. It is 12 of the sealed 22 units and 1 of the 2 reference positives. The sealed input cannot be reconstructed, so no sealed premise verdict exists (Q3: the input is not the sealed input).
2. The line-family cue is refuted in the opposite direction. Court views are not the frames carrying the most long-line families; billboards, LED ribbons, title cards and crowd rails carry more.
3. The surface AUC of 1.000000000 is one positive outranking eleven negatives, and choose_rule set surface_floor to the surface value of that single positive. A threshold fitted to one point is self-fit (contract B8), and the runner-up is a CLOSEUP at 0.378590.

## Held-out set: NOT SEALED -- the prereg balance rule is unsatisfiable
The SEALED rule applied to an even interior sample (12 positions per section, never a head slice) over the whole available population -- 384 frames, 32 sections, 16 videos, 8 competition tags, balance_probe.csv -- predicts COURT 034, NON_COURT 005, ABSTAIN 345; additive per-mille 089 / 013 / 898. The prereg requires at least 60 predicted COURT and at least 60 predicted NON_COURT. NON_COURT requires families below the floor, that is ZERO long line segments in every orientation bin, seen in 013 per mille of frames and only on dark or near-static ones. Reaching 60 needs roughly 4,600 evenly sampled frames from 32 available sections, and the class so obtained would be blank frames rather than a representative non-court class (contract B9). Lowering the floor to make the branch reachable would move a sealed threshold (Q3). The set was therefore NOT sealed, NOT built and NOT rated; no sheet was produced and no rater was invoked.

## HONEST LIMITATIONS
Model raters proxy for human labels; court presence does not establish geometric validity; 200 frames are a screening; the 22 premise units are excluded from any future held-out set. Byte-size equality plus an eye check is strong evidence of the same media, not proof of identical bytes. Delta sign convention: improvement = baseline loss minus candidate loss, positive = candidate better; this classification audit has no paired-loss delta.

## NOT VERIFIED
- The sealed 22-unit premise AUC. It cannot be computed while 10 of 22 units are irrecoverable.
- Any precision, recall, interval, kappa, confusion or abstention estimate for the cue; n is below the Q7 rail of 30 and nothing was rated.
- Whether the surface cue separates court from non-court at all. One positive cannot show it.
- Any feeder proposal or G352 amendment, which requires a VALIDATED result.

## Artifacts (LF sha256)
premise.csv dd2b04aa12a9f98ed887800fa0c3ccba56571d93f2f37e88d0a1da0a490d0ab9 ; source_identity.csv 9dd8cfad0a1f193b4dfa225e95add99f6fee97bfd07b7b51d81e27482ea069c4
balance_probe.csv 85ba9477bbb8f238458c70356275e7d36c104dca3c16bd6431f3c9f5302c4b21 ; eyecheck_recovered_01.jpg d10d9fc21ae101ec07b9c6e01e09cf1ffd7ca1043728decea58ab29a38e74734
eyecheck_recovered_02.jpg fbdd5ef5a7d34d02ef48b62d0dffedbe9b02a0b9af8ef74a6828a00f27d540c6. Both images are under 200 KB.
No sealed file, no landed content gate, no router threshold, no flag, no results ledger and no register row was touched. src/, api/, kernel/, intel/ and data/ are unchanged.
TEST: python -m pytest tests/platformkit/test_g360_court_presence_cue.py -q -p no:cacheprovider --confcutdir=tests/platformkit -> 3 passed in 1.31s
Wall time 00:30 (2026-09-09 17:47Z to 18:17Z), about 00:10 of it the section re-fetch.
NEXT ROW (not this one): a court-presence cue learned from labels, or a rule whose negative branch is reachable. Both need a premise measurable on inputs that still exist when the finisher runs, so the successor spec must pin its own sources before the corpus rotates.
