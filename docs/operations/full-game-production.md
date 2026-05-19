# Full-Game Production Config

*One-command full-game processing on RunPod. Updated 2026-05-18.*

---

## Quick Start

```bash
# On pod after setup_pod_optimized.sh:
FULL_GAME=1 bash scripts/launch_multigpu.sh 1
```

That's it. No other config needed.

---

## What Changed (vs 18K-frame clips)

| Setting | Clip mode (18K) | Full-game mode |
|---------|----------------|----------------|
| Frame cap | 18,000 | None (entire video) |
| Per-game timeout | 60 min | 3 hours |
| RSS kill threshold | 25GB emergency cleanup | 40GB hard abort (env: `RSS_KILL_GB`) |
| Checkpoint interval | 2000 frames | 2000 frames (same) |
| Periodic flush | tracking, ball, scoreboard, events | + shot_log (was unflushed) |
| Emergency cleanup | Clear predictions only | Flush all buffers + gc + malloc_trim |

## Memory Safety

The pipeline now has three tiers of memory defense:

1. **Periodic flush** (every 2000 gameplay frames): tracking_rows, ball_rows, scoreboard, events, shot_log all flushed to CSV and cleared.
2. **Emergency cleanup** (RSS > 25GB): flush ALL buffers, force gc.collect + malloc_trim.
3. **Hard abort** (RSS > RSS_KILL_GB, default 40GB): flush remaining data, break out of processing loop. Partial game data is preserved.

External watchdog (`scripts/worker_memory_watchdog.sh`) kills workers exceeding 50GB RSS.

## Estimated Performance

Based on measured 18K-frame runs (80 games, RTX 3090):

| Metric | Clip (18K) | Full game (est.) |
|--------|-----------|------------------|
| Gameplay frames | ~6,000 | ~30-50K |
| Wall time | 5-10 min | 60-150 min |
| Peak RSS | 2-3 GB steady, 20-30 GB peak | 3-5 GB steady, 25-40 GB peak |
| VRAM | 894 MB | 894 MB (constant) |
| Output CSV size | ~5 MB | ~30-70 MB |

*Non-gameplay frames (halftime, commercials, replays) are auto-detected and skipped via scoreboard OCR and vision-based detection, so actual processed frames are less than total video frames.*

## Cost Estimates

### Per-Game Cost
| GPU | $/hr | Wall time/game | Cost/game |
|-----|------|---------------|-----------|
| RTX 4090 | $0.34 | ~2h | $0.68 |
| RTX 3090 | $0.40 | ~2.5h | $1.00 |
| A40 (48GB) | $0.44 | ~2h | $0.88 |

### Season Costs (1230 games)
| Config | Wall time | Total cost |
|--------|-----------|------------|
| 1× RTX 4090, parallel=1 | ~2460 hrs (103 days) | ~$836 |
| 4× RTX 4090 pod, 1 per GPU | ~615 hrs (26 days) | ~$836 |
| 4× A40 pod, 1 per GPU | ~615 hrs (26 days) | ~$1085 |

### Recommended: Process 200-game subset
For model training, 200 diverse games is sufficient (covers all teams, home/away, spread across season):
| Config | Wall time | Total cost |
|--------|-----------|------------|
| 4× RTX 4090, 1 per GPU | ~100 hrs (4 days) | ~$136 |

## Recommended Pod Configuration

**Pod type:** 4× RTX 4090 (community cloud)
**Parallel per GPU:** 1 (no sharing — full-game runs hold GPU for 2+ hours)
**RAM:** 125GB+ pod RAM
**Disk:** 200GB+ (full-game tracking CSVs are larger)
**Estimated cost:** $0.34/hr × 4 GPUs = $1.36/hr total

```bash
# Optimized launch command:
FULL_GAME=1 RSS_KILL_GB=30 bash scripts/launch_multigpu.sh 1
```

## Games That May Fail

Videos longer than 140 minutes (pregame + game + postgame in one file) may exceed RSS limits even with all memory defenses. These will be gracefully aborted and logged in `phase_g_failed.txt`.

From the 80-game test run, 0022500066.mp4 (126 min) was quarantined at 112GB RSS. With the new flush+abort system, it will process what it can and save partial results rather than OOM-killing the entire pod.

## Monitoring

```bash
# Watch all GPU workers
tail -f phase_g_batch_gpu*.log

# Check RSS per worker
ps aux --sort=-rss | head -5

# Watch for MEM EMERGENCY or MEM FATAL lines
grep -h '\[MEM' phase_g_batch_gpu*.log | tail -20

# Progress
wc -l data/phase_g_processed.txt
cat data/phase_g_metrics.csv | tail -5
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FULL_GAME` | 0 | Set to 1 for full-game processing |
| `FRAMES` | 18000 | Per-game frame cap (ignored if FULL_GAME=1) |
| `RSS_KILL_GB` | 40 | Hard RSS abort threshold per worker (GB) |
| `PHASE_G_GAME_TIMEOUT` | 10800 | Per-game timeout in seconds (3 hours) |
| `PHASE_G_STAGGER_S` | 60 | Seconds between worker starts |
| `DECORD_ENABLE` | 0 | Set to 1 to use decord GPU decode (leaks — keep at 0) |
