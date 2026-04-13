# Fix Memory Leak in NBA CV Pipeline — RunPod 3090

## SSH Connection
```
ssh root@213.192.2.72 -p 40037
```
Pod: RTX 3090 24GB, 116GB RAM cgroup, 27.2 CPU cores.

## The Problem
The tracking pipeline leaks ~1.5 GB/sec of **native (C/C++) memory** that Python/tracemalloc cannot see. PyAV alone is clean (72 MB flat over 1500 frames). YOLO alone is clean (1235 MB flat over 500 frames). But the full pipeline (`run_clip.py` → `UnifiedPipeline.run()`) goes 2 GB → 20 GB → 47 GB → 69 GB → 93 GB → 117 GB → OOM killed in ~90 seconds.

The pipeline's own `[MEM gc]` log reports RSS stable at 2.6 GB because it reads `resource.getrusage().ru_maxrss` which on Linux reports **peak** RSS, not current. The actual RSS from `/proc/PID/status` shows the massive leak.

## What's Been Ruled Out
- **decord**: Disabled (`DECORD_ENABLE=0` by default). Not loaded.
- **PyAV decode**: Tested in isolation — 72 MB flat over 1500 frames. No leak.
- **YOLO inference**: Tested in isolation with predictor cache clearing — 1235 MB flat over 500 frames. No leak.
- **LoFTR/kornia GPU homography**: Disabled via `COURTV_NO_LOFTR=1`.
- **SIFT**: Only runs every 300 frames. Leak is ~1.5 GB/sec so it's per-frame.

## Prime Suspects (investigate in this order)

### 1. EasyOCR reader (scoreboard OCR)
`ScoreboardOCR.read(frame)` runs on every gameplay frame (line 1465 of unified_pipeline.py). EasyOCR's `Reader.readtext()` is known to leak in its CRAFT text detection network — it keeps intermediate tensors and doesn't release them. It creates new numpy arrays internally via OpenCV that land in glibc arenas.

Check: `src/pipeline/unified_pipeline.py` — find `ScoreboardOCR` class, check how the easyocr Reader is used. If `reader.readtext()` is called per frame (even with an interval), the internal CRAFT detector may fragment memory.

**Fix approach**: Either (a) move OCR to a subprocess that gets killed/restarted every N frames, or (b) add `del` + `gc.collect()` after each readtext call, or (c) reduce OCR frequency dramatically (every 90 frames instead of every frame).

### 2. OpenCV imencode/warpPerspective temp buffers
`_get_homography()` and `_is_gameplay()` may create temporary OpenCV buffers (resize, cvtColor, warpPerspective) that fragment the glibc arena. With `MALLOC_ARENA_MAX=2`, these should return to OS via `malloc_trim`, but if they're allocated inside OpenCV's C++ side they may use a different allocator.

### 3. Ultralytics YOLO — hidden caches beyond predictor.results
Even though we clear `predictor.results` and `predictor.batch`, Ultralytics 8.4.37 may cache `orig_img` in other places (e.g., `model.predictor.plotted_img`, `model.predictor.data`). Check `model.predictor.__dict__` for any large numpy arrays after each call.

### 4. The `_FramePrefetcher` thread queue
`bgr.copy()` on line 259 creates a copy for every frame. The queue is maxsize=8, but if the consumer is slow and the producer keeps yielding, the generator itself may buffer frames in Python's generator stack. Check if `_pyav_frame_iter` has yielded frames that haven't been consumed yet.

### 5. kornia GPU tensors in color_reid / rectify_court
Even with `torch.no_grad()` and `del`, PyTorch's CUDA caching allocator holds memory. `torch.cuda.empty_cache()` only runs every 3000 frames. But this would show as VRAM growth, not RSS.

## How to Diagnose

Run this on the pod to identify the exact leaking function:

```bash
cd /workspace/nba-ai-system
MALLOC_ARENA_MAX=2 MALLOC_MMAP_THRESHOLD_=65536 OMP_NUM_THREADS=4 CUDA_VISIBLE_DEVICES=0 COURTV_NO_LOFTR=1 python3 -c "
import os, psutil, time, sys
sys.path.insert(0, '.')
proc = psutil.Process(os.getpid())

# Import pipeline
from src.pipeline.unified_pipeline import UnifiedPipeline

# Monkey-patch key functions to measure RSS delta
_orig_is_gameplay = UnifiedPipeline._is_gameplay
_orig_get_homography = UnifiedPipeline._get_homography

def _wrap_is_gameplay(self, frame, frame_idx):
    r0 = proc.memory_info().rss
    result = _orig_is_gameplay(self, frame, frame_idx)
    r1 = proc.memory_info().rss
    delta = (r1 - r0) / 1024 / 1024
    if abs(delta) > 5:
        print(f'[LEAK] _is_gameplay f={frame_idx} delta={delta:.0f}MB')
    return result

def _wrap_get_homography(self, frame):
    r0 = proc.memory_info().rss
    result = _orig_get_homography(self, frame)
    r1 = proc.memory_info().rss
    delta = (r1 - r0) / 1024 / 1024
    if abs(delta) > 5:
        print(f'[LEAK] _get_homography delta={delta:.0f}MB')
    return result

UnifiedPipeline._is_gameplay = _wrap_is_gameplay
UnifiedPipeline._get_homography = _wrap_get_homography

pipe = UnifiedPipeline(
    video_path='data/videos/full_games/0022400690.mp4',
    max_frames=200,
    show=False,
    data_dir='/tmp/leak_diag',
    game_id='0022400690',
)
print(f'After init: RSS={proc.memory_info().rss/1024/1024:.0f}MB')
pipe.run()
print(f'After run: RSS={proc.memory_info().rss/1024/1024:.0f}MB')
" 2>&1 | grep -E 'LEAK|After|RSS'
```

Also try disabling scoreboard OCR entirely to isolate:
```python
# In unified_pipeline.py, at line ~1465, comment out:
# sb_state = self.scoreboard_ocr.read(frame)
# and set sb_state = None
```

If RSS stabilizes with OCR disabled, the fix is to run OCR less frequently or in a subprocess.

## Key Files
- `src/pipeline/unified_pipeline.py` — main loop (line 1439+), scoreboard OCR (1465), homography (1561), player tracking (1586), ball detection (1618), GC (1770)
- `src/tracking/advanced_tracker.py` — YOLO + OSNet + player tracking
- `src/tracking/color_reid.py` — GPU HSV batch conversion
- `scripts/run_clip.py` — subprocess wrapper that calls UnifiedPipeline
- `scripts/run_phase_g.py` — batch orchestrator

## Current State on Pod
- Code deployed and import verified
- 12 of 99 videos uploaded (upload may have died — restart with `scp`)
- `phase_g_processed.txt` has 16 entries (mostly RC3 failures from junk test videos)
- Pipeline is NOT running (killed for investigation)
- A watchdog script may be lingering — check with `pgrep -af 'while true'`

## Upload Videos (still needed)
```bash
# From local Windows machine:
scp -o StrictHostKeyChecking=no -P 40037 data/videos/full_games/*.mp4 root@213.192.2.72:/workspace/nba-ai-system/data/videos/full_games/
```
Or use the remaining list approach — check what's on pod, diff, upload the rest.

## After Fixing the Leak
```bash
cd /workspace/nba-ai-system
> data/phase_g_processed.txt

MALLOC_ARENA_MAX=2 \
MALLOC_MMAP_THRESHOLD_=65536 \
OMP_NUM_THREADS=4 \
MKL_NUM_THREADS=4 \
OPENBLAS_NUM_THREADS=4 \
NUMEXPR_NUM_THREADS=4 \
CUDA_VISIBLE_DEVICES=0 \
COURTV_NO_LOFTR=1 \
nohup python3 scripts/run_phase_g.py --frames 18000 --parallel 1 > phase_g_batch.log 2>&1 & disown
```

Verify RSS stays under 5 GB for 1000+ frames before scaling to --parallel 2 or 4.

## Data Sync (CRITICAL — pod disk is ephemeral)
```bash
rsync -az -e "ssh -p 40037" root@213.192.2.72:/workspace/nba-ai-system/data/tracking/ data/tracking/
scp -P 40037 root@213.192.2.72:/workspace/nba-ai-system/data/phase_g_processed.txt data/
scp -P 40037 root@213.192.2.72:/workspace/nba-ai-system/data/phase_g_metrics.csv data/
```

## Rules
- _VRAM_FLUSH_INTERVAL must stay 3000
- Do NOT enable decord
- Do NOT use TensorRT
- Do NOT modify SIFT interval (300), OCR stride (30), or stride (3) without quality testing
- No cv2.imshow — headless only
- Max 300 LOC/file
