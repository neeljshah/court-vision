# G176 - decoded coverage gate across sports

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), especially A2, A7,
B1-B10, Q7, and Q8. This was one batched, read-only pod-ledger snapshot. No
pod file was changed, and the daemon was neither stopped, restarted, polled,
nor deployed over.

## Q8 premise first: current harness bars

These values are quoted from the current local harness, not copied from the
specification. They are observations only; no bar, gate, coordinate contract,
or verdict was changed.

| Harness sport | `coverage_min` | Source |
|---|---:|---|
| basketball | 0.60 | `scripts/platformkit/tracking_harness.py:24-27` |
| wnba | 0.60 | `scripts/platformkit/tracking_harness.py:37-38` (copies basketball map) |
| baseball | 0.70 | `scripts/platformkit/tracking_harness.py:28-31,47-49` |
| npb | 0.70 | `scripts/platformkit/tracking_harness.py:28-31,47-49` |
| kbo | 0.70 | `scripts/platformkit/tracking_harness.py:28-31,47-49` |
| tennis | 0.90 | `scripts/platformkit/tracking_harness.py:39-42` |
| soccer | 0.85 | `scripts/platformkit/tracking_harness.py:43-46` |
| football | 0.85 | `scripts/platformkit/tracking_harness.py:52-55` |

The premise that ledger `coverage_pct` can be compared to one of those bars is
**FALSIFIED**. As [G164](g164_three_coverages_2026-09-03.md) established, the
ledger field is emitted-frame presence over decoded frames. The gate needs the
fraction of decoded-padded frames with at least `min_players` player IDs.

## Eligible denominator and result

The eligible denominator is **every physical line in the current pod
`track_daemon_ledger.jsonl`**: 17 physical rows, all 17 valid JSON rows. No
row was excluded for status, sport, duplicate game ID, null metric, or failed
verdict. The 17 physical rows contain 16 distinct `game_id` values because
`wnba_01` appears twice; both physical appends remain in the denominator.

`coverage_pct` below is explicitly the ledger quantity, not the coverage-gate
quantity. `C` is the literal coordinate-contract head reproduced in the raw
output: `coordinate_contract: rows declare coordinate_space image_px not
accepted for sport <sport>; a preserved detection corpus is never a scorable
game`.

| # | sport | game_id | rows | decoded_frames | ledger coverage_pct | passed | failure heads | coverage-gate state |
|---:|---|---|---:|---:|---:|---|---|---|
| 1 | baseball | mlb_2026-08-30_10893dca | 32,380 | 39,035 | 0.1565 | false | C (baseball) | NOT EVALUATED: coordinate contract |
| 2 | baseball | kbo_01 | 63,497 | 69,170 | 0.1573 | false | C (baseball) | NOT EVALUATED: coordinate contract |
| 3 | baseball | mlb_2026-08-30_0f36e8cc | 54,537 | 49,079 | 0.1607 | false | C (baseball) | NOT EVALUATED: coordinate contract |
| 4 | baseball | mlb_2026-08-30_7e8080e5 | 48,816 | 41,029 | 0.1567 | false | C (baseball) | NOT EVALUATED: coordinate contract |
| 5 | baseball | mlb_2026-08-30_3a02d9b3 | 35,882 | 36,925 | 0.1563 | false | C (baseball) | NOT EVALUATED: coordinate contract |
| 6 | wnba | wnba_01 | 0 | null | null | null | none | NOT EVALUATED: thin |
| 7 | baseball | mlb_2026-08-30_08b16ce9 | 49,132 | 49,346 | 0.1583 | false | C (baseball) | NOT EVALUATED: coordinate contract |
| 8 | baseball | kbo_02 | 39,744 | 48,506 | 0.1561 | false | C (baseball) | NOT EVALUATED: coordinate contract |
| 9 | baseball | mlb_2026-08-30_1c6706c6 | 42,691 | 40,216 | 0.1575 | false | C (baseball) | NOT EVALUATED: coordinate contract |
| 10 | soccer | soccer_kSgNjoaqCpI | 230,794 | 182,100 | 0.0806 | false | C (soccer) | NOT EVALUATED: coordinate contract |
| 11 | baseball | mlb_2026-08-30_2b814fad | 46,490 | 40,179 | 0.1586 | false | C (baseball) | NOT EVALUATED: coordinate contract |
| 12 | baseball | kbo_03 | 39,254 | 46,976 | 0.1499 | false | C (baseball) | NOT EVALUATED: coordinate contract |
| 13 | baseball | mlb_2026-08-30_03d78bee | 39,998 | 37,862 | 0.1597 | false | C (baseball) | NOT EVALUATED: coordinate contract |
| 14 | ncaa_basketball | ncaa_basketball_IB-_u4gW3ds | 0 | null | null | null | none | NOT EVALUATED: thin |
| 15 | tennis | tennis_ref01 | 1,861 | 28,773 | 0.0252 | false | duplicate frame-track rows 4; coverage 0.02 < 0.90; median_track_len 1.00 < 3.00; jump_max 48.93 > 8.00 | FAILS coverage |
| 16 | wnba | wnba_01 | 0 | null | null | null | none | NOT EVALUATED: thin |
| 17 | baseball | mlb_2026-08-30_2143de43 | 46,570 | 43,564 | 0.1593 | false | C (baseball) | NOT EVALUATED: coordinate contract |

Per-sport physical-row accounting is baseball 12, soccer 1, tennis 1, WNBA 2,
and NCAA basketball 1: **12 + 1 + 1 + 2 + 1 = 17**. Fourteen rows are
`tracked` (13 coordinate-contract early returns and the one tennis adjudication);
three are `thin`.

## Answer to the coverage-gate question

**The number of rows confirmed to pass the decoded coverage gate is 0.** The
ledger alone does **not** answer whether any sport would pass it: it records
one explicit tennis coverage failure, but 13 tracked rows never reached the
coverage calculation and three thin rows have no adjudication. Therefore the
suspicion that the decoded gate fails every sport remains **NOT VERIFIED**, not
established by the ledger's 17 rows.

This is not an inference from overall `passed`: `passed=false` can arise at a
different gate, and `passed=null` is unadjudicated. It is also not an inference
from ledger `coverage_pct`: that scalar has the wrong numerator for the gate.
The retained per-row decoded-padded min-player coverage would answer the
question; it is discarded by `track_daemon_done.adjudicate`, as G164 found.

Coordinate normalization returns a failed report at
`tracking_harness.py:214-220`; the min-player coverage expression appears only
after it at `tracking_harness.py:248-251`. Thus the 13 `C` rows have no
coverage-gate value to read. Tennis's persisted `coverage 0.02 < 0.90` head is
the sole row-level coverage verdict in this ledger snapshot.

## Reproduction command and raw output

The following command was invoked once. Its payload only reads the ledger and
prints selected fields; `python3 -B` plus `PYTHONDONTWRITEBYTECODE=1` prevents
bytecode writes.

```sh
ssh -F "$HOME/.ssh/config.pod" -T pod 'printf %s <base64-encoded-read-only-payload> | base64 -d | /bin/sh'
```

The decoded payload read
`/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl`, counted its
physical lines, parsed each line, and printed the selected fields below.

```text
SNAPSHOT_UTC=2026-09-03T16:47:02+00:00
LEDGER_PATH=/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl
PHYSICAL_ROWS=17
ROW={"coverage_pct":0.1565,"decoded_frames":39035,"failure_heads":["coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball; a preserved detection corpus is never a scorable game"],"game_id":"mlb_2026-08-30_10893dca","index":1,"passed":false,"rows":32380,"sport":"baseball","status":"tracked"}
ROW={"coverage_pct":0.1573,"decoded_frames":69170,"failure_heads":["coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball; a preserved detection corpus is never a scorable game"],"game_id":"kbo_01","index":2,"passed":false,"rows":63497,"sport":"baseball","status":"tracked"}
ROW={"coverage_pct":0.1607,"decoded_frames":49079,"failure_heads":["coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball; a preserved detection corpus is never a scorable game"],"game_id":"mlb_2026-08-30_0f36e8cc","index":3,"passed":false,"rows":54537,"sport":"baseball","status":"tracked"}
ROW={"coverage_pct":0.1567,"decoded_frames":41029,"failure_heads":["coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball; a preserved detection corpus is never a scorable game"],"game_id":"mlb_2026-08-30_7e8080e5","index":4,"passed":false,"rows":48816,"sport":"baseball","status":"tracked"}
ROW={"coverage_pct":0.1563,"decoded_frames":36925,"failure_heads":["coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball; a preserved detection corpus is never a scorable game"],"game_id":"mlb_2026-08-30_3a02d9b3","index":5,"passed":false,"rows":35882,"sport":"baseball","status":"tracked"}
ROW={"coverage_pct":null,"decoded_frames":null,"failure_heads":[],"game_id":"wnba_01","index":6,"passed":null,"rows":0,"sport":"wnba","status":"thin"}
ROW={"coverage_pct":0.1583,"decoded_frames":49346,"failure_heads":["coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball; a preserved detection corpus is never a scorable game"],"game_id":"mlb_2026-08-30_08b16ce9","index":7,"passed":false,"rows":49132,"sport":"baseball","status":"tracked"}
ROW={"coverage_pct":0.1561,"decoded_frames":48506,"failure_heads":["coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball; a preserved detection corpus is never a scorable game"],"game_id":"kbo_02","index":8,"passed":false,"rows":39744,"sport":"baseball","status":"tracked"}
ROW={"coverage_pct":0.1575,"decoded_frames":40216,"failure_heads":["coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball; a preserved detection corpus is never a scorable game"],"game_id":"mlb_2026-08-30_1c6706c6","index":9,"passed":false,"rows":42691,"sport":"baseball","status":"tracked"}
ROW={"coverage_pct":0.0806,"decoded_frames":182100,"failure_heads":["coordinate_contract: rows declare coordinate_space image_px not accepted for sport soccer; a preserved detection corpus is never a scorable game"],"game_id":"soccer_kSgNjoaqCpI","index":10,"passed":false,"rows":230794,"sport":"soccer","status":"tracked"}
ROW={"coverage_pct":0.1586,"decoded_frames":40179,"failure_heads":["coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball; a preserved detection corpus is never a scorable game"],"game_id":"mlb_2026-08-30_2b814fad","index":11,"passed":false,"rows":46490,"sport":"baseball","status":"tracked"}
ROW={"coverage_pct":0.1499,"decoded_frames":46976,"failure_heads":["coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball; a preserved detection corpus is never a scorable game"],"game_id":"kbo_03","index":12,"passed":false,"rows":39254,"sport":"baseball","status":"tracked"}
ROW={"coverage_pct":0.1597,"decoded_frames":37862,"failure_heads":["coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball; a preserved detection corpus is never a scorable game"],"game_id":"mlb_2026-08-30_03d78bee","index":13,"passed":false,"rows":39998,"sport":"baseball","status":"tracked"}
ROW={"coverage_pct":null,"decoded_frames":null,"failure_heads":[],"game_id":"ncaa_basketball_IB-_u4gW3ds","index":14,"passed":null,"rows":0,"sport":"ncaa_basketball","status":"thin"}
ROW={"coverage_pct":0.0252,"decoded_frames":28773,"failure_heads":["duplicate frame-track rows 4","coverage 0.02 < 0.90","median_track_len 1.00 < 3.00","jump_max 48.93 > 8.00"],"game_id":"tennis_ref01","index":15,"passed":false,"rows":1861,"sport":"tennis","status":"tracked"}
ROW={"coverage_pct":null,"decoded_frames":null,"failure_heads":[],"game_id":"wnba_01","index":16,"passed":null,"rows":0,"sport":"wnba","status":"thin"}
ROW={"coverage_pct":0.1593,"decoded_frames":43564,"failure_heads":["coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball; a preserved detection corpus is never a scorable game"],"game_id":"mlb_2026-08-30_2143de43","index":17,"passed":false,"rows":46570,"sport":"baseball","status":"tracked"}
VALID_JSON_ROWS=17
```

## Independent recomputation and verifier self-check

**A2/A4/Q7.** I independently counted the raw rows: 12 baseball + 1 soccer +
1 tennis + 2 WNBA + 1 NCAA basketball = 17 physical, valid JSON rows. The 17
physical lines reduce to 16 distinct game IDs only because the same `wnba_01`
thin record occurs twice; no duplicate is silently removed. This is the
required exhaustive construct enumeration, so no render sample applies.

**A7.** Before commit, the evidence paths named here were confirmed present:
this memo, `docs/evidence/tracking/VERIFIER_CONTRACT.md`,
`docs/evidence/tracking/g164_three_coverages_2026-09-03.md`, and
`docs/evidence/tracking/specs/G176_spec.md`. The pod ledger is reproduced as
raw output above rather than cited as an uncommitted external artifact.

No test was run: this change is evidence-only. No full test suite was run.

| Section B condition | Self-check |
|---|---|
| B1 circular metric | Clear. Every physical ledger row is named; neither coverage quantity is filtered to passing rows. |
| B2 non-additive schema | Clear. No schema, field, status, reader, or code changed. |
| B3 fall-through loss | Clear. No daemon gate, lifecycle, claim, or retention path changed. |
| B4 re-claim loop | Clear. No claim or failure path changed. |
| B5 pre-verification deploy | Clear. No file was copied or deployed to the pod. |
| B6 orphans | Clear. No module moved, retired, imported, or tested. |
| B7 head-slice evidence | Clear under Q7. All 17 physical ledger rows form the construct denominator. |
| B8 self-fit as independent | Clear. No fitted model, residual, or comparison is claimed. |
| B9 degenerate denominator | Clear. The denominator is the current physical append population, with its one duplicate disclosed. |
| B10 moved bar | Clear. The harness values were read and quoted only; no threshold, gate, coordinate contract, or verdict changed. |

## NOT VERIFIED

- Whether any of the 13 coordinate-contract rows would pass the decoded
  min-player coverage gate if their coordinate precondition were satisfied.
- Whether any of the three thin rows would pass after an adjudication exists.
- Any aggregate of the scalar ledger `coverage_pct` as a coverage-gate result.
- A program-wide claim that every sport fails decoded coverage. The current
  ledger cannot establish it.
