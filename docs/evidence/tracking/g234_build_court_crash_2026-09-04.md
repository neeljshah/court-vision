# The `_build_court` crash that empties most basketball tracking runs

**Date:** 2026-09-04. **Author:** orchestrator. **Status:** diagnosis from the pod's own daemon ledger
plus code reading in master. **No code, threshold, gate, verdict or pod file was changed.**

## What was measured

`data/tracking/track_daemon_ledger.jsonl` on the pod, 54 entries, filtered to basketball
(`wnba` + `ncaa_basketball`, 13 entries). Every `thin` entry has **exactly 0 rows**.

**The same clip appears in both outcomes, which makes this a controlled comparison rather than a
footage property:**

| game_id | status | rows | decoded_frames | seconds | rung |
|---|---|---:|---|---:|---|
| `wnba_01` | thin | 0 | None | 45 | None |
| `wnba_01` | thin | 0 | None | 30 | None |
| `wnba_01` | thin | 0 | None | 30 | None |
| `wnba_01` | thin | 0 | None | 30 | None |
| `wnba_01` | thin | 0 | None | 30 | None |
| `wnba_01` | **tracked** | **3,377** | **174,430** | **2,552** | `IMAGE_PX_DECLARED` |

`ncaa_basketball_IB-_u4gW3ds` shows the same split: 4 thin at 0 rows, 1 tracked at 271 rows.
`wnba_02` (4,171) and `wnba_03` (4,534) tracked.

**All five failing `wnba_01` runs carry the identical tail:**

```
src/pipeline/unified_pipeline.py", line 1097, in _build_court
    map_2d = cv2.resize(map_img, (_rw, _rh))
cv2.error: OpenCV(5.0.0) /io/opencv/modules/imgproc/src/resize.cpp:4217
```

They die in **30-45 seconds**; the run that worked took **2,552 seconds**. So this is a hard crash at
court construction, long before tracking.

## The code, read in master

`src/pipeline/unified_pipeline.py:1055-1097`:

```python
_pano_ok = pano is not None and isinstance(pano, np.ndarray) and pano.size > 0
if not _pano_ok:
    _rw, _rh = 940, 500                      # guard 1: no pano
else:
    try:
        img = binarize_erode_dilate(pano, plot=False)
        _, corners = rectangularize_court(img, plot=False)
        rectified = rectify(pano, corners, plot=False)
        _rh, _rw = rectified.shape[:2]       # <-- unvalidated
        if _rh > _rw:                        # guard 2: PORTRAIT only
            ...rotate, else _rw, _rh = 940, 500
    except Exception as _e:
        _rw, _rh = 940, 500                  # guard 3: exception
map_2d = cv2.resize(map_img, (_rw, _rh))     # :1097
```

**There are three fallbacks to 940x500 and none of them covers a zero or degenerate dimension.**
If `rectify()` returns an array whose height is 0, then `_rh = 0`, the portrait test `0 > _rw` is
**False**, no fallback fires, and `cv2.resize(map_img, (_rw, 0))` raises exactly the error above.
`resize.cpp` rejects a destination whose area is not positive.

## Why this plausibly hits basketball specifically

`rectify()` is fed corners from `rectangularize_court`. **Basketball court corner detection is measured
at 0 of 17 frames** (G205, G208, G210b, G214, G227 -- G227 abstained on 17/17), so a degenerate
rectification result is exactly what a failed corner detection would be expected to produce. Sports
whose adapters do not take this path show **zero** thin results in 32 jobs (baseball 24, football 4,
soccer 4). **This is a coherent link, not a demonstrated one:** nobody has logged `rectified.shape` on a
failing run.

## Proposed fix -- HUMAN-GATED, NOT APPLIED

`src/` is human-gated, so this is a proposal only. It matches the shape of the three fallbacks the
function already has, adding no new behaviour and no new constant:

```python
        _rh, _rw = rectified.shape[:2]
        if _rw <= 0 or _rh <= 0:
            _log_mod.getLogger(__name__).warning(
                "_build_court: rectified has a degenerate shape (%dx%d) — forcing 940x500 map",
                _rw, _rh,
            )
            _rw, _rh = 940, 500
        elif _rh > _rw:
            ...existing portrait handling unchanged...
```

**Expected effect:** the run proceeds on the 940x500 default instead of dying, which is what the other
two failure paths already do. **What it does NOT do:** it does not improve calibration, and the run
would still declare `image_px` and still fail `coordinate_contract`. **It converts a silent 30-second
crash into a completed run**, which is the difference between 0 rows and something scorable.

**A second, independent improvement worth considering separately:** these runs **exit 0**. The daemon
only notices via its own `MIN_TRACKING_ROWS = 500` "thin" label, whose comment already says such a run
is *"a failed detection pass wearing a successful exit code"*. A crash in `_build_court` should not
present as success.

## NOT VERIFIED

- `rectified.shape` on any failing run. The zero-dimension path is inferred from the guard structure and
  the exception text, **not observed**.
- Whether the four successful basketball runs took a different branch, or simply got a usable pano.
- Whether `ncaa_basketball_IB-_u4gW3ds`'s four failures carry the same tail; only `wnba_01`'s five were
  read in full.
- Whether G211b's zero-row run shares this cause. **It reported 400 collector calls, so it reached the
  frame loop, which this crash would preclude — so they may be different failures and must not be
  merged without evidence.**
- OpenCV 5.0.0 is an unusual major version; no check was made of whether an older OpenCV tolerated this
  input.

---

## Addendum 2026-09-04: the resize behaviour is now tested, not asserted

The memo above claimed that `cv2.resize` "rejects a destination whose area is not positive". That was
read from the traceback, not tested. It is now tested locally:

```
local cv2 4.11.0
resize (940, 0) -> cv2.error: ... resize.cpp:4211: error: (-215:Assertion failed) ...
resize (0, 500) -> cv2.error: ... resize.cpp:4211: error: (-215:Assertion failed) ...
resize (940, 500) -> OK shape (500, 940, 3)
```

**Either zero dimension raises; a valid pair succeeds.** The local build is OpenCV **4.11.0** raising at
`resize.cpp:4211`, against the pod's **5.0.0** raising at `resize.cpp:4217` — the same assertion, a few
lines apart across major versions. So the failure mode reproduces on a different OpenCV build, and the
error is not specific to the pod's unusual 5.0.0.

**This still does not observe `rectified.shape` on a failing run**, which remains the open link and is
what G235 is specified to measure. What it removes is the weaker of the two assumptions: a zero
dimension definitely produces this exact error, so if the shape does turn out to carry a zero, the chain
is complete.
