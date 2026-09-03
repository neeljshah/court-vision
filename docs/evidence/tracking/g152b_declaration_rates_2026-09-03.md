# G152b - tennis declaration rates on the local reference clip

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A7 and the
Section B self-check. This is the measurement-only second attempt for G152.
The declaration trace in [G152 attempt 1](g152_court_feet_declaration_2026-09-03.md)
is accepted as landed context and was not re-derived. No pod, SSH, deployment,
or production-code change occurred.

## Q8 premise re-measurement and method

The attempt-1 availability premise is **FALSIFIED** in this worktree:
`data/videos/reference/tennis.mp4` is present and opens locally. I used that
one fixed clip, with scratch game id `g152b_tennis_reference_20260903`; its
CSV and frame manifest were written only to a disposable local scratch
directory, never to the shared tracking store.

OpenCV's container field reported 28,908 frames, but a complete sequential
`cv2.VideoCapture.read()` pass decoded **28,773** frames. The adapter's
`last_frame_manifest` independently has 28,773 unique frames numbered
0--28,772, all evaluated at the default stride of one. The decoded pass, not
the inaccurate container field, is the denominator below.

I ran the unchanged `domains.tennis.tracking.adapter.TennisAdapter` over the
whole clip, then independently recomputed every rate by reading the scratch
CSV. A declared frame means a frame with at least one emitted row whose
`coordinate_space` is `court_feet` and whose `calibration` is `homography`.
That definition measures observable declared output per decoded source frame;
it does not pretend a table-level stamp is a per-frame geometry solve.

## Results

| Metric | Result |
|---|---:|
| Decoded frames | 28,773 |
| Emitted rows | 6,770 |
| Distinct emitted frames | 2,597 |
| `coordinate_space` across rows | `court_feet`: 6,770/6,770 |
| `calibration` across rows | `homography`: 6,770/6,770 |
| All-frame declaration rate | **2,597 / 28,773 = 9.0258%** |
| Rally-only declaration rate | **Unmeasured** |
| Solved-geometry row share | **1,350 / 6,770 = 19.9409%** |

The rally-only rate is deliberately unmeasured. There is no retained
per-frame rally label or classifier for this clip. G34's 125/300 hand census
is for a different video and is not imported here. A new seeded, evenly spaced
hand census would be needed to construct this clip's rally denominator; I did
not guess it.

## Declaration is not recovered geometry

The requested geometry numerator is intentionally stricter than the declaration
numerator: a row must have `calibration_provenance == solved` **and** both
`raw_projected_x_ft` and `raw_projected_y_ft` populated. That yields 1,350
rows. There are 1,624 rows with both raw coordinates populated and 5,594 rows
whose provenance is `solved`; their intersection is the 1,350-row numerator.

The two requested rates differ. Their published denominators differ too, so
the direct numerical comparison is not a like-for-like performance comparison:
the 19.9409% row share is 10.9151 percentage points above the 9.0258%
decoded-frame declaration rate. On the common decoded-frame unit, those 1,350
geometry-backed rows occupy 1,350 distinct frames: **1,350 / 28,773 =
4.6919%**, which is **4.3339 percentage points below** the declaration rate.
Thus 2,597 frames carry declared output, but only 1,350 frames carry a row
meeting this spec's solved-and-raw geometry condition. The unconditional
`court_feet`/`homography` stamp is therefore not evidence that every declared
frame recovered fresh solved geometry.

## Required eye check

There were 1,176 rows with `calibration_provenance` other than `solved`, so
the specified first branch applies. I sorted their emitted frame identities
and selected positions 0%, 25%, 50%, 75%, and 100% of that decision set,
instead of taking its head. Each selected frame is a full-court US Open
broadcast view with both sides of the court and the usual score graphic visible;
the images show why a lock-reuse row can exist while its provenance is not a
fresh `solved` value.

| Frame | Rows / provenance | Eye observation |
|---|---|---|
| 1,277 | 2 / `camera_lock_drift_checked` | Full blue court and both player positions are visible; the near player is at the baseline and the far player is at the opposite end. |
| 8,662 | 3 / `camera_lock_drift_checked` | The wide behind-baseline broadcast view shows the entire playable court, both players, and the score graphic. |
| 19,811 | 3 / `camera_lock_drift_checked` | Full court markings are visible; both players are in the wide view, with the near player low in frame. |
| 24,004 | 3 / `camera_lock_drift_checked` | A wide court view shows both baselines, service boxes, and players on opposite sides. |
| 28,463 | 3 / `camera_lock_drift_checked` | The full court and both players remain visible in the standard broadcast camera angle. |

Renders: [frame 1,277](g152b_rates/frame_01277.png),
[frame 8,662](g152b_rates/frame_08662.png),
[frame 19,811](g152b_rates/frame_19811.png),
[frame 24,004](g152b_rates/frame_24004.png), and
[frame 28,463](g152b_rates/frame_28463.png).

## G142's five undeclared tables

G142's `tennis_01` through `tennis_05` are the explanation at the available
evidence level. The committed G142 census records their bare five-column
schema, while the retained tracking state and ledger identify them as
pre-fix legacy tables. They did not traverse the current adapter return path,
which stamps even an empty result; hence their missing declaration is not a
counterexample to the current unconditional stamp. The precise historical
writer revision is not retained. Resolving that narrower attribution would
require a retained writer command, deployed revision, or table-lineage record
for each legacy file.

## Verifier-contract self-check

### A

- **A2:** Recomputed the CSV numerators and denominators independently after
  the adapter run; the manifest independently confirms the decoded-frame
  extent. No rate is copied from the run's printout.
- **A3 / B7:** The five eye-check frames are evenly distributed over the
  non-solved emitted-frame decision set, not a head slice.
- **A4 / B9:** The all-frame denominator is all 28,773 decoded source frames;
  neither track ids nor repeated rows are used as a frame denominator.
- **A5:** No schema field or reader changed.
- **A6:** This is an evidence-only explicit-path worktree commit; no archive
  landing, deployment, or pod action occurred.
- **A7:** Before commit, this memo and all five linked renders were checked to
  exist.

### B

- **B1:** Clear. The 28,773-frame denominator includes every decoded frame,
  including all no-row frames; the 6,770-row geometry denominator includes
  every emitted row.
- **B2:** Clear. No field, schema, status, or reader changed.
- **B3:** Clear. Absent rows remain in the declaration denominator; they are
  not classified as bad footage.
- **B4:** Clear. No claim, retry, queue, or ownership code changed.
- **B5:** Clear. Local-only; nothing was copied to or run on the pod.
- **B6:** Clear. No module, import, test, or command was moved or retired.
- **B8:** Clear. No fitted residual or independence claim is made.
- **B10:** Clear. No threshold, gate, contract, or verdict changed.

## NOT VERIFIED

- This clip's rally-only declaration rate; no exact-clip rally labels were
  available, and G34's different-clip share was not reused.
- The precise deployed writer lineage of G142's five legacy undeclared tables.
- Any quality-gate, downstream prediction, or calibration conclusion. This is
  solely a local declaration-versus-geometry measurement.
- No new code was added, so no per-file test was applicable. No full test run
  was performed.
