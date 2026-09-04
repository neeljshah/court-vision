# G219 tennis failure-head diagnosis

## Verdict: NOT VALIDATED

This memo follows [the tracking verifier contract](VERIFIER_CONTRACT.md),
including a section-B self-check. It is a local, table-and-static-code
diagnosis only. No production code changed. `src/` was read only.

The G219 construct is exactly the three coordinate-valid G207 tennis tables:
22,935 emitted rows in total. `tennis_smoke` is excluded because G207 marked it
UNSCORABLE: it has no durable denominator. The full construct could not be
validated because only one of the three permitted copies survived locally.

## Acquisition and premise check

G207's authoritative inputs were opened locally:

| Input | Full local path | Bytes | SHA-256 |
|---|---|---:|---|
| G207 census | `docs/evidence/tracking/g207_pod_ledger_rescore_census_2026-09-03.md` | 14,412 | `fc208f6c0d9aa0178023185d1c79fc80692b314bb9a5b8f3d715b0fbb0609039` |
| G207 per-row source ledger | `docs/evidence/tracking/g207_pod_ledger_rescore_rows_2026-09-03.csv` | 10,647 | `d488e40e268a2d4d32a16719228f6e94308fe4ba40201346d91f61f558701511` |

One permitted local `scp` invocation named exactly these three pod sources:

| G207 row | Full pod path | G207 eligible denominator | Local result |
|---|---|---:|---|
| `tennis_01` | `/workspace/nba-ai-system/data/tracking/tennis_01/tracking_data.csv` | 19,437 rows | Copied first, then overwritten because every source had basename `tracking_data.csv`; unavailable for reconciliation or analysis. |
| `tennis_02` | `/workspace/nba-ai-system/data/tracking/tennis_02/tracking_data.csv` | 1,637 rows | Copied second, then overwritten for the same reason; unavailable for reconciliation or analysis. |
| `tennis_ref01` | `/workspace/nba-ai-system/data/tracking/tennis_ref01/tracking_data.csv` | 1,861 rows | Preserved and reconciled below. |

The local destination was a single directory. `scp` used each source basename,
so the final `tennis_ref01` transfer replaced the prior two outputs. G219
permits only these three copies. No fourth copy was attempted, and no other pod
operation occurred.

The retained source is
`docs/evidence/tracking/g219_inputs/tennis_ref01_tracking_data.csv`: 252,850
bytes; SHA-256
`77accc8cd83dee040601605a19bd7db592a703b2dd2bdf066fb0f2a8245f567b`.
Its eligible denominator is all 1,861 rows, exactly matching G207. It declares
`coordinate_space=court_feet`, `source_fps=29.97`, source height 360, and
source duration 964.5645645645646 seconds. No source-width column exists, so
the full source resolution is NOT RECORDED. No video was opened, probed,
decoded, or otherwise used.

G207 recorded the pod `scripts/platformkit/tracking_harness.py` SHA-256 as
`59f60428c5e82460f13e009a04db05d0b27e4a567aff33a324fb7b40bea87f1d`.
The local current harness opened for static definition reuse is
`scripts/platformkit/tracking_harness.py`, 21,851 bytes, SHA-256
`c5a86154da32177f00b72c8b54651ce73b4d68c48001348848ff4df3c6bd2f95`.
The identities differ. Therefore, only the retained table's duplicate count is
claimed as directly reproduced here; no current-local result is presented as a
reproduction of G207's other two table scores.

## Harness definitions used

The harness counts duplicate extra rows using `df.duplicated([frame,
track_id]).sum()` (adding `game_id` only when present) at
`scripts/platformkit/tracking_harness.py:310-313`. It computes player track
length as the median number of rows per player `track_id` at `:322-329`, and
computes `jump_max` from the maximum distance at the modal positive frame
stride at `:340-346`. These are the definitions G219 requires.

## Head diagnoses

### `tennis_01`: `jump_max` 108.39 > 8.00

G207 names this first failure head and its unchanged 8.00 bar. The table did
not survive acquisition, so the offending track, frame pair, coordinates,
units, and frame gap cannot be identified. Its cause is **UNDETERMINED**: the
evidence cannot distinguish an identity switch, coordinate-unit/scale error,
or a large frame gap. The preserved `tennis_ref01` is not a substitute artifact.

Evidence that would settle this is the exact retained `tennis_01` CSV, sorted
by player track and frame with the harness modal-stride filter applied.

### `tennis_02`: `median_track_len` 1.00 < 3.00

G207 names this first failure head and its unchanged 3.00 bar. The table did
not survive acquisition, so its requested full distribution (one frame, two
frames, three to five frames, six or more frames) and the fraction of emitted
rows belonging to one-frame tracks are **NOT VERIFIED**.

The static tennis path has several emission barriers, but does not identify
which one produced `tennis_02`: player rows are emitted only after a usable
homography (`domains/tennis/tracking/adapter.py:227-233`); `detect_players`
returns no rows unless both court halves have a selected candidate
(`domains/tennis/tracking/adapter.py:178-196`); a gap longer than three strides
ends the current identity epoch (`adapter.py:228-229`); and a cut also resets
the epoch (`adapter.py:220-221`). Within an epoch, `assign_epoch` uses centroid
continuity and assigns two identities (`domains/tennis/tracking/identity.py:12-25`).
This code has no embedding or appearance-threshold branch in that association
routine. **UNDETERMINED from static reading** whether the observed one-frame
median came from missing complete pairs, calibration loss, epoch resets, or a
different historical route. The exact `tennis_02` table plus its frame manifest
would settle that distinction.

### `tennis_ref01`: duplicate `(frame, track_id)` rows = 4

The full 1,861-row retained table reproduces G207's count: four duplicate extra
rows in four two-row groups. All differing columns are `cls`, `x`, `y`,
`projection_status`, `raw_projected_x_ft`, and `raw_projected_y_ft`; shared
metadata is identical within each pair.

| Frame | Track ID | Player `(x, y)` court feet | Ball `(x, y)` court feet | Differing class |
|---:|---:|---|---|---|
| 5676 | 99 | `(0.373066008091, 15.8271064758)` | `(83.9656811913, 26.5508073982)` | `player` / `ball` |
| 5679 | 99 | `(0.0576981827617, 15.7163286209)` | `(81.1327492969, 25.2752120613)` | `player` / `ball` |
| 5688 | 99 | `(0.0381591580808, 15.6045951843)` | `(81.1009542284, 23.7816039295)` | `player` / `ball` |
| 5691 | 99 | `(0.0555760450661, 15.5807428360)` | `(83.1474512724, 22.9133033274)` | `player` / `ball` |

This is an emission-time ID-namespace collision, not a retry or a re-ID merge:
the adapter appends player rows during the frame loop
(`domains/tennis/tracking/adapter.py:230-236`) and appends ball rows later
(`:251-256`). The current ball module states that historical tables retained
literal ball ID 99, while future rows use the disjoint ID -1
(`domains/tennis/tracking/ball.py:19-21`, `:239-253`). Player epoch IDs are
formed from an increasing epoch base (`domains/tennis/tracking/identity.py:7-9`)
plus 1 or 2 (`:24-25`), allowing a player to reach 99. The four rows are exactly
where that historical constant collided with a player epoch. The harness then
correctly detects the shared `(frame, track_id)` key without considering class
(`scripts/platformkit/tracking_harness.py:310-313`).

The collision is **tennis-path-specific in its observed cause**: it is carried
by `domains/tennis/tracking/adapter.py` and the historical tennis ball ID.
The harness predicate itself is shared code, but this memo does not claim that
other sports have the same collision. Current tennis code already reserves -1;
the retained historical table is not rewritten.

## Human-gated proposals only

No `src/` change is proposed: the diagnosed duplicate producer is the tennis
adapter path, not `src/`. If a human chooses a follow-up repair, it should first
add a regression fixture with a player ID 99 and a ball row, then verify the
output namespace before a new route run. Expected effect: prevent this
cross-class ID collision in future tennis tables. Regression risk: a migration
or post-hoc renumbering could break downstream joins that retain historical ball
ID 99. Nothing was applied.

## Limitations and NOT VERIFIED

- These tables came from a non-deterministic route documented by G189, G195,
  G198, and G203. This diagnoses the retained table, not a stable population.
- The three clips cannot establish a rate. Tennis has two to four players while
  basketball has ten, so no tennis finding transfers by default.
- `tennis_01` incident identity, coordinates, units, frame gap, and cause
  classification are NOT VERIFIED.
- `tennis_02` full track-length distribution, one-frame row share, and specific
  association rejection condition are NOT VERIFIED.
- A local direct score of retained `tennis_ref01` reports four duplicates, but
  current local harness code identity differs from G207's recorded pod hash;
  no broader G207 score reproduction is claimed.

## Tests and verifier self-check

Focused tests only:

```text
python -m pytest domains/tennis/tracking/test_ball.py -q
5 passed in 2.03s

python -m pytest scripts/platformkit/test_tracking_harness_g88_jump_statistic.py -q
FAILED: the unchanged current harness adds `attempted_frames unavailable`, so
the test's expected pass assertion fails before its intended jump assertion.
```

Section B self-check: B1 no circular metric (the retained duplicate count uses
all 1,861 rows); B2 no schema change; B3-B4 no gate or claim logic changed; B5
no file was copied to the pod; B6 no move; B7 no sampled evidence; B8 no fit;
B9 the eligible denominator is named; B10 no bar moved. Q rules do not apply:
G219 is not an S-row and makes no scored comparison. The evidence paths named
in this memo exist in this worktree at commit time.
