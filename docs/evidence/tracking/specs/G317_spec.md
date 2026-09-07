GAP G317 | sport all | worktree aXX | log g317_segment_source_metadata
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check
against every line of section B before you report.
**ADDITIVE ONLY. `src/`, `domains/` and `api/` are READ and IMPORT ONLY. The fix
belongs in `scripts/platformkit/` (a safe area). If the defect turns out to sit
inside `src/`, write a PROPOSED diff under `docs/research/organization-sprint/`
and STOP -- a human applies it. Adopt nothing. Flip no flag.**

WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):
  - PREMISE (step 0) is POD: the `track_daemon` ledger JSONL lives on the pod.
    Use `~/bin/pod_run <aN> --fetch <the premise summary JSON> -- python -m
    scripts.platformkit.tracking.g317_segment_source_metadata --premise`.
    ONE job. Poll to POD_RUN_DONE. NO GPU: this step reads JSONL only.
  - TRACE (step 1) is LOCAL: `scripts/platformkit/track_daemon.py` and
    `scripts/platformkit/tracking/source_timebase.py` are in the checkout.
  - BACKFILL (step 3) is POD (it re-probes segment video files) and needs NO GPU;
    `ffprobe` is CPU. Gate on the `dd conv=fsync` probe passing, because this
    step WRITES a sidecar. CPU gate: load15 (field 3 of /proc/loadavg) below
    `nproc`. NEVER stop, signal or interfere with `track_daemon`; read its pids
    from /proc; never kill. No git on the pod.
  - Disk: report `v=$(timeout 60 du -sm /workspace | cut -f1);
    [ -z "$v" ] && v=UNKNOWN` verbatim as CONTEXT and NEVER stop on UNKNOWN.
    Stop only on a failed `dd conv=fsync` probe.

PREMISE (step 0, binding before-condition): S314's census
(`docs/evidence/harness/S314_teach_packet_census_2026-09-07.md:41-43`) found
`source_fps` / `source_height` / `source_duration` EMPTY for segment
`0022500575_s1500` while present for its siblings. REPRODUCE on the pod: over
EVERY segment row in the `track_daemon` ledger, print the count with at least one
of the three fields absent-or-null, the total segment-row count, and the list of
affected `game_id`s. If the count is 0, the premise is FALSIFIED -- STOP, write
the memo, commit, report FALSIFIED. That is a valid result and earns its own
register row.

TRACE (step 1, read-only): name with `file:line` where the three fields are
produced and written. The known path, which you must confirm rather than assume:
`scripts/platformkit/track_daemon.py:387` stamps `"source": probe_source(path)`
at CLAIM time; `:307-310` writes the three fields into the ledger entry only
`if source:`; `:238-240` stamps the same dict into `tracking_data.csv`. The
producer `probe_source()` at
`scripts/platformkit/tracking/source_timebase.py:11-30` uses `cv2.VideoCapture`,
NOT `ffprobe`, and returns all-None when the backend cannot open the file or
reports `fps <= 0` / `frame_count <= 0`. State whether the ledger can today
distinguish "never probed" from "probe failed". (Landmine, 2026-09-02: a pod
rebuild pulling `opencv-python-headless` 5 silently emptied every tracking table.
Print the pod `cv2.__version__` in the memo -- an all-None probe from a cv2
version bump is a DIFFERENT defect from an unreadable file, and this row must say
which one it measured.)

CHANGE (step 2, additive only, safe area): add an `ffprobe` fallback INSIDE
`probe_source()` -- when the cv2 read yields a null for any of the three fields,
call `ffprobe -v error -show_streams -show_format -of json` and fill from the
container metadata -- plus one NEW additive key `source_probe` recording which
route produced the values (`cv2` / `ffprobe` / `none`). Every existing key keeps
its name and its value on the cv2-success path. Renaming or removing an existing
field, column or status value is an automatic reject. Name every reader of
`probe_source()` you checked.

BACKFILL (step 3, additive only): a script that re-probes the affected segments
and writes the recovered values to a NEW sidecar JSONL keyed by `game_id`.
**DO NOT REWRITE HISTORICAL LEDGER ROWS.** The ledger is append-only; earlier
whole-file rewrites destroyed 17 rows across 9 gap ids. A segment counts as
covered when the UNION of (its ledger row, the backfill sidecar) carries all
three fields. Segments whose source video is no longer on the pod cannot be
re-probed -- that count is the LIMIT of this row, and you report it rather than
working around it. Write NOTHING under `data/`; touch no ledger `passed` field.

ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = segments with all three of `source_fps` / `source_height` /
                  `source_duration` present, denominator = EVERY segment row in
                  the pod `track_daemon` ledger (no row excluded)
  before        = the reproduced premise count of segments missing at least one
                  field, with the total row count printed
  bar           = 0 segments with empty source metadata among those whose source
                  video still exists on the pod; segments whose video is gone are
                  reported separately BY COUNT AND `game_id` as the LIMIT, not
                  silently dropped from the denominator
  n             = every segment row in the ledger (CENSUS, not sampled); print it
  eye check     = n/a (no frames in this row); reproduction = a second,
                  independent `ffprobe -show_streams` run on 3 named backfilled
                  segments returns byte-identical values for the three fields
  must not move = every pre-existing ledger key byte-identical (diff the ledger
                  with `git`-style numstat or a line-count check showing 0
                  deletions); the `passed` field untouched; the claim/retry
                  lifecycle in `scripts/platformkit/track_daemon.py` unchanged;
                  `src/**` byte-identical (SHA-256 before and after)

NON-TAUTOLOGY: the metric covers EVERY segment row in the ledger and excludes
none. The one legitimate exclusion -- segments whose video file is gone -- is the
row's LIMIT and must be reported with its count and its ids, because moving those
rows out of the denominator is exactly what would make the number look complete
when it is not. If you find yourself excluding any other row to reach the bar,
report REJECT yourself. **Filling a metadata field is NOT a tracking improvement:
this row makes NO recall, precision, coverage, registration, tracking-quality or
harness-pass claim, and licenses no `passed` flip.**

EVIDENCE: `docs/evidence/tracking/g317_segment_source_metadata_2026-09-07.md` --
premise table (missing count / total / affected ids), the producer trace with
`file:line`, the pod `cv2.__version__`, the before/after table, n, the
re-probe reproduction on 3 named segments, the LIMIT count, and a "NOT VERIFIED"
list. Copy the premise summary JSON and the backfill sidecar under
`docs/evidence/`: a directory of artifacts may stay on the pod, but the numbers
behind the claim must not. Preserve the FULL column set in any re-emitted table.
Memo <= 60 lines.

TEST: exactly one new per-file test,
`tests/platformkit/test_g317_segment_source_metadata.py`, over a CONSTRUCT that
never touches a real video: (a) cv2 succeeds -> output byte-identical to today's
three values and `source_probe == "cv2"`; (b) cv2 yields nulls and ffprobe
returns metadata -> the three fields filled and `source_probe == "ffprobe"`;
(c) both fail -> all three stay None, `source_probe == "none"`, and no exception
escapes. n = 3 (CONSTRUCT) -- every case enumerated. Run only that file:
`python -m pytest tests/platformkit/test_g317_segment_source_metadata.py -q
-p no:cacheprovider`. Never run a full pytest.

POD: CPU only; own `nohup setsid nice` job, unique /tmp log, never kill anything,
no git on the pod, and NO scp of any module until the verifier accepts. Report
the files you would deploy; do not deploy them.
COMMIT: explicit pathspec, in the worktree, no push. Report the sha.
NEVER PARK: poll your own jobs in a blocking loop; never end waiting.
