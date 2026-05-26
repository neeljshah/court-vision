# Fresh-Pod Bootstrap Guide — R16

Single-command flow to spin up a brand-new RunPod pod that runs the tracker pipeline EXACTLY like the prior pod. Designed to take <30 minutes cold start.

## TL;DR

```bash
# On laptop, from nba-ai-system/ directory:
bash scripts/runpod_bootstrap.sh <NEW_POD_IP> <NEW_POD_SSH_PORT>
```

That single command does everything below.

## What it does (step by step)

| Step | What | Source | Where it ends up on pod |
|------|------|--------|-------------------------|
| 1 | Verify GPU + Python | n/a | `nvidia-smi -L`, `python3 --version` |
| 2 | rsync source code | laptop `./` | `/workspace/nba-ai-system/` (+ mirror to `/workspace/pred-system/`) |
| 3 | Push critical artefacts | laptop `data/models/`, `data/nba/`, `resources/`, `models/weights/` | `/workspace/nba-ai-system/{data/models,data/nba,resources}/`, `/workspace/nba-ai-system/models/weights/` |
| 4 | Push `.env` | laptop `.env` (must exist) | `/workspace/nba-ai-system/.env` |
| 5 | Install Python deps (PINNED R16) | `requirements.txt` + cu128 torch wheels | system pip (`--break-system-packages`) |
| 6 | Smoke-test imports | n/a | runs `python3 -c "import torch, ultralytics, ..."` |
| 7 | rclone-sync videos from B2 | `b2:${B2_BUCKET}/full_games/` | `/root/nba_videos/` |
| 8 | Build TRT engines for this GPU | `scripts/build_trt_engines.sh` | `resources/*.engine` |

## Prerequisites

1. **A laptop with the project repo** (with `data/models/`, `data/nba/`, `resources/` populated — these are pushed to the pod).
2. **A `.env` file on the laptop** with all secrets (copy `.env.example`, fill in NBA_API_KEY, CLAUDE_API_KEY, THE_ODDS_API_KEY, KALSHI_*, POLY_*, B2_*, DATABASE_URL).
3. **B2 bucket configured + populated** (one-time setup, see below).
4. **rclone installed on the pod** — the bootstrap auto-installs via apt; if not, run `curl https://rclone.org/install.sh | bash`.

## One-time B2 setup (do this BEFORE you ever stop the pod)

You need a Backblaze B2 bucket holding the artefacts that CAN'T be re-downloaded from anywhere else. These are:

| Artefact | Size | Why critical |
|----------|------|--------------|
| `data/models/` | 48 MB | 111 trained ML models from cycles 26-106d — weeks of work, no other source |
| `data/nba/` | 126 MB | NBA Stats API cache (boxscores, rosters) — re-fetchable but slow (rate-limited) |
| `data/cache/` | 77 MB | Bankroll state, predictions parquet — operational state |
| `resources/` | small | Court anchor PNGs, RectifyL/R/1.npy, osnet_x025.onnx — custom CV artefacts |
| `/root/nba_videos/*.mp4` | 23 GB | Game video archive — only source is your laptop or YouTube re-fetch |

### Setup steps

1. Create B2 bucket: https://secure.backblaze.com/b2_buckets.htm  (e.g. `courtvision-prod-backup`)
2. Generate application key with read+write to that bucket
3. Configure rclone: `rclone config` → create remote named `b2`
4. Add `B2_BUCKET=courtvision-prod-backup` to your `.env`
5. **One-time backup of everything currently on the pod:**
   ```bash
   ssh -p <PORT> root@<IP> "cd /workspace/nba-ai-system && bash scripts/runpod_backup_to_b2.sh"
   ```

## Backing up before stopping a pod

```bash
ssh -p <PORT> root@<IP> "cd /workspace/nba-ai-system && bash scripts/runpod_backup_to_b2.sh"
```

This uploads:
- `data/models/` (rclone sync — only changed files)
- `data/nba/` (rclone sync)
- `data/cache/` (rclone sync)
- `resources/` (rclone sync)
- `/root/nba_videos/*.mp4` from last 30 days (rclone copy)

Takes ~5-15 min for the 23 GB video tier; <1 min for the rest.

## What still needs your laptop

The bootstrap PUSHES from your laptop. If your laptop dies too, B2 is the only source. Recommendation:

1. Keep `.env` in 1Password (it's 1 KB).
2. Schedule weekly B2 backups during model-training cycles.
3. Mirror the git repo to GitHub (already done — `origin/master`).

## Verifying the fresh pod actually works

After bootstrap completes:

```bash
# 1. Test suite passes
ssh -p <PORT> root@<IP> "cd /workspace/pred-system && python3 -m pytest -q tests/test_tracker.py tests/test_shot_log_features.py"

# 2. Run a 300-frame smoke clip
ssh -p <PORT> root@<IP> "cd /workspace/nba-ai-system && \
  python3 scripts/run_clip.py --video /root/nba_videos/$(ls /root/nba_videos/ | head -1) \
  --no-show --data-dir /tmp/smoke --skip-features --game-id smoke --max-frames 300"

# 3. Check output has the R8-R18 columns
ssh -p <PORT> root@<IP> "head -1 /tmp/smoke/tracking_data.csv | tr ',' '\n' | grep -E 'team_abbrev|contest_arm_angle|fast_break_flag|homography_valid|live'"
```

All 3 should succeed. If any fails, the bootstrap left something out — file a ticket and re-run with `-x` (verbose) to see where it broke.

## What R16 explicitly does NOT solve

- **First-time B2 bucket setup** is manual (one rclone configure + one initial backup).
- **Video re-fetch from YouTube** if B2 ever goes down — `scripts/fetch_games.py` exists but is not invoked from bootstrap.
- **Database state** — `DATABASE_URL=postgresql://localhost/nba_ai` requires a live Postgres on the new pod (or external DB). If you depend on Postgres, add a separate `pg_dump`/`pg_restore` step before/after pod stop.

## Risk assessment

| Failure mode | Probability | Mitigation |
|--------------|------|------------|
| Laptop dies AND B2 down | Low | Both must fail. Run backup quarterly to a second remote. |
| `.env` keys rotated (NBA, Claude, etc.) | Medium | Keep .env in 1Password; bootstrap pushes fresh on each run. |
| New CUDA on RunPod base image breaks pinned torch wheel | Medium | Update `requirements.txt` torch line + re-test. |
| ONNX runtime version mismatch (osnet_x025.onnx) | Low | Pinned in requirements.txt. |
| YouTube blocks fetch_games.py | Already happened (Android player workaround) | Keep B2 as primary video source. |
