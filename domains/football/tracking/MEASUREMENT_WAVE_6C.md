# Football Wave 6C NFL pilot measurement

Source: `football_wHZt1eY3A9s`, `/workspace/nba-ai-system/data/footage_bridge/football__football_wHZt1eY3A9s.mp4`.

Measured 2026-09-01 with `nice -n 15` on the pod. The source was 1280x720 at
29.970 fps; 60 frames were selected evenly across the decoded frame range.

| Funnel stage | Survivors |
| --- | ---: |
| Decoded samples | 60 |
| Field view | 28 |
| LSD line detection | 28 |
| Yard-line family clustering | 1 |
| Two hash-row detection | 0 |

The independent NFL scale check has `n=0`; it is provisional and does not
meet the required `n >= 30`. No median or p95 ratio error exists. The expected
NFL ratio is `18.5 / 15 = 1.233333`; it was not compared to an observed ratio.
The scale gate therefore fails and the adapter and frozen harness were not run.

Rule source: NFL Rule 1 field markings item 10 says professional inbounds hash
marks are 70 ft 9 in from each sideline, versus 60 ft for college:
https://operations.nfl.com/rules-officiating/2026-nfl-rulebook

The NFL's field glossary states that yard lines are painted at five-yard
intervals, making adjacent painted-yard-line spacing 15 ft:
https://operations.nfl.com/football-101/terms-glossary/glossary-terms-list/yard-lines/
