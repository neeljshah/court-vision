# G346 preregistration

Date: 2026-09-08
Route: `scripts/platformkit/footage_liveness.py` called by `scripts/platformkit/footage_content_gate.py`.
Sample rule: attempt 60 frame indices evenly spaced over `[0, frame_count - 1]`; decode at 320x180 grayscale and report valid decoded count.
Measures: mean absolute difference of consecutive sampled frames on a 0-255 scale; near-identical share where difference is `< 1.0`; bytes per frame is container byte size divided by reported frame count.
Frozen rule: FROZEN if near-identical share is `>= 0.90`, or if bytes per frame is `< 2000` and decoded height is `>= 720`; otherwise LIVE.
Decision rule: the existing gate decision and reason remain unchanged unless explicit `--reject-frozen` is supplied; that option defaults OFF.
Comparison convention: no calibration comparison is scored in this preparation lane. If a comparison is later made, improvement equals baseline loss minus candidate loss; positive means candidate better.
Inputs: named G338 sections are remeasured only when present under this worktree; their absence is reported, never treated as FROZEN.
Census scope: finisher-only pod snapshot; seal its source file list and SHA-256 digests before measuring.
SEAL sha256 9c8bfb7bfc163b1e781b33becec7bb25565fbb86d69a11b1c95f32808cfc0b4f
