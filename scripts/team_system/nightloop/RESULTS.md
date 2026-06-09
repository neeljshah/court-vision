# Night-loop results log

One line per completed experiment (newest at bottom). The loop appends: `ID | verdict | key numbers`.
CANDIDATE findings (a param that beats default on RMSE/bias+coverage, or a new signal that validates
leak-free) are ALSO written to ~/.claude memory project_monte_carlo_engine for the next session. Nothing
is auto-applied to the engine — candidates are flagged for human review.

| when | ID | verdict | key numbers |
|---|---|---|---|
| seed | S00 | KEEP | USAGE_CONCENTRATION default 1.25 ~optimal (1.15 MAE 5.287 vs 1.25 5.291 = noise) |
| 06-06 23:53 | S01 | CAND | VERDICT: best pts-MAE at RECENCY_W=0.3 (MAE 5.184); default 0.6 (MAE 5.291) -> CANDIDATE RECENCY_W=0.3 (pts MAE -0.107 vs default) |
| 06-07 00:02 | S02 | ok | VERDICT: best pts-MAE at RIM_ANCHOR_SLOPE=0.005 (MAE 5.289); default 0.007 (MAE 5.291) -> KEEP default |
| 06-07 00:08 | S03 | ok | VERDICT: best pts-MAE at PERIM_ANCHOR_SLOPE=0.002 (MAE 5.287); default 0.004 (MAE 5.291) -> KEEP default |
| 06-07 00:25 | S04 | ok | VERDICT: best pts-MAE at DEF_RIM_SLOPE=0.0018 (MAE 5.290); default 0.0024 (MAE 5.291) -> KEEP default |
| 06-07 00:31 | S05 | ok | VERDICT: best pts-MAE at DEF_PERIM_SLOPE=0.0009 (MAE 5.291); default 0.0013 (MAE 5.291) -> KEEP default |
| 06-07 00:36 | S06 | ok | VERDICT: best pts-MAE at DISP_BASE=0.14 (MAE 5.291); default 0.2 (MAE 5.291) -> KEEP default |
| 06-07 00:43 | S07 | ok | VERDICT: best pts-MAE at DISP_MINUTE=0.45 (MAE 5.291); default 0.6 (MAE 5.291) -> KEEP default |
| 06-07 00:49 | S08 | ok | VERDICT: best pts-MAE at REF_RIM_D=68.0 (MAE 5.283); default 65.0 (MAE 5.291) -> KEEP default |
| 06-07 00:55 | S09 | ok | VERDICT: best pts-MAE at REF_PERIM_D=68.0 (MAE 5.288); default 65.0 (MAE 5.291) -> KEEP default |
| 06-07 01:00 | S10 | ok | VERDICT: best pts-MAE at P_STEAL_ON_TOV=0.45 (MAE 5.291); default 0.55 (MAE 5.291) -> KEEP default |
| 06-07 01:01 | G01 | ok | suppression: SAS --2.3, NYK -4.3 (NYK faces tougher D) -> PASS True / 3. EQUIVALENCE: per-player pts MAE(ref vs fast) 0.10 (PASS<0.6: True)  / speedup 11.8x (ref 33.5s, fast 2.8s) |
| 06-07 01:02 | G02 | ok | ....                                                                     [100%] / 4 passed in 29.59s |
| 06-07 01:02 | G03 | ok | caveat: defensive trait ratings + shot-zone style are season-fixed (slow traits, not the / circular pts leak); opp rotation minutes are actual (~known pregame); empirical opp-def is sparse. |
| 06-07 01:02 | G04 | ok | 4 /          -3.87 /             +0.88 / caveat: leak-free as-of; pts=ppm*actual_min (minutes given). bias<0 => under-predicts. |
| 06-07 01:12 | G05 | ok | note: anchor mean ~leak-free over ~100 games; minutes not conditioned (pregame MC), / so minute-surprise legitimately widens realized spread. PIT<0.5 => sim over-predicts. |
| 06-07 01:12 | G06 | ok | shrink K=8: w=0.93 -> ft_force=0.935 / shrink K=15: w=0.87 -> ft_force=0.939 |
| 06-07 01:12 | G07 | ok | clutch-segment won 17/lost 24  /  GAME record in clutch games 25-18 (58%) / full-game record 74-28 (73%)  avg margin +8.4  /  time leading/g 32.7 min |
| 06-07 01:31 | G08 | ERROR | TIMEOUT (>900s) |
| 06-07 01:35 | N01 | ok | VERDICT: rest is a context signal; wire only if a team shows a stable >2 pt rest gradient (else noise). |
| 06-07 01:38 | N02 | CAND | VERDICT: RIGHT-SKEW FIX candidate (>q90 over target) -> add lognormal right-skew to star dispersion |
| 06-07 01:38 | N03 | CAND | VERDICT: candidate if factor!=1 and split-half stable; CHECK double-count vs rim_d make-suppression before wiring. |
| 06-07 01:44 | N04 | ok | VERDICT: descriptive variance signal (live-or-die); a high hot-vs-cold win gap = a swing team. Scouting, not a sim modulator (anchor has the mean). |
| 06-07 01:44 | N05 | ok | === assist_2nd ===  UNIMPLEMENTED signal -- loop should build a measurement for it or skip. Known: rest_days, paint_rate_def, three_var, upper_tail |
| 06-07 01:51 | S11 | ok | VERDICT: best pts-MAE at RECENCY_W=0.6 (MAE 5.291); default 0.6 (MAE 5.291) -> KEEP default / minbias RECENCY_W=0.6 (pbias -1.793 vs dflt -1.793) / bestcov RECENCY_W=0.6 (cov 76% vs dflt 76%) |
| 06-07 02:00 | S12 | ok | VERDICT: best pts-MAE at REF_RIM_D=68.0 (MAE 5.283); default 65.0 (MAE 5.291) -> KEEP default / minbias REF_RIM_D=68.0 (pbias -1.674 vs dflt -1.793) / bestcov REF_RIM_D=66.0 (cov 77% vs dflt 76%) |
| 06-07 02:07 | S13 | ok | VERDICT: best pts-MAE at DISP_BASE=0.14 (MAE 5.291); default 0.2 (MAE 5.291) -> KEEP default / minbias DISP_BASE=0.14 (pbias -1.793 vs dflt -1.793) / bestcov DISP_BASE=0.32 (cov 81% vs dflt 76%) |
| 06-07 02:13 | S14 | ok | VERDICT: best pts-MAE at DISP_MINUTE=0.45 (MAE 5.291); default 0.6 (MAE 5.291) -> KEEP default / minbias DISP_MINUTE=0.45 (pbias -1.793 vs dflt -1.793) / bestcov DISP_MINUTE=0.9 (cov 77% vs dflt 76%) |
| 06-07 02:22 | S15 | ok | VERDICT: best pts-MAE at USAGE_CONCENTRATION=1.1 (MAE 5.284); default 1.25 (MAE 5.291) -> KEEP default / minbias USAGE_CONCENTRATION=1.1 (pbias -1.786 vs dflt -1.793) / bestcov USAGE_CONCENTRATION=1.1 (cov 77% vs dflt 76%) |
| 06-07 02:29 | S16 | ok | VERDICT: best pts-MAE at RIM_ANCHOR_SLOPE=0.005 (MAE 5.289); default 0.007 (MAE 5.291) -> KEEP default / minbias RIM_ANCHOR_SLOPE=0.011 (pbias -1.757 vs dflt -1.793) / bestcov RIM_ANCHOR_SLOPE=0.009 (cov 77% vs dflt 76%) |
| 06-07 02:37 | S17 | ok | VERDICT: best pts-MAE at REF_PERIM_D=68.0 (MAE 5.288); default 65.0 (MAE 5.291) -> KEEP default / minbias REF_PERIM_D=68.0 (pbias -1.681 vs dflt -1.793) / bestcov REF_PERIM_D=66.0 (cov 77% vs dflt 76%) |
| 06-07 02:45 | S18 | ok | VERDICT: best pts-MAE at PERIM_ANCHOR_SLOPE=0.002 (MAE 5.287); default 0.004 (MAE 5.291) -> KEEP default / minbias PERIM_ANCHOR_SLOPE=0.008 (pbias -1.695 vs dflt -1.793) / bestcov PERIM_ANCHOR_SLOPE=0.002 (cov 77% vs dflt 76%) |
| 06-07 02:50 | S19 | ok | VERDICT: best pts-MAE at MIN_MPG=4.0 (MAE 5.289); default 6.0 (MAE 5.291) -> KEEP default / minbias MIN_MPG=4.0 (pbias -1.787 vs dflt -1.793) / bestcov MIN_MPG=4.0 (cov 77% vs dflt 76%) |
| 06-07 02:51 | G09 | ok | suppression: SAS --2.3, NYK -4.3 (NYK faces tougher D) -> PASS True / 3. EQUIVALENCE: per-player pts MAE(ref vs fast) 0.10 (PASS<0.6: True)  / speedup 11.3x (ref 33.4s, fast 3.0s) |
| 06-07 02:53 | G10 | ok | ....                                                                     [100%] / 4 passed in 30.27s |
| 06-07 03:03 | G11 | ok | note: anchor mean ~leak-free over ~100 games; minutes not conditioned (pregame MC), / so minute-surprise legitimately widens realized spread. PIT<0.5 => sim over-predicts. |
| 06-07 03:40 | G12 | ok | suppression: SAS --2.3, NYK -4.3 (NYK faces tougher D) -> PASS True / 3. EQUIVALENCE: per-player pts MAE(ref vs fast) 0.10 (PASS<0.6: True)  / speedup 12.1x (ref 33.8s, fast 2.8s) |
| 06-07 03:40 | G13 | ok | ....                                                                     [100%] / 4 passed in 29.95s |
| 06-07 07:26 | G14 | ok | 4 /          -3.87 /             +0.88 / caveat: leak-free as-of; pts=ppm*actual_min (minutes given). bias<0 => under-predicts. |
| 06-07 07:36 | G15 | ok | note: anchor mean ~leak-free over ~100 games; minutes not conditioned (pregame MC), / so minute-surprise legitimately widens realized spread. PIT<0.5 => sim over-predicts. |
| 06-07 08:14 | G16 | ok | suppression: SAS --2.3, NYK -4.3 (NYK faces tougher D) -> PASS True / 3. EQUIVALENCE: per-player pts MAE(ref vs fast) 0.10 (PASS<0.6: True)  / speedup 11.7x (ref 33.6s, fast 2.9s) |
| 06-07 08:14 | G17 | ok | ....                                                                     [100%] / 4 passed in 29.61s |
