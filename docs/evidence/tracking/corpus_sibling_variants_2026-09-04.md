# G28b: duration-aware sibling source selection

Log: `cx_g28b_siblings_duration`
Date: 2026-09-01
Scope: all sports; CONSTRUCT, `n = 8` (four exhaustive sibling groups plus
their four singleton-suffixed staging cases).

## Premise reproduction

Read-only pod command, run from `/workspace/nba-ai-system`:

```text
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate -show_entries format=duration -of csv=p=0 <each corpus file>
```

| sibling group | corpus file | width x height | fps | duration seconds |
|---|---|---:|---:|---:|
| football_wHZt1eY3A9s | football__football_wHZt1eY3A9s.mp4 | 1280 x 720 | 30000/1001 | 964.466133 |
| football_wHZt1eY3A9s | football__football_wHZt1eY3A9s_1080p.mp4 | 1920 x 1080 | 30000/1001 | 300.066000 |
| wnba_01 | wnba__wnba_01.mp4 | 1280 x 720 | 30/1 | 962.082333 |
| wnba_01 | wnba__wnba_01_1080p.mp4 | 1920 x 1080 | 30/1 | 600.067000 |
| ncaa_basketball_IB-_u4gW3ds | ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4 | 640 x 360 | 30000/1001 | 960.158000 |
| ncaa_basketball_IB-_u4gW3ds | ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p.mp4 | 1920 x 1080 | 30000/1001 | 600.099000 |
| tennis_nyYk2nPZAwY | tennis__tennis_nyYk2nPZAwY.mp4 | 640 x 360 | 25/1 | 960.010000 |
| tennis_nyYk2nPZAwY | tennis__tennis_nyYk2nPZAwY_720p.mp4 | 1280 x 720 | 50/1 | 960.040000 |

The premise reproduces: a height-first rule picks the shorter source in the
football, WNBA, and NCAA groups. Tennis is effectively time-aligned and its
720p copy remains selected.

## Selection and identity result

The helper makes an explicit staged variant key. It uses the suffix-free root
only when two or more staged, parseable files share that root; a singleton uses
its full original game ID. Among valid staged siblings, rank is longest duration,
then greatest height, then filename only for a deterministic exact tie.

| group | height-first selection (before) | duration-first selection (after) | enqueued game ID | singleton suffixed staging ID |
|---|---|---|---|---|
| football_wHZt1eY3A9s | football__football_wHZt1eY3A9s_1080p.mp4 | football__football_wHZt1eY3A9s.mp4 | football_wHZt1eY3A9s | football_wHZt1eY3A9s_1080p |
| wnba_01 | wnba__wnba_01_1080p.mp4 | wnba__wnba_01.mp4 | wnba_01 | wnba_01_1080p |
| ncaa_basketball_IB-_u4gW3ds | ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p.mp4 | ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4 | ncaa_basketball_IB-_u4gW3ds | ncaa_basketball_IB-_u4gW3ds_1080p |
| tennis_nyYk2nPZAwY | tennis__tennis_nyYk2nPZAwY_720p.mp4 | tennis__tennis_nyYk2nPZAwY_720p.mp4 | tennis_nyYk2nPZAwY | tennis_nyYk2nPZAwY_720p |

The four singleton IDs in the final column are each asserted unchanged when
that file is the only staged member. The rule covers terminal `_<height>p`
resolution suffixes only when the staged directory contains a sibling with the
same sport and root. It deliberately leaves malformed names, non-resolution
suffixes, and every resolution-suffixed singleton as its original identity;
there are no hard-ID exclusions.

## Verification

```text
python -m pytest scripts/platformkit/test_track_daemon.py -q
28 passed in 16.13s

python -m pytest scripts/platformkit/tracking/test_tennis_sequential_plan.py -q
2 passed in 1.55s
```

- `test_sibling_duration_selection_and_singleton_identity` enumerates all four
  groups and all four singleton-suffixed identities.
- `test_seconds_ranges_convert_for_each_source_fps` preserves the exact
  306-312 second conversion at 25 and 50 fps.
- `track_daemon.py`: 263 lines after extraction (cap: 300).
- The ledger receives only additive `source_fps`, `source_height`,
  `source_duration`, and `source_variants` fields for newly launched jobs; CSV
  stamping appends the three source columns without renaming existing fields.

## Contract B self-check

- B1: construct table names every one of the eight cases; no failing row is excluded.
- B2: no existing schema field or status changed; source fields are additive and
  the source-field reader search found no existing consumer to update.
- B3: unreadable metadata does not quarantine or reject a valid source; it is
  still selectable with deterministic fallback ordering.
- B4: corrupt retain behavior remains covered by the existing failed-quarantine
  regression; selected siblings are retained together on completion or done-veto.
- B5: no daemon or shared-module file was copied to the pod.
- B6: the daemon imports the new helpers by full package path; source-timebase
  imports are updated in the only plan module that uses them.
- B7: not applicable: this is an exhaustive CONSTRUCT selection table, not a render sample.
- B8: no fit or residual metric is used.
- B9: unit is the named staged group or singleton identity, not a recycled denominator.
- B10: no harness threshold, daemon timeout, done-definition, or tracking-schema
  field set changed.

## NOT VERIFIED

- No actual pod staging/daemon run was performed, and no deployment or SCP occurred.
- The four-group inventory is reproduced from the current pod corpus only; future
  corpus additions need a new enumeration rather than an extrapolated `n` claim.
- The fallback ordering for a valid file whose duration metadata cannot be read is
  unit-tested by code path only, not against a corrupt real video.
