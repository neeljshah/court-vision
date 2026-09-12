VERDICT: REJECT
Candidate: b77b98005; acceptance plus B1-B10/Q1-Q8 only.
ACCEPTANCE input/export PASS: independently reproduced 60/60 unique ticks, 30/kind over 53 windows, 206 rows, 592 comparator boxes, 5 silences, and 206/206 exact unique joins (g409_box_coordinate_cause_2026-09-12/summary.json:87).
ACCEPTANCE causal trace PASS AS PARTIAL: code-derived +60 transform is unfitted, covers all 206 rows, retains 51 residuals/64 non-improvements, and identifies the export boundary without a universal correction claim (g409_box_coordinate_cause_2026-09-12.md:6).
ACCEPTANCE identity/reproduction PASS AS NOT VALIDATED: the memo accurately names the missing stage identities and does not assert exact completion; two Fix 1b rebuilds match (g409_box_coordinate_cause_2026-09-12.md:20; repeats.json:7).
PREMISE PASS: accepted G406 handoff exists; remeasure = 60 ticks, 206 rows, 592 comparator boxes, 51 pairs, 5 silences (G406_VERIFY_att1_ACCEPT_2026-09-11.md:1; tick_accounting.csv:2).
HEADLINE PASS: claimed -58.2 to 1.8 px; reproduced medians -58.203 to 1.797 px, n=51; 0/51 to 44/51 within 15 px; horizontal median 0.0 unchanged (summary.json:73).
EYE CHECK PASS: reviewed all 60 cards, 30/kind, plus all seven construct rows; each card has a separately labelled detector-input panel (g409_box_coordinate_cause_2026-09-12.md:11).
EVIDENCE PASS: all 15 named entries and 60 renders exist; all 209 checksum entries match; largest opened file 78,483,924 bytes (SHA256SUMS:1).
LOC PASS: g409_fix1b.py 191; test_g409_box_coordinate_cause.py 205, both <=300 (g409_fix1b.py:1; test_g409_box_coordinate_cause.py:1).
ADDITIVITY FAIL: repeats.json removes 290 prior schema paths, including baseline_digests and its full table/render manifest, contradicting the preservation claim (repeats.json:1; parent repeats.json:2).
MEMO PASS: explicit NOT VERIFIED list covers required subjects and additional missing identities (g409_box_coordinate_cause_2026-09-12.md:20).
READER CHECK PASS: the only existing test importing the new touched module is the named test (test_g409_box_coordinate_cause.py:103).
TEST PASS: `python -m pytest tests/platformkit/test_g409_box_coordinate_cause.py -q` -> 18 passed in 1.51s.
B1 PASS: all rows, silences, 51 residuals, and 64 non-improvements remain (g409_box_coordinate_cause_2026-09-12.md:8).
B2 FAIL: the prior repeat-receipt fields are removed without aliases; helper overwrites the file with only new fields (g409_fix1b.py:136; g409_fix1b.py:184).
B3 PASS (not applicable): no absent-evidence gate is introduced (g409_box_coordinate_cause_2026-09-12.md:28).
B4 PASS (not applicable): no claim/retry state is introduced (g409_box_coordinate_cause_2026-09-12.md:28).
B5 PASS: replay receipts name isolated scratch and no deployed-tree change (launch_receipts.json:968).
B6 PASS: no module is moved or retired; the only new import resolves in the passing test (test_g409_box_coordinate_cause.py:103).
B7 PASS: all 60 exact-even cards were reviewed, not a head slice (card_panel_manifest.csv:2).
B8 PASS: TOPCUT=60 comes from executed code before residual comparison and is declared unfitted (summary.json:19).
B9 PASS: denominators are 60 unique ticks, 206 unique event keys, and 51 frozen pairs (summary.json:87).
B10 PASS: no acceptance threshold or gate value moved (prereg.md:29).
Q1 PASS: seal fa227df1c8aecd6f46fbc779f71c3f5bedb0f76bdf252317e95b76e87668d697 recomputes and predates measurement (prereg.md:36).
Q2 PASS (not applicable): diagnostic is uncharged and reports no K (prereg.md:33).
Q3 PASS: bars remain byte-identical and unmet identity is reported NOT VALIDATED (G409_spec.md:23).
Q4 PASS (not applicable): no OOS score or learner is introduced (G409_spec.md:21).
Q5 PASS (not applicable): no AHEAD result is asserted (G409_spec.md:21).
Q6 PASS: independent scan of all 124 changed text paths found zero hits (q6_scan.json:441).
Q7 PASS: sampled n=60 and all seven construct cases are exhaustively retained (construct_cases.csv:2).
Q8 PASS: the full premise was remeasured before trace adjudication (g409_box_coordinate_cause_2026-09-12.md:5).
CORRECTION: restore the parent repeats.json fields/runs verbatim, nest Fix 1b receipts additively, and test the real artifact for baseline_digests, manifest, schema, and unchanged prior runs (g409_fix1b.py:124).
RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G409 | 60 ticks and 206 rows bind; vertical median -58.203 to 1.797 px (n=51), identity incomplete; repeat receipt removes 290 prior fields | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: Candidate b77b98005 commits 113 root-level replay-scratch files omitted from its 87-path scan and 209-entry checksum receipt; independent vocabulary scan found zero hits.
NEW GAP: Seven controls execute copied statements rather than archived route functions (construct_cases.csv:2).
