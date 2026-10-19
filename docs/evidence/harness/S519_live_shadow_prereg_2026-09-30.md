# S519 -- sealed prereg for the live shadow mid vs blend cumulative calibration comparison

Row: S519 (docs/evidence/HARNESS_GAPS_2026-09-03.md). Spec: docs/evidence/tracking/specs/S519_spec.md + AMENDMENTS 1-3.
PAPER ONLY. Calibration language only (Brier, log-loss); fills and markouts are out of scope (S516).

## What landed
- scripts/platformkit/execution/live_shadow_prereg.py: body() = the sealed design, build() adds the seal,
  verify() = schema / seal / body / first-commit attestation (seal_provenance) / prereg_not_alone, CLI --write/--check.
- tests/platformkit/execution/test_live_shadow_prereg.py: cases 1-13 (construct; tmp git repos); 13 passed.
- verify refusals: prereg_missing / _unparseable / _schema / _seal_mismatch / _body_mismatch / _not_committed /
  _not_alone (git show --no-renames) / _rewritten (write-once: any second commit in the file's incarnation).
- The sealed artifact docs/evidence/forward/live_shadow/PREREG_S519.json is written by `--write` and committed
  ALONE by the lead AFTER this module lands; its first eligible game date is the seal commit's UTC date + 1.

## Code identity (AMENDMENT 1 (8))
The body pins the LF-normalised sha256 of blend_apply.py, live_shadow_quoter.py and mlb_live_model.py at master
13d304aa7 (equal to the run-row sha256 map of the recorder run started 2026-09-29 23:48Z, run_nonce 576a4eb1, read by the lead).
A later edit of any of those three files makes new runs `code_identity_changed` (excluded, counted); I/O files are free.

## NOT VERIFIED
- The reader/evaluator does not exist yet (after S503's interface); nothing is scored.
- Real yield: the first live run (2026-09-29 23:48Z onward) recorded 0 paired ticks by 00:00Z: 85 of 98 tick
  pairs were tail_window_miss (the 2 MiB books tail held only trade-backfill rows; row S559) and the blend arm was
  p0_missing on the rest (the recorder started after BOS@NYY's first live state).

## Notes (AMENDMENT 2 (f))
- A merge-commit seal refuses (fail-closed). Git dates are self-asserted: the lead records the push time of the seal
  commit to private/trunk next to its committer date. --path is absolute or relative to the cwd.
- The module is 185 LOC (spec said <= 150; the repo rule is 300): the sealed body text is long by design.
