VERDICT: REJECT
Candidate: ebc748c57cf1c988f9c41e30ada887746a76065c.
PREMISE PASS: reproduced G361 EXACT 19 / ALIGNED 21 / UNKNOWN 844 and 0/884 known producer bindings; G369 snapshot has 55 fresh rows and 35 recorded on-disk attempts (g361_source_identity_2026-09-09/summary.json:31; g361_source_identity_2026-09-09/ledger_links.csv:1; g369_prospective_identity_2026-09-09.md:7-10).
METRIC PASS (PARTIAL): claimed 32/35, 8 source ids, 4 competitions; reproduced 32/35, 8, 4, with all 17 source fields populated (g369_prospective_identity_2026-09-09/summary.json:3-14; g369_prospective_identity_2026-09-09/sources.csv:1).
ABSENT PASS: all three attempts are counted with reasons; reproduced PINNED 32 / ABSENT 3 (g369_prospective_identity_2026-09-09/attempts.csv:9,10,26; g369_prospective_identity_2026-09-09.md:17).
ALIGNMENT PASS: claimed and reproduced 996 unique landmarks over 32 sections, 31-32 each, max 0.0000 native frames, all within bar (g369_prospective_identity_2026-09-09/alignment.csv:1; g369_prospective_identity_2026-09-09.md:25).
REPEATABILITY PASS: claimed and reproduced identical export bytes and SHA-256 57eb12d26dc30417cd700ac64e378f78eb0cd513e77e587a588f2cbe6528c09f (g369_prospective_identity_2026-09-09/export_hashes.json:2-5).
COLLISIONS PASS: claimed and reproduced 0 collisions and 0 unparseable ids across 32 unique pairs (g369_prospective_identity_2026-09-09/summary.json:5,15).
EYE CHECK PASS: inspected all 32 evenly exhaustive strips; 32 unique ids, 1280x384, max 164170 bytes <= 204800 (g369_prospective_identity_2026-09-09.md:27).
EVIDENCE PASS: every required path exists and all 44 recorded file digests reproduce raw or LF-normalised (g369_prospective_identity_2026-09-09/SHA256SUMS.txt:1).
IMMUTABILITY PASS: candidate changes only row code/evidence and reports protected paths unchanged (g369_prospective_identity_2026-09-09.md:4).
MEMO PASS: 53 lines <= 60 and a NOT VERIFIED list is present (g369_prospective_identity_2026-09-09.md:48-53).
LOC PASS: touched Python file is 247 lines <= 300 (scripts/platformkit/tracking/g369_prospective_identity.py:247).
B1 PASS: failed bindings remain named in the 35-attempt denominator (scripts/platformkit/tracking/g369_prospective_identity.py:139-162).
B2 FAIL: candidate removes manifest field `rule` when adding `crop_rule`, without an alias (scripts/platformkit/tracking/g369_prospective_identity.py:108; g369_prospective_identity_2026-09-09.md:32).
B3 PASS: missing input becomes a recorded ABSENT attempt; no operational gate is added (scripts/platformkit/tracking/g369_prospective_identity.py:146-155).
B4 PASS: reporting commands have no item-claim lifecycle (scripts/platformkit/tracking/g369_prospective_identity.py:139-221).
B5 PASS: pod work is compute-only in the lane and no deploy tree write is reported (g369_prospective_identity_2026-09-09.md:4,30).
B6 PASS: no module was moved or retired (scripts/platformkit/tracking/g369_prospective_identity.py:1).
B7 PASS: all 35 eligible attempts and all 32 pinned renders are used (g369_prospective_identity_2026-09-09.md:14,27).
B8 PASS: exact byte identity is not a fitted residual (g369_prospective_identity_2026-09-09.md:25).
B9 PASS: denominator is 35 distinct attempted sections, with 32 distinct source-offset pairs (g369_prospective_identity_2026-09-09/summary.json:3,14).
B10 PASS: the sealed 30-section / 10-game / 3-competition bar is retained (g369_prospective_identity_2026-09-09/g369_prereg_2026-09-09.md:31; g369_prospective_identity_2026-09-09.md:16).
Q1 PASS: all three seals match and their commit predates measurement (g369_prospective_identity_2026-09-09/g369_prereg_2026-09-09.md:80; g369_prospective_identity_2026-09-09.md:3,32).
Q2 PASS (not applicable): no charged trial or K is used (g369_prospective_identity_2026-09-09.md:3).
Q3 PASS: no bar or threshold moved (g369_prospective_identity_2026-09-09.md:16,29).
Q4 PASS (not applicable): no OOS model comparison or meta-learner is scored (g369_prospective_identity_2026-09-09.md:25).
Q5 PASS (not applicable): no AHEAD result is claimed (g369_prospective_identity_2026-09-09.md:1).
Q6 FAIL: automated scan found one forbidden-literal line outside a retraction context (g369_prospective_identity_2026-09-09.md:44).
Q7 PASS: n=35 is exhaustively attempted and all 32 pinned sections are rendered (g369_prospective_identity_2026-09-09.md:14,27).
Q8 PASS: premise is recorded before PIN and independently reproduces (g369_prospective_identity_2026-09-09.md:6-14).
TEST PASS: `python -m pytest tests/platformkit/test_g369_prospective_identity.py -q -p no:cacheprovider` -> 5 passed.
TEST PASS: `python -m pytest tests/platformkit/test_g361_strips.py -q -p no:cacheprovider` -> 2 passed (field-reader check); import census found no other touched-module test.
CORRECTION DIFF scripts/platformkit/tracking/g369_prospective_identity.py:108: -crop = {"crop_rule": "TOPCUT = 60", ...}; +crop = {"rule": "TOPCUT = 60", "crop_rule": "TOPCUT = 60", ...}; then regenerate dependent artifacts and digests.
CORRECTION DIFF docs/evidence/tracking/g369_prospective_identity_2026-09-09.md:44: -[embedded scan command]; +Q6 automated scan: 0 findings.
CORRECTION DIFF docs/evidence/tracking/g369_prospective_identity_2026-09-09.md:1: -but over 8 distinct source ids; +but only 8 distinct source ids.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-10 | tracking | G369 | reproduced 32/35 fully bound sections; 8 source ids; 4 competitions; 996/996 exact landmarks at 0.0000 frames; 0 collisions; exports byte-identical; B2 alias missing and Q6 scan 1 finding | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: A1 master rerun is unavailable pre-land because master contains neither the G369 module nor its test; candidate and reader tests were run in this worktree.
NEW GAP: verifier sandbox cannot create the linked-worktree index lock; direct git add and the lane commit broker both returned permission denied.
