# S211 In-Game Headline Re-Derivation

## NOT VERIFIED

The public values are not verified under attempt 2 shared CPCV. This is a completed calibration measurement.

## ATTEMPT 2

Seal: `E6CE4EEAEA909412EA52321E68B2F507295C05AC1576F6D16B1592CCCC9D913D` in `S211_ingame_headline_rederive_attempt_2_prereg_2026-09-04.md`, committed before scoring as `f623c98799908f6c4896d9eac419f565543ad440`.

OOS scoring used `cpcv_evaluate`: eight timestamp groups, two test groups, one-day symmetric calendar embargo, 48-hour same-team purge, and three-day symmetric same-matchup protection. The shared evaluator asserts no retained train row is blocked around a scored row. The frozen 1e-6 bar is unchanged.

| Sport | Before static to conditional | Attempt 2 static to score to conditional | Prior share 95 pct CI | Result |
|---|---|---|---|---|
| NBA | 0.209 to 0.159 | 0.218832501 to 0.172353183 to 0.163246781 | 16.382629 pct [11.469448, 22.682439] | NOT VERIFIED |
| MLB | 0.241 to 0.126 | 0.248972824 to 0.128228347 to 0.127997560 | 0.190773 pct [0.059197, 0.326297] | NOT VERIFIED |

Denominators: NBA 1,313 game paths and 27,573 CPCV-scored checkpoints; MLB 23,279 game paths and 488,341 CPCV-scored checkpoints. The three-arm series are `S211_nba_per_game_losses_2026-09-04.csv` and `S211_mlb_per_game_losses_2026-09-04.csv`; the summary is `S211_ingame_headline_rederive_2026-09-04.json`. Each embeds the seal. The page is unchanged; its figures do not meet the frozen bar under this protocol.
