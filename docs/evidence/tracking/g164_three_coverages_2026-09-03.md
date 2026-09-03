# G164: `coverage_pct` is three different metrics, and the one that gates is never written down

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), sections A (A2, A7) and
B. Measured by the orchestrator on 2026-09-03 while the codex backend was
returning 404 and no lane could run. **Nothing here changes a threshold, a bar, a
gate, the decoded-frame denominator, the coverage definition, or any verdict.**
Every number below was recomputed from the code and from a real artefact.

## Why this was looked at

An adversarial review of the session's own conclusions named this as the most
important question nobody had asked: *which coverage denominator produced each
historical number?* G147 has been blocked since 2026-09-02 waiting for a
"two-column current-versus-corrected coverage comparison". The finding is that
the premise of that framing is wrong. There are not two columns. There are
**three quantities**, two of them sharing the name `coverage_pct`, and the one
that actually decides PASS or FAIL is not persisted anywhere.

## The three quantities

**1. Ledger `coverage_pct` -- emitted-frame PRESENCE over decoded frames.**

`track_daemon_done.adjudicate` sets `coverage = manifest.summary.completeness`
and writes that into both the verdict sidecar and the ledger row. From
`decode_manifest.py:150-159`, a decoded frame is `SOLVED` when its index appears
in the emitted set at all, and

    completeness = counts[SOLVED] / (counts[SOLVED] + counts[UNSOLVED])

**This does not consult `min_players`, `cls`, or any position.** One row of any
kind in a frame makes that frame count. It is a frame-presence rate.

**2. Harness coverage on the DAEMON path -- min_players over decoded frames.**

`tracking_harness.py:251` computes

    coverage = (per_frame >= cfg["min_players"]).sum() / n_frames

where `per_frame` counts distinct player track ids per frame. On the daemon path
`track_daemon_done._with_decoded_denominator` first pads the frame with a filler
row for every missing decoded index, so `n_frames` becomes the decoded count.
**This quantity is what decides `passed`.** It is never written to the ledger,
never written to the sidecar, and is discarded when `adjudicate` returns.

**3. Harness coverage on ANY DIRECT call -- min_players over emitted frames.**

Every census, every lane, every hand check calls `evaluate(df, sport)` on an
unpadded frame, so `n_frames` is the emitted frame count. Same formula as (2),
different denominator, and it is the number the whole program has been reading.

## Reproduction on a real artefact

The pod's first completed job, `mlb_2026-08-30_10893dca`. Ledger row:
`rows = 32380`, `decoded_frames = 39035`, `coverage_pct = 0.1565`, `seconds = 296`.

Recomputed directly from `tracking_data.csv` on the pod:

    rows 32380   distinct_emitted_frames 6109
    6109 / 39035 = 0.1565

Exact match. So the ledger's `coverage_pct` is confirmed as quantity (1): 6,109
of 39,035 decoded frames emitted at least one row, at about 5.3 rows per emitted
frame. It says nothing about whether those frames had two players, and it did not
gate anything.

The same divergence, seen from the other end, on `G83_tennis_09`:

    evaluate(df, "tennis") -> passed=True  n_frames=38  coverage_pct=1.0

Quantity (3) on a table of 38 emitted frames spanning source frames 0-74. A
perfect 1.0 that means only "every frame we emitted, we emitted".

## What follows

- **G147's blocker was mis-stated.** It has been described as needing a
  denominator that no eligible table carries. The sharper statement is that the
  gating quantity (2) is computed and then thrown away on every job, so it cannot
  be compared against anything after the fact for ANY row, denominator or not.
- **Ledger `coverage_pct` must not be read as the gate's coverage.** They are
  different metrics, not the same metric at two scales. A row can have a low
  `coverage_pct` and still pass, or a high one and fail.
- **Every historical coverage figure needs its producer named.** Under Q9 a
  result that cannot be recomputed from its artefact is not a result, and today
  an artefact carrying `coverage_pct` does not record which of the three
  quantities it holds.

## What is NOT claimed

- **No fix, no bar change, no rename.** Persisting quantity (2) alongside (1)
  would be additive and is the obvious candidate, but it is not landed, not
  designed here, and every reader of `coverage_pct` would need the A5 survey
  first. B2 applies: no field may be renamed or removed.
- **No audit of historical figures.** How many committed coverage numbers came
  from which path is unmeasured; that is the lane this row justifies, not a
  result this row delivers.
- Quantity (1)'s treatment of `non_play` frames was read from the code and not
  exercised: no classifier is passed on the daemon path, so `non_play` is 0 and
  `in_play` equals `decoded` on every row observed today. Whether any caller
  supplies a classifier is unchecked.

## NOT VERIFIED

- Any historical `coverage_pct` in `docs/evidence/tracking/` traced to its
  producing path.
- Whether the sidecar's `coverage_pct` and the ledger's ever disagree.
- The `non_play` path, per above.
- That quantity (2) is discarded on every code path rather than the two read
  here (`adjudicate` and direct `evaluate`).
