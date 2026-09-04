# S222 Refresh-Layer Census

Date: 2026-09-04 | Area: in-game refresh layer | Verdict: **FALSIFIED**

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q1-Q9.
Calibration language only. No scored comparison was run.

## 0. Premise first

S222 requires metadata measurement first, one source at a time, with no whole
store read over 300 MB. `pyarrow.parquet.ParquetFile(path).metadata` measured
the 12 present Parquet sources below. Every file has one row group; only
`bullpen_relief_chains.parquet` then read its one 475,148-byte row group, and
only the `date` and `team` columns, to reproduce the stated final-day count.

The bullpen headline is confirmed: **71,523 rows**, date range
**2022-04-07 through 2026-07-02**, and **8 rows over 2 teams** on 2026-07-02.

The lineup-minutes headline is falsified: the required source
`data/cache/team_system/player_rates.parquet` is absent in this worktree.
Its date range, refresh status, and possible tick relationship cannot be
measured. S222 directs a stop when any headline is falsified, so no census
module, feature, join, flag, or test was created.

## 1. Constructed refresh-table list

The denominator is all 13 tables in the four S222 classes. `NOT COMPUTED` is
explicit, never a blank: the premise stop occurs before reading a separate
latest-tick corpus or scanning builders and join consumers.

| table | rows | min date | max date | staleness days vs latest sport tick | declared as-of | joined to a tick |
|---|---:|---|---|---|---|---|
| `data/cache/ingame/pbp_states_2024_25.parquet` | 30,383 | 2024-10-22 | 2025-06-22 | NOT COMPUTED: premise stop | NO: no exact `asof_supply.REGISTRY` source entry | NOT VERIFIED: premise stop |
| `data/cache/ingame/pbp_states_2025_26.parquet` | 30,199 | 2025-10-21 | 2026-05-24 | NOT COMPUTED: premise stop | NO: no exact `asof_supply.REGISTRY` source entry | NOT VERIFIED: premise stop |
| `data/cache/ingame/pbp_foul_states_2024_25.parquet` | 30,383 | 2024-10-22 | 2025-06-22 | NOT COMPUTED: premise stop | NO: no exact `asof_supply.REGISTRY` source entry | NOT VERIFIED: premise stop |
| `data/cache/ingame/pbp_foul_states_2025_26.parquet` | 30,199 | 2025-10-21 | 2026-05-24 | NOT COMPUTED: premise stop | NO: no exact `asof_supply.REGISTRY` source entry | NOT VERIFIED: premise stop |
| `data/cache/ingame/possession_states_2024_25.parquet` | 30,383 | 2024-10-22 | 2025-06-22 | NOT COMPUTED: premise stop | NO: no exact `asof_supply.REGISTRY` source entry | NOT VERIFIED: premise stop |
| `data/cache/ingame/possession_states_2025_26.parquet` | 30,199 | 2025-10-21 | 2026-05-24 | NOT COMPUTED: premise stop | NO: no exact `asof_supply.REGISTRY` source entry | NOT VERIFIED: premise stop |
| `data/cache/ingame/mlb_pitch_states__2022.parquet` | 66,266 | 2022-04-07 | 2022-04-22 | NOT COMPUTED: premise stop | NO: no exact `asof_supply.REGISTRY` source entry | NOT VERIFIED: premise stop |
| `data/cache/ingame/mlb_pitch_states__2023.parquet` | 69,823 | 2023-03-30 | 2023-04-14 | NOT COMPUTED: premise stop | NO: no exact `asof_supply.REGISTRY` source entry | NOT VERIFIED: premise stop |
| `data/cache/ingame/mlb_pitch_states__2024.parquet` | 70,326 | 2024-03-20 | 2024-09-30 | NOT COMPUTED: premise stop | NO: no exact `asof_supply.REGISTRY` source entry | NOT VERIFIED: premise stop |
| `data/cache/ingame/mlb_pitch_states__2025.parquet` | 65,983 | 2025-03-18 | 2025-09-28 | NOT COMPUTED: premise stop | NO: no exact `asof_supply.REGISTRY` source entry | NOT VERIFIED: premise stop |
| `data/cache/ingame/mlb_pitch_states__2026.parquet` | 29,319 | 2026-03-25 | 2026-06-16 | NOT COMPUTED: premise stop | NO: no exact `asof_supply.REGISTRY` source entry | NOT VERIFIED: premise stop |
| `data/domains/mlb/bullpen_relief_chains.parquet` | 71,523 | 2022-04-07 | 2026-07-02 | NOT COMPUTED: premise stop | YES: `scripts/platformkit/foundry/asof_supply.py:131-132`, `prior` | NOT VERIFIED: premise stop |
| `data/cache/team_system/player_rates.parquet` | NOT VERIFIED: source absent | NOT VERIFIED: source absent | NOT VERIFIED: source absent | NOT VERIFIED: source absent | NO: no exact `asof_supply.REGISTRY` source entry | NOT VERIFIED: premise stop |

The table paths are the complete state-source list in
`docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md` lines 261, 324, 333,
and 360, plus the S222-specified bullpen and player-rate sources. Builder
modules remain NOT VERIFIED because the missing player-rate premise closes the
row before the requested census implementation.

## 2. Staleness ranking

Not computed. The source needed to represent the lineup-minutes class is
absent, so calculating a partial ranking or selecting a separate current tick
corpus would not satisfy S222's all-table denominator.

## 3. Summary JSON

`docs/evidence/harness/S222_refresh_layer_census_2026-09-04.json` archives the
complete denominator, exact source paths, byte sizes for all opened sources,
metadata measurements, and the stop reason. It contains no score or
differential because none was computed.

## 4. NOT VERIFIED

- The absent player-rate table's row count, dates, and refresh state.
- Staleness days and all tick joins, because the failed premise stops the row
  before any separate tick corpus or join-consumer census is read.
- Builder modules, because no implementation census is authorized after stop.
- The S222 per-file test, because no module was created.

## 5. Contract self-check

B1/B7/B8/B9: no metric, sample, or score was computed. B2/B6: no source code
or schema changed. B3/B4/B5: no gate, claim, deployment, or external action.
B10/Q3: `ingame_screen.BAR` was not changed. Q1/Q2: uncharged; no prereg was
sealed and no ledger was opened. Q4/Q5/Q9: no scored or comparative result was
produced. Q6: calibration language only. Q7: the 13-table list is a complete
constructive denominator. Q8: the source premise was measured before
implementation and is FALSIFIED by the missing player-rate source.

## 6. Result

**FALSIFIED.** S222 cannot construct its all-class refresh census while its
specified lineup-minutes source is absent. No data was written, no join was
created, no feature was built, no flag changed, and no register or ledger was
touched.
