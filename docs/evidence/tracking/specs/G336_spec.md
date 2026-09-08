GAP G336 | sport basketball | worktree a21 | log cx_g336_track_id_continuity

**MEASUREMENT + HARNESS ROW (src edits authorized by the user 2026-09-08, but this row proposes; it
changes the production tracker only through a flag that defaults OFF).** The production tracker keeps 10
reusable roster slots (`player_id` 1-10, `unified_pipeline.py` ~:4352-4357); G310 attempt 2 measured that
on 40-frame windows those 10 slots resolve to 134-559 distinct track instances per run, i.e. an id is
reassigned every few frames. Downstream analytics (possessions, player props, lineup context) need
continuity, not slots. This row measures fragmentation without labels and evaluates one association
change behind a flag. NEVER write `data/registry/`, never flip a flag, never claim an edge, never touch
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` or any threshold.

**WHERE THIS ROW RUNS:** pod CPU/GPU scratch under `/workspace/wt/a21/` (never touch `track_daemon` or
the guards 1039858 / 1519254; GPU only under the 8,192 MiB lease rule; never write under
`/workspace/nba-ai-system`) or locally with peak RSS under 1.5 GB (the RAM guard kills at 99 pct; this
box has more than one interpreter -- print the version line). Sections: 4 from different broadcasts
(fixed stride from a sealed offset, >= 60 frames each); never commit video.

**PREMISE (step 0, BINDING before-condition):** on the 4 sections through the production tracker,
compute per run: distinct slot ids (expect 10), distinct track instances by G310's instance key
(`scripts/platformkit/tracking/g310_instance_key.py`: gap <= G frames, step <= J * height), median
instance length in frames, and the fragmentation ratio instances / (frames x 10). PRINT the table with
n. **If the median instance length exceeds 40 frames on 3 of 4 sections, the premise is FALSE: STOP,
write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **TRACE.** Cite the association step (`src/tracking/advanced_tracker.py`: Kalman + Hungarian, cost,
     gating, MAX_LOST; and how OSNet re-ID at `src/tracking/osnet_reid.py` is or is not used in the
     daemon route) with `file:line`. Name what forces reassignment (slot cap of 10 with > 10 people in
     frame after G337-style non-players; gating too tight for fast motion; lost-track eviction).
  2. **LABEL-FREE METRICS (the bar).** Per section: (a) fragmentation ratio; (b) median and p90 instance
     length; (c) identity-switch proxy = count of frames where two instances swap positions (an instance
     ending within 3 px of where another starts on the next frame); (d) appearance consistency = mean
     cosine similarity of OSNet embeddings within an instance vs. between instances (if OSNet is
     importable; else colour-histogram similarity, say which); (e) share of frames with > 10 people
     detected before any gate.
  3. **ONE CHANGE, BEHIND A FLAG.** Implement in `scripts/platformkit/tracking/` (harness) an association
     variant and, only if it wins, a <= 15-line hook in the tracker behind `TRACK_ASSOC_V2=0` (default
     OFF): the simplest candidate that addresses the named cause -- e.g. a two-stage association
     (high-confidence boxes first, then low, ByteTrack-style) plus appearance cost from OSNet embeddings
     with a gating threshold fixed in the prereg, and no slot cap during association (slots assigned
     after). State the design in the prereg with every parameter; one sensitivity pair allowed.
  4. **BEFORE/AFTER** on the same frames, same detector output (record the detector boxes once and feed
     both trackers; the ONLY difference is association): all five metrics with n. Also the runtime cost
     per frame (ms) for both.
  5. CHANGE NOTHING ELSE; no default moves.

**HONEST LIMITATIONS to state, not discover:** no identity ground truth exists; fewer, longer instances
can also mean wrong merges -- (c) and (d) are the checks; four sections are a screening; OSNet
embeddings on 720p crops are weak for same-team players.

ACCEPTANCE RULE:
  metric        = the premise table; the trace; the before/after table (a)-(e) + ms/frame with n
  before        = 10 slots resolve to 134-559 instances per 40 frames; no appearance term in the daemon
                  route's association (confirm or refute from code)
  bar           = the variant reduces the fragmentation ratio by >= 30 pct on >= 3 of 4 sections WITHOUT
                  raising the switch proxy (c) or lowering within-instance appearance similarity (d) on
                  those sections; runtime <= 2x; the hook (if added) defaults OFF and is tested
  n             = 4 sections x >= 60 frames; every box
  eye check     = OPTIONAL: one 20-frame strip per section with ids coloured (<= 300 KB), illustrative
  must not move = `data/`, `data/registry/`, every flag default, the pod daemon and guards, every
                  committed artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **MEASURED -- BAR MET** / **MEASURED -- BAR NOT MET** (with the failure mode);
                  PARTIAL only if a section could not be scored.
EVIDENCE: `docs/evidence/tracking/g336_track_id_continuity_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g336_track_id_continuity_2026-09-08/metrics.csv` and the
per-instance CSV (<= 5 MB; integer cells zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE
SAME COMMIT** (one `>>` append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g336_track_id_continuity.py` (metrics on a hand-pinned synthetic track set;
the association variant on a construct where the slot cap forces a reassignment) plus the existing test
file of every touched module, each alone. **NEVER a full pytest.** Every new file <= 300 lines.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
