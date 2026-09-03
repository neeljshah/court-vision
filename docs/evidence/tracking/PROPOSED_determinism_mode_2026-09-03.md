# PROPOSED (human-gated, NOT applied): a determinism mode for measurement runs

**This touches `src/pipeline/unified_pipeline.py`, which is human-gated. No edit
has been made.** This is the diff for a human to apply, with the reasoning and
the cost stated so the trade is yours to make.

## The problem this addresses

G189 measured the `run_clip.py` route producing **1,104 / 1,246 / 1,247 / 1,360 /
1,549 player rows across five identical runs** on one file with one command -- a
40 pct spread. Three quality rows had already been landed on that route before
anyone checked whether it repeats.

## Three named causes, all confirmed by reading the code

1. **`src/pipeline/unified_pipeline.py:657` sets `torch.backends.cudnn.benchmark = True`.**
   Its own comment says this "finds optimal convolution algorithms ... yielding
   ~10-15% throughput gain". The auto-tuner picks algorithms by TIMING them at
   runtime, so a differently-loaded box can select a different algorithm and
   produce different numerics. **This is probably the dominant cause, ahead of
   FP16**, because it varies per process rather than per operation.
2. **FP16 throughout** -- `half=use_half` at `unified_pipeline.py:919` and
   `:1024`, and `advanced_tracker.py:284, 344, 435, 444, 1218, 1227`. Half
   precision reductions are not bit-reproducible across algorithm choices.
3. **No seeding anywhere.** `grep` for `manual_seed`, `np.random.seed` and
   `random.seed` across `unified_pipeline.py`, `advanced_tracker.py` and
   `run_clip.py` returns nothing.

G189's evidence fits all three: three fresh raw-detector invocations on one frame
each returned exactly 15 boxes, but with coordinates and confidences differing in
low digits (`594.750` vs `594.000`; `0.24365` vs `0.24438`). Those differences
then cross the `conf=0.22` threshold and the stateful tracker amplifies one
flipped detection across the rest of the clip.

## The proposed change: a MODE, not an unconditional edit

**Do not simply set `benchmark = False`.** The comment's 10-15 pct throughput
claim is a real production cost and the pod is already throughput-constrained.
Reproducibility is needed for MEASUREMENT runs, not for bulk processing. So this
gates on an environment variable, default OFF, preserving current production
behaviour exactly.

Proposed, at `src/pipeline/unified_pipeline.py:654-659`, replacing the existing
try block:

```python
        # Enable cuDNN auto-tuner - finds optimal convolution algorithms for the
        # fixed input sizes used by YOLO and OSNet, yielding ~10-15% throughput gain.
        # CV_DETERMINISTIC=1 turns the tuner OFF and pins seeds instead: the tuner
        # selects algorithms by runtime timing, so a differently-loaded box can pick
        # a different algorithm and change the numerics. G189 measured a 40 pct
        # spread in emitted rows across five identical runs of this route.
        try:
            import torch
            _deterministic = os.environ.get("CV_DETERMINISTIC") == "1"
            torch.backends.cudnn.benchmark = not _deterministic
            if _deterministic:
                import random as _random
                import numpy as _np
                torch.backends.cudnn.deterministic = True
                torch.manual_seed(0)
                _np.random.seed(0)
                _random.seed(0)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(0)
        except Exception:
            pass
```

`half` is deliberately NOT forced off here. Seeding plus a fixed algorithm may be
sufficient; if a repeat test still varies, the next step is FP32 for measurement
runs, which is a larger change and should be justified by a measurement rather
than assumed.

## How to verify it worked, and the honest bar

Apply, then run the G189 protocol: the same clip, same `--frames 1200`, three
times with `CV_DETERMINISTIC=1`, and compare `tracking_data.csv` row counts and
the frame-474 survivor tuples.

- **Three identical results** -> determinism mode works; quality rows may then
  cite single runs taken in that mode, and only in that mode.
- **Still varying** -> the cause is elsewhere (FP16, or non-determinism in the
  tracker itself) and that is a finding, not a failure. Report it; do not start
  disabling things until it happens to agree.

**Do not tune anything to force agreement.** The value of this mode is that it
either holds or tells us something true.

## What this does NOT fix

Nothing about tracking quality. Determinism makes measurement trustworthy; it
does not make a single row pass a gate. 0 of 40 pod ledger rows pass and this
change moves that number by zero, by design.
