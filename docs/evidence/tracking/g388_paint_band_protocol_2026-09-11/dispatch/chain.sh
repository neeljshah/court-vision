#!/bin/bash
CACHE=/c/Users/neelj/AppData/Local/Temp/g388_work
cd "$CACHE"
while ! grep -q ALLDONE disp_sol_control.log; do sleep 20; done
echo "$(date +%H:%M:%S) sealed control pass complete: terra=$(ls -1 out_control_terra|wc -l) sol=$(ls -1 out_control_sol|wc -l)"
# LIMIT: only the controls with NO sealed response from at least one rater
mkdir -p batch_ctlimit_terra batch_ctlimit_sol
for R in terra sol; do
  rm -f batch_ctlimit_$R/batch_*.tsv
  n=0
  for B in batch_control_$R/batch_*.tsv; do
    while read -r line; do
      ID=$(echo "$line" | cut -f1)
      [ -f "out_control_terra/$ID.json" ] && [ -f "out_control_sol/$ID.json" ] && continue
      n=$((n+1)); F="batch_ctlimit_$R/batch_$(printf "%02d" $(( (n-1)/10 + 1 ))).tsv"
      echo "$line" >> "$F"
    done < "$B"
  done
  echo "LIMIT $R lines=$n"
done
./dispatch_limit.sh terra "C:\Users\neelj\.codex-a10" ctlimit > disp_terra_ctlimit.log 2>&1
./dispatch_limit.sh sol   "C:\Users\neelj\.codex-sol" ctlimit > disp_sol_ctlimit.log 2>&1
./dispatch_limit.sh terra "C:\Users\neelj\.codex-a10" real > disp_terra_real.log 2>&1
./dispatch_limit.sh sol   "C:\Users\neelj\.codex-sol" real > disp_sol_real.log 2>&1
echo "CHAIN_DONE"
