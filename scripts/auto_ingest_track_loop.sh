#!/bin/bash
# auto_ingest_track_loop.sh - Continuously fetch new games and spawn tracking.
#
# Watches /workspace/nba-ai-system/data/ingest/tmp/ for completed downloads,
# moves them to /root/nba_videos/ with .mp4 extension, and spawns a tracking
# worker for each via run_phase_g.py (parallel=1 per spawn — multiple loops
# of this script give parallelism).
#
# Self-throttling: refuses to start a new tracker if N tracking workers
# already running or disk < 5G or load > 50.
#
# Patches applied on top of recovered original (2026-05-26):
#   Patch 1 — attempt-count gate prevents infinite spawn of hash-deduped games
#   Patch 2 — watchdog liveness check at top of every iteration
#   Patch 3 — STUCK marker for mid-pipeline games stalled > 24h
#   Patch 4 — cleanup_videos.sh integration (per-game + periodic sweep)

set -u
cd /workspace/nba-ai-system

MAX_TRACKERS=${MAX_TRACKERS:-5}
MIN_DISK_G=${MIN_DISK_G:-5}
MAX_LOAD=${MAX_LOAD:-500}
TMP_DIR=/workspace/nba-ai-system/data/ingest/tmp
VIDEO_DIR=/root/nba_videos
PENDING_DIR=/workspace/nba_videos_pending
MIN_PROMOTE_DISK_G=${MIN_PROMOTE_DISK_G:-8}
LOG=/workspace/auto_ingest_loop.log

# Patch 1: directories for attempt-count gate
ATTEMPT_DIR=/workspace/nba-ai-system/data/ingest/.attempt_counts
BLACKLIST=/workspace/nba-ai-system/data/ingest/.permanently_blacklisted.txt
mkdir -p "$ATTEMPT_DIR"
touch "$BLACKLIST"

# Patch 4: track loop iterations for periodic sweep
CLEANUP_SCRIPT=/workspace/nba-ai-system/scripts/bot_guards/cleanup_videos.sh

ts() { date "+%H:%M:%S"; }
log() { echo "[$(ts)] $*" >> "$LOG"; }

# ---------------------------------------------------------------------------
# Patch 2: watchdog liveness helper
# Checks budget_watchdog.pid and sync_watchdog.pid; writes warnings to
# /tmp/auto_ingest_status.txt if either PID is dead.  Cannot auto-restart
# because the source scripts (budget_watchdog.sh / local_sync_watchdog.sh)
# are local-machine scripts that SSH in — they cannot be relaunched from
# inside the pod.
# ---------------------------------------------------------------------------
_check_watchdogs() {
  local status_file=/tmp/auto_ingest_status.txt
  for pair in \
    "budget_watchdog:/workspace/nba-ai-system/.budget_watchdog.pid" \
    "sync_watchdog:/workspace/nba-ai-system/.sync_watchdog.pid"
  do
    local name="${pair%%:*}"
    local pidfile="${pair##*:}"
    if [ -f "$pidfile" ]; then
      local pid
      pid=$(cat "$pidfile" 2>/dev/null | tr -dc '0-9')
      if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
        echo "[$(date '+%Y-%m-%dT%H:%M:%S')] WARN: $name (PID $pid) is dead — restart from operator machine" \
          >> "$status_file"
        log "WARN $name PID $pid dead — see $status_file"
      fi
    fi
  done
}

# ---------------------------------------------------------------------------
# Patch 1: attempt-count helpers
# _get_attempts <gid>   — returns current attempt count (0 if no file)
# _inc_attempts <gid>   — increments and echoes new count
# _reset_attempts <gid> — removes counter (called on successful completion)
# _is_blacklisted <gid> — returns 0 (true) if gid is in the blacklist
# ---------------------------------------------------------------------------
_get_attempts() {
  local gid="$1"
  local f="$ATTEMPT_DIR/$gid"
  [ -f "$f" ] && cat "$f" || echo 0
}

_inc_attempts() {
  local gid="$1"
  local f="$ATTEMPT_DIR/$gid"
  local n
  n=$(_get_attempts "$gid")
  n=$((n + 1))
  mkdir -p "$ATTEMPT_DIR"
  echo "$n" > "$f"
  echo "$n"
}

_reset_attempts() {
  local gid="$1"
  rm -f "$ATTEMPT_DIR/$gid"
}

_is_blacklisted() {
  local gid="$1"
  grep -qxF "$gid" "$BLACKLIST" 2>/dev/null
}

log "==== loop start ===="
while true; do

  # -------------------------------------------------------------------------
  # Patch 2: watchdog liveness check — runs at top of every iteration
  # -------------------------------------------------------------------------
  _check_watchdogs

  # 0. Promote one pending video from /workspace to /root if there is room.
  # Pending dir holds videos that were fetched but couldn't fit on /root
  # (50G overlay). When a worker completes AND disk has room, pull one in.
  mkdir -p "$PENDING_DIR"
  n_active=$(pgrep -fac 'run_clip.py --video' || echo 0)
  free_g=$(df --output=avail -BG / | tail -1 | tr -dc '0-9')
  if [ "$n_active" -lt "$MAX_TRACKERS" ] && [ "$free_g" -ge "$MIN_PROMOTE_DISK_G" ]; then
    promoted=0
    for vid in "$PENDING_DIR"/*.mp4; do
      [ -f "$vid" ] || continue
      name=$(basename "$vid")
      # Skip if already in /root (rare race)
      [ -e "$VIDEO_DIR/$name" ] && rm -f "$vid" && continue
      sz_g=$(du -BG --apparent-size "$vid" 2>/dev/null | awk '{print $1}' | tr -dc '0-9')
      sz_g=${sz_g:-5}
      # Need enough free space for the file + a safety margin
      if [ $((free_g - sz_g)) -lt "$MIN_DISK_G" ]; then
        break
      fi
      mv "$vid" "$VIDEO_DIR/$name"
      log "PROMOTED pending: $name (size=${sz_g}G, free_after=$((free_g - sz_g))G)"
      promoted=1
      break  # one per cycle
    done
  fi

  # 1. Move any completed downloads (no extension or .part finalised) to VIDEO_DIR
  for f in "$TMP_DIR"/*; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    # Skip if has extension already
    case "$name" in *.*) continue ;; esac
    # Skip if file still growing (size changed in last 5s)
    s1=$(stat -c%s "$f" 2>/dev/null || echo 0)
    sleep 5
    s2=$(stat -c%s "$f" 2>/dev/null || echo 0)
    if [ "$s1" != "$s2" ] || [ "$s2" -lt 100000000 ]; then
      continue  # still downloading or too small
    fi
    # Verify it's a valid mp4
    dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null | head -1)
    if [ -z "$dur" ]; then
      log "INVALID mp4: $name — skipping"
      continue
    fi
    # Move + rename
    # 2026-05-24: route to PENDING_DIR when /root is constrained.
    # /root is a 50G overlay; the 5 active workers' videos alone can occupy
    # 15-20G. Don't push an incoming video that would tip us over.
    sz_b=$(stat -c%s "$f" 2>/dev/null || echo 0)
    sz_g=$(( (sz_b + 1073741823) / 1073741824 ))  # ceil to GiB
    free_g=$(df --output=avail -BG / | tail -1 | tr -dc '0-9')
    fits_on_root=$(( free_g - sz_g >= MIN_DISK_G ))
    if [ "$fits_on_root" = "1" ]; then
      target="$VIDEO_DIR/${name}.mp4"
    else
      target="$PENDING_DIR/${name}.mp4"
      log "ROOT_FULL: routing $name to pending (size=${sz_g}G free=${free_g}G need=${MIN_DISK_G}G)"
      mkdir -p "$PENDING_DIR"
    fi
    if [ -e "$target" ]; then
      log "ALREADY HAVE: $name — removing tmp copy"
      rm -f "$f"
      continue
    fi
    # Also check if it's already in the OTHER location
    other="$VIDEO_DIR/${name}.mp4"
    [ "$target" = "$other" ] || other="$PENDING_DIR/${name}.mp4"
    if [ -e "$other" ] && [ "$other" != "$target" ]; then
      log "ALREADY HAVE elsewhere: $other — removing tmp copy"
      rm -f "$f"
      continue
    fi
    mv "$f" "$target"
    log "MOVED: $name -> $target ($(stat -c%s "$target") bytes, ${dur}s)"
  done

  # 2. Find unprocessed games (have .mp4 but no tracking_data.csv)
  for vid in "$VIDEO_DIR"/*.mp4; do
    [ -f "$vid" ] || continue
    gid=$(basename "$vid" .mp4)
    track_csv="/workspace/nba-ai-system/data/tracking/$gid/tracking_data.csv"
    run_log="/workspace/nba-ai-system/data/tracking/$gid/run.log"

    # -----------------------------------------------------------------------
    # Patch 1: blacklist gate — skip permanently-blacklisted games
    # -----------------------------------------------------------------------
    if _is_blacklisted "$gid"; then
      continue
    fi

    if [ -s "$track_csv" ]; then
      # Check if this game has enough rows to be considered successfully complete
      rows=$(awk 'NR>1{c++} END{print c+0}' "$track_csv" 2>/dev/null || echo 0)
      if [ "$rows" -ge 5000 ]; then
        # Reset attempt counter on successful completion
        _reset_attempts "$gid"
        # Patch 4: trigger per-game cleanup after confirmed success (50K+ rows)
        if [ "$rows" -ge 50000 ] && [ -x "$CLEANUP_SCRIPT" ]; then
          log "Cleanup: $gid has ${rows} rows — triggering per-game video cleanup"
          bash "$CLEANUP_SCRIPT" --game "$gid" >> "$LOG" 2>&1
        fi
        continue  # already processed
      fi
      # tracking_data.csv exists but tiny — fall through to re-spawn logic
    fi

    # -----------------------------------------------------------------------
    # Patch 3: STUCK marker — detect mid-pipeline games stalled > 24h
    # run.log > 1KB, mtime > 24h, no tracking_data.csv (or < 5000 rows)
    # -----------------------------------------------------------------------
    stuck_marker="/workspace/nba-ai-system/data/tracking/$gid/STUCK"
    if [ -f "$stuck_marker" ]; then
      continue  # already marked stuck; skip forever until operator clears
    fi
    if [ -f "$run_log" ]; then
      log_sz=$(stat -c%s "$run_log" 2>/dev/null || echo 0)
      log_age=$(( $(date +%s) - $(stat -c%Y "$run_log" 2>/dev/null || date +%s) ))
      csv_rows=0
      [ -f "$track_csv" ] && csv_rows=$(awk 'NR>1{c++} END{print c+0}' "$track_csv" 2>/dev/null || echo 0)
      if [ "$log_sz" -gt 1024 ] && [ "$log_age" -gt 86400 ] && [ "$csv_rows" -lt 5000 ]; then
        mkdir -p "/workspace/nba-ai-system/data/tracking/$gid"
        touch "$stuck_marker"
        log "STUCK marker written for $gid (run.log=${log_sz}B age=${log_age}s csv_rows=${csv_rows})"
        continue
      fi
    fi

    # Skip if a prior attempt left a run.log with a terminal state
    # (preflight failure, completion, or any output > a small probe)
    if [ -s "$run_log" ]; then
      # Look for definitive done markers
      if grep -qE 'PREFLIGHT FAIL|Output Summary|Total time:' "$run_log" 2>/dev/null; then
        continue
      fi
      # CUDA OOM is TRANSIENT — archive the log so we retry, but throttle
      # (1 retry per 6h) so a game that repeatedly OOMs doesn't spin.
      if grep -q 'CUDA out of memory\|CUDA error: out of memory\|torch.AcceleratorError: CUDA' "$run_log" 2>/dev/null; then
        retry_marker="/workspace/nba-ai-system/data/tracking/$gid/.oom_retried_at"
        last_retry=0
        [ -f "$retry_marker" ] && last_retry=$(stat -c%Y "$retry_marker" 2>/dev/null || echo 0)
        now=$(date +%s)
        if [ $((now - last_retry)) -gt 21600 ]; then
          log "OOM retry: archiving run.log for $gid (last_retry=${last_retry})"
          mv "$run_log" "${run_log}.oom_$(date +%H%M%S)" 2>/dev/null
          touch "$retry_marker"
          # fall through to spawn block below
        else
          continue
        fi
      else
        # If log is large (>1KB) but no done marker, it likely crashed mid-run —
        # don't keep retrying. Will fail same way.
        sz=$(stat -c%s "$run_log" 2>/dev/null || echo 0)
        if [ "$sz" -gt 1024 ]; then
          continue
        fi
      fi
    fi
    # Already being processed?
    if pgrep -f "run_clip.py.*$gid" > /dev/null; then
      continue
    fi

    # -----------------------------------------------------------------------
    # Patch 1: attempt-count gate — prevent infinite spawn of hash-deduped
    # or otherwise non-progressing games.
    # -----------------------------------------------------------------------
    attempts=$(_get_attempts "$gid")
    if [ "$attempts" -ge 5 ]; then
      # Permanently blacklist after 5 failed attempts
      if ! _is_blacklisted "$gid"; then
        echo "$gid" >> "$BLACKLIST"
        log "BLACKLISTED $gid after $attempts attempts (no tracking output)"
      fi
      continue
    fi
    if [ "$attempts" -ge 3 ]; then
      log "SKIP $gid — attempt count $attempts >= 3 (max before blacklist is 5)"
      continue
    fi

    # Throttle checks
    n_track=$(ps -eo args 2>/dev/null | awk '/^\/usr\/bin\/python3.*run_clip\.py --video/' | wc -l)
    if [ "$n_track" -ge "$MAX_TRACKERS" ]; then
      log "Throttled: $n_track trackers >= $MAX_TRACKERS; skipping $gid"
      break  # don't try to spawn more this iteration
    fi
    disk_g=$(df -BG /root | awk 'NR==2 {print $4}' | sed 's/G//')
    if [ "$disk_g" -lt "$MIN_DISK_G" ]; then
      log "Throttled: disk ${disk_g}G < ${MIN_DISK_G}G; skipping $gid"
      break
    fi
    load=$(awk '{print int($1)}' /proc/loadavg)
    if [ "$load" -gt "$MAX_LOAD" ]; then
      log "Throttled: load $load > $MAX_LOAD; skipping $gid"
      break
    fi

    # Increment attempt counter before spawn
    new_attempts=$(_inc_attempts "$gid")
    log "Attempt $new_attempts for $gid"

    # Spawn tracker for this game (parallel=1, in background)
    log "SPAWN tracker: $gid (workers=$n_track disk=${disk_g}G load=$load)"
    nohup setsid env \
      OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 NUMEXPR_NUM_THREADS=4 \
      TORCH_NUM_THREADS=4 VECLIB_MAXIMUM_THREADS=4 \
      PHASE_G_GAME_TIMEOUT=21600 FULL_GAME=1 RSS_KILL_GB=40 \
      PHASE_G_VIDEO_DIR=/root/nba_videos PHASE_G_STAGGER_S=15 \
      CUDA_MPS_PIPE_DIRECTORY=/tmp/nvidia-mps ENRICHMENT_TIMEOUT_S=600 \
      python3 scripts/run_phase_g.py --reprocess --game-ids "$gid" \
        --full --parallel 1 \
      > /workspace/track_${gid}.log 2>&1 < /dev/null &
    sleep 10  # let it grab GPU before next spawn
  done

  # 3. If queue has fewer than N queued, kick off a fetch
  n_tmp=$(ls "$TMP_DIR" 2>/dev/null | wc -l)
  if [ "$n_tmp" -lt 2 ] && ! pgrep -f "ingest_fetch.py" > /dev/null; then
    disk_g=$(df -BG /root | awk 'NR==2 {print $4}' | sed 's/G//')
    if [ "$disk_g" -ge 8 ]; then
      log "Spawning ingest_fetch (tmp=$n_tmp, disk=${disk_g}G)"
      nohup setsid python3 scripts/ingest_fetch.py --count 4 --parallel 2 \
        > /workspace/ab_autofetch_$(date +%H%M).log 2>&1 < /dev/null &
    fi
  fi

  # 4. Periodic re-extract PBP context + audit (every ~10 loops)
  loop_n=$((${loop_n:-0} + 1))
  if [ $((loop_n % 10)) -eq 0 ]; then
    log "Re-extracting PBP context + audit (loop $loop_n)"
    python3 scripts/extract_pbp_shot_context.py > /workspace/auto_extract_$(date +%H%M).log 2>&1
    python3 scripts/fix_team_abbrev_postscript.py --all >> /workspace/auto_extract_$(date +%H%M).log 2>&1
    python3 scripts/audit_completed.py 2>&1 | tail -5 >> "$LOG"
  fi

  # -------------------------------------------------------------------------
  # Patch 4: periodic disk cleanup sweep every 30 loop iterations (~30 min)
  # -------------------------------------------------------------------------
  if [ $((loop_n % 30)) -eq 0 ] && [ -x "$CLEANUP_SCRIPT" ]; then
    log "Periodic cleanup sweep (loop $loop_n)"
    bash "$CLEANUP_SCRIPT" --sweep >> "$LOG" 2>&1
  fi

  sleep 60
done
