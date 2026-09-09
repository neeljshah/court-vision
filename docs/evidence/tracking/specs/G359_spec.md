GAP G359 | sport all (basketball fixtures first) | worktree aX | log cx_g359_held_position_vs_threshold

**HARNESS ROW, SUCCESSOR TO G358 (PARTIAL 2026-09-08: 8 of 11 gates clear at full length; three sit inside the
live distribution). Codex PREPARES, a finisher MEASURES.** `src/`, `kernel/`, `api/` and `intel/` are READ and
IMPORT only. Build in `scripts/platformkit/tracking/` beside `production_schema_adapter.py`, `image_space_gates.py`
and `g358_gate_execution.py` (G358, once landed). NEVER write `data/registry/`, never flip a flag, never MOVE a
sealed threshold (a candidate v2 threshold may be PREREGISTERED beside the sealed one, additively, never in its
place), never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** LOCAL (conda `basketball_ai`; batched per-section reads; `python -m` from the worktree
root) with READ-ONLY pod fetches of full tracking tables (ledger `game_id` matching per G358 fix 1b; never
write on the pod; never touch the daemon pid 1596016 or the guards).

**WHY THIS ROW EXISTS.** G358 (713413a96) measured on 6 sealed full sections that `zero_step_share` (median
0.889 vs sealed threshold 0.884), `distinct_position_ratio` (median 0.119 vs 0.109) and
`stationary_track_share` reject the UNCHANGED arm and classified them THRESHOLD_MISCALIBRATED. A competing
explanation is measured elsewhere: the broadcast-CV CSVs carry a HELD-POSITION defect (2026-09-01: 0.8658 of
rows repeat the previous position because the row builder writes every frame but positions update only on
evaluated ticks). If most steps are zero because rows are HELD between evaluated ticks, the gates are
reading a PRODUCTION_SCHEMA_ARTIFACT, not live footage, and the fix is an adapter mode that scores
evaluated ticks only, with no threshold move at all. This row decides which explanation holds.

**PREMISE (step 0, BINDING before-condition):** on the 6 G358 sealed sections, per section: rows n, unique
frames n, the share of consecutive same-track rows whose (x, y) is byte-identical to the previous row
(held share), and the evaluated-tick stride implied by the ledger (`seconds`, `rows`, fps). PRINT the table.
**If the held share is below 0.20 on every section (positions are not held), the premise is FALSE: the
gates read live motion; STOP, write the memo, commit, report PREMISE FALSE (the reseal question then
belongs to a threshold row).**

METHOD:
  1. **SEALED SET.** >= 12 full sections from >= 6 games (G346 LIVE or post-epoch; >= 150 unique frames) by
     ledger order, path + sha256 + rows + unique frames, sealed as its own commit before scoring.
  2. **ADAPTER MODE (`evaluated_ticks_only`, additive flag in `production_schema_adapter.py`, default OFF):**
     collapse consecutive same-track rows with identical (x, y) into the first row of the run (count the
     collapsed rows per track as `held_rows`), leaving every other row untouched; every output row keeps
     `scorable=False`; the flag value is stamped on every row (`adapter_mode`). Tests: a synthetic held
     sequence collapses to its evaluated ticks; a non-held sequence is unchanged; the default mode is
     byte-identical to G358's adapter output.
  3. **TWO ARMS on the sealed set, gates UNCHANGED:** M0 = adapter default (G358 behaviour); M1 = adapter
     `evaluated_ticks_only`. Per gate: A0 false rejection on full sections with Wilson 95 pct intervals (n =
     sections), and the three planted defects (frozen, id-merge, ball-shift) detection per arm (a defect
     planted BEFORE the collapse so the mode cannot hide it).
  4. **DECISION (sealed):** for each of the three gates, if M1 clears the sealed threshold on >= 90 pct of
     sections while M0 does not, class = PRODUCTION_SCHEMA_ARTIFACT (the adapter mode is the fix; no
     threshold move); if M1 still rejects >= 10 pct, class = THRESHOLD_MISCALIBRATED and the row PREREGISTERS
     a candidate v2 threshold at the M1 distribution's p95 on the sealed set as an ADDITIVE gate version
     (`<gate>_v2`, reported beside the sealed gate, never replacing it), to be scored by a later row on a
     fresh sealed set (never on this one).
  5. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** twelve sections are a screening; collapsing held rows changes
the denominators of every per-frame statistic (report both); the v2 thresholds are candidates, unscored
here; the ball-shift plant remains limited by ball detection coverage (G357: 18 pct of frames).

ACCEPTANCE RULE:
  metric        = the held-share table; the sealed list; per gate x arm false rejection with intervals;
                  detections per arm; the decision table with class per gate
  before        = G358: zero_step_share, distinct_position_ratio, stationary_track_share reject the
                  unchanged arm on full sections; cause unclassified between artifact and threshold
  bar           = >= 12 sections / >= 6 games; adapter tests pass and the default mode is byte-identical
                  to G358; both arms scored with unchanged gates; each of the three gates classified by
                  the sealed decision rule with n; detections >= 0.80 for frozen and id-merge in both arms
                  (ball-shift reported); 0 threshold moves; 0 src edits
  n             = >= 12 sections x 2 arms x 4 plants x every gate
  eye check     = NONE. Say that.
  must not move = `src/`, `data/`, `data/registry/`, every flag, every sealed threshold, every landed
                  artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** with the class per gate if the bar holds; **PARTIAL** naming what could not run;
                  **PREMISE FALSE** if positions are not held.
EVIDENCE: `docs/evidence/tracking/g359_held_position_vs_threshold_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g359_held_position_vs_threshold_2026-09-08/held_share.csv`,
`sealed_sections.csv`, `arms.csv`, `decision.csv` (integer cells zero-padded; shares as ADDITIVE per-mille
columns; never rename or remove a column). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (append only).
**Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g359_evaluated_ticks_mode.py` plus `tests/platformkit/test_g358_production_schema_adapter.py`
and `tests/platformkit/test_g353_image_space_gates.py`, each alone. **NEVER a full pytest.** Every new file
<= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the held-share rule, the collapse rule,
the decision rule, the v2 candidate rule), the adapter mode, the tests and the memo skeleton with the exact
fetch and run commands in `python -m` form, and exits with the line `agent: PREPARED FOR FINISHER`; it must NOT
run the real sections (Q1). Absent fixtures or `data/registry` in the worktree are reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
