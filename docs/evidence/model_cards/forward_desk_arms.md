# Model card: forward paper desk scoring arms A, B, B_lag, C, D

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

- Name: the four-arm in-game instrument scored nightly by the forward paper desk.
- Version: sealed pre-registration `docs/evidence/forward/scoreboard/PREREG_2026-10-07.json`
  (amendment S492, implementation_version 2, effective 2026-10-07T00:00:00Z; file sha256 under
  Receipts; internal policy sha256 458941fb4b7cfca97aa4852dc535c771fe21e8c41a700892370a4ef984c8e3da).
  It supersedes `PREREG_2026-09-24.json`. Nights before 2026-10-07 read `PREREG_2026-10-03.json`.
- Arms (PREREG populations; `scripts/platformkit/ingame/baseline_four_arm.py`):
  - A: the tick's venue YES mid, untouched (a reference, not a devigged price).
  - B: ridge logistic regression (fixed penalty 1e-3, train-only scaling) on logit(mid).
  - C: the same fit on logit(mid) plus the sport's state features.
  - D: C plus the model probability, fit on model-present prior rows only.
  - B_lag: NBA only; B on the strictly prior same-game mid.

## Intended use and non-use

- Use: a prospective, sealed calibration record: does conditioning on state (C) or on the model
  (D) sharpen the mid-only fit (B) relative to the mid itself (A), per sport, segment and target.
- Non-use: paper only. No order is placed; not a wagering signal and not a sizing input; no return
  figure is computed or implied. Simulated fill counts are not markouts (packet section 5).
- Non-use: not a forward track record; every cell is INSUFFICIENT (packet section 4, the
  forward-track-record row).

## Inputs and data

- State features (`FEATURES` in `baseline_four_arm_features.py`): nba score_diff, quarter,
  seconds_remaining; mlb score_diff, inning, half, outs, base one-hot (7); soccer score_diff,
  minute, red cards and presence flags; nfl score_diff, period, game_seconds_remaining, down,
  distance, possession, timeouts.
- Sources: forward capture archives (Kalshi books and state, data cards C7 and C8,
  `docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md`).
- Window: from the desk start 2026-10-06; 113 games served through 2026-10-16 over 9 receipt
  nights (2 COMPLETE, 7 PARTIAL) (`CANONICAL_FIGURES.json` forward_window_counts).
- As-of: 2026-10-19 (packet section 5).
- NBA: the fitted arms train on regular-season games only; every NBA fit on disk is warmup; about
  20 settled regular-season games are needed before a fitted NBA arm scores (packet section 5).

## Method

- Expanding walk-forward (`eval_gate/walkforward.py`, purge 48 h + embargo 3 days + vintage;
  `CANONICAL_FIGURES.json` walkforward_purge_hours / walkforward_embargo_days): each test game
  trains only on games that started on an earlier date and settled more than the embargo before
  its day boundary, asserted in code; availability is never backdated. Excerpt:
  [WALK_FORWARD_LEAK_ASSERT.md](../method/WALK_FORWARD_LEAK_ASSERT.md).
- Implementation files are pinned by sha256 in the seal (listed under Receipts).
- Qualification grades the tape (coverage, linkage, staleness) before any cell can count.

## Evaluation

- Paired comparison (sealed): Brier and log loss per sport, segment and target, arms against arm A
  on the same ticks. Every cell is INSUFFICIENT until it holds 30 games
  (`CANONICAL_FIGURES.json` forward_cell_floor_games); the scoring identity is frozen until a cell
  reaches that floor (packet section 5). Interval method: null until the floor is met.

| As of | Reading | Verdict | Source |
|---|---|---|---|
| 2026-10-19 | every scoreboard cell, nights 10-06 to 10-10 and 10-12 | INSUFFICIENT (null interval) | packet section 5 |
| 2026-10-19 | current seal: 1 of the 30 games the floor needs (projected 2027-05-05) | INSUFFICIENT | packet section 5 |
| 2026-10-19 | qualification: 0 of 44 games judged qualified (nights 10-06 to 10-16) | no qualified decision | `CANONICAL_FIGURES.json` forward_window_counts |

- No interval, verdict or model-quality number exists for any arm. Per-night arm values on one or
  two games are not quoted. Descriptive receipts: `docs/evidence/forward/scoreboard/<D>.json` and
  the cumulative reader `docs/evidence/forward/cumulative/` (no interval). Reliability curves: not recorded.

## Known limitations

- The fitted arms were dark on most nights: fit `config_mismatch` (row S809) and
  `model_not_reconstructible` on 10-12 (packet section 5).
- The sealed scorer refits per history row, so wall time grows about quadratically (1,443 s at 29k
  rows); S824 raised the deadline as a stopgap; S825 is the fix (packet section 5).
- Laptop sleeps and a shadow recorder down since 2026-10-13 01:08Z left nights missing.
- All 44 judged games (through 10-16) failed qualification on COVERAGE_LOW and LINKAGE_INVALID.

## Retractions and corrections

- Superseded seals: 2026-09-24, 09-29, 09-30, 10-01, 10-03, 10-04, then 10-07 (current). A successor
  seal `PREREG_2026-10-21.json` (effective 2026-10-21) is committed; it is not described on this card.
- Retired claims that bear on this instrument
  ([retractions](https://neeljshah.github.io/court-vision/evidence/retractions/)): the
  forward-track-record row, the simulated-fills row, and the NBA-pre-registered row (all added
  2026-10-19, packet section 4).

## Reproduce

- Private corpus; not reproducible from the public tree (the capture archives are local-only).
  The seal and the pinned implementation files are tracked and can be hash-checked.

## Receipts

| Path | Bytes | sha256 | As of | Note |
|---|---|---|---|---|
| `docs/evidence/forward/scoreboard/PREREG_2026-10-07.json` | 2180 | 806fa58a3517d28b4f320e89c26f32a73ad6d1a5fe1f153aa5bf0aa9db7f85ea | 2026-10-20 | the seal |
| `scripts/platformkit/eval_gate/walkforward.py` | 8250 | 6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9 | 2026-10-20 | pinned |
| `scripts/platformkit/execution/ingame_scoreboard.py` | not recorded | 821ab4f66ecaabe0716ee4d8cc1ec7109d47264b6ad3ae874e46c97c4fbd301c | 2026-10-20 | pinned |
| `scripts/platformkit/execution/ingame_scoreboard_rules.py` | not recorded | a2228bffbcc0ba80903b72d3891cbb8b8b71ae3336a2c78571e9af51e5a5e002 | 2026-10-20 | pinned |
| `scripts/platformkit/ingame/baseline_four_arm.py` | not recorded | df1739348bb5d2f4823cb59489d4d4b99942eb34922d89247af568f11a76be48 | 2026-10-20 | pinned |
| `scripts/platformkit/ingame/baseline_four_arm_eligibility.py` | not recorded | 3a21ddd0f627087e245c15a5d1a07e795544d796f31e3c88d0125e5536817e20 | 2026-10-20 | pinned |
| `scripts/platformkit/ingame/baseline_four_arm_features.py` | not recorded | 79a9331477c50e224e783c565db44bd8a1293fe2cfab1273a968ac60cedaf959 | 2026-10-20 | pinned |
| `scripts/platformkit/ingame/baseline_four_arm_features_nfl.py` | not recorded | 117561dba781a8ba0b344fe657712023ebdb5aaf8b16cc3760bd2d66125af7c1 | 2026-10-20 | pinned |

Pinned hashes are the seal's, on LF-normalized bytes (the git blob); on 2026-10-20 all seven
matched HEAD. No fitted coefficients are persisted; the arms refit every night.

Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
