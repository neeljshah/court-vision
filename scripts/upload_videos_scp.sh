#!/bin/bash
# Sequential scp upload with skip-if-exists. Resumable.
set -uo pipefail
IP=213.192.2.107
PORT=40017
SRC="data/videos/full_games"
DEST="root@${IP}:/workspace/nba-ai-system/data/videos/full_games"

# Get list of remote files with sizes
REMOTE=$(ssh -o StrictHostKeyChecking=no -p $PORT root@$IP "find /workspace/nba-ai-system/data/videos/full_games -name '*.mp4' -printf '%f %s\n' 2>/dev/null")

uploaded=0
skipped=0
failed=0
for f in $SRC/*.mp4; do
    name=$(basename "$f")
    local_size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f")
    remote_size=$(echo "$REMOTE" | awk -v n="$name" '$1==n{print $2; exit}')
    if [ -n "$remote_size" ] && [ "$remote_size" = "$local_size" ]; then
        skipped=$((skipped+1))
        continue
    fi
    echo "[$(date +%H:%M:%S)] Uploading $name (${local_size} bytes)..."
    if scp -q -o StrictHostKeyChecking=no -P $PORT "$f" "$DEST/" 2>&1; then
        uploaded=$((uploaded+1))
    else
        failed=$((failed+1))
        echo "  FAIL: $name"
    fi
done
echo "Done. uploaded=$uploaded skipped=$skipped failed=$failed"
