VERDICT: PREMISE FALSE -- the amended G335 before-condition fails; STOP before preregistration, arm scoring, prototype, flag, or test.

# G335 ball detection coverage (2026-09-08, POD read-only census)

Contract cited and self-checked: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections A/B and Q as applicable.
MACHINE: pod, because the binding corpus is pod-only; the run used read-only CSV streams and did not dispatch a pod job.
PYTHON: 3.12.3. Wall time: about 20 seconds across the successful census reruns; no GPU work.

INPUTS (A9): every input opened was one CSV at a time under
`/workspace/nba-ai-system/data/tracking/<clip>/ball_tracking.csv`; this final snapshot found 491 clip directories and 485 present ball tables.
Each input is CSV, so video resolution is not applicable; no video or staged footage was opened.
The binding fields were `detected`, `ball_x2d`, and `ball_y2d`; all 485 present tables had those headers.

## Binding before-condition rerun

Exact final read-only census output:

| measure | value |
|---|---:|
| clips total | 491 |
| with a ball table | 485 |
| with at least one detected row | 475 |
| zero detected-ball tables | 10 |
| median detected rows per clip (n) | 703 (485) |
| median detected share per frame (n) | 0.866666667 (485) |
| rows total | 406115 |
| rows with a finite coordinate pair | 318293 |
| clips with a coordinate row | 475 |
| malformed required headers | 0 |

The amended stop condition requires fewer than 60 percent zero-detected tables AND median detected share above 0.20. Here 10/485 = 0.020619 and 0.866666667 > 0.20. Therefore the premise is false and the spec requires STOP.

## Read-only route trace

The detector call is `src/tracking/ball_detect_track.py:326-398` (COCO `classes=[32]`, `conf=0.20`, `imgsz=384` at :349; dedicated model `conf=0.05`, `imgsz=384` at :356), class filtering is :361-374, size filtering is :390-398, the tracker begins at :585, and the writer is `src/pipeline/unified_pipeline.py:4028-4045`.
Local route hashes: `ball_detect_track.py` `44de8241736bf650b947c2ce33e9d2daccfa3b0468ef6f888a950e99030c5381`; `unified_pipeline.py` `bb92310f54c06ffa4c7caf6bea23861a29c35f3588b6fb4a375aeaf74b6b15f8`; census reader `g309_multigame_census.py` `af1155f6b5cda332981d277cb7ae721df389c63f2cedb4c48fa375c6f0c620f8`.

No scored comparison occurred, so no preregistration, evaluator state, paired-loss archive, arm table, stage table, or delta exists. If a comparison were authorized, its sign convention would be improvement = baseline loss minus candidate loss; positive means the candidate is better.
No `src/`, `data/`, registry, flag default, pod daemon, guard, or threshold changed. The user instruction prohibits modifying the results ledger or register; neither was touched.

## Verifier B/Q self-check

No metric excluded rows (B1); no schema, gate, state machine, deployment, module, render, or threshold changed (B2-B10 clear). Q1-Q5 and Q9 are not applicable because scoring never started; Q6 is clear (calibration language only).

## NOT VERIFIED

- Detector recall, loss stage, raw/after-stage counts, coverage arms, plausibility, detector time, and all acceptance-bar comparisons were not measured after the required premise stop.
- No ball ground truth, candidate render, video resolution, or possession claim was evaluated.
- The pod tree changed between read-only reruns (the final snapshot had 485 tables); this memo reports only the final snapshot and does not establish historical stability.
- Per-file byte sizes were read during the census but are not archived in this bounded premise-stop memo; the full input manifest is not verified.
- Independent verification could not recreate the exact pod snapshot; a current 408-clip local mirror confirmed the stop classification only.

## Landing 2026-09-08 (verifier codex-sol: ACCEPT WITH CORRECTIONS)

- NEW GAP: archive the per-clip census manifest, or a compact aggregate of it, so a changing or unavailable pod cannot make the exact headline irreproducible.
- NEW GAP: the spec names a G335 test path that does not exist; that path is conditional on the flag being added, and this premise-stop row adds no flag.
- NEW GAP: linked-worktree index.lock blocked the lane's own commit (direct pathspec commit and lane_commit.py both failed); the memo landed via an external committer.

Vocabulary follows contract Q6; automated scan required.
