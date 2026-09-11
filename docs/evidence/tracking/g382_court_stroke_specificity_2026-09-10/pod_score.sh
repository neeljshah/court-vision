#!/bin/bash
# G382 pod-CPU scoring: two independent processes over the same staged native pixels.
set -e
S=/workspace/g382_scratch
WT=/workspace/wt/a20
MODE="${1:-both}"
OUT=$S/score_$MODE
mkdir -p "$OUT"

# frames_score.csv: RETAINED rows only, native_path repointed at the decoded native PNG.
python3 - "$MODE" <<'PYEOF'
import csv, sys
from pathlib import Path
S = Path("/workspace/g382_scratch")
mode = sys.argv[1]
rows = [r for r in csv.DictReader(open(S/"frames.csv")) if r["retained"] == "RETAINED"]
masks = S/("masks_"+mode)
keep = []
for r in rows:
    safe = r["frame_key"].replace(":", "_").replace("/", "_")
    src = masks/(safe+".json")
    if not src.is_file():
        continue
    dst = masks/(r["frame_key"]+".json")
    if dst != src:
        dst.write_bytes(src.read_bytes())
    keep.append({"frame_key": r["frame_key"], "native_path": r["frame_path"]})
with open(S/("frames_score_%s.csv" % mode), "w", newline="") as h:
    w = csv.DictWriter(h, fieldnames=["frame_key", "native_path"], lineterminator="\n")
    w.writeheader(); w.writerows(keep)
print("SCORE_INPUT mode=%s frames=%d of retained=%d" % (mode, len(keep), len(rows)))
PYEOF

cd "$WT"
for run in 1 2; do
  echo "=== run $run ($MODE) ==="
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="$WT" \
    nice -n 10 taskset -c 0-5 python3 -m scripts.platformkit.tracking.g382_score \
    --frames "$S/frames_score_$MODE.csv" --masks "$S/masks_$MODE" --out "$OUT/run$run"
done
PYTHONPATH="$WT" python3 -m scripts.platformkit.tracking.g382_repeat \
  --first "$OUT/run1/receipt.json" --second "$OUT/run2/receipt.json" --out "$OUT/repeats.json" \
  || echo "REPEAT_NOT_IDENTICAL"
echo "POD_SCORE_DONE $MODE"
