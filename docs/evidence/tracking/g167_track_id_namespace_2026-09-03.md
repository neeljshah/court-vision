# G167: tennis track-id namespaces

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, including A5, A7,
Q8, and section B. This is a future-only additive fix. No existing tracking
table was opened for writing, re-tracked, or modified. No pod process was
killed or restarted, and no code was copied to the pod.

## Q8 premise and mechanism, established before the fix

The pre-fix ball mint was the constant in `domains/tennis/tracking/ball.py:243`
(quoted from the pre-change source):

```python
rows.append({"frame": frame, "track_id": 99, "cls": "ball",
```

The player mint remains `domains/tennis/tracking/identity.py:24-25`:

```python
tracked = [(base + track_id, candidates[index][1]) for track_id, index in enumerate(order, start=1)]
return tracked, {base + track_id: centers[index] for track_id, index in enumerate(order, start=1)}
```

`end_epoch` advances `base` by two when it closes a non-empty epoch
(`identity.py:7-9`), and `TennisAdapter` initializes `_track_id_base = 0`
(`adapter.py:64`). Players therefore receive positive pairs `base + 1` and
`base + 2`, while every ball received 99.

This is structural, not incidental and not a wraparound: when the player base
reaches 98, the next player pair is 99 and 100. A ball emitted on either of
those frames necessarily shares the class-blind `(frame, track_id)` key with
the player 99. The paths are not independent counters: one is a constant and
the other is a two-ID epoch sequence.

## Exhaustive read-only table count

One bounded read-only pod query opened
`/workspace/nba-ai-system/data/tracking/tennis_smoke/tracking_data.csv` once
with Python's CSV reader. It grouped every row by `(frame, track_id)`, retained
the set of `cls` values for each key, and named no exclusions.

| Item | Count |
|---|---:|
| Rows read | 1,861 |
| Eligible denominator: distinct `(frame, track_id)` keys | 1,857 |
| Keys with more than one `cls` | 4 |
| Cross-class collision share | 4 / 1,857 = 0.002154011847065159 (0.2154 pct) |

The four keys are `(5676, 99)`, `(5679, 99)`, `(5688, 99)`, and `(5691, 99)`.
Each contains exactly `cls=player` and `cls=ball`. This reproduces the harness
count, but supplies its missing mechanism and exhaustive eligible denominator.

## A5 reader survey, completed before the code change

The exhaustive source inventory command was `git grep -l 'track_id' -- '*.py'`:
it enumerated 143 Python files. The evidence inventory command was
`git grep -l 'track_id' -- 'docs/evidence/**'`: 65 static evidence files. The
source-wide literal and range audit used `track_id.*99|99.*track_id` and
`track_id.*(>|<|uint|positive|negative|abs|range)` patterns. It found no runtime
consumer that requires a ball ID of 99, a positive ball ID, or an unsigned ID.

| Reader group | Paths checked | Result for future ball ID -1 |
|---|---|---|
| Harness | `scripts/platformkit/tracking_harness.py:237-262` | Uses class-blind `(frame, track_id)` duplicate keys and player-filtered track metrics; disjoint IDs remove only the false collision. |
| Census and scans | `g154_local_table_census.py:124-131`, `tracking_quality_scan.py:61-73` | Filter `cls == player` before grouping; ball ID is irrelevant. |
| Contract and schema | `tracking_contract.py:27,139`, `tracking_schema.py:37,86,268`, `tracking_depth_inventory.py:19-23`, `coordinate_provenance.py:8` | Require/preserve the field or duplicate key; no value/range rule. |
| Tennis analysis | `domains/tennis/tracking/quality_probe.py:29-66`, `rally_features.py:71-224` | Both derive player identity only after filtering player rows. |
| Tennis adapter and mint paths | `adapter.py:172-176,229-256`, `ball.py:236-250`, `identity.py:12-25` | Adapter passes the ball row through unchanged; player issue remains positive epoch IDs. |
| Other adapters and consumers | Baseball, basketball, football, and soccer adapters; platform render, overlay, replay, bridge, and analytics callers in the 143-file inventory | No cross-sport caller has a literal-99 or positive/unsigned contract for tennis ball IDs. |
| Tests and evidence | Tennis/platformkit fixtures and all 65 `docs/evidence` matches | Fixtures use 99 as sample data but do not consume adapter output. Evidence matches are static historical records and retain the old-table value 99. |

No checked reader would break. Had one required 99 or positive/unsigned IDs, this
change would not have landed.

## Additive future-only fix and row-pair check

`domains/tennis/tracking/ball.py` now defines `BALL_TRACK_ID = -1` and uses it
only when issuing new ball rows. Player issuance and every existing tracking
table remain unchanged; historical ball rows retain 99. Positive player epoch
IDs cannot collide with -1.

The before pair from the immutable table was:

```text
frame=5676 track_id=99 cls=player
frame=5676 track_id=99 cls=ball
```

The focused post-change function test constructs a new ball row and proves the
new pair is disjoint:

```text
frame=5676 track_id=99 cls=player
frame=5676 track_id=-1 cls=ball
```

`python -m pytest domains/tennis/tracking/test_ball.py -q` passed: 5 passed.
This is a function-level row-pair check only; no video was decoded locally and
no post-fix table was produced or deployed.

## Verifier self-check

- **A5:** Reader survey completed before the issue-site change; no reader requires the old value.
- **A7:** This memo, `ball.py`, `test_ball.py`, `RESULTS_LEDGER.md`, and the
  register row all exist before commit. Pod table access was read-only.
- **B1:** The collision metric groups all 1,861 rows and uses every one of the
  1,857 distinct keys; no collision key or class was excluded.
- **B2:** Only future ball values change. No column, status, field, or existing
  table was renamed, removed, renumbered, or rewritten; all readers were checked.
- **B3-B4:** No gate, quarantine, claim, or failure path changed.
- **B5:** Nothing was copied to the pod before verification.
- **B6:** No module moved or retired.
- **B7:** The required landing check is a named before/after row pair, not a
  sampled render set; it does not use a head slice.
- **B8:** No fitted model or residual is involved.
- **B9:** The denominator is exhaustive distinct table keys, not a recycled ID unit.
- **B10:** Harness, `min_players`, two-slot rule, `jump_max`, coverage bar,
  coordinate contract, existing tables, and verdicts have no diff.

## NOT VERIFIED

- No post-fix pod output exists: this patch is not deployed and no table was
  re-tracked, by scope.
- The frequency of this collision in any table other than `tennis_smoke` was
  not measured; the required exhaustive denominator is this table's full key set.
- This does not repair the four historical collisions or change their harness
  verdict; historical tables keep their IDs exactly as written.
- The independent epoch-churn and jump findings remain outside this change.
