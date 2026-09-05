#!/usr/bin/env bash
set -euo pipefail
cd /c/Users/neelj/nba-track-a6
OUT=docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact
scp -q -F "$HOME/.ssh/config.pod" pod:/workspace/wt/a6/pod_run_20260904220142.log "$OUT/compute_complete.log"
ssh -F "$HOME/.ssh/config.pod" pod python - <<'PY' > "$OUT/pod_owned_bytes.json"
import json
from pathlib import Path
root = Path('/workspace/wt/a6')
directories = ['g298_scratch', 'g298_code', 'docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact']
files = [p for d in directories for p in (root / d).rglob('*') if p.is_file() and not p.is_symlink()]
files += list((root / 'scripts/platformkit/tracking').glob('*g298*.py'))
files += [root / ('pod_run_' + stamp + '.log') for stamp in ['20260904215838', '20260904220142', '20260904220933', '20260904221053']]
rows = [{'path': str(p), 'bytes': p.stat().st_size} for p in sorted(set(files)) if p.is_file()]
print(json.dumps({'task_owned_files': rows, 'bytes_added_retained': sum(r['bytes'] for r in rows), 'bytes_freed': 8388608, 'freed_reason': 'original pod_run quota probe only; harness freed zero', 'whole_volume_net_growth': 'UNKNOWN; bulk restaging overwrote existing files'}, indent=2))
PY
