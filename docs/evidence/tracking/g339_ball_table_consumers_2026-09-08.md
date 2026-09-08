VERDICT: DONE. Every one of the 1,023 grep hits from the exhaustive six-pattern census now maps to a classified readers.csv row (117 semantic reader rows across 5 classes + 193 EXCLUDED rows across 6 reasons, 0 unmatched on a fresh re-grep); the real join on both named WNBA table pairs is unchanged from fix 1b: wnba_05 907/1000 frames carry a detected ball, wnba_02 803/1000 -- both reproduce G320's detected counts (907, 803) exactly, n = 2,000 ball rows.

# G339 ball-table consumer census (2026-09-08)

Machine: LOCAL, because this is a repository and CSV census; Python 3.10.0. No pod, GPU, video, daemon, deployed tree, or data/ path was used.
PREREG: `docs/evidence/tracking/g339_prereg_2026-09-08.md`; embedded seal `c7076a78cf1b7c8afe6810dc10d46f73c8d36993758f3853e50d046a5dbc2dee` was calculated before reports.
PREMISE binding output: feature hit `src/features/feature_engineering.py:79` names `ball_x2d`, `ball_y2d`; `src/sim/` produced no `ball_tracking.csv` or joined-table call-site hit. The premise holds; it is not falsified.

INPUTS (A9): master data paths, fetched read-only from the pod after landing: `data/tracking/wnba_05/ball_tracking.csv` (sha256 `805c6479e6988dbb0958d8b15c2b2f35f8a1ee4a51a626be5361b1d24f60ca1d`), `data/tracking/wnba_02/ball_tracking.csv` (sha256 `79537a95f1d8ca4f0f609b27e07c19aa1f1d66e6bdfb3926558e942d273b8510`). Byte sizes 24473 and 23410 match G314; both are the full 1,000-row table.
CORPUS (fix 1c): `docs/evidence/tracking/g339_ball_table_consumers_2026-09-08/corpus_manifest.csv` lists every local `data/tracking/<game_id>/ball_tracking.csv` (path, bytes, sha256, detected/total rows) found by a `Path("data/tracking").glob("*/ball_tracking.csv")` walk on this machine today: n=360. This is not the 485-table figure an earlier premise quoted -- 485 was a G335 pod-side snapshot, a different corpus from this local `data/tracking/` tree, and the two counts are not comparable.

## Consumer census
| class | n | summary |
|---|---:|---|
| READS_BALL_TABLE | 30 | operational, validation, and analytic readers of a separate ball_tracking.csv/table-presence check, incl. an API route and the join harness itself |
| EXPECTS_INLINE_BALL_ROWS | 38 | feature, harness, daemon, quality, render, recovery, census, and intelligence inline/object-row readers |
| RUNTIME_BALL_POS | 1 | consumes the in-process `ball_pos` parameter (EventDetector), never a persisted table |
| BALL_BLIND | 2 | simulation and `intel/` (zero semantic hits) |
| TEST_ONLY | 46 | synthetic construct/fixture readers exercising a real reader above |
10 readers join by frame (9 READS_BALL_TABLE incl. `ball_join.py` itself, 1 EXPECTS_INLINE_BALL_ROWS: `domains/basketball_nba/tracking/screens.py` merges a cls==ball frame onto player rows).
Every one of the 1,023 raw hits from `git grep -n -E "ball_tracking|ball_x2d|ball_y2d|ball_inferred|\bcls\b|[\"']ball[\"']" -- src scripts kernel domains api intel` is classified: `readers.csv` (row_id-keyed, 310 rows: 117 semantic + 193 EXCLUDED_*) carries the class per file/line, and the new `grep_hits.csv` maps every one of the 1,023 raw hits (file, line, matched pattern) to its readers.csv row_id, so the reconciliation is independently checkable by re-running the same grep. EXCLUDED reasons and counts: EXCLUDED_GENERIC_CLS_PARAM 83 (classmethod `cls`, CSS/HTML class tokens, unrelated classification labels), EXCLUDED_OTHER_SPORT 87 (MLB/soccer/tennis/football/KBO/NPB `ball` or schema hits), EXCLUDED_WRITER_SIDE 7 (detector internals and the ball_tracking.csv writer itself, upstream of any reader), EXCLUDED_DETECTOR_LABEL_LIST 3, EXCLUDED_COMMENT_ONLY 12, EXCLUDED_SIGNAL_TAG 1 (a playstyle-signal tag string, not a table column or value).
## Writer contract

| output | writer evidence | schema / inline outcome |
|---|---|---|
| ball_tracking.csv | `src/pipeline/unified_pipeline.py:1982-1991,4030-4039` | frame,timestamp,ball_x2d,ball_y2d,detected,live,ball_inferred |
| tracking_data.csv | `src/pipeline/unified_pipeline.py:4020-4025` | player rows; writer grep for cls/class/label ball returned 0 hits |

The daemon calls the inline harness (`scripts/platformkit/track_daemon_done.py:205`); the harness filters `cls == ball` (`tracking_harness.py:314,337`). EventDetector receives runtime `ball_pos` (`event_detector.py:191-234`) rather than reopening the ball CSV.

## Join harness and report
`scripts/platformkit/tracking/ball_join.py` is 100 LOC and emits frame, player count, detected/inferred flags, coordinates, nearest player, and pixel distance. `--report` prints all frames, detected and undetected frame counts, and nearest-distance n/min/p50/p95/max.
`docs/evidence/tracking/g339_ball_table_consumers_2026-09-08/join_report.csv` records the two real joins:
| game | frames | with detected ball | without | share | nearest_player_distance_px n / min / p50 / p95 / max |
|---|---:|---:|---:|---:|---|
| wnba_05 | 1000 | 907 | 93 | 0.907 | 904 / 7.62 / 188.07 / 545.51 / 1647.45 |
| wnba_02 | 1000 | 803 | 197 | 0.803 | 803 / 117.83 / 1097.20 / 1419.05 / 2832.63 |
Both detected counts (907, 803) reproduce G320's premise table exactly, n = 2,000 ball rows.
TEST: `python -m pytest tests/platformkit/test_g339_ball_join.py -q -p no:cacheprovider` -> 1 passed. It constructs a three-frame pair and verifies the join, nearest distance, and report denominator. EYE CHECK: NONE.
## Consumer proposal and checks

First simulation-path BALL_BLIND consumer: `src/sim/basketball_sim.py:95` reads only team-rate caches. Proposed seven-line optional `ball_context` input: `docs/research/organization-sprint/G339_PROPOSED_ball_join_consumer.md`, sha256 `39c19d244887e255e988164a1008477b1fcf0dc3606a6468756a74e41874f767`. It could change possession-context inputs and simulation calibration outputs only after owner-defined aggregation; no default changes.
No OOS comparison, loss, candidate delta, charged trial, evaluator, or AHEAD claim exists. If a later comparison is made, improvement means baseline loss minus candidate loss; positive means candidate better.
SHA-256 LF-normalized (refreshed -- fix 1c): prereg full file `ef4ffd741f805bb164da338e031b7d2ffb01d1b4008f98e3e73ec87fe810cd52`; harness `fd81363d726ee58929347a1d1b4d2fb9b7b71f7a961387499773a2d96e08ad2a`; test `3ed10b956c66542338258764a5b2f2f4253f90e13abe99dba31807d432d7af3b`; readers `0dc58d8ef0c9a5be01ad87b5ae9a4d46f59eb907d5b4925b99c3a08d2b47bee1`; grep_hits `82b070a90ef764217104d915725441bcd2fb11d92b70c160c9ae8241a6899935`; corpus_manifest `c61b060e740b079f203b6f7e2edb55e7ea2ce620af0ecf2cdda5eae3ecbf1dc3`; report `96c4b0665229f1966f3d6fcb5a50bd3672f73b54cb7b77814db9dac7b368155c`.
Contract self-check: B1-B10 pass (no exclusion, schema replacement, gate, lifecycle, deployment, moved module, head slice, fit, recycled denominator, or changed bar). Q1 seal exists before reports; Q2-Q5 and Q9 are inapplicable; Q6 calibration language only; Q7 is now an exhaustive census plus construct; Q8 binding premise was remeasured first.

## Corrections (fix 1b and fix 1c, 2026-09-08)
Verifier codex-sol REJECTed the first landing for two omitted readers and a wrong join-by-frame count, by verdict text only -- the verifier's own artifact was never committed on this branch. This pass re-ran the six-pattern census across `src/, scripts/, kernel/, domains/, api/, intel/`, added `scripts/cv_fix_anchor_intel.py:61-77` and `scripts/platformkit/tracking/g195_cv2_rng_route_determinism.py:26-47`, and reconciled every remaining hit found by the same patterns (9 more genuine readers, 16 more synthetic test fixtures, 1 reclassification: `event_detector.py` moves from BALL_BLIND to the new RUNTIME_BALL_POS class). Total readers 37 -> 66; join-by-frame 8 -> 9. `join_report.csv` was not touched. The `RESULTS_LEDGER.md` G339 row was corrected in place.
Verifier codex-sol REJECTed fix 1b, by verdict text only -- the verifier's own artifact was never committed on this branch -- for omitting four direct semantic readers (`coverage_recovery.py:23-25,190`, `render_tracking_demo.py:40-41`, `tracking_contract.py:69,126`, `tracking/ball_join.py:34-47`) and for the memo naming an uncommitted attempt-1 artifact. This pass re-ran the same six-pattern grep programmatically over `src, scripts, kernel, domains, api, intel` (1,023 raw hits, byte-identical on a fresh re-run), added the four named readers plus every other genuine hit the same patterns turned up (21 more EXPECTS_INLINE_BALL_ROWS, 2 more READS_BALL_TABLE incl. `ball_join.py` itself, 28 more TEST_ONLY), and classified the remaining 193 non-semantic hits into 6 EXCLUDED_* reasons instead of leaving them ungrouped. Total readers 66 -> 117; join-by-frame 9 -> 10. Added `corpus_manifest.csv` (n=360 local ball_tracking.csv tables, superseding the 485 pod-snapshot premise) and `grep_hits.csv` (all 1,023 raw hits, each pointing at its readers.csv row_id) as new artifacts. The `RESULTS_LEDGER.md` G339 row is corrected in place to the new totals.

## NOT VERIFIED
- The two WNBA joins are computed but not validated: `nearest_player_distance_px` is pixel-space proximity, never checked against an image or confirmed as the possessing player. Two games only, both WNBA; nothing generalises past them.
- Dynamic readers can evade a static grep census; this is a code-reader census, not runtime tracing.
- `detected` remains a detector flag, not a verified ball; no image or position validation occurred.
- The proposed simulation input has not received owner schema confirmation or adoption.
- Contract A1 is not executable before landing: master lacks the G339 module/test, so any absolute-path pytest run resolves the candidate tree, not a master-code rerun (verifier NEW GAP, unresolved).

Vocabulary follows contract Q6; automated scan required.
