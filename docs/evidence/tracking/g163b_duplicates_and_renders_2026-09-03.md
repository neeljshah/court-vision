# G163b: duplicate-row bytes and required eye check

Scope: this closes only the two items left open by
[`g162_g163_epoch_churn_2026-09-03.md`](g162_g163_epoch_churn_2026-09-03.md):
the bytes and admitting path for the four duplicate keys, and the G162/G163
visual check. It is diagnosis only. No adapter, harness, threshold, coordinate
contract, gate, or verdict changed.

## Read-only pod snapshot: duplicate rows

I made a bounded read-only SSH query of
`/workspace/nba-ai-system/data/tracking/tennis_smoke/tracking_data.csv`. It
opened the CSV once, returned only the header and raw byte lines for duplicate
keys, and did not write, re-track, deploy, restart, or otherwise touch the live
pod.

There are four duplicate `(frame, track_id)` keys, all `track_id=99`, at source
frames 5,676, 5,679, 5,688, and 5,691. Each key has exactly two rows. They are
**not byte-identical**: one is a `player` row and the other a `ball` row with
different coordinates and ball-only projection fields. Thus this is two
different positions claiming the same class-blind `(frame, track_id)` key, not
a duplicated player detection.

The following is the pod CSV header followed by the eight duplicate rows,
verbatim (including the `court_fet` spelling in the final raw row):

```csv
frame,track_id,cls,x,y,calibration_provenance,projection_status,projection_rejection_reason,raw_projected_x_ft,raw_projected_y_ft,coordinate_space,observation,calibration
5676,99,player,0.3730660080909729,15.827106475830078,solved,,,,,court_feet,observed,homography
5676,99,ball,83.96568119130163,26.550807398195516,solved,accepted,,83.96568119130163,26.550807398195516,court_feet,observed,homography
5679,99,player,0.05769818276166916,15.716328620910645,solved,,,,,court_feet,observed,homography
5679,99,ball,81.13274929691454,25.275212061325735,solved,accepted,,81.13274929691454,25.275212061325735,court_feet,observed,homography
5688,99,player,0.03815915808081627,15.604595184326172,solved,,,,,court_feet,observed,homography
5688,99,ball,81.1009542284437,23.781603929545376,solved,accepted,,81.1009542284437,23.781603929545376,court_feet,observed,homography
5691,99,player,0.05557604506611824,15.580742835998535,solved,,,,,court_feet,observed,homography
5691,99,ball,83.14745127242762,22.91330332737996,solved,accepted,,83.14745127242762,22.91330332737996,court_fet,observed,homography
```

## How the collision enters despite the two-slot rule

The two-slot rule is real, but it applies only to the `player` branch.

`domains/tennis/tracking/adapter.py:180-197` collects candidates in
`per_half`, replaces a half's candidate only when the new key is better, rejects
the frame unless both halves are present, then supplies exactly the two chosen
candidates to `_track_ids`:

```python
# adapter.py:189-197
half = 0 if foot[0] < 39.0 else 1
...
if half not in per_half or key > per_half[half][0]:
    per_half[half] = (key, center, foot)
if set(per_half) != {0, 1}:
    return []
return self._track_ids([(per_half[0][1], per_half[0][2]),
                        (per_half[1][1], per_half[1][2])])
```

Those player tuples alone are appended at `adapter.py:230-235`:

```python
# adapter.py:230-235
players = self.detect_players(frame, homography)
player_count = len(players)
for track_id, point in players:
    rows.append({"frame": source_frame, "track_id": track_id,
                 "cls": "player", "x": float(point[0]), "y": float(point[1]),
                 "calibration_provenance": provenance})
```

The ball branch bypasses that selection. After the video pass,
`adapter.py:251-256` rectifies ball points, creates a ball row, overwrites its
frame with the same `source_frame`, and appends it to the same `rows` list:

```python
# adapter.py:251-256
for point, (frame, homography, provenance) in zip(rectify_track(ball_points), ball_frames):
    balls = ball_rows((point,), homography)
    if not balls.empty:
        ball = balls.iloc[0].to_dict()
        ball["frame"], ball["calibration_provenance"] = frame, provenance
        rows.append(ball)
```

`domains/tennis/tracking/ball.py:236-250` hard-codes the ball namespace to
numeric id 99:

```python
# ball.py:236-250
for frame, point in enumerate(rectified):
    if point is None or point[2] < _MIN_CONFIDENCE:
        continue
    decision = guard_ball_projection(point, homography)
    rows.append({"frame": frame, "track_id": 99, "cls": "ball",
                 "x": decision.raw_x if decision.status == "accepted" else float("nan"),
                 "y": decision.raw_y if decision.status == "accepted" else float("nan"),
                 ...})
```

Meanwhile `domains/tennis/tracking/identity.py:12-25` assigns a player id as
`base + track_id`; it has no class namespace:

```python
# identity.py:17-25
if len(centroids) != 2:
    order = sorted(range(2), key=lambda index: (-centers[index][1], centers[index][0]))
...
tracked = [(base + track_id, candidates[index][1])
           for track_id, index in enumerate(order, start=1)]
```

Therefore a legitimate player id 99 and the fixed ball id 99 can coexist on an
emitted source frame. The adapter's one-detection-per-court-half invariant is
not violated; it simply cannot constrain the independently appended ball row.

## Required eye check

The existing table was not remeasured. For the visual decision set, I used its
four known duplicate frames plus the endpoints of its already-established four
over-threshold player jumps: 12 anomaly-bearing source frames in total. The
tracked processing window is 28,773 decoded frames, so the five equal source
targets are 0, 7,193, 14,386, 21,579, and 28,772. At each target I selected the
nearest anomaly-bearing source frame, yielding 5,676; 5,691; 18,792; 21,303;
and 25,437. This is evenly distributed over the full processed clip, not a head
slice. The selection is recorded in
[`g163_jump/selection.csv`](g163_jump/selection.csv).

Each render uses the local reference clip named by the G162/G163 context and
shows the raw broadcast frame beside a court-coordinate inset. The three jump
insets show the two existing table endpoints; they are explanatory overlays,
not a new measurement.

| Target / selected frame | Render | What the eye sees |
|---|---|---|
| 0 / 5,676 | [01 duplicate](g163_jump/01_target00000_frame05676_duplicate.png) | A wide behind-baseline rally view with both sides of the court visible. The inset separates `track_id=99` player at the left court edge from ball 99 beyond the right sideline. |
| 7,193 / 5,691 | [02 duplicate](g163_jump/02_target07193_frame05691_duplicate.png) | Another wide rally frame. Again the player and ball have visibly different mapped positions while sharing only numeric id 99. |
| 14,386 / 18,792 | [03 jump](g163_jump/03_target14386_frame18792_jump_track399.png) | A player close-up with transition graphics, not a complete court view. The existing endpoints place the same player track above the court then below it over three frames, visually implausible as physical player motion. |
| 21,579 / 21,303 | [04 jump](g163_jump/04_target21579_frame21303_jump_track462.png) | A player close-up without court geometry. The current endpoint is below and beyond the court boundary in the inset. |
| 28,772 / 25,437 | [05 jump](g163_jump/05_target28772_frame25437_jump_track510.png) | A player close-up/serve-preparation view without the full court. The current endpoint is beyond the far/right boundary in the inset. |

The eye check supports that the duplicate is a class/ID namespace collision and
that the sampled jumps are not visually credible physical moves. It does not
identify the precise jump-producing subsystem or alter the already-landed
jump-gate conclusion.

## Verifier self-check

- **A2:** This memo reports only the requested raw duplicate rows and the
  existing anomaly frame identities, read directly from the pod table. It does
  not reproduce or replace the landed measurement half.
- **A3 / B7:** Five nearest eligible anomaly frames were chosen from equal
  targets across the entire 28,773-frame processed window; no head slice was
  used.
- **A7:** All five PNGs and `selection.csv` named above exist under
  `docs/evidence/tracking/g163_jump/` at write time.
- **B1-B6, B8-B9:** No metric was newly computed, no schema or reader changed,
  no deployment or exclusion occurred, and no module moved.
- **B10:** No threshold, gate, coordinate contract, or verdict changed. The
  8.00-foot jump bar is untouched.

## NOT VERIFIED

- The exact player-epoch history that caused a player to receive id 99; this
  diagnosis reads the assigning code and the resulting rows but does not
  instrument the live adapter.
- Why ball observations coincide with player 99 on these four frames rather
  than on other player-id-99 frames.
- The exact subsystem producing each over-threshold jump. The eye check shows
  close-ups and implausible table endpoints, but it does not prove whether the
  cause is a cut, calibration state, detector selection, or another component.
- The fourth over-threshold jump (frames 21,234 to 21,237) was not individually
  rendered because the required cap is five frames; it remains in the full
  anomaly decision set used for sampling.
- Byte identity between the local reference video used for the renders and the
  pod invocation input. The table and G162/G163 context identify it as the
  local reference clip, but this bounded diagnostic did not retrieve or hash a
  pod video file.
- Any fix, namespace change, duplicate-key policy, threshold movement, or new
  harness verdict.
