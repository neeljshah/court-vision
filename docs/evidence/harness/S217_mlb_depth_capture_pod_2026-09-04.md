# S217 MLB depth capture pod - FALSIFIED at premise

## Verdict

**FALSIFIED (Q8).** S217 step 0 required the local
`data/cache/depth_history/mlb` store to contain 15 files dated 2026-07-05 through
2026-09-02. The directory is absent in this worktree. This is a valid closure:
no live pass, restart construct, helper, test, deployment, flag change, or
store write was performed.

## Bounded premise re-measurement

| Required check | Result | Status |
|---|---:|---|
| `data/cache/book_depth/kalshi` file count | 0; directory absent | matches premise |
| `data/cache/depth_history/mlb` file count | 0; directory absent | FALSIFIES premise |
| `DEPTH_CAPTURE_EVERY_N_TICKS` at HEAD | 15 | unchanged |
| `LIVE_INTERVAL_SEC` at HEAD | 20.0 s | unchanged |
| `TARGET_CADENCE_SEC` at HEAD | 5.0 s | unchanged |
| `MAX_CADENCE_SEC` at HEAD | 60.0 s | unchanged |
| S105 reported live cadence | p50 30.0 s; p90 64.8 s | historical context only |

S105 attributes its reported p50 floor to an approximately 30 s full-pass
duration. It is not a new S217 live measurement. Because the required
depth-history premise is false, S217 stops before step 1; no measured S217 pass
floor or CLOSED AT LIMIT result exists.

## Construct and capture status

| Required item | Result |
|---|---|
| Clean-stop restart case | Not constructed; premise false |
| SIGTERM mid-pass restart case | Not constructed; premise false |
| Process-kill mid-write restart case | Not constructed; premise false |
| Live-game cadence table | Not measured; premise false |
| Duplicate count for `(date, ticker, ts)` | Not measured; no S217 capture JSONL |
| Lost-window count | Not measured; no S217 capture JSONL |
| 429 tally | Not measured; no S217 requests |
| Capture JSONL sample and summary JSON | Not created; no S217 capture run |

Files that would be deployed: none. B5 prohibits pre-verification deployment,
and the Q8 closure leaves no helper to deploy.

## Inputs opened

All paths below are under `C:\Users\neelj\nba-track-a17`. No raster input was
opened, so resolution is not applicable.

| Path | Bytes | Use |
|---|---:|---|
| `docs/evidence/tracking/specs/S217_spec.md` | 4,108 | S217 requirements |
| `docs/evidence/tracking/VERIFIER_CONTRACT.md` | 11,650 | sections B and Q |
| `docs/evidence/harness/S105_depth_capture_cadence_2026-09-03.md` | 19,852 | prior cadence context |
| `scripts/platformkit/ingame/inplay_capture_loop.py` at HEAD | 72,794 | unchanged local cadence constants |
| `scripts/platformkit/ingame/mlb_book_capture.py` at HEAD | 14,900 | unchanged capture constants |
| `data/cache/book_depth/kalshi` | absent | metadata-only file count |
| `data/cache/depth_history/mlb` | absent | metadata-only file count; falsifying fact |

## Verification status

- Test: not run. S217 requires stopping at the falsified premise before helper
  construction; no new test file exists.
- Q1, Q2, Q4, Q5, and Q9: not applicable. This is not a scored comparison or
  a capture run; no preregistration, charge, K read, model result, or
  differential artifact was created.
- Q3: all four named cadence constants were rechecked at HEAD and not changed.
- Q6: calibration language only.
- Q7: the three-case construct did not begin because Q8 requires the stop.
- B1-B4 and B6-B9: no schema, gate, claim lifecycle, reader, or metric code
  changed. B5: no file was deployed. B10: no threshold changed.
- The register and ledger received no writes. No file under `data/` was written.

## NOT VERIFIED

- A live MLB slate was not available for S217 because the step-0 store premise
  was already false.
- The capture helper and its restart behavior were not implemented or tested.
- The acceptance cadence, uniqueness, lost-window, and 429 quantities cannot
  be reproduced because S217 correctly produced no capture archive.
