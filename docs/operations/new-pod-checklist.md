# New-pod day-1 checklist (100-game push)

Goal: bring a fresh RunPod online and start processing 100 games without
babysitting. Steps in order.

---

## Before the pod is up

### A. Refresh YouTube cookies (CRITICAL — 5 min, do this first)

The cookies in `data/videos/youtube_cookies.txt` expire every ~2 weeks.
Without fresh cookies yt-dlp gets blocked at "How to pass cookies to yt-dlp"
and every download fails fast.

1. Open Chrome → log in to youtube.com (use the account you normally use)
2. Install browser extension "Get cookies.txt LOCALLY" if not already
3. On any youtube.com page, click the extension → Export → Netscape format
4. Save to `C:\Users\neelj\nba-ai-system\data\videos\youtube_cookies.txt`
5. Confirm file size > 5 KB (a real cookie set is 30-100 KB)

### B. Pick fresh game IDs (3 min)

Sequential old game IDs (like 0022500281-0022500284) are DMCA-expired or
auth-locked. Best targets:

- **Last 30 days** of the current season (2025-26): IDs starting `0022501100+`
- **Playoff games**: stay on YouTube longer than regular season
- Games you already have on the previous pod (`/root/nba_videos/*.mp4`): can
  be re-used; just rsync the .mp4 files to the new pod

Verify each candidate has a YouTube broadcast before adding to games.txt:
```
ssh ... python3 scripts/fetch_games.py --full --game-id 0022501xxx --out-dir /tmp/test
```
Look for "Found full game:" — that means yt-dlp located it. If "No YouTube
full game found", skip the ID.

---

## When the new pod is provisioned

You'll have: a new IP, a new SSH port, and an empty `/workspace/`.

### 1. Sync the code (~2 min)

From your **LOCAL machine**:

```bash
NEW_IP=<new-pod-ip>
NEW_PORT=<new-pod-port>

# Sync everything except videos and tracking outputs
rsync -av -e "ssh -p $NEW_PORT -o StrictHostKeyChecking=no" \
    --exclude='data/videos/full_games/*.mp4' \
    --exclude='data/tracking/*' \
    --exclude='*.pyc' --exclude='__pycache__' \
    --exclude='.git/' \
    C:/Users/neelj/nba-ai-system/ \
    root@$NEW_IP:/workspace/nba-ai-system/
```

(On Windows, use git-bash for rsync, or scp -r as a fallback.)

### 2. Bootstrap the pod (~5 min)

```bash
ssh -p $NEW_PORT root@$NEW_IP "cd /workspace/nba-ai-system && bash scripts/bootstrap_new_pod.sh"
```

Expected output:
- Python 3.12 detected
- GPU detected (3090 / 4090 / A100)
- All deps installed
- Models load
- Cookie file present (if you ran step A)

If TRT engines fail to load (different GPU than old pod), that's OK — Ultralytics
falls back to the .pt file. First few frames are slower but it works.

### 3. Verify connectivity from local (~30 sec)

```bash
# PowerShell or Git Bash on Windows
$env:NBA_POD_IP="<new-pod-ip>"
$env:NBA_POD_PORT="<new-pod-port>"
python scripts/ingest_pulse.py
```

Expected: pod_alive=True, disk free > 30 GB, GPU detected, no pipelines running.

### 4. Kick off the 100-game batch

Three options based on how confident you want to be:

#### Option A — single-game smoke first (recommended, ~75 min for confidence)

```bash
NBA_POD_IP=<ip> NBA_POD_PORT=<port> \
    python scripts/ingest_one_game.py 0022501XXX
```

Wait for the row to appear in `nba-data-backup\.ingest_log.csv`. If OK, move
on to the batch.

#### Option B — orchestrator batch with resume

```bash
NBA_POD_IP=<ip> NBA_POD_PORT=<port> \
    python scripts/ingest_one_game.py --batch games.txt --resume
```

`--resume` skips any game already marked OK in the log. Safe to re-run after
a crash. Each game is sequential and takes ~90 min on a 3090.

#### Option C — multi-worker parallel (faster, more risk)

The canonical 100-game push command per the original runbook:

```bash
ssh -p $NEW_PORT root@$NEW_IP "cd /workspace/nba-ai-system && \
    FULL_GAME=1 OMP_PER_WORKER=12 RSS_KILL_GB=40 \
    bash scripts/launch_multigpu.sh 2"
```

Use 2 workers per 3090, 4-6 per 4090/A100. Doesn't use the orchestrator —
runs directly on the pod and writes to `data/tracking/<game_id>/`. You'll
need to manually sync to local afterward via:

```bash
python scripts/sync_tracking_to_laptop.py
```

### 5. Monitoring (whenever)

From your local machine, anytime during the run:

```bash
python scripts/ingest_pulse.py
```

Shows: pod alive, disk, GPU, running pipelines with frame progress, recent
log entries, suspect small files. Safe to run repeatedly.

---

## When games complete

Each completed game gets auto-validated by the orchestrator:
- `.quality.json` (validate_ingest.py): file presence + key metrics
- `.diagnostic.json` (diagnose_tracking_quality.py): per-signal A-F grades

After the batch:

```bash
# Roll up grades across the whole run
python scripts/diagnose_tracking_quality.py --from-log

# Apply homography fix to every new game (per-game empirical calibration)
python scripts/fix_homography_offset.py --all

# Recompute paint pressure with corrected coords
python scripts/recompute_paint_pressure.py --all

# Build the CV profile parquet (the actual modeling input)
python scripts/build_player_cv_profiles.py --all
```

Output: `data/player_cv_per_game.parquet` + `data/player_cv_per_player.parquet`
ready for `prop_pergame_walk_forward` consumption.

---

## What to do if things fail

| Symptom | Cause | Fix |
|---|---|---|
| SSH ConnectTimeout | Pod IP/port wrong | Check pod status; update `NBA_POD_IP`/`NBA_POD_PORT` |
| "video download failed" 8s | Cookies expired | Refresh `data/videos/youtube_cookies.txt` (step A above) |
| "video download failed" 13s | DMCA expired | Pick a newer game (last 30 days) |
| Pipeline timeout 14400s | Huge game OR feature engineering slow | Bump `--pipeline-timeout 18000`; investigate |
| OOM on pod | GPU memory pressure | Drop to 1 worker; check `nvidia-smi` |
| pose_state never populated | Pose model load failed | Verify `resources/yolov8n-pose.engine` exists; falls back to .pt |
| `disk /root` filling up | Old videos not cleaned | `ssh ... rm /root/nba_videos/<old-game>.mp4` |

---

## Estimated cost

At 90 min/game × 100 games × $0.34/hr (RTX 3090 RunPod pricing as of May 2026):
- Sequential: ~150 hours of pod time = ~$50
- 2-worker parallel: ~75 hours = ~$25
- 6-worker parallel: ~25 hours = ~$8.50

Plus storage. Total $10-50 for the 100-game push.

---

## Definition of done

- [ ] 100 games processed, all marked OK in `.ingest_log.csv`
- [ ] Local backup has all 8 files per game, non-empty row counts
- [ ] `python scripts/diagnose_tracking_quality.py --from-log` shows ≥80 games at B+
- [ ] `data/player_cv_per_game.parquet` has ≥1,500 player-game rows
- [ ] `python scripts/prop_pergame_walk_forward.py` against `cvb_*` columns produces a result file
