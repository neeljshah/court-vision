# S264 ISO-week game-ID overlap

## Contract and result

This memo follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
Result: REPARTITIONED. The premise was confirmed, not falsified.

## Inputs and code identity

| item | path | bytes or SHA-256 | resolution |
|---|---|---|---|
| premise store | `data/cache/ingame_grade_joined` | 73485324 bytes | N/A: read-only JSONL store |
| source calibration table | `docs/evidence/harness/s88_phase_recal_2026-09-04.csv` | 4311731 bytes; `B7CC67E0FF39A8F20B9B12E981CE93C2ACE55374B38D9805E092ADA99F9BA91D` | N/A: CSV |
| S88 route | `scripts/platformkit/ingame/s88_phase_recal.py` | `42053BE397858A7346F8109682146DC94D363AB7BC0AB2F2BC874D26870CDD8A` | N/A: Python |
| CPCV route | `scripts/platformkit/eval_gate/cpcv_engine.py` | `D91983E8410E4F7072A3D74E6B61C44420F66E64FE384EA802D4385F4D052CB9` | N/A: Python |
| S264 route | `scripts/platformkit/ingame/s264_isoweek_overlap.py` | `C747BDAC1121055CC80E83D16E43C521E7C8B7AEDAA181E4B0C165C2E81368E3` | N/A: Python |

## Binding premise measurement

The exact named binding was rerun: `discover_store`, `hedge_trial_arms.load_corpus`,
and `s88_phase_recal.build_records`, then every returned record was grouped by
`iso_week(ts)` and `game_id`. Its exact output was:

```text
STORE=data/cache/ingame_grade_joined
STORE_BYTES=73485324
RECORDS=47104
DISTINCT_GAME_IDS=158
ISO_WEEK_BLOCKS=2
SHARED_GAME_ID_COUNT=4
SHARED_GAME_IDS=KXMLBGAME-26JUL051920SDLAD,KXMLBGAME-26JUL052130BOSLAA,KXMLBGAME-26JUL061410PHIKC,KXMLBGAME-26JUL061915NYMATL
WEEK_BLOCKS=2026-W27:72;2026-W28:90
```

The published non-burn-in S88 calibration table is the 33,920-row gate subset.
Its exhaustive ISO-week check has the same four shared IDs: 41 distinct game IDs
in 2026-W27 and 90 in 2026-W28. No row was excluded from either count.

## Additive game-first-date table

`docs/evidence/harness/S264_s88_phase_recal_game_first_date_2026-09-04.csv`
(4,956,239 bytes) is the new 33,920-row table. It preserves every pre-existing
source column and source string value byte-for-byte per CSV cell, then adds:

- `iso_week_alias`: the unchanged ISO year/week derived from `ts`.
- `game_id_block`: `_first_dates(ticks)[game_id]`, the earliest raw
  `timestamp[:10]` used by S88's outer game-first-date walk-forward construction.

The new key is additive; no source table, threshold, flag, serving route, or
SCREEN/VERDICT membership was changed. S88 has no `screened_n` field, so there is
no family screening count to reprint. The game-first-date block counts are:

| game_id_block | distinct game IDs |
|---|---:|
| 2026-07-03 | 14 |
| 2026-07-04 | 22 |
| 2026-07-05 | 5 |
| 2026-07-06 | 6 |
| 2026-07-07 | 23 |
| 2026-07-08 | 12 |
| 2026-07-09 | 2 |
| 2026-07-10 | 18 |
| 2026-07-11 | 24 |
| 2026-07-12 | 1 |

The shared-ID count is 4 under `iso_week_alias` and 0 under `game_id_block`.

## Sealed calibration reproduction

Preregistration: `docs/evidence/harness/S264_game_first_date_prereg_2026-09-04.md`.
Its committed-byte seal is
`af5a5d8c66c45cf2116fa4abf2cb1be3ce77e8bb794129e73f48a4abad4af9da`.
After its commit, the required verification command
`git show HEAD:docs/evidence/harness/S264_game_first_date_prereg_2026-09-04.md | head -n 37 | sha256sum`
returned that same SHA-256.

The source and new tables were each evaluated through `cpcv_evaluate` with two
groups, one test group, a symmetric nonzero one-day embargo, and the evaluator's
48-hour team purge. Strict redaction was enabled. The evaluator callback emitted
the as-of `published_recal_prob` feature for every probability: 33,920 unique
`(game_id, ts)` outputs for each table.

| iso_week_alias | n | recal Brier | incumbent Brier | market Brier |
|---|---:|---:|---:|---:|
| 2026-W27 | 15207 | 0.20100813802070910 | 0.20612712281659337 | 0.19283151673571977 |
| 2026-W28 | 18713 | 0.21138417144683716 | 0.21584596179730160 | 0.20833856409982680 |

Source and new-table summaries selected through `iso_week_alias` have maximum
absolute difference 0.0, within the unchanged `1e-9` bar.

`docs/evidence/harness/S264_isoweek_game_id_overlap_paired_loss_2026-09-04.csv`
(6,373,333 bytes) archives all 33,920 source/output paired losses with cluster ID,
timestamp, both partition keys, and both probabilities. Every `loss_difference`
is 0.0.

## Test and verifier self-check

```text
python -m pytest tests/platformkit/ingame/test_s264_isoweek_overlap.py -q
2 passed
```

- B1/B9/Q7: every raw and gate-subset row is counted; game ID is the named unit.
- B2: all additions are new columns in a new table; the reader survey found no
  existing readers of either added field outside the S264 route and its dedicated test.
- B3-B6/B10: no gate fallback, claim path, deployment, retired route, or threshold changed.
- B7/B8: this S-row has no eye check and no fitted model comparison.
- Q1: the final preregistration and committed-byte seal above predate final scoring.
- Q2/Q5: no charged trial, ledger action, or AHEAD claim is involved.
- Q3/Q4/Q9: the unchanged bar, purged symmetric-embargo CPCV, callback outputs,
  and full paired-loss archive are recorded above.
- Q6: calibration language only.

## NOT VERIFIED

- Production deployment, model selection, and downstream adoption of the new partition key were not evaluated.
