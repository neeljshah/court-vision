#!/bin/bash
# usage: correction.sh <rater> <codex_home>
# PRACTICE feedback pass only. Each rater may request exactly ONE instruction or
# display correction. It is recorded, frozen, and never revisited.
R="$1"; HOME_DIR="$2"
WT=C:/Users/neelj/nba-track-a3
CODEX=$(for d in $(ls -1dt /c/Users/neelj/AppData/Local/OpenAI/Codex/bin/*/); do \
  [ -f "$d/codex.exe" ] && [ -f "$d/codex-code-mode-host.exe" ] && echo "$d/codex.exe" && break; done)
[ -z "$CODEX" ] && echo "FAULT no complete codex bin dir" && exit 2
EVID="$WT/docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11"
OUTDIR="$WT/.g396_out/corrections"
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
gate
LOG="C:/Users/neelj/AppData/Local/Temp/cx_g396_rater_${R}_correction01.log"
P="You rated 30 practice images. Read your instruction file $EVID/rater_instruction_control.md and your practice feedback $EVID/practice/feedback_${R}.md. You may now request AT MOST ONE correction to your own instructions or to how you display/read the image - one sentence, no more. It will be appended to your instructions and frozen; there will be no further feedback and no retry. Write exactly one JSON file ${OUTDIR}/correction_${R}.json with keys requested (true or false), correction (the one sentence, or an empty string), rationale (at most three sentences). Do not read any other file. Do not run git. Do not rate anything. ASCII only."
echo "$(date +%H:%M:%S) launch $R correction codex=$CODEX"
python /c/Users/neelj/bin/hidden_launch2.py --log "$LOG" --cwd "$WT" --tag "g396_rater_${R}_correction01" \
  --env "CODEX_HOME=$HOME_DIR" -- "$CODEX" exec --skip-git-repo-check --sandbox workspace-write \
  -c model_reasoning_effort=high -- "$P"
echo "$(date +%H:%M:%S) done $R correction rc=$? files=$(ls -1 "$OUTDIR" 2>/dev/null | wc -l)"
