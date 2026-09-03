# G173 -- first tennis ledger row

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), with the required
section-B self-check. This is an evidence-only, one-time, read-only pod
census. It did not stage, copy to the pod, deploy, run the adapter, restart,
or kill any pod process.

## Q8 premise re-measurement

The prior premise (zero tennis ledger rows) is **FALSIFIED**. The final
literal-safe, batched read of
`/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl` found
**16 physical ledger rows**, of which the exhaustive construct denominator is
**1 tennis ledger row**:

```text
game_id='tennis_ref01' rows=1861 decoded_frames=28773 coverage_pct=0.0252 seconds=223 passed=False failure_heads=['duplicate frame-track rows 4', 'coverage 0.02 < 0.90', 'median_track_len 1.00 < 3.00', 'jump_max 48.93 > 8.00'] coordinate_space='court_feet' rung='COURT_FEET'
```

The initial one-shot staging/process census found the staged
`data/footage_bridge/tennis__tennis_ref01.mp4` file absent, no adjacent
`tennis__tennis_ref01*.log` file, and no matching adapter job from a
read-only `ps` query. The daemon was alive as PID 33064 with its documented
`scripts.platformkit.track_daemon --workers 10 --forever --interval 15`
command. Its tennis log line says:

```text
tennis_ref01 tennis tracked rows=1861 passed=False duplicate frame-track rows 4;coverage 0.02 < 0.90;median_track_len 1.00 < 3.00;jump_max 48
```

This is a completed natural daemon row, not a hand-run substitute. The source
was found read-only at
`data/footage_corpus/tennis__tennis_ref01.mp4`; it was copied out only to
render the required local evidence frames.

## [G164](g164_three_coverages_2026-09-03.md) three-quantity comparison

The relevant raw table is `data/tracking/tennis_ref01/tracking_data.csv`.
It has 1,861 emitted rows across **726 distinct emitted source frames**. Its
row-level `cls == player` identities yield **715 emitted frames with at least
two distinct player track IDs**. The ledger supplies **28,773 decoded source
frames**.

| G164 quantity | Numerator / eligible denominator | Result | Meaning |
| --- | --- | ---: | --- |
| Harness coverage, emitted frames | 715 qualifying emitted frames / 726 distinct emitted frames | 0.984848 | Direct-harness denominator only. |
| Harness coverage, decoded frames | 715 qualifying emitted frames / 28,773 decoded source frames | 0.024850 | Daemon-path gated quantity, reconstructed from the raw table and decoded denominator; it is not persisted as its own ledger field. |
| Ledger completeness | 726 emitted frames with any row / 28,773 decoded source frames | 0.025232 | This is the ledger's `coverage_pct`, rounded there to 0.0252; it is frame presence, not the min-player harness quantity. |

Hand reproduction from the raw CSV for the ledger quantity:

```text
distinct frame values in 1,861 CSV rows = 726
decoded_frames in the one matching ledger row = 28,773
726 / 28,773 = 0.0252319883 -> ledger coverage_pct 0.0252 (rounded)
```

The two decoded-frame quantities have the same eligible denominator (every
one of the 28,773 decoded source frames, including no-row frames), but distinct
numerators. The emitted-frame harness quantity instead has exactly the 726
frames represented in the CSV as its eligible denominator. They are named
separately and are not conflated.

## Declaration and recovered geometry are separate

`coordinate_space` is `court_feet` in **1,861 / 1,861 emitted rows**. This is
an unconditional coordinate declaration, not recovered-geometry evidence.

Separately, `calibration_provenance == solved` occurs in **1,558 / 1,861
emitted rows = 0.837184**. Applying [G152](g152b_declaration_rates_2026-09-03.md)'s stricter solved-geometry predicate
-- `calibration_provenance == solved` and both `raw_projected_x_ft` and
`raw_projected_y_ft` populated -- yields **358 / 1,861 emitted rows =
0.192370**. The eligible denominator for both shares is every emitted CSV row;
neither is a decoded-frame or coordinate-declaration share.

## Even frame sample and eye check

The decision set is the sorted 726 distinct emitted frame IDs. Positions
`round(i * (726 - 1) / 4)` for `i = 0..4` select frames 372, 7,452, 13,800,
21,189, and 28,461: an even selection rather than a head slice. Each render
shows the wide US Open court view, court markings, and both players on
opposite sides of the net; the score graphic is also visible. The sampled
playing state differs, including a near-player serve (372), a far player low
at the sideline (7,452), and baseline exchanges (13,800, 21,189, 28,461).

- [frame 372](g173_tennis/frame_00372.png)
- [frame 7,452](g173_tennis/frame_07452.png)
- [frame 13,800](g173_tennis/frame_13800.png)
- [frame 21,189](g173_tennis/frame_21189.png)
- [frame 28,461](g173_tennis/frame_28461.png)

## Verifier-contract self-check

### A

- **A1:** No code changed, so no per-file test applies; no full test suite ran.
- **A2:** The raw CSV count independently reproduces the ledger's rounded
  completeness value, and all three quantities show their numerator and
  eligible denominator.
- **A3 / Q7:** `n = 1 tennis ledger row (CONSTRUCT, exhaustive)`. The required
  five-frame check is evenly distributed across the 726-frame decision set.
- **A4:** The comparison uses one named ledger row and one named source table;
  frame counts are distinct frame identities, not CSV-row or track-ID counts.
- **A5-A6:** Evidence-only change: no reader, schema, deployment, or archive
  operation is involved. The commit uses explicit pathspecs.
- **A7:** This memo, all five renders, the verifier contract, G164, and G152
  were checked locally before commit.

### B

| Condition | Self-check |
| --- | --- |
| B1 | Clear: the only tennis ledger row is named; no row was excluded. |
| B2 | Clear: no schema, field, status, or reader changed. |
| B3-B6 | Clear: no gate, claim/retry path, pod deployment, module, import, or command changed. |
| B7 | Clear: the five source frames follow the stated even-spacing formula. |
| B8-B9 | Clear: no fitted residual, recycled ID, or trivial denominator is offered. |
| B10 | Clear: no bar, threshold, harness, contract, or verdict changed. |

## NOT VERIFIED

- A persisted daemon-path min-player-over-decoded coverage field: G164
  establishes that it is discarded; the table above reconstructs the formula
  from this row's retained raw CSV and decoded denominator instead.
- Any result beyond this one exhaustive tennis ledger-row observation.
- Any altered, alternate, rally-scoped, or corrected bar. None is proposed.
- The requested `.claude/skills/lane-spawn-rails/SKILL.md` RAILS block: that
  path is absent in this worktree, so it could not be read.
