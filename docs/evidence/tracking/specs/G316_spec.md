GAP G316 | sport all | worktree a12 | log g316_scoreboard_clock_liveness
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check
against every line of section B before you report.
**MEASUREMENT + ADDITIVE RECORD. `src/`, `domains/` and `api/` are READ and IMPORT
ONLY. Build in `scripts/platformkit/tracking/`. If the defect is inside `src/`,
write a PROPOSED diff under `docs/research/organization-sprint/` and STOP -- a
human applies it. Adopt nothing. Flip no flag.**

WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):
  - PREMISE (step 0) is POD: `data/tracking/<game>/tracking_data.csv` lives on the
    pod, not in the local checkout. Use `~/bin/pod_run a12 --fetch <the summary
    JSON> -- python -m scripts.platformkit.tracking.g316_scoreboard_clock_liveness
    --premise`. ONE job. Poll to POD_RUN_DONE. NO GPU: this step reads CSV only.
  - TRACE (step 1) is LOCAL: `src/tracking/scoreboard_ocr.py` and
    `src/pipeline/unified_pipeline.py` are in the local checkout. Read only.
  - MEASURE (step 2) is POD and needs LIGHT GPU (EasyOCR). Gate on
    `nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader`
    showing free VRAM >= 2,048 MiB. NEVER stop, signal or interfere with
    `track_daemon`; read its pids from /proc; never kill. No git on the pod.
  - Disk: this row writes summaries only, so no `du` guard. Report
    `v=$(timeout 60 du -sm /workspace | cut -f1); [ -z "$v" ] && v=UNKNOWN`
    verbatim as CONTEXT and NEVER stop on UNKNOWN.

PREMISE (step 0, binding before-condition): S314's census
(`docs/evidence/harness/S314_census_pod_2026-09-07.jsonl`) reports
`scoreboard_game_clock` filled in **0 of 46,791 rows across 18 pod segments** and
`scoreboard_period` self-contradictory (periods 1-4 inside one ~152 s clip).
REPRODUCE the 0/N fill on TWO named pod games from
`data/tracking/<game>/tracking_data.csv`: print, per game, N (total rows), the
count of non-empty `scoreboard_game_clock`, the count of non-empty
`scoreboard_period`, the DISTINCT period values, and the clip duration in
seconds. If either game shows a non-zero clock fill, the premise is FALSIFIED --
STOP, write the memo, commit, report FALSIFIED. That is a valid result and earns
its own register row.

TRACE (step 1, read-only): name with `file:line` every producer of the two
fields. The known path, which you must confirm rather than assume:
`src/tracking/scoreboard_ocr.py:222` `read()` -> `_parse_scoreboard_text()`
(`:347`, `game_clock_sec` default `-1.0` at `:122`) -> the confidence-gated write
site `src/pipeline/unified_pipeline.py:2752-2768`, which emits `""` for the clock
whenever `_sb_conf < 0.3` and `""` for the period whenever OCR returned `-1`; and
the post-tracking pass `_backfill_scoreboard_period()` at
`src/pipeline/unified_pipeline.py:4282-4350`, whose docstring already states the
period is "~100% empty ... across production games" and which then fills EVERY
empty cell with a frame-percentile fallback
`quarter = max(1, min(4, int(frame / max_frame * 4) + 1))`. State plainly whether
that fallback -- not a scoreboard reading -- is what puts periods 1-4 inside a
152 s clip. If it is, the contradiction is EXPLAINED, and explaining it is the
deliverable; do not edit `src/`.

LIMIT (step 2a): sample 200 frames EVENLY SPACED (no head slice) from each of TWO
already-tracked 1080p pod broadcasts and count how many carry a visible
scoreboard graphic, by a DECLARED deterministic rule stated in the memo before
you run it. If fewer than 30 of the 200 frames in BOTH broadcasts show a
scoreboard, the corpus cannot support a clock reader: STOP and report CLOSED AT
LIMIT with the two counts. Do not fix.

CHANGE (step 2b, additive only): on the frames that DO show a scoreboard, run a
deterministic crop plus OCR and try to parse `MM:SS`. DECLARE the reader
(EasyOCR version, or the exact `src/tracking/scoreboard_ocr.py` entry point) and
record its per-frame confidence. Emit TWO new files under
`scripts/platformkit/tracking/` output: an ADDITIVE per-frame record
(`frame_index, scoreboard_present, crop_box, parsed_clock, parsed_period,
ocr_confidence, reader`) and a liveness SUMMARY JSON (per broadcast: frames
sampled, scoreboard-present count, parsed-clock count, parse rate, median
confidence). Renaming or removing any existing field, column or status value is
an automatic reject. Write NOTHING under `data/`, touch no ledger `passed` field,
change no threshold.

ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = parsed-clock rate = frames yielding a `MM:SS` parse / frames
                  whose `scoreboard_present` rule fired (per broadcast; both
                  denominators printed, zero-parse frames stay in the denominator)
  before        = the reproduced premise fill: 0 of N `scoreboard_game_clock`
                  cells on each of the two named pod games, N printed per game
  bar           = >= 90 pct parsed-clock rate on scoreboard-present frames, AND
                  every one of the 20 hand-checked frames whose hand-read clock
                  is within 1 s of the parsed clock, AND the period contradiction
                  explained with a `file:line`
  n             = 200 sampled frames per broadcast, 2 broadcasts (n = 400)
  eye check     = 20 renders EVENLY SPACED over the scoreboard-present frames of
                  the two broadcasts, clock read BY EYE and tabulated against the
                  parsed value; no head slice
  must not move = `src/**` byte-identical (SHA-256 before and after for
                  `src/tracking/scoreboard_ocr.py` and
                  `src/pipeline/unified_pipeline.py`); every existing
                  `tracking_data.csv` column and the ledger `passed` field
                  untouched; no file written under `data/`

NON-TAUTOLOGY: the metric covers frames the declared `scoreboard_present` rule
accepts and EXCLUDES frames it rejects. That exclusion is exactly where this row
can go circular: a rule tuned until only easily-read scoreboards survive makes
90 pct trivial. So the rule must be fixed and written down BEFORE the run, the
rejected-frame count must be printed, and the 20 eye-checked renders must be
drawn from the full 400-frame sample -- not only from accepted frames -- so a
scoreboard the rule missed is visible. If you cannot satisfy that, report REJECT
yourself. **A parsed clock is a READ, not a validated clock: this row makes NO
recall, precision, registration, tracking-quality or harness-pass claim, licenses
no `passed` flip, and does not make the two broadcasts usable for training.**

EVIDENCE: `docs/evidence/tracking/g316_scoreboard_clock_liveness_2026-09-07.md`
-- premise table (per game: N, clock fill, period fill, distinct periods, clip
seconds), the producer trace with `file:line`, the before/after table, n, both
denominators, the 20-render eye-check tally, and a "NOT VERIFIED" list. Copy the
per-frame record and the summary JSON under `docs/evidence/` too: a directory of
renders may stay local, but the numbers behind the renders must not. Preserve the
FULL column set in any re-emitted table. Memo <= 60 lines.

TEST: exactly one new per-file test,
`tests/platformkit/test_g316_scoreboard_clock_liveness.py`, over a SYNTHETIC
scoreboard construct (a generated frame with a drawn `MM:SS` at a known box, plus
a frame with no scoreboard). Assert: the present-rule fires on the first and not
the second; the parsed clock equals the drawn value; a frame with no scoreboard
contributes to the denominator and not the numerator. Run only that file:
`python -m pytest tests/platformkit/test_g316_scoreboard_clock_liveness.py -q
-p no:cacheprovider`. Never run a full pytest.

POD: heavy compute only; own `nohup setsid nice` job, unique /tmp log, never kill
anything, no git on the pod, and NO scp of any module until the verifier accepts.
Report the files you would deploy; do not deploy them.
COMMIT: explicit pathspec, in the worktree, no push. Report the sha.
NEVER PARK: poll your own jobs in a blocking loop; never end waiting.
