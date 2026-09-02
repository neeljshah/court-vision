# S19 Request Governor Evidence

GAP S19 | sport mlb | worktree a11 | log cx_s19_request_governor

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

## Premise and fixed limit

The premise was measured before the code change. A mocked `GovernedClient`
opener slept 3.6 seconds for each of 18 orderbook requests (9 games x 2
sides); the existing serial `capture_once` measured **101.172 seconds** and
returned 18 rows. The premise holds.

`BASE_RPS = 15.0`; `depth_capture` share = `0.10`; ceiling =
`15.0 * 0.10 = 1.5 requests/sec`; floor = `18 / 1.5 = 12.0 seconds`.
The fixed floor is below the unchanged 15-second bar. No rate limit, governor
share, or 429 behavior was changed.

## Change and construct result

`capture_once` now has additive `max_concurrency: int = 4`, backed by the
`MAX_FETCH_CONCURRENCY` module constant (`ponytail:` comment names 8 as the
later upgrade). Discovery remains single-threaded. Ordered `executor.map`
keeps fetch output in input-index order; `max_concurrency=1` produces the same
output bytes as four workers. Every worker calls the existing `client.get`,
therefore the same `depth_capture` governor instance still executes
`before_request` and `report_429`; a client lock serializes access to that one
bucket without creating another rate path. A failed fetch produces an additive
`record_type="fetch_error"` row rather than disappearing from the pass.

The construct enumerates all 18 per-ticker requests (n = 18, CONSTRUCT): its
0.2-second mocked opener verified wall time less than half the serial wall,
in-flight work never above four, exactly 18 `before_request` calls for the
parallel pass, 429 reporting with cadence doubled to 10 seconds, and
byte-identical serial/parallel output.

## Test output

```text
python -m pytest tests/platformkit/ingame/test_mlb_book_capture_governor.py -q
.                                                                        [100%]
1 passed in 6.24s

python -m pytest scripts/platformkit/ingame/test_mlb_book_capture.py -q
........                                                                 [100%]
8 passed in 2.00s
```

The requested `tests/platformkit/ingame/test_mlb_book_capture.py` path is not
present in this worktree. Its actual tracked counterpart above was run; no
broader test command was run.

## Acceptance rail and pod reproduction

Metric: capture-pass wall seconds, denominator one full pass at 9 games x 2
sides. The unchanged pod acceptance rail is median and p90 at or below 15
seconds over n = 30 pod passes; 5 seconds is not promised. Eye check = n/a
(S-row); reproduction = parse the 30 `record_type="cadence"` rows and
recompute median and p90 from `tick_latency_sec`.

After verifier acceptance and deployment, run this on the pod to write exactly
30 pass records (the unique log is intentionally under `/tmp`):

```bash
CV_CAPTURE_POD=1 CV_MLB_BOOK_ARCHIVE_LIVE=1 python -c 'from pathlib import Path; from scripts.platformkit.ingame.mlb_book_capture import run_pod_capture; ticks = {"n": 0}; stop = lambda: ticks["n"] >= 30 if ticks["n"] >= 30 else (ticks.__setitem__("n", ticks["n"] + 1) or False); run_pod_capture(stop=stop, output=Path("/tmp/cx_s19_request_governor_30.jsonl"))'
python -c 'import json, statistics; p="/tmp/cx_s19_request_governor_30.jsonl"; x=[json.loads(s)["tick_latency_sec"] for s in open(p) if json.loads(s).get("record_type")=="cadence"]; print({"n":len(x),"median":statistics.median(x),"p90":sorted(x)[max(0, (len(x)*90+99)//100-1)]})'
```

Would deploy: `scripts/platformkit/ingame/mlb_book_capture.py`. No file was
deployed, copied to a pod, or otherwise applied outside this worktree.

## Contract self-check

- B1: all 18 requests are represented; failed fetches have named error rows.
- B2: existing successful snapshot fields and order are unchanged; only an additive error record exists.
- B3: an absent fetch becomes a row, not a quarantine or drop.
- B4: no claim/reclaim path changed.
- B5: no pre-verification deployment occurred.
- B6: no module moved or retired; the existing regression test passed.
- B7: n/a; this S-row has no render sample.
- B8: no fitted or scored residual is claimed.
- B9: denominator is one full 9-game, 18-request capture pass.
- B10: governor constants, shares, 429 semantics, evaluation gates, ledger, and protected data paths were not changed.
- Q1: no scored comparison is claimed; the pod score is pending.
- Q2: no trial ledger was charged and no `_charge_ledger` call was made.
- Q3: the 15-second/n=30 rail is copied unchanged.
- Q4: no OOS model evaluation or meta-learner is involved.
- Q5: no AHEAD result is claimed.
- Q6: this memo uses calibration/measurement language only; it makes no financial claim.
- Q7: the mocked test is exhaustive construct n=18; the sampled pod rail remains n=30.
- Q8: the serial premise was re-measured before implementation.

## NOT VERIFIED

30 pod passes not yet run.
