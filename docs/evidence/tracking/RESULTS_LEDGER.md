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
2026-09-02 | soccer | G22 | packet detector determinism: 27/100 frame-count mismatches -> 0/100 on repeats (pinned decode+seeds) | codex done, awaiting verifier | b5d9c2bce (wt a4)
2026-09-02 | soccer | G17 | role filter attempt 2: paired delta -1.23 -> +0.90 (n=100), render tally 11.4 pct disagreements vs 10 pct bar | NOT VALIDATED (honest) | b5d9c2bce (wt a4)
