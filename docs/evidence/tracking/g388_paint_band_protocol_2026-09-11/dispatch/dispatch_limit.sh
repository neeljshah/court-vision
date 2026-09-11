#!/bin/bash
# usage: dispatch.sh <rater> <codex_home> <pass>
R="$1"; HOME_DIR="$2"; PASS="$3"
CACHE=/c/Users/neelj/AppData/Local/Temp/g388_work
WT=C:/Users/neelj/nba-track-a12
# PINNED: the newest bin dir lacks codex-code-mode-host.exe and rates nothing.
CODEX=$(for d in $(ls -1dt /c/Users/neelj/AppData/Local/OpenAI/Codex/bin/*/); do \
  [ -f "$d/codex.exe" ] && [ -f "$d/codex-code-mode-host.exe" ] && echo "$d/codex.exe" && break; done)
[ -z "$CODEX" ] && echo "FAULT no complete codex bin dir" && exit 2
INSTR="$WT/docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/rater_instruction_$( [ "$PASS" = ctlimit ] && echo control || echo $PASS ).md"
OUTDIR="C:/Users/neelj/nba-track-a12/.g388_out/${PASS}_${R}"
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
for B in "$CACHE/batch_${PASS}_${R}"/batch_*.tsv; do
  n=$((n+1)); NN=$(printf "%02d" $n)
  gate
  LOG="C:/Users/neelj/AppData/Local/Temp/cx_g388limit_rater_${R}_${PASS}${NN}.log"
  P="You are a blind image rater. Read the instruction file $INSTR and follow it EXACTLY. Your batch file is $(cygpath -m "$B"). Your output directory is $(cygpath -m "$OUTDIR") - create it if needed and write one JSON file per batch line there. Open and look at every image path listed. Do not read any other file. Do not run git. Do not search the repository. ASCII only."
  echo "$(date +%H:%M:%S) launch $R $PASS $NN codex=$CODEX"
  python /c/Users/neelj/bin/hidden_launch2.py --log "$LOG" --cwd "$WT" --tag "g388limit_rater_${R}_${PASS}${NN}" \
    --env "CODEX_HOME=$HOME_DIR" -- "$CODEX" exec --skip-git-repo-check --sandbox workspace-write \
    -c model_reasoning_effort=medium -- "$P"
  echo "$(date +%H:%M:%S) done $R $PASS $NN rc=$? files=$(ls -1 "$OUTDIR" 2>/dev/null | wc -l)"
done
echo "ALLDONE $R $PASS files=$(ls -1 "$OUTDIR" 2>/dev/null | wc -l)"
