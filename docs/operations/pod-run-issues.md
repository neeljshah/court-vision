# Pod Run — Issues Log & Bulletproofing

*Live log of every failure hit during RunPod CV processing runs, with root cause,
fix, and the permanent prevention. Read this before launching a pod run.*

> Origin: 2026-05-22 RTX 3090 run. ~9 hours of run time were lost to the issues
> below before the pipeline became stable. Every entry has a prevention so the
> next run does not repeat it.

---

## Pre-launch checklist (do all of these)

1. **Strip CRLF** from every shell script after syncing code to the pod:
   `find scripts -name '*.sh' -exec sed -i 's/\r$//' {} +`
2. **Codec-scan every video** before processing — quarantine non-h264:
   `ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 X.mp4`
3. **Install TensorRT explicitly**: `pip install --break-system-packages tensorrt-cu12==10.16.1.11`
   (it is NOT in `setup_pod_optimized.sh`'s pip line — see issue #4).
4. **Verify TRT after launch**: `grep -c 'for TensorRT inference' phase_g_batch_gpu0.log`
   should be `3 × n_workers`. If 0 → CPU fallback, 4× slow.
5. **Confirm VRAM flush interval is 3000**: `grep _VRAM_FLUSH_INTERVAL src/pipeline/unified_pipeline.py`
6. Launch the processor only through `supervisor.sh` (singleton-guarded).

---

## Issues

### #1 — CRLF line endings broke shell scripts
- **Symptom:** `setup_pod_optimized.sh` aborted at step 4. `build_trt_engines.sh: line 13: set: pipefail: invalid option name`, `$'\r': command not found`.
- **Root cause:** scripts synced from Windows carry CRLF line endings; `set -euo pipefail\r` is invalid.
- **Fix:** `sed -i 's/\r$//'` on all `scripts/*.sh` on the pod.
- **Prevention:** strip CRLF immediately after every code sync (checklist #1). Better: add `*.sh text eol=lf` to `.gitattributes`.

### #2 — AV1 videos hang the pipeline
- **Symptom:** parallel runs collapsed to ~4 fps; workers stuck in `do_wait`; GPU at 0%.
- **Root cause:** 5 of the synced videos were AV1-encoded. AV1 software-decode saturates CPU; it does not hard-fail, it just crawls — and starves every other worker. 5 of the first 6 sorted videos were AV1, so every early parallel run was poisoned.
- **Fix:** `ffprobe` codec-scan all videos; quarantine non-h264.
- **Prevention:** the downloader requests `vcodec^=avc` (h264) and ffprobe-rejects anything else. Always codec-scan before processing (checklist #2).

### #3 — Pod restart wiped /root
- **Symptom:** SSH port changed (40022→40045); `/root/nba_videos` empty, pip deps gone (`ModuleNotFoundError: ultralytics`).
- **Root cause:** RunPod's container overlay (`/`, `/root`) is ephemeral — wiped on stop/restart. Only the `/workspace` network volume persists.
- **Fix:** re-upload videos, reinstall deps.
- **Prevention:** keep code + TRT engines + tracking output on `/workspace` (they survive). Treat `/root` as scratch. A restart needs a manual rebuild — see recovery runbook below.

### #4 — TensorRT missing after a deps reinstall (4× slowdown)
- **Symptom:** processing at 16 fps instead of 60; no `for TensorRT inference` in the log.
- **Root cause:** `setup_pod_optimized.sh`'s pip line does NOT include tensorrt. On the first setup it gets installed only as a side-effect of `build_trt_engines.sh` (ultralytics AutoUpdate). A standalone deps reinstall therefore omits it → YOLO runs unaccelerated.
- **Fix:** `pip install --break-system-packages tensorrt-cu12==10.16.1.11` (must match the version the `.engine` files were built with).
- **Prevention:** checklist #3 + #4. TODO: add `tensorrt-cu12` to `setup_pod_optimized.sh`.

### #5 — `pkill -f` self-match killed the SSH session
- **Symptom:** `pkill -KILL -f run_clip.py` killed the controlling shell; SSH dropped (exit 255).
- **Root cause:** `pkill -f` matches the whole command line — including the shell running the `pkill` command, whose argv contains the literal string `run_clip.py`.
- **Prevention:** never `pkill -f <str>` when `<str>` appears in the kill command. Kill by PID, filtering `comm=="python3"` (the real worker) so the bash shell can't match. Same trap with `pgrep -c` / `grep -c` — counts self-inflate; filter on `comm` or exact argv.

### #6 — Per-game timeout kill cascaded and killed the whole run
- **Symptom:** one game hit the 3-h timeout; run_phase_g, the 2 other in-flight games, AND the supervisor all died at once.
- **Root cause:** `run_phase_g.py` timeout does `os.killpg(os.getpgid(child.pid), SIGKILL)`. The `run_clip` subprocess was not in its own session, so `getpgid` returned the shared process group and `killpg` SIGKILL'd everything in it.
- **Fix:** added `start_new_session=True` to the `subprocess.Popen` in `run_phase_g.py:_run_clip` — each game is now its own session leader; a timeout kill hits only that game.
- **Prevention:** applied in code. Supervisor is launched with `setsid` (own session) so it can never be caught in a process-group kill.

### #7 — Duplicate supervisor / duplicate processor
- **Symptom:** 2 `supervisor.sh` and 2 `run_phase_g` running; both processing the same video dir → race on `phase_g_processed.txt` and tracking dirs.
- **Root cause:** `supervisor.sh` had no singleton guard; restarting it while an old instance was alive produced duplicates.
- **Fix:** rewrote `supervisor.sh` with a PID-file singleton guard — a second instance detects the live PID and exits.
- **Prevention:** applied. Monitor also alerts if `sup != 1` or `phaseg > 1`.

### #8 — Worker-count parallelism is GPU-contended (not a bug)
- **Finding:** 1 worker = 60 fps, 3 = 88 fps, 6 = 81 fps. One GPU; more processes → context-switch contention → sublinear, then negative.
- **Resolution:** locked at **3 workers**. Short-window fps measurements are noisy — don't over-tune.

### #9 — Games are full broadcasts (200–300K frames)
- **Finding:** uploaded videos are full broadcasts (pre-game, 4 quarters, halftime, post-game) — 200–300K frames, of which only ~90K is gameplay. ~2 h/game at 3-way.
- **Resolution:** the pipeline ALREADY skips non-gameplay efficiently — `_is_gameplay()` with positive/negative caching (~600 YOLO checks saved per halftime) and the main loop `continue`s on non-gameplay (no tracking/OCR). Verified on `0022500045`: 218K source frames → 17.7K gameplay frames heavy-processed (92% skipped) → ~30 min of basketball in ~72 min wall.

### #10 — Ball perspective-division explosion (data corruption)
- **Symptom:** `ball_x2d / ball_y2d` columns in ball_tracking.csv contained values up to 3,300,000 px on some frames (real court coords are < ~3700px). 3 of 4 audited games affected on a fraction of frames.
- **Root cause:** `ball_detect_track.py:905` does `homo = np.int32(homo / homo[-1])`. When M/M1 is near-singular for a frame, `homo[-1]≈0` so the division explodes. The existing guard at line 913 only rejected *negative* coords; huge positives slipped through. The downstream drift guard couldn't catch them either when no players were tracked that frame (which happens — broadcasts often show <3 players).
- **Fix:** bounded the guard at [ball_detect_track.py:914](src/tracking/ball_detect_track.py:914): `if not (0 <= ball_2d[0] < 6000 and 0 <= ball_2d[1] < 6000): last_2d_pos = None`. Catches negatives, huge positives, and inf/nan→INT_MIN from div-by-zero. Garbage frames now correctly register as "ball not detected."
- **Prevention:** applied in repo + pod. Future games are clean. Already-processed games with the bug stay flagged by issue #11's quality gate.

### #11 — Quality gate was broken (homography_valid_pct always 0)
- **Symptom:** No game could ever be tiered CLEAN. The gate required `homography_valid_pct ≥ 70`, but the metric was silently always 0.
- **Root cause:** `src/ingest/quality.py:_load_tracking` computed `homo_valid` from a `homography_valid` column in tracking_data.csv — that column **never existed**. `r.get("homography_valid", "")` returned `""` for every row → homo_pct = 0 for every game.
- **Fix:** replaced with real **coordinate-sanity** computation from ball_tracking.csv — fraction of rows where ball_x2d/y2d are in [-100, 6000] (catches the issue #10 explosions). Tightened threshold to 99.9% (single-frame outliers stay ≥99.99%; real corruption like 0022500047 at 99.79% now fails). Result: gate is functional AND auto-flags issue-#10-style corruption going forward.
- **Verified:** on the 4 audited games — 0022500047 (99.79%) correctly tiered PARTIAL on homography failure; the others stay CLEAN.

### #12 — launch_multigpu.sh under-threads on newer cgroup layouts
- **Symptom:** OMP/MKL set to 4 per worker (low) → throughput ~half of expected.
- **Root cause:** the script reads `/sys/fs/cgroup/cpu.max` (cgroup v2). On some RunPod images that path doesn't exist (only `/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_quota_us` does), and even when it does, the fallback default `print(8)` kicks in → THREADS_PER_WORKER = 8 / N → clamped to 4. OMP_PER_WORKER env var was set but unused.
- **Fix:** [scripts/launch_multigpu.sh:71](scripts/launch_multigpu.sh:71) — `OMP_PER_WORKER` env now overrides the CFS-derived value (`!= ""` and `!= "auto"`). Supervisor.sh defaults to 8 (verified-best). Verified 113 fps on mps-6 OMP=8 vs 104 fps with the old auto path.

### #13 — supervisor.sh hardcoded OMP_PER_WORKER=12
- **Symptom:** even with `env OMP_PER_WORKER=8 bash supervisor.sh`, the run launched at OMP=12.
- **Root cause:** supervisor.sh's launch line literally had `OMP_PER_WORKER=12` set on the launch_multigpu invocation, shadowing the inherited env var.
- **Fix:** [scripts/loops/supervisor.sh:7-8](scripts/loops/supervisor.sh:7) — `OMP_PER_WORKER="${OMP_PER_WORKER:-8}"` and pass it through, so env override works.
- **Prevention:** lesson — never hardcode a value the caller might want to set via env. Default in a `${VAR:-default}` block.

---

## Recovery runbook — pod restarted (/root wiped)

```bash
PORT=<new_ssh_port>
# 1. reinstall deps INCLUDING tensorrt
ssh -p $PORT root@<ip> 'pip install --break-system-packages -q ultralytics decord av \
  easyocr torchreid kornia onnxruntime-gpu paddleocr tensorrt-cu12==10.16.1.11 yt-dlp'
# 2. re-stage videos to /root/nba_videos (TRT engines + code survive on /workspace)
# 3. restart loops: disk_watchdog.sh, supervisor.sh (setsid), downloader.sh
# 4. verify TRT loads (checklist #4)
```
