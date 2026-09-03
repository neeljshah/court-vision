GAP G182 | sport tennis | worktree a5 | log cx_g182_calibration_unavailable_cause
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it (A2, A3, A7, Q8); self-check B.
RAILS: heavy work ON THE POD under nohup, batched, never poll. One store at a time, never a whole
store over 300 MB. NEVER kill, restart or deploy over the pod daemon or keeper. Never launch
powershell. Never write under `data/`. ASCII only. Never paste a credential-shaped string.

THE ONE TENNIS QUESTION LEFT. G175 (landed) joined G161's 113 hand-labelled `RALLY_VIEW` frames to
the per-frame `status` column and found the killer:

| status | RALLY_VIEW | share | NOT_RALLY | share |
|---|---:|---:|---:|---:|
| `calibration_unavailable` | 104/113 | **92.04 pct** | 170/187 | **90.91 pct** |
| `emitted_players` | 8/113 | 7.08 pct | 15/187 | 8.02 pct |
| `unsolved_drift` | 1/113 | 0.88 pct | 2/187 | 1.07 pct |

Two things follow and both are already adjudicated -- do NOT re-open them. (1) The coverage bar is not
the binding constraint and tennis is CLOSED AT LIMIT. (2) Rally-view selection does NOT rescue tennis,
because calibration is missing inside rally view at essentially the same rate as outside it. G166
separately showed 89.08 pct of identity resets are `emission_gap` false resets, so coverage,
`median_track_len` and `jump_max` are ONE defect read three ways.

**That defect is `calibration_unavailable`, and nobody has traced WHY it fires.** This row traces it.

DO THIS:
  (a) Find where `calibration_unavailable` is set. Quote it with file:line and give the FULL condition
      chain that leads there -- every branch, not just the last one. Q8: quote, do not infer.
  (b) The adapter holds `self._corners`, `self._homography`, a `CameraLock` and a `TemporalCalibrator`.
      Establish which of them being absent or stale produces this status, and in what order they are
      consulted. Name the single earliest point at which a frame is doomed.
  (c) Instrument READ-ONLY on the pod to count, over the decoded frames of one tennis clip, how many
      reach each stage of that chain. A funnel: N decoded -> N reaching corner detection -> N with
      enough corners -> N with a homography -> N passing the lock/drift check -> N emitting. **The
      funnel is the deliverable.** Report the eligible denominator at every step; never a bare count.
  (c2) Commit the instrumentation diff as an UNLANDED measurement harness and restore the adapter.
  (d) Say which single step loses the most frames, with its share. If corner detection is the wall,
      say so plainly -- G136/G138/G141 already measured basketball's corner detection as
      unrecoverable, and a tennis equivalent would be a major, decision-relevant result.
  (e) Eye check REQUIRED: render 5 frames sampled EVENLY (A3, B7 -- never a head slice) from the
      largest-loss step and say what the eye sees. A frame a human would call obviously calibratable
      is a very different finding from one where the court genuinely is not visible.

DO NOT change the adapter, the solver, the camera lock, the drift threshold, the harness, any bar, the
coordinate contract, or any verdict. Do not propose a fix -- this row locates the wall, it does not
move it. Do not re-open the coverage adjudication.

ACCEPTANCE RULE:
  metric        = the quoted condition chain; the per-stage funnel with a denominator at every step;
                  the largest-loss step named with its share
  before        = `calibration_unavailable` is 92 pct of rally frames with no traced cause
  bar           = NO pass bar. Success is the funnel measured and the wall located. "Corner detection
                  is the wall and it is unrecoverable on this footage" is a FULL SUCCESS and would be
                  the most decision-relevant outcome available.
  n             = every decoded frame of >= 1 tennis clip (CONSTRUCT, exhaustive); state the count
  eye check     = REQUIRED: 5 evenly sampled frames from the largest-loss step, committed
  must not move = the adapter, the solver, the camera lock, every threshold and bar, the coordinate
                  contract, and every verdict
EVIDENCE: docs/evidence/tracking/g182_calibration_unavailable_cause_2026-09-03.md with the quoted
chain, the funnel table, the named wall, renders under docs/evidence/tracking/g182_funnel/, the
unlanded instrumentation diff, and a NOT VERIFIED list. **COMMIT THE MEMO BEFORE YOU REPORT (A7).**
TEST: one per-file test only if you add code; run it alone. NEVER a full pytest.
COMMIT: explicit pathspec only, in a5, no push. Report the sha and the largest-loss step.
NEVER PARK.
