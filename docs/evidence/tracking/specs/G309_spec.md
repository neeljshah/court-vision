GAP G309 | sport all | worktree a12 | log g309_multigame_census
**MEASUREMENT ONLY, READ-ONLY ON THE POD. `src/`, `domains/` and `api/` are READ and IMPORT only.
Build in `scripts/platformkit/tracking/`. Propose NO production change. Adopt nothing.**

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **THE CENSUS RUNS ON THE POD** -- `data/tracking/` lives there and is NOT in the local checkout.
    Use `~/bin/pod_run a12 --fetch docs/evidence/tracking/g309_multigame_census_2026-09-07.csv --
    python -m scripts.platformkit.tracking.g309_multigame_census`. ONE job. Poll to POD_RUN_DONE.
  - **NO GPU.** This row reads CSV and JSONL only. It contends for NOTHING the daemon needs, so the
    GPU lease does NOT apply and `nvidia-smi` is NOT a gate here. **Report the reading anyway as
    context.**
  - **NEVER stop, signal or interfere with `track_daemon` (pid 25560, 4 workers).** It is WRITING the
    tree you are reading. Read whatever is on disk at census time and **timestamp the census**; a
    partially written file is a FINDING, not a failure.
  - **DISK GUARD: none needed** -- this row writes one CSV and one memo. `du -sm /workspace` is a
    MooseFS network walk: empty means UNKNOWN, NEVER 0, and NEVER stop on UNKNOWN.
  - **THE MEMO AND THE ARITHMETIC CHECKS ARE LOCAL**, on the fetched CSV.

**WHY THIS ROW EXISTS.** Every tracking row to date measured ONE clip. The reallocated pod has now
tracked eight games in one sitting and the feeder is adding more, so for the first time the programme
can ask **what the CROSS-GAME distribution of its own tracking output looks like** -- and whether the
eight games fail the same way or eight different ways. **A per-game defect that is invisible in a
single-clip row (a game with zero ball rows, an id churn twice the median, a coverage outlier) is
exactly what a census surfaces.**

**PREMISE (step 0, BINDING before-condition):** count the ledger rows in
`data/tracking/track_daemon_ledger.jsonl` with `passed != null` and **PRINT THE COUNT**. **If that
count is below 6, STOP, write the memo, commit, and report PREMISE FALSE** -- a census of fewer than
six games is a case series, not a distribution. **At allocation time the orchestrator measured 8**
(16 ledger lines: 8 `status=thin` with `passed=null`, 8 `status=tracked` with `passed=false`).

METHOD:
  1. **ENUMERATE** every `data/tracking/<game>/` directory holding a `tracking_data.csv`. For each,
     read `tracking_data.csv`, `ball_tracking.csv` if present, `harness_verdict.json` and
     `evaluated_frame_count.json` if present, and the **LAST** ledger line whose `game_id` matches.
     **A game directory with no ledger line still gets a census row, with the ledger fields empty and
     `ledger_row=absent` -- say so rather than dropping it.**
  2. **COMPUTE PER GAME, ALL IN IMAGE SPACE.** `coordinate_space` is `image_px`; **make NO court,
     foot, metre or registration claim anywhere in this row, and state that the census cannot and does
     not speak to registration.** Metrics, each with its denominator named in the memo:
     - `rows` (data rows in `tracking_data.csv`), `frames_emitted` (distinct `frame` values)
     - `frames_attempted` = the harness/ledger `evaluated_frames` where present, else
       `ceil(decoded_frames / stride)`; `coverage_attempted_frames_pct` = frames_emitted /
       frames_attempted. **Also report `coverage_decoded_pct` = frames_emitted / decoded_frames, which
       is what the ledger's own `coverage_pct` means -- name which is which, they differ by the stride.**
     - `distinct_track_ids`; `median_track_len_rows` (median rows per `player_id`)
     - `id_churn_per_detection` = distinct_track_ids / rows
     - ball: `ball_rows`, `ball_detected`, `ball_inferred`, `ball_none`, and `ball_valid_share` =
       rows with a finite `ball_x2d` AND `ball_y2d`, over `ball_rows`. **Name the convention.**
     - `p95_disp_norm` = the 95th percentile of the per-track consecutive-observation displacement of
       the bbox bottom-centre `((bbox_x1+bbox_x2)/2, bbox_y2)`, in image px, **divided by
       `source_height`**. **State the footpoint convention and that steps skip a frame gap without
       interpolating.** Report `n_steps` as its denominator.
     - `share_frames_ge6_boxes` = frames with >= 6 player rows, over frames_emitted
     - `zero_step_share` = steps with displacement exactly 0.0, over `n_steps` (LIVENESS -- a high
       share is the held-position defect recorded on 2026-09-01)
     - the ledger's own `passed`, `status`, `rung`, `verdict` and the FIRST `failure_heads` entry
       verbatim (truncated, ASCII), so the reader sees the stated failure reason next to the numbers.
  3. **ONE TABLE:** `docs/evidence/tracking/g309_multigame_census_2026-09-07.csv`, one row per game,
     every metric above as a named column. **Fetch it back and commit it.**
  4. **CROSS-GAME DISTRIBUTION IN THE MEMO:** for each numeric metric report **median, min, max and
     the named argmin/argmax game**. **Name the outliers by game id.**
  5. **NEW GAP LINES** for anything anomalous -- at minimum: any game with `ball_detected == 0`, any
     game with `id_churn_per_detection` above 2x the median, any game with `zero_step_share` above 2x
     the median, and any game whose recomputed `rows` disagrees with its ledger `rows`.
  6. **CHANGE NOTHING.** No production edit, no threshold, no proposal, no adoption.

**HONEST LIMITATIONS to state, not discover:** **this is a census of the PRODUCER'S OWN OUTPUT with no
ground truth of any kind** -- every metric is an internal-consistency proxy and **not one of them is
recall, precision, accuracy or registration.** **A game can score well on every column here and still
be tracking the wrong things**; say that in those words. The games are whatever the feeder happened to
queue, **not a sample of anything**, so no number here generalises past these files. **All eight
ledger rows at allocation carried `passed=false`, so this is a distribution of FAILING runs.** The
tree is being written while it is read.

ACCEPTANCE RULE:
  metric        = the premise count printed; one census row per game directory holding a
                  `tracking_data.csv`, with EVERY ledger `game_id` that has one appearing EXACTLY
                  ONCE; all metrics of step 2 recomputed FROM THE CSVs and never copied from the
                  ledger; the cross-game median/min/max table with named outliers; and NEW GAP lines
  before        = eight ledger rows with `passed != null`, all `passed=false`, and NO cross-game
                  distribution of any tracking metric anywhere in the programme
  bar           = **NO pass bar. This row is descriptive.** Its success is a complete table with named
                  denominators plus the outliers it surfaces; **finding nothing anomalous is a FULL
                  SUCCESS and must be reported as one.**
  agreement     = recomputed `rows` equals the ledger `rows` EXACTLY for every game where both exist,
                  and recomputed `coverage_decoded_pct` equals the ledger `coverage_pct` **to the
                  ledger's own 4-decimal rounding** (the ledger stores it rounded, so 1e-9 equality is
                  not attainable and is not required); **any disagreement is REPORTED, never patched**
  n             = >= 6 games (8 at allocation) -- name the game count, the row count and every
                  per-metric denominator in the verdict line
  eye check     = NONE. This row has no frames, no renders and no labels; it is arithmetic over
                  committed CSVs. **Say that rather than implying validation.**
  must not move = `data/tracking/` on the pod (READ ONLY -- never write, never delete, never touch the
                  ledger); the running `track_daemon`; `src/`, `domains/`, `api/`, `kernel/`;
                  `tracking_harness.py`; every existing threshold and verdict
EVIDENCE: `docs/evidence/tracking/g309_multigame_census_2026-09-07.md` (<= 60 lines) with the premise
count, the census table summary, the distribution table, named outliers, every denominator, the census
timestamp, and a **NOT VERIFIED** list. The CSV is committed beside it. **ADD ONE RESULTS_LEDGER.md
ROW IN THE SAME COMMIT.** Commit BEFORE reporting (A7). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: `tests/platformkit/test_g309_multigame_census.py` -- a 3-game SYNTHETIC construct pinning
coverage, id churn, ball share and the zero-step liveness share against hand-computed values.
**n = 3 (CONSTRUCT).** Run that ONE file. **NEVER a full pytest.**
COMMIT: explicit pathspec only, no push. ASCII stdout. **NEVER PARK.**
