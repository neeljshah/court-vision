#!/usr/bin/env bash
# G410 bounded observer replay driver (PC side).
#
# For each queued section: gate on measured free VRAM, place the retained source
# on the pod when it is not already there, run the archived route once under the
# G410 observer hook, fetch the trace and the emitted table, then remove every
# byte this lane wrote.  The deploy tree is never written: its route-file digests
# are recorded before and after each launch.
set -u
POD="ssh -n -o ConnectTimeout=20 -p 40117 root@213.192.2.120"
SCPP="-o ConnectTimeout=20 -P 40117"
HOST="root@213.192.2.120"
QUEUE="$1"
OUT="$2"
MIN_VRAM="${3:-4200}"
SCRATCH=/workspace/g410_scratch
DEPLOY=/workspace/deploy/nba-ai-system
mkdir -p "$OUT/traces" "$OUT/logs"
RECEIPTS="$OUT/launch_receipts.tsv"
: > "$RECEIPTS"
STARVED=0

while IFS=$'\t' read -r KIND SEC LOCAL SHA START FRAMES ORIGSRC <&3; do
  [ -z "${SEC:-}" ] && continue
  if [ -s "$OUT/traces/$SEC.trace.txt" ]; then echo "SKIP $SEC"; continue; fi
  # --- bounded VRAM gate: at most 40 polls of 30 s (20 min) per section -------
  FREE=0
  for i in $(seq 1 20); do
    FREE=$($POD 'nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits' 2>/dev/null | tr -d ' \r')
    case "$FREE" in ''|*[!0-9]*) FREE=0;; esac
    [ "$FREE" -ge "$MIN_VRAM" ] && break
    sleep 30
  done
  if [ "$FREE" -lt "$MIN_VRAM" ]; then
    printf '%s\t%s\tVRAM_UNAVAILABLE\t%s\t\t\t\n' "$KIND" "$SEC" "$FREE" >> "$RECEIPTS"
    continue
  fi
  # --- source placement -------------------------------------------------------
  SRC="$ORIGSRC"
  UPLOADED=0
  if ! $POD "test -s $ORIGSRC"; then
    SRC="$SCRATCH/src/$SEC.mp4"
    $POD "mkdir -p $SCRATCH/src $SCRATCH/out $SCRATCH/trace"
    WINPATH=$(printf '%s' "$LOCAL" | sed 's|^\([A-Za-z]\):|/\L\1|')
    scp $SCPP -q "$WINPATH" "$HOST:$SRC" || { printf '%s\t%s\tUPLOAD_FAILED\t%s\t\t\t\n' "$KIND" "$SEC" "$FREE" >> "$RECEIPTS"; continue; }
    PODSHA=$($POD "sha256sum $SRC | cut -d' ' -f1" | tr -d ' \r')
    if [ "$PODSHA" != "$SHA" ]; then
      $POD "rm -f $SRC"
      printf '%s\t%s\tUPLOAD_DIGEST_MISMATCH\t%s\t%s\t\t\n' "$KIND" "$SEC" "$FREE" "$PODSHA" >> "$RECEIPTS"
      continue
    fi
    UPLOADED=1
  fi
  # --- archived-route digests before the launch -------------------------------
  BEFORE=$($POD "cd $DEPLOY && sha256sum src/pipeline/unified_pipeline.py src/tracking/advanced_tracker.py src/tracking/player_detection.py scripts/run_clip.py | sha256sum | cut -d' ' -f1" | tr -d ' \r')
  T0=$(date +%s)
  $POD "mkdir -p $SCRATCH/out $SCRATCH/trace && cd $DEPLOY && \
    PYTHONPATH=$SCRATCH/hook PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 G410_TRACE=$SCRATCH/trace/$SEC.trace.txt \
    /usr/bin/python3 scripts/run_clip.py --video=$SRC --game-id=$SEC --no-show \
    --frames $FRAMES --start-frame $START --data-dir=$SCRATCH/out/$SEC" \
    > "$OUT/logs/$SEC.log.txt" 2>&1
  RC=$?
  T1=$(date +%s)
  AFTER=$($POD "cd $DEPLOY && sha256sum src/pipeline/unified_pipeline.py src/tracking/advanced_tracker.py src/tracking/player_detection.py scripts/run_clip.py | sha256sum | cut -d' ' -f1" | tr -d ' \r')
  scp $SCPP -q "$HOST:$SCRATCH/trace/$SEC.trace.txt" "$OUT/traces/$SEC.trace.txt" 2>/dev/null
  scp $SCPP -q "$HOST:$SCRATCH/out/$SEC/tracking_data.csv" "$OUT/traces/$SEC.tracking_data.csv" 2>/dev/null
  TB=0; [ -s "$OUT/traces/$SEC.trace.txt" ] && TB=$(wc -c < "$OUT/traces/$SEC.trace.txt")
  printf '%s\t%s\tRC%s\t%s\t%s\t%s\t%s\t%s\n' "$KIND" "$SEC" "$RC" "$FREE" "$((T1-T0))" "$TB" "$BEFORE" "$AFTER" >> "$RECEIPTS"
  $POD "rm -rf $SCRATCH/out/$SEC $SCRATCH/trace/$SEC.trace.txt"
  [ "$UPLOADED" = "1" ] && $POD "rm -f $SRC"
  echo "DONE $SEC rc=$RC trace_bytes=$TB secs=$((T1-T0))"
done 3< "$QUEUE"
echo "G410_REPLAY_QUEUE_COMPLETE"
