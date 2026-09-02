# Tracking gap register -- 2026-09-01 (living; one gap = one lane)

Rule: a gap is closed only by a measured artifact (n, denominator = decoded
frames, render-and-look). Harness thresholds never move. Broadcast footage
only. Rung ladder: IMAGE_PX_DECLARED -> METRIC_LOCAL -> COURT_FEET.

| id | sport | gap (measured) | evidence | status |
|----|-------|----------------|----------|--------|
| G01 | all | corpus intake accepted junk (talk shows, volleyball, esports); 12 clips quarantined; football denominator 35/41 | corpus_mislabel_2026-09-01.md, footage_census.py | census tool shipped; ingest gate (_valid_football_item) NOT yet re-run on legacy queue items |
| G02 | all | coordinate declaration gate is magnitude-blind (minimap px passed as image_px) | basketball_imagepx_relabel_2026-09-01.md, test_image_px_containment.py | containment gate in flight (T3b) |
| G03 | basketball | producer writes map_2d canvas px under x/y; 23.22 pct inside frame, 8/8 games FAIL | same | producer fix in flight (T3b) |
| G04 | basketball | no player identity; no court lock on broadcast pans | harness_sweep_173_games | OPEN; after G03: image_px features + partial court lock on half-court possessions |
| G05 | tennis | far-court verticals vanish (0-1 vs >=2 gate) -> 10.18 pct camera-lock coverage | tennis_camera_lock_honest_measurement_2026-09-01.md | in flight (T1) |
| G06 | tennis | synthcal keypoint model does not converge (PCK 0.13, no checkpoint) | synthcal_w7_verdict_2026-09-01.md | CLOSED as FAIL; classical 5.28 ft = ceiling until G05 lands |
| G07 | soccer | detector-bound vs camera-bound undecided at n=36 (pct>=14 0.5833) | soccer_s1_blind_verdict_2026-09-01.md | n=100 blind verdict in flight (T2c) |
| G08 | soccer | ext packet distinct_track_ids blank: homography never locks on isolated frames (needs video stream) | 50b9c69ca report | OPEN; churn unmeasurable until stream-based packet |
| G09 | soccer | no learned calibration; synthetic route failed; licensed labeled set unknown | sports_cv_licensed_assets memory | OPEN; licence check before any training |
| G10 | baseball | scale anchor = mound diameter; chord on dirt 2/6; 14.9-66.4 px/ft | baseball_footage_acq_2026-09-01.md | plate landmark + 10 pct two-reference validation in flight (T5c) |
| G11 | baseball | dominant_green scores 0 on night games (stadium lighting) -> pitch-view gate lighting-dependent | same | OPEN |
| G12 | baseball | pod daemon corpus 87 games mostly junk; only 4 real broadcasts | same | OPEN; acquire more official condensed games (bridge fixed: explicit section) |
| G13 | football | motion-energy snap detection structural REJECT (13-15 pct precision); OCR terminal | football_fieldview_2026-09-01.md | PAUSED this session |
| G14 | all | pod adapter/keypoint code lags master (tennis adapter pre camera-lock) | synthcal verdict report | OPEN; deploy + daemon restart pending after G02/G03 |
| G15 | all | daemon "done" = rows>=500 not harness verdict; deletes footage | done_means_verdict memory | OPEN; verify current daemon logic |
| G16 | all | teacher->student gate does not exist as a module (rule only) | product_runtime_contract memory | OPEN; needed before any "tracking improved a model" claim |

Next single-problem lanes, in order: G01 ingest re-gate, G14 pod deploy, G15
daemon done-definition, G12 more real baseball, G04 basketball image_px
features, G09 licence check, G16 student gate.
