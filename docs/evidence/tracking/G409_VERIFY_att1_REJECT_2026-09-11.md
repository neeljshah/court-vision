VERDICT: REJECT
Candidate: 75050b6a5; acceptance and B1-B10/Q1-Q8 only.
Input/export binding: PASS. Reproduced 60 distinct ticks (30/kind), 206 rows, 51 frozen pairs, 5 silent ticks, and a 206/206 exact full-key join with no absent, duplicate, or substituted row (g409_box_coordinate_cause_2026-09-12/summary.json:87).
Causal coordinate trace: PASS. Code-derived TOPCUT=60 gives dy median -58.2 -> 1.8 px on 51 pairs/28 frames; 44/51 end within 15 px, while x remains 37/51; all 206 rows and seven controls remain (g409_box_coordinate_cause_2026-09-12/summary.json:19).
Identity/reproduction: FAIL. The bar requires complete stage records (specs/G409_spec.md:23), but the observer captures crop, detector box, and export only; it omits model-call/cache identity, model-input key/shape, actual CSV values, and serialized join key (../../../scripts/platformkit/tracking/g409_observer.py:43).
Eye check: FAIL for that same bar. I reviewed all 60 evenly distributed native cards; they show stored, mapped, and comparator boxes, but not actual detector input separately as required (specs/G409_spec.md:15).
Claimed/reproduced: 60/60 ticks, 206/206 joins, 51 pairs, dy -58.2 -> 1.8 px, and two identical rebuilds agree (g409_box_coordinate_cause_2026-09-12/repeats.json:148).
Independent integrity: 60/60 retained sources rehashed while streamed; 153/153 SHA256SUMS entries exist and match; largest source was 78,483,924 bytes.
Test: `python -m pytest tests/platformkit/test_g409_box_coordinate_cause.py -q` -> 15 passed in 1.34s.
B1 PASS: all rows, silence, residuals, and 64 non-improving rows remain; no outcome filtering (g409_box_coordinate_cause_2026-09-12/summary.json:2).
B2 PASS: additions are G409-local; no field/status rename or removal, and the only reader is the named full-package test (tests/platformkit/test_g409_box_coordinate_cause.py:1).
B3 PASS (not applicable): no gate or absent-evidence quarantine is introduced (g409_box_coordinate_cause_2026-09-12.md:36).
B4 PASS (not applicable): no claim/retry state is introduced (g409_box_coordinate_cause_2026-09-12.md:36).
B5 PASS: instrumentation writes only to a scratch-tree copy; deploy bytes are unchanged (../../../scripts/platformkit/tracking/g409_observer.py:89).
B6 PASS: no module was moved or retired; imports resolve in the passing named test (tests/platformkit/test_g409_box_coordinate_cause.py:1).
B7 PASS: all 60 evenly sampled cards, 30 per kind, were reviewed (g409_box_coordinate_cause_2026-09-12/summary.json:101).
B8 PASS: the 60 px transform is read from executed code before comparison and is marked unfitted (g409_box_coordinate_cause_2026-09-12/summary.json:19).
B9 PASS: unique denominators are 60 ticks, 206 rows, and 51 frozen pairs (g409_box_coordinate_cause_2026-09-12/summary.json:87).
B10 PASS: prereg binds the spec bars byte-for-byte (g409_box_coordinate_cause_2026-09-12/prereg.md:29).
Q1 PASS: prereg seal fa227df1c8aecd6f46fbc779f71c3f5bedb0f76bdf252317e95b76e87668d697 independently recomputes and predates measurement (g409_box_coordinate_cause_2026-09-12/prereg.md:36).
Q2 PASS (not applicable): this is an uncharged diagnostic (g409_box_coordinate_cause_2026-09-12/prereg.md:33).
Q3 PASS: no acceptance bar or threshold moved (g409_box_coordinate_cause_2026-09-12/prereg.md:29).
Q4 PASS (not applicable): no OOS score or learner is introduced (specs/G409_spec.md:21).
Q5 PASS (not applicable): no AHEAD result is asserted (specs/G409_spec.md:21).
Q6 PASS: candidate scan reports 90 paths and zero hits; this verifier memo also rescans at zero (g409_box_coordinate_cause_2026-09-12/q6_scan.json:2).
Q7 PASS: sampled n=60; all seven enumerated controls are retained (g409_box_coordinate_cause_2026-09-12/summary.json:13).
Q8 PASS: premise was independently remeasured before trace review (g409_box_coordinate_cause_2026-09-12/summary.json:87).
Required correction: capture the omitted identities/values at their call/write sites and render actual detector input separately on all 60 cards; until then change memo line 1 from DONE to NOT VALIDATED.
Proposed RESULTS_LEDGER row: `2026-09-11 | tracking | G409 | 60 ticks and 206 rows bind exactly; dy median -58.2 px maps to 1.8 px with code-derived +60, but stage records and native cards omit required identities | REJECT (verified: codex-sol, contract A/B/Q)`
NEW GAP: A1 cannot run in master 720e7c40 before landing because it contains neither the candidate test nor the G409 modules; the candidate-tree per-file run is green (VERIFIER_CONTRACT.md:11).
NEW GAP: the seven controls reproduce copied crop/serialization statements rather than invoking archived route functions; this is not an acceptance-table rejection (specs/G409_spec.md:14).
