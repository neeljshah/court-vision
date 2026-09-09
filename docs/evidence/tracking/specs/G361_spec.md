GAP G361 | sport basketball | worktree a1 | log cx_g361_source_identity

**IDENTITY ROW (astra plan 2026-09-09, critical-path item 1). Codex PREPARES, a Claude finisher MEASURES on the
pod.** `src/`, `kernel/`, `api/`, `intel/` are READ and IMPORT only. Build in `scripts/platformkit/tracking/`
(`g361_source_identity.py` + its test only). NEVER write `data/registry/`, never flip a flag, never edit an
archived tracking table or the ledger, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** ON THE POD, in `/workspace/wt/a1` (`python3 -m` from the worktree root; `data/tracking`
and `data/footage_bridge` are symlinks into `/workspace/data`; the daemon writes there -- READ ONLY for this row;
no `pod_run` exists any more). Heavy reads stream one table at a time (largest ball table 92 MB).

**WHY THIS ROW EXISTS.** The old corpus is gone and every future visual join re-fetches sections from YouTube
(same id + offset does NOT imply identical bytes or frame index: codec, seek rounding, rate and TOPCUT move the
alignment). The ledger has no start field and no source hash; tables carry no source sha256 / PTS binding; the
`_s<offset>` suffix can alias different fetched offsets. Without an identity map every G360/G362/G363 join and
every teacher split is unverifiable (pre-mortem items 2 and 5).

**PREMISE (step 0, BINDING before-condition):** census the ledger (`game_id, finished_at, seconds, rows,
decoded_frames, evaluated_frames, stride, source_duration, probe_status`) and every `<game_id>/tracking_data.csv`
header for a source hash / PTS / crop / timebase field. PRINT the counts. **If >= 95 pct of rows already carry a
complete source binding (sha256 + first PTS + fps + dimensions + crop), the premise is FALSE: STOP, memo, commit,
report PREMISE FALSE.**

METHOD (additive; zero archival edits):
  1. `sources.csv`: one row per bridge/corpus file the finisher can still read: `video_id, requested_start_s,
     requested_end_s, actual_first_pts, fps, width, height, topcut_px, source_sha256, bytes, fetch_utc, format_id`.
  2. `ledger_links.csv`: one row per ledger `game_id`: `table_sha256 (tracking_data.csv), ball_table_sha256,
     deploy_manifest_sha256 (deployed producer digests at run time if recorded, else UNKNOWN), run_start_utc =
     finished_at - seconds, join_class in {EXACT, ALIGNED, UNKNOWN}` -- EXACT = source bytes present and hash-bound;
     ALIGNED = same id/offset, bytes unavailable, alignment proven by `alignment.csv`; UNKNOWN otherwise.
  3. `alignment.csv`: for >= 30 sections across >= 10 games (EVEN sample over the eligible set, never a head
     slice; archive the census fields that decided eligibility): re-fetch the section on the pod, decode, and
     compare >= 30 evenly spaced landmark frames against the archived table's evaluated ticks (frame index of the
     first evaluated tick, per-landmark temporal error in native frames). Bar per section: <= 1 native frame.
  4. `summary.json`: counts per join_class, collisions (two tables claiming one source/offset), unreadable tables.
  5. CHANGE NOTHING ELSE.

ACCEPTANCE RULE:
  metric        = classified mappings / all ledger rows (100 pct classified); collisions; proven ALIGNED sections
  before        = no source binding on any archived table (the premise counts)
  bar           = 100 pct rows classified; 0 silent collisions; >= 30 sections / >= 10 games proven EXACT or
                  ALIGNED at <= 1 native frame; every UNKNOWN stays UNKNOWN with a reason (never inferred exact)
  n             = all ledger rows (CONSTRUCT) + >= 30 sections (sampled, even)
  eye check     = REQUIRED: 30 evenly spaced alignment strips (archived tick vs re-fetched frame) <= 200 KB each
  must not move = the daemon, the ledger, every archived table, all gates and flags, `data/registry/`
  verdict       = **DONE** / **PARTIAL** (name what could not be proven) / **PREMISE FALSE** with the counts
EVIDENCE: `docs/evidence/tracking/g361_source_identity_2026-09-09.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED;
wall time; SHA-256s) + `.../g361_source_identity_2026-09-09/sources.csv`, `ledger_links.csv`, `alignment.csv`,
`summary.json`, `strips/`. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (append only).
TEST: `tests/platformkit/test_g361_source_identity.py` alone (synthetic ledger + two tables: EXACT / ALIGNED /
UNKNOWN classification; collision detection). **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: codex prepares the prereg (sealed alone: join classes, even-sampling rule, <= 1 frame bar,
landmark rule), the module, the test and the memo skeleton, exits `agent: PREPARED FOR FINISHER` with `python3 -m`
commands; the Claude finisher re-fetches, aligns, fills the CSVs and scores (Q1). Vocabulary follows contract Q6;
automated scan required. COMMIT: explicit pathspec only; prereg as its OWN commit first (`SEAL sha256 <hex>` over the
LF-normalised bytes above it). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-09
