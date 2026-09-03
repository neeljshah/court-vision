# G199: attempted frame count source

## Result

The direct CSV harness now asks a sibling `ball_tracking.csv` for an attempted
frame count, but only after a whole-file, non-circular frame-set audit. The
helper returns `None` for a missing sibling, a missing/invalid `frame`, a
missing `detected` flag, an empty ball set, duplicate ball-frame rows, or any
case where the ball frame set does not cover the tracking frame set. It does
not clamp, pad, take a maximum, or use `tracking_data.csv.frame.nunique()`.

This is direct-harness-only. `src/`, `track_daemon_done.py`, the pod daemon,
and the keeper were not read for modification, restarted, or deployed.

## Whole paired-artifact audit (Q7)

Construct: every `data/tracking/**/tracking_data.csv` paired only with a
sibling file named `ball_tracking.csv`. Each full CSV `frame` column was read;
the ball file was also required to contain the documented `detected` flag.
Frames must be integral and non-null. The denominator is the number of unique
ball frames only after the tracking frame set is a subset of that set and the
ball table has exactly one row per frame.

| Quantity | Result |
|---|---:|
| tracking tables found | 362 |
| paired artifacts audited | 355 |
| accepted per-table attempted counts | 351 |
| rejected paired artifacts | 4 |
| frame-set superset violations | 2 |
| ball files inspected for `detected` | 359 / 359 |

The two denominator-support violations are the decisive finding. Their ball
frame sets are not supersets, so their attempted count is unavailable:

| tracking table | tracking frames | ball frames | tracking frames absent from ball set | modal stride (tracking / ball) | last frame (tracking / ball) | result |
|---|---:|---:|---:|---|---|---|
| `data/tracking/0022401183/tracking_data.csv` | 5,292 | 18,000 | 2,664 | 3 / 3 | 26,001 / 73,389 | `None`: not a superset |
| `data/tracking/tracking_data.csv` | 1,675 | 2,000 | 852 | 3 / 3 | 11,937 / 12,927 | `None`: not a superset |

The second row is the named 2,000-row candidate. Its 2,000 distinct ball
frames and `detected` flag do not overcome the 852 tracking frames outside its
set. A count smaller than that numerator support is incoherent, so no count is
manufactured.

The other two rejected pairs also return `None`: `0022401185` has an invalid
tracking `frame` value, and `0022401198` has an empty ball-frame set. They are
not counted as frame-set superset violations because a comparable complete set
could not be formed.

Frame values are strided. For every one of the 353 pairs with readable,
non-empty frame sets, the unique modal tracking-frame stride equals the unique
modal ball-frame stride; the observed modal strides are 3 or 6 frames. No
paired ball table ends before its tracking table. Ball tables extend beyond
their tracking sibling in 163 pairs (a detectable tracking-side early exit,
because `ball_last_frame > tracking_last_frame`); equal final frames occur in
the remaining comparable pairs. That trailing asymmetry does not invalidate a
superset denominator: all tracking-frame support is still present.

Excluded because a denominator cannot be paired with a numerator:

- Tracking-only: `0022500585`, `failclosed_smoke`, `G83_table_0022400625`,
  `G83_table_0022400687`, `G83_table_0022400690`, `G83_tennis_09`, and
  `mlb_2iosUkpL0Bc` have no sibling `ball_tracking.csv`.
- Ball-only: `0022401123`, `0022500003`, `0022500581`, and
  `0022500737.f298` have no sibling `tracking_data.csv`.

Reproduction was a local, read-only full-column scan of every file in this
construct with `audit_paired_ball_table`; it performs the same validation used
by the direct scorer. No video decode, inference, `run_clip.py`, or pod was
run.

## Direct scoring behavior

`evaluate_csv_path()` is the direct CSV path and passes only
`attempted_frames_from_paired_ball_table(path)` into the existing
`evaluate(..., attempted_frames=...)` argument. The underlying G197 gate is
unchanged. Therefore 351 verified sibling pairs can receive their real count;
the four rejected pairs and seven tracking-only files receive `None` and fail
closed. There is no fallback to emitted frames.

The four committed tables G197 scored are evidence artifacts, not
`data/tracking` sibling pairs. All four have no paired ball table and therefore
remain `None` before and after this G199 direct-path wiring. The `pre-G197`
column below is a reproduction only: it passes emitted-frame count explicitly
to recreate the historical circular denominator. It is not an accepted count.

| committed table | sport | reconstructed pre-G197 attempted count / verdict | G197 state before G199 | G199 attempted count / corrected coverage / ball / verdict |
|---|---|---|---|---|
| `g96_jump_flips/nyyk_720p_tracking_data.csv` | tennis | 2,245 / FAIL (`jump_max`) | `None`, FAIL closed | `None` / `None` / `None` / FAIL (`jump_max`; `attempted_frames unavailable`) |
| `g96_jump_flips/tennis_10_tracking_data.csv` | tennis | 880 / FAIL (`jump_max`) | `None`, FAIL closed | `None` / `None` / `None` / FAIL (`jump_max`; `attempted_frames unavailable`) |
| `g69_metric_local/metric_local_clean_rows.csv` | baseball | 30 / PASS_METRIC_LOCAL | `None`, FAIL_METRIC_LOCAL closed | `None` / `None` / `None` / FAIL_METRIC_LOCAL (`attempted_frames unavailable`) |
| `football_imagepx_snap/schema_sample_head30.csv` | football | not reached / FAIL (coordinate contract) | `None`, FAIL | `None` / `None` / `None` / FAIL (coordinate contract) |

There are zero G199 FAIL-to-PASS changes among these committed G197 tables.
The prior circular metric-local PASS remains a fail-closed FAIL, as intended.

## Threshold invariance

The complete `_BASKETBALL`, `_BASEBALL`, `CONFIG_VERSIONS`, and `SPORTS` AST
source slices were compared byte-for-byte with `HEAD`:

```text
config_byte_identical=True
head_config_sha256=16fb30076099cdfdb1d58b2692cdcf94684c3bd25bbe7346c1df51621728b3f6
worktree_config_sha256=16fb30076099cdfdb1d58b2692cdcf94684c3bd25bbe7346c1df51621728b3f6
```

`git diff --unified=0 -- scripts/platformkit/tracking_harness.py` contains
only an added sibling-count import and direct-path wrapper/call replacement;
there is no configuration-table hunk. Thus no threshold, bar, eligibility
definition, existing field name, or verdict label changed.

## Tests

```text
python -m pytest scripts/platformkit/test_attempted_frame_count_source.py -q
3 passed in 1.23s

python -m pytest scripts/platformkit/test_tracking_harness.py -q
24 passed in 2.44s

python -m pytest scripts/platformkit/test_tracking_harness_g197.py -q
2 passed in 1.47s
```

The new per-file regression creates a 100-frame complete tracking table with
a verified 200-frame sibling ball table. Direct scoring receives 200, reports
0.5 attempted-frame coverage and ball validity, and fails the unchanged gate.
It also proves a 50-frame non-superset sibling returns `None` and fails closed.
Duplicate ball-frame rows also return `None`. Without this change the direct-path
wrapper and source helper do not exist.

## NOT VERIFIED

- The sibling `ball_tracking.csv` contract is verified structurally here
  (`frame`, `detected`, one row per frame, and support superset), not by
  decoding source video again.
- No count is available for the two support violations, the two malformed
  paired files, the seven tracking-only files, or the four G197 evidence
  tables.
- No claim is made about real-world tracking accuracy, model quality, betting,
  or any edge.
