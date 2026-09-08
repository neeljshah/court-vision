# G317 segment source-metadata completeness -- 2026-09-07

VERDICT: **PREMISE FALSIFIED**. Over EVERY segment row in the pod `track_daemon` ledger, **0 rows are
missing any of `source_fps` / `source_height` / `source_duration`**. Per `docs/evidence/tracking/specs/G317_spec.md:30-33`
("If the count is 0, the premise is FALSIFIED -- STOP, write the memo, commit, report FALSIFIED") and contract Q8,
this row closes with NO code change, NO backfill, NO test and NO flag flip. Calibration language only: no
tracking-quality, coverage, registration or harness claim is made or licensed, and no `passed` field was touched.

## Premise, re-measured (CENSUS, not sampled)
Ledger (S4): pod `/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl` -- the only
`*track_daemon*ledger*` file on the pod. MISSING = any of the three absent-or-null. Segment = `game_id` =~ `^.+_s\d+$`.

Three independent reads on 2026-09-07 (23:34 / 23:37 / 23:39): ledger rows 56 / 58 / 58, segment rows
25 / 25 / 25, segment rows missing >=1 field **0 / 0 / 0**, ALL ledger rows missing >=1 field 0 / 0 / 0.
n = 25 segment rows of 58 ledger rows; no row excluded. Affected `game_id` list: **EMPTY**. Malformed lines: 0.
The corpus is LIVE (the daemon appended 2 rows between reads 1 and 2); 0 held on all three reads. LIMIT
(segments whose source video is gone): **0 of 25** -- every ledgered segment still has its mp4 under
`data/footage_corpus/` or `data/footage_bridge/`, so nothing was moved out of the denominator.

The spec's cited source, `docs/evidence/harness/S314_teach_packet_census_2026-09-07.md`, states the OPPOSITE for
this segment: "Set B -- the 3 pod official ids: ... declared source PTS yes (`source_fps` 29.97002997002997,
`source_height` 360, `source_duration` 151.08 s)". S314's empty-metadata finding is a DIFFERENT artifact -- the 19
API-complete LOCAL `data/tracking/<gid>/tracking_data.csv` on the old producer schema ("Declared source PTS: 0 of
19"). G317's spec transferred that onto the pod ledger, where it does not hold.

## Reproduction (independent of cv2, of the ledger, and of itself)
`ffprobe -v error -show_streams -show_format -of json`, run TWICE per file on the pod; all three `run_1 == run_2`.

| game_id | mp4 bytes / sha256 head | ledger fps / height | ffprobe fps / height | agree |
|---|---|---|---|---|
| 0022500575_s1500 | 13,632,393 / f59744c4 | 29.97002997002997 / 360 | 29.97002997002997 / 360 | yes |
| 0022500575_s2100 | 10,826,546 / d8f2f64e | 29.97002997002997 / 360 | 29.97002997002997 / 360 | yes |
| 0022500575_s2700 | 13,263,966 / bc75ad6d | 29.97002997002997 / 360 | 29.97002997002997 / 360 | yes |

`source_duration` also agrees on the STREAM: the ledger stores cv2 `frame_count / fps`, and
`ledger_duration * ledger_fps` reproduces ffprobe `nb_frames` exactly (4652, 3955, 4559). Container
`format.duration` is 1.87-5.17 s shorter -- a container-vs-stream definitional difference on all three, not this
row's metric.

## Trace (read-only, confirmed not assumed)
- `scripts/platformkit/tracking/source_timebase.py:11-30` `probe_source()` reads via `cv2.VideoCapture`; all-None at `:16-18` when the backend cannot open the file.
- `scripts/platformkit/track_daemon.py:387` stamps `"source": probe_source(path)` at CLAIM time; `:307-310` writes the three fields into the ledger entry under `if source:`; `:238-240` stamps the same three into `tracking_data.csv` at completion.
- Readers of `probe_source()` checked (A5): `track_daemon.py:32`; `track_daemon_sources.py:9` (`_ranking()` `:59-64`, `.get()`-tolerant of None); `tracking/tennis_sequential_plan.py:14`. `tracking/g296a_extract_frames.py:38` is an unrelated same-named local function.
- **Latent gap, NOT a defect today (0 occurrences in 58/58 rows):** the ledger CANNOT distinguish "never probed" from "probe failed" -- `probe_source()` always returns a truthy 5-key dict, so `if source:` at `:307` is always true and both cases would appear as identical nulls. Candidate register row; not fixed here.
- Pod `cv2.__version__` = **4.14.0**, so the 2026-09-02 opencv-5 landmine is NOT in play; no all-None probe was measured at all.
- Code identity (A11): `source_timebase.py` LF-normalized SHA-256 `b16f74a94c3ce968e3909567dbf319df24837badf71b2d36253d3a897120be13` -- IDENTICAL pod and worktree. Pod `track_daemon.py` `204a8920...`, `track_daemon_sources.py` `f9dc8626...`.
## Context measured, outside the premise
4 of 26 pod segment `tracking_data.csv` lack the three COLUMNS: `0022500575_s3900`, `0022500575_s8700`,
`0022500594_s8700`, `0022500630_s1500`. All 4 have **0 ledger rows** and their mp4 is still staged in
`data/footage_bridge/` -- they are IN FLIGHT, and `stamp_tracking_csv` runs only at completion
(`track_daemon.py:238-240`). Daemon lifecycle, not a probe failure, and outside the spec's ledger denominator.
## Artifacts
`docs/evidence/tracking/g317_premise_census_2026-09-07.json` (ledger + CSV + code identity) and `g317_ffprobe_reproduction_2026-09-07.json` (two-run ffprobe), both in this commit. Ledger snapshot at read 2: sha256 `5024ce9dd03f9f6ee6afbf560145e0ad64e31c74e95ee997653c25781299acf6`, 62,308 bytes.

## NOT VERIFIED
- No change was made, so nothing was preregistered, no bar was scored, no test added: the spec's CHANGE / BACKFILL / TEST steps are unreached by construction.
- The "never probed vs probe failed" ambiguity is inferred from code reading; NOT exercised, because no ledger row exhibits it.
- The 1.87-5.17 s container-vs-stream duration gap is reported, not adjudicated.
- Nothing was written, moved, stopped or deployed on the pod; `track_daemon` was read from `ps` only, never signalled; no file was copied to the pod (B5).
- Local (non-pod) ledgers and the 19 local old-schema CSVs S314 actually found empty were not re-measured; different denominator, own row.
