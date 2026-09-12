#!/bin/bash
# G409 observer replay driver (regenerating code, run from the PC).
# For each sealed window: ensure the retained original is on the pod, run the
# ARCHIVED producer route inside the observer-injected scratch tree, fetch the
# stage observations, then delete the uploaded source. Never touches the deploy tree.
POD="ssh -n -o ConnectTimeout=20 -o ServerAliveInterval=30 -p 40117 root@213.192.2.120"
OUT=/c/Users/neelj/nba-track-a12/.g409_rep
mkdir -p "$OUT"
python -c "
import json
for j in json.load(open(r'C:/Users/neelj/nba-track-a12/.g409_jobs.json')):
    print('\t'.join(['%s__%s'%(j['draw_kind'],j['section_id']), j['source_path'], j['source_sha256'], str(j['start_frame']), str(j['frames']), j['section_id'], ','.join(str(t) for t in j['ticks'])]))
" > "$OUT/plan.tsv"
wc -l < "$OUT/plan.tsv"
n=0
while IFS=$'\t' read -r key src sha start frames sid ticks; do
  n=$((n+1))
  key=$(echo "$key" | tr -d '\r'); ticks=$(echo "$ticks" | tr -d '\r')
  [ -s "$OUT/$key.jsonl" ] && { echo "SKIP $n $key"; continue; }
  base=$(basename "$src")
  have=$($POD "[ -f '$src' ] && echo YES || echo NO")
  use="$src"; uploaded=0
  if [ "$have" = "NO" ]; then
    lsrc="/c/Users/neelj/g402_receiver/${sid}.mp4"
    [ -f "$lsrc" ] || lsrc="/c/Users/neelj/g402_receiver/$base"
    if [ ! -f "$lsrc" ]; then echo "NOSRC $n $key"; printf '%s\tNOSRC\t\t\t\n' "$key" >> "$OUT/status.tsv"; continue; fi
    scp -q -o ConnectTimeout=20 -P 40117 "$lsrc" root@213.192.2.120:/workspace/g409_scratch/srcs/$base
    use=/workspace/g409_scratch/srcs/$base; uploaded=1
  fi
  podsha=$($POD "sha256sum '$use' 2>/dev/null | cut -d' ' -f1")
  if [ "$podsha" != "$sha" ]; then echo "SHAMISMATCH $n $key"; printf '%s\tSHAMISMATCH\t%s\t\t\n' "$key" "$podsha" >> "$OUT/status.tsv"; [ $uploaded = 1 ] && $POD "rm -f '$use'"; continue; fi
  echo "RUN $n/53 $key"
  rc=$($POD "cd /workspace/g409_scratch/tree && rm -f /workspace/g409_scratch/obs/$key.jsonl && OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 G409_SINK=/workspace/g409_scratch/obs/$key.jsonl G409_TICKS='$ticks' timeout 900 python3 scripts/run_clip.py --video='$use' --game-id='$sid' --no-show --frames $frames --start-frame $start --data-dir=/workspace/g409_scratch/out/$sid > /workspace/g409_scratch/logs/$key.log 2>&1; echo RC=\$?")
  scp -q -o ConnectTimeout=20 -P 40117 root@213.192.2.120:/workspace/g409_scratch/obs/$key.jsonl "$OUT/$key.jsonl" 2>/dev/null
  scp -q -o ConnectTimeout=20 -P 40117 root@213.192.2.120:/workspace/g409_scratch/out/$sid/tracking_data.csv "$OUT/$key.tracking.csv" 2>/dev/null
  logsha=$($POD "sha256sum /workspace/g409_scratch/logs/$key.log | cut -d' ' -f1")
  printf '%s\t%s\t%s\t%s\t%s\n' "$key" "$use" "$podsha" "$rc" "$logsha" >> "$OUT/status.tsv"
  [ $uploaded = 1 ] && $POD "rm -f '$use'"
  $POD "rm -rf /workspace/g409_scratch/out/$sid"
done < "$OUT/plan.tsv"
echo "DRIVER_DONE"
