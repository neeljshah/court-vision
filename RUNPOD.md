# RunPod Phase G Runbook

3-command workflow on any fresh single-4090 pod. Assumes videos already on pod (or upload separately).

## 0. Configure connection

Edit `.runpod` with new pod IP/PORT from RunPod UI → Connect → SSH, then:
```
source .runpod
```

## 1. Bootstrap (once per fresh pod)
```
bash scripts/bootstrap_pod.sh
```
What it does:
- rsyncs code to `/workspace/nba-ai-system`
- installs decord + torch + ultralytics + deps
- creates `/root/nba_videos` and symlinks `data/videos/full_games` → there (mfs is 38× slower)
- quarantines AV1-encoded videos (decoder can't handle them)
- verifies `_VRAM_FLUSH_INTERVAL = 3000`
- prints CPU quota

If videos aren't on the pod yet, upload them into `/root/nba_videos` first:
```
rsync -az -e "ssh -p $RUNPOD_PORT" data/videos/full_games/ root@$RUNPOD_IP:/root/nba_videos/
```

## 2. Launch
```
bash scripts/launch_single_gpu_pod.sh
```
Runs `run_phase_g.py --parallel 4 --frames 18000` with `OMP/MKL/OPENBLAS/NUMEXPR=6`. This is the documented optimum — parallel-4 + OMP cap fits the 17.85-core CFS quota, gets ~80 fps aggregate.

## 3. Sync results back (IMPORTANT — pod disk is ephemeral)
In a separate terminal, leave this running:
```
source .runpod && bash scripts/sync_tracking_results.sh
```
Auto-pulls each game dir as it completes. Also run once at the end:
```
rsync -az -e "ssh -p $RUNPOD_PORT" root@$RUNPOD_IP:/workspace/nba-ai-system/data/tracking/ data/tracking/
scp -P $RUNPOD_PORT root@$RUNPOD_IP:/workspace/nba-ai-system/data/phase_g_processed.txt data/
scp -P $RUNPOD_PORT root@$RUNPOD_IP:/workspace/nba-ai-system/data/phase_g_metrics.csv data/
```
**Stopping the pod without syncing = lost work.**

## Health check (run ~2 min after launch)
```
ssh -p $RUNPOD_PORT root@$RUNPOD_IP 'cat /proc/loadavg; pgrep -f run_clip.py | wc -l'
```
Expect: load < 20, 4 workers. If throttle delta > 50/60s, the OMP cap didn't propagate — re-launch.

## Troubleshooting
- **0 workers after launch** → check `/workspace/nba-ai-system/phase_g_p4.log` for stack traces
- **Throttling > 50%** → drop to `--parallel 3` (edit launcher)
- **AV1 decode errors** → re-run step 4 of bootstrap, a new video slipped through
- **`decord` not found** → rerun bootstrap (first time setup didn't complete)

## See also
- `CLAUDE.md` → "RunPod single-4090 runbook" section for full background
- `scripts/bootstrap_pod.sh` — bootstrap source
- `scripts/launch_single_gpu_pod.sh` — launch source
