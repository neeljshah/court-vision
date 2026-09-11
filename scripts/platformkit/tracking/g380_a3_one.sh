#!/bin/bash
# G380 amendment A3, pod side: verify ONE sent source against its G386 sha256, run
# the PATCHED arm alone on it under the independent import-time hook, delete the copy.
# Usage: bash g380_a3_one.sh <source_name> <expected_sha256> <game_id>
set -u
NAME="$1"; WANT="$2"; GID="$3"
SRC="/workspace/g380_scratch/sources/$NAME"
EV="/workspace/wt/a19/docs/evidence/tracking/g380_producer_provenance_2026-09-10"
GOT=$(sha256sum "$SRC" 2>/dev/null | cut -d' ' -f1)
if [ "$GOT" != "$WANT" ]; then
  echo "SHA_MISMATCH $NAME got=$GOT want=$WANT"
  rm -f "$SRC"
  exit 9
fi
echo "SHA_OK $NAME"
cd /workspace/g380_scratch/armA || exit 8
PYTHONDONTWRITEBYTECODE=1 python3 -m scripts.platformkit.tracking.g380_trace_sections \
  --out "$EV" --source "$SRC" --game-id="$GID" --csv-name receipts_trace_a3.csv
RC=$?
rm -f "$SRC"
du -sm /workspace
exit $RC
