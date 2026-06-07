# Backfill 100s of NBA Games on Any RunPod — R20 Playbook

End-to-end guide to process hundreds of full NBA games through the R8-R19 tracker on any fresh RunPod, using `scripts/run_backfill.py`.

## Speed math (per RunPod tier)

These are realistic full-game wall-clock numbers at **stride=5** (R20 default) on the R8-R19 pipeline. Stride=5 is ~35% faster than stride=3 with modest accuracy loss (acceptable for backfill / training).

| GPU model | Per-game time | 100 games on 1 GPU | 100 games on 4 GPUs |
|-----------|---------------|--------------------|--------------------|
| RTX 4090 (24 GB) | ~2.0 hr | ~200 hr / 8.3 days | **~50 hr / 2.1 days** |
| RTX 3090 (24 GB) | ~2.4 hr | ~240 hr / 10 days | ~60 hr / 2.5 days |
| A100 (40 GB) | ~1.7 hr | ~170 hr / 7 days | ~43 hr / 1.8 days |
| H100 (80 GB) | ~1.2 hr | ~120 hr / 5 days | ~30 hr / 1.25 days |

**Recommendation for 100-300 game backfills:** 4× RTX 4090 pod, stride=5, full-game mode. ~50 hours wall-clock for 100 games.

## Setup (one-time, ~30 min)

1. **Fresh pod boot** — follow `docs/operations/fresh-pod-bootstrap.md`:
   ```bash
   bash scripts/runpod_bootstrap.sh <NEW_IP> <NEW_PORT>
   ```
   This pushes code, models, resources, .env, installs pinned deps, builds TRT engines.

2. **Verify the pipeline imports + GPUs visible:**
   ```bash
   ssh -p <PORT> root@<IP> "python3 -c 'import torch; print(torch.cuda.device_count(), \"GPUs\")'"
   ```

3. **Pull videos** — three options:
   - **B2 sync (preferred):** `ssh <pod> "cd /workspace/nba-ai-system && source .env && rclone copy b2:\$B2_BUCKET/full_games/ /root/nba_videos/"`
   - **YouTube fetch:** `python3 scripts/fetch_games.py --season 2025-26` (slow, rate-limited)
   - **scp from laptop:** `scp -P <PORT> /local/videos/*.mp4 root@<IP>:/root/nba_videos/`

## Run the backfill

1. **Create a manifest** — list of game IDs to process. Two formats supported:

   **txt** (one per line, comments OK):
   ```
   # data/games_to_backfill.txt
   0022500045
   0022500047
   0022500048
   # commented-out games are skipped
   ```

   **json** (list of strings or list of dicts with `game_id`):
   ```json
   [{"game_id": "0022500045"}, {"game_id": "0022500047"}]
   ```

2. **Launch the backfill:**
   ```bash
   ssh -p <PORT> root@<IP> "cd /workspace/nba-ai-system && \
     nohup python3 scripts/run_backfill.py \
       --manifest data/games_to_backfill.txt \
       --full \
       --stride 5 \
       --delete-video-on-success \
       > /tmp/backfill.log 2>&1 & echo PID:\$!"
   ```

   This:
   - Auto-detects all GPUs and launches one worker per GPU
   - Skips games already processed (resumable)
   - Processes each game with stride=5 (the recommended backfill setting)
   - Deletes the source `.mp4` after each successful game (saves disk)
   - Logs every game to `data/backfill_log.csv`
   - Per-game console output: `[N/M] game_id GPUx ok 124.5m rows=235K shots=183 poss=187 (✓42 ✗3 eta=180m)`

3. **Monitor progress:**
   ```bash
   ssh -p <PORT> root@<IP> "python3 /workspace/nba-ai-system/scripts/backfill_status.py --watch"
   ```

   Or tail the master log: `ssh <pod> "tail -f /tmp/backfill.log"`.

## Resumability

The backfill is **fully resumable**:
- Each completed game is recorded in `data/backfill_log.csv`.
- A game is "done" if `tracking_data.csv` exists with ≥ 10K rows.
- Re-running the same command **skips done games** and continues with the rest.
- Pod restart? Just re-run the same `nohup` command — picks up where it left off.

To **force re-process** specific games, delete their output dirs first:
```bash
ssh <pod> "rm -rf /workspace/nba-ai-system/data/tracking/0022500045_R19"
```

Or `--reset` to re-process EVERYTHING in the manifest.

## Disk-pressure management

- Without `--delete-video-on-success`: pod accumulates videos AND tracking outputs.
  - 100 games × 250 MB video = ~25 GB videos + ~30 GB outputs = ~55 GB.
- With `--delete-video-on-success` (recommended): pod only retains outputs.
  - 100 games × ~300 MB output = ~30 GB total.

For very large backfills (300+ games), also enable B2 mirroring of outputs:
```bash
# After backfill completes, push everything to B2:
ssh <pod> "cd /workspace/nba-ai-system && bash scripts/runpod_backup_to_b2.sh"
```

## Failure modes + recovery

| Status code | Meaning | Recovery |
|-------------|---------|----------|
| `ok` | Tracking completed successfully | None — done |
| `fail` | Pipeline returned non-zero exit code | Re-run; inspect `data/tracking/<game>_R19/run.log` |
| `crash` | Worker raised an exception | Re-run; check Python traceback in run.log |
| `timeout` | Exceeded 4-hour per-game wall-clock | Use shorter stride or split video, then re-run |
| `no_video` | Video not found in `/root/nba_videos/` | Fetch the video first, then re-run |

The backfill **does NOT crash** if a single game fails — it logs the failure and moves on. After completion, re-run with the same manifest to retry failed games (they'll be picked up because `already_done()` returns False).

## Output schema (per-game directory under `data/tracking/<game_id>_R19/`)

```
tracking_data.csv       (~230K rows, 65 cols)  — per-frame per-player
shot_log.csv            (~170 rows, 28 cols)   — per-shot with R8/R11/R13 enrichment
shot_log_enriched.csv   identical to shot_log.csv (legacy duplicate)
possessions.csv         (~200 rows, 22 cols)   — per-possession with R17/R18 strict definitions
possessions_enriched.csv identical to possessions.csv
events_log.csv          (~varies)              — screen/cut/drive/closeout/post_up/steal/block/rebound (R19)
ball_tracking.csv       (~50K rows)            — per-frame ball position + R12 live/dead-ball gate
scoreboard_log.csv      (~3000 rows)           — R8 lifted from ~1/695 frames to ~1/30
player_clip_stats.csv   (10 rows, one per slot)
jersey_name_map.json    — R9+R14 nested-by-team format
run.log                 — full stdout/stderr of this game's pipeline run
```

## Quality validation after first batch

Run this on the first ~5 games to confirm the R8-R19 fixes are working as expected:

```bash
ssh <pod> "cd /workspace/nba-ai-system/data/tracking && python3 -c '
import pandas as pd, os, glob
for game_dir in sorted(glob.glob(\"*_R19\"))[:5]:
    s = pd.read_csv(f\"{game_dir}/shot_log.csv\")
    print(f\"{game_dir}: shots={len(s)} made_null={s[\\\"made\\\"].isna().mean()*100:.1f}% \"
          f\"player_unknown={(s[\\\"player_name\\\"].str.contains(\\\"#?\\\", na=False) | s[\\\"player_name\\\"].isna()).mean()*100:.1f}% \"
          f\"shot_creation_buckets={s[\\\"shot_creation\\\"].nunique()}\")
'"
```

Expected targets (per game):
- `shots`: 150-180 (R11 + R13)
- `made_null`: < 15% (R8 PBP ±8s fallback)
- `player_unknown`: < 15% (R9 + R14 jersey OCR)
- `shot_creation_buckets`: ≥ 5 (was 1 pre-R8, now ~7-9 buckets: catch_and_shoot/pull_up/PnR/drive/iso/transition/post_up/floater/other)

If any of these are off across multiple games → file an issue + investigate before continuing the full 100-game wave.

## Cost estimate (RunPod 2026 pricing, ballpark)

| Pod | $/hr | 100 games / 50 hr | 300 games / 150 hr |
|-----|------|-------------------|--------------------|
| 4× RTX 4090 | $1.99 | $100 | $300 |
| 4× RTX 3090 | $1.20 | $60 | $180 |
| 4× A100 40G | $4.40 | $220 | $660 |

Add ~$2-5 for B2 storage of the output archive (per 100 games).
