# Model card: M2 market-anchored state projection (S542 / PREREG_M2)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

## Name and version

- Name: PROJ, the market-anchored state projection built in row S542 and read out nightly as M2
  under row S544.
- Version: replay seal `s542_prereg_v1` (seal 95e9cfa5ba51959666e97e3aa491ac7fccedb259fc062e2d4f9104b373dbec29,
  `docs/evidence/harness/S542_prereg.json`); forward read-out seal `docs/evidence/forward/model2/PREREG_M2.json`
  (row S544, effective 2026-10-01, latest_effective_date 2026-10-19).

## Intended use

- A staleness backstop: when our copy of the venue book is stale, project the last mid forward
  through the game events seen since, so the stale price is not used as if it were current.
- Scored by Brier against the STALE book only (S542 memo, Status line).

## Not intended use

- Paper only. Not a wagering signal and not a sizing input; no return figure is computed or implied.
- Not a claim against a fresh mid: the readout label is "vs our own stale receipt copy of the
  venue mid; receipt age is ours, not the venue's" (PREREG_M2 constants).

## Inputs and leak guard

- Inputs: the anchor mid at the anchor time; the score / clock state since; NBA Stern win
  probability with mu inversion (mu clip 30, sigma 22.0, period 2880 s); MLB normal-approximation
  win expectancy with a 60-step mu bisection (S542 memo; PREREG_M2 constants).
- Leak guard: state is taken as known at t - L (feed lag L); sigma is cross-fit (chosen on the other
  season); a placebo with same-season donors and a lag canary are scored (S542 replay).

## Training data and period

- NBA: `nba_checkpoints_r1` (Polymarket, data card C1), seasons 2024-25 (656 games) and 2025-26
  (937 games). MLB: 35 games, 2026-09, vs own stale receipt (S542 replay).
- Forward: the desk's capture archives from 2026-10-01 (PREREG_M2 effective date).

## Validation protocol

- Game-clustered bootstrap (2,000 resamples, seed 13), lags 0 / 18 / 31 / 60 s plus a canary,
  placebo cell, verdict rule sealed before the first metric (S542 memo; PREREG_M2 constants).
- Forward floor: 30 games per cell (PREREG_M2 `floor`).

## Measured performance

| As of | Cell | games | PROJ minus STALE | PROJ minus FRESH | Source |
|---|---|---|---|---|---|
| 2026-09-29 | nba L0 2025-26 projected | 937 | -0.00255 [-0.00347, -0.00186] | -0.00059 [-0.00149, +0.00009] | S542 replay |
| 2026-09-29 | nba L18 2025-26 projected | 937 | -0.00200 [-0.00296, -0.00127] | +0.00006 [-0.00088, +0.00077] | S542 replay |
| 2026-09-29 | mlb Lreal 2026-09 all | 35 | -0.00091 [-0.00208, -0.00011] | -0.00036 [-0.00124, +0.00044] | S542 replay |

- Replay verdict: ACCEPT_STALENESS_BACKSTOP_ONLY. Brier deltas, negative = PROJ closer to the
  outcome; intervals are game-clustered 95 percent (S542 replay).
- Forward M2 read-outs: through 2026-10-16 no cell exceeds 11 games, below the 30-game floor; no
  verdict (`docs/evidence/forward/model2/m2/HISTORY.json`).

## Calibration diagnostics

- Per-cell FRESH / STALE / PROJ Brier, recovery fraction R, placebo and canary cells in the replay
  file. Reliability curves: not recorded.

## Known failure modes and limitations

- Against a fresh mid PROJ is no better anywhere and measurably worse at L18 in 2024-25 (+0.00058 [+0.00025, +0.00089]); its value is only against our stale receipt.
- Replay rows (S542 replay memo lines 28-38, PROJ minus FRESH): nba/L18/2024-25/projected +0.00058 [+0.00025, +0.00089]; nba/L18/2024-25/all +0.00046 [+0.00026, +0.00066].
- Replay cells are on nba_checkpoints_r1, where 244,183 of 465,249 rows are post-final dead ticks (D12); on live ticks only, 2025-26 PROJ minus FRESH is -0.00270 [-0.01057, +0.00377] (INGAME_MODEL_2_PLAN A1).
- ACCEPT is conditional on the ESPN wallclock not leading the real event (S542 memo, lines 103 and 112).
- PREREG_M2 latest_effective_date is 2026-10-19; read-outs after that date are outside this seal.
- Single venue per sport (Polymarket NBA; Kalshi MLB); MLB n is small (35 games).
- Several S542 pins in PREREG_M2 refer to LF-normalized bytes; on 2026-10-20 all ten matched HEAD.

## Artifacts

| Path | Bytes | sha256 | Note |
|---|---|---|---|
| `docs/evidence/harness/S542_prereg.json` | 3345 | 36ade6ced3c044cf34b2eb18d147b14d3b1f8616374f3afadc18aa36cdd62489 | replay seal file |
| `docs/evidence/harness/S542_anchor_projection_replay_2026-09-29.json` | 35315 | e7b4366332313011b563512dbe87ddb053f5169d6d563985796d366029cae3a9 | replay result |
| `docs/evidence/forward/model2/PREREG_M2.json` | 4660 | 1bf7f6b9c3d5bb50188fe1e5021939c64b3126aea1111ac32262414510dbad3d | forward seal |

- No fitted binary: the projection is a closed-form formula with sealed constants.

## Retraction and supersession history

- None recorded. The probe memos that preceded this build are under
  `docs/evidence/harness/ingame_model_2_probes/`; their verdict count is not recorded on this card.

## Owner and last verified

- Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
