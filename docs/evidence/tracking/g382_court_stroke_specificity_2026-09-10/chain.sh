#!/bin/bash
# G382 rater chain: dispatch batches under the PC gate (<=3 codex exec, >=2.8 GB free).
R="$1"; HOME_ENV="$2"; START="$3"
CX=$(ls -1dt /c/Users/neelj/AppData/Local/OpenAI/Codex/bin/*/codex.exe | head -1)
[ -f "$(dirname "$CX")/codex-code-mode-host.exe" ] || { echo "BAD_BIN $CX"; exit 1; }
W=/c/Users/neelj/g382_pc_scratch/work/$R
for n in $(seq -w "$START" 5); do
  while true; do
    C=$(powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \"Name='codex.exe'\" | Where-Object { \$_.CommandLine -match ' exec ' }).Count")
    M=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)")
    ok=$(python -c "print(1 if $C < 3 and $M >= 2.8 else 0)")
    [ "$ok" = "1" ] && break
    echo "$(date -u +%H:%M:%S) gate wait codex=$C ram=$M"; sleep 100
  done
  LOG=C:/Users/neelj/AppData/Local/Temp/cx_g382_rater_${R}_${n}.log
  echo "$(date -u +%H:%M:%S) dispatch $R batch_$n"
  python ~/bin/hidden_launch2.py --log "$LOG" --cwd "C:/Users/neelj/g382_pc_scratch/work/$R" \
    --tag "g382_rater_${R}_${n}" --env "CODEX_HOME=$HOME_ENV" -- "$CX" exec \
    --skip-git-repo-check --sandbox workspace-write -c model_reasoning_effort=medium -- \
    "Read rater_instruction.md in this directory and follow it exactly. Your batch file is batches/batch_${n}.txt. Write one JSON file per line of that batch into the ratings/ subdirectory. Open and look at every sheet image. Write nothing except those JSON files." >> "$LOG.chain" 2>&1
  echo "$(date -u +%H:%M:%S) done $R batch_$n outputs=$(ls $W/ratings | wc -l)"
done
echo "CHAIN_DONE $R outputs=$(ls $W/ratings | wc -l)"
