VERDICT: ACCEPT WITH CORRECTIONS
Candidate 030313484: full diff reviewed; three additive receipt files and three manifest path substitutions (SHA256SUMS:2,7-8).
PREMISE PASS: independently counted 1973 attempts / 1599 sections, all ORIGINAL; 1080p30 1072/783, 720p60 41/41, OTHER 860/775 (census.csv:2).
PREMISE PASS: 1944 attempts before the boundary and 29 after; 27/29 after are 720p60; earliest 720p60 is 2026-09-07T21:49:41Z, matching the refined claim (g397_mixed_source_producer_census_2026-09-11.md:11).
REPRODUCTION PASS: claimed medians 0.8452 vs 0.7775 and difference -0.0676; reproduced 0.8451670326 vs 0.7775470862 and -0.0676199465 (summary.json:10,80,264).
ACCEPTANCE-1 PASS: correct PARTIAL; even draw is 30/30, but measured height/fps is 130/1973 attempts and 22/60 selected sections (G397_spec.md:29; g397_mixed_source_producer_census_2026-09-11.md:44).
ACCEPTANCE-2 PASS: correct NOT VALIDATED; 60/60 retained, schedules reproduce as 29/30 and 26/30 complete, below the bar (G397_spec.md:30; g397_mixed_source_producer_census_2026-09-11.md:45).
ACCEPTANCE-3 PASS: 67/67 unique attempts join once, original fields are byte-value preserved, extras are only four g397 fields; 22 MATCH/45 UNKNOWN (G397_spec.md:31; g397_mixed_source_producer_census_2026-09-11.md:32,46).
B1 PASS: all excluded denominator states are named; UNKNOWN is not collapsed to zero (g397_mixed_source_producer_census_2026-09-11.md:29).
B2 PASS: no field/status removal or rename; independent selected-vs-enriched comparison preserved all 67 originals (g397_tables.py:109-112).
B3 PASS: absent schedules and sources remain explicit UNKNOWN/ABSENT states (g397_mixed_source_producer_census_2026-09-11.md:29).
B4 PASS: this finite observational census adds no claim/retry gate (g397_run.py:161-195).
B5 PASS: deployed producer and daemon remained read-only; no restart or flag change is claimed (g397_mixed_source_producer_census_2026-09-11.md:8).
B6 PASS: candidate removes no module, test, import, or module entry point (SHA256SUMS:2,7-8).
B7 PASS: independently regenerated both 30-index even draws exactly; populations are 783 and 41 (g397_mixed_source_producer_census_2026-09-11.md:17-18).
B8 PASS: descriptive comparison has no fitted residual or independence claim (g397_mixed_source_producer_census_2026-09-11.md:3).
B9 PASS: denominators are actual evaluated ticks and shared-player pairs, with missing schedules explicit (g397_mixed_source_producer_census_2026-09-11.md:20-29).
B10 PASS: completion bars match the sealed preregistration and spec (prereg.md:87-94; G397_spec.md:29-31).
Q1 PASS: seal 9c7544f867124d78ccceaaa66b91696976da4bab8015dd8dae69db5ee2baa402 recomputes and commit dd17e284b predates measurement (prereg.md:99).
Q2 PASS: no charged trial or K-dependent metric exists in this observational row (prereg.md:97-98).
Q3 PASS: no bar or threshold moved (G397_spec.md:29-31; prereg.md:89-94).
Q4 PASS: no OOS model score or meta-learner is claimed (g397_mixed_source_producer_census_2026-09-11.md:3).
Q5 PASS: no AHEAD status is claimed; outcomes are PARTIAL, NOT VALIDATED, and DONE (g397_mixed_source_producer_census_2026-09-11.md:44-46).
Q6 PASS: independent strict scan of 196 row text/code files found 0 prohibited vocabulary or exact-figure hits; all were ASCII (g397_mixed_source_producer_census_2026-09-11.md:38).
Q7 PASS: sampled decision set has 60 unique sections, 30 per kind (g397_mixed_source_producer_census_2026-09-11.md:18,35).
Q8 PASS: whole-set premise was re-measured before interpretation and the admission-time premise was refined (g397_mixed_source_producer_census_2026-09-11.md:6-14).
EVIDENCE PASS: all 16 required paths exist; manifest is exhaustive at 246/246 files with 0 missing, extra, or digest mismatch (SHA256SUMS:1-246).
EYE PASS: sampled orders 0,6,12,18,24,29 in each kind; native and explicit metadata-only cards agree with the index states (eye_index.csv:2-61).
LOC PASS: candidate touches no .py; cumulative G397 helpers are 33-199 lines, maximum g397_report.py:199.
ADDITIVITY PASS: candidate adds receipts whose bytes match the pre-existing digests; no reader references the replaced missing basenames (SHA256SUMS:2,7-8).
TEST PASS: `python -m pytest tests/platformkit/test_g397_mixed_source_producer_census.py -q` -> 13 passed (test_g397_mixed_source_producer_census.py:1-125).
IMPORTER PASS: sole test importer of cumulative touched modules is the spec test above; it was run alone (test_g397_mixed_source_producer_census.py:8-9).
NOT VERIFIED PASS: memo includes an explicit list covering unavailable source probes, active wiring, registration, and uncommitted full tables (g397_mixed_source_producer_census_2026-09-11.md:40-41).
CORRECTION (minimal memo diff at g397_mixed_source_producer_census_2026-09-11.md:10):
- `(relaunch.log "RESTARTED 11:50:51 fmt720 patch")`
+ `(common_receipts/relaunch.log.txt "RESTARTED 11:50:51 fmt720 patch")`
2026-09-11 | tracking | G397 | 1973 attempts / 1599 sections; 30 sections per kind; format accounting PARTIAL, producer comparison NOT VALIDATED, provenance copy DONE | ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: g397_mixed_source_producer_census_2026-09-11.md:10 cites the absent old receipt basename; the committed receipt is common_receipts/relaunch.log.txt (SHA256SUMS:7). Apply the minimal correction above.
