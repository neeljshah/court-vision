# G68D basketball paint-solvability census

**Verdict: ACCEPT. The pre-registered approximately 0.10 rule does not trigger: basketball paint solvability is 1,029/1,650 = 0.6236 (Wilson 95% [0.6000, 0.6467]) and is spread throughout every clip, so the per-frame paint route remains eligible; this aggregation writes no role-assignment lane.**

## Precondition and denominator

All eleven required label files were present under `g68_paint_census/labels/`, and each had exactly 150 data rows: `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds`, `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p`, `ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss`, `ncaa_basketball__ncaa_basketball_sRtHQbywiTE`, `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo`, `ncaa_basketball__ncaa_basketball_zqBCKovJCQU`, `wnba__wnba_01`, `wnba__wnba_01_1080p`, `wnba__wnba_02`, `wnba__wnba_04`, and `wnba__wnba_05`. The fixed denominator is therefore all 1,650 sampled decoded tiles, not court-only frames.

The labels remain frozen chunk calls. This lane added no labels and did not re-judge any tile.

## Results

The durable per-clip breakdown, including Wilson 95% intervals and the frame-index clustering calculation, is [aggregate_2026-09-02.csv](g68_paint_census/aggregate_2026-09-02.csv).

| Scope | PAINT_SOLVABLE / all tiles | Share, Wilson 95% | COURT_NO_PAINT / all tiles | Share, Wilson 95% |
|---|---:|---:|---:|---:|
| NCAA | 549 / 900 | 0.6100 [0.5777, 0.6413] | 92 / 900 | 0.1022 [0.0841, 0.1237] |
| WNBA | 480 / 750 | 0.6400 [0.6050, 0.6736] | 115 / 750 | 0.1533 [0.1293, 0.1809] |
| Pooled | 1,029 / 1,650 | 0.6236 [0.6000, 0.6467] | 207 / 1,650 | 0.1255 [0.1103, 0.1423] |

`COURT_NO_PAINT` is a result in its own right: 207/1,650 = 0.1255 [0.1103, 0.1423] of every sampled broadcast tile was a court view whose paint was not fittable. The rate is higher in WNBA (0.1533) than NCAA (0.1022) in these clips.

## Frame-index clustering check

For each 150-row file, the ordered sample was partitioned into ten contiguous 15-tile temporal deciles. `PAINT_SOLVABLE` occurs in all 10/10 deciles for every one of the 11 clips; the first and last solvable sampled frame also span nearly each clip's full sampled index range. The per-clip table records `SPREAD` for all clips. Thus solvable tiles spread across each clip; they do not bunch into a few static half-court stretches. This supports a per-frame route rather than a dead-ball-only route.

## Seeded full-resolution re-read

The already-persisted G68A re-read is [g68a_eye_check_2026-09-02.md](g68_paint_census/g68a_eye_check_2026-09-02.md): seed `68017`, 20 sampled `PAINT_SOLVABLE` calls, 0 flips. No re-read was repeated here, consistent with aggregation-only scope. No separately persisted G68B/G68C re-read record was found; consequently the documented aggregate is **0 flips / 20 re-read calls**, not a claim of 20 re-reads per chunk.

## Comparison and disposition

Soccer, ranked most tractable before these censuses, recorded 72/1,500 = 0.0480 [0.0383, 0.0600] and CLOSED AT LIMIT. Basketball's 0.6236 [0.6000, 0.6467] is far higher, reversing that prior strategy ranking for the paint/box landmark route. The pre-registered 0.10 rule is unchanged and is not met on either condition: the pooled share is above 0.10 and calls spread across clips.

## Verifier-contract self-check

- A7: the memo, aggregate table, eleven label files, G68A re-read record, and referenced contact-sheet directory exist at reporting time.
- B1: every sampled tile is in the denominator; no court-only or accepted-frame conditioning occurred.
- B2-B6: no schema, reader, gate, deployment, module, or claim state changed.
- B7: aggregation used every row of all clips, not a head slice.
- B8-B9: no fitted residual or recycled/trivial denominator is used; rows are sampled decoded tiles.
- B10: the pre-registered approximately 0.10 decision rule and chunk labels were not changed.

## Not verified

- This aggregation did not independently rerun content-hash deduplication; it relied on the frozen 11-clip list stated by the G68 specs. The earlier hash-table artifact is not present in this checkout.
- It does not validate a paint-line solver, line-role assignment, an independent landmark, or a persisted per-frame homography sidecar.
- The documented full-resolution re-read covers G68A's 20 calls only; no persisted G68B/G68C re-read record was available to aggregate.
