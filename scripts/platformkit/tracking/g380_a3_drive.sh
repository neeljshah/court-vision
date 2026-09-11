#!/bin/bash
# G380 fix 1c / amendment A3, PC side: attempt-level receipt-versus-trace over the
# 30 replay objects G386 retained locally.  One object at a time -- send, verify its
# sha256 on the pod, run the patched arm alone under the hook, delete the copy --
# so the pod volume never carries more than one source.  EVERY section in
# a3_sources.csv stays in the denominator: a send or run failure is logged by name.
set -u
POD="root@213.192.2.120"
PORT=40117
OBJ="C:/Users/neelj/nba-ai-system/data/pod_backup_2026-09-10/g386_objects"
EV="C:/Users/neelj/nba-track-a19/docs/evidence/tracking/g380_producer_provenance_2026-09-10"
# -n matters: without it ssh eats the loop's stdin and the loop ends after one row.
SSH="ssh -n -o ConnectTimeout=20 -o ServerAliveInterval=30 -p $PORT $POD"
CSV="/workspace/wt/a19/docs/evidence/tracking/g380_producer_provenance_2026-09-10/receipts_trace_a3.csv"
DONE=$($SSH "cut -d, -f1 $CSV 2>/dev/null" | tr -d '\r')

while IFS=, read -r NAME SHA BYTES GID VIDEO; do
  [ -z "$NAME" ] && continue
  if echo "$DONE" | grep -qx "$GID"; then
    echo "=== SKIP $GID -- already measured"
    continue
  fi
  echo "=== $(date -u +%H:%M:%SZ) SEND $NAME"
  if ! scp -o ConnectTimeout=20 -P $PORT "$OBJ/$NAME" \
        "$POD:/workspace/g380_scratch/sources/$NAME"; then
    echo "SEND_FAILED $NAME -- retrying once"
    sleep 30
    if ! scp -o ConnectTimeout=20 -P $PORT "$OBJ/$NAME" \
          "$POD:/workspace/g380_scratch/sources/$NAME"; then
      echo "SEND_FAILED_FINAL $GID"
      continue
    fi
  fi
  echo "=== $(date -u +%H:%M:%SZ) RUN $GID"
  $SSH "bash /workspace/wt/a19/scripts/platformkit/tracking/g380_a3_one.sh '$NAME' '$SHA' '$GID'"
  echo "=== $(date -u +%H:%M:%SZ) RC=$? $GID"
done < <(tail -n +2 "$EV/a3_sources.csv")
echo "A3_DRIVE_DONE $(date -u +%H:%M:%SZ)"
