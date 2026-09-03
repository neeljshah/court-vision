# G181 follow-through: the two "unrecoverable" basketball games were blocked by a missing 51 KB PNG

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md) A2, A7, Q8. Measured and
fixed by the orchestrator, 2026-09-03. **No production code was changed.** The
change is a missing ASSET deployed to the pod; `src/` is human-gated and was not
touched.

## What G181 found, and what it could not say

G181 established that all five retained thin attempts on `wnba_01` and
`ncaa_basketball_IB-_u4gW3ds` die with the identical ledger `tail`:
`_build_court` calls `cv2.resize(map_img, (_rw, _rh))` and OpenCV raises
`(-215:Assertion failed) !ssize.empty()`. It correctly called this "an empty
court-map asset, not a footage limit" and left the cause open.

## The cause, measured

`src/pipeline/unified_pipeline.py:1052` reads the asset:

    map_img = cv2.imread(os.path.join(_RESOURCES, "2d_map.png"))

`cv2.imread` returns `None` for a missing file rather than raising, so the
failure surfaces 45 lines later at the `cv2.resize` call. Counted on both sides:

| | local repo | pod, before |
|---|---:|---:|
| files under `resources/` | **93** | **3** |
| size | 99 MB | 7.9 MB |
| `2d_map.png` present | yes | **no** |

The pod's `resources/` held only `panos`. The gap traces to the orchestrator's
own pod bootstrap: the new box was seeded from a gzipped `git archive` sized down
to 187 MB, and `resources/` did not survive that trim.

## The fix and its verification

Assets were copied to the pod, **excluding every `.engine` file**: those are
TensorRT engines built for the local RTX 4060, and the pod is an RTX 3090 with a
different compute capability, so they cannot load there. `yolov8n.pt`, the
portable weights file, was shipped instead.

Verified on the pod by running the exact call that was failing, not by `ls`:

    imread -> (695, 1241, 3)
    resize ok -> (500, 940, 3)

`cv2.resize(map_img, (940, 500))` now succeeds where it previously raised.

## What is NOT claimed

- **No basketball game has been tracked successfully yet.** This clears one
  specific exception at one specific line. Whether the pipeline then completes,
  and whether its output passes any gate, is unmeasured and is the next row's
  job. Calling this "wnba and ncaa now work" would repeat exactly the over-read
  pattern this program keeps correcting.
- No verdict, bar, gate, denominator or coordinate contract changed. The five
  thin attempts keep their existing ledger rows.
- Whether the other 90 absent `resources/` files matter to any code path was not
  surveyed; only the one the traceback names was diagnosed.

## NOT VERIFIED

- That any downstream stage of `unified_pipeline` succeeds after `_build_court`.
- Whether the remaining absent assets block a different route.
- Whether the same bootstrap trim dropped anything else the pod needs; the file
  COUNT gap of 93 vs 3 was closed only for the eight assets shipped.
