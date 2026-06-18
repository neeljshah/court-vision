# EDGE-HUNT RESULTS -- honest real-data hunt (2026-06-16)

All numbers below are live harness output on the real local corpora. No edge fabricated, no $ claim made.

## 1. Real-data baselines per sport (vs the SHIN-devigged close)

| Sport | Market | Metric | N | Our model | Close | Gap | Standing |
|---|---|---|---|---|---|---|---|
| NBA | moneyline | Brier | 372 | 0.1735 | 0.1672 | +0.0063 | MATCH |
| NBA | total O/U | RMSE | 372 | 19.172 | 18.114 | +1.058 | BEHIND (freshness) |
| MLB | moneyline | Brier | 13,992 | 0.2429 | 0.2390 | +0.0039 | MATCH |
| MLB | total O/U | RMSE | 1,679 | 4.719 | 4.441 | +0.278 | BEHIND (freshness) |
| Soccer | O/U-2.5 | Brier | 7,558 | 0.2465 | 0.2390 | +0.0076 | MATCH |
| Tennis (ATP) | match-win | Brier | 7,374 | 0.2177 | 0.2028 | +0.0149 | BEHIND (freshness) |

Team-strength win markets MATCH within sampling noise; totals/ATP are BEHIND by the freshness gap (injuries/lineups/SP/weather/park) a box model cannot see. Nothing BEATS the close pregame.

## 2. Candidate results table

| Candidate | Corpora | BSS-vs-close | DM p | N | Verdict | Note |
|---|---|---|---|---|---|---|
| NBA b2b_diff | 2026 H1/H2 | +0.0006 | 0.657 | 1103 | REJECT | sign flips H1<->H2 |
| NBA three_in_four_diff | 2026 H1/H2 | +0.0003 | 0.795 | 1156 | REJECT | sign flips |
| NBA rest_diff | 2026 H1/H2 | +0.0007 | 0.508 | 1103 | REJECT | sign flips |
| NBA home_court (HCA probe) | 2026 H1/H2 | 0.0000 | 0.173 | 1156 | REJECT | HCA fully in devig |
| NBA altitude_home | 2026 H1/H2 | -0.0014 | 0.162 | 1156 | REJECT | consistently worse |
| NBA travel_diff | 2026 H1/H2 | +0.0011 | 0.759 | 1103 | REJECT | sign flips |
| MLB rest/streak/h2h x3 | NL + AL | <=0 | n/s | 14k each | REJECT | reject on BOTH leagues |
| Soccer rest/totals/h2h x3 | by div | <=0 | n/s | 7.5k | REJECT | fail null-shuffle/BH-FDR |
| Tennis fatigue/surface/h2h x3 | 2 corpora | <=0 | n/s | 7.4k | REJECT | fail null-shuffle/BH-FDR |
| MLB totals slice (NL ALL) | NL | -0.0141 (worse) | 0.0092 | 1594 | REJECT | close beats us |
| MLB totals slice (AL ALL) | AL | -0.0185 (worse) | 0.0002 | 1610 | REJECT | close beats us |
| MLB open->close CLV capture | NL + AL | n/a | CI straddles 0 | 25.5k | REJECT | NL/AL sign disagree |
| NBA in-game conditioning | NBA + MLB | n/a (calibration) | n/a | 3,939 ckpt | SHIP (forecaster quality, NOT $) | see below |

## 3. Line-movement / freshness / CLV finding (the most promising lane)

- odds_snapshots/ is NOT a backtest corpus (NBA = 18 lines / 1 game, no real move). Real open->close exists only in MLB (28k, 2010-2021) and Soccer (16k, 2019-2026) odds.parquet.
- The move IS material: MLB mean |open->close| = 2.27 pp; 70.9% move >1pp. Soccer 2.19 pp.
- CLV genuinely EXISTS as a market phenomenon: the close is sharper than the open (MLB DM on log-loss t=4.43, p=0.0010, N=27,975; Brier-skill of close over open +0.43%).
- BUT we cannot anticipate the move: leak-free open-time model corr(model_p - opener, close - open) = +0.0038, CI [-0.046, +0.055] = zero. CLV-capture mean: NL +0.108 pp, AL -0.017 pp -- CI straddles zero and NL/AL disagree in sign (the overfit signature). REJECT.
- Conclusion: the freshness lane is a same-day-information/speed edge, not something a retrospective model captures. Confirms standing memory (clv_over_roi).

## 4. HONEST BOTTOM LINE

NOTHING survived >=2 corpora + DM p<0.05 + N>=200 as a market-beating edge. Every schedule/fatigue/form/h2h/totals candidate REJECTED across independent corpora; positive full-sample BSS reversed sign on the held-out half (overfit signature). The market is efficient on every pregame slice measured. This is the honest, correct result for efficient markets -- recorded as a SUCCESS, not a failure.

The one genuine, measured, calibrated win is NBA (and MLB) IN-GAME conditioning: win-prob Brier NBA 0.209 -> 0.159, MLB 0.241 -> 0.126, COMBINED (rating prior + realized score) sharpest, well-calibrated after one temperature param. This is FORECASTER QUALITY / calibration, NOT a dollar edge -- a live book also sees the score. No DM-vs-close test applies; no $ is claimed. Any in-sample survivor (there are none on the price side) would carry the explicit tag "needs forward CLV before any dollar."

## 5. NEXT real steps

- Capture a real forward line-movement archive (timestamped open->close polling that actually spans hours/days), since odds_snapshots is currently a live-poll format with no movement -- only this enables a true forward-CLV test.
- Wire a live same-day-information feed (injuries/lineups/scratches/weather/SP) at open time -- the only thing that could close the totals/ATP freshness gap; it is a data/speed problem, not a model problem.
- Productize NBA/MLB in-game conditioning as the shipped calibration product (already proven + calibrated), labelled forecaster quality, never an edge.
- Re-run all REJECTs forward on Oct-2026 data as a second independent season for the schedule signals (currently one priced season for NBA).
