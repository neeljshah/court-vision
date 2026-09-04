# S214 Soccer In-Play Census

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S214.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q (Q1-Q9).

## Verdict

**FALSIFIED.** The two named parquet stores are absent from this worktree, and the premise that neither is read by a module is also false. Per the S214 step-0 stop rule, no census module, test, summary JSON, or per-event CSV was produced.

## Step 0 premise re-measurement

Input files opened: none. The file inventory below was metadata-only; no parquet file was opened, so there is no byte size, resolution, row count, event count, or ParquetFile metadata to report.

The two independent, whole-worktree filename inventories were run one store at a time:

| expected store | inventory result | metadata result |
|---|---:|---|
| `soccer_price_series.parquet` | 0 matches | unavailable: no file exists in this worktree |
| `soccer_intl_price_series.parquet` | 0 matches | unavailable: no file exists in this worktree |

The required S117 baseline does reproduce from its archived memo:

| S117 fact | archived value |
|---|---:|
| total ticks | 9,003 |
| events | 51 |
| usable events | 29 |
| usable ticks | 3,658 |
| scored ticks | 163 |
| scored game clusters | 2 |

## Reader survey

The required module-reader grep over `scripts/platformkit/**/*.py` returned one hit, not zero:

| file | lines | finding |
|---|---|---|
| `scripts/platformkit/ingame/s90_microstructure_screen.py` | 45, 81-97 | Defines `SOCCER_PRICES` as `data/cache/inplay_odds/soccer_intl_price_series.parquet` and passes that path to `pd.read_parquet` when it exists. |

The source reader has an existence guard, so it did not open the absent file in this run. The reader claim in S214 is nevertheless falsified because this module contains the parquet read path.

The documentation reference grep returned five hits: the S214 gap row, `INGAME_DATA_ENGINE_PROGRAM_2026-09-04.md`, `S80_player_grain_2026-09-03.md`, `S81_market_move_2026-09-03.md`, and `S90_microstructure_screen_2026-09-04.md`.

## Stop result

The absent stores make the requested exhaustive five-class classification impossible, and the existing module reader independently falsifies the stated no-reader premise. No interpolation, state join, score, charge, preregistration, ledger operation, flag change, or data write occurred. The register and ledger were not touched.

## Contract self-check

- **B1-B10:** no metric was computed and no schema, reader, threshold, deployment, or data surface changed.
- **Q1-Q5, Q9:** not applicable; this is an unscored premise-stop result with no comparison or differential.
- **Q6:** calibration language only.
- **Q7:** no sampled or scored metric was produced.
- **Q8:** the premise was re-measured before implementation and is falsified.

## NOT VERIFIED

There is no class table, state-age table, join-key resolution table, summary JSON, or per-event summary CSV because S214 requires stopping immediately on a falsified premise. A future row would need to establish the presence and intended source paths of the two stores before a census can run.
