# G296B: independent clip-wide player locations, pass B

This row builds an INPUT and produces no recall number. Locator: pass B,
gpt-6-astra, a MODEL locator. Denominator: the 24 preregistered frames from one
clip, one independent locator in this pass. No pass bar applies.

Spec: [G296B_spec.md](specs/G296B_spec.md). Contract:
[VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including the B5 scratch exception.

I did not look for, read, or wait for pass A's output, and did not read any prior
located-feet file. No detector was run, imported, inspected, or joined to these
locations. The historical rationale supplied in the mandatory spec was read;
before the seal no separate recall report or detector output was opened.
The location-only commit is `eab39f126f87ecd5c9b4f63d1ce19d55f0d4d6c3`.
No join or comparison was performed afterward either. The ledger format and
its opening historical entries were read only after this commit, solely to append
this row; they did not inform or alter the sealed annotations.

## Machines and source

Extraction: pod scratch `/workspace/wt/a12`, because the original source is on
the pod. Location work: local `C:/Users/neelj/nba-track-a12`, branch `track-a12`,
using the fetched native JPEGs. All local writes and git commands stayed there.
No production tree, source video, corpus file, bridge partial, registry, feature
flag, gap register, or other worktree was changed. No push was made.

Source: `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`,
2,931,985,407 bytes. The extraction manifest records its full SHA-256, resolution,
frame count, frame rate, exact ffmpeg argv/command, route hash, and every fetched
JPEG's path, byte size, SHA-256, and native dimensions.

## Launcher adaptation and disk guard

The initial exact invocation of `~/bin/pod_run a12 --ship
scripts/platformkit/tracking/g296b_located_players.py --fetch
docs/evidence/tracking/g296b_located_players_artifact/frames_manifest.zip --
python3 scripts/platformkit/tracking/g296b_located_players.py` stalled in its
unbounded MooseFS `du -sm /workspace` walk before shipping. The installed helper
also defaults empty usage to zero and has a 47 GB size stop, conflicting with
this spec. It returned no size measurement; that result was UNKNOWN, never zero.

I stopped only the exactly identified local Windows bash wrapper PID 9684; no
pod process was killed or restarted. A worktree-local copy,
`scripts/platformkit/tracking/g296b_pod_run.sh`, preserves the helper's scratch
shipping, run, and fetch behavior but replaces the disk-size walk/stop with an
actual `dd conv=fsync` failure gate. Its fallback to another worktree is removed;
it accepts only a12. This is a disclosed launcher deviation from the literal
`~/bin/pod_run` path, required to honor the newer explicit disk-guard instructions.
The upstream helper was not modified; its SHA-256 was
`45581c1f7901851ad87b84169cee6d84db80132bda02f6b882280cadaf2de1d6`.

The harness separately gates decode on load15 below `nproc` and a successful
fsync probe. No GPU lane or `nvidia-smi` check was used. No internet/corpus
download occurred; only the requested derived frames and manifest were fetched.

## Annotation conventions

Coordinates use the full native image origin at top left, x rightward and y
downward. One point represents one player's visible floor contact; when two
soles are grounded, the point is between their contact locations. Hidden or
out-of-frame feet have `feet_visible=false` and empty x/y fields. No hidden foot
position is inferred. `players_located` counts on-court players with a recorded
coordinate; on-court players without visible feet remain separate person rows.
Confidence on a row without coordinates describes the person/visibility
judgment, not an invented foot location. Nonplayer roles are excluded from the
player counts.

## Required limitations

YOU ARE A MODEL, NOT A HUMAN, AND THIS IS NOT GROUND TRUTH IN THE STRICT SENSE.
Two model locators agreeing measures REPRODUCIBILITY, never CORRECTNESS, and
both can be wrong in the same way. No human has checked these frames.
24 frames across one clip is a thin, wide sample: it fixes the
span-representativeness problem and does NOT fix the one-clip problem.
Locating a foot in a 1920x1080 broadcast frame is itself uncertain at the
tens-of-pixels scale for distant players -- that is what the confidence field
is for, and any recall figure later computed from this set inherits it.
The frame indices are deterministic and were fixed before either pass ran,
so neither locator chose its own frames.

## NOT VERIFIED

- Human correctness of any role, visibility, or coordinate judgment.
- Agreement with pass A; only the verifier may merge the independent passes.
- Any detector match, recall, model performance, or production implication.
- Generalization beyond this one clip or beyond these 24 fixed frames.
- Sub-20-pixel accuracy for approximate or guess coordinates.
- Total /workspace disk usage; it remains UNKNOWN.

## Final input inventory and verdict

INPUT BUILT; no pass bar: n=24 fixed frames, one clip, one MODEL locator (pass B).
There are 163 on-court-player observations: 130 with a coordinate and 33 without.
There are 296 person rows total: 163 player_on_court, 41 official, 56
bench_or_coach, 31 spectator_or_media, and 5 other. These are per-frame person
observations, not distinct identities across time. Person indices restart at 1.

Coordinate confidence for the 130 player points: confident=9, approximate=119,
guess=2. For all 211 coordinate-bearing person rows: confident=21,
approximate=185, guess=5. For all 296 rows, including visibility/role judgments
without coordinates: confident=82, approximate=209, guess=5.

21 frames have visible court geometry; three do not. Eight frames have zero
located player points. Two frames have neither court geometry nor on-court
players; the third geometry-free frame has three judged players in a tight
postgame close-up with no feet visible. These judgments were retained regardless
of the spec's expected proportion of non-court frames. No frame was substituted.

This is an exhaustive attempt to identify every visible on-court player, not an
exhaustive census of the hundreds of indistinct spectators in the stands. The
nonplayer rows record distinguishable nearby officials, bench members, staff,
and media/spectators considered during location. Dense background crowd members
were not individually enumerated; completeness of nonplayer enumeration is NOT
VERIFIED. Uniformed athletes seated at a timeout bench are bench_or_coach.
Photo portraits inside broadcast graphics are not physical people in the scene.

For clearly airborne players or an airborne visible shoe with the planted foot
hidden, this pass conservatively uses feet_visible=false with an explicit note:
no floor-contact coordinate can be observed. This is a disclosed semantic
extension: false means no observable floor contact, not necessarily invisible
shoes. There is no inferred floor point beneath an airborne shoe. A downstream
merger must read these notes rather than interpret every false row as occlusion.

Three supplementary enlargements were made locally only for frame 0 inspection:
inspection_frame0_center.png crops (780,290,1140,510) and enlarges 3x;
inspection_frame0_near.png crops (300,470,1420,630) and enlarges 1.5x;
inspection_frame0_roles.png crops (1040,470,1390,600) and enlarges 3x.
They are viewing aids, not extraction inputs and not coordinate-space changes.
All 24 source JPEGs are the full native 1920x1080 image, uncropped and unresized.

## Completed extraction route and operational disclosure

The first sequential-decode attempt was too slow on shared storage and was not
used for annotation. Its local wait/fetch wrapper PID 8908 was stopped after
exact executable/argument identification; the pod process was not killed. The
original sequential process PID 3289772 was still active at the post-seal status
check (elapsed 22:57; CPU 03:23), writing only its original a12 scratch paths.
Its outputs were not fetched, opened, compared, or used. This unused scratch job
is not a dependency of the completed input and will exit naturally. Its gate is
archived in sequential_gate.json. No other lane was interrupted.

The successful route uses a separate `/workspace/wt/a12/g296b_seek/` output
folder. The local launcher was further narrowed to ship only its explicit
--ship files, avoiding another transfer of the entire Python tree. The final
invocation was:

```bash
bash scripts/platformkit/tracking/g296b_pod_run.sh a12 --ship scripts/platformkit/tracking/g296b_seek_frames.py --ship scripts/platformkit/tracking/g296b_located_players.py --fetch docs/evidence/tracking/g296b_located_players_artifact/seek_frames_manifest.zip -- python3 -m scripts.platformkit.tracking.g296b_seek_frames
```

The command finished with POD_RUN_DONE rc=0. Each frame uses accurate input seek
floored to microseconds, preserves original timestamps with -copyts, and checks
showinfo's first decoded frame: source PTS = source_frame * 512. The stream
starts at PTS 0, has time_base=1/15360 and frame rate 30/1. All 24 PTS assertions
passed, including the last frame. No temporal approximation was accepted.
The local early-fetch copies were byte-checked against the completed archive;
every final JPEG SHA-256 and its actual 1920x1080 dimensions were checked locally.
No unverified sequential output was mixed into this set.

The successful extraction gate was load15=87.04736328125 < nproc=256, with
loadavg=[12.533203125,59.974609375,87.04736328125]; dd conv=fsync returned 0.
No GPU usage or lane count entered that decision.

Source SHA-256: `f361ad7a32ccc6d98ae8e98eee0b090f5e121f9425182e24a31c282ca226c678`. Source dimensions: 1920x1080; frames: 174430; rate: 30/1.

Formula: `round(i * 174429 / 23)` for `i=0..23`. Extracted list (exact match):

```text
0, 7584, 15168, 22752, 30335, 37919, 45503, 53087, 60671, 68255, 75839, 83423, 91006, 98590, 106174, 113758, 121342, 128926, 136510, 144094, 151677, 159261, 166845, 174429
```

The following are all 24 exact successful ffmpeg commands. Each writes one JPEG, with no scale or crop filter. The native dimensions and source PTS are also in the individual ffmpeg logs.

```bash
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 0.000000 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_000000.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 252.800000 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_007584.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 505.600000 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_015168.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 758.400000 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_022752.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 1011.166666 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_030335.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 1263.966666 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_037919.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 1516.766666 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_045503.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 1769.566666 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_053087.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 2022.366666 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_060671.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 2275.166666 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_068255.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 2527.966666 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_075839.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 2780.766666 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_083423.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 3033.533333 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_091006.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 3286.333333 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_098590.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 3539.133333 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_106174.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 3791.933333 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_113758.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 4044.733333 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_121342.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 4297.533333 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_128926.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 4550.333333 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_136510.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 4803.133333 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_144094.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 5055.900000 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_151677.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 5308.700000 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_159261.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 5561.500000 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_166845.jpg
ffmpeg -hide_banner -nostdin -loglevel info -threads 1 -ss 5814.300000 -copyts -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -vf showinfo -vsync 0 -frames:v 1 -threads 1 -q:v 2 g296b_seek/frames/frame_174429.jpg
```

Route identity (SHA-256 of files actually exercised on the pod):

- `scripts/platformkit/tracking/g296b_seek_frames.py`: `11b4d56122f4038fd12ed2a65e8f3865d5d783471070c56875c32905842085e9`
- `scripts/platformkit/tracking/g296b_located_players.py`: `29a802fba2d9ea4b03c5854cad9cd45aeb0a4ed318912c820f39597c18dd2417`

ffmpeg: `ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023 the FFmpeg developers`.

## Every disk-guard probe, verbatim

```text
Pass B preliminary gate, pod /workspace/wt/a12.
Command:
dd if=/dev/zero of=/workspace/wt/a12/g296b_fsync_probe bs=1M count=8 conv=fsync
8+0 records in
8+0 records out
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.300794 s, 27.9 MB/s
cat /proc/loadavg
23.75 92.68 100.94 580/17913 3285039
nproc
256

A prior PowerShell/bash quoting attempt returned only the following and was
NOT accepted as a gate measurement (it did not execute the intended command):
0+0 records in
0+0 records out
0 bytes copied, 0.0899199 s, 0.0 kB/s

pod_run's additional default 8 MiB write probe (not the fsync gate):
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.195083 s, 43.0 MB/s

First local launcher fsync probe:
8+0 records in
8+0 records out
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.29502 s, 28.4 MB/s

Sequential harness fsync probe:
8+0 records in
8+0 records out
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.303088 s, 27.7 MB/s
loadavg=[107.33642578125,133.0634765625,113.70068359375]; nproc=256

Final local launcher fsync probe:
8+0 records in
8+0 records out
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.20102 s, 41.7 MB/s

Successful seek harness fsync probe:
8+0 records in
8+0 records out
8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.290491 s, 28.9 MB/s
loadavg=[12.533203125,59.974609375,87.04736328125]; nproc=256
/workspace disk usage: UNKNOWN
```

## Exact schemas and per-frame summary

```csv
source_frame,person_index,role,feet_visible,foot_x_px,foot_y_px,confidence,note
source_frame,court_visible,shot_description,players_located
```

| Frame | Court visible | Player rows | Located points | Shot |
|---|---|---|---|---|
| 0 | true | 7 | 6 | Wide center-court opening shot with standing foreground crowd and overlapping center-circle players |
| 7584 | true | 7 | 7 | Close-up low sideline court action with players and bench behind |
| 15168 | true | 10 | 9 | Wide half-court stopped play with players around the right paint |
| 22752 | true | 5 | 0 | Close-up of five white-uniform teammates huddling by blue court markings; all feet outside shot |
| 30335 | true | 10 | 10 | Wide right half-court action with a dark-uniform drive into traffic |
| 37919 | true | 10 | 8 | Wide right half-court pass with a central airborne player and near-corner occlusion |
| 45503 | true | 10 | 8 | Wide right half-court ball handling; entire source image is visibly soft and motion-blurred |
| 53087 | true | 10 | 8 | Wide right half-court pass with score graphic covering foreground feet |
| 60671 | true | 1 | 0 | Tight player close-up with a small blue floor and white marking fragment at lower left |
| 68255 | true | 10 | 10 | Wide left half-court drive near right elbow with overlapping feet |
| 75839 | true | 9 | 8 | Wide right basket after scoring with players running left; several feet airborne or overlapped |
| 83423 | true | 6 | 4 | Wide left-baseline inbound and transition; foreground feet covered by graphic |
| 91006 | true | 10 | 10 | Wide left-basket rebound with clustered white players under hoop |
| 98590 | true | 9 | 7 | Wide right-half-court action with running players and a near-right screen |
| 106174 | true | 10 | 9 | Wide left-half-court perimeter pass with overlapping screen and foreground score graphic |
| 113758 | true | 1 | 0 | Close-up white player raising hands beside clearly visible sideline; feet outside shot |
| 121342 | true | 10 | 9 | Wide transition through midcourt with ten judged on-court players including one cropped at right edge |
| 128926 | true | 3 | 0 | Close-up two main on-court players and partial teammate; seated bench behind is excluded from player role |
| 136510 | false | 0 | 0 | Close-up timeout bench huddle with staff and seated players; no court geometry or on-court players |
| 144094 | true | 9 | 8 | Wide right-basket stoppage with nine on-court players visible and one set of feet occluded |
| 151677 | true | 9 | 9 | Wide overtime half-court possession with nine on-court players visible |
| 159261 | false | 0 | 0 | Tight timeout bench staff huddle; no court geometry and no on-court players |
| 166845 | true | 4 | 0 | Close-up dark-uniform players and foreground white opponent beside visible blue sideline; no feet in shot |
| 174429 | false | 3 | 0 | Final-score close-up of three dark-uniform players; no court geometry and all feet outside shot |

## Tests and verifier-contract self-check

Per-file commands and final results, pasted:

```text
python -m pytest tests/platformkit/test_g296b_located_players.py -q
......                                                                   [100%]
6 passed in 1.28s
python -m pytest tests/platformkit/test_loc_rail_scope.py -q
.                                                                        [100%]
1 passed in 1.84s
```

The full dedicated test is pasted below. It pins every literal frame index
against the formula and both exact CSV headers; it also validates source PTS,
native dimensions, person-row uniqueness, allowed role/confidence values,
empty hidden-foot coordinates, bounds, and per-frame point counts.
No full pytest invocation was run. New Python harnesses stay below 300 LOC;
no allowlisted file grew, so A12 requires no allowlist change.

```python
"""Pin G296B's immutable frame selection and merge schema."""
import csv
import json
from pathlib import Path

from scripts.platformkit.tracking.g296b_located_players import (
    FRAME_HEADER, FRAME_INDICES, PLAYER_HEADER,
)


def test_exact_frame_indices_and_formula():
    expected = (0, 7584, 15168, 22752, 30335, 37919, 45503, 53087,
                60671, 68255, 75839, 83423, 91006, 98590, 106174, 113758,
                121342, 128926, 136510, 144094, 151677, 159261, 166845, 174429)
    assert FRAME_INDICES == expected
    assert FRAME_INDICES == tuple(round(i * 174429 / 23) for i in range(24))
    assert len(set(FRAME_INDICES)) == 24


def test_exact_csv_headers():
    assert PLAYER_HEADER == (
        "source_frame,person_index,role,feet_visible,foot_x_px,foot_y_px,confidence,note"
    )
    assert FRAME_HEADER == "source_frame,court_visible,shot_description,players_located"


def test_microsecond_seek_never_passes_target_pts():
    for frame in FRAME_INDICES:
        micros = frame * 1_000_000 // 30
        assert micros * 30 <= frame * 1_000_000 < (micros + 1) * 30


def test_manifest_source_pts_and_native_dimensions_when_present():
    root = Path(__file__).resolve().parents[2]
    path = root / "docs/evidence/tracking/g296b_located_players_artifact/manifest.json"
    if not path.exists():
        return
    manifest = json.loads(path.read_text())
    assert tuple(manifest["frame_indices"]) == FRAME_INDICES
    assert len(manifest["frames"]) == 24
    for row, index in zip(manifest["frames"], FRAME_INDICES):
        assert row["source_frame"] == index
        assert row["source_pts"] == index * 512
        assert (row["width"], row["height"]) == (1920, 1080)


def test_local_launcher_has_no_network_size_stop_or_other_worktree_fallback():
    root = Path(__file__).resolve().parents[2]
    wrapper = (root / "scripts/platformkit/tracking/g296b_pod_run.sh").read_text()
    assert "conv=fsync" in wrapper
    assert "du -sm" not in wrapper
    assert "USED_MB" not in wrapper
    assert '[ "$H" = a12 ]' in wrapper
    assert '|| WT=' not in wrapper


def test_committed_annotations_when_present():
    root = Path(__file__).resolve().parents[2]
    artifact = root / "docs/evidence/tracking/g296b_located_players_artifact"
    if not (artifact / "located_players.csv").exists():
        return  # Extraction harness can be tested before independent annotation.
    with (artifact / "located_players.csv").open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == PLAYER_HEADER.split(",")
        people = list(reader)
    with (artifact / "frames.csv").open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == FRAME_HEADER.split(",")
        frames = list(reader)
    assert tuple(int(row["source_frame"]) for row in frames) == FRAME_INDICES
    keys = [(row["source_frame"], row["person_index"]) for row in people]
    assert len(keys) == len(set(keys))
    for row in people:
        assert None not in row and all(value is not None for value in row.values())
        assert int(row["source_frame"]) in FRAME_INDICES
        assert row["role"] in {"player_on_court", "official", "bench_or_coach",
                                "spectator_or_media", "other"}
        assert row["confidence"] in {"confident", "approximate", "guess"}
        assert row["feet_visible"] in {"true", "false"}
        if row["feet_visible"] == "false":
            assert row["foot_x_px"] == row["foot_y_px"] == ""
        else:
            assert 0 <= float(row["foot_x_px"]) < 1920
            assert 0 <= float(row["foot_y_px"]) < 1080
    for row in frames:
        assert row["court_visible"] in {"true", "false"}
        assert row["shot_description"]
        assert int(row["players_located"]) == sum(
            p["source_frame"] == row["source_frame"] and
            p["role"] == "player_on_court" and p["feet_visible"] == "true"
            for p in people
        )

```

B1: all 24 fixed frames retained, including every zero-point frame; no metric
was filtered or computed. B2: new exact schemas only; no existing reader schema
changed. B3-B4: no quarantine or claim workflow. B5: only a12 compute scratch,
under the explicit B5 exception; no deployment. B6: no module moved or retired.
B7: all fixed clip-wide indices were viewed, not a head slice. B8: independent
locations sealed before joins; no fit or residual claim. B9: denominator is 24
unique source frames and per-frame person observations, not track identities.
B10: no threshold, verdict, bar, or production flag changed. B11: input
construction only; no system-performance or route-repeatability claim. Exact
source timestamps and fetched image hashes establish which images were judged,
not independent correctness of judgments. Q does not apply: this is a G-row
input construction, not an S-row scored signal or system comparison.

Evidence paths, all under g296b_located_players_artifact/: located_players.csv,
frames.csv, manifest.json, summary.json, gate.json, sequential_gate.json,
preliminary_gate.txt, pod_run.log, pod_seek_run.log, seek_frames_manifest.zip,
the 24 frames/frame_NNNNNN.jpg files and 24 ffmpeg_NNNNNN.log files enumerated
by the manifest, and the three explicitly described inspection PNGs. Every
referenced path exists locally. The memo and RESULTS_LEDGER row are committed
together after the separate location seal. Source data and all original bars
remain untouched. The memo date is the requested row date; pod UTC timestamps
cross into 2026-09-05 (the local work occurred on 2026-09-04 America/Chicago).

Whitespace note: standalone ffmpeg logs have trailing spaces removed for the git whitespace check. Their untouched originals remain inside seek_frames_manifest.zip. Probe outputs are unchanged.
