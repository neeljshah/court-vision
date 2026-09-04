# S253 CDN on-court-five reconstruction

## Scope and premise

This construction audit reads `data/domains/wnba/cdn_backfill` sequentially, one JSON file at a time. It opened 168 `boxscore.json` and 168 `playbyplay.json` files, all from the 168 game directories in that archive. The exact path, byte size, SHA-256, and `n/a_json` resolution for every opened source file are recorded in [input_manifest.csv](S253_nba_oncourt_five_from_cdn_subs_2026-09-04/input_manifest.csv).

The step-0 premise re-measure found 168/168 paired games with exactly five string-valued `starter == "1"` players for each team, and 168/168 paired play-by-play payloads with at least one `actionType == "substitution"` action. The premise holds.

The module used was `scripts/platformkit/ingame/nba_oncourt_five_from_cdn_subs.py`, SHA-256 `5f8467b78708831c4ab2463d46d0727c173c2ca01974286e2ebcb846ace67107`. It is additive, 261 lines, and does not call or alter `boxscore_read.py` or `ingame_live_state.py`.

## Reconstruction and limit

The module seeds both five-player sets from the boxscore starters, groups substitution actions by `timeActual`, replays each group in wallclock order atomically, and writes an opening stamp plus one post-substitution stamp for every resolved group. A group is rejected when its in/out counts differ, its memberships do not resolve from the prior five, or either side does not close at five.

The limit result is CLEAR: 167 qualifying game clusters is above the 30-game minimum. Game `1022600019` is excluded and named in [not_verified.csv](S253_nba_oncourt_five_from_cdn_subs_2026-09-04/not_verified.csv): at period 4, clock `PT00M13.10S`, a substitution batch attempts to add already-on-court players. It is not silently included or removed from any qualifying-game metric.

## Recomputed construction results

| Measure | Result |
|---|---:|
| Archive pair directories enumerated | 168 |
| Qualifying game clusters | 167 |
| Substitution-bounded ticks in denominator | 5,647 |
| Complete five-by-five stamps | 5,647 |
| Coverage | 100.00 pct |
| Duplicate-on-court violations | 0 |
| Substitution in/out imbalance | 0 |
| Excluded games | 1 |

The complete derived table is [stamps.csv](S253_nba_oncourt_five_from_cdn_subs_2026-09-04/stamps.csv), 929,213 bytes, below the 2 MB artifact limit. The self-contained summary is [summary.json](S253_nba_oncourt_five_from_cdn_subs_2026-09-04/summary.json), and the consistency table is [consistency.csv](S253_nba_oncourt_five_from_cdn_subs_2026-09-04/consistency.csv).

For an evenly spaced deterministic 30-game spot check, 844 player rows compare summed reconstructed on-court interval seconds with the same-game boxscore `statistics.minutes` value. All 844 rows have zero absolute difference seconds. The full table is [minutes_spot_check.csv](S253_nba_oncourt_five_from_cdn_subs_2026-09-04/minutes_spot_check.csv).

## Reproduction

Run this command from the repository root:

```text
python -m scripts.platformkit.ingame.nba_oncourt_five_from_cdn_subs data/domains/wnba/cdn_backfill docs/evidence/harness/S253_nba_oncourt_five_from_cdn_subs_2026-09-04
```

The verifier can recompute the derived table, coverage denominator, five-player uniqueness, in/out balance, exclusion list, and minutes check from the archive pairs alone. The archive was only read; no file under `data/` was written. The manifest preserves the source identities needed to check that assertion.

## NOT VERIFIED

- Generalization beyond the enumerated 168-game WNBA archive.
- Independent validation of CDN starter, substitution, and minutes fields.

## Verifier-contract self-check

- B1: The denominator contains every opening and substitution-bounded tick from all 167 qualifying games. The one non-qualifying game and exact reason are named.
- B2-B6: This is an additive module with no renamed schema, callers, deployment, or retired route.
- B7-B9: This is an exhaustive archive reconstruction, not a head slice or fitted comparison; its game and tick denominators are named.
- B10: The stated bar remains 95 pct coverage, zero duplicate violations, zero in/out imbalance, and at least 30 game clusters.
- Q1-Q5 and Q9: Not applicable. This is a full-archive construction audit, not a scored predictive comparison or trial.
- Q6: This memo makes only construction and calibration-safe statements.
- Q7: All 168 archive directories were enumerated; the 30-game minutes check is evenly spaced and names its count.
- Q8: The starter and substitution premise was re-measured before implementation.

Verdict: ACCEPT. No register or ledger was modified.
