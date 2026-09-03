# G204: evaluated denominator for the direct harness path

## Result

The direct CSV harness now supplies `attempted_frames` only when every emitted
row carries one stable, non-null pre-tracking triplet:
`decoded_frames`, `source_fps`, and `max_frames`. It derives the count with the
same sampling rule and evaluated-frame cap used by G179. If any input is absent,
invalid, or inconsistent, it supplies `None`; it does not use a gameplay frame,
emitted frame, or the sibling ball detector as a fallback.

This is stricter. None of the four committed G197 tables carries the triplet,
so none receives a count. All four remain fail-closed. This is the expected
full-success outcome: the direct route does not yet persist the required source
facts, and emitting them is a separate producer row.

## Producer semantics and formula

The stride is not assumed from table spacing. `adapter_run.py:100` calls
`sampling_plan(metadata.get("frame_rate"))`, and `tracking_timebase.py:35`
returns `max(1, round(frame_rate * 0.1))`. `adapter_run.py:81` records the
default `--max-frames` value of 30,000, but a direct table must carry its own
`max_frames` value because an invocation can override that default.

The baseball adapter establishes the cap semantics at
`domains/baseball/tracking/adapter.py:198,202,251`: its loop checks
`processed < max_frames`, selects a frame only when `source_frame % stride ==
0`, and increments `processed` only for that selected frame. Thus the cap is
on evaluations, not decoded source reads. `track_daemon_done.py:107-114` uses
the equivalent G179 construction; G204 implements the same count at
`attempted_frame_count_source.py:144-152`:

```text
s = max(1, round(0.1 * source_fps))
N = ceil(decoded_frames / s)
E = min(N, max_frames)
  = len(range(0, min(decoded_frames, s * max_frames), s))
```

No gameplay-derived quantity is used. In particular, `_is_gameplay` is not an
input: its positive/negative cache is detector-dependent. `frame`, player
rows, row count, frame spacing, `coverage_pct`, and `ball_tracking.csv` are
also not inputs. G199's paired-ball audit remains available as an audit helper,
but the direct harness no longer treats a detector-produced ball table as a
denominator source.

## Worked arithmetic

### Uncapped committed construct: `mlb_2026-08-30_10893dca`

G179's committed reproduction records `D = 39,035`, `source_fps = 60`, and
the adapter default `M = 30,000`.

```text
s = max(1, round(0.1 * 60)) = 6
N = ceil(39,035 / 6) = 6,506
E = min(6,506, 30,000) = 6,506
```

Although 39,035 is greater than 30,000, this run is **not capped**: 30,000 is
an evaluated-frame cap, not a source-frame cap. Treating it as a raw decode cap
would contradict the adapter's `processed` control flow and produce the wrong
denominator.

### Capped committed construct: `npb_01`

G179's committed reproduction records `D = 426,072`, `source_fps = 30`, and
`M = 30,000`.

```text
s = max(1, round(0.1 * 30)) = 3
N = ceil(426,072 / 3) = 142,024
E = min(142,024, 30,000) = 30,000
evaluated source frames = 0, 3, ..., 89,997
```

This is the reachable capped daemon construct. It is arithmetic over G179's
committed `decoded_frames` and source-fps artifact, not a daemon run or a claim
that an unrecorded direct CSV is scorable.

## Committed direct-table reproduction (Q7)

Construct: the four complete canonical tables G197 scored. Each was read from
the committed artifact and scored through `evaluate_csv_path()` after G204. The
metadata-column scan found `source_count_fields=none` for every one, so the
direct count source has no inputs and returns `None`.

| committed table | sport | G197/G199 before | G204 source facts | G204 evaluated count / coverage / ball | resulting verdict |
|---|---|---|---|---|---|
| `g96_jump_flips/nyyk_720p_tracking_data.csv` | tennis | `None`, fail closed | all three absent | `None` / `None` / `None` | `FAIL` (`jump_max`; `attempted_frames unavailable`) |
| `g96_jump_flips/tennis_10_tracking_data.csv` | tennis | `None`, fail closed | all three absent | `None` / `None` / `None` | `FAIL` (`jump_max`; `attempted_frames unavailable`) |
| `g69_metric_local/metric_local_clean_rows.csv` | baseball | `None`, fail closed | all three absent | `None` / `None` / `None` | `FAIL_METRIC_LOCAL` (`attempted_frames unavailable`) |
| `football_imagepx_snap/schema_sample_head30.csv` | football | `None`, fail closed | all three absent | `None` / `None` / `None` | `FAIL` (unchanged `coordinate_contract`) |

There are zero `None -> PASS` changes, zero `FAIL -> PASS` changes, and zero
new real denominators among the four. The football row exits at its unchanged
coordinate contract before coverage is adjudicated; its default report fields
remain `None`. Exclusions are explicit: these four evidence CSVs lack all three
required source facts, so none may be estimated. The capped `npb_01` construct
is not listed as a direct-table result because no committed direct table with
the same triplet was available.

The local reproduction output was:

```text
docs/evidence/tracking/g96_jump_flips/nyyk_720p_tracking_data.csv|tennis|None|None|None|FAIL|jump_max 56.39 > 8.00; attempted_frames unavailable
docs/evidence/tracking/g96_jump_flips/tennis_10_tracking_data.csv|tennis|None|None|None|FAIL|jump_max 45.21 > 8.00; attempted_frames unavailable
docs/evidence/tracking/g69_metric_local/metric_local_clean_rows.csv|baseball|None|None|None|FAIL_METRIC_LOCAL|attempted_frames unavailable
docs/evidence/tracking/football_imagepx_snap/schema_sample_head30.csv|football|None|None|None|FAIL|coordinate_contract: rows declare coordinate_space image_px not accepted for sport football; a preserved detection corpus is never a scorable game
```

## Threshold and contract invariance

The `DEFAULT_CONFIG_VERSION` through `CONFIG_VERSIONS` source slice was compared
byte-for-byte between `HEAD` and this worktree after normalizing only working
copy line endings. The full zero-context diff contains only the direct-source
import and `evaluate_csv_path()` wrapper; it contains no configuration hunk.

```text
config_byte_identical=True
head_config_sha256=ccebcfd6ec6c85b407834794647c6bac2e1c43f66f6d70bd087944d3077204e6
worktree_config_sha256=ccebcfd6ec6c85b407834794647c6bac2e1c43f66f6d70bd087944d3077204e6
```

No threshold, bar, verdict label, field name, eligibility definition, or
coordinate contract changed. `src/`, the daemon path, pod daemon, keeper, and
corpus were not edited or run.

## Tests

The new regression fails before G204 because the source-metadata helper and
direct-path wiring do not exist. It covers uncapped arithmetic, a true cap, and
missing/unstable metadata fail-closed behavior. The three required existing
per-file suites were then run individually; no full suite was run.

```text
python -m pytest scripts/platformkit/test_evaluated_frame_count_direct_path.py -q
...                                                                      [100%]
3 passed in 0.70s

python -m pytest scripts/platformkit/test_tracking_harness.py -q
........................                                                 [100%]
24 passed in 1.12s

python -m pytest scripts/platformkit/test_tracking_harness_g197.py -q
..                                                                       [100%]
2 passed in 0.49s

python -m pytest scripts/platformkit/test_attempted_frame_count_source.py -q
...                                                                      [100%]
3 passed in 0.60s
```

`tests/platformkit/test_loc_rail_scope.py` also passed (`1 passed in 2.08s`).
`tracking_harness.py` grew from 424 to 425 lines, so its allowlist entry was
raised to 425 in this same commit, as required by A12.

## NOT VERIFIED

- No committed G197 direct CSV currently records all of `decoded_frames`,
  `source_fps`, and invocation-specific `max_frames`; none can yet receive an
  honest count.
- No adapter-run producer now stamps that triplet into its direct CSV. Adding
  that producer provenance is deliberately out of scope for this direct-path
  row.
- No pod connection, daemon completion, deployment, restart, keeper action,
  video decode, inference, or corpus mutation occurred.
- The committed G179 NPB calculation verifies cap arithmetic only; it does not
  make a separate direct-table quality verdict available.
