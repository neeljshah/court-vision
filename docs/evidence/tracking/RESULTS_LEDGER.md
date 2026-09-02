# Tracking results ledger (append-only; one line per landed improvement)

Format: date | sport | gap | metric before -> after (n, denominator) | verdict | commit
Only measured numbers with an artifact. Honest FAIL/REJECT lines belong here too.

2026-09-01 | tennis | G05 | camera-lock coverage 0.1018 -> 0.1987 (599 decoded, linspace plan); sequential 15300-15600: 0/31 -> 270/301 = 0.897, harness PASS; 1080p control 5/71 -> 58/71 PASS | LANDED | 1c5f1e6b7
2026-09-01 | tennis | G06 | synthcal W7 keypoints: no checkpoint (synthetic PCK 0.13); v1 arm 29-34 ft vs classical 5.28 ft anchor (n=259) | FAIL (classical stands) | 8f8db7c8d
2026-09-01 | basketball | G02/G03 | image_px containment 0.00-0.81 -> 0.94-0.98 on 8 games (32,355 pts); containment gate at intake 0.95 fail-closed | LANDED (producer fix PROPOSED in src) | beb8e4c6d
2026-09-01 | baseball | G10 | METRIC_LOCAL reached on 4 real MLB broadcasts (176/84/9/6 pitch segments with scale); two-reference validation: 9/36 segments (25 pct) validated, rest fail closed | LANDED | 452c9d954, 1942be94b
2026-09-01 | soccer | G07 | blind S1 verdict n=100: manual median 13.0, pct>=14 0.490, paired delta -1.23 | AMBIGUOUS -> S0 (honest) | c59f5499d
2026-09-01 | football | G13 | image_px snap precision 3/20 -> 4/30 with field-view gate; structural | REJECT (paused) | e01abb401, 33057c216
2026-09-01 | all | G01 | corpus census: 12 junk clips quarantined; football denominator 41 -> 35 | LANDED | 398410393
2026-09-01 | all | G14 | pod deploy 53 files, daemon restart; pod tennis coverage 0.8970 bit-identical to local | LANDED | 84d1c9652
2026-09-02 | baseball | G11 | night pitch-view gate (hue_geometry, opt-in): night 4.0 -> 39.7 pct accepts but hand-check precision 0.78 (<0.80) and day marginal accepts 0/8 | REJECT (unmerged 00b9ed4de) | fed355220
2026-09-02 | soccer | G17 | role filter attempt 1: paired delta manual-minus-detector -1.23 -> +2.26 (n=100), over-rejects players; found G22 detector non-reproducibility 27/100 | REJECT (unmerged 310be150b) | register
2026-09-02 | soccer | G22 | packet detector determinism: sealed-vs-fresh 27/100 frame-count mismatches -> 0/100 between fresh runs (pinned JPEG decode + model path + seeds + single-thread cv2); verifier reproduced 2 separate processes identical on 10 frames, 1/10 differ from the sealed csv | ACCEPT (verified, landed) | 639336c44
2026-09-02 | soccer | G17 | role filter attempt 2: paired delta -1.23 -> +0.90 (n=100), render tally 19/167 = 11.4 pct disagreements vs 10 pct bar | NOT VALIDATED (honest); module landed unused/opt-in, zero callers | 639336c44
2026-09-02 | all | G09 | licence-compliant calibration route researched: 2 SHIP-OK assets, 9 BLOCKED/unlicensed; per-sport self-label route + published ceilings recorded | LANDED (research) | 754b7543e
2026-09-02 | baseball | G11 | composed night gate v2: park A 1.0 -> 29.6 pct accepts at 16/16 precision, park B 0.3 -> 2.5 pct at 5/9, day marginal 0/7 (80 renders viewed) | REJECT (park-dependent; unmerged d6259ce4d) | register
2026-09-02 | tennis | G18 | sequential-plan harness on 3 matches (15 ranges x 300 frames, frozen harness): ranges PASS 5/5 nyYk 720p, 1/5 tennis_09, 4/5 tennis_10; jump_p95 failures 0/15 (was the linspace artifact); all 5 failures are oob, and render-and-look on 12 frames shows lines on lines in 12/12 -- oob = detect_players picking the chair umpire / ball kids / courtside staff, not a bad solve | LANDED (plan defect closed; detector-selection gap opened) | c57bcb85e
2026-09-02 | basketball | G04 | image_px teacher proxies on 8 pod games (32,355 rows): per-game JSON with coordinate_space=image_px, decoded-frame denominator, per-feature n_frames_used/n_excluded; wnba_01 pace 0.0456, rev/min 76.25, spread 0.1245, pan share 0.0113 (964/965/965 usable frames of 2,998 decoded); 6 renders reviewed, tight shots show crowd/bench false detections | ACCEPT (verified, landed) | ef0b5e152
2026-09-02 | basketball | G19 | coast tagging: 1,436/32,355 rows (4.44 pct) tagged, containment_all unchanged -- but pod tables carry no bbox columns, so ONLY the off-frame rule fired and containment_observed 0.9991-1.0000 is tautological; manifest lacks coasted_rule and emits verdict_observed on that number | REJECT (circular as measured; codex ea5835abb unmerged) | register
2026-09-02 | basketball | G25 | verifier measurement over the same 8 tables: 6,624/32,355 emitted foot points (20.5 pct) fall in the TOP 20 pct of frame height, per game 0.18 pct to 57.0 pct; track-level share degenerate (10 recycled ids/game, 7/8 games at 1.0) | NEW GAP (open) | register
