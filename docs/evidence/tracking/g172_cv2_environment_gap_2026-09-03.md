# G172 - current pod run does not reproduce the historical 3.6x frame gap

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A2, A7,
Q7-Q8, and section B. Rails were read from
`.claude/skills/lane-spawn-rails/SKILL.md`. The run was isolated under `nohup`;
no daemon, keeper, deployment, or OpenCV installation was touched.

## Verdict

**NOT REPRODUCIBLE.** Fresh pod OpenCV 5.0.0 decoded 28,773 frames and the
unchanged tennis adapter emitted 6,511 rows over 2,518 distinct frames from
the 38,094,576-byte `tennis_smoke.mp4` clip. Historical G152b local OpenCV
4.11.0 emitted 6,770 rows over 2,597 frames from the pre-overwrite 38 MB
clip. The fresh pod count is 79 frames (3.042%) below G152b, not the old
`tennis_smoke` 726-frame endpoint (a 3.577x gap).

This does not isolate OpenCV. The fresh pod adapter and entrypoint hashes do
not match the historical G152b local source hashes. It does establish that the
reported 3.6x endpoint gap is not reproduced by the current pod runtime.

## Q8 premise re-measurement

| Historical source | OpenCV | Decoded | Rows | Distinct frames |
|---|---:|---:|---:|---:|
| G152b local, about 09:40 | 4.11.0 | 28,773 | 6,770 | 2,597 |
| Historical pod `tennis_smoke` | not retained | 28,773 | 1,861 | 726 |

G170 establishes that the local reference was overwritten at 09:45:18, after
both historical runs; G152b used the earlier 38 MB clip. G169's initial
current-file comparison was corrected for that timeline. No local decode was
attempted: the historical sequential count is durable and a local decode was
RAM-killed earlier today.

## Commands and raw output

Historical evidence retained by G169:

```text
CHECK_CV2=4.11.0
REMOTE_DECODED_FRAMES=28773
```

One SSH batch launched and waited for this isolated scratch command. Its
in-process Python instantiated `TennisAdapter`, wrapped only the detector to
count calls and raw boxes, ran `process_video` with stride one and
`max_frames=30000`, then wrote only the scratch outputs.

```text
cd /workspace/nba-ai-system
game_id=g172_cv2_environment_gap_20260903_a5
nohup /usr/local/bin/python -u - "$game_id" > /workspace/g172_cv2_environment_gap_20260903_a5.log 2>&1 &
```

Launch output:

```text
POD_CWD=/workspace/nba-ai-system
POD_GAME_ID=g172_cv2_environment_gap_20260903_a5
POD_CLIP_BYTES=38094576 POD_CLIP_MTIME=2026-09-03 14:16:01.000000000 +0000
685b25d113f1c62e02e7de1f53fcfbad0bfefbefb45feff6c22d63aca89c18db  data/videos/tennis_smoke.mp4
c7314449ddccc9f27868ea5a20dbbe8458c96d9a4678b9597dc4b585708fcc58  domains/tennis/tracking/adapter.py
90172789dc13bf771a93c5dacbb9568eceb06783dc51e8b591fa2f380621f4e0  scripts/platformkit/adapter_run.py
NOHUP_PID=66985
```

One final batched collection read the completed log and independently recounted
the CSV. Raw output:

```text
OPENCV=5.0.0
DECODED_FRAMES=28773
EVALUATED_FRAMES=28773
DETECTOR_CALLS=2522
DETECTOR_BOXES_RAW=11409
FRAMES_WITH_PLAYER_PAIR=2487
PLAYER_ROWS=4974
BALL_ROWS=1537
TOTAL_ROWS=6511
DISTINCT_EMITTED_FRAMES=2518
HARNESS_PASSED=False
STATUS_COUNTS={"calibration_unavailable": 25843, "emitted_players": 2487, "no_complete_player_pair": 35, "unsolved_drift": 408}
HARNESS_FAILURES=["duplicate frame-track rows 3", "median_track_len 2.00 < 3.00", "jump_max 56.27 > 8.00"]
OUTPUT_CSV=data/tracking/g172_cv2_environment_gap_20260903_a5/tracking_data.csv
OUTPUT_MANIFEST=data/tracking/g172_cv2_environment_gap_20260903_a5/tracking_data.manifest.csv
OUTPUT_STAGE_COUNTS=data/tracking/g172_cv2_environment_gap_20260903_a5/g172_stage_counts.json
CSV_RECOUNT_ROWS=6511
CSV_RECOUNT_DISTINCT_FRAMES=2518
```

The remote log is `/workspace/g172_cv2_environment_gap_20260903_a5.log`.
It is not a committed dependency: the full raw runtime result is above. The
scratch id is `g172_cv2_environment_gap_20260903_a5`; `tennis_smoke` was not
written.

## Endpoint and stage comparison

| Measure | G152b local | Fresh pod | Result |
|---|---:|---:|---|
| Decoded frames | 28,773 | 28,773 | Equal; decode is not the source. |
| Emitted rows | 6,770 | 6,511 | Fresh pod lower by 259 (3.826%). |
| Distinct emitted frames | 2,597 | 2,518 | Fresh pod lower by 79 (3.042%). |
| Historical pod distinct frames | 726 | 2,518 | Old low endpoint not reproduced. |

Fresh-pod stages: all 28,773 frames evaluated; 25,843
`calibration_unavailable`, 408 `unsolved_drift`, 35 `no_complete_player_pair`,
and 2,487 `emitted_players`. Detector calls were 2,522 with 11,409 raw boxes;
2,487 frames passed the two-player rule. Player and ball rows were 4,974 and
1,537. The 2,518 distinct emitted-frame total includes ball-only emissions.

The historic 726-frame table lacks a manifest, detector-call count, raw-box
count, and two-slot count. Decode is ruled out, but detection versus the
two-slot rule cannot be assigned for that low run. The stage result is
**unknown**, not an environment assignment.

G152b commit `ddb4e09c174fe7e321a6ca5d8a0577bf4d08da00` hashes are
`f7687c5646dfa3f9a8206d1559238941020b6f5828d28c160e11426699a2bac9`
for the adapter and
`773a59619a5a374c7a4a1c5467a8edd65c8dee324db1f485787700485a7e2e67`
for the entrypoint. They differ from the fresh pod hashes above. No source was
copied to the pod (B5).

## Consequence for the register

G169's G152b-versus-historical-`tennis_smoke` comparison is directly affected:
the current pod does not exhibit the low endpoint, but the historic causal
stage remains unarchived and no result is retracted. G52 and its G26
cross-environment comparison remain affected only in their recorded scope:
this row neither repeats their ranges nor isolates OpenCV from OS, Python, or
source state. G14's local-versus-pod `0.8970` statement is named but not
recomputed or re-adjudicated. G160 is a source inventory, not an output metric,
and is unaffected. No other named local-versus-pod tracking comparison was
identified in the register.

## Verifier-contract self-check

- **A2:** Final SSH collection independently recounted 6,511 CSV rows and
  2,518 unique `frame` values, matching the runtime summary.
- **A4/B9:** Rows and distinct frames are separate; the decoded denominator is
  all 28,773 frames, never a track-id count.
- **A7:** Before commit, this memo, G152b, G169, G160, the ledger, register,
  and verifier contract were checked to exist.
- **Q7/Q8:** This is the specified construct reproduction; commands and raw
  output replace sampling, and timing plus the historical counts were checked
  before the run.
- **B1:** Clear; no decoded frames, rows, or emitted frames were excluded.
- **B2:** Clear; no schema, status, field, or reader changed.
- **B3/B4:** Clear; no gate, lifecycle, queue, or retry behavior changed.
- **B5:** Clear; resident pod code only, with no copy or deploy.
- **B6:** Clear; no module, import, test, or command moved or retired.
- **B7:** Clear; Q7 reproduction replaces visual sampling.
- **B8:** Clear; no fit or independent-residual claim.
- **B10:** Clear; no threshold, gate, coordinate contract, or verdict moved.

## NOT VERIFIED

- Historic low-run detector, calibration, and two-slot counts.
- A one-variable OpenCV effect; source hashes differ and local OS/Python were
  not changed or re-run.
- The exact historical OpenCV version and command line for the 726-frame run.
- Any tracking-quality, calibration, coverage, or downstream conclusion.

No code changed, so no per-file test applied. No full pytest run was made.
