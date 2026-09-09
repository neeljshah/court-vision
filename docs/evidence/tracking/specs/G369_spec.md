GAP G369 | sport basketball | worktree a19 | log cx_g369_prospective_identity

**PROSPECTIVE-IDENTITY ROW, SUCCESSOR TO G361 (PARTIAL 2026-09-09 17a175cc: 884 archived ids classified EXACT 19 /
ALIGNED 21 / UNKNOWN 844; re-fetch alignment <= 0.015 native frames on 21 sections; 8 sources unreachable;
`deploy_manifest_sha256` UNKNOWN for every archived row -- no archived table can be tied to the producer revision that
wrote it, and the corpus rotates within a day so bytes vanish before a join is proven). Astra day review 2026-09-09
section 5 seed G369. Codex PREPARES, a Claude finisher MEASURES on the pod; CPU only, zero GPU minutes.** `src/`,
`kernel/`, `api/`, `intel/` are READ and IMPORT only (the daemon and producer are never changed). Build additively in
`scripts/platformkit/tracking/g369_*.py` (import `g361_source_identity` / `g361_strips`; copy none). NEVER write
`data/registry/`, never flip a flag, never touch the register.

**WHERE THIS ROW RUNS:** ON THE POD, in `/workspace/wt/a19` (`python3 -m` from the worktree root); the live queue
`data/footage_bridge`, the retained `data/footage_corpus` and `data/tracking` are READ ONLY; the row's own pinning
store is under its evidence dir (never `data/`). Runs while sources are still on disk: the row PINS a section
(source bytes sha256, byte size, ffprobe fps / dims / first PTS, crop, the exercised route file digests and weight
digests at that moment, the ledger row) BEFORE the corpus rotates it away.

**PREMISE (step 0, BINDING before-condition):** re-read G361's `summary.json` / `ledger_links.csv` and PRINT the
class counts and the count of rows with a known `deploy_manifest_sha256` (expect 0 of 884). Then, on the live
ledger snapshot, count fresh sections (tracked on/after 2026-09-09T17:47Z) whose source mp4 is STILL on disk. **If
fewer than 10 fresh sections still have their bytes on disk, the premise is FALSE for the prospective part: STOP,
memo, commit, report (the row then only re-confirms the archival classes).**

METHOD (sealed before any number; additive to G361):
  1. **PIN (`sources.csv`, `attempts.csv`):** for >= 30 fresh sections / >= 10 games / 3 competitions (even sample
     over the eligible set, sealed rule; every attempt recorded, unreachable = ABSENT with the error text): the
     source sha256 and byte size, ffprobe codec / fps / dims / nb_frames / first PTS, the crop and pixel transform
     the producer applies (from the producer config, cited), the ledger row, and the exercised route + weight
     digests (`unified_pipeline.py`, `ball_detect_track.py`, `run_clip.py`, `yolov8n.pt`, `yolov8n_ball.pt`,
     `osnet_x0_25_imagenet.pth`) as `manifests.json` -- a binding that G361 could not reconstruct historically.
  2. **ALIGN (`alignment.csv`):** where a re-fetch join is used, >= 30 evenly spaced landmark evaluated ticks per
     section vs the archived table (bar <= 1 native frame), reusing G361's `align`; where the original bytes are
     still on disk, the join is EXACT by construction (state it).
  3. **REPEATABILITY (`export_hashes.json`):** run the manifest + alignment export TWICE on identical inputs; the
     two outputs must be byte-identical (sha256 both); any difference is reported line by line.
  4. **COLLISIONS:** zero (source id, offset) pairs claimed by two tables; unparseable ids reported separately.
  5. CHANGE NOTHING ELSE; no src hook; no flag; no daemon interaction.

ACCEPTANCE RULE:
  metric        = pinned sections / attempted; required bindings present per section (all fields); alignment
                  errors per landmark; export byte-identity; collisions; ABSENT list with reasons
  before        = G361: 0 of 884 archived rows with a producer binding; classes 19 / 21 / 844
  bar           = >= 30 fresh sections / >= 10 games / 3 competitions with 100 pct of the required bindings present
                  (or PARTIAL naming the count); 0 collisions; alignment <= 1 native frame at >= 30 landmarks where a
                  re-fetch join is used; two exports byte-identical; every attempted source counted
  n             = >= 30 sections (sampled evenly; CONSTRUCT if <= 40 eligible)
  eye check     = REQUIRED: 30 evenly spaced strips (G361 renderer) <= 200 KB
  must not move = the daemon, the producer, every archived table, all gates and flags, `data/registry/`
  verdict       = **DONE** / **PARTIAL** (name the missing binding or count) / **PREMISE FALSE** (part)
EVIDENCE: `docs/evidence/tracking/g369_prospective_identity_2026-09-09.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED;
wall time; SHA-256s) + `.../g369_prospective_identity_2026-09-09/sources.csv`, `attempts.csv`, `manifests.json`,
`alignment.csv`, `export_hashes.json`, `SHA256SUMS.txt`, `strips/`, `summary.json`. **ADD ONE RESULTS_LEDGER.md ROW
IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g369_prospective_identity.py` alone (a synthetic section pins every required field;
a missing field yields PARTIAL not a pass; two exports of one fixture are byte-identical; a duplicate (id, offset)
pair is a collision; the seal check). **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: codex prepares the prereg (sealed alone: the required binding fields, the even-sampling rule,
the landmark bar, the repeatability rule), the module, the test and the memo skeleton, exits `agent: PREPARED FOR
FINISHER` with `python3 -m` commands; the Claude finisher pins, aligns, exports twice and scores (Q1). Vocabulary
follows contract Q6; automated scan required. COMMIT: explicit pathspec only; prereg sealed as its OWN commit
first (`SEAL sha256 <hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-09
