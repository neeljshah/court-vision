VERDICT: REJECT
Candidate: a7af422626f7b0a5c8273ca0a7e2eac6152ecc55; scope is the G386 acceptance rule plus B1-B10 and Q1-Q8.
ACCEPTANCE FAIL: draw.csv:2-31 assigns full_replay_source to 30/30, but g386_pin_copy_one_pass_2026-09-10.md:20 says every full replay copy was released and none was preserved off-pod. Required reader objects retained are 0/30, omitted from the metric table at :10-18 against G386_spec.md:17,20,23.
ACCEPTANCE FAIL: g386_pin_copy.py:79-89 sets pixel_opened from final.is_file, and :141-145 marks CAPTURED before the decoder runs at g386_capture_run.py:140-157. This is not receiver pixel-open acknowledgement as required by G386_spec.md:10,17,19.
ACCEPTANCE PASS: independently parsed artifacts reproduce 30/30 CAPTURED, 30/30 byte matches, 30/30 post-capture pixel matches, 0 sampled false receipts, 6/7 exact controls, and identical exports (memo:11-17).
PREMISE PASS: census.csv:2-1195 reproduces 33 retained of 1,194 sections over 18/182 videos, 27.6 per mille retained and 1,161 absent; named pre-existing tools do not implement receiver readback (memo:4).
RENDERS PASS: 30 unique JPEGs and receipts reproduce 30/30 digests and 1920x1080 dimensions; evenly inspected a01,a07,a13,a18,a24,a30 (memo:18,29-56).
LIVE COHORT PASS: artifacts reproduce 16/16 captures, receipts and pixel matches, then 16/16 originals absent over ticks 44-109, a 65-minute interval (memo:21).
NOT VERIFIED PASS: the memo carries an explicit limitation list at g386_pin_copy_one_pass_2026-09-10.md:23-27.
LOC PASS: candidate touches no .py; supporting g386_pin_copy.py 161, g386_capture_run.py 235, g386_controls.py 121, test 115, all <=300.
TEST PASS: `python -m pytest tests/platformkit/test_g386_pin_copy_one_pass.py -q -p no:cacheprovider` -> 9 passed in 1.49s.
IMPORTER PASS: test_g386_pin_copy_one_pass.py is the only test importing the three G386 support modules; it was run alone.
B1 PASS: all 30 sealed attempts and all 7 controls remain in attempts.csv:2-31 and faults.csv:2-8.
B2 FAIL: a7af42262~1 summary.json:3-4 had n_attempts and status; candidate summary.json:1-105 removes both without aliases. No code reader exists, but removal itself is automatic; memo:26 incorrectly says no schema changed.
B3 PASS: absent and changed sources remain LOST/CHANGED and are never substituted (g386_pin_copy.py:102-115; test:24-43).
B4 PASS: candidate adds no claim or retry queue behavior; receipt versions differ on retry (test:68-78).
B5 PASS: the candidate changes evidence only and memo:27 records no deployed-tree write or restart.
B6 PASS: no module was moved or retired by a7af42262.
B7 PASS: recomputed draw equals the sealed 30-point even draw across all 33 available rows, including first and last; renders map uniquely to all attempts (memo:6,17-18).
B8 PASS: no fitted residual is used as independent evidence.
B9 PASS: 30 unique sections, source digests, version IDs, pixel digests and render names reproduce from draw/source_identity/receipts/pixel_checks.csv.
B10 PASS: no harness or threshold is touched; the 6/7 control result is disclosed without changing the bar (memo:15,22).
Q1 PASS: prereg blob prefix recomputes to embedded seal 517122d019f0174592ff76e2a4d9eb5d948bacf58a995cf50964e14a4c3ac227; commit 7c01d57e3 predates the 02:02:03Z census (memo:3-4).
Q2 PASS (N/A): this is not a charged trial and has no K metric.
Q3 PASS: spec bars are unchanged and the failed control is reported unmet (memo:2,15,22).
Q4 PASS (N/A): no OOS model comparison is scored.
Q5 PASS (N/A): no AHEAD result is claimed.
Q6 PASS: character-built whole-word scan of candidate-added text found 0 prohibited claim-language or retracted-number hits.
Q7 PASS: sampled n is 30 distinct sections across 18 videos; constructed controls are separate (memo:6,17,22).
Q8 PASS: premise was measured first; census recomputation is 33/1,194 retained and the G377 restore utility does not prove live one-pass capture plus versioned receiver acknowledgement (memo:4).
CORRECTION 1 (minimal diff): summary.json add `"n_attempts": 30` and `"status": "PARTIAL"`; do not remove the prior fields.
CORRECTION 2 (minimal diff): memo:2 and its metric table must report required full replay objects retained 0/30; memo:20 must say 33/33 objects opened and 30/30 image objects were 1920x1080.
CORRECTION 3 (minimal diff): receiver must actually decode the requested pixel before acknowledgement, CAPTURED must depend on that result, and the spec test must cover byte-valid but undecodable receiver content before remeasurement.
2026-09-10 | tracking | G386 | premise 33/1,194 retained; sealed 30/18 draw had 30/30 transient byte and post-capture pixel matches, 0/30 required full replay objects retained, controls 6/7; live census 16/16 originals absent after 65 minutes | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: G379's exact 16/29-at-30-min before-state has no committed per-source after-state; the later G386 census shows 0/29 retained, which supports instability but cannot reconstruct that earlier snapshot.
