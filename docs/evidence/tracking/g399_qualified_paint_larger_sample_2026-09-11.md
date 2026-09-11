VERDICT: CLOSED AT LIMIT

G399 qualified-rater paint larger sample. PC only: no pod, GPU, or fitter. Sealed prereg:
`docs/evidence/tracking/g399_qualified_paint_larger_sample_2026-09-11/g399_prereg_2026-09-11.md`,
seal 1ce0d72bb49ee61b95bbb92e5742e804d24af576a9c11adbdb65b49aa347f9df.

PREMISE (step 0; premise_receipt.json). G396 raw scores reproduce astra 30/30, sol 27/30,
same-control joint 27/30, and three real audit passes. Both frozen instructions, high rater
configurations, and executable digest are byte-identical to G396. All 30 G386 retained sources
rehash exactly at native 1920x1080. The PREPARE 0/30 was a path fault: it read pod-side source_path
instead of G386 retained_path; source_receipts.csv corrects it without substitute footage.

METHOD AS RUN. A decoded-PTS census (pts_bounds.csv) found 29/30 sources decode fewer frames than
their packets, so packet/header spans were not used. The frozen competition/video/section/source-digest
order selected two interior nearest-PTS states per source, yielding 60 archived states before labels.
Every export is PTS-verified; 60 frame and 360 tile digests are unique. Both qualified raters blind-rated
all 60 after passing image-open fixtures. The finisher recorded native visibility before opening traces.

RESULT. 60 planned, 60 decoded, 42 finisher-visible. Astra: 45 VISIBLE / 14 ABSENT / 1 UNKNOWN,
83 fragments. Sol: 39 VISIBLE / 21 ABSENT, 70 fragments. All answers are present. Three of 153
fragments formed same-tile same-family sealed-rule pairs; 147 are archived unmatched. Independent
nine-point audit passes only G399_031; G399_008 and G399_022 each have one sol fragment at 6/9.

RECOVERY. 1 state recovered: 1/60 planned, 1/60 decoded, 1/42 finisher-visible. The continuation
bar is 30. Because 1 < 30, this reference route and sample are CLOSED AT LIMIT; paint-based fitter
work PAUSES. No H fit, orientation inference, or registration acceptance is claimed.

CLUSTERING. 21 videos, 30 sections, four competition labels (34 unlabelled, 12 nba, 10 ncaa_basketball,
4 wnba). The three candidates span three videos and labels. One video supplies 8/42 visible states.
Raters agree on state in 53/60 but disagree on family in 30 states; same-family pairing binds supply.

REPRODUCTION. After the recorded redaction, two fresh processes reran pairing, scoring, per_frame,
summary, audit_points, and blind_ratings from delivered immutable answers and audit judgments. Every
canonical digest matches each process and landed table (repeats.json); no measurement changed. Q6 scan
now inventories all 182 evidence-surface paths, including 14 dispatch TSVs, with zero non-opaque hits.
Focused test: tests/platformkit/test_g399_qualified_paint_larger_sample.py.

2026-09-11 Fix 1b addresses ACCEPTANCE-3 (post-redaction repeats), ADDITIVITY/B2 and B10 (field-aware
claim-field parity), NEW GAP 1 (all dispatch TSV inventory), and NEW GAP 2 (render_point_grid boundary
decode regression); repeats, scanner, tests, checksums, and receipts changed, while measured numbers did not.
2026-09-11 Fix 1c addresses ADDITIVITY/B2 aliases, Q6 split-character numeric fixtures, and the portable Fix 1d (2026-09-11): the parent per-run stdout/returncode fields are restored in repeats.json from two fresh finalize.py processes (SUMMARY line identical; recorded under finalize_runs with the pre-redaction blind_ratings digest disclosed); scan count corrected to 182.
complete scan inventory (code, test, and dispatch TSVs); repeats aliases current digests and numbers remain unchanged.

SHA-256 5f2a3c63007f8b142b22ee0d1f35efb48640e950f94c179f4f1352b644803d68 docs/evidence/tracking/g399_qualified_paint_larger_sample_2026-09-11/repeats.json
SHA-256 e2c897e23bec7c3933277825d7de5b909237cd5f9c78ff9595eaf9b1c14b8c9c docs/evidence/tracking/g399_qualified_paint_larger_sample_2026-09-11/q6_scan.json
SHA-256 2f9c3347e4b7ae652cb0d9b04e0f5ec59cf86795ce19fd119813e4205f325479 scripts/platformkit/tracking/g399_q6_scan.py
SHA-256 556a020c9d6007dc418e09d3a6a121bdb5c43274ca99ce6f34232c304cd5b604 tests/platformkit/test_g399_qualified_paint_larger_sample.py

NOT VERIFIED:
- Whether the recovered band is usable geometry: it is defocused, 8-12 px wide, and its centre is not localized to 3 px.
- Rater/adjudicator repeatability, 720p sources, paint observability generally, or the G383 FIT/VALIDATION prerequisite.
- The separate G387/G396 parent accounting (60 planned / 49 retained / 11 decode failures, 3-of-30 recovery).
