#!/bin/bash
# usage: dispatch.sh <rater> <codex_home> <set>   set = smoke | practice | qualification | real
R="$1"; HOME_DIR="$2"; SET="$3"
CACHE=/c/Users/neelj/AppData/Local/Temp/g396_work
WT=C:/Users/neelj/nba-track-a3
# PINNED: the newest bin dir can lack codex-code-mode-host.exe and rates nothing.
CODEX=$(for d in $(ls -1dt /c/Users/neelj/AppData/Local/OpenAI/Codex/bin/*/); do \
  [ -f "$d/codex.exe" ] && [ -f "$d/codex-code-mode-host.exe" ] && echo "$d/codex.exe" && break; done)
[ -z "$CODEX" ] && echo "FAULT no complete codex bin dir" && exit 2
EVID="$WT/docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11"
INSTR="$EVID/rater_instruction_control.md"
[ "$SET" = qualification ] && INSTR="$EVID/frozen_instructions_${R}.md"
[ "$SET" = smoke ] && INSTR="$EVID/rater_instruction_smoke.md"
[ "$SET" = real ] && INSTR="$EVID/rater_instruction_real.md"
OUTDIR="$WT/.g396_out/${SET}_${R}"
mkdir -p "$OUTDIR"
gate() {
  while true; do
    C=$(powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \"Name='codex.exe'\" | Where-Object { \$_.CommandLine -match ' exec ' }).Count" | tr -d '\r')
    M=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r')
    OK=$(python -c "print(1 if $C < 3 and $M >= 2.8 else 0)")
    [ "$OK" = "1" ] && return 0
    echo "$(date +%H:%M:%S) gate wait codex=$C ram=$M"
    sleep 110
  done
}
n=0
for B in "$CACHE/batch_${SET}_${R}"/batch_*.tsv; do
  n=$((n+1)); NN=$(printf "%02d" $n)
  gate
  LOG="C:/Users/neelj/AppData/Local/Temp/cx_g396_rater_${R}_${SET}${NN}.log"
  P="You are a blind image rater. Read the instruction file $INSTR and follow it EXACTLY. Your batch file is $(cygpath -m "$B"). Your output directory is $(cygpath -m "$OUTDIR") - create it if needed and write one JSON file per batch line there. Open and look at every image path listed. Do not read any other file. Do not run git. Do not search the repository. ASCII only."
  echo "$(date +%H:%M:%S) launch $R $SET $NN codex=$CODEX"
  python /c/Users/neelj/bin/hidden_launch2.py --log "$LOG" --cwd "$WT" --tag "g396_rater_${R}_${SET}${NN}" \
    --env "CODEX_HOME=$HOME_DIR" -- "$CODEX" exec --skip-git-repo-check --sandbox workspace-write \
    -c model_reasoning_effort=high -- "$P"
  echo "$(date +%H:%M:%S) done $R $SET $NN rc=$? files=$(ls -1 "$OUTDIR" 2>/dev/null | wc -l)"
done
echo "ALLDONE $R $SET files=$(ls -1 "$OUTDIR" 2>/dev/null | wc -l)"
