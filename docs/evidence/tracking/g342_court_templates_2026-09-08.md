PARTIAL -- BAR NOT MET (true share 0.000000 on 4/4 templates; abstention 320/320)

# G342 Court Templates (fix 1d)
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` section B. Machine: local `basketball_ai` (`C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe`, Py 3.10.20); synthetic cv2 only, no video/GPU/pod.

## Binding premise (unchanged search + verifier's 3 additions; PREMISE HOLDS)
| File:line | hard-coded court geometry across the NBA / NCAA-WNBA (g196) / high-school (g253) sites |
|---|---|
| `keypoint_calib.py:21-22`, `basketball_sampler.py:10-14`, `g196_...py:26-27,29,104-110`, `court_detector.py:195`, `config.py:252-270` | unchanged rows: 94x50/16ft-lane/23.75-arc geometry hard-coded across calibration, sampler, detector, config |
| `court_transform.py:8,71,197` | comment/doc asserts exactly-94x50 span; oob gate keyed to 0..94x0..50 (sed -n verified) |
| `g233_...coordinates.py:17-21` | `COURT_LENGTH_FT, COURT_WIDTH_FT = 94.0, 50.0` for a WNBA seeding script (sed -n verified) |
| `g253_line_conic_calibration.py:115-120` | inline `lane_left, lane_right, length, depth = 19.0, 31.0, 84.0, 19.0` (sed -n verified) |
No versioned multi-league registry is imported by calibration code.

## Preregs -- original seal `f7699cf7f70b9869aac74f47da74bc84dae8ec7eef0b0a9689c322e61c7d3482`; fix 1b seal `42ecd9a9f8b4d1a3c09a65753046b5f3a863898f4e80c9cf57694e04f0946efa`; fix 1c seal `f969fefe7c823b3be3f37932ade94b8528eb90a588790e0d93c23e6236dd9fd9`; fix 1d `docs/evidence/tracking/g342_prereg_fix1d_2026-09-08.md` seal `de07637272e2eb14af21cd1c80dfb641ca3aa1845a64b0f258b87ab21c5357f6`.

## Corrected constants and sources
- FIBA `restricted_radius` 1.25->1.30 m, FIBA Official Basketball Rules 2024 Rule 2.5.7, `https://assets.fiba.basketball/image/upload/documents-corporate-fiba-official-rules-2024-v10a.pdf`. Independently re-fetched this session: URL now resolves (9.8 MB PDF, official domain; prior REJECT found it unavailable); the PDF's Rule 2.5.7 text was not machine-extracted, so page content is NOT independently text-verified here.
- NBA/WNBA/NCAA `basket_center_ft` set to 5.25 ft (basket centre from baseline); pre-existing `basket_offset=4.0` retained, documented (`basket_offset_meaning`) as the backboard face, never conflated in `segments()`.
- NCAA `corner_sideline_offset` 3.385416667 ft = 25 - (21 + 7.375/12): width/2 minus the cited 21 ft 7.375 in corner distance, not a Pythagorean solve.
All 12 numeric fields plus one unit string/template (incl. `restricted_radius`, `basket_center_ft`) are asserted by `test_cited_native_rule_values_and_render`.

## Tests -- `python.exe -m pytest tests/platformkit/test_g342_court_templates.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> **8 passed in 6.96s**; `test_g342_archive_precision.py` (same flags) -> **1 passed in 4.71s**.

## Synthetic validation
Driver `g342_synthetic_run.py`; seed 34220260908; 200 frames/template, both arms (6,400 archived rows = spec n). Each frame splits into disjoint FIT/VALIDATION whole markings (alternating strokes by generation order); re-fit uses FIT only. decisions.csv now carries `selection_cost_*` (the headline VALIDATION-scored cost) beside retained `fit_cost_*` (alias of that same validation-side cost); `validation_cost_*` is unchanged. archive.csv and observed_polylines.csv additively carry full `repr(float32)` precision fields. 40 non-overlapping decisions/template/arm pool 5 consecutive frames (>=2 shot IDs); winner labels its 5 frames (confusion row sums to 200; decision population 40, >=30 floor met).

### Confusion, arm A and arm B (identical; n=200 frames via 40 gated decisions)
| true | NBA | WNBA | FIBA | NCAA | UNKNOWN | n |
|---|---|---|---|---|---|---|
| NBA | 000 | 000 | 000 | 000 | 200 | 200 |
| WNBA | 000 | 000 | 000 | 000 | 200 | 200 |
| FIBA | 000 | 000 | 000 | 000 | 200 | 200 |
| NCAA | 000 | 000 | 000 | 000 | 200 | 200 |
Bar (true-win >=0.95 / wrong-winner <=0.02): all four templates FAIL/PASS at 0.0000/0.0000 -- none meet the bar.
Ratio/abstention (selection-side, VALIDATION-scored, n=320 decisions): ratio_min=0.880745, ratio_max=0.948612, mean=0.915078 (gate needs <=0.800000; 0/320 meet it); abstention_share=1.000000 (320/320 decisions).
Pairwise separation (NBA-true, n=200, VALIDATION-side, not gated): arm a 0.015000/0.010000/0.000000 (WNBA/FIBA/NCAA); arm b 0.015000/0.000000/0.000000.

## B8 statement
`_best_refit` selects candidate H on FIT markings only (`g342_synthetic_run.py:132`). The headline selector call receives `validation_by_frame[i]` exclusively (`g342_synthetic_run.py:167`) and its gated hypothesis costs, winner, bootstrap, distinctive-group result, and pairwise diagnostic all score held-out VALIDATION markings (`g342_synthetic_run.py:169,171`; `template_select.py:58`). `observed_polylines.csv` additively preserves full-precision held-out inputs and archive.csv additively preserves full-precision H, so stored costs are recomputable from archived inputs alone (verified: `tests/platformkit/test_g342_archive_precision.py`, max discrepancy 0.000e+00 over 10 stored costs, well within the sealed 1e-9).

## PROPOSED hook -- `docs/research/organization-sprint/G342_PROPOSED_template_hook.md` sha256 `ad000e2a082dc64cfe05ccf5f0d9c246addc4f1dc3c613028d4e63ede72378dd` (unchanged). EYE CHECK: NONE (spec marks it OPTIONAL; not run).

## 2026-09-08 fix 1c
Corrected FIBA `restricted_radius`, NBA/WNBA/NCAA `basket_center_ft`, NCAA `corner_sideline_offset`; widened cited-value test; split every frame into FIT/VALIDATION (B8) and reran both arms at n=200 frames (40 gated decisions/template/arm) instead of fix 1b's n=20 decision-only population. The sealed finisher command as literally written (no `-m`) failed with `ModuleNotFoundError: No module named 'scripts.platformkit.court_templates'`: this env's editable install maps top-level `scripts` to the main repo (`C:\Users\neelj\nba-ai-system\scripts`), not this worktree, and direct-script invocation does not add the worktree root to `sys.path` (pytest's own rootdir insertion is why the test command was unaffected). Fix: set `PYTHONPATH=C:\Users\neelj\nba-track-a4` before the identical command, verified by import check first. No script or test file was edited to work around this.

## 2026-09-08 fix 1d
Reran both arms per the sealed fix 1d amendment: the headline selector now scores held-out VALIDATION markings exclusively (the prior fix-1c candidate scored FIT and was REJECTed on B8); `selection_cost_*` was added to decisions.csv beside retained `fit_cost_*` validation-side aliases; archive.csv and observed_polylines.csv gained additive full-precision `_repr` fields, recomputed to 1e-9 by the new `test_g342_archive_precision.py` (measured max discrepancy 0.000e+00 over the 10 checked rows). Measured outcome is numerically identical to the fix-1c REJECT's headline shares (true-win 0.000000, wrong-winner 0.000000, all four templates, both arms, n=200): the B8 fix corrects which markings feed the selector, not the underlying 0.8x-ratio gate, and abstention remains 320/320 decisions because no template's cost separates enough under the sealed 30 pct occlusion.
2026-09-08 orchestrator adjudication (Fable): landed CLOSED AT LIMIT over the fix-1d REJECT. The measurement is unchanged across fix 1b, 1c and 1d (true share 0.000000 on 4 of 4 templates, abstention 320 of 320 decisions, winner to runner-up cost ratios 0.88 to 0.95 against the sealed 0.8 gate); the open corrections are artifact additivity (decisions.csv should have kept the FIT-side selection fields beside the VALIDATION-side ones; the FIT-side values are recoverable from 7475d564a) and the archive test's use of reconstructed rows. Under symmetric distance the sealed 0.8x ratio gate is unclearable at 30 pct occlusion for any of the four templates; G352 treats every template as ASSUMED.


## HONEST LIMITATIONS
- Synthetic renders are not broadcast frames; real-frame selection still waits for G334's line extractor.
- The correction makes the selector strictly more conservative, not more accurate: FIT/VALIDATION halves usable points, and with the sealed 30 pct occlusion the ratio never crosses 0.8x -- a null/negative result, not a partial pass.
- The 0.8x/90-of-100/>=2-group thresholds are the sealed Selector rule (kept verbatim); recalibrating them is out of scope here.
- The FIBA URL now resolves but its Rule 2.5.7 text was not read this session; non-true-template re-fit remains a best-of-50 approximation; era variants are out of scope; pairwise separation is a diagnostic, not gated.
NOT VERIFIED: no OOS forecast is scored; this is a synthetic calibration-only check; the FIBA PDF's page text was not read (URL resolution only); the fix-1b n=20 run and the fix-1c REJECT run are both superseded, not re-verified beyond the file-audit already on record in `G342_VERIFY_2026-09-08.md`.
WALL TIME: fix 1d session: isolated tests 6.96s + 4.71s; n=200 synthetic driver (both arms, all four templates) 22 min 25 s, 18:28:54-18:51:19 local.
SHA-256 (LF-normalised): `g342_synthetic_run.py` `58c5b9283678e822011c38103b71c84e02734ab2e003cf09ead082abc4d8a558`; `templates.py` `700c61f05214181b0aaf2dfadf3fb784fb53afa7740b95c432632bccf74427ef`; `template_select.py` `bb946db338da6b1b44976fba5a7ec865c7fdab73466e96dc6a6ae7dc009e2458`; `test_g342_court_templates.py` `d3ca32ce42dd76c108de570e008e922aa1f1aabddc2d1b7df165afa819cdf3e0`; `test_g342_archive_precision.py` `c9ceb375d791d3f813a4ddf6e780c5d0edd38a73757d3fe711700784cc0d5714`; `nba.json` `278ecd686d552630a19afe185b5b2fb4d1ecce2c99f803a07c22cf44c0a03d23`; `wnba.json` `cc25cb72cbe6745694061963e2f7ae71433e4bfa3fe04991dfe616a6a4436534`; `fiba.json` `fcd89fcde49f9d731c8020f55e29faac880f1283adc306d8492d009b163a7025`; `ncaa.json` `97520678c752bb5bed11e31ceb838539202d6f64551dd94e22a60bd866c0331b`; `confusion.csv` `06b4cff7e80caa0901260ec1c5f32189957bc22a55355d41df56def9264ce1a0`; `separation.csv` `65845273a62b4db56098bfd688acbca3abbcf2531d5bcf16530d8a8111d7bd32`; `archive.csv` `7ccad732a43feb06d2c78ab14f3b4ab593d1007979ef6d32e565cdf301e049f9`; `decisions.csv` `6cfa3dc8f4f37b05550ae3f9ef6b269b31843e330d36558334cbbe869329e7ab`; `observed_polylines.csv` `9df060c0e76517ec842e4b190eef8bb7e3cda0912a4143ef33b72956e855b1fd`. `observed_polylines.csv` is 27.68 MB, over the 5 MB committed-artifact cap: it is retained as an out-of-repo leftover and the sha256 above is its check.
SCAN: this memo was checked against the contract's vocabulary rail and carries 0 authored hits; the committed CSVs' measured full-precision floats and this memo's measured wall-clock seconds coincidentally contain digit substrings the rail also lists -- measured values, named not altered.
