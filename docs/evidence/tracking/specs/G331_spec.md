GAP G331 | sport all | worktree a6 | log cx_g331_evaluated_frames_sidecar

**TOOLING ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and IMPORT only --
`src/pipeline/unified_pipeline.py` is HUMAN-GATED (PROPOSED diff only). Build in `scripts/platformkit/`.
NEVER edit a committed evidence hash, a committed evidence artifact,
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`, or any threshold.**

**WHERE THIS ROW RUNS:** LOCAL for code, tests and the recomputation; the pod is READ-ONLY (`ssh -F
~/.ssh/config.pod pod`; never stop/signal/restart `track_daemon` or `vol_guard.py`; never write on the pod).
No GPU. No video decode beyond one local 130 s section if the sidecar producer must be exercised end to end
(copy it from the pod corpus, delete it afterwards, peak RSS under 1.5 GB -- the local RAM guard kills at 99 pct).

**WHY THIS ROW EXISTS.** The production route writes `evaluated_frame_count.json` with
`evaluated_frames: null` and the reason `max_frames_is_detector_dependent_in_this_route` (G310 attempt 2,
all 10 runs), so every rows-per-frame denominator in the tracking evidence falls back to
`frames_with_rows`, which is NOT the decoded-frame count and silently inflates rows-per-frame on frames
the detector emitted nothing for. The G310 verifier also found two reader defects:
`scripts/platformkit/tracking/g310_instance_key.py:80` treats an explicit `evaluated_frames = 0` as absent
(must use `is not None`), and `g310_native_input_arm.py:32-37` labels a rounded-index percentile as
nearest-rank. G149 and G153 earlier tried to persist a decoded denominator; `test_g149_persist_decoded_denominator.py`
is RED on master (a TypeError on an unexpected keyword argument named publish) -- state that, and
say whether this row's sidecar supersedes G149's or feeds it.

**PREMISE (step 0, BINDING before-condition):** open the committed G310 sidecars
(`docs/evidence/tracking/g310_attempt2/**` and the attempt-1 archive) and PRINT, per run, `evaluated_frames`
and `reason`. **If any committed sidecar carries a non-null `evaluated_frames`, the premise is PARTIALLY
FALSE: report the counts (null vs non-null, n) and continue only for the null cases.**

METHOD:
  1. **PRODUCER TRACE (read-only).** Cite with `file:line` where the route writes the sidecar, where
     `max_frames` is decided, why the count is null in this route, and what the three candidate
     denominators are at that point in the code: DECODED (frames read from the container), EVALUATED
     (frames handed to the detector after stride/cap), EMITTED (frames with >= 1 row). Define the
     denominator contract in one table (name, meaning, where it is knowable, which proxies use which).
  2. **HARNESS-SIDE SIDECAR (additive).** Under `scripts/platformkit/tracking/`, a writer that records
     `decoded_frames`, `evaluated_frames`, `emitted_frames`, `stride`, `frame_cap`, `source_frames`
     (ffprobe `nb_frames` or duration x fps, say which) and `producer_version` next to the route output,
     fed from the route's own counters where they exist and from the tracking CSV where they do not
     (say which field came from where). New fields only; the existing sidecar keys keep their names and
     meanings (B2). If the true EVALUATED count is only knowable inside `unified_pipeline.py`, write the
     PROPOSED 3-5 line diff under `docs/research/organization-sprint/G331_PROPOSED_evaluated_frames.md`
     (gitignored, local-only: carry its sha256 in the memo) and have the harness sidecar record
     `evaluated_frames: null` with `reason` verbatim from the route -- never a guessed number.
  3. **READER FIXES.** `g310_instance_key.py:80` -> `is not None`; the percentile at
     `g310_native_input_arm.py:32-37` -> a correctly labelled nearest-rank (or keep the rounded index and
     relabel it -- say which, and show the p95 values before/after on the archived G310 columns).
  4. **THE CHECK.** Recompute the G310 attempt-2 rows-per-frame table from the archived columns under
     `docs/evidence/tracking/g310_attempt2/` with each denominator (EMITTED as archived; DECODED and
     EVALUATED where the archived columns or ffprobe of the surviving section allow; NOT KNOWABLE where
     they do not), n per cell. Report how much the EMITTED denominator inflates rows-per-frame versus the
     best available true denominator, per run.
  5. **CHANGE NOTHING ELSE.** No threshold, no committed hash, no register edit, no `src/` edit, no
     adoption, no daemon interaction.

**HONEST LIMITATIONS to state, not discover:** a denominator recorded by the harness after the fact is a
reconstruction, not the producer's count; the route's null stays null until the PROPOSED diff is applied
by a human; this row measures no recall, precision or registration.

ACCEPTANCE RULE:
  metric        = the producer trace with `file:line`; the denominator contract table; the sidecar writer
                  + test; the two reader fixes with before/after; the recomputed G310 rows-per-frame
                  table with every denominator and n
  before        = every committed G310 sidecar has `evaluated_frames: null`; rows-per-frame uses EMITTED
                  frames; `evaluated_frames = 0` reads as absent; the percentile label is wrong
  bar           = the trace names the producer line (not guessed); every new field is additive; the two
                  reader defects are fixed with tests; every cell of the recomputed table carries its
                  denominator name and n or the words NOT KNOWABLE
  n             = every committed G310 sidecar (exhaustive; Q7); the G310 attempt-2 archived runs
  eye check     = NONE. Say that.
  must not move = `src/`, `domains/`, `api/`, `kernel/`, `intel/`; every committed artifact and hash;
                  `data/`; anything on the pod; the running daemon and guard;
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/tracking/g331_evaluated_frames_sidecar_2026-09-08.md` (<= 60 lines) with VERDICT
on line 1, the trace, the contract table, the recomputed table, a **NOT VERIFIED** list, wall time and the
SHA-256s; plus `docs/evidence/tracking/g331_evaluated_frames_sidecar_2026-09-08/rows_per_frame.csv`
(integer cells zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>`
append). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g331_evaluated_frames_sidecar.py` -- the sidecar writer round trip, the
`is not None` read of an explicit 0, the percentile on a hand-pinned construct. Run that ONE file and the
existing test file of every touched module (`scripts/platformkit/tracking/test_g310_native_input_arm.py`,
`tests/platformkit/test_g310_instance_key.py`). **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
